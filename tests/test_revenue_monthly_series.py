# -*- coding: utf-8 -*-
"""24/08/2026: revenue_monthly_series() - tool CHUOI THEO THANG.

Vi sao co tool nay: truoc do MOI tool doanh thu chi tra ve 1 con so TONG cho ca khoang ngay, khong
phai chuoi tung thang. Muon 12 thang phai goi 12 lan -> dung tran MAX_UNIQUE_TOOL_CALLS=12, an tron
han muc; 24 thang thi bat kha thi. Xem docs/doi_chieu_138_cau_voi_tool_thuc_te.md (nut that so 1).
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
        return cls(2026, 8, 19)


def _make_db(path):
    """Kho co du lieu tu 2025-07 (phan da nen) den 2026-07 (chi tiet).

    _detail_cutoff() voi today=2026-08-19 ra 2025-08-01, nen 2025-07 PHAI nam o
    monthly_customer_summary - dung nhu production (vhoadon_* chi giu 12 thang gan nhat).
    """
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
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, position_code TEXT,
            area_code TEXT, dmsid TEXT, is_duplicate INTEGER);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, manager_code TEXT,
            save_date TEXT, emp_dms_code TEXT);
        """
    )
    conn.execute("INSERT INTO dim_nhanvien VALUES ('NV01','Nhan vien 1','TDV','MB','NV01',0)")
    conn.execute("INSERT INTO dim_nhanvien VALUES ('Q1','Quan ly 1','QLV','MB','Q1',0)")
    conn.execute("INSERT INTO fact_tonghopkhachhang VALUES ('NV01','Q1','2026-07-31','NV01')")
    # Chi tiet: 3 thang lien tiep, doanh thu tang dan de MoM co dau ro rang.
    for day, amount, stt in (("2026-05-10", 1_000_000, "HD5"),
                              ("2026-06-10", 2_000_000, "HD6"),
                              ("2026-07-10", 3_000_000, "HD7")):
        conn.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (day, "KH01", "SP01", amount, 10, 100_000, stt, 1, "NV01", day, "ASM01"))
    conn.execute("INSERT INTO vhoadon_etc VALUES (?,?,?,?,?,?,?,?,?,?)",
                 ("2026-07-12", "KH02", "SP01", 500_000, 5, 100_000, "HD7E", 1, "NV02", "2026-07-12"))
    # Phan da nen: 2025-07 lam moc YoY cho 2026-07.
    conn.execute("INSERT INTO monthly_customer_summary VALUES (?,?,?,?,?,?)",
                 ("2025-07", "OTC", "KH01", "NV01", 1_750_000, 3))
    conn.commit()
    conn.close()


def _setup(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)


