"""Hop 24/09/2026: "bam bang KPI cua QLV/TDV (% dat KPI, nhom hang trong tam, cong no qua han)". get_kpi_scorecard
tra bang KPI tung nguoi ban hang trong MOT lan goi, ke ca snapshot giua thang, khong lo tien thuong; no qua han ca
doi theo dung dinh nghia receivables_overview. Du lieu gia."""
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402

_COT = ("employee_code, employee_name, position_code, area_code, manager_code, save_date, month_sale_amount, "
        "month_sale_target, month_sale_percent, target_product_percent, sku_quantity, sku_target, sku_percent, "
        "reorder_cus_quantity, reorder_percent, new_cus_quantity, new_cus_target, new_cus_percent, aso_quantity, "
        "aso_percent, active_cus_quantity, active_cus_target, active_cus_percent, total_point, dm_bonus, v15_bonus")


def _kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    c = sqlite3.connect(path)
    c.executescript(f"""
        CREATE TABLE vhoadon_otc (customer_code TEXT, amount9 REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE vhoadon_etc (customer_code TEXT, amount9 REAL, doc_date TEXT, employee_code TEXT);
        INSERT INTO vhoadon_otc VALUES ('K1', 1, '2026-09-20', 'D1');
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        INSERT INTO dim_nhanvien (employee_code, name, is_duplicate, position_code, area_code, dmsid) VALUES
          ('T1','Tran Mot',0,'TDV','MB','D1'), ('T2','Le Hai',0,'TDV','MB','D2'), ('C1','Cho Si',0,'CS','MB','D3'),
          ('T9','Nam Chin',0,'TDV','MN','D9'), ('Q1','Quan Ly Bac',0,'QLV','MB','A1'), ('Q9','Quan Ly Nam',0,'QLV','MN','A9');
        CREATE TABLE fact_thongketinhluong ({_COT.replace(',', ' REAL,').replace('employee_code REAL', 'employee_code TEXT')} REAL);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, manager_code TEXT, save_date TEXT);
        INSERT INTO fact_tonghopkhachhang VALUES
          ('T1','K1','Q1','2026-09-20'), ('T2','K2','Q1','2026-09-20'), ('Q1','K3','Q1','2026-09-20'),
          ('T9','K9','Q9','2026-09-20');
        CREATE TABLE fact_congno_khachhang (customer_code TEXT, sales_channel TEXT, snapshot_at TEXT,
            balance_end REAL, total_overdue REAL, overdue_gt_45 REAL);
        INSERT INTO fact_congno_khachhang VALUES
          ('K1','OTC','2026-09-22T08:00',100,40,10), ('K2','OTC','2026-09-22T08:00',50,0,0),
          ('K3','OTC','2026-09-22T08:00',70,30,30), ('K9','OTC','2026-09-22T08:00',9,9,9);
    """)
    dong = [
        # dong khoi tao ngay 1 thang 10 (doanh so 0) phai bi bo qua
        ("T1", "Tran Mot", "TDV", "MB", "Q1", "2026-10-01", 0, 100, 0, None, 0, 25, 0, 0, 0, 0, 3, 0, 0, 0,
         0, 0, None, 0, 0, 0),
        ("T1", "Tran Mot", "TDV", "MB", "Q1", "2026-09-23", 80, 100, 0.8, 0.5, 30, 25, 1.2, 9, 0.9, 1, 3, 0.3333,
         45, 0.75, 0, 0, None, 0.62, 9000000, 500000),
        ("T2", "Le Hai", "TDV", "MB", "Q1", "2026-09-23", 30, 100, 0.3, None, 10, 25, 0.4, 0, 0, 0, 3, 0, 0, 0,
         0, 0, None, 0.1, 0, 0),
        ("C1", "Cho Si", "CS", "MB", "Q1", "2026-09-23", 200, 150, 1.3333, None, 20, 20, 1, 0, 0, 0, 0, None, 5, 1,
         12, 10, 1.2, 0.9, 0, 0),
        ("Q1", "Quan Ly Bac", "QLV", "MB", None, "2026-09-23", 310, 350, 0.8857, None, 0, 0, 0, 0, 0, 0, 0, None,
         0, 0, 0, 0, None, 0.7, 0, 0),
        ("T9", "Nam Chin", "TDV", "MN", "Q9", "2026-09-23", 90, 100, 0.9, 0.8, 20, 25, 0.8, 5, 0.5, 2, 2, 1,
         30, 0.6, 0, 0, None, 0.8, 0, 0),
    ]
    c.executemany(f"INSERT INTO fact_thongketinhluong ({_COT}) VALUES ({','.join('?' * 26)})", dong)
    c.commit(); c.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)


