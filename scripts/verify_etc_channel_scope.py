# -*- coding: utf-8 -*-
"""Kiem tra read-only phan quyen kenh ETC tren warehouse.db that.

Khong goi LLM/API, khong gui Teams/email va khong ghi vao database. Chay tu root repository:
    python scripts/verify_etc_channel_scope.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import report_templates as rt


def _tool(name: str, args: dict) -> dict:
    wrapped = rt.call_template(
        name,
        args,
        scope_role="regional_director",
        scope_channel="ETC",
    )
    if not wrapped.get("ok"):
        raise AssertionError(f"{name} tra loi: {wrapped}")
    return wrapped["result"]


def _month_bounds(as_of: str) -> tuple[str, str]:
    value = dt.date.fromisoformat(as_of)
    return value.replace(day=1).isoformat(), value.isoformat()


def main() -> int:
    as_of = rt.latest_data_date()
    if not as_of:
        raise RuntimeError("Kho local chua co ngay du lieu moi nhat.")
    date_from, date_to = _month_bounds(as_of)
    checks = []

    # Mot so ban sao warehouse.db cu tren may dev chua co cot is_duplicate. Cot nay chi phuc vu
    # gan ten nhan vien, khong tham gia phep loc kenh dang kiem tra. Neu gap schema cu, bo rieng buoc
    # gan danh tinh trong TIEN TRINH SMOKE TEST (khong ghi DB, khong doi code production) de phep
    # kiem chung kenh van chay duoc. May 24 sau dong bo binh thuong phai co cot nay.
    employee_columns = {row["name"] for row in rt._q("PRAGMA table_info(dim_nhanvien)")}
    legacy_employee_schema = "is_duplicate" not in employee_columns
    if legacy_employee_schema:
        rt._not_duplicate_sql = lambda _alias: "1=1"
        rt._resolve_employee_identity = lambda code: {
            "code": code,
            "name": None,
            "position_code": None,
            "area_code": None,
            "dmsid": code,
        }

    revenue = _tool("get_revenue_by_channel", {"date_from": date_from, "date_to": date_to})
    assert revenue["otc"] == {"revenue": 0.0, "invoices": 0}, revenue
    assert revenue["total"] == revenue["etc"], revenue
    checks.append({
        "check": "revenue_by_channel",
        "result": "PASS",
        "etc_revenue": revenue["etc"]["revenue"],
        "etc_invoices": revenue["etc"]["invoices"],
        "otc_redacted": True,
    })

    mixed = rt._q(
        """WITH o AS (
               SELECT customer_code, SUM(amount9) revenue, COUNT(DISTINCT stt) invoices
               FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ? AND customer_code IS NOT NULL
               GROUP BY customer_code
           ), e AS (
               SELECT customer_code, SUM(amount9) revenue, COUNT(DISTINCT stt) invoices
               FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ? AND customer_code IS NOT NULL
               GROUP BY customer_code
           )
           SELECT e.customer_code, e.revenue, e.invoices
           FROM e INNER JOIN o ON o.customer_code=e.customer_code
           WHERE e.invoices>0 AND o.invoices>0
           ORDER BY e.revenue DESC LIMIT 1""",
        (date_from, date_to, date_from, date_to),
    )
    if mixed:
        expected = mixed[0]
        customer = _tool(
            "get_customer_detail",
            {"customer_code": expected["customer_code"], "date_from": date_from, "date_to": date_to},
        )
        assert customer["channel"] == "ETC", customer
        assert customer["revenue"] == float(expected["revenue"] or 0), customer
        assert customer["orders"] == int(expected["invoices"] or 0), customer
        checks.append({
            "check": "customer_detail_mixed_channel",
            "result": "PASS",
            "customer_code": expected["customer_code"],
            "etc_revenue": customer["revenue"],
            "otc_redacted": True,
        })
    else:
        pure_otc = rt._q(
            """SELECT o.customer_code FROM vhoadon_otc o
               WHERE o.doc_date BETWEEN ? AND ? AND o.customer_code IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM vhoadon_etc e
                     WHERE e.customer_code=o.customer_code AND e.doc_date BETWEEN ? AND ?
                 )
               LIMIT 1""",
            (date_from, date_to, date_from, date_to),
        )
        if not pure_otc:
            raise AssertionError("Khong tim thay khach hai kenh hoac khach thuan OTC de kiem tra.")
        wrapped = rt.call_template(
            "get_customer_detail",
            {"customer_code": pure_otc[0]["customer_code"], "date_from": date_from, "date_to": date_to},
            scope_role="regional_director",
            scope_channel="ETC",
        )
        result = wrapped.get("result") or {}
        assert wrapped.get("ok") and "error" in result, wrapped
        checks.append({
            "check": "customer_detail_pure_otc_denied",
            "result": "PASS",
            "customer_code": pure_otc[0]["customer_code"],
        })

    expected_flagged = rt._q(
        """SELECT COUNT(*) count
           FROM vhoadon_etc
           WHERE doc_date BETWEEN ? AND ? AND created_at IS NOT NULL
             AND ABS(CAST(julianday(created_at) - julianday(doc_date) AS INTEGER)) >= 2""",
        (date_from, date_to),
    )[0]["count"]
    timing = _tool(
        "check_order_timing",
        {"date_from": date_from, "date_to": date_to, "threshold_days": 2, "limit": 1},
    )
    assert timing["total_flagged"] == int(expected_flagged or 0), timing
    checks.append({
        "check": "order_timing",
        "result": "PASS",
        "etc_flagged": timing["total_flagged"],
        "matches_direct_etc_count": True,
    })

    print(json.dumps({
        "mode": "READ_ONLY_NO_API_NO_SEND",
        "legacy_employee_schema_bypassed_for_identity_only": legacy_employee_schema,
        "period": {"date_from": date_from, "date_to": date_to},
        "checks": checks,
        "result": "PASS",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise
