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
    """Doanh thu OTC+ETC thuần trong [start_dt, end_dt) — loại CTKM khuyến mãi + chứng từ hủy
    (đúng quy tắc đã dùng ở check_revenue_drop_alert). region: None (không lọc) hoặc
    'bac'/'nam'/'trung' — lọc theo AreaCode qua chain CityId -> dim_tinhthanhpho.
    Trả (otc_rev, etc_rev, invoice_count).

    JOIN dms_khachhang/dmssx_khachhang LUÔN bắt buộc (kể cả khi region=None) — trước 09/07/2026
    chỉ JOIN khi có lọc vùng, khiến mã nội bộ/chuyển kho không phải khách hàng thật (vd '1001136',
    'P000001') vẫn được cộng vào tổng doanh thu. Phát hiện thực tế: '1001136'+'P000001' chiếm 72%
    "doanh thu ETC" báo cáo tuần 29/06-05/07/2026 ở lần gửi thử đầu tiên qua Bravo trước khi vá —
    cùng loại mã giả đã xác nhận và lọc ở check_customer_churn_alert/_top_customers.

    Tự failover Supabase (Postgres) -> Bravo SQL Server trực tiếp qua run_with_failover() khi
    Supabase timeout/mất kết nối — KHÔNG còn nhận `conn` từ ngoài (tự chọn nguồn/kết nối), vì 2
    nguồn cần 2 câu SQL khác dialect (Postgres vs T-SQL). Đã xác nhận thực tế trên Bravo (09/07/2026):
    DocDate là kiểu date thật (không cần cast), IsActive/IsHC/IsCancelled là bit, tên cột/bảng
    giữ nguyên y hệt Supabase (sync không đổi tên cột) — chỉ prefix schema "dbo." khác.
    """
    from sqlalchemy import text, bindparam
    from src.database import run_with_failover
    markers = _region_markers(region)
    params = {"start_dt": start_dt, "end_dt": end_dt}
    if markers:
        params["region_markers"] = tuple(markers)

    def _pg(conn):
        # JOIN dms_khachhang/dmssx_khachhang LUÔN bắt buộc (không chỉ khi lọc vùng) — đúng pattern
        # đã dùng ở _top_customers/_revenue_by_region/check_customer_churn_alert: brv_hoadonhdr
        # chứa nhiều "CustomerCode" KHÔNG phải khách hàng thật (mã nội bộ/chuyển kho '1001136', mã
        # công ty mẹ 'P000001'...) — thiếu JOIN này khiến tổng doanh thu bị thổi phồng bởi các mã
        # giả (xác nhận thực tế 09/07/2026: '1001136'+'P000001' chiếm 72% doanh thu ETC báo cáo
        # tuần 29/06-05/07 trong lần test đầu, trước khi vá).
        region_join, region_where = "", ""
        if markers:
            region_join = 'JOIN dim_tinhthanhpho rt ON k."CityId" = rt."CityId"'
            region_where = ' AND rt."AreaCode" IN :region_markers'

        otc_sql = text(f'''
            SELECT COALESCE(SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END), 0),
                   COUNT(DISTINCT h."Stt")
            FROM brv_hoadonct c
            JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
            JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
            {region_join}
            LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
              AND h."DocDate"::timestamp >= :start_dt AND h."DocDate"::timestamp < :end_dt
              {region_where}
        ''')
        if markers:
            otc_sql = otc_sql.bindparams(bindparam("region_markers", expanding=True))
        otc_row = conn.execute(otc_sql, params).fetchone()

        etc_sql = text(f'''
            SELECT COALESCE(SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END), 0),
                   COUNT(DISTINCT h."Stt")
            FROM brvsx_hoadonct c
            JOIN brvsx_hoadonhdr h ON c."Stt" = h."Stt"
            JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
            {region_join}
            LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = TRUE
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
              AND h."DocDate"::timestamp >= :start_dt AND h."DocDate"::timestamp < :end_dt
              {region_where}
        ''')
        if markers:
            etc_sql = etc_sql.bindparams(bindparam("region_markers", expanding=True))
        etc_row = conn.execute(etc_sql, params).fetchone()
        return float(otc_row[0]), float(etc_row[0]), int(otc_row[1]) + int(etc_row[1])

    def _mssql(conn):
        region_join, region_where = "", ""
        if markers:
            region_join = 'JOIN dbo.DIM_TinhThanhPho rt ON k."CityId" = rt."CityId"'
            region_where = ' AND rt."AreaCode" IN :region_markers'

        otc_sql = text(f'''
            SELECT COALESCE(SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END), 0),
                   COUNT(DISTINCT h."Stt")
            FROM dbo.BRV_HoaDonCt c
            JOIN dbo.BRV_HoaDonHdr h ON c."Stt" = h."Stt"
            JOIN dbo.DMS_KhachHang k ON h."CustomerCode" = k."Code"
            {region_join}
            LEFT JOIN dbo.BRV_TrangThaiDuyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN dbo.BRV_TrangThaiHoaDon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = 1 AND h."IsHC" = 0
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = 0)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = 0)
              AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
              {region_where}
        ''')
        if markers:
            otc_sql = otc_sql.bindparams(bindparam("region_markers", expanding=True))
        otc_row = conn.execute(otc_sql, params).fetchone()

        etc_sql = text(f'''
            SELECT COALESCE(SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END), 0),
                   COUNT(DISTINCT h."Stt")
            FROM dbo.BRVSX_HoaDonCt c
            JOIN dbo.BRVSX_HoaDonHdr h ON c."Stt" = h."Stt"
            JOIN dbo.DMSSX_KhachHang k ON h."CustomerCode" = k."Code"
            {region_join}
            LEFT JOIN dbo.BRV_TrangThaiDuyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN dbo.BRV_TrangThaiHoaDon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = 1
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = 0)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = 0)
              AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
              {region_where}
        ''')
        if markers:
            etc_sql = etc_sql.bindparams(bindparam("region_markers", expanding=True))
        etc_row = conn.execute(etc_sql, params).fetchone()
        return float(otc_row[0]), float(etc_row[0]), int(otc_row[1]) + int(etc_row[1])

    result = run_with_failover(_pg, _mssql, label="period_revenue")
    return result if result is not None else (0.0, 0.0, 0)


