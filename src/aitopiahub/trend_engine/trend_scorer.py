"""
Composite trend scoring algoritması.

Ham sinyalleri tek bir skor'a dönüştürür:
  raw_score = 0.30*google_trend + 0.25*news_mentions +
              0.25*velocity + 0.10*reddit + 0.10*keyword_match

Zaman azalması: score × e^(-0.12 × saat_geçen)
  → 5.8 saatte score yarıya iner
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class RawSignal:
    keyword: str
    google_trend_index: float = 0.0     # 0-100
    news_mentions: int = 0
    reddit_score: int = 0
    keyword_match_score: float = 0.0    # 0-1 (seed keywords benzerliği)
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prev_total_volume: int = 0          # 1 saat önceki hacim (velocity için)
    current_total_volume: int = 0


@dataclass
class ScoredTrend:
    keyword: str
    raw_score: float
    final_score: float
    google_trend_index: float
    news_mentions: int
    reddit_score: int
    velocity: float
    keyword_match_score: float
    hours_old: float
    first_seen_at: datetime


class TrendScorer:
    """
    Ağırlıklı composite trend skoru hesaplar.
    Tüm normalizasyon rolling 7-günlük max'a göre yapılır.
    """

    WEIGHTS = {
        "google_trend": 0.30,
        "news_mentions": 0.25,
        "velocity": 0.25,
        "reddit": 0.10,
        "keyword_match": 0.10,
    }
    DECAY_LAMBDA = 0.12     # Score 5.8 saatte yarıya iner
    MAX_VELOCITY_RATIO = 5.0  # Maksimum velocity oranı (5x büyüme = 1.0)

    # Rolling max değerleri (gerçekte Redis'ten okunur, burada default)
    _rolling_max = {
        "google_trend": 100.0,
        "news_mentions": 50.0,
        "reddit": 5000,
    }

    def score(self, signal: RawSignal) -> ScoredTrend:
        # Normalize
        google_norm = min(signal.google_trend_index / self._rolling_max["google_trend"], 1.0)
        news_norm = min(signal.news_mentions / self._rolling_max["news_mentions"], 1.0)
        reddit_norm = min(signal.reddit_score / self._rolling_max["reddit"], 1.0)

        # Velocity: son 1 saatteki büyüme oranı
        velocity = self._calc_velocity(
            signal.prev_total_volume, signal.current_total_volume
        )
        velocity_norm = min(velocity / self.MAX_VELOCITY_RATIO, 1.0)

        raw_score = (
            self.WEIGHTS["google_trend"] * google_norm
            + self.WEIGHTS["news_mentions"] * news_norm
            + self.WEIGHTS["velocity"] * velocity_norm
            + self.WEIGHTS["reddit"] * reddit_norm
            + self.WEIGHTS["keyword_match"] * signal.keyword_match_score
        )

        # Zaman azalması
        hours_old = self._hours_since(signal.first_seen_at)
        final_score = raw_score * math.exp(-self.DECAY_LAMBDA * hours_old)

        return ScoredTrend(
            keyword=signal.keyword,
            raw_score=raw_score,
            final_score=final_score,
            google_trend_index=signal.google_trend_index,
            news_mentions=signal.news_mentions,
            reddit_score=signal.reddit_score,
            velocity=velocity,
            keyword_match_score=signal.keyword_match_score,
            hours_old=hours_old,
            first_seen_at=signal.first_seen_at,
        )

    def score_batch(self, signals: list[RawSignal]) -> list[ScoredTrend]:
        """Tüm sinyalleri skorla ve büyükten küçüğe sırala."""
        self._update_rolling_max(signals)
        scored = [self.score(s) for s in signals]
        return sorted(scored, key=lambda x: x.final_score, reverse=True)

    def _calc_velocity(self, prev: int, current: int) -> float:
        if prev <= 0:
            return 0.0
        return max((current - prev) / prev, 0.0)

    def _hours_since(self, dt: datetime) -> float:
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        return delta.total_seconds() / 3600

    def _update_rolling_max(self, signals: list[RawSignal]) -> None:
        if signals:
            max_google = max(s.google_trend_index for s in signals)
            max_news = max(s.news_mentions for s in signals)
            max_reddit = max(s.reddit_score for s in signals)
            # Yavaş güncelle — ani spike'larda normalize bozulmasın
            self._rolling_max["google_trend"] = max(
                self._rolling_max["google_trend"] * 0.9, max_google
            )
            self._rolling_max["news_mentions"] = max(
                self._rolling_max["news_mentions"] * 0.9, max_news
            )
            self._rolling_max["reddit"] = max(
                self._rolling_max["reddit"] * 0.9, max_reddit
            )

    def is_high_velocity(self, trend: ScoredTrend) -> bool:
        """Acil paylaşım tetikleyici: çok hızlı büyüyen trend."""
        return trend.final_score > 0.80 and trend.velocity > 2.0
