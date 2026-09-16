# -*- coding: utf-8 -*-
"""UAT nhat ky 16/09/2026 (chay lai chieu 15/09): C-Level hoi "... doi qlv TM23100148" bi LOI sau 114 giay.

Ba tool danh sach chi loc doi khi TAI KHOAN la QLV; C-Level khong co tham so nao de gioi han mot doi nen
model phai loc tay tren danh sach toan cong ty (523 khach, payload ~105k ky tu) roi cham tran thoi gian.
Them tham so manager_code; pham vi server cua tai khoan QLV van thang tham so do. Du lieu gia.
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT, year_sale_target REAL,
            amount_cus REAL, is_ro INTEGER, is_ac INTEGER, max_customer_ord_amount REAL, emp_dms_code TEXT,
            nc_save_date TEXT, ro_month REAL, ro_last_date TEXT, reorder_start_date TEXT, reorder_save_date TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT, position_code TEXT,
            area_code TEXT, manager_code TEXT, save_date TEXT, reorder_cus_quantity REAL, reorder_cus_target REAL,
            reorder_percent REAL, target_product_amount REAL, target_product_percent REAL, tpr_point REAL,
            tpr_target_amount REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE vhoadon_otc (doc_date TEXT);
    """)
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-09-15')")
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,0,?,'MN',NULL,NULL,NULL,0,NULL)", [
        ("TDV_A", "TDV Doi A", "TDV"), ("TDV_B", "TDV Doi B", "TDV"),
        ("QLV_A", "Quan Ly A", "QLV"), ("QLV_B", "Quan Ly B", "QLV")])
    conn.executemany("INSERT INTO dms_khachhang VALUES (?,?,1)", [
        ("KH_A1", "Khach doi A"), ("KH_A2", "Khach doi A 2"), ("KH_B1", "Khach doi B")])

    def fact(emp, cus, mgr, nc="0", ro="0"):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,100,0,'2026-09-15',?,?,0,100,?,0,0,?,"
                     "'2026-09-05',3,'2026-08-01','2026-06-01',NULL)", (emp, cus, nc, mgr, ro, emp))

    fact("TDV_A", "KH_A1", "QLV_A", nc="1", ro="1")   # khach moi VA da tai don -> chi vao danh sach khach moi
    fact("TDV_A", "KH_A2", "QLV_A")
    fact("TDV_B", "KH_B1", "QLV_B", nc="1")
    conn.executemany("INSERT INTO fact_thongketinhluong VALUES (?,?,?,'MN',?, '2026-09-15',0,0,0,?,0.5,1,?)", [
        ("QLV_A", "Quan Ly A", "QLV", "TP", 50.0, 100.0),
        ("QLV_B", "Quan Ly B", "QLV", "TP", 30.0, 100.0),
        ("TDV_A", "TDV Doi A", "TDV", "QLV_A", 20.0, 40.0)])
    conn.commit()
    conn.close()
    return str(path)


def _goi(monkeypatch, path, ten, args, **scope):
    monkeypatch.setattr(local_warehouse, "DB_PATH", path)
    return rt.call_template(ten, args, question="doi qlv", **scope)["result"]


def test_c_level_loc_dung_mot_doi_bang_manager_code(tmp_path, monkeypatch):
    path = _kho(tmp_path)

    moi = _goi(monkeypatch, path, "get_new_customer_list",
               {"year_month": "2026-09", "manager_code": "QLV_A"}, scope_role="c_level")
    tai_don = _goi(monkeypatch, path, "get_reorder_pending_customers",
                   {"year_month": "2026-09", "manager_code": "QLV_A"}, scope_role="c_level")
    trong_tam = _goi(monkeypatch, path, "get_focus_product_kpi",
                     {"year_month": "2026-09", "manager_code": "QLV_A"}, scope_role="c_level")

    assert [r["customer_code"] for r in moi["rows"]] == ["KH_A1"]
    assert [r["customer_code"] for r in tai_don["rows"]] == ["KH_A2"]
    assert [q["employee_code"] for q in trong_tam["quan_ly_vung"]] == ["QLV_A"]
    assert [m["employee_code"] for m in trong_tam["thanh_vien_doi"]] == ["TDV_A"]
    assert trong_tam["ma_doi"] == "QLV_A"


def test_khong_truyen_manager_code_thi_van_ra_toan_cong_ty(tmp_path, monkeypatch):
    moi = _goi(monkeypatch, _kho(tmp_path), "get_new_customer_list", {"year_month": "2026-09"},
               scope_role="c_level")

    assert {r["customer_code"] for r in moi["rows"]} == {"KH_A1", "KH_B1"}


def test_tai_khoan_qlv_khong_the_xem_doi_khac_qua_tham_so(tmp_path, monkeypatch):
    path = _kho(tmp_path)

    moi = _goi(monkeypatch, path, "get_new_customer_list",
               {"year_month": "2026-09", "manager_code": "QLV_B"},
               scope_role="qlv", scope_area_code="MN", scope_employee_code="QLV_A")
    trong_tam = _goi(monkeypatch, path, "get_focus_product_kpi",
                     {"year_month": "2026-09", "manager_code": "QLV_B"},
                     scope_role="qlv", scope_area_code="MN", scope_employee_code="QLV_A")

    assert [r["customer_code"] for r in moi["rows"]] == ["KH_A1"]     # khong thay KH_B1 cua doi khac
    assert [q["employee_code"] for q in trong_tam["quan_ly_vung"]] == ["QLV_A"]
