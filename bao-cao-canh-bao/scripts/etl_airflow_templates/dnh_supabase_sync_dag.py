from datetime import datetime, timedelta
import os
import sys
from airflow import DAG
from airflow.operators.python import PythonOperator

# Thêm thư mục gốc dự án D:\DNH vào PATH để Airflow có thể import các module
PROJECT_ROOT = r"D:\DNH"
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Import hàm sync đã viết sẵn từ scripts.sync_to_supabase
from scripts.sync_to_supabase import sync

default_args = {
    'owner': 'dnh_data_team',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': True,
    'email': ['alerts-dwh@namhapharma.com'],
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'dnh_supabase_sync_pipeline',
    default_args=default_args,
    description='Đồng bộ hóa dữ liệu DWH từ máy chủ vật lý lên Supabase Cloud',
    schedule_interval=timedelta(hours=1),  # Chạy tự động mỗi giờ một lần (hoặc tùy chỉnh)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['dnh', 'supabase', 'dwh'],
) as dag:

    # Task thực thi hàm đồng bộ lên Supabase Postgres
    sync_to_supabase_task = PythonOperator(
        task_id='sync_to_supabase',
        python_callable=sync,
    )

    sync_to_supabase_task
