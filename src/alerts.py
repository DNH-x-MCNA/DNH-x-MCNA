import os
import sys
import sqlite3
from datetime import datetime, timedelta
from src.database import load_config, get_db_engines
from src.etl import get_low_inventory, get_recent_failed_orders, get_unresolved_urgent_tickets
from src.notifier import send_alert_to_all_channels
import math

# Đảm bảo terminal/log ghi nhận được tiếng Việt có dấu
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB_DIR = os.path.join(PROJECT_ROOT, 'data')
STATE_DB_PATH = os.path.join(STATE_DB_DIR, 'alerts_state.db')

def init_state_db():
    os.makedirs(STATE_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(STATE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_alerts (
            alert_key TEXT PRIMARY KEY,
            last_sent_at TIMESTAMP NOT NULL,
            last_value TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def should_send_alert(alert_key, cooldown_hours, current_value):
    """
    Kiểm tra xem có nên gửi cảnh báo hay không dựa trên thời gian cooldown
    và sự thay đổi của giá trị chỉ số.
    """
    init_state_db()
    conn = sqlite3.connect(STATE_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT last_sent_at, last_value FROM sent_alerts WHERE alert_key = ?", (alert_key,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return True # Chưa từng gửi cảnh báo này -> Gửi ngay
        
    last_sent_str, last_val_str = row
    last_sent_at = datetime.strptime(last_sent_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
    
    # Nếu đã quá thời gian cooldown -> Gửi lại để nhắc nhở
    if datetime.now() - last_sent_at > timedelta(hours=cooldown_hours):
        return True
        
    # Hoặc nếu giá trị lỗi tăng lên đáng kể (ví dụ: số đơn hàng lỗi tăng lên)
    try:
        if float(current_value) > float(last_val_str):
            return True
    except ValueError:
        if current_value != last_val_str:
            return True
            
    return False

def record_alert_sent(alert_key, current_value):
    """
    Ghi nhận trạng thái đã gửi cảnh báo để chống spam
    """
    init_state_db()
    conn = sqlite3.connect(STATE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sent_alerts (alert_key, last_sent_at, last_value)
        VALUES (?, ?, ?)
        ON CONFLICT(alert_key) DO UPDATE SET 
            last_sent_at = excluded.last_sent_at,
            last_value = excluded.last_value
    ''', (alert_key, datetime.now(), str(current_value)))
    conn.commit()
    conn.close()

def _init_debt_aging_snapshot_db():
    """
    Bảng snapshot công nợ nội bộ (SQLite, cùng file alerts_state.db) — thêm 10/07/2026 để
    check_debt_aging_migration_alert (A1: khách MỚI rơi vào nhóm nợ >45 ngày) hết phụ thuộc
    receivable_detail (Supabase, vốn có snapshot theo kỳ THÁNG sẵn) khi chuyển hẳn sang Bravo.

    Bravo (get_bravo_receivables_snapshot) chỉ có ledger SỐNG, không tự lưu lịch sử — nên PHẢI tự
    ghi lại 1 bản chụp (snapshot_date, customer_code) -> overdue_gt_45 MỖI LẦN hàm cảnh báo chạy
    (ghi đè trong cùng ngày, không nhân bản). Cần TÍCH LŨY vài tuần dữ liệu trước khi có đủ "kỳ
    trước" để so sánh — trước lúc đó hàm sẽ tự báo "chưa đủ lịch sử" thay vì báo sai/trống im lặng.
    """
    os.makedirs(STATE_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(STATE_DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS debt_aging_snapshot (
            snapshot_date TEXT NOT NULL,
            customer_code TEXT NOT NULL,
            customer_name TEXT,
            overdue_gt_45 REAL NOT NULL,
            PRIMARY KEY (snapshot_date, customer_code)
        )
    ''')
    conn.commit()
    conn.close()


def _save_debt_aging_snapshot(rows):
    """
    Ghi/ghi đè bản chụp công nợ >45 ngày HÔM NAY từ `rows` (list customer_code/customer_name/
    overdue_gt_45 — xem get_bravo_receivables_snapshot, đã gộp OTC+ETC theo khách hàng ở nơi gọi).
    Idempotent trong ngày — gọi nhiều lần/ngày (5 lần sync) chỉ ghi đè, không nhân bản dòng.
    """
    _init_debt_aging_snapshot_db()
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(STATE_DB_PATH)
    conn.executemany('''
        INSERT INTO debt_aging_snapshot (snapshot_date, customer_code, customer_name, overdue_gt_45)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(snapshot_date, customer_code) DO UPDATE SET
            customer_name = excluded.customer_name,
            overdue_gt_45 = excluded.overdue_gt_45
    ''', [(today, code, name, amt) for code, name, amt in rows])
    conn.commit()
    conn.close()


def _get_debt_aging_snapshot(snapshot_date):
    """Trả {customer_code: (customer_name, overdue_gt_45)} cho đúng snapshot_date ('YYYY-MM-DD')."""
    _init_debt_aging_snapshot_db()
    conn = sqlite3.connect(STATE_DB_PATH)
    cur = conn.execute(
        'SELECT customer_code, customer_name, overdue_gt_45 FROM debt_aging_snapshot WHERE snapshot_date = ?',
        (snapshot_date,))
    result = {code: (name, amt) for code, name, amt in cur.fetchall()}
    conn.close()
    return result


def _find_prev_month_snapshot_date(today_str):
    """Ngày snapshot GẦN NHẤT thuộc tháng liền trước today_str ('YYYY-MM-DD') — None nếu chưa có."""
    _init_debt_aging_snapshot_db()
    today = datetime.strptime(today_str, "%Y-%m-%d")
    prev_year, prev_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    prefix = f"{prev_year:04d}-{prev_month:02d}-"
    conn = sqlite3.connect(STATE_DB_PATH)
    cur = conn.execute(
        "SELECT MAX(snapshot_date) FROM debt_aging_snapshot WHERE snapshot_date LIKE ?",
        (prefix + '%',))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def clear_alert_state(alert_key):
    """
    Xóa trạng thái cảnh báo khi chỉ số đã trở lại bình thường (để cảnh báo lại ngay lập tức nếu lỗi tái diễn)
    """
    init_state_db()
    conn = sqlite3.connect(STATE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sent_alerts WHERE alert_key = ?", (alert_key,))
    conn.commit()
    conn.close()

def run_alert_checks(erp_engine, crm_engine):
    """
    Hàm kiểm tra toàn bộ các ngưỡng cảnh báo và thực hiện gửi thông báo đa kênh
    """
    config = load_config()
    
    # 1. KIỂM TRA TỒN KHO THẤP (ERP)
    low_inv_limit = config['thresholds']['erp']['low_inventory_limit']
    df_low_inv = get_low_inventory(erp_engine, low_inv_limit)
    
    if not df_low_inv.empty:
        rows_to_alert = []
        alert_keys_to_record = []
        for idx, row in df_low_inv.iterrows():
            sku = row['sku']
            item_name = row['item_name']
            qty = row['quantity']
            
            alert_key = f"low_inventory:{sku}"
            # Cooldown 4 tiếng đối với cảnh báo tồn kho của từng sản phẩm
            if should_send_alert(alert_key, cooldown_hours=4, current_value=qty):
                rows_to_alert.append([sku, item_name, str(qty), str(row['updated_at'])])
                alert_keys_to_record.append((alert_key, qty))
                
        if rows_to_alert:
            if send_alert_to_all_channels(
                alert_name="CANH BAO TON KHO THAP",
                severity="WARNING",
                summary=f"Phat hien {len(rows_to_alert)} san pham co ton kho thap duoi nguong cho phep (Nguong canh bao: < {low_inv_limit}).",
                table_headers=["Ma SKU", "Ten San Pham", "Ton Kho Hien Tai", "Thoi Gian Cap Nhat"],
                table_rows=rows_to_alert,
                channels=("teams",)
            ):
                for alert_key, qty in alert_keys_to_record:
                    record_alert_sent(alert_key, qty)

    # 2. KIỂM TRA GIAO DỊCH LỖI (ERP)
    failed_limit = config['thresholds']['erp']['failed_orders_limit']
    lookback = config['thresholds']['erp']['failed_orders_lookback_hours']
    df_failed = get_recent_failed_orders(erp_engine, lookback)
    failed_count = len(df_failed)
    
    alert_key_failed = "failed_orders_peak"
    if failed_count > failed_limit:
        # Cooldown 1 tiếng
        if should_send_alert(alert_key_failed, cooldown_hours=1, current_value=failed_count):
            rows = []
            for idx, row in df_failed.iterrows():
                rows.append([str(row['id']), str(row['customer_id']), f"${row['amount']}", str(row['order_date'])])
                
            if send_alert_to_all_channels(
                alert_name="CANH BAO GIAO DICH LOI VUOT NGUONG",
                severity="CRITICAL",
                summary=f"He thong phat hien so luong don hang loi tang dot bien: {failed_count} don hang that bai trong {lookback} gio qua (Nguong cho phep: <= {failed_limit}).",
                table_headers=["ID Don", "Ma Khach Hang", "Gia Tri", "Thoi Gian Giao Dich"],
                table_rows=rows,
                channels=("teams",)
            ):
                record_alert_sent(alert_key_failed, failed_count)
    else:
        clear_alert_state(alert_key_failed)

    # 3. KIỂM TRA QUÁ TẢI TICKET URGENT (CRM)
    crm_limit = config['thresholds']['crm']['unresolved_urgent_tickets_limit']
    df_tickets = get_unresolved_urgent_tickets(crm_engine)
    urgent_count = len(df_tickets)
    
    alert_key_crm = "crm_urgent_overload"
    if urgent_count > crm_limit:
        # Cooldown 1 tiếng
        if should_send_alert(alert_key_crm, cooldown_hours=1, current_value=urgent_count):
            rows = []
            for idx, row in df_tickets.iterrows():
                rows.append([str(row['id']), str(row['customer_id']), row['priority'], str(row['created_at'])])
                
            if send_alert_to_all_channels(
                alert_name="CANH BAO QUA TAI KHACH HANG (CRM)",
                severity="CRITICAL",
                summary=f"So luong yeu cau ho tro khan cap (Urgent) chua giai quyet dang vuot nguong: {urgent_count} ca (Nguong cho phep: <= {crm_limit}).",
                table_headers=["ID Ca", "Ma Khach Hang", "Do Uu Tien", "Thoi Gian Yeu Cau"],
                table_rows=rows,
                channels=("teams",)
            ):
                record_alert_sent(alert_key_crm, urgent_count)
    else:
        clear_alert_state(alert_key_crm)

def format_vietnamese_money(amount):
    if amount is None:
        return "0 đ"
    if amount >= 1e9:
        return f"{amount/1e9:,.2f} tỷ đ".replace('.', '#').replace(',', '.').replace('#', ',')
    elif amount >= 1e6:
        return f"{amount/1e6:,.1f} triệu đ".replace('.', '#').replace(',', '.').replace('#', ',')
    else:
        return f"{amount:,.0f} đ".replace('.', '#').replace(',', '.').replace('#', ',')

def format_months_to_sell(months):
    if months is None or months <= 0:
        return "Đã hết hàng hoặc không có giao dịch"
    days = round(months * 30)
    if days <= 7:
        return f"Cực kỳ nguy cấp (chỉ còn {days} ngày bán)"
    elif days <= 15:
        return f"Nguy cấp (còn {days} ngày bán)"
    else:
        return f"Còn {days} ngày bán ({months:.1f} thg)"

def estimate_overdue_days_str(period_str, overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45):
    """
    Ước lượng số ngày quá hạn từ kỳ báo cáo (period) + nhóm tuổi nợ (aging bucket).
    receivable_detail trên Supabase là bảng tổng hợp nợ theo kỳ, không có cột trạng thái từng
    hóa đơn để tra ngày quá hạn chính xác tuyệt đối — đây là ước lượng theo bucket, không phải
    số ngày thực đo từ hóa đơn gốc.

    14/07/2026: hằng số mốc ngày đổi theo mốc mới (1-30/31-60/61-90/>90, xem
    _BRAVO_RECEIVABLES_SQL). LƯU Ý: dữ liệu THẬT trong receivable_detail (Supabase) được import
    1 lần từ trước khi đổi mốc — các cột overdue_1_15/15_30/30_45/gt_45 của bảng đó vẫn là SỐ đã
    tính theo mốc CŨ (1-15/15-30/30-45/>45), chỉ TÊN CỘT/hàm này đổi theo mốc mới cho nhất quán
    với nhánh Bravo. Nhánh dự phòng này hiếm khi chạy (chỉ khi Bravo lỗi) — chấp nhận sai số nhỏ
    cho tới khi có nhu cầu import lại receivable_detail theo đúng mốc mới.
    """
    try:
        parts = period_str.split('_')
        month, year = int(parts[0]), int(parts[1])

        import calendar
        last_day = calendar.monthrange(year, month)[1]
        report_date = datetime(year, month, last_day)

        today = datetime.now()
        days_since_report = max(0, (today - report_date).days)

        if overdue_gt_45 and overdue_gt_45 > 0:
            return f"Ít nhất {90 + days_since_report} ngày"
        elif overdue_30_45 and overdue_30_45 > 0:
            return f"Từ {61 + days_since_report} đến {90 + days_since_report} ngày"
        elif overdue_15_30 and overdue_15_30 > 0:
            return f"Từ {31 + days_since_report} đến {60 + days_since_report} ngày"
        elif overdue_1_15 and overdue_1_15 > 0:
            return f"Từ {1 + days_since_report} đến {30 + days_since_report} ngày"
    except Exception:
        pass

    return "Trên 90 ngày"


def normalize_channel_label(raw_channel):
    """
    Chuẩn hoá giá trị kênh thô từ DB (vd receivable_detail.sales_channel) về nhãn hiển thị
    chuẩn "OTC"/"ETC". Chưa xác nhận 100% định dạng gốc DNH lưu trong cột này nên nhận diện
    theo từ khoá, KHÔNG suy đoán mù nếu không khớp — trả nguyên giá trị gốc để không hiển thị
    sai mà không ai biết (dễ phát hiện qua log/card thay vì âm thầm gắn nhãn sai).
    """
    if not raw_channel:
        return "Không rõ"
    val = str(raw_channel).strip().upper()
    if "OTC" in val:
        return "OTC"
    if "ETC" in val:
        return "ETC"
    return str(raw_channel)


def normalize_region_label(area_code):
    """
    Map area_code thô (vd 'MB', 'MB2', 'MN', 'MT') sang tên miền tiếng Việt — dùng lại đúng bảng
    ánh xạ đã kiểm chứng trong DNHChatbot (_REGION_SQL_MARKERS/_REGION_NAMES_VI), không định
    nghĩa lại quy ước mã miền ở 2 nơi khác nhau trong codebase.
    """
    if not area_code:
        return "Không rõ"
    from ai_agent.chatbot import DNHChatbot
    val = str(area_code).strip().upper()
    for region_key, markers in DNHChatbot._REGION_SQL_MARKERS.items():
        if val in markers:
            return DNHChatbot._REGION_NAMES_VI[region_key]
    return str(area_code)


def get_customer_regions_by_code(customer_codes, channel_label):
    """
    Tra map {customer_code: tên miền} qua chain CityId -> dim_tinhthanhpho.AreaCode đã xác minh
    (docs/dev_supabase_schema.sql): khách OTC tra qua dms_khachhang, khách ETC qua dmssx_khachhang.
    Dùng 1 câu truy vấn IN theo lô (không query từng khách hàng riêng lẻ) để đỡ tải Supabase.
    Trả dict rỗng nếu lỗi hoặc danh sách mã KH rỗng — gọi nơi dùng phải tự fallback (vd "Không rõ").
    Tự failover Supabase -> Bravo qua run_with_failover() (xem src/etl.py::_period_revenue).
    """
    if not customer_codes:
        return {}
    from sqlalchemy import text, bindparam
    from src.database import run_with_failover

    def _pg(conn):
        table = "dms_khachhang" if channel_label == "OTC" else "dmssx_khachhang"
        sql = text(f'''
            SELECT k."Code" AS cc, t."AreaCode" AS area_code
            FROM {table} k
            LEFT JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
            WHERE k."Code" IN :codes
        ''').bindparams(bindparam("codes", expanding=True))
        return conn.execute(sql, {"codes": tuple(customer_codes)}).fetchall()

    def _mssql(conn):
        table = "dbo.DMS_KhachHang" if channel_label == "OTC" else "dbo.DMSSX_KhachHang"
        sql = text(f'''
            SELECT k."Code" AS cc, t."AreaCode" AS area_code
            FROM {table} k
            LEFT JOIN dbo.DIM_TinhThanhPho t ON k."CityId" = t."CityId"
            WHERE k."Code" IN :codes
        ''').bindparams(bindparam("codes", expanding=True))
        return conn.execute(sql, {"codes": tuple(customer_codes)}).fetchall()

    try:
        rows = run_with_failover(_pg, _mssql, label="customer_regions")
    except Exception as e:
        print(f"[ALERTS][region_lookup] Lỗi tra vùng theo CityId ({channel_label}): {e}")
        return {}
    if not rows:
        return {}
    return {r.cc: normalize_region_label(r.area_code) for r in rows}


_BRAVO_RECEIVABLES_SQL = """
WITH Receivables AS (
    SELECT k.[Code] AS customer_code, k.[Name] AS customer_name, N'OTC' AS sales_channel,
           rt.[AreaCode] AS area_code,
           (h.[TotalAmount] - h.[PaidAmount]) AS amount,
           DATEDIFF(day, DATEADD(day, ISNULL(h.[DueDate], 0), h.[DocDate]), GETDATE()) AS overdue_days
    FROM [BRV_HTTDuDK] h
    JOIN [BRV_KhachHang] k ON h.[CustomerId] = k.[Id]
    LEFT JOIN [DMS_KhachHang] d ON k.[DMSId] = d.[Id]
    LEFT JOIN [DIM_TinhThanhPho] rt ON d.[CityId] = rt.[CityId]
    WHERE h.[Account] LIKE '131%' AND (h.[TotalAmount] - h.[PaidAmount]) > 0
      AND k.[IsCustomer] = 1 AND k.[Code] <> 'NCC100122'
    UNION ALL
    SELECT k.[Code], k.[Name], N'ETC',
           rt.[AreaCode],
           (h.[TotalAmount] - h.[PaidAmount]),
           DATEDIFF(day, DATEADD(day, ISNULL(h.[DueDate], 0), h.[DocDate]), GETDATE())
    FROM [BRVSX_HTTDuDK] h
    JOIN [BRVSX_KhachHang] k ON h.[CustomerId] = k.[Id]
    LEFT JOIN [DMSSX_KhachHang] d ON k.[DMSId] = d.[Id]
    LEFT JOIN [DIM_TinhThanhPho] rt ON d.[CityId] = rt.[CityId]
    WHERE h.[Account] LIKE '131%' AND (h.[TotalAmount] - h.[PaidAmount]) > 0
      AND k.[IsCustomer] = 1 AND k.[Code] <> 'NCC100122'
)
SELECT customer_code, customer_name, sales_channel, area_code,
    SUM(amount) AS balance_end,
    -- 14/07/2026: đổi mốc tuổi nợ sang 1-30/31-60/61-90/>90 ngày (chuẩn AR aging phổ biến,
    -- phù hợp hơn mốc 15 ngày cũ với quy mô DNH — xem docstring get_bravo_receivables_snapshot).
    -- GIỮ NGUYÊN tên cột overdue_1_15/15_30/30_45/gt_45 (không đổi tên) để tránh phải migrate
    -- schema debt_aging_snapshot (SQLite) + receivable_detail (Supabase) — tên cột giờ CHỈ LÀ
    -- NHÃN, không còn khớp nghĩa đen với số ngày; đây là đề xuất theo thông lệ chung, CHƯA được
    -- DNH xác nhận chính thức (xem docs/Cau_hoi_can_DNH_chot_truoc_hop_16-07.md).
    SUM(CASE WHEN overdue_days BETWEEN 1 AND 30 THEN amount ELSE 0 END) AS overdue_1_15,
    SUM(CASE WHEN overdue_days BETWEEN 31 AND 60 THEN amount ELSE 0 END) AS overdue_15_30,
    SUM(CASE WHEN overdue_days BETWEEN 61 AND 90 THEN amount ELSE 0 END) AS overdue_30_45,
    SUM(CASE WHEN overdue_days > 90 THEN amount ELSE 0 END) AS overdue_gt_45
FROM Receivables
GROUP BY customer_code, customer_name, sales_channel, area_code
"""


def get_bravo_receivables_snapshot():
    """
    Snapshot công nợ THEO KHÁCH HÀNG tính TRỰC TIẾP, TỨC THỜI từ Bravo (BRV_HTTDuDK/BRVSX_HTTDuDK)
    — dùng chung công thức đã kiểm chứng bên chatbot (TotalAmount-PaidAmount, Account LIKE '131%',
    IsCustomer=1, loại NCC100122, DueDate = DocDate + số ngày công nợ).

    LƯU Ý QUAN TRỌNG: đây là công thức TẠM THỜI, ngày cơ sở tính tuổi nợ CHƯA được DNH xác nhận
    chính thức (xem config/config.yaml::debt_aging, đã từng gây tranh chấp hợp đồng trước đây) —
    giống hệt mức độ rủi ro banner cảnh báo bên chatbot, nhưng card Teams không có chỗ hiển thị
    banner nên KHÔNG được coi là số liệu chính thức khi trình bày với khách hàng/đối tác.

    KHÔNG có khái niệm "kỳ" (period) như receivable_detail trên Supabase — đây luôn là số liệu
    TỨC THỜI tính đến thời điểm gọi hàm, KHÔNG dùng được cho các so sánh period-over-period (vd
    check_debt_aging_migration_alert cần so 2 kỳ trước/sau — hàm đó vẫn giữ đọc receivable_detail
    vì Bravo không có cơ chế snapshot theo kỳ).

    Trả về list các object có field: customer_code, customer_name, sales_channel, area_code,
    balance_end, overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45 (Decimal). area_code
    (14/07/2026, mới thêm) join qua BRV_KhachHang/BRVSX_KhachHang.DMSId -> DMS_KhachHang/
    DMSSX_KhachHang.Id -> CityId -> DIM_TinhThanhPho — xác nhận thực tế join khớp 99,6% khách OTC
    và 95,9% khách ETC (số ít không khớp -> area_code NULL, coi là "Không rõ" khi hiển thị). Raise
    exception nếu Bravo không truy cập được — người gọi tự bắt để fallback sang receivable_detail
    (Supabase).
    """
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    with engine.connect() as conn:
        return conn.execute(text(_BRAVO_RECEIVABLES_SQL)).fetchall()


_BRAVO_OVERDUE_GT45_SQL = """
WITH Receivables AS (
    SELECT k.[Code] AS customer_code, k.[Name] AS customer_name,
           (h.[TotalAmount] - h.[PaidAmount]) AS amount,
           DATEDIFF(day, DATEADD(day, ISNULL(h.[DueDate], 0), h.[DocDate]), GETDATE()) AS overdue_days
    FROM [BRV_HTTDuDK] h
    JOIN [BRV_KhachHang] k ON h.[CustomerId] = k.[Id]
    WHERE h.[Account] LIKE '131%' AND (h.[TotalAmount] - h.[PaidAmount]) > 0
      AND k.[IsCustomer] = 1 AND k.[Code] <> 'NCC100122'
    UNION ALL
    SELECT k.[Code], k.[Name],
           (h.[TotalAmount] - h.[PaidAmount]),
           DATEDIFF(day, DATEADD(day, ISNULL(h.[DueDate], 0), h.[DocDate]), GETDATE())
    FROM [BRVSX_HTTDuDK] h
    JOIN [BRVSX_KhachHang] k ON h.[CustomerId] = k.[Id]
    WHERE h.[Account] LIKE '131%' AND (h.[TotalAmount] - h.[PaidAmount]) > 0
      AND k.[IsCustomer] = 1 AND k.[Code] <> 'NCC100122'
)
SELECT customer_code, customer_name,
    SUM(CASE WHEN overdue_days > 45 THEN amount ELSE 0 END) AS overdue_gt_45
FROM Receivables
GROUP BY customer_code, customer_name
"""


def _bravo_overdue_gt45_by_customer():
    """A1 (check_debt_aging_migration_alert): nợ >45 ngày theo khách hàng (OTC+ETC gộp) — TÁCH
    RIÊNG khỏi get_bravo_receivables_snapshot()/_BRAVO_RECEIVABLES_SQL (14/07/2026). Mốc >45 ngày
    là 1 trong 4 trigger đã CHỐT THEO HỢP ĐỒNG (xem skill dnh-email-alert-builder) — không phụ
    thuộc/không tự đổi theo mốc hiển thị chung của bảng aging (đã đổi sang 1-30/31-60/61-90/>90
    ngày cùng ngày, theo đề xuất thông lệ chung, chờ DNH xác nhận riêng)."""
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    with engine.connect() as conn:
        return conn.execute(text(_BRAVO_OVERDUE_GT45_SQL)).fetchall()


def get_bravo_kpi_tdv_snapshot(position_codes=('TDV',)):
    """
    Snapshot KPI TỨC THỜI từ Bravo (FACT_TongHopKhachHang + DIM_NhanVien) — tái dùng đúng công
    thức đã kiểm chứng bên chatbot (ai_agent/chatbot.py::kpi_tdv_instruction nhánh bravo,
    10/07/2026): MAX(SaveDate) làm mốc kỳ mới nhất (KHÔNG hardcode tháng), loại IsDuplicate,
    SELECT DISTINCT target trước khi so — tránh cộng trùng khi 1 NV lặp nhiều dòng theo khách hàng.

    CHỈ áp dụng cho TDV/QLV — 'kpi_summary' (TP/PP/TBP/CS/CTV/TK) KHÔNG tồn tại trên Bravo, các vị
    trí đó BẮT BUỘC vẫn đọc Supabase (xem run_sales_kpi_insights_alert, không đổi).

    Trả list object có field: employee_code, employee_name, area_code, month_sale_target,
    month_sale_amount, month_sale_percent (0..1, None nếu target<=0). Raise exception nếu Bravo
    không truy cập được — người gọi tự bắt để fallback sang kpi_summary (Supabase).
    """
    from sqlalchemy import text
    import types
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    placeholders = ",".join(f"'{p}'" for p in position_codes)
    sql = text(f'''
        WITH tdv_actual AS (
            SELECT [EmployeeCode], SUM([Amount_Cus]) AS TotalActual
            FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] = (SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang])
            GROUP BY [EmployeeCode]
        ),
        tdv_target AS (
            SELECT DISTINCT [EmployeeCode], [AreaCode], [MonthSaleTarget]
            FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] = (SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang])
        )
        SELECT n.[EmployeeCode] AS employee_code, n.[Name] AS employee_name, t.[AreaCode] AS area_code,
               n.[PositionCode] AS position_code,
               t.[MonthSaleTarget] AS month_sale_target, ISNULL(a.TotalActual, 0) AS month_sale_amount
        FROM tdv_target t
        JOIN [DIM_NhanVien] n ON t.[EmployeeCode] = n.[EmployeeCode]
        LEFT JOIN tdv_actual a ON t.[EmployeeCode] = a.[EmployeeCode]
        WHERE n.[PositionCode] IN ({placeholders}) AND (n.[IsDuplicate] IS NULL OR n.[IsDuplicate] = 0)
    ''')
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    result = []
    for r in rows:
        target = float(r.month_sale_target) if r.month_sale_target else 0.0
        amount = float(r.month_sale_amount or 0)
        pct = (amount / target) if target > 0 else None
        result.append(types.SimpleNamespace(
            employee_code=r.employee_code, employee_name=r.employee_name, area_code=r.area_code,
            position_code=r.position_code,
            month_sale_target=target, month_sale_amount=amount, month_sale_percent=pct))
    return result


def get_bravo_kpi_quarter_year_snapshot(position_codes):
    """
    Tái tạo % QUÝ và % NĂM từ lịch sử SNAPSHOT HÀNG THÁNG trên FACT_TongHopKhachHang (Bravo,
    10/07/2026) — bảng không có cột quý/năm riêng, nhưng giữ 1 bản ghi mỗi tháng (SaveDate =
    ngày làm việc cuối tháng, hoặc hôm nay cho tháng đang chạy) từ 01/2025 tới nay.

    XÁC NHẬN THỰC TẾ trước khi dùng: [MonthSaleTarget]/[Amount_Cus] là số THÁNG, dao động lên
    xuống theo từng tháng (KHÔNG cộng dồn) — vd 1 NV: 880tr/900tr/968tr/830tr/1010tr/923tr qua
    6 tháng liên tiếp, không phải chuỗi tăng dần. [YearSaleTarget] NGƯỢC LẠI đã là số CỘNG DỒN
    theo năm (2.6 tỷ tháng 1 -> 11.8 tỷ tháng 7, luôn tăng) — không được cộng dồn thêm lần nữa.
    => % quý = tổng Amount_Cus các tháng trong quý / tổng MonthSaleTarget các tháng đó.
    => % năm = tổng Amount_Cus các tháng từ đầu năm / YearSaleTarget tại snapshot MỚI NHẤT.

    RỦI RO CẦN BIẾT (khác hẳn công nợ/KPI tháng đã verify được số thật): KHÔNG có số liệu "sự
    thật đã biết" nào để đối chiếu (không giống công nợ — đã so khớp được với số liệu quan sát
    trước đó). "Quý" ở đây là quý dương lịch (Q1=T1-3...) — CHƯA xác nhận đây có đúng là cách
    DNH tự định nghĩa quý trong chính sách QĐ 0429-2 hay không. CHỈ dùng cho cảnh báo SỚM, không
    dùng làm căn cứ chính thức cho quyết định nhân sự (giống tinh thần banner công nợ tạm thời).

    Trả dict {employee_code: SimpleNamespace(employee_code, employee_name, area_code,
    quarter_sale_percent, year_sale_percent)}. Raise exception nếu Bravo không truy cập được.
    """
    from sqlalchemy import text
    import types
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    pos_ph = ",".join(f"'{p}'" for p in position_codes)

    def _sum_for_dates(conn, dates):
        if not dates:
            return {}
        date_ph = ",".join(f"'{d.strftime('%Y-%m-%d')}'" for d in dates)
        sql = text(f'''
            WITH tgt AS (
                SELECT DISTINCT [SaveDate], [EmployeeCode], [AreaCode], [MonthSaleTarget]
                FROM [FACT_TongHopKhachHang] WHERE [SaveDate] IN ({date_ph})
            ),
            act AS (
                SELECT [SaveDate], [EmployeeCode], SUM([Amount_Cus]) AS amt
                FROM [FACT_TongHopKhachHang] WHERE [SaveDate] IN ({date_ph})
                GROUP BY [SaveDate], [EmployeeCode]
            )
            SELECT n.[EmployeeCode] AS employee_code, n.[Name] AS employee_name,
                   MAX(t.[AreaCode]) AS area_code,
                   SUM(t.[MonthSaleTarget]) AS total_target, SUM(ISNULL(a.amt, 0)) AS total_actual
            FROM tgt t
            JOIN [DIM_NhanVien] n ON t.[EmployeeCode] = n.[EmployeeCode]
            LEFT JOIN act a ON a.[SaveDate] = t.[SaveDate] AND a.[EmployeeCode] = t.[EmployeeCode]
            WHERE n.[PositionCode] IN ({pos_ph}) AND (n.[IsDuplicate] IS NULL OR n.[IsDuplicate] = 0)
            GROUP BY n.[EmployeeCode], n.[Name]
        ''')
        rows = conn.execute(sql).fetchall()
        return {r.employee_code: (r.employee_name, r.area_code, float(r.total_target or 0), float(r.total_actual or 0))
                for r in rows}

    with engine.connect() as conn:
        raw_dates = [r[0] for r in conn.execute(text("SELECT DISTINCT [SaveDate] FROM [FACT_TongHopKhachHang]")).fetchall()]
        parsed = [d if hasattr(d, "year") else datetime.strptime(str(d)[:10], "%Y-%m-%d").date() for d in raw_dates]
        if not parsed:
            return {}
        parsed.sort()
        latest = parsed[-1]
        by_month = {}
        for d in parsed:
            by_month[(d.year, d.month)] = d  # sort tăng dần -> luôn giữ bản MỚI NHẤT trong tháng đó
        quarter_start_month = ((latest.month - 1) // 3) * 3 + 1
        quarter_dates = [dt for (y, m), dt in by_month.items() if y == latest.year and quarter_start_month <= m <= latest.month]
        year_dates = [dt for (y, m), dt in by_month.items() if y == latest.year and m <= latest.month]

        quarter_map = _sum_for_dates(conn, quarter_dates)
        year_actual_map = _sum_for_dates(conn, year_dates)
        year_target_row = conn.execute(text('''
            SELECT DISTINCT [EmployeeCode], [YearSaleTarget]
            FROM [FACT_TongHopKhachHang] WHERE [SaveDate] = :latest
        '''), {"latest": latest.strftime("%Y-%m-%d")}).fetchall()
        year_target_map = {r[0]: float(r[1] or 0) for r in year_target_row}

    result = {}
    for emp_code, (name, area, q_target, q_actual) in quarter_map.items():
        q_pct = (q_actual / q_target) if q_target > 0 else None
        y_actual = year_actual_map.get(emp_code, (name, area, 0, 0))[3]
        y_target = year_target_map.get(emp_code, 0)
        y_pct = (y_actual / y_target) if y_target > 0 else None
        result[emp_code] = types.SimpleNamespace(
            employee_code=emp_code, employee_name=name, area_code=area,
            quarter_sale_percent=q_pct, year_sale_percent=y_pct)
    return result


def _last_complete_data_day():
    """
    Trả về ngày LIỀN TRƯỚC ngày mới nhất có dữ liệu hóa đơn (gộp cả OTC brv_hoadonhdr và ETC
    brvsx_hoadonhdr) — mốc "hôm nay" dùng chung cho MỌI alert cần gắn nhãn thời gian rõ ràng
    (ngày/tháng/năm cụ thể) thay vì datetime.now() (giờ máy chạy job, có thể khác ngày dữ liệu
    thật đã đồng bộ) hoặc MAX(DocDate) thẳng (ngày mới nhất luôn có thể đang dở dang do TDV nhập
    liệu suốt ngày / sync chưa bắt kịp cuối ngày — xác minh thực tế 08/07/2026: ngày mới nhất chỉ
    16/~135 nhân viên phát sinh hóa đơn so với ngày liền trước có 135 người).
    None nếu chưa có dữ liệu hóa đơn nào. Tự failover Supabase -> Bravo qua run_with_failover().
    """
    from sqlalchemy import text
    from src.database import run_with_failover

    def _pg(conn):
        overall_max_row = conn.execute(text('''
            SELECT MAX(d) FROM (
                SELECT MAX("DocDate"::date) AS d FROM brv_hoadonhdr WHERE "IsActive"=TRUE
                UNION ALL
                SELECT MAX("DocDate"::date) FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE
            ) x
        ''')).fetchone()
        overall_max = overall_max_row[0] if overall_max_row else None
        if not overall_max:
            return None
        complete_row = conn.execute(text('''
            SELECT MAX(d) FROM (
                SELECT MAX("DocDate"::date) AS d FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "DocDate"::date < :overall_max
                UNION ALL
                SELECT MAX("DocDate"::date) FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE AND "DocDate"::date < :overall_max
            ) x
        '''), {"overall_max": overall_max}).fetchone()
        return complete_row[0] if complete_row else None

    def _mssql(conn):
        # Driver ODBC cũ "SQL Server" (không phải "ODBC Driver 17"): (a) trả cột kiểu date về dạng
        # CHUỖI 'YYYY-MM-DD' thay vì datetime.date gốc, (b) lỗi SQLBindParameter nếu bind thẳng
        # datetime.date vào query sau — xác nhận thực tế 10/07/2026. Ép kiểu tường minh cả 2 chiều.
        overall_max_row = conn.execute(text('''
            SELECT MAX(d) FROM (
                SELECT MAX("DocDate") AS d FROM dbo.BRV_HoaDonHdr WHERE "IsActive"=1
                UNION ALL
                SELECT MAX("DocDate") FROM dbo.BRVSX_HoaDonHdr WHERE "IsActive"=1
            ) x
        ''')).fetchone()
        overall_max = overall_max_row[0] if overall_max_row else None
        if not overall_max:
            return None
        overall_max_str = overall_max.strftime("%Y-%m-%d") if hasattr(overall_max, "strftime") else str(overall_max)
        complete_row = conn.execute(text('''
            SELECT MAX(d) FROM (
                SELECT MAX("DocDate") AS d FROM dbo.BRV_HoaDonHdr WHERE "IsActive"=1 AND "DocDate" < :overall_max
                UNION ALL
                SELECT MAX("DocDate") FROM dbo.BRVSX_HoaDonHdr WHERE "IsActive"=1 AND "DocDate" < :overall_max
            ) x
        '''), {"overall_max": overall_max_str}).fetchone()
        result = complete_row[0] if complete_row else None
        if result is None or hasattr(result, "strftime"):
            return result
        return datetime.strptime(str(result)[:10], "%Y-%m-%d").date()

    return run_with_failover(_pg, _mssql, label="last_complete_data_day")


def _month_period_label(month_start, data_day=None):
    """
    Nhãn "Kỳ / Ngày" rõ ràng cho card Teams/email: tháng lấy từ DỮ LIỆU THẬT (không phải giờ máy
    chạy job) + ngày dữ liệu đã đồng bộ trọn vẹn gần nhất (nếu biết) — tránh nhãn mơ hồ kiểu chỉ
    "MM/YYYY" hoặc lệch ngày do dùng thẳng datetime.now().

    month_start/data_day có thể là CHUỖI 'YYYY-MM-DD' thay vì date/datetime khi tới từ nhánh Bravo
    (driver ODBC cũ "SQL Server" trả cột date dạng chuỗi — xác nhận thực tế 13/07/2026, cùng lỗi
    đã sửa ở nhiều nơi khác trong file này). Ép kiểu tường minh trước khi gọi .strftime().
    """
    if month_start is None:
        return datetime.now().strftime("%m/%Y")
    if not hasattr(month_start, "strftime"):
        month_start = datetime.strptime(str(month_start)[:10], "%Y-%m-%d")
    label = month_start.strftime("%m/%Y")
    if data_day:
        if not hasattr(data_day, "strftime"):
            data_day = datetime.strptime(str(data_day)[:10], "%Y-%m-%d")
        label += f" (dữ liệu cập nhật đến ngày {data_day.strftime('%d/%m/%Y')})"
    return label


def run_smart_business_alerts():
    """
    Quét và gửi cảnh báo thông minh (Nợ quá hạn, Cháy kho, KPI thấp).

    Phần NỢ QUÁ HẠN ưu tiên tính TỨC THỜI từ Bravo (get_bravo_receivables_snapshot, 10/07/2026),
    dự phòng receivable_detail (Supabase) nếu Bravo lỗi. Phần Cháy kho/KPI vẫn đọc inventory/
    kpi_summary trên Supabase (chưa có nguồn Bravo tương đương đã kiểm chứng — xem TODO tồn kho).
    """
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return

    # 1. CẢNH BÁO NỢ QUÁ HẠN KHUNG (Top Overdue Debts) — Bravo trước, Supabase dự phòng
    debt_rows = []
    debt_period_label = None
    try:
        snapshot = get_bravo_receivables_snapshot()
        debt_period_label = f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})"
        enriched = []
        for r in snapshot:
            total_overdue = float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            if total_overdue <= 10000000:
                continue
            # 14/07/2026: cập nhật nhãn theo mốc mới (1-30/31-60/61-90/>90 ngày) — trước đó ghi
            # cứng text theo mốc CŨ (1-15/15-30/30-45/>45) trong khi field overdue_1_15/15_30/
            # 30_45/gt_45 đã đổi ý nghĩa (giữ nguyên TÊN field, chỉ đổi biên ngày tính, xem
            # _BRAVO_RECEIVABLES_SQL) — sai nhãn hiển thị dù số tiền vẫn đúng.
            if r.overdue_gt_45 and float(r.overdue_gt_45) > 0:
                days_overdue = "Trên 90 ngày"
            elif r.overdue_30_45 and float(r.overdue_30_45) > 0:
                days_overdue = "Từ 61 đến 90 ngày"
            elif r.overdue_15_30 and float(r.overdue_15_30) > 0:
                days_overdue = "Từ 31 đến 60 ngày"
            else:
                days_overdue = "Từ 1 đến 30 ngày"
            enriched.append((total_overdue, r.customer_code, r.customer_name, r.sales_channel,
                              float(r.balance_end or 0), days_overdue))
        enriched.sort(key=lambda x: x[0], reverse=True)
        debt_rows = enriched[:5]
    except Exception as e:
        print(f"[ALERTS][smart_debt] Bravo lỗi ({e}) — dự phòng Supabase receivable_detail.")
        try:
            with engine.connect() as conn:
                latest_period, _ = _two_latest_periods(conn)
            if not latest_period:
                print("[ALERTS][smart_debt] Không tìm thấy kỳ báo cáo nào trong receivable_detail.")
            else:
                debt_period_label = latest_period
                with engine.connect() as conn:
                    sb_rows = conn.execute(text('''
                        SELECT period, customer_code, customer_name, total_overdue, balance_end,
                               overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45, sales_channel
                        FROM receivable_detail
                        WHERE period = :p AND total_overdue > 10000000
                        ORDER BY total_overdue DESC
                        LIMIT 5
                    '''), {"p": latest_period}).fetchall()
                for r in sb_rows:
                    days_overdue = estimate_overdue_days_str(
                        r.period, r.overdue_1_15, r.overdue_15_30, r.overdue_30_45, r.overdue_gt_45)
                    debt_rows.append((r.total_overdue, r.customer_code, r.customer_name, r.sales_channel,
                                       r.balance_end, days_overdue))
        except Exception as e2:
            print(f"[ALERTS][smart_debt] Lỗi cả 2 nguồn: {e2}")

    if debt_rows:
        alert_key = "smart_debt_overdue_top5"
        top_overdue = debt_rows[0][0]
        if should_send_alert(alert_key, cooldown_hours=6, current_value=str(top_overdue)):
            rows = []
            channels_seen = set()
            for total_overdue, customer_code, customer_name, sales_channel, balance_end, days_overdue in debt_rows:
                overdue_fmt = format_vietnamese_money(total_overdue)
                balance_fmt = format_vietnamese_money(balance_end)
                channel_label = normalize_channel_label(sales_channel)
                channels_seen.add(channel_label)
                rows.append([str(customer_code), customer_name, channel_label, overdue_fmt, balance_fmt, days_overdue])

            header_channel = channels_seen.pop() if len(channels_seen) == 1 else "OTC + ETC"
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO NỢ QUÁ HẠN LỚN (TOP 5)",
                severity="CRITICAL",
                summary=f"Hệ thống phát hiện danh sách nhà thuốc/đại lý đang có nợ quá hạn lớn nhất ở mức báo động đỏ (Kỳ: {debt_period_label}).",
                table_headers=["Mã KH", "Tên Đại Lý", "Kênh", "Nợ Quá Hạn", "Tổng Nợ", "Số Ngày Nợ"],
                table_rows=rows,
                channels=("teams",),
                period=debt_period_label, channel=header_channel, region="Toàn quốc",
                issue="Top 5 khách hàng/đại lý có nợ quá hạn lớn nhất vượt mức báo động đỏ"
            )
            record_alert_sent(alert_key, top_overdue)
    else:
        print("[ALERTS][smart_debt] Không có khách hàng nào nợ quá hạn vượt ngưỡng 10 triệu.")

    # 2. CẢNH BÁO CHÁY HÀNG TỒN KHO (Inventory Out-of-Stock Risk)
    inv_rows = []
    try:
        with engine.connect() as conn:
            if not _supabase_table_exists(conn, "inventory"):
                print("[ALERTS][smart_inventory] Bảng 'inventory' chưa có dữ liệu (chờ Excel/DNH) — bỏ qua.")
            else:
                inv_rows = conn.execute(text('''
                    SELECT item_code, item_name, closing_qty, outward_qty, months_to_sell, channel
                    FROM inventory
                    WHERE months_to_sell > 0.0 AND months_to_sell <= 1.0 AND closing_qty > 0
                    ORDER BY months_to_sell ASC
                    LIMIT 5
                ''')).fetchall()
    except Exception as e:
        print(f"[ALERTS][smart_inventory] Lỗi truy vấn tồn kho (có thể thiếu cột outward_qty hoặc channel trên Supabase): {e}")
        inv_rows = []
 
    if inv_rows:
        alert_key = "smart_inventory_depletion_top5"
        top_qty = inv_rows[0].closing_qty
        if should_send_alert(alert_key, cooldown_hours=12, current_value=str(top_qty)):
            rows = []
            for r in inv_rows:
                closing_qty = r.closing_qty
                outward_qty = r.outward_qty
                months_to_sell = r.months_to_sell
                channel = r.channel or "Không rõ"
 
                # Số ngày bán = Tồn kho / Số lượng bán trung bình mỗi ngày (outward_qty/365).
                # 14/07/2026: bỏ math.ceil() trên sales_per_day trước khi chia — làm tròn LÊN 1 tỷ
                # lệ (rate) rồi mới chia khiến MỌI mặt hàng có outward_qty từ 1-364 (bán dưới 1
                # SKU/ngày) đều bị quy đồng về đúng "1 SKU/ngày", làm sai lệch "ngày còn bán" rất xa
                # so với months_to_sell (đã tính đúng ở ETL) — phát hiện qua audit toàn repo. Giờ
                # chia trực tiếp với độ chính xác đầy đủ, chỉ làm tròn (ceil, ước lượng thận trọng)
                # ở kết quả CUỐI (số ngày), không làm tròn ở bước trung gian.
                if outward_qty is not None and outward_qty > 0:
                    sales_per_day = outward_qty / 365
                    days = math.ceil(closing_qty / sales_per_day)
                    days_to_sell_fmt = f"Còn {days} ngày bán (Trung bình bán {sales_per_day:.2f} SKU/ngày)"
                else:
                    days_to_sell_fmt = format_months_to_sell(months_to_sell)
 
                rows.append([str(r.item_code), channel, r.item_name, f"{closing_qty:,.0f}".replace(',', '.'), days_to_sell_fmt])
 
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO NGUY CƠ ĐỨT HÀNG (TOP 5)",
                severity="WARNING",
                summary="Các mặt hàng sau có tốc độ bán quá nhanh và tồn kho chỉ đủ dùng trong dưới 1 tháng.",
                table_headers=["Mã SKU", "Kênh", "Tên Thuốc", "Tồn Kho Hiện Tại", "Dự Kiến Bán Hết"],
                table_rows=rows,
                channels=("teams",),
                period=datetime.now().strftime("%d/%m/%Y"), region="Toàn quốc",
                issue="Tồn kho sắp cạn (dưới 1 tháng bán) do tốc độ bán quá nhanh"
            )
            record_alert_sent(alert_key, top_qty)
    else:
        print("[ALERTS][smart_inventory] Không có mặt hàng nào sắp cạn (dưới 1 tháng bán).")

    # 3. CẢNH BÁO TIẾN ĐỘ KPI DOANH SỐ THẤP (Low sales target progress) — Bravo trước (TDV), Supabase dự phòng
    kpi_rows = []
    kpi_period_label = None
    try:
        snapshot = get_bravo_kpi_tdv_snapshot()
        kpi_period_label = f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})"
        kpi_rows = [r for r in snapshot if r.month_sale_target > 10000000 and r.month_sale_percent is not None and r.month_sale_percent < 0.60]
        kpi_rows.sort(key=lambda r: r.month_sale_percent)
        kpi_rows = kpi_rows[:5]
    except Exception as e:
        print(f"[ALERTS][smart_kpi] Bravo lỗi ({e}) — dự phòng Supabase kpi_summary.")
        try:
            with engine.connect() as conn:
                kpi_rows = conn.execute(text('''
                    SELECT employee_code, employee_name, area_code, month_sale_target, month_sale_amount, month_sale_percent
                    FROM kpi_summary
                    WHERE month_sale_target > 10000000 AND month_sale_percent < 0.60
                    ORDER BY month_sale_percent ASC
                    LIMIT 5
                ''')).fetchall()
                # kpi_summary không có cột ngày riêng — mượn ngày dữ liệu hóa đơn gần nhất đã đồng bộ
                # trọn vẹn làm mốc "tính đến ngày" rõ ràng, thay vì giờ máy chạy job (datetime.now()).
                kpi_period_label = _month_period_label(_last_complete_data_day(), _last_complete_data_day())
        except Exception as e2:
            print(f"[ALERTS][smart_kpi] Lỗi cả 2 nguồn: {e2}")
            kpi_rows = []

    if kpi_rows:
        alert_key = "smart_kpi_low_progress_top5"
        lowest_pct = kpi_rows[0].month_sale_percent
        if should_send_alert(alert_key, cooldown_hours=24, current_value=str(lowest_pct)):
            rows = []
            regions_seen = set()
            for r in kpi_rows:
                real_pct = r.month_sale_percent * 100
                percent_fmt = f"{real_pct:.1f}%".replace('.', ',')
                target_fmt = format_vietnamese_money(r.month_sale_target)
                amount_fmt = format_vietnamese_money(r.month_sale_amount)
                region_label = normalize_region_label(r.area_code)
                regions_seen.add(region_label)
                rows.append([str(r.employee_code), r.employee_name, region_label, target_fmt, amount_fmt, percent_fmt])
            header_region = regions_seen.pop() if len(regions_seen) == 1 else "Nhiều miền"

            send_alert_to_all_channels(
                alert_name="CẢNH BÁO TIẾN ĐỘ KPI TDV THẤP (TOP 5)",
                severity="WARNING",
                summary="Các Trình dược viên sau đang đạt dưới 60% chỉ tiêu doanh số tháng.",
                table_headers=["Mã TDV", "Tên TDV", "Vùng", "Chỉ Tiêu", "Doanh Số Đạt", "Đạt Được"],
                table_rows=rows,
                channels=("teams",),
                period=kpi_period_label,
                region=header_region,
                issue="Trình dược viên đạt dưới 60% chỉ tiêu doanh số tháng"
            )
            record_alert_sent(alert_key, lowest_pct)
    else:
        print("[ALERTS][smart_kpi] Không có nhân sự nào đạt dưới 60% chỉ tiêu doanh số tháng.")

def run_sales_kpi_insights_alert():
    """
    Quét và gửi báo cáo phân tích hiệu suất KPI doanh số theo chức danh (TP/PP/QLV/TDV/CTV/CS).

    LƯU Ý: trước đây báo cáo này còn có phần chia theo kênh (OTC/ETC), nhưng phần đó dựa trên
    dữ liệu suy luận không đáng tin cậy (xem docstring get_sales_and_kpi_analytics) nên đã bỏ —
    chỉ còn phần so sánh theo chức danh, đọc thẳng kpi_summary trên Supabase.

    CHỦ ĐỘNG GIỮ SUPABASE (không chuyển Bravo-first, 10/07/2026): báo cáo gồm CẢ TP/PP/QLV lẫn
    TDV/CTV/CS trong cùng 1 bảng so sánh — TP/PP/CS/CTV/TK KHÔNG tồn tại trên Bravo (chỉ TDV/QLV có
    qua FACT_TongHopKhachHang, đã xác nhận ở get_bravo_kpi_tdv_snapshot). Không tách được 1 phần
    sang Bravo mà giữ nguyên ý nghĩa "so sánh đủ mọi cấp bậc" của báo cáo này.
    """
    from src.analytics import get_sales_and_kpi_analytics

    data = get_sales_and_kpi_analytics()
    if "error" in data:
        print(f"[ALERTS] Không thể phân tích KPI doanh số: {data['error']}")
        return

    alert_key = f"sales_kpi_insights_report_{data['latest_period']}"
    # Cooldown 12 tiếng để tránh spam báo cáo định kỳ
    if should_send_alert(alert_key, cooldown_hours=12, current_value="sent"):
        rows = []

        # 1. So sánh hiệu suất giữa các Trưởng phòng (TP)
        if data['tps']:
            for r in data['tps']:
                rows.append([
                    f"TP: {r['employee_name']}",
                    format_vietnamese_money(r['month_sale_target']),
                    format_vietnamese_money(r['month_sale_amount']),
                    f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
                ])
                
        # 2. So sánh hiệu suất giữa các Phó phòng (PP)
        if data['pps']:
            for r in data['pps']:
                rows.append([
                    f"PP: {r['employee_name']}",
                    format_vietnamese_money(r['month_sale_target']),
                    format_vietnamese_money(r['month_sale_amount']),
                    f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
                ])

        # 3. So sánh hiệu suất giữa các Quản lý vùng (QLV)
        if data['qlvs']:
            for r in data['qlvs']:
                rows.append([
                    f"QLV: {r['employee_name']}",
                    format_vietnamese_money(r['month_sale_target']),
                    format_vietnamese_money(r['month_sale_amount']),
                    f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
                ])
                
        # 4. Top 3 TDV/CTV xuất sắc nhất
        for idx, r in enumerate(data['top_reps']):
            rows.append([
                f"⭐ Top {idx+1} TDV: {r['employee_name']}",
                format_vietnamese_money(r['month_sale_target']),
                format_vietnamese_money(r['month_sale_amount']),
                f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
            ])

        # 5. Top 3 TDV/CTV cần hỗ trợ
        for idx, r in enumerate(data['bottom_reps']):
            rows.append([
                f"⚠️ Cần hỗ trợ #{idx+1}: {r['employee_name']} ({r['position_code']})",
                format_vietnamese_money(r['month_sale_target']),
                format_vietnamese_money(r['month_sale_amount']),
                f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
            ])

        send_alert_to_all_channels(
            alert_name="BÁO CÁO PHÂN TÍCH KPI THEO CHỨC DANH",
            severity="INFO",
            summary=f"Báo cáo định kỳ so sánh hiệu suất thực hiện KPI doanh số theo cấp bậc quản lý (TP/PP/QLV) vs nhân viên trực tiếp (TDV/CTV/CS) — kỳ {data['latest_period']}.",
            table_headers=["Phân Loại / Nhân Sự", "KPI Mục Tiêu", "Doanh Số Đạt", "Tỷ Lệ Hoàn Thành"],
            table_rows=rows,
            channels=("teams",),
            period=data['latest_period'], region="Toàn quốc",
            issue="Báo cáo định kỳ hiệu suất KPI doanh số theo cấp bậc quản lý"
        )
        record_alert_sent(alert_key, "sent")

# =============================================================================
# TRIGGER 4 & 5 (Phase 1.2 — Go-Live Plan): Doanh thu giảm > ngưỡng + Nợ vượt hạn mức
# Đọc dữ liệu THẬT từ Postgres/Supabase (mirror Bravo/DMS) qua engine dùng chung của
# chatbot — tái sử dụng, không viết lại logic kết nối/parse kỳ.
# =============================================================================

def revenue_drop_ratio(prev_revenue, latest_revenue):
    """
    Hàm thuần (pure) để unit test: trả về tỷ lệ sụt giảm doanh thu so với kỳ trước.
    (prev - latest) / prev. Trả về None nếu không tính được (prev <= 0 hoặc thiếu dữ liệu).
    Giá trị dương = có sụt giảm; âm = tăng trưởng.
    """
    if prev_revenue is None or latest_revenue is None:
        return None
    try:
        prev = float(prev_revenue)
        latest = float(latest_revenue)
    except (TypeError, ValueError):
        return None
    if prev <= 0:
        return None
    return (prev - latest) / prev


def _get_revenue_drop_threshold():
    """Đọc ngưỡng % sụt giảm từ config (mặc định 0.20 = 20%)."""
    try:
        config = load_config()
        return float(config['thresholds']['business']['revenue_drop_pct'])
    except Exception:
        return 0.20


def check_revenue_drop_alert():
    """
    TRIGGER 4: Cảnh báo khi doanh thu (loại trừ dòng khuyến mãi CTKM) từ đầu tháng đến ngày dữ
    liệu mới nhất giảm quá ngưỡng (mặc định 20%) so với ĐÚNG SỐ NGÀY tương ứng của tháng liền
    trước — tính RIÊNG cho từng kênh OTC/ETC (không gộp trước khi so ngưỡng).

    So sánh "cùng số ngày đầu kỳ" (apples-to-apples) thay vì tháng-hiện-tại-dở-dang vs
    tháng-trước-trọn-vẹn: nếu không sẽ luôn báo sụt giảm giả ~80-95% vào đầu mỗi tháng chỉ vì
    tháng mới có vài ngày dữ liệu so với tháng trước đủ ~30 ngày. Lỗi này phát hiện thực tế ngày
    08/07/2026 (alert báo ETC "giảm 84.9%" chỉ vì mới có 8 ngày tháng 7 so với trọn tháng 6, không
    phải sụt giảm kinh doanh thật). Khi tháng hiện tại đã đủ ngày (cuối tháng), công thức tự động
    quay về đúng "tháng N trọn vẹn vs tháng N-1 trọn vẹn" như thiết kế ban đầu.

    Mốc "hôm nay" lấy theo ngày LIỀN TRƯỚC ngày mới nhất có dữ liệu hóa đơn (không dùng
    datetime.now(), KHÔNG dùng thẳng MAX(DocDate)) — xác minh thực tế 08/07/2026 (xem
    check_daily_kpi_pace_alert): ngày mới nhất trong dữ liệu luôn CHƯA đồng bộ xong (TDV nhập liệu
    suốt ngày, sync 5 lần/ngày chưa chắc bắt kịp cuối ngày — vd hôm đó ngày mới nhất chỉ có
    16/~135 nhân viên phát sinh hóa đơn so với ngày liền trước có 135 người). Dùng thẳng ngày đó
    làm mốc cuối kỳ sẽ khiến kỳ "tháng này" bị thiếu 1 ngày gần trọn vẹn, làm tỷ lệ sụt giảm lệch
    lên — ngày liền trước chắc chắn đã đồng bộ trọn vẹn.

    LƯU Ý CÁCH TÍNH (cần DNH xác nhận theo MCNA_DNH_ProjectPlan_v3.docx):
      - Hiện triển khai so sánh THÁNG N vs THÁNG N-1 (month-over-month, kỳ liền kề).
      - Nếu DNH chốt so cùng kỳ NĂM TRƯỚC (year-over-year, tránh nhiễu mùa vụ) thì đổi
        mốc thời gian — nhưng dữ liệu hiện chỉ có Q2/2026 nên YoY chưa tính được.
    """
    try:
        from ai_agent.chatbot import _get_cloud_engine
        from src.etl import _period_revenue, _prev_month_tuple
        from sqlalchemy import text
    except Exception as e:
        print(f"[ALERTS][revenue_drop] Không import được engine dữ liệu: {e}")
        return

    try:
        data_max_date = _last_complete_data_day()
        if not data_max_date:
            print("[ALERTS][revenue_drop] Chưa có dữ liệu hóa đơn để so sánh.")
            return

        cur_month_start = datetime(data_max_date.year, data_max_date.month, 1)
        days_elapsed = (data_max_date - cur_month_start.date()).days + 1
        cur_start = cur_month_start
        cur_end = cur_month_start + timedelta(days=days_elapsed)

        prev_year, prev_month = _prev_month_tuple(cur_month_start)
        prev_start = datetime(prev_year, prev_month, 1)
        # Chặn trên bằng đầu tháng hiện tại — nếu tháng trước ít ngày hơn số ngày đã trôi qua
        # của tháng này (vd so ngày 31 với tháng 2) thì lấy trọn tháng trước, không tràn sang tháng sau nữa.
        prev_end = min(prev_start + timedelta(days=days_elapsed), cur_month_start)

        cur_otc, cur_etc, _, _ = _period_revenue(cur_start, cur_end)
        prev_otc, prev_etc, _, _ = _period_revenue(prev_start, prev_end)
    except Exception as e:
        print(f"[ALERTS][revenue_drop] Lỗi truy vấn doanh thu: {e}")
        return

    threshold = _get_revenue_drop_threshold()
    by_channel = {"OTC": (cur_otc, prev_otc), "ETC": (cur_etc, prev_etc)}
    period_desc = f"{cur_start.strftime('%d/%m')}-{data_max_date.strftime('%d/%m/%Y')}"
    prev_period_desc = f"{prev_start.strftime('%d/%m')}-{(prev_end - timedelta(days=1)).strftime('%d/%m/%Y')}"

    for channel_label, (latest_rev, prev_rev) in by_channel.items():
        ratio = revenue_drop_ratio(prev_rev, latest_rev)
        if ratio is None:
            print(f"[ALERTS][revenue_drop][{channel_label}] Không tính được tỷ lệ sụt giảm (doanh thu kỳ trước <= 0).")
            continue

        print(f"[ALERTS][revenue_drop][{channel_label}] {period_desc} vs {prev_period_desc}: tỷ lệ thay đổi = {ratio*100:.1f}% (ngưỡng cảnh báo giảm > {threshold*100:.0f}%).")

        if ratio > threshold:
            alert_key = f"revenue_drop:{channel_label}:{cur_month_start.strftime('%Y-%m')}"
            if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(ratio, 4))):
                drop_amount = float(prev_rev) - float(latest_rev)
                send_alert_to_all_channels(
                    alert_name=f"CẢNH BÁO DOANH THU SỤT GIẢM MẠNH ({channel_label})",
                    severity="CRITICAL",
                    summary=(f"Doanh thu kênh {channel_label} kỳ {period_desc} giảm "
                             f"{ratio*100:.1f}% so với cùng số ngày kỳ {prev_period_desc} "
                             f"(vượt ngưỡng cảnh báo {threshold*100:.0f}%)."),
                    table_headers=["Kỳ", f"Doanh thu {channel_label} (đã trừ KM)", "Chênh lệch"],
                    table_rows=[
                        [prev_period_desc, format_vietnamese_money(prev_rev), "—"],
                        [period_desc, format_vietnamese_money(latest_rev),
                         f"-{format_vietnamese_money(drop_amount)} ({ratio*100:.1f}%)"],
                    ],
                    channels=("teams",),
                    period=cur_month_start.strftime('%m/%Y'), channel=channel_label, region="Toàn quốc",
                    issue=f"Doanh thu kênh {channel_label} giảm {ratio*100:.1f}% so với cùng số ngày kỳ trước"
                )
                record_alert_sent(alert_key, str(round(ratio, 4)))


