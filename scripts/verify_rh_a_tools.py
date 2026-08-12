"""
Kiem chung 5 tool R-H(a) da mo cho vai QLV (report_templates.py) doi voi du lieu that:
get_revenue_by_channel, get_revenue_by_region, get_top_customers, get_top_products, compare_periods.

Cach kiem: voi MOI QLV thuc su co doi TDV, so:
    (a) goi tool voi scope_employee_code = ma QLV  -> tong CA DOI (QLV + TDV duoi quyen, qua
        _employee_scope_clause -> _get_team_dms_ids)
    (b) cong don ket qua tung tool goi RIENG cho tung TDV (scope_employee_code = ma TDV)
(a) va (b) PHAI khop tuyet doi (sai lech > 1 dong do lam tron). Neu lech, day la loi that can bao.

Chay tren may 24 (co warehouse.db that):
    cd C:\\dnh_chatbot\\backend
    python D:\\DNH\\scripts\\verify_rh_a_tools.py     (hoac copy file nay vao backend/ roi chay)

Khong sua gi ca - chi doc va so sanh, an toan chay nhieu lan.
"""
import sys
import os

BACKEND_DIR = os.environ.get("DNH_BACKEND_DIR", r"C:\dnh_chatbot\backend")
sys.path.insert(0, BACKEND_DIR)
sys.stdout.reconfigure(encoding="utf-8")

import report_templates as rt

DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-31"
TOL = 1.0  # dung sai lam tron (VND)


def f(x):
    return float(x) if x is not None else 0.0


def sum_channel_totals(qlv_code, tdv_codes):
    """Cong don OTC/ETC rev+hd tu tung TDV rieng le."""
    tot = {"otc_revenue": 0.0, "otc_invoices": 0, "etc_revenue": 0.0, "etc_invoices": 0}
    for code in tdv_codes:
        r = rt.revenue_by_channel(DATE_FROM, DATE_TO, scope_employee_code=code)
        tot["otc_revenue"] += f(r.get("otc_revenue"))
        tot["otc_invoices"] += int(r.get("otc_invoices") or 0)
        tot["etc_revenue"] += f(r.get("etc_revenue"))
        tot["etc_invoices"] += int(r.get("etc_invoices") or 0)
    return tot


def check_revenue_by_channel(qlv_code, qlv_name, tdv_codes):
    team = rt.revenue_by_channel(DATE_FROM, DATE_TO, scope_employee_code=qlv_code)
    added = sum_channel_totals(qlv_code, tdv_codes)
    diffs = []
    for key in ("otc_revenue", "etc_revenue"):
        d = abs(f(team.get(key)) - added[key])
        if d > TOL:
            diffs.append(f"{key}: doi={f(team.get(key)):,.0f} vs cong_don={added[key]:,.0f} (lech {d:,.0f})")
    return diffs, team, added


def check_revenue_by_region(qlv_code, qlv_name, tdv_codes):
    team_rows = rt.revenue_by_region(DATE_FROM, DATE_TO, scope_employee_code=qlv_code)
    team_total = sum(f(r.get("revenue")) for r in team_rows)
    added_total = 0.0
    for code in tdv_codes:
        rows = rt.revenue_by_region(DATE_FROM, DATE_TO, scope_employee_code=code)
        added_total += sum(f(r.get("revenue")) for r in rows)
    d = abs(team_total - added_total)
    diffs = []
    if d > TOL:
        diffs.append(f"tong_revenue: doi={team_total:,.0f} vs cong_don={added_total:,.0f} (lech {d:,.0f})")
    return diffs, team_total, added_total


def check_top_list(fn, qlv_code, tdv_codes, label):
    """Dung cho top_customers/top_products - lay limit LON de coi nhu 'het danh sach', so TONG doanh
    thu (khong so tung dong, vi thu tu/gioi han co the khac nhau giua doi va tung nguoi)."""
    team_rows = fn(DATE_FROM, DATE_TO, limit=99999, scope_employee_code=qlv_code)
    team_total = sum(f(r.get("revenue")) for r in team_rows)
    added_total = 0.0
    for code in tdv_codes:
        rows = fn(DATE_FROM, DATE_TO, limit=99999, scope_employee_code=code)
        added_total += sum(f(r.get("revenue")) for r in rows)
    d = abs(team_total - added_total)
    diffs = []
    if d > TOL:
        diffs.append(f"{label} tong_revenue: doi={team_total:,.0f} vs cong_don={added_total:,.0f} (lech {d:,.0f})")
    return diffs, team_total, added_total


