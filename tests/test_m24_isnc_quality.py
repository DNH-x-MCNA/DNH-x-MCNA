"""M24 phai danh gia dung cohort IsNC va nguoi phu trach trong snapshot KPI."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
import local_warehouse as lw
import nl2sql
import report_templates as rt
import sync_warehouse as sync
from data_freshness import FreshnessCollector


QUESTION = "Mở nhiều khách mới nhưng DT/khách và tỷ lệ mua lại thấp tháng 8/2026"


@pytest.fixture
def kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    monkeypatch.setattr(lw, "DB_PATH", str(path))
    lw.init_schema()
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    with sqlite3.connect(path) as c:
        c.executemany("INSERT INTO dim_nhanvien (employee_code,name,position_code,is_duplicate,area_code) "
                      "VALUES (?,?,?,?,?)", [
            ("T1", "TDV 1", "TDV", None, "MN"),  # Chuyen mien sau ky: phai loc theo FACT MB.
            ("T1", "Ban trung", "QLV", 1, "MN"),
            ("T2", "TDV 2", "TDV", 0, "MB"),
            ("T3", "TDV 3", "TDV", 0, "MB"),
            ("T4", "TDV 4", "TDV", 0, "MN"),
            ("C1", "CTV 1", "CTV", 0, "MB"),  # Tang nhan vien khong chi co TDV.
            ("Q1", "QLV 1", "QLV", 0, "MB"),
        ])
        c.executemany("INSERT INTO fact_tonghopkhachhang "
                      "(employee_code,customer_code,save_date,is_nc,amount_ct,manager_code,area_code) "
                      "VALUES (?,?,?,?,?,?,?)", [
            ("T1", "K1", "2026-08-20", 1, 999, "Q1", "MB"),
            ("T1", "KH_CO_QLV", "2026-08-20", 1, 999, "Q1", "MB"),
            ("T1", "K1", "2026-08-30", 1, 100, "Q1", "MB"),
            ("T1", "K2", "2026-08-30", 1, 200, "Q1", "MB"),
            ("T1", "K3", "2026-08-30", 1, 300, "Q1", "MB"),
            # Dong TDV het co nhung dong rollup QLV con co: van la khach moi (quy tac 15/09, checker
            # S93). Do tren kho 21/09 ky 8/2026: chi dem dong TDV ra 611 khach, OR moi dong ra 627 -
            # dung con so 627/627 ghi trong local_warehouse.py::SCHEMA.
            ("T1", "KH_CO_QLV", "2026-08-30", 0, 900, "Q1", "MB"),
            ("Q1", "KH_CO_QLV", "2026-08-31", 1, 900, "TOP", "MB"),
            ("Q1", "KH_CHI_QLV", "2026-08-31", 1, 250, "TOP", "MB"),  # Khong co dong tang NV nao.
            ("T2", "K4", "2026-08-31", 1, 500, "Q1", "MB"),
            ("T3", "K5", "2026-08-31", 1, 700, "Q2", "MB"),
            ("C1", "K7", "2026-08-31", 1, 400, "Q1", "MB"),
            ("T4", "K6", "2026-08-31", 1, 800, "Q1", "MN"),
            ("T1", "FUTURE", "2026-09-01", 1, 999, "Q1", "MB"),
        ])
        c.execute("INSERT INTO dmssx_nhanvien (code,name,dmscode) VALUES ('DNH01186','NV ETC','DNH01186')")
        c.executemany("INSERT INTO vhoadon_otc (customer_code,stt,doc_date,amount9,employee_code) VALUES (?,?,?,?,?)", [
            ("K1", "A", "2026-08-31 09:00:00", 12, "OTHER_SELLER"),
            ("K1", "B", "2026-08-31 17:00:00", 13, "OTHER_SELLER"),  # 2 don cung ngay.
            ("K2", "C", "2026-08-10", 30, "OTHER_SELLER"),
            ("K2", "C", "2026-08-10", 40, "OTHER_SELLER"),  # 2 SKU chi 1 don.
            ("K3", "X", "2026-08-10", 50, "OTHER_SELLER"),
            ("K2", "NEXT", "2026-09-01", 60, "OTHER_SELLER"),
        ])
        c.executemany("INSERT INTO vhoadon_etc (customer_code,stt,doc_date,amount9,employee_code) VALUES (?,?,?,?,?)", [
            ("K3", "X", "2026-08-10", 70, "DNH01186"),  # Trung Stt khac kenh = 2 don.
            ("ONLY_ETC", "ETC_ONLY", "2026-08-10", 999, "DNH01186"),
        ])
    return path


def quality(**kwargs):
    return rt.new_customer_list(year_month="2026-08", mode="quality", **kwargs)


def test_snapshot_tung_nv_isnc_tdv_va_orderkey_khong_phai_ngay_mua(kho):
    out = quality(scope_area_code="MB")
    rows = {r["employee_code"]: r for r in out["by_employee"]}
    assert set(rows) == {"T1", "T2", "T3", "C1", "Q1"}
    assert "DNH01186" not in rows
    assert rows["T1"]["khach_moi"] == 4
    assert rows["T1"]["doanh_thu_khach_moi"] == 1500  # Amount_CT, khong phai doanh thu hoa don.
    assert rows["T1"]["doanh_thu_binh_quan_khach_moi"] == 375
    assert rows["T1"]["khach_moi_co_mua_lai"] == 2
    assert rows["T1"]["ty_le_mua_lai_khach_moi_pct"] == pytest.approx(50)
    assert rows["T2"]["khach_moi_co_mua_lai"] == 0
    assert out["snapshot_dates"] == ["2026-08-30", "2026-08-31"]
    assert out["by_area"][0]["so_luot_khach_moi_theo_nhan_vien"] == 8
    assert out["by_area"][0]["so_khach_moi_duy_nhat"] == 8
    assert out["by_area"][0]["so_nhan_vien"] == 5
    assert out["tong_khach_moi_duy_nhat"] == 8


def test_co_isnc_o_dong_rollup_qlv_van_la_khach_moi(kho):
    """Quy tac 15/09 (checker S93): co IsNC OR tren moi dong roi moi gan nguoi phu trach."""
    rows = {r["employee_code"]: r for r in quality(scope_area_code="MB")["by_employee"]}
    # Co o dong QLV, co dong TDV de gan -> tinh cho TDV, khong tinh hai lan.
    assert "KH_CO_QLV" not in [r["employee_code"] for r in rows.values()]
    assert rows["T1"]["khach_moi"] == 4 and rows["T1"]["doanh_thu_khach_moi"] == 1500
    # Khong co dong tang nhan vien nao -> giu dong quan ly, khong bo khach.
    assert rows["Q1"]["khach_moi"] == 1 and rows["Q1"]["position_code"] == "QLV"
    # Chuc danh tang nhan vien khong chi co TDV (CTV/CS/TK deu la nguoi ban).
    assert rows["C1"]["khach_moi"] == 1 and rows["C1"]["position_code"] == "CTV"


def test_tai_khoan_tdv_van_thay_khach_cua_chinh_minh(kho):
    """Loc moi manager_code thi tai khoan TDV ra rong va bi bao '0 khach moi'."""
    out = quality(scope_employee_code="T2")
    assert [r["employee_code"] for r in out["by_employee"]] == ["T2"]
    assert out["by_employee"][0]["khach_moi"] == 1
    assert out["tong_khach_moi_duy_nhat"] == 1


def test_scope_doi_kenh_va_limit_khong_lam_sai_tong(kho):
    out = quality(scope_area_code="MB", scope_employee_code="Q1", manager_code="Q2", scope_channel="OTC")
    assert {r["employee_code"] for r in out["by_employee"]} == {"T1", "T2", "C1", "Q1"}
    assert out["by_employee"][0]["khach_moi_co_mua_lai"] == 1  # Khong dem ETC.
    assert quality(scope_channel="ETC")["not_applicable"] is True
    cut = quality(scope_area_code="MB", scope_employee_code="Q1", scope_channel="OTC", limit=1)
    assert cut["by_area"] == out["by_area"]
    assert cut["total_count"] == 4 and cut["returned_count"] == 1 and cut["truncated"]


def test_kho_cu_thieu_area_hoac_ky_phai_bao_chua_danh_gia(kho):
    assert "error" in rt.new_customer_list(year_month="2025-01", mode="quality")
    with sqlite3.connect(kho) as c:
        c.execute("UPDATE fact_tonghopkhachhang SET area_code=NULL")
    assert "AreaCode" in quality(scope_area_code="MB")["error"]
    with sqlite3.connect(kho) as c:
        c.execute("ALTER TABLE fact_tonghopkhachhang DROP COLUMN area_code")
    assert "AreaCode" in quality()["error"]


def test_snapshot_trung_khach_tdv_khong_cong_doanh_thu_sai(kho):
    with sqlite3.connect(kho) as c:
        c.execute("INSERT INTO fact_tonghopkhachhang SELECT * FROM fact_tonghopkhachhang "
                  "WHERE employee_code='T1' AND customer_code='K1' AND save_date='2026-08-30'")
    assert "trung cap TDV/khach" in quality()["error"]


def test_m24_router_dispatch_va_nguon_du_lieu(kho):
    assert nl2sql._required_tool_for_question(QUESTION) == "get_new_customer_list"
    assert nl2sql._required_tool_for_question(
        "Vùng nào mở nhiều khách mới nhưng doanh thu/khách và tỷ lệ mua lại thấp?"
    ) == "get_new_customer_list"
    result = rt.call_template("get_new_customer_list", {"year_month": "2026-08", "mode": "list"},
                              question=QUESTION, scope_role="regional_director", scope_area_code="MB")
    assert result["ok"], result
    assert result["result"]["classification_basis"] == "BRAVO_ISNC_SNAPSHOT"
    collector = FreshnessCollector()
    collector.record_template("get_new_customer_list", result, scope_channel="OTC")
    assert {r.source_key for r in collector.records()} == {"kpi", "sales_otc"}


def test_sync_area_nguon_va_migration_kho_cu(kho, monkeypatch):
    with sqlite3.connect(kho) as c:
        c.execute("ALTER TABLE fact_tonghopkhachhang DROP COLUMN area_code")
    lw.init_schema()
    def query(sql, **params):
        assert "ReOrderSaveDate, AreaCode" in sql
        return [], [("TDV", "KH", 123, 0, "2026-08-31", 1, "QLV", 0, 0, 0, 0,
                     0, "DMS", None, None, None, None, None, "MT")]
    monkeypatch.setattr(sync, "bravo_query", query)
    sync.sync_fact_tonghopkhachhang()
    with sqlite3.connect(kho) as c:
        assert c.execute("SELECT employee_code,amount_ct,area_code FROM fact_tonghopkhachhang").fetchall() == [
            ("TDV", 123.0, "MT")]
