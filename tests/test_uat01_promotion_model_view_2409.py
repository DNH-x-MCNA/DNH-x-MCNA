import json
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import nl2sql  # noqa: E402
from query_plan import build_query_plan  # noqa: E402


def test_uat01_model_sees_all_programs_and_both_same_code_rows():
    """UAT 24/09: a generic 10k-character trim hid 13/21 programs from the model."""
    programs = []
    for index in range(21):
        code = ("Q4.2025_NHOM_BOPHE_SIRO_" if index in (11, 20)
                else f"PROGRAM_{index:02d}_2025")
        programs.append({
            "program_id": 118_900 + index,
            "program_code": code,
            "program_name": "Chương trình khuyến mãi tháng 12 năm 2025 " + str(index),
            "associated_revenue": 12_000_000_000 - index * 400_000_000,
            "participating_customers": 600 - index * 8,
            "orders": 4_251 if index == 11 else (644 if index == 20 else 900 - index * 10),
            "invoiced_orders": 3_722 if index == 11 else (586 if index == 20 else 800 - index * 10),
            "average_revenue_per_invoiced_order": 2_000_000,
            "configured_product_count": 5,
            "gift_product_count": 1,
            "paid_product_occurrences": 10,
            "program_from": "2025-10-01",
            "program_to": "2025-12-31",
            "program_month_count": 3,
            "program_spans_multiple_months": True,
            "report_covers_full_program": False,
            "period_coverage_note": "Báo cáo chỉ tính phần tháng 12 của chương trình.",
            "code_is_ambiguous": index in (11, 20),
            "same_code_programs": [],
        })
    data = {
        "status": "ok", "period": {"from": "2025-12-01", "to": "2025-12-31"},
        "scope_area_code": "MB", "scope_note": "Chỉ Miền Bắc, không phải toàn quốc.",
        "promotion_link_coverage_to": "2026-01-09", "program_count_returned": 21,
        "same_code_programs_to_distinguish": [
            {key: row[key] for key in ("program_id", "program_code", "program_name", "orders", "invoiced_orders", "associated_revenue")}
            for row in (programs[11], programs[20])
        ],
        "programs": programs,
    }

    serialized = nl2sql._serialize_payload_for_model(
        "get_promotion_effectiveness", {"ok": True, "du_lieu": data},
        "Khuyến mãi nhiều khách tham gia nhưng không tạo tăng trưởng; chương trình nào uplift tốt",
    )
    model_data = json.loads(serialized)["du_lieu"]
    rows = model_data["programs"]

    assert len(serialized) <= nl2sql.MAX_PAYLOAD_CHARS
    assert len(rows) == model_data["program_count_returned"] == 21
    assert {(row["program_id"], row["orders"], row["invoiced_orders"])
            for row in rows if row["program_code"] == "Q4.2025_NHOM_BOPHE_SIRO_"} == {
                (118_911, 4_251, 3_722), (118_920, 644, 586),
            }
    assert model_data["scope_area_code"] == "MB"
    assert model_data["promotion_link_coverage_to"] == "2026-01-09"


def test_uat01_answer_cannot_hide_invoiced_orders_or_same_code_programs():
    plan = build_query_plan(
        "Khuyến mãi nhiều khách tham gia nhưng không tạo tăng trưởng; chương trình nào uplift tốt",
        query_id="uat01", scope_role="regional_director", scope_area_code="MB",
        scope_employee_code=None, scope_channel="OTC", max_rounds=10,
        max_tools_per_round=5, max_unique_tools=12, request_timeout_seconds=110,
    )
    programs = [
        {"program_id": 118969, "program_code": "Q4.2025_NHOM_BOPHE_SIRO_",
         "program_name": "Nhóm Bổ phế siro mua 10", "participating_customers": 100,
         "orders": 4251, "invoiced_orders": 3722, "associated_revenue": 10_757_944_139},
        {"program_id": 118972, "program_code": "Q4.2025_NHOM_BOPHE_SIRO_",
         "program_name": "Nhóm Bổ phế siro mua 5", "participating_customers": 20,
         "orders": 644, "invoiced_orders": 586, "associated_revenue": 1_261_462_541},
    ]
    key = "promotion"
    plan.start_tool("get_promotion_effectiveness", {}, key)
    plan.finish_tool(
        key, ok=True,
        payload={"status": "ok", "period": {"from": "2025-12-01", "to": "2025-12-31"},
                 "scope_area_code": "MB", "program_count_returned": 2,
                 "promotion_link_coverage_to": "2026-01-09",
                 "interpretation_note": "Không kết luận uplift khi chưa có nhóm đối chứng.",
                 "programs": programs},
        source="template:get_promotion_effectiveness", duration_ms=10, timeout_seconds=40,
    )
    plan.finalize()

    answer = plan.finalize_answer("Tôi chỉ liệt kê một chương trình tiêu biểu.")
    assert "118969" in answer and "118972" in answer
    assert "4.251" in answer and "644" in answer
    assert "3.722" in answer and "586" in answer
    assert "Miền MB" in answer
    assert "không thể kết luận uplift" in answer.lower()
