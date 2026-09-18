# -*- coding: utf-8 -*-
"""18/09/2026 - cau C34: mot so SKU chatbot tra ve KHONG co trong checker S22.

Nguyen nhan: checker dung #sales voi cua so @FromDate 2025-09-01 den @ToDate 2026-09-01, tuc CAT
BO hoan toan thang 9/2026. Tool thi lay den latest_data_date() (15/09/2026), nen SKU co lan ban dau
tien roi vao nua dau thang 9 chi xuat hien o phia chatbot. Do tren kho that ngay 18/09: tool ra 151
ung vien, checker ra 148 - lech dung 3 SKU deu co first_observed 2026-09, trong do 60106200011 dung
hang 7 theo doanh thu thang dau nen chac chan lot vao cau tra loi.

Sai o day khong phai "thua ba dong". Doanh thu thang dau cua ba SKU do do tren NUA THANG roi duoc
xep chung bang voi SKU do tron 30 ngay - cung lop loi like-for-like da sua o YTD (cau C02). Va vi
moi moc tuoi 1/3/6/12 thang cua chung deu chua den han, chung khong dong gop gi cho cau hoi ngoai
nhieu.

Du lieu gia, khong cham Bravo."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path):
    """Bien trai lich su 2025-09. SKU_TRON ghi nhan dau 2026-07 (thang da dong),
    SKU_DO_DANG ghi nhan dau 2026-09 (thang dang chay, du lieu moi den 15/09)."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
    """)
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,?)", [
        ("2025-09-03", "KH1", "SKU_CU", 1_000.0),        # neo bien trai lich su
        ("2026-08-20", "KH1", "SKU_CU", 1_000.0),
        ("2026-07-10", "KH1", "SKU_TRON", 900.0),
        ("2026-08-10", "KH2", "SKU_TRON", 900.0),
        ("2026-09-05", "KH1", "SKU_DO_DANG", 5_000.0),   # doanh thu cao nhat, nhung nua thang
    ])
    conn.executemany("INSERT INTO brv_sanpham VALUES (?,?,?,?,?)", [
        ("SKU_CU", "San pham cu", "G1", "hop", 1),
        ("SKU_TRON", "San pham thang du", "G1", "hop", 2),
        ("SKU_DO_DANG", "San pham thang do dang", "G1", "hop", 3),
    ])
    conn.commit()
    conn.close()
    return str(path)


def test_sku_ghi_nhan_dau_o_thang_chua_tron_khong_dung_de_so_sanh(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15", lookback_months=12)

    theo_ma = {r["item_code"]: r for r in kq["products"]}
    do_dang = theo_ma["SKU_DO_DANG"]
    assert do_dang["first_observed_sale_month"] == "2026-09"
    assert do_dang["first_observed_month_complete"] is False
    assert do_dang["valid_for_launch_age_analysis"] is False
    assert any("CHUA TRON" in ly for ly in do_dang["ly_do_khong_dung_cho_phan_tich_tuoi"])


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

    assert kq["total_count"] == 2                       # SKU_CU o bien trai, ngoai cua so ung vien
    assert kq["so_sku_thang_dau_chua_tron"] == 1
    assert kq["so_sku_dung_cho_phan_tich_tuoi"] == 1
    assert "KHONG duoc dua vao bang so sanh" in kq["answer_rule"]


def test_bao_so_thang_lich_su_truoc_moc_ghi_nhan_dau(tmp_path, monkeypatch):
    """Bang chung 'SKU moi' manh hay yeu tuy vao co bao nhieu thang sach phia truoc. Kho chi giu
    12 thang nen SKU ghi nhan dau ngay sat bien trai co the chi la SKU ban lai sau ky nghi."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-15", lookback_months=12)

    theo_ma = {r["item_code"]: r for r in kq["products"]}
    assert theo_ma["SKU_TRON"]["months_of_history_before_first_sale"] == 10   # 2025-09 -> 2026-07
    assert theo_ma["SKU_DO_DANG"]["months_of_history_before_first_sale"] == 12
    assert any("ban lai sau mot thoi gian nghi" in l for l in kq["limitations"])


def test_thang_cuoi_da_dong_thi_khong_loai_oan(tmp_path, monkeypatch):
    """Hoi vao dung ngay cuoi thang: 2026-09 da tron, SKU thang 9 phai duoc dung binh thuong."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.product_first_observed_performance(as_of_date="2026-09-30", lookback_months=12)

    do_dang = {r["item_code"]: r for r in kq["products"]}["SKU_DO_DANG"]
    assert do_dang["first_observed_month_complete"] is True
    assert do_dang["valid_for_launch_age_analysis"] is True
    assert kq["so_sku_thang_dau_chua_tron"] == 0
