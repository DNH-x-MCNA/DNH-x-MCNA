"""Cost of Value (hop 24/09/2026, anh Long: "khong gioi han so cau hoi, toi uu gia tri tren moi dong chi phi").

MIEN PHI, CHI DOC - khong goi model. Chay THANG tren may 24:
    python C:\\dnh_chatbot\\scripts\\phan_tich_cost_of_value.py [--tu 2026-09-01] [--den 2026-09-30] [--ca-kiem-thu]

Noi ba nguon, moi nguon chi co mot phan su that:
  - logs/cost_log.jsonl: MOT DONG = MOT VONG goi model (mot cau hoi 3-9 dong) -> gop theo (session_id, cau hoi).
  - memory.db query_runs: trang thai luot (completed/partial_timeout/error/...), tool da goi (sql_used_json), cau tra loi.
  - auth.db users: vai tro (c_level/regional_director/qlv/admin_ops).
Gio: cost_log ghi gio DIA PHUONG, query_runs ghi UTC (lech 7 tieng) -> ghep theo session_id + cau hoi + thu tu,
khong ghep theo gio.

"Khong ra gia tri" = het gio, loi, huy/treo, hoac chi hoi lai (khong goi tool nao, cau tra loi ket bang dau hoi).
Tool goi trung = cung ten tool va cung tham so goi >= 2 lan trong mot luot.
Luot kiem thu (username/session co tien to cham-/kiemtra-/uat-, hoac khong co username) mac dinh bi LOAI;
them --ca-kiem-thu de xem ca hai.
"""
import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

GOC = Path(__file__).resolve().parents[1]
BACKEND = GOC / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))

try:
    from pricing import USD_TO_VND_RATE
except Exception:  # chay rieng khong co backend
    USD_TO_VND_RATE = 26334.50
try:
    from query_plan import infer_domains
except Exception:
    infer_domains = None

COST_LOG = os.environ.get("DNH_COST_LOG", str(BACKEND / "logs" / "cost_log.jsonl"))
MEMORY_DB = os.environ.get("DNH_MEMORY_DB", str(BACKEND / "memory.db"))
AUTH_DB = os.environ.get("DNH_AUTH_DB", str(BACKEND / "auth.db"))
KHONG_GIA_TRI = {"het_gio", "loi", "huy_treo", "chi_hoi_lai"}
# Tien to session_id/username cua cac script (26/09: ban dau thieu "chamlai" -> luot cham lai UAT, chay bang tai
# khoan THAT dnh/danh.nguyen..., bi tinh la nguoi dung that). Nguon: cham_lai_uat.py "chamlai<ngay>-<ma>",
# run_bo_138_cau.py "bo138-", business-eval "beval-" + username business-eval, run_complex_evaluation "complex-",
# run_tool_routing_sample "routing-", evaluate_model_canary "canary-", verify_fixes "verify", tool check "kiemtra-".
TIEN_TO_KIEM_THU = ("chamlai", "cham-", "cham_", "kiemtra", "bo138-", "beval-", "business-eval", "complex-",
                    "routing-", "canary-", "verify", "uat-", "uat_", "test-", "test_", "eval-")


