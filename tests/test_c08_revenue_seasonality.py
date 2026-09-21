# -*- coding: utf-8 -*-
"""C08/S80: tool mua vu phai nhanh va khong phu thuoc warehouse.db cua may chay test."""
import datetime as real_dt
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt


class _FixedDate(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 15)


def _month_add(year_month: str, delta: int) -> str:
    year, month = map(int, year_month.split("-"))
    number = year * 12 + month - 1 + delta
    return f"{number // 12:04d}-{number % 12 + 1:02d}"


def _lean_series_fixture(calls):
    """24 thang tron + thang dang chay, khong can kho SQLite that."""
    months = []
    for index in range(24):
        ym = _month_add("2024-08", index)
        months.append({
            "month": ym,
            "otc_revenue": 100.0 + index,
            "etc_revenue": 200.0 + index,
            "revenue": 300.0 + index,
        })
    months.append({
        "month": "2026-08", "otc_revenue": 90.0, "etc_revenue": 180.0, "revenue": 270.0,
    })

    def fake_series(**kwargs):
        calls.append(kwargs)
        return {
            "month_from": "2024-08", "month_to": "2026-08", "months": months,
            "data_as_of": "2026-08-15",
        }

    return fake_series


def _fake_query(sql, params=()):
    if "FROM vhoadon_etc" in sql:
        # Chi tiet 24 thang cua ETC: du de kiem tra mapping ten nhom, khong phai du lieu UAT that.
        return [{"month": _month_add("2024-08", i), "group_code": "0", "revenue": 1.0}
                for i in range(24)]
    if "FROM dim_keyclass" in sql:
        return [{"code": "0", "name": "Hang dau tu"}]
    raise AssertionError(f"C08 goi truy van khong mong doi: {sql}")


def test_seasonality_uses_lean_series_and_returns_ready_history(monkeypatch):
    """Loi C08 la keo 24 lan target/tach mien; tool moi chi duoc goi chuoi doanh thu toi gian."""
    calls = []
    monkeypatch.setattr(rt, "revenue_monthly_series", _lean_series_fixture(calls))
    monkeypatch.setattr(rt, "_q", _fake_query)
    monkeypatch.setattr(rt.dt, "date", _FixedDate)

    result = rt.revenue_seasonality(months_back=24)

    assert calls == [{
        "month_to": None, "months_back": 24, "include_yoy": False,
        "scope_area_code": None, "scope_channel": None, "scope_employee_code": None,
        "include_plans": False, "include_region_breakdown": False,
        "include_special_channels": False,
    }]
    assert result["status"] == "READY"
    channels = {row["channel"]: row for row in result["seasonality_by_channel"]}
    assert set(channels) == {"OTC", "ETC"}
    assert all(row["status"] == "READY" for row in channels.values())
    assert all(len(row["months"]) == 12 for row in channels.values())
    assert channels["OTC"]["current_month_note"]
    assert channels["OTC"]["deviation_from_seasonal"] is None
    assert result["product_groups"]["etc_status"] == "READY"
    assert result["product_groups"]["etc_groups"][0]["group_name"] == "Hang dau tu"


def test_seasonality_keeps_channel_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(rt, "revenue_monthly_series", _lean_series_fixture(calls))
    monkeypatch.setattr(rt, "_q", _fake_query)
    monkeypatch.setattr(rt.dt, "date", _FixedDate)

    otc = rt.revenue_seasonality(months_back=24, scope_channel="OTC")
    etc = rt.revenue_seasonality(months_back=24, scope_channel="ETC")

    assert [row["channel"] for row in otc["seasonality_by_channel"]] == ["OTC"]
    assert otc["product_groups"]["etc_status"] == "NOT_APPLICABLE_CHANNEL_SCOPE"
    assert [row["channel"] for row in etc["seasonality_by_channel"]] == ["ETC"]
    assert all(call["scope_channel"] in {"OTC", "ETC"} for call in calls)


def test_seasonality_forwards_short_history_request(monkeypatch):
    calls = []
    monkeypatch.setattr(rt, "revenue_monthly_series", _lean_series_fixture(calls))
    monkeypatch.setattr(rt, "_q", _fake_query)
    monkeypatch.setattr(rt.dt, "date", _FixedDate)

    rt.revenue_seasonality(months_back=12)

    assert calls[0]["months_back"] == 12


def test_revenue_seasonality_router():
    assert nl2sql._required_tool_for_question("tinh mua vu doanh thu") == "get_revenue_seasonality"
    assert nl2sql._required_tool_for_question("danh gia tinh mua vu cua kenh OTC") == "get_revenue_seasonality"
    assert nl2sql._required_tool_for_question("phan tich mua vu ban hang") == "get_revenue_seasonality"
