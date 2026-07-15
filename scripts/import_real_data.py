"""
import_real_data.py - ETL Script nap du lieu thuc te tu cac file Excel DNH
vao CSDL trung gian dnh_intermediate.db.

Xu ly:
  - Monkeypatch openpyxl de doc file 1 (ton kho) bi loi PrintTitles #N/A
  - Dung dung ten sheet va ten cot thuc te tu cac file Excel goc cua DNH
"""
import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# Monkeypatch openpyxl de xu ly file Excel bi loi #N/A print titles
# ============================================================
import openpyxl.worksheet.print_settings
from openpyxl.worksheet.print_settings import PrintTitles
_orig_from_string = PrintTitles.from_string
@classmethod
def _safe_from_string(cls, val):
    if '#N/A' in str(val):
        return PrintTitles()
    return _orig_from_string.__func__(cls, val)
PrintTitles.from_string = _safe_from_string

# ============================================================
# Helpers
# ============================================================
def strip_accents(s):
    m = {
        'a': 'áàảãạăắằẳẵặâấầẩẫậ', 'A': 'ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬ',
        'd': 'đ', 'D': 'Đ',
        'e': 'éèẻẽẹêếềểễệ', 'E': 'ÉÈẺẼẸÊẾỀỂỄỆ',
        'i': 'íìỉĩị', 'I': 'ÍÌỈĨỊ',
        'o': 'óòỏõọôốồổỗộơớờởỡợ', 'O': 'ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ',
        'u': 'úùủũụưứừửữự', 'U': 'ÚÙỦŨỤƯỨỪỬỮỰ',
        'y': 'ýỳỷỹỵ', 'Y': 'ÝỲỶỸỴ'
    }
    res = str(s)
    for r, chars in m.items():
        for c in chars:
            res = res.replace(c, r)
    return res

def sp(msg):
    """Safe print - strip accents truoc khi in ra console Windows."""
    print(strip_accents(msg))

DB_PATH = os.path.join(os.path.dirname(__file__), "dnh_intermediate.db")
BASE_DIR = r"D:\DNH"

def safe_float(val, default=0.0):
    try:
        if pd.isna(val):
            return default
        return float(val)
    except:
        return default

def safe_int(val, default=0):
    try:
        if pd.isna(val):
            return default
        return int(float(val))
    except:
        return default

def safe_str(val, default=""):
    if pd.isna(val):
        return default
    return str(val).strip()

