"""Stock video fetcher for kid-friendly scene motion assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class StockVideoAsset:
    provider: str
    query: str
    url: str
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    tags: list[str] | None = None


class StockVideoProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.timeout = aiohttp.ClientTimeout(total=20)

    async def fetch(self, query: str, mood: str = "playful") -> StockVideoAsset | None:
        """Try primary + secondary providers in order."""
        providers = [
            (self.settings.visual_provider_primary or "pexels").strip().lower(),
            (self.settings.visual_provider_secondary or "pixabay").strip().lower(),
        ]
        seen: set[str] = set()
        for provider in providers:
            if not provider or provider in seen:
                continue
            seen.add(provider)
            try:
                if provider == "pexels":
                    asset = await self._fetch_pexels(query, mood)
                elif provider == "pixabay":
                    asset = await self._fetch_pixabay(query, mood)
                else:
                    continue
                if asset:
                    return asset
            except Exception as exc:
                log.warning("stock_video_provider_error", provider=provider, error=str(exc))
        return None

    async def _fetch_pexels(self, query: str, mood: str) -> StockVideoAsset | None:
        api_key = (self.settings.pexels_api_key or "").strip()
        if not api_key:
            return None
        params = {"query": f"{query} kids animation {mood}", "per_page": 12, "orientation": "portrait"}
        headers = {"Authorization": api_key}
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get("https://api.pexels.com/videos/search", params=params, headers=headers) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json()
        videos = payload.get("videos") or []
        best = self._pick_best_pexels(videos)
        if not best:
            return None
        best.query = query
        return best

    async def _fetch_pixabay(self, query: str, mood: str) -> StockVideoAsset | None:
        api_key = (self.settings.pixabay_api_key or "").strip()
        if not api_key:
            return None
        params = {"key": api_key, "q": f"{query} kids {mood}", "video_type": "all", "per_page": 15}
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get("https://pixabay.com/api/videos/", params=params) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json()
        hits = payload.get("hits") or []
        best = self._pick_best_pixabay(hits, query=query)
        if not best:
            return None
        return best

    def _pick_best_pexels(self, videos: list[dict[str, Any]]) -> StockVideoAsset | None:
        winner: StockVideoAsset | None = None
        winner_score = -1.0
        banned_tokens = {"news", "anchor", "studio", "politics", "war", "blood", "crime"}
        for item in videos:
            tags_blob = str(item.get("url") or "").lower()
            if any(token in tags_blob for token in banned_tokens):
                continue
            duration = float(item.get("duration") or 0.0)
            for file_info in item.get("video_files") or []:
                link = str(file_info.get("link") or "")
                if not link:
                    continue
                width = int(file_info.get("width") or 0)
                height = int(file_info.get("height") or 0)
                quality = str(file_info.get("quality") or "").lower()
                score = 0.0
                if height >= width and width >= 720:
                    score += 2.0
                if quality == "hd":
                    score += 1.0
                if 4 <= duration <= 15:
                    score += 1.5
                if score > winner_score:
                    winner_score = score
                    winner = StockVideoAsset(
                        provider="pexels",
                        query="",
                        url=link,
                        duration=duration or None,
                        width=width or None,
                        height=height or None,
                        tags=[],
                    )
        return winner

    def _pick_best_pixabay(self, hits: list[dict[str, Any]], query: str) -> StockVideoAsset | None:
        winner: StockVideoAsset | None = None
        winner_score = -1.0
        banned_tokens = {"news", "anchor", "studio", "politics", "war", "blood", "crime"}
        for item in hits:
            tags_text = str(item.get("tags") or "").lower()
            if any(token in tags_text for token in banned_tokens):
                continue
            videos = item.get("videos") or {}
            chosen = videos.get("large") or videos.get("medium") or videos.get("small")
            if not isinstance(chosen, dict):
                continue
            link = str(chosen.get("url") or "")
            if not link:
                continue
            width = int(chosen.get("width") or 0)
            height = int(chosen.get("height") or 0)
            duration = float(item.get("duration") or 0.0)
            score = 0.0
            if height >= width and width >= 720:
                score += 2.0
            if 4 <= duration <= 15:
                score += 1.5
            if score > winner_score:
                winner_score = score
                tags = str(item.get("tags") or "").split(",")
                winner = StockVideoAsset(
                    provider="pixabay",
                    query=query,
                    url=link,
                    duration=duration or None,
                    width=width or None,
                    height=height or None,
                    tags=[t.strip() for t in tags if t.strip()],
                )
        return winner
