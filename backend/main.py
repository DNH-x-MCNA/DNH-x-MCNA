import os
import sys
import base64
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text

# Add parent directory to path to import chatbot
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_agent.chatbot import DNHChatbot, _get_cloud_engine, _latest_period_key
# NOTE: Teams Q&A bot đã deprecate (Go-Live Plan Phase 5.1) — chatbot chỉ chạy trên web UI.
# Teams chỉ nhận alert webhook (src/notifier.py). Xem _deprecated/README.md.

app = FastAPI(title="DNH Intermediate API Middleware", version="1.0.0")

# CORS: mặc định "*" cho tiện dev; production PHẢI siết về domain nội bộ DNH bằng cách
# đặt biến môi trường ALLOWED_ORIGINS (danh sách domain, phân tách bằng dấu phẩy).
# Ví dụ: ALLOWED_ORIGINS="https://portal.duocnamha.local,https://dnh.internal"
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory users for under 10 users permission control
USERS = {
    "admin": "dnh@admin2026",
    "c_level": "dnh@clevel2026",
    # Manager — giới hạn 1 chiều (miền HOẶC kênh). Nhận diện role qua token username, xem
    # ai_agent/chatbot.py::_resolve_user_scope() — thêm role mới ở đây KHÔNG cần sửa chatbot.py,
    # chỉ cần username chứa đúng 1 token miền (bac/nam/trung) và/hoặc 1 token kênh (otc/etc).
    "manager_bac": "dnh@bac2026",
    "manager_nam": "dnh@nam2026",
    "manager_trung": "dnh@trung2026",
    "manager_otc": "dnh@otc2026",
    "manager_etc": "dnh@etc2026",
    # QLV (Quản lý vùng)
    "qlv_bac": "dnh@qlvbac2026",
    "qlv_nam": "dnh@qlvnam2026",
    "qlv_trung": "dnh@qlvtrung2026",
    "qlv_otc": "dnh@qlvotc2026",
    "qlv_etc": "dnh@qlvetc2026",
    # Phó phòng (PP)
    "pp_bac": "dnh@ppbac2026",
    "pp_nam": "dnh@ppnam2026",
    "pp_trung": "dnh@pptrung2026",
    "pp_otc": "dnh@ppotc2026",
    "pp_etc": "dnh@ppetc2026",
}

# Chatbot instance
chatbot = DNHChatbot()

class LoginRequest(BaseModel):
    username: str
    password: str

class QueryRequest(BaseModel):
    question: str

def get_cloud_connection():
    """All dashboard/debt/kpi endpoints read from Supabase (cloud Postgres) —
    the same engine/pool the chatbot uses, not the local SQLite intermediate DB."""
    engine = _get_cloud_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="CLOUD_DB_URL chua duoc cau hinh.")
    try:
        return engine.connect()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Khong ket noi duoc Supabase: {e}")

def get_latest_receivable_period(conn):
    """receivable_detail.period is TEXT 'M_YYYY' (not zero-padded) — must parse
    (year, month) rather than take a plain SQL/string MAX(). See _latest_period_key."""
    periods = [r[0] for r in conn.execute(text("SELECT DISTINCT period FROM receivable_detail")).fetchall() if r[0]]
    if not periods:
        raise HTTPException(status_code=500, detail="Khong tim thay ky bao cao nao trong receivable_detail.")
    return max(periods, key=_latest_period_key)

# Simple Authentication dependency
def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Thieu token xac thuc")
    token = authorization.split(" ")[1]
    # Token hop le <=> username tuong ung con trong USERS (tu dong theo danh sach tai khoan,
    # khong hard-code tung token rieng le - them tai khoan moi vao USERS la du).
    if token.replace("token_", "", 1) not in USERS:
        raise HTTPException(status_code=401, detail="Token khong hop le hoac da het han")
    return token

def _display_role(username):
    """Nhãn vai trò hiển thị trên UI, suy ra từ token trong username — xem cùng quy ước với
    ai_agent/chatbot.py::_resolve_user_scope()."""
    if username in ("c_level", "admin"):
        return "C-Level"
    tokens = username.replace('-', '_').split('_')
    if "qlv" in tokens:
        return "QLV"
    if "pp" in tokens:
        return "Phó phòng"
    return "Manager"

