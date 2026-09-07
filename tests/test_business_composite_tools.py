import os
import sys
from types import SimpleNamespace


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    # Append so backend/nl2sql.py is importable without shadowing the root main.py.
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt


def test_promotion_effectiveness_uses_dms_link_and_latest_complete_month(monkeypatch):
    seen = []

    def fake_bravo(sql, params=None):
        seen.append((sql, params or {}))
        if "LinkRowId" in sql:
            return [{"CoverageDate": "2026-01-09", "LinkSyncedAt": "2026-01-09T11:12:10", "LinkRowId": 9}]
        assert "DMS_DonHangCTKM" in sql
        assert "DMS_CTKM p" in sql
        assert "GROUP BY CTKM" not in sql.upper()
        return [{
            "ProgramId": 1,
            "ProgramCode": "KM01",
            "ProgramName": "Mua 10 tang 1",
            "Orders": 5,
            "Customers": 4,
            "AssociatedRevenue": 1_000_000,
            "OrdersWithoutInvoice": 1,
            "PaidProductOccurrences": 8,
            "GiftProductCount": 1,
            "ConfiguredProductCount": 1,
        }]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.promotion_effectiveness(limit=10)

    assert result["period"] == {"from": "2025-12-01", "to": "2025-12-31"}
    assert result["programs"][0]["associated_revenue"] == 1_000_000
    assert result["programs"][0]["participating_customers"] == 4
    assert result["programs"][0]["average_revenue_per_invoiced_order"] == 250_000
    assert len(seen) == 2


def test_promotion_effectiveness_does_not_fallback_to_invoice_note(monkeypatch):
    calls = []

    def fake_bravo(sql, params=None):
        calls.append(sql)
        return [{"CoverageDate": "2026-01-09", "LinkSyncedAt": "2026-01-09", "LinkRowId": 9}]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.promotion_effectiveness("2026-08-01", "2026-08-14")

    assert result["status"] == "source_gap"
    assert result["programs"] == []
    assert "ghi chu" in result["warning"].lower()
    assert len(calls) == 1, "Nguon thieu thi khong duoc chay query thay the sai nghia"


def test_v25_tu_07_2026_la_doi_co_che_khong_phai_mismatch(monkeypatch):
    monkeypatch.setattr(rt, "_q", lambda sql, params=(): [{"d": "2026-07-31"}])

    def fake_bravo(sql, params=None):
        if "FROM dbo.DIM_BacThuong" in sql and "SELECT CriterialCode" in sql:
            return [{
                "CriterialCode": "MB", "TypeCode": "V25", "AreaCode": "MN",
                "PositionCode": "QLV", "Description": "Thuong tien do QLV",
                "StartDate": "2025-01-01", "EndDate": None,
                "IsTargetPercent": 1, "IsEarnPercent": 0,
                "FromValue": 70, "ToValue": 80, "Earn1": 1_000_000,
                "Earn2": None, "EarnMax": None, "CheckASO": None,
                "CheckTargetEmp": None, "ASOCusCondType": None,
            }]
        raise AssertionError(sql)

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.salary_bonus_policy("v25")

    assert result["mechanism_status"] == "INACTIVE_FROM_2026_07_REPLACED_BY_V15_V22"
    assert result["procedure_loads_v25_rules"] is None
    assert result["rule_actual_mismatch_count"] == 0
    assert result["rule_actual_mismatches"] == []
    assert result["implementation_warning"] is None
    assert result["rule_count"] == 0
    assert result["inactive_rule_rows_count"] == 1
    assert "KHONG PHAI loi tinh luong" in result["formula"]


def test_customer_revenue_debt_risk_is_one_composite_query(monkeypatch):
    captured = []

    def fake_q(sql, params=()):
        captured.append((sql, params))
        return [{
            "customer_code": "KH01", "customer_name": "Nha thuoc A",
            "rev_recent": 200_000_000, "rev_prior": 400_000_000,
            "pct_change": -50.0, "balance_end": 300_000_000,
            "overdue": 100_000_000, "snapshot_at": "2026-08-14T10:45:00",
        }]

    monkeypatch.setattr(rt, "_q", fake_q)
    result = rt.customer_revenue_debt_risk(as_of_date="2026-08-14", limit=20)

    assert result["recent_period"] == {"from": "2026-05-01", "to": "2026-07-31"}
    assert result["prior_period"] == {"from": "2026-02-01", "to": "2026-04-30"}
    assert result["customers"][0]["change_pct"] == -50.0
    assert len(captured) == 1
    assert "revenue" in captured[0][0]
    assert "debt" in captured[0][0]


