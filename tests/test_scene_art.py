"""Dropping a picture into `static/scenes/` has to be the whole of adding art.

人類 2026-08-08 looked at the drawn scenes and said 「看不懂你的美術以及視覺畫面 太不行了」,
then chose image assets over redrawing. Nobody here can draw, so the deliverable is the
pipeline: the moment a file exists it is on screen, and while none exists the page keeps
drawing what it draws today rather than showing a broken image.

The server resolves which file to use, not the page. A page that guessed would have to
probe URLs and read 404s as "no art", which is untestable from a stub DOM and puts a
failed request in the player's console on every visit.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.parse import quote

import pytest
from conftest import FakeLLMClient

from everliving import web


@pytest.fixture
def gallery(tmp_path, monkeypatch):
    """A scenes folder of our own, so a real one appearing later can't sway a test."""
    folder = tmp_path / "scenes"
    folder.mkdir()
    monkeypatch.setattr(web, "SCENES_DIR", folder)
    return folder


@pytest.fixture
def session(tmp_path, monkeypatch, gallery):
    fake = FakeLLMClient(reply="我在修水管。")
    monkeypatch.setattr(web, "make_client", lambda provider: fake)
    s = web.Session(str(tmp_path / "test.db"), None, None)
    s.fake = fake
    return s


def test_no_art_means_the_page_keeps_drawing_it_itself(session):
    """The fallback is the product's current behaviour, not a placeholder box."""
    payload = session.open()

    assert payload["scene_image"] is None


def test_a_scene_with_a_picture_gets_its_url(session, gallery):
    (gallery / "工作間.webp").write_bytes(b"not really a webp")

    payload = session.open()

    assert payload["scene"] == "工作間"
    assert payload["scene_image"] == "/scenes/工作間.webp"


def test_the_picture_for_this_stage_beats_the_general_one(session, gallery):
    """`-s2` next to a plain file is how the world clock reaches the art at all.

    Without it a static image would freeze the one thing that is supposed to move,
    which is the complaint 世界時鐘 was built to answer in the first place.

    The place is read back off the payload rather than named here: at stage 2 the
    opening is 回收場, not 工作間 (第 22 輪), and a test that spelled the place out
    would be quietly asserting its own guess about a decision the product makes.
    """
    _age(session, days=20)  # stage 2
    scene = session.open()["scene"]
    (gallery / f"{scene}.webp").write_bytes(b"x")
    (gallery / f"{scene}-s2.webp").write_bytes(b"x")

    payload = session.open()

    assert payload["world"]["stage"] == 2
    assert payload["scene_image"] == f"/scenes/{scene}-s2.webp"


def test_a_picture_for_a_different_stage_is_left_alone(session, gallery):
    """Half a set must degrade to the general picture, not to someone else's stage."""
    _age(session, days=20)  # stage 2, and there will be no -s2
    scene = session.open()["scene"]
    (gallery / f"{scene}.webp").write_bytes(b"x")
    (gallery / f"{scene}-s4.webp").write_bytes(b"x")

    assert session.open()["scene_image"] == f"/scenes/{scene}.webp"


def test_a_reply_that_names_no_place_leaves_the_picture_alone(session, gallery):
    """He does not tag a scene on every line, and those turns must not blank the art.

    Sending `scene_image: null` here would wipe the picture on every sentence he said
    without naming where he was — the art would flicker away mid-conversation and
    nothing in the payload would look wrong. So the two keys travel together or not
    at all, and the page keeps the place it is already showing.
    """
    (gallery / "工作間.webp").write_bytes(b"x")
    assert session.open()["scene_image"] == "/scenes/工作間.webp"

    reply = session.say("你還好嗎?")  # the fake reply carries no 場景: tag

    assert "scene" not in reply
    assert "scene_image" not in reply


def test_a_reply_that_does_name_a_place_brings_its_picture(session, gallery):
    """The other half of the pair: tag a scene and the art follows it."""
    (gallery / "配電所.webp").write_bytes(b"x")
    session.open()
    session.fake.reply = "這裡又跳電了。\n場景:配電所"  # the tag is anchored to the end

    reply = session.say("你在哪?")

    assert reply["scene"] == "配電所"
    assert reply["scene_image"] == "/scenes/配電所.webp"


def test_a_folder_with_junk_in_it_offers_only_pictures(session, gallery):
    """Whatever else lands in that folder — notes, prompts, `.DS_Store` — is not art."""
    (gallery / "工作間.txt").write_bytes(b"my prompt notes")
    (gallery / "README.md").write_bytes(b"how to add art")

    assert session.open()["scene_image"] is None


def _age(session, days):
    from datetime import datetime, timedelta, timezone

    from everliving import db, world

    conn = db.get_connection(session.db_path)
    world.pressure(conn)
    started = (datetime.now(timezone.utc) - timedelta(days=days, hours=1)).isoformat()
    conn.execute("UPDATE world SET started_at = ? WHERE id = 1", (started,))
    conn.commit()
    conn.close()


# ---- over a real socket, because the routing comment claims a security property ----


@pytest.fixture
def server(session, gallery):
    (gallery / "工作間.webp").write_bytes(b"RIFF....WEBPVP8 fake")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(session))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_the_picture_is_actually_served(server):
    # Percent-encoded, because that is what a browser sends for a 中文 filename and
    # `urllib` refuses to send anything else.
    with urllib.request.urlopen(f"{server}{quote('/scenes/工作間.webp')}") as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/webp"
        assert r.read() == b"RIFF....WEBPVP8 fake"


@pytest.mark.parametrize(
    "attack",
    [
        "/scenes/../index.html",
        "/scenes/..%2findex.html",
        "/scenes/%2e%2e/index.html",
        "/scenes/subdir/%E5%B7%A5%E4%BD%9C%E9%96%93.webp",
        "/scenes/",
    ],
)
def test_nothing_climbs_out_of_the_scenes_folder(server, attack):
    """`do_GET` carried a comment promising no request path is ever joined onto a
    filesystem path. Serving files could have quietly retired that promise, so the
    lookup is a dict built from the directory listing and the URL is only ever a key.
    """
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(f"{server}{attack}")
    assert caught.value.code == 404


def test_a_new_picture_is_picked_up_without_a_restart(server, gallery):
    """They will be generating these one at a time and looking after each one.

    A map built once at startup would mean a restart per attempt, which is enough
    friction to make nobody iterate.
    """
    with urllib.request.urlopen(f"{server}/api/open", data=b"{}") as r:
        first = json.load(r)
    assert first["scene_image"] == "/scenes/工作間.webp"

    (gallery / "工作間-s0.webp").write_bytes(b"newer")

    with urllib.request.urlopen(f"{server}/api/open", data=b"{}") as r:
        assert json.load(r)["scene_image"] == "/scenes/工作間-s0.webp"
