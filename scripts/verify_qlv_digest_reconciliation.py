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


def _discover_qlv_recipients(report_tools, as_of: str) -> list[dict]:
    """Tìm QLV từ snapshot KPI để kiểm tra trước khi có mapping người nhận Teams."""
    latest_rows = report_tools._q(
        "SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?",
        (as_of,),
    )
    latest = latest_rows[0].get("d") if latest_rows else None
    if not latest:
        return []
    manager_rows = report_tools._q(
        "SELECT DISTINCT manager_code FROM fact_tonghopkhachhang "
        "WHERE save_date=? AND manager_code IS NOT NULL AND TRIM(manager_code)<>''",
        (latest,),
    )
    codes = [str(row.get("manager_code") or "").strip() for row in manager_rows]
    codes = list(dict.fromkeys(code for code in codes if code))
    if not codes:
        return []
    placeholders = ",".join("?" for _ in codes)
    identity_rows = report_tools._q(
        "SELECT employee_code, area_code, position_code FROM dim_nhanvien "
        f"WHERE employee_code IN ({placeholders})",
        tuple(codes),
    )
    identities = {
        str(row.get("employee_code") or "").strip(): row
        for row in identity_rows
        if row.get("employee_code")
    }
    recipients = []
    for code in codes:
        identity = identities.get(code)
        if not identity or str(identity.get("position_code") or "").strip().upper() != "QLV":
            raise RuntimeError(
                f"Snapshot có manager_code '{code}' nhưng không có danh mục QLV tương ứng."
            )
        recipients.append({
            "audience": f"QLV {code} (discovery)",
            "role": "qlv",
            "employee_code": code,
            "region": identity.get("area_code"),
            "channel": "OTC",
        })
    return recipients


def _group_totals(metrics_rows: list[dict], period_key: str) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], float] = collections.defaultdict(float)
    for metrics in metrics_rows:
        key = (metrics["area_code"], metrics["channel"])
        totals[key] += float(metrics[period_key]["total"]["revenue"] or 0.0)
    return dict(totals)


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
    if args.discover:
        try:
            configured_recipients = _discover_qlv_recipients(tools, args.as_of)
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
        daily_diff = qlv_daily - float(region_daily or 0.0)
        month_diff = qlv_month - float(region_month or 0.0)
        status = "PASS" if max(abs(daily_diff), abs(month_diff)) <= args.tolerance_vnd else "FAIL"
        print(
            f"  {status} {area}/{channel}: ngày lệch {daily_diff:,.0f} đ; "
            f"lũy kế tháng lệch {month_diff:,.0f} đ"
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
