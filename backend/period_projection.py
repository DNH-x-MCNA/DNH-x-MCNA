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
            raise ValueError("Chưa có snapshot KPI của tháng hiện tại trong kho.")
        return value["rows"], observed

    def revenue(first, last, filters):
        value = rt.revenue_by_channel(str(first), str(last) + " 23:59:59", **filters)
        if value.get("data_coverage", {}).get("complete") is False:
            raise ValueError(value.get("coverage_warning") or "Thiếu dữ liệu doanh thu trong kỳ.")
        return float(value["total"]["revenue"])

    histories = []
    skipped = []
    notes = []
    if kpi:
        try:
            # 30/09/2026 (test that may 24: "Du phong KPI cuoi thang theo QLV" -> "Khong co snapshot KPI dung
            # thang/ngay yeu cau"): kho chi giu 1 snapshot KPI/thang, thang dang chay mang ngay dong bo gan nhat -
            # thuong la HOM NAY. Hoi snapshot "<= hom qua" luon roi ve snapshot cuoi thang TRUOC roi bao loi, tuc
            # V09/M43/KPI theo QLV chua bao gio chay duoc trong thang dang chay. Lay snapshot moi nhat cua thang
            # (<= hom nay); moc tinh kich ban/so ngay con lai la ngay SOM hon giua snapshot va du lieu doanh thu.
            current, snap = kpi_rows(today)
        except (ValueError, rt.KhongXacDinhDuocDoi) as exc:
            return {"error": str(exc)}
        as_of = min(as_of, snap)
        current = [{"key": r["group_code"], "label": r["group_name"], "actual": r["actual"],
                    "target": r["target"], "linear": r["linear_run_rate"]} for r in current]
        # Loi 2 (review 30/09): kho chi giu 1 snapshot KPI/thang (thang cu = ngay cuoi thang) nen khong bao gio co
        # "luy ke cung ngay" cua thang truoc -> V09 khong co kich ban. Lay nhip tu hoa don OTC CUNG PHAM VI.
        pace_scope = {**scope, "scope_channel": "OTC"}
        pace_label = (f"đội {scope_employee_code}" if scope_employee_code else
                      f"miền {scope_area_code}" if scope_area_code else "toàn công ty")
        notes.append(f"Kịch bản đội/TDV dùng nhịp hóa đơn OTC của {pace_label} trong các tháng trước, "
                     "áp cùng một tỷ lệ cho lũy kế KPI từng dòng; kho chỉ giữ snapshot KPI cuối tháng nên không có "
                     "lũy kế KPI cùng ngày của tháng cũ.")
        notes.append(f"Số KPI lấy từ snapshot ngày {snap:%d/%m/%Y} (kho chỉ giữ bản mới nhất của tháng); kịch bản "
                     f"và số cần mỗi ngày tính từ mốc {as_of:%d/%m/%Y}, cùng mốc với dự phóng doanh thu.")
    else:
        slices = [("ALL", "Tổng phạm vi", scope)]
        if group_by == "area":
            slices = [(a, a, {**scope, "scope_area_code": a}) for a in
                      ([scope_area_code] if scope_area_code else ["MB", "MT", "MN"])]
        elif group_by == "channel":
            slices = [(c, c, {**scope, "scope_channel": c}) for c in
                      ([scope_channel] if scope_channel and scope_channel != "ALL" else ["OTC", "ETC"])]
        # Loi 1 (review 30/09): ke hoach ETC chi co toan quoc, _ytd_plan theo mien tra total=None trong khi thuc te la
        # OTC+ETC -> dong mien khong co chi tieu/gap/%. Loc theo mien ma khong chi kenh: chi tinh OTC cho khop ke hoach.
        chinh, doi_sang_otc = [], False
        for key, label, filters in slices:
            if filters.get("scope_area_code") and str(filters.get("scope_channel") or "ALL").upper() == "ALL":
                filters = {**filters, "scope_channel": "OTC"}
                label = f"{label} · OTC"
                doi_sang_otc = True
            chinh.append((key, label, filters))
        if doi_sang_otc:
            notes.append("Kế hoạch ETC chỉ có toàn quốc, không tách theo miền, nên dòng theo miền chỉ tính OTC: "
                         "thực tế OTC so với kế hoạch OTC của miền.")
        slices = chinh

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
            # Compressed monthly totals cannot stand in for same-day MTD.
            if str(first) < rt._detail_cutoff():
                raise ValueError("Lịch sử chỉ còn tổng tháng")
            if kpi:
                a, b = revenue(first, comparable, pace_scope), revenue(first, last, pace_scope)
                partial = {row["key"]: a for row in current}
                full = {row["key"]: b for row in current}
            else:
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
        target = row["target"]
        du_dat = None
        if target and ratios and period == "month" and as_of != end:
            du_dat = sum(1 for r in ratios if actual * r >= target)
        row.update(scenarios=scenarios, history_months=samples, history_count=len(samples),
                   gap=gap, needed_per_day=(gap / remaining if remaining else (0 if gap == 0 else None)) if gap is not None else None,
                   projected_gap=(target - row["linear"]) if target is not None else None,
                   linear_pct=(row["linear"] / target * 100) if target else None,
                   base_pct=(scenarios["base"] / target * 100) if target and scenarios else None,
                   months_pace_reaching_target=du_dat)
    co_pct = [r for r in current if r.get("linear_pct") is not None]
    ranking = [{"label": r["label"], "linear_pct": r["linear_pct"], "base_pct": r["base_pct"],
                "months_pace_reaching_target": r["months_pace_reaching_target"], "history_count": r["history_count"]}
               for r in sorted(co_pct, key=lambda r: (r["linear_pct"], str(r["label"])))] if len(co_pct) > 1 else []
    return {"period": period, "as_of": str(as_of), "period_from": str(quarter_start if period == "quarter" else start),
            "ranking_lowest_first": ranking, "notes": notes,
            "period_to": str(quarter_end if period == "quarter" else end), "rows": current,
            "basis": "KPI đội/nhân viên" if kpi else "Doanh thu hóa đơn",
            "scope": scope, "skipped_history": skipped,
            "method": "Tháng: lũy kế / ngày lịch đã qua × số ngày tháng. Quý: thực tế các tháng đã đóng + nhịp ngày tháng hiện tại cho phần còn lại.",
            "scenario_note": "Xấu/cơ sở/tốt dùng min/trung vị/max tỷ lệ cuối tháng trên lũy kế cùng ngày của tối đa 6 tháng trước; cần ít nhất 3 tháng hợp lệ. Không phải khoảng tin cậy hay xác suất đạt. Tháng âm/thiếu lịch sử không có kịch bản.",
            "assumptions": "Giả định nhịp bán và cơ cấu giữ nguyên; chưa mô hình hóa mùa vụ, ngày nghỉ hay chương trình mới."}


