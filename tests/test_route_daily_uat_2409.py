"""UAT 24/09: đơn đúng tuyến theo từng ngày là cờ trên đơn, không phải lượt thăm có đơn."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt


def test_route_daily_counts_orders_separately_and_keeps_missing_days_unknown(monkeypatch):
    captured = {}

    def fake_bravo(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"DocDate": "2026-09-02", "MonthEnd": "2026-09-30", "EmpDMSCode": "D1",
             "Visits": 4, "VisitedCustomers": 3, "MonthlyVisitedCustomers": 5,
             "PlannedVisits": 2, "VisitsWithOrder": 1, "Orders": 4,
             "OnRouteOrders": 3, "Revenue": 100},
            {"DocDate": "2026-09-04", "MonthEnd": "2026-09-30", "EmpDMSCode": "D1",
             "Visits": 3, "VisitedCustomers": 3, "MonthlyVisitedCustomers": 5,
             "PlannedVisits": 3, "VisitsWithOrder": 2, "Orders": 2,
             "OnRouteOrders": 2, "Revenue": 100},
        ]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-23")
    result = rt._route_visit_effectiveness(month_to="2026-09", months_back=1)

    assert "h.IsPlaned" in captured["sql"]
    assert "h.StatusId<>2 OR h.StatusId IS NULL" in captured["sql"]
    assert result["rows"][0]["on_route_orders"] == 5
    assert result["rows"][0]["visits_with_order"] == 3
    assert result["rows"][0]["visited_customers"] == 5
    assert result["monthly_summary"][0]["on_route_orders"] == 5
    days = {row["date"]: row for row in result["daily_summary"]}
    assert days["2026-09-01"]["on_route_orders"] is None
    assert days["2026-09-01"]["data_status"] == "NO_ROUTE_OR_ORDER_RECORD"
    assert days["2026-09-03"]["on_route_orders"] is None
    assert days["2026-09-02"]["on_route_orders"] == 3
    assert days["2026-09-04"]["on_route_orders"] == 2
    assert result["daily_employee_table"]["D1"] == "02=3,04=2"
    assert "KHONG phai ty le hoan thanh" in result["definition"]
    # Mang daily_summary bi nen xuong 12 dong khi payload lon; bang chuoi ngan
    # phai giu ngay cuoi thang cho model, khong chi 12 ngay dau.
    bloated = dict(result)
    bloated["daily_employee_rows"] = bloated["daily_employee_rows"] * 150
    serialized = nl2sql._serialize_payload_for_model(
        "get_workforce_productivity", {"ok": True, "result": bloated},
        "số lượng đơn hàng đúng tuyến từng ngày từ đầu tháng")
    assert "daily_table_parts" in serialized
    assert "2026-09-23" in serialized


def test_route_question_is_forced_to_current_month_daily_mode(monkeypatch):
    assert nl2sql._required_tool_for_question(
        "số lượng đơn hàng đúng tuyến từng ngày từ đầu tháng của các trình dược viên"
    ) == "get_workforce_productivity"

    calls = {}
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "_route_visit_effectiveness", lambda *args, **kwargs: calls.update(
        {"args": args, "kwargs": kwargs}) or {"daily_summary": []})
    result = rt.call_template(
        "get_workforce_productivity", {"mode": "productivity", "month_to": "2026-08"},
        question="số lượng đơn hàng đúng tuyến từng ngày từ đầu tháng của các trình dược viên",
        username="test.route", session_id="kiemtra-route-2409", scope_role="c_level",
    )
    assert result["ok"]
    assert calls["args"][0] == "2026-09"
    assert calls["args"][1] == 1
