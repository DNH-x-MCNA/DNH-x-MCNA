# -*- coding: utf-8 -*-
"""Đối chiếu tổng doanh số các QLV đã cấu hình với doanh số toàn miền.

Chỉ đọc ``warehouse.db``; không gọi LLM/API và không gửi Teams/email. Chạy sau khi điền đủ danh
sách QLV trong ``config/config.yaml`` và trước khi bật lịch gửi thật::

    python scripts/verify_qlv_digest_reconciliation.py --as-of 2026-08-27
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import sys
from pathlib import Path

import yaml


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.qlv_digest import build_qlv_digest_metrics  # noqa: E402


def _load_report_recipients() -> list[dict]:
    config = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8")) or {}
    return config.get("report_recipients") or []


def _discover_qlv_recipients(report_tools, as_of: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Tìm QLV từ snapshot KPI để kiểm tra trước khi có mapping người nhận Teams."""
    latest_rows = report_tools._q(
        "SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?",
        (as_of,),
    )
    latest = latest_rows[0].get("d") if latest_rows else None
    if not latest:
        return [], []
    manager_rows = report_tools._q(
        "SELECT DISTINCT manager_code FROM fact_tonghopkhachhang "
        "WHERE save_date=? AND manager_code IS NOT NULL AND TRIM(manager_code)<>''",
        (latest,),
    )
    codes = [str(row.get("manager_code") or "").strip() for row in manager_rows]
    codes = list(dict.fromkeys(code for code in codes if code))
    if not codes:
        return [], []
    placeholders = ",".join("?" for _ in codes)
    identity_rows = report_tools._q(
        "SELECT employee_code, area_code, position_code, is_duplicate FROM dim_nhanvien "
        f"WHERE employee_code IN ({placeholders})",
        tuple(codes),
    )
    identities = {
        str(row.get("employee_code") or "").strip(): row
        for row in identity_rows
        if row.get("employee_code")
    }
    recipients = []
    skipped = []
    known_misflagged = set(getattr(report_tools, "_KNOWN_MISFLAGGED_DUPLICATE_CODES", ()))
    for code in codes:
        identity = identities.get(code)
        if not identity:
            raise RuntimeError(f"Snapshot có manager_code '{code}' nhưng không có danh mục nhân sự tương ứng.")
        position = str(identity.get("position_code") or "").strip().upper()
        if position != "QLV":
            skipped.append((code, f"position_code={position or 'trống'}"))
            continue
        # MN1 (Kênh MT) và MN4 (Chợ sỉ) là các đơn vị/kênh rollup, không phải đội QLV cá nhân;
        # kpi_ranking() cũng đánh dấu chúng bằng IsDuplicate=1. Hai mã thật bị gắn nhầm cờ
        # (MBKV12/TM25030101) được report_templates khai báo ngoại lệ và vẫn phải giữ lại.
        if int(identity.get("is_duplicate") or 0) == 1 and code not in known_misflagged:
            skipped.append((code, "đơn vị/nhóm kênh (is_duplicate=1)"))
            continue
        recipients.append({
            "audience": f"QLV {code} (discovery)",
            "role": "qlv",
            "employee_code": code,
            "region": identity.get("area_code"),
            "channel": "OTC",
        })
    return recipients, skipped


def _group_totals(metrics_rows: list[dict], period_key: str) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], float] = collections.defaultdict(float)
    for metrics in metrics_rows:
        key = (metrics["area_code"], metrics["channel"])
        totals[key] += float(metrics[period_key]["total"]["revenue"] or 0.0)
    return dict(totals)


