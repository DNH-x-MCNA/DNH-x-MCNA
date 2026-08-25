# -*- coding: utf-8 -*-
"""Chan doan vi sao run_tool_routing_sample.py ra 0 tool / 0 dong - KHONG goi API, khong ton tien.

25/08/2026: chay that tren may 24 ba lan deu ra "1/25 (4%)" va chi phi $0.0000, trong y het model
chon sai tool hang loat. Da loai tru: thieu API key (key dung la key production ...J4dQAA), bo loc
chan du bao (chi 1/25 cau bi chan, dung thiet ke). Nghi van con lai: NGAN SACH THOI GIAN cua request
qua nho -> ask() thoat ngay o "if query_plan.expired(): break" (nl2sql.py:1665) TRUOC khi goi model,
nen tra ve cau tra loi binh thuong ma khong tool, khong ton tien.

Chay: python scripts/chan_doan_tool_routing.py [duong_dan_file_ket_qua.json]
"""
import glob
import io
import json
import os
import sys
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

for env_path in (BACKEND / ".env", ROOT / ".env"):
    if env_path.exists():
        with io.open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

print("=" * 72)
print("1. NGAN SACH THOI GIAN (nghi pham chinh)")
print("=" * 72)
for name, mac_dinh in (("CHAT_REQUEST_TIMEOUT_SECONDS", 110),
                        ("CHAT_LLM_TIMEOUT_SECONDS", 45),
                        ("CHAT_TOOL_TIMEOUT_SECONDS", 40)):
    raw = os.environ.get(name)
    print("  %-32s = %s" % (name, repr(raw) if raw is not None else "(khong dat -> mac dinh %s)" % mac_dinh))

import nl2sql  # noqa: E402

print()
print("  Gia tri THUC SU dang dung:")
print("    REQUEST_TIMEOUT_SECONDS  = %s giay" % nl2sql.REQUEST_TIMEOUT_SECONDS)
print("    LLM_CALL_TIMEOUT_SECONDS = %s giay" % nl2sql.LLM_CALL_TIMEOUT_SECONDS)
print("    TOOL_TIMEOUT_SECONDS     = %s giay" % nl2sql.TOOL_TIMEOUT_SECONDS)
if nl2sql.REQUEST_TIMEOUT_SECONDS < 30:
    print()
    print("  >>> DAY LA NGUYEN NHAN. Ngan sach ca request chi %s giay." % nl2sql.REQUEST_TIMEOUT_SECONDS)
    print("      ask() kiem 'query_plan.expired()' TRUOC khi goi model (nl2sql.py:1665) nen thoat")
    print("      ngay, tra ve cau tra loi binh thuong ma KHONG goi tool va KHONG ton tien.")
    print("      Sua: bo hoac dat lai CHAT_REQUEST_TIMEOUT_SECONDS=110 trong .env roi chay lai.")

print()
print("=" * 72)
print("2. CAU TRA LOI THUC TE (ask() da tra ve gi)")
print("=" * 72)
path = sys.argv[1] if len(sys.argv) > 1 else None
if not path:
    ung_vien = sorted(glob.glob(str(ROOT / "results" / "tool-routing-*.json")))
    path = ung_vien[-1] if ung_vien else None
if not path or not os.path.exists(path):
    print("  Khong tim thay file ket qua. Truyen duong dan lam tham so.")
else:
    print("  File: %s" % path)
    rows = json.load(io.open(path, encoding="utf-8"))
    for r in rows[:3]:
        print()
        print("  --- %s [%s] ---" % (r["id"], r["role"]))
        print("  tool da goi : %s" % (r.get("tools_called") or "(khong co)"))
        print("  chi phi     : %s USD" % r.get("cost_usd"))
        print("  thoi gian   : %s giay" % r.get("duration_seconds"))
        if r.get("error"):
            print("  LOI         : %s" % str(r["error"])[:200])
        print("  cau tra loi : %s" % (r.get("answer") or "(rong)")[:400].replace("\n", " "))

print()
print("=" * 72)
print("3. SO CHI PHI GHI DUOC TRONG 15 PHUT GAN NHAT")
print("=" * 72)
import datetime as dt
log = BACKEND / "logs" / "cost_log.jsonl"
print("  Duong dan: %s (ton tai: %s)" % (log, log.is_file()))
if log.is_file():
    moc = dt.datetime.now() - dt.timedelta(minutes=15)
    dem = 0
    tong = 0.0
    with io.open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                item = json.loads(line)
                if dt.datetime.fromisoformat(item["ts"]) >= moc:
                    dem += 1
                    tong += float(item.get("cost_usd") or 0)
            except Exception:
                continue
    print("  So dong ghi trong 15 phut gan nhat: %d (tong %.4f USD)" % (dem, tong))
    if dem == 0:
        print("  >>> KHONG co dong nao: xac nhan KHONG lan goi model nao thanh cong.")
