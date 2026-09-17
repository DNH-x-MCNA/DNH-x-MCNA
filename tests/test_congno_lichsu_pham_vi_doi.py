# -*- coding: utf-8 -*-
"""17/09/2026 - VA LO PHAM VI DOI tren hai tool lich su cong no, va cho chuoi ve trong MOT lan goi.

LO PHAM VI: receivables_period_compare KHONG nhan scope_employee_code va KHONG nam trong
_PERSON_LEVEL_TEMPLATES, nen chot fail-closed trong call_template() khong he kich hoat voi tai khoan
QLV - tool chay voi pham vi CA VUNG. Khi tool chi tra 2 con so tong thi hau qua con nho; nhung ban
17/09 them TOP 10 KHACH kem ten va so no, tuc QLV doc duoc khach cua doi khac. Dung dieu ma chinh
chot fail-closed goi la khong chap nhan duoc.

MOT LAN GOI: receivables_history_dates cu chi tra danh sach NGAY, muon ve duong xu huong thi model
phai goi period_compare cho tung cap - voi ~27 moc la bat kha thi trong han muc vong goi tool, nen
model chi lay 4 moc roi trinh bay nhu the do la toan bo du lieu (UAT that, cau C37).

Du lieu gia, khong cham Bravo."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fact_congno_khachhang_history (snapshot_date TEXT, snapshot_at TEXT,
            customer_code TEXT, customer_name TEXT, sales_channel TEXT, area_code TEXT,
            balance_end REAL, overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL,
            overdue_gt_45 REAL, total_overdue REAL);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, manager_code TEXT,
            save_date TEXT, amount_ct REAL, month_sale_target REAL, is_nc INTEGER);
    """)
    rows = []
    for ngay, no_doi, no_ngoai in (("2026-09-01", 100.0, 900.0), ("2026-09-08", 150.0, 800.0),
                                   ("2026-09-15", 200.0, 700.0)):
        rows.append((ngay, "KH_DOI", "Khach cua doi minh", "OTC", "MB", 1000.0, no_doi, 0.0, 0.0, 0.0, no_doi))
        rows.append((ngay, "KH_NGOAI", "Khach doi khac", "OTC", "MB", 5000.0, no_ngoai, 0.0, 0.0, 0.0, no_ngoai))
    conn.executemany(
        "INSERT INTO fact_congno_khachhang_history VALUES (?,'2026-09-15T10:00:00',?,?,?,?,?,?,?,?,?,?)",
        rows)
    # Phan cong KPI: KH_DOI thuoc doi QLV1, KH_NGOAI thuoc doi khac.
    conn.executemany(
        "INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,'2026-09-15',0,0,0)",
        [("TDV1", "KH_DOI", "QLV1"), ("TDV9", "KH_NGOAI", "QLV9")])
    conn.commit()
    conn.close()
    return str(path)


