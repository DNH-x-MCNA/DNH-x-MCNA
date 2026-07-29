# -*- coding: utf-8 -*-
"""
Ghi log chi phi THUC TE (khong phai uoc tinh truoc) sau moi lan goi Claude API - dung so lieu `usage`
that ma API tra ve. CHI ghi log + canh bao neu vuot tran $0.045 - KHONG tu dong can thiep vao noi dung/
chat luong cau tra loi (da thong nhat voi nguoi dung: uu tien do chinh xac hon la kiem soat chi phi
tuyet doi o quy mo hien tai).

Ngoai canh bao per-request, con theo doi TONG chi phi LUY KE trong THANG HIEN TAI so voi ngan sach
MONTHLY_BUDGET_USD (nguoi dung dat $50/thang, 24/07/2026) - ghi canh bao rieng khi vuot 80%/100% ngan
sach. Van CHI la canh bao (ghi log/file), KHONG tu dong chan chatbot - giu dung nguyen tac cu.
"""
import os, json, datetime as dt
from pricing import compute_cost_usd, HARD_COST_LIMIT_USD, MONTHLY_BUDGET_USD, MONTHLY_WARN_RATIO

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "cost_log.jsonl")
MONTHLY_ALERT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "monthly_cost_alert.txt")
# Danh dau thang da bao 80%/100% - tranh ghi canh bao lap lai moi cau hoi trong cung thang (chi ghi
# khi VUA vuot moc, giu file log gon nhe de doc).
_alerted_months: set = set()


def compute_and_log_cost(usage, model: str, question: str = "", session_id: str = "",
                          username: str = "") -> float:
    """usage: object tra ve tu response.usage cua Anthropic SDK (co input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens). Tra ve cost USD cua lan goi nay.

    username (29/07/2026): GHI THANG vao log de quy chi phi cho tung nguoi. Truoc day dashboard phai
    NOI NGUOC qua session_id sang audit_log.jsonl, cach do bo sot rat nhieu:
      - audit_log chi ghi khi chay SQL / goi tool bao cao. Luot nao AI tra loi thang (khong goi tool)
        van TON TIEN nhung khong co dong audit nao de noi vao.
      - audit_log moi bat dau ghi session_id tu 28/07; moi ban ghi truoc do khong the khop.
    Ket qua: 89% chi phi do duoc ngay 29/07 khong quy duoc cho ai. Ghi thang username o day xoa han
    su phu thuoc vao phep noi - moi lan goi API deu biet ro la cua ai."""
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

    cost = compute_cost_usd(model, input_tokens, output_tokens, cache_read, cache_write)

    entry = {
        "ts": dt.datetime.now().isoformat(),
        "session_id": session_id,
        "username": username or "",
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

    _check_monthly_budget()

    return cost


def get_current_month_cost_usd() -> float:
    """Cong don cost_usd cua tat ca dong log co ts thuoc THANG HIEN TAI (theo gio may chay backend)."""
    now = dt.datetime.now()
    total = 0.0
    if not os.path.exists(LOG_PATH):
        return total
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                ts = dt.datetime.fromisoformat(row["ts"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if ts.year == now.year and ts.month == now.month:
                total += row.get("cost_usd", 0.0)
    return total


def _check_monthly_budget() -> None:
    """Ghi canh bao vao MONTHLY_ALERT_PATH khi tong chi phi thang hien tai vuot 80% hoac 100% ngan
    sach $50 - chi ghi 1 LAN moi moc/thang (dung _alerted_months tranh spam file)."""
    now = dt.datetime.now()
    month_key = f"{now.year}-{now.month:02d}"
    total = get_current_month_cost_usd()
    warn_threshold = MONTHLY_BUDGET_USD * MONTHLY_WARN_RATIO

    level = None
    if total >= MONTHLY_BUDGET_USD and f"{month_key}-100" not in _alerted_months:
        level = "VUOT 100%"
        _alerted_months.add(f"{month_key}-100")
    elif total >= warn_threshold and f"{month_key}-80" not in _alerted_months:
        level = f"VUOT {int(MONTHLY_WARN_RATIO*100)}%"
        _alerted_months.add(f"{month_key}-80")

    if level:
        os.makedirs(os.path.dirname(MONTHLY_ALERT_PATH), exist_ok=True)
        with open(MONTHLY_ALERT_PATH, "a", encoding="utf-8") as f:
            f.write(
                f"[{now.isoformat()}] {level} ngan sach thang {month_key}: "
                f"da dung ${total:.2f} / ${MONTHLY_BUDGET_USD:.2f}\n"
            )
