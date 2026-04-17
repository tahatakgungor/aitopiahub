"""
Celery Beat periyodik görev takvimi.
"""

from celery.schedules import crontab
from aitopiahub.tasks.celery_app import app

# Aktif hesaplar — yeni hesap eklenince buraya da ekle
ACTIVE_ACCOUNTS = ["aitopiahub_news"]

app.conf.beat_schedule = {
    # === TREND TESPİTİ (her 15 dk) ===
    **{
        f"fetch_trends_{account}": {
            "task": "aitopiahub.tasks.trend_tasks.fetch_and_score_trends",
            "schedule": crontab(minute="*/15"),
            "args": (account,),
            "options": {"queue": "trend"},
        }
        for account in ACTIVE_ACCOUNTS
    },

    # === İÇERİK ÜRETİMİ (her 30 dk) ===
    **{
        f"generate_content_{account}": {
            "task": "aitopiahub.tasks.content_tasks.generate_pending_content",
            "schedule": crontab(minute="*/30"),
            "args": (account,),
            "options": {"queue": "content"},
        }
        for account in ACTIVE_ACCOUNTS
    },

    # === YAYIN KONTROLü (her 5 dk) ===
    **{
        f"check_queue_{account}": {
            "task": "aitopiahub.tasks.publish_tasks.check_and_publish",
            "schedule": crontab(minute="*/5"),
            "args": (account,),
            "options": {"queue": "publish"},
        }
        for account in ACTIVE_ACCOUNTS
    },

    # === ENGAGEMENT TOPLAMA (her 2 saat) ===
    **{
        f"collect_metrics_{account}": {
            "task": "aitopiahub.tasks.engagement_tasks.collect_metrics",
            "schedule": crontab(hour="*/2", minute="0"),
            "args": (account,),
            "options": {"queue": "engagement"},
        }
        for account in ACTIVE_ACCOUNTS
    },

    # === ÖĞRENME DÖNGüSü (her 6 saat) ===
    **{
        f"run_feedback_loop_{account}": {
            "task": "aitopiahub.tasks.engagement_tasks.run_feedback_loop",
            "schedule": crontab(hour="*/6", minute="15"),
            "args": (account,),
            "options": {"queue": "engagement"},
        }
        for account in ACTIVE_ACCOUNTS
    },
}
