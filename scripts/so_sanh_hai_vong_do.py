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


def _doc_token_cache(so_phut_gan_nhat=120):
    """Doc backend/logs/cost_log.jsonl de CHOT bang so lieu thay vi suy luan tu chi phi.

    Ghi cache va doc cache chenh nhau 10-20 lan don gia, nen chi can nhin ty le
    cache_write/cache_read la biet mot dot tang chi phi co phai do phai ghi lai cache khong.
    """
    import datetime as dt
    log = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend")) / "logs" / "cost_log.jsonl"
    if not log.is_file():
        log = ROOT / "backend" / "logs" / "cost_log.jsonl"
    if not log.is_file():
        return None
    moc = dt.datetime.now() - dt.timedelta(minutes=so_phut_gan_nhat)
    rows = []
    with io.open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
                if dt.datetime.fromisoformat(r["ts"]) >= moc:
                    rows.append(r)
            except Exception:
                continue
    return rows



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
    doi_tool = [d for d in dong if d[4] != d[5]]
    tang_ma_KHONG_doi_tool = [d for d in dat_len if d[4] == d[5]]
    muc_tang = tong2 - tong1

    print("  So cau RE hon: %d | DAT hon: %d | gan nhu khong doi: %d"
          % (len(re_di), len(dat_len), len(dong) - len(re_di) - len(dat_len)))
    print("  So cau DOI tool: %d" % len(doi_tool))

    # Trung vi quan trong hon trung binh: vai cau phai GHI cache keo trung binh len rat manh,
    # dung trung binh de lap ke hoach ngan sach la uoc qua tay.
    cot2 = sorted(d[3] for d in dong)
    trung_vi = cot2[len(cot2) // 2]
    print("  Chi phi vong 2: trung binh %.4f USD/cau, TRUNG VI %.4f USD/cau"
          % (tong2 / len(dong), trung_vi))
    print("    -> dung TRUNG VI de lap ke hoach ngan sach; trung binh bi vai cau ghi cache keo len.")

    print()
    # Gia thuyet 1 CHI dung neu cau tang manh nhat THUC SU doi tool - truoc day cho nay chi xet muc
    # do tap trung nen tung ket luan sai (bao cau S01 "doi tu SQL sang tool" trong khi tool y nguyen).
    tang_do_doi_tool = sum(d[0] for d in doi_tool if d[0] > 0)
    tang_khong_doi_tool = sum(d[0] for d in tang_ma_KHONG_doi_tool)
    print("  Muc tang chia ra:")
    print("    do cau DOI tool          : %+.4f USD (%d cau)" % (tang_do_doi_tool, len([d for d in doi_tool if d[0] > 0])))
    print("    do cau KHONG doi tool    : %+.4f USD (%d cau)" % (tang_khong_doi_tool, len(tang_ma_KHONG_doi_tool)))

    print()
    if tang_khong_doi_tool > tang_do_doi_tool:
        print("  >>> Phan lon muc tang den tu cac cau KHONG he doi tool.")
        print("      Day la dau hieu GHI LAI CACHE, khong phai model lam nhieu viec hon. Cache prompt")
        print("      nam tren may chu Anthropic va duoc dinh danh theo NOI DUNG tien to prompt - nen")
        print("      restart dich vu KHONG xoa cache, nhung SUA MO TA TOOL / system prompt thi lam")
        print("      hong tien to do va moi VAI phai ghi lai cache tu dau.")
        top_khong_doi = [d for d in tang_ma_KHONG_doi_tool][:3]
        if top_khong_doi:
            print("      Cac cau tra gia ghi cache: %s" % ", ".join(d[1] for d in top_khong_doi))
        print("      HE QUA VAN HANH: day la chi phi MOT LAN moi dot sua prompt, khong phai muc chi")
        print("      phi moi. Lan chay ke tiep (khong sua gi them) phai tro ve muc cu - kiem bang lan 3.")
    elif doi_tool and tang_do_doi_tool > 0:
        print("  >>> Muc tang chu yeu den tu cac cau DOI tool: %s"
              % ", ".join(d[1] for d in doi_tool if d[0] > 0))
        print("      Day la muc tang THUC va LAU DAI: goi tool that tra ve payload lon hon SQL tay.")

    print()
    if not re_di:
        print("  >>> KHONG cau nao re di. Kiem lai ban sua gia da thuc su chay tren may 24 chua:")
        print("      dong log moi trong backend/logs/cost_log.jsonl phai co 'cache_write_5m_tokens'")
        print("      khac null. Neu van null la ban sua CHUA duoc nap.")
    else:
        print("  >>> Co %d cau re di -> ban sua gia cache theo TTL da co tac dung." % len(re_di))
    rows = _doc_token_cache()
    if rows:
        print()
        print("=" * 78)
        print("CHOT BANG SO LIEU: TOKEN CACHE TRONG LOG (khong suy luan tu chi phi)")
        print("=" * 78)
        ghi = sum(int(r.get("cache_write_tokens") or 0) for r in rows)
        doc = sum(int(r.get("cache_read_tokens") or 0) for r in rows)
        print("  %d dong log trong 2 gio gan nhat: GHI cache %s token | DOC cache %s token"
              % (len(rows), format(ghi, ","), format(doc, ",")))
        if doc:
            print("  Ty le ghi/doc = %.2f (binh thuong o che do on dinh la duoi 0,10 vi doc lai nhieu"
                  " hon ghi rat nhieu)" % (ghi / doc))
        co_tach_ttl = [r for r in rows if r.get("cache_write_5m_tokens") is not None]
        print("  So dong da tach don gia cache theo TTL: %d/%d" % (len(co_tach_ttl), len(rows)))
        if not co_tach_ttl:
            print("    >>> KHONG dong nao co truong nay -> ban sua gia CHUA duoc nap tren may nay.")
            print("        Chay: git checkout origin/master -- backend/pricing.py backend/cost_logger.py")
            print("        roi Restart-Service DNH_Chatbot_Backend.")
        else:
            print("    -> ban sua gia cache theo TTL DA chay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
