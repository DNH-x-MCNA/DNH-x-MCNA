# -*- coding: utf-8 -*-
"""23/09/2026 - UAT v21 "Khach im lang 30/60/90 ngay".

Nguoi cham doi chieu bang chatbot voi checker S69c va bao "mot so khach lech doanh thu ky nhin lai
va san pham mua nhieu nhat". Truy nguyen ra HAI ky bi dat sai, doc lap nhau:

1. DOANH THU. Tool lay _month_add(as_of[:7], -(N-1)) + '-01', tuc moc DAU THANG LICH: hoi ngay
   23/09 thi ky bat dau 01/04. Checker dung DATEADD(month,-6,GETDATE()) = 23/03. Chenh dung phan
   doanh thu 23-31/03. Do tren kho ngay 23/09: 10/10 khach khop tuyet doi checker voi moc 23/03,
   7/10 khop so chatbot cu voi moc 01/04 (vd QNG00418 74,1 vs 6,4 trieu - chenh 67,8 trieu chi vi
   9 ngay cuoi thang 3).

2. SAN PHAM. Tool dung LAI chinh base 6 thang cua doanh thu, con checker lay 12 thang
   (DATEADD(month,-12,@MonthStart)). Hai ky khac han nen top SKU khac. Ca sach nhat la BDI00361:
   doanh thu giong het checker (5,5 trieu) ma san pham van khac - chung minh day la loi RIENG cua
   ky san pham, khong phai he qua cua loi ky doanh thu.

Cot "SP mua nhieu nhat" khong ghi ky nao ca, nen ky san pham duoc tra ra thanh truong rieng.
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

AS_OF = "2026-09-23"


def _make_db(path):
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
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, city_name TEXT, area_code TEXT);
        CREATE TABLE monthly_customer_summary (year_month TEXT, channel TEXT, customer_code TEXT,
            employee_code TEXT, revenue REAL, invoice_count INTEGER);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code TEXT);
        """
    )
    conn.executemany("INSERT INTO brv_sanpham VALUES (?,?,NULL,NULL,NULL)", [
        ("SP_CU", "San pham mua nhieu tu nam ngoai"),
        ("SP_MOI", "San pham moi mua gan day"),
    ])

    def ban(ngay, khach, sku, tien, stt):
        conn.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,1,?,?,1,'D1',?,'A')",
                     (ngay, khach, sku, tien, tien, stt, ngay))

    # KHDUOI3: co mua trong 23-31/03 - dung phan ma moc dau thang lich lam roi mat.
    ban("2026-03-25", "KHDUOI3", "SP_MOI", 50_000_000, "H1")
    ban("2026-05-10", "KHDUOI3", "SP_MOI", 10_000_000, "H2")

    # KHTRUOC3: chi mua TRUOC 23/03 - moc moi khong duoc keo them phan nay vao.
    ban("2026-03-10", "KHTRUOC3", "SP_MOI", 30_000_000, "H3")
    ban("2026-06-01", "KHTRUOC3", "SP_MOI", 5_000_000, "H4")

    # KHBIEN: mua DUNG ngay bien 23/03 - BETWEEN phai tinh ca ngay nay.
    ban("2026-03-23", "KHBIEN", "SP_MOI", 7_000_000, "H5")
    ban("2026-06-02", "KHBIEN", "SP_MOI", 1_000_000, "H6")

    # KHSANPHAM: mo phong BDI00361 - doanh thu ky nhin lai KHONG doi, chi san pham doi.
    # SP_CU mua 10/2025 (trong ky san pham 12 thang, ngoai ky doanh thu 6 thang).
    ban("2025-10-01", "KHSANPHAM", "SP_CU", 100_000_000, "H7")
    ban("2026-05-01", "KHSANPHAM", "SP_MOI", 20_000_000, "H8")

    conn.commit()
    conn.close()


