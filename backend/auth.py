# -*- coding: utf-8 -*-
"""
He thong tai khoan + phan quyen theo cap bac cho webapp DNH AI Chatbot.
3 cap: c_level (xem toan bo cong ty), regional_director (gioi han theo area_code MB/MT/MN),
qlv (gioi han theo chinh employee_code cua minh - chi xem duoc du lieu vung minh phu trach).

Dang nhap bang username noi bo HOAC email cong ty (@namhapharma.com) + mat khau.
Luu tru rieng trong auth.db (tach biet voi warehouse.db/memory.db) - CHI chua tai khoan dang nhap.
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
            email TEXT,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            name TEXT,
            role TEXT NOT NULL,          -- 'c_level' | 'regional_director' | 'qlv'
            scope_value TEXT,            -- NULL cho c_level; 'MB'/'MT'/'MN' cho regional_director VA qlv (loc du lieu vung)
            employee_code TEXT,          -- CHI dung cho qlv
            scope_channel TEXT,           -- NULL binh thuong; 'OTC' neu tai khoan bi gioi han CHI xem duoc kenh OTC
            status TEXT DEFAULT 'approved', -- 'pending' | 'approved'
            must_change_password INTEGER DEFAULT 0,
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

    # Dynamic migrations for existing databases
    for col_def in [
        ("scope_channel", "TEXT"),
        ("email", "TEXT"),
        ("status", "TEXT DEFAULT 'approved'"),
        ("must_change_password", "INTEGER DEFAULT 0"),
    ]:
        col_name, col_type = col_def
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Ensure index exists after ALTER TABLE columns exist
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.close()
    
    # Run user migration and seeding
    migrate_and_seed_users()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()


def generate_password(length: int = 10) -> str:
    """Sinh mat khau ngau nhien an toan, loai bo cac ky tu de nham (O/0, l/1/I)."""
    chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


def create_user(username: str, password: str, name: str, role: str, scope_value: str = None,
                employee_code: str = None, scope_channel: str = None, email: str = None,
                status: str = 'approved') -> dict:
    if role not in ("c_level", "admin_ops", "regional_director", "qlv"):
        raise ValueError(f"Vai tro khong hop le: {role}")
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(password, salt)
    clean_username = username.lower().strip()
    clean_email = email.lower().strip() if email else None

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, salt, name, role, scope_value, employee_code, "
            "scope_channel, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (clean_username, clean_email, pwd_hash, salt, name, role, scope_value, employee_code, scope_channel, status,
             dt.datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"username": clean_username, "email": clean_email, "name": name, "role": role, "scope_value": scope_value,
            "employee_code": employee_code, "scope_channel": scope_channel, "status": status}


def create_pending_user(email: str, name: str = None) -> tuple[dict, str]:
    """Tao tai khoan tu dang ky o trang thai pending, sinh mat khau ngau nhien."""
    clean_email = email.lower().strip()
    raw_pwd = generate_password(10)
    username = clean_email  # Dùng email làm username duy nhất
    display_name = name or clean_email.split('@')[0]

    user_info = create_user(
        username=username,
        email=clean_email,
        password=raw_pwd,
        name=display_name,
        role='qlv',           # Role mặc định
        scope_value=None,    # Chưa được phân vùng
        employee_code=None,  # Chưa gán mã nhân viên
        status='pending'     # Trạng thái chờ duyệt
    )
    return user_info, raw_pwd


def admin_create_user(username: str, name: str = None, role: str = 'qlv', scope_value: str = None,
                      employee_code: str = None, scope_channel: str = None,
                      email: str = None, password: str = None) -> tuple[dict, str]:
    """Admin tao tai khoan moi truc tiep voi status=approved.
    Neu khong truyen password, se sinh mat khau ngau nhien.
    Email la optional - khong bat buoc @namhapharma.com nua."""
    raw_pwd = password or generate_password(10)
    clean_email = email.lower().strip() if email else None
    display_name = name or username

    user_info = create_user(
        username=username,
        email=clean_email,
        password=raw_pwd,
        name=display_name,
        role=role,
        scope_value=scope_value,
        employee_code=employee_code,
        scope_channel=scope_channel,
        status='approved'
    )
    return user_info, raw_pwd


def get_user_by_email_or_username(identifier: str) -> dict | None:
    clean_id = identifier.lower().strip()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active "
            "FROM users WHERE username=? OR email=?",
            (clean_id, clean_id)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "username": row[1], "email": row[2], "name": row[3],
            "role": row[4], "scope_value": row[5], "employee_code": row[6],
            "scope_channel": row[7], "status": row[8] or 'approved', "is_active": row[9]
        }
    finally:
        conn.close()


def verify_login(identifier: str, password: str) -> dict | None:
    clean_id = identifier.lower().strip()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash, salt, name, role, scope_value, employee_code, scope_channel, status, is_active "
            "FROM users WHERE username=? OR email=?",
            (clean_id, clean_id),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    uid, db_username, db_email, pwd_hash, salt, name, role, scope_value, employee_code, scope_channel, status, is_active = row

    if not hmac.compare_digest(_hash_password(password, salt), pwd_hash):
        return {"error": "wrong_password"}

    return {
        "id": uid,
        "username": db_username,
        "email": db_email,
        "name": name,
        "role": role,
        "scope_value": scope_value,
        "employee_code": employee_code,
        "scope_channel": scope_channel,
        "status": status or 'approved',
        "is_active": is_active
    }


def set_password(identifier: str, new_password: str) -> bool:
    """Dat lai mat khau cho 1 tai khoan theo username hoac email."""
    clean_id = identifier.lower().strip()
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(new_password, salt)
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash=?, salt=?, must_change_password=0 WHERE username=? OR email=?",
            (pwd_hash, salt, clean_id, clean_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def approve_user(username_or_email: str, role: str, scope_value: str = None,
                 employee_code: str = None, scope_channel: str = None) -> bool:
    """Quan tri vien duyet tai khoan tu pending -> approved va gan phan quyen."""
    clean_id = username_or_email.lower().strip()
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET status='approved', role=?, scope_value=?, employee_code=?, scope_channel=? "
            "WHERE username=? OR email=?",
            (role, scope_value, employee_code, scope_channel, clean_id, clean_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_user_active(username_or_email: str) -> dict | None:
    """Bat/Tat trang thai is_active cua tai khoan."""
    clean_id = username_or_email.lower().strip()
    conn = get_conn()
    try:
        row = conn.execute("SELECT is_active FROM users WHERE username=? OR email=?", (clean_id, clean_id)).fetchone()
        if not row:
            return None
        new_active = 0 if row[0] == 1 else 1
        conn.execute("UPDATE users SET is_active=? WHERE username=? OR email=?", (new_active, clean_id, clean_id))
        conn.commit()
        return {"username": clean_id, "is_active": new_active}
    finally:
        conn.close()


def list_users(status: str = None) -> list[dict]:
    """Danh sach tat ca tai khoan, hoac loc theo status (pending/approved)."""
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT id, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active, created_at "
                "FROM users WHERE status=? ORDER BY id DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active, created_at "
                "FROM users ORDER BY id DESC"
            ).fetchall()

        return [
            {
                "id": r[0], "username": r[1], "email": r[2], "name": r[3],
                "role": r[4], "scope_value": r[5], "employee_code": r[6],
                "scope_channel": r[7], "status": r[8] or 'approved', "is_active": r[9],
                "created_at": r[10]
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_all_sessions_for_user(user_id: int):
    """Xoa tat ca phien lam viec cu cua nguoi dung (khi quen mat khau)."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def get_name_by_username(username: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM users WHERE username=? OR email=?", (username.lower().strip(), username.lower().strip())).fetchone()
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
            "SELECT s.expires_at, u.id, u.username, u.email, u.name, u.role, u.scope_value, u.employee_code, u.scope_channel, u.status, u.is_active "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token=?",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    expires_at, uid, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active = row
    if dt.datetime.fromisoformat(expires_at) < dt.datetime.now():
        return None
    return {
        "id": uid, "username": username, "email": email, "name": name, "role": role,
        "scope_value": scope_value, "employee_code": employee_code,
        "scope_channel": scope_channel, "status": status or 'approved', "is_active": is_active
    }


