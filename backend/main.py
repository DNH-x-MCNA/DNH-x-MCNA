# -*- coding: utf-8 -*-
"""FastAPI backend cho AI Chatbot DNH - Phase 2."""
import os
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
load_env()

from nl2sql import ask  # noqa: E402  (phai load_env truoc khi import - nl2sql doc ANTHROPIC_API_KEY luc goi ham)
from conversation_memory import (  # noqa: E402
    load_history, clear_session, register_session, list_sessions, get_session_owner,
)
import auth  # noqa: E402

auth.init_schema()

app = FastAPI(title="DNH AI Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://dnh-bot.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_API_KEY = os.environ.get("BACKEND_API_KEY")


def require_api_key(x_api_key: str = Header(default=None)):
    """Chan cac request khong kem dung API key (danh cho frontend Vercel qua tunnel cong khai) -
    hang rao co ban chong bot/scan tu dong, KHONG thay the cho kiem soat truy cap that (vd Cloudflare
    Access theo email DNH) neu can gioi han chi nhan vien cong ty duoc dung."""
    if BACKEND_API_KEY and x_api_key != BACKEND_API_KEY:
        raise HTTPException(401, "Thieu hoac sai API key")


def require_user(authorization: str = Header(default=None)) -> dict:
    """Xac thuc nguoi dung qua session token (Authorization: Bearer <token>) - day la lop bao mat
    THAT (khac API key chi la hang rao chong bot). Tra ve dict {id,username,name,role,scope_value}."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Chua dang nhap")
    token = authorization[len("Bearer "):]
    user = auth.get_user_by_session(token)
    if not user:
        raise HTTPException(401, "Phien dang nhap khong hop le hoac da het han")
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    name: str | None
    role: str
    scope_value: str | None


class UserInfo(BaseModel):
    username: str
    name: str | None
    role: str
    scope_value: str | None


class ChatRequest(BaseModel):
    question: str
    session_id: str = "default"  # 1 session = 1 phien chat webapp, dung de nho ngu canh


class ChatResponse(BaseModel):
    answer: str
    sql_used: list[str]
    columns: list[str] | None = None
    rows: list | None = None
    row_count: int | None = None


class HistoryMessage(BaseModel):
    role: str
    content: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(require_api_key)])
def login(req: LoginRequest):
    user = auth.verify_login(req.username, req.password)
    if not user:
        raise HTTPException(401, "Tai khoan hoac mat khau khong dung")
    token = auth.create_session(user["id"])
    return LoginResponse(token=token, name=user["name"], role=user["role"], scope_value=user["scope_value"])


@app.post("/auth/logout", dependencies=[Depends(require_api_key)])
def logout(authorization: str = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        auth.delete_session(authorization[len("Bearer "):])
    return {"status": "logged_out"}


@app.get("/auth/me", response_model=UserInfo, dependencies=[Depends(require_api_key)])
def me(user: dict = Depends(require_user)):
    return UserInfo(username=user["username"], name=user["name"], role=user["role"], scope_value=user["scope_value"])


def _require_session_access(session_id: str, user: dict):
    """Chan truy cap session cua nguoi khac - c_level xem duoc tat ca, con lai CHI xem duoc session
    cua CHINH MINH. owner=None (session cu tao truoc khi co bang sessions) tam thoi cho qua de khong
    vo du lieu cu."""
    owner = get_session_owner(session_id)
    if owner is not None and owner != user["username"] and user["role"] != "c_level":
        raise HTTPException(403, "Ban khong co quyen xem cuoc tro chuyen nay")


@app.get("/history/{session_id}", response_model=list[HistoryMessage], dependencies=[Depends(require_api_key)])
def get_history(session_id: str, user: dict = Depends(require_user)):
    """Lay lai lich su hoi thoai cua 1 session - de frontend hien thi lai khi mo lai trang."""
    _require_session_access(session_id, user)
    return [HistoryMessage(**m) for m in load_history(session_id, max_turns=20)]


class SessionSummary(BaseModel):
    session_id: str
    title: str | None
    owner_username: str
    owner_name: str | None
    created_at: str
    updated_at: str


@app.get("/sessions", response_model=list[SessionSummary], dependencies=[Depends(require_api_key)])
def get_sessions(user: dict = Depends(require_user)):
    """Danh sach cuoc tro chuyen (kieu ChatGPT) - c_level thay TAT CA (kem ten chu so huu), nguoi
    khac CHI thay cua chinh minh."""
    rows = list_sessions(None if user["role"] == "c_level" else user["username"])
    out = []
    for r in rows:
        owner_name = user["name"] if r["owner_username"] == user["username"] else auth.get_name_by_username(r["owner_username"])
        out.append(SessionSummary(owner_name=owner_name, **r))
    return out


@app.delete("/sessions/{session_id}", dependencies=[Depends(require_api_key)])
def delete_session_endpoint(session_id: str, user: dict = Depends(require_user)):
    """Xoa han 1 cuoc tro chuyen - CHI chu so huu moi xoa duoc (c_level xem duoc cua nguoi khac
    nhung KHONG tu y xoa, an toan hon)."""
    owner = get_session_owner(session_id)
    if owner is not None and owner != user["username"]:
        raise HTTPException(403, "Ban khong co quyen xoa cuoc tro chuyen nay")
    clear_session(session_id)
    return {"status": "deleted"}


@app.post("/clear/{session_id}", dependencies=[Depends(require_api_key)])
def clear(session_id: str, user: dict = Depends(require_user)):
    """Xoa lich su hoi thoai cua 1 session (giu lai de tuong thich nguoc - frontend moi dung
    DELETE /sessions/{id} thay the)."""
    owner = get_session_owner(session_id)
    if owner is not None and owner != user["username"]:
        raise HTTPException(403, "Ban khong co quyen xoa cuoc tro chuyen nay")
    clear_session(session_id)
    return {"status": "cleared"}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest, user: dict = Depends(require_user)):
    if not req.question or not req.question.strip():
        raise HTTPException(400, "Cau hoi khong duoc de trong")
    _require_session_access(req.session_id, user)
    try:
        # regional_director/qlv bi gioi han xem theo vung (scope_value = MB/MT/MN) - c_level khong
        # gioi han gi (scope_area_code=None). Enforce THAT xay ra o report_templates.py (tang code,
        # khong phu thuoc AI), day chi la buoc suy ra scope tu tai khoan da dang nhap.
        scope_area_code = user["scope_value"] if user["role"] in ("regional_director", "qlv") else None
        # scope_employee_code: CHI danh cho qlv (khong danh cho regional_director - ho la cap tren
        # nhieu QLV nen duoc xem het ca vung nhu thiet ke ban dau) - gioi han bao cao lo hieu suat CA
        # NHAN dong nghiep (get_revenue_tree/get_kpi_ranking) chi con doi cua rieng ho, khong thay
        # KPI ca nhan cua cac QLV khac trong cung vung.
        scope_employee_code = user["employee_code"] if user["role"] == "qlv" else None
        # scope_channel: doc lap voi role/scope_area_code - CHI gioi han theo kenh (vd 'OTC') khi tai
        # khoan duoc gan rieng, ap dung duoc cho BAT KY role nao (vd c_level nhung chi duoc xem OTC).
        scope_channel = user.get("scope_channel")
        result = ask(req.question, session_id=req.session_id, username=user["username"],
                     scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                     scope_channel=scope_channel)
        register_session(req.session_id, user["username"], req.question)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Loi he thong: {str(e)[:300]}")

    lr = result.get("last_result") or {}
    # last_result co 2 dang: ket qua tool bao cao chuan ({"ok","result"}) hoac raw SQL ({"ok","columns","rows","row_count"}).
    # Chi tra ve columns/rows/row_count khi la dang raw SQL (co du 3 truong nay).
    is_raw_sql = lr.get("ok") and "columns" in lr
    return ChatResponse(
        answer=result["answer"],
        sql_used=result["sql_used"],
        columns=lr.get("columns") if is_raw_sql else None,
        rows=lr.get("rows") if is_raw_sql else None,
        row_count=lr.get("row_count") if is_raw_sql else None,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
