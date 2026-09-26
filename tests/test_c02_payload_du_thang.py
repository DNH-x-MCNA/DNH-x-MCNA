"""26/09/2026 (Cost of Value, C02): chuoi 12 thang vuot MAX_PAYLOAD_CHARS nen ban rut gon chung chi gui model 5/12 thang
(3/12 sau khi them ETC theo mien) -> model goi lai get_revenue_monthly_series 12 -> 6 -> 3 thang (may 24 16-17/09: 3-4 lan
goi, 12-13 nghin dong/luot). Ban dang bang phai giu DU moi thang trong ngan sach. Du lieu gia."""
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import nl2sql  # noqa: E402

CAU = "Mỗi tháng đạt bao nhiêu phần trăm kế hoạch; thiếu/vượt bao nhiêu tiền theo toàn công ty, kênh và miền?"


def _thang(i):
    ym = f"2025-{i:02d}" if i <= 12 else f"2026-{i - 12:02d}"
    mien = [{"area_code": a, "otc_revenue": 12345678901.123 + i, "plan_otc_revenue": 23456789012.456,
             "achievement_pct": 52.63157894736842, "plan_variance": -11111110111.333,
             "actual_source": "FACT_ThongKeTinhLuong_S02"} for a in ("MB", "MT", "MN")]
    return {
        "month": ym, "otc_revenue": 48926217306.0 + i, "etc_revenue": 31627295751.0, "revenue": 80553513057.0 + i,
        "invoices": 10211, "plan_revenue": 98014716823.0, "plan_otc_revenue": 55518899591.0,
        "plan_etc_revenue": 42495817232.0, "target_source": "FACT_ThongKeTinhLuong_S02",
        "achievement_pct": 82.18512042683108, "plan_variance": -17461203766.0, "otc_by_region": mien,
        "s02_otc_company": {"actual": 48922979422.0, "target": 55518899591.0, "achievement_pct": 88.11950485764086,
                            "plan_variance": -6595920169.0, "source": "FACT_ThongKeTinhLuong_S02"},
        "otc_region_reconciliation": {"revenue_matches": True, "plan_matches": True, "revenue_sum_regions": 1.0},
        "otc_special_channels": [{"name": "Kênh MT", "area_code": "MN", "revenue": 5113615629.0,
                                  "plan_revenue": 5672814418.0, "achievement_pct": 90.14248047273243}],
        "etc_by_region": [{"area_code": a, "etc_revenue": 10542431917.0} for a in ("MB", "MT", "MN")],
        "etc_region_reconciliation": {"revenue_matches": True},
        "etc_plan_by_region": None, "etc_region_note": "Nguon chi co ke hoach ETC TOAN CONG TY ...",
        "mom_delta": 5718045734.0, "mom_pct": 7.640823179896962, "yoy_delta": -5414917719.0, "yoy_pct": -6.2987,
    }


def _payload(n):
    return {"month_from": "2025-10", "month_to": "2026-09", "so_thang": n, "months": [_thang(i) for i in range(1, n + 1)]}


def test_muoi_hai_thang_gui_du_cho_model_trong_ngan_sach():
    raw = _payload(12)
    assert len(json.dumps(raw, ensure_ascii=False)) > nl2sql.MAX_PAYLOAD_CHARS, "fixture phai vuot ngan sach"
    out = nl2sql._serialize_payload_for_model("get_revenue_monthly_series", raw, CAU)
    assert len(out) <= nl2sql.MAX_PAYLOAD_CHARS
    m = json.loads(out)
    assert m["_model_view"]["mode"] == "bang_gon_du_thang" and m["_model_view"]["so_thang"] == 12
    assert [d[0] for d in m["thang"]] == [t["month"] for t in raw["months"]], "Du 12 thang, dung thu tu."
    assert len(m["otc_theo_mien"]) == 36 and len(m["etc_theo_mien"]) == 36 and len(m["kenh_dac_biet"]) == 12
    dong = dict(zip(m["cot_thang"], m["thang"][-1]))
    assert dong["revenue"] == 80553513069 and dong["achievement_pct"] == 82.19
    assert dong["s02_otc_achievement_pct"] == 88.12 and dong["otc_mien_khop_tong"] is True
    assert m["etc_ke_hoach_theo_mien"] is None and "TOAN CONG TY" in m["etc_ghi_chu"]
    assert "collections" not in m["_model_view"], "Khong duoc roi vao ban cat chung."


def test_chuoi_ngan_giu_nguyen_dang_cu():
    raw = _payload(2)
    assert len(json.dumps(raw, ensure_ascii=False)) <= nl2sql.MAX_PAYLOAD_CHARS
    assert json.loads(nl2sql._serialize_payload_for_model("get_revenue_monthly_series", raw, CAU)) == raw


def test_boc_canh_bao_van_giu_canh_bao():
    raw = {"du_lieu": _payload(12), "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": ["x"]}
    m = json.loads(nl2sql._serialize_payload_for_model("get_revenue_monthly_series", raw, CAU))
    assert m["CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG"] == ["x"] and len(m["du_lieu"]["thang"]) == 12
