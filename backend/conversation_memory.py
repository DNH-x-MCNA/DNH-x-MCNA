# -*- coding: utf-8 -*-
"""
"Bo nao" nho ngu canh hoi thoai cho chatbot webapp - luu cac cap (cau hoi, cau tra loi cuoi cung)
theo tung session (1 phien chat tren webapp), de cau hoi tiep theo (vd "con thang truoc thi sao")
hieu duoc ngu canh ma khong can nguoi dung nhac lai tu dau.

Chi luu VAN BAN cau hoi + cau tra loi cuoi (khong luu lai chi tiet cac buoc goi tool/SQL trung gian) -
don gian, ben vung qua nhieu lan restart server (SQLite file), va Claude van suy luan tot tu ngu canh
van ban thuan nay ma khong can replay lai dung tool_use/tool_result cu.
"""
import os, sqlite3, time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


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
    # Query State (co cau truc) - luu tool/tham so vua dung trong session, de cau hoi noi tiep kieu
    # "con quy truoc thi sao?" co the doi chieu chac chan thay vi chi doc lai text lich su tho.
    conn.execute("""CREATE TABLE IF NOT EXISTS query_state (
        session_id TEXT PRIMARY KEY,
        last_tool TEXT,
        last_args TEXT,
        updated_at TEXT NOT NULL
    )""")
    conn.commit()
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


def append_message(session_id: str, role: str, content: str):
    conn = _conn()
    try:
        conn.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                      (session_id, role, content, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()


def clear_session(session_id: str):
    conn = _conn()
    try:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM query_state WHERE session_id=?", (session_id,))
        conn.commit()
    finally:
        conn.close()


init()