def test_composite_business_tools_are_exposed_to_model():
    names = {tool["name"] for tool in nl2sql.TEMPLATE_TOOLS}
    assert {
        "get_promotion_effectiveness",
        "get_promotion_data_quality",
        "get_salary_bonus_policy",
        "get_salary_data_quality",
        "get_customer_revenue_debt_risk",
    } <= names
    salary_tool = next(tool for tool in nl2sql.TEMPLATE_TOOLS
                       if tool["name"] == "get_salary_achievement_summary")
    assert "chi phi thuong/doanh thu" in salary_tool["description"].lower()


def test_top_products_channel_comparison_requires_two_separate_calls():
    tool = next(tool for tool in nl2sql.TEMPLATE_TOOLS if tool["name"] == "get_top_products")
    description = tool["description"]
    channel_description = tool["input_schema"]["properties"]["channel"]["description"]
    system_prompt = nl2sql._static_system_prompt()

    for text in (description, channel_description, system_prompt):
        assert "channel=OTC" in text
        assert "channel=ETC" in text
        assert "channel=ALL" in text

    calls = [
        SimpleNamespace(
            id="otc", name="get_top_products",
            input={"date_from": "2026-08-01", "date_to": "2026-08-28", "limit": 10, "channel": "OTC"},
        ),
        SimpleNamespace(
            id="etc", name="get_top_products",
            input={"date_from": "2026-08-01", "date_to": "2026-08-28", "limit": 10, "channel": "ETC"},
        ),
    ]
    assert nl2sql._merge_bulk_tool_calls(calls) == set()


def test_promotion_data_quality_is_one_scoped_query(monkeypatch):
    captured = []

    def fake_bravo(sql, params=None):
        captured.append((sql, params or {}))
        return [{
            "FirstLinkedOrderDate": "2025-01-01",
            "LastLinkedOrderDate": "2026-01-09",
            "LinkRows": 2_257_428,
            "LinkedOrders": 495_199,
            "Programs": 91,
            "MissingOrder": 12,
            "MissingProgram": 22,
            "ValidLinks": 2_257_394,
            "LastLinkSyncAt": "2026-01-09T10:00:00",
        }]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.promotion_data_quality(scope_area_code="MN")

    assert result["last_linked_order_date"] == "2026-01-09"
    assert result["missing_order"] == 12
    assert result["missing_program"] == 22
    assert len(captured) == 1
    assert "tp.AreaCode=:scope_area_code" in captured[0][0]
    assert captured[0][1]["scope_area_code"] == "MN"


def test_salary_data_quality_reconciles_dm_in_fixed_queries(monkeypatch):
    calls = []

    def fake_q(sql, params=()):
        calls.append((sql, tuple(params)))
        if "SELECT MAX(save_date)" in sql:
            return [{"d": "2026-07-31"}]
        if "SELECT COUNT(*) employees" in sql:
            return [{
                "employees": 206, "employees_with_dm_bonus": 115,
                "mismatches": 0, "max_abs_delta": 0.005,
            }]
        if "expected_dm_bonus" in sql:
            return []
        raise AssertionError(sql)

    monkeypatch.setattr(rt, "_q", fake_q)
    result = rt.salary_data_quality("dm_reconciliation", "2026-07")

    assert result["snapshot_date"] == "2026-07-31"
    assert result["employees"] == 206
    assert result["mismatch_count"] == 0
    assert "TotalPoint" in result["formula"]
    assert len(calls) == 3


def test_salary_data_quality_base_salary_uses_live_schema(monkeypatch):
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: [
        {"ColumnName": "SalaryLevel", "DataType": "varchar"},
    ])
    result = rt.salary_data_quality("base_salary_schema")
    assert result["has_base_salary_amount"] is False
    assert result["has_level_to_base_salary_mapping"] is False
    assert "chua co" in result["conclusion"].lower()


