# -*- coding: utf-8 -*-
"""Hoi quy cac thieu chieu that cua cum C-F; khong goi model/Bravo."""
import os
import sqlite3
import sys


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import local_warehouse
import report_templates as rt


C11 = ("Doanh thu đang phụ thuộc vào top 10 khách hàng, top 10 sản phẩm và top 3 "
       "miền/vùng ở mức nào; xu hướng tập trung tăng hay giảm?")
M40 = "Hàng cận date/chậm luân chuyển nào cần chuyển vùng, đẩy bán hoặc dừng nhập?"


def test_schema_cu_duoc_nang_cap_cot_chiet_khau_tra_hang_va_trang_thai_khach(
        tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "CREATE TABLE vhoadon_otc (doc_date TEXT,customer_code TEXT,item_code TEXT,"
        "employee_code TEXT,channel_code TEXT,city_id INTEGER);"
        "CREATE TABLE vhoadon_etc (doc_date TEXT,customer_code TEXT,item_code TEXT,employee_code TEXT);"
        "CREATE TABLE dms_khachhang (code TEXT,city_id INTEGER);"
    )
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    local_warehouse.init_schema()

    conn = sqlite3.connect(db_path)
    try:
        otc = {row[1] for row in conn.execute("PRAGMA table_info(vhoadon_otc)")}
        etc = {row[1] for row in conn.execute("PRAGMA table_info(vhoadon_etc)")}
        customer = {row[1] for row in conn.execute("PRAGMA table_info(dms_khachhang)")}
    finally:
        conn.close()
    assert {"discount_rate", "doc_code"} <= otc
    assert {"discount_rate", "doc_code"} <= etc
    assert "is_active" in customer


def test_c11_va_m40_khong_bi_luat_rong_cuop_dinh_tuyen():
    assert nl2sql._required_tool_for_question(C11) == "get_top_customers"
    assert nl2sql._required_tool_for_question(M40) == "get_inventory_expiry_report"


def test_top_khach_tang_giam_duoc_tinh_rieng_tung_thang_tren_toan_tap(monkeypatch):
    raw = [
        {"month": "2026-07", "customer_code": "A", "employee_code": "NV1", "revenue": 100},
        {"month": "2026-07", "customer_code": "B", "employee_code": "NV2", "revenue": 50},
        {"month": "2026-08", "customer_code": "A", "employee_code": "NV1", "revenue": 50},
        {"month": "2026-08", "customer_code": "B", "employee_code": "NV2", "revenue": 150},
    ]
    monkeypatch.setattr(rt, "_q", lambda sql, params=(): raw)
    monkeypatch.setattr(rt, "_customer_names", lambda codes: {"A": "Khach A", "B": "Khach B"})

    result = rt._top_customer_changes_by_month(
        "2026-07-01", "2026-08-31", scope_channel="OTC")

    august = result["rows"][0]
    assert august["scope_revenue_delta"] == 50
    assert august["top_increases"][0]["customer_code"] == "B"
    assert august["top_increases"][0]["contribution_pct_of_total_change"] == 200
    assert august["top_decreases"][0]["customer_code"] == "A"
    assert august["top_decreases"][0]["employee_dms_code"] == "NV1"


def test_c11_co_cung_chuoi_thang_cho_ba_chieu_tap_trung(monkeypatch):
    monkeypatch.setattr(rt, "top_customers", lambda *args, **kwargs: [
        {"revenue": 30, "scope_revenue": 100}, {"revenue": 20, "scope_revenue": 100},
    ])
    monkeypatch.setattr(rt, "top_products", lambda *args, **kwargs: [
        {"revenue": 25}, {"revenue": 15},
    ])
    monkeypatch.setattr(rt, "revenue_by_region", lambda *args, **kwargs: [
        {"area": "MB", "revenue": 60}, {"area": "MN", "revenue": 30},
        {"area": "MT", "revenue": 10},
    ])

    result = rt._revenue_concentration_by_month("2026-07-01", "2026-08-31")

    assert [row["month"] for row in result["rows"]] == ["2026-07", "2026-08"]
    assert result["trend_available"] is True
    assert result["rows"][0]["top_10_customer_share_pct"] == 50
    assert result["rows"][0]["top_10_product_share_pct"] == 40
    assert result["rows"][0]["top_3_region_share_pct"] == 100
    assert result["rows"][0]["top_1_region_share_pct"] == 60


