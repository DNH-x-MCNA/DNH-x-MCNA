# -*- coding: utf-8 -*-
"""
Doc + tong hop chi phi AI tu logs/cost_log.jsonl (cost_logger.py chi GHI, day la choc DOC dau tien).
Phuc vu cam ket uoc tinh chi phi go-live (tuan 8-10).

BA LUU Y QUAN TRONG (khac voi "dem so dong log"):
  1. MOT cau hoi sinh 8-9 dong log (moi vong goi tool 1 dong) -> KHONG dem dong = so cau hoi. Gop
     theo (session_id, question_preview) de uoc luong so LUOT HOI, cost/luot = tong cac dong cua luot.
  2. Log KHONG co username, chi co session_id -> noi qua bang sessions trong memory.db
     (conversation_memory.py) de quy ve nguoi dung.
  3. Gia Sonnet hien la GIA GIOI THIEU, tang ~50% sau 31/08/2026 -> ban uoc tinh go-live PHAI dung
     gia SAU khuyen mai. Script in CA HAI: chi phi thuc te da phat sinh (gia hien tai) va chi phi
     DU KIEN neu tinh theo gia sau khuyen mai.

Chay:  py cost_report.py [--days N] [--by-user] [--top N]
"""
import os, sys, json, argparse, sqlite3, datetime as dt
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from cost_logger import LOG_PATH
from pricing import MODEL_PRICING

# Gia SAU khi het khuyen mai (Sonnet 5 tang tu 31/08/2026: input $2->$3, output $10->$15, cache theo
# ty le tuong ung). Haiku/Opus giu nguyen (chua cong bo tang). Dieu chinh lai neu Anthropic cong bo khac.
POST_PROMO_PRICING = {
    **{k: dict(v) for k, v in MODEL_PRICING.items()},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
}


def _cost(pricing, model, it, ot, cr, cw):
    p = pricing.get(model)
    if not p:
        return 0.0
    return (it / 1e6 * p["input"] + ot / 1e6 * p["output"]
            + cr / 1e6 * p["cache_read"] + cw / 1e6 * p["cache_write"])


def _session_owner_map():
    """session_id -> owner_username tu memory.db (bang sessions). Session chua dang ky -> khong co
    trong map (quy ve '(khong ro)')."""
    try:
        from conversation_memory import DB_PATH as MEM_DB
    except Exception:
        MEM_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")
    m = {}
    if os.path.exists(MEM_DB):
        try:
            conn = sqlite3.connect(MEM_DB)
            for sid, owner in conn.execute("SELECT session_id, owner_username FROM sessions"):
                m[sid] = owner
            conn.close()
        except Exception as e:
            print(f"[canh bao] Khong doc duoc bang sessions: {e}")
    return m