def _unit_revenue(report_tools, manager_code: str, area: str, date_from: str, date_to: str) -> float:
    """Doanh số nhóm/kênh rollup (MN1/MN4), chỉ dùng để cộng đủ tổng miền khi đối chiếu."""
    latest_rows = report_tools._q(
        "SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?",
        (date_to,),
    )
    latest = latest_rows[0].get("d") if latest_rows else None
    if not latest:
        return 0.0
    rows = report_tools._q(
        "WITH latest AS ("
        " SELECT employee_code, MAX(save_date) d FROM fact_tonghopkhachhang "
        " WHERE save_date<=? GROUP BY employee_code) "
        "SELECT e.employee_code, MAX(e.emp_dms_code) emp_dms_code, MAX(nv.dmsid) dmsid "
        "FROM fact_tonghopkhachhang e JOIN latest l "
        " ON l.employee_code=e.employee_code AND l.d=e.save_date "
        "LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code "
        "WHERE e.manager_code=? GROUP BY e.employee_code",
        (latest, manager_code),
    )
    keys = []
    for row in rows:
        for key in (row.get("employee_code"), row.get("emp_dms_code"), row.get("dmsid")):
            if key and str(key).strip():
                keys.append(str(key).strip())
    keys = list(dict.fromkeys(keys))
    if not keys:
        return 0.0
    placeholders = ",".join("?" for _ in keys)
    result = report_tools._q(
        "SELECT COALESCE(SUM(v.amount9),0) revenue "
        "FROM vhoadon_otc v "
        "LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
        "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
        f"WHERE v.employee_code IN ({placeholders}) AND tp.area_code=? "
        "AND v.doc_date BETWEEN ? AND ?",
        tuple(keys) + (area, date_from, date_to),
    )
    return float(result[0].get("revenue") or 0.0) if result else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Đối chiếu tổng QLV với doanh số miền, không gửi ra ngoài")
    parser.add_argument("--as-of", default=dt.date.today().isoformat(), help="Ngày báo cáo YYYY-MM-DD")
    parser.add_argument("--tolerance-vnd", type=float, default=1.0, help="Sai số tối đa cho phép")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Tự tìm QLV từ snapshot warehouse, dùng trước khi config có mapping người nhận",
    )
    args = parser.parse_args()

    from src.qlv_digest import _load_report_tools  # noqa: PLC0415
    tools = _load_report_tools()
    configured_recipients = _load_report_recipients()
    skipped: list[tuple[str, str]] = []
    if args.discover:
        try:
            configured_recipients, skipped = _discover_qlv_recipients(tools, args.as_of)
            for code, reason in skipped:
                print(f"INFO: bỏ qua {code} khỏi tổng QLV — {reason}.")
        except Exception as exc:
            print(f"FAIL: không tự phát hiện được QLV: {exc}")
            return 2
    misclassified = [
        recipient.get("audience") or "(không tên)"
        for recipient in configured_recipients
        if str(recipient.get("employee_code") or "").strip()
        and str(recipient.get("role") or "").strip().lower() != "qlv"
    ]
    if misclassified:
        print("FAIL: người nhận có employee_code nhưng thiếu role=qlv: " + ", ".join(misclassified))
        return 2
    recipients = [
        recipient for recipient in configured_recipients
        if str(recipient.get("role") or "").strip().lower() == "qlv"
    ]
    if not recipients:
        print("FAIL: config chưa có report_recipients nào mang role=qlv.")
        return 2

    codes = [str(recipient.get("employee_code") or "").strip() for recipient in recipients]
    missing = [recipient.get("audience") or "(không tên)" for recipient, code in zip(recipients, codes) if not code]
    duplicates = sorted(code for code, count in collections.Counter(codes).items() if code and count > 1)
    if missing or duplicates:
        if missing:
            print("FAIL: QLV thiếu employee_code: " + ", ".join(missing))
        if duplicates:
            print("FAIL: employee_code bị cấu hình lặp: " + ", ".join(duplicates))
        return 2

    metrics_rows = []
    build_failures = []
    for recipient in recipients:
        try:
            metrics_rows.append(build_qlv_digest_metrics(
                employee_code=recipient["employee_code"],
                region=recipient.get("region"),
                channel=recipient.get("channel"),
                as_of_date=args.as_of,
                report_tools=tools,
            ))
        except Exception as exc:
            build_failures.append((recipient.get("employee_code"), str(exc)))
    if build_failures:
        for code, error in build_failures:
            print(f"FAIL: {code}: {error}")
        return 1

    daily_by_scope = _group_totals(metrics_rows, "daily_revenue")
    month_by_scope = _group_totals(metrics_rows, "month_to_date_revenue")
    day = dt.date.fromisoformat(args.as_of)
    date_to = f"{day.isoformat()} 23:59:59"
    unit_daily_by_scope: dict[tuple[str, str], float] = collections.defaultdict(float)
    unit_month_by_scope: dict[tuple[str, str], float] = collections.defaultdict(float)
    for code, reason in skipped:
        if "is_duplicate=1" not in reason:
            continue
        identity = tools._q(
            "SELECT area_code FROM dim_nhanvien WHERE employee_code=? LIMIT 1", (code,)
        )
        area = str(identity[0].get("area_code") or "").strip().upper() if identity else ""
        if not area:
            print(f"FAIL: không xác định được miền của nhóm/kênh {code}.")
            return 1
        unit_daily_by_scope[(area, "OTC")] += _unit_revenue(
            tools, code, area, day.isoformat(), date_to
        )
        unit_month_by_scope[(area, "OTC")] += _unit_revenue(
            tools, code, area, day.replace(day=1).isoformat(), date_to
        )
    failures = []
    print(f"Đang đối chiếu {len(metrics_rows)} QLV tại ngày {day.isoformat()}:")
    for area, channel in sorted(daily_by_scope):
        region_daily = tools.revenue_by_channel(
            day.isoformat(), date_to,
            scope_area_code=area, scope_channel=channel,
        )["total"]["revenue"]
        region_month = tools.revenue_by_channel(
            day.replace(day=1).isoformat(), date_to,
            scope_area_code=area, scope_channel=channel,
        )["total"]["revenue"]
        qlv_daily = daily_by_scope[(area, channel)]
        qlv_month = month_by_scope[(area, channel)]
        unit_daily = unit_daily_by_scope.get((area, channel), 0.0)
        unit_month = unit_month_by_scope.get((area, channel), 0.0)
        daily_diff = qlv_daily + unit_daily - float(region_daily or 0.0)
        month_diff = qlv_month + unit_month - float(region_month or 0.0)
        status = "PASS" if max(abs(daily_diff), abs(month_diff)) <= args.tolerance_vnd else "FAIL"
        print(
            f"  {status} {area}/{channel}: QLV ngày {qlv_daily:,.0f} đ + nhóm/kênh {unit_daily:,.0f} đ "
            f"→ lệch {daily_diff:,.0f} đ; lũy kế lệch {month_diff:,.0f} đ"
        )
        if status == "FAIL":
            failures.append((area, channel, daily_diff, month_diff))

    if failures:
        print("FAIL: tổng các đội chưa khớp số miền; kiểm tra QLV thiếu, mã lặp hoặc ManagerCode Bravo.")
        return 1
    print("PASS: tổng các QLV khớp số miền cho cả ngày và lũy kế tháng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