def test_qlv_chi_thay_khach_cua_doi_minh_trong_so_sanh_hai_moc(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_period_compare("2026-09-15", "2026-09-01", scope_employee_code="QLV1")

    a = kq["ky_a"]
    assert a["total_overdue"] == 200.0          # CHI no cua KH_DOI, khong gom 700 cua khach doi khac
    ma_khach = {c["customer_code"] for c in a["top_overdue_customers"]}
    assert ma_khach == {"KH_DOI"}               # KHONG duoc lo ten khach cua doi khac


def test_qlv_chi_thay_doi_minh_trong_chuoi_theo_moc(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_history_dates(scope_employee_code="QLV1")

    assert [r["total_overdue"] for r in kq["chuoi_theo_moc"]] == [100.0, 150.0, 200.0]
    assert kq["pham_vi_doi"]["manager_code"] == "QLV1"
    assert kq["pham_vi_doi"]["assigned_customers"] == 1


def test_khong_co_scope_thi_van_thay_toan_bo(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_history_dates()

    assert [r["total_overdue"] for r in kq["chuoi_theo_moc"]] == [1000.0, 950.0, 900.0]
    assert "pham_vi_doi" not in kq


def test_qlv_hoi_kenh_etc_bi_tu_choi_thay_vi_lay_ca_vung(tmp_path, monkeypatch):
    """Chua co phan cong khach ETC theo doi - phai tu choi, khong duoc lay cong no ca vung thay the."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    import pytest
    with pytest.raises(rt.KhongXacDinhDuocDoi):
        rt.receivables_history_dates(scope_employee_code="QLV1", scope_channel="ETC")
    with pytest.raises(rt.KhongXacDinhDuocDoi):
        rt.receivables_period_compare("2026-09-15", "2026-09-01",
                                      scope_employee_code="QLV1", scope_channel="ETC")


def test_chuoi_ve_du_moc_trong_mot_lan_goi_kem_chenh_lech(tmp_path, monkeypatch):
    """Dung cai ma cau C37 thieu: ca chuoi trong MOT lan goi, khong phai goi so sanh tung cap."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_history_dates()

    chuoi = kq["chuoi_theo_moc"]
    assert len(chuoi) == 3 and kq["so_ngay_co_du_lieu"] == 3
    assert [r["snapshot_date"] for r in chuoi] == ["2026-09-01", "2026-09-08", "2026-09-15"]
    assert chuoi[0].get("delta_total_overdue") is None      # moc dau khong co gi de tru
    assert chuoi[1]["delta_total_overdue"] == -50.0
    assert chuoi[2]["delta_total_overdue"] == -50.0
    assert "KHONG duoc goi get_receivables_period_compare lap lai" in kq["answer_rule"] or \
           "KHONG can goi get_receivables_period_compare" in kq["answer_rule"]


def test_hai_tool_da_dang_ky_gioi_han_doi_o_ca_hai_tap():
    """Chot lai bang dang ky: thieu mot trong hai tap la lo pham vi hoac bi tu choi oan."""
    for ten in ("get_receivables_period_compare", "get_receivables_history_dates"):
        assert ten in rt._PERSON_LEVEL_TEMPLATES
        assert ten in rt._EMPLOYEE_SCOPED_TEMPLATES
        assert ten not in rt._AREA_EXEMPT_TEMPLATES
        assert rt._CHANNEL_SCOPE_POLICIES[ten] == "filter"


def _kho_tuoi_no(tmp_path):
    """Hai moc: KH_GIA di tu nhom 15-30 sang 30-45; KH_YEN giu nguyen nhom 1-15."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fact_congno_khachhang_history (snapshot_date TEXT, snapshot_at TEXT,
            customer_code TEXT, customer_name TEXT, sales_channel TEXT, area_code TEXT,
            balance_end REAL, overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL,
            overdue_gt_45 REAL, total_overdue REAL);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, manager_code TEXT,
            save_date TEXT, amount_ct REAL, month_sale_target REAL, is_nc INTEGER);
    """)
    conn.executemany(
        "INSERT INTO fact_congno_khachhang_history VALUES (?,'2026-09-15T10:00:00',?,?,'OTC','MB',?,?,?,?,?,?)",
        [
            # moc CU: KH_GIA dang o nhom 15-30
            ("2026-09-01", "KH_GIA", "Khach gia di", 900.0, 0.0, 300.0, 0.0, 0.0, 300.0),
            ("2026-09-01", "KH_YEN", "Khach yen", 500.0, 200.0, 0.0, 0.0, 0.0, 200.0),
            # moc MOI: KH_GIA da chuyen sang 30-45 (tien khong doi - dung cai bay cua meo suy luan)
            ("2026-09-15", "KH_GIA", "Khach gia di", 900.0, 0.0, 0.0, 300.0, 0.0, 300.0),
            ("2026-09-15", "KH_YEN", "Khach yen", 500.0, 200.0, 0.0, 0.0, 0.0, 200.0),
        ])
    conn.commit()
    conn.close()
    return str(path)


def test_chi_ra_khach_gia_di_bang_doi_chieu_khong_phai_suy_luan(tmp_path, monkeypatch):
    """V35 17/09/2026: chatbot tung phai suy luan tu 'so tien qua han khong doi' vi tool khong tra
    nhom tuoi theo tung khach. KH_GIA co so tien Y NGUYEN 300 nhung da chuyen 15-30 -> 30-45: chi
    doi chieu nhom tuoi moi thay, meo 'tien khong doi' thi KHONG phan biet duoc voi KH_YEN."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_tuoi_no(tmp_path))

    kq = rt.receivables_period_compare("2026-09-15", "2026-09-01")

    gia_di = kq["khach_chuyen_nhom_tuoi_xau_hon"]
    assert [k["customer_code"] for k in gia_di] == ["KH_GIA"]
    assert gia_di[0]["nhom_tuoi_truoc"] == "overdue_15_30"
    assert gia_di[0]["nhom_tuoi_sau"] == "overdue_30_45"
    assert gia_di[0]["total_overdue_truoc"] == gia_di[0]["total_overdue_sau"]   # tien khong doi
    assert "KHONG suy luan" in kq["pham_vi_so_sanh_khach"]


def test_tung_khach_co_nhom_tuoi_va_bo_nhom_bang_khong(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho_tuoi_no(tmp_path))

    kq = rt.receivables_period_compare("2026-09-15", "2026-09-01")

    theo_ma = {c["customer_code"]: c for c in kq["ky_a"]["top_overdue_customers"]}
    assert theo_ma["KH_GIA"]["nhom_tuoi_xau_nhat"] == "overdue_30_45"
    assert theo_ma["KH_GIA"]["aging"] == {"overdue_30_45": 300}    # bo cac nhom bang 0
    assert theo_ma["KH_YEN"]["aging"] == {"overdue_1_15": 200}
