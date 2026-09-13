# -*- coding: utf-8 -*-
"""V15/S61b, V21/S69b, V23/S68b (UAT 12-13/09/2026) - khong goi API, khong cham Bravo.

V15: khach tung mua TRUOC cua so hien thi bi goi la "khach mo moi". Do tren Bravo doi MBKV2 thang
8/2026: dung la 22 khach mo moi + 215 tai kich hoat, nhung cach cu goi 32 khach la moi (10 khach da
mua tu 2023-2025). Kem theo: so khach theo tung TDV phai tinh san, khong de model dem tren top-N.
V21: "doanh thu ky nhin lai" (co dinh den hom nay) khac "6 thang truoc lan mua cuoi".
V23: binh quan truoc khi ngung phai tinh tren chuoi thang lien tiep, ke ca phan ngoai cua so.
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
        return cls(2026, 9, 13)


SCHEMA = """
CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
  quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER, employee_code TEXT,
  created_at TEXT, channel_code TEXT);
CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
  quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT, created_at TEXT);
CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
  employee_code TEXT, revenue REAL, invoice_count INTEGER);
CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
  emp_code TEXT, kenh_bh TEXT);
CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, kenh_bh TEXT);
CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
  position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
  is_resigned INTEGER, manager_area_code TEXT);
