import os
import sys
import json
import datetime as dt
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


# 28/07/2026: PHUC HOI ham nay - ban main.py truoc do (viet lai cho dashboard C-Level) da lam mat
# buoc load .env, khien os.environ["ANTHROPIC_API_KEY"] (doc trong nl2sql.py::ask()) nem KeyError
# ngay khi nguoi dung hoi cau dau tien ("Loi he thong: 'ANTHROPIC_API_KEY'"). PHAI goi TRUOC khi
# import auth/conversation_memory/nl2sql vi cac module do co the doc bien moi truong ngay luc import.
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
load_env()

from auth import (
    init_schema as init_auth_schema,
    verify_login,
    create_session,
    get_user_by_session,
    delete_session,
    get_name_by_username,
    generate_password,
    admin_create_user,
    set_password,
    approve_user,
    toggle_user_active,
    list_users,
    delete_all_sessions_for_user,
    get_user_by_email_or_username,
    get_subordinate_usernames,
)
from mailer import send_password_email
from conversation_memory import (
    register_session,
    list_sessions,
    delete_session as delete_conversation_session,
    get_session_history,
)
from nl2sql import ask
from query_engine import _write_log
from pricing import USD_TO_VND_RATE

init_auth_schema()

app = FastAPI(title="DNH AI Chatbot API", version="1.0.0")

API_KEY = os.getenv("BACKEND_API_KEY", "").strip()
ALLOWED_EMAIL_DOMAIN = "namhapharma.com"

# Rate limiting cho dang ky / quen mat khau
_EMAIL_AUTH_ATTEMPTS = defaultdict(list)
_IP_AUTH_ATTEMPTS = defaultdict(list)


def require_api_key(x_api_key: str = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "API Key khong hop le")


def require_user(authorization: str = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Yeu cau dang nhap (thieu Bearer token)")
    token = authorization.split(" ", 1)[1]
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(401, "Phien dang nhap het han hoac khong hop le")
    return user


def require_approved_user(user: dict = Depends(require_user)) -> dict:
    """Fail-closed dependency cho moi endpoint du lieu: Yeu cau tai khoan da duoc duyet (status=='approved') va active."""
    if user.get("is_active") != 1:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Quản trị viên.")
    if user.get("status") == "pending":
        raise HTTPException(403, "Tài khoản của bạn đang ở trạng thái CHỜ DUYỆT. Quản trị viên chưa gán vai trò và phạm vi truy cập cho bạn.")
    return user


_USER_LAST_REQUEST = {}
RATE_LIMIT_INTERVAL_SEC = 2.0


def _check_rate_limit(username: str):
    now = dt.datetime.now()
    last = _USER_LAST_REQUEST.get(username)
    if last and (now - last).total_seconds() < RATE_LIMIT_INTERVAL_SEC:
        raise HTTPException(429, "Thao tac qua nhanh, vui long cho 2 giay")
    _USER_LAST_REQUEST[username] = now


def _check_public_auth_rate_limit(email: str, client_ip: str = "local"):
    """Rate limit rieng cho /auth/register va /auth/forgot-password: Toi da 3 lan/email/gio va 10 lan/IP/gio."""
    now = dt.datetime.now()
    cutoff = now - dt.timedelta(hours=1)

    _EMAIL_AUTH_ATTEMPTS[email] = [t for t in _EMAIL_AUTH_ATTEMPTS[email] if t > cutoff]
    _IP_AUTH_ATTEMPTS[client_ip] = [t for t in _IP_AUTH_ATTEMPTS[client_ip] if t > cutoff]

    if len(_EMAIL_AUTH_ATTEMPTS[email]) >= 3:
        raise HTTPException(429, "Bạn đã gửi yêu cầu quá 3 lần trong 1 giờ cho email này. Vui lòng thử lại sau.")
    if len(_IP_AUTH_ATTEMPTS[client_ip]) >= 10:
        raise HTTPException(429, "Thao tác quá nhiều lần từ IP này. Vui lòng thử lại sau 1 giờ.")

    _EMAIL_AUTH_ATTEMPTS[email].append(now)
    _IP_AUTH_ATTEMPTS[client_ip].append(now)


def _require_session_access(session_id: str, user: dict):
    """Chi dung cho DOC (GET /history) - admin_ops & c_level duoc xem tat ca, regional_director xem duoc cua QLV thuoc scope."""
    from conversation_memory import get_session_owner
    owner = get_session_owner(session_id)
    if owner is None:
        return
    role = user.get("role")
    if role in ("c_level", "admin_ops"):
        return
    if owner == user["username"]:
        return
    if role == "regional_director":
        subordinates = get_subordinate_usernames(user)
        if subordinates and owner in subordinates:
            return
    raise HTTPException(403, "Khong co quyen truy cap cuoc tro chuyen nay")


def _require_session_write_access(session_id: str, user: dict):
    """Dung cho GHI vao phien (POST /chat, POST /clear) - KHONG co ngoai le cho C-Level, kem ca
    DELETE /sessions da co san logic tuong tu ben duoi.
    Phat hien 03/08/2026: _require_session_access() (chi danh cho doc) dang bi tai su dung cho ca
    /chat va /clear, khien C-Level GUI DUOC tin nhan vao phien cua nguoi khac (messages khong co cot
    nguoi gui rieng - tin nhan chen vao se LAN VAO lich su that cua ho, khong co dau hieu phan biet -
    tuong duong mao danh) va XOA DUOC toan bo lich su cua ho (clear_session con xoa ca dong sessions).
    Xem lich su la giam sat hop le; gui tin/xoa thay nguoi khac thi khong, phai chan tuyet doi bat ke
    vai tro."""
    from conversation_memory import get_session_owner
    owner = get_session_owner(session_id)
    if owner is not None and owner != user["username"]:
        raise HTTPException(403, "Chi chu so huu moi duoc gui tin nhan hoac xoa cuoc tro chuyen nay. "
                                  "C-Level chi co quyen XEM lich su, khong duoc thao tac thay nguoi khac.")


# --- PYDANTIC SCHEMAS ---

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    name: Optional[str]
    role: str
    scope_value: Optional[str]
    scope_channel: Optional[str]
    status: Optional[str] = 'approved'
    email: Optional[str] = None


class UserInfo(BaseModel):
    username: str
    name: Optional[str]
    role: str
    scope_value: Optional[str]
    scope_channel: Optional[str]
    status: Optional[str] = 'approved'
    email: Optional[str] = None


class RegisterRequest(BaseModel):
    email: str
    name: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ApproveUserRequest(BaseModel):
    role: str
    scope_value: Optional[str] = None
    employee_code: Optional[str] = None
    scope_channel: Optional[str] = None


class ChatRequest(BaseModel):
    question: str
    session_id: str


class ChatResponse(BaseModel):
    answer: str
    sql_used: list[str]
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    row_count: Optional[int] = None


class SessionSummary(BaseModel):
    session_id: str
    title: Optional[str]
    owner_username: str
    owner_name: Optional[str]
    created_at: str
    updated_at: str


class HistoryMessage(BaseModel):
    role: str
    content: str


# --- ENDPOINTS ---

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": dt.datetime.now().isoformat()}


@app.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(require_api_key)])
def login(req: LoginRequest):
    user = verify_login(req.username, req.password)
    if not user:
        raise HTTPException(401, "Tài khoản hoặc mật khẩu không chính xác")
    if isinstance(user, dict) and user.get("error") == "wrong_password":
        raise HTTPException(401, "Tài khoản hoặc mật khẩu không chính xác")

    if user.get("is_active") != 1:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Quản trị viên.")

    token = create_session(user["id"])
    _write_log({
        "ts": dt.datetime.now().isoformat(),
        "username": user["username"],
        "question": "🔑 Đăng nhập hệ thống",
        "sql": "<auth:login>",
        "status": "ok"
    })
    return LoginResponse(
        token=token,
        username=user["username"],
        name=user["name"],
        role=user["role"],
        scope_value=user["scope_value"],
        scope_channel=user["scope_channel"],
        status=user.get("status", "approved"),
        email=user.get("email"),
    )


