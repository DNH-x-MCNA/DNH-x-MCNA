# -*- coding: utf-8 -*-
"""Chẩn đoán chênh lệch đối chiếu QLV, chỉ đọc warehouse.db, không gọi API.

Script này không thay đổi dữ liệu và không gửi báo cáo. Nó liệt kê các mã nhân viên trên hóa đơn
chưa nằm trong tập DMSId mà digest QLV thực sự dùng, giúp phân biệt lỗi mapping với doanh thu nhóm/kênh.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_qlv_digest_reconciliation import _discover_qlv_recipients  # noqa: E402
from src.qlv_digest import _load_report_tools  # noqa: E402


def _normalise(value) -> str:
    return str(value or "").strip()


def _invoice_rows(tools, area: str, date_from: str, date_to: str) -> list[dict]:
    return tools._q(
        "SELECT COALESCE(v.employee_code,'') employee_code, COALESCE(v.channel_code,'') channel_code, "
        "SUM(v.amount9) revenue "
        "FROM vhoadon_otc v "
        "LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
        "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
        "WHERE tp.area_code=? AND v.doc_date BETWEEN ? AND ? "
        "GROUP BY v.employee_code, v.channel_code ORDER BY SUM(v.amount9) DESC",
        (area, date_from, date_to),
    )


def _identity(tools, code: str) -> dict:
    rows = tools._q(
        "SELECT employee_code,name,position_code,area_code,dmsid,is_duplicate "
        "FROM dim_nhanvien WHERE employee_code=? OR dmsid=? "
        "ORDER BY is_duplicate DESC LIMIT 1",
        (code, code),
    )
    return rows[0] if rows else {}


def _print_uncovered(tools, area: str, date_from: str, date_to: str,
                     covered_employees: set[str], covered_channels: set[str], label: str) -> None:
    rows = _invoice_rows(tools, area, date_from, date_to)
    uncovered = []
    for row in rows:
        employee = _normalise(row.get("employee_code"))
        channel = _normalise(row.get("channel_code"))
        if employee in covered_employees or channel in covered_channels:
            continue
        ident = _identity(tools, employee)
        uncovered.append({
            "employee": employee or "(trống)",
            "channel": channel or "(trống)",
            "revenue": float(row.get("revenue") or 0.0),
            "name": _normalise(ident.get("name")) or "(không có danh mục)",
            "position": _normalise(ident.get("position_code")) or "?",
            "dmsid": _normalise(ident.get("dmsid")) or "?",
        })
    total = sum(row["revenue"] for row in uncovered)
    print(f"  {area}/OTC {label}: chưa phủ {total:,.0f} đ qua {len(uncovered)} nhóm mã")
    for row in uncovered[:15]:
        print(
            f"    - employee={row['employee']} channel={row['channel']} "
            f"DMS={row['dmsid']} position={row['position']} name={row['name']}: "
            f"{row['revenue']:,.0f} đ"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Chẩn đoán gap doanh thu QLV, không gửi ra ngoài")
    parser.add_argument("--as-of", default=dt.date.today().isoformat())
    args = parser.parse_args()

    tools = _load_report_tools()
    recipients, skipped = _discover_qlv_recipients(tools, args.as_of)
    fdate = tools._fact_date_le(args.as_of)
    if not fdate:
        print("FAIL: warehouse không có snapshot FACT_TongHopKhachHang phù hợp.")
        return 2

    covered_by_area: dict[str, set[str]] = defaultdict(set)
    channel_by_area: dict[str, set[str]] = defaultdict(set)
    print(f"Snapshot KPI dùng để chốt đội: {fdate}")
    for recipient in recipients:
        code = _normalise(recipient.get("employee_code"))
        area = _normalise(recipient.get("region")).upper()
        try:
            dms_ids = {_normalise(value) for value in tools._get_team_dms_ids(code, fdate) if _normalise(value)}
        except Exception as exc:
            print(f"  WARN {code}/{area}: không lấy được tập DMSId: {exc}")
            continue
        covered_by_area[area].update(dms_ids)
        team = tools._team_of_qlv(code, fdate)
        team_codes = {_normalise(row.get("employee_code")) for row in team if _normalise(row.get("employee_code"))}
        missing_rows = tools._q(
            "SELECT employee_code,dmsid FROM dim_nhanvien "
            f"WHERE employee_code IN ({','.join('?' for _ in team_codes)}) "
            "AND (dmsid IS NULL OR TRIM(dmsid)='')",
            tuple(sorted(team_codes)),
        ) if team_codes else []
        print(
            f"  {area} {code}: TDV={len(team_codes)} DMSId={len(dms_ids)} "
            f"thiếu_DMSId={len(missing_rows)}"
        )
        for row in missing_rows:
            print(f"    MISSING DMSId: {row.get('employee_code')}")

    # Chỉ các mã bị phân loại là nhóm/kênh mới được loại khỏi danh sách QLV cá nhân; channel_code
    # của chúng vẫn phải được coi là đã phủ khi tìm các hóa đơn chưa gán.
    for code, reason in skipped:
        if "is_duplicate=1" not in reason:
            continue
        ident = _identity(tools, code)
        area = _normalise(ident.get("area_code")).upper()
        if area:
            channel_by_area[area].add(code)
            if _normalise(ident.get("dmsid")):
                channel_by_area[area].add(_normalise(ident.get("dmsid")))

    print("Các mã hóa đơn chưa nằm trong tập đội QLV:")
    day = dt.date.fromisoformat(args.as_of)
    date_to = f"{day.isoformat()} 23:59:59"
    for area in ("MB", "MN", "MT"):
        _print_uncovered(
            tools, area, day.isoformat(), date_to,
            covered_by_area[area], channel_by_area[area], "ngày"
        )
        _print_uncovered(
            tools, area, day.replace(day=1).isoformat(), date_to,
            covered_by_area[area], channel_by_area[area], "lũy kế tháng"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
