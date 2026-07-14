import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from src.database import get_db_engines, load_config

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'alerts_state.db')

def get_low_inventory(erp_engine, limit):
    """
    Trích xuất các sản phẩm có tồn kho thấp dưới ngưỡng limit
    """
    query = """
        SELECT sku, item_name, quantity, updated_at
        FROM inventory
        WHERE quantity < :limit
    """
    # Sử dụng pandas.read_sql với parameter bind
    df = pd.read_sql(query, erp_engine, params={"limit": limit})
    return df

def get_recent_failed_orders(erp_engine, lookback_hours):
    """
    Trích xuất danh sách và số lượng đơn hàng lỗi trong khoảng thời gian lookback
    """
    lookback_time = datetime.now() - timedelta(hours=lookback_hours)

    # Do SQLite và SQL Server có cú pháp so sánh ngày khác nhau,
    # ta có thể dùng định dạng ISO string hoặc parameter binding chuẩn để SQLAlchemy xử lý
    query = """
        SELECT id, customer_id, amount, order_date, status
        FROM orders
        WHERE status = 'Failed' AND order_date >= :lookback_time
    """
    df = pd.read_sql(query, erp_engine, params={"lookback_time": lookback_time})
    return df

def get_unresolved_urgent_tickets(crm_engine):
    """
    Trích xuất danh sách support ticket ưu tiên Urgent chưa giải quyết
    """
    query = """
        SELECT id, customer_id, priority, status, created_at
        FROM support_tickets
        WHERE priority = 'Urgent' AND status = 'Open'
    """
    df = pd.read_sql(query, crm_engine)
    return df

def _region_markers(region):
    """region: None hoặc 'bac'/'nam'/'trung' -> danh sách mã AreaCode tương ứng, dùng chung quy
    ước với DNHChatbot._REGION_SQL_MARKERS (nguồn chuẩn duy nhất cho mapping vùng/mã)."""
    if not region:
        return None
    from ai_agent.chatbot import DNHChatbot
    return DNHChatbot._REGION_SQL_MARKERS.get(region)

def _region_label(area_code):
    """Map area_code thô sang tên miền tiếng Việt — bản sao gọn của
    src/alerts.py::normalize_region_label, tách riêng để tránh vòng lặp import (alerts.py đã
    import từ etl.py). Cả 2 đều đọc từ cùng 1 nguồn DNHChatbot._REGION_SQL_MARKERS/_REGION_NAMES_VI."""
    if not area_code:
        return "Không rõ"
    from ai_agent.chatbot import DNHChatbot
    val = str(area_code).strip().upper()
    for region_key, markers in DNHChatbot._REGION_SQL_MARKERS.items():
        if val in markers:
            return DNHChatbot._REGION_NAMES_VI[region_key]
    return str(area_code)

def _period_revenue(start_dt, end_dt, region=None):
    """Doanh thu OTC+ETC thuần trong [start_dt, end_dt). region: None (không lọc) hoặc
    'bac'/'nam'/'trung' — lọc theo AreaCode qua CityId -> DIM_TinhThanhPho.
    Trả (otc_rev, etc_rev, otc_invoice_count, etc_invoice_count) — tách riêng số hóa đơn từng
    kênh (13/07/2026, trước đó gộp chung 1 số duy nhất, không rõ ràng khi xem báo cáo).

    14/07/2026: đổi hẳn sang query THẲNG 2 view gốc Bravo (dbo.vHoaDonTotal cho OTC,
    dbo.vHoaDonETCTotal cho ETC) thay vì tự ráp lại logic từ bảng thô — xác nhận thực tế:
    công thức tự ráp trước đó (JOIN brv_hoadonct/brv_hoadonhdr + loại CTKM/hủy) lệch ETC ~4%/ngày
    so với 2 view này, vì view gốc còn TRỪ hàng trả lại (BRVSX_TraLai), lọc theo trạng thái đã ghi
    thẻ kho (Post_TheKho=1), loại thêm 1 số mã khách hàng cụ thể, và CỘNG THÊM nhóm chứng từ "HC"
    (đọc từ BRV_HoaDonHCCt/BRVSX_HoaDonHCCt — 2 bảng CHƯA được đồng bộ sang Supabase) cùng ~10
    trường hợp đặc biệt hardcode theo mã khách hàng — quá phức tạp và rủi ro để tự dịch lại đúng
    100%, nên dùng thẳng view đã được xác nhận là nguồn đúng của DNH.

    HỆ QUẢ: bỏ hẳn failover Postgres/Supabase cho hàm này — 2 view trên CHỈ tồn tại ở Bravo, không
    có bản tương đương bên Supabase. Nếu Bravo mất kết nối, hàm raise lỗi (không âm thầm trả số
    liệu Postgres cũ/gần đúng) — ưu tiên "báo lỗi rõ ràng" hơn "hiện số có thể sai" cho con số quan
    trọng nhất của mọi báo cáo. Các hàm gọi _period_revenue nên tự try/except nếu cần chạy tiếp dù
    thiếu doanh thu (đã áp dụng ở get_digest_metrics/_revenue_trend qua đường try/except sẵn có).
    """
    from sqlalchemy import text, bindparam
    from src.database import _get_bravo_engine

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError(
            "Chưa cấu hình BRAVO_SQL_* trong .env — không còn nguồn nào khác cho doanh thu "
            "(đã bỏ failover Postgres, xem docstring _period_revenue)."
        )

    markers = _region_markers(region)
    params = {"start_dt": start_dt, "end_dt": end_dt}
    # OTC (vHoaDonTotal) KHÔNG lộ sẵn CityId trong cột output -> join thêm qua CustomerCode.
    # ETC (vHoaDonETCTotal) ĐÃ lộ sẵn CityId -> join thẳng DIM_TinhThanhPho, không cần thêm bảng.
    otc_region_join, etc_region_join, region_where = "", "", ""
    if markers:
        otc_region_join = "JOIN dbo.DMS_KhachHang k ON v.CustomerCode = k.Code JOIN dbo.DIM_TinhThanhPho rt ON k.CityId = rt.CityId"
        etc_region_join = "JOIN dbo.DIM_TinhThanhPho rt ON v.CityId = rt.CityId"
        region_where = " AND rt.AreaCode IN :region_markers"
        params["region_markers"] = tuple(markers)

    otc_sql = text(f'''
        SELECT COALESCE(SUM(v.Amount9), 0), COUNT(DISTINCT v.Stt)
        FROM dbo.vHoaDonTotal v
        {otc_region_join}
        WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
        {region_where}
    ''')
    etc_sql = text(f'''
        SELECT COALESCE(SUM(v.Amount9), 0), COUNT(DISTINCT v.Stt)
        FROM dbo.vHoaDonETCTotal v
        {etc_region_join}
        WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
        {region_where}
    ''')
    if markers:
        otc_sql = otc_sql.bindparams(bindparam("region_markers", expanding=True))
        etc_sql = etc_sql.bindparams(bindparam("region_markers", expanding=True))

    with engine.connect() as conn:
        otc_row = conn.execute(otc_sql, params).fetchone()
        etc_row = conn.execute(etc_sql, params).fetchone()

    return float(otc_row[0]), float(etc_row[0]), int(otc_row[1]), int(etc_row[1])


