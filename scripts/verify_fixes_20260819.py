# -*- coding: utf-8 -*-
"""Kiem chung 11 muc trong docs/chatbot_accuracy_99_can_xac_minh_khi_co_api.md bang chatbot THAT.

KHAC scripts/run_business_evaluation.py (chay ca 90 cau golden, ton tien/thoi gian): script nay
CHI goi dung so cau hoi can de kiem tra tung fix cua 18-19/08/2026, moi khoang 15-20 lan goi model.

Voi cac muc BAO MAT (salary_ranking, check_order_timing), ngoai cau hoi tu nhien qua chatbot (kiem
model co dung tool dung cach khong), con goi THANG call_template() voi CUNG scope de lay ket qua
CHUAN (bo qua rui ro model dien dat mo ho) - giong triet ly "ground truth checker" cua
business_stress_suite.py, khong doan y model tra loi dung hay sai bang mat.

Chay (can may 24, ANTHROPIC_API_KEY that + noi duoc SQL Server):
    cd C:\\dnh_chatbot
    python scripts\\verify_fixes_20260819.py
    python scripts\\verify_fixes_20260819.py --qlv-code TM24050101   # neu muon chi dinh QLV cu the
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load_env_before_first_call() -> None:
    """Giong het run_business_evaluation.py::_load_env_before_first_call - script doc lap khong
    qua main.py nen phai tu nap .env, neu khong cau dau se dinh 'Chua cau hinh API Key' oan."""
    for env_path in (BACKEND / ".env", ROOT / ".env"):
        if not env_path.exists():
            continue
        with io.open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env_before_first_call()

AUDIT_LOG = BACKEND / "logs" / "audit_log.jsonl"
LABEL = "verifyfix"


def _find_qlv_with_team(explicit_code: str = None) -> tuple:
    """Tim 1 QLV that co doi (>=2 TDV bao cao truc tiep qua manager_code) trong snapshot gan nhat,
    de dung cho cac test can vai QLV. Tra ve (employee_code, so_TDV, area_code) hoac (None, 0, None)
    neu khong tim duoc - khi do PHAI chi dinh --qlv-code thu cong."""
    import report_templates as rt

    def _area_of(code):
        row = rt._q("SELECT area_code FROM dim_nhanvien WHERE employee_code=? LIMIT 1", (code,))
        return row[0]["area_code"] if row else None

    if explicit_code:
        team = rt._team_of_qlv(explicit_code)
        return explicit_code, len(team), _area_of(explicit_code)
    rows = rt._q("""
        SELECT manager_code, COUNT(DISTINCT employee_code) n
        FROM fact_tonghopkhachhang
        WHERE manager_code IS NOT NULL AND manager_code<>''
        GROUP BY manager_code HAVING n>=2 ORDER BY n DESC LIMIT 5
    """)
    if not rows:
        return None, 0, None
    best = rows[0]
    return best["manager_code"], best["n"], _area_of(best["manager_code"])


def _session_id(tag: str) -> str:
    return f"{LABEL}-{tag}-{uuid.uuid4().hex[:8]}"


def _ask(nl2sql, question, tag, **scope_kwargs):
    sid = _session_id(tag)
    try:
        resp = nl2sql.ask(question, session_id=sid, username="verify-fix", **scope_kwargs)
        return {"tag": tag, "question": question, "session_id": sid,
                "answer": resp.get("answer", ""), "error": None, "scope": scope_kwargs}
    except Exception as exc:
        return {"tag": tag, "question": question, "session_id": sid,
                "answer": "", "error": f"{type(exc).__name__}: {exc}", "scope": scope_kwargs}


def _audit_for_sessions(session_ids: set) -> dict:
    found = {sid: [] for sid in session_ids}
    if not AUDIT_LOG.is_file():
        return found
    with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid in found:
                found[sid].append(item)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qlv-code", default=None, help="Ma QLV that co doi, bo trong de tu tim")
    args = parser.parse_args()

    import nl2sql
    import report_templates as rt

    qlv_code, team_size, qlv_area = _find_qlv_with_team(args.qlv_code)
    print(f"=== QLV dung de kiem: {qlv_code!r} (doi {team_size} TDV, vung {qlv_area}) ===")
    if not qlv_code or team_size < 1:
        print("!! KHONG tim duoc QLV nao co doi trong du lieu hien tai - cac muc can vai QLV se bi "
              "bo qua. Chi dinh --qlv-code thu cong neu biet 1 ma QLV that co doi.")

    results = []

    # --- Uu tien 1: bao mat (goi truc tiep call_template - ket qua CHUAN, khong phu thuoc model) ---
    if qlv_code and team_size >= 1:
        team_codes = {t["employee_code"] for t in rt._team_of_qlv(qlv_code)} | {qlv_code}

        r = rt.call_template("get_salary_ranking", {}, scope_role="qlv", scope_employee_code=qlv_code)
        leaked = []
        if r.get("ok"):
            seen = {row["employee_code"] for row in r["result"]["ranking"]}
            leaked = sorted(seen - team_codes)
        results.append({"tag": "SEC-1-salary_ranking", "ok": r.get("ok"),
                        "error": r.get("error"), "leaked_outside_team": leaked,
                        "team_expected": sorted(team_codes)})

        r2 = rt.call_template("check_order_timing",
                              {"date_from": "2026-07-01", "date_to": "2026-07-31"},
                              scope_role="qlv", scope_employee_code=qlv_code)
        leaked2 = []
        if r2.get("ok"):
            seen2 = {row["employee_code"] for row in r2["result"]["summary_by_employee"]}
            leaked2 = sorted(seen2 - team_codes - {"(khong xac dinh)"})
        results.append({"tag": "SEC-2-check_order_timing", "ok": r2.get("ok"),
                        "error": r2.get("error"), "leaked_outside_team": leaked2})

        for name in ("get_inventory_by_region", "get_receivables_overview",
                    "get_qlv_change_history", "get_revenue_reconciliation"):
            r3 = rt.call_template(name, {}, scope_role="qlv", scope_employee_code=qlv_code,
                                  scope_area_code=qlv_area)
            results.append({"tag": f"SEC-3-{name}", "ok": r3.get("ok"), "error": r3.get("error")})

    # --- Uu tien 2-5: qua chatbot that (dung cau hoi tu nhien, session moi) ---
    # scope_role="c_level": bo 90 cau golden von duoc cham o vai C-Level (xem
    # run_business_evaluation.py::evaluate - scope_role="c_level"). 20/08/2026: lan chay dau KHONG
    # truyen tham so nay nen Q012 that bai OAN - tai khoan khong ro vai tro bi loai khoi
    # LIVE_SQL_ALLOWED_ROLES nen KHONG duoc dung query_sql_server, khong the doc view thuong de doi
    # soat. Day la loi cua SCRIPT kiem chung, khong phai loi chatbot.
    CLEVEL = {"scope_role": "c_level"}
    nl_cases = [
        ("DATA-1-Q016", "Bao nhiêu TDV chưa có quản lý trực tiếp trong dữ liệu tháng 7?", CLEVEL),
        ("DATA-2-Q012", "Đối soát doanh thu tháng 7 giữa view tổng và view thường: lệch bao nhiêu và nên tin nguồn nào?", CLEVEL),
        ("DATA-3-Q044", "Có bao nhiêu khách đang có dư nợ ở cả OTC và ETC; tổng nợ của họ thế nào?", CLEVEL),
        ("UX-1-freshness", "Doanh thu tháng 7 theo kênh là bao nhiêu?", CLEVEL),
        ("UX-3-kpi-status", "Xếp hạng KPI tháng 7 top 10 nhân viên", CLEVEL),
        ("UX-4-branch-label", "Tồn kho theo chi nhánh hiện nay thế nào?", CLEVEL),
        ("PROMPT-1-crosssell", "Những cặp sản phẩm nào thường được mua cùng một đơn nhất trong tháng 7?", CLEVEL),
        ("PROMPT-2-group", "Nhóm sản phẩm nào đóng góp doanh thu lớn nhất và có bao nhiêu mã hàng bán ra tháng 7?", CLEVEL),
        ("PROMPT-3-concentration", "Top 10 khách hàng chiếm bao nhiêu phần trăm doanh thu toàn công ty tháng 7?", CLEVEL),
    ]
    if qlv_code and team_size >= 1:
        nl_cases.append(("DATA-4-salary-achievement",
                         "Trong đội tôi có bao nhiêu người đạt V15/V22/V25/ASO tháng 7?",
                         {"scope_role": "qlv", "scope_employee_code": qlv_code}))
        # UX-2 (nhan Do/Vang/Xanh theo NGAY): PHAI hoi dich danh 1 TDV that. Lan chay 20/08 hoi
        # "cua toi" voi scope rong -> chatbot hoi lai ma nhan vien (dung hanh vi, nhung KHONG kiem
        # duoc nhan mau vi khong tool nao chay).
        team_members = [t["employee_code"] for t in rt._team_of_qlv(qlv_code)
                        if t.get("employee_code") and t["employee_code"] != qlv_code]
        if team_members:
            nl_cases.append(("UX-2-daily-kpi",
                             f"Doanh số từng ngày tháng 7 của nhân viên {team_members[0]}, "
                             f"ngày nào đỏ ngày nào vàng?",
                             {"scope_role": "qlv", "scope_employee_code": qlv_code}))

    nl_results = [_ask(nl2sql, q, tag, **scope) for tag, q, scope in nl_cases]
    audit = _audit_for_sessions({r["session_id"] for r in nl_results})

    # --- In bao cao ---
    print("\n" + "=" * 100)
    print("PHAN 1 - BAO MAT (goi truc tiep, ket qua CHUAN)")
    print("=" * 100)
    for r in results:
        print(f"\n--- {r['tag']} ---")
        for k, v in r.items():
            if k == "tag":
                continue
            print(f"  {k}: {v}")

    print("\n" + "=" * 100)
    print("PHAN 2 - QUA CHATBOT THAT (session moi, dung audit_log de biet tool/SQL da chay)")
    print("=" * 100)
    for r in nl_results:
        print(f"\n--- {r['tag']} | session={r['session_id']} ---")
        print(f"Cau hoi: {r['question']}")
        print(f"Scope: {r['scope']}")
        if r["error"]:
            print(f"LOI: {r['error']}")
        print(f"Tra loi:\n{r['answer']}")
        entries = audit.get(r["session_id"], [])
        print(f"[audit_log: {len(entries)} dong]")
        for e in entries:
            tool_tag = e.get("sql", "")[:150]
            print(f"  - db={e.get('db')} status={e.get('status')} sql/tool={tool_tag}")

    out_path = ROOT / "results" / f"verify-fixes-{uuid.uuid4().hex[:8]}.json"
    out_path.parent.mkdir(exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump({"security": results, "chatbot": nl_results,
                   "qlv_code": qlv_code, "team_size": team_size}, f, ensure_ascii=False, indent=2)
    print(f"\n\nDa ghi ket qua day du vao: {out_path}")


if __name__ == "__main__":
    main()
