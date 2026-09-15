# -*- coding: utf-8 -*-
"""Quy tắc insight dùng CHUNG cho cảnh báo thời gian thực (src/alerts.py) và báo cáo định kỳ
(src/etl.py, main.py) — 14/09/2026.

Vì sao có module này: rà lại toàn bộ cảnh báo cũ trên lịch sử Bravo thật (01/2025-09/2026, chỉ
đọc) cho thấy phần lớn không mang thông tin:
  - bắn gần như liên tục: sụt giảm doanh thu (27% số ngày OTC, 38% ở tuần đầu tháng), mốc ngày
    10/20 theo kênh (17/30 lần OTC), nhịp KPI ngày (TB 78% TDV bị "Đỏ"), mốc 10/20 từng TDV (~90
    người/tháng, gần như ngẫu nhiên), khách lớn sụt giảm (~120 khách OTC/tháng, chỉ đúng 38%),
    khách quá hạn vẫn lên đơn (~134 khách/tháng);
  - không bao giờ bắn: tỷ lệ nợ quá hạn (thực tế ETC 38,8% / OTC 59,1% so với ngưỡng 65% / 80%),
    tập trung doanh thu (top 3 khách chỉ 8-23% so với ngưỡng 50%).
Gốc của nhóm "bắn liên tục": doanh số dồn cuối tháng. OTC có 28% doanh thu tháng rơi vào ngày 26
trở đi; lũy kế tới ngày 15 dao động 22-60% cả tháng. Mọi phép so "chia đều theo ngày" vì vậy báo
động giả vào đầu tháng. Các quy tắc dưới đây so với ĐƯỜNG CONG lũy kế thật của 3 tháng trước.

Hai lớp: hàm THUẦN (không đụng DB, unit test được) và hàm LẤY DỮ LIỆU Bravo (chỉ đọc). Số kiểm
thử ngược ghi ở docstring từng quy tắc. Ngưỡng đọc từ config.yaml
(thresholds.business.insight_rules). CHƯA ngưỡng nào được DNH chốt chính thức.
"""
from __future__ import annotations

import calendar
import copy
import datetime as dt
import math
import time
from collections import defaultdict
from statistics import mean

# ---------------------------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------------------------

DEFAULT_RULES = {
    # Số tháng liền trước dùng làm đường cong lũy kế và mức nền cả tháng.
    "curve_lookback_months": 3,
    # Kiểm thử 05/2025-08/2026, "tháng xấu" = cả tháng < 85% TB 3 tháng trước (OTC 5, ETC 4 tháng):
    #   ETC chậm nhịp >20% từ ngày 8: bắn 14% số ngày, 93% số ngày bắn nằm trong tháng xấu, bắt 4/4.
    #   OTC chậm nhịp >30% từ ngày 10: bắn 17% số ngày, 77% nằm trong tháng xấu, bắt 5/5.
    #   (Quy tắc cũ OTC: bắn 28% số ngày, 69%; ETC: 19%, 58%, bỏ sót 1/4.)
    "channel_pace": {"min_day": {"OTC": 10, "ETC": 8}, "max_gap_pct": {"OTC": 30, "ETC": 20}},
    # Kiểm thử 01-08/2026, đội = QLV có >= 3 TDV, "đúng" = đội cuối tháng < 80% chỉ tiêu:
    #   từ ngày 15, dự phóng < 60%: ~7 đội/tháng (trên 18), đúng 72%.
    #   từ ngày 20, dự phóng < 60%: ~5 đội/tháng, đúng 90%.
    "team_pace": {"min_day": 15, "max_projection_pct": 60, "min_members": 3},
    # Kiểm thử 07/2025-08/2026, "đúng" = cả tháng < 30% mức nền:
    #   OTC nền >= 50tr, mua đủ 6/6 tháng, tới ngày 20 chưa mua: ~11 khách/tháng, đúng 47%.
    #   ETC nền >= 100tr, cùng điều kiện: ~5 khách/tháng, đúng 81%.
    #   (Quy tắc cũ "tháng này giảm >50% so tháng trước": ~120 khách OTC/tháng, đúng 38%.)
    "silent_customer": {"min_day": 20, "lookback_months": 6,
                        "min_baseline": {"OTC": 50_000_000, "ETC": 100_000_000}},
    # 04/08 -> 14/09/2026: 27 khách mới vào nhóm >45 ngày với > 50tr (3,76 tỷ), ~4-5 khách/tuần.
    # max_snapshot_age_days: ban chup cu hon thi CHUA so. May 24 co ban chup cuoi 10/08/2026 (loi ghi
    # ban chup tu do); so thang voi hom nay se bao don vai chuc khach "moi" trong mot lan.
    "new_over45": {"min_value": 50_000_000, "compare_days": 7, "max_snapshot_age_days": 14},
    # 14/09/2026: nợ >45 ngày > 50tr VÀ có đơn trong tháng = 14 khách (đơn 1,42 tỷ);
    # quy tắc cũ (quá hạn bất kỳ > 10tr) = 134 khách.
    "overdue_ordering": {"min_overdue_gt45": 50_000_000},
    # Tỷ lệ trả ETC theo tháng 06/2025-08/2026: 0,04-1,15%, riêng 04/2026 là 7,82% (2,2 tỷ).
    "etc_returns": {"window_days": 30, "min_rate_pct": 3.0, "min_amount": 200_000_000},
}