@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.username in USERS and USERS[req.username] == req.password:
        # Return a simple mock token based on username
        token = f"token_{req.username}"
        return {
            "success": True,
            "token": token,
            "username": req.username,
            "role": _display_role(req.username)
        }
    raise HTTPException(status_code=400, detail="Sai ten dang nhap hoac mat khau")

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, token: str = Depends(verify_token)):
    username = token.replace("token_", "", 1)

    # Kiểm tra mật khẩu cũ
    if USERS.get(username) != req.old_password:
        raise HTTPException(status_code=400, detail="Mật khẩu cũ không đúng")

    # Kiểm tra xác nhận mật khẩu mới
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Mật khẩu mới và xác nhận mật khẩu không khớp")

    # Kiểm tra độ dài mật khẩu mới
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải có ít nhất 8 ký tự")

    # Cập nhật mật khẩu (in-memory, có hiệu lực trong phiên server đang chạy)
    USERS[username] = req.new_password
    return {"success": True, "message": "Đổi mật khẩu thành công"}

@app.get("/api/dashboard/stats")
def get_stats(token: str = Depends(verify_token)):
    conn = get_cloud_connection()
    try:
        period = get_latest_receivable_period(conn)

        total_receivable = conn.execute(text(
            "SELECT COALESCE(SUM(balance_end), 0) FROM receivable_detail WHERE period = :p"
        ), {"p": period}).scalar()

        total_overdue = conn.execute(text(
            "SELECT COALESCE(SUM(total_overdue), 0) FROM receivable_detail WHERE period = :p"
        ), {"p": period}).scalar()

        total_customers = conn.execute(text(
            "SELECT COUNT(DISTINCT customer_code) FROM receivable_detail WHERE period = :p"
        ), {"p": period}).scalar()

        total_inventory_items = conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar()

        total_inventory_value = conn.execute(text(
            "SELECT COALESCE(SUM(closing_value), 0) FROM inventory"
        )).scalar()

        total_employees = conn.execute(text("SELECT COUNT(*) FROM kpi_summary")).scalar()

        return {
            "period": period,
            "total_receivable": total_receivable,
            "total_overdue": total_overdue,
            "total_customers": total_customers,
            "total_inventory_items": total_inventory_items,
            "total_inventory_value": total_inventory_value,
            "total_employees": total_employees
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/dashboard/charts")
def get_charts(token: str = Depends(verify_token)):
    conn = get_cloud_connection()
    try:
        period = get_latest_receivable_period(conn)

        # 1. Cong no theo kenh ban hang
        receivable_by_channel = [dict(r._mapping) for r in conn.execute(text("""
            SELECT sales_channel, COALESCE(SUM(balance_end), 0) as total_balance
            FROM receivable_detail
            WHERE period = :p
            GROUP BY sales_channel
            ORDER BY total_balance DESC
        """), {"p": period})]

        # 2. Phan tich tuoi no qua han
        aging_row = conn.execute(text("""
            SELECT
                COALESCE(SUM(overdue_1_15), 0)  as overdue_1_15,
                COALESCE(SUM(overdue_15_30), 0) as overdue_15_30,
                COALESCE(SUM(overdue_30_45), 0) as overdue_30_45,
                COALESCE(SUM(overdue_gt_45), 0) as overdue_gt_45
            FROM receivable_detail
            WHERE period = :p
        """), {"p": period}).mappings().fetchone()
        overdue_aging = [
            {"bucket": "1-15 ngay",  "amount": aging_row["overdue_1_15"]},
            {"bucket": "15-30 ngay", "amount": aging_row["overdue_15_30"]},
            {"bucket": "30-45 ngay", "amount": aging_row["overdue_30_45"]},
            {"bucket": ">45 ngay",   "amount": aging_row["overdue_gt_45"]},
        ]

        # 3. Top 10 khach hang qua han cao nhat
        top_overdue_customers = [dict(r._mapping) for r in conn.execute(text("""
            SELECT customer_code, customer_name,
                   COALESCE(SUM(total_overdue), 0) as total_overdue
            FROM receivable_detail
            WHERE period = :p
            GROUP BY customer_code, customer_name
            ORDER BY total_overdue DESC
            LIMIT 10
        """), {"p": period})]

        # 4. KPI doanh so theo vung
        kpi_by_region = [dict(r._mapping) for r in conn.execute(text("""
            SELECT area_code,
                   COALESCE(SUM(month_sale_amount), 0) as total_month_sale
            FROM kpi_summary
            GROUP BY area_code
            ORDER BY total_month_sale DESC
        """))]

        return {
            "period": period,
            "receivable_by_channel": receivable_by_channel,
            "overdue_aging": overdue_aging,
            "top_overdue_customers": top_overdue_customers,
            "kpi_by_region": kpi_by_region
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/debt/alerts")
def get_debt_alerts(token: str = Depends(verify_token)):
    """Tra ve khach hang co no qua han, sap xep giam dan theo total_overdue."""
    conn = get_cloud_connection()
    try:
        period = get_latest_receivable_period(conn)
        alerts = [dict(r._mapping) for r in conn.execute(text("""
            SELECT customer_code, customer_name, sales_channel,
                   COALESCE(SUM(balance_end), 0)    as balance_end,
                   COALESCE(SUM(in_term), 0)         as in_term,
                   COALESCE(SUM(overdue_1_15), 0)    as overdue_1_15,
                   COALESCE(SUM(overdue_15_30), 0)   as overdue_15_30,
                   COALESCE(SUM(overdue_30_45), 0)   as overdue_30_45,
                   COALESCE(SUM(overdue_gt_45), 0)   as overdue_gt_45,
                   COALESCE(SUM(total_overdue), 0)   as total_overdue
            FROM receivable_detail
            WHERE period = :p
            GROUP BY customer_code, customer_name, sales_channel
            HAVING SUM(total_overdue) > 0
            ORDER BY total_overdue DESC
            LIMIT 50
        """), {"p": period})]

        return {
            "period": period,
            "total_alerts": len(alerts),
            "alerts": alerts
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/inventory/summary")
def get_inventory_summary(token: str = Depends(verify_token)):
    """Tra ve danh sach ton kho va phan loai rui ro theo months_to_sell."""
    conn = get_cloud_connection()
    try:
        items = [dict(r._mapping) for r in conn.execute(text("""
            SELECT item_code, item_name, unit,
                   closing_qty, closing_value, months_to_sell,
                   CASE
                       WHEN months_to_sell >= 6 THEN 'Can date'
                       WHEN months_to_sell > 1  THEN 'Binh thuong'
                       ELSE 'Thieu hang'
                   END as risk_level
            FROM inventory
            ORDER BY months_to_sell ASC
        """))]

        # Thong ke theo nhom rui ro
        risk_summary = {}
        for item in items:
            level = item["risk_level"]
            if level not in risk_summary:
                risk_summary[level] = {"count": 0, "total_value": 0}
            risk_summary[level]["count"] += 1
            risk_summary[level]["total_value"] += item["closing_value"] or 0

        return {
            "total_items": len(items),
            "risk_summary": risk_summary,
            "items": items
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/kpi/summary")
def get_kpi_summary(token: str = Depends(verify_token)):
    """Tra ve bang tong hop KPI nhan vien."""
    conn = get_cloud_connection()
    try:
        rows = [dict(r._mapping) for r in conn.execute(text("""
            SELECT area_code, employee_code, employee_name, position_code,
                   month_sale_target, month_sale_amount, month_sale_percent,
                   total_point,
                   quarter_sale_target, quarter_sale_amount, quarter_sale_percent,
                   year_sale_target, year_sale_amount, year_sale_percent
            FROM kpi_summary
            ORDER BY area_code, employee_code
        """))]

        return {
            "total_employees": len(rows),
            "data": rows
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/chatbot/query")
def chat_query(req: QueryRequest, token: str = Depends(verify_token)):
    if not req.question:
        raise HTTPException(status_code=400, detail="Cau hoi khong duoc de trong")

    try:
        username = token.replace("token_", "") if token else None
        response_data = chatbot.ask(req.question, session_key=token, username=username)
        # Chart is a local file on the server (matplotlib output). Inline it as
        # base64 so the browser can render it directly, same as the Telegram/Teams
        # bots do — no need for a separate static-file route to the scratch dir.
        chart_path = response_data.get("chart_path")
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, "rb") as f:
                response_data["chart_base64"] = base64.b64encode(f.read()).decode("utf-8")
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# NOTE: Route POST /api/messages (Teams Bot webhook) đã gỡ theo Go-Live Plan Phase 5.1.
# Teams giờ chỉ nhận alert một chiều qua Incoming Webhook (src/notifier.py::send_teams_alert),
# không còn hội thoại hai chiều. Xem _deprecated/README.md.

# Mount static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # host="0.0.0.0" (không phải 127.0.0.1) để máy khác trong mạng nội bộ gọi vào được khi deploy
    # lên 1 server dùng chung (vd để nút "Xem chi tiết trên Chatbot" trong card Teams hoạt động
    # cho cả công ty, không chỉ từ máy đang chạy backend) — vẫn truy cập được qua localhost bình
    # thường khi chạy dev trên máy cá nhân. reload=False vì đây là service chạy thường trực
    # (qua NSSM), không cần tự nạp lại code mỗi khi file đổi như lúc code dev.
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
