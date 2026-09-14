# -*- coding: utf-8 -*-
"""Quy tắc insight dùng chung cho cảnh báo và báo cáo (src/insights.py) — chỉ hàm thuần, không DB.

Ngưỡng mặc định và số kiểm thử ngược trên Bravo ghi ở src/insights.py::DEFAULT_RULES.
"""
import datetime as dt

import pytest

from src import insights


def _thang(y, m, theo_ngay):
    """{date: doanh thu} cho một tháng từ {ngày: doanh thu}."""
    return {dt.date(y, m, d): v for d, v in theo_ngay.items()}


def _chuoi_don_cuoi_thang():
    """3 tháng mẫu bán 100 mỗi tháng nhưng dồn cuối tháng: tới ngày 10 mới được 20 (20%)."""
    daily = {}
    for m in (6, 7, 8):
        daily.update(_thang(2026, m, {5: 10, 10: 10, 20: 30, 28: 50}))
    return daily


def test_month_pace_so_voi_duong_cong_khong_phai_chia_deu_theo_ngay():
    daily = _chuoi_don_cuoi_thang()
    daily.update(_thang(2026, 9, {5: 10, 10: 10}))   # đúng nhịp thường lệ: 20 tới ngày 10

    pace = insights.month_pace(daily, dt.date(2026, 9, 10), lookback=3)

    assert pace["expected_share_pct"] == pytest.approx(20)
    assert pace["gap_pct"] == pytest.approx(0)
    assert pace["projected_full_month"] == pytest.approx(100)
    # Chia đều theo ngày thì kỳ vọng 33% (10/30) và báo chậm 40% — đúng loại báo động giả cũ.
    assert not insights.channel_pace_breach(pace, min_day=10, max_gap_pct=30)


def test_month_pace_bao_cham_nhip_khi_that_su_thieu():
    daily = _chuoi_don_cuoi_thang()
    daily.update(_thang(2026, 9, {5: 5, 10: 5}))     # mới 10 so với kỳ vọng 20

    pace = insights.month_pace(daily, dt.date(2026, 9, 10), lookback=3)

    assert pace["gap_pct"] == pytest.approx(50)
    assert pace["projected_full_month"] == pytest.approx(50)
    assert pace["projected_vs_baseline_pct"] == pytest.approx(-50)
    assert insights.channel_pace_breach(pace, min_day=10, max_gap_pct=30)
    assert not insights.channel_pace_breach(pace, min_day=11, max_gap_pct=30)  # chưa tới ngày đánh giá


def test_month_pace_can_it_nhat_2_thang_nen_va_so_cung_ky_thang_truoc():
    assert insights.month_pace(_thang(2026, 8, {1: 100}), dt.date(2026, 9, 5)) is None
    daily = _chuoi_don_cuoi_thang()
    daily.update(_thang(2026, 9, {5: 12}))
    pace = insights.month_pace(daily, dt.date(2026, 9, 5), lookback=3)
    assert pace["prev_month_same_days"] == 10
    assert pace["vs_prev_month_same_days_pct"] == pytest.approx(20)


def test_month_pace_ngay_31_so_voi_thang_ngan_lay_tron_thang():
    daily = {}
    for m, last in ((4, 30), (5, 31), (6, 30)):
        daily.update(_thang(2026, m, {1: 50, last: 50}))
    daily.update(_thang(2026, 7, {1: 50}))
    pace = insights.month_pace(daily, dt.date(2026, 7, 31), lookback=3)
    # Ngày 31 của tháng 6 (30 ngày) phải lấy tròn tháng: tỷ trọng thường lệ tới "ngày 31" là 100%.
    assert pace["expected_share_pct"] == pytest.approx(100)
    assert pace["projected_full_month"] == pytest.approx(50)


def test_worsen_bucket_chi_tang_khi_xau_them_tron_bac():
    assert insights.worsen_bucket(34.9, 10) == 30
    assert insights.worsen_bucket(39.9, 10) == 30
    assert insights.worsen_bucket(40.0, 10) == 40


def test_team_pace_gop_theo_doi_bo_doi_qua_nho_va_sap_theo_du_phong():
    members = (
        [{"team_code": "Q1", "target": 100, "actual": 20, "area_code": "MB"}] * 3
        + [{"team_code": "Q2", "target": 100, "actual": 45, "area_code": "MN"}] * 4
        + [{"team_code": "Q3", "target": 100, "actual": 5, "area_code": "MT"}] * 2   # 2 TDV: bỏ
        + [{"team_code": None, "target": 100, "actual": 5}]
    )
    teams = insights.team_pace(members, expected_share=0.5, min_members=3)

    assert [t["team_code"] for t in teams] == ["Q1", "Q2"]
    assert teams[0]["projection_pct"] == pytest.approx(40)   # 60/0.5/300
    assert teams[0]["achievement_pct"] == pytest.approx(20)
    assert teams[1]["projection_pct"] == pytest.approx(90)
    assert teams[1]["area_code"] == "MN"
    assert insights.team_pace(members, expected_share=0) == []


def _lich_su(so_thang, ca_thang, truoc_ngay):
    months = [insights.month_add(2026, 9, -k) for k in range(1, so_thang + 1)]
    return {mo: (ca_thang, truoc_ngay) for mo in months}


