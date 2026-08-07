"""Did anyone come back? — the number 里程碑 0 is graded on, and nobody could read it.

H-1 asks 「一個人隔天想不想再打開」. It has never been answered, and until `visits` existed
it could not be: `player_state` kept one row that every visit overwrote, so two evenings
and twenty looked identical.

人類 2026-08-07 set the goal 「以目標變成最多人玩的遊戲」 and asked, in effect, what the
measurable version of that is. This does not answer that question — that is his to
answer — but it puts the candidates on screen next to real numbers so the answer can be
pointed at instead of imagined.

    python tools/retention.py                 # everliving.db
    python tools/retention.py play.db
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from everliving import db  # noqa: E402


def _day(stamp: str) -> str:
    return stamp[:10]


def summarise(conn, agent_id: int) -> dict:
    """Everything the record can honestly say about coming back.

    Counts days rather than visits wherever the question is about habit: opening it
    twice in one evening is enthusiasm, not retention, and conflating them would let a
    single long night look like a week of them.
    """
    visits = [row["visited_at"] for row in db.get_visits(conn, agent_id)]
    days = sorted({_day(v) for v in visits})

    gaps: list[int] = []
    for earlier, later in zip(days, days[1:]):
        gaps.append(
            (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).days
        )

    nights = conn.execute(
        "SELECT content FROM memory_events WHERE agent_id = ? AND kind = 'offline_narrative'",
        (agent_id,),
    ).fetchall()
    threads = conn.execute(
        "SELECT status, COUNT(*) AS n FROM open_threads WHERE agent_id = ? GROUP BY status",
        (agent_id,),
    ).fetchall()
    errands = conn.execute(
        "SELECT status, COUNT(*) AS n FROM delegations WHERE agent_id = ? GROUP BY status",
        (agent_id,),
    ).fetchall()
    models = conn.execute(
        "SELECT model, COUNT(*) AS n FROM llm_calls WHERE agent_id = ? GROUP BY model",
        (agent_id,),
    ).fetchall()

    return {
        "visits": len(visits),
        "days": days,
        "gaps": gaps,
        "came_back_next_day": sum(1 for g in gaps if g == 1),
        "longest_gap": max(gaps) if gaps else None,
        "nights_written": sum(1 for n in nights if n["content"].strip()),
        "nights_blank": sum(1 for n in nights if not n["content"].strip()),
        "threads": {row["status"]: row["n"] for row in threads},
        "errands": {row["status"]: row["n"] for row in errands},
        "models": {row["model"]: row["n"] for row in models},
    }


def render(s: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 66)
    add("H-1:他隔天有沒有再打開?")
    add("=" * 66)

    if not s["days"]:
        add("")
        add("  還沒有任何一次來訪被記下來。")
        add("  注意:`visits` 是 2026-08-07 才加的,在那之前的來訪**沒有被記錄過**,")
        add("  不是「他沒來」。空的答案是真的,像樣的答案會是假的。")
        return "\n".join(lines)

    add("")
    add(f"  打開過 {s['visits']} 次,分佈在 {len(s['days'])} 個不同的日子")
    add(f"  第一次 {s['days'][0]},最後一次 {s['days'][-1]}")
    add("")
    add(f"  ★ 隔天又回來:{s['came_back_next_day']} 次   ← 這就是 H-1 的答案")
    if s["longest_gap"] is not None:
        add(f"    最長中斷 {s['longest_gap']} 天;每次間隔:{s['gaps']}")
    if s["came_back_next_day"] == 0:
        add("    **H-1 還沒過。** 沒有任何一次是隔天回來的。")

    add("")
    add("-" * 66)
    add("他回來時讀到了什麼")
    add("-" * 66)
    add(f"  寫成的夜晚 {s['nights_written']} 個,空白的 {s['nights_blank']} 個")
    if s["nights_blank"]:
        add("    空白的夜晚是 2026-08-07 之後才擋掉的,舊的留著當紀錄")
    add(f"  懸念:{s['threads'] or '(沒有)'}")
    add(f"  委託:{s['errands'] or '(沒有)'}")
    add(f"  誰寫的:{s['models'] or '(沒有)'}")

    add("")
    add("-" * 66)
    add("「最多人玩」要量哪一個?——這幾個都是候選,人類自己指")
    add("-" * 66)
    add("  a) 隔天回訪率      —— 跟 H-1 同一個東西,只是換成比例。最保守")
    add("  b) 連續回來的天數  —— 量的是習慣,不是好奇心")
    add("  c) 一個人總共幾天  —— 量的是這個世界能撐多久才被看完")
    add("  d) 有沒有人講給別人聽 —— 唯一跟「最多人」直接有關的,而且**現在完全沒有在記**")
    add("")
    add("  **agent 不替你選。** 但 (d) 值得先講一句:前三個都只量得到「這一個人」,")
    add("  而你的目標寫的是「最多人」——那條線現在一筆資料都沒有。")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "everliving.db"
    if not Path(path).exists():
        print(f"找不到 {path}")
        return 1

    conn = db.get_connection(path)
    db.init_schema(conn)
    try:
        agents = conn.execute("SELECT id, name FROM agents ORDER BY id").fetchall()
        if not agents:
            print(f"{path} 裡沒有任何 agent")
            return 1
        for agent in agents:
            print(f"\n### {agent['name']}(agent {agent['id']})— {path}")
            print(render(summarise(conn, agent["id"])))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv))
