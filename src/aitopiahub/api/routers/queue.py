import json
from fastapi import APIRouter, HTTPException, Header
from aitopiahub.core.config import get_settings
from aitopiahub.core.redis_client import get_redis
from aitopiahub.publisher.queue_manager import QueueManager

router = APIRouter()


def _auth(x_api_key: str = Header(...)):
    if x_api_key != get_settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Geçersiz API key")


@router.get("/accounts/{account_handle}/queue")
async def get_queue(account_handle: str, x_api_key: str = Header(...)):
    _auth(x_api_key)
    redis = get_redis()
    mgr = QueueManager(redis)
    items = await mgr.peek(account_handle, limit=20)
    size = await mgr.queue_size(account_handle)
    return {"account": account_handle, "queue_size": size, "next_items": items}


@router.post("/accounts/{account_handle}/queue/pause")
async def pause_queue(account_handle: str, x_api_key: str = Header(...)):
    _auth(x_api_key)
    redis = get_redis()
    await redis.set(f"queue_paused:{account_handle}", "1", ex=3600)
    return {"status": "paused", "account": account_handle}


@router.post("/accounts/{account_handle}/queue/resume")
async def resume_queue(account_handle: str, x_api_key: str = Header(...)):
    _auth(x_api_key)
    redis = get_redis()
    await redis.delete(f"queue_paused:{account_handle}")
    return {"status": "resumed", "account": account_handle}
