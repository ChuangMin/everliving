"""The suite must not be able to reach the network, whatever the config says.

This has now bitten twice, the same shape both times:

1. `conftest._hide_the_developers_dotenv` records the first — a developer's `.env` with
   `EVERLIVING_PROVIDER=groq` turned 8 passing tests into live API calls and a
   200-second suite. The fix hid `.env`.
2. 2026-08-07, wiring AUTO ROUTER: `test_provider_selection.py` sets a fake
   `XAI_API_KEY` itself, so with `auto` as the default the router happily built a real
   Grok client and called out. The suite hung until it was killed.

Hiding `.env` cannot stop the second one, because the key never came from `.env`. The
only thing that covers both is making the call itself impossible — so the guard sits on
the socket, below every provider, every SDK, and every way a key can arrive.

This matters more than it looks: a suite that can reach the network is a suite whose
results depend on someone's laptop, and one that can hang forever instead of failing.
"""

from __future__ import annotations

import socket

import pytest


def test_an_outbound_connection_is_refused_rather_than_attempted():
    """The guard is on, and it fails loudly instead of hanging.

    Addressed off-box on purpose: an earlier draft of this test said 「outbound」 and
    dialled loopback, which is the same defect this session kept finding elsewhere — a
    test whose name claims more than it checks.
    """
    with pytest.raises(RuntimeError, match="測試不准"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("api.groq.com", 443))


def test_the_local_model_is_blocked_too():
    """Ollama is on localhost, so 「只擋外網」 would have missed the case that hung.

    It is also the slowest thing that could be reached by accident: five to seven
    minutes per call, which is how a stray real call turns into a suite that looks
    frozen rather than broken.
    """
    with pytest.raises(RuntimeError, match="測試不准"):
        socket.create_connection(("localhost", 11434), timeout=1)
