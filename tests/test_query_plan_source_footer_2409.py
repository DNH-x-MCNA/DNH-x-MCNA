import sys
from pathlib import Path

import pytest


BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from query_plan import build_query_plan  # noqa: E402


def _plan(question):
    return build_query_plan(
        question, query_id="uat-2409", scope_role="c_level", scope_area_code=None,
        scope_employee_code=None, scope_channel=None, max_rounds=10,
        max_tools_per_round=5, max_unique_tools=12, request_timeout_seconds=110,
    )


@pytest.mark.parametrize("question,tool,args,payload", [
    (
        "Mở nhiều khách mới nhưng doanh thu trên khách và tỷ lệ mua lại thấp",
        "get_new_customer_list", {"mode": "quality"},
        {"mode": "quality", "tong_khach_moi_duy_nhat": 627,
         "by_area": [{"area_code": "MB", "doanh_thu_binh_quan_khach_moi": 100,
                      "ty_le_mua_lai_khach_moi_pct": 20}]},
    ),
    (
        "Danh sách khách hàng phát sinh 3 tháng nhưng chưa đạt KPI tái đơn",
        "get_reorder_pending_customers", {},
        {"total_pending_customers": 2, "rows": [{"customer_code": "C1"}],
         "kpi_tai_don_theo_nhan_vien": [{"employee_code": "E1", "ty_le_dat_kpi_tai_don_pct": 70}]},
    ),
    (
        "Doanh số tháng này theo các nhóm hàng",
        "get_top_products", {"group_by": "category"},
        {"products": [{"group_name": "DM1", "revenue": 100}]},
    ),
    (
        "Doanh số sản phẩm DM1, DM2, DM3, trọng tâm",
        "get_top_products", {},
        {"products": [{"item_code": "DM1", "revenue": 100}]},
    ),
    (
        "Doanh số sản phẩm DM1, DM2, DM3, trọng tâm",
        "get_focus_product_kpi", {},
        {"products": [{"item_code": "DM1", "actual": 100, "target": 120}]},
    ),
])
def test_one_matching_composite_tool_does_not_claim_source_was_never_called(
        question, tool, args, payload):
    plan = _plan(question)
    plan.start_tool(tool, args, "real-tool")
    plan.finish_tool("real-tool", ok=True, payload=payload, source=f"template:{tool}",
                     duration_ms=10, timeout_seconds=40)
    plan.finalize()
    answer = plan.finalize_answer("Đã trả số liệu từ nguồn tương ứng.")

    assert plan.status == "completed"
    assert all(step.status == "completed" for step in plan.steps)
    assert "Model chưa gọi nguồn" not in answer
    assert "### Phần chưa thể kiểm chứng" not in answer


def test_really_uncalled_independent_source_still_requires_caveat():
    plan = _plan("So sánh doanh thu và công nợ tháng 8/2026")
    plan.start_tool("get_revenue_by_channel", {}, "revenue")
    plan.finish_tool("revenue", ok=True,
                     payload={"otc": {"revenue": 40}, "etc": {"revenue": 60},
                              "total": {"revenue": 100}},
                     source="template:get_revenue_by_channel", duration_ms=10, timeout_seconds=40)
    plan.finalize()

    assert plan.status == "partial"
    assert "đối chiếu công nợ" in plan.finalize_answer("Doanh thu là 100 đồng.").lower()


def test_new_customer_list_mode_does_not_claim_revenue_per_customer_was_checked():
    question = "Mở nhiều khách mới nhưng doanh thu trên khách và tỷ lệ mua lại thấp"
    plan = _plan(question)
    plan.start_tool("get_new_customer_list", {"mode": "list"}, "list")
    plan.finish_tool("list", ok=True, payload={"rows": [{"customer_code": "C1"}]},
                     source="template:get_new_customer_list", duration_ms=10,
                     timeout_seconds=40)
    plan.finalize()

    assert plan.status == "partial"
    assert "Đối chiếu doanh thu" in plan.finalize_answer("Có 1 khách mới.")
