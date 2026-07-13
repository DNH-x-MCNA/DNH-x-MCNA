import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text, inspect

# Đảm bảo console ghi nhận được tiếng Việt
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Nạp cấu hình từ .env ở thư mục gốc project — tính theo vị trí file này (không hardcode ổ đĩa/máy
# cụ thể), để chạy đúng trên bất kỳ máy nào project được deploy tới (vd máy 24), không chỉ D:\DNH.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# 1. Cấu hình Kết nối SQL Server Nguồn (Chỉ đọc) — đọc từ .env, KHÔNG hardcode mật khẩu
_bravo_server = os.getenv("BRAVO_SQL_SERVER", "")
_bravo_database = os.getenv("BRAVO_SQL_DATABASE", "")
_bravo_uid = os.getenv("BRAVO_SQL_UID", "")
_bravo_pwd = os.getenv("BRAVO_SQL_PWD", "")
if not all([_bravo_server, _bravo_database, _bravo_uid, _bravo_pwd]):
    print("[LỖI]: Thiếu BRAVO_SQL_SERVER/BRAVO_SQL_DATABASE/BRAVO_SQL_UID/BRAVO_SQL_PWD trong .env!")
    sys.exit(1)

SQL_SERVER_CONN = (
    "DRIVER={SQL Server};"
    f"SERVER={_bravo_server};"
    f"DATABASE={_bravo_database};"
    f"UID={_bravo_uid};"
    f"PWD={_bravo_pwd};"
    "TrustServerCertificate=yes;"
)

# 2. Cấu hình Kết nối Supabase Đích (Connection Pooler)
CLOUD_DB_URL = os.getenv("CLOUD_DB_URL", "")
if not CLOUD_DB_URL:
    print("[LỖI]: Không tìm thấy CLOUD_DB_URL trong file .env!")
    sys.exit(1)

# Sửa giao thức postgres:// thành postgresql://
db_url = CLOUD_DB_URL.strip()
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Định nghĩa khóa chính cho từng bảng trên Supabase để thực hiện UPSERT
TABLE_PRIMARY_KEYS = {
    "brv_hoadonhdr": ["Id"],
    "brv_hoadonct": ["Id"],
    "brvsx_hoadonhdr": ["Id"],
    "brvsx_hoadonct": ["Id"],
    "brvsx_tralai": ["Id"],
    "dms_khachhang": ["Id"],
    "dmssx_khachhang": ["Id"],
    "brv_sanpham": ["Id"],
    "dim_nhanvien": ["EmployeeCode"],
    "dim_tinhthanhpho": ["CityId"],
    "brv_trangthaihoadon": ["Id"],
    "brv_trangthaiduyet": ["Id"],
    # Thêm 08/07/2026 — 3 bảng chatbot đã có sẵn business rule dùng (xem ai_agent/chatbot.py)
    # nhưng trước đó CHƯA được sync, khiến câu hỏi về chỉ tiêu vùng/ETC/KPI chi tiết theo khách
    # hàng luôn lỗi hoặc rơi về fallback thô hơn. "Id" là PK thật đã xác nhận trong SQL Server
    # cho fact_kehoachtongetc/fact_tonghopkhachhang; dim_targetvungmien theo đúng pattern các
    # bảng "Id" khác ở trên (SQL Server không khai báo PK tường minh cho bảng này).
    "dim_targetvungmien": ["Id"],
    "fact_kehoachtongetc": ["Id"],
    "fact_tonghopkhachhang": ["Id"],
}

def get_sql_server_connection():
    import pyodbc
    return pyodbc.connect(SQL_SERVER_CONN)

def get_supabase_engine():
    from sqlalchemy.pool import NullPool
    # connect_timeout/statement_timeout: KHÔNG có timeout nào trước đây -> nếu Supabase phản hồi
    # chậm/quá tải (đã xác nhận thực tế 13/07/2026: sự cố đầy đĩa khiến kết nối treo im lặng),
    # script đứng vô thời hạn ở bảng đó thay vì báo lỗi + chuyển bảng tiếp theo như try/except
    # trong run_sync() đã thiết kế. Cùng giá trị connect_timeout với src/database.py::
    # _get_fast_cloud_engine (5s) để nhất quán; statement_timeout để cao hơn (60s) vì đây là
    # upsert hàng loạt (chunksize=2000), có thể lâu hơn 1 câu SELECT cảnh báo thông thường.
    return create_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=60000"},
    )

def fetch_table_schema_columns(sql_conn, schema, table_name):
    # Lấy danh sách cột thực tế của bảng SQL Server từ cursor description
    cursor = sql_conn.cursor()
    cursor.execute(f"SELECT TOP 1 * FROM [{schema}].[{table_name}]")
    return [col[0] for col in cursor.description]

