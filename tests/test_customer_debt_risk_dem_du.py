# -*- coding: utf-8 -*-
"""17/09/2026 - customer_revenue_debt_risk bao so khach BANG DUNG gia tri limit.

customer_count truoc day = len(danh sach DA CAT theo LIMIT), nen tool noi "co 20 khach" du thuc te
co hang nghin. Do tren kho that cung ngay: limit=5/20/100 deu cho customer_count = chinh gia tri do,
trong khi tong that la 3.066 khach.

Day la lop loi thu BA cung kieu trong mot ngay, sau "hoi top 10 tra top 3" (cong no) va "50 hop
dong duoi 50%" (ETC): danh sach bi cat nhung khong co so dem that di kem, model doc so dong nhan
duoc va tuong do la tong. Hau qua nang nhat o cau V36 (thu no): cong tien cua vai khach roi goi do
la "tong so tien can thu".

Du lieu gia, khong cham Bravo."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path, so_khach=6):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, amount9 REAL,
            employee_code TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, amount9 REAL,
            employee_code TEXT);
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT,
            customer_name TEXT, sales_channel TEXT, area_code TEXT, balance_end REAL,
            overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL,
            total_overdue REAL);
    """)
    for i in range(so_khach):
        ma = f"KH{i:03d}"
        # Voi as_of 15/09 (chua het thang), tool lay ky GAN DAY = 01/06-31/08 va ky TRUOC =
        # 01/03-31/05. Phai dat hoa don o dung hai cua so do thi dieu kien "doanh thu giam" moi bat.
        conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-04-15',?,?,'NV1','GT')", (ma, 500_000_000.0))
        conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-07-15',?,?,'NV1','GT')", (ma, 200_000_000.0))
        conn.execute(
            "INSERT INTO fact_congno_khachhang VALUES ('2026-09-15','2026-09-15T10:00:00',?,?,"
            "'OTC','MB',?,0,0,0,?,?)", (ma, f"Khach {i}", 900_000_000.0, 100_000_000.0, 100_000_000.0))
    conn.commit()
    conn.close()
    return str(path)


def test_dem_du_tong_khach_du_danh_sach_bi_cat(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, so_khach=6))

    kq = rt.customer_revenue_debt_risk(as_of_date="2026-09-15", limit=2)

    assert kq["customer_count"] == 6        # TONG that, khong phu thuoc limit
    assert kq["returned_count"] == 2        # so dong thuc su tra ve
    assert len(kq["customers"]) == 2


def test_tong_khong_doi_khi_limit_doi(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, so_khach=6))

    nho = rt.customer_revenue_debt_risk(as_of_date="2026-09-15", limit=1)
    to = rt.customer_revenue_debt_risk(as_of_date="2026-09-15", limit=50)

    assert nho["customer_count"] == to["customer_count"] == 6
    assert (nho["returned_count"], to["returned_count"]) == (1, 6)


def test_co_quy_tac_cam_goi_phan_da_liet_ke_la_toan_bo(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, so_khach=6))

    kq = rt.customer_revenue_debt_risk(as_of_date="2026-09-15", limit=2)

    rule = kq["display_rule"]
    assert "KHONG duoc trinh bay nhu the day la toan bo" in rule
    assert "tong so tien can thu" in rule      # dung cai bay cua cau V36


def test_khong_co_khach_nao_thi_dem_bang_khong(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, so_khach=0))

    kq = rt.customer_revenue_debt_risk(as_of_date="2026-09-15", limit=5)

    assert kq["customer_count"] == 0 and kq["customers"] == []
