"""Offline-time tracking and simulation.

The point of this module is the core bet: while you're away, things actually happen.
Not a diary entry — the agent's state changes, and it can end up waiting on you for
something. That unresolved thread is what should make you want to come back.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from everliving import db
from everliving.llm import LLMClient, log_usage
from everliving.script_check import warn_if_simplified

_log = logging.getLogger(__name__)



#: Below this, "you were away" isn't true enough to be worth a story.
#: Without a floor, quitting and relaunching immediately fires a full simulation —
#: which bills an LLM call, invents a whole offline period, and adds a thread for an
#: absence of thirty seconds. That's a cost hole as much as a narrative one.
MIN_OFFLINE_GAP = timedelta(minutes=30)


def is_worth_simulating(elapsed: timedelta | None, minimum: timedelta = MIN_OFFLINE_GAP) -> bool:
    """Whether a gap is long enough that something could plausibly have happened."""
    return elapsed is not None and elapsed >= minimum


#: Where a narrative took place. A closed vocabulary on purpose: the display side
#: has one drawing per scene, so a value it doesn't know about would render nothing.
#: The model picks from this list rather than inventing places, which also keeps it
#: from quietly adding geography (generating places is the expensive kind — see the
#: design doc on rings).
SCENES = ("工作間", "回收場", "潮線", "配電所", "機器廠", "港城")

#: Where to land when the model names a place we can't draw. The city panorama is the
#: widest and always-plausible catch-all, so a bad value degrades instead of breaking.
DEFAULT_SCENE = "港城"

#: What the player sees on a visit with no offline period to show — the opening shot.
#: Deliberately *not* DEFAULT_SCENE: those are unrelated jobs, and sharing one constant
#: meant the game opened on a city panorama by accident rather than by choice. 陌洲
#: repairs old life-support systems for a living, so his workshop is both the most
#: personal scene and the one that says who he is without a line of dialogue.
OPENING_SCENE = "工作間"

#: What is happening, as opposed to where. `scene` alone kept producing a mismatch the
#: player noticed immediately: he'd describe a welding arc on a valve face and the
#: picture showed a generic workshop. A place tag can't fix that, because the place was
#: already right. So this is a second axis on the same closed-vocabulary principle —
#: each value has a visible rendering, and anything else falls back to none.
#: Kept deliberately short: every entry has to be worth drawing, and a long list would
#: cost prompt room that the narrative itself needs.
ACTIONS = ("焊接", "停電", "淹水", "起霧")
NO_ACTION = ""


@dataclass
class OfflineResult:
    narrative: str
    events: list[str] = field(default_factory=list)
    state_changes: dict[str, str] = field(default_factory=dict)
    open_thread: str | None = None
    resolved_thread_ids: list[int] = field(default_factory=list)
    scene: str = DEFAULT_SCENE
    #: How each thing the player asked for turned out: `{id, status, outcome}` with
    #: status either `done` or `refused`. This is the whole of the delegation model —
    #: you asked, you left, and this is what you come back to.
    delegation_outcomes: list[dict] = field(default_factory=list)
    #: What was happening, as opposed to where. The conversation path has had this
    #: since the player noticed the picture disagreeing with the words; the offline
    #: path never did, so a night could say it was spent in the workshop but never
    #: that the lights were out the whole time. None means nothing in particular.
    action: str | None = None
    #: The `memory_events` row this narrative was stored as — the anchor a video, a
    #: still or a written page attaches to later (see the design doc, 第五節). None
    #: when the result was parsed but never persisted.
    narrative_event_id: int | None = None


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


def _extract_json(raw: str) -> dict | None:
    """Pull a JSON object out of an LLM response, tolerating code fences and stray prose."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_offline_response(raw: str) -> OfflineResult:
    """Structured if the model complied, graceful degradation to plain prose if it didn't.

    A malformed response must never lose the narrative — that's the one thing the
    player actually reads.
    """
    parsed = _extract_json(raw)
    if parsed is None:
        return OfflineResult(narrative=raw.strip())

    narrative = str(parsed.get("narrative") or "").strip() or raw.strip()

    events = [str(item) for item in parsed.get("events") or [] if str(item).strip()]

    raw_changes = parsed.get("state_changes") or {}
    state_changes = (
        {str(k): str(v) for k, v in raw_changes.items()} if isinstance(raw_changes, dict) else {}
    )

    open_thread = parsed.get("open_thread")
    open_thread = str(open_thread).strip() if open_thread else None

    resolved = parsed.get("resolved_thread_ids") or []
    resolved_thread_ids = []
    if isinstance(resolved, list):
        for item in resolved:
            try:
                resolved_thread_ids.append(int(item))
            except (TypeError, ValueError):
                continue

    outcomes = []
    raw_outcomes = parsed.get("delegation_outcomes")
    if isinstance(raw_outcomes, list):
        for item in raw_outcomes:
            if not isinstance(item, dict):
                continue
            try:
                item_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            # Anything that isn't an explicit refusal counts as done. A status the
            # model invented must not leave the errand hanging forever — an unparsable
            # answer is still an answer that the night happened.
            status = "refused" if str(item.get("status", "")).strip() == "refused" else "done"
            outcome = str(item.get("outcome") or "").strip()
            if outcome:
                outcomes.append({"id": item_id, "status": status, "outcome": outcome})

    scene = str(parsed.get("scene") or "").strip()
    if scene not in SCENES:  # an unknown place would draw nothing at all
        scene = DEFAULT_SCENE

    # Unlike scene, this has no fallback: "nothing in particular is happening" is a
    # real state of the picture, so an unrecognised value degrades to it rather than
    # to some default weather the narrative never mentioned.
    action = str(parsed.get("action") or "").strip()
    action = action if action in ACTIONS else None

    result = OfflineResult(
        narrative=narrative,
        events=events,
        state_changes=state_changes,
        open_thread=open_thread,
        resolved_thread_ids=resolved_thread_ids,
        delegation_outcomes=outcomes,
        scene=scene,
        action=action,
    )
    _warn_about_simplified(result)
    return result


