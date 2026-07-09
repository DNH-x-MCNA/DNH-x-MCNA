"""
Tạo thêm index để hỗ trợ query sargable (xem ai_agent/chatbot.py rule sinh SQL) — giảm Disk IO
bằng cách để Postgres dùng index thay vì full table scan.

QUAN TRỌNG: CREATE INDEX tốn IO thật khi chạy (phải quét toàn bảng để build index) — KHÔNG chạy
script này khi Supabase đang cạn Disk IO budget. Chỉ chạy khi IO đã hồi phục hoặc vào giờ thấp
điểm. Dùng CREATE INDEX CONCURRENTLY để không khóa bảng trong lúc build (an toàn hơn cho hệ thống
đang có traffic thật), đổi lại KHÔNG chạy được trong 1 transaction nên script tự dùng autocommit.

Chạy: python scripts/add_performance_indexes.py
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
url = os.getenv("CLOUD_DB_URL", "").strip()
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

# Composite (DocDate, IsActive) — hầu hết query đều lọc "IsActive=TRUE AND DocDate trong khoảng",
# 1 index gộp cả 2 điều kiện hiệu quả hơn 2 index riêng (tránh Postgres phải bitmap-AND).
# DocDate đứng trước vì đó thường là điều kiện chọn lọc mạnh nhất (thu hẹp về ~1 tháng).
STATEMENTS = [
    ('brv_hoadonhdr', 'idx_brvhdr_docdate_active',
     'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_brvhdr_docdate_active ON brv_hoadonhdr ("DocDate", "IsActive")'),
    ('brvsx_hoadonhdr', 'idx_brvsxhdr_docdate_active',
     'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_brvsxhdr_docdate_active ON brvsx_hoadonhdr ("DocDate", "IsActive")'),
]

engine = create_engine(url, connect_args={'connect_timeout': 15})
# CREATE INDEX CONCURRENTLY không được chạy trong transaction block -> autocommit
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    for table, idx_name, stmt in STATEMENTS:
        print(f"[*] Tao {idx_name} tren {table} (CONCURRENTLY, khong khoa bang)...")
        try:
            conn.execute(text(stmt))
            print(f"    -> OK")
        except Exception as e:
            print(f"    -> LOI: {e}")

print("\nXong. Kiem tra lai bang: SELECT indexname FROM pg_indexes WHERE tablename IN ('brv_hoadonhdr','brvsx_hoadonhdr');")