def _goi(args, **scope):
    kq = rt.call_template("get_kpi_scorecard", args, question="bang kpi doi", **scope)
    assert kq["ok"] is True, kq
    return kq["result"]


def test_bang_kpi_doi_giua_thang_du_thanh_phan(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    # Goi thang ham: chot chan ngay tuong lai cua call_template phu thuoc ngay chay test.
    r = rt.kpi_scorecard(manager_code="Q1", as_of_date="2026-10-01")
    assert r["moc_snapshot"] == "2026-09-23" and r["luy_ke_giua_thang"] is True, "Bo dong khoi tao 01/10."
    r = _goi({"manager_code": "Q1"}, scope_role="c_level")
    assert [d["employee_code"] for d in r["nhan_vien"]] == ["T2", "T1", "C1"], "% doanh so thap truoc, khong QLV."
    t1 = next(d for d in r["nhan_vien"] if d["employee_code"] == "T1")
    assert t1["pct_doanh_so"] == 80.0 and t1["toi_nguong_thuong"] is True and t1["nguong_thuong_pct"] == 65
    assert t1["trong_tam_pct_dat"] == 50.0
    assert t1["sku"] == {"dat": 30.0, "chi_tieu": 25.0, "pct": 120.0}
    assert t1["tai_don"] == {"dat": 9.0, "chi_tieu": 10, "pct": 90.0}
    assert t1["aso"] == {"dat": 45.0, "chi_tieu": 60, "pct": 75.0} and "active_customer" not in t1
    assert t1["cong_no_khach_phu_trach"]["no_qua_han"] == 40.0
    t2 = next(d for d in r["nhan_vien"] if d["employee_code"] == "T2")
    assert t2["tai_don"]["chi_tieu"] is None, "Ty le 0 -> khong suy chi tieu."
    cs = next(d for d in r["nhan_vien"] if d["employee_code"] == "C1")
    assert "aso" not in cs and cs["active_customer"]["pct"] == 120.0, "CS dung active customer, khong ASO."


def test_khong_lo_tien_thuong(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi({"manager_code": "Q1"}, scope_role="c_level")
    phang = str(r)
    assert "9000000" not in phang and "500000" not in phang and "bonus" not in phang


def test_no_qua_han_ca_doi_theo_dinh_nghia_cong_no(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    t = _goi({"manager_code": "Q1"}, scope_role="c_level")["tong_hop_theo_qlv"][0]
    # K1 (T1) 40 + K2 (T2) 0 = 40 cua thanh vien; K3 do QLV tu giu 30 -> ca doi 70.
    assert t["no_qua_han_cua_thanh_vien"] == 40.0 and t["no_qua_han_ca_doi"] == 70.0
    assert t["no_qua_han_chua_gan_thanh_vien"] == 30.0
    assert t["doanh_so"] == 310.0 and round(t["pct_doanh_so_doi"], 2) == 88.57


def test_qlv_chi_thay_doi_minh_gd_mien_chi_thay_mien_minh(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi({"manager_code": "Q9"}, scope_role="qlv", scope_employee_code="Q1", scope_area_code="MB")
    assert {d["manager_code"] for d in r["nhan_vien"]} == {"Q1"}, "QLV khong mo duoc doi khac qua manager_code."
    r = _goi({"area_code": "MN"}, scope_role="regional_director", scope_area_code="MB")
    assert {d["area_code"] for d in r["nhan_vien"]} == {"MB"}, "Scope vung cua server thang area_code cua model."


def test_mot_nhan_vien_theo_ten_va_ngoai_doi(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = _goi({"employee_code": "Nam Chin"}, scope_role="c_level")
    assert [d["employee_code"] for d in r["nhan_vien"]] == ["T9"]
    r = _goi({"employee_code": "T9"}, scope_role="qlv", scope_employee_code="Q1", scope_area_code="MB")
    assert "error" in r and "nhan_vien" not in r


def test_tai_khoan_etc_bi_chan_va_dinh_tuyen_bang_kpi():
    assert rt.template_available_for_channel("get_kpi_scorecard", "ETC") is False
    assert rt.template_available_for_channel("get_kpi_scorecard", "OTC") is True
    assert nl2sql._required_tool_for_question("Bảng KPI đội của tôi tháng này") == "get_kpi_scorecard"
    assert nl2sql._required_tool_for_question("bảng KPI thưởng của đội") != "get_kpi_scorecard"
    assert "get_kpi_scorecard" in {t["name"] for t in nl2sql.TEMPLATE_TOOLS}
