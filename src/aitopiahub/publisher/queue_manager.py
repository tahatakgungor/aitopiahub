"""
Redis sorted set tabanlı posting kuyruğu.
Score = Unix timestamp → en erken post ilk sırada.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class QueueItem:
    draft_id: str
    account_id: str
    post_format: str
    scheduled_for: datetime
    trend_score: float = 0.5


class QueueManager:
    """
    Per-account Redis sorted set ile post kuyruğu yönetir.
    key: queue:{account_id}
    score: scheduled_timestamp (Unix epoch)
    value: JSON payload
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    def _key(self, account_id: str) -> str:
        return f"queue:{account_id}"

    async def enqueue(self, item: QueueItem) -> None:
        """Post kuyruğa ekle."""
        score = item.scheduled_for.timestamp()
        payload = json.dumps({
            "draft_id": item.draft_id,
            "account_id": item.account_id,
            "post_format": item.post_format,
            "scheduled_for": item.scheduled_for.isoformat(),
            "trend_score": item.trend_score,
        })
        await self.redis.zadd(self._key(item.account_id), {payload: score})
        log.info(
            "enqueued",
            draft_id=item.draft_id,
            scheduled=str(item.scheduled_for),
        )

    async def dequeue_due(self, account_id: str) -> list[QueueItem]:
        """Zamanı gelmiş postları kuyruğdan al ve sil."""
        now_ts = time.time()
        key = self._key(account_id)

        # Zaman score'una göre filtrele
        due_items = await self.redis.zrangebyscore(key, 0, now_ts, withscores=False)

        if not due_items:
            return []

        # Atomik olarak sil
        async with self.redis.pipeline() as pipe:
            for item_str in due_items:
                pipe.zrem(key, item_str)
            await pipe.execute()

        result = []
        for item_str in due_items:
            try:
                data = json.loads(item_str)
                result.append(
                    QueueItem(
                        draft_id=data["draft_id"],
                        account_id=data["account_id"],
                        post_format=data["post_format"],
                        scheduled_for=datetime.fromisoformat(data["scheduled_for"]),
                        trend_score=data.get("trend_score", 0.5),
                    )
                )
            except (json.JSONDecodeError, KeyError) as e:
                log.warning("queue_parse_error", error=str(e))

        log.info("dequeued_due", account_id=account_id, count=len(result))
        return result

    async def peek(self, account_id: str, limit: int = 10) -> list[dict]:
        """Kuyruğa bakmak için (silmeden)."""
        key = self._key(account_id)
        items = await self.redis.zrange(key, 0, limit - 1, withscores=True)
        result = []
        for item_str, score in items:
            try:
                data = json.loads(item_str)
                data["score_ts"] = score
                result.append(data)
            except json.JSONDecodeError:
                pass
        return result

    async def queue_size(self, account_id: str) -> int:
        return await self.redis.zcard(self._key(account_id))

    async def scheduled_times(self, account_id: str) -> list[datetime]:
        """Bugün için scheduled datetime listesi döndür."""
        items = await self.redis.zrange(
            self._key(account_id), 0, -1, withscores=True
        )
        times = []
        for _, score in items:
            times.append(datetime.fromtimestamp(score, tz=timezone.utc))
        return times
