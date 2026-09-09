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


def test_reconcile_revenue_rollup_thieu_khong_duoc_danh_dau_passed():
    plan = _plan()
    key = "rollup"
    plan.start_tool("get_revenue_reconciliation", {}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "coverage_pct": 72.4,
            "reconciliation_status": "incomplete_needs_investigation",
            "warning": "CHUA DOI SOAT KHOP: can dieu tra.",
        },
        source="template:get_revenue_reconciliation",
        duration_ms=10,
        timeout_seconds=40,
    )

    revenue_rule = next(item for item in plan.reconciliation_rules if item.rule == "revenue_totals")
    assert revenue_rule.status == "failed"
    assert "CHUA DOI SOAT KHOP" in revenue_rule.detail


def test_reconcile_revenue_rollup_chi_pass_khi_nam_trong_dung_sai_hai_phia():
    for coverage, expected in ((72.4, "failed"), (100.2, "passed"), (101.0, "failed")):
        plan = _plan(query_id=f"coverage-{coverage}")
        key = f"rollup-{coverage}"
        plan.start_tool("get_revenue_reconciliation", {}, key)
        plan.finish_tool(
            key,
            ok=True,
            payload={"coverage_pct": coverage},
            source="template:get_revenue_reconciliation",
            duration_ms=10,
            timeout_seconds=40,
        )
        revenue_rule = next(item for item in plan.reconciliation_rules if item.rule == "revenue_totals")
        assert revenue_rule.status == expected


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
        ("SKU khách đang cần nhưng kho thiếu là gì; đơn/doanh thu nào có nguy cơ mất vì thiếu hàng?",
         "get_inventory_expiry_report"),
        ("SKU tồn cao/chậm bán/cận date trong phạm vi vùng là gì; khách nào phù hợp để xử lý tồn?",
         "get_inventory_expiry_report"),
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


def test_c28_assignment_change_khong_tao_buoc_kpi_gia():
    question = ("Nếu loại ảnh hưởng của thay đổi địa bàn, chuyển nhân viên và chuyển khách, "
                "tăng trưởng thực của từng đơn vị còn bao nhiêu?")
    plan = _plan(question, query_id="c28-assignment-change")

    assert {step.domain for step in plan.steps} == {"customer"}
    assert all(step.domain != "kpi" for step in plan.steps)

    key = "coverage-c28"
    plan.start_tool("get_customer_product_coverage", {"mode": "assignment_change"}, key)
    plan.finish_tool(
        key, ok=True,
        payload={"status": "PARTIAL_SOURCE_LIMIT", "reconciliation": {"passed": True}},
        source="template:get_customer_product_coverage", duration_ms=5, timeout_seconds=40,
    )
    plan.finalize()
    assert plan.status == "completed"


def test_c29_lifecycle_khong_bi_hieu_nham_la_kpi_nhan_su():
    question = ("Số khách hoạt động, khách mới, khách mua lại, khách tái kích hoạt và "
                "khách ngừng mua từng tháng là bao nhiêu?")
    plan = _plan(question, query_id="c29-lifecycle")

    assert {step.domain for step in plan.steps} == {"customer"}


def test_inventory_tool_khong_duoc_danh_dau_xong_doanh_thu_o_cau_hoi_tong_hop_chung():
    plan = _plan(
        "Tổng doanh thu và giá trị tồn kho hiện tại là bao nhiêu?",
        query_id="revenue-inventory-separate",
    )
    revenue = next(step for step in plan.steps if step.domain == "revenue")
    inventory = next(step for step in plan.steps if step.domain == "inventory")

    assert "get_inventory_expiry_report" not in revenue.tool_hints
    assert "get_inventory_expiry_report" in inventory.tool_hints


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
    assert "Giới hạn kết luận" in answer


def test_partial_answer_co_san_phan_chua_kiem_chung_van_bi_chen_hang_rao_ket_luan():
    plan = _plan("So sánh doanh thu và công nợ tháng 7/2026", query_id="existing-footer")
    plan.finalize(limit_reached=True)
    answer = plan.finalize_answer("### Phần chưa thể kiểm chứng\n- Công nợ: chưa có nguồn.")

    assert "Giới hạn kết luận" in answer
    assert "không có bất thường" in answer


