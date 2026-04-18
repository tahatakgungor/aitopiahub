from __future__ import annotations

from aitopiahub.core.config import get_settings
from aitopiahub.tasks.beat_schedule import build_beat_schedule


def test_build_beat_schedule_uses_two_slots_and_languages(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_HANDLE", "aitopiahub_kids")
    monkeypatch.setenv("KIDS_RUN_SLOTS", "10:00,19:00")
    monkeypatch.setenv("SLOT1_MODE", "fairy_tale")
    monkeypatch.setenv("SLOT2_MODE", "demand_driven")
    get_settings.cache_clear()

    schedule = build_beat_schedule()

    assert "kids_slot_1_tr" in schedule
    assert "kids_slot_2_en" in schedule
    assert schedule["kids_slot_1_tr"]["args"] == ("aitopiahub_kids", "tr", "fairy_tale")
    assert schedule["kids_slot_2_en"]["args"] == ("aitopiahub_kids", "en", "demand_driven")
