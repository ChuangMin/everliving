"""The one thing in this world that moves without the player (設計文件 第十一節).

The human's answer to "系統還是太簡單了" was 「單調」, and the root of it was 「玩十次跟玩一次
一樣」: nothing accumulates, so the scene has no reason to change and he has no new material
to talk about. The design doc already had the piece for this — pollution as 「單向惡化的背景
壓力,一個不管玩家做什麼都在走的時鐘」 — so this invents no lore, it just makes it run.

Two properties are load-bearing and both are tested here rather than trusted:

- it moves while nobody is playing, which is what makes coming back different from staying
- it only ever moves one way, which is what makes it accumulation rather than weather
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from everliving import db, world
from everliving.offline import _build_prompts


def _at(days: float) -> datetime:
    """A moment `days` after the epoch the tests below start every world at."""
    return EPOCH + timedelta(days=days)


EPOCH = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def started(conn):
    """A world whose clock started at a known moment, so readings are checkable."""
    world.start_world(conn, at=EPOCH)
    return conn


# --- it moves on its own ------------------------------------------------------


def test_the_clock_moves_while_nobody_is_playing(started):
    """Nothing happens between these two readings — no turn, no visit, no call.

    This is the whole point of the thing. A number that only advances when the player
    does something is a score, and a score is exactly what 「玩十次跟玩一次一樣」 describes.
    """
    early = world.pollution(started, now=_at(1))
    late = world.pollution(started, now=_at(40))

    assert late > early


def test_the_clock_is_derived_from_the_calendar_rather_than_ticked(started):
    """Lazy simulation, the same bet the whole project rests on (設計文件).

    Nothing ticks it forward; it is a function of how long the world has existed, so
    it is already correct at whatever moment someone happens to look. A ticking clock
    would have to run while the process is dead, which is the one thing it cannot do.
    """
    once = world.pollution(started, now=_at(10))
    again = world.pollution(started, now=_at(10))

    assert once == again, "reading it must not be what moves it"


def test_the_world_remembers_when_it_started(tmp_path):
    """Restarting the process must not restart the world.

    On a real file, closed and reopened, and the epoch is deliberately *not* handed
    back in on the second connection — the reading has to come out of storage. An
    earlier version of this test opened a second `:memory:` database and passed the
    same epoch to both, which is 「同一個常數等於它自己」 and stayed green even with
    stored-epoch reads removed entirely.
    """
    path = str(tmp_path / "world.db")
    writing = db.get_connection(path)
    db.init_schema(writing)
    world.start_world(writing, at=EPOCH)
    writing.close()

    reopened = db.get_connection(path)
    try:
        db.init_schema(reopened)
        assert world.pollution(reopened, now=_at(10)) == 10
    finally:
        reopened.close()


def test_starting_a_world_twice_does_not_move_its_epoch(tmp_path):
    """Opening the app is not the same as creating the world.

    `start_world` runs on every open, so if the second call reset the epoch the clock
    would sit at zero forever — which looks exactly like a clock that works, until
    someone checks whether it ever left the first stage.

    The second call passes a *different* epoch on purpose: handing back the original
    would let a reset pass unnoticed.
    """
    path = str(tmp_path / "world.db")
    conn = db.get_connection(path)
    try:
        db.init_schema(conn)
        world.start_world(conn, at=EPOCH)
        world.start_world(conn, at=_at(29))

        assert world.pollution(conn, now=_at(30)) == 30
    finally:
        conn.close()


def test_an_existing_save_does_not_get_a_brand_new_world(conn):
    """`everliving.db` has months of history in it. Starting its clock at zero would
    say that world began today, which is false and readable — his surroundings would
    snap back to 「水濾一次就能喝」 after months of them getting worse.

    The first agent's `created_at` is a real recorded timestamp, so leaning on it
    recovers a fact rather than inventing one. That distinction is the whole reason
    the scene work refused to backfill: there, no scene had ever been recorded and any
    answer would have been fabricated; here, the date is sitting in the table.
    """
    agent_id = db.create_agent(conn, "陌洲", "修東西的", "沉默")
    conn.execute(
        "UPDATE agents SET created_at = ? WHERE id = ?", (_at(-200).isoformat(), agent_id)
    )
    conn.commit()

    world.start_world(conn)

    assert world.pollution(conn, now=EPOCH) == 200


def test_an_empty_database_starts_its_world_now(conn):
    """Nothing to recover, so the world begins when someone first looks at it."""
    before = datetime.now(timezone.utc)
    world.start_world(conn)

    assert world.pollution(conn, now=before) == 0


# --- it only goes one way -----------------------------------------------------


def test_the_clock_never_goes_backwards(started):
    """單向惡化 is the property, so it gets swept rather than spot-checked."""
    readings = [world.pollution(started, now=_at(day)) for day in range(0, 400, 3)]

    assert readings == sorted(readings)
    assert readings[-1] > readings[0]


def test_a_clock_read_before_its_world_began_reads_zero(started):
    """Clamped rather than negative.

    Clock skew and hand-set test times can both produce a `now` behind the epoch, and
    a negative pressure would read as the world *improving* — the one thing this is
    supposed to be unable to say.
    """
    assert world.pollution(started, now=_at(-5)) == 0


def test_the_clock_is_not_stored_where_the_model_can_write_to_it(started, conn):
    """`agent_state` is written straight from the model's `state_changes`.

    Putting the clock there would hand the thing that must only rise to the one writer
    that can say anything at all — one hallucinated 「汙染:好轉」 and the accumulation
    is gone. So it lives in its own table and nothing in the offline path writes it.
    """
    agent_id = db.create_agent(conn, "陌洲", "修東西的", "沉默")
    db.set_state(conn, agent_id, "汙染", "好轉了")

    assert world.pollution(started, now=_at(50)) > 0, "state must not be able to touch it"


# --- it reaches the story -----------------------------------------------------


def test_the_pressure_reaches_the_offline_prompt(started):
    """Stored but unread would be a number in a database, not a world."""
    _, user_message = _build_prompts(
        {"name": "陌洲", "background": "修東西的", "personality": "沉默"},
        "一天",
        "(還沒有記憶)",
        {},
        [],
        pressure=world.pressure(started, now=_at(2)),
    )

    assert world.pressure(started, now=_at(2)).description in user_message


def test_the_prompt_never_hands_the_model_a_bare_number(started):
    """判準 said it in parentheses: 不是硬塞一句「汙染是 37」.

    A raw index in the prompt gets quoted back as a raw index, and a narrator who
    reports instrument readings is not a person living in the place.
    """
    pressure = world.pressure(started, now=_at(200))
    _, user_message = _build_prompts(
        {"name": "陌洲", "background": "修東西的", "personality": "沉默"},
        "一天",
        "(還沒有記憶)",
        {},
        [],
        pressure=pressure,
    )

    assert str(pressure.index) not in user_message
    assert "汙染" not in user_message or "指數" not in user_message


def test_a_later_world_gives_the_model_different_material(started):
    """The test that would actually fail if the clock did nothing.

    Everything above can pass with a number that rises and is never used. This is the
    one that pins 「玩十次跟玩一次一樣」: two visits far enough apart have to arrive with
    different pressure on the page.
    """

    def prompt_at(days: float) -> str:
        _, user_message = _build_prompts(
            {"name": "陌洲", "background": "修東西的", "personality": "沉默"},
            "一天",
            "(還沒有記憶)",
            {},
            [],
            pressure=world.pressure(started, now=_at(days)),
        )
        return user_message

    assert prompt_at(0) != prompt_at(200)


def test_the_pressure_is_written_as_his_week_rather_than_the_end_of_the_world(started):
    """設計文件 第十一節: 必須局部化 — 「這一週,你認識的某個人正在崩」.

    Civilisation-scale doom changes no `agent_state` and gives the story layer nothing
    to grip, so every stage has to describe something he can touch this week.
    """
    for days in (0, 10, 60, 200, 900):
        description = world.pressure(started, now=_at(days)).description
        assert description.strip()
        assert not any(word in description for word in ("人類", "文明", "滅亡", "全世界"))


def test_every_stage_is_reachable_and_they_read_differently(started):
    """A stage table nobody can reach is set dressing.

    Sweeping a long span has to turn up every stage — otherwise a boundary typo leaves
    one unreachable and the world silently has fewer gears than it claims.
    """
    seen = {world.pressure(started, now=_at(day)).stage for day in range(0, 1200, 2)}

    assert seen == set(range(len(world.STAGES)))
