"""
Apache Airflow DAG - ETL Pipeline for Duoc Nam Ha (DNH)
Data Source: ERP Bravo / DMS CRM
Data Warehouse: Microsoft SQL Server (dnh_core)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import pandas as pd
import pyodbc

default_args = {
    'owner': 'dnh_data_team',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': True,
    'email': ['alerts-dwh@namhapharma.com'],
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

def get_sql_server_connection():
    """
    Tra ve ket noi pyodbc den co so du lieu SQL Server DWH cua DNH.
    Doi voi moi truong san xuat cua DNH, can truyen dung Driver, Server IP va Password.
    """
    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=192.168.1.100;"  # IP Server cua DNH
        "Database=dnh_dwh;"
        "UID=dnh_etl_user;"
        "PWD=ETL_Secure_Password_2026;"
    )
    return pyodbc.connect(conn_str)

def extract_and_validate_receivables():
    """
    Extract: Lay du lieu tu he thong Bravo ERP va DMS.
    Data Quality Validation: Check va clean du lieu truoc khi nap vao staging.
    """
    # Gia dinh doc tu share folder chua file CSV Bravo export hang ngay
    # Hoac truy van truc tiep qua Linked Server bang odbc
    file_path = "/mnt/bravo_shares/receivables_latest.csv"
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"[ERROR] Khong tim thay file nguon tai {file_path}. Dung Job ETL.")
        raise
        
    validation_errors = []
    
    # 1. Validation rule: Ma khach hang (customer_code) khong duoc phep rong
    null_cust = df[df['customer_code'].isna()]
    if not null_cust.empty:
        validation_errors.append(f"Phat hien {len(null_cust)} dong bi rong ma khach hang.")
        df = df.dropna(subset=['customer_code'])
        
    # 2. Validation rule: Du no cuoi ky (balance_end) khong duoc phep am
    negative_debt = df[df['balance_end'] < 0]
    if not negative_debt.empty:
        validation_errors.append(f"Phat hien {len(negative_debt)} dong co du no am. Tu dong lam tron ve 0.")
        df.loc[df['balance_end'] < 0, 'balance_end'] = 0.0
        
    # Ghi log canh bao ra Airflow Logs neu co loi ve chat luong du lieu
    if validation_errors:
        print("[DATA QUALITY WARNING] Phat hien cac loi chat luong du lieu:")
        for err in validation_errors:
            print(f" - {err}")
            
    # Tra ve du lieu sach sang dinh dang records de dung XCom truyen sang task load
    return df.to_dict(orient='records')

def load_to_sql_server(**context):
    """
    Load: Truyen du lieu sach vao staging va chay MERGE T-SQL de cap nhat vao dnh_core.
    """
    records = context['task_instance'].xcom_pull(task_ids='extract_and_validate')
    if not records:
        print("Khong co du lieu sach nao de nap vao SQL Server.")
        return
        
    conn = get_sql_server_connection()
    cursor = conn.cursor()
    
    # 1. Truncate staging table de xoa du lieu rac tu phien chay truoc
    cursor.execute("TRUNCATE TABLE dnh_staging.receivable_detail_temp;")
    
    # 2. Nap vao staging temp
    insert_query = """
    INSERT INTO dnh_staging.receivable_detail_temp 
    (period, customer_code, balance_end, in_term, overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45, total_overdue, sales_channel)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    params = [
        (r['period'], r['customer_code'], r['balance_end'], r['in_term'], 
         r['overdue_1_15'], r['overdue_15_30'], r['overdue_30_45'], r['overdue_gt_45'], 
         r['total_overdue'], r['sales_channel'])
        for r in records
    ]
    
    cursor.executemany(insert_query, params)
    
    # 3. Thuc hien T-SQL MERGE de upsert tu staging vao Core DWH
    merge_query = """
    MERGE dnh_core.receivable_detail AS target
    USING dnh_staging.receivable_detail_temp AS source
    ON (target.customer_code = source.customer_code AND target.period = source.period)
    WHEN MATCHED THEN
        UPDATE SET 
            target.balance_end = source.balance_end,
            target.in_term = source.in_term,
            target.overdue_1_15 = source.overdue_1_15,
            target.overdue_15_30 = source.overdue_15_30,
            target.overdue_30_45 = source.overdue_30_45,
            target.overdue_gt_45 = source.overdue_gt_45,
            target.total_overdue = source.total_overdue,
            target.sync_date = GETDATE()
    WHEN NOT MATCHED THEN
        INSERT (period, customer_code, balance_end, in_term, overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45, total_overdue, sales_channel)
        VALUES (source.period, source.customer_code, source.balance_end, source.in_term, source.overdue_1_15, source.overdue_15_30, source.overdue_30_45, source.overdue_gt_45, source.total_overdue, source.sales_channel);
    """
    cursor.execute(merge_query)
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"ETL Load thanh cong {len(records)} ban ghi vao dnh_core.receivable_detail.")

with DAG('dnh_daily_etl_sqlserver', default_args=default_args, schedule_interval='0 4 * * *', catchup=False) as dag:
    
    task_extract = PythonOperator(
        task_id='extract_and_validate',
        python_callable=extract_and_validate_receivables
    )
    
    task_load = PythonOperator(
        task_id='load_to_sql_server',
        python_callable=load_to_sql_server
    )
    
    task_extract >> task_load
