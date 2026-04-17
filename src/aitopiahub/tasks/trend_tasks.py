"""
Trend tespiti Celery task'ları.
"""

from __future__ import annotations

import asyncio

from aitopiahub.tasks.celery_app import app
from aitopiahub.core.config import AccountConfig
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.trend_engine.google_trends import GoogleTrendsFetcher
from aitopiahub.trend_engine.news_aggregator import NewsAggregator
from aitopiahub.trend_engine.rss_fetcher import RSSFetcher
from aitopiahub.trend_engine.reddit_fetcher import RedditFetcher
from aitopiahub.trend_engine.trend_scorer import TrendScorer, RawSignal
from aitopiahub.trend_engine.relevance_filter import RelevanceFilter
from aitopiahub.trend_engine.deduplicator import TrendDeduplicator
from aitopiahub.trend_engine.handoff import build_mention_map, enqueue_new_trends
from aitopiahub.content_engine.llm_client import LLMClient

log = get_logger(__name__)


@app.task(
    name="aitopiahub.tasks.trend_tasks.fetch_and_score_trends",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def fetch_and_score_trends(self, account_handle: str) -> dict:
    """
    Bir hesap için trend pipeline'ını çalıştır:
    Fetch → Score → Filter → Deduplicate → DB'ye yaz
    """
    return asyncio.run(_fetch_and_score_async(account_handle))


async def _fetch_and_score_async(account_handle: str) -> dict:
    config = AccountConfig.for_account(account_handle)
    redis = get_redis()
    llm = LLMClient()

    log.info("trend_pipeline_start", account=account_handle)

    # Paralel fetch
    google_fetcher = GoogleTrendsFetcher(config.seed_keywords)
    rss_fetcher = RSSFetcher()
    reddit_fetcher = RedditFetcher()
    news_fetcher = NewsAggregator()

    google_trends, rss_items, reddit_posts, news_items = await asyncio.gather(
        google_fetcher.fetch_trends(),
        rss_fetcher.fetch_all(),
        reddit_fetcher.fetch_hot(),
        news_fetcher.fetch_tech_headlines(config.seed_keywords),
        return_exceptions=True,
    )

    if isinstance(google_trends, Exception):
        log.warning("google_trends_failed", error=str(google_trends))
        google_trends = []
    if isinstance(rss_items, Exception):
        log.warning("rss_fetch_failed", error=str(rss_items))
        rss_items = []
    if isinstance(reddit_posts, Exception):
        log.warning("reddit_fetch_failed", error=str(reddit_posts))
        reddit_posts = []
    if isinstance(news_items, Exception):
        log.warning("newsapi_fetch_failed", error=str(news_items))
        news_items = []

    # Reddit keyword → score map
    reddit_map: dict[str, int] = {}
    for post in reddit_posts:
        words = post.title.lower().split()
        for word in words:
            if len(word) > 4:
                reddit_map[word] = reddit_map.get(word, 0) + post.score

    # RSS + News keyword → mention count
    mention_map = build_mention_map(
        seed_keywords=config.seed_keywords,
        text_blobs=[item.title for item in rss_items] + [item.title for item in news_items],
    )
    seed_keywords_lower = {kw.lower() for kw in config.seed_keywords}

    # Signal oluştur
    signals = []
    for gt in google_trends:
        signal = RawSignal(
            keyword=gt.keyword,
            google_trend_index=gt.trend_index,
            news_mentions=mention_map.get(gt.keyword.lower(), 0),
            reddit_score=reddit_map.get(gt.keyword.lower().split()[0], 0),
            keyword_match_score=1.0 if gt.keyword.lower() in seed_keywords_lower else 0.5,
        )
        signals.append(signal)

    # Seed keyword'ler için de signal ekle
    for kw in config.seed_keywords:
        if not any(s.keyword == kw for s in signals):
            signals.append(
                RawSignal(
                    keyword=kw,
                    google_trend_index=0,
                    news_mentions=mention_map.get(kw.lower(), 0),
                    reddit_score=reddit_map.get(kw.lower(), 0),
                    keyword_match_score=1.0,
                )
            )

    if not signals:
        log.warning("no_signals", account=account_handle)
        return {"trends": 0}

    # Score
    scorer = TrendScorer()
    scored = scorer.score_batch(signals)

    # Relevance filter (LLM)
    relevant_scored = [s for s in scored if s.final_score >= config.min_trend_score]
    if relevant_scored:
        rel_filter = RelevanceFilter(llm, config.niche, config.blocked_keywords)
        relevant_scored = await rel_filter.filter(relevant_scored)

    # Dedup
    dedup = TrendDeduplicator(redis, str(account_handle))
    new_keywords = await dedup.filter_new([s.keyword for s in relevant_scored])
    new_trends = [s for s in relevant_scored if s.keyword in new_keywords]

    for trend in new_trends:
        await dedup.mark_seen(trend.keyword)

    # Content pipeline handoff: kalıcı liste + opsiyonel pub/sub event
    if new_trends:
        await enqueue_new_trends(
            redis=redis,
            account_handle=account_handle,
            trends=new_trends,
            max_per_cycle=config.max_trends_per_cycle,
        )

    log.info(
        "trend_pipeline_done",
        account=account_handle,
        signals=len(signals),
        scored=len(scored),
        relevant=len(relevant_scored),
        new=len(new_trends),
    )

    return {
        "signals": len(signals),
        "scored": len(scored),
        "relevant": len(relevant_scored),
        "new_trends": len(new_trends),
        "top_trend": new_trends[0].keyword if new_trends else None,
    }
