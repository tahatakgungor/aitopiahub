from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse

from aitopiahub.core.config import get_settings, AccountConfig
from aitopiahub.core.redis_client import get_redis
from aitopiahub.monetization import AffiliateCatalog, OfferRanker, LinkTracker

router = APIRouter()


class OfferSelectBody(BaseModel):
    keyword: str = Field(..., min_length=2)
    caption_preview: str = ""
    limit: int = 3


class SignupEventBody(BaseModel):
    offer_id: str
    count: int = 1


def _auth(x_api_key: str):
    if x_api_key != get_settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Geçersiz API key")


@router.get("/monetization/{account_handle}/summary")
async def monetization_summary(account_handle: str, x_api_key: str = Header(...)):
    _auth(x_api_key)
    redis = get_redis()
    cfg = AccountConfig.for_account(account_handle)

    clicks = await _total_hincr(redis, f"affiliate_clicks:{account_handle}")
    signups = await _total_hincr(redis, f"affiliate_signups:{account_handle}")
    revenue_estimate = round(signups * cfg.signup_value_estimate, 2)

    top_offers = []
    for offer_id, value in (await redis.hgetall(f"offer_clicks:{account_handle}")).items():
        try:
            top_offers.append({"offer_id": offer_id, "clicks": int(value)})
        except (TypeError, ValueError):
            continue
    top_offers.sort(key=lambda x: x["clicks"], reverse=True)

    return {
        "account": account_handle,
        "enabled": cfg.monetization_enabled,
        "affiliate_ratio_max": cfg.affiliate_ratio_max,
        "affiliate_clicks": clicks,
        "signup_events": signups,
        "revenue_estimate": revenue_estimate,
        "top_offers": top_offers[:5],
    }


@router.post("/monetization/{account_handle}/offers/select")
async def select_offers(account_handle: str, body: OfferSelectBody, x_api_key: str = Header(...)):
    _auth(x_api_key)
    redis = get_redis()
    cfg = AccountConfig.for_account(account_handle)

    ranker = OfferRanker()
    catalog = AffiliateCatalog()
    tracker = LinkTracker(redis, account_handle, cfg.default_utm_campaign)

    ranked = ranker.rank(catalog.list_offers(), keyword=body.keyword, caption=body.caption_preview, limit=body.limit)
    result = []
    for item in ranked:
        code, url = await tracker.build_tracking_url(
            offer_id=item.offer.offer_id,
            base_url=item.offer.base_url,
            keyword=body.keyword,
            draft_id=f"preview-{body.keyword[:12]}",
        )
        result.append(
            {
                "offer_id": item.offer.offer_id,
                "offer_name": item.offer.name,
                "provider": item.offer.provider,
                "commission_type": item.offer.commission_type,
                "commercial_intent_score": item.commercial_intent_score,
                "tracking_code": code,
                "tracking_url": url,
            }
        )

    return {"account": account_handle, "offers": result}


@router.post("/monetization/offers/select")
async def select_offers_legacy(
    account_handle: str,
    body: OfferSelectBody,
    x_api_key: str = Header(...),
):
    return await select_offers(account_handle=account_handle, body=body, x_api_key=x_api_key)


@router.get("/monetization/{account_handle}/track/{code}")
async def track_click(account_handle: str, code: str):
    """Tracking link redirect endpoint (public)."""
    redis = get_redis()
    tracker = LinkTracker(redis, account_handle, campaign="ignored")
    target = await tracker.resolve(code)
    if not target:
        raise HTTPException(status_code=404, detail="Tracking link bulunamadı")

    await tracker.register_click(code)
    meta = await redis.hget(f"link_meta:{account_handle}", code)
    if meta:
        offer_id = str(meta).split("|")[0]
        await redis.hincrby(f"offer_clicks:{account_handle}", offer_id, 1)

    return RedirectResponse(url=target, status_code=307)


@router.post("/monetization/{account_handle}/events/signup")
async def register_signup(
    account_handle: str,
    body: SignupEventBody,
    x_api_key: str = Header(...),
):
    _auth(x_api_key)
    redis = get_redis()
    await redis.hincrby(f"affiliate_signups:{account_handle}", body.offer_id, max(body.count, 1))
    return {"account": account_handle, "status": "ok"}


async def _total_hincr(redis, key: str) -> int:
    values = await redis.hvals(key)
    total = 0
    for value in values:
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total
