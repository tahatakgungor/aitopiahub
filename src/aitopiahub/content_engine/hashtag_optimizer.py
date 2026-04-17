"""
Hashtag seçim ve sıralama motoru.
Engagement geçmişine göre ağırlıklandırılmış seçim.
Büyük + orta + küçük hashtag karışımı (Instagram best practice).
"""

from __future__ import annotations

from aitopiahub.core.config import AccountConfig
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# Aitopiahub News için varsayılan hashtag setleri
DEFAULT_HASHTAGS = {
    "large": [  # 10M+ post — geniş erişim
        "AI", "ArtificialIntelligence", "Technology", "Tech", "Innovation",
        "MachineLearning", "DeepLearning", "Future", "Digital",
    ],
    "medium": [  # 100K-10M post — niche erişim
        "AINews", "TechNews", "YapayZeka", "Teknoloji", "OpenAI",
        "ChatGPT", "LLM", "GenerativeAI", "AITurkey", "TechTurkey",
        "Robotics", "DataScience", "Python", "MLOps",
    ],
    "small": [  # <100K post — yüksek engage oranı
        "AIToplulugu", "YapayZekaHaberleri", "TurkishTech",
        "AItopiahub", "TeknolojiHaberleri",
    ],
}

# Strateji: 5 büyük + 8 orta + 5 küçük = 18 hashtag
STRATEGY = {"large": 5, "medium": 8, "small": 5}


class HashtagOptimizer:
    """
    Trend keyword ve geçmiş performansa göre optimal hashtag seti seçer.
    """

    def __init__(self, config: AccountConfig):
        self.config = config
        # Gerçekte Redis'ten okunur — burada default ağırlıklar
        self._weights: dict[str, float] = {}
        self._seed_tags = [
            self._clean(k) for k in config.seed_keywords if k and len(k.strip()) > 1
        ]

    async def optimize(
        self,
        suggested: list[str],
        keyword: str,
        max_tags: int = 18,
    ) -> list[str]:
        """Optimal hashtag listesi döndür."""

        result: list[str] = []
        seen: set[str] = set()

        # 1. Önce önerilen hashtag'leri değerlendir
        cleaned_suggested = [self._clean(h) for h in suggested if h]
        cleaned_suggested = [h for h in cleaned_suggested if h and len(h) <= 30]
        ranked_suggested = sorted(
            cleaned_suggested,
            key=lambda t: self._weights.get(t, 0.5),
            reverse=True,
        )
        for tag in ranked_suggested[:6]:
            if tag not in seen:
                result.append(tag)
                seen.add(tag)

        # 2. Keyword'e özel hashtag ekle
        keyword_tag = self._clean(keyword.replace(" ", ""))
        if keyword_tag and keyword_tag not in seen:
            result.append(keyword_tag)
            seen.add(keyword_tag)

        # 3. Hesabın seed keyword'lerinden 2 güçlü etiket ekle
        for tag in self._seed_tags[:2]:
            if tag not in seen:
                result.append(tag)
                seen.add(tag)

        # 4. Kategorilerden tamamla
        for size, count in STRATEGY.items():
            needed = count - sum(
                1 for tag in result
                if self._tag_size(tag) == size
            )
            if needed <= 0:
                continue
            pool = [
                t for t in DEFAULT_HASHTAGS.get(size, [])
                if t not in seen
            ]
            # Ağırlığa göre sırala
            pool.sort(key=lambda t: self._weights.get(t, 0.5), reverse=True)
            for tag in pool[:needed]:
                if tag not in seen:
                    result.append(tag)
                    seen.add(tag)

        # Toplam limitle sınırla
        final = result[:max_tags]
        log.debug("hashtag_optimizer_done", count=len(final), keyword=keyword)
        return final

    def set_weights(self, weights: dict[str, float]) -> None:
        """Feedback loop'tan gelen hashtag performans ağırlıklarını yükle."""
        cleaned = {}
        for tag, score in weights.items():
            ctag = self._clean(tag)
            if ctag:
                cleaned[ctag] = max(0.0, min(float(score), 2.0))
        self._weights = cleaned

    def update_weights(self, hashtag: str, engagement_rate: float) -> None:
        """Engagement sonuçlarına göre ağırlık güncelle (feedback loop)."""
        current = self._weights.get(hashtag, 0.5)
        # Exponential moving average
        self._weights[hashtag] = 0.7 * current + 0.3 * min(engagement_rate * 10, 1.0)

    def _clean(self, tag: str) -> str:
        return tag.strip().lstrip("#").replace(" ", "")

    def _tag_size(self, tag: str) -> str:
        for size, tags in DEFAULT_HASHTAGS.items():
            if tag in tags:
                return size
        return "medium"
