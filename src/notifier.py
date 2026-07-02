import os
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from dotenv import load_dotenv
from src.database import load_config
import json
import urllib.request

# Đảm bảo terminal/log ghi nhận được tiếng Việt có dấu
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
        .header.critical { background: linear-gradient(135deg, #e53e3e 0%, #b7791f 100%); }
        .header.warning { background: linear-gradient(135deg, #dd6b20 0%, #d69e2e 100%); }
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

# HTML template for Daily Digest
DAILY_DIGEST_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333333; margin: 0; padding: 20px; background-color: #f4f5f8; }
        .container { max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); overflow: hidden; border: 1px solid #e2e8f0; }
        .header { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px 24px; color: #ffffff; }
        .header h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }
        .header p { margin: 5px 0 0 0; font-size: 14px; opacity: 0.9; }
        .content { padding: 24px; }
        .section-title { font-size: 16px; font-weight: 700; color: #1e3a8a; margin-top: 24px; margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .grid { display: flex; flex-wrap: wrap; margin: -8px; }
        .col { flex: 1; min-width: 130px; padding: 8px; }
        .kpi-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center; }
        .kpi-card .val { font-size: 22px; font-weight: 700; color: #1e293b; margin: 5px 0; }
        .kpi-card .lbl { font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .kpi-card.failed { border-left: 4px solid #ef4444; }
        .kpi-card.success { border-left: 4px solid #10b981; }
        .data-table { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 20px; }
        .data-table th { text-align: left; padding: 10px; background-color: #f1f5f9; border-bottom: 2px solid #e2e8f0; font-size: 12px; color: #475569; text-transform: uppercase; }
        .data-table td { padding: 12px 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px; color: #334155; }
        .no-data { font-size: 13px; color: #64748b; font-style: italic; padding: 10px 0; }
        .footer { background: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>BÁO CÁO TỔNG HỢP HOẠT ĐỘNG DAILY</h1>
            <p>Ngày ghi nhận: {{ metrics.date }}</p>
        </div>
        
        <div class="content">
            <!-- ERP KPI Section -->
            <div class="section-title">Tổng Hợp Giao Dịch ERP</div>
            <div class="grid">
                <div class="col">
                    <div class="kpi-card">
                        <div class="lbl">Tổng Đơn Hàng</div>
                        <div class="val">{{ metrics.erp.total_orders }}</div>
                    </div>
                </div>
                <div class="col">
                    <div class="kpi-card success">
                        <div class="lbl">Đơn Hoàn Thành</div>
                        <div class="val">{{ metrics.erp.completed_orders }}</div>
                    </div>
                </div>
                <div class="col">
                    <div class="kpi-card failed">
                        <div class="lbl">Đơn Bị Lỗi</div>
                        <div class="val" style="color: #ef4444;">{{ metrics.erp.failed_orders }}</div>
                    </div>
                </div>
                <div class="col">
                    <div class="kpi-card">
                        <div class="lbl">Doanh Thu</div>
                        <div class="val" style="color: #10b981;">${{ "{:,.2f}".format(metrics.erp.total_revenue) }}</div>
                    </div>
                </div>
            </div>
            
            <!-- CRM KPI Section -->
            <div class="section-title">Tổng Hợp Support CRM</div>
            <div class="grid">
                <div class="col">
                    <div class="kpi-card">
                        <div class="lbl">Tổng số ca</div>
                        <div class="val">{{ metrics.crm.total_tickets }}</div>
                    </div>
                </div>
                <div class="col">
                    <div class="kpi-card success">
                        <div class="lbl">Đã Giải Quyết</div>
                        <div class="val">{{ metrics.crm.resolved_tickets }}</div>
                    </div>
                </div>
                <div class="col">
                    <div class="kpi-card failed">
                        <div class="lbl">Chưa Xử Lý (Open)</div>
                        <div class="val" style="color: #ea580c;">{{ metrics.crm.open_tickets }}</div>
                    </div>
                </div>
                <div class="col">
                    <div class="kpi-card">
                        <div class="lbl">Số ca Khẩn Cấp</div>
                        <div class="val" style="color: #ef4444;">{{ metrics.crm.urgent_open }}</div>
                    </div>
                </div>
            </div>
            
            <!-- Low Inventory List Section -->
            <div class="section-title">Sản Phẩm Cần Nhập Hàng (Tồn < {{ low_limit }})</div>
            {% if metrics.erp.low_inventory_count > 0 %}
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Mã SKU</th>
                        <th>Tên sản phẩm</th>
                        <th>Số lượng còn</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in metrics.erp.low_inventory_items %}
                    <tr>
                        <td><strong>{{ item.sku }}</strong></td>
                        <td>{{ item.item_name }}</td>
                        <td style="color: #ef4444; font-weight: bold;">{{ item.quantity }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else: %}
            <p class="no-data">Không có sản phẩm nào dưới ngưỡng tồn kho tối thiểu. Rất tốt!</p>
            {% endif %}
            
        </div>
        <div class="footer">
            Báo cáo tự động từ Pipeline ETL &bull; Vui lòng không trả lời trực tiếp email này.
        </div>
    </div>
</body>
</html>
"""

def send_email(subject, html_content):
    """
    Gửi email bằng SMTP Outlook
    """
    config = load_config()
    
    # Ưu tiên lấy cấu hình SMTP từ file .env cho bảo mật, nếu không có mới lấy từ config.yaml
    smtp_user = os.getenv("SMTP_USER") or config['email'].get('smtp_user')
    smtp_pass = os.getenv("SMTP_PASSWORD") or config['email'].get('smtp_password')
    sender_email = os.getenv("SENDER_EMAIL") or config['email'].get('sender_email') or smtp_user
    
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
        
    smtp_server = config['email'].get('smtp_server', 'smtp.office365.com')
    smtp_port = int(config['email'].get('smtp_port', 587))
    use_tls = config['email'].get('use_tls', True)
    sender_name = config['email'].get('sender_name', 'Alerting System')
    
    # Thiết lập email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = ", ".join(recipient_emails)
    
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

def build_daily_digest_email(metrics):
    """
    Tạo nội dung HTML cho email báo cáo tổng hợp daily
    """
    config = load_config()
    low_limit = config['thresholds']['erp']['low_inventory_limit']
    
    template = Template(DAILY_DIGEST_TEMPLATE)
    return template.render(
        metrics=metrics,
        low_limit=low_limit
    )

def analyze_alert_with_gemini(alert_name, summary, table_headers, table_rows):
    """
    Sử dụng Gemini API để phân tích dữ liệu cảnh báo và đưa ra nhận xét, đề xuất kinh doanh bằng tiếng Việt.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[WARNING] GEMINI_API_KEY is not configured in .env. Skipping Gemini analysis.")
        return ""
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    # Chuẩn bị dữ liệu bảng dưới dạng văn bản Markdown
    table_text = ""
    if table_headers and table_rows:
        table_text = " | ".join(table_headers) + "\n"
        table_text += " | ".join(["---"] * len(table_headers)) + "\n"
        for row in table_rows:
            table_text += " | ".join([str(cell) for cell in row]) + "\n"
        
    prompt = f"""
Bạn là một chuyên gia phân tích dữ liệu kinh doanh và công nợ tài chính cao cấp tại công ty Dược phẩm Nam Hà (DNH).
Hãy phân tích dữ liệu cảnh báo sau và viết một đoạn nhận xét ngắn gọn, sắc bén (khoảng 3-4 câu) bằng tiếng Việt có dấu.
Đoạn phân tích cần:
1. Nêu bật vấn đề nghiêm trọng nhất hoặc các mã khách hàng/mã hàng đáng lo ngại từ dữ liệu.
2. Đưa ra 1 khuyến nghị hành động cụ thể cho bộ phận kinh doanh hoặc kế toán (ví dụ: siết nợ, nhập thêm nguyên liệu, thúc đẩy TDV...).
3. Giọng điệu chuyên nghiệp, ngắn gọn, phù hợp để gửi tin nhắn thông báo nhanh.

Thông tin cảnh báo:
- Tên cảnh báo: {alert_name}
- Mô tả: {summary}

Dữ liệu chi tiết:
{table_text}
"""
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode('utf-8'))
            text = res['candidates'][0]['content']['parts'][0]['text']
            return text.strip()
    except Exception as e:
        print(f"[GEMINI] Loi phan tich Gemini: {e}")
        return ""

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

def send_teams_alert(title, summary, table_headers=None, table_rows=None):
    """
    Gửi tin nhắn cảnh báo qua Microsoft Teams Incoming Webhook
    """
    webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        print("[WARNING] TEAMS_WEBHOOK_URL is not configured in .env. Skipping Teams alert.")
        return False
        
    # Tạo nội dung dạng văn bản Markdown
    text_content = f"### 🚨 {title}\n\n**{summary}**\n\n"
    if table_headers and table_rows:
        header_line = " | ".join(table_headers)
        separator_line = " | ".join(["---"] * len(table_headers))
        text_content += f"| {header_line} |\n| {separator_line} |\n"
        for row in table_rows:
            row_line = " | ".join([str(cell) for cell in row])
            text_content += f"| {row_line} |\n"
            
    payload = {
        "text": text_content
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url.strip(), 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print("[TEAMS] Gui canh bao Teams thanh cong!")
            return True
    except Exception as e:
        print(f"[TEAMS] Loi gui Teams: {e}")
        return False

def send_alert_to_all_channels(alert_name, severity, summary, table_headers=None, table_rows=None):
    """
    Gửi cảnh báo đồng thời qua các kênh cấu hình: Email, Telegram, Teams.
    """
    print(f"\n--- BAT DAU GUI CANH BAO: {alert_name} [{severity}] ---")
    any_sent = False
    
    # Gọi Gemini AI phân tích dữ liệu cảnh báo nếu có API Key
    gemini_analysis = ""
    if os.getenv("GEMINI_API_KEY"):
        print("[GEMINI] Dang phan tich du lieu bang AI...")
        gemini_analysis = analyze_alert_with_gemini(alert_name, summary, table_headers, table_rows)
    
    # 1. Gui qua Email
    try:
        subject = f"[{severity}] {alert_name}"
        html_content = build_alert_email(alert_name, severity, summary, table_headers, table_rows)
        # Thêm phân tích Gemini vào email nếu có
        if gemini_analysis:
            # Chèn phân tích vào trước thẻ kết thúc của class content
            insert_idx = html_content.find("</div>\n        <div class=\"footer\">")
            if insert_idx != -1:
                ai_html = f"""
                <div style="margin-top: 20px; padding: 15px; background: #f0f7ff; border-left: 4px solid #3b82f6; border-radius: 6px;">
                    <strong style="color: #1e3a8a; font-size: 14px;">💡 PHÂN TÍCH THÔNG MINH (AI GEMINI):</strong>
                    <p style="margin: 5px 0 0 0; font-size: 13px; color: #2d3748; line-height: 1.5; font-style: italic;">{gemini_analysis}</p>
                </div>
                """
                html_content = html_content[:insert_idx] + ai_html + html_content[insert_idx:]
                
        email_sent = send_email(subject, html_content)
        if email_sent:
            any_sent = True
    except Exception as e:
        print(f"[ERROR] Loi gui Email: {e}")
        
    # 2. Gui qua Telegram
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
            
        if gemini_analysis:
            telegram_text += f"💡 <b>PHÂN TÍCH THÔNG MINH (AI GEMINI):</b>\n"
            telegram_text += f"<i>{escape_html(gemini_analysis)}</i>\n\n"
            telegram_text += f"━━━━━━━━━━━━━━━━━━━━━\n"
            
        telegram_text += "🤖 <i>Hệ thống Giám sát DWH Dược Nam Hà (DNH)</i>"
        
        telegram_sent = send_telegram_alert(telegram_text)
        if telegram_sent:
            any_sent = True
    except Exception as e:
        print(f"[ERROR] Loi gui Telegram: {e}")
        
    # 3. Gui qua Teams
    try:
        # Nếu có phân tích AI, đính kèm vào nội dung Teams
        teams_summary = summary
        if gemini_analysis:
            teams_summary = f"{summary}\n\n**💡 Phân tích AI:** *{gemini_analysis}*"
        teams_sent = send_teams_alert(alert_name, teams_summary, table_headers, table_rows)
        if teams_sent:
            any_sent = True
    except Exception as e:
        print(f"[ERROR] Loi gui Teams: {e}")
        
    return any_sent

if __name__ == '__main__':
    # Kiểm duyệt render template cục bộ
    mock_metrics = {
        "date": "01/07/2026",
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
    
    html = build_daily_digest_email(mock_metrics)
    print("Daily digest rendered length:", len(html))
    
    alert_html = build_alert_email(
        alert_name="CẢNH BÁO TỒN KHO THẤP",
        severity="WARNING",
        summary="Phát hiện sản phẩm Laptop Dell XPS dưới ngưỡng tồn tối thiểu",
        table_headers=["Mã SKU", "Tên sản phẩm", "Tồn kho thực tế"],
        table_rows=[["LAP-DELL-XPS", "Laptop Dell XPS", "12"]]
    )
    print("Alert rendered length:", len(alert_html))
    
    # Save a copy to examine design locally
    os.makedirs(os.path.join(PROJECT_ROOT, 'scratch'), exist_ok=True)
    with open(os.path.join(PROJECT_ROOT, 'scratch', 'test_alert.html'), 'w', encoding='utf-8') as f:
        f.write(alert_html)
    with open(os.path.join(PROJECT_ROOT, 'scratch', 'test_daily.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print("Rendered HTML saved for verification in scratch/ directory.")
