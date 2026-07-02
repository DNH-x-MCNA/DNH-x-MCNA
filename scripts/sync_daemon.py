import time
import os
import sys
import threading
import urllib.request
import urllib.error
import json
from datetime import datetime
from dotenv import load_dotenv

# Thêm thư mục cha vào sys.path để import được module trong scripts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.sync_to_supabase import sync_tables
from src.alerts import run_smart_business_alerts, run_sales_kpi_insights_alert
from ai_agent.chatbot import DNHChatbot

def send_telegram_photo(token, chat_id, photo_path, caption=None):
    """
    Gửi ảnh biểu đồ qua Telegram Bot API (multipart/form-data)
    """
    import uuid
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = f"----TelegramBotBoundary{uuid.uuid4().hex}"
    
    if not os.path.exists(photo_path):
        print(f"[TELEGRAM_BOT] File anh bieu do {photo_path} khong ton tai.")
        return False
        
    try:
        with open(photo_path, 'rb') as f:
            file_data = f.read()
            
        filename = os.path.basename(photo_path)
        parts = []
        
        # Field: chat_id
        parts.append(f"--{boundary}\r\n".encode('utf-8'))
        parts.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode('utf-8'))
        
        # Field: caption
        if caption:
            parts.append(f"--{boundary}\r\n".encode('utf-8'))
            safe_caption = caption[:1000]
            parts.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n{safe_caption}\r\n'.encode('utf-8'))
            
        # Field: photo
        parts.append(f"--{boundary}\r\n".encode('utf-8'))
        parts.append(f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode('utf-8'))
        parts.append('Content-Type: image/png\r\n\r\n'.encode('utf-8'))
        parts.append(file_data)
        parts.append('\r\n'.encode('utf-8'))
        
        parts.append(f"--{boundary}--\r\n".encode('utf-8'))
        body = b"".join(parts)
        
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(body))
            }
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res.get("ok", False)
    except Exception as e:
        print(f"[TELEGRAM_BOT] Loi gui anh bieu do: {e}")
        return False

