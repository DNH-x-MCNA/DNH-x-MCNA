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
        "cache_write": 4.00,  # 2x input - he so cache TTL 1 GIO. Sua 05/08/2026 - truoc do ghi
                               # 2.50 (1.25x cua TTL 5 phut) lam MOI bao cao chi phi cache-write bi
                               # bao THIEU ~37%.
                               #
                               # HAN CHE DO DAC (06/08/2026): tu nay nl2sql.py dung HAI TTL khac nhau
                               # - system prompt + tool definitions van "1h" (2x = 4.00), rieng
                               # breakpoint tren tool_results ha ve mac dinh 5 phut (1.25x = 2.50) vi
                               # chi doc lai trong cung 1 cau hoi. Bang gia nay chi co MOT don gia
                               # cache_write nen phan ghi 5 phut dang bi tinh theo gia 1 gio ->
                               # bao cao chi phi cache-write hoi CAO HON thuc te (nguoc voi loi cu la
                               # bao thap hon). Chua kiem chung duoc API co tra ve token ghi tach
                               # rieng theo tung TTL hay khong (can goi that, luc sua thi API key dang
                               # ngat). Neu co, tach thanh 2 don gia rieng va sua cost_logger.py.
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

    # 13/08/2026 - DeepSeek V4, dung de THU NGHIEM doi nha cung cap (xem LLM_BASE_URL trong nl2sql.py).
    # DeepSeek tinh gia theo GIO: gia cao diem gap doi gia thap diem. Bang nay chi co MOT don gia nen
    # co y lay GIA CAO DIEM - bao cao chi phi se cao hon thuc te thay vi thap hon. Chon huong nay vi
    # 05/08/2026 da dinh mot lan bao THIEU 37% chi phi cache-write, va bao thieu thi nguy hiem hon
    # bao thua (tuong con re, dung thoai mai, den cuoi thang moi vo le).
    #
    # DeepSeek KHONG tinh tien rieng cho viec ghi cache - gia "cache miss" da bao gom. Nen cache_write
    # de 0, KHONG phai vi chua biet gia ma vi that su khong co khoan nay.
    "deepseek-v4-pro": {
        "input": 1.32,        # cache miss, cao diem (thap diem 0.66)
        "output": 3.96,       # cao diem (thap diem 1.98)
        "cache_read": 0.044,  # cache hit, cao diem (thap diem 0.022)
        "cache_write": 0.0,
    },
    "deepseek-v4-flash": {
        "input": 0.44,        # cache miss, cao diem (thap diem 0.22)
        "output": 1.32,       # cao diem (thap diem 0.66)
        "cache_read": 0.014,  # cache hit, cao diem (thap diem 0.007)
        "cache_write": 0.0,
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


def api_provider_for_model(model: str) -> str:
    """Tra ten nha cung cap de hien thi; chi suy ra tu model da ghi trong cost log."""
    normalized = (model or "").strip().lower()
    if normalized.startswith("deepseek-"):
        return "DeepSeek"
    if normalized.startswith("claude-"):
        return "Anthropic"
    if normalized.startswith("gemini-"):
        return "Google Gemini"
    if normalized.startswith(("gpt-", "o1", "o3", "o4")):
        return "OpenAI"
    return "Không xác định" if not normalized else normalized


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int,
                      cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    p = MODEL_PRICING.get(model)
    if not p:
        # 13/08/2026: truoc day lang le tra 0.0 - doi model ma quen them gia thi MOI bao cao chi phi
        # deu ra 0d, trong y het "dung it tien", khong ai nghi la thieu bang gia. Gio ghi canh bao
        # ra log de con biet. Van tra 0.0 chu KHONG nem loi: chi phi sai khong duoc lam vo cau tra loi.
        import logging
        logging.getLogger(__name__).warning(
            "Khong co bang gia cho model %r - moi chi phi cua model nay se ghi 0d. "
            "Them vao MODEL_PRICING (backend/pricing.py) truoc khi tin bao cao chi phi.", model)
        return 0.0
    return (
        (input_tokens or 0) / 1_000_000 * p["input"]
        + (output_tokens or 0) / 1_000_000 * p["output"]
        + (cache_read_tokens or 0) / 1_000_000 * p["cache_read"]
        + (cache_write_tokens or 0) / 1_000_000 * p["cache_write"]
    )
