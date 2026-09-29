# -*- coding: utf-8 -*-
"""29/09/2026 - GET /history khong duoc la duong vong xem luong/thuong ca nhan.

call_template() chan moi tool luong voi regional_director; admin_ops bi chan khoi /chat. Nhung
_require_session_access() cho ca hai doc phien cua nguoi khac: Giam doc mien doc phien QLV thuoc
vung (QLV xem duoc luong doi minh), Admin Van Hanh doc moi phien (C-Level xem duoc luong toan cong
ty). Truoc ban sua, cau tra loi luong tra ve nguyen van qua duong doc lich su."""
import importlib.util
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import auth
import conversation_memory as cm

SO_LUONG = "Lương tháng 08 của TDV NV001: 18.500.000 đ, thưởng V15 2.300.000 đ"
SO_DOANH_THU = "Doanh thu tháng 08 của đội: 1,2 tỷ"


def _nap_main(tmp_path, monkeypatch, ten):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(cm, "DB_PATH", str(tmp_path / "memory.db"))
    cm.init()
    spec = importlib.util.spec_from_file_location(ten, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[ten] = chatbot_main
    spec.loader.exec_module(chatbot_main)
    return chatbot_main


def _luot(session_id, username, query_id, question, answer, sql_used):
    cm.create_query_run(query_id, session_id, username, question)
    cm.append_message(session_id, "user", question, query_id=query_id)
    cm.append_message(session_id, "assistant", answer, query_id=query_id)
    cm.complete_query_run(query_id, answer, sql_used=sql_used)


def _phien_qlv():
    cm.register_session("phien-qlv", "qlv.mb", "luong doi toi")
    _luot("phien-qlv", "qlv.mb", "q-luong", "Lương đội tôi tháng 8", SO_LUONG,
          ["[bao cao chuan] get_salary_detail({'year_month': '2026-08'})"])
    _luot("phien-qlv", "qlv.mb", "q-doanh-thu", "Doanh thu đội tháng 8", SO_DOANH_THU,
          ["[bao cao chuan] get_sales_summary({'year_month': '2026-08'})"])


def _noi_dung(history):
    return [m["content"] for m in history if m["role"] == "assistant"]


def test_giam_doc_mien_doc_phien_qlv_khong_thay_so_luong(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lich_su_an_luong_gd")
    auth.create_user("qlv.mb", "mat-khau-qlv-1", name="QLV", role="qlv", scope_value="MB",
                     employee_code="NV900")
    _phien_qlv()
    giam_doc = {"username": "gd.mb", "role": "regional_director", "scope_value": "MB",
                "scope_channel": None}

    history = chatbot_main.get_history("phien-qlv", giam_doc)

    assert _noi_dung(history) == [chatbot_main.NOI_DUNG_LUONG_DA_AN, SO_DOANH_THU]
    # Cau hoi cua QLV van hien (khong chua so lieu), chi cau tra loi luong bi thay.
    assert [m["content"] for m in history if m["role"] == "user"] == [
        "Lương đội tôi tháng 8", "Doanh thu đội tháng 8"]
    assert all(SO_LUONG not in m["content"] for m in history)


def test_admin_van_hanh_khong_thay_luong_ke_ca_sql_tu_do_cua_c_level(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lich_su_an_luong_ops")
    cm.register_session("phien-ceo", "ceo", "luong toan cong ty")
    _luot("phien-ceo", "ceo", "q-sql", "Top 5 TDV lương cao nhất", "Top 5: ... 45.000.000 đ",
          ["[local] SELECT employee_code, total_salary FROM fact_thongketinhluong ORDER BY 2 DESC LIMIT 5"])
    _luot("phien-ceo", "ceo", "q-tool", "Lương đội NV900", SO_LUONG,
          ["[bao cao chuan] get_salary_ranking({})"])
    _luot("phien-ceo", "ceo", "q-kpi", "KPI đội NV900", "Đạt 82% KPI",
          ["[bao cao chuan] get_employee_kpi({})"])

    history = chatbot_main.get_history("phien-ceo", {"username": "admin.dnh", "role": "admin_ops"})

    an = chatbot_main.NOI_DUNG_LUONG_DA_AN
    assert _noi_dung(history) == [an, an, "Đạt 82% KPI"]


def test_chu_phien_va_c_level_van_doc_nguyen_van(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lich_su_an_luong_chu")
    _phien_qlv()

    cua_chu = chatbot_main.get_history("phien-qlv", {"username": "qlv.mb", "role": "qlv"})
    cua_ceo = chatbot_main.get_history("phien-qlv", {"username": "ceo", "role": "c_level"})

    assert _noi_dung(cua_chu) == [SO_LUONG, SO_DOANH_THU]
    assert _noi_dung(cua_ceo) == [SO_LUONG, SO_DOANH_THU]


def test_nhan_dien_luot_luong_chi_theo_tool_luong_va_bang_luong(tmp_path, monkeypatch):
    _luot_co_so_lieu_luong = _nap_main(tmp_path, monkeypatch, "lich_su_an_luong_nhan_dien")._luot_co_so_lieu_luong

    assert _luot_co_so_lieu_luong(["[bao cao chuan] get_salary_aso_detail({'month': '2026-08'})"])
    assert _luot_co_so_lieu_luong(["[bravo] SELECT EmployeeCode FROM dbo.FACT_ThongKeTinhLuong"])
    assert not _luot_co_so_lieu_luong(["[bao cao chuan] get_employee_kpi({})"])
    assert not _luot_co_so_lieu_luong(["[bao cao chuan] get_sales_summary({'note': 'thongketinhluong'})"])
    assert not _luot_co_so_lieu_luong([])
    assert not _luot_co_so_lieu_luong(None)
