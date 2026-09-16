# -*- coding: utf-8 -*-
"""Tra cuu theo TEN thay vi bat buoc co MA (yeu cau anh Dang 16/09/2026).

Nguoi dung nho ten nhan vien/khach hang chu khong nho ma, nhung cac tool KPI ngay va thuong/luong
truoc day chi nhan employee_code nen bot tra loi "can ma nhan vien". Test khoa lai:
  - ten duy nhat -> tu quy ra ma, chay binh thuong;
  - ten trung nhieu nguoi -> tra danh sach ung vien de hoi lai, KHONG duoc tu chon;
  - chuoi la MA that -> khong bi doan mo sang tim ten;
  - khach hang cung ma nhung hai danh muc ghi ten khac nhau (Bac Giang / Bac Ninh sau sap nhap
    don vi hanh chinh) KHONG duoc dien giai thanh hai khach khac nhau.
Du lieu gia, khong cham Bravo.
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path, nhan_vien=(), nhan_vien_sx=()):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, employee_code TEXT, amount9 REAL);
        CREATE TABLE vhoadon_etc (doc_date TEXT, employee_code TEXT, amount9 REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, month_sale_target REAL, save_date TEXT);
    """)
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?)", nhan_vien)
    conn.executemany("INSERT INTO dmssx_nhanvien VALUES (?,?,?)", nhan_vien_sx)
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('NV01', 1000000, '2026-01-15')")
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-01-05', 'dms01', 30000)")
    conn.commit()
    conn.close()
    return str(path)


def test_ten_duy_nhat_co_dau_van_ra_dung_ma(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(
        tmp_path, nhan_vien=[("NV01", "Nguyễn Văn Danh", 0, "TDV", "MB", "dms01")]))

    # Nguoi dung go khong dau; SQLite LIKE khong bo dau nen phai loc trong Python.
    ident = rt._resolve_employee_identity("nguyen van danh")

    assert ident["code"] == "NV01"
    assert ident["dmsid"] == "dms01"
    assert ident["resolved_from_name"] == "nguyen van danh"


def test_ten_trung_nhieu_nguoi_thi_hoi_lai_chu_khong_doan(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, nhan_vien=[
        ("NV01", "Nguyễn Văn Danh", 0, "TDV", "MB", "dms01"),
        ("NV02", "Nguyễn Văn Danh", 0, "TDV", "MN", "dms02")]))

    ident = rt._resolve_employee_identity("Nguyễn Văn Danh")
    kq = rt.employee_daily_kpi(employee_code="Nguyễn Văn Danh", year_month="2026-01")

    assert {u["employee_code"] for u in ident["name_candidates"]} == {"NV01", "NV02"}
    assert "error" in kq
    assert {u["employee_code"] for u in kq["employee_candidates"]} == {"NV01", "NV02"}
    assert "khong tu chon mot nguoi" in kq["answer_rule"].lower()


def test_kpi_ngay_goi_bang_ten_chay_het_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(
        tmp_path, nhan_vien=[("NV01", "Nguyễn Văn Danh", 0, "TDV", "MB", "dms01")]))

    kq = rt.employee_daily_kpi(employee_code="Nguyễn Văn Danh", year_month="2026-01")

    assert "error" not in kq
    assert kq["resolved_employee_code"] == "NV01"
    assert kq["month_total_sales"] == 30000


def test_nhan_vien_etc_chi_co_trong_bang_sx_cung_tra_duoc_theo_ten(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(
        tmp_path, nhan_vien_sx=[("DNH00087", "E01", "Trần Thị Bình")]))

    ident = rt._resolve_employee_identity("tran thi binh")

    assert ident["code"] == "DNH00087" and ident["dmsid"] == "E01"


def test_ma_that_khong_bi_doan_thanh_ten(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(
        tmp_path, nhan_vien=[("NV01", "Nguyễn Văn Danh", 0, "TDV", "MB", "dms01")]))

    ident = rt._resolve_employee_identity("TM25010199")

    assert ident["code"] == "TM25010199" and ident["name"] is None
    assert "name_candidates" not in ident and "resolved_from_name" not in ident


def _kho_khach(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, amount9 REAL, stt TEXT,
            city_id INTEGER, employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, amount9 REAL, stt TEXT,
            city_id INTEGER, employee_code TEXT, created_at TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            kenh_bh TEXT);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dim_chucvu (position_code TEXT, description TEXT);
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT,
            customer_name TEXT, sales_channel TEXT, area_code TEXT, balance_end REAL,
            overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL,
            total_overdue REAL);
    """)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Bắc Ninh','MB')")
    conn.execute("INSERT INTO dms_khachhang VALUES "
                 "('BGI00699','Bệnh viện đa khoa Tỉnh Bắc Giang',1,1,NULL,'GT')")
    conn.execute("INSERT INTO dmssx_khachhang VALUES "
                 "('BGI00699','Bệnh viện đa khoa Bắc Ninh số 1',1,2,'GT')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                 "('2026-06-12','BGI00699',42000000,'HD1',1,'NV1','2026-06-12')")
    conn.commit()
    conn.close()
    return str(path)


def test_ten_tinh_cu_va_moi_la_mot_khach_khong_duoc_noi_la_khach_khac(tmp_path, monkeypatch):
    """Bac Giang da sap nhap vao Bac Ninh - danh muc giu ten cu, van la MOT benh vien."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_khach(tmp_path))

    kq = rt.customer_detail(customer_code="BGI00699", date_from="2026-01-01", date_to="2026-09-16")

    canh_bao = kq["catalog_identity_warning"]
    assert canh_bao["selected_channel"] == "ETC"
    assert "KHONG PHAI hai khach" in canh_bao["answer_rule"]
    assert "sap nhap" in kq["identity_check"].lower()
    assert "khach khac" not in canh_bao["answer_rule"].replace("KHONG PHAI hai khach", "")
