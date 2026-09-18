# -*- coding: utf-8 -*-
"""18/09/2026 - cau C42: "he thong danh dau 11 SKU [nguy co thieu hang], nhung toi chua lay duoc
danh sach chi tiet cu the (cong cu chi tra ve mau cua nhom ton cao/cham luan chuyen)".

Chatbot noi dung: no doc duoc so dem trong status_counts nhung trong rows khong co lay MOT dong
nao mang trang thai do. _inventory_supply_risk() sap xep theo uu tien cua focus roi cat thang theo
limit, nen nhom nao bi focus day xuong duoi co the bi cat sach. Do that tren kho 18/09 voi
focus='overstock', limit=30: 55 SKU can xu ly (16 thieu hang / 28 cham luan chuyen / 11 ton khong
ban) - 30 dong tra ve gom 11 ton khong ban + 19 cham luan chuyen, KHONG co dong thieu hang nao.

Day la lop loi thu tu trong chuoi "danh sach bi cat nhung khong ai noi ra": sau "hoi top 10 tra top
3" (cong no), "50 hop dong" (ETC), "20 khach" (rui ro khach hang). Khac ba lan truoc o cho lan nay
so dem CO san va dung - cai thieu la BANG CHUNG, nen model buoc phai tu thu nhan la khong lay duoc.

Du lieu gia, khong cham Bravo."""
import datetime as real_dt
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


class _NgayCoDinh(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 28)


# 3 thang hoan tat gan nhat tinh tu 28/08 la T5-T7/2026.
_THANG_BAN = ("2026-05-10", "2026-06-10", "2026-07-10")


