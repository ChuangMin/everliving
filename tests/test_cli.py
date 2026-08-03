from datetime import datetime, timedelta, timezone

from conftest import FakeLLMClient

from everliving import cli, db


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


def _run_once(monkeypatch, reply):
    llm = FakeLLMClient(reply=reply)
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", lambda **kw: llm)
    monkeypatch.setattr("builtins.input", _scripted_input(["exit"]))
    cli.main([])
    return llm


def _backdate_last_seen(db_path, hours):
    conn = db.get_connection(db_path)
    when = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn.execute("UPDATE player_state SET last_seen_at = ?", (when,))
    conn.commit()
    conn.close()


def test_main_second_run_shows_offline_narrative(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    _run_once(monkeypatch, "我很好。")
    assert "這段時間發生的事" not in capsys.readouterr().out

    # A real absence, not a relaunch — that's what earns a narrative.
    _backdate_last_seen(db_path, hours=24)

    _run_once(monkeypatch, "我修好了發電機。")
    second_out = capsys.readouterr().out

    assert "這段時間發生的事" in second_out
    assert "我修好了發電機。" in second_out


def test_immediate_relaunch_does_not_simulate_an_offline_period(tmp_path, monkeypatch, capsys):
    """Quitting and starting again is not an absence.

    Without a floor this billed an LLM call and invented a whole offline period —
    state changes, a new thread and all — for a gap of a few milliseconds.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    _run_once(monkeypatch, "我很好。")
    capsys.readouterr()

    second = _run_once(monkeypatch, "不該被呼叫。")
    out = capsys.readouterr().out

    assert "這段時間發生的事" not in out
    assert second.calls == []  # no call means no bill

    conn = db.get_connection(db_path)
    assert conn.execute("SELECT COUNT(*) FROM open_threads").fetchone()[0] == 0
    conn.close()