def test_high_risk_intents_force_their_single_verified_tool():
    assert nl2sql._required_tool_for_question(
        "Chuỗi liên kết đơn hàng–khuyến mãi hiện có dữ liệu đến ngày nào?"
    ) == "get_promotion_data_quality"
    assert nl2sql._required_tool_for_question(
        "Có bao nhiêu liên kết khuyến mãi mất đơn hàng hoặc mất mã chương trình?"
    ) == "get_promotion_data_quality"
    assert nl2sql._required_tool_for_question(
        "Thưởng DM1/DM2/DM3 và TotalPoint của từng người khớp nhau thế nào?"
    ) == "get_salary_data_quality"
    assert nl2sql._required_tool_for_question(
        "Bảng hiện có đủ dữ liệu để kết luận tổng thu nhập đã gồm lương cơ bản chưa?"
    ) == "get_salary_data_quality"
    assert nl2sql._required_tool_for_question(
        "Có ai V25Bonus đã lưu bằng 0 dù nằm trong bậc thưởng không?"
    ) == "get_salary_bonus_policy"
    assert nl2sql._required_tool_for_question(
        "Loại đơn hàng lớn bất thường và hàng trả; kết quả thực chất của đội"
    ) == "check_order_timing"
    assert nl2sql._required_tool_for_question(
        "So 3 tháng gần nhất, tháng này đội giảm ở khách/đơn/sản lượng hay giá trị đơn"
    ) == "get_geography_monthly_performance"
    assert nl2sql._required_tool_for_question(
        "DT đội đến từ bao nhiêu khách/đơn; AOV và tần suất mua thay đổi"
    ) == "get_customer_product_coverage"
    assert nl2sql._required_tool_for_question(
        "Còn thiếu bao nhiêu để đạt 65%, 80%, 100%; mỗi ngày cần bán bao nhiêu"
    ) == "get_kpi_gap_run_rate"
    assert nl2sql._required_tool_for_question(
        "Thưởng/phụ cấp từng người thay đổi; điểm không khớp KPI/chính sách của cả đội"
    ) == "get_salary_ranking"
    assert nl2sql._required_tool_for_question(
        "Lũy kế YTD so kế hoạch/cùng kỳ; bình quân cần đạt mỗi tháng còn lại"
    ) == "get_revenue_ytd_cumulative"
    assert nl2sql._required_tool_for_question(
        "Khách lớn nào ngừng mua hoặc kéo dài chu kỳ mua so lịch sử"
    ) == "get_customer_movement"
    assert nl2sql._required_tool_for_question(
        "Tăng trưởng like-for-like tách khỏi tăng trưởng do mở mới"
    ) == "get_customer_movement"
    assert nl2sql._required_tool_for_question(
        "Phụ thuộc top 10 khách/top 10 SP/top 3 miền ở mức nào; xu hướng tập trung"
    ) == "get_top_customers"
    assert nl2sql._required_tool_for_question(
        "Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả, doanh thu thuần từng tháng"
    ) == "check_order_timing"
    assert nl2sql._required_tool_for_question(
        "SKU doanh thu giảm do ít khách, ít đơn, giảm lượng hay giảm giá bán"
    ) == "get_customer_product_coverage"
    assert nl2sql._required_tool_for_question(
        "Chỉ tiêu nào sai do thiếu manager, thiếu target, sai mapping hoặc trùng mã"
    ) == "get_operational_data_quality"
    assert nl2sql._required_tool_for_question(
        "Hàng cận date và chậm luân chuyển nào cần đẩy bán hoặc dừng nhập"
    ) == "get_inventory_expiry_report"
    assert nl2sql._required_tool_for_question(
        "Giá trị tồn kho, số tháng tồn và stock-out theo tháng"
    ) == "get_inventory_by_region"
    assert nl2sql._required_tool_for_question(
        "Tháng mùa vụ cao/thấp; tháng hiện tại lệch mô hình bao nhiêu"
    ) == "get_revenue_monthly_series"
    assert nl2sql._required_tool_for_question(
        "Khuyến mãi nào có nhiều khách tham gia nhưng không tạo tăng trưởng"
    ) == "get_promotion_effectiveness"
    assert nl2sql._required_tool_for_question(
        "Tỷ lệ nhân sự đạt 65%, 70%, 80%, 100% và 120% là bao nhiêu"
    ) == "get_employee_kpi"
    assert nl2sql._required_tool_for_question(
        "Chi phí thưởng kinh doanh trên doanh thu; tăng trưởng có bền vững không"
    ) == "get_salary_ranking"


