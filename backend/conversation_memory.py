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
        conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.commit()
    finally:
        conn.close()


init()


# Aliases for compatibility with main.py imports
delete_session = clear_session
get_session_history = load_history
