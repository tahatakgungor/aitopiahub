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

# Beat Schedule Konfigürasyonu
app.conf.beat_schedule = {
    "autonomous_kids_hub_cycle": {
        "task": "aitopiahub.tasks.content_tasks.run_autonomous_kids_cycle",
        "schedule": 86400.0, # Günde bir kez (veya crontab ile 10:00)
        "args": ("aitopiahub_kids",),
    },
    "trend_hunt_scout": {
        "task": "aitopiahub.tasks.trend_tasks.fetch_and_score_trends",
        "schedule": 14400.0, # Her 4 saatte bir
        "args": ("aitopiahub_kids",),
    },
    "self_improvement_feedback": {
        "task": "aitopiahub.tasks.content_tasks.run_self_improvement",
        "schedule": 604800.0, # Haftada bir
        "args": ("aitopiahub_kids",),
    },
}

# Task'ları auto-discover
app.autodiscover_tasks([
    "aitopiahub.tasks.trend_tasks",
    "aitopiahub.tasks.content_tasks",
    "aitopiahub.tasks.publish_tasks",
    "aitopiahub.tasks.engagement_tasks",
])
