# -*- coding: utf-8 -*-
"""UAT nhat ky 15/09/2026 - cum OTC C-Level (14:23-14:40). Du lieu gia, khong cham Bravo.

- "So luong ton kho bo phe tinh den hom nay": khong goi SQL (tool ton kho bi chan voi tai khoan gioi han
  kenh, va khong co tool tim ton theo ten san pham).
- "Top 10 khach hang no qua han" / "Bo sung nhan vien, quan ly vung tuong ung": top xep theo qua han, can
  kem nguoi phu trach va khach du no lon chua qua han.
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import nl2sql
import report_templates as rt

CAU_TON_KHO = "Số lượng tồn kho bổ phế tính đến hôm nay"


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL, amount REAL,
            is_active INTEGER, fiscal_year INTEGER);
        CREATE TABLE brvsx_tonkhodk (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER, quantity REAL,
            amount REAL, is_active INTEGER, year INTEGER);
        CREATE TABLE vhoadon_otc (doc_date TEXT);
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT,
            customer_name TEXT, sales_channel TEXT, area_code TEXT, balance_end REAL, overdue_1_15 REAL,
            overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL, total_overdue REAL);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER,
            manager_area_code TEXT);
    """)
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-09-15')")
    conn.executemany("INSERT INTO brv_sanpham VALUES (?,?,NULL,?,?)", [
        ("31190000680", "Siro thuốc ho bổ phế Nam Hà", "Lọ", 1),
        ("41220000200", "TPBVSK Viên ngậm Bổ Phế Nam Hà Candy", "Viên", 2),
        ("30000000001", "Paracetamol 500mg", "Viên", 3)])
    conn.executemany("INSERT INTO brv_kho VALUES (?,?,?,?)", [(10, "B02", "K02", "Kho MB"), (11, "B04", "K04", "Kho MN")])
    conn.executemany("INSERT INTO brv_tonkhodk VALUES (?,?,?,0,1,?)", [
        (10, 1, 999.0, 2025),                       # nam cu - khong duoc cong
        (10, 1, 100.0, 2026), (11, 1, 50.0, 2026), (11, 2, 7.0, 2026), (10, 3, 5000.0, 2026)])
    conn.execute("INSERT INTO brvsx_tonkhodk VALUES ('A01', 90, 1, 1234.0, 0, 1, 2026)")
    conn.executemany("INSERT INTO fact_congno_khachhang VALUES ('2026-09-15','2026-09-15T14:00:00',?,?,?,'MN',?,0,0,0,?,?)", [
        ("KH_NO", "Nha thuoc No", "OTC", 1000.0, 500.0, 500.0),
        ("HCM04162", "Duoc Sai Gon", "OTC", 2914915581.0, 0.0, 0.0),
        ("KH_ETC", "Benh vien", "ETC", 9000.0, 9000.0, 9000.0)])
    conn.executemany("INSERT INTO fact_tonghopkhachhang VALUES (?,?,0,0,?,0,?)", [
        ("TDV1", "KH_NO", "2026-09-15", "QLV1"), ("QLV1", "KH_NO", "2026-09-15", "TP1"),
        ("TDV1", "KH_NO", "2026-08-31", "QLV_CU")])
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,0,?,'MN',NULL,NULL,NULL,0,NULL)", [
        ("TDV1", "TDV Mot", "TDV"), ("QLV1", "Quan Ly Mot", "QLV")])
    conn.commit()
    conn.close()
    return str(path)


def _ton(monkeypatch, path, args=None, **scope):
    monkeypatch.setattr(local_warehouse, "DB_PATH", path)
    return rt.call_template("get_inventory_item_stock", args or {"item_search": "bổ phế"}, **scope)


def test_ton_kho_tim_theo_ten_khong_phan_biet_dau_va_chi_nam_moi_nhat(tmp_path, monkeypatch):
    kq = _ton(monkeypatch, _kho(tmp_path), scope_role="c_level", scope_channel="OTC")

    assert kq["ok"] is True, kq
    r = kq["result"]
    theo_ma = {row["item_code"]: row for row in r["rows"]}
    assert set(theo_ma) == {"31190000680", "41220000200"}          # ca "bổ phế" va "Bổ Phế"
    siro = theo_ma["31190000680"]
    assert siro["ton_kho_kinh_doanh"] == 150.0                     # 2026 only, khong gom 999 cua 2025
    assert [(b["branch_code"], b["so_luong"]) for b in siro["ton_kinh_doanh_theo_kho"]] == [("B02", 100.0), ("B04", 50.0)]
    assert siro["ton_kho_san_xuat"] == 1234.0 and siro["don_vi_tinh"] == "Lọ"
    assert theo_ma["41220000200"]["ton_kho_san_xuat"] is None      # khong co dong ton SX, khong ghi 0


def test_ton_kho_gioi_han_vung_an_kho_san_xuat_va_tai_khoan_etc_duoc_xem(tmp_path, monkeypatch):
    path = _ton_path = _kho(tmp_path)
    vung = _ton(monkeypatch, path, scope_role="regional_director", scope_area_code="MB")["result"]
    siro = next(row for row in vung["rows"] if row["item_code"] == "31190000680")
    assert siro["ton_kho_kinh_doanh"] == 100.0 and siro["ton_kho_san_xuat"] is None

    assert _ton(monkeypatch, path, scope_role="regional_director", scope_channel="ETC")["ok"] is True
    khong_co = _ton(monkeypatch, path, {"item_search": "khong ton tai"}, scope_role="c_level")["result"]
    assert khong_co["status"] == "NO_MATCH" and khong_co["matched_items"] == 0


def test_dinh_tuyen_ton_kho_theo_ten_khong_cuop_cau_ton_kho_khac():
    assert nl2sql._required_tool_for_question(CAU_TON_KHO) == "get_inventory_item_stock"
    assert nl2sql._required_tool_for_question("Giá trị tồn kho, số tháng tồn và stock-out theo tháng") == \
        "get_inventory_by_region"
    assert nl2sql._required_tool_for_question("Hàng cận date và chậm luân chuyển nào cần đẩy bán hoặc dừng nhập") == \
        "get_inventory_expiry_report"


def test_cong_no_top_kem_nguoi_phu_trach_va_du_no_lon_chua_qua_han(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.call_template("get_receivables_overview", {}, scope_role="c_level", scope_channel="OTC")

    r = kq["result"]
    assert [c["customer_code"] for c in r["top_overdue_customers"]] == ["KH_NO"]   # ETC bi loc
    top = r["top_overdue_customers"][0]
    assert (top["employee_code"], top["employee_name"]) == ("TDV1", "TDV Mot")
    assert (top["manager_code"], top["manager_name"]) == ("QLV1", "Quan Ly Mot")   # snapshot moi nhat
    assert "NO QUA HAN" in r["ranking_basis"]
    lon = r["du_no_lon_chua_qua_han"]
    assert [c["customer_code"] for c in lon] == ["HCM04162"] and lon[0]["balance_end"] == 2914915581.0
    assert lon[0]["employee_code"] is None and "Khong co phan cong" in lon[0]["nguoi_phu_trach_ghi_chu"]
