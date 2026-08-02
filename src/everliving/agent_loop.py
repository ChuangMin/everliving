"""One turn of player <-> agent interaction (T0-3): respond, then remember what happened."""

from __future__ import annotations

import sqlite3

from everliving import db
from everliving.llm import LLMClient


def build_system_prompt(agent: dict) -> str:
    return (
        f"你是{agent['name']}。背景:{agent['background']}\n"
        f"個性:{agent['personality']}\n"
        "用符合這個角色的語氣和邏輯,以第一人稱回應玩家的訊息。"
        "回覆簡短(1-3 句)、有畫面感,不要用條列或客套開場白。"
    )


def _format_recent_memory(events: list[dict]) -> str:
    if not events:
        return "(還沒有記憶)"
    return "\n".join(f"- {event['content']}" for event in reversed(events))


def respond(
    conn: sqlite3.Connection,
    agent_id: int,
    llm: LLMClient,
    player_message: str,
    memory_limit: int = 10,
) -> str:
    agent = db.get_agent(conn, agent_id)
    if agent is None:
        raise ValueError(f"unknown agent_id={agent_id}")

    system_prompt = build_system_prompt(agent)
    recent = db.get_recent_memory(conn, agent_id, limit=memory_limit)
    memory_text = _format_recent_memory(recent)
    user_message = f"最近的記憶:\n{memory_text}\n\n玩家對你說:{player_message}"

    reply = llm.complete(system_prompt, user_message)

    db.add_memory_event(conn, agent_id, kind="raw", content=f"玩家說:{player_message}")
    db.add_memory_event(conn, agent_id, kind="raw", content=f"我回答:{reply}")

    return reply