def test_kpi_nhieu_thang_dem_nguoi_co_target_va_tach_bon_moc(monkeypatch):
    monkeypatch.setattr(rt, "_q", lambda sql, params=(): [
        {"month": "2026-07", "employee_code": "T1", "position_code": "TDV", "area_code": "MB",
         "manager_code": "Q1", "actual": 70, "target": 100},
        {"month": "2026-07", "employee_code": "T2", "position_code": "TDV", "area_code": "MB",
         "manager_code": "Q1", "actual": 130, "target": 100},
        {"month": "2026-08", "employee_code": "T1", "position_code": "TDV", "area_code": "MB",
         "manager_code": "Q1", "actual": 90, "target": 100},
        {"month": "2026-08", "employee_code": "T2", "position_code": "TDV", "area_code": "MB",
         "manager_code": "Q1", "actual": 110, "target": 100},
    ])

    result = rt._kpi_thresholds_by_month("2026-08-31", 2, "manager")

    july, august = result["rows"]
    assert july["employees_with_target"] == 2
    assert (july["count_gate"], july["count_80"], july["count_100"], july["count_120"]) == (2, 1, 1, 1)
    assert (august["count_gate"], august["count_80"], august["count_100"], august["count_120"]) == (2, 2, 1, 0)
    assert august["pct_gate_rolling_3_month_avg"] == 100