def _find_credit_limit_column(conn):
    """
    Dò tìm cột hạn mức tín dụng trong schema (dms_khachhang / receivable_detail).
    Trả về (table_name, column_name) nếu tìm thấy, ngược lại None.
    Đây là GAP DỮ LIỆU đã biết: hạn mức tín dụng có thể còn nằm ở Bravo/DMS nguồn,
    chưa được đưa vào staging/mart — cần DNH xác nhận (xem Go-Live Plan Phase 1.2b).
    """
    from sqlalchemy import text
    q = text("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('dms_khachhang', 'dmssx_khachhang', 'receivable_detail')
          AND (lower(column_name) LIKE '%credit%limit%'
               OR lower(column_name) LIKE '%creditlimit%'
               OR lower(column_name) LIKE '%hanmuc%'
               OR lower(column_name) LIKE '%han_muc%')
        LIMIT 1
    """)
    row = conn.execute(q).fetchone()
    return (row[0], row[1]) if row else None


def check_credit_limit_exceeded_alert():
    """
    TRIGGER 5: Cảnh báo khi dư nợ hiện tại của khách hàng vượt hạn mức tín dụng.

    TRẠNG THÁI: Phòng thủ theo GAP DỮ LIỆU. Hàm tự dò cột hạn mức tín dụng lúc chạy;
    nếu schema chưa có cột này (rất có thể vì credit limit còn ở Bravo/DMS nguồn, chưa
    được đưa vào staging/mart), hàm ghi log rõ ràng và no-op — KHÔNG crash. Khi DNH đưa
    cột hạn mức vào mart, hàm tự động kích hoạt so sánh balance_end vs hạn mức mà không
    cần sửa code khung này (chỉ hoàn thiện phần liệt kê nếu cần).
    """
    try:
        from ai_agent.chatbot import _get_cloud_engine
        from sqlalchemy import text
    except Exception as e:
        print(f"[ALERTS][credit_limit] Không import được engine dữ liệu: {e}")
        return

    engine = _get_cloud_engine()
    if engine is None:
        print("[ALERTS][credit_limit] Chưa cấu hình CLOUD_DB_URL — bỏ qua cảnh báo hạn mức tín dụng.")
        return

    try:
        with engine.connect() as conn:
            found = _find_credit_limit_column(conn)
            if not found:
                print("[ALERTS][credit_limit] GAP DỮ LIỆU: chưa tìm thấy cột hạn mức tín dụng "
                      "trong dms_khachhang/receivable_detail. Cần DNH đưa hạn mức từ Bravo/DMS "
                      "vào mart trước khi bật cảnh báo này. Bỏ qua (no-op).")
                return

            table_name, col = found
            print(f"[ALERTS][credit_limit] Tìm thấy cột hạn mức: {table_name}.{col} — chạy so sánh dư nợ.")
            # Chỉ chạy khi cột nằm trên receivable_detail (có sẵn balance_end cùng bảng).
            # Nếu hạn mức nằm ở bảng khách hàng, cần join theo customer_code — hoàn thiện khi
            # xác nhận được khóa join thực tế với DNH.
            if table_name != 'receivable_detail':
                print(f"[ALERTS][credit_limit] Cột hạn mức nằm ở '{table_name}', cần xác nhận khóa join "
                      "với receivable_detail (customer_code) trước khi bật — tạm bỏ qua.")
                return

            latest_period_row = conn.execute(text(
                "SELECT DISTINCT period FROM receivable_detail")).fetchall()
            periods = [r[0] for r in latest_period_row if r[0]]
            if not periods:
                return
            try:
                from ai_agent.chatbot import _latest_period_key
                latest_period = max(periods, key=_latest_period_key)
            except Exception:
                latest_period = max(periods)

            q = text(f'''
                SELECT customer_code, customer_name, balance_end, "{col}" AS credit_limit,
                       (balance_end - "{col}") AS over_amount
                FROM receivable_detail
                WHERE period = :p AND "{col}" IS NOT NULL AND "{col}" > 0
                  AND balance_end > "{col}"
                ORDER BY (balance_end - "{col}") DESC
                LIMIT 10
            ''')
            over_rows = conn.execute(q, {"p": latest_period}).fetchall()
    except Exception as e:
        print(f"[ALERTS][credit_limit] Lỗi khi kiểm tra hạn mức tín dụng: {e}")
        return

    if not over_rows:
        print("[ALERTS][credit_limit] Không có khách hàng nào vượt hạn mức tín dụng.")
        return

    alert_key = "credit_limit_exceeded_top10"
    top_over = over_rows[0][4]
    if should_send_alert(alert_key, cooldown_hours=12, current_value=str(top_over)):
        rows = []
        for r in over_rows:
            rows.append([
                str(r[0]), r[1],
                format_vietnamese_money(r[2]),
                format_vietnamese_money(r[3]),
                format_vietnamese_money(r[4]),
            ])
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO NỢ VƯỢT HẠN MỨC TÍN DỤNG",
            severity="CRITICAL",
            summary="Các khách hàng sau có dư nợ hiện tại vượt hạn mức tín dụng được cấp.",
            table_headers=["Mã KH", "Tên Khách Hàng", "Dư Nợ", "Hạn Mức", "Vượt"],
            table_rows=rows,
            channels=("teams",),
            period=latest_period, region="Toàn quốc",
            issue="Khách hàng có dư nợ hiện tại vượt hạn mức tín dụng được cấp"
        )
        record_alert_sent(alert_key, str(top_over))


# =============================================================================
# TRIGGER MỞ RỘNG (nhóm A-G) — đọc lớp dữ liệu hậu-ETL thật (Supabase/Postgres).
# Mỗi hàm tự bọc try/except: lỗi 1 trigger KHÔNG làm chết cả job. Ngưỡng đọc từ config.
# =============================================================================

def _biz_threshold(key, default):
    """Đọc 1 ngưỡng trong thresholds.business của config, fallback default."""
    try:
        return load_config()['thresholds']['business'][key]
    except Exception:
        return default


def _alert_engine():
    """Cloud engine dùng chung của chatbot (lớp hậu-ETL). None nếu chưa cấu hình."""
    try:
        from ai_agent.chatbot import _get_cloud_engine
        return _get_cloud_engine()
    except Exception as e:
        print(f"[ALERTS] Không lấy được engine dữ liệu: {e}")
        return None


def _supabase_table_exists(conn, table_name):
    """
    True nếu bảng tồn tại trong schema public trên Supabase (Postgres). Dùng to_regclass — trả
    NULL thay vì NÉM LỖI khi bảng vắng, nên KHÔNG làm bẩn log bằng stack trace UndefinedTable mỗi
    chu kỳ quét (5 lần/ngày) cho các bảng đang CHỦ ĐỘNG để trống (vd 'inventory' chờ dữ liệu
    Excel/DNH — xem docstring check_dead_stock_alert). Giữ log sạch để lỗi THẬT không bị chôn vùi.
    """
    from sqlalchemy import text
    return conn.execute(
        text("SELECT to_regclass('public.' || :t)"), {"t": table_name}
    ).scalar() is not None


def _two_latest_periods(conn):
    """Trả (latest, previous) period của receivable_detail theo đúng thứ tự thời gian."""
    from sqlalchemy import text
    from ai_agent.chatbot import _latest_period_key
    periods = [r[0] for r in conn.execute(text("SELECT DISTINCT period FROM receivable_detail")).fetchall() if r[0]]
    if not periods:
        return None, None
    periods_sorted = sorted(periods, key=_latest_period_key, reverse=True)
    latest = periods_sorted[0]
    prev = periods_sorted[1] if len(periods_sorted) > 1 else None
    return latest, prev


# ---- Pure helpers (unit-test được, không đụng DB) --------------------------

def overdue_ratio(total_overdue, total_balance):
    """Tỷ lệ nợ quá hạn / tổng dư nợ. None nếu mẫu <= 0."""
    if total_overdue is None or total_balance is None:
        return None
    try:
        ov = float(total_overdue); bal = float(total_balance)
    except (TypeError, ValueError):
        return None
    if bal <= 0:
        return None
    return ov / bal


def concentration_ratio(top_sum, total_sum):
    """Tỷ trọng doanh thu của nhóm top / tổng. None nếu tổng <= 0."""
    if top_sum is None or total_sum is None:
        return None
    try:
        t = float(top_sum); tot = float(total_sum)
    except (TypeError, ValueError):
        return None
    if tot <= 0:
        return None
    return t / tot


def return_rate(return_value, sales_value):
    """Tỷ lệ giá trị hàng trả / doanh số. None nếu doanh số <= 0."""
    if return_value is None or sales_value is None:
        return None
    try:
        rv = float(return_value); sv = float(sales_value)
    except (TypeError, ValueError):
        return None
    if sv <= 0:
        return None
    return rv / sv


# ---- Nhóm A: Công nợ / dòng tiền -------------------------------------------

def check_company_overdue_ratio_alert():
    """
    A3: Tỷ lệ nợ quá hạn / tổng dư nợ vượt ngưỡng (sức khỏe dòng tiền).
    Tính RIÊNG cho từng kênh OTC/ETC (receivable_detail.sales_channel) thay vì gộp toàn công ty,
    để bắt được ca 1 kênh có tỷ lệ quá hạn cao bị kênh kia che lấp khi gộp.
    Ưu tiên tính TỨC THỜI từ Bravo (get_bravo_receivables_snapshot, 10/07/2026); Bravo lỗi thì dự
    phòng đọc receivable_detail (Supabase, theo kỳ gần nhất) như trước.
    """
    from sqlalchemy import text
    threshold = float(_biz_threshold('overdue_ratio_pct', 0.35))

    period_label = None
    by_channel = {}
    try:
        rows = get_bravo_receivables_snapshot()
        period_label = f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})"
        for r in rows:
            label = normalize_channel_label(r.sales_channel)
            acc = by_channel.setdefault(label, [0, 0])
            overdue = float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            acc[0] += overdue
            acc[1] += float(r.balance_end or 0)
    except Exception as e:
        print(f"[ALERTS][overdue_ratio] Bravo lỗi ({e}) — dự phòng Supabase receivable_detail.")
        engine = _alert_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                latest, _ = _two_latest_periods(conn)
                if not latest:
                    return
                period_label = latest
                rows = conn.execute(text(
                    "SELECT sales_channel, SUM(total_overdue) AS overdue, SUM(balance_end) AS balance "
                    "FROM receivable_detail WHERE period=:p GROUP BY sales_channel"
                ), {"p": latest}).fetchall()
                for r in rows:
                    label = normalize_channel_label(r.sales_channel)
                    acc = by_channel.setdefault(label, [0, 0])
                    acc[0] += float(r.overdue or 0)
                    acc[1] += float(r.balance or 0)
        except Exception as e2:
            print(f"[ALERTS][overdue_ratio] Lỗi cả 2 nguồn: {e2}")
            return

    for channel_label, (overdue_sum, balance_sum) in by_channel.items():
        ratio = overdue_ratio(overdue_sum, balance_sum)
        if ratio is None:
            continue
        print(f"[ALERTS][overdue_ratio][{channel_label}] {period_label}: nợ quá hạn/tổng nợ = {ratio*100:.1f}% (ngưỡng {threshold*100:.0f}%).")
        if ratio > threshold:
            alert_key = f"company_overdue_ratio:{channel_label}:{datetime.now().strftime('%Y-%m-%d')}"
            if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(ratio, 4))):
                send_alert_to_all_channels(
                    alert_name=f"CẢNH BÁO TỶ LỆ NỢ QUÁ HẠN CAO ({channel_label})",
                    severity="CRITICAL",
                    summary=(f"{period_label}: tổng nợ quá hạn kênh {channel_label} chiếm {ratio*100:.1f}% tổng dư nợ kênh này "
                             f"(vượt ngưỡng {threshold*100:.0f}%) — dòng tiền kênh {channel_label} đang bị nghẽn."),
                    table_headers=["Tổng dư nợ", "Nợ quá hạn", "Tỷ lệ quá hạn"],
                    table_rows=[[format_vietnamese_money(balance_sum), format_vietnamese_money(overdue_sum), f"{ratio*100:.1f}%"]],
                    channels=("teams",),
                    period=period_label, channel=channel_label, region="Toàn quốc",
                    issue=f"Tỷ lệ nợ quá hạn/tổng dư nợ kênh {channel_label} đạt {ratio*100:.1f}%, vượt ngưỡng an toàn"
                )
                record_alert_sent(alert_key, str(round(ratio, 4)))


def _bravo_recent_orders_by_customer(since):
    """
    Số đơn/giá trị đơn mới theo mã KH từ ngày `since` (date) — đọc thẳng Bravo (OTC+ETC).
    Truyền `since` dưới dạng chuỗi 'YYYY-MM-DD' (không phải datetime.date) — driver ODBC cũ
    "SQL Server" (không phải "ODBC Driver 17") lỗi SQLBindParameter khi bind thẳng kiểu date của
    Python, xác nhận thực tế 10/07/2026; chuỗi ISO thì SQL Server tự convert đúng, không lỗi.

    14/07/2026: đổi sang query view gốc (vHoaDonTotal/vHoaDonETCTotal) thay vì SELECT thẳng
    BRV_HoaDonHdr/BRVSX_HoaDonHdr — bản cũ KHÔNG lọc chứng từ hủy (IsCancelled qua
    BRV_TrangThaiDuyet/BRV_TrangThaiHoaDon, các hàm khác trong file này đã biết lọc) nên 1 đơn
    hàng bị hủy vẫn được tính là "đơn mới", gây cảnh báo A2 sai dựa trên đơn không còn hiệu lực.
    Dùng COUNT(DISTINCT Stt)/SUM(Amount9) từ view thay vì COUNT(*)/SUM(TotalAmount) từ header —
    nhất quán với cách tính "đơn hàng"/"doanh thu" ở mọi nơi khác đã sửa hôm nay.
    """
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine")
    since_str = since.strftime("%Y-%m-%d") if hasattr(since, "strftime") else str(since)
    sql = text('''
        SELECT CustomerCode AS cc, COUNT(DISTINCT Stt) AS n, SUM(Amount9) AS amt FROM (
            SELECT CustomerCode, Stt, Amount9 FROM dbo.vHoaDonTotal WHERE DocDate >= :since
            UNION ALL
            SELECT CustomerCode, Stt, Amount9 FROM dbo.vHoaDonETCTotal WHERE DocDate >= :since
        ) x GROUP BY CustomerCode
    ''')
    with engine.connect() as conn:
        rows = conn.execute(sql, {"since": since_str}).fetchall()
    return {r.cc: (int(r.n), float(r.amt or 0)) for r in rows}


def check_overdue_customer_new_orders_alert():
    """
    A2: Khách đang nợ quá hạn NHƯNG vẫn được lên đơn mới trong tháng gần nhất.
    Ưu tiên tính TỨC THỜI từ Bravo (get_bravo_receivables_snapshot + _bravo_recent_orders_by_customer,
    10/07/2026); Bravo lỗi thì dự phòng đọc receivable_detail (Supabase, theo kỳ gần nhất) như trước.
    """
    from sqlalchemy import text
    import types

    period_label = None
    joined = []  # list of SimpleNamespace(customer_code, customer_name, total_overdue, sales_channel, n, amt)
    try:
        overdue_rows = get_bravo_receivables_snapshot()
        since = datetime.now().replace(day=1).date()
        recent_map = _bravo_recent_orders_by_customer(since)
        period_label = f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})"
        for r in overdue_rows:
            total_overdue = float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            if total_overdue <= 10000000:
                continue
            recent = recent_map.get(r.customer_code)
            if not recent:
                continue
            joined.append(types.SimpleNamespace(
                customer_code=r.customer_code, customer_name=r.customer_name,
                total_overdue=total_overdue, sales_channel=r.sales_channel,
                n=recent[0], amt=recent[1]))
    except Exception as e:
        print(f"[ALERTS][overdue_new_orders] Bravo lỗi ({e}) — dự phòng Supabase receivable_detail.")
        engine = _alert_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                latest, _ = _two_latest_periods(conn)
                if not latest:
                    return
                period_label = latest
                since_row = conn.execute(text(
                    'SELECT DATE_TRUNC(\'month\', MAX("DocDate"::date))::date FROM brv_hoadonhdr WHERE "IsActive"=TRUE'
                )).fetchone()
                since = since_row[0] if since_row and since_row[0] else None
                if since is None:
                    return
                sql = text('''
                    WITH overdue_cust AS (
                        SELECT customer_code, customer_name, total_overdue, sales_channel
                        FROM receivable_detail
                        WHERE period = :p AND total_overdue > 10000000
                    ),
                    recent AS (
                        SELECT "CustomerCode" AS cc, COUNT(*) AS n, SUM("TotalAmount") AS amt
                        FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "IsHC"=FALSE AND "DocDate"::date >= :since
                        GROUP BY "CustomerCode"
                        UNION ALL
                        SELECT "CustomerCode", COUNT(*), SUM("TotalAmount")
                        FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE AND "DocDate"::date >= :since
                        GROUP BY "CustomerCode"
                    ),
                    recent_agg AS (SELECT cc, SUM(n) AS n, SUM(amt) AS amt FROM recent GROUP BY cc)
                    SELECT o.customer_code, o.customer_name, o.total_overdue, o.sales_channel, r.n, r.amt
                    FROM overdue_cust o JOIN recent_agg r ON o.customer_code = r.cc
                    ORDER BY o.total_overdue DESC
                ''')
                joined = conn.execute(sql, {"p": latest, "since": since}).fetchall()
        except Exception as e2:
            print(f"[ALERTS][overdue_new_orders] Lỗi cả 2 nguồn: {e2}")
            return

    if not joined:
        print("[ALERTS][overdue_new_orders] Không có khách quá hạn nào được lên đơn mới.")
        return

    by_channel = {}
    for r in joined:
        label = normalize_channel_label(r.sales_channel)
        by_channel.setdefault(label, []).append(r)

    for channel_label, channel_rows in by_channel.items():
        channel_rows = sorted(channel_rows, key=lambda r: r.total_overdue, reverse=True)[:10]
        alert_key = f"overdue_customer_new_orders:{channel_label}"
        top = channel_rows[0].total_overdue
        if should_send_alert(alert_key, cooldown_hours=12, current_value=str(top)):
            region_map = get_customer_regions_by_code([r.customer_code for r in channel_rows], channel_label)
            table = [[str(r.customer_code), region_map.get(r.customer_code, "Không rõ"), r.customer_name,
                      format_vietnamese_money(r.total_overdue), str(int(r.n)), format_vietnamese_money(r.amt)]
                     for r in channel_rows]
            send_alert_to_all_channels(
                alert_name=f"CẢNH BÁO: KHÁCH NỢ QUÁ HẠN VẪN ĐƯỢC LÊN ĐƠN MỚI ({channel_label})",
                severity="CRITICAL",
                summary=f"Các khách hàng kênh {channel_label} đang nợ quá hạn lớn nhưng vẫn phát sinh đơn hàng mới — cần kiểm duyệt trước khi giao thêm.",
                table_headers=["Mã KH", "Vùng", "Tên KH", "Nợ Quá Hạn", "Số Đơn Mới", "Giá Trị Đơn Mới"],
                table_rows=table,
                channels=("teams",),
                period=period_label, channel=channel_label, region="Toàn quốc",
                issue=f"Khách hàng kênh {channel_label} đang nợ quá hạn lớn nhưng vẫn phát sinh đơn hàng mới chưa được kiểm duyệt"
            )
            record_alert_sent(alert_key, str(top))


def check_debt_aging_migration_alert():
    """
    A1: Khách MỚI rơi vào nhóm nợ >45 ngày ở kỳ này (kỳ trước chưa có) — nợ xấu hình thành.

    ƯU TIÊN BRAVO (10/07/2026): Bravo chỉ có ledger SỐNG (get_bravo_receivables_snapshot() luôn là
    số liệu TỨC THỜI, không tự lưu lịch sử) — nên hàm này tự XÂY snapshot nội bộ (SQLite, xem
    _save_debt_aging_snapshot/_find_prev_month_snapshot_date): mỗi lần chạy tự chụp lại tình trạng
    nợ >45 ngày HÔM NAY, rồi so với bản chụp gần nhất thuộc THÁNG TRƯỚC đã tích lũy được.

    GIỚI HẠN GIAI ĐOẠN ĐẦU: vừa triển khai nên CHƯA có dữ liệu tháng trước để so sánh — những tuần
    đầu sẽ tự dự phòng đọc receivable_detail (Supabase, đã có sẵn lịch sử) cho tới khi snapshot nội
    bộ tích đủ ít nhất 1 tháng, sau đó tự chuyển hẳn sang dùng snapshot Bravo, không cần sửa code.
    """
    from sqlalchemy import text

    rows = []
    latest_label = None
    prev_label = None
    key_suffix = None  # phần colon-free dùng cho alert_key — xem giải thích ở dòng gán alert_key
    try:
        # 14/07/2026: dùng _bravo_overdue_gt45_by_customer() riêng (không phải
        # get_bravo_receivables_snapshot()) — mốc >45 ngày của A1 độc lập với mốc hiển thị chung
        # (đã đổi sang 1-30/31-60/61-90/>90 ngày cùng ngày), xem docstring hàm đó.
        snap = _bravo_overdue_gt45_by_customer()
        by_customer = {r.customer_code: (r.customer_name, float(r.overdue_gt_45 or 0)) for r in snap}
        today_str = datetime.now().strftime("%Y-%m-%d")
        _save_debt_aging_snapshot([(code, name, amt) for code, (name, amt) in by_customer.items()])

        prev_date = _find_prev_month_snapshot_date(today_str)
        if not prev_date:
            raise RuntimeError("Chưa tích lũy đủ snapshot tháng trước (tính năng mới triển khai)")
        prev_snap = _get_debt_aging_snapshot(prev_date)
        latest_label = f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})"
        prev_label = prev_date
        key_suffix = today_str  # "YYYY-MM-DD" — không có dấu ":"
        for code, (name, amt) in by_customer.items():
            if amt <= 10000000:
                continue
            prev_amt = prev_snap.get(code, (None, 0.0))[1]
            if prev_amt == 0:
                rows.append((code, name, amt))
        rows.sort(key=lambda r: r[2], reverse=True)
        rows = rows[:10]
    except Exception as e:
        print(f"[ALERTS][aging_migration] Bravo lỗi/chưa đủ lịch sử ({e}) — dự phòng Supabase receivable_detail.")
        engine = _alert_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                latest, prev = _two_latest_periods(conn)
                if not latest or not prev:
                    print("[ALERTS][aging_migration] Chưa đủ 2 kỳ để so sánh.")
                    return
                latest_label, prev_label = latest, prev
                key_suffix = latest  # "M_YYYY" — không có dấu ":"
                sql = text('''
                    SELECT c.customer_code, c.customer_name, c.overdue_gt_45,
                           COALESCE(p.overdue_gt_45, 0) AS prev_gt45
                    FROM receivable_detail c
                    LEFT JOIN receivable_detail p
                           ON c.customer_code = p.customer_code AND p.period = :prev
                    WHERE c.period = :latest
                      AND c.overdue_gt_45 > 10000000
                      AND COALESCE(p.overdue_gt_45, 0) = 0
                    ORDER BY c.overdue_gt_45 DESC LIMIT 10
                ''')
                db_rows = conn.execute(sql, {"latest": latest, "prev": prev}).fetchall()
                rows = [(r[0], r[1], r[2]) for r in db_rows]
        except Exception as e2:
            print(f"[ALERTS][aging_migration] Lỗi cả 2 nguồn: {e2}")
            return

    if not rows:
        print("[ALERTS][aging_migration] Không có khách mới rơi vào nhóm >45 ngày.")
        return
    # 14/07/2026: alert_key dùng key_suffix (colon-free) thay vì latest_label trực tiếp —
    # latest_label nhánh Bravo có dạng "Tức thời (đến DD/MM/YYYY HH:MM)", CHỨA dấu ":" (giờ:phút),
    # phá vỡ alert_key.split(":") ở _highlight_group_key/_humanize_highlight (src/etl.py) —
    # phát hiện qua audit toàn repo, gây vỡ hiển thị + hỏng logic gộp nhóm "Điểm Nổi Bật".
    alert_key = f"aging_migration_gt45:{key_suffix}"
    top = rows[0][2]
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(top)):
        table = [[str(r[0]), r[1], format_vietnamese_money(r[2])] for r in rows]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO NỢ CHUYỂN NHÓM XẤU (>45 NGÀY)",
            severity="CRITICAL",
            summary=(f"Kỳ {latest_label}: các khách sau LẦN ĐẦU rơi vào nhóm nợ quá hạn >45 ngày "
                     f"(kỳ trước {prev_label} chưa có) — nguy cơ nợ xấu, cần thu hồi gấp."),
            table_headers=["Mã KH", "Tên KH", "Nợ >45 ngày"],
            table_rows=table,
            channels=("teams",),
            period=latest_label, region="Toàn quốc",
            issue=f"Khách hàng lần đầu rơi vào nhóm nợ quá hạn >45 ngày (kỳ trước {prev_label} chưa có) — nguy cơ nợ xấu"
        )
        record_alert_sent(alert_key, str(top))


# ---- Nhóm B: Tồn kho -------------------------------------------------------

def check_dead_stock_alert():
    """
    B2: Tồn "chết"/bán chậm — months_to_sell rất lớn + giá trị tồn cao (vốn đọng).

    CHỦ ĐỘNG GIỮ SUPABASE (không chuyển Bravo-first, 10/07/2026): khảo sát Bravo cho thấy CÓ bảng
    tồn kho (BRV_TheKho/BRV_TonKhoDK) nhưng số lượng nhập/xuất suy ra từ DebitAccount/CreditAccount
    (quy ước kế toán kép, cần đọc đúng mã tài khoản mới biết chiều tăng/giảm) — RỦI RO tính sai tồn
    kho hiện tại nếu suy đoán sai quy ước. BRV_TheKhoLot có cột ReceiptQuantity/IssueQuantity rõ
    ràng hơn nhưng chưa verify được số dư tồn kho tính ra khớp với số liệu tồn kho thực tế đã biết
    (khác hẳn công nợ — công thức TotalAmount-PaidAmount đã đối chiếu được số liệu thật trước khi
    dùng). Để lại xác minh kỹ hơn trước khi chuyển, tránh báo sai tồn kho ảnh hưởng quyết định nhập
    hàng.
    """
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    dead_months = float(_biz_threshold('dead_stock_months', 12.0))
    min_value = float(_biz_threshold('dead_stock_min_value', 50000000))
    try:
        with engine.connect() as conn:
            if not _supabase_table_exists(conn, "inventory"):
                print("[ALERTS][dead_stock] Bảng 'inventory' chưa có dữ liệu (chờ Excel/DNH) — bỏ qua.")
                return
            rows = conn.execute(text('''
                SELECT item_code, item_name, unit, closing_qty, closing_value, months_to_sell, channel
                FROM inventory
                WHERE months_to_sell >= :m AND closing_value > :v
                ORDER BY closing_value DESC LIMIT 10
            '''), {"m": dead_months, "v": min_value}).fetchall()
    except Exception as e:
        print(f"[ALERTS][dead_stock] Lỗi: {e}")
        return
    if not rows:
        print("[ALERTS][dead_stock] Không có mặt hàng tồn chết vượt ngưỡng.")
        return
    alert_key = "dead_stock_top10"
    top = rows[0].closing_value
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(top)):
        table = [[str(r.item_code), r.channel or "Không rõ", r.item_name, f"{r.closing_qty:,.0f}".replace(',', '.'),
                  format_vietnamese_money(r.closing_value), f"{r.months_to_sell:.1f} tháng"] for r in rows]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO TỒN KHO CHẾT / BÁN CHẬM",
            severity="WARNING",
            summary=(f"Các mặt hàng sau tồn kho đủ bán trên {dead_months:.0f} tháng và giá trị tồn lớn "
                     f"— vốn đang bị đọng, cân nhắc xả hàng/khuyến mãi."),
            table_headers=["Mã SKU", "Kênh", "Tên Hàng", "Tồn Kho", "Giá Trị Tồn", "Số Tháng Bán"],
            table_rows=table,
            channels=("teams",),
            period=datetime.now().strftime("%d/%m/%Y"), region="Toàn quốc",
            issue=f"Tồn kho bán chậm trên {dead_months:.0f} tháng, giá trị tồn đọng lớn — vốn bị đọng"
        )
        record_alert_sent(alert_key, str(top))


def check_near_expiry_alert():
    """
    B1: Hàng cận date / sắp hết hạn. TRẠNG THÁI: phòng thủ theo GAP DỮ LIỆU.
    Tồn kho theo lô (brvsx_thekholot) hiện chỉ có ItemLotCode + số lượng, KHÔNG có cột
    hạn dùng của lô. Cần bảng map lô -> hạn dùng (MfgDate/ExpiryDate) từ Bravo/DMS. Hàm tự
    dò cột hạn dùng gắn với tồn kho lúc chạy; nếu chưa có -> no-op + log rõ (không crash).

    XÁC NHẬN THÊM (10/07/2026): khảo sát trực tiếp Bravo (BRV_SanPham, BRV_TheKhoLot,
    BRV_TonKhoDKLot) cũng KHÔNG thấy cột hạn dùng/ExpiryDate nào — gap dữ liệu này không phải do
    thiếu ở Supabase mà do bản thân Bravo cũng chưa lưu thông tin hạn dùng theo lô. Không có nguồn
    nào để chuyển sang, kể cả Bravo.
    """
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    try:
        with engine.connect() as conn:
            # Dò cột hạn dùng trên các bảng tồn kho/thẻ kho lô (không tính bảng trả hàng)
            cols = conn.execute(text('''
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema='public'
                  AND (lower(table_name) LIKE '%thekho%' OR lower(table_name) LIKE '%tonkho%' OR table_name='inventory')
                  AND (lower(column_name) LIKE '%expir%' OR lower(column_name) LIKE '%handung%'
                       OR lower(column_name) LIKE '%han_dung%' OR lower(column_name) LIKE '%hsd%')
                LIMIT 1
            ''')).fetchone()
    except Exception as e:
        print(f"[ALERTS][near_expiry] Lỗi khi dò cột hạn dùng: {e}")
        return
    if not cols:
        print("[ALERTS][near_expiry] GAP DỮ LIỆU: tồn kho theo lô chưa có cột hạn dùng (ExpiryDate). "
              "Cần DNH bổ sung map lô->hạn dùng từ Bravo/DMS vào mart trước khi bật cảnh báo cận date. Bỏ qua (no-op).")
        return
    print(f"[ALERTS][near_expiry] Tìm thấy cột hạn dùng: {cols[0]}.{cols[1]} — cần hoàn thiện logic tính tồn theo lô còn hạn.")
    # Khi có cột: tính tồn hiện tại theo lô (SUM Receipt - Issue trên brvsx_thekholot) join hạn dùng,
    # cảnh báo lô còn < N tháng hết hạn mà còn tồn > 0. Hoàn thiện khi xác nhận khóa join lô với DNH.


# ---- Nhóm C: Doanh thu / khách hàng ----------------------------------------

def check_customer_churn_alert():
    """
    C1: Khách lớn (tháng trước mua nhiều) nhưng tháng mới nhất rớt mạnh — nguy cơ mất khách.
    Tính RIÊNG top 10 cho từng kênh OTC/ETC (không gộp trước khi xếp hạng/so ngưỡng).

    INNER JOIN với dms_khachhang/dmssx_khachhang để CHỈ tính khách hàng thật — xác nhận thực tế
    (08/07/2026) rằng brv_hoadonhdr/brvsx_hoadonhdr chứa nhiều "CustomerCode" KHÔNG phải khách
    hàng bán lẻ/ETC thật (mã nội bộ/công ty mẹ 'P000001', mã nhà cung cấp 'NCC*', mã chi phí nội
    bộ 'I000001'/'I000002'...) — nếu không lọc sẽ hiện nhầm các mã này như "khách hàng lớn" cần
    chăm sóc (đã thấy thực tế mã '1001136' 274 tỷ đồng/197 hóa đơn không khớp dim khách hàng nào).
    """
    # 14/07/2026: đổi sang query view gốc Bravo (vHoaDonTotal/vHoaDonETCTotal) thay vì tự ráp
    # SUM(h."TotalAmount") trực tiếp từ header — cùng lý do/cách làm với _period_revenue (đã sửa
    # 13/07/2026): công thức tự ráp thiếu trừ hàng trả lại, thiếu lọc Post_TheKho=1. Không còn
    # failover Postgres (view chỉ có ở Bravo, xem docstring _period_revenue trong src/etl.py).
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    drop_pct = float(_biz_threshold('customer_churn_drop_pct', 0.50))
    min_prev = float(_biz_threshold('customer_churn_min_prev', 50000000))
    params = {"min_prev": min_prev, "drop": drop_pct}

    try:
        engine = _get_bravo_engine()
        if engine is None:
            raise RuntimeError("Chưa cấu hình BRAVO_SQL_* — không có nguồn nào khác cho churn.")
        sql = text('''
            WITH cm AS (
                SELECT 'OTC' AS channel, v.CustomerCode AS cc, k.Name AS cname,
                       DATEFROMPARTS(YEAR(v.DocDate), MONTH(v.DocDate), 1) AS m, SUM(v.Amount9) AS rev
                FROM dbo.vHoaDonTotal v
                JOIN dbo.DMS_KhachHang k ON v.CustomerCode = k.Code
                GROUP BY v.CustomerCode, k.Name, DATEFROMPARTS(YEAR(v.DocDate), MONTH(v.DocDate), 1)
                UNION ALL
                SELECT 'ETC', v.CustomerCode, k.Name,
                       DATEFROMPARTS(YEAR(v.DocDate), MONTH(v.DocDate), 1), SUM(v.Amount9)
                FROM dbo.vHoaDonETCTotal v
                JOIN dbo.DMSSX_KhachHang k ON v.CustomerCode = k.Code
                GROUP BY v.CustomerCode, k.Name, DATEFROMPARTS(YEAR(v.DocDate), MONTH(v.DocDate), 1)
            ),
            agg AS (SELECT channel, cc, cname, m, SUM(rev) AS rev FROM cm GROUP BY channel, cc, cname, m),
            mranked AS (
                SELECT channel, m, ROW_NUMBER() OVER (PARTITION BY channel ORDER BY m DESC) AS rn
                FROM (SELECT DISTINCT channel, m FROM agg) d
            ),
            latest AS (SELECT channel, m FROM mranked WHERE rn = 1),
            prevm AS (SELECT channel, m FROM mranked WHERE rn = 2)
            SELECT a.channel, a.cc, a.cname,
                   COALESCE(cur.rev,0) AS cur_rev,
                   prevd.rev AS prev_rev,
                   l.m AS latest_month
            FROM (SELECT DISTINCT channel, cc, cname FROM agg) a
            JOIN prevm p ON p.channel = a.channel
            JOIN agg prevd ON prevd.cc=a.cc AND prevd.channel=a.channel AND prevd.m=p.m
            LEFT JOIN latest l ON l.channel=a.channel
            LEFT JOIN agg cur ON cur.cc=a.cc AND cur.channel=a.channel AND cur.m=l.m
            WHERE prevd.rev > :min_prev
              AND (prevd.rev - COALESCE(cur.rev,0)) / prevd.rev > :drop
            ORDER BY a.channel, prevd.rev DESC
        ''')
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        churn_data_day = _last_complete_data_day()
    except Exception as e:
        print(f"[ALERTS][churn] Lỗi: {e}")
        return
    if rows is None:
        rows = []
    if not rows:
        print("[ALERTS][churn] Không có khách lớn nào rớt doanh số vượt ngưỡng.")
        return

    for channel_label in ("OTC", "ETC"):
        channel_rows = [r for r in rows if r.channel == channel_label][:10]
        if not channel_rows:
            continue
        alert_key = f"customer_churn:{channel_label}"
        top = channel_rows[0].cc
        if should_send_alert(alert_key, cooldown_hours=24, current_value=str(top)):
            region_map = get_customer_regions_by_code([r.cc for r in channel_rows], channel_label)
            table = []
            for r in channel_rows:
                cur_rev = float(r.cur_rev); prev_rev = float(r.prev_rev)
                drop = (prev_rev - cur_rev) / prev_rev if prev_rev > 0 else 0
                table.append([str(r.cc), r.cname, region_map.get(r.cc, "Không rõ"), format_vietnamese_money(prev_rev),
                              format_vietnamese_money(cur_rev), f"-{drop*100:.0f}%"])
            send_alert_to_all_channels(
                alert_name=f"CẢNH BÁO KHÁCH HÀNG LỚN SỤT GIẢM ({channel_label}) — NGUY CƠ MẤT KHÁCH",
                severity="WARNING",
                summary=f"Các khách hàng lớn kênh {channel_label} sau có doanh số tháng mới nhất rớt mạnh so với tháng trước — cần chăm sóc ngay.",
                table_headers=["Mã KH", "Tên KH", "Vùng", "Doanh Số Tháng Trước", "Doanh Số Tháng Này", "Sụt Giảm"],
                table_rows=table,
                channels=("teams",),
                period=_month_period_label(channel_rows[0].latest_month, churn_data_day),
                channel=channel_label, region="Toàn quốc",
                issue=f"Khách hàng lớn kênh {channel_label} có doanh số tháng mới nhất sụt giảm mạnh so với tháng trước — nguy cơ mất khách"
            )
            record_alert_sent(alert_key, str(top))


def check_revenue_concentration_alert():
    """
    C2: Rủi ro tập trung — top N khách chiếm > X% tổng doanh thu tháng mới nhất.
    Tính RIÊNG cho từng kênh OTC/ETC (không gộp trước khi tính tỷ trọng).

    INNER JOIN với dms_khachhang/dmssx_khachhang để CHỈ tính khách hàng thật trong cả tử số (top
    N) lẫn mẫu số (tổng doanh thu kênh) — cùng lý do đã xác nhận thực tế ở check_customer_churn_alert
    (mã nội bộ/NCC lẫn trong CustomerCode của brv_hoadonhdr/brvsx_hoadonhdr).
    """
    # 14/07/2026: đổi sang query view gốc Bravo (vHoaDonTotal/vHoaDonETCTotal), cùng lý do/cách
    # làm với check_customer_churn_alert/_period_revenue. Không còn failover Postgres.
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    top_n = int(_biz_threshold('concentration_top_n', 3))
    threshold = float(_biz_threshold('concentration_pct', 0.50))
    params = {"n": top_n}

    try:
        engine = _get_bravo_engine()
        if engine is None:
            raise RuntimeError("Chưa cấu hình BRAVO_SQL_* — không có nguồn nào khác cho concentration.")
        # TOP (:n) cần ngoặc vì n là bind param, không phải literal.
        sql = text('''
            WITH mx AS (
                SELECT 'OTC' AS channel, DATEFROMPARTS(YEAR(MAX(DocDate)), MONTH(MAX(DocDate)), 1) AS m FROM dbo.vHoaDonTotal
                UNION ALL
                SELECT 'ETC', DATEFROMPARTS(YEAR(MAX(DocDate)), MONTH(MAX(DocDate)), 1) FROM dbo.vHoaDonETCTotal
            ),
            cm AS (
                SELECT 'OTC' AS channel, v.CustomerCode AS cc, SUM(v.Amount9) AS rev
                FROM dbo.vHoaDonTotal v
                JOIN dbo.DMS_KhachHang k ON v.CustomerCode = k.Code
                WHERE DATEFROMPARTS(YEAR(v.DocDate), MONTH(v.DocDate), 1) = (SELECT m FROM mx WHERE channel='OTC')
                GROUP BY v.CustomerCode
                UNION ALL
                SELECT 'ETC', v.CustomerCode, SUM(v.Amount9)
                FROM dbo.vHoaDonETCTotal v
                JOIN dbo.DMSSX_KhachHang k ON v.CustomerCode = k.Code
                WHERE DATEFROMPARTS(YEAR(v.DocDate), MONTH(v.DocDate), 1) = (SELECT m FROM mx WHERE channel='ETC')
                GROUP BY v.CustomerCode
            ),
            agg AS (SELECT channel, cc, SUM(rev) AS rev FROM cm GROUP BY channel, cc)
            SELECT agg.channel,
                (SELECT COALESCE(SUM(rev),0) FROM (SELECT TOP (:n) rev FROM agg a2 WHERE a2.channel=agg.channel ORDER BY rev DESC) t) AS top_sum,
                (SELECT COALESCE(SUM(rev),0) FROM agg a3 WHERE a3.channel=agg.channel) AS total_sum,
                mx.m AS channel_month
            FROM agg JOIN mx ON mx.channel = agg.channel
            GROUP BY agg.channel, mx.m
        ''')
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        concentration_data_day = _last_complete_data_day()
    except Exception as e:
        print(f"[ALERTS][concentration] Lỗi: {e}")
        return
    if rows is None:
        rows = []

    for r in rows:
        channel_label = r.channel
        ratio = concentration_ratio(r.top_sum, r.total_sum)
        if ratio is None:
            continue
        print(f"[ALERTS][concentration][{channel_label}] Top {top_n} khách chiếm {ratio*100:.1f}% doanh thu (ngưỡng {threshold*100:.0f}%).")
        if ratio > threshold:
            alert_key = f"revenue_concentration:{channel_label}"
            if should_send_alert(alert_key, cooldown_hours=48, current_value=str(round(ratio, 4))):
                send_alert_to_all_channels(
                    alert_name=f"CẢNH BÁO RỦI RO TẬP TRUNG DOANH THU ({channel_label})",
                    severity="WARNING",
                    summary=(f"Top {top_n} khách hàng kênh {channel_label} chiếm {ratio*100:.1f}% tổng doanh thu kênh này tháng mới nhất "
                             f"(vượt {threshold*100:.0f}%) — phụ thuộc quá nhiều vào ít khách, rủi ro nếu mất 1 khách."),
                    table_headers=[f"Doanh thu Top {top_n}", "Tổng doanh thu", "Tỷ trọng"],
                    table_rows=[[format_vietnamese_money(r.top_sum), format_vietnamese_money(r.total_sum), f"{ratio*100:.1f}%"]],
                    channels=("teams",),
                    period=_month_period_label(r.channel_month, concentration_data_day),
                    channel=channel_label, region="Toàn quốc",
                    issue=f"Top {top_n} khách hàng kênh {channel_label} chiếm {ratio*100:.1f}% tổng doanh thu kênh này — rủi ro tập trung quá cao"
                )
                record_alert_sent(alert_key, str(round(ratio, 4)))


# ---- Nhóm E: Hàng trả về ---------------------------------------------------

def check_return_rate_alert():
    """E: Tỷ lệ giá trị hàng trả về (brvsx_tralai) / doanh số ETC tháng mới nhất vượt ngưỡng."""
    from sqlalchemy import text
    from src.database import run_with_failover
    threshold = float(_biz_threshold('return_rate_pct', 0.05))

    def _pg(conn):
        sql = text('''
            WITH mx AS (SELECT DATE_TRUNC('month', MAX("DocDate"::date)) AS m FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE),
            ret AS (
                SELECT COALESCE(SUM("Amount9"),0) AS v FROM brvsx_tralai
                WHERE "IsActive"=TRUE AND DATE_TRUNC('month',"DocDate"::timestamp) = (SELECT m FROM mx)
            ),
            sales AS (
                SELECT COALESCE(SUM("TotalAmount"),0) AS v FROM brvsx_hoadonhdr
                WHERE "IsActive"=TRUE AND DATE_TRUNC('month',"DocDate"::timestamp) = (SELECT m FROM mx)
            )
            SELECT (SELECT v FROM ret), (SELECT v FROM sales), (SELECT m FROM mx)
        ''')
        return conn.execute(sql).fetchone()

    def _mssql(conn):
        sql = text('''
            WITH mx AS (SELECT DATEFROMPARTS(YEAR(MAX("DocDate")), MONTH(MAX("DocDate")), 1) AS m FROM dbo.BRVSX_HoaDonHdr WHERE "IsActive"=1),
            ret AS (
                SELECT COALESCE(SUM("Amount9"),0) AS v FROM dbo.BRVSX_TraLai
                WHERE "IsActive"=1 AND DATEFROMPARTS(YEAR("DocDate"), MONTH("DocDate"), 1) = (SELECT m FROM mx)
            ),
            sales AS (
                SELECT COALESCE(SUM("TotalAmount"),0) AS v FROM dbo.BRVSX_HoaDonHdr
                WHERE "IsActive"=1 AND DATEFROMPARTS(YEAR("DocDate"), MONTH("DocDate"), 1) = (SELECT m FROM mx)
            )
            SELECT (SELECT v FROM ret), (SELECT v FROM sales), (SELECT m FROM mx)
        ''')
        return conn.execute(sql).fetchone()

    try:
        row = run_with_failover(_pg, _mssql, label="return_rate")
    except Exception as e:
        print(f"[ALERTS][return_rate] Lỗi: {e}")
        return
    if row is None:
        print("[ALERTS][return_rate] Không lấy được dữ liệu (Supabase và Bravo đều không dùng được).")
        return
    rate = return_rate(row[0], row[1])
    if rate is None:
        print("[ALERTS][return_rate] Chưa đủ dữ liệu (doanh số ETC = 0) để tính tỷ lệ trả hàng.")
        return
    print(f"[ALERTS][return_rate] Tỷ lệ trả hàng ETC = {rate*100:.2f}% (ngưỡng {threshold*100:.0f}%).")
    if rate > threshold:
        alert_key = "etc_return_rate"
        if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(rate, 4))):
            # row[2] (mốc tháng) có thể là chuỗi 'YYYY-MM-DD' khi run_with_failover trả về từ
            # nhánh Bravo (driver ODBC cũ trả cột date dạng chuỗi, không phải datetime.date gốc —
            # xác nhận thực tế 13/07/2026, cùng lỗi đã sửa ở _last_complete_data_day và nơi khác).
            m_val = row[2]
            if m_val and not hasattr(m_val, "strftime"):
                m_val = datetime.strptime(str(m_val)[:10], "%Y-%m-%d")
            period_m = m_val.strftime('%m/%Y') if m_val else None
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO TỶ LỆ HÀNG TRẢ VỀ CAO (ETC)",
                severity="WARNING",
                summary=(f"Tỷ lệ giá trị hàng trả về / doanh số ETC tháng mới nhất đạt {rate*100:.2f}% "
                         f"(vượt {threshold*100:.0f}%) — nghi vấn chất lượng lô/quá hạn/sai đơn."),
                table_headers=["Giá trị trả về", "Doanh số ETC", "Tỷ lệ trả"],
                table_rows=[[format_vietnamese_money(row[0]), format_vietnamese_money(row[1]), f"{rate*100:.2f}%"]],
                channels=("teams",),
                period=period_m, channel="ETC", region="Toàn quốc",
                issue=f"Tỷ lệ giá trị hàng trả về/doanh số ETC đạt {rate*100:.2f}%, vượt ngưỡng — nghi vấn chất lượng lô/quá hạn/sai đơn"
            )
            record_alert_sent(alert_key, str(round(rate, 4)))


# ---- Nhóm F: KPI / nhân sự -------------------------------------------------

def check_zero_sales_rep_alert():
    """
    F: Nhân viên có chỉ tiêu nhưng doanh số = 0 trong kỳ (nghỉ ngầm / vấn đề địa bàn).
    Ưu tiên tính TỨC THỜI từ Bravo (get_bravo_kpi_tdv_snapshot, chỉ TDV/QLV, 10/07/2026); Bravo lỗi
    thì dự phòng đọc kpi_summary (Supabase, đủ mọi chức danh) như trước.
    """
    from sqlalchemy import text
    period_label = None
    rows = []
    try:
        snapshot = get_bravo_kpi_tdv_snapshot(position_codes=('TDV', 'QLV'))
        period_label = f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})"
        filtered = [r for r in snapshot if r.month_sale_target > 10000000 and (r.month_sale_amount or 0) == 0]
        filtered.sort(key=lambda r: r.month_sale_target, reverse=True)
        # 14/07/2026: dùng đúng position_code thật từ get_bravo_kpi_tdv_snapshot (mới thêm) thay
        # vì heuristic cũ "TDV nếu month_sale_percent is not None else QLV" — heuristic này LUÔN
        # cho ra "TDV" vì filtered đã lọc month_sale_target>0, nên month_sale_percent không bao
        # giờ None (kể cả với nhân sự QLV thật), nhánh "QLV" không bao giờ chạy tới.
        rows = [(r.employee_code, r.employee_name, r.area_code, r.position_code, r.month_sale_target)
                for r in filtered[:10]]
    except Exception as e:
        print(f"[ALERTS][zero_sales] Bravo lỗi ({e}) — dự phòng Supabase kpi_summary.")
        engine = _alert_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                rows = conn.execute(text('''
                    SELECT employee_code, employee_name, area_code, position_code, month_sale_target
                    FROM kpi_summary
                    WHERE month_sale_target > 10000000 AND COALESCE(month_sale_amount,0) = 0
                    ORDER BY month_sale_target DESC LIMIT 10
                ''')).fetchall()
                period_label = _month_period_label(_last_complete_data_day(), _last_complete_data_day())
        except Exception as e2:
            print(f"[ALERTS][zero_sales] Lỗi cả 2 nguồn: {e2}")
            return
    if not rows:
        print("[ALERTS][zero_sales] Không có nhân sự nào doanh số = 0.")
        return
    alert_key = "zero_sales_rep"
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(len(rows))):
        regions_seen = set()
        table = []
        for r in rows:
            region_label = normalize_region_label(r[2])
            regions_seen.add(region_label)
            table.append([str(r[0]), r[1], region_label, str(r[3]), format_vietnamese_money(r[4])])
        header_region = regions_seen.pop() if len(regions_seen) == 1 else "Nhiều miền"
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO NHÂN SỰ DOANH SỐ BẰNG 0",
            severity="WARNING",
            summary="Các nhân sự sau có chỉ tiêu nhưng doanh số kỳ này = 0 — cần kiểm tra tình trạng làm việc/địa bàn.",
            table_headers=["Mã NV", "Tên NV", "Vùng", "Chức danh", "Chỉ tiêu"],
            table_rows=table,
            channels=("teams",),
            period=period_label, region=header_region,
            issue="Nhân sự có chỉ tiêu doanh số nhưng đạt 0 trong kỳ — nghi ngờ nghỉ ngầm/vấn đề địa bàn"
        )
        record_alert_sent(alert_key, str(len(rows)))


def kpi_sales_force_risk_reasons(position_code, month_pct, quarter_pct, year_pct,
                                  risk_map, quarter_floor, year_floor):
    """
    Pure helper (unit-test được, không đụng DB): trả về list lý do vi phạm ngưỡng KPI
    theo QĐ 0429-2/QĐ-HĐQT.25 (khối OTC miền Nam) cho 1 nhân sự. Rỗng nếu không vi phạm gì.
    """
    reasons = []
    role_threshold = risk_map.get(position_code)
    if role_threshold is not None and month_pct is not None and month_pct <= role_threshold:
        reasons.append(
            f"Nguy cơ chấm dứt HĐLĐ (tháng {month_pct*100:.0f}% <= {role_threshold*100:.0f}%, mới tính 1 tháng)")
    if quarter_pct is not None and quarter_pct < quarter_floor:
        reasons.append(f"Mất thưởng quý (quý {quarter_pct*100:.0f}% < {quarter_floor*100:.0f}%)")
    if year_pct is not None and year_pct < year_floor:
        reasons.append(f"Thưởng năm về sàn 0% (năm {year_pct*100:.0f}% < {year_floor*100:.0f}%)")
    return reasons


def check_kpi_sales_force_risk_alert():
    """
    F2: Cảnh báo rủi ro theo ngưỡng chính sách thu nhập OTC MIỀN NAM (QĐ 0429-2/QĐ-HĐQT.25):
    nguy cơ chấm dứt HĐLĐ, mất thưởng quý, thưởng năm rơi về sàn — đọc thresholds.kpi_sales_force.

    ƯU TIÊN BRAVO (10/07/2026): FACT_TongHopKhachHang không có cột quý riêng, nhưng giữ lịch sử
    snapshot HÀNG THÁNG (01/2025 tới nay) — đủ để TÁI TẠO % quý/năm bằng cách cộng dồn các tháng
    liên quan (xem get_bravo_kpi_quarter_year_snapshot). RỦI RO CAO HƠN các cảnh báo công nợ/KPI
    tháng đã chuyển: KHÔNG có số liệu quý/năm "đã biết đúng" nào để đối chiếu (khác công nợ, đã so
    khớp được với số liệu quan sát trước đó) — dùng cho cảnh báo SỚM, KHÔNG dùng làm căn cứ chính
    thức cho quyết định chấm dứt HĐLĐ mà không xác nhận lại với DNH. Bravo lỗi thì dự phòng
    kpi_summary (Supabase) như cũ. CHỈ áp dụng TDV/QLV/CS/TK có trên Bravo — vai trò nào trong
    risk_map KHÔNG có trên Bravo (nếu có) sẽ tự vắng mặt khỏi kết quả Bravo, không crash.

    GIỚI HẠN CẦN BIẾT:
      - Chính sách yêu cầu "2 tháng liên tiếp" dưới ngưỡng mới đủ điều kiện xem xét chấm dứt HĐLĐ,
        nhưng kpi_summary chỉ là snapshot hiện tại (không lưu lịch sử theo tháng) -> hàm này chỉ
        kiểm tra được THÁNG HIỆN TẠI, là cảnh báo sớm chứ KHÔNG phải xác nhận chính thức đủ điều
        kiện chấm dứt HĐLĐ.
      - Ánh xạ vai trò <-> position_code (CS = TDV chợ sỉ, TK = Trưởng kênh MT) suy luận từ số
        lượng nhân viên thực tế (dim_nhanvien, AreaCode='MN'), chưa có bảng chú giải chính thức
        từ HR.
      - Lọc area_code LIKE 'MN%' vì đây là chính sách MIỀN NAM; tiền tố này là giả định dựa theo
        quy ước quan sát được (dim_nhanvien.AreaCode='MN', kpi_summary.area_code='MB2' ở miền Bắc)
        — sửa lại filter nếu DNH xác nhận tiền tố khác khi ETL đổ dữ liệu miền Nam vào bảng này.
    """
    from sqlalchemy import text

    try:
        cfg = load_config()['thresholds']['kpi_sales_force']
        risk_map = {str(k): float(v) for k, v in cfg['contract_risk_pct'].items()}
        quarter_floor = float(cfg['quarter_zero_bonus_pct'])
        year_floor = float(cfg['year_floor_pct'])
    except Exception as e:
        print(f"[ALERTS][kpi_sales_force] Chưa cấu hình đủ thresholds.kpi_sales_force trong config.yaml: {e}")
        return

    rows = []
    kpi_force_data_day = None
    try:
        roles = tuple(risk_map.keys())
        month_snap = {r.employee_code: r for r in get_bravo_kpi_tdv_snapshot(position_codes=roles)}
        qy_snap = get_bravo_kpi_quarter_year_snapshot(roles)
        # position_code không có sẵn trong 2 snapshot trên (đều đã filter theo roles rồi) — dò lại
        # qua DIM_NhanVien 1 lần để gắn đúng position_code cho từng dòng kết quả.
        from src.database import _get_bravo_engine
        bravo_engine = _get_bravo_engine()
        pos_ph = ",".join(f"'{p}'" for p in roles)
        with bravo_engine.connect() as conn:
            pos_rows = conn.execute(text(f'''
                SELECT [EmployeeCode], [PositionCode] FROM [DIM_NhanVien]
                WHERE [PositionCode] IN ({pos_ph}) AND ([IsDuplicate] IS NULL OR [IsDuplicate] = 0)
            ''')).fetchall()
        pos_map = {r[0]: r[1] for r in pos_rows}
        kpi_force_data_day = datetime.now()
        for emp_code, m in month_snap.items():
            area = m.area_code or ""
            if not area.upper().startswith("MN"):
                continue
            pos = pos_map.get(emp_code)
            if pos not in risk_map:
                continue
            qy = qy_snap.get(emp_code)
            rows.append((emp_code, m.employee_name, area, pos, m.month_sale_percent,
                          qy.quarter_sale_percent if qy else None, qy.year_sale_percent if qy else None))
    except Exception as e:
        print(f"[ALERTS][kpi_sales_force] Bravo lỗi ({e}) — dự phòng Supabase kpi_summary.")
        engine = _alert_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                rows = conn.execute(text('''
                    SELECT employee_code, employee_name, area_code, position_code,
                           month_sale_percent, quarter_sale_percent, year_sale_percent
                    FROM kpi_summary
                    WHERE position_code = ANY(:roles)
                      AND area_code LIKE 'MN%'
                      AND COALESCE(month_sale_target, 0) > 0
                '''), {"roles": list(risk_map.keys())}).fetchall()
                kpi_force_data_day = _last_complete_data_day()
        except Exception as e2:
            print(f"[ALERTS][kpi_sales_force] Lỗi cả 2 nguồn: {e2}")
            return

    if not rows:
        print("[ALERTS][kpi_sales_force] Không có dòng nào khớp (area_code LIKE 'MN%' + vai trò đã map) "
              "— nhiều khả năng do chưa có dữ liệu miền Nam khớp vai trò (gap dữ liệu đã biết).")
        return

    at_risk = []
    for emp_code, emp_name, area, pos, m_pct, q_pct, y_pct in rows:
        reasons = kpi_sales_force_risk_reasons(pos, m_pct, q_pct, y_pct, risk_map, quarter_floor, year_floor)
        if reasons:
            at_risk.append((emp_code, emp_name, area, pos, m_pct, q_pct, y_pct, "; ".join(reasons)))

    if not at_risk:
        print("[ALERTS][kpi_sales_force] Không nhân sự miền Nam nào vi phạm ngưỡng KPI hiện tại.")
        return

    at_risk.sort(key=lambda x: (x[4] if x[4] is not None else 1.0))
    alert_key = "kpi_sales_force_risk"
    current_value = f"{len(at_risk)}:{at_risk[0][0]}"
    if should_send_alert(alert_key, cooldown_hours=24, current_value=current_value):
        table = [[
            str(emp_code), emp_name, pos,
            f"{m_pct*100:.0f}%" if m_pct is not None else "—",
            f"{q_pct*100:.0f}%" if q_pct is not None else "—",
            f"{y_pct*100:.0f}%" if y_pct is not None else "—",
            reason,
        ] for emp_code, emp_name, area, pos, m_pct, q_pct, y_pct, reason in at_risk[:10]]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO RỦI RO KPI KHỐI OTC MIỀN NAM (QĐ 0429-2)",
            severity="WARNING",
            summary=(f"{len(at_risk)} nhân sự OTC miền Nam đang dưới ít nhất 1 ngưỡng KPI theo QĐ 0429-2. "
                     f"Ngưỡng 'nguy cơ chấm dứt HĐLĐ' mới kiểm tra được THÁNG HIỆN TẠI, chưa xác nhận đủ "
                     f"điều kiện chính thức '2 tháng liên tiếp' (thiếu lịch sử theo tháng)."),
            table_headers=["Mã NV", "Tên NV", "Vai trò", "% Tháng", "% Quý", "% Năm", "Cảnh báo"],
            table_rows=table,
            channels=("teams",),
            period=_month_period_label(kpi_force_data_day, kpi_force_data_day), channel="OTC", region="Miền Nam",
            issue=f"{len(at_risk)} nhân sự vi phạm ít nhất 1 ngưỡng KPI theo QĐ 0429-2 (nguy cơ chấm dứt HĐLĐ/mất thưởng)"
        )
        record_alert_sent(alert_key, current_value)


def check_daily_kpi_pace_alert():
    """
    Nhịp KPI theo NGÀY của từng TDV: doanh số phát sinh TRONG NGÀY / chỉ tiêu THÁNG của chính TDV
    đó — <3% Đỏ, 3%-<4% Vàng, >=4% Xanh (nhịp ~4%/ngày khớp đủ chỉ tiêu qua ~25 ngày làm việc).

    LƯU Ý QUAN TRỌNG (phát hiện thực tế khi backtest 57 ngày làm việc 05-07/2026): doanh số bán
    buôn dược phẩm đến theo TỪNG ĐƠN LỚN không đều, KHÔNG rải đều 1/25 chỉ tiêu mỗi ngày như giả
    định ban đầu — trung bình 39.7/49 TDV (81%) đã ở mức Đỏ NGAY CẢ VÀO NGÀY KINH DOANH BÌNH
    THƯỜNG (thấp nhất quan sát được: 23/49, cao nhất 49/49). Vì vậy ngưỡng ">=5 người Đỏ" gần như
    LUÔN đúng — đã trao đổi lại và CHỐT: giữ nguyên ngưỡng 5 nhưng đổi bản chất từ "cảnh báo bất
    thường" (WARNING) sang "báo cáo tóm tắt hàng ngày" (INFO, kèm đầy đủ số liệu Đỏ/Vàng/Xanh) —
    không dùng ngưỡng số người Đỏ này để suy luận mức độ nghiêm trọng.

    Chủ nhật LUÔN 100% Đỏ (10/10 Chủ nhật quan sát được đều 49/49 — công ty không kinh doanh ngày
    này) nên KHÔNG chạy report vào Chủ nhật, tránh gửi 1 báo cáo vô nghĩa mỗi tuần.

    ƯU TIÊN BRAVO (10/07/2026): query nhiều JOIN đã dịch sang T-SQL (brv_hoadonct/hoadonhdr/
    dim_nhanvien/trạng thái duyệt/hóa đơn điện tử), chỉ tiêu tháng lấy qua FACT_TongHopKhachHang
    (giống get_bravo_kpi_tdv_snapshot) — đã kiểm chứng bảng/cột tồn tại + chạy thật trước khi ghép.
    Bravo lỗi thì dự phòng nguyên vẹn logic Supabase cũ.

    GIỚI HẠN DỮ LIỆU (đã xác minh trực tiếp trên Supabase 08/07/2026, ÁP DỤNG CHO NHÁNH DỰ PHÒNG
    SUPABASE — nhánh Bravo chính KHÔNG còn bị giới hạn miền Bắc, xem bên dưới):
      - CHỈ khả thi kênh OTC — brvsx_hoadonhdr (ETC) không có cột nhân viên nào trên hóa đơn.
      - Chỉ tính TDV bắc cầu được brv_hoadonhdr.EmpDMSCode -> dim_nhanvien.DMSId ->
        dim_nhanvien.EmployeeCode -> kpi_summary.employee_code (50/58 TDV có chỉ tiêu hiện bắc
        cầu được — verify trực tiếp, KHÔNG suy đoán; EmpDMSCode KHÔNG khớp thẳng employee_code).
      - kpi_summary hiện 100% area_code miền Bắc (gap dữ liệu đã biết, xem flag
        kpi_sales_force_risk_check) -> nhánh dự phòng này chỉ áp dụng thực tế cho TDV miền Bắc.

    CẢI THIỆN KHI DÙNG BRAVO (10/07/2026): FACT_TongHopKhachHang có đủ TDV mọi miền (không chỉ
    Bắc) — xác nhận thực tế chạy ra 146 TDV đủ Bắc/Trung/Nam, nhiều hơn hẳn 50 TDV giới hạn miền
    Bắc của nhánh Supabase cũ. Giới hạn "chỉ OTC" vẫn còn (ETC vẫn không có cột nhân viên trên Bravo).
    """
    from sqlalchemy import text
    import types

    red_pct = float(_biz_threshold('kpi_pace_red_pct', 3.0))
    yellow_pct = float(_biz_threshold('kpi_pace_yellow_pct', 4.0))
    red_alert_count = int(_biz_threshold('kpi_pace_red_alert_count', 5))

    target_day = None
    rows = []
    try:
        from src.database import _get_bravo_engine
        bravo_engine = _get_bravo_engine()
        if bravo_engine is None:
            raise RuntimeError("Không có Bravo engine")
        with bravo_engine.connect() as conn:
            # Dùng ngày LIỀN TRƯỚC ngày mới nhất có dữ liệu — cùng lý do đã ghi ở bản Supabase cũ
            # (ngày mới nhất luôn có thể chưa đồng bộ xong).
            overall_max_row = conn.execute(text(
                'SELECT MAX([DocDate]) FROM [BRV_HoaDonHdr] WHERE [IsActive]=1'
            )).fetchone()
            overall_max = overall_max_row[0] if overall_max_row else None
            if not overall_max:
                print("[ALERTS][kpi_pace] Chưa có dữ liệu hóa đơn OTC để tính nhịp KPI.")
                return
            overall_max_str = overall_max.strftime("%Y-%m-%d") if hasattr(overall_max, "strftime") else str(overall_max)

            target_row = conn.execute(text(
                'SELECT MAX([DocDate]) FROM [BRV_HoaDonHdr] WHERE [IsActive]=1 AND [DocDate] < :overall_max'
            ), {"overall_max": overall_max_str}).fetchone()
            target_raw = target_row[0] if target_row else None
            if not target_raw:
                print("[ALERTS][kpi_pace] Chưa đủ 2 ngày dữ liệu để xác định ngày đã đồng bộ xong — bỏ qua.")
                return
            target_day = target_raw if hasattr(target_raw, "strftime") else datetime.strptime(str(target_raw)[:10], "%Y-%m-%d").date()
            if target_day.weekday() == 6:  # Chủ nhật — luôn 100% Đỏ (không kinh doanh), bỏ qua
                print(f"[ALERTS][kpi_pace] Ngày {target_day} là Chủ nhật — không kinh doanh, bỏ qua report.")
                return
            target_day_str = target_day.strftime("%Y-%m-%d")

            bravo_rows = conn.execute(text('''
                WITH daily_sales AS (
                    SELECT n.[EmployeeCode] AS employee_code,
                           SUM(CASE WHEN c.[CTKM] IS NULL OR c.[CTKM] = '' THEN c.[Amount9] ELSE 0 END) AS day_rev
                    FROM [BRV_HoaDonCt] c
                    JOIN [BRV_HoaDonHdr] h ON c.[Stt] = h.[Stt]
                    JOIN [DIM_NhanVien] n ON h.[EmpDMSCode] = n.[DMSId]
                    LEFT JOIN [BRV_TrangThaiDuyet] d ON h.[DocStatus] = d.[DocStatusKey]
                    LEFT JOIN [BRV_TrangThaiHoaDon] e ON h.[EInvoiceStatus] = e.[EInvoiceStatusKey]
                    WHERE h.[IsActive] = 1 AND h.[IsHC] = 0
                      AND (d.[IsCancelled] IS NULL OR d.[IsCancelled] = 0)
                      AND (e.[IsCancelled] IS NULL OR e.[IsCancelled] = 0)
                      AND d.[Post_TheKho] = 1
                      AND h.[DocDate] = :target_day
                    GROUP BY n.[EmployeeCode]
                ),
                tdv_target AS (
                    SELECT DISTINCT [EmployeeCode], [AreaCode], [MonthSaleTarget]
                    FROM [FACT_TongHopKhachHang]
                    WHERE [SaveDate] = (SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang])
                )
                SELECT n.[EmployeeCode] AS employee_code, n.[Name] AS employee_name, t.[AreaCode] AS area_code,
                       t.[MonthSaleTarget] AS month_sale_target, ISNULL(ds.day_rev, 0) AS day_rev
                FROM tdv_target t
                JOIN [DIM_NhanVien] n ON t.[EmployeeCode] = n.[EmployeeCode]
                LEFT JOIN daily_sales ds ON ds.employee_code = t.[EmployeeCode]
                WHERE n.[PositionCode] = 'TDV' AND (n.[IsDuplicate] IS NULL OR n.[IsDuplicate] = 0)
                  AND t.[MonthSaleTarget] > 0
            '''), {"target_day": target_day_str}).fetchall()
        rows = [types.SimpleNamespace(
            employee_code=r.employee_code, employee_name=r.employee_name, area_code=r.area_code,
            month_sale_target=float(r.month_sale_target or 0), day_rev=float(r.day_rev or 0))
            for r in bravo_rows]
    except Exception as e:
        print(f"[ALERTS][kpi_pace] Bravo lỗi ({e}) — dự phòng Supabase.")
        engine = _alert_engine()
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                overall_max_row = conn.execute(text(
                    'SELECT MAX("DocDate"::date) FROM brv_hoadonhdr WHERE "IsActive"=TRUE'
                )).fetchone()
                overall_max = overall_max_row[0] if overall_max_row else None
                if not overall_max:
                    print("[ALERTS][kpi_pace] Chưa có dữ liệu hóa đơn OTC để tính nhịp KPI.")
                    return

                target_row = conn.execute(text(
                    'SELECT MAX("DocDate"::date) FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "DocDate"::date < :overall_max'
                ), {"overall_max": overall_max}).fetchone()
                target_day = target_row[0] if target_row else None
                if not target_day:
                    print("[ALERTS][kpi_pace] Chưa đủ 2 ngày dữ liệu để xác định ngày đã đồng bộ xong — bỏ qua.")
                    return
                if target_day.weekday() == 6:
                    print(f"[ALERTS][kpi_pace] Ngày {target_day} là Chủ nhật — không kinh doanh, bỏ qua report.")
                    return

                rows = conn.execute(text('''
                    WITH daily_sales AS (
                        SELECT n."EmployeeCode" AS employee_code,
                               SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS day_rev
                        FROM brv_hoadonct c
                        JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
                        JOIN dim_nhanvien n ON h."EmpDMSCode" = n."DMSId"
                        LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
                        LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
                        WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
                          AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
                          AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
                          AND d."Post_TheKho" = TRUE
                          AND h."DocDate"::date = :target_day
                        GROUP BY n."EmployeeCode"
                    )
                    SELECT k.employee_code, k.employee_name, k.area_code, k.month_sale_target,
                           COALESCE(ds.day_rev, 0) AS day_rev
                    FROM kpi_summary k
                    LEFT JOIN daily_sales ds ON ds.employee_code = k.employee_code
                    WHERE k.position_code = 'TDV' AND COALESCE(k.month_sale_target,0) > 0
                '''), {"target_day": target_day}).fetchall()
        except Exception as e2:
            print(f"[ALERTS][kpi_pace] Lỗi cả 2 nguồn: {e2}")
            return

    if not rows:
        print("[ALERTS][kpi_pace] Không có TDV nào (position_code='TDV', có chỉ tiêu tháng) để tính nhịp KPI.")
        return

    reds, yellows, greens = [], [], []
    for r in rows:
        pct = (float(r.day_rev) / float(r.month_sale_target)) * 100 if r.month_sale_target else 0.0
        if pct < red_pct:
            reds.append((r, pct))
        elif pct < yellow_pct:
            yellows.append((r, pct))
        else:
            greens.append((r, pct))

    print(f"[ALERTS][kpi_pace] Ngày {target_day}: Đỏ {len(reds)} / Vàng {len(yellows)} / Xanh {len(greens)} "
          f"(tổng {len(rows)} TDV, ngưỡng gửi report: Đỏ >={red_alert_count}).")

    if len(reds) < red_alert_count:
        return

    alert_key = f"kpi_daily_pace_red:{target_day}"
    if should_send_alert(alert_key, cooldown_hours=20, current_value=str(len(reds))):
        reds.sort(key=lambda x: x[1])
        regions_seen = set()
        table = []
        for r, pct in reds[:15]:
            region_label = normalize_region_label(r.area_code)
            regions_seen.add(region_label)
            table.append([str(r.employee_code), r.employee_name, region_label,
                          format_vietnamese_money(r.day_rev), format_vietnamese_money(r.month_sale_target),
                          f"{pct:.1f}%"])
        header_region = regions_seen.pop() if len(regions_seen) == 1 else "Nhiều miền"
        more_note = f" (hiển thị 15/{len(reds)} TDV mức Đỏ thấp nhất)" if len(reds) > 15 else ""
        send_alert_to_all_channels(
            alert_name="BÁO CÁO NHỊP KPI NGÀY (TDV)",
            severity="INFO",
            summary=(f"Nhịp KPI ngày {target_day.strftime('%d/%m/%Y')}: "
                     f"Đỏ {len(reds)} · Vàng {len(yellows)} · Xanh {len(greens)} (/{len(rows)} TDV)."
                     f"{more_note}"),
            table_headers=["Mã TDV", "Tên TDV", "Vùng", "Doanh Số Ngày", "Chỉ Tiêu Tháng", "% Ngày"],
            table_rows=table,
            channels=("teams",),
            period=target_day.strftime('%d/%m/%Y'), channel="OTC", region=header_region,
            issue=(f"Đỏ {len(reds)} · Vàng {len(yellows)} · Xanh {len(greens)} — báo cáo tóm tắt nhịp "
                   f"KPI ngày, không phải cảnh báo bất thường (xem ghi chú backtest trong docstring)")
        )
        record_alert_sent(alert_key, str(len(reds)))


def check_kpi_milestone_drop_alert():
    """
    Mốc ngày 10 và ngày 20 hàng tháng: so doanh thu lũy kế đầu tháng -> ngày mốc của THÁNG NÀY với
    trung bình cộng lũy kế cùng khoảng ngày đó của N tháng liền trước (mặc định 5 tháng) — cảnh
    báo nếu giảm > ngưỡng (mặc định 5%). Kiểm tra CẢ 2 mức: (a) từng kênh OTC/ETC riêng biệt,
    (b) từng cá nhân TDV (chỉ khả thi kênh OTC — xem giới hạn dữ liệu ở check_daily_kpi_pace_alert).

    Mốc "hôm nay" lấy theo ngày LIỀN TRƯỚC ngày mới nhất có dữ liệu (không dùng datetime.now(),
    KHÔNG dùng thẳng MAX(DocDate) — xác minh thực tế 08/07/2026 ở check_daily_kpi_pace_alert():
    ngày mới nhất trong dữ liệu luôn chưa đồng bộ xong, dùng trực tiếp sẽ làm cả gate ngày 10/20
    lẫn tổng lũy kế bị lệch/thiếu). Chỉ thực sự tính toán khi ngày đã đồng bộ xong đó ĐÚNG LÀ ngày
    10 hoặc 20, các ngày khác bỏ qua ngay để không tốn query vô ích mỗi lần sync (5 lần/ngày).

    ƯU TIÊN NGUỒN (10/07/2026): phần (a) theo kênh dùng _period_revenue() (src/etl.py) — hàm này
    ĐÃ tự Bravo-first qua run_with_failover() (đổi ưu tiên chung ở src/database.py), không cần sửa
    gì thêm ở đây. Phần (b) theo từng TDV vẫn đọc thẳng Supabase (kpi_summary + brv_hoadonct/
    brv_hoadonhdr) — cùng lý do với check_daily_kpi_pace_alert (query nhiều JOIN phức tạp, để lại
    dịch T-SQL cẩn thận sau, chưa vội trong đợt này).
    """
    from sqlalchemy import text
    from src.etl import _period_revenue, _prev_month_tuple
    engine = _alert_engine()
    if engine is None:
        return

    lookback = int(_biz_threshold('kpi_milestone_lookback_months', 5))
    drop_threshold = float(_biz_threshold('kpi_milestone_drop_pct', 0.05))
    min_prev = float(_biz_threshold('kpi_milestone_min_prev', 10000000))

    try:
        with engine.connect() as conn:
            data_max_date = _last_complete_data_day()
    except Exception as e:
        print(f"[ALERTS][kpi_milestone] Lỗi lấy ngày dữ liệu mới nhất: {e}")
        return

    if not data_max_date:
        print("[ALERTS][kpi_milestone] Chưa có dữ liệu hóa đơn.")
        return

    if data_max_date.day not in (10, 20):
        print(f"[ALERTS][kpi_milestone] Ngày dữ liệu mới nhất ({data_max_date}) chưa tới mốc ngày 10/20 — bỏ qua.")
        return

    milestone_day = data_max_date.day
    month_start = datetime(data_max_date.year, data_max_date.month, 1)

    # 6 kỳ: kỳ hiện tại (idx 0) + N kỳ liền trước (idx 1..lookback), mỗi kỳ [start, start+milestone_day ngày)
    periods = []
    y, m = data_max_date.year, data_max_date.month
    for i in range(lookback + 1):
        p_start = datetime(y, m, 1)
        p_end = p_start + timedelta(days=milestone_day)
        periods.append((i, p_start, p_end))
        y, m = _prev_month_tuple(p_start)

    try:
        with engine.connect() as conn:
            # (a) Theo từng kênh — tái dùng _period_revenue (src/etl.py), ĐÃ tự Bravo-first qua
            # run_with_failover() (đổi ưu tiên chung ở src/database.py) — không cần sửa gì thêm.
            channel_series = {"OTC": [], "ETC": []}
            for idx, p_start, p_end in periods:
                otc_rev, etc_rev, _, _ = _period_revenue(p_start, p_end)
                channel_series["OTC"].append((idx, otc_rev))
                channel_series["ETC"].append((idx, etc_rev))

        # (b) Theo từng TDV — ưu tiên Bravo (T-SQL, FACT_TongHopKhachHang cho danh sách TDV +
        # dịch cùng query brv_hoadonct/hoadonhdr/dim_nhanvien như check_daily_kpi_pace_alert,
        # 10/07/2026); Bravo lỗi thì dự phòng nguyên vẹn logic Supabase cũ.
        import types
        tdv_rows = []
        try:
            from src.database import _get_bravo_engine
            bravo_engine = _get_bravo_engine()
            if bravo_engine is None:
                raise RuntimeError("Không có Bravo engine")
            union_blocks = []
            params = {}
            for idx, p_start, p_end in periods:
                params[f"start_{idx}"] = p_start.strftime("%Y-%m-%d")
                params[f"end_{idx}"] = p_end.strftime("%Y-%m-%d")
                union_blocks.append(f'''
                    SELECT {idx} AS period_idx, n.[EmployeeCode] AS employee_code,
                           SUM(CASE WHEN c.[CTKM] IS NULL OR c.[CTKM] = '' THEN c.[Amount9] ELSE 0 END) AS rev
                    FROM [BRV_HoaDonCt] c
                    JOIN [BRV_HoaDonHdr] h ON c.[Stt] = h.[Stt]
                    JOIN [DIM_NhanVien] n ON h.[EmpDMSCode] = n.[DMSId]
                    LEFT JOIN [BRV_TrangThaiDuyet] d ON h.[DocStatus] = d.[DocStatusKey]
                    LEFT JOIN [BRV_TrangThaiHoaDon] e ON h.[EInvoiceStatus] = e.[EInvoiceStatusKey]
                    WHERE h.[IsActive] = 1 AND h.[IsHC] = 0
                      AND (d.[IsCancelled] IS NULL OR d.[IsCancelled] = 0)
                      AND (e.[IsCancelled] IS NULL OR e.[IsCancelled] = 0)
                      AND d.[Post_TheKho] = 1
                      AND h.[DocDate] >= :start_{idx} AND h.[DocDate] < :end_{idx}
                    GROUP BY n.[EmployeeCode]
                ''')
            tdv_sql = text('''
                WITH tdv_periods AS (''' + " UNION ALL ".join(union_blocks) + '''
                ),
                tdv_target AS (
                    SELECT DISTINCT [EmployeeCode], [AreaCode], [MonthSaleTarget]
                    FROM [FACT_TongHopKhachHang]
                    WHERE [SaveDate] = (SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang])
                )
                SELECT n.[EmployeeCode] AS employee_code, n.[Name] AS employee_name, t.[AreaCode] AS area_code,
                       tp.period_idx, tp.rev
                FROM tdv_target t
                JOIN [DIM_NhanVien] n ON t.[EmployeeCode] = n.[EmployeeCode]
                JOIN tdv_periods tp ON tp.employee_code = t.[EmployeeCode]
                WHERE n.[PositionCode] = 'TDV' AND (n.[IsDuplicate] IS NULL OR n.[IsDuplicate] = 0)
                  AND t.[MonthSaleTarget] > 0
            ''')
            with bravo_engine.connect() as bconn:
                raw_rows = bconn.execute(tdv_sql, params).fetchall()
            tdv_rows = [types.SimpleNamespace(
                employee_code=r.employee_code, employee_name=r.employee_name, area_code=r.area_code,
                period_idx=r.period_idx, rev=float(r.rev or 0))
                for r in raw_rows]
        except Exception as e:
            print(f"[ALERTS][kpi_milestone] Bravo lỗi ({e}) — dự phòng Supabase cho phần TDV.")
            union_blocks = []
            params = {}
            for idx, p_start, p_end in periods:
                params[f"start_{idx}"] = p_start
                params[f"end_{idx}"] = p_end
                union_blocks.append(f'''
                    SELECT {idx} AS period_idx, n."EmployeeCode" AS employee_code,
                           SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
                    FROM brv_hoadonct c
                    JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
                    JOIN dim_nhanvien n ON h."EmpDMSCode" = n."DMSId"
                    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
                    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
                    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
                      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
                      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
                      AND d."Post_TheKho" = TRUE
                      AND h."DocDate"::timestamp >= :start_{idx} AND h."DocDate"::timestamp < :end_{idx}
                    GROUP BY n."EmployeeCode"
                ''')
            tdv_sql = text('''
                WITH tdv_periods AS (''' + " UNION ALL ".join(union_blocks) + '''
                )
                SELECT k.employee_code, k.employee_name, k.area_code, tp.period_idx, tp.rev
                FROM kpi_summary k
                JOIN tdv_periods tp ON tp.employee_code = k.employee_code
                WHERE k.position_code = 'TDV' AND COALESCE(k.month_sale_target,0) > 0
            ''')
            try:
                with engine.connect() as conn2:
                    tdv_rows = conn2.execute(tdv_sql, params).fetchall()
            except Exception as e2:
                print(f"[ALERTS][kpi_milestone] Lỗi cả 2 nguồn cho phần TDV: {e2}")
                tdv_rows = []
    except Exception as e:
        print(f"[ALERTS][kpi_milestone] Lỗi truy vấn lũy kế mốc ngày {milestone_day}: {e}")
        return

    period_desc = f"01/{month_start.strftime('%m')} - {milestone_day}/{month_start.strftime('%m/%Y')}"

    # (a) Theo từng kênh
    for channel_label, series in channel_series.items():
        series_sorted = sorted(series, key=lambda x: x[0])
        cur_rev = series_sorted[0][1]
        prev_revs = [rev for idx, rev in series_sorted[1:]]
        if not prev_revs:
            continue
        avg_prev = sum(prev_revs) / len(prev_revs)
        if avg_prev <= 0:
            continue
        drop = (avg_prev - cur_rev) / avg_prev
        print(f"[ALERTS][kpi_milestone][{channel_label}] Lũy kế {period_desc}: {format_vietnamese_money(cur_rev)} "
              f"vs TB {lookback} tháng trước {format_vietnamese_money(avg_prev)} ({drop*100:.1f}% thay đổi).")
        if drop > drop_threshold:
            alert_key = f"kpi_milestone_channel:{channel_label}:{milestone_day}:{month_start.strftime('%Y-%m')}"
            if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(drop, 4))):
                send_alert_to_all_channels(
                    alert_name=f"CẢNH BÁO LŨY KẾ NGÀY {milestone_day} SỤT GIẢM ({channel_label})",
                    severity="CRITICAL",
                    summary=(f"Lũy kế doanh thu kênh {channel_label} {period_desc} đạt {format_vietnamese_money(cur_rev)}, "
                             f"giảm {drop*100:.1f}% so với TB cộng cùng khoảng ngày của {lookback} tháng trước "
                             f"({format_vietnamese_money(avg_prev)})."),
                    table_headers=["Kỳ", f"Lũy kế {channel_label}"],
                    table_rows=[
                        [f"TB {lookback} tháng trước (đến ngày {milestone_day})", format_vietnamese_money(avg_prev)],
                        [f"Tháng này (đến ngày {milestone_day})", format_vietnamese_money(cur_rev)],
                    ],
                    channels=("teams",),
                    period=month_start.strftime('%m/%Y'), channel=channel_label, region="Toàn quốc",
                    issue=f"Lũy kế đến ngày {milestone_day} kênh {channel_label} giảm {drop*100:.1f}% so với TB {lookback} tháng trước"
                )
                record_alert_sent(alert_key, str(round(drop, 4)))

    # (b) Theo từng TDV (chỉ OTC — xem giới hạn dữ liệu)
    by_emp = {}
    for r in tdv_rows:
        info = by_emp.setdefault(r.employee_code, {"name": r.employee_name, "area": r.area_code, "periods": {}})
        info["periods"][r.period_idx] = float(r.rev)

    dropped_tdv = []
    for emp_code, info in by_emp.items():
        cur_rev = info["periods"].get(0, 0.0)
        prev_revs = [info["periods"][i] for i in range(1, lookback + 1) if i in info["periods"]]
        if not prev_revs:
            continue
        avg_prev = sum(prev_revs) / len(prev_revs)
        if avg_prev < min_prev:
            continue
        drop = (avg_prev - cur_rev) / avg_prev
        if drop > drop_threshold:
            dropped_tdv.append((emp_code, info["name"], info["area"], cur_rev, avg_prev, drop))

    if dropped_tdv:
        alert_key = f"kpi_milestone_tdv:{milestone_day}:{month_start.strftime('%Y-%m')}"
        current_value = str(len(dropped_tdv))
        if should_send_alert(alert_key, cooldown_hours=24, current_value=current_value):
            dropped_tdv.sort(key=lambda x: -x[5])
            regions_seen = set()
            table = []
            for emp_code, name, area, cur_rev, avg_prev, drop in dropped_tdv[:15]:
                region_label = normalize_region_label(area)
                regions_seen.add(region_label)
                table.append([str(emp_code), name, region_label, format_vietnamese_money(cur_rev),
                              format_vietnamese_money(avg_prev), f"-{drop*100:.1f}%"])
            header_region = regions_seen.pop() if len(regions_seen) == 1 else "Nhiều miền"
            send_alert_to_all_channels(
                alert_name=f"CẢNH BÁO LŨY KẾ NGÀY {milestone_day} SỤT GIẢM (TỪNG TDV)",
                severity="WARNING",
                summary=(f"{len(dropped_tdv)} TDV có lũy kế doanh số {period_desc} giảm >{drop_threshold*100:.0f}% "
                         f"so với TB {lookback} tháng trước cùng khoảng ngày."),
                table_headers=["Mã TDV", "Tên TDV", "Vùng", "Lũy Kế Tháng Này", f"TB {lookback} Tháng Trước", "% Giảm"],
                table_rows=table,
                channels=("teams",),
                period=month_start.strftime('%m/%Y'), channel="OTC", region=header_region,
                issue=f"{len(dropped_tdv)} TDV có lũy kế đến ngày {milestone_day} giảm >{drop_threshold*100:.0f}% so với TB {lookback} tháng trước"
            )
            record_alert_sent(alert_key, current_value)


# ---- Nhóm G: Meta-alert vận hành / chất lượng dữ liệu ----------------------

def check_data_sanity_ok():
    """
    G2 (guard): Kiểm tra dữ liệu có "lành" không TRƯỚC khi chạy các alert nghiệp vụ.
    Trả True nếu ổn. Nếu các chỉ số cốt lõi rơi về 0 bất thường (nghi ETL hỏng) -> gửi
    cảnh báo meta + trả False để job KHÔNG gửi alert nghiệp vụ dựa trên dữ liệu rác.
    """
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return True  # không có cloud -> để các hàm khác tự log, không chặn
    try:
        with engine.connect() as conn:
            cust = conn.execute(text("SELECT COUNT(*) FROM receivable_detail")).fetchone()[0]
            # 'inventory' có thể CHỦ ĐỘNG để trống (chờ Excel/DNH — xem check_dead_stock_alert).
            # Chỉ đếm nếu bảng THỰC SỰ tồn tại; bảng chưa dựng -> inv=None, KHÔNG coi là ETL lỗi
            # (tránh làm guard "mù" toàn bộ chỉ vì 1 bảng đã biết là tạm vắng — hành vi cũ: query
            # ném UndefinedTable -> except -> return True -> guard bị bỏ qua HOÀN TOÀN).
            inv = conn.execute(text("SELECT COUNT(*) FROM inventory")).fetchone()[0] \
                if _supabase_table_exists(conn, "inventory") else None
    except Exception as e:
        print(f"[ALERTS][data_sanity] Không kiểm tra được (bỏ qua guard): {e}")
        return True
    if cust == 0 or inv == 0:
        inv_display = str(inv) if inv is not None else "N/A (bảng chưa dựng)"
        alert_key = "data_sanity_zero"
        if should_send_alert(alert_key, cooldown_hours=6, current_value="zero"):
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO HỆ THỐNG: DỮ LIỆU BẤT THƯỜNG (RỖNG)",
                severity="CRITICAL",
                summary=(f"Bảng công nợ ({cust} dòng) hoặc tồn kho ({inv_display} dòng) đang rỗng — nghi ETL lỗi. "
                         f"Đã TẠM DỪNG gửi các cảnh báo nghiệp vụ để tránh báo sai."),
                table_headers=["Bảng", "Số dòng"],
                table_rows=[["receivable_detail", str(cust)], ["inventory", inv_display]],
                channels=("teams",),
                period=datetime.now().strftime("%d/%m/%Y %H:%M"), region="Toàn quốc (hệ thống)",
                issue="Bảng công nợ hoặc tồn kho đang rỗng — nghi ETL lỗi, đã tạm dừng các cảnh báo nghiệp vụ"
            )
            record_alert_sent(alert_key, "zero")
        return False
    return True


def check_etl_freshness_alert():
    """
    G1: Meta-alert — dữ liệu hậu-ETL không được refresh quá lâu (MAX SyncAt cũ hơn N giờ)
    -> nghi ETL thượng nguồn bị đứng. Vừa là health-check, vừa là 'watermark' đã bàn.
    """
    from sqlalchemy import text
    from datetime import datetime as _dt
    engine = _alert_engine()
    if engine is None:
        return
    stale_hours = float(_biz_threshold('etl_stale_hours', 3))
    try:
        with engine.connect() as conn:
            row = conn.execute(text('SELECT MAX("SyncAt") FROM brv_hoadonct')).fetchone()
            last_sync = row[0] if row else None
    except Exception as e:
        print(f"[ALERTS][etl_freshness] Lỗi đọc SyncAt: {e}")
        return
    if last_sync is None:
        print("[ALERTS][etl_freshness] Không có mốc SyncAt để đánh giá.")
        return
    if isinstance(last_sync, str):
        try:
            last_sync = _dt.fromisoformat(last_sync.replace('Z', '').split('.')[0])
        except Exception:
            print("[ALERTS][etl_freshness] Không parse được SyncAt.")
            return
    age_hours = (datetime.now() - last_sync).total_seconds() / 3600.0
    print(f"[ALERTS][etl_freshness] Dữ liệu mới nhất cách đây {age_hours:.1f} giờ (ngưỡng {stale_hours:.0f} giờ).")
    if age_hours > stale_hours:
        alert_key = "etl_stale"
        if should_send_alert(alert_key, cooldown_hours=2, current_value=str(int(age_hours))):
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO HỆ THỐNG: ETL CÓ THỂ ĐÃ ĐỨNG",
                severity="CRITICAL",
                summary=(f"Dữ liệu hậu-ETL không được cập nhật đã {age_hours:.1f} giờ "
                         f"(ngưỡng {stale_hours:.0f} giờ). Kiểm tra tiến trình ETL thượng nguồn."),
                table_headers=["Mốc dữ liệu mới nhất", "Đã cũ"],
                table_rows=[[str(last_sync), f"{age_hours:.1f} giờ"]],
                channels=("teams",),
                period=datetime.now().strftime("%d/%m/%Y %H:%M"), region="Toàn quốc (hệ thống)",
                issue=f"Dữ liệu hậu-ETL không được cập nhật đã {age_hours:.1f} giờ — nghi ETL thượng nguồn bị đứng"
            )
            record_alert_sent(alert_key, str(int(age_hours)))


if __name__ == '__main__':
    # Chạy thử test module cảnh báo cục bộ
    # Vì chưa set tài khoản SMTP thật nên send_email sẽ ghi warning ra log thay vì crash.
    erp_eng, crm_eng = get_db_engines()
    print("Khởi chạy kiểm tra cảnh báo...")
    run_alert_checks(erp_eng, crm_eng)
    print("Kiểm tra hoàn thành.")
