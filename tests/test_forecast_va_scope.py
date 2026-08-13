# -*- coding: utf-8 -*-
"""Test cho 2 thay doi ngay 12/08/2026, deu chay tren KHO GIA nen khong can may 24:

  1. revenue_by_region KHONG con bao dong gia khi bi gioi han theo doi QLV.
     Truoc do phep tu-doi-chieu ben trong ham so tong CUA DOI voi tong TOAN CONG TY
     (revenue_by_channel duoc goi khong kem scope) -> doi nao cung "lech" -> luon bom canh bao
     "SO LIEU THEO VUNG CO THE THIEU" va dan AI "KHONG duoc trinh bay breakdown nay nhu so lieu
     chac chan", DU SO HOAN TOAN DUNG.

  2. revenue_forecast_month - mo hinh du bao moi (trung binh cung thang 3 nam gan nhat).

Kho gia dung dung schema that o cac cot cac ham nay doc toi. Khong cham vao warehouse.db that.
"""
import datetime as dt
import os
import sqlite3
import sys

import pytest

# APPEND chu khong insert(0): backend/ co main.py rieng, day len dau sys.path se che mat main.py
# o goc repo va lam test_phase1_phase2.py vo ngay luc thu thap ("cannot import name
# send_daily_digest from main"). Append van du de tim report_templates/local_warehouse.
_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _BACKEND not in sys.path:
    sys.path.append(_BACKEND)

import local_warehouse  # noqa: E402
import report_templates as rt  # noqa: E402

QLV_CODE = "Q1"
ZONE = "V01"
TDV_DMS = ["D01", "D02"]


def _ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _build(path, thang_co_doanh_thu):
    """thang_co_doanh_thu: {(year_month, channel): tong_doanh_thu_cua_doi}."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE vhoadon_otc (stt INTEGER, doc_date TEXT, amount9 REAL, customer_code TEXT,
                                  employee_code TEXT, item_code TEXT, quantity REAL,
                                  unit_price REAL, channel_code TEXT);
        CREATE TABLE vhoadon_etc (stt INTEGER, doc_date TEXT, amount9 REAL, customer_code TEXT,
                                  employee_code TEXT, item_code TEXT, quantity REAL, unit_price REAL);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
                                               employee_code TEXT, revenue REAL, invoice_count INTEGER);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, position_code TEXT, area_code TEXT,
                                   manager_area_code TEXT, dmsid TEXT, end_date TEXT,
                                   is_resigned INTEGER, is_duplicate INTEGER);
        CREATE TABLE dms_khachhang (code TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT);
    """)
    # Cay to chuc: 1 ban ghi "bong" cua QLV mang manager_area_code cua to, + ban ghi QLV that
    # cung ten (day dung la co che suy luan cua org_hierarchy.zone_to_qlv_map).
    con.executemany(
        "INSERT INTO dim_nhanvien (employee_code,name,position_code,area_code,manager_area_code,"
        "dmsid,end_date,is_resigned,is_duplicate) VALUES (?,?,?,?,?,?,NULL,0,0)",
        [
            ("SHADOW", "Nguyen Van A (QLV)", "TDV", "MB", ZONE, "DQ1"),
            (QLV_CODE, "Nguyen Van A", "QLV", "MB", None, "DQ1"),
            ("T01", "Tran Thi B", "TDV", "MB", ZONE, TDV_DMS[0]),
            ("T02", "Le Van C", "TDV", "MB", ZONE, TDV_DMS[1]),
            # Nguoi NGOAI doi - doanh thu cua ho KHONG duoc lot vao pham vi cua QLV tren
            ("T99", "Pham Ngoai Doi", "TDV", "MN", "V09", "D99"),
        ])
    con.execute("INSERT INTO dms_khachhang VALUES ('KH001', 1)")
    con.execute("INSERT INTO dmssx_khachhang VALUES ('KH001', 1)")
    con.execute("INSERT INTO dim_tinhthanhpho VALUES (1, 'MB')")

    cutoff = rt._detail_cutoff()  # 12 thang gan nhat moi con chi tiet
    stt = 0
    for (ym, ch), tong in thang_co_doanh_thu.items():
        moi_nguoi = tong / len(TDV_DMS)
        for dms in TDV_DMS:
            if f"{ym}-15" >= cutoff:
                stt += 1
                con.execute(
                    f"INSERT INTO vhoadon_{ch.lower()} (stt,doc_date,amount9,customer_code,"
                    f"employee_code,item_code,quantity,unit_price) VALUES (?,?,?,?,?,?,?,?)",
                    (stt, f"{ym}-15 09:00:00", moi_nguoi, "KH001", dms, "SP1", 1, 100))
            else:
                con.execute("INSERT INTO monthly_customer_summary VALUES (?,?,?,?,?,?)",
                            (ym, ch, "KH001", dms, moi_nguoi, 1))
        # Nguoi ngoai doi luon co doanh thu, de tong toan cong ty KHAC tong cua doi.
        if f"{ym}-15" >= cutoff:
            stt += 1
            con.execute(
                f"INSERT INTO vhoadon_{ch.lower()} (stt,doc_date,amount9,customer_code,"
                f"employee_code,item_code,quantity,unit_price) VALUES (?,?,?,?,?,?,?,?)",
                (stt, f"{ym}-15 09:00:00", tong * 3, "KH001", "D99", "SP1", 1, 100))
        else:
            con.execute("INSERT INTO monthly_customer_summary VALUES (?,?,?,?,?,?)",
                        (ym, ch, "KH001", "D99", tong * 3, 1))
    con.commit()
    con.close()


