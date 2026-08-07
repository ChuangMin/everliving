"""Keep what the model actually said, in the form it said it.

第 7 輪 auditor found this and it has been open ever since: `_log_call_started` writes the
system prompt and the user message at DEBUG and **never writes the reply**. So the record
holds the player's half of every exchange and none of 陌洲's — and `memory_events` stores
the narrative only *after* `split_scene_tag` has taken the stage directions off it.

It stopped being theoretical on 2026-08-07. Three separate 6-minute runs came back blank,
and answering 「模型到底吐了什麼」 was impossible: `llm_calls` had 3423 output tokens and no
way to see one of them. The diagnosis had to be reconstructed from token counts.

This is `AGENTS.md` 第六題 applied to the one place that had already been caught and not
fixed: a reply is history, not state, and history has to be written down while it exists.
"""

from __future__ import annotations

import pytest

from everliving import db


@pytest.fixture
def agent_id(conn):
    return db.create_agent(conn, "陌洲", "修東西的", "沉默")


def test_a_reply_is_kept_in_the_form_the_model_sent_it(conn, agent_id):
    """Raw, before any stripping.

    `memory_events` keeps the narrative after `split_scene_tag` has removed the stage
    directions, which is the right thing for the story and the wrong thing for asking
    「他當初到底寫了什麼」.
    """
    raw = '好的。\n場景:工作間\n動作:焊接'
    call_id = db.record_llm_call(
        conn, agent_id=agent_id, purpose="conversation",
        model="qwen3.6:latest", input_tokens=10, output_tokens=20,
    )
    db.record_llm_reply(conn, call_id, raw)

    assert db.get_llm_reply(conn, call_id) == raw


def test_an_empty_reply_is_recorded_as_empty_rather_than_skipped(conn, agent_id):
    """The blank nights are the whole reason this exists.

    Skipping empties would drop exactly the calls worth investigating, and leave the
    same hole that made 2026-08-07 take three runs to diagnose: a row of token counts
    with nothing to look at.
    """
    call_id = db.record_llm_call(
        conn, agent_id=agent_id, purpose="offline_narrative",
        model="qwen3.6:latest", input_tokens=673, output_tokens=3423,
    )
    db.record_llm_reply(conn, call_id, "")

    assert db.get_llm_reply(conn, call_id) == ""


def test_a_call_with_no_reply_recorded_is_distinguishable_from_an_empty_one(conn, agent_id):
    """「還沒記」 and 「記了,是空的」 are different facts.

    Collapsing them would recreate the ambiguity the scene work refused when it declined
    to write a row for a `None` scene: an absent answer is true, an invented one is not.
    """
    call_id = db.record_llm_call(
        conn, agent_id=agent_id, purpose="conversation",
        model="qwen3.6:latest", input_tokens=10, output_tokens=0,
    )

    assert db.get_llm_reply(conn, call_id) is None


def test_a_real_conversation_turn_keeps_its_stage_directions(conn):
    """The wiring, not just the function.

    第 11 輪 was rejected for storing something correctly and never asking who reads it,
    so this walks the actual path: `respond` strips the stage directions out of the
    reply the player sees, and the recorded raw has to still carry them.
    """
    from conftest import FakeLLMClient

    from everliving import persona
    from everliving.agent_loop import respond

    agent_id = persona.seed_default_agent(conn)
    raw = "我把閥門纏好了。\n場景:工作間\n動作:焊接"
    # Usage supplied because the reply rides along on the usage row, so a client that
    # reports no usage records no reply either. Every real provider reports it; a fake
    # that doesn't would be testing a path none of them take.
    usage = {"model": "fake", "input_tokens": 10, "output_tokens": 20}
    turn = respond(conn, agent_id, FakeLLMClient(reply=raw, usage=usage), "在嗎?")

    assert "場景:" not in turn.reply, "the player must not see the stage directions"

    call_id = conn.execute("SELECT id FROM llm_calls ORDER BY id DESC LIMIT 1").fetchone()["id"]
    assert db.get_llm_reply(conn, call_id) == raw


def test_replies_do_not_overwrite_each_other(conn, agent_id):
    """One row per call, and calls are already append-only.

    The retry makes two calls for one night, and the whole finding of 2026-08-07 was
    that both produced *identical* output — which is only visible if both were kept.
    """
    first = db.record_llm_call(
        conn, agent_id=agent_id, purpose="offline_narrative",
        model="m", input_tokens=673, output_tokens=3423,
    )
    second = db.record_llm_call(
        conn, agent_id=agent_id, purpose="offline_narrative",
        model="m", input_tokens=673, output_tokens=3423,
    )
    db.record_llm_reply(conn, first, "第一次")
    db.record_llm_reply(conn, second, "第二次")

    assert db.get_llm_reply(conn, first) == "第一次"
    assert db.get_llm_reply(conn, second) == "第二次"
