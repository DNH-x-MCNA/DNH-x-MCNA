import os
import sys
import json
import datetime as dt
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Header, Depends, Query
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
)
from conversation_memory import (
    register_session,
    list_sessions,
    delete_session as delete_conversation_session,
    get_session_history,
)
from nl2sql import ask
from pricing import USD_TO_VND_RATE

init_auth_schema()

app = FastAPI(title="DNH AI Chatbot API", version="1.0.0")

API_KEY = os.getenv("BACKEND_API_KEY", "").strip()


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


_USER_LAST_REQUEST = {}
RATE_LIMIT_INTERVAL_SEC = 2.0


def _check_rate_limit(username: str):
    now = dt.datetime.now()
    last = _USER_LAST_REQUEST.get(username)
    if last and (now - last).total_seconds() < RATE_LIMIT_INTERVAL_SEC:
        raise HTTPException(429, "Thao tac qua nhanh, vui long cho 2 giay")
    _USER_LAST_REQUEST[username] = now


def _require_session_access(session_id: str, user: dict):
    from conversation_memory import get_session_owner
    owner = get_session_owner(session_id)
    if owner is not None and owner != user["username"] and user["role"] != "c_level":
        raise HTTPException(403, "Khong co quyen truy cap cuoc tro chuyen nay")


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


class UserInfo(BaseModel):
    username: str
    name: Optional[str]
    role: str
    scope_value: Optional[str]
    scope_channel: Optional[str]


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


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": dt.datetime.now().isoformat()}


@app.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(require_api_key)])
def login(req: LoginRequest):
    user = verify_login(req.username, req.password)
    if not user:
        raise HTTPException(401, "Tai khoan hoac mat khau khong dung")
    token = create_session(user["id"])
    return LoginResponse(
        token=token,
        username=user["username"],
        name=user["name"],
        role=user["role"],
        scope_value=user["scope_value"],
        scope_channel=user["scope_channel"],
    )


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
    )


@app.get("/history/{session_id}", response_model=list[HistoryMessage], dependencies=[Depends(require_api_key)])
def get_history(session_id: str, user: dict = Depends(require_user)):
    _require_session_access(session_id, user)
    return get_session_history(session_id)


@app.get("/sessions", response_model=list[SessionSummary], dependencies=[Depends(require_api_key)])
def get_sessions(user: dict = Depends(require_user)):
    rows = list_sessions(None if user["role"] == "c_level" else user["username"])
    out = []
    for r in rows:
        owner_name = get_name_by_username(r["owner_username"]) if user["role"] == "c_level" else user.get("name")
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
def delete_session_endpoint(session_id: str, user: dict = Depends(require_user)):
    from conversation_memory import get_session_owner
    owner = get_session_owner(session_id)
    if owner is not None and owner != user["username"]:
        raise HTTPException(403, "Chi chu so huu moi co quyen xoa cuoc tro chuyen nay")
    delete_conversation_session(session_id)
    return {"ok": True}


