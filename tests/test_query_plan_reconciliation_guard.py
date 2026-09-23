"""Regression gates for contradictory evidence; all model responses are fake."""
from types import SimpleNamespace

import pytest

from test_query_plan import _plan


DATES = {"date_from": "2026-08-01", "date_to": "2026-08-31"}
MATCHED = {"otc": {"revenue": 40}, "etc": {"revenue": 60}, "total": {"revenue": 100}}
MISMATCHED = {"otc": {"revenue": 40}, "etc": {"revenue": 60}, "total": {"revenue": 150}}
UNSAFE = "Mọi số liệu đã khớp. Doanh thu chắc chắn là 150 đồng, không có bất thường."


def add(plan, tool, payload, args=None):
    args = dict(DATES if args is None else args)
    key = f"{tool}:{len(plan.steps)}:{len(plan._runtime_steps)}"
    plan.start_tool(tool, args, key)
    plan.finish_tool(key, ok=True, payload=payload, source=f"template:{tool}",
                     duration_ms=1, timeout_seconds=40)


def revenue_rule(plan):
    return next(item for item in plan.reconciliation_rules if item.rule == "revenue_totals")


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("other_tool,other_payload", [
    ("get_revenue_by_region", [{"area": "MB", "revenue": 150}]),
    ("get_customer_movement", {"summary_all_customers": {"total_revenue_delta": 10, "reconciled_delta": 10}}),
    ("get_customer_product_coverage", {"reconciliation": {"passed": True}}),
])
def test_one_matching_check_cannot_erase_another_mismatch(reverse, other_tool, other_payload):
    plan = _plan("Doanh thu tháng 8/2026")
    calls = [("get_revenue_by_channel", MISMATCHED), (other_tool, other_payload)]
    for tool, payload in reversed(calls) if reverse else calls:
        add(plan, tool, payload)
    plan.finalize()
    assert all(step.status == "completed" for step in plan.steps)
    assert revenue_rule(plan).status == "failed"
    assert "tổng báo cáo = 150.00" in revenue_rule(plan).detail
    assert plan.status == "partial"


def test_later_month_does_not_erase_earlier_month_mismatch():
    plan = _plan("Doanh thu tháng 7 và 8/2026")
    july = {"date_from": "2026-07-01", "date_to": "2026-07-31"}
    add(plan, "get_revenue_by_channel", MISMATCHED, july)
    add(plan, "get_revenue_by_channel", MATCHED)
    plan.finalize()
    assert revenue_rule(plan).status == "failed"
    assert "2026-07-01 đến 2026-07-31" in plan.finalize_answer(UNSAFE)
    assert UNSAFE not in plan.finalize_answer(UNSAFE)


@pytest.mark.parametrize("draft", [UNSAFE, "**Giới hạn kết luận:** " + UNSAFE])
def test_completed_tools_with_failed_check_replace_unsafe_model_answer(draft):
    plan = _plan("Doanh thu tháng 8/2026")
    add(plan, "get_revenue_by_channel", MISMATCHED)
    plan.finalize()
    assert all(step.status == "completed" for step in plan.steps)
    answer = plan.finalize_answer(draft)
    assert "### Chưa thể xác nhận số liệu" in answer
    assert "tổng báo cáo = 150.00" in answer
    assert "Mọi số liệu đã khớp" not in answer
    assert "chắc chắn là 150" not in answer
    assert answer == plan.finalize_answer(answer)


def test_timeout_does_not_call_inconsistent_data_verified():
    plan = _plan("Doanh thu tháng 8/2026")
    add(plan, "get_revenue_by_channel", MISMATCHED)
    plan.finalize(limit_reached=True)
    assert "Chưa thể xác nhận số liệu" in plan.timeout_answer()
    assert "Đã kiểm chứng:" not in plan.timeout_answer()


@pytest.mark.parametrize("special_renderer", ["m20", "c29"])
def test_special_renderers_cannot_bypass_failed_reconciliation(special_renderer):
    question = ("Doanh thu, khách mới, tái kích hoạt, ngừng mua từng tháng" if special_renderer == "c29"
                else "Doanh thu và KPI đội ngũ")
    plan = _plan(question)
    if special_renderer == "m20":
        plan.scope["role"] = "regional_director"
        add(plan, "get_employee_kpi", {
            "kpi_source": "fact_thongketinhluong", "position_code": "TDV",
            "comparison_threshold_summary": {
                "denominator_all_tdv": 95, "employees_with_target": 91,
                "unassessed_missing_target": 4, "at_least_100_pct": 0,
                "at_least_80_pct": 1, "at_least_65_pct": 3, "below_65_pct": 88,
            },
        })
    else:
        add(plan, "get_customer_lifecycle_summary", {
            "invoice_lifecycle_series": {"months": [{"month": "2026-08", "invoice_active_customers": 5}]},
        })
    add(plan, "get_revenue_by_channel", MISMATCHED)
    plan.finalize()
    assert "Chưa thể xác nhận số liệu" in plan.finalize_answer(UNSAFE)


