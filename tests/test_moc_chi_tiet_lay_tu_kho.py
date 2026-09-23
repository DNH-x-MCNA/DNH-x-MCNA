# -*- coding: utf-8 -*-
"""23/09/2026 - UAT dnh_etc 15/09 14:53 "thuc hien, ke hoach doanh so cac thang trong nam".

Nguoi cham ghi "Ke hoach dung, thuc hien sai". Truy nguyen: _detail_cutoff() tra ve HANG SO
2024-01-01 (khop sync_warehouse.DETAIL_HISTORY_START), nhung kho tren dia duoc dung theo chinh
sach CU (chi giu 12 thang chi tiet) nen hoa don chi tiet that su chi bat dau tu 2025-09.

Hai nguon vi the ho mat dung khoang giua hai moc:
  - revenue_by_channel chi UNION monthly_customer_summary khi date_from < cutoff (= 2024-01-01),
    nen thang 2024-01 -> 2025-08 KHONG duoc doc tu bang nen;
  - ma bang chi tiet lai rong o khoang do.
Ket qua: 20 thang lien tiep tra ve DUNG 0 dong cho CA HAI kenh, trong khi monthly_customer_summary
co du so. Ke hoach lay tu fact_kehoachtongetc nen van dung - khop y nguyen nhan xet cua nguoi cham.

Hang so va du lieu chi khop nhau sau khi da --full lai toan bo hoa don. Cac test duoi khoa lai:
moc cat phai doc TU CHINH KHO, de do lech giua chinh sach sync va du lieu tren dia tu lanh.
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
        return cls(2026, 3, 31)


def _make_db(path):
    """Kho mo phong dung tinh huong may 24: bang nen den het 2025-08, chi tiet tu 2025-09."""
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
    # Bang nen: 2025-07 va 2025-08 - nam SAU hang so 2024-01-01 nhung TRUOC moc chi tiet that.
    conn.executemany(
        "INSERT INTO monthly_customer_summary VALUES (?,?,?,?,?,?)",
        [
            ("2025-07", "OTC", "KH01", "NV01", 7_000_000, 7),
            ("2025-07", "ETC", "KH02", "NV02", 3_000_000, 3),
            ("2025-08", "OTC", "KH01", "NV01", 8_000_000, 8),
            ("2025-08", "ETC", "KH02", "NV02", 4_000_000, 4),
        ],
    )
    # Chi tiet: bat dau 2025-09. Khong co dong nao truoc moc nay.
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2025-09-05", "KH01", "SP01", 9_000_000, 9, 1_000_000, "HD09O", 1, "NV01", "2025-09-05", None),
            ("2026-03-05", "KH01", "SP01", 5_000_000, 5, 1_000_000, "HD03O", 1, "NV01", "2026-03-05", None),
        ],
    )
    conn.executemany(
        "INSERT INTO vhoadon_etc VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("2025-09-05", "KH02", "SP01", 2_000_000, 2, 1_000_000, "HD09E", 1, "NV02", "2025-09-05"),
            ("2026-03-05", "KH02", "SP01", 1_000_000, 1, 1_000_000, "HD03E", 1, "NV02", "2026-03-05"),
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


def test_moc_cat_lay_tu_kho_chu_khong_phai_hang_so(tmp_path, monkeypatch):
    """Kho nay chi co chi tiet tu 09/2025; moc cat phai noi dung the, khong tra 2024-01-01."""
    _kho(tmp_path, monkeypatch)

    assert rt._detail_cutoff() == "2025-09-01"


def test_thang_giua_hang_so_va_moc_that_khong_duoc_tra_ve_0(tmp_path, monkeypatch):
    """LOI GOC UAT 15/09: 2025-07 nam sau hang so 2024-01-01 nhung truoc moc chi tiet that 2025-09.

    Code cu: khong UNION bang nen (vi date_from >= cutoff) + bang chi tiet rong = 0 dong ca hai kenh.
    """
    _kho(tmp_path, monkeypatch)

    r = rt.revenue_by_channel(date_from="2025-07-01", date_to="2025-07-31")

    assert r["otc"]["revenue"] == 7_000_000, "thang da nen bi tra ve 0 - dung loi UAT 15/09"
    assert r["etc"]["revenue"] == 3_000_000, "thang da nen bi tra ve 0 - dung loi UAT 15/09"
    assert r["total"]["revenue"] == 10_000_000
    assert r["total"]["invoices"] == 10


def test_chuoi_thang_khong_con_thang_0_dong_gia(tmp_path, monkeypatch):
    """Cau hoi that la "thuc hien, ke hoach doanh so CAC THANG trong nam" -> di qua chuoi theo thang.

    Chuoi phai lien tuc: khong duoc co thang 0 dong xen giua hai thang co so that, vi model se doc
    thanh "thang do ban duoc 0 dong" roi tinh ca vao MoM/YoY.
    """
    _kho(tmp_path, monkeypatch)

    r = rt.revenue_monthly_series(month_to="2025-09", months_back=3, include_plans=False,
                                  include_region_breakdown=False, include_special_channels=False)

    theo_thang = {m["month"]: m for m in r["months"]}
    assert theo_thang["2025-07"]["revenue"] == 10_000_000
    assert theo_thang["2025-08"]["revenue"] == 12_000_000
    assert theo_thang["2025-09"]["revenue"] == 11_000_000
    assert not any(m.get("can_kiem_chung") for m in r["months"]), (
        "khong thang nao con bi danh dau thieu du lieu sau khi doc dung bang nen")


def test_chuoi_thang_kenh_etc_lay_dung_so_bang_nen(tmp_path, monkeypatch):
    """Dung vai tai khoan da bao loi: dnh_etc chi duoc xem kenh ETC."""
    _kho(tmp_path, monkeypatch)

    r = rt.revenue_monthly_series(month_to="2025-09", months_back=3, scope_channel="ETC",
                                  include_plans=False, include_region_breakdown=False,
                                  include_special_channels=False)

    assert [m["etc_revenue"] for m in r["months"]] == [3_000_000, 4_000_000, 2_000_000]
    assert all(m["otc_revenue"] == 0.0 for m in r["months"]), "scope ETC khong duoc lo doanh thu OTC"


def test_thang_giao_giua_hai_nguon_khong_bi_cong_doi(tmp_path, monkeypatch):
    """Thang cua moc cat phai chi lay tu MOT nguon.

    Neu cat theo NGAY (min(date_to, cutoff) roi lay [:7]) thi thang chua moc se roi vao CA hai
    khoang truy van - cong doi dung mot thang, rat kho thay vi cac thang khac van dung.
    """
    _kho(tmp_path, monkeypatch)
    conn = sqlite3.connect(local_warehouse.DB_PATH)
    # Co tinh dat them dong da nen o dung thang giao (2025-09) de bay cong doi.
    conn.execute("INSERT INTO monthly_customer_summary VALUES (?,?,?,?,?,?)",
                 ("2025-09", "OTC", "KH01", "NV01", 999_000_000, 999))
    conn.commit()
    conn.close()

    r = rt.revenue_by_channel(date_from="2025-07-01", date_to="2025-09-30")

    # 7tr + 8tr (nen) + 9tr (chi tiet). Dong 999tr o thang giao KHONG duoc cong them.
    assert r["otc"]["revenue"] == 24_000_000
    assert r["etc"]["revenue"] == 9_000_000


def test_kho_rong_van_giu_hang_so_thay_vi_no(tmp_path, monkeypatch):
    """Kho chua co hoa don nao: khong duoc no, cung khong duoc doan moc."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, amount9 REAL, stt TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, amount9 REAL, stt TEXT);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    assert rt._detail_cutoff() == "2024-01-01"


def test_cache_moc_cat_khong_lan_giua_hai_kho(tmp_path, monkeypatch):
    """Cache 10 phut phai khoa theo duong dan kho.

    Cache mot o nho duy nhat se tra moc cua kho TRUOC do cho kho HIEN TAI: sai am tham, va lam
    ket qua phu thuoc thu tu goi - dung kieu loi ma bo test rat de bo qua.
    """
    _kho(tmp_path, monkeypatch)
    assert rt._detail_cutoff() == "2025-09-01"

    kho_khac = tmp_path / "kho_khac.db"
    conn = sqlite3.connect(kho_khac)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, amount9 REAL, stt TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, amount9 REAL, stt TEXT);
        """
    )
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-02-10', 1000, 'HD')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(kho_khac))

    assert rt._detail_cutoff() == "2026-02-01"
