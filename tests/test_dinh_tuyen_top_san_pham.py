# -*- coding: utf-8 -*-
"""29/09/2026: cau "top 10 san pham" khong duoc ep vong dau vao tool KHACH HANG.

Cum "top 10 san pham" tung nam trong luat C11 (muc do tap trung top khach/SKU/mien) tra get_top_customers, nen
"Top 10 san pham ban chay nhat?" - goi y tren man chao cua moi nguoi dung - va cau backlog 14/08 "top 10 OTC va
top 10 ETC khac nhau the nao" deu bi goi get_top_customers truoc, ton them mot vong tool.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql


def test_top_10_san_pham_vao_tool_san_pham():
    for cau in ("Top 10 sản phẩm bán chạy nhất?",
                "Top 10 sản phẩm OTC và top 10 ETC có khác nhau thế nào?",
                "top 10 san pham doanh thu cao nhat mien bac"):
        assert nl2sql._required_tool_for_question(cau) == "get_top_products", cau


def test_c11_va_top_khach_van_vao_top_customers():
    c11 = ("Doanh thu đang phụ thuộc vào top 10 khách hàng, top 10 sản phẩm và top 3 miền/vùng ở mức nào; "
           "xu hướng tập trung tăng hay giảm?")
    assert nl2sql._required_tool_for_question(c11) == "get_top_customers"
    assert nl2sql._required_tool_for_question("Top 10 khách hàng doanh thu cao nhất tháng 9") == "get_top_customers"
