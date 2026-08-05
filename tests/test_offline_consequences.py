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


def test_parses_action_from_the_closed_vocabulary():
    assert parse_offline_response(_response(action="停電")).action == "停電"


def test_unknown_action_degrades_to_nothing_in_particular():
    """No fallback here, unlike scene: inventing weather the narrative never mentioned
    is worse than showing the place calm."""
    assert parse_offline_response(_response(action="下雪")).action is None
    assert parse_offline_response(_response(action=None)).action is None
    assert parse_offline_response(_response()).action is None


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


def test_the_result_carries_the_id_of_the_beat_it_wrote(conn):
    """The narrative row's id is the anchor every story asset hangs on (a clip, a
    still, a page). The simulation was writing that row and throwing the id away,
    which left the display side with no way to ever point at a specific beat."""
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply=_response())

    result = simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    assert result.narrative_event_id is not None
    row = conn.execute(
        "SELECT kind, content FROM memory_events WHERE id = ?",
        (result.narrative_event_id,),
    ).fetchone()
    assert row["kind"] == "offline_narrative"
    assert row["content"] == result.narrative


def test_an_asset_can_be_hung_on_the_beat_the_simulation_just_wrote(conn):
    """End to end: the reservation is only real if a beat produced by a real run can
    actually carry a clip."""
    agent_id = persona.seed_default_agent(conn)
    result = simulate_offline_period(
        conn, agent_id, FakeLLMClient(reply=_response()), timedelta(days=1)
    )

    db.attach_asset(conn, result.narrative_event_id, kind="video", ref="clips/夜.webm")

    assert [a["ref"] for a in db.get_assets(conn, result.narrative_event_id)] == [
        "clips/夜.webm"
    ]


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


# --- threads have to be able to close (T0-17) ------------------------------
#
# The 2026-08-05 rehearsal ran four steps and closed nothing: the last offline
# period picked up the player's promise correctly, then filed it as a *second*
# thread restating the first. Two near-identical rows, `resolved` at 0 forever,
# and a conversation prompt that grows every night. Asserting the instruction is
# present is all a test can do — whether the model obeys is what a real run is
# for — but the instruction being conditional is testable and matters.


def test_offline_prompt_forbids_restating_an_open_thread(conn):
    agent_id = persona.seed_default_agent(conn)
    db.add_open_thread(conn, agent_id, "我需要你幫忙弄到一個壓力閥。")
    llm = FakeLLMClient(reply=_response(open_thread=None))

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    system_prompt, _ = llm.calls[0]
    assert "同一件事" in system_prompt
    # The "usually leave a thread behind" default is what produced the duplicate,
    # so it has to be the branch that's replaced, not one the model sees as well.
    assert "通常要留下一件" not in system_prompt


def test_offline_prompt_asks_for_a_thread_when_nothing_is_open(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply=_response())

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    system_prompt, _ = llm.calls[0]
    assert "通常要留下一件" in system_prompt
    assert "同一件事" not in system_prompt


# --- delegation: you ask, you leave, you find out --------------------------
#
# 設計文件 第十二節: the control model is delegation. You never move anyone — you ask,
# and it gets carried out or refused during the offline period. The two rules that
# stop it collapsing are that refusing needs a reason from his own state (or he reads
# as a broken system rather than a person) and that a refusal has to leave a hook
# behind (or saying no just ends the conversation).


def test_a_delegation_gets_an_outcome_and_stops_being_pending(conn):
    agent_id = persona.seed_default_agent(conn)
    ask_id = db.add_delegation(conn, agent_id, "去回收場東邊找一個還能用的壓力閥")
    llm = FakeLLMClient(reply=_response(
        open_thread=None,
        delegation_outcomes=[{"id": ask_id, "status": "done", "outcome": "找到了,閥體有裂"}],
    ))

    result = simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    assert db.get_pending_delegations(conn, agent_id) == []
    assert result.delegation_outcomes[0]["status"] == "done"


def test_a_refusal_leaves_a_thread_behind(conn):
    """Saying no has to open something, not close the conversation."""
    agent_id = persona.seed_default_agent(conn)
    ask_id = db.add_delegation(conn, agent_id, "去機器廠幫我問那批貨")
    llm = FakeLLMClient(reply=_response(
        open_thread=None,
        delegation_outcomes=[
            {"id": ask_id, "status": "refused", "outcome": "手還爛著,機器廠那條路我這幾天不走。"}
        ],
    ))

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    threads = [t["description"] for t in db.get_open_threads(conn, agent_id)]
    assert "手還爛著,機器廠那條路我這幾天不走。" in threads


def test_a_hallucinated_delegation_id_is_ignored(conn):
    """Same guard as thread ids: an invented number must never close an errand the
    player is still waiting on."""
    agent_id = persona.seed_default_agent(conn)
    db.add_delegation(conn, agent_id, "真的委託")
    llm = FakeLLMClient(reply=_response(
        open_thread=None,
        delegation_outcomes=[{"id": 9999, "status": "done", "outcome": "做完了"}],
    ))

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    assert len(db.get_pending_delegations(conn, agent_id)) == 1


def test_an_unrecognised_status_still_settles_the_errand(conn):
    """An answer we can't parse is still an answer that the night happened. Leaving it
    pending would keep it in every future prompt forever."""
    agent_id = persona.seed_default_agent(conn)
    ask_id = db.add_delegation(conn, agent_id, "去看看潮線那邊")
    llm = FakeLLMClient(reply=_response(
        open_thread=None,
        delegation_outcomes=[{"id": ask_id, "status": "維修中", "outcome": "去了,沒東西"}],
    ))

    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))

    assert db.get_pending_delegations(conn, agent_id) == []


def test_offline_prompt_only_carries_the_refusal_rules_when_something_is_pending(conn):
    agent_id = persona.seed_default_agent(conn)
    llm = FakeLLMClient(reply=_response())
    simulate_offline_period(conn, agent_id, llm, timedelta(days=1))
    assert "可以拒絕" not in llm.calls[0][0]

    db.add_delegation(conn, agent_id, "去回收場找濾芯")
    llm2 = FakeLLMClient(reply=_response(open_thread=None))
    simulate_offline_period(conn, agent_id, llm2, timedelta(days=1))
    system_prompt, user_message = llm2.calls[0]
    assert "可以拒絕" in system_prompt
    assert "去回收場找濾芯" in user_message


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
