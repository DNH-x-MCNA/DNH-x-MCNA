import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "dnh_intermediate.db")
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "email_log.txt")

# Configuration placeholders for DNH
SMTP_CONFIG = {
    "server": "smtp.office365.com",
    "port": 587,
    "username": "service-account@namhapharma.com",
    "password": "YOUR_SECRET_PASSWORD"
}

RECIPIENTS = [
    "ceo@namhapharma.com",
    "cfo@namhapharma.com",
    "sales-manager@namhapharma.com"
]

def strip_accents(s):
    m = {
        'a': 'áàảãạăắằẳẵặâấầẩẫậ', 'A': 'ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬ',
        'd': 'đ', 'D': 'Đ',
        'e': 'éèẻẽẹêếềểễệ', 'E': 'ÉÈẺẼẸÊẾỀỂỄỆ',
        'i': 'íìỉĩị', 'I': 'ÍÌỈĨỊ',
        'o': 'óòỏõọôốồổỗộơớờởỡợ', 'O': 'ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ',
        'u': 'úùủũụưứừửữự', 'U': 'ÚÙỦŨỤƯỨỪỬỮỰ',
        'y': 'ýỳỷỹỵ', 'Y': 'ÝỲỶỸỴ'
    }
    res = str(s)
    for r, chars in m.items():
        for c in chars:
            res = res.replace(c, r)
    return res

def sp(msg):
    print(strip_accents(msg))

def send_outlook_email(to_list, subject, html_content):
    sp(f"\n--- GOI OUTLOOK EMAIL SENDER ---")
    sp(f"Gui den: {', '.join(to_list)}")
    sp(f"Tieu de: {subject}")
    sp(f"--- [Chi tiet email da ghi nhan trong docs/email_log.txt] ---\n")
    
    log_dir = os.path.dirname(LOG_PATH)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"Thoi gian gui: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Nguoi nhan: {', '.join(to_list)}\n")
        f.write(f"Tieu de: {subject}\n")
        f.write(f"Noi dung Email (HTML):\n{html_content}\n")

def check_and_notify():
    sp("Bat dau quet trigger va gui canh bao tu dong...")
    
    if not os.path.exists(DB_PATH):
        sp("Loi: Database trung gian chua duoc khoi tao.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. QUET CANH BAO CONG NO QUA HAN (Tu receivable_detail)
    cursor.execute("""
        SELECT customer_code, customer_name, sales_channel, balance_end, total_overdue,
               overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45
        FROM receivable_detail
        WHERE total_overdue > 0
        ORDER BY total_overdue DESC
        LIMIT 15
    """)
    debt_rows = cursor.fetchall()
    debt_alerts = [dict(row) for row in debt_rows]
    
    # 2. QUET CHI SO DOANH THU TRONG NGAY MOI NHAT (Tu kpi_sales_product cua ky gan nhat)
    cursor.execute("""
        SELECT SUM(amount_item) FROM kpi_sales_product WHERE save_date = '2025-10-31'
    """)
    latest_sales = cursor.fetchone()[0] or 0
    
    # Moc trigger doanh thu trong ngay (Vi du: 200.000.000 VND)
    sales_trigger_limit = 200000000.0
    is_sales_triggered = latest_sales > sales_trigger_limit
    
    # 3. KHOI TAO NOI DUNG EMAIL BAO CAO
    if len(debt_alerts) > 0 or is_sales_triggered:
        subject = f"[DNH Canh Bao] Bao cao chi so & cong no Duoc Nam Ha ngay 2025-10-31"
        
        # HTML Content
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="background-color: #1e1b4b; padding: 20px; text-align: center; color: white;">
                <h2 style="margin:0;">Bao Cao Canh Bao Chi So Tu Dong</h2>
                <p style="margin:5px 0 0 0;">Duoc Nam Ha - Du lieu ngay 2025-10-31</p>
            </div>
            
            <div style="padding: 20px;">
                <h3>1. Chi So Doanh Thu Trong Ngay</h3>
                <p>Tong doanh thu ghi nhan trong ky: <strong>{latest_sales:,.2f} VND</strong></p>
        """
        if is_sales_triggered:
            html += f"""
                <div style="background-color: #d1fae5; border-left: 5px solid #10b981; padding: 10px; margin-bottom: 20px; color: #065f46;">
                    <strong>[Trigger Dat Moc]:</strong> Doanh thu trong ky da vuot moc trigger dinh san ({sales_trigger_limit:,.0f} VND).
                </div>
            """
        else:
            html += "<p><em>(Doanh thu chua cham moc trigger canh bao)</em></p>"
            
        # Add Debt Alerts Table
        if len(debt_alerts) > 0:
            html += """
                <h3>2. Top 15 Khach Hang Co No Qua Han Cao Nhat</h3>
                <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; text-align: left;">
                    <tr style="background-color: #f3f4f6;">
                        <th>Ma KH</th>
                        <th>Ten Khach Hang</th>
                        <th>Kenh</th>
                        <th>Tong Du No</th>
                        <th>No Qua Han</th>
                        <th>Phan Loai Qua Han</th>
                    </tr>
            """
            for alert in debt_alerts:
                # Detail breakdown
                breakdown = []
                if alert['overdue_1_15'] > 0: breakdown.append(f"1-15d: {alert['overdue_1_15']:,.0f}")
                if alert['overdue_15_30'] > 0: breakdown.append(f"15-30d: {alert['overdue_15_30']:,.0f}")
                if alert['overdue_30_45'] > 0: breakdown.append(f"30-45d: {alert['overdue_30_45']:,.0f}")
                if alert['overdue_gt_45'] > 0: breakdown.append(f">45d: {alert['overdue_gt_45']:,.0f}")
                breakdown_str = " | ".join(breakdown) if breakdown else "N/A"

                html += f"""
                    <tr>
                        <td>{alert['customer_code']}</td>
                        <td>{alert['customer_name']}</td>
                        <td>{alert['sales_channel']}</td>
                        <td>{alert['balance_end']:,.0f} VND</td>
                        <td style="color: red; font-weight: bold;">{alert['total_overdue']:,.0f} VND</td>
                        <td style="font-size: 12px; color: #555;">{breakdown_str}</td>
                    </tr>
                """
            html += """
                </table>
                <p style="color: #ef4444; margin-top: 15px;"><strong>Luu y:</strong> Vui long chi dao bo phan kinh doanh kiem tra lai truoc khi ky duyet don hang tiep theo cho cac doi tuong tren.</p>
            """
        else:
            html += "<h3>2. Danh Sach Khach Hang Vi Pham Cong No</h3><p><em>Khong co canh bao vi pham cong no ngay hom nay.</em></p>"
            
        html += """
            </div>
            <div style="background-color: #f3f4f6; padding: 10px; text-align: center; font-size: 11px; color: #6b7280; margin-top: 30px;">
                Email nay duoc gui tu dong tu he thong DNH Portal API. Vui long khong tra loi truc tiep email nay.
            </div>
        </body>
        </html>
        """
        
        # Gui email
        send_outlook_email(RECIPIENTS, subject, html)
        sp("Gui email canh bao hoan tat!")
    else:
        sp("Khong co trigger nao bi vuot nguong va khong co canh bao cong no ngay hom nay.")
        
    conn.close()

if __name__ == "__main__":
    check_and_notify()
