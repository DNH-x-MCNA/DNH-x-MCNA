# -*- coding: utf-8 -*-
"""18/09/2026 - cau M33: "cong cu tra ve tong so dem (68 SKU giam, 94 SKU tang, 68 SKU mat ty trong
noi bo) nhung KHONG kem danh sach chi tiet tung ma SKU".

Lan thu NAM cua lop loi danh sach bi cat am tham, va la lan dau nguyen nhan khong nam trong tool ma
nam o khau dong goi payload. Payload tho cua nhanh mode='product' do duoc 500.156 ky tu - gap 50
lan ngan sach 10.000. _serialize_payload_for_model ha dan so dong moi collection theo bac
12 -> 8 -> 5 -> 3 -> 1 -> 0, va o buoc 0 thi MOI danh sach SKU thanh mang rong trong khi cac so dem
vo huong van con nguyen. Model doc duoc con so ma khong co bang chung, nen phai tu thu nhan.

Phinh den 500k vi sau danh sach (rows, largest_revenue_declines, largest_revenue_increases,
largest_internal_share_losses, coverage_up_revenue_per_customer_down, revenue_up_coverage_down)
deu chua LAI ca dong day du ~40 truong cua cung mot SKU.

Cau hoi that la "SKU nao giam VI SAO", nen ban gui model gom thang theo nguyen nhan chinh thay vi
tra sau danh sach chong cheo nhau.

Du lieu gia, khong goi API model."""
import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql

_CAU_HOI = "SKU nao doanh thu giam do it khach mua, it don, giam luong/don hay giam gia ban?"


def _dong_sku(ma, nguyen_nhan, giam, khach_delta=-5, don_delta=-9):
    """Dong SKU day du nhu tool that tra ve - nhieu truong, moi dong nang."""
    row = {
        "code": ma, "name": f"San pham {ma} (Hop x 2 vi x 10 vien)",
        "revenue": 1_000_000_000.0, "previous_revenue": 1_000_000_000.0 - giam,
        "revenue_delta": float(giam),
        "customers": 100, "previous_customers": 100 - khach_delta,
        "customers_delta": float(khach_delta),
        "orders": 200, "previous_orders": 200 - don_delta, "orders_delta": float(don_delta),
        "quantity": 5000.0, "previous_quantity": 5200.0,
        "primary_decline_driver": nguyen_nhan,
        "internal_share_delta_pct_points": -0.35,
        "revenue_per_customer": 10_000_000.0, "previous_revenue_per_customer": 10_500_000.0,
        "revenue_per_customer_delta": -500_000.0,
        "product_gap_vs_scope_avg": 1.5, "revenue_gap_vs_scope_avg": 2.5,
        "quantity_per_order_delta": -1.2, "net_revenue_per_paid_unit_delta": -300.0,
        "current_internal_revenue_share_pct": 2.1, "previous_internal_revenue_share_pct": 2.45,
        "ghi_chu_dai": "x" * 400,
    }
    return row


def _payload_that(so_giam=66, so_tang=94):
    giam = []
    for i in range(so_giam):
        nn = ("FEWER_CUSTOMERS" if i < 47 else
              "LOWER_PAID_QUANTITY_PER_ORDER" if i < 61 else "FEWER_ORDERS")
        giam.append(_dong_sku(f"GIAM{i:03d}", nn, -(so_giam - i) * 1_000_000))
    tang = [_dong_sku(f"TANG{i:03d}", None, +(i + 1) * 1_000_000) for i in range(so_tang)]
    return {
        "mode": "product", "window_days": 80,
        "current_period": {"from": "2026-07-01", "to": "2026-09-18"},
        "previous_period": {"from": "2026-04-12", "to": "2026-06-30"},
        "comparison_basis": "80 ngay lien ke",
        "scope_totals": {"current": {"revenue": 100_040_000_000.0},
                         "previous": {"revenue": 102_250_000_000.0},
                         "revenue_delta": -2_210_000_000.0},
        "rows": giam + tang,
        "largest_revenue_declines": giam,
        "largest_revenue_increases": tang,
        "largest_internal_share_losses": giam,
        "coverage_up_revenue_per_customer_down": giam[:33],
        "revenue_up_coverage_down": tang[:8],
        "decline_driver_definition": "Chi gan nguyen nhan chinh cho SKU co revenue_delta<0...",
        "data_as_of": "2026-09-18",
    }


def _goi():
    return json.loads(nl2sql._serialize_payload_for_model(
        "get_customer_product_coverage", _payload_that(), _CAU_HOI))


def test_payload_that_vuot_xa_ngan_sach_neu_khong_rut_gon():
    """Chot lai tien de: khong co nhanh rut gon rieng thi bo ha bac se xoa sach danh sach."""
    tho = json.dumps(_payload_that(), ensure_ascii=False)
    assert len(tho) > nl2sql.MAX_PAYLOAD_CHARS * 10


def test_ban_gui_model_nam_trong_ngan_sach(  ):
    goi = json.dumps(_goi(), ensure_ascii=False)
    assert len(goi) <= nl2sql.MAX_PAYLOAD_CHARS


def test_khong_bi_ha_bac_ve_mang_rong():
    """Dau hieu cua loi cu: _model_view mode='concise_priority_view' va moi list ve 0 dong."""
    d = _goi()
    assert "_model_view" not in d
    assert d["sku_giam_theo_nguyen_nhan"]
    assert all(nhom["dan_dau"] for nhom in d["sku_giam_theo_nguyen_nhan"].values())


def test_giu_du_so_dem_that_va_ma_sku_cu_the():
    d = _goi()

    assert d["so_sku_giam"] == 66 and d["so_sku_tang"] == 94
    nhom = d["sku_giam_theo_nguyen_nhan"]
    assert nhom["FEWER_CUSTOMERS"]["so_sku"] == 47
    assert nhom["LOWER_PAID_QUANTITY_PER_ORDER"]["so_sku"] == 14
    assert nhom["FEWER_ORDERS"]["so_sku"] == 5
    # Co ma SKU that de tra loi "SKU nao", khong chi co con so.
    assert all(r["ma"].startswith("GIAM") for r in nhom["FEWER_CUSTOMERS"]["dan_dau"])


def test_moi_nhom_noi_ro_con_bao_nhieu_ma_chua_liet_ke():
    d = _goi()

    for ten, nhom in d["sku_giam_theo_nguyen_nhan"].items():
        assert len(nhom["dan_dau"]) + nhom["so_sku_chua_liet_ke"] == nhom["so_sku"], ten
    assert d["sku_giam_theo_nguyen_nhan"]["FEWER_ORDERS"]["so_sku_chua_liet_ke"] == 0


def test_moi_nhom_dan_dau_bang_ma_giam_manh_nhat():
    d = _goi()

    dan_dau = d["sku_giam_theo_nguyen_nhan"]["FEWER_CUSTOMERS"]["dan_dau"]
    muc_giam = [r["thay_doi"] for r in dan_dau]
    assert muc_giam == sorted(muc_giam)          # am nhat len truoc
    assert muc_giam[0] == -66_000_000


def test_cam_noi_la_khong_co_danh_sach():
    d = _goi()
    assert "TUYET DOI khong noi la khong co danh sach chi tiet" in d["display_rule"]


def test_nhanh_khac_mode_khong_bi_anh_huong():
    """Chi mode='product' di qua nhanh nay; mode khac giu nguyen duong cu."""
    payload = {"mode": "customer", "rows": [{"code": "KH1", "revenue": 1.0}]}
    ra = nl2sql._payload_for_model("get_customer_product_coverage", payload, _CAU_HOI)
    assert ra == payload
