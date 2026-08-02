"""Interactive CLI for Milestone 0. Run with: python -m everliving.cli"""

from __future__ import annotations

import sys

from everliving import db, persona
from everliving.agent_loop import respond
from everliving.offline import generate_offline_narrative, time_since_last_seen

DB_PATH = "everliving.db"


def main() -> None:
    conn = db.get_connection(DB_PATH)
    db.init_schema(conn)
    agent_id = persona.seed_default_agent(conn)
    agent = db.get_agent(conn, agent_id)

    try:
        from everliving.llm import AnthropicLLMClient

        llm = AnthropicLLMClient()
    except Exception as exc:  # missing package or ANTHROPIC_API_KEY
        print(f"無法初始化 LLM client:{exc}")
        print("設定 ANTHROPIC_API_KEY 並安裝 `anthropic` 套件後再試一次(見 README)。")
        sys.exit(1)

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