@pytest.fixture
def kho(tmp_path, monkeypatch):
    """Kho gia: 4 nam lich su, thang 8 moi nam co doanh thu doi biet truoc."""
    hom_nay = dt.date.today()
    thang_nay = hom_nay.strftime("%Y-%m")
    data = {}
    for i in range(1, 49):  # 48 thang truoc thang hien tai
        ym = _ym_add(thang_nay, -i)
        data[(ym, "OTC")] = 1_000_000_000.0
        data[(ym, "ETC")] = 2_000_000_000.0
    db = str(tmp_path / "warehouse.db")
    _build(db, data)
    monkeypatch.setattr(local_warehouse, "DB_PATH", db)
    return db


# ---------------------------------------------------------------- lỗi cảnh báo sai (dòng 429)

def test_gioi_han_theo_doi_KHONG_con_bao_dong_gia(kho):
    """Tong cua doi (2 TDV) khac han tong toan cong ty (co them nguoi ngoai doi gap 3 lan).
    Phep tu-doi-chieu phai so DOI voi DOI, khong duoc so DOI voi TOAN CONG TY."""
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    p = rt.call_template("get_revenue_by_region",
                         {"date_from": f"{thang}-01", "date_to": f"{thang}-28"},
                         scope_employee_code=QLV_CODE, scope_role="qlv")
    assert p["ok"], p.get("error")
    canh_bao = " ".join(p.get("canh_bao") or [])
    assert "THEO VUNG CO THE THIEU" not in canh_bao.upper(), (
        "Bao dong gia da quay lai: revenue_by_region dang so tong CUA DOI voi tong TOAN CONG TY "
        f"(xem report_templates.py, phep tu-doi-chieu). Canh bao nhan duoc: {canh_bao}")


def test_khong_gioi_han_thi_van_con_phep_tu_doi_chieu(kho):
    """Ban va KHONG duoc lam mat phep tu-doi-chieu o pham vi toan cong ty - do van la luoi an toan
    that (bat truong hop JOIN am tham lam roi du lieu)."""
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    p = rt.call_template("get_revenue_by_region",
                         {"date_from": f"{thang}-01", "date_to": f"{thang}-28"},
                         scope_role="tp")
    assert p["ok"], p.get("error")
    assert not (p.get("canh_bao") or []), "Du lieu gia vay khong lech, khong duoc canh bao gi"