def load_entries(days=None):
    if not os.path.exists(LOG_PATH):
        print(f"Khong tim thay {LOG_PATH} - chua co du lieu chi phi (hoac chua deploy/chay chatbot).")
        return []
    cutoff = None
    if days:
        cutoff = dt.datetime.now() - dt.timedelta(days=days)
    out = []
    for line in open(LOG_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if cutoff:
            try:
                if dt.datetime.fromisoformat(e["ts"]) < cutoff:
                    continue
            except Exception:
                pass
        out.append(e)
    return out


def report(days=None, by_user=False, top=10):
    entries = load_entries(days)
    if not entries:
        return
    owners = _session_owner_map()

    n_calls = len(entries)
    total_now = total_post = 0.0
    by_model = defaultdict(lambda: {"calls": 0, "now": 0.0, "post": 0.0})
    # gop theo luot hoi: (session_id, question_preview)
    turns = defaultdict(lambda: {"now": 0.0, "post": 0.0, "calls": 0, "owner": None, "q": ""})
    by_user_agg = defaultdict(lambda: {"now": 0.0, "post": 0.0, "turns": set(), "calls": 0})

    for e in entries:
        it = e.get("input_tokens", 0) or 0; ot = e.get("output_tokens", 0) or 0
        cr = e.get("cache_read_tokens", 0) or 0; cw = e.get("cache_write_tokens", 0) or 0
        model = e.get("model", "")
        c_now = e.get("cost_usd")
        if c_now is None:
            c_now = _cost(MODEL_PRICING, model, it, ot, cr, cw)
        c_post = _cost(POST_PROMO_PRICING, model, it, ot, cr, cw)
        total_now += c_now; total_post += c_post
        by_model[model]["calls"] += 1; by_model[model]["now"] += c_now; by_model[model]["post"] += c_post

        sid = e.get("session_id", "") or ""
        owner = owners.get(sid, "(khong ro)")
        key = (sid, e.get("question_preview", ""))
        t = turns[key]
        t["now"] += c_now; t["post"] += c_post; t["calls"] += 1
        t["owner"] = owner; t["q"] = e.get("question_preview", "")

        u = by_user_agg[owner]
        u["now"] += c_now; u["post"] += c_post; u["calls"] += 1; u["turns"].add(key)

    n_turns = len(turns)
    n_sessions = len({k[0] for k in turns})
    ds = sorted(e["ts"] for e in entries)

    print("=" * 68)
    print("BAO CAO CHI PHI AI" + (f" (─ {days} ngay gan nhat)" if days else " (toan bo lich su)"))
    print("=" * 68)
    print(f"Khoang thoi gian : {ds[0][:19]}  ->  {ds[-1][:19]}")
    print(f"So loi goi API   : {n_calls:,}")
    print(f"So LUOT HOI (uoc): {n_turns:,}  (gop theo session+cau hoi; ~{n_calls/max(n_turns,1):.1f} goi API/luot)")
    print(f"So phien chat    : {n_sessions:,}")
    print("-" * 68)
    print(f"CHI PHI THUC TE (gia hien tai)        : ${total_now:,.4f}")
    print(f"CHI PHI DU KIEN (gia SAU 31/08/2026)  : ${total_post:,.4f}  (+{(total_post/total_now-1)*100:.0f}% neu chi phi tang)"
          if total_now else "")
    if n_turns:
        print(f"Trung binh moi luot hoi (hien tai)    : ${total_now/n_turns:.4f}")
        print(f"Trung binh moi luot hoi (sau KM)      : ${total_post/n_turns:.4f}")
    print("-" * 68)
    print("Theo model:")
    for model, v in sorted(by_model.items(), key=lambda x: -x[1]["now"]):
        print(f"  {model:22s} {v['calls']:>6,} goi  ${v['now']:>10,.4f} (hien tai)  ${v['post']:>10,.4f} (sau KM)")

    if by_user:
        print("-" * 68)
        print("Theo nguoi dung (noi qua bang sessions):")
        print(f"  {'Nguoi dung':22s} {'Luot':>6} {'Goi':>7} {'Hien tai':>12} {'Sau KM':>12}")
        for owner, v in sorted(by_user_agg.items(), key=lambda x: -x[1]["now"]):
            print(f"  {owner:22s} {len(v['turns']):>6,} {v['calls']:>7,} ${v['now']:>10,.4f} ${v['post']:>10,.4f}")

    print("-" * 68)
    print(f"Top {top} luot hoi DAT NHAT (gia hien tai):")
    for (sid, q), t in sorted(turns.items(), key=lambda x: -x[1]["now"])[:top]:
        print(f"  ${t['now']:.4f} ({t['calls']} goi) [{t['owner']}] {t['q'][:70]}")
    print("=" * 68)
    print("LUU Y: 'so luot hoi' la UOC LUONG (gop theo session_id + text cau hoi) - 2 luot hoi trung "
          "text trong cung phien se bi dem lam 1. Chi phi tong khong bi anh huong boi cach gop nay.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="Chi tinh N ngay gan nhat (mac dinh: toan bo)")
    ap.add_argument("--by-user", action="store_true", help="Tach chi phi theo nguoi dung")
    ap.add_argument("--top", type=int, default=10, help="So luot hoi dat nhat can liet ke")
    a = ap.parse_args()
    report(days=a.days, by_user=a.by_user, top=a.top)