def check_compare_periods(qlv_code, qlv_name, tdv_codes):
    """compare_periods() goi lai revenue_by_channel 2 lan - kiem tra no PROPAGATE dung scope, khong
    tu tinh rieng bang cach nao khac gay lech."""
    cp = rt.compare_periods(DATE_FROM, DATE_TO, DATE_FROM, DATE_TO, scope_employee_code=qlv_code)
    direct = rt.revenue_by_channel(DATE_FROM, DATE_TO, scope_employee_code=qlv_code)
    diffs = []
    a_otc = f(cp.get("period_a", {}).get("otc_revenue"))
    d_otc = f(direct.get("otc_revenue"))
    if abs(a_otc - d_otc) > TOL:
        diffs.append(f"compare_periods.period_a.otc_revenue={a_otc:,.0f} vs revenue_by_channel truc "
                      f"tiep={d_otc:,.0f} (lech {abs(a_otc - d_otc):,.0f})")
    return diffs


def main():
    print(f"=== Kiem chung R-H(a): {DATE_FROM} -> {DATE_TO} ===\n")

    tree = rt.revenue_tree(as_of_date="2026-07-31")
    qlv_list = []
    for tp in tree.get("tree", []):
        for q in tp.get("qlv", []):
            if q.get("la_nhom_kenh"):
                continue  # bo qua "nhom/kenh" (Kenh MT/Cho si) - khong phai QLV that co doi TDV
            tdvs = q.get("tdv", [])
            if not tdvs:
                continue  # QLV khong co TDV (vd MBKV12, ca dac biet) - khong test duoc kieu doi/cong don
            qlv_list.append((q["employee_code"], q["name"], [t["employee_code"] for t in tdvs]))

    print(f"So QLV co doi TDV de kiem: {len(qlv_list)}\n")

    total_fail = 0
    for qlv_code, qlv_name, tdv_codes in qlv_list:
        print(f"--- QLV {qlv_code} ({qlv_name}) - {len(tdv_codes)} TDV ---")
        all_diffs = []

        diffs, _, _ = check_revenue_by_channel(qlv_code, qlv_name, tdv_codes)
        all_diffs += [("get_revenue_by_channel", d) for d in diffs]

        diffs, _, _ = check_revenue_by_region(qlv_code, qlv_name, tdv_codes)
        all_diffs += [("get_revenue_by_region", d) for d in diffs]

        diffs, _, _ = check_top_list(rt.top_customers, qlv_code, tdv_codes, "top_customers")
        all_diffs += [("get_top_customers", d) for d in diffs]

        diffs, _, _ = check_top_list(rt.top_products, qlv_code, tdv_codes, "top_products")
        all_diffs += [("get_top_products", d) for d in diffs]

        diffs = check_compare_periods(qlv_code, qlv_name, tdv_codes)
        all_diffs += [("compare_periods", d) for d in diffs]

        if all_diffs:
            total_fail += 1
            print(f"  LECH ({len(all_diffs)} diem):")
            for tool, d in all_diffs:
                print(f"    [{tool}] {d}")
        else:
            print("  OK - khop tuyet doi ca 5 tool.")
        print()

    print("=" * 60)
    if total_fail == 0:
        print(f"KET LUAN: TAT CA {len(qlv_list)} QLV khop tuyet doi tren ca 5 tool. An toan cho demo.")
    else:
        print(f"KET LUAN: {total_fail}/{len(qlv_list)} QLV co lech - CAN XEM LAI TRUOC DEMO.")
        print("(Xem chi tiet tung diem lech o tren, tool nao/QLV nao.)")


if __name__ == "__main__":
    main()
