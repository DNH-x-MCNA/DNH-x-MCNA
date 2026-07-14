import os
import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Load .env file
load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')

# ---- Failover Supabase (Postgres) -> Bravo SQL Server (T-SQL) --------------
# Dùng cho các query đọc bảng hóa đơn/khách hàng/nhân viên có mặt ở CẢ HAI nguồn
# (brv_*/brvsx_*/dms_*/dim_* — đã sync bởi scripts/sync_from_bravo_to_supabase.py). KHÔNG áp
# dụng cho receivable_detail/kpi_summary/inventory — 3 bảng này KHÔNG tồn tại trên Bravo, không
# có đường fallback.

_bravo_engine = None
_fast_cloud_engine = None
_fast_cloud_engine_url = None
_bravo_down_until = None  # time.monotonic() mốc hết "circuit breaker" — None = chưa ghi nhận lỗi
_CIRCUIT_BREAKER_SECONDS = 120  # trong 1 lần build report/alert (thường vài chục giây), 1 lần lỗi
                                 # là đủ tín hiệu — 120s đủ dài để không thử lại Bravo vô ích
                                 # nhiều lần trong CÙNG 1 lần chạy, nhưng đủ ngắn để lần chạy SAU
                                 # (vài chục phút sau) tự thử lại Bravo.


def _get_bravo_engine():
    """
    Engine SQLAlchemy kết nối trực tiếp Bravo SQL Server (172.16.0.26) — đọc credentials từ
    BRAVO_SQL_SERVER/DATABASE/UID/PWD trong .env (đúng biến scripts/sync_from_bravo_to_supabase.py
    đang dùng ổn định 5 lần/ngày). driver="SQL Server" vì máy chỉ cài driver ODBC cũ này (không có
    "ODBC Driver 17"), xác nhận qua pyodbc.drivers(). Chỉ dùng cho query đọc dữ liệu hóa đơn/khách
    hàng/nhân viên — KHÔNG dùng cho công nợ/tồn kho/KPI (không tồn tại trên Bravo).
    """
    global _bravo_engine
    if _bravo_engine is not None:
        return _bravo_engine
    server = os.getenv("BRAVO_SQL_SERVER")
    database = os.getenv("BRAVO_SQL_DATABASE")
    uid = os.getenv("BRAVO_SQL_UID")
    pwd = os.getenv("BRAVO_SQL_PWD")
    if not all([server, database, uid, pwd]):
        print("[DB][bravo] Thiếu BRAVO_SQL_SERVER/DATABASE/UID/PWD trong .env — không tạo được engine Bravo.")
        return None
    from sqlalchemy.engine import URL
    url = URL.create(
        "mssql+pyodbc",
        username=uid, password=pwd,
        host=server, database=database,
        query={"driver": "SQL Server", "TrustServerCertificate": "yes"},
    )
    try:
        # 14/07/2026: thêm pool_pre_ping=True — từ khi nhiều hàm doanh thu/công nợ đổi sang gọi
        # thẳng Bravo (bỏ failover Postgres, xem docstring _period_revenue trong src/etl.py), số
        # lượng query Bravo mỗi chu kỳ quét tăng đáng kể, gặp thực tế lỗi "Communication link
        # failure" (kết nối cũ trong pool đã bị rớt do timeout mạng/server, SQLAlchemy vẫn đưa ra
        # dùng lại mà không kiểm tra trước). pool_pre_ping tự ping nhẹ trước khi dùng 1 connection
        # lấy từ pool, tự âm thầm mở lại nếu đã chết — Postgres engine (_get_fast_cloud_engine)
        # đã có sẵn tuỳ chọn này, Bravo engine trước đó thiếu.
        #
        # pool_recycle=240: nhiều firewall/thiết bị mạng nội bộ tự ngắt kết nối TCP nhàn rỗi sau
        # ~5 phút — chủ động "làm mới" connection sau 240s (dù đang idle, chưa kịp bị ngắt) thay vì
        # chờ pool_pre_ping phát hiện đã chết rồi mới mở lại. Kết hợp cả 2 giảm khả năng dính lỗi
        # kết nối khi 1 chu kỳ quét chạy nhiều query rải rác qua thời gian (vd chờ Teams/email gửi
        # xong giữa các alert).
        _bravo_engine = create_engine(url, connect_args={"timeout": 10}, pool_pre_ping=True, pool_recycle=240)
    except Exception as e:
        print(f"[DB][bravo] Không tạo được engine Bravo: {e}")
        return None
    return _bravo_engine


