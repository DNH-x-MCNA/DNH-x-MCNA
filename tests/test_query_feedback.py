import sqlite3

from backend import conversation_memory as memory


def use_temp_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    memory.init()
    return db_path


def test_init_migrates_existing_messages_without_losing_data(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
        "role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
        ("old-session", "user", "Cau hoi cu", "2026-08-01 08:00:00"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    memory.init()

    conn = sqlite3.connect(db_path)
    message_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    old_message = conn.execute("SELECT content, query_id FROM messages").fetchone()
    query_run_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='query_runs'"
    ).fetchone()
    conn.close()

    assert "query_id" in message_columns
    assert old_message == ("Cau hoi cu", None)
    assert query_run_exists == (1,)


def test_query_run_feedback_is_joined_into_history_and_audited(tmp_path, monkeypatch):
    db_path = use_temp_database(tmp_path, monkeypatch)
    query_id = "query-001"
    memory.create_query_run(query_id, "session-001", "alice", "Doanh thu hom nay?")
    memory.append_message("session-001", "user", "Doanh thu hom nay?", query_id=query_id)
    memory.append_message("session-001", "assistant", "100 trieu dong", query_id=query_id)
    memory.complete_query_run(
        query_id,
        "100 trieu dong",
        sql_used=["SELECT 100"],
        row_count=1,
        duration_ms=125,
    )

    first = memory.save_query_feedback(query_id, "alice", -1, "wrong_number", "Can kiem tra VAT")
    second = memory.save_query_feedback(query_id, "alice", 1, None, "Da doi chieu lai, ket qua dung")
    # Dong stream sau event `done` khong duoc ghi de trang thai completed thanh cancelled/error.
    memory.fail_query_run(query_id, "late disconnect", duration_ms=999, status="cancelled")

    query_run = memory.get_query_run(query_id)
    history = memory.get_session_history("session-001")
    conn = sqlite3.connect(db_path)
    event_count = conn.execute(
        "SELECT COUNT(*) FROM query_feedback_events WHERE query_id=?", (query_id,)
    ).fetchone()[0]
    conn.close()

    assert first["rating"] == -1
    assert second["rating"] == 1
    assert query_run["status"] == "completed"
    assert query_run["sql_used"] == ["SELECT 100"]
    assert query_run["feedback_comment"] == "Da doi chieu lai, ket qua dung"
    assert history[-1]["query_id"] == query_id
    assert history[-1]["feedback_rating"] == 1
    assert event_count == 2


def test_feedback_cannot_be_written_by_another_user(tmp_path, monkeypatch):
    use_temp_database(tmp_path, monkeypatch)
    memory.create_query_run("query-002", "session-002", "alice", "Cong no?")

    assert memory.save_query_feedback("query-002", "bob", -1, "wrong_scope", "Sai mien") is None
    assert memory.get_query_run("query-002")["feedback_rating"] is None