CREATE TABLE brv_sanpham (code TEXT, name TEXT);
"""


def _db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB')")
    con.execute("INSERT INTO brv_sanpham VALUES ('A','Thuoc A')")
    con.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("TM01", "Nguyen Van A", 0, "TDV", "MB", "D1", "2025-01-01", None, 0, None),
        ("TM02", "Tran Thi B", 0, "TDV", "MB", "D2", "2025-01-01", None, 0, None),
    ])
    khach = ("KH_MOI", "KH_QUAY_TRONG_CUA_SO", "KH_QUAY_NGOAI_CUA_SO", "KH_DEU", "KH_IM_LANG")
    con.executemany("INSERT INTO dms_khachhang VALUES (?,?,1,1,'D1','OTC')",
                    [(ma, "Khach " + ma) for ma in khach])

    def hoa_don(ngay, ma_kh, tien, nv="D1"):
        con.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ngay, ma_kh, "A", tien, 1, tien, ngay + ma_kh, 1, nv, ngay, "OTC"))

    # Chi tiet hoa don chi giu 12 thang gan nhat (cutoff 2025-09-01 voi hom nay 13/09/2026).
    hoa_don("2026-08-05", "KH_MOI", 500, "D2")           # lan dau mua that su
    hoa_don("2026-08-20", "KH_MOI", 300, "D2")           # co mua lai ngay trong thang
    hoa_don("2026-03-10", "KH_QUAY_TRONG_CUA_SO", 900)   # tung mua trong cua so
    hoa_don("2026-08-12", "KH_QUAY_TRONG_CUA_SO", 700)
    hoa_don("2026-08-15", "KH_QUAY_NGOAI_CUA_SO", 1000)  # trong cua so chi thay dung 1 lan
    hoa_don("2026-07-02", "KH_DEU", 400)
    hoa_don("2026-08-02", "KH_DEU", 450)
    hoa_don("2026-01-20", "KH_IM_LANG", 120)             # lan mua cuoi -> im lang tu do
    hoa_don("2025-12-15", "KH_IM_LANG", 180)
    hoa_don("2025-11-11", "KH_IM_LANG", 200)
    # Lich su cu hon cua so CHI ton tai o bang nen - day la phan cach cu bo qua.
    con.executemany("INSERT INTO monthly_customer_summary VALUES (?,?,?,?,?,?)", [
        ("2024-05", "OTC", "KH_QUAY_NGOAI_CUA_SO", "D1", 600.0, 1),
        ("2024-06", "OTC", "KH_QUAY_NGOAI_CUA_SO", "D1", 800.0, 1),
        ("2024-07", "OTC", "KH_QUAY_NGOAI_CUA_SO", "D1", 1000.0, 1),
        ("2024-02", "OTC", "KH_QUAY_NGOAI_CUA_SO", "D1", 5000.0, 1),  # cu hon, KHONG lien tiep
        ("2025-08", "OTC", "KH_IM_LANG", "D1", 300.0, 1),
    ])
    con.commit()
    con.close()


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _db(path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    return path


def _theo_ma(ket_qua):
    return {r["customer_code"]: r for r in ket_qua["customers"]}


def test_v15_khach_tung_mua_ngoai_cua_so_khong_duoc_goi_la_khach_moi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.customer_movement(month="2026-08", history_months=6)

    kh = _theo_ma(r)
    assert kh["KH_QUAY_NGOAI_CUA_SO"]["movement"] == "REACTIVATED"
    assert kh["KH_QUAY_NGOAI_CUA_SO"]["first_purchase_month"] == "2024-02"
    assert kh["KH_MOI"]["movement"] == "NEW_OR_FIRST_OBSERVED"
    assert kh["KH_MOI"]["first_purchase_month"] == "2026-08"
    assert kh["KH_QUAY_TRONG_CUA_SO"]["movement"] == "REACTIVATED"
    assert r["summary_all_customers"]["counts"]["NEW_OR_FIRST_OBSERVED"] == 1


def test_v23_binh_quan_truoc_khi_ngung_tinh_tren_chuoi_lien_tiep_ngoai_cua_so(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.customer_movement(month="2026-08", history_months=6)

    kh = _theo_ma(r)["KH_QUAY_NGOAI_CUA_SO"]
    # Chuoi lien tiep ngay truoc ky nghi la 05-07/2024 (2.400d), KHONG gom 02/2024 vi dut quang.
    assert kh["last_active_month_before_reactivation"] == "2024-07"
    assert kh["pre_stop_streak_month_count"] == 3
    assert kh["pre_stop_average_monthly_revenue"] == 800
    assert kh["recovery_pct_vs_pre_stop_average"] == 125  # 1000/800
    assert kh["inactive_months_before_reactivation"] == 24  # 08/2024 -> 07/2026


def test_v15_so_khach_theo_tung_tdv_tinh_san_tren_toan_bo_tap(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.customer_movement(month="2026-08", history_months=6, limit=1)

    assert len(r["customers"]) == 1  # danh sach hien thi bi cat
    theo_nv = {x["employee_code"]: x for x in r["by_employee"]}
    # Quy khach cho nguoi ban trong CHINH thang 8 va doi chieu duoc bang ma nhan vien, khong phai DMSId.
    assert theo_nv["TM02"]["khach_moi"] == 1
    assert theo_nv["TM02"]["khach_moi_co_mua_lai"] == 1
    assert theo_nv["TM02"]["ty_le_mua_lai_khach_moi_pct"] == 100
    assert theo_nv["TM02"]["employee_name"] == "Tran Thi B"
    assert theo_nv["TM01"]["khach_moi"] == 0
    assert theo_nv["TM01"]["khach_tai_kich_hoat"] == 2


def test_v21_doanh_thu_sau_thang_truoc_lan_mua_cuoi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.customers_silent(as_of_date="2026-09-13", silent_days=60, lookback_months=12)

    kh = {x["customer_code"]: x for x in r["khach_im_lang"]}["KH_IM_LANG"]
    assert kh["lan_mua_cuoi"] == "2026-01-20"
    # Ky nhin lai CO DINH (10/2025-09/2026) chi thay 500d; con 6 thang truoc khi ngung la 800d vi co
    # ca thang 08/2025 nam ngoai ky do (lay tu bang nen). Hai con so nay KHONG duoc dung lan nhau.
    assert kh["doanh_thu_ky_nhin_lai"] == 500
    truoc = kh["sau_thang_truoc_khi_ngung"]
    # 6 thang lich den 01/2026: 08/2025 (300, tu bang nen) + 11,12/2025 + 01/2026 = 800
    assert (truoc["tu_thang"], truoc["den_thang"]) == ("2025-08", "2026-01")
    assert truoc["doanh_thu"] == 800
    assert truoc["so_thang_co_mua"] == 4
    assert truoc["trung_binh_thang"] == 200
