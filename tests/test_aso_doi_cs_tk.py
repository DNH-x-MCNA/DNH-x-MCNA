"""get_salary_aso_detail voi doi CS/TK (Kenh MT = MN1, Cho si = MN4/MBKV12) - khong goi Bravo that."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt  # noqa: E402


def _dong(code, position, calculated=0, final=None):
    return {"EmployeeCode": code, "EmployeeName": code, "PositionCode": position, "AreaCode": "MN",
            "IsCalASOBonus": calculated, "PassCheckASOForASO": final, "PassCheckSaleForASO": final,
            "PassCheckASOBonus": final, "ASOQuantity": 2, "ASOQuantityTarget": 3,
            "ASOPercent_R": None, "ASOBonus": 0, "IsSuspend": 0}


def _bravo(monkeypatch, dong):
    sql_da_chay = []

    def fake(sql, params):
        sql_da_chay.append(sql)
        if "MAX(SaveDate)" in sql:
            return [{"snapshot_date": "2026-08-31"}]
        return dong
    monkeypatch.setattr(rt, "_q_bravo", fake)
    return sql_da_chay


def test_doi_chi_gom_tk_tra_khong_ap_dung_thay_vi_mot_nguoi_chua_danh_gia(monkeypatch):
    # Dung hinh that 11/09: MN1 'Kenh MT' la ma khung QLV khong tinh ASO, doi chi co 1 TK.
    sql = _bravo(monkeypatch, [_dong("MN1", "QLV"), _dong("TM23100133", "TK")])

    r = rt.salary_aso_detail("2026-08", scope_role="qlv", scope_area_code="MN",
                             scope_employee_code="MN1")

    assert r["not_applicable"] is True and r["rows"] == []
    assert r["cs_tk_count"] == 1
    assert r["cs_tk_employees"][0]["employee_code"] == "TM23100133"
    assert "total_employees" not in r
    assert "NOT IN ('CS','TK')" not in sql[-1]


def test_doi_tron_tdv_va_cs_van_danh_gia_tdv_va_bao_so_cs_da_loai(monkeypatch):
    _bravo(monkeypatch, [_dong("Q1", "QLV"), _dong("T1", "TDV", calculated=1, final=1),
                         _dong("CS1", "CS", calculated=1, final=0)])

    r = rt.salary_aso_detail("2026-08", scope_role="qlv", scope_area_code="MN",
                             scope_employee_code="Q1")

    assert "not_applicable" not in r
    assert {x["employee_code"] for x in r["rows"]} == {"Q1", "T1"}
    assert r["total_passed"] == 1 and r["total_failed"] == 0
    assert r["cs_tk_excluded_count"] == 1


def test_quan_ly_co_aso_that_thi_khong_bi_giau_du_doi_la_cs(monkeypatch):
    _bravo(monkeypatch, [_dong("MBKV12", "QLV", calculated=1, final=1),
                         _dong("TM25010101", "CS"), _dong("TM25010103", "CS")])

    r = rt.salary_aso_detail("2026-08", scope_role="qlv", scope_area_code="MB",
                             scope_employee_code="MBKV12")

    assert "not_applicable" not in r
    assert [x["employee_code"] for x in r["rows"]] == ["MBKV12"]
    assert r["cs_tk_excluded_count"] == 2


def test_toan_cong_ty_khong_bi_tra_khong_ap_dung_vi_co_cs(monkeypatch):
    _bravo(monkeypatch, [_dong("T1", "TDV", calculated=1, final=0), _dong("CS1", "CS")])

    r = rt.salary_aso_detail("2026-08", scope_role="c_level")

    assert "not_applicable" not in r
    assert r["total_employees"] == 1 and r["cs_tk_excluded_count"] == 1
