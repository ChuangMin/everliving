"""One turn of player <-> agent interaction (T0-3): respond, then remember what happened."""

from __future__ import annotations

import sqlite3

from everliving import db
from everliving.llm import LLMClient, log_usage


def build_system_prompt(agent: dict, has_open_threads: bool = False) -> str:
    prompt = (
        f"你是{agent['name']}。背景:{agent['background']}\n"
        f"個性:{agent['personality']}\n"
        "用符合這個角色的語氣和邏輯,以第一人稱回應玩家的訊息。"
        "回覆簡短(1-3 句)、有畫面感,不要用條列或客套開場白。"
    )
    if has_open_threads:
        # Without this the agent never surfaces what it's waiting on, and the
        # offline period stops having any pull on the player.
        prompt += (
            "\n你有還沒解決、需要這個玩家回應的事。如果對話有一點空間,"
            "就自然地提起來——用你的個性提,不要像在唸待辦清單。"
        )
    return prompt


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

    threads = db.get_open_threads(conn, agent_id)
    state = db.get_state(conn, agent_id)
    system_prompt = build_system_prompt(agent, has_open_threads=bool(threads))

    recent = db.get_recent_memory(conn, agent_id, limit=memory_limit)
    memory_text = _format_recent_memory(recent)

    sections = []
    if state:
        sections.append(
            "你目前的狀態:\n" + "\n".join(f"- {key}:{value}" for key, value in state.items())
        )
    if threads:
        sections.append(
            "你還沒解決、跟這個玩家有關的事:\n"
            + "\n".join(f"- {thread['description']}" for thread in threads)
        )
    sections.append(f"最近的記憶:\n{memory_text}")
    sections.append(f"玩家對你說:{player_message}")
    user_message = "\n\n".join(sections)

    reply = llm.complete(system_prompt, user_message)
    log_usage(conn, llm, agent_id, purpose="conversation")

    db.add_memory_event(conn, agent_id, kind="raw", content=f"玩家說:{player_message}")
    db.add_memory_event(conn, agent_id, kind="raw", content=f"我回答:{reply}")

    return reply
