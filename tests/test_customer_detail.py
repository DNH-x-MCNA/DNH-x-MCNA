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
import nl2sql
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


def test_tra_ten_benh_vien_mo_ho_tra_danh_sach_ma_de_chon(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO dmssx_khachhang VALUES (?,?,?,?,?)",
        [
            ("BNI00003", "Bệnh viện đa khoa tỉnh Bắc Ninh", 1, 1, "GT"),
            ("BNI00017", "Bệnh viện y học cổ truyền và phục hồi chức năng tỉnh Bắc Ninh", 1, 2, "GT"),
            ("BGI00699", "Bệnh viện Đa khoa tỉnh Bắc Giang", 1, 3, "GT"),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(
        customer_code="Bệnh viện Bắc Ninh",
        date_from="2026-01-01", date_to="2026-09-16",
    )

    assert result["customer_lookup_status"] == "ambiguous"
    assert {row["customer_code"] for row in result["customer_candidates"]} == {
        "BNI00003", "BNI00017",
    }
    assert all(row["customer_code"] != "BGI00699" for row in result["customer_candidates"])


def test_tra_ten_day_du_duy_nhat_tu_dong_tra_cong_no(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO dmssx_khachhang VALUES ('BNI00003','Bệnh viện đa khoa tỉnh Bắc Ninh',1,1,'GT')"
    )
    conn.execute(
        "INSERT INTO fact_congno_khachhang VALUES "
        "('2026-09-16','2026-09-16T10:07:00','BNI00003','Bệnh viện đa khoa tỉnh Bắc Ninh',"
        "'ETC','MB',700000000,100000000,0,0,500000000,600000000)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(
        customer_code="Bệnh viện đa khoa tỉnh Bắc Ninh",
        date_from="2026-01-01", date_to="2026-09-16",
    )

    assert result["customer_code"] == "BNI00003"
    assert result["customer_name"] == "Bệnh viện đa khoa tỉnh Bắc Ninh"
    assert result["balance_end"] == 700_000_000
    assert result["total_overdue"] == 600_000_000


def test_ma_khach_luon_kem_quy_tac_doi_chieu_ten_va_route_cau_no_theo_ten(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO dmssx_khachhang VALUES ('BGI00699','Bệnh viện Đa khoa tỉnh Bắc Giang',1,1,'GT')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(
        customer_code="BGI00699", date_from="2026-01-01", date_to="2026-09-16",
    )

    assert "Bệnh viện Đa khoa tỉnh Bắc Giang" in result["identity_check"]
    assert nl2sql._required_tool_for_question(
        "Bệnh viện Bắc Ninh còn nợ bao nhiêu"
    ) == "get_customer_detail"


def test_ma_trung_hai_danh_muc_chon_ten_theo_kenh_cong_no(tmp_path, monkeypatch):
    """BGI00699 that tren kho: OTC ghi Bac Giang, ETC/cong no ghi Bac Ninh."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO dms_khachhang VALUES "
        "('BGI00699','Bệnh viện đa khoa Tỉnh Bắc Giang',1,1,NULL,'GT')"
    )
    conn.execute(
        "INSERT INTO dmssx_khachhang VALUES "
        "('BGI00699','Bệnh viện đa khoa Bắc Ninh số 1',1,2,'GT')"
    )
    conn.execute(
        "INSERT INTO vhoadon_etc VALUES "
        "('2026-06-12','BGI00699','SP01',42000000,1,42000000,'HD1',1,'NV1','2026-06-12')"
    )
    conn.execute(
        "INSERT INTO fact_congno_khachhang VALUES "
        "('2026-09-16','2026-09-16T10:07:00','BGI00699','Bệnh viện đa khoa Bắc Ninh số 1',"
        "'ETC','MB',647788000,17388000,0,0,630400000,647788000)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.customer_detail(
        customer_code="BGI00699", date_from="2026-01-01", date_to="2026-09-16",
    )

    assert result["channel"] == "ETC"
    assert result["customer_name"] == "Bệnh viện đa khoa Bắc Ninh số 1"
    assert result["balance_end"] == 647_788_000
    assert result["catalog_identity_warning"]["OTC"] == "Bệnh viện đa khoa Tỉnh Bắc Giang"
    assert result["catalog_identity_warning"]["ETC"] == "Bệnh viện đa khoa Bắc Ninh số 1"
    assert result["catalog_identity_warning"]["selected_channel"] == "ETC"


def _kho_nhieu_thang(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH01','Khach A',1,100,NULL,'GT')")
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,'KH01','SP01',?,1,1,?,1,'NV01',?,'ASM01')", [
        ("2026-05-10", 100.0, "H5", "2026-05-10"), ("2026-05-20", 50.0, "H5b", "2026-05-20"),
        ("2026-07-03", 300.0, "H7", "2026-07-03")])
    conn.execute("INSERT INTO vhoadon_etc VALUES ('2026-07-04','KH01','SP01',40,1,1,'E7',1,'NV02','2026-07-04')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2025-10-01")


def test_khoang_nhieu_thang_tra_theo_thang_tong_khop(tmp_path, monkeypatch):
    # 26/09/2026 (may 24 23/09): "QTI00109 chi tiet doanh thu 5 thang" -> model goi tool 5 lan, moi thang mot lan.
    _kho_nhieu_thang(tmp_path, monkeypatch)
    r = rt.customer_detail(customer_code="KH01", date_from="2026-05-01", date_to="2026-07-31 23:59:59")
    assert [(t["month"], t["revenue"], t["orders"]) for t in r["theo_thang"]] == [
        ("2026-05", 150.0, 2), ("2026-06", 0.0, 0), ("2026-07", 340.0, 2)], "Thang khong mua = 0, van co dong."
    assert sum(t["revenue"] for t in r["theo_thang"]) == r["revenue"] == 490.0
    assert r["theo_thang"][2]["otc_revenue"] == 300.0 and r["theo_thang"][2]["etc_revenue"] == 40.0


def test_theo_thang_chi_kenh_duoc_phep_va_ngoai_cua_so_la_none(tmp_path, monkeypatch):
    _kho_nhieu_thang(tmp_path, monkeypatch)
    r = rt.customer_detail(customer_code="KH01", date_from="2026-05-01", date_to="2026-07-31 23:59:59",
                           scope_channel="OTC")
    assert [t["revenue"] for t in r["theo_thang"]] == [150.0, 0.0, 300.0], "Tai khoan OTC khong thay ETC."
    assert all("etc_revenue" not in t for t in r["theo_thang"])
    r = rt.customer_detail(customer_code="KH01", date_from="2025-09-01", date_to="2025-10-31 23:59:59")
    assert r["theo_thang"][0] == {"month": "2025-09", "revenue": None, "ngoai_cua_so_chi_tiet": True}
    assert r["theo_thang"][1]["revenue"] == 0.0


def test_mot_thang_khong_co_theo_thang_va_mo_ta_tool(tmp_path, monkeypatch):
    _kho_nhieu_thang(tmp_path, monkeypatch)
    r = rt.customer_detail(customer_code="KH01", date_from="2026-07-01", date_to="2026-07-31 23:59:59")
    assert "theo_thang" not in r
    mo_ta = {t["name"]: t["description"] for t in nl2sql.TEMPLATE_TOOLS}
    assert "theo_thang" in mo_ta["get_customer_detail"]
    assert "get_kpi_scorecard" in mo_ta["get_focus_product_kpi"]
