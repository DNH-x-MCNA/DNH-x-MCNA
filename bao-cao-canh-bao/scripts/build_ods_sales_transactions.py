# -*- coding: utf-8 -*-
"""Dựng 2 bảng mart doanh số theo tháng (`mart_sales_employee_monthly`,
`mart_sales_product_monthly`) trên Supabase — anh em với `build_mart_revenue_summary.py`.

TRẠNG THÁI (22/07/2026): **KHÔNG nằm trong luồng chạy tự động.** Từ 20/07/2026 toàn bộ pipeline
báo cáo/cảnh báo đã chuyển Bravo-first (đọc thẳng SQL Server, bỏ Supabase — xem commit
`f2cd08c`), nên 2 bảng mart này hiện KHÔNG được hàm nào đọc. Giữ lại vì:
  - Kiến trúc mart layer vẫn nằm trong kế hoạch gốc (xem skill `dnh-realtime-etl-pipeline`);
  - Từng dùng để đối chiếu mã nhân viên/bí danh DMSCode (xem `docs/data_dictionary.md`).
Chạy thủ công khi cần dựng lại mart; KHÔNG đăng ký vào scheduled task.
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

# Add system paths
PROJECT_ROOT = r"D:\DNH"
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, "src"))

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from region_map import region_from_customer_code

# Connection variables
_bravo_server = os.getenv("BRAVO_SQL_SERVER", "")
_bravo_database = os.getenv("BRAVO_SQL_DATABASE", "")
_bravo_uid = os.getenv("BRAVO_SQL_UID", "")
_bravo_pwd = os.getenv("BRAVO_SQL_PWD", "")

SQL_SERVER_CONN = (
    "DRIVER={SQL Server};"
    f"SERVER={_bravo_server};"
    f"DATABASE={_bravo_database};"
    f"UID={_bravo_uid};"
    f"PWD={_bravo_pwd};"
    "TrustServerCertificate=yes;"
)

CLOUD_DB_URL = os.getenv("CLOUD_DB_URL", "")
db_url = CLOUD_DB_URL.strip()
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

def get_sql_server_connection():
    import pyodbc
    return pyodbc.connect(SQL_SERVER_CONN)

def get_supabase_engine():
    from sqlalchemy.pool import NullPool
    return create_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 10, "options": "-c statement_timeout=120000"},
    )

DDL_SQL = """
CREATE TABLE IF NOT EXISTS mart_sales_employee_monthly (
    id              text PRIMARY KEY,             -- KenhBH_Nam_Thang_EmpCode_AreaCode
    kenh_bh         text NOT NULL,                -- 'OTC' hoặc 'ETC'
    nam             integer NOT NULL,
    thang           integer NOT NULL,
    emp_dms_code    text,                         -- Mã trình dược viên
    emp_name        text,                         -- Tên trình dược viên
    position_code   text,                         -- Chức vụ
    area_code       text,                         -- Vùng miền chuẩn ('MB', 'MT', 'MN')
    amount          numeric(20, 2),               -- Tổng doanh số trước thuế
    sync_at         timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mart_emp_time ON mart_sales_employee_monthly (nam, thang);
CREATE INDEX IF NOT EXISTS idx_mart_emp_code ON mart_sales_employee_monthly (emp_dms_code);

CREATE TABLE IF NOT EXISTS mart_sales_product_monthly (
    id              text PRIMARY KEY,             -- KenhBH_Nam_Thang_EmpCode_ItemCode_AreaCode
    kenh_bh         text NOT NULL,
    nam             integer NOT NULL,
    thang           integer NOT NULL,
    emp_dms_code    text,
    emp_name        text,
    area_code       text,
    item_code       text NOT NULL,
    item_name       text,
    unit            text,
    quantity        numeric(20, 2),               -- Tổng số lượng bán
    amount          numeric(20, 2),               -- Tổng doanh số trước thuế
    sync_at         timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mart_prod_time ON mart_sales_product_monthly (nam, thang);
CREATE INDEX IF NOT EXISTS idx_mart_prod_item ON mart_sales_product_monthly (item_code);
"""

def create_tables(pg_engine):
    print("Creating tables and indexes on Supabase...", flush=True)
    with pg_engine.begin() as conn:
        for stmt in DDL_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    print("Tables and indexes verified.", flush=True)

def clean_dataframe(df):
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
    return df

def upsert_chunk(pg_engine, table_name, df, key_columns):
    """Upsert standard dataframe chunk to Supabase using temp staging table."""
    import random
    temp_table = f"temp_{table_name}_{random.randint(10000, 99999)}"
    
    # Write to staging table
    df.to_sql(temp_table, pg_engine, if_exists='replace', index=False, method='multi')
    
    # Build ON CONFLICT query
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
        
    try:
        with pg_engine.begin() as conn:
            conn.execute(text(upsert_query))
            conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
    except Exception as ex:
        try:
            with pg_engine.begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
        except:
            pass
        raise ex

def load_lookups(sql_conn):
    print("Loading dimension lookups from Bravo...", flush=True)
    
    # 1. Product Map (OTC + ETC)
    sp_map = {}
    try:
        df_sp_otc = pd.read_sql("SELECT Code, Name, Unit FROM dbo.BRV_SanPham WITH (NOLOCK)", sql_conn)
        for _, r in df_sp_otc.iterrows():
            sp_map[r['Code']] = (r['Name'], r['Unit'])
        print(f"  Loaded {len(df_sp_otc)} OTC products.")
    except Exception as e:
        print(f"Error loading BRV_SanPham: {e}")
        
    try:
        df_sp_etc = pd.read_sql("SELECT Code, Name, Unit FROM dbo.BRVSX_SanPham WITH (NOLOCK)", sql_conn)
        for _, r in df_sp_etc.iterrows():
            sp_map[r['Code']] = (r['Name'], r['Unit'])
        print(f"  Loaded/Updated with {len(df_sp_etc)} ETC products.")
    except Exception as e:
        print(f"Error loading BRVSX_SanPham: {e}")
    
    # 2. Employee Map (DMS + DIM)
    nv_map = {}
    try:
        df_nv_dms = pd.read_sql("SELECT Code, DMSCode, Name FROM dbo.DMSSX_NhanVien WITH (NOLOCK)", sql_conn)
        for _, r in df_nv_dms.iterrows():
            if r['Code']:
                nv_map[r['Code']] = (r['Name'], 'TDV')
            if r['DMSCode']:
                nv_map[r['DMSCode']] = (r['Name'], 'TDV')
        print(f"  Loaded {len(df_nv_dms)} DMS employees.")
    except Exception as e:
        print(f"Error loading DMSSX_NhanVien: {e}")
        
    try:
        df_nv_dim = pd.read_sql("SELECT EmployeeCode, Name, PositionCode FROM dbo.DIM_NhanVien WITH (NOLOCK)", sql_conn)
        for _, r in df_nv_dim.iterrows():
            nv_map[r['EmployeeCode']] = (r['Name'], r['PositionCode'])
        print(f"  Loaded/Updated with {len(df_nv_dim)} DIM employees.")
    except Exception as e:
        print(f"Error loading DIM_NhanVien: {e}")
    
    # 3. Tỉnh thành Map
    df_tt = pd.read_sql("SELECT CityId, CityName, AreaCode FROM dbo.DIM_TinhThanhPho WITH (NOLOCK)", sql_conn)
    tt_map = {r['CityId']: (r['CityName'], r['AreaCode']) for _, r in df_tt.iterrows()}
    
    return sp_map, nv_map, tt_map

def build_and_sync():
    sql_conn = get_sql_server_connection()
    pg_engine = get_supabase_engine()
    
    create_tables(pg_engine)
    sp_map, nv_map, tt_map = load_lookups(sql_conn)
    
    # ========================================================
    # OTC Sales Query (Historical 2023 - Present)
    # ========================================================
    print("\nReading OTC Sales from Bravo...", flush=True)
    otc_sql = """
    SELECT 
        v.CustomerCode,
        v.EmpDMSCode,
        v.ItemCode,
        v.DocDate,
        v.Quantity,
        v.Amount9 AS Amount,
        k.CityId
    FROM dbo.vHoaDonTotal v WITH (NOLOCK)
    LEFT JOIN dbo.DMS_KhachHang k WITH (NOLOCK) ON v.CustomerCode = k.Code
    WHERE v.DocDate >= '2023-01-01'
    """
    df_otc = pd.read_sql(otc_sql, sql_conn)
    df_otc['KenhBH'] = 'OTC'
    print(f"Read {len(df_otc):,} OTC rows.", flush=True)

    # ========================================================
    # ETC Sales Query (Historical 2023 - Present)
    # ========================================================
    print("\nReading ETC Sales from Bravo...", flush=True)
    etc_sql = """
    SELECT 
        v.CustomerCode,
        v.EmpDMSCode,
        v.ItemCode,
        v.DocDate,
        v.Quantity,
        v.Amount9 AS Amount,
        v.CityId
    FROM dbo.vHoaDonETCTotal v WITH (NOLOCK)
    WHERE v.DocDate >= '2023-01-01'
    """
    df_etc = pd.read_sql(etc_sql, sql_conn)
    df_etc['KenhBH'] = 'ETC'
    print(f"Read {len(df_etc):,} ETC rows.", flush=True)

    # Union all transactions
    df_sales = pd.concat([df_otc, df_etc], ignore_index=True)
    del df_otc, df_etc # Free memory
    
    print("\nProcessing dates and area codes...", flush=True)
    # Extract Nam/Thang
    df_sales['DocDate'] = pd.to_datetime(df_sales['DocDate'])
    df_sales['Nam'] = df_sales['DocDate'].dt.year
    df_sales['Thang'] = df_sales['DocDate'].dt.month
    
    # Map area code using city_id, fallback to customer prefix
    def get_area_code(row):
        city_id = row['CityId']
        if pd.notna(city_id) and int(city_id) in tt_map:
            area = tt_map[int(city_id)][1]
            if area:
                return area
        # Fallback to customer code prefix
        fallback = region_from_customer_code(row['CustomerCode'])
        return fallback if fallback else None
        
    df_sales['AreaCode'] = df_sales.apply(get_area_code, axis=1)

    # Clean missing codes
    df_sales['EmpDMSCode'] = df_sales['EmpDMSCode'].fillna('N/A')
    df_sales['AreaCode'] = df_sales['AreaCode'].fillna('N/A')
    
    # --------------------------------------------------------
    # 1. BUILD & SYNC mart_sales_employee_monthly
    # --------------------------------------------------------
    print("\nBuilding mart_sales_employee_monthly...", flush=True)
    df_emp = df_sales.groupby(['KenhBH', 'Nam', 'Thang', 'EmpDMSCode', 'AreaCode'])['Amount'].sum().reset_index()
    
    # Map names & positions
    def get_emp_details(code):
        if code in nv_map:
            return nv_map[code][0], nv_map[code][1]
        return 'Unknown', None
        
    df_emp['EmpName'], df_emp['PositionCode'] = zip(*df_emp['EmpDMSCode'].apply(get_emp_details))
    
    # Generate unique ID
    df_emp['id'] = df_emp['KenhBH'] + "_" + df_emp['Nam'].astype(str) + "_" + df_emp['Thang'].astype(str) + "_" + df_emp['EmpDMSCode'] + "_" + df_emp['AreaCode']
    
    # Format cols
    df_emp = df_emp.rename(columns={
        'KenhBH': 'kenh_bh',
        'Nam': 'nam',
        'Thang': 'thang',
        'EmpDMSCode': 'emp_dms_code',
        'EmpName': 'emp_name',
        'PositionCode': 'position_code',
        'AreaCode': 'area_code',
        'Amount': 'amount'
    })
    df_emp = clean_dataframe(df_emp)
    
    print(f"Syncing {len(df_emp):,} rows of mart_sales_employee_monthly to Supabase...", flush=True)
    # Sync in batches of 1000
    chunk_size = 1000
    for i in range(0, len(df_emp), chunk_size):
        chunk = df_emp.iloc[i:i+chunk_size]
        upsert_chunk(pg_engine, 'mart_sales_employee_monthly', chunk, ['id'])
    print("Employee monthly mart sync completed.", flush=True)
    del df_emp
    
    # --------------------------------------------------------
    # 2. BUILD & SYNC mart_sales_product_monthly
    # --------------------------------------------------------
    print("\nBuilding mart_sales_product_monthly...", flush=True)
    df_prod = df_sales.groupby(['KenhBH', 'Nam', 'Thang', 'EmpDMSCode', 'AreaCode', 'ItemCode']).agg(
        quantity=('Quantity', 'sum'),
        amount=('Amount', 'sum')
    ).reset_index()
    
    # Map employee names
    df_prod['emp_name'] = df_prod['EmpDMSCode'].apply(lambda x: nv_map[x][0] if x in nv_map else 'Unknown')
    
    # Map product details
    def get_prod_details(code):
        if code in sp_map:
            return sp_map[code][0], sp_map[code][1]
        return 'Unknown Product', None
        
    df_prod['ItemName'], df_prod['Unit'] = zip(*df_prod['ItemCode'].apply(get_prod_details))
    
    # Generate unique ID
    df_prod['id'] = df_prod['KenhBH'] + "_" + df_prod['Nam'].astype(str) + "_" + df_prod['Thang'].astype(str) + "_" + df_prod['EmpDMSCode'] + "_" + df_prod['ItemCode'] + "_" + df_prod['AreaCode']
    
    # Format cols
    df_prod = df_prod.rename(columns={
        'KenhBH': 'kenh_bh',
        'Nam': 'nam',
        'Thang': 'thang',
        'EmpDMSCode': 'emp_dms_code',
        'AreaCode': 'area_code',
        'ItemCode': 'item_code',
        'ItemName': 'item_name',
        'Unit': 'unit'
    })
    df_prod = clean_dataframe(df_prod)
    
    print(f"Syncing {len(df_prod):,} rows of mart_sales_product_monthly to Supabase...", flush=True)
    # Sync in batches of 1000
    for i in range(0, len(df_prod), chunk_size):
        chunk = df_prod.iloc[i:i+chunk_size]
        upsert_chunk(pg_engine, 'mart_sales_product_monthly', chunk, ['id'])
    print("Product monthly mart sync completed.", flush=True)
    
    # ========================================================
    # 3. VERIFICATION
    # ========================================================
    print("\n" + "="*50)
    print("VERIFICATION STATS:")
    print("="*50, flush=True)
    
    # Total sum on Bravo SQL
    bravo_sum = float(df_sales['Amount'].sum() or 0.0)
    print(f"Bravo total revenue (from 2023):  {bravo_sum:,.2f} VNĐ")
    
    # Total sum on Supabase mart_sales_employee_monthly
    with pg_engine.connect() as conn:
        res = conn.execute(text("SELECT SUM(amount) FROM mart_sales_employee_monthly"))
        sup_emp_sum = float(res.fetchone()[0] or 0.0)
        
        res = conn.execute(text("SELECT SUM(amount) FROM mart_sales_product_monthly"))
        sup_prod_sum = float(res.fetchone()[0] or 0.0)
        
    print(f"Supabase employee mart sum:     {sup_emp_sum:,.2f} VNĐ (Diff: {abs(bravo_sum - sup_emp_sum):,.2f})")
    print(f"Supabase product mart sum:      {sup_prod_sum:,.2f} VNĐ (Diff: {abs(bravo_sum - sup_prod_sum):,.2f})")
    
    sql_conn.close()
    print("\nETL run completed successfully.", flush=True)

if __name__ == "__main__":
    build_and_sync()
