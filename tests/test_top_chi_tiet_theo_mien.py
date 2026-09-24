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
            INSERT INTO dim_tinhthanhpho VALUES (1,'MB2','Ha Noi'),(2,'MN','HCM'),(3,'MT','Da Nang');
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
    assert sp["SP1"]["theo_mien"] == {"MB": 100, "MN": 57, "MT": 20}      # MB2 -> MB; HCM999 -> MN
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
