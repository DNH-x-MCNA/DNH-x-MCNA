# -*- coding: utf-8 -*-
"""UAT nhat ky 17/09/2026 - "may cau ton kho ay, chat no lay tu moi cai snap dau nam khong lay den
hien tai nen lech nhieu". Xac nhan truc tiep tren Bravo (doc-only, tuan tu): BRV_TonKhoDK/
BRVSX_TonKhoDK la TON DAU NAM TAI CHINH (dung nghia "DK" = Dau Ky), Bravo khong cap nhat lai trong
nam - ModifiedAt gan nhat cua FiscalYear=2026 la 27/01/2026 (234 ngay truoc thoi diem phat hien).

Cong thuc cong bien dong lay NGUYEN VAN tu chinh thu tuc Bravo dbo.usp_StockLotFinance_Report:
Ton hien tai = Ton dau nam (vTonKhoDKLot) + SUM(Nhap - Xuat den ngay) tu vTheKhoLot.

Du lieu gia, khong cham Bravo that (bravo_query da duoc monkeypatch)."""
import datetime as dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import sync_warehouse as sw


def _kho(tmp_path):
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
    conn.execute("INSERT INTO brvsx_kho VALUES (90, 'A01', 'A01', 'Kho San Xuat')")
    # Ton dau nam (nhu Bravo nap ngay 27/01, dung im tu do): kho B04, ma hang 500, 100 don vi.
    conn.execute("INSERT INTO brv_tonkhodk VALUES (10, 500, 100.0, 5000.0, 1, 2026)")
    conn.execute("INSERT INTO brvsx_tonkhodk VALUES ('A01', 90, 700, 200.0, 9000.0, 1, 2026)")
    # Ton kho theo lo dau nam: 2 lo cua ma 500 tai B04.
    conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B04', 10, 500, 'LOT-A', 60.0, 1, 2026)")
    conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B04', 10, 500, 'LOT-B', 40.0, 1, 2026)")
    conn.commit()
    conn.close()
    return str(path)


def test_ton_kinh_doanh_cong_dung_bien_dong_khong_dung_im_o_dau_nam(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    def gia_bravo_query(sql, **params):
        if "ClassCode='TM'" in sql and "ItemLotCode" not in sql:
            return ["WarehouseCode", "ItemId", "delta_qty"], [("B04", 500, 45.0)]
        if "ClassCode='SX'" in sql:
            return ["WarehouseCode", "ItemId", "delta_qty"], [("A01", 700, -30.0)]
        if "ItemLotCode" in sql:
            # LOT-A ban het (-60), LOT-B nhan them hang moi (+25) - dung ca hai chieu.
            return (["WarehouseCode", "ItemId", "ItemLotCode", "delta_qty"],
                    [("B04", 500, "LOT-A", -60.0), ("B04", 500, "LOT-B", 25.0)])
        raise AssertionError(f"SQL khong mong doi: {sql}")

    monkeypatch.setattr(sw, "bravo_query", gia_bravo_query)

    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 17))

    conn = sqlite3.connect(local_warehouse.DB_PATH)
    try:
        # Kinh doanh: 100 (dau nam) + 45 (bien dong) = 145, giu nguyen dong dau nam (khong UPDATE).
        tong_kd = conn.execute(
            "SELECT SUM(quantity) FROM brv_tonkhodk WHERE warehouse_id=10 AND item_id=500 "
            "AND is_active=1 AND fiscal_year=2026").fetchone()[0]
        assert tong_kd == 145.0

        # San xuat: 200 (dau nam) + (-30) (xuat nhieu hon nhap) = 170.
        tong_sx = conn.execute(
            "SELECT SUM(quantity) FROM brvsx_tonkhodk WHERE warehouse_id=90 AND item_id=700 "
            "AND is_active=1 AND year=2026").fetchone()[0]
        assert tong_sx == 170.0

        # Theo lo: LOT-A ban het (60-60=0 -> XOA, khong con dong lech), LOT-B con 40+25=65.
        lots = dict(conn.execute(
            "SELECT item_lot_code, quantity FROM brv_tonkhodklot "
            "WHERE warehouse_id=10 AND item_id=500 AND year=2026").fetchall())
        assert lots == {"LOT-B": 65.0}          # LOT-A da bien mat, KHONG con dong "0 don vi" ma
        # Tong theo lo van khop voi tong kinh doanh moi (145): 65 (LOT-B) + phan da chen o tren (45)
        # + ton dau nam LOT-A da xoa (60) - LOT-A ban het (60) = 145. Kiem bang cach doc lai tu dong
        # da chen o bang tong hop:
        assert conn.execute(
            "SELECT SUM(quantity) FROM brv_tonkhodklot WHERE warehouse_id=10 AND item_id=500"
        ).fetchone()[0] == 65.0
    finally:
        conn.close()


