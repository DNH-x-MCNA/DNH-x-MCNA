# -*- coding: utf-8 -*-
"""
Kiem chung 5 tool R-H(a) da mo cho vai QLV doi voi du lieu that:
get_revenue_by_channel, get_revenue_by_region, get_top_customers, get_top_products, compare_periods.

=== BAN TRUOC (11-12/08) SAI PHUONG PHAP - DA VIET LAI ===
Ban cu so "tong ca doi QLV" voi "cong don ket qua goi rieng tung TDV". Cach do KHONG dung, vi
`scope_employee_code` KHONG co nghia la "ca nhan nay" ma la "CA DOI cua QLV nay":
    _employee_scope_clause -> _get_team_dms_ids -> org_hierarchy.qlv_zones(code)
Voi ma TDV, qlv_zones() tra ve [] (TDV khong phu trach zone nao) -> menh de thanh " AND 1=0"
-> moi tool tra 0d. Nen "cong don = 0" la DUNG THIET KE, khong phai lech du lieu.
Ban cu con doc sai ten khoa (r["otc_revenue"] trong khi ham tra {"otc": {"revenue": ...}}) nen
2 tool get_revenue_by_channel va compare_periods THUC TE CHUA HE DUOC KIEM - luon ra 0 == 0.

=== BAN NAY KIEM 3 THU, deu la bat bien THAT ===
(1) QLV KHONG RA SO: neu _get_team_dms_ids(qlv) rong -> menh de " AND 1=0" -> MOI tool tra 0d
    ma KHONG bao loi. org_hierarchy.py da ghi truoc: ~30% to khong suy ra duoc QLV phu trach
    (ban ghi bong da EndDate/doi vai tro). Day la loi that va nguy hiem: chatbot tra "0 dong"
    dang tin thay vi noi "khong xac dinh duoc".
(2) LECH GIUA 2 DUONG SUY LUAN DOI: revenue_tree() dung mot duong de dung doi TDV, con
    _get_team_dms_ids() dung duong khac. Hai ben ra so nguoi khac nhau = mau thuan noi bo.
(3) LECH GIUA CAC TOOL: trong cung 1 pham vi, 4 tool phai ra CUNG mot tong doanh thu:
        revenue_by_channel.total == sum(revenue_by_region) == sum(top_customers) == sum(top_products)
    Ca 4 doc cung vhoadon_otc/etc, cung dieu kien loc, chi khac cach GOM NHOM. revenue_by_region
    dung LEFT JOIN (khach mo coi khong bi loai) nen tong phai bang. compare_periods goi lai
    revenue_by_channel nen period_a phai khop tuyet doi.
    Khoang kiem nam TRON trong cua so 12 thang chi tiet -> khong dinh phan da nen
    (monthly_customer_summary khong con item_code, top_products se lech that su - khong phai loi).

Chay tren may 24:
    cd C:\\dnh_chatbot
    python scripts\\verify_rh_a_tools.py

Khong sua gi - chi doc va so sanh, an toan chay nhieu lan.
"""
import sys
import os

BACKEND_DIR = os.environ.get("DNH_BACKEND_DIR", r"C:\dnh_chatbot\backend")
sys.path.insert(0, BACKEND_DIR)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sqlite3

import report_templates as rt

DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-31"
TOL = 1.0  # dung sai lam tron (VND)


def f(x):
    return float(x) if x is not None else 0.0


def qlv_accounts():
    """Cac tai khoan QLV THAT trong auth.db, kem dung 2 gia tri scope ma main.py se truyen:
        scope_area_code    = users.scope_value       (main.py:525)
        scope_employee_code= users.employee_code     (main.py:526)
    Phai kiem dung cap scope nay, KHONG duoc tu bia - vi revenue_by_region re nhanh khac nhau
    tuy scope_area_code co gia tri hay khong."""
    p = os.path.join(BACKEND_DIR, "auth.db")
    if not os.path.exists(p):
        return None
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT username, name, scope_value, employee_code, scope_channel, status, is_active "
            "FROM users WHERE role='qlv'").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def rows_of(res, key):
    """top_products co the tra dict {'warning':..., 'products':[...]} thay vi list."""
    if isinstance(res, dict):
        return res.get(key) or []
    return res or []


def call(name, args, area_code, qlv_code, channel_scope):
    """Goi tool Y HET cach main.py -> nl2sql.py -> call_template() goi khi tai khoan QLV dang dung.
    Phai di qua call_template (khong goi thang ham) vi: (a) no moi la noi ep scope tu server,
    (b) no mo "hop" canh bao _tool_warnings - goi thang thi canh bao bi nuot mat."""
    return rt.call_template(name, dict(args), question="<verify R-H(a)>", username="<verify>",
                            scope_area_code=area_code, scope_employee_code=qlv_code,
                            scope_channel=channel_scope, scope_role="qlv")