def test_tra_ve_chuoi_tung_thang_va_tinh_dung_mom(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(month_to="2026-07", months_back=3, include_yoy=False)

    assert [m["month"] for m in r["months"]] == ["2026-05", "2026-06", "2026-07"]
    assert r["months"][0]["revenue"] == 1_000_000
    assert r["months"][1]["revenue"] == 2_000_000
    assert r["months"][2]["revenue"] == 3_500_000  # 3tr OTC + 0,5tr ETC

    # MoM cua thang thu 2: 2tr - 1tr = +1tr (+100%)
    assert r["months"][1]["mom_delta"] == 1_000_000
    assert r["months"][1]["mom_pct"] == 100.0


def test_so_lieu_tung_thang_KHOP_TUYET_DOI_voi_revenue_by_channel(tmp_path, monkeypatch):
    """Rang buoc quan trong nhat: nguoi dung hoi 'doanh thu thang 7' va hoi 'chuoi 12 thang' PHAI
    ra CUNG mot con so cho thang 7. Day la ly do tool goi lai chinh revenue_by_channel() thay vi
    tu viet SQL GROUP BY thang moi (se lech vi bo qua logic ghep 2 nguon chi tiet/da nen)."""
    _setup(tmp_path, monkeypatch)
    series = rt.revenue_monthly_series(month_to="2026-07", months_back=1, include_yoy=False)
    single = rt.revenue_by_channel("2026-07-01", "2026-07-31")

    thang7 = series["months"][0]
    assert thang7["revenue"] == single["total"]["revenue"]
    assert thang7["otc_revenue"] == single["otc"]["revenue"]
    assert thang7["etc_revenue"] == single["etc"]["revenue"]
    assert thang7["invoices"] == single["total"]["invoices"]


def test_yoy_tinh_duoc_tu_thang_cung_ky_nam_truoc_o_bang_da_nen(tmp_path, monkeypatch):
    """include_yoy tu dong lay them 12 thang phia truoc (khong hien ra) - 2025-07 nam o
    monthly_customer_summary chu khong phai bang chi tiet, van phai tinh duoc."""
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(month_to="2026-07", months_back=1, include_yoy=True)

    thang7 = r["months"][0]
    assert r["so_thang"] == 1, "chi duoc TRA VE thang duoc hoi, 12 thang lay them chi de tinh YoY"
    assert thang7["yoy_delta"] == 3_500_000 - 1_750_000
    assert thang7["yoy_pct"] == 100.0


def test_yoy_cap_doi_ky_cu_ghi_ro_dung_thanh_phan_doi_hien_tai(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(
        month_to="2026-07", months_back=1, include_yoy=True,
        scope_employee_code="Q1",
    )

    basis = r["team_membership_basis"]
    assert basis["exact_history_from"] == "2026-07-31"
    assert basis["older_periods_use"] == "CURRENT_TEAM_MEMBERSHIP"
    assert "thanh phan doi tai ky lich su co the khac" in basis["warning"]
    # Loc pham vi doi Q1 = chi NV01. Hoa don ETC 500k thang 7 la cua NV02 (NGOAI doi) nen PHAI bi
    # loai: ky nay 3,0tr (khong phai 3,5tr nhu test khong loc pham vi), ky truoc 1,75tr cua NV01
    # trong bang da nen -> (3,0-1,75)/1,75 = 71,43%. Neu ra 100% tuc la doanh thu nguoi NGOAI doi
    # dang bi tinh vao doi.
    thang = r["months"][0]
    assert thang["revenue"] == 3_000_000, "doanh thu ETC cua NV02 (ngoai doi) khong duoc tinh vao"
    assert thang["yoy_delta"] == 3_000_000 - 1_750_000
    assert round(thang["yoy_pct"], 2) == 71.43


def test_thang_ngoai_pham_vi_du_lieu_tra_None_KHONG_PHAI_0(tmp_path, monkeypatch):
    """Bay quan trong nhat cua tool nay. revenue_by_channel() tra 0 cho moi khoang khong co du lieu
    - neu chuoi thang cu the ma hien 0, chatbot se NOI THANH CAU 'thang 3/2024 doanh thu 0 dong'
    nghe nhu su that, trong khi thuc te chi la chua dong bo. Xac nhan thuc te 24/08/2026 tren may
    dev: kho chi co thang 7/2026, goi revenue_by_channel('2024-03-01','2024-03-31') tra ve dung 0
    chu khong bao loi."""
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(month_to="2026-07", months_back=24, include_yoy=False)

    ngoai_pham_vi = [m for m in r["months"] if m.get("khong_co_du_lieu")]
    assert ngoai_pham_vi, "phai danh dau cac thang truoc 2025-07"
    for m in ngoai_pham_vi:
        assert m["revenue"] is None, "TUYET DOI khong duoc tra 0 cho thang khong co du lieu"
        assert m["month"] < "2025-07"

    assert "canh_bao" in r
    assert "KHONG CO du lieu" in r["canh_bao"]
    assert r["pham_vi_du_lieu_co_that"] == {"tu_thang": "2025-07", "den_thang": "2026-07"}


def test_thang_trong_pham_vi_nhung_khong_co_hoa_don_bi_danh_dau_can_kiem_chung(tmp_path, monkeypatch):
    """2026-01 nam TRONG khoang [2025-07, 2026-07] nhung khong co hoa don nao - pham vi tong the
    khong bat duoc, phai co canh bao mem rieng (co the la lo hong dong bo)."""
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(month_to="2026-07", months_back=12, include_yoy=False)

    thang_rong = [m for m in r["months"] if m.get("can_kiem_chung")]
    assert thang_rong, "thang trong pham vi ma 0 hoa don phai duoc danh dau"
    for m in thang_rong:
        assert m["revenue"] == 0
        assert not m.get("khong_co_du_lieu"), "khac hẳn thang NGOAI pham vi"


def test_gioi_han_24_thang_va_mac_dinh_12(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert rt.revenue_monthly_series(month_to="2026-07", months_back=999, include_yoy=False)["so_thang"] == 24
    assert rt.revenue_monthly_series(month_to="2026-07", months_back=0, include_yoy=False)["so_thang"] == 1
    assert rt.revenue_monthly_series(month_to="2026-07", include_yoy=False)["so_thang"] == 12


def test_scope_channel_chi_tra_kenh_duoc_phep(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(month_to="2026-07", months_back=1, include_yoy=False,
                                   scope_channel="OTC")
    thang7 = r["months"][0]
    assert thang7["otc_revenue"] == 3_000_000
    assert thang7["etc_revenue"] == 0.0, "tai khoan gioi han OTC khong duoc thay so ETC"
    assert thang7["revenue"] == 3_000_000
    assert "channel_scope" in r


def test_mac_dinh_lay_thang_moi_nhat_co_du_lieu(tmp_path, monkeypatch):
    """Khong truyen month_to -> phai lay thang co du lieu moi nhat (2026-07), KHONG lay thang he
    thong (2026-08) vi thang do chua co du lieu nao."""
    _setup(tmp_path, monkeypatch)
    r = rt.revenue_monthly_series(months_back=1, include_yoy=False)
    assert r["month_to"] == "2026-07"
    assert r["months"][0]["revenue"] == 3_500_000
