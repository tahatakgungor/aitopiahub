from __future__ import annotations

from pathlib import Path

import pytest

from aitopiahub.core.config import get_settings
from aitopiahub.video_engine.tts_engine import TTSEngine


@pytest.mark.asyncio
async def test_tts_engine_falls_back_to_piper(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TTS_PROVIDER_PRIMARY", "edge")
    monkeypatch.setenv("TTS_PROVIDER_FALLBACK", "piper")
    monkeypatch.setenv("PIPER_MODEL_TR_PATH", str(tmp_path / "tr.onnx"))
    (tmp_path / "tr.onnx").write_bytes(b"model")
    get_settings.cache_clear()

    engine = TTSEngine(output_dir=tmp_path)

    async def _fail_edge(*args, **kwargs):
        raise RuntimeError("edge_403")

    async def _ok_piper(*args, **kwargs):
        out = tmp_path / "fallback.wav"
        out.write_bytes(b"audio")
        return out

    monkeypatch.setattr(engine, "_generate_edge", _fail_edge)
    monkeypatch.setattr(engine, "_generate_piper", _ok_piper)
    monkeypatch.setattr(engine, "_post_process_audio", lambda input_path, output_path: input_path)

    output = await engine.generate("Merhaba", lang="tr", character="narrator")
    assert output.suffix == ".wav"
    assert output.exists()