def total_of(payload, key):
    """Tong doanh thu tu 1 payload call_template + danh sach canh bao kem theo."""
    warns = payload.get("canh_bao") or []
    if not payload.get("ok"):
        return None, warns, payload.get("error")
    return sum(f(r.get("revenue")) for r in rows_of(payload.get("result"), key)), warns, None


def check_qlv(qlv_code, tdv_codes, area_code, channel_scope):
    """Tra ve (danh sach van de, tong doanh thu doi). area_code/channel_scope truyen y het main.py."""
    problems = []
    d = dict(date_from=DATE_FROM, date_to=DATE_TO)

    # --- (1) QLV co ra so khong ---
    # 13/08: _get_team_dms_ids() gio NEM KhongXacDinhDuocDoi thay vi tra [] -> tool bao ro ly do
    # chu khong am tham tra 0d. Van la van de can bao, nhung KHAC HAN ve muc do nguy hiem.
    try:
        dms_ids = rt._get_team_dms_ids(qlv_code)
    except rt.KhongXacDinhDuocDoi as e:
        problems.append((
            "KHONG XAC DINH DUOC DOI",
            f"Tool BAO RO thay vi tra 0d am tham (day la hanh vi dung). Nhung van chua dung duoc: "
            f"revenue_tree thay {len(tdv_codes)} TDV ma khong ai bao cao len ma nay qua manager_code. "
            f"Can DNH kiem ManagerCode tren Bravo. Thong diep: {str(e)[:120]}"))
        return problems, 0.0

    # --- (2) 2 duong suy luan doi co khop khong ---
    if len(dms_ids) != len(tdv_codes):
        problems.append((
            "LECH DOI HINH",
            f"revenue_tree thay {len(tdv_codes)} TDV nhung _get_team_dms_ids tra {len(dms_ids)} dmsid "
            f"-> 2 duong suy luan doi khong khop, so cua tool va so cua cay to chuc se khac nhau."))

    # --- (3) 4 tool phai ra cung 1 tong ---
    p_ch = call("get_revenue_by_channel", d, area_code, qlv_code, channel_scope)
    if not p_ch.get("ok"):
        problems.append(("get_revenue_by_channel", f"KHONG CHAY DUOC: {p_ch.get('error')}"))
        return problems, 0.0
    base = f(p_ch["result"]["total"]["revenue"])
    all_warns = list(p_ch.get("canh_bao") or [])

    reg, w, err = total_of(call("get_revenue_by_region", d, area_code, qlv_code, channel_scope), "regions")
    all_warns += w
    cus, w, _ = total_of(call("get_top_customers", dict(d, limit=999999),
                              area_code, qlv_code, channel_scope), "customers")
    all_warns += w
    prd, w, _ = total_of(call("get_top_products", dict(d, limit=999999),
                              area_code, qlv_code, channel_scope), "products")
    all_warns += w

    # revenue_by_region khi BI gioi han vung chi tra ve DUNG 1 vung -> tong nho hon la dung thiet ke.
    comparisons = [("get_top_customers", cus), ("get_top_products", prd)]
    if not area_code:
        comparisons.insert(0, ("get_revenue_by_region", reg))
    for label, val in comparisons:
        if val is None:
            problems.append((label, "KHONG CHAY DUOC"))
        elif abs(val - base) > TOL:
            problems.append((label, f"tong={val:,.0f} vs get_revenue_by_channel={base:,.0f} "
                                    f"(lech {abs(val - base):,.0f})"))

    # Canh bao SAI SU THAT: phep tu-doi-chieu trong revenue_by_region so tong CUA DOI voi tong
    # TOAN CONG TY - revenue_by_channel o report_templates.py:429 duoc goi KHONG kem scope nao.
    # Ket qua: doi nao cung "lech" -> bom canh bao "so lieu theo vung co the thieu" vao cau tra
    # loi du so hoan toan dung, va dan AI "KHONG duoc trinh bay breakdown nay nhu so lieu chac chan".
    for w in all_warns:
        if "THEO VUNG CO THE THIEU" in str(w).upper():
            problems.append(("CANH BAO SAI",
                             "revenue_by_region bom canh bao 'so lieu theo vung co the thieu' du so "
                             "dung - phep tu-doi-chieu dang so tong DOI voi tong TOAN CONG TY."))
            break

    p_cp = call("compare_periods", dict(date_from_a=DATE_FROM, date_to_a=DATE_TO,
                                        date_from_b=DATE_FROM, date_to_b=DATE_TO),
                area_code, qlv_code, channel_scope)
    if not p_cp.get("ok"):
        problems.append(("compare_periods", f"KHONG CHAY DUOC: {p_cp.get('error')}"))
    else:
        cp = p_cp["result"]
        cp_a = f(cp.get("period_a", {}).get("total", {}).get("revenue"))
        if abs(cp_a - base) > TOL:
            problems.append(("compare_periods",
                             f"period_a.total={cp_a:,.0f} vs get_revenue_by_channel={base:,.0f} "
                             f"(lech {abs(cp_a - base):,.0f})"))
        if abs(f(cp.get("delta"))) > TOL:
            problems.append(("compare_periods",
                             f"so 2 ky GIONG HET NHAU ma delta={f(cp.get('delta')):,.0f} (phai bang 0)"))

    return problems, base


