import inspect
import os
import re
import sqlite3

import pytest

from scripts import chay_sql_doi_chung_138 as bo_sql


def test_catalog_phu_du_138_cau_va_92_checker():
    noi_dung = bo_sql.doc_tai_lieu()
    checker = bo_sql.lay_checker(noi_dung)
    mapping = bo_sql.lay_mapping(noi_dung)
    assert len(checker) == 92
    assert len(bo_sql.lay_cau_hoi(noi_dung)) == 138
    assert sum(map(len, mapping.values())) == 138
    assert {item["ma"] for item in checker} == set(mapping), "Không được còn checker mồ côi"


def test_doi_tham_so_thay_duoc_bieu_thuc_as_of():
    sql = "DECLARE @AsOfDate date = DATEADD(day,-1,@MonthEnd);"
    assert bo_sql.doi_tham_so(sql, {"AsOfDate": "2026-08-28"}) == (
        "DECLARE @AsOfDate date = '2026-08-28';"
    )


def test_khoi_khai_bao_khong_lam_roi_bieu_thuc_as_of():
    khai_bao, tao_sales = bo_sql.lay_khai_bao_va_sales(bo_sql.doc_tai_lieu())
    assert "DECLARE @AsOfDate" in khai_bao
    assert "WHEN CONVERT(date,GETDATE())" in khai_bao
    assert "WHEN CONVERT(date,GETDATE())" not in tao_sales


def test_master_va_catalog_dung_cung_mapping():
    noi_dung = bo_sql.doc_tai_lieu()
    with open(
        bo_sql.os.path.join(
            bo_sql.ROOT, "docs", "bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md"
        ),
        encoding="utf-8",
    ) as fh:
        master = fh.read()
    master_map = dict(
        re.findall(r"\*\*([CMV]\d{2})\*\*.*?\[SQL: (S\d+)\]", master)
    )
    catalog_map = {
        cau["ma"]: cau["checker"] for cau in bo_sql.lay_cau_hoi(noi_dung)
    }
    assert master_map == catalog_map


def test_s38_loc_dung_manager_o_ca_ba_truy_van():
    """V17/M28: TUNG bang cua S38 phai tu ap scope doi, khong tron so toan cong ty.

    Kiem theo tung cau lenh chu khong dem chuoi tren ban ghep. Dem tren ban ghep van xanh
    ke ca khi ca ba bo loc don vao mot bang, con hai bang kia van tra so toan cong ty.
    """
    noi_dung = bo_sql.doc_tai_lieu()
    checker = {item["ma"]: item for item in bo_sql.lay_checker(noi_dung)}
    cau_lenh = checker["S38"]["cau_lenh"]

    assert len(cau_lenh) == 3, "S38 phai co dung 3 bang: tong hop, theo tang, tung nguoi"
    mau = re.compile(r"@ManagerCode IS NULL OR (?:\w+\.)?ManagerCode\s*(=|<>|!=)\s*@ManagerCode")
    for i, sql in enumerate(cau_lenh, 1):
        dau = mau.findall(sql)
        assert dau, "Bang %d cua S38 thieu bo loc @ManagerCode - se tra so toan cong ty" % i
        for d in dau:
            assert d == "=", "Bang %d dung dau '%s' thay vi '=' - dao nguoc pham vi doi" % (i, d)


def test_s38_bang_tung_nguoi_van_giu_nhanh_thieu_target():
    """Chan viec them scope lam chet nhanh nghiep vu con lai.

    Bang 3 loc (thieu manager HOAC thieu target). Khi da rang buoc ManagerCode=@ManagerCode thi
    nhanh "thieu manager" thanh bat kha thi, nen nhanh "thieu target" la thu duy nhat con lai
    va KHONG duoc mat theo.
    """
    noi_dung = bo_sql.doc_tai_lieu()
    checker = {item["ma"]: item for item in bo_sql.lay_checker(noi_dung)}
    bang_tung_nguoi = checker["S38"]["cau_lenh"][2]
    assert "MonthSaleTarget IS NULL OR" in bang_tung_nguoi
    assert "MonthSaleTarget<=0" in bang_tung_nguoi


