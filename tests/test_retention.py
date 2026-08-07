"""The retention report has to be right about the one number it exists to show.

人類 2026-08-07 set the goal 「以目標變成最多人玩的遊戲」. Before you can chase that you have
to be able to read whether one person came back twice, and that reading has to be
trustworthy — a retention number that flatters is worse than none, because it removes
the pressure that would have fixed the thing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from everliving import db, persona  # noqa: E402
from retention import render, summarise  # noqa: E402


@pytest.fixture
def agent_id(conn):
    return persona.seed_default_agent(conn)


def _visit(conn, agent_id, day: str, hour: str = "20:00:00"):
    db.record_visit(conn, agent_id, at=f"2026-08-{day}T{hour}+00:00")


def test_coming_back_the_next_day_is_what_gets_counted(conn, agent_id):
    """H-1 itself: consecutive calendar days, not merely 'more than one visit'."""
    _visit(conn, agent_id, "01")
    _visit(conn, agent_id, "02")
    _visit(conn, agent_id, "03")

    assert summarise(conn, agent_id)["came_back_next_day"] == 2


def test_two_visits_in_one_evening_are_not_a_streak(conn, agent_id):
    """Enthusiasm is not retention.

    Counting visits instead of days would let one long night look like a habit — which
    is exactly how a number starts lying to the person relying on it.
    """
    _visit(conn, agent_id, "01", "20:00:00")
    _visit(conn, agent_id, "01", "23:30:00")

    summary = summarise(conn, agent_id)

    assert summary["visits"] == 2
    assert len(summary["days"]) == 1
    assert summary["came_back_next_day"] == 0


def test_a_gap_of_several_days_does_not_count_as_coming_back_next_day(conn, agent_id):
    _visit(conn, agent_id, "01")
    _visit(conn, agent_id, "09")

    summary = summarise(conn, agent_id)

    assert summary["came_back_next_day"] == 0
    assert summary["longest_gap"] == 8


def test_an_empty_record_says_unrecorded_rather_than_never(conn, agent_id):
    """`visits` is newer than the save it will be run against.

    Reporting 「他從來沒回來過」 for a period that was simply never recorded would be the
    same fabrication the scene work refused when it declined to backfill.
    """
    text = render(summarise(conn, agent_id))

    assert "沒有被記錄過" in text
    assert "不是「他沒來」" in text


def test_the_report_says_plainly_when_h1_has_not_passed(conn, agent_id):
    """No hedging on the one number 里程碑 0 is graded on."""
    _visit(conn, agent_id, "01")
    _visit(conn, agent_id, "09")

    assert "H-1 還沒過" in render(summarise(conn, agent_id))


def test_the_report_never_picks_the_goal_metric_for_the_human(conn, agent_id):
    """He was asked what 「最多人玩」 should be measured by and hasn't answered.

    The report lays the candidates out so he can point at one; choosing for him would be
    exactly the thing `AGENTS.md` forbids (替人類拍板).
    """
    _visit(conn, agent_id, "01")

    text = render(summarise(conn, agent_id))

    assert "agent 不替你選" in text
    assert "完全沒有在記" in text, "the one that measures 「最多人」 has no data at all"
