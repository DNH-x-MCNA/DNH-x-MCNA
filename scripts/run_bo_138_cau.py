# -*- coding: utf-8 -*-
"""Chay TOAN BO 138 cau hoi dieu hanh, do KET QUA THUC TE va doi chieu voi du doan tren giay.

26/08/2026 - VI SAO CAN:
  - docs/doi_chieu_138_cau_voi_tool_thuc_te.md danh gia do phu ~61% (84/138) nhung day la doi chieu
    TREN GIAY: mo ta tool khop noi dung cau hoi. KHONG phai so do.
  - Bo 25 cau (run_tool_routing_sample.py) da do that va dat 25/25, nhung chi phu 25 cau va chi cham
    DINH TUYEN TOOL, khong cham "tra loi duoc hay khong".
  - 113 cau con lai CHUA TUNG duoc hoi lan nao.

KHAC bo 25 cau o cho: khong the liet ke tool ky vong cho 138 cau, nen kich ban nay do KET QUA:
tra loi duoc / tu choi vi thieu du lieu / bi chan du bao / loi. Roi DOI CHIEU CHEO voi cot trang thai
(READY/PARTIAL/DERIVED/BLOCKED) ma tai lieu da du doan. Bang cheo do moi la thu dang bao cao: no cho
biet danh gia tren giay dung den dau, chu khong chi cho mot con so phan tram tron.

NGUON CAU HOI: doc THANG tu docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md - KHONG chep lai danh
sach vao day. Chep lai la tao nguon su that thu hai, sua mot ben quen ben kia.

Vai tro suy tu tien to ma: C = c_level (54 cau), M = regional_director/TP (44), V = qlv (40).

Chay tren MAY 24 (noi co du lieu that + API key con so du):
    python scripts/run_bo_138_cau.py --qlv-employee-code <ma_QLV_that> --qlv-area-code MB

Uoc tinh: ~138 cau x 0,06 USD ~ 8-10 USD, ~90 phut. GHI KET QUA SAU TUNG CAU nen dut giua chung
khong mat gi - chay lai voi --resume de tiep tuc tu cho do.
"""
import argparse
import importlib.util
import io
import json
import os
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
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

NGUON_CAU_HOI = ROOT / "docs" / "bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md"
VAI_THEO_TIEN_TO = {"C": "c_level", "M": "regional_director", "V": "qlv"}


def _load_env():
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

_API_KEY = (os.environ.get("LLM_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_API_KEY", "").strip())
if not _API_KEY or _API_KEY == "mock-key-for-local-testing":
    # Cung chot chan nhu run_tool_routing_sample.py: ask() KHONG nem loi khi thieu key, no tra ve
    # binh thuong mot cau "Chua cau hinh API Key". Khong chan o day thi chay het 138 cau roi bao
    # "0% tra loi duoc" - da mat 2 lan chay vi chuyen nay ngay 25/08.
    print("LOI: khong co API key dung de goi model (dang thay: %s)."
          % (repr(_API_KEY) if _API_KEY else "(rong)"))
    print("     Neu key nam o moi truong cua service chu khong o .env:")
    print('       $env:ANTHROPIC_API_KEY = "<key>"  roi chay lai.')
    raise SystemExit(2)

print("API key dang dung: %s...%s (dai %d)" % (_API_KEY[:14], _API_KEY[-6:], len(_API_KEY)))

import nl2sql  # noqa: E402


