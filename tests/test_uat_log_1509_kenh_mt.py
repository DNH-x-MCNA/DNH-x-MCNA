# -*- coding: utf-8 -*-
"""UAT nhat ky 15/09/2026 - OTC-Only C-Level 14:17-14:20: "Doanh so thuc hien kenh MT cac thang tinh tu
dau nam" (dat) roi "bo sung ke hoach va % thuc hien tu ket qua tren" - thieu target kenh MT.
Nguon target: DIM_TargetVungMien ChannelCode='MT' (khop chi tieu dong MN1 'Kênh MT'). Du lieu gia.
"""
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
        return cls(2026, 8, 20)


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
            unit_price REAL, stt TEXT, city_id INTEGER, employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
            unit_price REAL, stt TEXT, employee_code TEXT, created_at TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, kenh_bh TEXT);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, position_code TEXT, area_code TEXT,
            dmsid TEXT, is_duplicate INTEGER);
        CREATE TABLE dim_targetvungmien (area_code TEXT, channel_code TEXT, amount REAL, doc_date TEXT);
    """)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (2,'HCM','MN')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('LC01','Long Chau',2,1,NULL,'MT')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('NT01','Nha thuoc',2,2,NULL,'GT')")
    conn.execute("INSERT INTO dim_nhanvien VALUES ('MN1','Kênh MT','QLV','MN','ASM01',1)")
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,?, 'SP', ?, 1, 1, ?, 2, 'NV', NULL, ?)", [
        ("2026-07-10", "LC01", 3_000_000, "H1", "ASM01"),
        ("2026-07-11", "NT01", 1_000_000, "H2", "ASM03"),
        ("2026-08-12", "LC01", 5_000_000, "H3", "ASM01"),
    ])
    conn.executemany("INSERT INTO dim_targetvungmien VALUES (?,?,?,?)", [
        ("MN", "MT", 5_000_000, "2026-07-01"), ("MN", "MT", 6_000_000, "2026-08-01"),
        ("MN", "GT", 9_000_000, "2026-07-01"), ("MB", "GT", 7_000_000, "2026-07-01"),
    ])
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)


def _kenh_mt(rows):
    mn = next(r for r in rows if r["area"] == "MN")
    return next(b for b in mn["channel_breakdown"] if b["name"] == "Kênh MT")


def test_doanh_thu_theo_vung_kem_ke_hoach_va_pct_kenh_mt_thang_tron(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    mt = _kenh_mt(rt.revenue_by_region("2026-07-01", "2026-07-31 23:59:59", channel="OTC"))

    assert (mt["revenue"], mt["plan_revenue"], mt["achievement_pct"]) == (3_000_000, 5_000_000, 60.0)


def test_khoang_khong_tron_thang_khong_tinh_ke_hoach(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    mt = _kenh_mt(rt.revenue_by_region("2026-07-01", "2026-07-15 23:59:59", channel="OTC"))

    assert mt["plan_revenue"] is None and mt["achievement_pct"] is None
    assert "khong tron thang" in mt["plan_note"]


def test_chuoi_thang_co_doanh_thu_ke_hoach_pct_kenh_mt_tung_thang(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.revenue_monthly_series(month_to="2026-08", months_back=2, include_yoy=False, scope_channel="OTC")

    kenh = [m["otc_special_channels"][0] for m in r["months"]]
    assert [(k["revenue"], k["plan_revenue"]) for k in kenh] == [(3_000_000, 5_000_000), (5_000_000, 6_000_000)]
    assert round(kenh[1]["achievement_pct"], 1) == 83.3
    assert "thang_dang_chay" in kenh[1] and "thang_dang_chay" not in kenh[0]


def test_tai_khoan_etc_khong_co_kenh_mt(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.revenue_monthly_series(month_to="2026-08", months_back=1, include_yoy=False, scope_channel="ETC")

    assert "otc_special_channels" not in r["months"][0]
