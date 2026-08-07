import socket

import pytest

from everliving import db


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Make a real call impossible, rather than merely unlikely.

    The `.env` fixture below covers one way a live provider gets selected. It cannot
    cover the others: `test_provider_selection.py` sets a fake `XAI_API_KEY` itself, and
    with AUTO ROUTER in place that was enough for the router to build a real Grok client
    and call out — the suite hung until it was killed (2026-08-07).

    Config-level guards will keep losing this race, because there is always one more way
    for a key to arrive. The socket is below all of them: below every SDK, every
    provider, and every route a credential can take. Blocking `connect` leaves `bind`
    and `listen` alone, so anything that wants a local server still works.

    Loopback stays open, because several tests start their own HTTP server and talk to
    it — that is the app under test, not the outside world. The one exception is the
    local model's own port, read from `OPENAI_COMPATIBLE` rather than typed in here so
    the block follows the config instead of drifting away from it. Ollama is on
    localhost and takes 5-7 minutes a call, which makes it the single best way to turn
    one stray request into a suite that looks frozen rather than failed.
    """
    real_connect = socket.socket.connect
    blocked_local = {_provider_port("ollama")}

    def refuse(self, address, *args, **kwargs):
        host, port = (address + (None,))[:2] if isinstance(address, tuple) else (address, None)
        loopback = host in ("127.0.0.1", "::1", "localhost")
        if loopback and port not in blocked_local:
            return real_connect(self, address, *args, **kwargs)
        raise RuntimeError(
            f"測試不准打真的網路連線({address})。"
            "要測 provider 請注入假的 client,不要讓它真的連出去。"
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)


def _provider_port(name: str) -> int | None:
    """The port a local provider listens on, read from the same config the app uses."""
    from urllib.parse import urlparse

    from everliving.llm import OPENAI_COMPATIBLE

    return urlparse(OPENAI_COMPATIBLE[name]["base_url"]).port


@pytest.fixture(autouse=True)
def _hide_the_developers_dotenv(monkeypatch, tmp_path):
    """Run every test somewhere `.env` doesn't exist.

    The CLI and web entry points call `load_dotenv()`, which reads `.env` from the
    current directory — so a developer's local config would otherwise decide what the
    tests exercise. This bit us for real: adding `EVERLIVING_PROVIDER=groq` to `.env`
    turned 8 passing tests into live API calls and a 200-second suite.

    Deleting the variables instead doesn't work: `load_dotenv()` runs *inside* the
    test and only skips keys already in the environment, so anything cleared
    beforehand gets set right back from the file. The file has to be out of reach.
    """
    monkeypatch.chdir(tmp_path)


class FakeLLMClient:
    """Records every call it receives and returns a scripted or canned reply."""

    def __init__(
        self,
        reply: str = "(fake reply)",
        usage: dict | None = None,
        model: str | None = None,
    ):
        # `model` mirrors the real client constructors so make_client() can build a
        # fake the same way it builds a real one.
        self.reply = reply
        self.calls: list[tuple[str, str]] = []
        self.last_usage = usage
        self.model = model

    def complete(self, system_prompt: str, user_message: str) -> str:
        self.calls.append((system_prompt, user_message))
        return self.reply


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def fake_llm():
    return FakeLLMClient()