def test_m_role_questions_start_from_their_verified_report_not_free_sql():
    # Regression pack for the M01-M44 regional-management sheet.  These questions used to
    # fall through to ad-hoc SQL, or (M20) mistook the word "bất thường" for order timing.
    expected = {
        "Gap tới KH tháng/quý còn bao nhiêu; mỗi vùng cần đóng góp thêm bao nhiêu": "get_kpi_gap_run_rate",
        "Doanh thu ngày/tuần đang chạy nhanh/chậm hơn nhịp cần thiết": "get_kpi_gap_run_rate",
        "Số khách/đơn/AOV/tần suất mua miền/kênh thay đổi qua từng tháng": "get_geography_monthly_performance",
        "Đơn/hóa đơn bất thường làm biến động kết quả tháng; loại đi còn bao nhiêu": "check_order_timing",
        "Tỉnh/chi nhánh/NPP nào kéo giảm kết quả và cần ưu tiên can thiệp": "get_geography_monthly_performance",
        "Doanh số/target/%hoàn thành từng TDV trong đội theo tháng; ai cải thiện/suy giảm nhất": "get_employee_kpi",
        "Đội đạt 100%/80%/qua cổng 65-70%/dưới cổng; xu hướng 3 tháng": "get_employee_kpi",
        "Số NV dưới 80%; phần hụt tập trung ở ai": "get_employee_kpi",
        "NV giảm doanh số liên tiếp 3 tháng; do mất khách/giảm tần suất/giảm giá trị đơn": "get_workforce_productivity",
        "NV mới đạt ramp-up sau 1/2/3/6 tháng so chuẩn cùng vai trò": "get_workforce_productivity",
        "Địa bàn trống, NV nghỉ/chuyển vùng, khách chưa gán ảnh hưởng bao nhiêu DT": "get_operational_data_quality",
        "Thưởng/KPI đội có khớp doanh số và chính sách; bất thường cần kiểm tra": "get_salary_ranking",
        "Top khách hàng theo DT từng tháng; khách tăng/giảm mạnh, TDV phụ trách": "get_top_customers",
        "Mở nhiều khách mới nhưng DT/khách và tỷ lệ mua lại thấp": "get_customer_movement",
        "Tỉnh/huyện ít khách hoạt động/ít đơn/DT-khách thấp hơn chuẩn miền": "get_geography_monthly_performance",
        "NPP/chi nhánh tăng khách tốt nhưng công nợ/tồn kho xấu đi": "get_geography_monthly_performance",
        "SKU chiến lược đạt %KH tại vùng; khoảng trống độ phủ lớn nhất": "get_customer_product_coverage",
        "SP mới đạt độ phủ/DT sau 1/3/6 tháng tại vùng": "get_customer_product_coverage",
        "Tỷ lệ trả hàng/chiết khấu/hàng tặng trên DT của từng vùng thay đổi": "check_order_timing",
        "Tổng nợ/quá hạn/DSO/thu tiền từng vùng-QLV qua từng tháng; đơn vị xấu nhanh nhất": "get_receivables_overview",
        "Khách cần dừng/bóp bán vì nợ xấu; DT nguy cơ ảnh hưởng bao nhiêu": "get_customer_revenue_debt_risk",
        "ETC: kế hoạch thầu, tỷ lệ trúng, DT thực hiện, thu tiền từng tháng theo vùng/khách": "get_geography_monthly_performance",
        "Với vùng dưới KH: 3 nguyên nhân định lượng, 3 hành động, owner, deadline": "get_operational_data_quality",
    }
    for question, tool in expected.items():
        assert nl2sql._required_tool_for_question(question) == tool, question


