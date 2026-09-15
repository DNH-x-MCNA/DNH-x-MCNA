# -*- coding: utf-8 -*-
"""Hàm phân tích thuần của scripts/nghien_cuu_insight.py — dữ liệu giả, không Bravo."""
import datetime as dt

from scripts import nghien_cuu_insight as nc

D = dt.date


def _no(b31_45=0.0, gt45=0.0, area="MB"):
    return {"area": area, "balance": b31_45 + gt45, "b31_45": b31_45, "gt45": gt45}


def test_quantile_noi_suy():
    assert nc.quantile([1, 2, 3, 4, 5], 0.5) == 3
    assert nc.quantile([0, 10], 0.9) == 9
    assert nc.quantile([], 0.9) is None


def test_khach_moi_do_chinh_xac_va_ty_le_nen():
    don = {
        "CU": [(D(2022, 8, 1), 1e6), (D(2023, 9, 1), 1e6)],       # đơn đầu trước mốc 1 năm: không phải khách mới
        "MUA_LAI": [(D(2024, 1, 1), 10e6), (D(2024, 1, 20), 5e6)],  # mua lại trong 30 ngày: không bắn
        "MAT": [(D(2024, 1, 1), 30e6)],                             # không bao giờ quay lại
        "VE_MUON": [(D(2024, 1, 1), 2e6), (D(2024, 3, 1), 2e6)],     # bắn ở ngày 30, quay lại sau đó
    }
    kq = nc.phan_tich_khach_moi(don, {"MAT": "nam"}, D(2026, 9, 1), "2022-07-01",
                                k_list=(30,), horizon=90, min_don_dau_list=(0.0, 5e6))

    tat_ca = kq[0]
    assert (tat_ca["tong_khach_moi"], tat_ca["so_lan_ban"]) == (3, 2)
    assert (tat_ca["do_chinh_xac_pct"], tat_ca["ty_le_nen_mat_pct"], tat_ca["tu_quay_lai_pct"]) == (50.0, 33.3, 50.0)
    lon = kq[1]                                                     # đơn đầu >= 5tr: bỏ VE_MUON
    assert (lon["tong_khach_moi"], lon["so_lan_ban"], lon["do_chinh_xac_pct"]) == (2, 1, 100.0)
    assert lon["gia_tri_don_dau_khach_mat"] == 30e6


def test_sku_chu_luc_chi_ban_khi_khach_van_mua_nhung_bo_sku():
    M = (2026, 3)
    truoc = [nc.month_add(2026, 3, -i) for i in range(1, 7)]
    rows = []
    for item in ("DEU", "BO", "TAM"):
        rows += [("K", item, p, 20e6, 10e6) for p in truoc]
    rows += [("K", "DEU", M, 20e6, 10e6), ("K", "DEU", (2026, 4), 20e6, 10e6)]   # vẫn mua
    rows += [("K", "TAM", M, 20e6, 0.0)]                                          # tới ngày 20 chưa lấy, cuối tháng lấy
    # "BO": không có dòng tháng 3, 4 -> bỏ thật
    rows += [("IM", "X", p, 20e6, 10e6) for p in truoc]                           # khách không mua gì tháng 3
    upto20 = {("K", M): 10e6}

    kq = nc.phan_tich_sku_chu_luc(rows, upto20, [M], min_tb=10e6)

    assert kq["so_cap_danh_gia"] == 3                                             # IM bị loại (khách không hoạt động)
    assert (kq["so_lan_ban"], kq["do_chinh_xac_pct"], kq["ty_le_nen_bo_pct"]) == (2, 50.0, 33.3)


