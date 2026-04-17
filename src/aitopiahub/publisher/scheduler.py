"""
Optimal posting zaman hesaplama.
Engagement verilerine göre peak saatler önceliklendirilir.
Yüksek velocity trendler en erken slota atlar.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aitopiahub.core.config import AccountConfig
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


class OptimalScheduler:
    """
    Günlük posting slotlarını hesaplar.
    TR kitlesi default peak: [9, 12, 17, 20, 22]
    """

    def __init__(self, config: AccountConfig):
        self.config = config
        # Tarihsel engagement rate per hour (Redis'ten okunur, burada default)
        self._hour_weights: dict[int, float] = {
            h: (2.5 if h in config.peak_hours else 1.0)
            for h in range(7, 24)
        }

    def next_slot(
        self,
        occupied_times: list[datetime],
        trend_score: float = 0.5,
    ) -> datetime:
        """
        Bir sonraki optimal posting zamanını döndür.
        trend_score > 0.8 ise en erken müsait slota atlar.
        """
        now_utc = datetime.now(timezone.utc)
        tz = ZoneInfo(self.config.timezone)
        now_local = now_utc.astimezone(tz)

        candidates = self._generate_candidates(now_local)
        available = self._filter_available(candidates, occupied_times)

        if not available:
            # Tüm slotlar dolu → yarın ilk slot
            tomorrow = now_local + timedelta(days=1)
            first_slot = tomorrow.replace(
                hour=int(self.config.posting_window_start.split(":")[0]),
                minute=random.randint(0, 30),
                second=0,
                microsecond=0,
            )
            log.info("scheduler_tomorrow", slot=str(first_slot))
            return first_slot.astimezone(timezone.utc)

        # Yüksek velocity → en erken slota zıpla
        if trend_score > 0.8:
            chosen = min(available)
            log.info("scheduler_high_velocity", slot=str(chosen), score=trend_score)
        else:
            # Önce peak saatleri dene, strict ise sadece onlar arasında seç.
            peak_candidates = [dt for dt in available if dt.hour in self.config.peak_hours]
            if peak_candidates:
                chosen = max(peak_candidates, key=lambda dt: self._weight(dt.hour))
            elif self.config.strict_peak_hours:
                chosen = min(available)
            else:
                chosen = max(available, key=lambda dt: self._weight(dt.hour))
            log.info("scheduler_normal", slot=str(chosen), hour=chosen.hour)

        # UTC'ye çevir
        return chosen.astimezone(timezone.utc)

    def _generate_candidates(self, now_local: datetime) -> list[datetime]:
        """Bugünkü posting window içindeki tüm candidate slotları üret."""
        start_h = int(self.config.posting_window_start.split(":")[0])
        end_h = int(self.config.posting_window_end.split(":")[0])

        candidates = []
        for h in range(start_h, end_h + 1):
            # Her saat için 2 slot: başı ve ortası
            for m in [0, 30]:
                slot = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
                if slot > now_local + timedelta(minutes=5):
                    candidates.append(slot)
        return candidates

    def _filter_available(
        self, candidates: list[datetime], occupied: list[datetime]
    ) -> list[datetime]:
        """Min gap kuralını uygula."""
        min_gap = timedelta(minutes=self.config.min_gap_minutes)
        available = []
        for slot in candidates:
            if all(abs((slot - occ).total_seconds()) >= min_gap.total_seconds()
                   for occ in occupied):
                available.append(slot)
        return available

    def _weight(self, hour: int) -> float:
        return self._hour_weights.get(hour, 1.0)

    def update_hour_weight(self, hour: int, engagement_rate: float) -> None:
        """Engagement sonuçlarına göre saat ağırlığını güncelle."""
        current = self._hour_weights.get(hour, 1.0)
        # Exponential moving average
        new_weight = 0.7 * current + 0.3 * (engagement_rate * 5.0)
        self._hour_weights[hour] = max(0.5, min(new_weight, 5.0))
