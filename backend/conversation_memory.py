# -*- coding: utf-8 -*-
"""
"Bo nao" nho ngu canh hoi thoai cho chatbot webapp - luu cac cap (cau hoi, cau tra loi cuoi cung)
theo tung session (1 phien chat tren webapp), de cau hoi tiep theo (vd "con thang truoc thi sao")
hieu duoc ngu canh ma khong can nguoi dung nhac lai tu dau.

Chi luu VAN BAN cau hoi + cau tra loi cuoi (khong luu lai chi tiet cac buoc goi tool/SQL trung gian) -
don gian, ben vung qua nhieu lan restart server (SQLite file), va Claude van suy luan tot tu ngu canh
van ban thuan nay ma khong can replay lai dung tool_use/tool_result cu.
"""
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_column(conn, table_name: str, column_name: str, definition: str):
    """Them cot cho SQLite cu theo cach idempotent (SQLite khong co ADD COLUMN IF NOT EXISTS)."""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init():
    conn = _conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, id)")
    _ensure_column(conn, "messages", "query_id", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_query ON messages(query_id)")
    # Query State (co cau truc) - luu tool/tham so vua dung trong session, de cau hoi noi tiep kieu
    # "con quy truoc thi sao?" co the doi chieu chac chan thay vi chi doc lai text lich su tho.
    conn.execute("""CREATE TABLE IF NOT EXISTS query_state (
        session_id TEXT PRIMARY KEY,
        last_tool TEXT,
        last_args TEXT,
        updated_at TEXT NOT NULL
    )""")
    # sessions: 1 dong = 1 cuoc tro chuyen (nhieu session/nguoi dung, kieu ChatGPT). owner_username
    # dung de kiem soat quyen xem: nguoi thuong CHI xem duoc session cua chinh minh, c_level xem duoc
    # tat ca (xem GET /sessions, GET /history/{id} trong main.py).
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        owner_username TEXT NOT NULL,
        title TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_owner ON sessions(owner_username, updated_at)")
    # query_runs: so cai truy van chuan. Moi cau hoi co mot query_id xuyen suot tu API den UI;
    # feedback hien tai nam ngay tren dong truy van de dashboard/bao cao khong phai ghep event.
    conn.execute("""CREATE TABLE IF NOT EXISTS query_runs (
        query_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        username TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        sql_used_json TEXT,
        freshness_json TEXT,
        row_count INTEGER,
        duration_ms INTEGER,
        error_message TEXT,
        feedback_rating INTEGER CHECK(feedback_rating IS NULL OR feedback_rating IN (-1, 1)),
        feedback_category TEXT,
        feedback_comment TEXT,
        feedback_by TEXT,
        feedback_at TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    )""")
    _ensure_column(conn, "query_runs", "freshness_json", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query_runs_session ON query_runs(session_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query_runs_user ON query_runs(username, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query_runs_feedback ON query_runs(feedback_rating, feedback_at)")
    # Event append-only giu lich su khi nguoi dung thay doi danh gia; query_runs van la current state.
    conn.execute("""CREATE TABLE IF NOT EXISTS query_feedback_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_id TEXT NOT NULL,
        username TEXT NOT NULL,
        rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
        category TEXT,
        comment TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(query_id) REFERENCES query_runs(query_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_events_query ON query_feedback_events(query_id, id)")
    conn.commit()
    conn.close()


def register_session(session_id: str, owner_username: str, first_question: str):
    """Goi moi lan co tin nhan moi trong session (tu POST /chat) - INSERT neu la session moi (title
    lay tu ~50 ky tu dau cau hoi DAU TIEN), hoac chi cap nhat updated_at neu session da ton tai (title
    giu nguyen, khong doi theo cau hoi sau)."""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    title = (first_question or "").strip()[:50] or "Cuộc trò chuyện mới"
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO sessions (session_id, owner_username, title, created_at, updated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, owner_username, title, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def list_sessions(owner_username: str = None):
    """owner_username=None (danh cho c_level) tra ve TAT CA session, kem owner_username de biet cua
    ai; nguoc lai chi tra ve session cua dung nguoi do. Sap xep moi nhat truoc."""
    conn = _conn()
    try:
        if owner_username is None:
            rows = conn.execute(
                "SELECT session_id, owner_username, title, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, owner_username, title, created_at, updated_at "
                "FROM sessions WHERE owner_username=? ORDER BY updated_at DESC",
                (owner_username,),
            ).fetchall()
        return [{"session_id": r[0], "owner_username": r[1], "title": r[2],
                 "created_at": r[3], "updated_at": r[4]} for r in rows]
    finally:
        conn.close()


def get_session_owner(session_id: str):
    """Tra ve owner_username cua session, hoac None neu session chua dang ky (vd session cu tao
    truoc khi co bang nay, hoac khong ton tai) - main.py coi None la 'cho qua' de khong vo du lieu cu."""
    conn = _conn()
    try:
        row = conn.execute("SELECT owner_username FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_query_state(session_id: str, tool_name: str, args: str):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO query_state (session_id, last_tool, last_args, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET last_tool=excluded.last_tool, "
            "last_args=excluded.last_args, updated_at=excluded.updated_at",
            (session_id, tool_name, args, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()


def get_query_state(session_id: str):
    """Tra ve {last_tool, last_args, updated_at} hoac None neu session chua co truy van nao."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT last_tool, last_args, updated_at FROM query_state WHERE session_id=?", (session_id,)
        ).fetchone()
        return {"last_tool": row[0], "last_args": row[1], "updated_at": row[2]} if row else None
    finally:
        conn.close()


def load_history(session_id: str, max_turns: int = 10):
    """Tra ve list [{role, content}] cac tin nhan gan nhat trong session (moi turn = 1 cap hoi-dap,
    nen max_turns=10 nghia la toi da 20 dong tin nhan)."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, max_turns * 2),
        ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]
    finally:
        conn.close()


def append_message(session_id: str, role: str, content: str, query_id: str = None):
    conn = _conn()
    try:
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at, query_id) VALUES (?,?,?,?,?)",
            (session_id, role, content, time.strftime("%Y-%m-%d %H:%M:%S"), query_id),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def create_query_run(query_id: str, session_id: str, username: str, question: str):
    """Mo mot query run truoc khi goi model de loi/timeout van co dau vet day du."""
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO query_runs (query_id, session_id, username, question, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (query_id, session_id, username, question, "running", _utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def complete_query_run(
    query_id: str,
    answer: str,
    sql_used=None,
    freshness=None,
    row_count: int = None,
    duration_ms: int = None,
):
    conn = _conn()
    try:
        conn.execute(
            "UPDATE query_runs SET answer=?, status='completed', sql_used_json=?, freshness_json=?, row_count=?, "
            "duration_ms=?, error_message=NULL, completed_at=? WHERE query_id=?",
            (
                answer,
                json.dumps(sql_used or [], ensure_ascii=False),
                json.dumps(freshness or [], ensure_ascii=False),
                row_count,
                duration_ms,
                _utc_now(),
                query_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fail_query_run(query_id: str, error_message: str, duration_ms: int = None, status: str = "error"):
    conn = _conn()
    try:
        conn.execute(
            "UPDATE query_runs SET status=?, error_message=?, duration_ms=?, completed_at=? "
            "WHERE query_id=? AND status='running'",
            (status, (error_message or "")[:4000], duration_ms, _utc_now(), query_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_query_run(query_id: str):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT query_id, session_id, username, question, answer, status, sql_used_json, freshness_json, "
            "row_count, duration_ms, error_message, feedback_rating, feedback_category, "
            "feedback_comment, feedback_by, feedback_at, created_at, completed_at "
            "FROM query_runs WHERE query_id=?",
            (query_id,),
        ).fetchone()
        if not row:
            return None
        keys = (
            "query_id", "session_id", "username", "question", "answer", "status", "sql_used_json", "freshness_json",
            "row_count", "duration_ms", "error_message", "feedback_rating", "feedback_category",
            "feedback_comment", "feedback_by", "feedback_at", "created_at", "completed_at",
        )
        result = dict(zip(keys, row))
        try:
            result["sql_used"] = json.loads(result.pop("sql_used_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            result["sql_used"] = []
            result.pop("sql_used_json", None)
        try:
            result["freshness"] = json.loads(result.pop("freshness_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            result["freshness"] = []
            result.pop("freshness_json", None)
        return result
    finally:
        conn.close()


def list_query_runs(limit: int = 5000):
    """Nguon chuan cho dashboard lich su truy van; gioi han de khong nap vo han vao RAM."""
    safe_limit = max(1, min(int(limit or 5000), 10000))
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT query_id, session_id, username, question, answer, status, sql_used_json, freshness_json, "
            "row_count, duration_ms, error_message, feedback_rating, feedback_category, "
            "feedback_comment, feedback_by, feedback_at, created_at, completed_at "
            "FROM query_runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        keys = (
            "query_id", "session_id", "username", "question", "answer", "status", "sql_used_json", "freshness_json",
            "row_count", "duration_ms", "error_message", "feedback_rating", "feedback_category",
            "feedback_comment", "feedback_by", "feedback_at", "created_at", "completed_at",
        )
        result = []
        for row in rows:
            item = dict(zip(keys, row))
            try:
                item["sql_used"] = json.loads(item.pop("sql_used_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                item["sql_used"] = []
                item.pop("sql_used_json", None)
            try:
                item["freshness"] = json.loads(item.pop("freshness_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                item["freshness"] = []
                item.pop("freshness_json", None)
            result.append(item)
        return result
    finally:
        conn.close()


def save_query_feedback(query_id: str, username: str, rating: int, category: str = None, comment: str = None):
    """Cap nhat current state va them event trong cung transaction; API kiem tra owner truoc khi goi."""
    now = _utc_now()
    conn = _conn()
    try:
        cursor = conn.execute(
            "UPDATE query_runs SET feedback_rating=?, feedback_category=?, feedback_comment=?, "
            "feedback_by=?, feedback_at=? WHERE query_id=? AND username=?",
            (rating, category, comment, username, now, query_id, username),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        conn.execute(
            "INSERT INTO query_feedback_events (query_id, username, rating, category, comment, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (query_id, username, rating, category, comment, now),
        )
        conn.commit()
        return {
            "query_id": query_id,
            "rating": rating,
            "category": category,
            "comment": comment,
            "feedback_at": now,
        }
    finally:
        conn.close()


def get_session_history(session_id: str):
    """Lich su cho UI, kem query_id va feedback; load_history van giu payload gon cho LLM."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT m.id, m.role, m.content, m.query_id, qr.feedback_rating, "
            "qr.feedback_category, qr.feedback_comment "
            "FROM messages m LEFT JOIN query_runs qr ON qr.query_id=m.query_id "
            "WHERE m.session_id=? ORDER BY m.id",
            (session_id,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "query_id": row[3],
                "feedback_rating": row[4],
                "feedback_category": row[5],
                "feedback_comment": row[6],
            }
            for row in rows
        ]
    finally:
        conn.close()


def clear_session(session_id: str):
    conn = _conn()
    try:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM query_state WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.commit()
    finally:
        conn.close()


init()


# Aliases for compatibility with main.py imports
delete_session = clear_session