def _kho(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    return str(db_path)


def _goi(**kwargs):
    tham_so = dict(as_of_date=AS_OF, silent_days=30, lookback_months=6, limit=200)
    tham_so.update(kwargs)
    r = rt.customers_silent(**tham_so)
    return r, {k["customer_code"]: k for k in r["khach_im_lang"]}


def test_ky_nhin_lai_lui_dung_6_thang_tu_as_of(tmp_path, monkeypatch):
    """23/09 lui 6 thang = 23/03, khong phai 01/04."""
    _kho(tmp_path, monkeypatch)

    r, _ = _goi()

    assert r["ky_nhin_lai"] == {"tu": "2026-03-23", "den": AS_OF}


def test_doanh_thu_gom_ca_phan_duoi_thang_3(tmp_path, monkeypatch):
    """LOI GOC UAT v21: moc dau thang lich lam roi doanh thu 23-31/03."""
    _kho(tmp_path, monkeypatch)

    _, theo_ma = _goi()

    assert theo_ma["KHDUOI3"]["doanh_thu_ky_nhin_lai"] == 60_000_000, (
        "phan ban 25/03 bi roi - dung loi nguoi cham bao o v21")


def test_khong_keo_them_phan_truoc_moc(tmp_path, monkeypatch):
    """Nan ky cho khop checker KHONG duoc thanh noi rong ky vo toi han."""
    _kho(tmp_path, monkeypatch)

    _, theo_ma = _goi()

    assert theo_ma["KHTRUOC3"]["doanh_thu_ky_nhin_lai"] == 5_000_000, (
        "hoa don 10/03 nam TRUOC moc 23/03, khong duoc tinh")


def test_ngay_bien_23_03_duoc_tinh(tmp_path, monkeypatch):
    """Checker dung >= DATEADD(...), nen dung ngay bien phai duoc tinh."""
    _kho(tmp_path, monkeypatch)

    _, theo_ma = _goi()

    assert theo_ma["KHBIEN"]["doanh_thu_ky_nhin_lai"] == 8_000_000


def test_ky_san_pham_la_12_thang_rieng(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)

    r, _ = _goi()

    assert r["ky_san_pham"] == {"tu": "2025-09-01", "den": AS_OF}
    assert r["ky_san_pham"]["tu"] < r["ky_nhin_lai"]["tu"], "ky san pham phai rong hon"


def test_san_pham_lay_theo_ky_12_thang_du_doanh_thu_khong_doi(tmp_path, monkeypatch):
    """Ca BDI00361: doanh thu ky nhin lai giong het checker ma san pham van khac.

    SP_CU mua 10/2025 (100tr) nam NGOAI ky doanh thu 6 thang nhung TRONG ky san pham 12 thang, nen
    no moi la san pham mua nhieu nhat - dung nhu checker. Dung chung mot ky se ra SP_MOI.
    """
    _kho(tmp_path, monkeypatch)

    _, theo_ma = _goi()
    kh = theo_ma["KHSANPHAM"]

    assert kh["doanh_thu_ky_nhin_lai"] == 20_000_000, "doanh thu chi tinh trong ky nhin lai 6 thang"
    sp = kh["san_pham_mua_nhieu_nhat"]
    assert sp["item_code"] == "SP_CU", "san pham phai lay theo ky 12 thang, khong phai 6 thang"
    assert sp["item_name"] == "San pham mua nhieu tu nam ngoai"
    assert sp["revenue_trong_ky_san_pham"] == 100_000_000
    assert sp["ky"] == {"tu": "2025-09-01", "den": AS_OF}


def test_ghi_chu_noi_ro_hai_ky_khac_nhau(tmp_path, monkeypatch):
    """Cot "SP mua nhieu nhat" khong ghi ky, nen payload phai bat model noi ro."""
    _kho(tmp_path, monkeypatch)

    r, _ = _goi()

    assert "ky_san_pham" in r["ghi_chu"]
    assert "KHAC ky_nhin_lai" in r["ghi_chu"]


def test_scope_kenh_van_ap_cho_ky_san_pham(tmp_path, monkeypatch):
    """Ky san pham dung base RIENG - phai ep scope y het base doanh thu, khong duoc query tho."""
    _kho(tmp_path, monkeypatch)

    r, theo_ma = _goi(scope_channel="ETC")

    assert theo_ma == {}, "kho chi co hoa don OTC nen scope ETC phai ra rong"
    assert r["so_khach"] == 0


def test_lui_thang_ket_ngay_khi_thang_dich_ngan_hon(tmp_path, monkeypatch):
    """DATEADD(month,-1,'2026-03-31') cua SQL Server ra 28/02; helper phai ket ngay y het,
    neu khong thi ky se truot sang 03/03 va lai lech voi checker."""
    assert rt._lui_thang_giu_ngay("2026-03-31", 1) == "2026-02-28"
    assert rt._lui_thang_giu_ngay("2026-09-23", 6) == "2026-03-23"
    assert rt._lui_thang_giu_ngay("2026-01-15", 12) == "2025-01-15"


def test_theo_nguong_30_60_90_mot_lan_khop_goi_rieng(tmp_path, monkeypatch):
    # 26/09/2026 (may 24 23/09): "Khach im lang 30/60/90 ngay" -> model goi tool 3 lan. theo_nguong phai khop tung lan goi
    # rieng va tinh tren toan bo tap (khong bi limit).
    db_path = tmp_path / "warehouse.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,?,'SP_MOI',?,1,1,?,1,'NV1',?,NULL)", [
        ("2026-08-14", "KH_40_NGAY", 7_000_000, "S40", "2026-08-14"),   # im lang 40 ngay: chi >=30
        ("2026-07-15", "KH_70_NGAY", 5_000_000, "S70", "2026-07-15"),   # im lang 70 ngay: >=30 va >=60
    ])
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    r = rt.customers_silent(as_of_date=AS_OF, silent_days=30, limit=1)
    bang = {x["nguong_ngay"]: x for x in r["theo_nguong"]}
    assert set(bang) >= {30, 60, 90, 180}
    for n in (30, 60, 90):
        rieng = rt.customers_silent(as_of_date=AS_OF, silent_days=n, limit=200)
        assert bang[n]["so_khach"] == rieng["total_count"]
        assert abs(bang[n]["doanh_thu_ky_nhin_lai"] - sum(k["doanh_thu_ky_nhin_lai"] for k in rieng["khach_im_lang"])) < 1
    assert (bang[30]["so_khach"], bang[60]["so_khach"], bang[90]["so_khach"]) == (6, 5, 4), "Tich luy theo nguong."
