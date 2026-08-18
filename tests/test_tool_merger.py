"""
Unit test cho Tool Merger (backend/nl2sql.py::_merge_bulk_tool_calls).

Boi canh 10/08/2026: ham gop nay truoc day nam lan trong ask() nen khong test duoc, va chua hai loi
gay MAT DU LIEU AM THAM tren production:

  1. Danh dau "da gop" ke ca khi KHONG gop duoc gi (dong `merged_sub_ids.add()` nam ngoai khoi
     `if codes:`) -> lenh goi thu 2 bi bo, model nhan lai cau "Da gop ket qua... vao luot goi truoc"
     (mot loi noi doi) roi tra loi tu tin bang du lieu thieu.
  2. Chi gop MOT tham so khoa, am tham vut moi tham so khac -> hoi "so sanh khach X thang 7 voi
     thang 8" thi lenh goi thang 8 bi bo, model chi co thang 7 nhung tuong da co ca hai.

Hai test `test_khac_tham_so_phu_thi_KHONG_gop` va `test_tool_khong_co_tham_so_khoa_thi_KHONG_gop`
chinh la 2 loi tren - chung PHAI fail tren code cu va pass tren code moi.

Chi test logic thuan (pure), KHONG goi model/DB/API.

Chay:  python -m pytest tests/test_tool_merger.py -v
Hoac:  python tests/test_tool_merger.py
"""
import os
import sys

# APPEND, khong insert(0): backend/ co main.py rieng, day len dau se che mat main.py o goc repo
# va lam tests/test_phase1_phase2.py vo ngay luc thu thap ("cannot import name send_daily_digest
# from main"). Da dinh dung loi nay 1 lan (test_forecast_va_scope.py, 12/08/2026) - day la ban
# goc tu 11/08, truoc khi quy uoc append duoc lap.
_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _BACKEND not in sys.path:
    sys.path.append(_BACKEND)

from nl2sql import _merge_bulk_tool_calls, BULK_TOOLS_MAP


class FakeToolUse:
    """Gia lap block tool_use cua Anthropic API - chi can 3 thuoc tinh ma ham gop dung toi."""

    def __init__(self, tool_id, name, tool_input):
        self.id = tool_id
        self.name = name
        self.input = tool_input


def test_cung_tham_so_khac_ma_thi_GOP():
    """Hoi luong 2 nguoi cung mot ky -> gop lam 1 lenh goi mang 'MBKV1,MBKV2'."""
    calls = [
        FakeToolUse("t1", "get_salary_detail", {"employee_code": "MBKV1", "save_date": "2026-07"}),
        FakeToolUse("t2", "get_salary_detail", {"employee_code": "MBKV2", "save_date": "2026-07"}),
    ]
    merged = _merge_bulk_tool_calls(calls)

    assert merged == {"t2"}, "Lenh goi thu 2 phai duoc gop vao lenh dau"
    assert calls[0].input["employee_code"] == "MBKV1,MBKV2"
    assert calls[0].input["save_date"] == "2026-07", "Tham so phu phai giu nguyen"


def test_khac_tham_so_phu_thi_KHONG_gop():
    """LOI (2) - phai fail tren code cu.

    "So sanh doanh so khach X thang 7 voi thang 8": cung customer_code nhung KHAC khoang ngay.
    Ban cu khu trung con codes=['X'] roi VAN bo lenh goi thu 2 -> mat han du lieu thang 8.
    """
    calls = [
        FakeToolUse("t1", "get_customer_detail",
                    {"customer_code": "KH001", "date_from": "2026-07-01", "date_to": "2026-07-31"}),
        FakeToolUse("t2", "get_customer_detail",
                    {"customer_code": "KH001", "date_from": "2026-08-01", "date_to": "2026-08-10"}),
    ]
    merged = _merge_bulk_tool_calls(calls)

    assert merged == set(), "Khac khoang ngay thi PHAI chay rieng ca hai, khong duoc gop"
    assert calls[0].input["date_from"] == "2026-07-01"
    assert calls[1].input["date_from"] == "2026-08-01", "Lenh goi thang 8 phai con nguyen"


