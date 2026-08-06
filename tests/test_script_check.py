"""The prompt has demanded Traditional Chinese since T0; nothing has ever checked.

`src/everliving/offline.py:259` says "所有文字一律用繁體中文,包括 state_changes 的鍵名",
and the first local Ollama run produced 「從没见过」 anyway
(`playtests/2026-08-06-ollama.txt:40`). Groq never did it, so the rule looked like it
was working for months. It wasn't working — nobody was looking.

The detector is deliberately conservative: it only knows characters that are
*simplified-only*, and skips every form that is also legitimate Traditional Chinese
(里 in 公里, 后 in 皇后, 面 in 面對). Missing a slip is cheap; flagging correct prose
would train everyone to ignore the warning, which costs the whole check.
"""

import logging

from everliving import offline, persona
from everliving.agent_loop import respond
from everliving.script_check import find_simplified

WARNED = "everliving.script_check"


def test_finds_simplified_characters_in_order():
    assert find_simplified("重新點火時,備援晶片跳出一個從没见过卻熟悉代號") == ["没", "见", "过"]


def test_real_traditional_narrative_is_clean():
    # The rest of that same Ollama narrative, which was correct.
    text = (
        "潮汐硬把水位頂過防禦線,我脫了外套踩進冷水裡,花了一整夜才把主泵沉沙格掏空。"
        "你留在工具架上的老電表還釘在牆上沒動,儘管缺錢我也只拿舊零件去換密封墊。"
    )
    assert find_simplified(text) == []


def test_characters_that_are_also_valid_traditional_are_not_flagged():
    # 里 (公里), 后 (皇后), 面 (面對), 只 (只有), 干 (干擾), 云 (子曰詩云), 系 (系統),
    # 台 (台北), 制 (制度), 表 (表面) all simplify something else but are correct here.
    # A detector that cries about these gets muted, and then catches nothing at all.
    text = "他走了三公里,皇后在台北的系統面前只說了一句話,干擾表面上是制度問題"
    assert find_simplified(text) == []


def test_each_character_reported_once():
    assert find_simplified("这这这个个") == ["这", "个"]


def test_empty_and_non_chinese_text():
    assert find_simplified("") == []
    assert find_simplified("SELECT * FROM memory_events;") == []


def test_conversation_reply_is_checked_too(conn, fake_llm, caplog):
    # Wiring the check into offline parsing alone left the chat path open, and the very
    # next real reply went through it: 「坐标是舊港區的沉標塔」 — 标 simplified and 標
    # correct, in one sentence. Chat is the path players touch most; it cannot be the
    # one that isn't watched.
    fake_llm.reply = "訊號已傳回去,坐标是舊港區的沉標塔。"
    agent_id = persona.seed_default_agent(conn)

    with caplog.at_level(logging.WARNING, logger=WARNED):
        turn = respond(conn, agent_id, fake_llm, "確認")

    assert turn.reply == "訊號已傳回去,坐标是舊港區的沉標塔。"
    assert any("标" in record.message for record in caplog.records)


def test_conversation_stays_quiet_on_clean_reply(conn, fake_llm, caplog):
    fake_llm.reply = "訊號已傳回去,坐標是舊港區的沉標塔。"
    agent_id = persona.seed_default_agent(conn)
    with caplog.at_level(logging.WARNING, logger=WARNED):
        respond(conn, agent_id, fake_llm, "確認")
    assert caplog.records == []


def test_offline_parse_logs_a_warning_when_the_model_slips(caplog):
    raw = '{"narrative": "備援晶片跳出一個從没见过的訊號", "events": [], "state_changes": {}}'
    with caplog.at_level(logging.WARNING, logger=WARNED):
        result = offline.parse_offline_response(raw)

    # The narrative still reaches the player — regenerating costs another call, and on
    # a local model that is five minutes. Detection first; what to do about it is a
    # decision for the human, not something to settle inside a parser.
    assert "从" not in result.narrative
    assert result.narrative == "備援晶片跳出一個從没见过的訊號"
    assert any("简" in r.message or "簡" in r.message for r in caplog.records)
    assert any("没" in r.message for r in caplog.records)


def test_offline_parse_stays_quiet_on_clean_output(caplog):
    raw = '{"narrative": "我把主泵沉沙格掏空了", "events": [], "state_changes": {}}'
    with caplog.at_level(logging.WARNING, logger=WARNED):
        offline.parse_offline_response(raw)
    assert caplog.records == []


def test_state_change_keys_are_checked_too():
    # The prompt calls the keys out by name because the player sees them. A slip there
    # is more visible than one buried mid-sentence, not less.
    raw = '{"narrative": "沒事", "events": [], "state_changes": {"右手腕机能": "發炎"}}'
    assert find_simplified("右手腕机能") == ["机"]
    result = offline.parse_offline_response(raw)
    assert result.state_changes == {"右手腕机能": "發炎"}
