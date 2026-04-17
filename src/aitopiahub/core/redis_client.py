import redis.asyncio as aioredis
from redis.asyncio import Redis

from aitopiahub.core.config import get_settings

def get_redis() -> Redis:
    settings = get_settings()
    # Celery task'larında asyncio.run ile loop değişebildiği için
    # global async redis client farklı loop'a bağlanıp hata üretiyor.
    # Bu nedenle loop-bağımsız şekilde her çağrıda yeni client döndür.
    return aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


class RateLimiter:
    """Redis token bucket — her endpoint için ayrı bucket."""

    def __init__(self, redis: Redis, key: str, capacity: int, refill_per_minute: float):
        self.redis = redis
        self.key = key
        self.capacity = capacity
        self.refill_rate = refill_per_minute  # token/dakika

    async def acquire(self) -> bool:
        """Token al. Başarılı ise True döner, yoksa False."""
        script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local data = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(data[1]) or capacity
        local last_refill = tonumber(data[2]) or now

        -- Token yenile
        local elapsed = (now - last_refill) / 60  -- dakikaya çevir
        tokens = math.min(capacity, tokens + elapsed * refill_rate)

        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
            redis.call('EXPIRE', key, 3600)
            return 1
        else
            redis.call('HSET', key, 'last_refill', now)
            return 0
        end
        """
        import time
        result = await self.redis.eval(
            script, 1, self.key, self.capacity, self.refill_rate, time.time()
        )
        return bool(result)

    async def wait_for_token(self, max_wait_seconds: int = 300) -> bool:
        """Token müsait olana kadar bekle."""
        import asyncio
        waited = 0
        interval = 5
        while waited < max_wait_seconds:
            if await self.acquire():
                return True
            await asyncio.sleep(interval)
            waited += interval
        return False
