"""An AI sitting in the player's seat.

Why this exists: "the world keeps living while you're away" is almost impossible to
show in a screenshot, and H-1 is blocked on a person being willing to sit down. An
agent visitor makes the loop visible and exercisable on demand.

**What it cannot do is answer H-1.** H-1 asks whether *you* want to come back, and a
model saying it found the conversation interesting is not evidence of that. Autoplay
is a demo and a pressure test, never the validation — treating it as validation would
be the third time this project's核心賭注 went unasked.

Note what is deliberately absent: the visitor is never announced to 陌洲 as an AI. The
architecture reservation says the world doesn't need to know whether a resident is a
person or an agent (第五節〈架構預留〉統一居民介面), and this is the first thing to
actually rely on it. The distinction lives in `llm_calls.purpose`, where it belongs —
in the books, not in the fiction.
"""

from __future__ import annotations

import sqlite3

from everliving import db
from everliving.llm import LLMClient, log_usage

#: Trailing/leading quote marks a model likes to wrap a line of dialogue in. Left in,
#: they'd be typed into the game as if the visitor had actually said them.
_QUOTES = "「」\"'“”『』 \n"

SYSTEM_PROMPT = (
    "你是一個來找{name}說話的人。{name}是{background}\n"
    "你對他的生活有興趣,講話像個普通人,不像記者也不像客服。\n"
    "只輸出你要說的那一句話,不要加引號、不要解釋、不要旁白。"
    "一次一句,最多兩句,口語,繁體中文。"
    "如果他提到還沒解決的事,就接著那件事問或回應——不要每次都換新話題。"
)


def next_message(
    conn: sqlite3.Connection, agent_id: int, llm: LLMClient, memory_limit: int = 8
) -> str:
    """Decide what the visitor says next, given what's already been said."""
    agent = db.get_agent(conn, agent_id)
    if agent is None:
        raise ValueError(f"unknown agent_id={agent_id}")

    recent = db.get_recent_memory(conn, agent_id, limit=memory_limit)
    history = "\n".join(f"- {event['content']}" for event in reversed(recent))

    system_prompt = SYSTEM_PROMPT.format(name=agent["name"], background=agent["background"])
    user_message = (
        f"到目前為止發生過的事:\n{history or '(還沒說過話)'}\n\n"
        "你現在要說什麼?"
    )

    raw = llm.complete(system_prompt, user_message)
    # Recorded separately from a real player's turn: same fiction, different books.
    log_usage(conn, llm, agent_id, purpose="auto_visitor")

    line = raw.strip().splitlines()[0] if raw.strip() else ""
    return line.strip(_QUOTES).strip()
