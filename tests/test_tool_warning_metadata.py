"""Tool warnings carry authored display text independently of model guidance."""
import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Barrier

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import report_templates as rt


@pytest.fixture(autouse=True)
def no_audit_or_name_queries(monkeypatch):
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "_gan_ten_cho_ma", lambda result: result)


def _call(monkeypatch, fn):
    monkeypatch.setitem(rt.TEMPLATES, "get_revenue_by_channel", fn)
    return rt.call_template("get_revenue_by_channel", {})


def test_every_production_warn_has_authored_display_metadata():
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_warn"]
    assert calls, "Audit must cover the real production warning producers."
    for call in calls:
        keywords = {k.arg: k.value for k in call.keywords}
        assert {"code", "severity", "message"} <= keywords.keys(), call.lineno
        assert isinstance(keywords["code"], ast.Constant), call.lineno
        assert keywords["severity"].value in {"info", "warning"}, call.lineno
        # The user-facing text must not just repeat or rewrite raw model guidance.
        assert isinstance(keywords["message"], (ast.Constant, ast.JoinedStr)), call.lineno


def test_legacy_transport_and_display_transport_dedup_without_losing_period(monkeypatch):
    def tool():
        for month in ["2026-08", "2026-08", "2026-09"]:
            rt._warn(f"PHAI noi ro {month}", code="fixture_incomplete", severity="warning",
                     message=f"Kỳ {month} chưa đủ dữ liệu để đánh giá.")
        return {"total": 12}

    payload = _call(monkeypatch, tool)
    assert payload["ok"] is True
    assert payload["canh_bao"] == ["PHAI noi ro 2026-08", "PHAI noi ro 2026-09"]
    assert payload["user_warnings"] == [
        {"code": "fixture_incomplete", "severity": "warning",
         "message": f"Kỳ {month} chưa đủ dữ liệu để đánh giá."}
        for month in ["2026-08", "2026-09"]
    ]


@pytest.mark.parametrize("salary_available", [True, False])
def test_real_roster_fallback_distinguishes_valid_salary_from_after_period(monkeypatch, salary_available):
    team = [{"employee_code": "TDV_1"}]
    monkeypatch.setattr(rt, "_team_of_qlv", lambda code, date: team if date == "2026-06-30" else [])
    monkeypatch.setattr(rt, "_team_of_qlv_tu_luong", lambda code, date:
                        (team, "2025-12-31") if salary_available else ([], None))
    monkeypatch.setattr(rt, "_dms_theo_ma_nv", lambda codes: {"TDV_1": "DMS_1"})
    monkeypatch.setattr(rt, "_q", lambda *args: [{"d": "2026-06-30"}])

    def tool():
        return {"ids": rt._get_team_dms_ids("QLV_TEST", "2025-12-31")}

    payload = _call(monkeypatch, tool)
    assert payload["ok"] is True
    assert payload["result"]["ids"] == ["DMS_1"]
    warning, = payload["user_warnings"]
    assert warning["severity"] == ("info" if salary_available else "warning")
    assert warning["code"] == ("team_roster_salary_snapshot" if salary_available
                               else "historical_team_roster_after_period")
    assert "QLV_TEST" in warning["message"]
    assert "2025-12-31" in warning["message"]
    if not salary_available:
        assert "2026-06-30" in warning["message"]
        assert "sau kỳ" in warning["message"]
    assert "PHAI" not in warning["message"]
    assert "fact_" not in warning["message"]


def test_real_missing_member_warning_contains_coverage_and_user_scope(monkeypatch):
    monkeypatch.setattr(rt, "_team_of_qlv", lambda *args: [
        {"employee_code": "TDV_OK"}, {"employee_code": "TDV_MISSING"}])
    monkeypatch.setattr(rt, "_roster_snapshot_dates", lambda *args: ["2026-08-31"])
    monkeypatch.setattr(rt, "_dms_theo_ma_nv", lambda codes: {"TDV_OK": "DMS_OK"})

    payload = _call(monkeypatch, lambda: {
        "ids": rt._get_team_dms_ids("QLV_TEST", "2026-08-31")})
    assert payload["ok"] is True
    warning, = payload["user_warnings"]
    assert warning["severity"] == "warning"
    assert warning["code"] == "team_revenue_partial_members"
    assert all(part in warning["message"] for part in ["QLV_TEST", "1/2", "TDV_MISSING"])
    assert "PHAI" not in warning["message"]
    assert "sync_warehouse" not in warning["message"]


def test_warning_context_is_restored_after_exception(monkeypatch):
    outer = [{"code": "outer", "severity": "info", "message": "Thông tin của lượt gọi ngoài."}]
    token = rt._tool_user_warnings.set(outer)
    try:
        def tool():
            rt._warn("PHAI noi ro", code="inner", severity="warning", message="Dữ liệu còn thiếu.")
            raise ValueError("fixture failure")

        payload = _call(monkeypatch, tool)
        assert payload["ok"] is False
        assert rt._tool_user_warnings.get() is outer
        clean = _call(monkeypatch, lambda: {"total": 1})
        assert clean["ok"] is True
        assert "user_warnings" not in clean
    finally:
        rt._tool_user_warnings.reset(token)


def test_warning_context_does_not_cross_concurrent_requests(monkeypatch):
    barrier = Barrier(2)

    def tool(scope):
        rt._warn(f"PHAI noi ro {scope}", code="partial", severity="warning",
                 message=f"Dữ liệu vùng {scope} còn thiếu.")
        barrier.wait(timeout=5)
        return {"scope": scope}

    monkeypatch.setitem(rt.TEMPLATES, "get_revenue_by_channel", tool)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(rt.call_template, "get_revenue_by_channel", {"scope": scope})
                   for scope in ["MB", "MT"]]
        results = [future.result(timeout=10) for future in futures]
    for scope, payload in zip(["MB", "MT"], results):
        assert payload["ok"] is True
        warning, = payload["user_warnings"]
        assert warning["message"] == f"Dữ liệu vùng {scope} còn thiếu."