# ============================================================
# Main Import
# ============================================================
def run_import():
    sp("=" * 60)
    sp("BAT DAU IMPORT DU LIEU THUC TE TU CAC FILE EXCEL DNH")
    sp("=" * 60)

    if not os.path.exists(DB_PATH):
        sp(f"Loi: Database trung gian {DB_PATH} khong ton tai.")
        sp("Vui long chay init_db.py truoc!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # --- Drop va tao lai cac bang phu cho kho, KPI, cong no chi tiet ---
    cursor.executescript("""
    DROP TABLE IF EXISTS inventory;
    DROP TABLE IF EXISTS kpi_sales_product;
    DROP TABLE IF EXISTS kpi_sales_customer;
    DROP TABLE IF EXISTS kpi_summary;
    DROP TABLE IF EXISTS receivable_detail;
    DROP TABLE IF EXISTS receivable_etc;

    CREATE TABLE IF NOT EXISTS inventory (
        item_code TEXT PRIMARY KEY,
        item_name TEXT NOT NULL,
        unit TEXT,
        opening_qty REAL DEFAULT 0,
        inward_qty REAL DEFAULT 0,
        outward_qty REAL DEFAULT 0,
        closing_qty REAL DEFAULT 0,
        closing_value REAL DEFAULT 0,
        months_to_sell REAL DEFAULT 0,
        warehouse TEXT
    );

    CREATE TABLE IF NOT EXISTS kpi_sales_product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area_code TEXT,
        employee_code TEXT,
        employee_name TEXT,
        position_name TEXT,
        manager_code TEXT,
        item_code TEXT,
        item_name TEXT,
        group_code TEXT,
        amount_item REAL DEFAULT 0,
        is_sku INTEGER DEFAULT 0,
        save_date DATE
    );

    CREATE TABLE IF NOT EXISTS kpi_sales_customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area_code TEXT,
        employee_code TEXT,
        employee_name TEXT,
        position_name TEXT,
        manager_code TEXT,
        customer_code TEXT,
        customer_name TEXT,
        amount_cus REAL DEFAULT 0,
        reorder_start_date DATE,
        ro_last_date DATE,
        is_ro INTEGER DEFAULT 0,
        new_cus_start_date DATE,
        is_nc INTEGER DEFAULT 0,
        is_aso INTEGER DEFAULT 0,
        is_ac INTEGER DEFAULT 0,
        save_date DATE
    );

    CREATE TABLE IF NOT EXISTS kpi_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        area_code TEXT,
        employee_code TEXT,
        employee_name TEXT,
        position_code TEXT,
        month_sale_target REAL DEFAULT 0,
        month_sale_amount REAL DEFAULT 0,
        month_sale_percent REAL DEFAULT 0,
        total_point REAL DEFAULT 0,
        quarter_sale_target REAL DEFAULT 0,
        quarter_sale_amount REAL DEFAULT 0,
        quarter_sale_percent REAL DEFAULT 0,
        year_sale_target REAL DEFAULT 0,
        year_sale_amount REAL DEFAULT 0,
        year_sale_percent REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS receivable_detail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT,
        customer_code TEXT,
        customer_name TEXT,
        balance_end REAL DEFAULT 0,
        in_term REAL DEFAULT 0,
        overdue_1_15 REAL DEFAULT 0,
        overdue_15_30 REAL DEFAULT 0,
        overdue_30_45 REAL DEFAULT 0,
        overdue_gt_45 REAL DEFAULT 0,
        total_overdue REAL DEFAULT 0,
        sales_channel TEXT
    );

    CREATE TABLE IF NOT EXISTS receivable_etc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_code TEXT,
        customer_name TEXT,
        contract_value REAL DEFAULT 0,
        total_paid REAL DEFAULT 0,
        in_term REAL DEFAULT 0,
        overdue_1_7 REAL DEFAULT 0,
        overdue_8_14 REAL DEFAULT 0,
        overdue_15_21 REAL DEFAULT 0,
        overdue_gt_21 REAL DEFAULT 0,
        total_overdue REAL DEFAULT 0,
        total_receivable REAL DEFAULT 0,
        province_code TEXT,
        sales_manager TEXT
    );
    """)
    conn.commit()

    # ============================================================
    # FILE 2: Data Phai thu tong hop SX&TM - sheet 'Data'
    # Cau truc: Ky bao cao | Ma | Ten khach hang | So du phai thu cuoi ky |
    #           Phai thu trong han | Phai thu qua han 1-15 | 15-30 | 30-45 | >45 |
    #           Phai thu qua han | Kenh ban hang
    # ============================================================
    file2 = os.path.join(BASE_DIR, "2. Data Phai thu tổng hợp SX&TM 16.01.26.xlsx")
    if os.path.exists(file2):
        sp("\n[1/4] Dang doc file: 2. Data Phai thu tong hop SX&TM...")

        # --- Sheet 'Data': Cong no phai thu tong hop (OTC + SX) ---
        df_data = pd.read_excel(file2, sheet_name='Data')
        df_data.columns = [strip_accents(str(c)) for c in df_data.columns]
        df_data = df_data.dropna(subset=["Ma"])

        cursor.execute("DELETE FROM receivable_detail")
        recv_count = 0
        region_set = set()
        cust_set = set()

        for _, row in df_data.iterrows():
            c_code = safe_str(row.get("Ma"))
            c_name = safe_str(row.get("Ten khach hang"))
            period = safe_str(row.get("Ky bao cao"))
            balance = safe_float(row.get("So du phai thu cuoi ky"))
            in_term = safe_float(row.get("Phai thu trong han"))
            od_1_15 = safe_float(row.get("Phai thu qua han 1 - 15 ngay"))
            od_15_30 = safe_float(row.get("Phai thu qua han 15 - 30ngay"))
            od_30_45 = safe_float(row.get("Phai thu qua han 30-45 ngay"))
            od_gt_45 = safe_float(row.get("Phai thu qua han > 45 ngay"))
            total_od = safe_float(row.get("Phai thu qua han"))
            channel = safe_str(row.get("Kenh ban hang"))

            cursor.execute("""
            INSERT INTO receivable_detail
            (period, customer_code, customer_name, balance_end, in_term,
             overdue_1_15, overdue_15_30, overdue_30_45, overdue_gt_45,
             total_overdue, sales_channel)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (period, c_code, c_name, balance, in_term,
                  od_1_15, od_15_30, od_30_45, od_gt_45, total_od, channel))
            recv_count += 1

            # Tao customer trong bang customers neu chua co
            if c_code not in cust_set:
                cust_set.add(c_code)
                seg = "OTC" if channel in ("0", "OTC", "") else str(channel).upper()
                cursor.execute("""
                INSERT OR IGNORE INTO customers
                (customer_id, customer_name, segment, region_id, daily_debt_limit, allowed_debt_days)
                VALUES (?, ?, ?, 'N/A', 0.0, 30)
                """, (c_code, c_name, seg))

        sp(f"   -> Da import {recv_count} dong cong no phai thu tong hop (OTC+SX).")

        # --- Sheet 'Data' cua File 3: Cong no phai thu Nam Ha TM (ETC) ---
        # (xu ly phia duoi)

    # ============================================================
    # FILE 3: Bao cao cong no phai thu Nam Ha TM - sheet 'Data'
    # Cau truc: Unnamed:0 (Ky) | Unnamed:1 (Ma) | Unnamed:2 (Ten KH) |
    #           Gia tri HD | Tong gia tri thanh toan | Phai thu Trong han |
    #           Phai thu qua han 1-7 | 8-14 | 15-21 | >21 | Qua han | Phai thu |
    #           Unnamed:12 (Ma tinh) | Unnamed:13 (GDKD)
    # ============================================================
    file3 = os.path.join(BASE_DIR, "3. Báo cáo công nợ phải thu Nam Hà TM_16.01.2026.xlsx")
    if os.path.exists(file3):
        sp("\n[2/4] Dang doc file: 3. Bao cao cong no phai thu Nam Ha TM (ETC)...")
        df_etc = pd.read_excel(file3, sheet_name='Data')
        # Cot Unnamed:0=Ky, Unnamed:1=Ma, Unnamed:2=Ten KH,
        # Unnamed:12=Ma tinh, Unnamed:13=GDKD
        cols = list(df_etc.columns)

        cursor.execute("DELETE FROM receivable_etc")
        etc_count = 0

        for _, row in df_etc.iterrows():
            # row 0 la tong -> bo qua nhung hang co cot Ma (Unnamed:1) la NaN
            c_code = safe_str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
            if not c_code or c_code == "nan":
                continue

            c_name = safe_str(row.iloc[2])
            contract_val = safe_float(row.get("Gia tri HD"))
            total_paid = safe_float(row.get("Tong gia tri thanh toan"))
            in_term = safe_float(row.get("Phai thu Trong han"))
            od_1_7 = safe_float(row.get("Phai thu qua han 1 - 7 ngay"))
            od_8_14 = safe_float(row.get("Phai thu qua han 8 - 14 ngay"))
            od_15_21 = safe_float(row.get("Phai thu qua han 15 - 21 ngay"))
            od_gt_21 = safe_float(row.get("Phai thu qua han > 21 ngay"))
            total_od = safe_float(row.get("Qua han"))
            total_recv = safe_float(row.get("Phai thu"))
            province = safe_str(row.iloc[12]) if len(row) > 12 else ""
            gdkd = safe_str(row.iloc[13]) if len(row) > 13 else ""

            cursor.execute("""
            INSERT INTO receivable_etc
            (customer_code, customer_name, contract_value, total_paid,
             in_term, overdue_1_7, overdue_8_14, overdue_15_21, overdue_gt_21,
             total_overdue, total_receivable, province_code, sales_manager)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (c_code, c_name, contract_val, total_paid,
                  in_term, od_1_7, od_8_14, od_15_21, od_gt_21,
                  total_od, total_recv, province, gdkd))
            etc_count += 1

            # Tao customer trong bang customers neu chua co
            if c_code not in cust_set:
                cust_set.add(c_code)
                cursor.execute("""
                INSERT OR IGNORE INTO customers
                (customer_id, customer_name, segment, region_id, daily_debt_limit, allowed_debt_days)
                VALUES (?, ?, 'ETC', 'N/A', 0.0, 30)
                """, (c_code, c_name))

        sp(f"   -> Da import {etc_count} dong cong no phai thu ETC (benh vien/thau).")

    # ============================================================
    # FILE 1: Bao cao ton kho thanh pham
    # Su dung sheet 'Du phong so thang ban' (du lieu tong hop sach)
    # Header tai row 4: Ma so | Mat hang | Ten SP | Dvt Goc | Dvt DMS |
    #   Sum of Ton cuoi | Sum of Ton cuoi DMS | Sum of Gia tri |
    #   Luong ban binh quan 1 thang (DMS) | Du phong so thang ban het
    # ============================================================
    file1 = os.path.join(BASE_DIR, "1. Báo cáo tồn kho thành phẩm 16.01.2026.xlsx")
    if os.path.exists(file1):
        sp("\n[3/4] Dang doc file: 1. Bao cao ton kho thanh pham...")
        try:
            df_tk = pd.read_excel(file1, sheet_name='Dự phòng số tháng bán', header=None)
            
            # Tim dong header: chua 'Mã số' hoac 'Ma so'
            header_row = None
            for i in range(min(10, len(df_tk))):
                row_vals = [strip_accents(safe_str(v)).lower() for v in df_tk.iloc[i]]
                if any('ma so' in v for v in row_vals):
                    header_row = i
                    break

            if header_row is not None:
                df_tk.columns = [strip_accents(safe_str(c)) for c in df_tk.iloc[header_row]]
                df_tk = df_tk.iloc[header_row + 1:]
                df_tk = df_tk.reset_index(drop=True)

                sp(f"   Tim thay header tai dong {header_row}. Columns: {[strip_accents(c) for c in df_tk.columns[:6]]}...")

                # Tim cac cot quan trong (da strip_accents)
                col_map = {}
                for c in df_tk.columns:
                    cl = c.lower().strip()
                    if 'ma so' in cl or cl == 'ma':
                        col_map['code'] = c
                    elif 'mat hang' in cl and 'code' not in col_map:
                        col_map['name'] = c
                    elif 'ten sp' in cl:
                        col_map['name'] = c  # uu tien Ten SP
                    elif 'dvt' in cl and 'goc' in cl:
                        col_map['unit'] = c
                    elif 'ton cuoi' in cl and 'dms' not in cl:
                        col_map['closing_qty'] = c
                    elif 'gia tri' in cl:
                        col_map['closing_value'] = c
                    elif 'so thang' in cl or 'du phong' in cl:
                        col_map['months'] = c
                    elif 'binh quan' in cl:
                        col_map['avg_monthly'] = c

                cursor.execute("DELETE FROM inventory")
                tk_count = 0

                if 'code' in col_map:
                    for _, row in df_tk.iterrows():
                        code = safe_str(row.get(col_map['code']))
                        if not code or code == 'nan' or code.lower() in ('total', 'tong', 'tong cong'):
                            continue
                        
                        name = safe_str(row.get(col_map.get('name', ''), ''))
                        if not name or name == 'nan':
                            continue
                        
                        unit = safe_str(row.get(col_map.get('unit', ''), ''))
                        closing_qty = safe_float(row.get(col_map.get('closing_qty', ''), 0))
                        closing_val = safe_float(row.get(col_map.get('closing_value', ''), 0))
                        months = safe_float(row.get(col_map.get('months', ''), 0))

                        cursor.execute("""
                        INSERT OR REPLACE INTO inventory
                        (item_code, item_name, unit, closing_qty, closing_value, months_to_sell)
                        VALUES (?,?,?,?,?,?)
                        """, (code, name, unit, closing_qty, closing_val, months))
                        tk_count += 1

                sp(f"   -> Da import {tk_count} mat hang ton kho (du phong so thang ban).")
            else:
                sp("   -> Khong tim thay header trong sheet 'Du phong so thang ban'.")

        except Exception as e:
            sp(f"   -> Loi doc file ton kho: {e}")

    # ============================================================
    # FILE 4: Bao cao KPI luong kinh doanh_MN
    # Sheet 'Chi tiet san pham': AreaCode2 | EmployeeCode | EmployeeName |
    #     PositionName | ManagerCode | ItemCode | ItemName | GroupCode |
    #     Amount_Item | IsSKU | SaveDate
    # Sheet 'Chi tiet khach hang': ... (16 cot)
    # Sheet 'Tong hop KPI': ... (60 cot)
    # ============================================================
    file4 = os.path.join(BASE_DIR, "Báo cáo KPI lương kinh doanh_MN.xlsx")
    if os.path.exists(file4):
        sp("\n[4/4] Dang doc file: Bao cao KPI luong kinh doanh_MN...")

        # --- Sheet 'Chi tiet san pham' ---
        df_sp = pd.read_excel(file4, sheet_name='Chi tiết sản phẩm')
        df_sp = df_sp.dropna(subset=['EmployeeCode', 'ItemCode'])

        cursor.execute("DELETE FROM kpi_sales_product")
        sp_count = 0
        for _, row in df_sp.iterrows():
            save_date = str(row['SaveDate'])[:10] if pd.notna(row['SaveDate']) else '2025-10-31'
            cursor.execute("""
            INSERT INTO kpi_sales_product
            (area_code, employee_code, employee_name, position_name, manager_code,
             item_code, item_name, group_code, amount_item, is_sku, save_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                safe_str(row.get('AreaCode2')),
                safe_str(row['EmployeeCode']),
                safe_str(row['EmployeeName']),
                safe_str(row.get('PositionName')),
                safe_str(row.get('ManagerCode')),
                safe_str(row['ItemCode']),
                safe_str(row['ItemName']),
                safe_str(row.get('GroupCode')),
                safe_float(row['Amount_Item']),
                safe_int(row.get('IsSKU')),
                save_date
            ))
            sp_count += 1
        sp(f"   -> Da import {sp_count} dong chi tiet san pham KPI.")

        # --- Sheet 'Chi tiet khach hang' ---
        df_ch = pd.read_excel(file4, sheet_name='Chi tiết khách hàng')
        df_ch = df_ch.dropna(subset=['EmployeeCode', 'CustomerCode'])

        cursor.execute("SELECT DISTINCT customer_code FROM receivable_etc")
        etc_cust_codes = {r[0] for r in cursor.fetchall() if r[0]}

        cursor.execute("DELETE FROM kpi_sales_customer")
        ch_count = 0
        for _, row in df_ch.iterrows():
            save_date = str(row['SaveDate'])[:10] if pd.notna(row['SaveDate']) else '2025-10-31'
            c_code = safe_str(row['CustomerCode'])
            c_name = safe_str(row['CustomerName'])
            
            # Tao customer trong bang customers neu chua co
            if c_code not in cust_set:
                cust_set.add(c_code)
                seg = 'ETC' if c_code in etc_cust_codes else 'OTC'
                cursor.execute("""
                INSERT OR IGNORE INTO customers
                (customer_id, customer_name, segment, region_id, daily_debt_limit, allowed_debt_days)
                VALUES (?, ?, ?, 'MN', 0.0, 30)
                """, (c_code, c_name, seg))

            cursor.execute("""
            INSERT INTO kpi_sales_customer
            (area_code, employee_code, employee_name, position_name, manager_code,
             customer_code, customer_name, amount_cus,
             reorder_start_date, ro_last_date, is_ro,
             new_cus_start_date, is_nc, is_aso, is_ac, save_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                safe_str(row.get('AreaCode2')),
                safe_str(row['EmployeeCode']),
                safe_str(row['EmployeeName']),
                safe_str(row.get('PositionName')),
                safe_str(row.get('ManagerCode')),
                c_code,
                c_name,
                safe_float(row['Amount_Cus']),
                str(row.get('ReOrderStartDate', ''))[:10] if pd.notna(row.get('ReOrderStartDate')) else None,
                str(row.get('ROLastDate', ''))[:10] if pd.notna(row.get('ROLastDate')) else None,
                safe_int(row.get('IsRO')),
                str(row.get('NewCusStartDate', ''))[:10] if pd.notna(row.get('NewCusStartDate')) else None,
                safe_int(row.get('IsNC')),
                safe_int(row.get('IsASO')),
                safe_int(row.get('IsAC')),
                save_date
            ))
            ch_count += 1
        sp(f"   -> Da import {ch_count} dong chi tiet khach hang KPI.")

        # --- Sheet 'Tong hop KPI' ---
        df_kpi = pd.read_excel(file4, sheet_name='Tổng hợp KPI')
        df_kpi = df_kpi.dropna(subset=['EmployeeCode'])

        cursor.execute("DELETE FROM kpi_summary")
        kpi_count = 0
        for _, row in df_kpi.iterrows():
            cursor.execute("""
            INSERT INTO kpi_summary
            (area_code, employee_code, employee_name, position_code,
             month_sale_target, month_sale_amount, month_sale_percent, total_point,
             quarter_sale_target, quarter_sale_amount, quarter_sale_percent,
             year_sale_target, year_sale_amount, year_sale_percent)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                safe_str(row.get('AreaCode2')),
                safe_str(row['EmployeeCode']),
                safe_str(row['EmployeeName']),
                safe_str(row.get('PositionCode')),
                safe_float(row.get('MonthSaleTarget')),
                safe_float(row.get('MonthSaleAmount')),
                safe_float(row.get('MonthSalePercent_R')),
                safe_float(row.get('TotalPoint')),
                safe_float(row.get('QuaterSaleTarget')),
                safe_float(row.get('QuaterSaleAmount')),
                safe_float(row.get('QuaterSalePercent')),
                safe_float(row.get('YearSaleTarget')),
                safe_float(row.get('YearSaleAmount')),
                safe_float(row.get('YearSalePercent'))
            ))
            kpi_count += 1
        sp(f"   -> Da import {kpi_count} dong tong hop KPI.")

    # --- Regions/Employees tu KPI data ---
    sp("\n[+] Tao bang Regions va Employees tu du lieu KPI...")
    cursor.execute("""
    INSERT OR IGNORE INTO regions (region_id, region_name)
    SELECT DISTINCT area_code, 
        CASE area_code
            WHEN 'MN' THEN 'Mien Nam'
            WHEN 'MB' THEN 'Mien Bac'
            WHEN 'MB2' THEN 'Mien Bac 2'
            WHEN 'MT' THEN 'Mien Trung'
            ELSE 'Mien ' || area_code
        END
    FROM kpi_sales_product
    WHERE area_code IS NOT NULL AND area_code != ''
    """)

    cursor.execute("""
    INSERT OR IGNORE INTO employees (employee_id, full_name, region_id)
    SELECT DISTINCT employee_code, employee_name, area_code
    FROM kpi_sales_product
    WHERE employee_code IS NOT NULL AND employee_code != ''
    """)

    conn.commit()

    # ============================================================
    # Thong ke tong hop
    # ============================================================
    sp("\n" + "=" * 60)
    sp("THONG KE SAU KHI IMPORT:")
    sp("=" * 60)

    tables = [
        "regions", "employees", "customers",
        "receivable_detail", "receivable_etc",
        "inventory",
        "kpi_sales_product", "kpi_sales_customer", "kpi_summary",
        "orders", "invoices", "contracts", "appendices"
    ]
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            count = cursor.fetchone()[0]
            sp(f"  {t:30s} -> {count:>8,} dong")
        except:
            sp(f"  {t:30s} -> (bang chua ton tai)")

    conn.close()
    sp("\nDONG BO DU LIEU THUC TE HOAN TAT!")

if __name__ == "__main__":
    run_import()
