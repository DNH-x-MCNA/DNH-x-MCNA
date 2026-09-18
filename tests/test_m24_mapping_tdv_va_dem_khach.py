# -*- coding: utf-8 -*-
"""18/09/2026 - cau M24: "mapping so khach moi voi TDV sai, lech so khach trong thang 8".

Ba loi rieng biet, deu do lai duoc tren kho that:

1. _nv_theo_dms() chi tra dim_nhanvien. Nhan vien ETC/SX (DNH00087, DNH00268, Sale02...) KHONG co
   trong bang do - ho chi ton tai o dmssx_nhanvien. Ket qua: 26/194 dong by_employee cua thang 8 ra
   ma tran khong co ten, om 35 khach moi va 186 khach tai kich hoat.
   _resolve_employee_identity() da tra bang thu hai nay tu 20/07/2026; _nv_theo_dms thi chua.

2. Khi mot DMSId ung voi nhieu dong danh muc, ban cu sap xep theo is_duplicate DESC roi lay dong
   dau - va cham vao dung O TRONG dang cho tuyen: TM24060301 ra "Trong QLV MK3" thay vi Truong Ho
   Minh Luan, TM24100101 ra "Trong QLV" thay vi Nguyen Ngoc Quoc Hung. is_duplicate khong phan biet
   duoc: TM24060301 co CA HAI dong deu =1, con TM24100101 thi chinh dong o trong moi =1.

3. customer_lifecycle_summary() loc "tang nhan vien" ngay trong WHERE, ap len ca cac cot DEM.
   COUNT(DISTINCT customer_code) von da mien nhiem voi dong rollup QLV chong len dong TDV, nen phep
   loc do khong chong duoc gi ma chi lam MAT khach chi xuat hien tren dong QLV - khach do chinh QLV
   ban truc tiep. Do that: snapshot 31/08 bao 612 trong khi Bravo co 627; thang 7 la 605/613, thang
   6 la 752/765 - lech mot chieu, co he thong.

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
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT,
            year_sale_target REAL, amount_cus REAL, is_ro INTEGER, is_ac INTEGER,
            max_customer_ord_amount REAL, emp_dms_code TEXT);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE dmssx_nhanvien (id_code INTEGER, name TEXT, dmscode TEXT, code TEXT,
            is_active TEXT);
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
    """)
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?,NULL,NULL,0,NULL)", [
        ("TDV1", "TDV Mot", 0, "TDV", "MB", "D1"),
        ("QLV1", "QLV Mot", 0, "QLV", "MB", "Q1"),
        # Hai kieu o trong da gap that. VT_A: o trong va nguoi that cung is_duplicate=1.
        ("VT_A", "Trong QLV MK3", 1, "QLV", "MN", "DMS_A"),
        ("VT_A.", "Truong Ho Minh Luan (QLV)", 1, "TDV", "MN", "DMS_A"),
        # VT_B: chinh dong O TRONG mang is_duplicate=1, nguoi that mang 0.
        ("VT_B#", "Trong QLV", 1, "QLV", "MT", "DMS_B"),
        ("VT_B", "Nguyen Ngoc Quoc Hung", 0, "QLV", "MT", "DMS_B"),
    ])
    conn.execute("INSERT INTO dmssx_nhanvien VALUES (111298,'Nguyen Du Chung','DNH00099','DNH00099','1')")
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'Ha Noi','MB')")
    conn.execute("INSERT INTO monthly_customer_summary VALUES ('2025-05','OTC','HISTORY-BOUND','D1',0,0)")

    def fact(emp, cus, amount, nc="0", ro="0", mgr="QLV1"):
        conn.execute("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,0,'2026-08-31',?,?,0,0,?,'0',0,?)",
                     (emp, cus, amount, nc, mgr, ro, emp))

    # KH_TDV: co ca dong TDV lan dong rollup QLV - dung tinh huong "chong len" ma phep loc tang
    # sinh ra de chong. Dong QLV de trong ca hai co, giong het production.
    fact("TDV1", "KH_TDV", 100.0, nc="1")
    fact("QLV1", "KH_TDV", 100.0)
    # KH_QLV: CHI co dong QLV - QLV tu ban, khong TDV nao duoi quyen ghi nhan. Ban cu danh roi khach
    # nay; day chinh la 15 khach cua thang 8.
    fact("QLV1", "KH_QLV", 50.0, nc="1")
    # KH_RO: khach dat lai hang, de kiem dang thuc nc + ro + khong mang co = tong.
    fact("TDV1", "KH_RO", 70.0, ro="1")
    fact("QLV1", "KH_RO", 70.0)
    conn.commit()
    conn.close()
    return str(path)


