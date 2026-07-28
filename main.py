import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv
from src.database import get_db_engines, load_config
from src.etl import get_daily_digest_metrics, get_weekly_digest_metrics, get_monthly_digest_metrics
from src.notifier import build_digest_email, send_email, flush_critical_teams_queue, send_teams_alert
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
    check_kpi_sales_force_risk_alert,    # F2: rủi ro KPI khối OTC miền Nam (QĐ 0429-2, no-op nếu thiếu dữ liệu)
    check_daily_kpi_pace_alert,          # F3: nhịp KPI ngày từng TDV (đỏ/vàng/xanh, OTC only)
    check_kpi_milestone_drop_alert,      # F4: mốc ngày 10/20 giảm >5% so TB 5 tháng trước (kênh + từng TDV)
    check_data_sanity_ok,                # G2: guard chặn alert khi dữ liệu rỗng/hỏng
    check_etl_freshness_alert,           # G1: ETL đứng (dữ liệu không refresh)
    check_kpi_revenue_reconciliation_alert,  # G3: doanh thu KPI lệch so với hóa đơn thực tế (OTC)
    format_vietnamese_money,
)


def _is_alert_business_hours(config):
    """15/07/2026: chỉ cho phép quét/gửi cảnh báo nghiệp vụ thời gian thực trong giờ hành chính
    (config['scheduler']::alert_business_hours_start/end/days) — xem ghi chú trong config.yaml.
    Không có khung giờ trong config (môi trường cũ) -> mặc định luôn cho phép (hành vi cũ)."""
    sched = config.get('scheduler', {}) or {}
    start_str = sched.get('alert_business_hours_start')
    end_str = sched.get('alert_business_hours_end')
    days = sched.get('alert_business_days')
    if not start_str or not end_str or not days:
        return True
    now = datetime.now()
    try:
        int_days = [int(d) for d in days]
        if now.isoweekday() not in int_days:
            return False
    except Exception:
        if now.isoweekday() not in days:
            return False

    start_h, start_m = (int(x) for x in start_str.split(':'))
    end_h, end_m = (int(x) for x in end_str.split(':'))
    start_t = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_t = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start_t <= now < end_t


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
    if not _is_alert_business_hours(config):
        print(f"[ALERTS] Ngoài giờ hành chính ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) — bỏ qua chu kỳ quét cảnh báo này.")
        return

    flags = config.get('alert_feature_flags', {}) or {}

    if flags.get('etl_freshness_check', True):
        check_etl_freshness_alert()

    if not check_data_sanity_ok():
        print("[ALERTS] Dữ liệu bất thường (rỗng) — bỏ qua các cảnh báo nghiệp vụ lần này.")
        return

    print("[ALERTS] Chạy các cảnh báo nghiệp vụ thật...")

    run_smart_business_alerts()          # nợ quá hạn / cháy kho / KPI thấp
    run_sales_kpi_insights_alert()       # phân tích doanh số & KPI
    check_revenue_drop_alert()
    if flags.get('credit_limit_check', True):
        check_credit_limit_exceeded_alert()
    check_company_overdue_ratio_alert()
    check_overdue_customer_new_orders_alert()
    check_debt_aging_migration_alert()
    check_dead_stock_alert()
    if flags.get('near_expiry_check', True):
        check_near_expiry_alert()
    check_customer_churn_alert()
    check_revenue_concentration_alert()
    check_return_rate_alert()
    check_zero_sales_rep_alert()
    if flags.get('kpi_sales_force_risk_check', True):
        check_kpi_sales_force_risk_alert()
    check_daily_kpi_pace_alert()
    check_kpi_milestone_drop_alert()
    check_kpi_revenue_reconciliation_alert()

    if str(config.get('environment', 'local')).lower() == 'local' and erp_engine is not None and crm_engine is not None:
        print("[ALERTS] (môi trường 'local') Chạy thêm bộ MOCK ERP/CRM để dev test...")
        run_alert_checks(erp_engine, crm_engine)

    flush_critical_teams_queue()

load_dotenv()

