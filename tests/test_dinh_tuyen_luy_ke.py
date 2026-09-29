# -*- coding: utf-8 -*-
"""29/09/2026: "luy ke"/"ytd" chi ep vao get_revenue_ytd_cumulative khi cau hoi la DOANH THU.

Tool nay chi tinh luy ke doanh thu. Truoc day moi cau co "luy ke" deu bi ep vao day, ke ca cau hoi cong no
va so khach moi - vong dau goi tool doanh thu roi model moi di tim nguon dung.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql


def test_luy_ke_cong_no_va_khach_moi_khong_vao_tool_doanh_thu():
    for cau in ("Công nợ lũy kế của khách hàng BGI00699 là bao nhiêu?",
                "Công nợ quá hạn lũy kế theo miền",
                "Số khách hàng mới lũy kế từ đầu năm"):
        assert nl2sql._required_tool_for_question(cau) != "get_revenue_ytd_cumulative", cau
    assert nl2sql._required_tool_for_question("Công nợ quá hạn lũy kế theo miền") == "get_receivables_overview"


def test_luy_ke_doanh_thu_van_vao_tool_ytd():
    for cau in ("Doanh thu lũy kế từ đầu năm đến nay",
                "Lũy kế YTD thực hiện so kế hoạch và cùng kỳ năm trước thế nào; cần bình quân bao nhiêu mỗi "
                "tháng còn lại để đạt kế hoạch",
                "Đội tôi đạt bao nhiêu doanh số và bao nhiêu % target tháng; MoM, YoY và YTD thế nào?"):
        assert nl2sql._required_tool_for_question(cau) == "get_revenue_ytd_cumulative", cau
