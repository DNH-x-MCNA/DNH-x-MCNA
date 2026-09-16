# -*- coding: utf-8 -*-
"""Nhat ky UAT 16/09/2026 - ba loi lo ra khi doc log chieu 16/09. Du lieu gia, khong cham Bravo.

1. 14:02 "Tinh/vung do phu khach thap; co hoi trang o dau" chay 110 giay, het 15.126 dong:
   get_geography_monthly_performance tra 166 dong (103k ky tu) ma KHONG co nhanh thu gon, nen luoi
   an toan cat mu con 12 dong DAU - khong phai 12 dia ban yeu nhat. Model ket luan tren 7% du lieu
   ma van noi chac chan. Kho that co 64 tinh nen test dung dung quy mo do: neu ban thu gon phinh qua
   ngan sach, luoi an toan lai cat danh sach dia ban va loi tai dien am tham.
2. Danh sach "du no lon chua qua han" truoc day chi gui cho model khi cau hoi chua tu khoa; cau
   "vi sao thieu HCM04162" khong khop tu khoa nao nen model khong he thay danh sach.
3. revenue_ytd_cumulative() thieu year_month_to thi nem TypeError -> "Loi khi chay bao cao chuan".
"""
import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt

CAU_DO_PHU = "Tỉnh/vùng độ phủ khách thấp so địa bàn tương đồng; cơ hội trắng ở đâu"
SO_TINH = 64      # dung so tinh that trong kho may 24
SO_THANG = 6


def _ket_qua_dia_ban(so_thang=SO_THANG, so_tinh=SO_TINH):
    """Cung hinh dang dong that cua geography_monthly_performance (thang x dia ban)."""
    rows = []
    for thang in range(1, so_thang + 1):
        for tinh in range(so_tinh):
            rows.append({
                "month": f"2026-{thang + 3:02d}", "unit": f"Tinh so {tinh:02d}",
                "area_code": "MB" if tinh % 2 else "MN",
                "revenue": 17_867_631_804.0 - tinh * 1_000_000, "invoices": 3405 - tinh,
                "customers": tinh + 1, "paid_quantity": 1_733_134.0,
                "aov": 5_247_468.958590308, "orders_per_customer": 1.17983367983368,
                "revenue_per_customer": 6_191_140.611226611, "mom_delta": None, "mom_pct": 1.5,
                "share_pct": 45.60601137210752, "streak_direction": None, "streak_months": 0,
                "area_avg_revenue_per_city": 5_000_000.0,
            })
    return {
        "month_from": "2026-04", "month_to": f"2026-{so_thang + 3:02d}", "dimension": "city",
        "customer_count_definition": "Khach duy nhat co hoa don trong thang.",
        "rows": rows, "so_dia_ban_khong_hien": 0, "data_as_of": "2026-09-16",
        "month_to_is_partial": True,
    }


def test_dia_ban_khong_bi_cat_mu_va_xep_dung_tieu_chi_cau_hoi():
    gon = nl2sql._payload_for_model("get_geography_monthly_performance",
                                    _ket_qua_dia_ban(), CAU_DO_PHU)

    assert "rows" not in gon                        # khong de luoi an toan cat mu 12 dong dau nua
    assert gon["tieu_chi_xep_hang"] == "customers"  # cau hoi ve DO PHU -> xep theo so khach
    assert gon["tong_so_dong_goc"] == SO_THANG * SO_TINH and gon["tong_so_dia_ban"] == SO_TINH
    assert len({m["unit"] for m in gon["tong_ca_ky_theo_dia_ban"]}) == SO_TINH
    thap = [r["customers"] for r in gon["thap_nhat_thang_cuoi"]]
    assert thap == sorted(thap) and thap[0] == 1    # dung nhung dia ban IT KHACH nhat
    assert gon["cao_nhat_thang_cuoi"][0]["customers"] == SO_TINH
    assert all(r["month"] == "2026-09" for r in gon["thap_nhat_thang_cuoi"])
    assert "KHONG duoc ket luan thieu dia ban nao" in gon["display_rule"]


def test_cau_hoi_ve_doanh_thu_thi_xep_theo_doanh_thu():
    gon = nl2sql._payload_for_model("get_geography_monthly_performance", _ket_qua_dia_ban(),
                                    "Doanh thu theo tỉnh các tháng gần đây")

    assert gon["tieu_chi_xep_hang"] == "revenue"
    doanh_thu = [r["revenue"] for r in gon["thap_nhat_thang_cuoi"]]
    assert doanh_thu == sorted(doanh_thu)


def test_du_64_dia_ban_song_sot_trong_ngan_sach_gui_model():
    """Phep kiem quan trong nhat: ban gui model phai vua ngan sach MA VAN du 64 dia ban."""
    chuoi = nl2sql._serialize_payload_for_model(
        "get_geography_monthly_performance", _ket_qua_dia_ban(), CAU_DO_PHU)

    assert len(chuoi) <= nl2sql.MAX_PAYLOAD_CHARS
    d = json.loads(chuoi)
    assert d.get("_model_view", {}).get("mode") is None   # khong roi vao che do cat bot
    assert len(d["tong_ca_ky_theo_dia_ban"]) == SO_TINH
    assert len(d["thap_nhat_thang_cuoi"]) == 10


def test_du_no_lon_chua_qua_han_luon_duoc_gui_du_cau_hoi_khong_co_tu_khoa():
    goc = {
        "receivable_status": "ok", "total_balance_end": 100.0, "total_overdue": 10.0,
        "top_overdue_customers": [{"customer_code": "KH1", "customer_name": "A",
                                   "balance_end": 10.0, "total_overdue": 10.0,
                                   "employee_code": "TDV1", "employee_name": "NV A"}],
        "du_no_lon_chua_qua_han": [{"customer_code": "HCM04162", "balance_end": 2_914_915_581.0}],
        "top_overdue_requested_count": 10, "top_overdue_returned_count": 1,
    }

    gon = nl2sql._payload_for_model("get_receivables_overview", goc, "Vì sao thiếu HCM04162")

    assert [r["customer_code"] for r in gon["du_no_lon_chua_qua_han"]] == ["HCM04162"]


def test_ytd_thieu_tham_so_thi_lay_thang_du_lieu_gan_nhat_chu_khong_vo(monkeypatch):
    monkeypatch.setattr(rt, "_revenue_data_month_range", lambda: ("2026-01", "2026-09"))
    monkeypatch.setattr(rt, "revenue_by_channel",
                        lambda *a, **k: {"total": {"revenue": 0.0, "invoices": 0},
                                         "otc": {"revenue": 0.0}, "etc": {"revenue": 0.0}})

    kq = rt.revenue_ytd_cumulative()          # TRUOC DAY: TypeError -> "Loi khi chay bao cao chuan"

    assert kq["den_thang"] == "09" and kq["tu_thang"] == "01"


def test_ytd_kho_rong_bao_loi_ro_rang(monkeypatch):
    monkeypatch.setattr(rt, "_revenue_data_month_range", lambda: (None, None))

    assert "Kho chua co hoa don" in rt.revenue_ytd_cumulative()["error"]
