from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from aitopiahub.trend_engine.handoff import build_mention_map, enqueue_new_trends
from aitopiahub.trend_engine.trend_scorer import ScoredTrend


class _FakeRedis:
    def __init__(self):
        self.rpush_calls: list[tuple[str, str]] = []
        self.publish_calls: list[tuple[str, str]] = []

    async def rpush(self, key: str, value: str) -> None:
        self.rpush_calls.append((key, value))

    async def publish(self, channel: str, value: str) -> None:
        self.publish_calls.append((channel, value))


def test_build_mention_map_counts_case_insensitive_mentions() -> None:
    result = build_mention_map(
        seed_keywords=["ChatGPT", "yapay zeka"],
        text_blobs=[
            "ChatGPT yeni modelini duyurdu",
            "YAPAY ZEKA piyasayı dönüştürüyor",
            "chatgpt enterprise güncellemesi",
        ],
    )

    assert result["chatgpt"] == 2
    assert result["yapay zeka"] == 1


def test_enqueue_new_trends_pushes_pending_and_publishes() -> None:
    redis = _FakeRedis()
    trends = [
        ScoredTrend(
            keyword="chatgpt",
            raw_score=0.9,
            final_score=0.82,
            google_trend_index=85,
            news_mentions=7,
            reddit_score=1200,
            velocity=2.1,
            keyword_match_score=1.0,
            hours_old=0.1,
            first_seen_at=datetime.now(timezone.utc),
        ),
        ScoredTrend(
            keyword="gemini",
            raw_score=0.8,
            final_score=0.75,
            google_trend_index=70,
            news_mentions=5,
            reddit_score=700,
            velocity=1.8,
            keyword_match_score=1.0,
            hours_old=0.2,
            first_seen_at=datetime.now(timezone.utc),
        ),
    ]

    pushed = asyncio.run(
        enqueue_new_trends(
            redis=redis,
            account_handle="aitopiahub_news",
            trends=trends,
            max_per_cycle=1,
        )
    )

    assert pushed == 1
    assert len(redis.rpush_calls) == 1
    assert len(redis.publish_calls) == 1

    pending_key, pending_payload = redis.rpush_calls[0]
    channel, publish_payload = redis.publish_calls[0]

    assert pending_key == "pending_trends:aitopiahub_news"
    assert channel == "new_trend:aitopiahub_news"
    assert pending_payload == publish_payload

    payload = json.loads(pending_payload)
    assert payload["keyword"] == "chatgpt"
    assert payload["score"] == 0.82
