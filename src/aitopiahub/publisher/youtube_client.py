"""YouTube publisher adapter (Faz-2 hazırlık)."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import os

from aitopiahub.core.config import get_settings
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

    async def publish_video(
        self,
        title: str,
        description: str,
        video_path: str,
        tags: list[str] | None = None,
        is_short: bool = False,
        made_for_kids: bool = True,
        dry_run: bool = True,
    ) -> YouTubePublishResult:
        """Video dosyasını YouTube'a yükler."""
        if dry_run or not self.enabled:
            log.info("youtube_publish_dry_run", title=title[:40], video=video_path)
            return YouTubePublishResult(video_id="dry_run", url=f"file://{video_path}")

        # Real upload logic
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials

        settings = get_settings()
        creds = Credentials(
            token=None,
            refresh_token=settings.youtube_refresh_token,
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )

        try:
            youtube = build("youtube", "v3", credentials=creds)
            
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description,
                    "tags": tags or [],
                    "categoryId": "1"  # Film & Animation for high quality kids content
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": made_for_kids
                }
            }

            insert_request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
            )

            response = await asyncio.to_thread(insert_request.execute)
            video_id = response.get("id")
            
            log.info("youtube_publish_success", video_id=video_id, title=title[:40])
            
            url = f"https://youtube.com/shorts/{video_id}" if is_short else f"https://youtube.com/watch?v={video_id}"
            return YouTubePublishResult(
                video_id=video_id,
                url=url
            )

        except Exception as e:
            log.error("youtube_publish_failed", error=str(e))
            raise e
