"""
NewsAPI free tier ile teknoloji haberleri çeker.
Trend sinyaline ek haber mention katkısı sağlar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class NewsItem:
    source_name: str
    title: str
    description: str
    url: str
    published_at: datetime | None


class NewsAggregator:
    """NewsAPI wrapper (free tier)."""

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 12):
        settings = get_settings()
        self.api_key = api_key or settings.newsapi_key
        self.timeout = timeout_seconds
        self.base_url = "https://newsapi.org/v2/everything"

    async def fetch_tech_headlines(
        self,
        seed_keywords: list[str] | None = None,
        page_size: int = 30,
    ) -> list[NewsItem]:
        """
        Tek istekle teknoloji odaklı haber akışı döndür.
        Free tier limitine saygılı olmak için çağrı sayısı düşük tutulur.
        """
        if not self.api_key:
            log.debug("newsapi_key_missing_skip")
            return []

        query = self._build_query(seed_keywords or [])
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": max(1, min(page_size, 100)),
            "apiKey": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
        except Exception as exc:
            log.warning("newsapi_request_error", error=str(exc))
            return []

        if response.status_code != 200:
            log.warning("newsapi_bad_status", status=response.status_code)
            return []

        try:
            payload = response.json()
        except ValueError:
            log.warning("newsapi_parse_error")
            return []

        articles = payload.get("articles", []) or []
        items: list[NewsItem] = []
        for article in articles:
            title = (article.get("title") or "").strip()
            if not title:
                continue

            items.append(
                NewsItem(
                    source_name=(article.get("source") or {}).get("name", "unknown"),
                    title=title,
                    description=(article.get("description") or "").strip(),
                    url=article.get("url") or "",
                    published_at=self._parse_published_at(article.get("publishedAt")),
                )
            )

        log.info("newsapi_fetch_complete", total_items=len(items))
        return items

    def _build_query(self, seed_keywords: list[str]) -> str:
        cleaned = [kw.strip() for kw in seed_keywords if kw and kw.strip()]
        if cleaned:
            # Free tier'da sorguyu kısa tut: en fazla 5 seed keyword.
            return " OR ".join(cleaned[:5])
        return "artificial intelligence OR machine learning OR technology"

    def _parse_published_at(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
