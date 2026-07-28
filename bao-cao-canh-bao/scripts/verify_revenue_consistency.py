# -*- coding: utf-8 -*-
"""
Kiểm tra tự động: các cách tính doanh thu khác nhau (tổng công ty, tổng theo vùng, tổng lọc từng
vùng riêng lẻ) có "tổng = tổng" khớp nhau không, cho nhiều kỳ khác nhau.

Lý do có script này: toàn bộ đợt rà soát 14-15/07/2026 phát hiện nhiều lỗi cùng 1 dạng — dùng
JOIN (INNER) thay vì LEFT JOIN khi map khách hàng/vùng miền, khiến khách hàng "mồ côi" (thiếu hồ
sơ trong DMS_KhachHang/DMSSX_KhachHang) bị loại âm thầm khỏi 1 số báo cáo mà không có dấu hiệu gì
— chỉ phát hiện được qua đối chiếu tay với số liệu DNH báo. Script này tự động hoá đúng phép đối
chiếu "tổng các phần = tổng chung" để bắt sớm loại lỗi này (vd sau khi sửa công thức, hoặc định kỳ
kiểm tra sức khoẻ dữ liệu), không cần đợi đối chiếu tay với DNH mới phát hiện.

Chạy: python scripts/verify_revenue_consistency.py
Thoát code 0 nếu mọi phép đối chiếu khớp, code 1 nếu có ít nhất 1 chỗ lệch (dùng được trong CI/
scheduled task nếu muốn tự động cảnh báo).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from src.etl import _period_revenue, _revenue_by_region

TOLERANCE = 1.0  # VND — cho phép sai số làm tròn cực nhỏ, không phải sai số thật


def check(label, expected, actual):
    diff = abs(expected - actual)
    status = "OK  " if diff <= TOLERANCE else "LECH"
    print(f"  [{status}] {label}: ky_vong={expected:,.0f}  thuc_te={actual:,.0f}  chenh_lech={diff:,.0f}")
    return diff <= TOLERANCE


def check_period(label, start_dt, end_dt):
    print(f"\n=== {label} ({start_dt.strftime('%d/%m/%Y')} - {end_dt.strftime('%d/%m/%Y')}) ===")
    all_ok = True

    try:
        otc_total, etc_total, _, _ = _period_revenue(start_dt, end_dt)
    except Exception as e:
        print(f"  [LOI] Khong lay duoc tong doanh thu ky nay: {e}")
        return False

    # 1. OTC: tong theo vung (_revenue_by_region) phai khop tong khong loc vung (_period_revenue)
    try:
        rows_otc = _revenue_by_region(start_dt, end_dt, channel="OTC")
        sum_otc_region = sum(r["revenue"] for r in rows_otc)
        all_ok &= check("OTC - tong theo vung (breakdown) vs tong cong ty", otc_total, sum_otc_region)
    except Exception as e:
        print(f"  [LOI] OTC breakdown vung: {e}")
        all_ok = False

    # 2. ETC: tuong tu
    try:
        rows_etc = _revenue_by_region(start_dt, end_dt, channel="ETC")
        sum_etc_region = sum(r["revenue"] for r in rows_etc)
        all_ok &= check("ETC - tong theo vung (breakdown) vs tong cong ty", etc_total, sum_etc_region)
    except Exception as e:
        print(f"  [LOI] ETC breakdown vung: {e}")
        all_ok = False

    # 3. OTC: tong 3 vung loc RIENG LE qua _period_revenue(region=...) cong lai phai khop tong
    #    chung - duong tinh toan khac hoan toan breakdown o tren (dung CASE fallback trong SQL
    #    thay vi gop Python), neu ca 2 duong deu khop tong chung thi rat dang tin.
    try:
        bac, _, _, _ = _period_revenue(start_dt, end_dt, region="bac")
        nam, _, _, _ = _period_revenue(start_dt, end_dt, region="nam")
        trung, _, _, _ = _period_revenue(start_dt, end_dt, region="trung")
        all_ok &= check("OTC - Bac+Nam+Trung (loc rieng tung vung) vs tong cong ty", otc_total, bac + nam + trung)
    except Exception as e:
        print(f"  [LOI] OTC loc rieng tung vung: {e}")
        all_ok = False

    try:
        _, bac_etc, _, _ = _period_revenue(start_dt, end_dt, region="bac")
        _, nam_etc, _, _ = _period_revenue(start_dt, end_dt, region="nam")
        _, trung_etc, _, _ = _period_revenue(start_dt, end_dt, region="trung")
        all_ok &= check("ETC - Bac+Nam+Trung (loc rieng tung vung) vs tong cong ty", etc_total, bac_etc + nam_etc + trung_etc)
    except Exception as e:
        print(f"  [LOI] ETC loc rieng tung vung: {e}")
        all_ok = False

    return all_ok


def main():
    today = datetime.now()
    month_start = datetime(today.year, today.month, 1)
    year_start = datetime(today.year, 1, 1)

    periods = [
        ("Thang hien tai (den nay)", month_start, today),
        ("Nam hien tai (den nay)", year_start, today),
        ("Nam 2025 (ca nam)", datetime(2025, 1, 1), datetime(2026, 1, 1)),
        ("Nam 2024 (ca nam)", datetime(2024, 1, 1), datetime(2025, 1, 1)),
    ]

    print("KIEM TRA DOI CHIEU DOANH THU - TONG CAC PHAN PHAI BANG TONG CHUNG")
    all_ok = True
    for label, start, end in periods:
        all_ok &= check_period(label, start, end)

    print("\n" + "=" * 70)
    if all_ok:
        print("KET QUA: TAT CA KHOP - khong phat hien lech nao.")
    else:
        print("KET QUA: CANH BAO - co it nhat 1 phep doi chieu LECH.")
        print("Kiem tra lai cong thuc/JOIN trong src/etl.py (_period_revenue/_revenue_by_region)")
        print("hoac co the co khach hang moi bi 'mo coi' voi tien to chua co trong")
        print("src/region_map.py::CUSTOMER_CODE_PREFIX_TO_REGION.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
