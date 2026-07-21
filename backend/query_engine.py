# -*- coding: utf-8 -*-
"""Query Engine: validate + thuc thi SQL an toan (chi SELECT) tren "local" (SQLite, mac dinh),
Bravo (SQL Server song), hoac Supabase.

"local" la kho SQLite dong bo dinh ky tu Bravo (xem sync_warehouse.py) - nhanh (<=10s), co day du
lich su nhieu nam, dung cho HAU HET cau hoi (ca 5 tool bao cao chuan lan cau hoi tu do). Bravo song
CHI con duoc cham toi boi job dong bo nen (KHONG boi chatbot truc tiep nua) - tru truong hop can so
lieu "ngay tuc thi" chua kip dong bo. Supabase CHI dung cho inventory/receivable_* (bang cua dong
nghiep tu nhap, khong co tren Bravo).
"""
import os, re, ssl, time, json, datetime as dt, decimal, urllib.parse
from sqlalchemy import create_engine, text


def _jsonable(v):
    """Convert cac kieu Python khong tu JSON-serialize duoc (date, datetime, Decimal) sang str/float."""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "audit_log.jsonl")
MAX_ROWS = 200
STATEMENT_TIMEOUT_SEC = 30

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|COPY|CALL|EXECUTE|MERGE|VACUUM|"
    r"pg_sleep|pg_terminate_backend|pg_read_file)\b",
    re.IGNORECASE,
)

_engines = {}


def _get_engine(db: str = "local"):
    if db not in _engines:
        if db == "local":
            from local_warehouse import DB_PATH
            _engines[db] = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
        elif db == "bravo":
            import pyodbc
            sd = [d for d in pyodbc.drivers() if "SQL Server" in d]
            if "ODBC Driver 18 for SQL Server" in sd:
                drv = "ODBC Driver 18 for SQL Server"
            elif "ODBC Driver 17 for SQL Server" in sd:
                drv = "ODBC Driver 17 for SQL Server"
            else:
                drv = "SQL Server"
            server = os.environ["BRAVO_SERVER"]; port = os.environ.get("BRAVO_PORT", "1433")
            dbname = os.environ["BRAVO_DATABASE"]; user = os.environ["BRAVO_USER"]; pwd = os.environ["BRAVO_PASSWORD"]
            # Connection Timeout ngan (15s) - mac dinh driver co the treo RAT LAU (vai phut) neu VPN
            # chua san sang (vd ngay sau khi may vua khoi dong) thay vi bao loi nhanh de retry som.
            s = f"DRIVER={{{drv}}};SERVER={server},{port};DATABASE={dbname};UID={user};PWD={pwd};Connection Timeout=15;"
            if drv == "ODBC Driver 18 for SQL Server":
                s += "TrustServerCertificate=yes;"
            _engines[db] = create_engine("mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(s), pool_pre_ping=True)
        elif db == "supabase":
            pwd = os.environ["SUPABASE_DB_PASSWORD"]; ref = os.environ["SUPABASE_REF"]; host = os.environ["SUPABASE_HOST"]
            url = f"postgresql+pg8000://postgres.{ref}:{urllib.parse.quote_plus(pwd)}@{host}:5432/postgres"
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            _engines[db] = create_engine(url, connect_args={"ssl_context": ctx}, pool_pre_ping=True)
        else:
            raise ValueError(f"db khong hop le: {db}")
    return _engines[db]


class SqlRejected(Exception):
    pass


def validate_sql(sql: str, db: str = "local") -> str:
    """Kiem tra SQL an toan: chi 1 cau SELECT/WITH, khong co tu khoa ghi/sua/xoa."""
    s = sql.strip().rstrip(";")
    if ";" in s:
        raise SqlRejected("Chi cho phep 1 cau lenh duy nhat (khong duoc co dau ';' o giua).")
    if not re.match(r"^\s*(SELECT|WITH)\b", s, re.IGNORECASE):
        raise SqlRejected("Chi cho phep cau lenh SELECT (hoac WITH ... SELECT).")
    if _FORBIDDEN.search(s):
        raise SqlRejected("SQL chua tu khoa khong duoc phep (chi cho phep doc du lieu).")
    if db in ("supabase", "local") and not re.search(r"\bLIMIT\s+\d+\b", s, re.IGNORECASE):
        s = f"{s}\nLIMIT {MAX_ROWS}"
    # db == "bravo" (T-SQL): khong tu dong them TOP N (cu phap SELECT...LIMIT khong hop le voi SQL Server,
    # AI tu dung TOP N neu can) - fetchmany(MAX_ROWS) ben duoi van dam bao gioi han so dong tra ve.
    return s


def run_query(sql: str, question: str = "", db: str = "local", username: str = None) -> dict:
    """Validate, thuc thi SQL (chi doc), ghi audit log, tra ve {columns, rows, row_count, duration_ms} hoac loi."""
    t0 = time.time()
    entry = {"ts": dt.datetime.now().isoformat(), "username": username, "question": question, "sql": sql, "db": db}
    try:
        safe_sql = validate_sql(sql, db)
        eng = _get_engine(db)
        with eng.connect() as conn:
            if db == "supabase":
                conn.execute(text(f"SET statement_timeout = {STATEMENT_TIMEOUT_SEC * 1000}"))
            result = conn.execute(text(safe_sql))
            cols = list(result.keys())
            rows = [[_jsonable(v) for v in r] for r in result.fetchmany(MAX_ROWS)]
        duration_ms = int((time.time() - t0) * 1000)
        entry["status"] = "ok"; entry["row_count"] = len(rows); entry["duration_ms"] = duration_ms
        _write_log(entry)
        return {"ok": True, "columns": cols, "rows": rows, "row_count": len(rows), "duration_ms": duration_ms}
    except SqlRejected as e:
        entry["status"] = "rejected"; entry["error"] = str(e)
        _write_log(entry)
        return {"ok": False, "error": f"SQL bi tu choi: {e}"}
    except Exception as e:
        entry["status"] = "error"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": f"Loi khi truy van: {str(e)[:300]}"}


def _write_log(entry: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
