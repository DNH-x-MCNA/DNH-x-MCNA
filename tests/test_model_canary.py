import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "evaluate_model_canary.py"
SPEC = importlib.util.spec_from_file_location("evaluate_model_canary", MODULE_PATH)
canary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = canary
SPEC.loader.exec_module(canary)


def test_canary_has_no_future_forecast_cases_and_every_case_has_a_sql_checker():
    canary._assert_cases_are_current()
    assert len(canary.CANARY_CASES) >= 18
    assert all(case.required_tools and case.sql_checker_id for case in canary.CANARY_CASES)
    # Checker ID phai ton tai trong suite SQL, tranh canary bao "dat" nhung khong co cach doi soat so.
    stress_text = (ROOT / "scripts" / "business_stress_suite.py").read_text(encoding="utf-8")
    assert all(f'_checker("{case.sql_checker_id}"' in stress_text for case in canary.CANARY_CASES)


def test_canary_rejects_a_future_feature_case():
    invalid = (canary.CanaryCase("BAD", "x", "Dự báo doanh thu tháng tới", ("get_revenue_by_channel",), "REV_CHANNEL", "x"),)
    original = canary.CANARY_CASES
    try:
        canary.CANARY_CASES = invalid
        try:
            canary._assert_cases_are_current()
        except ValueError as exc:
            assert "da bi tat" in str(exc)
        else:
            raise AssertionError("Future case phai bi chan")
    finally:
        canary.CANARY_CASES = original
