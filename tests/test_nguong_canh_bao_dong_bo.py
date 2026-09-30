# -*- coding: utf-8 -*-
"""30/09/2026 - canh bao "sync TREO" trong cau tra loi dung nguong 60 phut, trong khi sync_scheduler.ps1 dong bo
MOI 60 PHUT (kiem moi 5 phut, huy sau 90 s): luc binh thuong lan dong bo gan nhat da cach toi ~67 phut, nen
gio nao cung co vai phut bao treo gia. Tu PR #162 cau du phong in THANG canh bao nay cho nguoi dung.
Nay dung chung nguong voi dong freshness tren giao dien (CHAT_FRESHNESS_STALE_MINUTES, mac dinh 90)."""
import datetime as real_dt
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.append(str(BACKEND))
import data_freshness  # noqa: E402
import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates  # noqa: E402

BAY_GIO = real_dt.datetime(2026, 9, 30, 11, 0, 0)


@pytest.fixture
def kho(tmp_path, monkeypatch):
    monkeypatch.delenv("CHAT_FRESHNESS_STALE_MINUTES", raising=False)

    class GioCoDinh(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return BAY_GIO

    monkeypatch.setattr(report_templates.dt, "datetime", GioCoDinh)

    def dat(phut_otc, phut_etc=5):
        path = tmp_path / f"kho_{phut_otc}_{phut_etc}.db"
        conn = sqlite3.connect(path)
        conn.executescript("CREATE TABLE vhoadon_otc (doc_date TEXT);"
                           "CREATE TABLE sync_meta (table_name TEXT PRIMARY KEY, last_synced_at TEXT,"
                           " earliest_synced_date TEXT, latest_synced_date TEXT);")
        conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-09-29')")
        conn.executemany("INSERT INTO sync_meta VALUES (?, ?, NULL, NULL)", [
            ("vhoadon_otc", (BAY_GIO - real_dt.timedelta(minutes=phut_otc)).isoformat()),
            ("vhoadon_etc", (BAY_GIO - real_dt.timedelta(minutes=phut_etc)).isoformat()),
        ])
        conn.commit()
        conn.close()
        monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))

    return dat


def test_cach_67_phut_la_binh_thuong_khong_canh_bao(kho):
    kho(67)
    assert report_templates.sync_freshness_note() == ""
    assert "CẢNH BÁO ĐỒNG BỘ" not in nl2sql._dynamic_context_note("Doanh thu hôm nay?", "sess-nguong")


def test_qua_90_phut_moi_canh_bao_va_ghi_dung_chu_ky(kho):
    kho(91)
    canh_bao = report_templates.sync_freshness_note()
    assert "vhoadon_otc" in canh_bao and "91 phút" in canh_bao
    assert "định kỳ 60 phút" in canh_bao and "quá 90 phút" in canh_bao
    assert "15-30" not in canh_bao
    # Cau du phong (nl2sql._projection_response) cat phan lenh cho model tai dung chuoi nay.
    assert " PHẢI cảnh báo rõ người dùng" in canh_bao


def test_nguong_cau_hinh_dung_chung_voi_dong_freshness(kho, monkeypatch):
    monkeypatch.setenv("CHAT_FRESHNESS_STALE_MINUTES", "120")
    kho(100)
    assert report_templates.sync_freshness_note() == ""
    assert data_freshness.FreshnessCollector().stale_minutes == 120
    kho(121)
    assert "quá 120 phút" in report_templates.sync_freshness_note()


def test_cau_hinh_hong_quay_ve_90_phut(monkeypatch):
    monkeypatch.setenv("CHAT_FRESHNESS_STALE_MINUTES", "chin-muoi")
    assert data_freshness.configured_stale_minutes() == 90
    assert data_freshness.FreshnessCollector().stale_minutes == 90


def test_truyen_nguong_rieng_van_duoc_ton_trong(kho):
    kho(61)
    assert "quá 60 phút" in report_templates.sync_freshness_note(stale_minutes=60)


def _hang_so_ps1(path, ten):
    return int(re.search(rf"^\${ten}\s*=\s*(\d+)", path.read_text(encoding="utf-8"), re.M).group(1))


@pytest.mark.parametrize("ps1", ["backend/sync_scheduler.ps1", "backend/server_deploy/sync_scheduler.ps1"])
def test_nguong_lon_hon_do_tre_binh_thuong_cua_lich_dong_bo(ps1):
    """Doi lich trong sync_scheduler.ps1 ma quen nguong thi test nay hong, khong de canh bao gia quay lai."""
    path = ROOT / ps1
    chu_ky = _hang_so_ps1(path, "REGULAR_INTERVAL_MIN")
    tre_toi_da = chu_ky + _hang_so_ps1(path, "CHECK_INTERVAL_SEC") / 60 + _hang_so_ps1(path, "TIMEOUT_SEC") / 60
    assert chu_ky == data_freshness.SYNC_INTERVAL_MINUTES
    assert data_freshness.DEFAULT_STALE_MINUTES > tre_toi_da
    mau = int(re.search(r"^CHAT_FRESHNESS_STALE_MINUTES=(\d+)", (BACKEND / ".env.example").read_text(encoding="utf-8"),
                        re.M).group(1))
    assert mau > tre_toi_da
