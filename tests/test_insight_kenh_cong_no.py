# -*- coding: utf-8 -*-
"""Insight công nợ theo ĐÚNG kênh (src/insights.py) — 15/09/2026. Không Bravo, không DB thật.

- Khách nợ >45 ngày ở cả OTC lẫn ETC: bản cũ gộp thành MỘT dòng mang kênh của dòng đầu, nên nợ ETC
  có thể gửi nhầm giám đốc kênh OTC kèm số tổng hai kênh.
- "Nợ >45 ngày vẫn lên đơn": bản cũ đếm đơn của CẢ HAI kênh và cả chứng từ đề ngày tương lai.
"""
import datetime as dt
from types import SimpleNamespace

from src import alerts, insights


def _no(cc, channel, area, gt45, balance=0.0, name=None):
    return SimpleNamespace(customer_code=cc, customer_name=name or cc, sales_channel=channel,
                           area_code=area, overdue_gt_45=gt45, balance_end=balance)


def _chay_new_over45(monkeypatch, snapshot, previous):
    monkeypatch.setattr(alerts, "_save_debt_aging_snapshot", lambda rows: None)
    monkeypatch.setattr(alerts, "_find_debt_snapshot_on_or_before", lambda before: "2026-09-08")
    monkeypatch.setattr(alerts, "_get_debt_aging_snapshot",
                        lambda d: {cc: ("x", amount) for cc, amount in previous.items()})
    return insights._new_over45_part(snapshot, insights.DEFAULT_RULES, today=dt.date(2026, 9, 15))


def test_khach_no_ca_hai_kenh_tach_thanh_dong_rieng_dung_so_tung_kenh(monkeypatch):
    snapshot = [_no("K", "OTC", "MB", 30e6), _no("K", "ETC", "MN", 40e6), _no("CU", "ETC", "MN", 90e6)]

    part = _chay_new_over45(monkeypatch, snapshot, previous={"CU": 5e6})

    theo_kenh = {(r["customer_code"], r["sales_channel"]): r for r in part["rows"]}
    assert set(theo_kenh) == {("K", "OTC"), ("K", "ETC")}   # 70tr tổng vượt 50tr, CU đã có từ trước
    assert theo_kenh[("K", "OTC")]["overdue_gt_45"] == 30e6
    assert theo_kenh[("K", "ETC")]["overdue_gt_45"] == 40e6
    assert theo_kenh[("K", "ETC")]["region_key"] == "nam"
    assert theo_kenh[("K", "OTC")]["overdue_gt_45_all_channels"] == 70e6

    otc = insights.scope_insight_bundle({"new_over45": part}, channel="OTC")["new_over45"]["rows"]
    assert [(r["sales_channel"], r["overdue_gt_45"]) for r in otc] == [("OTC", 30e6)]


def test_kenh_khong_co_no_tren_45_ngay_khong_sinh_dong(monkeypatch):
    snapshot = [_no("K", "OTC", "MB", 0.0), _no("K", "ETC", "MN", 60e6)]

    part = _chay_new_over45(monkeypatch, snapshot, previous={})

    assert [(r["customer_code"], r["sales_channel"]) for r in part["rows"]] == [("K", "ETC")]


def test_no_otc_khong_bi_bao_van_len_don_chi_vi_co_don_etc():
    receivables = [_no("A", "OTC", "MB", 80e6, 120e6), _no("A", "ETC", "MB", 70e6, 90e6)]
    orders = {("A", "ETC"): (3, 25e6)}

    rows = insights.overdue_customers_still_ordering(receivables, orders, 50e6)

    assert [(r["sales_channel"], r["new_orders"]) for r in rows] == [("ETC", 3)]


def test_don_hang_khoa_ma_khach_van_dung_nhu_cu():
    rows = insights.overdue_customers_still_ordering([_no("A", "OTC", "MB", 80e6)], {"A": (1, 5e6)}, 50e6)
    assert [r["customer_code"] for r in rows] == ["A"]


def _kpi(code, pos, area, manager, target, amount, name=None):
    return SimpleNamespace(employee_code=code, employee_name=name or code, area_code=area, position_code=pos,
                           manager_code=manager, month_sale_target=target, month_sale_amount=amount,
                           month_sale_percent=None)


def test_doi_du_phong_neu_ten_nhom_duoi_3_tdv_thay_vi_lang_le_bo(monkeypatch):
    tdv = [_kpi(f"T{i}", "TDV", "MB", "MBKV2", 1e9, 0.2e9) for i in range(3)]
    quan_ly = [_kpi("MBKV2", "QLV", "MB", None, 3.5e9, 0.6e9, "Phạm Xuân Tú"),
               _kpi("MN1", "QLV", "MN", None, 6.65e9, 0.1e9, "Kênh MT"),
               _kpi("MN4", "QLV", "MN", None, 1.7e9, 0.3e9, "Chợ sỉ")]

    def fake_snapshot(position_codes=("TDV",), include_duplicates=False):
        if position_codes == ("TDV",):
            return tdv
        return quan_ly

    monkeypatch.setattr(alerts, "get_bravo_kpi_tdv_snapshot", fake_snapshot)
    monkeypatch.setattr(alerts, "get_bravo_manager_codes", lambda: {"MBKV2", "MN1", "MN4"})

    part = insights._team_pace_part(dt.date(2026, 9, 20), {"expected_share_pct": 50}, insights.DEFAULT_RULES)

    assert [t["team_code"] for t in part["teams"]] == ["MBKV2"]
    assert [(t["team_code"], t["region_key"]) for t in part["not_projected"]] == [("MN1", "nam"), ("MN4", "nam")]
    assert "chưa tính" in part["basis_note"]

    mien_bac = insights.scope_insight_bundle({"team_pace": part}, region="bac")["team_pace"]
    assert mien_bac["not_projected"] == []
    etc = insights.scope_insight_bundle({"team_pace": part}, channel="ETC")["team_pace"]
    assert etc["not_projected"] == []


def test_lay_don_theo_kenh_va_chan_chung_tu_de_ngay_tuong_lai(monkeypatch):
    goi = {}

    def fake_orders(since, until=None, by_channel=False):
        goi.update(since=since, until=until, by_channel=by_channel)
        return {}

    monkeypatch.setattr(alerts, "_bravo_recent_orders_by_customer", fake_orders)
    insights._overdue_ordering_part(dt.date(2026, 9, 14), [], insights.DEFAULT_RULES)

    assert goi["since"] == dt.date(2026, 9, 1)
    assert goi["by_channel"] is True
    assert goi["until"] == dt.date.today() + dt.timedelta(days=1)
