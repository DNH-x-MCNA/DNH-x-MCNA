# -*- coding: utf-8 -*-
"""Cham lai UAT 24/09 muc 04: "Danh sach khach phat sinh 3 thang nhung chua dat KPI tai don".

Tieu chi: tra DANH SACH khach KEM LAN MUA GAN NHAT. Tool chi co ro_last_date_bravo (ROLastDate, co the rong,
khong phai ngay mua) nen chatbot tra danh sach khong co ngay mua. Va model doc so_khach_chua_tai_don thanh
"con thieu" -> TDV dat 100% van bi ghi "thieu 3 khach". Du lieu gia."""
import sqlite3

import test_uat_log_1509_khach_kpi as goc


def _kho_co_hoa_don(tmp_path):
    path = goc._kho(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE vhoadon_otc ADD COLUMN customer_code TEXT")
    conn.executemany("INSERT INTO vhoadon_otc (doc_date, customer_code) VALUES (?,?)", [
        ("2026-06-02", "KH_CU"), ("2026-07-19 00:00:00", "KH_CU"),
        ("2026-08-03", "KH_CU"),          # sau thang dang xet (07/2026) - khong duoc tinh
    ])
    conn.commit(); conn.close()
    return path


def test_danh_sach_chua_tai_don_co_lan_mua_gan_nhat_tu_hoa_don(tmp_path, monkeypatch):
    kq = goc._goi(monkeypatch, _kho_co_hoa_don(tmp_path), "get_reorder_pending_customers", scope_role="qlv",
                  scope_area_code="MB", scope_employee_code="QLV1")
    cu = next(row for row in kq["result"]["rows"] if row["customer_code"] == "KH_CU")
    assert cu["lan_mua_gan_nhat"] == "2026-07-19", "Ngay hoa don gan nhat den het thang dang xet."
    assert cu["ro_last_date_bravo"] == "2026-06-05", "Van giu cot Bravo, nhung khong goi la ngay mua."
    assert "lan_mua_gan_nhat" in kq["result"]["definition"]


def test_con_thieu_la_chi_tieu_tru_da_tai_don_khong_phai_so_khach_trong_danh_sach(tmp_path, monkeypatch):
    kq = goc._goi(monkeypatch, _kho_co_hoa_don(tmp_path), "get_reorder_pending_customers", scope_role="qlv",
                  scope_area_code="MB", scope_employee_code="QLV1")
    kpi = {k["employee_code"]: k for k in kq["result"]["kpi_tai_don_theo_nhan_vien"]}
    assert kpi["TDV_MB"]["chi_tieu_khach_tai_don"] == 10 and kpi["TDV_MB"]["khach_da_tai_don"] == 5
    assert kpi["TDV_MB"]["con_thieu_de_dat_chi_tieu"] == 5
    assert kpi["TDV_MB"]["so_khach_chua_tai_don"] != kpi["TDV_MB"]["con_thieu_de_dat_chi_tieu"]


def test_kho_cu_khong_co_cot_ma_khach_tren_hoa_don_van_chay(tmp_path, monkeypatch):
    kq = goc._goi(monkeypatch, goc._kho(tmp_path), "get_reorder_pending_customers", scope_role="qlv",
                  scope_area_code="MB", scope_employee_code="QLV1")
    assert all(row["lan_mua_gan_nhat"] is None for row in kq["result"]["rows"])
