"""İçerik format serializer'ları (Instagram + future channels)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ShortScript:
    title_hook: str
    voiceover_lines: list[str]
    thumbnail_hook: str
    cta_line: str


class ContentFormatBuilder:
    """Mevcut caption/slide yapısından kanal-özel format üretir."""

    def build_short_script(self, caption: str, slide_texts: list[dict] | None = None) -> ShortScript:
        lines = [line.strip() for line in (caption or "").splitlines() if line.strip()]
        hook = lines[0][:70] if lines else "Bugün AI dünyasında kritik bir gelişme var"

        voiceover: list[str] = []
        if slide_texts:
            for slide in slide_texts[:4]:
                headline = str(slide.get("headline", "")).strip()
                body = str(slide.get("body", "")).strip()
                if headline:
                    voiceover.append(headline)
                if body:
                    voiceover.append(body[:160])
        if not voiceover:
            voiceover = lines[1:5] if len(lines) > 1 else [hook]

        cta = "Daha fazlası için takip etmeyi unutma."
        thumbnail = hook[:45]
        return ShortScript(
            title_hook=hook,
            voiceover_lines=voiceover[:6],
            thumbnail_hook=thumbnail,
            cta_line=cta,
        )
