# -*- coding: utf-8 -*-
"""Doi chieu nhom khuyen mai sau khi DNH nap bu DMS_DonHangCTKM + DMS_CTKM. CHI DOC Bravo, KHONG goi model.

    python scripts/doi_chieu_ctkm_sau_nap_bu.py                    # thang da nap du gan nhat, toan quoc
    python scripts/doi_chieu_ctkm_sau_nap_bu.py --thang 2026-08 --mien MB

1. Do phu lien ket CTKM tung thang tu 06/2025. Binh thuong 99,3-99,9% don DMS co lien ket; duoi 95% la
   thang chua nap du - tool se khong dua so cho thang do.
2. V34/M35/C18: checker S12 (docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md) tinh rieng tung ProgId,
   so voi promotion_effectiveness: so don, don da xuat hoa don, so khach, doanh thu gan don.
3. C13/M36: tong gia tri thuong DMS theo thang KHONG noi bang vung, so voi _ctkm_gia_tri_theo_thang (bat
   dem trung khi noi DMS_KhachHang/DIM_TinhThanhPho), kem phan gia tri cua don huy da bi loai.

Ma thoat: 0 = khop, 1 = co lech, 2 = chua co thang nao nap du de doi chieu.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import report_templates as rt  # noqa: E402

TU_THANG = dt.date(2025, 6, 1)
LECH_TIEN = 1.0  # dong
GIOI_HAN = 50  # limit toi da cua promotion_effectiveness


def _dau_thang(thang: str) -> dt.date:
    return dt.date(int(thang[:4]), int(thang[5:7]), 1)


def do_phu() -> list:
    hom_nay = dt.date.today()
    thang = rt._ctkm_thang(rt._ctkm_don_gan_theo_ngay(TU_THANG, hom_nay), TU_THANG, hom_nay)
    print("== 1. Do phu lien ket CTKM theo thang (toan cong ty)")
    for t in thang:
        print(f"   {t['thang']}  {t['don_gan_ctkm']:>6}/{t['don_dms']:<6} {t['ty_le_gan_pct']:>5}%  "
              f"{'du' if t['da_nap_du'] else 'CHUA NAP DU'}")
    return thang


def s12_theo_chuong_trinh(tu: dt.date, den: dt.date, mien: str = None) -> dict:
    noi, loc, params = "", "", {"f": tu, "t": den + dt.timedelta(days=1)}
    if mien:
        noi = (" LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=h.CustomerCode"
               " LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId")
        loc, params["mien"] = " AND tp.AreaCode=:mien", mien
    rows = rt._q_bravo(f"""
        WITH po AS (
          SELECT x.ProgId, x.OrderId, MAX(h.CustomerCode) CustomerCode
          FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId{noi}
          WHERE h.DocDate>=:f AND h.DocDate<:t{loc}
          GROUP BY x.ProgId, x.OrderId
        ), inv AS (
          SELECT TRY_CONVERT(int, DMSId) OrderId, SUM(Amount9) Revenue
          FROM dbo.vHoaDonTotal
          WHERE DocDate>=:f AND DocDate<:t AND TRY_CONVERT(int, DMSId) IS NOT NULL
          GROUP BY TRY_CONVERT(int, DMSId)
        )
        SELECT po.ProgId, COUNT(*) Orders, COUNT(inv.OrderId) Invoiced,
               COUNT(DISTINCT po.CustomerCode) Customers, SUM(ISNULL(inv.Revenue, 0)) Revenue
        FROM po JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId LEFT JOIN inv ON inv.OrderId=po.OrderId
        GROUP BY po.ProgId
    """, params)
    return {int(r["ProgId"]): r for r in rows}


def doi_chieu_chuong_trinh(tu: dt.date, den: dt.date, mien: str = None) -> int:
    print(f"== 2. Hieu qua tung chuong trinh {tu} den {den}{' mien ' + mien if mien else ' toan quoc'}")
    tool = rt.promotion_effectiveness(str(tu), str(den), limit=GIOI_HAN, scope_area_code=mien)
    if tool.get("status") != "ok":
        print(f"   tool status={tool.get('status')}: {tool.get('warning')}")
        return 1
    if tool["period"] != {"from": str(tu), "to": str(den)}:
        print(f"   tool tu cat ky thanh {tool['period']}: {tool.get('warning')}")
        return 1
    checker = s12_theo_chuong_trinh(tu, den, mien)
    lech = 0
    for p in tool["programs"]:
        c = checker.get(int(p["program_id"]))
        if c is None:
            print(f"   LECH {p['program_code']} (ProgId {p['program_id']}): checker khong co")
            lech += 1
            continue
        cap = (("orders", "Orders"), ("invoiced_orders", "Invoiced"),
               ("participating_customers", "Customers"), ("associated_revenue", "Revenue"))
        sai = [f"{a} tool={p[a]} checker={c[b]}" for a, b in cap if abs(float(p[a]) - float(c[b] or 0)) > LECH_TIEN]
        if sai:
            print(f"   LECH {p['program_code']} (ProgId {p['program_id']}): " + "; ".join(sai))
            lech += 1
    # Tool tra top GIOI_HAN theo doanh thu (hoa theo ProgId) cong cac chuong trinh trung ma xep thap hon.
    top_checker = sorted(checker, key=lambda k: (-float(checker[k]["Revenue"] or 0), k))[:GIOI_HAN]
    thieu = set(top_checker) - {int(p["program_id"]) for p in tool["programs"]}
    if thieu:
        print(f"   LECH thu hang: checker co trong top {GIOI_HAN} ma tool khong tra: {sorted(thieu)}")
        lech += 1
    print(f"   {len(tool['programs'])} chuong trinh, {lech} cho lech")
    return 1 if lech else 0


def doi_chieu_gia_tri(thang_du: list) -> int:
    tu, den = _dau_thang(thang_du[0]), rt._month_end(_dau_thang(thang_du[-1]))
    print(f"== 3. Gia tri khuyen mai DMS theo thang {thang_du[0]} den {thang_du[-1]} (toan quoc)")
    rows = rt._q_bravo("""
        SELECT CONVERT(char(7), h.DocDate, 126) Thang,
               SUM(CASE WHEN ISNULL(h.StatusId, 0)<>2 THEN CAST(x.Amount AS float) ELSE 0 END) KhongHuy,
               SUM(CASE WHEN h.StatusId=2 THEN CAST(x.Amount AS float) ELSE 0 END) DonHuy
        FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
        WHERE h.DocDate>=:f AND h.DocDate<:t
        GROUP BY CONVERT(char(7), h.DocDate, 126)
    """, {"f": tu, "t": den + dt.timedelta(days=1)})
    checker = {str(r["Thang"])[:7]: r for r in rows}
    tool = {b["thang"]: b for b in rt._ctkm_gia_tri_theo_thang(str(tu), str(den))["theo_thang"]}
    lech = 0
    for thang in thang_du:
        c, t = checker.get(thang) or {}, tool.get(thang) or {}
        ck, tk = float(c.get("KhongHuy") or 0), float(t.get("tong_gia_tri_km") or 0)
        dau = "khop" if abs(ck - tk) <= LECH_TIEN else "LECH"
        lech += dau == "LECH"
        print(f"   {thang}  checker {ck:>18,.0f}  tool {tk:>18,.0f}  {dau}   (don huy da loai: "
              f"{float(c.get('DonHuy') or 0):,.0f})")
    return 1 if lech else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thang", help="YYYY-MM can doi chieu hieu qua chuong trinh; mac dinh thang du gan nhat")
    ap.add_argument("--mien", help="AreaCode tren Bravo (MB/MN/MT); bo trong = toan quoc")
    args = ap.parse_args()
    thang = do_phu()
    hien_tai = dt.date.today().strftime("%Y-%m")
    thang_du = [t["thang"] for t in thang if t["da_nap_du"] and t["don_dms"] and t["thang"] < hien_tai]
    if not thang_du:
        print("Chua co thang nao nap du lien ket CTKM.")
        return 2
    chon = args.thang or thang_du[-1]
    if chon not in thang_du:
        print(f"Thang {chon} chua nap du lien ket CTKM; khong doi chieu.")
        return 2
    ket_qua = doi_chieu_chuong_trinh(_dau_thang(chon), rt._month_end(_dau_thang(chon)), args.mien)
    ket_qua |= doi_chieu_gia_tri(thang_du[-12:])
    print("KET LUAN:", "KHOP" if ket_qua == 0 else "CO LECH - xem cac dong LECH o tren")
    return ket_qua


if __name__ == "__main__":
    sys.exit(main())