def _revenue_by_region(start_dt, end_dt, channel=None):
    """Breakdown doanh thu theo VÙNG (Bắc/Nam/Trung) trong [start_dt, end_dt) — chỉ gọi cho
    weekly/monthly (không tính hàng ngày, tốn thêm query join). channel=None -> cả 2 kênh.

    14/07/2026: đổi sang query view gốc Bravo (vHoaDonTotal/vHoaDonETCTotal), cùng lý do và cách
    làm với _period_revenue — công thức tự ráp cũ (JOIN bảng thô + loại CTKM/hủy) dùng chung
    logic với _period_revenue nên chắc chắn dính đúng lỗi tương tự (thiếu trừ hàng trả lại...).
    Không còn failover Postgres (view chỉ có ở Bravo, xem docstring _period_revenue)."""
    from sqlalchemy import text
    from src.database import _get_bravo_engine

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError(
            "Chưa cấu hình BRAVO_SQL_* trong .env — không còn nguồn nào khác cho breakdown vùng."
        )

    parts = []
    if channel is None or channel == "OTC":
        parts.append('''
            SELECT rt.AreaCode AS area_code, SUM(v.Amount9) AS rev
            FROM dbo.vHoaDonTotal v
            JOIN dbo.DMS_KhachHang k ON v.CustomerCode = k.Code
            JOIN dbo.DIM_TinhThanhPho rt ON k.CityId = rt.CityId
            WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
            GROUP BY rt.AreaCode
        ''')
    if channel is None or channel == "ETC":
        parts.append('''
            SELECT rt.AreaCode AS area_code, SUM(v.Amount9) AS rev
            FROM dbo.vHoaDonETCTotal v
            JOIN dbo.DIM_TinhThanhPho rt ON v.CityId = rt.CityId
            WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
            GROUP BY rt.AreaCode
        ''')
    if not parts:
        return []
    union_sql = text(f'''
        SELECT area_code, SUM(rev) AS rev FROM ({" UNION ALL ".join(parts)}) x
        GROUP BY area_code ORDER BY rev DESC
    ''')
    try:
        with engine.connect() as conn:
            rows = conn.execute(union_sql, {"start_dt": start_dt, "end_dt": end_dt}).fetchall()
    except Exception as e:
        print(f"[DIGEST] Lỗi truy vấn breakdown vùng: {e}")
        return []
    return [{"region": _region_label(r.area_code), "revenue": round(float(r.rev or 0), 2)} for r in rows]


def _top_customers(start_dt, end_dt, channel_label, region_markers=None):
    """Top 5 khách hàng theo doanh thu trong [start_dt, end_dt) cho 1 kênh (OTC hoặc ETC) —
    dùng cho get_digest_metrics(). Trả list row (CustomerCode, Name, rev). Tự failover
    Supabase -> Bravo qua run_with_failover() (xem _period_revenue)."""
    # 14/07/2026: đổi sang query view gốc Bravo (vHoaDonTotal/vHoaDonETCTotal), cùng lý do và
    # cách làm với _period_revenue — công thức tự ráp cũ dùng chung logic (JOIN bảng thô + loại
    # CTKM/hủy) nên chắc chắn dính đúng lỗi tương tự (thiếu trừ hàng trả lại...). Không còn
    # failover Postgres (view chỉ có ở Bravo, xem docstring _period_revenue).
    from sqlalchemy import text, bindparam
    from src.database import _get_bravo_engine

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError(
            "Chưa cấu hình BRAVO_SQL_* trong .env — không còn nguồn nào khác cho top khách hàng."
        )

    view = "dbo.vHoaDonTotal" if channel_label == "OTC" else "dbo.vHoaDonETCTotal"
    kh_table = "dbo.DMS_KhachHang" if channel_label == "OTC" else "dbo.DMSSX_KhachHang"
    params = {"start_dt": start_dt, "end_dt": end_dt}
    region_join, region_where = "", ""
    if region_markers:
        region_join = "JOIN dbo.DIM_TinhThanhPho rt ON k.CityId = rt.CityId"
        region_where = " AND rt.AreaCode IN :region_markers"
        params["region_markers"] = tuple(region_markers)

    sql = text(f'''
        SELECT TOP 5 v.CustomerCode, k.Name, SUM(v.Amount9) AS rev
        FROM {view} v
        JOIN {kh_table} k ON v.CustomerCode = k.Code
        {region_join}
        WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
        {region_where}
        GROUP BY v.CustomerCode, k.Name
        ORDER BY rev DESC
    ''')
    if region_markers:
        sql = sql.bindparams(bindparam("region_markers", expanding=True))
    with engine.connect() as conn:
        return conn.execute(sql, params).fetchall()