def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def rule_config(config=None):
    """Ngưỡng quy tắc: mặc định ở DEFAULT_RULES, ghi đè bằng thresholds.business.insight_rules."""
    if config is None:
        try:
            from src.database import load_config
            config = load_config()
        except Exception:
            config = {}
    override = (((config or {}).get("thresholds") or {}).get("business") or {}).get("insight_rules")
    return _deep_merge(DEFAULT_RULES, override)


# ---------------------------------------------------------------------------------------------
# Hàm thuần
# ---------------------------------------------------------------------------------------------

def month_add(year, month, k):
    """(year, month) dời k tháng."""
    idx = year * 12 + (month - 1) + k
    return idx // 12, idx % 12 + 1


def _days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def month_pace(daily, as_of, lookback=3):
    """Tiến độ tháng của MỘT chuỗi doanh thu ngày (vd một kênh) tính đến hết ngày ``as_of``.

    ``daily``: {date: doanh thu}. Kỳ vọng lũy kế tới ngày N = TB tỷ trọng lũy kế tới ngày N nhân TB
    doanh thu cả tháng của ``lookback`` tháng liền trước. Tháng không có doanh thu bị bỏ qua; cần ít
    nhất 2 tháng dùng được, nếu không trả None. ``gap_pct`` dương = đang chậm hơn nhịp thường lệ.
    """
    as_of = _as_date(as_of)
    totals = defaultdict(float)
    by_month = defaultdict(list)
    for day, value in daily.items():
        day = _as_date(day)
        totals[(day.year, day.month)] += float(value or 0)
        by_month[(day.year, day.month)].append((day.day, float(value or 0)))

    def upto(year, month, n):
        return sum(v for d, v in by_month.get((year, month), ()) if d <= n)

    y, m, n = as_of.year, as_of.month, as_of.day
    mtd = upto(y, m, n)
    py, pm = month_add(y, m, -1)
    prev_same = upto(py, pm, min(n, _days_in_month(py, pm)))
    shares, fulls = [], []
    for k in range(1, lookback + 1):
        yy, mm = month_add(y, m, -k)
        full = totals.get((yy, mm), 0.0)
        if full <= 0:
            continue
        shares.append(upto(yy, mm, min(n, _days_in_month(yy, mm))) / full)
        fulls.append(full)
    if len(shares) < 2:
        return None
    exp_share = mean(shares)
    baseline = mean(fulls)
    expected_mtd = exp_share * baseline
    projected = mtd / exp_share if exp_share > 0 else None
    return {
        "as_of": as_of.isoformat(),
        "day": n,
        "days_in_month": _days_in_month(y, m),
        "mtd": mtd,
        "prev_month_same_days": prev_same,
        "vs_prev_month_same_days_pct": (mtd / prev_same - 1) * 100 if prev_same > 0 else None,
        "baseline_full_month": baseline,
        "expected_share_pct": exp_share * 100,
        "expected_mtd": expected_mtd,
        "gap_pct": (expected_mtd - mtd) / expected_mtd * 100 if expected_mtd > 0 else None,
        "projected_full_month": projected,
        "projected_vs_baseline_pct": (projected / baseline - 1) * 100 if projected is not None else None,
        "months_used": len(shares),
    }


