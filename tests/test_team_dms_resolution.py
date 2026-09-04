"""Chot hanh vi phan giai DMSId cua doi QLV.

Boi canh (UAT that 04/09/2026, QLV TM25010183): chi 2/10 TDV phan giai duoc DMSId nen doanh thu
T1-T5/2026 chi ra ~22% so that (thang 1 bao 487,4tr / that 2.026,0tr). Cac thang T6-T8 dung vi di
duong khac (snapshot KPI khoa theo employee_code), khien bang so nhin rat hop ly - 3 thang cuoi khop
tuyet doi, 5 thang dau sai gap 4 lan, khong mot dong canh bao nao.
"""
import os
import sqlite3
import sys

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path, monkeypatch, dmsid_cua, emp_dms_cua):
    """dmsid_cua/emp_dms_cua: dict employee_code -> gia tri (None = thieu)."""
    path = tmp_path / "wh.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, position_code TEXT,
          area_code TEXT, dmsid TEXT, is_duplicate INTEGER);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT,
          manager_code TEXT, save_date TEXT, emp_dms_code TEXT, amount_ct REAL);
        """
    )
    for code in ("T1", "T2", "T3"):
        con.execute("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,0)",
                    (code, f"TDV {code}", "TDV", "MB", dmsid_cua.get(code)))
        con.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?)",
                    (code, f"KH{code}", "Q1", "2026-08-31", emp_dms_cua.get(code), 100.0))
    con.commit()
    con.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    return path


def _goi(monkeypatch):
    """Goi _get_team_dms_ids trong mot bucket canh bao, tra ve (dms_ids, canh_bao)."""
    token = rt._tool_warnings.set([])
    try:
        ids = rt._get_team_dms_ids("Q1", "2026-08-31")
        return ids, list(rt._tool_warnings.get() or [])
    finally:
        rt._tool_warnings.reset(token)


def test_du_dmsid_thi_khong_canh_bao(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch, {"T1": "D1", "T2": "D2", "T3": "D3"}, {})
    ids, canh_bao = _goi(monkeypatch)
    assert sorted(ids) == ["D1", "D2", "D3"]
    assert canh_bao == []


def test_dmsid_thieu_duoc_va_lai_tu_fact_khong_canh_bao(tmp_path, monkeypatch):
    # Kho sync cu: dim_nhanvien.dmsid NULL, nhung FACT van giu emp_dms_code -> phai va lai DU doi.
    _kho(tmp_path, monkeypatch, {"T1": "D1"}, {"T2": "D2", "T3": "D3"})
    ids, canh_bao = _goi(monkeypatch)
    assert sorted(ids) == ["D1", "D2", "D3"], "fallback qua fact_tonghopkhachhang phai va du doi"
    assert canh_bao == []


def test_phan_giai_mot_phan_PHAI_canh_bao(tmp_path, monkeypatch):
    # Ca gay ra su co 04/09/2026: chi 1/3 nguoi co DMSId, hai nguoi con lai thieu ca hai nguon.
    _kho(tmp_path, monkeypatch, {"T1": "D1"}, {})
    ids, canh_bao = _goi(monkeypatch)
    assert ids == ["D1"]
    assert canh_bao, "phan giai mot phan ma IM LANG chinh la loi da lam T1-T5 chi ra 22% so that"
    msg = canh_bao[0]
    assert "HUT" in msg
    assert "3 TDV" in msg and "1 nguoi" in msg
    assert "T2" in msg and "T3" in msg, "phai neu dich danh ai bi thieu de con di sua"


def test_khong_ai_phan_giai_duoc_thi_nem_loi_chu_khong_tra_0(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch, {}, {})
    with pytest.raises(rt.KhongXacDinhDuocDoi):
        _goi(monkeypatch)
