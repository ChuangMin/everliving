"""The world clock is on screen, or it is not accumulating as far as the player knows.

第 16 輪 built a clock that only ever reached the prompt. `web.py` had zero hits for
`world` and `index.html` zero for `pressure`, so the one thing built specifically to
answer 人類's 「單調」 was invisible to the person who said it. 第 11 輪's lesson was
that stored data leaked *to* the player; this is the same question from the other end —
stored, and nobody reads it.

The load-bearing assertion here is not "a field exists". It is that the sentence on the
screen and the sentence in the prompt are the same object, so the two can never drift
into describing different worlds.
"""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import FakeLLMClient

from everliving import db, web, world


@pytest.fixture
def session(tmp_path, monkeypatch):
    fake = FakeLLMClient(reply="我在修水管。")
    monkeypatch.setattr(web, "make_client", lambda provider: fake)
    s = web.Session(str(tmp_path / "test.db"), None, None)
    s.fake = fake
    return s


def _age_the_world(session, days):
    """Move this world's epoch back, so the clock reads `days` old.

    The read comes first on purpose: a world row is created lazily on first read, so an
    UPDATE against a database nobody has asked the time of yet matches nothing and the
    world stays new. That cost one confusing red here, which is the helper's fault and
    not the product's.
    """
    conn = db.get_connection(session.db_path)
    world.pressure(conn)
    started = (datetime.now(timezone.utc) - timedelta(days=days, hours=1)).isoformat()
    conn.execute("UPDATE world SET started_at = ? WHERE id = 1", (started,))
    conn.commit()
    conn.close()


def test_the_snapshot_carries_the_world_the_player_is_standing_in(session):
    payload = session.open()

    assert "world" in payload, "沒有這個欄位,時鐘就只走給模型看"
    assert payload["world"]["description"]
    assert payload["world"]["stage"] == 0
    assert payload["world"]["stages"] == len(world.STAGES)
    assert payload["world"]["day"] == 0


def test_the_sentence_on_screen_is_the_one_the_prompt_was_given(session):
    """Two renderings of the same world would eventually disagree about it.

    The stage text is already written as things he handles rather than as a reading,
    which is exactly why it can be shown as-is — see `world.describe_for_prompt`.
    """
    _age_the_world(session, 20)
    payload = session.open()

    conn = db.get_connection(session.db_path)
    try:
        current = world.pressure(conn)
    finally:
        conn.close()

    assert payload["world"]["description"] == current.description
    assert current.description in world.describe_for_prompt(current)


def test_an_older_world_says_something_different_on_screen(session):
    """The whole point is that it changes. A field that never moves is decoration."""
    young = session.open()["world"]

    _age_the_world(session, 200)
    old = session.open()["world"]

    assert old["description"] != young["description"]
    assert old["stage"] > young["stage"]
    assert old["day"] > young["day"]


def test_the_stage_dots_have_a_ceiling_that_is_not_invented(session):
    """`stages` is what lets the page draw ●●○○○ without making up a scale.

    Days have no ceiling — `world.pollution` counts them forever — so a progress bar
    would have to invent an end for the world that nothing in the design decided.
    Stages do have a real count, and this pins the page to that count rather than to a
    number someone typed into the markup.
    """
    _age_the_world(session, 10_000)
    payload = session.open()

    assert payload["world"]["stages"] == len(world.STAGES)
    assert payload["world"]["stage"] == len(world.STAGES) - 1, "最後一階之後不准再長出格子"
    assert payload["world"]["stage"] < payload["world"]["stages"]


def test_the_world_shows_up_after_talking_too_not_only_on_arrival(session):
    """`snapshot` feeds every response, so a reply must not blank the world out.

    Cheap to get wrong: were this built onto `open()` alone, the panel would appear on
    arrival and vanish the moment the player said anything.
    """
    session.open()
    payload = session.say("你還好嗎?")

    assert payload["world"]["description"]
    assert payload["world"]["stages"] == len(world.STAGES)
