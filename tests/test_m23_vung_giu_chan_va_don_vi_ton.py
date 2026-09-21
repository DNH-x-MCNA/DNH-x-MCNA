# -*- coding: utf-8 -*-
"""18/09/2026 - cau M23 va M40.

M23 hoi HAI ve: "so khach moi, tai kich hoat, mua lai va ngung mua cua TUNG VUNG" va "ty le giu
chan sau 3/6 thang". Chatbot tra ve mot dong toan quoc cua thang 9 MTD, khong co vung nao va khong
co giu chan - truot ca hai ve. Hai nguyen nhan rieng biet:

1. customer_lifecycle_summary chi co scope_area_code de LOC, khong co truc vung. Checker S67 cua
   chinh cau nay da chot san so de doi chieu: MB 4.859 / MN 1.080 / MT 987, tong 6.926.

2. customer_cohort_retention voi months_back mac dinh 6 thi cua so cohort bat dau o thang_to - 5,
   trong khi mot cohort phai lui it nhat 6 thang truoc thang TRON gan nhat moi cham duoc tuoi 6.
   Cot tuoi 6 vi the rong 100% - khong phai vi thieu du lieu (kho co lich su tu 2022) ma vi cua so
   tu chon sai. Do that: months_back=6 cho 0/6 cohort co so o tuoi 6; months_back=12 cho 5/12.

M40: hai ve cua phep chia months_of_cover khong cung don vi - ton kho dem bang VIEN, hoa don ban
theo HOP. Hysdin ra "155 thang" trong khi quy ve hop chi khoang 6,8 thang.

Du lieu gia, khong cham Bravo."""
import datetime as real_dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho_vung(tmp_path):
    """KH_MB co dong TDV (MB) VA dong rollup QLV (MB). KH_QLV_MN chi co dong QLV (MN) - khach do
    QLV tu ban khi dia ban trong, dung truong hop LCH00074 ma S67 neu ten."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT,
            year_sale_target REAL, amount_cus REAL, is_ro INTEGER, is_ac INTEGER,
            max_customer_ord_amount REAL, emp_dms_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE dmssx_nhanvien (id_code INTEGER, name TEXT, dmscode TEXT, code TEXT,
            is_active TEXT);
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
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
    """)
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,0,?,?,?,NULL,NULL,0,NULL)", [
        ("TDV_MB", "TDV Mien Bac", "TDV", "MB", "D1"),
        ("QLV_MB", "QLV Mien Bac", "QLV", "MB", "Q1"),
        ("QLV_MN", "QLV Mien Nam", "QLV", "MN", "Q2"),
    ])
    conn.execute("INSERT INTO monthly_customer_summary VALUES ('2025-05','OTC','X','D1',0,0)")

    def fact(emp, cus, nc="0", ro="0"):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,100,0,'2026-08-31',?,'QLV_MB',"
                     "0,0,?,'0',0,?)", (emp, cus, nc, ro, emp))

    fact("TDV_MB", "KH_MB", nc="1")
    fact("QLV_MB", "KH_MB")           # dong rollup cua chinh khach tren - khong duoc dem thanh vung khac
    fact("QLV_MN", "KH_QLV_MN", nc="1")
    fact("TDV_MB", "KH_MB_RO", ro="1")
    conn.commit()
    conn.close()
    return str(path)


def test_tach_duoc_so_khach_theo_tung_vung(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_vung(tmp_path))

    m = rt.customer_lifecycle_summary(year_month="2026-08")["months"][0]

    theo_vung = {v["area_code"]: v for v in m["theo_vung"]}
    assert set(theo_vung) == {"MB", "MN"}
    assert theo_vung["MB"]["tong_khach"] == 2 and theo_vung["MB"]["khach_moi"] == 1
    assert theo_vung["MN"]["tong_khach"] == 1 and theo_vung["MN"]["khach_moi"] == 1


def test_cac_vung_cong_lai_bang_dung_so_toan_quoc(tmp_path, monkeypatch):
    """Quy tac S67: moi khach thuoc DUNG MOT vung. Group thang theo area_code se dem KH_MB hai lan."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_vung(tmp_path))

    m = rt.customer_lifecycle_summary(year_month="2026-08")["months"][0]

    for cot in ("tong_khach", "khach_moi", "so_is_ro", "khach_khong_mang_co"):
        assert sum(v[cot] for v in m["theo_vung"]) == m[cot], cot


def test_khach_do_qlv_tu_ban_van_duoc_tinh_cho_vung_cua_qlv(tmp_path, monkeypatch):
    """KH_QLV_MN khong co dong TDV nao - phai rot vao MN chu khong bien mat."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_vung(tmp_path))

    m = rt.customer_lifecycle_summary(year_month="2026-08")["months"][0]

    mn = next(v for v in m["theo_vung"] if v["area_code"] == "MN")
    assert mn["tong_khach"] == 1


