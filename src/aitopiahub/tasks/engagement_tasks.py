"""Engagement collection + feedback learning loop tasks."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime

from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.publisher.instagram_client import InstagramClient
from aitopiahub.publisher.youtube_client import YouTubeClient
from aitopiahub.tasks.celery_app import app

log = get_logger(__name__)


@app.task(name="aitopiahub.tasks.engagement_tasks.collect_metrics")
def collect_metrics(account_handle: str) -> dict:
    return asyncio.run(_collect_metrics_async(account_handle))


async def _collect_metrics_async(account_handle: str) -> dict:
    redis = get_redis()
    instagram = InstagramClient()
    youtube = YouTubeClient(enabled=True)

    collected = 0

    # Legacy Instagram keys from publish_tasks
    for key in (await redis.keys("published:*"))[:50]:
        try:
            data = await _json_get(redis, key)
            if not data or data.get("account") != account_handle:
                continue
            media_id = str(data.get("media_id") or "")
            if not media_id:
                continue

            insights = await instagram.get_media_insights(media_id)
            parsed = _parse_instagram_insights(insights)
            if not parsed:
                continue

            payload = {
                "metric_id": media_id,
                "platform": "instagram",
                "account": account_handle,
                "format": data.get("format", "unknown"),
                "content_mode": data.get("content_mode", "demand_driven"),
                "story_id": data.get("story_id"),
                **parsed,
                "weighted_score": _weighted_score(
                    likes=parsed["likes"],
                    comments=parsed["comments"],
                    saves=parsed["saves"],
                    shares=parsed["shares"],
                    impressions=parsed["impressions"],
                ),
            }
            await redis.setex(f"metrics:instagram:{media_id}", 30 * 86400, json.dumps(payload))
            collected += 1
        except Exception as exc:
            log.warning("metrics_collect_error", key=key, error=str(exc))

    # New Instagram episode records
    for key in (await redis.keys("published_instagram:*") )[:50]:
        try:
            data = await _json_get(redis, key)
            if not data or data.get("account") != account_handle:
                continue
            media_id = str(data.get("media_id") or "")
            if not media_id:
                continue

            insights = await instagram.get_media_insights(media_id)
            parsed = _parse_instagram_insights(insights)
            if not parsed:
                continue

            payload = {
                "metric_id": media_id,
                "platform": "instagram",
                "account": account_handle,
                "format": "reel",
                "content_mode": data.get("content_mode", "demand_driven"),
                "story_id": data.get("story_id"),
                **parsed,
                "weighted_score": _weighted_score(
                    likes=parsed["likes"],
                    comments=parsed["comments"],
                    saves=parsed["saves"],
                    shares=parsed["shares"],
                    impressions=parsed["impressions"],
                ),
            }
            await redis.setex(f"metrics:instagram:{media_id}", 30 * 86400, json.dumps(payload))
            collected += 1
        except Exception as exc:
            log.warning("metrics_collect_error", key=key, error=str(exc))

    # YouTube records (long form)
    for key in (await redis.keys("published_youtube:*"))[:50]:
        try:
            data = await _json_get(redis, key)
            if not data or data.get("account") != account_handle:
                continue
            video_id = str(data.get("video_id") or "")
            if not video_id:
                continue

            insights = await youtube.get_video_insights(video_id)
            if not insights:
                continue

            views = int(insights.get("views", 0))
            likes = int(insights.get("likes", 0))
            comments = int(insights.get("comments", 0))
            duration = str(insights.get("duration") or "")

            ctr_proxy = (likes + comments) / views if views > 0 else 0.0
            retention_proxy = min(max((likes * 1.4 + comments * 2.0) / max(views, 1), 0.0), 1.0)

            payload = {
                "metric_id": video_id,
                "platform": "youtube",
                "account": account_handle,
                "format": "long_episode",
                "content_mode": data.get("content_mode", "demand_driven"),
                "story_id": data.get("story_id"),
                "views": views,
                "likes": likes,
                "comments": comments,
                "duration": duration,
                "ctr_proxy": ctr_proxy,
                "retention_proxy": retention_proxy,
                "completion_proxy": retention_proxy,
                "weighted_score": (likes + comments * 2.0) / max(views, 1),
            }
            await redis.setex(f"metrics:youtube:{video_id}", 30 * 86400, json.dumps(payload))
            collected += 1
        except Exception as exc:
            log.warning("youtube_metrics_collect_error", key=key, error=str(exc))

    log.info("metrics_collected", account=account_handle, count=collected)
    return {"collected": collected}


@app.task(name="aitopiahub.tasks.engagement_tasks.run_feedback_loop")
def run_feedback_loop(account_handle: str) -> dict:
    return asyncio.run(_feedback_loop_async(account_handle))


async def _feedback_loop_async(account_handle: str) -> dict:
    redis = get_redis()

    metric_keys = await redis.keys("metrics:*")
    metrics_list = []

    for key in metric_keys:
        data_str = await redis.get(key)
        if not data_str:
            continue
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if data.get("account") == account_handle:
            metrics_list.append(data)

    if len(metrics_list) < 3:
        log.info("feedback_loop_insufficient_data", account=account_handle)
        return {"updated": False}

    format_stats: dict[str, list[float]] = {}
    platform_stats: dict[str, list[float]] = defaultdict(list)
    mode_stats: dict[str, list[float]] = defaultdict(list)
    post_type_stats: dict[str, list[float]] = {"affiliate": [], "organic": []}
    hashtag_scores: dict[str, list[float]] = defaultdict(list)
    hook_scores: dict[str, list[float]] = defaultdict(list)
    hour_scores: dict[int, list[float]] = defaultdict(list)
    topic_scores: dict[str, list[float]] = defaultdict(list)
    scene_scores: dict[int, list[float]] = defaultdict(list)
    story_scores: dict[str, list[float]] = defaultdict(list)

    published_map = await _load_published_meta(redis, account_handle)

    for m in metrics_list:
        fmt = m.get("format", "unknown")
        er = float(m.get("weighted_score", m.get("engagement_rate", 0.0)) or 0.0)
        format_stats.setdefault(fmt, []).append(er)
        platform_stats[str(m.get("platform", "unknown"))].append(er)
        mode_stats[str(m.get("content_mode", "demand_driven"))].append(er)

        metric_id = str(m.get("metric_id") or m.get("media_id") or m.get("video_id") or "")
        meta = published_map.get(metric_id)
        if not meta:
            continue

        if meta.get("is_affiliate"):
            post_type_stats["affiliate"].append(er)
        else:
            post_type_stats["organic"].append(er)

        for tag in (meta.get("hashtags") or []):
            if isinstance(tag, str) and tag.strip():
                hashtag_scores[tag.strip().lstrip("#")].append(er)

        hook = (meta.get("hook_text") or meta.get("title") or "").strip()
        if hook:
            hook_scores[hook[:140]].append(er)

        keyword = (meta.get("keyword") or "").strip()
        if keyword:
            topic_scores[keyword].append(er)
        story_id = (meta.get("story_id") or "").strip() if isinstance(meta.get("story_id"), str) else meta.get("story_id")
        if story_id:
            story_scores[str(story_id)].append(er)

        scene_count = meta.get("scene_count")
        try:
            if scene_count is not None:
                scene_scores[int(scene_count)].append(er)
        except Exception:
            pass

        published_at = meta.get("published_at") or meta.get("scheduled_for")
        try:
            dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            hour_scores[dt.hour].append(er)
        except Exception:
            pass

    await redis.setex(
        f"feedback_stats:{account_handle}",
        7 * 86400,
        json.dumps(
            {
                "format_stats": {k: sum(v) / len(v) for k, v in format_stats.items() if v},
                "platform_stats": {k: sum(v) / len(v) for k, v in platform_stats.items() if v},
                "mode_stats": {k: sum(v) / len(v) for k, v in mode_stats.items() if v},
                "post_type_performance": {
                    k: (sum(v) / len(v) if v else 0.0) for k, v in post_type_stats.items()
                },
                "total_posts": len(metrics_list),
            }
        ),
    )

    await _persist_hashtag_weights(redis, account_handle, hashtag_scores)
    await _persist_hook_bank(redis, account_handle, hook_scores)
    await _persist_hour_weights(redis, account_handle, hour_scores)
    await _persist_topic_weights(redis, account_handle, topic_scores)
    await _persist_mode_weights(redis, account_handle, mode_stats)
    await _persist_story_weights(redis, account_handle, story_scores)
    await _persist_scene_targets(redis, account_handle, scene_scores)

    log.info("feedback_loop_done", account=account_handle, posts=len(metrics_list))
    return {"updated": True, "posts_analyzed": len(metrics_list)}


def _parse_instagram_insights(insights: dict) -> dict | None:
    if not insights or "data" not in insights:
        return None

    metrics = {}
    for item in insights["data"]:
        name = item.get("name")
        values = item.get("values") or []
        value = values[-1]["value"] if values else 0
        metrics[name] = value

    impressions = int(metrics.get("impressions", 0) or 0)
    likes = int(metrics.get("likes", 0) or 0)
    comments = int(metrics.get("comments", 0) or 0)
    saves = int(metrics.get("saved", 0) or 0)
    shares = int(metrics.get("shares", 0) or 0)
    reach = int(metrics.get("reach", 0) or 0)

    engagement_rate = ((likes + comments + saves + shares) / impressions) if impressions > 0 else 0.0
    ctr_proxy = (shares + saves) / impressions if impressions > 0 else 0.0

    return {
        "impressions": impressions,
        "reach": reach,
        "likes": likes,
        "comments": comments,
        "saves": saves,
        "shares": shares,
        "engagement_rate": engagement_rate,
        "ctr_proxy": ctr_proxy,
        "retention_proxy": min((saves + shares * 1.2) / max(impressions, 1), 1.0),
        "completion_proxy": min((saves + shares * 1.2) / max(impressions, 1), 1.0),
    }


def _weighted_score(likes: int, comments: int, saves: int, shares: int, impressions: int) -> float:
    if impressions <= 0:
        return 0.0
    weighted = likes + (comments * 1.8) + (saves * 2.8) + (shares * 3.0)
    return weighted / impressions


async def _json_get(redis, key: str) -> dict | None:
    raw = await redis.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _load_published_meta(redis, account_handle: str) -> dict[str, dict]:
    result: dict[str, dict] = {}

    for pattern, id_field in [
        ("published:*", "media_id"),
        ("published_instagram:*", "media_id"),
        ("published_youtube:*", "video_id"),
    ]:
        keys = await redis.keys(pattern)
        for key in keys:
            data = await _json_get(redis, key)
            if not data or data.get("account") != account_handle:
                continue
            media_id = data.get(id_field)
            if media_id:
                result[str(media_id)] = data

    return result


async def _persist_hashtag_weights(redis, account_handle: str, hashtag_scores: dict[str, list[float]]) -> None:
    key = f"feedback:hashtag_weights:{account_handle}"
    payload: dict[str, float] = {}
    for tag, scores in hashtag_scores.items():
        if len(scores) < 2:
            continue
        payload[tag] = min(sum(scores) / len(scores) * 12.0, 2.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)


async def _persist_hook_bank(redis, account_handle: str, hook_scores: dict[str, list[float]]) -> None:
    key = f"feedback:hook_bank:{account_handle}"
    if not hook_scores:
        return
    pipe = redis.pipeline()
    for hook, scores in hook_scores.items():
        if len(scores) < 2:
            continue
        pipe.zadd(key, {hook: sum(scores) / len(scores)})
    pipe.expire(key, 30 * 86400)
    await pipe.execute()


async def _persist_hour_weights(redis, account_handle: str, hour_scores: dict[int, list[float]]) -> None:
    key = f"feedback:hour_weights:{account_handle}"
    payload = {}
    for hour, scores in hour_scores.items():
        if len(scores) < 2:
            continue
        payload[str(hour)] = min(max(sum(scores) / len(scores) * 10, 0.5), 5.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)


async def _persist_topic_weights(redis, account_handle: str, topic_scores: dict[str, list[float]]) -> None:
    key = f"feedback:topic_weights:{account_handle}"
    payload: dict[str, float] = {}
    for topic, scores in topic_scores.items():
        if len(scores) < 2:
            continue
        payload[topic] = min(max(sum(scores) / len(scores) * 8.0, 0.2), 5.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)


async def _persist_mode_weights(redis, account_handle: str, mode_scores: dict[str, list[float]]) -> None:
    key = f"feedback:mode_weights:{account_handle}"
    payload: dict[str, float] = {}
    for mode, scores in mode_scores.items():
        if len(scores) < 2:
            continue
        payload[mode] = min(max(sum(scores) / len(scores) * 10.0, 0.2), 5.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)


async def _persist_story_weights(redis, account_handle: str, story_scores: dict[str, list[float]]) -> None:
    key = f"feedback:story_weights:{account_handle}"
    payload: dict[str, float] = {}
    for story_id, scores in story_scores.items():
        if len(scores) < 2:
            continue
        payload[story_id] = min(max(sum(scores) / len(scores) * 10.0, 0.2), 5.0)
    if payload:
        await redis.hset(key, mapping=payload)
        await redis.expire(key, 30 * 86400)


async def _persist_scene_targets(redis, account_handle: str, scene_scores: dict[int, list[float]]) -> None:
    key = f"feedback:scene_targets:{account_handle}"
    if not scene_scores:
        return

    best_scene = None
    best_score = -1.0
    for scene_count, scores in scene_scores.items():
        if len(scores) < 2:
            continue
        avg = sum(scores) / len(scores)
        if avg > best_score:
            best_score = avg
            best_scene = scene_count

    if best_scene is not None:
        await redis.hset(
            key,
            mapping={
                "target_scene_count": best_scene,
                "updated_at": datetime.utcnow().isoformat(),
                "score": round(best_score, 6),
            },
        )
        await redis.expire(key, 30 * 86400)