def _digest_table(metrics):
    headers = ["Chỉ số", "Giá trị"]
    change_pct = metrics['revenue']['change_pct']
    prev_label = metrics['revenue'].get('prev_period_label', '')
    change_str = f"{change_pct:+.1f}% so kỳ {prev_label}" if change_pct is not None else "chưa đủ dữ liệu kỳ trước"
    scoped_channel = metrics.get('channel')
    rows = []
    if scoped_channel != "ETC":
        rows.append(["Doanh thu OTC", format_vietnamese_money(metrics['revenue']['otc'])])
    if scoped_channel != "OTC":
        rows.append(["Doanh thu ETC", format_vietnamese_money(metrics['revenue']['etc'])])
    rows.append(["Tổng doanh thu", f"{format_vietnamese_money(metrics['revenue']['total'])} ({change_str})"])
    if scoped_channel != "ETC":
        rows.append(["Số hóa đơn OTC", str(metrics['revenue']['otc_invoice_count'])])
    if scoped_channel != "OTC":
        rows.append(["Số hóa đơn ETC", str(metrics['revenue']['etc_invoice_count'])])
    rows.append(["Tổng số hóa đơn", str(metrics['revenue']['invoice_count'])])
    rows.append(["Mặt hàng tồn chết", str(metrics['inventory']['dead_stock_count'])])
    rows.append(["Mặt hàng sắp hết hàng", str(metrics['inventory']['near_stockout_count'])])
    for h in metrics.get('highlights', []):
        rows.append([f"Cảnh báo: {h['label']}", f"{h['value_display']} (lúc {h['sent_at_display']})"])

    return headers, rows

def send_daily_digest():
    print(f"[{datetime.now()}] Đang chuẩn bị báo cáo Daily Digest...")
    from src.region_map import REGION_NAMES_VI

    config = load_config()
    recipients = config.get('report_recipients') or []
    if not recipients:
        print(f"[{datetime.now()}] Chưa cấu hình report_recipients — gửi Daily Digest bản không lọc (hành vi cũ).")
        recipients = [{"audience": None, "region": None, "channel": None, "teams_webhook": None}]

    overall_ok = True
    for r in recipients:
        audience = r.get('audience')
        region = r.get('region')
        channel = r.get('channel')
        webhook = (r.get('teams_webhook') or '').strip() or None
        try:
            metrics = get_daily_digest_metrics(region=region, channel=channel)
            headers, rows = _digest_table(metrics)
            region_label = REGION_NAMES_VI.get(region, region) if region else "Toàn quốc"
            title = f"BÁO CÁO TỔNG HỢP HÀNG NGÀY ({metrics['date']})" + (f" — {audience}" if audience else "")
            summary = (
                f"Tổng hợp hoạt động ERP/CRM ngày {metrics['date']}."
                f" Dữ liệu cập nhật lúc {metrics.get('updated_at', 'N/A')}."
            )
            sent = send_teams_alert(
                title=title,
                summary=summary,
                table_headers=headers,
                table_rows=rows,
                severity="INFO",
                period=metrics['date'],
                channel=channel or "OTC + ETC (gộp)",
                region=region_label,
                webhook_url_override=webhook,
            )
            if sent:
                print(f"[{datetime.now()}] Daily Digest cho '{audience or 'mặc định'}' đã gửi thành công.")
            else:
                print(f"[{datetime.now()}] Gửi Daily Digest cho '{audience or 'mặc định'}' thất bại.")
                overall_ok = False
        except Exception as e:
            print(f"[{datetime.now()}] Lỗi khi tạo/gửi Daily Digest cho '{audience or 'mặc định'}': {e}")
            overall_ok = False
    return overall_ok

def _scope_label(region, channel):
    parts = []
    if region:
        from src.region_map import REGION_NAMES_VI
        parts.append(REGION_NAMES_VI.get(region, region))
    if channel:
        parts.append(f"Kênh {channel}")
    return " — ".join(parts) if parts else "Toàn quốc, tất cả kênh"

