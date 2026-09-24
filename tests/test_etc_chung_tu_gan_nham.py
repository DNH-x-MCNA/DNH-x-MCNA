# -*- coding: utf-8 -*-
"""UAT 24/09/2026 - cau C44: hop dong KT.06.G1.HD.TTYTTB-NH bi bao da xuat -3,3 trieu (-4,8%).

HD cua khach DTH00244, 1 SKU: ban 2.000 roi tra lai du 2.000 -> rong 0. Phieu tra TL 00006979 ngay 16/09
cua KHACH KHAC (TBI00502), MAT HANG KHAC (80440000007) lai mang ContractId cua hop dong nay. Chung tu khac
CA khach LAN SKU la gan nham: khong tinh vao da xuat, bao rieng. Khac ma khach nhung cung SKU thi van
tinh (phan lon la cung don vi hai ma sau sap nhap). Du lieu gia (monkeypatch _q_bravo)."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def _dong(i, gia_tri, da_xuat, gan_nham=0, tien_gan_nham=0.0, khac_ma_khach=0.0):
    return {
        "Id": i, "DocNo": f"HD{i:04d}", "CustomerCode": f"KH{i:03d}", "StatusId": 1,
        "SoDong": 1, "SoDongLechGiaTri": 0, "FromDate": "2026-01-01", "ToDate": "2027-09-08",
        "GiaTri": gia_tri, "DaXuat": da_xuat, "SoHoaDon": 2, "LanXuatCuoi": "2026-08-27",
        "ConLaiNgay": 350, "SoDongGanNham": gan_nham, "TienGanNham": tien_gan_nham,
        "TienKhacMaKhach": khac_ma_khach,
    }


def test_chung_tu_khac_ca_khach_lan_sku_khong_lam_am_da_xuat(monkeypatch):
    rows = [_dong(121808, 68_571_400.0, 0.0, gan_nham=1, tien_gan_nham=-3_304_990.0),
            _dong(2, 1_000_000.0, 400_000.0)]
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)
    kq = rt.etc_contract_status(as_of_date="2026-09-23")

    kt06 = [x for x in kq["hop_dong_thuc_hien_duoi_50_pct"] if x["contract_id"] == 121808][0]
    assert kt06["da_xuat_hoa_don"] == 0 and kt06["ty_le_thuc_hien_pct"] == 0
    assert kt06["chung_tu_gan_nham_da_loai"]["so_tien"] == -3_304_990.0
    assert kq["so_hop_dong_co_chung_tu_gan_nham"] == 1
    assert kq["tong_tien_chung_tu_gan_nham_da_loai"] == -3_304_990.0
    assert kq["hop_dong_co_chung_tu_gan_nham"][0]["contract_id"] == 121808
    assert kq["tong_da_xuat_hoa_don"] == 400_000.0, "Tien gan nham khong duoc lot vao tong da xuat."
    assert "gan nham" in kq["canh_bao"]


def test_hoa_don_khac_ma_khach_cung_sku_van_tinh_va_duoc_danh_dau(monkeypatch):
    rows = [_dong(1, 1_000_000.0, 600_000.0, khac_ma_khach=200_000.0), _dong(2, 1_000_000.0, 100_000.0)]
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)
    kq = rt.etc_contract_status(as_of_date="2026-09-23")

    assert kq["tong_da_xuat_hoa_don"] == 700_000.0
    assert kq["so_hop_dong_co_hoa_don_khac_ma_khach"] == 1
    assert kq["so_hop_dong_co_chung_tu_gan_nham"] == 0 and kq["hop_dong_co_chung_tu_gan_nham"] == []


def test_sql_chi_loai_khi_khac_ca_khach_lan_sku(monkeypatch):
    bat = {}

    def _gia_q(sql, params=None):
        bat["sql"] = sql
        return []
    monkeypatch.setattr(rt, "_q_bravo", _gia_q)
    rt.etc_contract_status(as_of_date="2026-09-23")
    sql = bat["sql"]
    assert "SUM(CASE WHEN KhacKhach=1 AND KhacSku=1 THEN 0 ELSE Amount9 END) DaXuat" in sql
    assert "s.CustomerCode<>hd.CustomerCode" in sql
    assert "LEFT JOIN sku_hop_dong k ON k.Id0=m.HopDongGocId AND k.ItemCode=s.ItemCode" in sql
    assert "JOIN map_hop_dong m ON m.ContractId=s.ContractId" in sql, "Van noi qua ContractId."
