from fastapi import APIRouter
from aitopiahub.core.redis_client import get_redis

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    try:
        redis = get_redis()
        await redis.ping()
        return {"status": "ready", "redis": "ok"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}
