"""End to end: can the system tell that someone came back the next day?

Every piece of this exists and is tested on its own — `visits` records arrivals,
`retention.summarise` counts consecutive days, `web.Session.open` is what a player
actually touches. None of that proves they are connected, and 第 11 輪 was rejected for
exactly this: the data was stored correctly and nobody had asked who reads it.

So this walks the real path. Two visits a day apart through `web.Session`, then the
report, and the number it prints has to be 1.

It matters more than an ordinary integration test because H-1 is 里程碑 0's only success
criterion, and it went three months unanswerable while every unit involved worked. A
chain that is right at every link and broken at one joint looks identical from inside
any single test.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import FakeLLMClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from everliving import db, web  # noqa: E402
from retention import render, summarise  # noqa: E402

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "h1.db")


def _visit(db_path, monkeypatch, *, offline_hours=None):
    """One session, the way the page drives it: open, say something, leave."""
    fake = FakeLLMClient(reply="我把閥門纏好了。")
    monkeypatch.setattr(web, "make_client", lambda *a, **k: fake)
    session = web.Session(db_path, "fake", offline_hours)
    session.open()
    session.say("在嗎?")
    session.leave()
    return session


def test_two_evenings_a_day_apart_are_readable_as_coming_back(db_path, monkeypatch):
    """The whole point. If this number is wrong, H-1 cannot be graded."""
    _visit(db_path, monkeypatch)

    conn = db.get_connection(db_path)
    agent_id = conn.execute("SELECT id FROM agents").fetchone()["id"]
    # Age the first visit by exactly one day rather than sleeping through one. Relative
    # to now, not a fixed date: the second visit is stamped by the real clock, so a
    # hard-coded 「上禮拜一」 would make the gap grow by one every day this test is run —
    # green today, quietly wrong forever after.
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    conn.execute("UPDATE visits SET visited_at = ?", (yesterday.isoformat(),))
    conn.execute("UPDATE player_state SET last_seen_at = ?", (yesterday.isoformat(),))
    conn.commit()
    conn.close()

    _visit(db_path, monkeypatch, offline_hours=24)

    conn = db.get_connection(db_path)
    try:
        summary = summarise(conn, agent_id)
    finally:
        conn.close()

    assert summary["visits"] == 2
    assert summary["came_back_next_day"] == 1
    assert "H-1 還沒過" not in render(summary)


def test_opening_the_page_is_what_records_the_visit(db_path, monkeypatch):
    """Recorded on arrival, so a closed tab still counts.

    `leave` is a button. Hanging the record on it would mean the players who wander off
    — the ones a retention number most needs to see — are the ones it silently drops.
    """
    fake = FakeLLMClient(reply="我在。")
    monkeypatch.setattr(web, "make_client", lambda *a, **k: fake)
    session = web.Session(db_path, "fake", None)
    session.open()  # and never leaves

    conn = db.get_connection(db_path)
    try:
        agent_id = conn.execute("SELECT id FROM agents").fetchone()["id"]
        assert len(db.get_visits(conn, agent_id)) == 1
    finally:
        conn.close()


def test_refreshing_the_page_is_not_a_second_visit(db_path, monkeypatch):
    """`open()` is also what a refresh calls.

    Counting those would inflate the only number 里程碑 0 is graded on, and it would
    inflate it most for the player who is confused rather than engaged.
    """
    fake = FakeLLMClient(reply="我在。")
    monkeypatch.setattr(web, "make_client", lambda *a, **k: fake)
    session = web.Session(db_path, "fake", None)
    session.open()
    session.open()
    session.open()

    conn = db.get_connection(db_path)
    try:
        agent_id = conn.execute("SELECT id FROM agents").fetchone()["id"]
        assert len(db.get_visits(conn, agent_id)) == 1
    finally:
        conn.close()