def _kho(tmp_path):
    """28 SKU cho xu ly, chia ba nhom - nhieu hon limit de bat buoc phai cat."""
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_tonkhodklot (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            item_lot_code TEXT, quantity REAL, is_active INTEGER);
        CREATE TABLE brv_lot (item_lot_code TEXT, item_id INTEGER, mfg_date TEXT,
            expiry_date TEXT, is_active INTEGER);
        CREATE TABLE brv_sanpham (code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER);
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT, amount9 REAL,
            quantity REAL, unit_price REAL, employee_code TEXT);
        CREATE TABLE dms_khachhang (code TEXT, name TEXT, city_id INTEGER);
        CREATE TABLE dim_tinhthanhpho (city_id INTEGER, area_code TEXT);
    """)
    conn.execute("INSERT INTO brv_kho VALUES (2,'B02','KMB','Kho Mien Bac')")
    conn.execute("INSERT INTO dim_tinhthanhpho VALUES (1,'MB')")
    conn.execute("INSERT INTO dms_khachhang VALUES ('KH1','Khach Mien Bac',1)")

    ma_id = 0

    def sku(ma, ten, ton, ban_thang):
        nonlocal ma_id
        ma_id += 1
        conn.execute("INSERT INTO brv_sanpham VALUES (?,?,'G','hop',?)", (ma, ten, ma_id))
        conn.execute("INSERT INTO brv_tonkhodklot VALUES ('B02',2,?,?,?,1)",
                     (ma_id, f"LO-{ma}", ton))
        for ngay in _THANG_BAN:
            if ban_thang:
                conn.execute("INSERT INTO vhoadon_otc VALUES (?,'KH1',?,?,?,10,'DMS01')",
                             (ngay, ma, ban_thang * 10.0, ban_thang))

    # Nhom 1: ton nhung 3 thang khong ban duoc dong nao -> TON_KHONG_BAN_3_THANG.
    for i in range(12):
        sku(f"DUNG{i:02d}", f"San pham nam im {i}", ton=5_000, ban_thang=0)
    # Nhom 2: ban 100/thang, ton 700 -> so thang du hang = 7 > 6 -> CHAM_LUAN_CHUYEN.
    for i in range(12):
        sku(f"CHAM{i:02d}", f"San pham cham {i}", ton=700, ban_thang=100)
    # Nhom 3: ban 30/thang, ton 10 -> ton < binh quan thang -> CO_NGUY_CO_THIEU_HANG.
    for i in range(4):
        sku(f"THIEU{i:02d}", f"San pham sap het {i}", ton=10, ban_thang=30)
    conn.commit()
    conn.close()
    return str(path)


def _canh_bao(tmp_path, monkeypatch, focus, limit=10):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))
    monkeypatch.setattr(rt.dt, "date", _NgayCoDinh)
    monkeypatch.setattr(rt, "get_sync_meta", lambda _t: (None, None, None))
    return rt.inventory_expiry_report(scope_area_code="MB", focus=focus, limit=limit)["supply_risk"]


def _dem_theo_trang_thai(rows):
    out = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def test_nhom_bi_focus_day_xuong_van_co_dong_trong_ket_qua(tmp_path, monkeypatch):
    """focus='overstock' xep ton cao len dau. Ban cu: 10 dong deu la ton khong ban, nhom thieu hang
    bien mat sach du status_counts van bao co 4."""
    kq = _canh_bao(tmp_path, monkeypatch, focus="overstock", limit=10)

    assert kq["status_counts"]["CO_NGUY_CO_THIEU_HANG_DERIVED"] == 4
    hien = _dem_theo_trang_thai(kq["rows"])
    assert hien.get("CO_NGUY_CO_THIEU_HANG_DERIVED", 0) >= 3
    # Va khong nhom nao bien mat hoan toan.
    for trang_thai, so_dem in kq["status_counts"].items():
        if so_dem:
            assert hien.get(trang_thai, 0) >= 1, trang_thai


def test_focus_nguoc_lai_cung_khong_lam_mat_nhom_nao(tmp_path, monkeypatch):
    kq = _canh_bao(tmp_path, monkeypatch, focus="shortage", limit=10)

    hien = _dem_theo_trang_thai(kq["rows"])
    for trang_thai, so_dem in kq["status_counts"].items():
        if so_dem:
            assert hien.get(trang_thai, 0) >= 1, trang_thai


def test_focus_van_giu_quyen_uu_tien_cho_nhom_chinh(tmp_path, monkeypatch):
    """Han ngach la de khong mat nhom, KHONG duoc lam focus mat tac dung: nhom duoc focus phai
    chiem nhieu dong nhat."""
    kq = _canh_bao(tmp_path, monkeypatch, focus="shortage", limit=10)

    hien = _dem_theo_trang_thai(kq["rows"])
    assert hien["CO_NGUY_CO_THIEU_HANG_DERIVED"] == 4      # lay het ca 4 SKU thieu hang
    assert hien["CO_NGUY_CO_THIEU_HANG_DERIVED"] >= max(
        v for k, v in hien.items() if k != "CO_NGUY_CO_THIEU_HANG_DERIVED")


def test_noi_ro_con_bao_nhieu_dong_chua_hien_theo_tung_nhom(tmp_path, monkeypatch):
    kq = _canh_bao(tmp_path, monkeypatch, focus="overstock", limit=10)

    con_lai = kq["so_dong_chua_hien_theo_trang_thai"]
    hien = _dem_theo_trang_thai(kq["rows"])
    for trang_thai, so_dem in kq["status_counts"].items():
        assert hien.get(trang_thai, 0) + con_lai.get(trang_thai, 0) == so_dem
    assert kq["so_dong_da_hien"] == len(kq["rows"]) == 10
    assert "khong noi la khong lay duoc danh sach" in kq["answer_rule"]


def test_du_cho_thi_khong_cat_va_khong_bao_con_du(tmp_path, monkeypatch):
    """limit rong hon tong so dong: phai tra HET, va so_dong_chua_hien phai rong."""
    kq = _canh_bao(tmp_path, monkeypatch, focus="all", limit=50)

    assert len(kq["rows"]) == kq["total_actionable_skus"] == 28
    assert kq["so_dong_chua_hien_theo_trang_thai"] == {}
