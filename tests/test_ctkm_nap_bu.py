"""28/09/2026: chuan bi cho luc DNH nap bu DMS_DonHangCTKM + DMS_CTKM (dung tu 09/01/2026).

Do that tren Bravo: 06-12/2025 co 99,3-99,9% don DMS gan CTKM, ngay 09/01/2026 chi 140/319 don, tu 02/2026
la 0%. Moc phu lay tu dong lien ket nap sau cung khong du khi ngay cuoi nap do hoac nap bu khong theo thu
tu ngay. Kem gia tri khuyen mai DMS cho C13/M36 (bo don huy) va ban gui model du dong cho bao cao don theo
thang (truoc day 64 KB -> luoi cat chung con 0/12 dong). Du lieu gia.
"""
import json
import os
import sys

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402

CHUONG_TRINH = [{"ProgramId": 1, "ProgramCode": "KM01", "ProgramName": "Mua 10 tang 1", "Orders": 5,
                 "Customers": 4, "AssociatedRevenue": 1_000_000, "OrdersWithoutInvoice": 1,
                 "PaidProductOccurrences": 8, "GiftProductCount": 1}]


def _bravo(moc, ngay, goi=None):
    """moc: ngay cua dong lien ket cuoi; ngay: {YYYY-MM-DD: (don DMS, don co lien ket)}."""
    goi = goi if goi is not None else []

    def fn(sql, params=None):
        goi.append((sql, params or {}))
        if "LinkRowId" in sql:
            return [{"CoverageDate": moc, "LinkSyncedAt": moc, "LinkRowId": 9}]
        if "LinkedOrders" in sql:
            tu, den = str(params["date_from"]), str(params["date_to_exclusive"])
            return [{"Ky": k, "Orders": d, "LinkedOrders": g} for k, (d, g) in ngay.items() if tu <= k < den]
        return CHUONG_TRINH

    return fn


def test_ngay_cuoi_nap_do_thi_moc_phu_lui_ve_ngay_du(monkeypatch):
    ngay = {"2026-01-07": (363, 363), "2026-01-08": (362, 359), "2026-01-09": (319, 140)}
    monkeypatch.setattr(rt, "_q_bravo", _bravo("2026-01-09", ngay))

    r = rt.promotion_effectiveness("2026-01-01", "2026-01-31")

    assert r["promotion_link_last_row_date"] == "2026-01-09"
    assert r["promotion_link_coverage_to"] == "2026-01-08"
    assert r["period"] == {"from": "2026-01-01", "to": "2026-01-08"}
    assert "140/319" in r["warning"]


def test_ngay_it_don_khong_bi_coi_la_nap_do():
    assert rt._ctkm_ky_du(17, 15) is True        # 04/01/2026: ngay Chu nhat, 2 don khong dung CTKM
    assert rt._ctkm_ky_du(17, 0) is False
    assert rt._ctkm_ky_du(0, 0) is True
    assert rt._ctkm_ky_du(319, 140) is False


# Nap bu khong theo thu tu: moc nhay len 27/09 nhung thang 8 moi co mot phan.
NAP_LON_XON = {"2026-07-15": (10000, 9950), "2026-08-15": (9000, 3000), "2026-09-27": (300, 299)}


def test_ky_mac_dinh_bo_qua_thang_chua_nap_du(monkeypatch):
    monkeypatch.setattr(rt, "_q_bravo", _bravo("2026-09-27", NAP_LON_XON))

    r = rt.promotion_effectiveness()

    assert r["status"] == "ok"
    assert r["period"] == {"from": "2026-07-01", "to": "2026-07-31"}
    assert "Bo qua" in r["warning"] and "2026-08 33.3%" in r["warning"]


def test_thang_dau_ky_chua_nap_du_thi_source_gap_khong_chay_query_chinh(monkeypatch):
    goi = []
    monkeypatch.setattr(rt, "_q_bravo", _bravo("2026-09-27", NAP_LON_XON, goi))

    r = rt.promotion_effectiveness("2026-08-01", "2026-09-27")

    assert r["status"] == "source_gap" and r["programs"] == []
    assert r["thang_chua_nap_du"] == ["2026-08"]
    assert "CHUA NAP DU" in r["warning"] and "khong dung cot CTKM" in r["answer_rule"]
    assert not any("ProgramOrders" in sql for sql, _ in goi)


