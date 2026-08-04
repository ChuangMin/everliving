"""Local web shell for the playtest.

The CLI works, but a terminal turned out to be enough friction that the one person
who has to test this didn't want to open it. This serves the same core loop —
`agent_loop.respond` and `offline.simulate_offline_period`, no duplicated logic —
behind a page you can leave in a browser tab.

Security posture, because this holds an API key and talks to a paid service:

- binds to 127.0.0.1 only, never 0.0.0.0, so nothing on the LAN can reach it
- serves exactly one embedded page; no path from the request ever reaches the
  filesystem, so there is no traversal to find
- no CORS headers at all, so another origin's page cannot call these endpoints
- state-changing work is POST only, so a stray <img src> can't spend money
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
from everliving.offline import (
    DEFAULT_SCENE,
    is_worth_simulating,
    simulate_offline_period,
    time_since_last_seen,
)

PAGE = Path(__file__).parent / "static" / "index.html"

#: One request at a time. The LLM calls are slow and SQLite has a single writer,
#: and a local playtest has exactly one player, so serialising is both correct
#: and simpler than reasoning about concurrent writes to the same agent.
_lock = threading.Lock()


class Session:
    """Everything a request needs, built once at startup."""

    def __init__(self, db_path: str, provider: str | None, offline_hours: float | None):
        self.db_path = db_path
        self.llm = make_client(provider)
        self.offline_hours = offline_hours
        self.opened = False

        conn = self._connect()
        try:
            self.agent_id = persona.seed_default_agent(conn)
            self.agent = db.get_agent(conn, self.agent_id)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = db.get_connection(self.db_path)
        db.init_schema(conn)
        return conn

    def snapshot(self, conn: sqlite3.Connection) -> dict:
        return {
            "name": self.agent["name"],
            "state": db.get_state(conn, self.agent_id),
            "threads": [t["description"] for t in db.get_open_threads(conn, self.agent_id)],
        }

    def open(self) -> dict:
        """Start a visit: catch up on the offline period, then report where things stand."""
        conn = self._connect()
        try:
            if self.offline_hours is not None:
                elapsed = timedelta(hours=self.offline_hours)
            else:
                elapsed = time_since_last_seen(conn, self.agent_id)

            offline = None
            # Only ever once per server run, so a page refresh can't re-bill it.
            if not self.opened and is_worth_simulating(elapsed):
                result = simulate_offline_period(conn, self.agent_id, self.llm, elapsed)
                offline = {
                    "narrative": result.narrative,
                    "events": result.events,
                    "state_changes": result.state_changes,
                    "open_thread": result.open_thread,
                    "scene": result.scene,
                }
            self.opened = True

            payload = self.snapshot(conn)
            payload["offline"] = offline
            payload["scene"] = offline["scene"] if offline else DEFAULT_SCENE
            return payload
        finally:
            conn.close()

    def say(self, message: str) -> dict:
        conn = self._connect()
        try:
            reply = respond(conn, self.agent_id, self.llm, message)
            payload = self.snapshot(conn)
            payload["reply"] = reply
            return payload
        finally:
            conn.close()

    def leave(self) -> dict:
        conn = self._connect()
        try:
            db.set_last_seen(conn, self.agent_id)
            return {"ok": True}
        finally:
            conn.close()


def _make_handler(session: Session):
    page_bytes = PAGE.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "everliving"
        sys_version = ""

        def log_message(self, fmt, *args):  # quieter: this runs in the player's terminal
            pass

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            # Nothing here should ever be embedded elsewhere or sniffed into a script.
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict):
            self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json")

        def do_GET(self):
            # Exact match only — no path is ever joined onto a filesystem path.
            if self.path in ("/", "/index.html"):
                self._send(200, page_bytes, "text/html; charset=utf-8")
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            routes = {"/api/open": self._open, "/api/say": self._say, "/api/leave": self._leave}
            handler = routes.get(self.path)
            if handler is None:
                self._json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length > 8000:  # a chat turn is never this big; refuse rather than buffer
                self._json(413, {"error": "訊息太長了"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                # json.loads decodes bytes before parsing, so a body that isn't UTF-8
                # fails earlier and with a different exception than malformed JSON.
                # Uncaught it killed the request thread and answered nothing at all.
                self._json(400, {"error": "bad json"})
                return

            with _lock:
                try:
                    self._json(200, handler(body))
                except (LLMAuthError, LLMUnavailable, LLMRefusal) as exc:
                    self._json(200, {"error": str(exc)})

        def _open(self, body):
            return session.open()

        def _say(self, body):
            message = str(body.get("message") or "").strip()
            if not message:
                return {"error": "說點什麼吧"}
            return session.say(message)

        def _leave(self, body):
            return session.leave()

    return Handler


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="everliving-web")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--provider", choices=PROVIDERS, default=None)
    parser.add_argument(
        "--offline-hours",
        type=float,
        default=None,
        metavar="N",
        help="假裝你已經離開 N 小時(playtest 用,跟 CLI 同一個意思)。",
    )
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    load_dotenv()

    try:
        session = Session("everliving.db", args.provider, args.offline_hours)
    except (LLMAuthError, LLMUnavailable) as exc:
        print(f"無法初始化 LLM client:{exc}")
        sys.exit(1)

    # 127.0.0.1, not 0.0.0.0 — this process holds an API key that spends real money.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _make_handler(session))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"開著了:{url}")
    print("(Ctrl-C 結束)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n先這樣。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
