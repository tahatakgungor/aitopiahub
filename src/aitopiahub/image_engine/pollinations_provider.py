"""
Pollinations.ai FLUX.1 görsel üretici.
Tamamen ücretsiz, API key gerektirmez.
https://pollinations.ai
"""

from __future__ import annotations

import asyncio
import urllib.parse
from pathlib import Path

import aiohttp

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

BASE_URL = "https://image.pollinations.ai/prompt"

# Instagram format boyutları
SIZES = {
    "square": (1080, 1080),       # Feed 1:1
    "portrait": (1080, 1350),     # Feed 4:5 (en iyi erişim)
    "story": (1080, 1920),        # Story 9:16
}


class PollinationsProvider:
    """
    FLUX.1 modeli ile ücretsiz görsel üretir.
    Timeout: 60 saniye. Başarısız olursa None döner.
    """

    def __init__(self, timeout: int = 60):
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def generate(
        self,
        prompt: str,
        size: str = "portrait",
        seed: int | None = None,
        model: str = "flux",
    ) -> bytes | None:
        """Görsel üret ve raw bytes döndür."""
        enhanced_prompt = self._enhance_prompt(prompt)
        url = self._build_url(enhanced_prompt, size, seed, model)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        log.warning("pollinations_error", status=resp.status, url=url[:100])
                        return None
                    content_type = resp.headers.get("Content-Type", "")
                    if "image" not in content_type:
                        log.warning("pollinations_not_image", content_type=content_type)
                        return None
                    data = await resp.read()
                    log.info("pollinations_success", size=size, bytes=len(data))
                    return data
        except asyncio.TimeoutError:
            log.warning("pollinations_timeout", prompt=prompt[:50])
            return None
        except Exception as e:
            log.warning("pollinations_exception", error=str(e))
            return None

    def _build_url(
        self, prompt: str, size: str, seed: int | None, model: str
    ) -> str:
        w, h = SIZES.get(size, SIZES["portrait"])
        encoded = urllib.parse.quote(prompt)
        url = f"{BASE_URL}/{encoded}?width={w}&height={h}&model={model}&nologo=true&enhance=true"
        if seed is not None:
            url += f"&seed={seed}"
        return url

    def _enhance_prompt(self, hint: str) -> str:
        """Görsel prompt'u kalite artırıcı terimlerle zenginleştir."""
        quality_terms = (
            "professional photography, high resolution, 8k, sharp focus, "
            "cinematic lighting, modern aesthetic, clean composition"
        )
        style_terms = (
            "tech news magazine style, no text overlay, no watermark, "
            "photorealistic, vibrant colors"
        )
        return f"{hint}. {style_terms}. {quality_terms}"