def _revenue_by_region(start_dt, end_dt, channel=None):
    """Breakdown doanh thu theo VÙNG (Bắc/Nam/Trung) trong [start_dt, end_dt) — chỉ gọi cho
    weekly/monthly (không tính hàng ngày, tốn thêm query join). channel=None -> cả 2 kênh.
    Tự failover Supabase -> Bravo qua run_with_failover() (xem _period_revenue)."""
    from sqlalchemy import text
    from src.database import run_with_failover

    def _pg(conn):
        parts = []
        if channel is None or channel == "OTC":
            parts.append('''
                SELECT rt."AreaCode" AS area_code,
                       SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
                FROM brv_hoadonct c
                JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
                JOIN dms_khachhang rk ON h."CustomerCode" = rk."Code"
                JOIN dim_tinhthanhpho rt ON rk."CityId" = rt."CityId"
                LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
                LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
                WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
                  AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
                  AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
                  AND h."DocDate"::timestamp >= :start_dt AND h."DocDate"::timestamp < :end_dt
                GROUP BY rt."AreaCode"
            ''')
        if channel is None or channel == "ETC":
            parts.append('''
                SELECT rt."AreaCode" AS area_code,
                       SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
                FROM brvsx_hoadonct c
                JOIN brvsx_hoadonhdr h ON c."Stt" = h."Stt"
                JOIN dmssx_khachhang rk ON h."CustomerCode" = rk."Code"
                JOIN dim_tinhthanhpho rt ON rk."CityId" = rt."CityId"
                LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
                LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
                WHERE h."IsActive" = TRUE
                  AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
                  AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
                  AND h."DocDate"::timestamp >= :start_dt AND h."DocDate"::timestamp < :end_dt
                GROUP BY rt."AreaCode"
            ''')
        if not parts:
            return []
        union_sql = text(f'''
            SELECT area_code, SUM(rev) AS rev FROM ({" UNION ALL ".join(parts)}) x
            GROUP BY area_code ORDER BY rev DESC
        ''')
        rows = conn.execute(union_sql, {"start_dt": start_dt, "end_dt": end_dt}).fetchall()
        return [{"region": _region_label(r.area_code), "revenue": round(float(r.rev or 0), 2)} for r in rows]

    def _mssql(conn):
        parts = []
        if channel is None or channel == "OTC":
            parts.append('''
                SELECT rt."AreaCode" AS area_code,
                       SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
                FROM dbo.BRV_HoaDonCt c
                JOIN dbo.BRV_HoaDonHdr h ON c."Stt" = h."Stt"
                JOIN dbo.DMS_KhachHang rk ON h."CustomerCode" = rk."Code"
                JOIN dbo.DIM_TinhThanhPho rt ON rk."CityId" = rt."CityId"
                LEFT JOIN dbo.BRV_TrangThaiDuyet d ON h."DocStatus" = d."DocStatusKey"
                LEFT JOIN dbo.BRV_TrangThaiHoaDon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
                WHERE h."IsActive" = 1 AND h."IsHC" = 0
                  AND (d."IsCancelled" IS NULL OR d."IsCancelled" = 0)
                  AND (e."IsCancelled" IS NULL OR e."IsCancelled" = 0)
                  AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
                GROUP BY rt."AreaCode"
            ''')
        if channel is None or channel == "ETC":
            parts.append('''
                SELECT rt."AreaCode" AS area_code,
                       SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
                FROM dbo.BRVSX_HoaDonCt c
                JOIN dbo.BRVSX_HoaDonHdr h ON c."Stt" = h."Stt"
                JOIN dbo.DMSSX_KhachHang rk ON h."CustomerCode" = rk."Code"
                JOIN dbo.DIM_TinhThanhPho rt ON rk."CityId" = rt."CityId"
                LEFT JOIN dbo.BRV_TrangThaiDuyet d ON h."DocStatus" = d."DocStatusKey"
                LEFT JOIN dbo.BRV_TrangThaiHoaDon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
                WHERE h."IsActive" = 1
                  AND (d."IsCancelled" IS NULL OR d."IsCancelled" = 0)
                  AND (e."IsCancelled" IS NULL OR e."IsCancelled" = 0)
                  AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
                GROUP BY rt."AreaCode"
            ''')
        if not parts:
            return []
        union_sql = text(f'''
            SELECT area_code, SUM(rev) AS rev FROM ({" UNION ALL ".join(parts)}) x
            GROUP BY area_code ORDER BY rev DESC
        ''')
        rows = conn.execute(union_sql, {"start_dt": start_dt, "end_dt": end_dt}).fetchall()
        return [{"region": _region_label(r.area_code), "revenue": round(float(r.rev or 0), 2)} for r in rows]

    try:
        result = run_with_failover(_pg, _mssql, label="revenue_by_region")
    except Exception as e:
        print(f"[DIGEST] Lỗi truy vấn breakdown vùng: {e}")
        return []
    return result if result is not None else []


