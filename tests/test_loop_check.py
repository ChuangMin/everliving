"""The contract in AGENTS.md is only real if something checks it.

Every rule here mirrors a line the four development agents are supposed to follow
(design doc section 19). Writing those rules down is cheap; the project has already
been burned once by a rule that was written and simply never took effect — the
`prefers-reduced-motion` handling passed review, shipped, and was doing nothing at
all until someone counted the elements in a real browser. So the rules that *can*
be machine-checked are checked here, and the ones that can't are called out as such
in the task list rather than pretended into a test.
"""

import io
import sys

from tools.loop_check import check, main

SKELETON = """# LOOP.md — 想 → 寫 → 查

**現在輪到**:想(planner)   **上一棒**:—
**本輪次**:0   **距離下次反思**:3 輪   **距離人類心跳**:5 輪

## 退回重做

## 排隊中

## 進行中

## 待驗收

## 驗收結果

## 反思

## skill 帳本

## 輪次記錄
"""


def fill(section: str, body: str) -> str:
    """Put `body` under `section` in a copy of the empty skeleton."""
    return SKELETON.replace(f"## {section}\n", f"## {section}\n{body}")


def test_empty_skeleton_passes():
    # The file a fresh loop starts from has to be legal, or the first agent to wake
    # up hits a wall of complaints about a board nobody has written on yet.
    assert check(SKELETON) == []


def test_missing_section_reported():
    text = SKELETON.replace("## skill 帳本\n", "")
    assert any("skill 帳本" in m for m in check(text))


def test_sections_out_of_order_reported():
    # Handing off works by position: an agent is told to write "its own section" and
    # finds it by scanning down. Two sections swapped means someone writes into the
    # wrong one while every section is still technically present.
    text = SKELETON.replace("## 排隊中\n\n## 進行中\n", "## 進行中\n\n## 排隊中\n")
    assert any("順序" in m for m in check(text))


def test_invalid_turn_owner_reported():
    text = SKELETON.replace("**現在輪到**:想(planner)", "**現在輪到**:大家")
    assert any("現在輪到" in m for m in check(text))


def test_in_progress_at_most_one():
    text = fill("進行中", "- 甲任務\n- 乙任務\n")
    assert any("進行中" in m for m in check(text))


def test_queued_item_needs_tier_tag():
    text = fill("排隊中", "- 修好那個東西 判準:測試通過\n")
    assert any("階數" in m for m in check(text))


def test_queued_item_needs_criteria():
    # Without a stated bar, the auditor has nothing to hold the work against and
    # "done" quietly becomes whatever the builder felt like stopping at.
    text = fill("排隊中", "- [階1] 修好那個東西\n")
    assert any("判準" in m for m in check(text))


def after(baton: str, section: str, body: str) -> str:
    """A board where `baton` was the last role to act.

    The quota rule is about what the planner *added*, so which baton just finished is
    load-bearing for it — see `test_the_quota_does_not_fire_at_a_queue_the_builder_drained`.
    """
    return fill(section, body).replace("**上一棒**:—", f"**上一棒**:{baton}")


def test_tier_5_to_7_quota():
    # Stated as 「想 just handed off」 because that is the only moment the rule is about:
    # the planner put three in and two of them are its own invention.
    text = after("想", "排隊中", "- [階5] 甲 判準:x\n- [階6] 乙 判準:x\n- [階1] 丙 判準:x\n")
    assert any("階 5-7" in m for m in check(text))


def test_tier_5_to_7_quota_allows_half():
    text = after("想", "排隊中", "- [階5] 甲 判準:x\n- [階1] 乙 判準:x\n")
    assert check(text) == []


def test_the_quota_does_not_fire_at_a_queue_the_builder_drained():
    """The false alarm this rule has been raising for twenty rounds.

    The cap is on what the planner adds. But it was measured against whatever happened
    to be left in the queue — and the builder takes one item per round, so a queue that
    was legal when it was written becomes illegal purely by being worked on. Rounds
    6, 7, 10, 22, 26 and 28 all sat on a red light that no one's decision had caused.

    A checker that cries wolf every other round teaches everyone to ignore it, and
    `AGENTS.md` says so out loud: 紅燈太便宜就會被無視.
    """
    text = after("寫", "排隊中", "- [階6] 剩下的最後一則 判準:x\n")
    assert check(text) == []


