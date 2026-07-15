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
import sys, os, argparse, datetime as dt, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
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

N_RECENT_DAYS = 10  # so ngay gan nhat can refresh moi lan chay incremental (du lieu Bravo con "sơ bo")


def _sqlite_val(v):
    """SQLite khong ho tro Decimal/date/datetime truc tiep - chuyen ve float/str.
    LUU Y: phai kiem tra datetime TRUOC date (datetime la subclass cua date) - datetime GIU NGUYEN
    ca gio:phut:giay (can cho created_at de phat hien "chay don don KPI"), chi date thuan moi cat con
    YYYY-MM-DD."""
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


# ==================== BANG HOA DON (lon, co lich su) ====================
def sync_hoadon_full(table_bravo, table_local, has_city):
    print(f"[{table_local}] Dong bo FULL lich su...")
    cols_sql, rows = bravo_query(f"SELECT MIN(DocDate) mn, MAX(DocDate) mx FROM dbo.{table_bravo}")
    mn, mx = rows[0]
    mn = dt.datetime.strptime(mn, "%Y-%m-%d").date() if isinstance(mn, str) else mn
    mx = dt.datetime.strptime(mx, "%Y-%m-%d").date() if isinstance(mx, str) else mx
    conn = get_conn()
    conn.execute(f"DELETE FROM {table_local}")
    conn.commit()
    total = 0
    t0 = time.time()
    for a, b in month_ranges(mn, mx):
        cols = "DocDate, CustomerCode, ItemCode, Amount9, Quantity, UnitPrice, Stt, EmpDMSCode2" + (", CityId" if has_city else "") + ", CreatedAt"
        _, rows = bravo_query(
            f"SELECT {cols} FROM dbo.{table_bravo} WHERE DocDate BETWEEN :a AND :b",
            a=str(a), b=str(b),
        )
        if rows:
            placeholders = ",".join(["?"] * (10 if has_city else 9))
            cols_local = "doc_date,customer_code,item_code,amount9,quantity,unit_price,stt,employee_code" + (",city_id" if has_city else "") + ",created_at"
            conn.executemany(
                f"INSERT INTO {table_local} ({cols_local}) VALUES ({placeholders})", rows,
            )
            conn.commit()
            total += len(rows)
        print(f"  {a} -> {b}: {len(rows)} dong (tong {total}, {time.time()-t0:.0f}s)")
    conn.close()
    set_sync_meta(table_local, str(mn), str(mx))
    print(f"[{table_local}] Xong FULL: {total} dong, {time.time()-t0:.0f}s")


def sync_hoadon_recent(table_bravo, table_local, has_city, days=N_RECENT_DAYS):
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    print(f"[{table_local}] Refresh gia tang {start} -> {today}...")
    conn = get_conn()
    conn.execute(f"DELETE FROM {table_local} WHERE doc_date >= ?", (str(start),))
    conn.commit()
    cols = "DocDate, CustomerCode, ItemCode, Amount9, Quantity, UnitPrice, Stt, EmpDMSCode2" + (", CityId" if has_city else "") + ", CreatedAt"
    _, rows = bravo_query(
        f"SELECT {cols} FROM dbo.{table_bravo} WHERE DocDate >= :a", a=str(start),
    )
    if rows:
        placeholders = ",".join(["?"] * (10 if has_city else 9))
        cols_local = "doc_date,customer_code,item_code,amount9,quantity,unit_price,stt,employee_code" + (",city_id" if has_city else "") + ",created_at"
        conn.executemany(
            f"INSERT INTO {table_local} ({cols_local}) VALUES ({placeholders})", rows,
        )
        conn.commit()
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
    ("DMS_KhachHang", "dms_khachhang", "Code, Name, CityId, Id, EmpDMSCode1, KenhBH", "code,name,city_id,id_code,emp_code,kenh_bh"),
    ("DIM_NhanVien", "dim_nhanvien", "EmployeeCode, Name, IsDuplicate, PositionCode, AreaCode, DMSId", "employee_code,name,is_duplicate,position_code,area_code,dmsid"),
    ("BRV_SanPham", "brv_sanpham", "Code, Name, GroupCode, Unit", "code,name,group_code,unit"),
    ("BRVSX_TraLai", "brvsx_tralai", "DocDate, Amount9, IsActive, Stt, CustomerCode", "doc_date,amount9,is_active,stt,customer_code"),
    ("DIM_ChucVu", "dim_chucvu", "DISTINCT PositionCode, Description", "position_code,description"),
]


def sync_small_table(bravo_tbl, local_tbl, bravo_cols, local_cols):
    _, rows = bravo_query(f"SELECT {bravo_cols} FROM dbo.{bravo_tbl}")
    conn = get_conn()
    conn.execute(f"DELETE FROM {local_tbl}")
    if rows:
        placeholders = ",".join(["?"] * len(local_cols.split(",")))
        conn.executemany(f"INSERT INTO {local_tbl} ({local_cols}) VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()
    print(f"[{local_tbl}] Reload: {len(rows)} dong")


def sync_fact_tonghopkhachhang(days=90):
    """Chi dong bo N ngay gan nhat (snapshot SaveDate) - lich su xa hon it gia tri cho KPI hien tai."""
    start = dt.date.today() - dt.timedelta(days=days)
    _, rows = bravo_query(
        "SELECT EmployeeCode, CustomerCode, Amount_CT, MonthSaleTarget, SaveDate, IsNC "
        "FROM dbo.FACT_TongHopKhachHang WHERE SaveDate >= :a", a=str(start),
    )
    conn = get_conn()
    conn.execute("DELETE FROM fact_tonghopkhachhang")
    if rows:
        conn.executemany(
            "INSERT INTO fact_tonghopkhachhang (employee_code,customer_code,amount_ct,month_sale_target,save_date,is_nc) "
            "VALUES (?,?,?,?,?,?)", rows,
        )
    conn.commit()
    conn.close()
    print(f"[fact_tonghopkhachhang] Reload {days} ngay gan nhat: {len(rows)} dong")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Dong bo toan bo lich su (thay vi chi gan day)")
    a = ap.parse_args()

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
        sync_hoadon_full("vHoaDonTotal", "vhoadon_otc", has_city=False)
        sync_hoadon_full("vHoaDonETCTotal", "vhoadon_etc", has_city=False)
    else:
        sync_hoadon_recent("vHoaDonTotal", "vhoadon_otc", has_city=False)
        sync_hoadon_recent("vHoaDonETCTotal", "vhoadon_etc", has_city=False)

    for bravo_tbl, local_tbl, bravo_cols, local_cols in SMALL_TABLES:
        sync_small_table(bravo_tbl, local_tbl, bravo_cols, local_cols)

    sync_fact_tonghopkhachhang()

    print(f"===== HOAN TAT DONG BO trong {time.time()-t0:.0f}s =====")


if __name__ == "__main__":
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "sync_warehouse.log")
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
    try:
        main()
    except Exception:
        import traceback
        print("LOI:", traceback.format_exc())
        sys.exit(1)
