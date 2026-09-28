# -*- coding: utf-8 -*-
"""29/09/2026: "ngung mua"/"khong mua" KEM DO DAI la khach im lang (get_customers_silent).

get_customer_movement chi so thang nay voi thang truoc; "Khach hang nao ngung mua 3 thang nay?" can so ngay tu lan
mua cuoi. Cau khong neu do dai giu duong cu (movement, attrition, lifecycle).
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql

route = nl2sql._required_tool_for_question


def test_ngung_mua_kem_do_dai_vao_khach_im_lang():
    for cau in ("Khách hàng nào ngừng mua 3 tháng nay?", "Nhà thuốc nào lâu rồi không lấy hàng?",
                "Khách nào 60 ngày không mua?"):
        assert route(cau) == "get_customers_silent", cau


def test_ngung_mua_khong_neu_do_dai_giu_duong_cu():
    assert route("Khách hàng nào ngừng mua tháng này?") == "get_customer_movement"
    assert route("Doanh thu mất đi từ khách ngừng mua và doanh thu tăng thêm từ khách mới/tái kích hoạt bù được "
                 "bao nhiêu?") == "get_customer_movement"                                     # C31
    assert route("Khách lớn nào ngừng mua, giảm mua hoặc kéo dài chu kỳ mua so với lịch sử?") \
        == "get_customer_attrition_risk"                                                      # M22
