"""The response-shape handling that only breaks against the real API — so it gets tests."""

import types

import pytest

from everliving.llm import LLMRefusal, extract_text


def block(kind: str, text: str | None = None):
    b = types.SimpleNamespace(type=kind)
    if text is not None:
        b.text = text
    return b


def test_extracts_single_text_block():
    assert extract_text([block("text", "我在修水管。")]) == "我在修水管。"


def test_skips_leading_thinking_block():
    """Thinking is on by default on the Claude 5 family — block 0 is not text there."""
    blocks = [block("thinking"), block("text", "我在修水管。")]
    assert extract_text(blocks) == "我在修水管。"


def test_joins_multiple_text_blocks():
    blocks = [block("text", "我在修水管。"), block("text", "晚點再說。")]
    assert extract_text(blocks) == "我在修水管。晚點再說。"


def test_skips_tool_use_block():
    blocks = [block("tool_use"), block("text", "好。")]
    assert extract_text(blocks) == "好。"


def test_no_text_blocks_returns_empty_string():
    assert extract_text([block("thinking")]) == ""


def test_strips_surrounding_whitespace():
    assert extract_text([block("text", "\n  好。  \n")]) == "好。"


def test_refusal_is_its_own_exception_type():
    """So callers can tell a declined request apart from a network or auth failure."""
    assert issubclass(LLMRefusal, RuntimeError)
    with pytest.raises(LLMRefusal):
        raise LLMRefusal("declined")