def _get_fast_cloud_engine():
    """
    Engine Postgres RIÊNG (không dùng chung cache với _get_cloud_engine() ở dưới — tránh đổi hành
    vi timeout của pool đang phục vụ chatbot sống) trỏ cùng CLOUD_DB_URL nhưng có
    connect_timeout=5s + statement_timeout=15s (qua psycopg2 "options") — để khi Supabase hết IO
    budget/nghẽn thì BAIL SỚM (15s) thay vì đợi Supabase tự huỷ statement sau 90-150s+ như quan sát
    thực tế 09/07/2026, rồi mới chuyển sang Bravo qua run_with_failover().
    """
    global _fast_cloud_engine, _fast_cloud_engine_url
    cloud_db_url = os.getenv("CLOUD_DB_URL", "")
    if not cloud_db_url:
        return None
    db_url = cloud_db_url.strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if _fast_cloud_engine is not None and _fast_cloud_engine_url == db_url:
        return _fast_cloud_engine
    _fast_cloud_engine = create_engine(
        db_url,
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"},
    )
    _fast_cloud_engine_url = db_url
    return _fast_cloud_engine


_cloud_engine = None
_cloud_engine_url = None


def _get_cloud_engine():
    """
    Engine Postgres của CHATBOT (ai_agent/chatbot.py) — tách riêng khỏi _get_fast_cloud_engine() ở
    trên dù cùng trỏ CLOUD_DB_URL, để KHÔNG dùng chung cache/pool: chatbot cần connect_timeout dài
    hơn (10s, đo thật handshake tới pooler mất ~2.3-2.9s ngay cả khi rảnh) và pool_size lớn hơn
    (nhiều người chat đồng thời) so với engine "fast" phục vụ report/alert (bail sớm 5s, pool nhỏ).

    14/07/2026: chuyển hẳn định nghĩa từ ai_agent/chatbot.py sang đây — service báo cáo/cảnh báo
    (src/alerts.py, src/analytics.py) trước đó import thẳng hàm này từ file chatbot, khiến service
    phụ thuộc runtime vào 1 file thuộc phần chatbot. chatbot.py giờ import ngược lại từ đây, hành vi
    (pool_size/pool_recycle/connect_timeout) giữ nguyên không đổi.
    """
    global _cloud_engine, _cloud_engine_url
    cloud_db_url = os.getenv("CLOUD_DB_URL", "")
    if not cloud_db_url:
        return None

    db_url = cloud_db_url.strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    if _cloud_engine is not None and _cloud_engine_url == db_url:
        return _cloud_engine

    _cloud_engine = create_engine(
        db_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={'connect_timeout': 10},
    )
    _cloud_engine_url = db_url
    return _cloud_engine


def run_with_failover(pg_fn, mssql_fn, label=""):
    """
    Thử mssql_fn(conn) trên Bravo SQL Server trực tiếp TRƯỚC (nguồn "sự thật" tức thời, đổi ưu
    tiên 10/07/2026 theo yêu cầu — trước đó ưu tiên Supabase); bất kỳ lỗi nào (mất kết nối, Bravo
    tạm không truy cập được...) -> log rõ + thử pg_fn(conn) trên Supabase (engine "fast", bail sớm
    nếu nghẽn) làm dự phòng. Trả kết quả của bên thành công (None nếu cả 2 đều không dùng được).

    pg_fn/mssql_fn: callable(conn) -> kết quả bất kỳ (row/list row/scalar...) — mỗi bên tự viết
    câu SQL đúng dialect của mình (Postgres vs T-SQL khác cú pháp: TRUE/FALSE vs 1/0, DATE_TRUNC
    vs DATEFROMPARTS, LIMIT vs TOP...).

    CHỈ dùng cho bảng có ở CẢ HAI nguồn (brv_*/brvsx_*/dms_*/dim_* — không dùng cho
    receivable_detail/kpi_summary/inventory (chỉ có trên Supabase, không có gì để fallback).

    Circuit breaker: 1 hàm digest/alert thường gọi hàm này NHIỀU LẦN liên tiếp (vd trend 7 ngày =
    7 lần) — nếu để mỗi lần đều tự thử+chờ timeout Bravo riêng thì 1 lần build report có thể mất
    vài phút khi Bravo đang không truy cập được. Sau 1 lần mssql_fn thất bại, nhớ lại "Bravo đang
    down" trong _CIRCUIT_BREAKER_SECONDS giây tới -> các lần gọi sau trong cửa sổ đó bỏ qua thẳng
    Supabase, không thử lại Bravo vô ích.
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
                _bravo_down_until = None  # thành công -> xoá trạng thái down (nếu có)
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
