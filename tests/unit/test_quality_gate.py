from __future__ import annotations

import wave
from pathlib import Path

from aitopiahub.video_engine.quality_gate import QualityGate


def _write_wave(path: Path, seconds: float = 0.5, framerate: int = 16000) -> None:
    nframes = int(seconds * framerate)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes((b"\x01\x00" * nframes))


def test_quality_gate_blocks_missing_music(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    video = tmp_path / "v.mp4"
    _write_wave(audio)
    video.write_bytes(b"\x00" * (6 * 1024 * 1024))
    gate = QualityGate()
    result = gate.evaluate(
        scene_data=[
            {
                "audio_path": str(audio),
                "text": "red riding hood forest friendship",
                "asset_query": "forest friendship kids animation",
                "visual_provider_used": "pexels",
            }
        ],
        video_path=video,
        music_track_id=None,
    )
    assert result.passed is False
    assert result.failed_layer == "music"
