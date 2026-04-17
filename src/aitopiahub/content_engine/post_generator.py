"""
Ana içerik üretim koordinatörü.
4 ajanı sırayla çalıştırır ve A/B varyantları oluşturur.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from aitopiahub.content_engine.agents.editor import EditorAgent
from aitopiahub.content_engine.agents.localizer import LocalizerAgent
from aitopiahub.content_engine.agents.researcher import ResearchNote, ResearcherAgent
from aitopiahub.content_engine.agents.writer import WriterAgent
from aitopiahub.content_engine.hashtag_optimizer import HashtagOptimizer
from aitopiahub.content_engine.llm_client import LLMClient
from aitopiahub.core.config import AccountConfig
from aitopiahub.core.constants import ContentAngle, PostFormat
from aitopiahub.core.logging import get_logger
from aitopiahub.trend_engine.rss_fetcher import RSSItem
from aitopiahub.trend_engine.trend_scorer import ScoredTrend

log = get_logger(__name__)


@dataclass
class GeneratedPost:
    variant_group: uuid.UUID
    variant_label: str           # 'A' veya 'B'
    post_format: str
    language: str
    caption_text: str
    hashtags: list[str]
    slide_texts: list[dict] | None
    image_prompt_hint: str
    researcher_output: dict
    writer_output: dict
    editor_output: dict
    quality_score: float
    approved: bool


class PostGenerator:
    """
    Researcher → Writer → Editor → Localizer pipeline'ını yönetir.
    Her trend için A+B olmak üzere 2 variant üretir.
    """

    def __init__(self, account_config: AccountConfig, llm: LLMClient):
        self.config = account_config
        self.researcher = ResearcherAgent(llm)
        self.writer = WriterAgent(llm, persona=account_config.llm_system_prompt_variant)
        self.editor = EditorAgent(llm, min_quality=account_config.min_quality_score)
        self.localizer = LocalizerAgent(llm)
        self.hashtag_optimizer = HashtagOptimizer(account_config)

    async def generate(
        self,
        trend: ScoredTrend,
        related_items: list[RSSItem],
        post_format: PostFormat = PostFormat.CAROUSEL,
        proven_hooks: list[str] | None = None,
    ) -> list[GeneratedPost]:
        """Bir trend için A/B varyant çifti üret."""

        # Adım 1: Researcher
        note = await self.researcher.research(
            trend.keyword,
            related_items,
            self.config.niche,
        )

        variant_group = uuid.uuid4()
        posts = []

        # Variant A: Bilgilendirici açı
        post_a = await self._generate_variant(
            note, post_format, ContentAngle.INFORMATIVE,
            variant_group, "A", proven_hooks=proven_hooks,
        )
        if post_a:
            posts.append(post_a)

        # Variant B: Engaging açı (soru/tartışma)
        post_b = await self._generate_variant(
            note, post_format, ContentAngle.ENGAGING,
            variant_group, "B", proven_hooks=proven_hooks,
        )
        if post_b:
            posts.append(post_b)

        log.info(
            "post_generator_done",
            keyword=trend.keyword,
            variants=len(posts),
            format=post_format,
        )
        return posts

    async def _generate_variant(
        self,
        note: ResearchNote,
        post_format: PostFormat,
        angle: ContentAngle,
        variant_group: uuid.UUID,
        label: str,
        proven_hooks: list[str] | None = None,
    ) -> GeneratedPost | None:
        try:
            # Adım 2: Writer
            writer_out = await self.writer.write(
                note,
                post_format=post_format,
                angle=angle,
                language=self.config.language_primary,
                proven_hooks=proven_hooks,
            )

            # Adım 3: Editor (self-critique loop)
            research_context = f"{note.main_finding}. {'; '.join(note.supporting_facts[:3])}"
            editor_result = await self.editor.review(
                writer_out,
                research_context=research_context,
                niche=self.config.niche,
            )

            # Adım 4: Localizer
            localized = await self.localizer.localize(
                editor_result.output,
                primary_language=self.config.language_primary,
            )

            # Hashtag optimizasyonu
            all_hashtags = editor_result.output.suggested_hashtags
            optimized_hashtags = await self.hashtag_optimizer.optimize(
                all_hashtags,
                note.keyword,
            )

            caption = (
                localized.tr_caption
                if self.config.language_primary == "tr"
                else localized.en_caption
            )
            caption = self._enhance_caption(caption, angle)

            return GeneratedPost(
                variant_group=variant_group,
                variant_label=label,
                post_format=post_format,
                language=self.config.language_primary,
                caption_text=caption,
                hashtags=optimized_hashtags,
                slide_texts=(
                    localized.tr_slide_texts
                    if self.config.language_primary == "tr"
                    else localized.en_slide_texts
                ),
                image_prompt_hint=editor_result.output.image_prompt_hint,
                researcher_output={
                    "main_finding": note.main_finding,
                    "supporting_facts": note.supporting_facts,
                    "novelty_score": note.novelty_score,
                },
                writer_output={
                    "angle": angle,
                    "format": post_format,
                },
                editor_output={
                    "quality_score": editor_result.quality_score,
                    "hook_strength": editor_result.hook_strength,
                    "feedback": editor_result.feedback,
                },
                quality_score=editor_result.quality_score,
                approved=editor_result.approved,
            )

        except Exception as e:
            log.error(
                "variant_generation_failed",
                label=label,
                angle=angle,
                error=str(e),
            )
            return None

    def _enhance_caption(self, caption: str, angle: ContentAngle) -> str:
        text = (caption or "").strip()
        if not text:
            return text

        # İlk satırın güçlü bir hook ile başlamasını teşvik et.
        first_line, *rest = text.splitlines()
        if len(first_line) < 18:
            first_line = f"Bugünün kritik AI gelişmesi: {first_line}".strip()

        merged = "\n".join([first_line] + rest).strip()

        # Yorum tetikleyici soru eksikse ekle.
        if "?" not in merged:
            question = (
                "Sence bu gelişme en çok hangi sektörü etkileyecek?"
                if angle == ContentAngle.INFORMATIVE
                else "Sen olsan bu teknolojiyi günlük hayatta nerede kullanırdın?"
            )
            merged = f"{merged}\n\n{question}"

        # Takip CTA'sı eksikse ekle.
        lowered = merged.lower()
        if "takip" not in lowered and "follow" not in lowered:
            merged = f"{merged}\nDaha fazla AI gündemi için takip etmeyi unutma."

        # Caption çok uzarsa daha okunur bir limite çek.
        if len(merged) > 1800:
            merged = merged[:1797].rstrip() + "..."
        return merged
