"""Tests for the core bet: offline periods must produce consequences, not just prose."""

import json
from datetime import timedelta

from conftest import FakeLLMClient

from everliving import db, persona
from everliving.agent_loop import build_system_prompt, respond
from everliving.offline import parse_offline_response, simulate_offline_period


def _response(**overrides) -> str:
    payload = {
        "narrative": "我把幫浦拆了,零件不夠。",
        "events": ["拆了港口的舊幫浦"],
        "state_changes": {"持有物": "半組幫浦零件"},
        "open_thread": "我需要你幫忙弄到一個壓力閥。",
        "resolved_thread_ids": [],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


# --- parsing ---------------------------------------------------------------


def test_parses_structured_response():
    result = parse_offline_response(_response())
    assert result.narrative == "我把幫浦拆了,零件不夠。"
    assert result.events == ["拆了港口的舊幫浦"]
    assert result.state_changes == {"持有物": "半組幫浦零件"}
    assert result.open_thread == "我需要你幫忙弄到一個壓力閥。"


def test_parses_json_wrapped_in_code_fence():
    raw = "```json\n" + _response() + "\n```"
    assert parse_offline_response(raw).open_thread == "我需要你幫忙弄到一個壓力閥。"


def test_malformed_response_degrades_to_plain_narrative():
    """The narrative is the one thing the player reads — it must never be lost."""
    result = parse_offline_response("我這幾天都在修東西,沒什麼特別的。")
    assert result.narrative == "我這幾天都在修東西,沒什麼特別的。"
    assert result.events == []
    assert result.open_thread is None


def test_null_open_thread_is_none():
    assert parse_offline_response(_response(open_thread=None)).open_thread is None


def test_non_dict_state_changes_ignored():
    assert parse_offline_response(_response(state_changes=["nope"])).state_changes == {}


# --- persistence -----------------------------------------------------------


def test_simulation_persists_state_events_and_thread(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply=_response())

    result = simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    assert db.get_state(conn, agent_id) == {"持有物": "半組幫浦零件"}

    threads = db.get_open_threads(conn, agent_id)
    assert len(threads) == 1
    assert threads[0]["description"] == result.open_thread

    kinds = [event["kind"] for event in db.get_recent_memory(conn, agent_id)]
    assert "offline_narrative" in kinds
    assert "offline_event" in kinds


def test_existing_state_and_threads_are_fed_back_into_the_prompt(conn):
    """Continuity is the point: the next offline period must know what already happened."""
    agent_id = persona.seed_default_agent(conn)
    db.set_state(conn, agent_id, "持有物", "半組幫浦零件")
    db.add_open_thread(conn, agent_id, "我需要你幫忙弄到一個壓力閥。")
    llm = FakeLLMClient(reply=_response())

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    _, user_message = llm.calls[0]
    assert "半組幫浦零件" in user_message
    assert "壓力閥" in user_message


def test_resolved_thread_is_closed(conn):
    agent_id = persona.seed_default_agent(conn)
    thread_id = db.add_open_thread(conn, agent_id, "我需要你幫忙弄到一個壓力閥。")
    llm = FakeLLMClient(reply=_response(resolved_thread_ids=[thread_id], open_thread=None))

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    assert db.get_open_threads(conn, agent_id) == []


def test_hallucinated_thread_id_is_ignored(conn):
    agent_id = persona.seed_default_agent(conn)
    real_id = db.add_open_thread(conn, agent_id, "真的懸念")
    llm = FakeLLMClient(reply=_response(resolved_thread_ids=[9999], open_thread=None))

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    remaining = db.get_open_threads(conn, agent_id)
    assert [thread["id"] for thread in remaining] == [real_id]


# --- the hook actually reaching the player ---------------------------------


def test_conversation_prompt_includes_open_thread(conn):
    agent_id = persona.seed_default_agent(conn)
    db.add_open_thread(conn, agent_id, "我需要你幫忙弄到一個壓力閥。")
    llm = FakeLLMClient(reply="嗯。")

    respond(conn, agent_id, llm, "最近怎樣?")

    system_prompt, user_message = llm.calls[0]
    assert "壓力閥" in user_message
    assert "還沒解決" in system_prompt


def test_conversation_prompt_omits_thread_instruction_when_none(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply="嗯。")

    respond(conn, agent_id, llm, "最近怎樣?")

    system_prompt, _ = llm.calls[0]
    assert "還沒解決" not in system_prompt


def test_build_system_prompt_thread_instruction_is_opt_in():
    agent = {"name": "A", "background": "b", "personality": "p"}
    assert "還沒解決" not in build_system_prompt(agent)
    assert "還沒解決" in build_system_prompt(agent, has_open_threads=True)
