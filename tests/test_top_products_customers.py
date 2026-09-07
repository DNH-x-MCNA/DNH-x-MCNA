# -*- coding: utf-8 -*-
"""Kiem chung report_templates.top_products()/top_customers() - Ngay 20 checklist (Khach hang &
San pham), CHUA TUNG co test truoc 19/08/2026. Khoa lai: loai hang khuyen mai (unit_price=0) khoi
so luong ban that (doanh thu VAN tinh du), xep hang doanh thu dung, ten san pham thieu co fallback
ro rang thay vi None."""
import datetime as real_dt
import io
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            kenh_bh TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        """
    )
    conn.commit()
    conn.close()


class _FixedDate(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 19)


def _freeze_today(monkeypatch):
    """Co dinh 'hom nay' de _detail_cutoff() (dua tren dt.date.today()) khong phu thuoc dong ho
    may that - tranh test tro nen khong on dinh (flaky) theo ngay chay."""
    monkeypatch.setattr(rt.dt, "date", _FixedDate)


def test_top_products_loai_hang_tang_khoi_so_luong_nhung_van_tinh_doanh_thu(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO brv_sanpham VALUES ('SP01','San pham A','G1','hop',1)")
    # Ban that: 10 don vi, gia > 0.
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    # Hang tang kem: 5 don vi, gia = 0 (unit_price=0) - doanh thu dong goi = 0 nhung KHONG duoc
    # tinh vao so luong ban that.
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-11','KH01','SP01',0,5,0,'HD2',1,'NV01','2026-07-11','ASM01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    _freeze_today(monkeypatch)

    result = rt.top_products(date_from="2026-07-01", date_to="2026-07-31")

    assert len(result) == 1
    assert result[0]["revenue"] == 1_000_000  # doanh thu = ca 2 dong (dong tang gia 0 khong doi gi)
    assert result[0]["qty"] == 10  # so luong CHI tinh dong ban that (unit_price>0)


def test_top_products_thieu_ten_co_fallback_ro_rang(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    # KHONG insert brv_sanpham cho 'SP_LA' - san pham mo coi, khong co trong danh muc.
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP_LA',500000,5,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    _freeze_today(monkeypatch)

    result = rt.top_products(date_from="2026-07-01", date_to="2026-07-31")

    assert result[0]["name"] == "(chua co ten - ma SP_LA)"


def test_top_products_tach_dung_theo_kenh(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO brv_sanpham VALUES ('SP01','San pham A','G1','hop',1)")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-07-10','KH02','SP01',2000000,20,100000,'HD2',1,'NV02','2026-07-10')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    _freeze_today(monkeypatch)

    otc_only = rt.top_products(date_from="2026-07-01", date_to="2026-07-31", channel="OTC")
    both = rt.top_products(date_from="2026-07-01", date_to="2026-07-31", channel="ALL")

    assert otc_only[0]["revenue"] == 1_000_000
    assert both[0]["revenue"] == 3_000_000  # gop ca OTC + ETC cung 1 ma san pham


def test_top_customers_xep_hang_dung_theo_doanh_thu(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH_LON','SP01',5000000,1,5000000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH_NHO','SP01',1000000,1,1000000,'HD2',1,'NV01','2026-07-10','ASM01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    _freeze_today(monkeypatch)

    result = rt.top_customers(date_from="2026-07-01", date_to="2026-07-31")

    assert result[0]["customer_code"] == "KH_LON"
    assert result[0]["revenue"] == 5_000_000
    assert result[0]["scope_revenue"] == 6_000_000
    assert round(result[0]["share_pct_of_scope"], 2) == 83.33
    assert result[1]["customer_code"] == "KH_NHO"
