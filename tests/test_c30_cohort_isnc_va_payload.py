# -*- coding: utf-8 -*-
"""24/09/2026 - UAT C30 "Ty le giu chan theo cohort thang mo moi sau 1/3/6/12 thang" (cham 21/09).

Nguoi cham ghi hai loi:
1. "Lech so khach moi trong khi C29 lai tra loi dung": cohort hoa don cho 08/2026 = 324 khach,
   C29/M24 bao 627 khach moi (is_nc=1). Hai dinh nghia khac nhau, nay tra ca cohort theo IsNC.
2. "Thang 8 da ket thuc nhung lai tra loi khong du du lieu tinh % giu chan 1 thang": tuoi 1 cua
   cohort 08 roi vao thang 09 dang chay. Van tra None, them so tam tinh co nhan.

Them loi thu ba do tren may 24: payload 16 cohort bi cat con 12 dong dau, model mat cohort moi nhat
roi viet sai "chua tron ky" / "chua cohort nao du 12 thang".

Du lieu gia, khong cham Bravo, khong goi model."""
import json
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import nl2sql
import report_templates as rt


def _kho(tmp_path, co_snapshot=True):
    """KH_CU mua tu 2025 va duoc gan IsNC thang 08/2026 (mo moi lai). KH_MOI lan dau mua 08/2026.
    KH_07 mo moi thang 07 va mua lai thang 08. Du lieu den 21/09/2026 (thang 09 chua tron)."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
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
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
    """)
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB')")
    for kh in ("KH_CU", "KH_MOI", "KH_07"):
        conn.execute("INSERT INTO dms_khachhang VALUES (?,?,1,1,'D1','GT')", (kh, kh))
    conn.execute("INSERT INTO dim_nhanvien VALUES ('TDV1','TDV Mot',0,'TDV','MB','D1',NULL,NULL,0,NULL)")
    hoa_don = [("2025-03-10", "KH_CU"), ("2026-08-05", "KH_CU"), ("2026-09-10", "KH_CU"),
               ("2026-07-03", "KH_07"), ("2026-08-12", "KH_07"),
               ("2026-08-20", "KH_MOI"), ("2026-09-21", "KH_MOI")]
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES (?,?,'SP1',100,1,100,?,1,'D1',?,'OTC')",
        [(d, kh, f"H{i}", d) for i, (d, kh) in enumerate(hoa_don)])
    if co_snapshot:
        conn.executescript("""
            CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
                month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT,
                year_sale_target REAL, amount_cus REAL, is_ro INTEGER, is_ac INTEGER,
                max_customer_ord_amount REAL, emp_dms_code TEXT);
        """)
        conn.executemany(
            "INSERT INTO fact_tonghopkhachhang (employee_code, customer_code, amount_ct, save_date, "
            "is_nc, is_ro, is_ac) VALUES ('TDV1',?,100,?,?,0,0)",
            [("KH_07", "2026-07-31", 1),
             ("KH_07", "2026-08-31", 0), ("KH_CU", "2026-08-31", 1), ("KH_MOI", "2026-08-31", 1)])
    conn.commit()
    conn.close()
    return str(path)


def _cohort(kq, thang):
    return next(c for c in kq["cohorts"] if c["cohort_month"] == thang)


def _tuoi(cohort, tuoi):
    return next(r for r in cohort["retention"] if r["age_month"] == tuoi)


