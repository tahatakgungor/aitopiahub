"""Kids content calendar with optional weight-based topic prioritization."""

from __future__ import annotations

import datetime
import random

TOPICS = [
    {"keyword": "Güneş Sistemi", "finding": "Gezegenlerin isimleri, büyüklükleri ve ilginç özellikleri."},
    {"keyword": "Dinozorlar Alemi", "finding": "T-Rex'ten Triceratops'a kadar en meşhur dinozorlar ve yaşamları."},
    {"keyword": "Okyanusun Derinlikleri", "finding": "Mavi balinalar, köpekbalıkları ve parlayan derin deniz canlıları."},
    {"keyword": "Vücudumuzun Sırları", "finding": "Kalp nasıl atar? Beynimiz nasıl düşünür? İskeletimiz ne işe yarar?"},
    {"keyword": "Mısır Piramitleri", "finding": "Piramitler nasıl yapıldı? Firavunlar kimdi? Mumyalar nedir?"},
    {"keyword": "Ormandaki Dostlarımız", "finding": "Aslanlar, filler ve zürafaların ormandaki gizli yaşamı."},
    {"keyword": "Uzay Yolculuğu", "finding": "Astronotlar ne yer? Roketler nasıl uçar? Ay'da yürümek nasıl bir his?"},
    {"keyword": "İyilik ve Yardımseverlik", "finding": "Küçük bir iyiliğin dünyayı nasıl değiştirebileceğine dair bir hikaye."},
    {"keyword": "Doğayı Koruyalım", "finding": "Geri dönüşüm nedir? Ağaçlar neden nefes almamızı sağlar?"},
    {"keyword": "Böceklerin Mikro Dünyası", "finding": "Karıncaların gücü, arıların bal yapma serüveni."},
]


class ContentCalendar:
    @staticmethod
    def get_topic_for_today(topic_weights: dict[str, float] | None = None) -> dict:
        """Select topic deterministically per day, biased by learned weights."""
        day_of_year = datetime.datetime.now().timetuple().tm_yday
        if not topic_weights:
            index = day_of_year % len(TOPICS)
            return TOPICS[index]

        rng = random.Random(day_of_year)
        weighted_topics = []
        for topic in TOPICS:
            keyword = topic["keyword"]
            raw_weight = topic_weights.get(keyword, 1.0)
            weight = min(max(float(raw_weight), 0.2), 5.0)
            weighted_topics.append((topic, weight))

        population = [item[0] for item in weighted_topics]
        weights = [item[1] for item in weighted_topics]
        return rng.choices(population, weights=weights, k=1)[0]

    @staticmethod
    def build_demand_candidates(topic_weights: dict[str, float] | None = None, limit: int = 6) -> list[dict]:
        weighted = []
        for topic in TOPICS:
            keyword = topic["keyword"]
            raw_weight = (topic_weights or {}).get(keyword, 1.0)
            weight = min(max(float(raw_weight), 0.2), 5.0)
            weighted.append(
                {
                    "mode": "demand_driven",
                    "keyword": keyword,
                    "finding": topic["finding"],
                    "weight": weight,
                }
            )
        weighted.sort(key=lambda x: x["weight"], reverse=True)
        return weighted[:limit]
