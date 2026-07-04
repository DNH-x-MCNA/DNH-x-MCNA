import os
import sqlite3
import re
import anthropic
from openai import OpenAI
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "dnh_intermediate.db")

# Cached, pooled engine for the cloud Postgres DB. Built once per process and
# reused by every call site below (schema fetch, date lookups, query exec)
# instead of opening a brand new TCP/SSL connection on every single request.
_cloud_engine = None
_cloud_engine_url = None

def _get_cloud_engine():
    global _cloud_engine, _cloud_engine_url
    cloud_db_url = os.getenv("CLOUD_DB_URL", "")
    if not cloud_db_url:
        return None

    db_url = cloud_db_url.strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    if _cloud_engine is not None and _cloud_engine_url == db_url:
        return _cloud_engine

    from sqlalchemy import create_engine
    _cloud_engine = create_engine(
        db_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,   # discard/replace stale pooled connections automatically
        pool_recycle=300,     # avoid Supabase/pgbouncer idle-connection kills
        connect_args={'connect_timeout': 3}
    )
    _cloud_engine_url = db_url
    return _cloud_engine

# Helper to get the database schema dynamically
def get_db_schema():
    engine = _get_cloud_engine()
    if engine is not None:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                tables_to_include = (
                    'brv_hoadonhdr', 'brv_hoadonct', 'brvsx_hoadonhdr', 'brvsx_hoadonct',
                    'brv_trangthaihoadon', 'brv_trangthaiduyet', 'dms_khachhang', 'dmssx_khachhang',
                    'dim_tinhthanhpho', 'dim_targetvungmien', 'fact_kehoachtongetc', 'fact_tonghopkhachhang',
                    'dim_nhanvien', 'brv_sanpham', 'brvsx_tralai', 'receivable_detail', 'inventory',
                    'kpi_summary'
                )
                query = text("""
                    SELECT table_name, column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name IN :tables
                    ORDER BY table_name, ordinal_position
                """)
                result = conn.execute(query, {"tables": tables_to_include})
                cols = result.fetchall()
                schema_dict = {}
                for r in cols:
                    schema_dict.setdefault(r[0], []).append(f"{r[1]} ({r[2]})")
                
                schema_text = "Dược Nam Hà central database schema:\n"
                for t, cols_str in schema_dict.items():
                    schema_text += f"- Table '{t}': Columns are {', '.join(cols_str)}\n"
                return schema_text
        except Exception as e:
            print(f"[Warning] Failed to fetch schema from Supabase: {e}. Falling back to SQLite...")
            
    if not os.path.exists(DB_PATH):
        return "Database not initialized."
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall() if t[0] not in ('sqlite_sequence',)]
    
    schema_text = ""
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        cols_str = ", ".join([f"{c[1]} ({c[2]})" for c in columns])
        schema_text += f"- Table '{table}': Columns are {cols_str}\n"
        
    conn.close()
    return schema_text

def _latest_period_key(period):
    """Sort key for receivable_detail.period ('M_YYYY' text, not zero-padded).

    String comparison alone is wrong here: '9_2025' > '1_2026' lexicographically
    (month '9' beats any month starting with '1'), so a plain SQL MAX(period)
    silently picks a stale period whenever the true latest month starts with 1.
    """
    try:
        month_str, year_str = str(period).split('_')
        return (int(year_str), int(month_str))
    except (ValueError, AttributeError):
        return (0, 0)

