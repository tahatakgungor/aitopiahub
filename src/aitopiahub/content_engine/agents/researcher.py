"""
Ajan 1 — Researcher
Görev: Trend için kaynak materyal topla, özetle, ana bulgular çıkar.
Çıktı: Yapılandırılmış araştırma notu (JSON).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aitopiahub.content_engine.llm_client import LLMClient, ModelTier
from aitopiahub.core.logging import get_logger
from aitopiahub.trend_engine.rss_fetcher import RSSItem

log = get_logger(__name__)


@dataclass
class ResearchNote:
    keyword: str
    main_finding: str
    supporting_facts: list[str]
    source_urls: list[str]
    source_credibility: float   # 0-10
    novelty_score: float        # 0-10
    suggested_angle: str        # Önerilen içerik açısı
    language_of_sources: str    # 'tr', 'en', 'mixed'
    raw_sources: list[str] = field(default_factory=list)


class ResearcherAgent:
    """
    İlgili RSS item'larını analiz eder ve yapılandırılmış bir
    araştırma notu üretir. İçerik kalitesinin temeli burada atılır.
    """

    SYSTEM_PROMPT = """Sen deneyimli bir teknoloji gazetecisisin.
Verilen haber başlıklarını ve içeriklerini analiz ederek:
1. Ana bulguyu tek cümleyle özetle
2. Destekleyici 3-5 faktüel detay çıkar
3. İçerik için en iyi açıyı öner (bilgilendirici mi, tartışmalı mı, pratik mi?)
4. Kaynakların güvenilirliğini değerlendir

Her zaman doğru bilgilere sadık kal. Spekülasyon yapma."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def research(
        self,
        keyword: str,
        related_items: list[RSSItem],
        niche: str = "news",
    ) -> ResearchNote:
        """Trend keyword için araştırma notu üret."""

        if not related_items:
            return self._empty_note(keyword)

        # En alakalı 5 kaynağı al
        top_items = related_items[:5]
        sources_text = self._format_sources(top_items)

        prompt = f"""Konu: "{keyword}"
Hesap niş'i: {niche}

Haber kaynakları:
{sources_text}

Yukarıdaki kaynakları analiz et ve aşağıdaki JSON formatında araştırma notu üret:
{{
  "main_finding": "Ana bulguyu tek net cümleyle yaz",
  "supporting_facts": ["Detay 1", "Detay 2", "Detay 3"],
  "source_credibility": 8.5,
  "novelty_score": 7.0,
  "suggested_angle": "informative|engaging|how-to|breaking",
  "language_of_sources": "en|tr|mixed"
}}

Sadece JSON döndür."""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.SYSTEM_PROMPT,
                model=ModelTier.QUALITY,
                max_tokens=600,
            )

            note = ResearchNote(
                keyword=keyword,
                main_finding=data.get("main_finding", ""),
                supporting_facts=data.get("supporting_facts", []),
                source_urls=[item.url for item in top_items if item.url],
                source_credibility=float(data.get("source_credibility", 7.0)),
                novelty_score=float(data.get("novelty_score", 5.0)),
                suggested_angle=data.get("suggested_angle", "informative"),
                language_of_sources=data.get("language_of_sources", "en"),
                raw_sources=[f"{item.source_name}: {item.title}" for item in top_items],
            )

            log.info(
                "researcher_done",
                keyword=keyword,
                credibility=note.source_credibility,
                novelty=note.novelty_score,
                angle=note.suggested_angle,
            )
            return note

        except Exception as e:
            log.warning("researcher_failed", keyword=keyword, error=str(e))
            return self._empty_note(keyword)

    def _format_sources(self, items: list[RSSItem]) -> str:
        parts = []
        for i, item in enumerate(items, 1):
            parts.append(
                f"[{i}] {item.source_name} ({item.language.upper()})\n"
                f"Başlık: {item.title}\n"
                f"Özet: {item.content[:300]}\n"
            )
        return "\n".join(parts)

    def _empty_note(self, keyword: str) -> ResearchNote:
        return ResearchNote(
            keyword=keyword,
            main_finding=keyword,
            supporting_facts=[],
            source_urls=[],
            source_credibility=5.0,
            novelty_score=5.0,
            suggested_angle="informative",
            language_of_sources="mixed",
        )
