# -*- coding: utf-8 -*-
"""Kiem chung report_templates.kpi_ranking() - CHUA co test rieng truoc 20/08/2026, du day la ham
da vai loi THAT tot kem nhat trong lich su du an (27/07/2026: gop tang la thay vi tang rollup lam
Mien Nam thieu 7,93 ty mau so -> nhay tu hang 2 len hang 1 SAI CA con so lan THU HANG).

Khoa lai dung 4 co che phong ve da co trong code, moi cai deu tung la bug that:
  1. group_by='region' gop theo TANG ROLLUP (manager_code), khong phai tang la.
  2. Target gop ve 1 dong/nguoi TRUOC khi SUM theo vung (neu SUM thang tren fact se dem target
     trung 1 lan/khach hang).
  3. KHONG loc position_code/is_duplicate khi xac dinh tang rollup (ca 2 deu sai nhan tren Bravo).
  4. Ban ghi don vi ao (Kenh MT/Cho si) duoc danh dau la_nhom_kenh de khong bi goi nham la ca nhan.
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
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dim_targetvungmien (area_code TEXT, channel_code TEXT, amount REAL, doc_date TEXT);
        """
    )
    # QLV1 (MB): quan ly TDV1+TDV2. Rollup cua QLV da bao gom san doi (Bravo tu tong hop).
    #   -> 2 dong khach hang, CUNG month_sale_target=1.000.000 (target lap lai moi dong khach).
    #   Neu SUM(target) thang se ra 2.000.000 = THOI PHONG GAP DOI - day la bug that da vai.
    conn.execute("INSERT INTO dim_nhanvien VALUES ('QLV1','Quan ly Mot',0,'QLV','MB','QLV1')")
    conn.executemany(
        "INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,0,?)",
        [("QLV1", "KH1", 400000, 1000000, SAVE_DATE, None),
         ("QLV1", "KH2", 400000, 1000000, SAVE_DATE, None)],
    )
    # 2 TDV duoi quyen QLV1 - la TANG LA, KHONG duoc cong them vao tong vung (se gap doi).
    for code in ("TDV1", "TDV2"):
        conn.execute("INSERT INTO dim_nhanvien VALUES (?,?,0,'TDV','MB',?)", (code, f"NV {code}", code))
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,0,?)",
                    (code, "KH9", 150000, 400000, SAVE_DATE, "QLV1"))
    # MN1 'Kenh MT': don vi AO (is_duplicate=1, KHONG nam trong _KNOWN_MISFLAGGED_DUPLICATE_CODES)
    # -> phai vao bang xep hang (neu loc is_duplicate se lam bay hoi doanh thu that) nhung phai
    # duoc danh dau la_nhom_kenh=True.
    conn.execute("INSERT INTO dim_nhanvien VALUES ('MN1','Kênh MT',1,'QLV','MN','ASM01')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('MN1','KH3',900000,1000000,?,0,NULL)",
                (SAVE_DATE,))
    # TK1: cap duoi cua MN1, mang chuc danh 'TK' (KHONG phai 'QLV') - neu loc position_code='QLV'
    # thi MN1 van vao duoc nhung TK1 se khong duoc nhan la tang la -> day la ly do _rollup_tier_codes
    # CO Y khong loc position_code.
    conn.execute("INSERT INTO dim_nhanvien VALUES ('TK1','Truong kenh',0,'TK','MN','TK1')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('TK1','KH4',100000,200000,?,0,'MN1')",
                (SAVE_DATE,))
    conn.commit()
    conn.close()


def test_region_gop_theo_tang_rollup_khong_cong_them_tang_la(tmp_path, monkeypatch):
    """MB chi duoc tinh QLV1 (800.000/1.000.000 = 80%), KHONG cong them TDV1+TDV2 - rollup cua QLV
    da bao gom doi ho san roi. Cong ca 2 tang = gap doi (bug 23/07/2026)."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.kpi_ranking(group_by="region", as_of_date=SAVE_DATE)
    by_area = {r["area_code"]: r for r in rows}

    assert by_area["MB"]["sales"] == 800_000
    # Diem mau chot: target = 1.000.000 (MAX theo tung nguoi roi moi SUM), KHONG phai 2.000.000
    # (SUM thang tren 2 dong khach hang) va cung KHONG phai 1.800.000 (cong them 2 TDV).
    assert by_area["MB"]["target"] == 1_000_000
    assert by_area["MB"]["pct"] == 80.0


def test_region_khong_loc_is_duplicate_khong_lam_bay_hoi_don_vi_ao(tmp_path, monkeypatch):
    """MN1 'Kenh MT' co is_duplicate=1 - neu loc thi mat 900.000 doanh thu that cua Mien Nam."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.kpi_ranking(group_by="region", as_of_date=SAVE_DATE)
    by_area = {r["area_code"]: r for r in rows}

    assert "MN" in by_area, "Mien Nam bi bay hoi - dang loc nham is_duplicate"
    assert by_area["MN"]["sales"] == 900_000
    assert by_area["MN"]["target"] == 1_000_000


