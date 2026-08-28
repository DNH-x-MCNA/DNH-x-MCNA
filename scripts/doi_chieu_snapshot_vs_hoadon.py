# -*- coding: utf-8 -*-
"""Doi chieu snapshot KPI/luong voi hoa don goc tren Bravo.

Muc dich: bat loi cua chinh BANG DAP AN. Cac checker KPI/luong doc
dbo.FACT_ThongKeTinhLuong - dau ra cua usp_SaleSalary_Calculation_Ver2. Neu SP do
sai thi checker sai theo ma khong ai biet. Script nay tinh lai doanh thu tung
nhan vien/thang tu vHoaDonTotal + vHoaDonETCTotal roi so voi MonthSaleAmount.

KHONG ket luan "snapshot sai" khi lech: SP luong co the co dinh nghia rieng
(loai hang tra, loai kenh, chot theo ngay khac). Script chi DO va PHAN LOAI muc
lech de nguoi doc quyet dinh.

Chi doc: khong goi LLM/API, khong gui tin, khong ghi vao du lieu DNH.
Chay tu root repository:
    python scripts/doi_chieu_snapshot_vs_hoadon.py
    python scripts/doi_chieu_snapshot_vs_hoadon.py --nguong 1.0 --ra docs/doi_chieu.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import chay_sql_doi_chung_138 as bo_sql  # noqa: E402

# Tang nhan vien tuyen duoi. Khong gop QLV/TP vi day la rollup cua chinh tang nay.
TANG_NHAN_VIEN = "('TDV','CTV','CS')"

SQL_DOI_CHIEU = """
WITH dim_employee AS (
  SELECT EmployeeCode,MAX(ISNULL(IsDuplicate,0)) IsDuplicate
  FROM dbo.DIM_NhanVien GROUP BY EmployeeCode
), dms_map AS (
  SELECT DMSId,MAX(EmployeeCode) EmployeeCode,
         COUNT(DISTINCT EmployeeCode) EmployeeCount
  FROM dbo.DIM_NhanVien
  WHERE DMSId IS NOT NULL AND (@BoTrungLap=0 OR ISNULL(IsDuplicate,0)=0)
  GROUP BY DMSId
), latest AS (
  SELECT EmployeeCode, EOMONTH(SaveDate) MonthEnd, MAX(SaveDate) d
  FROM dbo.FACT_ThongKeTinhLuong
  WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
  GROUP BY EmployeeCode, EOMONTH(SaveDate)
), snap AS (
  SELECT l.MonthEnd, f.EmployeeCode, MAX(f.EmployeeName) EmployeeName,
         MAX(f.AreaCode) AreaCode, MAX(f.ManagerCode) ManagerCode,
         SUM(f.MonthSaleAmount) FactAmount
  FROM dbo.FACT_ThongKeTinhLuong f
  JOIN latest l ON l.EmployeeCode=f.EmployeeCode AND l.d=f.SaveDate
  LEFT JOIN dim_employee dn ON dn.EmployeeCode=f.EmployeeCode
  WHERE f.PositionCode IN {tang}
    AND (@BoTrungLap=0 OR ISNULL(dn.IsDuplicate,0)=0)
  GROUP BY l.MonthEnd, f.EmployeeCode
), hd AS (
  SELECT EOMONTH(s.DocDate) MonthEnd, n.EmployeeCode,
         SUM(s.Amount9) InvoiceAll,
         SUM(CASE WHEN s.Channel='OTC' THEN s.Amount9 ELSE 0 END) InvoiceOTC,
         SUM(CASE WHEN s.Channel='ETC' THEN s.Amount9 ELSE 0 END) InvoiceETC,
         SUM(CASE WHEN s.Amount9>0 THEN s.Amount9 ELSE 0 END) InvoiceGross
  FROM #sales s
  JOIN dms_map n ON n.DMSId=s.EmpDMSCode AND n.EmployeeCount=1
  GROUP BY EOMONTH(s.DocDate), n.EmployeeCode
)
SELECT ISNULL(sn.MonthEnd,hd.MonthEnd) MonthEnd,
       ISNULL(sn.EmployeeCode,hd.EmployeeCode) EmployeeCode,
       sn.EmployeeName, sn.AreaCode, sn.ManagerCode,
       sn.FactAmount,
       hd.InvoiceAll, hd.InvoiceOTC, hd.InvoiceETC, hd.InvoiceGross,
       CASE WHEN sn.EmployeeCode IS NULL THEN 'CHI_CO_HOA_DON'
            WHEN hd.EmployeeCode IS NULL THEN 'CHI_CO_SNAPSHOT'
            ELSE 'CO_CA_HAI' END TrangThai
