# -*- coding: utf-8 -*-
"""Kiem chung report_templates.promotion_effectiveness() (CTKM/khuyen mai) - CHUA TUNG co test
truoc 19/08/2026, domain hoan toan chua duoc rong toi trong chien dich accuracy-99. Ham nay hoan
toan dua vao Bravo live (_q_bravo, 2 lan goi) - gia lap theo THU TU goi (khong theo noi dung SQL,
vi 2 truy van co cau truc khac han nhau va thu tu goi la CO DINH: coverage truoc, du lieu chinh
sau CHI KHI khong bi source_gap)."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def _fake_q_bravo(coverage_date, main_rows=None, sync_at="2026-07-31T23:50:00"):
    calls = {"n": 0}

    def fn(sql, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            if coverage_date is None:
                return []
            return [{"CoverageDate": coverage_date, "LinkSyncedAt": sync_at, "LinkRowId": 999}]
        return main_rows or []

    return fn


def test_khong_co_coverage_thi_bao_source_gap(monkeypatch):
    monkeypatch.setattr(rt, "_q_bravo", _fake_q_bravo(coverage_date=None))

    result = rt.promotion_effectiveness()

    assert result["status"] == "source_gap"
    assert result["programs"] == []


def test_ky_hoi_vuot_qua_coverage_ve_tuong_lai_bao_source_gap(monkeypatch):
    """coverage_date la moc GAN NHAT (moi nhat) co du lieu lien ket, khong phai moc bat dau. Hoi
    ky BAT DAU SAU moc do (vuot ve tuong lai so voi du lieu da dong bo) PHAI bao source_gap, khong
    duoc am tham tra ve du lieu rong nhu the la 'khong co chuong trinh nao chay'."""
    monkeypatch.setattr(rt, "_q_bravo", _fake_q_bravo(coverage_date="2026-07-15"))

    result = rt.promotion_effectiveness(date_from="2026-08-01", date_to="2026-08-31")

    assert result["status"] == "source_gap"
    assert result["promotion_link_coverage_to"] == "2026-07-15"


def test_khong_chi_dinh_ky_thi_dung_thang_day_du_gan_nhat(monkeypatch):
    """Coverage moi den giua thang 7 (15/07) -> phai lui ve THANG 6 day du, khong dung thang 7 do
    (thang 7 chua het, so lieu se thieu ma khong ai biet)."""
    monkeypatch.setattr(rt, "_q_bravo", _fake_q_bravo(coverage_date="2026-07-15"))

    result = rt.promotion_effectiveness()

    assert result["period"] == {"from": "2026-06-01", "to": "2026-06-30"}
    assert "thang day du gan nhat" in result["warning"]


def test_ky_hoi_vuot_qua_coverage_bi_cat_va_bao_ro(monkeypatch):
    monkeypatch.setattr(rt, "_q_bravo", _fake_q_bravo(coverage_date="2026-07-15"))

    result = rt.promotion_effectiveness(date_from="2026-07-01", date_to="2026-07-31")

    assert result["period"]["to"] == "2026-07-15"  # cat tai coverage, khong suy dien het thang
    assert "cat tai moc nay" in result["warning"]


def test_scope_channel_khac_otc_thi_not_applicable(monkeypatch):
    monkeypatch.setattr(rt, "_q_bravo", _fake_q_bravo(coverage_date="2026-07-31"))

    result = rt.promotion_effectiveness(scope_channel="ETC")

    assert result["status"] == "not_applicable"


def test_xay_dung_dung_cac_truong_dau_ra_va_khong_goi_la_ROI(monkeypatch):
    rows = [
        {"ProgramId": 1, "ProgramCode": "KM01", "ProgramName": "Khuyen mai A",
         "Orders": 10, "Customers": 8, "AssociatedRevenue": 100_000_000,
         "OrdersWithoutInvoice": 2, "PaidProductOccurrences": 15,
         "GiftProductCount": 3, "ConfiguredProductCount": 5},
        # Chuong trinh KHONG co don nao khop hoa don -> tranh chia cho 0.
        {"ProgramId": 2, "ProgramCode": "KM02", "ProgramName": "Khuyen mai B",
         "Orders": 4, "Customers": 4, "AssociatedRevenue": 0,
         "OrdersWithoutInvoice": 4, "PaidProductOccurrences": 0,
         "GiftProductCount": 1, "ConfiguredProductCount": 2},
    ]
    monkeypatch.setattr(rt, "_q_bravo", _fake_q_bravo(coverage_date="2026-07-31", main_rows=rows))

    result = rt.promotion_effectiveness(date_from="2026-07-01", date_to="2026-07-31")

    km01 = next(p for p in result["programs"] if p["program_code"] == "KM01")
    km02 = next(p for p in result["programs"] if p["program_code"] == "KM02")

    assert km01["invoiced_orders"] == 8  # 10 don - 2 chua co hoa don
    assert km01["average_revenue_per_invoiced_order"] == 100_000_000 / 8
    assert km01["gift_product_count"] == 3
    assert km01["configured_product_count"] == 5

    # 0 don co hoa don -> KHONG duoc chia cho 0, phai tra ve 0.
    assert km02["invoiced_orders"] == 0
    assert km02["average_revenue_per_invoiced_order"] == 0.0

    note = result["interpretation_note"].lower()
    # "roi" chi duoc phep xuat hien trong cau canh bao "CHUA DU CO SO de ket luan ROI" - khong duoc
    # de mot cau nao khac trong ket qua khang dinh doanh thu gan CTKM LA ROI/uplift.
    assert "chua du co so ket luan roi" in note
    assert "khong cong doanh thu" in note