def test_tra_duoc_ten_nhan_vien_etc_sx_tu_bang_rieng(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt._nv_theo_dms(["DNH00099"])

    assert kq["DNH00099"]["employee_name"] == "Nguyen Du Chung"


def test_khong_tra_duoc_thi_bo_trong_chu_khong_bia(tmp_path, monkeypatch):
    """Ma khong co o ca hai bang (vd Sale03 tren kho that) phai vang mat, khong duoc gan bua ten."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    assert rt._nv_theo_dms(["KHONG_TON_TAI"]) == {}


def test_chon_nguoi_that_thay_vi_o_trong_khi_hai_dong_cung_is_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt._nv_theo_dms(["DMS_A"])

    assert kq["DMS_A"]["employee_name"] == "Truong Ho Minh Luan (QLV)"
    assert kq["DMS_A"]["employee_code"] == "VT_A."


def test_chon_nguoi_that_ngay_ca_khi_o_trong_moi_la_dong_is_duplicate_1(tmp_path, monkeypatch):
    """Bay nguoc cua meo "is_duplicate=1 thuong la nguoi that"."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt._nv_theo_dms(["DMS_B"])

    assert kq["DMS_B"]["employee_name"] == "Nguyen Ngoc Quoc Hung"


def test_dem_ca_khach_ma_qlv_tu_ban_khong_qua_tdv(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.customer_lifecycle_summary(year_month="2026-08")
    m = kq["months"][0]

    assert m["khach_moi"] == 2                          # KH_TDV va KH_QLV, ban cu chi thay 1
    assert m["khach_moi_do_qlv_ban_truc_tiep"] == 1     # noi ro phan chenh den tu dau
    assert m["tong_khach"] == 3


def test_doanh_so_van_chi_cong_tang_nhan_vien(tmp_path, monkeypatch):
    """Phan chua sua: tien THI that su bi cong hai lan neu gom ca dong rollup QLV."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    m = rt.customer_lifecycle_summary(year_month="2026-08")["months"][0]

    assert m["doanh_so_khach_moi"] == 100.0            # chi dong TDV cua KH_TDV
    assert m["doanh_so_tang_nhan_vien"] == 170.0       # 100 + 70, khong gom dong QLV


def test_khach_khong_mang_co_khong_bi_thoi_phong_boi_dong_rollup(tmp_path, monkeypatch):
    """Dong QLV de trong ca hai co, nen dem theo DONG thi khach nao cung "khong mang co nao".
    Do that sau khi bo loc tang: 6.344 thay vi 734. Phai dem khach CO co roi tru ra."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    m = rt.customer_lifecycle_summary(year_month="2026-08")["months"][0]

    assert m["khach_khong_mang_co"] == 0
    assert m["khach_moi"] + m["so_is_ro"] + m["khach_khong_mang_co"] == m["tong_khach"]


def test_so_khach_hoat_dong_that_nam_ngay_canh_so_is_ac(tmp_path, monkeypatch):
    """is_ac la co Bravo danh rieng cho CS/TK (28-46 khach/thang tren ~6.900), KHONG phai so khach
    con mua. So dung truoc day nam trong nhanh long invoice_lifecycle_series - du xa de bi doc nham."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))
    conn = sqlite3.connect(local_warehouse.DB_PATH)
    conn.executemany(
        "INSERT INTO vhoadon_otc VALUES ('2026-08-10',?,'SP1',?,1,1,?,1,'D1','2026-08-10','OTC')",
        [("KH_TDV", 100.0, "H1"), ("KH_QLV", 50.0, "H2")])
    conn.commit()
    conn.close()

    m = rt.customer_lifecycle_summary(year_month="2026-08")["months"][0]

    assert m["so_is_ac"] == 0
    assert m["khach_co_hoa_don_trong_thang"] == 2
    assert "KHONG phai so khach dang hoat dong" in m["y_nghia_so_is_ac"]
