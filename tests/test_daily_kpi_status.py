# -*- coding: utf-8 -*-
"""Khoa lai loi mojibake (chu Viet/emoji vo font do byte UTF-8 bi doc nham roi luu lai) tim thay
19/08/2026 trong report_templates.py::_daily_kpi_status() va employee_daily_kpi().

Day KHONG CHI la loi hien thi: dong so sanh "status.startswith('🔴')"/"'🟡'" trong
employee_daily_kpi() dung CHUOI EMOJI BI HONG (khac voi emoji THAT ma _daily_kpi_status() tra ve),
nen KHONG BAO GIO khop - count_red va count_yellow LUON BANG 0 trong production, moi ngay du do/
vang deu bi dem nham vao count_green. Loi chua ai phat hien vi ham nay chua tung co test rieng.
"""
import io
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, employee_code TEXT, amount9 REAL);
        CREATE TABLE vhoadon_etc (doc_date TEXT, employee_code TEXT, amount9 REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, month_sale_target REAL, save_date TEXT);
        """
    )
    # Target thang: 1.000.000d -> target/ngay = 4% = 40.000d. Do<2,5% (<25.000d), Vang 2,5-3,5%
    # (25.000-35.000d), Xanh >3,5% (>35.000d).
    conn.execute(
        "INSERT INTO fact_tonghopkhachhang VALUES ('NV01', 1000000, '2026-01-15')"
    )
    conn.execute(
        "INSERT INTO dim_nhanvien VALUES ('NV01', 'Nguyen Van A', 0, 'TDV', 'MB', 'NV01')"
    )
    # 2026-01-05 (T2): 30.000d -> 3,0% -> Vang. 2026-01-06 (T3): 50.000d -> 5,0% -> Xanh.
    # Cac ngay trong tuan khac trong thang khong co dong nao -> mac dinh 0d -> Do.
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-01-05', 'NV01', 30000)")
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-01-06', 'NV01', 50000)")
    conn.commit()
    conn.close()


def test_daily_kpi_status_tra_dung_emoji_va_chu_tieng_viet():
    """Khoa truc tiep dau ra cua ham - phai la emoji THAT (U+1F534/U+1F7E1/U+1F7E2), khong phai
    chuoi mojibake nhu truoc khi sua."""
    assert report_templates._daily_kpi_status(1.0) == "\U0001F534 Đỏ"
    assert report_templates._daily_kpi_status(3.0) == "\U0001F7E1 V\xe0ng"
    assert report_templates._daily_kpi_status(5.0) == "\U0001F7E2 Xanh"


def test_kpi_status_tra_dung_nhan_tieng_viet():
    """_kpi_status() (dung trong employee_kpi()::truong 'status', nguong 80/50 - khac han
    _daily_kpi_status() nguong 2,5/3,5) cung bi mojibake tim thay cung dot (19/08/2026)."""
    assert report_templates._kpi_status(90) == "\U0001F7E2 Tốt"
    assert report_templates._kpi_status(60) == "\U0001F7E1 Trung b\xecnh"
    assert report_templates._kpi_status(20) == "\U0001F534 Nguy hiểm"


def test_employee_daily_kpi_dem_dung_so_ngay_do_vang_xanh(tmp_path, monkeypatch):
    """19/08/2026 (thuc te): truoc khi sua, count_red/count_yellow LUON BANG 0 du co ngay do/vang
    that trong du lieu, vi dong so sanh trong employee_daily_kpi() dung chuoi emoji hong. Test nay
    FAIL tren code cu, PASS tren code da sua."""
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.employee_daily_kpi("NV01", "2026-01")

    assert result["count_yellow"] == 1
    assert result["count_green"] == 1
    assert result["count_red"] >= 1
    total_weekdays = result["count_red"] + result["count_yellow"] + result["count_green"]
    assert total_weekdays == len(result["days"])

    by_date = {d["date"]: d for d in result["days"]}
    assert by_date["2026-01-05"]["status"] == "\U0001F7E1 V\xe0ng"
    assert by_date["2026-01-06"]["status"] == "\U0001F7E2 Xanh"


def test_bulk_daily_kpi_giu_du_moi_nhan_vien_nhung_khong_phinh_payload(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO dim_nhanvien VALUES ('NV02','Nguyen Van B',0,'TDV','MB','NV02')")
    con.execute("INSERT INTO fact_tonghopkhachhang VALUES ('NV02',1000000,'2026-01-15')")
    con.execute("INSERT INTO vhoadon_otc VALUES ('2026-01-07','NV02',60000)")
    con.commit(); con.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = report_templates.employee_daily_kpi("NV01,NV02", "2026-01")

    assert result["requested_count"] == result["count"] == 2
    assert {r["employee_name"] for r in result["employees"]} == {"Nguyen Van A", "Nguyen Van B"}
    assert all("days" not in r for r in result["employees"])
    assert result["team_daily_summary"]["count_yellow"] >= 1
    assert len(result["team_daily_summary"]["top_revenue_dates"]) == 5
    assert result["errors"] == []
