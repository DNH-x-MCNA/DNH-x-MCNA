# -*- coding: utf-8 -*-
"""C44/M42 (13/09/2026): hop dong ETC - gia tri, da xuat, con lai, sap het han, gia tri bat thuong.

Ba cau cum H tung bi ket luan "chua co khoa lien ket hoa don voi hop dong/goi thau ETC" nen CHUA DAT.
Kiem lai tren Bravo: vHoaDonETCTotal CO cot ContractId, phu 100% dong hoa don ETC T7-T8/2026 va khop
1.037/1.037 ma hop dong. Nhung gia tri hop dong co ban ghi hong (1 hop dong ghi don gia 295 ty/don vi),
nen moi con so tong phai TACH RIENG nhom bat thuong. Test dung du lieu gia, khong cham Bravo.
"""
import os
import sys

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def _dong(contract_id, gia_tri, da_xuat, con_lai_ngay, so_hoa_don=1, lech=0, so_dong=2):
    return {
        "Id": contract_id, "DocNo": "HD%s" % contract_id, "CustomerCode": "KH%s" % contract_id,
        "StatusId": 2, "SoDong": so_dong, "SoDongLechGiaTri": lech,
        "FromDate": "2026-01-01", "ToDate": "2026-12-31",
        "GiaTri": gia_tri, "DaXuat": da_xuat, "SoHoaDon": so_hoa_don,
        "LanXuatCuoi": "2026-09-01", "ConLaiNgay": con_lai_ngay,
    }


def _chay(monkeypatch, rows, **kw):
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-13")
    return rt.etc_contract_status(as_of_date="2026-09-13", **kw)


def test_tinh_dung_con_lai_va_ty_le_thuc_hien(monkeypatch):
    r = _chay(monkeypatch, [_dong(1, 1000.0, 400.0, 200)])

    hd = r["hop_dong_thuc_hien_duoi_50_pct"][0]
    assert hd["gia_tri_hop_dong"] == 1000 and hd["da_xuat_hoa_don"] == 400
    assert hd["con_lai"] == 600 and hd["ty_le_thuc_hien_pct"] == 40
    assert r["tong_con_lai"] == 600


def test_hop_dong_gia_tri_bat_thuong_khong_duoc_cong_vao_tong(monkeypatch):
    r = _chay(monkeypatch, [
        _dong(1, 1000.0, 400.0, 200),
        _dong(2, 3_100_000_000_000_000.0, 0.0, 200, so_hoa_don=0, lech=1),  # ban ghi hong
    ])

    assert r["tong_gia_tri"] == 1000  # KHONG gom hop dong hong
    assert r["so_hop_dong_gia_tri_bat_thuong"] == 1
    assert r["hop_dong_gia_tri_bat_thuong"][0]["contract_id"] == 2
    assert "lech qua 5%" in r["hop_dong_gia_tri_bat_thuong"][0]["ly_do_bat_thuong"]
    assert r["tong_so_hop_dong"] == 2  # van bao du tong so hop dong
    # Hop dong hong khong duoc dem vao nhom "chua xuat hoa don nao".
    assert r["so_hop_dong_chua_xuat_hoa_don_nao"] == 0


def test_sap_het_han_va_het_han(monkeypatch):
    r = _chay(monkeypatch, [
        _dong(1, 1000.0, 100.0, 10),    # sap het han
        _dong(2, 2000.0, 0.0, -5, so_hoa_don=0),  # da het han
        _dong(3, 3000.0, 500.0, 300),   # con dai han
    ], expiring_days=90)

    assert r["so_hop_dong_sap_het_han"] == 1
    assert r["gia_tri_con_lai_cua_hop_dong_sap_het_han"] == 900
    assert [x["contract_id"] for x in r["hop_dong_sap_het_han"]] == [1]
    # only_active mac dinh: hop dong het han khong tinh vao tong va khong tinh "chua xuat hoa don".
    assert r["so_hop_dong_con_hieu_luc"] == 2
    assert r["tong_gia_tri"] == 4000
    assert r["so_hop_dong_chua_xuat_hoa_don_nao"] == 0


