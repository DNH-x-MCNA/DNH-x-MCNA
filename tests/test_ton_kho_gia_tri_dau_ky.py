# -*- coding: utf-8 -*-
"""Sau ban sua 17/09/2026 (sync_tonkho_hien_tai): SO LUONG ton kho da la so HIEN TAI, nhung GIA TRI
thi KHONG - view nguon vTheKhoLot chi co cot so luong nhap/xuat, khong co cot tien, nen cac dong
bien dong de amount rong.

Kiem chung tren may 24 ngay 17/09/2026 sau khi chay sync: so luong doi han (kho SX 202,3 trieu ->
165,1 trieu don vi, giam 18%) trong khi gia tri van y nguyen 175,43 ty nhu truoc khi sua. Ghep hai
cot do lai se ra mot cau tra loi nghe rat tron nhung sai: "gia tri ton kho hien tai 175 ty" that ra
la gia tri dau nam, va don gia suy ra tu phep chia cung sai theo.

Du lieu gia, khong cham Bravo."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


def _kho(tmp_path, co_bien_dong: bool):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brvsx_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        CREATE TABLE brv_tonkhodk (warehouse_id INTEGER, item_id INTEGER, quantity REAL,
            amount REAL, is_active INTEGER, fiscal_year INTEGER);
        CREATE TABLE brvsx_tonkhodk (branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            quantity REAL, amount REAL, is_active INTEGER, year INTEGER);
    """)
    conn.execute("INSERT INTO brv_kho VALUES (10,'B02','B02','Kho MB')")
    conn.execute("INSERT INTO brvsx_kho VALUES (90,'A01','A01','Kho SX')")
    # Ton dau nam: co CA so luong lan gia tri.
    conn.execute("INSERT INTO brv_tonkhodk VALUES (10, 500, 100.0, 5000.0, 1, 2026)")
    conn.execute("INSERT INTO brvsx_tonkhodk VALUES ('A01', 90, 700, 200.0, 9000.0, 1, 2026)")
    if co_bien_dong:
        # Dong bien dong do sync_tonkho_hien_tai chen: CO so luong, KHONG co gia tri.
        conn.execute("INSERT INTO brv_tonkhodk VALUES (10, 500, 40.0, NULL, 1, 2026)")
        conn.execute("INSERT INTO brvsx_tonkhodk VALUES ('A01', 90, 700, -50.0, NULL, 1, 2026)")
    conn.commit()
    conn.close()
    return str(path)


def test_co_bien_dong_thi_canh_bao_gia_tri_chi_la_dau_nam(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, co_bien_dong=True))

    rows = rt.inventory_by_region()

    kd = next(r for r in rows if r["he_thong"] == "KINH_DOANH")
    sx = next(r for r in rows if r["he_thong"] == "SAN_XUAT")
    # So luong la HIEN TAI (da cong bien dong), gia tri van la dau nam.
    assert kd["tong_so_luong"] == 140.0 and kd["tong_gia_tri"] == 5000.0
    assert sx["tong_so_luong"] == 150.0 and sx["tong_gia_tri"] == 9000.0
    for r in (kd, sx):
        assert r["gia_tri_moc_thoi_gian"] == "DAU_NAM"
        assert "KHONG" in r["canh_bao_gia_tri"]
        assert "don gia" in r["canh_bao_gia_tri"]


def test_chua_chay_sync_moi_thi_khong_gan_canh_bao_thua(tmp_path, monkeypatch):
    """Kho chua co dong bien dong nao (chua chay ban sync moi): gia tri va so luong VAN cung mot
    moc dau nam - khong duoc bao dong gia."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path, co_bien_dong=False))

    rows = rt.inventory_by_region()

    for r in rows:
        assert "canh_bao_gia_tri" not in r
        assert "gia_tri_moc_thoi_gian" not in r
