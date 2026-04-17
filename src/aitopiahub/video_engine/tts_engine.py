"""
Microsoft Edge TTS motoru.
Ücretsiz, yüksek kaliteli ve TR/EN destekli.
"""

from __future__ import annotations

import asyncio
import edge_tts
from pathlib import Path

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# Karakter bazlı ses eşlemeleri
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
    }
}

class TTSEngine:
    """Metinleri sese dönüştüren motor."""

    def __init__(self, output_dir: Path | str = "./data/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(
        self, 
        text: str, 
        lang: str = "tr", 
        filename: str | None = None,
        character: str = "narrator"
    ) -> Path:
        """
        Metni sese çevirir ve dosya yolunu döner.
        """
        # Ses seçimi: Spesifik karakter sesi veya dilin varsayılanı
        lang_voices = CHARACTER_VOICES.get(lang.lower(), CHARACTER_VOICES["en"])
        voice = lang_voices.get(character.lower(), lang_voices["narrator"])
        
        if not filename:
            import hashlib
            h = hashlib.md5(f"{text}{voice}".encode()).hexdigest()[:8]
            filename = f"tts_{lang}_{character}_{h}.mp3"
        
        output_path = self.output_dir / filename
        
        log.info("generating_tts", lang=lang, character=character, voice=voice)
        
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        
        if not output_path.exists():
            raise RuntimeError(f"TTS üretilemedi: {output_path}")
            
        return output_path