def _revenue_trend(start_dt, end_dt, granularity, region=None, channel=None):
    """Xu hướng doanh thu trong kỳ: 'weekly' -> theo TỪNG NGÀY (7 điểm), 'monthly' -> theo TỪNG
    TUẦN (4-5 điểm). Chạy thêm N truy vấn _period_revenue nhỏ — chấp nhận được vì weekly/monthly
    chỉ chạy 1 lần/tuần hoặc 1 lần/tháng (không nằm trong luồng cảnh báo tần suất cao 5 lần/ngày).

    13/07/2026: kẹp end_dt tại hết hôm nay — get_weekly/monthly_digest_metrics giờ dùng kỳ ĐANG
    CHẠY (chưa hết), nếu không kẹp thì vòng lặp bucket vẽ cả các ngày TƯƠNG LAI (không có dữ liệu,
    toàn số 0), khiến biểu đồ rối/vô nghĩa (vd gửi thứ 2 mà vẽ luôn cả thứ 3 - chủ nhật trống).

    14/07/2026: `channel` trước đó nhận vào nhưng KHÔNG được dùng — mọi điểm trend đều cộng CẢ
    OTC+ETC bất kể channel gì, trong khi phần "Tổng Doanh Thu" chính (get_digest_metrics) đã ép
    đúng kênh được lọc. Hậu quả: audience chỉ được cấp quyền xem 1 kênh (vd "Quản lý Kênh OTC")
    thấy đúng Tổng Doanh Thu (chỉ OTC) nhưng bảng Xu Hướng bên dưới lại lộ cả doanh thu ETC — vừa
    sai số liệu vừa lộ dữ liệu ngoài phạm vi audience được cấp. Sửa: ép về 0 đúng kênh không được
    chọn, khớp với cách get_digest_metrics đã làm cho phần tổng."""
    today_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_dt = min(end_dt, today_end)
    buckets = []
    if granularity == "weekly":
        cur = start_dt
        while cur < end_dt:
            nxt = cur + timedelta(days=1)
            buckets.append((cur, nxt, cur.strftime("%a %d/%m")))
            cur = nxt
    elif granularity == "monthly":
        cur = start_dt
        while cur < end_dt:
            nxt = min(cur + timedelta(days=7), end_dt)
            buckets.append((cur, nxt, f"{cur.strftime('%d/%m')}-{(nxt - timedelta(days=1)).strftime('%d/%m')}"))
            cur = nxt
    else:
        return []

    trend = []
    for b_start, b_end, label in buckets:
        otc_rev, etc_rev, _, _ = _period_revenue(b_start, b_end, region=region)
        if channel == "OTC":
            etc_rev = 0.0
        elif channel == "ETC":
            otc_rev = 0.0
        trend.append({
            "label": label,
            "revenue": round(otc_rev + etc_rev, 2),
            "otc": round(otc_rev, 2),
            "etc": round(etc_rev, 2)
        })
    return trend


def _kpi_summary(conn, region=None):
    """Tóm tắt KPI toàn đội từ kpi_summary — LƯU Ý: bảng này là SNAPSHOT hiện tại, không lưu
    lịch sử theo kỳ (xem ghi chú trong config.yaml), nên số liệu luôn là "tính đến hiện tại",
    không thực sự bó hẹp trong [start_dt, end_dt) của báo cáo tuần/tháng."""
    from sqlalchemy import text, bindparam
    markers = _region_markers(region)
    where = 'month_sale_target > 0'
    params = {}
    if markers:
        where += ' AND area_code IN :region_markers'
        params["region_markers"] = tuple(markers)
    sql = text(f'''
        SELECT COUNT(*) FILTER (WHERE month_sale_percent >= 1.0) AS achieved,
               COUNT(*) AS total,
               COALESCE(SUM(month_sale_target),0) AS total_target,
               COALESCE(SUM(month_sale_amount),0) AS total_amount
        FROM kpi_summary WHERE {where}
    ''')
    if markers:
        sql = sql.bindparams(bindparam("region_markers", expanding=True))
    try:
        row = conn.execute(sql, params).fetchone()
    except Exception as e:
        print(f"[DIGEST] Lỗi truy vấn tóm tắt KPI: {e}")
        return None
    if not row or not row[1]:
        return None
    achieved, total, total_target, total_amount = row
    team_pct = (float(total_amount) / float(total_target)) if total_target else None
    return {
        "achieved_count": int(achieved or 0),
        "total_count": int(total or 0),
        "team_pct": round(team_pct * 100, 1) if team_pct is not None else None,
        "total_target": round(float(total_target), 2),
        "total_amount": round(float(total_amount), 2),
    }


