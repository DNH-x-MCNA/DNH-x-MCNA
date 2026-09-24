# -*- coding: utf-8 -*-
"""24/09/2026: hop dong da ky nhung CHUA toi ngay bat dau khong phai "con hieu luc".

Truoc day tool chi xet ngay ket thuc -> hop dong bat dau sau as_of bi dem la con hieu luc voi 0% va lot
vao "chua xuat hoa don nao" / "duoi 50%" nhu the thuc hien cham. Du lieu gia (monkeypatch _q_bravo)."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def _dong(i, tu_ngay, gia_tri, da_xuat, so_hoa_don):
    return {"Id": i, "DocNo": f"HD{i}", "CustomerCode": f"KH{i}", "StatusId": 1, "SoDong": 1,
            "SoDongLechGiaTri": 0, "FromDate": tu_ngay, "ToDate": "2027-06-30", "GiaTri": gia_tri,
            "DaXuat": da_xuat, "SoHoaDon": so_hoa_don, "LanXuatCuoi": None, "ConLaiNgay": 280}


def test_hop_dong_chua_bat_dau_tach_rieng_khoi_con_hieu_luc(monkeypatch):
    rows = [_dong(1, "2026-01-01", 1_000_000.0, 300_000.0, 3),
            _dong(2, "2026-10-01", 5_000_000.0, 0.0, 0)]      # bat dau sau as_of 23/09
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)
    kq = rt.etc_contract_status(as_of_date="2026-09-23")

    assert kq["so_hop_dong_con_hieu_luc"] == 1
    assert kq["so_hop_dong_chua_bat_dau"] == 1 and kq["gia_tri_hop_dong_chua_bat_dau"] == 5_000_000.0
    assert kq["so_hop_dong_chua_xuat_hoa_don_nao"] == 0, "Chua bat dau thi chua xuat la dung, khong phai cham."
    assert [x["contract_id"] for x in kq["hop_dong_thuc_hien_duoi_50_pct"]] == [1]
    assert kq["tong_gia_tri"] == 1_000_000.0


def test_hop_dong_bat_dau_dung_ngay_as_of_la_con_hieu_luc(monkeypatch):
    rows = [_dong(1, "2026-09-23", 1_000_000.0, 0.0, 0)]
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)
    kq = rt.etc_contract_status(as_of_date="2026-09-23")
    assert kq["so_hop_dong_con_hieu_luc"] == 1 and kq["so_hop_dong_chua_bat_dau"] == 0
