"""Reasoning models on the OpenAI wire format inline their deliberation in the reply.

Observed with qwen/qwen3.6-27b on Groq: the player saw several paragraphs of the
model workshopping the line before the line itself.
"""

from everliving.llm import strip_reasoning


def test_removes_a_think_block():
    raw = "<think>Let me consider the tone.</think>碼頭的黑水深。"
    assert strip_reasoning(raw) == "碼頭的黑水深。"


def test_plain_reply_is_untouched():
    assert strip_reasoning("碼頭的黑水深。") == "碼頭的黑水深。"


def test_handles_a_closing_tag_with_no_opening_tag():
    """Some servers strip the opening tag but leave the closing one."""
    assert strip_reasoning("thinking out loud</think>我在修水管。") == "我在修水管。"


def test_splits_on_the_last_closing_tag():
    raw = "<think>a</think>middle</think>真正的回覆。"
    assert strip_reasoning(raw) == "真正的回覆。"


def test_unclosed_think_block_yields_nothing():
    """Budget went entirely to reasoning — there is no reply to salvage."""
    assert strip_reasoning("<think>still deliberating and never finished") == ""


def test_strips_surrounding_whitespace():
    assert strip_reasoning("<think>x</think>\n\n  我在修水管。  \n") == "我在修水管。"


def test_multiline_reasoning_is_removed_entirely():
    raw = "<think>\nline one\nline two\n</think>\n港口很安靜。"
    assert strip_reasoning(raw) == "港口很安靜。"
    assert "line one" not in strip_reasoning(raw)
