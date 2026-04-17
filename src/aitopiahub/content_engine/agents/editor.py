"""
Ajan 3 — Editor (Self-Critique Loop)
Görev: Writer çıktısını değerlendir, kalite puanı ver, yetersizse revize et.
Max 2 iterasyon. Minimum geçer puan: 75/100.
"""

from __future__ import annotations

from dataclasses import dataclass

from aitopiahub.content_engine.agents.writer import WriterOutput
from aitopiahub.content_engine.llm_client import LLMClient, ModelTier
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

MIN_QUALITY_SCORE = 75
MAX_ITERATIONS = 2


@dataclass
class EditorResult:
    output: WriterOutput
    quality_score: float
    hook_strength: float
    factual_accuracy: float
    engagement_potential: float
    clarity: float
    brand_voice: float
    format_fit: float
    revision_count: int
    approved: bool
    feedback: str


class EditorAgent:
    """
    Writer çıktısını eleştirir ve gerekirse revize eder.
    Composite kalite puanı:
      0.25*hook + 0.20*factual + 0.20*engagement + 0.15*clarity + 0.10*brand + 0.10*format
    """

    SYSTEM_PROMPT = """Sen sert ama adil bir sosyal medya içerik editörüsün.
Görüşlerin doğrudan ve yapıcı. Kalite konusunda taviz vermiyorsun.
Abartılı, clickbait veya belirsiz içerikleri reddediyorsun."""

    def __init__(self, llm: LLMClient, min_quality: int = MIN_QUALITY_SCORE):
        self.llm = llm
        self.min_quality = min_quality

    async def review(
        self,
        writer_output: WriterOutput,
        research_context: str,
        niche: str = "news",
    ) -> EditorResult:
        """İçeriği değerlendir, gerekirse revize et."""

        current = writer_output
        revision_count = 0

        for iteration in range(MAX_ITERATIONS + 1):
            result = await self._evaluate(current, research_context, niche)

            if result.quality_score >= self.min_quality:
                log.info(
                    "editor_approved",
                    score=result.quality_score,
                    revisions=revision_count,
                )
                return result

            if iteration < MAX_ITERATIONS:
                log.info(
                    "editor_requesting_revision",
                    score=result.quality_score,
                    iteration=iteration + 1,
                    feedback=result.feedback[:100],
                )
                revised = await self._revise(current, result.feedback, research_context)
                if revised:
                    current = revised
                    revision_count += 1

        # Max iterasyon sonunda — kalite düşük olsa da döndür ama işaretle
        final_result = await self._evaluate(current, research_context, niche)
        final_result.revision_count = revision_count
        final_result.approved = final_result.quality_score >= self.min_quality
        log.info(
            "editor_final_decision",
            score=final_result.quality_score,
            approved=final_result.approved,
        )
        return final_result

    async def _evaluate(
        self, output: WriterOutput, research_context: str, niche: str
    ) -> EditorResult:
        content_preview = output.caption_text[:500]
        if output.slide_texts:
            slides_preview = str(output.slide_texts)[:300]
            content_preview += f"\n\nSlaytlar: {slides_preview}"

        prompt = f"""İçerik niş'i: {niche}
Format: {output.post_format}

Caption:
{output.caption_text}

Araştırma bağlamı: {research_context[:400]}

Bu içeriği şu kriterlere göre 0-100 arasında puanla ve JSON döndür:
{{
  "hook_strength": 85,
  "factual_accuracy": 90,
  "engagement_potential": 80,
  "clarity": 88,
  "brand_voice": 85,
  "format_fit": 82,
  "composite": 85,
  "feedback": "Varsa spesifik eleştiri ve öneri. Yoksa 'Onaylandı'.",
  "approved": true
}}

Puanlama rehberi:
- hook_strength: İlk cümle ilk 2 kelimede dikkat çekiyor mu?
- factual_accuracy: Araştırma bağlamıyla tutarlı mı, abartı var mı?
- engagement_potential: Yorum/kaydetme/paylaşma tetikler mi?
- clarity: Net ve anlaşılır mı, jargon fazla mı?
- brand_voice: Güvenilir, otoritatif ama samimi mi?
- format_fit: Instagram formatına uygun mu (uzunluk, emoji kullanımı)?
- composite: Ağırlıklı ortalama (hook*0.25 + factual*0.20 + engagement*0.20 + clarity*0.15 + brand*0.10 + format*0.10)"""

        try:
            data = await self.llm.complete_json(
                prompt,
                system=self.SYSTEM_PROMPT,
                model=ModelTier.QUALITY,
                max_tokens=400,
            )

            composite = float(data.get("composite", 70))
            return EditorResult(
                output=output,
                quality_score=composite,
                hook_strength=float(data.get("hook_strength", 70)),
                factual_accuracy=float(data.get("factual_accuracy", 70)),
                engagement_potential=float(data.get("engagement_potential", 70)),
                clarity=float(data.get("clarity", 70)),
                brand_voice=float(data.get("brand_voice", 70)),
                format_fit=float(data.get("format_fit", 70)),
                revision_count=0,
                approved=composite >= self.min_quality,
                feedback=data.get("feedback", ""),
            )
        except Exception as e:
            log.warning("editor_evaluate_failed", error=str(e))
            return EditorResult(
                output=output,
                quality_score=70.0,
                hook_strength=70.0,
                factual_accuracy=70.0,
                engagement_potential=70.0,
                clarity=70.0,
                brand_voice=70.0,
                format_fit=70.0,
                revision_count=0,
                approved=False,
                feedback=str(e),
            )

    async def _revise(
        self, output: WriterOutput, feedback: str, research_context: str
    ) -> WriterOutput | None:
        """Geri bildirime göre içeriği revize et."""
        prompt = f"""Mevcut caption:
{output.caption_text}

Editör geri bildirimi:
{feedback}

Araştırma bağlamı: {research_context[:300]}

Geri bildirimi dikkate alarak caption'ı revize et. Sadece revize edilmiş caption metnini döndür, başka hiçbir şey yazma."""

        try:
            revised_text = await self.llm.complete(
                prompt,
                model=ModelTier.QUALITY,
                max_tokens=400,
                temperature=0.7,
            )
            revised = WriterOutput(
                post_format=output.post_format,
                caption_text=revised_text.strip(),
                slide_texts=output.slide_texts,
                image_prompt_hint=output.image_prompt_hint,
                angle=output.angle,
                suggested_hashtags=output.suggested_hashtags,
            )
            return revised
        except Exception as e:
            log.warning("editor_revise_failed", error=str(e))
            return None
