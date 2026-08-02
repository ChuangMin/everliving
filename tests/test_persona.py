from everliving import db, persona


def test_seed_default_agent_creates_agent(conn):
    agent_id = persona.seed_default_agent(conn)
    agent = db.get_agent(conn, agent_id)
    assert agent["name"] == persona.DEFAULT_PERSONA["name"]


def test_seed_default_agent_is_idempotent(conn):
    first_id = persona.seed_default_agent(conn)
    second_id = persona.seed_default_agent(conn)
    assert first_id == second_id
    assert conn.execute("SELECT COUNT(*) AS n FROM agents").fetchone()["n"] == 1
