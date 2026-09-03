import re

from scripts import chay_sql_doi_chung_138 as bo_sql


def test_catalog_phu_du_138_cau_va_86_checker():
    noi_dung = bo_sql.doc_tai_lieu()
    checker = bo_sql.lay_checker(noi_dung)
    mapping = bo_sql.lay_mapping(noi_dung)
    assert len(checker) == 86
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
