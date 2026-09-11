"""Review gates for the two machine24 branches. No real model calls."""
import datetime as dt
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

import nl2sql
import report_templates as rt
from query_plan import infer_domains
from test_data_freshness import _patch_nl2sql_runtime
from test_management_rounds_remaining import _setup


C29 = "Khách hoạt động, mới, mua lại, tái kích hoạt, ngừng mua từng tháng"
LIFECYCLE = "get_customer_lifecycle_summary"
MOVEMENT = "get_customer_movement"


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("same_round", [False, True])
def test_c29_never_executes_both_customer_definitions(monkeypatch, streaming, reverse, same_round):
    names = [LIFECYCLE, MOVEMENT]
    if reverse:
        names.reverse()
    batches = [names] if same_round else [[names[0]], [names[1]]]
    calls, executed = [], []

    class Stream:
        def __init__(self, message):
            self.message = message
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __iter__(self):
            return iter(())
        def get_final_message(self):
            return self.message

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            if "tools" in kwargs:
                assert MOVEMENT not in {t["name"] for t in kwargs["tools"]}
                assert LIFECYCLE in {t["name"] for t in kwargs["tools"]}
            if batches:
                batch = batches.pop(0)
                content = [SimpleNamespace(type="tool_use", name=name,
                           id=f"{len(calls)}-{index}", input={}) for index, name in enumerate(batch)]
            else:
                content = [SimpleNamespace(type="text", text="Đã tổng hợp đúng cờ Bravo.")]
            return SimpleNamespace(content=content, usage=SimpleNamespace())
        def stream(self, **kwargs):
            return Stream(self.create(**kwargs))

    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=Messages()), [])
    monkeypatch.setattr(nl2sql, "_static_system_prompt", lambda: "test")
    monkeypatch.setattr(nl2sql, "_dynamic_context_note", lambda *a: "test")
    def fake_tool(name, args, **kwargs):
        executed.append(name)
        return {"ok": True, "result": {"rows": [{"month": "2026-08", "new_customers": 612}]}}
    monkeypatch.setattr(nl2sql, "call_template", fake_tool)
    if streaming:
        list(nl2sql.ask_stream(C29, session_id="unit-c29", username="unit", scope_role="c_level"))
    else:
        nl2sql.ask(C29, session_id="unit-c29", username="unit", scope_role="c_level")
    assert executed == [LIFECYCLE]


def test_c29_guard_does_not_globally_disable_movement():
    assert nl2sql._required_tool_for_question(C29) == LIFECYCLE
    assert not nl2sql._customer_tool_conflict(MOVEMENT, "Khách mới và tái kích hoạt bù doanh thu mất bao nhiêu?")
    assert "kpi" not in {d["domain"] for d in infer_domains(C29)}


@pytest.mark.parametrize("question,expected", [
    ("Đối soát doanh thu giữa view tổng và view thường", "get_revenue_view_reconciliation"),
    ("Thưởng ASO từng nhân viên chốt thế nào, ai không qua điều kiện?", "get_salary_aso_detail"),
    ("SKU doanh thu giảm so kỳ trước trong khi còn tồn kho", "get_sku_revenue_drop_vs_stock"),
    ("Xếp hạng toàn bộ nhân viên theo tỷ lệ hoàn thành", "get_employee_kpi"),
    ("SKU khách cần nhưng kho thiếu là gì?", "get_inventory_expiry_report"),
])
def test_routes_new_tools_without_stealing_inventory_intent(question, expected):
    assert nl2sql._required_tool_for_question(question) == expected


