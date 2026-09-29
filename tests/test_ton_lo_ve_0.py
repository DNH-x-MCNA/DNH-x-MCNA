# -*- coding: utf-8 -*-
"""29/09/2026 (UAT C42): lo da ban het phai con dong ton = 0, khong bi xoa.

Truoc day sync_tonkho_hien_tai xoa lo cong xong = 0 va HAVING bo qua lo nhap roi ban het trong nam -> SKU het hang
khong con dong nao; get_sku_revenue_drop_vs_stock coi la "chua biet" (SQL doi chieu tren Bravo: 21 SKU ton = 0, tool:
0), va supply_risk chi xet SKU con ton > 0 nen bo sot SKU het sach ma van dang ban.
Du lieu gia, khong cham Bravo.
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
import sync_warehouse as sw


def test_lo_nhap_roi_ban_het_trong_nam_van_co_dong_ton_0(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brvsx_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL, amount REAL,
            is_active INTEGER, fiscal_year INTEGER);
        CREATE TABLE brvsx_tonkhodk (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER, quantity REAL,
            amount REAL, is_active INTEGER, year INTEGER);
        CREATE TABLE brv_tonkhodklot (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            item_lot_code TEXT, quantity REAL, is_active INTEGER, year INTEGER);
        INSERT INTO brv_kho VALUES (10, 'B04', 'B04', 'Kho KD Mien Nam');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    def gia_bravo(sql, **params):
        if "ItemLotCode" in sql:
            assert "HAVING" not in sql, "khong duoc bo qua lo co bien dong rong = 0"
            # LOT-MOI: khong co ton dau nam, nhap 50 roi ban 50 trong nam -> bien dong rong 0.
            return ["WarehouseCode", "ItemId", "ItemLotCode", "delta_qty"], [("B04", 900, "LOT-MOI", 0.0)]
        return ["WarehouseCode", "ItemId", "delta_qty"], []

    monkeypatch.setattr(sw, "bravo_query", gia_bravo)
    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 28))

    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT item_lot_code, quantity FROM brv_tonkhodklot WHERE item_id=900").fetchall() \
            == [("LOT-MOI", 0.0)]
    finally:
        conn.close()


def _kho_ton(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_tonkhodklot (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            item_lot_code TEXT, quantity REAL, is_active INTEGER, year INTEGER);
        CREATE TABLE brv_lot (item_lot_code TEXT, item_id INTEGER, mfg_date TEXT, expiry_date TEXT, is_active INTEGER);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
            unit_price REAL, employee_code TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT);
        INSERT INTO brv_kho VALUES (2, 'B02', 'KMB', 'Kho Mien Bac');
        INSERT INTO brv_sanpham VALUES ('HET', 'Het hang con ban', 'G', 'hop', 1);
        INSERT INTO brv_sanpham VALUES ('NGUNG', 'Het hang khong ban nua', 'G', 'hop', 2);
        INSERT INTO brv_sanpham VALUES ('CON', 'Con hang', 'G', 'hop', 3);
        INSERT INTO brv_tonkhodklot VALUES ('B02', 2, 1, 'L1', 0, 1, 2026);
        INSERT INTO brv_tonkhodklot VALUES ('B02', 2, 2, 'L2', 0, 1, 2026);
        INSERT INTO brv_tonkhodklot VALUES ('B02', 2, 3, 'L3', 100, 1, 2026);
        INSERT INTO brv_lot VALUES ('L1', 1, '2026-01-01', '2027-01-01', 1);
        INSERT INTO brv_lot VALUES ('L3', 3, '2026-01-01', '2027-06-01', 1);
    """)
    # Nhu cau 3 thang da chot (07-09/2026 khi hom nay la 10/2026): HET con ban 90, CON ban 30.
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?)", [
        ("2026-08-10", "KH1", "HET", 900.0, 90.0, 10.0, "NV1"),
        ("2026-08-10", "KH1", "CON", 300.0, 30.0, 10.0, "NV1"),
    ])
    conn.commit()
    conn.close()


class _NgayCoDinh(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 5)


def test_ton_kho_het_sach_con_nhu_cau_la_thieu_hang_lo_0_khong_vao_han_dung(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _kho_ton(path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _NgayCoDinh)
    monkeypatch.setattr(rt, "get_sync_meta", lambda _table: (None, None, None))

    kq = rt.inventory_expiry_report(limit=30)

    # Han dung chi tinh lo con hang: dung 1 lo (L3), khong co lo 0 nao.
    assert sum(b["so_lo"] for b in kq["summary"].values()) == 1
    assert kq["khong_xac_dinh_han"] == 0
    rui_ro = {r["item_code"]: r for r in kq["supply_risk"]["rows"]}
    assert rui_ro["HET"]["status"] == "CO_NGUY_CO_THIEU_HANG_DERIVED" and rui_ro["HET"]["het_hang_ghi_nhan"] is True
    assert "NGUNG" not in rui_ro, "het hang ma khong con ban thi khong phai 'ton khong ban'"
    assert "het_hang_ghi_nhan" not in rui_ro.get("CON", {})
