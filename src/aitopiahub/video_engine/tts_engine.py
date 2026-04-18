"""Quality-oriented TTS engine: XTTS local CPU -> Edge -> Piper."""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

import aiohttp
import edge_tts
from pydub import AudioSegment
from pydub.effects import compress_dynamic_range, high_pass_filter, normalize, strip_silence

from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# Character-based voice maps (Edge TTS)
CHARACTER_VOICES = {
    "tr": {"narrator": "tr-TR-AhmetNeural", "kid": "tr-TR-EmelNeural", "wise": "tr-TR-AhmetNeural"},
    "en": {"narrator": "en-US-AndrewNeural", "kid": "en-US-ChristopherNeural", "wise": "en-US-EricNeural"},
}

# Character speaker hints (XTTS)
CHARACTER_SPEAKER_PRESETS = {
    "tr": {"narrator": "male", "kid": "female", "wise": "male"},
    "en": {"narrator": "male", "kid": "female", "wise": "male"},
}


class TTSEngine:
    """Text-to-speech with strict quality-first fallback policy."""

    def __init__(self, output_dir: Path | str = "./data/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings = get_settings()
        self.last_provider_used: str = "unknown"

    async def generate(
        self,
        text: str,
        lang: str = "tr",
        filename: str | None = None,
        character: str = "narrator",
        providers_override: list[str] | None = None,
    ) -> Path:
        """Generate speech and return created file path."""
        normalized_lang = (lang or "en").lower()
        normalized_character = (character or "narrator").lower()
        voice = CHARACTER_VOICES.get(normalized_lang, CHARACTER_VOICES["en"]).get(
            normalized_character,
            CHARACTER_VOICES.get(normalized_lang, CHARACTER_VOICES["en"])["narrator"],
        )

        if not filename:
            h = hashlib.md5(f"{text}{voice}{normalized_lang}".encode()).hexdigest()[:10]
            filename = f"tts_{normalized_lang}_{normalized_character}_{h}.wav"
        output_path = self.output_dir / filename

        providers = self._provider_order(providers_override=providers_override)
        last_error: Exception | None = None
        for provider in providers:
            try:
                if provider == "elevenlabs":
                    raw_path = output_path.with_name(output_path.stem + "_elevenlabs.mp3")
                    produced = await self._generate_elevenlabs(text, normalized_lang, raw_path)
                elif provider == "xtts_local":
                    raw_path = output_path.with_name(output_path.stem + "_xtts.wav")
                    produced = await self._generate_xtts(text, normalized_lang, normalized_character, raw_path)
                elif provider == "edge":
                    raw_path = output_path.with_name(output_path.stem + "_edge.mp3")
                    produced = await self._generate_edge(text, voice, raw_path, normalized_lang, normalized_character)
                elif provider == "piper":
                    raw_path = output_path.with_name(output_path.stem + "_piper.wav")
                    produced = await self._generate_piper(text, normalized_lang, raw_path)
                else:
                    continue

                self.last_provider_used = provider
                return self._post_process_audio(produced, output_path)
            except Exception as exc:
                last_error = exc
                log.warning("tts_provider_failed", provider=provider, error=str(exc))

        raise RuntimeError(f"TTS failed for all providers: {last_error}")

    def _provider_order(self, providers_override: list[str] | None = None) -> list[str]:
        if providers_override:
            normalized: list[str] = []
            for provider in providers_override:
                p = (provider or "").strip().lower()
                if p and p not in normalized:
                    normalized.append(p)
            if normalized:
                return normalized

        primary = (self.settings.tts_provider_primary or "xtts_local").strip().lower()
        secondary = (self.settings.tts_provider_secondary or "edge").strip().lower()
        fallback = (self.settings.tts_provider_fallback or "piper").strip().lower()
        order: list[str] = []
        for candidate in (primary, secondary, fallback):
            if candidate and candidate not in order:
                order.append(candidate)
        return order

    async def _generate_elevenlabs(self, text: str, lang: str, output_path: Path) -> Path:
        api_key = (self.settings.elevenlabs_api_key or "").strip()
        if not api_key:
            raise RuntimeError("missing_elevenlabs_api_key")

        if lang == "tr":
            voice_id = (self.settings.elevenlabs_voice_tr or "").strip()
        else:
            voice_id = (self.settings.elevenlabs_voice_en or "").strip()
        if not voice_id:
            raise RuntimeError(f"missing_elevenlabs_voice_for_{lang}")

        model_id = (self.settings.elevenlabs_model_id or "eleven_multilingual_v2").strip()
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.82,
                "style": 0.2,
                "use_speaker_boost": True,
            },
        }
        timeout = aiohttp.ClientTimeout(total=40)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"elevenlabs_http_{resp.status}:{body[:200]}")
                output_path.write_bytes(await resp.read())
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("elevenlabs_empty_audio")
        return output_path

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

    async def _generate_xtts(self, text: str, lang: str, character: str, output_path: Path) -> Path:
        model_path = (self.settings.xtts_model_path or "").strip()
        if not model_path:
            raise RuntimeError("XTTS model path is not configured")
        model = Path(model_path)
        if not model.exists():
            raise RuntimeError(f"XTTS model file does not exist: {model}")

        # Keep sentence chunks short for stable CPU inference.
        chunks = self._split_sentences(text, max_chars=220)
        if not chunks:
            raise RuntimeError("empty_tts_text")

        tts_binary = (self.settings.xtts_binary or "tts").strip()
        speaker_hint = CHARACTER_SPEAKER_PRESETS.get(lang, CHARACTER_SPEAKER_PRESETS["en"]).get(character, "male")
        rendered_chunks: list[Path] = []
        for i, chunk in enumerate(chunks):
            part = output_path.with_name(f"{output_path.stem}_part_{i:02d}.wav")
            proc = await asyncio.create_subprocess_exec(
                tts_binary,
                "--model_path",
                str(model),
                "--text",
                chunk,
                "--out_path",
                str(part),
                "--speaker_idx",
                speaker_hint,
                "--language_idx",
                lang,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"XTTS synthesis failed (code={proc.returncode}): {(stderr or stdout).decode('utf-8', errors='ignore')[:280]}"
                )
            if not part.exists() or part.stat().st_size == 0:
                raise RuntimeError(f"XTTS chunk failed: {i}")
            rendered_chunks.append(part)

        combined = AudioSegment.silent(duration=0)
        for chunk_path in rendered_chunks:
            combined += AudioSegment.from_file(chunk_path)
            combined += AudioSegment.silent(duration=70)
        combined.export(output_path, format="wav")
        for chunk_path in rendered_chunks:
            try:
                chunk_path.unlink(missing_ok=True)
            except Exception:
                pass
        return output_path

    def _post_process_audio(self, input_path: Path, output_path: Path) -> Path:
        """Normalize + de-harsh + trim silences for kid-friendly narration."""
        seg = AudioSegment.from_file(input_path)
        seg = normalize(seg)
        seg = compress_dynamic_range(seg, threshold=-22.0, ratio=3.0, attack=8.0, release=100.0)
        seg = high_pass_filter(seg, cutoff=80)
        seg = seg.low_pass_filter(7600)
        seg = strip_silence(seg, silence_len=500, silence_thresh=-38, padding=120)
        seg.export(output_path, format="wav")
        if input_path != output_path:
            try:
                input_path.unlink(missing_ok=True)
            except Exception:
                pass
        return output_path

    def _split_sentences(self, text: str, max_chars: int = 220) -> list[str]:
        stripped = (text or "").strip()
        if not stripped:
            return []
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", stripped) if s.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_chars:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return chunks

    def _piper_model_for_lang(self, lang: str) -> str:
        if lang == "tr":
            return self.settings.piper_model_tr_path
        if lang == "en":
            return self.settings.piper_model_en_path
        return self.settings.piper_model_en_path
