import os
import sys
import sqlite3
import pandas as pd
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
        for idx, row in df_low_inv.iterrows():
            sku = row['sku']
            item_name = row['item_name']
            qty = row['quantity']
            
            alert_key = f"low_inventory:{sku}"
            # Cooldown 4 tiếng đối với cảnh báo tồn kho của từng sản phẩm
            if should_send_alert(alert_key, cooldown_hours=4, current_value=qty):
                if send_alert_to_all_channels(
                    alert_name="CANH BAO TON KHO THAP",
                    severity="WARNING",
                    summary=f"San pham '{item_name}' (SKU: {sku}) hien chi con {qty} san pham trong kho (Nguong canh bao: < {low_inv_limit}).",
                    table_headers=["Ma SKU", "Ten San Pham", "Ton Kho Hien Tai", "Thoi Gian Cap Nhat"],
                    table_rows=[[sku, item_name, str(qty), str(row['updated_at'])]],
                    channels=("telegram", "teams")
                ):
                    record_alert_sent(alert_key, qty)
    else:
        # Nếu không còn sản phẩm nào tồn kho thấp, xóa sạch trạng thái để kích hoạt cảnh báo tức thì khi có lỗi sau này
        pass

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
                channels=("telegram", "teams")
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
                channels=("telegram", "teams")
            ):
                record_alert_sent(alert_key_crm, urgent_count)
    else:
        clear_alert_state(alert_key_crm)

LOCAL_DB_PATH = os.path.join(PROJECT_ROOT, "scripts", "dnh_intermediate.db")

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

def get_overdue_days_str(conn, r):
    customer_code = r['customer_code']
    period_str = r['period']
    
    # 1. Thử truy vấn hóa đơn chưa thanh toán thực tế (Chính xác nhất)
    query = """
    SELECT MIN(i.invoice_date) as oldest_date
    FROM invoices i
    JOIN orders o ON i.order_id = o.order_id
    WHERE o.customer_id = ? AND i.status = 'Da phat hanh';
    """
    try:
        df = pd.read_sql(query, conn, params=(customer_code,))
        if not df.empty and df.iloc[0]['oldest_date'] is not None:
            oldest_date_str = df.iloc[0]['oldest_date']
            oldest_date = datetime.strptime(oldest_date_str, "%Y-%m-%d")
            today = datetime.now()
            days = (today - oldest_date).days
            return f"{days} ngày (từ {oldest_date.strftime('%d/%m/%Y')})"
    except Exception:
        pass
        
    # 2. Phương án dự phòng: Tính toán từ Tuổi nợ (Aging) + Kỳ báo cáo (Period)
    try:
        parts = period_str.split('_')
        month, year = int(parts[0]), int(parts[1])
        
        # Lấy ngày cuối cùng của tháng báo cáo
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        report_date = datetime(year, month, last_day)
        
        # Mốc ngày chạy hệ thống
        today = datetime.now()
        days_since_report = (today - report_date).days
        if days_since_report < 0:
            days_since_report = 0
            
        if r['overdue_gt_45'] > 0:
            return f"Ít nhất {45 + days_since_report} ngày"
        elif r['overdue_30_45'] > 0:
            return f"Từ {30 + days_since_report} đến {45 + days_since_report} ngày"
        elif r['overdue_15_30'] > 0:
            return f"Từ {15 + days_since_report} đến {30 + days_since_report} ngày"
        elif r['overdue_1_15'] > 0:
            return f"Từ {1 + days_since_report} đến {15 + days_since_report} ngày"
    except Exception:
        pass
        
    return "Trên 45 ngày"

def get_latest_period(conn):
    """
    Tự động dò tìm kỳ báo cáo mới nhất trong bảng receivable_detail
    """
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT period FROM receivable_detail")
    periods = [row[0] for row in cursor.fetchall() if row[0]]
    if not periods:
        return None
    
    # Hàm phân tích cú pháp 'month_year' để tìm max
    def parse_period(p):
        parts = p.split('_')
        if len(parts) == 2:
            return int(parts[1]), int(parts[0])
        return 0, 0
    return max(periods, key=parse_period)