def channel_pace_breach(pace, min_day, max_gap_pct):
    """True khi đã tới ngày đánh giá và kênh chậm hơn nhịp thường lệ quá ``max_gap_pct`` %."""
    return bool(pace and pace.get("gap_pct") is not None
                and pace["day"] >= min_day and pace["gap_pct"] > max_gap_pct)


def worsen_bucket(value, step):
    """Làm tròn XUỐNG theo bậc ``step``.

    Cơ chế chống lặp (src/alerts.py::should_send_alert) gửi lại trong thời gian chờ khi giá trị TĂNG.
    Truyền giá trị thô thì chỉ xấu đi 0,1 điểm cũng gửi lại; truyền bậc thì chỉ gửi lại khi xấu đi
    thêm trọn một bậc.
    """
    return math.floor(float(value) / step) * step


def team_pace(members, expected_share, min_members=3):
    """Gộp TDV theo đội QLV và dự phóng cuối tháng theo đường cong.

    ``members``: dict có team_code, target, actual (thêm area_code nếu có). ``expected_share``: tỷ
    trọng lũy kế thường lệ tới hôm nay (0..1). Đội dưới ``min_members`` TDV bị bỏ vì một hai người
    dao động quá mạnh. Kết quả sắp theo dự phóng tăng dần.
    """
    if not expected_share or expected_share <= 0:
        return []
    groups = {}
    for row in members:
        code = row.get("team_code")
        if not code:
            continue
        group = groups.setdefault(code, {"team_code": code, "members": 0, "target": 0.0,
                                         "actual": 0.0, "areas": defaultdict(int)})
        group["members"] += 1
        group["target"] += float(row.get("target") or 0)
        group["actual"] += float(row.get("actual") or 0)
        if row.get("area_code"):
            group["areas"][row["area_code"]] += 1
    out = []
    for group in groups.values():
        if group["members"] < min_members or group["target"] <= 0:
            continue
        areas = group.pop("areas")
        group["area_code"] = max(areas, key=areas.get) if areas else None
        group["achievement_pct"] = group["actual"] / group["target"] * 100
        group["projection_pct"] = group["actual"] / expected_share / group["target"] * 100
        out.append(group)
    out.sort(key=lambda g: g["projection_pct"])
    return out


def silent_regular_customers(history, current_mtd, as_of, lookback=6, min_baseline=0.0):
    """Khách mua ĐỀU mà tới hôm nay trong tháng chưa có đơn nào.

    ``history``: {cc: {(year, month): (doanh thu cả tháng, doanh thu từ ngày 1 tới ngày as_of.day)}}
    cho các tháng trước. ``current_mtd``: {cc: doanh thu tháng này tới as_of}. Điều kiện: có mua đủ
    ``lookback`` tháng liền trước, TB tháng >= ``min_baseline``, ít nhất ``lookback-1`` tháng đã có
    đơn trước ngày tương ứng (tức "thường thì tới giờ này đã mua"), và tháng này chưa mua.
    """
    as_of = _as_date(as_of)
    months = [month_add(as_of.year, as_of.month, -k) for k in range(1, lookback + 1)]
    out = []
    for cc, per_month in history.items():
        fulls = [float(per_month.get(mo, (0.0, 0.0))[0] or 0) for mo in months]
        if any(value <= 0 for value in fulls):
            continue
        baseline = mean(fulls)
        if baseline < min_baseline:
            continue
        ordered_by_day = sum(1 for mo in months if float(per_month.get(mo, (0.0, 0.0))[1] or 0) > 0)
        if ordered_by_day < lookback - 1:
            continue
        if float(current_mtd.get(cc, 0) or 0) > 0:
            continue
        out.append({"customer_code": cc, "baseline_monthly": baseline,
                    "months_ordered_by_this_day": ordered_by_day, "lookback_months": lookback})
    out.sort(key=lambda r: -r["baseline_monthly"])
    return out


