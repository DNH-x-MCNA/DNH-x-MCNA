# -*- coding: utf-8 -*-
"""UAT nhat ky 15/09/2026 - cum khach hang/KPI (13:59-14:11). Du lieu gia, khong cham Bravo.

- "danh sach khach hang moi, ngay ghi nhan va doanh so phat sinh thang nay": thieu khach, ngay sai.
- "Danh sach khach hang phat sinh 3 thang nhung chua dat kpi tai don": chi mo ta chung.
- "Doanh so san pham trong tam theo quan ly vung": thieu KPI san pham trong tam.
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

CAU_KHACH_MOI = "danh sách khách hàng mới, ngày ghi nhận và doanh số phát sinh tháng này"
CAU_TAI_DON = "Danh sách khách hàng phát sinh 3 tháng nhưng chưa đạt kpi tái đơn của trình dược viên"
CAU_TRONG_TAM = "Doanh số sản phẩm trọng tâm theo quản lý vùng"


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT,
            year_sale_target REAL, amount_cus REAL, is_ro INTEGER, is_ac INTEGER,
            max_customer_ord_amount REAL, emp_dms_code TEXT, nc_save_date TEXT, ro_month REAL,
            ro_last_date TEXT, reorder_start_date TEXT, reorder_save_date TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT, position_code TEXT,
            area_code TEXT, manager_code TEXT, save_date TEXT, reorder_cus_quantity REAL,
            reorder_cus_target REAL, reorder_percent REAL, target_product_amount REAL,
            target_product_percent REAL, tpr_point REAL, tpr_target_amount REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER,
            manager_area_code TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE vhoadon_otc (doc_date TEXT);
    """)
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-07-31')")
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,0,?,?,NULL,NULL,NULL,0,NULL)", [
        ("TDV_MB", "TDV Bac", "TDV", "MB"), ("TDV_MT", "TDV Trung", "TDV", "MT"),
        ("TDV_DOI2", "TDV Doi Hai", "TDV", "MB"),
        ("QLV1", "Quan Ly Mot", "QLV", "MB"), ("QLV2", "Quan Ly Hai", "QLV", "MT"),
        ("QLV3", "Quan Ly Ba", "QLV", "MB")])
    conn.executemany("INSERT INTO dms_khachhang VALUES (?,?,1)", [
        ("KH_MB", "Nha thuoc Bac"), ("KH_MT", "Nha thuoc Trung"), ("KH_CU", "Khach Cu")])

    def fact(emp, cus, amount, save, mgr, nc="0", ro="0", nc_date=None, ro_month=3.0, ro_last=None):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,0,?,?,?,0,?,?,0,0,?,?,?,?,?,NULL)",
                     (emp, cus, amount, save, nc, mgr, amount, ro, emp, nc_date, ro_month, ro_last, "2026-05-01"))

    # Mien Bac chot snapshot 27/07, Mien Trung 28/07: MAX(save_date) chung se mat KH_MB.
    fact("TDV_MB", "KH_MB", 500.0, "2026-07-27", "QLV1", nc="1", nc_date="2026-07-12")
    fact("QLV1", "KH_MB", 500.0, "2026-07-27", "TP1", nc="1", nc_date="2026-07-12")   # dong rollup QLV
    fact("TDV_MT", "KH_MT", 300.0, "2026-07-28", "QLV2", nc="1", nc_date="2026-07-20")
    fact("TDV_MB", "KH_CU", 100.0, "2026-07-27", "QLV1", ro="0", ro_last="2026-06-05")
    fact("TDV_MB", "KH_RO", 100.0, "2026-07-27", "QLV1", ro="1", ro_last="2026-07-02")
    # Dong rollup QLV mang IsRO=0 cho khach TDV da tai don (do that tren Bravo 15/09) - khong duoc lot.
    fact("QLV1", "KH_RO", 100.0, "2026-07-27", "TP1", ro="0")
    fact("TDV_DOI2", "KH_DOI2", 100.0, "2026-07-27", "QLV3", ro="0", ro_last="2026-05-20")
    # TDV moi: dong TDV IsNC=0, dong rollup QLV IsNC=1 kem NCSaveDate -> van la khach moi, gan cho TDV.
    fact("TDV_MB", "KH_MOI_TDV_MOI", 200.0, "2026-07-27", "QLV1", nc="0")
    fact("QLV1", "KH_MOI_TDV_MOI", 200.0, "2026-07-27", "TP1", nc="1", nc_date="2026-07-15")
    # Snapshot cu hon trong thang cua TDV_MB khong duoc tinh.
    fact("TDV_MB", "KH_CU_SNAP", 999.0, "2026-07-10", "QLV1", nc="1", nc_date="2026-07-05")

    conn.executemany("INSERT INTO fact_thongketinhluong VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("QLV1", "Quan Ly Mot", "QLV", "MB", "TP1", "2026-07-31", 0, 0, 0, 80.0, 0.8, 1.0, 100.0),
        ("QLV2", "Quan Ly Hai", "QLV", "MT", "TP2", "2026-07-31", 0, 0, 0, 30.0, 0.3, 0.0, 100.0),
        ("TDV_MB", "TDV Bac", "TDV", "MB", "QLV1", "2026-07-31", 5, 10, 0.5, 40.0, 0.4, 0.0, 50.0),
        ("TP1", "Truong Phong", "TP", "MB", None, "2026-07-31", 0, 0, 0, 110.0, 0.9, 1.0, 120.0),
    ])
    conn.commit()
    conn.close()
    return str(path)


def _goi(monkeypatch, path, ten, args=None, **scope):
    monkeypatch.setattr(local_warehouse, "DB_PATH", path)
    return rt.call_template(ten, args or {"year_month": "2026-07"}, **scope)


