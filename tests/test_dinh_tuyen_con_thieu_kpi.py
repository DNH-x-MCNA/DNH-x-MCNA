# -*- coding: utf-8 -*-
"""29/09/2026: cau "con thieu"/"moi ngay can" vao get_kpi_gap_run_rate (mo ta tool ghi BAT BUOC).

Truoc day cum "dat 100%" ep "Con thieu bao nhieu de dat 100% KPI?" vao get_employee_kpi truoc luat run-rate, con
"Moi ngay can ban bao nhieu de dat target?" (khong co so %/chu KPI) khong vao tool nao.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql

route = nl2sql._required_tool_for_question


def test_cau_khoang_thieu_vao_run_rate():
    for cau in ("Còn thiếu bao nhiêu để đạt 100% KPI?", "Mỗi ngày cần bán bao nhiêu để đạt target?",
                "Còn thiếu bao nhiêu để đạt chỉ tiêu tháng này?", "Đội tôi còn thiếu bao nhiêu so với kế hoạch?"):
        assert route(cau) == "get_kpi_gap_run_rate", cau


def test_cau_dat_nguong_theo_nguoi_van_vao_employee_kpi():
    assert route("TDV nào đạt 100% target tháng 8?") == "get_employee_kpi"
    # V12 (bo 138 cau): luat nguong o dau ham bat truoc, khong doi.
    assert route("Ai dưới 65/70%, dưới 80%, đạt 100% hoặc vượt 120%; mỗi người còn thiếu bao nhiêu tiền?") \
        == "get_employee_kpi"
