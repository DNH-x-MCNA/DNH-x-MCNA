# -*- coding: utf-8 -*-
"""Chạy TOÀN BỘ 90 câu nghiệp vụ (scripts/business_stress_suite.py) qua chatbot thật và
chấm điểm tự động những gì có thể chấm CHẮC CHẮN, còn lại giao cho người kiểm.

Bối cảnh: scripts/evaluate_model_canary.py (18/08/2026) là canary NHANH - 18 câu, đủ để
biết model có "đi đúng đường" hay không sau mỗi lần đổi cấu hình/nhà cung cấp. Script này
là bài kiểm ĐẦY ĐỦ - toàn bộ 90 câu golden, có đối chiếu số với SQL Server thật khi làm được
một cách AN TOÀN, chạy trước khi mở production cho vai trò mới hoặc đổi model mặc định.

=== TRIẾT LÝ CHẤM ĐIỂM: KHÔNG BỊA ĐỘ TIN CẬY ===
business_stress_suite.py tự ghi rõ trong docstring: "Không tự động phán PASS bằng so khớp
câu chữ; người kiểm thử đối chiếu số, kỳ, phạm vi và cảnh báo." Script này tôn trọng đúng
nguyên tắc đó, KHÔNG cố tự động hoá phần không thể tự động hoá đáng tin:

  TỰ ĐỘNG CHẤM ĐƯỢC (áp dụng cho cả 90 câu, không có ngoại lệ - nếu sai là sai thật):
    - Có lỗi hệ thống khi hỏi không.
    - Có bị từ chối "câu hỏi quá phức tạp" không (chatbot có dữ liệu, không được từ chối).
    - Có TỪ NGỮ DỰ BÁO/ƯỚC TÍNH lọt vào câu trả lời không - dự báo bị khoá tuyệt đối, không
      có ngoại lệ theo câu hỏi nên kiểm tra được trên toàn bộ 90 câu.
    - Có gọi tool nào không - hỏi số liệu nghiệp vụ mà 0 tool nào chạy là dấu hiệu trực tiếp
      của việc tự bịa, bất kể tool cụ thể nào "đáng lẽ" phải gọi (không đoán tool đúng, chỉ
      bắt trường hợp KHÔNG tool nào).

  ĐỐI CHIẾU SỐ VỚI SQL SERVER - CHỈ khi kết quả checker "gọn" (<=3 dòng, <=12 ô số): mọi số
  gốc phải xuất hiện nguyên vẹn (theo dãy chữ số, bỏ hết dấu phân cách) trong câu trả lời.
  Loại checker dạng "top N" (vd top 20 khách hàng) KHÔNG được tự chấm theo cách này - đối
  chiếu 1-trong-20 dòng nào đúng cần hiểu ý câu hỏi, không phải việc máy nên tự quyết. Ground
  truth vẫn được đính kèm nguyên trong báo cáo để người kiểm đối chiếu nhanh, đúng tinh thần
  gốc của business_stress_suite.py.

  KHÔNG cố chấm: đúng tool cụ thể (chưa có ai hạ bút xác nhận tool nào đúng cho từng câu/90),
  đúng phạm vi vai trò (audience trong BusinessCase chỉ là NHÃN tài liệu, không map ra
  scope_role/scope_area thật - tự bịa mapping đó rủi ro hơn là để trống), SQL ghi (đã có
  _FORBIDDEN regex + test riêng ở backend/query_engine.py, không lặp lại ở đây).

Chạy (cần backend có ANTHROPIC_API_KEY/LLM_* và kết nối SQL Server thật - máy 24):
    cd C:\\dnh_chatbot
    python scripts\\run_business_evaluation.py --label sonnet-5
    python scripts\\run_business_evaluation.py --group "Công nợ" --label smoke-debt
    python scripts\\run_business_evaluation.py --skip-ground-truth   # may khong noi duoc SQL Server
    python scripts\\run_business_evaluation.py --dry-run             # chi in danh sach, khong goi gi
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import io
import json
import os
import re
import statistics
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
# APPEND, khong insert(0): xem ghi chu day du trong scripts/evaluate_model_canary.py va
# tests/test_tool_merger.py - insert(0) tung lam vo tests/test_phase1_phase2.py 4 lan.
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AUDIT_LOG = BACKEND / "logs" / "audit_log.jsonl"
COST_LOG = BACKEND / "logs" / "cost_log.jsonl"
RESULTS_DIR = ROOT / "results"

REFUSAL_MARKERS = ("qua phuc tap", "quá phức tạp", "vui long hoi cu the", "vui lòng hỏi cụ thể")
# Chi kiem trong CAU TRA LOI (khong phai cau hoi) - khac evaluate_model_canary.py von chi kiem
# tu ngu cua CASE luc dinh nghia. O day bat dung luc model TU SINH ra tu du bao trong luc tra
# loi, du cau hoi hoan toan khong nhac toi.
FORECAST_LEAK_MARKERS = ("dự báo", "du bao", "ước tính", "uoc tinh", "forecast")

# "gon" = du nho de doi chieu CHAC CHAN bang may, khong doan y nguoi hoi.
COMPACT_MAX_ROWS = 3
COMPACT_MAX_NUMERIC_CELLS = 12
MIN_DIGIT_RUN = 5  # duoi muc nay de tranh khop nham so trang/phan tram/thu tu dong


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _digits_of(value: Any) -> str:
    """Chuoi chu so cua 1 O DU LIEU SQL (khong phai van ban tu do), bo het dau phan cach/don vi.
    So thuc/Decimal duoc lam tron ve so nguyen truoc (doanh thu/KPI trong mien nay luon la don
    vi nguyen), tranh '39327016119.0' hay ky phap khoa hoc lam sai lech so sanh.

    CO Y bo qua chuoi ky tu (str) - KHONG rut chu so tu do: cot ma khach hang/nhan vien tra ve
    tu SQL la string (vd "HCM04298", "TM23110128"). Neu rut '04298' tu "HCM04298" roi doi hoi
    no phai xuat hien trong cau tra loi thi mot cot MA lai bien thanh mot 'con so can doi chieu'
    khong co that - da bat duoc bang test truoc khi len production."""
    if value is None or isinstance(value, (bool, str)):
        return ""
    if isinstance(value, int):
        return re.sub(r"\D", "", str(value))
    if isinstance(value, float):
        try:
            return re.sub(r"\D", "", str(int(round(value))))
        except (ValueError, OverflowError):
            return ""
    try:  # decimal.Decimal va cac kieu tuong tu tu driver SQL
        return re.sub(r"\D", "", str(int(round(float(value)))))
    except (TypeError, ValueError):
        return ""


# Khop CA HAI dang: so da dinh dang theo nhom 3 chu so ("39.327.016.119" hoac kieu Anh-My
# "39,327,016,119"), VA day so tho khong dau phan cach. Khong dung \d+ don gian: dau cham/phay
# ngan nghin CAT chuoi so THAT thanh nhieu cum ngan ("39", "327", "016", "119"), khong cum nao
# du dai de vuot MIN_DIGIT_RUN - lam MOI so dung dinh dang deu bi bao "thieu", du cau tra loi
# hoan toan chinh xac. Da bat duoc bang test truoc khi len production (xem
# test_significant_digit_runs_bo_qua_so_qua_ngan).
_FORMATTED_NUMBER = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")


def _significant_digit_runs(text: str, min_len: int = MIN_DIGIT_RUN) -> set[str]:
    runs = set()
    for match in _FORMATTED_NUMBER.findall(text or ""):
        digits = re.sub(r"\D", "", match)
        if len(digits) >= min_len:
            runs.add(digits)
    return runs


def _ground_truth_numbers(ground_truth: dict) -> set[str]:
    runs: set[str] = set()
    for row in ground_truth.get("rows", []):
        for cell in row:
            digits = _digits_of(cell)
            if len(digits) >= MIN_DIGIT_RUN:
                runs.add(digits)
    return runs


def _is_compact(ground_truth: dict) -> bool:
    rows = ground_truth.get("rows", [])
    if len(rows) > COMPACT_MAX_ROWS:
        return False
    numeric_cells = sum(
        1 for row in rows for cell in row
        if isinstance(cell, (int, float)) or (isinstance(cell, str) and re.fullmatch(r"[\d.,\s]+", cell or ""))
    )
    return numeric_cells <= COMPACT_MAX_NUMERIC_CELLS


def _audit_by_session(session_ids: set[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {sid: set() for sid in session_ids}
    if not AUDIT_LOG.is_file():
        return found
    with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid not in found:
                continue
            match = re.search(r"<template:([a-zA-Z_]+)>", str(item.get("sql") or ""))
            if match:
                found[sid].add(match.group(1))
    return found


def _cost_by_session(session_ids: set[str]) -> dict[str, float]:
    cost: dict[str, float] = {sid: 0.0 for sid in session_ids}
    if not COST_LOG.is_file():
        return cost
    with io.open(COST_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid in cost:
                cost[sid] += float(item.get("cost_usd") or 0.0)
    return cost


def _fetch_ground_truth(suite, checker_id: str, *, scope_area: Optional[str],
                        skip: bool) -> dict:
    if skip:
        return {"status": "bo_qua", "reason": "chay voi --skip-ground-truth"}
    checker = suite.CHECKERS.get(checker_id)
    if checker is None:
        return {"status": "loi", "reason": f"khong tim thay checker '{checker_id}'"}
    try:
        return suite._execute_checker(checker, scope_area=scope_area)
    except Exception as exc:  # May dev khong ket noi duoc SQL Server - ghi ro, KHONG coi la PASS.
        return {"status": "loi", "reason": f"{type(exc).__name__}: {exc}"}


def grade_case(case, answer: str, error: Optional[str], tools_called: list[str],
              ground_truth: dict) -> dict:
    problems: list[dict] = []

    if error:
        problems.append({"severity": "P0", "code": "loi_he_thong", "detail": error})

    lower = (answer or "").lower()
    if any(marker in lower for marker in REFUSAL_MARKERS):
        problems.append({"severity": "P0", "code": "tu_choi",
                         "detail": "Chatbot tu choi voi ly do 'qua phuc tap' - vi pham gate "
                                   "'0 tu choi voi cau co du dieu ho tro'."})

    leaked = [m for m in FORECAST_LEAK_MARKERS if m in lower]
    if leaked:
        problems.append({"severity": "P0", "code": "lo_du_bao",
                         "detail": f"Cau tra loi chua tu ngu du bao bi cam: {leaked}"})

    if not error and not tools_called:
        problems.append({"severity": "P0", "code": "khong_goi_tool",
                         "detail": "Tra loi so lieu nghiep vu ma khong tool nao duoc goi - "
                                   "dau hieu truc tiep cua tu bia du lieu."})

    gt_status = ground_truth.get("status")
    ground_truth_check = "khong_ap_dung"
    if gt_status == "ok" and not error:
        if _is_compact(ground_truth):
            gt_numbers = _ground_truth_numbers(ground_truth)
            ans_numbers = _significant_digit_runs(answer)
            missing = gt_numbers - ans_numbers
            if gt_numbers and missing:
                problems.append({"severity": "P0", "code": "sai_so_lieu",
                                 "detail": f"Thieu {len(missing)} so tu SQL Server trong cau "
                                           f"tra loi: {sorted(missing)[:5]}"})
                ground_truth_check = "fail"
            elif gt_numbers:
                ground_truth_check = "pass"
            else:
                ground_truth_check = "khong_co_so_de_doi_chieu"
        else:
            ground_truth_check = "can_doi_chieu_tay"  # checker "top N" - danh cho nguoi kiem
    elif gt_status in ("loi", "bo_qua", "empty", None):
        ground_truth_check = f"chua_doi_chieu_duoc ({ground_truth.get('reason', gt_status)})"

    severities = {p["severity"] for p in problems}
    passed_auto = "P0" not in severities and not error
    return {
        "problems": problems,
        "passed_auto": passed_auto,
        "ground_truth_check": ground_truth_check,
        "needs_human_review": ground_truth_check == "can_doi_chieu_tay",
    }


def evaluate(suite, cases, *, label: str, delay_seconds: float, skip_ground_truth: bool,
            scope_area: Optional[str]) -> list[dict]:
    import nl2sql

    results: list[dict] = []
    for index, case in enumerate(cases, 1):
        session_id = f"beval-{label}-{case.id}-{uuid.uuid4().hex[:8]}"
        print(f"[{index}/{len(cases)}] {case.id} [{case.audience}] {case.question[:60]}", flush=True)
        started = time.monotonic()
        try:
            response = nl2sql.ask(case.question, session_id=session_id,
                                 username="business-eval", scope_role="c_level")
            answer, error = str(response.get("answer") or ""), None
        except Exception as exc:
            answer, error = "", f"{type(exc).__name__}: {exc}"
        duration = round(time.monotonic() - started, 2)
        ground_truth = _fetch_ground_truth(suite, case.checker_id, scope_area=scope_area,
                                           skip=skip_ground_truth)
        results.append({
            "case": asdict(case), "session_id": session_id, "answer": answer, "error": error,
            "duration_seconds": duration, "ground_truth": ground_truth,
        })
        if delay_seconds:
            time.sleep(delay_seconds)

    audit = _audit_by_session({r["session_id"] for r in results})
    cost = _cost_by_session({r["session_id"] for r in results})
    for r in results:
        tools = sorted(audit[r["session_id"]])
        r["tools_called"] = tools
        r["cost_usd"] = round(cost[r["session_id"]], 6)
        r["grade"] = grade_case(_CaseView(**r["case"]), r["answer"], r["error"], tools,
                                r["ground_truth"])
    return results


class _CaseView:
    """Bien du lieu case tu dict (sau khi da qua asdict) tro lai co thuoc tinh, tranh phai
    truyen ca doi tuong BusinessCase xuyen qua vong lap sau khi da serialize."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def render_markdown(results: list[dict], label: str) -> str:
    total = len(results)
    auto_pass = sum(1 for r in results if r["grade"]["passed_auto"])
    needs_review = sum(1 for r in results if r["grade"]["needs_human_review"])
    by_group: dict[str, list[dict]] = {}
    for r in results:
        by_group.setdefault(r["case"]["group"], []).append(r)

    lines = [
        f"# Kết quả đánh giá nghiệp vụ — {label}",
        "",
        f"Chạy lúc: {dt.datetime.now().strftime('%H:%M %d/%m/%Y')}",
        "",
        "**Đọc bảng này đúng cách**: `Đạt (tự động)` chỉ xác nhận KHÔNG có lỗi hệ thống, từ "
        "chối, lộ dự báo, thiếu tool, hay sai số ở các checker gọn. Dòng `cần đối chiếu tay` "
        "là 'top N' - máy KHÔNG tự phán đúng/sai, phải mở `ground_truth` trong file JSON kèm "
        "theo và so bằng mắt, đúng tinh thần gốc của `business_stress_suite.py`.",
        "",
        f"- Tổng số câu: {total}",
        f"- Đạt tự động (0 vấn đề P0): {auto_pass}/{total}",
        f"- Cần đối chiếu tay (checker dạng danh sách): {needs_review}",
        "",
        "## Theo nhóm nghiệp vụ",
        "",
        "| Nhóm | Đạt tự động | Cần đối chiếu tay | Tổng |",
        "|---|---:|---:|---:|",
    ]
    for group, items in sorted(by_group.items()):
        g_pass = sum(1 for r in items if r["grade"]["passed_auto"])
        g_review = sum(1 for r in items if r["grade"]["needs_human_review"])
        lines.append(f"| {group} | {g_pass}/{len(items)} | {g_review} | {len(items)} |")

    failing = [r for r in results if not r["grade"]["passed_auto"]]
    if failing:
        lines += ["", "## Câu chưa đạt tự động", ""]
        for r in failing:
            probs = "; ".join(f"[{p['severity']}] {p['code']}: {p['detail']}" for p in r["grade"]["problems"])
            lines.append(f"- **{r['case']['id']}** ({r['case']['audience']}) — {r['case']['question'][:70]}")
            lines.append(f"  {probs}")

    durations = [r["duration_seconds"] for r in results if not r["error"]]
    if durations:
        durations_sorted = sorted(durations)
        p50 = statistics.median(durations_sorted)
        p95 = durations_sorted[min(len(durations_sorted) - 1, int(len(durations_sorted) * 0.95))]
        total_cost = sum(r["cost_usd"] for r in results)
        lines += [
            "",
            "## Hiệu năng & chi phí",
            "",
            f"- Thời gian trả lời: P50 {p50:.1f}s · P95 {p95:.1f}s",
            f"- Tổng chi phí lần chạy này: ${total_cost:.4f}",
        ]

    return "\n".join(lines) + "\n"


