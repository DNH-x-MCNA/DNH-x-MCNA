# -*- coding: utf-8 -*-
"""Khoa lai loi mojibake tim thay 19/08/2026 trong _channel_sub_buckets(): chuoi SQL LIKE
'KÃªnh%' (phai la 'Kênh%') KHONG BAO GIO khop du lieu that - ham nay LUON tra ve rong, khien
tinh nang "tach doanh thu kenh dac biet (Modern Trade...) khoi tong vung" trong revenue_by_region()
lang le khong bao gio hoat dong, du code logic goi no hoan toan dung."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def test_channel_sub_buckets_tim_dung_ban_ghi_kenh_dac_biet(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT);
        """
    )
    # Ban ghi "kenh ao" that: QLV gia, is_duplicate=1, ten bat dau bang "Kênh".
    conn.execute("INSERT INTO dim_nhanvien VALUES "
                "('MN1','Kênh MT',1,'QLV','MN','ASM01')")
    # Mot QLV that (khong phai kenh ao) - KHONG duoc lot vao ket qua.
    conn.execute("INSERT INTO dim_nhanvien VALUES "
                "('QLV01','Nguyen Van A',0,'QLV','MB','QLV01')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    buckets = rt._channel_sub_buckets()

    assert len(buckets) == 1
    assert buckets[0]["dmsid"] == "ASM01"
    assert buckets[0]["area_code"] == "MN"