def run_smart_business_alerts():
    """
    Quét và gửi cảnh báo thông minh dựa trên dữ liệu thực tế DNH (Nợ quá hạn, Cháy kho, KPI)
    """
    if not os.path.exists(LOCAL_DB_PATH):
        print(f"[ALERTS] CSDL trung gian {LOCAL_DB_PATH} không tồn tại. Bỏ qua quét.")
        return
        
    try:
        conn = sqlite3.connect(LOCAL_DB_PATH)
        
        # Lấy kỳ báo cáo mới nhất để tránh bị lặp đại lý từ các tháng trước
        latest_period = get_latest_period(conn)
        if not latest_period:
            print("[ALERTS] Không tìm thấy kỳ báo cáo nào trong CSDL.")
            conn.close()
            return
            
        print(f"[ALERTS] Dang quet canh bao cho ky bao cao moi nhat: {latest_period}")
        
        # 1. CẢNH BÁO NỢ QUÁ HẠN KHUNG (Top Overdue Debts)
        query_debt = """
        SELECT period, customer_code, customer_name, total_overdue, balance_end,
               overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45
        FROM receivable_detail
        WHERE period = ? AND total_overdue > 10000000 -- Trên 10 triệu
        ORDER BY total_overdue DESC
        LIMIT 5;
        """
        df_debt = pd.read_sql(query_debt, conn, params=(latest_period,))
        if not df_debt.empty:
            alert_key = "smart_debt_overdue_top5"
            top_overdue = df_debt.iloc[0]['total_overdue']
            # Cooldown 6 tiếng
            if should_send_alert(alert_key, cooldown_hours=6, current_value=str(top_overdue)):
                rows = []
                for _, r in df_debt.iterrows():
                    overdue_fmt = format_vietnamese_money(r['total_overdue'])
                    balance_fmt = format_vietnamese_money(r['balance_end'])
                    days_overdue = get_overdue_days_str(conn, r)
                    rows.append([str(r['customer_code']), r['customer_name'], overdue_fmt, balance_fmt, days_overdue])
                    
                send_alert_to_all_channels(
                    alert_name="CẢNH BÁO NỢ QUÁ HẠN LỚN (TOP 5)",
                    severity="CRITICAL",
                    summary=f"Hệ thống phát hiện danh sách nhà thuốc/đại lý đang có nợ quá hạn lớn nhất ở mức báo động đỏ (Kỳ: {latest_period}).",
                    table_headers=["Mã KH", "Tên Đại Lý", "Nợ Quá Hạn", "Tổng Nợ", "Số Ngày Nợ"],
                    table_rows=rows,
                    channels=("telegram", "teams")
                )
                record_alert_sent(alert_key, top_overdue)
                
        # 2. CẢNH BÁO CHÁY HÀNG TỒN KHO (Inventory Out-of-Stock Risk)
        query_inv = """
        SELECT item_code, item_name, closing_qty, outward_qty, months_to_sell
        FROM inventory
        WHERE months_to_sell > 0.0 AND months_to_sell <= 1.0 AND closing_qty > 0
        ORDER BY months_to_sell ASC
        LIMIT 5;
        """
        df_inv = pd.read_sql(query_inv, conn)
        if not df_inv.empty:
            alert_key = "smart_inventory_depletion_top5"
            top_qty = df_inv.iloc[0]['closing_qty']
            # Cooldown 12 tiếng
            if should_send_alert(alert_key, cooldown_hours=12, current_value=str(top_qty)):
                rows = []
                for _, r in df_inv.iterrows():
                    closing_qty = r['closing_qty']
                    outward_qty = r['outward_qty']
                    months_to_sell = r['months_to_sell']
                    
                    # Tính toán số ngày bán còn lại theo công thức chuẩn của người dùng:
                    # Số ngày bán = Tồn kho / Số lượng bán trung bình mỗi ngày
                    # Số lượng bán trung bình mỗi ngày = Số lượng 1 năm / 365 (làm tròn lên - ceil)
                    if outward_qty is not None and outward_qty > 0:
                        sales_per_day = math.ceil(outward_qty / 365)
                        if sales_per_day > 0:
                            days = math.ceil(closing_qty / sales_per_day)
                            days_to_sell_fmt = f"Còn {days} ngày bán (Trung bình bán {sales_per_day} SKU/ngày)"
                        else:
                            days_to_sell_fmt = format_months_to_sell(months_to_sell)
                    else:
                        # Dự phòng nếu file mock/CSDL tạm chưa có số lượng bán 1 năm (outward_qty = 0)
                        days_to_sell_fmt = format_months_to_sell(months_to_sell)
                        
                    rows.append([str(r['item_code']), r['item_name'], f"{r['closing_qty']:,.0f}".replace(',', '.'), days_to_sell_fmt])
                    
                send_alert_to_all_channels(
                    alert_name="CẢNH BÁO NGUY CƠ ĐỨT HÀNG (TOP 5)",
                    severity="WARNING",
                    summary="Các mặt hàng sau có tốc độ bán quá nhanh và tồn kho chỉ đủ dùng trong dưới 1 tháng.",
                    table_headers=["Mã SKU", "Tên Thuốc", "Tồn Kho Hiện Tại", "Dự Kiến Bán Hết"],
                    table_rows=rows,
                    channels=("telegram", "teams")
                )
                record_alert_sent(alert_key, top_qty)

        # 3. CẢNH BÁO TIẾN ĐỘ KPI DOANH SỐ THẤP (Low sales target progress)
        query_kpi = """
        SELECT employee_code, employee_name, month_sale_target, month_sale_amount, month_sale_percent
        FROM kpi_summary
        WHERE month_sale_target > 10000000 AND month_sale_percent < 0.60 -- Dưới 60% chỉ tiêu
        ORDER BY month_sale_percent ASC
        LIMIT 5;
        """
        df_kpi = pd.read_sql(query_kpi, conn)
        if not df_kpi.empty:
            alert_key = "smart_kpi_low_progress_top5"
            lowest_pct = df_kpi.iloc[0]['month_sale_percent']
            # Cooldown 24 tiếng
            if should_send_alert(alert_key, cooldown_hours=24, current_value=str(lowest_pct)):
                rows = []
                for _, r in df_kpi.iterrows():
                    # Nhân 100 để đổi từ hệ số thập phân sang tỷ lệ phần trăm thực tế (Ví dụ: 0.1 -> 10.0%)
                    real_pct = r['month_sale_percent'] * 100
                    percent_fmt = f"{real_pct:.1f}%".replace('.', ',')
                    target_fmt = format_vietnamese_money(r['month_sale_target'])
                    amount_fmt = format_vietnamese_money(r['month_sale_amount'])
                    rows.append([str(r['employee_code']), r['employee_name'], target_fmt, amount_fmt, percent_fmt])
                    
                send_alert_to_all_channels(
                    alert_name="CẢNH BÁO TIẾN ĐỘ KPI TDV THẤP (TOP 5)",
                    severity="WARNING",
                    summary="Các Trình dược viên sau đang đạt dưới 60% chỉ tiêu doanh số tháng.",
                    table_headers=["Mã TDV", "Tên TDV", "Chỉ Tiêu", "Doanh Số Đạt", "Đạt Được"],
                    table_rows=rows,
                    channels=("telegram", "teams")
                )
                record_alert_sent(alert_key, lowest_pct)

        conn.close()
    except Exception as e:
        print(f"[ALERTS] Lỗi khi quét cảnh báo kinh doanh: {e}")