def test_silent_regular_customers_chi_bat_khach_mua_deu_ma_thang_nay_chua_mua():
    as_of = dt.date(2026, 9, 20)
    history = {
        "KH_IM_LANG": _lich_su(6, 80e6, 30e6),
        "KH_DA_MUA": _lich_su(6, 80e6, 30e6),
        "KH_NHO": _lich_su(6, 10e6, 5e6),
        "KH_THIEU_THANG": _lich_su(5, 80e6, 30e6),
        "KH_THUONG_MUA_CUOI_THANG": _lich_su(6, 80e6, 0),
    }
    rows = insights.silent_regular_customers(history, {"KH_DA_MUA": 1e6}, as_of,
                                             lookback=6, min_baseline=50e6)
    assert [r["customer_code"] for r in rows] == ["KH_IM_LANG"]
    assert rows[0]["baseline_monthly"] == pytest.approx(80e6)
    assert rows[0]["months_ordered_by_this_day"] == 6


def test_new_over45_debtors_chi_khach_moi_vuot_nguong():
    current = {
        "MOI": {"customer_name": "A", "sales_channel": "ETC", "area_code": "MN", "overdue_gt_45": 80e6},
        "CU": {"customer_name": "B", "sales_channel": "ETC", "area_code": "MN", "overdue_gt_45": 90e6},
        "NHO": {"customer_name": "C", "sales_channel": "OTC", "area_code": "MB", "overdue_gt_45": 20e6},
    }
    rows = insights.new_over45_debtors(current, {"CU": 1.0, "MOI": 0.0}, min_value=50e6)
    assert [r["customer_code"] for r in rows] == ["MOI"]


def test_overdue_customers_still_ordering_chi_no_tren_45_ngay_du_lon():
    from collections import namedtuple
    Row = namedtuple("Row", "customer_code customer_name sales_channel area_code overdue_gt_45 balance_end")
    receivables = [Row("A", "Bệnh viện A", "ETC", "MB", 60e6, 200e6),
                   Row("B", "Nhà thuốc B", "OTC", "MN", 40e6, 90e6),
                   Row("C", "Nhà thuốc C", "OTC", "MN", 70e6, 90e6)]
    rows = insights.overdue_customers_still_ordering(receivables, {"A": (2, 15e6), "B": (1, 5e6)}, 50e6)
    assert [(r["customer_code"], r["new_orders"]) for r in rows] == [("A", 2)]


def test_return_rate_breach_can_ca_ty_le_va_gia_tri():
    rate, breach = insights.return_rate_breach(250e6, 4_750e6, min_rate_pct=3, min_amount=200e6)
    assert rate == pytest.approx(5) and breach
    assert insights.return_rate_breach(30e6, 470e6, 3, 200e6)[1] is False   # 6% nhưng chỉ 30tr
    assert insights.return_rate_breach(0, 0, 3, 200e6) == (None, False)


def test_scope_bundle_loc_vung_kenh_va_an_dong_khong_ro_vung():
    bundle = {
        "as_of": dt.date(2026, 9, 20),
        "team_pace": {"evaluated": True, "at_risk": [
            {"team_code": "Q1", "region_key": "bac", "sales_channel": "OTC"},
            {"team_code": "Q2", "region_key": "nam", "sales_channel": "OTC"}]},
        "silent_customers": {"rows": [
            {"customer_code": "K1", "region_key": "bac", "sales_channel": "ETC"},
            {"customer_code": "K2", "region_key": None, "sales_channel": "OTC"}]},
        "new_over45": {"available": True, "rows": [{"customer_code": "N1", "region_key": "nam", "sales_channel": "ETC"}]},
        "overdue_ordering": {"rows": []},
    }
    bac_etc = insights.scope_insight_bundle(bundle, region="bac", channel="ETC")
    assert bac_etc["team_pace"]["at_risk"] == [] and bac_etc["team_pace"]["applicable"] is False
    assert [r["customer_code"] for r in bac_etc["silent_customers"]["rows"]] == ["K1"]
    assert bac_etc["new_over45"]["rows"] == [] and bac_etc["new_over45"]["available"] is True

    toan_quoc = insights.scope_insight_bundle(bundle)
    assert len(toan_quoc["team_pace"]["at_risk"]) == 2
    assert {r["customer_code"] for r in toan_quoc["silent_customers"]["rows"]} == {"K1", "K2"}


def test_rule_config_ghi_de_mot_phan_giu_mac_dinh_con_lai():
    cfg = insights.rule_config({"thresholds": {"business": {"insight_rules": {
        "channel_pace": {"max_gap_pct": {"OTC": 25}}}}}})
    assert cfg["channel_pace"]["max_gap_pct"] == {"OTC": 25, "ETC": 20}
    assert cfg["channel_pace"]["min_day"] == {"OTC": 10, "ETC": 8}
    assert cfg["team_pace"] == insights.DEFAULT_RULES["team_pace"]


def test_region_key_of_area():
    assert insights.region_key_of_area("MB2") == "bac"
    assert insights.region_key_of_area("MB1") == "bac"
    assert insights.region_key_of_area("MN") == "nam"
    assert insights.region_key_of_area(None) is None