FROM snap sn
FULL OUTER JOIN hd ON hd.MonthEnd=sn.MonthEnd AND hd.EmployeeCode=sn.EmployeeCode;
""".replace("{tang}", TANG_NHAN_VIEN)

SQL_DMS_MO_HO = """
WITH dms_map AS (
  SELECT DMSId,COUNT(DISTINCT EmployeeCode) EmployeeCount
  FROM dbo.DIM_NhanVien
  WHERE DMSId IS NOT NULL AND (@BoTrungLap=0 OR ISNULL(IsDuplicate,0)=0)
  GROUP BY DMSId
)
SELECT COUNT(DISTINCT CASE WHEN d.EmployeeCount>1 THEN s.EmpDMSCode END) AmbiguousDMSCodes,
       COUNT(CASE WHEN d.EmployeeCount>1 THEN 1 END) AmbiguousInvoiceRows,
       SUM(CASE WHEN d.EmployeeCount>1 THEN s.Amount9 ELSE 0 END) AmbiguousRevenue,
       COUNT(DISTINCT CASE WHEN d.DMSId IS NULL THEN s.EmpDMSCode END) UnmappedDMSCodes,
       COUNT(CASE WHEN d.DMSId IS NULL THEN 1 END) UnmappedInvoiceRows,
       SUM(CASE WHEN d.DMSId IS NULL THEN s.Amount9 ELSE 0 END) UnmappedRevenue