def new_over45_debtors(current, previous, min_value):
    """Khách có nợ >45 ngày vượt ``min_value`` mà ở bản chụp trước chưa có đồng nợ >45 ngày nào.

    ``current``: {cc: dict(customer_name, sales_channel, area_code, overdue_gt_45)}.
    ``previous``: {cc: nợ >45 ngày tại bản chụp cũ}; vắng mặt nghĩa là 0.
    """
    out = []
    for cc, row in current.items():
        value = float(row.get("overdue_gt_45") or 0)
        if value <= min_value or float(previous.get(cc, 0) or 0) > 0:
            continue
        out.append({**row, "customer_code": cc, "overdue_gt_45": value})
    out.sort(key=lambda r: -r["overdue_gt_45"])
    return out


def _field(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name, None)


def overdue_customers_still_ordering(receivables, orders, min_gt45):
    """Khách nợ >45 ngày từ ``min_gt45`` trở lên mà vẫn có đơn trong kỳ ``orders`` ({cc: (số đơn, giá trị)})."""
    out = []
    for row in receivables:
        cc = _field(row, "customer_code")
        gt45 = float(_field(row, "overdue_gt_45") or 0)
        # ``orders`` khóa (mã KH, kênh) thì chỉ tính đơn CÙNG kênh với dòng nợ; khóa mã KH thì như cũ.
        order = orders.get((cc, _field(row, "sales_channel")), orders.get(cc))
        if gt45 < min_gt45 or not order or int(order[0] or 0) <= 0:
            continue
        out.append({"customer_code": cc, "customer_name": _field(row, "customer_name"),
                    "sales_channel": _field(row, "sales_channel"), "area_code": _field(row, "area_code"),
                    "overdue_gt_45": gt45, "balance_end": float(_field(row, "balance_end") or 0),
                    "new_orders": int(order[0]), "new_order_value": float(order[1] or 0)})
    out.sort(key=lambda r: -r["overdue_gt_45"])
    return out


def return_rate_breach(returns_amount, net_sales, min_rate_pct, min_amount):
    """(tỷ lệ trả %, có vượt ngưỡng). Doanh số view ETC đã trừ hàng trả nên mẫu số = net + trả."""
    returns_amount = float(returns_amount or 0)
    gross = float(net_sales or 0) + returns_amount
    rate = returns_amount / gross * 100 if gross > 0 else None
    return rate, bool(rate is not None and rate > min_rate_pct and returns_amount >= min_amount)


def region_key_of_area(area_code):
    """'MB'/'MB2' -> 'bac', 'MN' -> 'nam', 'MT' -> 'trung'; không rõ -> None."""
    from src.region_map import REGION_SQL_MARKERS
    value = str(area_code or "").strip().upper()
    if value == "MB1":
        value = "MB"
    for key, markers in REGION_SQL_MARKERS.items():
        if value in markers:
            return key
    return None


def scope_insight_bundle(bundle, region=None, channel=None):
    """Lọc bundle (tính một lần cho toàn công ty) về đúng phạm vi vùng/kênh của một người nhận.

    Dòng không xác định được vùng chỉ hiện cho người nhận toàn quốc: thà ẩn còn hơn lộ dữ liệu
    vùng khác. Tiến độ đội QLV chỉ có ở OTC.
    """
    def keep(row):
        if region and row.get("region_key") != region:
            return False
        if channel and row.get("sales_channel") and row["sales_channel"] != channel:
            return False
        return True

    team = dict(bundle.get("team_pace") or {})
    team["at_risk"] = [] if channel == "ETC" else [r for r in team.get("at_risk", []) if keep(r)]
    team["not_projected"] = [] if channel == "ETC" else [r for r in team.get("not_projected", []) if keep(r)]
    team["applicable"] = channel != "ETC"
    out = {
        "as_of": bundle.get("as_of"),
        "team_pace": team,
        "errors": dict(bundle.get("errors") or {}),
    }
    for name in ("silent_customers", "new_over45", "overdue_ordering"):
        part = dict(bundle.get(name) or {})
        part["rows"] = [r for r in part.get("rows", []) if keep(r)]
        out[name] = part
    return out


# ---------------------------------------------------------------------------------------------
# Lấy dữ liệu Bravo (CHỈ ĐỌC)
# ---------------------------------------------------------------------------------------------

_VIEWS = (("OTC", "dbo.vHoaDonTotal"), ("ETC", "dbo.vHoaDonETCTotal"))


def _engine():
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    return engine


