# -*- coding: utf-8 -*-
"""Regression real-user 14/09/2026: context dung, du y va ngan gon."""
import datetime as dt
import json
import os
import sys


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import query_plan
import realtime_context


def _kpi_payload(row_count=24):
    rows = []
    for index in range(row_count):
        rows.append({
            "name": f"Nhân viên bán hàng số {index + 1}",
            "employee_code": f"NV{index + 1:03d}",
            "position_code": "TDV",
            "position_label": "Trình dược viên",
            "sales": 10_000_000 + index,
            "target": 135_000_000,
            "new_customers": index,
            "metric_snapshot": "2026-08-31",
            "manager_code": "QLV01",
            "manager_name": "Quản lý vùng",
            "pct": 10.123456 + index,
            "threshold": 65,
            "kpi_threshold": 80,
            "meets_kpi": False,
            "status": "🔴 Nguy hiểm",
            "meets_full_target": False,
        })
    return {
        "as_of": "2026-08-31",
        "total_employees": 146,
        "roster_employees": 147,
        "unassessed_count": 1,
        "missing_current_snapshot_count": 0,
        "roster_snapshots": {"current": "2026-08-31"},
        "unassessed_rows": [{"employee_code": "NV999", "name": "Chưa có target",
                             "reason": "missing_target", "sales": 1, "pct": None}],
        "unassessed_rows_truncated": False,
        "count_below_target": row_count,
        "count_above_target": 122,
        "count_kpi_achieved": 66,
        "kpi_threshold_pct": 80,
        "count_full_target": 30,
        "full_target_pct": 100,
        "threshold_summary": [{"threshold_pct": 65, "count": 122, "total": 146}],
        "below_kpi_by_manager": [{
            "manager_code": "QLV01", "manager_name": "Quản lý vùng",
            "count_below_kpi": row_count, "employees": rows,
        }],
        "rows": rows,
    }


def test_kpi_payload_giu_du_24_nguoi_va_nam_duoi_tran_6000_ky_tu():
    encoded = nl2sql._serialize_payload_for_model(
        "get_employee_kpi", _kpi_payload(), "danh sách TDV dưới 65% tháng 8"
    )
    compact = json.loads(encoded)

    assert len(encoded) <= nl2sql.MAX_PAYLOAD_CHARS
    assert compact["rows_returned"] == 24
    assert len(compact["rows"]) == 24
    assert compact["rows"][-1]["employee_code"] == "NV024"
    assert compact["count_below_target"] == 24
    assert "below_kpi_by_manager" not in compact


def test_payload_lon_bat_ky_van_la_json_hop_le_va_giu_tong():
    payload = {
        "total_count": 100,
        "total_revenue": 12_345_678_900,
        "rows": [
            {"code": f"KH{i:03d}", "name": "Khách hàng " + ("rất dài " * 20), "revenue": i}
            for i in range(100)
        ],
    }

    encoded = nl2sql._serialize_payload_for_model(
        "get_top_customers", payload, "danh sách tất cả khách hàng"
    )
    decoded = json.loads(encoded)

    assert len(encoded) <= nl2sql.MAX_PAYLOAD_CHARS
    assert decoded["total_count"] == 100
    assert decoded["total_revenue"] == 12_345_678_900
    assert decoded["_model_view"]["full_result_available_for_download"] is True
    plain = encoded.lower()
    assert "bi cat" not in plain and "bị cắt" not in plain and "truncated" not in plain


def test_payload_nhieu_truong_vo_huong_van_khong_vuot_ngan_sach():
    payload = {
        "total_count": 321,
        **{f"field_{index:04d}": index for index in range(2_000)},
    }

    encoded = nl2sql._serialize_payload_for_model("generic_tool", payload, "báo cáo tổng hợp")
    decoded = json.loads(encoded)

    assert len(encoded) <= nl2sql.MAX_PAYLOAD_CHARS
    assert decoded["total_count"] == 321
    assert decoded["_model_view"]["mode"] == "summary_only"


def test_danh_sach_chung_tu_nang_limit_nhung_top_n_giu_nguyen():
    all_args = nl2sql._normalize_tool_input_for_question(
        "get_customers_silent", {"limit": 15}, "danh sách tất cả khách hàng im lặng"
    )
    top_args = nl2sql._normalize_tool_input_for_question(
        "get_customers_silent", {"limit": 10}, "top 10 khách hàng im lặng"
    )

    assert all_args["limit"] == 200
    assert top_args["limit"] == 10


def test_lop_cuoi_loai_thong_diep_gioi_han_ky_thuat():
    plan = query_plan.build_query_plan(
        "danh sách khách hàng im lặng",
        query_id="unit-no-truncation-wording",
        scope_role="c_level",
        scope_area_code=None,
        scope_employee_code=None,
        scope_channel=None,
        max_rounds=3,
        max_tools_per_round=3,
        max_unique_tools=5,
        request_timeout_seconds=60,
    )
    answer = plan.finalize_answer(
        "Có 100 khách hàng.\nDữ liệu bị cắt bớt do giới hạn hiển thị.\n"
        "Còn 85 khách chưa hiển thị.\nTải Excel để xem danh sách chi tiết."
    )

    assert "Có 100 khách hàng." in answer
    assert "Tải Excel" in answer
    assert "cắt" not in answer.lower()
    assert "chưa hiển thị" not in answer.lower()


def test_danh_sach_duoi_nguong_tu_nang_limit_va_loc_dung_mot_lan():
    args = nl2sql._normalize_tool_input_for_question(
        "get_employee_kpi",
        {"as_of_date": "2026-08-31", "limit": 15},
        "những nhân viên bán hàng không đạt KPI 60% của tháng 8",
    )

    assert args["limit"] == 200
    assert args["filter"] == "below_target"
    assert args["position_code"] == "TDV"


def test_cac_cau_real_user_duoc_ep_vao_dung_tool_ngay_vong_dau():
    expected = {
        "báo cáo hoàn thành của tháng 8": "get_revenue_tree",
        "doanh số của ngày 26 và 27/8 của 3 miền như nào": "get_revenue_by_region",
        "phát sinh 10 ngày cuối tháng 8 của 3 miền": "get_revenue_by_region",
        "những nhân viên bán hàng không đạt KPI 60% của tháng 8": "get_employee_kpi",
        "danh sách dưới 65 %": "get_employee_kpi",
    }
    for question, tool_name in expected.items():
        assert nl2sql._required_tool_for_question(question) == tool_name


def test_cau_noi_danh_sach_duoi_65_khong_bi_hieu_nham_thanh_doanh_thu():
    domains = query_plan.infer_domains("danh sách dưới 65 %")
    assert [item["domain"] for item in domains] == ["kpi"]


def test_thang_khong_ghi_nam_duoc_hieu_la_lan_gan_nhat():
    today = dt.date.today()
    expected_year = today.year if 8 <= today.month else today.year - 1

    planned = query_plan.infer_period("danh sách dưới 65% tháng 8")
    resolved = realtime_context.resolve_relative_date("tháng 8")

    assert planned["date_from"] == f"{expected_year}-08-01"
    assert planned["date_to"] == f"{expected_year}-08-31"
    assert resolved["start_date"] == f"{expected_year}-08-01"
    assert resolved["end_date"] == f"{expected_year}-08-31"


def test_nguong_cua_khach_hang_khong_bi_dinh_tuyen_nham_sang_kpi():
    question = "danh sách khách hàng có tỷ lệ mua lại dưới 65%"
    assert nl2sql._required_tool_for_question(question) != "get_employee_kpi"
    assert "customer" in {item["domain"] for item in query_plan.infer_domains(question)}
