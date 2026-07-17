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
    # Thêm 13/07/2026 — bảng inventory tính từ Bravo TheKhoLot + TonKhoDK, tách OTC/ETC
    "inventory": ["item_code", "channel"],
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

# 16/07/2026: 2 bảng kiểm soát vận hành ETL còn thiếu theo đúng kế hoạch gốc (skill
# dnh-realtime-etl-pipeline đã chỉ rõ đây là gap) — theo yêu cầu DNH sau họp 16/07: tập trung
# "tính chính xác + tính mở rộng", cụ thể là kiểm soát được ETL dễ hơn. KHÔNG đổi filter/upsert
# logic hiện có — chỉ bổ sung ghi log/watermark sau mỗi bảng đã sync như trước.
#
# etl_run_log: LỊCH SỬ đầy đủ, 1 dòng/bảng/lần chạy — trả lời được "lần nào lỗi, lỗi gì, chậm
# bao lâu, đồng bộ được bao nhiêu dòng" — trước đây không lưu lại được gì, chỉ in ra console rồi
# mất khi cửa sổ terminal đóng.
#
# etl_sync_watermark: TRẠNG THÁI HIỆN TẠI, 1 dòng/bảng (upsert đè), tra cứu nhanh "bảng X lần
# cuối đồng bộ thành công lúc nào" mà không cần quét etl_run_log — dùng thay cho cách cũ
# check_etl_freshness_alert phải tự query ad-hoc MAX(SyncAt) trên đúng 1 bảng brv_hoadonct mỗi
# lần chạy (src/alerts.py::check_etl_freshness_alert), không biết gì về CÁC bảng khác.
ETL_CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS etl_run_log (
    id              BIGSERIAL PRIMARY KEY,
    table_name      text NOT NULL,
    run_started_at  timestamp NOT NULL,
    run_finished_at timestamp,
    status          text NOT NULL,      -- 'success' | 'failed'
    rows_synced     integer,
    rows_purged     integer,
    error_message   text
);
CREATE INDEX IF NOT EXISTS idx_etl_run_log_table_time ON etl_run_log (table_name, run_started_at);

