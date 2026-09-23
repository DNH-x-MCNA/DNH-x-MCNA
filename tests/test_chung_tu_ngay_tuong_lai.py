# -*- coding: utf-8 -*-
"""23/09/2026 - hoa don ETC tren may 24 co chung tu de NGAY TUONG LAI.

Do tren may 24 ngay 23/09: vhoadon_etc co 4 dong de ngay 28/09 (1 khach, 18 trieu). Truoc do ngay
14/08 da gap dung kieu nay - tai khoan `dnh` hoi "du lieu hoa don moi nhat den ngay nao" thi nhan
duoc "ETC co chung tu ngay 28/08/2026". CUNG NGAY 28, cung kenh ETC, cach nhau hon mot thang: day
la chung tu de ngay truoc theo lich chu khong phai loi sync ngau nhien. DNH chua tra loi day la ghi
truoc theo ke hoach hay nhap sai ngay.

Hau qua trong code: revenue_monthly_series lay _month_bounds(ym) = CA THANG, nen thang dang chay
cong luon phan tuong lai; trong khi cau hoi "doanh so thang nay" di qua resolve_relative_date lai
cat tai hom nay. CUNG MOT THANG ra HAI con so tuy cach hoi - dung kieu lech ma
test_cat_danh_sach_chuoi_thang da ghi nhan o cho khac.

Muc 23/09 chi 18 trieu tren 24,6 ty (0,07%) nen khong ai phat hien bang mat. Cac test duoi khoa lai
truoc khi mot lo chung tu lon hon roi vao.
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
        return cls(2026, 9, 23)


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
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        """
    )
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-08-10", "KH01", "SP01", 5_000_000, 5, 1_000_000, "HD08O", 1, "NV01", "2026-08-10", None),
            ("2026-09-10", "KH01", "SP01", 3_000_000, 3, 1_000_000, "HD09O", 1, "NV01", "2026-09-10", None),
        ],
    )
    conn.executemany(
        "INSERT INTO vhoadon_etc VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-08-15", "KH02", "SP01", 4_000_000, 4, 1_000_000, "HD08E", 1, "NV02", "2026-08-15"),
            ("2026-09-20", "KH02", "SP01", 2_000_000, 2, 1_000_000, "HD09E", 1, "NV02", "2026-09-20"),
            # Chung tu de ngay 28/09 trong khi "hom nay" la 23/09 - dung mau tren may 24.
            ("2026-09-28", "KH02", "SP01", 18_000, 1, 18_000, "HD09TL", 1, "NV02", "2026-09-20"),
        ],
    )
    conn.commit()
    conn.close()


def _kho(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    return str(db_path)


def _chuoi(**kwargs):
    tham_so = dict(month_to="2026-09", months_back=2, include_yoy=False, include_plans=False,
                   include_region_breakdown=False, include_special_channels=False)
    tham_so.update(kwargs)
    return rt.revenue_monthly_series(**tham_so)


def test_thang_dang_chay_khong_cong_chung_tu_ngay_tuong_lai(tmp_path, monkeypatch):
    """Loi goc: 18.000 de ngay 28/09 bi cong vao doanh thu thang 9 du hom nay moi 23/09."""
    _kho(tmp_path, monkeypatch)

    thang_9 = {m["month"]: m for m in _chuoi()["months"]}["2026-09"]

    assert thang_9["etc_revenue"] == 2_000_000, "chung tu ngay 28/09 bi cong vao thang dang chay"
    assert thang_9["revenue"] == 5_000_000


def test_thang_dang_chay_noi_ro_tinh_den_ngay_nao(tmp_path, monkeypatch):
    """Thang chua tron ma khong noi ro thi "%dat ke hoach" bi doc thanh ket qua ca thang."""
    _kho(tmp_path, monkeypatch)

    thang_9 = {m["month"]: m for m in _chuoi()["months"]}["2026-09"]

    assert thang_9["tinh_den_ngay"] == "2026-09-23"
    assert "ke hoach la CA THANG" in thang_9["thang_chua_tron"]


def test_chung_tu_tuong_lai_bi_loai_nhung_van_duoc_neu_ra(tmp_path, monkeypatch):
    """Loai khoi tong la dung, nhung giau di thi cung sai: DNH chua chot day la ghi truoc theo ke
    hoach hay nhap sai ngay, nen phai neu ra chu khong duoc am tham bo."""
    _kho(tmp_path, monkeypatch)

    thang_9 = {m["month"]: m for m in _chuoi()["months"]}["2026-09"]
    tl = thang_9["chung_tu_ngay_tuong_lai"]

    assert tl["tu_ngay"] == "2026-09-24"
    assert tl["den_ngay"] == "2026-09-30"
    assert tl["revenue"] == 18_000
    assert tl["invoices"] == 1
    assert "KHONG duoc cong vao" in tl["ghi_chu"]


def test_thang_da_tron_khong_bi_cat_va_khong_gan_co_thua(tmp_path, monkeypatch):
    """Canh bao thua cung la nhieu: thang 8 da tron thi khong duoc dinh gi ca."""
    _kho(tmp_path, monkeypatch)

    thang_8 = {m["month"]: m for m in _chuoi()["months"]}["2026-08"]

    assert thang_8["revenue"] == 9_000_000
    assert "tinh_den_ngay" not in thang_8
    assert "thang_chua_tron" not in thang_8
    assert "chung_tu_ngay_tuong_lai" not in thang_8


def test_hai_cach_hoi_cung_mot_thang_phai_ra_cung_mot_so(tmp_path, monkeypatch):
    """Day la loi that su: "doanh so thang nay" (cat tai hom nay qua resolve_relative_date) va
    "doanh so cac thang trong nam" (chuoi theo thang) phai ra CUNG mot con so cho thang 9.

    Doi chieu nay chinh la ly do revenue_monthly_series goi lai revenue_by_channel thay vi tu viet
    SQL GROUP BY thang - xem docstring cua no.
    """
    _kho(tmp_path, monkeypatch)

    hoi_thang_nay = rt.revenue_by_channel("2026-09-01", "2026-09-23")
    thang_9 = {m["month"]: m for m in _chuoi()["months"]}["2026-09"]

    assert thang_9["revenue"] == hoi_thang_nay["total"]["revenue"]
    assert thang_9["etc_revenue"] == hoi_thang_nay["etc"]["revenue"]
    assert thang_9["invoices"] == hoi_thang_nay["total"]["invoices"]


def test_scope_kenh_etc_van_duoc_ap_cho_phan_chung_tu_tuong_lai(tmp_path, monkeypatch):
    """Phan neu ra cung phai di qua revenue_by_channel de an theo scope, khong duoc query tho:
    tai khoan gioi han kenh khong duoc nhin thay so kenh khac o bat ky truong nao."""
    _kho(tmp_path, monkeypatch)

    thang_9 = {m["month"]: m for m in _chuoi(scope_channel="ETC")["months"]}["2026-09"]

    assert thang_9["otc_revenue"] == 0.0
    assert thang_9["etc_revenue"] == 2_000_000
    assert thang_9["chung_tu_ngay_tuong_lai"]["revenue"] == 18_000
