import json
from fastapi import APIRouter, Header, HTTPException
from aitopiahub.core.config import get_settings, AccountConfig
from aitopiahub.core.redis_client import get_redis

router = APIRouter()


def _auth(x_api_key: str):
    if x_api_key != get_settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Geçersiz API key")


@router.get("/analytics/{account_handle}")
async def get_analytics(account_handle: str, x_api_key: str = Header(...)):
    """Hesap için engagement özeti."""
    _auth(x_api_key)
    redis = get_redis()
    account_cfg = AccountConfig.for_account(account_handle)

    # Feedback stats
    stats_str = await redis.get(f"feedback_stats:{account_handle}")
    stats = json.loads(stats_str) if stats_str else {}

    # Son 10 metrik
    metric_keys = await redis.keys("metrics:*")
    metrics = []
    for key in metric_keys[:10]:
        m_str = await redis.get(key)
        if m_str:
            try:
                m = json.loads(m_str)
                if m.get("account") == account_handle:
                    metrics.append(m)
            except json.JSONDecodeError:
                pass

    published = await _load_published(redis, account_handle)
    metric_map = {str(m.get("media_id")): m for m in metrics if m.get("media_id")}
    clicks = await _total_hincr(redis, f"affiliate_clicks:{account_handle}")
    signup_events = await _total_hincr(redis, f"affiliate_signups:{account_handle}")
    revenue_estimate = round(signup_events * account_cfg.signup_value_estimate, 2)
    impressions = sum(int(m.get("impressions", 0)) for m in metrics)
    ctr = (clicks / impressions) if impressions > 0 else 0.0
    affiliate_posts = [p for p in published if p.get("is_affiliate")]
    non_affiliate_posts = [p for p in published if not p.get("is_affiliate")]
    cta_performance = _cta_performance(published, metric_map)
    hook_hashtag = _hook_hashtag_combo(published, metric_map)

    return {
        "account": account_handle,
        "summary": stats,
        "recent_posts": len(metrics),
        "ctr": round(ctr, 6),
        "affiliate_clicks": clicks,
        "signup_events": signup_events,
        "revenue_estimate": revenue_estimate,
        "post_type_performance": {
            "affiliate_count": len(affiliate_posts),
            "non_affiliate_count": len(non_affiliate_posts),
        },
        "cta_performance": cta_performance,
        "top_hook_hashtag_combos": hook_hashtag,
        "metrics": metrics,
    }


@router.get("/analytics/{account_handle}/trends")
async def get_trend_stats(account_handle: str, x_api_key: str = Header(...)):
    """Son trend tespiti istatistikleri."""
    _auth(x_api_key)
    redis = get_redis()
    seen = await redis.smembers(f"seen_trends:{account_handle}")
    return {
        "account": account_handle,
        "trends_seen_last_6h": len(seen),
    }


@router.get("/analytics/{account_handle}/revenue")
async def get_revenue(account_handle: str, x_api_key: str = Header(...)):
    _auth(x_api_key)
    redis = get_redis()
    account_cfg = AccountConfig.for_account(account_handle)

    clicks = await _total_hincr(redis, f"affiliate_clicks:{account_handle}")
    signup_events = await _total_hincr(redis, f"affiliate_signups:{account_handle}")
    revenue_estimate = round(signup_events * account_cfg.signup_value_estimate, 2)

    return {
        "account": account_handle,
        "affiliate_clicks": clicks,
        "signup_events": signup_events,
        "revenue_estimate": revenue_estimate,
        "signup_value_estimate": account_cfg.signup_value_estimate,
    }


@router.get("/analytics/{account_handle}/candidates")
async def get_content_candidates(account_handle: str, x_api_key: str = Header(...)):
    """Internal aday içerik listesi (mode etiketli)."""
    _auth(x_api_key)
    redis = get_redis()
    raw = await redis.get(f"content_candidates:{account_handle}")
    if not raw:
        return {"account": account_handle, "items": []}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"items": []}
    return {"account": account_handle, **payload}


async def _load_published(redis, account_handle: str) -> list[dict]:
    result = []
    keys = await redis.keys("published:*")
    for key in keys:
        payload = await redis.get(key)
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("account") == account_handle:
            result.append(data)
    return result


async def _total_hincr(redis, key: str) -> int:
    values = await redis.hvals(key)
    total = 0
    for value in values:
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total


def _cta_performance(published: list[dict], metric_map: dict[str, dict]) -> list[dict]:
    buckets: dict[str, list[float]] = {}
    for post in published:
        variant = post.get("cta_variant")
        media_id = str(post.get("media_id", ""))
        if not variant or media_id not in metric_map:
            continue
        score = float(metric_map[media_id].get("weighted_score", 0.0))
        buckets.setdefault(variant, []).append(score)
    result = []
    for variant, scores in buckets.items():
        result.append({"cta_variant": variant, "avg_score": sum(scores) / len(scores), "count": len(scores)})
    result.sort(key=lambda x: x["avg_score"], reverse=True)
    return result


def _hook_hashtag_combo(published: list[dict], metric_map: dict[str, dict], limit: int = 5) -> list[dict]:
    scored = []
    for post in published:
        media_id = str(post.get("media_id", ""))
        if media_id not in metric_map:
            continue
        hook = (post.get("hook_text") or "").strip()
        first_tag = (post.get("hashtags") or [None])[0]
        if not hook or not first_tag:
            continue
        score = float(metric_map[media_id].get("weighted_score", 0.0))
        scored.append(
            {
                "hook": hook[:80],
                "hashtag": first_tag,
                "score": score,
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
