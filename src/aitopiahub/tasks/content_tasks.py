"""
İçerik üretimi Celery task'ları.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone

from aitopiahub.tasks.celery_app import app
from aitopiahub.core.config import AccountConfig, get_settings
from aitopiahub.core.constants import PostFormat
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.content_engine.llm_client import LLMClient
from aitopiahub.content_engine.post_generator import PostGenerator
from aitopiahub.content_engine.safety_checker import SafetyChecker
from aitopiahub.trend_engine.deduplicator import ContentDeduplicator
from aitopiahub.trend_engine.rss_fetcher import RSSFetcher, RSSItem
from aitopiahub.trend_engine.trend_scorer import ScoredTrend
from aitopiahub.image_engine.carousel_builder import CarouselBuilder
from aitopiahub.image_engine.image_store import ImageStore
from aitopiahub.monetization import (
    AffiliateCatalog,
    OfferRanker,
    CTAInjector,
    LinkTracker,
)

log = get_logger(__name__)


@app.task(
    name="aitopiahub.tasks.content_tasks.generate_pending_content",
    bind=True,
    max_retries=2,
)
def generate_pending_content(self, account_handle: str) -> dict:
    """Redis Pub/Sub'dan bekleyen trendler için içerik üret."""
    return asyncio.run(_generate_async(account_handle))


async def _generate_async(account_handle: str) -> dict:
    config = AccountConfig.for_account(account_handle)
    redis = get_redis()
    llm = LLMClient()

    # Redis'ten bekleyen trend event'leri oku
    pending_key = f"pending_trends:{account_handle}"
    trend_data_list = []
    while True:
        item = await redis.lpop(pending_key)
        if not item:
            break
        try:
            trend_data_list.append(json.loads(item))
        except json.JSONDecodeError:
            pass

    if not trend_data_list:
        log.debug("no_pending_trends", account=account_handle)
        return {"generated": 0}

    # RSS item'larını topla (kaynak materyal)
    rss_fetcher = RSSFetcher()
    all_rss_items = await rss_fetcher.fetch_all()

    generator = PostGenerator(config, llm)
    content_dedup = ContentDeduplicator(redis, account_handle)
    safety_checker = SafetyChecker(llm, config, content_dedup)
    carousel_builder = CarouselBuilder()
    image_store = ImageStore()

    generated_count = 0
    hook_bank = await _load_proven_hooks(redis, account_handle)
    hashtag_weights = await _load_hashtag_weights(redis, account_handle)
    ab_ratio = await _effective_ab_ratio(redis, account_handle, config.ab_test_ratio)
    tracker = LinkTracker(redis, account_handle, config.default_utm_campaign)
    offer_ranker = OfferRanker()
    catalog = AffiliateCatalog()
    cta_injector = CTAInjector()
    approval_mode = await _is_manual_approval_mode(redis, account_handle, config.requires_manual_approval_days)
    if hashtag_weights:
        generator.hashtag_optimizer.set_weights(hashtag_weights)

    for trend_data in trend_data_list[:3]:  # Max 3 trend/döngü
        keyword = trend_data.get("keyword", "")
        score = trend_data.get("score", 0.5)

        # İlgili RSS item'larını bul
        related = _find_related_items(keyword, all_rss_items, limit=5)

        trend = ScoredTrend(
            keyword=keyword,
            raw_score=score,
            final_score=score,
            google_trend_index=0,
            news_mentions=len(related),
            reddit_score=0,
            velocity=0,
            keyword_match_score=1.0,
            hours_old=0,
            first_seen_at=__import__("datetime").datetime.utcnow(),
        )

        # İçerik üret (A/B varyantlar)
        posts = await generator.generate(
            trend,
            related,
            post_format=PostFormat.CAROUSEL,
            proven_hooks=hook_bank,
        )

        approved_posts = [p for p in posts if p.approved]
        approved_posts.sort(key=lambda p: p.quality_score, reverse=True)
        selected_posts = approved_posts[:1]
        if len(approved_posts) > 1 and random.random() < ab_ratio:
            selected_posts.append(approved_posts[1])

        for post in selected_posts:
            if not post.approved:
                log.info("draft_rejected", keyword=keyword, score=post.quality_score)
                continue
            if post.quality_score < config.min_publish_quality_score:
                log.info(
                    "draft_below_publish_threshold",
                    keyword=keyword,
                    score=post.quality_score,
                    threshold=config.min_publish_quality_score,
                )
                continue

            # Safety check
            is_safe, reason = await safety_checker.check(post.caption_text)
            if not is_safe:
                log.info("draft_safety_rejected", keyword=keyword, reason=reason)
                continue

            affiliate_meta = await _maybe_attach_affiliate(
                redis=redis,
                tracker=tracker,
                offer_ranker=offer_ranker,
                catalog=catalog,
                cta_injector=cta_injector,
                account_handle=account_handle,
                keyword=keyword,
                trend_score=score,
                caption=post.caption_text,
                quality_score=post.quality_score,
                draft_id=str(post.variant_group) + post.variant_label,
                ratio_max=config.affiliate_ratio_max,
                min_quality_for_affiliate=config.min_quality_for_affiliate,
                monetization_enabled=config.monetization_enabled,
            )
            if affiliate_meta:
                post.caption_text = affiliate_meta["caption"]

            # Görsel üret
            if post.slide_texts and post.post_format == PostFormat.CAROUSEL:
                slides = await carousel_builder.build(
                    post.slide_texts,
                    post.image_prompt_hint,
                )
                image_paths = []
                for slide in slides:
                    path, url = await image_store.save(
                        slide.image_bytes,
                        account_id=account_handle,
                        subfolder=f"carousel_{post.variant_group}",
                    )
                    image_paths.append((path, url))

                # Draft'ı Redis queue'ya ekle (publisher için)
                draft_data = {
                    "draft_id": str(post.variant_group) + post.variant_label,
                    "account_handle": account_handle,
                    "post_format": post.post_format,
                    "caption": post.caption_text,
                    "hashtags": post.hashtags,
                    "keyword": keyword,
                    "variant_label": post.variant_label,
                    "angle": post.writer_output.get("angle"),
                    "hook_text": (post.caption_text.splitlines()[0] if post.caption_text else "")[:140],
                    "image_paths": [p[0] for p in image_paths],
                    "image_urls": [p[1] for p in image_paths],
                    "quality_score": post.quality_score,
                    "trend_score": score,
                    "offer_id": affiliate_meta.get("offer_id") if affiliate_meta else None,
                    "tracking_url": affiliate_meta.get("tracking_url") if affiliate_meta else None,
                    "cta_variant": affiliate_meta.get("cta_variant") if affiliate_meta else None,
                    "commercial_intent_score": (
                        affiliate_meta.get("commercial_intent_score", 0.0) if affiliate_meta else 0.0
                    ),
                    "is_affiliate": bool(affiliate_meta),
                }
                target_queue = f"review_drafts:{account_handle}" if approval_mode else f"ready_drafts:{account_handle}"
                await redis.rpush(target_queue, json.dumps(draft_data))
                
                # Shorts pipeline opsiyonel (default: kapalı)
                settings = get_settings()
                if settings.enable_shorts_pipeline:
                    from aitopiahub.tasks.youtube_tasks import generate_and_publish_shorts
                    generate_and_publish_shorts.delay(account_handle, json.dumps(draft_data))

                generated_count += 1
                log.info(
                    "draft_queued",
                    keyword=keyword,
                    variant=post.variant_label,
                    approval_mode=approval_mode,
                    affiliate=bool(affiliate_meta),
                    youtube_triggered=bool(settings.enable_shorts_pipeline),
                )

    log.info("content_pipeline_done", account=account_handle, generated=generated_count)
    return {"generated": generated_count}


