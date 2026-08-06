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

from everliving import db, logs, web
from everliving.offline import DEFAULT_SCENE, OPENING_SCENE


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


def test_autoplay_runs_a_turn_and_reports_both_sides(session):
    session.fake.reply = "在忙嗎?"
    payload = session.auto_turn()

    assert payload["visitor"] == "在忙嗎?"
    assert payload["reply"] == "在忙嗎?"       # same fake on both sides of the seat
    assert payload["auto"]["used"] == 1


def test_autoplay_stops_at_the_cap(session):
    """Each auto turn is two LLM calls and the loop drives itself, so an uncapped
    autoplay is a denial-of-wallet path aimed at the owner's own key."""
    session.auto_cap = 2
    session.auto_turn()
    session.auto_turn()

    payload = session.auto_turn()
    assert payload["auto"]["used"] == 2         # the third never ran
    assert payload["auto"]["remaining"] == 0
    assert "上限" in payload["error"]


def test_autoplay_turns_are_billed_separately_from_a_real_player(session):
    session.fake.last_usage = {"model": "m", "input_tokens": 5, "output_tokens": 3}
    session.auto_turn()

    conn = db.get_connection(session.db_path)
    purposes = sorted(r["purpose"] for r in conn.execute("SELECT purpose FROM llm_calls"))
    conn.close()
    assert purposes == ["auto_visitor", "conversation"]


def test_the_workbench_counts_nights_events_and_exchanges(session):
    """The panel leads with nights he lived through without you, because that is the
    number the whole bet rests on."""
    session.fake.reply = json.dumps(
        {"narrative": "夜裡漲潮。", "events": ["撿到一段管線", "修好了閥門"],
         "scene": "潮線"}, ensure_ascii=False
    )
    session.leave()
    _backdate(session, hours=24)
    session.open()
    session.fake.reply = "我在修水管。"
    session.say("在忙嗎?")

    ledger = session.say("還好嗎?")["ledger"]
    assert ledger["nights"] == 1
    assert ledger["events"] == 2
    assert ledger["exchanges"] == 2   # two player turns, each stored as a pair
    assert ledger["resolved"] == 0


def test_the_workbench_starts_empty_rather_than_wrong(session):
    payload = session.open()
    assert payload["ledger"] == {"nights": 0, "events": 0, "exchanges": 0, "resolved": 0}


def test_a_reply_carries_its_own_anchor_and_assets(session):
    """Assets ride alongside every beat, not just the offline ones."""
    session.fake.reply = "我在修水管。"
    payload = session.say("在嗎?")

    assert payload["event_id"] is not None
    assert payload["assets"] == []   # nothing attached yet, and that must not error


def test_the_scene_a_beat_was_drawn_in_never_reaches_the_player(session):
    """Kept in the record, kept off the screen.

    The scene each beat chose is stored on the beat so a mismatch can be looked into
    later — but `story_assets` is also what the page renders beside a line, as
    `kind · ref`. Sent unfiltered, every single turn grew two labels reading
    `scene · 工作間` and `action · 焊接`, which is debug output standing where the
    story goes. The scene already travels as its own field, so this was a duplicate
    that could only do harm.
    """
    session.fake.reply = "我把閥門纏好了。\n場景:工作間\n動作:焊接"
    payload = session.say("在嗎?")

    assert payload["assets"] == []

    conn = db.get_connection(session.db_path)
    kinds = {a["kind"] for a in db.get_assets(conn, payload["event_id"])}
    conn.close()
    assert kinds == {"scene", "action"}, "still has to be recorded — only hidden"


def test_the_offline_beat_hides_its_scene_the_same_way(session):
    """Both paths render assets, so both paths had the leak."""
    session.fake.reply = json.dumps(
        {"narrative": "我整夜都在掏沉沙格。", "events": [], "state_changes": {},
         "scene": "配電所", "action": "淹水"},
        ensure_ascii=False,
    )
    _backdate(session, 24)
    payload = session.open()

    assert payload["offline"]["assets"] == []

    conn = db.get_connection(session.db_path)
    kinds = {a["kind"] for a in db.get_assets(conn, payload["offline"]["event_id"])}
    conn.close()
    assert kinds == {"scene", "action"}


def test_a_visit_with_no_offline_period_opens_in_the_workshop(session):
    """The opening shot and the can't-draw-that fallback used to be the same constant,
    so a first visit landed on the city panorama by accident rather than by choice.
    陌洲 repairs things for a living; his workshop says who he is, and it's a person's
    own space rather than a wide view of somewhere."""
    payload = session.open()

    assert payload["scene"] == OPENING_SCENE == "工作間"


def test_the_fallback_is_still_the_city_not_the_opening_shot(session):
    """Splitting the two must not move the fallback: when the model names a place we
    can't draw, the widest always-plausible scene is the right catch-all."""
    assert DEFAULT_SCENE == "港城"
    assert OPENING_SCENE != DEFAULT_SCENE


def test_scene_defaults_when_the_model_names_a_place_we_cannot_draw(session):
    session.fake.reply = json.dumps(
        {"narrative": "夜裡漲潮。", "scene": "月球背面"}, ensure_ascii=False
    )
    session.leave()
    _backdate(session, hours=24)

    payload = session.open()

    assert payload["scene"] == DEFAULT_SCENE


def test_scene_passes_through_when_it_is_one_we_can_draw(session):
    session.fake.reply = json.dumps(
        {"narrative": "在廢料堆裡翻了一整天。", "scene": "回收場"}, ensure_ascii=False
    )
    session.leave()
    _backdate(session, hours=24)

    assert session.open()["scene"] == "回收場"


def test_a_night_can_say_what_was_happening_not_only_where(session):
    """The offline path had `scene` but no `action`, so a night spent in a blackout
    opened on a calmly lit workshop. The page reads `action` at the top level, which
    is where it has to arrive."""
    session.fake.reply = json.dumps(
        {"narrative": "整層樓的燈都滅了。", "scene": "配電所", "action": "停電"},
        ensure_ascii=False,
    )
    session.leave()
    _backdate(session, hours=24)

    payload = session.open()

    assert payload["action"] == "停電"
    assert payload["offline"]["action"] == "停電"


def test_the_payload_carries_what_you_asked_him_to_do(session):
    """A delegation is settled while the player is away, so between asking and finding
    out the workbench is the only place it exists. It has to reach the page."""
    conn = session._connect()
    try:
        db.add_delegation(conn, session.agent_id, "去回收場東邊找一個還能用的壓力閥")
    finally:
        conn.close()

    payload = session.open()

    assert payload["delegations"] == ["去回收場東邊找一個還能用的壓力閥"]


def test_a_quiet_night_reports_no_action_rather_than_omitting_it(session):
    """Null is a real value here — it's how the picture is told to go back to nothing
    in particular. Omitting the key would leave the last action stuck on screen."""
    payload = session.open()

    assert "action" in payload and payload["action"] is None


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


def test_an_unexpected_error_answers_500_and_is_written_down(server, session, tmp_path):
    """An exception we didn't anticipate used to escape into the request thread: the
    player saw a hung page and the run recorded nothing. Now it answers, and the
    reason survives in the log."""
    log_path = tmp_path / "boom.log"
    logs.setup(path=log_path, console=False)

    def explode(_message):
        raise RuntimeError("資料庫爆了")

    session.say = explode

    request = urllib.request.Request(
        server + "/api/say",
        data=json.dumps({"message": "你好"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request)
    assert excinfo.value.code == 500

    logs.reset()
    written = log_path.read_text(encoding="utf-8")
    assert "資料庫爆了" in written
    assert "RuntimeError" in written


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
