"""Kiem cac tool loc theo doi QLV co chot DUNG doi hinh cua ky qua khu khong - KHONG goi model.

    python scripts/kiem_doi_ky_qua_khu.py                 # mac dinh ky 05/2026
    python scripts/kiem_doi_ky_qua_khu.py 2026-04-01 2026-04-30

24/09/2026: loi cung ho v34 van con o ~17 tool. PR #63 chi va promotion_effectiveness. Cac tool loc
doi qua `_employee_scope_clause` khi ky hoi cu hon cua so fact_tonghopkhachhang (sync 90 ngay) thi
truyen fdate=None vao _get_team_dms_ids -> lay DOI HIEN TAI, va nhanh du phong fact_thongketinhluong
khong bao gio chay. Do tren kho dev, ky 05/2026: 10/21 QLV lech doanh thu, thieu 2,5 ty (-17,7%
tren nhom bi anh huong).

"Doi dung" o day = doi theo fact_thongketinhluong (sync 400 ngay) tai moc gan nhat <= cuoi ky - cung
nguon voi checker UAT dung (FACT_ThongKeTinhLuong + ManagerCode).

PHAN XET BANG DOANH THU, KHONG BANG DANH SACH THANH VIEN. Hai nguon doi hinh (fact_tonghopkhachhang
va fact_thongketinhluong) khac nhau vai nguoi KHONG co doanh so ngay ca trong ky con nam trong cua so:
chay voi ky 08/2026 thi 15/21 QLV lech thanh vien nhung doanh thu lech 0 dong. So thanh vien vi vay
la nhieu; doanh thu moi la thu nguoi dung nhin thay.

Chay ky 08/2026 (trong cua so) la phep DOI CHUNG: phai ra lech 0. Ky 05/2026 ra -2,5 ty trong khi doi
chung ra 0 => khoan lech den tu viec chot sai MOC doi, khong phai tu viec hai nguon khac nhau.

Ma thoat: 0 neu doanh thu moi QLV khop; 1 neu con QLV lech. Dung duoc sau khi sua de xac nhan.
"""
import os
import sqlite3
import sys

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GOC, "backend"))

for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import local_warehouse  # noqa: E402
import report_templates as rt  # noqa: E402


def _dong(x):
    return format(round(x), ",d").replace(",", ".")


def main():
    ky_tu, ky_den = (sys.argv[1], sys.argv[2]) if len(sys.argv) >= 3 else ("2026-05-01", "2026-05-31")
    con = sqlite3.connect(local_warehouse.DB_PATH)

    moc_khach = rt._fact_date_le(ky_den)
    moc_luong = con.execute("SELECT MAX(save_date) FROM fact_thongketinhluong WHERE save_date<=?",
                            (ky_den,)).fetchone()[0]
    print("=" * 78)
    print("KIEM DOI HINH KY QUA KHU: %s -> %s" % (ky_tu, ky_den))
    print("=" * 78)
    print("Moc phan cong doi (fact_tonghopkhachhang) <= cuoi ky : %s" % (moc_khach or "KHONG CO"))
    print("Moc snapshot luong (fact_thongketinhluong) <= cuoi ky : %s" % (moc_luong or "KHONG CO"))
    if moc_khach:
        print("-> Ky nay con trong cua so phan cong doi, loi khong xuat hien o ky nay.")
    if not moc_luong:
        sys.exit("Khong co snapshot luong phu ky nay - khong co 'doi dung' de so.")
    print()

    def doanh_thu(ids):
        if not ids:
            return 0.0
        ph = ",".join("?" * len(ids))
        tong = 0.0
        for bang in ("vhoadon_otc", "vhoadon_etc"):
            tong += con.execute(
                "SELECT COALESCE(SUM(amount9),0) FROM %s WHERE doc_date BETWEEN ? AND ? "
                "AND employee_code IN (%s)" % (bang, ph), (ky_tu, ky_den, *ids)).fetchone()[0]
        return tong

    qlvs = [r[0] for r in con.execute(
        "SELECT DISTINCT manager_code FROM fact_thongketinhluong WHERE save_date=? "
        "AND manager_code IS NOT NULL AND TRIM(manager_code)<>'' ORDER BY manager_code", (moc_luong,))]

    sai, tong_sai, tong_dung = [], 0.0, 0.0
    for qlv in qlvs:
        try:
            _, tham = rt._employee_scope_clause(qlv, "v", as_of=ky_den)
            dung, _moc = rt._team_of_qlv_tu_luong(qlv, ky_den)
            dung_ids = sorted(set(rt._dms_theo_ma_nv([t["employee_code"] for t in dung]).values()))
        except Exception:
            continue
        if not dung_ids:
            continue
        a, b = doanh_thu(list(tham)), doanh_thu(dung_ids)
        if abs(a - b) < 1:
            continue
        tong_sai += a
        tong_dung += b
        sai.append((qlv, len(set(tham)), len(dung_ids), len(set(tham) - set(dung_ids)),
                    len(set(dung_ids) - set(tham)), a, b))

    if not sai:
        print("DAT: doanh thu cua ca %d QLV khop doi hinh dung ky." % len(qlvs))
        return 0

    print("%-12s %5s %5s %6s %6s %16s %16s %8s" % (
        "QLV", "DANG", "DUNG", "THUA", "SOT", "DT DANG TRA", "DT DUNG KY", "LECH"))
    for qlv, n_dang, n_dung, thua, sot, a, b in sai:
        print("%-12s %5d %5d %6d %6d %16s %16s %7.1f%%" % (
            qlv, n_dang, n_dung, thua, sot, _dong(a), _dong(b), (a - b) / b * 100 if b else 0))
    print()
    print("CHUA DAT: %d/%d QLV ra doanh thu khac doi hinh dung ky." % (len(sai), len(qlvs)))
    print("Doanh thu dang tra %s | dung ky %s | lech %s (%.1f%%)" % (
        _dong(tong_sai), _dong(tong_dung), _dong(tong_sai - tong_dung),
        (tong_sai - tong_dung) / tong_dung * 100 if tong_dung else 0))
    print("THUA = nguoi co trong doi hom nay nhung chua vao doi o ky do; SOT = nguoi da roi doi.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
