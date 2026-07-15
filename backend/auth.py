# -*- coding: utf-8 -*-
"""
He thong tai khoan + phan quyen theo cap bac cho webapp DNH AI Chatbot.
3 cap: c_level (xem toan bo cong ty), regional_director (gioi han theo area_code MB/MT/MN),
qlv (gioi han theo chinh employee_code cua minh - chi xem duoc du lieu vung minh phu trach).

Dang nhap bang username noi bo (KHONG dung email) + mat khau.
Luu tru rieng trong auth.db (tach biet voi warehouse.db/memory.db) - CHI chua tai khoan dang nhap,
KHONG chua du lieu kinh doanh cua DNH.
"""
import os
import sqlite3
import hashlib
import hmac
import secrets
import datetime as dt

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth.db")
SESSION_TTL_HOURS = 24 * 7  # phien dang nhap song 7 ngay


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            name TEXT,
            role TEXT NOT NULL,          -- 'c_level' | 'regional_director' | 'qlv'
            scope_value TEXT,            -- NULL cho c_level; 'MB'/'MT'/'MN' cho regional_director; employee_code cho qlv
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT,
            expires_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    """)
    conn.commit()
    conn.close()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()


def create_user(username: str, password: str, name: str, role: str, scope_value: str = None) -> dict:
    if role not in ("c_level", "regional_director", "qlv"):
        raise ValueError(f"Vai tro khong hop le: {role}")
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(password, salt)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, name, role, scope_value, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username.lower().strip(), pwd_hash, salt, name, role, scope_value, dt.datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"username": username, "name": name, "role": role, "scope_value": scope_value}


def verify_login(username: str, password: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, name, role, scope_value FROM users "
            "WHERE username=? AND is_active=1",
            (username.lower().strip(),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    uid, db_username, pwd_hash, salt, name, role, scope_value = row
    if not hmac.compare_digest(_hash_password(password, salt), pwd_hash):
        return None
    return {"id": uid, "username": db_username, "name": name, "role": role, "scope_value": scope_value}


def get_name_by_username(username: str) -> str | None:
    """Tra ten hien thi (name) tu username - dung khi c_level xem danh sach session cua nguoi khac,
    can hien ten thay vi chi username ky thuat."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM users WHERE username=?", (username.lower().strip(),)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = dt.datetime.now()
    expires = now + dt.timedelta(hours=SESSION_TTL_HOURS)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def get_user_by_session(token: str) -> dict | None:
    if not token:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT s.expires_at, u.id, u.username, u.name, u.role, u.scope_value "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token=? AND u.is_active=1",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    expires_at, uid, username, name, role, scope_value = row
    if dt.datetime.fromisoformat(expires_at) < dt.datetime.now():
        return None
    return {"id": uid, "username": username, "name": name, "role": role, "scope_value": scope_value}


def delete_session(token: str):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
    print(f"Schema auth da tao/xac nhan tai: {DB_PATH}")
