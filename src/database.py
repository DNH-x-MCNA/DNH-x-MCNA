import os
import yaml
from urllib.parse import quote_plus
from sqlalchemy import create_engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config.yaml')

_bravo_engine = None


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


def load_config():
    global CONFIG_PATH
    if not os.path.exists(CONFIG_PATH):
        alt_path = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')
        if os.path.exists(alt_path):
            CONFIG_PATH = alt_path
        else:
            raise FileNotFoundError(f"Config file not found at {CONFIG_PATH} or {alt_path}")
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