def test_doi_tham_so_ho_tro_scope_manager_va_area():
    sql = (
        "DECLARE @AreaCode varchar(24) = NULL;\n"
        "DECLARE @ManagerCode varchar(24) = NULL;"
    )
    result = bo_sql.doi_tham_so(sql, {"AreaCode": "MB", "ManagerCode": "MBKV2"})

    assert "@AreaCode varchar(24) = 'MB'" in result
    assert "@ManagerCode varchar(24) = 'MBKV2'" in result


_TSQL_KHONG_CHAY_TREN_SQLITE = (
    (re.compile(r"\bSELECT\s+TOP\s*\(", re.I), "SELECT TOP (n) - SQLite dung LIMIT n"),
    (re.compile(r"\bDATEADD\s*\(", re.I), "DATEADD - SQLite dung date(x,'-1 month')"),
    (re.compile(r"\bEOMONTH\s*\(", re.I), "EOMONTH - khong co trong SQLite"),
    (re.compile(r"\bDATEDIFF\s*\(", re.I), "DATEDIFF - khong co trong SQLite"),
    (re.compile(r"\bISNULL\s*\(", re.I), "ISNULL - SQLite dung IFNULL/COALESCE"),
    (re.compile(r"@\w+"), "tham so @Ten kieu T-SQL - SQLite dung ? hoac :ten"),
)


def _cau_lenh_kho_local():
    noi_dung = bo_sql.doc_tai_lieu()
    for item in bo_sql.lay_checker(noi_dung):
        for sql in item["cau_lenh"]:
            if bo_sql._BANG_KHO_LOCAL.search(sql):
                yield item["ma"], sql


def test_checker_kho_local_khong_duoc_dung_cu_phap_tsql():
    """Cau lenh chay tren warehouse.db (SQLite) khong duoc mang cu phap T-SQL.

    S26 tung mang dong thoi 'SELECT TOP (100)' va join vao bang khong ton tai ma van xanh nhieu
    thang, vi trinh doi chung chi DAN NHAN roi bo qua thay vi chay that.
    """
    loi = []
    for ma, sql in _cau_lenh_kho_local():
        for mau, mo_ta in _TSQL_KHONG_CHAY_TREN_SQLITE:
            if mau.search(sql):
                loi.append("%s: %s" % (ma, mo_ta))
    assert loi == [], "Cu phap T-SQL trong cau lenh kho local: %s" % loi


def test_trinh_doi_chung_thuc_su_chay_checker_kho_local():
    """Nhanh KHO_LOCAL phai goi chay_kho_local, khong duoc chi gan nhan roi bo qua."""
    assert hasattr(bo_sql, "chay_kho_local")
    nguon = inspect.getsource(bo_sql.main)
    assert "chay_kho_local(" in nguon, "main() khong con chay checker kho local"


@pytest.mark.skipif(
    not os.path.isfile(os.path.join(bo_sql.ROOT, "backend", "warehouse.db")),
    reason="Khong co warehouse.db tren may nay",
)
def test_cau_lenh_kho_local_chay_duoc_that_tren_warehouse():
    """EXPLAIN tren kho that: bat ca loi cu phap lan bang/cot khong ton tai, khong tra du lieu."""
    con = sqlite3.connect(os.path.join(bo_sql.ROOT, "backend", "warehouse.db"))
    try:
        for ma, sql in _cau_lenh_kho_local():
            try:
                con.execute("EXPLAIN " + sql.rstrip().rstrip(";"))
            except sqlite3.Error as loi:
                raise AssertionError("%s khong chay duoc tren kho local: %s" % (ma, loi))
    finally:
        con.close()


