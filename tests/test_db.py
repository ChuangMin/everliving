from everliving import db


def test_create_and_get_agent(conn):
    agent_id = db.create_agent(conn, "測試角色", "背景故事", "個性描述")
    agent = db.get_agent(conn, agent_id)
    assert agent is not None
    assert agent["name"] == "測試角色"
    assert agent["background"] == "背景故事"
    assert agent["personality"] == "個性描述"


def test_get_agent_missing_returns_none(conn):
    assert db.get_agent(conn, 999) is None


def test_add_and_get_recent_memory_ordering(conn):
    agent_id = db.create_agent(conn, "A", "b", "p")
    db.add_memory_event(conn, agent_id, "raw", "first", occurred_at="2026-01-01T00:00:00+00:00")
    db.add_memory_event(conn, agent_id, "raw", "second", occurred_at="2026-01-02T00:00:00+00:00")
    db.add_memory_event(conn, agent_id, "raw", "third", occurred_at="2026-01-03T00:00:00+00:00")

    recent = db.get_recent_memory(conn, agent_id, limit=2)

    assert [row["content"] for row in recent] == ["third", "second"]


def test_get_recent_memory_scoped_to_agent(conn):
    agent_a = db.create_agent(conn, "A", "b", "p")
    agent_b = db.create_agent(conn, "B", "b", "p")
    db.add_memory_event(conn, agent_a, "raw", "belongs to A")
    db.add_memory_event(conn, agent_b, "raw", "belongs to B")

    recent_a = db.get_recent_memory(conn, agent_a)

    assert len(recent_a) == 1
    assert recent_a[0]["content"] == "belongs to A"


def test_last_seen_set_and_get(conn):
    agent_id = db.create_agent(conn, "A", "b", "p")
    assert db.get_last_seen(conn, agent_id) is None

    db.set_last_seen(conn, agent_id, "2026-01-01T00:00:00+00:00")
    assert db.get_last_seen(conn, agent_id) == "2026-01-01T00:00:00+00:00"

    db.set_last_seen(conn, agent_id, "2026-01-02T00:00:00+00:00")
    assert db.get_last_seen(conn, agent_id) == "2026-01-02T00:00:00+00:00"
