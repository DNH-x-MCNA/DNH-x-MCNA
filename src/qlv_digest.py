# -*- coding: utf-8 -*-
"""Báo cáo Daily Digest riêng cho từng đội Quản lý vùng (QLV).

Module này cố ý đọc ``warehouse.db`` qua các hàm báo cáo chuẩn trong
``backend/report_templates.py``. Nó không dùng ``src.etl.get_digest_metrics`` vì luồng ETL đó
không có khóa phạm vi theo đội và có cả dữ liệu tồn kho — tồn kho không được gán cho từng QLV.

Nguyên tắc an toàn quan trọng nhất: thiếu ``employee_code`` hoặc không xác định được đội thì phải
dừng, tuyệt đối không lùi về báo cáo toàn miền/toàn công ty.
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
from pathlib import Path
from typing import Any, Callable


class QLVDigestScopeError(ValueError):
    """Cấu hình không đủ để giới hạn báo cáo vào đúng một đội QLV."""


_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"

_AREA_ALIASES = {
    "BAC": "MB",
    "MIEN BAC": "MB",
    "MIỀN BẮC": "MB",
    "MB": "MB",
    "MB2": "MB2",
    "NAM": "MN",
    "MIEN NAM": "MN",
    "MIỀN NAM": "MN",
    "MN": "MN",
    "TRUNG": "MT",
    "MIEN TRUNG": "MT",
    "MIỀN TRUNG": "MT",
    "MT": "MT",
}


def _load_report_tools():
    """Nạp đúng lớp báo cáo thuộc repo hiện tại; lệch thư mục thì dừng thay vì đọc nhầm kho."""
    backend_text = str(_BACKEND)
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    module = importlib.import_module("report_templates")
    loaded_from = Path(module.__file__).resolve()
    expected = (_BACKEND / "report_templates.py").resolve()
    if loaded_from != expected:
        raise RuntimeError(
            f"Đang nạp report_templates từ '{loaded_from}', không phải repo hiện tại '{expected}'."
        )
    return module


def _normalise_area(region: str | None) -> str:
    raw = str(region or "").strip().upper()
    area = _AREA_ALIASES.get(raw)
    if not area:
        raise QLVDigestScopeError(
            "Báo cáo QLV thiếu miền hợp lệ (MB/MN/MT hoặc bac/nam/trung); đã dừng để không mở rộng phạm vi."
        )
    return area


def _normalise_channel(channel: str | None) -> str:
    # Các QLV hiện tại thuộc hệ thống OTC-only. Giữ mặc định OTC cho cấu hình cũ; nếu sau này có
    # QLV ETC thì phải khai báo rõ channel=ETC trên chính người nhận đó.
    value = str(channel or "OTC").strip().upper()
    if value not in {"OTC", "ETC"}:
        raise QLVDigestScopeError("Kênh của báo cáo QLV chỉ được là OTC hoặc ETC.")
    return value


def _report_day(value: str | None, report_tools) -> dt.date:
    raw = str(value or dt.date.today().isoformat())[:10]
    try:
        day = dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("as_of_date phải có định dạng YYYY-MM-DD.") from exc
    if day > dt.date.today():
        raise ValueError("Không được dựng báo cáo QLV cho ngày trong tương lai.")
    return day


def _team_kpi_summary(kpi: dict, employee_code: str) -> dict:
    rows = list(kpi.get("rows") or [])
    manager = next(
        (row for row in rows if str(row.get("employee_code") or "").strip() == employee_code),
        None,
    )
    members = [
        row for row in rows
        if str(row.get("employee_code") or "").strip() != employee_code
    ]
    lowest = sorted(members, key=lambda row: float(row.get("pct") or 0.0))[:3]
    return {
        "as_of": kpi.get("as_of"),
        "manager": manager,
        "member_count": len(members),
        "kpi_achieved_count": sum(bool(row.get("meets_kpi")) for row in members),
        "full_target_count": sum(bool(row.get("meets_full_target")) for row in members),
        "lowest_completion": lowest,
        "note": kpi.get("note"),
    }


def build_qlv_digest_metrics(
    *,
    employee_code: str,
    region: str,
    channel: str | None = None,
    as_of_date: str | None = None,
    report_tools=None,
) -> dict:
    """Dựng dữ liệu báo cáo cho đúng một đội QLV, không gọi LLM và không gửi ra ngoài."""
    code = str(employee_code or "").strip()
    if not code:
        raise QLVDigestScopeError(
            "Báo cáo QLV thiếu employee_code; đã dừng để không rơi về dữ liệu toàn miền."
        )

    area = _normalise_area(region)
    scoped_channel = _normalise_channel(channel)
    tools = report_tools or _load_report_tools()
    day = _report_day(as_of_date, tools)
    date_from = day.isoformat()
    date_to = f"{day.isoformat()} 23:59:59"
    month_from = day.replace(day=1).isoformat()

    # revenue_by_channel gọi _get_team_dms_ids() ở tầng SQL. Nếu mã QLV không có đội hợp lệ, hàm
    # ném lỗi và toàn bộ digest dừng — đây chính là hàng rào fail-closed của báo cáo.
    daily_revenue = tools.revenue_by_channel(
        date_from,
        date_to,
        scope_area_code=area,
        scope_channel=scoped_channel,
        scope_employee_code=code,
    )
    month_revenue = tools.revenue_by_channel(
        month_from,
        date_to,
        scope_area_code=area,
        scope_channel=scoped_channel,
        scope_employee_code=code,
    )

    if scoped_channel == "OTC":
        raw_kpi = tools.employee_kpi(
            day.isoformat(),
            limit=200,
            order_by="pct",
            filter="all",
            scope_area_code=area,
            scope_employee_code=code,
        )
        team_kpi = _team_kpi_summary(raw_kpi, code)
        lifecycle = tools.customer_lifecycle_summary(
            year_month=day.strftime("%Y-%m"),
            months_back=1,
            scope_area_code=area,
            scope_employee_code=code,
            scope_channel="OTC",
        )
    else:
        # Nguồn KPI/vòng đời hiện chỉ có cho OTC. Không lấy số OTC gắn nhãn ETC.
        team_kpi = {
            "not_applicable": True,
            "note": "Nguồn KPI đội và vòng đời khách hiện chỉ phủ kênh OTC.",
            "member_count": 0,
            "kpi_achieved_count": 0,
            "full_target_count": 0,
            "lowest_completion": [],
        }
        lifecycle = {
            "not_applicable": True,
            "error": "Nguồn vòng đời khách hiện chỉ phủ kênh OTC.",
        }

    debt_risk = tools.customer_revenue_debt_risk(
        as_of_date=day.isoformat(),
        scope_area_code=area,
        scope_employee_code=code,
        scope_channel=scoped_channel,
    )

    freshness = ""
    if hasattr(tools, "data_freshness_note"):
        freshness = tools.data_freshness_note()

    return {
        "report_type": "qlv_team_daily",
        "date": day.isoformat(),
        "month": day.strftime("%Y-%m"),
        "employee_code": code,
        "area_code": area,
        "channel": scoped_channel,
        "daily_revenue": daily_revenue,
        "month_to_date_revenue": month_revenue,
        "team_kpi": team_kpi,
        "customer_lifecycle": lifecycle,
        "debt_risk": debt_risk,
        "freshness_note": freshness,
        # Khóa hồi quy: báo cáo QLV tuyệt đối không được ghép tồn kho vì kho không thuộc một đội.
        "inventory_included": False,
    }


def build_qlv_teams_content(
    metrics: dict,
    money_formatter: Callable[[float], str],
) -> tuple[list[str], list[list[str]], list[dict[str, Any]]]:
    """Chuyển dữ liệu QLV thành bảng/section dùng chung với Adaptive Card hiện tại."""
    daily = metrics["daily_revenue"]["total"]
    month = metrics["month_to_date_revenue"]["total"]
    rows = [
        ["Doanh số đội trong ngày", money_formatter(daily["revenue"])],
        ["Số hóa đơn trong ngày", str(daily["invoices"])],
        ["Doanh số đội lũy kế tháng", money_formatter(month["revenue"])],
        ["Số hóa đơn lũy kế tháng", str(month["invoices"])],
    ]

    kpi = metrics.get("team_kpi") or {}
    manager = kpi.get("manager")
    if manager:
        rows.append([
            "Mức hoàn thành KPI của QLV",
            f"{float(manager.get('pct') or 0.0):.1f}%",
        ])

    sections: list[dict[str, Any]] = []
    if not kpi.get("not_applicable"):
        kpi_items = [
            f"• Số TDV trong đội: {kpi.get('member_count', 0)}",
            f"• TDV đạt KPI từ 80%: {kpi.get('kpi_achieved_count', 0)}",
            f"• TDV hoàn thành đủ 100% chỉ tiêu: {kpi.get('full_target_count', 0)}",
        ]
        lowest = kpi.get("lowest_completion") or []
        if lowest:
            kpi_items.append("• Ba TDV có tỷ lệ hoàn thành thấp nhất:")
            for item in lowest:
                name = item.get("name") or item.get("employee_code") or "Chưa rõ"
                kpi_items.append(f"   - {name}: {float(item.get('pct') or 0.0):.1f}%")
        elif kpi.get("note"):
            kpi_items.append(f"• {kpi['note']}")
        sections.append({
            "id": "section_qlv_team_kpi",
            "title": "📈 TIẾN ĐỘ ĐỘI",
            "is_collapsed": False,
            "items": kpi_items,
        })

    lifecycle = metrics.get("customer_lifecycle") or {}
    if not lifecycle.get("not_applicable"):
        month_rows = [m for m in (lifecycle.get("months") or []) if not m.get("khong_co_du_lieu")]
        if month_rows:
            current = month_rows[-1]
            sections.append({
                "id": "section_qlv_customers",
                "title": "👥 KHÁCH HÀNG CỦA ĐỘI",
                "is_collapsed": False,
                "items": [
                    f"• Tổng khách có trong snapshot: {current.get('tong_khach', 0)}",
                    f"• Khách mới trong tháng: {current.get('khach_moi', 0)}",
                    f"• Doanh số từ khách mới: {money_formatter(current.get('doanh_so_khach_moi', 0))}",
                ],
            })

    debt = metrics.get("debt_risk") or {}
    debt_items = []
    customers = debt.get("customers") or []
    if customers:
        debt_items.append(
            f"• {len(customers)} khách đồng thời có doanh thu lớn, nợ quá hạn và doanh thu giảm:"
        )
        for customer in customers[:5]:
            name = customer.get("customer_name") or customer.get("customer_code") or "Chưa rõ"
            debt_items.append(
                f"   - {name}: quá hạn {money_formatter(customer.get('overdue', 0))}; "
                f"doanh thu {float(customer.get('change_pct') or 0.0):+.1f}%"
            )
    else:
        debt_items.append("• Chưa ghi nhận khách vượt đồng thời các ngưỡng rủi ro của báo cáo.")
    sections.append({
        "id": "section_qlv_debt_risk",
        "title": "💳 KHÁCH HÀNG CẦN ƯU TIÊN CÔNG NỢ",
        "is_collapsed": False,
        "items": debt_items,
    })

    return ["Chỉ số", "Giá trị"], rows, sections
