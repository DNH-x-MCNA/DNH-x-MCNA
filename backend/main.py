import os
import sqlite3
import sys
import json
from fastapi import FastAPI, HTTPException, Header, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# Add parent directory to path to import chatbot
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_agent.chatbot import DNHChatbot
from botbuilder.schema import Activity
from src.teams_bot import ADAPTER, dnh_bot

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "dnh_intermediate.db")

app = FastAPI(title="DNH Intermediate API Middleware", version="1.0.0")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory users for under 10 users permission control
USERS = {
    "admin": "dnh@admin2026",
    "manager_bac": "dnh@bac2026",
    "manager_etc": "dnh@etc2026",
    "c_level": "dnh@clevel2026"
}

# Chatbot instance
chatbot = DNHChatbot()

class LoginRequest(BaseModel):
    username: str
    password: str

class QueryRequest(BaseModel):
    question: str

def get_db_connection():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=500, detail="Database trung gian chua duoc khoi tao.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Simple Authentication dependency
def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Thieu token xac thuc")
    token = authorization.split(" ")[1]
    # Simple check for demo purposes
    if token not in ["token_admin", "token_manager_bac", "token_manager_etc", "token_c_level"]:
        raise HTTPException(status_code=401, detail="Token khong hop le hoac da het han")
    return token

@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.username in USERS and USERS[req.username] == req.password:
        # Return a simple mock token based on username
        token = f"token_{req.username}"
        return {
            "success": True,
            "token": token,
            "username": req.username,
            "role": "C-Level" if req.username == "c_level" or req.username == "admin" else "Manager"
        }
    raise HTTPException(status_code=400, detail="Sai ten dang nhap hoac mat khau")