def test_moi_lo_van_dung_dung_mot_dong_khong_bi_dem_hai_lan(tmp_path, monkeypatch):
    """inventory_expiry_report() doc TUNG DONG rieng le (khong SUM) - moi lo PHAI van la DUNG MOT
    dong sau khi cong bien dong, khong duoc chen them thanh 2 dong cho cung 1 lo."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    def gia_bravo_query(sql, **params):
        if "ItemLotCode" in sql:
            return (["WarehouseCode", "ItemId", "ItemLotCode", "delta_qty"],
                    [("B04", 500, "LOT-A", 10.0)])
        return ["WarehouseCode", "ItemId", "delta_qty"], []

    monkeypatch.setattr(sw, "bravo_query", gia_bravo_query)
    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 17))

    conn = sqlite3.connect(local_warehouse.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT quantity FROM brv_tonkhodklot WHERE warehouse_id=10 AND item_id=500 "
            "AND item_lot_code='LOT-A'").fetchall()
        assert rows == [(70.0,)]                 # 60 (dau nam) + 10, DUNG MOT dong - khong phai 2
    finally:
        conn.close()


def test_khong_co_bien_dong_thi_giu_nguyen_ton_dau_nam(tmp_path, monkeypatch):
    """Khong co du lieu tra ve (vd loi quyen/VPN) -> KHONG duoc xoa hay lam trong bat cu gi, giu
    nguyen ton dau nam da nap - cu con hon khong co."""
    path = _kho(tmp_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", path)
    monkeypatch.setattr(sw, "bravo_query", lambda sql, **params: (["a"], []))

    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 17))

    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT quantity FROM brv_tonkhodk").fetchall() == [(100.0,)]
        assert conn.execute("SELECT COUNT(*) FROM brv_tonkhodklot").fetchone()[0] == 2
    finally:
        conn.close()


def test_loi_ket_noi_bravo_khong_lam_hong_sync_con_lai(tmp_path, monkeypatch):
    """Dung dung tinh than sync_fact_thongketinhluong/sync_fact_congno: loi (quyen/VPN) khong duoc
    nem ra ngoai lam hong phan sync khac dang chay chung mot lan."""
    path = _kho(tmp_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", path)

    def loi(sql, **params):
        raise RuntimeError("gia lap mat VPN")

    monkeypatch.setattr(sw, "bravo_query", loi)

    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 17))     # KHONG duoc raise

    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT quantity FROM brv_tonkhodk").fetchall() == [(100.0,)]
    finally:
        conn.close()


def test_ma_hang_ton_dau_nam_bang_0_van_duoc_them_neu_co_bien_dong(tmp_path, monkeypatch):
    """Mat hang moi phat sinh sau ngay dau nam (khong co dong ton dau nam) van phai xuat hien khi
    co bien dong, khong duoc bo sot vi "khong co dong de UPDATE"."""
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
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    def gia_bravo_query(sql, **params):
        if "ClassCode='TM'" in sql and "ItemLotCode" not in sql:
            return ["WarehouseCode", "ItemId", "delta_qty"], [("B04", 999, 30.0)]
        return ["WarehouseCode", "ItemId", "delta_qty"], []

    monkeypatch.setattr(sw, "bravo_query", gia_bravo_query)
    sw.sync_tonkho_hien_tai(as_of=dt.date(2026, 9, 17))

    conn = sqlite3.connect(path)
    try:
        assert conn.execute(
            "SELECT quantity FROM brv_tonkhodk WHERE item_id=999").fetchall() == [(30.0,)]
    finally:
        conn.close()
