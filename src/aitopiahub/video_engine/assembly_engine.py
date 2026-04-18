"""Video assembly engine for short/teaser/long episode outputs."""

from __future__ import annotations

import os
import random
from pathlib import Path

from PIL import Image
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
    vfx,
)

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

# Pillow 10+ removed ANTIALIAS while MoviePy 1.0.3 still references it.
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = getattr(Image, "Resampling", Image).LANCZOS


class AssemblyEngine:
    """Combine images + audio into publishable vertical/horizontal videos."""

    def __init__(self, output_dir: Path | str = "./data/videos"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def create_short(
        self,
        image_paths: list[Path | str],
        audio_path: Path | str,
        output_filename: str,
        subtitles: list[str] | None = None,
        bg_music_path: Path | str | None = None,
    ) -> Path:
        """Build YouTube Shorts / IG Reels style 9:16 short video."""
        if not image_paths:
            raise ValueError("create_short requires at least one image path")

        output_path = self.output_dir / output_filename
        log.info("starting_video_assembly", output=output_filename, scenes=len(image_paths))

        audio = AudioFileClip(str(audio_path))
        duration = max(audio.duration, 1.0)

        base_scene_duration = max(5.0, duration / max(len(image_paths), 1))
        clips = []
        for i, img_path in enumerate(image_paths):
            clip = ImageClip(str(img_path)).set_duration(base_scene_duration).resize(height=1920)
            zoom_speed = 0.05 + (random.random() * 0.03)
            clip = clip.resize(lambda t: 1 + zoom_speed * t / base_scene_duration)
            if i > 0:
                clip = clip.crossfadein(1.0)
            clips.append(clip)

        final_video = concatenate_videoclips(clips, method="compose", padding=-1)
        final_video = final_video.set_duration(max(duration, final_video.duration))

        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(str(bg_music_path)).volumex(0.15)
            if bg_music.duration < duration:
                bg_music = bg_music.fx(vfx.loop, duration=duration)
            bg_music = bg_music.set_duration(duration)
            from moviepy.audio.AudioClip import CompositeAudioClip

            final_audio = CompositeAudioClip([audio.volumex(1.0), bg_music])
            final_video = final_video.set_audio(final_audio)
        else:
            final_video = final_video.set_audio(audio)

        if subtitles:
            txt_clips = []
            sub_duration = duration / max(len(subtitles), 1)
            for i, text in enumerate(subtitles):
                try:
                    txt = (
                        TextClip(
                            text,
                            fontsize=60,
                            color="yellow",
                            font="Arial-Bold",
                            stroke_color="black",
                            stroke_width=2,
                            method="caption",
                            size=(800, None),
                        )
                        .set_start(i * sub_duration)
                        .set_duration(sub_duration)
                        .set_position(("center", 1350))
                    )
                    txt_clips.append(txt)
                except Exception as exc:
                    log.warning("subtitle_render_failed", error=str(exc))
            if txt_clips:
                final_video = CompositeVideoClip([final_video] + txt_clips)

        log.info("rendering_video", path=str(output_path))
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            logger=None,
        )
        final_video.close()
        audio.close()
        return output_path

    async def create_episode(
        self,
        scene_data: list[dict],
        output_filename: str,
        bg_music_path: Path | str | None = None,
    ) -> Path:
        """Build 5-10 minute long-form episode."""
        if not scene_data:
            raise ValueError("create_episode requires scene data")

        output_path = self.output_dir / output_filename
        log.info("starting_episode_assembly", output=output_filename, scenes=len(scene_data))

        clips = []
        for i, scene in enumerate(scene_data):
            audio_clip = AudioFileClip(str(scene["audio_path"]))
            scene_duration = audio_clip.duration + 0.5

            clip = ImageClip(str(scene["image_path"]))
            clip = clip.set_duration(scene_duration).resize(height=1080)
            zoom_speed = 0.04 + (random.random() * 0.04)
            clip = clip.resize(lambda t: 1 + zoom_speed * t / scene_duration)
            if i > 0:
                clip = clip.crossfadein(0.8)

            text = scene.get("text", "")
            if text:
                try:
                    txt = (
                        TextClip(
                            text,
                            fontsize=45,
                            color="white",
                            font="Arial-Bold",
                            stroke_color="black",
                            stroke_width=1,
                            method="caption",
                            size=(1600, None),
                        )
                        .set_duration(scene_duration)
                        .set_position(("center", 850))
                    )
                    clip = CompositeVideoClip([clip, txt])
                except Exception as exc:
                    log.warning("episode_subtitle_failed", scene=i, error=str(exc))

            clip = clip.set_audio(audio_clip)
            clips.append(clip)

        final_video = concatenate_videoclips(clips, method="compose", padding=-0.5)

        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(str(bg_music_path)).volumex(0.1)
            if bg_music.duration < final_video.duration:
                bg_music = bg_music.fx(vfx.loop, duration=final_video.duration)
            bg_music = bg_music.set_duration(final_video.duration)
            from moviepy.audio.AudioClip import CompositeAudioClip

            mixed = CompositeAudioClip([final_video.audio, bg_music])
            final_video = final_video.set_audio(mixed)

        log.info("rendering_long_episode", path=str(output_path))
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            logger=None,
        )
        final_video.close()
        return output_path

    async def create_teaser(
        self,
        scene_data: list[dict],
        output_filename: str,
        max_duration: float = 60.0,
        bg_music_path: Path | str | None = None,
    ) -> Path:
        """Build short teaser for Instagram Reels."""
        if not scene_data:
            raise ValueError("create_teaser requires scene data")

        output_path = self.output_dir / output_filename
        log.info("starting_teaser_assembly", output=output_filename, max_target=max_duration)

        clips = []
        current_duration = 0.0

        for i, scene in enumerate(scene_data):
            if current_duration >= max_duration:
                break

            audio_clip = AudioFileClip(str(scene["audio_path"]))
            scene_duration = audio_clip.duration + 0.2
            if current_duration + scene_duration > max_duration:
                scene_duration = max_duration - current_duration
                audio_clip = audio_clip.set_duration(scene_duration)

            clip = ImageClip(str(scene["image_path"]))
            clip = clip.set_duration(scene_duration).resize(height=1920)
            clip = clip.resize(lambda t: 1 + 0.05 * t / max(scene_duration, 0.1))
            if i > 0:
                clip = clip.crossfadein(0.5)

            text = scene.get("text", "")
            if text:
                try:
                    txt = (
                        TextClip(
                            text,
                            fontsize=60,
                            color="yellow",
                            font="Arial-Bold",
                            stroke_color="black",
                            stroke_width=2,
                            method="caption",
                            size=(900, None),
                        )
                        .set_duration(scene_duration)
                        .set_position(("center", 1400))
                    )
                    clip = CompositeVideoClip([clip, txt])
                except Exception as exc:
                    log.warning("teaser_subtitle_failed", error=str(exc))

            clip = clip.set_audio(audio_clip)
            clips.append(clip)
            current_duration += scene_duration

        if clips:
            try:
                cta_text = (
                    TextClip(
                        "DEVAMI YOUTUBE\nKANALIMIZDA!",
                        fontsize=80,
                        color="white",
                        font="Arial-Bold",
                        stroke_color="red",
                        stroke_width=3,
                        method="caption",
                        size=(1000, None),
                    )
                    .set_duration(2.0)
                    .set_position("center")
                    .crossfadein(0.5)
                )
                last_clip = clips[-1]
                clips[-1] = CompositeVideoClip([last_clip, cta_text.set_start(max(0, last_clip.duration - 2.0))])
            except Exception:
                pass

        final_video = concatenate_videoclips(clips, method="compose", padding=-0.3)

        if bg_music_path and os.path.exists(bg_music_path):
            bg_music = AudioFileClip(str(bg_music_path)).volumex(0.2)
            if bg_music.duration < final_video.duration:
                bg_music = bg_music.fx(vfx.loop, duration=final_video.duration)
            bg_music = bg_music.set_duration(final_video.duration)
            from moviepy.audio.AudioClip import CompositeAudioClip

            final_audio = CompositeAudioClip([final_video.audio, bg_music])
            final_video = final_video.set_audio(final_audio)

        log.info("rendering_teaser", path=str(output_path))
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
        final_video.close()
        return output_path
