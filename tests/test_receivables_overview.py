# -*- coding: utf-8 -*-
"""Kiem chung report_templates.receivables_overview() - CHUA TUNG co test rieng cho logic tong
hop (tach kenh, tach vung, top N) truoc 19/08/2026, chi co test cho phan dong bo SP
(tests/test_debt_source.py). Khoa lai dung 3 bullet trong checklist Ngay 21 (cong no):
"Tach OTC/ETC", "Khach hai kenh khong bi cong sai", "Top no dung dung mau so".
"""
import io
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_congno_khachhang (
            snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT, customer_name TEXT,
            sales_channel TEXT, area_code TEXT, balance_end REAL,
            overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL,
            total_overdue REAL
        );
        """
    )
    rows = [
        # C1: khach 2 kenh (OTC MB + ETC MB) - phai CONG DUOC ca 2 dong khi tinh tong cua C1
        ("2026-08-19", "2026-08-19T10:00:00", "C1", "Khach C1", "OTC", "MB",
         1_000_000, 200_000, 0, 0, 0, 200_000),
        ("2026-08-19", "2026-08-19T10:00:00", "C1", "Khach C1", "ETC", "MB",
         500_000, 100_000, 0, 0, 0, 100_000),
        # C2: mien Bac (MB2) - qua han toan bo, phai dung hang 1 khi xep top no qua han
        ("2026-08-19", "2026-08-19T10:00:00", "C2", "Khach C2", "OTC", "MB2",
         2_000_000, 0, 0, 0, 2_000_000, 2_000_000),
        # C3: mien Nam, KHONG qua han - phai bi LOAI khoi top_overdue_customers (HAVING >0)
        ("2026-08-19", "2026-08-19T10:00:00", "C3", "Khach C3", "OTC", "MN",
         100_000, 0, 0, 0, 0, 0),
    ]
    conn.executemany(
        "INSERT INTO fact_congno_khachhang VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    conn.commit()
    conn.close()


def test_tong_va_tach_kenh_dung(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.receivables_overview()

    assert result["receivable_status"] == "ok"
    assert result["total_balance_end"] == 3_600_000
    assert result["total_overdue"] == 2_300_000

    by_channel = {c["channel"]: c for c in result["by_channel"]}
    assert by_channel["OTC"]["balance_end"] == 3_100_000
    assert by_channel["OTC"]["total_overdue"] == 2_200_000
    assert by_channel["ETC"]["balance_end"] == 500_000
    assert by_channel["ETC"]["total_overdue"] == 100_000


def test_gop_vung_mb_va_mb2_thanh_mien_bac(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.receivables_overview()

    by_region = {r["region"]: r for r in result["by_region"]}
    assert "Miền Bắc" in by_region
    # C1 (MB) + C2 (MB2) phai duoc GOP chung thanh "Mien Bac"
    assert by_region["Miền Bắc"]["balance_end"] == 3_500_000
    assert by_region["Miền Bắc"]["total_overdue"] == 2_300_000
    assert by_region["Miền Nam"]["balance_end"] == 100_000


def test_khach_2_kenh_khong_bi_cong_sai_va_top_no_dung_mau_so(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.receivables_overview(top_n=10)

    top = {c["customer_code"]: c for c in result["top_overdue_customers"]}
    # C1 phai la TONG ca 2 kenh (200k+100k=300k), khong phai chi 1 kenh
    assert top["C1"]["total_overdue"] == 300_000
    assert top["C1"]["balance_end"] == 1_500_000
    # C2 no qua han nhieu nhat -> dung hang 1
    assert result["top_overdue_customers"][0]["customer_code"] == "C2"
    # C3 khong qua han -> KHONG duoc xuat hien trong top (HAVING SUM(total_overdue) > 0)
    assert "C3" not in top


def test_scope_area_code_chi_loc_dung_vung(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.receivables_overview(scope_area_code="MB")

    # scope "MB" phai gom ca MB va MB2 (REGION_SQL_MARKERS["bac"]) -> C1 + C2, KHONG co C3 (MN)
    assert result["total_balance_end"] == 3_500_000
    assert result["total_overdue"] == 2_300_000
    assert result["by_region"] == []  # da gioi han 1 vung, khong tach lai theo vung nua


def test_khong_co_du_lieu_thi_bao_ro_khong_am_tham_thanh_0(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, "
        "customer_code TEXT, customer_name TEXT, sales_channel TEXT, area_code TEXT, "
        "balance_end REAL, overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, "
        "overdue_gt_45 REAL, total_overdue REAL)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.receivables_overview()

    assert result["receivable_status"] == "unavailable"