def test_khach_moi_lay_snapshot_tung_nhan_vien_va_ngay_ghi_nhan_ncsavedate(tmp_path, monkeypatch):
    kq = _goi(monkeypatch, _kho(tmp_path), "get_new_customer_list", scope_role="c_level")

    r = kq["result"]
    assert r["total_new_customers"] == 3                    # KH_MB (27/07), KH_MT (28/07), KH_MOI_TDV_MOI
    theo_kh = {row["customer_code"]: row for row in r["rows"]}
    assert set(theo_kh) == {"KH_MB", "KH_MT", "KH_MOI_TDV_MOI"}   # KH_CU_SNAP o snapshot cu bi loai
    moi = theo_kh["KH_MOI_TDV_MOI"]
    assert (moi["employee_code"], moi["ngay_ghi_nhan"]) == ("TDV_MB", "2026-07-15")
    assert theo_kh["KH_MB"]["ngay_ghi_nhan"] == "2026-07-12"
    assert theo_kh["KH_MB"]["employee_code"] == "TDV_MB"    # dong rollup QLV khong nhan doi
    assert theo_kh["KH_MB"]["employee_name"] == "TDV Bac"
    assert theo_kh["KH_MB"]["manager_name"] == "Quan Ly Mot"
    assert theo_kh["KH_MB"]["customer_name"] == "Nha thuoc Bac"
    assert r["tong_doanh_so_thang"] == 1000.0


def test_khach_moi_qlv_chi_thay_doi_minh_va_etc_khong_ap_dung(tmp_path, monkeypatch):
    path = _kho(tmp_path)
    kq = _goi(monkeypatch, path, "get_new_customer_list", scope_role="qlv",
              scope_area_code="MB", scope_employee_code="QLV1")
    assert {row["customer_code"] for row in kq["result"]["rows"]} == {"KH_MB", "KH_MOI_TDV_MOI"}   # khong KH_MT
    assert kq["result"]["pham_vi_du_lieu"]["loai"] == "DOI_CUA_QLV"

    etc = _goi(monkeypatch, path, "get_new_customer_list", scope_role="regional_director", scope_channel="ETC")
    assert etc["result"]["not_applicable"] is True


def test_khach_chua_tai_don_tra_danh_sach_va_kpi_tung_tdv(tmp_path, monkeypatch):
    kq = _goi(monkeypatch, _kho(tmp_path), "get_reorder_pending_customers", scope_role="qlv",
              scope_area_code="MB", scope_employee_code="QLV1")

    r = kq["result"]
    ma = [row["customer_code"] for row in r["rows"]]
    assert "KH_CU" in ma and "KH_RO" not in ma and "KH_DOI2" not in ma
    cu = next(row for row in r["rows"] if row["customer_code"] == "KH_CU")
    assert cu["ro_last_date_bravo"] == "2026-06-05" and cu["so_thang_cua_so"] == 3
    assert all(row["employee_code"] != "QLV1" for row in r["rows"])
    kpi = {k["employee_code"]: k for k in r["kpi_tai_don_theo_nhan_vien"]}
    assert kpi["TDV_MB"]["khach_da_tai_don"] == 5 and kpi["TDV_MB"]["chi_tieu_khach_tai_don"] == 10
    # ReOrderCusTarget cua Bravo la he so (1.0), chi tieu so khach suy tu so tai don / ty le dat.
    assert kpi["TDV_MB"]["ty_le_dat_kpi_tai_don_pct"] == 50.0


def test_kpi_trong_tam_theo_qlv_chi_tang_qlv_kem_doi_khi_la_qlv(tmp_path, monkeypatch):
    path = _kho(tmp_path)
    toan_cty = _goi(monkeypatch, path, "get_focus_product_kpi", scope_role="c_level")["result"]
    assert [q["employee_code"] for q in toan_cty["quan_ly_vung"]] == ["QLV2", "QLV1"]   # % thap truoc
    qlv1 = next(q for q in toan_cty["quan_ly_vung"] if q["employee_code"] == "QLV1")
    assert qlv1["doanh_so_trong_tam"] == 80.0 and qlv1["chi_tieu_trong_tam"] == 100.0
    assert qlv1["pct_dat"] == 80.0
    assert "thanh_vien_doi" not in toan_cty

    doi = _goi(monkeypatch, path, "get_focus_product_kpi", scope_role="qlv",
               scope_area_code="MB", scope_employee_code="QLV1")["result"]
    assert [q["employee_code"] for q in doi["quan_ly_vung"]] == ["QLV1"]
    assert [m["employee_code"] for m in doi["thanh_vien_doi"]] == ["TDV_MB"]


def test_dinh_tuyen_ba_cau_uat_khong_cuop_v22_v30():
    assert nl2sql._required_tool_for_question(CAU_KHACH_MOI) == "get_new_customer_list"
    assert nl2sql._required_tool_for_question(CAU_TAI_DON) == "get_reorder_pending_customers"
    assert nl2sql._required_tool_for_question(CAU_TRONG_TAM) == "get_focus_product_kpi"
    assert nl2sql._required_tool_for_question(
        "Khách mới tháng này là ai; đã có đơn lặp lại chưa và TDV nào phụ trách?") == "get_customer_movement"
    assert nl2sql._required_tool_for_question(
        "SKU trọng tâm đạt %target theo từng TDV/khách; khoảng thiếu bao nhiêu") == "get_customer_product_coverage"


def test_ba_tool_moi_co_nguon_du_lieu():
    from backend.data_freshness import _TEMPLATE_SOURCES
    for ten in ("get_new_customer_list", "get_reorder_pending_customers", "get_focus_product_kpi"):
        assert _TEMPLATE_SOURCES[ten]
