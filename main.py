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
    format_vietnamese_money,
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
    flags = config.get('alert_feature_flags', {}) or {}

    # G1: health-check ETL trước (không phụ thuộc dữ liệu nghiệp vụ) — tắt tạm khi trỏ vào
    # Supabase dev/test (snapshot tĩnh, SyncAt không tăng nên sẽ báo "ETL đứng" liên tục sai).
    if flags.get('etl_freshness_check', True):
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

    if str(config.get('environment', 'local')).lower() == 'local' and erp_engine is not None and crm_engine is not None:
        print("[ALERTS] (môi trường 'local') Chạy thêm bộ MOCK ERP/CRM để dev test...")
        run_alert_checks(erp_engine, crm_engine)

    # Gửi hết card CRITICAL đã gom trong hàng đợi (xem src/notifier.py::flush_critical_teams_queue)
    # — BẮT BUỘC gọi ở CUỐI, sau khi TẤT CẢ check_*_alert() ở trên đã chạy xong, để gộp đúng mọi
    # alert CRITICAL phát hiện được trong CÙNG 1 chu kỳ quét thành 1 card duy nhất/webhook.
    flush_critical_teams_queue()

load_dotenv()

def _digest_table(metrics):
    """Chuyển metrics dict (doanh thu/công nợ/tồn kho THẬT từ Supabase) thành
    table_headers/table_rows để gửi qua Email (dùng cho bản tóm tắt dạng bảng đơn giản —
    email HTML đầy đủ hơn thì xem build_digest_email/DIGEST_EMAIL_TEMPLATE)."""
    headers = ["Chỉ số", "Giá trị"]
    change_pct = metrics['revenue']['change_pct']
    change_str = f"{change_pct:+.1f}% so kỳ trước" if change_pct is not None else "chưa đủ dữ liệu kỳ trước"
    rows = [
        ["Doanh thu OTC", format_vietnamese_money(metrics['revenue']['otc'])],
        ["Doanh thu ETC", format_vietnamese_money(metrics['revenue']['etc'])],
        ["Tổng doanh thu", f"{format_vietnamese_money(metrics['revenue']['total'])} ({change_str})"],
        ["Số hóa đơn OTC", str(metrics['revenue']['otc_invoice_count'])],
        ["Số hóa đơn ETC", str(metrics['revenue']['etc_invoice_count'])],
        ["Tổng số hóa đơn", str(metrics['revenue']['invoice_count'])],
        ["Mặt hàng tồn chết", str(metrics['inventory']['dead_stock_count'])],
        ["Mặt hàng sắp hết hàng", str(metrics['inventory']['near_stockout_count'])],
    ]
    if metrics['receivables']:
        period = metrics['receivables']['period']
        rows.append([f"Nợ quá hạn OTC (kỳ {period})", format_vietnamese_money(metrics['receivables'].get('otc_overdue'))])
        rows.append(["Dư nợ OTC", format_vietnamese_money(metrics['receivables'].get('otc_balance'))])
        rows.append(["Nợ quá hạn ETC", format_vietnamese_money(metrics['receivables'].get('etc_overdue'))])
        rows.append(["Dư nợ ETC", format_vietnamese_money(metrics['receivables'].get('etc_balance'))])
        rows.append(["Tổng dư nợ toàn công ty", format_vietnamese_money(metrics['receivables']['balance_end'])])
        
    # Thêm phần tổng hợp các cảnh báo trong ngày và trạng thái xử lý
    if metrics.get("alerts_summary"):
        rows.append(["━━━━━━━━━━━━━━━━━━━━━", "━━━━━━━━━━━━━━━━━━━━━"])
        rows.append(["CẢNH BÁO PHÁT SINH HÔM NAY", "TRẠNG THÁI HIỆN TẠI"])
        for alert in metrics["alerts_summary"]:
            status_str = "🔴 Chưa xử lý" if alert["active"] else "🟢 Đã giải quyết"
            rows.append([f"• {alert['name']}", status_str])
            
    return headers, rows