def _top_customers(start_dt, end_dt, channel_label, region_markers=None):
    """Top 5 khách hàng theo doanh thu trong [start_dt, end_dt) cho 1 kênh (OTC hoặc ETC) —
    dùng cho get_digest_metrics(). Trả list row (CustomerCode, Name, rev). Tự failover
    Supabase -> Bravo qua run_with_failover() (xem _period_revenue)."""
    from sqlalchemy import text, bindparam
    from src.database import run_with_failover
    params = {"start_dt": start_dt, "end_dt": end_dt}
    if region_markers:
        params["region_markers"] = tuple(region_markers)

    def _pg(conn):
        ct, hdr, kh = ("brv_hoadonct", "brv_hoadonhdr", "dms_khachhang") if channel_label == "OTC" \
            else ("brvsx_hoadonct", "brvsx_hoadonhdr", "dmssx_khachhang")
        region_join, region_where = "", ""
        if region_markers:
            region_join = 'JOIN dim_tinhthanhpho rt ON k."CityId" = rt."CityId"'
            region_where = ' AND rt."AreaCode" IN :region_markers'
        hc_cond = 'AND h."IsHC" = FALSE ' if channel_label == "OTC" else ''
        sql = text(f'''
            SELECT h."CustomerCode", k."Name",
                   SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
            FROM {ct} c
            JOIN {hdr} h ON c."Stt" = h."Stt"
            JOIN {kh} k ON h."CustomerCode" = k."Code"
            {region_join}
            LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = TRUE {hc_cond}
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
              AND h."DocDate"::timestamp >= :start_dt AND h."DocDate"::timestamp < :end_dt
              {region_where}
            GROUP BY h."CustomerCode", k."Name"
            ORDER BY rev DESC LIMIT 5
        ''')
        if region_markers:
            sql = sql.bindparams(bindparam("region_markers", expanding=True))
        return conn.execute(sql, params).fetchall()

    def _mssql(conn):
        ct, hdr, kh = ("dbo.BRV_HoaDonCt", "dbo.BRV_HoaDonHdr", "dbo.DMS_KhachHang") if channel_label == "OTC" \
            else ("dbo.BRVSX_HoaDonCt", "dbo.BRVSX_HoaDonHdr", "dbo.DMSSX_KhachHang")
        region_join, region_where = "", ""
        if region_markers:
            region_join = 'JOIN dbo.DIM_TinhThanhPho rt ON k."CityId" = rt."CityId"'
            region_where = ' AND rt."AreaCode" IN :region_markers'
        hc_cond = 'AND h."IsHC" = 0 ' if channel_label == "OTC" else ''
        sql = text(f'''
            SELECT TOP 5 h."CustomerCode", k."Name",
                   SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
            FROM {ct} c
            JOIN {hdr} h ON c."Stt" = h."Stt"
            JOIN {kh} k ON h."CustomerCode" = k."Code"
            {region_join}
            LEFT JOIN dbo.BRV_TrangThaiDuyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN dbo.BRV_TrangThaiHoaDon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = 1 {hc_cond}
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = 0)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = 0)
              AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
              {region_where}
            GROUP BY h."CustomerCode", k."Name"
            ORDER BY rev DESC
        ''')
        if region_markers:
            sql = sql.bindparams(bindparam("region_markers", expanding=True))
        return conn.execute(sql, params).fetchall()

    result = run_with_failover(_pg, _mssql, label=f"top_customers_{channel_label}")
    return result if result is not None else []


