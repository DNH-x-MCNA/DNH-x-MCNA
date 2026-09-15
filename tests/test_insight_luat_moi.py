# -*- coding: utf-8 -*-
"""Hai luật insight 15/09: cờ tắt, lọc phạm vi và trạng thái lỗi; không gọi Bravo."""
import copy
import datetime as dt

import pytest

from src import alerts, insight_report, insights
from src.alerts import format_vietnamese_money


AS_OF = dt.date(2026, 9, 20)


def _stub_existing_parts(monkeypatch):
    monkeypatch.setattr(insights, "channel_pace_for_scope", lambda *a, **k: {})
    monkeypatch.setattr(insights, "_team_pace_part",
                        lambda *a, **k: {"evaluated": True, "teams": [], "at_risk": []})
    monkeypatch.setattr(insights, "_silent_part",
                        lambda *a, **k: {"evaluated": True, "rows": []})
    monkeypatch.setattr(alerts, "get_bravo_receivables_snapshot", lambda: [])
    monkeypatch.setattr(insights, "_overdue_ordering_part", lambda *a, **k: {"rows": []})
    monkeypatch.setattr(insights, "_new_over45_part",
                        lambda *a, **k: {"available": True, "rows": []})


def test_hai_co_tat_thi_build_bundle_khong_truy_van_hai_nguon_moi(monkeypatch):
    _stub_existing_parts(monkeypatch)
    monkeypatch.setattr(insights, "_etc_sku_stop_part",
                        lambda *a, **k: pytest.fail("Không được truy vấn SKU khi cờ tắt"))
    monkeypatch.setattr(insights, "_new_customer_no_repeat_part",
                        lambda *a, **k: pytest.fail("Không được truy vấn đơn khách mới khi cờ tắt"))

    bundle = insights.build_insight_bundle(
        AS_OF, rules=copy.deepcopy(insights.DEFAULT_RULES), force=True, feature_flags={})

    assert bundle["etc_sku_stops"] == {"enabled": False, "evaluated": False, "rows": []}
    assert bundle["new_customer_no_repeat"] == {"enabled": False, "evaluated": False, "rows": []}
    assert "SKU chủ lực" not in "\n".join(
        insight_report.action_lines(insights.scope_insight_bundle(bundle), format_vietnamese_money))


def test_bat_co_chi_hien_khach_dung_vung_kenh_va_doi():
    bundle = {
        "as_of": AS_OF, "errors": {},
        "team_pace": {"evaluated": True, "at_risk": []},
        "silent_customers": {"evaluated": True, "rows": []},
        "etc_sku_stops": {"enabled": True, "evaluated": True, "rows": [
            {"customer_code": "K1", "customer_name": "BV Bắc", "item_code": "S1",
             "sales_channel": "ETC", "region_key": "bac", "baseline_monthly": 120e6,
             "active_contracts": [{"doc_no": "HD1", "to_date": "2026-12-31"}]},
            {"customer_code": "K2", "customer_name": "BV Nam", "item_code": "S2",
             "sales_channel": "ETC", "region_key": "nam", "baseline_monthly": 150e6,
             "active_contracts": []},
        ]},
        "new_customer_no_repeat": {"enabled": True, "evaluated": True, "rows": [
            {"customer_code": "K1", "customer_name": "NT Bắc", "sales_channel": "OTC",
             "region_key": "bac", "first_order_date": "2026-08-06", "first_order_value": 25e6,
             "wait_days": 45},
            {"customer_code": "K2", "customer_name": "NT Nam", "sales_channel": "OTC",
             "region_key": "nam", "first_order_date": "2026-08-06", "first_order_value": 30e6,
             "wait_days": 45},
        ]},
        "new_over45": {"available": True, "rows": []}, "overdue_ordering": {"rows": []},
    }

    bac_etc = insights.scope_insight_bundle(bundle, region="bac", channel="ETC")
    assert [row["customer_code"] for row in bac_etc["etc_sku_stops"]["rows"]] == ["K1"]
    assert bac_etc["new_customer_no_repeat"]["rows"] == []
    text = "\n".join(insight_report.action_lines(bac_etc, format_vietnamese_money))
    assert "BV Bắc" in text and "BV Nam" not in text and "HD1" in text

    bundle["errors"] = {"etc_sku_stops": "Bravo timeout"}
    team = insights.scope_insight_bundle_to_team(bundle, "QLV1", {"K1"}, channel="OTC")
    assert team["etc_sku_stops"]["rows"] == []
    assert team["etc_sku_stops"]["applicable"] is False and "etc_sku_stops" not in team["errors"]
    assert [row["customer_code"] for row in team["new_customer_no_repeat"]["rows"]] == ["K1"]
    text = "\n".join(insight_report.action_lines(team, format_vietnamese_money))
    assert "NT Bắc" in text and "NT Nam" not in text and "BV Bắc" not in text


@pytest.mark.parametrize(
    ("broken", "expected"),
    [("etc_sku_stops", "Khách ETC ngừng SKU chủ lực: CHƯA đánh giá được"),
     ("new_customer_no_repeat", "Khách mới chưa mua lại: CHƯA đánh giá được")],
)
def test_loi_du_lieu_hien_chua_danh_gia_khong_hien_khong_co_viec(monkeypatch, broken, expected):
    _stub_existing_parts(monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("Bravo timeout")

    monkeypatch.setattr(insights, "_etc_sku_stop_part", fail if broken == "etc_sku_stops" else
                        (lambda *a, **k: {"enabled": True, "evaluated": True, "rows": []}))
    monkeypatch.setattr(insights, "_new_customer_no_repeat_part",
                        fail if broken == "new_customer_no_repeat" else
                        (lambda *a, **k: {"enabled": True, "evaluated": True, "rows": []}))
    bundle = insights.build_insight_bundle(
        AS_OF, rules=copy.deepcopy(insights.DEFAULT_RULES), force=True,
        feature_flags={"insight_etc_sku_stop": True, "insight_new_customer_no_repeat": True})
    view = insights.scope_insight_bundle(bundle)

    lines = insight_report.action_lines(view, format_vietnamese_money)

    assert any(expected in line for line in lines)
    assert "• Không có việc nào vượt ngưỡng cảnh báo." not in lines
