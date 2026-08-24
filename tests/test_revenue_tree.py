# -*- coding: utf-8 -*-
"""Kiem chung report_templates.revenue_tree() - tool cuoi cung chua co test rieng (20/08/2026).

Khoa lai 4 co che phong ve, moi cai deu tu mot su co THAT:
  1. Danh sach QLV duoi TP lay tu _rollup_tier_codes() - CUNG nguon voi kpi_ranking(), khong loc
     position_code/is_duplicate (27/07/2026: loc lam cay Mien Nam ra 3,50 ty trong khi tong vung
     that la 6,25 ty - thieu Kenh MT 2,73 ty + Cho si 0,15 ty).
  2. Don vi ao (Kenh MT/Cho si) duoc danh dau la_nhom_kenh va KHONG di tim doi TDV.
  3. QLV TRUNG TEN voi chinh TP quan ly vung do -> canh bao nghi van trung ban ghi (10/08/2026).
  4. scope_employee_code ep chi tra ve DUNG 1 QLV (du lieu hieu suat ca nhan dong nghiep).
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt

SAVE_DATE = "2026-07-31"


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
        """
    )

    def nv(code, name, dup, pos, area):
        conn.execute("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,NULL,NULL,0,NULL)",
                    (code, name, dup, pos, area, code))

    def fact(code, cus, sales, target, manager=None):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,0,?)",
                    (code, cus, sales, target, SAVE_DATE, manager))

    # TP vung MN
    nv("TP_MN", "Truong phong MN", 0, "TP", "MN")
    # QLV that duoi TP_MN, co 1 TDV
    nv("QLV_MN", "Quan ly MN", 0, "QLV", "MN")
    fact("QLV_MN", "KH1", 500_000, 1_000_000)
    nv("TDV_MN", "Nhan vien MN", 0, "TDV", "MN")
    fact("TDV_MN", "KH2", 300_000, 600_000, "QLV_MN")
    # 'Kenh MT': don vi AO (is_duplicate=1, khong nam trong danh sach mien tru) - PHAI vao cay
    # (neu loc is_duplicate se mat doanh thu that) nhung KHONG di tim doi TDV.
    nv("MN1", "Kênh MT", 1, "QLV", "MN")
    fact("MN1", "KH3", 900_000, 1_000_000)
    # Cap duoi cua MN1 mang chuc danh 'TK' - de xac nhan _rollup_tier_codes khong loc position_code.
    nv("TK1", "Truong kenh", 0, "TK", "MN")
    fact("TK1", "KH4", 100_000, 200_000, "MN1")

    # TP vung MB - co QLV TRUNG TEN voi chinh TP (ca that da ghi nhan 10/08/2026).
    nv("TP_MB", "Nguyen Thi Thanh Thuy", 0, "TP", "MB")
    nv("MBKV12", "Nguyen Thi Thanh Thuy", 1, "QLV", "MB")  # trong _KNOWN_MISFLAGGED -> nguoi THAT
    fact("MBKV12", "KH5", 400_000, 800_000)
    nv("TDV_MB", "Nhan vien MB", 0, "TDV", "MB")
    fact("TDV_MB", "KH6", 200_000, 400_000, "MBKV12")
    conn.commit()
    conn.close()


def test_don_vi_ao_duoc_danh_dau_va_khong_di_tim_doi(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.revenue_tree(as_of_date=SAVE_DATE, area_code="MN")
    tp = next(t for t in result["tree"] if t["employee_code"] == "TP_MN")
    by_code = {q["employee_code"]: q for q in tp["qlv"]}

    assert by_code["MN1"]["la_nhom_kenh"] is True
    assert by_code["MN1"]["tdv_count"] == 0, "don vi ao KHONG duoc di tim doi TDV"
    assert "ghi_chu" in by_code["MN1"]
    assert by_code["QLV_MN"]["la_nhom_kenh"] is False
    assert by_code["QLV_MN"]["tdv_count"] == 1


def test_khong_loc_is_duplicate_nen_khong_bay_hoi_doanh_thu_vung(tmp_path, monkeypatch):
    """27/07/2026: loc is_duplicate lam cay MN thieu han Kenh MT/Cho si."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.revenue_tree(as_of_date=SAVE_DATE, area_code="MN")
    tp = next(t for t in result["tree"] if t["employee_code"] == "TP_MN")
    tong_qlv = sum(q["sales"] for q in tp["qlv"])

    # QLV_MN 500.000 + MN1 900.000 = 1.400.000. Neu loc is_duplicate se chi con 500.000.
    assert tong_qlv == 1_400_000


def test_qlv_trung_ten_voi_TP_duoc_canh_bao(tmp_path, monkeypatch):
    """10/08/2026: MBKV12 trung ten voi chinh TP quan ly vung MB - phai canh bao nghi van trung
    ban ghi, khong trinh bay nhu QLV thong thuong."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.revenue_tree(as_of_date=SAVE_DATE, area_code="MB")
    tp = next(t for t in result["tree"] if t["employee_code"] == "TP_MB")
    qlv = next(q for q in tp["qlv"] if q["employee_code"] == "MBKV12")

    assert "ghi_chu" in qlv
    assert "TRUNG TEN" in qlv["ghi_chu"]
    # MBKV12 nam trong _KNOWN_MISFLAGGED_DUPLICATE_CODES -> la NGUOI THAT, khong phai don vi ao.
    assert qlv["la_nhom_kenh"] is False
    assert qlv["tdv_count"] == 1


def test_scope_employee_code_chi_tra_ve_dung_1_qlv(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.revenue_tree(as_of_date=SAVE_DATE, scope_employee_code="QLV_MN")
    all_qlv = [q["employee_code"] for t in result["tree"] for q in t["qlv"]]

    assert all_qlv == ["QLV_MN"], f"lo QLV khac: {all_qlv}"
    # 24/08/2026: BUG THAT da xac nhan tren du lieu that (QLV MBKV1 vung MB nhan ve ca TP Mien Nam/
    # Mien Trung du qlv_count=0) - vong lap "for tp in tp_rows" truoc day chay qua TAT CA TP toan
    # cong ty roi moi loc qlv_rows BEN TRONG, tao node RONG cho TP khong lien quan thay vi loai han,
    # lo TEN + MA nhan vien cua Truong phong VUNG KHAC. Du lieu test co 2 vung (MN, MB) - PHAI CHI
    # con dung 1 node TP (cua vung MN, noi QLV_MN thuoc ve), khong duoc thay ca TP_MB.
    assert len(result["tree"]) == 1, f"lo them TP khong lien quan: {[t['employee_code'] for t in result['tree']]}"
    assert result["tree"][0]["employee_code"] == "TP_MN"


def test_cap_TP_khong_co_target_rieng_van_tra_ve_0_khong_bao_loi(tmp_path, monkeypatch):
    """Cap TP LUON co sales/target=0 (Bravo khong tracking target ca nhan cho TP) - day la gioi han
    du lieu da biet, ham van phai chay binh thuong, khong duoc coi la loi."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.revenue_tree(as_of_date=SAVE_DATE, area_code="MN")
    tp = next(t for t in result["tree"] if t["employee_code"] == "TP_MN")

    assert tp["sales"] == 0.0 and tp["target"] == 0.0
    assert tp["qlv_count"] == 2  # van liet ke du QLV ben duoi
