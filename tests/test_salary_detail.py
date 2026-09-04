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


def test_goi_hang_loat_tra_payload_gon_va_khong_cat_mat_nguoi(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    for index in range(8):
        code = f"TDV{index:02d}"
        _insert(conn, employee_code=code, employee_name=f"Nhan vien {index}", position_code="TDV",
                manager_code="QLV01", save_date="2026-08-31", month_sale_percent=0.8,
                dm_bonus=100_000 + index, v25_percent=0.8, v25_bonus=50_000,
                lunch_amount=20_000, transport_amount=30_000, phone_amount=40_000)
    conn.commit(); conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    codes = ",".join(f"TDV{index:02d}" for index in range(8))
    result = rt.salary_detail(employee_code=codes, scope_employee_code="QLV01", scope_role="qlv")

    assert result["requested_count"] == result["count"] == result["success_count"] == 8
    assert result["errors"] == []
    assert len(result["employees"]) == 8
    assert all("kpi_indicators" not in row and "dm_breakdown" not in row
               for row in result["employees"])
    assert len(__import__("json").dumps(result, ensure_ascii=False)) < 6000


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
    _insert(conn, employee_code="TRONGTDV6", employee_name="QLV A (vi tri trong)", position_code="TDV",
            manager_code="QLV01", save_date="2026-07-31", v25_percent=0.9, dm_bonus=8_888_888)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    scoped = rt.salary_ranking(scope_employee_code="QLV01")
    codes = {r["employee_code"] for r in scoped["ranking"]}

    assert codes == {"QLV01", "TDV01"}
    assert "TDV_KHAC" not in codes
    assert "TRONGTDV6" not in codes


def test_salary_ranking_co_ky_truoc_va_delta(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="QLV01", employee_name="Quan ly A", position_code="QLV",
            save_date="2026-07-31", v25_percent=0.7, month_sale_percent=0.7,
            dm_bonus=1_000_000, lunch_amount=100_000)
    _insert(conn, employee_code="QLV01", employee_name="Quan ly A", position_code="QLV",
            save_date="2026-08-31", v25_percent=0.8, month_sale_percent=0.8,
            dm_bonus=1_500_000, lunch_amount=150_000)
    conn.commit(); conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_ranking(year_month="2026-08", scope_employee_code="QLV01")

    row = result["ranking"][0]
    assert result["previous_save_date"] == "2026-07-31"
    assert row["previous_month_sale_percent"] == 70.0
    assert row["total_bonus_delta"] == 500_000
    assert row["allowance_delta"] == 50_000


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


def test_salary_achievement_summary_qlv_scope_khop_dung_du_lieu_that(tmp_path, monkeypatch):
    """19/08/2026 (thuc te): salary_achievement_summary() dung _employee_scope_clause() ->
    _get_team_dms_ids() - ham nay tra ve DMSId (dung de loc BANG HOA DON vhoadon_otc/etc). Nhung
    sync_warehouse.py::sync_fact_thongketinhluong() dong bo fact_thongketinhluong.employee_code tu
    CHINH EmployeeCode tho cua Bravo (khong phai EmpDMSCode) - vd EmployeeCode='DNH00832' nhung
    DMSId='HYE_02' (da tai lieu hoa trong employee_daily_kpi()). Neu loc nham DMSId len bang luong,
    QLV se KHONG BAO GIO thay duoc du lieu that cua doi minh."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        f"""
        CREATE TABLE fact_thongketinhluong ({', '.join(c + ' TEXT' if c in
            ('employee_code','employee_name','position_code','area_code','area_code2','manager_code','save_date')
            else c + ' REAL' for c in FTL_COLUMNS)});
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dmssx_nhanvien (id_code INTEGER, name TEXT, dmscode TEXT, code TEXT, is_active TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        """
    )
    # employee_code THAT ('DNH00832') KHAC dmsid ('HYE_02') - dung dinh dang da tai lieu hoa.
    conn.execute("INSERT INTO dim_nhanvien VALUES ('DNH00832','Nhan vien That',0,'TDV','MB','HYE_02')")
    # fact_tonghopkhachhang: xac lap "DNH00832 bao cao len QLV01" de _team_of_qlv tim ra doi.
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES "
                "('DNH00832','KH01',1000000,2000000,'2026-07-15',0,'QLV01')")
    _insert(conn, employee_code="DNH00832", employee_name="Nhan vien That", position_code="TDV",
            manager_code="QLV01", save_date="2026-07-31", v25_percent=0.9,
            v15_bonus=100_000, v22_bonus=0, v25_bonus=0, aso_bonus=0)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_achievement_summary(save_date="2026-07-31", scope_employee_code="QLV01")

    assert "error" not in result, f"QLV khong thay duoc doi minh: {result}"
    assert result["total_employees"] == 1
    assert result["v15_achieved_count"] == 1


def test_cs_va_tk_dung_is_ac_khong_co_aso_trong_salary_detail(tmp_path, monkeypatch):
    """27/08/2026: CS (Cho si) va TK (kenh MT) dung Active Customer/is_ac.
    Neu nguon vo tinh co aso_bonus, bao cao van phai fail-closed: khong hien ASO va
    khong cong ASO vao tong thuong."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="CS01", employee_name="Cho si A", position_code="CS",
            area_code="MB", save_date="2026-07-31", v25_percent=0.9,
            dm_bonus=1_000_000, aso_bonus=99_000_000,
            active_cus_quantity=12, active_cus_target=40, active_cus_percent=0.30,
            aso_quantity=99, aso_percent=2.475,
            v15_bonus=100_000, v22_bonus=200_000, v25_bonus=300_000)
    _insert(conn, employee_code="TK01", employee_name="Kenh MT A", position_code="TK",
            area_code="MB", save_date="2026-07-31", v25_percent=0.9,
            dm_bonus=2_000_000, aso_bonus=88_000_000,
            active_cus_quantity=8, active_cus_target=20, active_cus_percent=0.40,
            aso_quantity=88, aso_percent=4.4)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_detail(employee_code="CS01", scope_employee_code="CS01", scope_role="c_level")

    assert "error" not in result
    assert result["customer_activity_metric"] == "is_ac"
    assert result["is_ac_applicable"] is True
    assert result["aso_applicable"] is False
    assert result["aso_bonus"] is None
    assert result["total_bonus"] == 1_000_000 + 100_000 + 200_000 + 300_000
    assert result["kpi_indicators"]["active_customer"] == {
        "quantity": 12.0, "target": 40.0, "percent": 0.30,
    }
    assert result["kpi_indicators"]["aso"] is None


def test_salary_ranking_loai_aso_cs_tk_va_khong_cong_aso_vao_total(tmp_path, monkeypatch):
    """ASO ranking khong duoc tra CS/TK; total ranking cung khong de ASO bi cong nham."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="CS01", employee_name="Cho si A", position_code="CS",
            area_code="MB", save_date="2026-07-31", v25_percent=0.9,
            dm_bonus=1_000_000, aso_bonus=99_000_000,
            active_cus_quantity=12, active_cus_target=40, active_cus_percent=0.30)
    _insert(conn, employee_code="TDV01", employee_name="TDV A", position_code="TDV",
            area_code="MB", save_date="2026-07-31", v25_percent=0.9,
            dm_bonus=2_000_000, aso_bonus=5_000_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    aso = rt.salary_ranking(position_code="CS", bonus_type="aso")
    assert aso["not_applicable"] is True and aso["ranking"] == []

    total = rt.salary_ranking(bonus_type="total")
    cs = next(row for row in total["ranking"] if row["employee_code"] == "CS01")
    tdv = next(row for row in total["ranking"] if row["employee_code"] == "TDV01")
    assert cs["aso_bonus"] is None
    assert cs["total_bonus"] == 1_000_000
    assert tdv["total_bonus"] == 7_000_000


def test_salary_achievement_summary_khong_dem_aso_cho_cs_tk(tmp_path, monkeypatch):
    """ASO achievement chi tinh vi tri khong phai CS/TK; dong CS/TK duoc ghi nhan la nhom is_ac."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="CS01", employee_name="Cho si A", position_code="CS",
            area_code="MB", save_date="2026-07-31", v25_percent=0.9, aso_bonus=99_000_000)
    _insert(conn, employee_code="TDV01", employee_name="TDV A", position_code="TDV",
            area_code="MB", save_date="2026-07-31", v25_percent=0.9, aso_bonus=5_000_000)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.salary_achievement_summary(save_date="2026-07-31")

    assert result["aso_achieved_count"] == 1
    assert result["is_ac_position_count"] == 1


