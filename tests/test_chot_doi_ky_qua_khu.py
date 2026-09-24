"""V34 + v24: chot doi cho ky QUA KHU, va khu trung dmsid khi join dim_nhanvien.

Do tren du lieu that 23/09/2026 (QLV TM23110128, chuong trinh MT_SP_TICHLUYCHAOTHU_ANC, ky 12/2025):
    chot doi tai 31/12/2025 -> 14 khach / 13 don co HD / 784.895.766d   (khop checker)
    chot doi tai 30/06/2026 -> 11 khach / 12 don       / 775.680.951d   (so chatbot da tra)
Lech vi 3 nguoi roi doi va 3 nguoi moi vao giua hai moc. Chenh doanh thu chi 1,2% nen khong the
phat hien bang mat - phai co test khoa lai.
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import local_warehouse  # noqa: E402
import report_templates as rt  # noqa: E402


QLV = "QLV_MT"
TIER = "TDV"


@pytest.fixture()
def kho(tmp_path, monkeypatch):
    """Kho toi thieu: doi 12/2025 co 3 nguoi, doi 06/2026 thay 1 nguoi khac."""
    db = tmp_path / "w.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE dim_nhanvien (employee_code TEXT, dmsid TEXT, name TEXT,
                                   position_code TEXT, area_code TEXT, is_duplicate INT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, manager_code TEXT, save_date TEXT,
                                            emp_dms_code TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, manager_code TEXT, save_date TEXT);
        """
    )
    con.executemany(
        "INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?)",
        [("E_CU", "D_CU", "Nguoi roi doi", TIER, "MT", 0),
         ("E_CHUNG", "D_CHUNG", "Nguoi o lai", TIER, "MT", 0),
         ("E_MOI", "D_MOI", "Nguoi moi vao", TIER, "MT", 0)],
    )
    # Bang theo khach chi giu snapshot GAN DAY (mo phong sync 90 ngay) - khong phu 12/2025.
    con.executemany(
        "INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?)",
        [("E_CHUNG", QLV, "2026-06-30", "D_CHUNG"), ("E_MOI", QLV, "2026-06-30", "D_MOI")],
    )
    # Bang luong giu lau hon (sync 400 ngay) - CO phu 12/2025, voi doi hinh CUA CHINH ky do.
    con.executemany(
        "INSERT INTO fact_thongketinhluong VALUES (?,?,?)",
        [("E_CU", QLV, "2025-12-31"), ("E_CHUNG", QLV, "2025-12-31"),
         ("E_CHUNG", QLV, "2026-06-30"), ("E_MOI", QLV, "2026-06-30")],
    )
    con.commit()
    con.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db))
    return db


def test_ky_qua_khu_chot_doi_dung_ky_thay_vi_nhay_toi_moc_sau(kho):
    """Loi V34: khong co snapshot <= ky hoi thi TRUOC DAY nhay toi moc SAU ky -> sai doi hinh."""
    thong_tin = {}
    ids = rt._get_team_dms_ids(QLV, "2025-12-31", thong_tin)

    assert set(ids) == {"D_CU", "D_CHUNG"}, (
        "Phai la doi hinh CUA 12/2025. Neu ra D_MOI thi da nhay toi moc 06/2026 - dung loi V34.")
    assert thong_tin["moc_chot_doi"] == "2025-12-31"
    assert thong_tin["nguon_chot_doi"] == "fact_thongketinhluong"
    assert thong_tin["moc_sau_ky"] is False


def test_nguoi_roi_doi_khong_bi_loai_khoi_ky_ma_ho_con_lam(kho):
    ids = rt._get_team_dms_ids(QLV, "2025-12-31")
    assert "D_CU" in ids
    assert "D_MOI" not in ids, "Nguoi vao thang 6/2026 khong duoc tinh vao ky 12/2025."


def test_bo_loc_dung_doi_12_2025_khi_snapshot_khach_da_het_han(kho):
    """Duong chung cua cac tool doanh thu phai thu snapshot luong khi khong con KPI 12/2025."""
    sql, ids = rt._employee_scope_clause(QLV, "v", as_of="2025-12-31")
    assert sql == " AND v.employee_code IN (?,?)"
    assert set(ids) == {"D_CU", "D_CHUNG"}
    assert "D_MOI" not in ids


def test_bo_loc_ky_co_snapshot_khach_van_dung_doi_cua_ky(kho):
    sql, ids = rt._employee_scope_clause(QLV, "v", as_of="2026-06-30")
    assert sql == " AND v.employee_code IN (?,?)"
    assert set(ids) == {"D_CHUNG", "D_MOI"}


def test_ky_hien_tai_van_dung_bang_theo_khach(kho):
    """Ban va khong duoc lam doi duong di cua ky BINH THUONG."""
    thong_tin = {}
    ids = rt._get_team_dms_ids(QLV, "2026-06-30", thong_tin)
    assert set(ids) == {"D_CHUNG", "D_MOI"}
    assert thong_tin["nguon_chot_doi"] == "fact_tonghopkhachhang"
    assert thong_tin["moc_sau_ky"] is False


def test_ghi_ro_khi_buoc_phai_dung_moc_sau_ky(kho):
    """Neu ca hai bang deu khong phu thi van phai chay duoc, nhung PHAI danh dau moc_sau_ky."""
    con = sqlite3.connect(kho)
    con.execute("DELETE FROM fact_thongketinhluong WHERE save_date='2025-12-31'")
    con.commit()
    con.close()

    thong_tin = {}
    ids = rt._get_team_dms_ids(QLV, "2025-12-31", thong_tin)
    assert ids, "Khong duoc hong cung - van phai tra duoc so kem canh bao."
    assert thong_tin["moc_sau_ky"] is True
    assert thong_tin["moc_chot_doi"] == "2026-06-30"


def test_khu_trung_dmsid_khong_nhan_ban_dong_hoa_don(tmp_path, monkeypatch):
    """v24 phat hien 1: dmsid trung trong dim_nhanvien lam dong hoa don bi dem hai lan."""
    db = tmp_path / "w2.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE dim_nhanvien (employee_code TEXT, dmsid TEXT, name TEXT,
                                   position_code TEXT, area_code TEXT, is_duplicate INT);
        CREATE TABLE hd (employee_code TEXT, amount9 REAL);
        """
    )
    # Dung hinh that gap tren kho: mot dmsid ung voi hai employee_code, mot dong bi danh co trung.
    con.executemany(
        "INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?)",
        [("TM23110109", "TM23110109", "Ban chinh", TIER, "MT", 0),
         ("TM23110109.", "TM23110109", "Ban trung", TIER, "MT", 1)],
    )
    con.execute("INSERT INTO hd VALUES ('TM23110109', 1000)")
    con.commit()

    tho = con.execute(
        "SELECT SUM(v.amount9) FROM hd v "
        "LEFT JOIN dim_nhanvien nv ON nv.dmsid=v.employee_code").fetchone()[0]
    assert tho == 2000, "Xac nhan bay co that: join tho lam doanh thu phong gap doi."

    khu = con.execute(
        f"SELECT SUM(v.amount9), MAX(nv.employee_code) FROM hd v "
        f"LEFT JOIN {rt._NV_THEO_DMSID} nv ON nv.dmsid=v.employee_code").fetchone()
    con.close()

    assert khu[0] == 1000, "Sau khu trung, moi dong hoa don chi duoc dem mot lan."
    assert khu[1] == "TM23110109", "Phai giu dong KHONG bi danh co is_duplicate."
