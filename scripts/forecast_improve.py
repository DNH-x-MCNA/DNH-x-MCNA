# -*- coding: utf-8 -*-
"""
Thu CAI TIEN mo hinh nen "trung binh doanh thu cung thang cua 3 nam gan nhat".

CHAY:
    cd C:\\dnh_chatbot
    git fetch origin
    git checkout origin/feat/forecast-scripts -- scripts/forecast_improve.py
    cd backend
    python ..\\scripts\\forecast_improve.py

CHI DOC warehouse.db. Chi dung thu vien chuan Python.

=== VI SAO THU NHUNG CAI NAY ===
Mo hinh dang tot nhat rat don gian: lay doanh thu cung thang cua 3 nam gan nhat roi TRUNG BINH.
No danh bai 13 mo hinh phuc tap hon. Nhung van con 2 diem yeu ro rang, do duoc tu ket qua that:

  1. OTC dang GIAM 13-14% so cung ky -> mo hinh neo vao qua khu nen doan CAO hon thuc te mot cach
     he thong (+8%). Can mot cach "keo" du bao theo da giam.
  2. ETC co thang DI THUONG cuc doan (02/2024 = 8,63 ty trong khi cac thang 2 khac 23-28 ty;
     01/2026 = 51,45 ty gap 2,3 lan moi thang 1 truoc do). TRUNG BINH bi mot nam di thuong keo lech
     rat manh; TRUNG VI thi khong.

Nen thu theo 3 nhom, tach bach de biet cai nao thuc su co tac dung:

  NHOM 1 - doi CACH GOP 3 nam   : trung binh (goc) / trung vi / co trong so / 2 nam / 4 nam
  NHOM 2 - nhan HE SO TANG-GIAM : da 3, 6, 12 thang; co va khong GIAM CHAN (damping)
  NHOM 3 - KET HOP cach gop tot nhat voi he so tot nhat

DA BIET TRUOC (do o buoc truoc, ghi lai de khong lam lai):
  - Nhan da tang truong 3 thang  : TE HON (OTC 19,3% / ETC 30,3% so voi nen 12,9% / 17,1%)
  - Nhan da tang truong 12 thang : TE HON (OTC 17,2% / ETC 29,7%)
  - Hieu chinh do lech 6 thang   : TOT HON cho OTC (11,7%) nhung TE HON cho ETC (25,0%)
  => Da 6 thang CHUA thu. Trung vi CHUA thu. Trong so theo nam CHUA thu. Giam chan CHUA thu.

Danh gia: walk-forward (moi thang chi dung du lieu truoc no), tren cung khoang thoi gian voi
forecast_loocv.py de so sanh duoc truc tiep.
"""
import os
import sys
import sqlite3
import datetime as dt
from collections import defaultdict
from statistics import median

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BACKEND_DIR = os.environ.get("DNH_BACKEND_DIR", r"C:\dnh_chatbot\backend")
DB_PATH = os.path.join(BACKEND_DIR, "warehouse.db")
CHANNELS = {"OTC": "vhoadon_otc", "ETC": "vhoadon_etc"}
TY = 1_000_000_000
START_MONTH = os.environ.get("FORECAST_START", "2024-01")
BASE_NAME = "G0. trung binh 3 nam (mo hinh dang dung)"


def month_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def load_series(conn, channel, table):
    det = {r[0]: float(r[1] or 0) for r in conn.execute(
        f"SELECT substr(doc_date,1,7), SUM(amount9) FROM {table} "
        f"WHERE doc_date IS NOT NULL GROUP BY 1").fetchall()}
    try:
        comp = {r[0]: float(r[1] or 0) for r in conn.execute(
            "SELECT year_month, SUM(revenue) FROM monthly_customer_summary "
            "WHERE channel=? GROUP BY year_month", (channel,)).fetchall()}
    except sqlite3.OperationalError:
        comp = {}
    s = dict(comp)
    s.update(det)
    today = dt.date.today()
    cur = f"{today.year:04d}-{today.month:02d}"
    months = sorted(k for k in s if s[k] > 0)
    if months:
        months = [m for m in months if m != cur and m != months[0]]
    return {m: s[m] for m in months}, months


