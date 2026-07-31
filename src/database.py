import os
import yaml
from urllib.parse import quote_plus
from sqlalchemy import create_engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')

_cloud_engine = None
_fast_cloud_engine = None
_bravo_engine = None
_bravo_down_until = None
_CIRCUIT_BREAKER_SECONDS = 300.0


def _get_cloud_engine():
    global _cloud_engine
    if _cloud_engine is not None:
        return _cloud_engine
    url = (os.getenv("CLOUD_DB_URL") or "").strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    _cloud_engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _cloud_engine


def _get_fast_cloud_engine():
    global _fast_cloud_engine
    if _fast_cloud_engine is not None:
        return _fast_cloud_engine
    url = (os.getenv("CLOUD_DB_URL") or "").strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    _fast_cloud_engine = create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 3})
    return _fast_cloud_engine


def _get_bravo_engine():
    global _bravo_engine
    if _bravo_engine is not None:
        return _bravo_engine
    server = (os.getenv("BRAVO_SQL_SERVER") or "").strip()
    database = (os.getenv("BRAVO_SQL_DATABASE") or "").strip()
    uid = (os.getenv("BRAVO_SQL_UID") or "").strip()
    pwd = (os.getenv("BRAVO_SQL_PWD") or "").strip()
    if not all([server, database, uid, pwd]):
        return None

    encoded_pwd = quote_plus(pwd)

    conn_str = (
        f"mssql+pyodbc://{uid}:{encoded_pwd}@{server}/{database}"
        f"?driver=SQL+Server&TrustServerCertificate=yes"
    )
    _bravo_engine = create_engine(
        conn_str,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=5,
        connect_args={'timeout': 10}
    )
    return _bravo_engine


def run_with_failover(label, pg_fn, mssql_fn):
    """
    Ưu tiên đọc từ Bravo SQL Server nếu có cấu hình + Bravo đang truy cập được. Nếu Bravo lỗi/down
    hoặc chưa cấu hình -> tự động fallback sang đọc từ Supabase Cloud.
    """
    global _bravo_down_until
    import time
    now = time.monotonic()
    skip_bravo = _bravo_down_until is not None and now < _bravo_down_until

    if not skip_bravo:
        bravo_engine = _get_bravo_engine()
        if bravo_engine is not None:
            try:
                with bravo_engine.connect() as conn:
                    result = mssql_fn(conn)
                _bravo_down_until = None
                return result
            except Exception as e:
                print(f"[DB][{label}] Bravo lỗi/không truy cập được ({e}) — chuyển sang Supabase dự phòng.")
                _bravo_down_until = now + _CIRCUIT_BREAKER_SECONDS
        else:
            print(f"[DB][{label}] Chưa cấu hình BRAVO_SQL_* — thử thẳng Supabase.")
    else:
        print(f"[DB][{label}] Bravo mới báo lỗi gần đây — bỏ qua, dùng thẳng Supabase (tự thử lại Bravo sau {_CIRCUIT_BREAKER_SECONDS}s).")

    engine = _get_fast_cloud_engine()
    if engine is None:
        print(f"[DB][{label}] Không có Supabase engine để fallback — bỏ qua.")
        return None
    with engine.connect() as conn:
        return pg_fn(conn)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_db_engines():
    config = load_config()
    env = config.get('environment', 'local').lower()
    
    if env == 'local':
        local_cfg = config['database']['local']
        erp_conn = local_cfg['erp_connection_string']
        crm_conn = local_cfg['crm_connection_string']
        
        if erp_conn.startswith("sqlite:///"):
            rel_path = erp_conn.replace("sqlite:///", "")
            abs_path = os.path.join(PROJECT_ROOT, rel_path)
            erp_conn = f"sqlite:///{abs_path.replace(os.sep, '/')}"
            
        if crm_conn.startswith("sqlite:///"):
            rel_path = crm_conn.replace("sqlite:///", "")
            abs_path = os.path.join(PROJECT_ROOT, rel_path)
            crm_conn = f"sqlite:///{abs_path.replace(os.sep, '/')}"
            
        erp_engine = create_engine(erp_conn)
        crm_engine = create_engine(crm_conn)
    else:
        prod_cfg = config['database']['production']
        
        db_user = os.getenv('DB_USER', 'sa')
        db_pass = os.getenv('DB_PASS', '')
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '1433')
        erp_name = os.getenv('ERP_DB_NAME', 'ERP')
        crm_name = os.getenv('CRM_DB_NAME', 'CRM')

        encoded_pass = quote_plus(db_pass)
        
        erp_conn = prod_cfg['erp_connection_string'].format(
            DB_USER=db_user, DB_PASS=encoded_pass, DB_HOST=db_host,
            DB_PORT=db_port, ERP_DB_NAME=erp_name
        )
        crm_conn = prod_cfg['crm_connection_string'].format(
            DB_USER=db_user, DB_PASS=encoded_pass, DB_HOST=db_host,
            DB_PORT=db_port, CRM_DB_NAME=crm_name
        )
        
        erp_engine = create_engine(erp_conn)
        crm_engine = create_engine(crm_conn)
        
    return erp_engine, crm_engine


if __name__ == '__main__':
    try:
        erp_eng, crm_eng = get_db_engines()
        print("ERP Engine:", erp_eng)
        print("CRM Engine:", crm_eng)
        
        with erp_eng.connect() as conn:
            print("ERP connection test successful.")
        with crm_eng.connect() as conn:
            print("CRM connection test successful.")
    except Exception as e:
        print("Connection test failed:", e)
