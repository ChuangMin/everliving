"""LLM client abstraction. Real calls go through AnthropicLLMClient; tests inject a fake."""

from __future__ import annotations

import os
from typing import Protocol

# Cheap default so casual dev/playtest sessions don't rack up cost. Override with
# EVERLIVING_MODEL (e.g. "claude-sonnet-5") once you're past kicking the tires.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str: ...


class AnthropicLLMClient:
    """Thin wrapper around the Anthropic API. Requires ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic  # lazy import: only needed for real runs, not for mocked tests

        self._client = anthropic.Anthropic()
        self._model = model or os.environ.get("EVERLIVING_MODEL", DEFAULT_MODEL)

    def complete(self, system_prompt: str, user_message: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