def test_v14_dung_danh_muc_phan_cong_lam_mau_so(monkeypatch):
    def fake_q(sql, params=()):
        if sql.startswith("PRAGMA"):
            return [{"name": "is_active"}]
        if "total_rows" in sql:
            return [{"total_rows": 14, "populated_rows": 14}]
        if "assigned_customers" in sql:
            return [{"emp_code": "D1", "assigned_customers": 10},
                    {"emp_code": "D2", "assigned_customers": 4}]
        if "purchasing_customers" in sql:
            return [{"emp_code": "D1", "purchasing_customers": 2, "revenue": 200},
                    {"emp_code": "D2", "purchasing_customers": 4, "revenue": 800}]
        if "FROM dim_nhanvien" in sql:
            return [
                {"dmsid": "D1", "employee_code": "E1", "name": "NV 1", "position_code": "TDV", "area_code": "MB"},
                {"dmsid": "D2", "employee_code": "E2", "name": "NV 2", "position_code": "TDV", "area_code": "MB"},
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(rt, "_q", fake_q)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-08-31")
    monkeypatch.setattr(rt, "_get_team_dms_ids", lambda *args: ["D1", "D2"])

    result = rt.employee_assignment_coverage(scope_area_code="MB", scope_employee_code="Q1")

    by_code = {row["employee_code"]: row for row in result["rows"]}
    assert by_code["E1"]["assigned_customers"] == 10
    assert by_code["E1"]["purchasing_customers"] == 2
    assert by_code["E1"]["purchase_rate_pct"] == 20
    assert result["many_assigned_low_purchase_rate"][0]["employee_code"] == "E1"
    assert result["few_assigned_high_revenue_per_customer"][0]["employee_code"] == "E2"


def test_s77_s78_s87_tinh_chiet_khau_va_hang_tra_theo_thang(monkeypatch):
    def fake_q(sql, params=()):
        if sql.startswith("PRAGMA"):
            return [{"name": "discount_rate"}, {"name": "doc_code"}]
        if "total_rows" in sql:
            return [{"total_rows": 3, "populated_rows": 3}]
        return [
            {"month": "2026-08", "channel": "OTC", "area_code": "MB", "amount9": 100,
             "quantity": 1, "unit_price": 100, "discount_rate": 0.1, "doc_code": "BH", "order_key": "1"},
            {"month": "2026-08", "channel": "OTC", "area_code": "MB", "amount9": -20,
             "quantity": -1, "unit_price": 20, "discount_rate": 0, "doc_code": "HC", "order_key": "2"},
            {"month": "2026-08", "channel": "OTC", "area_code": "MB", "amount9": 0,
             "quantity": 3, "unit_price": 0, "discount_rate": 0, "doc_code": "BH", "order_key": "3"},
        ]

    monkeypatch.setattr(rt, "_q", fake_q)
    result = rt._sales_financial_quality_by_month("2026-08-01", "2026-08-31")

    row = result["rows_by_month_channel"][0]
    assert row["gross_revenue"] == 100
    assert row["discount_amount"] == 10
    assert row["return_adjustment"] == 20
    assert row["net_revenue_after_discount_and_returns"] == 70
    assert row["discount_rate_pct"] == 10
    assert row["return_adjustment_rate_pct"] == 20
    assert row["gift_quantity"] == 3
    assert row["gift_orders"] == 1
    assert row["total_orders"] == 3
    assert round(row["gift_order_share_pct"], 2) == 33.33
    assert result["gift_metric_status"].startswith("AVAILABLE")


def test_cot_hoa_don_moi_tao_nhung_chua_nap_lai_thi_fail_closed(monkeypatch):
    def fake_q(sql, params=()):
        if sql.startswith("PRAGMA"):
            return [{"name": "discount_rate"}, {"name": "doc_code"}]
        if "total_rows" in sql:
            return [{"total_rows": 20, "populated_rows": 0}]
        raise AssertionError(sql)

    monkeypatch.setattr(rt, "_q", fake_q)
    result = rt._sales_financial_quality_by_month(
        "2026-08-01", "2026-08-31", scope_channel="OTC")

    assert result["status"] == "SOURCE_GAP_INVOICE_QUALITY_COLUMNS_NOT_SYNCED"
    assert result["tables_with_unpopulated_new_columns"] == {"vhoadon_otc": 20}


def test_backend_tu_ep_mode_v14_va_khoang_nhieu_thang_c13(monkeypatch):
    seen = {}
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-08-31")
    monkeypatch.setattr(rt, "_sales_financial_quality_by_month", lambda *args: {
        "rows_by_month_channel": [{"month": "2026-08"}], "rows_by_month_area": []})

    def fake_order(**kwargs):
        seen.update(kwargs)
        return {"core_result_by_month": []}

    monkeypatch.setitem(rt.TEMPLATES, "check_order_timing", fake_order)
    result = rt.call_template(
        "check_order_timing", {"date_from": "2026-08-01", "date_to": "2026-08-31"},
        question="Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu?",
        scope_role="c_level",
    )

    assert result["ok"] is True
    assert seen["group_by_month"] is True
    assert seen["date_from"] == "2026-03-01"
    assert seen["date_to"] == "2026-08-31"

    seen.clear()

    def fake_coverage(**kwargs):
        seen.update(kwargs)
        return {"rows": []}

    monkeypatch.setitem(rt.TEMPLATES, "get_customer_product_coverage", fake_coverage)
    result = rt.call_template(
        "get_customer_product_coverage", {"mode": "customer", "as_of_date": "2026-08-31"},
        question="Ai có nhiều khách phụ trách nhưng tỷ lệ khách mua thấp, và ai ngược lại?",
        scope_role="regional_director", scope_area_code="MB",
    )

    assert result["ok"] is True
    assert seen["mode"] == "employee_assignment"
    assert seen["limit"] == 200