@pytest.mark.parametrize("region_dates", [{}, {"date_from": "2026-07-01", "date_to": "2026-07-31"}])
def test_different_or_unknown_periods_are_not_compared(region_dates):
    plan = _plan("Doanh thu theo miền tháng 8/2026")
    add(plan, "get_revenue_by_channel", {**MATCHED, **DATES})
    add(plan, "get_revenue_by_region", [{"area": "MB", "revenue": 40}], region_dates)
    plan.finalize()
    # Passed here only means OTC + ETC = total. No cross-period region check was performed.
    assert revenue_rule(plan).status == "passed"
    assert "Tổng vùng" not in revenue_rule(plan).detail
    assert plan.finalize_answer("Số từng kỳ được trình bày riêng.") == "Số từng kỳ được trình bày riêng."


@pytest.mark.parametrize("channel,total", [("OTC", 40), ("ETC", 60)])
def test_regional_channel_is_compared_with_matching_channel_total(channel, total):
    plan = _plan("Doanh thu theo miền tháng 8/2026")
    add(plan, "get_revenue_by_channel", MATCHED)
    add(plan, "get_revenue_by_region", [{"area": "MB", "revenue": total}], {**DATES, "channel": channel})
    plan.finalize()
    assert revenue_rule(plan).status == "passed"
    assert plan.status == "completed"


def test_server_channel_scope_overrides_model_requested_channel():
    plan = _plan("Doanh thu theo miền tháng 8/2026")
    plan.scope["channel"] = "ETC"
    scoped = {"otc": {"revenue": 0}, "etc": {"revenue": 60}, "total": {"revenue": 60}}
    add(plan, "get_revenue_by_channel", scoped)
    add(plan, "get_revenue_by_region", [{"area": "MB", "revenue": 60}], {**DATES, "channel": "OTC"})
    assert revenue_rule(plan).status == "passed"


def test_matching_total_does_not_mask_genuine_region_mismatch():
    plan = _plan("Doanh thu theo miền tháng 8/2026")
    add(plan, "get_revenue_by_channel", MATCHED)
    add(plan, "get_revenue_by_region", [{"area": "MB", "revenue": 80}])
    plan.finalize()
    assert revenue_rule(plan).status == "failed"
    assert "80.00" in plan.finalize_answer(UNSAFE)
    assert UNSAFE not in plan.finalize_answer(UNSAFE)


def test_corrected_evidence_for_same_check_can_clear_its_failure():
    plan = _plan("Doanh thu tháng 8/2026")
    add(plan, "get_revenue_by_channel", MISMATCHED)
    add(plan, "get_revenue_by_channel", MATCHED)
    plan.finalize()
    assert revenue_rule(plan).status == "passed"
    assert plan.status == "completed"
    assert plan.finalize_answer("Tổng doanh thu: 100 đồng.") == "Tổng doanh thu: 100 đồng."


def test_all_matching_checks_keep_answer_and_request_state_is_separate():
    plan = _plan("Doanh thu tháng 8/2026")
    add(plan, "get_revenue_by_channel", MATCHED)
    add(plan, "get_revenue_by_region", [{"area": "MB", "revenue": 100}])
    plan.finalize()
    assert plan.status == "completed"
    assert plan.finalize_answer("Tổng doanh thu: 100 đồng.") == "Tổng doanh thu: 100 đồng."
    assert revenue_rule(_plan("Doanh thu tháng 8/2026", query_id="another")).status == "pending"
    assert "_evidence_args" not in plan.as_dict()
    assert "_reconciliation_checks" not in plan.as_dict()


@pytest.mark.parametrize("streaming", [False, True])
def test_api_only_emits_and_saves_guarded_answer(monkeypatch, streaming):
    import nl2sql
    from test_data_freshness import _patch_nl2sql_runtime

    class Stream:
        def __init__(self, message):
            self.message = message

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            for block in self.message.content:
                if block.type == "text":
                    yield SimpleNamespace(type="text", text=block.text)

        def get_final_message(self):
            return self.message

    class Messages:
        calls = 0

        def create(self, **kwargs):
            self.calls += 1
            content = ([SimpleNamespace(type="tool_use", id="guard-tool", name="get_revenue_by_channel", input=DATES)]
                       if self.calls == 1 else [SimpleNamespace(type="text", text=UNSAFE)])
            return SimpleNamespace(content=content, usage=SimpleNamespace())

        def stream(self, **kwargs):
            return Stream(self.create(**kwargs))

    appended = []
    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=Messages()), appended)
    monkeypatch.setattr(nl2sql, "_static_system_prompt", lambda: "test")
    monkeypatch.setattr(nl2sql, "_dynamic_context_note", lambda *args: "test")
    monkeypatch.setattr(nl2sql, "call_template", lambda *args, **kwargs: {"ok": True, "result": MISMATCHED})
    kwargs = dict(session_id="unit-answer-guard", username="unit-answer-guard", scope_role="c_level")
    if streaming:
        events = list(nl2sql.ask_stream("Doanh thu tháng 8/2026", **kwargs))
        result = events[-1]
        emitted = "".join(event["text"] for event in events if event["type"] == "text_delta")
        assert emitted == result["answer"]
    else:
        result = nl2sql.ask("Doanh thu tháng 8/2026", **kwargs)
    assert result["answer"] == appended[-1][2]
    assert "Chưa thể xác nhận số liệu" in result["answer"]
    assert UNSAFE not in result["answer"]
    assert result["query_plan"]["status"] == "partial"