def start_telegram_bot_thread():
    """
    Tiến trình chạy ngầm lắng nghe tin nhắn Telegram Bot và tự động trả lời bằng AI.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[TELEGRAM_BOT] TELEGRAM_BOT_TOKEN không tìm thấy trong file .env. Bỏ qua chạy chatbot.")
        return
        
    print("[TELEGRAM_BOT] Bắt đầu khởi chạy tiến trình lắng nghe Telegram Bot (Long polling)...")
    chatbot = DNHChatbot()
    offset = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=35) as response:
                res = json.loads(response.read().decode('utf-8'))
                if not res.get("ok"):
                    time.sleep(5)
                    continue
                    
                for update in res.get("result", []):
                    update_id = update["update_id"]
                    offset = update_id + 1
                    
                    message = update.get("message")
                    if not message or "chat" not in message:
                        continue
                        
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")
                    
                    if not text:
                        continue
                        
                    print(f"[TELEGRAM_BOT] Nhận tin nhắn từ Chat ID {chat_id}: {text}")
                    
                    # Gọi Chatbot AI trả lời
                    reply = chatbot.ask(text)
                    answer = reply.get("answer", "Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi của bạn.")
                    chart_path = reply.get("chart_path")
                    
                    # Nếu có biểu đồ, gửi ảnh biểu đồ trước
                    if chart_path and os.path.exists(chart_path):
                        print(f"[TELEGRAM_BOT] Phat hien bieu do tai {chart_path}. Dang gui anh...")
                        send_telegram_photo(
                            token=token,
                            chat_id=chat_id,
                            photo_path=chart_path,
                            caption=f"📊 Biểu đồ phân tích cho câu hỏi: \"{text[:100]}\""
                        )
                        try:
                            os.remove(chart_path)
                        except Exception as ex:
                            print(f"[TELEGRAM_BOT] Loi xoa file bieu do tam: {ex}")
                    
                    # Gửi câu trả lời văn bản chi tiết về cho user
                    send_url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = {
                        "chat_id": chat_id,
                        "text": answer,
                        "parse_mode": "HTML"
                    }
                    
                    data = json.dumps(payload).encode('utf-8')
                    send_req = urllib.request.Request(
                        send_url,
                        data=data,
                        headers={'Content-Type': 'application/json'}
                    )
                    with urllib.request.urlopen(send_req, timeout=15) as send_resp:
                        print(f"[TELEGRAM_BOT] Đã phản hồi tin nhắn thành công tới Chat ID {chat_id}!")
                        
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            print(f"[TELEGRAM_BOT] Lỗi HTTP {e.code} trong vòng lặp bot: {err_body}")
            time.sleep(10)
        except Exception as e:
            print(f"[TELEGRAM_BOT] Lỗi trong vòng lặp bot: {e}")
            time.sleep(10)

def main():
    print("=" * 60)
    print(" KHOI CHAY DICH VU DONG BO DU LIEU & CANH BAO DOANH NGHIEP")
    print(" Dich vu chay nen de giu du lieu luon cap nhat va phat alert.")
    print("=" * 60)
    
    # Khởi chạy bot chat Telegram trong luồng riêng biệt
    load_dotenv()
    bot_thread = threading.Thread(target=start_telegram_bot_thread, daemon=True)
    bot_thread.start()
    
    # Luu moc thoi gian cua lan dong bo cuoi (epoch time)
    last_sync = {
        "fast": 0.0,    # Dong bo nhanh (moi 1 phut) - Danh cho Doanh so/Don hang
        "medium": 0.0,  # Dong bo trung binh (moi 5 phut) - Danh cho Cong no + Phat canh bao
        "slow": 0.0     # Dong bo cham (moi 30 phut) - Danh cho Ton kho, KPIs va Danh muc
    }
    
    # Dinh nghia nhom bang theo gop y nghiep vu cua nguoi dung
    groups = {
        "fast": ["orders", "invoices"],
        "medium": ["receivable_detail", "receivable_etc"],
        "slow": [
            "inventory", 
            "regions", "employees", "customers", 
            "contracts", "appendices", "kpi_summary", 
            "kpi_sales_product", "kpi_sales_customer"
        ]
    }
    
    # Chay canh bao khoi tao 1 lan duy nhat khi vua bat dich vu de check ket noi
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Kiem tra canh bao khoi tao luc bat dau...")
    run_smart_business_alerts()
    run_sales_kpi_insights_alert()
    
    while True:
        try:
            now = time.time()
            
            # 1. Dong bo NHANH (Moi 1 phut - 60 giay): Doanh so va Hoa don moi
            if now - last_sync["fast"] >= 60:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Bat dau dong bo NHANH (chu ky 60s) ---")
                sync_tables(groups["fast"])
                last_sync["fast"] = now
                
            # 2. Dong bo TRUNG BINH (Moi 5 phut - 300 giay): Cong no thay doi & Phat canh bao
            if now - last_sync["medium"] >= 300:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Bat dau dong bo TRUNG BINH (chu ky 5m) ---")
                sync_tables(groups["medium"])
                # Phat canh bao ngay sau khi nạp xong du lieu cong no moi
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Dang quet canh bao nghiep vu...")
                run_smart_business_alerts()
                run_sales_kpi_insights_alert()
                last_sync["medium"] = now
                
            # 3. Dong bo CHAM (Moi 30 phut - 1800 giay): Ton kho thuc te, KPIs luong va Danh muc
            if now - last_sync["slow"] >= 1800:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Bat dau dong bo CHAM (chu ky 30m) ---")
                sync_tables(groups["slow"])
                last_sync["slow"] = now
                
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Loi trong vong lap cua Daemon: {e}")
            
        # Nghi ngan 5 giay truoc khi kiem tra lai
        time.sleep(5)

if __name__ == "__main__":
    main()