def fetch_daily_revenue(date_from, date_to, region=None):
    """{'OTC': {date: doanh thu}, 'ETC': {...}} trong [date_from, date_to], cùng định nghĩa với
    src/etl.py::_period_revenue (tổng Amount9 của 2 view gốc, đã trừ hàng trả). Ngày truyền dạng
    chuỗi ISO vì driver ODBC cũ lỗi khi bind kiểu date."""
    from sqlalchemy import bindparam, text
    from src.region_map import REGION_SQL_MARKERS, customer_region_resolve_sql

    markers = REGION_SQL_MARKERS.get(region) if region else None
    date_from, date_to = _as_date(date_from), _as_date(date_to)
    out = {"OTC": {}, "ETC": {}}
    with _engine().connect() as conn:
        for channel, view in _VIEWS:
            join, where = "", ""
            params = {"f": date_from.isoformat(), "t": (date_to + dt.timedelta(days=1)).isoformat()}
            if markers:
                join, area_expr = customer_region_resolve_sql("v", channel)
                where = f" AND {area_expr} IN :markers"
                params["markers"] = tuple(markers)
            sql = text(f"SELECT CAST(v.DocDate AS date) AS d, SUM(v.Amount9) AS rev FROM {view} v {join} "
                       f"WHERE v.DocDate >= :f AND v.DocDate < :t{where} GROUP BY CAST(v.DocDate AS date)")
            if markers:
                sql = sql.bindparams(bindparam("markers", expanding=True))
            for day, rev in conn.execute(sql, params).fetchall():
                out[channel][_as_date(day)] = float(rev or 0)
    return out


def fetch_customer_month_history(as_of, lookback):
    """Doanh thu khách x tháng cho ``lookback`` tháng trước và tháng của ``as_of``, kèm lũy kế tới
    ngày ``as_of.day`` của từng tháng. Loại mã rác bằng customer_keep_filter_sql như cảnh báo cũ."""
    from sqlalchemy import text
    from src.region_map import customer_keep_filter_sql

    as_of = _as_date(as_of)
    sy, sm = month_add(as_of.year, as_of.month, -lookback)
    params = {"f": dt.date(sy, sm, 1).isoformat(), "t": (as_of + dt.timedelta(days=1)).isoformat(),
              "n": as_of.day}
    current = (as_of.year, as_of.month)
    out = {}
    with _engine().connect() as conn:
        for channel, view in _VIEWS:
            join, keep = customer_keep_filter_sql("v", channel)
            sql = text(f"""
                SELECT v.CustomerCode AS cc, MAX(k.Name) AS cname, YEAR(v.DocDate) AS y, MONTH(v.DocDate) AS m,
                       SUM(v.Amount9) AS full_rev,
                       SUM(CASE WHEN DAY(v.DocDate) <= :n THEN v.Amount9 ELSE 0 END) AS upto_rev
                FROM {view} v {join}
                WHERE {keep} AND v.DocDate >= :f AND v.DocDate < :t
                GROUP BY v.CustomerCode, YEAR(v.DocDate), MONTH(v.DocDate)""")
            history, current_mtd, names = defaultdict(dict), {}, {}
            for row in conn.execute(sql, params).fetchall():
                key = (int(row.y), int(row.m))
                names[row.cc] = row.cname or row.cc
                if key == current:
                    current_mtd[row.cc] = float(row.full_rev or 0)
                else:
                    history[row.cc][key] = (float(row.full_rev or 0), float(row.upto_rev or 0))
            out[channel] = {"history": dict(history), "current_mtd": current_mtd, "names": names}
    return out


def fetch_etc_returns(date_from, date_to):
    """(giá trị hàng trả ETC còn hiệu lực, doanh số ETC thuần) trong [date_from, date_to]."""
    from sqlalchemy import text
    params = {"f": _as_date(date_from).isoformat(),
              "t": (_as_date(date_to) + dt.timedelta(days=1)).isoformat()}
    with _engine().connect() as conn:
        returns = conn.execute(text(
            "SELECT COALESCE(SUM(Amount9), 0) FROM dbo.BRVSX_TraLai "
            "WHERE IsActive = 1 AND DocDate >= :f AND DocDate < :t"), params).scalar()
        sales = conn.execute(text(
            "SELECT COALESCE(SUM(Amount9), 0) FROM dbo.vHoaDonETCTotal "
            "WHERE DocDate >= :f AND DocDate < :t"), params).scalar()
    return float(returns or 0), float(sales or 0)