def run_sales_kpi_insights_alert():
    """
    Quét và gửi báo cáo phân tích doanh số, hiệu suất KPI theo kênh (OTC/ETC) và chức danh.
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
        
        # 1. Kênh bán hàng (Phân phối, không phải con người)
        for ch in data['channels']:
            rows.append([
                f"Kênh {ch['channel']}",
                format_vietnamese_money(ch['target']),
                format_vietnamese_money(ch['actual']),
                f"{ch['percent']:.1f}%".replace('.', ',')
            ])
            
        # 2. So sánh hiệu suất giữa các Trưởng phòng (TP)
        if data['tps']:
            for r in data['tps']:
                rows.append([
                    f"TP: {r['employee_name']}",
                    format_vietnamese_money(r['month_sale_target']),
                    format_vietnamese_money(r['month_sale_amount']),
                    f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
                ])
                
        # 3. So sánh hiệu suất giữa các Phó phòng (PP)
        if data['pps']:
            for r in data['pps']:
                rows.append([
                    f"PP: {r['employee_name']}",
                    format_vietnamese_money(r['month_sale_target']),
                    format_vietnamese_money(r['month_sale_amount']),
                    f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
                ])
                
        # 4. So sánh hiệu suất giữa các Quản lý vùng (QLV)
        if data['qlvs']:
            for r in data['qlvs']:
                rows.append([
                    f"QLV: {r['employee_name']}",
                    format_vietnamese_money(r['month_sale_target']),
                    format_vietnamese_money(r['month_sale_amount']),
                    f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
                ])
                
        # 5. Top 3 TDV/CTV xuất sắc nhất
        for idx, r in enumerate(data['top_reps']):
            rows.append([
                f"⭐ Top {idx+1} TDV: {r['employee_name']}",
                format_vietnamese_money(r['month_sale_target']),
                format_vietnamese_money(r['month_sale_amount']),
                f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
            ])
            
        # 6. Top 3 TDV/CTV cần hỗ trợ
        for idx, r in enumerate(data['bottom_reps']):
            rows.append([
                f"⚠️ Cần hỗ trợ #{idx+1}: {r['employee_name']} ({r['position_code']})",
                format_vietnamese_money(r['month_sale_target']),
                format_vietnamese_money(r['month_sale_amount']),
                f"{r['month_sale_percent']*100:.1f}%".replace('.', ',')
            ])
            
        send_alert_to_all_channels(
            alert_name="BÁO CÁO PHÂN TÍCH DOANH SỐ & KPI",
            severity="INFO",
            summary=f"Báo cáo định kỳ phân tích hiệu suất thực hiện KPI doanh số theo Kênh phân phối và cấp bậc quản lý (TP/PP/QLV) vs nhân viên trực tiếp (TDV/CTV/CS) tại kỳ báo cáo {data['latest_period']}.",
            table_headers=["Phân Loại / Nhân Sự", "KPI Mục Tiêu", "Doanh Số Đạt", "Tỷ Lệ Hoàn Thành"],
            table_rows=rows,
            channels=("telegram", "teams")
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
    TRIGGER 4: Cảnh báo khi tổng doanh thu (OTC + ETC, loại trừ dòng khuyến mãi CTKM)
    của tháng mới nhất giảm quá ngưỡng (mặc định 20%) so với tháng liền trước.

    LƯU Ý CÁCH TÍNH (cần DNH xác nhận theo MCNA_DNH_ProjectPlan_v3.docx):
      - Hiện triển khai so sánh THÁNG N vs THÁNG N-1 (month-over-month, kỳ liền kề).
      - Nếu DNH chốt so cùng kỳ NĂM TRƯỚC (year-over-year, tránh nhiễu mùa vụ) thì đổi
        mốc thời gian — nhưng dữ liệu hiện chỉ có Q2/2026 nên YoY chưa tính được.
    """
    try:
        from ai_agent.chatbot import _get_cloud_engine
        from sqlalchemy import text
    except Exception as e:
        print(f"[ALERTS][revenue_drop] Không import được engine dữ liệu: {e}")
        return

    engine = _get_cloud_engine()
    if engine is None:
        print("[ALERTS][revenue_drop] Chưa cấu hình CLOUD_DB_URL — bỏ qua cảnh báo doanh thu giảm.")
        return

    # Doanh thu theo tháng: gộp OTC (brv_hoadonct) + ETC (brvsx_hoadonct) qua CTE riêng rồi
    # UNION ALL (đúng quy tắc join-per-channel trong chatbot), chỉ tính SL/doanh thu thực bán
    # (loại dòng CTKM khuyến mãi), lấy 2 tháng gần nhất theo DocDate.
    sql = text("""
        WITH otc AS (
            SELECT DATE_TRUNC('month', h."DocDate"::timestamp)::date AS m,
                   SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
            FROM brv_hoadonct c
            JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
            LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
            GROUP BY 1
        ),
        etc AS (
            SELECT DATE_TRUNC('month', h."DocDate"::timestamp)::date AS m,
                   SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END) AS rev
            FROM brvsx_hoadonct c
            JOIN brvsx_hoadonhdr h ON c."Stt" = h."Stt"
            LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
            LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
            WHERE h."IsActive" = TRUE
              AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
              AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
            GROUP BY 1
        ),
        allm AS (
            SELECT m, SUM(rev) AS rev
            FROM (SELECT * FROM otc UNION ALL SELECT * FROM etc) x
            GROUP BY m
        )
        SELECT m, rev FROM allm ORDER BY m DESC LIMIT 2
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(sql).fetchall()
    except Exception as e:
        print(f"[ALERTS][revenue_drop] Lỗi truy vấn doanh thu: {e}")
        return

    if len(result) < 2:
        print("[ALERTS][revenue_drop] Chưa đủ 2 tháng dữ liệu để so sánh — bỏ qua.")
        return

    latest_month, latest_rev = result[0][0], result[0][1]
    prev_month, prev_rev = result[1][0], result[1][1]

    ratio = revenue_drop_ratio(prev_rev, latest_rev)
    threshold = _get_revenue_drop_threshold()
    if ratio is None:
        print("[ALERTS][revenue_drop] Không tính được tỷ lệ sụt giảm (doanh thu kỳ trước <= 0).")
        return

    print(f"[ALERTS][revenue_drop] Tháng {latest_month} vs {prev_month}: tỷ lệ thay đổi = {ratio*100:.1f}% (ngưỡng cảnh báo giảm > {threshold*100:.0f}%).")

    if ratio > threshold:
        alert_key = f"revenue_drop:{latest_month}"
        if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(ratio, 4))):
            drop_amount = float(prev_rev) - float(latest_rev)
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO DOANH THU SỤT GIẢM MẠNH",
                severity="CRITICAL",
                summary=(f"Doanh thu tháng {latest_month.strftime('%m/%Y')} giảm "
                         f"{ratio*100:.1f}% so với tháng {prev_month.strftime('%m/%Y')} "
                         f"(vượt ngưỡng cảnh báo {threshold*100:.0f}%)."),
                table_headers=["Kỳ", "Doanh thu (OTC+ETC, đã trừ KM)", "Chênh lệch"],
                table_rows=[
                    [prev_month.strftime('%m/%Y'), format_vietnamese_money(prev_rev), "—"],
                    [latest_month.strftime('%m/%Y'), format_vietnamese_money(latest_rev),
                     f"-{format_vietnamese_money(drop_amount)} ({ratio*100:.1f}%)"],
                ],
                channels=("telegram", "teams")
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
            channels=("telegram", "teams")
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
    """A3: Tỷ lệ nợ quá hạn / tổng dư nợ TOÀN CÔNG TY vượt ngưỡng (sức khỏe dòng tiền)."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    threshold = float(_biz_threshold('overdue_ratio_pct', 0.35))
    try:
        with engine.connect() as conn:
            latest, _ = _two_latest_periods(conn)
            if not latest:
                return
            row = conn.execute(text(
                "SELECT SUM(total_overdue), SUM(balance_end) FROM receivable_detail WHERE period=:p"
            ), {"p": latest}).fetchone()
    except Exception as e:
        print(f"[ALERTS][overdue_ratio] Lỗi: {e}")
        return
    ratio = overdue_ratio(row[0], row[1])
    if ratio is None:
        return
    print(f"[ALERTS][overdue_ratio] Kỳ {latest}: nợ quá hạn/tổng nợ = {ratio*100:.1f}% (ngưỡng {threshold*100:.0f}%).")
    if ratio > threshold:
        alert_key = f"company_overdue_ratio:{latest}"
        if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(ratio, 4))):
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO TỶ LỆ NỢ QUÁ HẠN TOÀN CÔNG TY CAO",
                severity="CRITICAL",
                summary=(f"Kỳ {latest}: tổng nợ quá hạn chiếm {ratio*100:.1f}% tổng dư nợ "
                         f"(vượt ngưỡng {threshold*100:.0f}%) — dòng tiền đang bị nghẽn."),
                table_headers=["Tổng dư nợ", "Nợ quá hạn", "Tỷ lệ quá hạn"],
                table_rows=[[format_vietnamese_money(row[1]), format_vietnamese_money(row[0]), f"{ratio*100:.1f}%"]],
                channels=("telegram", "teams")
            )
            record_alert_sent(alert_key, str(round(ratio, 4)))


