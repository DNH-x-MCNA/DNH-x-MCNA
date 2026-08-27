# -*- coding: utf-8 -*-
"""24/08/2026: 2 tool vong doi khach hang.

- customer_lifecycle_summary: dem theo co Bravo (is_nc/is_ro/is_ac) tren snapshot KPI.
- customers_silent: khach ngung mua, dua tren LICH SU HOA DON that (khong phu thuoc co nao).

Truoc do khong co tool nao phu nhom cau hoi nay, ma TP/QLV lai KHONG duoc dung SQL tu do nen khong
co duong lui - xem docs/doi_chieu_138_cau_voi_tool_thuc_te.md.
"""
import datetime as real_dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


class _FixedDate(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 19)


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT,
            year_sale_target REAL, amount_cus REAL, is_ro INTEGER, is_ac INTEGER,
            max_customer_ord_amount REAL, emp_dms_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
            kenh_bh TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        """
    )
    conn.execute("INSERT INTO dim_nhanvien VALUES ('TDV1','TDV Mot',0,'TDV','MB','D1',NULL,NULL,0,NULL)")
    conn.execute("INSERT INTO dim_nhanvien VALUES ('TDV2','TDV Hai',0,'TDV','MN','D2',NULL,NULL,0,NULL)")
    conn.execute("INSERT INTO dim_nhanvien VALUES ('QLV1','QLV Mot',0,'QLV','MB','Q1',NULL,NULL,0,NULL)")
    conn.execute("INSERT INTO dim_nhanvien VALUES ('TDVDUP','TDV Trung',1,'TDV','MB','D9',NULL,NULL,0,NULL)")

    # Co luu kieu TEXT '0'/'1' - dung Y HET production (do thuc te 24/08/2026: typeof=text du schema
    # khai INTEGER). Day la diem lam COALESCE(is_nc,0)=0 hong am tham, xem test rieng ben duoi.
    def fact(emp, cus, amount, save_date, nc="0", ro="0", ac="0", mgr="QLV1"):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (emp, cus, amount, 1_000_000, save_date, nc, mgr, 0, amount, ro, ac, 0, emp))

    # Thang 7: KH01 moi, KH02 co is_ro, KH03 KHONG mang co nao (van co doanh thu - dung nhu that).
    fact("TDV1", "KH01", 100, "2026-07-31", nc="1")
    fact("TDV1", "KH02", 200, "2026-07-31", ro="1")
    fact("TDV1", "KH03", 300, "2026-07-31")
    # Dong rollup QLV cho CUNG cac khach do - PHAI bi loai khoi tang nhan vien, neu khong se dem doi.
    for cus, amt in (("KH01", 100), ("KH02", 200), ("KH03", 300)):
        fact("QLV1", cus, amt, "2026-07-31", nc="1" if cus == "KH01" else "0")
    # Nhan vien bi danh dau trung - phai bi loai khoi SUM doanh so.
    fact("TDVDUP", "KH09", 999, "2026-07-31", ro="1")
    # Thang 6 + khach vung MN de test loc vung.
    fact("TDV1", "KH01", 50, "2026-06-30", ro="1")
    # TDV2 thuoc mot doi khac; neu de mac dinh manager_code="QLV1" thi fixture tu mau thuan voi
    # test phan quyen ben duoi va lam QLV1 nhin thay khach MN cua TDV2.
    fact("TDV2", "KH50", 70, "2026-07-31", nc="1", mgr="QLV2")

    # Hoa don: KH01 mua gan day, KH02 im lang tu 2026-03.
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-07-20','KH01','SP1',1000,1,1000,'H1',1,'D1','2026-07-20','A')")
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-03-10','KH02','SP1',5000,1,5000,'H2',1,'D1','2026-03-10','A')")
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-03-15','KHMOCOI','SP1',7000,1,7000,'H3',1,'D1','2026-03-15','A')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH01','Nha thuoc Mot',1,1,'D1','OTC')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH02','Nha thuoc Hai',1,2,'D1','OTC')")
    conn.commit()
    conn.close()


def _setup(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    return db_path


# ---------- customer_lifecycle_summary ----------

def test_dem_dung_tang_nhan_vien_KHONG_dem_doi_voi_dong_rollup_qlv(tmp_path, monkeypatch):
    """Bay lon nhat cua bang nay: co CA dong TDV lan dong rollup QLV cho cung mot khach. Do thuc te
    24/08/2026 tren production: 2.258 dong / 1.131 khach that, va SUM(is_nc) cho 174 trong khi so
    khach that chi 92 (sai gap 1,89 lan)."""
    _setup(tmp_path, monkeypatch)
    r = rt.customer_lifecycle_summary(year_month="2026-07")
    m = r["months"][0]

    # KH01, KH02, KH03 tu TDV1 + KH50 tu TDV2. Dong QLV1 va TDVDUP bi loai.
    assert m["tong_khach"] == 4
    assert m["khach_moi"] == 2, "KH01 va KH50 - KHONG duoc dem lai KH01 tu dong rollup QLV1"
    assert m["so_is_ro"] == 1


def test_khach_khong_mang_co_dem_dung_bay_COALESCE_tren_cot_TEXT(tmp_path, monkeypatch):
    """BAY SQLite THAT (24/08/2026): is_nc/is_ro luu kieu TEXT ('0'/'1') du schema khai INTEGER.
    So sanh THANG 'f.is_nc=1' van dung vi SQLite ap affinity cua COT len gia tri; nhung
    COALESCE(f.is_nc,0)=0 la BIEU THUC - bieu thuc KHONG co affinity nen thanh so sanh TEXT voi
    INTEGER va LUON SAI. Ban dau viet bang COALESCE cho ra 0 khach thay vi 646 tren du lieu that."""
    _setup(tmp_path, monkeypatch)
    r = rt.customer_lifecycle_summary(year_month="2026-07")
    assert r["months"][0]["khach_khong_mang_co"] == 1, "KH03: co doanh thu nhung khong mang co nao"


def test_loai_nhan_vien_bi_danh_dau_trung_khoi_doanh_so(tmp_path, monkeypatch):
    """So DEM khach khong bi anh huong (da COUNT DISTINCT) nhung doanh so dung SUM thi bi thoi phong."""
    _setup(tmp_path, monkeypatch)
    r = rt.customer_lifecycle_summary(year_month="2026-07")
    m = r["months"][0]
    assert m["doanh_so_tang_nhan_vien"] == 100 + 200 + 300 + 70, "999 cua TDVDUP phai bi loai"
    assert m["doanh_so_khach_moi"] == 100 + 70


def test_canh_bao_dinh_nghia_co_khoa_dung_muc_tin_cay_tung_co(tmp_path, monkeypatch):
    """DNH da xac nhan TEN VIET TAT ngay 26/08/2026 (NC=New Customer, RO=Re-Order, AC=Active
    Customer) - nhung ten duoc xac nhan KHONG co nghia moi con so deu dung duoc nhu nhau.

    is_ac ten la "Active Customer" ma chi ung 37-44 khach/thang tren ~6.000 (0,6%), trong khi ~80%
    khach mang is_ro tuc VAN DANG MUA. Hai dieu do khong the cung dung neu hieu is_ac la phep dem
    khach dang hoat dong. Nen canh bao PHAI giu dung khoang cach: goi ten thi duoc, dung con so de
    tra loi "cong ty co bao nhieu khach dang hoat dong" thi KHONG.

    Test nay tung khoa DUNG CHUOI CHU "CHUA XAC NHAN VOI DNH" - viet lai canh bao la no do du noi
    dung van du y, tuc bao ve cach dien dat chu khong bao ve noi dung. Nay khoa theo Y."""
    _setup(tmp_path, monkeypatch)
    r = rt.customer_lifecycle_summary(year_month="2026-07")
    canh_bao = r["canh_bao_dinh_nghia"]
    assert "is_ac" in canh_bao, "canh bao phai noi den is_ac"
    assert "hoat dong" in canh_bao, "canh bao phai nhac cum 'khach hoat dong' de canh chinh no"
    assert "0,6%" in canh_bao or "37-44" in canh_bao, \
        "phai neu CON SO that lam bang chung, khong chi noi chung chung la 'can than'"
    assert "so_is_ro" in r["months"][0] and "so_is_ac" in r["months"][0], \
        "ten truong tra ve van phai trung tinh, de model khong tu dat nhan nghiep vu"
    for cam in ("mua_lai", "khach_mua_lai", "khach_hoat_dong"):
        assert cam not in r["months"][0], f"khong duoc dat ten nghiep vu chua xac nhan: {cam}"


def test_loc_theo_vung_va_theo_doi_qlv(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    mn = rt.customer_lifecycle_summary(year_month="2026-07", scope_area_code="MN")["months"][0]
    assert mn["tong_khach"] == 1 and mn["khach_moi"] == 1  # chi KH50 cua TDV2 (vung MN)

    team = rt.customer_lifecycle_summary(year_month="2026-07", scope_employee_code="QLV1")["months"][0]
    assert team["tong_khach"] == 3, "chi khach cua doi QLV1 (TDV1), khong thay KH50 cua TDV2"


def test_is_ac_chi_dem_cs_tk_khong_gan_nham_cho_tdv(tmp_path, monkeypatch):
    """27/08/2026: is_ac la co cua CS/Cho si va TK/kenh MT, khong phai co ASO cua TDV."""
    db_path = _setup(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dim_nhanvien VALUES ('CS1','Cho si Mot',0,'CS','MB','CS-D1',NULL,NULL,0,NULL)")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES "
                 "('CS1','KHCS',400,1000000,'2026-07-31','0','QLV1',0,400,'0','1',0,'CS1')")
    # Co is_ac tren dong TDV la du lieu khong hop le theo quy tac moi; phep dem phai fail-closed
    # va chi nhan dong thuoc CS/TK.
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES "
                 "('TDV1','KHTDV',500,1000000,'2026-07-31','0','QLV1',0,500,'0','1',0,'TDV1')")
    conn.commit()
    conn.close()

    month = rt.customer_lifecycle_summary(year_month="2026-07")["months"][0]

    assert month["so_is_ac"] == 1


def test_chuoi_nhieu_thang_va_thang_thieu_snapshot(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.customer_lifecycle_summary(year_month="2026-07", months_back=3)
    assert [m["month"] for m in r["months"]] == ["2026-05", "2026-06", "2026-07"]
    assert r["months"][0]["khong_co_du_lieu"] is True, "2026-05 khong co snapshot"
    assert r["months"][1]["tong_khach"] == 1  # thang 6 chi co KH01
    assert "2026-05" in r["canh_bao_thieu_lich_su"]


def test_lifecycle_etc_fail_closed_vi_nguon_chi_phu_otc(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.customer_lifecycle_summary(year_month="2026-07", scope_channel="ETC")
    assert r["not_applicable"] is True
    assert "OTC" in r["error"] and r["channel_scope"] == "ETC"


# ---------- customers_silent ----------

def test_liet_ke_dung_khach_im_lang_va_tinh_dung_so_ngay(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.customers_silent(as_of_date="2026-07-29", silent_days=60, lookback_months=6)

    codes = [k["customer_code"] for k in r["khach_im_lang"]]
    assert "KH01" not in codes, "KH01 mua 20/07 - khong im lang"
    assert "KH02" in codes and "KHMOCOI" in codes
    kh02 = next(k for k in r["khach_im_lang"] if k["customer_code"] == "KH02")
    assert kh02["lan_mua_cuoi"] == "2026-03-10"
    assert kh02["so_ngay_im_lang"] == (real_dt.date(2026, 7, 29) - real_dt.date(2026, 3, 10)).days


def test_sap_xep_khach_mat_nhieu_tien_nhat_len_dau(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.customers_silent(as_of_date="2026-07-29", silent_days=60, lookback_months=6)
    doanh_thu = [k["doanh_thu_ky_nhin_lai"] for k in r["khach_im_lang"]]
    assert doanh_thu == sorted(doanh_thu, reverse=True)
    assert r["khach_im_lang"][0]["customer_code"] == "KHMOCOI"  # 7000 > 5000


def test_giu_khach_mo_coi_khong_co_trong_danh_muc(tmp_path, monkeypatch):
    """Khach 'mo coi' (co hoa don nhung khong co trong danh muc) la CO THAT - vd HCM13508 ~2,3 ty
    doanh thu 2022-2025. Loai di la lam bay hoi doanh thu that, phai giu lai va ghi ro thieu ten."""
    _setup(tmp_path, monkeypatch)
    r = rt.customers_silent(as_of_date="2026-07-29", silent_days=60, lookback_months=6)
    mocoi = next(k for k in r["khach_im_lang"] if k["customer_code"] == "KHMOCOI")
    assert "khong co trong danh muc" in mocoi["customer_name"]
    assert mocoi["doanh_thu_ky_nhin_lai"] == 7000


def test_nguong_im_lang_thay_doi_lam_doi_danh_sach(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    rong = rt.customers_silent(as_of_date="2026-07-29", silent_days=1, lookback_months=6)
    chat = rt.customers_silent(as_of_date="2026-07-29", silent_days=200, lookback_months=6)
    assert rong["so_khach"] > chat["so_khach"]
    assert chat["so_khach"] == 0, "khong ai im lang qua 200 ngay trong cua so nhin lai"


def test_im_lang_dung_bang_nguong_ngay_van_duoc_tinh(tmp_path, monkeypatch):
    """Mo ta tool quy dinh so_ngay_im_lang >= silent_days, nen dung bang nguong khong duoc loai."""
    db_path = _setup(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                 "('2026-05-30','KHBOUND','SP1',3000,1,3000,'HB',1,'D1','2026-05-30','A')")
    conn.commit()
    conn.close()

    r = rt.customers_silent(as_of_date="2026-07-29", silent_days=60, lookback_months=6)
    boundary = next(k for k in r["khach_im_lang"] if k["customer_code"] == "KHBOUND")
    assert boundary["so_ngay_im_lang"] == 60