# ---------------------------------------------------------------------------------------------
# Bundle: tính một lần, dùng chung cho cảnh báo và 6 người nhận báo cáo
# ---------------------------------------------------------------------------------------------

_BUNDLE_TTL_SECONDS = 600
_BUNDLE_CACHE = {"ts": 0.0, "data": None}
_PACE_CACHE = {}


def _curve_window_start(as_of, lookback):
    y, m = month_add(as_of.year, as_of.month, -lookback)
    return dt.date(y, m, 1)


def channel_pace_for_scope(as_of, region=None, channel=None, rules=None):
    """Tiến độ tháng từng kênh trong phạm vi vùng (cache 10 phút theo ngày dữ liệu + vùng)."""
    rules = rules or rule_config()
    as_of = _as_date(as_of)
    lookback = int(rules["curve_lookback_months"])
    key = (as_of, region)
    cached = _PACE_CACHE.get(key)
    if cached and time.time() - cached[0] < _BUNDLE_TTL_SECONDS:
        paces = cached[1]
    else:
        daily = fetch_daily_revenue(_curve_window_start(as_of, lookback), as_of, region=region)
        paces = {ch: month_pace(series, as_of, lookback) for ch, series in daily.items()}
        _PACE_CACHE[key] = (time.time(), paces)
    return {ch: pace for ch, pace in paces.items() if not channel or ch == channel}


def _team_pace_part(as_of, otc_pace, rules):
    from src.alerts import get_bravo_kpi_tdv_snapshot, get_bravo_manager_codes
    rule = rules["team_pace"]
    part = {"evaluated": as_of.day >= int(rule["min_day"]), "min_day": int(rule["min_day"]),
            "threshold_pct": float(rule["max_projection_pct"]), "teams": [], "at_risk": []}
    if not otc_pace or not otc_pace.get("expected_share_pct"):
        # 15/09/2026: không có nhịp OTC thì KHÔNG dự phóng được - ghi lý do, không để lặng thành "0 đội".
        part["skipped_reason"] = "Chưa có nhịp doanh thu OTC để dự phóng đội."
        return part
    tdvs = get_bravo_kpi_tdv_snapshot(position_codes=("TDV",))
    # QLV thật có thể bị Bravo gắn nhầm cờ trùng (xem get_bravo_kpi_tdv_snapshot) nên lấy tên kèm cả dòng trùng.
    names = {r.employee_code: r.employee_name
             for r in get_bravo_kpi_tdv_snapshot(position_codes=("QLV",), include_duplicates=True)}
    members = [{"team_code": r.manager_code, "target": r.month_sale_target,
                "actual": r.month_sale_amount, "area_code": r.area_code} for r in tdvs]
    teams = team_pace(members, otc_pace["expected_share_pct"] / 100, int(rule["min_members"]))
    for team in teams:
        team["team_name"] = names.get(team["team_code"]) or team["team_code"]
        team["region_key"] = region_key_of_area(team.get("area_code"))
        team["sales_channel"] = "OTC"
    part["teams"] = teams
    if part["evaluated"]:
        part["at_risk"] = [t for t in teams if t["projection_pct"] < part["threshold_pct"]]
    # 15/09/2026: đội/nhóm có chỉ tiêu nhưng KHÔNG dự phóng phải nêu tên. Tháng 9/2026 là MBKV12 (Chợ sỉ
    # MB 7,55 tỷ), MN1 "Kênh MT" 6,65 tỷ, MN4 "Chợ sỉ" 1,70 tỷ - 18,95/58,14 tỷ chỉ tiêu OTC lặng lẽ vắng
    # mặt. Không dự phóng chúng là ĐÚNG (1-2 người, doanh số dồn vài đơn lớn, đường cong OTC vô nghĩa)
    # nhưng người đọc phải biết. Dự phóng chỉ gồm phần chỉ tiêu của TDV (ngưỡng đã kiểm thử ngược theo
    # cách này) - phần QLV tự phụ trách chưa tính, xem basis_note.
    part["basis_note"] = ("Dự phóng tính trên chỉ tiêu và doanh số của TDV trong đội; phần chỉ tiêu QLV tự "
                          "phụ trách chưa tính vào.")
    try:
        managers = get_bravo_manager_codes()
        rollup = [r for r in get_bravo_kpi_tdv_snapshot(position_codes=("TDV", "QLV"), include_duplicates=True)
                  if r.employee_code in managers]
    except Exception as exc:
        part["not_projected_error"] = str(exc)
        rollup = []
    projected = {t["team_code"] for t in teams}
    seen = set()
    not_projected = []
    for r in rollup:
        if r.employee_code in projected or r.employee_code in seen or not (r.month_sale_target or 0) > 0:
            continue
        seen.add(r.employee_code)
        not_projected.append({"team_code": r.employee_code, "team_name": r.employee_name or r.employee_code,
                              "target": float(r.month_sale_target), "sales_channel": "OTC",
                              "region_key": region_key_of_area(r.area_code)})
    part["not_projected"] = sorted(not_projected, key=lambda t: -t["target"])
    return part


