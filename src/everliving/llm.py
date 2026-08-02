"""LLM client abstraction. Real calls go through a provider client; tests inject a fake.

Two providers are supported so the project isn't hostage to one account's credit
balance. Selection is explicit (EVERLIVING_PROVIDER or --provider), never magic —
silently switching models would quietly change what a playtest is measuring.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Protocol

from everliving import db

PROVIDERS = ("anthropic", "grok")
DEFAULT_PROVIDER = "anthropic"

# Cheap defaults so casual dev/playtest sessions don't rack up cost. Override either
# with EVERLIVING_MODEL. Model IDs change — check the provider's console if one 404s.
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_GROK_MODEL = "grok-4"

GROK_BASE_URL = "https://api.x.ai/v1"

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
        if isinstance(error, str) and error:  # xAI sometimes returns a bare string
            return error
        if body.get("message"):
            return str(body["message"])
    return str(exc)


def translate_sdk_error(exc: Exception, sdk, provider: str) -> Exception:
    """Map a provider SDK's exception onto ours.

    The anthropic and openai SDKs expose the same error hierarchy and the same
    subclassing trap: AuthenticationError is a subclass of APIStatusError, so it has
    to be tested first or a bad key reads as an outage.
    """
    if isinstance(exc, sdk.AuthenticationError):
        return LLMAuthError(str(exc))
    if isinstance(exc, sdk.APIStatusError):
        return LLMUnavailable(_server_message(exc))
    if isinstance(exc, sdk.APIConnectionError):
        return LLMUnavailable(f"連不上 {provider} API:{exc}")
    if isinstance(exc, TypeError):
        # No credential resolvable at all — raised from header validation before any
        # request goes out. Narrowed by message so a real TypeError in our own code
        # still surfaces as the bug it is.
        if "authentication" in str(exc).lower():
            return LLMAuthError(str(exc))
    return exc


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
        except Exception as exc:
            raise translate_sdk_error(exc, self._anthropic, "Anthropic") from exc
        self.last_usage = {
            "model": self._model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        if response.stop_reason == "refusal":
            raise LLMRefusal("模型拒絕回應這個請求。")
        return extract_text(response.content)


class GrokLLMClient:
    """xAI's Grok, via its OpenAI-compatible endpoint. Requires XAI_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import openai  # lazy import: only needed when this provider is selected

        self._openai = openai
        api_key = os.environ.get("XAI_API_KEY")
        if not api_key:
            # The OpenAI SDK would otherwise raise at construction with a message
            # naming OPENAI_API_KEY, which is the wrong variable to go looking for.
            raise LLMAuthError("找不到 XAI_API_KEY。")
        self._client = openai.OpenAI(api_key=api_key, base_url=GROK_BASE_URL)
        self._model = model or os.environ.get("EVERLIVING_MODEL", DEFAULT_GROK_MODEL)
        self.last_usage: dict | None = None

    def complete(self, system_prompt: str, user_message: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as exc:
            raise translate_sdk_error(exc, self._openai, "xAI") from exc

        usage = response.usage
        self.last_usage = {
            "model": self._model,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
        }
        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise LLMRefusal("模型拒絕回應這個請求。")
        return (choice.message.content or "").strip()


def make_client(provider: str | None = None, model: str | None = None) -> LLMClient:
    """Build the selected provider's client. Selection is explicit, never inferred."""
    provider = (provider or os.environ.get("EVERLIVING_PROVIDER") or DEFAULT_PROVIDER).lower()
    if provider == "anthropic":
        return AnthropicLLMClient(model=model)
    if provider == "grok":
        return GrokLLMClient(model=model)
    raise ValueError(f"unknown provider {provider!r}; expected one of {PROVIDERS}")
