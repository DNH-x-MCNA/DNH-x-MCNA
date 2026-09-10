import re

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
    """V17/M28: moi bang S38 phai cung dung scope doi, khong tron so toan cong ty."""
    noi_dung = bo_sql.doc_tai_lieu()
    checker = {item["ma"]: item for item in bo_sql.lay_checker(noi_dung)}
    sql = "\n".join(checker["S38"]["cau_lenh"])

    assert sql.count("@ManagerCode IS NULL") == 3
    assert "f.ManagerCode=@ManagerCode" in sql
    assert "ManagerCode=@ManagerCode" in sql
    assert "b.ManagerCode=@ManagerCode" in sql


def test_doi_tham_so_ho_tro_scope_manager_va_area():
    sql = (
        "DECLARE @AreaCode varchar(24) = NULL;\n"
        "DECLARE @ManagerCode varchar(24) = NULL;"
    )
    result = bo_sql.doi_tham_so(sql, {"AreaCode": "MB", "ManagerCode": "MBKV2"})

    assert "@AreaCode varchar(24) = 'MB'" in result
    assert "@ManagerCode varchar(24) = 'MBKV2'" in result
