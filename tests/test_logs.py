"""A playtest that fails silently teaches nothing — these pin down that the run
leaves usable evidence behind, and that the evidence never includes a key."""

import json
import logging
import urllib.error
import urllib.request

import pytest

from everliving import logs


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    logs.reset()


def test_the_log_file_is_utf8_so_the_narrative_survives(tmp_path):
    """Windows defaults to cp950, which cannot encode 陌洲 — a crash while writing
    the log would take down whatever it was reporting on."""
    path = tmp_path / "everliving.log"
    logs.setup(path=path, console=False)
    logs.get_logger("test").info("陌洲說:潮水漲上來了")
    logs.reset()  # close the handler so the bytes are flushed to disk

    assert "陌洲說:潮水漲上來了" in path.read_text(encoding="utf-8")


def test_calling_setup_twice_does_not_double_every_line(tmp_path):
    """The CLI and the web entry both call setup; one process doing both must not
    start writing everything twice."""
    path = tmp_path / "everliving.log"
    logs.setup(path=path, console=False)
    logs.setup(path=path, console=False)
    logs.get_logger("test").info("一次就好")
    logs.reset()

    assert path.read_text(encoding="utf-8").count("一次就好") == 1


def test_debug_level_is_needed_to_record_what_the_player_typed(tmp_path):
    """Message content is the player's, not ours. Metadata at INFO is enough to
    troubleshoot; the words themselves only land in the file if asked for."""
    path = tmp_path / "everliving.log"
    logs.setup(path=path, console=False, level=logging.INFO)
    log = logs.get_logger("test")
    log.debug("player said: 我明天會回來")
    log.info("say ok")
    logs.reset()

    contents = path.read_text(encoding="utf-8")
    assert "我明天會回來" not in contents
    assert "say ok" in contents
