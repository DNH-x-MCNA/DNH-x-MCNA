import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv
from src.database import get_db_engines, load_config
from src.etl import get_daily_digest_metrics, get_weekly_digest_metrics, get_monthly_digest_metrics
from src.notifier import build_digest_email, send_email, send_alert_to_all_channels
from src.alerts import (
    run_alert_checks,               # bản MOCK (ERP/CRM giả lập) — chỉ dùng ở môi trường 'local'
    run_smart_business_alerts,      # cảnh báo thật: nợ quá hạn / cháy kho / KPI thấp
    run_sales_kpi_insights_alert,   # báo cáo phân tích doanh số & KPI theo kênh/chức danh
    check_revenue_drop_alert,       # doanh thu giảm > ngưỡng so với kỳ trước
    check_credit_limit_exceeded_alert,   # nợ vượt hạn mức tín dụng (no-op nếu thiếu dữ liệu)
    # --- Trigger mở rộng (nhóm A-G) ---
    check_company_overdue_ratio_alert,   # A3: tỷ lệ nợ quá hạn toàn công ty
    check_overdue_customer_new_orders_alert,  # A2: khách quá hạn vẫn được lên đơn mới
    check_debt_aging_migration_alert,    # A1: nợ mới chuyển nhóm >45 ngày
    check_dead_stock_alert,              # B2: tồn kho chết / bán chậm
    check_near_expiry_alert,             # B1: cận date (no-op nếu thiếu dữ liệu hạn dùng)
    check_customer_churn_alert,          # C1: khách lớn sụt giảm / nguy cơ mất khách
    check_revenue_concentration_alert,   # C2: rủi ro tập trung doanh thu
    check_return_rate_alert,             # E: tỷ lệ hàng trả về cao (ETC)
    check_zero_sales_rep_alert,          # F: nhân sự doanh số = 0
    check_data_sanity_ok,                # G2: guard chặn alert khi dữ liệu rỗng/hỏng
    check_etl_freshness_alert,           # G1: ETL đứng (dữ liệu không refresh)
    should_send_alert, record_alert_sent
)


def run_all_alert_checks(config, erp_engine=None, crm_engine=None):
    """
    Chạy TOÀN BỘ cảnh báo nghiệp vụ THẬT của DNH đọc từ dữ liệu thật:
      - run_smart_business_alerts(): nợ quá hạn, cháy kho, KPI thấp
      - run_sales_kpi_insights_alert(): phân tích doanh số & KPI theo kênh/chức danh
      - check_revenue_drop_alert(): doanh thu giảm > ngưỡng so với kỳ trước
      - check_credit_limit_exceeded_alert(): nợ vượt hạn mức tín dụng (no-op nếu chưa có dữ liệu)

    Mỗi hàm tự bọc try/except bên trong nên lỗi 1 loại cảnh báo không làm chết cả vòng lặp.
    Bản MOCK run_alert_checks(ERP/CRM giả lập) CHỈ chạy khi environment == 'local' để dev test;
    production KHÔNG bao giờ chạy mock.
    """
    # G1: health-check ETL trước (không phụ thuộc dữ liệu nghiệp vụ)
    check_etl_freshness_alert()

    # G2: guard — nếu dữ liệu cốt lõi rỗng/hỏng thì DỪNG, không gửi alert nghiệp vụ sai
    if not check_data_sanity_ok():
        print("[ALERTS] Dữ liệu bất thường (rỗng) — bỏ qua các cảnh báo nghiệp vụ lần này.")
        return

    print("[ALERTS] Chạy các cảnh báo nghiệp vụ thật...")
    # Nhóm cảnh báo gốc
    run_smart_business_alerts()          # nợ quá hạn / cháy kho / KPI thấp
    run_sales_kpi_insights_alert()       # phân tích doanh số & KPI
    # Trigger mở rộng — mỗi hàm tự try/except, lỗi 1 cái không chặn cái khác
    check_revenue_drop_alert()
    check_credit_limit_exceeded_alert()
    check_company_overdue_ratio_alert()
    check_overdue_customer_new_orders_alert()
    check_debt_aging_migration_alert()
    check_dead_stock_alert()
    check_near_expiry_alert()
    check_customer_churn_alert()
    check_revenue_concentration_alert()
    check_return_rate_alert()
    check_zero_sales_rep_alert()

    if str(config.get('environment', 'local')).lower() == 'local' and erp_engine is not None and crm_engine is not None:
        print("[ALERTS] (môi trường 'local') Chạy thêm bộ MOCK ERP/CRM để dev test...")
        run_alert_checks(erp_engine, crm_engine)

