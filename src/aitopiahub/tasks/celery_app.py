"""
Celery uygulama fabrikası.
Pipeline'ın sinir sistemi — tüm async görevler buradan yönetilir.
"""

from celery import Celery
from aitopiahub.core.config import get_settings

settings = get_settings()

app = Celery(
    "aitopiahub",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,

    # Routing — her modül kendi kuyruğunda
    task_routes={
        "aitopiahub.tasks.trend_tasks.*": {"queue": "trend"},
        "aitopiahub.tasks.content_tasks.*": {"queue": "content"},
        "aitopiahub.tasks.publish_tasks.*": {"queue": "publish"},
        "aitopiahub.tasks.engagement_tasks.*": {"queue": "engagement"},
    },

    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,

    # Rate limiting (Instagram API koruması)
    task_annotations={
        "aitopiahub.tasks.publish_tasks.publish_post": {
            "rate_limit": "5/m",  # Max 5 publish/dakika
        },
    },

    # RedBeat scheduler config
    redbeat_redis_url=settings.redis_url,
    redbeat_lock_timeout=60 * 5,  # 5 dakika
)

# Task'ları auto-discover
app.autodiscover_tasks([
    "aitopiahub.tasks.trend_tasks",
    "aitopiahub.tasks.content_tasks",
    "aitopiahub.tasks.publish_tasks",
    "aitopiahub.tasks.engagement_tasks",
])
