"""Free-first TTS engine: Edge primary + Piper offline fallback."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import edge_tts

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# Character-based voice maps (Edge TTS)
CHARACTER_VOICES = {
    "tr": {
        "narrator": "tr-TR-AhmetNeural",
        "kid": "tr-TR-EmelNeural",
        "wise": "tr-TR-AhmetNeural",
    },
    "en": {
        "narrator": "en-US-AndrewNeural",
        "kid": "en-US-ChristopherNeural",
        "wise": "en-US-EricNeural",
    },
}


class TTSEngine:
    """Text-to-speech with strict free-mode fallback policy."""

    def __init__(self, output_dir: Path | str = "./data/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings = get_settings()

    async def generate(
        self,
        text: str,
        lang: str = "tr",
        filename: str | None = None,
        character: str = "narrator",
    ) -> Path:
        """Generate speech and return created file path."""
        normalized_lang = (lang or "en").lower()
        voice = CHARACTER_VOICES.get(normalized_lang, CHARACTER_VOICES["en"]).get(
            character.lower(),
            CHARACTER_VOICES.get(normalized_lang, CHARACTER_VOICES["en"])["narrator"],
        )

        if not filename:
            h = hashlib.md5(f"{text}{voice}".encode()).hexdigest()[:8]
            filename = f"tts_{normalized_lang}_{character}_{h}.mp3"
        output_path = self.output_dir / filename

        primary = (self.settings.tts_provider_primary or "edge").strip().lower()
        fallback = (self.settings.tts_provider_fallback or "piper").strip().lower()

        providers = [primary]
        if fallback and fallback != primary:
            providers.append(fallback)

        last_error: Exception | None = None
        for provider in providers:
            try:
                if provider == "edge":
                    return await self._generate_edge(text, voice, output_path, normalized_lang, character)
                if provider == "piper":
                    piper_output = output_path.with_suffix(".wav")
                    return await self._generate_piper(text, normalized_lang, piper_output)
                log.warning("unknown_tts_provider", provider=provider)
            except Exception as exc:
                last_error = exc
                log.warning("tts_provider_failed", provider=provider, error=str(exc))

        raise RuntimeError(f"TTS failed for all providers: {last_error}")

    async def _generate_edge(
        self,
        text: str,
        voice: str,
        output_path: Path,
        lang: str,
        character: str,
    ) -> Path:
        log.info("generating_tts_edge", lang=lang, character=character, voice=voice)
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return output_path

    async def _generate_piper(self, text: str, lang: str, output_path: Path) -> Path:
        model_path = self._piper_model_for_lang(lang)
        if not model_path:
            raise RuntimeError(f"Piper model is not configured for language: {lang}")

        model = Path(model_path)
        if not model.exists():
            raise RuntimeError(f"Piper model file does not exist: {model}")

        binary = (self.settings.piper_binary or "piper").strip()
        log.info("generating_tts_piper", lang=lang, model=str(model), output=str(output_path))

        proc = await asyncio.create_subprocess_exec(
            binary,
            "--model",
            str(model),
            "--output_file",
            str(output_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(
                f"Piper synthesis failed (code={proc.returncode}): {(stderr or stdout).decode('utf-8', errors='ignore')[:300]}"
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Piper synthesis did not produce audio")
        return output_path

    def _piper_model_for_lang(self, lang: str) -> str:
        if lang == "tr":
            return self.settings.piper_model_tr_path
        if lang == "en":
            return self.settings.piper_model_en_path
        return self.settings.piper_model_en_path
