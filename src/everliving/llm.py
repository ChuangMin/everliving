"""LLM client abstraction. Real calls go through AnthropicLLMClient; tests inject a fake."""

from __future__ import annotations

import os
import sqlite3
from typing import Protocol

from everliving import db

# Cheap default so casual dev/playtest sessions don't rack up cost. Override with
# EVERLIVING_MODEL (e.g. "claude-sonnet-5") once you're past kicking the tires.
DEFAULT_MODEL = "claude-haiku-4-5"

# Replies are 2-4 sentences, so this is generous for output alone. The headroom is for
# models where thinking is on by default (Claude 5 family) — there max_tokens caps
# thinking *and* text together, and a tight limit truncates the reply mid-sentence.
MAX_TOKENS = 2048


class LLMRefusal(RuntimeError):
    """The model declined to answer. Distinct from a network or auth failure."""


class LLMAuthError(RuntimeError):
    """No usable credentials. Surfaces on the first call, not at construction —
    the SDK resolves credentials lazily, so a missing key looks fine until you call."""


class LLMUnavailable(RuntimeError):
    """The API couldn't serve the request — no credit, rate limited, outage, offline.

    Rephrasing won't help, so callers should stop rather than retry. The server's own
    message is carried through: it usually says exactly what to do.
    """


def _server_message(exc) -> str:
    """The human-readable half of an API error, without the status-code noise."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(exc)


def extract_text(blocks) -> str:
    """Join the text blocks of a response, skipping thinking and tool blocks.

    Indexing content[0] would break the moment someone points EVERLIVING_MODEL at a
    model where thinking is on by default — block 0 is a thinking block there, and it
    has no .text at all.
    """
    return "".join(
        block.text for block in blocks if getattr(block, "type", None) == "text"
    ).strip()


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

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._model = model or os.environ.get("EVERLIVING_MODEL", DEFAULT_MODEL)
        self.last_usage: dict | None = None

    def complete(self, system_prompt: str, user_message: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except self._anthropic.AuthenticationError as exc:
            # A credential exists but the server rejected it (401). Must precede
            # APIStatusError below — it's a subclass.
            raise LLMAuthError(str(exc)) from exc
        except self._anthropic.APIStatusError as exc:
            # Billing, rate limits, server errors. The most common one in practice is
            # an empty credit balance, which arrives as a 400 — not something the
            # player can fix by rewording, so surface the server's text and stop.
            raise LLMUnavailable(_server_message(exc)) from exc
        except self._anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f"連不上 Anthropic API:{exc}") from exc
        except TypeError as exc:
            # No credential could be resolved at all — the SDK raises a plain TypeError
            # from header validation before any request goes out. Narrow by message so
            # a genuine TypeError in our own code still surfaces as a bug.
            if "authentication" not in str(exc).lower():
                raise
            raise LLMAuthError(str(exc)) from exc
        self.last_usage = {
            "model": self._model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        if response.stop_reason == "refusal":
            raise LLMRefusal("模型拒絕回應這個請求。")
        return extract_text(response.content)
