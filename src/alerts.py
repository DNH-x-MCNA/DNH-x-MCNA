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
                    table_rows=[[sku, item_name, str(qty), str(row['updated_at'])]]
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
                table_rows=rows
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
                table_rows=rows
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
                    table_rows=rows
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
                    table_rows=rows
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
                    table_rows=rows
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
            table_rows=rows
        )
        record_alert_sent(alert_key, "sent")

if __name__ == '__main__':
    # Chạy thử test module cảnh báo cục bộ
    # Vì chưa set tài khoản SMTP thật nên send_email sẽ ghi warning ra log thay vì crash.
    erp_eng, crm_eng = get_db_engines()
    print("Khởi chạy kiểm tra cảnh báo...")
    run_alert_checks(erp_eng, crm_eng)
    print("Kiểm tra hoàn thành.")
