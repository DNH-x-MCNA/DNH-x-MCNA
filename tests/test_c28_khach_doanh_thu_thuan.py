"""28/09/2026: C28 phan nhom khop SQL dap an - khach co mua trong cua so khi doanh thu THUAN cua cua so > 0;
khach <= 0 ca hai cua so bi loai (doi soat rieng); NV chinh chi xet dong co ma NV. Truoc day tool coi co dong hoa
don la "co mat" nen lech vai khach so voi dap an (khach chi con hang tra, khach doanh thu 0). Du lieu gia."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt

P, C = "PREVIOUS", "CURRENT"
DONG = [
    (P, "K1", "A", 100), (C, "K1", "A", 120),                           # giu nguyen NV
    (P, "K2", "A", 100), (C, "K2", "B", 50),                            # doi NV
    (P, "K3", "A", 100), (C, "K3", "A", -30),                           # ky nay chi con hang tra -> khong con mua
    (P, "K4", "A", 0), (C, "K4", "A", 0),                               # 0 ca hai ky -> loai
    (C, "K5", "A", 0),                                                  # 0 ky nay, khong co ky truoc -> loai
    (P, "K6", "UNKNOWN", 80), (P, "K6", "A", 20), (C, "K6", "A", 60),    # NV chinh chi xet dong co ma -> A
    (C, "K7", "UNKNOWN", 40),                                           # khach moi du thieu ma NV
    (P, "K8", "UNKNOWN", 50), (C, "K8", "B", 70),                       # mua ca hai ky, ky truoc khong co ma
    (P, "K9", "A", -10), (C, "K9", "A", 90),                            # ky truoc <= 0 -> khach moi
]


def _chay(monkeypatch):
    def fake_q(sql, params=()):
        if "MIN(doc_date)" in sql:
            return [{"min_date": "2025-01-01", "max_date": "2026-09-15"}]
        assert "FROM vhoadon_otc" in sql
        return [{"period": p, "customer_code": k, "employee_code": nv, "revenue": dt} for p, k, nv, dt in DONG]

    monkeypatch.setattr(rt, "_q", fake_q)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-15")
    return rt.customer_assignment_change(as_of_date="2026-08-31")


def test_phan_nhom_theo_doanh_thu_thuan_nhu_dap_an(monkeypatch):
    kq = _chay(monkeypatch)
    nhom = {g["group"]: g for g in kq["groups"]}
    assert {k: g["customers"] for k, g in nhom.items()} == {
        "STABLE_EMPLOYEE": 2, "CHANGED_EMPLOYEE": 1, "CURRENT_ONLY": 2, "PREVIOUS_ONLY": 1, "UNKNOWN_ASSIGNMENT": 1}
    assert nhom["PREVIOUS_ONLY"]["previous_revenue"] == 100 and nhom["PREVIOUS_ONLY"]["current_revenue"] == -30
    assert nhom["CURRENT_ONLY"]["previous_revenue"] == -10 and nhom["CURRENT_ONLY"]["current_revenue"] == 130
    assert kq["excluded_non_positive_customers"] == {"customers": 2, "previous_revenue": 0.0, "current_revenue": 0.0}


def test_nv_chinh_bo_qua_dong_khong_ma_va_doi_soat_du(monkeypatch):
    kq = _chay(monkeypatch)
    assert kq["stable_growth_by_employee"] == [{
        "employee_code": "A", "customers": 2, "previous_revenue": 200.0, "current_revenue": 180.0,
        "delta": -20.0, "growth_pct": -10.0}]
    assert [s["customer_code"] for s in kq["changed_customer_samples"]] == ["K2"]
    doi_soat = kq["reconciliation"]
    assert doi_soat["passed"] is True
    assert doi_soat["total_previous_revenue"] == 440 and doi_soat["total_current_revenue"] == 400
