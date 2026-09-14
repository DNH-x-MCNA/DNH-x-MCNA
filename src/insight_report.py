# -*- coding: utf-8 -*-
"""Trình bày insight (src/insights.py) cho báo cáo định kỳ — 14/09/2026.

Báo cáo Daily (Teams) và Weekly/Monthly (email) trước đây có hai mục "Cảnh báo trong kỳ" và "Điểm nổi
bật trong kỳ" đọc lại log cảnh báo đã gửi. Log đó phần lớn là cảnh báo lặp (vd "Nợ quá hạn lớn top 5"
gửi 16 lần trong 11 ngày cùng một danh sách) nên người đọc không biết việc nào còn phải làm. Hai mục đó
được thay bằng "Tiến độ tháng" và "Việc cần xử lý", tính ngay lúc dựng báo cáo bằng CÙNG quy tắc đã
kiểm thử ngược của bộ cảnh báo, rồi lọc đúng phạm vi vùng/kênh của người nhận.
"""
from __future__ import annotations

ACTION_ROWS_TEAMS = 5


def attach_insights(region=None, channel=None):
    """View insight đã lọc phạm vi cho một người nhận; None nếu không dựng được.

    Insight hỏng không được làm hỏng cả báo cáo: doanh thu, công nợ, KPI vẫn gửi như cũ.
    """
    from src import insights
    try:
        bundle = insights.build_insight_bundle()
        view = insights.scope_insight_bundle(bundle, region=region, channel=channel)
    except Exception as exc:
        print(f"[DIGEST] Không dựng được insight ({exc}) — bỏ mục Tiến độ tháng/Việc cần xử lý.")
        return None
    rules = bundle.get("rules") or insights.DEFAULT_RULES
    try:
        view["month_pace"] = insights.channel_pace_for_scope(bundle["as_of"], region=region,
                                                             channel=channel, rules=rules)
    except Exception as exc:
        view["month_pace"] = {}
        view["errors"]["month_pace"] = str(exc)
    view["as_of_display"] = bundle["as_of"].strftime("%d/%m/%Y")
    view["lookback"] = int(rules["curve_lookback_months"])
    view["action_count"] = action_count(view)
    return view


def action_count(view):
    if not view:
        return 0
    return (len((view.get("team_pace") or {}).get("at_risk") or [])
            + len((view.get("silent_customers") or {}).get("rows") or [])
            + len((view.get("new_over45") or {}).get("rows") or [])
            + len((view.get("overdue_ordering") or {}).get("rows") or []))


def pace_lines(view, money):
    """Dòng [nhãn, giá trị] tiến độ tháng từng kênh cho bảng 2 cột của card Teams."""
    rows = []
    if not view:
        return rows
    for channel, pace in (view.get("month_pace") or {}).items():
        if not pace or pace.get("gap_pct") is None:
            continue
        gap = pace["gap_pct"]
        trang_thai = f"chậm {gap:.0f}%" if gap > 0 else f"nhanh {-gap:.0f}%"
        rows.append([
            f"Lũy kế tháng {channel} (đến {view.get('as_of_display')})",
            f"{money(pace['mtd'])} — {trang_thai} so nhịp thường lệ; dự phóng cả tháng "
            f"{money(pace['projected_full_month'])} ({pace['projected_vs_baseline_pct']:+.0f}% so TB "
            f"{view.get('lookback', 3)} tháng)",
        ])
    return rows


def _them_danh_sach(lines, rows, max_rows, fmt, don_vi="khách"):
    for row in rows[:max_rows]:
        lines.append("   - " + fmt(row))
    if len(rows) > max_rows:
        lines.append(f"   - Đang liệt kê {max_rows}/{len(rows)} {don_vi}.")


def action_lines(view, money, max_rows=ACTION_ROWS_TEAMS):
    """Dòng chữ mục "Việc cần xử lý" của card Teams. Mỗi nhóm tối đa max_rows dòng."""
    if not view:
        return []
    lines = []
    team = view.get("team_pace") or {}
    if team.get("applicable", True):
        if not team.get("evaluated"):
            lines.append(f"• Đội QLV: đánh giá nguy cơ hụt chỉ tiêu từ ngày {team.get('min_day', 15)} hằng tháng.")
        elif team.get("at_risk"):
            lines.append(f"• {len(team['at_risk'])} đội QLV dự phóng cuối tháng dưới "
                         f"{team.get('threshold_pct', 60):.0f}% chỉ tiêu:")
            _them_danh_sach(lines, team["at_risk"], max_rows,
                            lambda t: f"{t['team_name']}: đạt {t['achievement_pct']:.0f}%, dự phóng "
                                      f"{t['projection_pct']:.0f}%", don_vi="đội")

    silent = view.get("silent_customers") or {}
    if silent.get("evaluated") and silent.get("rows"):
        lines.append(f"• {len(silent['rows'])} khách mua đều chưa có đơn tháng này:")
        _them_danh_sach(lines, silent["rows"], max_rows,
                        lambda c: f"{c.get('customer_name') or c['customer_code']} ({c['customer_code']}, "
                                  f"{c.get('sales_channel')}): thường mua {money(c['baseline_monthly'])}/tháng")

    new_debt = view.get("new_over45") or {}
    if new_debt.get("rows"):
        lines.append(f"• {len(new_debt['rows'])} khách mới có nợ quá hạn trên 45 ngày:")
        _them_danh_sach(lines, new_debt["rows"], max_rows,
                        lambda c: f"{c.get('customer_name') or c['customer_code']} ({c['customer_code']}): "
                                  f"{money(c['overdue_gt_45'])}")

    ordering = view.get("overdue_ordering") or {}
    if ordering.get("rows"):
        lines.append(f"• {len(ordering['rows'])} khách nợ trên 45 ngày vẫn lên đơn tháng này:")
        _them_danh_sach(lines, ordering["rows"], max_rows,
                        lambda c: f"{c.get('customer_name') or c['customer_code']} ({c['customer_code']}): "
                                  f"nợ >45 ngày {money(c['overdue_gt_45'])}, {c['new_orders']} đơn "
                                  f"{money(c['new_order_value'])}")

    if not action_count(view):
        lines.append("• Không có việc nào vượt ngưỡng cảnh báo.")
    if view.get("errors"):
        lines.append("• Một phần dữ liệu chưa lấy được lúc dựng báo cáo: " + ", ".join(view["errors"]) + ".")
    return lines