def _kho_cohort(tmp_path):
    """Khach mua thang 2026-01 roi mua lai thang 2026-07 (tuoi 6)."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
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
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
    """)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH1','Khach Mot',1,1,'D1','GT')")
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES (?,'KH1','SP1',100,1,100,?,1,'D1',?,'OTC')",
        [("2026-01-10", "H1", "2026-01-10"), ("2026-07-10", "H2", "2026-07-10"),
         ("2026-08-10", "H3", "2026-08-10")])
    conn.commit()
    conn.close()
    return str(path)


def test_noi_rong_cua_so_cohort_de_tuoi_lon_nhat_co_so_that(tmp_path, monkeypatch):
    """months_back=3 chi lui den 2026-06, cohort 2026-01 nam ngoai - tuoi 6 se rong hoan toan."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_cohort(tmp_path))

    kq = rt.customer_cohort_retention(month_to="2026-08", months_back=3, age_months=[6])

    assert kq["cohort_from_da_mo_rong"] is True
    assert kq["cohort_from"] <= "2026-01"
    cohort = next(c for c in kq["cohorts"] if c["cohort_month"] == "2026-01")
    tuoi6 = next(r for r in cohort["retention"] if r["age_month"] == 6)
    assert tuoi6["retained_customers"] == 1          # KH1 co mua lai o thang 2026-07


def test_khong_mo_rong_thi_khong_ghi_ly_do_thua(tmp_path, monkeypatch):
    """months_back da du rong: khong duoc bao la da mo rong."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_cohort(tmp_path))

    kq = rt.customer_cohort_retention(month_to="2026-08", months_back=24, age_months=[1])

    assert kq["cohort_from_da_mo_rong"] is False
    assert kq["ly_do_mo_rong_cua_so"] is None


class _NgayCoDinh(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 28)


def test_canh_bao_ton_va_ban_khong_cung_don_vi(tmp_path, monkeypatch):
    """M40: ton dem bang VIEN, hoa don ban theo HOP - months_of_cover bi thoi phong bang he so quy
    cach (Hysdin: 155 so voi khoang 6,8 thang that). Chua co bang quy doi nen khong sua cong thuc
    duoc, nhung TUYET DOI khong duoc de model viet ra 'ton 155 thang'."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_tonkhodklot (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            item_lot_code TEXT, quantity REAL, is_active INTEGER);
        CREATE TABLE brv_lot (item_lot_code TEXT, item_id INTEGER, mfg_date TEXT,
            expiry_date TEXT, is_active INTEGER);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, employee_code TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT);
    """)
    conn.execute("INSERT INTO brv_kho VALUES (2,'B02','KMB','Kho Mien Bac')")
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'MB')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH1','Khach',1)")
    conn.execute("INSERT INTO brv_sanpham VALUES ('SP1','Hysdin (Hop x 2 vi x 10 vien)','G','Vien',1)")
    conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B02',2,1,'LO1',96420,1)")
    conn.execute("INSERT INTO brv_sanpham VALUES ('SP0','SKU co quy cach khac','G','Vien',2)")
    conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B02',2,2,'LO2',1000,1)")
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,'KH1','SP1',10000,621,17143,'DMS01')",
                     [("2026-05-10",), ("2026-06-10",), ("2026-07-10",)])
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,'KH1','SP0',10000,10,10000,'DMS01')",
                     [("2026-05-10",), ("2026-06-10",), ("2026-07-10",)])
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _NgayCoDinh)
    monkeypatch.setattr(rt, "get_sync_meta", lambda _t: (None, None, None))

    kq = rt.inventory_expiry_report(scope_area_code="MB", limit=30)["supply_risk"]

    assert kq["don_vi_hai_ve_khong_khop"] is True
    assert "KHONG phai so thang" in kq["canh_bao_don_vi"]
    assert "KHONG duoc XEP HANG cac SKU" in kq["canh_bao_don_vi"]
    assert "155" not in kq["canh_bao_don_vi"]
    assert "TON_KHONG_BAN_3_THANG khong bi anh huong" in kq["canh_bao_don_vi"]
    # 155 va 100 la hai ti le chua quy doi; thu tu chi theo ma, khong theo ti le.
    assert [row["item_code"] for row in kq["rows"]] == ["SP0", "SP1"]
