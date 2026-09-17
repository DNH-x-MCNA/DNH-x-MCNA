# -*- coding: utf-8 -*-
"""UAT nhat ky 17/09/2026 - C37 va C40 tu tuyen bo GIOI HAN DU LIEU KHONG CO THAT.

C37 noi: "kho chi luu snapshot moi nhat o muc chi tiet theo kenh/mien/tuoi no; cac moc snapshot
lich su cu chi co tong du no & tong qua han (khong tach duoc kenh/mien/co cau tuoi no cho qua khu)".
C40 noi: "khong luu lai xep hang chi tiet theo tung khach hang o cac moc qua khu" va de nghi DNH
"bo sung luu snapshot chi tiet theo khach hang".

CA HAI DEU SAI: bang fact_congno_khachhang_history luu DAY DU tung khach x kenh x vung x 4 nhom
tuoi no tai MOI moc, tu 21/08/2026. Nguyen nhan: receivables_period_compare() chi tra
SUM(balance_end) + SUM(total_overdue), vut bo moi chieu con lai - chatbot tuong do la gioi han cua
DU LIEU chu khong phai cua CONG CU. Bao thieu nang luc minh dang co, va khuyen khach hang di xay
cai da co san, la sai nghiem trong hon mot loi ky thuat.

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
    """)
    rows = [
        # moc CU (01/09): tap trung thap hon, no con tre
        ("2026-09-01", "KH_LON", "Khach Lon", "ETC", "MB", 1000.0, 100.0, 0.0, 0.0, 0.0, 100.0),
        ("2026-09-01", "KH_NHO", "Khach Nho", "OTC", "MN", 500.0, 50.0, 0.0, 0.0, 0.0, 50.0),
        ("2026-09-01", "KH_BA", "Khach Ba", "OTC", "MB", 400.0, 50.0, 0.0, 0.0, 0.0, 50.0),
        # moc MOI (15/09): no gia di (chuyen sang nhom >45) va tap trung vao KH_LON
        ("2026-09-15", "KH_LON", "Khach Lon", "ETC", "MB", 1200.0, 0.0, 0.0, 0.0, 400.0, 400.0),
        ("2026-09-15", "KH_NHO", "Khach Nho", "OTC", "MN", 500.0, 40.0, 0.0, 0.0, 0.0, 40.0),
        ("2026-09-15", "KH_BA", "Khach Ba", "OTC", "MB", 400.0, 60.0, 0.0, 0.0, 0.0, 60.0),
    ]
    conn.executemany(
        "INSERT INTO fact_congno_khachhang_history VALUES (?,'2026-09-15T10:00:00',?,?,?,?,?,?,?,?,?,?)",
        rows)
    conn.commit()
    conn.close()
    return str(path)


def test_lich_su_tra_du_tuoi_no_kenh_vung_va_tung_khach(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_period_compare("2026-09-15", "2026-09-01")

    a = kq["ky_a"]
    assert a["balance_end"] == 2100.0 and a["total_overdue"] == 500.0
    assert a["aging"]["overdue_gt_45"] == 400.0        # co cau tuoi no CO trong lich su
    assert a["aging"]["overdue_1_15"] == 100.0
    assert {c["channel"] for c in a["by_channel"]} == {"ETC", "OTC"}
    assert {r["region"] for r in a["by_region"]} == {"Miền Bắc", "Miền Nam"}
    assert [c["customer_code"] for c in a["top_overdue_customers"]][0] == "KH_LON"
    assert a["so_khach_qua_han"] == 3


def test_tra_loi_duoc_no_gia_di_va_tap_trung_tang_hay_giam(tmp_path, monkeypatch):
    """Dung hai cau C37/C40 tung tu choi: co cau tuoi no dich chuyen ra sao, tap trung tang/giam."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_period_compare("2026-09-15", "2026-09-01")

    # No GIA DI: nhom >45 tang 400, nhom 1-15 giam 100 - tra loi duoc "co cau tuoi no thay doi".
    assert kq["delta_aging"]["overdue_gt_45"] == 400.0
    assert kq["delta_aging"]["overdue_1_15"] == -100.0
    # TAP TRUNG TANG: KH_LON tu 50% len 80% tong qua han.
    assert kq["ky_b"]["tap_trung_no_qua_han"]["top10_share_pct"] == 100.0
    assert kq["delta_tap_trung_diem"]["top10_share_pct"] == 0.0     # chi 3 khach, top10 phu het
    assert kq["ky_a"]["by_channel"]                                  # co chieu kenh de so sanh


def test_cam_noi_lich_su_chi_co_tong(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_period_compare("2026-09-15", "2026-09-01")

    rule = kq["answer_rule"]
    assert "KHONG duoc noi rang lich su chi co tong du no" in rule
    assert "bo sung luu snapshot chi tiet" in rule     # cam khuyen DNH xay cai da co


def test_pham_vi_vung_kenh_van_duoc_giu_tren_cac_chieu_moi(tmp_path, monkeypatch):
    """Cac chieu moi (by_channel/by_region/top khach) dung chung menh de WHERE da loc pham vi -
    tai khoan gioi han vung/kenh KHONG duoc thay du lieu ngoai pham vi qua duong moi mo nay."""
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    chi_mb = rt.receivables_period_compare("2026-09-15", "2026-09-01", scope_area_code="MB")
    chi_otc = rt.receivables_period_compare("2026-09-15", "2026-09-01", scope_channel="OTC")

    # Gioi han MB: khong con KH_NHO (MN) trong top, tong chi con MB.
    assert {c["customer_code"] for c in chi_mb["ky_a"]["top_overdue_customers"]} == {"KH_LON", "KH_BA"}
    assert chi_mb["ky_a"]["balance_end"] == 1600.0
    assert "by_region" not in chi_mb["ky_a"]        # da scope 1 vung, khong tach lai
    # Gioi han OTC: khong con KH_LON (ETC).
    assert {c["channel"] for c in chi_otc["ky_a"]["by_channel"]} == {"OTC"}
    assert all(c["customer_code"] != "KH_LON" for c in chi_otc["ky_a"]["top_overdue_customers"])
    assert chi_otc["ky_a"]["total_overdue"] == 100.0


def test_ngay_khong_co_du_lieu_van_bao_loi_ro_nhu_cu(tmp_path, monkeypatch):
    monkeypatch.setattr(local_warehouse, "DB_PATH", _kho(tmp_path))

    kq = rt.receivables_period_compare("2026-07-31", "2026-09-01")

    assert "Khong co du lieu cong no lich su" in kq["error"]
