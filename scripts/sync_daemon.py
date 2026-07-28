import time
import os
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime
from dotenv import load_dotenv

# Thêm thư mục cha vào sys.path để import được module trong scripts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.sync_to_supabase import sync_tables
from src.alerts import run_smart_business_alerts, run_sales_kpi_insights_alert

def main():
    print("=" * 60)
    print(" KHOI CHAY DICH VU DONG BO DU LIEU & CANH BAO DOANH NGHIEP")
    print(" Dich vu chay nen de giu du lieu luon cap nhat va phat alert.")
    print("=" * 60)

    load_dotenv()

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
    try:
        run_smart_business_alerts()
        run_sales_kpi_insights_alert()
    except Exception as e:
        print(f"[DAEMON] Error running initial alerts: {e}")
    
    while True:
        try:
            now = time.time()
            
            # 1. Dong bo NHANH (Moi 1 phut - 60 giay): Doanh so va Hoa don moi
            if now - last_sync["fast"] >= 60:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Bat dau dong bo NHANH (chu ky 60s) ---")
                sync_tables(groups["fast"])
                last_sync["fast"] = time.time()  # Set AFTER execution to avoid tight loop thrashing
                
            # 2. Dong bo TRUNG BINH (Moi 5 phut - 300 giay): Cong no thay doi & Phat canh bao
            if now - last_sync["medium"] >= 300:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Bat dau dong bo TRUNG BINH (chu ky 5m) ---")
                sync_tables(groups["medium"])
                # Phat canh bao ngay sau khi nạp xong du lieu cong no moi
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Dang quet canh bao nghiep vu...")
                run_smart_business_alerts()
                run_sales_kpi_insights_alert()
                last_sync["medium"] = time.time()  # Set AFTER execution
                
            # 3. Dong bo CHAM (Moi 30 phut - 1800 giay): Ton kho thuc te, KPIs luong va Danh muc
            if now - last_sync["slow"] >= 1800:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Bat dau dong bo CHAM (chu ky 30m) ---")
                sync_tables(groups["slow"])
                last_sync["slow"] = time.time()  # Set AFTER execution
                
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Loi trong vong lap cua Daemon: {e}")
            
        # Nghi ngan 5 giay truoc khi kiem tra lai
        time.sleep(5)

if __name__ == "__main__":
    main()