def test_a_missing_last_baton_is_caught_rather_than_quietly_excusing_the_quota():
    """The cost of making the quota conditional, paid for out in the open.

    Tying it to 「上一棒是想」 means a board that forgets to say who just acted escapes
    the check entirely — the old rule failed loud and wrong, and this one could fail
    quiet and wrong, which is worse. So the field itself is validated: garbage or
    missing is a violation on its own, and the silence becomes unreachable by accident.

    It does not stop a planner that deliberately writes the wrong baton. Nothing here
    can — the whole board is self-reported — but that is a lie in the record, not a
    gap in the checker.
    """
    text = fill("排隊中", "- [階6] 甲 判準:x\n").replace("**上一棒**:—", "**上一棒**:")
    assert any("上一棒" in m for m in check(text))


def test_the_opening_dash_is_still_a_legal_last_baton():
    """Round one has no previous baton and must not read as a broken board."""
    assert check(SKELETON) == []


def test_the_quota_still_fires_the_moment_the_planner_hands_off():
    """The fix must not amount to deleting the rule.

    Same single tier-6 item, but with the planner as the last baton — now it *is*
    someone's decision, and one invented item out of one is over the cap.
    """
    text = after("想", "排隊中", "- [階6] 我自己想出來的 判準:x\n")
    assert any("階 5-7" in m for m in check(text))


def test_queue_depth_capped():
    # The planner adds up to four a round, the builder finishes one. Uncapped, the
    # board grows every round forever — and every agent reads it whole on waking, so
    # the cost of running the loop climbs with no ceiling. This is the rule that
    # keeps LOOP.md a fixed-size file instead of a second PROGRESS.md.
    text = fill(
        "排隊中",
        "".join(f"- [階1] 第 {i} 則 判準:x\n" for i in range(1, 5)),
    )
    assert any("上限" in m for m in check(text))


def test_verdict_needs_evidence():
    text = fill("驗收結果", "- 退回,感覺沒做完\n")
    assert any("證據" in m for m in check(text))


def test_verdict_evidence_may_sit_on_a_continuation_line():
    # This repo writes multi-line entries with indented continuations (see TASKS.md),
    # so evidence on the second line still counts as evidence.
    text = fill("驗收結果", "- 退回:離線敘事沒有落在狀態上\n      `src/everliving/offline.py:88`\n")
    assert check(text) == []


def test_main_survives_a_console_that_cannot_encode_its_output(tmp_path, monkeypatch):
    # The checker crashed the first time it had a violation to report: it printed `✗`,
    # the console encoding couldn't hold that character, and the traceback exited 1 —
    # the same code a clean run's failure would use, so nothing looked wrong from
    # outside while every message it wanted to give was lost. Five rounds ran that
    # way. An ascii stream is a harsher console than the real one, and enough to pin it.
    board = tmp_path / "LOOP.md"
    board.write_text(fill("進行中", "- 甲\n- 乙\n"), encoding="utf-8")
    narrow = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
    monkeypatch.setattr(sys, "stdout", narrow)

    assert main(["loop_check.py", str(board)]) == 1


def test_heartbeat_overdue_blocks_loop():
    # The most important rule in the file. The other eight catch formatting; this one
    # catches the loop running happily for weeks with no human ever opening the thing
    # it produces — which is the failure the auditor cannot catch, because the auditor
    # is grading its own team's homework.
    text = fill("輪次記錄", "".join(f"- 第 {i} 輪\n" for i in range(1, 6)))
    assert any("心跳" in m for m in check(text))


def test_heartbeat_resets_when_human_opened_it():
    text = fill(
        "輪次記錄",
        "- 第 1 輪\n- 第 2 輪 人類心跳:已開\n- 第 3 輪\n- 第 4 輪\n",
    )
    assert check(text) == []
