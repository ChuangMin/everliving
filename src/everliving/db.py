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
