"""The opening shot stops being the same picture every time.

`offline.py` pinned the opening to 工作間 on purpose — 陌洲 repairs old life-support
systems, so his bench says who he is without a line of dialogue. That reasoning is right
on the first visit and becomes 「畫面都一樣」 by the tenth, which is one of the four axes
the human named when he said 「單調」.

The fix is not randomness. A shuffled opening flickers without meaning, and the whole
complaint was that nothing accumulates — so the opening follows the one thing that now
does accumulate (the world clock), with his own body allowed to overrule it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from everliving import db, persona, world
from everliving.offline import OPENING_BY_STAGE, opening_scene

EPOCH = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _at(days: float) -> datetime:
    return EPOCH + timedelta(days=days)


@pytest.fixture
def agent_id(conn):
    world.start_world(conn, at=EPOCH)
    return persona.seed_default_agent(conn)


def test_a_new_world_still_opens_on_his_bench(conn, agent_id):
    """The original reason survives where it was right: the first visit.

    Nothing has gone wrong yet, so there is nothing else for the opening to be about,
    and the bench is still the fastest way to say who he is.
    """
    assert opening_scene(conn, agent_id, now=_at(0)) == "工作間"


def test_three_visits_far_enough_apart_do_not_all_look_the_same(conn, agent_id):
    """判準: 連開三次至少看到兩種不同的開場.

    Spread across the clock rather than repeated at one moment, because that is what
    actually happens — 「玩十次跟玩一次一樣」 was a complaint about ten *evenings*.
    """
    seen = {opening_scene(conn, agent_id, now=_at(day)) for day in (0, 20, 200)}

    assert len(seen) >= 2


def test_the_opening_is_decided_rather_than_rolled(conn, agent_id):
    """Same world, same state, same answer — every time.

    A random opening would read as flicker, and flicker is not accumulation. It would
    also make the picture stop meaning anything, which is worse than one picture that
    at least meant something.
    """
    answers = {opening_scene(conn, agent_id, now=_at(60)) for _ in range(20)}

    assert len(answers) == 1


def test_every_opening_is_a_scene_the_page_can_draw(conn, agent_id):
    """`SCENES` is a closed vocabulary because each value has a drawing.

    An opening the display side doesn't know would render nothing at all — the failure
    `DEFAULT_SCENE` exists to prevent, reintroduced from the other end.
    """
    from everliving.offline import SCENES

    assert set(OPENING_BY_STAGE) <= set(SCENES)
    assert len(OPENING_BY_STAGE) == len(world.STAGES), "every stage needs an opening"


def test_a_hurt_body_keeps_him_at_his_bench(conn, agent_id):
    """His own state overrules the world's.

    Whatever the tide or the rationing is doing, a man with an inflamed wrist is at his
    bench — that is where the story actually is that evening. It also keeps the one
    piece of state the player has personally seen change from being ignored by the
    picture, which is what 「代打沒甚麼反應」 felt like.
    """
    late = opening_scene(conn, agent_id, now=_at(200))
    assert late != "工作間", "otherwise this test proves nothing"

    db.set_state(conn, agent_id, "右手腕機能", "發炎受限")

    assert opening_scene(conn, agent_id, now=_at(200)) == "工作間"


def test_an_unrelated_state_change_does_not_move_the_opening(conn, agent_id):
    """Only his body overrules the world, not any state at all.

    Without this the rule would read as 「有狀態就回工作間」, and since he almost always
    has some state, the opening would collapse back to one picture — the bug this
    round exists to remove, reintroduced by a rule that is too eager.
    """
    before = opening_scene(conn, agent_id, now=_at(200))

    db.set_state(conn, agent_id, "庫存狀態", "多出一枚導航晶片")

    assert opening_scene(conn, agent_id, now=_at(200)) == before
