# -*- coding: utf-8 -*-
"""29/09/2026: co is_team chi bat khi cau hoi ve ĐỘI (nhom), khong bat vi "đối chiếu", "thay đổi", "đổi trả"...

Bo dau thi ca bon tu "đội/đối/đổi/đôi" cung la "doi"; truoc day moi cau co "doi" kem "khach"/"don" bi ep vao
get_customer_product_coverage (bang chi so cua doi QLV).
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql

route = nl2sql._required_tool_for_question


def test_doi_chieu_thay_doi_doi_tra_khong_bi_coi_la_doi_nhom():
    for cau in ("Đổi trả hàng của khách tháng 9", "Khách hàng nào thay đổi TDV phụ trách?",
                "Đối chiếu doanh thu khách hàng BGI00699", "Thay đổi số đơn hàng tháng này so với tháng trước",
                "Tỷ lệ chuyển đổi khách hàng tháng này", "Đối thủ cạnh tranh ảnh hưởng thế nào đến số khách?"):
        assert route(cau) != "get_customer_product_coverage", cau


def test_cau_hoi_ve_doi_van_vao_bang_chi_so_doi():
    for cau in ("Số khách hàng của đội tôi tháng này", "Đội tôi có bao nhiêu đơn hàng tháng 9?",
                "Toàn đội có bao nhiêu khách mua lại?",
                "so khach hang cua doi toi thang nay"):   # go khong dau: giu nhu cu
        assert route(cau) == "get_customer_product_coverage", cau
