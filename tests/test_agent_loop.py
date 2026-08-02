import pytest

from everliving import db, persona
from everliving.agent_loop import build_system_prompt, respond


def test_build_system_prompt_includes_name_and_traits():
    agent = {"name": "陌洲", "background": "港城技師", "personality": "務實寡言"}
    prompt = build_system_prompt(agent)
    assert "陌洲" in prompt
    assert "港城技師" in prompt
    assert "務實寡言" in prompt


def test_respond_returns_llm_reply_and_records_memory(conn, fake_llm):
    fake_llm.reply = "我在修水管,晚點再說。"
    agent_id = persona.seed_default_agent(conn)

    reply = respond(conn, agent_id, fake_llm, "你在忙什麼?")

    assert reply == "我在修水管,晚點再說。"
    events = db.get_recent_memory(conn, agent_id)
    contents = [event["content"] for event in events]
    assert "玩家說:你在忙什麼?" in contents
    assert "我回答:我在修水管,晚點再說。" in contents


def test_respond_includes_recent_memory_in_prompt(conn, fake_llm):
    agent_id = persona.seed_default_agent(conn)
    db.add_memory_event(conn, agent_id, kind="raw", content="昨天修好了發電機")

    respond(conn, agent_id, fake_llm, "發電機還好嗎?")

    assert len(fake_llm.calls) == 1
    _, user_message = fake_llm.calls[0]
    assert "昨天修好了發電機" in user_message
    assert "發電機還好嗎?" in user_message


def test_respond_unknown_agent_raises(conn, fake_llm):
    with pytest.raises(ValueError):
        respond(conn, 999, fake_llm, "hi")