def test_ask_sends_forced_tool_choice_only_on_first_round(monkeypatch):
    seen = []

    class FakeMessages:
        def create(self, **kwargs):
            seen.append(kwargs)
            if len(seen) == 1:
                return SimpleNamespace(
                    content=[SimpleNamespace(
                        type="tool_use", id="quality-1",
                        name="get_promotion_data_quality", input={},
                    )],
                    usage=SimpleNamespace(),
                )
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Dữ liệu liên kết đến 09/01/2026.")],
                usage=SimpleNamespace(),
            )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(nl2sql, "LLM_BASE_URL", "")
    monkeypatch.setattr(
        nl2sql.anthropic, "Anthropic",
        lambda api_key: SimpleNamespace(messages=FakeMessages()),
    )
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "append_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "set_query_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "compute_and_log_cost", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "latest_data_date", lambda: "2026-08-24")
    monkeypatch.setattr(
        nl2sql, "call_template",
        lambda *args, **kwargs: {"ok": True, "result": {
            "status": "ok", "last_linked_order_date": "2026-01-09",
            "missing_order": 34, "missing_program": 0,
        }},
    )

    result = nl2sql.ask(
        "Chuỗi liên kết đơn hàng–khuyến mãi hiện có dữ liệu đến ngày nào?",
        session_id="forced-quality", scope_role="c_level",
    )

    assert result["answer"].startswith("Dữ liệu liên kết đến")
    assert seen[0]["tool_choice"] == {
        "type": "tool", "name": "get_promotion_data_quality",
    }
    assert "tool_choice" not in seen[1]


def test_new_quality_tools_keep_qlv_scope_fail_closed(monkeypatch):
    seen = {}

    def fake_promo(**kwargs):
        seen["promo"] = kwargs
        return {"status": "ok"}

    def fake_salary(**kwargs):
        seen["salary"] = kwargs
        return {"status": "ok"}

    monkeypatch.setitem(rt.TEMPLATES, "get_promotion_data_quality", fake_promo)
    monkeypatch.setitem(rt.TEMPLATES, "get_salary_data_quality", fake_salary)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)

    promo = rt.call_template(
        "get_promotion_data_quality", {}, scope_area_code="MN",
        scope_employee_code="QLV01", scope_channel="OTC", scope_role="qlv",
    )
    salary = rt.call_template(
        "get_salary_data_quality", {"check_type": "dm_reconciliation"},
        scope_area_code="MN", scope_employee_code="QLV01", scope_role="qlv",
    )

    assert promo["ok"] is True and salary["ok"] is True
    assert seen["promo"] == {
        "scope_area_code": "MN", "scope_employee_code": "QLV01", "scope_channel": "OTC",
    }
    assert seen["salary"] == {
        "check_type": "dm_reconciliation", "scope_role": "qlv",
        "scope_employee_code": "QLV01",
    }


def test_provider_configuration_survives_multi_step_merge(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setenv("LLM_API_KEY", "provider-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-fallback-key")
    monkeypatch.setattr(nl2sql, "LLM_BASE_URL", "https://provider.example/anthropic")
    monkeypatch.setattr(nl2sql.anthropic, "Anthropic", fake_client)

    client = nl2sql._llm_client()

    assert isinstance(client, SimpleNamespace)
    assert captured == {
        "api_key": "provider-test-key",
        "base_url": "https://provider.example/anthropic",
    }
    # Day bay chong doi so vong goi tool AM THAM (so nay anh huong truc tiep toi chi phi va thoi gian
    # tra loi). Doi gia tri o day la viec CO Y - doc khoi ghi chu lich su trong nl2sql.py truoc da.
    # 19/08/2026: doi tu hang so phang sang theo cap vai tro - bay ca 2 phia (mac dinh + tung vai tro).
    assert nl2sql.DEFAULT_MAX_TOOL_ROUNDS == 6
    assert nl2sql.MAX_TOOL_ROUNDS_BY_ROLE == {
        "qlv": 5, "regional_director": 8, "c_level": 10, "admin_ops": 10,
    }


def test_timeout_env_is_bounded_and_invalid_value_falls_back(monkeypatch):
    monkeypatch.setenv("TEST_CHAT_TIMEOUT", "300")
    assert nl2sql._timeout_env("TEST_CHAT_TIMEOUT", 110, 120) == 120
    monkeypatch.setenv("TEST_CHAT_TIMEOUT", "khong-phai-so")
    assert nl2sql._timeout_env("TEST_CHAT_TIMEOUT", 110, 120) == 110


def _run_ask_until_rounds_exhausted(monkeypatch, scope_role):
    """Model LUON tra ve tool_use voi tham so KHAC nhau moi vong (tranh co che chong lap lai bat
    som) - buoc vong lap chay het so vong cho phep cua vai tro, roi bi ep tra loi cuoi cung."""
    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if "tools" not in kwargs:
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="Tong hop cuoi cung.")],
                    usage=SimpleNamespace(),
                )
            return SimpleNamespace(
                content=[SimpleNamespace(
                    type="tool_use", id=f"tool-{self.calls}",
                    name="get_promotion_effectiveness", input={"limit": self.calls},
                )],
                usage=SimpleNamespace(),
            )

    fake_messages = FakeMessages()
    fake_client = SimpleNamespace(messages=fake_messages)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(nl2sql, "LLM_BASE_URL", "")
    monkeypatch.setattr(nl2sql.anthropic, "Anthropic", lambda api_key: fake_client)
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "append_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "set_query_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "compute_and_log_cost", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "latest_data_date", lambda: "2026-08-24")
    monkeypatch.setattr(nl2sql, "call_template",
                        lambda name, args, **kw: {"ok": True, "result": {"programs": []}})

    nl2sql.ask("Danh gia hieu qua khuyen mai", session_id="s-test", query_id="q-test",
              scope_role=scope_role)
    return fake_messages.calls


