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
import html
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
_AREA_MARKERS = {
    "MB": {"MB", "MB2"},
    "MN": {"MN"},
    "MT": {"MT"},
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


def _report_day(value: str | None) -> dt.date:
    raw = str(value or dt.date.today().isoformat())[:10]
    try:
        day = dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("as_of_date phải có định dạng YYYY-MM-DD.") from exc
    if day > dt.date.today():
        raise ValueError("Không được dựng báo cáo QLV cho ngày trong tương lai.")
    return day


def _validate_qlv_identity(report_tools, employee_code: str, area: str) -> None:
    """Kiểm tra mã cấu hình thực sự là QLV đúng miền nếu lớp kho cung cấp truy vấn nội bộ."""
    query = getattr(report_tools, "_q", None)
    if query is None:
        return
    rows = query(
        "SELECT position_code, area_code FROM dim_nhanvien WHERE employee_code=? "
        "ORDER BY CASE WHEN is_resigned=0 THEN 0 ELSE 1 END LIMIT 1",
        (employee_code,),
    )
    if not rows:
        raise QLVDigestScopeError(
            f"Không tìm thấy employee_code '{employee_code}' trong danh mục nhân sự; đã dừng báo cáo."
        )
    position = str(rows[0].get("position_code") or "").strip().upper()
    if position != "QLV":
        raise QLVDigestScopeError(
            f"employee_code '{employee_code}' không phải mã QLV (position_code={position or 'trống'})."
        )
    own_area = str(rows[0].get("area_code") or "").strip().upper()
    if own_area not in _AREA_MARKERS[area]:
        raise QLVDigestScopeError(
            f"employee_code '{employee_code}' thuộc miền {own_area or 'trống'}, "
            f"không khớp miền cấu hình {area}; đã dừng để tránh báo cáo nhầm đội."
        )


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
    _validate_qlv_identity(tools, code, area)
    day = _report_day(as_of_date)
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


def _period_window(period_type: str, day: dt.date) -> dict[str, dt.date | str]:
    """Trả cửa sổ kỳ hiện tại và kỳ trước, đều kết thúc tại ngày ``day``.

    Weekly dùng thứ Hai tới ngày chốt; monthly dùng ngày đầu tháng tới ngày chốt. Kỳ trước có
    cùng số ngày đã trôi qua để tránh so sánh một phần tháng/tuần với cả kỳ hoàn chỉnh.
    """
    kind = str(period_type or "").strip().lower()
    if kind == "weekly":
        current_start = day - dt.timedelta(days=day.weekday())
        previous_start = current_start - dt.timedelta(days=7)
        elapsed_days = (day - current_start).days
        previous_end = previous_start + dt.timedelta(days=elapsed_days)
        label = f"Tuần {current_start:%d/%m/%Y} - {day:%d/%m/%Y}"
    elif kind == "monthly":
        current_start = day.replace(day=1)
        previous_last = current_start - dt.timedelta(days=1)
        previous_start = previous_last.replace(day=1)
        elapsed_days = (day - current_start).days
        previous_end = min(previous_last, previous_start + dt.timedelta(days=elapsed_days))
        label = f"Tháng {day:%m/%Y} ({current_start:%d/%m} - {day:%d/%m/%Y})"
    else:
        raise QLVDigestScopeError("period_type của báo cáo QLV chỉ được là weekly hoặc monthly.")

    return {
        "period_type": kind,
        "date_from": current_start,
        "date_to": day,
        "previous_date_from": previous_start,
        "previous_date_to": previous_end,
        "label": label,
    }


def build_qlv_period_metrics(
    *,
    employee_code: str,
    region: str,
    period_type: str,
    channel: str | None = None,
    as_of_date: str | None = None,
    report_tools=None,
) -> dict:
    """Dựng báo cáo tuần/tháng riêng một đội QLV, không dùng số liệu toàn miền.

    Kỳ hiện tại là từ thứ Hai/ngày đầu tháng tới ``as_of_date``. Kỳ trước có cùng số ngày đã
    trôi qua. Hàm chỉ đọc warehouse qua lớp report tools, không gọi LLM/API và không có tồn kho.
    """
    code = str(employee_code or "").strip()
    if not code:
        raise QLVDigestScopeError(
            "Báo cáo QLV thiếu employee_code; đã dừng để không rơi về dữ liệu toàn miền."
        )

    area = _normalise_area(region)
    scoped_channel = _normalise_channel(channel)
    tools = report_tools or _load_report_tools()
    _validate_qlv_identity(tools, code, area)
    day = _report_day(as_of_date)
    window = _period_window(period_type, day)

    def _range(start: dt.date, end: dt.date) -> tuple[str, str]:
        return start.isoformat(), f"{end.isoformat()} 23:59:59"

    current_from, current_to = _range(window["date_from"], window["date_to"])
    previous_from, previous_to = _range(window["previous_date_from"], window["previous_date_to"])
    scope = {
        "scope_area_code": area,
        "scope_channel": scoped_channel,
        "scope_employee_code": code,
    }
    period_revenue = tools.revenue_by_channel(current_from, current_to, **scope)
    previous_revenue = tools.revenue_by_channel(previous_from, previous_to, **scope)

    current_total = float((period_revenue.get("total") or {}).get("revenue") or 0.0)
    previous_total = float((previous_revenue.get("total") or {}).get("revenue") or 0.0)
    delta = current_total - previous_total
    comparison_pct = (delta / previous_total * 100.0) if previous_total else None

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
    freshness = tools.data_freshness_note() if hasattr(tools, "data_freshness_note") else ""

    return {
        "report_type": f"qlv_team_{window['period_type']}",
        "period_type": window["period_type"],
        "date": day.isoformat(),
        "month": day.strftime("%Y-%m"),
        "employee_code": code,
        "area_code": area,
        "channel": scoped_channel,
        "period": {
            "label": window["label"],
            "date_from": current_from,
            "date_to": current_to,
            "previous_date_from": previous_from,
            "previous_date_to": previous_to,
        },
        "period_revenue": period_revenue,
        "previous_period_revenue": previous_revenue,
        "comparison": {
            "revenue_delta": delta,
            "revenue_pct": comparison_pct,
        },
        "team_kpi": team_kpi,
        "customer_lifecycle": lifecycle,
        "debt_risk": debt_risk,
        "freshness_note": freshness,
        "inventory_included": False,
    }


def _build_qlv_sections(
    metrics: dict,
    money_formatter: Callable[[float], str],
) -> list[dict[str, Any]]:
    """Dựng các section dùng chung cho Daily/Weekly/Monthly QLV."""
    sections: list[dict[str, Any]] = []
    kpi = metrics.get("team_kpi") or {}
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
    customers = debt.get("customers") or []
    debt_items = []
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
    return sections


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
    return ["Chỉ số", "Giá trị"], rows, _build_qlv_sections(metrics, money_formatter)


def build_qlv_period_teams_content(
    metrics: dict,
    money_formatter: Callable[[float], str],
) -> tuple[list[str], list[list[str]], list[dict[str, Any]]]:
    """Chuyển báo cáo tuần/tháng QLV thành bảng/section Adaptive Card."""
    current = (metrics.get("period_revenue") or {}).get("total") or {}
    comparison = metrics.get("comparison") or {}
    pct = comparison.get("revenue_pct")
    if pct is None:
        comparison_text = "Chưa có doanh thu kỳ trước để tính tỷ lệ"
    else:
        delta = float(comparison.get("revenue_delta") or 0.0)
        comparison_text = f"{pct:+.1f}% ({money_formatter(delta)})"

    rows = [
        ["Doanh số đội trong kỳ", money_formatter(current.get("revenue", 0))],
        ["Số hóa đơn trong kỳ", str(current.get("invoices", 0))],
        ["So với kỳ trước", comparison_text],
    ]
    manager = (metrics.get("team_kpi") or {}).get("manager")
    if manager:
        rows.append([
            "Mức hoàn thành KPI của QLV",
            f"{float(manager.get('pct') or 0.0):.1f}%",
        ])

    return ["Chỉ số", "Giá trị"], rows, _build_qlv_sections(metrics, money_formatter)


def build_qlv_period_email(
    metrics: dict,
    money_formatter: Callable[[float], str],
) -> str:
    """Dựng email tuần/tháng cho đúng một đội QLV.

    Weekly/Monthly là báo cáo email; Teams chỉ dùng cho Daily Digest. Hàm này dùng cùng
    metrics/sections đã khóa phạm vi đội, nhưng không tạo payload hoặc gửi Teams.
    """
    headers, rows, sections = build_qlv_period_teams_content(metrics, money_formatter)
    period_type = str(metrics.get("period_type") or "weekly").lower()
    period_label = "TUẦN" if period_type == "weekly" else "THÁNG"
    code = html.escape(str(metrics.get("employee_code") or ""))
    area = str(metrics.get("area_code") or "").upper()
    area_label = {
        "MB": "Miền Bắc",
        "MB2": "Miền Bắc",
        "MN": "Miền Nam",
        "MT": "Miền Trung",
    }.get(area, area)
    period = metrics.get("period") or {}
    period_text = html.escape(str(period.get("label") or metrics.get("date") or ""))
    freshness = html.escape(str(metrics.get("freshness_note") or ""))

    row_html = "".join(
        f"<tr><th>{html.escape(str(label))}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in rows
    )
    section_html = []
    for section in sections:
        title = html.escape(str(section.get("title") or ""))
        items = section.get("items") or []
        items_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
        section_html.append(
            f'<h2 style="color:#1f4a22;font-size:16px;margin:22px 0 8px;">{title}</h2>'
            f'<ul style="margin:0;padding-left:22px;line-height:1.55;">{items_html}</ul>'
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;color:#334155;background:#f4f5f8;margin:0;padding:20px;">
  <div style="max-width:680px;margin:auto;background:#fff;border:1px solid #dbe5d6;border-top:5px solid #337337;border-radius:12px;padding:24px;">
    <div style="color:#1f4a22;font-size:21px;font-weight:700;">BÁO CÁO ĐỘI QLV {period_label}</div>
    <div style="margin-top:6px;color:#475569;">{period_text} · {html.escape(area_label)} · Đội {code}</div>
    {f'<div style="margin-top:6px;color:#64748b;font-size:13px;">{freshness}</div>' if freshness else ''}
    <table style="width:100%;border-collapse:collapse;margin-top:20px;">
      <thead><tr style="background:#1f4a22;color:#fff;"><th style="text-align:left;padding:9px;">Chỉ số</th><th style="text-align:left;padding:9px;">Giá trị</th></tr></thead>
      <tbody>{row_html}</tbody>
    </table>
    {''.join(section_html)}
    <div style="margin-top:24px;padding-top:12px;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:12px;">Báo cáo chỉ bao gồm dữ liệu của đội {code}; không bao gồm tồn kho.</div>
  </div>
</body></html>"""
