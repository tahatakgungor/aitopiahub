"""
Reddit API'den hot/rising postları çeker.
PRAW kütüphanesi — ücretsiz, OAuth2 gerektirmez (read-only).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import praw

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# AI/Tech için takip edilecek subreddit'ler
AI_TECH_SUBREDDITS = [
    "artificial",
    "MachineLearning",
    "technology",
    "singularity",
    "OpenAI",
    "ChatGPT",
    "LocalLLaMA",
    "StableDiffusion",
    "tech",
]


@dataclass
class RedditPost:
    subreddit: str
    title: str
    url: str
    score: int
    num_comments: int
    upvote_ratio: float
    created_at: datetime
    keywords: list[str] = field(default_factory=list)


class RedditFetcher:
    """Reddit hot/rising postlarını çeker."""

    def __init__(self, subreddits: list[str] | None = None):
        self.subreddits = subreddits or AI_TECH_SUBREDDITS
        settings = get_settings()
        self._reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

    async def fetch_hot(self, limit: int = 10) -> list[RedditPost]:
        return await asyncio.to_thread(self._fetch_sync, limit)

    def _fetch_sync(self, limit: int) -> list[RedditPost]:
        posts: list[RedditPost] = []

        for sub_name in self.subreddits:
            try:
                sub = self._reddit.subreddit(sub_name)
                for submission in sub.hot(limit=limit):
                    if submission.is_self and not submission.selftext:
                        continue
                    if submission.score < 50:
                        continue

                    posts.append(
                        RedditPost(
                            subreddit=sub_name,
                            title=submission.title,
                            url=submission.url,
                            score=submission.score,
                            num_comments=submission.num_comments,
                            upvote_ratio=submission.upvote_ratio,
                            created_at=datetime.fromtimestamp(submission.created_utc),
                        )
                    )
            except Exception as e:
                log.warning("reddit_fetch_error", subreddit=sub_name, error=str(e))

        log.info("reddit_fetch_complete", count=len(posts))
        return posts