# Tên tiếng Việt + kiểu định dạng giá trị cho từng loại alert_key (prefix trước dấu ":" đầu
# tiên) — dùng để "dịch" các dòng "Điểm Nổi Bật Trong Kỳ" từ key/số thô sang câu chữ đọc được.
# Kiểu giá trị: money (tiền VNĐ) | ratio/percent (0-1 -> %) | qty (số lượng) | count (số nguyên)
# | hours (giờ) | customer (mã khách hàng) | status (chuỗi trạng thái) | raw (giữ nguyên).
_HIGHLIGHT_LABELS = {
    "low_inventory": ("Tồn kho thấp", "qty"),
    "failed_orders_peak": ("Đơn hàng lỗi/hủy tăng đột biến", "count"),
    "crm_urgent_overload": ("Ticket CRM khẩn cấp quá tải", "count"),
    "smart_debt_overdue_top5": ("Top 5 khách nợ quá hạn cao nhất", "money"),
    "smart_inventory_depletion_top5": ("Top 5 mặt hàng sắp cạn kho", "qty"),
    "smart_kpi_low_progress_top5": ("Top 5 KPI tiến độ thấp nhất", "ratio"),
    "sales_kpi_insights_report": ("Báo cáo phân tích KPI doanh số đã gửi", "status"),
    "revenue_drop": ("Doanh thu sụt giảm bất thường", "ratio"),
    "credit_limit_exceeded_top10": ("Top 10 khách vượt hạn mức tín dụng", "money"),
    "company_overdue_ratio": ("Tỷ lệ nợ quá hạn toàn công ty", "percent"),
    "overdue_customer_new_orders": ("Khách quá hạn vẫn phát sinh đơn mới (tổng giá trị đơn)", "money"),
    "aging_migration_gt45": ("Nợ mới chuyển nhóm quá hạn > 45 ngày", "money"),
    "dead_stock_top10": ("Top 10 tồn kho chết (giá trị)", "money"),
    "customer_churn": ("Khách hàng lớn sụt giảm/rời bỏ", "customer"),
    "revenue_concentration": ("Rủi ro tập trung doanh thu", "percent"),
    "etc_return_rate": ("Tỷ lệ hàng trả về ETC cao", "percent"),
    "zero_sales_rep": ("Số nhân sự có doanh số bằng 0", "count"),
    "kpi_sales_force_risk": ("Số nhân sự rủi ro KPI", "count"),
    "kpi_daily_pace_red": ("Số TDV có nhịp KPI ngày mức Đỏ", "count"),
    "kpi_milestone_channel": ("Mốc KPI kênh giảm so TB 5 tháng trước", "percent"),
    "kpi_milestone_tdv": ("Số TDV giảm KPI so TB 5 tháng trước", "count"),
    "data_sanity_zero": ("Dữ liệu rỗng/bất thường — đã chặn cảnh báo", "status"),
    "etl_stale": ("ETL nghi đứng (dữ liệu không mới)", "hours"),
}

def _format_highlight_date_part(part):
    """Nếu 1 mảnh suffix của alert_key là ngày/tháng (YYYY-MM-DD, YYYY-MM, hoặc "M_YYYY" — định
    dạng period dùng ở receivable_detail/check_debt_aging_migration_alert), đổi sang định dạng
    Việt Nam (DD/MM/YYYY hoặc MM/YYYY) — các mảnh khác (mã kênh OTC/ETC, SKU...) giữ nguyên."""
    for fmt_in, fmt_out in (("%Y-%m-%d", "%d/%m/%Y"), ("%Y-%m", "%m/%Y")):
        try:
            return datetime.strptime(part, fmt_in).strftime(fmt_out)
        except ValueError:
            continue
    if "_" in part:
        month_str, _, year_str = part.partition("_")
        if month_str.isdigit() and year_str.isdigit() and len(year_str) == 4:
            return f"{int(month_str):02d}/{year_str}"
    return part

def _is_date_like_segment(part):
    """True nếu 1 mảnh suffix của alert_key là ngày/tháng nhận dạng được (xem
    _format_highlight_date_part) — dùng để loại các mảnh NGÀY khỏi khóa gộp nhóm trong
    _get_period_highlights, để "Tỷ lệ nợ quá hạn... (OTC, 11/07)" và "...(OTC, 12/07)" được coi
    là CÙNG 1 loại cảnh báo (chỉ khác ngày) thay vì liệt kê riêng từng ngày."""
    for fmt_in in ("%Y-%m-%d", "%Y-%m"):
        try:
            datetime.strptime(part, fmt_in)
            return True
        except ValueError:
            continue
    if "_" in part:
        month_str, _, year_str = part.partition("_")
        if month_str.isdigit() and year_str.isdigit() and len(year_str) == 4:
            return True
    return False

def _highlight_group_key(alert_key):
    """Khóa gộp nhóm cho 1 alert_key — bỏ các mảnh NGÀY (xem _is_date_like_segment), giữ lại
    prefix + các mảnh khác (kênh OTC/ETC, mã SKU...). 2 alert_key cùng khóa gộp -> coi là CÙNG
    1 loại cảnh báo lặp lại theo ngày, chỉ giữ lần gần nhất (xem _get_period_highlights)."""
    if alert_key.startswith("sales_kpi_insights_report_"):
        return "sales_kpi_insights_report"
    segments = alert_key.split(":")
    prefix, parts = segments[0], segments[1:]
    kept = [p for p in parts if not _is_date_like_segment(p)]
    return ":".join([prefix] + kept)

def _format_highlight_value(value, value_type):
    try:
        if value_type == "money":
            from src.alerts import format_vietnamese_money
            return format_vietnamese_money(float(value))
        if value_type in ("ratio", "percent"):
            return f"{float(value) * 100:.1f}%"
        if value_type == "qty":
            return f"{float(value):,.0f}".replace(",", ".")
        if value_type == "count":
            return f"{int(float(value)):,}".replace(",", ".")
        if value_type == "hours":
            return f"{int(float(value))} giờ"
        if value_type == "customer":
            return f"Mã KH {value}"
        if value_type == "status":
            return {"sent": "Đã gửi", "zero": "Không phát hiện bất thường"}.get(str(value), str(value))
    except (ValueError, TypeError):
        pass
    return str(value)

