"""
Async RSS/Atom feed okuyucu.
25+ kaynak eş zamanlı çekilir — aiohttp + feedparser.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp
import feedparser

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# Global + Türkçe haber kaynakları (Aitopiahub News için)
DEFAULT_RSS_SOURCES = [
    # === Global Tech ===
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "lang": "en"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "lang": "en"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "lang": "en"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "lang": "en"},
    {"name": "ZDNet AI", "url": "https://www.zdnet.com/topic/artificial-intelligence/rss.xml", "lang": "en"},
    # === Türkçe Tech ===
    {"name": "Webtekno", "url": "https://www.webtekno.com/rss.xml", "lang": "tr"},
    {"name": "ShiftDelete", "url": "https://shiftdelete.net/feed", "lang": "tr"},
    {"name": "Donanım Haber", "url": "https://www.donanimhaber.com/rss/tum/", "lang": "tr"},
    {"name": "Hürriyet Teknoloji", "url": "https://www.hurriyet.com.tr/rss/teknoloji", "lang": "tr"},
    {"name": "Sabah Teknoloji", "url": "https://www.sabah.com.tr/rss/teknoloji.xml", "lang": "tr"},
    {"name": "Milliyet Teknoloji", "url": "https://www.milliyet.com.tr/rss/rssNew/teknoloji", "lang": "tr"},
]


@dataclass
class RSSItem:
    source_name: str
    title: str
    content: str
    url: str
    published_at: datetime | None
    language: str
    content_hash: str


class RSSFetcher:
    """Tüm kaynakları paralel olarak çeker."""

    def __init__(self, sources: list[dict] | None = None, timeout_seconds: int = 15):
        self.sources = sources or DEFAULT_RSS_SOURCES
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def fetch_all(self) -> list[RSSItem]:
        async with aiohttp.ClientSession(
            timeout=self.timeout,
            headers={"User-Agent": "Aitopiahub/1.0 RSS Reader"},
        ) as session:
            tasks = [self._fetch_source(session, src) for src in self.sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[RSSItem] = []
        for result in results:
            if isinstance(result, list):
                items.extend(result)
            elif isinstance(result, Exception):
                log.warning("rss_fetch_exception", error=str(result))

        log.info("rss_fetch_complete", total_items=len(items), sources=len(self.sources))
        return items

    async def _fetch_source(self, session: aiohttp.ClientSession, source: dict) -> list[RSSItem]:
        try:
            async with session.get(source["url"]) as resp:
                if resp.status != 200:
                    log.warning("rss_source_error", source=source["name"], status=resp.status)
                    return []
                raw = await resp.text()
        except Exception as e:
            log.warning("rss_source_timeout", source=source["name"], error=str(e))
            return []

        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries[:10]:  # Kaynak başı max 10 haber
            title = getattr(entry, "title", "").strip()
            if not title:
                continue

            content = (
                getattr(entry, "summary", "")
                or getattr(entry, "description", "")
                or ""
            ).strip()

            url = getattr(entry, "link", "")
            published = self._parse_date(entry)

            raw_text = f"{title} {url}"
            content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

            items.append(
                RSSItem(
                    source_name=source["name"],
                    title=title,
                    content=content[:2000],
                    url=url,
                    published_at=published,
                    language=source.get("lang", "en"),
                    content_hash=content_hash,
                )
            )
        return items

    def _parse_date(self, entry) -> datetime | None:
        try:
            import time
            published_parsed = getattr(entry, "published_parsed", None)
            if published_parsed:
                return datetime.fromtimestamp(time.mktime(published_parsed))
        except Exception:
            pass
        return None