def delete_session(token: str):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()


def get_subordinate_usernames(director_user: dict) -> list[str] | None:
    """Lay danh sach username cua QLV thuoc cung scope_value (Mien) va/hoac scope_channel (Kenh) cua director."""
    role = director_user.get("role")
    if role in ("c_level", "admin_ops"):
        return None  # Xem duoc tat ca
    
    scope_val = director_user.get("scope_value")
    scope_chan = director_user.get("scope_channel")
    username = director_user.get("username")
    
    conn = get_conn()
    try:
        query = "SELECT username FROM users WHERE role='qlv'"
        params = []
        if scope_val:
            query += " AND scope_value=?"
            params.append(scope_val)
        if scope_chan:
            query += " AND scope_channel=?"
            params.append(scope_chan)
            
        rows = conn.execute(query, params).fetchall()
        result = [r[0] for r in rows]
        if username and username not in result:
            result.append(username)
        return result
    finally:
        conn.close()


def migrate_and_seed_users():
    """Tudong migration: trieu.dang -> admin.dnh (giu nguyen mat khau hash), va khoi tao dnh (c_level)."""
    conn = get_conn()
    try:
        # 1. Doi username trieu.dang -> admin.dnh neu co
        row_trieu = conn.execute("SELECT id FROM users WHERE username='trieu.dang' OR email='trieu.dang@namhapharma.com'").fetchone()
        row_admin = conn.execute("SELECT id FROM users WHERE username='admin.dnh'").fetchone()
        
        if row_trieu and not row_admin:
            conn.execute("UPDATE users SET username='admin.dnh', role='admin_ops', name='Admin Vận Hành' WHERE id=?", (row_trieu[0],))
            conn.commit()
        elif not row_trieu and not row_admin:
            salt = secrets.token_hex(16)
            pwd_hash = _hash_password("dnh@admin2026", salt)
            conn.execute(
                "INSERT INTO users (username, email, password_hash, salt, name, role, status, created_at) "
                "VALUES ('admin.dnh', 'admin@namhapharma.com', ?, ?, 'Admin Vận Hành', 'admin_ops', 'approved', ?)",
                (pwd_hash, salt, dt.datetime.now().isoformat())
            )
            conn.commit()
        else:
            conn.execute("UPDATE users SET role='admin_ops' WHERE username='admin.dnh'")
            conn.commit()

        # 2. Dam bao tai khoan dnh (C-Level duy nhat) ton tai
        row_dnh = conn.execute("SELECT id FROM users WHERE username='dnh'").fetchone()
        if not row_dnh:
            salt = secrets.token_hex(16)
            pwd_hash = _hash_password("dnh@clevel2026", salt)
            conn.execute(
                "INSERT INTO users (username, email, password_hash, salt, name, role, status, created_at) "
                "VALUES ('dnh', 'dnh@namhapharma.com', ?, ?, 'Tổng Giám Đốc', 'c_level', 'approved', ?)",
                (pwd_hash, salt, dt.datetime.now().isoformat())
            )
            conn.commit()
        else:
            conn.execute("UPDATE users SET role='c_level' WHERE username='dnh'")
            conn.commit()

        # 3. Dam bao tat ca cac tai khoan Giam doc Mien / Kenh (co scope_value hoac scope_channel hoac username cap manager) KHONG bi set lam c_level
        conn.execute(
            "UPDATE users SET role='regional_director' "
            "WHERE username NOT IN ('dnh', 'admin.dnh') AND (scope_value IS NOT NULL OR scope_channel IS NOT NULL OR username LIKE 'manager_%')"
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
    print(f"Schema auth da tao/xac nhan tai: {DB_PATH}")

