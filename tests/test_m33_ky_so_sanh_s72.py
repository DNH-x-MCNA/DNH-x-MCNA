# -*- coding: utf-8 -*-
"""24/09/2026 - UAT M33 "SKU DT giam do it khach/it don/giam luong/giam gia ban" (cham 22/09).

Nguoi cham ghi "mot so SKU khong khop doanh thu, delta so khach va so don". Do tren may 24 ngay
24/09: CUNG ky thi get_customer_product_coverage(mode='product') khop checker S72 tung SKU (ca voi
MB/MB1/MB2 va co/khong dong hang tang). Cho lech la KY: model tu chon lookback_months=3 nen so
01/07-22/09 voi 08/04-30/06, con S72 so thang tron voi thang truoc - ket luan nguoc chieu (Siro ho
bo phe -8,98 ty theo 3 thang nhung +5,74 ty T8 so T7).

Them loi phu: as_of la ngay cuoi thang (thang tron) thi thang truoc bi cat theo so ngay - 30/09 chi
so voi 01-30/08, mat ngay 31. Du lieu gia, khong cham Bravo, khong goi model."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import nl2sql
import report_templates as rt

CAU_M33 = "SKU DT giảm do ít khách/ít đơn/giảm lượng/giảm giá bán"


def test_m33_khong_neu_ky_thi_ep_thang_tron_so_thang_truoc(monkeypatch):
    monkeypatch.setattr(rt, "_latest_complete_revenue_month", lambda: "2026-08")

    args = nl2sql._normalize_tool_input_for_question(
        "get_customer_product_coverage", {"mode": "product", "lookback_months": 3}, CAU_M33)

    assert args["as_of_date"] == "2026-08-31"
    assert args["lookback_months"] == 1
    assert args["mode"] == "product"


def test_m33_nguoi_hoi_neu_ky_thi_giu_tham_so_cua_model(monkeypatch):
    monkeypatch.setattr(rt, "_latest_complete_revenue_month", lambda: "2026-08")
    goc = {"mode": "product", "lookback_months": 3}

    for cau in (CAU_M33 + " trong quý 3", CAU_M33 + " 3 tháng gần nhất", CAU_M33 + " tháng 7/2026",
                CAU_M33 + " tháng này"):
        args = nl2sql._normalize_tool_input_for_question("get_customer_product_coverage", dict(goc), cau)
        assert args.get("lookback_months") == 3 and "as_of_date" not in args, cau


def test_cau_khac_cung_tool_khong_bi_ep_ky(monkeypatch):
    monkeypatch.setattr(rt, "_latest_complete_revenue_month", lambda: "2026-08")

    args = nl2sql._normalize_tool_input_for_question(
        "get_customer_product_coverage", {"mode": "product", "lookback_months": 3},
        "SKU nào tăng độ phủ nhưng giảm doanh thu trên mỗi khách")

    assert args == {"mode": "product", "lookback_months": 3}


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER, employee_code TEXT,
            created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER, employee_code TEXT,
            created_at TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT);
    """)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH1','Khach Mot',1)")
    conn.execute("INSERT INTO brv_sanpham VALUES ('SP1','San pham 1')")
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES (?,'KH1','SP1',?,1,?,?,1,'D1',?,'OTC')",
        [("2026-08-10", 100, 100, "H1", "2026-08-10"), ("2026-08-31", 500, 500, "H2", "2026-08-31"),
         ("2026-09-15", 300, 300, "H3", "2026-09-15")])
    conn.commit()
    conn.close()
    return str(path)


def test_thang_tron_so_voi_tron_thang_truoc_ke_ca_ngay_31(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.customer_product_coverage(as_of_date="2026-09-30", lookback_months=1, mode="product")

    assert kq["previous_period"] == {"from": "2026-08-01", "to": "2026-08-31"}
    assert kq["scope_totals"]["previous"]["revenue"] == 600, "Hoa don 31/08 phai nam trong ky truoc."


def test_giua_thang_van_so_cung_so_ngay_thang_truoc(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.customer_product_coverage(as_of_date="2026-09-15", lookback_months=1, mode="product")

    assert kq["previous_period"] == {"from": "2026-08-01", "to": "2026-08-15"}
