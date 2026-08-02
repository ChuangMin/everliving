"""The single hardcoded agent persona for Milestone 0. Original character, no borrowed IP."""

from __future__ import annotations

import sqlite3

from everliving import db

DEFAULT_PERSONA = {
    "name": "陌洲",
    "background": (
        "生活在未來地球一座半沉沒港城裡的技師,靠修理老舊維生系統維生。"
        "話不多,但對答應過的事情極度固執。"
    ),
    "personality": "務實、寡言、對陌生人有戒心但重情義,一旦認定的朋友會照顧到底。",
}


def seed_default_agent(conn: sqlite3.Connection) -> int:
    """Create the Milestone-0 agent if it doesn't exist yet; return its id."""
    existing = conn.execute(
        "SELECT id FROM agents WHERE name = ?", (DEFAULT_PERSONA["name"],)
    ).fetchone()
    if existing:
        return existing["id"]
    return db.create_agent(
        conn,
        name=DEFAULT_PERSONA["name"],
        background=DEFAULT_PERSONA["background"],
        personality=DEFAULT_PERSONA["personality"],
    )
