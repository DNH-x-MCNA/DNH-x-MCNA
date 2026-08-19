# -*- coding: utf-8 -*-
"""Kiem chung report_templates.salary_detail()/_salary_detail_one() - CHUA TUNG co test rieng
truoc 19/08/2026 (chi co 1 test cho _closed_salary_date_filter trong
test_business_composite_tools.py). Day la ham nhay cam nhat trong domain luong thuong: da bi vai
that qua nhieu lan sua that (03/08 loi phan quyen QLV, 28/07/2026 loi dong "khoi tao" dau thang).
Khoa lai dung hanh vi da sua, khong tim loi moi.
"""
import io
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt

FTL_COLUMNS = [
    "employee_code", "employee_name", "position_code", "area_code", "area_code2",
    "manager_code", "save_date",
    "month_sale_amount", "month_sale_target", "month_sale_percent",
    "dm1_amount", "dm1_percent", "dm2_amount", "dm2_percent", "dm3_amount", "dm3_percent",
    "dm_bonus", "total_point",
    "sku_quantity", "sku_target", "sku_percent",
    "reorder_cus_quantity", "reorder_cus_target", "reorder_percent",
    "new_cus_quantity", "new_cus_target", "new_cus_percent",
    "active_cus_quantity", "active_cus_target", "active_cus_percent",
    "aso_quantity", "aso_percent", "aso_bonus",
    "call_quantity", "call_target", "call_percent",
    "v15_amount", "v15_percent", "v15_bonus",
    "v22_amount", "v22_percent", "v22_bonus",
    "v25_amount", "v25_percent", "v25_bonus",
    "target_product_amount", "target_product_percent", "tpr_point",
    "lunch_amount", "transport_amount", "phone_amount",
    "salary_coeff",
]


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        f"""
        CREATE TABLE fact_thongketinhluong ({', '.join(c + ' TEXT' if c in
            ('employee_code','employee_name','position_code','area_code','area_code2','manager_code','save_date')
            else c + ' REAL' for c in FTL_COLUMNS)});
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dmssx_nhanvien (id_code INTEGER, name TEXT, dmscode TEXT, code TEXT, is_active TEXT);
        """
    )
    conn.commit()
    conn.close()


def _row(**overrides):
    """1 dong fact_thongketinhluong day du, gia tri mac dinh la 0/None hop le - test ghi de tung
    truong can thiet."""
    base = {c: (None if c in
                ("employee_code", "employee_name", "position_code", "area_code", "area_code2",
                 "manager_code", "save_date")
                else 0.0) for c in FTL_COLUMNS}
    base.update(overrides)
    return tuple(base[c] for c in FTL_COLUMNS)


def _insert(conn, **overrides):
    placeholders = ",".join(["?"] * len(FTL_COLUMNS))
    conn.execute(f"INSERT INTO fact_thongketinhluong VALUES ({placeholders})", _row(**overrides))


def test_bo_qua_dong_khoi_tao_dau_thang_lay_dung_snapshot_da_chot(tmp_path, monkeypatch):
    """28/07/2026 (thuc te): Bravo tao san 1 dong 'khoi tao' dau thang moi (total_point=0.0, cac
    truong v15/v22/v25_percent la NULL that su). Neu chi lay MAX(save_date) don thuan se lay nham
    dong rong nay thay vi snapshot THAT da chot cua ky truoc."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    # Snapshot THAT da chot, 31/07 - co du v15/v22/v25_percent va dm_bonus>0
    _insert(conn, employee_code="NV01", employee_name="Nguyen Van A", position_code="TDV",
            area_code="MB", save_date="2026-07-31",
            month_sale_amount=50_000_000, month_sale_target=60_000_000, month_sale_percent=0.833,
            dm_bonus=2_000_000, v15_percent=0.3, v15_bonus=500_000,
            v22_percent=0.6, v22_bonus=800_000, v25_percent=0.833, v25_bonus=1_000_000,
            aso_bonus=300_000, lunch_amount=500_000, transport_amount=300_000, phone_amount=200_000)
    # Dong "khoi tao" dau thang moi 01/08 - total_point=0.0 (KHONG PHAI NULL) nhung v25_percent NULL
    _insert(conn, employee_code="NV01", employee_name="Nguyen Van A", position_code="TDV",
            area_code="MB", save_date="2026-08-01", total_point=0.0,
            v15_percent=None, v22_percent=None, v25_percent=None)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_detail(employee_code="NV01", scope_employee_code="NV01", scope_role="qlv")

    assert "error" not in result
    assert result["save_date"] == "2026-07-31"
    assert result["total_bonus"] == 2_000_000 + 300_000 + 500_000 + 800_000 + 1_000_000


def test_total_bonus_khong_gom_phu_cap(tmp_path, monkeypatch):
    """'Phan biet thuong va phu cap' - total_bonus CHI gom DM+ASO+V15+V22+V25, KHONG duoc cong them
    an ca/xang xe/dien thoai vao chung."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="NV01", employee_name="Nguyen Van A", position_code="TDV",
            save_date="2026-07-31", v25_percent=0.9,
            dm_bonus=1_000_000, aso_bonus=200_000, v15_bonus=300_000, v22_bonus=400_000, v25_bonus=500_000,
            lunch_amount=1_000_000, transport_amount=1_000_000, phone_amount=1_000_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_detail(employee_code="NV01", scope_employee_code="NV01", scope_role="qlv")

    assert result["total_bonus"] == 1_000_000 + 200_000 + 300_000 + 400_000 + 500_000
    assert result["allowance"]["total"] == 3_000_000
    assert "CHUA GOM LUONG CO BAN" in result["warning"]


