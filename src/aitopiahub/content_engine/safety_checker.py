"""
İçerik güvenlik kontrolü:
1. Keyword blocklist
2. Toxicity LLM kontrolü
3. Duplicate içerik tespiti
"""

from __future__ import annotations

from aitopiahub.content_engine.llm_client import LLMClient, ModelTier
from aitopiahub.core.config import AccountConfig
from aitopiahub.core.logging import get_logger
from aitopiahub.trend_engine.deduplicator import ContentDeduplicator

log = get_logger(__name__)


class SafetyChecker:
    def __init__(
        self,
        llm: LLMClient,
        config: AccountConfig,
        deduplicator: ContentDeduplicator,
    ):
        self.llm = llm
        self.config = config
        self.deduplicator = deduplicator
        self._blocked = [kw.lower() for kw in config.blocked_keywords]

    async def check(self, caption: str) -> tuple[bool, str]:
        """
        (is_safe, reason) döndür.
        is_safe=False ise reason nedeni açıklar.
        """

        # L1: Keyword blocklist
        caption_lower = caption.lower()
        for blocked in self._blocked:
            if blocked in caption_lower:
                return False, f"Engellenen keyword: '{blocked}'"

        # L2: Duplicate içerik
        if await self.deduplicator.is_duplicate(caption):
            return False, "Bu içerik daha önce paylaşıldı"

        # L3: LLM toxicity/spam kontrolü
        is_clean, reason = await self._llm_check(caption)
        if not is_clean:
            return False, f"Güvenlik kontrolü: {reason}"

        return True, "OK"

    async def _llm_check(self, caption: str) -> tuple[bool, str]:
        prompt = f"""Bu Instagram gönderisi bir teknoloji haber hesabı için. Kontrol et:

"{caption[:500]}"

JSON döndür:
{{
  "is_safe": true,
  "reasons": []
}}

Şu durumlarda is_safe=false:
- Yanlış bilgi / dezenformasyon içeriyor
- Nefret söylemi, taciz, şiddet içeriyor
- Spam veya clickbait (gerçekleşmeyen iddialar)
- Telif hakkı ihlali riski

Eğer içerik normal ve meşruysa is_safe=true."""

        try:
            data = await self.llm.complete_json(
                prompt,
                model=ModelTier.FAST,
                max_tokens=150,
            )
            is_safe = bool(data.get("is_safe", True))
            reasons = data.get("reasons", [])
            reason_str = "; ".join(reasons) if reasons else ""
            return is_safe, reason_str
        except Exception as e:
            log.warning("safety_check_llm_error", error=str(e))
            return True, ""  # LLM hatası → güvenli varsay