class AdminCreateUserRequest(BaseModel):
    username: str
    password: Optional[str] = None       # Neu khong truyen -> sinh ngau nhien
    name: Optional[str] = None
    email: Optional[str] = None          # Optional, khong bat buoc nua
    role: str = "qlv"
    scope_value: Optional[str] = None
    employee_code: Optional[str] = None
    scope_channel: Optional[str] = None


@app.post("/auth/register", dependencies=[Depends(require_api_key)])
def register(req: RegisterRequest):
    """CO TINH VO HIEU HOA - giu endpoint de tra loi ro rang neu con client cu goi vao, thay vi 404."""
    raise HTTPException(403, "Chức năng tự đăng ký đã bị tắt. Vui lòng liên hệ Quản trị viên để được cấp tài khoản (username + mật khẩu).")


@app.post("/auth/forgot-password", dependencies=[Depends(require_api_key)])
def forgot_password(req: ForgotPasswordRequest, request: Request):
    if not req.email or not req.email.strip():
        raise HTTPException(400, "Vui lòng nhập Email công ty")

    clean_email = req.email.strip().lower()
    parts = clean_email.split("@")
    if len(parts) != 2 or parts[1] != ALLOWED_EMAIL_DOMAIN:
        raise HTTPException(400, f"Chức năng chỉ hỗ trợ email công ty Dược Nam Hà (@{ALLOWED_EMAIL_DOMAIN})")

    client_ip = request.client.host if request.client else "local"
    _check_public_auth_rate_limit(clean_email, client_ip)

    user = get_user_by_email_or_username(clean_email)
    if user:
        # 29/07/2026 - THU TU QUAN TRONG: gui mail TRUOC, doi mat khau trong DB SAU.
        # Lam nguoc lai (doi truoc, gui sau) thi khi SMTP loi - sai app password, mang chap chon,
        # Office365 chan - mat khau da bi thay doi nhung nguoi dung KHONG nhan duoc mat khau moi,
        # tu khoa chinh minh ra khoi tai khoan va bat buoc phai nho admin can thiep.
        new_pwd = generate_password(10)
        if send_password_email(clean_email, new_pwd, is_reset=True):
            set_password(clean_email, new_pwd)
            delete_all_sessions_for_user(user["id"])
            _write_log({
                "ts": dt.datetime.now().isoformat(),
                "username": user["username"],
                "question": f"🔑 Quên/Reset mật khẩu thành công qua email ({clean_email})",
                "sql": "<auth:forgot_password>",
                "status": "ok"
            })
        else:
            # Gui that bai -> KHONG doi gi ca, mat khau cu van dung duoc binh thuong.
            # Chi ghi nhan su co (KHONG ghi mat khau) de admin doi chieu khi co nguoi bao khong nhan duoc mail.
            print(f"[FORGOT-PASSWORD] Gui mail that bai cho {clean_email} - GIU NGUYEN mat khau cu")
            _write_log({
                "ts": dt.datetime.now().isoformat(),
                "username": user["username"],
                "question": f"⚠️ Gửi email reset mật khẩu thất bại ({clean_email})",
                "sql": "<auth:forgot_password_failed>",
                "status": "error"
            })

    # Luon tra CUNG MOT thong bao, du email co ton tai hay khong va du gui mail thanh cong hay khong.
    # Neu phan biet (vd tra 500 khi email co that), ke ngoai chi can thu lan luot vai email roi xem
    # phan hoi nao khac di la do duoc chinh xac ai dang co tai khoan trong he thong.
    return {"ok": True, "message": "Nếu email thuộc hệ thống Dược Nam Hà, mật khẩu mới đã được gửi đến hộp thư Outlook của bạn."}


