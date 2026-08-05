import pytest

from everliving import db, persona
from everliving.agent_loop import build_system_prompt, respond, split_scene_tag


def test_build_system_prompt_includes_name_and_traits():
    agent = {"name": "陌洲", "background": "港城技師", "personality": "務實寡言"}
    prompt = build_system_prompt(agent)
    assert "陌洲" in prompt
    assert "港城技師" in prompt
    assert "務實寡言" in prompt


def test_respond_returns_llm_reply_and_records_memory(conn, fake_llm):
    fake_llm.reply = "我在修水管,晚點再說。"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "你在忙什麼?")

    assert turn.reply == "我在修水管,晚點再說。"
    events = db.get_recent_memory(conn, agent_id)
    contents = [event["content"] for event in events]
    assert "玩家說:你在忙什麼?" in contents
    assert "我回答:我在修水管,晚點再說。" in contents


def test_respond_includes_recent_memory_in_prompt(conn, fake_llm):
    agent_id = persona.seed_default_agent(conn)
    db.add_memory_event(conn, agent_id, kind="raw", content="昨天修好了發電機")

    respond(conn, agent_id, fake_llm, "發電機還好嗎?")

    assert len(fake_llm.calls) == 1
    _, user_message = fake_llm.calls[0]
    assert "昨天修好了發電機" in user_message
    assert "發電機還好嗎?" in user_message


def test_respond_unknown_agent_raises(conn, fake_llm):
    with pytest.raises(ValueError):
        respond(conn, 999, fake_llm, "hi")


# --- the scene has to follow what he just said ------------------------------


def test_a_reply_can_move_the_scene(conn, fake_llm):
    """The picture and the words were drifting apart: 陌洲 would talk about the work
    lamp and the bench while the background sat on wherever the last offline period
    left it. He tags where he is, so the scene follows the conversation."""
    fake_llm.reply = "我把防潮簾拉緊了。\n場景:工作間"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "晚安")

    assert turn.scene == "工作間"
    assert turn.reply == "我把防潮簾拉緊了。"  # the tag is never shown to the player


def test_a_scene_we_cannot_draw_is_ignored_rather_than_shown(conn, fake_llm):
    fake_llm.reply = "我在月球背面。\n場景:月球背面"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "你在哪?")

    assert turn.scene is None  # None means "don't move the camera"
    assert turn.reply == "我在月球背面。"


def test_a_reply_without_a_tag_leaves_the_scene_alone(conn, fake_llm):
    """Degrading safely matters more than tagging every turn: a missed tag should
    hold the picture still, never blank it or reset it to somewhere wrong."""
    fake_llm.reply = "我在修水管。"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "在忙?")

    assert turn.scene is None
    assert turn.reply == "我在修水管。"


def test_the_memory_stores_the_reply_without_the_tag(conn, fake_llm):
    """The tag is stage direction, not something 陌洲 said. Letting it into memory
    would feed it back as dialogue on the next turn."""
    fake_llm.reply = "水退了。\n場景:潮線"
    agent_id = persona.seed_default_agent(conn)

    respond(conn, agent_id, fake_llm, "外面怎樣?")

    contents = [e["content"] for e in db.get_recent_memory(conn, agent_id)]
    assert "我回答:水退了。" in contents
    assert not any("場景" in c for c in contents)


def test_what_is_happening_is_tagged_separately_from_where(conn, fake_llm):
    """The place tag couldn't fix the mismatch the player saw: he described a welding
    arc and got a generic workshop, because the workshop was already the right place.
    What was missing was what he was doing in it."""
    fake_llm.reply = "閥面燒紅了。\n場景:工作間\n動作:焊接"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "在做什麼?")

    assert turn.scene == "工作間"
    assert turn.action == "焊接"
    assert turn.reply == "閥面燒紅了。"


def test_the_tags_parse_in_either_order(conn, fake_llm):
    fake_llm.reply = "全黑了。\n動作:停電\n場景:配電所"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "怎麼了?")

    assert (turn.scene, turn.action) == ("配電所", "停電")
    assert turn.reply == "全黑了。"


def test_an_action_we_cannot_draw_is_dropped_not_shown(conn, fake_llm):
    fake_llm.reply = "我在跳舞。\n場景:工作間\n動作:跳舞"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "在幹嘛?")

    assert turn.action is None
    assert turn.scene == "工作間"
    assert turn.reply == "我在跳舞。"


def test_a_conversation_beat_gets_an_anchor_too(conn, fake_llm):
    """Every beat the system produces carries an id, not just the offline ones —
    otherwise half the story could never hold a clip or a page."""
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "在嗎?")

    db.attach_asset(conn, turn.event_id, kind="video", ref="clips/bench.webm")
    assert [a["ref"] for a in db.get_assets(conn, turn.event_id)] == ["clips/bench.webm"]


# --- delegation (設計文件 第十二節) -----------------------------------------


def test_a_delegation_tag_is_peeled_off_and_recorded(conn, fake_llm):
    """The tag is a stage direction like the others: it must never reach the player,
    and it must never reach memory either, or the next turn feeds it back as something
    he said out loud."""
    fake_llm.reply = "行,我明天繞過去看看。\n場景:工作間\n委託:去回收場東邊找一個還能用的壓力閥"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "幫我看看回收場東邊還有沒有能用的壓力閥")

    assert turn.reply == "行,我明天繞過去看看。"
    assert turn.delegation == "去回收場東邊找一個還能用的壓力閥"
    assert [d["request"] for d in db.get_pending_delegations(conn, agent_id)] == [
        "去回收場東邊找一個還能用的壓力閥"
    ]
    assert "委託" not in db.get_recent_memory(conn, agent_id, limit=2)[0]["content"]


def test_an_ordinary_turn_records_no_delegation(conn, fake_llm):
    fake_llm.reply = "還行。\n場景:工作間"
    agent_id = persona.seed_default_agent(conn)

    turn = respond(conn, agent_id, fake_llm, "最近怎樣?")

    assert turn.delegation is None
    assert db.get_pending_delegations(conn, agent_id) == []


def test_an_empty_delegation_tag_is_not_an_errand():
    """A model told the line is optional writes it anyway. Recording that would leave
    him owing the player something nobody asked for."""
    for filler in ("無", "沒有", "null"):
        _, _, _, delegation = split_scene_tag(f"嗯。\n委託:{filler}")
        assert delegation is None


def test_a_pending_delegation_is_in_the_next_conversation_prompt(conn, fake_llm):
    """Without this he takes the same errand on twice and the player can't tell."""
    agent_id = persona.seed_default_agent(conn)
    db.add_delegation(conn, agent_id, "去回收場東邊找壓力閥")

    respond(conn, agent_id, fake_llm, "在嗎?")

    assert "去回收場東邊找壓力閥" in fake_llm.calls[0][1]