def test_tool_khong_co_tham_so_khoa_thi_KHONG_gop():
    """LOI (1) - phai fail tren code cu.

    Gia lap dung tinh huong da suyt xay ra: them "get_employee_kpi": "employee_code" vao bang gop,
    trong khi tool do KHONG he co tham so employee_code. Ban cu se bo lenh goi thu 2 trong im lang.
    """
    bad_map = dict(BULK_TOOLS_MAP)
    bad_map["get_employee_kpi"] = "employee_code"   # co y sai, giong thay doi hong o clone cu

    calls = [
        FakeToolUse("t1", "get_employee_kpi",
                    {"as_of_date": "2026-07-31", "position_code": "TDV", "filter": "all"}),
        FakeToolUse("t2", "get_employee_kpi",
                    {"as_of_date": "2026-07-31", "position_code": "QLV", "filter": "all"}),
    ]
    merged = _merge_bulk_tool_calls(calls, bulk_tools_map=bad_map)

    assert merged == set(), "Khong co tham so khoa thi TUYET DOI khong duoc danh dau da-gop"
    assert calls[1].input["position_code"] == "QLV", "Lenh goi QLV phai con nguyen"


def test_trung_hoan_toan_thi_gop_lam_mot():
    """Hai lenh goi y het nhau la du thua that -> gop lai la dung, tiet kiem token."""
    calls = [
        FakeToolUse("t1", "get_employee_daily_kpi", {"employee_code": "MBKV1", "year_month": "2026-07"}),
        FakeToolUse("t2", "get_employee_daily_kpi", {"employee_code": "MBKV1", "year_month": "2026-07"}),
    ]
    merged = _merge_bulk_tool_calls(calls)

    assert merged == {"t2"}
    assert calls[0].input["employee_code"] == "MBKV1", "Trung nhau thi khong duoc nhan doi ma"


def test_ba_nhom_lan_lon_van_tach_dung():
    """Tinh huong hon hop: 2 lenh gop duoc (cung ky) + 1 lenh khac ky -> chi gop dung cap dau."""
    calls = [
        FakeToolUse("t1", "get_salary_detail", {"employee_code": "A", "save_date": "2026-07"}),
        FakeToolUse("t2", "get_salary_detail", {"employee_code": "B", "save_date": "2026-07"}),
        FakeToolUse("t3", "get_salary_detail", {"employee_code": "A", "save_date": "2026-06"}),
    ]
    merged = _merge_bulk_tool_calls(calls)

    assert merged == {"t2"}, "Chi gop 2 lenh cung ky 2026-07"
    assert calls[0].input["employee_code"] == "A,B"
    assert calls[2].input == {"employee_code": "A", "save_date": "2026-06"}, "Ky 2026-06 phai con nguyen"


def test_tool_ngoai_bang_gop_thi_khong_dung_toi():
    """Tool khong nam trong BULK_TOOLS_MAP thi khong bao gio bi gop, du goi bao nhieu lan."""
    calls = [
        FakeToolUse("t1", "get_revenue_tree", {"area_code": "MB"}),
        FakeToolUse("t2", "get_revenue_tree", {"area_code": "MN"}),
    ]
    merged = _merge_bulk_tool_calls(calls)

    assert merged == set()
    assert calls[0].input["area_code"] == "MB"
    assert calls[1].input["area_code"] == "MN"


def test_mot_lenh_goi_duy_nhat_khong_doi_gi():
    calls = [FakeToolUse("t1", "get_salary_detail", {"employee_code": "MBKV1"})]
    merged = _merge_bulk_tool_calls(calls)

    assert merged == set()
    assert calls[0].input == {"employee_code": "MBKV1"}


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}")
                failed += 1
    print(f"\n{passed} pass, {failed} fail")
    sys.exit(1 if failed else 0)
