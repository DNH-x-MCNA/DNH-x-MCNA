"""Truy nguon cac luot goi model KHONG co username - doc log, KHONG goi model tra phi.

Chay THANG tren may 24:
    python C:\\dnh_chatbot\\scripts\\truy_luot_khong_ten.py

Vi sao: AGENTS.md bat buoc moi luot goi model tra phi phai co `username` rieng va `session_id` co
tien to nhan dien duoc; thieu thi ket qua KHONG dung de cham UAT. Log con khoang 133.300d cac luot
`unknown` (8 luot toi 13/09 va mot cum 11/09) chua truy duoc ai chay.

BA NGUON, BA HE GIO KHAC NHAU - lan la sai ngay:
  cost_log.jsonl   `ts`         : gio DIA PHUONG (dt.datetime.now())
  audit_log.jsonl               : gio DIA PHUONG
  query_runs.created_at         : gio UTC  (= gio dia phuong - 7)

Cach truy: mot session co the co ca luot co ten lan luot khong ten. Neu MOI luot co ten trong cung
session deu thuoc duy nhat mot nguoi thi quy ca session cho nguoi do - dung logic ma
conversation_memory.py dang dung de gan owner cho session cu. Neu session khong co luot nao co ten
thi ghi ro la KHONG truy duoc, khong doan bua.
"""
import datetime as dt
import json
import os
import sqlite3
import sys

for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

GOC = os.environ.get("DNH_ROOT", r"C:\dnh_chatbot")
COST_LOG = os.path.join(GOC, "backend", "logs", "cost_log.jsonl")
AUDIT_LOG = os.path.join(GOC, "backend", "logs", "audit_log.jsonl")
MEMORY_DB = os.path.join(GOC, "backend", "memory.db")

# Ten khong quy duoc cho ai. 'alice/test/admin' la ten mau trong tai lieu va smoke test.
TEN_KHONG_HOP_LE = {"", "unknown", "alice", "test", "admin", "none", "null"}

# Ty gia de doi USD ra VND cho de doc. Chi de uoc luong, khong dung de quyet toan.
VND_MOI_USD = float(os.environ.get("DNH_VND_PER_USD", "25000"))


def _vnd(usd):
    """Doi USD ra chuoi VND. Dung round() chu khong int(): 1.15*25000 ra 28749.999... trong so thuc,
    int() cat cut thanh 28.749 - sai 1 dong va nhin nhu loi tinh."""
    return format(round(usd * VND_MOI_USD), ",d").replace(",", ".")


def _doc_jsonl(duong_dan):
    if not os.path.exists(duong_dan):
        print("  (khong thay %s)" % duong_dan)
        return []
    dong = []
    with open(duong_dan, encoding="utf-8", errors="replace") as f:
        for so, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                dong.append(json.loads(raw))
            except ValueError:
                print("  (bo qua dong %d khong phai JSON hop le)" % so)
    return dong


def _ten_hop_le(ten):
    return str(ten or "").strip().lower() not in TEN_KHONG_HOP_LE


def _chu_session_tu_query_runs():
    """session_id -> ten chu, suy tu query_runs. Chi nhan khi session chi thuoc DUY NHAT mot nguoi."""
    if not os.path.exists(MEMORY_DB):
        print("  (khong thay %s - bo qua buoc doi chieu query_runs)" % MEMORY_DB)
        return {}
    con = sqlite3.connect(MEMORY_DB)
    con.row_factory = sqlite3.Row
    chu = {}
    try:
        rows = con.execute(
            "SELECT session_id, username, COUNT(*) n FROM query_runs GROUP BY session_id, username")
        gom = {}
        for r in rows:
            if _ten_hop_le(r["username"]):
                gom.setdefault(r["session_id"], set()).add(r["username"])
        for sid, ten in gom.items():
            if len(ten) == 1:
                chu[sid] = next(iter(ten))
    except sqlite3.OperationalError as loi:
        print("  (khong doc duoc query_runs: %s)" % loi)
    finally:
        con.close()
    return chu