def check_overdue_customer_new_orders_alert():
    """A2: Khách đang nợ quá hạn NHƯNG vẫn được lên đơn mới trong tháng gần nhất."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    try:
        with engine.connect() as conn:
            latest, _ = _two_latest_periods(conn)
            if not latest:
                return
            # mốc đầu tháng gần nhất theo dữ liệu hóa đơn thật
            since_row = conn.execute(text(
                'SELECT DATE_TRUNC(\'month\', MAX("DocDate"::date))::date FROM brv_hoadonhdr WHERE "IsActive"=TRUE'
            )).fetchone()
            since = since_row[0] if since_row and since_row[0] else None
            if since is None:
                return
            sql = text('''
                WITH overdue_cust AS (
                    SELECT customer_code, customer_name, total_overdue
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
                SELECT o.customer_code, o.customer_name, o.total_overdue, r.n, r.amt
                FROM overdue_cust o JOIN recent_agg r ON o.customer_code = r.cc
                ORDER BY o.total_overdue DESC LIMIT 10
            ''')
            rows = conn.execute(sql, {"p": latest, "since": since}).fetchall()
    except Exception as e:
        print(f"[ALERTS][overdue_new_orders] Lỗi: {e}")
        return
    if not rows:
        print("[ALERTS][overdue_new_orders] Không có khách quá hạn nào được lên đơn mới.")
        return
    alert_key = "overdue_customer_new_orders"
    top = rows[0][2]
    if should_send_alert(alert_key, cooldown_hours=12, current_value=str(top)):
        table = [[str(r[0]), r[1], format_vietnamese_money(r[2]), str(int(r[3])), format_vietnamese_money(r[4])] for r in rows]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO: KHÁCH NỢ QUÁ HẠN VẪN ĐƯỢC LÊN ĐƠN MỚI",
            severity="CRITICAL",
            summary="Các khách hàng đang nợ quá hạn lớn nhưng vẫn phát sinh đơn hàng mới — cần kiểm duyệt trước khi giao thêm.",
            table_headers=["Mã KH", "Tên KH", "Nợ Quá Hạn", "Số Đơn Mới", "Giá Trị Đơn Mới"],
            table_rows=table,
            channels=("telegram", "teams")
        )
        record_alert_sent(alert_key, str(top))


def check_debt_aging_migration_alert():
    """A1: Khách MỚI rơi vào nhóm nợ >45 ngày ở kỳ này (kỳ trước chưa có) — nợ xấu hình thành."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    try:
        with engine.connect() as conn:
            latest, prev = _two_latest_periods(conn)
            if not latest or not prev:
                print("[ALERTS][aging_migration] Chưa đủ 2 kỳ để so sánh.")
                return
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
            rows = conn.execute(sql, {"latest": latest, "prev": prev}).fetchall()
    except Exception as e:
        print(f"[ALERTS][aging_migration] Lỗi: {e}")
        return
    if not rows:
        print("[ALERTS][aging_migration] Không có khách mới rơi vào nhóm >45 ngày.")
        return
    alert_key = f"aging_migration_gt45:{latest}"
    top = rows[0][2]
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(top)):
        table = [[str(r[0]), r[1], format_vietnamese_money(r[2])] for r in rows]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO NỢ CHUYỂN NHÓM XẤU (>45 NGÀY)",
            severity="CRITICAL",
            summary=(f"Kỳ {latest}: các khách sau LẦN ĐẦU rơi vào nhóm nợ quá hạn >45 ngày "
                     f"(kỳ trước {prev} chưa có) — nguy cơ nợ xấu, cần thu hồi gấp."),
            table_headers=["Mã KH", "Tên KH", "Nợ >45 ngày"],
            table_rows=table,
            channels=("telegram", "teams")
        )
        record_alert_sent(alert_key, str(top))