def _revenue_trend(start_dt, end_dt, granularity, region=None, channel=None):
    """Xu hướng doanh thu trong kỳ: 'weekly' -> theo TỪNG NGÀY (7 điểm), 'monthly' -> theo TỪNG
    TUẦN (4-5 điểm). Chạy thêm N truy vấn _period_revenue nhỏ — chấp nhận được vì weekly/monthly
    chỉ chạy 1 lần/tuần hoặc 1 lần/tháng (không nằm trong luồng cảnh báo tần suất cao 5 lần/ngày)."""
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
        otc_rev, etc_rev, _ = _period_revenue(b_start, b_end, region=region)
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


def _get_period_highlights(start_dt, end_dt):
    """"Điểm nổi bật trong kỳ": các cảnh báo nghiệp vụ đã THỰC SỰ fire trong [start_dt, end_dt),
    đọc từ data/alerts_state.db (bảng sent_alerts, ghi bởi src/alerts.py::record_alert_sent) —
    nối luồng cảnh báo thời gian thực với báo cáo định kỳ thành 1 câu chuyện liền mạch."""
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
    return [{"alert_key": r[0], "sent_at": r[1], "value": r[2]} for r in rows]


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

    config = load_config()
    dead_months = float(config['thresholds']['business'].get('dead_stock_months', 12.0))
    dead_min_value = float(config['thresholds']['business'].get('dead_stock_min_value', 50000000))
    region_markers = _region_markers(region)

    # 1. Doanh thu kỳ này + kỳ liền trước (cùng độ dài) để so sánh tăng/giảm — theo đúng phạm vi
    #    region/channel của audience đang xem báo cáo. Tự failover Supabase -> Bravo nội bộ (xem
    #    _period_revenue) nên KHÔNG cần mở connection ở đây nữa.
    otc_rev, etc_rev, invoice_count = _period_revenue(start_dt, end_dt, region=region)
    period_len = end_dt - start_dt
    prev_otc_rev, prev_etc_rev, _ = _period_revenue(start_dt - period_len, start_dt, region=region)
    if channel == "OTC":
        etc_rev = prev_etc_rev = 0.0
    elif channel == "ETC":
        otc_rev = prev_otc_rev = 0.0
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
        "revenue": {
            "otc": round(otc_rev, 2),
            "etc": round(etc_rev, 2),
            "total": round(total_rev, 2),
            "invoice_count": invoice_count,
            "prev_total": round(prev_total_rev, 2),
            "change_pct": round(change_pct * 100, 1) if change_pct is not None else None,
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

def _get_today_alerts_status(start_dt, end_dt):
    """
    Lấy danh sách các alert đã từng bắn trong ngày hôm nay, và kiểm tra xem
    hiện tại trạng thái của chỉ số đó đã quay về mức an toàn chưa (Đã giải quyết).
    """
    from sqlalchemy import text
    if not os.path.exists(STATE_DB_PATH):
        return []
        
    # 1. Đọc lịch sử các alert đã gửi hôm nay
    today_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    fired_alerts = set()
    try:
        conn = sqlite3.connect(STATE_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT alert_name FROM alert_severity_log WHERE sent_at >= ?",
            (today_str,)
        )
        for r in cur.fetchall():
            fired_alerts.add(r[0])
        conn.close()
    except Exception as e:
        print(f"[DIGEST] Không đọc được alert_severity_log: {e}")
        return []
        
    if not fired_alerts:
        return []
        
    # 2. Khởi động các check để xem còn vi phạm không
    config = load_config()
    results = []
    
    # 2.1 Tỷ lệ nợ quá hạn
    overdue_alerts = [a for a in fired_alerts if "NỢ QUÁ HẠN" in a.upper() or "NỢ QUÁ HẠN LỚN" in a.upper()]
    if overdue_alerts:
        try:
            from src.alerts import get_bravo_receivables_snapshot
            snap = get_bravo_receivables_snapshot()
            limit = config['thresholds']['business']['overdue_ratio_pct']
            
            # Check OTC
            if any("OTC" in a.upper() or "NỢ QUÁ HẠN LỚN" in a.upper() for a in overdue_alerts):
                sub_snap = [r for r in snap if r.sales_channel == 'OTC']
                overdue = sum(float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0) for r in sub_snap)
                total = sum(float(r.balance_end or 0) for r in sub_snap)
                ratio = (overdue / total) if total > 0 else 0
                results.append({
                    "name": "Tỷ lệ nợ quá hạn OTC",
                    "active": ratio > limit
                })
            # Check ETC
            if any("ETC" in a.upper() or "NỢ QUÁ HẠN LỚN" in a.upper() for a in overdue_alerts):
                sub_snap = [r for r in snap if r.sales_channel == 'ETC']
                overdue = sum(float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0) for r in sub_snap)
                total = sum(float(r.balance_end or 0) for r in sub_snap)
                ratio = (overdue / total) if total > 0 else 0
                results.append({
                    "name": "Tỷ lệ nợ quá hạn ETC",
                    "active": ratio > limit
                })
        except Exception as e:
            print(f"[DIGEST] Lỗi check nợ quá hạn: {e}")
            
    # 2.2 Nguy cơ đứt hàng (cháy kho)
    if any("ĐỨT HÀNG" in a.upper() or "TỒN KHO THẤP" in a.upper() for a in fired_alerts):
        try:
            from src.database import _get_fast_cloud_engine
            fast_engine = _get_fast_cloud_engine()
            if fast_engine is not None:
                with fast_engine.connect() as conn:
                    cnt = conn.execute(text("SELECT COUNT(*) FROM inventory WHERE months_to_sell > 0.0 AND months_to_sell <= 1.0 AND closing_qty > 0")).scalar()
                results.append({
                    "name": "Nguy cơ đứt hàng",
                    "active": cnt > 0
                })
        except Exception as e:
            print(f"[DIGEST] Lỗi check đứt hàng: {e}")
            
    # 2.3 Khách nợ quá hạn vẫn lên đơn mới
    if any("ĐƠN MỚI" in a.upper() for a in fired_alerts):
        try:
            conn = sqlite3.connect(STATE_DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sent_alerts WHERE alert_key LIKE 'overdue_customer_new_orders%'")
            cnt = cur.fetchone()[0]
            conn.close()
            results.append({
                "name": "Khách quá hạn lên đơn mới",
                "active": cnt > 0
            })
        except Exception as e:
            print(f"[DIGEST] Lỗi check nợ lên đơn mới: {e}")
            
    # 2.4 Nhịp KPI TDV đỏ
    if any("KPI TDV THẤP" in a.upper() or "NHỊP KPI" in a.upper() for a in fired_alerts):
        try:
            from src.alerts import get_bravo_kpi_tdv_snapshot
            kpi_snap = get_bravo_kpi_tdv_snapshot(position_codes=('TDV',))
            limit_alert = config['thresholds']['business']['kpi_pace_red_alert_count']
            red_cnt = sum(1 for r in kpi_snap if r.month_sale_target > 0 and (r.month_sale_percent or 0) < 0.03)
            results.append({
                "name": "Nhịp KPI TDV ở mức Đỏ",
                "active": red_cnt >= limit_alert
            })
        except Exception as e:
            print(f"[DIGEST] Lỗi check kpi pace: {e}")

    # 2.5 Đơn hàng lỗi (Failed Orders)
    if any("GIAO DỊCH LỖI" in a.upper() for a in fired_alerts):
        try:
            erp_engine, _ = get_db_engines()
            if erp_engine:
                limit = config['thresholds']['erp']['failed_orders_limit']
                lookback = config['thresholds']['erp']['failed_orders_lookback_hours']
                lookback_time = datetime.now() - timedelta(hours=lookback)
                with erp_engine.connect() as conn:
                    cnt = conn.execute(text("SELECT COUNT(*) FROM orders WHERE status = 'Failed' AND order_date >= :t"), {"t": lookback_time}).scalar()
                results.append({
                    "name": "Đơn hàng lỗi (ERP)",
                    "active": cnt > limit
                })
        except Exception as e:
            print(f"[DIGEST] Lỗi check failed orders: {e}")

    # 2.6 Quá tải ticket (CRM Urgent)
    if any("QUÁ TẢI KHÁCH HÀNG" in a.upper() or "TICKET" in a.upper() for a in fired_alerts):
        try:
            _, crm_engine = get_db_engines()
            if crm_engine:
                limit = config['thresholds']['crm']['unresolved_urgent_tickets_limit']
                with crm_engine.connect() as conn:
                    cnt = conn.execute(text("SELECT COUNT(*) FROM support_tickets WHERE priority = 'Urgent' AND status = 'Open'")).scalar()
                results.append({
                    "name": "Ticket khẩn cấp chưa xử lý",
                    "active": cnt > limit
                })
        except Exception as e:
            print(f"[DIGEST] Lỗi check crm tickets: {e}")
            
    return results

def get_daily_digest_metrics():
    """Tổng hợp dữ liệu trong ngày phục vụ Daily Digest (Email)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    metrics = get_digest_metrics(today_start, today_end, today_start.strftime("%d/%m/%Y"))
    metrics["alerts_summary"] = _get_today_alerts_status(today_start, today_end)
    return metrics

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
