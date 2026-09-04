# -*- coding: utf-8 -*-
"""
Dong bo du lieu tu Bravo (chi SELECT, khong bao gio ghi/sua gi tren Bravo) vao kho local SQLite
(warehouse.db) de chatbot query nhanh <=10s.

Che do:
  --full          Dong bo toan bo lich su (chia theo thang de tranh timeout/mat ket noi qua VPN).
                   Chay 1 lan dau tien, hoac khi muon dong bo lai tu dau.
  (mac dinh)      Dong bo GIA TANG: cac bang nho (dim/fact nho) reload toan bo (nhanh); rieng
                   vhoadon_otc/vhoadon_etc chi refresh N_RECENT_DAYS ngay gan nhat (du lieu Bravo
                   con "sơ bo"/tiep tuc cap nhat trong vai ngay dau).

Chay: py sync_warehouse.py [--full]
"""
import sys, os, argparse, datetime as dt, time, sqlite3
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def load_env():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    for env_path in (os.path.join(backend_dir, ".env"), os.path.join(os.path.dirname(backend_dir), ".env")):
        if not os.path.exists(env_path):
            continue
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
load_env()

import decimal
from sqlalchemy import text
from query_engine import _get_engine
from local_warehouse import get_conn, init_schema, set_sync_meta

N_RECENT_DAYS = 45  # so ngay gan nhat can refresh moi lan chay incremental (du lieu Bravo con "sơ bo")