def _send_periodic_email_report(get_metrics_fn, period_label, report_title):
    config = load_config()
    recipients = config.get('report_recipients') or []
    if not recipients:
        print(f"[{datetime.now()}] Chưa cấu hình report_recipients — gửi {report_title} bản không lọc (hành vi cũ).")
        recipients = [{"audience": None, "region": None, "channel": None, "emails": None}]

    overall_ok = True
    for r in recipients:
        audience = r.get('audience')
        region = r.get('region')
        channel = r.get('channel')
        emails = [e for e in (r.get('emails') or []) if e]
        print(f"[{datetime.now()}] Đang chuẩn bị {report_title} cho '{audience or 'mặc định'}'...")
        try:
            metrics = get_metrics_fn(region=region, channel=channel)
            scope = _scope_label(region, channel)
            subject_suffix = f" ({audience})" if audience else ""
            subject = f"{report_title}{subject_suffix} — {metrics.get('period_range', metrics['date'])}"
            html_content = build_digest_email(metrics, period_label=period_label, audience=audience, scope_label=scope)
            if send_email(subject, html_content, recipient_override=emails or None, importance=None):
                print(f"[{datetime.now()}] {report_title} cho '{audience or 'mặc định'}' đã gửi thành công.")
            else:
                print(f"[{datetime.now()}] Gửi {report_title} cho '{audience or 'mặc định'}' thất bại.")
                overall_ok = False
        except Exception as e:
            print(f"[{datetime.now()}] Lỗi khi tạo/gửi {report_title} cho '{audience or 'mặc định'}': {e}")
            overall_ok = False
    return overall_ok

def send_weekly_report():
    return _send_periodic_email_report(get_weekly_digest_metrics, "Weekly", "Báo cáo tổng hợp TUẦN")

def send_monthly_report():
    return _send_periodic_email_report(get_monthly_digest_metrics, "Monthly", "Báo cáo tổng hợp THÁNG")

def main():
    parser = argparse.ArgumentParser(description="Pipeline ETL & Cảnh báo thời gian thực ERP/CRM")
    parser.add_argument('--once', action='store_true', help='Chạy trích xuất và kiểm tra cảnh báo 1 lần duy nhất rồi thoát')
    parser.add_argument('--send-daily', action='store_true', help='Gửi báo cáo Daily Digest (Email) ngay lập tức rồi thoát')
    parser.add_argument('--send-weekly', action='store_true', help='Gửi báo cáo Weekly (Email) ngay lập tức rồi thoát')
    parser.add_argument('--send-monthly', action='store_true', help='Gửi báo cáo Monthly (Email) ngay lập tức rồi thoát')
    args = parser.parse_args()

    config = load_config()
    is_local = str(config.get('environment', 'local')).lower() == 'local'

    erp_engine = crm_engine = None
    if is_local:
        try:
            erp_engine, crm_engine = get_db_engines()
        except Exception as e:
            print(f"[{datetime.now()}] Cảnh báo: không tạo được mock ERP/CRM engine (bỏ qua bản mock): {e}")

    if args.send_daily:
        send_daily_digest()
        sys.exit(0)
    if args.send_weekly:
        send_weekly_report()
        sys.exit(0)
    if args.send_monthly:
        send_monthly_report()
        sys.exit(0)

    if args.once:
        print(f"[{datetime.now()}] Bắt đầu quét cảnh báo nghiệp vụ DNH một lần...")
        run_all_alert_checks(config, erp_engine, crm_engine)
        print(f"[{datetime.now()}] Quét cảnh báo hoàn thành.")
        sys.exit(0)

    interval = int(config['scheduler'].get('etl_check_interval_seconds', 3600))

    print("=" * 60)
    print(" KHỞI CHẠY PIPELINE CẢNH BÁO NGHIỆP VỤ (LƯỚI AN TOÀN DỰ PHÒNG) ")
    print(f" - Tần suất quét dự phòng: {interval} giây")
    print(" - Cảnh báo thời gian thực chính: trigger ngay sau mỗi lần đồng bộ Bravo (5 lần/ngày)")
    print(" - Báo cáo Daily/Weekly/Monthly: chạy qua scheduled task riêng, không qua vòng lặp này")
    print(" Cửa sổ CMD này cần được mở để hệ thống tiếp tục chạy nền.")
    print("=" * 60)

    while True:
        try:
            now = datetime.now()
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Đang quét cảnh báo nghiệp vụ DNH (lưới an toàn dự phòng)...")
            run_all_alert_checks(config, erp_engine, crm_engine)
        except KeyboardInterrupt:
            print("\nDừng dịch vụ theo yêu cầu người dùng.")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Lỗi hệ thống trong vòng lặp chính: {e}")

        time.sleep(interval)

if __name__ == '__main__':
    main()