CREATE TABLE IF NOT EXISTS etl_sync_watermark (
    table_name        text PRIMARY KEY,
    last_run_at       timestamp NOT NULL,
    last_success_at   timestamp,
    last_status       text NOT NULL,
    rows_synced       integer
);
"""


def ensure_etl_control_tables(pg_engine):
    """Tạo etl_run_log/etl_sync_watermark nếu chưa có — an toàn gọi lại nhiều lần (IF NOT EXISTS),
    không đổi gì nếu bảng đã tồn tại."""
    with pg_engine.begin() as conn:
        for stmt in ETL_CONTROL_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))


def log_sync_run(pg_engine, table_name, started_at, status, rows_synced=None, rows_purged=None, error_message=None):
    """Ghi 1 dòng lịch sử vào etl_run_log + cập nhật trạng thái mới nhất vào etl_sync_watermark.
    Lỗi khi ghi log KHÔNG được làm chết cả job đồng bộ chính — chỉ in cảnh báo rồi bỏ qua, đúng
    tinh thần các log phụ trợ khác trong dự án (vd _log_alert_severity trong src/notifier.py)."""
    finished_at = datetime.now()
    if error_message and len(error_message) > 1000:
        error_message = error_message[:1000] + f"... (cắt bớt, dài {len(error_message)} ký tự)"
    try:
        with pg_engine.begin() as conn:
            conn.execute(text('''
                INSERT INTO etl_run_log (table_name, run_started_at, run_finished_at, status, rows_synced, rows_purged, error_message)
                VALUES (:table_name, :started_at, :finished_at, :status, :rows_synced, :rows_purged, :error_message)
            '''), {
                "table_name": table_name, "started_at": started_at, "finished_at": finished_at,
                "status": status, "rows_synced": rows_synced, "rows_purged": rows_purged, "error_message": error_message,
            })
            conn.execute(text('''
                INSERT INTO etl_sync_watermark (table_name, last_run_at, last_success_at, last_status, rows_synced)
                VALUES (:table_name, :run_at, :success_at, :status, :rows_synced)
                ON CONFLICT (table_name) DO UPDATE SET
                    last_run_at = EXCLUDED.last_run_at,
                    last_success_at = COALESCE(EXCLUDED.last_success_at, etl_sync_watermark.last_success_at),
                    last_status = EXCLUDED.last_status,
                    rows_synced = EXCLUDED.rows_synced
            '''), {
                "table_name": table_name, "run_at": finished_at,
                "success_at": finished_at if status == "success" else None,
                "status": status, "rows_synced": rows_synced,
            })
    except Exception as e:
        print(f"  -> [CẢNH BÁO] Không ghi được etl_run_log/etl_sync_watermark cho '{table_name}' (bỏ qua, không ảnh hưởng sync): {e}")


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

def sync_inventory_from_bravo(dry_run=False):
    """
    Tính toán bảng inventory (tồn kho) từ dữ liệu thô Bravo:
      - BRV_TheKhoLot + BRV_TonKhoDK + BRV_SanPham  (OTC)
      - BRVSX_TheKhoLot + BRVSX_TonKhoDK + BRVSX_SanPham  (ETC)
    rồi UPSERT lên Supabase bảng `inventory` (PK = item_code + channel).

    Công thức:
      opening_qty  = SUM(TonKhoDK.Quantity) cho năm tài chính hiện tại
      inward_qty   = SUM(TheKhoLot.ReceiptQuantity) cho năm tài chính hiện tại
      outward_qty  = SUM(TheKhoLot.IssueQuantity) cho năm tài chính hiện tại
      closing_qty  = opening_qty + inward_qty - outward_qty
      months_to_sell = closing_qty / (outward_qty / months_elapsed)  [0 nếu không bán]
      closing_value  = 0  (tạm — BRV_TonKhoDK.Amount phần lớn = 0, chờ DNH xác nhận nguồn)

    Tách riêng OTC / ETC thành 2 dòng (cùng item_code có thể xuất hiện ở cả 2 kênh).
    dry_run=True chỉ in kết quả, không upsert.
    """
    print("\n" + "=" * 60)
    print("ĐỒNG BỘ TỒN KHO: BRAVO -> SUPABASE (inventory)")
    print("=" * 60)

    fiscal_year = str(datetime.now().year)
    # Số tháng đã trôi qua từ đầu năm (dùng tính avg_monthly_sales)
    now = datetime.now()
    months_elapsed = (now.month - 1) + now.day / 30.0  # xấp xỉ, đủ chính xác cho months_to_sell
    if months_elapsed < 0.5:
        months_elapsed = 0.5  # tránh chia 0 đầu tháng 1

    sql_conn = get_sql_server_connection()

    # Cấu hình 2 kênh: (channel_label, SanPham_table, TonKhoDK_table, TheKhoLot_table, year_col)
    channel_configs = [
        ("OTC", "BRV_SanPham", "BRV_TonKhoDK", "BRV_TheKhoLot", "FiscalYear"),
        ("ETC", "BRVSX_SanPham", "BRVSX_TonKhoDK", "BRVSX_TheKhoLot", "FiscalYear"),
    ]

    all_rows = []
    for channel, sp_tbl, dk_tbl, tk_tbl, yr_col in channel_configs:
        # BRVSX_TonKhoDK dùng cột "Year" thay vì "FiscalYear"
        # Kiểm tra tên cột thực tế
        cursor = sql_conn.cursor()
        cursor.execute(f"SELECT TOP 1 * FROM [{dk_tbl}]")
        dk_cols = [col[0] for col in cursor.description]
        cursor.close()
        actual_yr_col = "FiscalYear" if "FiscalYear" in dk_cols else "Year"

        query = f"""
            SELECT s.Code AS item_code, s.Name AS item_name, s.Unit AS unit,
                ISNULL(dk.open_qty, 0) AS opening_qty,
                ISNULL(tk.total_receipt, 0) AS inward_qty,
                ISNULL(tk.total_issue, 0) AS outward_qty
            FROM [{sp_tbl}] s
            LEFT JOIN (
                SELECT ItemId, SUM(Quantity) AS open_qty
                FROM [{dk_tbl}] WHERE [{actual_yr_col}] = ?
                GROUP BY ItemId
            ) dk ON dk.ItemId = s.Id
            LEFT JOIN (
                SELECT ItemId,
                    SUM(ReceiptQuantity) AS total_receipt,
                    SUM(IssueQuantity) AS total_issue
                FROM [{tk_tbl}] WHERE FiscalYear = ?
                GROUP BY ItemId
            ) tk ON tk.ItemId = s.Id
            WHERE ISNULL(dk.open_qty, 0) + ISNULL(tk.total_receipt, 0) + ISNULL(tk.total_issue, 0) > 0
        """
        df = pd.read_sql(query, sql_conn, params=[fiscal_year, fiscal_year])
        df["channel"] = channel
        print(f"  [{channel}] Đọc {len(df):,} mặt hàng có biến động năm {fiscal_year} từ Bravo.")
        all_rows.append(df)

    if not all_rows:
        print("  -> Không có dữ liệu tồn kho nào từ Bravo.")
        try:
            sql_conn.close()
        except:
            pass
        return

    df_all = pd.concat(all_rows, ignore_index=True)

    # Tính closing_qty, months_to_sell
    df_all["closing_qty"] = df_all["opening_qty"] + df_all["inward_qty"] - df_all["outward_qty"]
    df_all["closing_value"] = 0.0  # tạm — chờ DNH xác nhận nguồn giá trị tồn kho

    def calc_months_to_sell(row):
        if row["closing_qty"] <= 0:
            return 0.0
        if row["outward_qty"] <= 0:
            return 9999.0  # không bán được -> tồn vĩnh viễn
        avg_monthly = row["outward_qty"] / months_elapsed
        if avg_monthly <= 0:
            return 9999.0
        return round(row["closing_qty"] / avg_monthly, 2)

    df_all["months_to_sell"] = df_all.apply(calc_months_to_sell, axis=1)
    df_all["warehouse"] = None  # gộp tất cả kho, không phân biệt

    # Chỉ giữ các cột đúng schema inventory
    inventory_cols = ["item_code", "item_name", "unit", "opening_qty", "inward_qty",
                      "outward_qty", "closing_qty", "closing_value", "months_to_sell",
                      "warehouse", "channel"]
    df_final = df_all[inventory_cols].copy()

    # Làm sạch
    df_final = clean_dataframe(df_final)

    print(f"  -> Tổng cộng {len(df_final):,} dòng inventory (OTC + ETC tách riêng).")
    stats = df_final.groupby("channel").agg(
        count=("item_code", "count"),
        has_stock=("closing_qty", lambda x: (x > 0).sum()),
        near_stockout=("months_to_sell", lambda x: ((x > 0) & (x <= 1.0)).sum()),
    )
    for ch, row in stats.iterrows():
        print(f"     {ch}: {row['count']} mặt hàng, {row['has_stock']} còn tồn, {row['near_stockout']} sắp hết")

    if dry_run:
        print("  [DRY RUN] Không upsert. Mẫu 5 dòng đầu:")
        print(df_final.head().to_string(index=False))
    else:
        pg_engine = get_supabase_engine()
        key_cols = TABLE_PRIMARY_KEYS["inventory"]
        upsert_to_supabase("inventory", df_final, pg_engine, key_cols)

    try:
        sql_conn.close()
    except:
        pass
    print("  -> Hoàn thành đồng bộ tồn kho!")


def run_sync():
    print("=" * 60)
    print("BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU CHỈ ĐỌC TỪ SQL SERVER -> SUPABASE (2025 - 2026)")
    print("=" * 60)
    
    sql_conn = get_sql_server_connection()
    pg_engine = get_supabase_engine()
    ensure_etl_control_tables(pg_engine)

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
    # Vế Postgres tương đương, dùng để XOÁ dữ liệu CŨ đã có sẵn trên Supabase từ trước (khi còn
    # lọc cả năm) — chỉ đổi filter đọc thôi KHÔNG tự dọn dữ liệu cũ đã tồn tại, phải tự xoá thêm
    # mới thật sự giảm dung lượng. "purge" chạy SAU upsert, trên pg_engine (Postgres/Supabase).
    PG_WINDOW_START = "DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'"

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
            "filter": ROLLING_WINDOW_DOCDATE,
            "purge": f'DELETE FROM brv_hoadonhdr WHERE "DocDate"::date < {PG_WINDOW_START}'
        },
        {
            "src": "dbo.BRV_HoaDonCt",
            "dest": "brv_hoadonct",
            "filter": f"Stt IN (SELECT Stt FROM dbo.BRV_HoaDonHdr WHERE {ROLLING_WINDOW_DOCDATE})",
            # Chạy SAU khi brv_hoadonhdr đã purge — xoá luôn các dòng chi tiết mồ côi (Stt không
            # còn tồn tại ở bảng hóa đơn đã bị dọn), vì brv_hoadonct không có cột ngày riêng.
            "purge": 'DELETE FROM brv_hoadonct WHERE "Stt" NOT IN (SELECT "Stt" FROM brv_hoadonhdr)'
        },
        {
            "src": "dbo.BRVSX_HoaDonHdr",
            "dest": "brvsx_hoadonhdr",
            "filter": ROLLING_WINDOW_DOCDATE,
            "purge": f'DELETE FROM brvsx_hoadonhdr WHERE "DocDate"::date < {PG_WINDOW_START}'
        },
        {
            "src": "dbo.BRVSX_HoaDonCt",
            "dest": "brvsx_hoadonct",
            "filter": f"Stt IN (SELECT Stt FROM dbo.BRVSX_HoaDonHdr WHERE {ROLLING_WINDOW_DOCDATE})",
            "purge": 'DELETE FROM brvsx_hoadonct WHERE "Stt" NOT IN (SELECT "Stt" FROM brvsx_hoadonhdr)'
        },
        {
            "src": "dbo.BRVSX_TraLai",
            "dest": "brvsx_tralai",
            "filter": ROLLING_WINDOW_DOCDATE,
            "purge": f'DELETE FROM brvsx_tralai WHERE "DocDate"::date < {PG_WINDOW_START}'
        },

        # --- Thêm 08/07/2026: chỉ tiêu vùng/ETC + KPI chi tiết theo khách hàng ---
        {
            "src": "dbo.DIM_TargetVungMien",
            "dest": "dim_targetvungmien",
            "filter": ROLLING_WINDOW_DOCDATE,
            "purge": f'DELETE FROM dim_targetvungmien WHERE "DocDate"::date < {PG_WINDOW_START}'
        },
        {
            "src": "dbo.FACT_KeHoachTongETC",
            "dest": "fact_kehoachtongetc",
            "filter": ROLLING_WINDOW_DOCDATE,
            "purge": f'DELETE FROM fact_kehoachtongetc WHERE "DocDate"::date < {PG_WINDOW_START}'
        },
        {
            "src": "dbo.FACT_TongHopKhachHang",
            "dest": "fact_tonghopkhachhang",
            "filter": ROLLING_WINDOW_SAVEDATE,
            "purge": f'DELETE FROM fact_tonghopkhachhang WHERE "SaveDate"::date < {PG_WINDOW_START}'
        }
    ]

    for item in sync_config:
        src_table = item["src"]
        dest_table = item["dest"]
        filter_cond = item["filter"]
        
        print(f"\n[*] Đang xử lý bảng '{src_table}' -> '{dest_table}'...")
        run_started_at = datetime.now()
        rows_purged = None

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

            # 5. Dọn dữ liệu NGOÀI cửa sổ trượt đã có sẵn trên Supabase (nếu bảng này có khai báo
            # "purge") — chỉ đổi filter đọc ở trên không tự xoá dữ liệu cũ đã tồn tại từ trước.
            purge_sql = item.get("purge")
            if purge_sql:
                with pg_engine.begin() as pg_conn:
                    result = pg_conn.execute(text(purge_sql))
                rows_purged = result.rowcount
                print(f"  -> Đã dọn {result.rowcount:,} dòng ngoài cửa sổ trượt khỏi '{dest_table}'.")

            log_sync_run(pg_engine, dest_table, run_started_at, "success", rows_synced=len(df_cleaned), rows_purged=rows_purged)

        except Exception as e:
            # SQLAlchemy tự in kèm CẢ câu SQL lẫn TOÀN BỘ tham số bind khi lỗi xảy ra trên câu
            # upsert hàng loạt (vd 2000 dòng/chunk) -> str(e) có thể dài hàng chục nghìn ký tự,
            # tràn terminal, không dán lại được để debug. Cắt ngắn, chỉ giữ phần đầu đủ để biết
            # loại lỗi (vd OperationalError/timeout) — xác nhận thực tế 13/07/2026.
            err_text = str(e)
            if len(err_text) > 500:
                err_text = err_text[:500] + f"... (cắt bớt, dài {len(err_text)} ký tự)"
            print(f"  -> [THẤT BẠI] Lỗi khi xử lý bảng '{dest_table}': {err_text}")
            log_sync_run(pg_engine, dest_table, run_started_at, "failed", error_message=err_text)

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
    sync_inventory_from_bravo()
    run_alert_checks_after_sync()
