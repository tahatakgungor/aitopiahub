"""YouTube publisher adapter with upload + insights support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class YouTubePublishResult:
    video_id: str
    url: str


class YouTubeClient:
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
        if dry_run or not self.enabled:
            log.info("youtube_publish_dry_run", title=title[:40], video=video_path)
            return YouTubePublishResult(video_id="dry_run", url=f"file://{video_path}")

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        settings = get_settings()
        creds = Credentials(
            token=None,
            refresh_token=settings.youtube_refresh_token,
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags or [],
                "categoryId": "1",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }

        try:
            youtube = build("youtube", "v3", credentials=creds)
            insert_request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
            )
            response = await asyncio.to_thread(insert_request.execute)
            video_id = str(response.get("id") or "")
            if not video_id:
                raise RuntimeError("youtube returned empty video id")

            url = (
                f"https://youtube.com/shorts/{video_id}"
                if is_short
                else f"https://youtube.com/watch?v={video_id}"
            )
            log.info("youtube_publish_success", video_id=video_id, title=title[:40])
            return YouTubePublishResult(video_id=video_id, url=url)
        except HttpError as exc:
            raw = str(exc)
            if "quotaExceeded" in raw or "dailyLimitExceeded" in raw:
                raise RuntimeError("YouTube quota exceeded") from exc
            log.error("youtube_publish_failed", error=raw)
            raise
        except Exception as exc:
            log.error("youtube_publish_failed", error=str(exc))
            raise

    async def publish_short(
        self,
        title: str,
        description: str,
        video_path: str,
        tags: list[str] | None = None,
        made_for_kids: bool = True,
        dry_run: bool = True,
    ) -> YouTubePublishResult:
        """Backward-compatible wrapper used by old shorts tasks."""
        return await self.publish_video(
            title=title,
            description=description,
            video_path=video_path,
            tags=tags,
            is_short=True,
            made_for_kids=made_for_kids,
            dry_run=dry_run,
        )

    async def get_video_insights(self, video_id: str) -> dict:
        """Fetch lightweight public metrics for a published video."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        settings = get_settings()
        creds = Credentials(
            token=None,
            refresh_token=settings.youtube_refresh_token,
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )

        youtube = build("youtube", "v3", credentials=creds)
        request = youtube.videos().list(part="statistics,contentDetails", id=video_id)
        response = await asyncio.to_thread(request.execute)
        items = response.get("items", [])
        if not items:
            return {}

        stats = items[0].get("statistics", {})
        details = items[0].get("contentDetails", {})
        return {
            "video_id": video_id,
            "views": int(stats.get("viewCount", 0) or 0),
            "likes": int(stats.get("likeCount", 0) or 0),
            "comments": int(stats.get("commentCount", 0) or 0),
            "duration": details.get("duration"),
        }
