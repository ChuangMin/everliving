"""Interactive CLI for Milestone 0. Run with: python -m everliving.cli"""

from __future__ import annotations

import sys

from everliving import db, persona
from everliving.agent_loop import respond

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

    print(f"你正在和 {agent['name']} 對話。輸入 exit 離開。")
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

    conn.close()


if __name__ == "__main__":
    main()
