import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))

from query_plan import build_query_plan  # noqa: E402


def _plan(question="So sánh doanh thu, KPI và công nợ tháng 7/2026 theo miền", query_id="q1"):
    return build_query_plan(
        question,
        query_id=query_id,
        scope_role="c_level",
        scope_area_code=None,
        scope_employee_code=None,
        scope_channel=None,
        max_rounds=10,
        max_tools_per_round=5,
        max_unique_tools=12,
        request_timeout_seconds=110,
    )


def test_query_plan_has_required_structure_period_and_request_local_scope():
    plan = _plan()
    data = plan.as_dict()

    assert data["plan_id"] == "plan-q1"
    assert data["metrics"] == ["revenue", "kpi", "receivables", "overdue"]
    assert data["period"] == {
        "date_from": "2026-07-01",
        "date_to": "2026-07-31",
        "label": "07/2026",
    }
    assert data["scope"]["role"] == "c_level"
    assert {step["domain"] for step in data["steps"]} == {"revenue", "kpi", "debt"}
    assert set(data["dependencies"]) == {step["step_id"] for step in data["steps"]}
    assert {item["rule"] for item in data["reconciliation_rules"]} == {
        "revenue_totals", "team_employee_rollup", "debt_aging",
    }


def test_two_query_plans_do_not_share_runtime_state():
    first = _plan(query_id="first")
    second = _plan(query_id="second")
    key = "get_revenue_by_channel:{}"
    first.start_tool("get_revenue_by_channel", {}, key)
    first.finish_tool(
        key,
        ok=True,
        payload={
            "otc": {"revenue": 40},
            "etc": {"revenue": 60},
            "total": {"revenue": 100},
        },
        source="template:get_revenue_by_channel",
        duration_ms=5,
        timeout_seconds=40,
    )

    assert first.sources == ["template:get_revenue_by_channel"]
    assert second.sources == []
    assert second.steps[0].status == "pending"


def test_reconcile_revenue_and_debt_from_real_payload_shapes():
    plan = _plan()
    revenue_key = "revenue"
    plan.start_tool("get_revenue_by_channel", {}, revenue_key)
    plan.finish_tool(
        revenue_key,
        ok=True,
        payload={
            "otc": {"revenue": 39_327_016_119},
            "etc": {"revenue": 35_508_451_204},
            "total": {"revenue": 74_835_467_323},
        },
        source="template:get_revenue_by_channel",
        duration_ms=10,
        timeout_seconds=40,
    )
    debt_key = "debt"
    plan.start_tool("get_receivables_overview", {}, debt_key)
    plan.finish_tool(
        debt_key,
        ok=True,
        payload={
            "receivable_status": "ok",
            "total_overdue": 100,
            "overdue_1_15": 10,
            "overdue_15_30": 20,
            "overdue_30_45": 30,
            "overdue_gt_45": 40,
        },
        source="template:get_receivables_overview",
        duration_ms=10,
        timeout_seconds=40,
    )

    statuses = {item.rule: item.status for item in plan.reconciliation_rules}
    assert statuses["revenue_totals"] == "passed"
    assert statuses["debt_aging"] == "passed"


def test_composite_promotion_tool_completes_promotion_customer_and_product_steps():
    plan = _plan(
        "Đánh giá CTKM theo khách hàng, sản phẩm và doanh thu tháng 12/2025",
        query_id="promo",
    )
    key = "promo"
    plan.start_tool("get_promotion_effectiveness", {"limit": 20}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "status": "ok",
            "programs": [{"program_code": "KM01"}],
            "interpretation_note": "Không cộng ngang doanh thu các chương trình.",
        },
        source="template:get_promotion_effectiveness",
        duration_ms=10,
        timeout_seconds=40,
    )
    plan.finalize()

    domain_status = {step.domain: step.status for step in plan.steps}
    assert domain_status["promotion"] == "completed"
    assert domain_status["customer"] == "completed"
    assert domain_status["product"] == "completed"
    assert plan.status == "completed"


