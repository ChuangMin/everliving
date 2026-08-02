import os

import pytest

from everliving.config import load_dotenv

MANAGED_KEYS = ("ANTHROPIC_API_KEY", "EVERLIVING_MODEL")


@pytest.fixture(autouse=True)
def restore_env():
    """load_dotenv writes to os.environ directly, so monkeypatch can't track it.

    Without this, a value set here leaks into whatever test runs next.
    """
    saved = {key: os.environ.get(key) for key in MANAGED_KEYS}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_loads_key_value_pairs(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    load_dotenv(env_file)

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"


def test_real_environment_wins(tmp_path, monkeypatch):
    """An exported key is the more deliberate choice — .env must not override it."""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-environment")

    load_dotenv(env_file)

    assert os.environ["ANTHROPIC_API_KEY"] == "from-environment"


def test_strips_quotes_and_whitespace(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('  EVERLIVING_MODEL = "claude-sonnet-5"  \n', encoding="utf-8")
    monkeypatch.delenv("EVERLIVING_MODEL", raising=False)

    load_dotenv(env_file)

    assert os.environ["EVERLIVING_MODEL"] == "claude-sonnet-5"


def test_ignores_comments_and_blank_lines(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n\nEVERLIVING_MODEL=claude-haiku-4-5\n", encoding="utf-8"
    )
    monkeypatch.delenv("EVERLIVING_MODEL", raising=False)

    load_dotenv(env_file)

    assert os.environ["EVERLIVING_MODEL"] == "claude-haiku-4-5"


def test_missing_file_is_not_an_error(tmp_path):
    load_dotenv(tmp_path / "does-not-exist.env")  # must not raise
