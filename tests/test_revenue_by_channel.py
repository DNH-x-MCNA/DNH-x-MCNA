# -*- coding: utf-8 -*-
"""Kiem chung report_templates.revenue_by_channel() - CHUA co test rieng cho logic co ban (tong
OTC/ETC, gioi han kenh scope_channel) truoc 19/08/2026."""
import datetime as real_dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


class _FixedDate(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 19)


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
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            kenh_bh TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        """
    )
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-11','KH01','SP01',500000,5,100000,'HD2',1,'NV01','2026-07-11','ASM01')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-07-10','KH02','SP01',2000000,20,100000,'HD3',1,'NV02','2026-07-10')")
    conn.commit()
    conn.close()


def test_tong_dung_ca_2_kenh_va_dem_dung_so_hoa_don(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)

    result = rt.revenue_by_channel(date_from="2026-07-01", date_to="2026-07-31")

    assert result["otc"]["revenue"] == 1_500_000
    assert result["otc"]["invoices"] == 2  # 2 chung tu khac nhau (stt HD1, HD2)
    assert result["etc"]["revenue"] == 2_000_000
    assert result["total"]["revenue"] == 3_500_000
    assert "channel_scope" not in result


def test_scope_channel_otc_khong_tra_du_lieu_etc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)

    result = rt.revenue_by_channel(date_from="2026-07-01", date_to="2026-07-31", scope_channel="OTC")

    assert result["otc"]["revenue"] == 1_500_000
    assert result["etc"]["revenue"] == 0.0
    assert result["etc"]["invoices"] == 0
    assert "channel_scope" in result