def test_c03_ytd_thieu_lich_su_bi_danh_dau_partial_va_chan_so_model_tu_tinh():
    """C03: tool báo thiếu lịch sử thì backend không được giữ số YTD model tự tính."""
    plan = _plan(
        "Lũy kế YTD thực hiện so kế hoạch và cùng kỳ năm trước thế nào?",
        query_id="c03-incomplete-ytd",
    )
    key = "ytd"
    plan.start_tool("get_revenue_ytd_cumulative", {"year_month_to": "2026-08"}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "cac_nam": [{
                "year": 2026,
                "date_from": "2026-01-01",
                "date_to": "2026-08-31",
                "revenue": 119_731_751_334,
                "plan_revenue": 777_008_113_856,
                "pct_of_plan": None,
                "revenue_history_complete": False,
                "revenue_history_available_from": "2026-07",
            }],
            "canh_bao_thieu_lich_su_doanh_thu": "Thiếu doanh thu trước 2026-07.",
        },
        source="template:get_revenue_ytd_cumulative",
        duration_ms=5,
        timeout_seconds=40,
    )
    plan.finalize()

    answer = plan.finalize_answer(
        "YTD đạt 617,01 tỷ trên kế hoạch 777,01 tỷ, tương đương 79,41%."
    )

    revenue_step = next(step for step in plan.steps if step.domain == "revenue")
    assert revenue_step.status == "partial"
    assert plan.status == "partial"
    assert "Chưa thể tính chính xác YTD" in answer
    assert "2026-01-01 đến 2026-08-31" in answer
    assert "2026-07" in answer
    assert "617,01" not in answer
    assert "79,41" not in answer
    assert "Không suy đoán số" in answer


def test_c31_khong_doi_first_observed_thanh_khach_moi_thuc_su():
    """C31: lan dau thay trong cua so lich su khong chung minh la khach moi trong doi."""
    plan = _plan(
        "Khách mới và tái kích hoạt bù doanh thu khách ngừng mua được bao nhiêu?",
        query_id="c31-first-observed",
    )
    key = "movement"
    plan.start_tool("get_customer_movement", {"month": "2026-08"}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "month": "2026-08",
            "previous_month": "2026-07",
            "history_from": "2025-09",
            "summary_all_customers": {
                "total_revenue_delta": 5_718_045_734,
                "reconciled_delta": 5_718_045_734,
            },
            "canh_bao": (
                "NEW_OR_FIRST_OBSERVED chi la lan dau thay trong cua so du lieu; "
                "khong khang dinh la khach moi trong doi."
            ),
        },
        source="template:get_customer_movement",
        duration_ms=5,
        timeout_seconds=40,
    )
    plan.finalize()

    answer = plan.finalize_answer(
        "Khách tái kích hoạt mang về gấp 5 lần khách mới thực sự."
    )

    assert "khách mới thực sự" not in answer
    assert "khách lần đầu quan sát trong cửa sổ dữ liệu" in answer
    assert "2025-09 đến 2026-08" in answer
    assert "không đủ cơ sở xác nhận khách mới trong đời" in answer


def test_m20_giam_doc_mien_khong_bi_ke_hoach_goi_lap_tool_luong_bi_chan():
    plan = build_query_plan(
        "Thưởng/KPI của đội có khớp doanh số và chính sách đã chốt?",
        query_id="m20-regional-director",
        scope_role="regional_director",
        scope_area_code="MB",
        scope_employee_code=None,
        scope_channel=None,
        max_rounds=8,
        max_tools_per_round=5,
        max_unique_tools=12,
        request_timeout_seconds=110,
    )

    salary = next(step for step in plan.steps if step.domain == "salary")
    assert salary.status == "skipped"
    assert salary.tool_hints == []
    assert "không mở" in salary.error
    assert "get_salary_ranking" not in plan.prompt_note()
    assert not any(rule.rule.startswith("salary_") for rule in plan.reconciliation_rules)

    plan.finalize()
    answer = plan.finalize_answer("KPI đã được đối chiếu.")
    assert answer.count("Đối chiếu lương thưởng") == 1
    assert "đạt giới hạn" not in answer.lower()


def test_v33_la_kiem_tra_don_khong_bi_hieu_nham_thanh_doi_chieu_doanh_thu():
    plan = build_query_plan(
        "Đơn nào bị hủy, trả, điều chỉnh, giao/hóa đơn chậm hoặc chưa tìm thấy hóa đơn?",
        query_id="v33-order-exceptions",
        scope_role="qlv",
        scope_area_code="MB",
        scope_employee_code="TM25010183",
        scope_channel="OTC",
        max_rounds=8,
        max_tools_per_round=5,
        max_unique_tools=12,
        request_timeout_seconds=110,
    )

    assert [step.domain for step in plan.steps] == ["orders"]
    assert plan.metrics == ["order_quality"]
    assert plan.steps[0].tool_hints == ["check_order_timing"]
    assert plan.reconciliation_rules == []

    key = "check-order-default-period"
    plan.start_tool("check_order_timing", {}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "status": "OK",
            "order_fulfillment_exceptions": {"rows": []},
            "unavailable_checks": [
                "Giao chậm: chưa có mốc giao hàng thực tế; chỉ có ngày đơn và ngày hóa đơn."
            ],
        },
        source="template:check_order_timing",
        duration_ms=5,
        timeout_seconds=40,
    )
    plan.finalize()
    assert plan.status == "partial"
    assert "Đối chiếu doanh thu" not in plan.prompt_note()
    answer = plan.finalize_answer("Có 22 đơn cần kiểm tra; phần giao chậm chưa đủ nguồn.")
    assert "Giao chậm" in answer
    assert "Giới hạn kết luận" in answer