@app.post("/auth/change-password", dependencies=[Depends(require_api_key)])
def change_password(req: ChangePasswordRequest, user: dict = Depends(require_user)):
    if not req.current_password or not req.new_password:
        raise HTTPException(400, "Vui lòng nhập đầy đủ mật khẩu hiện tại và mật khẩu mới")

    if len(req.new_password) < 6:
        raise HTTPException(400, "Mật khẩu mới phải có tối thiểu 6 ký tự")

    # Xác thực mật khẩu cũ
    verified = verify_login(user["username"], req.current_password)
    if not verified or (isinstance(verified, dict) and verified.get("error") == "wrong_password"):
        raise HTTPException(400, "Mật khẩu hiện tại không chính xác")

    set_password(user["username"], req.new_password)
    _write_log({
        "ts": dt.datetime.now().isoformat(),
        "username": user["username"],
        "question": "🔐 Đổi mật khẩu tài khoản thành công",
        "sql": "<auth:change_password>",
        "status": "ok"
    })
    return {"ok": True, "message": "Đổi mật khẩu thành công!"}


@app.post("/auth/logout", dependencies=[Depends(require_api_key)])
def logout(authorization: str = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        delete_session(token)
    return {"ok": True}


@app.get("/auth/me", response_model=UserInfo, dependencies=[Depends(require_api_key)])
def me(user: dict = Depends(require_user)):
    return UserInfo(
        username=user["username"],
        name=user["name"],
        role=user["role"],
        scope_value=user["scope_value"],
        scope_channel=user["scope_channel"],
        status=user.get("status", "approved"),
        email=user.get("email"),
    )


# --- ADMIN ENDPOINTS (Chỉ dành cho C-Level đã được duyệt) ---

@app.get("/admin/users", dependencies=[Depends(require_api_key)])
def get_users_list(status: Optional[str] = Query(default=None), user: dict = Depends(require_approved_user)):
    if user["role"] not in ("c_level", "admin_ops"):
        raise HTTPException(403, "Chi Quản trị viên mới có quyền xem danh sách tài khoản")
    return list_users(status=status)


@app.post("/admin/users/create", dependencies=[Depends(require_api_key)])
def create_user_by_admin(req: AdminCreateUserRequest, user: dict = Depends(require_approved_user)):
    if user["role"] not in ("c_level", "admin_ops"):
        raise HTTPException(403, "Chi Quản trị viên mới có quyền tạo tài khoản mới")

    clean_username = req.username.strip().lower()
    existing = get_user_by_email_or_username(clean_username)
    if existing:
        raise HTTPException(400, f"Tài khoản hoặc username '{clean_username}' đã tồn tại")

    user_info, generated_pwd = admin_create_user(
        username=clean_username,
        name=req.name,
        role=req.role,
        scope_value=req.scope_value if req.role != "c_level" else None,
        employee_code=req.employee_code if req.role == "qlv" else None,
        scope_channel=req.scope_channel,
        email=req.email.strip().lower() if req.email else None,
        password=req.password,
    )

    if req.email and req.email.strip():
        send_password_email(
            to_email=req.email.strip(),
            user_name=req.name or clean_username,
            password=generated_pwd
        )

    _write_log({
        "ts": dt.datetime.now().isoformat(),
        "username": user["username"],
        "question": f"👤 Admin tạo tài khoản mới: {clean_username} (vai trò {req.role})",
        "sql": "<admin:create_user>",
        "status": "ok"
    })

    return {
        "ok": True,
        "message": f"Khởi tạo tài khoản {clean_username} thành công!",
        "username": clean_username,
        "email": req.email,
        "generated_password": generated_pwd if not req.password else None
    }


@app.post("/admin/users/{username}/approve", dependencies=[Depends(require_api_key)])
def approve_user_endpoint(username: str, req: ApproveUserRequest, user: dict = Depends(require_approved_user)):
    if user["role"] not in ("c_level", "admin_ops"):
        raise HTTPException(403, "Chi Quản trị viên mới có quyền phê duyệt tài khoản")

    success = approve_user(username, req.role, req.scope_value, req.employee_code, req.scope_channel)
    if not success:
        raise HTTPException(404, "Không tìm thấy tài khoản để phê duyệt")
    _write_log({
        "ts": dt.datetime.now().isoformat(),
        "username": user["username"],
        "question": f"✅ Phê duyệt tài khoản {username} (vai trò {req.role})",
        "sql": "<admin:approve_user>",
        "status": "ok"
    })
    return {"ok": True, "message": f"Phê duyệt tài khoản {username} thành công"}


@app.post("/admin/users/{username}/toggle-active", dependencies=[Depends(require_api_key)])
def toggle_user_active_endpoint(username: str, user: dict = Depends(require_approved_user)):
    if user["role"] not in ("c_level", "admin_ops"):
        raise HTTPException(403, "Chi Quản trị viên mới có quyền bật/tắt tài khoản")

    res = toggle_user_active(username)
    if not res:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    _write_log({
        "ts": dt.datetime.now().isoformat(),
        "username": user["username"],
        "question": f"🔒 Bật/Tắt khóa tài khoản {username} ({'Mở khóa' if res.get('is_active') == 1 else 'Khóa'})",
        "sql": "<admin:toggle_active>",
        "status": "ok"
    })
    return {"ok": True, "result": res}


# --- DATA ENDPOINTS (Được bảo vệ bằng require_approved_user) ---

@app.get("/history/{session_id}", response_model=list[HistoryMessage], dependencies=[Depends(require_api_key)])
def get_history(session_id: str, user: dict = Depends(require_approved_user)):
    _require_session_access(session_id, user)
    return get_session_history(session_id)


@app.get("/sessions", response_model=list[SessionSummary], dependencies=[Depends(require_api_key)])
def get_sessions(user: dict = Depends(require_approved_user)):
    role = user["role"]
    if role in ("c_level", "admin_ops"):
        rows = list_sessions(None)
    elif role == "regional_director":
        subordinates = get_subordinate_usernames(user)
        all_rows = list_sessions(None)
        rows = [r for r in all_rows if subordinates and r["owner_username"] in subordinates]
    else:
        rows = list_sessions(user["username"])

    out = []
    for r in rows:
        owner_name = get_name_by_username(r["owner_username"]) if role in ("c_level", "admin_ops", "regional_director") else user.get("name")
        out.append(SessionSummary(
            session_id=r["session_id"],
            title=r["title"],
            owner_username=r["owner_username"],
            owner_name=owner_name,
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        ))
    return out


@app.delete("/sessions/{session_id}", dependencies=[Depends(require_api_key)])
def delete_session_endpoint(session_id: str, user: dict = Depends(require_approved_user)):
    _require_session_write_access(session_id, user)
    delete_conversation_session(session_id)
    return {"ok": True}


@app.post("/clear/{session_id}", dependencies=[Depends(require_api_key)])
def clear(session_id: str, user: dict = Depends(require_approved_user)):
    _require_session_write_access(session_id, user)
    from conversation_memory import clear_session
    clear_session(session_id)
    return {"ok": True}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest, user: dict = Depends(require_approved_user)):
    if user["role"] == "admin_ops":
        raise HTTPException(403, "Tài khoản Admin Vận Hành (admin.dnh) chỉ dùng để quản trị hệ thống, không có quyền truy vấn dữ liệu kinh doanh qua Chatbot.")
    if not req.question or not req.question.strip():
        raise HTTPException(400, "Cau hoi khong duoc de trong")
    _check_rate_limit(user["username"])
    _require_session_write_access(req.session_id, user)
    try:
        scope_area_code = user["scope_value"] if user["role"] in ("regional_director", "qlv") else None
        scope_employee_code = user["employee_code"] if user["role"] == "qlv" else None
        scope_channel = user.get("scope_channel")
        result = ask(req.question, session_id=req.session_id, username=user["username"],
                     scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                     scope_channel=scope_channel, scope_role=user["role"])
        register_session(req.session_id, user["username"], req.question)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Loi he thong: {str(e)[:300]}")

    lr = result.get("last_result") or {}
    is_raw_sql = lr.get("ok") and "columns" in lr
    return ChatResponse(
        answer=result["answer"],
        sql_used=result["sql_used"],
        columns=lr.get("columns") if is_raw_sql else None,
        rows=lr.get("rows") if is_raw_sql else None,
        row_count=lr.get("row_count") if is_raw_sql else None,
    )


