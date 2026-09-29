"""Current-period extrapolation from existing scoped local reports. No model or live SQL."""
import calendar
import datetime as dt
import math
from statistics import median

from feature_policy import feature_enabled, disabled_future_result


def _end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def current_period_projection(period="month", group_by="overall", scope_area_code=None,
                              scope_channel=None, scope_employee_code=None):
    if not feature_enabled("DNH_BAT_DU_PHONG"):
        return disabled_future_result()
    if period not in {"month", "quarter"} or group_by not in {"overall", "channel", "area", "qlv", "employee"}:
        return {"error": "Chỉ hỗ trợ tháng/quý hiện tại và nhóm tổng/kênh/miền/QLV/TDV."}
    import report_templates as rt

    today = dt.date.today()
    as_of = min(today - dt.timedelta(days=1), dt.date.fromisoformat(rt.latest_data_date()[:10]))
    if as_of.replace(day=1) != today.replace(day=1):
        return {"error": "Kho chưa có dữ liệu tháng hiện tại; chưa đủ cơ sở dự phóng.", "as_of": str(as_of)}
    start = as_of.replace(day=1)
    end = _end(as_of)
    kpi = bool(scope_employee_code or group_by in {"qlv", "employee"})
    if kpi and period == "quarter":
        return {"error": "Chưa có bộ chỉ tiêu/snapshot đủ kỳ để dự phóng quý theo đội/TDV. Hãy chọn tháng hiện tại."}
    scope = dict(scope_area_code=scope_area_code, scope_channel=scope_channel,
                 scope_employee_code=scope_employee_code)

    def kpi_rows(day):
        value = rt.kpi_gap_run_rate(str(day), group_by if group_by in {"qlv", "employee"} else "total", 200, **scope)
        if value.get("error"):
            raise ValueError(value["error"])
        observed = dt.date.fromisoformat(value["as_of"][:10])
        if observed.year != day.year or observed.month != day.month or observed > day:
            raise ValueError("Không có snapshot KPI đúng tháng/ngày yêu cầu.")
        return value["rows"], observed

    histories = []
    skipped = []
    if kpi:
        try:
            current, as_of = kpi_rows(as_of)
        except (ValueError, rt.KhongXacDinhDuocDoi) as exc:
            return {"error": str(exc)}
        current = [{"key": r["group_code"], "label": r["group_name"], "actual": r["actual"],
                    "target": r["target"], "linear": r["linear_run_rate"]} for r in current]
    else:
        slices = [("ALL", "Tổng phạm vi", scope)]
        if group_by == "area":
            slices = [(a, a, {**scope, "scope_area_code": a}) for a in
                      ([scope_area_code] if scope_area_code else ["MB", "MT", "MN"])]
        elif group_by == "channel":
            slices = [(c, c, {**scope, "scope_channel": c}) for c in
                      ([scope_channel] if scope_channel and scope_channel != "ALL" else ["OTC", "ETC"])]

        def revenue(first, last, filters):
            value = rt.revenue_by_channel(str(first), str(last) + " 23:59:59", **filters)
            if value.get("data_coverage", {}).get("complete") is False:
                raise ValueError(value.get("coverage_warning") or "Thiếu dữ liệu doanh thu trong kỳ.")
            return float(value["total"]["revenue"])

        current = []
        try:
            for key, label, filters in slices:
                actual = revenue(start, as_of, filters)
                plan = rt._ytd_plan(start.year, f"{start.month:02}", f"{start.month:02}", **filters)
                current.append(dict(key=key, label=label, actual=actual, target=plan["total"],
                                    target_note=plan.get("note"), linear=actual / as_of.day * end.day))
        except ValueError as exc:
            return {"error": str(exc)}

    # Six previous months, matched calendar day. Incomplete/negative/non-finite bases are excluded.
    for offset in range(1, 7):
        ym = rt._month_add(as_of.strftime("%Y-%m"), -offset)
        first = dt.date.fromisoformat(ym + "-01")
        last = _end(first)
        comparable = first.replace(day=min(as_of.day, last.day))
        try:
            if kpi:
                partial, partial_day = kpi_rows(comparable)
                full, full_day = kpi_rows(last)
                if partial_day != comparable or full_day != last:
                    raise ValueError("Snapshot không đúng ngày so sánh/cuối tháng")
                partial = {r["group_code"]: r["actual"] for r in partial}
                full = {r["group_code"]: r["actual"] for r in full}
            else:
                # Compressed monthly totals cannot stand in for same-day MTD.
                if str(first) < rt._detail_cutoff():
                    raise ValueError("Lịch sử chỉ còn tổng tháng")
                partial = {key: revenue(first, comparable, filters) for key, _, filters in slices}
                full = {key: revenue(first, last, filters) for key, _, filters in slices}
            histories.append((ym, partial, full))
        except (ValueError, rt.KhongXacDinhDuocDoi) as exc:
            skipped.append({"month": ym, "reason": str(exc)})

    quarter_start = start.replace(month=((start.month - 1) // 3) * 3 + 1)
    quarter_end = _end(start.replace(month=quarter_start.month + 2))
    for row in current:
        actual = float(row["actual"])
        ratios = []
        samples = []
        for ym, partial, full in histories:
            a, b = partial.get(row["key"]), full.get(row["key"])
            if a is not None and b is not None and a > 0 and b >= 0 and math.isfinite(a) and math.isfinite(b):
                ratios.append(b / a)
                samples.append(ym)
        scenarios = None
        if len(ratios) >= 3 and actual >= 0:
            scenarios = {"low": actual * min(ratios), "base": actual * median(ratios), "high": actual * max(ratios)}
        if as_of == end:
            scenarios = dict(low=actual, base=actual, high=actual)
        if period == "quarter":
            filters = next(filters for key, _, filters in slices if key == row["key"])
            try:
                closed_actual = revenue(quarter_start, start - dt.timedelta(days=1), filters) if quarter_start < start else 0.0
            except ValueError as exc:
                return {"error": str(exc)}
            # Completed months are actual; remaining quarter follows this month's daily pace.
            scale = 1 + (quarter_end - end).days / end.day
            row["linear"] = closed_actual + row["linear"] * scale
            if scenarios:
                scenarios = {key: closed_actual + value * scale for key, value in scenarios.items()}
            row["actual"] = closed_actual + actual
            plan = rt._ytd_plan(start.year, f"{quarter_start.month:02}", f"{quarter_end.month:02}", **filters)
            row["target"], row["target_note"] = plan["total"], plan.get("note")
        remaining = ((quarter_end if period == "quarter" else end) - as_of).days
        gap = max(0, row["target"] - row["actual"]) if row["target"] is not None else None
        row.update(scenarios=scenarios, history_months=samples, history_count=len(samples),
                   gap=gap, needed_per_day=(gap / remaining if remaining else (0 if gap == 0 else None)) if gap is not None else None,
                   projected_gap=(row["target"] - row["linear"]) if row["target"] is not None else None)
    return {"period": period, "as_of": str(as_of), "period_from": str(quarter_start if period == "quarter" else start),
            "period_to": str(quarter_end if period == "quarter" else end), "rows": current,
            "basis": "KPI đội/nhân viên" if kpi else "Doanh thu hóa đơn",
            "scope": scope, "skipped_history": skipped,
            "method": "Tháng: lũy kế / ngày lịch đã qua × số ngày tháng. Quý: thực tế các tháng đã đóng + nhịp ngày tháng hiện tại cho phần còn lại.",
            "scenario_note": "Xấu/cơ sở/tốt dùng min/trung vị/max tỷ lệ cuối tháng trên lũy kế cùng ngày của tối đa 6 tháng trước; cần ít nhất 3 tháng hợp lệ. Không phải khoảng tin cậy hay xác suất đạt. Tháng âm/thiếu lịch sử không có kịch bản.",
            "assumptions": "Giả định nhịp bán và cơ cấu giữ nguyên; chưa mô hình hóa mùa vụ, ngày nghỉ hay chương trình mới."}


def render_projection(data):
    if data.get("error"):
        return data["error"]
    def money(value):
        return "Chưa đủ dữ liệu" if value is None else f"{value:,.0f}".replace(",", ".")
    scope_note = " · ".join(str(v) for v in data["scope"].values() if v) or "Toàn công ty"
    lines = [f"**Dự phóng {'quý' if data['period'] == 'quarter' else 'tháng'} đang chạy** — dữ liệu đến {data['as_of']}",
             f"Nguồn: {data['basis']}. Phạm vi: {scope_note}. Đơn vị: đồng.",
             "| Phạm vi | Thực tế | Chỉ tiêu | Tuyến tính | Xấu | Cơ sở | Tốt | Cần/ngày |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in data["rows"]:
        s = r["scenarios"] or {}
        label = str(r["label"]).replace("|", " ").replace("\n", " ")
        values = [r["actual"], r["target"], r["linear"], s.get("low"), s.get("base"), s.get("high"), r["needed_per_day"]]
        lines.append("| " + " | ".join([label] + [money(x) for x in values]) + " |")
    notes = list(dict.fromkeys(r["target_note"] for r in data["rows"] if r.get("target_note")))
    return "\n".join(lines) + "\n\n" + "\n\n".join([data["method"], data["scenario_note"], data["assumptions"], "Lịch sử hợp lệ: " + "; ".join(f"{r['label']}: {r['history_count']}/6 tháng" for r in data["rows"]), *notes])