def send_daily_digest():
    """
    Trích xuất dữ liệu tổng hợp trong ngày và gửi qua Teams —
    quy tắc kênh: ALERT nghiệp vụ (src/alerts.py) và Daily Digest đi Teams (cần ngắn gọn, xem
    nhanh); Weekly/Monthly Report đi Outlook (báo cáo dài, đọc kỹ không cần đọc ngay). Đổi từ
    Email sang Teams 10/07/2026 theo yêu cầu — trước đó Daily Digest từng đi Email, nay khớp với
    ghi chú kênh đã có sẵn trong send_alert_to_all_channels().

    13/07/2026: đổi từ gửi 1 bản chung (không lọc region/channel -> chỉ khớp audience "C-Level
    Toàn quốc", 5 audience còn lại không nhận được Daily Digest) sang lặp qua report_recipients
    (giống _send_periodic_email_report của Weekly/Monthly) — mỗi audience nhận đúng phạm vi dữ
    liệu của mình. Gửi TRỰC TIẾP tới đúng teams_webhook của từng audience (send_teams_alert +
    webhook_url_override) thay vì qua send_alert_to_all_channels/_resolve_teams_webhooks — cơ chế
    đó tự fan-out theo region/channel KHỚP nên nếu gọi lặp sẽ khiến C-Level nhận trùng cả 6 bản
    (audience không giới hạn vùng/kênh luôn khớp mọi lần gọi).
    """
    print(f"[{datetime.now()}] Đang chuẩn bị báo cáo Daily Digest...")
    from ai_agent.chatbot import DNHChatbot

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
            region_label = DNHChatbot._REGION_NAMES_VI.get(region, region) if region else "Toàn quốc"
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
    """Nhãn phạm vi hiển thị trong email — dùng chung tên miền tiếng Việt đã kiểm chứng."""
    parts = []
    if region:
        from ai_agent.chatbot import DNHChatbot
        parts.append(DNHChatbot._REGION_NAMES_VI.get(region, region))
    if channel:
        parts.append(f"Kênh {channel}")
    return " — ".join(parts) if parts else "Toàn quốc, tất cả kênh"

def _send_periodic_email_report(get_metrics_fn, period_label, report_title):
    """
    Dùng chung cho Weekly/Monthly report — CHỈ gửi qua Email (báo cáo lớn, đọc kỹ không cần đọc
    ngay). Lặp qua config['report_recipients'] (Phần 3 — phân quyền theo cấp quản lý), gọi
    get_metrics_fn(region=.., channel=..) cho từng audience rồi gửi RIÊNG tới email của audience
    đó — mỗi audience nhận đúng phạm vi dữ liệu của mình, không gộp chung 1 bản như trước.
    Nếu config chưa có report_recipients (vd môi trường cũ chưa cập nhật) thì fallback gửi 1 bản
    không lọc như hành vi cũ, để không phá vỡ nơi gọi khác.
    """
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
            has_critical = metrics.get("has_critical")
            subject_prefix = "🔴 " if has_critical else "📊 "
            subject = f"{subject_prefix}{report_title}{subject_suffix} — {metrics.get('period_range', metrics['date'])}"
            html_content = build_digest_email(metrics, period_label=period_label, audience=audience, scope_label=scope)
            importance = "high" if has_critical else None
            if send_email(subject, html_content, recipient_override=emails or None, importance=importance):
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

    # 3. Chạy dạng Vòng lặp/Dịch vụ nền liên tục — vai trò LƯỚI AN TOÀN DỰ PHÒNG.
    # Cảnh báo thời gian thực chính được trigger NGAY sau mỗi lần đồng bộ Bravo (xem
    # scripts/sync_from_bravo_to_supabase.py::run_alert_checks_after_sync) — độ trễ gần như
    # bằng 0 vì chạy đúng lúc dữ liệu vừa cập nhật, thay vì đoán chu kỳ poll. Vòng lặp này chỉ
    # chạy lại định kỳ để bắt các trường hợp lỡ (sync thất bại giữa chừng, ETL bị đứng — xem
    # check_etl_freshness_alert). Báo cáo Daily/Weekly/Monthly đã tách sang scheduled task riêng
    # (DNH_Daily_Digest_1745/DNH_Weekly_Report/DNH_Monthly_Report — scripts/register_digest_schedule.bat),
    # không còn phụ thuộc vòng lặp này nên không cần poll theo phút nữa.
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

        # Chờ đến chu kỳ quét tiếp theo
        time.sleep(interval)

if __name__ == '__main__':
    main()