def test_salary_bonus_policy_aso_cs_tk_tra_not_applicable():
    result = rt.salary_bonus_policy(bonus_type="aso", position_code="tk")

    assert result["not_applicable"] is True
    assert result["position_code"] == "TK"
    assert result["rule_count"] == 0
    assert "is_ac" in result["formula"]


# ---------------------------------------------------------------- salary_bonus_policy (Bravo live)

def test_salary_bonus_policy_bonus_type_khong_hop_le_bi_tu_choi():
    try:
        rt.salary_bonus_policy(bonus_type="v99")
        assert False, "phai raise ValueError"
    except ValueError:
        pass


def test_salary_bonus_policy_v25_tu_07_khong_bao_sai_loi_he_thong(tmp_path, monkeypatch):
    """salary_bonus_policy() tron 2 nguon: _q() (local SQLite, chi de tim NGAY snapshot da chot)
    va _q_bravo() (SQL Server live that, DIM_BacThuong + FACT_ThongKeTinhLuong). Gia lap _q_bravo
    theo NOI DUNG SQL de tra dung loai du lieu cho tung truy van."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, employee_code="TDV01", save_date="2026-07-31", v25_percent=0.9)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    def fake_q_bravo(sql, params=None):
        if "DIM_BacThuong" in sql and "OBJECT_DEFINITION" not in sql:
            # 2 bac (65-75%, 75%+) cho CUNG 1 nhom (MB, TDV, "Thuong nhom hang")
            return [
                {"CriterialCode": "C1", "TypeCode": "V25", "AreaCode": "MB", "PositionCode": "TDV",
                 "Description": "Thuong nhom hang", "StartDate": "2026-07-01", "EndDate": None,
                 "IsTargetPercent": 1, "IsEarnPercent": 0, "FromValue": 65, "ToValue": 75,
                 "Earn1": 500_000, "Earn2": None, "EarnMax": None,
                 "CheckASO": 0, "CheckTargetEmp": 0, "ASOCusCondType": None},
                {"CriterialCode": "C2", "TypeCode": "V25", "AreaCode": "MB", "PositionCode": "TDV",
                 "Description": "Thuong nhom hang", "StartDate": "2026-07-01", "EndDate": None,
                 "IsTargetPercent": 1, "IsEarnPercent": 0, "FromValue": 75, "ToValue": 3000,
                 "Earn1": 1_000_000, "Earn2": None, "EarnMax": None,
                 "CheckASO": 0, "CheckTargetEmp": 0, "ASOCusCondType": None},
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(rt, "_q_bravo", fake_q_bravo)

    result = rt.salary_bonus_policy(bonus_type="v25", as_of_date="2026-07-31", area_code="MB", position_code="TDV")

    assert result["bonus_type"] == "V25"
    assert result["mechanism_status"] == "INACTIVE_FROM_2026_07_REPLACED_BY_V15_V22"
    assert result["rules"] == []
    assert result["rule_count"] == 0
    assert result["inactive_rule_rows_count"] == 2
    assert result["procedure_loads_v25_rules"] is None
    assert result["rule_actual_mismatch_count"] == 0
    assert result["implementation_warning"] is None