def _selected_cases(suite, args):
    cases = list(suite.CASES)
    if args.case:
        wanted = {c.upper() for c in args.case}
        cases = [c for c in cases if c.id in wanted]
    if args.group:
        needle = args.group.casefold()
        cases = [c for c in cases if needle in c.group.casefold()]
    if args.audience:
        cases = [c for c in cases if c.audience == args.audience]
    if args.limit:
        cases = cases[:args.limit]
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="current-model")
    parser.add_argument("--case", nargs="*", default=None, help="Chi chay dung cac ma nay (Q001...)")
    parser.add_argument("--group", default=None, help="Loc theo nhom (khop mot phan, khong phan biet hoa thuong)")
    parser.add_argument("--audience", default=None, choices=["qlv", "tp", "manager", "c_level"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=7.0, help="Giay nghi giua 2 cau (gioi han 10 cau/phut)")
    parser.add_argument("--skip-ground-truth", action="store_true",
                        help="May khong noi duoc SQL Server - chi cham 4 muc tu-log, bo doi chieu so")
    parser.add_argument("--scope-area", default=None, help="Bat buoc cho checker DEBT_SCOPE_AGING")
    parser.add_argument("--dry-run", action="store_true", help="Chi in danh sach cau se chay")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    suite = _load_module("business_stress_suite", ROOT / "scripts" / "business_stress_suite.py")
    errors = suite.validate_catalog()
    if errors:
        print("Bo cau hoi khong hop le, dung lai:")
        for e in errors:
            print(" ", e)
        return 2

    cases = _selected_cases(suite, args)
    if not cases:
        print("Khong co cau nao khop bo loc.")
        return 1

    if args.dry_run:
        for c in cases:
            print(f"{c.id} [{c.audience}/{c.group}] {c.question} -> {c.checker_id}")
        print(f"\nTong: {len(cases)} cau (dry-run, chua goi gi)")
        return 0

    results = evaluate(suite, cases, label=args.label, delay_seconds=args.delay,
                       skip_ground_truth=args.skip_ground_truth, scope_area=args.scope_area)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = Path(args.output) if args.output else RESULTS_DIR / f"business-eval-{args.label}-{stamp}.json"
    md_path = json_path.with_suffix(".md")

    auto_pass = sum(1 for r in results if r["grade"]["passed_auto"])
    payload = {"label": args.label, "run_at": dt.datetime.now().isoformat(),
              "total": len(results), "passed_auto": auto_pass, "results": results}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(results, args.label), encoding="utf-8")

    print(f"\nKET QUA: {auto_pass}/{len(results)} dat tu dong.")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    needs_review = sum(1 for r in results if r["grade"]["needs_human_review"])
    if needs_review:
        print(f"  {needs_review} cau dang 'top N' can nguoi doi chieu tay - xem ground_truth trong JSON.")
    return 0 if auto_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