@app.get("/api/dashboard/stats")
def get_stats(token: str = Depends(verify_token)):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COALESCE(SUM(balance_end), 0) FROM receivable_detail")
        total_receivable = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(total_overdue), 0) FROM receivable_detail")
        total_overdue = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT customer_code) FROM receivable_detail")
        total_customers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM inventory")
        total_inventory_items = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(closing_value), 0) FROM inventory")
        total_inventory_value = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM kpi_summary")
        total_employees = cursor.fetchone()[0]

        conn.close()
        return {
            "total_receivable": total_receivable,
            "total_overdue": total_overdue,
            "total_customers": total_customers,
            "total_inventory_items": total_inventory_items,
            "total_inventory_value": total_inventory_value,
            "total_employees": total_employees
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/charts")
def get_charts(token: str = Depends(verify_token)):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Cong no theo kenh ban hang
        cursor.execute("""
            SELECT sales_channel, COALESCE(SUM(balance_end), 0) as total_balance
            FROM receivable_detail
            GROUP BY sales_channel
            ORDER BY total_balance DESC
        """)
        receivable_by_channel = [dict(row) for row in cursor.fetchall()]

        # 2. Phan tich tuoi no qua han
        cursor.execute("""
            SELECT
                COALESCE(SUM(overdue_1_15), 0)  as overdue_1_15,
                COALESCE(SUM(overdue_15_30), 0) as overdue_15_30,
                COALESCE(SUM(overdue_30_45), 0) as overdue_30_45,
                COALESCE(SUM(overdue_gt_45), 0) as overdue_gt_45
            FROM receivable_detail
        """)
        aging_row = dict(cursor.fetchone())
        overdue_aging = [
            {"bucket": "1-15 ngay",  "amount": aging_row["overdue_1_15"]},
            {"bucket": "15-30 ngay", "amount": aging_row["overdue_15_30"]},
            {"bucket": "30-45 ngay", "amount": aging_row["overdue_30_45"]},
            {"bucket": ">45 ngay",   "amount": aging_row["overdue_gt_45"]},
        ]

        # 3. Top 10 khach hang qua han cao nhat
        cursor.execute("""
            SELECT customer_code, customer_name,
                   COALESCE(SUM(total_overdue), 0) as total_overdue
            FROM receivable_detail
            GROUP BY customer_code, customer_name
            ORDER BY total_overdue DESC
            LIMIT 10
        """)
        top_overdue_customers = [dict(row) for row in cursor.fetchall()]

        # 4. KPI doanh so theo vung
        cursor.execute("""
            SELECT area_code,
                   COALESCE(SUM(month_sale_amount), 0) as total_month_sale
            FROM kpi_summary
            GROUP BY area_code
            ORDER BY total_month_sale DESC
        """)
        kpi_by_region = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return {
            "receivable_by_channel": receivable_by_channel,
            "overdue_aging": overdue_aging,
            "top_overdue_customers": top_overdue_customers,
            "kpi_by_region": kpi_by_region
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debt/alerts")
def get_debt_alerts(token: str = Depends(verify_token)):
    """Tra ve khach hang co no qua han, sap xep giam dan theo total_overdue."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT customer_code, customer_name, sales_channel,
                   COALESCE(SUM(balance_end), 0)    as balance_end,
                   COALESCE(SUM(in_term), 0)         as in_term,
                   COALESCE(SUM(overdue_1_15), 0)    as overdue_1_15,
                   COALESCE(SUM(overdue_15_30), 0)   as overdue_15_30,
                   COALESCE(SUM(overdue_30_45), 0)   as overdue_30_45,
                   COALESCE(SUM(overdue_gt_45), 0)   as overdue_gt_45,
                   COALESCE(SUM(total_overdue), 0)   as total_overdue
            FROM receivable_detail
            GROUP BY customer_code, customer_name, sales_channel
            HAVING SUM(total_overdue) > 0
            ORDER BY total_overdue DESC
            LIMIT 50
        """)
        alerts = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return {
            "total_alerts": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/inventory/summary")
def get_inventory_summary(token: str = Depends(verify_token)):
    """Tra ve danh sach ton kho va phan loai rui ro theo months_to_sell."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT item_code, item_name, unit,
                   closing_qty, closing_value, months_to_sell,
                   CASE
                       WHEN months_to_sell >= 6 THEN 'Can date'
                       WHEN months_to_sell > 1  THEN 'Binh thuong'
                       ELSE 'Thieu hang'
                   END as risk_level
            FROM inventory
            ORDER BY months_to_sell ASC
        """)
        items = [dict(row) for row in cursor.fetchall()]

        # Thong ke theo nhom rui ro
        risk_summary = {}
        for item in items:
            level = item["risk_level"]
            if level not in risk_summary:
                risk_summary[level] = {"count": 0, "total_value": 0}
            risk_summary[level]["count"] += 1
            risk_summary[level]["total_value"] += item["closing_value"] or 0

        conn.close()
        return {
            "total_items": len(items),
            "risk_summary": risk_summary,
            "items": items
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kpi/summary")
def get_kpi_summary(token: str = Depends(verify_token)):
    """Tra ve bang tong hop KPI nhan vien."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT area_code, employee_code, employee_name, position_code,
                   month_sale_target, month_sale_amount, month_sale_percent,
                   total_point,
                   quarter_sale_target, quarter_sale_amount, quarter_sale_percent,
                   year_sale_target, year_sale_amount, year_sale_percent
            FROM kpi_summary
            ORDER BY area_code, employee_code
        """)
        rows = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return {
            "total_employees": len(rows),
            "data": rows
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chatbot/query")
def chat_query(req: QueryRequest, token: str = Depends(verify_token)):
    if not req.question:
        raise HTTPException(status_code=400, detail="Cau hoi khong duoc de trong")
    
    try:
        response_data = chatbot.ask(req.question)
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/messages")
async def messages(request: Request):
    """Endpoint chính tiếp nhận tin nhắn từ Microsoft Teams"""
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
    else:
        return Response(status_code=415, content="Unsupported Media Type")

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    async def call_bot(turn_context):
        await dnh_bot.on_turn(turn_context)

    try:
        response = await ADAPTER.process_activity(activity, auth_header, call_bot)
        if response:
            return Response(
                content=json.dumps(response.body),
                status_code=response.status,
                media_type="application/json"
            )
        return Response(status_code=200)
    except Exception as e:
        print(f"Error processing Teams activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
