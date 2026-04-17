"""YouTube publisher adapter (Faz-2 hazırlık)."""

from __future__ import annotations

from dataclasses import dataclass

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class YouTubePublishResult:
    video_id: str
    url: str


class YouTubeClient:
    """Faz-2 için adapter iskeleti. Şimdilik dry-run ve payload validasyonu yapar."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    async def publish_short(
        self,
        title: str,
        description: str,
        video_path: str,
        tags: list[str] | None = None,
        dry_run: bool = True,
    ) -> YouTubePublishResult:
        if dry_run or not self.enabled:
            log.info(
                "youtube_publish_dry_run",
                title=title[:60],
                video_path=video_path,
                tags=len(tags or []),
            )
            return YouTubePublishResult(video_id="dry_run", url="https://youtube.com/shorts/dry_run")

        raise NotImplementedError("YouTube publish entegrasyonu Faz-2'de aktive edilecek")
