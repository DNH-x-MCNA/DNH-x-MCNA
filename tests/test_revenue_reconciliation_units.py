"""Khóa phép đối soát doanh thu nhóm/kênh và khách chưa quy về tầng bán hàng."""
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))
import local_warehouse
import report_templates as rt


DATE = "2026-09-15"


def _warehouse(path, *, missing_customers=0):
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE fact_tonghopkhachhang (
                employee_code TEXT, customer_code TEXT, amount_ct REAL,
                month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
            CREATE TABLE dim_nhanvien (
                employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
                area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
                is_resigned INTEGER, manager_area_code TEXT);
            CREATE TABLE vhoadon_otc (customer_code TEXT, doc_date TEXT, amount9 REAL);
            CREATE TABLE dms_khachhang (code TEXT, city_id TEXT);
            CREATE TABLE dim_tinhthanhpho (city_id TEXT, area_code TEXT);
            INSERT INTO dim_tinhthanhpho VALUES ('C_MN','MN'),('C_MB','MB');
            INSERT INTO dim_nhanvien VALUES
                ('TP_MN','Truong phong MN',0,'TP','MN','TP_MN',NULL,NULL,0,NULL),
                ('Q_MN','Quan ly MN',0,'QLV','MN','Q_MN',NULL,NULL,0,NULL),
                ('T_MN','TDV MN',0,'TDV','MN','T_MN',NULL,NULL,0,NULL),
                ('MN1','Kenh MT',1,'QLV','MN','MN1',NULL,NULL,0,NULL),
                ('TK_MN','Nhan vien kenh',0,'TK','MN','TK_MN',NULL,NULL,0,NULL),
                ('TP_MB','Truong phong MB',0,'TP','MB','TP_MB',NULL,NULL,0,NULL),
                ('Q_MB','Quan ly MB',0,'QLV','MB','Q_MB',NULL,NULL,0,NULL),
                ('T_MB','TDV MB',0,'TDV','MB','T_MB',NULL,NULL,0,NULL);
            INSERT INTO fact_tonghopkhachhang VALUES
                ('Q_MN','LEAF_MN',10000000,12000000,'2026-09-15',0,NULL),
                ('T_MN','LEAF_MN',10000000,12000000,'2026-09-15',0,'Q_MN'),
                ('MN1','UNIT_MN',200000,300000,'2026-09-15',0,NULL),
                ('TK_MN','UNIT_MN',200000,300000,'2026-09-15',0,'MN1'),
                ('Q_MB','LEAF_MB',3000000,4000000,'2026-09-15',0,NULL),
                ('T_MB','LEAF_MB',3000000,4000000,'2026-09-15',0,'Q_MB');
            INSERT INTO vhoadon_otc VALUES
                ('LEAF_MN','2026-09-15',10000000),
                ('UNIT_MN','2026-09-15',200000),
                ('LEAF_MB','2026-09-15',3000000);
            INSERT INTO dms_khachhang VALUES
                ('LEAF_MN','C_MN'),('UNIT_MN','C_MN'),('LEAF_MB','C_MB');
        """)
        for index in range(missing_customers):
            code = f"NO_LEAF_{index:02d}"
            conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?,?)",
                         ("Q_MN", code, 1000, 12000000, DATE, 0, None))
            conn.execute("INSERT INTO vhoadon_otc VALUES (?,?,?)", (code, DATE, 1000))
            conn.execute("INSERT INTO dms_khachhang VALUES (?,?)", (code, "C_MN"))


def test_nhom_kenh_khong_co_doi_van_duoc_cong_vao_tong_doi_soat(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _warehouse(path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    mn = rt.revenue_reconciliation_check(as_of_date=DATE, area_code="MN")
    assert mn["top_down_revenue_otc"] == mn["bottom_up_revenue_otc"] == 10_200_000
    assert mn["leaf_revenue_otc"] == 10_000_000
    assert mn["standalone_rollup_revenue_otc"] == 200_000
    assert mn["leaf_count_by_position"] == {"TDV": 1}
    assert mn["rollup_nodes_without_tdv"] == 1
    assert mn["reconciliation_status"] == "matched_within_tolerance"
    assert mn["unattributed_invoice_customer_count"] == 0

    mb = rt.revenue_reconciliation_check(as_of_date=DATE, area_code="MB")
    assert mb["top_down_revenue_otc"] == mb["bottom_up_revenue_otc"] == 3_000_000
    assert mb["standalone_rollup_revenue_otc"] == 0
    assert mb["unattributed_invoice_customer_count"] == 0


def test_11_khach_khong_co_dong_tang_ban_hang_khong_duoc_bao_khop(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _warehouse(path, missing_customers=11)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    result = rt.revenue_reconciliation_check(as_of_date=DATE, area_code="MN")
    assert result["top_down_revenue_otc"] == 10_211_000
    assert result["bottom_up_revenue_otc"] == 10_200_000
    assert 99.5 < result["coverage_pct"] < 100.5
    assert result["unattributed_invoice_customer_count"] == 11
    assert result["unattributed_invoice_revenue_otc"] == 11_000
    assert result["reconciliation_status"] == "incomplete_customer_attribution"
    assert result["matched_within_tolerance"] is False
    assert "200,000" in result["warning"]
    assert "11" in result["warning"]
    assert "11,000" in result["warning"]
    assert result["cause_attribution_available"] is False


def test_khach_thieu_tang_ban_hang_khong_ro_ngoai_vung(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _warehouse(path, missing_customers=11)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    mb = rt.revenue_reconciliation_check(as_of_date=DATE, scope_area_code="MB")
    assert mb["area_code"] == "MB"
    assert mb["top_down_revenue_otc"] == 3_000_000
    assert mb["bottom_up_revenue_otc"] == 3_000_000
    assert mb["unattributed_invoice_customer_count"] == 0
    assert mb["unattributed_invoice_revenue_otc"] == 0


def test_khach_co_fact_o_mien_khac_van_la_thieu_phan_bo_trong_mien_duoc_hoi(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _warehouse(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?,?)",
                     ("T_MN", "CROSS", 100, 12000000, DATE, 0, "Q_MN"))
        conn.execute("INSERT INTO vhoadon_otc VALUES (?,?,?)", ("CROSS", DATE, 100))
        conn.execute("INSERT INTO dms_khachhang VALUES (?,?)", ("CROSS", "C_MB"))
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    mb = rt.revenue_reconciliation_check(as_of_date=DATE, scope_area_code="MB")
    assert mb["top_down_revenue_otc"] == 3_000_100
    assert mb["unattributed_invoice_customer_count"] == 1
    assert mb["unattributed_invoice_revenue_otc"] == 100
    assert mb["reconciliation_status"] == "incomplete_customer_attribution"
