# -*- coding: utf-8 -*-
"""Chay mau ~25 cau de do MOT thu duy nhat: MODEL CO CHON DUNG TOOL KHONG.

25/08/2026 - vi sao can kich ban rieng thay vi dung run_business_evaluation.py:
  - Bo 90 cau kia cham DO CHINH XAC SO LIEU (can ground truth SQL, chay lau, ton tien).
  - Cai CHUA AI DO la: he thong vua them 11 tool moi (3 tool 24/08 + 8 tool Codex). 322 test don vi
    da chung minh SQL cua tung tool CHAY DUNG, nhung KHONG chung minh model biet CHON dung tool khi
    nguoi dung hoi bang tieng Viet tu nhien. Day dung la khoang cach da nhieu lan gay loi trong du
    an nay (cau tra loi trong hop ly nhung goi nham tool / nham tang du lieu).
  - Kich ban nay CHI cham "tool ky vong co duoc goi khong" nen re hon nhieu (khong chay ground truth).

Chay tren MAY 24 - noi co API key con so du VA co du lieu that (kho may dev gan nhu rong):
    python scripts/run_tool_routing_sample.py --qlv-employee-code <ma_QLV_that> --qlv-area-code MB

Boi canh 138 cau: xem docs/doi_chieu_138_cau_voi_tool_thuc_te.md
"""
import argparse
import importlib.util
import io
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for _p in (str(BACKEND), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load_env():
    """Giong run_business_evaluation.py: kich ban doc lap KHONG di qua backend/main.py nen phai tu
    nap .env, neu khong cau dau tien se bao 'chua cau hinh API key' oan."""
    for env_path in (BACKEND / ".env", ROOT / ".env"):
        if not env_path.exists():
            continue
        with io.open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

# 25/08/2026 - DUNG NGAY neu khong thay API key, thay vi chay het 25 cau roi bao "0% chon dung tool".
# Lan chay dau tren may 24 dinh dung bay nay: ask() KHONG nem loi khi thieu key - no tra ve BINH
# THUONG mot cau "Chua cau hinh API Key" (nl2sql.py dong ~1585), khong goi tool nao va khong ton
# tien. Ket qua la bao cao ra "1/25 (4%)" trong y het model chon sai tool hang loat, ke ca 5 cau
# doi chung dung tool cu da chay on dinh nhieu thang. Dau hieu that: chi phi $0.0000.
_API_KEY = (os.environ.get("LLM_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_API_KEY", "").strip())
# PHAI kiem CA gia tri gia "mock-key-for-local-testing": ask() coi no NHU LA thieu key va tra ve
# "Chua cau hinh API Key" (nl2sql.py:1587 va :1977) - chi kiem key rong thi van lot. Lan chay thu 2
# tren may 24 dinh dung ca nay: guard cu di qua duoc nhung ket qua van 0% va $0.
if not _API_KEY or _API_KEY == "mock-key-for-local-testing":
    print("LOI: khong co API key dung de goi model.")
    print("     Gia tri dang thay: %s" % (repr(_API_KEY) if _API_KEY else "(rong)"))
    print("     Da thu doc: %s va %s" % (BACKEND / ".env", ROOT / ".env"))
    print("     ask() se tra ve 'Chua cau hinh API Key' cho MOI cau - khong goi tool, khong ton tien,")
    print("     nhung bao cao se trong nhu model chon sai tool 100%. Dung truoc de khoi hieu nham.")
    print("     Neu key nam o moi truong cua service (NSSM) chu khong phai file .env, hay chay:")
    print('       $env:ANTHROPIC_API_KEY = "<key>"   roi chay lai kich ban nay.')
    raise SystemExit(2)

# In DANH TINH key (che phan giua) de doi chieu voi key dang co so du tren Anthropic Console -
# may dev va may 24 tung dung 2 key khac nhau, nhin ky nay la biet ngay dang chay bang key nao.
print("API key dang dung: %s...%s (dai %d)" % (_API_KEY[:14], _API_KEY[-6:], len(_API_KEY)))

import nl2sql  # noqa: E402


def _load_eval_helpers():
    """Tai dung _audit_by_session/_cost_by_session cua run_business_evaluation.py thay vi viet lai:
    ham do co logic phan biet call_template voi SQL tu do, da duoc sua qua chay that 18/08."""
    spec = importlib.util.spec_from_file_location(
        "beval_helpers", ROOT / "scripts" / "run_business_evaluation.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["beval_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


# (ma, vai tro, cau hoi tieng Viet tu nhien, tap tool CHAP NHAN DUOC)
# Uu tien tuyet doi cho 11 TOOL MOI. Kem 5 cau doi chung dung tool cu da chay on dinh - neu nhom
# doi chung cung truot thi la loi he thong, khong phai loi rieng cua tool moi.
SAMPLE = [
    ("S01", "c_level", "Doanh thu 12 tháng gần nhất từng tháng là bao nhiêu, tháng nào tăng giảm mạnh nhất?",
     {"get_revenue_monthly_series"}),
    ("S02", "c_level", "Cho tôi xu hướng doanh thu theo từng tháng trong năm nay, có so với cùng kỳ năm ngoái.",
     {"get_revenue_monthly_series"}),
    ("S03", "regional_director", "Khách hàng nào đã ngừng mua trên 60 ngày mà trước đó mua nhiều?",
     {"get_customers_silent"}),
    ("S04", "qlv", "Đội tôi có khách nào im lặng lâu chưa quay lại mua không?",
     {"get_customers_silent"}),
    ("S05", "c_level", "Tháng này có bao nhiêu khách hàng mở mới?",
     {"get_customer_lifecycle_summary", "get_customer_movement"}),
    ("S06", "c_level", "Tỷ lệ giữ chân khách hàng sau 3 và 6 tháng kể từ lúc mở mới là bao nhiêu?",
     {"get_customer_cohort_retention"}),
    ("S07", "regional_director", "Khách nào mới, khách nào tái kích hoạt, khách nào ngừng mua so với tháng trước?",
     {"get_customer_movement"}),
    ("S08", "qlv", "Đội tôi còn thiếu bao nhiêu để đạt chỉ tiêu, mỗi ngày còn lại cần bán bao nhiêu?",
     {"get_kpi_gap_run_rate"}),
    ("S09", "regional_director", "Vùng nào đang dưới 80% kế hoạch và còn hụt bao nhiêu tiền?",
     {"get_kpi_gap_run_rate"}),
    ("S10", "c_level", "Doanh thu trên đầu người của từng miền thay đổi thế nào, nơi nào tăng người mà giảm năng suất?",
     {"get_workforce_productivity"}),
    ("S11", "regional_director", "Quản lý vùng nào có quá nhiều nhân viên dưới quyền so với mặt bằng?",
     {"get_workforce_productivity"}),
    ("S12", "c_level", "Xếp hạng các tỉnh theo doanh thu từng tháng, tỉnh nào giảm liên tiếp nhiều tháng?",
     {"get_geography_monthly_performance"}),
    ("S13", "c_level", "Địa bàn nào quy mô lớn nhưng tăng trưởng thấp?",
     {"get_geography_monthly_performance"}),
    ("S14", "regional_director", "Cặp sản phẩm nào hay được mua cùng nhau, khách nào mua A mà chưa mua B?",
     {"get_cross_sell_opportunities"}),
    ("S15", "qlv", "Khách nào của đội tôi chỉ mua một nhóm sản phẩm, có cơ hội bán thêm?",
     {"get_cross_sell_opportunities", "get_customer_product_coverage"}),
    ("S16", "regional_director", "Khách nào giảm tần suất mua và giảm số mã hàng so với 3 tháng trước?",
     {"get_customer_product_coverage"}),
    ("S17", "qlv", "Nhân viên nào phụ trách nhiều khách nhưng tỷ lệ khách thực mua lại thấp?",
     {"get_customer_product_coverage", "get_workforce_productivity"}),
    ("S18", "c_level", "Có nhân viên nào thiếu quản lý trực tiếp, thiếu chỉ tiêu hoặc trùng mã không?",
     {"get_operational_data_quality"}),
    ("S19", "qlv", "Cuối tháng còn tồn đọng gì chưa xử lý: khách chưa gán, thiếu target, dữ liệu sai?",
     {"get_operational_data_quality"}),
    ("C01", "c_level", "Doanh thu tháng 7 chia theo kênh OTC và ETC là bao nhiêu?",
     {"get_revenue_by_channel"}),
    ("C02", "c_level", "Tổng nợ quá hạn hiện tại và top khách nợ nhiều nhất?",
     {"get_receivables_overview"}),
    ("C03", "regional_director", "Top 10 sản phẩm bán chạy nhất tháng 7?",
     {"get_top_products"}),
    ("C04", "qlv", "Đội tôi tháng 7 ai đạt chỉ tiêu, ai chưa?",
     {"get_employee_kpi", "get_revenue_tree", "get_kpi_ranking"}),
    ("C05", "c_level", "Dữ liệu doanh thu và công nợ đang cập nhật đến ngày nào?",
     {"get_receivables_overview", "get_revenue_by_channel"}),
    ("B01", "c_level", "Dự báo doanh thu cuối tháng này là bao nhiêu?", set()),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--qlv-employee-code", default=os.getenv("EVAL_QLV_EMPLOYEE_CODE"),
                    help="Ma QLV THAT cho cac cau vai tro qlv (bat buoc - khong doan bua)")
    ap.add_argument("--qlv-area-code", default=os.getenv("EVAL_QLV_AREA_CODE"))
    ap.add_argument("--rd-area-code", default="MB")
    ap.add_argument("--only", help="Chi chay cac ma nay, cach nhau dau phay (vd S01,S06)")
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()

    cases = SAMPLE
    if args.only:
        want = set(x.strip() for x in args.only.split(",") if x.strip())
        cases = [c for c in cases if c[0] in want]

    if any(c[1] == "qlv" for c in cases) and not args.qlv_employee_code:
        print("LOI: co cau vai tro 'qlv' nhung thieu --qlv-employee-code.")
        return 2

    helpers = _load_eval_helpers()
    # 25/08/2026 - BAT BUOC ep lai duong dan log. run_business_evaluation.py tinh duong dan doc qua
    # bien moi truong DNH_BACKEND_DIR, con code GHI log (cost_logger.py, query_engine.py) lai dung
    # vi tri file cua chinh no - hai ben CO THE tro ve hai cho khac nhau. Khi do doc ra 0 dong va
    # bao cao thanh "model khong goi tool nao", trong y het loi chat luong model.
    # Da dinh dung bay nay tren may 24: chatbot tra loi HOAN TOAN DUNG (bang 12 thang co MoM/YoY,
    # danh sach khach im lang...), cost_log co 33 dong / 0,87 USD, nhung bao cao van ra "1/25 (4%)
    # va $0.0000". Lay thang duong dan tu module dang GHI thi khong the lech duoc nua.
    import cost_logger as _cl
    import query_engine as _qe
    helpers.COST_LOG = Path(_cl.LOG_PATH)
    helpers.AUDIT_LOG = Path(_qe.LOG_PATH)

    results = []
    for i, (cid, role, question, expect) in enumerate(cases, 1):
        sid = "routing-%s-%s-%s" % (args.label, cid, uuid.uuid4().hex[:8])
        print("[%d/%d] %s [%s] %s" % (i, len(cases), cid, role, question[:60]), flush=True)
        scope_area = scope_emp = None
        if role == "qlv":
            scope_area, scope_emp = args.qlv_area_code, args.qlv_employee_code
        elif role == "regional_director":
            scope_area = args.rd_area_code
        started = time.monotonic()
        try:
            resp = nl2sql.ask(question, session_id=sid, username="tool-routing-eval",
                              scope_area_code=scope_area, scope_employee_code=scope_emp,
                              scope_role=role)
            answer, error = str(resp.get("answer") or ""), None
        except Exception as exc:
            answer, error = "", "%s: %s" % (type(exc).__name__, exc)
        # Chot chan cuoi: ask() tra ve thong bao nay NHU MOT CAU TRA LOI BINH THUONG (khong nem loi)
        # khi khong dung duoc key. Bat ngay o cau dau thay vi chay not 24 cau roi bao "0% chon dung
        # tool" - da mat 2 lan chay tren may 24 vi khong co chot nay.
        if "Chưa cấu hình API Key" in answer:
            print("\nDUNG: ask() tra ve 'Chua cau hinh API Key' - khong lan goi nao den duoc model.")
            print("      Key da nap vao moi truong nhung backend van khong dung duoc no.")
            print("      Kiem: key co dung dinh dang sk-ant-... khong, va co phai key CON SO DU khong.")
            return 3
        results.append({
            "id": cid, "role": role, "question": question,
            "expected_tools": sorted(expect), "answer": answer, "error": error,
            "session_id": sid, "duration_seconds": round(time.monotonic() - started, 2),
        })
        if args.delay:
            time.sleep(args.delay)

    sids = set(r["session_id"] for r in results)
    audit = helpers._audit_by_session(sids)
    cost = helpers._cost_by_session(sids)
    for r in results:
        called = sorted(audit[r["session_id"]])
        r["tools_called"] = called
        r["cost_usd"] = round(cost[r["session_id"]], 6)
        expect = set(r["expected_tools"])
        if not expect:
            # Ca chan co chu dich: DUNG khi KHONG goi tool nao va co tu choi ro rang.
            low = r["answer"].lower()
            r["dat"] = (not called) and ("ước tính" in low or "dự báo" in low or "không" in low)
        else:
            r["dat"] = bool(expect & set(called))

    dat = [r for r in results if r["dat"]]
    tong_cost = sum(r["cost_usd"] for r in results)
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / ("tool-routing-%s.json" % args.label)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("CHON DUNG TOOL: %d/%d (%.0f%%)   |   Chi phi: %.4f USD"
          % (len(dat), len(results), 100.0 * len(dat) / len(results), tong_cost))
    print("=" * 72)
    if tong_cost <= 0 and any(not r["error"] and r["answer"] for r in results):
        # Co cau tra loi that nhung doc ra 0 dong chi phi -> gan nhu chac chan la DOI CHIEU LOG hong,
        # khong phai model. In bang chung doi chieu de thay ngay chO lech.
        print("\n!!! CO CAU TRA LOI NHUNG DOC RA 0 DONG CHI PHI - loi doi chieu log, khong phai model.")
        print("    File chi phi dang doc: %s" % helpers.COST_LOG)
        try:
            dong = [json.loads(l) for l in io.open(helpers.COST_LOG, encoding="utf-8", errors="replace")
                    if l.strip()]
            print("    Tong so dong trong file: %d" % len(dong))
            if dong:
                print("    session_id dong cuoi cung : %r" % dong[-1].get("session_id"))
            print("    session_id kich ban tao ra: %r" % results[0]["session_id"])
        except Exception as exc:
            print("    Khong doc duoc file: %s" % exc)

    if tong_cost <= 0:
        # Goi model that thi LUON ton tien. Tong = 0 nghia la khong co lan goi nao den duoc model,
        # hoac session_id khong khop duoc voi cost_log.jsonl -> con so % o tren VO NGHIA, khong duoc
        # doc thanh "model chon sai tool". Xem 3 nguyen nhan hay gap ben duoi.
        print("\n!!! CANH BAO: TONG CHI PHI BANG 0 - KET QUA TREN KHONG DANG TIN.")
        print("    Goi model that thi luon ton tien. Bang 0 nghia la mot trong ba:")
        print("      1. Khong lan goi nao den duoc model (thieu API key / het so du / mat mang).")
        print("      2. Kich ban chay o thu muc khac noi backend ghi log (kiem AUDIT_LOG/COST_LOG).")
        print("      3. session_id khong duoc ghi vao cost_log.jsonl.")
        print("    Doc thu mot cau tra loi de biet ngay nguyen nhan:")
        print('      python -c "import json,io;d=json.load(io.open(r\'%s\',encoding=\'utf-8\'));print(d[0][\'answer\'][:400])"' % out)
    truot = [r for r in results if not r["dat"]]
    if truot:
        print("\nCAC CAU TRUOT (ky vong -> thuc te goi):")
        for r in truot:
            print("  %s [%s] %s" % (r["id"], r["role"], r["question"][:52]))
            print("      ky vong: %s" % (r["expected_tools"] or "(khong goi tool nao)"))
            print("      da goi : %s" % (r["tools_called"] or "(khong goi tool nao)"))
            if r["error"]:
                print("      LOI    : %s" % r["error"][:110])
    print("\nChi tiet day du: %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
