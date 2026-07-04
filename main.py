import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv
from src.database import get_db_engines, load_config
from src.etl import get_daily_digest_metrics, get_weekly_digest_metrics, get_monthly_digest_metrics
from src.notifier import build_digest_email, send_email, send_alert_to_all_channels
from src.alerts import run_alert_checks, should_send_alert, record_alert_sent

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

    erp_engine, crm_engine = get_db_engines()
    config = load_config()

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
        print(f"[{datetime.now()}] Bắt đầu quét dữ liệu ERP/CRM một lần...")
        run_alert_checks(erp_engine, crm_engine)
        print(f"[{datetime.now()}] Quét dữ liệu hoàn thành.")
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

            # Quét dữ liệu và kiểm tra ngưỡng cảnh báo
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Đang quét dữ liệu ERP/CRM...")
            run_alert_checks(erp_engine, crm_engine)

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
