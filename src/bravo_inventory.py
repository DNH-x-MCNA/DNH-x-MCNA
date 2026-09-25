"""Ton kho OTC+ETC tinh TRUC TIEP tu Bravo - dung cho canh bao/digest (src/alerts.py).

25/09/2026: tach khoi scripts/sync_from_bravo_to_supabase.py khi bo han Supabase. Truoc day src/alerts.py import
hai ham nay tu script dong bo Supabase - ma script do sys.exit(1) ngay luc import neu thieu CLOUD_DB_URL, nen bo
Supabase khoi .env se lam canh bao ton kho am tham tra rong. Cong thuc giu nguyen tung dong (chi doi noi chua).
Chi doc (SELECT) tren Bravo.
"""
import os
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def get_sql_server_connection():
    """Ket noi pyodbc CHI DOC toi Bravo tu BRAVO_SQL_* trong .env (giong src/database.py::_get_bravo_engine)."""
    import pyodbc
    thieu = [k for k in ("BRAVO_SQL_SERVER", "BRAVO_SQL_DATABASE", "BRAVO_SQL_UID", "BRAVO_SQL_PWD")
             if not (os.getenv(k) or "").strip()]
    if thieu:
        raise RuntimeError("Thieu " + ", ".join(thieu) + " trong .env - khong ket noi duoc Bravo.")
    return pyodbc.connect(
        "DRIVER={SQL Server};"
        f"SERVER={os.getenv('BRAVO_SQL_SERVER').strip()};"
        f"DATABASE={os.getenv('BRAVO_SQL_DATABASE').strip()};"
        f"UID={os.getenv('BRAVO_SQL_UID').strip()};"
        f"PWD={os.getenv('BRAVO_SQL_PWD').strip()};"
        "TrustServerCertificate=yes;"
    )


