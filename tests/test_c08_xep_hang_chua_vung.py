# -*- coding: utf-8 -*-
"""C08 UAT 23/09: tool phai chi ro xep hang cao/thap nhat nao CHUA VUNG, khong chi bat co chung.

Ca that: thang 2 (82,26%, 2 nam) chi thap hon thang 9 (87,26%, 1 nam) 5,0 diem - nho hon dao dong
binh thuong giua hai nam cua cung mot thang (10,2 diem, do tren kho that). Status
INSUFFICIENT_HISTORY da co san nhung cau tra loi van chot "thang 2 thap nhat" nhu chac chan.
Du lieu gia, khong phu thuoc warehouse.db.
"""
import datetime as real_dt
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt  # noqa: E402


class _NgayCoDinh(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 23)


def _chuoi(doanh_thu_theo_thang):
    """doanh_thu_theo_thang: {"YYYY-MM": so} -> fake revenue_monthly_series cho kenh ETC."""
    months = [{"month": ym, "etc_revenue": v, "otc_revenue": v, "revenue": 2 * v}
              for ym, v in sorted(doanh_thu_theo_thang.items())]
    months.append({"month": "2026-09", "etc_revenue": 1.0, "otc_revenue": 1.0, "revenue": 2.0})

    def fake(**kwargs):
        return {"month_from": months[0]["month"], "month_to": "2026-09", "months": months,
                "data_as_of": "2026-09-23"}
    return fake


def _chay(monkeypatch, du_lieu):
    monkeypatch.setattr(rt, "revenue_monthly_series", _chuoi(du_lieu))
    monkeypatch.setattr(rt, "_q", lambda sql, params=(): [])
    monkeypatch.setattr(rt.dt, "date", _NgayCoDinh)
    kq = rt.revenue_seasonality(months_back=24, scope_channel="ETC")
    return kq["seasonality_by_channel"][0]


def _hai_nam(gia_tri_theo_thang, bo_thang_9_nam_sau=True):
    """Tao 23 thang tron 10/2024 -> 08/2026: moi thang duong lich 2 nam, tru thang 9 chi 1 nam."""
    du_lieu = {}
    for nam in (2024, 2025, 2026):
        for thang in range(1, 13):
            ym = "%04d-%02d" % (nam, thang)
            if ym < "2024-10" or ym > "2026-08":
                continue
            du_lieu[ym] = gia_tri_theo_thang[thang] * (1.1 if nam == 2025 else 0.9)
    return du_lieu


def test_thap_nhat_sat_nut_voi_thang_it_quan_sat_bi_danh_chua_vung(monkeypatch):
    # Thang 9 chi co nam 2025 (he so 1,1): 78 x 1,1 = 85,8 -> chi so ~88, thang 2 ~82 -> chenh ~6 diem,
    # nho hon dao dong hai nam ~10 diem. Dung hinh ca C08 that (5,0 diem vs 10,2 diem).
    gia = {m: 100.0 for m in range(1, 13)}
    gia[2], gia[9] = 80.0, 78.0
    kenh = _chay(monkeypatch, _hai_nam(gia))

    assert kenh["calendar_months_with_fewer_observations"] == [9]
    thap = kenh["lowest_ranking"]
    assert thap["calendar_month"] == 2 and thap["runner_up_month"] == 9
    assert thap["robust"] is False, "Chenh nho hon dao dong ma van coi la vung - dung loi C08."
    assert "thang 9 lai chi co 1 nam du lieu" in thap["reason"]
    assert "thap hon" in thap["reason"], "Dau thap nhat phai ghi 'thap hon', khong phai 'hon'."
    assert kenh["ranking_note"] and "CHUA VUNG" in kenh["ranking_note"]


def test_thang_it_quan_sat_nhung_cach_xa_thi_van_vung(monkeypatch):
    # Thang 9 (1 nam) = 84 x 1,1 = 92,4 -> cach thang 2 ~12,7 diem, LON hon dao dong ~10 diem.
    # Chi it quan sat o thang dung thu hai thi khong du ly do bac bo xep hang.
    gia = {m: 100.0 for m in range(1, 13)}
    gia[2], gia[9] = 80.0, 84.0
    kenh = _chay(monkeypatch, _hai_nam(gia))
    assert kenh["lowest_ranking"]["calendar_month"] == 2
    assert kenh["lowest_ranking"]["gap_pts"] > kenh["year_to_year_noise_pts"]
    assert kenh["lowest_ranking"]["robust"] is True


def test_cao_nhat_tach_xa_la_vung_va_khong_bi_canh_bao_oan(monkeypatch):
    gia = {m: 100.0 for m in range(1, 13)}
    gia[12] = 160.0          # vuot xa moi thang khac
    gia[2], gia[9] = 80.0, 84.0
    kenh = _chay(monkeypatch, _hai_nam(gia))

    cao = kenh["highest_ranking"]
    assert cao["calendar_month"] == 12
    assert cao["robust"] is True and cao["reason"] is None
    assert "cao nhat" not in (kenh["ranking_note"] or ""), "Khong duoc canh bao dau cao nhat khi no vung."


def test_du_lieu_deu_va_tach_ro_thi_khong_co_ranking_note(monkeypatch):
    gia = {m: 100.0 for m in range(1, 13)}
    gia[12], gia[2] = 170.0, 50.0
    du_lieu = _hai_nam(gia)
    du_lieu["2024-09"] = gia[9] * 1.1   # bu thang 9 cho du 2 nam
    kenh = _chay(monkeypatch, du_lieu)

    assert kenh["calendar_months_with_fewer_observations"] == []
    assert kenh["lowest_ranking"]["robust"] and kenh["highest_ranking"]["robust"]
    assert kenh["ranking_note"] is None