def test_gioi_han_vong_tool_theo_cap_vai_tro(monkeypatch):
    """19/08/2026: gioi han vong tool THEO CAP VAI TRO thay vi hang so phang - qlv=5 (it nhat, cau
    hoi trong pham vi 1 doi nho, kem 'Truong kenh' MT cung cap), regional_director=8 (TP = Giam doc
    Mien = Giam doc Kenh, quan ly rong hon), c_level/admin_ops=10 (nhieu nhat, hoi toan cong ty).
    Tong so lan goi model = so vong + 1 (lan cuoi bi ep tong hop, khong con 'tools' trong kwargs)."""
    for role, expected_rounds in (("qlv", 5), ("regional_director", 8), ("c_level", 10), ("admin_ops", 10)):
        calls = _run_ask_until_rounds_exhausted(monkeypatch, role)
        assert calls == expected_rounds + 1, f"vai tro {role}: ky vong {expected_rounds + 1} lan goi, thuc te {calls}"


def test_repeated_tool_call_is_not_reexecuted_and_forces_final_answer(monkeypatch):
    tool_runs = []

    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if "tools" not in kwargs:
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="Da tong hop tu du lieu da truy van.")],
                    usage=SimpleNamespace(),
                )
            return SimpleNamespace(
                content=[SimpleNamespace(
                    type="tool_use", id=f"tool-{self.calls}",
                    name="get_promotion_effectiveness", input={"limit": 10},
                )],
                usage=SimpleNamespace(),
            )

    fake_messages = FakeMessages()
    fake_client = SimpleNamespace(messages=fake_messages)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # This test uses the default Anthropic-shaped mock.  Keep it isolated from
    # the machine's optional provider configuration restored by the previous test.
    monkeypatch.setattr(nl2sql, "LLM_BASE_URL", "")
    monkeypatch.setattr(nl2sql.anthropic, "Anthropic", lambda api_key: fake_client)
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "append_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "set_query_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "compute_and_log_cost", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "latest_data_date", lambda: "2026-08-24")

    def fake_template(name, args, **kwargs):
        tool_runs.append((name, args))
        return {"ok": True, "result": {"programs": [{"program_name": "KM01"}]}}

    monkeypatch.setattr(nl2sql, "call_template", fake_template)
    result = nl2sql.ask("Danh gia hieu qua khuyen mai", session_id="s-test", query_id="q-test")

    assert result["answer"].startswith("Da tong hop tu du lieu da truy van.")
    assert "Dữ liệu trực tiếp:" in result["answer"]
    assert result["freshness"][0]["source_key"] == "promotion_live"
    assert "qua phuc tap" not in result["answer"].lower()
    assert len(tool_runs) == 1
    assert fake_messages.calls == 3
    assert result["last_result"] is None
    assert result["partial_results_hidden"] is True
    assert result["query_plan"]["plan_id"] == "plan-q-test"
    assert result["query_plan"]["status"] == "completed"
    assert result["query_plan"]["steps"][0]["tool_name"] == "get_promotion_effectiveness"


def test_tool_call_key_is_order_independent():
    assert nl2sql._tool_call_key("x", {"a": 1, "b": 2}) == nl2sql._tool_call_key(
        "x", {"b": 2, "a": 1}
    )


def test_salary_queries_only_use_closed_period_snapshots():
    clause, params = rt._closed_salary_date_filter("f", None)
    assert "start of month" in clause
    assert params == ()

    clause, params = rt._closed_salary_date_filter("", "2026-07")
    assert "substr(save_date,1,7)=?" in clause
    assert params == ("2026-07",)
