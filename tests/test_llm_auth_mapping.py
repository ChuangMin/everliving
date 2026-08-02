"""AnthropicLLMClient must map both credential failure shapes onto LLMAuthError.

The SDK has two: a plain TypeError from header validation when no credential can be
resolved at all, and AuthenticationError for a 401 from a credential that exists but
is rejected. Only the first is reachable without a network call.
"""

import sys
import types

import pytest

from everliving.llm import LLMAuthError

NO_CREDS_MESSAGE = (
    "Could not resolve authentication method. Expected one of api_key, "
    "auth_token, or credentials to be set."
)


class _AuthenticationError(Exception):
    pass


def _fake_anthropic(raises: Exception):
    """Stub the SDK surface AnthropicLLMClient touches."""

    class _Messages:
        def create(self, **kwargs):
            raise raises

    class _Client:
        def __init__(self):
            self.messages = _Messages()

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client
    module.AuthenticationError = _AuthenticationError
    return module


def _client(monkeypatch, raises):
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(raises))
    from everliving.llm import AnthropicLLMClient

    return AnthropicLLMClient()


def test_unresolvable_credentials_typeerror_becomes_auth_error(monkeypatch):
    client = _client(monkeypatch, TypeError(NO_CREDS_MESSAGE))
    with pytest.raises(LLMAuthError):
        client.complete("sys", "hi")


def test_rejected_credential_401_becomes_auth_error(monkeypatch):
    client = _client(monkeypatch, _AuthenticationError("invalid x-api-key"))
    with pytest.raises(LLMAuthError):
        client.complete("sys", "hi")


def test_unrelated_typeerror_still_propagates_as_a_bug(monkeypatch):
    """Narrowing by message matters — a real TypeError in our code must not be swallowed."""
    client = _client(monkeypatch, TypeError("unsupported operand type(s) for +"))
    with pytest.raises(TypeError) as excinfo:
        client.complete("sys", "hi")
    assert not isinstance(excinfo.value, LLMAuthError)
