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


def test_v25_policy_flags_rule_procedure_and_actual_mismatch(monkeypatch):
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
        if "FROM dbo.FACT_ThongKeTinhLuong f" in sql:
            return [{
                "EmployeeCode": "QLV01", "EmployeeName": "Nguyen Van A",
                "AreaCode": "MN", "PositionCode": "QLV", "SaveDate": "2026-07-31",
                "V25Date": "2026-07-27", "V25Amount": 735_600_000,
                "MonthSaleTarget": 1_000_000_000, "V25Percent_R": 0.7356,
                "V25Bonus": 0,
            }]
        if "OBJECT_DEFINITION" in sql:
            return [{"Definition": (
                "SELECT TypeCode INTO #KPICt FROM dbo.DIM_BacThuong "
                "WHERE TypeCode IN ('V15','V22','ASO'); "
                "IF OBJECT_ID('Tempdb..#LongKPICt') IS NOT NULL DROP TABLE #LongKPICt"
            )}]
        raise AssertionError(sql)

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.salary_bonus_policy("v25")

    assert result["procedure_loads_v25_rules"] is False
    assert result["rule_actual_mismatch_count"] == 1
    assert result["rule_actual_mismatches"][0]["v25_percent"] == 73.56
    assert "#KPICt" in result["implementation_warning"]


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
        "get_salary_bonus_policy",
        "get_customer_revenue_debt_risk",
    } <= names


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
    assert nl2sql.MAX_TOOL_ROUNDS == 8


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
    monkeypatch.setattr(nl2sql.anthropic, "Anthropic", lambda api_key: fake_client)
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "append_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "set_query_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "compute_and_log_cost", lambda *args, **kwargs: None)

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