def prior_same_months(series, hist, target, k):
    """Gia tri cung thang cua k nam TRUOC target (chi lay trong `hist`)."""
    out = []
    for i in range(1, 7):
        if len(out) >= k:
            break
        m = month_add(target, -12 * i)
        if m in hist and series.get(m, 0) > 0:
            out.append(series[m])
    return out


def growth_ratio(series, hist, target, n):
    """Da tang/giam: tong n thang gan nhat / tong dung n thang do cua nam truoc.
    None neu thieu du lieu -> khong doan bua."""
    cur, prv = [], []
    for i in range(1, n + 1):
        a, b = month_add(target, -i), month_add(target, -i - 12)
        if a in hist and b in hist and series.get(b, 0) > 0:
            cur.append(series[a])
            prv.append(series[b])
    if len(cur) == n and sum(prv) > 0:
        return sum(cur) / sum(prv)
    return None


def base_mean3(series, hist, target):
    v = prior_same_months(series, hist, target, 3)
    return sum(v) / len(v) if v else None


def bias_correct(series, hist, target, base_fn, n=6):
    """Do do lech cua chinh base_fn trong n thang gan nhat roi chia lai."""
    errs = []
    for i in range(1, n + 1):
        m = month_add(target, -i)
        if m not in hist or series.get(m, 0) <= 0:
            continue
        h2 = {x for x in hist if x < m}
        b = base_fn(series, h2, m)
        if b:
            errs.append((b - series[m]) / series[m])
    if not errs:
        return None
    bias = sum(errs) / len(errs)
    return bias if bias > -0.9 else None


def variants(series, hist, target):
    """Tra ve {ten: du_bao}. Tat ca chi dung `hist` (cac thang TRUOC target)."""
    out = {}
    v3 = prior_same_months(series, hist, target, 3)
    if not v3:
        return out
    base = sum(v3) / len(v3)
    out[BASE_NAME] = base

    # ---------- NHOM 1: doi cach gop cac nam ----------
    if len(v3) == 3:
        out["G1. TRUNG VI 3 nam (chong nam di thuong)"] = median(v3)
        # trong so uu tien nam gan nhat: 0,5 / 0,3 / 0,2
        out["G2. trung binh CO TRONG SO (0,5/0,3/0,2)"] = 0.5 * v3[0] + 0.3 * v3[1] + 0.2 * v3[2]
    v2 = prior_same_months(series, hist, target, 2)
    if len(v2) == 2:
        out["G3. trung binh 2 nam gan nhat"] = sum(v2) / 2

    # ---------- NHOM 2: nhan he so tang/giam ----------
    for n in (3, 6, 12):
        g = growth_ratio(series, hist, target, n)
        if g:
            out[f"H{n}. x da tang-giam {n} thang"] = base * g
            # GIAM CHAN 50%: chi an theo mot nua da, tranh phan ung thai qua voi bien dong ngan han
            out[f"H{n}d. x da {n} thang, GIAM CHAN 50%"] = base * (1 + 0.5 * (g - 1))

    # ---------- NHOM 3: ket hop ----------
    bias = bias_correct(series, hist, target, base_mean3, 6)
    if bias is not None:
        out["K1. + hieu chinh do lech 6 thang"] = base / (1 + bias)

    if len(v3) == 3:
        med = median(v3)
        g6 = growth_ratio(series, hist, target, 6)
        if g6:
            out["K2. TRUNG VI x da 6 thang"] = med * g6
            out["K3. TRUNG VI x da 6 thang, GIAM CHAN 50%"] = med * (1 + 0.5 * (g6 - 1))
        bmed = bias_correct(series, hist, target,
                            lambda s, h, t: (median(prior_same_months(s, h, t, 3))
                                             if len(prior_same_months(s, h, t, 3)) == 3 else None), 6)
        if bmed is not None:
            out["K4. TRUNG VI + hieu chinh do lech"] = med / (1 + bmed)

        w = 0.5 * v3[0] + 0.3 * v3[1] + 0.2 * v3[2]
        if g6:
            out["K5. CO TRONG SO x da 6 thang, GIAM CHAN"] = w * (1 + 0.5 * (g6 - 1))
    return out


