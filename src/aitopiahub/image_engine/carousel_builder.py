"""
Carousel içerik montajı.
AI görsel (Pollinations) + Pillow şablonları birleştirerek
tam bir Instagram carousel seti üretir.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aitopiahub.image_engine.pollinations_provider import PollinationsProvider
from aitopiahub.image_engine.template_renderer import TemplateRenderer
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class CarouselSlide:
    index: int
    is_cover: bool
    image_bytes: bytes
    slide_type: str  # 'ai_cover', 'template_content', 'template_cta'


class CarouselBuilder:
    """
    Carousel slayt dizisi üretir:
    - Kapak: AI görsel + başlık (Pollinations)
    - İç slaytlar: Pillow şablon
    - Son slayt: CTA şablon
    """

    def __init__(self):
        self.pollinations = PollinationsProvider()
        self.renderer = TemplateRenderer()

    async def build(
        self,
        slide_texts: list[dict],
        image_prompt_hint: str,
        generate_ai_cover: bool = True,
    ) -> list[CarouselSlide]:
        """Tam carousel seti üret."""

        slides = []
        total = len(slide_texts)

        for i, slide_data in enumerate(slide_texts):
            is_cover = slide_data.get("is_cover", i == 0)
            headline = slide_data.get("headline", "")
            body = slide_data.get("body", "")
            is_cta = "takip et" in headline.lower() or "follow" in headline.lower()

            if is_cta:
                # Son slayt: CTA
                image_bytes = self.renderer.render_slide_cta(headline)
                slide_type = "template_cta"
            elif is_cover and generate_ai_cover:
                # Kapak: AI görsel dene, başarısız olursa şablon
                ai_image = await self._get_ai_image(image_prompt_hint)
                image_bytes = self.renderer.render_slide_cover(
                    headline,
                    bg_image=ai_image,
                )
                slide_type = "ai_cover" if ai_image else "template_cover"
            else:
                # İç slayt: şablon
                image_bytes = self.renderer.render_slide_content(
                    slide_num=i + 1,
                    total_slides=total,
                    headline=headline,
                    body=body,
                )
                slide_type = "template_content"

            slides.append(
                CarouselSlide(
                    index=i,
                    is_cover=is_cover,
                    image_bytes=image_bytes,
                    slide_type=slide_type,
                )
            )

            log.debug("carousel_slide_built", index=i, type=slide_type, bytes=len(image_bytes))

        log.info("carousel_built", total_slides=len(slides))
        return slides

    async def _get_ai_image(self, hint: str) -> bytes | None:
        """Pollinations'dan görsel al, başarısız olursa None."""
        try:
            return await asyncio.wait_for(
                self.pollinations.generate(hint, size="square"),
                timeout=45,
            )
        except asyncio.TimeoutError:
            log.warning("ai_image_timeout", hint=hint[:50])
            return None
        except Exception as e:
            log.warning("ai_image_error", error=str(e))
            return None
