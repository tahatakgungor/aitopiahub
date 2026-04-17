"""
Groq API wrapper — Llama 3.3 70B üretim, Llama 3.1 8B hız.
Otomatik Ollama fallback.
"""

from __future__ import annotations

import json
from enum import Enum

from groq import AsyncGroq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from aitopiahub.core.config import get_settings
from aitopiahub.core.exceptions import LLMError
from aitopiahub.core.logging import get_logger

log = get_logger(__name__)


class ModelTier(str, Enum):
    QUALITY = "quality"   # Llama 3.3 70B — içerik üretimi
    FAST = "fast"         # Llama 3.1 8B — sınıflandırma, filtreleme


GROQ_MODELS = {
    ModelTier.QUALITY: "llama-3.3-70b-versatile",
    ModelTier.FAST: "llama-3.1-8b-instant",
}


class LLMClient:
    """Groq API ile iletişim + Ollama fallback."""

    def __init__(self):
        settings = get_settings()
        self._groq = AsyncGroq(api_key=settings.groq_api_key)
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
            log.warning("groq_error_falling_back_to_ollama", error=str(e))
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
