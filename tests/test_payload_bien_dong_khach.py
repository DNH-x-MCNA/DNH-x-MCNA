"""28/09/2026: get_customer_movement ca cong ty 94 KB -> luoi cat chung con 5/194 nhan vien, 5/50 khach. May 24 18/09:
"ai mo nhieu khach moi nhung mua lai thap" goi lai voi limit=200 ma van khong thay them ai. Ban gui model: du bang
nhan vien neu vua (doi QLV), khong thi bang xep hang tren TOAN BO nhan vien + tong ca doi. Du lieu gia."""
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import nl2sql  # noqa: E402

CAU_HOI = "Ai mở nhiều khách mới nhưng tỷ lệ mua lại thấp; ai tái kích hoạt tốt nhất?"


def _nhan_vien(i):
    moi = (i * 7) % 23
    return {"employee_code": f"TM{i:08d}", "employee_name": f"Nguyen Van Thu {i} (HDU{i})", "dms_id": f"DNH{i:05d}",
            "khach_moi": moi, "khach_moi_co_mua_lai": moi // 3, "doanh_thu_khach_moi": 1234567.0 * moi,
            "khach_tai_kich_hoat": (i * 5) % 31, "doanh_thu_tai_kich_hoat": 2345678.0 * ((i * 5) % 31),
            "khach_ngung_mua": i % 4, "doanh_thu_mat_do_ngung": 3456789.0 * (i % 4),
            "ty_le_mua_lai_khach_moi_pct": (moi // 3) / moi * 100 if moi else None}


def _khach(i):
    dong = {"customer_code": f"HCM{i:05d}", "customer_name": "Cong ty TNHH duoc pham so " + str(i),
            "movement": "REACTIVATED" if i % 5 == 0 else "GROWING", "current_revenue": 3110207622.0,
            "previous_revenue": 800853334.0, "delta": 2309354288.0 - i, "current_orders": 4, "previous_orders": 1,
            "has_repeat_order_current": True, "earlier_revenue_in_window": 18828968837.0, "employee_code": "DNH-CS02",
            "employee_code_this_month": "DNH-CS02", "channels": ["OTC"], "areas": ["MN"],
            "first_purchase_month": None, "employee_name": "Dang Truong"}
    if i % 5 == 0:
        dong.update(last_active_month_before_reactivation="2026-06", inactive_months_before_reactivation=1,
                    pre_stop_streak_month_count=3, pre_stop_streak_revenue=2105323209.0,
                    pre_stop_average_monthly_revenue=701774403.0, recovery_delta_vs_pre_stop_average=-271743927.0,
                    recovery_pct_vs_pre_stop_average=61.2775949)
    return dong


def _bien_dong(so_nv):
    return {"month": "2026-08", "previous_month": "2026-07", "classification_basis": "full_history",
            "summary_all_customers": {"customer_count_considered": 18493, "counts": {"NEW_OR_FIRST_OBSERVED": 323}},
            "by_employee": [_nhan_vien(i) for i in range(so_nv)],
            "summary_on_returned_top_rows": {"customer_count_considered": 50},
            "customers": [_khach(i) for i in range(50)], "canh_bao": "x" * 700, "data_as_of": "2026-09-15"}


def test_ca_cong_ty_xep_hang_tren_toan_bo_nhan_vien():
    raw = _bien_dong(194)
    assert len(json.dumps(raw, ensure_ascii=False)) > 5 * nl2sql.MAX_PAYLOAD_CHARS
    out = nl2sql._serialize_payload_for_model("get_customer_movement", raw, CAU_HOI)
    m = json.loads(out)

    assert len(out) <= nl2sql.MAX_PAYLOAD_CHARS and m["_model_view"]["mode"] == "bang_gon_du_dong"
    be = m["by_employee"]
    assert be["so_nhan_vien"] == 194
    assert be["tong_ca_doi"]["khach_moi"] == sum(r["khach_moi"] for r in raw["by_employee"])
    assert be["tong_ca_doi"]["doanh_thu_mat_do_ngung"] == sum(r["doanh_thu_mat_do_ngung"] for r in raw["by_employee"])
    mo_moi = [dict(zip(be["mo_moi_nhieu_nhat"]["cot"], d)) for d in be["mo_moi_nhieu_nhat"]["dong"]]
    assert len(mo_moi) == 20 and mo_moi[0]["khach_moi"] == max(r["khach_moi"] for r in raw["by_employee"])
    assert all(a["khach_moi"] >= b["khach_moi"] for a, b in zip(mo_moi, mo_moi[1:]))
    assert "ty_le_mua_lai_khach_moi_pct" in be["mo_moi_nhieu_nhat"]["cot"]
    tai = [dict(zip(be["tai_kich_hoat_nhieu_nhat"]["cot"], d)) for d in be["tai_kich_hoat_nhieu_nhat"]["dong"]]
    assert tai[0]["khach_tai_kich_hoat"] == 30
    assert be["mo_moi_nhieu_nhat_so_nguoi_co_so_lieu"] == sum(1 for r in raw["by_employee"] if r["khach_moi"])
    assert "TOAN BO 194" in m["_model_view"]["giai_thich"]


def test_doi_nho_giu_du_bang_nhan_vien_bot_khach_truoc():
    out = nl2sql._serialize_payload_for_model("get_customer_movement", _bien_dong(12), CAU_HOI)
    m = json.loads(out)

    assert len(out) <= nl2sql.MAX_PAYLOAD_CHARS
    assert len(m["by_employee"]["dong"]) == 12 and "dms_id" not in m["by_employee"]["cot"]
    khach = m["customers"]
    assert 10 <= len(khach["dong"]) < 50
    assert "pre_stop_average_monthly_revenue" in khach["cot"] and "recovery_pct_vs_pre_stop_average" in khach["cot"]
    assert dict(zip(khach["cot"], khach["dong"][0]))["channels"] == "OTC"
    assert "dang liet ke %d/50" % len(khach["dong"]) in m["_model_view"]["giai_thich"]


def test_payload_nho_giu_nguyen():
    raw = {"month": "2026-08", "by_employee": [_nhan_vien(1)], "customers": [_khach(1)]}
    assert json.loads(nl2sql._serialize_payload_for_model("get_customer_movement", raw, CAU_HOI)) == raw
