"""
Multi-provider LLM abstraction with automatic fallback chain.
Providers: Anthropic (Claude) → OpenAI (GPT) → Ollama (local)
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Literal, Optional

from src.config.settings import SETTINGS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Provider Interface
# ─────────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Send a prompt and return the completion."""
        ...

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Send a chat conversation and return the assistant's reply."""
        # Default: flatten messages into a prompt
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        prompt = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages if m["role"] != "system"
        )
        return self.complete(prompt, system, temperature=temperature, max_tokens=max_tokens, **kwargs)

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""
        ...


# ─────────────────────────────────────────────────────────────────
# Anthropic / Claude
# ─────────────────────────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        api_key = SETTINGS.ANTHROPIC_API_KEY
        self.model = SETTINGS.ANTHROPIC_MODEL
        self._client: Optional[Any] = None
        if api_key:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=api_key)
            except ImportError:
                logger.warning("anthropic package not installed")

    def is_available(self) -> bool:
        return SETTINGS.is_provider_available("anthropic")

    def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        if not self._client:
            raise RuntimeError("Anthropic client not initialized")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "user", "content": system + "\n\n" + prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        # Synchronous wrapper
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        response = loop.run_until_complete(
            self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        )
        return response.content[0].text


# ─────────────────────────────────────────────────────────────────
# OpenAI / GPT
# ─────────────────────────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        api_key = SETTINGS.OPENAI_API_KEY
        base_url = SETTINGS.OPENAI_BASE_URL
        self.model = SETTINGS.OPENAI_MODEL
        self._client: Optional[Any] = None
        if api_key:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            except ImportError:
                logger.warning("openai package not installed")

    def is_available(self) -> bool:
        return SETTINGS.is_provider_available("openai")

    def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        if not self._client:
            raise RuntimeError("OpenAI client not initialized")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        response = loop.run_until_complete(
            self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        )
        return response.choices[0].message.content or ""


# ─────────────────────────────────────────────────────────────────
# Ollama (local)
# ─────────────────────────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        self.base_url = SETTINGS.OLLAMA_BASE_URL
        self.model = SETTINGS.OLLAMA_MODEL

    def is_available(self) -> bool:
        if not SETTINGS.is_provider_available("ollama"):
            return False
        # Actually ping the Ollama server to verify it's reachable
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/",
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        import urllib.request
        import json

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "temperature": temperature,
            "options": {"num_predict": max_tokens},
            "stream": False,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except Exception as e:
            raise RuntimeError(f"Ollama request failed: {e}")


# ─────────────────────────────────────────────────────────────────
# Fallback Chain
# ─────────────────────────────────────────────────────────────────

class FallbackLLM:
    """
    Multi-provider LLM with automatic fallback.
    Tries providers in order (SETTINGS.LLM_PROVIDER_ORDER) until one succeeds.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        for provider_name in SETTINGS.LLM_PROVIDER_ORDER:
            if provider_name == "anthropic":
                self._providers["anthropic"] = AnthropicProvider()
            elif provider_name == "openai":
                self._providers["openai"] = OpenAIProvider()
            elif provider_name == "ollama":
                self._providers["ollama"] = OllamaProvider()

        # Build ordered list of available providers
        self._available: list[tuple[str, LLMProvider]] = [
            (name, prov) for name, prov in self._providers.items() if prov.is_available()
        ]

        if not self._available:
            logger.warning(
                "No LLM providers configured. Set ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, or OLLAMA_BASE_URL in .env"
            )

    @property
    def primary_provider(self) -> Optional[LLMProvider]:
        """Return the first available provider."""
        if self._available:
            return self._available[0][1]
        return None

    @property
    def provider_info(self) -> dict[str, bool]:
        return {name: prov.is_available() for name, prov in self._providers.items()}

    def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 120,
        **kwargs: Any,
    ) -> str:
        """
        Try each provider in order. On exception, log and fall back to the next.
        """
        errors: list[str] = []

        for name, provider in self._available:
            try:
                logger.info(f"Trying LLM provider: {name}")
                result = provider.complete(
                    prompt,
                    system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                logger.info(f"Provider {name} succeeded")
                return result
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Provider {name} failed: {exc}")
                errors.append(f"{name}: {exc}")
                continue

        raise RuntimeError(
            f"All LLM providers failed. Errors:\n" + "\n".join(errors)
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Try each provider in order for a chat completion."""
        errors: list[str] = []

        for name, provider in self._available:
            try:
                return provider.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Provider {name} chat failed: {exc}")
                errors.append(f"{name}: {exc}")
                continue

        raise RuntimeError(
            f"All LLM providers failed for chat. Errors:\n" + "\n".join(errors)
        )


# ─────────────────────────────────────────────────────────────────
# Singleton instance
# ─────────────────────────────────────────────────────────────────

_llm_instance: Optional[FallbackLLM] = None


def get_llm() -> FallbackLLM:
    """Return the singleton FallbackLLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = FallbackLLM()
    return _llm_instance
