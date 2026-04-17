from __future__ import annotations

import asyncio

from aitopiahub.monetization import AffiliateCatalog, OfferRanker, CTAInjector, LinkTracker


class _FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}

    async def hset(self, key: str, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping:
            for k, v in mapping.items():
                bucket[str(k)] = str(v)
        elif field is not None:
            bucket[str(field)] = str(value)

    async def hget(self, key: str, field: str):
        return self.hashes.get(key, {}).get(field)

    async def hincrby(self, key: str, field: str, amount: int):
        bucket = self.hashes.setdefault(key, {})
        current = int(bucket.get(field, "0"))
        bucket[field] = str(current + amount)


def test_offer_ranker_returns_ranked_results() -> None:
    catalog = AffiliateCatalog()
    ranker = OfferRanker()

    ranked = ranker.rank(
        catalog.list_offers(),
        keyword="AI productivity workflow",
        caption="Bugün automation ve notes için güçlü bir AI rehberi",
    )

    assert ranked
    assert ranked[0].commercial_intent_score >= ranked[-1].commercial_intent_score


def test_cta_injector_appends_single_cta_block() -> None:
    offer = AffiliateCatalog().list_offers()[0]
    injector = CTAInjector()
    caption, variant = injector.inject("Kısa içerik metni", offer, "https://example.com/t")

    assert "https://example.com/t" in caption
    assert "affiliate" in caption.lower()
    assert variant == "soft_value_cta"


def test_link_tracker_builds_utm_and_resolves() -> None:
    redis = _FakeRedis()
    tracker = LinkTracker(redis, account_handle="aitopiahub_news", campaign="launch")

    code, tracking_url = asyncio.run(
        tracker.build_tracking_url(
            offer_id="notion_ai",
            base_url="https://example.com/product",
            keyword="ai",
            draft_id="draft-1",
        )
    )

    assert code
    assert "utm_campaign=launch" in tracking_url
    resolved = asyncio.run(tracker.resolve(code))
    assert resolved == tracking_url
