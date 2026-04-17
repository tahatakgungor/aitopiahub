"""
Meta Instagram Graph API wrapper.
Tek görsel ve carousel post destekler.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from aitopiahub.core.config import get_settings
from aitopiahub.core.exceptions import PublishError
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


@dataclass
class PublishResult:
    media_id: str
    permalink: str | None = None


class InstagramClient:
    """
    Meta Graph API ile Instagram'a post yayınlar.

    Akış (Carousel):
      1. Her slayt görseli media container oluştur
      2. Carousel container oluştur (tüm slayt ID'leri ile)
      3. Yayınla

    Akış (Single):
      1. Görsel media container oluştur
      2. Yayınla
    """

    def __init__(
        self,
        access_token: str | None = None,
        business_account_id: str | None = None,
    ):
        settings = get_settings()
        self._token = access_token or settings.instagram_access_token
        self._account_id = business_account_id or settings.instagram_business_account_id
        self._timeout = aiohttp.ClientTimeout(total=60)

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def publish_single(
        self,
        image_url: str,
        caption: str,
    ) -> PublishResult:
        """Tek görsel post yayınla."""
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            # Adım 1: Media container oluştur
            container_id = await self._create_image_container(session, image_url, caption)

            # Kısa bekleme — Meta API gereksinimi
            await asyncio.sleep(3)

            # Adım 2: Yayınla
            media_id = await self._publish_container(session, container_id)

        log.info("instagram_single_published", media_id=media_id)
        return PublishResult(media_id=media_id)

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def publish_carousel(
        self,
        image_urls: list[str],
        caption: str,
    ) -> PublishResult:
        """Çok slaytlı carousel post yayınla."""
        if not 2 <= len(image_urls) <= 10:
            raise PublishError(f"Carousel: 2-10 slayt gerekli, {len(image_urls)} verildi")

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            # Adım 1: Her slayt için ayrı container
            slide_ids = []
            for i, url in enumerate(image_urls):
                cid = await self._create_image_container(
                    session, url, caption=None, is_carousel_item=True
                )
                slide_ids.append(cid)
                log.debug("carousel_slide_container", index=i, container_id=cid)
                await asyncio.sleep(1)  # Rate limit önlemi

            # Adım 2: Carousel container
            carousel_id = await self._create_carousel_container(session, slide_ids, caption)

            # Adım 3: Yayınla
            await asyncio.sleep(5)  # Meta API gecikme
            media_id = await self._publish_container(session, carousel_id)

        log.info("instagram_carousel_published", media_id=media_id, slides=len(image_urls))
        return PublishResult(media_id=media_id)

    async def get_media_insights(self, media_id: str) -> dict:
        """Post engagement metriklerini çek."""
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            url = f"{GRAPH_BASE}/{media_id}/insights"
            params = {
                "metric": "impressions,reach,likes,comments,shares,saved",
                "access_token": self._token,
            }
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                if "error" in data:
                    log.warning("insights_error", media_id=media_id, error=data["error"])
                    return {}
                return data

    async def _create_image_container(
        self,
        session: aiohttp.ClientSession,
        image_url: str,
        caption: str | None,
        is_carousel_item: bool = False,
    ) -> str:
        url = f"{GRAPH_BASE}/{self._account_id}/media"
        payload: dict = {
            "image_url": image_url,
            "access_token": self._token,
        }
        if caption and not is_carousel_item:
            payload["caption"] = caption
        if is_carousel_item:
            payload["is_carousel_item"] = True

        async with session.post(url, data=payload) as resp:
            data = await resp.json()
            if "error" in data:
                raise PublishError(f"Container oluşturulamadı: {data['error']}")
            return data["id"]

    async def _create_carousel_container(
        self,
        session: aiohttp.ClientSession,
        children: list[str],
        caption: str,
    ) -> str:
        url = f"{GRAPH_BASE}/{self._account_id}/media"
        payload = {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
            "access_token": self._token,
        }
        async with session.post(url, data=payload) as resp:
            data = await resp.json()
            if "error" in data:
                raise PublishError(f"Carousel container oluşturulamadı: {data['error']}")
            return data["id"]

    async def _publish_container(
        self, session: aiohttp.ClientSession, container_id: str
    ) -> str:
        url = f"{GRAPH_BASE}/{self._account_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self._token,
        }
        async with session.post(url, data=payload) as resp:
            data = await resp.json()
            if "error" in data:
                raise PublishError(f"Yayınlama başarısız: {data['error']}")
            return data["id"]