def test_qlv_danh_dau_don_vi_ao_de_khong_goi_nham_la_ca_nhan(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.kpi_ranking(group_by="qlv", as_of_date=SAVE_DATE)
    by_code = {r["employee_code"]: r for r in rows}

    assert by_code["MN1"]["la_nhom_kenh"] is True
    assert "ghi_chu" in by_code["MN1"]
    assert by_code["QLV1"]["la_nhom_kenh"] is False
    assert "ghi_chu" not in by_code["QLV1"]


def test_qlv_va_region_luon_khop_tong(tmp_path, monkeypatch):
    """2 nhanh PHAI dung CHUNG _rollup_tier_codes() - nguoi dung cong tay danh sach QLV cua 1 vung
    phai ra dung tong vung do. Lech nhau la dau hieu 1 trong 2 nhanh them dieu kien loc rieng."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    regions = {r["area_code"]: r for r in rt.kpi_ranking(group_by="region", as_of_date=SAVE_DATE)}
    qlvs = rt.kpi_ranking(group_by="qlv", as_of_date=SAVE_DATE, limit=100)

    for area, region_row in regions.items():
        tong_qlv = sum(q["sales"] for q in qlvs if q["area_code"] == area)
        assert tong_qlv == region_row["sales"], f"vung {area}: tong QLV {tong_qlv} != tong vung {region_row['sales']}"


def test_scope_employee_code_chi_tra_ve_chinh_ho(tmp_path, monkeypatch):
    """Tai khoan QLV KHONG duoc xem bang xep hang so sanh voi QLV khac (du lieu hieu suat ca nhan)."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.kpi_ranking(group_by="qlv", as_of_date=SAVE_DATE, scope_employee_code="QLV1")

    assert [r["employee_code"] for r in rows] == ["QLV1"]


def test_khong_co_tang_quan_ly_thi_bao_ro_khong_tra_rong_am_tham(tmp_path, monkeypatch):
    """manager_code rong het -> KHONG duoc tra [] am tham (nguoi dung hieu la 'khong ai dat KPI'),
    phai co canh bao qua _warn()."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dim_targetvungmien (area_code TEXT, channel_code TEXT, amount REAL, doc_date TEXT);
        """
    )
    conn.execute("INSERT INTO dim_nhanvien VALUES ('X','Nguoi X',0,'TDV','MB','X')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('X','KH1',100,200,?,0,NULL)", (SAVE_DATE,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    token = rt._tool_warnings.set([])
    try:
        rows = rt.kpi_ranking(group_by="region", as_of_date=SAVE_DATE)
        warnings = rt._tool_warnings.get()
    finally:
        rt._tool_warnings.reset(token)

    assert rows == []
    assert warnings, "phai canh bao khi khong xac dinh duoc tang quan ly"
    assert "KHONG" in warnings[0]


def test_dau_thang_dung_ky_tron_va_hop_roster_de_khong_tra_rong(tmp_path, monkeypatch):
    """04/09/2026: snapshot dau thang chi con nguoi da ban; ranking phai dung ky tron gan nhat."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    # Thang moi chi QLV1 co cap duoi phat sinh. MN1 va cap duoi chua ban nen bien mat khoi snapshot.
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES "
                 "('TDV1','KH-MOI',10,0,'2026-09-04',0,'QLV1')")
    # Nguoi moi vao can duoc roster nhan dien, du chua co KPI o ky tron truoc de vao bang xep hang.
    conn.execute("INSERT INTO dim_nhanvien VALUES "
                 "('QLV-MOI','Quan ly moi',0,'QLV','MB','QLV-MOI')")
    conn.execute("INSERT INTO dim_nhanvien VALUES "
                 "('TDV-MOI','Nhan vien moi',0,'TDV','MB','TDV-MOI')")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES "
                 "('TDV-MOI','KH-MOI-2',5,0,'2026-09-04',0,'QLV-MOI')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    token = rt._tool_warnings.set([])
    try:
        qlvs = rt.kpi_ranking(group_by="qlv", as_of_date="2026-09-04", limit=100)
        regions = rt.kpi_ranking(group_by="region", as_of_date="2026-09-04", limit=100)
        warnings = rt._tool_warnings.get()
    finally:
        rt._tool_warnings.reset(token)

    assert {r["employee_code"] for r in qlvs} == {"QLV1", "MN1"}
    assert {r["area_code"] for r in regions} == {"MB", "MN"}
    assert {"QLV1", "MN1", "QLV-MOI"} <= set(rt._rollup_tier_codes("2026-09-04"))
    assert any(SAVE_DATE in warning and "snapshot giua thang" in warning for warning in warnings)
    assert {r['as_of'] for r in qlvs + regions} == {SAVE_DATE}


def test_giua_thang_co_target_thi_giu_ky_hien_tai_va_bao_nguoi_chua_du_du_lieu(tmp_path, monkeypatch):
    path = tmp_path / 'warehouse.db'
    _make_db(path)
    with sqlite3.connect(path) as conn:
        # QLV1 da co KPI ky moi, MN1 chi co doanh so nhung chua co target.
        conn.executemany('INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?,?)', [
            ('QLV1','ROLL1',30,100,'2026-08-02',0,None),
            ('MN1','ROLL2',50,0,'2026-08-02',0,None),
        ])
    monkeypatch.setattr(local_warehouse, 'DB_PATH', str(path))
    token = rt._tool_warnings.set([])
    try:
        qlvs = rt.kpi_ranking('qlv', '2026-08-02', limit=100)
        regions = rt.kpi_ranking('region', '2026-08-02', limit=100)
        warnings = rt._tool_warnings.get()
    finally:
        rt._tool_warnings.reset(token)
    assert [r['employee_code'] for r in qlvs] == ['QLV1']
    assert {r['as_of'] for r in qlvs + regions} == {'2026-08-02'}
    # 30 la doanh so ky moi da biet doc lap; khong the xanh neu ca hai ve cung lay nham thang cu.
    assert sum(r['sales'] for r in qlvs) == sum(r['sales'] for r in regions) == 30
    assert qlvs[0]['pct'] == 30
    assert any('chua du snapshot/target' in warning for warning in warnings)
