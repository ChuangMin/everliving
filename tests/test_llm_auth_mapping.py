"""AnthropicLLMClient must map both credential failure shapes onto LLMAuthError.

The SDK has two: a plain TypeError from header validation when no credential can be
resolved at all, and AuthenticationError for a 401 from a credential that exists but
is rejected. Only the first is reachable without a network call.
"""

import sys
import types

import pytest

from everliving.llm import LLMAuthError, LLMUnavailable

NO_CREDS_MESSAGE = (
    "Could not resolve authentication method. Expected one of api_key, "
    "auth_token, or credentials to be set."
)
LOW_CREDIT_MESSAGE = (
    "Your credit balance is too low to access the Anthropic API. "
    "Please go to Plans & Billing to upgrade or purchase credits."
)


class _APIStatusError(Exception):
    def __init__(self, message, body=None):
        super().__init__(message)
        self.body = body


class _AuthenticationError(_APIStatusError):
    """Mirrors the real SDK hierarchy — AuthenticationError subclasses APIStatusError."""


class _APIConnectionError(Exception):
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
    module.APIStatusError = _APIStatusError
    module.APIConnectionError = _APIConnectionError
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


def test_low_credit_becomes_unavailable_with_the_server_message(monkeypatch):
    """The most likely first-run failure — and the server text says exactly what to do."""
    error = _APIStatusError(
        "Error code: 400", body={"error": {"message": LOW_CREDIT_MESSAGE}}
    )
    client = _client(monkeypatch, error)
    with pytest.raises(LLMUnavailable) as excinfo:
        client.complete("sys", "hi")
    assert "credit balance is too low" in str(excinfo.value)


def test_status_error_without_a_body_falls_back_to_str(monkeypatch):
    client = _client(monkeypatch, _APIStatusError("Error code: 529 overloaded"))
    with pytest.raises(LLMUnavailable) as excinfo:
        client.complete("sys", "hi")
    assert "529" in str(excinfo.value)


def test_connection_error_becomes_unavailable(monkeypatch):
    client = _client(monkeypatch, _APIConnectionError("connection refused"))
    with pytest.raises(LLMUnavailable):
        client.complete("sys", "hi")


def test_auth_error_wins_over_its_status_error_parent(monkeypatch):
    """AuthenticationError subclasses APIStatusError; ordering decides which fires."""
    client = _client(monkeypatch, _AuthenticationError("invalid x-api-key"))
    with pytest.raises(LLMAuthError):
        client.complete("sys", "hi")


def test_unrelated_typeerror_still_propagates_as_a_bug(monkeypatch):
    """Narrowing by message matters — a real TypeError in our code must not be swallowed."""
    client = _client(monkeypatch, TypeError("unsupported operand type(s) for +"))
    with pytest.raises(TypeError) as excinfo:
        client.complete("sys", "hi")
    assert not isinstance(excinfo.value, LLMAuthError)
