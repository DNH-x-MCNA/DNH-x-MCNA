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
        connect_args={'connect_timeout': 10}  # đo thật: handshake tới pooler mất ~2.3-2.9s ngay
                                               # cả khi rảnh (compute tier yếu) -> 3s cũ gần như
                                               # luôn timeout khi có thêm tải, 10s mới có biên an toàn
    )
    _cloud_engine_url = db_url
    return _cloud_engine

# Helper to get the database schema dynamically — cached theo process (giống _cloud_engine)
# vì schema hầu như không đổi giữa các câu hỏi, nhưng trước đây bị fetch lại MỖI câu hỏi (~3.25s
# đo thật mỗi lần), chiếm phần đáng kể trong tổng thời gian trả lời chatbot.
# Cache theo TỪNG dialect riêng (dict) — trước đây chỉ 1 cache dùng chung, có thể trả nhầm schema
# Postgres cho 1 câu hỏi đang chạy trên Bravo (hoặc ngược lại) nếu nguồn đổi giữa 2 lần hỏi.
_schema_cache = {}
_schema_cache_time = {}
_SCHEMA_CACHE_TTL_SECONDS = 300  # 5 phút — đủ mới, không cần fetch lại mỗi câu hỏi

# CHÍNH XÁC LÀ 99 bảng thật sự tồn tại trên Bravo (đã quét lại toàn bộ INFORMATION_SCHEMA.TABLES
# 09/07/2026, sửa nhận định SAI trước đó nói chỉ có 12 bảng/thiếu công nợ-tồn kho-KPI). Danh sách
# dưới đây chỉ là các bảng ĐÃ ĐƯỢC DẠY cho chatbot dùng (không phải toàn bộ 99 bảng có trên Bravo) —
# mở rộng dần khi có nhu cầu + đã verify kỹ logic nghiệp vụ, tránh AI tự bịa cách dùng bảng lạ.
# brv_httdudk/brvsx_httdudk + brv_khachhang/brvsx_khachhang (công nợ, thêm 09/07/2026) — xem
# mart_layer_instruction nhánh active_backend=="bravo" để biết công thức tính đã kiểm chứng.
# receivable_detail/inventory/kpi_summary/fact_tonghopkhachhang bên Supabase KHÔNG phải sync tự
# động từ Bravo mỗi loại như nhau: fact_tonghopkhachhang LÀ 1-1 sync thật từ FACT_TongHopKhachHang
# (có thể dùng thẳng, CHƯA làm trong lượt này); receivable_detail/inventory/kpi_summary lại là
# import 1 LẦN từ Excel DNH gửi đầu dự án (KHÔNG tự động, đã cũ ~6 tháng) — không phải nguồn Bravo
# thiếu, mà do chưa xây transformation logic tương đương trên Bravo cho 2 mảng còn lại (tồn kho/KPI).
_BRAVO_TABLES = (
    'brv_hoadonhdr', 'brv_hoadonct', 'brvsx_hoadonhdr', 'brvsx_hoadonct',
    'brv_trangthaihoadon', 'brv_trangthaiduyet', 'dms_khachhang', 'dmssx_khachhang',
    'dim_tinhthanhpho', 'dim_nhanvien', 'brv_sanpham', 'brvsx_tralai',
    'brv_httdudk', 'brvsx_httdudk', 'brv_khachhang', 'brvsx_khachhang',
)

def get_db_schema(dialect="postgres"):
    """dialect: "postgres" (Supabase, mặc định — giữ nguyên hành vi cũ) / "bravo" (SQL Server trực
    tiếp) / "sqlite" (local, không cần fetch động — xử lý y hệt nhánh cuối như trước)."""
    now_ts = __import__("time").time()
    if dialect in _schema_cache and (now_ts - _schema_cache_time.get(dialect, 0)) < _SCHEMA_CACHE_TTL_SECONDS:
        return _schema_cache[dialect]

    if dialect == "bravo":
        from src.database import _get_bravo_engine
        engine = _get_bravo_engine()
        if engine is not None:
            try:
                from sqlalchemy import text, bindparam
                with engine.connect() as conn:
                    # Bravo đặt tên bảng khác case với Postgres (vd "BRV_HoaDonHdr" vs
                    # "brv_hoadonhdr") — so khớp không phân biệt hoa/thường bằng LOWER().
                    query = text("""
                        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_SCHEMA = 'dbo' AND LOWER(TABLE_NAME) IN :tables
                        ORDER BY TABLE_NAME, ORDINAL_POSITION
                    """).bindparams(bindparam("tables", expanding=True))
                    cols = conn.execute(query, {"tables": _BRAVO_TABLES}).fetchall()
                    schema_dict = {}
                    for r in cols:
                        schema_dict.setdefault(r[0], []).append(f"{r[1]} ({r[2]})")
                    schema_text = "Dược Nam Hà central database schema (Bravo SQL Server — nguồn chính, có công nợ, KHÔNG có tồn kho/KPI):\n"
                    for t, cols_str in schema_dict.items():
                        schema_text += f"- Table '{t}': Columns are {', '.join(cols_str)}\n"
                    _schema_cache["bravo"], _schema_cache_time["bravo"] = schema_text, now_ts
                    return schema_text
            except Exception as e:
                print(f"[Warning] Failed to fetch schema from Bravo: {e}. Falling back to SQLite...")
        # Bravo không dùng được -> rơi thẳng xuống nhánh SQLite ở cuối hàm (dùng chung code).

    elif dialect == "postgres":
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

                    # mart_layer.mart_revenue_summary — bảng riêng schema khác (không phải 'public'),
                    # query info_schema tự trả về RỖNG nếu schema/bảng chưa tồn tại (không lỗi), nên
                    # an toàn khi chưa chạy DDL tạo mart layer. Khi bảng thật sự tồn tại, tên hiển thị
                    # có tiền tố schema để LLM biết viết đúng "mart_layer.mart_revenue_summary".
                    mart_cols = conn.execute(text("""
                        SELECT column_name, data_type FROM information_schema.columns
                        WHERE table_schema = 'mart_layer' AND table_name = 'mart_revenue_summary'
                        ORDER BY ordinal_position
                    """)).fetchall()
                    if mart_cols:
                        schema_dict["mart_layer.mart_revenue_summary"] = [f"{r[0]} ({r[1]})" for r in mart_cols]

                    schema_text = "Dược Nam Hà central database schema:\n"
                    for t, cols_str in schema_dict.items():
                        schema_text += f"- Table '{t}': Columns are {', '.join(cols_str)}\n"
                    _schema_cache["postgres"], _schema_cache_time["postgres"] = schema_text, now_ts
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
    _schema_cache["sqlite"], _schema_cache_time["sqlite"] = schema_text, now_ts
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

# --- Chart styling helpers (bảng màu brand DNH + format tiền/số tiếng Việt) ---
_CHART_GREEN = '#337337'
_CHART_ORANGE = '#f15a25'
_CHART_RED = '#c0392b'
_CHART_SLATE = '#5b6b78'
_CHART_TEAL = '#2f7e7a'
_CHART_GOLD = '#c99a2e'
_CHART_INK = '#26332e'
_CHART_GRID = '#d8e0da'
_CHART_PALETTE = [_CHART_GREEN, _CHART_ORANGE, _CHART_TEAL, _CHART_SLATE, _CHART_GOLD, '#8e6fb0']

_MONEY_HINTS = ['amount', 'revenue', 'overdue', 'balance', 'paid', 'receivable', 'sales', 'budget',
                'target', 'doanh thu', 'doanh số', 'doanh so', 'nợ', 'công nợ', 'cong no', 'giá trị',
                'gia tri', 'tiền', 'tien', 'chỉ tiêu', 'chi tieu', 'thực đạt', 'thuc dat', 'dư nợ',
                'du no', 'thanh toán', 'thanh toan']
_BAD_HINTS = ['nợ', 'quá hạn', 'qua han', 'overdue', 'giảm', 'giam', 'chậm', 'cham', 'trả', 'debt',
              'thiếu', 'thieu']

def _is_money_col(name):
    return any(h in (name or '').lower() for h in _MONEY_HINTS)

def _is_bad_col(name):
    return any(h in (name or '').lower() for h in _BAD_HINTS)

def _fmt_time_label(lbl):
    """'2026-06-01' -> 'T6/2026' (đầu tháng); '2026-06-22' -> '22/06' (tuần/ngày); khác giữ nguyên."""
    import re as _re
    s = str(lbl)
    m = _re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        return f"T{mo}/{y}" if d == 1 else f"{d:02d}/{mo:02d}"
    m = _re.match(r'(\d{4})-(\d{2})', s)
    if m:
        return f"T{int(m.group(2))}/{m.group(1)}"
    return s if len(s) <= 18 else s[:18] + '...'


def _fmt_time_labels(seq):
    """Format cả dãy nhãn thời gian nhất quán: nếu dãy là ngày đầy đủ và KHÔNG phải toàn
    mùng 1 (dữ liệu tuần/ngày) thì tất cả dùng dd/mm — tránh lẫn 'T6/2026' giữa '08/06'."""
    import re as _re
    vals = [str(s) for s in seq]
    ms = [_re.match(r'(\d{4})-(\d{2})-(\d{2})', v) for v in vals]
    if vals and all(ms) and any(int(m.group(3)) != 1 for m in ms):
        return [f"{int(m.group(3)):02d}/{int(m.group(2)):02d}" for m in ms]
    return [_fmt_time_label(v) for v in vals]


def _fmt_chart_val(v, is_money=True):
    """Format 1 giá trị cho chart: tiền -> tỷ/tr/đ; số đếm -> tỷ/M/K. Dấu thập phân kiểu VN (phẩy)."""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return str(v)
    a = abs(v)
    if is_money:
        if a >= 1e9:   s = f"{v/1e9:.2f} tỷ"
        elif a >= 1e6: s = f"{v/1e6:.0f} tr"
        elif a >= 1e3: s = f"{v/1e3:.0f}K"
        else:          s = f"{v:.0f} đ"
    else:
        if a >= 1e9:   s = f"{v/1e9:.2f} tỷ"
        elif a >= 1e6: s = f"{v/1e6:.1f}M"
        elif a >= 1e3: s = f"{v/1e3:.1f}K"
        else:          s = f"{v:.0f}"
    return s.replace('.', ',')

