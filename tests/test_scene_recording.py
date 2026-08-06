"""Keep the scene a beat was drawn in, so the picture can be checked against the words.

`場景`/`動作` reached the browser and then stopped existing. A rehearsal once produced
「配電所/淹水」 over dialogue still set in the workshop, and the report ends 「只出現一次,
先記著不動」 — because there was nothing to go back to. Round 7's audit found why: the
narrative is stored, the scene it chose is not; `llm_calls` keeps only token counts, and
`--debug` records the prompt and the player's message but never the model's reply.

So the question was never "is the picture right", it was "could anyone tell". Three
things become answerable once the pair is kept: how often it happens, whether it still
happens, and — the one that matters — whether a fix worked.

This records. It does not judge: comparing scene against narrative is a separate job,
and doing it here would mean shipping a检查 for something nobody has yet observed.
"""

import json
from datetime import timedelta

from everliving import db, persona
from everliving.agent_loop import respond
from everliving.offline import simulate_offline_period


def offline_json(scene="配電所", action="淹水", narrative="我在配電所待了一整夜。"):
    return json.dumps(
        {
            "narrative": narrative,
            "events": [],
            "state_changes": {},
            "scene": scene,
            "action": action,
        },
        ensure_ascii=False,
    )


def assets_by_kind(conn, event_id):
    return {asset["kind"]: asset["ref"] for asset in db.get_assets(conn, event_id)}


def test_offline_narrative_keeps_the_scene_it_chose(conn, fake_llm):
    fake_llm.reply = offline_json()
    agent_id = persona.seed_default_agent(conn)

    result = simulate_offline_period(conn, agent_id, fake_llm, timedelta(hours=24))

    assert assets_by_kind(conn, result.narrative_event_id) == {
        "scene": "配電所",
        "action": "淹水",
    }


def test_the_pair_can_be_read_back_together(conn, fake_llm):
    # The whole point. Reconstructing "which beat was that" by matching text afterwards
    # is the fragile approach `offline.py` already rules out, so the row id is the join.
    fake_llm.reply = offline_json(narrative="水位頂過防禦線,我整夜都在掏沉沙格。")
    agent_id = persona.seed_default_agent(conn)

    result = simulate_offline_period(conn, agent_id, fake_llm, timedelta(hours=24))
    stored = [
        event
        for event in db.get_recent_memory(conn, agent_id)
        if event["id"] == result.narrative_event_id
    ]

    assert stored[0]["content"] == "水位頂過防禦線,我整夜都在掏沉沙格。"
    assert assets_by_kind(conn, result.narrative_event_id)["scene"] == "配電所"


def test_no_action_writes_no_row(conn, fake_llm):
    # "Nothing in particular is happening" is a real state of the picture, not missing
    # data. A row saying so would be indistinguishable from a row written by mistake.
    fake_llm.reply = offline_json(action=None)
    agent_id = persona.seed_default_agent(conn)

    result = simulate_offline_period(conn, agent_id, fake_llm, timedelta(hours=24))

    assert assets_by_kind(conn, result.narrative_event_id) == {"scene": "配電所"}


def test_conversation_turn_keeps_its_scene(conn, fake_llm):
    fake_llm.reply = "我把閥門纏好了。\n場景:工作間\n動作:焊接"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "你在忙什麼?")

    assert assets_by_kind(conn, turn.event_id) == {"scene": "工作間", "action": "焊接"}


def test_conversation_without_a_tag_records_nothing(conn, fake_llm):
    # A reply with no stage direction means "leave the picture where it is". Inventing
    # a row for it would put a scene in the record that the model never chose.
    fake_llm.reply = "我把閥門纏好了。"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "你在忙什麼?")

    assert db.get_assets(conn, turn.event_id) == []


def test_old_rows_are_left_alone(conn, fake_llm):
    # Backfilling would mean inventing a scene for a beat whose choice was never kept.
    # An empty answer is the true one; a plausible one would be a lie in the record.
    agent_id = persona.seed_default_agent(conn)
    old = db.add_memory_event(conn, agent_id, kind="offline_narrative", content="舊的敘事")

    fake_llm.reply = offline_json()
    simulate_offline_period(conn, agent_id, fake_llm, timedelta(hours=24))

    assert db.get_assets(conn, old) == []