load_dotenv()

def _digest_table(metrics):
    """Chuyển metrics dict (ERP/CRM) thành table_headers/table_rows để gửi qua Teams/Telegram."""
    headers = ["Chỉ số", "Giá trị"]
    rows = [
        ["Tổng đơn hàng", str(metrics['erp']['total_orders'])],
        ["Đơn hoàn thành", str(metrics['erp']['completed_orders'])],
        ["Đơn lỗi", str(metrics['erp']['failed_orders'])],
        ["Doanh thu", f"${metrics['erp']['total_revenue']:,.2f}"],
        ["Sản phẩm tồn kho thấp", str(metrics['erp']['low_inventory_count'])],
        ["Tổng số ca CRM", str(metrics['crm']['total_tickets'])],
        ["Ca đã giải quyết", str(metrics['crm']['resolved_tickets'])],
        ["Ca chưa xử lý", str(metrics['crm']['open_tickets'])],
        ["Ca khẩn cấp (Urgent)", str(metrics['crm']['urgent_open'])],
    ]
    return headers, rows

def send_daily_digest():
    """
    Trích xuất dữ liệu tổng hợp trong ngày và gửi qua Teams/Telegram
    (KHÔNG còn qua email — email chỉ dành cho báo cáo tuần/tháng, xem send_weekly_report/send_monthly_report).
    """
    print(f"[{datetime.now()}] Đang chuẩn bị báo cáo Daily Digest...")
    try:
        metrics = get_daily_digest_metrics()
        headers, rows = _digest_table(metrics)
        sent = send_alert_to_all_channels(
            alert_name=f"BÁO CÁO TỔNG HỢP HÀNG NGÀY ({metrics['date']})",
            severity="INFO",
            summary=f"Tổng hợp hoạt động ERP/CRM ngày {metrics['date']}.",
            table_headers=headers,
            table_rows=rows,
            channels=("telegram", "teams")
        )
        if sent:
            print(f"[{datetime.now()}] Báo cáo Daily Digest đã gửi thành công (Teams/Telegram).")
        else:
            print(f"[{datetime.now()}] Gửi báo cáo Daily Digest thất bại.")
        return sent
    except Exception as e:
        print(f"[{datetime.now()}] Lỗi khi tạo/gửi báo cáo Daily: {e}")
        return False

def _send_periodic_email_report(get_metrics_fn, period_label, report_title):
    """Dùng chung cho Weekly/Monthly report — CHỈ gửi qua Email (báo cáo lớn, đọc kỹ không cần đọc ngay)."""
    print(f"[{datetime.now()}] Đang chuẩn bị {report_title}...")
    try:
        metrics = get_metrics_fn()
        subject = f"📊 {report_title} — {metrics.get('period_range', metrics['date'])}"
        html_content = build_digest_email(metrics, period_label=period_label)
        if send_email(subject, html_content):
            print(f"[{datetime.now()}] {report_title} đã gửi thành công.")
            return True
        else:
            print(f"[{datetime.now()}] Gửi {report_title} thất bại.")
            return False
    except Exception as e:
        print(f"[{datetime.now()}] Lỗi khi tạo/gửi {report_title}: {e}")
        return False

def send_weekly_report():
    return _send_periodic_email_report(get_weekly_digest_metrics, "Weekly", "Báo cáo tổng hợp TUẦN")

def send_monthly_report():
    return _send_periodic_email_report(get_monthly_digest_metrics, "Monthly", "Báo cáo tổng hợp THÁNG")

