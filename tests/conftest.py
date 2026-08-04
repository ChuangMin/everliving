import pytest

from everliving import db


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
