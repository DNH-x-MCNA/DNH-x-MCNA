# -*- coding: utf-8 -*-
"""29/09/2026: ba cum tu khoa bat nham trong _required_tool_for_question.

- "giam luong": sau khi bo dau "giảm lượng" (san luong) va "giảm lương" (tien luong) trung nhau -> cau luong bi
  ep vao tool do phu khach-SKU.
- "uu tien" + "khach hang" chan truoc nhanh cong no -> "can uu tien thu no" vao tool do phu.
- "thu hoi" -> tool cong no ca khi hoi thu hoi san pham.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql

route = nl2sql._required_tool_for_question


def test_giam_luong_tien_luong_khong_vao_tool_do_phu_khach():
    assert route("Vì sao TDV Nguyễn Văn A bị giảm lương tháng này?") != "get_customer_product_coverage"


def test_giam_luong_san_luong_van_vao_tool_do_phu():
    for cau in ("Khách hàng nào giảm lượng mua nhiều nhất?", "Doanh thu giảm do giảm lượng hay giảm giá?",
                "vi sao giam luong mua cua khach"):   # khong dau: giu nhu cu (y san luong)
        assert route(cau) == "get_customer_product_coverage", cau


def test_uu_tien_thu_no_vao_cong_no_uu_tien_khac_giu_nguyen():
    assert route("Khách hàng nào cần ưu tiên thu nợ?") == "get_receivables_overview"
    assert route("Khách hàng nào cần ưu tiên thu hồi công nợ trước?") == "get_receivables_overview"
    assert route("Khách hàng nào cần ưu tiên chăm sóc để tăng doanh số?") == "get_customer_product_coverage"


def test_thu_hoi_chi_la_cong_no_khi_co_chu_no_hoac_tien():
    assert route("Sản phẩm nào bị thu hồi?") != "get_receivables_overview"
    assert route("Tiến độ thu hồi nợ quá hạn tháng này") == "get_receivables_overview"
