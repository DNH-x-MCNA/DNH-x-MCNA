"""Hop tien do 24/09/2026: "SKU theo detail, khu vuc theo vung mien (top khach hang, no, khu vuc...) -> bat lay
detail theo khu vuc". Top khach kem mien, top san pham kem doanh thu tung mien. Du lieu gia."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402


def _kho(tmp_path, monkeypatch, co_danh_muc=True):
    path = tmp_path / "warehouse.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE vhoadon_otc (customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
                                  unit_price REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE vhoadon_etc (customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
                                  unit_price REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT);
    """)
    if co_danh_muc:
        c.executescript("""
            CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
            CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
            CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT, city_name TEXT);
            INSERT INTO dim_tinhthanhpho VALUES (1,'MB','Ha Noi'),(2,'MN','HCM'),(3,'MT','Da Nang');
            INSERT INTO dms_khachhang VALUES ('KB','Bac',1),('KN','Nam',2);
            INSERT INTO dmssx_khachhang VALUES ('BV','Benh vien Trung',3);
        """)
    c.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?)", [
        ("KB", "SP1", 100, 1, 100, "2026-09-10", "T"), ("KN", "SP1", 50, 1, 50, "2026-09-11", "T"),
        ("HCM999", "SP1", 7, 1, 7, "2026-09-12", "T"),     # khach mo coi: suy mien tu tien to HCM -> MN
        ("KB", "SP2", 30, 1, 30, "2026-09-12", "T")])
    c.executemany("INSERT INTO vhoadon_etc VALUES (?,?,?,?,?,?,?)", [
        ("BV", "SP1", 20, 1, 20, "2026-09-13", "E")])
    c.commit(); c.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))


def test_top_san_pham_kem_doanh_thu_tung_mien_khop_tong(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    sp = {x["item_code"]: x for x in rt.top_products("2026-09-01", "2026-09-30", limit=5)}
    assert sp["SP1"]["theo_mien"] == {"MB": 100, "MN": 57, "MT": 20}      # HCM999 -> MN theo tien to
    assert sum(sp["SP1"]["theo_mien"].values()) == sp["SP1"]["revenue"]
    assert sp["SP2"]["theo_mien"] == {"MB": 30}


def test_top_khach_kem_mien(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kh = {x["customer_code"]: x["mien"] for x in rt.top_customers("2026-09-01", "2026-09-30", limit=10)}
    assert kh == {"KB": "MB", "KN": "MN", "BV": "MT", "HCM999": "MN"}


def test_kho_thieu_danh_muc_van_tra_top_nhu_cu(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch, co_danh_muc=False)
    sp = rt.top_products("2026-09-01", "2026-09-30", limit=5)
    assert sp and "revenue" in sp[0] and "theo_mien" not in sp[0]
    kh = rt.top_customers("2026-09-01", "2026-09-30", limit=5)
    assert {x["customer_code"]: x["mien"] for x in kh}["HCM999"] == "MN"


def test_huong_dan_model_trinh_bay_theo_mien():
    mo_ta = {t["name"]: t["description"] for t in nl2sql.TEMPLATE_TOOLS}
    assert "theo_mien" in mo_ta["get_top_products"] and "Mien" in mo_ta["get_top_customers"]
    assert "CHI TIET THEO KHU VUC" in nl2sql._static_system_prompt()


def _goi(monkeypatch, ten, args, **scope):
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    kq = rt.call_template(ten, args, question="top khach hang mien Trung", **scope)
    assert kq["ok"] is True, kq
    return kq["result"]


def test_hoi_top_mot_mien_thi_loc_ngay_tu_dau(tmp_path, monkeypatch):
    # Hop 24/09: "hoi top khach hang mien Trung, bot lay top 50 toan quoc roi moi loc ra 2 khach mien Trung".
    _kho(tmp_path, monkeypatch)
    kh = _goi(monkeypatch, "get_top_customers", {"date_from": "2026-09-01", "date_to": "2026-09-20",
                                                 "area_code": "MT"}, scope_role="c_level")
    assert [x["customer_code"] for x in kh] == ["BV"]
    sp = _goi(monkeypatch, "get_top_products", {"date_from": "2026-09-01", "date_to": "2026-09-20",
                                                "area_code": "MB"}, scope_role="c_level")
    assert {x["item_code"]: x["revenue"] for x in sp} == {"SP1": 100, "SP2": 30}


def test_tai_khoan_gioi_han_vung_khong_mo_duoc_vung_khac(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kh = _goi(monkeypatch, "get_top_customers", {"date_from": "2026-09-01", "date_to": "2026-09-20",
                                                 "area_code": "MT", "scope_area_code": "MT"},
              scope_role="regional_director", scope_area_code="MB")
    assert [x["customer_code"] for x in kh] == ["KB"], "Scope cua server phai thang tham so cua model."


def test_model_tu_truyen_scope_area_code_bi_bo_qua(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kh = _goi(monkeypatch, "get_top_customers", {"date_from": "2026-09-01", "date_to": "2026-09-20",
                                                 "scope_area_code": "MN"}, scope_role="c_level")
    assert len(kh) == 4, "Khong co area_code hop le -> top toan quoc, khong nhan scope tu model."


def test_chuan_hoa_ma_mien():
    assert (rt._mien_chuan("MB2"), rt._mien_chuan("mt"), rt._mien_chuan(None, "HNO123"),
            rt._mien_chuan(None, "ZZZ")) == ("MB", "MT", "MB", "Khac")
