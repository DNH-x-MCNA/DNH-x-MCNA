import os
import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Load .env file
load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')

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
        # Convert relative paths to absolute paths for SQLite
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
        # Production - SQL Server using credentials from .env
        prod_cfg = config['database']['production']
        
        # Read from environment variables
        db_user = os.getenv('DB_USER', 'sa')
        db_pass = os.getenv('DB_PASS', '')
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '1433')
        erp_name = os.getenv('ERP_DB_NAME', 'ERP')
        crm_name = os.getenv('CRM_DB_NAME', 'CRM')
        
        erp_conn = prod_cfg['erp_connection_string'].format(
            DB_USER=db_user, DB_PASS=db_pass, DB_HOST=db_host,
            DB_PORT=db_port, ERP_DB_NAME=erp_name
        )
        crm_conn = prod_cfg['crm_connection_string'].format(
            DB_USER=db_user, DB_PASS=db_pass, DB_HOST=db_host,
            DB_PORT=db_port, CRM_DB_NAME=crm_name
        )
        
        # SQL Server PyODBC connection setup
        erp_engine = create_engine(erp_conn)
        crm_engine = create_engine(crm_conn)
        
    return erp_engine, crm_engine

if __name__ == '__main__':
    # Test connection
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
