"""Kid-safe music pool selector with simple mood matching."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from aitopiahub.core.config import BASE_DIR, get_settings


@dataclass
class MusicTrack:
    track_id: str
    path: str
    mood: str
    energy: float
    safe_tags: list[str]


class MusicSelector:
    def __init__(self, manifest_path: str | None = None):
        settings = get_settings()
        rel = manifest_path or settings.music_pool_manifest
        path = Path(rel)
        if not path.is_absolute():
            path = (BASE_DIR / rel).resolve()
        self.manifest_path = path
        self._tracks = self._load_manifest(path)

    @property
    def tracks(self) -> list[MusicTrack]:
        return list(self._tracks)

    def choose_tracks(self, mood: str, target_duration: float, max_changes: int = 2) -> list[MusicTrack]:
        """Return one or more tracks, allowing at most two segment changes."""
        if not self._tracks:
            return []
        normalized = (mood or "playful").strip().lower()
        pool = [t for t in self._tracks if t.mood == normalized]
        if not pool:
            pool = list(self._tracks)
        rng = random.Random(int(target_duration) + len(pool))
        first = rng.choice(pool)
        if max_changes <= 0 or target_duration < 180:
            return [first]
        # For longer videos, blend at most two transitions (max 3 tracks).
        count = 2 if target_duration < 420 else 3
        count = min(count, max_changes + 1, len(pool))
        selected = [first]
        candidates = [x for x in pool if x.track_id != first.track_id]
        rng.shuffle(candidates)
        selected.extend(candidates[: max(0, count - 1)])
        return selected

    def _load_manifest(self, path: Path) -> list[MusicTrack]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        tracks = payload.get("tracks") if isinstance(payload, dict) else []
        parsed: list[MusicTrack] = []
        for item in tracks or []:
            if not isinstance(item, dict):
                continue
            track_id = str(item.get("id") or "").strip()
            path_value = str(item.get("path") or "").strip()
            if not track_id or not path_value:
                continue
            p = Path(path_value)
            if not p.is_absolute():
                p = (BASE_DIR / path_value).resolve()
            parsed.append(
                MusicTrack(
                    track_id=track_id,
                    path=str(p),
                    mood=str(item.get("mood") or "playful").strip().lower(),
                    energy=float(item.get("energy") or 0.5),
                    safe_tags=[str(x).strip().lower() for x in (item.get("safe_tags") or []) if str(x).strip()],
                )
            )
        return parsed
