"""One turn of player <-> agent interaction (T0-3): respond, then remember what happened."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from everliving import db
from everliving.llm import LLMClient, log_usage
from everliving.offline import SCENES

#: The stage direction at the end of a reply. Not dialogue — it never reaches the
#: player, and it must never reach memory either, or the next turn feeds it back as
#: something 陌洲 said.
_SCENE_TAG = re.compile(r"\n*場景[:：]\s*(\S+)\s*$")


@dataclass
class Turn:
    """One exchange. More than the reply, because the display side needs to know
    where he is now, and story assets need something to hang on."""

    reply: str
    #: Where he is after this turn, or None for "leave the picture where it is".
    scene: str | None = None
    #: The `memory_events` row holding the reply — the anchor for a clip or a page.
    event_id: int | None = None


def split_scene_tag(raw: str) -> tuple[str, str | None]:
    """Pull the trailing scene tag off a reply, if it wrote one we can draw."""
    match = _SCENE_TAG.search(raw)
    if not match:
        return raw.strip(), None
    scene = match.group(1)
    # An unknown place would draw nothing, so hold the current picture instead.
    return raw[: match.start()].strip(), scene if scene in SCENES else None


def build_system_prompt(agent: dict, has_open_threads: bool = False) -> str:
    prompt = (
        f"你是{agent['name']}。背景:{agent['background']}\n"
        f"個性:{agent['personality']}\n"
        "用符合這個角色的語氣和邏輯,以第一人稱回應玩家的訊息。"
        "回覆簡短(1-3 句)、有畫面感,不要用條列或客套開場白。"
        # The picture used to sit wherever the last offline period left it while he
        # talked about being somewhere else. One line costs a few tokens and keeps
        # the scene honest to the words.
        "\n回覆結束後另起一行寫 `場景:X`,X 只能從這幾個選一個:"
        f"{'、'.join(SCENES)}。那一行是給畫面用的,不是講給玩家聽的。"
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
) -> Turn:
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

    raw = llm.complete(system_prompt, user_message)
    log_usage(conn, llm, agent_id, purpose="conversation")

    reply, scene = split_scene_tag(raw)

    db.add_memory_event(conn, agent_id, kind="raw", content=f"玩家說:{player_message}")
    event_id = db.add_memory_event(conn, agent_id, kind="raw", content=f"我回答:{reply}")

    return Turn(reply=reply, scene=scene, event_id=event_id)
