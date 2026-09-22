"""M20 (UAT 09/09): Giam doc mien hoi thuong/KPI doi - tu choi phan luong ca nhan, van tra phan KPI."""
import sys
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

import nl2sql  # noqa: E402
import local_warehouse  # noqa: E402
import report_templates  # noqa: E402
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


def test_m20_mien_bac_doi_chieu_du_tdv_ke_ca_nguoi_chua_co_khach_va_co_trung(tmp_path, monkeypatch):
    """S33 dem 1 ma TDV/nguoi tu snapshot nhan su; fact theo khach bo sot nguoi chua ban."""
    path = tmp_path / "warehouse.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE fact_tonghopkhachhang (
                employee_code TEXT, customer_code TEXT, amount_ct REAL,
                month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
            CREATE TABLE fact_thongketinhluong (
                employee_code TEXT, employee_name TEXT, position_code TEXT, area_code TEXT,
                manager_code TEXT, save_date TEXT, month_sale_amount REAL, month_sale_target REAL);
            CREATE TABLE dim_nhanvien (
                employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT, area_code TEXT);
            CREATE TABLE dim_chucvu (position_code TEXT, description TEXT);
            INSERT INTO dim_chucvu VALUES ('TDV','Trinh duoc vien'),('QLV','Quan ly vung');
            INSERT INTO dim_nhanvien VALUES
                ('A','A',0,'TDV','MB'),('B','B',1,'TDV','MB'),
                ('C','C',1,'TDV','MB'),('Q','Q',0,'QLV','MB'),('D','D',0,'TDV','MN');
            INSERT INTO fact_tonghopkhachhang VALUES
                ('A','KH1',100,100,'2026-09-22',0,'Q'),
                ('Q','KH2',90,100,'2026-09-22',0,NULL);
            INSERT INTO fact_thongketinhluong VALUES
                ('A','A','TDV','MB','Q','2026-09-15',0,100),
                ('A','A','TDV','MB','Q','2026-09-22',100,100),
                ('B','B','TDV','MB','Q','2026-09-22',65,100),
                ('C','C','TDV','MB','Q','2026-09-22',0,0),
                ('Q','Q','QLV','MB',NULL,'2026-09-22',90,100),
                ('D','D','TDV','MN',NULL,'2026-09-22',100,100);
        """)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    result = report_templates.call_template(
        "get_employee_kpi",
        {"as_of_date": "2026-09-22", "position_code": "QLV", "kpi_source": "customer"},
        question=M20, scope_role="regional_director", scope_area_code="MB",
    )

    assert result["ok"] is True
    data = result["result"]
    assert data["kpi_source"] == "fact_thongketinhluong"
    assert data["position_code"] == "TDV"
    assert data["roster_employees"] == 3
    assert data["total_employees"] == 2
    assert data["unassessed_count"] == 1
    assert data["count_above_target"] == 2
    assert data["count_below_target"] == 0
    assert data["count_kpi_achieved"] == data["count_full_target"] == 1
    assert data["comparison_threshold_summary"] == {
        "denominator_all_tdv": 3,
        "employees_with_target": 2,
        "unassessed_missing_target": 1,
        "at_least_100_pct": 1,
        "at_least_80_pct": 1,
        "at_least_65_pct": 2,
        "below_65_pct": 0,
    }
    assert {row["employee_code"] for row in data["rows"]} == {"A", "B"}
    assert data["rows"][0]["employee_code"] == "A"  # snapshot moi, khong lay A=0 ngay 15
    assert "roster_employees" in data["comparison_basis"]
    model_data = nl2sql._payload_for_model("get_employee_kpi", data, M20)
    assert model_data["comparison_threshold_summary"] == data["comparison_threshold_summary"]
    assert model_data["position_code"] == "TDV"


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
