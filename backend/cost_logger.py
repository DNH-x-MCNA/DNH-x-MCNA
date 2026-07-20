# -*- coding: utf-8 -*-
"""
Ghi log chi phi THUC TE (khong phai uoc tinh truoc) sau moi lan goi Claude API - dung so lieu `usage`
that ma API tra ve. CHI ghi log + canh bao neu vuot tran $0.045 - KHONG tu dong can thiep vao noi dung/
chat luong cau tra loi (da thong nhat voi nguoi dung: uu tien do chinh xac hon la kiem soat chi phi
tuyet doi o quy mo hien tai).
"""
import os, json, datetime as dt
from pricing import compute_cost_usd, HARD_COST_LIMIT_USD

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "cost_log.jsonl")


def compute_and_log_cost(usage, model: str, question: str = "", session_id: str = "") -> float:
    """usage: object tra ve tu response.usage cua Anthropic SDK (co input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens). Tra ve cost USD cua lan goi nay."""
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

    cost = compute_cost_usd(model, input_tokens, output_tokens, cache_read, cache_write)

    entry = {
        "ts": dt.datetime.now().isoformat(),
        "session_id": session_id,
        "question_preview": (question or "")[:120],
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "cost_usd": round(cost, 6),
    }
    if cost > HARD_COST_LIMIT_USD:
        entry["warn"] = f"Vuot tran ${HARD_COST_LIMIT_USD}/luot"

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return cost
