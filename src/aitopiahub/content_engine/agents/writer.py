"""
Ajan 2 — Writer
Görev: Researcher notundan Instagram formatında içerik üret.
SINGLE: Tek görsel + caption
CAROUSEL: 3-7 slayt metni + caption
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aitopiahub.content_engine.agents.researcher import ResearchNote
from aitopiahub.content_engine.llm_client import LLMClient, ModelTier
from aitopiahub.core.constants import ContentAngle, PostFormat
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

PERSONA_PROMPTS = {
    "news_authoritative": """Sen Aitopiahub News hesabısın. Misyonun: yapay zeka ve teknoloji dünyasındaki en önemli gelişmeleri Türk ve global kitleye sade, doğru ve ilgi çekici bir dille aktarmak.

Ton: Otoritatif ama samimi. NYT Tech bölümü gibi güvenilir, ama Instagram'a uygun sıcak.
Kural: Abartma yok, clickbait yok. Gerçekler konuşsun.""",
    "kids_storyteller": """Sen 'Meraklı Yumurcak' kanalının hikaye anlatıcısısın. 
Misyonun: Çocuklara ilginç bilgileri, hayvanlar dünyasını ve bilimi çok heyecanlı, eğlenceli ve basit bir dille anlatmak.
Ton: Çok enerjik, neşeli, merak uyandırıcı. Bol bol 'Biliyor muydunuz?', 'İnanılmaz değil mi?' gibi ifadeler kullan.
Görsel Üslup: Her zaman Pixar/Disney tarzı 3D animasyon görselleri hayal et.""",

    "default": "Sen bir teknoloji ve yapay zeka haberleri Instagram hesabısın.",
}


@dataclass
class WriterOutput:
    post_format: str
    caption_text: str
    slide_texts: list[dict] | None   # Carousel için
    image_prompt_hint: str           # Görsel oluşturmak için ipucu
    angle: str
    suggested_hashtags: list[str]


class WriterAgent:
    """
    Research notundan Instagram içeriği yazar.
    Format otomatik seçilir veya dışarıdan belirtilebilir.
    """

    def __init__(self, llm: LLMClient, persona: str = "news_authoritative"):
        self.llm = llm
        self.persona = persona
        self.system_prompt = PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["default"])

    async def write(
        self,
        note: ResearchNote,
        post_format: PostFormat = PostFormat.CAROUSEL,
        angle: ContentAngle = ContentAngle.INFORMATIVE,
        language: str = "tr",
        proven_hooks: list[str] | None = None,
        content_mode: str = "demand_driven",
        story_profile: dict | None = None,
        fairy_style: str = "modern_educational",
    ) -> WriterOutput:
        """İçerik taslağı üret."""

        if post_format == PostFormat.CAROUSEL:
            return await self._write_carousel(note, angle, language, proven_hooks)
        elif post_format == PostFormat.SHORT_SCRIPT:
            return await self._write_short_script(note, angle, language, proven_hooks)
        elif post_format == PostFormat.LONG_EPISODE:
            return await self._write_long_episode(
                note,
                angle,
                language,
                proven_hooks,
                content_mode=content_mode,
                story_profile=story_profile,
                fairy_style=fairy_style,
            )
        else:
            return await self._write_single(note, angle, language, proven_hooks)

    async def _write_long_episode(
        self,
        note: ResearchNote,
        angle: ContentAngle,
        language: str,
        proven_hooks: list[str] | None,
        content_mode: str = "demand_driven",
        story_profile: dict | None = None,
        fairy_style: str = "modern_educational",
    ) -> WriterOutput:
        story_constraints = ""
        if content_mode == "fairy_tale" and story_profile:
            chars = ", ".join(story_profile.get("characters", []))
            blocked = ", ".join(story_profile.get("blocked_elements", []))
            moral = story_profile.get("moral", "")
            story_constraints = f"""
Masal modu aktif. Hikaye kimliği: {story_profile.get("id")}
Karakterler: {chars}
Kaçınılacak unsurlar: {blocked}
Pedagojik mesaj: {moral}
Stil: {fairy_style}
Ek Kurallar:
- Klasik hikayeyi modern ve çocuk güvenliğine uygun şekilde anlat.
- Korku/şiddet içeren kısımları yumuşat.
- Finalde tam 1 ders cümlesi ve 1 etkileşim sorusu ekle.
- Sahne metinleri ve görseller birbirini birebir tamamlasın.
"""

        min_words = 35 if language == "tr" else 30
        prompt = f"""Konu: "{note.keyword}"
