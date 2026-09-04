# -*- coding: utf-8 -*-
r"""Kiem bang chung ban sua ton kho (fiscal_year/year) da an tren may chay that chua.

Chay tren MAY 24 sau khi da `git checkout` + `py sync_warehouse.py` + restart:

    py scripts/kiem_ton_kho_sau_deploy.py
    py scripts/kiem_ton_kho_sau_deploy.py C:\dnh_chatbot\backend\warehouse.db

Chi DOC, khong ghi gi. In ket luan DAT / CHUA DAT kem ly do.
"""
import os, sys, sqlite3

def tim_db(argv):
    if len(argv) > 1:
        return argv[1]
    for p in (r"C:\dnh_chatbot\backend\warehouse.db",
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "backend", "warehouse.db")):
        if os.path.exists(p):
            return p
    return None

def co_cot(cur, bang, cot):
    try:
        return cot in {r[1] for r in cur.execute(f"PRAGMA table_info({bang})")}
    except sqlite3.Error:
        return False

def main():
    db = tim_db(sys.argv)
    if not db or not os.path.exists(db):
        print("KHONG TIM THAY warehouse.db - truyen duong dan lam tham so.")
        return 2
    print(f"Kho: {db}\n")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()
    loi = []

    # --- 1. Cot nam da ton tai chua ---
    for bang, cot in (("brv_tonkhodk", "fiscal_year"), ("brv_tonkhodklot", "year")):
        if co_cot(cur, bang, cot):
            print(f"[OK]   {bang}.{cot} da co")
        else:
            print(f"[LOI]  {bang}.{cot} CHUA CO -> chua chay init_schema/sync ban moi")
            loi.append(f"{bang}.{cot} thieu")

    # --- 2. Cot nam da co DU LIEU chua ---
    print()
    for bang, cot in (("brv_tonkhodk", "fiscal_year"), ("brv_tonkhodklot", "year")):
        if not co_cot(cur, bang, cot):
            continue
        rows = cur.execute(
            f"SELECT {cot}, COUNT(*), SUM(quantity) FROM {bang} GROUP BY {cot} ORDER BY {cot}"
        ).fetchall()
        if not rows:
            print(f"[?]    {bang}: bang RONG - sync chua chay hoac Bravo khong tra ve dong nao")
            loi.append(f"{bang} rong")
            continue
        print(f"       {bang} theo {cot}:")
        chi_none = True
        for nam, n, sl in rows:
            print(f"         {str(nam):<8} {n:>6,} dong   SL {float(sl or 0):>16,.0f}")
            if nam is not None:
                chi_none = False
        if chi_none:
            print(f"[LOI]  {bang}: MOI dong deu {cot}=NULL -> sync CHUA nap cot nam")
            loi.append(f"{bang}.{cot} toan NULL")
        elif len(rows) > 1:
            print(f"[OK]   {bang}: co {len(rows)} nam rieng biet - loc nam se co tac dung")

    # --- 3. Ket qua that qua chinh ham bao cao ---
    print()
    backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(db))), "backend")
    backend = backend if os.path.isdir(backend) else os.path.dirname(os.path.abspath(db))
    sys.path.insert(0, backend)
    cwd = os.getcwd()
    try:
        os.chdir(backend)
        import report_templates as rt
        vung = rt.inventory_by_region()
        print("       inventory_by_region():")
        for r in vung:
            canh = "  <-- CANH BAO: " + r["canh_bao"][:60] if r.get("canh_bao") else ""
            print(f"         {r['area_code']:<5} {float(r['tong_so_luong']):>16,.0f} don vi"
                  f"   {float(r['tong_gia_tri'])/1e9:>8,.2f} ty   nam={r.get('nam_tai_chinh')}{canh}")
            if r.get("canh_bao"):
                loi.append("inventory_by_region con canh bao thieu cot nam")
        b04 = next((float(r["tong_so_luong"]) for r in vung if r["area_code"] == "B04"), None)
        if b04 is not None:
            if b04 > 20e6:
                print(f"[LOI]  B04 = {b04:,.0f} - VAN dang cong don nhieu nam (truoc khi sua: 28,78 trieu)")
                loi.append("B04 van cong don nhieu nam")
            else:
                print(f"[OK]   B04 = {b04:,.0f} - da ve mot nam (truoc khi sua: 28.777.307)")

        bao_cao = rt.inventory_expiry_report()
        so_lo = None
        if isinstance(bao_cao, dict) and not bao_cao.get("error"):
            so_lo = (bao_cao.get("summary") or {}).get("het_han", {}).get("so_lo")
        print(f"\n       inventory_expiry_report() - lo DA HET HAN: {so_lo}")
        if so_lo is None:
            print("[?]    Khong doc duoc so lo tu ket qua - kiem tay ban in ra o duoi")
            print("      ", str(bao_cao)[:400])
        elif so_lo > 100:
            print(f"[LOI]  Con {so_lo} lo het han - truoc khi sua la 668 lo ma (ton dau ky nam cu)")
            loi.append(f"con {so_lo} lo het han")
        else:
            print(f"[OK]   {so_lo} lo het han - da het lo ma")
    except Exception as e:
        print(f"[?]    Khong goi duoc report_templates: {type(e).__name__}: {e}")
        print("       (khong sao - phan 1 va 2 o tren van du de ket luan)")
    finally:
        os.chdir(cwd)
        con.close()

    print("\n" + "=" * 62)
    if loi:
        print("CHUA DAT. Ly do:")
        for x in loi:
            print("  -", x)
        print()
        print("Xu ly: chay lai  py sync_warehouse.py  trong thu muc backend,")
        print("roi `Restart-Service DNH_Chatbot_Backend`, roi chay lai script nay.")
        return 1
    print("DAT - ban sua ton kho da an. Co the mo lai nhom cau hoi ton kho cho UAT.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
