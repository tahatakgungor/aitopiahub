from __future__ import annotations

from aitopiahub.core.config import get_settings
from aitopiahub.video_engine.cost_guard import CostGuard


def test_cost_guard_stays_free_when_strict(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_STRICT_FREE", "true")
    monkeypatch.setenv("ALLOW_PREMIUM_MODELS", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    get_settings.cache_clear()

    guard = CostGuard()
    decision = guard.evaluate_tts_budget(total_text_chars=2000)
    assert decision.premium_allowed is False
    assert decision.reason == "strict_free_policy"


def test_cost_guard_allows_premium_under_budget(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_STRICT_FREE", "false")
    monkeypatch.setenv("ALLOW_PREMIUM_MODELS", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    monkeypatch.setenv("ELEVENLABS_COST_PER_1K_CHARS", "0.3")
    monkeypatch.setenv("MAX_COST_PER_VIDEO_USD", "5.0")
    get_settings.cache_clear()

    guard = CostGuard()
    decision = guard.evaluate_tts_budget(total_text_chars=5000)
    assert decision.premium_allowed is True
    assert decision.estimated_cost_usd <= 5.0