def test_thang_thieu_o_giua_ky_thi_cat_ky_tai_do(monkeypatch):
    goi = []
    monkeypatch.setattr(rt, "_q_bravo", _bravo("2026-09-27", NAP_LON_XON, goi))

    r = rt.promotion_effectiveness("2026-07-01", "2026-09-27")

    assert r["period"] == {"from": "2026-07-01", "to": "2026-07-31"}
    assert [t["thang"] for t in r["do_phu_lien_ket_theo_thang"]] == ["2026-07"]
    assert "chi tinh den 2026-07-31" in r["warning"]
    chinh = next(p for sql, p in goi if "ProgramOrders" in sql)
    assert str(chinh["date_to_exclusive"]) == "2026-08-01"


def test_do_phu_loi_thi_giu_cach_cu_va_bao_ra(monkeypatch):
    def fn(sql, params=None):
        if "LinkRowId" in sql:
            return [{"CoverageDate": "2026-01-09", "LinkSyncedAt": "2026-01-09", "LinkRowId": 9}]
        if "LinkedOrders" in sql:
            raise RuntimeError("Lock request time out period exceeded")
        return CHUONG_TRINH

    monkeypatch.setattr(rt, "_q_bravo", fn)
    r = rt.promotion_effectiveness()

    assert r["status"] == "ok" and r["period"] == {"from": "2025-12-01", "to": "2025-12-31"}
    assert "Lock request" in r["do_phu_lien_ket_loi"]


def _bravo_gia_tri(ngay, dong, goi):
    def fn(sql, params=None):
        goi.append((sql, params or {}))
        if "LinkedOrders" in sql:
            return [{"Ky": k, "Orders": d, "LinkedOrders": g} for k, (d, g) in ngay.items()]
        return dong
    return fn


def test_gia_tri_khuyen_mai_chi_thang_du_bo_don_huy_va_gop_mien(monkeypatch):
    goi = []
    ngay = {"2025-12-10": (13557, 13545), "2026-01-05": (11035, 2042)}
    dong = [
        {"Thang": "2025-12", "AreaCode": "MB", "PromoOrders": 8000, "GiftValue": 10e9, "MoneyValue": 2e9},
        {"Thang": "2025-12", "AreaCode": "MB2", "PromoOrders": 59, "GiftValue": 1e9, "MoneyValue": 0.5e9},
        {"Thang": "2025-12", "AreaCode": "MN", "PromoOrders": 1653, "GiftValue": 3e9, "MoneyValue": 1e9},
        {"Thang": "2026-01", "AreaCode": "MB", "PromoOrders": 1500, "GiftValue": 1e9, "MoneyValue": 0.2e9},
    ]
    monkeypatch.setattr(rt, "_q_bravo", _bravo_gia_tri(ngay, dong, goi))

    km = rt._ctkm_gia_tri_theo_thang("2025-12-01", "2026-01-31")

    assert km["status"] == "mot_phan" and km["thang_chua_nap_du"] == ["2026-01"]
    assert [t["thang"] for t in km["theo_thang"]] == ["2025-12"]
    assert km["theo_thang"][0]["tong_gia_tri_km"] == pytest.approx(17.5e9)
    mb = next(b for b in km["theo_thang_vung"] if b["vung"] == rt._AREA_TO_REGION_VI["MB"])
    assert mb["so_don_huong_km"] == 8059 and mb["gia_tri_hang_tang"] == pytest.approx(11e9)
    sql_gia_tri = goi[-1][0]
    assert "ISNULL(h.StatusId, 0)<>2" in sql_gia_tri
    assert str(goi[-1][1]["date_to_exclusive"]) == "2026-01-01", "Chi truy van cac thang da nap du."

    goi.clear()
    mien_nam = rt._ctkm_gia_tri_theo_thang("2025-12-01", "2025-12-31", scope_area_code="MN")
    assert [b["vung"] for b in mien_nam["theo_thang_vung"]] == [rt._AREA_TO_REGION_VI["MN"]]


def test_gia_tri_khuyen_mai_khi_chua_nap_thang_nao_thi_khong_chay_query_gia_tri(monkeypatch):
    goi = []
    monkeypatch.setattr(rt, "_q_bravo", _bravo_gia_tri({"2026-08-10": (9000, 0)}, [], goi))

    km = rt._ctkm_gia_tri_theo_thang("2026-08-01", "2026-08-31")

    assert km["status"] == "source_gap" and km["thang_chua_nap_du"] == ["2026-08"]
    assert km["theo_thang"] == [] and len(goi) == 1
    assert "KHONG ghi 0" in km["answer_rule"]
    assert rt._ctkm_gia_tri_theo_thang("2026-08-01", "2026-08-31", scope_channel="ETC")["status"] == "not_applicable"


