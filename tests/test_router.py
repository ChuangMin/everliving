"""AUTO ROUTER: pick a provider per call instead of making the human pick once.

人類 2026-08-07 answered the provider question with 「AUTO ROUTER」 — not one of them,
something that chooses. Then he set the goal 「以目標變成最多人玩的遊戲」 and took the
scope fence down, which makes this the first thing that matters: right now the app dies
at startup if the selected provider has no key, so anyone who clones this and has no
account cannot play at all.

The measured numbers this routes between (2026-08-07):

- Groq: 2.8s, but 200k tokens/day and it has already run out once mid-playtest
- Ollama: $0, no network, no key — but 5-7 minutes, and 2 of 4 calls produced nothing

`TASKS.md` H-1 warns that switching provider mid-run destroys attribution. It doesn't:
`log_usage` already writes `usage["model"]` on every single call, so which provider wrote
which beat is recorded rather than assumed. The conflict was between switching and
*guessing afterwards*, and nobody has to guess.
"""

from __future__ import annotations

import pytest

from everliving.llm import LLMAuthError, LLMRefusal, LLMUnavailable
from everliving.router import RoutingLLMClient


class FakeProvider:
    """Stands in for one provider. Records whether it was actually asked."""

    def __init__(self, name: str, reply: str = "ok", raises: Exception | None = None) -> None:
        self._name = name
        self._reply = reply
        self._raises = raises
        self.calls = 0
        self.last_usage: dict | None = None

    def complete(self, system_prompt: str, user_message: str) -> str:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        self.last_usage = {
            "model": self._name,
            "input_tokens": 10,
            "output_tokens": 20,
        }
        return self._reply


def _router(*candidates) -> RoutingLLMClient:
    """Candidates as (name, builder) pairs, the shape the real one takes."""
    return RoutingLLMClient([(name, lambda p=provider: p) for name, provider in candidates])


def test_the_first_healthy_provider_answers_and_the_rest_are_left_alone():
    """Order is the policy: fastest first, local last.

    A fallback that always warms up the slow one would cost 5-7 minutes to save 2.8
    seconds, which is the opposite of the point.
    """
    fast = FakeProvider("groq")
    slow = FakeProvider("ollama")

    router = _router(("groq", fast), ("ollama", slow))
    assert router.complete("s", "u") == "ok"

    assert fast.calls == 1
    assert slow.calls == 0


def test_an_outage_falls_through_to_the_next_one():
    """The failure that actually happened: Groq 429 mid-playtest, everything stopped."""
    dead = FakeProvider("groq", raises=LLMUnavailable("429 額度用完了"))
    local = FakeProvider("ollama", reply="本機答的")

    router = _router(("groq", dead), ("ollama", local))

    assert router.complete("s", "u") == "本機答的"
    assert local.calls == 1


def test_a_provider_that_cannot_even_be_built_is_skipped():
    """No key, or the SDK isn't installed.

    This is the one that decides whether a stranger can run this at all: today a
    missing GROQ_API_KEY exits the process. Someone who clones this with no account
    should land on the local provider without configuring anything.
    """

    def cannot_build():
        raise LLMAuthError("找不到 GROQ_API_KEY")

    local = FakeProvider("ollama")
    router = RoutingLLMClient([("groq", cannot_build), ("ollama", lambda: local)])

    assert router.complete("s", "u") == "ok"
    assert local.calls == 1


def test_the_provider_that_answered_is_the_one_recorded():
    """Attribution survives switching, which is what H-1's warning was really about.

    `log_usage` reads `last_usage["model"]`, so this is what ends up in `llm_calls` —
    every beat carries the name of whoever wrote it.
    """
    dead = FakeProvider("groq", raises=LLMUnavailable("down"))
    local = FakeProvider("ollama")

    router = _router(("groq", dead), ("ollama", local))
    router.complete("s", "u")

    assert router.last_usage is not None
    assert router.last_usage["model"] == "ollama"


def test_running_out_of_providers_raises_rather_than_returning_nothing():
    """An empty string here would become a blank night, and blank nights are permanent."""
    first = FakeProvider("groq", raises=LLMUnavailable("down"))
    second = FakeProvider("ollama", raises=LLMUnavailable("也連不上"))

    router = _router(("groq", first), ("ollama", second))

    with pytest.raises(LLMUnavailable):
        router.complete("s", "u")


def test_a_refusal_is_an_answer_and_is_not_routed_around():
    """The model declined. That is a reply, not an outage.

    Asking the next provider would spend a second call — on the slow one — to get a
    different opinion on something the first one already answered, and it would quietly
    turn 「他說不要」 into 「問到有人肯為止」, which is the opposite of what the refusal
    rules in 設計文件 第十二節 are for.
    """
    principled = FakeProvider("groq", raises=LLMRefusal("我不想講這個"))
    local = FakeProvider("ollama")

    router = _router(("groq", principled), ("ollama", local))

    with pytest.raises(LLMRefusal):
        router.complete("s", "u")
    assert local.calls == 0, "a refusal must not be shopped around"


def test_a_provider_is_only_built_once_across_calls():
    """Building a client opens SDK objects; doing it per call would be waste."""
    builds = []

    def build():
        builds.append(1)
        return FakeProvider("ollama")

    router = RoutingLLMClient([("ollama", build)])
    router.complete("s", "u")
    router.complete("s", "u")

    assert len(builds) == 1
