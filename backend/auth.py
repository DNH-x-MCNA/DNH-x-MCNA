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

VALID_ROLES = frozenset({"c_level", "admin_ops", "regional_director", "qlv"})
VALID_STATUSES = frozenset({"pending", "approved"})
VALID_AREA_CODES = frozenset({"MB", "MT", "MN"})
VALID_CHANNEL_CODES = frozenset({"OTC", "ETC"})


def validate_account_assignment(role: str, scope_value: str = None,
                                employee_code: str = None, scope_channel: str = None,
                                status: str = "approved", require_complete: bool = False) -> tuple:
    """Chuan hoa va kiem tra role/scope tai mot cho, dung cho moi duong ghi tai khoan.

    `require_complete=False` cho phep tao tai khoan pending hoac fixture noi bo chua gan du pham vi.
    Moi duong admin tao/duyet tai khoan approved phai truyen True de khong luu mot tai khoan co quyen
    nhung thieu scope. Runtime van kiem tra lai doc lap trong main.py theo nguyen tac fail-closed.
    """
    normalized_role = str(role or "").strip().lower()
    normalized_status = str(status or "").strip().lower()
    area = str(scope_value).strip().upper() if scope_value else None
    employee = str(employee_code).strip() if employee_code else None
    channel = str(scope_channel).strip().upper() if scope_channel else None

    if normalized_role not in VALID_ROLES:
        raise ValueError(f"Vai tro khong hop le: {role}")
    if normalized_status not in VALID_STATUSES:
        raise ValueError(f"Trang thai tai khoan khong hop le: {status}")
    if area and area not in VALID_AREA_CODES:
        raise ValueError(f"Pham vi mien khong hop le: {scope_value}")
    if channel and channel not in VALID_CHANNEL_CODES:
        raise ValueError(f"Pham vi kenh khong hop le: {scope_channel}")

    if normalized_role in {"c_level", "admin_ops"} and (area or employee or channel):
        raise ValueError(f"Vai tro {normalized_role} khong duoc gan scope mien/kenh/nhan vien")
    if normalized_role == "regional_director" and employee:
        raise ValueError("Giam doc mien/kenh khong duoc gan employee_code cua QLV")
    if require_complete and normalized_status == "approved":
        if normalized_role == "regional_director" and not (area or channel):
            raise ValueError("Giam doc mien/kenh phai duoc gan it nhat mot scope mien hoac kenh")
        if normalized_role == "qlv" and (not area or not employee):
            raise ValueError("QLV phai duoc gan day du scope mien va employee_code")

    return normalized_role, area, employee, channel, normalized_status


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
        ("password_changed_at", "TEXT"),
        ("last_login_at", "TEXT"),
        ("weekly_question_count", "INTEGER DEFAULT 0"),
        ("weekly_reset_at", "TEXT"),
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
                status: str = 'approved', must_change_password: int = 0) -> dict:
    role, scope_value, employee_code, scope_channel, status = validate_account_assignment(
        role, scope_value, employee_code, scope_channel, status, require_complete=False
    )
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(password, salt)
    clean_username = username.lower().strip()
    clean_email = email.lower().strip() if email else None

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, salt, name, role, scope_value, employee_code, "
            "scope_channel, status, must_change_password, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (clean_username, clean_email, pwd_hash, salt, name, role, scope_value, employee_code, scope_channel, status,
             1 if must_change_password else 0, dt.datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"username": clean_username, "email": clean_email, "name": name, "role": role, "scope_value": scope_value,
            "employee_code": employee_code, "scope_channel": scope_channel, "status": status,
            "must_change_password": 1 if must_change_password else 0}


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
        status='pending',    # Trạng thái chờ duyệt
        must_change_password=1,
    )
    return user_info, raw_pwd


def admin_create_user(username: str, name: str = None, role: str = 'qlv', scope_value: str = None,
                      employee_code: str = None, scope_channel: str = None,
                      email: str = None, password: str = None) -> tuple[dict, str]:
    """Admin tao tai khoan moi truc tiep voi status=approved.
    Neu khong truyen password, se sinh mat khau ngau nhien.
    Email la optional - khong bat buoc @namhapharma.com nua."""
    role, scope_value, employee_code, scope_channel, _ = validate_account_assignment(
        role, scope_value, employee_code, scope_channel, "approved", require_complete=True
    )
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
        status='approved',
        must_change_password=1,
    )
    return user_info, raw_pwd


def get_user_by_email_or_username(identifier: str) -> dict | None:
    clean_id = identifier.lower().strip()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active, "
            "must_change_password "
            "FROM users WHERE username=? OR email=?",
            (clean_id, clean_id)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "username": row[1], "email": row[2], "name": row[3],
            "role": row[4], "scope_value": row[5], "employee_code": row[6],
            "scope_channel": row[7], "status": row[8] or 'approved', "is_active": row[9],
            "must_change_password": int(row[10] or 0),
        }
    finally:
        conn.close()