def _warn_about_simplified(result: OfflineResult) -> None:
    """The state-change keys are read as carefully as the prose.

    The prompt calls those keys out by name because the player sees them on screen,
    so a slip there is more visible than one buried mid-sentence, not less.
    """
    warn_if_simplified(
        result.narrative,
        *result.events,
        *result.state_changes,
        *result.state_changes.values(),
    )


def _build_prompts(
    agent: dict,
    duration_text: str,
    memory_text: str,
    state: dict[str, str],
    threads: list[dict],
    delegations: list[dict] | None = None,
) -> tuple[str, str]:
    # Three jobs, so three rules, and the order between them matters. "Usually leave a
    # thread behind" is the right default *only* when nothing else can produce one —
    # it's what gives the player a reason to come back. Anything else that can produce
    # a hook has to take precedence over it, or the two instructions disagree and the
    # model obeys both:
    #
    # - an open thread already exists: asking for another produced a restatement of
    #   the first, so `resolved` sat at 0 and the panel showed the same待辦 twice
    # - a delegation is pending: a refusal already becomes a thread, and a live run
    #   duly returned the refusal *and* an open_thread saying the same thing in
    #   different words. Same defect, a door I opened myself one session later.
    if threads:
        thread_rule = (
            "2. **你已經有還沒解決的事了,而它的下一步就是這段時間最該發生的東西。**"
            "預設是把那件事**往前推**,不是再開一條:發展寫進 events 跟 narrative,"
            "open_thread 填 null。真的另外冒出一件不相干的事,才開新的一條。\n"
            "**同一件事換句話說寫成一條新的懸念,在玩家眼裡就是這件事永遠不會結束。**\n"
        )
    elif delegations:
        thread_rule = (
            "2. **這一輪的懸念會從委託的下場自己長出來**——尤其是你拒絕的時候,"
            "拒絕的理由本身就是玩家要回來面對的事。所以 open_thread **預設填 null**,"
            "真的另外冒出一件跟那件委託不相干的事,才寫進去。\n"
        )
    else:
        thread_rule = (
            "2. 通常要留下一件**懸而未決、需要玩家回應的事**(open_thread)。"
            "這是玩家下次想回來的理由。但不要每次都硬塞,沒有就填 null。\n"
        )

    # Only present when there is something to settle. The refusal rules are the design
    # doc's (第十二節): always obeying makes him a puppet and kills the one thing being
    # sold, but refusing without a reason grounded in his own state reads as the system
    # failing rather than as a person saying no. And a refusal has to leave something
    # behind — he said no *because* of something, and that something is the new hook.
    if delegations:
        delegation_rule = (
            "4. **玩家請你做的事,這段時間要有下場**,每一件都要出現在 delegation_outcomes。\n"
            "   - 你**可以拒絕**,但理由必須來自你上面的狀態或你的個性,而且要讀起來像個人,不像系統失敗\n"
            "   - **拒絕的那件事本身就是新的懸念**,所以 open_thread 不用再重複寫一次\n"
            "   - 也可以做了但撞上別的事——那就是 done,結果寫實際發生的\n"
        )
    else:
        delegation_rule = ""

    system_prompt = (
        f"你是{agent['name']}。背景:{agent['background']}\n"
        f"個性:{agent['personality']}\n\n"
        "玩家離開了一段時間,現在要回來了。決定這段時間你身上**實際發生了什麼**。\n"
        "規則:\n"
        "1. 必須有具體後果——你得到或失去了什麼、做了一個決定、跟誰起了衝突或建立了關係。"
        "不可以只是『我過得還好』這種沒有後果的描述。\n"
        f"{thread_rule}"
        "3. 如果既有的未解事項已經因為這段時間的發展而結束,把它的 id 放進 resolved_thread_ids。\n"
        f"{delegation_rule}"
        "\n"
        "4. **所有文字一律用繁體中文,包括 state_changes 的鍵名**"
        "(要寫「手部狀態」不是 physical_status)。玩家看得到這些鍵名。\n\n"
        "只輸出 JSON,不要有其他文字:\n"
        "{\n"
        '  "narrative": "2-4 句第一人稱敘述,給玩家讀的,要有畫面感",\n'
        '  "events": ["具體發生的事,一句一件"],\n'
        '  "state_changes": {"中文狀態名": "中文的新值"},\n'
        '  "open_thread": "需要玩家回應的懸念,或 null",\n'
        '  "resolved_thread_ids": [已解決的既有事項 id],\n'
        '  "delegation_outcomes": [{"id": 委託的 id, "status": "done" 或 "refused", '
        '"outcome": "一句話說結果或拒絕的理由"}],\n'
        f'  "scene": "這段敘事主要發生在哪,只能從這幾個選一個:{"、".join(SCENES)}",\n'
        f'  "action": "這段時間主要在發生什麼,只能從這幾個選一個:{"、".join(ACTIONS)};'
        '沒有特別在發生什麼就填 null"\n'
        "}"
    )

    state_text = (
        "\n".join(f"- {key}:{value}" for key, value in state.items()) if state else "(還沒有)"
    )
    threads_text = (
        "\n".join(f"- [id={thread['id']}] {thread['description']}" for thread in threads)
        if threads
        else "(沒有)"
    )
    sections = [
        f"玩家離開了 {duration_text}。",
        f"你目前的狀態:\n{state_text}",
        f"還沒解決的事:\n{threads_text}",
    ]
    if delegations:
        sections.append(
            "玩家請你做、還沒有下場的事:\n"
            + "\n".join(f"- [id={d['id']}] {d['request']}" for d in delegations)
        )
    sections.append(f"你最近的記憶:\n{memory_text}")
    sections.append("這段時間你身上發生了什麼?")
    return system_prompt, "\n\n".join(sections)


