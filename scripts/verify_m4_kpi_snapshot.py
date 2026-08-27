# -*- coding: utf-8 -*-
"""Kiem tra read-only ban va snapshot KPI cho M4 tren may co ket noi Bravo.

Khong goi LLM/API, khong gui email/Teams, khong ghi database. Script doi chieu ket qua cua hai
helper dang chay production voi SQL doc truc tiep, va fail neu snapshot gop thang khong phuc hoi
du ba mien hoac ManagerCode van chua theo dong moi nhat cua tung nhan vien.

Chay tu thu muc goc repo::

    python scripts/verify_m4_kpi_snapshot.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.alerts import (  # noqa: E402
    _MONTH_START_OF_LATEST_SNAPSHOT_SQL,
    get_bravo_kpi_tdv_snapshot,
    get_bravo_manager_codes,
)
from src.database import _get_bravo_engine  # noqa: E402


def _normalise_area(value):
    raw = str(value or "").strip().upper()
    aliases = {
        "MIỀN BẮC": "MB", "MIEN BAC": "MB", "BAC": "MB",
        "MIỀN NAM": "MN", "MIEN NAM": "MN", "NAM": "MN",
        "MIỀN TRUNG": "MT", "MIEN TRUNG": "MT", "TRUNG": "MT",
    }
    return aliases.get(raw, raw)


def _rows_as_dicts(result):
    return [dict(row._mapping) for row in result]


def main():
    engine = _get_bravo_engine()
    if engine is None:
        print("FAIL: thiếu BRAVO_SQL_SERVER/BRAVO_SQL_DATABASE/BRAVO_SQL_UID/BRAVO_SQL_PWD.")
        return 2

    with engine.connect() as conn:
        latest_date = conn.execute(text(
            "SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang]"
        )).scalar()

        distribution = _rows_as_dicts(conn.execute(text(f'''
            SELECT CAST([SaveDate] AS date) AS save_date, [AreaCode] AS area_code,
                   COUNT(DISTINCT [EmployeeCode]) AS employees
            FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] >= {_MONTH_START_OF_LATEST_SNAPSHOT_SQL}
            GROUP BY CAST([SaveDate] AS date), [AreaCode]
            ORDER BY save_date, area_code
        ''')))

        latest_employee_summary = _rows_as_dicts(conn.execute(text(f'''
            WITH latest AS (
                SELECT [EmployeeCode], MAX([SaveDate]) AS d
                FROM [FACT_TongHopKhachHang]
                WHERE [SaveDate] >= {_MONTH_START_OF_LATEST_SNAPSHOT_SQL}
                GROUP BY [EmployeeCode]
            ), employee_actual AS (
                SELECT f.[EmployeeCode], SUM(COALESCE(f.[Amount_Cus], 0)) AS actual
                FROM [FACT_TongHopKhachHang] f
                JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]
                GROUP BY f.[EmployeeCode]
            ), employee_target AS (
                SELECT DISTINCT f.[EmployeeCode], f.[AreaCode], f.[MonthSaleTarget]
                FROM [FACT_TongHopKhachHang] f
                JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]
            )
            SELECT t.[AreaCode] AS area_code, COUNT(DISTINCT t.[EmployeeCode]) AS employees,
                   SUM(COALESCE(t.[MonthSaleTarget], 0)) AS target,
                   SUM(COALESCE(a.actual, 0)) AS actual
            FROM employee_target t
            LEFT JOIN employee_actual a ON a.[EmployeeCode] = t.[EmployeeCode]
            GROUP BY t.[AreaCode]
            ORDER BY t.[AreaCode]
        ''')))

        manager_comparison = conn.execute(text(f'''
            WITH latest AS (
                SELECT [EmployeeCode], MAX([SaveDate]) AS d
                FROM [FACT_TongHopKhachHang]
                WHERE [SaveDate] >= {_MONTH_START_OF_LATEST_SNAPSHOT_SQL}
                GROUP BY [EmployeeCode]
            ), current_managers AS (
                SELECT DISTINCT f.[ManagerCode]
                FROM [FACT_TongHopKhachHang] f
                JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]
                WHERE f.[ManagerCode] IS NOT NULL AND f.[ManagerCode] <> ''
            ), monthly_managers AS (
                SELECT DISTINCT [ManagerCode]
                FROM [FACT_TongHopKhachHang]
                WHERE [SaveDate] >= {_MONTH_START_OF_LATEST_SNAPSHOT_SQL}
                  AND [ManagerCode] IS NOT NULL AND [ManagerCode] <> ''
            )
            SELECT
                (SELECT COUNT(*) FROM current_managers) AS current_count,
                (SELECT COUNT(*) FROM monthly_managers) AS monthly_count,
                (SELECT COUNT(*) FROM monthly_managers m
                 WHERE NOT EXISTS (SELECT 1 FROM current_managers c
                                   WHERE c.[ManagerCode] = m.[ManagerCode])) AS stale_count
        ''')).one()._mapping

        expected_managers = {
            row[0] for row in conn.execute(text(f'''
                WITH latest AS (
                    SELECT [EmployeeCode], MAX([SaveDate]) AS d
                    FROM [FACT_TongHopKhachHang]
                    WHERE [SaveDate] >= {_MONTH_START_OF_LATEST_SNAPSHOT_SQL}
                    GROUP BY [EmployeeCode]
                )
                SELECT DISTINCT f.[ManagerCode]
                FROM [FACT_TongHopKhachHang] f
                JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]
                WHERE f.[ManagerCode] IS NOT NULL AND f.[ManagerCode] <> ''
            '''))
        }

    helper_managers = get_bravo_manager_codes()
    kpi_rows = get_bravo_kpi_tdv_snapshot(
        position_codes=("TDV", "QLV"), include_duplicates=True)
    observed_areas = {
        _normalise_area(row.get("area_code") if isinstance(row, dict) else row.area_code)
        for row in kpi_rows
    }
    required_areas = {"MB", "MN", "MT"}

    failures = []
    if latest_date is None:
        failures.append("FACT_TongHopKhachHang không có snapshot")
    if not kpi_rows:
        failures.append("helper KPI trả về 0 dòng")
    if not required_areas.issubset(observed_areas):
        failures.append(f"snapshot gộp tháng thiếu miền: {sorted(required_areas - observed_areas)}")
    if helper_managers != expected_managers:
        failures.append(
            "get_bravo_manager_codes lệch SQL đối chiếu "
            f"(thừa={sorted(helper_managers - expected_managers)}, "
            f"thiếu={sorted(expected_managers - helper_managers)})")

    report = {
        "latest_snapshot": str(latest_date),
        "snapshot_distribution": distribution,
        "latest_per_employee_by_area": latest_employee_summary,
        "manager_codes": dict(manager_comparison),
        "helper_kpi_rows": len(kpi_rows),
        "helper_areas": sorted(observed_areas),
        "result": "FAIL" if failures else "PASS",
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