def test_payload_thanh_cong_ky_thuat_nhung_comparison_invalid_van_la_partial():
    plan = _plan("So sánh doanh thu tháng 7 và tháng 8/2026", query_id="compare-incomplete")
    key = "compare"
    plan.start_tool("compare_periods", {}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "comparison_valid": False,
            "warning": "Kỳ tháng 7 nằm ngoài phạm vi dữ liệu đầy đủ.",
        },
        source="template:compare_periods",
        duration_ms=5,
        timeout_seconds=40,
    )

    step = next(item for item in plan.steps if item.tool_name == "compare_periods")
    assert step.status == "partial"
    assert "ngoài phạm vi" in step.error


def test_status_partial_khong_bi_planner_danh_dau_completed():
    plan = _plan("Khách nào giảm mua và còn thiếu dữ liệu công nợ?", query_id="nested-partial")
    key = "coverage"
    plan.start_tool("get_customer_product_coverage", {}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "status": "PARTIAL",
            "unavailable_metrics": ["receivables"],
            "rows": [],
        },
        source="template:get_customer_product_coverage",
        duration_ms=5,
        timeout_seconds=40,
    )

    assert any(step.status == "partial" for step in plan.steps)


def test_kpi_giua_thang_khong_duoc_goi_la_binh_thuong_chi_vi_dau_thang():
    plan = _plan(
        "Thưởng/KPI của đội có khớp doanh số và chính sách; có bất thường nào cần kiểm tra?",
        query_id="m20-midmonth",
    )
    key = "kpi-midmonth"
    plan.start_tool("get_employee_kpi", {"as_of_date": "2026-09-09"}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "as_of": "2026-09-09",
            "total_employees": 98,
            "count_kpi_achieved": 0,
            "rows": [{"employee_code": "MBKV12", "pct": 6.1}],
        },
        source="template:get_employee_kpi",
        duration_ms=5,
        timeout_seconds=40,
    )
    plan.finalize()

    answer = plan.finalize_answer(
        "- Đây là điều **bình thường ở giai đoạn đầu tháng** vì target là cho cả tháng.\n"
        "- Không có ai lệch bất thường so với mặt bằng chung — phù hợp việc đang ở đầu chu kỳ tháng."
    )

    assert "bình thường ở giai đoạn đầu tháng" not in answer
    assert "không có ai lệch bất thường" not in answer
    assert "chưa đủ cơ sở kết luận nhịp độ hiện tại là bình thường hay bất thường" in answer


def test_footer_khong_lo_ten_ham_noi_bo_cho_nguoi_dung():
    plan = _plan("KPI đội có bất thường nào cần kiểm tra?", query_id="friendly-footer")
    plan.finalize()

    answer = plan.finalize_answer(
        "### Phần chưa thể kiểm chứng\n"
        "- Truy vấn bổ sung bằng get_operational_data_quality: chưa có nguồn action tracker."
    )

    assert "get_operational_data_quality" not in answer
    assert "Kiểm tra bổ sung: chưa có nguồn action tracker." in answer


def test_hoi_tien_da_thu_gap_long_trong_receivables_overview_duoc_nang_len_partial():
    plan = _plan("Tháng này từng TDV đã thu được bao nhiêu tiền?", query_id="collection-gap")
    key = "receivables"
    plan.start_tool("get_receivables_overview", {}, key)
    plan.finish_tool(
        key,
        ok=True,
        payload={
            "receivable_status": "ok",
            "total_overdue": 100,
            "collection_activity": {
                "status": "source_gap",
                "note": "Chưa có nguồn sự kiện thu tiền theo TDV.",
            },
        },
        source="template:get_receivables_overview",
        duration_ms=5,
        timeout_seconds=40,
    )

    assert any(step.status == "partial" for step in plan.steps)
    assert any("sự kiện thu tiền" in (step.error or "") for step in plan.steps)


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
