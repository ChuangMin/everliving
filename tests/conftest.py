import pytest

from everliving import db


class FakeLLMClient:
    """Records every call it receives and returns a scripted or canned reply."""

    def __init__(self, reply: str = "(fake reply)", usage: dict | None = None):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []
        self.last_usage = usage

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