def test_do_phu_doi_tach_doi_da_yeu_va_doi_dang_tot():
    thang = [(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)]
    ns, kn = [], []
    for ym in thang:
        for doi, dat_thang_4, dat_thang_5 in (("GIAM", 0.9, 0.6), ("ON", 0.9, 0.9)):
            dat = dat_thang_5 if ym == (2026, 5) else dat_thang_4
            ns.append((ym, doi, None, None, 100.0, 100.0 * dat))
            for i in range(3):
                ns.append((ym, f"{doi}{i}", f"{doi}D{i}", doi, 10.0, 5.0))
            so_khach = 5 if (doi == "GIAM" and ym == (2026, 4)) else 10
            for i in range(so_khach):
                kn.append((ym, f"{doi}D0", f"{doi}C{i}"))

    kq = nc.phan_tich_do_phu_doi(ns, kn, [(2026, 4)], nguong_giam=(0.2,))[0]

    assert kq["so_doi_thang"] == 2 and kq["ty_le_nen_duoi_80_pct"] == 50.0
    assert (kq["so_lan_ban"], kq["do_chinh_xac_pct"]) == (1, 100.0)
    assert kq["khi_thang_nay_tren_80"]["ban"] == 1


def test_so_sanh_team_pace_dung_cung_ket_cuc_rollup_va_cung_tap_doi():
    facts = []
    for team, customers, rollup_customer, rollup_target, rollup_actual in (
        ("Q1", ("A", "B", "C"), "R", 400.0, 360.0),
        ("Q2", ("D", "E", "F"), "S", 300.0, 150.0),
    ):
        for customer in customers:
            facts.append(((2026, 7), customer, "TDV", team, "MB", 100.0,
                          customer, 60.0 if team == "Q1" else 30.0))
        facts.append(((2026, 7), team, "QLV", "", "MB", rollup_target,
                      rollup_customer, rollup_actual))

    daily = []
    for month in (4, 5, 6):
        daily += [("HIST", D(2026, month, 10), 50.0),
                  ("HIST", D(2026, month, 25), 50.0)]
    for customer in ("A", "B", "C"):
        daily += [(customer, D(2026, 7, 10), 10.0),
                  (customer, D(2026, 7, 25), 50.0)]
    for customer in ("D", "E", "F"):
        daily += [(customer, D(2026, 7, 10), 5.0),
                  (customer, D(2026, 7, 25), 25.0)]
    daily += [("R", D(2026, 7, 10), 120.0), ("R", D(2026, 7, 25), 240.0),
              ("S", D(2026, 7, 10), 30.0), ("S", D(2026, 7, 25), 120.0)]

    result = nc.phan_tich_du_phong_doi(facts, daily, [(2026, 7)], ngay_list=(15,))

    day15 = result["theo_ngay"][0]
    assert (day15["so_doi_thang"], day15["ty_le_nen_pct"]) == (2, 50.0)
    assert (day15["tdv"]["so_lan_ban"], day15["tdv"]["do_chinh_xac_pct"]) == (2, 50.0)
    assert (day15["rollup"]["so_lan_ban"], day15["rollup"]["do_chinh_xac_pct"]) == (1, 100.0)


def test_chi_tieu_bao_khong_the_dat_khi_ban_o_nhip_cao_nhat_van_thieu():
    doanh_thu = {}
    for y, m in [(2025, i) for i in range(1, 13)]:
        doanh_thu[D(y, m, 5)] = 20.0
        doanh_thu[D(y, m, 25)] = 80.0                                # lịch sử: 80% doanh thu sau ngày 10
    doanh_thu[D(2026, 1, 5)] = 20.0
    doanh_thu[D(2026, 1, 25)] = 80.0
    chi_tieu = {(2026, 1): 300.0}                                    # tối đa ~100 << 300

    kq = nc.phan_tich_chi_tieu(doanh_thu, chi_tieu, D(2026, 1, 31), ngay_list=(10,), min_hist=6)

    n10 = kq["theo_ngay"][0]
    assert (n10["so_thang"], n10["ban_100"], n10["do_chinh_xac_100_pct"], n10["do_phu_100_pct"]) == (1, 1, 100.0, 100.0)
    assert kq["cac_lan_ban_100"][0]["thang"] == "2026-01"