def test_employee_kpi_manager_counts_before_limit_and_excludes_missing_target(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE dim_chucvu (position_code TEXT, description TEXT)")
        # Duplicate manager label must not double all reports to that manager.
        db.execute("INSERT INTO dim_nhanvien SELECT * FROM dim_nhanvien WHERE employee_code='Q1'")
    result = rt.employee_kpi("2026-04-15", limit=1, scope_area_code="MB", position_code="TDV")
    assert len(result["rows"]) == 1
    summary = next(r for r in result["below_kpi_by_manager"] if r["manager_code"] == "Q1")
    assert summary["count_below_kpi"] == 2
    assert {e["employee_code"] for e in summary["employees"]} == {"T1", "T2"}
    assert {r["manager_code"] for r in result["below_kpi_by_manager"]} == {"Q1"}


def test_c46_headcount_increase_zero_productivity_is_not_skipped_or_mtd(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM fact_thongketinhluong")
        for month, people, revenue in (("2026-02-28", ["T1"], 100),
                                        ("2026-03-31", ["T1", "T2"], 0),
                                        ("2026-04-15", ["T1", "T2", "T3"], -1)):
            for emp in people:
                db.execute("INSERT INTO fact_thongketinhluong VALUES (?,?,?,?,?,?,?,?,?)",
                           (emp, emp, "TDV", "MB", "Q1", month, revenue, 100, revenue))
    result = rt.workforce_productivity("2026-04", 3, group_by="manager", limit=1)
    matches = result["headcount_up_productivity_down"]
    assert len(matches) == 1
    assert matches[0]["month"] == "2026-03"
    assert matches[0]["revenue_per_employee"] == 0
    assert matches[0]["revenue_per_employee_pct_change"] == -100


def test_geography_peer_average_before_limit_and_within_region(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO dim_tinhthanhpho VALUES (3,'Hai Phong','MB')")
        db.execute("UPDATE dms_khachhang SET city_id=3 WHERE code='C2'")
    result = rt.geography_monthly_performance("2026-03", 1, dimension="city", limit=1, scope_area_code="MB")
    # March: Hanoi C1 = 180, Hai Phong C2 = 500. Region average 340, even if only one city shown.
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["area_avg_revenue_per_city"] == 340
    assert row["area_avg_customers_per_city"] == 1
    assert row["area_avg_revenue_per_customer"] == 340
    assert row["revenue_per_customer"] == 500
    assert row["below_area_avg_revenue_per_customer"] is False


def _stock_db(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.executescript("""
            DELETE FROM vhoadon_otc; DELETE FROM vhoadon_etc;
            CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT);
            CREATE TABLE brv_tonkhodklot (item_id INTEGER, warehouse_id INTEGER, quantity REAL,
                                        is_active INTEGER, year INTEGER);
            INSERT INTO brv_kho VALUES (1,'B02'),(2,'B04');
            INSERT INTO brv_tonkhodklot VALUES (1,1,0,1,2026),(1,2,999,1,2026),
                (1,1,9999,1,2025),(2,1,10,1,2026);
        """)
        for item in ("A", "B", "MISSING"):
            db.execute("INSERT INTO vhoadon_otc (doc_date,customer_code,item_code,amount9,employee_code) "
                       "VALUES ('2026-02-28 23:59:59','C1',?,100,'D1')", (item,))
            db.execute("INSERT INTO vhoadon_otc (doc_date,customer_code,item_code,amount9,employee_code) "
                       "VALUES ('2026-03-31 23:59:59','C1',?,20,'D1')", (item,))
        db.execute("INSERT INTO vhoadon_otc (doc_date,customer_code,item_code,amount9) "
                   "VALUES ('2026-03-10','C4','A',5000)")
        db.execute("INSERT INTO vhoadon_etc (doc_date,customer_code,item_code,amount9) "
                   "VALUES ('2026-03-10','C1','A',9000)")
    monkeypatch.setattr(rt, "_latest_complete_revenue_month", lambda: "2026-03")
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2026-01-01")
    return path


def test_sku_stock_scope_year_missing_zero_and_last_day(tmp_path, monkeypatch):
    _stock_db(tmp_path, monkeypatch)
    r = rt.sku_revenue_drop_vs_stock(months_back=1, area_code="MN", scope_area_code="MB",
                                    scope_channel="OTC", min_prev_revenue=1)
    assert r["period_previous"]["from"] == "2026-02-01"
    assert r["period_current"]["to"].startswith("2026-03-31")
    assert r["counts"] == {"zero_recorded_stock": 1, "positive_recorded_stock": 1, "unknown_or_negative_stock": 1}
    zero = r["zero_recorded_stock"][0]
    assert (zero["item_code"], zero["prev_revenue"], zero["cur_revenue"], zero["stock_qty"]) == ("A", 100, 20, 0)
    assert r["unknown_or_negative_stock"][0]["stock_qty"] is None
    assert r["positive_recorded_stock"][0]["item_code"] == "B"
    assert r["stock_basis"] == "FISCAL_YEAR_LOT_RECORDS_NOT_LIVE_ATP"


def test_sku_unknown_area_and_missing_history_fail_closed(tmp_path, monkeypatch):
    _stock_db(tmp_path, monkeypatch)
    assert "error" in rt.sku_revenue_drop_vs_stock(scope_area_code="BAD")
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2026-03-01")
    assert rt.sku_revenue_drop_vs_stock(months_back=1)["status"] == "source_gap"


def test_view_reconciliation_two_channels_zero_base_and_day_end(monkeypatch):
    queries = []
    def bravo(sql, params):
        queries.append(sql)
        assert params["date_to_exclusive"] == dt.date(2026, 9, 1)
        assert "BETWEEN" not in sql
        return [{"total_view_revenue": 0, "base_view_revenue": 10,
                 "total_view_invoices": 1, "base_view_invoices": 2}]
    monkeypatch.setattr(rt, "_q_bravo", bravo)
    r = rt.revenue_view_reconciliation("2026-08-01", "2026-08-31", scope_role="c_level")
    assert len(queries) == 2
    assert "vHoaDonETCTotal" in queries[1]
    assert r["otc"]["needs_investigation"] is True
    assert r["otc"]["gap_pct"] is None
    assert r["total"]["gap_base_minus_total"] == 20


@pytest.mark.parametrize("scope", [
    {"scope_role": "regional_director"}, {"scope_role": "qlv", "scope_employee_code": "Q1"},
    {"scope_role": "c_level", "scope_area_code": "MB"},
    {"scope_role": "c_level", "scope_channel": "ETC"},
])
def test_view_reconciliation_scoped_roles_cannot_query_bravo(monkeypatch, scope):
    monkeypatch.setattr(rt, "_write_log", lambda e: None)
    monkeypatch.setattr(rt, "_q_bravo", lambda *a: pytest.fail("must block before reading"))
    r = rt.call_template("get_revenue_view_reconciliation", {"date_from": "2026-08-01", "date_to": "2026-08-31"}, **scope)
    assert not r["ok"] or "error" in r.get("result", {})
    assert "get_revenue_view_reconciliation" not in {t["name"] for t in nl2sql._tools_for_request(**scope)}


def _aso_row(code, quantity=1, sale=1, final=1, calculated=1):
    return {"EmployeeCode": code, "EmployeeName": code, "PositionCode": "TDV", "AreaCode": "MB",
            "IsCalASOBonus": calculated, "PassCheckASOForASO": quantity, "PassCheckSaleForASO": sale,
            "PassCheckASOBonus": final, "ASOQuantity": 20, "ASOQuantityTarget": 10,
            "ASOPercent_R": 2, "ASOBonus": 100, "IsSuspend": 0}


def test_aso_scope_null_flags_and_full_counts_before_filter_limit(monkeypatch):
    def bravo(sql, params):
        if "MAX(SaveDate)" in sql:
            assert params["month_from"] == "2026-08-01"
            assert params["month_to"] == "2026-09-01"
            return [{"snapshot_date": "2026-08-31"}]
        assert "f.ManagerCode=:employee" in sql
        assert params["employee"] == "Q1" and params["area_code"] == "MB"
        return [_aso_row("OK"), _aso_row("F1", 0, 0, 0), _aso_row("F2", 1, 1, 0),
                _aso_row("UNKNOWN", final=None), _aso_row("OFF", final=0, calculated=0)]
    monkeypatch.setattr(rt, "_q_bravo", bravo)
    r = rt.salary_aso_detail("2026-08", area_code="MN", scope_area_code="MB", scope_role="qlv",
                            scope_employee_code="Q1", only_failed=True, limit=1)
    assert (r["total_employees"], r["total_passed"], r["total_failed"], r["unassessed_count"]) == (5, 1, 2, 2)
    assert r["selected_total"] == 2 and r["rows_truncated"] is True
    assert r["rows"][0]["fail_reasons"] == ["customer_quantity_condition_failed", "sale_condition_failed"]
    assert r["rows"][0]["aso_percent"] == 200


def test_aso_requested_month_never_falls_back_to_previous(monkeypatch):
    monkeypatch.setattr(rt, "_q_bravo", lambda *a: [{"snapshot_date": None}])
    r = rt.salary_aso_detail("2026-08", scope_role="c_level")
    assert r["status"] == "source_gap" and r["requested_month"] == "2026-08"


@pytest.mark.parametrize("role,employee", [("regional_director", None), ("qlv", None)])
def test_aso_salary_access_is_not_opened_for_new_tool(monkeypatch, role, employee):
    monkeypatch.setattr(rt, "_write_log", lambda e: None)
    monkeypatch.setattr(rt, "_q_bravo", lambda *a: pytest.fail("salary read must be blocked"))
    result = rt.call_template("get_salary_aso_detail", {"scope_role": "c_level"},
                              scope_role=role, scope_employee_code=employee)
    assert not result["ok"]


@pytest.mark.parametrize("position", ["CS", "TK"])
def test_aso_cs_tk_are_not_applicable_without_source_query(monkeypatch, position):
    monkeypatch.setattr(rt, "_q_bravo", lambda *a: pytest.fail("not applicable"))
    assert rt.salary_aso_detail(position_code=position, scope_role="c_level")["not_applicable"]