def test_cohort_isnc_khop_so_khach_moi_c29_va_co_bang_doi_chieu(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.customer_cohort_retention(month_to="2026-08", months_back=3, age_months=[1])

    c29 = rt.customer_lifecycle_summary(year_month="2026-08", months_back=2)["months"]
    khach_moi_c29 = {m["month"]: m["khach_moi"] for m in c29}
    isnc = kq["cohort_theo_isnc"]
    assert isnc["status"] == "ok"
    for c in isnc["cohorts"]:
        assert c["cohort_customers"] == khach_moi_c29[c["cohort_month"]], c["cohort_month"]
    # KH_CU mua tu 2025 nen KHONG nam trong cohort hoa don 08/2026, nhung la khach mo moi theo IsNC.
    assert _cohort(kq, "2026-08")["cohort_customers"] == 1
    doi_chieu = {d["month"]: d for d in kq["doi_chieu_hai_dinh_nghia_khach_moi"]}
    assert doi_chieu["2026-08"] == {"month": "2026-08", "khach_mo_moi_isnc": 2,
                                    "khach_lan_dau_co_hoa_don_trong_kho": 1}
    # Cohort IsNC 07/2026 (KH_07) mua lai thang 08 - thang da tron.
    tuoi1_07 = _tuoi(next(c for c in isnc["cohorts"] if c["cohort_month"] == "2026-07"), 1)
    assert tuoi1_07["retention_pct"] == 100.0


def test_thang_dich_chua_tron_giu_none_va_them_so_tam_tinh(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.customer_cohort_retention(month_to="2026-08", months_back=3, age_months=[1])

    tuoi1 = _tuoi(_cohort(kq, "2026-08"), 1)
    assert tuoi1["ky_da_du"] is False
    assert tuoi1["retention_pct"] is None, "Thang 09 chua tron - khong duoc chot ty le."
    assert tuoi1["retention_pct_tam_tinh"] == 100.0          # KH_MOI mua lai 21/09
    assert "2026-09-21" in kq["tam_tinh_thang_chua_tron"]
    tuoi1_isnc = _tuoi(next(c for c in kq["cohort_theo_isnc"]["cohorts"]
                            if c["cohort_month"] == "2026-08"), 1)
    assert tuoi1_isnc["retention_pct"] is None
    assert tuoi1_isnc["retention_pct_tam_tinh"] == 100.0     # KH_CU va KH_MOI deu mua thang 09


def test_kho_chua_co_snapshot_kpi_thi_bao_khong_co_nguon(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, co_snapshot=False))

    kq = rt.customer_cohort_retention(month_to="2026-08", months_back=3, age_months=[1])

    assert kq["cohort_theo_isnc"]["status"] == "khong_co_nguon"
    assert kq["doi_chieu_hai_dinh_nghia_khach_moi"] is None
    assert kq["cohorts"], "Bang cohort hoa don van phai tra binh thuong."


def test_tach_theo_vung_thi_khong_ghep_cohort_isnc(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.customer_cohort_retention(month_to="2026-08", months_back=3, age_months=[1],
                                      group_by="area")

    assert kq["cohort_theo_isnc"] is None


def _payload_16_cohort():
    """Dung hinh dang tra ve that tren may 24 ngay 24/09: 06/2025-09/2026, tuoi 1/3/6/12."""
    thang = ["2025-%02d" % m for m in range(6, 13)] + ["2026-%02d" % m for m in range(1, 10)]
    tron = "2026-08"
    cohorts = []
    for cm in thang:
        retention = []
        for tuoi in (1, 3, 6, 12):
            y, m = int(cm[:4]), int(cm[5:]) + tuoi
            y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            dich = "%d-%02d" % (y, m)
            du = dich <= tron
            retention.append({"age_month": tuoi, "target_month": dich,
                              "retained_customers": 123 if du else None,
                              "retention_pct": 37.123456789 if du else None, "ky_da_du": du})
        cohorts.append({"cohort_month": cm, "group": "ALL", "cohort_customers": 345,
                        "cohort_is_left_censored": False, "valid_new_customer_cohort": True,
                        "retention": retention})
    return {"definition": "x" * 120, "cohort_from": "2025-06", "cohort_to": "2026-09",
            "group_by": "overall", "ages": [1, 3, 6, 12], "cohorts": cohorts,
            "latest_complete_month": tron, "canh_bao": "y" * 700, "luu_y_doi_chieu": "z" * 200,
            "left_censored_cohort_months": [], "valid_cohort_count": 16}


def test_payload_gui_model_giu_du_16_cohort_va_dem_cohort_co_so_theo_tuoi():
    goi = json.loads(nl2sql._serialize_payload_for_model(
        "get_customer_cohort_retention", _payload_16_cohort(),
        "Tỷ lệ giữ chân theo cohort tháng mở mới sau 1/3/6/12 tháng"))

    assert "_model_view" not in goi, "Khong duoc roi vao luoi an toan cat mu."
    assert goi["tong_so_cohort"] == 16
    assert [d["cohort"] for d in goi["bang_cohort"]][-3:] == ["2026-07", "2026-08", "2026-09"]
    assert goi["cohort_co_so_theo_tuoi"]["t12"] == {"so_cohort": 3, "tu": "2025-06", "den": "2025-08"}
    assert goi["cohort_co_so_theo_tuoi"]["t1"]["den"] == "2026-07"
    dong_07 = next(d for d in goi["bang_cohort"] if d["cohort"] == "2026-07")
    assert dong_07["t1"] == 37.1 and dong_07["t3"] is None
