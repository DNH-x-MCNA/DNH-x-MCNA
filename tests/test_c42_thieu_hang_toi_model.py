# -*- coding: utf-8 -*-
"""29/09/2026 (UAT C42 cham lai sau deploy): ve "SKU mat doanh so do thieu hang" khong toi duoc model.

1. get_inventory_expiry_report tra supply_risk.rows XEP THEO NHOM trang thai; ban gui model lay 6 dong dau nen voi
   focus overstock model chi thay nhom "ton khong ban", 16 SKU nguy co thieu hang chi con so dem.
2. Model tu ha min_prev_revenue cua get_sku_revenue_drop_vs_stock xuong 10 trieu du cau hoi khong neu nguong ->
   danh sach lech SQL doi chieu S47 (50 trieu, giam >=30%).
"""
import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt

C42 = "SKU nào mất doanh số do thiếu hàng; SKU nào tồn cao trong khi doanh số giảm liên tục?"


def _dong(i, status):
    return {"item_code": f"SP{i:03d}", "item_name": f"San pham {i}", "stock_qty": 10.0,
            "average_monthly_qty_3m": 5.0, "average_monthly_revenue_3m": 1_000_000.0,
            "months_of_cover": 2.0, "status": status}


def test_moi_nhom_trang_thai_deu_toi_model_du_tool_xep_theo_nhom():
    rows = ([_dong(i, "TON_KHONG_BAN_3_THANG") for i in range(11)]
            + [_dong(100 + i, "CHAM_LUAN_CHUYEN_DERIVED") for i in range(14)]
            + [_dong(200 + i, "CO_NGUY_CO_THIEU_HANG_DERIVED") for i in range(5)])
    payload = {"as_of": "2026-09-28", "rows": [], "summary": {},
               "supply_risk": {"status": "OK_DERIVED", "focus": "overstock", "rows": rows,
                               "status_counts": {"CO_NGUY_CO_THIEU_HANG_DERIVED": 16,
                                                 "CHAM_LUAN_CHUYEN_DERIVED": 28, "TON_KHONG_BAN_3_THANG": 11},
                               "recent_customer_candidates": []}}

    gui = json.loads(nl2sql._serialize_payload_for_model("get_inventory_expiry_report", payload, C42))
    hien = [r["status"] for r in gui["supply_risk"]["rows"]]

    assert hien.count("CO_NGUY_CO_THIEU_HANG_DERIVED") >= 3, hien
    assert hien.count("TON_KHONG_BAN_3_THANG") >= 3 and hien.count("CHAM_LUAN_CHUYEN_DERIVED") >= 3
    assert all("months_of_cover" not in r for r in gui["supply_risk"]["rows"])
    # So chua liet ke tinh theo goc nhin cua model: 16 thieu hang - so dong da gui.
    assert gui["supply_risk"]["so_dong_chua_hien_theo_trang_thai"]["CO_NGUY_CO_THIEU_HANG_DERIVED"] \
        == 16 - hien.count("CO_NGUY_CO_THIEU_HANG_DERIVED")


def test_nguong_c42_giu_mac_dinh_khi_cau_hoi_khong_neu(monkeypatch):
    nhan = {}

    def gia(**kwargs):
        nhan.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setitem(rt.TEMPLATES, "get_sku_revenue_drop_vs_stock", gia)
    rt.call_template("get_sku_revenue_drop_vs_stock", {"min_prev_revenue": 10_000_000, "drop_pct_threshold": 20},
                     question=C42)
    assert "min_prev_revenue" not in nhan and "drop_pct_threshold" not in nhan   # dung mac dinh 50 trieu / 30%

    nhan.clear()
    rt.call_template("get_sku_revenue_drop_vs_stock", {"min_prev_revenue": 10_000_000},
                     question="SKU nào doanh thu kỳ trước trên 10 triệu mà giảm mạnh?")
    assert nhan["min_prev_revenue"] == 10_000_000
