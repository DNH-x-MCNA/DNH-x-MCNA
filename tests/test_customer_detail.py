# -*- coding: utf-8 -*-
"""Kiem chung report_templates.customer_detail() - CHUA co test rieng truoc 19/08/2026 cho cac
hanh vi phan quyen theo kenh (scope_channel) va vung (scope_area_code) da tai lieu hoa trong
docstring nhung chua duoc khoa lai bang test."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
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
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dim_chucvu (position_code TEXT, description TEXT);
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT,
            customer_name TEXT, sales_channel TEXT, area_code TEXT, balance_end REAL,
            overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL,
            total_overdue REAL);
        """
    )
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB')")
    conn.commit()
    conn.close()


def test_khach_2_kenh_tong_dung_va_nhan_dung_kenh(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH01','Khach A',1,100,NULL,'GT')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-07-10','KH01','SP01',2000000,20,100000,'HD2',1,'NV02','2026-07-10')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH01", date_from="2026-07-01", date_to="2026-07-31")

    assert result["channel"] == "OTC+ETC"
    assert result["revenue"] == 3_000_000
    assert result["orders"] == 2
    assert result["avg_order_value"] == 1_500_000


def test_scope_channel_otc_redact_khach_2_kenh_khong_lo_so_etc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH01','Khach A',1,100,NULL,'GT')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-07-10','KH01','SP01',2000000,20,100000,'HD2',1,'NV02','2026-07-10')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH01", date_from="2026-07-01", date_to="2026-07-31",
                                scope_channel="OTC")

    assert "error" not in result
    assert result["revenue"] == 1_000_000  # CHI OTC, khong lo doanh thu ETC
    assert result["channel"] == "OTC"
    assert "channel_scope" in result


def test_scope_channel_otc_tu_choi_khach_thuan_etc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dmssx_khachhang VALUES ('KH02','Khach ETC',1,200,'GT')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-07-10','KH02','SP01',2000000,20,100000,'HD1',1,'NV02','2026-07-10')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH02", date_from="2026-07-01", date_to="2026-07-31",
                                scope_channel="OTC")

    assert "error" in result


def test_scope_channel_etc_redact_khach_2_kenh_khong_lo_so_otc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH01','Khach A',1,100,NULL,'GT')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.execute("INSERT INTO vhoadon_etc VALUES "
                "('2026-07-10','KH01','SP01',2000000,20,100000,'HD2',1,'NV02','2026-07-10')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH01", date_from="2026-07-01", date_to="2026-07-31",
                                scope_channel="ETC")

    assert "error" not in result
    assert result["revenue"] == 2_000_000
    assert result["orders"] == 1
    assert result["channel"] == "ETC"
    assert "channel_scope" in result


def test_scope_channel_etc_tu_choi_khach_thuan_otc(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH01','Khach OTC',1,100,NULL,'GT')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH01','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH01", date_from="2026-07-01", date_to="2026-07-31",
                                scope_channel="ETC")

    assert "error" in result
    assert "OTC" in result["error"]


def test_scope_area_code_tu_choi_khach_ngoai_vung(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (2,'Can Tho','MN')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH_MN','Khach Mien Nam',2,300,NULL,'GT')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH_MN", date_from="2026-07-01", date_to="2026-07-31",
                                scope_area_code="MB")

    assert "error" in result


def test_goi_hang_loat_nhieu_ma_1_loi_khong_lam_hong_ca_lo_nhung_khong_duoc_im_lang(tmp_path, monkeypatch):
    """24/08/2026: SUA hanh vi - truoc day ma bi tu choi (ngoai vung) bi AM THAM loai khoi ket qua,
    khien nguoi dung hoi 2 ma nhung chi thay 1 ket qua ma khong biet ma kia bi gi (khac han nguyen tac
    "khong duoc im lang bo qua loi" da ap dung nhat quan o salary_detail). Gio ca 2 ma DEU co mat
    trong 'customers', ma bi loi mang 'error' + 'requested_customer_code' thay vi bi xoa mat."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (2,'Can Tho','MN')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH_MB','Khach MB',1,100,NULL,'GT')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH_MN','Khach MN',2,300,NULL,'GT')")
    conn.execute("INSERT INTO vhoadon_otc VALUES "
                "('2026-07-10','KH_MB','SP01',1000000,10,100000,'HD1',1,'NV01','2026-07-10','ASM01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(customer_code="KH_MB,KH_MN", date_from="2026-07-01",
                                date_to="2026-07-31", scope_area_code="MB")

    assert result["is_bulk"] is True
    assert result["count"] == 2  # CA HAI ma deu co mat, khong bi xoa mat ma nao
    by_requested = {c["requested_customer_code"]: c for c in result["customers"]}
    assert by_requested["KH_MB"].get("customer_code") == "KH_MB"
    assert "error" not in by_requested["KH_MB"]
    assert "error" in by_requested["KH_MN"]  # KH_MN bi tu choi (ngoai vung) NHUNG van duoc bao ro ly do