def test_ty_le_khuyen_mai_tinh_tren_doanh_thu_gop_otc(monkeypatch):
    def fake_q(sql, params=()):
        if sql.startswith("PRAGMA"):
            return [{"name": "discount_rate"}, {"name": "doc_code"}]
        if "total_rows" in sql:
            return [{"total_rows": 3, "populated_rows": 3}]
        return [
            {"month": "2025-12", "channel": "OTC", "area_code": "MB", "amount9": 1000, "quantity": 1,
             "unit_price": 1000, "discount_rate": 0, "doc_code": "BH", "order_key": "A"},
            {"month": "2025-12", "channel": "OTC", "area_code": "MB", "amount9": -100, "quantity": -1,
             "unit_price": 100, "discount_rate": 0, "doc_code": "HC", "order_key": "B"},
            {"month": "2025-12", "channel": "ETC", "area_code": "MB", "amount9": 5000, "quantity": 1,
             "unit_price": 5000, "discount_rate": 0, "doc_code": "BH", "order_key": "C"},
        ]

    monkeypatch.setattr(rt, "_q", fake_q)
    vung = rt._AREA_TO_REGION_VI["MB"]
    km = {"status": "ok", "theo_thang": [{"thang": "2025-12", "tong_gia_tri_km": 250.0, "gia_tri_hang_tang": 200.0}],
          "theo_thang_vung": [{"thang": "2025-12", "vung": vung, "tong_gia_tri_km": 250.0, "gia_tri_hang_tang": 200.0}]}

    fq = rt._sales_financial_quality_by_month("2025-12-01", "2025-12-31", khuyen_mai_dms=km)

    assert fq["promotion_metric_status"] == "AVAILABLE_FROM_DMS_PROMOTION_LINK"
    thang = fq["khuyen_mai_dms"]["theo_thang"][0]
    assert thang["dt_gop_otc"] == 1000, "Chi doanh thu gop OTC duong, khong cong ETC, khong tru hang tra."
    assert thang["ty_le_km_tren_dt_gop_otc_pct"] == pytest.approx(25.0)
    assert fq["khuyen_mai_dms"]["theo_thang_vung"][0]["ty_le_hang_tang_tren_dt_gop_otc_pct"] == pytest.approx(20.0)
    assert "khuyen_mai_dms" not in rt._sales_financial_quality_by_month("2025-12-01", "2025-12-31")


def _bao_cao_don_6_thang():
    thangs = [f"2026-0{m}" for m in range(4, 10)]
    tien = lambda i: 46302581047.0 + i  # noqa: E731
    kenh = [{"month": t, "channel": c, "gross_revenue": tien(1), "discount_amount": 1766937150.58,
             "return_adjustment": 72617426.0, "invoice_revenue_after_returns": tien(2), "gift_quantity": 0.0,
             "gift_orders": 0, "total_orders": 7403, "gift_order_share_pct": 0.0, "gift_value_rate_pct": None,
             "net_revenue_after_discount_and_returns": tien(3), "discount_rate_pct": 3.8160662119,
             "return_adjustment_rate_pct": 0.1568323500, "return_threshold_pct": 2.0,
             "return_threshold_flag": "TRONG_NGUONG_DE_XUAT"} for t in thangs for c in ("ETC", "OTC")]
    mien = [{**kenh[0], "month": t, "region": v, "discount_rate_change_pp": 0.12345,
             "return_rate_change_pp": -0.0123, "gift_order_share_change_pp": None}
            for t in thangs for v in ("Miền Bắc", "Miền Nam", "Miền Trung")]
    for row in mien:
        row.pop("channel")
    ma_vung = [{**row, "area_code": "MB"} for row in mien]
    km_dong = lambda **k: {"so_don_huong_km": 11606, "gia_tri_hang_tang": 8358729946.64,  # noqa: E731
                           "gia_tri_tien_km": 2819249460.33, "tong_gia_tri_km": 11177979406.97,
                           "dt_gop_otc": 49713221313.0, "ty_le_km_tren_dt_gop_otc_pct": 22.48,
                           "ty_le_hang_tang_tren_dt_gop_otc_pct": 16.81, **k}
    fq = {"status": "ok", "rows_by_month_channel": kenh, "rows_by_month_area": ma_vung, "rows_by_month_region": mien,
          "discount_definition": "Chiet khau = Amount9 duong x DiscountRate.",
          "khuyen_mai_dms": {"status": "ok", "thang_chua_nap_du": [],
                             "do_phu_lien_ket_theo_thang": [{"thang": t, "ty_le_gan_pct": 99.6, "da_nap_du": True}
                                                            for t in thangs],
                             "theo_thang": [km_dong(thang=t) for t in thangs],
                             "theo_thang_vung": [km_dong(thang=t, vung=v) for t in thangs
                                                 for v in ("Miền Bắc", "Miền Nam", "Miền Trung")]}}
    return {"date_from": "2026-04-01", "date_to": "2026-09-23", "total_flagged": 9861,
            "top_detail": [{"stt": i, "reasons": ["HANG_TRA_DIEU_CHINH"], "revenue": -1.0, "ghi_chu": "x" * 200}
                           for i in range(3)],
            "core_result_by_month": [{"month": t, "channel": c, "total_orders": 566, "flagged_orders": 205,
                                      "revenue_including_flagged": tien(4), "core_revenue_excluding_flagged": tien(5),
                                      "flagged_revenue": tien(6), "flagged_revenue_share_pct": 82.29078470138}
                                     for t in thangs for c in ("ETC", "OTC")],
            "order_value_distribution": {"orders": 60000, "ghi_chu": "y" * 600},
            "financial_quality_by_month": fq, "return_adjustment_by_month": kenh,
            "financial_quality_by_month_area": ma_vung, "financial_quality_by_month_region": mien}


