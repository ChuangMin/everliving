"""Interactive CLI for Milestone 0. Run with: python -m everliving.cli"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from everliving import db, persona
from everliving.agent_loop import respond
from everliving.offline import generate_offline_narrative, time_since_last_seen

DB_PATH = "everliving.db"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="everliving")
    parser.add_argument(
        "--offline-hours",
        type=float,
        default=None,
        metavar="N",
        help=(
            "假裝你已經離開 N 小時,直接生成該期間的敘事。"
            "這樣不用真的等一天就能測試核心體驗(H-1 playtest 用)。"
        ),
    )
    parser.add_argument(
        "--cost-report",
        action="store_true",
        help="印出每日 token 用量統計後離開,不進入對話。",
    )
    return parser.parse_args(argv)


def _print_cost_report(conn) -> None:
    rows = db.token_usage_by_day(conn)
    if not rows:
        print("還沒有任何 LLM 呼叫記錄。")
        return
    print(f"{'日期':<12}{'模型':<28}{'次數':>6}{'輸入 token':>12}{'輸出 token':>12}")
    for row in rows:
        print(
            f"{row['day']:<12}{row['model']:<28}{row['calls']:>6}"
            f"{row['input_tokens']:>12}{row['output_tokens']:>12}"
        )
    print("\n(換算成金額請自行乘上當前各模型單價——單價會變,所以這裡只存 token 這個不會過期的事實)")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    conn = db.get_connection(DB_PATH)
    db.init_schema(conn)

    if args.cost_report:
        _print_cost_report(conn)
        conn.close()
        return

    agent_id = persona.seed_default_agent(conn)
    agent = db.get_agent(conn, agent_id)

    try:
        from everliving.llm import AnthropicLLMClient

        llm = AnthropicLLMClient()
    except Exception as exc:  # missing package or ANTHROPIC_API_KEY
        print(f"無法初始化 LLM client:{exc}")
        print("設定 ANTHROPIC_API_KEY 並安裝 `anthropic` 套件後再試一次(見 README)。")
        sys.exit(1)

    if args.offline_hours is not None:
        elapsed = timedelta(hours=args.offline_hours)
    else:
        elapsed = time_since_last_seen(conn, agent_id)

    if elapsed is not None:
        narrative = generate_offline_narrative(conn, agent_id, llm, elapsed)
        print(f"\n({agent['name']} 這段時間發生的事)")
        print(narrative)
        print()

    print(f"你正在和 {agent['name']} 對話。輸入 exit 離開。")
    try:
        while True:
            try:
                player_message = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if player_message.lower() in {"exit", "quit"}:
                break
            if not player_message:
                continue
            reply = respond(conn, agent_id, llm, player_message)
            print(f"{agent['name']}: {reply}")
    finally:
        db.set_last_seen(conn, agent_id)
        conn.close()


if __name__ == "__main__":
    main()
