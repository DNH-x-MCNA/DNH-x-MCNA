# -*- coding: utf-8 -*-
"""Kiem chung report_templates.sync_freshness_note() va viec no da duoc noi vao
nl2sql._dynamic_context_note() (19/08/2026) - truoc do ham nay ton tai tu 20/07/2026 nhung CHUA
TUNG duoc goi o dau, phat hien lai qua ke hoach 11/08/2026 van con nguyen sau hon 1 tuan.

Cung khoa lai loi mojibake (chu Viet vo font) tim thay trong chuoi canh bao khi sua - ham chua bao
gio duoc goi nen chua ai thay dau ra that de phat hien loi nay truoc do.
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import nl2sql
import report_templates


def _make_db(path, *, otc_synced_at, etc_synced_at):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT);
        CREATE TABLE sync_meta (
            table_name TEXT PRIMARY KEY,
            last_synced_at TEXT,
            earliest_synced_date TEXT,
            latest_synced_date TEXT
        );
        """
    )
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-08-18')")
    conn.executemany(
        "INSERT INTO sync_meta VALUES (?, ?, NULL, NULL)",
        [("vhoadon_otc", otc_synced_at), ("vhoadon_etc", etc_synced_at)],
    )
    conn.commit()
    conn.close()


def test_sync_freshness_note_rong_khi_moi(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    _make_db(db_path, otc_synced_at="2026-08-19T10:50:00", etc_synced_at="2026-08-19T10:55:00")
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    import datetime as real_dt
    fixed_now = real_dt.datetime(2026, 8, 19, 11, 0, 0)

    class _FixedDateTime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(report_templates.dt, "datetime", _FixedDateTime)

    assert report_templates.sync_freshness_note(stale_minutes=60) == ""


def test_sync_freshness_note_canh_bao_khi_treo_va_chu_viet_khong_vo(tmp_path, monkeypatch):
    """Khoa lai loi mojibake da tim thay khi sua: chuoi tra ve phai la tieng Viet doc duoc, khong
    con byte hong (vd '\\x81', '\\x9d', '\\xa0' tung xuat hien truoc khi sua)."""
    db_path = tmp_path / "stale.db"
    _make_db(db_path, otc_synced_at="2026-08-19T08:00:00", etc_synced_at="2026-08-19T10:55:00")
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    import datetime as real_dt
    fixed_now = real_dt.datetime(2026, 8, 19, 11, 0, 0)

    class _FixedDateTime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(report_templates.dt, "datetime", _FixedDateTime)

    warning = report_templates.sync_freshness_note(stale_minutes=60)
    assert "vhoadon_otc" in warning
    assert "180" in warning  # 08:00 -> 11:00 = 180 phut
    assert "CẢNH BÁO ĐỒNG BỘ" in warning
    assert "TREO/LỖI" in warning
    for bad_char in (chr(0x81), chr(0x90), chr(0x9d), chr(0xa0)):
        assert bad_char not in warning


def test_dynamic_context_note_gan_canh_bao_khi_sync_treo(tmp_path, monkeypatch):
    db_path = tmp_path / "stale2.db"
    _make_db(db_path, otc_synced_at="2026-08-19T08:00:00", etc_synced_at="2026-08-19T10:55:00")
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    import datetime as real_dt
    fixed_now = real_dt.datetime(2026, 8, 19, 11, 0, 0)

    class _FixedDateTime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(report_templates.dt, "datetime", _FixedDateTime)

    note = nl2sql._dynamic_context_note("Doanh thu hôm nay?", "sess-1")
    assert "CẢNH BÁO ĐỒNG BỘ" in note


def test_dynamic_context_note_khong_gan_canh_bao_khi_sync_binh_thuong(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh2.db"
    _make_db(db_path, otc_synced_at="2026-08-19T10:50:00", etc_synced_at="2026-08-19T10:55:00")
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    import datetime as real_dt
    fixed_now = real_dt.datetime(2026, 8, 19, 11, 0, 0)

    class _FixedDateTime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(report_templates.dt, "datetime", _FixedDateTime)

    note = nl2sql._dynamic_context_note("Doanh thu hôm nay?", "sess-1")
    assert "CẢNH BÁO ĐỒNG BỘ" not in note
