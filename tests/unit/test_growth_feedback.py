from __future__ import annotations

import asyncio

from aitopiahub.core.config import get_settings
from aitopiahub.image_engine.image_store import ImageStore
from aitopiahub.tasks.engagement_tasks import _weighted_score


def test_weighted_score_prioritizes_saves_and_shares() -> None:
    base = _weighted_score(likes=40, comments=5, saves=2, shares=1, impressions=1000)
    improved = _weighted_score(likes=40, comments=5, saves=8, shares=4, impressions=1000)
    assert improved > base
    assert improved > 0


def test_image_store_returns_absolute_public_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://89.45.45.232:8010")
    get_settings.cache_clear()

    store = ImageStore()
    _, public_url = asyncio.run(
        store.save(
            image_bytes=b"fake-image",
            account_id="aitopiahub_news",
            filename="demo.jpg",
            subfolder="test",
        )
    )

    assert public_url == "http://89.45.45.232:8010/images/aitopiahub_news/test/demo.jpg"
