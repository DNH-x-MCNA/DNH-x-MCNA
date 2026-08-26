# -*- coding: utf-8 -*-
"""So sanh hai vong do tool routing - KHONG goi API, khong ton tien.

25/08/2026: vong 1 het 1,4360 USD, vong 2 het 1,8539 USD (+29%) DU giua hai vong da deploy ban sua
gia cache theo TTL (le ra phai LAM GIAM chi phi). Script nay quy trach nhiem phan chenh lech ve tung
cau, thay vi doan.

Ba gia thuyet can phan biet:
  1. S13 gio goi tool that (thay vi SQL tay) -> payload tool lon hon -> ton hon. Neu dung: chenh lech
     tap trung o S13.
  2. Restart dich vu lam mat cache prompt -> vong 2 phai GHI lai cache tu dau. Neu dung: chenh lech
     rai deu moi cau, khong tap trung.
  3. Ban sua gia chua thuc su chay tren may 24. Neu dung: khong cau nao re di, ke ca cau khong doi.

Chay: python scripts/so_sanh_hai_vong_do.py <vong1.json> <vong2.json>
      (khong truyen tham so thi tu lay 2 file moi nhat trong results/)
"""
import glob
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _nap(duong_dan):
    rows = json.load(io.open(duong_dan, encoding="utf-8"))
    return {r["id"]: r for r in rows}


def main():
    if len(sys.argv) > 2:
        a, b = sys.argv[1], sys.argv[2]
    else:
        ung_vien = sorted(glob.glob(str(ROOT / "results" / "tool-routing-*.json")))
        if len(ung_vien) < 2:
            print("Can it nhat 2 file ket qua trong results/. Truyen duong dan lam tham so.")
            return 1
        a, b = ung_vien[-2], ung_vien[-1]

    print("Vong 1: %s" % os.path.basename(a))
    print("Vong 2: %s" % os.path.basename(b))
    print()

    v1, v2 = _nap(a), _nap(b)
    chung = [k for k in v2 if k in v1]
    if not chung:
        print("Hai file khong co cau nao trung ma - khong so sanh duoc.")
        return 1

    dong = []
    for k in chung:
        c1 = float(v1[k].get("cost_usd") or 0)
        c2 = float(v2[k].get("cost_usd") or 0)
        t1 = v1[k].get("tools_called") or []
        t2 = v2[k].get("tools_called") or []
        dong.append((c2 - c1, k, c1, c2, t1, t2))
    dong.sort(reverse=True)

    tong1 = sum(d[2] for d in dong)
    tong2 = sum(d[3] for d in dong)
    print("Tong vong 1: %.4f USD | tong vong 2: %.4f USD | chenh %+.4f USD" % (tong1, tong2, tong2 - tong1))
    print()

    print("%-6s %9s %9s %9s   %s" % ("CAU", "VONG1", "VONG2", "CHENH", "TOOL DA DOI"))
    print("-" * 78)
    for chenh, k, c1, c2, t1, t2 in dong:
        doi = "" if t1 == t2 else "%s -> %s" % (t1 or "(khong)", t2 or "(khong)")
        print("%-6s %9.4f %9.4f %+9.4f   %s" % (k, c1, c2, chenh, doi[:120]))

    print()
    print("=" * 78)
    print("DOC KET QUA")
    print("=" * 78)
    re_di = [d for d in dong if d[0] < -0.0001]
    dat_len = [d for d in dong if d[0] > 0.0001]
    khong_doi_tool = [d for d in dong if d[4] == d[5]]
    khong_doi_ma_dat_len = [d for d in khong_doi_tool if d[0] > 0.0001]

    print("  So cau RE hon: %d | DAT hon: %d | gan nhu khong doi: %d"
          % (len(re_di), len(dat_len), len(dong) - len(re_di) - len(dat_len)))
    if dong and dat_len and dong[0][0] > (tong2 - tong1) * 0.4:
        print("  >>> Chenh lech TAP TRUNG o cau %s (chiem %.0f%% muc tang) - hop voi gia thuyet 1:"
              % (dong[0][1], 100 * dong[0][0] / max(tong2 - tong1, 1e-9)))
        print("      cau do doi tu SQL tay sang goi tool that nen payload lon hon.")
    elif len(khong_doi_ma_dat_len) > len(dong) * 0.6:
        print("  >>> Muc tang RAI DEU o cac cau KHONG doi tool - hop voi gia thuyet 2:")
        print("      restart dich vu lam mat cache prompt, vong 2 phai ghi lai cache tu dau.")
        print("      Neu dung thi lan chay ke tiep (khong restart) se re han - kiem lai bang lan 3.")
    if not re_di:
        print("  >>> KHONG cau nao re di. Kiem lai ban sua gia da thuc su chay tren may 24 chua:")
        print("      cac dong log moi trong backend/logs/cost_log.jsonl phai co truong")
        print("      'cache_write_5m_tokens' khac null. Neu van null la ban sua CHUA duoc nap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
