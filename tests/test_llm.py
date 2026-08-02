import sys
import types

import pytest

from everliving.llm import DEFAULT_MODEL


@pytest.fixture
def fake_anthropic_module(monkeypatch):
    """Stub out the `anthropic` package so AnthropicLLMClient can be constructed without it installed."""
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = lambda: object()
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    yield


def test_default_model_used_when_not_specified(fake_anthropic_module):
    from everliving.llm import AnthropicLLMClient

    client = AnthropicLLMClient()
    assert client._model == DEFAULT_MODEL


def test_env_var_overrides_default_model(fake_anthropic_module, monkeypatch):
    monkeypatch.setenv("EVERLIVING_MODEL", "claude-sonnet-5")
    from everliving.llm import AnthropicLLMClient

    client = AnthropicLLMClient()
    assert client._model == "claude-sonnet-5"


def test_explicit_model_argument_wins(fake_anthropic_module, monkeypatch):
    monkeypatch.setenv("EVERLIVING_MODEL", "claude-sonnet-5")
    from everliving.llm import AnthropicLLMClient

    client = AnthropicLLMClient(model="claude-opus-5")
    assert client._model == "claude-opus-5"
