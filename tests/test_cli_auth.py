"""Missing credentials must fail with guidance, not a traceback.

This path only fires on the first API call — the SDK resolves credentials lazily, so
a missing key looks fine right up until the model is actually needed.
"""

import pytest
from conftest import FakeLLMClient

from everliving import cli
from everliving.llm import LLMAuthError, LLMUnavailable

NO_CREDS = (
    "Could not resolve authentication method. Expected one of api_key, "
    "auth_token, or credentials to be set."
)


class UnauthenticatedLLM(FakeLLMClient):
    def complete(self, system_prompt, user_message):
        raise LLMAuthError(NO_CREDS)


def _scripted_input(responses):
    it = iter(responses)

    def _input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return _input


def test_missing_credentials_in_conversation_exits_with_guidance(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", UnauthenticatedLLM)
    monkeypatch.setattr("builtins.input", _scripted_input(["你好", "exit"]))

    with pytest.raises(SystemExit) as excinfo:
        cli.main([])

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "找不到可用的 API 憑證" in out
    assert "ANTHROPIC_API_KEY" in out


class BrokeLLM(FakeLLMClient):
    def complete(self, system_prompt, user_message):
        raise LLMUnavailable(
            "Your credit balance is too low to access the Anthropic API."
        )


def test_low_credit_exits_with_the_server_message(tmp_path, monkeypatch, capsys):
    """Observed for real: this is what an un-topped-up account hits on turn one."""
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", BrokeLLM)
    monkeypatch.setattr("builtins.input", _scripted_input(["你好", "exit"]))

    with pytest.raises(SystemExit) as excinfo:
        cli.main([])

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "credit balance is too low" in out
    assert "Plans & Billing" in out


def test_missing_credentials_in_offline_narrative_exits_with_guidance(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", UnauthenticatedLLM)
    monkeypatch.setattr("builtins.input", _scripted_input(["exit"]))

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--offline-hours", "24"])

    assert excinfo.value.code == 1
    assert "找不到可用的 API 憑證" in capsys.readouterr().out