def _chu_session_tu_audit(audit):
    gom = {}
    for e in audit:
        sid = e.get("session_id")
        ten = e.get("username") or e.get("user")
        if sid and _ten_hop_le(ten):
            gom.setdefault(sid, set()).add(ten)
    return {sid: next(iter(t)) for sid, t in gom.items() if len(t) == 1}


def main():
    print("=" * 78)
    print("TRUY NGUON CAC LUOT GOI MODEL KHONG CO USERNAME")
    print("=" * 78)
    print("Goc: %s" % GOC)
    print()

    cost = _doc_jsonl(COST_LOG)
    if not cost:
        sys.exit("Khong doc duoc cost_log.jsonl - khong co gi de truy.")
    audit = _doc_jsonl(AUDIT_LOG)
    print("Doc duoc %d dong cost_log, %d dong audit_log." % (len(cost), len(audit)))
    print()

    khong_ten = [e for e in cost if not _ten_hop_le(e.get("username"))]
    if not khong_ten:
        print("Khong con dong nao thieu username trong cost_log. Tot.")
        return

    tong_usd = sum(float(e.get("cost_usd") or 0) for e in khong_ten)
    print("So dong thieu username : %d / %d" % (len(khong_ten), len(cost)))
    print("Tong chi phi           : %.4f USD  (~%s VND)" % (tong_usd, _vnd(tong_usd)))
    print()

    chu_qr = _chu_session_tu_query_runs()
    chu_audit = _chu_session_tu_audit(audit)

    theo_session = {}
    for e in khong_ten:
        theo_session.setdefault(e.get("session_id") or "(khong co session_id)", []).append(e)

    print("=" * 78)
    print("THEO SESSION")
    print("=" * 78)
    truy_duoc, khong_truy_duoc = 0.0, 0.0
    for sid, ds in sorted(theo_session.items(), key=lambda kv: min(str(x.get("ts")) for x in kv[1])):
        ts = sorted(str(x.get("ts") or "") for x in ds)
        tien = sum(float(x.get("cost_usd") or 0) for x in ds)
        chu = chu_qr.get(sid) or chu_audit.get(sid)
        nguon = "query_runs" if chu_qr.get(sid) else ("audit_log" if chu_audit.get(sid) else None)
        print()
        print("session %s" % sid)
        print("  %d luot | %s -> %s (gio dia phuong) | %.4f USD" % (
            len(ds), ts[0][:19], ts[-1][:19], tien))
        if chu:
            truy_duoc += tien
            print("  => QUY DUOC cho: %s  (suy tu %s, session chi thuoc mot nguoi)" % (chu, nguon))
        else:
            khong_truy_duoc += tien
            print("  => KHONG truy duoc: session nay khong co luot nao mang ten hop le.")
        for x in ds[:5]:
            print("     %s | %-22s | %.4f USD | %s" % (
                str(x.get("ts"))[:19], str(x.get("model"))[:22],
                float(x.get("cost_usd") or 0), (x.get("question_preview") or "")[:60]))
        if len(ds) > 5:
            print("     ... con %d luot" % (len(ds) - 5))

    print()
    print("=" * 78)
    print("TONG KET")
    print("=" * 78)
    print("Quy duoc cho nguoi cu the : %.4f USD (~%s VND)" % (truy_duoc, _vnd(truy_duoc)))
    print("Khong truy duoc           : %.4f USD (~%s VND)" % (khong_truy_duoc, _vnd(khong_truy_duoc)))
    print()
    print(">> Phan KHONG truy duoc: theo AGENTS.md cac luot nay khong dung de cham UAT.")
    print(">> Doi chieu gio DIA PHUONG o tren voi lich lam viec/lich chay script de khoanh nguoi.")
    print(">> Tu PR #65, luot thieu username bi CHAN truoc khi goi model - danh sach nay chi con")
    print(">> gia tri truy nguon lich su, khong nen dai them.")


if __name__ == "__main__":
    main()