def render_projection_method(data):
    """Doan phuong phap/kich ban/gia dinh chung cua moi bang - cau tra loi nhieu bang chi in MOT lan o cuoi."""
    return "\n\n".join([data["method"], data["scenario_note"], data["assumptions"]])


def render_projection(data, kem_phuong_phap=True):
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
    notes = list(dict.fromkeys([*(data.get("notes") or []),
                                *(r["target_note"] for r in data["rows"] if r.get("target_note"))]))
    extra = []
    if data.get("ranking_lowest_first"):
        def pct(v):
            return "—" if v is None else f"{v:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")
        parts = []
        for x in data["ranking_lowest_first"]:
            nhip = (f", {x['months_pace_reaching_target']}/{x['history_count']} tháng có nhịp đủ đạt kế hoạch"
                    if x.get("months_pace_reaching_target") is not None else "")
            parts.append(f"{x['label']} {pct(x['linear_pct'])} (cơ sở {pct(x['base_pct'])}{nhip})")
        extra.append("**Dự phóng đạt thấp nhất so với kế hoạch trước:** " + "; ".join(parts) + ". Đây là xếp hạng "
                     "theo dự phóng và số tháng lịch sử có nhịp đủ đạt, KHÔNG phải xác suất thống kê.")
    phuong_phap = [render_projection_method(data)] if kem_phuong_phap else []
    return "\n".join(lines) + "\n\n" + "\n\n".join([*extra, *phuong_phap, "Lịch sử hợp lệ: " + "; ".join(f"{r['label']}: {r['history_count']}/6 tháng" for r in data["rows"]), *notes])
