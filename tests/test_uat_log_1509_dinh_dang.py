# -*- coding: utf-8 -*-
"""Dinh dang cau tra loi (anh Dang 15/09/2026):
- moi cau tra loi co so lieu phai co dong "Nguon du lieu: ... (du lieu den ..., dong bo luc ...)";
- moi ma san pham / ma nhan vien phai kem ten.
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
from backend.data_freshness import _SOURCES, _TEMPLATE_SOURCES


def test_moi_tool_da_dang_ky_deu_co_nguon_du_lieu():
    assert set(_TEMPLATE_SOURCES) == set(rt.TEMPLATES)
    assert all(source in _SOURCES for sources in _TEMPLATE_SOURCES.values() for source in sources)


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER,
            manager_area_code TEXT);
        CREATE TABLE dmssx_nhanvien (id_code INTEGER, name TEXT, dmscode TEXT, code TEXT, is_active INTEGER);
    """)
    conn.execute("INSERT INTO brv_sanpham VALUES ('SP01','Siro bo phe',NULL,'Lo',1)")
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,0,'TDV','MB',?,NULL,NULL,0,NULL)", [
        ("TDV01", "Nguyen Van A", "DMS01"), ("QLV01", "Tran Thi B", "DMSQ1")])
    conn.execute("INSERT INTO dmssx_nhanvien VALUES (1,'Nhan vien ETC','DNH00087','E01',1)")
    conn.commit()
    conn.close()
    return str(path)


def test_gan_ten_cho_ma_khong_ghi_de_va_khong_tu_dat_ten(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))
    payload = {
        "rows": [
            {"item_code": "SP01", "revenue": 1},
            {"item_code": "SP_LA", "revenue": 2},
            {"employee_code": "TDV01", "manager_code": "QLV01"},
            {"employee_code": "TDV01", "name": "Ten da co"},
        ],
        "chi_tiet": {"nhan_vien": [{"employee_code": "DNH00087"}, {"employee_code": "DMS01"}]},
    }

    rt._gan_ten_cho_ma(payload)

    rows = payload["rows"]
    assert rows[0]["item_name"] == "Siro bo phe"
    assert "item_name" not in rows[1]                              # khong co trong danh muc: khong bia
    assert rows[2]["employee_name"] == "Nguyen Van A" and rows[2]["manager_name"] == "Tran Thi B"
    assert rows[3] == {"employee_code": "TDV01", "name": "Ten da co"}   # khong ghi de
    assert payload["chi_tiet"]["nhan_vien"][0]["employee_name"] == "Nhan vien ETC"   # nhan vien ETC
    assert payload["chi_tiet"]["nhan_vien"][1]["employee_name"] == "Nguyen Van A"    # ma DMS


def test_call_template_tra_ket_qua_da_gan_ten(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setitem(rt.TEMPLATES, "get_top_products",
                        lambda **kwargs: [{"item_code": "SP01", "revenue": 10}])

    kq = rt.call_template("get_top_products", {"date_from": "2026-09-01", "date_to": "2026-09-15"},
                          scope_role="c_level")

    assert kq["ok"] is True and kq["result"][0]["item_name"] == "Siro bo phe"


def test_gan_ten_loi_danh_muc_khong_lam_hong_ket_qua(tmp_path, monkeypatch):
    path = tmp_path / "rong.db"
    sqlite3.connect(path).close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    payload = [{"item_code": "SP01"}, {"employee_code": "TDV01"}]

    assert rt._gan_ten_cho_ma(payload) == [{"item_code": "SP01"}, {"employee_code": "TDV01"}]


def test_prompt_co_quy_tac_ma_kem_ten():
    prompt = nl2sql._static_system_prompt()
    assert "MA KEM TEN" in prompt and "KHONG tu dat ten" in prompt