def test_composite_uat_tools_complete_all_inferred_domains_without_phantom_pending_steps():
    cases = [
        ("Tăng trưởng doanh thu đến từ khách mở mới hay khách hiện hữu", "get_customer_movement"),
        ("SKU tồn kho cận date và chậm luân chuyển nào cần xử lý", "get_inventory_expiry_report"),
        ("Doanh thu/khách và sản lượng từng sản phẩm thay đổi", "get_customer_product_coverage"),
    ]
    for index, (question, tool) in enumerate(cases):
        plan = _plan(question, query_id=f"composite-{index}")
        key = f"{tool}-{index}"
        plan.start_tool(tool, {}, key)
        payload = {"status": "ok"}
        if tool == "get_customer_movement":
            payload["summary_all_customers"] = {
                "total_revenue_delta": 100, "reconciled_delta": 100,
            }
        elif tool == "get_customer_product_coverage":
            payload["reconciliation"] = {"passed": True}
        plan.finish_tool(
            key, ok=True, payload=payload, source=f"template:{tool}",
            duration_ms=5, timeout_seconds=40,
        )
        plan.finalize()
        assert plan.status == "completed", (question, plan.as_dict())


def test_failed_source_produces_structured_partial_answer_without_guessing():
    plan = _plan("So sánh doanh thu và công nợ tháng 7/2026", query_id="partial")
    revenue_key = "revenue"
    plan.start_tool("get_revenue_by_channel", {}, revenue_key)
    plan.finish_tool(
        revenue_key,
        ok=True,
        payload={
            "otc": {"revenue": 40}, "etc": {"revenue": 60}, "total": {"revenue": 100}
        },
        source="template:get_revenue_by_channel",
        duration_ms=5,
        timeout_seconds=40,
    )
    debt_key = "debt"
    plan.start_tool("get_receivables_overview", {}, debt_key)
    plan.finish_tool(
        debt_key,
        ok=False,
        payload={"error": "SIMULATED_SOURCE_FAILURE"},
        source="template:get_receivables_overview",
        duration_ms=5,
        timeout_seconds=40,
    )
    plan.finalize()
    answer = plan.finalize_answer("Doanh thu đã được kiểm chứng là 100 đồng.")

    assert plan.status == "partial"
    assert "### Phần chưa thể kiểm chứng" in answer
    assert "SIMULATED_SOURCE_FAILURE" in answer
    assert "Không suy đoán số" in answer


def test_request_timeout_is_measured_from_plan_start():
    plan = _plan(query_id="timeout")
    plan.request_timeout_seconds = 0.01
    plan._started_monotonic = time.monotonic() - 1
    assert plan.expired() is True
    assert plan.remaining_seconds() == 0


def test_multi_period_and_vietnamese_bat_thuong_do_not_trigger_salary_false_positive():
    plan = _plan(
        "Phát hiện bất thường khi doanh thu và KPI tháng 6 và tháng 7/2026 không khớp",
        query_id="periods",
    )
    assert [step.domain for step in plan.steps] == ["revenue", "kpi"]
    assert plan.period["label"] == "06/2026 vs 07/2026"
    assert len(plan.period["periods"]) == 2


def test_san_luong_khong_bi_hieu_nham_thanh_luong_nhan_su():
    plan = _plan("Doanh thu/khách và sản lượng từng sản phẩm thay đổi", query_id="quantity")
    assert "salary" not in {step.domain for step in plan.steps}


def test_timestamp_question_uses_one_multisource_freshness_step():
    plan = _plan(
        "So sánh timestamp và business date của doanh thu, KPI, lương và khuyến mãi",
        query_id="freshness",
    )
    assert [step.domain for step in plan.steps] == ["freshness"]
    assert [item.rule for item in plan.reconciliation_rules] == ["source_freshness"]


def test_one_raw_sql_can_complete_multiple_domains_when_sql_really_joins_them():
    plan = _plan(
        "Tìm khách hàng giảm mua và ảnh hưởng doanh thu tháng 7/2026",
        query_id="raw",
    )
    args = {"sql": "SELECT CustomerCode, SUM(Amount9) FROM dbo.vHoaDonTotal GROUP BY CustomerCode"}
    key = "raw"
    plan.start_tool("query_sql_server", args, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={"columns": ["CustomerCode", "Revenue"], "rows": [["KH1", 100]]},
        source="bravo",
        duration_ms=10,
        timeout_seconds=40,
    )
    statuses = {step.domain: step.status for step in plan.steps}
    assert statuses == {"revenue": "completed", "customer": "completed"}
