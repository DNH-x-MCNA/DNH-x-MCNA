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
        "cache_read": 0.20,   # ~10% gia input goc
        "cache_write": 2.50,  # cache creation (ghi cache lan dau) - uoc tinh ~1.25x input, dieu chinh
                               # lai neu Anthropic cong bo gia chinh xac rieng cho model nay
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

SOFT_COST_LIMIT_USD = 0.03   # tran "mem" - phan lon request nen duoi muc nay
HARD_COST_LIMIT_USD = 0.045  # tran "cung" - vuot muc nay thi ghi canh bao (KHONG tu dong can thiep)


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
