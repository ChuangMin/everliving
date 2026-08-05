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


def get_assets(conn: sqlite3.Connection, memory_event_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM story_assets WHERE memory_event_id = ? ORDER BY id",
        (memory_event_id,),
    ).fetchall()
    return [dict(row) for row in rows]


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
) -> None:
    """Log token usage so we can answer '每個玩家每天燒多少 API 錢' with real data."""
    conn.execute(
        "INSERT INTO llm_calls (agent_id, purpose, model, input_tokens, output_tokens, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, purpose, model, input_tokens, output_tokens, _now()),
    )
    conn.commit()


def token_usage_by_day(conn: sqlite3.Connection) -> list[dict]:
    """Per-day, per-model token totals. Multiply by current per-token pricing yourself —
    prices change, so we store the durable fact (tokens) rather than a stale dollar figure."""
    rows = conn.execute(
        "SELECT substr(created_at, 1, 10) AS day, model, COUNT(*) AS calls, "
        "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
        "FROM llm_calls GROUP BY day, model ORDER BY day DESC, model"
    ).fetchall()
    return [dict(row) for row in rows]
