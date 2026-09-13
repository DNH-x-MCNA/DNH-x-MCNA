# -*- coding: utf-8 -*-
"""V34 (ra soat 13/09/2026): ky duoc hoi nam TRUOC pham vi phan cong doi con giu trong kho.

fact_tonghopkhachhang chi giu ~90 ngay. Tool khuyen mai lay moc phu CTKM (09/01/2026 tren Bravo) lam
ngay chot doi, nen _get_team_dms_ids nem KhongXacDinhDuocDoi -> MOI cau hoi khuyen mai cua QLV hong
cung. _employee_scope_clause gap cung tinh huong thi canh bao roi dung doi hien tai; hai duong phai xu
ly giong nhau: lay snapshot som nhat con giu VA canh bao ro, khong im lang, khong hong cung.
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


def _kho(tmp_path, monkeypatch, co_snapshot=True):
    path = tmp_path / "warehouse.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, emp_dms_code TEXT, manager_code TEXT,
          save_date TEXT, customer_code TEXT, amount_ct REAL, month_sale_target REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
          position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
          is_resigned INTEGER, manager_area_code TEXT);
        """
    )
    con.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("TM01", "TDV 1", 0, "TDV", "MB", "D1", "2025-01-01", None, 0, None),
        ("TM02", "TDV 2", 0, "TDV", "MB", "D2", "2025-01-01", None, 0, None),
        ("MBKV2", "QLV", 0, "QLV", "MB", "KV2", "2024-01-01", None, 0, None),
    ])
    if co_snapshot:
        # Snapshot som nhat la 30/06/2026 - cau hoi ve thang 1/2026 nam TRUOC moc nay.
        con.executemany("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?,?)", [
            ("TM01", "D1", "MBKV2", "2026-06-30", "KH1", 100.0, 1000.0),
            ("TM02", "D2", "MBKV2", "2026-06-30", "KH2", 200.0, 1000.0),
            ("TM01", "D1", "MBKV2", "2026-08-31", "KH1", 150.0, 1000.0),
        ])
    con.commit(); con.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    return path


def test_ky_cu_hon_snapshot_dung_doi_som_nhat_va_canh_bao(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    rt._tool_warnings.set([])

    dms = rt._get_team_dms_ids("MBKV2", "2026-01-09")

    assert sorted(dms) == ["D1", "D2"]
    canh_bao = " ".join(rt._tool_warnings.get() or [])
    assert "DOI LICH SU KHONG CO SNAPSHOT" in canh_bao
    assert "2026-06-30" in canh_bao  # noi ro dang dung doi hinh cua moc nao


def test_ky_trong_pham_vi_snapshot_khong_phat_canh_bao(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    rt._tool_warnings.set([])

    dms = rt._get_team_dms_ids("MBKV2", "2026-08-31")

    assert sorted(dms) == ["D1"]
    assert not any("DOI LICH SU KHONG CO SNAPSHOT" in c for c in (rt._tool_warnings.get() or []))


def test_khong_co_snapshot_nao_thi_van_fail_closed(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch, co_snapshot=False)

    with pytest.raises(rt.KhongXacDinhDuocDoi):
        rt._get_team_dms_ids("MBKV2", "2026-01-09")
