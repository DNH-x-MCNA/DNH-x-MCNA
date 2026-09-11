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

11/09/2026 - PHAM VI 126 CAU VA TRAN CHI PHI (ke hoach chot UAT 11-20/09, AGENTS.md):
  - Mac dinh chi chay 126 cau trong pham vi; 12 cau ngoai pham vi can --ca-138 moi chay.
  - Tai khoan tu gan theo nhom: M = regional_director mien MB; V01-V32 = doi MBKV2; V33-V40 = doi
    TM25010183 (theo docs/handoff_antigravity_uat_09-09.md). In ra o --thu de nguoi duyet xac nhan.
  - GOI MODEL THAT bat buoc co --tran-chi-usd va --nguoi-duyet. Cham tran thi dung truoc cau ke
    tiep; cau vua chay ma khong do duoc chi phi trong cost_log thi cung dung (khong vuot tran mu).
  - Ly do: ngay 10/09/2026 business-eval chay 235 luot (7,08 USD) trong luc khong ai dieu phoi.

Xem truoc, KHONG goi model, khong can API key:
    python scripts/run_bo_138_cau.py --thu

Chay that tren MAY 24 (sau khi anh Dang duyet):
    python scripts/run_bo_138_cau.py --tran-chi-usd 20 --nguoi-duyet "Dang" --label vong-nen-1409

Uoc tinh theo log 10-11/09 tren may 24: ~0,18 USD moi cau (220 luot / 56 phien), mac dinh uoc
0,20 USD/cau -> 126 cau ~ 25 USD. GHI KET QUA SAU TUNG CAU nen dut giua chung khong mat gi - chay
lai voi --resume de tiep tuc tu cho do.
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

