# -*- coding: utf-8 -*-
r"""Chan doan: doi cua 1 QLV co phan giai du DMSId khong.

Su co 04/09/2026 (QLV TM25010183): doanh thu T1-T5/2026 chi ra ~22% so that vi chi 2/10 TDV phan
giai duoc DMSId (thang 1 bao 487,4tr / that 2.026,0tr - dung bang DNH00618 + HNO_04). T6-T8 dung vi
di duong khac (snapshot KPI khoa theo employee_code), nen bang so nhin rat hop ly.

    py scripts/kiem_phan_giai_doi_qlv.py                 # mac dinh TM25010183
    py scripts/kiem_phan_giai_doi_qlv.py TM25010183 TM25010142

CHI DOC. Khong cham Bravo, khong goi LLM.
"""
import os, sys, sqlite3

MAC_DINH = ["TM25010183"]


def main():
    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend = os.path.join(goc, "backend")
    if not os.path.isdir(backend):
        print("Khong tim thay thu muc backend/ canh scripts/")
        return 2
    sys.path.insert(0, backend)
    os.chdir(backend)
    import report_templates as rt
    from local_warehouse import get_conn

    con = get_conn()
    cur = con.cursor()
    tong = cur.execute("SELECT COUNT(*) FROM dim_nhanvien").fetchone()[0]
    rong = cur.execute(
        "SELECT COUNT(*) FROM dim_nhanvien WHERE dmsid IS NULL OR TRIM(dmsid)=''").fetchone()[0]
    print(f"dim_nhanvien: {tong} dong, thieu dmsid: {rong} ({100.0*rong/tong if tong else 0:.0f}%)")
    if rong == tong and tong:
        print("  [LOI] TOAN BO thieu dmsid -> kho chua dong bo lai sau khi them cot.")
        print("        Xu ly: py sync_warehouse.py")
    elif rong:
        print("  [!]   Mot phan thieu dmsid - nhung nguoi do se bi hut khoi bao cao doi.")
    else:
        print("  [OK]  Day du dmsid.")
    con.close()

    loi = 0
    for qlv in (sys.argv[1:] or MAC_DINH):
        print(f"\n=== QLV {qlv} ===")
        try:
            team = rt._team_of_qlv(qlv)
        except Exception as e:
            print(f"  [LOI] _team_of_qlv: {type(e).__name__}: {e}")
            loi += 1
            continue
        codes = [t["employee_code"] for t in team if t.get("employee_code")]
        print(f"  Cay to chuc  : {len(codes)} TDV  {codes}")
        # 04/09/2026: buoc 1 cung co the rot nguoi. fact_tonghopkhachhang la 1 dong/(NV x khach)
        # nen snapshot GIUA THANG chi chua nguoi DA BAN - danh sach doi co lai, va buoc 2 khong the
        # phat hien vi ca hai ve deu bi cat bang nhau. _team_of_qlv() gio tu chot ve thang DA TRON;
        # dong duoi in ra de thay ro no da tranh duoc bay gi.
        try:
            moi_nhat, roster = rt._fact_latest_date(), rt._fdate_roster()
            if roster and moi_nhat and roster != moi_nhat:
                from local_warehouse import get_conn as _gc
                c = _gc().cursor()
                n_giua = c.execute(
                    "SELECT COUNT(DISTINCT employee_code) FROM fact_tonghopkhachhang "
                    "WHERE manager_code=? AND save_date=?", (qlv, moi_nhat)).fetchone()[0]
                print(f"  Moc danh sach: {roster} (thang da tron), KHONG dung {moi_nhat} (giua thang)")
                if n_giua < len(codes):
                    print(f"                 neu lay moc giua thang chi con {n_giua}/{len(codes)} TDV"
                          f" -> da tranh duoc bay co lai danh sach doi")
        except Exception as e:
            print(f"  (khong kiem duoc moc danh sach: {type(e).__name__})")
        token = rt._tool_warnings.set([])
        try:
            ids = rt._get_team_dms_ids(qlv)
            canh_bao = list(rt._tool_warnings.get() or [])
        except Exception as e:
            print(f"  [LOI] _get_team_dms_ids: {type(e).__name__}: {str(e)[:120]}")
            loi += 1
            continue
        finally:
            rt._tool_warnings.reset(token)
        print(f"  Phan giai DMS: {len(ids)} ma   {ids}")
        if len(ids) < len(codes):
            print(f"  [LOI] HUT {len(codes)-len(ids)}/{len(codes)} nguoi -> moi bao cao doanh thu doi")
            print(f"        cua QLV nay dang THIEU dung phan cua ho.")
            loi += 1
        elif len(codes):
            print("  [OK]  Phan giai du doi.")
        for c in canh_bao:
            print(f"  canh bao -> {c[:150]}")

    print("\n" + "=" * 60)
    if loi:
        print("CHUA DAT - xem cac dong [LOI] o tren.")
        return 1
    print("DAT - doi phan giai du, bao cao doanh thu doi khong bi hut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
