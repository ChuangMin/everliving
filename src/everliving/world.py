"""The world clock: the one thing here that moves without the player.

The human's answer to 「系統還是太簡單了」 was 「單調」, and the root of it was 「玩十次跟玩一次
一樣」 — nothing accumulated, so the scene had no reason to change and he had no new material
to talk about. 設計文件 第十一節 already held the piece for this: pollution as 「單向惡化的
背景壓力,一個不管玩家做什麼都在走的時鐘」. Nothing here invents lore; it makes that run.

Three decisions worth keeping:

**It is derived, not ticked.** Pollution is a function of how long the world has existed,
so it is already correct at whatever moment someone happens to look. That is the same
lazy-simulation bet the offline narrative rests on, and it is the only design that
survives the process being dead for a week — a ticker would have to run while nothing
is running.

**It only rises, by construction rather than by guard.** A monotonic function of elapsed
time cannot be talked down. Nothing in this module writes a level, so there is no code
path that could lower one.

**It reaches the model as his week, never as a reading.** 設計文件 第十一節 requires the
pressure be localised — 「這一週,你認識的某個人正在崩」 — because civilisation-scale doom
changes no `agent_state` and hands the story layer nothing to grip. So the prompt gets
water that needs filtering twice and rust that bites deeper, and never gets a number.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

#: Each stage is (第一天, 這段時間的日子長什麼樣). Read in order; the last one that has
#: started is the one in force.
#:
#: The spacing accelerates on purpose. 設計文件 warns that pushing a background axis too
#: fast costs the world its sense of stability, but a first week that never visibly
#: changes is the very complaint this exists to answer — so the early gears turn in days
#: and the later ones in seasons. Someone who plays ten evenings crosses three stages;
#: someone who plays for a year still has somewhere left to go.
STAGES: list[tuple[int, str]] = [
    (
        0,
        "水濾一次就能喝。工作間的鐵件放著不管,一個月才起一層薄鏽。",
    ),
    (
        4,
        "水要濾兩次,第二次的濾芯會泛黃。手邊的零件開始出現咬得比較深的鏽點,"
        "焊道也比以前難清。",
    ),
    (
        14,
        "濾芯換得比以前勤,喉嚨在夜裡會癢。街上戴口罩的人變多了,"
        "回收場送來的零件十件裡有兩件是鏽穿的。",
    ),
    (
        45,
        "水要放一夜讓它沉,只有上層那半敢用。你認識的人裡開始有人咳得停不下來,"
        "配電所限電的日子從一週一次變成三次。",
    ),
    (
        150,
        "濾水花掉的時間比修東西還長。巷子那頭的老人上個月搬進了模擬倉,"
        "他的房間現在堆著沒人要的零件。",
    ),
]


@dataclass(frozen=True)
class Pressure:
    """What the world feels like right now.

    `index` exists for tests and for anyone debugging the curve. It is deliberately not
    what gets shown to the model — see `describe_for_prompt`.
    """

    index: int
    stage: int
    description: str


def _parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def start_world(conn: sqlite3.Connection, at: datetime | None = None) -> datetime:
    """Record when this world began, once. Returns the epoch, existing or new.

    Idempotent because it runs on every open. Overwriting here would pin the clock to
    the current session and it would read as working right up until someone checked
    whether it had ever left the first stage.
    """
    row = conn.execute("SELECT started_at FROM world WHERE id = 1").fetchone()
    if row is not None:
        return _parse(row["started_at"])

    epoch = at or _inferred_epoch(conn)
    conn.execute("INSERT INTO world (id, started_at) VALUES (1, ?)", (epoch.isoformat(),))
    conn.commit()
    return epoch


def _inferred_epoch(conn: sqlite3.Connection) -> datetime:
    """When this world began, for a save that predates the clock.

    `everliving.db` holds months of history, and starting its clock at zero would say
    that world began today — his surroundings would snap back to clean water after
    months of getting worse, which is both false and visible.

    The first agent's `created_at` is a real recorded timestamp, so this recovers a
    fact. That is the line the scene work drew when it refused to backfill: there, no
    scene had ever been written down and any answer would have been invented; here the
    date is sitting in the table. An empty database has nothing to recover, so its
    world begins the first time someone looks at it.
    """
    row = conn.execute("SELECT MIN(created_at) AS first FROM agents").fetchone()
    if row is not None and row["first"]:
        return _parse(row["first"])
    return datetime.now(timezone.utc)


def _epoch(conn: sqlite3.Connection) -> datetime:
    row = conn.execute("SELECT started_at FROM world WHERE id = 1").fetchone()
    return _parse(row["started_at"]) if row is not None else start_world(conn)


def pollution(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Whole days this world has existed. Never negative, never smaller than before.

    Clamped at zero rather than allowed to go negative: a clock read behind its own
    epoch (clock skew, a hand-set time in a test) would otherwise report the world
    *improving*, which is the one thing it must be unable to say.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    elapsed = moment - _epoch(conn)
    return max(0, elapsed.days)


def pressure(conn: sqlite3.Connection, now: datetime | None = None) -> Pressure:
    """The current level, as something he could point at in his own workshop."""
    index = pollution(conn, now)
    stage = 0
    for position, (first_day, _) in enumerate(STAGES):
        if index >= first_day:
            stage = position
    return Pressure(index=index, stage=stage, description=STAGES[stage][1])


def describe_for_prompt(current: Pressure) -> str:
    """The prompt section. No number reaches the model, and that is the point.

    A raw level gets quoted straight back as a raw level, and a narrator who reports
    instrument readings has stopped being someone who lives in the place. The stage
    text is already written as things he handles, so the instruction only has to stop
    him announcing it.
    """
    return (
        "這陣子這裡的樣子:\n"
        f"{current.description}\n"
        "這是背景,不是新聞——**讓它出現在你做的事和你的身體上,不要拿出來講**,"
        "也不要提任何數字或等級。"
    )
