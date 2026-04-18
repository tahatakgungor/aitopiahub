"""
Pillow tabanlı branded şablon sistemi.
Profesyonel haber kartı tasarımı (NYT/BBC estetiği).
Sıfır maliyet, tutarlı marka kimliği.
"""

from __future__ import annotations

import io
import random
import textwrap
from enum import Enum
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

ASSETS_DIR = Path(__file__).resolve().parents[4] / "assets" / "templates"
FONTS_DIR = ASSETS_DIR / "fonts"

# Marka renk paleti
COLORS = {
    "bg_dark": (10, 10, 20),          # Koyu lacivert arka plan
    "bg_card": (18, 18, 32),          # Kart arka planı
    "accent_red": (220, 50, 50),       # Breaking news kırmızı
    "accent_blue": (50, 130, 220),     # Analiz mavisi
    "accent_green": (50, 200, 100),    # Başarı/pozitif
    "accent_purple": (150, 80, 220),   # Tech/AI mor
    "text_primary": (255, 255, 255),   # Beyaz metin
    "text_secondary": (180, 180, 200), # Gri metin
    "text_muted": (120, 120, 140),     # Soluk metin
    "divider": (40, 40, 60),          # Bölücü çizgi
}

INSTAGRAM_SIZES = {
    "portrait": (1080, 1350),
    "square": (1080, 1080),
    "story": (1080, 1920),   # 9:16 vertical — YouTube Shorts / Instagram Stories
}