def clean_dataframe(df):
    """Làm sạch kiểu dữ liệu để tương thích với PostgreSQL."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
    return df

def upsert_to_supabase(table_name, df, pg_engine, key_columns):
    """Thực hiện ghi đè dữ liệu (UPSERT) an toàn lên Supabase."""
    if df.empty:
        print(f"  -> Không có dữ liệu để đồng bộ cho '{table_name}'.")
        return

    ins = inspect(pg_engine)
    
    # 1. Tạo bảng nếu chưa tồn tại
    if not ins.has_table(table_name):
        print(f"  -> Tạo bảng mới '{table_name}' trên Supabase...")
        df.to_sql(table_name, pg_engine, if_exists='fail', index=False, chunksize=2000, method='multi')
        if key_columns:
            pk_cols = ", ".join([f'"{c}"' for c in key_columns])
            with pg_engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ({pk_cols})'))
            print(f"  -> Đã tạo khóa chính ({pk_cols}) cho '{table_name}'.")
        return

    # 2. Tạo bảng tạm (Staging table) với tên ngẫu nhiên tránh xung đột type trong PG
    import random
    temp_table = f"temp_{table_name}_stage_{random.randint(10000, 99999)}"
    df.to_sql(temp_table, pg_engine, if_exists='replace', index=False, chunksize=2000, method='multi')

    # 3. Tạo truy vấn UPSERT (ON CONFLICT DO UPDATE)
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
        upsert_query = f"""
            INSERT INTO "{table_name}" ({col_str})
            SELECT {col_str} FROM "{temp_table}"
            ON CONFLICT ({pk_str})
            DO NOTHING
        """

    # 4. Thực thi và dọn bảng tạm
    try:
        with pg_engine.begin() as conn:
            conn.execute(text(upsert_query))
            conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
        print(f"  -> Hoàn thành UPSERT {len(df):,} dòng vào '{table_name}'!")
    except Exception as ex:
        try:
            with pg_engine.begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
        except:
            pass
        raise ex

def run_sync():
    print("=" * 60)
    print("BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU CHỈ ĐỌC TỪ SQL SERVER -> SUPABASE (2025 - 2026)")
    print("=" * 60)
    
    sql_conn = get_sql_server_connection()
    pg_engine = get_supabase_engine()

    # Cửa sổ trượt "từ ngày 1 tháng TRƯỚC tới hiện tại" (tối thiểu ~30 ngày nếu hôm nay là đầu
    # tháng, tối đa ~62 ngày nếu hôm nay là cuối tháng) — đổi từ lọc cả năm (YEAR(x)=2026) sang đây
    # 13/07/2026 để giảm dung lượng Supabase sau sự cố đầy đĩa hôm nay (brv_hoadonct riêng đã
    # 226MB chỉ tính năm nay). Tính ĐỘNG mỗi lần chạy (không hardcode năm/tháng) bằng công thức
    # T-SQL chuẩn: DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 1, 0) = ngày 1 của tháng liền
    # trước tháng hiện tại.
    #
    # ĐÁNH ĐỔI CẦN BIẾT: các luồng cảnh báo/báo cáo CHÍNH đã Bravo-first (run_with_failover) không
    # bị ảnh hưởng — luôn đọc Bravo trực tiếp, không phụ thuộc cửa sổ này. CHỈ ảnh hưởng đường DỰ
    # PHÒNG Supabase khi Bravo tạm không truy cập được — riêng check_kpi_milestone_drop_alert
    # (src/alerts.py, cần so sánh lũy kế tới 5 tháng trước) sẽ dự phòng THIẾU dữ liệu nếu đúng lúc
    # đó Bravo cũng đang down — rủi ro hẹp (2 sự cố trùng lúc), đã cân nhắc và chấp nhận.
    ROLLING_WINDOW_DOCDATE = "DocDate >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 1, 0)"
    ROLLING_WINDOW_SAVEDATE = "SaveDate >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 1, 0)"

    # Định nghĩa cấu hình các bảng đồng bộ
    sync_config = [
        # --- Danh mục (Lấy toàn bộ) ---
        {"src": "dbo.DIM_NhanVien", "dest": "dim_nhanvien", "filter": None},
        {"src": "dbo.DMS_KhachHang", "dest": "dms_khachhang", "filter": None},
        {"src": "dbo.DMSSX_KhachHang", "dest": "dmssx_khachhang", "filter": None},
        {"src": "dbo.BRV_SanPham", "dest": "brv_sanpham", "filter": None},
        {"src": "dbo.DIM_TinhThanhPho", "dest": "dim_tinhthanhpho", "filter": None},
        {"src": "dbo.BRV_TrangThaiHoaDon", "dest": "brv_trangthaihoadon", "filter": None},
        {"src": "dbo.BRV_TrangThaiDuyet", "dest": "brv_trangthaiduyet", "filter": None},

        # --- Giao dịch (cửa sổ trượt ~30-62 ngày gần nhất — xem ghi chú ROLLING_WINDOW_* ở trên) ---
        {
            "src": "dbo.BRV_HoaDonHdr",
            "dest": "brv_hoadonhdr",
            "filter": ROLLING_WINDOW_DOCDATE
        },
        {
            "src": "dbo.BRV_HoaDonCt",
            "dest": "brv_hoadonct",
            "filter": f"Stt IN (SELECT Stt FROM dbo.BRV_HoaDonHdr WHERE {ROLLING_WINDOW_DOCDATE})"
        },
        {
            "src": "dbo.BRVSX_HoaDonHdr",
            "dest": "brvsx_hoadonhdr",
            "filter": ROLLING_WINDOW_DOCDATE
        },
        {
            "src": "dbo.BRVSX_HoaDonCt",
            "dest": "brvsx_hoadonct",
            "filter": f"Stt IN (SELECT Stt FROM dbo.BRVSX_HoaDonHdr WHERE {ROLLING_WINDOW_DOCDATE})"
        },
        {
            "src": "dbo.BRVSX_TraLai",
            "dest": "brvsx_tralai",
            "filter": ROLLING_WINDOW_DOCDATE
        },

        # --- Thêm 08/07/2026: chỉ tiêu vùng/ETC + KPI chi tiết theo khách hàng ---
        {
            "src": "dbo.DIM_TargetVungMien",
            "dest": "dim_targetvungmien",
            "filter": ROLLING_WINDOW_DOCDATE
        },
        {
            "src": "dbo.FACT_KeHoachTongETC",
            "dest": "fact_kehoachtongetc",
            "filter": ROLLING_WINDOW_DOCDATE
        },
        {
            "src": "dbo.FACT_TongHopKhachHang",
            "dest": "fact_tonghopkhachhang",
            "filter": ROLLING_WINDOW_SAVEDATE
        }
    ]

    for item in sync_config:
        src_table = item["src"]
        dest_table = item["dest"]
        filter_cond = item["filter"]
        
        print(f"\n[*] Đang xử lý bảng '{src_table}' -> '{dest_table}'...")
        
        try:
            # 1. Lấy danh sách cột thực tế của bảng nguồn
            schema, table_name = src_table.split(".")
            cols = fetch_table_schema_columns(sql_conn, schema, table_name)
            col_list_str = ", ".join([f"[{c}]" for c in cols])
            
            # 2. Xây dựng truy vấn đọc
            if filter_cond:
                query = f"SELECT {col_list_str} FROM {src_table} WITH (NOLOCK) WHERE {filter_cond}"
            else:
                query = f"SELECT {col_list_str} FROM {src_table} WITH (NOLOCK)"
            
            # 3. Đọc dữ liệu về DataFrame dùng kết nối pyodbc trực tiếp
            df = pd.read_sql(query, sql_conn)
            
            print(f"  -> Đọc thành công {len(df):,} dòng từ SQL Server.")
            
            # 4. Làm sạch dữ liệu và đẩy lên Supabase
            df_cleaned = clean_dataframe(df)
            key_cols = TABLE_PRIMARY_KEYS.get(dest_table, [])
            upsert_to_supabase(dest_table, df_cleaned, pg_engine, key_cols)
            
        except Exception as e:
            # SQLAlchemy tự in kèm CẢ câu SQL lẫn TOÀN BỘ tham số bind khi lỗi xảy ra trên câu
            # upsert hàng loạt (vd 2000 dòng/chunk) -> str(e) có thể dài hàng chục nghìn ký tự,
            # tràn terminal, không dán lại được để debug. Cắt ngắn, chỉ giữ phần đầu đủ để biết
            # loại lỗi (vd OperationalError/timeout) — xác nhận thực tế 13/07/2026.
            err_text = str(e)
            if len(err_text) > 500:
                err_text = err_text[:500] + f"... (cắt bớt, dài {len(err_text)} ký tự)"
            print(f"  -> [THẤT BẠI] Lỗi khi xử lý bảng '{dest_table}': {err_text}")

    try:
        sql_conn.close()
        print("\nĐã đóng kết nối SQL Server an toàn.")
    except:
        pass

    print("\n" + "=" * 60)
    print("QUÁ TRÌNH ĐỒNG BỘ HOÀN TẤT!")
    print("=" * 60)

def run_alert_checks_after_sync():
    """
    Quét cảnh báo nghiệp vụ NGAY sau khi đồng bộ xong — đây là điểm duy nhất dữ liệu thực sự
    thay đổi (task này chạy 5 lần/ngày theo lịch cố định), nên trigger cảnh báo tại đây cho độ
    trễ gần như bằng 0, thay vì chờ vòng lặp poll định kỳ của DNH_Realtime_Alerts (service đó
    giờ chỉ còn vai trò lưới an toàn dự phòng — xem main.py).
    """
    try:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from main import run_all_alert_checks
        from src.database import load_config

        print("\n" + "=" * 60)
        print("QUÉT CẢNH BÁO NGHIỆP VỤ TRÊN DỮ LIỆU VỪA ĐỒNG BỘ...")
        print("=" * 60)
        run_all_alert_checks(load_config())
    except Exception as e:
        print(f"[CẢNH BÁO] Lỗi khi quét cảnh báo sau đồng bộ: {e}")

if __name__ == "__main__":
    run_sync()
    run_alert_checks_after_sync()
