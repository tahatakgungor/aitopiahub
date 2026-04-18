"""Learning agent that updates topic/hook/hour preferences from live metrics."""

from __future__ import annotations

import json
from collections import defaultdict

from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis

log = get_logger(__name__)


class FeedbackAgent:
    """Analyze engagement signals and persist lightweight preferences."""

    def __init__(self, account_handle: str):
        self.account_handle = account_handle

    async def analyze_and_optimize(self, youtube_stats: dict, instagram_stats: dict) -> dict:
        log.info("intelligence_loop_started", account=self.account_handle)
        redis = get_redis()

        metrics = await self._load_metrics(redis)
        if len(metrics) < 3:
            log.info("intelligence_loop_not_enough_data", account=self.account_handle)
            return {"updated": False, "reason": "insufficient_data"}

        topic_scores: dict[str, list[float]] = defaultdict(list)
        mode_scores: dict[str, list[float]] = defaultdict(list)
        story_scores: dict[str, list[float]] = defaultdict(list)
        hook_scores: dict[str, list[float]] = defaultdict(list)
        hour_scores: dict[int, list[float]] = defaultdict(list)

        for row in metrics:
            score = float(row.get("weighted_score", 0.0) or 0.0)
            keyword = str(row.get("keyword", "")).strip()
            if keyword:
                topic_scores[keyword].append(score)
            mode = str(row.get("content_mode") or "demand_driven")
            mode_scores[mode].append(score)
            story_id = str(row.get("story_id") or "").strip()
            if story_id:
                story_scores[story_id].append(score)

            hook = str(row.get("title") or row.get("hook_text") or "").strip()
            if hook:
                hook_scores[hook[:140]].append(score)

            published_at = str(row.get("published_at") or "")
            if published_at:
                try:
                    hour = int(published_at[11:13])
                    hour_scores[hour].append(score)
                except Exception:
                    pass

        await self._merge_topic_weights(redis, topic_scores)
        await self._merge_mode_scores(redis, mode_scores)
        await self._merge_story_scores(redis, story_scores)
        await self._merge_hook_scores(redis, hook_scores)
        await self._merge_hour_scores(redis, hour_scores)

        log.info("intelligence_loop_finished", account=self.account_handle)
        return {
            "updated": True,
            "topics": len(topic_scores),
            "hooks": len(hook_scores),
            "hours": len(hour_scores),
        }

    async def _load_metrics(self, redis) -> list[dict]:
        rows: list[dict] = []
        keys = await redis.keys("metrics:*")
        for key in keys:
            raw = await redis.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("account") != self.account_handle:
                continue

            metric_id = str(data.get("metric_id") or "")
            published_raw = await redis.get(f"published_youtube:{metric_id}") or await redis.get(
                f"published_instagram:{metric_id}"
            )
            if not published_raw:
                continue
            try:
                published = json.loads(published_raw)
            except json.JSONDecodeError:
                continue
            rows.append({**published, "weighted_score": data.get("weighted_score", 0.0)})
        return rows

    async def _merge_topic_weights(self, redis, topic_scores: dict[str, list[float]]) -> None:
        key = f"feedback:topic_weights:{self.account_handle}"
        payload: dict[str, float] = {}
        for topic, scores in topic_scores.items():
            if len(scores) < 2:
                continue
            payload[topic] = min(max(sum(scores) / len(scores) * 8.0, 0.2), 5.0)
        if payload:
            await redis.hset(key, mapping=payload)
            await redis.expire(key, 30 * 86400)

    async def _merge_hook_scores(self, redis, hook_scores: dict[str, list[float]]) -> None:
        key = f"feedback:hook_bank:{self.account_handle}"
        if not hook_scores:
            return
        pipe = redis.pipeline()
        for hook, scores in hook_scores.items():
            if len(scores) < 2:
                continue
            pipe.zadd(key, {hook: sum(scores) / len(scores)})
        pipe.expire(key, 30 * 86400)
        await pipe.execute()

    async def _merge_mode_scores(self, redis, mode_scores: dict[str, list[float]]) -> None:
        key = f"feedback:mode_weights:{self.account_handle}"
        payload: dict[str, float] = {}
        for mode, scores in mode_scores.items():
            if len(scores) < 2:
                continue
            payload[mode] = min(max(sum(scores) / len(scores) * 10.0, 0.2), 5.0)
        if payload:
            await redis.hset(key, mapping=payload)
            await redis.expire(key, 30 * 86400)

    async def _merge_story_scores(self, redis, story_scores: dict[str, list[float]]) -> None:
        key = f"feedback:story_weights:{self.account_handle}"
        payload: dict[str, float] = {}
        for story_id, scores in story_scores.items():
            if len(scores) < 2:
                continue
            payload[story_id] = min(max(sum(scores) / len(scores) * 10.0, 0.2), 5.0)
        if payload:
            await redis.hset(key, mapping=payload)
            await redis.expire(key, 30 * 86400)

    async def _merge_hour_scores(self, redis, hour_scores: dict[int, list[float]]) -> None:
        key = f"feedback:hour_weights:{self.account_handle}"
        payload: dict[str, float] = {}
        for hour, scores in hour_scores.items():
            if len(scores) < 2:
                continue
            payload[str(hour)] = min(max(sum(scores) / len(scores) * 10.0, 0.5), 5.0)
        if payload:
            await redis.hset(key, mapping=payload)
            await redis.expire(key, 30 * 86400)
