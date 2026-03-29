"""Claude Haiku / Sonnet wrapper via the Anthropic SDK.

Provides a unified async interface for LLM calls. Defaults to Haiku
for speed/cost; callers can request Sonnet for complex reasoning.
"""

import logging
from typing import Any

import anthropic

from core.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# Model identifiers
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"


class LLMClient:
    """Async wrapper around Anthropic's message API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY must be set to use LLMClient"
                )
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            logger.info("Anthropic async client initialized")
        return self._client

    async def ask(
        self,
        prompt: str,
        *,
        system: str = "",
        model: str = HAIKU,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """Send a single-turn message and return the text response."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        logger.info("LLM request: model=%s tokens=%d", model, max_tokens)
        response = await self.client.messages.create(**kwargs)
        text = response.content[0].text
        logger.info(
            "LLM response: %d chars, stop=%s", len(text), response.stop_reason
        )
        return text

    async def ask_json(
        self,
        prompt: str,
        *,
        system: str = "Return only valid JSON, no preamble.",
        model: str = HAIKU,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """Convenience: ask with JSON-oriented system prompt."""
        return await self.ask(
            prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def ask_complex(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """Route to Sonnet for complex reasoning tasks."""
        return await self.ask(
            prompt,
            system=system,
            model=SONNET,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def health_check(self) -> bool:
        """Verify the API key is valid by counting tokens (cheap call)."""
        try:
            await self.client.messages.count_tokens(
                model=HAIKU,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as exc:
            logger.warning("LLM health check failed: %s", exc)
            return False