class DNHChatbot:
    def __init__(self):
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

        if self.anthropic_key:
            self.client = anthropic.Anthropic(api_key=self.anthropic_key)
            self.is_mock = False
            self.model_type = "claude"
            self.sql_model = "claude-opus-4-8"
            self.summary_model = "claude-opus-4-8"
            print("[Info] Running in Live Claude Mode.")
        elif self.gemini_key:
            self.client = None
            self.is_mock = False
            self.model_type = "gemini"
            self.sql_model = "gemini-3.5-flash"
            self.summary_model = "gemini-3.5-flash"
            print("[Info] Running in Live Gemini 3.5 Mode.")
        elif self.openai_key:
            self.client = OpenAI(api_key=self.openai_key)
            self.is_mock = False
            self.model_type = "openai"
            self.sql_model = "gpt-4o"
            self.summary_model = "gpt-4o-mini"
            print("[Info] Running in Live OpenAI Mode.")
        else:
            self.client = None
            self.is_mock = True
            self.model_type = "mock"
            print("[Warning] API keys check failed. Running in Offline Mock/Heuristic Mode.")

        self.dashboards = {
            "doanh_so": "https://dnh-dashboard.vercel.app/kpi",
            "cong_no": "https://dnh-dashboard.vercel.app/receivables",
            "ton_kho": "https://dnh-dashboard.vercel.app/inventory"
        }

        # Initialize cached cloud connection flags
        self._last_cloud_check = 0.0
        self._cloud_available_cached = False

        # Conversation memory: session_key -> list[{"question","answer","ts"}]
        # In-memory/per-process, bounded, self-expiring after idle timeout.
        self._conversation_histories = {}
        self._MAX_HISTORY_TURNS = 6
        self._SESSION_IDLE_TIMEOUT_SECONDS = 1200
        self._MAX_SESSIONS = 500

        # Trigger initial check
        _ = self.cloud_available

    def _get_history_block(self, session_key):
        """Builds a text block summarizing recent turns for this session, or '' if none/stale."""
        if not session_key:
            return ""
        import time as _time
        history = self._conversation_histories.get(session_key)
        if not history:
            return ""
        if _time.time() - history[-1].get("ts", 0) > self._SESSION_IDLE_TIMEOUT_SECONDS:
            del self._conversation_histories[session_key]
            return ""

        lines = [
            "LỊCH SỬ HỘI THOẠI GẦN ĐÂY (chỉ để hiểu ngữ cảnh nếu câu hỏi hiện tại ngắn/mơ hồ và ám chỉ nội dung đã hỏi trước đó; "
            "đây KHÔNG PHẢI là yêu cầu trả lời lại):"
        ]
        for turn in history:
            lines.append(f'- Người dùng đã hỏi: "{turn["question"]}"')
            lines.append(f'  Trợ lý đã trả lời: "{turn["answer"]}"')
        return "\n".join(lines) + "\n"

    def _remember_turn(self, session_key, question, answer_text):
        """Appends a Q&A turn to this session's history, trimming old turns/sessions."""
        if not session_key:
            return
        import time as _time
        if session_key not in self._conversation_histories and len(self._conversation_histories) >= self._MAX_SESSIONS:
            oldest_key = next(iter(self._conversation_histories))
            del self._conversation_histories[oldest_key]

        short_answer = re.sub(r'<[^>]+>', ' ', answer_text or "")
        short_answer = " ".join(short_answer.split())[:300]

        history = self._conversation_histories.setdefault(session_key, [])
        history.append({"question": question, "answer": short_answer, "ts": _time.time()})
        if len(history) > self._MAX_HISTORY_TURNS:
            del history[0:len(history) - self._MAX_HISTORY_TURNS]

    @property
    def cloud_available(self):
        """Dynamic cached property to check Postgres Cloud availability with a 15-second cooldown."""
        import time as _time
        now = _time.time()
        if now - self._last_cloud_check < 15:
            return self._cloud_available_cached
            
        self._last_cloud_check = now
        engine = _get_cloud_engine()
        if engine is None or self.is_mock:
            self._cloud_available_cached = False
            return False

        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM regions LIMIT 1"))
                self._cloud_available_cached = True
                return True
        except Exception as e:
            self._cloud_available_cached = False
            # Print warning on transition to False or first check
            print(f"[Warning] Postgres Cloud DB check failed: {e}. Bot will use SQLite fallback if query fails.")
            return False

    def _get_latest_dates(self):
        """Retrieves the latest invoice date, month-end date, and receivable period dynamically."""
        latest_date = "2026-06-30"
        latest_month_end = "2026-06-30"
        latest_period = "1_2026"

        engine = _get_cloud_engine()
        if engine is not None and not self.is_mock and self.cloud_available:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    # Get max DocDate
                    res1 = conn.execute(text('SELECT MAX("DocDate") FROM brv_hoadonhdr WHERE "IsActive" = TRUE'))
                    row1 = res1.fetchone()
                    if row1 and row1[0]:
                        latest_date = str(row1[0]).split(' ')[0].split('T')[0]

                    # Get max SaveDate
                    res2 = conn.execute(text('SELECT MAX("SaveDate") FROM fact_tonghopkhachhang'))
                    row2 = res2.fetchone()
                    if row2 and row2[0]:
                        latest_month_end = str(row2[0]).split(' ')[0].split('T')[0]

                    # Get max Period from receivable_detail. 'period' is TEXT 'M_YYYY'
                    # (not zero-padded), so a plain SQL MAX() sorts lexicographically and
                    # picks e.g. '9_2025' over '1_2026' (month '9' beats any month
                    # starting with '1'). Must fetch all distinct values and pick the
                    # true (year, month) max in Python instead.
                    res3 = conn.execute(text('SELECT DISTINCT period FROM receivable_detail'))
                    periods = [r[0] for r in res3.fetchall() if r[0]]
                    if periods:
                        latest_period = max(periods, key=_latest_period_key)
                return latest_date, latest_month_end, latest_period
            except Exception as e:
                print(f"[Warning] Failed to fetch max dates from cloud: {e}")

        # Try local SQLite fallback
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('SELECT MAX(DocDate) FROM brv_hoadonhdr WHERE IsActive = 1')
                r1 = cursor.fetchone()
                if r1 and r1[0]:
                    latest_date = str(r1[0]).split(' ')[0].split('T')[0]
                cursor.execute('SELECT MAX(SaveDate) FROM fact_tonghopkhachhang')
                r2 = cursor.fetchone()
                if r2 and r2[0]:
                    latest_month_end = str(r2[0]).split(' ')[0].split('T')[0]
                # Same lexicographic-vs-chronological pitfall as the cloud branch above.
                cursor.execute('SELECT DISTINCT period FROM receivable_detail')
                periods = [r[0] for r in cursor.fetchall() if r[0]]
                if periods:
                    latest_period = max(periods, key=_latest_period_key)
                conn.close()
            except Exception as e:
                print(f"[Warning] Failed to fetch max dates from SQLite: {e}")

        return latest_date, latest_month_end, latest_period

    def _call_gemini_rest(self, model, system_instruction, user_content, temperature=0.0):
        import urllib.request
        import json
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key.strip()}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": user_content}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [
                    {"text": system_instruction}
                ]
            }
            
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res = json.loads(response.read().decode('utf-8'))
            text = res['candidates'][0]['content']['parts'][0]['text']
            return text.strip()

    def _call_claude(self, model, system_instruction, user_content):
        # NOTE: claude-opus-4-8 does not accept temperature/top_p/top_k (400 if sent), so
        # unlike the Gemini/OpenAI branches, no sampling parameter is forwarded here.
        response = self.client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_instruction,
            messages=[{"role": "user", "content": user_content}],
        )
        return next((b.text for b in response.content if b.type == "text"), "").strip()

    def _call_ai(self, model, system_prompt, user_prompt, temperature=0.0):
        if self.model_type == "gemini":
            return self._call_gemini_rest(model, system_prompt, user_prompt, temperature)
        elif self.model_type == "claude":
            return self._call_claude(model, system_prompt, user_prompt)
        else:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            return resp.choices[0].message.content.strip()



    def _execute_sql(self, sql_query):
        """Executes SQL query safely on the intermediate database (Postgres Cloud or SQLite Local)."""
        # Basic SQL safety check (Read-only check)
        lower_sql = sql_query.lower().strip()
        forbidden_keywords = ['drop', 'delete', 'update', 'insert', 'alter', 'truncate', 'create', 'replace', 'xp_cmdshell', 'exec']
        for keyword in forbidden_keywords:
            if re.search(r'\b' + keyword + r'\b', lower_sql):
                return {"error": f"Bao mat: Cau lenh chua tu khoa khong cho phep '{keyword}'"}

        # 1. Enforce SELECT/WITH whitelist
        # Strip comments/whitespace to find the first word
        clean_sql = re.sub(r'--.*$', '', sql_query, flags=re.MULTILINE)
        clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
        first_word_match = re.match(r'^\s*([a-zA-Z]+)', clean_sql)
        if not first_word_match:
            return {"error": "Bao mat: Cau lenh SQL khong hop le."}
        first_word = first_word_match.group(1).upper()
        if first_word not in ['SELECT', 'WITH']:
            return {"error": f"Bao mat: Chi cho phep truy van SELECT hoac WITH. Tu khoa bat dau: '{first_word}'"}

        # 2. Block ';' if it is not the very last non-whitespace character (prevent multi-statement)
        stripped_sql = sql_query.strip()
        if ';' in stripped_sql:
            if stripped_sql.find(';') != len(stripped_sql) - 1:
                return {"error": "Bao mat: Phat hien multi-statement query (;)."}

        # 3. Block comment injection (only allow '-- NOTE:' case-insensitive at start of line)
        if '--' in sql_query:
            for line in sql_query.split('\n'):
                if '--' in line:
                    if not line.strip().upper().startswith('-- NOTE:'):
                        return {"error": "Bao mat: Phat hien SQL comment injection."}
        if '/*' in sql_query or '*/' in sql_query:
            return {"error": "Bao mat: Phat hien SQL block comment injection."}

        engine = _get_cloud_engine()
        postgres_error = None
        if engine is not None and not self.is_mock and self.cloud_available:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    result = conn.execute(text(sql_query))
                    if result.returns_rows:
                        columns = list(result.keys())
                        formatted_rows = [dict(row._mapping) for row in result.fetchall()]
                        return {
                            "columns": columns,
                            "rows": formatted_rows,
                            "count": len(formatted_rows)
                        }
                    else:
                        return {"columns": [], "rows": [], "count": 0}
            except Exception as e:
                postgres_error = str(e)
                print(f"[Warning] Resilient Chatbot: Postgres Cloud query failed ({postgres_error}). Falling back to SQLite...")

        # Fallback to local SQLite intermediate database
        if not os.path.exists(DB_PATH):
            err_msg = "Intermediate database file not found."
            if postgres_error:
                err_msg += f" (Postgres Cloud Error: {postgres_error})"
            return {"error": err_msg}
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            if not rows:
                return {"columns": [], "rows": [], "count": 0}
            columns = list(rows[0].keys())
            formatted_rows = [dict(row) for row in rows]
            conn.close()
            return {
                "columns": columns,
                "rows": formatted_rows,
                "count": len(formatted_rows)
            }
        except Exception as e:
            err_msg = f"Loi thuc thi SQLite: {str(e)}"
            if postgres_error:
                err_msg += f" (Postgres Cloud Error: {postgres_error})"
            return {"error": err_msg, "query": sql_query}

    def _generate_mock_sql(self, query):
        """Offline heuristic SQL generator for typical demo queries based on real tables."""
        # Chuyen chu tieng Viet thanh khong dau de match tu khoa offline
        def strip_accents(s):
            accents_map = {
                'a': 'áàảãạăắằẳẵặâấầẩẫậ',
                'A': 'ÁÀẢÃẠĂẮẰClarẴẶÂẤẦẨẪẬ',
                'd': 'đ', 'D': 'Đ',
                'e': 'éèẻẽẹêếềểễệ', 'E': 'ÉÈẺẼẸÊẾỀỂỄỆ',
                'i': 'íìỉĩị', 'I': 'ÍÌỈĨỊ',
                'o': 'óòỏõọôốồổỗộơớờởỡợ', 'O': 'ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ',
                'u': 'úùủũụưứừửữự', 'U': 'ÚÙỦŨỤƯỨỪỬỮỰ',
                'y': 'ýỳỷỹỵ', 'Y': 'ÝỲỶỸỴ'
            }
            res = s
            for r, chars in accents_map.items():
                for c in chars:
                    res = res.replace(c, r)
            return res

        query_lower = strip_accents(query.lower())
        
        # 1. Tỷ lệ phần trăm doanh số kênh OTC/ETC (truy vấn bảng orders)
        if ("otc" in query_lower or "etc" in query_lower) and ("doanh thu" in query_lower or "doanh so" in query_lower) and ("chiem" in query_lower or "ty le" in query_lower or "phan tram" in query_lower or "%" in query_lower):
            if "otc" in query_lower:
                return "SELECT SUM(CASE WHEN segment = 'OTC' THEN total_amount ELSE 0 END) as otc_amount, SUM(total_amount) as total_amount, (SUM(CASE WHEN segment = 'OTC' THEN total_amount ELSE 0 END) * 100.0 / SUM(total_amount)) as otc_percent FROM orders;"
            else:
                return "SELECT SUM(CASE WHEN segment = 'ETC' THEN total_amount ELSE 0 END) as etc_amount, SUM(total_amount) as total_amount, (SUM(CASE WHEN segment = 'ETC' THEN total_amount ELSE 0 END) * 100.0 / SUM(total_amount)) as etc_percent FROM orders;"
        
        # 2. Doanh thu/Doanh số theo kênh OTC/ETC (truy vấn bảng orders)
        if "otc" in query_lower and ("doanh thu" in query_lower or "doanh so" in query_lower):
            return "SELECT SUM(total_amount) as otc_amount FROM orders WHERE segment = 'OTC';"
        elif "etc" in query_lower and ("doanh thu" in query_lower or "doanh so" in query_lower):
            return "SELECT SUM(total_amount) as etc_amount FROM orders WHERE segment = 'ETC';"

        # 3. Doanh thu theo vung mien / nhan vien (dung kpi_summary)
        if "doanh thu" in query_lower or "doanh so" in query_lower or "kpi" in query_lower:
            if "mien bac" in query_lower:
                return "SELECT 'Mien Bac' as region, SUM(month_sale_amount) as total_sale, SUM(month_sale_target) as total_target, (SUM(month_sale_amount)*100.0/SUM(month_sale_target)) as kpi_pct FROM kpi_summary WHERE area_code IN ('MB', 'MB2')"
            elif "mien nam" in query_lower:
                return "SELECT 'Mien Nam' as region, SUM(month_sale_amount) as total_sale, SUM(month_sale_target) as total_target, (SUM(month_sale_amount)*100.0/SUM(month_sale_target)) as kpi_pct FROM kpi_summary WHERE area_code = 'MN'"
            elif "mien trung" in query_lower:
                return "SELECT 'Mien Trung' as region, SUM(month_sale_amount) as total_sale, SUM(month_sale_target) as total_target, (SUM(month_sale_amount)*100.0/SUM(month_sale_target)) as kpi_pct FROM kpi_summary WHERE area_code = 'MT'"
            elif "do thi thuy" in query_lower or "thuy" in query_lower:
                return "SELECT employee_name, position_code, month_sale_target, month_sale_amount, (month_sale_percent*100) as kpi_pct, total_point FROM kpi_summary WHERE employee_name LIKE '%Thuy%'"
            elif "chua dat" in query_lower or "thap" in query_lower or "kem" in query_lower:
                return "SELECT employee_name, month_sale_target, month_sale_amount, month_sale_percent FROM kpi_summary WHERE month_sale_amount < month_sale_target ORDER BY month_sale_percent ASC LIMIT 5"
            elif "dat" in query_lower:
                return "SELECT employee_name, month_sale_target, month_sale_amount, month_sale_percent FROM kpi_summary WHERE month_sale_amount >= month_sale_target ORDER BY month_sale_percent DESC LIMIT 5"
            else:
                return "SELECT employee_name, month_sale_target, month_sale_amount, month_sale_percent FROM kpi_summary ORDER BY month_sale_amount DESC LIMIT 5"
        
        # 4. Khach hang qua han cong no / phai thu
        if "qua han" in query_lower or "cong no" in query_lower or "no" in query_lower or "phai thu" in query_lower:
            if "otc" in query_lower or "ban le" in query_lower:
                return "SELECT customer_name, balance_end, total_overdue, sales_channel FROM receivable_detail WHERE total_overdue > 0 AND sales_channel = 'OTC' ORDER BY total_overdue DESC LIMIT 5"
            elif "etc" in query_lower or "thau" in query_lower or "benh vien" in query_lower:
                return "SELECT customer_name, contract_value, total_paid, total_receivable, total_overdue FROM receivable_etc WHERE total_overdue > 0 ORDER BY total_overdue DESC LIMIT 5"
            else:
                return "SELECT customer_name, balance_end, total_overdue, sales_channel FROM receivable_detail WHERE total_overdue > 0 ORDER BY total_overdue DESC LIMIT 5"

        # 5. Ton kho
        if "ton kho" in query_lower or "ton" in query_lower or "kho" in query_lower:
            if "bo phe" in query_lower or "siro" in query_lower:
                return "SELECT item_code, item_name, unit, closing_qty, closing_value, months_to_sell FROM inventory WHERE item_name LIKE '%bo phe%' OR item_name LIKE '%siro%' ORDER BY closing_qty DESC"
            elif "can date" in query_lower or "ban cham" in query_lower:
                return "SELECT item_code, item_name, unit, closing_qty, closing_value, months_to_sell FROM inventory WHERE months_to_sell >= 6 ORDER BY months_to_sell DESC LIMIT 5"
            elif "thieu hang" in query_lower or "shortage" in query_lower:
                return "SELECT item_code, item_name, unit, closing_qty, closing_value, months_to_sell FROM inventory WHERE months_to_sell <= 1 ORDER BY months_to_sell ASC LIMIT 5"
            else:
                return "SELECT item_code, item_name, unit, closing_qty, closing_value, months_to_sell FROM inventory ORDER BY closing_qty DESC LIMIT 5"

        # Default fallback
        return "SELECT employee_name, month_sale_target, month_sale_amount FROM kpi_summary ORDER BY month_sale_amount DESC LIMIT 5"

    def _get_database_summary(self):
        """Thu thập tóm tắt số liệu từ database để làm ngữ cảnh phân tích cho câu hỏi Why/How"""
        if not os.path.exists(DB_PATH):
            return "Không có dữ liệu hệ thống."
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            summary_parts = []
            
            # 1. Tóm tắt công nợ (receivable_detail)
            try:
                cursor.execute("SELECT SUM(balance_end) as total, SUM(total_overdue) as overdue FROM receivable_detail")
                rec_row = cursor.fetchone()
                total_rec = rec_row['total'] or 0
                overdue_rec = rec_row['overdue'] or 0
                summary_parts.append(f"- Tổng công nợ hiện tại: {total_rec:,.0f} VND (Trong đó nợ quá hạn: {overdue_rec:,.0f} VND).")
                
                cursor.execute("SELECT customer_name, total_overdue FROM receivable_detail WHERE total_overdue > 0 ORDER BY total_overdue DESC LIMIT 3")
                top_debtors = ", ".join([f"{r['customer_name']} ({r['total_overdue']:,.0f} VND)" for r in cursor.fetchall()])
                if top_debtors:
                    summary_parts.append(f"- Top 3 khách hàng nợ quá hạn cao nhất: {top_debtors}.")
            except Exception as e:
                pass
                
            # 2. Tóm tắt tồn kho (inventory)
            try:
                cursor.execute("SELECT COUNT(*) as cnt, SUM(closing_value) as val FROM inventory")
                inv_row = cursor.fetchone()
                inv_count = inv_row['cnt'] or 0
                inv_val = inv_row['val'] or 0
                summary_parts.append(f"- Tổng số mặt hàng tồn kho: {inv_count} mặt hàng (Tổng giá trị tồn: {inv_val:,.0f} VND).")
                
                cursor.execute("SELECT item_name, closing_qty, months_to_sell FROM inventory WHERE months_to_sell <= 1 ORDER BY closing_qty ASC LIMIT 3")
                shortage_items = ", ".join([f"{r['item_name']} (Tồn {r['closing_qty']}sp, dự kiến bán hết trong {r['months_to_sell']} tháng)" for r in cursor.fetchall()])
                if shortage_items:
                    summary_parts.append(f"- Các sản phẩm đang thiếu hàng trầm trọng (dưới 1 tháng bán): {shortage_items}.")
            except Exception as e:
                pass
                
            # 3. Tóm tắt hiệu suất KPI nhân viên (kpi_summary)
            try:
                cursor.execute("SELECT SUM(month_sale_target) as target, SUM(month_sale_amount) as amount FROM kpi_summary")
                kpi_row = cursor.fetchone()
                target = kpi_row['target'] or 1
                amount = kpi_row['amount'] or 0
                pct = (amount / target) * 100
                summary_parts.append(f"- KPI doanh số tháng: Đạt {amount:,.0f} / {target:,.0f} VND (Tỷ lệ hoàn thành: {pct:.2f}%).")
                
                cursor.execute("SELECT employee_name, month_sale_percent FROM kpi_summary ORDER BY month_sale_percent ASC LIMIT 2")
                bottom_staff = ", ".join([f"{r['employee_name']} ({r['month_sale_percent']*100:.1f}%)" for r in cursor.fetchall()])
                if bottom_staff:
                    summary_parts.append(f"- Nhân viên có tỷ lệ đạt chỉ tiêu thấp nhất: {bottom_staff}.")
            except Exception as e:
                pass
                
            conn.close()
            return "\n".join(summary_parts)
        except Exception as e:
            return f"Lỗi lấy tóm tắt CSDL: {e}"

    _RESET_CONVERSATION_PHRASES = {
        "reset", "reset_conversation", "xóa hội thoại", "xoá hội thoại",
        "quên đi", "bắt đầu lại"
    }

    def ask(self, user_question, session_key=None):
        """Translates natural language question to SQL, runs it, and formats response."""
        if user_question.strip() == "admin_restart_bot_process":
            # Acknowledge the update to Telegram to break the infinite restart loop
            try:
                import urllib.request
                import json
                token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                if token:
                    # Fetch latest updates to get the update_id of this restart command
                    get_url = f"https://api.telegram.org/bot{token}/getUpdates?limit=10"
                    with urllib.request.urlopen(get_url, timeout=5) as resp:
                        res = json.loads(resp.read().decode('utf-8'))
                        if res.get("ok") and res.get("result"):
                            # Find the update_id of the restart message
                            max_update_id = None
                            for update in res["result"]:
                                msg = update.get("message", {})
                                if msg.get("text", "").strip() == "admin_restart_bot_process":
                                    max_update_id = max(max_update_id or 0, update["update_id"])
                            if max_update_id is not None:
                                # Send getUpdates with offset to acknowledge the message
                                ack_url = f"https://api.telegram.org/bot{token}/getUpdates?offset={max_update_id + 1}&limit=1"
                                urllib.request.urlopen(ack_url, timeout=5).close()
            except Exception as e:
                print(f"[Error acknowledging restart update]: {e}")
                
            os._exit(0)

        if user_question.strip().lower() in self._RESET_CONVERSATION_PHRASES:
            if session_key and session_key in self._conversation_histories:
                del self._conversation_histories[session_key]
            return {
                "question": user_question,
                "sql": "",
                "data": [],
                "columns": [],
                "answer": "Đã xóa lịch sử hội thoại. Anh/Chị có thể bắt đầu câu hỏi mới.",
                "mode": "System"
            }

        db_schema = get_db_schema()
        history_block = self._get_history_block(session_key)

        # 1. Phân loại ý định của câu hỏi (Intent Classification)
        intent = "DATA_QUERY"
        q_lower = user_question.lower().strip()

        # Mặc định mọi bảng/danh sách chỉ hiển thị Top 10 (giữ câu trả lời + bảng gọn),
        # trừ khi người dùng chủ động hỏi xem toàn bộ/đầy đủ danh sách.
        wants_full_list = any(k in q_lower for k in [
            "toàn bộ", "toan bo", "tất cả", "tat ca", "đầy đủ", "day du",
            "danh sách đầy đủ", "danh sach day du", "full list", "không giới hạn", "khong gioi han"
        ])

        # Fast Heuristic Intent Classifier (Bypasses LLM to save 3+ seconds)
        # "hi" phải check bằng \b (word boundary), KHÔNG dùng substring "hi " thô — "hi " từng
        # khớp nhầm bên trong vô số từ tiếng Việt thông dụng chứa "hi" theo sau khoảng trắng/âm
        # tiết khác, ví dụ "chi tiết", "khi tôi", "nghi ngờ" — khiến các câu hỏi dữ liệu hợp lệ
        # bị coi là lời chào và không bao giờ chạy SQL (ví dụ: "Xem chi tiết các hợp đồng ETC").
        _has_hi_greeting = bool(re.search(r'\bhi\b', q_lower))
        if _has_hi_greeting or any(w in q_lower for w in ["chào", "hello", "bạn là ai", "huong dan", "hướng dẫn", "chức năng", "giúp gì", "cmd", "help"]):
            intent = "GENERAL"
        elif any(w in q_lower for w in ["tại sao", "tai sao", "vì sao", "vi sao", "làm thế nào", "lam the nao", "giải pháp", "giai phap", "khắc phục", "khac phuc"]):
            intent = "ANALYSIS"
        elif q_lower in ["báo cáo đi", "tình hình thế nào", "số liệu", "cho xin báo cáo", "hôm nay thế nào", "báo cáo", "bao cao", "tình hình", "tinh hinh"]:
            intent = "AMBIGUOUS"

        # 2. Xử lý theo từng Intent
        if intent == "AMBIGUOUS":
            answer = """Để em báo cáo chính xác nhất cho Anh/Chị, Anh/Chị vui lòng chọn thông tin muốn xem dưới đây:

1️⃣ <b>Báo cáo Doanh số & KPI</b> (Kênh OTC/ETC, ngành hàng, Top nhân sự/đơn hàng).
2️⃣ <b>Báo cáo Quản lý Công nợ</b> (Nợ quá hạn OTC/ETC, top đại lý nợ nhiều nhất).
3️⃣ <b>Báo cáo Tồn kho & Đứt hàng</b> (Sản phẩm bán chạy, cháy hàng dưới 1 tháng).

<i>(Vui lòng gõ số hoặc câu hỏi chi tiết hơn để em hỗ trợ nhé!)</i>"""
            result = {
                "question": user_question,
                "sql": "",
                "data": [],
                "columns": [],
                "answer": answer,
                "mode": "Disambiguation Menu"
            }
            self._remember_turn(session_key, user_question, result["answer"])
            return result
        if intent == "ANALYSIS" and not self.is_mock:
            # Lấy tóm tắt dữ liệu hiện tại làm ngữ cảnh
            db_summary = self._get_database_summary()

            analysis_prompt = f"""
Bạn là chuyên gia phân tích dữ liệu kinh doanh và tư vấn chiến lược của Dược Nam Hà (DNH).
Người dùng hỏi một câu hỏi dạng "tại sao" hoặc "làm thế nào" (why/how) liên quan đến hoạt động kinh doanh.

{history_block}
Dưới đây là tóm tắt trạng thái dữ liệu hiện tại của hệ thống DNH:
{db_summary}

Câu hỏi của người dùng: "{user_question}"

QUY TẮC TRÌNH BÀY (BẮT BUỘC):
1. Trả lời NGẮN GỌN, súc tích, KHÔNG quá 150 từ. Đây là tin nhắn chat, không phải báo cáo văn bản dài.
2. Trình bày đúng 3 phần theo thứ tự, mỗi phần CHỈ 1-2 câu ngắn (dùng thẻ <b> làm tiêu đề, KHÔNG dùng #, ##, ###):
   <b>Thực trạng:</b> 1 câu nêu con số cốt lõi.
   <b>Nguyên nhân:</b> tối đa 2-3 nguyên nhân chính, mỗi nguyên nhân 1 câu ngắn.
   <b>Giải pháp:</b> tối đa 2-3 giải pháp chính, mỗi giải pháp 1 câu ngắn.
3. TUYỆT ĐỐI KHÔNG dùng markdown: không `**text**`, không `*text*`, không `###`/`##`, không `---`, không đánh số La Mã (I./II.), không tiêu đề phụ lồng nhau. Nếu cần in đậm, dùng thẻ HTML <b>text</b>.
4. Nếu cần liệt kê, dùng gạch đầu dòng đơn giản "- " trên từng dòng, KHÔNG lồng thêm bullet con bên dưới mỗi ý.
5. Không lặp lại toàn bộ số liệu chi tiết (tên từng nhân viên/từng SKU/từng khách hàng) — chỉ nêu tối đa 1 ví dụ tiêu biểu nhất cho mỗi nguyên nhân nếu thực sự cần thiết.
6. Viết bằng tiếng Việt tự nhiên, giọng văn chuyên nghiệp nhưng đi thẳng vào trọng tâm.
"""
            try:
                answer = self._call_ai(
                    model=self.summary_model,
                    system_prompt="You are a helpful data analyst.",
                    user_prompt=analysis_prompt
                )
                result = {
                    "question": user_question,
                    "sql": "",
                    "data": [],
                    "columns": [],
                    "answer": answer,
                    "mode": f"Live {self.model_type.upper()} API (Analysis)"
                }
                self._remember_turn(session_key, user_question, result["answer"])
                return result
            except Exception as e:
                print(f"[Error generating analysis]: {e}")
                # Fallback to query if analysis generation fails
                intent = "DATA_QUERY"

        elif intent == "GENERAL" and not self.is_mock:
            general_prompt = f"""
Bạn là trợ lý ảo phân tích dữ liệu Dược Nam Hà (DNH).
Người dùng đang chào hỏi hoặc nói chuyện thông thường.
Hãy trả lời một cách thân thiện, ngắn gọn và giới thiệu các nhóm dữ liệu bạn có thể giúp họ tra cứu hoặc phân tích bao gồm:
1. Dữ liệu công nợ khách hàng (overdue, OTC, ETC).
2. Dữ liệu tồn kho sản phẩm (mặt hàng bán chậm, cận date, thiếu hàng).
3. Hiệu suất đạt chỉ tiêu KPI doanh số của nhân viên kinh doanh theo vùng miền.

Hãy viết bằng tiếng Việt.

{history_block}
Câu hỏi/Lời chào của người dùng: "{user_question}"
"""
            try:
                answer = self._call_ai(
                    model=self.summary_model,
                    system_prompt="You are a helpful chatbot assistant.",
                    user_prompt=general_prompt
                )
                result = {
                    "question": user_question,
                    "sql": "",
                    "data": [],
                    "columns": [],
                    "answer": answer,
                    "mode": f"Live {self.model_type.upper()} API (Chat)"
                }
                self._remember_turn(session_key, user_question, result["answer"])
                return result
            except Exception as e:
                print(f"[Error generating general reply]: {e}")
                intent = "DATA_QUERY"

        # LUỒNG CHẠY DATA_QUERY (HOẶC MOCK): Dịch SQL, thực thi và tóm tắt kết quả
        cloud_db_url = os.getenv("CLOUD_DB_URL", "")
        
        # Get dynamic date context from the database to avoid hardcoding date boundaries
        latest_date_str, latest_month_end_str, latest_period = self._get_latest_dates()
        parts = latest_date_str.split('-')
        latest_year = parts[0] if len(parts) > 0 else "2026"
        latest_month = parts[1] if len(parts) > 1 else "06"
        latest_q_start = f"{latest_year}-04-01"

        db_dialect = "PostgreSQL"
        # Cloud is configured but unreachable right now (DNS/network failure) — distinct from
        # "no cloud configured"/"mock mode", both of which are intentional offline setups the
        # user already knows about. This case silently swaps in the old, much smaller SQLite
        # fallback schema (missing brv_hoadonhdr/dms_khachhang/etc.), so answers can look
        # confidently correct while actually coming from an unrelated/stale mock table.
        cloud_unreachable_fallback = bool(cloud_db_url) and not self.is_mock and not self.cloud_available
        if "mssql" in cloud_db_url.lower() or "sqlserver" in cloud_db_url.lower() or os.getenv("DB_DIALECT", "").lower() == "mssql":
            db_dialect = "TSQL"
        elif not cloud_db_url or self.is_mock or not self.cloud_available:
            db_dialect = "SQLite"
        
        dialect_rules = ""
        if db_dialect == "PostgreSQL":
            dialect_rules = """
3. Make sure to use SQL functions that are compatible with PostgreSQL (e.g. COALESCE, NOW(), CURRENT_DATE, ILIKE for case-insensitive search, etc.).
4. VERY IMPORTANT: Use 'ILIKE' instead of 'LIKE' for case-insensitive search on text columns. Since values in the database (like CityName, Name, item_name) may be stored without Vietnamese tone marks, when filtering Vietnamese text, you MUST search for BOTH the accented and unaccented versions using OR. For example: (t."CityName" ILIKE '%Bắc%' OR t."CityName" ILIKE '%Bac%') or (n."Name" ILIKE '%Tùng%' OR n."Name" ILIKE '%Tung%').
5. VERY IMPORTANT: In PostgreSQL, the ROUND(value, decimals) function requires the first argument to be explicitly cast to numeric, e.g. ROUND(expression::numeric, 2). Otherwise, it will fail with "function round(double precision, integer) does not exist".
6. VERY IMPORTANT: In the DNH database, date columns like 'DocDate' or 'SaveDate' are stored as TEXT (VARCHAR). In PostgreSQL, you MUST explicitly cast them to timestamp or date when using date/time functions like DATE_TRUNC or when doing date comparisons. For example: DATE_TRUNC('month', "DocDate"::timestamp), DATE_TRUNC('day', "DocDate"::timestamp), or WHERE "DocDate"::date >= '2026-04-01'. Failure to do so will cause PostgreSQL crash error: "function date_trunc(unknown, text) does not exist".
7. Do not use SQLite specific functions like strftime. Use standard Postgres date/time operators and intervals.
8. ALWAYS wrap case-sensitive table and column names in double quotes if they contain uppercase letters (e.g. "TotalAmount", "DocStatus", "EInvoiceStatus", "IsActive", "CustomerCode", "EmployeeCode", "MonthSaleTarget", "Amount_Cus", "Amount_CT", "SaveDate"). For example: h."TotalAmount", f."MonthSaleTarget".
"""
        elif db_dialect == "TSQL":
            dialect_rules = """
3. Make sure to use SQL functions that are compatible with Microsoft SQL Server (T-SQL) (e.g. COALESCE, GETDATE(), TRY_CAST, CONVERT, DATEADD, DATEDIFF, DATEPART, etc.).
4. ALWAYS use 'LIKE' instead of 'ILIKE' (T-SQL is case-insensitive by default under standard collation). Since values in the database (like CityName, Name, item_name) may be stored without Vietnamese tone marks, when filtering Vietnamese text, you MUST search for BOTH the accented and unaccented versions using OR. For example: (t.CityName LIKE '%Bắc%' OR t.CityName LIKE '%Bac%') or (n.Name LIKE '%Tùng%' OR n.Name LIKE '%Tung%').
5. ALWAYS wrap case-sensitive table and column names in square brackets if they contain uppercase letters or spaces (e.g. h.[TotalAmount], f.[MonthSaleTarget], [brv_hoadonhdr], [dms_khachhang]). Do NOT use double quotes.
6. VERY IMPORTANT: In T-SQL, there is no LIMIT clause. To limit the number of rows returned, use 'SELECT TOP N ...' at the very beginning of the query instead of 'LIMIT N' at the end. For example: 'SELECT TOP 100 ...' or 'SELECT TOP 5 ...'. Always default to TOP 100 for open list queries.
7. VERY IMPORTANT: In the DNH database, date columns like 'DocDate' or 'SaveDate' are stored as TEXT (VARCHAR). In T-SQL, you MUST explicitly cast them to DATE or DATETIME when doing date/time functions or date comparisons using TRY_CAST or CONVERT. For example: TRY_CAST([DocDate] AS DATE), or DATEADD(month, DATEDIFF(month, 0, TRY_CAST([DocDate] AS DATE)), 0) to truncate to the beginning of the month.
8. For multi-month grouping in T-SQL, use DATEPART(month, TRY_CAST([DocDate] AS DATE)) or convert to month-start, and group by it.
9. ALWAYS default to adding 'TOP 100' for open-ended queries to prevent dumping thousands of records.
"""
        else:
            dialect_rules = """
3. Make sure to use SQL functions that are compatible with SQLite (e.g. COALESCE, IFNULL, strftime, etc.).
"""

        system_prompt = f"""
You are an expert SQL Generator for Duoc Nam Ha (DNH) commercial data warehouse.
Your task is to convert the user's Vietnamese natural language query into a single valid {db_dialect} query.

Here is the database schema:
{db_schema}

Key Business Logic & Tables & Strict Mapping Rules:
1. Doanh thu thực tế (Actual Sales/Revenue):
   - Do NOT query the 'orders' or 'invoices' tables. They are mock/deprecated tables.
   - For general "doanh thu" or "doanh số" (without specifying OTC or ETC), they want the combined total of BOTH OTC and ETC. You MUST use a UNION ALL of both 'brv_hoadonhdr' (OTC) and 'brvsx_hoadonhdr' (ETC).
   - IMPORTANT matching & filtering rules to match DNH official reports:
     * ALWAYS join 'brv_hoadonhdr' with 'dms_khachhang' (for OTC) and 'brvsx_hoadonhdr' with 'dmssx_khachhang' (for ETC) on CustomerCode = Code. This naturally filters out internal branch transfer codes (like '1001136', '1001679', 'P000001', 'P000002') because they do not exist in the customer dimension tables.
     * For OTC: ALWAYS filter h."IsHC" = FALSE (to exclude mock invoices).
     * For ETC: ALWAYS filter h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632') to exclude non-operating wholesalers/distributors from the hospital sales figures.
   - For OTC Revenue (Doanh thu OTC): Query from 'brv_hoadonhdr' h JOIN 'dms_khachhang' k ON h."CustomerCode" = k."Code".
   - For ETC Revenue (Doanh thu ETC): Query from 'brvsx_hoadonhdr' h JOIN 'dmssx_khachhang' k ON h."CustomerCode" = k."Code".
   - Net ETC Revenue (Doanh thu thuần ETC): Is ETC Revenue minus returns: 'brvsx_hoadonhdr.TotalAmount' minus 'brvsx_tralai.TotalAmount0' (both filtered with IsActive, status, and joined with dmssx_khachhang).
   - Valid Invoices Filter (Lọc hóa đơn hợp lệ): ALWAYS filter out cancelled/deleted invoices by joining with 'brv_trangthaiduyet' and 'brv_trangthaihoadon':
     * Join 'brv_trangthaiduyet' d ON h.DocStatus = d.DocStatusKey -> filter (d.IsCancelled IS NULL OR d.IsCancelled = FALSE)
     * Join 'brv_trangthaihoadon' e ON h.EInvoiceStatus = e.EInvoiceStatusKey -> filter (e.IsCancelled IS NULL OR e.IsCancelled = FALSE)
     * Always add: WHERE h.IsActive = TRUE (or h."IsActive" = TRUE)
   - Example query for general/total revenue by region:
     WITH otc_sales AS (
       SELECT 'OTC' AS "Channel", t."AreaCode" AS "Region", h."TotalAmount", h."DocStatus", h."EInvoiceStatus", h."IsActive", h."DocDate"
       FROM brv_hoadonhdr h
       JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
       JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
       WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
     ),
     etc_sales AS (
       SELECT 'ETC' AS "Channel", t."AreaCode" AS "Region", h."TotalAmount", h."DocStatus", h."EInvoiceStatus", h."IsActive", h."DocDate"
       FROM brvsx_hoadonhdr h
       JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
       JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
       WHERE h."IsActive" = TRUE AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
     ),
     combined_sales AS (
       SELECT * FROM otc_sales
       UNION ALL
       SELECT * FROM etc_sales
     )
     SELECT c."Channel", c."Region", SUM(c."TotalAmount") AS "Revenue"
     FROM combined_sales c
     LEFT JOIN brv_trangthaiduyet d ON c."DocStatus" = d."DocStatusKey"
     LEFT JOIN brv_trangthaihoadon e ON c."EInvoiceStatus" = e."EInvoiceStatusKey"
     WHERE (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE) 
       AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
     GROUP BY c."Channel", c."Region"
   - VERY IMPORTANT DUPLICATION RULE: AVOID performing joins on combined/UNION subqueries (e.g. joining a union of invoices with a union of customer lists). This causes invoice rows to duplicate because customer codes overlap across channels. ALWAYS join each invoice table with its corresponding customer table first inside separate CTEs (like 'otc_sales' and 'etc_sales'), and then UNION ALL the CTEs.

2. Vùng miền / Địa bàn (Regions/Territories):
   - There is no direct region column in the headers. You must join with client and city tables:
     * For OTC: Join 'brv_hoadonhdr' with 'dms_khachhang' on CustomerCode = Code -> Join 'dim_tinhthanhpho' on CityId = CityId.
     * For ETC: Join 'brvsx_hoadonhdr' with 'dmssx_khachhang' on CustomerCode = Code -> Join 'dim_tinhthanhpho' on CityId = CityId.
     * Use 'dim_tinhthanhpho.AreaCode' to get the region:
       - 'MB' -> Miền Bắc (North)
       - 'MT' -> Miền Trung (Central)
       - 'MN' -> Miền Nam (South)
     * Example query for North region OTC sales:
       SELECT SUM(h."TotalAmount") FROM brv_hoadonhdr h
       JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
       JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
       LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
       LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
       WHERE h."IsActive" = TRUE AND t."AreaCode" = 'MB'
         AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
         AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)

3. Chỉ tiêu Doanh thu (Revenue Targets):
   - CRITICAL DATE FILTER: 'dim_targetvungmien' và 'fact_kehoachtongetc' lưu chỉ tiêu THEO THÁNG — mỗi tháng có NHIỀU dòng (theo từng nhân viên/khu vực chi tiết trong dim_targetvungmien, hoặc theo ItemGroup trong fact_kehoachtongetc). Cột "DocDate" là TEXT dạng 'YYYY-MM-01T00:00:00' (luôn là ngày 01 đầu tháng kèm giờ). BẮT BUỘC lọc "DocDate"::date = 'YYYY-MM-01' (ép kiểu date rồi so sánh) khi cần chỉ tiêu của MỘT tháng cụ thể — KHÔNG so sánh chuỗi thô kiểu "DocDate" = 'YYYY-MM-01' (thiếu phần 'T00:00:00' sẽ không khớp dòng nào, trả về SUM = 0, dẫn tới báo sai "chưa có target"). Nếu quên lọc "DocDate" hoàn toàn, kết quả sẽ CỘNG DỒN target của TẤT CẢ các tháng có trong bảng (sai, bị nhân lên nhiều lần).
   - Target OTC Region: Query 'dim_targetvungmien' (column 'Amount'). Grouped by 'AreaCode' ('MB', 'MT', 'MN'). ALWAYS filter: "ChannelCode" = 'GT' for OTC region targets. Ví dụ target OTC miền Bắc của tháng hiện tại:
     SELECT COALESCE(SUM("Amount"), 0) AS target_amount
     FROM dim_targetvungmien
     WHERE "AreaCode" = 'MB' AND "ChannelCode" = 'GT'
       AND "DocDate"::date = '{latest_year}-{latest_month}-01'
   - Target ETC Region: Query 'dim_targetvungmien' with "ChannelCode" = 'MT', áp dụng cùng cách lọc "DocDate"::date như trên.
   - Target ETC toàn công ty: Query 'fact_kehoachtongetc' (column 'Amount', có cột 'ItemGroup' nhưng KHÔNG có cột vùng miền), cũng phải lọc "DocDate"::date = 'YYYY-MM-01' như trên.
   - Employee targets: Query 'fact_tonghopkhachhang' (column 'MonthSaleTarget').
     * VERY IMPORTANT: Since fact_tonghopkhachhang has duplicate target values per customer row for each employee, ALWAYS group by EmployeeCode and SaveDate to get the unique employee targets before summing them:
       SELECT SUM(target) FROM (SELECT DISTINCT "EmployeeCode", "SaveDate", "MonthSaleTarget" as target FROM fact_tonghopkhachhang) t
   - COMPARISON (ACTUAL VS TARGET MONTHLY BREAKDOWN): Khi so sánh thực tế và chỉ tiêu của một Quý hoặc cả năm, bạn BẮT BUỘC phải GROUP BY theo từng tháng (sử dụng WITH CTEs cho actual và target, sau đó JOIN trên ngày đầu tháng). KHÔNG ĐƯỢC gộp chung cả quý vào 1 dòng duy nhất.
     Ví dụ so sánh doanh số thực tế và chỉ tiêu target OTC của miền Bắc trong quý 2-2026:
     WITH actual_monthly AS (
       SELECT 
         DATE_TRUNC('month', h."DocDate"::timestamp)::date AS month_start,
         COALESCE(SUM(h."TotalAmount"), 0) AS actual_revenue
       FROM brv_hoadonhdr h
       JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
       JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
       LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
       LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
       WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
         AND t."AreaCode" = 'MB'
         AND h."DocDate"::date >= '2026-04-01' AND h."DocDate"::date <= '2026-06-30'
         AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
         AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
       GROUP BY DATE_TRUNC('month', h."DocDate"::timestamp)::date
     ),
     target_monthly AS (
       SELECT 
         "DocDate"::date AS month_start,
         COALESCE(SUM("Amount"), 0) AS target_revenue
       FROM dim_targetvungmien
       WHERE "AreaCode" = 'MB' AND "ChannelCode" = 'GT'
         AND "DocDate"::date >= '2026-04-01' AND "DocDate"::date <= '2026-06-30'
       GROUP BY "DocDate"::date
     )
     SELECT 
       TO_CHAR(COALESCE(a.month_start, t.month_start), 'MM-YYYY') AS "Tháng",
       COALESCE(a.actual_revenue, 0) AS "Doanh số thực tế",
       COALESCE(t.target_revenue, 0) AS "Chỉ tiêu Target",
       COALESCE(a.actual_revenue, 0) - COALESCE(t.target_revenue, 0) AS "Chênh lệch",
       CASE 
         WHEN COALESCE(t.target_revenue, 0) > 0 THEN ROUND((COALESCE(a.actual_revenue, 0) * 100.0 / t.target_revenue)::numeric, 2)
         ELSE 0
       END AS "Tỷ lệ hoàn thành"
     FROM actual_monthly a
     FULL OUTER JOIN target_monthly t ON a.month_start = t.month_start
     ORDER BY COALESCE(a.month_start, t.month_start);

4. KPI / Hiệu suất Nhân viên (Employee KPI & Sales Performance):
   - CRITICAL — HAI NGUỒN KHÁC NHAU THEO CẤP BẬC, KHÔNG DÙNG LẪN:
     * 'fact_tonghopkhachhang' CHỈ có dữ liệu cho nhân sự CÓ danh mục khách hàng riêng: PositionCode 'TDV', 'QLV', 'CS', 'CTV', 'TK'. Bảng này là tổng hợp theo TỪNG KHÁCH HÀNG của từng nhân viên, nên cấp quản lý không trực tiếp bán hàng sẽ KHÔNG xuất hiện.
     * 'TP' (Trưởng phòng), 'PP' (Phó phòng), 'TBP' (Trưởng bộ phận) KHÔNG có dòng nào trong 'fact_tonghopkhachhang' (join với dim_nhanvien sẽ luôn ra 0 dòng — dim_nhanvien."EmployeeCode" của các cấp này có thể là mã VÙNG như 'MB'/'MT'/'MN', không phải mã nhân viên bán hàng thật). BẮT BUỘC dùng bảng 'kpi_summary' (đã tổng hợp sẵn, có cột position_code, employee_code, employee_name, month_sale_target, month_sale_amount, month_sale_percent, quarter_sale_*, year_sale_*) — KHÔNG join với dim_nhanvien/fact_tonghopkhachhang cho các cấp này.
     * Ví dụ tỉ lệ đạt KPI của Trưởng phòng:
       SELECT employee_name, month_sale_target, month_sale_amount,
              ROUND((month_sale_percent * 100)::numeric, 2) AS "Tỉ lệ đạt KPI (%)"
       FROM kpi_summary
       WHERE position_code = 'TP'
       ORDER BY month_sale_percent DESC
     * LƯU Ý DỮ LIỆU: 'kpi_summary' hiện có thể chưa đầy đủ cho mọi Trưởng phòng/Phó phòng (dữ liệu nhập tay từ báo cáo Excel định kỳ, không đồng bộ tự động như fact_tonghopkhachhang) — nếu kết quả trả về ít dòng hơn số lượng nhân sự cấp đó thực tế có, đừng coi là lỗi truy vấn, hãy nêu rõ trong câu trả lời rằng dữ liệu hệ thống hiện chỉ ghi nhận được từng đó người.
   - Với TDV/QLV/CS/CTV/TK, tiếp tục dùng 'fact_tonghopkhachhang' (actual sales = 'Amount_Cus', target = 'MonthSaleTarget', employee code = 'EmployeeCode', region = 'AreaCode' / 'AreaCode2').
   - Join with 'dim_nhanvien' on EmployeeCode = EmployeeCode to get employee details (like employee name: 'Name', position: 'PositionCode').
   - IMPORTANT DEDUP RULES:
     * dim_nhanvien has 'IsDuplicate' column. ALWAYS filter: (n."IsDuplicate" IS NULL OR n."IsDuplicate" = 0) to exclude duplicate employee records.
     * fact_tonghopkhachhang has one row PER CUSTOMER per employee per month. MonthSaleTarget is repeated on every row for the same employee.
     * To get the correct target: SELECT DISTINCT "EmployeeCode", "SaveDate", "MonthSaleTarget" FROM fact_tonghopkhachhang
     * To get the correct actual total: SUM("Amount_Cus") grouped by EmployeeCode.
   - Position codes:
     * 'TDV' or 'Trình dược viên' -> dim_nhanvien."PositionCode" = 'TDV' (dùng fact_tonghopkhachhang)
     * 'QLV' or 'Quản lý vùng' -> dim_nhanvien."PositionCode" = 'QLV' (dùng fact_tonghopkhachhang)
     * 'TP' or 'Trưởng phòng' -> kpi_summary.position_code = 'TP' (dùng kpi_summary, xem CRITICAL ở trên — KHÔNG dùng fact_tonghopkhachhang)
     * 'PP' or 'Phó phòng' -> kpi_summary.position_code = 'PP' (dùng kpi_summary)
     * 'TBP' or 'Trưởng bộ phận' -> kpi_summary.position_code = 'TBP' (dùng kpi_summary)
   - When the user asks about KPI or nhân viên without specifying position, DEFAULT to TDV (Trình dược viên) since they are the primary salesforce.
   - SaveDate is the month-end date stored as TEXT: '{latest_month_end_str}T00:00:00' for the latest month. The LATEST period is '{latest_month_end_str}T00:00:00'.
   - Example to get Top TDV by KPI completion (correct dedup):
     WITH tdv_actual AS (
       SELECT f."EmployeeCode", SUM(f."Amount_Cus") AS total_actual
       FROM fact_tonghopkhachhang f
       JOIN dim_nhanvien n ON f."EmployeeCode" = n."EmployeeCode"
       WHERE n."PositionCode" = 'TDV'
         AND (n."IsDuplicate" IS NULL OR n."IsDuplicate" = 0)
         AND f."SaveDate" = '{latest_month_end_str}T00:00:00'
       GROUP BY f."EmployeeCode"
     ),
     tdv_target AS (
       SELECT DISTINCT f."EmployeeCode", f."MonthSaleTarget"
       FROM fact_tonghopkhachhang f
       JOIN dim_nhanvien n ON f."EmployeeCode" = n."EmployeeCode"
       WHERE n."PositionCode" = 'TDV'
         AND (n."IsDuplicate" IS NULL OR n."IsDuplicate" = 0)
         AND f."SaveDate" = '{latest_month_end_str}T00:00:00'
         AND f."MonthSaleTarget" IS NOT NULL
     )
     SELECT n."Name", a."EmployeeCode", a.total_actual, t."MonthSaleTarget" AS target,
            ROUND((a.total_actual / t."MonthSaleTarget" * 100)::numeric, 1) AS pct
     FROM tdv_actual a
     JOIN dim_nhanvien n ON a."EmployeeCode" = n."EmployeeCode"
     JOIN tdv_target t ON a."EmployeeCode" = t."EmployeeCode"
     WHERE t."MonthSaleTarget" > 0
     ORDER BY pct DESC
     LIMIT 5

5. Sản phẩm (Products) & Top bán chạy:
   - Query product details by joining 'brv_hoadonct' (for OTC) or 'brvsx_hoadonct' (for ETC) with 'brv_sanpham' on ItemCode = Code.
   - Use 'brv_sanpham.Name' to filter product names.
   - IMPORTANT: 'Quantity9' is the selling-unit quantity. 'Quantity' is the sub-unit quantity (e.g. pills, pieces). Always use Quantity9 for reporting.
   - Revenue per line item: 'Amount9'.
   - IMPORTANT: The 'CTKM' column identifies promotion/free-goods lines (Chương trình khuyến mãi). When CTKM is NOT empty, it means the line is a free-goods/promotion giveaway (UnitPrice=0, Amount9=0).
   - When asked for 'Top sản phẩm bán chạy' or similar, ALWAYS split quantities into:
     * SL Thực bán (Actual sold qty): SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Quantity9" ELSE 0 END)
     * SL Khuyến mãi (Promo/Free qty): SUM(CASE WHEN c."CTKM" IS NOT NULL AND c."CTKM" != '' THEN c."Quantity9" ELSE 0 END)
     * Tổng SL (Total qty): SUM(c."Quantity9")
     * Doanh thu (Revenue): SUM(c."Amount9")
   - Example Top 10 OTC best sellers:
     SELECT p."Name" AS product_name,
            SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Quantity9" ELSE 0 END) AS sl_thuc_ban,
            SUM(CASE WHEN c."CTKM" IS NOT NULL AND c."CTKM" != '' THEN c."Quantity9" ELSE 0 END) AS sl_khuyen_mai,
            SUM(c."Quantity9") AS tong_sl,
            SUM(c."Amount9") AS doanh_thu
     FROM brv_hoadonct c
     JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
     JOIN brv_sanpham p ON c."ItemCode" = p."Code"
     LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
     LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
     WHERE h."IsActive" = TRUE
       AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
       AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
     GROUP BY p."Name"
     ORDER BY doanh_thu DESC
     LIMIT 10

6. Công nợ (Receivables):
   - Query 'receivable_detail' (period, customer_code, customer_name, balance_end, in_term, total_overdue, sales_channel).
   - Do NOT query receivable_etc.
   - LATEST PERIOD: Always filter by period = '{latest_period}' (using underscore, e.g. '{latest_period}' represents the latest period) when looking for the latest receivables!

7. Tồn kho (Inventory):
   - Query 'inventory' (item_code, item_name, unit, closing_qty, closing_value, months_to_sell, warehouse).
   - 'months_to_sell' là cột nhập thẳng từ hệ thống nguồn (dự phòng số tháng bán), KHÔNG rõ cách tính — KHÔNG dùng cột này làm câu trả lời chính khi người dùng hỏi về tốc độ bán/số ngày còn lại; PHẢI tự tính toán minh bạch từ dữ liệu hóa đơn thực tế theo hướng dẫn dưới đây.
   - VERY IMPORTANT — "Tồn kho nhiều nhất/ít nhất", "còn bán được bao lâu", "số ngày tồn kho còn lại": KHÔNG được chỉ trả về closing_qty thô. PHẢI tính thêm "trung bình bán mỗi ngày" (từ tổng SL Thực bán trong dữ liệu hóa đơn đã có, chia cho số ngày của khoảng dữ liệu đó) và "số ngày tồn kho còn lại" = closing_qty / trung bình bán mỗi ngày. Tính trung bình bán bằng cách gộp cả 2 kênh OTC ('brv_hoadonct'+'brv_hoadonhdr') và ETC ('brvsx_hoadonct'+'brvsx_hoadonhdr') qua CTE riêng rồi UNION ALL (theo đúng quy tắc CTE-per-channel ở mục 5), chỉ tính SL Thực bán (loại trừ dòng khuyến mãi CTKM), join với inventory qua ItemCode = item_code. Ví dụ:
     WITH otc_sold AS (
       SELECT c."ItemCode" AS item_code,
              SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Quantity9" ELSE 0 END) AS qty_sold
       FROM brv_hoadonct c
       JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
       LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
       LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
       WHERE h."IsActive" = TRUE
         AND h."DocDate"::date >= '{latest_q_start}' AND h."DocDate"::date <= '{latest_date_str}'
         AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
         AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
       GROUP BY c."ItemCode"
     ),
     etc_sold AS (
       SELECT c."ItemCode" AS item_code,
              SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Quantity9" ELSE 0 END) AS qty_sold
       FROM brvsx_hoadonct c
       JOIN brvsx_hoadonhdr h ON c."Stt" = h."Stt"
       LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
       LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
       WHERE h."IsActive" = TRUE
         AND h."DocDate"::date >= '{latest_q_start}' AND h."DocDate"::date <= '{latest_date_str}'
         AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
         AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
       GROUP BY c."ItemCode"
     ),
     total_sold AS (
       SELECT item_code, SUM(qty_sold) AS total_qty_sold
       FROM (SELECT * FROM otc_sold UNION ALL SELECT * FROM etc_sold) x
       GROUP BY item_code
     )
     SELECT i.item_name AS "Tên sản phẩm",
            i.closing_qty AS "Tồn kho hiện tại",
            ROUND((COALESCE(s.total_qty_sold, 0) / (DATE '{latest_date_str}' - DATE '{latest_q_start}' + 1))::numeric, 2) AS "TB bán/ngày",
            ROUND((i.closing_qty / NULLIF(COALESCE(s.total_qty_sold, 0) / (DATE '{latest_date_str}' - DATE '{latest_q_start}' + 1), 0))::numeric, 1) AS "Số ngày tồn kho còn lại"
     FROM inventory i
     LEFT JOIN total_sold s ON i.item_code = s.item_code
     ORDER BY i.closing_qty DESC
     LIMIT 10
   - Mặt hàng có total_qty_sold = 0 (chưa bán trong kỳ) sẽ có "Số ngày tồn kho còn lại" = NULL (không chia được cho 0) — nêu rõ trong câu trả lời là "chưa phát sinh bán trong kỳ, không ước tính được" thay vì bỏ qua hoặc báo lỗi.

8. Date Queries & Date-based KPIs (Doanh thu theo thời gian & KPI lũy kế):
   - CRITICAL DATA BOUNDARY: The invoice data in the database ONLY spans from '{latest_q_start}' to '{latest_date_str}' (3 months: April, May, June {latest_year}). Data for January, February, March {latest_year} and any months before April {latest_year} DO NOT EXIST in the database.
   - VERY IMPORTANT: When user asks for '6 tháng đầu năm {latest_year}', '6 months', 'H1 {latest_year}', 'nửa đầu năm', etc. — the database ONLY has Q2 data (Apr-Jun). Your SQL must ONLY query the available date range '{latest_q_start}' to '{latest_date_str}'. You MUST add a comment in your SQL: -- NOTE: Only Q2 data (Apr-Jun {latest_year}) available. Jan-Mar data not in DB.
   - MANDATORY MONTHLY BREAKDOWN: When a user asks about revenue over a MULTI-MONTH period (e.g., '6 tháng', 'cả năm', 'theo tháng', 'Q2', 'quý 2', 'so sánh tháng X và tháng Y', etc.), you MUST return results GROUPED BY MONTH (not a single total). This produces multiple rows — one per month — so the chart can show each month separately. Use DATE_TRUNC('month', h."DocDate"::timestamp) AS "month" in the SELECT and GROUP BY clause. Example:
     SELECT DATE_TRUNC('month', h."DocDate"::timestamp) AS "month",
            SUM(otc.amount + etc.amount) AS "total_revenue"
     ... GROUP BY DATE_TRUNC('month', h."DocDate"::timestamp)
     ORDER BY "month"
   - VERY IMPORTANT — GROUP BY / SELECT EXPRESSION MUST MATCH EXACTLY: PostgreSQL requires every non-aggregated SELECT expression to appear VERBATIM in GROUP BY. NEVER mix two different date functions between SELECT and GROUP BY — e.g. do NOT write `SELECT TO_CHAR(h."DocDate"::timestamp, 'MM-YYYY') ... GROUP BY DATE_TRUNC('month', h."DocDate"::timestamp)`, this WILL fail with "column must appear in the GROUP BY clause". If you need a formatted month label (e.g. 'MM-YYYY') in SELECT, GROUP BY that exact same TO_CHAR(...) expression — do not swap in DATE_TRUNC for GROUP BY. Prefer grouping/ordering by DATE_TRUNC('month', h."DocDate"::timestamp) as a plain column (not reformatted with TO_CHAR) unless the user explicitly needs a text label; this also sorts chronologically correctly, unlike a formatted 'MM-YYYY' string.
   - Do NOT use CURRENT_DATE or NOW() for filters since the database does not contain July {latest_year} data.
   - For '7 ngày gần nhất' (last 7 days): Base the query on the maximum date in the database: (SELECT MAX("DocDate"::date) FROM brv_hoadonhdr) (which is '{latest_date_str}'). Filter for dates between MAX(date) - INTERVAL '6 days' and MAX(date):
     WHERE h."DocDate"::date >= (SELECT MAX("DocDate"::date) FROM brv_hoadonhdr WHERE "IsActive" = TRUE) - INTERVAL '6 days'
   - For 'doanh thu theo tháng' (monthly revenue): Group and sum the total revenue by month using DATE_TRUNC('month', h."DocDate"::timestamp) or similar casting:
     SELECT DATE_TRUNC('month', h."DocDate"::timestamp) AS month, SUM(h."TotalAmount") AS revenue
   - For 'kpi đến ngày 20' (KPI/revenue up to day 20): Sum cumulative actual sales from day 1 to day 20 of the latest month ({latest_year}-{latest_month}, i.e., from '{latest_year}-{latest_month}-01' to '{latest_year}-{latest_month}-20') and compare it to the target:
     WHERE h."DocDate"::date >= '{latest_year}-{latest_month}-01' AND h."DocDate"::date <= '{latest_year}-{latest_month}-20'

9. Chỉ số phái sinh BẮT BUỘC (Derived Metrics — cùng nguyên tắc với mục 7 Tồn kho):
   Nguyên tắc chung: con số thô gần như vô nghĩa với người quản lý — mọi câu hỏi dạng xếp hạng/đánh giá/so sánh PHẢI kèm thêm cột phái sinh giúp diễn giải con số đó. Cụ thể theo từng nhóm:
   - CÔNG NỢ ("khách nào nợ nhiều nhất", "rủi ro công nợ", "nợ xấu"): luôn thêm cột "Tỷ lệ quá hạn (%)" = ROUND((total_overdue / NULLIF(balance_end, 0) * 100)::numeric, 1). Khách nợ lớn nhưng tỷ lệ quá hạn thấp khác hẳn khách nợ nhỏ nhưng 100% đã quá hạn — bảng phải cho thấy điều đó.
   - TOP SẢN PHẨM BÁN CHẠY: ngoài 4 cột ở mục 5, thêm "TB bán/ngày" = SL Thực bán / (DATE '{latest_date_str}' - DATE '{latest_q_start}' + 1) và "Tỷ lệ KM (%)" = ROUND((SL Khuyến mãi / NULLIF(Tổng SL, 0) * 100)::numeric, 1) — tỷ lệ khuyến mãi cao cho thấy doanh số "ảo" nhờ hàng tặng.
   - KPI NHÂN VIÊN: ngoài % đạt chỉ tiêu, luôn thêm cột "Còn thiếu" = GREATEST(target - actual, 0) để thấy khoảng cách tuyệt đối phải bù (0 nếu đã vượt chỉ tiêu).
   - DOANH THU NHIỀU THÁNG (so sánh theo tháng): luôn thêm cột "% so với tháng trước" dùng window function LAG:
     ROUND(((rev - LAG(rev) OVER (ORDER BY month)) / NULLIF(LAG(rev) OVER (ORDER BY month), 0) * 100)::numeric, 1) AS "% so với tháng trước"
     (bọc aggregate trong CTE/subquery trước rồi mới áp LAG ở SELECT ngoài để tránh lồng aggregate + window sai cú pháp).
   - KHÁCH HÀNG MUA NHIỀU NHẤT (theo doanh thu): thêm "Số đơn hàng" = COUNT(DISTINCT h."Stt") và "Giá trị TB/đơn" = doanh thu / NULLIF(COUNT(DISTINCT h."Stt"), 0) — cho thấy khách mua đều đặn hay chỉ 1 đơn lớn.
   - LUÔN dùng NULLIF(mẫu_số, 0) cho mọi phép chia; nếu kết quả NULL do mẫu số bằng 0, câu trả lời phải nêu rõ "không đủ dữ liệu để tính" thay vì lờ đi.

NLP Synonym & Slang Mapping:
- "số má", "doanh số", "thu về", "doanh thu" -> Invoice TotalAmount (from brv_hoadonhdr / brvsx_hoadonhdr) or Amount_Cus (from fact_tonghopkhachhang).
- "nợ xấu", "kẹt tiền", "nợ đọng", "quá hạn" -> total_overdue in receivable_detail.
- "cháy hàng", "hết thuốc", "cạn kho" -> months_to_sell <= 1.0 or closing_qty = 0 in inventory.
- "run rate", "chốt sổ", "kết quả kinh doanh" -> fact_tonghopkhachhang.

Rules:
1. Return ONLY the {db_dialect} statement. Do not wrap it in markdown code block or write any explanation.
2. The query must be a SELECT statement.
VERY IMPORTANT — Default Row Limit: If the query returns a LIST of multiple records (e.g. ranking/listing of customers, products, employees, invoices — NOT a single aggregate SUM/COUNT/AVG row), by default add ORDER BY <cột giá trị/số lượng phản ánh đúng ý "cao nhất"/"nhiều nhất"/"thấp nhất" mà câu hỏi ngụ ý> (DESC, hoặc ASC nếu câu hỏi hỏi "thấp nhất"/"ít nhất") and limit the result to only the top 10 rows (use "LIMIT 10" in PostgreSQL/SQLite, or "TOP 10" in T-SQL — match the {db_dialect} syntax). {"Người dùng ĐÃ yêu cầu xem toàn bộ/đầy đủ danh sách trong câu hỏi này — KHÔNG giới hạn số dòng, trả về TẤT CẢ các dòng phù hợp." if wants_full_list else "Người dùng KHÔNG yêu cầu xem toàn bộ danh sách — PHẢI giới hạn 10 dòng như trên."}
VERY IMPORTANT — Vietnamese Column Labels (BẮT BUỘC): EVERY column in the SELECT clause MUST be aliased with a clear, human-readable Vietnamese label using AS "Tên tiếng Việt" — kể cả các cột passthrough đơn giản như mã khách hàng, tên khách hàng, kênh bán hàng. TUYỆT ĐỐI KHÔNG để lộ ra tên cột thô/snake_case/tiếng Anh của database (ví dụ: customer_code, customer_name, balance_end, total_overdue, sales_channel, employee_name, item_code, month_sale_target...) trong kết quả trả về — người dùng cuối không đọc được tên kỹ thuật này, nó sẽ hiển thị thẳng làm tiêu đề cột trên giao diện. Ví dụ ĐÚNG:
     SELECT customer_code AS "Mã khách hàng", customer_name AS "Tên khách hàng", sales_channel AS "Kênh bán hàng", total_overdue AS "Nợ quá hạn" FROM receivable_detail ...
   Áp dụng quy tắc này cho MỌI bảng/cột, không chỉ ví dụ trên — luôn tự dịch tên cột kỹ thuật sang tiếng Việt sát nghĩa nhất theo ngữ cảnh nghiệp vụ dược phẩm/thương mại của DNH.
{dialect_rules}
"""
        sql_query = ""
        if self.is_mock:
            sql_query = self._generate_mock_sql(user_question)
        else:
            try:
                sql_user_prompt = user_question
                if history_block:
                    sql_user_prompt = (
                        f'{history_block}\n'
                        f'Câu hỏi HIỆN TẠI cần chuyển thành SQL (dùng lịch sử ở trên chỉ để hiểu ngữ cảnh/tham chiếu, '
                        f'ví dụ câu hỏi ngắn như "1" hay "còn tháng khác thì sao" ám chỉ nội dung đã hỏi trước đó): "{user_question}"'
                    )
                sql_query = self._call_ai(
                    model=self.sql_model,
                    system_prompt=system_prompt,
                    user_prompt=sql_user_prompt,
                    temperature=0.0
                )
                if sql_query.startswith("```"):
                    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
            except Exception as e:
                print(f"[Error calling OpenAI API]: {e}")
                sql_query = self._generate_mock_sql(user_question)

        # Run the query
        query_result = self._execute_sql(sql_query)
        
        # Format textual answer
        answer = ""
        if "error" in query_result:
            answer = f"Tôi gặp lỗi khi thực hiện câu lệnh SQL: {query_result['error']}"
        else:
            if self.is_mock:
                if "total_sale" in str(query_result) or "month_sale_amount" in str(query_result):
                    row = query_result['rows'][0] if query_result['rows'] else {}
                    val = row.get('total_sale') or row.get('month_sale_amount') or 0
                    pct = row.get('kpi_pct') or (row.get('month_sale_percent', 0) * 100) or 0
                    name = row.get('employee_name') or row.get('region') or "đối tượng yêu cầu"
                    answer = f"Doanh số đạt được của {name} là: <b>{val:,.0f} VND</b>, hoàn thành <b>{pct:.2f}%</b> chỉ tiêu.\n\n"
                    answer += self._format_heuristically(query_result.get("columns", []), query_result.get("rows", []), user_question)
                elif "total_overdue" in str(query_result):
                    answer = "Dưới đây là danh sách khách hàng đang có nợ quá hạn cao nhất:\n\n"
                    answer += self._format_heuristically(query_result.get("columns", []), query_result.get("rows", []), user_question)
                elif "closing_qty" in str(query_result):
                    answer = "Dưới đây là danh sách các mặt hàng tồn kho theo yêu cầu của bạn:\n\n"
                    answer += self._format_heuristically(query_result.get("columns", []), query_result.get("rows", []), user_question)
                elif "contract_value" in str(query_result):
                    answer = "Thông tin thực hiện các hợp đồng thầu ETC (Bệnh viện) ghi nhận trên hệ thống:\n\n"
                    answer += self._format_heuristically(query_result.get("columns", []), query_result.get("rows", []), user_question)
                else:
                    answer = "Dưới đây là kết quả phân tích dữ liệu cho câu hỏi của bạn:\n\n"
                    answer += self._format_heuristically(query_result.get("columns", []), query_result.get("rows", []), user_question)
            else:
                llm_rows = query_result['rows']
                is_truncated_for_llm = False
                total_rows_count = len(llm_rows)
                if total_rows_count > 100:
                    llm_rows = llm_rows[:100]
                    is_truncated_for_llm = True

                # Parse intent using our fast heuristic visual intent parser first
                parsed_intent = self._parse_data_intent(user_question)
                intent_type = parsed_intent.get("intent", "Single_Value")
                
                # Mặc định LUÔN trả lời đơn giản/trực tiếp — chỉ mở rộng thành khung đầy đủ
                # Thực trạng-Nguyên nhân-Giải pháp khi câu hỏi TRỰC TIẾP hỏi "tại sao"/"như thế nào"
                # (không còn phụ thuộc số dòng kết quả — trước đây multi-row vẫn tự bị áp khung đầy
                # đủ dù người dùng không hỏi nguyên nhân/giải pháp).
                wants_deep_analysis = any(k in user_question.lower() for k in [
                    "tại sao", "tai sao", "vì sao", "vi sao",
                    "như thế nào", "nhu the nao", "làm thế nào", "lam the nao",
                    "làm sao", "lam sao", "nguyên nhân", "nguyen nhan", "giải pháp", "giai phap"
                ])

                framework_directive = ""
                if not wants_deep_analysis:
                    framework_directive = """5. Direct Response (KHÔNG dùng khung "Thực trạng - Nguyên nhân - Giải pháp"): Người dùng chỉ hỏi số liệu/thông tin, KHÔNG hỏi "tại sao" hay "như thế nào". Chỉ trả lời đúng cái được hỏi — trình bày số liệu/kết quả trực tiếp, ngắn gọn, chuyên nghiệp, TỐI ĐA 2-3 CÂU. TUYỆT ĐỐI KHÔNG tự thêm phần phân tích nguyên nhân hay đề xuất giải pháp khi không được hỏi. TUYỆT ĐỐI KHÔNG liệt kê nhiều mục theo từng nhóm/bullet point kiểu "Nhóm A: ...", "Nhóm B: ..." hay nêu tên từng dòng dữ liệu một — bảng dữ liệu chi tiết (Top 10) đã hiển thị riêng ở giao diện, câu trả lời chỉ cần nêu con số tổng hợp nổi bật nhất (ví dụ tổng số lượng, giá trị cao nhất) và tối đa 1 ví dụ tiêu biểu, rồi dẫn người dùng xem bảng bên dưới để biết chi tiết."""
                else:
                    framework_directive = """5. Executive Response Framework (Thực trạng - Nguyên nhân - Giải pháp): Người dùng có hỏi "tại sao"/"như thế nào" nên PHẢI trình bày đủ 3 phần theo thứ tự (dùng thẻ <b> làm tiêu đề):
   - <b>Thực trạng:</b> Trình bày trực tiếp các con số cốt lõi (Hero Metrics) dưới dạng in đậm (dùng thẻ <b>). Không cần liệt kê lại bảng dữ liệu chi tiết (đã hiển thị riêng ở giao diện), chỉ nêu con số tổng hợp.
   - <b>Nguyên nhân:</b> Phân tích sâu sắc và bóc tách nguyên nhân dựa trên số liệu thực tế từ kết quả truy vấn.
   - <b>Giải pháp:</b> Đề xuất các kiến nghị hành động cụ thể, phân vai rõ ràng cho các phòng ban."""

                summary_prompt = f"""
You are the executive AI Chatbot assistant for Duoc Nam Ha.
Your task is to summarize the SQL query results for C-level executives in a clean, professional, and natural Vietnamese tone.

{history_block}
User's original question: {user_question}
SQL query run: {sql_query}
Query results (showing {len(llm_rows)} of {total_rows_count} total records): {str(llm_rows)}
{"(Note: The query results were truncated to 100 rows for summarization. Please indicate in the response that only the top rows are shown and direct them to the dashboard/link for the full list of " + str(total_rows_count) + " records.)" if is_truncated_for_llm else ""}

CRITICAL RULES:
1. Zero-Hallucination: If the Query results are empty (i.e. '[]' or None or empty list), you MUST respond exactly: "Hiện tại chưa có dữ liệu cho truy vấn này". Do not guess, speculate, or fabricate anything.

2. BLUF (Bottom Line Up Front): Always present the most critical overall number (Hero Metric) on the very first line of the answer. E.g. "Doanh số OTC đạt <b>4,28 tỷ đ</b>, hoàn thành <b>95%</b> chỉ tiêu." Do not use polite greetings or introduction phrases.

3. KHÔNG chèn bảng dữ liệu (Markdown table) vào trong câu trả lời văn bản, kể cả khi kết quả có nhiều dòng — giao diện đã tự hiển thị bảng dữ liệu riêng từ kết quả truy vấn gốc (cột `data`/`columns`), chèn thêm bảng trong `answer` sẽ bị lặp. Chỉ viết văn xuôi ngắn gọn nêu con số/kết luận nổi bật.

4. Contextualization: Always contextualize numbers by comparing them MoM, YoY, or against Target (if targets exist in data). Format money in VND using 'tỷ đ' hoặc 'triệu đ' (e.g., '12,5 tỷ đ', '350 triệu đ', '250.000 đ') and percentages using '%'.

{framework_directive}

6. Formatting Guard: NEVER use markdown bold syntax like `**text**` or `*text*`. If you want to bold a word or number, ALWAYS use HTML tags like `<b>text</b>` or `<strong>text</strong>` — cả web UI lẫn Telegram đều render trực tiếp `answer` dưới dạng HTML, markdown thô sẽ hiện dấu sao thô.

7. Data Boundary Transparency (CRITICAL): The database only contains invoice data from {latest_q_start} to {latest_date_str} (3 months: April, May, June {latest_year}). January, February, and March {latest_year} data do NOT exist. If the user asked for '6 tháng đầu năm {latest_year}', 'H1 {latest_year}', 'nửa đầu năm', or any period that includes Jan-Mar {latest_year}, you MUST prominently warn the user in your response with this EXACT note at the beginning:
⚠️ <b>Lưu ý quan trọng về dữ liệu:</b> Hệ thống hiện chỉ có dữ liệu hóa đơn từ tháng 04/{latest_year} đến {latest_month}/{latest_year} (Q2/{latest_year}). Dữ liệu tháng 1, 2, 3 năm {latest_year} chưa được tải vào CSDL, do đó kết quả bên dưới chỉ phản ánh <b>3 tháng (Q2/{latest_year})</b>, KHÔNG phải 6 tháng đầu năm đầy đủ.
Then present the numbers clearly labeled as "Q2/{latest_year} (Tháng 4-{int(latest_month)})" not "6 tháng đầu năm".
"""
                try:
                    answer = self._call_ai(
                        model=self.summary_model,
                        system_prompt="You are a helpful assistant for data analysis.",
                        user_prompt=summary_prompt
                    )
                    # Convert any accidental markdown bold to HTML bold to ensure rendering
                    answer = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', answer)
                except Exception as e:
                    answer = self._format_heuristically(query_result.get("columns", []), query_result.get("rows", []), user_question)

        chart_path = None
        if not "error" in query_result and query_result.get("rows") and len(query_result["rows"]) >= 1:
            try:
                # 2. Run deterministic Rule Engine
                visual_type = "KPI_Card"
                metrics_count = len(parsed_intent.get("metrics", []))
                num_rows = len(query_result["rows"])
                columns_lower = [c.lower() for c in query_result.get("columns", [])]
                
                # Detect if data looks like a time series (has a month/date/time column)
                time_cols = [c for c in columns_lower if any(k in c for k in ['month', 'date', 'thang', 'ngay', 'week', 'quarter', 'year', 'sale_date', 'saledate', 'tu_ngay', 'time', 'period'])]
                
                # If there are no time columns in the results, it cannot be a Trend/time-series chart
                if not time_cols and intent_type == "Trend":
                    intent_type = "Comparison_Rank"
                
                if num_rows == 1:
                    # Single row → always KPI Card
                    visual_type = "KPI_Card"
                elif intent_type == "Trend" or time_cols:
                    # Time series data → Bar Chart (clearer than Line for few months)
                    if metrics_count <= 1:
                        visual_type = "Bar_Chart"
                    else:
                        visual_type = "Line_and_Stacked_Column_Chart"
                elif intent_type == "Single_Value" and num_rows >= 2:
                    # Multiple rows but LLM said Single_Value → it's actually a comparison
                    visual_type = "Horizontal_Bar_Chart"
                elif intent_type == "Composition":
                    visual_type = "Pie_Chart"
                elif intent_type == "Comparison_Rank":
                    visual_type = "Horizontal_Bar_Chart"
                elif intent_type == "Variance":
                    visual_type = "Waterfall_Chart"
                    
                print(f"[Rule Engine Visual Selection]: {visual_type}")
                
                # 3. Call rendering engine for the selected Visual_Type
                chart_path = self._render_visual(visual_type, query_result.get("columns", []), query_result.get("rows", []), user_question)
            except Exception as e:
                print(f"[Error generating chart via Rule Engine]: {e}")

        # Lưới an toàn: dù SQL sinh ra có quên ORDER BY/LIMIT 10 hay không, bảng hiển thị
        # cho người dùng vẫn không bao giờ vượt quá 10 dòng, trừ khi họ hỏi "toàn bộ".
        table_rows = query_result.get("rows", [])
        if not wants_full_list and len(table_rows) > 10:
            table_rows = table_rows[:10]

        if cloud_unreachable_fallback:
            answer = (
                "⚠️ <b>Không kết nối được CSDL chính (Supabase)</b> tại thời điểm này — câu trả lời dưới đây "
                "dùng dữ liệu offline dự phòng, có thể THIẾU bảng dữ liệu hoặc KHÔNG khớp với câu hỏi. "
                "Vui lòng kiểm tra kết nối mạng/DNS rồi thử lại để có số liệu chính xác.\n\n" + answer
            )

        result = {
            "question": user_question,
            "sql": sql_query,
            "data": table_rows,
            "columns": query_result.get("columns", []),
            "answer": answer,
            "chart_path": chart_path,
            "mode": f"Live {self.model_type.upper()} API" if not self.is_mock else "Offline Mock Engine"
        }
        self._remember_turn(session_key, user_question, result["answer"])
        return result

    def _format_heuristically(self, columns, rows, question):
        if not rows:
            return "Không tìm thấy dữ liệu phù hợp với yêu cầu của bạn."
            
        def fmt_money(val):
            if val is None:
                return "0 đ"
            try:
                val = float(val)
                if val >= 1_000_000_000:
                    return f"{val / 1_000_000_000:.2f} tỷ đ".replace('.', ',')
                elif val >= 1_000_000:
                    return f"{val / 1_000_000:.1f} triệu đ".replace('.', ',')
                else:
                    return f"{val:,.0f} đ".replace(',', '.')
            except:
                return str(val)
                
        def fmt_pct(val):
            if val is None:
                return "0%"
            try:
                val = float(val)
                # Check if it is a fraction (e.g. 0.85 -> 85%)
                if val <= 2.0:
                    val = val * 100
                return f"{val:.1f}%".replace('.', ',')
            except:
                return str(val)

        formatted_rows = []
        for r in rows:
            formatted_row = {}
            for col in columns:
                val = r.get(col)
                col_lower = col.lower()
                if any(k in col_lower for k in ['amount', 'revenue', 'target', 'value', 'balance', 'overdue', 'paid', 'receivable']):
                    formatted_row[col] = fmt_money(val)
                elif any(k in col_lower for k in ['percent', 'pct']):
                    formatted_row[col] = fmt_pct(val)
                else:
                    formatted_row[col] = str(val) if val is not None else ""
            formatted_rows.append(formatted_row)
            
        text = ""
        header_map = {
            'employee_name': 'Nhân viên',
            'employee_code': 'Mã NV',
            'customer_name': 'Khách hàng',
            'customer_code': 'Mã KH',
            'month_sale_target': 'Chỉ tiêu',
            'month_sale_amount': 'Thực đạt',
            'month_sale_percent': 'Tỷ lệ đạt',
            'total_overdue': 'Nợ quá hạn',
            'balance_end': 'Tổng nợ',
            'item_name': 'Sản phẩm',
            'closing_qty': 'Tồn kho',
            'months_to_sell': 'Tháng bán tồn',
            'otc_amount': 'Doanh thu OTC',
            'etc_amount': 'Doanh thu ETC',
            'total_amount': 'Tổng doanh số',
            'otc_percent': 'Tỷ lệ OTC',
            'etc_percent': 'Tỷ lệ ETC'
        }
        
        for idx, r in enumerate(formatted_rows):
            text += f"<b>Hồ sơ #{idx+1}:</b>\n"
            for col in columns:
                display_name = header_map.get(col, col)
                text += f"   • {display_name}: <b>{r[col]}</b>\n"
            text += "\n"
            
        return text

    def _parse_data_intent(self, user_question):
        """
        Fast heuristic visual intent parser (Bypasses LLM call to save 3+ seconds).
        Returns a dictionary containing:
        - intent: Single_Value, Trend, Composition, Comparison_Rank, Variance
        - metrics: list of strings
        - dimensions: list of strings
        - time_context: string
        - filter: string
        """
        q_lower = user_question.lower()
        intent = "Comparison_Rank"
        if any(k in q_lower for k in ["xu huong", "trend", "ngay", "thang", "tháng", "chu ky", "chu kỳ", "7 ngày", "thời gian", "lịch sử", "theo ngày", "theo tháng"]):
            intent = "Trend"
        elif any(k in q_lower for k in ["ty le", "tỷ lệ", "phan tram", "phần trăm", "co cau", "cơ cấu", "chiem", "chiếm", "tỷ trọng", "tỷ trọng"]):
            intent = "Composition"
        elif any(k in q_lower for k in ["tai sao", "tại sao", "bien dong", "biến động", "chenh lech", "chênh lệch"]):
            intent = "Variance"
            
        # Check if the question is querying a single value without breakdown or comparison
        breakdown_keywords = [
            "so sanh", "so sánh", "top", "hon", "hơn", "thap", "thấp", "cao", 
            "lon", "lớn", "nho", "nhỏ", "chia theo", "theo", "breakdown", 
            "phan bo", "phân bổ", "kênh", "kenh", "miền", "mien", "vùng", "vung",
            "nhân viên", "nhan vien", "tdv", "danh sách", "danh sach", "bảng"
        ]
        if not any(k in q_lower for k in breakdown_keywords):
            if intent != "Trend":
                intent = "Single_Value"
                
        return {
            "intent": intent,
            "metrics": ["doanh số"],
            "dimensions": [],
            "time_context": "",
            "filter": ""
        }

    def _render_visual(self, visual_type, columns, rows, question):
        if not rows or len(rows) == 0 or not columns:
            return None
            
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import uuid
        import numpy as np
        import seaborn as sns
        
        # Use seaborn styling
        sns.set_theme(style="whitegrid")
        matplotlib.rcParams['font.family'] = 'Segoe UI'
        matplotlib.rcParams['font.size'] = 10
        colors = ['#1a365d', '#319795', '#d69e2e', '#e53e3e', '#3182ce', '#38a169']
        
        # Unified identification of true metrics vs category/dimension columns
        numeric_cols = []
        cat_cols = []
        for col in columns:
            col_lower = col.lower()
            if any(k in col_lower for k in ['id', 'code', 'symbol', 'number', 'stt']):
                cat_cols.append(col)
                continue
                
            val = rows[0].get(col)
            if val is not None:
                try:
                    float(val)
                    numeric_cols.append(col)
                except (ValueError, TypeError):
                    cat_cols.append(col)
            else:
                cat_cols.append(col)
                
        if not numeric_cols:
            return None
            
        num_col = numeric_cols[0]
        cat_col = cat_cols[0] if cat_cols else columns[0]
        
        fig, ax = None, None
        
        if visual_type == "KPI_Card":
            metric_name = "Chỉ số"
            metric_value = "0"
            
            if cat_cols and numeric_cols:
                metric_name = str(rows[0].get(cat_cols[0], "Chỉ số"))
                num_val = float(rows[0].get(numeric_cols[0], 0))
                col_name_lower = numeric_cols[0].lower()
                if any(k in col_name_lower for k in ['amount', 'revenue', 'overdue', 'balance', 'paid', 'receivable']):
                    if num_val >= 1_000_000_000:
                        metric_value = f"{num_val*1e-9:.2f} tỷ đ".replace('.', ',')
                    elif num_val >= 1_000_000:
                        metric_value = f"{num_val*1e-6:.1f} triệu đ".replace('.', ',')
                    else:
                        metric_value = f"{num_val:,.0f} đ".replace(',', '.')
                elif any(k in col_name_lower for k in ['percent', 'pct', 'rate']):
                    if num_val <= 2.0:
                        metric_value = f"{num_val*100:.1f}%".replace('.', ',')
                    else:
                        metric_value = f"{num_val:.1f}%".replace('.', ',')
                else:
                    metric_value = f"{num_val:,.0f}".replace(',', '.')
            elif numeric_cols:
                metric_name = numeric_cols[0].replace('_', ' ').title()
                num_val = float(rows[0].get(numeric_cols[0], 0))
                col_name_lower = numeric_cols[0].lower()
                if any(k in col_name_lower for k in ['amount', 'revenue', 'overdue', 'balance', 'paid', 'receivable', 'sales']):
                    if num_val >= 1_000_000_000:
                        metric_value = f"{num_val*1e-9:.2f} tỷ đ".replace('.', ',')
                    elif num_val >= 1_000_000:
                        metric_value = f"{num_val*1e-6:.1f} triệu đ".replace('.', ',')
                    else:
                        metric_value = f"{num_val:,.0f} đ".replace(',', '.')
                else:
                    metric_value = f"{num_val:,.0f}".replace(',', '.')
                
            fig, ax = plt.subplots(figsize=(4, 2.5), dpi=150)
            fig.patch.set_facecolor('#f8f9fa')
            ax.set_facecolor('#f8f9fa')
            ax.axis('off')
            
            # Fix layering by adding the rectangle to the axis block with zorder=0
            rect = plt.Rectangle((0.02, 0.02), 0.96, 0.96, transform=fig.transFigure,
                                 facecolor='#ffffff', edgecolor='#e2e8f0', linewidth=1.5, zorder=0)
            ax.add_patch(rect)
            
            # Draw text with high zorder
            ax.text(0.5, 0.7, metric_name, fontsize=12, fontweight='bold', color='#4a5568', ha='center', va='center', zorder=5)
            ax.text(0.5, 0.4, metric_value, fontsize=20, fontweight='bold', color='#1a365d', ha='center', va='center', zorder=5)
            
            target_cols = [c for c in columns if 'target' in c.lower() or 'chi_tieu' in c.lower()]
            if target_cols and len(numeric_cols) > 1:
                t_val = float(rows[0].get(target_cols[0], 0) or 0)
                if t_val > 0:
                    pct = (num_val / t_val) * 100
                    ax.text(0.5, 0.18, f"Đạt {pct:.1f}% chỉ tiêu".replace('.', ','), fontsize=10, fontweight='bold', color='#38a169' if pct >= 100 else '#ff7f0e', ha='center', va='center', zorder=5)

        elif visual_type == "Line_Chart":
            plot_rows = rows[:15]
            labels = [str(r.get(cat_col, '')) for r in plot_rows]
            labels = [l[:25] + '...' if len(l) > 25 else l for l in labels]
            values = [float(r.get(num_col, 0) or 0) for r in plot_rows]
            
            fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
            sns.lineplot(x=labels, y=values, marker='o', linewidth=2.5, color='#3182ce', ax=ax, errorbar=None)
            ax.fill_between(labels, values, alpha=0.15, color='#3182ce')
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.set_title(f"Biểu đồ Xu hướng ({num_col.replace('_',' ').title()})", fontweight='bold', fontsize=12, pad=15)
            ax.grid(True, linestyle='--', alpha=0.5)

        elif visual_type == "Bar_Chart":
            plot_rows = rows[:12]
            # Try to find the category/time label column among actual columns
            _time_keywords = ['month', 'date', 'thang', 'ngay', 'week', 'quarter', 'year', 'sale_date', 'saledate', 'period', 'time']
            actual_label_col = next((c for c in columns if any(k in c.lower() for k in _time_keywords)), cat_col)
            raw_labels = [str(r.get(actual_label_col, '')) for r in plot_rows]
            # Format date labels nicely (e.g. 2026-04-01 00:00:00+00:00 → T4/2026)
            import re as _re
            formatted_labels = []
            for lbl in raw_labels:
                m = _re.match(r'(\d{4})-(\d{2})', str(lbl))
                if m:
                    formatted_labels.append(f"T{int(m.group(2))}/{m.group(1)}")
                else:
                    short = str(lbl)[:18]
                    formatted_labels.append(short + '...' if len(str(lbl)) > 18 else short)
            values = [float(r.get(num_col, 0) or 0) for r in plot_rows]
            max_val = max(values) if values else 1
            
            fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
            bar_colors = ['#e53e3e' if v == max_val else '#2b6cb0' for v in values]
            bars = ax.bar(range(len(formatted_labels)), values, color=bar_colors, edgecolor='white', linewidth=1.2, width=0.6)
            
            # Value labels on top of bars
            for bar, val in zip(bars, values):
                if val >= 1_000_000_000:
                    lbl_text = f"{val/1e9:.2f} tỷ".replace('.', ',')
                elif val >= 1_000_000:
                    lbl_text = f"{val/1e6:.1f}M".replace('.', ',')
                else:
                    lbl_text = f"{val:,.0f}"
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max_val * 0.015,
                        lbl_text, ha='center', va='bottom', fontsize=9, fontweight='bold', color='#2d3748')
            
            ax.set_xticks(range(len(formatted_labels)))
            ax.set_xticklabels(formatted_labels, rotation=30, ha='right', fontsize=10)
            ax.set_title(f"Doanh thu theo thời gian", fontweight='bold', fontsize=12, pad=15)
            ax.grid(True, linestyle='--', alpha=0.4, axis='y')
            ax.set_axisbelow(True)

        elif visual_type == "Line_and_Stacked_Column_Chart":
            if len(numeric_cols) < 2:
                return None
                
            plot_rows = rows[:15]
            if len(cat_cols) > 1:
                labels = [" - ".join([str(r.get(c, '')) for c in cat_cols if r.get(c) is not None]) for r in plot_rows]
            else:
                labels = [str(r.get(cat_col, '')) for r in plot_rows]
            labels = [l[:25] + '...' if len(l) > 25 else l for l in labels]
            
            fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
            x = np.arange(len(labels))
            width = 0.35
            
            col1 = numeric_cols[0]
            col2 = numeric_cols[1]
            val1 = [float(r.get(col1, 0) or 0) for r in plot_rows]
            val2 = [float(r.get(col2, 0) or 0) for r in plot_rows]
            
            ax.bar(x - width/2, val1, width, label=col1.replace('_',' ').title(), color='#3182ce', alpha=0.9, edgecolor='white')
            ax.bar(x + width/2, val2, width, label=col2.replace('_',' ').title(), color='#38a169', alpha=0.9, edgecolor='white')
            
            if len(numeric_cols) >= 3:
                col3 = numeric_cols[2]
                val3 = [float(r.get(col3, 0) or 0) for r in plot_rows]
                if any(v <= 2.0 for v in val3):
                    val3 = [v * 100 for v in val3]
                ax2 = ax.twinx()
                ax2.plot(x, val3, color='#e53e3e', marker='s', linewidth=2.5, label=col3.replace('_',' ').title())
                ax2.set_ylabel(f"{col3.replace('_',' ').title()} (%)")
                ax2.grid(False)
                
                lines, labels_l = ax.get_legend_handles_labels()
                lines2, labels_l2 = ax2.get_legend_handles_labels()
                ax.legend(lines + lines2, labels_l + labels_l2, loc='upper left')
            else:
                ax.legend(loc='upper left')
                
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.set_title(f"So sánh Đa chỉ số theo {cat_col.replace('_',' ').title()}", fontweight='bold', fontsize=12, pad=15)

        elif visual_type == "Pie_Chart":
            plot_rows = rows[:15]
            if len(cat_cols) > 1:
                labels = [" - ".join([str(r.get(c, '')) for c in cat_cols if r.get(c) is not None]) for r in plot_rows]
            else:
                labels = [str(r.get(cat_col, '')) for r in plot_rows]
            values = [float(r.get(num_col, 0) or 0) for r in plot_rows]
            
            pie_data = [(l, v) for l, v in zip(labels, values) if v > 0]
            
            fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
            if pie_data:
                p_labels, p_values = zip(*pie_data)
                pie_colors = sns.color_palette("muted", len(p_labels))
                ax.pie(p_values, labels=p_labels, autopct='%1.1f%%', startangle=90, colors=pie_colors, 
                       wedgeprops={'edgecolor': 'white', 'linewidth': 1.5})
                ax.axis('equal')
                ax.set_title(f"Cơ cấu tỷ lệ ({num_col.replace('_',' ').title()})", fontweight='bold', fontsize=12, pad=15)
            else:
                sns.barplot(x=labels, y=values, color='#3182ce', alpha=0.9, ax=ax)
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha='right')

        elif visual_type == "Horizontal_Bar_Chart":
            sorted_rows = sorted(rows, key=lambda x: float(x.get(num_col, 0) or 0), reverse=True)[:15]
            if len(cat_cols) > 1:
                labels = [" - ".join([str(r.get(c, '')) for c in cat_cols if r.get(c) is not None]) for r in sorted_rows]
            else:
                labels = [str(r.get(cat_col, '')) for r in sorted_rows]
            labels = [l[:25] + '...' if len(l) > 25 else l for l in labels]
            values = [float(r.get(num_col, 0) or 0) for r in sorted_rows]
            max_val = max(values) if values else 1
            
            fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
            # Use corporate blue for standard bars, highlight maximum bar in red
            bar_colors = ['#e53e3e' if v == max_val else '#2b6cb0' for v in values]
            bars = ax.barh(range(len(labels)), values, color=bar_colors, edgecolor='white', height=0.6)
            
            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels, fontsize=10, fontweight='bold', color='#2d3748')
            ax.invert_yaxis()  # Top-down ranking
            
            # Value labels at the end of bars
            for bar, val in zip(bars, values):
                if val >= 1_000_000_000:
                    lbl_text = f" {val/1e9:.2f} tỷ".replace('.', ',')
                elif val >= 1_000_000:
                    lbl_text = f" {val/1e6:.1f}M".replace('.', ',')
                else:
                    lbl_text = f" {val:,.0f}"
                ax.text(bar.get_width() + max_val * 0.015, bar.get_y() + bar.get_height()/2,
                        lbl_text, ha='left', va='center', fontsize=9, fontweight='bold', color='#2d3748')
            
            ax.set_title(f"Bảng xếp hạng ({num_col.replace('_',' ').title()})", fontweight='bold', fontsize=12, pad=15)
            ax.grid(True, linestyle='--', alpha=0.4, axis='x')
            ax.set_axisbelow(True)

        elif visual_type == "Waterfall_Chart":
            plot_rows = rows[:10]
            labels = [str(r.get(cat_col, '')) for r in plot_rows]
            labels = [l[:20] + '...' if len(l) > 20 else l for l in labels]
            values = [float(r.get(num_col, 0) or 0) for r in plot_rows]
            
            cumulative = np.cumsum(values)
            starts = np.zeros_like(values)
            starts[1:] = cumulative[:-1]
            
            fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
            bar_colors = ['#38a169' if v >= 0 else '#e53e3e' for v in values]
            
            ax.bar(labels, values, bottom=starts, color=bar_colors, edgecolor='white', alpha=0.9)
            
            for i in range(len(values) - 1):
                ax.plot([i, i+1], [cumulative[i], cumulative[i]], color='#a0aec0', linestyle='--', linewidth=1.2)
                
            if len(values) > 1:
                labels.append("Tổng Net")
                net_val = cumulative[-1]
                ax.bar(["Tổng Net"], [net_val], color='#3182ce', edgecolor='white', alpha=0.95)
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha='right')
            else:
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha='right')
                
            ax.set_title(f"Biến động Lũy kế ({num_col.replace('_',' ').title()})", fontweight='bold', fontsize=12, pad=15)

        if ax is not None:
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            
            def format_y_ticks(x, pos):
                if abs(x) >= 1_000_000_000:
                    return f'{x*1e-9:.1f}B'
                elif abs(x) >= 1_000_000:
                    return f'{x*1e-6:.1f}M'
                elif abs(x) >= 1_000:
                    return f'{x*1e-3:.1f}K'
                return str(x)
                
            if visual_type != "Pie_Chart" and visual_type != "KPI_Card":
                from matplotlib.ticker import FuncFormatter
                if visual_type == "Horizontal_Bar_Chart":
                    ax.xaxis.set_major_formatter(FuncFormatter(format_y_ticks))
                else:
                    ax.yaxis.set_major_formatter(FuncFormatter(format_y_ticks))
                    
            plt.tight_layout()
            
            os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scratch"), exist_ok=True)
            filename = f"chart_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scratch", filename)
            plt.savefig(filepath, format='png', dpi=150)
            plt.close()
            return filepath
            
        return None

if __name__ == "__main__":
    chatbot = DNHChatbot()
    # Test chitchat
    res = chatbot.ask("xin chào")
    print("General response:\n", res["answer"])
    print("-" * 50)
    # Test reasoning why/how
    res_why = chatbot.ask("tại sao công nợ của công ty lại cao?")
    print("Why/How response:\n", res_why["answer"])
    print("-" * 50)
    # Test data query
    res_data = chatbot.ask("Cho tôi biết doanh thu mien bac")
    print("Data response:\n", res_data["answer"])

