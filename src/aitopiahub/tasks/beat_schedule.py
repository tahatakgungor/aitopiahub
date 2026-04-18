"""Celery Beat schedule builder (single source of truth)."""

from __future__ import annotations

from celery.schedules import crontab

from aitopiahub.core.config import get_settings


def _parse_slots(raw: str) -> list[tuple[int, int]]:
    slots: list[tuple[int, int]] = []
    for token in (raw or "").split(","):
        item = token.strip()
        if not item:
            continue
        try:
            hh, mm = item.split(":", 1)
            h = int(hh)
            m = int(mm)
            if 0 <= h <= 23 and 0 <= m <= 59:
                slots.append((h, m))
        except Exception:
            continue
    if len(slots) < 2:
        return [(10, 0), (19, 0)]
    return slots[:2]


def build_beat_schedule() -> dict:
    settings = get_settings()
    account = settings.account_handle
    (h1, m1), (h2, m2) = _parse_slots(settings.kids_run_slots)

    return {
        "kids_slot_1_tr": {
            "task": "aitopiahub.tasks.content_tasks.run_kids_language_cycle",
            "schedule": crontab(hour=h1, minute=m1),
            "args": (account, "tr", settings.slot1_mode),
            "options": {"queue": "content"},
        },
        "kids_slot_2_en": {
            "task": "aitopiahub.tasks.content_tasks.run_kids_language_cycle",
            "schedule": crontab(hour=h2, minute=m2),
            "args": (account, "en", settings.slot2_mode),
            "options": {"queue": "content"},
        },
        "collect_metrics_kids": {
            "task": "aitopiahub.tasks.engagement_tasks.collect_metrics",
            "schedule": crontab(hour="*/2", minute="0"),
            "args": (account,),
            "options": {"queue": "engagement"},
        },
        "run_feedback_loop_kids": {
            "task": "aitopiahub.tasks.engagement_tasks.run_feedback_loop",
            "schedule": crontab(hour="*/6", minute="15"),
            "args": (account,),
            "options": {"queue": "engagement"},
        },
    }