def _plain(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _loai_cau(cau: str) -> str:
    p = _plain(cau)
    if any(m in p for m in ("so sanh", "so voi", "cung ky", "tang giam", "tang/giam", "bien dong")):
        return "so_sanh"
    if infer_domains is not None:
        try:
            return infer_domains(cau)[0]["domain"]
        except Exception:
            pass
    return "khac"


def _doc_cost_log(tu: str, den: str) -> dict:
    """(session_id, cau hoi[:120]) -> danh sach luot, moi luot = cac vong lien tiep (cach nhau < 10 phut)."""
    theo_khoa = defaultdict(list)
    if not os.path.exists(COST_LOG):
        print(f"[canh bao] Khong thay {COST_LOG}")
        return {}
    with open(COST_LOG, encoding="utf-8") as f:
        for dong in f:
            try:
                e = json.loads(dong)
            except ValueError:
                continue
            ts = str(e.get("ts") or "")
            if not (tu <= ts[:10] <= den):
                continue
            khoa = (e.get("session_id") or "", (e.get("question_preview") or "")[:120])
            theo_khoa[khoa].append(e)
    luot = {}
    for khoa, ds in theo_khoa.items():
        ds.sort(key=lambda e: e["ts"])
        nhom, truoc = [], None
        for e in ds:
            t = dt.datetime.fromisoformat(e["ts"][:19])
            if truoc is None or (t - truoc).total_seconds() > 600:
                nhom.append([])
            nhom[-1].append(e)
            truoc = t
        luot[khoa] = nhom
    return luot


def _doc_query_runs(tu: str, den: str) -> dict:
    kq = defaultdict(list)
    if not os.path.exists(MEMORY_DB):
        print(f"[canh bao] Khong thay {MEMORY_DB}")
        return kq
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row
    # created_at UTC: noi rong 1 ngay moi dau de khong mat luot gan nua dem gio dia phuong.
    for r in conn.execute("SELECT query_id, session_id, username, question, answer, status, sql_used_json, "
                          "duration_ms, created_at, error_message FROM query_runs WHERE substr(created_at,1,10) BETWEEN ? AND ? "
                          "ORDER BY created_at", ((dt.date.fromisoformat(tu) - dt.timedelta(days=1)).isoformat(), den)):
        kq[(r["session_id"] or "", (r["question"] or "")[:120])].append(dict(r))
    conn.close()
    return kq


def _vai_tro() -> dict:
    if not os.path.exists(AUTH_DB):
        return {}
    conn = sqlite3.connect(AUTH_DB)
    kq = {u: (role or "?") for u, role in conn.execute("SELECT username, role FROM users")}
    conn.close()
    return kq


def _ket_qua_luot(run: dict | None) -> str:
    if run is None:
        return "khong_co_query_run"
    st = (run.get("status") or "").lower()
    if st in ("partial_timeout", "timeout"):
        return "het_gio"
    if st in ("error", "api_credit_exhausted"):
        return "loi"
    if st in ("cancelled", "abandoned", "running"):
        return "huy_treo"
    tools = _tools(run)
    tra_loi = (run.get("answer") or "").strip()
    if not tools and tra_loi and "?" in tra_loi[-300:]:
        return "chi_hoi_lai"
    return "tra_loi"


def _tools(run: dict | None) -> list:
    if not run:
        return []
    try:
        ds = json.loads(run.get("sql_used_json") or "[]")
    except ValueError:
        return []
    return [str(x) for x in ds if x]


def _goi_trung(tools: list) -> int:
    dem = defaultdict(int)
    for t in tools:
        dem[re.sub(r"\s+", "", t)] += 1
    return sum(n - 1 for n in dem.values() if n > 1)


def _gio_dia_phuong(utc_text):
    """query_runs.created_at la UTC; cost_log ghi gio may 24 (UTC+7)."""
    try:
        return dt.datetime.fromisoformat(str(utc_text or "")[:19]) + dt.timedelta(hours=7)
    except ValueError:
        return None


def _nguon(user: str, sid: str) -> str:
    for tt in TIEN_TO_KIEM_THU:
        if (user or "").lower().startswith(tt) or (sid or "").lower().startswith(tt):
            return "kiem_thu:" + tt.strip("-_")
    return "kiem_thu:khong_ten" if not user else "that"


def _nhom_loi(msg: str) -> str:
    """Gom thong diep loi: bo so/ma de cac lan cung mot loai loi ve mot dong."""
    m = re.sub(r"req_[A-Za-z0-9]+|\b[0-9a-f]{8,}\b", "<id>", msg or "")
    m = re.sub(r"\d+", "N", m)
    return re.sub(r"\s+", " ", m).strip()[:110] or "(khong ghi loi)"


def main():
    ap = argparse.ArgumentParser()
    homnay = dt.date.today()
    ap.add_argument("--tu", default=homnay.replace(day=1).isoformat())
    ap.add_argument("--den", default=homnay.isoformat())
    ap.add_argument("--ca-kiem-thu", action="store_true")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()

    cost = _doc_cost_log(a.tu, a.den)
    runs = _doc_query_runs(a.tu, a.den)
    vai_tro = _vai_tro()

    luot_ds = []
    for khoa, nhom in cost.items():
        # Ghep theo GIO, khong theo thu tu (26/09): cham lai UAT dung CUNG session+cau hoi cho nhieu lan chay; lan
        # 24/09 hong ket noi (0 dong cost) da an chi phi cua lan chay sau -> 18 luot "Connection error." 76.343d gia.
        ds_run = [(r, _gio_dia_phuong(r.get("created_at"))) for r in runs.get(khoa, [])]
        for vong in nhom:
            bat_dau = dt.datetime.fromisoformat(vong[0]["ts"][:19])
            ung_vien = [(t, r) for r, t in ds_run if t and t <= bat_dau + dt.timedelta(seconds=90)]
            run = max(ung_vien, key=lambda x: x[0])[1] if ung_vien else None
            user = (vong[0].get("username") or (run or {}).get("username") or "").strip()
            sid = khoa[0]
            kiem_thu = _nguon(user, sid) != "that"
            if kiem_thu and not a.ca_kiem_thu:
                continue
            usd = sum(float(e.get("cost_usd") or 0) for e in vong)
            tools = _tools(run)
            luot_ds.append({
                "ts": vong[0]["ts"][:16], "user": user or "(khong ten)", "vai_tro": vai_tro.get(user, "?"),
                "cau": khoa[1], "loai": _loai_cau(khoa[1]), "vnd": usd * USD_TO_VND_RATE, "so_vong": len(vong),
                "ket_qua": _ket_qua_luot(run), "so_tool": len(tools), "goi_trung": _goi_trung(tools),
                "giay": round((run or {}).get("duration_ms") or 0) / 1000 if run else None,
                "kiem_thu": kiem_thu, "loi": ((run or {}).get("error_message") or "").strip(),
                "nguon": _nguon(user, sid),
            })

    if not luot_ds:
        print("Khong co luot nao trong khoang da chon.")
        return
    tong = sum(l["vnd"] for l in luot_ds)
    phi_gia_tri = [l for l in luot_ds if l["ket_qua"] in KHONG_GIA_TRI]
    print("=" * 100)
    print(f"COST OF VALUE {a.tu} -> {a.den} | {len(luot_ds)} luot | tong {tong:,.0f}d | "
          f"TB {tong / len(luot_ds):,.0f}d/luot | ty gia {USD_TO_VND_RATE:,.0f}"
          + (" | GOM CA KIEM THU" if a.ca_kiem_thu else " | da loai luot kiem thu"))
    print(f"Khong ra gia tri: {len(phi_gia_tri)} luot ({len(phi_gia_tri) / len(luot_ds):.0%}), "
          f"{sum(l['vnd'] for l in phi_gia_tri):,.0f}d ({sum(l['vnd'] for l in phi_gia_tri) / tong:.0%} chi phi)")
    print("=" * 100)

    def _bang(tieu_de, khoa_fn):
        g = defaultdict(list)
        for l in luot_ds:
            g[khoa_fn(l)].append(l)
        print(f"\n{tieu_de}")
        print(f"  {'nhom':<34}{'luot':>6}{'tong d':>13}{'TB d/luot':>11}{'% khong GT':>11}{'d khong GT':>12}{'vong TB':>8}")
        for k, ds in sorted(g.items(), key=lambda x: -sum(l["vnd"] for l in x[1])):
            s = sum(l["vnd"] for l in ds)
            kg = [l for l in ds if l["ket_qua"] in KHONG_GIA_TRI]
            print(f"  {str(k)[:33]:<34}{len(ds):>6}{s:>13,.0f}{s / len(ds):>11,.0f}{len(kg) / len(ds):>11.0%}"
                  f"{sum(l['vnd'] for l in kg):>12,.0f}{sum(l['so_vong'] for l in ds) / len(ds):>8.1f}")

    _bang("THEO VAI TRO", lambda l: l["vai_tro"])
    _bang("THEO LOAI CAU HOI", lambda l: l["loai"])
    _bang("VAI TRO x LOAI", lambda l: f"{l['vai_tro']} / {l['loai']}")
    _bang("THEO KET QUA", lambda l: l["ket_qua"])

    if a.ca_kiem_thu:
        _bang("THEO NGUON (that / kiem thu theo tien to)", lambda l: l["nguon"])

    print("\nLOI / HUY / HET GIO THEO NOI DUNG (error_message trong query_runs)")
    g = defaultdict(list)
    for l in luot_ds:
        if l["ket_qua"] in ("loi", "huy_treo", "het_gio"):
            g[(l["ket_qua"], _nhom_loi(l["loi"]))].append(l)
    for (kq, msg), ds in sorted(g.items(), key=lambda x: -sum(l["vnd"] for l in x[1])):
        ngay = sorted({l["ts"][:10] for l in ds})
        print(f"  {len(ds):>3} luot {sum(l['vnd'] for l in ds):>9,.0f}d {kq:<9} {ngay[0][5:]}..{ngay[-1][5:]}  {msg}")

    khong_ro = defaultdict(list)
    for l in luot_ds:
        if l["vai_tro"] == "?":
            khong_ro[l["user"]].append(l)
    if khong_ro:
        print("\nUSERNAME KHONG CO TRONG auth.db (vai tro '?')")
        for u, ds in sorted(khong_ro.items(), key=lambda x: -sum(l["vnd"] for l in x[1]))[:15]:
            ngay = sorted({l["ts"][:10] for l in ds})
            print(f"  {u[:28]:<28} {len(ds):>4} luot {sum(l['vnd'] for l in ds):>10,.0f}d  {ngay[0]}..{ngay[-1]}")

    trung = [l for l in luot_ds if l["goi_trung"]]
    print(f"\nTOOL GOI TRUNG: {len(trung)} luot, {sum(l['goi_trung'] for l in trung)} lan goi thua, "
          f"cac luot do tong {sum(l['vnd'] for l in trung):,.0f}d")

    print(f"\nTOP {a.top} LUOT DAT NHAT KHONG RA GIA TRI")
    for l in sorted(phi_gia_tri, key=lambda l: -l["vnd"])[:a.top]:
        print(f"  {l['ts']} {l['vnd']:>8,.0f}d {l['ket_qua']:<12} {l['so_vong']}v {l['so_tool']}t "
              f"{l['vai_tro']:<17} {l['user'][:16]:<16} {l['cau'][:70]}")
    print(f"\nTOP {a.top} LUOT DAT NHAT CO TRA LOI (xem co dang gia khong)")
    for l in sorted([l for l in luot_ds if l["ket_qua"] == "tra_loi"], key=lambda l: -l["vnd"])[:a.top]:
        print(f"  {l['ts']} {l['vnd']:>8,.0f}d {l['so_vong']}v {l['so_tool']}t trung={l['goi_trung']} "
              f"{l['vai_tro']:<17} {l['cau'][:80]}")
    khong_noi = sum(1 for l in luot_ds if l["ket_qua"] == "khong_co_query_run")
    if khong_noi:
        print(f"\n[luu y] {khong_noi} luot co chi phi nhung khong ghep duoc query_runs (luot truoc khi co "
              "query_runs, hoac cau hoi bi sua giua chung) - ket qua ghi 'khong_co_query_run'.")


if __name__ == "__main__":
    main()
