"""M36/S78, UAT 10/09: ty le co gia tri theo vung x thang, hang tang thieu gia tri."""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt


def test_m36_combines_northern_area_codes_and_reports_percentage_point_changes(monkeypatch):
    def fake_q(sql, params=()):
        if sql.startswith("PRAGMA"):
            return [{"name": "discount_rate"}, {"name": "doc_code"}]
        if "total_rows" in sql:
            return [{"total_rows": 5, "populated_rows": 5}]
        return [
            {"month": "2026-08", "channel": "OTC", "area_code": "MB", "amount9": 100,
             "quantity": 1, "unit_price": 100, "discount_rate": 0.1, "doc_code": "BH", "order_key": "A"},
            {"month": "2026-08", "channel": "OTC", "area_code": "MB2", "amount9": 100,
             "quantity": 1, "unit_price": 100, "discount_rate": 0.2, "doc_code": "BH", "order_key": "B"},
            {"month": "2026-09", "channel": "OTC", "area_code": "MB", "amount9": 100,
             "quantity": 1, "unit_price": 100, "discount_rate": 0.2, "doc_code": "BH", "order_key": "C"},
            {"month": "2026-09", "channel": "OTC", "area_code": "MB", "amount9": -10,
             "quantity": -1, "unit_price": 10, "discount_rate": 0, "doc_code": "HC", "order_key": "D"},
            {"month": "2026-09", "channel": "OTC", "area_code": "MB", "amount9": 0,
             "quantity": 2, "unit_price": 0, "discount_rate": 0, "doc_code": "BH", "order_key": "E"},
        ]

    monkeypatch.setattr(rt, "_q", fake_q)
    result = rt._sales_financial_quality_by_month(
        "2026-08-01", "2026-09-23", scope_channel="OTC")
    rows = result["rows_by_month_region"]
    assert [(r["month"], r["region"]) for r in rows] == [
        ("2026-08", "Miền Bắc"), ("2026-09", "Miền Bắc")]
    assert rows[0]["gross_revenue"] == 200
    assert rows[0]["discount_amount"] == 30
    assert rows[0]["discount_rate_pct"] == 15
    assert rows[0]["discount_rate_change_pp"] is None
    assert rows[1]["discount_rate_pct"] == 20
    assert rows[1]["discount_rate_change_pp"] == 5
    assert rows[1]["return_adjustment_rate_pct"] == 10
    assert rows[1]["gift_quantity"] == 2
    assert rows[1]["gift_order_share_pct"] == pytest.approx(100 / 3)
    assert rows[1]["gift_value_rate_pct"] is None
    assert result["gift_value_rate_status"] == "UNAVAILABLE_NO_GIFT_VALUATION"
    scoped = rt._sales_financial_quality_by_month(
        "2026-08-01", "2026-09-23", scope_channel="OTC", scope_area_code="MB")
    assert scoped["rows_by_month_region"][0]["gross_revenue"] == 200


def test_m36_question_already_has_a_tool_and_monthly_mode_is_forced(monkeypatch):
    question = "Tỷ lệ trả hàng/chiết khấu/hàng tặng trên DT của từng vùng thay đổi ra sao?"
    assert nl2sql._required_tool_for_question(question) == "check_order_timing"
    calls = {}
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-23")
    monkeypatch.setattr(rt, "order_timing_check", lambda **kw: calls.update(kw) or {})
    monkeypatch.setitem(rt.TEMPLATES, "check_order_timing", rt.order_timing_check)
    answer = rt.call_template("check_order_timing", {}, question=question,
                              username="test.m36", session_id="kiemtra-m36-2409",
                              scope_role="regional_director", scope_area_code="MB")
    assert answer["ok"]
    assert calls["date_from"] == "2026-04-01"
    assert calls["date_to"].startswith("2026-09-23")
    assert calls["group_by_month"] is True
    assert calls["scope_area_code"] == "MB"
