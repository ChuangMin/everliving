"""One turn of player <-> agent interaction (T0-3): respond, then remember what happened."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from everliving import db
from everliving.llm import LLMClient, log_usage
from everliving.offline import ACTIONS, SCENES

#: The stage direction at the end of a reply. Not dialogue — it never reaches the
#: player, and it must never reach memory either, or the next turn feeds it back as
#: something 陌洲 said.
_TAGS = re.compile(r"\n*(?:場景[:：]\s*(\S+)|動作[:：]\s*(\S+))\s*$")


@dataclass
class Turn:
    """One exchange. More than the reply, because the display side needs to know
    where he is now, and story assets need something to hang on."""

    reply: str
    #: Where he is after this turn, or None for "leave the picture where it is".
    scene: str | None = None
    #: What is happening there — welding, a blackout — or None for nothing in
    #: particular. Separate from `scene` because the place was often already right
    #: while the picture still failed to match the words.
    action: str | None = None
    #: The `memory_events` row holding the reply — the anchor for a clip or a page.
    event_id: int | None = None


def split_scene_tag(raw: str) -> tuple[str, str | None, str | None]:
    """Strip the trailing stage directions off a reply.

    Tags are matched from the end and peeled off one at a time, so their order doesn't
    matter and a model that writes only one of them still parses. Anything we can't
    draw resolves to None, which the display side reads as "don't change it" — a
    missed tag has to freeze the picture, never send it somewhere wrong.
    """
    text, scene, action = raw.strip(), None, None
    while True:
        match = _TAGS.search(text)
        if not match:
            return text.strip(), scene, action
        if match.group(1) is not None and scene is None:
            scene = match.group(1) if match.group(1) in SCENES else None
        elif match.group(2) is not None and action is None:
            action = match.group(2) if match.group(2) in ACTIONS else None
        text = text[: match.start()].strip()


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
        f"{'、'.join(SCENES)}。\n"
        # Place alone wasn't enough: he'd describe a welding arc and the picture
        # showed a generic workshop, because the workshop *was* the right place.
        "如果此刻正在發生下面其中一件事,再另起一行寫 `動作:Y`(沒有就不要寫這行):"
        f"{'、'.join(ACTIONS)}。\n"
        "這兩行是給畫面用的,不是講給玩家聽的。"
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

    reply, scene, action = split_scene_tag(raw)

    db.add_memory_event(conn, agent_id, kind="raw", content=f"玩家說:{player_message}")
    event_id = db.add_memory_event(conn, agent_id, kind="raw", content=f"我回答:{reply}")

    return Turn(reply=reply, scene=scene, action=action, event_id=event_id)
