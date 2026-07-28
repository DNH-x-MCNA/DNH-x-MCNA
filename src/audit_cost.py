"""
Audit Logging and Token Cost Tracking Module with User-level Filtering and Role-Based Access Control (RBAC).

Features:
- Query Audit Logging (who, when, question, generated SQL, execution time, row count, status).
- LLM Token & Cost Tracking (prompt tokens, completion tokens, total tokens, USD cost, VND cost).
- User-level Filtering & Analytics.
- Role-Based Access Control (only C_LEVEL and SUPER_ADMIN roles can view audit logs).
"""

import os
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

try:
    import pytz
    VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
except ImportError:
    VN_TZ = None

logger = logging.getLogger(__name__)

# Exchange rate USD -> VND
USD_TO_VND_RATE = 25400.0

# Pricing table per 1M tokens (USD)
MODEL_PRICING = {
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "default": {"input": 0.10, "output": 0.40}
}

ALLOWED_ROLES_FOR_AUDIT = {"SUPER_ADMIN", "C_LEVEL", "CEO", "CFO", "COO"}

def get_now_vn() -> datetime:
    """Get current datetime in Asia/Ho_Chi_Minh timezone."""
    if VN_TZ:
        return datetime.now(VN_TZ)
    return datetime.now()

def calculate_token_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> Dict[str, float]:
    """
    Calculate USD and VND cost based on token counts and model pricing.
    """
    model_key = model_name.lower().strip()
    pricing = MODEL_PRICING.get(model_key, MODEL_PRICING["default"])
    
    cost_usd = (prompt_tokens / 1_000_000.0 * pricing["input"]) + \
               (completion_tokens / 1_000_000.0 * pricing["output"])
    cost_vnd = cost_usd * USD_TO_VND_RATE
    
    return {
        "cost_usd": round(cost_usd, 6),
        "cost_vnd": round(cost_vnd, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens
    }

def is_user_authorized_for_audit(user_role: str) -> bool:
    """
    Check if the given user role is authorized to view audit logs and cost tracking.
    """
    if not user_role:
        return False
    return user_role.upper().strip() in ALLOWED_ROLES_FOR_AUDIT

def init_audit_tables(pg_engine):
    """
    Create query_audit_logs and chat_usage_logs tables if they don't exist.
    """
    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS public.query_audit_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id VARCHAR(100),
        user_name VARCHAR(200),
        user_role VARCHAR(50),
        question_text TEXT,
        generated_sql TEXT,
        execution_status VARCHAR(20),
        execution_time_ms INT,
        rows_returned INT,
        error_message TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.chat_usage_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id VARCHAR(100),
        user_name VARCHAR(200),
        user_role VARCHAR(50),
        conversation_id VARCHAR(100),
        question_text TEXT,
        model_name VARCHAR(100),
        prompt_tokens INT NOT NULL,
        completion_tokens INT NOT NULL,
        total_tokens INT NOT NULL,
        cost_usd NUMERIC(10, 6),
        cost_vnd NUMERIC(12, 2),
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_audit_user_id ON public.query_audit_logs(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_created_at ON public.query_audit_logs(created_at);
    CREATE INDEX IF NOT EXISTS idx_usage_user_id ON public.chat_usage_logs(user_id);
    CREATE INDEX IF NOT EXISTS idx_usage_created_at ON public.chat_usage_logs(created_at);
    """
    try:
        with pg_engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text(create_tables_sql))
            conn.commit()
            logger.info("Successfully initialized audit_logs and chat_usage_logs tables.")
    except Exception as e:
        logger.error(f"Failed to initialize audit tables: {e}")

def log_query_audit(
    pg_engine,
    user_id: str,
    user_name: str,
    user_role: str,
    question_text: str,
    generated_sql: str,
    execution_status: str,
    execution_time_ms: int,
    rows_returned: int = 0,
    error_message: str = None
):
    """
    Record an execution audit log entry.
    """
    try:
        from sqlalchemy import text
        sql = text("""
            INSERT INTO public.query_audit_logs 
            (user_id, user_name, user_role, question_text, generated_sql, execution_status, execution_time_ms, rows_returned, error_message, created_at)
            VALUES (:user_id, :user_name, :user_role, :question, :sql_text, :status, :exec_time, :rows_cnt, :err_msg, NOW())
        """)
        with pg_engine.connect() as conn:
            conn.execute(sql, {
                "user_id": user_id or "ANONYMOUS",
                "user_name": user_name or "Anonymous User",
                "user_role": user_role or "USER",
                "question": question_text,
                "sql_text": generated_sql,
                "status": execution_status,
                "exec_time": execution_time_ms,
                "rows_cnt": rows_returned,
                "err_msg": error_message
            })
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log query audit: {e}")

def log_token_usage(
    pg_engine,
    user_id: str,
    user_name: str,
    user_role: str,
    conversation_id: str,
    question_text: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int
) -> Dict[str, float]:
    """
    Calculate and record token usage & cost.
    """
    cost_info = calculate_token_cost(model_name, prompt_tokens, completion_tokens)
    
    try:
        from sqlalchemy import text
        sql = text("""
            INSERT INTO public.chat_usage_logs
            (user_id, user_name, user_role, conversation_id, question_text, model_name, prompt_tokens, completion_tokens, total_tokens, cost_usd, cost_vnd, created_at)
            VALUES (:user_id, :user_name, :user_role, :conv_id, :question, :model, :p_tok, :c_tok, :t_tok, :cost_usd, :cost_vnd, NOW())
        """)
        with pg_engine.connect() as conn:
            conn.execute(sql, {
                "user_id": user_id or "ANONYMOUS",
                "user_name": user_name or "Anonymous User",
                "user_role": user_role or "USER",
                "conv_id": conversation_id or "",
                "question": question_text,
                "model": model_name,
                "p_tok": prompt_tokens,
                "c_tok": completion_tokens,
                "t_tok": cost_info["total_tokens"],
                "cost_usd": cost_info["cost_usd"],
                "cost_vnd": cost_info["cost_vnd"]
            })
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log token usage: {e}")
        
    return cost_info

def query_audit_reports(
    pg_engine,
    requesting_user_role: str,
    filter_user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query audit logs and token cost reports with User filtering.
    Restricted to C_LEVEL and SUPER_ADMIN roles only.
    """
    if not is_user_authorized_for_audit(requesting_user_role):
        return {
            "authorized": False,
            "error": "⛔ Access Denied: Audit Logs are restricted to C-Level and Super Admin accounts only."
        }
        
    from sqlalchemy import text
    
    where_clauses = ["1=1"]
    params = {}
    
    if filter_user_id:
        where_clauses.append("(user_id = :filter_user OR LOWER(user_name) LIKE LOWER(:filter_user_name))")
        params["filter_user"] = filter_user_id
        params["filter_user_name"] = f"%{filter_user_id}%"
        
    if start_date:
        where_clauses.append("created_at >= :start_date")
        params["start_date"] = start_date
        
    if end_date:
        where_clauses.append("created_at <= :end_date")
        params["end_date"] = end_date
        
    where_str = " AND ".join(where_clauses)
    
    audit_sql = text(f"""
        SELECT id, user_id, user_name, user_role, question_text, generated_sql, execution_status, execution_time_ms, rows_returned, created_at
        FROM public.query_audit_logs
        WHERE {where_str}
        ORDER BY created_at DESC
        LIMIT 100
    """)
    
    usage_summary_sql = text(f"""
        SELECT 
            COUNT(*) AS total_questions,
            COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
            COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
            COALESCE(SUM(total_tokens), 0) AS grand_total_tokens,
            COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
            COALESCE(SUM(cost_vnd), 0) AS total_cost_vnd
        FROM public.chat_usage_logs
        WHERE {where_str}
    """)
    
    user_breakdown_sql = text(f"""
        SELECT 
            user_id, user_name, user_role,
            COUNT(*) AS question_count,
            SUM(total_tokens) AS user_total_tokens,
            SUM(cost_usd) AS user_cost_usd,
            SUM(cost_vnd) AS user_cost_vnd
        FROM public.chat_usage_logs
        WHERE {where_str}
        GROUP BY user_id, user_name, user_role
        ORDER BY user_cost_vnd DESC
    """)
    
    try:
        with pg_engine.connect() as conn:
            audit_rows = conn.execute(audit_sql, params).mappings().all()
            summary_row = conn.execute(usage_summary_sql, params).mappings().first()
            user_rows = conn.execute(user_breakdown_sql, params).mappings().all()
            
            return {
                "authorized": True,
                "summary": dict(summary_row) if summary_row else {},
                "user_breakdown": [dict(r) for r in user_rows],
                "audit_logs": [dict(r) for r in audit_rows]
            }
    except Exception as e:
        logger.error(f"Failed to query audit reports: {e}")
        return {"authorized": True, "error": str(e), "summary": {}, "user_breakdown": [], "audit_logs": []}
