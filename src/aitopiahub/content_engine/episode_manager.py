"""
Episode Manager — Uzun Metraj Çocuk Kanalı Koordinatörü.
Görevi: Konu bulma, senaryo yazma, Türkçe cilalama, seslendirme ve render süreçlerini yönetmek.
"""

import asyncio
import os
import datetime
from pathlib import Path
from aitopiahub.core.logging import get_logger
from aitopiahub.content_engine.llm_client import LLMClient
from aitopiahub.content_engine.agents.researcher import ResearchNote
from aitopiahub.content_engine.agents.writer import WriterAgent
from aitopiahub.content_engine.agents.native_refiner import NativeRefinerAgent
from aitopiahub.content_engine.content_calendar import ContentCalendar
from aitopiahub.image_engine.pollinations_provider import PollinationsProvider
from aitopiahub.image_engine.image_store import ImageStore
from aitopiahub.video_engine.tts_engine import TTSEngine
from aitopiahub.video_engine.assembly_engine import AssemblyEngine
from aitopiahub.publisher.youtube_client import YouTubeClient
from aitopiahub.publisher.instagram_client import InstagramClient
from aitopiahub.core.constants import PostFormat, ContentAngle
from aitopiahub.core.config import get_settings

log = get_logger(__name__)

class EpisodeManager:
    def __init__(self, account_handle: str):
        self.account_handle = account_handle
        self.llm = LLMClient()
        self.writer = WriterAgent(self.llm, persona="kids_storyteller")
        self.refiner = NativeRefinerAgent(self.llm)
        self.img_provider = PollinationsProvider()
        self.img_store = ImageStore()
        self.tts = TTSEngine()
        self.assembly = AssemblyEngine()
        self.yt_client = YouTubeClient(enabled=True)
        self.ig_client = InstagramClient()
        self.settings = get_settings()
        self.log_file = Path("data/production.log")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _log_status(self, message: str):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
        log.info(message)

    async def run_daily_flow(self, lang: str = "tr"):
        self._log_status(f"Bölüm üretim döngüsü başlatıldı. Dil: {lang}")
        
        # 1. Konu Seçimi
        topic_data = ContentCalendar.get_topic_for_today()
        note = ResearchNote(
            keyword=topic_data["keyword"],
            main_finding=topic_data["finding"],
            supporting_facts=[],
            source_urls=[],
            source_credibility=10,
            novelty_score=10.0,
            suggested_angle="story",
            language_of_sources="en"
        )
        
        # 2. Senaryo Üretimi (Uzun Metraj)
        self._log_status(f"Senaryo yazılıyor: {note.keyword}...")
        writer_out = await self.writer.write(
            note, 
            post_format=PostFormat.LONG_EPISODE,
            angle=ContentAngle.INFORMATIVE,
            language=lang
        )
        self._log_status(f"Senaryo hazır. {len(writer_out.slide_texts)} sahne oluşturuldu.")
        
        # 3. Türkçe Cilalama (Sadece TR için)
        if lang == "tr":
            self._log_status("Türkçe dil kalitesi artırılıyor (NativeRefiner)...")
            for i, scene in enumerate(writer_out.slide_texts):
                original = scene["text"]
                scene["text"] = await self.refiner.refine(original)
                self._log_status(f"Sahne {i+1} cilalandı.")
                await asyncio.sleep(1) # Rate limit guard
        
        # 4. Varlık Üretimi (Resim ve Ses)
        self._log_status("Görsel ve Ses varlıkları üretiliyor...")
        scene_data = []
        for i, scene in enumerate(writer_out.slide_texts):
            # Resim (Retry ile)
            prompt = scene.get("image_prompt", writer_out.image_prompt_hint)
            if "Pixar" not in prompt:
                prompt = f"Pixar style 3D animation, {prompt}, vibrant colors, high detail"
            
            img_data = None
            for attempt in range(3):
                self._log_status(f"Sahne {i+1}/{len(writer_out.slide_texts)} - Görsel üretiliyor (Deneme {attempt+1})...")
                img_data = await self.img_provider.generate(prompt, size="story")
                if img_data:
                    break
                await asyncio.sleep(2)

            if not img_data:
                self._log_status(f"UYARI: Sahne {i+1} için görsel üretilemedi. Önceki görsel kullanılacak.")
                if scene_data:
                    img_data = Path(scene_data[-1]["image_path"]).read_bytes()
                else:
                    # Fallback to a plain color if absolutely nothing
                    img_data = await self.img_provider.generate("Pixar style 3D cute background", size="story")

            storage_path, _ = await self.img_store.save(img_data, self.account_handle, subfolder=f"episode_{lang}")
            
            # Ses (Karakter bazlı)
            speaker = scene.get("speaker", "narrator").lower()
            self._log_status(f"Sahne {i+1}/{len(writer_out.slide_texts)} - Ses üretiliyor ({speaker})...")
            audio_path = await self.tts.generate(
                scene["text"], 
                lang=lang, 
                character=speaker
            )
            
            scene_data.append({
                "image_path": str(storage_path),
                "audio_path": str(audio_path),
                "text": scene["text"]
            })
            
        # 5. Render (Episode Modu)
        self._log_status("Video montajı ve sahne birleştirme işlemi başlıyor...")
        output_filename = f"episode_{lang}_{datetime.datetime.now().strftime('%Y%m%d')}.mp4"
        bg_music = "assets/music/happy_kids.mp3"
        
        final_video_path = await self.assembly.create_episode(
            scene_data=scene_data,
            output_filename=output_filename,
            bg_music_path=bg_music
        )
        
        # 6. YouTube Upload (Video Olarak, Shorts Değil)
        title = writer_out.caption_text.split("\n")[0][:100]
        self._log_status(f"Video yüklüyor: {title}")
        
        result = await self.yt_client.publish_video(
            title=title,
            description=f"{writer_out.caption_text}\n\n#kids #education #learning #merakliyumurcak",
            video_path=str(final_video_path),
            tags=["kids", "learning", "animals", lang],
            is_short=False,
            made_for_kids=True,
            dry_run=False
        )
        
        self._log_status(f"Tebrikler! YouTube Bölümü başarıyla paylaşıldı: {result.url}")
        
        # 7. Instagram Entegrasyonu (Reels ve Carousel)
        try:
            self._log_status("Instagram için fragman (Reels) üretiliyor...")
            teaser_filename = f"teaser_{lang}_{datetime.datetime.now().strftime('%Y%m%d')}.mp4"
            teaser_path = await self.assembly.create_teaser(
                scene_data=scene_data,
                output_filename=teaser_filename,
                max_duration=60.0,
                bg_music_path=bg_music
            )
            
            # Instagram için public URL'ler (Meta API yerel path kabul etmez)
            base_url = self.settings.public_base_url.rstrip("/")
            teaser_url = f"{base_url}/videos/{teaser_filename}"
            
            caption = f"🚀 Yeni Bölüm Yayında: {title}\n\nVideonun tamamı ve daha fazlası için YouTube kanalımıza bekliyoruz! Link bioda. ☝️\n\n#merakliyumurcak #çocuk #eğitim #reels #kids"
            
            self._log_status("Instagram Reels paylaşılıyor...")
            ig_reel = await self.ig_client.publish_reel(teaser_url, caption)
            
            # Carousel: En iyi 7 görseli paylaş
            self._log_status("Instagram Carousel (Görsel sürprizi) hazırlanıyor...")
            top_images = []
            for scene in scene_data[:7]:
                # Resmin relative path'ini alıp public URL'e çevir
                img_rel = Path(scene["image_path"]).relative_to(Path(self.settings.storage_local_path))
                top_images.append(f"{base_url}/images/{img_rel}")
            
            await self.ig_client.publish_carousel(top_images, caption)
            self._log_status("Instagram paylaşımları tamamlandı!")
            
        except Exception as e:
            self._log_status(f"UYARI: Instagram paylaşımı sırasında bir hata oluştu: {str(e)}")

        return result.url

    async def run_automated_cycle(self):
        """
        Otonom döngü: Hem Türkçe hem İngilizce içerikleri ardışık üretir.
        """
        languages = ["tr", "en"]
        self._log_status("--- Otonom Çift Dilli Döngü Başlatılıyor ---")
        
        results = {}
        for lang in languages:
            try:
                url = await self.run_daily_flow(lang=lang)
                results[lang] = url
                # Diller arası kısa bekleme
                await asyncio.sleep(5)
            except Exception as e:
                self._log_status(f"HATA: {lang} üretimi başarısız: {str(e)}")
        
        self._log_status(f"Döngü tamamlandı. Sonuçlar: {results}")
        return results

if __name__ == "__main__":
    manager = EpisodeManager("aitopiahub_kids")
    asyncio.run(manager.run_automated_cycle())