@pytest.mark.parametrize("ma, cau_hoi, phai_co", [
    ("C13", "Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu?",
     ("rows_by_month_channel", "khuyen_mai_dms.theo_thang")),
    ("M36", "Tỷ lệ trả hàng, chiết khấu và hàng tặng trên doanh thu của từng vùng thay đổi ra sao?",
     ("rows_by_month_region", "khuyen_mai_dms.theo_thang_vung")),
    ("C17", "Tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh là bao nhiêu; nơi nào vượt ngưỡng?",
     ("rows_by_month_channel", "rows_by_month_region")),
    ("C12", "Nếu loại các giao dịch bất thường, đơn lớn đột biến, trả hàng và điều chỉnh, tăng trưởng cốt lõi "
            "từng tháng còn bao nhiêu?", ("core_result_by_month", "rows_by_month_channel")),
])
def test_bao_cao_don_theo_thang_gui_model_du_dong_phan_can_cho_cau_hoi(ma, cau_hoi, phai_co):
    raw = _bao_cao_don_6_thang()
    assert len(json.dumps(raw, ensure_ascii=False)) > 3 * nl2sql.MAX_PAYLOAD_CHARS

    out = nl2sql._serialize_payload_for_model("check_order_timing", raw, cau_hoi)
    m = json.loads(out)

    assert len(out) <= nl2sql.MAX_PAYLOAD_CHARS and m["_model_view"]["mode"] == "bang_gon_du_dong", ma
    for ban_sao in ("return_adjustment_by_month", "financial_quality_by_month_area",
                    "financial_quality_by_month_region"):
        assert ban_sao not in m
    fq = m["financial_quality_by_month"]
    so_dong = {"rows_by_month_channel": 12, "rows_by_month_region": 18, "core_result_by_month": 12,
               "khuyen_mai_dms.theo_thang": 6, "khuyen_mai_dms.theo_thang_vung": 18}
    for phan in phai_co:
        goc, _, con = phan.partition(".")
        bang = m.get(goc) if goc == "core_result_by_month" else (fq[goc][con] if con else fq[goc])
        assert len(bang["dong"]) == so_dong[phan], (ma, phan)
    # Chi bo dan khi con vuot; phan cau hoi can thi khong bao gio bi bo.
    assert not set(phai_co) & set(m["_model_view"]["bo_khoi_ban_gui_model"]), ma
    assert "rows_by_month_area" not in fq
    assert "gift_value_rate_pct" not in fq.get("rows_by_month_channel", fq.get("rows_by_month_region"))["cot"]


def test_bao_cao_don_nho_giu_nguyen():
    raw = {"date_from": "2026-09-01", "financial_quality_by_month": {"status": "ok", "rows_by_month_channel": []}}
    assert json.loads(nl2sql._serialize_payload_for_model("check_order_timing", raw, "doanh thu gop")) == raw


def test_moc_phu_lay_ngay_don_moi_nhat_co_lien_ket_khong_theo_id_cuoi(monkeypatch):
    """28/09/2026: DNH nap lai CTKM, dong Id lon nhat tro don 826308 chua co trong DMS_DonHangHdr (bang don dong bo
    rieng) -> LEFT JOIN ra DocDate NULL -> tool tu choi MOI cau khuyen mai tren may that."""
    goi = []
    monkeypatch.setattr(rt, "_q_bravo", _bravo("2026-09-28", {"2026-08-15": (10000, 9990)}, goi))

    r = rt.promotion_effectiveness()

    sql_moc = " ".join(goi[0][0].split())
    assert "MAX(h.DocDate) AS CoverageDate" in sql_moc and "INNER HASH JOIN dbo.DMS_DonHangHdr" in sql_moc
    assert "ORDER BY x.Id DESC" not in sql_moc
    assert r["status"] == "ok" and r["period"] == {"from": "2026-08-01", "to": "2026-08-31"}
