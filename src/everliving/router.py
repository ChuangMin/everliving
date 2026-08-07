"""AUTO ROUTER — choose a provider per call, instead of making the human choose once.

人類 2026-08-07 answered the provider question with 「AUTO ROUTER」: not one of them,
something that chooses. Then he set the goal 「以目標變成最多人玩的遊戲」 and took the
scope fence down, which promotes this from a nicety to the first obstacle — today the
app exits at startup when the selected provider has no key, so a stranger who clones
this and has no account cannot play at all.

What it routes between, measured 2026-08-07:

- **Groq**: 2.8s per call, but 200k tokens/day, and it has already run out mid-playtest
- **Ollama**: $0, no key, no network — but 5-7 minutes, and 2 of 4 calls produced nothing

So the order is fastest-first, local-last. A router that warmed up the local model on
every call would spend five minutes to save three seconds.

**On H-1's warning that switching provider mid-run destroys attribution** (`TASKS.md`):
it doesn't. `log_usage` writes `usage["model"]` on every call, so `llm_calls` already
records who wrote each beat. The real conflict was between switching and *guessing
afterwards* — and with this, nobody has to guess.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from everliving.llm import LLMClient, LLMRefusal

_log = logging.getLogger("everliving.router")

#: Fastest first, local last. The local one is deliberately the final entry rather than
#: one option among equals: it is the only one that cannot run out, so it is what makes
#: "someone with no account can still play" true.
DEFAULT_ORDER = ("groq", "grok", "anthropic", "ollama")


class AllProvidersFailed(RuntimeError):
    """Nothing answered. Distinct from any single provider's failure."""


class RoutingLLMClient:
    """An `LLMClient` that delegates to the first candidate able to answer.

    Candidates are `(name, build)` pairs and are built lazily, at most once each,
    because constructing a client opens SDK objects and validates credentials — doing
    that for providers we never reach would reintroduce the startup failure this exists
    to remove.
    """

    def __init__(self, candidates: Sequence[tuple[str, Callable[[], LLMClient]]]) -> None:
        self._candidates = list(candidates)
        self._built: dict[str, LLMClient | None] = {}
        self.last_usage: dict | None = None

    def _client(self, name: str, build: Callable[[], LLMClient]) -> LLMClient | None:
        """Build once and remember, including remembering that it can't be built.

        A missing key or an uninstalled SDK is a permanent fact for this process, so
        re-attempting it on every call would pay the same failure repeatedly.
        """
        if name not in self._built:
            try:
                self._built[name] = build()
            except Exception as exc:  # no key, SDK missing, bad config
                _log.info("provider %s 建不起來,跳過:%s", name, exc)
                self._built[name] = None
        return self._built[name]

    def complete(self, system_prompt: str, user_message: str) -> str:
        failures: list[str] = []

        for name, build in self._candidates:
            client = self._client(name, build)
            if client is None:
                failures.append(f"{name}(建不起來)")
                continue

            try:
                reply = client.complete(system_prompt, user_message)
            except LLMRefusal:
                # A refusal is an answer. Asking the next provider would spend a second
                # call to get a different opinion on something already answered, and it
                # would quietly turn 「他說不要」 into 「問到有人肯為止」 — the opposite of
                # what the refusal rules exist for (設計文件 第十二節).
                raise
            except Exception as exc:
                _log.warning("provider %s 失敗,換下一個:%s", name, exc)
                failures.append(f"{name}({type(exc).__name__})")
                self._last_error = exc
                continue

            self.last_usage = getattr(client, "last_usage", None)
            if failures:
                _log.info("provider %s 接手了,前面失敗的:%s", name, "、".join(failures))
            return reply

        raise self._exhausted(failures)

    def _exhausted(self, failures: list[str]) -> Exception:
        """Re-raise the last real failure rather than a generic one.

        The last error carries the provider's own message, which is usually the actual
        instruction ("API key is invalid", "rate limit exceeded"). Replacing it with
        「全部都失敗了」 would throw away the only sentence worth reading.
        """
        last = getattr(self, "_last_error", None)
        if last is not None:
            return last
        return AllProvidersFailed("沒有任何 provider 可用:" + "、".join(failures))
