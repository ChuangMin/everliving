"""Rehearse the H-1 five-step sequence with the visitor agent in the player's seat.

**This is not H-1 and cannot answer it.** H-1 asks whether *you* want to open it
again; an agent driving the loop can only tell us whether the loop runs, what the
narrative reads like, whether state and threads actually connect across sessions,
and what four steps cost. Read the output as a rehearsal, never as validation.

Why it drives `web.Session` rather than the HTTP layer: that is the same object the
page's buttons call, so what runs here is the real path rather than a second copy
of it. Each step builds a *fresh* Session, which is what closing the tab and
launching the next command actually does — `Session.opened` is per run, so reusing
one would silently skip the offline simulation the whole test is about.

The database defaults to a scratch file. Whether to clear `everliving.db` is the
human's call, and a rehearsal has no business making it.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from everliving import db, logs
from everliving.config import load_dotenv
from everliving.web import Session

#: offline_hours per step, mirroring the four commands in TASKS.md's H-1 entry:
#: first visit, come back a day later, answer immediately, come back a day later.
STEPS = (
    (None, "第一次打開 — 聊幾句"),
    (24.0, "隔天回來 — 讀敘事、看狀態變化"),
    (0.0, "馬上回來 — 回應它在等的那件事"),
    (24.0, "隔天回來 — 看它有沒有接住"),
)


def _out(*parts: str) -> None:
    print(*parts, flush=True)


def _show_open(payload: dict) -> None:
    offline = payload.get("offline")
    if offline is None:
        _out("  (沒有離線期間可演)")
    else:
        _out(f"  [場景] {offline['scene']}")
        _out(f"  [敘事] {offline['narrative']}")
        for event in offline["events"]:
            _out(f"    · {event}")
        for key, value in (offline["state_changes"] or {}).items():
            _out(f"    [狀態] {key} = {value}")
        if offline["open_thread"]:
            _out(f"    [懸念] {offline['open_thread']}")
    _out(f"  [帳面] {payload['ledger']}")


def _show_turn(index: int, payload: dict) -> None:
    if payload.get("error"):
        _out(f"  ! {payload['error']}")
        return
    _out(f"  訪客{index}:{payload['visitor']}")
    _out(f"  陌洲{index}:{payload['reply']}")
    tags = [payload.get("scene") or "-", payload.get("action") or "-"]
    _out(f"    (場景/動作:{tags[0]} / {tags[1]})")


def _show_standing(payload: dict) -> None:
    state = payload.get("state") or {}
    if state:
        _out("  [收尾狀態]")
        for key, value in state.items():
            _out(f"    {key} = {value}")
    threads = payload.get("threads") or []
    if threads:
        _out("  [還開著的懸念]")
        for thread in threads:
            _out(f"    · {thread}")


def _cost_report(conn: sqlite3.Connection) -> None:
    _out("\n=== 這一趟花了多少 ===")
    for row in db.token_usage_by_day(conn):
        _out(
            f"  {row['day']} {row['model']}: {row['calls']} 次呼叫,"
            f"input {row['input_tokens']} / output {row['output_tokens']}"
        )
    _out("  依用途分項:")
    rows = conn.execute(
        "SELECT purpose, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
        "SUM(output_tokens) AS output_tokens FROM llm_calls "
        "GROUP BY purpose ORDER BY calls DESC"
    ).fetchall()
    for row in rows:
        _out(
            f"    {row['purpose']}: {row['calls']} 次,"
            f"input {row['input_tokens']} / output {row['output_tokens']}"
        )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="h1-autoplay")
    parser.add_argument(
        "--db",
        default="h1_rehearsal.db",
        help="跑在哪個 DB(預設另開一個,不動 everliving.db)。",
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument(
        "--turns", type=int, default=3, metavar="N", help="每一步讓 AI 代打幾輪。"
    )
    parser.add_argument(
        "--log-file",
        default="h1_autoplay.log",
        help="這一趟的記錄寫去哪(跟 everliving.log 分開,免得蓋掉真人 playtest 的記錄)。",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp950
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    # console=False: the transcript below *is* the output, and interleaving the log
    # into it makes the run unreadable. The file still gets every timing and failure.
    logs.setup(args.log_file, console=False)

    for index, (offline_hours, label) in enumerate(STEPS, start=1):
        _out(f"\n=== 第 {index} 步:{label}(offline_hours={offline_hours}) ===")
        # Fresh Session = closed the tab, Ctrl-C, ran the next line.
        session = Session(args.db, args.provider, offline_hours, auto_cap=args.turns)
        _show_open(session.open())
        payload: dict = {}
        for turn in range(1, args.turns + 1):
            payload = session.auto_turn()
            _show_turn(turn, payload)
        _show_standing(payload or session.snapshot_only())
        session.leave()

    conn = db.get_connection(args.db)
    try:
        _cost_report(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
