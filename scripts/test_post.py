#!/usr/bin/env python3
"""
Tek bir post üretimini test eder — gerçek yayınlama yapmaz (--dry-run).
Kullanım: python scripts/test_post.py --account aitopiahub_news --keyword "ChatGPT" --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


async def test_pipeline(account_handle: str, keyword: str, dry_run: bool) -> None:
    from aitopiahub.core.config import AccountConfig
    from aitopiahub.core.logging import configure_logging
    from aitopiahub.content_engine.llm_client import LLMClient
    from aitopiahub.content_engine.post_generator import PostGenerator
    from aitopiahub.trend_engine.rss_fetcher import RSSFetcher
    from aitopiahub.trend_engine.trend_scorer import ScoredTrend
    from aitopiahub.core.constants import PostFormat
    from aitopiahub.image_engine.carousel_builder import CarouselBuilder
    import datetime

    configure_logging()

    print(f"\n{'='*60}")
    print(f"TEST POST — {account_handle} | keyword: {keyword}")
    print(f"{'='*60}\n")

    config = AccountConfig.for_account(account_handle)
    llm = LLMClient()
    generator = PostGenerator(config, llm)
    rss_fetcher = RSSFetcher()

    print("📡 RSS kaynakları çekiliyor...")
    rss_items = await rss_fetcher.fetch_all()
    print(f"   {len(rss_items)} haber bulundu\n")

    trend = ScoredTrend(
        keyword=keyword,
        raw_score=0.75,
        final_score=0.75,
        google_trend_index=70,
        news_mentions=5,
        reddit_score=1000,
        velocity=1.5,
        keyword_match_score=1.0,
        hours_old=0.5,
        first_seen_at=datetime.datetime.utcnow(),
    )

    related = [
        item for item in rss_items
        if keyword.lower() in item.title.lower()
    ][:5]
    print(f"📰 İlgili haber: {len(related)} kaynak\n")

    print("🤖 4 ajanlı içerik pipeline çalışıyor...")
    posts = await generator.generate(trend, related, PostFormat.CAROUSEL)

    for post in posts:
        print(f"\n{'─'*50}")
        print(f"VARIANT {post.variant_label} | Format: {post.post_format}")
        print(f"Kalite: {post.quality_score:.1f}/100 | Onay: {'✅' if post.approved else '❌'}")
        print(f"\nCaption:\n{post.caption_text[:400]}")
        print(f"\nHashtag'ler: {', '.join('#' + h for h in post.hashtags[:8])}...")

        if post.slide_texts:
            print(f"\nSlayt sayısı: {len(post.slide_texts)}")

    if not dry_run and posts:
        print("\n⚠️  Gerçek yayınlama için --dry-run bayrağını kaldır")

    if dry_run:
        approved = [p for p in posts if p.approved]
        if approved and approved[0].slide_texts:
            print("\n🎨 Carousel görsel üretimi test ediliyor...")
            builder = CarouselBuilder()
            slides = await builder.build(
                approved[0].slide_texts,
                approved[0].image_prompt_hint,
                generate_ai_cover=True,
            )
            print(f"   {len(slides)} slayt üretildi")
            for s in slides:
                print(f"   [{s.index}] {s.slide_type} — {len(s.image_bytes)//1024} KB")

    print(f"\n{'='*60}")
    print("✅ Test tamamlandı")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default="aitopiahub_news")
    parser.add_argument("--keyword", default="artificial intelligence")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    asyncio.run(test_pipeline(args.account, args.keyword, args.dry_run))
