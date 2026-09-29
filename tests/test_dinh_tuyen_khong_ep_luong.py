# -*- coding: utf-8 -*-
"""29/09/2026: cau doanh thu/du lieu khong bi ep vao tool LUONG vi chuoi con "luong"/"thuong".

Tren cau da bo dau, "luong" nam trong "số lượng/sản lượng/chất lượng", "thuong" nam trong "thương hiệu/bình thường/
bất thường" va ten nguoi "Thương". Kem "thay doi"/"tung nguoi" la bi ep vao get_salary_ranking - model doc du lieu
luong nhay cam cho mot cau khong hoi luong.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql

route = nl2sql._required_tool_for_question
SALARY_TOOLS = {"get_salary_ranking", "get_salary_detail", "get_salary_data_quality", "get_salary_bonus_policy",
                "get_salary_achievement_summary", "get_salary_aso_detail"}


def test_cau_khong_hoi_luong_khong_vao_tool_luong():
    for cau in ("Doanh thu thương hiệu Boganic thay đổi thế nào?",
                "Doanh số của TDV Thương thay đổi thế nào so với tháng trước?",
                "Doanh thu tháng này có bình thường không, thay đổi ra sao?",
                "Tình hình kinh doanh có gì bất thường không, thay đổi thế nào?",
                "Thay đổi số lượng đơn hàng tháng này so với tháng trước",
                "Chất lượng dữ liệu thay đổi ra sao?",
                "Số lượng khách hàng từng người phụ trách",
                "so luong don hang thay doi the nao"):
        assert route(cau) not in SALARY_TOOLS, cau


def test_cau_hoi_luong_thuong_van_vao_tool_luong():
    assert route("Thưởng tháng 9 của từng người trong đội") == "get_salary_ranking"
    assert route("Lương của đội tôi thay đổi thế nào?") == "get_salary_ranking"
    assert route("luong cua doi toi thay doi the nao") == "get_salary_ranking"   # go khong dau
    assert route("thuong thang 9 tung nguoi") == "get_salary_ranking"
    assert route("Chi phí thưởng trên doanh thu") == "get_salary_ranking"
    assert route("Thưởng V25 bậc nào bằng 0?") == "get_salary_bonus_policy"
    assert route("Lương cơ bản của TDV A") == "get_salary_data_quality"
