from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from aitopiahub.content_engine.episode_manager import EpisodeManager


@dataclass
class _FakeYtResult:
    video_id: str
    url: str


@dataclass
class _FakeIgResult:
    media_id: str
    permalink: str | None = None


@pytest.mark.asyncio
async def test_episode_manager_run_daily_flow_returns_url(monkeypatch, tmp_path: Path) -> None:
    class _FakeWriterOutput:
        caption_text = "Uzay Macerası"
        image_prompt_hint = "space kids"
        slide_texts = [{"text": "Merhaba çocuklar", "speaker": "narrator", "image_prompt": "space"}]

    class _FakeWriter:
        async def write(self, *args, **kwargs):
            return _FakeWriterOutput()

    class _FakeRefiner:
        async def refine(self, text: str):
            return text

    class _FakeImgProvider:
        async def generate(self, *args, **kwargs):
            return b"img"

    class _FakeStore:
        async def save(self, *args, **kwargs):
            p = tmp_path / "scene.jpg"
            p.write_bytes(b"img")
            return p, "http://localhost/images/scene.jpg"

    class _FakeTts:
        async def generate(self, *args, **kwargs):
            p = tmp_path / "scene.wav"
            p.write_bytes(b"audio")
            return p

    class _FakeAssembly:
        async def create_episode(self, *args, **kwargs):
            p = tmp_path / "episode.mp4"
            p.write_bytes(b"video")
            return p

        async def create_teaser(self, *args, **kwargs):
            p = tmp_path / "teaser.mp4"
            p.write_bytes(b"video")
            return p

    class _FakeYt:
        async def publish_video(self, *args, **kwargs):
            return _FakeYtResult(video_id="vid123", url="https://youtube.com/watch?v=vid123")

    class _FakeIg:
        async def publish_reel(self, *args, **kwargs):
            return _FakeIgResult(media_id="ig123")

    class _FakeRedis:
        async def hgetall(self, *args, **kwargs):
            return {}

        async def setex(self, *args, **kwargs):
            return True

    monkeypatch.setattr("aitopiahub.content_engine.episode_manager.get_redis", lambda: _FakeRedis())

    manager = EpisodeManager("aitopiahub_kids")
    manager.writer = _FakeWriter()
    manager.refiner = _FakeRefiner()
    manager.img_provider = _FakeImgProvider()
    manager.img_store = _FakeStore()
    manager.tts = _FakeTts()
    manager.assembly = _FakeAssembly()
    manager.yt_client = _FakeYt()
    manager.ig_client = _FakeIg()

    result = await manager.run_daily_flow(lang="tr")
    assert result == "https://youtube.com/watch?v=vid123"
