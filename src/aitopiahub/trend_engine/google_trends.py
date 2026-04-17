"""
Google Trends'den güncel trend verisini çeker.
pytrends kütüphanesi — tamamen ücretsiz, API key gerektirmez.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from pytrends.request import TrendReq

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class GoogleTrend:
    keyword: str
    trend_index: float          # 0-100 arası Google Trends indeksi
    related_queries: list[str]
    region: str
    fetched_at: datetime = field(default_factory=datetime.utcnow)


class GoogleTrendsFetcher:
    """
    Google Trends'den TR + Global trending konuları çeker.
    Seed keywords + realtime trending topics.
    """

    TR_GEO = "TR"
    GLOBAL_GEO = ""

    def __init__(self, seed_keywords: list[str]):
        self.seed_keywords = seed_keywords
        self._pytrends = TrendReq(
            hl="tr-TR",
            tz=180,  # UTC+3 (İstanbul)
            timeout=(10, 30),
            # pytrends'in bazı sürümlerinde urllib3 Retry parametre uyumsuzluğu
            # (method_whitelist -> allowed_methods) görülebiliyor.
            # Stabilite için internal retry kapalı; hata yönetimi çağıran task'ta.
            retries=0,
            backoff_factor=0,
        )

    async def fetch_trends(self) -> list[GoogleTrend]:
        """Seed keywords için güncel trend indekslerini çek."""
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> list[GoogleTrend]:
        trends: list[GoogleTrend] = []

        # Batch'lere böl (pytrends max 5 keyword/istek)
        batch_size = 5
        for i in range(0, len(self.seed_keywords), batch_size):
            batch = self.seed_keywords[i:i + batch_size]
            try:
                batch_trends = self._fetch_batch(batch, geo=self.TR_GEO)
                trends.extend(batch_trends)
            except Exception as e:
                log.warning("google_trends_batch_failed", batch=batch, error=str(e))

        # Global trending (İngilizce seed'ler için)
        try:
            realtime = self._fetch_realtime_trending()
            trends.extend(realtime)
        except Exception as e:
            log.warning("google_trends_realtime_failed", error=str(e))

        log.info("google_trends_fetched", count=len(trends))
        return trends

    def _fetch_batch(self, keywords: list[str], geo: str) -> list[GoogleTrend]:
        self._pytrends.build_payload(
            keywords,
            cat=0,
            timeframe="now 1-d",
            geo=geo,
        )
        interest_df = self._pytrends.interest_over_time()

        if interest_df.empty:
            return []

        trends = []
        latest = interest_df.iloc[-1]
        for kw in keywords:
            if kw not in latest:
                continue
            index_value = float(latest[kw])
            if index_value < 10:
                continue

            # İlgili sorgular
            try:
                related = self._pytrends.related_queries()
                top_queries = related.get(kw, {}).get("top", None)
                related_list = (
                    top_queries["query"].tolist()[:5]
                    if top_queries is not None and not top_queries.empty
                    else []
                )
            except Exception:
                related_list = []

            trends.append(
                GoogleTrend(
                    keyword=kw,
                    trend_index=index_value,
                    related_queries=related_list,
                    region=geo or "GLOBAL",
                )
            )
        return trends

    def _fetch_realtime_trending(self) -> list[GoogleTrend]:
        """Türkiye'deki realtime trending searches."""
        try:
            df = self._pytrends.trending_searches(pn="turkey")
            if df is None or df.empty:
                return []

            trends = []
            for _, row in df.head(20).iterrows():
                keyword = str(row[0]).strip()
                if len(keyword) < 3:
                    continue
                trends.append(
                    GoogleTrend(
                        keyword=keyword,
                        trend_index=50.0,  # Realtime trend'ler için default
                        related_queries=[],
                        region=self.TR_GEO,
                    )
                )
            return trends
        except Exception as e:
            log.warning("realtime_trending_failed", error=str(e))
            return []
