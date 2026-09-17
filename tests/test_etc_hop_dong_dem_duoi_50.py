# -*- coding: utf-8 -*-
"""UAT 17/09/2026 - cau C44: chatbot bao "Co 50 hop dong thuc hien duoi 50%".

50 chinh la gia tri LIMIT mac dinh, khong phai tong that. Do tren Bravo cung ngay: co 1.848 hop
dong con hieu luc duoi 50%, tuc bao thieu 37 lan. Nguyen nhan: moi danh sach khac trong
etc_contract_status deu co truong dem di kem (so_hop_dong_sap_het_han,
so_hop_dong_chua_xuat_hoa_don_nao, so_hop_dong_gia_tri_bat_thuong) - RIENG danh sach duoi 50% thi
khong, nen model doc duoc 50 dong va tuong do la tat ca. Cung lop loi voi "hoi top 10 tra top 3"
cua bao cao cong no.

Du lieu gia (da monkeypatch _q_bravo), khong cham Bravo that."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def _dong(i, gia_tri, da_xuat, con_lai_ngay=100, so_dong_lech=0):
    return {
        "Id": i, "DocNo": f"HD{i:04d}", "CustomerCode": f"KH{i:03d}", "StatusId": 1,
        "SoDong": 1, "SoDongLechGiaTri": so_dong_lech,
        "FromDate": "2026-01-01", "ToDate": "2026-12-31",
        "GiaTri": gia_tri, "DaXuat": da_xuat, "SoHoaDon": 1,
        "LanXuatCuoi": "2026-09-01", "ConLaiNgay": con_lai_ngay,
    }


def test_dem_du_hop_dong_duoi_50_du_danh_sach_bi_cat(monkeypatch):
    # 120 hop dong deu duoi 50% (da xuat 10% gia tri) - nhieu hon limit mac dinh 50.
    rows = [_dong(i, 1_000_000.0, 100_000.0) for i in range(1, 121)]
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)

    kq = rt.etc_contract_status()

    assert kq["so_hop_dong_thuc_hien_duoi_50_pct"] == 120    # TONG that
    assert len(kq["hop_dong_thuc_hien_duoi_50_pct"]) == 50   # danh sach bi cat theo limit
    # Hai con so khac nhau -> model biet danh sach chi la mau, khong phai toan bo.
    assert (kq["so_hop_dong_thuc_hien_duoi_50_pct"]
            > len(kq["hop_dong_thuc_hien_duoi_50_pct"]))


def test_dem_khop_khi_danh_sach_khong_bi_cat(monkeypatch):
    rows = [_dong(i, 1_000_000.0, 100_000.0) for i in range(1, 6)]
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)

    kq = rt.etc_contract_status()

    assert kq["so_hop_dong_thuc_hien_duoi_50_pct"] == 5
    assert len(kq["hop_dong_thuc_hien_duoi_50_pct"]) == 5


def test_hop_dong_gia_tri_bat_thuong_khong_bi_tinh_vao_dem(monkeypatch):
    """Hop dong gia tri hong da bi tach rieng - khong duoc lot vao so dem duoi 50%."""
    rows = ([_dong(i, 1_000_000.0, 100_000.0) for i in range(1, 4)]
            + [_dong(90 + i, 1_000_000.0, 0.0, so_dong_lech=1) for i in range(3)])
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)

    kq = rt.etc_contract_status()

    assert kq["so_hop_dong_thuc_hien_duoi_50_pct"] == 3
    assert kq["so_hop_dong_gia_tri_bat_thuong"] == 3
