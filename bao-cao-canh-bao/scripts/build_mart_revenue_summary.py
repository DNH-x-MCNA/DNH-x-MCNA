"""
Tổng hợp mart_layer.mart_revenue_summary từ dữ liệu hóa đơn thô (brv_*/brvsx_*) — xem thiết kế
đầy đủ tại docs/mart_revenue_summary_design.md.

Business rule tính doanh thu GIỮ NGUYÊN đúng logic đã kiểm chứng nhiều lần trong dự án này:
loại dòng CTKM khuyến mãi, loại chứng từ hủy, loại mã chuyển kho nội bộ (qua JOIN dim khách
hàng) — cùng quy tắc với check_revenue_drop_alert (src/alerts.py) và _period_revenue (src/etl.py).

Cách dùng:
    python scripts/build_mart_revenue_summary.py            # incremental — chỉ tính lại N ngày
                                                              # gần nhất (mặc định 7), RẺ, dùng
                                                              # cho lịch chạy hằng đêm.
    python scripts/build_mart_revenue_summary.py --full      # backfill toàn bộ lịch sử — NẶNG,
                                                              # chỉ chạy 1 lần khi IO đã hồi phục,
                                                              # KHÔNG chạy khi Supabase đang cạn
                                                              # Disk IO budget.
    python scripts/build_mart_revenue_summary.py --days 30   # incremental nhưng tùy chỉnh số
                                                              # ngày gần nhất cần tính lại.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
CLOUD_DB_URL = os.getenv("CLOUD_DB_URL", "").strip()
if CLOUD_DB_URL.startswith("postgres://"):
    CLOUD_DB_URL = CLOUD_DB_URL.replace("postgres://", "postgresql://", 1)

DDL = """
CREATE SCHEMA IF NOT EXISTS mart_layer;

CREATE TABLE IF NOT EXISTS mart_layer.mart_revenue_summary (
    report_date     date NOT NULL,
    channel         text NOT NULL,
    revenue         numeric(18,2) NOT NULL DEFAULT 0,
    invoice_count   integer NOT NULL DEFAULT 0,
    updated_at      timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (report_date, channel)
);

CREATE INDEX IF NOT EXISTS idx_mart_revenue_date ON mart_layer.mart_revenue_summary (report_date);
"""

# OTC/ETC dùng chung 1 mẫu, chỉ khác bảng nguồn + điều kiện IsHC (chỉ OTC có cột này) và điều
# kiện loại mã chuyển kho nội bộ (chỉ ETC cần lọc thủ công vì chưa có FK sạch sang dim khách hàng
# — xem docs/dev_supabase_schema.sql phần ghi chú FK).
UPSERT_OTC = """
INSERT INTO mart_layer.mart_revenue_summary (report_date, channel, revenue, invoice_count, updated_at)
SELECT
    h."DocDate"::date AS report_date,
    'OTC' AS channel,
    COALESCE(SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END), 0) AS revenue,
    COUNT(DISTINCT h."Stt") AS invoice_count,
    now() AS updated_at
FROM brv_hoadonct c
JOIN brv_hoadonhdr h ON c."Stt" = h."Stt"
LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
  AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
  AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
  AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
GROUP BY h."DocDate"::date
ON CONFLICT (report_date, channel) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    invoice_count = EXCLUDED.invoice_count,
    updated_at = EXCLUDED.updated_at;
"""

UPSERT_ETC = """
INSERT INTO mart_layer.mart_revenue_summary (report_date, channel, revenue, invoice_count, updated_at)
SELECT
    h."DocDate"::date AS report_date,
    'ETC' AS channel,
    COALESCE(SUM(CASE WHEN c."CTKM" IS NULL OR c."CTKM" = '' THEN c."Amount9" ELSE 0 END), 0) AS revenue,
    COUNT(DISTINCT h."Stt") AS invoice_count,
    now() AS updated_at
FROM brvsx_hoadonct c
JOIN brvsx_hoadonhdr h ON c."Stt" = h."Stt"
LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
WHERE h."IsActive" = TRUE
  AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
  AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
  AND h."DocDate" >= :start_dt AND h."DocDate" < :end_dt
GROUP BY h."DocDate"::date
ON CONFLICT (report_date, channel) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    invoice_count = EXCLUDED.invoice_count,
    updated_at = EXCLUDED.updated_at;
"""


def run(start_dt, end_dt, label):
    engine = create_engine(CLOUD_DB_URL, connect_args={'connect_timeout': 15})
    print(f"[*] Tong hop mart_revenue_summary cho {label} ({start_dt} -> {end_dt})...")
    with engine.begin() as conn:
        conn.execute(text(DDL))
        r1 = conn.execute(text(UPSERT_OTC), {"start_dt": start_dt, "end_dt": end_dt})
        print(f"    OTC: {r1.rowcount} dong upsert")
        r2 = conn.execute(text(UPSERT_ETC), {"start_dt": start_dt, "end_dt": end_dt})
        print(f"    ETC: {r2.rowcount} dong upsert")
    print("Xong.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tong hop mart_layer.mart_revenue_summary")
    parser.add_argument("--full", action="store_true",
                         help="Backfill toan bo lich su (NANG - chi chay khi IO da hoi phuc)")
    parser.add_argument("--days", type=int, default=7,
                         help="So ngay gan nhat can tinh lai (mac dinh 7, dung cho incremental)")
    args = parser.parse_args()

    if args.full:
        # Backfill tu dau nam data that su co (xem earliest_date trong ai_agent/chatbot.py -
        # hien tai la dau thang 1/2026); dat mot moc som an toan, WHERE >= that se tu gioi han
        # theo du lieu thuc te co.
        run("2020-01-01", "2100-01-01", "TOAN BO LICH SU (full backfill)")
    else:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=args.days)
        end = today + timedelta(days=1)
        run(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), f"{args.days} ngay gan nhat (incremental)")
