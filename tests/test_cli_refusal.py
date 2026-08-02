"""A refusal must degrade gracefully mid-playtest, not end the session with a traceback."""

from conftest import FakeLLMClient

from everliving import cli
from everliving.llm import LLMRefusal


class RefusingLLM(FakeLLMClient):
    def complete(self, system_prompt, user_message):
        raise LLMRefusal("模型拒絕回應這個請求。")


def _scripted_input(responses):
    it = iter(responses)

    def _input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return _input


def test_refusal_during_conversation_keeps_session_alive(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", RefusingLLM)
    monkeypatch.setattr("builtins.input", _scripted_input(["某個被拒絕的問題", "exit"]))

    cli.main([])  # must not raise

    out = capsys.readouterr().out
    assert "換個說法再試一次" in out


def test_refusal_during_offline_narrative_still_enters_conversation(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", RefusingLLM)
    monkeypatch.setattr("builtins.input", _scripted_input(["exit"]))

    cli.main(["--offline-hours", "24"])  # must not raise

    out = capsys.readouterr().out
    assert "沒能生成離線敘事" in out
    assert "輸入 exit 離開" in out  # reached the conversation loop anyway
