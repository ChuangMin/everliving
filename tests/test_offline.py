from datetime import datetime, timedelta, timezone

import pytest

from everliving import db, persona
from everliving.offline import (
    MIN_OFFLINE_GAP,
    _format_duration,
    generate_offline_narrative,
    is_worth_simulating,
    time_since_last_seen,
)


def test_time_since_last_seen_none_when_never_seen(conn):
    agent_id = persona.seed_default_agent(conn)
    assert time_since_last_seen(conn, agent_id) is None


def test_time_since_last_seen_computes_delta(conn):
    agent_id = persona.seed_default_agent(conn)
    now = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    db.set_last_seen(conn, agent_id, "2026-01-01T12:00:00+00:00")

    elapsed = time_since_last_seen(conn, agent_id, now=now)

    assert elapsed == timedelta(days=1)


@pytest.mark.parametrize(
    "delta,expected",
    [
        (timedelta(seconds=30), "不到一分鐘"),
        (timedelta(minutes=5), "5 分鐘"),
        (timedelta(hours=2, minutes=30), "2 小時 30 分鐘"),
        (timedelta(days=1, hours=3), "1 天 3 小時"),
    ],
)
def test_format_duration(delta, expected):
    assert _format_duration(delta) == expected


def test_generate_offline_narrative_calls_llm_and_records_memory(conn, fake_llm):
    fake_llm.reply = "我修好了發電機,還跟鄰居借了工具。"
    agent_id = persona.seed_default_agent(conn)
    db.add_memory_event(conn, agent_id, kind="raw", content="發電機壞了")

    narrative = generate_offline_narrative(conn, agent_id, fake_llm, timedelta(hours=5))

    assert narrative == "我修好了發電機,還跟鄰居借了工具。"
    events = db.get_recent_memory(conn, agent_id)
    offline_events = [e for e in events if e["kind"] == "offline_narrative"]
    assert len(offline_events) == 1
    assert offline_events[0]["content"] == narrative


def test_generate_offline_narrative_prompt_includes_duration_and_memory(conn, fake_llm):
    agent_id = persona.seed_default_agent(conn)
    db.add_memory_event(conn, agent_id, kind="raw", content="發電機壞了")

    generate_offline_narrative(conn, agent_id, fake_llm, timedelta(hours=5))

    assert len(fake_llm.calls) == 1
    _, user_message = fake_llm.calls[0]
    assert "5 小時" in user_message
    assert "發電機壞了" in user_message


def test_generate_offline_narrative_unknown_agent_raises(conn, fake_llm):
    with pytest.raises(ValueError):
        generate_offline_narrative(conn, 999, fake_llm, timedelta(hours=1))


def test_is_worth_simulating_needs_a_real_gap():
    assert not is_worth_simulating(None)
    assert not is_worth_simulating(timedelta(seconds=30))
    assert not is_worth_simulating(MIN_OFFLINE_GAP - timedelta(seconds=1))
    assert is_worth_simulating(MIN_OFFLINE_GAP)
    assert is_worth_simulating(timedelta(hours=24))