def _silent_part(as_of, rules):
    from src.alerts import get_customer_regions_by_code
    rule = rules["silent_customer"]
    part = {"evaluated": as_of.day >= int(rule["min_day"]), "min_day": int(rule["min_day"]), "rows": []}
    if not part["evaluated"]:
        return part
    lookback = int(rule["lookback_months"])
    data = fetch_customer_month_history(as_of, lookback)
    for channel, payload in data.items():
        found = silent_regular_customers(payload["history"], payload["current_mtd"], as_of, lookback,
                                         float(rule["min_baseline"][channel]))
        regions = get_customer_regions_by_code([r["customer_code"] for r in found], channel) if found else {}
        label_to_key = _label_to_region_key()
        for row in found:
            row.update(customer_name=payload["names"].get(row["customer_code"]), sales_channel=channel,
                       region_key=label_to_key.get(regions.get(row["customer_code"])))
        part["rows"].extend(found)
    return part


def _label_to_region_key():
    from src.region_map import REGION_NAMES_VI
    return {label: key for key, label in REGION_NAMES_VI.items()}


def _overdue_ordering_part(as_of, snapshot, rules):
    from src import alerts
    # 15/09/2026: đơn cùng kênh với dòng nợ, chặn chứng từ đề ngày sau hôm nay.
    orders = alerts._bravo_recent_orders_by_customer(
        as_of.replace(day=1), until=dt.date.today() + dt.timedelta(days=1), by_channel=True)
    rows = overdue_customers_still_ordering(snapshot, orders,
                                            float(rules["overdue_ordering"]["min_overdue_gt45"]))
    for row in rows:
        row["region_key"] = region_key_of_area(row.get("area_code"))
    return {"rows": rows}