Detaylar: {note.main_finding}
Dil: {"Türkçe" if language == "tr" else "English"}
İçerik modu: {content_mode}
{story_constraints}

YouTube için 5 dakikalık çocuk eğitim/hikaye videosu (Episode) senaryosu yaz.
Kurallar:
- SÜRE: Toplam 5 dakika (yaklaşık 700-800 kelime, HER SAHNE EN AZ {min_words} KELIME).
- YAPI: Giriş (Hook), 3 Ana Bölüm, Etkileşim (Soru-Cevap), Kapanış.
- KARAKTERLER: Bir 'Anlatıcı' (Narrator) ve en az 1-2 'Karakter' (Diyalog kurabilirler).
- SAHNELER: TAM OLARAK 20 sahne yaz. Her sahne için görsel prompt ve metin.
- KRİTİK: Her "text" alanı EN AZ {min_words} kelime içermeli. Kısa cümleler KESİNLİKLE YASAK.
JSON formatında döndür:
{{
  "title": "Bölüm Başlığı",
  "caption": "Video açıklaması",
  "scenes": [
    {{
      "index": 0,
      "speaker": "Narrator",
      "text": "En az {min_words} kelimeden oluşan detaylı, akıcı seslendirme metni. Çocukların hayal gücünü ateşleyen, merak uyandıran cümleler yaz. Bu sahne hikayenin girişi olmalı.",
      "image_prompt": "Pixar 3D animation style, colorful kids illustration showing [scene content], vibrant colors, no text",
      "asset_query": "kids animated short clip [scene topic]",
      "mood": "playful",
      "motion_hint": "gentle camera pan right",
      "avoid_elements": ["violence", "horror", "blood"]
    }}
  ],
  "image_prompt_hint": "Pixar 3D animation style, bright colors, child-friendly"
}}

KRİTİK KURAL: Her "text" değeri {min_words} kelimeden AZ OLAMAZ. Toplam 20 sahne × {min_words} kelime = en az {20 * min_words} kelime gerekli.
{"Türkçe kalitesini EN ÜST seviyede tut. Çeviri gibi değil, bir Türk çocuk masalı gibi aksın." if language == "tr" else "Write natural, engaging English that flows like a professional children's storyteller."}
"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.system_prompt,
                model=ModelTier.QUALITY,
                max_tokens=6000,  # 20 scenes × ~250 tokens each = ~5000 tokens needed
            )

            scenes = self._normalize_episode_scenes(data.get("scenes", []))
            # Enforce minimum text per scene — short scenes cause < 60s videos
            scenes = self._enforce_scene_text_minimum(scenes, language=language, min_words=min_words)
            return WriterOutput(
                post_format=PostFormat.LONG_EPISODE,
                caption_text=data.get("caption", ""),
                slide_texts=scenes,
                image_prompt_hint=data.get("image_prompt_hint", "Pixar style 3D animation"),
                angle=angle,
                suggested_hashtags=["kids", "learning", "storytime"],
            )
        except Exception as e:
            log.warning("writer_long_episode_failed", error=str(e))
            return self._fallback_output(note, PostFormat.LONG_EPISODE)

    async def _write_short_script(
        self,
        note: ResearchNote,
        angle: ContentAngle,
        language: str,
        proven_hooks: list[str] | None,
    ) -> WriterOutput:
        facts_str = "\n".join(f"• {f}" for f in note.supporting_facts)
        prompt = f"""Konu: "{note.keyword}"
Ana bulgu: {note.main_finding}
Detaylar: {facts_str}
Dil: {"Türkçe" if language == "tr" else "English"}

YouTube Shorts (9:16) video senaryosu oluştur. Toplam süre 40-50 saniye olmalı.
Her sahne için görsel prompt ve seslendirme metni yaz (5-8 sahne).
JSON formatında döndür:
{{
  "caption": "Video açıklaması (hook + hashtag)",
  "scenes": [
    {{
      "index": 0,
      "text": "Seslendirme metni (doğal, akıcı)",
      "image_prompt": "Bu sahne için İngilizce detaylı görsel prompt'u (fotorealistik, sinematik, text içermeyen)",
      "is_hook": true
    }},
    {{
      "index": 1,
      "text": "Seslendirme metni",
      "image_prompt": "Bu sahne için detaylı görsel prompt'u"
    }}
  ],
  "image_prompt_hint": "Genel görsel üslubu için özet (Örn: futuristic photorealistic city etc.)",
  "suggested_hashtags": ["ai", "tech"]
}}

Kurallar:
- SAHNELER: En az 6, en fazla 8 sahne.
- TEXT: Her sahnede seslendirme metni en az 15, en fazla 25 kelime olmalı (Videonun 30-50 saniye sürmesi için bu ÇOK ÖNEMLİ).
- GÖRSELLER: Sahneye özel İngilizce detaylı görsel prompt'u (Pixar style, 3D render, high quality, vibrant colors).
- DİL: Metinleri {language.upper()} dilinde yaz.
- ASLA görsel üzerinde yazı (text) isteme.
"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.system_prompt,
                model=ModelTier.QUALITY,
                max_tokens=1500,
            )

            return WriterOutput(
                post_format=PostFormat.SHORT_SCRIPT,
                caption_text=data.get("caption", ""),
                slide_texts=data.get("scenes", []),
                image_prompt_hint=data.get("image_prompt_hint", note.keyword),
                angle=angle,
                suggested_hashtags=data.get("suggested_hashtags", []),
            )
        except Exception as e:
            log.warning("writer_short_script_failed", keyword=note.keyword, error=str(e))
            return self._fallback_output(note, PostFormat.SHORT_SCRIPT)

    async def _write_carousel(
        self,
        note: ResearchNote,
        angle: ContentAngle,
        language: str,
        proven_hooks: list[str] | None,
    ) -> WriterOutput:
        hook_examples = ""
        if proven_hooks:
            hook_examples = f"\nKanıtlanmış hook örnekleri (bunlara benzer yaz):\n" + "\n".join(
                f"- {h}" for h in proven_hooks[:3]
            )

        facts_str = "\n".join(f"• {f}" for f in note.supporting_facts)
        prompt = f"""Konu: "{note.keyword}"
