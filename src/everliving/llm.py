"""LLM client abstraction. Real calls go through AnthropicLLMClient; tests inject a fake."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str: ...


class AnthropicLLMClient:
    """Thin wrapper around the Anthropic API. Requires ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model: str = "claude-sonnet-5") -> None:
        import anthropic  # lazy import: only needed for real runs, not for mocked tests

        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, system_prompt: str, user_message: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