def clean_dataframe(df):
    """Làm sạch kiểu dữ liệu để tương thích với PostgreSQL."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
    return df



def build_inventory_dataframe(sql_conn):
    """
    Tính DataFrame tồn kho (OTC+ETC) từ Bravo — TÁCH RIÊNG khỏi sync_inventory_from_bravo() ngày
    20/07/2026 để dùng chung được cho cả (a) job đồng bộ định kỳ lên Supabase (không còn gọi, xem
    ghi chú ở sync_inventory_from_bravo) và (b) src/alerts.py::get_bravo_inventory_snapshot() —
    đọc TRỰC TIẾP Bravo cho digest/alert, không qua Supabase nữa (cùng lý do/kiểu với
    _period_revenue, get_bravo_receivables_snapshot: tránh lệch dữ liệu do bảng trung gian không
    được ghi/ghi lỗi — đúng là nguyên nhân bug "column channel does not exist" phát hiện 20/07/2026,
    bảng Supabase inventory chưa từng nhận được dữ liệu đúng schema mới này).

    sql_conn: connection Bravo (pyodbc raw connection, dùng được với pandas.read_sql).
    Trả về DataFrame với các cột đúng schema inventory (item_code, item_name, unit, opening_qty,
    inward_qty, outward_qty, closing_qty, closing_value, months_to_sell, warehouse, channel).

    Công thức — xem chi tiết lịch sử/lý do trong sync_inventory_from_bravo().
    """
    now = datetime.now()
    fiscal_year = str(now.year)

    # Cửa sổ 6 tháng ĐÃ HOÀN TẤT gần nhất (loại tháng hiện tại đang chạy dở).
    window_end = datetime(now.year, now.month, 1)
    wy, wm = now.year, now.month - 6
    while wm <= 0:
        wm += 12
        wy -= 1
    window_start = datetime(wy, wm, 1)

    # ---- 1a. OTC — bảng thô (không có lỗi quy đổi đơn vị) ----
    df_otc = pd.read_sql(
        """
        SELECT s.Code AS ItemCode, s.Name AS item_name, s.Unit AS unit,
            ISNULL(dk.open_qty, 0) AS opening_qty,
            ISNULL(tk.total_receipt, 0) AS inward_qty,
            ISNULL(tk.total_issue, 0) AS outward_qty
        FROM BRV_SanPham s
        LEFT JOIN (
            SELECT ItemId, SUM(Quantity) AS open_qty FROM BRV_TonKhoDK WHERE FiscalYear = ? GROUP BY ItemId
        ) dk ON dk.ItemId = s.Id
        LEFT JOIN (
            SELECT ItemId, SUM(ReceiptQuantity) AS total_receipt, SUM(IssueQuantity) AS total_issue
            FROM BRV_TheKhoLot WHERE FiscalYear = ? GROUP BY ItemId
        ) tk ON tk.ItemId = s.Id
        WHERE ISNULL(dk.open_qty, 0) + ISNULL(tk.total_receipt, 0) + ISNULL(tk.total_issue, 0) <> 0
        """, sql_conn, params=[fiscal_year, fiscal_year])
    df_otc["closing_qty"] = df_otc["opening_qty"] + df_otc["inward_qty"] - df_otc["outward_qty"]
    df_otc = df_otc[df_otc["closing_qty"] != 0].copy()
    df_otc["channel"] = "OTC"
    df_otc = df_otc.rename(columns={"ItemCode": "item_code"})
    print(f"  [OTC] {len(df_otc):,} mặt hàng có tồn kho ròng khác 0 (bảng thô, không cần quy đổi đơn vị).")

    # ---- 1b. ETC — hybrid: hàng có lô dùng view đã quy đổi DMS sẵn; hàng không lô dùng bảng thô
    # + tự chia ConvertRateDMS ----
    df_etc_lot_open = pd.read_sql(
        "SELECT ItemCode, UnitDMS, SUM(QuantityDMS) AS opening_qty FROM vTonKhoDKLot "
        "WHERE Year = ? AND ClassCode = 'SX' GROUP BY ItemCode, UnitDMS", sql_conn, params=[fiscal_year])
    df_etc_lot_flow = pd.read_sql(
        "SELECT ItemCode, UnitDMS, SUM(ReceiptQuantityDMS) AS inward_qty, SUM(IssueQuantityDMS) AS outward_qty "
        "FROM vTheKhoLot WHERE FiscalYear = ? AND ClassCode = 'SX' GROUP BY ItemCode, UnitDMS", sql_conn, params=[fiscal_year])
    df_etc_lot = pd.merge(df_etc_lot_open, df_etc_lot_flow, on=["ItemCode", "UnitDMS"], how="outer")
    for c in ("opening_qty", "inward_qty", "outward_qty"):
        df_etc_lot[c] = df_etc_lot[c].fillna(0.0)
    df_etc_lot["closing_qty"] = df_etc_lot["opening_qty"] + df_etc_lot["inward_qty"] - df_etc_lot["outward_qty"]
    df_etc_lot = df_etc_lot[df_etc_lot["closing_qty"] != 0].copy()
    df_etc_lot = df_etc_lot.rename(columns={"UnitDMS": "unit"})
    lot_item_codes = set(df_etc_lot["ItemCode"])
    print(f"  [ETC-lô] {len(df_etc_lot):,} mặt hàng có tồn kho ròng khác 0 (view đã quy đổi DMS).")

    df_etc_raw = pd.read_sql(
        """
        SELECT s.Code AS ItemCode, s.Name AS item_name, s.Unit AS unit,
            ISNULL(s.ConvertRateDMS, 1.0) AS convert_rate,
            ISNULL(dk.open_qty, 0) AS opening_qty_raw,
            ISNULL(tk.total_receipt, 0) AS inward_qty_raw,
            ISNULL(tk.total_issue, 0) AS outward_qty_raw
        FROM BRVSX_SanPham s
        LEFT JOIN (
            SELECT ItemId, SUM(Quantity) AS open_qty FROM BRVSX_TonKhoDK WHERE Year = ? GROUP BY ItemId
        ) dk ON dk.ItemId = s.Id
        LEFT JOIN (
            SELECT ItemId, SUM(ReceiptQuantity) AS total_receipt, SUM(IssueQuantity) AS total_issue
            FROM BRVSX_TheKhoLot WHERE FiscalYear = ? GROUP BY ItemId
        ) tk ON tk.ItemId = s.Id
        WHERE ISNULL(s.IsItemWithLot, 0) = 0
          AND ISNULL(dk.open_qty, 0) + ISNULL(tk.total_receipt, 0) + ISNULL(tk.total_issue, 0) <> 0
        """, sql_conn, params=[fiscal_year, fiscal_year])
    df_etc_raw = df_etc_raw[~df_etc_raw["ItemCode"].isin(lot_item_codes)].copy()
    for c in ("opening_qty_raw", "inward_qty_raw", "outward_qty_raw"):
        df_etc_raw[c] = df_etc_raw[c] / df_etc_raw["convert_rate"].replace(0, 1.0)
    df_etc_raw = df_etc_raw.rename(columns={
        "opening_qty_raw": "opening_qty", "inward_qty_raw": "inward_qty", "outward_qty_raw": "outward_qty"})
    df_etc_raw["closing_qty"] = df_etc_raw["opening_qty"] + df_etc_raw["inward_qty"] - df_etc_raw["outward_qty"]
    df_etc_raw = df_etc_raw[df_etc_raw["closing_qty"] != 0].copy()
    df_etc_raw = df_etc_raw.drop(columns=["convert_rate"])
    print(f"  [ETC-không lô] {len(df_etc_raw):,} mặt hàng có tồn kho ròng khác 0 (bảng thô, đã tự quy đổi ConvertRateDMS).")

    df_etc_names = pd.read_sql("SELECT Code AS ItemCode, Name AS item_name FROM BRVSX_SanPham", sql_conn)
    df_etc_lot = df_etc_lot.merge(df_etc_names, on="ItemCode", how="left")

    df_etc = pd.concat([df_etc_lot, df_etc_raw], ignore_index=True)
    df_etc["channel"] = "ETC"
    df_etc = df_etc.rename(columns={"ItemCode": "item_code"})

    df_all = pd.concat([df_otc, df_etc], ignore_index=True)

    # ---- 2. Vận tốc bán THẬT theo ĐÚNG kênh của từng dòng — doanh số 6 tháng hoàn tất gần nhất,
    # loại hàng khuyến mãi ----
    velocity_sql = """
        SELECT ItemCode AS item_code, DATEFROMPARTS(YEAR(DocDate), MONTH(DocDate), 1) AS month_key, SUM(Quantity) AS qty
        FROM {view}
        WHERE DocDate >= ? AND DocDate < ? AND UnitPrice > 0
        GROUP BY ItemCode, DATEFROMPARTS(YEAR(DocDate), MONTH(DocDate), 1)
    """
    df_vel_otc = pd.read_sql(velocity_sql.format(view="vHoaDonTotal"), sql_conn, params=[window_start, window_end])
    df_vel_etc = pd.read_sql(velocity_sql.format(view="vHoaDonETCTotal"), sql_conn, params=[window_start, window_end])
    df_vel_otc["channel"] = "OTC"
    df_vel_etc["channel"] = "ETC"
    df_vel = pd.concat([df_vel_otc, df_vel_etc], ignore_index=True)

    velocity = df_vel.groupby(["item_code", "channel"]).agg(
        total_qty=("qty", "sum"), months_with_sale=("month_key", "nunique")
    ).reset_index()
    velocity["avg_monthly_sales"] = velocity["total_qty"] / velocity["months_with_sale"]

    df_all = df_all.merge(velocity[["item_code", "channel", "avg_monthly_sales"]],
                           on=["item_code", "channel"], how="left")

    def calc_months_to_sell(row):
        if row["closing_qty"] <= 0:
            return 0.0
        avg = row["avg_monthly_sales"]
        if pd.isna(avg) or avg <= 0:
            return 9999.0  # không có doanh số bán thật trong 6 tháng gần nhất -> tồn vĩnh viễn
        return round(row["closing_qty"] / avg, 2)

    df_all["months_to_sell"] = df_all.apply(calc_months_to_sell, axis=1)
    df_all["closing_value"] = 0.0  # tạm — chờ DNH xác nhận nguồn giá trị tồn kho, không đổi so với trước
    df_all["warehouse"] = None  # gộp tất cả kho, không phân biệt

    # Chỉ giữ các cột đúng schema inventory
    inventory_cols = ["item_code", "item_name", "unit", "opening_qty", "inward_qty",
                      "outward_qty", "closing_qty", "closing_value", "months_to_sell",
                      "warehouse", "channel"]
    df_final = df_all[inventory_cols].copy()

    # Làm sạch
    df_final = clean_dataframe(df_final)

    print(f"  -> Tổng cộng {len(df_final):,} dòng inventory (OTC + ETC tách riêng).")
    stats = df_final.groupby("channel").agg(
        count=("item_code", "count"),
        has_stock=("closing_qty", lambda x: (x > 0).sum()),
        near_stockout=("months_to_sell", lambda x: ((x > 0) & (x <= 1.0)).sum()),
    )
    for ch, row in stats.iterrows():
        print(f"     {ch}: {row['count']} mặt hàng, {row['has_stock']} còn tồn, {row['near_stockout']} sắp hết")

    return df_final
