"""Quality gate scoring and publish decision."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pydub import AudioSegment

from aitopiahub.core.config import get_settings
from aitopiahub.core.exceptions import QualityGateError


@dataclass
class QualityGateResult:
    audio_score: float
    visual_score: float
    music_score: float
    technical_score: float
    passed: bool
    failed_layer: str | None

    @property
    def scores(self) -> dict[str, float]:
        return {
            "audio": self.audio_score,
            "visual": self.visual_score,
            "music": self.music_score,
            "technical": self.technical_score,
        }


class QualityGate:
    def __init__(self):
        self.settings = get_settings()

    def evaluate(
        self,
        *,
        scene_data: list[dict[str, Any]],
        video_path: Path,
        music_track_id: str | None,
    ) -> QualityGateResult:
        audio_score = self._audio_score(scene_data)
        visual_score = self._visual_score(scene_data)
        music_score = self._music_score(music_track_id)
        technical_score = self._technical_score(video_path=video_path)

        failed_layer: str | None = None
        if audio_score < self.settings.quality_min_audio:
            failed_layer = "audio"
        elif visual_score < self.settings.quality_min_visual:
            failed_layer = "visual"
        elif music_score < self.settings.quality_min_music:
            failed_layer = "music"
        elif technical_score < self.settings.quality_min_technical:
            failed_layer = "technical"

        passed = failed_layer is None
        return QualityGateResult(
            audio_score=audio_score,
            visual_score=visual_score,
            music_score=music_score,
            technical_score=technical_score,
            passed=passed,
            failed_layer=failed_layer,
        )

    def ensure(self, result: QualityGateResult) -> None:
        if not self.settings.quality_gate_strict:
            return
        if result.passed:
            return
        raise QualityGateError(f"quality_gate_failed:{result.failed_layer}:{result.scores}")

    def _audio_score(self, scene_data: list[dict[str, Any]]) -> float:
        scores: list[float] = []
        for scene in scene_data:
            audio_path = Path(str(scene.get("audio_path") or ""))
            if not audio_path.exists():
                continue
            try:
                seg = AudioSegment.from_file(audio_path)
            except Exception:
                continue
            arr = np.array(seg.get_array_of_samples()).astype(np.float32)
            if arr.size == 0:
                continue
            peak = np.max(np.abs(arr)) + 1e-6
            rms = np.sqrt(np.mean(np.square(arr))) + 1e-6
            snr_like = float(min(max((rms / peak) * 2.0, 0.0), 1.0))
            clipping = float(np.mean(np.abs(arr) >= peak * 0.99))
            silence = float(np.mean(np.abs(arr) < (peak * 0.02)))
            score = snr_like * 0.55 + (1.0 - clipping) * 0.30 + (1.0 - silence) * 0.15
            scores.append(float(min(max(score, 0.0), 1.0)))
        if not scores:
            return 0.0
        return float(sum(scores) / len(scores))

    def _visual_score(self, scene_data: list[dict[str, Any]]) -> float:
        scores: list[float] = []
        for scene in scene_data:
            text = str(scene.get("text") or "").lower()
            query = str(scene.get("asset_query") or "").lower()
            provider = str(scene.get("visual_provider_used") or "").lower()

            # If no visual asset at all, penalise.
            image_path = scene.get("image_path") or scene.get("visual_path") or ""
            video_path = scene.get("video_path") or ""
            has_visual = bool(image_path or video_path)

            if not has_visual:
                scores.append(0.1)
                continue

            # AI image generators (Pollinations/DALL-E/Stable Diffusion) produce
            # on-demand visuals that match the prompt well — reward them highly.
            ai_providers = {"pollinations", "dalle", "openai", "stable_diffusion", "sd"}
            stock_providers = {"pexels", "pixabay", "unsplash"}

            if any(p in provider for p in ai_providers):
                provider_bonus = 0.55  # AI images are scene-specific
            elif any(p in provider for p in stock_providers):
                provider_bonus = 0.40  # Stock footage is relevant but generic
            elif has_visual:
                provider_bonus = 0.30  # Fallback / template image

            # Semantic overlap is a soft bonus, not the primary signal.
            if text and query:
                text_tokens = {tok for tok in text.split() if len(tok) > 3}
                query_tokens = {tok for tok in query.split() if len(tok) > 3}
                overlap = len(text_tokens & query_tokens) / max(1, len(query_tokens))
            else:
                overlap = 0.0

            score = min(1.0, provider_bonus + overlap * 0.45)
            scores.append(score)

        if not scores:
            return 0.0
        return float(sum(scores) / len(scores))

    def _music_score(self, music_track_id: str | None) -> float:
        if not music_track_id:
            return 0.2
        return 0.85

    def _technical_score(self, video_path: Path) -> float:
        if not video_path.exists():
            return 0.0
        size_mb = video_path.stat().st_size / (1024 * 1024)
        if size_mb <= 1:
            return 0.3
        if size_mb < 5:
            return 0.6
        return 1.0