def _load_eval_helpers():
    spec = importlib.util.spec_from_file_location(
        "beval_helpers", ROOT / "scripts" / "run_business_evaluation.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["beval_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


def doc_bo_cau_hoi():
    """Doc 138 cau tu bang markdown. Dinh dang: | C01 | noi dung | S01 | READY |"""
    if not NGUON_CAU_HOI.is_file():
        raise SystemExit("Khong tim thay nguon cau hoi: %s" % NGUON_CAU_HOI)
    s = io.open(NGUON_CAU_HOI, encoding="utf-8").read()
    rows = re.findall(r"^\|\s*([CMV]\d{2})\s*\|\s*(.+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$",
                      s, re.M)
    if not rows:
        raise SystemExit("Khong parse duoc cau hoi nao tu %s - dinh dang bang co the da doi."
                         % NGUON_CAU_HOI)
    return [{"id": r[0], "question": r[1].strip(), "nhom": r[2].strip(),
             "trang_thai_tren_giay": r[3].strip(),
             "role": VAI_THEO_TIEN_TO[r[0][0]]} for r in rows]


# Dau hieu TU CHOI. Chatbot duoc thiet ke "tha noi khong biet con hon bia" nen tu choi la HANH VI
# DUNG cho cac cau khong co nguon du lieu - KHONG duoc dem la that bai. Cac cum nay lay tu chinh
# thong bao trong report_templates.py/nl2sql.py chu khong doan.
DAU_HIEU_TU_CHOI = (
    "không có dữ liệu", "chưa có dữ liệu", "chưa có nguồn", "không có nguồn",
    "not_available", "not_applicable", "chưa được đồng bộ", "chưa map",
    "hệ thống chưa", "không thể tra cứu", "chưa có trong kho", "ngoài phạm vi dữ liệu",
)
DAU_HIEU_CHAN_DU_BAO = ("dự báo", "không thể dự đoán", "chỉ phản ánh dữ liệu đã có")


def phan_loai(r):
    """Xep ket qua vao 4 nhom. Ghi ro tieu chi de nguoi doc bao cao kiem lai duoc, khong phai tin suong.

    LUU Y: day la phan loai TU DONG dua tren tu ngu - no uoc luong, khong tuyet doi. Bao cao PHAI noi
    ro dieu do va nen doc tay mot mau de kiem. Kinh nghiem 25/08: mot con so tu dong trong dep de bi
    tin ngay ma khong ai doc noi dung phia sau."""
    if r.get("error"):
        return "LOI"
    tra_loi = (r.get("answer") or "").lower()
    if not tra_loi.strip():
        return "LOI"
    co_tool = bool(r.get("tools_called"))
    co_tu_choi = any(d in tra_loi for d in DAU_HIEU_TU_CHOI)
    if not co_tool and any(d in tra_loi for d in DAU_HIEU_CHAN_DU_BAO) and len(tra_loi) < 900:
        return "CHAN_DU_BAO"
    if co_tu_choi and not co_tool:
        return "TU_CHOI_KHONG_CO_NGUON"
    if co_tu_choi and co_tool:
        # Goi tool nhung tool bao khong co nguon -> van la tu choi trung thuc, chi la biet duong tim.
        return "TRA_LOI_MOT_PHAN"
    if co_tool:
        return "TRA_LOI"
    return "TRA_LOI_KHONG_TOOL"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--qlv-employee-code", default=os.getenv("EVAL_QLV_EMPLOYEE_CODE"),
                    help="Ma QLV THAT cho 40 cau vai tro qlv (bat buoc)")
    ap.add_argument("--qlv-area-code", default=os.getenv("EVAL_QLV_AREA_CODE"))
    ap.add_argument("--rd-area-code", default="MB")
    ap.add_argument("--only", help="Chi chay cac ma nay, cach nhau dau phay (vd C01,M05)")
    ap.add_argument("--gioi-han", type=int, help="Chi chay N cau dau - de thu truoc khi chay het")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--resume", help="Duong dan file ket qua dang do - chay tiep cac cau con thieu")
    args = ap.parse_args()

    cases = doc_bo_cau_hoi()
    print("Doc duoc %d cau tu %s" % (len(cases), NGUON_CAU_HOI.name))
    if args.only:
        want = set(x.strip() for x in args.only.split(",") if x.strip())
        cases = [c for c in cases if c["id"] in want]
    if args.gioi_han:
        cases = cases[:args.gioi_han]

    if any(c["role"] == "qlv" for c in cases) and not args.qlv_employee_code:
        print("LOI: co cau vai tro 'qlv' nhung thieu --qlv-employee-code (khong duoc doan bua).")
        return 2

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = Path(args.resume) if args.resume else out_dir / ("bo138-%s.json" % args.label)

    # GHI SAU TUNG CAU: chay 90 phut ma dut giua chung thi khong duoc mat ca. Da co qua nhieu thu di
    # sai trong hai ngay qua de tin vao mot lan ghi duy nhat o cuoi.
    da_co = {}
    if out.is_file():
        try:
            for r in json.loads(out.read_text(encoding="utf-8")):
                da_co[r["id"]] = r
            print("Tiep tuc tu file co san: da co %d cau, con %d cau."
                  % (len(da_co), len([c for c in cases if c["id"] not in da_co])))
        except Exception as e:
            print("Khong doc duoc file cu (%s) - bat dau lai tu dau." % e)

    helpers = _load_eval_helpers()
    # Lay duong dan log THANG tu module dang GHI - xem ghi chu dai trong run_tool_routing_sample.py.
    import cost_logger as _cl
    import query_engine as _qe
    helpers.COST_LOG = Path(_cl.LOG_PATH)
    helpers.AUDIT_LOG = Path(_qe.LOG_PATH)

    can_chay = [c for c in cases if c["id"] not in da_co]
    t0 = time.monotonic()
    for i, case in enumerate(can_chay, 1):
        cid, role, question = case["id"], case["role"], case["question"]
        sid = "bo138-%s-%s-%s" % (args.label, cid, uuid.uuid4().hex[:8])
        con_lai = len(can_chay) - i
        uoc = (time.monotonic() - t0) / i * con_lai / 60 if i > 1 else 0
        print("[%d/%d] %s [%s] %s%s" % (i, len(can_chay), cid, role, question[:58],
                                        ("  (~%.0f phut nua)" % uoc) if uoc else ""), flush=True)
        scope_area = scope_emp = None
        if role == "qlv":
            scope_area, scope_emp = args.qlv_area_code, args.qlv_employee_code
        elif role == "regional_director":
            scope_area = args.rd_area_code
        started = time.monotonic()
        try:
            resp = nl2sql.ask(question, session_id=sid, username="bo138-eval",
                              scope_area_code=scope_area, scope_employee_code=scope_emp,
                              scope_role=role)
            answer, error = str(resp.get("answer") or ""), None
        except Exception as exc:
            answer, error = "", "%s: %s" % (type(exc).__name__, exc)
        if "Chưa cấu hình API Key" in answer:
            print("\nDUNG: ask() tra ve 'Chua cau hinh API Key' - khong lan goi nao den duoc model.")
            return 3
        da_co[cid] = {**case, "answer": answer, "error": error, "session_id": sid,
                      "duration_seconds": round(time.monotonic() - started, 2)}
        out.write_text(json.dumps(list(da_co.values()), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        if args.delay:
            time.sleep(args.delay)

    # Noi tool da goi + chi phi cho tung cau
    ket_qua = [da_co[c["id"]] for c in cases if c["id"] in da_co]
    sids = set(r["session_id"] for r in ket_qua)
    audit = helpers._audit_by_session(sids)
    cost = helpers._cost_by_session(sids)
    for r in ket_qua:
        r["tools_called"] = sorted(audit[r["session_id"]])
        r["cost_usd"] = round(cost[r["session_id"]], 6)
        r["ket_qua"] = phan_loai(r)
    out.write_text(json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- Bao cao ----------------
    dem = Counter(r["ket_qua"] for r in ket_qua)
    tong_cost = sum(r["cost_usd"] for r in ket_qua)
    print()
    print("=" * 78)
    print("KET QUA %d CAU  |  chi phi %.4f USD" % (len(ket_qua), tong_cost))
    print("=" * 78)
    for k in ("TRA_LOI", "TRA_LOI_MOT_PHAN", "TRA_LOI_KHONG_TOOL", "TU_CHOI_KHONG_CO_NGUON",
              "CHAN_DU_BAO", "LOI"):
        if dem.get(k):
            print("  %-24s %3d  (%.0f%%)" % (k, dem[k], dem[k] / len(ket_qua) * 100))

    print()
    print("DOI CHIEU CHEO: du doan TREN GIAY  vs  ket qua THUC TE")
    print("-" * 78)
    cheo = defaultdict(Counter)
    for r in ket_qua:
        cheo[r["trang_thai_tren_giay"]][r["ket_qua"]] += 1
    for tt in sorted(cheo):
        tong = sum(cheo[tt].values())
        chi_tiet = ", ".join("%s=%d" % (k, v) for k, v in cheo[tt].most_common())
        print("  %-16s (%3d cau): %s" % (tt, tong, chi_tiet))

    print()
    print("Theo vai tro:")
    theo_vai = defaultdict(Counter)
    for r in ket_qua:
        theo_vai[r["role"]][r["ket_qua"]] += 1
    for vai in sorted(theo_vai):
        tong = sum(theo_vai[vai].values())
        tl = theo_vai[vai].get("TRA_LOI", 0) + theo_vai[vai].get("TRA_LOI_MOT_PHAN", 0)
        print("  %-20s %3d cau, tra loi duoc %3d (%.0f%%)" % (vai, tong, tl, tl / tong * 100))

    loi = [r for r in ket_qua if r["ket_qua"] == "LOI"]
    if loi:
        print()
        print("CAC CAU LOI - can doc tay:")
        for r in loi[:10]:
            print("  %s: %s" % (r["id"], (r.get("error") or r["answer"][:80]) or "(rong)"))

    print()
    print("Chi tiet day du: %s" % out)
    print("LUU Y: phan loai tren la TU DONG theo tu ngu, chi de uoc luong. Truoc khi bao cao ra ngoai")
    print("       PHAI doc tay mot mau (nhat la nhom TU_CHOI va TRA_LOI_KHONG_TOOL) de xac nhan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