def main():
    print(f"=== Kiem chung R-H(a): {DATE_FROM} -> {DATE_TO} ===")
    print("Kiem 3 bat bien: (1) QLV co ra so khong  (2) 2 duong suy luan doi co khop khong")
    print("                 (3) 4 tool co ra cung 1 tong doanh thu khong\n")

    tree = rt.revenue_tree(as_of_date=DATE_TO)
    qlv_list = []
    for tp in tree.get("tree", []):
        for q in tp.get("qlv", []):
            if q.get("la_nhom_kenh"):
                continue  # "nhom/kenh" (Modern Trade/Cho si) - khong phai QLV that
            tdvs = q.get("tdv", [])
            if not tdvs:
                continue
            qlv_list.append((q["employee_code"], q["name"], [t["employee_code"] for t in tdvs]))

    print(f"So QLV co doi TDV de kiem: {len(qlv_list)}")

    # Noi voi tai khoan that de lay dung cap scope ma main.py se truyen. QLV KHONG co tai khoan
    # thi van kiem, nhung phai ghi ro la dang gia dinh scope - de khong ket luan nham.
    accs = qlv_accounts()
    by_code = {}
    if accs is None:
        print("CANH BAO: khong doc duoc auth.db -> gia dinh scope_area_code=None cho tat ca.\n")
    else:
        for a in accs:
            if a.get("employee_code"):
                by_code[a["employee_code"]] = a
        print(f"So tai khoan role='qlv' trong auth.db: {len(accs)} "
              f"(khop duoc {len(set(by_code) & {c for c, _, _ in qlv_list})} QLV trong cay)\n")

    zero_qlv, mismatch_qlv, tool_bug_qlv, ok_qlv, no_acc = [], [], [], [], []
    for qlv_code, qlv_name, tdv_codes in qlv_list:
        acc = by_code.get(qlv_code)
        area_code = acc.get("scope_value") if acc else None
        channel_scope = acc.get("scope_channel") if acc else None
        if not acc:
            no_acc.append((qlv_code, qlv_name))

        problems, base = check_qlv(qlv_code, tdv_codes, area_code, channel_scope)
        kinds = {k for k, _ in problems}
        tag = (f"tk={acc['username']} vung={area_code or '-'} kenh={channel_scope or '-'}"
               if acc else "CHUA CO TAI KHOAN (gia dinh khong gioi han vung)")
        print(f"--- QLV {qlv_code} ({qlv_name}) - {len(tdv_codes)} TDV | {tag} ---")
        if not problems:
            ok_qlv.append((qlv_code, qlv_name, base))
            print(f"  OK - cac tool cung ra {base:,.0f}d, compare_periods khop, khong canh bao sai.\n")
            continue

        for kind, msg in problems:
            print(f"    [{kind}] {msg}")
        print()
        if "KHONG XAC DINH DUOC DOI" in kinds:
            zero_qlv.append((qlv_code, qlv_name, len(tdv_codes)))
        if "LECH DOI HINH" in kinds:
            mismatch_qlv.append((qlv_code, qlv_name))
        if kinds - {"KHONG XAC DINH DUOC DOI", "LECH DOI HINH"}:
            tool_bug_qlv.append((qlv_code, qlv_name))

    print("=" * 72)
    print("KET LUAN")
    print(f"  QLV khop hoan toan            : {len(ok_qlv)}/{len(qlv_list)}")
    print(f"  QLV khong xac dinh duoc doi   : {len(zero_qlv)}/{len(qlv_list)}")
    print(f"  QLV lech doi hinh             : {len(mismatch_qlv)}/{len(qlv_list)}")
    print(f"  QLV lech GIUA CAC TOOL        : {len(tool_bug_qlv)}/{len(qlv_list)}")
    if no_acc:
        print(f"  (QLV chua co tai khoan chatbot: {len(no_acc)} - khong demo duoc bang vai QLV)")

    if zero_qlv:
        print("\n  >>> Cac QLV nay chua hoi duoc gi (tool BAO RO ly do, khong tra 0d am tham):")
        for c, n, k in zero_qlv:
            print(f"      {c:<14} {n}  ({k} TDV theo cay to chuc)")
        print("      TUYET DOI khong dung cac tai khoan nay de demo cho den khi sua xong.")
    if tool_bug_qlv:
        print("\n  >>> LOI TOOL THAT SU (cung pham vi ma 4 tool ra so khac nhau):")
        for c, n in tool_bug_qlv:
            print(f"      {c:<14} {n}")
    if not zero_qlv and not tool_bug_qlv:
        print("\n  Khong co loi chan demo. (Lech doi hinh neu co la van de cay to chuc, khong")
        print("  lam sai tong doanh thu cua tool.)")


if __name__ == "__main__":
    main()
