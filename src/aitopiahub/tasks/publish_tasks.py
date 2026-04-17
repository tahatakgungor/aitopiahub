"""
Yayınlama Celery task'ları.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aitopiahub.tasks.celery_app import app
from aitopiahub.core.config import AccountConfig, get_settings
from aitopiahub.core.constants import PostFormat
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis, RateLimiter
from aitopiahub.publisher.instagram_client import InstagramClient
from aitopiahub.publisher.scheduler import OptimalScheduler
from aitopiahub.publisher.queue_manager import QueueManager, QueueItem

log = get_logger(__name__)

# Instagram publish rate limit: max 5 post/15 dk
INSTAGRAM_RATE_CAPACITY = 5
INSTAGRAM_RATE_PER_MINUTE = 5 / 15  # token/dakika


@app.task(
    name="aitopiahub.tasks.publish_tasks.check_and_publish",
    bind=True,
    max_retries=1,
)
def check_and_publish(self, account_handle: str) -> dict:
    """Zamanı gelmiş post'ları yayınla."""
    return asyncio.run(_check_and_publish_async(account_handle))


async def _check_and_publish_async(account_handle: str) -> dict:
    config = AccountConfig.for_account(account_handle)
    redis = get_redis()
    instagram = InstagramClient()
    queue_mgr = QueueManager(redis)
    scheduler = OptimalScheduler(config)

    # Rate limiter
    rate_key = f"rate:instagram:publish:{account_handle}"
    rate_limiter = RateLimiter(
        redis,
        rate_key,
        INSTAGRAM_RATE_CAPACITY,
        INSTAGRAM_RATE_PER_MINUTE,
    )

    # 1. ready_drafts'tan yeni draft'ları al ve queue'ya ekle
    await _enqueue_ready_drafts(account_handle, redis, queue_mgr, scheduler)

    # 2. Zamanı gelmiş post'ları yayınla
    due_items = await queue_mgr.dequeue_due(account_handle)
    published = 0
    failed = 0

    for item in due_items:
        if not await rate_limiter.acquire():
            log.warning("rate_limit_hit", account=account_handle)
            # Geri koy — sonra tekrar dene
            await queue_mgr.enqueue(item)
            break

        try:
            await _publish_item(item, redis, instagram, account_handle)
            published += 1
        except Exception as e:
            log.error("publish_failed", draft_id=item.draft_id, error=str(e))
            failed += 1

    log.info(
        "publish_cycle_done",
        account=account_handle,
        published=published,
        failed=failed,
    )
    return {"published": published, "failed": failed}


async def _enqueue_ready_drafts(
    account_handle: str,
    redis,
    queue_mgr: QueueManager,
    scheduler: OptimalScheduler,
) -> None:
    """Redis'teki hazır draft'ları posting queue'ya ekle."""
    if not await _can_schedule_more_today(redis, queue_mgr, account_handle, scheduler.config):
        log.info("daily_post_cap_reached", account=account_handle)
        return

    hour_weights = await redis.hgetall(f"feedback:hour_weights:{account_handle}")
    for hour_str, weight_str in hour_weights.items():
        try:
            scheduler.update_hour_weight(int(hour_str), float(weight_str) / 5.0)
        except (TypeError, ValueError):
            continue

    while True:
        item_str = await redis.lpop(f"ready_drafts:{account_handle}")
        if not item_str:
            break
        try:
            data = json.loads(item_str)
            occupied = await queue_mgr.scheduled_times(account_handle)
            slot = scheduler.next_slot(
                occupied_times=occupied,
                trend_score=data.get("trend_score", 0.5),
            )
            await queue_mgr.enqueue(
                QueueItem(
                    draft_id=data["draft_id"],
                    account_id=account_handle,
                    post_format=data["post_format"],
                    scheduled_for=slot,
                    trend_score=data.get("trend_score", 0.5),
                )
            )
            # Draft verilerini Redis'te sakla (publish sırasında okunacak)
            await redis.setex(
                f"draft_data:{data['draft_id']}",
                86400,
                item_str,
            )
            if not await _can_schedule_more_today(redis, queue_mgr, account_handle, scheduler.config):
                log.info("daily_post_cap_reached_after_enqueue", account=account_handle)
                break
        except Exception as e:
            log.warning("enqueue_error", error=str(e))


