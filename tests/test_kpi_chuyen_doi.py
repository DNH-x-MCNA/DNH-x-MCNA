"""A new manager assignment supersedes last month's membership, even with a sparse roster."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import local_warehouse
import report_templates as rt


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE fact_tonghopkhachhang(employee_code TEXT, customer_code TEXT,
                amount_ct REAL, month_sale_target REAL, save_date TEXT, manager_code TEXT);
            CREATE TABLE dim_nhanvien(employee_code TEXT, name TEXT, position_code TEXT,
                area_code TEXT, dmsid TEXT, is_duplicate INTEGER, end_date TEXT, is_resigned INTEGER);
        """)
        employees = {"TP": "TP", "QOLD": "QLV", "QNEW": "QLV", "STAY": "TDV",
                     "MOVE": "TDV", "SILENT": "TDV", "NEW": "CTV"}
        conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,0,NULL,0)",
                         [(code, code, role, "MT", "D_" + code) for code, role in employees.items()])
        rows = [
            ("STAY", 50, "2026-08-31", "QOLD"),
            ("SILENT", 40, "2026-08-31", "QOLD"),  # no current-month invoice yet
            ("MOVE", 30, "2026-08-31", "QOLD"),
            ("QOLD", 120, "2026-08-31", None),
            ("QNEW", 0, "2026-08-31", None),
            ("MOVE", 10, "2026-09-02", "QOLD"),  # before the transfer
            ("MOVE", 55_866_929, "2026-09-23", "QNEW"),
            ("STAY", 941_259_047, "2026-09-23", "QOLD"),
            ("NEW", 100, "2026-09-23", "QOLD"),
            ("QOLD", 941_259_147, "2026-09-23", None),
            ("QNEW", 55_866_929, "2026-09-23", None),
        ]
        conn.executemany("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,1000000000,?,?)",
                         [(code, "KH_" + code, sales, day, mgr) for code, sales, day, mgr in rows])
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    return path


def codes(manager, date=None):
    return {r["employee_code"] for r in rt._team_of_qlv(manager, date)}


@pytest.mark.parametrize("date", [None, "2026-09-23"])
def test_transferred_employee_is_only_in_new_team(warehouse, date):
    assert codes("QOLD", date) == {"STAY", "SILENT", "NEW"}
    assert codes("QNEW", date) == {"MOVE"}


def test_sparse_snapshot_still_keeps_silent_and_new_members(warehouse):
    team = codes("QOLD", "2026-09-23")
    assert {"SILENT", "NEW"} <= team
    assert rt._kpi_snapshot("SILENT", "2026-09-23", "TDV")["sales"] == 0
    assert rt._kpi_snapshot("SILENT", "2026-09-23", "TDV")["target"] == 0


@pytest.mark.parametrize("date", ["2026-08-31", "2026-09-02"])
def test_historical_cutoff_keeps_assignment_before_transfer(warehouse, date):
    assert "MOVE" in codes("QOLD", date)
    assert "MOVE" not in codes("QNEW", date)


def test_revenue_tree_rollup_matches_children_after_transfer(warehouse):
    result = rt.revenue_tree("2026-09-23", scope_employee_code="QOLD")
    qlv, = result["tree"][0]["qlv"]
    assert qlv["sales"] == 941_259_147
    assert sum(member["sales"] for member in qlv["tdv"]) == qlv["sales"]
    assert {m["employee_code"] for m in qlv["tdv"]} == {"STAY", "SILENT", "NEW"}


def test_invoice_team_scope_does_not_keep_former_members_dms_id(warehouse):
    assert set(rt._get_team_dms_ids("QOLD", "2026-09-23")) == {"D_STAY", "D_SILENT", "D_NEW"}
    assert rt._get_team_dms_ids("QNEW", "2026-09-23") == ["D_MOVE"]


def test_explicitly_unassigned_employee_does_not_retain_old_manager(warehouse):
    with sqlite3.connect(warehouse) as conn:
        conn.execute("UPDATE fact_tonghopkhachhang SET manager_code=NULL "
                     "WHERE employee_code='MOVE' AND save_date='2026-09-23'")
    assert "MOVE" not in codes("QOLD", "2026-09-23")
    assert "MOVE" not in codes("QNEW", "2026-09-23")
