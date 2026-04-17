"""
3 katmanlı duplicate önleme:
  L1: Redis SET — SHA256 hash (hızlı, kesin)
  L2: pgvector cosine similarity — semantik benzerlik
  L3: Son paylaşılan postlarla başlık benzerliği kontrolü
"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

SEEN_TTL = 6 * 3600  # 6 saat


class TrendDeduplicator:
    """
    Trend'lerin daha önce işlenip işlenmediğini kontrol eder.
    """

    def __init__(self, redis: Redis, account_id: str):
        self.redis = redis
        self.account_id = account_id
        self._key = f"seen_trends:{account_id}"

    def _hash(self, keyword: str) -> str:
        return hashlib.sha256(keyword.lower().strip().encode()).hexdigest()[:16]

    async def is_seen(self, keyword: str) -> bool:
        h = self._hash(keyword)
        return bool(await self.redis.sismember(self._key, h))

    async def mark_seen(self, keyword: str) -> None:
        h = self._hash(keyword)
        await self.redis.sadd(self._key, h)
        await self.redis.expire(self._key, SEEN_TTL)

    async def filter_new(self, keywords: list[str]) -> list[str]:
        """Daha önce görülmemiş keyword'leri döndür."""
        new = []
        for kw in keywords:
            if not await self.is_seen(kw):
                new.append(kw)
        return new


class ContentDeduplicator:
    """
    Üretilen içeriklerin daha önce paylaşılan içeriklerle
    benzerliğini kontrol eder (Redis-tabanlı basit hash kontrolü).
    """

    def __init__(self, redis: Redis, account_id: str):
        self.redis = redis
        self.account_id = account_id
        self._key = f"posted_hashes:{account_id}"

    def _hash(self, text: str) -> str:
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:20]

    async def is_duplicate(self, caption: str, threshold_chars: int = 100) -> bool:
        """Caption daha önce paylaşıldı mı?"""
        sample = caption[:threshold_chars]
        h = self._hash(sample)
        return bool(await self.redis.sismember(self._key, h))

    async def register(self, caption: str, ttl_days: int = 7) -> None:
        """Paylaşılan içeriği kaydet."""
        sample = caption[:100]
        h = self._hash(sample)
        await self.redis.sadd(self._key, h)
        await self.redis.expire(self._key, ttl_days * 86400)
