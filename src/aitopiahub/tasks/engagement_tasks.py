"""
Engagement toplama ve öğrenme döngüsü task'ları.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime

from aitopiahub.tasks.celery_app import app
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.publisher.instagram_client import InstagramClient

log = get_logger(__name__)


@app.task(name="aitopiahub.tasks.engagement_tasks.collect_metrics")
def collect_metrics(account_handle: str) -> dict:
    return asyncio.run(_collect_metrics_async(account_handle))


async def _collect_metrics_async(account_handle: str) -> dict:
    redis = get_redis()
    instagram = InstagramClient()

    # Son 7 günlük yayınlanan post'ları al
    published_keys = await redis.keys(f"published:*")
    collected = 0

    for key in published_keys[:50]:  # Max 50 post/döngü
        try:
            data_str = await redis.get(key)
            if not data_str:
                continue
            data = json.loads(data_str)
            if data.get("account") != account_handle:
                continue

            media_id = data["media_id"]
            insights = await instagram.get_media_insights(media_id)

            if insights and "data" in insights:
                metrics = {}
                for item in insights["data"]:
                    metrics[item["name"]] = item["values"][-1]["value"] if item.get("values") else 0

                impressions = metrics.get("impressions", 0)
                likes = metrics.get("likes", 0)
                comments = metrics.get("comments", 0)
                saves = metrics.get("saved", 0)
                shares = metrics.get("shares", 0)
                reach = metrics.get("reach", 0)

                engagement_rate = (
                    (likes + comments + saves + shares) / impressions
                    if impressions > 0
                    else 0
                )

                await redis.setex(
                    f"metrics:{media_id}",
                    30 * 86400,
                    json.dumps({
                        "media_id": media_id,
                        "account": account_handle,
                        "format": data.get("format"),
                        "impressions": impressions,
                        "reach": reach,
                        "likes": likes,
                        "comments": comments,
                        "saves": saves,
                        "shares": shares,
                        "engagement_rate": engagement_rate,
                        "weighted_score": _weighted_score(
                            likes=likes,
                            comments=comments,
                            saves=saves,
                            shares=shares,
                            impressions=impressions,
                        ),
                    }),
                )
                collected += 1
        except Exception as e:
            log.warning("metrics_collect_error", key=key, error=str(e))

    log.info("metrics_collected", account=account_handle, count=collected)
    return {"collected": collected}


@app.task(name="aitopiahub.tasks.engagement_tasks.run_feedback_loop")
def run_feedback_loop(account_handle: str) -> dict:
    return asyncio.run(_feedback_loop_async(account_handle))


async def _feedback_loop_async(account_handle: str) -> dict:
    redis = get_redis()

    # Tüm metrikleri topla ve analiz et
    metric_keys = await redis.keys("metrics:*")
    metrics_list = []

    for key in metric_keys:
        data_str = await redis.get(key)
        if data_str:
            try:
                data = json.loads(data_str)
                if data.get("account") == account_handle:
                    metrics_list.append(data)
            except json.JSONDecodeError:
                pass

    if len(metrics_list) < 3:
        log.info("feedback_loop_insufficient_data", account=account_handle)
        return {"updated": False}

    # Format analizi
    format_stats: dict[str, list[float]] = {}
    post_type_stats: dict[str, list[float]] = {"affiliate": [], "organic": []}
    hashtag_scores: dict[str, list[float]] = defaultdict(list)
    hook_scores: dict[str, list[float]] = defaultdict(list)
    hour_scores: dict[int, list[float]] = defaultdict(list)

    published_map = await _load_published_meta(redis, account_handle)

    for m in metrics_list:
        fmt = m.get("format", "unknown")
        er = m.get("weighted_score", m.get("engagement_rate", 0))
        if fmt not in format_stats:
            format_stats[fmt] = []
        format_stats[fmt].append(er)

        meta = published_map.get(m.get("media_id", ""))
        if not meta:
            continue
        if meta.get("is_affiliate"):
            post_type_stats["affiliate"].append(er)
        else:
            post_type_stats["organic"].append(er)

        hashtags = meta.get("hashtags", []) or []
        for tag in hashtags:
            if isinstance(tag, str) and tag.strip():
                hashtag_scores[tag.strip().lstrip("#")].append(er)

        hook = (meta.get("hook_text") or "").strip()
        if hook:
            hook_scores[hook[:140]].append(er)

        published_at = meta.get("published_at") or meta.get("scheduled_for")
        try:
            dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            hour_scores[dt.hour].append(er)
        except Exception:
            pass

    for fmt, rates in format_stats.items():
        avg = sum(rates) / len(rates)
        log.info("format_performance", account=account_handle, format=fmt, avg_er=round(avg, 4))

    # En iyi saati bul
    # (Gerçekte post zamanı da kaydedilmeli — burada placeholder)

    # Sonuçları Redis'e kaydet
    await redis.setex(
        f"feedback_stats:{account_handle}",
        7 * 86400,
        json.dumps({
            "format_stats": {k: sum(v)/len(v) for k, v in format_stats.items()},
            "post_type_performance": {
                k: (sum(v) / len(v) if v else 0.0)
                for k, v in post_type_stats.items()
            },
            "total_posts": len(metrics_list),
        }),
    )

    await _persist_hashtag_weights(redis, account_handle, hashtag_scores)
    await _persist_hook_bank(redis, account_handle, hook_scores)
    await _persist_hour_weights(redis, account_handle, hour_scores)

    log.info("feedback_loop_done", account=account_handle, posts=len(metrics_list))
    return {"updated": True, "posts_analyzed": len(metrics_list)}


def _weighted_score(
    likes: int,
    comments: int,
    saves: int,
    shares: int,
    impressions: int,
) -> float:
    """
    Save/share odaklı skorlama:
    hızlı büyüme için saves ve shares'e daha yüksek ağırlık ver.
    """
    if impressions <= 0:
        return 0.0
    weighted = likes + (comments * 1.8) + (saves * 2.8) + (shares * 3.0)
    return weighted / impressions


async def _load_published_meta(redis, account_handle: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    keys = await redis.keys("published:*")
    for key in keys:
        data_str = await redis.get(key)
        if not data_str:
            continue
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if data.get("account") != account_handle:
            continue
        media_id = data.get("media_id")
        if media_id:
            result[str(media_id)] = data
    return result


async def _persist_hashtag_weights(
    redis,
    account_handle: str,
    hashtag_scores: dict[str, list[float]],
) -> None:
    key = f"feedback:hashtag_weights:{account_handle}"
    if not hashtag_scores:
        return
    payload: dict[str, float] = {}
    for tag, scores in hashtag_scores.items():
        if len(scores) < 2:
            continue
        payload[tag] = min(sum(scores) / len(scores) * 12.0, 2.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)


async def _persist_hook_bank(
    redis,
    account_handle: str,
    hook_scores: dict[str, list[float]],
) -> None:
    key = f"feedback:hook_bank:{account_handle}"
    if not hook_scores:
        return
    pipe = redis.pipeline()
    for hook, scores in hook_scores.items():
        if len(scores) < 2:
            continue
        score = sum(scores) / len(scores)
        pipe.zadd(key, {hook: score})
    pipe.expire(key, 30 * 86400)
    await pipe.execute()


async def _persist_hour_weights(
    redis,
    account_handle: str,
    hour_scores: dict[int, list[float]],
) -> None:
    key = f"feedback:hour_weights:{account_handle}"
    if not hour_scores:
        return
    payload = {}
    for hour, scores in hour_scores.items():
        if len(scores) < 2:
            continue
        payload[str(hour)] = min(max(sum(scores) / len(scores) * 10, 0.5), 5.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)