def test_qlv_xem_dung_doi_vien_bao_cao_truc_tiep_thi_duoc_phep(tmp_path, monkeypatch):
    """03/08/2026 (thuc te, QLV Bui Khac Dung): QLV phai xem duoc TDV BAO CAO TRUC TIEP len minh,
    xac dinh qua manager_code trong CHINH fact_thongketinhluong."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="TDV01", employee_name="Nhan vien A", position_code="TDV",
            manager_code="QLV01", save_date="2026-07-31", v25_percent=0.9, dm_bonus=100_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_detail(employee_code="TDV01", scope_employee_code="QLV01", scope_role="qlv")

    assert "error" not in result
    assert result["employee_code"] == "TDV01"


def test_qlv_xem_nguoi_ngoai_doi_bi_tu_choi(tmp_path, monkeypatch):
    """Cung sua 03/08: QLV KHONG duoc xem nguoi khong bao cao truc tiep len minh, du biet dung ma."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="TDV02", employee_name="Nhan vien B", position_code="TDV",
            manager_code="QLV_KHAC", save_date="2026-07-31", v25_percent=0.9, dm_bonus=100_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_detail(employee_code="TDV02", scope_employee_code="QLV01", scope_role="qlv")

    assert "error" in result
    assert "khong thuoc doi cua ban" in result["error"]


