# -*- coding: utf-8 -*-
"""Ton kho phai gom CA HAI he: kinh doanh (brv_*) va san xuat (brvsx_*).

Truoc 04/09/2026 chi doc he kinh doanh (nam 2026: ~5,4 ty) va trinh bay nhu ton kho TOAN CONG TY,
trong khi he san xuat co ~229,8 ty - tuc bao 2% su that, sai 43 lan. Hai he tach han (kiem chung
tren Bravo: khong trung mot Id kho nao, cap (kho, mat hang) nam 2026 trung 0 dong).
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path, monkeypatch, co_bang_sx=True):
    path = tmp_path / "wh.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL,
            amount REAL, is_active INTEGER, fiscal_year INTEGER);
        """
    )
    con.execute("INSERT INTO brv_kho VALUES (1,'B02','K1','Kho MB')")
    # Hai nam: 2025 va 2026 - phai CHI lay 2026.
    con.execute("INSERT INTO brv_tonkhodk VALUES (1,10,100,1000,1,2025)")
    con.execute("INSERT INTO brv_tonkhodk VALUES (1,10,200,2000,1,2026)")
    if co_bang_sx:
        con.executescript(
            """
            CREATE TABLE brvsx_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
            CREATE TABLE brvsx_tonkhodk (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
                quantity REAL, amount REAL, is_active INTEGER, year INTEGER);
            """
        )
        # Id kho 1 o he SAN XUAT la kho KHAC voi Id kho 1 o he kinh doanh - hai he doc lap.
        con.execute("INSERT INTO brvsx_kho VALUES (1,NULL,'SX1','Kho thanh pham')")
        con.execute("INSERT INTO brvsx_kho VALUES (2,'A01','SX2','Kho A01')")
        con.execute("INSERT INTO brvsx_tonkhodk VALUES (NULL,1,99,5000,50000,1,2026)")
        con.execute("INSERT INTO brvsx_tonkhodk VALUES ('A01',2,98,3000,30000,1,2026)")
        con.execute("INSERT INTO brvsx_tonkhodk VALUES (NULL,1,99,9999,99999,1,2025)")
    con.commit()
    con.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))


def test_tra_ve_ca_hai_he_va_danh_dau_ro(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    rows = rt.inventory_by_region()
    he = {r["he_thong"] for r in rows}
    assert he == {"KINH_DOANH", "SAN_XUAT"}, "phai tra ve CA HAI he, khong chi kho kinh doanh"

    kd = [r for r in rows if r["he_thong"] == "KINH_DOANH"]
    sx = [r for r in rows if r["he_thong"] == "SAN_XUAT"]
    assert len(kd) == 1 and kd[0]["tong_gia_tri"] == 2000, "chi lay nam moi nhat (2026), khong cong 2025"
    assert sum(r["tong_gia_tri"] for r in sx) == 80000, "san xuat: 50000 + 30000, khong tinh dong 2025"
    # Gia tri that cua cong ty phai la tong ca hai he.
    assert sum(r["tong_gia_tri"] for r in rows) == 82000


def test_tai_khoan_bi_gioi_han_vung_KHONG_thay_kho_san_xuat(tmp_path, monkeypatch):
    """Kho san xuat khong thuoc vung MB/MT/MN nao - cung quy tac dang ap cho B01."""
    _kho(tmp_path, monkeypatch)
    rows = rt.inventory_by_region(scope_area_code="MB")
    assert {r["he_thong"] for r in rows} == {"KINH_DOANH"}
    assert all(r["area_code"] == "B02" for r in rows)


def test_kho_cu_chua_co_bang_san_xuat_thi_CANH_BAO_chu_khong_sap(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch, co_bang_sx=False)
    rows = rt.inventory_by_region()
    assert rows, "van phai tra ve phan kho kinh doanh"
    assert all(r["he_thong"] == "KINH_DOANH" for r in rows)
    assert any("SAN XUAT" in (r.get("canh_bao") or "") for r in rows), (
        "thieu bang san xuat ma im lang = lai bao 2% su that nhu truoc")
