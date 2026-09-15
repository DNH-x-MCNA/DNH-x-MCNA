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
    mark_errors(view)
    view["action_count"] = action_count(view)
    return view


# Lỗi trong bundle -> mục "Việc cần xử lý" không đánh giá được. Nhịp OTC hỏng thì không dự phóng được
# đội; công nợ Bravo hỏng thì mất cả hai mục nợ >45 ngày.
_MUC_THEO_LOI = {
    "team_pace": ("team_pace",), "channel_pace": ("team_pace",),
    "silent_customers": ("silent_customers",),
    "receivables": ("new_over45", "overdue_ordering"),
    "new_over45": ("new_over45",), "overdue_ordering": ("overdue_ordering",),
}


def mark_errors(view):
    """Gắn ``error=True`` cho mục không đánh giá được (idempotent) — 15/09/2026.

    Bản cũ để mặc định ``evaluated=False`` khi phần đó lỗi, nên ngày 22 vẫn in "đánh giá từ ngày 15";
    mục nợ lỗi thì in "Không có khách nào" như thể đã kiểm mà sạch.
    """
    if not view:
        return view
    for loi in view.get("errors") or {}:
        for muc in _MUC_THEO_LOI.get(loi, ()):
            view[muc] = {**(view.get(muc) or {}), "error": True}
    team = view.get("team_pace") or {}
    if team.get("evaluated") and team.get("skipped_reason"):
        view["team_pace"] = {**team, "error": True}
    return view


def all_evaluated(view):
    """True khi mọi mục áp dụng cho người nhận đã đánh giá xong: không lỗi, đã tới ngày, có bản chụp."""
    if not view:
        return False
    team = view.get("team_pace") or {}
    if team.get("applicable", True) and (team.get("error") or not team.get("evaluated")):
        return False
    silent = view.get("silent_customers") or {}
    if silent.get("error") or not silent.get("evaluated"):
        return False
    new_debt = view.get("new_over45") or {}
    if new_debt.get("error") or not new_debt.get("available"):
        return False
    return not (view.get("overdue_ordering") or {}).get("error")


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
    view = mark_errors(dict(view))
    lines = []
    team = view.get("team_pace") or {}
    if team.get("applicable", True):
        if team.get("error"):
            lines.append("• Đội QLV nguy cơ hụt chỉ tiêu: CHƯA đánh giá được (lỗi dữ liệu lúc dựng báo cáo).")
        elif not team.get("evaluated"):
            lines.append(f"• Đội QLV: đánh giá nguy cơ hụt chỉ tiêu từ ngày {team.get('min_day', 15)} hằng tháng.")
        elif team.get("at_risk"):
            lines.append(f"• {len(team['at_risk'])} đội QLV dự phóng cuối tháng dưới "
                         f"{team.get('threshold_pct', 60):.0f}% chỉ tiêu:")
            _them_danh_sach(lines, team["at_risk"], max_rows,
                            lambda t: f"{t['team_name']}: đạt {t['achievement_pct']:.0f}%, dự phóng "
                                      f"{t['projection_pct']:.0f}%", don_vi="đội")
        if team.get("evaluated") and not team.get("error") and team.get("not_projected"):
            ds = team["not_projected"]
            ten = "; ".join(f"{t['team_name']} ({money(t['target'])})" for t in ds[:max_rows])
            them = f"; và {len(ds) - max_rows} nhóm khác" if len(ds) > max_rows else ""
            lines.append(f"   ({len(ds)} đội/nhóm dưới 3 TDV không dự phóng: {ten}{them})")

    silent = view.get("silent_customers") or {}
    if silent.get("error"):
        lines.append("• Khách mua đều chưa có đơn: CHƯA đánh giá được (lỗi dữ liệu lúc dựng báo cáo).")
    elif not silent.get("evaluated"):
        lines.append(f"• Khách mua đều chưa có đơn: đánh giá từ ngày {silent.get('min_day', 20)} hằng tháng.")
    elif silent.get("rows"):
        lines.append(f"• {len(silent['rows'])} khách mua đều chưa có đơn tháng này:")
        _them_danh_sach(lines, silent["rows"], max_rows,
                        lambda c: f"{c.get('customer_name') or c['customer_code']} ({c['customer_code']}, "
                                  f"{c.get('sales_channel')}): thường mua {money(c['baseline_monthly'])}/tháng")

    new_debt = view.get("new_over45") or {}
    if new_debt.get("error"):
        lines.append("• Khách mới nợ quá hạn >45 ngày: CHƯA đánh giá được (lỗi dữ liệu công nợ).")
    elif not new_debt.get("available"):
        lines.append("• Khách mới nợ quá hạn >45 ngày: chưa có bản chụp công nợ đủ để so sánh.")
    elif new_debt.get("rows"):
        lines.append(f"• {len(new_debt['rows'])} khách mới có nợ quá hạn trên 45 ngày:")
        _them_danh_sach(lines, new_debt["rows"], max_rows,
                        lambda c: f"{c.get('customer_name') or c['customer_code']} ({c['customer_code']}): "
                                  f"{money(c['overdue_gt_45'])}")

    ordering = view.get("overdue_ordering") or {}
    if ordering.get("error"):
        lines.append("• Khách nợ >45 ngày vẫn lên đơn: CHƯA đánh giá được (lỗi dữ liệu công nợ/đơn hàng).")
    elif ordering.get("rows"):
        lines.append(f"• {len(ordering['rows'])} khách nợ trên 45 ngày vẫn lên đơn tháng này:")
        _them_danh_sach(lines, ordering["rows"], max_rows,
                        lambda c: f"{c.get('customer_name') or c['customer_code']} ({c['customer_code']}): "
                                  f"nợ >45 ngày {money(c['overdue_gt_45'])}, {c['new_orders']} đơn "
                                  f"{money(c['new_order_value'])}")

    # Chỉ khẳng định "không có việc" khi mọi mục đều đã kiểm thật; mục chưa kiểm đã có dòng riêng ở trên.
    if not action_count(view) and all_evaluated(view):
        lines.append("• Không có việc nào vượt ngưỡng cảnh báo.")
    if view.get("errors"):
        lines.append("• Một phần dữ liệu chưa lấy được lúc dựng báo cáo: " + ", ".join(view["errors"]) + ".")
    return lines
