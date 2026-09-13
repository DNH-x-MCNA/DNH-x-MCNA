"""M20 (UAT 09/09): Giam doc mien hoi thuong/KPI doi - tu choi phan luong ca nhan, van tra phan KPI."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

import nl2sql  # noqa: E402
from test_data_freshness import _patch_nl2sql_runtime  # noqa: E402

M20 = "Thưởng/KPI đội có khớp doanh số và chính sách; bất thường cần kiểm tra"


def test_giam_doc_mien_bi_ep_sang_tool_kpi_kem_ghi_chu_quyen():
    tools = nl2sql._tools_for_request("MB", None, "regional_director", None)

    tool, ghi_chu = nl2sql._required_tool_for_request(M20, tools)

    assert nl2sql._required_tool_for_question(M20) == "get_salary_ranking"
    assert tool == "get_employee_kpi"
    assert "KHONG tu choi ca cau" in ghi_chu


@pytest.mark.parametrize("role,area,employee", [("c_level", None, None), ("qlv", "MB", "MBKV2")])
def test_vai_tro_duoc_xem_luong_giu_nguyen_tool_luong(role, area, employee):
    tools = nl2sql._tools_for_request(area, None, role, employee)

    assert nl2sql._required_tool_for_request(M20, tools) == ("get_salary_ranking", "")


def test_cau_khong_dinh_tuyen_vao_luong_khong_bi_doi():
    tools = nl2sql._tools_for_request("MB", None, "regional_director", None)
    cau = "Doanh thu tháng 8 theo kênh OTC và ETC là bao nhiêu?"

    assert nl2sql._required_tool_for_request(cau, tools) == (
        nl2sql._required_tool_for_question(cau), "")


@pytest.mark.parametrize("streaming", [False, True])
def test_ask_ep_tool_kpi_va_dua_ghi_chu_vao_system_dong(monkeypatch, streaming):
    calls = []

    class Stream:
        def __init__(self, message):
            self.message = message
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __iter__(self):
            return iter(())
        def get_final_message(self):
            return self.message

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                content = [SimpleNamespace(type="tool_use", name="get_employee_kpi", id="t1", input={})]
            else:
                content = [SimpleNamespace(type="text", text="KPI đội MB ...")]
            return SimpleNamespace(content=content, usage=SimpleNamespace())
        def stream(self, **kwargs):
            return Stream(self.create(**kwargs))

    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=Messages()), [])
    monkeypatch.setattr(nl2sql, "_static_system_prompt", lambda: "tinh")
    monkeypatch.setattr(nl2sql, "_dynamic_context_note", lambda *a: "dong")
    if streaming:
        list(nl2sql.ask_stream(M20, session_id="unit-m20", username="unit",
                               scope_role="regional_director", scope_area_code="MB"))
    else:
        nl2sql.ask(M20, session_id="unit-m20", username="unit",
                   scope_role="regional_director", scope_area_code="MB")

    dau = calls[0]
    assert dau["tool_choice"] == {"type": "tool", "name": "get_employee_kpi"}
    assert "get_salary_ranking" not in {t["name"] for t in dau["tools"]}
    assert "LUU Y QUYEN" in dau["system"][1]["text"]
    assert "LUU Y QUYEN" not in dau["system"][0]["text"]  # khong pha cache block tinh
