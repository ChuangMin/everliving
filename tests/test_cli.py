from conftest import FakeLLMClient

from everliving import cli


def _scripted_input(responses):
    it = iter(responses)

    def _input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return _input


def test_main_conversation_turn_prints_reply(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    fake = FakeLLMClient(reply="我在修水管。")
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", lambda **kw: fake)
    monkeypatch.setattr("builtins.input", _scripted_input(["你在忙什麼?", "exit"]))

    cli.main([])

    out = capsys.readouterr().out
    assert "我在修水管。" in out
    assert len(fake.calls) == 1


def test_main_second_run_shows_offline_narrative(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    first_llm = FakeLLMClient(reply="我很好。")
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", lambda **kw: first_llm)
    monkeypatch.setattr("builtins.input", _scripted_input(["exit"]))
    cli.main([])
    first_out = capsys.readouterr().out
    assert "這段時間發生的事" not in first_out

    second_llm = FakeLLMClient(reply="我修好了發電機。")
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", lambda **kw: second_llm)
    monkeypatch.setattr("builtins.input", _scripted_input(["exit"]))
    cli.main([])
    second_out = capsys.readouterr().out

    assert "這段時間發生的事" in second_out
    assert "我修好了發電機。" in second_out
