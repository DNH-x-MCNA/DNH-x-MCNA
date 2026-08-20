import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name, filename):
    path = SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


suite = _load("complex_business_suite_test", "complex_business_suite.py")
runner = _load("run_complex_evaluation_test", "run_complex_evaluation.py")


def test_complex_catalog_has_exactly_ten_bounded_cases():
    assert suite.validate_catalog() == []
    assert [case.id for case in suite.CASES] == [f"C{i:03d}" for i in range(1, 11)]
    assert all(case.max_rounds <= 10 for case in suite.CASES)
    assert all(case.timeout <= 120 for case in suite.CASES)
    assert suite.CASES[-1].simulated_failure_tool == "get_receivables_overview"
    assert suite.CASES[-1].allow_partial is True


def _complete_plan(case):
    tools = [group[0] for group in case.expected_tool_groups]
    steps = []
    for index, domain in enumerate(case.expected_domains):
        tool = tools[min(index, len(tools) - 1)]
        steps.append({
            "step_id": f"S{index + 1:02d}",
            "domain": domain,
            "status": "completed",
            "tool_name": tool,
            "tool_args": {"index": index},
        })
    # Có nhóm tool nhiều hơn số domain thì thêm step adhoc để mọi expectation đều được gọi.
    for index, tool in enumerate(tools[len(steps):], len(steps) + 1):
        steps.append({
            "step_id": f"S{index:02d}", "domain": "adhoc", "status": "completed",
            "tool_name": tool, "tool_args": {"index": index},
        })
    return {
        "plan_id": "plan-test",
        "question": case.question,
        "metrics": [],
        "period": {},
        "scope": {},
        "steps": steps,
        "dependencies": {step["step_id"]: [] for step in steps},
        "status": "completed",
        "sources": [f"template:{tool}" for tool in tools],
        "reconciliation_rules": [
            {"rule": rule, "status": "passed", "detail": "ok"}
            for rule in case.reconciliation_rules
        ],
    }


def test_complex_grade_accepts_complete_plan_and_keeps_human_number_review():
    case = suite.CASES[0]
    plan = _complete_plan(case)
    result = runner.grade(case, "Kết quả đã đối chiếu theo ba nguồn.", None, 20, plan)
    assert result["passed_auto"] is True
    assert result["needs_human_review"] is True


def test_complex_grade_rejects_missing_domain_and_repeated_tool_args():
    case = suite.CASES[0]
    plan = _complete_plan(case)
    plan["steps"][1]["status"] = "skipped"
    plan["steps"][2]["tool_name"] = plan["steps"][0]["tool_name"]
    plan["steps"][2]["tool_args"] = plan["steps"][0]["tool_args"]
    result = runner.grade(case, "Đã xong.", None, 20, plan)
    codes = {problem["code"] for problem in result["problems"]}
    assert result["passed_auto"] is False
    assert "thieu_buoc_nghiep_vu" in codes
    assert "goi_tool_lap" in codes


def test_failure_case_requires_structured_partial_answer():
    case = suite.CASES[-1]
    plan = _complete_plan(case)
    plan["status"] = "partial"
    plan["steps"][-1]["status"] = "failed"
    plan["steps"][-1]["error"] = "SIMULATED_SOURCE_FAILURE"
    for item in plan["reconciliation_rules"]:
        if item["rule"] == "debt_aging":
            item["status"] = "pending"
    passed = runner.grade(
        case,
        "Doanh thu đã kiểm chứng.\n\n### Phần chưa thể kiểm chứng\n- Công nợ: nguồn lỗi.",
        None,
        20,
        plan,
    )
    assert passed["passed_auto"] is True

    failed = runner.grade(case, "Doanh thu đã kiểm chứng.", None, 20, plan)
    assert failed["passed_auto"] is False
    assert any(p["code"] == "partial_khong_co_cau_truc" for p in failed["problems"])
