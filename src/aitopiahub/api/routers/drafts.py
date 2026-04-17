import json
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from aitopiahub.core.config import get_settings
from aitopiahub.core.redis_client import get_redis

router = APIRouter()


def _auth(x_api_key: str):
    if x_api_key != get_settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Geçersiz API key")


class RejectBody(BaseModel):
    reason: str = ""


@router.get("/drafts/{account_handle}")
async def list_drafts(account_handle: str, x_api_key: str = Header(...)):
    """Bekleyen draft'ları listele (review + ready)."""
    _auth(x_api_key)
    redis = get_redis()
    review_items = await redis.lrange(f"review_drafts:{account_handle}", 0, 49)
    ready_items = await redis.lrange(f"ready_drafts:{account_handle}", 0, 49)
    drafts = []
    for item_str in review_items:
        try:
            payload = json.loads(item_str)
            payload["approval_state"] = "review"
            drafts.append(payload)
        except json.JSONDecodeError:
            pass
    for item_str in ready_items:
        try:
            payload = json.loads(item_str)
            payload["approval_state"] = "ready"
            drafts.append(payload)
        except json.JSONDecodeError:
            pass
    return {
        "account": account_handle,
        "count": len(drafts),
        "review_count": len(review_items),
        "ready_count": len(ready_items),
        "drafts": drafts,
    }


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, account_handle: str, x_api_key: str = Header(...)):
    """Draft'ı review kuyruğundan ready kuyruğuna taşır."""
    _auth(x_api_key)
    redis = get_redis()
    review_key = f"review_drafts:{account_handle}"
    ready_key = f"ready_drafts:{account_handle}"
    items = await redis.lrange(review_key, 0, -1)
    moved = False
    for item_str in items:
        try:
            payload = json.loads(item_str)
        except json.JSONDecodeError:
            continue
        if payload.get("draft_id") == draft_id:
            await redis.lrem(review_key, 1, item_str)
            await redis.rpush(ready_key, item_str)
            moved = True
            break
    if not moved:
        raise HTTPException(status_code=404, detail="Draft review kuyruğunda bulunamadı")
    return {"status": "approved", "draft_id": draft_id, "account": account_handle}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    body: RejectBody,
    x_api_key: str = Header(...),
):
    """Draft'ı reddet — Redis'ten sil."""
    _auth(x_api_key)
    redis = get_redis()
    await redis.delete(f"draft_data:{draft_id}")
    return {"status": "rejected", "draft_id": draft_id, "reason": body.reason}
