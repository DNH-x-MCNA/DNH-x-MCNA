# -*- coding: utf-8 -*-
"""C34: phai giu du lich su SKU tu 01/2024 va chi dung cac thang da dong.

Neu chi giu 12 thang chi tiet, SKU tung ban 02/2025 lai bi goi la moi o 10/2025. Du lieu gia,
khong cham Bravo.
"""
import datetime as dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt
import sync_warehouse as sync


def _kho(tmp_path):
    """Bien trai lich su 2024-09. SKU_TRON ghi nhan dau 2026-07 (thang da dong),
    SKU_DO_DANG ghi nhan dau 2026-09 (thang dang chay, du lieu moi den 15/09)."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
    """)
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,?)", [
        ("2024-09-03", "KH1", "SKU_CU", 1_000.0),        # neo bien trai lich su
        ("2026-08-20", "KH1", "SKU_CU", 1_000.0),
        # Tung ban tu 02/2025, sau do ban lai gia tri lon 10/2025. Khong duoc nham 10/2025 la thang dau.
        ("2025-02-10", "KH1", "SKU_OLD", 97_142_857.0),
        ("2025-10-10", "KH1", "SKU_OLD", 446_794_286.0),
        ("2026-07-10", "KH1", "SKU_TRON", 900.0),
        ("2026-08-10", "KH2", "SKU_TRON", 900.0),
        ("2026-09-05", "KH1", "SKU_DO_DANG", 5_000.0),   # doanh thu cao nhat, nhung nua thang
    ])
    conn.executemany("INSERT INTO brv_sanpham VALUES (?,?,?,?,?)", [
        ("SKU_CU", "San pham cu", "G1", "hop", 1),
        ("SKU_TRON", "San pham thang du", "G1", "hop", 2),
        ("SKU_DO_DANG", "San pham thang do dang", "G1", "hop", 3),
        ("SKU_OLD", "San pham da tung ban", "G1", "hop", 4),
    ])
    conn.commit()
    conn.close()
    return str(path)


def test_thang_hien_tai_chua_tron_khong_nam_trong_cua_so_so_sanh(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15", lookback_months=12)

    theo_ma = {r["item_code"]: r for r in kq["products"]}
    assert "SKU_DO_DANG" not in theo_ma
    assert kq["complete_through_month"] == "2026-08"
    assert kq["so_sku_thang_dau_chua_tron"] == 0


def test_sku_thang_da_dong_van_dung_binh_thuong(tmp_path, monkeypatch):
    """Khong duoc sieng nang qua tay: thang da dong thi van hop le."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15", lookback_months=12)

    tron = {r["item_code"]: r for r in kq["products"]}["SKU_TRON"]
    assert tron["first_observed_month_complete"] is True
    assert tron["valid_for_launch_age_analysis"] is True
    assert tron["ly_do_khong_dung_cho_phan_tich_tuoi"] == []


def test_dem_rieng_so_sku_thang_dau_chua_tron(tmp_path, monkeypatch):
    """Model phai doc duoc ngay o cap tong: bao nhieu dong khong dung de so sanh."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15", lookback_months=12)

    assert kq["total_count"] == 3                       # SKU_CU o bien trai + SKU_OLD + SKU_TRON
    assert kq["so_sku_thang_dau_chua_tron"] == 0
    assert kq["so_sku_dung_cho_phan_tich_tuoi"] == 2
    assert "KHONG duoc dua vao bang so sanh" in kq["answer_rule"]


def test_bao_so_thang_lich_su_truoc_moc_ghi_nhan_dau(tmp_path, monkeypatch):
    """Bang chung 'SKU moi' manh hay yeu tuy vao co bao nhieu thang sach phia truoc."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15", lookback_months=12)

    theo_ma = {r["item_code"]: r for r in kq["products"]}
    assert theo_ma["SKU_TRON"]["months_of_history_before_first_sale"] == 22   # 2024-09 -> 2026-07
    assert theo_ma["SKU_OLD"]["first_observed_sale_month"] == "2025-02"
    assert theo_ma["SKU_OLD"]["first_observed_revenue"] == 97_142_857.0
    assert any("ban lai sau mot thoi gian nghi" in l for l in kq["limitations"])


def test_thang_cuoi_da_dong_thi_khong_loai_oan(tmp_path, monkeypatch):
    """Hoi vao dung ngay cuoi thang: 2026-09 da tron, SKU thang 9 phai duoc dung binh thuong."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-30", lookback_months=12)

    do_dang = {r["item_code"]: r for r in kq["products"]}["SKU_DO_DANG"]
    assert do_dang["first_observed_month_complete"] is True
    assert do_dang["valid_for_launch_age_analysis"] is True
    assert kq["so_sku_thang_dau_chua_tron"] == 0


def test_sku_cu_khong_bi_goi_nham_la_moi_tu_dot_ban_lai(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15")

    old = {r["item_code"]: r for r in kq["products"]}["SKU_OLD"]
    assert old["first_observed_sale_month"] == "2025-02"
    assert old["first_observed_revenue"] == 97_142_857.0


def test_kho_chua_keo_lai_tu_2024_thi_c34_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL);
    """)
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2025-09-03','KH1','SKU',100)")
    conn.commit(); conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15")

    assert kq["status"] == "HISTORY_INCOMPLETE"
    assert kq["products"] == []
    assert "sync_warehouse.py --full" in kq["note"]


def test_dong_bo_giu_chi_tiet_tu_dau_2024():
    assert sync._detail_cutoff_date(dt.date(2030, 1, 1)) == dt.date(2024, 1, 1)
