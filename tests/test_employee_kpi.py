# -*- coding: utf-8 -*-
"""Kiem chung report_templates.employee_kpi() - tool KPI dung nhieu nhat, CHUA TUNG co test rieng
cho logic 3 moc (DAT CHI TIEU 100% / DAT KPI 80% / TOI MUC THUONG 65-70% theo vai tro) truoc
19/08/2026 - day la 3 khai niem da GOP NHAM nhieu lan that trong lich su du an (xem rule 11 trong
schema_context.py), nen la diem rui ro cao dang duoc khoa lai bang test."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dim_chucvu (position_code TEXT, description TEXT);
        """
    )
    conn.execute("INSERT INTO dim_chucvu VALUES ('TDV','Trinh duoc vien')")
    conn.execute("INSERT INTO dim_chucvu VALUES ('QLV','Quan ly vung')")
    # A (TDV): 65% - dung nguong toi thieu cong thuong TDV, chua dat KPI (80), chua dat chi tieu (100).
    conn.execute("INSERT INTO dim_nhanvien VALUES ('A','Nhan vien A',0,'TDV','MB','A')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('A','KH1',650000,1000000,'2026-07-31',0,NULL)")
    # B (QLV): 69% - DUOI nguong cong thuong QLV (70), du hon nguong TDV (65) - phai phan biet theo vai tro.
    conn.execute("INSERT INTO dim_nhanvien VALUES ('B','Quan ly B',0,'QLV','MB','B')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('B','KH2',690000,1000000,'2026-07-31',0,NULL)")
    # C (TDV): 105% - vuot ca 3 moc.
    conn.execute("INSERT INTO dim_nhanvien VALUES ('C','Nhan vien C',0,'TDV','MB','C')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('C','KH3',1050000,1000000,'2026-07-31',0,NULL)")
    # D (TDV): co doanh so nhung KHONG co target (0) - phai bi loai khoi tinh toan ty le (chia cho 0).
    conn.execute("INSERT INTO dim_nhanvien VALUES ('D','Nhan vien D',0,'TDV','MB','D')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('D','KH4',300000,0,'2026-07-31',0,NULL)")
    conn.commit()
    conn.close()


def test_ba_moc_doc_lap_khong_gop_nham(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.employee_kpi(as_of_date="2026-07-31", limit=10)

    assert result["total_employees"] == 3  # D bi loai vi target=0
    # DAT CHI TIEU (100%): chi C.
    assert result["count_full_target"] == 1
    # DAT KPI (80%, chung moi vai tro): chi C.
    assert result["count_kpi_achieved"] == 1
    # TOI MUC THUONG (65% TDV / 70% QLV): A (65>=65) va C (105>=65) dat; B (69<70) CHUA dat du 69>65.
    assert result["count_above_target"] == 2
    assert result["count_below_target"] == 1


def test_nguong_thuong_phan_biet_dung_theo_vai_tro(tmp_path, monkeypatch):
    """Diem mau chot: B (QLV, 69%) va A (TDV, 65%) - neu dung chung 1 nguong phang se sai it nhat
    1 trong 2 nguoi. Phai dung DUNG nguong theo TUNG DONG (vai tro cua chinh nguoi do)."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.employee_kpi(as_of_date="2026-07-31", limit=10)["rows"]
    a = next(r for r in rows if r["employee_code"] == "A")
    b = next(r for r in rows if r["employee_code"] == "B")
    c = next(r for r in rows if r["employee_code"] == "C")

    assert a["threshold"] == 65 and a["pct"] == 65.0
    assert b["threshold"] == 70 and round(b["pct"], 1) == 69.0
    assert c["threshold"] == 65


def test_filter_below_target_xep_te_nhat_truoc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.employee_kpi(as_of_date="2026-07-31", limit=10, filter="below_target")

    # Chi B duoi nguong cong thuong (70) - A va C da dat/vuot nguong cua rieng ho.
    codes = [r["employee_code"] for r in result["rows"]]
    assert codes == ["B"]


def test_filter_above_target_xep_tot_nhat_truoc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.employee_kpi(as_of_date="2026-07-31", limit=10, filter="above_target")

    codes = [r["employee_code"] for r in result["rows"]]
    assert codes == ["C", "A"]  # C (105%) truoc A (65%) - tot nhat truoc


def test_position_code_loc_dung(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.employee_kpi(as_of_date="2026-07-31", limit=10, position_code="QLV")

    assert result["total_employees"] == 1
    assert result["rows"][0]["employee_code"] == "B"