def verify_login(identifier: str, password: str) -> dict | None:
    clean_id = identifier.lower().strip()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash, salt, name, role, scope_value, employee_code, scope_channel, "
            "status, is_active, must_change_password "
            "FROM users WHERE username=? OR email=?",
            (clean_id, clean_id),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    (uid, db_username, db_email, pwd_hash, salt, name, role, scope_value, employee_code,
     scope_channel, status, is_active, must_change_password) = row

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
        "is_active": is_active,
        "must_change_password": int(must_change_password or 0),
    }


def set_password(identifier: str, new_password: str, must_change_password: bool = False) -> bool:
    """Dat lai mat khau cho 1 tai khoan theo username hoac email."""
    clean_id = identifier.lower().strip()
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(new_password, salt)
    now_iso = dt.datetime.now().isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash=?, salt=?, must_change_password=?, password_changed_at=? WHERE username=? OR email=?",
            (pwd_hash, salt, 1 if must_change_password else 0, now_iso, clean_id, clean_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def reset_password_and_revoke_sessions(identifier: str, new_password: str,
                                       must_change_password: bool = True) -> bool:
    """Dat mat khau va thu hoi moi session trong cung mot transaction.

    Dung cho thao tac reset cua quan tri vien de khong co cua so thoi gian token cu con hieu luc
    sau khi mat khau da bi thay doi.
    """
    clean_id = identifier.lower().strip()
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(new_password, salt)
    now_iso = dt.datetime.now().isoformat()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM users WHERE username=? OR email=?", (clean_id, clean_id)
        ).fetchone()
        if not row:
            conn.rollback()
            return False
        conn.execute(
            "UPDATE users SET password_hash=?, salt=?, must_change_password=?, "
            "password_changed_at=? WHERE id=?",
            (pwd_hash, salt, 1 if must_change_password else 0, now_iso, row[0]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (row[0],))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def approve_user(username_or_email: str, role: str, scope_value: str = None,
                 employee_code: str = None, scope_channel: str = None) -> bool:
    """Quan tri vien duyet tai khoan tu pending -> approved va gan phan quyen."""
    role, scope_value, employee_code, scope_channel, _ = validate_account_assignment(
        role, scope_value, employee_code, scope_channel, "approved", require_complete=True
    )
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
                "SELECT id, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active, created_at, password_changed_at, last_login_at "
                "FROM users WHERE status=? ORDER BY id DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, username, email, name, role, scope_value, employee_code, scope_channel, status, is_active, created_at, password_changed_at, last_login_at "
                "FROM users ORDER BY id DESC"
            ).fetchall()

        return [
            {
                "id": r[0], "username": r[1], "email": r[2], "name": r[3],
                "role": r[4], "scope_value": r[5], "employee_code": r[6],
                "scope_channel": r[7], "status": r[8] or 'approved', "is_active": r[9],
                "created_at": r[10], "password_changed_at": r[11], "last_login_at": r[12]
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
    now_iso = now.isoformat()
    expires = now + dt.timedelta(hours=SESSION_TTL_HOURS)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now_iso, expires.isoformat())
        )
        conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now_iso, user_id))
        conn.commit()
        return token
    finally:
        conn.close()
    return token


