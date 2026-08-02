from datetime import timedelta

from conftest import FakeLLMClient

from everliving import db, persona
from everliving.agent_loop import respond
from everliving.offline import generate_offline_narrative

USAGE = {"model": "claude-haiku-4-5-20251001", "input_tokens": 120, "output_tokens": 45}


def test_conversation_logs_token_usage(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply="嗯。", usage=USAGE)

    respond(conn, agent_id, llm, "在嗎?")

    rows = conn.execute("SELECT * FROM llm_calls").fetchall()
    assert len(rows) == 1
    assert rows[0]["purpose"] == "conversation"
    assert rows[0]["input_tokens"] == 120
    assert rows[0]["output_tokens"] == 45
    assert rows[0]["model"] == USAGE["model"]


def test_offline_narrative_logs_token_usage(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply="我修好了發電機。", usage=USAGE)

    generate_offline_narrative(conn, agent_id, llm, timedelta(hours=3))

    rows = conn.execute("SELECT * FROM llm_calls").fetchall()
    assert len(rows) == 1
    assert rows[0]["purpose"] == "offline_narrative"


def test_client_without_usage_reporting_logs_nothing(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply="嗯。")  # last_usage stays None

    respond(conn, agent_id, llm, "在嗎?")

    assert conn.execute("SELECT COUNT(*) AS n FROM llm_calls").fetchone()["n"] == 0


def test_token_usage_by_day_aggregates(conn):
    agent_id = persona.seed_default_agent(conn)
    for _ in range(3):
        db.record_llm_call(conn, agent_id, "conversation", "model-a", 100, 20)

    summary = db.token_usage_by_day(conn)

    assert len(summary) == 1
    assert summary[0]["calls"] == 3
    assert summary[0]["input_tokens"] == 300
    assert summary[0]["output_tokens"] == 60
