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

SCHEMA = r"""
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
-- Bang nhan vien RIENG cho phia SX/ETC - xac nhan 20/07/2026: mot nhom nhan vien (vd ma DNH00087,
-- DNH00268, Sale01-Sale15...) hoan toan KHONG co trong DIM_NhanVien, chi ton tai o day. dmscode/code
-- thuong giong nhau (co truong hop khac, vd Sale03/Sale04) - luon thu ca 2 khi tra cuu.
CREATE TABLE IF NOT EXISTS dmssx_nhanvien (id_code INTEGER, name TEXT, dmscode TEXT, code TEXT, is_active TEXT);
CREATE INDEX IF NOT EXISTS idx_dmssxnv_dmscode ON dmssx_nhanvien(dmscode);
CREATE INDEX IF NOT EXISTS idx_dmssxnv_code ON dmssx_nhanvien(code);
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
    month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_ftk_savedate ON fact_tonghopkhachhang(save_date);
CREATE INDEX IF NOT EXISTS idx_ftk_employee ON fact_tonghopkhachhang(employee_code);
CREATE INDEX IF NOT EXISTS idx_ftk_manager ON fact_tonghopkhachhang(manager_code);

-- 28/07/2026 (KPI+luong moi QD 0429/.25 + QD 0107/2026): Bravo FACT_ThongKeTinhLuong DA TU TINH SAN
-- ket qua thuong theo dung cong thuc trong 3 Phu luc chinh sach thu nhap (MN-TDV, MT-QLV, MT-TDV) -
-- VERIFY THUC TE 28/07/2026 tren TM23100123 (Tran Thien Khiem, QLV MN, SaveDate 2026-07-30):
--   DMBonus / (DM1Amount*DM1Percent_R + DM2Amount*DM2Percent_R + DM3Amount*DM3Percent_R) = 0.8897
--   = TotalPoint (0.88970) TUYET DOI KHOP -> xac nhan DM*Percent_R chinh la he so k_tn (Bang 01 PDF)
--   va TotalPoint chinh la "KPIs" trong cong thuc "Muc huong = Sigma(DM_n x k_tn) x KPIs".
-- CHI dong bo 1 SNAPSHOT/NGAY (SaveDate) - KHONG co nhieu ban ghi/ngay nhu fact_tonghopkhachhang.
-- position_code: THUC TE co 7 gia tri chu khong chi 'QLV'/'TDV' - do tren Bravo ky 31/07/2026 thay
-- du ca TP, PP, CS, TK, CTV. _bonus_threshold() van xu ly dung (TDV -> 65, MOI vai tro khac -> 70),
-- nhung dung tuong bang chi co 2 loai. RIENG CTV (3 nguoi MN) dang bi cham nguong 70% nhu quan ly -
-- can hoi DNH xem co dung y khong.
--
-- !!! 31/07/2026 - BANG NAY CO BA TANG CHONG LEN NHAU, NANG HON fact_tonghopkhachhang (chi 2 tang).
-- Do tren Bravo ky 31/07/2026 (206 ma), cong MonthSaleAmount theo tung cap:
--     TP (truong phong/GD mien, 3 nguoi)      33.307.889.644
--     QLV (21 nguoi)                          33.307.889.644
--     TDV + CS + TK + CTV (tang la, ~180)     33.307.889.644
--     PP (lop phu them, chi MN, 2 nguoi)       5.198.362.685
--     -> cong ca bang                        105.122.031.617
-- Ca BA tang deu DUNG BANG doanh thu OTC that thang 7 tu vHoaDonTotal (33.307.889.644). Cong ca bang
-- ra dung 3 x 33.307.889.644 + 5.198.362.685 = 105.122.031.617, tuc SAI GAP HON 3 LAN.
-- => Muon ra tong thi PHAI CHON MOT TANG. Va luu y: meo "ma nao khong xuat hien lam manager_code"
--    (dung tot cho fact_tonghopkhachhang 2 tang) LA SAI o day, vi QLV vua quan ly nguoi khac vua bi
--    TP quan ly - ap meo do ra 71.814.141.973, sai 2,16 lan.
--
-- HIEN TAI CHUA NGUY HIEM: salary_detail() chi tra DUNG 1 DONG cho 1 nguoi (LIMIT 1), khong cong gop;
-- va bang nay CO Y KHONG duoc khai trong schema_context.py nen AI khong the tu viet SQL cham vao.
-- !!! NEU SAU NAY KHAI BANG NAY VAO schema_context.py, PHAI VIET KEM CANH BAO 3 TANG NGAY TRONG CUNG
-- LAN SUA DO. Bay 2 tang cua fact_tonghopkhachhang da gay 4 cau tra loi sai ngay 31/07 (trong do 2
-- cau con bao nguoc lai voi khach rang du lieu cua ho hong) - bay 3 tang se nang hon.
CREATE TABLE IF NOT EXISTS fact_thongketinhluong (
    employee_code TEXT, employee_name TEXT, position_code TEXT, area_code TEXT, area_code2 TEXT,
    manager_code TEXT, save_date TEXT,
    month_sale_amount REAL, month_sale_target REAL, month_sale_percent REAL,
    dm1_amount REAL, dm1_percent REAL, dm2_amount REAL, dm2_percent REAL, dm3_amount REAL, dm3_percent REAL,
    dm_bonus REAL, total_point REAL,
    sku_quantity REAL, sku_target REAL, sku_percent REAL,
    reorder_cus_quantity REAL, reorder_cus_target REAL, reorder_percent REAL,
    new_cus_quantity REAL, new_cus_target REAL, new_cus_percent REAL,
    active_cus_quantity REAL, active_cus_target REAL, active_cus_percent REAL,
    aso_quantity REAL, aso_percent REAL, aso_bonus REAL,
    call_quantity REAL, call_target REAL, call_percent REAL,
    v15_amount REAL, v15_percent REAL, v15_bonus REAL,
    v22_amount REAL, v22_percent REAL, v22_bonus REAL,
    v25_amount REAL, v25_percent REAL, v25_bonus REAL,
    target_product_amount REAL, target_product_percent REAL, tpr_point REAL,
    lunch_amount REAL, transport_amount REAL, phone_amount REAL,
    salary_coeff REAL
);
CREATE INDEX IF NOT EXISTS idx_ftl_savedate ON fact_thongketinhluong(save_date);
CREATE INDEX IF NOT EXISTS idx_ftl_employee ON fact_thongketinhluong(employee_code, save_date);
CREATE INDEX IF NOT EXISTS idx_ftl_manager ON fact_thongketinhluong(manager_code);

-- Du lieu hoa don CU HON 12 THANG duoc NEN ve day (KH x thang, KHONG giu item_code/quantity/unit_price/
-- created_at/stt tung dong) de giam dung luong luu tru va giam rui ro lo du lieu chi tiet hoa don qua
-- khu (xem sync_warehouse.py::_compress_old_months()). 12 thang gan nhat van giu nguyen chi tiet trong
-- vhoadon_otc/vhoadon_etc nhu cu - CHI phan cu hon moi bi nen. Vi vay top_products/check_order_timing
-- (can item_code/created_at tung dong) KHONG the chay dung cho khoang ngay nam ngoai 12 thang gan nhat.
CREATE TABLE IF NOT EXISTS monthly_customer_summary (
    year_month TEXT NOT NULL,   -- 'YYYY-MM'
    channel TEXT NOT NULL,      -- 'OTC' hoac 'ETC'
    customer_code TEXT,
    employee_code TEXT,         -- giu lai de loc theo NV/vung (join qua bang khach hang/nhan vien)
    revenue REAL,                -- SUM(amount9) trong thang do
    invoice_count INTEGER        -- COUNT(DISTINCT stt) trong thang do
);
CREATE INDEX IF NOT EXISTS idx_mcs_yearmonth ON monthly_customer_summary(year_month);
CREATE INDEX IF NOT EXISTS idx_mcs_customer ON monthly_customer_summary(customer_code);
CREATE INDEX IF NOT EXISTS idx_mcs_employee ON monthly_customer_summary(employee_code);
CREATE INDEX IF NOT EXISTS idx_mcs_channel ON monthly_customer_summary(channel, year_month);

-- Cong no THEO KHACH HANG x KENH, snapshot tuc thoi tu SP goc DNH usp_DeptAccDueDate_GetData
-- (xem sync_warehouse.py::sync_fact_congno + D:\DNH\src\alerts.py::get_bravo_receivables_snapshot).
-- MOT DONG = (khach hang x kenh): khach ban ca OTC lan ETC co 2 dong -> moi truy van PHAI SUM,
-- KHONG duoc gia dinh 1 dong/khach. total_overdue tinh SAN khi ghi = overdue_1_15+15_30+30_45+gt_45.
-- Dinh nghia bucket theo @_Period2=15: 1-15 / 16-30 / 31-45 / >45 ngay (khop bucket cu).
-- KHONG dat UNIQUE/PRIMARY KEY (Bravo co the tra ma trung, va bang bi ghi de nguyen khoi moi snapshot).
CREATE TABLE IF NOT EXISTS fact_congno_khachhang (
    snapshot_date TEXT,          -- 'YYYY-MM-DD' ngay chay SP (mot snapshot/lan sync)
    snapshot_at TEXT,            -- ISO datetime day du (de biet snapshot cach day bao lau -> canh bao > 6h)
    customer_code TEXT,
    customer_name TEXT,
    sales_channel TEXT,          -- 'OTC' (ClassCode='TM') hoac 'ETC' ('SX')
    area_code TEXT,              -- MB/MB2/MN/MT (MB1 da map ve MB), NULL -> suy tu tien to ma KH
    balance_end REAL,            -- CloseBal (tong du no cuoi ky)
    overdue_1_15 REAL,           -- CloseBal5
    overdue_15_30 REAL,          -- CloseBal6
    overdue_30_45 REAL,          -- CloseBal7
    overdue_gt_45 REAL,          -- CloseBal8
    total_overdue REAL           -- tinh san = tong 4 bucket tren
);
CREATE INDEX IF NOT EXISTS idx_congno_customer ON fact_congno_khachhang(customer_code);
CREATE INDEX IF NOT EXISTS idx_congno_channel ON fact_congno_khachhang(sales_channel);
CREATE INDEX IF NOT EXISTS idx_congno_area ON fact_congno_khachhang(area_code);

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


# Cot da them vao SCHEMA SAU KHI bang da ton tai tu ban cu hon - CREATE TABLE IF NOT EXISTS khong tu
# them cot moi vao bang da co san, va SCHEMA co CREATE INDEX tren cac cot nay nen se loi "no such
# column" neu khong ALTER truoc. Moi lan them cot moi vao 1 bang da ton tai trong SCHEMA, PHAI khai
# them vao day (chu KHONG duoc quen - da tung gay loi thieu dmsid/start_date/... khi warehouse.db cu
# chua duoc --full lai sau khi SCHEMA doi).
_COLUMN_MIGRATIONS = {
    "vhoadon_otc": [("channel_code", "TEXT")],
    "dim_nhanvien": [("dmsid", "TEXT"), ("start_date", "TEXT"), ("end_date", "TEXT"),
                      ("is_resigned", "INTEGER"), ("manager_area_code", "TEXT")],
    "brv_sanpham": [("id_code", "INTEGER")],
    "fact_tonghopkhachhang": [("manager_code", "TEXT")],
}


def init_schema():
    conn = get_conn()
    try:
        for table, new_cols in _COLUMN_MIGRATIONS.items():
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not has_table:
                continue
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for col_name, col_type in new_cols:
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
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