def _new_over45_part(snapshot, rules, today=None):
    from src import alerts
    # Nợ >45 ngày gộp theo khách (một khách có thể có cả dòng OTC lẫn ETC). SP công nợ có trả dòng
    # không mã khách (xác nhận 14/09/2026) — bỏ qua, vừa vô nghĩa vừa làm hỏng khóa của bản chụp.
    current = {}
    theo_kenh = {}
    for row in snapshot:
        if not row.customer_code:
            continue
        amount = float(row.overdue_gt_45 or 0)
        entry = current.setdefault(row.customer_code, {
            "customer_name": row.customer_name, "sales_channel": row.sales_channel,
            "area_code": row.area_code, "overdue_gt_45": 0.0})
        entry["overdue_gt_45"] += amount
        if amount > 0:
            kenh = theo_kenh.setdefault((row.customer_code, row.sales_channel), {
                "customer_name": row.customer_name, "sales_channel": row.sales_channel,
                "area_code": row.area_code, "overdue_gt_45": 0.0})
            kenh["overdue_gt_45"] += amount
    # Bản chụp chỉ tích lũy khi có người chạy; báo cáo cũng ghi để lịch sử không phụ thuộc job cảnh báo.
    alerts._save_debt_aging_snapshot([(cc, r["customer_name"], r["overdue_gt_45"]) for cc, r in current.items()])
    rule = rules["new_over45"]
    today = today or dt.date.today()
    before = (today - dt.timedelta(days=int(rule["compare_days"]))).isoformat()
    compared_with = alerts._find_debt_snapshot_on_or_before(before)
    max_age = int(rule.get("max_snapshot_age_days", 14))
    stale = bool(compared_with) and (today - _as_date(compared_with)).days > max_age
    part = {"available": bool(compared_with) and not stale, "compared_with": compared_with,
            "stale_snapshot": compared_with if stale else None,
            "compare_days": int(rule["compare_days"]), "min_value": float(rule["min_value"]), "rows": []}
    if part["available"]:
        previous = {cc: amount for cc, (_, amount) in alerts._get_debt_aging_snapshot(compared_with).items()}
        # Khách "mới vào nhóm >45 ngày" xét trên TỔNG hai kênh (khớp bản chụp theo khách), nhưng mỗi
        # kênh có nợ >45 ngày là một dòng riêng với đúng số và vùng của kênh đó. 15/09/2026: bản cũ lấy
        # kênh của dòng đầu, nên nợ ETC có thể gửi nhầm giám đốc OTC kèm số gộp cả hai kênh.
        rows = []
        for moi in new_over45_debtors(current, previous, float(rule["min_value"])):
            cc = moi["customer_code"]
            for (ma, _kenh), kenh in theo_kenh.items():
                if ma != cc:
                    continue
                rows.append({**kenh, "customer_code": cc,
                             "overdue_gt_45_all_channels": moi["overdue_gt_45"],
                             "region_key": region_key_of_area(kenh.get("area_code"))})
        rows.sort(key=lambda r: -r["overdue_gt_45"])
        part["rows"] = rows
    return part


def build_insight_bundle(as_of=None, rules=None, force=False):
    """Tính MỘT lần mọi insight cho toàn công ty (cache 10 phút). Mỗi phần tự bắt lỗi và ghi vào
    ``errors`` để báo cáo vẫn dựng được phần còn lại thay vì hỏng cả bản."""
    now = time.time()
    if not force and _BUNDLE_CACHE["data"] is not None and now - _BUNDLE_CACHE["ts"] < _BUNDLE_TTL_SECONDS:
        return _BUNDLE_CACHE["data"]
    rules = rules or rule_config()
    if as_of is None:
        from src.alerts import _last_complete_data_day
        as_of = _last_complete_data_day()
    if as_of is None:
        raise RuntimeError("Chưa xác định được ngày dữ liệu đã đồng bộ xong.")
    as_of = _as_date(as_of)
    bundle = {"as_of": as_of, "rules": rules, "errors": {},
              "channel_pace": {}, "team_pace": {"evaluated": False, "teams": [], "at_risk": []},
              "silent_customers": {"evaluated": False, "rows": []},
              "new_over45": {"available": False, "rows": []}, "overdue_ordering": {"rows": []}}
    try:
        bundle["channel_pace"] = channel_pace_for_scope(as_of, rules=rules)
    except Exception as exc:
        bundle["errors"]["channel_pace"] = str(exc)
    try:
        bundle["team_pace"] = _team_pace_part(as_of, bundle["channel_pace"].get("OTC"), rules)
    except Exception as exc:
        bundle["errors"]["team_pace"] = str(exc)
    try:
        bundle["silent_customers"] = _silent_part(as_of, rules)
    except Exception as exc:
        bundle["errors"]["silent_customers"] = str(exc)
    try:
        from src.alerts import get_bravo_receivables_snapshot
        snapshot = get_bravo_receivables_snapshot()
    except Exception as exc:
        bundle["errors"]["receivables"] = str(exc)
        snapshot = None
    if snapshot is not None:
        # Hai phần riêng khối lỗi: 14/09/2026 một dòng công nợ thiếu mã khách làm hỏng bước ghi bản
        # chụp, và khi chung một khối thì mất luôn danh sách "nợ >45 ngày vẫn lên đơn".
        try:
            bundle["overdue_ordering"] = _overdue_ordering_part(as_of, snapshot, rules)
        except Exception as exc:
            bundle["errors"]["overdue_ordering"] = str(exc)
        try:
            bundle["new_over45"] = _new_over45_part(snapshot, rules)
        except Exception as exc:
            bundle["errors"]["new_over45"] = str(exc)
    _BUNDLE_CACHE.update(ts=now, data=bundle)
    return bundle
