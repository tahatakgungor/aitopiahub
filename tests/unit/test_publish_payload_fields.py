from __future__ import annotations

from aitopiahub.core.config import get_settings
from aitopiahub.tasks.publish_tasks import _normalize_image_urls


def test_normalize_image_urls_supports_relative_paths(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://89.45.45.232:8010")
    get_settings.cache_clear()

    result = _normalize_image_urls([
        "/images/a.jpg",
        "images/b.jpg",
        "https://cdn.example.com/c.jpg",
    ])

    assert result[0] == "http://89.45.45.232:8010/images/a.jpg"
    assert result[1] == "http://89.45.45.232:8010/images/b.jpg"
    assert result[2] == "https://cdn.example.com/c.jpg"