def test_hop_dong_thuc_hien_thap_bu_kip_va_hop_dong_moi():
    hd = {
        "THAP": {"cc": "BV", "tu": "2024-01-01", "den": "2024-12-31", "gia_tri": 1000e6, "lech": False},
        "BU_KIP": {"cc": "BV2", "tu": "2024-01-01", "den": "2024-12-31", "gia_tri": 1000e6, "lech": False},
        "LECH": {"cc": "BV3", "tu": "2024-01-01", "den": "2024-12-31", "gia_tri": 1000e6, "lech": True},
        "MOI": {"cc": "BV", "tu": "2025-01-05", "den": "2025-12-31", "gia_tri": 500e6, "lech": False},
    }
    hoa_don = {"THAP": [(D(2024, 3, 1), 200e6)],
               "BU_KIP": [(D(2024, 3, 1), 200e6), (D(2024, 12, 1), 700e6)]}

    kq = nc.phan_tich_hop_dong(hd, hoa_don, D(2025, 6, 30), moc_ngay=(60,), nguong_con_lai=(1.0,))[0]

    assert (kq["so_hop_dong"], kq["so_lan_ban"], kq["do_chinh_xac_pct"]) == (2, 2, 50.0)
    assert kq["thap_nhung_co_hop_dong_moi_pct"] == 100.0
    assert kq["gia_tri_con_lai_khong_thuc_hien"] == 800e6


def test_mondays_lay_dung_thu_hai():
    assert nc.mondays("2026-09-02", "2026-09-21") == [D(2026, 9, 7), D(2026, 9, 14), D(2026, 9, 21)]


def test_no_sap_45_do_chinh_xac_ty_le_nen_va_do_phu():
    d0, d1, d2, d3 = D(2026, 8, 3), D(2026, 8, 10), D(2026, 8, 17), D(2026, 8, 24)
    snaps = {
        d0: {("A", "ETC"): _no(b31_45=80e6),              # lớn, sẽ trượt hết sang >45
             ("B", "ETC"): _no(b31_45=60e6),              # lớn, sẽ trả
             ("C", "OTC"): _no(b31_45=5e6),               # nhỏ, trượt - chỉ vào tỷ lệ nền
             ("D", "ETC"): _no(b31_45=90e6, gt45=10e6)},  # đã có nợ >45: không bắn
        d1: {("A", "ETC"): _no(), ("B", "ETC"): _no(), ("C", "OTC"): _no(), ("D", "ETC"): _no(gt45=10e6)},
        d2: {("A", "ETC"): _no(gt45=80e6), ("C", "OTC"): _no(gt45=5e6), ("D", "ETC"): _no(gt45=100e6)},
        d3: {("A", "ETC"): _no(gt45=80e6)},
    }

    kq = nc.phan_tich_no_sap_45(snaps, nguong_list=(50e6,), buoc_ngay=14, nguong_su_kien=50e6)

    etc = next(r for r in kq["quy_tac"] if r["kenh"] == "ETC")
    assert (etc["so_lan_ban"], etc["do_chinh_xac_pct"]) == (2, 50.0)     # A trượt, B trả; D bị loại
    assert etc["ty_le_nen_pct"] == 66.7                                  # A, D trượt / A, B, D
    assert etc["gia_tri_da_truot"] == 80e6
    # Sự kiện nợ >45 mới tại d2: A (tuần trước 0) - đã báo từ d0; D có >45 từ trước nên không phải sự kiện.
    assert (etc["su_kien_no_45_moi"], etc["do_phu_pct"]) == (1, 100.0)
    assert kq["nen"]["OTC"] == {"so": 1, "ty_le_truot_pct": 100.0}
    assert not [r for r in kq["quy_tac"] if r["kenh"] == "OTC"]           # 5tr dưới ngưỡng
    assert kq["so_tuan_danh_gia"] == 2                                   # d0->d2, d1->d3
