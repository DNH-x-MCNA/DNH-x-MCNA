# -*- coding: utf-8 -*-
"""26/08/2026: hai tool chuoi-theo-thang cat danh sach bang `rows[-limit:]` - cat tu DUOI mang.

Boi canh phat hien: sau khi do dinh tuyen tool dat 25/25, chuyen sang kiem DO DUNG CUA SO. Ra soat
cach cat danh sach trong report_templates.py thay 11 cho dung `[:limit]` sau khi sap theo do quan
trong, rieng 2 cho dung `[-limit:]` - va ca 2 deu nam trong 11 tool moi:
  - geography_monthly_performance (dong ~2100)
  - workforce_productivity (dong ~2192)

Mang o ca 2 cho deu duoc sap theo (thang TANG DAN, thu hang TOT DAN truoc). Lay `[-limit:]` tuc la:
  1. giu cac thang CUOI, vut cac thang DAU - dung phan can nhat de nhin xu huong;
  2. trong thang bi cat do dang thi giu don vi TE NHAT, vut don vi TOT NHAT.

Quy mo that: 63 tinh x 6 thang = 378 dong > limit mac dinh 100. Cau S12 trong bo cau hoi dieu hanh
("Xep hang cac tinh theo doanh thu tung thang, tinh nao giam lien tiep nhieu thang?") roi dung vao
day - dinh tuyen tool DUNG nhung so lieu nhan ve da bi cat 3/4. Voi workforce_productivity
group_by='employee': 281 nhan vien x 6 thang = 1.686 dong > 200.

Cac test duoi day PHAI TRUOT tren code cu (rows[-limit:]) va DAT tren code moi (_giu_top_don_vi).
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
        return cls(2026, 4, 20)


# 6 tinh, doanh thu giam dan theo ten: T1 lon nhat -> T6 be nhat. Du de limit=2 cat that su.
_TINH = [("T%d" % i, 1000 - i * 100, "MB" if i <= 3 else "MN") for i in range(1, 7)]
_THANG = ["2026-01", "2026-02", "2026-03", "2026-04"]


def _make_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT,
          amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
          employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT,
          amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT, created_at TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
          employee_code TEXT, revenue REAL, invoice_count INTEGER);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER,
          emp_code TEXT, kenh_bh TEXT);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER, id_code INTEGER, kenh_bh TEXT);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
          position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
          is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT,
          position_code TEXT, area_code TEXT, manager_code TEXT, save_date TEXT,
          month_sale_amount REAL, month_sale_target REAL, month_sale_percent REAL);
        """
    )
    con.executemany("INSERT INTO dim_tinhthanhpho VALUES (?,?,?)",
                    [(i, ten, mien) for i, (ten, _, mien) in enumerate(_TINH, start=1)])
    con.executemany("INSERT INTO dms_khachhang VALUES (?,?,?,?,?,?)",
                    [("C%d" % i, "Khach %d" % i, i, i, "D%d" % i, "OTC")
                     for i in range(1, len(_TINH) + 1)])
    con.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [("D%d" % i, "TDV %d" % i, 0, "TDV", _TINH[i - 1][2], "D%d" % i,
                      "2025-01-01", None, 0, None) for i in range(1, len(_TINH) + 1)])

    # Moi tinh mot khach, ban deu moi thang - doanh thu khong doi theo thang de test tap trung vao
    # chuyen CAT, khong lan voi chuyen tinh MoM.
    for i, (ten, doanh_thu, _) in enumerate(_TINH, start=1):
        for thang in _THANG:
            con.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        ("%s-10" % thang, "C%d" % i, "A", doanh_thu, 1, doanh_thu,
                         "O%s%d" % (thang.replace("-", ""), i), i, "D%d" % i, "%s-10" % thang, "OTC"))

    # 6 nhan vien x 4 thang cho workforce_productivity, doanh so giam dan theo ma.
    for i in range(1, 7):
        for thang in _THANG:
            con.execute("INSERT INTO fact_thongketinhluong VALUES (?,?,?,?,?,?,?,?,?)",
                        ("D%d" % i, "TDV %d" % i, "TDV", _TINH[i - 1][2], "Q%d" % i,
                         "%s-28" % thang, 1000 - i * 100, 1000, 100 - i * 10))
    con.commit(); con.close()


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    _make_db(path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    return path


# ---------------------------------------------------------------------------------------
# geography_monthly_performance
# ---------------------------------------------------------------------------------------

def test_cat_danh_sach_dia_ban_KHONG_duoc_lam_mat_cac_thang_dau(tmp_path, monkeypatch):
    """Loi nang nhat: cat tu duoi mang lam bay hoi cac thang dau, trong khi cau hoi dien hinh cua
    tool nay la "tinh nao giam LIEN TIEP nhieu thang" - khong con chuoi thi khong tra loi duoc."""
    _setup(tmp_path, monkeypatch)
    r = rt.geography_monthly_performance(month_to="2026-04", months_back=4, dimension="city", limit=2)
    cac_thang = {row["month"] for row in r["rows"]}
    assert cac_thang == set(_THANG), (
        "Phai giu DU 4 thang cho cac tinh duoc chon. Code cu tra ve rows[-2:] nen chi con 1 thang: %s"
        % sorted(cac_thang))


def test_cat_danh_sach_dia_ban_phai_giu_tinh_LON_NHAT_chu_khong_phai_be_nhat(tmp_path, monkeypatch):
    """Model goi limit=2 la y muon "2 tinh lon nhat". Code cu tra ve dung 2 tinh BE NHAT - sai nguoc
    han y dinh, va sai mot cach khong the phat hien tu cau tra loi."""
    _setup(tmp_path, monkeypatch)
    r = rt.geography_monthly_performance(month_to="2026-04", months_back=4, dimension="city", limit=2)
    giu = {row["unit"] for row in r["rows"]}
    assert giu == {"T1", "T2"}, "Phai giu 2 tinh doanh thu cao nhat, nhan duoc: %s" % sorted(giu)
    assert "T6" not in giu


def test_bao_ro_so_dia_ban_bi_cat(tmp_path, monkeypatch):
    """Tha noi khong biet con hon giau: model phai biet co bao nhieu dia ban khong duoc hien de con
    noi lai cho nguoi dung, thay vi tuong minh dang nhin toan canh."""
    _setup(tmp_path, monkeypatch)
    r = rt.geography_monthly_performance(month_to="2026-04", months_back=4, dimension="city", limit=2)
    assert r["so_dia_ban_khong_hien"] == 4

    day_du = rt.geography_monthly_performance(month_to="2026-04", months_back=4, dimension="city",
                                              limit=100)
    assert day_du["so_dia_ban_khong_hien"] == 0
    assert len(day_du["rows"]) == len(_TINH) * len(_THANG)


def test_thu_hang_va_ty_trong_van_tinh_tren_toan_bo_dia_ban(tmp_path, monkeypatch):
    """Cat bot dong hien ra KHONG duoc lam thu hang/ty trong bi tinh lai trong nhom con - neu khong,
    tinh thu 2 se hien thanh "chiem 45% ca nuoc" thay vi ty trong that."""
    _setup(tmp_path, monkeypatch)
    r = rt.geography_monthly_performance(month_to="2026-04", months_back=4, dimension="city", limit=2)
    thang_4 = [row for row in r["rows"] if row["month"] == "2026-04"]
    tong_that = sum(dt for _, dt, _ in _TINH)
    for row in thang_4:
        doanh_thu = next(dt for ten, dt, _ in _TINH if ten == row["unit"])
        assert abs(row["share_pct"] - doanh_thu / tong_that * 100) < 0.01
    assert {row["rank"] for row in thang_4} == {1, 2}


# ---------------------------------------------------------------------------------------
# workforce_productivity
# ---------------------------------------------------------------------------------------

def test_cat_danh_sach_nhan_su_KHONG_duoc_lam_mat_cac_thang_dau(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.workforce_productivity(month_to="2026-04", months_back=4, group_by="employee", limit=2)
    cac_thang = {row["month"] for row in r["rows"]}
    assert cac_thang == set(_THANG), (
        "decline_streak_months vo nghia neu khong con du chuoi thang. Nhan duoc: %s" % sorted(cac_thang))


def test_cat_danh_sach_nhan_su_phai_giu_nguoi_DOANH_SO_CAO_NHAT(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = rt.workforce_productivity(month_to="2026-04", months_back=4, group_by="employee", limit=2)
    giu = {row["group_code"] for row in r["rows"]}
    assert giu == {"D1", "D2"}, "Phai giu 2 nguoi doanh so cao nhat, nhan duoc: %s" % sorted(giu)
    assert r["so_nhom_khong_hien"] == 4


def test_khong_cat_gi_khi_so_don_vi_it_hon_limit(tmp_path, monkeypatch):
    """group_by mac dinh la 'manager' (28 QLV x 6 thang = 168 dong < 200) nen truoc gio KHONG lo ra
    loi - day chinh la ly do no song sot lau: duong di mac dinh vo tinh an toan, chi cac cau hoi hoi
    sau (theo tinh, theo tung nhan vien) moi dinh."""
    _setup(tmp_path, monkeypatch)
    r = rt.workforce_productivity(month_to="2026-04", months_back=4, group_by="area", limit=200)
    assert r["so_nhom_khong_hien"] == 0
    assert {row["group_code"] for row in r["rows"]} == {"MB", "MN"}
    assert {row["month"] for row in r["rows"]} == set(_THANG)


def test_tong_theo_mien_bang_tong_toan_bo(tmp_path, monkeypatch):
    """Bat loi cong lan tang TDV va tang QLV (da dinh 3 lan trong du an): tong doanh so nhom theo
    mien phai bang dung tong toan bo, khong duoc gap doi."""
    _setup(tmp_path, monkeypatch)
    theo_mien = rt.workforce_productivity(month_to="2026-04", months_back=4, group_by="area")
    toan_bo = rt.workforce_productivity(month_to="2026-04", months_back=4, group_by="total")
    for thang in _THANG:
        a = sum(r["actual"] for r in theo_mien["rows"] if r["month"] == thang)
        b = sum(r["actual"] for r in toan_bo["rows"] if r["month"] == thang)
        assert abs(a - b) < 0.01, "Thang %s: theo mien %s != toan bo %s" % (thang, a, b)


# ---------------------------------------------------------------------------------------
# Canh bao khi khoang hoi vuot ra ngoai cua so hoa don chi tiet
# ---------------------------------------------------------------------------------------

def test_hoi_thang_ngoai_cua_so_chi_tiet_phai_canh_bao_ro(tmp_path, monkeypatch):
    """geography_monthly_performance CHI doc vhoadon_otc/etc, khong cong monthly_customer_summary
    (bang nen khong co khoa tinh). Nen thang nam truoc moc cat se ra 0 - trong khi
    get_revenue_monthly_series tra ve so that cho chinh thang do. Cung mot thang, hai con so.

    Chua sua duoc phan so lieu (phai co DNH quyet chuyen suy tinh tu danh muc khach hien tai), nhung
    KHONG duoc de no im lang: model rat de doc 0 thanh 'dia ban do khong ban duoc gi'."""
    _setup(tmp_path, monkeypatch)
    # _FixedDate.today() = 2026-04-20 -> moc cat = 2025-04-01.
    # LUU Y ve so hoc: months_back bi kep toi da 12, nen lui 12 thang tu THANG MOI NHAT khong bao gio
    # cham qua moc cat (moc cung la 12 thang truoc hom nay). Ca that chi xay ra khi nguoi dung hoi ve
    # mot thang CU: month_to=2025-06 lui 12 thang -> bat dau tu 2024-07, truoc moc 2025-04-01.
    xa = rt.geography_monthly_performance(month_to="2025-06", months_back=12, dimension="city")
    assert "canh_bao_ngoai_cua_so" in xa, "phai canh bao khi khoang hoi vuot ra ngoai cua so chi tiet"
    assert xa["thieu_du_lieu_truoc_ngay"] == "2025-04-01"
    assert "khong duoc doc thanh" in xa["canh_bao_ngoai_cua_so"]


def test_hoi_trong_cua_so_thi_khong_canh_bao_thua(tmp_path, monkeypatch):
    """Canh bao thua cung la mot dang nhieu: neu thang nao cung canh bao thi model se quen no di."""
    _setup(tmp_path, monkeypatch)
    gan = rt.geography_monthly_performance(month_to="2026-04", months_back=4, dimension="city")
    assert "canh_bao_ngoai_cua_so" not in gan
