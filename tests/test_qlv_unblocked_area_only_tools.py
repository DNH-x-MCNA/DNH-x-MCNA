# -*- coding: utf-8 -*-
"""19/08/2026 (thuc te): 4 tool KHONG co cot nao gan voi TUNG NHAN VIEN ca nhan (ton kho theo vung,
cong no theo khach hang/vung, lich su QLV theo to, doi soat doanh thu toan vung) nhung bi dang ky
NHAM trong _PERSON_LEVEL_TEMPLATES. Vi tai khoan QLV LUON co ca scope_area_code LAN
scope_employee_code cung luc (xem main.py), nhanh fail-closed trong call_template() CHAN HOAN TOAN
moi lan QLV goi 4 tool nay - du scope_area_code (co san, dung) la du de gioi han an toan.

Test qua DUNG call_template() - duong san xuat that nl2sql.py goi vao - khong goi thang ham, de
bat dung loai loi (fail-closed o TANG PHAN QUYEN, khac voi loi/thieu du lieu o TANG TRUY VAN)."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt

_BLOCKED_MARKER = "chua ho tro gioi han theo doi"


def _make_min_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL,
            amount REAL, is_active INTEGER);
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT,
            customer_name TEXT, sales_channel TEXT, area_code TEXT, balance_end REAL,
            overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL,
            total_overdue REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        """
    )
    conn.commit()
    conn.close()


def _call(monkeypatch, tmp_path, tool_name, args=None):
    db_path = tmp_path / "warehouse.db"
    _make_min_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    return rt.call_template(tool_name, args or {}, scope_role="qlv",
                            scope_employee_code="QLV01", scope_area_code="MB")


def test_get_inventory_by_region_khong_con_bi_chan(tmp_path, monkeypatch):
    result = _call(monkeypatch, tmp_path, "get_inventory_by_region")
    assert result.get("ok") is True, f"van con bi chan: {result}"


def test_get_receivables_overview_khong_con_bi_chan(tmp_path, monkeypatch):
    result = _call(monkeypatch, tmp_path, "get_receivables_overview")
    assert result.get("ok") is True, f"van con bi chan: {result}"


def test_get_qlv_change_history_khong_con_bi_chan(tmp_path, monkeypatch):
    result = _call(monkeypatch, tmp_path, "get_qlv_change_history")
    assert result.get("ok") is True, f"van con bi chan: {result}"


def test_get_revenue_reconciliation_khong_con_bi_chan(tmp_path, monkeypatch):
    result = _call(monkeypatch, tmp_path, "get_revenue_reconciliation")
    assert result.get("ok") is True, f"van con bi chan: {result}"


def test_get_receivables_overview_van_dung_dung_scope_area_code(tmp_path, monkeypatch):
    """Go chan xong PHAI khong lam mat co che gioi han vung dang co san - QLV van CHI thay vung MB,
    khong duoc "mo khoa" thanh toan cong ty."""
    db_path = tmp_path / "warehouse.db"
    _make_min_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO fact_congno_khachhang VALUES "
                "('2026-08-19','2026-08-19T10:00:00','KH_MB','A','OTC','MB',1000000,0,0,0,0,500000)")
    conn.execute("INSERT INTO fact_congno_khachhang VALUES "
                "('2026-08-19','2026-08-19T10:00:00','KH_MN','B','OTC','MN',9999999,0,0,0,0,9999999)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.call_template("get_receivables_overview", {}, scope_role="qlv",
                              scope_employee_code="QLV01", scope_area_code="MB")

    assert result["ok"] is True
    assert result["result"]["total_balance_end"] == 1_000_000  # chi vung MB, khong gom MN
