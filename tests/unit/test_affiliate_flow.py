from __future__ import annotations

import asyncio

from aitopiahub.tasks.content_tasks import _maybe_attach_affiliate
from aitopiahub.monetization import AffiliateCatalog, OfferRanker, CTAInjector, LinkTracker


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.counters: dict[str, int] = {}

    async def keys(self, pattern: str):
        if pattern == "published:*":
            return [k for k in self.store if k.startswith("published:")]
        return []

    async def get(self, key: str):
        return self.store.get(key)

    async def incr(self, key: str):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, ttl: int):
        return None

    async def hset(self, key: str, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping:
            for k, v in mapping.items():
                bucket[str(k)] = str(v)
        elif field is not None:
            bucket[str(field)] = str(value)


def test_maybe_attach_affiliate_returns_payload_when_quality_high() -> None:
    redis = _FakeRedis()
    # cadence gate: third call should pass
    asyncio.run(redis.incr("affiliate_cadence:aitopiahub_news"))
    asyncio.run(redis.incr("affiliate_cadence:aitopiahub_news"))

    payload = asyncio.run(
        _maybe_attach_affiliate(
            redis=redis,
            tracker=LinkTracker(redis, "aitopiahub_news", "launch"),
            offer_ranker=OfferRanker(),
            catalog=AffiliateCatalog(),
            cta_injector=CTAInjector(),
            account_handle="aitopiahub_news",
            keyword="AI automation workflow",
            trend_score=0.9,
            caption="AI ile üretkenliği artırmanın pratik yolları",
            quality_score=88,
            draft_id="draft-1",
            ratio_max=0.3,
            min_quality_for_affiliate=82,
            monetization_enabled=True,
        )
    )

    assert payload is not None
    assert payload["offer_id"]
    assert payload["tracking_url"].startswith("https://")
    assert payload["commercial_intent_score"] >= 0.35
