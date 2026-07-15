import os
import sys
import sqlite3
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

# Đảm bảo terminal/log ghi nhận được tiếng Việt có dấu
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Load env variables
load_dotenv()

# Đường dẫn database SQLite trung gian cục bộ
LOCAL_DB = os.path.join(os.path.dirname(__file__), "dnh_intermediate.db")
# Đường dẫn kết nối CSDL Supabase PostgreSQL — dùng SYNC_CLOUD_DB_URL riêng nếu có (để service
# ghi này luôn nhắm đúng production, độc lập với CLOUD_DB_URL mà chatbot/alert/dashboard đang đọc,
# phòng khi CLOUD_DB_URL bị trỏ tạm sang Supabase dev/test).
CLOUD_DB_URL = os.getenv("SYNC_CLOUD_DB_URL") or os.getenv("CLOUD_DB_URL", "")

# Định nghĩa các khóa chính (Primary Keys) cho từng bảng để thực hiện UPSERT
TABLE_PRIMARY_KEYS = {
    "regions": ["region_id"],
    "employees": ["employee_id"],
    "customers": ["customer_id"],
    "contracts": ["contract_id"],
    "appendices": ["appendix_id"],
    "orders": ["order_id"],
    "invoices": ["invoice_id"],
    "inventory": ["item_code"],
    "kpi_summary": ["id"],
    "kpi_sales_product": ["id"],
    "kpi_sales_customer": ["id"],
    "receivable_detail": ["id"],
    "receivable_etc": ["id"]
}

# Các index cần đảm bảo tồn tại sau đồng bộ
POST_SYNC_INDEXES = {
    "receivable_detail": [
        'CREATE INDEX IF NOT EXISTS idx_receivable_detail_period ON receivable_detail("period")',
    ],
    "receivable_etc": [
        'CREATE INDEX IF NOT EXISTS idx_receivable_etc_customer ON receivable_etc("customer_code")',
    ],
}

def sync_table_upsert(table_name, df, engine, key_columns):
    """
    Thực hiện UPSERT (Insert or Update) dữ liệu từ DataFrame vào bảng PostgreSQL.
    Bảo đảm:
      - Không DROP bảng (giữ nguyên kết nối, RLS, Indexes, và không gây mất dữ liệu tạm thời).
      - Đồng bộ Idempotent bằng mệnh đề ON CONFLICT DO UPDATE.
    """
    ins = inspect(engine)
    
    # 1. Nếu bảng chưa tồn tại trên Cloud, tạo mới bảng và thêm ràng buộc khóa chính
    if not ins.has_table(table_name):
        print(f"  -> Bảng '{table_name}' chưa tồn tại trên Cloud. Khởi tạo cấu trúc bảng...")
        df.to_sql(table_name, engine, if_exists='fail', index=False)
        
        if key_columns:
            pk_cols = ", ".join([f'"{c}"' for c in key_columns])
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ({pk_cols})'))
            print(f"  -> Đã gán Khóa chính ({pk_cols}) cho bảng '{table_name}'.")
        return

    if df.empty:
        print(f"  -> Bảng '{table_name}' rỗng, không có dữ liệu để đồng bộ.")
        return

    # 2. Đẩy dữ liệu vào bảng tạm (Temporary Staging Table)
    temp_table = f"temp_{table_name}_stage"
    df.to_sql(temp_table, engine, if_exists='replace', index=False)
    
    # 3. Tạo câu lệnh SQL UPSERT (ON CONFLICT DO UPDATE)
    columns = [f'"{col}"' for col in df.columns]
    update_sets = [f'"{col}" = EXCLUDED."{col}"' for col in df.columns if col not in key_columns]
    
    col_str = ", ".join(columns)
    pk_str = ", ".join([f'"{c}"' for c in key_columns])
    
    if update_sets:
        update_str = ", ".join(update_sets)
        upsert_query = f"""
            INSERT INTO "{table_name}" ({col_str})
            SELECT {col_str} FROM "{temp_table}"
            ON CONFLICT ({pk_str})
            DO UPDATE SET {update_str}
        """
    else:
        # Nếu bảng chỉ có cột khóa chính, chọn DO NOTHING khi trùng lặp
        upsert_query = f"""
            INSERT INTO "{table_name}" ({col_str})
            SELECT {col_str} FROM "{temp_table}"
            ON CONFLICT ({pk_str})
            DO NOTHING
        """
        
    # 4. Thực thi câu lệnh UPSERT và dọn dẹp bảng tạm
    try:
        with engine.begin() as conn:
            conn.execute(text(upsert_query))
            conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
        print(f"  -> Hoàn thành UPSERT {len(df)} dòng vào bảng '{table_name}'!")
    except Exception as ex:
        # Cố gắng dọn dẹp bảng tạm kể cả khi lỗi
        try:
            with engine.begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
        except Exception:
            pass
        raise ex

def sync_tables(tables_to_sync):
    if not CLOUD_DB_URL:
        print("[Lỗi]: Chưa cấu hình biến CLOUD_DB_URL trong file .env!")
        return False
        
    if not os.path.exists(LOCAL_DB):
        print(f"[Lỗi]: Database cục bộ {LOCAL_DB} không tồn tại.")
        return False

    sqlite_conn = None
    postgres_engine = None
    try:
        # Kết nối CSDL SQLite cục bộ
        sqlite_conn = sqlite3.connect(LOCAL_DB)
        
        # Sửa giao thức postgres:// thành postgresql:// nếu có
        db_url = CLOUD_DB_URL.strip()
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        print("Đang kết nối đến Cloud database (Supabase)...")
        # Giới hạn size của pool và thêm pre-ping để tái sử dụng kết nối hiệu quả
        postgres_engine = create_engine(
            db_url,
            pool_size=3,
            max_overflow=2,
            pool_recycle=1800,
            pool_pre_ping=True
        )
        
        for table in tables_to_sync:
            print(f"Đang đọc bảng '{table}' từ CSDL SQLite cục bộ...")
            df = pd.read_sql(f"SELECT * FROM {table}", sqlite_conn)
            
            # Thực hiện UPSERT đồng bộ
            key_columns = TABLE_PRIMARY_KEYS.get(table, [])
            sync_table_upsert(table, df, postgres_engine, key_columns)

            # Đảm bảo các chỉ mục (indexes) tồn tại
            for stmt in POST_SYNC_INDEXES.get(table, []):
                try:
                    with postgres_engine.begin() as conn:
                        conn.execute(text(stmt))
                except Exception as ie:
                    print(f"  -> [Cảnh báo] Không tạo được index cho '{table}': {ie}")

        return True
    except Exception as e:
        print(f"[Error]: Gặp lỗi trong quá trình đồng bộ: {e}")
        return False
    finally:
        # Giải phóng kết nối an toàn trong khối finally
        if sqlite_conn:
            try:
                sqlite_conn.close()
            except Exception:
                pass
        if postgres_engine:
            try:
                postgres_engine.dispose()
                print("Đã đóng kết nối và giải phóng Connection Pool của Supabase.")
            except Exception:
                pass

def sync():
    print("=" * 60)
    print("BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU BẰNG UPSERT LÊN SUPABASE CLOUD")
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
        print("[Thành công]: ĐỒNG BỘ BẰNG UPSERT HOÀN THÀNH LÊN SUPABASE!")
        print("=" * 60)

if __name__ == "__main__":
    sync()
