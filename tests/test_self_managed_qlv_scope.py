# -*- coding: utf-8 -*-
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
        CREATE TABLE vhoadon_otc (
            doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT
        );
        CREATE TABLE vhoadon_etc (
            doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT
        );
        CREATE TABLE dms_khachhang (code TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT);
        CREATE TABLE dim_nhanvien (
            employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT
        );
        CREATE TABLE fact_tonghopkhachhang (
            employee_code TEXT, manager_code TEXT, save_date TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,NULL,NULL,0,NULL)",
        [
            ("MBKV12", "Nguyen Thi Thanh Thuy", 1, "QLV", "MB", "ASM11"),
            ("OUT1", "Nguoi Ngoai Pham Vi", 0, "TDV", "MB", "D99"),
            ("NO_TEAM", "QLV Chua Xac Minh", 0, "QLV", "MB", "Q99"),
        ],
    )
    conn.executemany(
        "INSERT INTO fact_tonghopkhachhang VALUES (?,?,?)",
        [
            ("MBKV12", "TP_MB", "2026-08-24"),
            ("OUT1", "QLV_KHAC", "2026-08-24"),
            ("NO_TEAM", "TP_MB", "2026-08-24"),
        ],
    )
    conn.executemany("INSERT INTO dim_tinhthanhpho VALUES (?,?)", [(1, "MB"), (2, "MB")])
    conn.executemany("INSERT INTO dms_khachhang VALUES (?,?)", [("KH_SELF", 1), ("KH_OUT", 2)])
    conn.executemany(
        "INSERT INTO brv_sanpham VALUES (?,?)",
        [("SP_SELF", "San pham cua QLV"), ("SP_OUT", "San pham ngoai pham vi")],
    )
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-08-10", "KH_SELF", "SP_SELF", 100.0, 2.0, 50.0, "1", "ASM11"),
            ("2026-08-10", "KH_OUT", "SP_OUT", 9999.0, 1.0, 9999.0, "2", "D99"),
        ],
    )
    conn.commit()
    conn.close()


def test_verified_self_managed_qlv_sees_only_own_direct_sales(tmp_path, monkeypatch):
    db = str(tmp_path / "warehouse.db")
    _make_db(db)
    monkeypatch.setattr(local_warehouse, "DB_PATH", db)

    result = rt.call_template(
        "get_top_products",
        {"date_from": "2026-08-01", "date_to": "2026-08-24", "limit": 10},
        question="Top 10 san pham ban chay nhat?",
        scope_area_code="MB",
        scope_employee_code="MBKV12",
        scope_role="qlv",
    )

    assert result["ok"] is True, result.get("error")
    assert [row["item_code"] for row in result["result"]] == ["SP_SELF"]
    assert result["result"][0]["revenue"] == 100.0
    assert result.get("canh_bao")
    assert "CHI gom giao dich" in result["canh_bao"][0]


def test_unverified_zero_team_qlv_still_fails_closed(tmp_path, monkeypatch):
    db = str(tmp_path / "warehouse.db")
    _make_db(db)
    monkeypatch.setattr(local_warehouse, "DB_PATH", db)

    result = rt.call_template(
        "get_top_products",
        {"date_from": "2026-08-01", "date_to": "2026-08-24", "limit": 10},
        scope_area_code="MB",
        scope_employee_code="NO_TEAM",
        scope_role="qlv",
    )

    assert result["ok"] is False
    assert "Khong xac dinh duoc doi" in result["error"]
