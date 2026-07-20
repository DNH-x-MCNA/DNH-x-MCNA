# -*- coding: utf-8 -*-
"""
Kho du lieu LOCAL (SQLite) - ban sao co index cua du lieu Bravo, dong bo dinh ky qua sync_warehouse.py.
Muc dich: tra loi chatbot nhanh (<=10s) ma khong can goi Bravo qua VPN cho moi cau hoi - Bravo van la
nguon SU THAT goc (chi doc), kho nay chi la ban sao CO THE CU vai chuc phut, dung cho truy van
thong ke/so sanh lich su. Cau hoi can du lieu "ngay bay gio" van co the can fallback ve Bravo song.

KHONG bao gio ghi/sua gi tren Bravo - kho nay hoan toan tach biet, chi doc (SELECT) tu Bravo roi
chep vao file SQLite rieng cua du an.
"""
import os, sqlite3, datetime as dt

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warehouse.db")

SCHEMA = """
-- employee_code (tu EmpDMSCode tren Bravo) - la DMSId CUA CHINH nguoi ban hang (TDV), CHI dung tin
-- cay cho nhan vien CA NHAN (vd "tungtx", "HYE_02"...). Ma khu vuc/quan ly vung (MBKV*, ASM*, MN*...)
-- KHONG xuat hien truc tiep tren hoa don qua cot nay - xem employee_kpi() (snapshot thang) cho nhom do.
-- channel_code (tu EmpDMSCode2 tren Bravo, CHI co o OTC) - ma QLV/kenh gan tren hoa don (KHAC
-- employee_code la nguoi ban thuc su) - dung de nhan dien cac "kenh dac biet" nhu Modern Trade (Long
-- Chau, Pharmacity...) duoc ghi nhan qua ban ghi "nhan vien ao" trong dim_nhanvien (vd DMSId='ASM01',
-- Name='Kênh MT') - xem revenue_by_region() cho cach tach doanh thu kenh nay.
-- created_at = CreatedAt tren Bravo (thoi diem BAN GHI THUC SU duoc tao trong he thong, KHAC voi
-- doc_date la ngay chung tu tren hoa don - co the bi chon/sua tay). Dung de phat hien "chay don don
-- KPI": tao hang loat hoa don CreatedAt dồn vao 1 ngay (thuong cuoi ky) nhung DocDate rai rac truoc do.
CREATE TABLE IF NOT EXISTS vhoadon_otc (
    doc_date TEXT NOT NULL, customer_code TEXT, item_code TEXT,
    amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER, employee_code TEXT,
    created_at TEXT, channel_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_otc_docdate ON vhoadon_otc(doc_date);
CREATE INDEX IF NOT EXISTS idx_otc_customer ON vhoadon_otc(customer_code);
CREATE INDEX IF NOT EXISTS idx_otc_item ON vhoadon_otc(item_code);
CREATE INDEX IF NOT EXISTS idx_otc_city ON vhoadon_otc(city_id);
CREATE INDEX IF NOT EXISTS idx_otc_employee ON vhoadon_otc(employee_code, doc_date);
CREATE INDEX IF NOT EXISTS idx_otc_channel ON vhoadon_otc(channel_code);

CREATE TABLE IF NOT EXISTS vhoadon_etc (
    doc_date TEXT NOT NULL, customer_code TEXT, item_code TEXT,
    amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_etc_docdate ON vhoadon_etc(doc_date);
CREATE INDEX IF NOT EXISTS idx_etc_customer ON vhoadon_etc(customer_code);
CREATE INDEX IF NOT EXISTS idx_etc_item ON vhoadon_etc(item_code);
CREATE INDEX IF NOT EXISTS idx_etc_employee ON vhoadon_etc(employee_code, doc_date);

-- LUU Y: Bravo co mot so ma bi trung (vd DIM_NhanVien.IsDuplicate) nen KHONG dat PRIMARY KEY/UNIQUE
-- cho cac cot ma o day - chi danh index thuong de tra cuu nhanh, tranh loi khi dong bo gap ma trung.
CREATE TABLE IF NOT EXISTS dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
CREATE INDEX IF NOT EXISTS idx_dtp_cityid ON dim_tinhthanhpho(city_id);
CREATE TABLE IF NOT EXISTS dim_targetvungmien (area_code TEXT, channel_code TEXT, amount REAL, doc_date TEXT);
CREATE INDEX IF NOT EXISTS idx_tvm_docdate ON dim_targetvungmien(doc_date);
CREATE TABLE IF NOT EXISTS fact_kehoachtongetc (doc_date TEXT, amount REAL, item_group TEXT);
-- id_code = DMSSX_KhachHang.Id (id noi bo cua DMS, khac customer_code). ETC KHONG co cot gan NV
-- phu trach truc tiep tren khach hang (khac OTC) - EmpDMSCode2 tren hoa don van la nguon duy nhat.
CREATE TABLE IF NOT EXISTS dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, kenh_bh TEXT);
CREATE INDEX IF NOT EXISTS idx_dmssx_code ON dmssx_khachhang(code);
-- emp_code = EmpDMSCode1 (ma NV DMS duoc GAN de phu trach khach hang nay - khac EmpDMSCode2 tren
-- hoa don la NV THUC TE ban hang; 2 ma co the khac nhau).
CREATE TABLE IF NOT EXISTS dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, emp_code TEXT, kenh_bh TEXT);
CREATE INDEX IF NOT EXISTS idx_dms_code ON dms_khachhang(code);
-- position_code: TDV=Trinh duoc vien, QLV=Quan ly vung, CTV/CS/TP/PP/TBP/TK = cac vai tro khac
-- (xem dim_chucvu de dich sang ten tieng Viet). area_code: MB/MT/MN.
-- dmsid: ma noi bo DMS - CO THE trung voi employee_code cua 1 dong KHAC (da xac nhan that, vd DMSId
-- 'DNH00601' vua la employee_code cua 1 dong TDV vua la dmsid cua 1 dong QLV khac) - TUYET DOI KHONG
-- coi dmsid la unique key, luon xu ly nhu co the tra ve NHIEU dong khi tra cuu.
-- start_date/end_date/is_resigned: lich su dam nhiem - Bravo GIU LAI ban ghi cu khi doi nguoi (khong
-- xoa), nen co the dung lam timeline. manager_area_code: ma khu vuc nho V01-V22 (xem org_hierarchy.py
-- de biet cach suy luan QLV nao phu trach to nao - suy luan qua ten co hau to "(QLV)", KHONG phai
-- khoa ngoai tuong minh, nen co the co truong hop khong xac dinh duoc).
CREATE TABLE IF NOT EXISTS dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER, manager_area_code TEXT);
CREATE INDEX IF NOT EXISTS idx_dnv_code ON dim_nhanvien(employee_code);
CREATE INDEX IF NOT EXISTS idx_dnv_dmsid ON dim_nhanvien(dmsid);
CREATE INDEX IF NOT EXISTS idx_dnv_manager_area ON dim_nhanvien(manager_area_code);
CREATE TABLE IF NOT EXISTS dim_chucvu (position_code TEXT, description TEXT);
CREATE INDEX IF NOT EXISTS idx_dcv_code ON dim_chucvu(position_code);
-- id_code = BRV_SanPham.Id (khoa noi, dung de join voi brv_tonkhodk.item_id - KHAC code la ma san
-- pham dang text hien thi cho nguoi dung).
CREATE TABLE IF NOT EXISTS brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
CREATE INDEX IF NOT EXISTS idx_bsp_code ON brv_sanpham(code);
CREATE INDEX IF NOT EXISTS idx_bsp_idcode ON brv_sanpham(id_code);

-- Ton kho THAT tu Bravo (thay Supabase inventory - cot warehouse ben do 100% NULL). branch_code tren
-- brv_kho: B01=San xuat, B02=Kinh doanh Mien Bac, B03=Kinh doanh Mien Trung, B04=Kinh doanh Mien Nam
-- (xac nhan voi DA 15/07/2026). Join: brv_tonkhodk.warehouse_id -> brv_kho.id_code de biet vung,
-- brv_tonkhodk.item_id -> brv_sanpham.id_code de biet ten san pham.
CREATE TABLE IF NOT EXISTS brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
CREATE INDEX IF NOT EXISTS idx_bkho_idcode ON brv_kho(id_code);
CREATE TABLE IF NOT EXISTS brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL, amount REAL, is_active INTEGER);
CREATE INDEX IF NOT EXISTS idx_tk_warehouse ON brv_tonkhodk(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_tk_item ON brv_tonkhodk(item_id);
CREATE TABLE IF NOT EXISTS brvsx_tralai (doc_date TEXT, amount9 REAL, is_active INTEGER, stt TEXT, customer_code TEXT);
CREATE INDEX IF NOT EXISTS idx_tralai_docdate ON brvsx_tralai(doc_date);

CREATE TABLE IF NOT EXISTS fact_tonghopkhachhang (
    employee_code TEXT, customer_code TEXT, amount_ct REAL,
    month_sale_target REAL, save_date TEXT, is_nc INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ftk_savedate ON fact_tonghopkhachhang(save_date);
CREATE INDEX IF NOT EXISTS idx_ftk_employee ON fact_tonghopkhachhang(employee_code);

CREATE TABLE IF NOT EXISTS sync_meta (
    table_name TEXT PRIMARY KEY,
    last_synced_at TEXT,
    earliest_synced_date TEXT,
    latest_synced_date TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def init_schema():
    conn = get_conn()
    try:
        # Migration: them cot channel_code TRUOC khi chay SCHEMA - SCHEMA co CREATE INDEX tren cot
        # nay, se loi "no such column" neu bang vhoadon_otc da ton tai tu truoc (CREATE TABLE IF NOT
        # EXISTS khong tu them cot moi vao bang da co san) ma chua duoc ALTER truoc.
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vhoadon_otc'").fetchone()
        if has_table:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(vhoadon_otc)").fetchall()]
            if "channel_code" not in cols:
                conn.execute("ALTER TABLE vhoadon_otc ADD COLUMN channel_code TEXT")
                conn.commit()
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_sync_meta(table_name: str):
    conn = get_conn()
    try:
        r = conn.execute("SELECT last_synced_at, earliest_synced_date, latest_synced_date "
                          "FROM sync_meta WHERE table_name=?", (table_name,)).fetchone()
        return r if r else (None, None, None)
    finally:
        conn.close()


def set_sync_meta(table_name: str, earliest: str, latest: str):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sync_meta (table_name, last_synced_at, earliest_synced_date, latest_synced_date) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(table_name) DO UPDATE SET "
            "last_synced_at=excluded.last_synced_at, "
            "earliest_synced_date=MIN(COALESCE(earliest_synced_date, excluded.earliest_synced_date), excluded.earliest_synced_date), "
            "latest_synced_date=MAX(COALESCE(latest_synced_date, excluded.latest_synced_date), excluded.latest_synced_date)",
            (table_name, dt.datetime.now().isoformat(), earliest, latest),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
    print(f"Schema da tao/xac nhan tai: {DB_PATH}")