@app.get("/audit-logs", dependencies=[Depends(require_api_key)])
def get_audit_logs_dashboard(
    days: int = Query(default=30, ge=1, le=365),
    date: Optional[str] = Query(default=None, description="Loc theo 1 ngay cu the (YYYY-MM-DD). Neu truyen, bo qua tham so days."),
    limit: int = Query(default=200, ge=1, le=1000),
    user_filter: Optional[str] = None,
    role_filter: Optional[str] = None,
    user: dict = Depends(require_approved_user)
):
    if user["role"] not in ("c_level", "admin_ops"):
        raise HTTPException(403, "Chi Quản trị viên / C-Level mới có quyền xem Dashboard Audit Log")

    _LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    AUDIT_LOG_PATH = os.path.join(_LOGS_DIR, "audit_log.jsonl")
    COST_LOG_PATH = os.path.join(_LOGS_DIR, "cost_log.jsonl")

    # 06/08/2026: Cho xem theo 1 NGAY CU THE thay vi chi "N ngay gan nhat". Neu co `date`, no thang
    # the cho `days` - chi giu lai entry roi vao dung ngay do (00:00:00 -> 23:59:59.999999).
    target_date = None
    if date:
        try:
            target_date = dt.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, "Tham so date khong hop le, dung dinh dang YYYY-MM-DD")

    date_start = date_end = None
    cutoff = None
    if target_date:
        date_start = dt.datetime.combine(target_date, dt.time.min)
        date_end = dt.datetime.combine(target_date, dt.time.max)
    elif days:
        cutoff = dt.datetime.now() - dt.timedelta(days=days)

    def _passes_time_filter(ts_str):
        if not ts_str:
            return True
        try:
            ts_dt = dt.datetime.fromisoformat(ts_str)
        except Exception:
            return True
        if target_date:
            return date_start <= ts_dt <= date_end
        if cutoff:
            return ts_dt >= cutoff
        return True

    audit_entries = []
    if os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    audit_entries.append(json.loads(line))
                except Exception:
                    continue

    # 05/08/2026: Nạp bổ sung lịch sử Đổi MK, Đăng nhập & Khởi tạo tài khoản từ auth.db
    # để hiển thị lại toàn bộ các sự kiện trước đây (khi chưa có file audit_log)
    # 06/08/2026: cung xay username -> role tu chinh danh sach nay de phuc vu bo loc "Chuc vu" -
    # dung 1 lan goi list_users(), khong query rieng.
    _username_to_role: dict = {}
    try:
        from auth import list_users
        all_u = list_users()
        for u in all_u:
            uname = u.get("username")
            if uname:
                _username_to_role[uname] = (u.get("role") or "").strip()
            if u.get("created_at"):
                audit_entries.append({
                    "ts": u["created_at"],
                    "username": uname,
                    "question": f"👤 Khởi tạo tài khoản: {uname}",
                    "sql": "<auth:create_user>",
                    "status": "ok"
                })
            if u.get("password_changed_at"):
                audit_entries.append({
                    "ts": u["password_changed_at"],
                    "username": uname,
                    "question": "🔐 Đổi mật khẩu tài khoản thành công",
                    "sql": "<auth:change_password>",
                    "status": "ok"
                })
            if u.get("last_login_at"):
                audit_entries.append({
                    "ts": u["last_login_at"],
                    "username": uname,
                    "question": "🔑 Đăng nhập hệ thống",
                    "sql": "<auth:login>",
                    "status": "ok"
                })
    except Exception as ex:
        print("[AUDIT-LOG] Lỗi nạp lịch sử từ auth.db:", ex)

    # Sắp xếp toàn bộ log theo thời gian mới nhất lên đầu
    audit_entries.sort(key=lambda x: x.get("ts") or "", reverse=True)

    cost_by_session = defaultdict(lambda: {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0, "calls": 0})
    cost_direct_by_user = defaultdict(lambda: {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0})
    # 03/08/2026: Per-question cost - nhom theo (session_id, question_preview) de hien chi phi TUNG CAU
    cost_per_question = defaultdict(lambda: {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0, "total_tokens": 0, "api_calls": 0,
        "username": "", "first_ts": None})
    # Cac phien da duoc quy chi phi TRUC TIEP cho nguoi dung (log co username). Vong duyet audit ben
    # duoi phai BO QUA chung khi cong vao user_stats, neu khong se cong hai lan -> chi phi gap doi.
    sessions_attributed_directly = set()
    grand_cost_usd = 0.0
    grand_input_tokens = 0
    grand_output_tokens = 0
    grand_cache_tokens = 0
    if os.path.exists(COST_LOG_PATH):
        with open(COST_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    c = json.loads(line)
                except Exception:
                    continue
                if not _passes_time_filter(c.get("ts")):
                    continue
                cost = c.get("cost_usd", 0.0) or 0.0
                it = c.get("input_tokens", 0) or 0
                ot = c.get("output_tokens", 0) or 0
                cr = c.get("cache_read_tokens", 0) or 0
                cw = c.get("cache_write_tokens", 0) or 0
                grand_cost_usd += cost
                grand_input_tokens += it
                grand_output_tokens += ot
                grand_cache_tokens += cr + cw

                # LUON gom theo phien - day la nguon so cho bang chi tiet TUNG CAU HOI. Truoc 31/07
                # khoi nay nam SAU mot "continue" cua nhanh username, ma tu 20bec9d (29/07) thi log
                # NAO cung co username, nen cost_by_session vinh vien rong va moi dong trong bang deu
                # hien 0 token / 0 d (tong theo nguoi va tong toan he thong van dung, chi bang chi
                # tiet chet). Dat truoc nhanh username de khong bao gio bi bo qua nua.
                sid = c.get("session_id")
                if sid:
                    cost_by_session[sid]["cost_usd"] += cost
                    cost_by_session[sid]["input_tokens"] += it
                    cost_by_session[sid]["output_tokens"] += ot
                    cost_by_session[sid]["cache_tokens"] += cr + cw
                    cost_by_session[sid]["total_tokens"] += it + ot + cr + cw
                    cost_by_session[sid]["calls"] += 1
                    # 03/08/2026: gom chi phi theo tung cau hoi (session + question_preview)
                    _qp = c.get("question_preview", "")
                    _qk = (sid, _qp)
                    _cpq = cost_per_question[_qk]
                    _cpq["cost_usd"] += cost
                    _cpq["input_tokens"] += it
                    _cpq["output_tokens"] += ot
                    _cpq["cache_read_tokens"] += cr
                    _cpq["cache_write_tokens"] += cw
                    _cpq["total_tokens"] += it + ot + cr + cw
                    _cpq["api_calls"] += 1
                    if not _cpq["username"]:
                        _cpq["username"] = (c.get("username") or "").strip()
                    if not _cpq["first_ts"]:
                        _cpq["first_ts"] = c.get("ts")

                uname_direct = (c.get("username") or "").strip()
                if uname_direct:
                    d = cost_direct_by_user[uname_direct]
                    d["cost_usd"] += cost
                    d["input_tokens"] += it
                    d["output_tokens"] += ot
                    d["cache_tokens"] += cr + cw
                    d["total_tokens"] += it + ot + cr + cw
                    if sid:
                        sessions_attributed_directly.add(sid)

    # 03/08/2026: Pre-compute so lenh SQL per question de hien thi
    _sql_count_by_q = defaultdict(int)
    for _e in audit_entries:
        _qk = (_e.get("session_id") or "", (_e.get("question") or "")[:120])
        _sql_count_by_q[_qk] += 1

    filtered_logs = []
    user_stats = defaultdict(lambda: {"query_count": 0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0, "cost_usd": 0.0})
    total_cost_usd = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_tokens_attributed = 0

    target_user_str = (user_filter or "").strip().lower()
    target_role_str = (role_filter or "").strip().lower()
    _seen_q = set()  # 03/08/2026: dedup by (session_id, question[:120])

    for e in audit_entries:
        uname = e.get("username") or "unknown"
        if target_user_str and target_user_str not in ("all", ""):
            if target_user_str not in uname.lower():
                continue
        if target_role_str and target_role_str != "all":
            if (_username_to_role.get(uname) or "").lower() != target_role_str:
                continue
        if not _passes_time_filter(e.get("ts")):
            continue

        sid = e.get("session_id") or ""
        # 06/08/2026: KHOI PHUC dong nay - commit d705ad9 (05/08) khi them tab Security Audit Log da
        # vo tinh GHI DE dong dinh nghia q_key bang 2 dong sql_str/is_security_event ben duoi, trong
        # khi q_key van con duoc dung o 4 cho phia sau. Hau qua: gap dong log truy van thuong dau tien
        # la NameError -> endpoint tra 500 -> dashboard Audit Log/Chi phi TRONG HOAN TOAN va frontend
        # bao "Unexpected token 'I', Internal S... is not valid JSON". Phai khop dung dang khoa cua
        # cost_per_question (session_id, question_preview[:120]) thi moi tra ve dung chi phi tung cau.
        q_key = (sid, (e.get("question") or "")[:120])
        sql_str = e.get("sql") or ""
        is_security_event = sql_str.startswith("<auth:") or sql_str.startswith("<admin:")

        # Security/Auth events (login, change_password, create_user...) NEVER deduplicated!
        if not is_security_event and q_key in _seen_q:
            continue
        if not is_security_event:
            _seen_q.add(q_key)

        cpq = cost_per_question.get(q_key, {})
        c_usd = cpq.get("cost_usd", 0.0)
        c_it = cpq.get("input_tokens", 0)
        c_ot = cpq.get("output_tokens", 0)
        c_cr = cpq.get("cache_read_tokens", 0)
        c_cw = cpq.get("cache_write_tokens", 0)
        c_tt = cpq.get("total_tokens", c_it + c_ot + c_cr + c_cw)

        display_name = get_name_by_username(uname) or uname

        user_stats[uname]["query_count"] += 1
        user_stats[uname]["display_name"] = display_name

        # Chi phi per-question (khong con gom theo session de tranh cong trung)
        if sid and sid not in sessions_attributed_directly:
            user_stats[uname]["input_tokens"] += c_it
            user_stats[uname]["output_tokens"] += c_ot
            user_stats[uname]["cache_tokens"] += c_cr + c_cw
            user_stats[uname]["total_tokens"] += c_tt
            user_stats[uname]["cost_usd"] += c_usd
            total_cost_usd += c_usd
            total_input_tokens += c_it
            total_output_tokens += c_ot
            total_cache_tokens_attributed += c_cr + c_cw

        filtered_logs.append({
            "ts": e.get("ts"),
            "username": uname,
            "user_name": display_name,
            "question": e.get("question"),
            "sql": e.get("sql"),
            "status": e.get("status", "success"),
            "duration_ms": e.get("duration_ms"),
            "session_id": sid,
            # 03/08/2026: Per-question tokens/cost (khong con per-session)
            "input_tokens": c_it,
            "output_tokens": c_ot,
            "cache_read_tokens": c_cr,
            "cache_write_tokens": c_cw,
            "total_tokens": c_tt,
            "cost_usd": round(c_usd, 6),
            "cost_vnd": round(c_usd * USD_TO_VND_RATE, 2),
            "api_calls": cpq.get("api_calls", 0),
            "sql_count": _sql_count_by_q.get(q_key, 0),
            # Backward compat: giu ten cu de frontend khong bi vo
            "session_input_tokens": c_it,
            "session_output_tokens": c_ot,
            "session_total_tokens": c_tt,
            "session_cost_usd": round(c_usd, 6),
            "session_cost_vnd": round(c_usd * USD_TO_VND_RATE, 2),
        })

    # 03/08/2026: Them cau hoi chi co trong cost_log ma KHONG co trong audit_log
    # (vd nguoi dung goi "Chao bot" - AI tra loi thang, khong chay SQL nao)
    for _qk2, _cpq2 in cost_per_question.items():
        if _qk2 in _seen_q:
            continue
        _sid2, _qp2 = _qk2
        _uname2 = _cpq2.get("username") or "unknown"
        if target_user_str and target_user_str not in ("all", ""):
            if target_user_str not in _uname2.lower():
                continue
        if target_role_str and target_role_str != "all":
            if (_username_to_role.get(_uname2) or "").lower() != target_role_str:
                continue
        if not _passes_time_filter(_cpq2.get("first_ts")):
            continue
        _seen_q.add(_qk2)
        _dn2 = get_name_by_username(_uname2) or _uname2
        user_stats[_uname2]["query_count"] += 1
        if not user_stats[_uname2].get("display_name"):
            user_stats[_uname2]["display_name"] = _dn2
        _c2 = _cpq2.get("cost_usd", 0.0)
        filtered_logs.append({
            "ts": _cpq2.get("first_ts"),
            "username": _uname2,
            "user_name": _dn2,
            "question": _qp2,
            "sql": None,
            "status": "no_sql",
            "duration_ms": None,
            "session_id": _sid2,
            "input_tokens": _cpq2.get("input_tokens", 0),
            "output_tokens": _cpq2.get("output_tokens", 0),
            "cache_read_tokens": _cpq2.get("cache_read_tokens", 0),
            "cache_write_tokens": _cpq2.get("cache_write_tokens", 0),
            "total_tokens": _cpq2.get("total_tokens", 0),
            "cost_usd": round(_c2, 6),
            "cost_vnd": round(_c2 * USD_TO_VND_RATE, 2),
            "api_calls": _cpq2.get("api_calls", 0),
            "sql_count": 0,
            "session_input_tokens": _cpq2.get("input_tokens", 0),
            "session_output_tokens": _cpq2.get("output_tokens", 0),
            "session_total_tokens": _cpq2.get("total_tokens", 0),
            "session_cost_usd": round(_c2, 6),
            "session_cost_vnd": round(_c2 * USD_TO_VND_RATE, 2),
        })

    filtered_logs.sort(key=lambda x: x.get("ts", ""), reverse=True)
    recent_logs = filtered_logs[:limit]

    for uname, d in cost_direct_by_user.items():
        st = user_stats[uname]
        st["cost_usd"] += d["cost_usd"]
        st["input_tokens"] += d["input_tokens"]
        st["output_tokens"] += d["output_tokens"]
        st["cache_tokens"] += d["cache_tokens"]
        st["total_tokens"] += d["total_tokens"]
        st.setdefault("query_count", 0)
        if "display_name" not in st:
            st["display_name"] = get_name_by_username(uname) or uname
        total_cost_usd += d["cost_usd"]
        total_input_tokens += d["input_tokens"]
        total_output_tokens += d["output_tokens"]
        total_cache_tokens_attributed += d["cache_tokens"]

    user_breakdown = []
    for uname, s in sorted(user_stats.items(), key=lambda x: -x[1]["cost_usd"]):
        user_breakdown.append({
            "username": uname,
            "user_name": s.get("display_name", uname),
            "query_count": s["query_count"],
            "input_tokens": s["input_tokens"],
            "output_tokens": s["output_tokens"],
            "cache_tokens": s["cache_tokens"],
            "total_tokens": s["total_tokens"],
            "cost_usd": round(s["cost_usd"], 6),
            "cost_vnd": round(s["cost_usd"] * USD_TO_VND_RATE, 2),
            "is_unattributed": False,
        })

    unattributed = grand_cost_usd - total_cost_usd
    if unattributed > 1e-9:
        un_it = max(0, grand_input_tokens - total_input_tokens)
        un_ot = max(0, grand_output_tokens - total_output_tokens)
        un_ct = max(0, grand_cache_tokens - total_cache_tokens_attributed)
        user_breakdown.append({
            "username": "(chưa quy được)",
            "user_name": "Chưa quy được cho người dùng",
            "query_count": 0,
            "input_tokens": un_it,
            "output_tokens": un_ot,
            "cache_tokens": un_ct,
            "total_tokens": un_it + un_ot + un_ct,
            "cost_usd": round(unattributed, 6),
            "cost_vnd": round(unattributed * USD_TO_VND_RATE, 2),
            "is_unattributed": True,
        })

    return {
        "summary": {
            "total_cost_usd": round(grand_cost_usd, 6),
            "total_cost_vnd": round(grand_cost_usd * USD_TO_VND_RATE, 2),
            "attributed_cost_usd": round(total_cost_usd, 6),
            "unattributed_cost_usd": round(max(0.0, unattributed), 6),
            "total_input_tokens": grand_input_tokens,
            "total_output_tokens": grand_output_tokens,
            "total_cache_tokens": grand_cache_tokens,
            "grand_total_tokens": grand_input_tokens + grand_output_tokens + grand_cache_tokens,
            "total_queries": len(filtered_logs),
            "unique_users_count": len([u for u in user_stats if u and u.lower() != "unknown"]),
            "days": days,
            "date": target_date.strftime("%Y-%m-%d") if target_date else None
        },
        "user_breakdown": user_breakdown,
        "logs": recent_logs
    }


@app.get("/audit-logs/weekly", dependencies=[Depends(require_api_key)])
def get_weekly_audit_dashboard(
    week_offset: int = Query(default=0, ge=-52, le=52),
    user: dict = Depends(require_approved_user)
):
    if user["role"] not in ("c_level", "admin_ops"):
        raise HTTPException(403, "Chỉ Quản trị viên / C-Level mới có quyền xem Dashboard Chi phí AI")

    _LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    COST_LOG_PATH = os.path.join(_LOGS_DIR, "cost_log.jsonl")

    now = dt.datetime.now()
    current_monday = now.date() - dt.timedelta(days=now.weekday())
    target_monday = current_monday + dt.timedelta(weeks=week_offset)
    target_sunday = target_monday + dt.timedelta(days=6)

    target_start_dt = dt.datetime.combine(target_monday, dt.time.min)
    target_end_dt = dt.datetime.combine(target_sunday, dt.time.max)

    day_names = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    daily_data = {
        i: {
            "day_index": i,
            "day_name": day_names[i],
            "date_str": (target_monday + dt.timedelta(days=i)).strftime("%Y-%m-%d"),
            "display_date": (target_monday + dt.timedelta(days=i)).strftime("%d/%m"),
            "is_today": (target_monday + dt.timedelta(days=i)) == now.date(),
            "query_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_vnd": 0.0,
        }
        for i in range(7)
    }

    user_weekly_cost = defaultdict(lambda: {"query_count": 0, "total_tokens": 0, "cost_usd": 0.0})

    if os.path.exists(COST_LOG_PATH):
        with open(COST_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    c = json.loads(line)
                    ts_str = c.get("ts")
                    if not ts_str:
                        continue
                    entry_dt = dt.datetime.fromisoformat(ts_str)
                    if target_start_dt <= entry_dt <= target_end_dt:
                        day_idx = (entry_dt.date() - target_monday).days
                        if 0 <= day_idx <= 6:
                            cost = c.get("cost_usd", 0.0) or 0.0
                            it = c.get("input_tokens", 0) or 0
                            ot = c.get("output_tokens", 0) or 0
                            cr = c.get("cache_read_tokens", 0) or 0
                            cw = c.get("cache_write_tokens", 0) or 0

                            d = daily_data[day_idx]
                            d["query_count"] += 1
                            d["input_tokens"] += it
                            d["output_tokens"] += ot
                            d["cache_tokens"] += cr + cw
                            d["total_tokens"] += it + ot + cr + cw
                            d["cost_usd"] += cost
                            d["cost_vnd"] += cost * USD_TO_VND_RATE

                            u = (c.get("username") or "unknown").strip()
                            user_weekly_cost[u]["query_count"] += 1
                            user_weekly_cost[u]["total_tokens"] += it + ot + cr + cw
                            user_weekly_cost[u]["cost_usd"] += cost
                except Exception:
                    continue

    daily_list = []
    total_week_cost_usd = 0.0
    total_week_cost_vnd = 0.0
    total_week_tokens = 0
    total_week_queries = 0

    for i in range(7):
        item = daily_data[i]
        item["cost_usd"] = round(item["cost_usd"], 6)
        item["cost_vnd"] = round(item["cost_vnd"], 2)
        total_week_cost_usd += item["cost_usd"]
        total_week_cost_vnd += item["cost_vnd"]
        total_week_tokens += item["total_tokens"]
        total_week_queries += item["query_count"]
        daily_list.append(item)

    user_breakdown = []
    for u, stats in user_weekly_cost.items():
        user_breakdown.append({
            "username": u,
            "user_name": get_name_by_username(u) or u,
            "query_count": stats["query_count"],
            "total_tokens": stats["total_tokens"],
            "cost_usd": round(stats["cost_usd"], 6),
            "cost_vnd": round(stats["cost_usd"] * USD_TO_VND_RATE, 2)
        })
    user_breakdown.sort(key=lambda x: x["cost_usd"], reverse=True)

    return {
        "week_offset": week_offset,
        "week_start": target_monday.strftime("%Y-%m-%d"),
        "week_end": target_sunday.strftime("%Y-%m-%d"),
        "week_label": f"{target_monday.strftime('%d/%m/%Y')} - {target_sunday.strftime('%d/%m/%Y')}",
        "is_current_week": week_offset == 0,
        "total_queries": total_week_queries,
        "total_tokens": total_week_tokens,
        "total_cost_usd": round(total_week_cost_usd, 4),
        "total_cost_vnd": round(total_week_cost_vnd, 2),
        "daily_breakdown": daily_list,
        "user_breakdown": user_breakdown,
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