Ana bulgu: {note.main_finding}
Destekleyici detaylar:
{facts_str}
İçerik açısı: {angle}
Dil: {"Türkçe" if language == "tr" else "English"}
{hook_examples}

Instagram CAROUSEL içeriği oluştur (4-6 slayt). JSON formatında döndür:
{{
  "caption": "Post caption'ı (1-3 cümle, güçlü hook + CTA + emoji)",
  "slides": [
    {{"index": 0, "is_cover": true, "headline": "Dikkat çekici başlık (max 8 kelime)", "subtext": "Alt açıklama (opsiyonel)"}},
    {{"index": 1, "is_cover": false, "headline": "Slide başlığı", "body": "Açıklama metni (2-3 cümle)"}},
    {{"index": 2, "is_cover": false, "headline": "Slide başlığı", "body": "Açıklama metni"}},
    {{"index": 3, "is_cover": false, "headline": "Slide başlığı", "body": "Açıklama metni"}},
    {{"index": 4, "is_cover": false, "headline": "Sonuç / Özet", "body": "Kapanış ve soru (yorum tetikleyici)"}},
    {{"index": 5, "is_cover": false, "headline": "Daha fazlası için takip et 🔔", "body": "@aitopiahub_news"}}
  ],
  "image_prompt_hint": "Görsel için İngilizce açıklama (fotoğrafçıya brief gibi)",
  "suggested_hashtags": ["hashtag1", "hashtag2"]
}}

