"""Cham lai UAT 24/09 C24: "Tinh/vung do phu khach thap so dia ban tuong dong; co hoi trang o dau" - 136 giay.

get_geography_monthly_performance LUON tra unavailable_metrics (target/gap/TDV theo tinh); query_plan coi moi
danh sach khong rong la buoc chua du -> cau khong hoi chi tieu bi danh dau thieu nguon, model goi lai tool
roi tu viet SQL den het gio. Chi giu la gioi han khi cau hoi thuc su hoi chi tieu/phu trach theo dia ban."""
import test_management_rounds_remaining as goc
import report_templates as rt
from types import SimpleNamespace

from query_plan import QueryPlan


def _gioi_han(payload, cau):
    return QueryPlan._payload_limitation(SimpleNamespace(question=cau), payload)


def _goi(tmp_path, monkeypatch, cau):
    goc._setup(tmp_path, monkeypatch)
    kq = rt.call_template("get_geography_monthly_performance", {"dimension": "city", "months_back": 3},
                          question=cau, scope_role="c_level")
    assert kq["ok"] is True, kq
    return kq["result"]


def test_cau_do_phu_khong_hoi_chi_tieu_thi_khong_thanh_buoc_thieu(tmp_path, monkeypatch):
    r = _goi(tmp_path, monkeypatch, "Tỉnh/vùng độ phủ khách thấp so địa bàn tương đồng; cơ hội trắng ở đâu")
    assert "unavailable_metrics" not in r
    assert "target_by_city" in r["chi_so_khong_co_theo_dia_ban"], "Van bao cho model biet, chi khong chan."
    assert _gioi_han(r, "do phu khach thap") is None


def test_cau_hoi_chi_tieu_theo_tinh_van_giu_gioi_han(tmp_path, monkeypatch):
    r = _goi(tmp_path, monkeypatch, "Tỉnh nào đạt bao nhiêu % kế hoạch, hụt bao nhiêu so với chỉ tiêu?")
    assert "target_by_city" in r["unavailable_metrics"]
    assert _gioi_han(r, "ke hoach theo tinh"), "Hoi chi tieu theo tinh thi van la buoc chua du."


def test_c29_mo_ta_tool_bat_trinh_bay_theo_vung():
    # Cham lai UAT 24/09 muc 14: payload co theo_vung nhung model bo qua vi cau hoi khong noi "vung".
    import nl2sql
    tool = next(t for t in nl2sql.TEMPLATE_TOOLS if t["name"] == "get_customer_lifecycle_summary")
    assert "BAT BUOC trinh bay them bang theo vung" in tool["description"]