async def _publish_item(
    item: QueueItem,
    redis,
    instagram: InstagramClient,
    account_handle: str,
) -> None:
    """Tek bir post'u Instagram'a yayınla."""
    # Draft verilerini al
    draft_str = await redis.get(f"draft_data:{item.draft_id}")
    if not draft_str:
        log.warning("draft_data_not_found", draft_id=item.draft_id)
        return

    data = json.loads(draft_str)
    caption = data["caption"]
    hashtags = data.get("hashtags", [])[:20]
    image_urls = _normalize_image_urls(data.get("image_urls", []))

    # Hashtag'leri caption'a ekle
    if hashtags:
        hashtag_str = " ".join(f"#{h}" for h in hashtags)
        full_caption = f"{caption}\n\n{hashtag_str}"
    else:
        full_caption = caption

    # Yayınla
    if item.post_format == PostFormat.CAROUSEL and len(image_urls) > 1:
        result = await instagram.publish_carousel(image_urls, full_caption)
    else:
        url = image_urls[0] if image_urls else None
        if not url:
            log.warning("no_image_url", draft_id=item.draft_id)
            return
        result = await instagram.publish_single(url, full_caption)

    # Başarı → draft verisini temizle, sonucu kaydet
    await redis.delete(f"draft_data:{item.draft_id}")
    await redis.setex(
        f"published:{item.draft_id}",
        7 * 86400,
        json.dumps({
            "media_id": result.media_id,
            "account": account_handle,
            "format": item.post_format,
            "scheduled_for": item.scheduled_for.isoformat(),
            "published_at": datetime.now(timezone.utc).isoformat(),
            "keyword": data.get("keyword"),
            "variant_label": data.get("variant_label"),
            "angle": data.get("angle"),
            "quality_score": data.get("quality_score"),
            "trend_score": data.get("trend_score"),
            "hashtags": hashtags,
            "hook_text": data.get("hook_text"),
            "offer_id": data.get("offer_id"),
            "tracking_url": data.get("tracking_url"),
            "cta_variant": data.get("cta_variant"),
            "commercial_intent_score": data.get("commercial_intent_score", 0.0),
            "is_affiliate": bool(data.get("is_affiliate", False)),
        }),
    )

    log.info(
        "published_success",
        draft_id=item.draft_id,
        media_id=result.media_id,
        format=item.post_format,
    )


def _normalize_image_urls(image_urls: list[str]) -> list[str]:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    normalized = []
    for url in image_urls:
        if not url:
            continue
        if url.startswith("http://") or url.startswith("https://"):
            normalized.append(url)
        elif url.startswith("/"):
            normalized.append(f"{base}{url}")
        else:
            normalized.append(f"{base}/{url.lstrip('/')}")
    return normalized


async def _can_schedule_more_today(redis, queue_mgr: QueueManager, account_handle: str, config) -> bool:
    """
    Hızlı büyüme için kontrollü hacim:
    - Hesabın ilk 48 saatinde max 4 post/gün
    - Sonrasında config.posts_per_day
    """
    now_utc = datetime.now(timezone.utc)
    launch_key = f"account_launch_at:{account_handle}"
    launch_value = await redis.get(launch_key)
    if not launch_value:
        await redis.set(launch_key, now_utc.isoformat())
        launch_dt = now_utc
    else:
        try:
            launch_dt = datetime.fromisoformat(str(launch_value).replace("Z", "+00:00"))
            if launch_dt.tzinfo is None:
                launch_dt = launch_dt.replace(tzinfo=timezone.utc)
        except Exception:
            launch_dt = now_utc

    in_bootstrap = (now_utc - launch_dt) < timedelta(hours=config.bootstrap_hours)
    daily_cap = config.bootstrap_posts_per_day if in_bootstrap else config.posts_per_day

    tz = ZoneInfo(config.timezone)
    today_local = now_utc.astimezone(tz).date()

    queued_today = 0
    for scheduled in await queue_mgr.scheduled_times(account_handle):
        local_dt = scheduled.astimezone(tz)
        if local_dt.date() == today_local:
            queued_today += 1

    published_today = 0
    for key in await redis.keys("published:*"):
        payload = await redis.get(key)
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("account") != account_handle:
            continue
        published_at = data.get("published_at")
        if not published_at:
            continue
        try:
            dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(tz).date() == today_local:
                published_today += 1
        except Exception:
            continue

    return (queued_today + published_today) < daily_cap
