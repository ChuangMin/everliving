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


def test_offline_hours_forces_narrative_on_first_run(tmp_path, monkeypatch, capsys):
    """Without the flag a first run has no narrative; with it, you can test the hook immediately."""
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    fake = FakeLLMClient(reply="我把港口的舊幫浦拆了。")
    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", lambda: fake)
    monkeypatch.setattr("builtins.input", _scripted_input(["exit"]))

    cli.main(["--offline-hours", "72"])

    out = capsys.readouterr().out
    assert "這段時間發生的事" in out
    assert "我把港口的舊幫浦拆了。" in out
    _, user_message = fake.calls[0]
    assert "3 天" in user_message


def test_cost_report_prints_usage_without_calling_llm(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = db.get_connection(db_path)
    db.init_schema(conn)
    db.record_llm_call(conn, None, "conversation", "model-a", 500, 100)
    conn.close()

    def _explode():
        raise AssertionError("cost report must not construct an LLM client")

    monkeypatch.setattr("everliving.llm.AnthropicLLMClient", _explode)

    cli.main(["--cost-report"])

    out = capsys.readouterr().out
    assert "model-a" in out
    assert "500" in out


def test_cost_report_with_no_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DB_PATH", str(tmp_path / "test.db"))
    cli.main(["--cost-report"])
    assert "還沒有任何 LLM 呼叫記錄" in capsys.readouterr().out
