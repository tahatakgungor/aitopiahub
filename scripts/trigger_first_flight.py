"""
First Flight: Aitopiahub'ın profesyonel çocuk içeriği testini üretip yükler.
"""

import asyncio
import os
from pathlib import Path
from PIL import Image

# MoviePy 1.0.3 + Pillow 10+ compatibility fix
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = getattr(Image, 'Resampling', Image).LANCZOS

from aitopiahub.core.config import AccountConfig, get_settings
from aitopiahub.core.logging import get_logger
from aitopiahub.content_engine.llm_client import ModelTier, LLMClient
from aitopiahub.content_engine.agents.researcher import ResearchNote
from aitopiahub.content_engine.agents.writer import WriterAgent
from aitopiahub.content_engine.agents.localizer import LocalizerAgent
from aitopiahub.core.constants import PostFormat, ContentAngle
from aitopiahub.image_engine.pollinations_provider import PollinationsProvider
from aitopiahub.image_engine.image_store import ImageStore
from aitopiahub.video_engine.tts_engine import TTSEngine
from aitopiahub.video_engine.assembly_engine import AssemblyEngine
from aitopiahub.publisher.youtube_client import YouTubeClient

log = get_logger(__name__)

async def trigger_first_flight(account_handle: str):
    log.info("kids_flight_initiated", account=account_handle)
    
    config = AccountConfig.for_account(account_handle)
    llm = LLMClient()
    # Çocuk kanalına özel persona
    writer = WriterAgent(llm, persona="kids_storyteller")
    localizer = LocalizerAgent(llm)
    
    img_provider = PollinationsProvider()
    img_store = ImageStore()
    tts = TTSEngine()
    assembly = AssemblyEngine()
    yt_client = YouTubeClient(enabled=True)
    
    # Arka plan müziği yolu
    bg_music = "assets/music/happy_kids.mp3"
    
    # 1. Trend Belirleme (Çocuklar için ilginç bir bilgi)
    trend_topic = "Amazing Nature Facts: Why Elephants are Scared of Bees?"
    log.info("selected_kids_topic", topic=trend_topic)
    
    # Mock Research Note
    note = ResearchNote(
        keyword="Elephant vs Bees",
        main_finding="Even though elephants are giants, they are terrified of tiny bees because they can sting their sensitive trunks.",
        supporting_facts=[
            "Elephants have a unique 'bee alarm' call to warn their family.",
            "They can be scared away just by the sound of buzzing.",
            "Conservationists use beehive fences to protect farms from elephants peacefully.",
            "An elephant's skin is thick, but its trunk has thousands of nerve endings."
        ],
        source_urls=["https://www.nature.com/articles/news.2007.151"],
        source_credibility=10,
        novelty_score=9.0,
        suggested_angle="informative",
        language_of_sources="en"
    )

    # 2. İçerik ve Script Üretimi (SHORT_SCRIPT formatında)
    # Persona zaten writer constructor'da verildi.
    writer_out = await writer.write(
        note,
        post_format=PostFormat.SHORT_SCRIPT,
        angle=ContentAngle.INFORMATIVE,
        language="en"
    )
    
    localized = await localizer.localize(writer_out, primary_language="tr")
    
    # TR ve EN dilleri için döngü
    languages = [
        ("tr", localized.tr_caption, localized.tr_slide_texts),
        ("en", localized.en_caption, localized.en_slide_texts)
    ]
    
    final_urls = []

    for lang, caption, scenes in languages:
        log.info("processing_language", lang=lang)
        
        if not scenes:
            log.warning("no_scenes_found", lang=lang)
            continue

        # 3. Görsel Üretimi (Her sahne için ayrı prompt)
        image_paths = []
        subtitles = []
        voiceover_parts = []
        
        for scene in scenes:
            prompt = scene.get("image_prompt", writer_out.image_prompt_hint)
            # Çocuklar için Pixar stilini garanti et
            if "Pixar" not in prompt:
                prompt = f"Pixar style 3D animation, {prompt}, vibrant colors, high detail"
            
            txt = scene.get("text", "")
            
            log.info("generating_kids_scene", index=scene.get("index"), prompt=prompt[:50])
            img_data = await img_provider.generate(prompt, size="story")
            
            if img_data:
                storage_path, _ = await img_store.save(img_data, account_handle, subfolder=f"kids_flight_{lang}")
                image_paths.append(storage_path)
                subtitles.append(txt)
                voiceover_parts.append(txt)
        
        if not image_paths:
            log.error("image_generation_failed", lang=lang)
            continue
            
        # 4. Audio (Çocuk tonunda tts seçilebilir, varsayılan devam edelim)
        text_to_speak = " ".join(voiceover_parts)
        audio_path = await tts.generate(text_to_speak, lang=lang)
        
        # 5. Video Render (Assembly)
        video_filename = f"kids_pro_{account_handle}_{lang}.mp4"
        video_path = await assembly.create_short(
            image_paths=image_paths,
            audio_path=audio_path,
            output_filename=video_filename,
            subtitles=subtitles,
            bg_music_path=bg_music
        )
        
        # 6. YouTube Upload (REAL)
        title_hook = caption.split("\n")[0][:100]
        # Eğer emoji varsa ve title çok kısaysa süsle
        if "🐘" not in title_hook: title_hook += " 🐘🐝"
        
        log.info("uploading_kids_video", lang=lang, video=video_filename)
        
        result = await yt_client.publish_short(
            title=title_hook,
            description=f"{caption}\n\n#kids #nature #funfacts #elephant #education #aitopiahub #{lang}",
            video_path=str(video_path),
            tags=["kids", "animals", "education", "fun facts", lang],
            dry_run=False
        )
        
        final_urls.append({"lang": lang, "url": result.url})
        log.info("upload_complete", lang=lang, url=result.url)

    return final_urls

if __name__ == "__main__":
    account = "aitopiahub_news"
    asyncio.run(trigger_first_flight(account))