def simulate_offline_period(
    conn: sqlite3.Connection,
    agent_id: int,
    llm: LLMClient,
    elapsed: timedelta,
    memory_limit: int = 10,
) -> OfflineResult:
    """One LLM call covering the whole offline window, then persist its consequences.

    Lazy simulation (design doc): we don't tick through the offline period, we
    generate it once on demand. That's the cost structure the whole project rests on.
    """
    agent = db.get_agent(conn, agent_id)
    if agent is None:
        raise ValueError(f"unknown agent_id={agent_id}")

    recent = db.get_recent_memory(conn, agent_id, limit=memory_limit)
    memory_text = "\n".join(f"- {event['content']}" for event in reversed(recent)) or "(還沒有記憶)"
    state = db.get_state(conn, agent_id)
    threads = db.get_open_threads(conn, agent_id)
    delegations = db.get_pending_delegations(conn, agent_id)

    system_prompt, user_message = _build_prompts(
        agent, _format_duration(elapsed), memory_text, state, threads, delegations
    )

    raw = llm.complete(system_prompt, user_message)
    log_usage(conn, llm, agent_id, purpose="offline_narrative")
    result = parse_offline_response(raw)

    # Keep the id: this row is what story assets hang on, and it can only be captured
    # here — reconstructing "which beat was that" from the text afterwards is exactly
    # the fragile matching the design doc rules out.
    result.narrative_event_id = db.add_memory_event(
        conn, agent_id, kind="offline_narrative", content=result.narrative
    )
    for event in result.events:
        db.add_memory_event(conn, agent_id, kind="offline_event", content=event)
    for key, value in result.state_changes.items():
        db.set_state(conn, agent_id, key, value)

    known_thread_ids = {thread["id"] for thread in threads}
    for thread_id in result.resolved_thread_ids:
        if thread_id in known_thread_ids:  # never let a hallucinated id touch the DB
            db.resolve_thread(conn, thread_id)

    # Same guard as thread ids: an id the model invented must never touch the DB, or a
    # hallucinated number would close an errand the player is still waiting on.
    known_delegation_ids = {item["id"] for item in delegations}
    for outcome in result.delegation_outcomes:
        if outcome["id"] not in known_delegation_ids:
            continue
        db.resolve_delegation(conn, outcome["id"], outcome["status"], outcome["outcome"])
        # 設計文件 第十二節: a refusal has to generate a thread. He said no because of
        # something, and that something is what the player has to come back to.
        if outcome["status"] == "refused":
            db.add_open_thread(conn, agent_id, outcome["outcome"])
        db.add_memory_event(
            conn,
            agent_id,
            kind="offline_event",
            content=outcome["outcome"],
        )

    if result.open_thread:
        db.add_open_thread(conn, agent_id, result.open_thread)

    return result


def generate_offline_narrative(
    conn: sqlite3.Connection,
    agent_id: int,
    llm: LLMClient,
    elapsed: timedelta,
    memory_limit: int = 10,
) -> str:
    """Narrative-only convenience wrapper for callers that just want the text."""
    return simulate_offline_period(conn, agent_id, llm, elapsed, memory_limit).narrative
