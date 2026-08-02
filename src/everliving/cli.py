"""Interactive CLI for Milestone 0. Run with: python -m everliving.cli"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from everliving import db, persona
from everliving.agent_loop import respond
from everliving.config import load_dotenv
from everliving.llm import (
    PROVIDERS,
    LLMAuthError,
    LLMRefusal,
    LLMUnavailable,
    make_client,
)
from everliving.offline import simulate_offline_period, time_since_last_seen

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
        "--provider",
        choices=PROVIDERS,
        default=None,
        help="用哪家的模型(預設 anthropic;也可用 EVERLIVING_PROVIDER 設定)。",
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


def _exit_unavailable(exc) -> None:
    """No credit, rate limited, or an outage — rewording won't help, so stop."""
    print(f"\n沒辦法呼叫模型:{exc}")
    print("(額度不足的話,到 console.anthropic.com 的 Plans & Billing 儲值。)")
    sys.exit(1)


def _exit_no_credentials(exc) -> None:
    """Credentials only fail on the first API call, so this can fire mid-session.

    Deliberately does not close the connection — the caller's `finally` owns cleanup,
    and closing here makes that block write to a closed database.
    """
    print("\n找不到可用的 API 憑證,沒辦法呼叫模型。")
    print("Anthropic:設定 ANTHROPIC_API_KEY,或用 `ant auth login` 登入。")
    print("Grok:設定 XAI_API_KEY,並加上 --provider grok(見 README)。")
    print(f"(原始訊息:{exc})")
    sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    load_dotenv()  # before the client resolves credentials

    conn = db.get_connection(DB_PATH)
    db.init_schema(conn)

    if args.cost_report:
        _print_cost_report(conn)
        conn.close()
        return

    agent_id = persona.seed_default_agent(conn)
    agent = db.get_agent(conn, agent_id)

    try:
        llm = make_client(args.provider)
    except LLMAuthError as exc:
        _exit_no_credentials(exc)
    except Exception as exc:  # the provider's package isn't installed
        print(f"無法初始化 LLM client:{exc}")
        print("先跑 `pip install -r requirements.txt`(見 README)。")
        sys.exit(1)

    if args.offline_hours is not None:
        elapsed = timedelta(hours=args.offline_hours)
    else:
        elapsed = time_since_last_seen(conn, agent_id)

    if elapsed is not None:
        try:
            result = simulate_offline_period(conn, agent_id, llm, elapsed)
        except LLMAuthError as exc:
            _exit_no_credentials(exc)
        except LLMUnavailable as exc:
            _exit_unavailable(exc)
        except LLMRefusal as exc:
            # Don't let this abort startup — the conversation loop is still usable.
            print(f"\n(這次沒能生成離線敘事:{exc})\n")
        else:
            print(f"\n({agent['name']} 這段時間發生的事)")
            print(result.narrative)
            if result.state_changes:
                print("\n有些事情變了:")
                for key, value in result.state_changes.items():
                    print(f"  · {key}:{value}")
            if result.open_thread:
                print(f"\n[ 有件事在等你 ] {result.open_thread}")
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
            try:
                reply = respond(conn, agent_id, llm, player_message)
            except LLMAuthError as exc:
                _exit_no_credentials(exc)
            except LLMUnavailable as exc:
                _exit_unavailable(exc)
            except LLMRefusal as exc:
                print(f"({exc} 換個說法再試一次。)")
                continue
            print(f"{agent['name']}: {reply}")
    finally:
        db.set_last_seen(conn, agent_id)
        conn.close()


if __name__ == "__main__":
    main()