# ---- Nhóm B: Tồn kho -------------------------------------------------------

def check_dead_stock_alert():
    """B2: Tồn "chết"/bán chậm — months_to_sell rất lớn + giá trị tồn cao (vốn đọng)."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    dead_months = float(_biz_threshold('dead_stock_months', 12.0))
    min_value = float(_biz_threshold('dead_stock_min_value', 50000000))
    try:
        with engine.connect() as conn:
            rows = conn.execute(text('''
                SELECT item_code, item_name, unit, closing_qty, closing_value, months_to_sell
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
    top = rows[0][4]
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(top)):
        table = [[str(r[0]), r[1], f"{r[3]:,.0f}".replace(',', '.'),
                  format_vietnamese_money(r[4]), f"{r[5]:.1f} tháng"] for r in rows]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO TỒN KHO CHẾT / BÁN CHẬM",
            severity="WARNING",
            summary=(f"Các mặt hàng sau tồn kho đủ bán trên {dead_months:.0f} tháng và giá trị tồn lớn "
                     f"— vốn đang bị đọng, cân nhắc xả hàng/khuyến mãi."),
            table_headers=["Mã SKU", "Tên Hàng", "Tồn Kho", "Giá Trị Tồn", "Số Tháng Bán"],
            table_rows=table,
            channels=("telegram", "teams")
        )
        record_alert_sent(alert_key, str(top))


def check_near_expiry_alert():
    """
    B1: Hàng cận date / sắp hết hạn. TRẠNG THÁI: phòng thủ theo GAP DỮ LIỆU.
    Tồn kho theo lô (brvsx_thekholot) hiện chỉ có ItemLotCode + số lượng, KHÔNG có cột
    hạn dùng của lô. Cần bảng map lô -> hạn dùng (MfgDate/ExpiryDate) từ Bravo/DMS. Hàm tự
    dò cột hạn dùng gắn với tồn kho lúc chạy; nếu chưa có -> no-op + log rõ (không crash).
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
    """C1: Khách lớn (tháng trước mua nhiều) nhưng tháng mới nhất rớt mạnh — nguy cơ mất khách."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    drop_pct = float(_biz_threshold('customer_churn_drop_pct', 0.50))
    min_prev = float(_biz_threshold('customer_churn_min_prev', 50000000))
    try:
        with engine.connect() as conn:
            sql = text('''
                WITH cm AS (
                    SELECT "CustomerCode" AS cc, DATE_TRUNC('month',"DocDate"::timestamp)::date AS m, SUM("TotalAmount") AS rev
                    FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "IsHC"=FALSE GROUP BY 1,2
                    UNION ALL
                    SELECT "CustomerCode", DATE_TRUNC('month',"DocDate"::timestamp)::date, SUM("TotalAmount")
                    FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE GROUP BY 1,2
                ),
                agg AS (SELECT cc, m, SUM(rev) AS rev FROM cm GROUP BY cc, m),
                mm AS (SELECT m FROM (SELECT DISTINCT m FROM agg ORDER BY m DESC LIMIT 2) t),
                latest AS (SELECT MAX(m) AS m FROM mm),
                prev AS (SELECT MIN(m) AS m FROM mm)
                SELECT a.cc,
                       COALESCE(cur.rev,0) AS cur_rev,
                       prevd.rev AS prev_rev
                FROM (SELECT DISTINCT cc FROM agg) a
                JOIN agg prevd ON prevd.cc=a.cc AND prevd.m=(SELECT m FROM prev)
                LEFT JOIN agg cur ON cur.cc=a.cc AND cur.m=(SELECT m FROM latest)
                WHERE prevd.rev > :min_prev
                  AND (prevd.rev - COALESCE(cur.rev,0)) / prevd.rev > :drop
                ORDER BY prevd.rev DESC LIMIT 10
            ''')
            rows = conn.execute(sql, {"min_prev": min_prev, "drop": drop_pct}).fetchall()
    except Exception as e:
        print(f"[ALERTS][churn] Lỗi: {e}")
        return
    if not rows:
        print("[ALERTS][churn] Không có khách lớn nào rớt doanh số vượt ngưỡng.")
        return
    alert_key = "customer_churn"
    top = rows[0][0]
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(top)):
        table = []
        for r in rows:
            cur_rev = float(r[1]); prev_rev = float(r[2])
            drop = (prev_rev - cur_rev) / prev_rev if prev_rev > 0 else 0
            table.append([str(r[0]), format_vietnamese_money(prev_rev),
                          format_vietnamese_money(cur_rev), f"-{drop*100:.0f}%"])
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO KHÁCH HÀNG LỚN SỤT GIẢM (NGUY CƠ MẤT KHÁCH)",
            severity="WARNING",
            summary="Các khách hàng lớn sau có doanh số tháng mới nhất rớt mạnh so với tháng trước — cần chăm sóc ngay.",
            table_headers=["Mã KH", "Doanh Số Tháng Trước", "Doanh Số Tháng Này", "Sụt Giảm"],
            table_rows=table,
            channels=("telegram", "teams")
        )
        record_alert_sent(alert_key, str(top))


def check_revenue_concentration_alert():
    """C2: Rủi ro tập trung — top N khách chiếm > X% tổng doanh thu tháng mới nhất."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    top_n = int(_biz_threshold('concentration_top_n', 3))
    threshold = float(_biz_threshold('concentration_pct', 0.50))
    try:
        with engine.connect() as conn:
            sql = text('''
                WITH cm AS (
                    SELECT "CustomerCode" AS cc, SUM("TotalAmount") AS rev
                    FROM brv_hoadonhdr
                    WHERE "IsActive"=TRUE AND "IsHC"=FALSE
                      AND DATE_TRUNC('month',"DocDate"::timestamp) = (SELECT DATE_TRUNC('month', MAX("DocDate"::date)) FROM brv_hoadonhdr WHERE "IsActive"=TRUE)
                    GROUP BY 1
                    UNION ALL
                    SELECT "CustomerCode", SUM("TotalAmount")
                    FROM brvsx_hoadonhdr
                    WHERE "IsActive"=TRUE
                      AND DATE_TRUNC('month',"DocDate"::timestamp) = (SELECT DATE_TRUNC('month', MAX("DocDate"::date)) FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE)
                    GROUP BY 1
                ),
                agg AS (SELECT cc, SUM(rev) AS rev FROM cm GROUP BY cc)
                SELECT
                    (SELECT COALESCE(SUM(rev),0) FROM (SELECT rev FROM agg ORDER BY rev DESC LIMIT :n) t) AS top_sum,
                    (SELECT COALESCE(SUM(rev),0) FROM agg) AS total_sum
            ''')
            row = conn.execute(sql, {"n": top_n}).fetchone()
    except Exception as e:
        print(f"[ALERTS][concentration] Lỗi: {e}")
        return
    ratio = concentration_ratio(row[0], row[1])
    if ratio is None:
        return
    print(f"[ALERTS][concentration] Top {top_n} khách chiếm {ratio*100:.1f}% doanh thu (ngưỡng {threshold*100:.0f}%).")
    if ratio > threshold:
        alert_key = "revenue_concentration"
        if should_send_alert(alert_key, cooldown_hours=48, current_value=str(round(ratio, 4))):
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO RỦI RO TẬP TRUNG DOANH THU",
                severity="WARNING",
                summary=(f"Top {top_n} khách hàng chiếm {ratio*100:.1f}% tổng doanh thu tháng mới nhất "
                         f"(vượt {threshold*100:.0f}%) — phụ thuộc quá nhiều vào ít khách, rủi ro nếu mất 1 khách."),
                table_headers=[f"Doanh thu Top {top_n}", "Tổng doanh thu", "Tỷ trọng"],
                table_rows=[[format_vietnamese_money(row[0]), format_vietnamese_money(row[1]), f"{ratio*100:.1f}%"]],
                channels=("telegram", "teams")
            )
            record_alert_sent(alert_key, str(round(ratio, 4)))


