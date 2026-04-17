"""
YouTube Shorts yayınlama Celery task'ları.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aitopiahub.tasks.celery_app import app
from aitopiahub.core.config import AccountConfig
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.publisher.youtube_client import YouTubeClient
from aitopiahub.video_engine.tts_engine import TTSEngine
from aitopiahub.video_engine.assembly_engine import AssemblyEngine
from aitopiahub.content_engine.content_formats import ContentFormatBuilder

log = get_logger(__name__)

@app.task(name="aitopiahub.tasks.youtube_tasks.generate_and_publish_shorts")
def generate_and_publish_shorts(account_handle: str, trend_data_json: str):
    """Trend verisinden YouTube Shorts üret ve yayınla."""
    return asyncio.run(_generate_youtube_async(account_handle, trend_data_json))

async def _generate_youtube_async(account_handle: str, trend_data_json: str):
    config = AccountConfig.for_account(account_handle)
    trend_data = json.loads(trend_data_json)
    
    tts = TTSEngine()
    assembly = AssemblyEngine()
    yt_client = YouTubeClient(enabled=True)
    builder = ContentFormatBuilder()
    
    # Diller: TR ve EN
    languages = ["tr", "en"]
    results = []

    for lang in languages:
        log.info("starting_youtube_short_generation", lang=lang, keyword=trend_data.get("keyword"))
        
        # 1. Script oluştur (Şimdilik basitleştirilmiş, Localizer eklenebilir)
        # TODO: PostGenerator ile gerçek TR/EN script üretimi
        caption = trend_data.get("caption", "AI Dünyasında Bugün")
        script = builder.build_short_script(caption)
        
        # 2. Seslendirme üret
        voiceover_text = " ".join(script.voiceover_lines)
        audio_path = await tts.generate(voiceover_text, lang=lang)
        
        # 3. Görseller (Mevcut image_urls'leri kullanıyoruz)
        image_urls = trend_data.get("image_urls", [])
        if not image_urls:
             # Fallback placeholder veya hata
             log.warning("no_images_for_video", lang=lang)
             continue
        
        # Yerel path'lere çevirme gerekebilir (ImageStore üzerinden)
        # Şimdilik image_paths olarak varsayalım (veya indirilmiş halleri)
        image_paths = trend_data.get("image_paths", [])
        
        # 4. Video Montaj
        video_filename = f"short_{account_handle}_{lang}_{trend_data.get('draft_id')}.mp4"
        video_path = await assembly.create_short(
            image_paths=image_paths,
            audio_path=audio_path,
            output_filename=video_filename,
            subtitles=script.voiceover_lines
        )
        
        # 5. Yayınla (Dry-run)
        publish_res = await yt_client.publish_short(
            title=script.title_hook,
            description=f"{caption}\n\n#ai #tech #shorts",
            video_path=str(video_path),
            tags=["ai", "tech", lang],
            dry_run=True
        )
        
        results.append({
            "lang": lang,
            "video_url": publish_res.url,
            "status": "dry_run_success"
        })

    return results
