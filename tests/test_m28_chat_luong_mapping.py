# -*- coding: utf-8 -*-
"""M28/S75 (13/09/2026): ty le khach khong gan TDV / ma NV la / sai vung / thieu danh muc THEO THANG.

Truoc do operational_data_quality chi dem tai MOT thoi diem nen M28 ("ty le ... theo thang") khong tra
loi tron cau duoc. Va phep dem "ma NV la" chi noi dim_nhanvien: 28/29 ma nguoi ban tren hoa don ETC
thang 8/2026 nam o bang nhan vien SX/ETC rieng nen bi dem nham la ma la (228 khach MB), that su chi 1
ma khong co o dau. Checker S75 cung thieu phep noi nay.
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


def _kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
          quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER, employee_code TEXT,
          created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
          quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT, created_at TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
          emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, kenh_bh TEXT);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
          position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
          is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, emp_dms_code TEXT, manager_code TEXT,
          save_date TEXT, customer_code TEXT, amount_ct REAL, month_sale_target REAL);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT, position_code TEXT,
          area_code TEXT, manager_code TEXT, save_date TEXT, month_sale_amount REAL,
          month_sale_target REAL, month_sale_percent REAL);
        INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB');
        INSERT INTO dim_nhanvien VALUES ('TM01','TDV 1',0,'TDV','MB','D1','2025-01-01',NULL,0,NULL);
        INSERT INTO dmssx_nhanvien VALUES ('SX01','ETC_01','NV he ETC');
        """
    )
    con.executemany("INSERT INTO dms_khachhang VALUES (?,?,?,1,'D1','OTC')", [
        ("KH_OK", "Khach du mapping", 1),
        ("KH_KHONG_GAN", "Khach hoa don thieu ma NV", 1),
        ("KH_MA_LA", "Khach ma NV khong co o dau", 1),
        ("KH_SAI_VUNG", "Khach khong map duoc vung", 99),  # city_id khong co trong danh muc tinh
    ])
    # KH_NGOAI_DM khong co trong ca hai bang danh muc khach.

    def otc(ngay, kh, nv):
        con.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ngay, kh, "A", 100, 1, 100, ngay + kh, 1, nv, ngay, "OTC"))

    otc("2026-08-05", "KH_OK", "D1")
    otc("2026-08-06", "KH_KHONG_GAN", "")
    otc("2026-08-07", "KH_MA_LA", "KHONG_TON_TAI")
    otc("2026-08-08", "KH_SAI_VUNG", "D1")
    otc("2026-08-09", "KH_NGOAI_DM", "D1")
    otc("2026-07-05", "KH_OK", "D1")
    # Hoa don ETC do nhan vien he ETC ban: ma nam o dmssx_nhanvien -> KHONG phai ma la.
    con.execute("INSERT INTO vhoadon_etc VALUES ('2026-08-10','KH_ETC','A',500,1,500,'E1','ETC_01','2026-08-10')")
    con.commit(); con.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "_trang_thai_nguon_don_hang",
                        lambda: {"status": "UNAVAILABLE", "reason": "test"})
    return path


def _thang(tmp_path, monkeypatch, thang="2026-08"):
    _kho(tmp_path, monkeypatch)
    r = rt.operational_data_quality(as_of_date="2026-08-31")
    rows = {x["thang"]: x for x in r["checks"]["customer_mapping_by_month"]["rows"]}
    return rows[thang]


def test_dem_dung_tung_loai_loi_mapping_theo_thang(tmp_path, monkeypatch):
    t8 = _thang(tmp_path, monkeypatch)

    assert t8["tong_khach"] == 6  # 5 khach OTC + 1 khach ETC
    assert t8["khong_gan_tdv"] == 1
    # KH_SAI_VUNG (city la) + KH_NGOAI_DM + KH_ETC (khong co trong danh muc khach ETC nen khong ra vung)
    assert t8["khong_map_vung"] == 3
    assert t8["khong_co_trong_danh_muc"] == 2  # KH_NGOAI_DM + KH_ETC (khong co trong dmssx_khachhang)
    assert t8["co_it_nhat_mot_loi"] == 4


def test_ma_nv_he_etc_khong_bi_dem_la_ma_la(tmp_path, monkeypatch):
    t8 = _thang(tmp_path, monkeypatch)

    assert t8["ma_nv_la"] == 1           # chi KH_MA_LA
    assert t8["ma_nv_he_etc"] == 1       # KH_ETC do NV he ETC ban - khong phai loi
    assert round(t8["ty_le_ma_nv_la_pct"], 2) == round(100 / 6, 2)


def test_co_du_chuoi_thang_va_mau_so_theo_tung_thang(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)

    r = rt.operational_data_quality(as_of_date="2026-08-31")

    rows = r["checks"]["customer_mapping_by_month"]["rows"]
    assert [x["thang"] for x in rows] == ["2026-07", "2026-08"]
    assert rows[0]["tong_khach"] == 1 and rows[0]["co_it_nhat_mot_loi"] == 0
    assert "S75" in r["checks"]["customer_mapping_by_month"]["definition"]
