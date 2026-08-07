"""SQLite storage for a single agent's persona and memory events (Milestone 0)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    background TEXT NOT NULL,
    personality TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_state (
    agent_id INTEGER PRIMARY KEY REFERENCES agents(id),
    last_seen_at TEXT NOT NULL
);

-- What the agent currently has / is / feels. Offline periods change these, so the
-- world is actually different when you come back rather than just described.
CREATE TABLE IF NOT EXISTS agent_state (
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (agent_id, key)
);

-- Unresolved situations that need the player. This is the hook that makes you
-- want to come back: the agent is waiting on you for something.
CREATE TABLE IF NOT EXISTS open_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

-- What the player has asked him to do. The control model is delegation (設計文件
-- 第十二節): you never move anyone, you ask, and it gets carried out — or refused —
-- while you're away. Kept apart from open_threads because the direction is opposite:
-- a thread is what he's waiting on you for, a delegation is what you're waiting on
-- him for. And a delegation has an outcome, which is the whole point of it; a thread
-- only has a status.
CREATE TABLE IF NOT EXISTS delegations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    request TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / done / refused
    outcome TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER REFERENCES agents(id),
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- Video, stills, written pages: anything that illustrates one narrative beat.
-- Empty for a long time by design — the point is that the anchor exists before the
-- assets do, because retrofitting one afterwards means rewriting history.
--
-- Keyed by memory_events.id and never by the narrative text. The text gets retold and
-- compressed as the agent remembers it (see the design doc on memory wear), so an
-- asset tied to wording would drift away from the moment it depicts. The player's
-- evidence has to stay pinned to the source row, which is never rewritten.
CREATE TABLE IF NOT EXISTS story_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_event_id INTEGER NOT NULL REFERENCES memory_events(id),
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- When this world began. One row, and the only thing the world clock needs to store:
-- pollution is a function of how long the world has existed (`world.py`), so there is
-- nothing to tick and nothing that can drift while the process is dead.
--
-- Deliberately not in `agent_state`. That table is written straight from the model's
-- `state_changes`, and a background pressure that only rises must not share a writer
-- with something that can say anything at all — one 「汙染:好轉」 and the accumulation
-- the whole thing exists for is gone.
--
-- No `agent_id`: the world is above the agent. 里程碑 1 puts several agents in it and
-- they have to be standing in the same weather, or there is nothing to have in common.
CREATE TABLE IF NOT EXISTS world (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    started_at TEXT NOT NULL
);

-- Every time the player opened it. `player_state` above holds one row that each visit
-- overwrites, which answers 「他現在在嗎」 and can never answer 「他有沒有再回來」 — and the
-- second one is what 里程碑 0 is graded on (H-1: 一個人隔天想不想再打開).
--
-- Append-only, and deliberately not deduplicated by day: deciding here that two visits
-- in one evening are "really" one would pick, in advance, which questions the data is
-- allowed to answer. That is the mistake this table exists to undo.
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    visited_at TEXT NOT NULL
);

-- What the model actually sent back, before anything was taken off it.
--
-- 第 7 輪 auditor found that this project records the player's half of every exchange
-- and none of 陌洲's: the prompts reach the log at DEBUG, the reply reaches nothing, and
-- `memory_events` keeps the narrative only after `split_scene_tag` has removed the stage
-- directions. It stayed open until 2026-08-07, when three 6-minute runs came back blank
-- and 「模型到底吐了什麼」 could not be answered — `llm_calls` had 3423 output tokens and
-- not one of them to look at.
--
-- Its own table rather than a column on `llm_calls`, so existing databases pick it up
-- from `CREATE TABLE IF NOT EXISTS` with no migration. One row per call, and a call with
-- no row is 「還沒記」 — distinct from a row holding "", which is 「記了,是空的」. Those are
-- different facts and the blank nights are exactly the second kind.
CREATE TABLE IF NOT EXISTS llm_replies (
    llm_call_id INTEGER PRIMARY KEY REFERENCES llm_calls(id),
    reply TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def create_agent(conn: sqlite3.Connection, name: str, background: str, personality: str) -> int:
    cur = conn.execute(
        "INSERT INTO agents (name, background, personality, created_at) VALUES (?, ?, ?, ?)",
        (name, background, personality, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_agent(conn: sqlite3.Connection, agent_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return dict(row) if row else None


def add_memory_event(
    conn: sqlite3.Connection,
    agent_id: int,
    kind: str,
    content: str,
    occurred_at: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO memory_events (agent_id, kind, content, occurred_at, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent_id, kind, content, occurred_at or _now(), _now()),
    )
    conn.commit()
    return cur.lastrowid


def attach_asset(
    conn: sqlite3.Connection, memory_event_id: int, kind: str, ref: str
) -> int:
    """Hang a clip, a still or a page on one narrative beat.

    `ref` is a pointer (a path or a URL), not the bytes: assets are pre-generated and
    reusable, so the same file can serve many beats and the database stays small.
    """
    cur = conn.execute(
        "INSERT INTO story_assets (memory_event_id, kind, ref, created_at) "
        "VALUES (?, ?, ?, ?)",
        (memory_event_id, kind, ref, _now()),
    )
    conn.commit()
    return cur.lastrowid


#: The kinds `attach_scene` writes. They hang off a beat exactly like a clip does, but
#: they are a record of what happened rather than something to show the player.
SCENE_KINDS = ("scene", "action")


def attach_scene(
    conn: sqlite3.Connection,
    memory_event_id: int,
    scene: str | None = None,
    action: str | None = None,
) -> None:
    """Record where a beat was drawn and what was happening there.

    Both axes were reaching the browser and then ceasing to exist, which left the one
    reported mismatch — 「配電所/淹水」 over dialogue still set in the workshop —
    impossible to look into, and any fix for it impossible to verify.

    Two rows rather than one combined value, because the axes failed independently:
    the place was often already right while the picture still didn't match the words.

    `None` writes nothing. "Nothing in particular is happening" is a real state of the
    picture, and a row saying so could not be told apart from one written by mistake.
    """
    if scene:
        attach_asset(conn, memory_event_id, "scene", scene)
    if action:
        attach_asset(conn, memory_event_id, "action", action)


def get_assets(conn: sqlite3.Connection, memory_event_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM story_assets WHERE memory_event_id = ? ORDER BY id",
        (memory_event_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_media_assets(conn: sqlite3.Connection, memory_event_id: int) -> list[dict]:
    """The assets meant to sit beside a beat — a clip, a still, a page.

    Everything the display side sends comes through here rather than `get_assets`,
    because the page renders each row as `kind · ref`: the scene rows went out
    unfiltered once and put `scene · 工作間` next to every line the player read.
    The scene already travels as its own field in the payload, so it was a duplicate
    that could only do harm.

    Use `get_assets` when you want the whole record, which is what the mismatch this
    was all built for will need.
    """
    return [
        asset
        for asset in get_assets(conn, memory_event_id)
        if asset["kind"] not in SCENE_KINDS
    ]


def get_recent_memory(conn: sqlite3.Connection, agent_id: int, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM memory_events WHERE agent_id = ? ORDER BY occurred_at DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def set_last_seen(conn: sqlite3.Connection, agent_id: int, when: str | None = None) -> None:
    ts = when or _now()
    conn.execute(
        "INSERT INTO player_state (agent_id, last_seen_at) VALUES (?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET last_seen_at = excluded.last_seen_at",
        (agent_id, ts),
    )
    conn.commit()


def record_visit(conn: sqlite3.Connection, agent_id: int, at: str | None = None) -> None:
    """Write down that the player arrived. Nothing else.

    Deliberately separate from `set_last_seen`, which records when he *stopped* — the
    offline gap has to be measured from the end of the last session, not the start of
    it. They are two different facts and an earlier draft of this coupled them for
    convenience.

    Arrival is also the honest moment to record: `leave` only fires if the player uses
    the button, so a closed tab would otherwise erase the visit entirely — and 「他關掉
    分頁就不算來過」 is exactly the kind of silent rule that makes a retention number lie.
    """
    conn.execute(
        "INSERT INTO visits (agent_id, visited_at) VALUES (?, ?)", (agent_id, at or _now())
    )
    conn.commit()


def get_visits(conn: sqlite3.Connection, agent_id: int) -> list[dict]:
    """Every visit, oldest first."""
    rows = conn.execute(
        "SELECT * FROM visits WHERE agent_id = ? ORDER BY visited_at", (agent_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def get_last_seen(conn: sqlite3.Connection, agent_id: int) -> str | None:
    row = conn.execute(
        "SELECT last_seen_at FROM player_state WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    return row["last_seen_at"] if row else None


def set_state(conn: sqlite3.Connection, agent_id: int, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO agent_state (agent_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(agent_id, key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (agent_id, key, value, _now()),
    )
    conn.commit()


def get_state(conn: sqlite3.Connection, agent_id: int) -> dict[str, str]:
    rows = conn.execute(
        "SELECT key, value FROM agent_state WHERE agent_id = ? ORDER BY key", (agent_id,)
    ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def add_open_thread(conn: sqlite3.Connection, agent_id: int, description: str) -> int:
    cur = conn.execute(
        "INSERT INTO open_threads (agent_id, description, status, created_at) "
        "VALUES (?, ?, 'open', ?)",
        (agent_id, description, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_open_threads(conn: sqlite3.Connection, agent_id: int, limit: int = 3) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM open_threads WHERE agent_id = ? AND status = 'open' "
        "ORDER BY created_at DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_thread(conn: sqlite3.Connection, thread_id: int) -> None:
    conn.execute(
        "UPDATE open_threads SET status = 'resolved', resolved_at = ? WHERE id = ?",
        (_now(), thread_id),
    )
    conn.commit()


def add_delegation(conn: sqlite3.Connection, agent_id: int, request: str) -> int:
    cur = conn.execute(
        "INSERT INTO delegations (agent_id, request, status, created_at) "
        "VALUES (?, ?, 'pending', ?)",
        (agent_id, request, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_pending_delegations(
    conn: sqlite3.Connection, agent_id: int, limit: int = 3
) -> list[dict]:
    """Oldest first: something asked for three nights ago should be settled before
    something asked for just now, and the cap keeps the prompt (and the bill) bounded
    the same way open threads are."""
    rows = conn.execute(
        "SELECT * FROM delegations WHERE agent_id = ? AND status = 'pending' "
        "ORDER BY created_at ASC LIMIT ?",
        (agent_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_delegation(
    conn: sqlite3.Connection, delegation_id: int, status: str, outcome: str
) -> None:
    """Close one out as done or refused. A refusal is an outcome, not a failure —
    the design doc is explicit that it can say no, so long as it says why."""
    conn.execute(
        "UPDATE delegations SET status = ?, outcome = ?, resolved_at = ? WHERE id = ?",
        (status, outcome, _now(), delegation_id),
    )
    conn.commit()


def record_llm_call(
    conn: sqlite3.Connection,
    agent_id: int | None,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> int:
    """Log token usage so we can answer '每個玩家每天燒多少 API 錢' with real data.

    Returns the row id so the reply can be hung off it (`record_llm_reply`).
    """
    cur = conn.execute(
        "INSERT INTO llm_calls (agent_id, purpose, model, input_tokens, output_tokens, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, purpose, model, input_tokens, output_tokens, _now()),
    )
    conn.commit()
    return cur.lastrowid


def record_llm_reply(conn: sqlite3.Connection, llm_call_id: int, reply: str) -> None:
    """Keep what came back, raw — including when what came back was nothing.

    Empties are the rows worth having. Skipping them would drop precisely the calls
    anyone would want to investigate, which is the hole that made 2026-08-07 take three
    runs to diagnose.
    """
    conn.execute(
        "INSERT OR REPLACE INTO llm_replies (llm_call_id, reply, created_at) VALUES (?, ?, ?)",
        (llm_call_id, reply, _now()),
    )
    conn.commit()


def get_llm_reply(conn: sqlite3.Connection, llm_call_id: int) -> str | None:
    """The raw reply, or None if none was ever recorded.

    `None` and `""` mean different things here — 「還沒記」 versus 「記了,是空的」 — and the
    blank nights are the second kind.
    """
    row = conn.execute(
        "SELECT reply FROM llm_replies WHERE llm_call_id = ?", (llm_call_id,)
    ).fetchone()
    return row["reply"] if row else None


def token_usage_by_day(conn: sqlite3.Connection) -> list[dict]:
    """Per-day, per-model token totals. Multiply by current per-token pricing yourself —
    prices change, so we store the durable fact (tokens) rather than a stale dollar figure."""
    rows = conn.execute(
        "SELECT substr(created_at, 1, 10) AS day, model, COUNT(*) AS calls, "
        "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
        "FROM llm_calls GROUP BY day, model ORDER BY day DESC, model"
    ).fetchall()
    return [dict(row) for row in rows]
