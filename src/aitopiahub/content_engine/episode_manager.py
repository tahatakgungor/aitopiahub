"""Episode Manager for long-form kids content production."""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path

from aitopiahub.content_engine.agents.native_refiner import NativeRefinerAgent
from aitopiahub.content_engine.agents.researcher import ResearchNote
from aitopiahub.content_engine.agents.writer import WriterAgent
from aitopiahub.content_engine.content_calendar import ContentCalendar
from aitopiahub.content_engine.fairy_library import FairyLibrary
from aitopiahub.content_engine.llm_client import LLMClient
from aitopiahub.core.config import BASE_DIR, AccountConfig, get_settings
from aitopiahub.core.constants import ContentAngle, PostFormat
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.image_engine.image_store import ImageStore
from aitopiahub.image_engine.pollinations_provider import PollinationsProvider
from aitopiahub.image_engine.template_renderer import TemplateRenderer
from aitopiahub.publisher.instagram_client import InstagramClient
from aitopiahub.publisher.youtube_client import YouTubeClient
from aitopiahub.video_engine.assembly_engine import AssemblyEngine
from aitopiahub.video_engine.tts_engine import TTSEngine

log = get_logger(__name__)


class EpisodeManager:
    def __init__(self, account_handle: str):
        self.account_handle = account_handle
        self.account_config = AccountConfig.for_account(account_handle)
        self.llm = LLMClient()
        self.writer = WriterAgent(self.llm, persona="kids_storyteller")
        self.refiner = NativeRefinerAgent(self.llm)
        self.img_provider = PollinationsProvider()
        self.img_store = ImageStore()
        self.template_renderer = TemplateRenderer()
        self.tts = TTSEngine()
        self.assembly = AssemblyEngine()
        self.yt_client = YouTubeClient(enabled=True)
        self.ig_client = InstagramClient()
        self.settings = get_settings()
        fairy_path = Path(self.settings.fairy_library_path)
        if not fairy_path.is_absolute():
            fairy_path = (BASE_DIR / fairy_path).resolve()
        self.fairy_library = FairyLibrary(fairy_path)
        self.log_file = Path("data/production.log")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _log_status(self, message: str) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as file:
            file.write(log_entry)
        log.info(message)

    async def _topic_weights(self) -> dict[str, float]:
        redis = get_redis()
        raw = await redis.hgetall(f"feedback:topic_weights:{self.account_handle}")
        weights: dict[str, float] = {}
        for topic, value in raw.items():
            try:
                weights[str(topic)] = float(value)
            except (TypeError, ValueError):
                continue
        return weights

    async def _story_weights(self) -> dict[str, float]:
        redis = get_redis()
        raw = await redis.hgetall(f"feedback:story_weights:{self.account_handle}")
        weights: dict[str, float] = {}
        for story_id, value in raw.items():
            try:
                weights[str(story_id)] = float(value)
            except (TypeError, ValueError):
                continue
        return weights

    async def _store_publish_records(
        self,
        *,
        lang: str,
        keyword: str,
        content_mode: str,
        story_id: str | None,
        title: str,
        scene_count: int,
        youtube_video_id: str,
        youtube_url: str,
        instagram_media_id: str | None,
        instagram_permalink: str | None,
    ) -> None:
        redis = get_redis()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        yt_payload = {
            "account": self.account_handle,
            "platform": "youtube",
            "video_id": youtube_video_id,
            "url": youtube_url,
            "published_at": now,
            "lang": lang,
            "keyword": keyword,
            "content_mode": content_mode,
            "story_id": story_id,
            "title": title,
            "scene_count": scene_count,
        }
        await redis.setex(f"published_youtube:{youtube_video_id}", 30 * 86400, json.dumps(yt_payload))

        if instagram_media_id:
            ig_payload = {
                "account": self.account_handle,
                "platform": "instagram",
                "media_id": instagram_media_id,
                "permalink": instagram_permalink,
                "published_at": now,
                "lang": lang,
                "keyword": keyword,
                "content_mode": content_mode,
                "story_id": story_id,
                "title": title,
                "scene_count": scene_count,
            }
            await redis.setex(f"published_instagram:{instagram_media_id}", 30 * 86400, json.dumps(ig_payload))

    async def _store_internal_candidates(self, topic_weights: dict[str, float]) -> None:
        redis = get_redis()
        topic_candidates = ContentCalendar.build_demand_candidates(topic_weights=topic_weights, limit=8)
        candidates = self.fairy_library.build_internal_candidates(topic_candidates)
        await redis.setex(
            f"content_candidates:{self.account_handle}",
            12 * 3600,
            json.dumps({"items": candidates, "generated_at": datetime.datetime.utcnow().isoformat()}),
        )

    async def run_daily_flow(self, lang: str = "tr", content_mode: str = "demand_driven") -> str | None:
        self._log_status(f"Bölüm üretim döngüsü başlatıldı. Dil: {lang}")

        topic_weights = await self._topic_weights()
        await self._store_internal_candidates(topic_weights)
        mode = (content_mode or "demand_driven").strip().lower()
        story_id: str | None = None

        if mode == "fairy_tale":
            story = self.fairy_library.get_story_for_today(await self._story_weights())
            if story:
                story_id = str(story.get("id"))
                topic_data = {
                    "keyword": str(story.get("title") or "Klasik Çocuk Hikayesi"),
                    "finding": str(story.get("moral") or "Bugün birlikte güzel bir masal öğreneceğiz."),
                    "story": story,
                }
            else:
                mode = "demand_driven"
                topic_data = ContentCalendar.get_topic_for_today(topic_weights=topic_weights)
        else:
            topic_data = ContentCalendar.get_topic_for_today(topic_weights=topic_weights)
        note = ResearchNote(
            keyword=topic_data["keyword"],
            main_finding=topic_data["finding"],
            supporting_facts=[],
            source_urls=[],
            source_credibility=10,
            novelty_score=10.0,
            suggested_angle="story",
            language_of_sources="en",
        )

        self._log_status(f"Senaryo yazılıyor: {note.keyword}...")
        writer_out = await self.writer.write(
            note,
            post_format=PostFormat.LONG_EPISODE,
            angle=ContentAngle.INFORMATIVE,
            language=lang,
            content_mode=mode,
            story_profile=topic_data.get("story"),
            fairy_style=self.settings.fairy_style,
        )

        if not writer_out or not writer_out.slide_texts:
            self._log_status("HATA: Senaryo üretilemedi (LLM boş cevap döndü).")
            return None

        self._log_status(f"Senaryo hazır. {len(writer_out.slide_texts)} sahne oluşturuldu.")

        if lang == "tr":
            self._log_status("Türkçe dil kalitesi artırılıyor (NativeRefiner)...")
            for i, scene in enumerate(writer_out.slide_texts):
                original = scene.get("text", "")
                scene["text"] = await self.refiner.refine(original)
                self._log_status(f"Sahne {i + 1} cilalandı.")
                await asyncio.sleep(1)

        self._log_status("Görsel ve Ses varlıkları üretiliyor...")
        scene_data: list[dict] = []
        for i, scene in enumerate(writer_out.slide_texts):
            prompt = str(scene.get("image_prompt") or writer_out.image_prompt_hint or note.keyword)
            if "Pixar" not in prompt:
                prompt = f"Pixar style 3D animation, {prompt}, vibrant colors, high detail"

            img_data = None
            for attempt in range(3):
                self._log_status(
                    f"Sahne {i + 1}/{len(writer_out.slide_texts)} - Görsel üretiliyor (Deneme {attempt + 1})..."
                )
                img_data = await self.img_provider.generate(prompt, size="story")
                if img_data:
                    break
                await asyncio.sleep(2)

            if not img_data:
                self._log_status(f"UYARI: Sahne {i + 1} için Pollinations başarısız, template fallback kullanılıyor.")
                try:
                    fallback_text = scene.get("text") or note.keyword
                    img_data = self.template_renderer.render_breaking_news(
                        headline=fallback_text[:90],
                        subtext=note.keyword,
                    )
                except Exception:
                    if scene_data:
                        img_data = Path(scene_data[-1]["image_path"]).read_bytes()
                    else:
                        img_data = await self.img_provider.generate(
                            "Pixar style 3D cute kids background",
                            size="story",
                        )
            if not img_data:
                raise RuntimeError(f"Image generation failed for scene {i + 1}")

            storage_path, _ = await self.img_store.save(
                img_data,
                self.account_handle,
                subfolder=f"episode_{lang}",
            )

            speaker = str(scene.get("speaker", "narrator")).lower()
            self._log_status(
                f"Sahne {i + 1}/{len(writer_out.slide_texts)} - Ses üretiliyor ({speaker})..."
            )
            audio_path = await self.tts.generate(
                scene.get("text", ""),
                lang=lang,
                character=speaker,
            )

            scene_data.append(
                {
                    "image_path": str(storage_path),
                    "audio_path": str(audio_path),
                    "text": scene.get("text", ""),
                }
            )

        self._log_status("Video montajı ve sahne birleştirme işlemi başlıyor...")
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output_filename = f"episode_{lang}_{stamp}.mp4"
        bg_music = "assets/music/happy_kids.mp3"

        final_video_path = await self.assembly.create_episode(
            scene_data=scene_data,
            output_filename=output_filename,
            bg_music_path=bg_music,
        )

        raw_title = (writer_out.caption_text or note.keyword).split("\n")[0].strip()
        title = raw_title[:100] if raw_title else note.keyword[:100]
        self._log_status(f"Video yüklüyor: {title}")

        result = await self.yt_client.publish_video(
            title=title,
            description=f"{writer_out.caption_text}\n\n#kids #education #learning #merakliyumurcak",
            video_path=str(final_video_path),
            tags=["kids", "learning", "animals", lang],
            is_short=False,
            made_for_kids=True,
            dry_run=False,
        )

        self._log_status(f"YouTube bölümü başarıyla paylaşıldı: {result.url}")

        ig_media_id: str | None = None
        ig_permalink: str | None = None
        try:
            self._log_status("Instagram için fragman (Reels) üretiliyor...")
            teaser_filename = f"teaser_{lang}_{stamp}.mp4"
            await self.assembly.create_teaser(
                scene_data=scene_data,
                output_filename=teaser_filename,
                max_duration=60.0,
                bg_music_path=bg_music,
            )

            base_url = self.settings.public_base_url.rstrip("/")
            teaser_url = f"{base_url}/videos/{teaser_filename}"
            caption = (
                f"Yeni Bölüm Yayında: {title}\n\n"
                "Videonun tamamı için YouTube kanalımıza bekliyoruz.\n\n"
                "#merakliyumurcak #çocuk #eğitim #reels #kids"
            )

            self._log_status("Instagram Reels paylaşılıyor...")
            ig_reel = await self.ig_client.publish_reel(teaser_url, caption)
            ig_media_id = ig_reel.media_id
            ig_permalink = ig_reel.permalink
            self._log_status("Instagram paylaşımı tamamlandı.")
        except Exception as exc:
            self._log_status(f"UYARI: Instagram paylaşımı sırasında hata oluştu: {exc}")

        await self._store_publish_records(
            lang=lang,
            keyword=note.keyword,
            content_mode=mode,
            story_id=story_id,
            title=title,
            scene_count=len(scene_data),
            youtube_video_id=result.video_id,
            youtube_url=result.url,
            instagram_media_id=ig_media_id,
            instagram_permalink=ig_permalink,
        )

        return result.url

    async def run_automated_cycle(self) -> dict[str, str | None]:
        """Run sequential TR+EN cycle once."""
        languages = [self.account_config.language_primary, self.account_config.language_secondary]
        dedup_languages: list[str] = []
        for lang in languages:
            normalized = str(lang or "").lower().strip()
            if normalized and normalized not in dedup_languages:
                dedup_languages.append(normalized)
        if not dedup_languages:
            dedup_languages = ["tr", "en"]

        self._log_status("--- Otonom Çift Dilli Döngü Başlatılıyor ---")
        results: dict[str, str | None] = {}
        for lang in dedup_languages:
            try:
                url = await self.run_daily_flow(lang=lang)
                results[lang] = url
                await asyncio.sleep(5)
            except Exception as exc:
                self._log_status(f"HATA: {lang} üretimi başarısız: {exc}")
                results[lang] = None

        self._log_status(f"Döngü tamamlandı. Sonuçlar: {results}")
        return results


if __name__ == "__main__":
    settings = get_settings()
    manager = EpisodeManager(settings.account_handle)
    asyncio.run(manager.run_automated_cycle())
