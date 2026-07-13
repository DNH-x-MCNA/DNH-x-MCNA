import os
import sys
import time
import sqlite3
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from dotenv import load_dotenv
from src.database import load_config
import json
import urllib.request
from urllib.parse import quote

# Đảm bảo terminal/log ghi nhận được tiếng Việt có dấu
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'alerts_state.db')


def _log_alert_severity(alert_name, severity):
    """
    Ghi lại (tên alert, mức độ, thời điểm) vào data/alerts_state.db mỗi khi 1 alert THỰC SỰ được
    gửi — phục vụ báo cáo Weekly/Monthly (main.py::_send_periodic_email_report) biết kỳ vừa qua
    có alert CRITICAL nào không, để gắn cờ Outlook Importance:High cho đúng email digest đó.

    KHÔNG dùng chung bảng sent_alerts (src/alerts.py) vì bảng đó chỉ giữ TRẠNG THÁI MỚI NHẤT theo
    alert_key (ghi đè liên tục, phục vụ cooldown) — không phải lịch sử theo thời gian như cần ở
    đây. Lỗi ghi log không được chặn việc gửi alert thật (chỉ log + bỏ qua).
    """
    try:
        os.makedirs(os.path.dirname(STATE_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(STATE_DB_PATH)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alert_severity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                sent_at TIMESTAMP NOT NULL
            )
        ''')
        conn.execute(
            'INSERT INTO alert_severity_log (alert_name, severity, sent_at) VALUES (?, ?, ?)',
            (alert_name, severity, datetime.now())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[NOTIFIER] Không ghi được alert_severity_log (bỏ qua, không ảnh hưởng gửi alert): {e}")


# HTML template for alerts
ALERT_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333333; margin: 0; padding: 20px; background-color: #f9f9fb; }
        .card { max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; border: 1px solid #e1e1e7; }
        .header { padding: 24px; color: #ffffff; font-weight: bold; font-size: 20px; text-transform: uppercase; letter-spacing: 0.5px; }
        .header.critical { background-color: #e53e3e; background: linear-gradient(135deg, #e53e3e 0%, #b7791f 100%); }
        .header.warning { background-color: #dd6b20; background: linear-gradient(135deg, #dd6b20 0%, #d69e2e 100%); }
        .header.info { background-color: #059669; background: linear-gradient(135deg, #059669 0%, #10b981 100%); }
        .content { padding: 24px; line-height: 1.6; }
        .alert-title { font-size: 18px; font-weight: bold; margin-bottom: 8px; color: #1a202c; }
        .alert-desc { font-size: 14px; color: #718096; margin-bottom: 20px; }
        .kpi-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        .kpi-table th { text-align: left; padding: 8px; background-color: #f7fafc; border-bottom: 2px solid #edf2f7; font-size: 12px; color: #4a5568; text-transform: uppercase; }
        .kpi-table td { padding: 10px 8px; border-bottom: 1px solid #edf2f7; font-size: 14px; color: #2d3748; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-transform: uppercase; }
        .badge.critical { background-color: #fed7d7; color: #9b2c2c; }
        .badge.warning { background-color: #feebc8; color: #9c4221; }
        .footer { background: #f7fafc; padding: 16px 24px; text-align: center; font-size: 12px; color: #a0aec0; border-top: 1px solid #edf2f7; }
    </style>
</head>
<body>
    <div class="card">
        <div class="header {{ severity.lower() }}">
            🚨 {{ alert_name }}
        </div>
        <div class="content">
            <div class="alert-title">{{ summary }}</div>
            <div class="alert-desc">Hệ thống phát hiện chỉ số đã vượt ngưỡng cảnh báo an toàn. Chi tiết bên dưới:</div>
            
            <table class="kpi-table">
                <thead>
                    <tr>
                        {% for col in table_headers %}
                        <th>{{ col }}</th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    {% for row in table_rows %}
                    <tr>
                        {% for cell in row %}
                        <td>{{ cell }}</td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            
            <p style="font-size: 13px; color: #e53e3e; font-weight: bold; background: #fff5f5; padding: 10px; border-radius: 6px; border-left: 4px solid #e53e3e;">
                Lưu ý: Cảnh báo này sẽ tạm thời bị khóa gửi lặp trong vòng 1-4 giờ tới để tránh spam hộp thư của bạn, trừ khi lỗi nghiêm trọng hơn xảy ra.
            </p>
        </div>
        <div class="footer">
            Hệ thống Giám sát ERP/CRM tự động &bull; Thời gian ghi nhận: {{ timestamp }}
        </div>
    </div>
</body>
</html>
"""

# HTML template dùng chung cho digest định kỳ (Daily/Weekly/Monthly) qua Email
DIGEST_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333333; margin: 0; padding: 20px; background-color: #f4f5f8; }
        .container { max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); overflow: hidden; border: 1px solid #e2e8f0; }
        .header { background-color: #1e3a8a; background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px 24px; color: #ffffff; }
        .header h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }
        .header p { margin: 5px 0 0 0; font-size: 14px; opacity: 0.9; }
        .content { padding: 24px; }
        .section-title { font-size: 16px; font-weight: 700; color: #1e3a8a; margin-top: 24px; margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .grid { display: block; width: 100%; margin: -8px 0; }
        .col { display: inline-block; vertical-align: top; box-sizing: border-box; }
        .kpi-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center; height: 100%; box-sizing: border-box; }
        .kpi-card .val { font-size: 20px; font-weight: 700; color: #1e293b; margin: 5px 0; }
        .kpi-card .lbl { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .kpi-card.failed { border-left: 4px solid #ef4444; }
        .kpi-card.success { border-left: 4px solid #10b981; }
        .data-table { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 20px; }
        .data-table th { text-align: left; padding: 10px; background-color: #f1f5f9; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #475569; text-transform: uppercase; }
        .data-table td { padding: 12px 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px; color: #334155; }
        .no-data { font-size: 13px; color: #64748b; font-style: italic; padding: 10px 0; }
        .trend-up { color: #10b981; font-size: 13px; font-weight: 600; }
        .trend-down { color: #ef4444; font-size: 13px; font-weight: 600; }
        .footer { background: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>BÁO CÁO TỔNG HỢP HOẠT ĐỘNG {{ period_label|upper }}</h1>
            <p>{{ metrics.period_range or metrics.date }}</p>
            {% if audience %}
            <p style="margin: 8px 0 0 0; font-size: 13px; opacity: 0.9;">
                Báo cáo dành cho: <strong>{{ audience }}</strong>{% if scope_label %} &bull; Phạm vi: {{ scope_label }}{% endif %}
            </p>
            {% endif %}
            {% if metrics.updated_at %}
            <p style="margin: 4px 0 0 0; font-size: 12px; opacity: 0.75;">Dữ liệu cập nhật lúc {{ metrics.updated_at }}</p>
            {% endif %}
        </div>

        <div class="content">
            {% if metrics.has_critical %}
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #ef4444; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #991b1b; font-weight: 600;">
                🔴 Kỳ này có ít nhất 1 cảnh báo mức CRITICAL — xem chi tiết ở mục "Điểm Nổi Bật Trong Kỳ" bên dưới.
            </div>
            {% endif %}

            {% if metrics.highlights %}
            <!-- Điểm nổi bật Section — nối luồng cảnh báo thời gian thực với báo cáo định kỳ -->
            <div class="section-title">Điểm Nổi Bật Trong Kỳ</div>
            <ul style="margin: 0 0 20px 0; padding-left: 20px; font-size: 13px; color: #334155;">
                {% for h in metrics.highlights %}
                <li style="margin-bottom: 6px;"><strong>{{ h.label }}</strong> — {{ h.sent_at_display }} (giá trị: {{ h.value_display }})</li>
                {% endfor %}
            </ul>
            {% endif %}

            <!-- Doanh thu Section -->
            <div class="section-title">Doanh Thu (OTC + ETC)</div>
            <div class="grid">
                <!--[if mso]>
                <table role="presentation" width="100%" style="border-collapse: collapse; border: 0;"><tr><td width="25%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 145px; padding: 8px;">
                    <div class="kpi-card">
                        <div class="lbl">Doanh Thu OTC</div>
                        <div class="val">{{ "{:,.0f}".format(metrics.revenue.otc) }} đ</div>
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="25%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 145px; padding: 8px;">
                    <div class="kpi-card">
                        <div class="lbl">Doanh Thu ETC</div>
                        <div class="val">{{ "{:,.0f}".format(metrics.revenue.etc) }} đ</div>
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="25%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 145px; padding: 8px;">
                    <div class="kpi-card success">
                        <div class="lbl">Tổng Doanh Thu</div>
                        <div class="val" style="color: #10b981;">{{ "{:,.0f}".format(metrics.revenue.total) }} đ</div>
                        {% if metrics.revenue.change_pct is not none %}
                        <div class="{{ 'trend-up' if metrics.revenue.change_pct >= 0 else 'trend-down' }}">
                            {{ "%+.1f"|format(metrics.revenue.change_pct) }}% so kỳ trước
                        </div>
                        {% else %}
                        <div class="no-data">Chưa đủ dữ liệu kỳ trước</div>
                        {% endif %}
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="25%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 145px; padding: 8px;">
                    <div class="kpi-card">
                        <div class="lbl">Số Hóa Đơn (OTC/ETC)</div>
                        <div class="val">{{ metrics.revenue.otc_invoice_count }} / {{ metrics.revenue.etc_invoice_count }}</div>
                        <div class="no-data">Tổng: {{ metrics.revenue.invoice_count }}</div>
                    </div>
                </div>
                <!--[if mso]>
                </td></tr></table>
                <![endif]-->
            </div>

            <!-- Top khách hàng Section -->
            <div class="section-title">Top 5 Khách Hàng Theo Doanh Thu</div>
            <div class="grid">
                <!--[if mso]>
                <table role="presentation" width="100%" style="border-collapse: collapse; border: 0;"><tr><td width="50%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 290px; padding: 8px;">
                    <p style="font-size:12px; font-weight:700; color:#64748b; text-transform:uppercase; margin: 0 0 6px;">Kênh OTC</p>
                    {% if metrics.top_customers_otc %}
                    <table class="data-table">
                        <thead><tr><th>Khách hàng</th><th>Doanh thu</th></tr></thead>
                        <tbody>
                            {% for c in metrics.top_customers_otc %}
                            <tr><td>{{ c.name }}</td><td>{{ "{:,.0f}".format(c.revenue) }} đ</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <p class="no-data">Không có dữ liệu.</p>
                    {% endif %}
                </div>
                <!--[if mso]>
                </td><td width="50%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 290px; padding: 8px;">
                    <p style="font-size:12px; font-weight:700; color:#64748b; text-transform:uppercase; margin: 0 0 6px;">Kênh ETC</p>
                    {% if metrics.top_customers_etc %}
                    <table class="data-table">
                        <thead><tr><th>Khách hàng</th><th>Doanh thu</th></tr></thead>
                        <tbody>
                            {% for c in metrics.top_customers_etc %}
                            <tr><td>{{ c.name }}</td><td>{{ "{:,.0f}".format(c.revenue) }} đ</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% else %}
                    <p class="no-data">Không có dữ liệu.</p>
                    {% endif %}
                </div>
                <!--[if mso]>
                </td></tr></table>
                <![endif]-->
            </div>

            {% if metrics.trend %}
            <!-- Xu hướng trong kỳ Section — weekly: theo NGÀY, monthly: theo TUẦN -->
            <div class="section-title">Xu Hướng Doanh Thu Trong Kỳ</div>
            
            {% if trend_chart_svg %}
            <div style="margin-bottom: 20px; text-align: center;">
                {{ trend_chart_svg | safe }}
            </div>
            {% endif %}

            <table class="data-table">
                <thead><tr><th>Giai đoạn</th><th>Doanh thu</th></tr></thead>
                <tbody>
                    {% for t in metrics.trend %}
                    <tr><td>{{ t.label }}</td><td>{{ "{:,.0f}".format(t.revenue) }} đ</td></tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}

            {% if metrics.region_breakdown %}
            <!-- Breakdown theo Vùng Section — chỉ hiện khi báo cáo KHÔNG lọc sẵn theo 1 vùng cụ thể -->
            <div class="section-title">Doanh Thu Theo Vùng</div>
            <table class="data-table">
                <thead><tr><th>Vùng</th><th>Doanh thu</th></tr></thead>
                <tbody>
                    {% for r in metrics.region_breakdown %}
                    <tr><td>{{ r.region }}</td><td>{{ "{:,.0f}".format(r.revenue) }} đ</td></tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}

            {% if metrics.kpi_summary %}
            <!-- Tóm tắt KPI Section — kpi_summary là SNAPSHOT hiện tại, không lưu lịch sử theo kỳ -->
            <div class="section-title">Tóm Tắt KPI Đội Ngũ (tính đến hiện tại)</div>
            <div class="grid">
                <!--[if mso]>
                <table role="presentation" width="100%" style="border-collapse: collapse; border: 0;"><tr><td width="33.3%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 190px; padding: 8px;">
                    <div class="kpi-card success">
                        <div class="lbl">Đạt Chỉ Tiêu</div>
                        <div class="val" style="color: #10b981;">{{ metrics.kpi_summary.achieved_count }}/{{ metrics.kpi_summary.total_count }}</div>
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="33.3%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 190px; padding: 8px;">
                    <div class="kpi-card">
                        <div class="lbl">% Hoàn Thành Toàn Đội</div>
                        <div class="val">{% if metrics.kpi_summary.team_pct is not none %}{{ "%.1f"|format(metrics.kpi_summary.team_pct) }}%{% else %}—{% endif %}</div>
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="33.3%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 190px; padding: 8px;">
                    <div class="kpi-card">
                        <div class="lbl">Tổng Doanh Số Đạt</div>
                        <div class="val">{{ "{:,.0f}".format(metrics.kpi_summary.total_amount) }} đ</div>
                    </div>
                </div>
                <!--[if mso]>
                </td></tr></table>
                <![endif]-->
            </div>
            {% endif %}

            {% if metrics.receivables %}
            <!-- Công nợ Section (chỉ hiện khi dữ liệu còn mới — cùng tháng hoặc tháng liền trước kỳ báo cáo) -->
            <div class="section-title">Công Nợ (Kỳ {{ metrics.receivables.period }})</div>
            <div class="grid">
                <!--[if mso]>
                <table role="presentation" width="100%" style="border-collapse: collapse; border: 0;"><tr><td width="50%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 290px; padding: 8px;">
                    <div class="kpi-card failed">
                        <div class="lbl">Nợ Quá Hạn</div>
                        <div class="val" style="color: #ef4444;">{{ "{:,.0f}".format(metrics.receivables.total_overdue) }} đ</div>
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="50%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 290px; padding: 8px;">
                    <div class="kpi-card">
                        <div class="lbl">Tổng Dư Nợ</div>
                        <div class="val">{{ "{:,.0f}".format(metrics.receivables.balance_end) }} đ</div>
                    </div>
                </div>
                <!--[if mso]>
                </td></tr></table>
                <![endif]-->
            </div>
            {% endif %}

            <!-- Tồn kho Section -->
            <div class="section-title">Tồn Kho</div>
            <div class="grid">
                <!--[if mso]>
                <table role="presentation" width="100%" style="border-collapse: collapse; border: 0;"><tr><td width="50%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 290px; padding: 8px;">
                    <div class="kpi-card failed">
                        <div class="lbl">Tồn Chết (&ge;12 tháng)</div>
                        <div class="val" style="color: #ea580c;">{{ metrics.inventory.dead_stock_count }}</div>
                    </div>
                </div>
                <!--[if mso]>
                </td><td width="50%" valign="top" style="padding: 8px;">
                <![endif]-->
                <div class="col" style="width: 100%; max-width: 290px; padding: 8px;">
                    <div class="kpi-card failed">
                        <div class="lbl">Sắp Hết Hàng (&le;1 tháng)</div>
                        <div class="val" style="color: #ef4444;">{{ metrics.inventory.near_stockout_count }}</div>
                    </div>
                </div>
                <!--[if mso]>
                </td></tr></table>
                <![endif]-->
            </div>
            {% if metrics.inventory.dead_stock_items %}
            <table class="data-table">
                <thead><tr><th>Mã SKU</th><th>Tên hàng</th><th>Giá trị tồn</th><th>Số tháng bán</th></tr></thead>
                <tbody>
                    {% for item in metrics.inventory.dead_stock_items %}
                    <tr>
                        <td><strong>{{ item.item_code }} ({% if item.channel %}{{ item.channel }}{% else %}—{% endif %})</strong></td>
                        <td>{{ item.item_name }}</td>
                        <td>{{ "{:,.0f}".format(item.closing_value) }} đ</td>
                        <td style="color: #ea580c; font-weight: bold;">{{ item.months_to_sell }} tháng</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}

            {% if chatbot_url %}
            <div style="text-align: center; margin-top: 28px; padding-top: 20px; border-top: 1px solid #e2e8f0;">
                <a href="{{ chatbot_url }}" style="display: inline-block; background-color: #1e3a8a; background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 700; padding: 12px 28px; border-radius: 8px;">
                    💬 Mở Chatbot DNH để hỏi thêm
                </a>
                <p style="margin: 10px 0 0 0; font-size: 12px; color: #94a3b8;">Đăng nhập đúng tài khoản của bạn để xem đúng phạm vi vùng/kênh được phân quyền.</p>
            </div>
            {% endif %}

        </div>
        <div class="footer">
            Báo cáo tự động từ Pipeline ETL &bull; Vui lòng không trả lời trực tiếp email này.
        </div>
    </div>
</body>
</html>
"""

def send_email_via_sendgrid(subject, html_content, recipient_override=None, importance=None):
    """
    Gửi email bằng SendGrid Web API v3 (Không sử dụng SMTP, tránh bị chặn bởi chính sách Office 365)
    recipient_override: nếu truyền vào (list email không rỗng) thì gửi tới danh sách này thay vì
    RECIPIENT_EMAILS/.env hay config.yaml — dùng cho báo cáo đã phân quyền theo audience
    (xem main.py::_send_periodic_email_report).
    importance: "high" -> gắn header Importance/X-Priority để Outlook hiện cờ đỏ "Mức độ quan
    trọng cao" trong hộp thư — dùng cho alert CRITICAL (xem send_alert_to_all_channels).
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL")

    # Đọc cấu hình
    config = load_config()
    sender_name = config['email'].get('sender_name', 'Alerting System (SendGrid)')

    if recipient_override:
        recipient_emails = list(recipient_override)
    else:
        # Đọc danh sách email nhận
        env_recipients = os.getenv("RECIPIENT_EMAILS")
        if env_recipients:
            recipient_emails = [email.strip() for email in env_recipients.split(',') if email.strip()]
        else:
            recipient_emails = config['email'].get('recipient_emails', [])
    recipient_emails = [r for r in recipient_emails if r]
    
    if not sender_email:
        print("[WARNING] SENDER_EMAIL must be set in .env to send via SendGrid.")
        return False
        
    if not recipient_emails:
        print("[WARNING] No recipient emails configured.")
        return False
        
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    personalizations = []
    for email in recipient_emails:
        personalizations.append({
            "to": [{"email": email}]
        })
        
    payload = {
        "personalizations": personalizations,
        "from": {
            "email": sender_email,
            "name": sender_name
        },
        "subject": subject,
        "content": [
            {
                "type": "text/html",
                "value": html_content
            }
        ]
    }
    if importance == "high":
        # Cả 2 header vì client đọc chuẩn khác nhau: Outlook/Office365 (MAPI) đọc "Importance",
        # Outlook cũ/1 số client khác đọc "X-Priority" — gắn cả 2 để chắc chắn cờ đỏ hiện ra.
        payload["headers"] = {"Importance": "high", "X-Priority": "1", "X-MSMail-Priority": "High"}

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            print(f"[SENDGRID] Gui email thanh cong qua SendGrid API toi: {', '.join(recipient_emails)}")
            return True
    except Exception as e:
        print(f"[SENDGRID] Loi gui mail qua SendGrid: {e}")
        if hasattr(e, 'read'):
            try:
                print("Chi tiet loi SendGrid:", e.read().decode('utf-8'))
            except Exception:
                pass
        return False

def send_email(subject, html_content, recipient_override=None, importance=None):
    """
    Gửi email báo cáo: Ưu tiên dùng SendGrid Web API nếu có API Key,
    nếu không có sẽ tự động fallback sang SMTP Outlook truyền thống.
    recipient_override: nếu truyền vào (list email không rỗng) thì gửi tới danh sách này thay vì
    RECIPIENT_EMAILS/.env hay config.yaml — dùng cho báo cáo đã phân quyền theo audience
    (xem main.py::_send_periodic_email_report).
    importance: "high" -> gắn header Importance/X-Priority để Outlook hiện cờ đỏ "Mức độ quan
    trọng cao" trong hộp thư — dùng cho alert CRITICAL (xem send_alert_to_all_channels).
    """
    if os.getenv("SENDGRID_API_KEY"):
        return send_email_via_sendgrid(subject, html_content, recipient_override=recipient_override,
                                        importance=importance)

    config = load_config()

    # Ưu tiên lấy cấu hình SMTP từ file .env cho bảo mật, nếu không có mới lấy từ config.yaml
    smtp_user = os.getenv("SMTP_USER") or config['email'].get('smtp_user')
    smtp_pass = os.getenv("SMTP_PASSWORD") or config['email'].get('smtp_password')
    sender_email = os.getenv("SENDER_EMAIL") or config['email'].get('sender_email') or smtp_user

    if recipient_override:
        recipient_emails = list(recipient_override)
    else:
        # Danh sách email nhận
        env_recipients = os.getenv("RECIPIENT_EMAILS")
        if env_recipients:
            recipient_emails = [email.strip() for email in env_recipients.split(',') if email.strip()]
        else:
            recipient_emails = config['email'].get('recipient_emails', [])

    # Loại bỏ các email trống
    recipient_emails = [r for r in recipient_emails if r]
    
    if not smtp_user or not smtp_pass:
        print(f"[WARNING] SMTP credentials are not set. Cannot send email for subject: {subject}")
        print("Vui long cap nhat SMTP_USER va SMTP_PASSWORD trong file .env")
        return False
        
    if not recipient_emails:
        print(f"[WARNING] No recipient emails configured. Cannot send email.")
        return False
        
    smtp_server = os.getenv("SMTP_SERVER") or config['email'].get('smtp_server', 'smtp.office365.com')
    smtp_port = int(os.getenv("SMTP_PORT") or config['email'].get('smtp_port', 587))
    use_tls = config['email'].get('use_tls', True)
    sender_name = config['email'].get('sender_name', 'Alerting System')
    
    # Thiết lập email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = ", ".join(recipient_emails)
    if importance == "high":
        # Cả 2 header vì Outlook/Office365 (MAPI) đọc "Importance", 1 số client khác đọc
        # "X-Priority"/"X-MSMail-Priority" — gắn cả 3 để chắc chắn cờ đỏ "Mức độ quan trọng cao"
        # hiện ra trong hộp thư thay vì trông giống email thường.
        msg['Importance'] = 'High'
        msg['X-Priority'] = '1'
        msg['X-MSMail-Priority'] = 'High'

    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        # Kết nối đến SMTP Server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        if use_tls:
            server.starttls() # Enable TLS
            server.ehlo()
            
        server.login(smtp_user, smtp_pass)
        server.sendmail(sender_email, recipient_emails, msg.as_string())
        server.quit()
        print(f"[EMAIL] Gui email thanh cong: '{subject}' toi {', '.join(recipient_emails)}")
        return True
    except Exception as e:
        print(f"[ERROR] Gui email that bai: {e}")
        return False

def build_alert_email(alert_name, severity, summary, table_headers, table_rows):
    """
    Tạo nội dung HTML cho email cảnh báo
    """
    template = Template(ALERT_EMAIL_TEMPLATE)
    return template.render(
        alert_name=alert_name,
        severity=severity,
        summary=summary,
        table_headers=table_headers,
        table_rows=table_rows,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def build_svg_clustered_chart(trend_data):
    if not trend_data:
        return ""
    
    # Dimensions
    view_width = 600
    view_height = 220
    margin_left = 65
    margin_right = 20
    margin_top = 30
    margin_bottom = 35
    
    chart_width = view_width - margin_left - margin_right
    chart_height = view_height - margin_top - margin_bottom
    
    # Calculate limits
    max_val = 1.0
    for x in trend_data:
        otc = float(x.get("otc") or 0)
        etc = float(x.get("etc") or 0)
        total = float(x.get("revenue") or (otc + etc))
        max_val = max(max_val, otc, etc, total)
    
    # Round max_val to nice number with headroom
    max_val = max_val * 1.15
    
    # Smart helper for formatting Y-axis labels
    def format_y_label(val):
        if val >= 1_000_000_000:
            return f"{val / 1_000_000_000:.1f} tỷ"
        elif val >= 1_000_000:
            return f"{val / 1_000_000:.0f} tr"
        elif val >= 1_000:
            return f"{val / 1_000:.0f} k"
        return f"{val:.0f}"

    svg = []
    svg.append(f'<svg width="100%" height="{view_height}" viewBox="0 0 {view_width} {view_height}" xmlns="http://www.w3.org/2000/svg" style="background:#ffffff; border: 1px solid #e2e8f0; border-radius:12px; font-family:\'Segoe UI\', Tahoma, Geneva, Verdana, sans-serif;">')
    
    # Define gradients and styles
    svg.append("""
    <defs>
        <linearGradient id="otcGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.85"/>
            <stop offset="100%" stop-color="#2563eb" stop-opacity="0.95"/>
        </linearGradient>
        <linearGradient id="etcGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#10b981" stop-opacity="0.85"/>
            <stop offset="100%" stop-color="#059669" stop-opacity="0.95"/>
        </linearGradient>
    </defs>
    """)

    # Title & Legend
    svg.append(f'<text x="20" y="25" font-size="12" font-weight="700" fill="#1e293b">XU HƯỚNG DOANH THU OTC VS ETC</text>')
    # Legend boxes
    svg.append('<rect x="360" y="15" width="12" height="12" rx="2" fill="url(#otcGrad)"/>')
    svg.append('<text x="377" y="25" font-size="10" font-weight="600" fill="#64748b">OTC</text>')
    svg.append('<rect x="420" y="15" width="12" height="12" rx="2" fill="url(#etcGrad)"/>')
    svg.append('<text x="437" y="25" font-size="10" font-weight="600" fill="#64748b">ETC</text>')
    svg.append('<line x1="480" y1="21" x2="500" y2="21" stroke="#ea580c" stroke-width="2" stroke-dasharray="2"/>')
    svg.append('<text x="507" y="25" font-size="10" font-weight="600" fill="#64748b">Tổng</text>')

    # Draw Y grid lines & labels (4 levels: 0%, 33%, 66%, 100%)
    for i in range(4):
        pct = i / 3.0
        y = margin_top + chart_height - (pct * chart_height)
        val = pct * max_val
        svg.append(f'<line x1="{margin_left}" y1="{y}" x2="{view_width - margin_right}" y2="{y}" stroke="#f1f5f9" stroke-width="1"/>')
        svg.append(f'<text x="{margin_left - 8}" y="{y + 3}" font-size="9" fill="#94a3b8" text-anchor="end">{format_y_label(val)}</text>')

    # Calculate points for line chart (Total) and bars
    n_points = len(trend_data)
    group_width = chart_width / max(n_points, 1)
    
    line_points = []
    
    for i, x in enumerate(trend_data):
        otc_val = float(x.get("otc") or 0)
        etc_val = float(x.get("etc") or 0)
        total_val = float(x.get("revenue") or (otc_val + etc_val))
        label = x.get("label") or ""
        
        group_x = margin_left + i * group_width
        
        # Draw Bars
        # Bar width = 28% of group width each
        bar_w = max(group_width * 0.28, 4)
        gap = max(group_width * 0.04, 1)
        
        otc_h = (otc_val / max_val) * chart_height
        otc_y = margin_top + chart_height - otc_h
        otc_x = group_x + (group_width - 2*bar_w - gap) / 2
        
        etc_h = (etc_val / max_val) * chart_height
        etc_y = margin_top + chart_height - etc_h
        etc_x = otc_x + bar_w + gap
        
        if otc_h > 0:
            svg.append(f'<rect x="{otc_x}" y="{otc_y}" width="{bar_w}" height="{otc_h}" rx="2" fill="url(#otcGrad)"/>')
        if etc_h > 0:
            svg.append(f'<rect x="{etc_x}" y="{etc_y}" width="{bar_w}" height="{etc_h}" rx="2" fill="url(#etcGrad)"/>')
            
        # Line point (Total)
        total_h = (total_val / max_val) * chart_height
        total_y = margin_top + chart_height - total_h
        center_x = group_x + group_width / 2
        line_points.append((center_x, total_y, total_val))
        
        # X-axis label
        svg.append(f'<text x="{center_x}" y="{view_height - 12}" font-size="9" font-weight="600" fill="#64748b" text-anchor="middle">{label}</text>')

    # Draw Total line & circles
    if len(line_points) > 1:
        path_d = []
        for idx, (px, py, _) in enumerate(line_points):
            if idx == 0:
                path_d.append(f"M {px} {py}")
            else:
                path_d.append(f"L {px} {py}")
        svg.append(f'<path d="{" ".join(path_d)}" fill="none" stroke="#ea580c" stroke-width="2" stroke-dasharray="3" stroke-linejoin="round" stroke-linecap="round"/>')
        
    for px, py, pval in line_points:
        svg.append(f'<circle cx="{px}" cy="{py}" r="3" fill="#ea580c"/>')
        if pval > 0:
            svg.append(f'<text x="{px}" y="{py - 6}" font-size="8" font-weight="700" fill="#7c2d12" text-anchor="middle">{format_y_label(pval)}</text>')

    # Draw baseline axis
    svg.append(f'<line x1="{margin_left}" y1="{view_height - margin_bottom}" x2="{view_width - margin_right}" y2="{view_height - margin_bottom}" stroke="#e2e8f0" stroke-width="1.5"/>')
    
    svg.append("</svg>")
    return "\n".join(svg)

def build_digest_email(metrics, period_label="Daily", audience=None, scope_label=None):
    """
    Tạo nội dung HTML cho email báo cáo tổng hợp định kỳ.
    period_label: "Daily" / "Weekly" / "Monthly" (hiển thị trong tiêu đề email).
    audience/scope_label: nhãn "Báo cáo dành cho: ..." — dùng cho báo cáo đã phân quyền theo
    cấp quản lý (xem main.py::send_weekly_report/send_monthly_report). None -> không hiện nhãn
    (giữ nguyên hành vi cũ cho các nơi gọi chưa truyền audience).
    """
    trend_chart_svg = ""
    if metrics.get("trend"):
        trend_chart_svg = build_svg_clustered_chart(metrics["trend"])

    template = Template(DIGEST_EMAIL_TEMPLATE)
    return template.render(
        metrics=metrics,
        period_label=period_label,
        audience=audience,
        scope_label=scope_label,
        chatbot_url=_chatbot_deep_link(),
        trend_chart_svg=trend_chart_svg,
    )

def send_telegram_alert(text):
    """
    Gửi tin nhắn cảnh báo qua Telegram Bot API (sử dụng urllib)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("[WARNING] Telegram credentials are not configured in .env. Skipping Telegram alert.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode('utf-8'))
            if res.get("ok"):
                print("[TELEGRAM] Gui canh bao thanh cong!")
                return True
            else:
                print(f"[TELEGRAM] Loi gui: {res}")
                return False
    except Exception as e:
        print(f"[TELEGRAM] Loi ket noi: {e}")
        return False

def _severity_to_card_style(severity):
    """Map severity -> Adaptive Card Container style (mau sac)."""
    s = (severity or "").upper()
    if s == "CRITICAL":
        return "attention"  # do
    if s == "WARNING":
        return "warning"    # vang
    return "good"           # xanh, dung cho INFO

def _chatbot_deep_link(question=None):
    """
    URL dẫn vào web chatbot — nếu có `question` thì kèm sẵn câu hỏi (?q=...), người bấm vào chỉ
    cần đăng nhập bằng đúng tài khoản của mình, RBAC theo username (DNHChatbot._resolve_user_scope)
    sẽ tự giới hạn đúng phạm vi vùng/kênh họ được xem, không cần nhúng thêm tham số phân quyền vào
    link. `question=None` -> trả về link trần (dùng cho nút "Mở Chatbot" chung trong báo cáo định
    kỳ, vốn không có 1 câu hỏi cụ thể duy nhất để prefill).

    CHATBOT_WEB_URL đọc từ .env, mặc định http://127.0.0.1:8000 (đúng địa chỉ chatbot đang chạy
    hiện tại — backend/main.py chỉ bind 127.0.0.1, chưa có domain public). Link này CHỈ mở được từ
    chính máy đang chạy backend cho tới khi có domain/tunnel public thật — điền CHATBOT_WEB_URL
    trong .env khi đã deploy, không cần sửa code.
    """
    base = os.getenv("CHATBOT_WEB_URL", "http://127.0.0.1:8000").rstrip('/')
    if question:
        return f"{base}/?q={quote(question)}"
    return base


def _build_teams_adaptive_card(title, summary, severity, table_headers=None, table_rows=None,
                                period=None, channel=None, region=None, issue=None):
    """
    Dung Adaptive Card (schema 1.5) thay vi text Markdown tho, de Teams hien thi
    co mau theo severity (do=CRITICAL, vang=WARNING, xanh=INFO).

    period/channel/region/issue la cac truong CO CAU TRUC moi (tuy chon, None thi bo qua) de
    nguoi nhan biet NGAY: canh bao nay cua KY/NGAY nao, KENH OTC/ETC nao, KHU VUC mien nao, va
    VAN DE cu the la gi — thay vi phai doc het doan van `summary` moi suy ra duoc.

    KHÔNG còn vẽ bảng chi tiết (table_headers/table_rows) trong card — bảng dài gây rối mắt, nhất
    là trên Teams mobile. Thay bằng 1 nút "Xem chi tiết trên Chatbot" dẫn tới _chatbot_deep_link()
    kèm sẵn câu hỏi tương ứng (lấy từ issue, dự phòng title). table_headers/table_rows vẫn nhận
    vào hàm — KHÔNG đổi chữ ký để không phải sửa lại toàn bộ các nơi gọi trong src/alerts.py — chỉ
    không dùng để vẽ Table nữa (email vẫn hiển thị bảng bình thường, không đổi).
    """
    body = [
        {
            "type": "Container",
            "style": _severity_to_card_style(severity),
            "bleed": True,
            "items": [
                {"type": "TextBlock", "text": f"🚨 {title}", "weight": "Bolder", "size": "Large", "wrap": True},
                {"type": "TextBlock", "text": f"Mức độ: {severity}", "isSubtle": True, "size": "Small", "wrap": True}
            ]
        }
    ]

    facts = []
    if period:
        facts.append({"title": "📅 Kỳ / Ngày", "value": str(period)})
    if channel:
        facts.append({"title": "🏷️ Kênh", "value": str(channel)})
    if region:
        facts.append({"title": "📍 Khu vực", "value": str(region)})
    if facts:
        body.append({"type": "FactSet", "facts": facts, "spacing": "Medium"})

    if issue:
        body.append({
            "type": "TextBlock",
            "text": f"⚠️ Vấn đề phát hiện: {issue}",
            "weight": "Bolder",
            "wrap": True,
            "color": _severity_to_card_style(severity),
            "spacing": "Medium" if not facts else "Small"
        })

    body.append({"type": "TextBlock", "text": summary, "wrap": True, "spacing": "Small" if issue else "Medium"})

    # Compact Table Container using Action.ToggleVisibility
    has_details = table_headers and table_rows
    if has_details:
        facts_list = []
        code_idx = None
        name_idx = None
        for idx, h in enumerate(table_headers):
            hl = h.lower()
            if ("mã" in hl or "sku" in hl or "code" in hl) and code_idx is None:
                code_idx = idx
            if ("tên" in hl or "name" in hl or "đại lý" in hl or "nhân sự" in hl) and name_idx is None:
                name_idx = idx
        
        # Fallbacks
        if code_idx is None:
            code_idx = 0
        if name_idx is None:
            name_idx = 1 if len(table_headers) > 1 else 0

        for row in table_rows:
            if len(table_headers) == 2:
                key = str(row[0])
                val = str(row[1])
            else:
                key = f"{row[code_idx]} - {row[name_idx]}" if code_idx != name_idx else str(row[code_idx])
                other_vals = [str(row[i]) for i in range(len(row)) if i not in (code_idx, name_idx)]
                val = " | ".join(other_vals)
            facts_list.append({"title": key, "value": val})

        body.append({
            "type": "Container",
            "id": "compactTableDetails",
            "isVisible": True,
            "spacing": "Medium",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "📋 Chi tiết danh sách:",
                    "weight": "Bolder",
                    "size": "Small"
                },
                {
                    "type": "FactSet",
                    "facts": facts_list,
                    "spacing": "Small"
                }
            ]
        })

    body.append({
        "type": "TextBlock",
        "text": f"Hệ thống Giám sát DWH Dược Nam Hà (DNH) • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "isSubtle": True,
        "size": "Small",
        "spacing": "Medium",
        "wrap": True
    })

    adaptive_card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body
    }

    # Actions list
    actions = []
    if has_details:
        actions.append({
            "type": "Action.ToggleVisibility",
            "title": "👁️ Thu gọn / Hiện chi tiết",
            "targetElements": ["compactTableDetails"]
        })

    # Hotline Call Button for debt-related issues
    is_debt = any(w in title.lower() or w in str(issue or "").lower() for w in ("nợ", "overdue", "credit", "limit", "hạn mức"))
    if is_debt:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "📞 Gọi Hotline DNH (1900 636433)",
            "url": "tel:1900636433"
        })

    chat_question = issue or title
    if chat_question:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "💬 Hỏi Chatbot DNH",
            "url": _chatbot_deep_link(f"Cho tôi xem chi tiết: {chat_question}")
        })

    if actions:
        adaptive_card["actions"] = actions

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": adaptive_card
            }
        ]
    }

def send_teams_alert(title, summary, table_headers=None, table_rows=None, severity="INFO",
                      period=None, channel=None, region=None, issue=None, webhook_url_override=None):
    """
    Gửi tin nhắn cảnh báo qua Microsoft Teams Incoming Webhook dưới dạng Adaptive Card
    (phân màu theo severity thay vì text Markdown thô).
    webhook_url_override: nếu truyền vào (không rỗng) thì gửi tới URL này thay vì
    TEAMS_WEBHOOK_URL mặc định — dùng khi định tuyến theo audience (xem _resolve_teams_webhooks).
    """
    webhook_url = webhook_url_override or os.getenv("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        print("[WARNING] TEAMS_WEBHOOK_URL is not configured in .env. Skipping Teams alert.")
        return False

    payload = _build_teams_adaptive_card(title, summary, severity, table_headers, table_rows,
                                          period=period, channel=channel, region=region, issue=issue)

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url.strip(),
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print("[TEAMS] Gui canh bao Teams (Adaptive Card) thanh cong!")
            return True
    except Exception as e:
        print(f"[TEAMS] Loi gui Teams: {e}")
        return False


def _resolve_teams_webhooks(region_label, channel_label):
    """
    Suy ra danh sách webhook Teams (URL, tên audience) cần gửi cho 1 alert có region_label/
    channel_label (nhãn hiển thị, vd "Miền Bắc"/"OTC" — xem src/alerts.py::normalize_region_label/
    normalize_channel_label), dựa trên config['report_recipients'] (Phần 3 — phân quyền theo cấp
    quản lý, nguồn DUY NHẤT dùng chung cho email/Teams/chatbot).

    Quy tắc khớp: 1 audience khớp alert nếu (audience.region rỗng HOẶC == vùng của alert) VÀ
    (audience.channel rỗng HOẶC == kênh của alert). Audience region/channel đều rỗng (C-Level)
    luôn khớp mọi alert. Alert có vùng/kênh KHÔNG xác định cụ thể (vd "Toàn quốc"/"Nhiều miền"/
    "OTC + ETC") chỉ khớp các audience không giới hạn tương ứng — tránh gửi nhầm alert đa vùng/đa
    kênh vào 1 webhook vùng/kênh cụ thể.

    Mỗi audience khớp có teams_webhook riêng (đã điền) hoặc rỗng (CHƯA có Flow riêng -> dùng
    chung TEAMS_WEBHOOK_URL mặc định). Trả về danh sách ĐÃ KHỬ TRÙNG theo URL, để không gửi lặp
    khi nhiều audience còn trỏ chung 1 webhook (vd lúc chưa điền webhook riêng, tất cả audience
    khớp cùng rơi về đúng 1 URL mặc định -> chỉ gửi 1 lần, y hệt hành vi cũ trước khi có Phần 3).
    Nếu config chưa có report_recipients (môi trường cũ) -> trả về đúng 1 webhook mặc định.
    """
    default_webhook = os.getenv("TEAMS_WEBHOOK_URL")
    try:
        config = load_config()
    except Exception:
        config = {}
    recipients = config.get('report_recipients') or []
    if not recipients:
        return [(default_webhook, None)] if default_webhook else []

    from ai_agent.chatbot import DNHChatbot
    region_key_by_label = {v: k for k, v in DNHChatbot._REGION_NAMES_VI.items()}
    alert_region_key = region_key_by_label.get(region_label)
    alert_channel_key = channel_label if channel_label in ("OTC", "ETC") else None

    matched = []
    seen_urls = set()
    for r in recipients:
        aud_region = r.get('region')
        aud_channel = r.get('channel')
        region_ok = (not aud_region) or (aud_region == alert_region_key)
        channel_ok = (not aud_channel) or (aud_channel == alert_channel_key)
        if not (region_ok and channel_ok):
            continue
        url = (r.get('teams_webhook') or '').strip() or default_webhook
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        matched.append((url, r.get('audience')))

    return matched

def _send_with_retry(fn, *args, max_retries=2, delays=(3, 6), **kwargs):
    """
    Goi fn(*args, **kwargs), retry khi co exception (loi mang/timeout).
    KHONG retry khi fn tra ve False do thieu cau hinh (SMTP/webhook rong) —
    retry khong giai quyet duoc loi cau hinh, chi lam cham vo ich.
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = delays[min(attempt, len(delays) - 1)]
                print(f"[RETRY] {fn.__name__} loi ({e}), thu lai sau {delay}s (lan {attempt + 1}/{max_retries})...")
                time.sleep(delay)
    print(f"[RETRY] {fn.__name__} that bai sau {max_retries} lan thu lai: {last_exception}")
    return False

# Hàng đợi gộp card CRITICAL — thêm 10/07/2026 theo yêu cầu tiếp theo sau bộ lọc CRITICAL-only:
# thay vì mỗi alert CRITICAL bắn 1 card Teams riêng (vẫn có thể dồn 3-5 card cùng lúc nếu 1 chu kỳ
# quét phát hiện nhiều vấn đề nghiêm trọng cùng lúc), GOM lại và gửi 1 card DUY NHẤT liệt kê tất cả
# vào cuối chu kỳ quét (xem flush_critical_teams_queue(), gọi từ main.py::run_all_alert_checks
# sau khi mọi check_*_alert() đã chạy xong). Gom theo TỪNG webhook riêng (không phải gộp mù 1 card
# chung cho tất cả) — nếu sau này report_recipients có Flow Teams riêng theo vùng/kênh, mỗi audience
# vẫn chỉ nhận đúng phần alert liên quan tới mình, không lẫn card của audience khác.
_pending_critical_teams_alerts = []

def flush_critical_teams_queue():
    """Gửi TẤT CẢ alert CRITICAL đang chờ trong hàng đợi (xem _pending_critical_teams_alerts) —
    gộp thành 1 card duy nhất CHO MỖI webhook đích, rồi xoá sạch hàng đợi. Gọi 1 LẦN ở CUỐI mỗi chu
    kỳ quét (main.py::run_all_alert_checks), KHÔNG gọi giữa chừng — gọi sớm sẽ gộp thiếu."""
    global _pending_critical_teams_alerts
    if not _pending_critical_teams_alerts:
        return
    by_webhook = {}
    for item in _pending_critical_teams_alerts:
        for webhook_url, audience in item["webhooks"]:
            group = by_webhook.setdefault(webhook_url, {"audience": audience, "alerts": []})
            group["alerts"].append(item)
    for webhook_url, group in by_webhook.items():
        payload = _build_teams_consolidated_card(group["alerts"])
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(webhook_url.strip(), data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                print(f"[TEAMS] Da gui card gop ({len(group['alerts'])} canh bao) toi audience '{group['audience'] or 'mac dinh'}'.")
        except Exception as e:
            print(f"[TEAMS] Loi gui card gop toi audience '{group['audience'] or 'mac dinh'}': {e}")
    _pending_critical_teams_alerts = []

def _build_teams_consolidated_card(alerts):
    """1 Adaptive Card liệt kê NHIỀU alert CRITICAL cùng lúc (xem flush_critical_teams_queue) —
    mỗi alert 1 mục riêng (tên + facts ngày/kênh/vùng + vấn đề), thay vì mỗi alert 1 card riêng."""
    body = [
        {
            "type": "Container",
            "style": "attention",
            "bleed": True,
            "items": [
                {"type": "TextBlock", "text": f"🚨 {len(alerts)} cảnh báo nghiêm trọng", "weight": "Bolder", "size": "Large", "wrap": True},
                {"type": "TextBlock", "text": f"Phát hiện lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "isSubtle": True, "size": "Small", "wrap": True}
            ]
        }
    ]
    for i, a in enumerate(alerts, 1):
        facts = []
        if a.get("period"):
            facts.append({"title": "📅 Kỳ / Ngày", "value": str(a["period"])})
        if a.get("channel"):
            facts.append({"title": "🏷️ Kênh", "value": str(a["channel"])})
        if a.get("region"):
            facts.append({"title": "📍 Khu vực", "value": str(a["region"])})
        item_items = [{"type": "TextBlock", "text": f"{i}. {a['alert_name']}", "weight": "Bolder", "wrap": True}]
        if facts:
            item_items.append({"type": "FactSet", "facts": facts, "spacing": "Small"})
        
        main_summary = a.get("summary") or ""
        item_items.append({"type": "TextBlock", "text": a.get("issue") or main_summary, "wrap": True, "spacing": "Small"})

        # Compact Table Toggle inside list if headers & rows present
        table_headers = a.get("table_headers")
        table_rows = a.get("table_rows")
        item_actions = []

        if table_headers and table_rows:
            facts_list = []
            code_idx = None
            name_idx = None
            for idx, h in enumerate(table_headers):
                hl = h.lower()
                if ("mã" in hl or "sku" in hl or "code" in hl) and code_idx is None:
                    code_idx = idx
                if ("tên" in hl or "name" in hl or "đại lý" in hl or "nhân sự" in hl) and name_idx is None:
                    name_idx = idx
            
            # Fallbacks
            if code_idx is None:
                code_idx = 0
            if name_idx is None:
                name_idx = 1 if len(table_headers) > 1 else 0

            for row in table_rows[:5]:
                if len(table_headers) == 2:
                    key = str(row[0])
                    val = str(row[1])
                else:
                    key = f"{row[code_idx]} - {row[name_idx]}" if code_idx != name_idx else str(row[code_idx])
                    other_vals = [str(row[i]) for i in range(len(row)) if i not in (code_idx, name_idx)]
                    val = " | ".join(other_vals)
                facts_list.append({"title": key, "value": val})

            toggle_id = f"compactTable_{i}"
            item_items.append({
                "type": "Container",
                "id": toggle_id,
                "isVisible": False,
                "spacing": "Small",
                "items": [
                    {"type": "TextBlock", "text": "📋 Chi tiết danh sách (tối đa 5 dòng):", "weight": "Bolder", "size": "Small"},
                    {"type": "FactSet", "facts": facts_list, "spacing": "Small"}
                ]
            })
            item_actions.append({
                "type": "Action.ToggleVisibility",
                "title": "👁️ Xem nhanh danh sách",
                "targetElements": [toggle_id]
            })

        # Phone action if related to debt
        is_debt = any(w in a["alert_name"].lower() or w in str(a.get("issue") or "").lower() for w in ("nợ", "overdue", "credit", "limit", "hạn mức"))
        if is_debt:
            item_actions.append({
                "type": "Action.OpenUrl",
                "title": "📞 Gọi Hotline DNH",
                "url": "tel:1900636433"
            })



        if item_actions:
            item_items.append({
                "type": "ActionSet",
                "actions": item_actions,
                "spacing": "Small"
            })

        body.append({"type": "Container", "items": item_items, "spacing": "Medium", "separator": True})

    body.append({
        "type": "TextBlock",
        "text": f"Hệ thống Giám sát DWH Dược Nam Hà (DNH) • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "isSubtle": True,
        "size": "Small",
        "spacing": "Medium",
        "wrap": True
    })

    adaptive_card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
        "actions": [{
            "type": "Action.OpenUrl",
            "title": "💬 Mở Chatbot DNH",
            "url": _chatbot_deep_link()
        }]
    }
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": adaptive_card
            }
        ]
    }

def send_alert_to_all_channels(alert_name, severity, summary, table_headers=None, table_rows=None,
                                channels=("email", "teams"), period=None, channel=None, region=None,
                                issue=None, require_critical_for_teams=True):
    """
    Gửi cảnh báo qua các kênh được chỉ định trong `channels` (mặc định: Email, Teams).
    Dùng `channels` để định tuyến theo loại nội dung — vd. alert tức thời/daily digest chỉ đi
    Teams, báo cáo tuần/tháng chỉ đi Email (xem main.py/src/alerts.py). Kênh Telegram đã ngừng
    dùng (chuyển hẳn qua web) — code gửi Telegram vẫn còn bên dưới nhưng không còn được gọi tới
    vì không nơi nào truyền "telegram" vào `channels` nữa.

    period/channel/region/issue: các trường có cấu trúc (tùy chọn) chỉ áp dụng cho card Teams —
    xem _build_teams_adaptive_card. Không đổi định dạng Email/Telegram hiện có.

    require_critical_for_teams (mặc định True, thêm 10/07/2026): chống nhiễu — CHỈ severity
    CRITICAL mới thực sự bắn Teams, WARNING/INFO vẫn được LOG (_log_alert_severity, không đổi)
    nhưng không chủ động đẩy thông báo. Áp dụng cho alert nghiệp vụ THỜI GIAN THỰC (src/alerts.py)
    — nơi nhiều loại cảnh báo có thể cùng trigger 1 lúc sau 1 chu kỳ quét, từng gây dồn 5-6 card
    cùng lúc. Daily Digest (main.py) KHÔNG bị ảnh hưởng — gửi 1 lần/ngày theo lịch cố định, không
    có hiện tượng dồn dập nên chủ động truyền require_critical_for_teams=False để bỏ qua bộ lọc.
    """
    print(f"\n--- BAT DAU GUI CANH BAO: {alert_name} [{severity}] (kenh: {', '.join(channels)}) ---")
    _log_alert_severity(alert_name, severity)
    any_sent = False

    # 1. Gui qua Email
    if "email" in channels:
        try:
            subject = f"[{severity}] {alert_name}"
            html_content = build_alert_email(alert_name, severity, summary, table_headers, table_rows)

            email_sent = _send_with_retry(
                send_email, subject, html_content,
                importance="high" if severity == "CRITICAL" else None)
            if email_sent:
                any_sent = True
        except Exception as e:
            print(f"[ERROR] Loi gui Email: {e}")

    # 2. Gui qua Telegram
    if "telegram" in channels:
        try:
            def escape_html(text):
                if not isinstance(text, str):
                    text = str(text)
                return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # Format text cho Telegram cực đẹp mắt và chuyên nghiệp (Sử dụng tiếng Việt có dấu)
            emoji = "🔴" if severity == "CRITICAL" else "🟡" if severity == "WARNING" else "ℹ️"

            telegram_text = f"{emoji} <b>{escape_html(alert_name)}</b>\n"
            telegram_text += f"━━━━━━━━━━━━━━━━━━━━━\n"
            telegram_text += f"📝 <b>Mô tả:</b> {escape_html(summary)}\n"
            telegram_text += f"⚠️ <b>Độ nghiêm trọng:</b> <code>{escape_html(severity)}</code>\n"
            telegram_text += f"📅 <b>Thời gian:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            telegram_text += f"━━━━━━━━━━━━━━━━━━━━━\n\n"

            if table_headers and table_rows:
                telegram_text += "📊 <b>CHI TIẾT DỮ LIỆU CẢNH BÁO:</b>\n"
                for idx, row in enumerate(table_rows):
                    telegram_text += f"\n<b>Hồ sơ #{idx+1}:</b>\n"
                    for col_idx, header in enumerate(table_headers):
                        telegram_text += f"   • {escape_html(header)}: <b>{escape_html(row[col_idx])}</b>\n"
                telegram_text += "\n━━━━━━━━━━━━━━━━━━━━━\n\n"

            telegram_text += "🤖 <i>Hệ thống Giám sát DWH Dược Nam Hà (DNH)</i>"

            telegram_sent = _send_with_retry(send_telegram_alert, telegram_text)
            if telegram_sent:
                any_sent = True
        except Exception as e:
            print(f"[ERROR] Loi gui Telegram: {e}")

    # 3. Gui qua Teams — định tuyến theo audience khớp region/channel của alert (Phần 3 phân
    #    quyền). Khi các audience còn trỏ chung 1 webhook mặc định (chưa điền Flow riêng),
    #    _resolve_teams_webhooks tự khử trùng nên hành vi giống hệt "1 webhook chung" trước đây.
    if "teams" in channels and require_critical_for_teams and severity != "CRITICAL":
        print(f"[TEAMS] Bỏ qua gửi Teams cho '{alert_name}' (severity={severity}, chỉ CRITICAL mới gửi Teams).")
    elif "teams" in channels and require_critical_for_teams:
        # CRITICAL + đang ở chế độ lọc alert nghiệp vụ mặc định -> ĐƯA VÀO HÀNG ĐỢI thay vì gửi
        # ngay (xem flush_critical_teams_queue() — gộp nhiều alert CRITICAL cùng chu kỳ quét
        # thành 1 card, thêm 10/07/2026 theo yêu cầu tiếp theo sau bộ lọc CRITICAL-only).
        try:
            webhooks = _resolve_teams_webhooks(region, channel)
            if not webhooks:
                print("[WARNING] Không có webhook Teams nào khớp (kiểm tra TEAMS_WEBHOOK_URL/.env hoặc report_recipients).")
            else:
                _pending_critical_teams_alerts.append({
                    "alert_name": alert_name, "summary": summary,
                    "period": period, "channel": channel, "region": region, "issue": issue,
                    "webhooks": webhooks,
                    "table_headers": table_headers, "table_rows": table_rows
                })
                any_sent = True
                print(f"[TEAMS] Đã đưa '{alert_name}' vào hàng đợi gộp card (gửi cuối chu kỳ quét).")
        except Exception as e:
            print(f"[ERROR] Loi dua vao hang doi Teams: {e}")
    elif "teams" in channels:
        # require_critical_for_teams=False (vd Daily Digest) -> gửi NGAY như cũ, không qua hàng
        # đợi (không có nguy cơ dồn card vì đây là các lần gửi đơn lẻ, không nằm trong 1 chu kỳ quét).
        try:
            webhooks = _resolve_teams_webhooks(region, channel)
            if not webhooks:
                print("[WARNING] Không có webhook Teams nào khớp (kiểm tra TEAMS_WEBHOOK_URL/.env hoặc report_recipients).")
            for webhook_url, audience in webhooks:
                teams_sent = _send_with_retry(send_teams_alert, alert_name, summary, table_headers, table_rows,
                                               severity=severity, period=period, channel=channel, region=region,
                                               issue=issue, webhook_url_override=webhook_url)
                if teams_sent:
                    any_sent = True
                    if audience:
                        print(f"[TEAMS] Đã gửi tới audience '{audience}'.")
        except Exception as e:
            print(f"[ERROR] Loi gui Teams: {e}")

    return any_sent

if __name__ == '__main__':
    # Kiểm duyệt render template cục bộ
    mock_metrics = {
        "date": "01/07/2026",
        "period_range": "Tuần 25/06/2026 - 01/07/2026",
        "erp": {
            "total_orders": 120,
            "completed_orders": 115,
            "failed_orders": 5,
            "total_revenue": 12500.50,
            "low_inventory_count": 1,
            "low_inventory_items": [
                {"sku": "LAP-DELL-XPS", "item_name": "Laptop Dell XPS", "quantity": 12}
            ]
        },
        "crm": {
            "total_tickets": 25,
            "resolved_tickets": 21,
            "open_tickets": 4,
            "urgent_open": 2,
            "high_open": 2
        }
    }

    html = build_digest_email(mock_metrics, period_label="Weekly")
    print("Digest email rendered length:", len(html))

    alert_html = build_alert_email(
        alert_name="CẢNH BÁO TỒN KHO THẤP",
        severity="WARNING",
        summary="Phát hiện sản phẩm Laptop Dell XPS dưới ngưỡng tồn tối thiểu",
        table_headers=["Mã SKU", "Tên sản phẩm", "Tồn kho thực tế"],
        table_rows=[["LAP-DELL-XPS", "Laptop Dell XPS", "12"]]
    )
    print("Alert rendered length:", len(alert_html))

    # Kiểm tra Adaptive Card sinh ra là JSON hợp lệ (không gửi thật vì chưa có webhook)
    adaptive_card_payload = _build_teams_adaptive_card(
        title="CẢNH BÁO TỒN KHO THẤP",
        summary="Phát hiện sản phẩm Laptop Dell XPS dưới ngưỡng tồn tối thiểu",
        severity="WARNING",
        table_headers=["Mã SKU", "Tên sản phẩm", "Tồn kho thực tế"],
        table_rows=[["LAP-DELL-XPS", "Laptop Dell XPS", "12"]]
    )
    adaptive_card_json = json.dumps(adaptive_card_payload, ensure_ascii=False, indent=2)
    print("Adaptive Card JSON hop le, do dai:", len(adaptive_card_json))

    # Save a copy to examine design locally
    os.makedirs(os.path.join(PROJECT_ROOT, 'scratch'), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, 'scratch', 'test_alert.html'), 'w', encoding='utf-8') as f:
        f.write(alert_html)
    with open(os.path.join(PROJECT_ROOT, 'scratch', 'test_digest.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    with open(os.path.join(PROJECT_ROOT, 'scratch', 'test_teams_adaptive_card.json'), 'w', encoding='utf-8') as f:
        f.write(adaptive_card_json)
    print("Rendered HTML/JSON saved for verification in scratch/ directory.")
