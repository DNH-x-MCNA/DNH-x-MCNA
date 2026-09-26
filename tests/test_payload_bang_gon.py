"""26/09/2026: payload vuot MAX_PAYLOAD_CHARS bi luoi cat chung con vai dong -> model goi lai tool (Cost of Value may 24:
12 tool bi goi lai trong cung luot). Do kho dev: get_kpi_scorecard ca cong ty 23,7 KB -> 5/20 nguoi; get_revenue_seasonality
10,8 KB -> 5/12 thang. Dang bang giu du dong khi vua ngan sach; khong vua thi tra ban goc cho luoi cat chung (khong duoc
cat danh sach ten cot). Du lieu gia."""
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import nl2sql  # noqa: E402


def _nguoi(i):
    return {"employee_code": f"TM{i:08d}", "employee_name": f"Nguyen Van Thu {i}", "position_code": "TDV",
            "area_code": "MB", "manager_code": "MBKV2", "snapshot_date": "2026-09-23",
            "doanh_so": 123456789.123, "chi_tieu_doanh_so": 300000000.0, "pct_doanh_so": 41.15226304,
            "nguong_thuong_pct": 65, "toi_nguong_thuong": False, "trong_tam_pct_dat": 52.51575334,
            "sku": {"dat": 21.0, "chi_tieu": 25.0, "pct": 84.0}, "tai_don": {"dat": 9.0, "chi_tieu": 10, "pct": 90.0},
            "khach_moi": {"dat": 1.0, "chi_tieu": 3.0, "pct": 33.333333}, "tong_diem_kpi_bravo": 0.6225,
            "aso": {"dat": 45.0, "chi_tieu": 65, "pct": 69.23},
            "cong_no_khach_phu_trach": {"du_no": 150000000.0, "no_qua_han": 40000000.0,
                                        "no_qua_han_tren_45_ngay": 10000000.0, "so_khach_no_qua_han": 3}}


def _bang_kpi(n):
    return {"month": "2026-09", "moc_snapshot": "2026-09-23", "so_nguoi": n,
            "nhan_vien": [_nguoi(i) for i in range(n)],
            "tong_hop_theo_qlv": [{"manager_code": f"Q{i}", "so_nguoi": 10, "doanh_so": 2009776533.0,
                                   "pct_doanh_so_doi": 58.17008778581766} for i in range(8)]}


def test_bang_kpi_vuot_ngan_sach_gui_du_nguoi_dang_bang():
    raw = _bang_kpi(20)
    assert len(json.dumps(raw, ensure_ascii=False)) > nl2sql.MAX_PAYLOAD_CHARS
    out = nl2sql._serialize_payload_for_model("get_kpi_scorecard", raw, "bang kpi")
    m = json.loads(out)
    assert len(out) <= nl2sql.MAX_PAYLOAD_CHARS and m["_model_view"]["mode"] == "bang_gon_du_dong"
    assert len(m["nhan_vien"]["dong"]) == 20 and len(m["tong_hop_theo_qlv"]["dong"]) == 8
    dong = dict(zip(m["nhan_vien"]["cot"], m["nhan_vien"]["dong"][0]))
    assert dong["sku.pct"] == 84.0 and dong["cong_no_khach_phu_trach.no_qua_han"] == 40000000
    assert dong["doanh_so"] == 123456789 and dong["pct_doanh_so"] == 41.152 and dong["tong_diem_kpi_bravo"] == 0.623


def test_dang_bang_van_vuot_thi_tra_ban_goc_khong_cat_ten_cot():
    m = json.loads(nl2sql._serialize_payload_for_model("get_kpi_scorecard", _bang_kpi(80), "bang kpi"))
    assert m["_model_view"]["mode"] == "concise_priority_view"
    assert isinstance(m["nhan_vien"], list) and isinstance(m["nhan_vien"][0], dict), "Luoi cat chung tren ban goc."
    assert "sku" in m["nhan_vien"][0]


def test_mua_vu_du_12_thang_moi_kenh():
    kenh = [{"channel": c, "months": [{"calendar_month": i, "observations": 1, "average_revenue": 46420096113.0 + i,
                                       "seasonal_index_pct": 92.15180413574998} for i in range(1, 13)],
             "highest_calendar_month": {"calendar_month": 3, "seasonal_index_pct": 118.2}} for c in ("OTC", "ETC")]
    raw = {"seasonality_by_channel": kenh,
           "product_groups": {"etc_groups": [{"group": f"N{g}", "revenue_by_month": [
               {"month": f"2025-{i:02d}", "revenue": 1234567890.5} for i in range(1, 13)]} for g in range(12)]}}
    assert len(json.dumps(raw, ensure_ascii=False)) > nl2sql.MAX_PAYLOAD_CHARS
    m = json.loads(nl2sql._serialize_payload_for_model("get_revenue_seasonality", raw, "mua vu"))
    assert m["_model_view"]["mode"] == "bang_gon_du_dong"
    assert all(len(k["months"]["dong"]) == 12 for k in m["seasonality_by_channel"])


def test_payload_nho_giu_nguyen():
    raw = _bang_kpi(3)
    assert json.loads(nl2sql._serialize_payload_for_model("get_kpi_scorecard", raw, "bang kpi")) == raw