def main():
    parser = argparse.ArgumentParser(description="Pipeline ETL & Cảnh báo thời gian thực ERP/CRM")
    parser.add_argument('--once', action='store_true', help='Chạy trích xuất và kiểm tra cảnh báo 1 lần duy nhất rồi thoát')
    parser.add_argument('--send-daily', action='store_true', help='Gửi báo cáo Daily Digest (Teams/Telegram) ngay lập tức rồi thoát')
    parser.add_argument('--send-weekly', action='store_true', help='Gửi báo cáo Weekly (Email) ngay lập tức rồi thoát')
    parser.add_argument('--send-monthly', action='store_true', help='Gửi báo cáo Monthly (Email) ngay lập tức rồi thoát')
    args = parser.parse_args()

    config = load_config()
    is_local = str(config.get('environment', 'local')).lower() == 'local'

    # Chỉ tạo mock ERP/CRM engine ở môi trường 'local' (production đọc dữ liệu thật, không cần mock).
    erp_engine = crm_engine = None
    if is_local:
        try:
            erp_engine, crm_engine = get_db_engines()
        except Exception as e:
            print(f"[{datetime.now()}] Cảnh báo: không tạo được mock ERP/CRM engine (bỏ qua bản mock): {e}")

    # 1. Nếu yêu cầu gửi báo cáo ngay lập tức
    if args.send_daily:
        send_daily_digest()
        sys.exit(0)
    if args.send_weekly:
        send_weekly_report()
        sys.exit(0)
    if args.send_monthly:
        send_monthly_report()
        sys.exit(0)

    # 2. Nếu yêu cầu chạy check 1 lần duy nhất
    if args.once:
        print(f"[{datetime.now()}] Bắt đầu quét cảnh báo nghiệp vụ DNH một lần...")
        run_all_alert_checks(config, erp_engine, crm_engine)
        print(f"[{datetime.now()}] Quét cảnh báo hoàn thành.")
        sys.exit(0)

    # 3. Chạy dạng Vòng lặp/Dịch vụ nền liên tục
    interval = int(config['scheduler'].get('etl_check_interval_seconds', 120))
    daily_time_str = config['scheduler'].get('daily_digest_time', '17:30')
    weekly_digest_day = config['scheduler'].get('weekly_digest_day', 'Monday')

    print("=" * 60)
    print(" KHỞI CHẠY PIPELINE ETL & CẢNH BÁO THỜI GIAN THỰC ERP/CRM ")
    print(f" - Tần suất quét cảnh báo: {interval} giây")
    print(f" - Giờ gửi báo cáo Daily (Teams/Telegram): {daily_time_str}")
    print(f" - Báo cáo Weekly (Email): {weekly_digest_day}, lúc {daily_time_str}")
    print(f" - Báo cáo Monthly (Email): ngày 1 hàng tháng, lúc {daily_time_str}")
    print(" Cửa sổ CMD này cần được mở để hệ thống tiếp tục chạy nền.")
    print("=" * 60)

    while True:
        try:
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            current_date_str = now.strftime("%Y-%m-%d")

            # Quét dữ liệu và kiểm tra ngưỡng cảnh báo nghiệp vụ thật của DNH
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Đang quét cảnh báo nghiệp vụ DNH...")
            run_all_alert_checks(config, erp_engine, crm_engine)

            # Kiểm tra xem đã đến giờ gửi báo cáo định kỳ chưa
            if current_time_str == daily_time_str:
                # Daily digest (Teams/Telegram) — mỗi ngày
                daily_alert_key = f"daily_digest:{current_date_str}"
                if should_send_alert(daily_alert_key, cooldown_hours=23, current_value="sent"):
                    send_daily_digest()
                    record_alert_sent(daily_alert_key, "sent")

                # Weekly report (Email) — đúng ngày trong tuần cấu hình (mặc định Monday)
                if now.strftime('%A') == weekly_digest_day:
                    weekly_alert_key = f"weekly_report:{now.strftime('%Y-W%W')}"
                    if should_send_alert(weekly_alert_key, cooldown_hours=23, current_value="sent"):
                        send_weekly_report()
                        record_alert_sent(weekly_alert_key, "sent")

                # Monthly report (Email) — ngày 1 hàng tháng
                if now.day == 1:
                    monthly_alert_key = f"monthly_report:{now.strftime('%Y-%m')}"
                    if should_send_alert(monthly_alert_key, cooldown_hours=23, current_value="sent"):
                        send_monthly_report()
                        record_alert_sent(monthly_alert_key, "sent")

        except KeyboardInterrupt:
            print("\nDừng dịch vụ theo yêu cầu người dùng.")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Lỗi hệ thống trong vòng lặp chính: {e}")

        # Chờ đến chu kỳ quét tiếp theo
        time.sleep(interval)

if __name__ == '__main__':
    main()