def main():
    if not os.path.exists(DB_PATH):
        print(f"KHONG tim thay {DB_PATH}")
        return 1
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    for channel, table in CHANNELS.items():
        series, months = load_series(conn, channel, table)
        rng = [m for m in months if m >= START_MONTH]
        if len(months) < 30 or not rng:
            print(f"\nKENH {channel}: khong du du lieu.")
            continue

        print(f"\n{'=' * 80}")
        print(f"KENH {channel} - THU CAI TIEN MO HINH NEN   ({len(rng)} thang tu {START_MONTH})")
        print(f"{'=' * 80}")

        errs = defaultdict(list)
        signed = defaultdict(list)
        for m in rng:
            a = series[m]
            if a <= 0:
                continue
            hist = {x for x in months if x < m}
            for name, p in variants(series, hist, m).items():
                errs[name].append(abs(p - a) / a * 100)
                signed[name].append((p - a) / a * 100)

        if BASE_NAME not in errs:
            print("  Khong tinh duoc mo hinh nen.")
            continue
        base_mape = sum(errs[BASE_NAME]) / len(errs[BASE_NAME])

        print(f"\n  {'Mo hinh':<44}{'Thang':>7}{'MAPE':>8}{'vs nen':>9}{'Lech TB':>10}")
        for name, e in sorted(errs.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
            mape = sum(e) / len(e)
            sg = sum(signed[name]) / len(signed[name])
            if name == BASE_NAME:
                delta = "  (nen)"
            else:
                d = mape - base_mape
                delta = f"{d:+.1f}" + ("  TOT" if d < -0.3 else ("  te" if d > 0.3 else "  ="))
            print(f"  {name:<44}{len(e):>7}{mape:>7.1f}%{delta:>9}{sg:>+9.1f}%")

        # --- SO SANH CONG BANG: chi tren cac thang MOI bien the trong nhom deu co du bao ---
        # Bang dau khong cong bang: bien the doi hoi du 3 nam chi chay duoc o cac thang gan day,
        # con mo hinh nen chay duoc gan het chuoi -> so MAPE cua 2 co mau khac nhau la vo nghia.
        per_month = defaultdict(dict)
        for m in rng:
            a = series[m]
            if a <= 0:
                continue
            hist = {x for x in months if x < m}
            for name, p in variants(series, hist, m).items():
                per_month[m][name] = abs(p - a) / a * 100
        n_rng = len([m for m in rng if series[m] > 0])

        # Chia 2 tang: tang RONG giu lai cac mo hinh chay duoc gan het chuoi (>=70% so thang)
        # -> so sanh tren nhieu thang, do tin cay cao hon. Tang DAY DU gom moi bien the nhung
        # phai thu hep ve so thang giao nhau.
        wide_names = {n for n in errs if len(errs[n]) >= 0.7 * n_rng}
        tiers = [("RONG  (cac mo hinh chay duoc gan het chuoi)", wide_names)]
        if set(errs) != wide_names:
            tiers.append(("DAY DU (gom ca bien the doi hoi du 3 nam)", set(errs)))

        verdicts = []
        for tier_label, names in tiers:
            if BASE_NAME not in names or len(names) < 2:
                continue
            common = sorted(m for m, d in per_month.items() if names <= set(d))
            if len(common) < 6:
                continue
            fair = {n: sum(per_month[m][n] for m in common) / len(common) for n in names}
            fb = fair[BASE_NAME]
            print(f"\n  {'-' * 76}")
            print(f"  SO SANH CONG BANG - TANG {tier_label}")
            print(f"  Tinh tren {len(common)} thang ({common[0]} -> {common[-1]}) ma MOI mo hinh "
                  f"trong nhom deu tinh duoc.")
            print(f"\n  {'Mo hinh':<44}{'MAPE':>8}{'vs nen':>10}")
            for n, v in sorted(fair.items(), key=lambda kv: kv[1]):
                tag = "  (nen)" if n == BASE_NAME else (
                    f"{v-fb:+.1f}" + ("  TOT" if v < fb - 0.3 else ("  te" if v > fb + 0.3 else "  =")))
                print(f"  {n:<44}{v:>7.1f}%{tag:>10}")
            bn2 = min(fair, key=fair.get)
            if fair[bn2] < fb - 0.3:
                print(f"  -> '{bn2}' tot hon nen {fb - fair[bn2]:.1f} diem tren {len(common)} thang")
            else:
                print(f"  -> KHONG bien the nao vuot ro mo hinh nen tren {len(common)} thang. Giu nguyen.")

            # --- DOI DAU TUNG THANG: chenh lech trung binh de bi MOT thang keo lech.
            # Neu ung vien chi thang o vai thang thi do la MAY, khong phai mo hinh tot hon.
            robust = None
            if bn2 != BASE_NAME:
                diffs = [(m, per_month[m][bn2] - per_month[m][BASE_NAME]) for m in common]
                wins = [d for _, d in diffs if d < 0]
                med = median([d for _, d in diffs])
                top_m, top_d = min(diffs, key=lambda x: x[1])
                total_gain = (fb - fair[bn2]) * len(common)
                share = (-top_d) / total_gain * 100 if total_gain > 0 else 0
                # Bo han thang dong gop nhieu nhat roi tinh lai: loi the con lai bao nhieu?
                # Day la phep do that su, chac hon nguong ty trong (mot thang chiem 49% van la qua nhieu).
                gain_ex_top = (total_gain - (-top_d)) / (len(common) - 1) if len(common) > 1 else 0
                print(f"\n  Doi dau tung thang: '{bn2}' vs mo hinh nen")
                print(f"    So thang doan sat hon: {len(wins)}/{len(common)}")
                print(f"    Chenh lech TRUNG VI: {med:+.1f} diem  (trung binh {fair[bn2] - fb:+.1f})")
                print(f"    Thang gop nhieu nhat: {top_m} ({top_d:+.1f} diem, "
                      f"chiem {share:.0f}% toan bo loi the)")
                print(f"    Bo {top_m} ra, loi the con: {gain_ex_top:.1f} diem/thang "
                      f"(dau la {fb - fair[bn2]:.1f})")
                robust = (len(wins) > len(common) * 0.6 and med < -0.3 and gain_ex_top > 0.3)
                if robust:
                    print("    => Loi the RAI DEU qua nhieu thang - dang tin.")
                else:
                    reasons = []
                    if len(wins) <= len(common) * 0.6:
                        reasons.append(f"chi thang {len(wins)}/{len(common)} thang")
                    if med >= -0.3:
                        reasons.append(f"trung vi chi {med:+.1f} diem")
                    if gain_ex_top <= 0.3:
                        reasons.append(f"bo {top_m} ra thi loi the chi con {gain_ex_top:.1f} diem")
                    print(f"    => LOI THE KHONG CHAC ({', '.join(reasons)}) - nhieu kha nang la may.")
            verdicts.append((tier_label, len(common), fb, bn2, fair[bn2], robust, fair))

        # --- CHOT: chi doc tu bang cong bang, KHONG doc tu bang dau (khac co mau) ---
        print(f"\n  === CHOT CHO KENH {channel} ===")
        if not verdicts:
            print("  Chua du du lieu de so sanh cong bang -> giu nguyen mo hinh nen.")
        else:
            # Chi coi la thang khi HOI DU 3 dieu: hon MAPE >0,3 diem, loi the rai deu qua cac
            # thang, VA khong thua mo hinh nen tren khoang dai hon. Dieu thu 3 la quan trong
            # nhat: thang o 12 thang gan day ma thua o 25 thang nghia la chi hop voi giai doan
            # hien tai, khong phai quy luat -> doi mo hinh la doi theo nhieu.
            wide_fair = next((v[6] for v in verdicts if v[0].startswith("RONG")), None)

            def loses_on_wide(name):
                if not wide_fair or name not in wide_fair or BASE_NAME not in wide_fair:
                    return False
                return wide_fair[name] > wide_fair[BASE_NAME] - 0.3

            winners = [v for v in verdicts if v[4] < v[2] - 0.3]
            solid = [v for v in winners if v[5] and not loses_on_wide(v[3])]
            if not winners:
                print(f"  GIU NGUYEN mo hinh nen ({BASE_NAME}).")
                print("  Khong bien the nao vuot duoc tren co mau cong bang.")
            elif not solid:
                lbl, nm, fb, bn2, bv, rb, _ = max(winners, key=lambda v: v[1])
                print(f"  GIU NGUYEN mo hinh nen ({BASE_NAME}).")
                if not rb:
                    print(f"  '{bn2}' co MAPE thap hon {fb - bv:.1f} diem nhung loi the KHONG rai deu")
                    print("  qua cac thang (xem phan 'Doi dau tung thang') -> chua du bang chung de doi.")
                else:
                    print(f"  '{bn2}' thap hon {fb - bv:.1f} diem tren {nm} thang gan day, NHUNG tren")
                    print(f"  khoang dai hon no lai THUA nen ({wide_fair[bn2]:.1f}% so voi "
                          f"{wide_fair[BASE_NAME]:.1f}%).")
                    print("  => chi hop voi giai doan hien tai, khong phai quy luat. Theo doi them,")
                    print("     do lai sau 3-6 thang; chua doi.")
            else:
                # uu tien ket luan tu tang co NHIEU thang nhat (do tin cay cao hon)
                lbl, nm, fb, bn2, bv, _, _ = max(solid, key=lambda v: v[1])
                print(f"  DOI SANG: {bn2}")
                print(f"  Giam {fb - bv:.1f} diem ({(fb - bv) / fb * 100:.0f}%) tren {nm} thang "
                      f"(tang {lbl.split('(')[0].strip()}), loi the rai deu qua cac thang.")
                if nm < 12:
                    print("  CANH BAO: co mau duoi 12 thang -> chua du chac. Nen theo doi them "
                          "vai thang truoc khi doi han.")

    conn.close()
    print(f"\n{'=' * 80}")
    print("CACH DOC:")
    print(" - BANG DAU (co cot 'Thang') tinh tren so thang KHAC NHAU vi bien the doi hoi du 3 nam chi")
    print("   chay duoc o cac thang gan day, con mo hinh nen chay duoc gan het chuoi. So MAPE cua 2")
    print("   co mau khac nhau la VO NGHIA -> chi dung bang dau de xem xu huong, QUYET DINH thi doc")
    print("   BANG SO SANH CONG BANG (moi mo hinh trong nhom cung tinh tren dung nhung thang do).")
    print(" - Tang RONG dang tin hon tang DAY DU vi nhieu thang hon; tang DAY DU chi de tham khao.")
    print(" - Cot 'vs nen': am la TOT HON mo hinh dang dung. Chi coi la that su tot hon khi giam")
    print("   >0,3 diem - duoi muc do la nhieu, khong dang doi mo hinh.")
    print(" - Cot 'Lech TB' (sai so co dau): gan 0 nghia la khong doan lech mot chieu. Mo hinh co")
    print("   MAPE tot nhung lech mot chieu manh van dang ngo - no dang bu tru may man.")
    print(" - Neu 2 kenh chon 2 mo hinh khac nhau thi khong sao: OTC dang GIAM deu (hop voi he so")
    print("   tang-giam / hieu chinh lech), con ETC bien dong cuc doan (hop voi TRUNG VI).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