def _kiem_api_key():
    """Chi goi khi sap goi model that (khong goi o che do --thu)."""
    key = (os.environ.get("LLM_API_KEY", "").strip()
           or os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not key or key == "mock-key-for-local-testing":
        # Cung chot chan nhu run_tool_routing_sample.py: ask() KHONG nem loi khi thieu key, no tra ve
        # binh thuong mot cau "Chua cau hinh API Key". Khong chan o day thi chay het 138 cau roi bao
        # "0% tra loi duoc" - da mat 2 lan chay vi chuyen nay ngay 25/08.
        print("LOI: khong co API key dung de goi model (dang thay: %s)."
              % (repr(key) if key else "(rong)"))
        print("     Neu key nam o moi truong cua service chu khong o .env:")
        print('       $env:ANTHROPIC_API_KEY = "<key>"  roi chay lai.')
        return False
    print("Da phat hien API key hop le (gia tri duoc an khoi log).")
    return True


import nl2sql  # noqa: E402


def _load_eval_helpers():
    # 11/09/2026: business-eval da bi go; hai ham doc nhat ky duoc tach sang nhat_ky_eval.py.
    spec = importlib.util.spec_from_file_location(
        "nhat_ky_eval", ROOT / "scripts" / "nhat_ky_eval.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nhat_ky_eval"] = mod
    spec.loader.exec_module(mod)
    return mod


# Ke hoach chot UAT 11-20/09/2026: pham vi cham la 126 cau. 12 cau nay nam ngoai pham vi (9 du bao
# hoac loi nhuan, 3 tam loai vi thieu nguon) - giu lich su tren sheet, KHONG chay, KHONG tinh mau so.
NGOAI_PHAM_VI_126 = frozenset("C04 C14 C15 C19 C50 C51 M39 M43 V09 C25 C49 V16".split())

# Tai khoan doi chung nhom V theo docs/handoff_antigravity_uat_09-09.md: V01-V32 la tu.pham (doi
# MBKV2, Pham Xuan Tu), V33-V40 la thuy.nguyen (doi TM25010183, Nguyen Thi Hong Thuy). Ca hai o MB.
QLV_V01_V32 = "MBKV2"
QLV_V33_V40 = "TM25010183"

# Log may 24 ngay 10-11/09/2026: 220 luot goi / 56 phien ~ 0,18 USD moi cau. Uoc 0,20 de du phong.
UOC_TINH_USD_MOI_CAU = 0.20


def chon_cau(cases, only=None, gioi_han=None, ca_138=False):
    """Loc danh sach cau se chay. Mac dinh bo 12 cau ngoai pham vi 126."""
    if only:
        want = set(x.strip() for x in only.split(",") if x.strip())
        bi_loai = sorted(want & NGOAI_PHAM_VI_126) if not ca_138 else []
        if bi_loai:
            print("CANH BAO: %s nam ngoai pham vi 126, bo qua. Can chay thi them --ca-138."
                  % ", ".join(bi_loai))
        cases = [c for c in cases if c["id"] in want]
    if not ca_138:
        cases = [c for c in cases if c["id"] not in NGOAI_PHAM_VI_126]
    if gioi_han:
        cases = cases[:gioi_han]
    return cases


def pham_vi_cho(case, args):
    """(vai, scope_area_code, scope_employee_code) cho mot cau."""
    role = case["role"]
    if role == "qlv":
        if args.qlv_employee_code:          # ep mot doi cho ca nhom V
            emp = args.qlv_employee_code
        elif int(case["id"][1:]) >= 33:
            emp = args.qlv_v33_v40
        else:
            emp = args.qlv_v01_v32
        return role, args.qlv_area_code, emp
    if role == "regional_director":
        return role, args.rd_area_code, None
    return role, None, None


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

# Cac loi nay khong the tu het khi chay sang cau tiep theo. Dung ngay de tranh tao mot file 138
# dong LOI gia (08/09/2026 da gap: het credit nhung smoke van goi du ca 5 cau).
DAU_HIEU_LOI_PROVIDER_CAN_DUNG = (
    "credit balance is too low",
    "plans & billing",
    "authentication_error",
    "invalid x-api-key",
    "api key is invalid",
    "rate_limit_error",
)


def loi_provider_can_dung(error):
    noi_dung = str(error or "").lower()
    return next((dau_hieu for dau_hieu in DAU_HIEU_LOI_PROVIDER_CAN_DUNG
                 if dau_hieu in noi_dung), None)


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
                    help="Ep MOT ma QLV cho ca nhom V (bo qua gan theo nhom V01-V32 / V33-V40)")
    ap.add_argument("--qlv-v01-v32", default=QLV_V01_V32, help="Ma QLV cho V01-V32 (mac dinh MBKV2)")
    ap.add_argument("--qlv-v33-v40", default=QLV_V33_V40,
                    help="Ma QLV cho V33-V40 (mac dinh TM25010183)")
    ap.add_argument("--qlv-area-code", default=os.getenv("EVAL_QLV_AREA_CODE") or "MB")
    ap.add_argument("--ca-138", action="store_true",
                    help="Chay ca 12 cau ngoai pham vi 126 (mac dinh KHONG)")
    ap.add_argument("--thu", action="store_true",
                    help="Chay thu: in ke hoach va chi phi uoc tinh, KHONG goi model, khong can API key")
    ap.add_argument("--tran-chi-usd", type=float,
                    help="Tran chi phi USD cho lan chay. BAT BUOC khi goi model that")
    ap.add_argument("--nguoi-duyet",
                    help="Ten nguoi duyet luot chay tra phi (AGENTS.md). BAT BUOC khi goi model that")
    ap.add_argument("--uoc-tinh-usd-moi-cau", type=float, default=UOC_TINH_USD_MOI_CAU)
    ap.add_argument("--rd-area-code", default="MB")
    ap.add_argument("--only", help="Chi chay cac ma nay, cach nhau dau phay (vd C01,M05)")
    ap.add_argument("--gioi-han", type=int, help="Chi chay N cau dau - de thu truoc khi chay het")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--resume", help="Duong dan file ket qua dang do - chay tiep cac cau con thieu")
    args = ap.parse_args()

    cases = doc_bo_cau_hoi()
    print("Doc duoc %d cau tu %s" % (len(cases), NGUON_CAU_HOI.name))
    cases = chon_cau(cases, only=args.only, gioi_han=args.gioi_han, ca_138=args.ca_138)

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

    can_chay = [c for c in cases if c["id"] not in da_co]
    theo_vai = Counter(c["role"] for c in can_chay)
    uoc = len(can_chay) * args.uoc_tinh_usd_moi_cau
    print()
    print("KE HOACH CHAY: %d cau (%s)%s" % (
        len(can_chay), ", ".join("%s %d" % (k, v) for k, v in sorted(theo_vai.items())),
        "" if args.ca_138 else " - pham vi 126, da bo 12 cau ngoai pham vi"))
    print("  C-Level          : khong gioi han vung/doi")
    print("  regional_director: mien %s" % args.rd_area_code)
    if args.qlv_employee_code:
        print("  qlv (ca nhom V)  : doi %s, mien %s" % (args.qlv_employee_code, args.qlv_area_code))
    else:
        print("  qlv V01-V32      : doi %s, mien %s" % (args.qlv_v01_v32, args.qlv_area_code))
        print("  qlv V33-V40      : doi %s, mien %s" % (args.qlv_v33_v40, args.qlv_area_code))
    print("  Uoc tinh         : %d x %.2f USD = %.2f USD" % (len(can_chay), args.uoc_tinh_usd_moi_cau, uoc))
    if args.thu:
        print("\nCHAY THU - khong goi model. Bo --thu va them --tran-chi-usd, --nguoi-duyet de chay that.")
        return 0

    if not args.tran_chi_usd or args.tran_chi_usd <= 0:
        print("LOI: goi model that bat buoc co --tran-chi-usd > 0 (AGENTS.md). Xem truoc bang --thu.")
        return 2
    if not (args.nguoi_duyet or "").strip():
        print("LOI: goi model that bat buoc co --nguoi-duyet (AGENTS.md: luot chay tra phi phai duoc duyet).")
        return 2
    if not _kiem_api_key():
        return 2
    if uoc > args.tran_chi_usd:
        print("LUU Y: uoc tinh %.2f USD vuot tran %.2f USD - se dung giua chung, chay tiep bang --resume."
              % (uoc, args.tran_chi_usd))
    tong_da_chi = sum(float(r.get("cost_usd") or 0.0) for r in da_co.values())
    meta = out.with_suffix(".meta.json")
    meta.write_text(json.dumps({
        "label": args.label, "nguoi_duyet": args.nguoi_duyet, "tran_chi_usd": args.tran_chi_usd,
        "bat_dau": time.strftime("%Y-%m-%d %H:%M:%S"), "ca_138": args.ca_138,
        "pham_vi": {"regional_director": args.rd_area_code,
                    "qlv": args.qlv_employee_code or {"V01-V32": args.qlv_v01_v32,
                                                      "V33-V40": args.qlv_v33_v40},
                    "qlv_area": args.qlv_area_code},
        "so_cau_se_chay": len(can_chay),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    helpers = _load_eval_helpers()
    # Lay duong dan log THANG tu module dang GHI - xem ghi chu dai trong run_tool_routing_sample.py.
    import cost_logger as _cl
    import query_engine as _qe
    helpers.COST_LOG = Path(_cl.LOG_PATH)
    helpers.AUDIT_LOG = Path(_qe.LOG_PATH)

    t0 = time.monotonic()
    max_cau = 0.0
    for i, case in enumerate(can_chay, 1):
        du_kien = max_cau if max_cau > 0 else args.uoc_tinh_usd_moi_cau
        if tong_da_chi + du_kien > args.tran_chi_usd:
            print("\nDUNG THEO TRAN: da chi %.4f USD, cau ke tiep du kien %.4f USD, tran %.2f USD."
                  % (tong_da_chi, du_kien, args.tran_chi_usd))
            print("Da luu %d cau. Xin duyet them roi chay tiep:" % len(da_co))
            print('  python scripts/run_bo_138_cau.py --resume "%s" --tran-chi-usd <tran_moi> '
                  '--nguoi-duyet "<ten>"' % out)
            return 6
        cid, role, question = case["id"], case["role"], case["question"]
        sid = "bo138-%s-%s-%s" % (args.label, cid, uuid.uuid4().hex[:8])
        con_lai = len(can_chay) - i
        uoc = (time.monotonic() - t0) / i * con_lai / 60 if i > 1 else 0
        print("[%d/%d] %s [%s] %s%s" % (i, len(can_chay), cid, role, question[:58],
                                        ("  (~%.0f phut nua)" % uoc) if uoc else ""), flush=True)
        role, scope_area, scope_emp = pham_vi_cho(case, args)
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
        loi_dung = loi_provider_can_dung(error)
        if loi_dung:
            print("\nDUNG: nha cung cap model dang chan luot chay (%s)." % loi_dung)
            print("Khong ghi cau loi nay vao ket qua. Cac cau truoc da duoc luu; khac phuc tai khoan")
            print("roi chay lai cung lenh voi --resume %s." % out)
            return 4
        chi_phi = float(helpers._cost_by_session({sid}).get(sid) or 0.0)
        da_co[cid] = {**case, "answer": answer, "error": error, "session_id": sid,
                      "scope_area_code": scope_area, "scope_employee_code": scope_emp,
                      "cost_usd": round(chi_phi, 6),
                      "duration_seconds": round(time.monotonic() - started, 2)}
        out.write_text(json.dumps(list(da_co.values()), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        if answer.strip() and not error and chi_phi <= 0:
            # Khong do duoc thi khong biet con bao nhieu duoi tran - dung, khong chay mu.
            print("\nDUNG: cau %s co tra loi nhung cost_log khong ghi chi phi cho session %s."
                  % (cid, sid))
            print("Khong kiem soat duoc tran chi phi nen dung. Kiem cost_logger roi chay tiep bang --resume.")
            return 5
        tong_da_chi += chi_phi
        max_cau = max(max_cau, chi_phi)
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