def get_user_by_session(token: str) -> dict | None:
    if not token:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT s.expires_at, u.id, u.username, u.email, u.name, u.role, u.scope_value, u.employee_code, "
            "u.scope_channel, u.status, u.is_active, u.must_change_password "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token=?",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    (expires_at, uid, username, email, name, role, scope_value, employee_code, scope_channel,
     status, is_active, must_change_password) = row
    if dt.datetime.fromisoformat(expires_at) < dt.datetime.now():
        return None
    return {
        "id": uid, "username": username, "email": email, "name": name, "role": role,
        "scope_value": scope_value, "employee_code": employee_code,
        "scope_channel": scope_channel, "status": status or 'approved', "is_active": is_active,
        "must_change_password": int(must_change_password or 0),
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


def _week_start(now: dt.datetime) -> dt.datetime:
    """Moc 00:00 thu Hai cua tuan chua `now` (weekday(): Thu Hai=0)."""
    monday = now - dt.timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def check_and_consume_weekly_quota(username: str, limit: int | None) -> dict:
    """Kiem tra + tang bo dem cau hoi chatbot trong tuan cho 1 tai khoan, reset 00:00 thu Hai.

    Nguyen tu qua BEGIN IMMEDIATE (khoa ghi ngay khi bat dau transaction) - tranh 2 request cung
    luc doc chung so du TRUOC khi tang, lam lot qua vuot limit that (race condition kinh dien cua
    kieu check-then-act tren SQLite/nhieu request).

    limit None hoac <=0: khong gioi han (vai tro chua duoc gan han o main.py).
    Tra ve {"allowed": bool, "used": int, "limit": int|None, "resets_at": ISO 00:00 thu Hai ke tiep}.
    """
    if not limit or limit <= 0:
        return {"allowed": True, "used": 0, "limit": None, "resets_at": None}

    now = dt.datetime.now()
    week_start = _week_start(now)
    next_reset = week_start + dt.timedelta(days=7)
    clean_username = username.lower().strip()

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT weekly_question_count, weekly_reset_at FROM users WHERE username=?",
            (clean_username,),
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return {"allowed": True, "used": 0, "limit": limit, "resets_at": next_reset.isoformat()}

        count, reset_at = row
        count = count or 0
        needs_reset = not reset_at or dt.datetime.fromisoformat(reset_at) < week_start
        if needs_reset:
            count = 0

        if count >= limit:
            conn.execute(
                "UPDATE users SET weekly_reset_at=? WHERE username=?",
                (week_start.isoformat(), clean_username),
            )
            conn.commit()
            return {"allowed": False, "used": count, "limit": limit, "resets_at": next_reset.isoformat()}

        new_count = count + 1
        conn.execute(
            "UPDATE users SET weekly_question_count=?, weekly_reset_at=? WHERE username=?",
            (new_count, week_start.isoformat(), clean_username),
        )
        conn.commit()
        return {"allowed": True, "used": new_count, "limit": limit, "resets_at": next_reset.isoformat()}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_weekly_quota_status(username: str, limit: int | None) -> dict:
    """CHI DOC trang thai quota tuan, KHONG tang dem - dung de hien thi UI ("con X/Y cau tuan
    nay"). Khac han check_and_consume_weekly_quota() (dung khi THAT SU goi 1 cau hoi vao chatbot,
    co tang dem) - goi ham nay khi mo trang/dang nhap khong duoc lam hut mat 1 luot cua nguoi dung.

    Tra ve {"used", "limit", "remaining", "resets_at"}. limit None/<=0: khong gioi han, moi truong
    deu None ngoai "used"=0.
    """
    now = dt.datetime.now()
    week_start = _week_start(now)
    next_reset = week_start + dt.timedelta(days=7)

    if not limit or limit <= 0:
        return {"used": 0, "limit": None, "remaining": None, "resets_at": None}

    clean_username = username.lower().strip()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT weekly_question_count, weekly_reset_at FROM users WHERE username=?",
            (clean_username,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"used": 0, "limit": limit, "remaining": limit, "resets_at": next_reset.isoformat()}

    count, reset_at = row
    count = count or 0
    needs_reset = not reset_at or dt.datetime.fromisoformat(reset_at) < week_start
    if needs_reset:
        count = 0
    return {
        "used": count, "limit": limit, "remaining": max(0, limit - count),
        "resets_at": next_reset.isoformat(),
    }


def migrate_and_seed_users():
    """Chay migration danh tinh cu, KHONG tu tao tai khoan dac quyen.

    Ham nay duoc goi moi khi backend khoi dong, vi vay tuyet doi khong duoc gan lai role cua
    tai khoan da ton tai. Role/pham vi sau khi admin cap nhat la du lieu nghiep vu va phai duoc
    giu nguyen qua restart/deploy.
    """
    conn = get_conn()
    try:
        # 1. Doi username trieu.dang -> admin.dnh neu co
        row_trieu = conn.execute("SELECT id FROM users WHERE username='trieu.dang' OR email='trieu.dang@namhapharma.com'").fetchone()
        row_admin = conn.execute("SELECT id FROM users WHERE username='admin.dnh'").fetchone()
        
        if row_trieu and not row_admin:
            conn.execute("UPDATE users SET username='admin.dnh', role='admin_ops', name='Admin Vận Hành' WHERE id=?", (row_trieu[0],))
            conn.commit()
        # Tuyet doi khong seed admin/C-Level bang mat khau co dinh. Tai khoan dac quyen phai duoc
        # tao qua quy trinh bootstrap van hanh voi mat khau ngau nhien va must_change_password=1.
        # Khong UPDATE role cua bat ky tai khoan da ton tai nao o day. Truoc 13/08/2026, khoi
        # dong backend tu dong ep manager_* thanh regional_director va moi tai khoan con lai
        # thanh qlv. Do do role Giam doc Mien/Kenh admin vua luu se bi mat sau lan restart ke tiep.
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
    print(f"Schema auth da tao/xac nhan tai: {DB_PATH}")

