# -*- coding: utf-8 -*-
"""UAT C41 29/09/2026 - "chatbot van tra ve ton dau nam tai chinh chu khong lay real time".

So luong chatbot tra (qua SQL tu do) DA la ton hien tai: tu 17/09 sync_tonkho_hien_tai chen them dong
bien dong nhap-xuat (amount NULL) vao brv_tonkhodk/brvsx_tonkhodk. Nhung mo ta bang trong
schema_context.py van bao model "TON KHO DAU KY... KHONG cap nhat trong nam - PHAI noi ro day la anh
chup dau nam", nen model dan nhan sai cho so dung. Test nay khoa mo ta vao DUNG hanh vi cua sync.
Du lieu gia, khong cham Bravo."""
import datetime as dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import schema_context
import sync_warehouse as sw


def _mo_ta_bang(ten):
    ctx = schema_context.SCHEMA_CONTEXT
    start = ctx.index(f"\n{ten}")
    return ctx[start:ctx.index("\n\n", start + 1)]


def test_mo_ta_khong_con_bao_model_so_luong_la_dau_nam():
    mo_ta = _mo_ta_bang("brv_tonkhodk")
    assert "KHONG phai ton kho hien" not in mo_ta
    assert "anh chup dau nam, khong duoc goi" not in mo_ta
    assert "SO LUONG LA TON HIEN TAI, GIA TRI LA DAU NAM" in mo_ta
    assert "amount IS NOT NULL" in mo_ta          # cach lay rieng ton dau nam
    assert "amount IS NULL" in mo_ta              # cach nhan biet sync bien dong loi
    assert "ton HIEN TAI" in _mo_ta_bang("brvsx_tonkhodk + brvsx_kho")


def test_sau_dong_bo_sum_quantity_la_ton_hien_tai_con_amount_la_dau_nam(tmp_path, monkeypatch):
    """Dung cac cau SQL ma mo ta huong dan model viet, tren kho gia da qua sync_tonkho_hien_tai."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brvsx_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL,
            amount REAL, is_active INTEGER, fiscal_year INTEGER);
        CREATE TABLE brvsx_tonkhodk (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            quantity REAL, amount REAL, is_active INTEGER, year INTEGER);
        CREATE TABLE brv_tonkhodklot (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            item_lot_code TEXT, quantity REAL, is_active INTEGER, year INTEGER);
    """)
    conn.execute("INSERT INTO brv_kho VALUES (10, 'B04', 'B04', 'Kho KD Mien Nam')")
    # Nhu ma 74260010030 that: dau nam 3.576.428 don vi, gia tri dau nam -413.425 d.
    conn.execute("INSERT INTO brv_tonkhodk VALUES (10, 500, 3576428.0, -413425.0, 1, 2026)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    def gia_bravo_query(sql, **params):
        if "ClassCode='TM'" in sql and "ItemLotCode" not in sql:
            return ["WarehouseCode", "ItemId", "delta_qty"], [("B04", 500, 2377110.0)]
        return ["WarehouseCode", "ItemId", "delta_qty"], []

    monkeypatch.setattr(sw, "bravo_query", gia_bravo_query)
    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 29))

    conn = sqlite3.connect(path)
    try:
        hien_tai, gia_tri = conn.execute(
            "SELECT SUM(quantity), SUM(amount) FROM brv_tonkhodk WHERE fiscal_year=2026 AND is_active=1"
        ).fetchone()
        dau_nam = conn.execute(
            "SELECT SUM(quantity) FROM brv_tonkhodk WHERE fiscal_year=2026 AND is_active=1 "
            "AND amount IS NOT NULL").fetchone()[0]
        so_dong_bien_dong = conn.execute(
            "SELECT COUNT(*) FROM brv_tonkhodk WHERE fiscal_year=2026 AND amount IS NULL").fetchone()[0]
    finally:
        conn.close()

    # 3.576.428 dau nam (kho may dev 24/09) + bien dong gia lap = 5.953.538, so chatbot tra 29/09.
    assert hien_tai == 5953538.0
    assert dau_nam == 3576428.0
    assert gia_tri == -413425.0           # gia tri chi co tu dong dau nam
    assert so_dong_bien_dong == 1