def test_tdv_khong_duoc_xem_nguoi_khac(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="TDV_KHAC", employee_name="Nhan vien C", position_code="TDV",
            save_date="2026-07-31", v25_percent=0.9, dm_bonus=999_999)
    _insert(conn, employee_code="TDV01", employee_name="Chinh minh", position_code="TDV",
            save_date="2026-07-31", v25_percent=0.9, dm_bonus=1_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    # TDV01 (khong phai qlv/regional_director/c_level) hoi ve TDV_KHAC -> bi ep ve chinh minh
    result = rt.salary_detail(employee_code="TDV_KHAC", scope_employee_code="TDV01", scope_role="tdv")

    assert result["employee_code"] == "TDV01"
    assert result["dm_bonus"] == 1_000


def test_goi_hang_loat_nhieu_ma_1_loi_khong_lam_hong_ca_lo(tmp_path, monkeypatch):
    """04-07/08/2026: ho tro nhieu ma cach nhau dau phay trong 1 lan goi. 1 nguoi loi (ngoai doi)
    KHONG duoc lam mat ket qua cua nguoi con lai."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="TDV01", employee_name="A", position_code="TDV",
            manager_code="QLV01", save_date="2026-07-31", v25_percent=0.9, dm_bonus=100_000)
    _insert(conn, employee_code="TDV02", employee_name="B", position_code="TDV",
            manager_code="QLV_KHAC", save_date="2026-07-31", v25_percent=0.9, dm_bonus=200_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_detail(employee_code="TDV01,TDV02", scope_employee_code="QLV01", scope_role="qlv")

    assert len(result["employees"]) == 2
    ok = next(e for e in result["employees"] if e["requested_employee_code"] == "TDV01")
    bad = next(e for e in result["employees"] if e["requested_employee_code"] == "TDV02")
    assert "error" not in ok and ok["dm_bonus"] == 100_000
    assert "error" in bad


def test_get_salary_ranking_da_dang_ky_trong_employee_scoped_templates():
    """19/08/2026 (thuc te): truoc khi sua, 'get_salary_ranking' nam trong _PERSON_LEVEL_TEMPLATES
    nhung KHONG nam trong _EMPLOYEE_SCOPED_TEMPLATES nhu 3 tool anh em cung domain (get_salary_detail/
    get_salary_achievement_summary/get_salary_bonus_policy) - khien call_template() FAIL-CLOSED tu
    choi MOI lan tai khoan QLV goi tool nay, ke ca hoi ve chinh doi minh. Day bay chong tai dien."""
    assert "get_salary_ranking" in rt._EMPLOYEE_SCOPED_TEMPLATES
    assert "get_salary_ranking" in rt._PERSON_LEVEL_TEMPLATES


def test_salary_ranking_qlv_scope_chi_thay_doi_minh_va_chinh_minh(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="QLV01", employee_name="Quan ly A", position_code="QLV",
            save_date="2026-07-31", v25_percent=0.9, dm_bonus=1_000_000)
    _insert(conn, employee_code="TDV01", employee_name="Nhan vien doi A", position_code="TDV",
            manager_code="QLV01", save_date="2026-07-31", v25_percent=0.9, dm_bonus=500_000)
    _insert(conn, employee_code="TDV_KHAC", employee_name="Nhan vien doi khac", position_code="TDV",
            manager_code="QLV_KHAC", save_date="2026-07-31", v25_percent=0.9, dm_bonus=9_999_999)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    scoped = rt.salary_ranking(scope_employee_code="QLV01")
    codes = {r["employee_code"] for r in scoped["ranking"]}

    assert codes == {"QLV01", "TDV01"}
    assert "TDV_KHAC" not in codes


def test_call_template_ep_dung_scope_cho_qlv_khong_con_lo_hay_bi_chan(tmp_path, monkeypatch):
    """Kiem qua DUNG duong san xuat that (call_template(), noi nl2sql.py goi vao) thay vi goi thang
    salary_ranking() - xac nhan ca 2 nhanh loi cu deu da het: (1) khong con lo du lieu doi khac cho
    QLV (truoc: scope_employee_code khong bao gio duoc ep vi thieu _PERSON_LEVEL_TEMPLATES), (2)
    khong con bi tu choi (truoc: neu THEM vao _PERSON_LEVEL_TEMPLATES ma QUEN _EMPLOYEE_SCOPED_
    TEMPLATES thi se fail-closed chan hoan toan)."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="QLV01", employee_name="A", position_code="QLV",
            save_date="2026-07-31", v25_percent=0.9, dm_bonus=1_000_000)
    _insert(conn, employee_code="TDV01", employee_name="B", position_code="TDV",
            manager_code="QLV01", save_date="2026-07-31", v25_percent=0.9, dm_bonus=500_000)
    _insert(conn, employee_code="TDV_KHAC", employee_name="C", position_code="TDV",
            manager_code="QLV_KHAC", save_date="2026-07-31", v25_percent=0.9, dm_bonus=9_999_999)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.call_template("get_salary_ranking", {}, scope_role="qlv",
                              scope_employee_code="QLV01", scope_area_code="MB")

    assert result.get("ok") is True, f"khong duoc bi chan: {result}"
    codes = {r["employee_code"] for r in result["result"]["ranking"]}
    assert codes == {"QLV01", "TDV01"}
    assert "TDV_KHAC" not in codes


def test_salary_ranking_khong_co_scope_thi_thay_het(tmp_path, monkeypatch):
    """Xac nhan them scope_employee_code KHONG lam vo hanh vi cu (c_level/khong truyen scope van
    thay toan bo, dung nhu truoc khi sua)."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="QLV01", employee_name="A", position_code="QLV",
            save_date="2026-07-31", v25_percent=0.9, dm_bonus=1_000_000)
    _insert(conn, employee_code="TDV_KHAC", employee_name="B", position_code="TDV",
            manager_code="QLV_KHAC", save_date="2026-07-31", v25_percent=0.9, dm_bonus=9_999_999)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_ranking()
    codes = {r["employee_code"] for r in result["ranking"]}

    assert codes == {"QLV01", "TDV_KHAC"}


def test_meets_bonus_threshold_khac_nhau_theo_vai_tro(tmp_path, monkeypatch):
    """TDV nguong 65%, QLV nguong 70% - cung 1 ty le 67% phai ra ket qua KHAC nhau tuy vai tro."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="TDV01", employee_name="A", position_code="TDV",
            save_date="2026-07-31", v25_percent=0.9, month_sale_percent=0.67)
    _insert(conn, employee_code="QLV01", employee_name="B", position_code="QLV",
            save_date="2026-07-31", v25_percent=0.9, month_sale_percent=0.67)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    tdv = rt.salary_detail(employee_code="TDV01", scope_employee_code="TDV01", scope_role="tdv")
    qlv = rt.salary_detail(employee_code="QLV01", scope_employee_code="QLV01", scope_role="qlv")

    assert tdv["bonus_threshold_pct"] == 65 and tdv["meets_bonus_threshold"] is True
    assert qlv["bonus_threshold_pct"] == 70 and qlv["meets_bonus_threshold"] is False
