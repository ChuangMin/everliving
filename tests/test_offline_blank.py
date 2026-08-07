"""What happens when the model hands back nothing usable.

Measured on 2026-08-07: four real Ollama calls, two of which produced no usable JSON —
one truncated mid-object, one completely empty (`playtests/2026-08-07-world-clock.txt`).
The empty one is the dangerous shape. `parse_offline_response` degrades a malformed
answer to plain prose so the narrative is never lost, but when the answer *is* empty
there is no prose to fall back to, and the blank went on to be written into
`memory_events` — which is append-only, so a blank beat is permanent.

That is 里程碑 0's own pass condition failing: 「打開來讀到那段敘事」 read nothing.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from everliving import db, persona
from everliving.llm import LLMRefusal
from everliving.offline import simulate_offline_period


class ScriptedLLM:
    """Hands back a prepared answer per call, so a retry is observable."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.calls = 0
        self.last_usage = None
        self._model = "scripted"

    def complete(self, system_prompt: str, user_message: str) -> str:
        self.calls += 1
        return self._replies.pop(0) if self._replies else ""


GOOD = json.dumps(
    {
        "narrative": "我把濾水器的喉管通開了。",
        "events": ["換掉一段鏽穿的管子"],
        "state_changes": {"雙手狀態": "起了新繭"},
        "open_thread": None,
        "resolved_thread_ids": [],
        "delegation_outcomes": [],
        "scene": "工作間",
        "action": None,
    },
    ensure_ascii=False,
)


@pytest.fixture
def agent_id(conn):
    return persona.seed_default_agent(conn)


def _simulate(conn, agent_id, llm):
    return simulate_offline_period(conn, agent_id, llm, elapsed=timedelta(hours=24))


def test_an_empty_answer_is_asked_again_rather_than_shown(conn, agent_id):
    """One retry, because the failure is a coin flip rather than a broken prompt.

    Both real failures came from the same model that had just answered correctly with
    the same prompt, so asking twice is the cheapest thing that works — and it only
    costs anything at all in the case that is currently costing the player everything.
    """
    llm = ScriptedLLM("", GOOD)

    result = _simulate(conn, agent_id, llm)

    assert llm.calls == 2
    assert result.narrative == "我把濾水器的喉管通開了。"


def test_a_good_answer_is_never_asked_twice(conn, agent_id):
    """The retry must not double the bill on the path that already works."""
    llm = ScriptedLLM(GOOD)

    _simulate(conn, agent_id, llm)

    assert llm.calls == 1


def test_two_blank_answers_reach_the_player_as_a_reason(conn, agent_id):
    """`web.py:312` already catches `LLMRefusal` and shows it.

    So the player gets a sentence explaining the night could not be written, instead
    of an empty panel that reads as the app being broken — which is exactly what the
    human reported last time as 「代打沒甚麼反應」.
    """
    llm = ScriptedLLM("", "   ")

    with pytest.raises(LLMRefusal):
        _simulate(conn, agent_id, llm)


def test_a_blank_night_is_never_written_into_permanent_history(conn, agent_id):
    """`memory_events` is append-only, so a blank beat can never be taken back.

    Worse than showing nothing: it would be re-read into every future prompt as a
    night on which he apparently said nothing at all.
    """
    llm = ScriptedLLM("", "")

    with pytest.raises(LLMRefusal):
        _simulate(conn, agent_id, llm)

    rows = conn.execute("SELECT content FROM memory_events WHERE agent_id = ?", (agent_id,))
    assert [row["content"] for row in rows] == []


def test_prose_that_is_not_json_still_counts_as_an_answer(conn, agent_id):
    """The existing graceful degradation must survive this change.

    A model that ignored the JSON instruction but wrote a real night is not a failure —
    losing that prose would trade one blank screen for another.
    """
    llm = ScriptedLLM("我整夜都在掏沉沙格,沒空回你。")

    result = _simulate(conn, agent_id, llm)

    assert llm.calls == 1
    assert "沉沙格" in result.narrative