def _find_related_items(keyword: str, items: list[RSSItem], limit: int = 5) -> list[RSSItem]:
    """Keyword ile en alakalı RSS item'larını bul (basit keyword match)."""
    kw_lower = keyword.lower()
    scored = []
    for item in items:
        score = 0
        if kw_lower in item.title.lower():
            score += 3
        if item.content and kw_lower in item.content.lower():
            score += 1
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


async def _load_proven_hooks(redis, account_handle: str, limit: int = 5) -> list[str]:
    key = f"feedback:hook_bank:{account_handle}"
    hooks = await redis.zrevrange(key, 0, limit - 1)
    return [h for h in hooks if isinstance(h, str) and h.strip()]


async def _load_hashtag_weights(redis, account_handle: str) -> dict[str, float]:
    key = f"feedback:hashtag_weights:{account_handle}"
    raw = await redis.hgetall(key)
    weights: dict[str, float] = {}
    for tag, value in raw.items():
        try:
            weights[tag] = float(value)
        except (TypeError, ValueError):
            continue
    return weights


async def _effective_ab_ratio(redis, account_handle: str, base_ratio: float) -> float:
    """
    Veri arttıkça A/B test yoğunluğunu artır:
    - <10 post analiz: base ratio (default %30)
    - >=10 post analiz: en az %45
    """
    data = await redis.get(f"feedback_stats:{account_handle}")
    if not data:
        return base_ratio
    try:
        parsed = json.loads(data)
        total_posts = int(parsed.get("total_posts", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return base_ratio
    if total_posts >= 10:
        return max(base_ratio, 0.45)
    return base_ratio


async def _is_manual_approval_mode(redis, account_handle: str, days: int) -> bool:
    launch_key = f"account_launch_at:{account_handle}"
    now = datetime.now(timezone.utc)
    launch_raw = await redis.get(launch_key)
    if not launch_raw:
        await redis.set(launch_key, now.isoformat())
        return True
    try:
        launch_dt = datetime.fromisoformat(str(launch_raw).replace("Z", "+00:00"))
        if launch_dt.tzinfo is None:
            launch_dt = launch_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return (now - launch_dt) < timedelta(days=days)


async def _maybe_attach_affiliate(
    redis,
    tracker: LinkTracker,
    offer_ranker: OfferRanker,
    catalog: AffiliateCatalog,
    cta_injector: CTAInjector,
    account_handle: str,
    keyword: str,
    trend_score: float,
    caption: str,
    quality_score: float,
    draft_id: str,
    ratio_max: float,
    min_quality_for_affiliate: int,
    monetization_enabled: bool,
) -> dict | None:
    if not monetization_enabled:
        return None
    if quality_score < min_quality_for_affiliate:
        return None
    if trend_score < 0.6:
        return None

    ratio = await _current_affiliate_ratio(redis, account_handle)
    if ratio >= ratio_max:
        return None
    if not await _cadence_allows_affiliate(redis, account_handle):
        return None

    ranked = offer_ranker.rank(catalog.list_offers(), keyword=keyword, caption=caption, limit=1)
    if not ranked:
        return None
    top = ranked[0]
    if top.commercial_intent_score < 0.35:
        return None

    _, tracking_url = await tracker.build_tracking_url(
        offer_id=top.offer.offer_id,
        base_url=top.offer.base_url,
        keyword=keyword,
        draft_id=draft_id,
    )
    new_caption, cta_variant = cta_injector.inject(caption, top.offer, tracking_url)
    return {
        "offer_id": top.offer.offer_id,
        "tracking_url": tracking_url,
        "cta_variant": cta_variant,
        "commercial_intent_score": top.commercial_intent_score,
        "caption": new_caption,
    }


async def _current_affiliate_ratio(redis, account_handle: str) -> float:
    keys = await redis.keys("published:*")
    total = 0
    affiliate = 0
    for key in keys:
        payload = await redis.get(key)
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("account") != account_handle:
            continue
        total += 1
        if data.get("is_affiliate"):
            affiliate += 1
    if total == 0:
        return 0.0
    return affiliate / total


async def _cadence_allows_affiliate(redis, account_handle: str) -> bool:
    """
    Feed'de satış oranını kabaca 1/3 altında tutmak için her 3 içerikte 1 affiliate.
    """
    key = f"affiliate_cadence:{account_handle}"
    index = await redis.incr(key)
    await redis.expire(key, 30 * 86400)
    return index % 3 == 0
@app.task(name="aitopiahub.tasks.content_tasks.run_autonomous_kids_cycle")
def run_autonomous_kids_cycle(account_handle: str):
    """Bilingual (TR/EN) kids production döngüsünü tetikler."""
    from aitopiahub.content_engine.episode_manager import EpisodeManager
    manager = EpisodeManager(account_handle)
    return asyncio.run(manager.run_automated_cycle())


@app.task(
    name="aitopiahub.tasks.content_tasks.run_kids_language_cycle",
    bind=True,
    max_retries=2,
)
def run_kids_language_cycle(self, account_handle: str, lang: str, content_mode: str = "demand_driven") -> dict:
    """Günlük slot bazlı tek dil üretim görevi (TR/EN + mode)."""
    return asyncio.run(_run_kids_language_cycle_async(self, account_handle, lang, content_mode))

@app.task(name="aitopiahub.tasks.content_tasks.run_self_improvement")
def run_self_improvement(account_handle: str):
    """Zeka katmanını çalıştırarak takvimi optimize eder."""
    from aitopiahub.content_engine.agents.feedback_agent import FeedbackAgent
    agent = FeedbackAgent(account_handle=account_handle)
    return asyncio.run(agent.analyze_and_optimize({}, {}))


async def _run_kids_language_cycle_async(
    task_ctx,
    account_handle: str,
    lang: str,
    content_mode: str = "demand_driven",
) -> dict:
    from aitopiahub.content_engine.episode_manager import EpisodeManager

    settings = get_settings()
    redis = get_redis()
    day_key = datetime.now(timezone.utc).strftime("%Y%m%d")
    mode = (content_mode or "demand_driven").strip().lower()
    if mode not in {"fairy_tale", "demand_driven"}:
        mode = "demand_driven"

    retry_key = f"retry_budget:kids:{account_handle}:{lang}:{mode}:{day_key}"
    dlq_key = f"dlq:kids:{account_handle}"

    try:
        manager = EpisodeManager(account_handle)
        url = await manager.run_daily_flow(lang=lang, content_mode=mode)
        if not url:
            raise RuntimeError("empty_publish_url")

        await redis.delete(retry_key)
        return {"ok": True, "lang": lang, "mode": mode, "url": url}
    except Exception as exc:
        failures = await redis.incr(retry_key)
        await redis.expire(retry_key, 2 * 86400)
        payload = {
            "account": account_handle,
            "lang": lang,
            "content_mode": mode,
            "error": str(exc),
            "quality_failure_reason": (str(exc).split("quality_gate_failed:", 1)[1] if "quality_gate_failed:" in str(exc) else None),
            "failures": failures,
            "task_retries": task_ctx.request.retries,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if failures > settings.kids_retry_budget or task_ctx.request.retries >= settings.kids_retry_budget:
            await redis.rpush(dlq_key, json.dumps(payload))
            log.error("kids_cycle_dead_lettered", **payload)
            raise

        log.warning("kids_cycle_retrying", **payload)
        raise task_ctx.retry(exc=exc, countdown=min(300, 30 * (task_ctx.request.retries + 1)))
