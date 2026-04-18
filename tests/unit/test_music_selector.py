from __future__ import annotations

import json
from pathlib import Path

from aitopiahub.video_engine.music_selector import MusicSelector


def test_music_selector_choose_tracks(tmp_path: Path) -> None:
    music = tmp_path / "track.mp3"
    music.write_bytes(b"fake")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": "t1",
                        "path": str(music),
                        "mood": "playful",
                        "energy": 0.8,
                        "safe_tags": ["kids", "safe"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    selector = MusicSelector(manifest_path=str(manifest))
    picks = selector.choose_tracks(mood="playful", target_duration=180)
    assert len(picks) == 1
    assert picks[0].track_id == "t1"
