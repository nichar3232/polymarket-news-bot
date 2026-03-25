"""
Unified LLM client with automatic fallback chain.

Priority: Groq (Llama 3.3 70B) → Google Gemini 1.5 Flash → Ollama local

All free-tier. Groq is fastest at ~500 tok/s.
Runs async so it never blocks the main trading loop.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from enum import Enum

from loguru import logger

try:
    from groq import AsyncGroq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    import ollama as ollama_lib
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False


class LLMProvider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    NONE = "none"


@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    latency_ms: float
    tokens_used: int = 0

    def parse_json(self) -> dict:
        """Extract JSON from response, handling markdown code blocks."""
        text = self.content.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise


class LLMClient:
    """
    Multi-provider LLM client with automatic fallback.
    """

    GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    GEMINI_MODEL = "gemini-1.5-flash"
    OLLAMA_MODEL = "llama3.2"

    def __init__(
        self,
        groq_api_key: str = "",
        gemini_api_key: str = "",
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.2",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._groq_key = groq_api_key
        self._gemini_key = gemini_api_key
        self._ollama_url = ollama_base_url
        self._ollama_model = ollama_model
        self._timeout = timeout_seconds

        # Initialize clients
        self._groq: AsyncGroq | None = None
        if HAS_GROQ and groq_api_key:
            self._groq = AsyncGroq(api_key=groq_api_key)

        self._gemini_client = None
        if HAS_GEMINI and gemini_api_key:
            self._gemini_client = _genai.Client(api_key=gemini_api_key)

        self._available_providers = self._detect_providers()
        logger.info(f"LLM providers available: {[p.value for p in self._available_providers]}")

    def _detect_providers(self) -> list[LLMProvider]:
        providers = []
        if HAS_GROQ and self._groq_key:
            providers.append(LLMProvider.GROQ)
        if HAS_GEMINI and self._gemini_key:
            providers.append(LLMProvider.GEMINI)
        if HAS_OLLAMA:
            providers.append(LLMProvider.OLLAMA)
        return providers

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Get completion from the best available provider.
        Falls back through the chain automatically.
        """
        last_error: Exception | None = None

        for provider in self._available_providers:
            try:
                if provider == LLMProvider.GROQ:
                    return await self._groq_complete(system_prompt, user_prompt, temperature, max_tokens)
                elif provider == LLMProvider.GEMINI:
                    return await self._gemini_complete(system_prompt, user_prompt, temperature, max_tokens)
                elif provider == LLMProvider.OLLAMA:
                    return await self._ollama_complete(system_prompt, user_prompt, temperature, max_tokens)
            except Exception as e:
                logger.warning(f"LLM provider {provider.value} failed: {e}")
                last_error = e
                continue

        # All providers failed
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    async def _groq_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        t0 = time.time()
        response = await asyncio.wait_for(
            self._groq.chat.completions.create(
                model=self.GROQ_MODELS[0],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            timeout=self._timeout,
        )
        latency = (time.time() - t0) * 1000
        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        return LLMResponse(
            content=content,
            provider=LLMProvider.GROQ,
            model=self.GROQ_MODELS[0],
            latency_ms=latency,
            tokens_used=tokens,
        )

    async def _gemini_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        t0 = time.time()
        response = await asyncio.wait_for(
            asyncio.to_thread(
                self._gemini_client.models.generate_content,
                model=self.GEMINI_MODEL,
                contents=user_prompt,
                config=_genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            ),
            timeout=self._timeout,
        )
        latency = (time.time() - t0) * 1000
        content = response.text or ""
        return LLMResponse(
            content=content,
            provider=LLMProvider.GEMINI,
            model=self.GEMINI_MODEL,
            latency_ms=latency,
        )

    async def _ollama_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        t0 = time.time()
        response = await asyncio.wait_for(
            asyncio.to_thread(
                ollama_lib.chat,
                model=self._ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={"temperature": temperature, "num_predict": max_tokens},
            ),
            timeout=self._timeout,
        )
        latency = (time.time() - t0) * 1000
        content = response["message"]["content"] if isinstance(response, dict) else str(response)
        return LLMResponse(
            content=content,
            provider=LLMProvider.OLLAMA,
            model=self._ollama_model,
            latency_ms=latency,
        )

    @property
    def primary_provider(self) -> LLMProvider:
        return self._available_providers[0] if self._available_providers else LLMProvider.NONE

    def is_available(self) -> bool:
        return len(self._available_providers) > 0
