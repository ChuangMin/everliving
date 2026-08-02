"""Offline-time tracking and narrative generation (T0-4/T0-5)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from everliving import db
from everliving.llm import LLMClient, log_usage


def time_since_last_seen(
    conn: sqlite3.Connection, agent_id: int, now: datetime | None = None
) -> timedelta | None:
    """How long it's been since the player was last seen, or None if never seen before."""
    last_seen = db.get_last_seen(conn, agent_id)
    if last_seen is None:
        return None
    now = now or datetime.now(timezone.utc)
    return now - datetime.fromisoformat(last_seen)


def _format_duration(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes < 1:
        return "不到一分鐘"
    days, remainder_minutes = divmod(total_minutes, 60 * 24)
    hours, minutes = divmod(remainder_minutes, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小時")
    if minutes and not days:
        parts.append(f"{minutes} 分鐘")
    return " ".join(parts) or "不到一分鐘"


def generate_offline_narrative(
    conn: sqlite3.Connection,
    agent_id: int,
    llm: LLMClient,
    elapsed: timedelta,
    memory_limit: int = 10,
) -> str:
    """One LLM call: given how long the player was away + recent memory, narrate what happened."""
    agent = db.get_agent(conn, agent_id)
    if agent is None:
        raise ValueError(f"unknown agent_id={agent_id}")

    recent = db.get_recent_memory(conn, agent_id, limit=memory_limit)
    memory_text = "\n".join(f"- {event['content']}" for event in reversed(recent)) or "(還沒有記憶)"
    duration_text = _format_duration(elapsed)

    system_prompt = (
        f"你是{agent['name']}。背景:{agent['background']}\n"
        f"個性:{agent['personality']}\n"
        "玩家離開了一段時間,現在要回來了。用第一人稱、符合角色個性的語氣,"
        "簡短敘述(2-4 句)這段時間你做了什麼——要具體、有畫面感,不要只是空泛地說『我很好』。"
    )
    user_message = (
        f"玩家離開了 {duration_text}。\n"
        f"你最近的記憶:\n{memory_text}\n\n"
        "描述這段時間你做了什麼。"
    )

    narrative = llm.complete(system_prompt, user_message)
    log_usage(conn, llm, agent_id, purpose="offline_narrative")
    db.add_memory_event(conn, agent_id, kind="offline_narrative", content=narrative)
    return narrative
