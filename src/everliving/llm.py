"""LLM client abstraction. Real calls go through a provider client; tests inject a fake.

Two providers are supported so the project isn't hostage to one account's credit
balance. Selection is explicit (EVERLIVING_PROVIDER or --provider), never magic —
silently switching models would quietly change what a playtest is measuring.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Protocol

from everliving import db, logs

_log = logs.get_logger("llm")

PROVIDERS = ("auto", "anthropic", "grok", "groq", "ollama")

#: ⚠️ **還沒改成 `auto`,而且那是刻意的。**
#:
#: 人類 2026-08-07 答的是「AUTO ROUTER」,`--provider auto` 已經可以用(見 `router.py`)。
#: 但把**預設**換成 `auto` 是另一件事,而且試過一次就踩到地雷:
#: `tests/test_provider_selection.py:76` 會設一把假的 `XAI_API_KEY`,於是 router 真的把
#: Grok client 建了起來、**發出真實網路呼叫**,整套測試當場卡死。
#:
#: 那個地雷本身比這個預設值重要:**這套測試在 provider 建得起來的時候,是會打真的 API 的。**
#: 換預設值要連同那件事一起處理,不能順手改一行。已排進 `LOOP.md`。
DEFAULT_PROVIDER = "anthropic"

# Cheap default so casual dev/playtest sessions don't rack up cost. Override with
# EVERLIVING_MODEL. Model IDs change — check the provider's console if one 404s.
DEFAULT_MODEL = "claude-haiku-4-5"

# grok (xAI) and groq (inference host for open models) are different companies whose
# names differ by one letter. Both speak the OpenAI wire format, so they share an
# implementation and differ only in the three values below.
OPENAI_COMPATIBLE = {
    "grok": {
        "base_url": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "default_model": "grok-4",
        "label": "xAI (Grok)",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "qwen/qwen3.6-27b",
        "label": "Groq",
    },
    # Ollama on this machine. `key_env: None` marks it keyless — nothing authenticates
    # because nothing leaves the box. That also makes it the only provider that can't
    # fail with a billing or expired-key error, which is why it's the playtest default
    # of last resort: a dead API key must not be able to block H-1 a second time.
    # Free per call, so it's also the only way to measure the loop without spending.
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "key_env": None,
        "default_model": "qwen3.6:latest",
        "label": "Ollama(本機)",
    },
}

GROK_BASE_URL = OPENAI_COMPATIBLE["grok"]["base_url"]
DEFAULT_GROK_MODEL = OPENAI_COMPATIBLE["grok"]["default_model"]
OLLAMA_BASE_URL = OPENAI_COMPATIBLE["ollama"]["base_url"]
DEFAULT_OLLAMA_MODEL = OPENAI_COMPATIBLE["ollama"]["default_model"]

# A ceiling, not a spend — you're only billed for what's actually generated, so this
# is set well above the 2-4 sentences a reply needs. The headroom matters for models
# that reason before answering (the Claude 5 family, Qwen): there the cap covers
# reasoning *and* output together. Observed: Qwen hit a 2048 cap exactly, which
# truncates the JSON the offline simulation depends on.
MAX_TOKENS = 6000


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


def strip_reasoning(text: str) -> str:
    """Remove inline <think> reasoning from an OpenAI-format reply.

    Reasoning models served over the OpenAI wire format put their deliberation in the
    content itself rather than in a separate block, so without this the player reads
    the model talking itself through the answer before reaching the answer.

    Splits on the *last* closing tag: some models emit a closing tag without an
    opening one, and nesting would otherwise strand part of the reasoning.
    """
    close = "</think>"
    if close in text:
        text = text.rsplit(close, 1)[1]
    elif text.lstrip().startswith("<think>"):
        # Opened but never closed — the model spent its whole budget reasoning.
        return ""
    return text.strip()


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


def _log_call_started(label: str, model: str, system_prompt: str, user_message: str):
    """Record that a call went out, and return the clock to measure it against.

    The prompts themselves are the player's side of the conversation, so they only
    reach the file at DEBUG. Everything needed to diagnose a stuck or expensive run —
    which provider, which model, how long, how many tokens — is INFO.
    """
    _log.info("%s → %s", label, model)
    _log.debug("%s system prompt: %s", label, system_prompt)
    _log.debug("%s user message: %s", label, user_message)
    return time.monotonic()


def _log_call_finished(label: str, model: str, started: float, usage: dict) -> None:
    _log.info(
        "%s ← %s in %.1fs (in=%s out=%s)",
        label,
        model,
        time.monotonic() - started,
        usage["input_tokens"],
        usage["output_tokens"],
    )


def _log_call_failed(label: str, model: str, started: float, exc: Exception) -> None:
    # The provider's own message, which is usually the actual instruction ("API key is
    # invalid", "insufficient credits"). No key is ever part of it.
    _log.error(
        "%s ✗ %s after %.1fs — %s: %s",
        label,
        model,
        time.monotonic() - started,
        type(exc).__name__,
        exc,
    )


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
        started = _log_call_started("Anthropic", self._model, system_prompt, user_message)
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:
            _log_call_failed("Anthropic", self._model, started, exc)
            raise translate_sdk_error(exc, self._anthropic, "Anthropic") from exc
        self.last_usage = {
            "model": self._model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        _log_call_finished("Anthropic", self._model, started, self.last_usage)
        if response.stop_reason == "refusal":
            raise LLMRefusal("模型拒絕回應這個請求。")
        return extract_text(response.content)


class OpenAICompatibleClient:
    """Any endpoint speaking the OpenAI wire format — currently xAI and Groq."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        import openai  # lazy import: only needed when this provider is selected

        config = OPENAI_COMPATIBLE[provider]
        self._openai = openai
        self._label = config["label"]

        key_env = config["key_env"]
        if key_env is None:
            # Keyless provider (local). The SDK still refuses to construct without a
            # non-empty string, so hand it a placeholder the server never reads.
            api_key = "local-no-key-needed"
        else:
            api_key = os.environ.get(key_env)
            if not api_key:
                # Checked here because the OpenAI SDK would complain about
                # OPENAI_API_KEY, sending you after a variable that has nothing to do
                # with this provider.
                raise LLMAuthError(_missing_key_message(provider, key_env))

        self._client = openai.OpenAI(api_key=api_key, base_url=config["base_url"])
        self._model = model or os.environ.get(
            "EVERLIVING_MODEL", config["default_model"]
        )
        self.last_usage: dict | None = None

    def complete(self, system_prompt: str, user_message: str) -> str:
        started = _log_call_started(self._label, self._model, system_prompt, user_message)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[
                    # Anthropic takes the persona via `system=`; here it's a message.
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as exc:
            _log_call_failed(self._label, self._model, started, exc)
            raise translate_sdk_error(exc, self._openai, self._label) from exc

        usage = response.usage
        self.last_usage = {
            "model": self._model,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
        }
        _log_call_finished(self._label, self._model, started, self.last_usage)
        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise LLMRefusal("模型拒絕回應這個請求。")
        return strip_reasoning(choice.message.content or "")


def _missing_key_message(provider: str, key_env: str) -> str:
    """grok/groq differ by one letter, so a missing key is often the wrong provider."""
    sibling = "groq" if provider == "grok" else "grok"
    sibling_env = OPENAI_COMPATIBLE[sibling]["key_env"]
    hint = ""
    if os.environ.get(sibling_env):
        hint = (
            f" 但找到了 {sibling_env}——你要的可能是 `--provider {sibling}`"
            f"({OPENAI_COMPATIBLE[sibling]['label']} 跟 "
            f"{OPENAI_COMPATIBLE[provider]['label']} 是不同的服務)。"
        )
    return f"找不到 {key_env}。{hint}"


class GrokLLMClient(OpenAICompatibleClient):
    """xAI's Grok. Requires XAI_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__("grok", model)


class GroqLLMClient(OpenAICompatibleClient):
    """Groq — fast inference for open-weight models. Requires GROQ_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__("groq", model)


class OllamaLLMClient(OpenAICompatibleClient):
    """A model served by Ollama on this machine. No API key, no per-call cost."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__("ollama", model)


def make_client(provider: str | None = None, model: str | None = None) -> LLMClient:
    """Build the selected provider's client.

    Naming one is still explicit and still wins. `auto` is the one that chooses, and it
    chooses per call rather than once at startup — see `router.py`.
    """
    provider = (
        provider or os.environ.get("EVERLIVING_PROVIDER") or DEFAULT_PROVIDER
    ).lower()
    if provider == "auto":
        # Imported here rather than at module scope: router imports this module back.
        from everliving.router import DEFAULT_ORDER, RoutingLLMClient

        return RoutingLLMClient(
            [
                (name, lambda n=name: make_client(n, model=model))
                for name in DEFAULT_ORDER
            ]
        )
    if provider == "anthropic":
        return AnthropicLLMClient(model=model)
    if provider == "grok":
        return GrokLLMClient(model=model)
    if provider == "groq":
        return GroqLLMClient(model=model)
    if provider == "ollama":
        return OllamaLLMClient(model=model)
    raise ValueError(f"unknown provider {provider!r}; expected one of {PROVIDERS}")
