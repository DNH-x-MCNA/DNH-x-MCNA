# -*- coding: utf-8 -*-
"""
Bang gia model Claude ($/1 trieu token) - tach rieng khoi logic tinh cost de de cap nhat khi gia doi
(vd gia gioi thieu Sonnet 5 het han 31/08/2026, tang tu $2/$10 len $3/$15). LUON kiem tra lai
claude.com/pricing truoc khi sua so lieu o day.

Don vi: USD / 1,000,000 token.
"""

MODEL_PRICING = {
    "claude-sonnet-5": {
        "input": 2.00,        # gia gioi thieu den 31/08/2026, sau do $3.00
        "output": 10.00,      # gia gioi thieu den 31/08/2026, sau do $15.00
        "cache_read": 0.20,   # 0.1x input - he so chuan Anthropic
        "cache_write": 4.00,  # 2x input - he so cache TTL 1 GIO (khong phai 5 phut). nl2sql.py goi
                               # cache_control voi ttl="1h" (dong 519/753/759), nen he so dung la 2x
                               # chu khong phai 1.25x cua TTL 5 phut. Sua 05/08/2026 - truoc do ghi
                               # 2.50 (1.25x) lam MOI bao cao chi phi cache-write bi bao THIEU ~37%.
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_write": 1.25,
    },
    "claude-opus-4-8": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_write": 6.25,
    },
}

# Ty gia quy doi USD -> VND hien thi tren dashboard va bao cao. NGUON DUY NHAT - truoc day so 25400
# bi chep cung o 8 cho trong 4 file (main.py x4, report_templates.py, audit_cost.py, page.tsx), sua
# mot cho la sot cac cho con lai. Cap nhat 29/07/2026 theo ty gia thuc te 26.334,50.
USD_TO_VND_RATE = 26334.50

SOFT_COST_LIMIT_USD = 0.03   # tran "mem" - phan lon request nen duoi muc nay
HARD_COST_LIMIT_USD = 0.045  # tran "cung" - vuot muc nay thi ghi canh bao (KHONG tu dong can thiep)

MONTHLY_BUDGET_USD = 50.00        # tran ngan sach thang nguoi dung dat (24/07/2026)
MONTHLY_WARN_RATIO = 0.8          # canh bao SOM khi da dung 80% ngan sach ($40)


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int,
                      cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    p = MODEL_PRICING.get(model)
    if not p:
        return 0.0
    return (
        (input_tokens or 0) / 1_000_000 * p["input"]
        + (output_tokens or 0) / 1_000_000 * p["output"]
        + (cache_read_tokens or 0) / 1_000_000 * p["cache_read"]
        + (cache_write_tokens or 0) / 1_000_000 * p["cache_write"]
    )
