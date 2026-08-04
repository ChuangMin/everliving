"""Assets (video, illustration, a written page) attach to a narrative beat.

The design doc's rule, made executable: they attach to the beat's **id**, never to its
text, and never to a compressed retelling of it. 陌洲 is allowed to remember a night
differently each time; the clip the player already watched of that night is not.
"""

import sqlite3

import pytest

from everliving import db


@pytest.fixture
def beat(conn):
    agent_id = db.create_agent(conn, "陌洲", "技師", "寡言")
    event_id = db.add_memory_event(
        conn, agent_id, kind="offline_narrative", content="夜裡漲潮,配電所跳了一次。"
    )
    return agent_id, event_id


def test_an_asset_attaches_to_a_beat_and_comes_back(conn, beat):
    _, event_id = beat
    db.attach_asset(conn, event_id, kind="video", ref="clips/配電所-夜.webm")

    assets = db.get_assets(conn, event_id)
    assert [(a["kind"], a["ref"]) for a in assets] == [("video", "clips/配電所-夜.webm")]


def test_one_beat_can_carry_more_than_one_kind(conn, beat):
    """A single night might eventually have an ambient clip, a still, and a page."""
    _, event_id = beat
    db.attach_asset(conn, event_id, kind="video", ref="clips/a.webm")
    db.attach_asset(conn, event_id, kind="image", ref="stills/a.png")
    db.attach_asset(conn, event_id, kind="story", ref="pages/a.md")

    kinds = sorted(a["kind"] for a in db.get_assets(conn, event_id))
    assert kinds == ["image", "story", "video"]


def test_an_asset_cannot_attach_to_a_beat_that_does_not_exist(conn, beat):
    """An asset pointing at nothing is how a clip ends up orphaned from its story."""
    with pytest.raises(sqlite3.IntegrityError):
        db.attach_asset(conn, 9999, kind="video", ref="clips/nowhere.webm")


def test_attaching_an_asset_never_edits_the_beat(conn, beat):
    """canon is append-only: if the row an asset hangs on could be rewritten, the
    player's evidence and the text they're reading would drift apart."""
    _, event_id = beat
    before = conn.execute(
        "SELECT content FROM memory_events WHERE id = ?", (event_id,)
    ).fetchone()["content"]

    db.attach_asset(conn, event_id, kind="video", ref="clips/a.webm")

    after = conn.execute(
        "SELECT content FROM memory_events WHERE id = ?", (event_id,)
    ).fetchone()["content"]
    assert after == before


def test_assets_of_other_beats_are_not_returned(conn, beat):
    agent_id, event_id = beat
    other = db.add_memory_event(conn, agent_id, kind="offline_narrative", content="別的一夜。")
    db.attach_asset(conn, event_id, kind="video", ref="clips/a.webm")
    db.attach_asset(conn, other, kind="video", ref="clips/b.webm")

    assert [a["ref"] for a in db.get_assets(conn, event_id)] == ["clips/a.webm"]


def test_a_beat_with_nothing_attached_is_empty_not_an_error(conn, beat):
    """The normal case for a long time: the reservation exists, the clips don't."""
    _, event_id = beat
    assert db.get_assets(conn, event_id) == []