# ---- Nhóm E: Hàng trả về ---------------------------------------------------

def check_return_rate_alert():
    """E: Tỷ lệ giá trị hàng trả về (brvsx_tralai) / doanh số ETC tháng mới nhất vượt ngưỡng."""
    from sqlalchemy import text
    engine = _alert_engine()
    if engine is None:
        return
    threshold = float(_biz_threshold('return_rate_pct', 0.05))
    try:
        with engine.connect() as conn:
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
            row = conn.execute(sql).fetchone()
    except Exception as e:
        print(f"[ALERTS][return_rate] Lỗi: {e}")
        return
    rate = return_rate(row[0], row[1])
    if rate is None:
        print("[ALERTS][return_rate] Chưa đủ dữ liệu (doanh số ETC = 0) để tính tỷ lệ trả hàng.")
        return
    print(f"[ALERTS][return_rate] Tỷ lệ trả hàng ETC = {rate*100:.2f}% (ngưỡng {threshold*100:.0f}%).")
    if rate > threshold:
        alert_key = "etc_return_rate"
        if should_send_alert(alert_key, cooldown_hours=24, current_value=str(round(rate, 4))):
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO TỶ LỆ HÀNG TRẢ VỀ CAO (ETC)",
                severity="WARNING",
                summary=(f"Tỷ lệ giá trị hàng trả về / doanh số ETC tháng mới nhất đạt {rate*100:.2f}% "
                         f"(vượt {threshold*100:.0f}%) — nghi vấn chất lượng lô/quá hạn/sai đơn."),
                table_headers=["Giá trị trả về", "Doanh số ETC", "Tỷ lệ trả"],
                table_rows=[[format_vietnamese_money(row[0]), format_vietnamese_money(row[1]), f"{rate*100:.2f}%"]],
                channels=("telegram", "teams")
            )
            record_alert_sent(alert_key, str(round(rate, 4)))


