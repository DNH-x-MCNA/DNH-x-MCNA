"""
Clone một bản sao dữ liệu từ Supabase production sang Supabase dev/test.

Mục đích: cho nhà phát triển 1 bản sao dữ liệu thật (đã qua ETL, sạch) để code/thử nghiệm
mà không đụng vào dữ liệu production. KHÔNG kết nối Bravo/DMS, KHÔNG chạy nền/daemon —
chạy tay khi cần: `python scripts/clone_to_dev_supabase.py [--months 6]`.

Lưu ý: production hiện đang chập chờn (statement_timeout 2 phút ép cứng, thỉnh thoảng cả
connection SSL bị đứt ngang giữa chừng) — nhiều khả năng do compute tier thấp + 2 service
đồng bộ/cảnh báo (DNH_Supabase_Sync, DNH_Realtime_Alerts) chạy liên tục cạnh tranh tài nguyên.
Vì vậy MỖI LẦN ĐỌC đều mở connection MỚI và tự thử lại (không tái sử dụng 1 connection cho cả
quá trình — connection cũ có thể đã chết). Script tự BỎ QUA các bảng đã clone xong ở lần chạy
trước (dùng --force để ép clone lại từ đầu), và bỏ qua bảng chi tiết cho các tháng mà bảng
header không có dòng nào (tránh JOIN lãng phí).
"""
import argparse
import os
import sys
import time
from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# Bảng dim/mart nhỏ -> copy toàn bộ, không lọc theo thời gian.
FULL_COPY_TABLES = [
    "dms_khachhang",
    "dmssx_khachhang",
    "receivable_detail",
    "inventory",
    "kpi_summary",
    "dim_nhanvien",
    "dim_tinhthanhpho",
    "brv_sanpham",
    "brv_trangthaiduyet",
    "brv_trangthaihoadon",
]

# View ở production -> vật chất hóa thành bảng thường (snapshot) ở dev.
VIEW_TABLES = ["vw_hoadon_otc", "vw_hoadon_etc"]

WRITE_CHUNKSIZE = 1000  # ghi theo lô nhỏ, tránh 1 câu INSERT khổng lồ cũng bị statement_timeout
STT_BATCH_SIZE = 500    # số Stt/lần khi lọc bảng chi tiết — production hiện rất chậm, cần lô nhỏ


