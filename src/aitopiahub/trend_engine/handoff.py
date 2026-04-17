"""
Trend pipeline ile content pipeline arasındaki handoff yardımcıları.
"""

from __future__ import annotations

import json
from typing import Any


def build_mention_map(seed_keywords: list[str], text_blobs: list[str]) -> dict[str, int]:
    """Başlık metinlerinden seed keyword mention sayılarını çıkar."""
    mention_map = {kw.lower(): 0 for kw in seed_keywords}
    for text in text_blobs:
        text_lower = (text or "").lower()
        if not text_lower:
            continue
        for kw in seed_keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                mention_map[kw_lower] = mention_map.get(kw_lower, 0) + 1
    return mention_map


async def enqueue_new_trends(
    redis: Any,
    account_handle: str,
    trends: list[Any],
    max_per_cycle: int,
) -> int:
    """
    Trend çıktısını content pipeline'a aktar.
    - pending_trends listesi: kalıcı ve worker restart sonrası kaybolmaz
    - new_trend channel: anlık gözlem/telemetri için
    """
    selected = trends[:max_per_cycle]
    pending_key = f"pending_trends:{account_handle}"
    channel = f"new_trend:{account_handle}"

    for trend in selected:
        payload = json.dumps({"keyword": trend.keyword, "score": trend.final_score})
        await redis.rpush(pending_key, payload)
        await redis.publish(channel, payload)

    return len(selected)
