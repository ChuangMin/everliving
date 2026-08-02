"""LLM client abstraction. Real calls go through AnthropicLLMClient; tests inject a fake."""

from __future__ import annotations

import os
import sqlite3
from typing import Protocol

from everliving import db

# Cheap default so casual dev/playtest sessions don't rack up cost. Override with
# EVERLIVING_MODEL (e.g. "claude-sonnet-5") once you're past kicking the tires.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_message: str) -> str: ...

    # Optional: after a call, holds {"model", "input_tokens", "output_tokens"} so callers
    # can log cost. Clients that can't report usage simply leave this as None.
    last_usage: dict | None


def log_usage(
    conn: sqlite3.Connection, llm: LLMClient, agent_id: int | None, purpose: str
) -> None:
    """Persist the token usage of the most recent call, if the client reported any."""
    usage = getattr(llm, "last_usage", None)
    if not usage:
        return
    db.record_llm_call(
        conn,
        agent_id=agent_id,
        purpose=purpose,
        model=usage["model"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
    )


class AnthropicLLMClient:
    """Thin wrapper around the Anthropic API. Requires ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic  # lazy import: only needed for real runs, not for mocked tests

        self._client = anthropic.Anthropic()
        self._model = model or os.environ.get("EVERLIVING_MODEL", DEFAULT_MODEL)
        self.last_usage: dict | None = None

    def complete(self, system_prompt: str, user_message: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        self.last_usage = {
            "model": self._model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return response.content[0].text