@app.post("/clear/{session_id}", dependencies=[Depends(require_api_key)])
def clear(session_id: str, user: dict = Depends(require_user)):
    _require_session_access(session_id, user)
    # 28/07/2026: truoc day import `clear_session_history` - ham nay KHONG TON TAI trong
    # conversation_memory.py (chi co clear_session, va 2 alias delete_session/get_session_history).
    # Vi import nam trong THAN ham nen khong lam sap luc khoi dong, chi no khi co nguoi bam xoa lich
    # su phien -> ImportError -> HTTP 500. Doi sang dung ham that.
    from conversation_memory import clear_session
    clear_session(session_id)
    return {"ok": True}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest, user: dict = Depends(require_user)):
    if not req.question or not req.question.strip():
        raise HTTPException(400, "Cau hoi khong duoc de trong")
    _check_rate_limit(user["username"])
    _require_session_access(req.session_id, user)
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
    limit: int = Query(default=200, ge=1, le=1000),
    user_filter: Optional[str] = None,
    user: dict = Depends(require_user)
):
    """
    Dashboard Audit Log & Chi phi AI truc quan khong can hoi AI - danh rieng cho Ban Dieu Hanh (C-Level / Super Admin).
    """
    if user["role"] != "c_level":
        raise HTTPException(403, "Chi tai khoan C-Level / Ban Dieu Hanh moi co quyen xem Dashboard Audit Log")

    _LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    AUDIT_LOG_PATH = os.path.join(_LOGS_DIR, "audit_log.jsonl")
    COST_LOG_PATH = os.path.join(_LOGS_DIR, "cost_log.jsonl")

    cutoff = dt.datetime.now() - dt.timedelta(days=days) if days else None

    # 1. Read audit logs
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

    # 2. Doc cost_log.jsonl - NGUON DUY NHAT CHO TONG CHI PHI THAT.
    #
    # 29/07/2026: truoc day tong chi phi duoc cong tu cac PHIEN co mat trong audit_log. Nhung
    # cost_log ghi MOI lan goi Claude API, con audit_log chi ghi khi chay SQL/goi tool bao cao - va
    # chi bat dau ghi session_id tu 28/07. Moi dong cost_log khong khop duoc voi audit_log deu bi bo
    # qua HOAN TOAN => tong bao ra thap hon thuc te rat nhieu (nguoi dung phan anh 29/07).
    #
    # Nay tach lam 2 khai niem:
    #   - TONG chi phi   = cong THANG tu cost_log (dung bang so tien Anthropic thuc thu)
    #   - Quy cho ai     = qua session_id, phan khong khop duoc gom vao dong "(chua quy duoc)"
    # Nho vay tong luon dung, va phan chua quy duoc thi HIEN RO thay vi bien mat.
    #
    # Token cung cong ca cache_read/cache_write: chi phi von da tinh chung (xem pricing.py), truoc
    # day chi hien input+output nen nguoi doc nham tay se thay khong khop voi so tien.
    cost_by_session = defaultdict(lambda: {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0, "calls": 0})
    cost_direct_by_user = defaultdict(lambda: {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0})
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
                # Ap CUNG bo loc thoi gian nhu audit_log - truoc day cost_log khong bi loc ngay nao,
                # nen chon "7 ngay" hay "30 ngay" deu ra cung mot so tien.
                if cutoff:
                    try:
                        if dt.datetime.fromisoformat(c["ts"]) < cutoff:
                            continue
                    except Exception:
                        pass
                cost = c.get("cost_usd", 0.0) or 0.0
                it = c.get("input_tokens", 0) or 0
                ot = c.get("output_tokens", 0) or 0
                cr = c.get("cache_read_tokens", 0) or 0
                cw = c.get("cache_write_tokens", 0) or 0
                grand_cost_usd += cost
                grand_input_tokens += it
                grand_output_tokens += ot
                grand_cache_tokens += cr + cw

                # Duong QUY CHI PHI thu nhat (29/07/2026, chinh xac nhat): cost_log nay ghi thang
                # username. Khong phu thuoc audit_log nen bat duoc CA nhung luot AI tra loi truc tiep
                # khong goi tool - von la phan lon chi phi bi that lac truoc day.
                uname_direct = (c.get("username") or "").strip()
                if uname_direct:
                    d = cost_direct_by_user[uname_direct]
                    d["cost_usd"] += cost
                    d["input_tokens"] += it
                    d["output_tokens"] += ot
                    d["cache_tokens"] += cr + cw
                    d["total_tokens"] += it + ot + cr + cw
                    continue  # da quy duoc, khong can den phep noi session

                # Duong DU PHONG: ban ghi cu (truoc 29/07) chua co username -> noi qua session_id.
                sid = c.get("session_id")
                if sid:
                    cost_by_session[sid]["cost_usd"] += cost
                    cost_by_session[sid]["input_tokens"] += it
                    cost_by_session[sid]["output_tokens"] += ot
                    cost_by_session[sid]["cache_tokens"] += cr + cw
                    cost_by_session[sid]["total_tokens"] += it + ot + cr + cw
                    cost_by_session[sid]["calls"] += 1

    # 3. Filter entries & aggregate stats per user
    filtered_logs = []
    user_stats = defaultdict(lambda: {"query_count": 0, "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0, "total_tokens": 0, "cost_usd": 0.0})
    total_cost_usd = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_tokens_attributed = 0

    target_user_str = (user_filter or "").strip().lower()

    # 29/07/2026 - CHONG CONG TRUNG CHI PHI.
    # cost_by_session[sid] la chi phi CA PHIEN, nhung vong lap duoi chay theo TUNG LUOT truy van.
    # Truoc day moi luot deu cong nguyen chi phi phien vao tong => phien co 6 luot bi tinh 6 lan.
    # Bang chung do duoc 29/07 (tai khoan tung.trinh): dashboard bao $1,0858 trong khi duong tinh
    # dung (report_templates.py::audit_log_summary - duyet tung dong cost_log DUNG MOT LAN) bao
    # $0,18 - lech 6,03 lan, khop chinh xac so luot trung binh moi phien (23 luot / 4 phien).
    # Nay moi phien CHI duoc cong mot lan, vao nguoi dung xuat hien dau tien trong phien do.
    counted_sessions = set()

    for e in audit_entries:
        uname = e.get("username") or "unknown"
        if target_user_str and target_user_str not in ("all", ""):
            if target_user_str not in uname.lower():
                continue
        if cutoff:
            try:
                if dt.datetime.fromisoformat(e["ts"]) < cutoff:
                    continue
            except Exception:
                pass

        sid = e.get("session_id")
        session_cost_data = cost_by_session.get(sid, {})
        c_usd = session_cost_data.get("cost_usd", 0.0)
        c_it = session_cost_data.get("input_tokens", 0)
        c_ot = session_cost_data.get("output_tokens", 0)
        c_ct = session_cost_data.get("cache_tokens", 0)
        c_tt = session_cost_data.get("total_tokens", c_it + c_ot)

        display_name = get_name_by_username(uname) or uname

        user_stats[uname]["query_count"] += 1
        user_stats[uname]["display_name"] = display_name

        # Chi cong chi phi/token khi gap phien nay LAN DAU - xem ghi chu "CHONG CONG TRUNG" o tren.
        # Luot khong co session_id (ban ghi truoc 28/07, khi audit_log chua ghi truong nay) van duoc
        # dem vao query_count nhung khong co chi phi - dung, vi khong the noi nguoc ve cost_log.
        if sid and sid not in counted_sessions:
            counted_sessions.add(sid)
            user_stats[uname]["input_tokens"] += c_it
            user_stats[uname]["output_tokens"] += c_ot
            user_stats[uname]["cache_tokens"] += c_ct
            user_stats[uname]["total_tokens"] += c_tt
            user_stats[uname]["cost_usd"] += c_usd
            total_cost_usd += c_usd
            total_input_tokens += c_it
            total_output_tokens += c_ot
            total_cache_tokens_attributed += c_ct

        filtered_logs.append({
            "ts": e.get("ts"),
            "username": uname,
            "user_name": display_name,
            "question": e.get("question"),
            "sql": e.get("sql"),
            "status": e.get("status", "success"),
            "duration_ms": e.get("duration_ms"),
            # CHI PHI CUA CA PHIEN, khong phai cua rieng luot nay - cost_log ghi theo lan goi API,
            # mot luot hoi sinh nhieu lan goi nen KHONG tach duoc xuong tung cau hoi. Nhieu dong
            # cung mot phien se hien CUNG mot so; cong tay cac dong nay lai se ra so sai (dung
            # tong o phan summary, da chong trung). Ten truong co hau to _session cho ro nghia.
            "session_id": sid,
            "session_input_tokens": c_it,
            "session_output_tokens": c_ot,
            "session_total_tokens": c_tt,
            "session_cost_usd": round(c_usd, 6),
            "session_cost_vnd": round(c_usd * USD_TO_VND_RATE, 2),
        })

    filtered_logs.sort(key=lambda x: x.get("ts", ""), reverse=True)
    recent_logs = filtered_logs[:limit]

    # Cong phan quy TRUC TIEP tu cost_log (co username) vao thong ke tung nguoi. Nguoi chi xuat hien
    # trong cost_log ma chua tung co dong audit_log nao van duoc tao muc rieng (query_count=0) - ho
    # co ton tien that, khong duoc bo sot.
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

    # Phan chi phi CO THAT nhung chua noi duoc ve nguoi dung nao (phien khong xuat hien trong
    # audit_log, hoac ban ghi truoc 28/07 khi audit_log chua ghi session_id). HIEN RO thanh 1 dong
    # thay vi de bien mat - chinh cho nay tung lam tong bao ra thap hon thuc te.
    unattributed = grand_cost_usd - total_cost_usd
    if unattributed > 1e-9:
        # 29/07/2026 - SUA LOI: truoc day total_tokens o dong nay bi ghi CUNG bang 0 trong khi
        # input/output van co so, nen tren dashboard hien "In 2.738.469 · Out 313.394" ma cot "Tong
        # Tokens" lai bang 0 - nhin nhu du lieu hong. Nay tinh dung bang phan con lai cua tong.
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
            # Co day de frontend KHONG danh dau "tieu thu cao nhat" vao dong nay - day khong phai
            # mot nguoi dung that, no la phan chi phi chua noi duoc ve ai.
            "is_unattributed": True,
        })

    return {
        "summary": {
            # TONG = cong thang tu cost_log, dung bang so tien thuc thu - KHONG phai tong phan da
            # quy duoc cho nguoi dung (xem ghi chu muc 2).
            "total_cost_usd": round(grand_cost_usd, 6),
            "total_cost_vnd": round(grand_cost_usd * USD_TO_VND_RATE, 2),
            "attributed_cost_usd": round(total_cost_usd, 6),
            "unattributed_cost_usd": round(max(0.0, unattributed), 6),
            "total_input_tokens": grand_input_tokens,
            "total_output_tokens": grand_output_tokens,
            "total_cache_tokens": grand_cache_tokens,
            "grand_total_tokens": grand_input_tokens + grand_output_tokens + grand_cache_tokens,
            "total_queries": len(filtered_logs),
            # Loai "unknown" (luot khong xac dinh duoc tai khoan) khoi so nguoi dung - truoc day dem
            # ca no nen so "nguoi dung hoat dong" luon nhieu hon so nguoi that.
            "unique_users_count": len([u for u in user_stats if u and u.lower() != "unknown"]),
            "days": days
        },
        "user_breakdown": user_breakdown,
        "logs": recent_logs
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