def read_sql_retry(query, engine, params=None, retries=5, backoff_seconds=15):
    """Mở connection MỚI mỗi lần thử (không tái dùng connection cũ có thể đã chết vì SSL đứt/
    hết pool). Production hiện chập chờn nên cần thử lại nhiều lần."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                return pd.read_sql(query, conn, params=params)
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = backoff_seconds * attempt
                print(f"    [Cảnh báo] Lỗi lần {attempt}/{retries}: {type(e).__name__}. Thử lại sau {wait}s...")
                time.sleep(wait)
    raise last_err


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def table_already_cloned(dst_engine, table_name: str) -> bool:
    """Bảng đã tồn tại và có dữ liệu ở dev -> coi như đã clone xong, bỏ qua khi retry."""
    ins = inspect(dst_engine)
    if not ins.has_table(table_name):
        return False
    with dst_engine.connect() as conn:
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
    return count > 0


def month_ranges(months: int):
    """Sinh danh sách (start, end) theo từng tháng, từ (months-1) tháng trước tới hết tháng này."""
    today = date.today()
    first_of_this_month = today.replace(day=1)
    ranges = []
    for i in range(months - 1, -1, -1):
        start = first_of_this_month - relativedelta(months=i)
        end = start + relativedelta(months=1)
        ranges.append((start, end))
    return ranges


def write_chunk(dst_engine, table_name: str, df: pd.DataFrame, first_chunk: bool):
    if first_chunk:
        with dst_engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        if_exists = 'replace'
    else:
        if_exists = 'append'
    df.to_sql(table_name, dst_engine, if_exists=if_exists, index=False, chunksize=WRITE_CHUNKSIZE, method='multi')


def clone_header_table_by_month(prod_engine, dst_engine, table_name: str, date_col: str, months: int, force: bool):
    if not force and table_already_cloned(dst_engine, table_name):
        print(f"'{table_name}' đã có dữ liệu ở dev (bỏ qua, dùng --force nếu muốn clone lại).")
        return {}

    print(f"Đang đọc '{table_name}' từ production (theo từng tháng, {months} tháng gần nhất)...")
    total = 0
    month_counts = {}
    first_written = False
    for start, end in month_ranges(months):
        query = text(f'SELECT * FROM "{table_name}" WHERE "{date_col}"::date >= :start AND "{date_col}"::date < :end')
        df = read_sql_retry(query, prod_engine, params={"start": start, "end": end})
        print(f"  - Tháng {start.isoformat()}: {len(df)} dòng.")
        month_counts[start] = len(df)
        # CHỈ ghi khi df thật sự có dữ liệu — bỏ qua hoàn toàn tháng rỗng, kể cả tháng đầu tiên.
        # Tạo schema bảng từ lô ĐẦU TIÊN CÓ DỮ LIỆU (không phải tháng đầu tiên theo thời gian) —
        # nếu ghi từ DataFrame rỗng, pandas suy luận kiểu cột sẽ ra toàn TEXT.
        if not df.empty:
            write_chunk(dst_engine, table_name, df, first_chunk=(not first_written))
            first_written = True
        total += len(df)
    print(f"  -> Đã ghi '{table_name}' vào Supabase dev ({total} dòng).")
    return month_counts


def get_stt_by_month_from_dev(dst_engine, header_table: str, join_col: str, date_col: str, months: int):
    """Header đã clone xong ở dev -> lấy danh sách Stt theo tháng từ DEV (nhanh, không tốn production)."""
    result = {}
    with dst_engine.connect() as conn:
        for start, end in month_ranges(months):
            rows = conn.execute(text(f'''
                SELECT "{join_col}" FROM "{header_table}"
                WHERE "{date_col}"::date >= :start AND "{date_col}"::date < :end
            '''), {"start": start, "end": end}).fetchall()
            result[start] = [r[0] for r in rows]
    return result


def clone_detail_table_by_month(prod_engine, dst_engine, detail_table: str, header_table: str, join_col: str,
                                 date_col: str, months: int, force: bool):
    """Bảng chi tiết (vd brv_hoadonct) không có cột ngày riêng. Vì '{join_col}' đã có index ở CẢ
    2 bảng (header và chi tiết), thay vì JOIN qua production (chậm do header không có index trên
    date_col), lấy danh sách Stt theo tháng từ bản header ĐÃ CLONE Ở DEV rồi lọc chi tiết ở
    production bằng "{join_col}" = ANY(...) — dùng thẳng index, nhẹ hơn nhiều."""
    if not force and table_already_cloned(dst_engine, detail_table):
        print(f"'{detail_table}' đã có dữ liệu ở dev (bỏ qua, dùng --force nếu muốn clone lại).")
        return
    if not table_already_cloned(dst_engine, header_table):
        print(f"[Lỗi]: '{header_table}' chưa có ở dev — cần clone header trước khi clone '{detail_table}'.")
        return

    print(f"Đang đọc '{detail_table}' (lọc theo Stt của '{header_table}' lấy từ dev, theo từng tháng, lô {STT_BATCH_SIZE} Stt/lần)...")
    stt_by_month = get_stt_by_month_from_dev(dst_engine, header_table, join_col, date_col, months)
    total = 0
    first_written = False
    for start, stt_list in stt_by_month.items():
        if not stt_list:
            print(f"  - Tháng {start.isoformat()}: bỏ qua (header không có dòng nào tháng này).")
            continue
        month_total = 0
        for batch_start in range(0, len(stt_list), STT_BATCH_SIZE):
            batch = stt_list[batch_start:batch_start + STT_BATCH_SIZE]
            query = text(f'SELECT * FROM "{detail_table}" WHERE "{join_col}" = ANY(:stt_list)')
            df = read_sql_retry(query, prod_engine, params={"stt_list": batch})
            if not df.empty:
                write_chunk(dst_engine, detail_table, df, first_chunk=(not first_written))
                first_written = True
            month_total += len(df)
        print(f"  - Tháng {start.isoformat()}: {month_total} dòng ({len(stt_list)} Stt, {(-(-len(stt_list)//STT_BATCH_SIZE))} lô).")
        total += month_total
    print(f"  -> Đã ghi '{detail_table}' vào Supabase dev ({total} dòng).")


def clone_full_table(prod_engine, dst_engine, table_name: str, force: bool):
    if not force and table_already_cloned(dst_engine, table_name):
        print(f"'{table_name}' đã có dữ liệu ở dev (bỏ qua, dùng --force nếu muốn clone lại).")
        return

    print(f"Đang đọc '{table_name}' từ production (toàn bộ)...")
    query = text(f'SELECT * FROM "{table_name}"')
    df = read_sql_retry(query, prod_engine)
    print(f"  -> {len(df)} dòng.")
    write_chunk(dst_engine, table_name, df, first_chunk=True)
    print(f"  -> Đã ghi '{table_name}' vào Supabase dev ({len(df)} dòng).")


def main():
    parser = argparse.ArgumentParser(description="Clone dữ liệu Supabase production sang Supabase dev/test")
    parser.add_argument('--months', type=int, default=6, help='Số tháng gần nhất lấy cho các bảng giao dịch lớn (mặc định 6)')
    parser.add_argument('--force', action='store_true', help='Clone lại từ đầu kể cả bảng đã có dữ liệu ở dev')
    args = parser.parse_args()

    prod_url = os.getenv("CLOUD_DB_URL", "")
    dev_url = os.getenv("DEV_CLOUD_DB_URL", "")

    if not prod_url:
        print("[Lỗi]: Chưa cấu hình CLOUD_DB_URL trong .env (nguồn production).")
        sys.exit(1)
    if not dev_url:
        print("[Lỗi]: Chưa cấu hình DEV_CLOUD_DB_URL trong .env (đích Supabase dev/test).")
        print("Tạo 1 Supabase project mới, lấy connection string Postgres, điền vào .env.")
        sys.exit(1)

    # pool_size nhỏ + pool_recycle ngắn: mỗi read_sql_retry tự mở/đóng connection riêng, không
    # giữ 1 connection sống lâu (dễ bị SSL đứt ngang trên production đang chập chờn).
    prod_engine = create_engine(normalize_url(prod_url), pool_pre_ping=True, pool_size=2,
                                 max_overflow=0, pool_timeout=60, pool_recycle=60)
    dev_engine = create_engine(normalize_url(dev_url), pool_pre_ping=True)

    print("=" * 60)
    print(f"CLONE DỮ LIỆU PRODUCTION -> DEV/TEST SUPABASE (cửa sổ {args.months} tháng cho bảng giao dịch)")
    print("=" * 60)

    clone_header_table_by_month(prod_engine, dev_engine, "brv_hoadonhdr", "DocDate", args.months, args.force)
    clone_header_table_by_month(prod_engine, dev_engine, "brvsx_hoadonhdr", "DocDate", args.months, args.force)
    clone_detail_table_by_month(prod_engine, dev_engine, "brv_hoadonct", "brv_hoadonhdr", "Stt", "DocDate", args.months, args.force)
    clone_detail_table_by_month(prod_engine, dev_engine, "brvsx_hoadonct", "brvsx_hoadonhdr", "Stt", "DocDate", args.months, args.force)

    for table in FULL_COPY_TABLES:
        clone_full_table(prod_engine, dev_engine, table, args.force)

    for view in VIEW_TABLES:
        clone_full_table(prod_engine, dev_engine, view, args.force)

    prod_engine.dispose()
    dev_engine.dispose()

    print("=" * 60)
    print("[Thành công]: Đã clone xong dữ liệu sang Supabase dev/test!")
    print("=" * 60)


if __name__ == "__main__":
    main()