def test_pham_vi_doi_chi_gom_doanh_thu_cua_doi(kho):
    """Chan lo du lieu: nguoi ngoai doi co doanh thu gap 3 lan ca doi, khong duoc lot vao."""
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    doi = rt.revenue_by_channel(f"{thang}-01", f"{thang}-28 23:59:59", scope_employee_code=QLV_CODE)
    ca_cong_ty = rt.revenue_by_channel(f"{thang}-01", f"{thang}-28 23:59:59")
    assert doi["otc"]["revenue"] == pytest.approx(1_000_000_000.0)
    assert ca_cong_ty["otc"]["revenue"] == pytest.approx(4_000_000_000.0)


# ---------------------------------------------------------------- tool dự báo

def test_du_bao_bang_trung_binh_cung_thang_3_nam(kho):
    """Mo hinh phai la trung binh dung 3 nam, khong phai gi khac."""
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    r = rt.revenue_forecast_month(thang, scope_employee_code=QLV_CODE)
    otc = r["cac_kenh"]["OTC"]
    assert otc["so_nam_can_cu"] == 3
    assert [c["thang"] for c in otc["can_cu"]] == [_ym_add(thang, -12 * i) for i in (1, 2, 3)]
    assert otc["du_bao"] == pytest.approx(1_000_000_000.0)


def test_bo_qua_thang_dang_chay(kho):
    """Thang hien tai chua tron - dua vao chuoi lich su la keo tut du bao xuong."""
    chuoi = rt._monthly_series("OTC", scope_employee_code=QLV_CODE)
    assert dt.date.today().strftime("%Y-%m") not in chuoi


def test_tu_choi_khi_thieu_lich_su(kho):
    """Chi co 1 nam cung thang -> KHONG duoc doan, phai noi ly do."""
    xa = _ym_add(dt.date.today().strftime("%Y-%m"), -47)
    r = rt.revenue_forecast_month(xa, scope_employee_code=QLV_CODE)
    otc = r["cac_kenh"]["OTC"]
    assert otc["du_bao"] is None
    assert "ly_do_khong_du_bao" in otc


def test_khoang_uoc_tinh_khong_bao_gio_am(kho, monkeypatch):
    """Sai so >100% thi pred*(1-e) am. Doanh thu khong the am -> phai chan day o 0."""
    monkeypatch.setattr(rt, "_forecast_accuracy",
                        lambda s: {"do_duoc": True, "so_thang_kiem": 24,
                                   "sai_so_trung_binh_pct": 140.0})
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    otc = rt.revenue_forecast_month(thang, scope_employee_code=QLV_CODE)["cac_kenh"]["OTC"]
    assert otc["khoang_uoc_tinh"]["thap"] == 0.0
    assert otc["khong_dang_tin"], "Sai so 140% ma khong danh dau khong dang tin"


def test_sai_so_binh_thuong_thi_khong_danh_dau(kho):
    """Nguoc lai: du lieu deu tam tap thi khong duoc gan nhan 'khong dang tin' vo co."""
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    otc = rt.revenue_forecast_month(thang, scope_employee_code=QLV_CODE)["cac_kenh"]["OTC"]
    assert "khong_dang_tin" not in otc
    assert otc["khoang_uoc_tinh"]["thap"] > 0


def test_thang_sai_dinh_dang_bao_loi_ro_rang(kho):
    assert "YYYY-MM" in rt.revenue_forecast_month("thang 8")["error"]


def test_luon_kem_canh_bao_day_la_uoc_tinh(kho):
    """Ba dieu bat buoc trong prompt phu thuoc vao cac truong nay - mat chung la AI trinh bay
    so uoc tinh nhu so that."""
    thang = _ym_add(dt.date.today().strftime("%Y-%m"), -1)
    r = rt.revenue_forecast_month(thang, scope_employee_code=QLV_CODE)
    assert r["day_la_uoc_tinh"] is True
    assert any("UOC TINH" in c.upper() for c in r["canh_bao"])