FROM #sales s LEFT JOIN dms_map d ON d.DMSId=s.EmpDMSCode;
"""


def _pct(a, b):
    return None if not b else 100.0 * (a - b) / b


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nguong", type=float, default=1.0,
                    help="Nguong %% lech duoc coi la khop (mac dinh 1%%)")
    ap.add_argument("--ra", default=os.path.join(ROOT, "docs",
                                                 "doi_chieu_snapshot_vs_hoadon.md"))
    ap.add_argument("--tu-ngay", help="Ghi de @FromDate")
    ap.add_argument("--den-ngay", help="Ghi de @ToDate")
    ap.add_argument("--bo-trung-lap", action="store_true",
                    help="Loai nhan vien co DIM_NhanVien.IsDuplicate=1 khoi phep doi chieu")
    ts = ap.parse_args()

    noi_dung = bo_sql.doc_tai_lieu()
    khai_bao, tao_sales = bo_sql.lay_khai_bao_va_sales(noi_dung)
    khai_bao = bo_sql.doi_tham_so(khai_bao,
                                  {"FromDate": ts.tu_ngay, "ToDate": ts.den_ngay})
    khai_bao += "\nDECLARE @BoTrungLap bit = %d;" % (1 if ts.bo_trung_lap else 0)
    bo_sql.kiem_chi_doc(tao_sales, "block #sales")
    bo_sql.kiem_chi_doc(SQL_DOI_CHIEU, "SQL doi chieu")
    bo_sql.kiem_chi_doc(SQL_DMS_MO_HO, "SQL kiem tra DMS mo ho")

    from main import load_env  # noqa: E402
    load_env()
    from src.database import _get_bravo_engine  # noqa: E402

    engine = _get_bravo_engine()
    if engine is None:
        raise SystemExit("Thieu bien BRAVO_SQL_* trong .env.")

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        print("Tao #sales ...")
        cur.execute(khai_bao + "\n" + tao_sales)
        while cur.nextset():
            pass
        print("Doi chieu snapshot voi hoa don ...")
        cur.execute(khai_bao + "\n" + SQL_DOI_CHIEU)
        cot = [c[0] for c in cur.description]
        dong = [dict(zip(cot, d)) for d in cur.fetchall()]
        cur.execute(khai_bao + "\n" + SQL_DMS_MO_HO)
        cot_dms = [c[0] for c in cur.description]
        dms_chat_luong = dict(zip(cot_dms, cur.fetchone()))
    finally:
        raw.close()

    ca_hai = [d for d in dong if d["TrangThai"] == "CO_CA_HAI"]
    chi_snap = [d for d in dong if d["TrangThai"] == "CHI_CO_SNAPSHOT"]
    chi_hd = [d for d in dong if d["TrangThai"] == "CHI_CO_HOA_DON"]

    # Voi moi cach dinh nghia doanh thu, xem cach nao khop snapshot nhat.
    dinh_nghia = {
        "InvoiceAll": "Ca hai kenh, tinh ca dong am (hang tra)",
        "InvoiceOTC": "Chi kenh OTC",
        "InvoiceETC": "Chi kenh ETC",
        "InvoiceGross": "Ca hai kenh, bo dong am",
    }
    do_khop = {}
    for k in dinh_nghia:
        lech = [abs(_pct(float(d[k] or 0), float(d["FactAmount"] or 0)) or 0)
                for d in ca_hai if d["FactAmount"]]
        if lech:
            do_khop[k] = {
                "trong_nguong": sum(1 for x in lech if x <= ts.nguong),
                "tong": len(lech),
                "trung_vi_lech": statistics.median(lech),
            }

    tot_nhat = max(do_khop, key=lambda k: do_khop[k]["trong_nguong"]) if do_khop else None

    print("")
    print("Dong doi chieu      : %s" % format(len(dong), ","))
    print("  co ca hai         : %s" % format(len(ca_hai), ","))
    print("  chi co snapshot   : %s" % format(len(chi_snap), ","))
    print("  chi co hoa don    : %s" % format(len(chi_hd), ","))
    print("  DMS mo ho         : %s ma, %s dong hoa don" % (
        format(dms_chat_luong["AmbiguousDMSCodes"] or 0, ","),
        format(dms_chat_luong["AmbiguousInvoiceRows"] or 0, ",")))
    print("")
    print("%-14s %-38s %14s %12s" % ("Dinh nghia", "Y nghia", "Khop <=%.1f%%" % ts.nguong,
                                     "Trung vi lech"))
    for k, v in sorted(do_khop.items(), key=lambda x: -x[1]["trong_nguong"]):
        print("%-14s %-38s %7d/%-6d %11.2f%%"
              % (k, dinh_nghia[k][:38], v["trong_nguong"], v["tong"], v["trung_vi_lech"]))
    if tot_nhat:
        print("")
        print("Khop nhat: %s (%s)" % (tot_nhat, dinh_nghia[tot_nhat]))

    # ---- bao cao markdown
    lech_nhat = sorted(
        (d for d in ca_hai if d["FactAmount"]),
        key=lambda d: -abs(_pct(float(d[tot_nhat] or 0), float(d["FactAmount"])) or 0)
    )[:25] if tot_nhat else []

    r = [
        "# Đối chiếu snapshot KPI/lương với hóa đơn gốc",
        "",
        "Mục đích: kiểm tra chính **bảng đáp án**. Các checker KPI/lương đọc "
        "`dbo.FACT_ThongKeTinhLuong` — đầu ra của `usp_SaleSalary_Calculation_Ver2`. "
        "Nếu SP đó sai thì checker sai theo mà không ai biết.",
        "",
        "> Lệch **không** đồng nghĩa snapshot sai. SP lương có thể có định nghĩa riêng "
        "(loại hàng trả, chỉ tính một kênh, chốt theo ngày khác). Bảng dưới đo mức lệch "
        "để người đọc quyết định.",
        "",
        f"- Thời điểm chạy: **{dt.datetime.now().isoformat(timespec='seconds')}**",
        f"- Phiên bản mã nguồn: **{bo_sql._commit_hien_tai()}**",
        f"- Ngưỡng coi là khớp: **{ts.nguong}%**",
        "",
        "```sql",
        khai_bao,
        "```",
        "",
        "## Độ phủ",
        "",
        "| Nhóm | Số dòng (nhân viên × tháng) |",
        "|---|---:|",
        f"| Có ở cả snapshot và hóa đơn | {len(ca_hai):,} |",
        f"| Chỉ có ở snapshot (không tìm được hóa đơn) | {len(chi_snap):,} |",
        f"| Chỉ có ở hóa đơn (không có trong bảng lương) | {len(chi_hd):,} |",
        "",
        "## Chất lượng mapping DMS",
        "",
        "Các mã DMS trỏ tới nhiều nhân viên được **loại khỏi phép cộng hóa đơn** để không nhân đôi doanh thu.",
        "Chúng được liệt kê riêng dưới đây để đội dữ liệu xử lý mapping trước khi kết luận chênh lệch.",
        "",
        "| Vấn đề | Số mã DMS | Số dòng hóa đơn | Doanh thu liên quan |",
        "|---|---:|---:|---:|",
        "| Một mã DMS trỏ tới nhiều nhân viên | %s | %s | %s |" % (
            format(dms_chat_luong["AmbiguousDMSCodes"] or 0, ","),
            format(dms_chat_luong["AmbiguousInvoiceRows"] or 0, ","),
            bo_sql._o_markdown(float(dms_chat_luong["AmbiguousRevenue"] or 0))),
        "| Mã DMS không có trong danh mục nhân viên | %s | %s | %s |" % (
            format(dms_chat_luong["UnmappedDMSCodes"] or 0, ","),
            format(dms_chat_luong["UnmappedInvoiceRows"] or 0, ","),
            bo_sql._o_markdown(float(dms_chat_luong["UnmappedRevenue"] or 0))),
        "",
        "## Định nghĩa doanh thu nào khớp snapshot nhất",
        "",
        "| Định nghĩa | Ý nghĩa | Khớp trong ngưỡng | Trung vị lệch |",
        "|---|---|---:|---:|",
    ]
    for k, v in sorted(do_khop.items(), key=lambda x: -x[1]["trong_nguong"]):
        r.append("| `%s` | %s | %d/%d | %.2f%% |"
                 % (k, dinh_nghia[k], v["trong_nguong"], v["tong"], v["trung_vi_lech"]))

    if tot_nhat:
        r += ["", "## 25 dòng lệch nhiều nhất (so với `%s`)" % tot_nhat, "",
              "| Tháng | Mã NV | Tên | Vùng | QLV | Snapshot | Hóa đơn | Lệch % |",
              "|---|---|---|---|---|---:|---:|---:|"]
        for d in lech_nhat:
            r.append("| %s | %s | %s | %s | %s | %s | %s | %.1f%% |" % (
                d["MonthEnd"], d["EmployeeCode"],
                bo_sql._o_markdown(d["EmployeeName"]), d["AreaCode"], d["ManagerCode"],
                bo_sql._o_markdown(float(d["FactAmount"])),
                bo_sql._o_markdown(float(d[tot_nhat] or 0)),
                _pct(float(d[tot_nhat] or 0), float(d["FactAmount"])) or 0))

    if chi_snap:
        r += ["", "## Có trong bảng lương nhưng không tìm được hóa đơn (20 dòng đầu)", "",
              "| Tháng | Mã NV | Tên | Vùng | Snapshot |", "|---|---|---|---|---:|"]
        for d in sorted(chi_snap, key=lambda x: -float(x["FactAmount"] or 0))[:20]:
            r.append("| %s | %s | %s | %s | %s |" % (
                d["MonthEnd"], d["EmployeeCode"], bo_sql._o_markdown(d["EmployeeName"]),
                d["AreaCode"], bo_sql._o_markdown(float(d["FactAmount"] or 0))))

    os.makedirs(os.path.dirname(os.path.abspath(ts.ra)), exist_ok=True)
    with open(ts.ra, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(r).rstrip() + "\n")
    print("")
    print("Bao cao: %s" % os.path.relpath(ts.ra, ROOT).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
