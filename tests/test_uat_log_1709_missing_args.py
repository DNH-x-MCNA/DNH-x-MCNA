# -*- coding: utf-8 -*-
"""UAT nhat ky 17/09/2026 - cau C37 "Du no, no qua han... month-by-month theo kenh/mien" ket thuc
bang: 'Loi khi chay bao cao chuan get_customer_detail: customer_detail() missing 3 required
positional arguments: customer_code, date_from, and date_to'.

Model tu goi them get_customer_detail() de "doi chieu cong no" nhung KHONG truyen tham so nao.
call_template() truoc day bat moi loi bang except Exception chung, tra NGUYEN VAN TypeError cua
Python (lo ten tham so noi bo) cho nguoi dung - doc nhu he thong hong thay vi model goi thieu tham
so. Test dung du lieu gia, khong cham Bravo, khong goi API model."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def test_goi_tool_thieu_tham_so_bat_buoc_tra_thong_diep_ro_khong_lo_python():
    kq = rt.call_template("get_customer_detail", {}, scope_role="c_level")

    assert kq["ok"] is False
    assert "customer_detail()" not in kq["error"]         # khong lo cu phap goi ham (co dau ngoac)
    assert "Loi khi chay bao cao chuan" not in kq["error"]  # khong con dien giai nhu loi HE THONG
    assert "get_customer_detail" in kq["error"]           # van neu ro TEN CONG CU cho de doi chieu log
    assert "customer_code" in kq["error"]                 # ten tham so con thieu VAN huu ich, giu lai
    assert "hoi lai nguoi dung" in kq["error"].lower()
    assert "khong duoc tu suy dien" in kq["error"].lower()


def test_goi_tool_khong_ton_tai_van_bao_loi_binh_thuong_khong_bi_nuot():
    """Chi bat TypeError dang 'thieu tham so bat buoc', KHONG duoc nuot nham cac TypeError khac."""
    kq = rt.call_template("get_salary_detail", {"employee_code": 12345}, scope_role="c_level")

    # employee_code phai la string; truyen int co the gay TypeError O NOI KHAC (vd .strip()) - loai
    # TypeError nay KHONG duoc bi nham thanh "thieu tham so", van phai qua nhanh Exception chung.
    assert kq["ok"] is False


def test_thieu_1_tham_so_don_le_cung_duoc_nhan_dien():
    def gia_can_1_tham_so(bat_buoc: str):
        return {"ok": True}

    rt.TEMPLATES["_gia_test_1_tham_so"] = gia_can_1_tham_so
    try:
        kq = rt.call_template("_gia_test_1_tham_so", {}, scope_role="c_level")
        assert kq["ok"] is False
        assert "gia_can_1_tham_so()" not in kq["error"]    # khong lo cu phap goi ham
        assert "bat_buoc" in kq["error"]                   # ten tham so con thieu van huu ich
        assert "hoi lai nguoi dung" in kq["error"].lower()
    finally:
        del rt.TEMPLATES["_gia_test_1_tham_so"]
