# -*- coding: utf-8 -*-
"""Dua ban sua tay tren may 24 ngay 14/09/2026 vao repo co test.

Hai phan hoi nguoi dung that sang 14/09 da duoc ai do va thang tren may chay that (11:07-11:40):
  1. "Mien Nam co 7 nhom/QLV nhung chi lay duoc chi tiet 5/7" - employee_kpi loc mat nhom kenh
     MN1 'Kenh MT' va MN4 'Cho si' (is_duplicate=1).
  2. "chi tiet ca 4 quan ly" mat 6-7 vong/SQL rieng va hon 100 giay - them include_team_detail.
Ban dua vao repo khac ban tay o ba cho, moi cho khoa bang mot test duoi day:
  - chi mien loc MN1/MN4 khi hoi RIENG QLV (so dem moi vai tro khong bi cong them 2 nhom kenh);
  - doi cua QLV lay snapshot moi nhat CUA TUNG NGUOI trong thang (ban tay doc save_date=fdate);
  - bo nen context cua ee2c590 giu team_detail (neu khong, ban va tay mat tac dung).
"""
import json
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402
from test_qlv_unblocked_area_only_tools import _make_min_db  # noqa: E402

AS_OF = "2026-09-12"


def _kho(tmp_path, monkeypatch):
    db = tmp_path / "warehouse.db"
    _make_min_db(db)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE dim_chucvu (position_code TEXT, description TEXT)")

    def nv(code, name, dup, position, area):
        conn.execute("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,NULL,NULL,0,NULL)",
                     (code, name, dup, position, area, code))

    def fact(code, customer, sales, target, save_date, manager):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,0,?)",
                     (code, customer, sales, target, save_date, manager))

    # Mien Bac ghi snapshot ngay 10, rieng TDV2 ghi ngay 12 - dung hinh DNH tach snapshot theo ngay.
    nv("QLV1", "Quan ly Mot", 0, "QLV", "MB")
    fact("QLV1", "KH1", 600_000, 1_000_000, "2026-09-10", None)
    nv("TDV1", "Trinh duoc vien Mot", 0, "TDV", "MB")
    fact("TDV1", "KH2", 300_000, 500_000, "2026-09-10", "QLV1")
    nv("TDV2", "Trinh duoc vien Hai", 0, "TDV", "MB")
    fact("TDV2", "KH3", 200_000, 500_000, "2026-09-12", "QLV1")
    # Nhom kenh MN1 (is_duplicate=1) co cap duoi that la TK1.
    nv("MN1", "Kênh MT", 1, "QLV", "MN")
    fact("MN1", "KH4", 900_000, 1_000_000, "2026-09-12", None)
    nv("TK1", "Truong kenh", 0, "TK", "MN")
    fact("TK1", "KH5", 100_000, 200_000, "2026-09-12", "MN1")
    # Ban ghi trung that (khong phai nhom kenh, khong phai nguoi bi gan nham) van phai bi loc.
    nv("QLV_TRUNG", "Ban ghi trung", 1, "QLV", "MB")
    fact("QLV_TRUNG", "KH6", 1, 1_000_000, "2026-09-12", None)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db))


def _theo_ma(result):
    return {r["employee_code"]: r for r in result["rows"]}


def test_hoi_rieng_qlv_hien_nhom_kenh_va_danh_dau_nhung_van_loc_ban_ghi_trung(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)

    qlv = _theo_ma(rt.employee_kpi(AS_OF, limit=50, position_code="QLV"))

    assert set(qlv) == {"QLV1", "MN1"}
    assert qlv["MN1"]["la_nhom_kenh"] is True and qlv["QLV1"]["la_nhom_kenh"] is False


def test_cau_moi_vai_tro_khong_bi_cong_them_nhom_kenh(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)

    tat_ca = rt.employee_kpi(AS_OF, limit=50)

    assert "MN1" not in _theo_ma(tat_ca)
    assert tat_ca["total_employees"] == 4          # QLV1, TDV1, TDV2, TK1


def test_doi_cua_qlv_lay_snapshot_moi_nhat_cua_tung_nguoi_khong_ra_0(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)

    qlv = _theo_ma(rt.employee_kpi(AS_OF, limit=50, position_code="QLV", include_team_detail=True))

    doi = {t["employee_code"]: t for t in qlv["QLV1"]["team_detail"]}
    assert set(doi) == {"TDV1", "TDV2"} and qlv["QLV1"]["team_detail_count"] == 2
    # TDV1 chi co snapshot ngay 10 trong khi fdate la ngay 12: ban sua tay doc save_date=fdate ra 0.
    assert doi["TDV1"]["sales"] == 300_000 and doi["TDV1"]["pct"] == 60.0
    assert [t["employee_code"] for t in qlv["MN1"]["team_detail"]] == ["TK1"]


def test_include_team_detail_bo_qua_khi_khong_hoi_rieng_qlv(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)

    rows = rt.employee_kpi(AS_OF, limit=50, include_team_detail=True)["rows"]

    assert all("team_detail" not in r for r in rows)


def test_tool_nhan_tham_so_va_bo_nen_context_giu_doi_cua_qlv(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    schema = next(t for t in nl2sql.ALL_TOOLS if t["name"] == "get_employee_kpi")["input_schema"]
    assert "include_team_detail" in schema["properties"]

    result = rt.call_template("get_employee_kpi", {"as_of_date": AS_OF, "position_code": "QLV",
                                                   "include_team_detail": True, "limit": 50},
                              scope_role="c_level")
    assert result.get("ok") is True, result

    context = json.loads(nl2sql._serialize_payload_for_model(
        "get_employee_kpi", result["result"], "chi tiết cả 4 quản lý"))
    theo_ma = {r["employee_code"]: r for r in context["rows"]}
    assert {t["employee_code"] for t in theo_ma["QLV1"]["team_detail"]} == {"TDV1", "TDV2"}
    assert theo_ma["MN1"]["la_nhom_kenh"] is True