Kurallar:
- Kapak slaytı en güçlü hook cümlesi olmalı
- Her slayt bağımsız anlaşılabilmeli ama birbirini tamamlamalı
- Caption'da 1 soru sor (yorum artırır)
- Caption'da "kaydet" veya "arkadaşına gönder" davranışını tetikleyen doğal bir cümle olsun
- Abartma yok, sadece gerçekler"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.system_prompt,
                model=ModelTier.QUALITY,
                max_tokens=1000,
            )

            return WriterOutput(
                post_format=PostFormat.CAROUSEL,
                caption_text=data.get("caption", ""),
                slide_texts=data.get("slides", []),
                image_prompt_hint=data.get("image_prompt_hint", note.keyword),
                angle=angle,
                suggested_hashtags=data.get("suggested_hashtags", []),
            )
        except Exception as e:
            log.warning("writer_carousel_failed", keyword=note.keyword, error=str(e))
            return self._fallback_output(note, PostFormat.CAROUSEL)

    async def _write_single(
        self,
        note: ResearchNote,
        angle: ContentAngle,
        language: str,
        proven_hooks: list[str] | None,
    ) -> WriterOutput:
        facts_str = "\n".join(f"• {f}" for f in note.supporting_facts)
        prompt = f"""Konu: "{note.keyword}"
Ana bulgu: {note.main_finding}
Detaylar:
{facts_str}
Dil: {"Türkçe" if language == "tr" else "English"}

Instagram tek görsel post'u için JSON döndür:
{{
  "caption": "2-4 cümle + emoji + soru + CTA. Max 170 kelime.",
  "image_prompt_hint": "Görsel brief İngilizce",
  "suggested_hashtags": ["hashtag1", "hashtag2", "hashtag3"]
}}

Kurallar:
- İlk satır güçlü hook olsun
- 1 adet yorum sorusu olsun
- 1 adet save/share odaklı doğal CTA olsun"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.system_prompt,
                model=ModelTier.QUALITY,
                max_tokens=500,
            )

            return WriterOutput(
                post_format=PostFormat.SINGLE,
                caption_text=data.get("caption", ""),
                slide_texts=None,
                image_prompt_hint=data.get("image_prompt_hint", note.keyword),
                angle=angle,
                suggested_hashtags=data.get("suggested_hashtags", []),
            )
        except Exception as e:
            log.warning("writer_single_failed", keyword=note.keyword, error=str(e))
            return self._fallback_output(note, PostFormat.SINGLE)

    def _fallback_output(self, note: ResearchNote, fmt: PostFormat) -> WriterOutput:
        return WriterOutput(
            post_format=fmt,
            caption_text=f"{note.main_finding}\n\n#AI #Teknoloji",
            slide_texts=None,
            image_prompt_hint=note.keyword,
            angle=ContentAngle.INFORMATIVE,
            suggested_hashtags=["AI", "Teknoloji"],
        )

    def _enforce_scene_text_minimum(
        self, scenes: list[dict], *, language: str = "tr", min_words: int = 30
    ) -> list[dict]:
        """Ensure every scene has at least min_words of narration text.

        If the LLM produced a scene that's too short, we expand it by repeating
        the core sentence with descriptive filler so TTS produces at least ~8–10s
        of audio per scene (target ~14s).  This prevents sub-60s output videos.
        """
        TR_FILLERS = [
            "Şimdi düşün bir dakika.",
            "Bu gerçekten çok ilginç, değil mi?",
            "Haydi birlikte keşfedelim!",
            "Bunu biliyor muydunuz?",
            "İşte tam da bu yüzden bu konu çok önemli.",
        ]
        EN_FILLERS = [
            "Isn't that amazing?",
            "Let's think about that for a moment.",
            "Can you believe it?",
            "That's truly wonderful!",
            "Let's explore this together!",
        ]
        fillers = TR_FILLERS if language == "tr" else EN_FILLERS
        import random as _random
        result = []
        for i, scene in enumerate(scenes):
            text = str(scene.get("text") or "").strip()
            words = text.split()
            if len(words) < min_words:
                # Pad with topic-aware filler until min_words reached
                extra = _random.choice(fillers)
                while len(text.split()) < min_words:
                    text = f"{text} {extra}"
                scene = dict(scene)
                scene["text"] = text.strip()
                log.debug("scene_text_padded", scene_index=i, original_words=len(words), final_words=len(text.split()))
            result.append(scene)
        return result

    def _normalize_episode_scenes(self, scenes: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for i, scene in enumerate(scenes or []):
            if not isinstance(scene, dict):
                continue
            text = str(scene.get("text") or "").strip()
            prompt = str(scene.get("image_prompt") or "").strip()
            asset_query = str(scene.get("asset_query") or prompt or "kids animation").strip()
            mood = str(scene.get("mood") or "playful").strip().lower()
            if mood not in {"playful", "calm", "adventure", "wonder"}:
                mood = "playful"
            motion_hint = str(scene.get("motion_hint") or "gentle camera pan").strip()
            avoid = scene.get("avoid_elements") or ["violence", "horror", "blood"]
            if not isinstance(avoid, list):
                avoid = ["violence", "horror", "blood"]
            normalized.append(
                {
                    "index": int(scene.get("index", i)),
                    "speaker": str(scene.get("speaker") or "Narrator"),
                    "text": text,
                    "image_prompt": prompt or "Pixar style 3D kids illustration",
                    "asset_query": asset_query,
                    "mood": mood,
                    "motion_hint": motion_hint,
                    "avoid_elements": [str(x) for x in avoid],
                }
            )
        return normalized