def _sqlite_val(v):
    """SQLite khong ho tro Decimal/date/datetime truc tiep - chuyen ve float/str.
    LUU Y: phai kiem tra datetime TRUOC date (datetime la subclass cua date) - datetime GIU NGUYEN
    ca gio:phut:giay (CreatedAt la thoi diem TAO DON; khong phai thoi diem xac nhan va khong dung de
    suy dien KPI/bat thuong), chi date thuan moi cat con YYYY-MM-DD."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return str(v)
    if isinstance(v, dt.date):
        return str(v)[:10]
    return v


def bravo_query(sql, **params):
    eng = _get_engine("bravo")
    with eng.connect() as c:
        r = c.execute(text(sql), params)
        cols = list(r.keys())
        rows = [tuple(_sqlite_val(v) for v in row) for row in r.fetchall()]
        return cols, rows


def month_ranges(start: dt.date, end: dt.date):
    cur = start.replace(day=1)
    while cur <= end:
        nxt = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield cur, min(nxt - dt.timedelta(days=1), end)
        cur = nxt


DETAIL_WINDOW_MONTHS = 12  # so thang gan nhat giu CHI TIET tung dong hoa don - xa hon bi NEN


def _detail_cutoff_date(today: dt.date = None) -> dt.date:
    """Ngay dau tien cua thang batdau cua-so 12 thang gan nhat - hoa don TRUOC ngay nay bi nen,
    TU ngay nay tro di van giu chi tiet nhu cu."""
    today = today or dt.date.today()
    y, m = today.year, today.month - DETAIL_WINDOW_MONTHS
    while m <= 0:
        m += 12
        y -= 1
    return dt.date(y, m, 1)


# ==================== BANG HOA DON (lon, co lich su) ====================
def sync_hoadon_full(table_bravo, table_local, has_city, has_channel=False, channel_label=""):
    print(f"[{table_local}] Dong bo FULL lich su...")
    cols_sql, rows = bravo_query(f"SELECT MIN(DocDate) mn, MAX(DocDate) mx FROM dbo.{table_bravo}")
    mn, mx = rows[0]
    mn = dt.datetime.strptime(mn, "%Y-%m-%d").date() if isinstance(mn, str) else mn
    mx = dt.datetime.strptime(mx, "%Y-%m-%d").date() if isinstance(mx, str) else mx
    cutoff = _detail_cutoff_date()
    conn = get_conn()
    conn.execute(f"DELETE FROM {table_local}")
    conn.execute("DELETE FROM monthly_customer_summary WHERE channel=?", (channel_label,))
    conn.commit()
    total = 0
    total_compressed = 0
    t0 = time.time()
    for a, b in month_ranges(mn, mx):
        # EmpDMSCode (KHONG PHAI EmpDMSCode2) - da xac minh 17/07/2026: EmpDMSCode2 tren hoa don la
        # ma QLV/khu vuc phu trach (vd 'ASM12'), KHONG PHAI ma nguoi ban hang (TDV) thuc su. EmpDMSCode
        # moi khop voi DIM_NhanVien.DMSId cua chinh TDV do (kiem chung: doi chieu ~150 TDV, khop 100%
        # doanh thu hoa don vs KPI khi join qua EmpDMSCode<->DMSId, sai lech 0 dong cho tat ca).
        # EmpDMSCode2 (has_channel, CHI OTC) duoc luu rieng vao channel_code - dung de nhan dien cac
        # "kenh ao" nhu Modern Trade (xem local_warehouse.py va report_templates.py revenue_by_region()).
        cols = ("DocDate, CustomerCode, ItemCode, Amount9, Quantity, UnitPrice, Stt, EmpDMSCode"
                + (", CityId" if has_city else "") + ", CreatedAt"
                + (", EmpDMSCode2" if has_channel else ""))
        _, rows = bravo_query(
            f"SELECT {cols} FROM dbo.{table_bravo} WHERE DocDate BETWEEN :a AND :b",
            a=str(a), b=str(b),
        )
        if not rows:
            print(f"  {a} -> {b}: 0 dong (tong {total}, {time.time()-t0:.0f}s)")
            continue
        if a < cutoff:
            # Thang cu hon cua so chi tiet (12 thang gan nhat) - NEN thang KH x thang, KHONG insert
            # tung dong vao vhoadon_otc/etc (item_code/quantity/unit_price/created_at/stt bi bo qua).
            n_compressed = _compress_rows_to_summary(conn, rows, channel_label, a.strftime("%Y-%m"))
            total_compressed += n_compressed
            print(f"  {a} -> {b}: {len(rows)} dong -> NEN thanh {n_compressed} dong KH x thang "
                  f"(tong nen {total_compressed}, {time.time()-t0:.0f}s)")
            continue
        n_cols = 9 + (1 if has_city else 0) + (1 if has_channel else 0)
        placeholders = ",".join(["?"] * n_cols)
        cols_local = ("doc_date,customer_code,item_code,amount9,quantity,unit_price,stt,employee_code"
                      + (",city_id" if has_city else "") + ",created_at"
                      + (",channel_code" if has_channel else ""))
        conn.executemany(
            f"INSERT INTO {table_local} ({cols_local}) VALUES ({placeholders})", rows,
        )
        conn.commit()
        total += len(rows)
        print(f"  {a} -> {b}: {len(rows)} dong (tong {total}, {time.time()-t0:.0f}s)")
    conn.close()
    set_sync_meta(table_local, str(mn), str(mx))
    print(f"[{table_local}] Xong FULL: {total} dong chi tiet (>={cutoff}) + {total_compressed} dong "
          f"nen KHxthang (<{cutoff}), {time.time()-t0:.0f}s")


def _compress_rows_to_summary(conn, rows, channel_label: str, year_month: str) -> int:
    """Gop danh sach dong hoa don THO (tuple tu bravo_query, cung thu tu cot nhu sync_hoadon_full/
    sync_hoadon_recent) thanh {(customer_code, employee_code): (revenue, so_hoa_don_distinct)} roi
    INSERT vao monthly_customer_summary. Vi tri cot: 0=DocDate,1=CustomerCode,2=ItemCode,3=Amount9,
    4=Quantity,5=UnitPrice,6=Stt,7=EmpDMSCode (cac cot sau la CityId/CreatedAt/EmpDMSCode2 tuy bang,
    KHONG can cho buoc nen nay)."""
    agg = {}
    for r in rows:
        customer_code, amount9, stt, employee_code = r[1], r[3], r[6], r[7]
        key = (customer_code, employee_code)
        rev, stts = agg.get(key, (0.0, set()))
        agg[key] = (rev + (float(amount9) if amount9 is not None else 0.0), stts | {stt})
    if not agg:
        return 0
    conn.executemany(
        "INSERT INTO monthly_customer_summary (year_month, channel, customer_code, employee_code, "
        "revenue, invoice_count) VALUES (?,?,?,?,?,?)",
        [(year_month, channel_label, cc, ec, rev, len(stts)) for (cc, ec), (rev, stts) in agg.items()],
    )
    conn.commit()
    return len(agg)


def sync_hoadon_recent(table_bravo, table_local, has_city, days=N_RECENT_DAYS, has_channel=False):
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    print(f"[{table_local}] Refresh gia tang {start} -> {today}...")
    cols = ("DocDate, CustomerCode, ItemCode, Amount9, Quantity, UnitPrice, Stt, EmpDMSCode"
            + (", CityId" if has_city else "") + ", CreatedAt"
            + (", EmpDMSCode2" if has_channel else ""))
    _, rows = bravo_query(
        f"SELECT {cols} FROM dbo.{table_bravo} WHERE DocDate >= :a", a=str(start),
    )
    conn = get_conn()
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"DELETE FROM {table_local} WHERE doc_date >= ?", (str(start),))
        if rows:
            n_cols = 9 + (1 if has_city else 0) + (1 if has_channel else 0)
            placeholders = ",".join(["?"] * n_cols)
            cols_local = ("doc_date,customer_code,item_code,amount9,quantity,unit_price,stt,employee_code"
                          + (",city_id" if has_city else "") + ",created_at"
                          + (",channel_code" if has_channel else ""))
            conn.executemany(
                f"INSERT INTO {table_local} ({cols_local}) VALUES ({placeholders})", rows,
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    set_sync_meta(table_local, str(start), str(today))
    print(f"[{table_local}] Xong: {len(rows)} dong refresh")


# ==================== BANG NHO (dim/fact) - RELOAD TOAN BO MOI LAN ====================
SMALL_TABLES = [
    # (bang Bravo, bang local, cot Bravo, cot local)
    ("DIM_TinhThanhPho", "dim_tinhthanhpho", "CityId, CityName, AreaCode", "city_id,city_name,area_code"),
    ("DIM_TargetVungMien", "dim_targetvungmien", "AreaCode, ChannelCode, Amount, DocDate", "area_code,channel_code,amount,doc_date"),
    ("FACT_KeHoachTongETC", "fact_kehoachtongetc", "DocDate, Amount, ItemGroup", "doc_date,amount,item_group"),
    ("DMSSX_KhachHang", "dmssx_khachhang", "Code, Name, CityId, Id, KenhBH", "code,name,city_id,id_code,kenh_bh"),
    # Nhan vien rieng phia SX/ETC, KHONG co trong DIM_NhanVien - xac nhan 20/07/2026 (vd ma DNH00087,
    # DNH00268, Sale01-Sale15...). Xem local_warehouse.py va report_templates.py _resolve_employee_identity().
    ("DMSSX_NhanVien", "dmssx_nhanvien", "Id, Name, DMSCode, Code, IsActive", "id_code,name,dmscode,code,is_active"),
    ("DMS_KhachHang", "dms_khachhang", "Code, Name, CityId, Id, EmpDMSCode1, KenhBH", "code,name,city_id,id_code,emp_code,kenh_bh"),
    # StartDate/EndDate/IsResigned: lich su dam nhiem (Bravo giu lai ban ghi cu, KHONG xoa khi doi
    # nguoi) - dung de dung lai timeline "ai phu trach luc nao". ManagerAreaCode: ma khu vuc nho
    # (V01-V22) - TDV mang ma nay de biet thuoc "to" nao, ban ghi "bong" cua QLV (ten co hau to
    # "(QLV)") cung mang dung ma nay de biet QLV nao phu trach to do (xem org_hierarchy.py).
    ("DIM_NhanVien", "dim_nhanvien",
     "EmployeeCode, Name, IsDuplicate, PositionCode, AreaCode, DMSId, StartDate, EndDate, IsResigned, ManagerAreaCode",
     "employee_code,name,is_duplicate,position_code,area_code,dmsid,start_date,end_date,is_resigned,manager_area_code"),
    ("BRV_SanPham", "brv_sanpham", "Id, Code, Name, GroupCode, Unit", "id_code,code,name,group_code,unit"),
    ("BRVSX_TraLai", "brvsx_tralai", "DocDate, Amount9, IsActive, Stt, CustomerCode", "doc_date,amount9,is_active,stt,customer_code"),
    ("DIM_ChucVu", "dim_chucvu", "DISTINCT PositionCode, Description", "position_code,description"),
    # Ton kho THAT (thay the Supabase inventory - cot "warehouse" ben do 100% NULL, khong dung duoc).
    # BranchCode tren BRV_Kho la B01=San xuat, B02=Kinh doanh Mien Bac, B03=Kinh doanh Mien Trung,
    # B04=Kinh doanh Mien Nam (xac nhan voi DA ben Bravo 15/07/2026) - join TonKhoDK.WarehouseId ->
    # BRV_Kho.Id de biet vung, roi ItemId -> brv_sanpham.id_code de biet ten san pham.
    ("BRV_Kho", "brv_kho", "Id, BranchCode, Code, Name", "id_code,branch_code,code,name"),
    ("BRV_TonKhoDK", "brv_tonkhodk", "WarehouseId, ItemId, Quantity, Amount, IsActive, FiscalYear",
     "warehouse_id,item_id,quantity,amount,is_active,fiscal_year"),
    # 13/08/2026: TON KHO THEO LO + HAN SU DUNG - xac nhan qua doi chieu voi file Excel "Bao cao ton
    # kho thanh pham" DNH cung cap (sheet "Ton kho theo lo date") - brv_tonkhodk o tren CHI co tong
    # theo kho, KHONG tach lo/han su dung. Quy mo NHO (~1.6K dong TonKhoDKLot, ~3.7K dong Lot - kiem
    # tra 13/08/2026), dung an toan chung co che RELOAD TOAN BO nhu cac bang nho khac o day.
    ("BRV_TonKhoDKLot", "brv_tonkhodklot",
     "BranchCode, WarehouseId, ItemId, ItemLotCode, Quantity, IsActive, Year",
     "branch_code,warehouse_id,item_id,item_lot_code,quantity,is_active,year"),
    # Khoa (item_lot_code, item_id) - KHONG dung item_lot_code rieng le, co the trung ma lo giua cac
    # san pham khac nhau (xac nhan tren Bravo THAT 13/08/2026, xem local_warehouse.py::SCHEMA).
    ("BRV_Lot", "brv_lot", "ItemLotCode, ItemId, MfgDate, ExpiryDate, IsActive",
     "item_lot_code,item_id,mfg_date,expiry_date,is_active"),
    # 04/09/2026: HE KHO SAN XUAT. BRV_* o tren chi la kho KINH DOANH (B01-B04) - do nam 2026 chi
    # 5,38 ty, trong khi kho san xuat co 229,80 ty. Chatbot truoc day bao 5,38 ty nhu the la toan
    # bo ton kho cong ty (2% su that). Hai he TACH HAN: BRV_Kho va BRVSX_Kho khong trung Id nao,
    # cap (kho, mat hang) nam 2026 trung 0 - cong hai he khong the dem trung.
    ("BRVSX_Kho", "brvsx_kho", "Id, BranchCode, Code, Name", "id_code,branch_code,code,name"),
    ("BRVSX_TonKhoDK", "brvsx_tonkhodk",
     "BranchCode, WarehouseId, ItemId, Quantity, Amount, IsActive, Year",
     "branch_code,warehouse_id,item_id,quantity,amount,is_active,year"),
]


def sync_small_table(bravo_tbl, local_tbl, bravo_cols, local_cols):
    """Reload toan bo bang tu Bravo. Query Bravo XONG TRUOC roi moi mo transaction xoa+ghi local -
    neu bravo_query() loi/mat ket noi giua chung, bang local KHONG bi dong (van con nguyen du lieu
    cu) thay vi bi xoa sach ma khong nap lai duoc (da tung xay ra voi dim_targetvungmien, gay thieu
    du lieu target MT mot thang ma khong ai biet cho toi khi nguoi dung phat hien so lieu sai)."""
    _, rows = bravo_query(f"SELECT {bravo_cols} FROM dbo.{bravo_tbl}")
    conn = get_conn()
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"DELETE FROM {local_tbl}")
        if rows:
            placeholders = ",".join(["?"] * len(local_cols.split(",")))
            conn.executemany(f"INSERT INTO {local_tbl} ({local_cols}) VALUES ({placeholders})", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    print(f"[{local_tbl}] Reload: {len(rows)} dong")


def compress_aged_out_months():
    """Chay MOI LAN sync (ca --full lan incremental): nen cac dong CON SOT LAI trong vhoadon_otc/etc
    ma DocDate da roi khoi cua so 12 thang gan nhat (vd lan sync FULL truoc chay luc thang nay con
    "moi", nay thoi gian troi qua khien no thanh "cu") - nen vao monthly_customer_summary roi XOA khoi
    bang chi tiet, giu warehouse.db luon dung dinh nghia 'chi giu chi tiet 12 thang gan nhat'. Doc/ghi
    hoan toan tren warehouse.db, KHONG can goi lai Bravo."""
    cutoff = _detail_cutoff_date()
    conn = get_conn()
    for table_local, channel_label in (("vhoadon_otc", "OTC"), ("vhoadon_etc", "ETC")):
        rows = conn.execute(
            f"SELECT doc_date, customer_code, item_code, amount9, quantity, unit_price, stt, employee_code "
            f"FROM {table_local} WHERE doc_date < ?", (str(cutoff),),
        ).fetchall()
        if not rows:
            continue
        by_month = {}
        for r in rows:
            ym = str(r[0])[:7]
            by_month.setdefault(ym, []).append(r)
        total_compressed = 0
        for ym, ym_rows in by_month.items():
            total_compressed += _compress_rows_to_summary(conn, ym_rows, channel_label, ym)
        conn.execute(f"DELETE FROM {table_local} WHERE doc_date < ?", (str(cutoff),))
        conn.commit()
        print(f"[{table_local}] Da nen {len(rows)} dong chi tiet qua han (< {cutoff}) thanh "
              f"{total_compressed} dong KH x thang, xoa khoi bang chi tiet.")
    conn.close()


def sync_fact_tonghopkhachhang(days=90):
    """Chi dong bo N ngay gan nhat (snapshot SaveDate) - lich su xa hon it gia tri cho KPI hien tai.
    23/07/2026: them ManagerCode - cot THAT tu Bravo xac dinh "TDV nay bao cao truc tiep len QLV nao",
    dung de thay the suy luan qua ma khu vuc (kem chinh xac hon, xem local_warehouse.py::SCHEMA).
    31/07/2026: them 6 cot (YearSaleTarget, Amount_Cus, IsRO, IsAC, MaxCustomerOrdAmount, EmpDMSCode).
    27/08/2026: DNH chot IsAC la co Active Customer cho CS (Cho si) va TK (kenh MT), khong phai
    ASO; dong da co IsAC khong duoc gan/cong them ASO o cac bao cao luong.
    Bang goc ben Bravo co 27 cot, truoc do kho chi keo 7 - 20 cot con lai deu phu du lieu 100% chu
    khong rong. Y nghia tung cot va ly do chon: xem local_warehouse.py::SCHEMA phan bang nay.
    Chi phi khong dang ke: kho chi giu 90 ngay ~ 3 ky x 13.000 dong.
    LUU Y: AreaCode CO Y khong keo o day du no cung co san va phu 100% - bang fact_thongketinhluong
    (Trieu them 30/07, ce6aeea) DA co cot do roi. Keo ve ca 2 noi se de 2 nguon lech nhau ma khong
    biet tin ben nao."""
    start = dt.date.today() - dt.timedelta(days=days)
    _, rows = bravo_query(
        "SELECT EmployeeCode, CustomerCode, Amount_CT, MonthSaleTarget, SaveDate, IsNC, ManagerCode, "
        "YearSaleTarget, Amount_Cus, IsRO, IsAC, MaxCustomerOrdAmount, EmpDMSCode "
        "FROM dbo.FACT_TongHopKhachHang WHERE SaveDate >= :a", a=str(start),
    )
    conn = get_conn()
    conn.execute("DELETE FROM fact_tonghopkhachhang")
    if rows:
        conn.executemany(
            "INSERT INTO fact_tonghopkhachhang (employee_code,customer_code,amount_ct,month_sale_target,"
            "save_date,is_nc,manager_code,year_sale_target,amount_cus,is_ro,is_ac,"
            "max_customer_ord_amount,emp_dms_code) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows,
        )
    conn.commit()
    conn.close()
    print(f"[fact_tonghopkhachhang] Reload {days} ngay gan nhat: {len(rows)} dong")


def sync_fact_thongketinhluong(days=90):
    """Dong bo ket qua tinh thuong/luong kinh doanh (KPI+luong moi QD 0429/.25 + QD 0107/2026) tu
    Bravo FACT_ThongKeTinhLuong - da xac nhan (xem local_warehouse.py::SCHEMA) day la ket qua Bravo
    DA TU TINH SAN dung cong thuc, khong phai du lieu tho can tinh lai. CHI 1 SNAPSHOT/NGAY (SaveDate),
    khac fact_tonghopkhachhang (nhieu dong/thang theo khach hang) - reload N ngay gan nhat la du vi
    day la du lieu KET QUA cuoi ky, khong can lich su xa de doi chieu tung khach hang."""
    start = dt.date.today() - dt.timedelta(days=days)
    _, rows = bravo_query(
        "SELECT EmployeeCode, EmployeeName, PositionCode, AreaCode, AreaCode2, ManagerCode, SaveDate, "
        "MonthSaleAmount, MonthSaleTarget, MonthSalePercent_R, "
        "DM1Amount, DM1Percent_R, DM2Amount, DM2Percent_R, DM3Amount, DM3Percent_R, "
        "DMBonus, TotalPoint, "
        "SKUQuantity, SKUTarget, SKUPercent_R, "
        "ROCustomerQuantity, ReOrderCusTarget, ROPercent_R, "
        "NewCustomerQuantity, NewCusTarget, NCPercent_R, "
        "ActiveCusQuantity, ActiveCusTarget, ACPercent_R, "
        "ASOQuantity, ASOPercent_R, ASOBonus, "
        "CallQuantity, CallTarget, CallPercent_R, "
        "V15Amount, V15Percent_R, V15Bonus, "
        "V22Amount, V22Percent_R, V22Bonus, "
        "V25Amount, V25Percent_R, V25Bonus, "
        "TargetProductAmount, TargetProductPercent_R, TPRPoint, "
        "LunchAmount_R, TransportAmount_R, PhoneAmount_R, SalaryCoeff "
        "FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate >= :a", a=str(start),
    )
    conn = get_conn()
    conn.execute("DELETE FROM fact_thongketinhluong")
    if rows:
        conn.executemany(
            "INSERT INTO fact_thongketinhluong (employee_code,employee_name,position_code,area_code,"
            "area_code2,manager_code,save_date,month_sale_amount,month_sale_target,month_sale_percent,"
            "dm1_amount,dm1_percent,dm2_amount,dm2_percent,dm3_amount,dm3_percent,dm_bonus,total_point,"
            "sku_quantity,sku_target,sku_percent,reorder_cus_quantity,reorder_cus_target,reorder_percent,"
            "new_cus_quantity,new_cus_target,new_cus_percent,active_cus_quantity,active_cus_target,"
            "active_cus_percent,aso_quantity,aso_percent,aso_bonus,call_quantity,call_target,call_percent,"
            "v15_amount,v15_percent,v15_bonus,v22_amount,v22_percent,v22_bonus,v25_amount,v25_percent,"
            "v25_bonus,target_product_amount,target_product_percent,tpr_point,lunch_amount,"
            "transport_amount,phone_amount,salary_coeff) "
            "VALUES (" + ",".join(["?"] * 52) + ")",
            rows,
        )
    conn.commit()
    conn.close()
    print(f"[fact_thongketinhluong] Reload {days} ngay gan nhat: {len(rows)} dong")


def sync_fact_congno():
    """Snapshot cong no THEO KHACH HANG x KENH tu SP goc DNH usp_DeptAccDueDate_GetData vao
    fact_congno_khachhang. PORT NGUYEN VAN tu D:\\DNH\\src\\alerts.py::get_bravo_receivables_snapshot
    (da verify khop 100% bao cao noi bo DNH) - KHONG duoc don gian hoa 3 diem sau:

      1. SP tra NHIEU result set -> dung raw_connection() + vong cur.nextset(), chon result set co
         DONG THOI CustomerCode va OverDueAmount. bravo_query() se lay nham set dau tien.
      2. raw.rollback() trong finally -> SP tao bang tam, rollback dam bao read-only tuyet doi voi Bravo.
      3. Map cot giu y nguyen: ClassCode='TM'->OTC (khac->ETC), AreaCode='MB1'->'MB', NULL->suy tu
         tien to ma KH (region_from_customer_code).

    HAI CHOT AN TOAN BAT BUOC (day la du lieu nguoi dung hoi truc tiep):
      - KHONG BAO GIO ghi de bang bang rong. SP loi quyen/VPN chap co the tra 0 dong; ghi de se lam
        chatbot mat kha nang tra loi cong no ma khong ai biet. 0 dong -> GIU snapshot cu, raise loi.
      - BEGIN IMMEDIATE + PRAGMA busy_timeout - backend doc song song, tranh 'database is locked'.

    21/08/2026: THEM ghi vao fact_congno_khachhang_history (1 ban ghi/khach/kenh/NGAY, khong phai
    moi lan sync) de tool bao cao co the so sanh cong no giua cac ky - truoc do bang chinh chi giu
    snapshot HIEN TAI (ghi de sach moi lan), khong co lich su nhu doanh thu. Xem schema trong
    local_warehouse.py de biet ly do chi insert 1 lan/ngay.
    """
    from debt_source import fetch_debt_snapshot

    source = fetch_debt_snapshot()
    snapshot_date = source.as_of_date
    snapshot_at = source.executed_at
    prepared = [(
        snapshot_date,
        snapshot_at,
        row["customer_code"],
        row["customer_name"],
        row["sales_channel"],
        row["area_code"],
        row["balance_end"],
        row["overdue_1_15"],
        row["overdue_15_30"],
        row["overdue_30_45"],
        row["overdue_gt_45"],
        row["total_overdue"],
    ) for row in source.rows]

    # CHOT AN TOAN 1: khong bao gio ghi de bang rong - giu snapshot cu, bao loi len tren.
    if not prepared:
        raise RuntimeError(
            "SP tra ve 0 dong cong no - GIU NGUYEN snapshot cu, KHONG ghi de. "
            "Kiem tra quyen EXECUTE / VPN / BRAVO_DATABASE.")

    conn = get_conn()
    conn.execute("PRAGMA busy_timeout=30000")   # CHOT AN TOAN 2: tranh 'database is locked'
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM fact_congno_khachhang")
        conn.executemany(
            "INSERT INTO fact_congno_khachhang (snapshot_date, snapshot_at, customer_code, "
            "customer_name, sales_channel, area_code, balance_end, overdue_1_15, overdue_15_30, "
            "overdue_30_45, overdue_gt_45, total_overdue) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            prepared)
        # 21/08/2026: THEM lich su theo ngay - CHI insert neu snapshot_date hom nay CHUA co trong
        # bang history (sync chay nhieu lan/ngay, khong insert lai moi lan de tranh bung no dung
        # luong - xem ghi chu day du trong local_warehouse.py::SCHEMA). Dung EXISTS trong CUNG
        # transaction voi ghi de o tren de dam bao nhat quan (khong bao gio history thieu 1 ngay
        # ma fact_congno_khachhang da co du lieu ngay do).
        # Boc try/except RIENG (khong lam hong phan ghi snapshot chinh o tren): bang history la
        # TINH NANG MOI, neu vi ly do gi bang chua ton tai (vd DB cu chua chay init_schema() moi
        # nhat) thi VAN PHAI giu duoc hanh vi cu (snapshot hien tai ghi thanh cong) - khong duoc de
        # 1 tinh nang phu lam crash ca luong cong no chinh nguoi dung dang phu thuoc.
        try:
            already = conn.execute(
                "SELECT 1 FROM fact_congno_khachhang_history WHERE snapshot_date=? LIMIT 1",
                (snapshot_date,)).fetchone()
            if not already:
                conn.executemany(
                    "INSERT INTO fact_congno_khachhang_history (snapshot_date, snapshot_at, customer_code, "
                    "customer_name, sales_channel, area_code, balance_end, overdue_1_15, overdue_15_30, "
                    "overdue_30_45, overdue_gt_45, total_overdue) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    prepared)
        except sqlite3.OperationalError:
            pass
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    set_sync_meta("fact_congno_khachhang", snapshot_date, snapshot_date)
    tot = sum(r[6] for r in prepared)
    tot_od = sum(r[11] for r in prepared)
    print(f"[fact_congno_khachhang] Snapshot {snapshot_date}: {len(prepared)} dong "
          f"(du no {tot:,.0f}, qua han {tot_od:,.0f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Dong bo toan bo lich su (thay vi chi gan day)")
    ap.add_argument("--congno-only", action="store_true",
                    help="Chi dong bo cong no (fact_congno_khachhang) - dung cho lich rieng neu SP chay lau")
    a = ap.parse_args()

    if a.congno_only:
        init_schema()
        sync_fact_congno()
        return

    init_schema()
    t0 = time.time()

    # OTC dong bo tu vHoaDonTotal (KHONG PHAI vHoaDon) - da xac nhan voi DA ben Bravo: vHoaDon am tham
    # loai bo cac dong dieu chinh/hoan (DocCode='HC', Amount9 am), gay overstate doanh thu OTC. vHoaDonTotal
    # khong co CityId (has_city=False) - vung mien phai join qua dms_khachhang, xem report_templates.py.
    # LUU Y: vHoaDonTotal cung khong co cac dong so luong=0 (hang khuyen mai/tang kem) ma vHoaDon co -
    # khong anh huong tinh doanh thu (amount9=0) nhung neu sau nay can phan tich rieng SL hang khuyen mai
    # thi phai tim nguon khac (vd cot CTKM tren vHoaDonTotal, chua kham pha).
    # ETC cung dong bo tu vHoaDonETCTotal (KHONG PHAI vHoaDonETC) - cung ly do nhu OTC: vHoaDonETC
    # thieu cac dong dieu chinh/hoan (DocCode='HC'), da xac nhan lech ~1.13 ty rieng nam 2025 toan quoc.
    if a.full:
        sync_hoadon_full("vHoaDonTotal", "vhoadon_otc", has_city=False, has_channel=True, channel_label="OTC")
        sync_hoadon_full("vHoaDonETCTotal", "vhoadon_etc", has_city=False, channel_label="ETC")
    else:
        sync_hoadon_recent("vHoaDonTotal", "vhoadon_otc", has_city=False, has_channel=True)
        sync_hoadon_recent("vHoaDonETCTotal", "vhoadon_etc", has_city=False)
        # Dong bo incremental chi cham N_RECENT_DAYS gan nhat, KHONG tu dong nen - goi rieng o day de
        # don dan cac thang da "gia" khoi cua so 12 thang gan nhat ke tu lan --full truoc.
        compress_aged_out_months()

    for bravo_tbl, local_tbl, bravo_cols, local_cols in SMALL_TABLES:
        sync_small_table(bravo_tbl, local_tbl, bravo_cols, local_cols)

    sync_fact_tonghopkhachhang()

    # KPI+luong moi (fact_thongketinhluong): boc try/except rieng nhu cong no - bang moi (28/07/2026),
    # neu Bravo doi cau truc/loi quyen thi KHONG duoc lam hong phan sync con lai (doanh thu/KPI cu van
    # phai chay binh thuong).
    try:
        sync_fact_thongketinhluong()
    except Exception as e:
        print(f"[CANH BAO] sync_fact_thongketinhluong loi, BO QUA lan nay (giu du lieu cu): {e}")

    # Cong no: boc try/except rieng - SP loi (quyen/VPN/timeout) KHONG duoc lam hong phan sync con lai.
    # Neu spike (muc 1.3) do SP > 60s: chuyen sang chay lich rieng bang --congno-only (timeout 300s) va
    # BO dong duoi day de tranh nhet SP cham vao vong sync chung (timeout 90s cua sync_scheduler.ps1).
    try:
        sync_fact_congno()
    except Exception:
        import traceback
        print("[fact_congno_khachhang] LOI (bo qua, giu snapshot cu):", traceback.format_exc())

    print(f"===== HOAN TAT DONG BO trong {time.time()-t0:.0f}s =====")


if __name__ == "__main__":
    _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(_log_dir, exist_ok=True)
    _log_path = os.path.join(_log_dir, "sync_warehouse.log")
    _logf = open(_log_path, "a", encoding="utf-8")

    class _Tee:
        def __init__(self, *s): self.s = [x for x in s if x]
        def write(self, d):
            for x in self.s:
                try: x.write(d); x.flush()
                except Exception: pass
        def flush(self):
            for x in self.s:
                try: x.flush()
                except Exception: pass

    sys.stdout = sys.stderr = _Tee(getattr(sys, "__stdout__", None), _logf)
    print(f"\n===== RUN {dt.datetime.now():%Y-%m-%d %H:%M:%S} =====")
    # 23/07/2026: PowerShell 5.1 co bug da biet - Process.ExitCode tra ve $null (khong throw, khong
    # sua duoc bang Refresh()/goi lai WaitForExit()) khi Start-Process dung -PassThru ket hop
    # -RedirectStandardOutput/-RedirectStandardError, du process da HasExited=True. sync_scheduler.ps1
    # tung dua vao $proc.ExitCode -eq 0 de biet lan sync co thanh cong khong -> ExitCode luon $null
    # khien scheduler tuong lan nao cung that bai, khong bao gio cap nhat $lastRunTime, va chay lai
    # MOI 5 PHUT (chu ky kiem tra) thay vi moi 60 phut (chu ky dong bo that su). Ghi file danh dau ket
    # qua RIENG (khong phu thuoc PowerShell doc dung exit code hay khong) de scheduler doc thay the.
    _result_path = os.path.join(_log_dir, "_sync_result.txt")
    try:
        main()
    except Exception:
        import traceback
        print("LOI:", traceback.format_exc())
        with open(_result_path, "w", encoding="utf-8") as rf:
            rf.write("FAIL")
        sys.exit(1)
    else:
        with open(_result_path, "w", encoding="utf-8") as rf:
            rf.write("OK")
