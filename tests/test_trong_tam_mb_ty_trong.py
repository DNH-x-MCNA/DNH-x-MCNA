"""26/09/2026: KPI san pham trong tam Mien Bac. TPRTargetAmount (= Bravo FACT_PhatSinhNhanVien.TProdTarget) o MB
la TY TRONG muc tieu 0,45-0,6 cua doanh so trong tam tren doanh so thang, khong phai so tien; MN/MT la so tien.
Truoc ban sua: TDV doi MBKV2 bi bao pct_dat 12.716.142.444% va chi tieu "0,45d". Bravo tinh TargetProductPercent =
(trong tam / doanh so thang) / TProdTarget (khop 86/86 TDV MB snapshot 31/08). Du lieu gia."""
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import local_warehouse  # noqa: E402
import report_templates as rt  # noqa: E402


def _kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE vhoadon_otc (customer_code TEXT, amount9 REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE vhoadon_etc (customer_code TEXT, amount9 REAL, doc_date TEXT, employee_code TEXT);
        INSERT INTO vhoadon_otc VALUES ('K','1','2026-08-30','D1');
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER,
            manager_area_code TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT, position_code TEXT,
            area_code TEXT, manager_code TEXT, save_date TEXT, month_sale_amount REAL,
            target_product_amount REAL, tpr_target_amount REAL, target_product_percent REAL, tpr_point REAL);
        INSERT INTO fact_thongketinhluong VALUES
          ('QMB','QLV Bac','QLV','MB',NULL,'2026-08-31',1000,400,0,NULL,NULL),
          ('TMB','TDV Bac','TDV','MB','QMB','2026-08-31',200,60,0.5,0.6,0.18),
          ('QMN','QLV Nam','QLV','MN',NULL,'2026-08-31',900,300,500,0.6,NULL),
          ('TMN','TDV Nam','TDV','MN','QMN','2026-08-31',300,90,120,0.75,0.2);
    """)
    c.commit(); c.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))


def test_tdv_mien_bac_chi_tieu_la_ty_trong_khop_bravo(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = rt.focus_product_kpi("2026-08", manager_code="QMB")
    tdv = r["thanh_vien_doi"][0]
    assert tdv["kieu_chi_tieu"] == "ty_trong_doanh_so"
    assert tdv["chi_tieu_trong_tam"] is None, "0,5 la ty trong, khong duoc trinh bay la so tien chi tieu."
    assert tdv["ty_trong_muc_tieu_pct"] == 50.0 and tdv["ty_trong_thuc_te_pct"] == 30.0
    assert round(tdv["pct_dat"], 6) == 60.0 == round(tdv["ty_le_goc_bravo"] * 100, 6)


def test_mien_nam_chi_tieu_so_tien_giu_nguyen(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = rt.focus_product_kpi("2026-08", manager_code="QMN")
    tdv = r["thanh_vien_doi"][0]
    assert tdv["kieu_chi_tieu"] == "so_tien" and tdv["chi_tieu_trong_tam"] == 120.0
    assert tdv["pct_dat"] == 75.0


def test_qlv_khong_co_chi_tieu_thi_khong_ghi_chi_tieu_0(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    q = next(x for x in rt.focus_product_kpi("2026-08")["quan_ly_vung"] if x["employee_code"] == "QMB")
    assert q["chi_tieu_trong_tam"] is None and q["pct_dat"] is None and "TPRTargetAmount=0" in q["ghi_chu_chi_tieu"]
