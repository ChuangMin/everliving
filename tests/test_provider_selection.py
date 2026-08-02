"""Provider selection is explicit — silently switching models would change what a
playtest is measuring without telling anyone."""

import sys
import types

import pytest

from everliving import llm
from everliving.llm import (
    DEFAULT_GROK_MODEL,
    DEFAULT_MODEL,
    GROK_BASE_URL,
    LLMAuthError,
    LLMRefusal,
    LLMUnavailable,
    make_client,
    translate_sdk_error,
)


class _APIStatusError(Exception):
    def __init__(self, message, body=None):
        super().__init__(message)
        self.body = body


class _AuthenticationError(_APIStatusError):
    pass


class _APIConnectionError(Exception):
    pass


def _fake_openai(monkeypatch, reply="好。", finish_reason="stop", raises=None):
    """Stub the slice of the OpenAI SDK GrokLLMClient touches."""
    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            if raises is not None:
                raise raises
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        finish_reason=finish_reason,
                        message=types.SimpleNamespace(content=reply),
                    )
                ],
                usage=types.SimpleNamespace(prompt_tokens=120, completion_tokens=45),
            )

    class _Client:
        def __init__(self, api_key=None, base_url=None):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            self.chat = types.SimpleNamespace(completions=_Completions())

    module = types.ModuleType("openai")
    module.OpenAI = _Client
    module.AuthenticationError = _AuthenticationError
    module.APIStatusError = _APIStatusError
    module.APIConnectionError = _APIConnectionError
    monkeypatch.setitem(sys.modules, "openai", module)
    return captured


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("EVERLIVING_PROVIDER", raising=False)
    monkeypatch.delenv("EVERLIVING_MODEL", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")


# --- selection -------------------------------------------------------------


def test_defaults_to_anthropic(monkeypatch):
    monkeypatch.setattr(llm, "AnthropicLLMClient", lambda **kw: "anthropic-client")
    assert make_client() == "anthropic-client"


def test_env_var_selects_grok(monkeypatch):
    monkeypatch.setenv("EVERLIVING_PROVIDER", "grok")
    monkeypatch.setattr(llm, "GrokLLMClient", lambda **kw: "grok-client")
    assert make_client() == "grok-client"


def test_explicit_argument_beats_env_var(monkeypatch):
    monkeypatch.setenv("EVERLIVING_PROVIDER", "grok")
    monkeypatch.setattr(llm, "AnthropicLLMClient", lambda **kw: "anthropic-client")
    assert make_client("anthropic") == "anthropic-client"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        make_client("gemini")


# --- the Grok client -------------------------------------------------------


def test_grok_targets_the_xai_endpoint(monkeypatch):
    captured = _fake_openai(monkeypatch)
    llm.GrokLLMClient().complete("你是陌洲。", "你好")
    assert captured["base_url"] == GROK_BASE_URL
    assert captured["api_key"] == "xai-test-key"


def test_grok_sends_system_prompt_as_a_system_message(monkeypatch):
    """Anthropic takes `system=`; the OpenAI shape needs it as a message instead."""
    captured = _fake_openai(monkeypatch)
    llm.GrokLLMClient().complete("你是陌洲。", "你好")
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user"]
    assert captured["messages"][0]["content"] == "你是陌洲。"


def test_grok_returns_reply_and_records_usage(monkeypatch):
    _fake_openai(monkeypatch, reply="我在修水管。")
    client = llm.GrokLLMClient()
    assert client.complete("sys", "hi") == "我在修水管。"
    assert client.last_usage["input_tokens"] == 120
    assert client.last_usage["output_tokens"] == 45


def test_grok_default_model_differs_from_anthropic(monkeypatch):
    captured = _fake_openai(monkeypatch)
    llm.GrokLLMClient().complete("sys", "hi")
    assert captured["model"] == DEFAULT_GROK_MODEL
    assert DEFAULT_GROK_MODEL != DEFAULT_MODEL


def test_grok_honours_model_override(monkeypatch):
    monkeypatch.setenv("EVERLIVING_MODEL", "grok-3-mini")
    captured = _fake_openai(monkeypatch)
    llm.GrokLLMClient().complete("sys", "hi")
    assert captured["model"] == "grok-3-mini"


def test_grok_content_filter_is_a_refusal(monkeypatch):
    _fake_openai(monkeypatch, finish_reason="content_filter")
    with pytest.raises(LLMRefusal):
        llm.GrokLLMClient().complete("sys", "hi")


def test_grok_missing_key_names_the_right_variable(monkeypatch):
    """The OpenAI SDK would say OPENAI_API_KEY, which is the wrong thing to go find."""
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    _fake_openai(monkeypatch)
    with pytest.raises(LLMAuthError) as excinfo:
        llm.GrokLLMClient()
    assert "XAI_API_KEY" in str(excinfo.value)


def test_grok_low_credit_becomes_unavailable(monkeypatch):
    error = _APIStatusError("400", body={"error": {"message": "insufficient credits"}})
    _fake_openai(monkeypatch, raises=error)
    with pytest.raises(LLMUnavailable) as excinfo:
        llm.GrokLLMClient().complete("sys", "hi")
    assert "insufficient credits" in str(excinfo.value)


# --- shared error translation ---------------------------------------------


def test_translate_prefers_auth_over_its_status_parent():
    sdk = types.SimpleNamespace(
        AuthenticationError=_AuthenticationError,
        APIStatusError=_APIStatusError,
        APIConnectionError=_APIConnectionError,
    )
    mapped = translate_sdk_error(_AuthenticationError("bad key"), sdk, "xAI")
    assert isinstance(mapped, LLMAuthError)


def test_translate_passes_unknown_errors_through_untouched():
    sdk = types.SimpleNamespace(
        AuthenticationError=_AuthenticationError,
        APIStatusError=_APIStatusError,
        APIConnectionError=_APIConnectionError,
    )
    original = ValueError("something else entirely")
    assert translate_sdk_error(original, sdk, "xAI") is original


def test_server_message_handles_a_bare_string_error_body():
    """xAI doesn't always wrap the message in an object the way Anthropic does."""
    error = _APIStatusError("429", body={"error": "rate limit exceeded"})
    sdk = types.SimpleNamespace(
        AuthenticationError=_AuthenticationError,
        APIStatusError=_APIStatusError,
        APIConnectionError=_APIConnectionError,
    )
    mapped = translate_sdk_error(error, sdk, "xAI")
    assert "rate limit exceeded" in str(mapped)
