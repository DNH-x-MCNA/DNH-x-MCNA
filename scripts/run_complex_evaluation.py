# -*- coding: utf-8 -*-
"""Chạy 10 câu complex ngày 22 qua chatbot thật và chấm lifecycle QueryPlan.

Khác runner golden 90, gate này chấm cấu trúc điều phối: đủ domain/nguồn, không gọi lặp, reconcile,
timeout và partial answer. SQL checker độc lập vẫn được đính kèm để người kiểm đối chiếu số; runner
không tự nhận hiểu đúng một bảng top/list phức tạp.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import io
import json
import os
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
if str(ROOT / "scripts") not in sys.path:
    sys.path.append(str(ROOT / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS_DIR = ROOT / "results"
COST_LOG = BACKEND / "logs" / "cost_log.jsonl"
REFUSALS = ("quá phức tạp", "qua phuc tap", "vui lòng hỏi cụ thể", "vui long hoi cu the")
INTERNAL_MARKERS = ("QUERY_PLAN_STATUS", "KE_HOACH_BACKEND_BAT_BUOC")


def _load_env() -> None:
    for path in (BACKEND / ".env", ROOT / ".env"):
        if not path.is_file():
            continue
        with io.open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _cost_for_session(session_id: str) -> float:
    if not COST_LOG.is_file():
        return 0.0
    total = 0.0
    with io.open(COST_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("session_id") == session_id:
                total += float(item.get("cost_usd") or 0)
    return round(total, 6)


def _tool_key(step: dict[str, Any]) -> str | None:
    if not step.get("tool_name"):
        return None
    return f"{step['tool_name']}:{json.dumps(step.get('tool_args') or {}, sort_keys=True, ensure_ascii=False, default=str)}"


def grade(case, answer: str, error: str | None, duration: float, plan: dict[str, Any] | None) -> dict:
    problems: list[dict[str, str]] = []
    if error:
        problems.append({"severity": "P0", "code": "loi_he_thong", "detail": error})
    if not answer.strip():
        problems.append({"severity": "P0", "code": "khong_co_cau_tra_loi", "detail": "Answer rỗng."})
    lower = answer.lower()
    if any(marker in lower for marker in REFUSALS):
        problems.append({"severity": "P0", "code": "tu_choi", "detail": "Câu complex bị từ chối là quá phức tạp."})
    leaked = [marker for marker in INTERNAL_MARKERS if marker in answer]
    if leaked:
        problems.append({"severity": "P0", "code": "lo_trace_noi_bo", "detail": f"Lộ marker nội bộ: {leaked}"})
    if duration > case.timeout:
        problems.append({"severity": "P0", "code": "qua_timeout", "detail": f"{duration:.1f}s > {case.timeout}s"})

    required_fields = {
        "plan_id", "question", "metrics", "period", "scope", "steps", "dependencies",
        "status", "sources", "reconciliation_rules",
    }
    if not plan or not required_fields.issubset(plan):
        problems.append({
            "severity": "P0", "code": "thieu_query_plan",
            "detail": f"QueryPlan thiếu trường: {sorted(required_fields - set(plan or {}))}",
        })
        return {"passed_auto": False, "problems": problems, "needs_human_review": True}

    if int(plan.get("max_rounds") or 0) > case.max_rounds:
        problems.append({
            "severity": "P0", "code": "vuot_vong_plan",
            "detail": f"max_rounds={plan.get('max_rounds')} > {case.max_rounds}",
        })
    if float(plan.get("request_timeout_seconds") or 0) > case.timeout:
        problems.append({
            "severity": "P0", "code": "budget_timeout_sai",
            "detail": f"request_timeout={plan.get('request_timeout_seconds')} > {case.timeout}",
        })

    steps = plan.get("steps") or []
    domains = {step.get("domain"): step.get("status") for step in steps}
    missing_domains = [domain for domain in case.expected_domains
                       if domains.get(domain) not in {"completed", "partial", "failed"}]
    if missing_domains:
        problems.append({
            "severity": "P0", "code": "thieu_buoc_nghiep_vu",
            "detail": f"Domain chưa được thực hiện: {missing_domains}",
        })

    called_tools = {step.get("tool_name") for step in steps if step.get("tool_name")}
    missing_groups = [list(group) for group in case.expected_tool_groups
                      if not called_tools.intersection(group)]
    if missing_groups:
        problems.append({
            "severity": "P0", "code": "thieu_nguon",
            "detail": f"Không gọi tool thuộc các nhóm: {missing_groups}",
        })

    attempted = [step for step in steps if step.get("status") in {"completed", "partial", "failed"}]
    minimum = 1 if case.allow_partial else case.min_completed_steps
    if len(attempted) < minimum:
        problems.append({
            "severity": "P0", "code": "thieu_buoc_hoan_tat",
            "detail": f"Mới thực hiện {len(attempted)} bước, cần ít nhất {minimum}.",
        })

    executed_keys = [_tool_key(step) for step in steps if step.get("status") in {"completed", "partial", "failed"}]
    executed_keys = [key for key in executed_keys if key]
    duplicates = sorted({key for key in executed_keys if executed_keys.count(key) > 1})
    if duplicates:
        problems.append({
            "severity": "P0", "code": "goi_tool_lap",
            "detail": f"Tool+args bị thực thi lặp: {duplicates[:3]}",
        })

    reconcile = {item.get("rule"): item.get("status")
                 for item in plan.get("reconciliation_rules") or []}
    missing_rules = [rule for rule in case.reconciliation_rules if rule not in reconcile]
    failed_rules = [rule for rule in case.reconciliation_rules if reconcile.get(rule) == "failed"]
    pending_rules = [rule for rule in case.reconciliation_rules if reconcile.get(rule) == "pending"]
    if missing_rules or failed_rules or (pending_rules and not case.allow_partial):
        problems.append({
            "severity": "P0", "code": "reconcile_chua_dat",
            "detail": f"missing={missing_rules}, failed={failed_rules}, pending={pending_rules}",
        })

    if case.allow_partial:
        if plan.get("status") != "partial":
            problems.append({
                "severity": "P0", "code": "khong_partial_khi_nguon_loi",
                "detail": f"Kỳ vọng partial, thực tế {plan.get('status')}",
            })
        if "phần chưa thể kiểm chứng" not in lower:
            problems.append({
                "severity": "P0", "code": "partial_khong_co_cau_truc",
                "detail": "Thiếu mục 'Phần chưa thể kiểm chứng'.",
            })
    elif plan.get("status") != "completed":
        problems.append({
            "severity": "P0", "code": "plan_chua_hoan_tat",
            "detail": f"QueryPlan status={plan.get('status')}",
        })

    passed = not any(problem["severity"] == "P0" for problem in problems)
    return {"passed_auto": passed, "problems": problems, "needs_human_review": True}


def _ground_truth(golden, checker_ids: tuple[str, ...], cache: dict[str, dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for checker_id in checker_ids:
        if checker_id not in cache:
            try:
                cache[checker_id] = golden._execute_checker(golden.CHECKERS[checker_id])
            except Exception as exc:
                cache[checker_id] = {"status": "loi", "reason": f"{type(exc).__name__}: {exc}"}
        result[checker_id] = cache[checker_id]
    return result


def render_markdown(results: list[dict], label: str) -> str:
    passed = sum(1 for item in results if item["grade"]["passed_auto"])
    durations = sorted(item["duration_seconds"] for item in results)
    p95 = durations[min(len(durations) - 1, int((len(durations) - 1) * .95))] if durations else 0
    lines = [
        f"# Kết quả 10 câu complex — {label}", "",
        f"- Đạt gate planner: {passed}/{len(results)}",
        f"- P95: {p95:.1f}s",
        f"- Chi phí: ${sum(item['cost_usd'] for item in results):.4f}",
        "- Tất cả case vẫn cần đối chiếu số/danh sách bằng ground_truth trong JSON.", "",
        "| Case | Plan | Tool steps | Reconcile | Kết quả |", "|---|---|---:|---|---|",
    ]
    for item in results:
        plan = item.get("query_plan") or {}
        attempted = sum(1 for step in plan.get("steps", [])
                        if step.get("status") in {"completed", "partial", "failed"})
        reconcile = ", ".join(f"{r.get('rule')}={r.get('status')}"
                              for r in plan.get("reconciliation_rules", []))
        result = "PASS" if item["grade"]["passed_auto"] else "FAIL"
        lines.append(f"| {item['case']['id']} | {plan.get('status', 'missing')} | {attempted} | {reconcile} | {result} |")
    failed = [item for item in results if not item["grade"]["passed_auto"]]
    lines.extend(["", "## Câu chưa đạt", ""])
    if not failed:
        lines.append("Không có P0.")
    for item in failed:
        lines.append(f"- **{item['case']['id']}** — {item['case']['question']}")
        for problem in item["grade"]["problems"]:
            lines.append(f"  - [{problem['severity']}] {problem['code']}: {problem['detail']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="complex-current")
    parser.add_argument("--case", nargs="*", default=None)
    parser.add_argument("--delay", type=float, default=7.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qlv-employee-code", default=os.environ.get("EVAL_QLV_EMPLOYEE_CODE"))
    parser.add_argument("--qlv-area-code", default=os.environ.get("EVAL_QLV_AREA_CODE"))
    args = parser.parse_args()

    _load_env()
    suite = _load_module("complex_business_suite", ROOT / "scripts" / "complex_business_suite.py")
    golden = _load_module("business_stress_suite_complex_ground", ROOT / "scripts" / "business_stress_suite.py")
    errors = suite.validate_catalog()
    if errors:
        print("Complex catalog không hợp lệ:\n" + "\n".join(errors))
        return 2
    cases = list(suite.CASES)
    if args.case:
        wanted = {value.upper() for value in args.case}
        cases = [case for case in cases if case.id in wanted]
    if args.dry_run:
        for case in cases:
            print(f"{case.id} [{case.audience}] {case.question}")
        print(f"\nTổng: {len(cases)} complex cases")
        return 0
    if any(case.audience == "qlv" for case in cases) and not args.qlv_employee_code:
        print("C006 cần --qlv-employee-code để test scope thật, không được giả định tài khoản QLV.")
        return 2

    import nl2sql

    results = []
    ground_cache: dict[str, dict] = {}
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case.id} [{case.audience}] {case.question[:65]}", flush=True)
        session_id = f"complex-{args.label}-{case.id}-{uuid.uuid4().hex[:8]}"
        original_template = nl2sql.call_template
        if case.simulated_failure_tool:
            failure_tool = case.simulated_failure_tool

            def failure_injected(name, call_args, **kwargs):
                if name == failure_tool:
                    return {"ok": False, "error": f"SIMULATED_SOURCE_FAILURE:{failure_tool}"}
                return original_template(name, call_args, **kwargs)

            nl2sql.call_template = failure_injected
        started = time.monotonic()
        response = {}
        try:
            response = nl2sql.ask(
                case.question,
                session_id=session_id,
                username="complex-eval",
                scope_role=case.audience,
                scope_area_code=args.qlv_area_code if case.audience == "qlv" else None,
                scope_employee_code=args.qlv_employee_code if case.audience == "qlv" else None,
                query_id=str(uuid.uuid4()),
            )
            answer, error = str(response.get("answer") or ""), None
        except Exception as exc:
            answer, error = "", f"{type(exc).__name__}: {exc}"
        finally:
            nl2sql.call_template = original_template
        duration = round(time.monotonic() - started, 2)
        plan = response.get("query_plan") if response else None
        item = {
            "case": asdict(case),
            "session_id": session_id,
            "answer": answer,
            "error": error,
            "duration_seconds": duration,
            "cost_usd": _cost_for_session(session_id),
            "query_plan": plan,
            "ground_truth": _ground_truth(golden, case.checker_ids, ground_cache),
        }
        item["grade"] = grade(case, answer, error, duration, plan)
        results.append(item)
        if args.delay and index < len(cases):
            time.sleep(args.delay)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = RESULTS_DIR / f"complex-eval-{args.label}-{stamp}.json"
    md_path = json_path.with_suffix(".md")
    json_path.write_text(json.dumps({
        "label": args.label,
        "run_at": dt.datetime.now().isoformat(),
        "results": results,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(results, args.label), encoding="utf-8")
    passed = sum(1 for item in results if item["grade"]["passed_auto"])
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print(f"\nKẾT QUẢ COMPLEX: {passed}/{len(results)} đạt gate planner; {len(results) - passed} P0.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