class DNHChatbot:
    def __init__(self):
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

        if self.anthropic_key:
            self.client = anthropic.Anthropic(api_key=self.anthropic_key)
            self.is_mock = False
            self.model_type = "claude"
            # Opus 4.8 là bậc lớn/chậm/đắt nhất — không hợp cho việc sinh SQL + tóm tắt lặp lại
            # mỗi câu hỏi (mục tiêu hiện tại là GIẢM độ trễ). Sonnet 5 cân bằng tốc độ/chất lượng
            # tốt hơn nhiều cho việc này, vẫn đủ mạnh để đọc schema nhiều bảng + luật nghiệp vụ.
            self.sql_model = "claude-sonnet-5"
            self.summary_model = "claude-sonnet-5"
            print("[Info] Running in Live Claude Mode (claude-sonnet-5).")
        elif self.gemini_key:
            self.client = None
            self.is_mock = False
            self.model_type = "gemini"
            # "gemini-2.0-flash" bị Google gỡ (404 "no longer available") dù vẫn hiện trong
            # ListModels — theo yêu cầu, dùng đích danh "gemini-3.5-flash" (đã test gọi thật
            # thành công 08/07/2026). Nếu sau này bản này cũng bị gỡ, kiểm tra lại bằng
            # scratch/list_gemini_models.py + gọi thử generateContent thật trước khi đổi tiếp —
            # KHÔNG chỉ tin ListModels vì đã có tiền lệ model hiện trong danh sách vẫn 404.
            self.sql_model = "gemini-3.5-flash"
            self.summary_model = "gemini-3.5-flash"
            print("[Info] Running in Live Gemini Mode (gemini-3.5-flash).")
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
        # Cache tương tự cho Bravo SQL Server trực tiếp — dùng khi Supabase (cloud) không kết nối
        # được (xem property bravo_available bên dưới, cạnh cloud_available).
        self._last_bravo_check = 0.0
        self._bravo_available_cached = False
        # Circuit breaker: cloud_available chỉ chạy "SELECT 1 FROM brv_hoadonhdr LIMIT 1" (rất nhẹ)
        # nên có thể báo "khoẻ" dù Supabase đang timeout với query THẬT nặng hơn (đã xác nhận thực
        # tế 09/07/2026: cloud_available trả True, sinh SQL Postgres, chạy timeout thật, rơi xuống
        # SQLite thay vì Bravo vì lúc quyết định dialect đã lỡ chọn Postgres). Khi _execute_sql()
        # thấy Postgres THẬT SỰ lỗi lúc chạy câu SQL, ghi mốc này để các câu hỏi SAU trong cùng
        # request/phiên bỏ qua Postgres, đi thẳng Bravo — không đợi timeout lặp lại vô ích.
        self._postgres_query_down_until = 0.0

        # Cache kết quả DATA_QUERY (SQL sinh + data + answer) — tránh gọi lại LLM + query DB cho
        # câu hỏi giống hệt hỏi lại trong vài phút (vd nhiều người cùng hỏi "doanh thu otc tháng 6"
        # trong 1 buổi họp). Key PHẢI gồm scope_region/scope_channel — 2 user khác quyền hỏi CÙNG
        # câu chữ vẫn phải ra 2 SQL/kết quả khác nhau (RBAC), tuyệt đối không dùng chung 1 entry.
        # CHỈ cache/CHỈ đọc cache khi history_block rỗng (câu hỏi KHÔNG phải follow-up dựa vào hội
        # thoại trước) — 1 câu hỏi giống hệt có thể mang nghĩa khác hẳn tuỳ ngữ cảnh hội thoại
        # trước đó (vd "còn quý trước thì sao"), cache theo đúng chữ mà bỏ qua ngữ cảnh sẽ SAI.
        self._query_cache = {}
        self._QUERY_CACHE_TTL_SECONDS = 300

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
                # brv_hoadonhdr luôn có mặt (production lẫn dev) — "regions" là bảng của pipeline
                # mock cũ (scripts/init_db.py), không thuộc schema thật brv_*/dms_* nên không dùng
                # để health-check nữa (trước đây luôn fail khi CLOUD_DB_URL trỏ sang dev).
                conn.execute(text("SELECT 1 FROM brv_hoadonhdr LIMIT 1"))
                self._cloud_available_cached = True
                return True
        except Exception as e:
            self._cloud_available_cached = False
            # Print warning on transition to False or first check
            print(f"[Warning] Postgres Cloud DB check failed: {e}. Bot will use SQLite fallback if query fails.")
            return False

    @property
    def bravo_available(self):
        """
        Dynamic cached property (cooldown 15s) kiểm tra Bravo SQL Server trực tiếp có dùng được
        không — CHỈ có ý nghĩa khi chạy trên máy có VPN/LAN vào 172.16.0.26 (không áp dụng cho bản
        deploy Vercel — đã ngừng dùng, xem _resolve_active_backend()). Kể từ 09/07/2026, Bravo là
        NGUỒN CHÍNH (không còn là dự phòng): nhanh hơn, ổn định hơn Supabase/PgBouncer (đã lặp lại
        sự cố statement_timeout bị bỏ qua), truy vấn trực tiếp không qua tầng đồng bộ trung gian.
        Postgres/Supabase chỉ còn dùng khi máy chạy KHÔNG có LAN/VPN tới Bravo.
        """
        import time as _time
        now = _time.time()
        if now - self._last_bravo_check < 15:
            return self._bravo_available_cached

        self._last_bravo_check = now
        from src.database import _get_bravo_engine
        engine = _get_bravo_engine()
        if engine is None:
            self._bravo_available_cached = False
            return False

        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT TOP 1 1 FROM brv_hoadonhdr"))
                self._bravo_available_cached = True
                return True
        except Exception as e:
            self._bravo_available_cached = False
            print(f"[Warning] Bravo SQL Server check failed: {e}.")
            return False

    def _resolve_active_backend(self):
        """
        Chọn nguồn dữ liệu THẬT SỰ dùng cho câu hỏi này — tính 1 LẦN DUY NHẤT, dùng xuyên suốt cho
        get_db_schema()/db_dialect/_execute_sql()/banner cảnh báo, tránh tình trạng mỗi nơi tự đoán
        lại độc lập (trước đây get_db_schema() và khối chọn db_dialect tự thử/catch riêng, có thể
        ra kết quả lệch nhau giữa 2 lần gọi).
        Trả "postgres" / "bravo" / "sqlite". self.is_mock luôn ưu tiên trước (không đổi hành vi cũ).

        09/07/2026: đảo ưu tiên — BRAVO LÀ MẶC ĐỊNH khi máy đang chạy có LAN/VPN tới (172.16.0.26),
        không còn thử Postgres/Supabase trước nữa. Lý do: Supabase (qua PgBouncer) liên tục chậm/
        lỗi trong ngày (statement_timeout bị pooler bỏ qua, có lúc mất ~2 phút/câu hỏi dù đã giới
        hạn client-side 15s ở _execute_sql), trong khi Bravo là nguồn trực tiếp, nhanh, ổn định.
        Postgres/Supabase giờ CHỈ còn là dự phòng khi Bravo không với tới được (vd chạy trên máy
        không có LAN/VPN — trường hợp Vercel cũ, đã ngừng dùng). Đánh đổi: các câu hỏi công nợ/tồn
        kho/KPI (chỉ có trên Supabase, xem kpi_tdv_instruction/mart_layer_instruction) sẽ LUÔN bị
        từ chối lịch sự khi Bravo khả dụng, kể cả khi Supabase lúc đó thực ra vẫn khoẻ — chấp nhận
        được vì Supabase đã không ổn định phần lớn thời gian hôm nay.

        DB_DIALECT=mssql (.env) vẫn giữ để ép cứng "bravo" khi cần test, không đổi hành vi.
        """
        import time as _time
        if self.is_mock:
            return "sqlite"
        if os.getenv("DB_DIALECT", "").lower() == "mssql":
            return "bravo" if self.bravo_available else "sqlite"
        if self.bravo_available:
            return "bravo"
        # Bravo không với tới được lúc này (hiếm, vd đứt LAN/VPN) — thử Postgres, vẫn tôn trọng
        # circuit breaker nếu Postgres vừa mới lỗi thật (đặt bởi _execute_sql), tránh lặp lại lỗi.
        if _time.time() < self._postgres_query_down_until:
            return "sqlite"
        if self.cloud_available:
            return "postgres"
        return "sqlite"

    def _get_latest_dates(self, backend="postgres"):
        """Retrieves the earliest/latest invoice date, month-end date, and receivable period
        dynamically. earliest_date dùng để tự động cảnh báo đúng "dữ liệu bắt đầu từ tháng nào"
        thay vì hard-code — đã bắt được 1 case thật: rule cũ hard-code "chỉ có Q2 (T4-T6)" trong
        khi dữ liệu thật đã có đủ từ tháng 1, khiến chatbot báo sai với người dùng.
        backend="bravo": chỉ lấy earliest/latest_date (brv_hoadonhdr có trên Bravo) — bỏ qua
        fact_tonghopkhachhang/receivable_detail (KHÔNG tồn tại trên Bravo), latest_month_end/
        latest_period giữ mặc định (vô hại vì system prompt đã chặn AI dùng 2 bảng đó khi ở Bravo,
        xem kpi_tdv_instruction/mart_layer_instruction nhánh active_backend=="bravo")."""
        earliest_date = "2026-01-01"
        latest_date = "2026-06-30"
        latest_month_end = "2026-06-30"
        latest_period = "1_2026"

        if backend == "bravo":
            from src.database import _get_bravo_engine
            engine = _get_bravo_engine()
            if engine is not None and self.bravo_available:
                try:
                    from sqlalchemy import text
                    with engine.connect() as conn:
                        row1 = conn.execute(text('SELECT MIN([DocDate]), MAX([DocDate]) FROM brv_hoadonhdr WHERE [IsActive] = 1')).fetchone()
                        if row1 and row1[0]:
                            earliest_date = str(row1[0]).split(' ')[0].split('T')[0]
                        if row1 and row1[1]:
                            latest_date = str(row1[1]).split(' ')[0].split('T')[0]
                except Exception as e:
                    print(f"[Warning] Failed to fetch earliest/latest DocDate from Bravo: {e}")
            return earliest_date, latest_date, latest_month_end, latest_period

        engine = _get_cloud_engine()
        if engine is not None and not self.is_mock and self.cloud_available:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    # 3 truy vấn tự try/except RIÊNG — 1 bảng thiếu (vd fact_tonghopkhachhang
                    # chưa có ở dev, xem GHI CHÚ ở system prompt sinh SQL) không được làm mất
                    # luôn 2 giá trị còn lại (trước đây cả 3 chung 1 try nên 1 lỗi -> mất sạch,
                    # rồi còn rơi tiếp xuống SQLite fallback vốn cũng luôn lỗi -> tốn thời gian
                    # vô ích trên MỌI câu hỏi).
                    try:
                        row1 = conn.execute(text('SELECT MIN("DocDate"), MAX("DocDate") FROM brv_hoadonhdr WHERE "IsActive" = TRUE')).fetchone()
                        if row1 and row1[0]:
                            earliest_date = str(row1[0]).split(' ')[0].split('T')[0]
                        if row1 and row1[1]:
                            latest_date = str(row1[1]).split(' ')[0].split('T')[0]
                    except Exception as e:
                        print(f"[Warning] Failed to fetch earliest/latest DocDate: {e}")
                        conn.rollback()

                    try:
                        row2 = conn.execute(text('SELECT MAX("SaveDate") FROM fact_tonghopkhachhang')).fetchone()
                        if row2 and row2[0]:
                            latest_month_end = str(row2[0]).split(' ')[0].split('T')[0]
                    except Exception:
                        # fact_tonghopkhachhang chưa có ở dev (bảng thuộc mart đầy đủ ở production) -> giữ mặc định.
                        # BẮT BUỘC rollback: Postgres coi transaction đã "aborted" sau lỗi này, câu SAU trên
                        # CÙNG connection sẽ bị từ chối luôn dù bản thân nó đúng, nếu không rollback trước.
                        conn.rollback()

                    # Get max Period from receivable_detail. 'period' là TEXT 'M_YYYY'
                    # (không đệm số 0), nên MAX() SQL thường sẽ sort theo lexicographic và
                    # chọn nhầm vd '9_2025' thay vì '1_2026' (ký tự '9' > '1'). Phải lấy hết
                    # rồi tự chọn true (year, month) max trong Python.
                    try:
                        periods = [r[0] for r in conn.execute(text("SELECT DISTINCT period FROM receivable_detail")).fetchall() if r[0]]
                        if periods:
                            latest_period = max(periods, key=_latest_period_key)
                    except Exception as e:
                        print(f"[Warning] Failed to fetch latest period: {e}")

                return earliest_date, latest_date, latest_month_end, latest_period
            except Exception as e:
                print(f"[Warning] Failed to connect to cloud DB for max dates: {e}")

        # Try local SQLite fallback — chỉ chạy khi cloud KHÔNG dùng được ở mức kết nối (engine
        # None/is_mock/cloud_available=False), không còn bị kích hoạt chỉ vì 1 bảng phụ thiếu.
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('SELECT MIN(DocDate), MAX(DocDate) FROM brv_hoadonhdr WHERE IsActive = 1')
                r1 = cursor.fetchone()
                if r1 and r1[0]:
                    earliest_date = str(r1[0]).split(' ')[0].split('T')[0]
                if r1 and r1[1]:
                    latest_date = str(r1[1]).split(' ')[0].split('T')[0]
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

        return earliest_date, latest_date, latest_month_end, latest_period

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
        # 60s (không phải 30s cũ) — đo thật: SQL-gen với prompt ~7200 ký tự thường mất ~10s
        # nhưng có lúc vượt 30s (đã bắt được 1 lần timeout thật gây rơi về mock giữa hội thoại
        # có ngữ cảnh) — 60s cho biên an toàn hơn nhiều so với độ trễ thực tế quan sát được.
        with urllib.request.urlopen(req, timeout=60) as response:
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



    def _execute_sql(self, sql_query, target="postgres"):
        """Executes SQL query safely on the intermediate database (Postgres Cloud, Bravo SQL Server,
        or SQLite Local). target: "postgres" (mặc định, giữ nguyên hành vi cũ) / "bravo" / "sqlite"
        — phải khớp với dialect câu SQL ĐÃ ĐƯỢC SINH RA (xem _resolve_active_backend trong ask()),
        không tự ý thử nguồn khác dialect vì cú pháp không tương thích (TOP vs LIMIT, =1 vs TRUE...)."""
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

        upstream_error = None

        if target == "postgres":
            # Dùng engine "fast" (connect_timeout=5s — xem src/database.py::_get_fast_cloud_engine)
            # CỘNG THÊM giới hạn thời gian PHÍA CLIENT (concurrent.futures, KHÔNG dựa vào
            # statement_timeout server-side) — xác nhận thực tế 09/07/2026 trên máy 24:
            # statement_timeout gửi qua connection "options" bị Supabase PgBouncer (connection
            # pooler) BỎ QUA, khiến câu lệnh vẫn chạy chậm y hệt cũ (~2 phút) dù đã đặt giới hạn.
            # Tự đếm giờ ở client là cách DUY NHẤT đảm bảo bail đúng hạn bất kể server/pooler có
            # tôn trọng giới hạn hay không.
            from src.database import _get_fast_cloud_engine
            engine = _get_fast_cloud_engine()
            if engine is not None and not self.is_mock:
                def _run_pg_query():
                    from sqlalchemy import text
                    with engine.connect() as conn:
                        result = conn.execute(text(sql_query))
                        if result.returns_rows:
                            columns = list(result.keys())
                            formatted_rows = [dict(row._mapping) for row in result.fetchall()]
                            return {"columns": columns, "rows": formatted_rows, "count": len(formatted_rows)}
                        return {"columns": [], "rows": [], "count": 0}

                import concurrent.futures
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = executor.submit(_run_pg_query)
                try:
                    result = future.result(timeout=15)
                    executor.shutdown(wait=False)
                    return result
                except concurrent.futures.TimeoutError:
                    executor.shutdown(wait=False)  # KHÔNG đợi thread bị bỏ dở — tiến ngay xuống fallback
                    upstream_error = "Client-side timeout sau 15s (Supabase/PgBouncer không tôn trọng statement_timeout server-side)"
                    import time as _time
                    self._postgres_query_down_until = _time.time() + 120
                    print(f"[Warning] Resilient Chatbot: Postgres Cloud query {upstream_error}. "
                          f"Ghi nhận Postgres lỗi trong 120s tới (câu hỏi sau sẽ ưu tiên Bravo). Falling back to SQLite...")
                except Exception as e:
                    executor.shutdown(wait=False)
                    upstream_error = str(e)
                    import time as _time
                    self._postgres_query_down_until = _time.time() + 120
                    print(f"[Warning] Resilient Chatbot: Postgres Cloud query failed ({upstream_error}). "
                          f"Ghi nhận Postgres lỗi trong 120s tới (câu hỏi sau sẽ ưu tiên Bravo). Falling back to SQLite...")

        elif target == "bravo":
            # KHÔNG thử Postgres trước — sql_query đã được sinh bằng cú pháp T-SQL ngay từ đầu
            # (xem _resolve_active_backend/db_dialect trong ask()), thử lại Postgres chỉ tổ lỗi cú
            # pháp (TOP thay vì LIMIT, "col"=1 thay vì TRUE...).
            from src.database import _get_bravo_engine
            engine = _get_bravo_engine()
            if engine is not None and not self.is_mock and self.bravo_available:
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
                    upstream_error = str(e)
                    # "Invalid object name" = bảng không tồn tại — gần như chắc chắn là câu hỏi
                    # đụng kpi_summary/fact_tonghopkhachhang/inventory/mart_layer (chỉ có trên
                    # Supabase, KHÔNG có trên Bravo) dù system prompt đã được dặn tránh — trả thông
                    # báo rõ ràng bằng tiếng Việt thay vì để lộ lỗi pyodbc thô cho người dùng cuối.
                    if "invalid object name" in upstream_error.lower():
                        return {"error": (
                            "Câu hỏi này cần dữ liệu tồn kho/KPI/chỉ tiêu — hiện KHÔNG có trên nguồn Bravo đang "
                            "dùng. Vui lòng thử lại sau khi Supabase kết nối được, hoặc hỏi lại theo hướng khác "
                            "(vd công nợ, doanh thu, khách hàng vẫn trả lời được bình thường)."
                        )}
                    print(f"[Warning] Resilient Chatbot: Bravo query failed ({upstream_error}). Falling back to SQLite...")

        # Fallback to local SQLite intermediate database
        if not os.path.exists(DB_PATH):
            err_msg = "Intermediate database file not found."
            if upstream_error:
                err_msg += f" (Upstream DB Error: {upstream_error})"
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
            if upstream_error:
                err_msg += f" (Upstream DB Error: {upstream_error})"
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

        # 1. Tỷ lệ phần trăm doanh số kênh OTC/ETC (bảng hóa đơn thật, không dùng 'orders' đã deprecated)
        if ("otc" in query_lower or "etc" in query_lower) and ("doanh thu" in query_lower or "doanh so" in query_lower) and ("chiem" in query_lower or "ty le" in query_lower or "phan tram" in query_lower or "%" in query_lower):
            return """
                WITH otc AS (SELECT COALESCE(SUM("TotalAmount"),0) AS v FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "IsHC"=FALSE),
                     etc AS (SELECT COALESCE(SUM("TotalAmount"),0) AS v FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE)
                SELECT otc.v AS otc_amount, etc.v AS etc_amount, (otc.v + etc.v) AS total_amount,
                       (otc.v * 100.0 / NULLIF(otc.v + etc.v, 0)) AS otc_pct,
                       (etc.v * 100.0 / NULLIF(otc.v + etc.v, 0)) AS etc_pct
                FROM otc, etc
            """

        # 2. Doanh thu/Doanh số theo kênh OTC/ETC (bảng hóa đơn thật)
        if "otc" in query_lower and ("doanh thu" in query_lower or "doanh so" in query_lower):
            return 'SELECT COALESCE(SUM("TotalAmount"),0) AS otc_amount FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "IsHC"=FALSE'
        elif "etc" in query_lower and ("doanh thu" in query_lower or "doanh so" in query_lower):
            return 'SELECT COALESCE(SUM("TotalAmount"),0) AS etc_amount FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE'

        # 2b. Top khách hàng doanh thu cao nhất (đặt trước nhánh doanh thu chung để ưu tiên khớp)
        if ("khach hang" in query_lower or "dai ly" in query_lower or "nha thuoc" in query_lower) and \
           ("doanh thu" in query_lower or "doanh so" in query_lower or "mua nhieu" in query_lower) and \
           not any(w in query_lower for w in ["giam", "roi bo", "mat khach", "sut giam"]):
            return """
                WITH cm AS (
                    SELECT h."CustomerCode" AS cc, SUM(h."TotalAmount") AS rev
                    FROM brv_hoadonhdr h WHERE h."IsActive"=TRUE AND h."IsHC"=FALSE GROUP BY 1
                    UNION ALL
                    SELECT h."CustomerCode", SUM(h."TotalAmount")
                    FROM brvsx_hoadonhdr h WHERE h."IsActive"=TRUE GROUP BY 1
                )
                SELECT k."Code" AS customer_code, k."Name" AS customer_name, SUM(cm.rev) AS revenue_amount
                FROM cm JOIN dms_khachhang k ON cm.cc = k."Code"
                GROUP BY 1,2 ORDER BY revenue_amount DESC LIMIT 10
            """

        # 2c. Khách hàng sụt giảm / có nguy cơ rời bỏ (so tháng gần nhất với tháng liền trước)
        if ("khach hang" in query_lower or "dai ly" in query_lower) and \
           any(w in query_lower for w in ["giam", "roi bo", "mat khach", "sut giam", "churn"]):
            return """
                WITH cm AS (
                    SELECT "CustomerCode" AS cc, DATE_TRUNC('month',"DocDate"::timestamp)::date AS m, SUM("TotalAmount") AS rev
                    FROM brv_hoadonhdr WHERE "IsActive"=TRUE AND "IsHC"=FALSE GROUP BY 1,2
                    UNION ALL
                    SELECT "CustomerCode", DATE_TRUNC('month',"DocDate"::timestamp)::date, SUM("TotalAmount")
                    FROM brvsx_hoadonhdr WHERE "IsActive"=TRUE GROUP BY 1,2
                ),
                agg AS (SELECT cc, m, SUM(rev) AS rev FROM cm GROUP BY cc, m),
                mm AS (SELECT m FROM (SELECT DISTINCT m FROM agg ORDER BY m DESC LIMIT 2) t),
                latest AS (SELECT MAX(m) AS m FROM mm), prev AS (SELECT MIN(m) AS m FROM mm)
                SELECT k."Name" AS customer_name, prevd.rev AS prev_revenue, COALESCE(cur.rev,0) AS current_revenue
                FROM (SELECT DISTINCT cc FROM agg) a
                JOIN agg prevd ON prevd.cc=a.cc AND prevd.m=(SELECT m FROM prev)
                LEFT JOIN agg cur ON cur.cc=a.cc AND cur.m=(SELECT m FROM latest)
                JOIN dms_khachhang k ON a.cc = k."Code"
                WHERE prevd.rev > 50000000 AND (prevd.rev - COALESCE(cur.rev,0)) / prevd.rev > 0.3
                ORDER BY prevd.rev DESC LIMIT 10
            """

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

    # Phân quyền theo miền/kênh — tổng quát hóa theo token trong username (phân tách bằng '_'),
    # KHÔNG hard-code từng role riêng lẻ. Cho phép thêm tài khoản mới (vd 'qlv_etc_bac',
    # 'pp_otc_nam'...) chỉ bằng cách thêm vào USERS dict (backend/main.py), không cần sửa code
    # ở đây — username chỉ cần chứa đúng 1 token miền (bac/nam/trung) và/hoặc 1 token kênh (otc/etc).
    _REGION_KEYWORDS = {
        "bac": ["miền bắc", "mien bac", "mb", "hà nội", "ha noi", "hải phòng", "hai phong"],
        "nam": ["miền nam", "mien nam", "mn", "hồ chí minh", "ho chi minh", "hcm",
                "sài gòn", "sai gon", "cần thơ", "can tho", "đông nam bộ", "dong nam bo"],
        "trung": ["miền trung", "mien trung", "mt", "đà nẵng", "da nang",
                  "tây nguyên", "tay nguyen"],
    }
    _CHANNEL_KEYWORDS = {
        "otc": ["otc", "nhà thuốc", "nha thuoc", "quầy thuốc", "quay thuoc",
                "bán lẻ", "ban le", "nhà thuốc tư nhân", "nha thuoc tu nhan"],
        "etc": ["etc", "bệnh viện", "benh vien", "thầu", "thau", "đấu thầu", "dau thau"],
    }
    _REGION_SQL_MARKERS = {"bac": ["MB", "MB2"], "nam": ["MN"], "trung": ["MT"]}  # mã miền, không quote — quote khi dùng
    _CHANNEL_SQL_MARKERS = {
        "otc": ["BRV_HOADONHDR", "BRV_HOADONCT", "BRV_HTTDUDK", "BRV_KHACHHANG", "'OTC'"],
        "etc": ["BRVSX_HOADONHDR", "BRVSX_HOADONCT", "BRVSX_HTTDUDK", "BRVSX_KHACHHANG", "'ETC'"],
    }
    # Bảng có dữ liệu TRỘN nhiều miền/nhiều kênh trong CÙNG 1 bảng (không phải bảng riêng theo
    # kênh như brv_*/brvsx_*) — nếu SQL đụng tới các bảng này mà KHÔNG thấy mã miền/kênh được
    # phép ở đâu cả, nhiều khả năng LLM quên lọc (không phải cố tình lọc SANG miền/kênh khác,
    # nên check "cấm mã lạ" phía trên không bắt được) -> phải chặn theo kiểu fail-closed, xem
    # đoạn "MỚI: fail-closed" trong ask().
    # BRV_HTTDUDK/BRVSX_HTTDUDK (công nợ Bravo, thêm 09/07/2026): thêm vào đây để fail-closed cũng
    # áp dụng — BRV_KhachHang không có cột vùng miền trực tiếp nhưng JOIN được sang DMS_KhachHang
    # qua Code rồi tới dim_tinhthanhpho (đã kiểm chứng khớp 99,99% dữ liệu thật, xem
    # mart_layer_instruction nhánh bravo) — user bị giới hạn miền BẮT BUỘC SQL phải có JOIN này +
    # mã miền được phép, nếu không sẽ bị chặn an toàn ở đây (không phải bug, là fail-closed đúng ý).
    _REGION_BEARING_TABLES = [
        "BRV_HOADONHDR", "BRV_HOADONCT", "BRVSX_HOADONHDR", "BRVSX_HOADONCT",
        "DIM_NHANVIEN", "KPI_SUMMARY", "RECEIVABLE_DETAIL", "DMS_KHACHHANG", "DMSSX_KHACHHANG",
        "BRV_HTTDUDK", "BRVSX_HTTDUDK",
    ]
    _CHANNEL_SHARED_TABLES = ["RECEIVABLE_DETAIL", "KPI_SUMMARY"]
    _REGION_NAMES_VI = {"bac": "Miền Bắc", "nam": "Miền Nam", "trung": "Miền Trung"}
    _CHANNEL_NAMES_VI = {"otc": "OTC (Nhà thuốc)", "etc": "ETC (Bệnh viện/Thầu)"}

    @staticmethod
    def _resolve_user_scope(user_key):
        """Suy ra (region, channel) mà user CHỈ được phép truy vấn, từ token trong username
        (vd 'qlv_etc_bac' -> region='bac', channel='etc'). None nếu không có token tương ứng
        (vd admin/c_level -> region=None, channel=None -> không giới hạn gì).

        Danh sách vùng/kênh HỢP LỆ đọc từ config['report_recipients'] (config/config.yaml) —
        cùng 1 nguồn audience duy nhất dùng chung cho cả phân quyền gửi báo cáo Email (Phần 3 kế
        hoạch báo cáo) lẫn phân quyền câu hỏi Chatbot ở đây, tránh định nghĩa lại quy ước vùng/kênh
        ở 2 nơi khác nhau trong codebase. Nếu report_recipients chưa cấu hình (vd môi trường cũ),
        fallback về đúng danh sách cứng trước đây để không phá vỡ hành vi hiện tại."""
        try:
            from src.database import load_config
            recipients = load_config().get('report_recipients') or []
        except Exception:
            recipients = []
        valid_regions = sorted({r['region'] for r in recipients if r.get('region')}) or ["bac", "nam", "trung"]
        valid_channels = sorted({str(r['channel']).lower() for r in recipients if r.get('channel')}) or ["otc", "etc"]

        tokens = user_key.replace('-', '_').split('_')
        region = next((r for r in valid_regions if r in tokens), None)
        channel = next((c for c in valid_channels if c in tokens), None)
        return region, channel

    def ask(self, user_question, session_key=None, username=None):
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

        # Resolve user role/scope based on session_key or username — tổng quát theo token miền
        # (bac/nam/trung) + kênh (otc/etc) trong username, KHÔNG hard-code từng role riêng lẻ.
        user_key = str(username or session_key or "").lower()
        scope_region, scope_channel = self._resolve_user_scope(user_key)
        if "admin" in user_key.replace('-', '_').split('_'):
            user_role = "admin"
        elif scope_region or scope_channel:
            user_role = user_key
        else:
            user_role = "c_level"  # mặc định: admin/c_level/không nhận diện được -> không giới hạn

        # 0. Role-based query interception (Pre-check) — áp cả 2 chiều (miền + kênh) độc lập,
        # 1 tài khoản có thể vừa bị giới hạn miền vừa bị giới hạn kênh (vd 'qlv_etc_bac')
        q_clean = user_question.lower().strip()
        if scope_region:
            restricted_regions = [kw for r in self._REGION_KEYWORDS if r != scope_region for kw in self._REGION_KEYWORDS[r]]
            if any(r in q_clean for r in restricted_regions):
                return {
                    "question": user_question,
                    "sql": "",
                    "data": [],
                    "columns": [],
                    "answer": f"Anh/Chị chỉ được truy vấn dữ liệu thuộc {self._REGION_NAMES_VI[scope_region]}. Vui lòng điều chỉnh câu hỏi cho phù hợp.",
                    "mode": "Security Restriction"
                }
        if scope_channel:
            other_channel = "etc" if scope_channel == "otc" else "otc"
            if any(c in q_clean for c in self._CHANNEL_KEYWORDS[other_channel]):
                return {
                    "question": user_question,
                    "sql": "",
                    "data": [],
                    "columns": [],
                    "answer": f"Anh/Chị chỉ được truy vấn dữ liệu thuộc kênh {self._CHANNEL_NAMES_VI[scope_channel]}. Vui lòng điều chỉnh câu hỏi cho phù hợp.",
                    "mode": "Security Restriction"
                }

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

        active_backend = self._resolve_active_backend()
        db_schema = get_db_schema(dialect=active_backend)
        history_block = self._get_history_block(session_key)

        # Đọc cache DATA_QUERY nếu có — key gồm cả scope_region/scope_channel (an toàn RBAC) và
        # CHỈ áp dụng khi không có lịch sử hội thoại (xem giải thích ở __init__, self._query_cache).
        import time as _time
        cache_key = (user_question.strip().lower(), scope_region, scope_channel, active_backend)
        if not history_block and not self.is_mock:
            cached = self._query_cache.get(cache_key)
            if cached is not None and (_time.time() - cached["ts"]) < self._QUERY_CACHE_TTL_SECONDS:
                result = dict(cached["result"])
                self._remember_turn(session_key, user_question, result["answer"])
                return result

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
        earliest_date_str, latest_date_str, latest_month_end_str, latest_period = self._get_latest_dates(backend=active_backend)
        parts = latest_date_str.split('-')
        latest_year = parts[0] if len(parts) > 0 else "2026"
        latest_month = parts[1] if len(parts) > 1 else "06"
        latest_q_start = f"{latest_year}-04-01"

        # Mart layer (mart_layer.mart_revenue_summary) — bảng tổng hợp sẵn doanh thu theo
        # ngày/kênh (xem docs/mart_revenue_summary_design.md), tạo ra để tránh full table scan
        # trên brv_hoadonhdr/brv_hoadonct hàng triệu dòng mỗi câu hỏi doanh thu (nguyên nhân gây
        # Postgres statement timeout trên hạ tầng hiện tại). Kiểm tra động — bảng có thể CHƯA
        # được tạo (chưa chạy DDL) nên chỉ ưu tiên dùng khi ĐÃ xác nhận tồn tại thật trong schema.
        has_mart_revenue_summary = "Table 'mart_layer.mart_revenue_summary'" in db_schema
        mart_layer_instruction = ""
        if has_mart_revenue_summary:
            mart_layer_instruction = """
0. ƯU TIÊN MART LAYER cho câu hỏi DOANH THU TỔNG HỢP theo kỳ (hôm nay/tuần/tháng/quý/năm, theo
   kênh OTC/ETC, có/không so sánh giữa các kỳ) — dùng 'mart_layer.mart_revenue_summary' (cột:
   report_date date, channel text ('OTC'/'ETC'), revenue numeric, invoice_count int) THAY VÌ quét
   brv_hoadonhdr/brv_hoadonct/brvsx_hoadonhdr/brvsx_hoadonct — bảng mart đã tổng hợp sẵn 1
   dòng/ngày/kênh nên cực nhanh, tránh timeout. Ví dụ:
     SELECT channel AS "Kênh", SUM(revenue) AS "Doanh thu"
     FROM mart_layer.mart_revenue_summary
     WHERE report_date >= '2026-04-01' AND report_date < '2026-05-01'
     GROUP BY channel
   CHỈ quay lại bảng raw (brv_hoadonhdr/ct, brvsx_hoadonhdr/ct) khi câu hỏi cần chi tiết mà mart
   layer KHÔNG có — theo khách hàng cụ thể, sản phẩm, nhân viên, hoặc từng hóa đơn riêng lẻ.
"""
        elif active_backend == "bravo":
            mart_layer_instruction = """
0. Đang dùng nguồn Bravo SQL Server (nguồn CHÍNH) — KHÔNG có 'mart_layer.mart_revenue_summary',
   KHÔNG có 'inventory' (tồn kho — chưa hỗ trợ, từ chối lịch sự nếu được hỏi). Doanh thu tính trực
   tiếp từ brv_hoadonhdr/brv_hoadonct/brvsx_hoadonhdr/brvsx_hoadonct như bình thường.

   CÔNG NỢ (receivable_detail không tồn tại trên Bravo với TÊN này, nhưng dữ liệu THÔ có thật và
   MỚI HƠN — đã kiểm chứng thực tế 09/07/2026): dùng 'BRV_HTTDuDK' (kênh OTC) / 'BRVSX_HTTDuDK'
   (kênh ETC), JOIN với 'BRV_KhachHang'/'BRVSX_KhachHang' tương ứng qua CustomerId = Id. CHỈ trả lời
   TỔNG SỐ CÒN NỢ (không bucket theo tuổi nợ — xem giới hạn bên dưới). 3 QUY TẮC BẮT BUỘC (đã verify
   bằng dữ liệu thật, sai bất kỳ điểm nào cũng ra số SAI):
     a. Số còn nợ = [TotalAmount] - [PaidAmount]. TUYỆT ĐỐI KHÔNG dùng cột IsOpenDue để lọc "còn nợ"
        — đã xác nhận cột này không phản ánh đúng thực tế (luôn = 0 kể cả hóa đơn hôm nay, PaidAmount
        = 0, rõ ràng còn nợ).
     b. CHỈ lấy [Account] LIKE '131%' (tài khoản Phải thu khách hàng theo Thông tư 200). TUYỆT ĐỐI
        KHÔNG gộp Account bắt đầu '331%' (Phải trả người bán — chiều ngược lại, không phải công nợ
        phải thu).
     c. LUÔN JOIN sang BRV_KhachHang/BRVSX_KhachHang rồi lọc k.[IsCustomer] = 1 — nếu bỏ qua bước
        này, mã nội bộ của chính DNH ('P000001' kênh OTC, '1001136' kênh ETC — 2 mã này có
        IsCustomer=0) sẽ bị tính vào công nợ, làm số bị thổi phồng gấp ~3-4 lần so với thực tế (đã
        đo được: 418 tỷ sai vs 114 tỷ đúng khi thiếu filter này).
   Ví dụ đúng — tổng công nợ theo khách hàng, kênh OTC:
     SELECT k.[Code] AS [Mã KH], k.[Name] AS [Tên khách hàng],
            SUM(h.[TotalAmount] - h.[PaidAmount]) AS [Còn nợ]
     FROM [BRV_HTTDuDK] h
     JOIN [BRV_KhachHang] k ON h.[CustomerId] = k.[Id]
     WHERE h.[Account] LIKE '131%' AND (h.[TotalAmount] - h.[PaidAmount]) > 0 AND k.[IsCustomer] = 1
     GROUP BY k.[Code], k.[Name]
     ORDER BY [Còn nợ] DESC
   Kênh ETC dùng BRVSX_HTTDuDK/BRVSX_KhachHang, logic y hệt.

   CÔNG NỢ THEO VÙNG MIỀN (Miền Bắc/Trung/Nam): BRV_KhachHang không có cột vùng miền trực tiếp,
   nhưng JOIN được sang DMS_KhachHang qua CỘT [Code] (k.[Code] = dk.[Code] — ĐÃ KIỂM CHỨNG khớp
   17.761/17.762 dòng thực tế, ~99,99%), rồi JOIN tiếp DMS_KhachHang -> DIM_TinhThanhPho như doanh
   thu để lấy AreaCode. Ví dụ công nợ Miền Bắc kênh OTC:
     SELECT SUM(h.[TotalAmount] - h.[PaidAmount]) AS [Công nợ Miền Bắc]
     FROM [BRV_HTTDuDK] h
     JOIN [BRV_KhachHang] k ON h.[CustomerId] = k.[Id]
     JOIN [DMS_KhachHang] dk ON k.[Code] = dk.[Code]
     JOIN [DIM_TinhThanhPho] t ON dk.[CityId] = t.[CityId]
     WHERE h.[Account] LIKE '131%' AND (h.[TotalAmount] - h.[PaidAmount]) > 0 AND k.[IsCustomer] = 1
       AND t.[AreaCode] IN ('MB', 'MB2')
   Kênh ETC JOIN sang DMSSX_KhachHang (thay DMS_KhachHang) qua cùng cách. LƯU Ý BẢO MẬT: nếu người
   hỏi bị giới hạn vùng miền (xem CRITICAL SECURITY RULE ở dưới nếu có), BẮT BUỘC luôn thêm JOIN +
   filter AreaCode này vào MỌI câu hỏi công nợ, kể cả khi câu hỏi không nói rõ vùng miền — thiếu
   filter này sẽ bị hệ thống an toàn tự chặn (không trả lời được), không phải lộ dữ liệu sai vùng.

   GIỚI HẠN CHƯA HỖ TRỢ — TUỔI NỢ / BUCKET QUÁ HẠN (vd "nợ quá hạn 1-15 ngày", "nợ quá 45 ngày",
   "aging"): TỪ CHỐI lịch sự, KHÔNG tự đoán/tự chế công thức. [DueDate] trên 2 bảng công nợ là SỐ
   NGÀY công nợ (payment term), KHÔNG PHẢI ngày — để tính quá hạn cần biết "ngày cơ sở" (date basis:
   tính từ DocDate hay từ 1 mốc khác), ĐÂY LÀ CÂU HỎI CHƯA ĐƯỢC DNH XÁC NHẬN (open item, xem
   dnh-debt-aging-schema/dnh-project-context) — dùng đúng dạng SELECT N'...' từ chối (xem rule
   dialect bên dưới).
   Câu hỏi công nợ KHÔNG bucket tuổi nợ (theo khách hàng/tổng công ty/theo kênh/theo vùng miền) vẫn
   trả lời bình thường theo quy tắc a/b/c ở trên (+ join vùng miền nếu cần).
"""

        # 'fact_tonghopkhachhang' thuộc mart đầy đủ (production), KHÔNG có ở bản dev hiện tại
        # (đã xác nhận: information_schema không trả về cột nào cho bảng này khi CLOUD_DB_URL trỏ
        # dev). Trước đây system prompt LUÔN LUÔN chỉ định TDV/QLV/CS/CTV/TK phải dùng bảng này
        # -> sinh SQL đúng cú pháp nhưng CHẮC CHẮN lỗi khi chạy trên dev (bảng không tồn tại).
        # Kiểm tra động thay vì hard-code — khi CLOUD_DB_URL trỏ production (có bảng này) thì
        # dùng hướng dẫn chi tiết gốc; khi trỏ dev thì tự chuyển hướng dẫn sang kpi_summary
        # (đã kiểm chứng có dữ liệu thật cho cả TDV/QLV/CS, không chỉ TP/PP/TBP như tài liệu cũ
        # giả định).
        has_fact_tonghopkhachhang = "Table 'fact_tonghopkhachhang'" in db_schema
        if has_fact_tonghopkhachhang:
            kpi_tdv_instruction = f"""   - Với TDV/QLV/CS/CTV/TK, tiếp tục dùng 'fact_tonghopkhachhang' (actual sales = 'Amount_Cus', target = 'MonthSaleTarget', employee code = 'EmployeeCode', region = 'AreaCode' / 'AreaCode2').
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
     LIMIT 5"""
        elif active_backend == "bravo":
            kpi_tdv_instruction = """   - Đang dùng nguồn dữ liệu DỰ PHÒNG (Bravo SQL Server, vì Supabase tạm không kết nối được).
   - CẢ 'fact_tonghopkhachhang' LẪN 'kpi_summary' ĐỀU KHÔNG tồn tại trên nguồn dự phòng này (chỉ có
     trên Supabase) — TUYỆT ĐỐI KHÔNG sinh SQL tham chiếu tới 2 bảng này, sẽ luôn lỗi khi chạy.
   - Nếu câu hỏi cần dữ liệu KPI/chỉ tiêu/nhân sự: BẮT BUỘC vẫn trả về ĐÚNG 1 câu SELECT hợp lệ (vì
     câu trả lời CHỈ ĐƯỢC LÀ SQL, không được viết văn xuôi thuần) — dùng đúng dạng:
     SELECT N'Dữ liệu KPI hiện không có trên nguồn dự phòng (Bravo SQL Server). Vui lòng thử lại khi Supabase hồi phục.' AS [Thông báo]
     TUYỆT ĐỐI KHÔNG trả lời bằng câu văn thường (không phải SELECT) — sẽ bị hệ thống an toàn chặn
     và hiện lỗi khó hiểu cho người dùng."""
        else:
            kpi_tdv_instruction = """   - 'fact_tonghopkhachhang' KHÔNG tồn tại trong nguồn dữ liệu đang kết nối hiện tại (không thấy trong schema ở trên) — TUYỆT ĐỐI KHÔNG được sinh SQL tham chiếu tới bảng này, sẽ luôn lỗi khi chạy.
   - Với TDV/QLV/CS/CTV/TK, dùng 'kpi_summary' (đã kiểm chứng có dữ liệu thật cho các position_code này, không chỉ TP/PP/TBP) — CÙNG cách truy vấn như hướng dẫn TP ở trên: filter position_code, dùng month_sale_target/month_sale_amount/month_sale_percent (hoặc quarter_/year_ tương ứng).
   - Position codes: TDV/QLV/CS/CTV/TK/TP/PP/TBP — tất cả đều dùng kpi_summary.position_code, KHÔNG có ngoại lệ nào cần fact_tonghopkhachhang.
   - When the user asks about KPI or nhân viên without specifying position, DEFAULT to TDV (Trình dược viên) since they are the primary salesforce.
   - LƯU Ý DỮ LIỆU: kpi_summary hiện có thể chưa đầy đủ cho mọi nhân sự (dữ liệu nhập tay/đồng bộ theo kỳ) — nếu kết quả trả về ít dòng hơn số lượng nhân sự cấp đó thực tế có, đừng coi là lỗi truy vấn, hãy nêu rõ trong câu trả lời rằng dữ liệu hệ thống hiện chỉ ghi nhận được từng đó người.
   - Example Top TDV theo KPI:
     SELECT employee_name, month_sale_target, month_sale_amount,
            ROUND((month_sale_percent * 100)::numeric, 2) AS "Tỉ lệ đạt KPI (%)"
     FROM kpi_summary
     WHERE position_code = 'TDV'
     ORDER BY month_sale_percent DESC
     LIMIT 5"""

        # db_dialect suy trực tiếp từ active_backend đã tính 1 lần ở đầu ask() (không tự đoán lại
        # độc lập nữa — trước đây khối này tự check cloud_db_url/cloud_available riêng, có thể lệch
        # với quyết định get_db_schema() đã dùng).
        db_dialect = {"postgres": "PostgreSQL", "bravo": "TSQL", "sqlite": "SQLite"}[active_backend]
        # Chỉ cần biết Postgres có lỗi thật hay không khi ĐÃ rơi xuống sqlite (cả Bravo lẫn Postgres
        # đều không dùng được) — banner cho case "bravo" giờ không phụ thuộc cloud_available nữa
        # (Bravo là mặc định chủ động, không phải fallback do Supabase lỗi, xem _resolve_active_backend),
        # nên bỏ qua việc gọi self.cloud_available (round-trip mạng) khi active_backend đã là "bravo".
        cloud_unreachable_fallback = (
            active_backend == "sqlite" and bool(cloud_db_url) and not self.is_mock and not self.cloud_available
        )

        dialect_rules = ""
        if db_dialect == "PostgreSQL":
            dialect_rules = """
3. Make sure to use SQL functions that are compatible with PostgreSQL (e.g. COALESCE, NOW(), CURRENT_DATE, ILIKE for case-insensitive search, etc.).
4. VERY IMPORTANT: Use 'ILIKE' instead of 'LIKE' for case-insensitive search on text columns. Since values in the database (like CityName, Name, item_name) may be stored without Vietnamese tone marks, when filtering Vietnamese text, you MUST search for BOTH the accented and unaccented versions using OR. For example: (t."CityName" ILIKE '%Bắc%' OR t."CityName" ILIKE '%Bac%') or (n."Name" ILIKE '%Tùng%' OR n."Name" ILIKE '%Tung%').
5. VERY IMPORTANT: In PostgreSQL, the ROUND(value, decimals) function requires the first argument to be explicitly cast to numeric, e.g. ROUND(expression::numeric, 2). Otherwise, it will fail with "function round(double precision, integer) does not exist".
6. VERY IMPORTANT — SARGABLE date filtering (BẮT BUỘC để tận dụng INDEX có sẵn trên DocDate,
   tránh full table scan gây PostgreSQL statement timeout — đây là sự cố THẬT đã xảy ra trên hạ
   tầng hiện tại, không phải lý thuyết): Date columns like 'DocDate'/'SaveDate' are stored as TEXT
   in ISO format ('YYYY-MM-DDTHH:MM:SS'), which sorts correctly as plain STRING comparison
   (lexicographic order = chronological order for ISO strings).
   - For WHERE-clause range/equality filtering (the vast majority of queries), compare DIRECTLY
     against the TEXT column WITHOUT any ::date/::timestamp cast — casting the column breaks the
     existing index (PostgreSQL cannot use a plain index when the indexed column itself is cast),
     forcing a full table scan. Use a RANGE for "on day X" instead of casting to compare equality:
       ĐÚNG (sargable, dùng được index): WHERE h."DocDate" >= '2026-04-01' AND h."DocDate" < '2026-05-01'
       ĐÚNG cho "đúng ngày X": WHERE h."DocDate" >= '2026-07-07' AND h."DocDate" < '2026-07-08'
       SAI (phá index, full scan, có thể timeout): WHERE h."DocDate"::date >= '2026-04-01' hoặc h."DocDate"::date = '2026-07-07'
   - ONLY cast to timestamp/date when you genuinely need a date FUNCTION with no sargable text
     equivalent — e.g. DATE_TRUNC('month', "DocDate"::timestamp) purely for GROUP BY/display
     month-bucketing. Even then, ALSO add a sargable range filter in WHERE (not just rely on the
     cast) whenever the query already knows the relevant date range, so the planner can use the
     index to narrow rows BEFORE the expensive cast/grouping runs on a small subset instead of
     the whole table. Failure to do so will cause PostgreSQL crash error: "function date_trunc(unknown, text) does not exist" if you forget the cast entirely inside an actual date function — nhưng KHÔNG cast trong WHERE filter thuần túy.
7. Do not use SQLite specific functions like strftime. Use standard Postgres date/time operators and intervals.
8. ALWAYS wrap case-sensitive table and column names in double quotes if they contain uppercase letters (e.g. "TotalAmount", "DocStatus", "EInvoiceStatus", "IsActive", "CustomerCode", "EmployeeCode", "MonthSaleTarget", "Amount_Cus", "Amount_CT", "SaveDate"). For example: h."TotalAmount", f."MonthSaleTarget".
"""
        elif db_dialect == "TSQL":
            dialect_rules = """
3. Make sure to use SQL functions that are compatible with Microsoft SQL Server (T-SQL) (e.g. COALESCE, GETDATE(), DATEADD, DATEDIFF, DATEPART, DATEFROMPARTS, etc.).
4. ALWAYS use 'LIKE' instead of 'ILIKE' (T-SQL is case-insensitive by default under standard collation). Since values in the database (like CityName, Name, item_name) may be stored without Vietnamese tone marks, when filtering Vietnamese text, you MUST search for BOTH the accented and unaccented versions using OR. For example: (t.CityName LIKE '%Bắc%' OR t.CityName LIKE '%Bac%') or (n.Name LIKE '%Tùng%' OR n.Name LIKE '%Tung%').
5. ALWAYS wrap case-sensitive table and column names in square brackets if they contain uppercase letters or spaces (e.g. h.[TotalAmount], f.[MonthSaleTarget], [brv_hoadonhdr], [dms_khachhang]). Do NOT use double quotes.
6. VERY IMPORTANT: In T-SQL, there is no LIMIT clause. To limit the number of rows returned, use 'SELECT TOP N ...' at the very beginning of the query instead of 'LIMIT N' at the end. For example: 'SELECT TOP 100 ...' or 'SELECT TOP 5 ...'. Always default to TOP 100 for open list queries.
7. VERY IMPORTANT — KHÁC với Postgres: trên nguồn dữ liệu này (Bravo SQL Server, nguồn dự phòng),
   date columns như 'DocDate'/'SaveDate' là kiểu DATE GỐC THẬT (không phải TEXT như bên Postgres) —
   ĐỪNG cast (không dùng TRY_CAST/CONVERT khi so sánh/lọc), so sánh trực tiếp: WHERE h.[DocDate]
   >= '2026-04-01' AND h.[DocDate] < '2026-05-01'. Cast thừa không sai cú pháp nhưng không cần thiết.
8. VERY IMPORTANT — KHÁC với Postgres: cột boolean (IsActive, IsHC, IsCancelled...) trên nguồn này là
   kiểu 'bit' THẬT — dùng '= 1' / '= 0', TUYỆT ĐỐI KHÔNG dùng 'TRUE'/'FALSE' (không phải literal hợp
   lệ trong T-SQL truyền thống). Ví dụ ĐÚNG: WHERE h.[IsActive] = 1 AND h.[IsHC] = 0. Ví dụ SAI:
   WHERE h.[IsActive] = TRUE.
9. For multi-month grouping in T-SQL, use DATEFROMPARTS(YEAR([DocDate]), MONTH([DocDate]), 1) to
   truncate to month-start, and GROUP BY it (tương đương DATE_TRUNC('month', ...) bên Postgres).
10. ALWAYS default to adding 'TOP 100' for open-ended queries to prevent dumping thousands of records.
11. Nguồn dữ liệu này (Bravo, nguồn CHÍNH từ 09/07/2026) có bảng hóa đơn/khách hàng/nhân viên/sản
    phẩm VÀ công nợ (xem mục "CÔNG NỢ" ở hướng dẫn phía trên — BRV_HTTDuDK/BRVSX_HTTDuDK). KHÔNG có
    'kpi_summary'/'fact_tonghopkhachhang' (KPI nhân viên/chỉ tiêu — chưa hỗ trợ trên nguồn này),
    'inventory' (tồn kho — chưa hỗ trợ), hay schema 'mart_layer'. Nếu câu hỏi CẦN các bảng CHƯA HỖ
    TRỢ này (KPI/tồn kho, KHÔNG phải công nợ): BẮT BUỘC vẫn trả về ĐÚNG 1 câu SELECT hợp lệ (câu trả
    lời CHỈ ĐƯỢC LÀ SQL, không được viết văn xuôi thuần — văn xuôi sẽ bị hệ thống an toàn chặn và
    hiện lỗi khó hiểu cho người dùng) — dùng đúng dạng:
    SELECT N'Dữ liệu tồn kho/KPI hiện chưa hỗ trợ trên nguồn Bravo. Vui lòng thử lại khi Supabase kết nối được.' AS [Thông báo]
"""
        else:
            dialect_rules = """
3. Make sure to use SQL functions that are compatible with SQLite (e.g. COALESCE, IFNULL, strftime, etc.).
"""

        # System prompt injection for role scope restriction — tổng quát theo scope_region/scope_channel
        # (xem _resolve_user_scope) thay vì hard-code từng role, để thêm role mới không cần sửa đây.
        role_system_instruction = ""
        if scope_region:
            allowed_list = "', '".join(self._REGION_SQL_MARKERS[scope_region])
            other_codes = ", ".join(
                f"'{m}'" for r in self._REGION_KEYWORDS if r != scope_region for m in self._REGION_SQL_MARKERS[r]
            )
            role_system_instruction += f"""
=== CRITICAL SECURITY RULE (VÙNG MIỀN) ===
You are generating SQL for a manager scoped to {self._REGION_NAMES_VI[scope_region]} only.
You MUST restrict all data queries to region code(s) '{allowed_list}'.
1. For invoice headers/customer data, you MUST join with dim_tinhthanhpho t and filter: t."AreaCode" IN ('{allowed_list}') or area_code IN ('{allowed_list}').
2. For KPI/targets summary, you MUST filter AreaCode/area_code IN ('{allowed_list}').
3. For client/receivable lists, filter AreaCode/AreaCode2 IN ('{allowed_list}') or join and filter.
Under no circumstances should you query or return data for other region codes ({other_codes}).
==============================
"""
        if scope_channel == "otc":
            role_system_instruction += """
=== CRITICAL SECURITY RULE (KÊNH) ===
You are generating SQL for a manager scoped to the OTC channel only.
1. Do NOT query ETC tables 'brvsx_hoadonhdr' or 'brvsx_hoadonct'.
2. ONLY query OTC tables 'brv_hoadonhdr', 'brv_hoadonct'.
3. If querying tables containing multiple channels (like 'receivable_detail' or 'kpi_summary'), you MUST explicitly filter: sales_channel = 'OTC' or similar.
Under no circumstances should you query or return ETC data.
==============================
"""
        elif scope_channel == "etc":
            role_system_instruction += """
=== CRITICAL SECURITY RULE (KÊNH) ===
You are generating SQL for the ETC Channel Manager (Manager kênh ETC).
You MUST restrict all queries to the ETC channel only.
1. Do NOT query OTC tables 'brv_hoadonhdr' or 'brv_hoadonct'.
2. ONLY query ETC tables 'brvsx_hoadonhdr', 'brvsx_hoadonct', 'receivable_etc', 'fact_kehoachtongetc'.
3. If querying tables containing multiple channels (like 'receivable_detail' or 'kpi_summary'), you MUST explicitly filter: sales_channel = 'ETC' or similar.
Under no circumstances should you query or return OTC data.
==============================
"""

        system_prompt = f"""
You are an expert SQL Generator for Duoc Nam Ha (DNH) commercial data warehouse.
Your task is to convert the user's Vietnamese natural language query into a single valid {db_dialect} query.

{role_system_instruction}

Here is the database schema:
{db_schema}

Key Business Logic & Tables & Strict Mapping Rules:
{mart_layer_instruction}
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
{kpi_tdv_instruction}

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
   - "HÔM NAY"/"today": filter DocDate = CURRENT_DATE (Postgres) hoặc CAST(GETDATE() AS DATE) (T-SQL/Bravo)
     — dùng ĐỒNG HỒ THẬT của server, KHÔNG dùng MAX(DocDate). Nếu hôm nay chưa có hóa đơn nào (business
     day chưa xong), kết quả 0 là ĐÚNG, không tự lùi sang ngày khác.
   - "HÔM QUA"/"yesterday": filter DocDate = CURRENT_DATE - 1 (Postgres) hoặc
     CAST(DATEADD(day, -1, GETDATE()) AS DATE) (T-SQL/Bravo) — CŨNG dùng đồng hồ thật.
     TUYỆT ĐỐI KHÔNG tính bằng MAX(DocDate) - 1 ngày — đã xác nhận lỗi thực tế 10/07/2026: hôm đó
     MAX(DocDate) đã chính là 09/07 (= hôm qua thật), nhưng AI tự trừ thêm 1 ngày nữa ra 08/07 (hôm
     kia), trả lời sai 1 ngày. Lý do sai: MAX(DocDate) thường ĐÃ XẤP XỈ "hôm qua" rồi (vì hôm nay dữ
     liệu có thể chưa nhập xong lúc đang hỏi) — trừ thêm 1 ngày nữa là sai kép.
   - Nguyên tắc chung: MỌI mốc thời gian có nghĩa LỊCH THỰC (hôm nay/hôm qua/tuần này/tháng này) phải
     neo vào đồng hồ thật (CURRENT_DATE/GETDATE()), KHÔNG neo vào MAX(DocDate) — 2 khái niệm khác nhau
     và có thể lệch nhau nếu dữ liệu hôm nay chưa nhập xong. CHỈ riêng "N ngày/tháng GẦN NHẤT" (rolling
     window trên dữ liệu SẴN CÓ, xem rule ngay dưới) mới neo vào MAX(DocDate) — vì mục đích của nó là
     lấy N đơn vị thời gian gần nhất CÓ DỮ LIỆU, khác hẳn khái niệm lịch thực ở trên.
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
   - DOANH THU CHUNG THEO THỜI GIAN (người dùng hỏi "doanh thu" theo tuần/tháng mà KHÔNG chỉ rõ kênh): BẮT BUỘC trả về TÁCH RIÊNG 2 cột "Doanh thu OTC" và "Doanh thu ETC" (mỗi kênh 1 cột, từ CTE riêng theo quy tắc mục 5) thay vì gộp thành 1 cột "Doanh thu" duy nhất — giao diện sẽ vẽ biểu đồ cụm so sánh 2 kênh theo từng kỳ. Chỉ gộp 1 cột khi người dùng nói rõ "tổng doanh thu".
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
            sql_user_prompt = user_question
            if history_block:
                sql_user_prompt = (
                    f'{history_block}\n'
                    f'Câu hỏi HIỆN TẠI cần chuyển thành SQL (dùng lịch sử ở trên chỉ để hiểu ngữ cảnh/tham chiếu, '
                    f'ví dụ câu hỏi ngắn như "1" hay "còn tháng khác thì sao" ám chỉ nội dung đã hỏi trước đó): "{user_question}"'
                )
            # Thử tối đa 2 lần trước khi rơi về mock. Đã bắt được thật: lỗi timeout/mạng NHẤT
            # THỜI ở lần gọi AI đầu khiến 1 câu hỏi ngắn phụ thuộc lịch sử hội thoại (vd "quý 1
            # và quý 2 cơ") rơi thẳng về _generate_mock_sql() — hàm này KHÔNG biết gì về lịch sử
            # hội thoại, nên đoán bừa sang chủ đề khác hẳn. Người dùng thấy câu trả lời trông
            # bình thường (không có dấu hiệu lỗi) nên hiểu lầm là AI "trả lời sai"/"quên ngữ
            # cảnh", trong khi thực chất là AI bị lỗi tạm thời rồi bị thay bằng bản dự phòng.
            sql_query = None
            last_error = None
            for attempt in range(2):
                try:
                    sql_query = self._call_ai(
                        model=self.sql_model,
                        system_prompt=system_prompt,
                        user_prompt=sql_user_prompt,
                        temperature=0.0
                    )
                    if sql_query.startswith("```"):
                        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
                    break
                except Exception as e:
                    last_error = e
                    print(f"[Warning] Lỗi gọi AI sinh SQL (lần {attempt + 1}/2): {e}")
            if sql_query is None:
                print(f"[Error] AI sinh SQL thất bại sau 2 lần thử, rơi về mock (KHÔNG có ngữ cảnh hội thoại): {last_error}")
                sql_query = self._generate_mock_sql(user_question)

        # Post-check Security Validation on generated SQL query
        sql_clean = sql_query.upper()
        unauthorized = False
        unauthorized_reason = ""
        
        # Chặn theo miền/kênh — tổng quát theo scope_region/scope_channel (đã suy ra từ username
        # ở đầu hàm ask()), cả 2 chiều độc lập nhau (1 role có thể bị giới hạn cả miền lẫn kênh).
        #
        # QUAN TRỌNG: đây KHÔNG phải RLS (Row-Level Security) thật ở tầng Postgres — vẫn là
        # kiểm tra chuỗi trên SQL text, không phải enforce ở tầng DB. RLS thật cần role Postgres
        # riêng (không phải role hiện tại — role owner/connection pooler mặc định BYPASS RLS) +
        # policy trên từng bảng + set session variable mỗi request — đổi cả cách quản lý kết nối
        # (xung đột với _get_cloud_engine() dùng pool dùng chung, xem dnh-project-context). Việc
        # đó là hạ tầng lớn, không làm trong lượt này — đây là bản heuristic tốt hơn, không phải
        # thay thế hoàn toàn.
        if scope_region:
            other_markers = [m for r in self._REGION_KEYWORDS if r != scope_region for m in self._REGION_SQL_MARKERS[r]]
            if any(f"'{m}'" in sql_clean for m in other_markers):
                unauthorized = True
                unauthorized_reason = f"Anh/Chị không có quyền truy vấn dữ liệu ngoài {self._REGION_NAMES_VI[scope_region]}."

            # MỚI — fail-closed: check cũ ở trên chỉ bắt được khi SQL CÓ nhắc mã miền khác. Nếu
            # LLM đơn giản QUÊN lọc miền (SQL đụng bảng nhiều-miền nhưng không có mã miền nào cả)
            # thì check cũ không bắt được -> lộ dữ liệu toàn công ty. Bắt buộc phải thấy CHÍNH mã
            # miền được phép ở đâu đó khi SQL đụng các bảng này, không thì từ chối (an toàn hơn
            # là đoán/tự sửa SQL).
            if not unauthorized:
                touches_region_table = any(t in sql_clean for t in self._REGION_BEARING_TABLES)
                own_marker_present = any(f"'{m}'" in sql_clean for m in self._REGION_SQL_MARKERS[scope_region])
                if touches_region_table and not own_marker_present:
                    unauthorized = True
                    unauthorized_reason = f"Không xác định được SQL có lọc đúng theo {self._REGION_NAMES_VI[scope_region]} hay không — từ chối để đảm bảo an toàn dữ liệu. Anh/Chị vui lòng hỏi lại cụ thể hơn (vd nêu rõ tên miền trong câu hỏi)."

        if scope_channel:
            other_channel = "etc" if scope_channel == "otc" else "otc"
            if any(m in sql_clean for m in self._CHANNEL_SQL_MARKERS[other_channel]):
                unauthorized = True
                unauthorized_reason = f"Anh/Chị không có quyền truy vấn dữ liệu ngoài kênh {self._CHANNEL_NAMES_VI[scope_channel]}."

            # MỚI — fail-closed tương tự, riêng cho bảng DÙNG CHUNG cả 2 kênh (receivable_detail/
            # kpi_summary không tách bảng riêng theo kênh như brv_*/brvsx_*, nên chỉ chặn "bảng
            # kênh kia" ở trên là chưa đủ — còn phải chặn cả trường hợp không lọc gì trên bảng gộp).
            if not unauthorized:
                touches_shared_table = any(t in sql_clean for t in self._CHANNEL_SHARED_TABLES)
                own_channel_marker_present = f"'{scope_channel.upper()}'" in sql_clean
                if touches_shared_table and not own_channel_marker_present:
                    unauthorized = True
                    unauthorized_reason = f"Không xác định được SQL có lọc đúng theo kênh {self._CHANNEL_NAMES_VI[scope_channel]} hay không (bảng dùng chung nhiều kênh) — từ chối để đảm bảo an toàn dữ liệu. Anh/Chị vui lòng hỏi lại cụ thể hơn."

        if unauthorized:
            query_result = {"error": unauthorized_reason}
        else:
            # Run the query
            query_result = self._execute_sql(sql_query, target=active_backend)
        
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

                # Mặc định LUÔN trả lời đơn giản/trực tiếp — chỉ mở rộng thành khung đầy đủ
                # Thực trạng-Nguyên nhân-Giải pháp khi câu hỏi TRỰC TIẾP hỏi "tại sao"/"như thế nào"
                # (không còn phụ thuộc số dòng kết quả — trước đây multi-row vẫn tự bị áp khung đầy
                # đủ dù người dùng không hỏi nguyên nhân/giải pháp).
                wants_deep_analysis = any(k in user_question.lower() for k in [
                    "tại sao", "tai sao", "vì sao", "vi sao",
                    "như thế nào", "nhu the nao", "làm thế nào", "lam the nao",
                    "làm sao", "lam sao", "nguyên nhân", "nguyen nhan", "giải pháp", "giai phap"
                ])

                # Parse intent using our fast heuristic visual intent parser first (không gọi AI,
                # vẫn cần chạy trong CẢ 2 nhánh dưới đây vì phần vẽ biểu đồ phía sau dùng tới).
                parsed_intent = self._parse_data_intent(user_question)
                intent_type = parsed_intent.get("intent", "Single_Value")

                # Fast path — kết quả 1 dòng, ít cột, không cần phân tích sâu: tự ghép câu bằng
                # code thay vì gọi AI lần 2 (đo thật: ~4-10s mỗi lần) chỉ để diễn giải vài con số
                # tổng hợp đơn giản. KHÔNG áp dụng cho case nhiều dòng/cần phân tích MoM-target/
                # "tại sao" — những case đó vẫn qua AI như cũ để giữ chất lượng câu trả lời.
                if (len(llm_rows) == 1 and not wants_deep_analysis and not is_truncated_for_llm
                        and len(query_result.get("columns", [])) <= 6):
                    answer = self._quick_format_single_row(query_result.get("columns", []), llm_rows[0])
                else:
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

7. Data Boundary Transparency (CRITICAL): The invoice data actually available right now spans from {earliest_date_str} to {latest_date_str} (kiểm tra động mỗi lần, KHÔNG giả định cố định — dữ liệu có thể đã được nạp thêm theo thời gian). If {earliest_date_str} is January 1st of its year, the FULL year is already available from the start — do NOT show any data-boundary warning in that case, even if the user asks for "cả năm"/"6 tháng đầu năm"/"từ đầu năm". ONLY if the user's question implies a period starting BEFORE {earliest_date_str} (i.e. {earliest_date_str} is genuinely later than Jan 1st of the relevant year), you MUST prominently warn at the beginning of your response using the REAL range above — do NOT invent or reuse any specific month range from memory, always state {earliest_date_str} to {latest_date_str} exactly:
⚠️ <b>Lưu ý quan trọng về dữ liệu:</b> Hệ thống hiện chỉ có dữ liệu hóa đơn từ {earliest_date_str} đến {latest_date_str}. Dữ liệu trước {earliest_date_str} chưa được tải vào CSDL, do đó kết quả bên dưới chỉ phản ánh giai đoạn thực có dữ liệu, KHÔNG phải toàn bộ khoảng thời gian được hỏi.
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
        # Chỉ vẽ biểu đồ khi người dùng CHỦ ĐỘNG yêu cầu (vẽ/biểu đồ/đồ thị/chart...).
        # Câu hỏi dữ liệu thông thường chỉ trả lời + bảng, không tự sinh chart.
        # So khớp bằng cụm từ có dấu/không dấu rõ nghĩa — tránh substring mơ hồ (bài học bug "hi ").
        wants_chart = any(k in q_lower for k in [
            "biểu đồ", "bieu do", "đồ thị", "do thi", "chart", "graph",
            "vẽ", "trực quan", "truc quan", "visualize", "visual hóa", "minh họa", "minh hoa"
        ])
        if wants_chart and not "error" in query_result and query_result.get("rows") and len(query_result["rows"]) >= 1:
            try:
                # 2. Run deterministic Rule Engine
                visual_type = "KPI_Card"
                metrics_count = len(parsed_intent.get("metrics", []))
                num_rows = len(query_result["rows"])
                columns_lower = [c.lower() for c in query_result.get("columns", [])]
                
                # Detect if data looks like a time series (has a month/date/time column).
                # Cột tiếng Việt ("Tuần", "Tháng", "Quý", "Kỳ", "Năm") so bằng STARTSWITH — nếu so
                # substring sẽ khớp nhầm cột phái sinh như "Số tháng bán"/"% so với tháng trước".
                _vn_time_starts = ('tuần', 'tuan', 'tháng', 'thang', 'quý', 'quy ', 'kỳ', 'năm', 'ngày', 'ngay')
                time_cols = [c for c in columns_lower
                             if any(k in c for k in ['month', 'date', 'week', 'quarter', 'year', 'sale_date', 'saledate', 'tu_ngay', 'time', 'period'])
                             or c.startswith(_vn_time_starts)]
                
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

        # Banner — 3 mức theo active_backend: "postgres" = không banner; "bravo" = banner nhẹ, LUÔN
        # hiện khi dùng Bravo (nguồn CHÍNH từ 09/07/2026, không còn là fallback do lỗi — xem
        # _resolve_active_backend), chỉ để nhắc thiếu tồn kho/KPI (công nợ ĐÃ hỗ trợ từ 09/07/2026,
        # xem mart_layer_instruction), không suy diễn Supabase có lỗi hay không; "sqlite" = banner
        # mạnh (cả Bravo lẫn Postgres đều không dùng được).
        if active_backend == "bravo":
            answer = (
                "ℹ️ <b>Dữ liệu trực tiếp từ Bravo</b> — số liệu hóa đơn/khách hàng/công nợ chính xác, "
                "real-time, nhưng KHÔNG có tồn kho/KPI (chỉ có trên Supabase).\n\n" + answer
            )
        elif cloud_unreachable_fallback and active_backend == "sqlite":
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

        # Ghi cache — chỉ khi KHÔNG có lỗi (không cache lỗi tạm thời như Bravo/Postgres timeout,
        # tránh lặp lại lỗi đã qua trong 5 phút tới) và KHÔNG có lịch sử hội thoại (xem điều kiện
        # đọc cache ở đầu ask(), self._query_cache). Dọn rác (entry hết hạn) mỗi lần ghi để cache
        # không phình vô hạn qua thời gian chạy dài của service.
        if not history_block and not self.is_mock and "error" not in query_result:
            self._query_cache = {
                k: v for k, v in self._query_cache.items()
                if (_time.time() - v["ts"]) < self._QUERY_CACHE_TTL_SECONDS
            }
            self._query_cache[cache_key] = {"result": dict(result), "ts": _time.time()}

        self._remember_turn(session_key, user_question, result["answer"])
        return result

    def _quick_format_single_row(self, columns, row):
        """Ghép câu nhanh cho kết quả CHỈ 1 dòng, không gọi AI — dùng khi câu hỏi rõ ràng chỉ cần
        vài con số tổng hợp (vd 'doanh thu hôm nay bao nhiêu'), tiết kiệm ~4-10s gọi AI lần 2 chỉ
        để diễn giải. Tên cột đã được AI sinh SQL alias sang tiếng Việt sẵn (AS "Tên tiếng Việt"),
        nên chỉ cần format giá trị, không cần dịch tên cột như _format_heuristically()."""
        if not row:
            return "Hiện tại chưa có dữ liệu cho truy vấn này"

        def _fmt_val(col, val):
            if val is None:
                return "—"
            col_lower = (col or "").lower()
            if _is_money_col(col_lower):
                try:
                    v = float(val)
                    if abs(v) >= 1_000_000_000:
                        return f"{v / 1_000_000_000:.2f} tỷ đ".replace('.', ',')
                    elif abs(v) >= 1_000_000:
                        return f"{v / 1_000_000:.1f} triệu đ".replace('.', ',')
                    else:
                        return f"{v:,.0f} đ".replace(',', '.')
                except (ValueError, TypeError):
                    return str(val)
            if any(k in col_lower for k in ['%', 'percent', 'pct', 'tỷ lệ', 'ty le']):
                try:
                    v = float(val)
                    if abs(v) <= 2.0:
                        v *= 100
                    return f"{v:.1f}%".replace('.', ',')
                except (ValueError, TypeError):
                    return str(val)
            return str(val)

        parts = [f"{col}: <b>{_fmt_val(col, row.get(col))}</b>" for col in columns]
        return ", ".join(parts) + "."

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
        matplotlib.rcParams['axes.edgecolor'] = _CHART_GRID
        matplotlib.rcParams['axes.titlecolor'] = _CHART_INK
        matplotlib.rcParams['text.color'] = _CHART_INK
        matplotlib.rcParams['axes.labelcolor'] = _CHART_INK
        matplotlib.rcParams['xtick.color'] = _CHART_SLATE
        matplotlib.rcParams['ytick.color'] = _CHART_SLATE
        colors = _CHART_PALETTE
        
        # Unified identification of true metrics vs category/dimension columns.
        # QUAN TRỌNG: cột mã/code (ví dụ "Mã sản phẩm" = '74260010030') là chuỗi số nên float()
        # thành công và dễ bị nhầm là SỐ ĐO rồi bị đem vẽ chart (bug: biểu đồ vẽ theo mã sản phẩm
        # thay vì số lượng). Phải loại các cột mã/id theo TÊN — kể cả tiếng Việt ('mã', 'sku').
        _code_hints = ['id', 'code', 'symbol', 'number', 'stt', 'mã', 'sku']
        numeric_cols = []
        cat_cols = []
        for col in columns:
            col_lower = col.lower()
            if any(k in col_lower for k in _code_hints):
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

        # Tách chỉ số CHÍNH (doanh thu/số lượng...) khỏi chỉ số PHỤ dạng tỷ lệ/phái sinh
        # ("% so với tháng trước", "Tỷ lệ KM (%)", "TB bán/ngày"...) — chỉ số phụ không vẽ
        # thành cột cùng trục với tiền, chỉ có thể làm đường % trên trục thứ 2.
        _aux_hints = ['%', 'tỷ lệ', 'ty le', 'percent', 'pct', 'rate', 'tb ', '/ngày', '/ngay',
                      'so với', 'so voi', 'tăng trưởng', 'tang truong', 'còn lại', 'con lai', 'số tháng', 'so thang']
        primary_metrics = [c for c in numeric_cols if not any(h in c.lower() for h in _aux_hints)]
        aux_pct_cols = [c for c in numeric_cols
                        if any(h in c.lower() for h in ['%', 'tỷ lệ', 'ty le', 'percent', 'pct', 'rate'])]
        if primary_metrics:
            num_col = primary_metrics[0]

        # Kết quả có >= 2 chỉ số chính (vd Doanh thu OTC + Doanh thu ETC theo tuần) mà loại chart
        # được chọn chỉ vẽ 1 chỉ số -> nâng cấp thành biểu đồ CỤM để không bỏ rơi chỉ số còn lại.
        if len(primary_metrics) >= 2 and visual_type in ("Bar_Chart", "Horizontal_Bar_Chart", "Line_Chart"):
            visual_type = "Line_and_Stacked_Column_Chart"

        # Ngữ cảnh style: tiền hay số đếm; chỉ số "xấu" (nợ/quá hạn) tô đỏ, còn lại xanh brand + cam nhấn.
        _money = _is_money_col(num_col)
        _bad = _is_bad_col(num_col)
        _base_color = _CHART_SLATE if _bad else _CHART_GREEN
        _hi_color = _CHART_RED if _bad else _CHART_ORANGE

        # Chọn 1 cột NHÃN mô tả (tên KH/sản phẩm/nhân viên) thay vì ghép cả mã + đơn vị vào nhãn.
        _name_hints = ['tên', 'ten', 'name', 'khách', 'khach', 'sản phẩm', 'san pham',
                       'mặt hàng', 'mat hang', 'nhân viên', 'nhan vien', 'đại lý', 'dai ly',
                       'product', 'customer', 'employee']
        _unit_hints = ['đơn vị', 'don vi', 'unit']
        # Loại cột mã/code TRƯỚC (một cột mã không bao giờ là nhãn), rồi mới ưu tiên cột tên.
        # Nếu không loại trước, hint 'sản phẩm' khớp nhầm cả "Mã sản phẩm" lẫn "Tên sản phẩm".
        _noncode_cats = [c for c in cat_cols if not any(s in c.lower() for s in _code_hints)]
        label_col = next((c for c in _noncode_cats if any(h in c.lower() for h in _name_hints)), None)
        if label_col is None:
            label_col = next((c for c in _noncode_cats if not any(u in c.lower() for u in _unit_hints)), None)
        if label_col is None:
            label_col = _noncode_cats[0] if _noncode_cats else cat_col
        
        fig, ax = None, None
        
        if visual_type == "KPI_Card":
            metric_name = "Chỉ số"
            metric_value = "0"
            
            def _kpi_fmt(colname, num_val):
                cl = colname.lower()
                if any(k in cl for k in ['percent', 'pct', 'rate', 'tỷ lệ', 'ty le', '(%)', 'hoàn thành', 'hoan thanh']):
                    v = num_val * 100 if abs(num_val) <= 2.0 else num_val
                    return f"{v:.1f}%".replace('.', ',')
                if _is_money_col(colname):
                    a = abs(num_val)
                    if a >= 1_000_000_000:
                        return f"{num_val*1e-9:.2f} tỷ đ".replace('.', ',')
                    elif a >= 1_000_000:
                        return f"{num_val*1e-6:.1f} triệu đ".replace('.', ',')
                    else:
                        return f"{num_val:,.0f} đ".replace(',', '.')
                return f"{num_val:,.0f}".replace(',', '.')

            if cat_cols and numeric_cols:
                metric_name = str(rows[0].get(cat_cols[0], "Chỉ số"))
                num_val = float(rows[0].get(numeric_cols[0], 0))
                metric_value = _kpi_fmt(numeric_cols[0], num_val)
            elif numeric_cols:
                metric_name = numeric_cols[0]
                num_val = float(rows[0].get(numeric_cols[0], 0))
                metric_value = _kpi_fmt(numeric_cols[0], num_val)
                
            fig, ax = plt.subplots(figsize=(4, 2.5), dpi=150)
            fig.patch.set_facecolor('#f8f9fa')
            ax.set_facecolor('#f8f9fa')
            ax.axis('off')
            
            # Fix layering by adding the rectangle to the axis block with zorder=0
            rect = plt.Rectangle((0.02, 0.02), 0.96, 0.96, transform=fig.transFigure,
                                 facecolor='#ffffff', edgecolor='#e2e8f0', linewidth=1.5, zorder=0)
            ax.add_patch(rect)
            
            # Draw text with high zorder
            ax.text(0.5, 0.7, metric_name, fontsize=12, fontweight='bold', color=_CHART_SLATE, ha='center', va='center', zorder=5)
            ax.text(0.5, 0.4, metric_value, fontsize=22, fontweight='bold', color=(_CHART_RED if _bad else _CHART_GREEN), ha='center', va='center', zorder=5)
            
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
            
            fig, ax = plt.subplots(figsize=(8.5, 5), dpi=150)
            sns.lineplot(x=labels, y=values, marker='o', linewidth=2.6, color=_CHART_GREEN, markerfacecolor=_CHART_ORANGE, ax=ax, errorbar=None)
            ax.fill_between(labels, values, alpha=0.12, color=_CHART_GREEN)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=20, ha='right')
            ax.set_title(f"Xu hướng {num_col}", fontweight='bold', fontsize=13, pad=14, loc='left')
            ax.grid(True, linestyle='--', alpha=0.35, color=_CHART_GRID)

        elif visual_type == "Bar_Chart":
            plot_rows = rows[:12]
            # Try to find the category/time label column among actual columns
            _time_keywords = ['month', 'date', 'thang', 'ngay', 'week', 'quarter', 'year', 'sale_date', 'saledate', 'period', 'time']
            actual_label_col = next((c for c in columns if any(k in c.lower() for k in _time_keywords)), label_col)
            formatted_labels = _fmt_time_labels([r.get(actual_label_col, '') for r in plot_rows])
            values = [float(r.get(num_col, 0) or 0) for r in plot_rows]
            max_val = max(values) if values else 1

            fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
            bar_colors = [_hi_color if v == max_val else _base_color for v in values]
            bars = ax.bar(range(len(formatted_labels)), values, color=bar_colors, edgecolor='white', linewidth=1.2, width=0.62)

            # Value labels on top of bars
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max_val * 0.02,
                        _fmt_chart_val(val, _money), ha='center', va='bottom', fontsize=9.5, fontweight='bold', color=_CHART_INK)

            ax.set_xticks(range(len(formatted_labels)))
            ax.set_xticklabels(formatted_labels, rotation=20, ha='right', fontsize=10)
            ax.set_ylim(0, max_val * 1.16)
            ax.set_title(f"{num_col} theo thời gian", fontweight='bold', fontsize=13, pad=14, loc='left')
            ax.grid(True, linestyle='--', alpha=0.35, axis='y', color=_CHART_GRID)
            ax.grid(False, axis='x')
            ax.set_axisbelow(True)

        elif visual_type == "Line_and_Stacked_Column_Chart":
            # Cột = các chỉ số CHÍNH cùng loại (tối đa 3, vd Doanh thu OTC / ETC / Tổng);
            # đường % (nếu có cột tỷ lệ) vẽ trên trục thứ 2. Giữ nguyên thứ tự dòng từ SQL
            # (chuỗi thời gian đã ORDER BY thời gian, không sắp lại theo giá trị).
            bar_cols = (primary_metrics if len(primary_metrics) >= 2 else numeric_cols)[:3]
            if len(bar_cols) < 2:
                return None

            plot_rows = rows[:15]
            labels = _fmt_time_labels([r.get(label_col, '') for r in plot_rows])

            fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
            x = np.arange(len(labels))
            n_bars = len(bar_cols)
            width = 0.78 / n_bars
            _bar_palette = [_CHART_GREEN, _CHART_ORANGE, _CHART_SLATE]

            for i, col in enumerate(bar_cols):
                vals = [float(r.get(col, 0) or 0) for r in plot_rows]
                offset = (i - (n_bars - 1) / 2) * width
                ax.bar(x + offset, vals, width, label=col, color=_bar_palette[i % 3], alpha=0.95, edgecolor='white')

            line_col = next((c for c in aux_pct_cols if c not in bar_cols), None)
            if line_col:
                val3 = [float(r.get(line_col, 0) or 0) for r in plot_rows]
                if all(abs(v) <= 2.0 for v in val3):
                    val3 = [v * 100 for v in val3]
                ax2 = ax.twinx()
                ax2.plot(x, val3, color=_CHART_INK, marker='o', linewidth=2.2, linestyle='--', label=line_col)
                ax2.set_ylabel(f"{line_col}")
                ax2.grid(False)
                lines, labels_l = ax.get_legend_handles_labels()
                lines2, labels_l2 = ax2.get_legend_handles_labels()
                ax.legend(lines + lines2, labels_l + labels_l2, loc='best', frameon=False)
            else:
                ax.legend(loc='best', frameon=False)

            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=15, ha='right')
            ax.set_title(" vs ".join(bar_cols[:2]) + (" ..." if n_bars > 2 else ""), fontweight='bold', fontsize=13, pad=14, loc='left')
            ax.grid(True, linestyle='--', alpha=0.35, axis='y', color=_CHART_GRID)
            ax.grid(False, axis='x')
            ax.set_axisbelow(True)

        elif visual_type == "Pie_Chart":
            plot_rows = rows[:15]
            labels = [str(r.get(label_col, '')) for r in plot_rows]
            values = [float(r.get(num_col, 0) or 0) for r in plot_rows]
            
            pie_data = [(l, v) for l, v in zip(labels, values) if v > 0]
            
            fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
            if pie_data:
                p_labels, p_values = zip(*pie_data)
                pie_colors = [_CHART_PALETTE[i % len(_CHART_PALETTE)] for i in range(len(p_labels))]
                wedges, _t, _a = ax.pie(p_values, labels=p_labels, autopct='%1.1f%%', startangle=90, colors=pie_colors,
                       pctdistance=0.78, wedgeprops={'edgecolor': 'white', 'linewidth': 2})
                for a in _a:
                    a.set_color('white'); a.set_fontweight('bold'); a.set_fontsize(10)
                ax.axis('equal')
                ax.set_title(f"Cơ cấu {num_col}", fontweight='bold', fontsize=13, pad=14)
            else:
                sns.barplot(x=labels, y=values, color='#3182ce', alpha=0.9, ax=ax)
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha='right')

        elif visual_type == "Horizontal_Bar_Chart":
            sorted_rows = sorted(rows, key=lambda x: float(x.get(num_col, 0) or 0), reverse=True)[:15]
            labels = [str(r.get(label_col, '')) for r in sorted_rows]
            labels = [l[:25] + '...' if len(l) > 25 else l for l in labels]
            values = [float(r.get(num_col, 0) or 0) for r in sorted_rows]
            max_val = max(values) if values else 1

            fig, ax = plt.subplots(figsize=(9.5, 5.8), dpi=150)
            # Cột thường màu brand (hoặc slate nếu là chỉ số "xấu"), cột cao nhất tô màu nhấn
            bar_colors = [_hi_color if v == max_val else _base_color for v in values]
            bars = ax.barh(range(len(labels)), values, color=bar_colors, edgecolor='white', height=0.66)

            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels, fontsize=10, fontweight='bold', color=_CHART_INK)
            ax.invert_yaxis()  # Top-down ranking

            # Value labels at the end of bars
            for bar, val in zip(bars, values):
                ax.text(bar.get_width() + max_val * 0.015, bar.get_y() + bar.get_height()/2,
                        ' ' + _fmt_chart_val(val, _money), ha='left', va='center', fontsize=9.5, fontweight='bold', color=_CHART_INK)

            ax.set_xlim(0, max_val * 1.18)
            ax.set_title(f"Xếp hạng theo {num_col}", fontweight='bold', fontsize=13, pad=14, loc='left')
            ax.grid(True, linestyle='--', alpha=0.35, axis='x', color=_CHART_GRID)
            ax.grid(False, axis='y')
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
            ax.spines['left'].set_color(_CHART_GRID)
            ax.spines['bottom'].set_color(_CHART_GRID)

            from matplotlib.ticker import FuncFormatter
            _tick_fmt = FuncFormatter(lambda x, pos: _fmt_chart_val(x, _money))

            # Bar/HBar đã có nhãn giá trị trên từng cột → bỏ nhãn trục giá trị cho gọn (tránh trùng lặp,
            # tránh "50.0B" tiếng Anh). Các loại khác giữ trục nhưng format kiểu VN (tỷ/tr/M).
            if visual_type == "Horizontal_Bar_Chart":
                ax.set_xticks([])
            elif visual_type == "Bar_Chart":
                ax.set_yticks([])
            elif visual_type not in ("Pie_Chart", "KPI_Card"):
                ax.yaxis.set_major_formatter(_tick_fmt)
                    
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

