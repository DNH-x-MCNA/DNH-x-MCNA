import datetime as dt
import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))
import period_projection as pp
import report_templates as rt
import feature_policy as fp
import chat_charts as cc
import conversation_memory as memory
import nl2sql


class FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 16)


@pytest.fixture
def projection(monkeypatch):
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    monkeypatch.setattr(pp.dt, "date", FixedDate)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-15")
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2025-09-01")
    seen = []
    def revenue(first, last, **scope):
        seen.append((first, last, scope))
        days = (dt.date.fromisoformat(last[:10]) - dt.date.fromisoformat(first)).days + 1
        return {"total": {"revenue": days * 10}, "data_coverage": {"complete": True}}
    monkeypatch.setattr(rt, "revenue_by_channel", revenue)
    monkeypatch.setattr(rt, "_ytd_plan", lambda *a, **k: {"total": 600, "note": None})
    monkeypatch.setattr(rt, "_write_log", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_q_bravo", lambda *a, **k: pytest.fail("Projection must not query Bravo"))
    return seen


def test_month_projection_reuses_sources_and_preserves_scope(projection):
    result = pp.current_period_projection(scope_area_code="MB", scope_channel="OTC")
    row = result["rows"][0]
    assert row["actual"] == 150
    assert row["linear"] == 300
    assert row["needed_per_day"] == 30
    assert row["history_count"] == 6
    assert row["scenarios"]["low"] <= row["scenarios"]["base"] <= row["scenarios"]["high"]
    assert all(scope["scope_area_code"] == "MB" and scope["scope_channel"] == "OTC" for _, _, scope in projection)
    assert "Không phải khoảng tin cậy" in result["scenario_note"]


def test_quarter_keeps_closed_months_actual(projection):
    row = pp.current_period_projection(period="quarter")["rows"][0]
    assert row["actual"] == 770  # July 31 + August 31 + Sep 15
    assert row["linear"] == 920


def test_no_partial_month_history_from_compressed_totals(projection, monkeypatch):
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2026-08-01")
    row = pp.current_period_projection()["rows"][0]
    assert row["history_count"] == 1
    assert row["scenarios"] is None


def test_missing_target_and_stale_month_are_explicit(projection, monkeypatch):
    monkeypatch.setattr(rt, "_ytd_plan", lambda *a, **k: {"total": None, "note": "Thiếu kế hoạch"})
    row = pp.current_period_projection()["rows"][0]
    assert row["target"] is None and row["needed_per_day"] is None
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-08-31")
    assert "error" in pp.current_period_projection()


def test_kpi_projection_uses_snapshot_run_rate_without_salary_fields(projection, monkeypatch):
    def kpi(day, group, limit, **scope):
        assert scope["scope_employee_code"] == "QLV1"
        return {"as_of": day, "rows": [{"group_code": "QLV1", "group_name": "Đội mình",
                  "actual": 50, "target": 100, "linear_run_rate": 77, "salary": 123456}]}
    monkeypatch.setattr(rt, "kpi_gap_run_rate", kpi)
    result = pp.current_period_projection(scope_employee_code="QLV1", scope_channel="OTC")
    assert result["rows"][0]["linear"] == 77
    assert "salary" not in json.dumps(result)


def test_call_template_overwrites_model_scope_and_blocks_missing_team(projection, monkeypatch):
    seen = {}
    def tool(**args):
        seen.update(args)
        return {"rows": []}
    monkeypatch.setitem(rt.TEMPLATES, "get_current_period_projection", tool)
    result = rt.call_template("get_current_period_projection", {"scope_area_code": "MN", "scope_channel": "ETC"},
                              scope_area_code="MB", scope_channel="OTC", scope_role="regional_director")
    assert result["ok"]
    assert seen["scope_area_code"] == "MB" and seen["scope_channel"] == "OTC"
    assert not rt.call_template("get_current_period_projection", {}, scope_role="qlv")["ok"]


@pytest.mark.parametrize("q", ["Dự báo doanh thu cuối tháng", "Dự báo doanh thu cuối tháng/quý theo kênh/miền",
                               "Dự báo cuối tháng của đội theo run-rate hiện tại; kịch bản cơ sở/tốt/xấu"])
def test_flag_routes_current_period_only(q, monkeypatch):
    monkeypatch.delenv("DNH_BAT_DU_PHONG", raising=False)
    assert fp.is_future_forecast_question(q)
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    assert not fp.is_future_forecast_question(q)
    assert nl2sql._required_tool_for_question(q) == "get_current_period_projection"


@pytest.mark.parametrize("q", ["Dự báo doanh thu tháng sau", "Dự báo doanh thu năm sau",
                               "Dự báo tồn kho cuối tháng", "Dự báo doanh thu tháng 12/2026",
                               "Dự báo cuối tháng và quý sau"])
def test_future_periods_stay_blocked_when_enabled(q, monkeypatch):
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    assert fp.is_future_forecast_question(q)


def test_disabled_tool_never_reads_data(monkeypatch):
    monkeypatch.delenv("DNH_BAT_DU_PHONG", raising=False)
    monkeypatch.setattr(rt, "latest_data_date", lambda: pytest.fail("read while disabled"))
    assert pp.current_period_projection()["feature_disabled"]
    assert all(t["name"] != "get_current_period_projection" for t in nl2sql._tools_for_request(scope_role="c_level"))


def test_projection_sync_stream_persist_same_chart_without_model(projection, monkeypatch, tmp_path):
    monkeypatch.setenv("DNH_BAT_BIEU_DO", "1")
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    monkeypatch.setattr(nl2sql, "_llm_client", lambda: pytest.fail("No model needed"))
    sync = nl2sql.ask("Dự báo doanh thu cuối tháng", session_id="p1", scope_role="c_level")
    events = list(nl2sql.ask_stream("Dự báo doanh thu cuối tháng", session_id="p2", scope_role="c_level"))
    assert events[-1]["charts"] == sync["charts"] and sync["charts"]
    assert memory.get_session_history("p2")[-1]["charts"] == sync["charts"]
    monkeypatch.setenv("DNH_BAT_BIEU_DO", "0")
    assert memory.get_session_history("p2")[-1]["charts"] == []


def test_chart_allowlist_and_nonfinite_rejected(monkeypatch):
    monkeypatch.setenv("DNH_BAT_BIEU_DO", "1")
    assert cc.build_charts("get_salary_detail", {"ok": True, "result": {"rows": []}}) == []
    chart = {"version": 1, "kind": "bar", "labels": ["<script>"], "series": [{"name": "x", "values": [float('nan')]}]}
    assert cc.validate_charts([chart]) == []
    chart["series"][0]["values"] = [None]
    assert cc.validate_charts([chart])[0]["labels"] == ["<script>"]  # rendered as text only


def test_memory_migrates_old_schema_idempotently(monkeypatch, tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, created_at TEXT)")
    con.execute("INSERT INTO messages VALUES (1, 's', 'assistant', 'old', '2026-01-01')")
    con.commit(); con.close()
    monkeypatch.setattr(memory, "DB_PATH", str(path))
    memory.init(); memory.init()
    assert memory.get_session_history("s")[0]["content"] == "old"


def test_requested_scope_never_widens_account(projection, monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    result = nl2sql.ask("Dự báo doanh thu cuối tháng miền Nam", session_id="s",
                        scope_area_code="MB", scope_role="regional_director")
    assert result["last_result"] is None and result["charts"] == []
    assert projection == []


def test_zeros_and_negative_actuals_do_not_create_fake_scenarios(projection, monkeypatch):
    monkeypatch.setattr(rt, "revenue_by_channel", lambda *a, **k: {"total": {"revenue": 0}})
    row = pp.current_period_projection()["rows"][0]
    assert row["linear"] == 0 and row["scenarios"] is None
    monkeypatch.setattr(rt, "revenue_by_channel", lambda *a, **k: {"total": {"revenue": -10}})
    assert pp.current_period_projection()["rows"][0]["scenarios"] is None


def test_missing_historical_team_does_not_hide_current_projection(projection, monkeypatch):
    def kpi(day, *args, **scope):
        if day[:7] != "2026-09":
            raise rt.KhongXacDinhDuocDoi("Không có lịch sử đội tháng cũ")
        return {"as_of": day, "rows": [{"group_code": "QLV1", "group_name": "Đội",
                 "actual": 100, "target": 200, "linear_run_rate": 200}]}
    monkeypatch.setattr(rt, "kpi_gap_run_rate", kpi)
    result = pp.current_period_projection(scope_employee_code="QLV1")
    assert result["rows"][0]["linear"] == 200
    # 30/09 (review): kho chi giu snapshot KPI cuoi thang, nen kich ban doi lay nhip hoa don OTC cung pham vi
    # thay vi snapshot KPI cung ngay cua thang cu (khong bao gio co) - thieu lich su KPI khong con lam mat kich ban.
    assert result["rows"][0]["scenarios"] is not None and result["rows"][0]["history_count"] == 6
    assert result["skipped_history"] == []
    assert any("nhịp hóa đơn OTC" in n for n in result["notes"])
