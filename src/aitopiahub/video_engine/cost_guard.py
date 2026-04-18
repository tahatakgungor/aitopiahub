"""Budget-aware policy for optional premium generation providers."""

from __future__ import annotations

from dataclasses import dataclass

from aitopiahub.core.config import get_settings


@dataclass
class BudgetDecision:
    premium_allowed: bool
    estimated_cost_usd: float
    reason: str


class CostGuard:
    """Keeps episode generation under configured per-video budget."""

    def __init__(self):
        self.settings = get_settings()

    def evaluate_tts_budget(self, total_text_chars: int) -> BudgetDecision:
        """
        Decide whether premium TTS can be used for this episode.

        The cost model is intentionally simple and fully configurable via env vars.
        """
        if self.settings.automation_strict_free:
            return BudgetDecision(False, 0.0, "strict_free_policy")
        if not self.settings.allow_premium_models:
            return BudgetDecision(False, 0.0, "premium_disabled")
        if not self.settings.elevenlabs_api_key.strip():
            return BudgetDecision(False, 0.0, "missing_premium_api_key")

        units = max(total_text_chars, 0) / 1000.0
        est = units * max(self.settings.elevenlabs_cost_per_1k_chars, 0.0)
        if est > max(self.settings.max_cost_per_video_usd, 0.0):
            return BudgetDecision(False, est, "budget_exceeded")
        return BudgetDecision(True, est, "within_budget")
