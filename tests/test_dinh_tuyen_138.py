# -*- coding: utf-8 -*-
"""Khoa bat bien dinh tuyen cua ca 138 cau - bat loi cung lop voi loi M22 tung mac.

M22 tung bi day vao get_customer_movement, mot tool khong co khoang cach mua trung binh nen khong
the tra loi ve "keo dai chu ky". Loi do khong lo ra o unit test cua tung tool, cung khong lo ra khi
chay tay vai cau; no chi lo ra khi doi chieu ca bo. Test nay lam viec do voi chi phi bang 0.
"""
import importlib.util
import os
import sys
from pathlib import Path

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "kiem_dinh_tuyen_138", ROOT / "scripts" / "kiem_dinh_tuyen_138.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_doc_du_138_cau_tu_tai_lieu():
    assert len(runner.doc_bo_cau_hoi()) == 138


def test_moi_cau_ngoai_nhom_du_bao_deu_co_tool_bat_buoc():
    roi_ve_free_sql = []
    for ma, noi_dung, checker, _ in runner.doc_bo_cau_hoi():
        if checker in runner.CHECKER_MIEN_TRU:
            continue
        if not nl2sql._required_tool_for_question(noi_dung):
            roi_ve_free_sql.append((ma, checker))
    # Free-SQL la duong da tung lam hong hoan toan C02 (viet thang cot khong ton tai, retry 8 lan
    # khong tu sua). Cau nao co checker xac dinh thi phai co tool bat buoc.
    assert roi_ve_free_sql == [], "Cau roi ve free-SQL: %s" % roi_ve_free_sql


def test_moi_tool_duoc_dinh_tuyen_deu_ton_tai_trong_registry():
    thieu = []
    for _, noi_dung, _, _ in runner.doc_bo_cau_hoi():
        tool = nl2sql._required_tool_for_question(noi_dung)
        if tool and tool not in rt.TEMPLATES:
            thieu.append(tool)
    assert thieu == [], "Router tro toi tool khong ton tai: %s" % sorted(set(thieu))


def test_m22_di_dung_tool_ba_tin_hieu():
    cau_m22 = next(noi_dung for ma, noi_dung, _, _ in runner.doc_bo_cau_hoi() if ma == "M22")
    assert nl2sql._required_tool_for_question(cau_m22) == "get_customer_attrition_risk"


def test_cau_hoi_chuoi_lien_tiep_phai_vao_tool_co_chuoi():
    """13/09/2026 (ra soat 126 cau): chi get_workforce_productivity co decline_streak_months va
    below_80_streak_months. Truoc do V13 ("ai giam lien tiep 2-3 thang; nguyen nhan mat khach, it don,
    it SKU") bi luat "it don" keo sang tool do phu khach-SKU, con C47 ("duoi 80% lien tiep 3 thang")
    bi luat dia ban keo di - ca hai deu khong tra loi duoc ve "lien tiep"."""
    theo_ma = {ma: noi_dung for ma, noi_dung, _, _ in runner.doc_bo_cau_hoi()}

    for ma in ("C47", "M05", "M16", "V13"):
        assert nl2sql._required_tool_for_question(theo_ma[ma]) == "get_workforce_productivity", ma

    # Luat moi khong duoc cuop cac cau khach hang/ton kho ben canh.
    assert nl2sql._required_tool_for_question(theo_ma["M22"]) == "get_customer_attrition_risk"
    assert nl2sql._required_tool_for_question(theo_ma["V21"]) == "get_customers_silent"
