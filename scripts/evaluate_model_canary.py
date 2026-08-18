# -*- coding: utf-8 -*-
r"""Canary danh gia model theo nghiep vu, khong co du bao tuong lai.

Day la lop KIEM TRA DUONG DI cua model: dung tool chuan, khong tu choi cau nghiep vu va khong tu
bịa khi bo tool. So lieu dung/khop SQL Server duoc chot boi business_stress_suite.py; moi case o day
deu tro toi checker SQL tuong ung de hai phep kiem tra khong bi nham thanh mot.

Chay tren may co SQL + API key, vi script goi chatbot that:
    python scripts\evaluate_model_canary.py --label sonnet-5
    python scripts\evaluate_model_canary.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
# APPEND, khong insert(0): script nay cung duoc tests/test_model_canary.py nap dong bang importlib
# trong CUNG mot tien trinh pytest. insert(0) day backend/ len dau sys.path, che mat main.py o goc
# repo va lam tests/test_phase1_phase2.py vo ngay luc thu thap ("cannot import name send_daily_digest
# from main"). Da dinh dung loi nay 3 lan o cac file test khac (12-17/08/2026) - day la nguon con sot.
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AUDIT_LOG = BACKEND / "logs" / "audit_log.jsonl"
RESULTS_DIR = ROOT / "results"
REFUSAL_MARKERS = ("qua phuc tap", "quá phức tạp", "vui long hoi cu the", "vui lòng hỏi cụ thể")
FUTURE_FEATURE_MARKERS = ("dự báo", "du bao", "forecast", "tương lai", "tuong lai")


@dataclass(frozen=True)
class CanaryCase:
    case_id: str
    group: str
    question: str
    required_tools: tuple[str, ...]
    sql_checker_id: str
    note: str


# Khong dung so hard-code: du lieu live thay doi. Cac con so phai doi chieu qua checker SQL ghi o
# sql_checker_id, con canary nay bat dung tool va bat hanh vi "tu choi / tu bia" cua model.
CANARY_CASES = (
    CanaryCase("REV-01", "Doanh thu", "Doanh thu tháng 7/2026 tách OTC và ETC; mỗi kênh có bao nhiêu hóa đơn?", ("get_revenue_by_channel",), "REV_CHANNEL", "Nguồn chuẩn view Total."),
    CanaryCase("REV-02", "Doanh thu", "So với tháng 6/2026, doanh thu tháng 7/2026 tăng hay giảm bao nhiêu tiền và bao nhiêu phần trăm?", ("compare_periods",), "REV_COMPARE", "Hai kỳ trọn tháng."),
    CanaryCase("REV-03", "Doanh thu", "Doanh thu tháng 7/2026 chia theo ba miền và OTC/ETC thế nào?", ("get_revenue_by_region",), "REV_REGION", "Không mất khách thiếu vùng."),
    CanaryCase("REV-04", "Dữ liệu nguồn", "Dữ liệu hóa đơn OTC và ETC mới nhất đang đến ngày nào, đồng bộ lúc nào?", ("get_revenue_by_channel",), "REV_FRESHNESS", "Business date tách sync time."),
    CanaryCase("KPI-01", "KPI", "Top 20 nhân viên theo tỷ lệ hoàn thành tháng 7; ai target bằng 0 phải tách riêng.", ("get_kpi_ranking", "get_employee_kpi"), "KPI_EMPLOYEE", "Không xếp phần trăm target 0."),
    CanaryCase("KPI-02", "KPI", "Bao nhiêu TDV đạt KPI 80% nhưng chưa đạt đủ chỉ tiêu 100%?", ("get_employee_kpi", "get_kpi_ranking"), "KPI_THRESHOLDS", "Mốc 80% và 100% khác nhau."),
    CanaryCase("KPI-03", "KPI", "Tổng doanh số theo tầng TP, QLV và nhân viên tuyến dưới có bằng nhau không; vì sao không cộng các tầng?", ("get_revenue_tree",), "KPI_LAYER_RECON", "Không cộng roll-up chồng tầng."),
    CanaryCase("DEBT-01", "Công nợ", "Tổng dư nợ, nợ quá hạn và tỷ lệ quá hạn hiện tại của OTC và ETC?", ("get_receivables_overview",), "DEBT_SUMMARY", "SQL Server SP là nguồn chuẩn."),
    CanaryCase("DEBT-02", "Công nợ", "Cơ cấu nợ quá hạn 1-15, 16-30, 31-45 và trên 45 ngày theo từng kênh?", ("get_receivables_overview",), "DEBT_AGING", "Tổng bucket phải khớp quá hạn."),
    CanaryCase("DEBT-03", "Công nợ", "Tìm khách đồng thời doanh thu lớn, nợ quá hạn cao và sức mua giảm.", ("get_customer_revenue_debt_risk",), "DEBT_RISK", "Một tool tổng hợp, không ghép bừa."),
    CanaryCase("SAL-01", "Lương thưởng", "Cách tính và bậc tiền thưởng V15 cho TDV là gì?", ("get_salary_bonus_policy",), "SALARY_RULES", "Quy tắc + snapshot chốt."),
    CanaryCase("SAL-02", "Lương thưởng", "Cách tính và bậc tiền thưởng V22 cho TDV là gì?", ("get_salary_bonus_policy",), "SALARY_RULES", "Không suy diễn từ V15."),
    CanaryCase("SAL-03", "Lương thưởng", "Cách tính và bậc tiền thưởng V25 cho QLV là gì?", ("get_salary_bonus_policy",), "SALARY_RULES", "Không bịa bậc thưởng."),
    CanaryCase("SAL-04", "Lương thưởng", "Thưởng ASO được tính thế nào; ASO trong dữ liệu này là gì?", ("get_salary_bonus_policy",), "SALARY_ASO", "ASO là chỉ tiêu/khoản thưởng, không phải chức danh."),
    CanaryCase("SAL-05", "Lương thưởng", "Top 30 nhân viên có tổng thưởng kinh doanh cao nhất kỳ lương tháng 7/2026?", ("get_salary_ranking",), "SALARY_RANK", "Không gọi là tổng thu nhập."),
    CanaryCase("CTKM-01", "Khuyến mãi", "Đánh giá hiệu quả từng chương trình khuyến mãi theo doanh thu, khách hàng tham gia và sản phẩm tháng 7/2026.", ("get_promotion_effectiveness",), "PROMO_EFFECT", "Không nhóm theo cột CTKM ghi chú tự do."),
    CanaryCase("CUS-01", "Khách hàng", "Top 20 khách hàng doanh thu lớn nhất tháng 7 là ai?", ("get_top_customers",), "CUS_TOP", "Không cộng OTC/ETC hai lần."),
    CanaryCase("PRD-01", "Sản phẩm", "Top 20 sản phẩm tháng 7 theo doanh thu và số lượng bán thật?", ("get_top_products",), "PRD_TOP", "Không tính hàng giá 0 vào số lượng bán thật."),
)


def _assert_cases_are_current() -> None:
    for case in CANARY_CASES:
        question = case.question.lower()
        if any(marker in question for marker in FUTURE_FEATURE_MARKERS):
            raise ValueError(f"{case.case_id} co noi dung da bi tat: {case.question}")
        if not case.required_tools or not case.sql_checker_id:
            raise ValueError(f"{case.case_id} thieu tool bat buoc hoac SQL checker")


def _audit_by_session(session_ids: set[str]) -> dict[str, set[str]]:
    found = {session_id: set() for session_id in session_ids}
    if not AUDIT_LOG.is_file():
        return found
    with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = item.get("session_id")
            if session_id not in found:
                continue
            match = re.search(r"<template:([a-zA-Z_]+)>", str(item.get("sql") or ""))
            if match:
                found[session_id].add(match.group(1))
    return found


def evaluate(cases: tuple[CanaryCase, ...], label: str, delay_seconds: float) -> list[dict]:
    import nl2sql

    results: list[dict] = []
    for index, case in enumerate(cases, 1):
        session_id = f"canary-{label}-{case.case_id}-{uuid.uuid4().hex[:8]}"
        print(f"[{index}/{len(cases)}] {case.case_id} {case.question[:70]}", flush=True)
        started = time.monotonic()
        try:
            response = nl2sql.ask(case.question, session_id=session_id,
                                 username="model-canary", scope_role="c_level")
            answer, error = str(response.get("answer") or ""), None
        except Exception as exc:  # Ket qua exception cung la mot loi canary, khong dung ca suite.
            answer, error = "", f"{type(exc).__name__}: {exc}"
        results.append({"case": asdict(case), "session_id": session_id, "answer": answer,
                        "error": error, "duration_seconds": round(time.monotonic() - started, 2)})
        if delay_seconds:
            time.sleep(delay_seconds)

    audit = _audit_by_session({item["session_id"] for item in results})
    for item in results:
        tools = sorted(audit[item["session_id"]])
        required = set(item["case"]["required_tools"])
        lower_answer = item["answer"].lower()
        errors = []
        if item["error"]:
            errors.append(item["error"])
        if any(marker in lower_answer for marker in REFUSAL_MARKERS):
            errors.append("chatbot tu choi cau nghiep vu")
        if not required.intersection(tools):
            errors.append(f"thieu tool chuan: can mot trong {sorted(required)}, da goi {tools or 'khong co'}")
        item.update({"tools_called": tools, "passed": not errors, "errors": errors})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="current-model", help="Nhan cua lan chay (vi du sonnet-5).")
    parser.add_argument("--limit", type=int, default=None, help="Chay N case dau tien de smoke test.")
    parser.add_argument("--delay", type=float, default=7.0, help="Khoang cach giua cac cau hoi that.")
    parser.add_argument("--dry-run", action="store_true", help="In manifest, khong goi model/API.")
    parser.add_argument("--output", default=None, help="File JSON ket qua; mac dinh results/model-canary-*.json.")
    args = parser.parse_args()
    _assert_cases_are_current()
    cases = CANARY_CASES[:args.limit] if args.limit else CANARY_CASES
    if args.dry_run:
        print(json.dumps([asdict(case) for case in cases], ensure_ascii=False, indent=2))
        return 0

    results = evaluate(cases, args.label, args.delay)
    passed = sum(item["passed"] for item in results)
    payload = {"label": args.label, "run_at": dt.datetime.now().isoformat(),
               "passed": passed, "total": len(results), "results": results}
    output = Path(args.output) if args.output else RESULTS_DIR / f"model-canary-{args.label}-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"KET QUA: {passed}/{len(results)} dat; file: {output}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