def _humanize_highlight(alert_key, sent_at, value):
    """Dịch 1 dòng sent_alerts thô (alert_key/sent_at/value) sang câu chữ đọc được cho email —
    xem _HIGHLIGHT_LABELS. Trước 13/07/2026, "Điểm Nổi Bật Trong Kỳ" hiển thị thẳng alert_key kỹ
    thuật (vd "smart_debt_overdue_top5") và timestamp/số thô, không ai đọc hiểu được."""
    # sales_kpi_insights_report nối kỳ báo cáo bằng "_" (không phải ":" như các key khác)
    if alert_key.startswith("sales_kpi_insights_report_"):
        prefix = "sales_kpi_insights_report"
        parts = [alert_key[len("sales_kpi_insights_report_"):]]
    else:
        segments = alert_key.split(":")
        prefix, parts = segments[0], segments[1:]

    label, value_type = _HIGHLIGHT_LABELS.get(prefix, (prefix, "raw"))
    formatted_parts = [_format_highlight_date_part(p) for p in parts]
    suffix = f" ({', '.join(formatted_parts)})" if formatted_parts else ""

    try:
        sent_at_display = datetime.strptime(str(sent_at).split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%H:%M %d/%m/%Y")
    except ValueError:
        sent_at_display = str(sent_at)

    return {
        "label": label + suffix,
        "sent_at_display": sent_at_display,
        "value_display": _format_highlight_value(value, value_type),
    }

_HIGHLIGHTS_MAX_ROWS = 15  # xem _get_period_highlights — trần số dòng hiển thị sau khi đã gộp nhóm

def _get_period_highlights(start_dt, end_dt):
    """"Điểm nổi bật trong kỳ": các cảnh báo nghiệp vụ đã THỰC SỰ fire trong [start_dt, end_dt),
    đọc từ data/alerts_state.db (bảng sent_alerts, ghi bởi src/alerts.py::record_alert_sent) —
    nối luồng cảnh báo thời gian thực với báo cáo định kỳ thành 1 câu chuyện liền mạch. Mỗi dòng
    được "dịch" qua _humanize_highlight() sang tên tiếng Việt + giá trị định dạng đúng kiểu.

    14/07/2026: gộp theo _highlight_group_key() (bỏ mảnh NGÀY khỏi alert_key) — trước đó các cảnh
    báo lặp lại theo ngày (vd "Tỷ lệ nợ quá hạn... (OTC)" tự bắn mỗi sáng) liệt kê riêng TỪNG NGÀY
    trong kỳ báo cáo Monthly, có thể ra 40-50 dòng cho 1 kỳ — chỉ giữ lần gần nhất mỗi nhóm, rồi
    giới hạn tối đa _HIGHLIGHTS_MAX_ROWS dòng (ưu tiên mới nhất, đã ORDER BY last_sent_at DESC)."""
    if not os.path.exists(STATE_DB_PATH):
        return []
    try:
        conn = sqlite3.connect(STATE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT alert_key, last_sent_at, last_value FROM sent_alerts "
            "WHERE last_sent_at >= ? AND last_sent_at < ? ORDER BY last_sent_at DESC",
            (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"))
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"[DIGEST] Lỗi đọc điểm nổi bật từ alerts_state.db: {e}")
        return []

    seen_groups = set()
    deduped = []
    for r in rows:
        group_key = _highlight_group_key(r[0])
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        deduped.append(r)
        if len(deduped) >= _HIGHLIGHTS_MAX_ROWS:
            break
    return [_humanize_highlight(r[0], r[1], r[2]) for r in deduped]


def _period_has_critical(start_dt, end_dt):
    """
    True nếu có >=1 alert CRITICAL THỰC SỰ được gửi trong [start_dt, end_dt) — đọc bảng
    alert_severity_log (ghi bởi src/notifier.py::send_alert_to_all_channels, LỊCH SỬ đầy đủ theo
    thời gian, khác bảng sent_alerts chỉ giữ trạng thái mới nhất). Dùng để gắn cờ Outlook
    Importance:High cho email digest Weekly/Monthly (xem main.py::_send_periodic_email_report).
    """
    if not os.path.exists(STATE_DB_PATH):
        return False
    try:
        conn = sqlite3.connect(STATE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM alert_severity_log WHERE severity = 'CRITICAL' "
            "AND sent_at >= ? AND sent_at < ?",
            (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"))
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[DIGEST] Lỗi đọc alert_severity_log (bảng có thể chưa tồn tại nếu chưa có alert nào gửi): {e}")
        return False


def _month_tuple(dt):
    return (dt.year, dt.month)


def _prev_month_tuple(dt):
    return (dt.year - 1, 12) if dt.month == 1 else (dt.year, dt.month - 1)


def get_digest_metrics(start_dt, end_dt, period_label, granularity=None, region=None, channel=None):
    """
    Tổng hợp dữ liệu THẬT (Supabase: brv_*/brvsx_*/receivable_detail/inventory/kpi_summary)
    trong khoảng [start_dt, end_dt) phục vụ digest định kỳ (dùng chung cho daily/weekly/monthly).

    granularity: None (Daily — giữ nguyên hành vi/cấu trúc cũ) hoặc "weekly"/"monthly" (bật thêm
    trend theo ngày/tuần, breakdown vùng, tóm tắt KPI, điểm nổi bật — xem Phần 2 kế hoạch báo cáo).
    region/channel: lọc phạm vi báo cáo theo audience (Phần 3 — phân quyền gửi theo cấp quản lý).
      - region: None hoặc 'bac'/'nam'/'trung'. channel: None hoặc 'OTC'/'ETC'.
      - Áp dụng cho doanh thu/top khách hàng/tóm tắt KPI. Công nợ và tồn kho GIỮ NGUYÊN không lọc
        (tồn kho không có chiều vùng/kênh; công nợ theo vùng cần join thêm qua sales_channon vẫn
        chưa xác nhận định dạng gốc — để nguyên toàn công ty, tránh suy đoán sai).
    """
    from sqlalchemy import text
    from src.database import _get_fast_cloud_engine

    # 13/07/2026: kẹp end_dt tại hết hôm nay ngay từ đầu hàm. Từ khi get_weekly/monthly_digest_metrics
    # dùng kỳ ĐANG CHẠY (chưa hết tuần/tháng), end_dt truyền vào có thể là ngày TƯƠNG LAI — phát
    # hiện thực tế: 1 chứng từ ETC ngày 18/07/2026 (tương lai) đã có sẵn trong hệ thống khiến "Tổng
    # Doanh Thu" cao hơn hẳn tổng bảng "Xu Hướng Doanh Thu Trong Kỳ" (đã kẹp ở _revenue_trend) — 2
    # con số trong CÙNG 1 báo cáo lệch nhau. Kẹp 1 lần ở đây áp dụng nhất quán cho MỌI phần dùng
    # end_dt bên dưới (doanh thu, top khách hàng, breakdown vùng, kỳ so sánh liền trước).
    today_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_dt = min(end_dt, today_end)

    config = load_config()
    dead_months = float(config['thresholds']['business'].get('dead_stock_months', 12.0))
    dead_min_value = float(config['thresholds']['business'].get('dead_stock_min_value', 50000000))
    region_markers = _region_markers(region)

    # 1. Doanh thu kỳ này + kỳ liền trước (cùng độ dài) để so sánh tăng/giảm — theo đúng phạm vi
    #    region/channel của audience đang xem báo cáo. Tự failover Supabase -> Bravo nội bộ (xem
    #    _period_revenue) nên KHÔNG cần mở connection ở đây nữa.
    otc_rev, etc_rev, otc_invoice_count, etc_invoice_count = _period_revenue(start_dt, end_dt, region=region)
    period_len = end_dt - start_dt
    prev_start, prev_end = start_dt - period_len, start_dt
    prev_otc_rev, prev_etc_rev, _, _ = _period_revenue(prev_start, prev_end, region=region)
    if channel == "OTC":
        etc_rev = prev_etc_rev = 0.0
        etc_invoice_count = 0
    elif channel == "ETC":
        otc_rev = prev_otc_rev = 0.0
        otc_invoice_count = 0
    invoice_count = otc_invoice_count + etc_invoice_count
    total_rev = otc_rev + etc_rev
    prev_total_rev = prev_otc_rev + prev_etc_rev
    change_pct = ((total_rev - prev_total_rev) / prev_total_rev) if prev_total_rev > 0 else None

    # 2. Top 5 khách hàng theo doanh thu — tách riêng OTC/ETC vì 2 kênh có KHÔNG GIAN MÃ khách
    #    hàng khác nhau (dms_khachhang vs dmssx_khachhang), không gộp chung được. Cũng tự failover
    #    nội bộ qua _top_customers().
    top_otc, top_etc = [], []
    if channel != "ETC":
        top_otc = _top_customers(start_dt, end_dt, "OTC", region_markers)
    if channel != "OTC":
        top_etc = _top_customers(start_dt, end_dt, "ETC", region_markers)

    # 3. Công nợ — ưu tiên TỨC THỜI từ Bravo (get_bravo_receivables_snapshot, 10/07/2026), dự
    #    phòng receivable_detail (Supabase) nếu Bravo lỗi. Bravo không có khái niệm "kỳ" (luôn
    #    tức thời) nên bỏ hẳn bước kiểm tra độ mới của kỳ khi dùng Bravo — chỉ áp dụng khi rơi
    #    xuống nhánh dự phòng Supabase.
    receivables = None
    try:
        from src.alerts import get_bravo_receivables_snapshot
        snap = get_bravo_receivables_snapshot()
        
        otc_snap = [r for r in snap if r.sales_channel == 'OTC']
        etc_snap = [r for r in snap if r.sales_channel == 'ETC']
        
        total_overdue = sum(
            float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            for r in snap)
        balance_end = sum(float(r.balance_end or 0) for r in snap)
        
        otc_overdue = sum(
            float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            for r in otc_snap)
        otc_balance = sum(float(r.balance_end or 0) for r in otc_snap)
        
        etc_overdue = sum(
            float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            for r in etc_snap)
        etc_balance = sum(float(r.balance_end or 0) for r in etc_snap)
        
        receivables = {
            "total_overdue": round(total_overdue, 2),
            "balance_end": round(balance_end, 2),
            "otc_overdue": round(otc_overdue, 2),
            "otc_balance": round(otc_balance, 2),
            "etc_overdue": round(etc_overdue, 2),
            "etc_balance": round(etc_balance, 2),
            "period": f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})",
        }
    except Exception as e:
        print(f"[DIGEST] Bravo lỗi ({e}) — dự phòng Supabase receivable_detail.")
        try:
            fast_engine = _get_fast_cloud_engine()
            if fast_engine is not None:
                with fast_engine.connect() as conn:
                    periods = [r[0] for r in conn.execute(text("SELECT DISTINCT period FROM receivable_detail")).fetchall() if r[0]]
                    if periods:
                        from ai_agent.chatbot import _latest_period_key
                        latest_period = max(periods, key=_latest_period_key)
                        month_str, year_str = latest_period.split('_')
                        latest_tuple = (int(year_str), int(month_str))
                        report_last_day = end_dt - timedelta(days=1)
                        if latest_tuple in (_month_tuple(report_last_day), _prev_month_tuple(report_last_day)):
                            # Total
                            deb_row = conn.execute(text(
                                'SELECT COALESCE(SUM(total_overdue),0), COALESCE(SUM(balance_end),0) '
                                'FROM receivable_detail WHERE period = :p'
                            ), {"p": latest_period}).fetchone()
                            # OTC
                            otc_row = conn.execute(text(
                                "SELECT COALESCE(SUM(total_overdue),0), COALESCE(SUM(balance_end),0) "
                                "FROM receivable_detail WHERE period = :p AND (sales_channel = 'OTC' OR sales_channel = '0')"
                            ), {"p": latest_period}).fetchone()
                            # ETC
                            etc_row = conn.execute(text(
                                "SELECT COALESCE(SUM(total_overdue),0), COALESCE(SUM(balance_end),0) "
                                "FROM receivable_detail WHERE period = :p AND sales_channel = 'ETC'"
                            ), {"p": latest_period}).fetchone()
                            
                            receivables = {
                                "total_overdue": round(float(deb_row[0]), 2),
                                "balance_end": round(float(deb_row[1]), 2),
                                "otc_overdue": round(float(otc_row[0]), 2),
                                "otc_balance": round(float(otc_row[1]), 2),
                                "etc_overdue": round(float(etc_row[0]), 2),
                                "etc_balance": round(float(etc_row[1]), 2),
                                "period": latest_period,
                            }
                        # else: dữ liệu công nợ quá cũ so với kỳ báo cáo -> để None, KHÔNG hiển thị
        except Exception as e2:
            print(f"[DIGEST] Lỗi cả 2 nguồn khi lấy công nợ: {e2}")

    # 4. Tồn kho — VẪN Supabase (chưa verify công thức Bravo BRV_TheKho/TonKhoDK khớp số liệu thật
    #    — xem docstring check_dead_stock_alert trong src/alerts.py, cùng lý do). KPI đội — ưu
    #    tiên Bravo (TDV/QLV, get_bravo_kpi_tdv_snapshot), dự phòng kpi_summary (Supabase, đủ mọi
    #    chức danh) nếu Bravo lỗi.
    dead_stock_count = near_stockout_count = 0
    dead_items = []
    kpi_summary = None
    fast_engine = _get_fast_cloud_engine()
    if fast_engine is not None:
        try:
            with fast_engine.connect() as conn:
                # Filter inventory by channel if specified
                channel_clause = ""
                if channel in ("OTC", "ETC"):
                    channel_clause = " WHERE channel = :channel"
                
                q_count = f'''
                    SELECT
                        COUNT(*) FILTER (WHERE months_to_sell >= :dead_months AND closing_value > :dead_min_value),
                        COUNT(*) FILTER (WHERE months_to_sell > 0 AND months_to_sell <= 1.0 AND closing_qty > 0)
                    FROM inventory
                    {channel_clause}
                '''
                
                q_items = f'''
                    SELECT item_code, item_name, closing_value, months_to_sell, channel
                    FROM inventory
                    WHERE months_to_sell >= :dead_months AND closing_value > :dead_min_value
                    {"AND channel = :channel" if channel in ("OTC", "ETC") else ""}
                    ORDER BY closing_value DESC LIMIT 5
                '''
                
                params = {"dead_months": dead_months, "dead_min_value": dead_min_value}
                if channel in ("OTC", "ETC"):
                    params["channel"] = channel

                inv_row = conn.execute(text(q_count), params).fetchone()
                dead_stock_count = int(inv_row[0] or 0)
                near_stockout_count = int(inv_row[1] or 0)

                dead_items = conn.execute(text(q_items), params).fetchall()
        except Exception as e:
            print(f"[DIGEST] Supabase lỗi/timeout khi lấy tồn kho (chưa có Bravo để fallback) — bỏ trống mục này: {e}")

    if granularity in ("weekly", "monthly"):
        try:
            from src.alerts import get_bravo_kpi_tdv_snapshot
            snap = get_bravo_kpi_tdv_snapshot(position_codes=('TDV', 'QLV'))
            markers = _region_markers(region)
            if markers:
                snap = [r for r in snap if r.area_code in markers]
            snap = [r for r in snap if r.month_sale_target > 0]
            if snap:
                achieved = sum(1 for r in snap if (r.month_sale_percent or 0) >= 1.0)
                total_target = sum(r.month_sale_target for r in snap)
                total_amount = sum(r.month_sale_amount for r in snap)
                team_pct = (total_amount / total_target) if total_target else None
                kpi_summary = {
                    "achieved_count": achieved, "total_count": len(snap),
                    "team_pct": round(team_pct * 100, 1) if team_pct is not None else None,
                    "total_target": round(total_target, 2), "total_amount": round(total_amount, 2),
                }
        except Exception as e:
            print(f"[DIGEST] Bravo lỗi khi lấy KPI đội ({e}) — dự phòng Supabase kpi_summary.")
            if fast_engine is not None:
                try:
                    with fast_engine.connect() as conn:
                        kpi_summary = _kpi_summary(conn, region=region)
                except Exception as e2:
                    print(f"[DIGEST] Lỗi cả 2 nguồn khi lấy KPI đội: {e2}")

    # 5. Phần mở rộng CHỈ cho weekly/monthly (không đổi hành vi/tải truy vấn của daily). Trend +
    #    region_breakdown tự failover nội bộ (xem _revenue_trend/_revenue_by_region).
    trend, region_breakdown = [], []
    if granularity in ("weekly", "monthly"):
        trend = _revenue_trend(start_dt, end_dt, granularity, region=region, channel=channel)
        if region is None:
            region_breakdown = _revenue_by_region(start_dt, end_dt, channel=channel)

    highlights = _get_period_highlights(start_dt, end_dt) if granularity in ("weekly", "monthly") else []
    has_critical = _period_has_critical(start_dt, end_dt) if granularity in ("weekly", "monthly") else False

    result = {
        "date": start_dt.strftime("%d/%m/%Y"),
        "period_range": period_label,
        "updated_at": datetime.now().strftime("%H:%M %d/%m/%Y"),
        "revenue": {
            "otc": round(otc_rev, 2),
            "etc": round(etc_rev, 2),
            "total": round(total_rev, 2),
            "invoice_count": invoice_count,
            "otc_invoice_count": otc_invoice_count,
            "etc_invoice_count": etc_invoice_count,
            "prev_total": round(prev_total_rev, 2),
            "change_pct": round(change_pct * 100, 1) if change_pct is not None else None,
            # 14/07/2026: nhãn ngày cụ thể của "kỳ trước" — "so kỳ trước" đơn thuần không rõ là so
            # với gì (kỳ trước = cùng ĐỘ DÀI ngày ngay trước start_dt, không nhất thiết là "tháng
            # trước"/"tuần trước" trọn vẹn, nhất là khi kỳ hiện tại đang chạy dở/chưa hết).
            "prev_period_label": f"{prev_start.strftime('%d/%m')}-{(prev_end - timedelta(days=1)).strftime('%d/%m/%Y')}",
        },
        "top_customers_otc": [{"code": r[0], "name": r[1], "revenue": round(float(r[2]), 2)} for r in top_otc],
        "top_customers_etc": [{"code": r[0], "name": r[1], "revenue": round(float(r[2]), 2)} for r in top_etc],
        "receivables": receivables,
        "inventory": {
            "dead_stock_count": dead_stock_count,
            "near_stockout_count": near_stockout_count,
            "dead_stock_items": [
                {"item_code": r[0], "item_name": r[1], "closing_value": round(float(r[2]), 2), "months_to_sell": round(float(r[3]), 1), "channel": r[4]}
                for r in dead_items
            ],
        },
    }
    if granularity in ("weekly", "monthly"):
        result["trend"] = trend
        result["region_breakdown"] = region_breakdown
        result["kpi_summary"] = kpi_summary
        result["highlights"] = highlights
        result["has_critical"] = has_critical
    return result

def get_daily_digest_metrics(region=None, channel=None):
    """Tổng hợp dữ liệu trong ngày phục vụ Daily Digest (Teams).
    13/07/2026: thêm region/channel (trước đó luôn None — chỉ có 1 bản toàn công ty gửi cho
    audience C-Level, 5 audience còn lại không nhận Daily Digest). Xem send_daily_digest()
    trong main.py — giờ lặp qua report_recipients, gọi hàm này riêng cho từng audience.
    region/channel: lọc phạm vi báo cáo theo audience (xem get_digest_metrics)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    return get_digest_metrics(today_start, today_end, today_start.strftime("%d/%m/%Y"), region=region, channel=channel)

def get_weekly_digest_metrics(region=None, channel=None):
    """Tổng hợp dữ liệu TUẦN ĐANG CHẠY (thứ 2 tới hiện tại) phục vụ Weekly Report (Email).
    13/07/2026: đổi từ "tuần TRƯỚC đã kết thúc trọn vẹn" sang tuần hiện tại — lịch chạy
    DNH_Weekly_Report là thứ Bảy 17:45 (scripts/register_digest_schedule.bat), nghĩa là tuần
    hiện tại (thứ 2 - hiện tại) CHƯA hết Chủ Nhật; logic cũ lùi thêm 1 tuần nữa để lấy tuần
    "đã kết thúc trọn vẹn", khiến báo cáo trễ tới gần 2 tuần so với thời điểm gửi (vd gửi 11/07
    mà báo cáo tuần 29/06-05/07). ĐÁNH ĐỔI (giống Monthly Report): thiếu dữ liệu chiều/tối thứ
    Bảy và cả ngày Chủ Nhật của tuần — chấp nhận được để đổi lấy báo cáo tươi hơn nhiều.
    region/channel: lọc phạm vi báo cáo theo audience (xem get_digest_metrics)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())  # weekday(): Thứ 2 = 0
    week_end = week_start + timedelta(days=7)  # exclusive — hết Chủ nhật tuần này (kể cả nếu chưa tới)
    label = f"Tuần {week_start.strftime('%d/%m/%Y')} - {(week_end - timedelta(days=1)).strftime('%d/%m/%Y')}"
    return get_digest_metrics(week_start, week_end, label, granularity="weekly", region=region, channel=channel)

def get_monthly_digest_metrics(region=None, channel=None):
    """Tổng hợp dữ liệu THÁNG ĐANG CHẠY (chứa ngày gọi hàm) phục vụ Monthly Report (Email).
    10/07/2026: đổi lịch DNH_Monthly_Report từ "ngày 1 tháng sau" sang "ngày cuối tháng, 17h45"
    (xem scripts/register_digest_schedule.bat) để báo cáo tháng vừa xong được gửi SỚM HƠN 1 ngày
    — ĐÁNH ĐỔI: thiếu vài giờ cuối ngày cuối tháng (17h45 → 24h), chấp nhận được theo yêu cầu.
    TRƯỚC ĐÂY hàm này tính "tháng TRƯỚC tháng chứa ngày gọi" (đúng khi lịch chạy là ngày 1 tháng
    sau) — giữ nguyên logic cũ trong khi đổi lịch chạy sẽ khiến báo cáo bị TRỄ THÊM 1 THÁNG (vd
    gửi 31/7 mà vẫn nói về tháng 6), nên phải sửa cả 2 cùng lúc, không chỉ đổi lịch schtasks.
    region/channel: lọc phạm vi báo cáo theo audience (xem get_digest_metrics)."""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_year, next_month = (month_start.year + 1, 1) if month_start.month == 12 else (month_start.year, month_start.month + 1)
    month_end = month_start.replace(year=next_year, month=next_month)  # exclusive — hết ngày cuối tháng này
    label = f"Tháng {month_start.strftime('%m/%Y')} ({month_start.strftime('%d/%m')} - {(month_end - timedelta(days=1)).strftime('%d/%m/%Y')})"
    return get_digest_metrics(month_start, month_end, label, granularity="monthly", region=region, channel=channel)

if __name__ == '__main__':
    # Chạy thử kiểm tra việc trích xuất
    erp_eng, crm_eng = get_db_engines()
    config = load_config()

    print("--- Kiêm tra dữ liệu ERP ---")
    limit = config['thresholds']['erp']['low_inventory_limit']
    lookback = config['thresholds']['erp']['failed_orders_lookback_hours']

    print(f"Sản phẩm tồn kho thấp (ngưỡng < {limit}):")
    print(get_low_inventory(erp_eng, limit))

    print(f"\nĐơn hàng lỗi gần đây (lookback {lookback}h):")
    print(get_recent_failed_orders(erp_eng, lookback))

    print("\n--- Kiểm tra dữ liệu CRM ---")
    print("Tickets Urgent chưa giải quyết:")
    print(get_unresolved_urgent_tickets(crm_eng))

    print("\n--- Báo cáo tổng hợp Daily Digest Metrics ---")
    import pprint
    pprint.pprint(get_daily_digest_metrics())
