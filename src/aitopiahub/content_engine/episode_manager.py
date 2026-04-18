"""Episode Manager for long-form kids content production."""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import uuid
from pathlib import Path

from aitopiahub.content_engine.agents.native_refiner import NativeRefinerAgent
from aitopiahub.content_engine.agents.researcher import ResearchNote
from aitopiahub.content_engine.agents.writer import WriterAgent
from aitopiahub.content_engine.content_calendar import ContentCalendar
from aitopiahub.content_engine.fairy_library import FairyLibrary
from aitopiahub.content_engine.llm_client import LLMClient
from aitopiahub.core.config import BASE_DIR, AccountConfig, get_settings
from aitopiahub.core.constants import ContentAngle, PostFormat
from aitopiahub.core.exceptions import QualityGateError
from aitopiahub.core.logging import get_logger
from aitopiahub.core.redis_client import get_redis
from aitopiahub.image_engine.image_store import ImageStore
from aitopiahub.image_engine.pollinations_provider import PollinationsProvider
from aitopiahub.image_engine.stock_video_provider import StockVideoProvider
from aitopiahub.image_engine.template_renderer import TemplateRenderer
from aitopiahub.publisher.instagram_client import InstagramClient
from aitopiahub.publisher.youtube_client import YouTubeClient
from aitopiahub.video_engine.assembly_engine import AssemblyEngine
from aitopiahub.video_engine.cost_guard import CostGuard
from aitopiahub.video_engine.music_selector import MusicSelector
from aitopiahub.video_engine.quality_gate import QualityGate
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
        self.stock_video_provider = StockVideoProvider()
        self.img_store = ImageStore()
        self.template_renderer = TemplateRenderer()
        self.tts = TTSEngine()
        self.assembly = AssemblyEngine()
        self.cost_guard = CostGuard()
        self.music_selector = MusicSelector()
        self.quality_gate = QualityGate()
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
        voice_provider_used: str,
        visual_provider_used: str,
        music_track_id: str | None,
        quality_scores: dict[str, float],
        quality_passed: bool,
        estimated_cost_usd: float,
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
            "voice_provider_used": voice_provider_used,
            "visual_provider_used": visual_provider_used,
            "music_track_id": music_track_id,
            "quality_scores": quality_scores,
            "quality_passed": quality_passed,
            "estimated_cost_usd": estimated_cost_usd,
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
                "voice_provider_used": voice_provider_used,
                "visual_provider_used": visual_provider_used,
                "music_track_id": music_track_id,
                "quality_scores": quality_scores,
                "quality_passed": quality_passed,
                "estimated_cost_usd": estimated_cost_usd,
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

    async def _download_video_bytes(self, url: str) -> bytes | None:
        import aiohttp

        if not url:
            return None
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.read()
        except Exception:
            return None

    async def _render_scene_assets(
        self,
        *,
        scene: dict,
        index: int,
        total: int,
        note: ResearchNote,
        lang: str,
    ) -> tuple[Path, Path | None, str, str]:
        prompt = str(scene.get("image_prompt") or note.keyword)
        asset_query = str(scene.get("asset_query") or prompt or note.keyword)
        mood = str(scene.get("mood") or "playful")

        self._log_status(f"Sahne {index}/{total} - Stok video aranıyor...")
        visual_provider = "kids_fallback"
        video_path: Path | None = None
        stock = await self.stock_video_provider.fetch(query=asset_query, mood=mood)
        if stock:
            raw_video = await self._download_video_bytes(stock.url)
            if raw_video:
                stored_video_path, _ = await self.img_store.save(
                    raw_video,
                    self.account_handle,
                    subfolder=f"episode_{lang}_video",
                    filename=f"{uuid.uuid4().hex}.mp4",
                )
                video_path = Path(stored_video_path)
                visual_provider = stock.provider

        img_data = None
        for attempt in range(2):
            self._log_status(f"Sahne {index}/{total} - AI görsel üretiliyor (Deneme {attempt + 1})...")
            img_data = await self.img_provider.generate(prompt, size="story")
            if img_data:
                visual_provider = self.settings.visual_provider_ai
                break
            await asyncio.sleep(1)
        if not img_data:
            img_data = self.template_renderer.render_kids_scene(
                title=str(scene.get("text") or note.keyword)[:120],
                subtitle=asset_query[:90],
                mood=mood,
            )
            visual_provider = "kids_fallback"

        storage_path, _ = await self.img_store.save(
            img_data,
            self.account_handle,
            subfolder=f"episode_{lang}",
        )
        return Path(storage_path), video_path, visual_provider, asset_query

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

        self._log_status("Görsel, ses ve kalite katmanı çalışıyor...")
        scene_data: list[dict] = []
        voice_provider_used = "unknown"
        visual_providers_seen: set[str] = set()

        total_chars = sum(len(str(scene.get("text") or "")) for scene in writer_out.slide_texts)
        budget_decision = self.cost_guard.evaluate_tts_budget(total_chars)
        if budget_decision.premium_allowed:
            tts_order = [
                self.settings.tts_provider_premium,
                self.settings.tts_provider_primary,
                self.settings.tts_provider_secondary,
                self.settings.tts_provider_fallback,
            ]
            self._log_status(
                f"Premium ses modu aktif (tahmini maliyet: ${budget_decision.estimated_cost_usd:.2f}, limit: ${self.settings.max_cost_per_video_usd:.2f})"
            )
        else:
            tts_order = [
                self.settings.tts_provider_primary,
                self.settings.tts_provider_secondary,
                self.settings.tts_provider_fallback,
            ]
            self._log_status(f"Ücretsiz ses modu aktif ({budget_decision.reason}).")

        for i, scene in enumerate(writer_out.slide_texts):
            image_path, video_path, scene_visual_provider, asset_query = await self._render_scene_assets(
                scene=scene,
                index=i + 1,
                total=len(writer_out.slide_texts),
                note=note,
                lang=lang,
            )
            visual_providers_seen.add(scene_visual_provider)

            speaker = str(scene.get("speaker", "narrator")).lower()
            self._log_status(f"Sahne {i + 1}/{len(writer_out.slide_texts)} - Ses üretiliyor ({speaker})...")
            audio_path = await self.tts.generate(
                scene.get("text", ""),
                lang=lang,
                character=speaker,
                providers_override=tts_order,
            )
            voice_provider_used = self.tts.last_provider_used

            scene_data.append(
                {
                    "image_path": str(image_path),
                    "video_path": str(video_path) if video_path else None,
                    "audio_path": str(audio_path),
                    "text": scene.get("text", ""),
                    "asset_query": asset_query,
                    "visual_provider_used": scene_visual_provider,
                }
            )

        self._log_status("Video montajı, müzik seçimi ve kalite kapısı başlıyor...")
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output_filename = f"episode_{lang}_{stamp}.mp4"
        mood = str(writer_out.slide_texts[0].get("mood") or "playful") if writer_out.slide_texts else "playful"

        music_tracks = self.music_selector.choose_tracks(
            mood=mood,
            target_duration=float(len(scene_data) * 14),
            max_changes=2,
        )
        track_payload = [{"id": t.track_id, "path": t.path} for t in music_tracks if os.path.exists(t.path)]
        final_video_path = await self.assembly.create_episode(
            scene_data=scene_data,
            output_filename=output_filename,
            bg_music_path=None,
            bg_music_tracks=track_payload,
            ducking_db=-16.0,
        )

        quality = self.quality_gate.evaluate(
            scene_data=scene_data,
            video_path=final_video_path,
            music_track_id=music_tracks[0].track_id if music_tracks else None,
        )
        if not quality.passed:
            failed = quality.failed_layer or "unknown"
            self._log_status(f"Kalite kapısı başarısız ({failed}); katman yeniden üretiliyor...")
            if failed == "audio":
                for scene in scene_data:
                    scene["audio_path"] = str(
                        await self.tts.generate(
                            scene.get("text", ""),
                            lang=lang,
                            character="narrator",
                            providers_override=tts_order,
                        )
                    )
                voice_provider_used = self.tts.last_provider_used
            elif failed == "visual":
                for idx, scene in enumerate(scene_data):
                    fallback_bytes = self.template_renderer.render_kids_scene(
                        title=str(scene.get("text") or note.keyword)[:100],
                        subtitle=note.keyword[:80],
                        mood="playful",
                    )
                    p, _ = await self.img_store.save(
                        fallback_bytes,
                        self.account_handle,
                        subfolder=f"episode_{lang}_retry",
                    )
                    scene["image_path"] = p
                    scene["video_path"] = None
                    scene["visual_provider_used"] = "kids_fallback"
                    scene["asset_query"] = str(scene.get("asset_query") or note.keyword)
                    visual_providers_seen.add("kids_fallback")
            elif failed == "music":
                music_tracks = self.music_selector.choose_tracks(
                    mood="playful",
                    target_duration=float(len(scene_data) * 14),
                    max_changes=0,
                )
                track_payload = [{"id": t.track_id, "path": t.path} for t in music_tracks if os.path.exists(t.path)]

            final_video_path = await self.assembly.create_episode(
                scene_data=scene_data,
                output_filename=f"episode_{lang}_{stamp}_retry.mp4",
                bg_music_path=None,
                bg_music_tracks=track_payload,
                ducking_db=-16.0,
            )
            quality = self.quality_gate.evaluate(
                scene_data=scene_data,
                video_path=final_video_path,
                music_track_id=music_tracks[0].track_id if music_tracks else None,
            )

        self.quality_gate.ensure(quality)

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
        teaser_music_path = music_tracks[0].path if music_tracks else None
        try:
            self._log_status("Instagram için fragman (Reels) üretiliyor...")
            teaser_filename = f"teaser_{lang}_{stamp}.mp4"
            await self.assembly.create_teaser(
                scene_data=scene_data,
                output_filename=teaser_filename,
                max_duration=60.0,
                bg_music_path=teaser_music_path,
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
            voice_provider_used=voice_provider_used,
            visual_provider_used=",".join(sorted(visual_providers_seen)) if visual_providers_seen else "unknown",
            music_track_id=music_tracks[0].track_id if music_tracks else None,
            quality_scores=quality.scores,
            quality_passed=quality.passed,
            estimated_cost_usd=budget_decision.estimated_cost_usd,
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
