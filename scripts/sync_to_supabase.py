import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Load env variables
load_dotenv()

# Đường dẫn database SQLite trung gian cục bộ
LOCAL_DB = os.path.join(os.path.dirname(__file__), "dnh_intermediate.db")
# Đường dẫn kết nối CSDL Supabase PostgreSQL
CLOUD_DB_URL = os.getenv("CLOUD_DB_URL", "")

def sync_tables(tables_to_sync):
    if not CLOUD_DB_URL:
        print("[Loi]: Chua cau hinh bien CLOUD_DB_URL trong file .env!")
        return False
        
    if not os.path.exists(LOCAL_DB):
        print(f"[Loi]: Database cuc bo {LOCAL_DB} khong ton tai.")
        return False

    try:
        # Ket noi CSDL SQLite cuc bo
        sqlite_conn = sqlite3.connect(LOCAL_DB)
        
        # Sua giao thuc postgres:// thanh postgresql:// neu co (de SQLAlchemy tuong thich)
        db_url = CLOUD_DB_URL.strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        print("Dang ket noi den Cloud database (Supabase)...")
        postgres_engine = create_engine(db_url)
        
        for table in tables_to_sync:
            print(f"Dang doc bang '{table}' tu CSDL SQLite cuc bo...")
            df = pd.read_sql(f"SELECT * FROM {table}", sqlite_conn)
            print(f"  -> Tim thay {len(df)} dong. Dang day len Supabase...")
            
            # Ghi du lieu sang Postgres
            df.to_sql(table, postgres_engine, if_exists='replace', index=False)
            print(f"  -> Hoan thanh dong bo bang '{table}'!")
            
        sqlite_conn.close()
        return True
    except Exception as e:
        print(f"[Error]: Gap loi trong qua trinh dong bo: {e}")
        return False

def sync():
    print("=" * 60)
    print("BAT DAU DONG BO DU LIEU LEN CLOUD DATABASE (SUPABASE)")
    print("=" * 60)
    
    tables = [
        "regions", 
        "employees", 
        "customers", 
        "contracts", 
        "appendices", 
        "orders", 
        "invoices", 
        "inventory", 
        "kpi_summary", 
        "kpi_sales_product", 
        "kpi_sales_customer",
        "receivable_detail", 
        "receivable_etc"
    ]
    
    success = sync_tables(tables)
    if success:
        print("=" * 60)
        print("[Thanh cong]: DONG BO THANH CONG TOAN BO DU LIEU LEN SUPABASE CLOUD!")
        print("=" * 60)

if __name__ == "__main__":
    sync()
