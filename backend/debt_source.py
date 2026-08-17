# -*- coding: utf-8 -*-
"""Doc snapshot cong no truc tiep tu stored procedure goc tren SQL Server.

Day la duong doc dung chung cho ETL va bo ground-truth. Lenh EXEC duoc hard-code,
khong nhan SQL tu model/nguoi dung, connection luon rollback sau khi doc result set.
"""
from __future__ import annotations

import datetime as dt
import decimal
from dataclasses import dataclass
from typing import Any, Optional


PROCEDURE_NAME = "dbo.usp_DeptAccDueDate_GetData"
REQUIRED_COLUMNS = {
    "CustomerCode", "CustomerName", "ClassCode", "AreaCode", "CloseBal",
    "CloseBal5", "CloseBal6", "CloseBal7", "CloseBal8", "OverDueAmount",
}


@dataclass(frozen=True)
class DebtSnapshot:
    procedure: str
    as_of_date: str
    executed_at: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, decimal.Decimal):
        return float(value)
    return float(value)


def _as_date(value: Optional[Any]) -> dt.date:
    if value is None:
        return dt.date.today()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def fetch_debt_snapshot(as_of_date: Optional[Any] = None, engine=None) -> DebtSnapshot:
    """Chay dung mot SP cong no da whitelist va tra snapshot da chuan hoa.

    Tai khoan chi can ket noi DB + EXECUTE tren SP. SP co the tao temp table trong
    session; rollback trong finally dam bao runner khong commit thay doi nao.
    """
    if engine is None:
        from query_engine import _get_engine
        engine = _get_engine("bravo")
    from region_map import region_from_customer_code

    report_date = _as_date(as_of_date)
    date_from = dt.date(report_date.year, 1, 1)
    executed_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    parameters = {
        "@_DocDate1": str(date_from),
        "@_DocDate2": str(report_date),
        "@_Period1": 7,
        "@_Period2": 15,
        "@_RepType": 1,
        "@_IsPrepaymentInclude": 1,
    }

    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        if hasattr(cursor, "timeout"):
            cursor.timeout = 60
        cursor.execute(
            f"EXEC {PROCEDURE_NAME} "
            "@_DocDate1=?, @_DocDate2=?, @_Period1=?, @_Period2=?, "
            "@_RepType=?, @_IsPrepaymentInclude=?",
            *parameters.values(),
        )
        columns = None
        data = None
        while True:
            if cursor.description is not None:
                candidate = [description[0] for description in cursor.description]
                if REQUIRED_COLUMNS <= set(candidate):
                    columns = candidate
                    data = cursor.fetchall()
                    break
            if not cursor.nextset():
                break
        if columns is None or data is None:
            raise RuntimeError(
                f"{PROCEDURE_NAME} khong tra result set co du cac cot cong no bat buoc."
            )
        if not data:
            raise RuntimeError(f"{PROCEDURE_NAME} tra 0 dong; khong the dung lam ground truth.")

        index = {name: position for position, name in enumerate(columns)}
        rows = []
        for record in data:
            customer_code = record[index["CustomerCode"]]
            raw_area = record[index["AreaCode"]]
            class_code = str(record[index["ClassCode"]] or "").upper()
            area_code = "MB" if raw_area == "MB1" else raw_area
            if not area_code:
                area_code = region_from_customer_code(customer_code)
            bucket_1 = _number(record[index["CloseBal5"]])
            bucket_2 = _number(record[index["CloseBal6"]])
            bucket_3 = _number(record[index["CloseBal7"]])
            bucket_4 = _number(record[index["CloseBal8"]])
            rows.append({
                "snapshot_date": str(report_date),
                "snapshot_at": executed_at,
                "customer_code": customer_code,
                "customer_name": record[index["CustomerName"]],
                "source_class_code": class_code,
                "sales_channel": "OTC" if class_code == "TM" else "ETC",
                "area_code": area_code,
                "balance_end": _number(record[index["CloseBal"]]),
                "overdue_1_15": bucket_1,
                "overdue_15_30": bucket_2,
                "overdue_30_45": bucket_3,
                "overdue_gt_45": bucket_4,
                "total_overdue": bucket_1 + bucket_2 + bucket_3 + bucket_4,
                "source_overdue_amount": _number(record[index["OverDueAmount"]]),
            })
    finally:
        try:
            raw.rollback()
        except Exception:
            pass
        raw.close()

    return DebtSnapshot(
        procedure=PROCEDURE_NAME,
        as_of_date=str(report_date),
        executed_at=executed_at,
        parameters=parameters,
        rows=rows,
    )
