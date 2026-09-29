"""Small, validated chart payloads derived solely from allowlisted tool results."""
import math
from feature_policy import feature_enabled


def validate_charts(charts):
    if not isinstance(charts, list):
        return []
    out = []
    for chart in charts[:3]:
        if not isinstance(chart, dict) or chart.get("version") != 1 or chart.get("kind") not in {"bar", "line"}:
            continue
        labels, series = chart.get("labels"), chart.get("series")
        if not isinstance(labels, list) or not 1 <= len(labels) <= 24 or not all(isinstance(x, str) for x in labels):
            continue
        if not isinstance(series, list) or not 1 <= len(series) <= 5:
            continue
        cleaned = []
        for s in series:
            if not isinstance(s, dict) or not isinstance(s.get("values"), list) or len(s["values"]) != len(labels):
                break
            if not all(v is None or (type(v) in (float, int) and math.isfinite(v) and abs(v) < 1e18) for v in s["values"]):
                break
            cleaned.append({"name": str(s.get("name", ""))[:80], "values": s["values"]})
        if len(cleaned) != len(series):
            continue
        out.append({"version": 1, "kind": chart["kind"], "title": str(chart.get("title", ""))[:160],
                    "unit": "VND", "labels": [x[:80] for x in labels], "series": cleaned,
                    "note": str(chart.get("note", ""))[:500]})
    return out


def build_charts(tool_name, wrapped):
    if not feature_enabled("DNH_BAT_BIEU_DO") or not isinstance(wrapped, dict) or not wrapped.get("ok"):
        return []
    data = wrapped.get("result")
    if not isinstance(data, dict) or data.get("error") or data.get("feature_disabled"):
        return []
    chart = {"version": 1, "kind": "bar", "unit": "VND", "note": "Số liệu lấy trực tiếp từ báo cáo theo quyền tài khoản."}
    if tool_name == "get_current_period_projection":
        rows = data.get("rows", [])[:12]
        chart.update(title="Thực tế, chỉ tiêu và dự phóng", labels=[str(r["label"]) for r in rows],
                     series=[{"name": name, "values": [r.get(key) for r in rows]} for key, name in
                             [("actual", "Thực tế"), ("target", "Chỉ tiêu"), ("linear", "Dự phóng tuyến tính")]],
                     note=f"Dữ liệu đến {data.get('as_of')}. Dự phóng là ước tính, không phải thực tế hay xác suất. Hiển thị tối đa 12 nhóm.")
    elif tool_name == "get_revenue_by_channel":
        allowed = [c for c in ("otc", "etc") if c in data and data[c].get("revenue") is not None]
        # Scoped reports zero the forbidden channel; omit zero channels rather than suggest access.
        allowed = [c for c in allowed if data[c]["revenue"] != 0]
        chart.update(title="Doanh thu theo kênh", labels=[c.upper() for c in allowed],
                     series=[{"name": "Doanh thu", "values": [data[c]["revenue"] for c in allowed]}])
    elif tool_name == "get_revenue_monthly_series":
        rows = data.get("months", [])[-24:]
        chart.update(kind="line", title="Doanh thu theo tháng", labels=[r["month"] for r in rows],
                     series=[{"name": "Doanh thu", "values": [r.get("revenue") for r in rows]}],
                     note="Tháng đang chạy chỉ gồm số phát sinh đến ngày dữ liệu trong báo cáo.")
    else:
        return []
    return validate_charts([chart])