def test_gop_trang_thai_chi_goi_mot_phan_khi_that_su_co_loi():
    """Checker vua chay Bravo vua chay kho local ma ca hai deu duoc thi la CHAY_DUOC.

    Truoc 10/09 to hop nay bi goi la CHAY_MOT_PHAN, khien S24 nhin nhu con thieu trong khi ca ba
    bang deu ra so - chi vi phan kho local hoi do khong duoc chay bao gio.
    """
    assert bo_sql.gop_trang_thai({"CHAY_DUOC", "KHO_LOCAL"}) == "CHAY_DUOC"
    assert bo_sql.gop_trang_thai({"CHAY_DUOC"}) == "CHAY_DUOC"
    assert bo_sql.gop_trang_thai({"KHO_LOCAL"}) == "KHO_LOCAL"
    assert bo_sql.gop_trang_thai({"LOI"}) == "LOI"
    assert bo_sql.gop_trang_thai({"LOI", "CHAY_DUOC"}) == "CHAY_MOT_PHAN"
    assert bo_sql.gop_trang_thai({"LOI", "KHO_LOCAL"}) == "CHAY_MOT_PHAN"


def _kho_gia_s26():
    """Kho SQLite gia: hoa don moi nhat 04/09 (thang 9 moi co 4 ngay), snapshot no 04/09."""
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, customer_code TEXT, customer_name TEXT,
            balance_end REAL, total_overdue REAL);
        CREATE TABLE vhoadon_otc (customer_code TEXT, doc_date TEXT, amount9 REAL);
        CREATE TABLE vhoadon_etc (customer_code TEXT, doc_date TEXT, amount9 REAL);
    """)
    for kh in ("DEU", "GIAM", "CHUA_KIP_MUA"):
        con.execute("INSERT INTO fact_congno_khachhang VALUES ('2026-09-04', ?, ?, 1000, 500)", (kh, kh))
    hoa_don = [
        ("DEU", "2026-07-10", 100), ("DEU", "2026-08-10", 100),            # mua deu hai thang tron
        ("GIAM", "2026-07-10", 100), ("GIAM", "2026-08-10", 40),           # giam that o thang tron
        ("CHUA_KIP_MUA", "2026-07-10", 100), ("CHUA_KIP_MUA", "2026-08-10", 100),
        ("DEU", "2026-09-04", 5),                                          # thang 9 moi co 4 ngay
    ]
    con.executemany("INSERT INTO vhoadon_otc VALUES (?, ?, ?)", hoa_don)
    return con


def test_s26_so_thang_tron_khong_so_thang_dang_chay_do():
    """Bay MTD: so 4 ngay dau thang 9 voi ca thang 8 thi gan nhu ai cung 'giam mua'.

    Ban 10/09 dinh bay nay: tren kho that ra 2.575 khach thay vi 961. Kho gia co 3 khach no qua han,
    chi 1 khach (GIAM) giam that o hai thang tron. Ban dung phai so T8 voi T7 va ra dung 1 khach.
    """
    noi_dung = bo_sql.doc_tai_lieu()
    checker = {item["ma"]: item for item in bo_sql.lay_checker(noi_dung)}
    cau_lenh = checker["S26"]["cau_lenh"]
    assert len(cau_lenh) == 2, "S26 phai co bang danh sach va bang tong"

    con = _kho_gia_s26()
    try:
        ds = con.execute(cau_lenh[0].rstrip().rstrip(";")).fetchall()
        tong = con.execute(cau_lenh[1].rstrip().rstrip(";")).fetchone()
    finally:
        con.close()

    assert [r[0] for r in ds] == ["GIAM"]
    snapshot, hoa_don_moi_nhat, ky_so_sanh, so_khach, tong_no = tong
    assert hoa_don_moi_nhat == "2026-09-04"
    assert ky_so_sanh == "2026-08-01", "Phai lui ve thang tron gan nhat, khong lay thang 9 dang do"
    assert so_khach == 1
    assert tong_no == 500
