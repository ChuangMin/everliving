"""The web shell exists so the playtest can actually happen, so it needs to hold up.

Two layers here: Session (the logic) directly, and one real request over a socket,
because "the tests pass but the command doesn't run" has already happened on this
project more than once.
"""

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest
from conftest import FakeLLMClient

from everliving import db, web


@pytest.fixture
def session(tmp_path, monkeypatch):
    fake = FakeLLMClient(reply="我在修水管。")
    monkeypatch.setattr(web, "make_client", lambda provider: fake)
    s = web.Session(str(tmp_path / "test.db"), None, None)
    s.fake = fake
    return s


def _backdate(session, hours):
    conn = db.get_connection(session.db_path)
    when = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    db.set_last_seen(conn, session.agent_id, when)
    conn.close()


def test_first_visit_has_no_offline_period_and_costs_nothing(session):
    payload = session.open()

    assert payload["offline"] is None
    assert payload["name"] == "陌洲"
    assert session.fake.calls == []


def test_returning_after_a_real_absence_produces_a_narrative(session):
    session.leave()
    _backdate(session, hours=24)

    payload = session.open()

    assert payload["offline"]["narrative"]
    assert len(session.fake.calls) == 1


def test_relaunching_immediately_does_not_bill_a_call(session):
    session.leave()  # last seen: just now

    payload = session.open()

    assert payload["offline"] is None
    assert session.fake.calls == []


def test_open_only_simulates_once_so_a_refresh_is_free(session):
    session.leave()
    _backdate(session, hours=24)

    first = session.open()
    second = session.open()

    assert first["offline"] is not None
    assert second["offline"] is None, "a page refresh must not re-bill the offline call"
    assert len(session.fake.calls) == 1


def test_say_returns_the_reply_and_the_current_state(session):
    session.open()

    payload = session.say("你在忙什麼?")

    assert payload["reply"] == "我在修水管。"
    assert "state" in payload and "threads" in payload


def test_scene_defaults_when_the_model_names_a_place_we_cannot_draw(session):
    session.fake.reply = json.dumps(
        {"narrative": "夜裡漲潮。", "scene": "月球背面"}, ensure_ascii=False
    )
    session.leave()
    _backdate(session, hours=24)

    payload = session.open()

    assert payload["scene"] == web.DEFAULT_SCENE


def test_scene_passes_through_when_it_is_one_we_can_draw(session):
    session.fake.reply = json.dumps(
        {"narrative": "在廢料堆裡翻了一整天。", "scene": "回收場"}, ensure_ascii=False
    )
    session.leave()
    _backdate(session, hours=24)

    assert session.open()["scene"] == "回收場"


# --- one real trip over a socket ---------------------------------------------


@pytest.fixture
def server(session):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(session))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _post(base, path, payload=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def test_the_page_is_actually_served(server):
    with urllib.request.urlopen(server + "/") as response:
        body = response.read().decode()
    assert response.status == 200
    assert "<title>陌洲</title>" in body


def test_talking_over_http(server):
    _post(server, "/api/open")

    assert _post(server, "/api/say", {"message": "你好"})["reply"] == "我在修水管。"


def test_empty_message_is_rejected_without_calling_the_model(server, session):
    _post(server, "/api/open")

    assert "error" in _post(server, "/api/say", {"message": "   "})
    assert session.fake.calls == []


def test_unknown_paths_are_not_served(server):
    for path in ("/etc/passwd", "/../pyproject.toml", "/static/index.html"):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(server + path)
        assert excinfo.value.code == 404


def test_oversized_bodies_are_refused_before_reaching_the_model(server, session):
    request = urllib.request.Request(
        server + "/api/say",
        data=json.dumps({"message": "字" * 9000}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request)

    assert excinfo.value.code == 413
    assert session.fake.calls == []


def test_a_body_that_is_not_utf8_is_a_400_not_a_crash(server, session):
    """`json.loads` on bytes decodes first, so invalid UTF-8 raises UnicodeDecodeError
    — not the JSONDecodeError the handler was catching. That killed the request thread
    with a traceback and answered nothing at all."""
    request = urllib.request.Request(
        server + "/api/say",
        data="{'message': '你好'}".encode("big5"),  # any non-UTF-8 encoding
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request)

    assert excinfo.value.code == 400
    assert session.fake.calls == []
