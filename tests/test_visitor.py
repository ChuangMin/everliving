"""An AI in the player's seat.

Two things this has to get right, and neither is about the conversation quality:

- **A hard cap.** Every auto turn is *two* LLM calls, and the loop drives itself. An
  uncapped autoplay is a denial-of-wallet path pointed at the owner's own key.
- **Honest books.** The world itself is not told whether it's talking to a person or
  an agent — that's the 統一居民介面 reservation, and this is the first thing to
  actually exercise it. But `llm_calls` must record which turns were machine-driven,
  or the cost numbers H-1 depends on quietly stop meaning anything.
"""

from conftest import FakeLLMClient

from everliving import db, persona, visitor


def test_the_visitor_says_something_and_it_reaches_the_agent(conn):
    llm = FakeLLMClient(reply="最近潮位怎麼樣?")
    agent_id = persona.seed_default_agent(conn)

    message = visitor.next_message(conn, agent_id, llm)

    assert message == "最近潮位怎麼樣?"


def test_the_visitor_sees_what_has_already_been_said(conn):
    """It has to continue a conversation, not restart one every turn."""
    llm = FakeLLMClient(reply="那泵房修好了嗎?")
    agent_id = persona.seed_default_agent(conn)
    db.add_memory_event(conn, agent_id, kind="raw", content="我回答:泵房進水了。")

    visitor.next_message(conn, agent_id, llm)

    _, user_message = llm.calls[0]
    assert "泵房進水了" in user_message


def test_a_quoted_reply_is_unwrapped(conn):
    """Models like to answer with 「…」 around the line. That quote mark would be
    typed into the game as if the visitor had said it."""
    llm = FakeLLMClient(reply='「你還好嗎?」')
    agent_id = persona.seed_default_agent(conn)

    assert visitor.next_message(conn, agent_id, llm) == "你還好嗎?"


def test_the_visitor_turn_is_logged_as_machine_driven(conn):
    """The world doesn't distinguish人 from agent, but the ledger must."""
    llm = FakeLLMClient(reply="在嗎?", usage={"model": "m", "input_tokens": 5, "output_tokens": 3})
    agent_id = persona.seed_default_agent(conn)

    visitor.next_message(conn, agent_id, llm)

    purposes = [r["purpose"] for r in conn.execute("SELECT purpose FROM llm_calls")]
    assert purposes == ["auto_visitor"]


def test_the_visitor_can_ask_him_to_do_something(conn, fake_llm):
    """A stand-in for the player needs the player's affordances. Delegation is the
    control model, so a visitor that can only make small talk exercises half the
    system and then reports that half as though it were the whole."""
    agent_id = persona.seed_default_agent(conn)

    visitor.next_message(conn, agent_id, fake_llm)

    system_prompt, _ = fake_llm.calls[0]
    assert "請他幫你去做一件事" in system_prompt
