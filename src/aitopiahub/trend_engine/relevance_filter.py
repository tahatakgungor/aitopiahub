"""
LLM tabanlı trend relevance sınıflandırıcısı.
Llama 3.1 8B (Groq) ile hızlı batch sınıflandırma.
10 trend → tek prompt → 0-10 puanlama → threshold ≥ 7
"""

from __future__ import annotations

import json

from aitopiahub.content_engine.llm_client import LLMClient
from aitopiahub.core.logging import get_logger
from aitopiahub.trend_engine.trend_scorer import ScoredTrend

log = get_logger(__name__)


class RelevanceFilter:
    """
    Hesap niche'ine göre trend'leri filtreler.
    Groq Llama 8B kullanır — hızlı ve ucuz.
    """

    THRESHOLD = 7.0

    def __init__(self, llm: LLMClient, niche: str, blocked_keywords: list[str] | None = None):
        self.llm = llm
        self.niche = niche
        self.blocked_keywords = [kw.lower() for kw in (blocked_keywords or [])]

    async def filter(self, trends: list[ScoredTrend]) -> list[ScoredTrend]:
        """Alakalı olmayan trend'leri eledir."""
        # Önce keyword blocklist kontrolü
        trends = [t for t in trends if not self._is_blocked(t.keyword)]

        if not trends:
            return []

        # Batch halinde LLM ile değerlendir (max 10'ar)
        passing = []
        batch_size = 10
        for i in range(0, len(trends), batch_size):
            batch = trends[i:i + batch_size]
            scores = await self._score_batch(batch)
            for trend, score in zip(batch, scores):
                if score >= self.THRESHOLD:
                    passing.append(trend)
                else:
                    log.debug(
                        "trend_filtered_by_relevance",
                        keyword=trend.keyword,
                        relevance=score,
                    )

        log.info(
            "relevance_filter_done",
            input=len(trends),
            output=len(passing),
            niche=self.niche,
        )
        return passing

    async def _score_batch(self, trends: list[ScoredTrend]) -> list[float]:
        keywords = [t.keyword for t in trends]
        prompt = self._build_prompt(keywords)

        try:
            response = await self.llm.complete(
                prompt,
                model="fast",  # Llama 3.1 8B
                max_tokens=300,
                temperature=0.1,
            )
            return self._parse_scores(response, len(trends))
        except Exception as e:
            log.warning("relevance_filter_llm_error", error=str(e))
            # LLM başarısız → hepsini geçir (güvenli taraf)
            return [7.0] * len(trends)

    def _build_prompt(self, keywords: list[str]) -> str:
        keywords_str = "\n".join(f"{i+1}. {kw}" for i, kw in enumerate(keywords))
        return f"""Sen bir sosyal medya içerik editörüsün. Hesap niş'i: "{self.niche}".

Aşağıdaki her trend konusu için, bu hesabın kitlesine ne kadar alakalı olduğunu 0-10 arasında puanla.
- 8-10: Çok alakalı, kesinlikle içerik yapılmalı
- 5-7: Kısmen alakalı
- 0-4: Alakasız, atla

Trend'ler:
{keywords_str}

Sadece JSON array döndür. Örnek: [8, 3, 9, 2, 7]
Açıklama yapma, sadece sayılar."""

    def _parse_scores(self, response: str, expected: int) -> list[float]:
        try:
            # JSON array bul
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                scores = json.loads(response[start:end])
                if len(scores) == expected:
                    return [float(s) for s in scores]
        except (json.JSONDecodeError, ValueError):
            pass

        log.warning("relevance_filter_parse_error", response=response[:200])
        return [7.0] * expected  # Parse hatası → hepsini geçir

    def _is_blocked(self, keyword: str) -> bool:
        kw_lower = keyword.lower()
        return any(blocked in kw_lower for blocked in self.blocked_keywords)
