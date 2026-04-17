"""
Video montaj motoru.
Görsel, ses ve altyazıları birleştirerek profesyonel 9:16 video üretir.
"""

from __future__ import annotations

import os
from pathlib import Path
import random

from moviepy.editor import (
    ImageClip, 
    AudioFileClip, 
    CompositeVideoClip, 
    concatenate_videoclips,
    TextClip,
    vfx
)

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

class AssemblyEngine:
    """Görsel ve sesleri birleştirip video üreten motor."""

    def __init__(self, output_dir: Path | str = "./data/videos"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Fonksiyonel olarak ImageMagick gerekiyorsa TextClip için yapılandırılmalıdır.
        # Dockerfile'da fonts-noto eklemiştik.

    async def create_short(
        self,
        image_paths: list[Path | str],
        audio_path: Path | str,
        output_filename: str,
        subtitles: list[str] | None = None,
        bg_music_path: Path | str | None = None
    ) -> Path:
        """
        YouTube Shorts / Instagram Reels formatında (9:16) video üretir.
        """
        log.info("starting_video_assembly", output=output_filename, scenes=len(image_paths))
        output_path = self.output_dir / output_filename
        
        # 1. Ses dosyasını yükle (Süre kontrolü için)
        audio = AudioFileClip(str(audio_path))
        duration = audio.duration
        
        # 2. Görselleri klip haline getir
        # Her sahnenin seslendirme süresine göre veya min 5 saniye olacak şekilde ayarla
        base_scene_duration = max(5.0, duration / len(image_paths))
        total_visual_duration = base_scene_duration * len(image_paths)
        
        clips = []
        for i, img_path in enumerate(image_paths):
            clip = ImageClip(str(img_path)).set_duration(base_scene_duration)
            clip = clip.resize(height=1920) # Portrait height
            
            # Ken Burns: Rastgele yön ve derinlik
            zoom_speed = 0.05 + (random.random() * 0.03)
            clip = clip.resize(lambda t: 1 + zoom_speed * t/base_scene_duration)
            
            # Sahneler arası geçiş (Crossfade) - İlk sahne hariç
            if i > 0:
                clip = clip.crossfadein(1.0)
            
            clips.append(clip)
        
        # Sahneleri birleştir (Yumuşak geçişler için padding)
        final_video = concatenate_videoclips(clips, method="compose", padding=-1)
        
        # Eğer video sesten uzunsa (min duration nedeniyle), sonunu ayarla
        final_video = final_video.set_duration(max(duration, total_visual_duration - (len(clips)-1)))
        
        # 3. Sesleri birleştir
        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(str(bg_music_path)).volumex(0.15).set_duration(duration)
            # Loop bg music if shorter than duration
            if bg_music.duration < duration:
                bg_music = bg_music.fx(vfx.loop, duration=duration)
            
            from moviepy.audio.AudioClip import CompositeAudioClip
            final_audio = CompositeAudioClip([audio.volumex(1.0), bg_music])
            final_video = final_video.set_audio(final_audio)
        else:
            final_video = final_video.set_audio(audio)

        # 4. Altyazı Ekleme (Basit Overlay)
        # Not: TextClip için ImageMagick konfigürasyonu gerekebilir. 
        # Şimdilik fallback olarak log basalım veya basit bir static text ekleyelim.
        # 4. Altyazı Ekleme (Okunabilirlik için Arka Planlı)
        if subtitles:
            txt_clips = []
            sub_duration = duration / len(subtitles)
            for i, text in enumerate(subtitles):
                try:
                    # Daha estetik ve okunabilir altyazılar
                    txt = (TextClip(text, 
                                    fontsize=60, 
                                    color='yellow', 
                                    font='Arial-Bold',
                                    stroke_color='black',
                                    stroke_width=2,
                                    method='caption', 
                                    size=(800, None))
                           .set_start(i * sub_duration)
                           .set_duration(sub_duration)
                           .set_position(('center', 1350)))
                    
                    # Altyazı arkasına hafif bir gölge/kutu eklemek için (opsiyonel ama şık)
                    txt_clips.append(txt)
                except Exception as e:
                    log.warning("subtitle_render_failed", error=str(e))
            
            if txt_clips:
                final_video = CompositeVideoClip([final_video] + txt_clips)

        # 5. Render
        log.info("rendering_video", path=str(output_path))
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True
        )
        

    async def create_episode(
        self,
        scene_data: list[dict], # list of {'image_path': str, 'audio_path': str, 'text': str}
        output_filename: str,
        bg_music_path: Path | str | None = None
    ) -> Path:
        """
        5-10 dakikalık uzun metrajlı bölümler üretir.
        Her sahneyi ses dosyasına göre senkronize eder.
        """
        log.info("starting_episode_assembly", output=output_filename, scenes=len(scene_data))
        output_path = self.output_dir / output_filename
        
        clips = []
        for i, scene in enumerate(scene_data):
            img_path = scene['image_path']
            audio_path = scene['audio_path']
            text = scene['text']
            
            # Ses dosyasını ve süresini al
            audio_clip = AudioFileClip(str(audio_path))
            scene_duration = audio_clip.duration + 0.5 # Yarım saniye boşluk
            
            # Görsel klip
            clip = ImageClip(str(img_path)).set_duration(scene_duration)
            clip = clip.resize(height=1080) # 16:9 HD standard
            
            # Ken Burns (Rastgele)
            zoom_speed = 0.04 + (random.random() * 0.04)
            clip = clip.resize(lambda t: 1 + zoom_speed * t/scene_duration)
            
            if i > 0:
                clip = clip.crossfadein(0.8)
            
            # Altyazı
            try:
                txt = (TextClip(text, 
                                fontsize=45, 
                                color='white', 
                                font='Arial-Bold',
                                stroke_color='black',
                                stroke_width=1,
                                method='caption', 
                                size=(1600, None))
                       .set_duration(scene_duration)
                       .set_position(('center', 850)))
                clip = CompositeVideoClip([clip, txt])
            except Exception as e:
                log.warning("episode_subtitle_failed", scene=i, error=str(e))
            
            clip = clip.set_audio(audio_clip)
            clips.append(clip)
            
        # Tüm sahneleri birleştir
        final_video = concatenate_videoclips(clips, method="compose", padding=-0.5)
        
        # Müzik ekle
        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(str(bg_music_path)).volumex(0.1).set_duration(final_video.duration)
            if bg_music.duration < final_video.duration:
                bg_music = bg_music.fx(vfx.loop, duration=final_video.duration)
            
            combined_audio = CompositeAudioClip([final_video.audio, bg_music])
            final_video = final_video.set_audio(combined_audio)
            
        log.info("rendering_long_episode", path=str(output_path))
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            threads=4, # Multithreading for long renders
            logger=None
        )
        
    async def create_teaser(
        self,
        scene_data: list[dict],
        output_filename: str,
        max_duration: float = 60.0,
        bg_music_path: Path | str | None = None
    ) -> Path:
        """
        Instagram Reels için dikey (9:16) ve kısa bir fragman üretir.
        """
        log.info("starting_teaser_assembly", output=output_filename, max_target=max_duration)
        output_path = self.output_dir / output_filename
        
        clips = []
        current_duration = 0.0
        
        for i, scene in enumerate(scene_data):
            if current_duration >= max_duration:
                break
                
            img_path = scene['image_path']
            audio_path = scene['audio_path']
            text = scene['text']
            
            audio_clip = AudioFileClip(str(audio_path))
            scene_duration = audio_clip.duration + 0.2
            
            # Eğer bu sahne ile limit aşılıyorsa, sahneyi kırp veya sonlandır
            if current_duration + scene_duration > max_duration:
                scene_duration = max_duration - current_duration
                audio_clip = audio_clip.set_duration(scene_duration)

            # Görsel klip (Dikey Format - 9:16)
            clip = ImageClip(str(img_path)).set_duration(scene_duration)
            clip = clip.resize(height=1920) # Reels standard height
            
            # Zoom effect
            zoom_speed = 0.05
            clip = clip.resize(lambda t: 1 + zoom_speed * t/scene_duration)
            
            if i > 0:
                clip = clip.crossfadein(0.5)
            
            # Altyazı (Dikey format için ortalanmış)
            try:
                txt = (TextClip(text, 
                                fontsize=60, 
                                color='yellow', 
                                font='Arial-Bold',
                                stroke_color='black',
                                stroke_width=2,
                                method='caption', 
                                size=(900, None))
                       .set_duration(scene_duration)
                       .set_position(('center', 1400)))
                clip = CompositeVideoClip([clip, txt])
            except Exception as e:
                log.warning("teaser_subtitle_failed", error=str(e))
            
            clip = clip.set_audio(audio_clip)
            clips.append(clip)
            current_duration += scene_duration

        # Son sahneye "Devamı YouTube Kanalımızda" yazısı ekle
        try:
            cta_text = (TextClip("DEVAMI YOUTUBE\nKANALIMIZDA!", 
                                fontsize=80, 
                                color='white', 
                                font='Arial-Bold',
                                stroke_color='red',
                                stroke_width=3,
                                method='caption', 
                                size=(1000, None))
                       .set_duration(2.0)
                       .set_position('center')
                       .crossfadein(0.5))
            # Son klibin sonuna ekle veya yeni bir klip yap
            last_clip = clips[-1]
            cta_clip = CompositeVideoClip([last_clip, cta_text.set_start(last_clip.duration - 2.0)])
            clips[-1] = cta_clip
        except:
             pass

        final_video = concatenate_videoclips(clips, method="compose", padding=-0.3)
        
        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(str(bg_music_path)).volumex(0.2).set_duration(final_video.duration)
            if bg_music.duration < final_video.duration:
                bg_music = bg_music.fx(vfx.loop, duration=final_video.duration)
            
            from moviepy.audio.AudioClip import CompositeAudioClip
            final_audio = CompositeAudioClip([final_video.audio, bg_music])
            final_video = final_video.set_audio(combined_audio if 'combined_audio' in locals() else final_audio)
            
        log.info("rendering_teaser", path=str(output_path))
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None
        )
        
        return output_path
