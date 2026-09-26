"""Hop 24/09/2026: cap 2/3 = mien -> QLV/TDV -> khach -> SKU. "Top khach cua TDV X", "top SKU doi QLV Y", "khach Z
mua SKU nao" phai loc TU DAU trong tool (khong lay top toan quoc roi loc, khong tu viet SQL); tai khoan QLV khong
mo duoc TDV doi khac. Top khach kem ten + NV ban chinh de model khong phai goi them get_customer_detail. Du lieu gia."""
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402


def _kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE vhoadon_otc (customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
                                  unit_price REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE vhoadon_etc (customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
                                  unit_price REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT, city_name TEXT);
        CREATE TABLE fact_congno_khachhang (customer_code TEXT, customer_name TEXT, sales_channel TEXT,
                                            area_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, dmsid TEXT, name TEXT, position_code TEXT,
                                   area_code TEXT, is_duplicate INTEGER);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        INSERT INTO dim_tinhthanhpho VALUES (1,'MB','Ha Noi'),(2,'MN','HCM');
        INSERT INTO dms_khachhang VALUES ('KA','Nha thuoc An',1),('KB','Nha thuoc Binh',1),('KN','Nha thuoc Nam',2);
        INSERT INTO brv_sanpham VALUES ('SP1','Siro'),('SP2','Vien');
        INSERT INTO dim_nhanvien VALUES
          ('TM01','D01','Tran Van Mot','TDV','MB',0),
          ('TM02','D02','Le Thi Hai','TDV','MB',0),
          ('TM03','D03','Pham Van Ba','TDV','MN',0),
          ('QL1','ASM1','Do Quan Ly','QLV','MB',0),
          ('GD1','GDM1','Giam Doc Bac','TP','MB',0);
    """)
    c.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?)", [
        ("KA", "SP1", 100, 1, 100, "2026-09-10", "D01"),
        ("KA", "SP2", 40, 1, 40, "2026-09-11", "D02"),
        ("KB", "SP2", 70, 1, 70, "2026-09-12", "D02"),
        ("KN", "SP1", 500, 1, 500, "2026-09-12", "D03"),
    ])
    c.commit(); c.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "_fact_date_le", lambda as_of=None: as_of)
    # Doi QLV lay tu snapshot phan cong (fact_tonghopkhachhang) - gia lap: QL1 quan ly D01, D02.
    monkeypatch.setattr(rt, "_get_team_dms_ids", lambda ma, fdate=None, thong_tin=None: {"QL1": ["D01", "D02"]}[ma])


def _goi(ten, args, **scope):
    kq = rt.call_template(ten, {"date_from": "2026-09-01", "date_to": "2026-09-20", "limit": 10, **args},
                          question="top khach cua TDV", **scope)
    return kq


def test_top_khach_co_ten_va_nv_ban_chinh(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kh = {x["customer_code"]: x for x in rt.top_customers("2026-09-01", "2026-09-20 23:59:59", 10)}
    assert kh["KA"]["customer_name"] == "Nha thuoc An"
    # KA: D01 100 + D02 40 -> NV ban chinh la TM01 (ma nhan vien, khong phai DMSId), 71,4%.
    assert kh["KA"]["nv_ban_chinh"]["employee_code"] == "TM01"
    assert kh["KA"]["nv_ban_chinh"]["dms_id"] == "D01"
    assert kh["KA"]["nv_ban_chinh"]["ty_trong_pct"] == 71.4


def test_top_khach_cua_mot_tdv_loc_tu_dau(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kq = _goi("get_top_customers", {"employee_code": "TM02"}, scope_role="c_level")
    assert kq["ok"] is True
    r = kq["result"]
    assert {x["customer_code"]: x["revenue"] for x in r["customers"]} == {"KB": 70, "KA": 40}
    assert r["customers"][0]["scope_revenue"] == 110, "Mau so ty trong la toan bo doanh thu cua TDV do."
    assert r["loc_theo"]["nhan_vien"]["kieu"] == "MOT_NHAN_VIEN"
    assert r["loc_theo"]["nhan_vien"]["employee_code"] == "TM02"


def test_tim_tdv_theo_ten(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi("get_top_customers", {"employee_code": "Pham Van Ba"}, scope_role="c_level")["result"]
    assert [x["customer_code"] for x in r["customers"]] == ["KN"]


def test_top_khach_ca_doi_qlv(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi("get_top_customers", {"employee_code": "QL1"}, scope_role="c_level")["result"]
    assert {x["customer_code"]: x["revenue"] for x in r["customers"]} == {"KA": 140, "KB": 70}
    assert r["loc_theo"]["nhan_vien"]["kieu"] == "DOI_CUA_QLV"


def test_top_sku_cua_mot_khach_va_cua_mot_tdv(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi("get_top_products", {"customer_code": "KA"}, scope_role="c_level")["result"]
    assert {x["item_code"]: x["revenue"] for x in r["products"]} == {"SP1": 100, "SP2": 40}
    assert r["loc_theo"]["khach_hang"]["customer_name"] == "Nha thuoc An"
    r = _goi("get_top_products", {"employee_code": "TM02"}, scope_role="c_level")["result"]
    assert {x["item_code"]: x["revenue"] for x in r["products"]} == {"SP2": 110}
    assert r["products"][0]["theo_mien"] == {"MB": 110}
    # Ket hop: SKU cua TDV TM02 ban cho khach KA.
    r = _goi("get_top_products", {"customer_code": "KA", "employee_code": "TM02"}, scope_role="c_level")["result"]
    assert {x["item_code"]: x["revenue"] for x in r["products"]} == {"SP2": 40}


def test_qlv_khong_mo_duoc_tdv_doi_khac(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kq = _goi("get_top_customers", {"employee_code": "TM03"}, scope_role="qlv", scope_employee_code="QL1")
    assert kq["ok"] is False and "khong thuoc doi" in kq["error"]
    kq = _goi("get_top_customers", {"employee_code": "TM01"}, scope_role="qlv", scope_employee_code="QL1")
    assert kq["ok"] is True and [x["customer_code"] for x in kq["result"]["customers"]] == ["KA"]


def test_giam_doc_mien_khong_mo_duoc_tdv_mien_khac(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kq = _goi("get_top_customers", {"employee_code": "TM03"}, scope_role="regional_director", scope_area_code="MB")
    assert kq["ok"] is False and "ngoai vung" in kq["error"]
    kq = _goi("get_top_products", {"customer_code": "KN"}, scope_role="regional_director", scope_area_code="MB")
    assert kq["ok"] is False and "ngoai vung" in kq["error"]


def test_model_khong_tu_truyen_dmsid_noi_bo(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kq = _goi("get_top_customers", {"loc_nv_dms": ["D03"]}, scope_role="qlv", scope_employee_code="QL1")
    assert kq["ok"] is True
    assert "KN" not in {x["customer_code"] for x in kq["result"]}, "loc_nv_dms tu model phai bi bo."


def test_ten_trung_hoac_khong_tim_thay_thi_hoi_lai(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi("get_top_customers", {"employee_code": "Van"}, scope_role="c_level")["result"]
    assert r.get("employee_candidates") and "customers" not in r
    r = _goi("get_top_customers", {"employee_code": "Khong Co Ai"}, scope_role="c_level")["result"]
    assert "Khong tim thay" in r["error"] and "customers" not in r
    r = _goi("get_top_customers", {"employee_code": "GD1"}, scope_role="c_level")["result"]
    assert "area_code" in r["answer_rule"], "Cap GD mien dung area_code, khong loc theo 1 nguoi."


def test_tdv_khong_co_hoa_don_trong_ky_thi_noi_ro(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi("get_top_customers", {"employee_code": "TM01", "date_from": "2026-09-15"}, scope_role="c_level")["result"]
    assert r["customers"] == [] and "KHONG thay bang top toan quoc" in r["loc_theo_ghi_chu"]


def test_mo_ta_tool_co_tham_so_cap3():
    tools = {t["name"]: t for t in nl2sql.TEMPLATE_TOOLS}
    assert "employee_code" in tools["get_top_customers"]["input_schema"]["properties"]
    assert {"employee_code", "customer_code"} <= set(tools["get_top_products"]["input_schema"]["properties"])
    assert "nv_ban_chinh" in tools["get_top_customers"]["description"]
    assert "Cap 2/3" in nl2sql._static_system_prompt()