# ---- Nhóm F: KPI / nhân sự -------------------------------------------------

def check_zero_sales_rep_alert():
    """F: Nhân viên có chỉ tiêu nhưng doanh số = 0 trong kỳ (nghỉ ngầm / vấn đề địa bàn)."""
    from sqlalchemy import text
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
    except Exception as e:
        print(f"[ALERTS][zero_sales] Lỗi: {e}")
        return
    if not rows:
        print("[ALERTS][zero_sales] Không có nhân sự nào doanh số = 0.")
        return
    alert_key = "zero_sales_rep"
    if should_send_alert(alert_key, cooldown_hours=24, current_value=str(len(rows))):
        table = [[str(r[0]), r[1], str(r[2]), str(r[3]), format_vietnamese_money(r[4])] for r in rows]
        send_alert_to_all_channels(
            alert_name="CẢNH BÁO NHÂN SỰ DOANH SỐ BẰNG 0",
            severity="WARNING",
            summary="Các nhân sự sau có chỉ tiêu nhưng doanh số kỳ này = 0 — cần kiểm tra tình trạng làm việc/địa bàn.",
            table_headers=["Mã NV", "Tên NV", "Vùng", "Chức danh", "Chỉ tiêu"],
            table_rows=table,
            channels=("telegram", "teams")
        )
        record_alert_sent(alert_key, str(len(rows)))


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
            inv = conn.execute(text("SELECT COUNT(*) FROM inventory")).fetchone()[0]
    except Exception as e:
        print(f"[ALERTS][data_sanity] Không kiểm tra được (bỏ qua guard): {e}")
        return True
    if cust == 0 or inv == 0:
        alert_key = "data_sanity_zero"
        if should_send_alert(alert_key, cooldown_hours=6, current_value="zero"):
            send_alert_to_all_channels(
                alert_name="CẢNH BÁO HỆ THỐNG: DỮ LIỆU BẤT THƯỜNG (RỖNG)",
                severity="CRITICAL",
                summary=(f"Bảng công nợ ({cust} dòng) hoặc tồn kho ({inv} dòng) đang rỗng — nghi ETL lỗi. "
                         f"Đã TẠM DỪNG gửi các cảnh báo nghiệp vụ để tránh báo sai."),
                table_headers=["Bảng", "Số dòng"],
                table_rows=[["receivable_detail", str(cust)], ["inventory", str(inv)]],
                channels=("telegram", "teams")
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
                channels=("telegram", "teams")
            )
            record_alert_sent(alert_key, str(int(age_hours)))


if __name__ == '__main__':
    # Chạy thử test module cảnh báo cục bộ
    # Vì chưa set tài khoản SMTP thật nên send_email sẽ ghi warning ra log thay vì crash.
    erp_eng, crm_eng = get_db_engines()
    print("Khởi chạy kiểm tra cảnh báo...")
    run_alert_checks(erp_eng, crm_eng)
    print("Kiểm tra hoàn thành.")
