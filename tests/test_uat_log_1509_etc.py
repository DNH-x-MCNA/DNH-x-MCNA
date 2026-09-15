# -*- coding: utf-8 -*-
"""UAT nhat ky 15/09/2026 - cum ETC (tai khoan dnh_etc, 14:43).

"Doanh so thang nay theo cac nhom hang" khong goi SQL va thieu Dau tu/Khai thac/Duoc lieu/Lao: kho
khong co GroupCode tren hoa don ETC va khong co DIM_KeyClass. Test dung du lieu gia, khong cham Bravo.
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

CAU_UAT = "Doanh số tháng này theo các nhóm hàng"


def _kho(tmp_path, co_cot_nhom=True, co_danh_muc=True):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    cot_nhom = ", group_code TEXT" if co_cot_nhom else ""
    conn.executescript(f"""
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT, created_at TEXT{cot_nhom});
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, amount9 REAL);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE dim_keyclass (group_code TEXT, code TEXT, name TEXT);
    """)
    conn.executemany("INSERT INTO dim_tinhthanhpho VALUES (?,?,?)", [(1, "Ha Noi", "MB"), (2, "HCM", "MN")])
    conn.executemany("INSERT INTO dmssx_khachhang VALUES (?,?,?)", [("BV_MB", "BV Bac", 1), ("BV_MN", "BV Nam", 2)])
    if co_danh_muc:
        conn.executemany("INSERT INTO dim_keyclass VALUES ('ItemTypeETC',?,?)", [
            ("0", "Hàng đầu tư"), ("1", "Hàng khai thác"), ("2", "Hàng dược liệu"),
            ("3", "Hàng lao"), ("4", "Hàng trực tiếp")])
        conn.execute("INSERT INTO dim_keyclass VALUES ('ContractType','0','Khong lien quan')")
    if co_cot_nhom:
        conn.executemany("INSERT INTO vhoadon_etc VALUES (?,?,?,?,1,1,?,NULL,NULL,?)", [
            ("2026-09-03", "BV_MB", "SP1", 400.0, "HD1", "0"),
            ("2026-09-03", "BV_MB", "SP2", 100.0, "HD1", "1"),   # cung hoa don, nhom khac
            ("2026-09-10", "BV_MN", "SP3", 300.0, "HD2", 3.0),   # ma so thuc 3.0 = nhom '3'
            ("2026-09-11", "BV_MN", "SP4", 50.0, "HD3", "9"),    # ma khong co trong danh muc
            ("2026-08-31", "BV_MN", "SP4", 999.0, "HD0", "0"),   # ngoai ky
        ])
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-09-15','KH',1)")
    conn.commit()
    conn.close()
    return str(path)


def _goi(monkeypatch, path, **scope):
    monkeypatch.setattr(local_warehouse, "DB_PATH", path)
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2025-10-01")
    return rt.call_template("get_etc_revenue_by_item_type",
                            {"date_from": "2026-09-01", "date_to": "2026-09-15"}, **scope)


def test_liet_ke_du_nhom_ke_ca_bang_0_va_giu_nguyen_ma_la(tmp_path, monkeypatch):
    kq = _goi(monkeypatch, _kho(tmp_path), scope_role="regional_director", scope_channel="ETC")

    assert kq["ok"] is True
    r = kq["result"]
    theo_ma = {g["group_code"]: g for g in r["groups"]}
    assert r["total_revenue"] == 850.0 and r["total_invoices"] == 3
    assert theo_ma["0"]["revenue"] == 400.0 and theo_ma["0"]["group_name"] == "Hàng đầu tư"
    assert theo_ma["3"]["revenue"] == 300.0 and theo_ma["3"]["group_name"] == "Hàng lao"
    assert theo_ma["2"]["revenue"] == 0.0 and theo_ma["2"]["group_name"] == "Hàng dược liệu"
    assert theo_ma["4"]["revenue"] == 0.0
    # Ma 9 khong co trong danh muc: giu ma, khong tu gan ten "Khac".
    assert theo_ma["9"]["group_name"] is None and "khong tu dat ten" in theo_ma["9"]["ghi_chu"]
    assert sum(g["revenue"] for g in r["groups"]) == r["total_revenue"]
    assert "DIM_KeyClass" in r["bravo_sql_doi_chieu"] and "'2026-09-16'" in r["bravo_sql_doi_chieu"]
    assert r["status"] == "OK"


def test_gioi_han_vung_chi_tinh_khach_cua_vung(tmp_path, monkeypatch):
    kq = _goi(monkeypatch, _kho(tmp_path), scope_role="regional_director", scope_area_code="MB")

    r = kq["result"]
    assert r["total_revenue"] == 500.0
    assert {g["group_code"]: g["revenue"] for g in r["groups"]}["3"] == 0.0


def test_kho_chua_co_cot_nhom_khong_bao_nhom_bang_0(tmp_path, monkeypatch):
    kq = _goi(monkeypatch, _kho(tmp_path, co_cot_nhom=False), scope_role="c_level")

    assert kq["result"]["status"] == "SOURCE_NOT_SYNCED"
    assert "groups" not in kq["result"]


def test_tai_khoan_otc_va_qlv_khong_duoc_goi(tmp_path, monkeypatch):
    path = _kho(tmp_path)
    assert _goi(monkeypatch, path, scope_role="regional_director", scope_channel="OTC")["ok"] is False
    assert _goi(monkeypatch, path, scope_role="qlv", scope_area_code="MB",
                scope_employee_code="QLV01")["ok"] is False


def test_dinh_tuyen_nhom_hang_etc():
    tools = [{"name": "get_etc_revenue_by_item_type"}, {"name": "get_revenue_by_channel"}]
    # Tai khoan kenh ETC hoi khong ghi "ETC" -> van vao tool nhom hang ETC.
    assert nl2sql._required_tool_for_request(CAU_UAT, tools, "ETC")[0] == "get_etc_revenue_by_item_type"
    # Tai khoan OTC/C-Level khong bi cuop sang nhom hang ETC.
    assert nl2sql._required_tool_for_request(CAU_UAT, tools, "OTC")[0] is None
    assert nl2sql._required_tool_for_request(CAU_UAT, tools, None)[0] is None
    assert nl2sql._required_tool_for_question("Doanh số ETC tháng này theo nhóm hàng") == \
        "get_etc_revenue_by_item_type"


def test_cong_cu_moi_co_nguon_du_lieu():
    from backend.data_freshness import _TEMPLATE_SOURCES
    assert _TEMPLATE_SOURCES["get_etc_revenue_by_item_type"] == ("sales_etc",)
