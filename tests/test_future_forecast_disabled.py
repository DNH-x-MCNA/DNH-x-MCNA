# -*- coding: utf-8 -*-
"""Regression: du bao tuong lai phai bi khoa truoc AI, DB va kenh thong bao."""
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import feature_policy as policy  # noqa: E402
import nl2sql  # noqa: E402


@pytest.mark.parametrize("question", [
    "Dự báo doanh thu tháng tới",
    "du bao KPI cuoi thang",
    "Forecast doanh số quý sau",
    "Doanh thu cuối tháng sẽ là bao nhiêu?",
    "Ước tính KPI cuối tháng của đội miền Bắc",
    "Mặt hàng này còn bao nhiêu ngày thì hết kho trong tương lai?",
    # 21/08/2026: cac cach dien dat KHEO tung lot qua nhanh chinh (thieu 1 trong 3 nhom tu khoa) -
    # xem _IMPLICIT_FUTURE_SPECULATION_RE trong feature_policy.py.
    "Tình hình doanh thu tháng sau sẽ thế nào?",
    "KPI đội miền Nam có khả năng đạt không?",
    "Xu hướng doanh số sắp tới ra sao?",
    "Nếu tiếp tục đà tăng này thì công nợ sẽ tăng hay giảm?",
    "Liệu có đạt chỉ tiêu doanh thu không?",
])
def test_nhan_dien_cau_hoi_du_bao(question):
    assert policy.is_future_forecast_question(question) is True


@pytest.mark.parametrize("question", [
    "So sánh doanh thu tháng này với tháng trước",
    "Doanh thu lũy kế thực tế đến ngày 14/08 là bao nhiêu?",
    "Chỉ tiêu tháng sau đã nhập là bao nhiêu?",
    "Kế hoạch quý tới của miền Bắc là bao nhiêu?",
    "KPI thực đạt so với target hiện tại",
    # 21/08/2026: cac cau hoi qua khu/hien tai KHONG duoc bi chan nham boi nhanh bo sung
    # _IMPLICIT_FUTURE_SPECULATION_RE (phai giu duoc kha nang tra loi du lieu thuc te).
    "Công nợ tuần trước so với tuần này thế nào?",
    "Doanh thu tháng 7 đã tăng hay giảm so với tháng 6?",
    "Đội miền Bắc đã đạt KPI tháng này chưa?",
])
def test_khong_chan_du_lieu_thuc_te_lich_su_va_ke_hoach(question):
    assert policy.is_future_forecast_question(question) is False


def test_tool_du_bao_khong_duoc_gui_cho_model():
    names = {tool["name"] for tool in nl2sql.ALL_TOOLS}
    assert names.isdisjoint(policy.DISABLED_FUTURE_TOOL_NAMES)
    prompt = nl2sql._static_system_prompt()
    assert "DU BAO TUONG LAI DA TAT" in prompt
    assert "get_revenue_forecast" not in prompt
    assert "get_kpi_forecast" not in prompt


def test_ask_chan_truoc_api_va_db(monkeypatch):
    saved = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    monkeypatch.setattr(nl2sql, "append_message", lambda *a, **kw: saved.append((a, kw)))
    monkeypatch.setattr(
        nl2sql.anthropic,
        "Anthropic",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Khong duoc goi AI")),
    )

    result = nl2sql.ask("Dự báo doanh thu tháng tới", session_id="s1", query_id="q1")

    assert result["feature_disabled"] is True
    assert result["sql_used"] == []
    assert result["last_result"] is None
    assert result["query_id"] == "q1"
    assert len(saved) == 2


def test_ask_stream_chan_truoc_api_va_db(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    monkeypatch.setattr(nl2sql, "append_message", lambda *a, **kw: None)
    monkeypatch.setattr(
        nl2sql.anthropic,
        "Anthropic",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Khong duoc goi AI")),
    )

    chunks = list(nl2sql.ask_stream("du phong KPI cuoi thang", query_id="q2"))

    assert [chunk["type"] for chunk in chunks] == ["text_delta", "done"]
    assert chunks[-1]["feature_disabled"] is True
    assert chunks[-1]["sql_used"] == []
    assert chunks[-1]["query_id"] == "q2"


def test_dead_stock_predictive_alert_khong_doc_snapshot(monkeypatch):
    from src import alerts

    monkeypatch.setattr(
        alerts,
        "get_bravo_inventory_snapshot",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Khong duoc doc snapshot")),
    )
    assert alerts.check_dead_stock_alert() is None
