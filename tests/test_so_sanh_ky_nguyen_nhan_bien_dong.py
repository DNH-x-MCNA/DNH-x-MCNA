"""Hop tien do 24/09/2026: chatbot phai giai thich nguyen nhan tang/giam doanh thu (khach moi nao, SKU nao ban
them...) chu khong chi dua ra con so so sanh. compare_periods tra kem nguyen_nhan_bien_dong. Du lieu gia."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402


def _kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE vhoadon_otc (customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
                                  unit_price REAL, doc_date TEXT, employee_code TEXT, stt TEXT);
        CREATE TABLE vhoadon_etc (customer_code TEXT, item_code TEXT, amount9 REAL, quantity REAL,
                                  unit_price REAL, doc_date TEXT, employee_code TEXT, stt TEXT);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dmssx_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT, city_name TEXT);
        INSERT INTO dim_tinhthanhpho VALUES (1,'MB','Ha Noi'),(2,'MN','HCM');
        INSERT INTO dms_khachhang VALUES ('KB','Nha thuoc Bac',1),('KN','Nha thuoc Nam',2),('KMOI','Khach moi',2);
        INSERT INTO brv_sanpham VALUES ('SP1','Siro ho'),('SP2','Vien ngam');
    """)
    c.executemany("INSERT INTO vhoadon_otc VALUES (?,?,?,1,?,?, 'T','s')", [
        # ky B (07/2026)
        ("KB", "SP1", 100, 100, "2026-07-05"), ("KN", "SP2", 80, 80, "2026-07-06"), ("KMAT", "SP2", 30, 30, "2026-07-07"),
        # ky A (08/2026)
        ("KB", "SP1", 250, 250, "2026-08-05"), ("KN", "SP2", 40, 40, "2026-08-06"), ("KMOI", "SP1", 60, 60, "2026-08-07"),
    ])
    c.commit(); c.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2026-01-01")
    monkeypatch.setattr(rt, "revenue_by_channel", lambda df, dt_, *a, **k: {
        "total": {"revenue": {"2026-08": 350.0, "2026-07": 210.0}[df[:7]]}, "data_coverage": {"complete": True}})


def test_chenh_lech_duoc_tach_thanh_mien_khach_va_sku_khop_tong(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    kq = rt.compare_periods("2026-08-01", "2026-08-31", "2026-07-01", "2026-07-31")
    n = kq["nguyen_nhan_bien_dong"]
    assert kq["delta"] == 140 and n["chenh_lech_tren_hoa_don_chi_tiet"] == 140 and n["khop_voi_chenh_lech_tong"]
    # KMAT khong co trong danh muc va tien to khong suy duoc mien -> "Khac", khong bi gan bua.
    assert {m: v["chenh_lech"] for m, v in n["theo_mien"].items()} == {"Khac": -30, "MB": 150, "MN": 20}
    assert [x["customer_code"] for x in n["khach_tang_manh_nhat"]] == ["KB", "KMOI"]
    assert n["khach_tang_manh_nhat"][0]["ten"] == "Nha thuoc Bac"
    assert [x["customer_code"] for x in n["khach_giam_manh_nhat"]] == ["KN", "KMAT"]
    assert n["khach_phat_sinh_moi_so_voi_ky_b"] == {"so_khach": 1, "doanh_thu": 60}
    assert n["khach_khong_con_mua_so_voi_ky_b"] == {"so_khach": 1, "doanh_thu_ky_b": 30}
    assert [(x["item_code"], x["chenh_lech"]) for x in n["sku_tang_manh_nhat"]] == [("SP1", 210)]
    assert [(x["item_code"], x["chenh_lech"]) for x in n["sku_giam_manh_nhat"]] == [("SP2", -70)]
    assert n["sku_tang_manh_nhat"][0]["ten"] == "Siro ho"


def test_ky_ngoai_cua_so_chi_tiet_thi_noi_ro_khong_tach_duoc(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2026-08-01")
    n = rt.compare_periods("2026-08-01", "2026-08-31", "2026-07-01", "2026-07-31")["nguyen_nhan_bien_dong"]
    assert n["status"] == "NGOAI_CUA_SO_CHI_TIET"


def test_mo_ta_tool_bat_giai_thich_nguyen_nhan():
    mo_ta = {t["name"]: t["description"] for t in nl2sql.TEMPLATE_TOOLS}["compare_periods"]
    assert "nguyen_nhan_bien_dong" in mo_ta and "BAT BUOC giai thich" in mo_ta
