# -*- coding: utf-8 -*-
"""UAT C41 29/09/2026 - "Thuoc ho vien ngam bo phe" ra 1.350.134 o bao cao can han nhung 1.277.726 o cau Top 20.

Kiem tren may 24 (SQLite, chi doc): bang tong 1.277.726 = bang lo cong MOI lo; bang lo chi cong lo duong = 1.350.134;
co 4 lo am. inventory_expiry_report loc quantity >= 0 nen ton theo SKU (supply_risk: cham luan chuyen / thieu hang)
lon hon so sach dung bang phan am. Du lieu gia, khong cham Bravo."""
import datetime as dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


class _NgayCoDinh(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 5)


def _kho(path):
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
        INSERT INTO brv_sanpham VALUES ('32200000670', 'Thuoc ho vien ngam bo phe Nam Ha', 'G', 'Vien', 1);
        INSERT INTO brv_sanpham VALUES ('AM', 'Ma chi con lo am', 'G', 'Vien', 2);
    """)
    lo = [("L%d" % i, q) for i, q in enumerate((700_000.0, 400_134.0, 250_000.0), 1)]           # duong: 1.350.134
    lo += [("A%d" % i, q) for i, q in enumerate((-40_000.0, -20_000.0, -10_000.0, -2_408.0), 1)]  # am: -72.408
    for ma, q in lo:
        conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B02', 2, 1, ?, ?, 1, 2026)", (ma, q))
        conn.execute("INSERT INTO brv_lot VALUES (?, 1, '2026-01-01', '2028-01-01', 1)", (ma,))
    conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B02', 2, 2, 'X1', -50.0, 1, 2026)")
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?)", [
        ("2026-08-10", "KH1", "32200000670", 1e8, 30_000.0, 1.0, "NV1"),
        ("2026-08-10", "KH1", "AM", 1e6, 300.0, 1.0, "NV1"),
    ])
    conn.commit()
    conn.close()


def _chay(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _kho(path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _NgayCoDinh)
    monkeypatch.setattr(rt, "get_sync_meta", lambda _table: (None, None, None))
    return rt.inventory_expiry_report(limit=30)


def test_ton_sku_la_so_sach_da_tru_lo_am_khop_bang_tong(tmp_path, monkeypatch):
    kq = _chay(tmp_path, monkeypatch)
    rui_ro = {r["item_code"]: r for r in kq["supply_risk"]["rows"]}
    # Ban 10.000 vien/thang, ton 1,28 trieu -> cham luan chuyen, phai co dong trong supply_risk.
    assert rui_ro["32200000670"]["stock_qty"] == 1_277_726.0          # truoc: 1.350.134 (bo lo am)
    assert rui_ro["32200000670"]["status"] == "CHAM_LUAN_CHUYEN_DERIVED"
    # Han dung chi tinh lo con hang: 3 lo duong, tong 1.350.134 - lech so sach dung phan am.
    assert sum(b["so_lo"] for b in kq["summary"].values()) == 3
    assert sum(b["tong_so_luong"] for b in kq["summary"].values()) == 1_350_134.0


def test_lo_am_duoc_bao_rieng(tmp_path, monkeypatch):
    kq = _chay(tmp_path, monkeypatch)
    am = kq["lo_am"]
    assert am["so_lo_am"] == 5 and am["so_sku_co_lo_am"] == 2
    assert am["tong_so_luong_am"] == -72_458.0
    thuoc_ho = next(x for x in am["sku_am_nhieu_nhat"] if x["item_code"] == "32200000670")
    assert thuoc_ho["so_lo_am"] == 4 and thuoc_ho["so_luong_am"] == -72_408.0
    assert thuoc_ho["item_name"] == "Thuoc ho vien ngam bo phe Nam Ha"
    assert "SO SACH" in am["giai_thich"]


def test_ton_so_sach_am_thi_so_thang_ton_bang_0_va_co_co(tmp_path, monkeypatch):
    kq = _chay(tmp_path, monkeypatch)
    am = next(r for r in kq["supply_risk"]["rows"] if r["item_code"] == "AM")
    assert am["stock_qty"] == -50.0 and am["ton_so_sach_am"] is True
    assert am["status"] == "CO_NGUY_CO_THIEU_HANG_DERIVED"
    assert am["months_of_cover"] in (0, 0.0)


def test_lo_am_toi_duoc_model(tmp_path, monkeypatch):
    import json
    import nl2sql
    kq = _chay(tmp_path, monkeypatch)
    cau = "Giá trị tồn kho, số tháng tồn, hàng chậm luân chuyển, stock-out và hàng cận date thay đổi thế nào theo tháng?"
    model = json.loads(nl2sql._serialize_payload_for_model("get_inventory_expiry_report", kq, cau))
    assert model["lo_am"]["so_lo_am"] == 5
