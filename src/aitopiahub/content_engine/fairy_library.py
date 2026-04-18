"""Fairy tale library loader and deterministic picker."""

from __future__ import annotations

import datetime
import random
from pathlib import Path
from typing import Any

import yaml


class FairyLibrary:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._stories: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._stories = []
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        stories = data.get("stories", [])
        if isinstance(stories, list):
            self._stories = [s for s in stories if isinstance(s, dict) and s.get("id")]
        else:
            self._stories = []

    @property
    def stories(self) -> list[dict[str, Any]]:
        return list(self._stories)

    def get_story_for_today(self, story_weights: dict[str, float] | None = None) -> dict[str, Any] | None:
        if not self._stories:
            return None

        day_of_year = datetime.datetime.now().timetuple().tm_yday
        rng = random.Random(day_of_year)

        if not story_weights:
            return self._stories[day_of_year % len(self._stories)]

        weighted = []
        for story in self._stories:
            story_id = str(story.get("id"))
            raw_weight = story_weights.get(story_id, 1.0)
            weight = min(max(float(raw_weight), 0.2), 5.0)
            weighted.append((story, weight))

        population = [item[0] for item in weighted]
        weights = [item[1] for item in weighted]
        return rng.choices(population, weights=weights, k=1)[0]

    def build_internal_candidates(self, topic_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fairy = [
            {
                "mode": "fairy_tale",
                "id": story.get("id"),
                "title": story.get("title"),
                "theme": story.get("theme"),
                "age_band": story.get("age_band"),
            }
            for story in self._stories[:5]
        ]
        demand = [
            {
                "mode": "demand_driven",
                "id": topic.get("keyword"),
                "title": topic.get("keyword"),
                "theme": "demand",
            }
            for topic in topic_candidates[:5]
        ]
        return fairy + demand
