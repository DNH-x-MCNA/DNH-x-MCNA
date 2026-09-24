"""V37/S45, UAT 23/09: thu BC/PT co nguon, ke hoach va cam ket chua co."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def test_v37_uses_actual_receipt_postings_and_keeps_missing_sources_explicit(monkeypatch):
    captured = {}
    monkeypatch.setattr(rt, "team_customer_codes", lambda *args: {"C001", "C002"})

    def fake_bravo(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"CustomerCode": "C001", "CustomerName": "Khach 1", "EmployeeDMSCode": "D1",
             "Amount": 120, "BankCreditAmount": 100, "CashReceiptAmount": 20,
             "PostingRows": 2},
            {"CustomerCode": "C002", "CustomerName": "Khach 2", "EmployeeDMSCode": "D1",
             "Amount": 80, "BankCreditAmount": 80, "CashReceiptAmount": 0,
             "PostingRows": 1},
        ]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt._collection_actual_mtd(
        "2026-09-23", scope_area_code="MT", scope_employee_code="TM23110128",
        customer_limit=1)

    assert result["status"] == "partial"
    assert result["period_from"] == "2026-09-01"
    assert result["period_to"] == "2026-09-23"
    assert result["total_actual_collected"] == 200
    assert result["total_customers"] == 2
    assert result["total_posting_rows"] == 3
    assert result["by_employee"][0]["actual_collected"] == 200
    assert result["customers_not_shown"] == 1
    assert result["by_customer"][0]["customer_code"] == "C001"
    assert "ke_hoach_thu_tien" in result["unavailable_metrics"]
    assert "cam_ket_thu_va_han_cam_ket" in result["unavailable_metrics"]
    assert "h.DocCode IN ('BC','PT')" in captured["sql"]
    assert "h.Account LIKE '131%'" in captured["sql"]
    assert "k.Code IN" in captured["sql"]
    assert "tp.AreaCode IN" in captured["sql"]
    assert "C001" in captured["params"].values()


def test_v37_question_forces_collection_mode_without_model_control(monkeypatch):
    captured = {}
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)

    def fake_receivables(**kwargs):
        captured.update(kwargs)
        return {"collection_activity": {"status": "partial"}}

    monkeypatch.setitem(rt.TEMPLATES, "get_receivables_overview", fake_receivables)
    result = rt.call_template(
        "get_receivables_overview",
        {"include_collection": False, "collection_as_of_date": "2030-01-01"},
        question="Thu tiền tháng này từng TDV/khách so KH; cam kết thu nào quá hạn?",
        username="test.v37", session_id="kiemtra-v37-2409", scope_role="qlv",
        scope_area_code="MT", scope_employee_code="TM23110128",
    )
    assert result["ok"]
    assert captured["include_collection"] is True
    assert "collection_as_of_date" not in captured
    assert captured["scope_employee_code"] == "TM23110128"
    assert captured["scope_area_code"] == "MT"

