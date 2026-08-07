"""Whether anyone came back — the one question 里程碑 0 is graded on.

H-1 asks 「一個人隔天想不想再打開」, and until now nothing could answer it. `player_state`
holds a single row that every visit overwrites (`db.set_last_seen`, ON CONFLICT DO
UPDATE), so the system knows **that you are here** and has never recorded **that you
came**. Two visits and twenty are the same row.

This is the third time this project has found the same shape:

1. `scene`/`action` lived in one HTTP response and were never stored — so 「場景跟台詞
   對不上」 could not even be observed, let alone fixed
2. `memory_events` keeps what the player said, never 陌洲's reply in its original form
3. and now: the state of being visited, never the history of visits

State is cheap and answers 「現在怎樣」. History is what answers 「有沒有變」 — and every
question worth asking here is the second kind.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from everliving import db, persona

START = datetime(2026, 8, 1, 20, 0, tzinfo=timezone.utc)


def _at(days: float, hours: float = 0) -> str:
    return (START + timedelta(days=days, hours=hours)).isoformat()


@pytest.fixture
def agent_id(conn):
    return persona.seed_default_agent(conn)


def test_every_visit_is_kept_not_just_the_latest(conn, agent_id):
    """The defect this exists to remove: `set_last_seen` overwrites, so visit two
    erased visit one and H-1 had nothing to count."""
    db.record_visit(conn, agent_id, at=_at(0))
    db.record_visit(conn, agent_id, at=_at(1))
    db.record_visit(conn, agent_id, at=_at(5))

    assert [row["visited_at"] for row in db.get_visits(conn, agent_id)] == [
        _at(0),
        _at(1),
        _at(5),
    ]


def test_visits_are_append_only_like_the_rest_of_the_record(conn, agent_id):
    """Two visits on one evening are two visits.

    Deduplicating here would be the same mistake in miniature: it decides in advance
    which question the data will be allowed to answer.
    """
    db.record_visit(conn, agent_id, at=_at(0))
    db.record_visit(conn, agent_id, at=_at(0, hours=2))

    assert len(db.get_visits(conn, agent_id)) == 2


def test_arriving_is_not_the_same_fact_as_leaving(conn, agent_id):
    """Two different facts, kept apart on purpose.

    The offline gap has to be measured from when he *stopped* — measuring it from the
    start of the last session would shorten every gap by however long he stayed. An
    earlier draft of `record_visit` moved `last_seen` too, which was convenience
    dressed up as consistency.
    """
    db.set_last_seen(conn, agent_id, _at(0))
    db.record_visit(conn, agent_id, at=_at(3))

    assert db.get_last_seen(conn, agent_id) == _at(0)


def test_a_visit_survives_the_player_closing_the_tab(conn, agent_id):
    """`leave` only fires if the player uses the button.

    Recording on arrival is what makes the count honest: 「他關掉分頁就不算來過」 would be
    a silent rule that quietly deflates the only number 里程碑 0 is graded on.
    """
    db.record_visit(conn, agent_id, at=_at(0))

    assert len(db.get_visits(conn, agent_id)) == 1
    assert db.get_last_seen(conn, agent_id) is None, "he never left, so nothing to record"
