"""
Groq API wrapper — Llama 3.3 70B üretim, Llama 3.1 8B hız.
Otomatik Ollama fallback.
"""

from __future__ import annotations

import json
from enum import Enum

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from aitopiahub.core.config import get_settings
from aitopiahub.core.exceptions import LLMError
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)

try:
    from groq import AsyncGroq
except Exception:  # pragma: no cover - optional dependency in some environments
    AsyncGroq = None  # type: ignore[assignment]


class ModelTier(str, Enum):
    QUALITY = "quality"   # Llama 3.3 70B — içerik üretimi
    FAST = "fast"         # Llama 3.1 8B — sınıflandırma, filtreleme


GROQ_MODELS = {
    ModelTier.QUALITY: "llama-3.3-70b-versatile",  # 70B for high-quality scene generation
    ModelTier.FAST: "llama-3.1-8b-instant",
}


class LLMClient:
    """Groq API ile iletişim + Ollama fallback."""

    def __init__(self):
        settings = get_settings()
        self._groq = AsyncGroq(api_key=settings.groq_api_key) if AsyncGroq else None
        self._ollama_base = settings.ollama_base_url

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(
        self,
        prompt: str,
        model: str | ModelTier = ModelTier.QUALITY,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.85,
        json_mode: bool = False,
    ) -> str:
        """LLM'e istek gönder, metin döndür."""
        groq_model = GROQ_MODELS.get(model, GROQ_MODELS[ModelTier.QUALITY])

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": groq_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        if self._groq is None:
            log.warning("groq_client_unavailable_falling_back_to_ollama")
            return await self._ollama_complete(prompt, system, max_tokens, temperature)

        try:
            resp = await self._groq.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            log.debug(
                "llm_complete",
                model=groq_model,
                prompt_len=len(prompt),
                response_len=len(content),
            )
            return content
        except Exception as e:
            err_str = str(e)
            # If 70B daily token limit exhausted, retry immediately with 8B
            # (8B has 6M TPD vs 100K TPD for 70B — much more headroom).
            if "tokens per day" in err_str and groq_model == GROQ_MODELS[ModelTier.QUALITY]:
                log.warning("groq_70b_daily_limit_falling_back_to_8b", error=err_str[:120])
                kwargs["model"] = GROQ_MODELS[ModelTier.FAST]
                # llama-3.1-8b-instant has a smaller per-request window; cap
                # max_tokens at 4096 to avoid 413 "Request too large" errors.
                kwargs["max_tokens"] = min(kwargs.get("max_tokens", 800), 4096)
                try:
                    resp = await self._groq.chat.completions.create(**kwargs)
                    content = resp.choices[0].message.content or ""
                    log.info("groq_8b_fallback_success", prompt_len=len(prompt))
                    return content
                except Exception as e2:
                    log.warning("groq_8b_fallback_failed", error=str(e2)[:120])
            log.warning("groq_error_falling_back_to_ollama", error=err_str[:200])
            return await self._ollama_complete(prompt, system, max_tokens, temperature)

    async def _ollama_complete(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Ollama local fallback."""
        import aiohttp

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "llama3.3:70b",
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._ollama_base}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        raise LLMError(f"Ollama error: {resp.status}")
                    data = await resp.json()
                    return data["message"]["content"]
        except Exception as e:
            raise LLMError(f"Tüm LLM fallback'ler başarısız: {e}") from e

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        model: str | ModelTier = ModelTier.QUALITY,
        max_tokens: int = 800,
    ) -> dict:
        """JSON çıktı garantili LLM çağrısı."""
        response = await self.complete(
            prompt,
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=0.3,
            json_mode=True,
        )
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # JSON parse hata → manuel bul
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
            raise LLMError(f"JSON parse edilemedi: {response[:300]}")