class TemplateType(str, Enum):
    BREAKING_NEWS = "breaking_news"
    ANALYSIS = "analysis"
    STAT_CARD = "stat_card"
    QUOTE_CARD = "quote_card"
    SLIDE_CONTENT = "slide_content"
    SLIDE_COVER = "slide_cover"
    SLIDE_CTA = "slide_cta"


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = FONTS_DIR / name
    try:
        return ImageFont.truetype(str(font_path), size)
    except (OSError, IOError):
        # Sistem font'larını dene
        system_fonts = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        for sf in system_fonts:
            try:
                return ImageFont.truetype(sf, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()


class TemplateRenderer:
    """
    Branded Instagram görsel şablonları üretir.
    Her şablon 1080x1350 (4:5) veya 1080x1080 (1:1) boyutunda.
    """

    def render_breaking_news(
        self,
        headline: str,
        subtext: str = "",
        bg_image: bytes | None = None,
    ) -> bytes:
        """Breaking news kartı: kırmızı banner + büyük başlık."""
        img = self._base_image("portrait")
        draw = ImageDraw.Draw(img)
        W, H = INSTAGRAM_SIZES["portrait"]

        # Arka plan overlay (AI görsel varsa)
        if bg_image:
            try:
                bg = Image.open(io.BytesIO(bg_image)).convert("RGBA").resize((W, H))
                overlay = Image.new("RGBA", (W, H), (*COLORS["bg_dark"], 180))
                img = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
                draw = ImageDraw.Draw(img)
            except Exception:
                pass

        # BREAKING NEWS banner (üst)
        banner_h = 90
        draw.rectangle([0, 80, W, 80 + banner_h], fill=COLORS["accent_red"])
        font_breaking = _load_font("Inter-Bold.ttf", 36)
        draw.text((40, 100), "⚡ BREAKING NEWS", font=font_breaking, fill=COLORS["text_primary"])

        # Ana başlık (ortada büyük)
        font_headline = _load_font("Inter-Bold.ttf", 72)
        wrapped = textwrap.wrap(headline, width=22)
        y = 250
        for line in wrapped[:4]:
            draw.text((40, y), line, font=font_headline, fill=COLORS["text_primary"])
            y += 90

        # Alt metin
        if subtext:
            font_sub = _load_font("Inter-Regular.ttf", 42)
            wrapped_sub = textwrap.wrap(subtext, width=32)
            for line in wrapped_sub[:3]:
                draw.text((40, y + 20), line, font=font_sub, fill=COLORS["text_secondary"])
                y += 55

        # Alt: Marka logosu
        self._draw_brand_footer(draw, img, W, H)

        return self._to_bytes(img)

    def render_slide_cover(
        self,
        headline: str,
        bg_image: bytes | None = None,
        accent_color: str = "accent_blue",
    ) -> bytes:
        """Carousel kapak slaytı: güçlü hook + AI görsel."""
        img = self._base_image("square")
        draw = ImageDraw.Draw(img)
        W, H = INSTAGRAM_SIZES["square"]

        if bg_image:
            try:
                bg = Image.open(io.BytesIO(bg_image)).convert("RGBA").resize((W, H))
                overlay = Image.new("RGBA", (W, H), (*COLORS["bg_dark"], 160))
                img = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
                draw = ImageDraw.Draw(img)
            except Exception:
                pass

        # Renk aksanı çizgisi (üst)
        accent = COLORS.get(accent_color, COLORS["accent_blue"])
        draw.rectangle([0, 0, W, 8], fill=accent)

        # Başlık
        font_h = _load_font("Inter-Bold.ttf", 68)
        wrapped = textwrap.wrap(headline, width=20)
        total_h = len(wrapped) * 85
        y_start = (H - total_h) // 2 - 40
        for line in wrapped[:4]:
            draw.text((50, y_start), line, font=font_h, fill=COLORS["text_primary"])
            y_start += 85

        # "Swipe →" işareti
        font_swipe = _load_font("Inter-Regular.ttf", 32)
        draw.text((W - 160, H - 80), "Swipe →", font=font_swipe, fill=COLORS["text_muted"])

        self._draw_brand_footer(draw, img, W, H)
        return self._to_bytes(img)

    def render_slide_content(
        self,
        slide_num: int,
        total_slides: int,
        headline: str,
        body: str,
    ) -> bytes:
        """İç slayt: başlık + içerik metni."""
        img = self._base_image("square")
        draw = ImageDraw.Draw(img)
        W, H = INSTAGRAM_SIZES["square"]

        # Slayt numarası (üst sağ)
        font_num = _load_font("Inter-Regular.ttf", 30)
        draw.text(
            (W - 100, 40),
            f"{slide_num}/{total_slides}",
            font=font_num,
            fill=COLORS["text_muted"],
        )

        # Üst mavi çizgi
        draw.rectangle([0, 0, W, 6], fill=COLORS["accent_blue"])

        # Başlık
        font_h = _load_font("Inter-Bold.ttf", 52)
        wrapped_h = textwrap.wrap(headline, width=24)
        y = 100
        for line in wrapped_h[:2]:
            draw.text((50, y), line, font=font_h, fill=COLORS["text_primary"])
            y += 65

        # Divider
        draw.rectangle([50, y + 20, W - 50, y + 23], fill=COLORS["divider"])
        y += 50

        # Body metin
        font_b = _load_font("Inter-Regular.ttf", 40)
        wrapped_b = textwrap.wrap(body, width=30)
        for line in wrapped_b[:6]:
            draw.text((50, y), line, font=font_b, fill=COLORS["text_secondary"])
            y += 55

        self._draw_brand_footer(draw, img, W, H)
        return self._to_bytes(img)

    def render_slide_cta(self, cta_text: str = "Takip et & Kaydet 🔔") -> bytes:
        """Son slayt: CTA + marka."""
        img = self._base_image("square")
        draw = ImageDraw.Draw(img)
        W, H = INSTAGRAM_SIZES["square"]

        # Gradient efekti (basit)
        for i in range(H):
            ratio = i / H
            r = int(10 + 40 * ratio)
            g = int(10 + 20 * ratio)
            b = int(20 + 60 * ratio)
            draw.line([(0, i), (W, i)], fill=(r, g, b))

        # CTA metni (ortada)
        font_cta = _load_font("Inter-Bold.ttf", 58)
        wrapped = textwrap.wrap(cta_text, width=18)
        total = len(wrapped) * 75
        y = (H - total) // 2 - 60
        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=font_cta)
            x = (W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font_cta, fill=COLORS["text_primary"])
            y += 75

        # Hesap adı
        font_handle = _load_font("Inter-Bold.ttf", 44)
        draw.text((50, H - 120), "@aitopiahub_news", font=font_handle, fill=COLORS["accent_blue"])

        return self._to_bytes(img)

    def render_kids_scene(
        self,
        title: str,
        subtitle: str = "",
        mood: str = "playful",
    ) -> bytes:
        """Kid-friendly fallback scene visual (non-news style)."""
        img = self._base_image("story")
        draw = ImageDraw.Draw(img)
        w, h = INSTAGRAM_SIZES["story"]

        base_map = {
            "playful": ((255, 198, 109), (120, 193, 255)),
            "calm": ((180, 229, 255), (135, 206, 250)),
            "adventure": ((255, 224, 130), (255, 183, 77)),
            "wonder": ((201, 169, 255), (140, 190, 255)),
        }
        c1, c2 = base_map.get(mood, base_map["playful"])
        for y in range(h):
            ratio = y / max(1, h - 1)
            r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
            g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
            b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        rng = random.Random(f"{title}:{subtitle}:{mood}")
        for _ in range(26):
            radius = rng.randint(12, 60)
            x = rng.randint(0, w)
            y = rng.randint(0, h)
            color = (
                rng.randint(120, 255),
                rng.randint(120, 255),
                rng.randint(120, 255),
                rng.randint(40, 110),
            )
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)

        font_title = _load_font("Inter-Bold.ttf", 74)
        font_sub = _load_font("Inter-Regular.ttf", 46)
        wrapped_title = textwrap.wrap(title, width=18)[:4]
        y = 240
        for line in wrapped_title:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            x = (w - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font_title, fill=(255, 255, 255))
            y += 92

        if subtitle:
            wrapped_sub = textwrap.wrap(subtitle, width=24)[:3]
            y += 20
            for line in wrapped_sub:
                bbox = draw.textbbox((0, 0), line, font=font_sub)
                x = (w - (bbox[2] - bbox[0])) // 2
                draw.text((x, y), line, font=font_sub, fill=(245, 245, 255))
                y += 58

        return self._to_bytes(img)

    def _base_image(self, size: str = "portrait") -> Image.Image:
        w, h = INSTAGRAM_SIZES.get(size, INSTAGRAM_SIZES["portrait"])
        return Image.new("RGB", (w, h), COLORS["bg_dark"])

    def _draw_brand_footer(
        self, draw: ImageDraw.ImageDraw, img: Image.Image, W: int, H: int
    ) -> None:
        font = _load_font("Inter-Regular.ttf", 28)
        draw.text((40, H - 60), "aitopiahub.com", font=font, fill=COLORS["text_muted"])

    def _to_bytes(self, img: Image.Image, quality: int = 92) -> bytes:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
