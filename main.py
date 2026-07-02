import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv
from src.database import get_db_engines, load_config
from src.etl import get_daily_digest_metrics
from src.notifier import build_daily_digest_email, send_email
from src.alerts import run_alert_checks, should_send_alert, record_alert_sent

load_dotenv()

def send_daily_digest():
    """
    Trích xuất dữ liệu tổng hợp trong ngày và gửi email báo cáo
    """
    print(f"[{datetime.now()}] Đang chuẩn bị báo cáo Daily Digest...")
    try:
        metrics = get_daily_digest_metrics()
        subject = f"📊 Báo cáo tổng hợp hoạt động ngày {metrics['date']}"
        html_content = build_daily_digest_email(metrics)
        
        if send_email(subject, html_content):
            print(f"[{datetime.now()}] Báo cáo Daily Digest đã gửi thành công.")
            return True
        else:
            print(f"[{datetime.now()}] Gửi báo cáo Daily Digest thất bại.")
            return False
    except Exception as e:
        print(f"[{datetime.now()}] Lỗi khi tạo/gửi báo cáo Daily: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Pipeline ETL & Cảnh báo thời gian thực ERP/CRM")
    parser.add_argument('--once', action='store_true', help='Chạy trích xuất và kiểm tra cảnh báo 1 lần duy nhất rồi thoát')
    parser.add_argument('--send-daily', action='store_true', help='Gửi báo cáo Daily Digest ngay lập tức rồi thoát')
    args = parser.parse_args()

    erp_engine, crm_engine = get_db_engines()
    config = load_config()
    
    # 1. Nếu yêu cầu gửi báo cáo Daily ngay lập tức
    if args.send_daily:
        send_daily_digest()
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
    
    print("=" * 60)
    print(" KHỞI CHẠY PIPELINE ETL & CẢNH BÁO THỜI GIAN THỰC ERP/CRM ")
    print(f" - Tần suất quét cảnh báo: {interval} giây")
    print(f" - Giờ gửi báo cáo Daily: {daily_time_str}")
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
            
            # Kiểm tra xem đã đến giờ gửi Daily Digest chưa
            if current_time_str == daily_time_str:
                daily_alert_key = f"daily_digest:{current_date_str}"
                # Chỉ gửi 1 lần duy nhất trong ngày hôm nay
                # Sử dụng hàm should_send_alert với cooldown 23 tiếng
                if should_send_alert(daily_alert_key, cooldown_hours=23, current_value="sent"):
                    send_daily_digest()
                    record_alert_sent(daily_alert_key, "sent")
            
        except KeyboardInterrupt:
            print("\nDừng dịch vụ theo yêu cầu người dùng.")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Lỗi hệ thống trong vòng lặp chính: {e}")
            
        # Chờ đến chu kỳ quét tiếp theo
        time.sleep(interval)

if __name__ == '__main__':
    main()
