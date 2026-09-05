# -*- coding: utf-8 -*-
"""24/08/2026: cac tool P0/P1/P2 con lai cua bo 138 cau hoi - khong goi API."""
import datetime as real_dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


class _FixedDate(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 4, 20)


def _make_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT,
          amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
          employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT,
          amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT, created_at TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
          employee_code TEXT, revenue REAL, invoice_count INTEGER);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
          emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, kenh_bh TEXT);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
          position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
          is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
          month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT,
          year_sale_target REAL, amount_cus REAL, is_ro INTEGER, is_ac INTEGER,
          max_customer_ord_amount REAL, emp_dms_code TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT,
          position_code TEXT, area_code TEXT, manager_code TEXT, save_date TEXT,
          month_sale_amount REAL, month_sale_target REAL, month_sale_percent REAL);
        CREATE TABLE dim_targetvungmien (doc_date TEXT, area_code TEXT, amount REAL);
        """
    )
    con.executemany("INSERT INTO dim_tinhthanhpho VALUES (?,?,?)", [(1, "Ha Noi", "MB"), (2, "HCM", "MN")])
    con.executemany("INSERT INTO dms_khachhang VALUES (?,?,?,?,?,?)", [
        ("C1", "Khach 1", 1, 1, "D1", "OTC"), ("C2", "Khach 2", 1, 2, "D2", "OTC"),
        ("C3", "Khach 3", 1, 3, "D1", "OTC"), ("C4", "Khach 4", 2, 4, "D3", "OTC"),
        ("C5", "Khach thieu tinh", 999, 5, "", "OTC"),
    ])
    con.executemany("INSERT INTO brv_sanpham VALUES (?,?,?,?,?)", [
        ("A", "San pham A", "G1", "hop", 1), ("B", "San pham B", "G1", "hop", 2),
    ])
    con.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("T1", "TDV 1", 0, "TDV", "MB", "D1", "2026-01-01", None, 0, None),
        ("T2", "TDV 2", 0, "TDV", "MB", "D2", "2025-01-01", None, 0, None),
        ("T3", "TDV 3", 0, "TDV", "MN", "D3", "2025-01-01", None, 0, None),
        ("Q1", "QLV Bac", 0, "QLV", "MB", "Q1D", "2020-01-01", None, 0, None),
        ("Q2", "QLV Nam", 0, "QLV", "MN", "Q2D", "2020-01-01", None, 0, None),
        ("DUP", "Ma trung", 1, "TDV", "MB", "DX", "2020-01-01", None, 0, None),
    ])

    def inv(day, customer, item, amount, order, emp):
        city = 2 if customer == "C4" else 1
        con.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (day, customer, item, amount, 1, amount, order, city, emp, day, "OTC"))

    # C1 mua A+B deu Jan-Apr -> cohort retention va cap mua kem manh.
    for month in (1, 2, 3, 4):
        inv(f"2026-{month:02d}-05", "C1", "A", 100, f"O{month}1", "D1")
        inv(f"2026-{month:02d}-05", "C1", "B", 80, f"O{month}1", "D1")
    # C2 chi mua A o Jan va Mar, dung mua trong Apr.
    inv("2026-01-10", "C2", "A", 300, "O12", "D2")
    inv("2026-03-10", "C2", "A", 500, "O32", "D2")
    # C3 chi xuat hien Apr; hai don de test repeat order.
    inv("2026-04-08", "C3", "A", 250, "O43", "D1")
    inv("2026-04-18", "C3", "A", 150, "O44", "D1")
    # C4 mua Jan, im Feb-Mar va quay lai Apr -> reactivated, thuoc MN/Q2.
    inv("2026-01-12", "C4", "B", 200, "O14", "D3")
    inv("2026-04-12", "C4", "B", 600, "O45", "D3")
    # Mo coi + thieu ma NV de data quality bat duoc.
    inv("2026-04-15", "ORPHAN", "A", 50, "O46", "")

    def fact(emp, customer, actual, target, manager, nc=0):
        con.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (emp, customer, actual, target, "2026-04-15", nc, manager,
                     0, actual, 0, 0, 0, emp))
    fact("T1", "C1", 600, 1000, "Q1")
    fact("T2", "C2", 200, 1000, "Q1")
    fact("T3", "C4", 900, 1000, "Q2")
    fact("Q1", "ROLL1", 800, 2000, None)
    fact("Q2", "ROLL2", 900, 1000, None)
    fact("MISSING", "CM", 10, 0, None)

    for month, vals in (("2026-02-28", (500, 100, 700)),
                        ("2026-03-31", (400, 200, 800)),
                        ("2026-04-15", (300, 300, 900))):
        for emp, name, area, manager, actual in (
            ("T1", "TDV 1", "MB", "Q1", vals[0]),
            ("T2", "TDV 2", "MB", "Q1", vals[1]),
            ("T3", "TDV 3", "MN", "Q2", vals[2]),
        ):
            con.execute("INSERT INTO fact_thongketinhluong VALUES (?,?,?,?,?,?,?,?,?)",
                        (emp, name, "TDV", area, manager, month, actual, 1000, actual / 10))
    con.executemany("INSERT INTO dim_targetvungmien VALUES (?,?,?)", [
        ("2026-04-01", "MB", 2000), ("2026-04-01", "MN", 1000),
    ])
    con.commit(); con.close()


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _make_db(path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    return path


def test_cohort_retention_tinh_dung_tu_hoa_don(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.customer_cohort_retention(month_to="2026-01", months_back=1, age_months=[1, 3])
    jan = next(x for x in r["cohorts"] if x["cohort_month"] == "2026-01")
    assert jan["cohort_customers"] == 3  # C1, C2, C4
    age1 = next(x for x in jan["retention"] if x["age_month"] == 1)
    age3 = next(x for x in jan["retention"] if x["age_month"] == 3)
    assert age1["retained_customers"] == 1  # chi C1 mua Feb
    assert age3["retained_customers"] == 2  # C1 va C4 mua Apr


def test_customer_movement_phan_loai_new_reactivated_stopped(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.customer_movement(month="2026-04", history_months=4, limit=50)
    by = {x["customer_code"]: x for x in r["customers"]}
    assert by["C3"]["movement"] == "NEW_OR_FIRST_OBSERVED"
    assert by["C3"]["has_repeat_order_current"] is True
    assert by["C4"]["movement"] == "REACTIVATED"
    assert by["C2"]["movement"] == "STOPPED"


def test_gap_run_rate_qlv_chi_thay_doi_minh(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.kpi_gap_run_rate(as_of_date="2026-04-15", group_by="employee",
                            scope_area_code="MB", scope_employee_code="Q1")
    assert {x["employee_code"] for x in r["rows"]} == {"T1", "T2"}
    t1 = next(x for x in r["rows"] if x["employee_code"] == "T1")
    # 04/09/2026: kpi_gap_run_rate doi nen tu fact_tonghopkhachhang (1 dong/(NV x khach), nhan vien
    # khong duoc giao khach nao thi VO HINH) sang fact_thongketinhluong (1 dong/nhan vien). Fixture
    # co y de 2 bang lech nhau: T1 co actual=600 ben bang cu, actual=300 ben bang moi. Cac ky vong
    # duoi day theo NGUON MOI - gap_80 = 1000*0.8-300, gap_100 = 1000-300, run-rate = 300/15*30.
    assert t1["gap_80"] == 500
    assert t1["gap_100"] == 700
    assert t1["linear_run_rate"] == 600

    team_total = rt.kpi_gap_run_rate(as_of_date="2026-04-15", group_by="total",
                                     scope_area_code="MB", scope_employee_code="Q1")
    assert len(team_total["rows"]) == 1
    assert team_total["rows"][0]["group_code"] == "Q1"
    assert team_total["rows"][0]["actual"] == 800


def test_cross_sell_tim_dung_khach_mua_a_chua_mua_b(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.cross_sell_opportunities(as_of_date="2026-04-20", lookback_months=4,
                                    min_together_orders=2)
    assert any({p["item_a"], p["item_b"]} == {"A", "B"} for p in r["pairs"])
    assert any(x["customer_code"] == "C2" and x["has_item"] == "A" and
               x["missing_item"] == "B" for x in r["opportunities"])


def test_coverage_benchmark_khach_va_san_pham(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    customers = rt.customer_product_coverage(as_of_date="2026-04-20", lookback_months=3,
                                             mode="customer")
    current = customers["current_period"]
    previous = customers["previous_period"]
    current_days = (real_dt.date.fromisoformat(current["to"]) -
                    real_dt.date.fromisoformat(current["from"])).days + 1
    previous_days = (real_dt.date.fromisoformat(previous["to"]) -
                     real_dt.date.fromisoformat(previous["from"])).days + 1
    assert customers["window_days"] == current_days == previous_days
    by = {x["code"]: x for x in customers["rows"]}
    assert by["C1"]["products"] == 2
    assert by["C3"]["products"] == 1
    assert by["C3"]["product_gap_vs_scope_avg"] > 0

    products = rt.customer_product_coverage(as_of_date="2026-04-20", lookback_months=3,
                                            mode="product")
    pb = next(x for x in products["rows"] if x["code"] == "B")
    assert pb["customers"] == 2  # C1 + C4
    assert pb["quantity_per_order"] == 1


def test_coverage_mtd_doi_chieu_cung_ngay_va_giu_nguoi_ky_nay_bang_0(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = rt.customer_product_coverage(
        as_of_date="2026-04-20", lookback_months=1, mode="employee",
        scope_area_code="MB", scope_employee_code="Q1",
    )

    assert result["current_period"] == {"from": "2026-04-01", "to": "2026-04-20"}
    assert result["previous_period"] == {"from": "2026-03-01", "to": "2026-03-20"}
    by = {r["code"]: r for r in result["rows"]}
    assert by["T2"]["revenue"] == 0
    assert by["T2"]["previous_revenue"] == 500
    assert result["largest_decrease"]["code"] == "T2"
    assert result["scope_totals"]["current"]["customers"] == 2
    assert result["scope_totals"]["previous"]["customers"] == 2
    assert result["scope_totals"]["current"]["frequency"] == 1.5
    assert "COUNT(DISTINCT customer_code)" in result["customer_count_definition"]


def test_scope_doi_fallback_emp_dms_code_khi_dim_dmsid_bi_rong(tmp_path, monkeypatch):
    db_path = _setup(tmp_path, monkeypatch)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE dim_nhanvien SET dmsid=NULL WHERE employee_code IN ('T1','T2')")
    con.execute("UPDATE fact_tonghopkhachhang SET emp_dms_code='D1' WHERE employee_code='T1'")
    con.execute("UPDATE fact_tonghopkhachhang SET emp_dms_code='D2' WHERE employee_code='T2'")
    con.commit(); con.close()

    assert set(rt._get_team_dms_ids("Q1", "2026-04-15")) == {"D1", "D2"}
    assert rt._resolve_employee_identity("T1")["dmsid"] == "D1"

    geography = rt.geography_monthly_performance(
        month_to="2026-04", months_back=1, dimension="city",
        scope_area_code="MB", scope_employee_code="Q1",
    )
    assert len(geography["rows"]) == 1
    assert geography["rows"][0]["unit"] == "Ha Noi"
    assert geography["rows"][0]["customers"] == 2
    assert geography["rows"][0]["share_pct"] == 100.0


def test_geography_monthly_co_san_luong_aov_tan_suat_cho_chuoi_3_thang(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = rt.geography_monthly_performance(
        month_to="2026-04", months_back=3, dimension="area",
        scope_area_code="MB", scope_employee_code="Q1",
    )

    assert [r["month"] for r in result["rows"]] == ["2026-02", "2026-03", "2026-04"]
    apr = result["rows"][-1]
    assert apr["paid_quantity"] == 4
    assert apr["invoices"] == 3
    assert apr["customers"] == 2
    assert apr["aov"] == apr["revenue"] / 3
    assert apr["orders_per_customer"] == 1.5
    assert "COUNT(DISTINCT customer_code)" in result["customer_count_definition"]


def test_kpi_gap_tra_san_so_nguoi_theo_tung_moc(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = rt.kpi_gap_run_rate(
        as_of_date="2026-04-15", group_by="employee",
        scope_area_code="MB", scope_employee_code="Q1",
    )

    counts = {row["threshold_pct"]: row["count"] for row in result["threshold_summary"]}
    assert counts == {65: 0, 70: 0, 80: 0, 100: 0, 120: 0}
    assert all(row["total_with_target"] == 2 for row in result["threshold_summary"])


def test_geography_scope_mb_khong_lo_mn(tmp_path, monkeypatch):
    db_path = _setup(tmp_path, monkeypatch)
    # C1 xuat hien ca OTC va ETC trong cung thang: customer count sau khi gop kenh van phai DISTINCT.
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO dmssx_khachhang VALUES ('C1','Khach 1 ETC',1,11,'OTC')")
    con.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-04-09','C1','A',70,1,70,'E1','D1','2026-04-09')")
    con.commit(); con.close()
    r = rt.geography_monthly_performance(month_to="2026-04", months_back=1,
                                         dimension="city", scope_area_code="MB")
    assert {x["unit"] for x in r["rows"]} == {"Ha Noi"}
    assert r["rows"][0]["customers"] == 2  # C1 + C3, C1 khong bi dem hai lan vi mua ca 2 kenh
    blocked = rt.geography_monthly_performance(dimension="npp")
    assert blocked["not_applicable"] is True


def test_workforce_productivity_headcount_va_streak(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.workforce_productivity(month_to="2026-04", months_back=3,
                                  group_by="manager", scope_area_code="MB")
    apr = next(x for x in r["rows"] if x["month"] == "2026-04" and x["group_code"] == "Q1")
    assert apr["headcount"] == 2
    assert apr["actual"] == 600
    assert apr["revenue_per_employee"] == 300


def test_operational_quality_bat_mapping_loi_va_noi_ro_phan_chua_co(tmp_path, monkeypatch):
    db_path = _setup(tmp_path, monkeypatch)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-05-01','C4','A',10,1,10,'FUTURE',2,'D3','2026-05-01','OTC')")
    con.commit(); con.close()
    r = rt.operational_data_quality(as_of_date="2026-04-20")
    kpi = r["checks"]["kpi_employee_mapping"]
    assert kpi["missing_manager"] >= 1 and kpi["missing_target"] >= 1
    assert kpi["missing_employee_dim"] >= 1
    assert r["checks"]["invoice_mapping"]["OTC"]["orphan_customers"] == 1
    assert any("chua hoa don" in x for x in r["unavailable_checks"])
    scoped = rt.operational_data_quality(as_of_date="2026-04-20", scope_area_code="MB")
    assert scoped["checks"]["invoice_mapping"]["OTC"]["future_dated_lines"] == 0


def test_quality_dau_thang_dem_ca_nguoi_mat_snapshot_va_nguoi_moi(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE fact_tonghopkhachhang SET save_date='2026-04-30'")
        conn.execute("INSERT INTO dim_nhanvien (employee_code,name,position_code,area_code,is_duplicate) "
                     "VALUES ('NEW','Nhan vien moi','TDV','MB',0)")
        conn.executemany("INSERT INTO fact_tonghopkhachhang "
                         "(employee_code,customer_code,amount_ct,month_sale_target,save_date,manager_code) "
                         "VALUES (?,?,?,?,?,?)", [
            ('T1','C1',50,1000,'2026-05-02','Q1'),
            ('NEW','CN',20,0,'2026-05-02','Q1'),
        ])
    result = rt.operational_data_quality(as_of_date='2026-05-02')
    check = result['checks']['kpi_employee_mapping']
    # 6 nguoi thang 4 (ke ca MISSING khong co dim) + NEW, khong chi 2 nguoi da ban thang 5.
    assert check['employees'] == 7
    assert check['missing_current_snapshot'] == 5
    assert check['missing_target'] == 6
    scoped = rt.operational_data_quality(as_of_date='2026-05-02', scope_employee_code='Q1')
    assert scoped['checks']['kpi_employee_mapping']['employees'] == 3  # T1/T2/NEW
    assert scoped['samples']['missing_current_snapshot'] == ['T2']
    assert set(scoped['samples']['missing_target']) == {'T2', 'NEW'}
    assert scoped['checks']['kpi_employee_mapping']['missing_manager'] == 0


def test_call_template_ep_du_ca_ba_scope_cho_tool_moi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.call_template("get_geography_monthly_performance",
                         {"month_to": "2026-04", "months_back": 1, "dimension": "city"},
                         scope_area_code="MB", scope_employee_code="Q1", scope_channel="OTC")
    assert r["ok"] is True
    assert {x["unit"] for x in r["result"]["rows"]} == {"Ha Noi"}
