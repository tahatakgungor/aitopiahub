"""
Ajan 4 — Localizer
Görev: Sadece çeviri değil, kültürel adaptasyon.
TR versiyonu: Türk okuyucuya hitap eden ton, yerel bağlam.
EN versiyonu: Global kitleye uygun.
"""

from __future__ import annotations

from dataclasses import dataclass

from aitopiahub.content_engine.agents.writer import WriterOutput
from aitopiahub.content_engine.llm_client import LLMClient, ModelTier
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class LocalizedContent:
    tr_caption: str
    en_caption: str
    tr_slide_texts: list[dict] | None
    en_slide_texts: list[dict] | None
    primary_language: str


class LocalizerAgent:
    """
    İçeriği hem TR hem EN'e adapte eder.
    Önemli: Bu bir çeviri aracı değil — her dil kendi doğasında akıcı olmalı.
    """

    SYSTEM_PROMPT = """Sen iki dilli bir sosyal medya uzmanısın.
Türkçe versiyon: Türk internet kültürüne, yerel referanslara ve TR kullanıcıların ilgi alanlarına uygun.
İngilizce versiyon: Global, evrensel, uluslararası kitleye uygun.
Her iki versiyon da kendi dilinde DOĞAL hissettirmeli — kelimesi kelimesine çeviri yapma."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def localize(
        self,
        writer_output: WriterOutput,
        primary_language: str = "tr",
    ) -> LocalizedContent:
        """İçeriği her iki dile adapte et."""

        tr_caption, en_caption = await self._localize_caption(writer_output.caption_text)

        tr_slides = None
        en_slides = None
        if writer_output.slide_texts:
            tr_slides, en_slides = await self._localize_slides(writer_output.slide_texts)

        log.info("localizer_done", post_format=writer_output.post_format)

        return LocalizedContent(
            tr_caption=tr_caption,
            en_caption=en_caption,
            tr_slide_texts=tr_slides,
            en_slide_texts=en_slides,
            primary_language=primary_language,
        )

    async def _localize_caption(self, caption: str) -> tuple[str, str]:
        prompt = f"""Orijinal içerik:
{caption}

Bu içeriği hem Türkçe hem İngilizce olarak adapte et. JSON döndür:
{{
  "tr": "Türkçe versiyon — Türk internet kültürüne uygun, doğal Türkçe",
  "en": "English version — Global audience friendly, natural English"
}}

Kurallar:
- Kelimesi kelimesine çeviri yapma
- Her dilde yerel deyim ve ifadeler kullan
- Emoji'leri koru ama gerekirse adapte et
- TR'de Türk kullanıcılara yakın referanslar kullan
- EN'de evrensel referanslar kullan"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.SYSTEM_PROMPT,
                model=ModelTier.QUALITY,
                max_tokens=600,
            )
            return data.get("tr", caption), data.get("en", caption)
        except Exception as e:
            log.warning("localizer_caption_failed", error=str(e))
            return caption, caption

    async def _localize_slides(
        self, slides: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        slides_json = str(slides)
        prompt = f"""İçerik (Slaytlar veya Video Sahneleri):
{slides_json[:1500]}

Bu içeriği hem Türkçe hem İngilizce adapte et. 
Önemli: Eğer bu bir video senaryosu ise (her objede 'image_prompt' varsa), bu alanları ASLA çevirme, olduğu gibi koru. Sadece 'text' veya 'headline' gibi metin alanlarını adapte et.

JSON döndür:
{{
  "tr_slides": [/* Türkçe versiyonlar, aynı JSON yapısında ve aynı sayıda obje */],
  "en_slides": [/* English versions, same JSON structure and count */]
}}"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.SYSTEM_PROMPT,
                model=ModelTier.QUALITY,
                max_tokens=2000,
            )
            return data.get("tr_slides", slides), data.get("en_slides", slides)
        except Exception as e:
            log.warning("localizer_slides_failed", error=str(e))
            return slides, slides
