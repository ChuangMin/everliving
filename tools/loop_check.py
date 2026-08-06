"""Check `LOOP.md` against the contract the four development agents work under.

The development loop (design doc section 19) splits work across four roles — 想
planner, 寫 builder, 查 auditor, 反思 reflector — and the whole thing hangs on each
role writing only into its own section of one shared board. That separation is what
stops the builder from grading its own work. Left as prose in `AGENTS.md` it is an
honour system, and an honour system read by a fresh agent every session is not a
mechanism. This is the mechanism.

Eight of the nine rules below are about shape: sections present, in order, entries
tagged. The ninth is not, and it is the one worth protecting. The auditor grades
work produced by its own team against criteria its own team wrote, so its standard
drifts downward and nothing internal to the loop can notice. The only anchor is a
human actually opening what the loop built, so the loop is required to stop when
that hasn't happened in five rounds.

    python tools/loop_check.py            # checks LOOP.md at the repo root
    python tools/loop_check.py somewhere/else/LOOP.md

Exits 1 with the problems printed, 0 when clean.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

#: In handoff order. An agent finds "its" section by scanning down, so order is
#: load-bearing, not cosmetic.
SECTIONS = [
    "退回重做",
    "排隊中",
    "進行中",
    "待驗收",
    "驗收結果",
    "反思",
    "skill 帳本",
    "輪次記錄",
]

OWNERS = ["想", "寫", "查", "反思"]

HEARTBEAT_EVERY = 5
HEARTBEAT_MARK = "人類心跳:已開"

#: Arrival has to be capped somewhere, because service is one item per round.
QUEUE_DEPTH = 3

_HEADING = re.compile(r"^##\s+(.*?)\s*$", re.M)
_OWNER = re.compile(r"\*\*現在輪到\*\*[::]\s*([^\s((]+)")
_TIER = re.compile(r"\[階([1-7])\]")


def _entries(text: str) -> dict[str, list[str]]:
    """Group each section's ``- `` bullets, keeping indented continuation lines.

    This repo writes long multi-line entries with the detail indented underneath
    (see `TASKS.md`), so an entry is a bullet plus everything indented after it —
    otherwise evidence written on the second line would read as missing.
    """
    found: dict[str, list[str]] = {}
    section: str | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            section = heading.group(1)
            found[section] = []
        elif section is None:
            continue
        elif line.startswith("- "):
            found[section].append(line)
        elif found[section] and line.strip() and line[:1] in " \t":
            found[section][-1] += "\n" + line
    return found


def _head(entry: str, width: int = 30) -> str:
    first = entry.splitlines()[0]
    return first if len(first) <= width else first[:width] + "…"


def check(text: str) -> list[str]:
    """Return a list of contract violations. Empty means the board is legal."""
    problems: list[str] = []
    order = [h for h in _HEADING.findall(text) if h in SECTIONS]

    missing = [s for s in SECTIONS if s not in order]
    if missing:
        problems.append("缺少區塊:" + "、".join(missing))
    elif order != SECTIONS:
        problems.append(
            "區塊順序錯了:應為 " + "→".join(SECTIONS) + ",實際為 " + "→".join(order)
        )

    owner = _OWNER.search(text)
    if owner is None or owner.group(1) not in OWNERS:
        got = owner.group(1) if owner else "(沒寫)"
        problems.append(
            "「現在輪到」必須是 " + "/".join(OWNERS) + f" 之一,不是「{got}」"
        )

    entries = _entries(text)

    in_progress = entries.get("進行中", [])
    if len(in_progress) > 1:
        problems.append(f"「進行中」有 {len(in_progress)} 則,builder 一次只能做一則")

    queued = entries.get("排隊中", [])
    tiers: list[int] = []
    for entry in queued:
        tier = _TIER.search(entry)
        if tier is None:
            problems.append(f"「排隊中」有一則沒標階數:{_head(entry)}")
        else:
            tiers.append(int(tier.group(1)))
        if "判準:" not in entry:
            problems.append(f"「排隊中」有一則沒寫判準:{_head(entry)}")

    if len(queued) > QUEUE_DEPTH:
        # The planner adds up to four items a round and the builder finishes one, so
        # an uncapped queue grows every single round — and it is read in full by
        # every agent that wakes up, which turns "keep the loop running" into a bill
        # that rises forever. A full queue does not mean the planner has nothing to
        # do that round; it means the round's work is re-ranking and dropping, not
        # adding.
        problems.append(
            f"「排隊中」有 {len(queued)} 則,上限是 {QUEUE_DEPTH} 則——"
            "這一棒該做的是重排跟砍,不是再加"
        )

    if queued:
        # Rounded down: with three queued items "no more than half" is one, not two.
        cap = math.floor(len(queued) / 2)
        invented = [t for t in tiers if t >= 5]
        if len(invented) > cap:
            problems.append(
                f"階 5-7 有 {len(invented)} 則,{len(queued)} 則裡最多只能 {cap} 則"
            )

    for entry in entries.get("驗收結果", []):
        if "`" not in entry:
            problems.append(
                f"「驗收結果」有一則沒附證據(要有 `檔案:行號` 或指令輸出):{_head(entry)}"
            )

    rounds = entries.get("輪次記錄", [])
    since_heartbeat = rounds
    for i, entry in enumerate(rounds):
        if HEARTBEAT_MARK in entry:
            since_heartbeat = rounds[i + 1 :]
    if len(since_heartbeat) >= HEARTBEAT_EVERY:
        problems.append(
            f"心跳逾期:已經 {len(since_heartbeat)} 輪沒有人類心跳,loop 應暫停(補丁 1)"
        )

    return problems


def main(argv: list[str]) -> int:
    default = Path(__file__).resolve().parent.parent / "LOOP.md"
    path = Path(argv[1]) if len(argv) > 1 else default
    if not path.exists():
        print(f"找不到 {path}")
        return 1
    problems = check(path.read_text(encoding="utf-8"))
    for problem in problems:
        print(f"✗ {problem}")
    if problems:
        print(f"\n{path.name}:{len(problems)} 個問題")
        return 1
    print(f"{path.name}:通過")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