def test_only_active_false_thi_tinh_ca_hop_dong_het_han(monkeypatch):
    r = _chay(monkeypatch, [
        _dong(1, 1000.0, 100.0, 10),
        _dong(2, 2000.0, 0.0, -5, so_hoa_don=0),
    ], only_active=False)

    assert r["tong_gia_tri"] == 3000
    assert r["so_hop_dong_chua_xuat_hoa_don_nao"] == 1


def test_gia_tri_hop_dong_truoc_vat_cung_goc_hoa_don_kiem_tra_hong_giu_nguyen(monkeypatch):
    bat = {}

    def _gia_q(sql, params=None):
        bat["sql"] = sql
        return [_dong(1, 1000.0, 400.0, 200)]

    monkeypatch.setattr(rt, "_q_bravo", _gia_q)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-13")
    r = rt.etc_contract_status(as_of_date="2026-09-13")

    assert "SUM(AmountBefVat) GiaTri" in bat["sql"]
    assert "SUM(AmountAfterVat) GiaTri" not in bat["sql"]
    assert "TRUOC VAT" in r["canh_bao"]
    # Kiem ban ghi hong (do Bravo 15/09): cach cu "AmountAfterVat lech Quantity*UnitPrice >5%" bo lot HD 115627
    # (don gia 295 ty) va tach oan hop dong thue 8%.
    assert "ABS(AmountAfterVat - Quantity*UnitPrice)" not in bat["sql"]
    assert "ABS(AmountBefVat - Quantity*UnitPrice)" in bat["sql"]
    assert "UnitPrice > 1000000000" in bat["sql"]
    assert "ABS(AmountAfterVat - AmountBefVat) >" in bat["sql"]


def test_cuon_phu_luc_ve_hop_dong_goc_va_noi_hoa_don_bang_contract_id(monkeypatch):
    bat = {}
    row = _dong(119761, 3_342_727_514.4, 3_341_737_148.0, 1)
    row.update({"DocNo": "239/DKTHG-DNH", "SoPhienBan": 2, "SoPhuLuc": 1})

    def _gia_q(sql, params=None):
        bat["sql"] = sql
        return [row]

    monkeypatch.setattr(rt, "_q_bravo", _gia_q)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-21")

    kq = rt.etc_contract_status(as_of_date="2026-09-21")
    hd = kq["hop_dong_sap_het_han"][0]

    assert hd["so_phu_luc"] == 1
    assert hd["so_phien_ban_hop_dong"] == 2
    assert hd["con_lai"] == pytest.approx(990_366.4)
    assert hd["ty_le_thuc_hien_pct"] == pytest.approx(99.9703725)
    assert "FROM dong GROUP BY Id0" in bat["sql"]
    assert "JOIN map_hop_dong m ON m.ContractId=s.ContractId" in bat["sql"]
    # Hoa don chi GAN vao hop dong qua ContractId, khong ghep theo khach/SKU (kieu S86 cu). Tu 24/09 khach
    # va SKU tren hoa don chi dung de DANH DAU chung tu gan nham (test_etc_chung_tu_gan_nham.py).
    assert "s.CustomerCode=" not in bat["sql"] and "=s.CustomerCode" not in bat["sql"]
    assert bat["sql"].count("s.ItemCode") == 1 and "LEFT JOIN sku_hop_dong k" in bat["sql"]


def test_tai_khoan_chi_xem_otc_bi_chan_tool_hop_dong_etc():
    assert rt.template_available_for_channel("get_etc_contract_status", "OTC") is False
    assert rt.template_available_for_channel("get_etc_contract_status", "ETC") is True
    assert rt.template_available_for_channel("get_etc_contract_status", None) is True
