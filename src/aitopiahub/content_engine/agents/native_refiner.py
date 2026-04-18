"""
Ajan 5 — Native Refiner (Kusursuz Türkçe Katmanı)
Görev: Çeviri kokan veya yapay metinleri doğal, akıcı ve edebi bir Türkçeye dönüştürmek.
"""

from __future__ import annotations

from aitopiahub.content_engine.llm_client import LLMClient, ModelTier
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

class NativeRefinerAgent:
    """
    Metinleri 'çeviri' hisinden kurtarıp, hedef dilde (özellikle Türkçe) 
    doğal bir anlatıcı tarafından yazılmış gibi yeniden kurgular.
    """

    SYSTEM_PROMPT = """Sen bir Türk çocuk edebiyatı yazarı ve profesyonel masal anlatıcısısın.
Görevin: Sana verilen Türkçe metinleri, anlamı bozmadan, çocukların seveceği, akıcı, doğal ve zengin bir Türkçe ile yeniden yazmak.

Kurallar:
1. 'Çeviri' kokan (Ingilizce cümle yapısını takip eden) ifadeleri tamamen temizle.
2. Çocuklara yönelik sıcak hitaplar ve deyimler kullan (Örn: 'Gelin bakalım çocuklar', 'İnanmazsınız ama...').
3. Cümle akışını melodik ve merak uyandırıcı hale getir.
4. Asla anlamı değiştirme, sadece anlatım tarzını kusursuzlaştır.
5. Eğer metinde diyalog varsa, karakterin doğasına uygun samimi bir dil kullan."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def refine(self, text: str) -> str:
        """Metni baştan aşağı doğal Türkçe ile süsle."""
        
        prompt = f"""Lütfen bu metni 'Kusursuz ve Doğal Türkçe' ile çocuklara anlatılıyormuş gibi yeniden yaz:\n\n{text}"""

        try:
            # Use FAST (8B) tier for per-scene refinement to preserve the 70B
            # daily token budget for the main script generation call.
            refined = await self.llm.complete(
                prompt,
                system=self.SYSTEM_PROMPT,
                model=ModelTier.FAST,
                max_tokens=2000,
            )
            log.info("native_refinement_success", original_len=len(text), refined_len=len(refined))
            return refined.strip()
        except Exception as e:
            log.warning("native_refinement_failed", error=str(e))
            return text # Fallback to original
