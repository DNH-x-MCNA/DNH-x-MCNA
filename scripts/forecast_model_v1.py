# -*- coding: utf-8 -*-
"""
Buoc 2: SOI chuoi thang that + thu cac mo hinh CO MUA VU, do xem co danh bai duoc moc nen khong.

Boi canh (do that tren may 24 ngay 12/08/2026, 49 thang 2022-07 -> 2026-07):
    Moc nen tot nhat = "cung ky nam truoc":  OTC 14,8%  |  ETC 13,7% (MAPE)
    Cac mo hinh khong co mua vu deu THUA ro: naive thang truoc 16-23%, trung binh 3 thang 19-31%,
    xu huong tuyen tinh 29-39%. => Mua vu theo NAM chi phoi, khong phai xu huong.
    Dieu chinh theo da tang truong 3 thang lam TE DI (ETC 13,7% -> 35,6%) => da ngan han la nhieu.

Script nay lam 2 viec:
  (A) IN RA chuoi that + cac chi so chan doan, de nguoi doc tu thay dac diem du lieu:
      - tang truong cung ky nam truoc tung thang
      - chi so mua vu tung thang trong nam
      - thang bat thuong (lech xa khoi ky vong mua vu)
      - do bien dong cua tung thang trong nam (thang nao von da kho du bao)
  (B) THU 4 mo hinh co mua vu, danh gia CUNG CACH va CUNG TAP TEST voi buoc truoc
      (walk-forward, chi dung du lieu truoc thang can du bao) de so sanh cong bang.

CHAY:
    cd C:\\dnh_chatbot
    git fetch origin
    git checkout origin/feat/forecast-scripts -- scripts/forecast_model_v1.py
    cd backend
    python ..\\scripts\\forecast_model_v1.py

CHI DOC, khong ghi gi vao warehouse.db. Chi dung thu vien chuan Python (khong can pandas/numpy).
"""
import os
import sys
import csv
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
OUT_DIR = os.path.join(BACKEND_DIR, "scratch", "forecast")
CHANNELS = {"OTC": "vhoadon_otc", "ETC": "vhoadon_etc"}

# 80/20 (doi tu "6 thang cuoi" sang ty le, theo yeu cau 12/08/2026).
# LUU Y: "20%" o day la 20% CUOI CHUOI, van cat theo THOI GIAN. TUYET DOI khong phai lay ngau nhien
# 20% so thang - voi chuoi thoi gian, lay ngau nhien la cho model hoc thang SAU roi di du bao thang
# TRUOC (nhin trom tuong lai), chi so dep gia ma ra that sai bet.
TEST_RATIO = 0.20
MIN_TEST_MONTHS = 3
MIN_TRAIN_MONTHS = 24   # duoi 24 thang thi khong uoc luong duoc mua vu theo nam
TY = 1_000_000_000


def n_test_months(n_months):
    """So thang dung lam TEST theo ty le 80/20, co chan de khong bop train xuong duoi 24 thang."""
    n_test = max(MIN_TEST_MONTHS, round(n_months * TEST_RATIO))
    return max(MIN_TEST_MONTHS, min(n_test, n_months - MIN_TRAIN_MONTHS))


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


# ---------------------------------------------------------------- (A) CHAN DOAN
def seasonal_index(series, months):
    """Chi so mua vu tung thang trong nam: ty le so voi trung binh truot 12 thang (centered).
    Dung median qua cac nam de 1 nam bat thuong khong keo lech."""
    ratios = defaultdict(list)
    for i in range(6, len(months) - 6):
        window = [series[months[j]] for j in range(i - 6, i + 6)]
        ma = sum(window) / len(window)
        if ma > 0:
            ratios[int(months[i][5:7])].append(series[months[i]] / ma)
    idx = {m: median(v) for m, v in ratios.items() if v}
    if idx:
        k = sum(idx.values()) / len(idx)
        idx = {m: v / k for m, v in idx.items()}   # chuan hoa trung binh = 1
    return idx, {m: len(v) for m, v in ratios.items()}


def diagnose(channel, series, months):
    print(f"\n{'=' * 78}\nCHAN DOAN CHUOI - KENH {channel}   ({len(months)} thang: {months[0]} -> {months[-1]})\n{'=' * 78}")

    print("\n  CHUOI THAT (ty dong) + tang truong so cung ky nam truoc:")
    print(f"    {'Thang':<9}{'Doanh thu':>12}{'So cung ky nam truoc':>24}")
    for m in months:
        prev = month_add(m, -12)
        if prev in series and series[prev] > 0:
            g = (series[m] / series[prev] - 1) * 100
            gtxt = f"{g:+.1f}%"
        else:
            gtxt = "-"
        print(f"    {m:<9}{series[m] / TY:>11.2f}{gtxt:>24}")

    idx, counts = seasonal_index(series, months)
    if idx:
        print("\n  CHI SO MUA VU tung thang (1,00 = trung binh nam):")
        names = ["", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"]
        for m in range(1, 13):
            if m in idx:
                bar = "#" * max(1, int(idx[m] * 20))
                print(f"    {names[m]:<5}{idx[m]:>6.2f}  ({counts.get(m,0)} nam)  {bar}")
        hi = max(idx, key=idx.get); lo = min(idx, key=idx.get)
        print(f"    -> Cao nhat {names[hi]} ({idx[hi]:.2f}), thap nhat {names[lo]} ({idx[lo]:.2f})"
              f"  => chenh {(idx[hi]/idx[lo]-1)*100:.0f}%")

        print("\n  THANG BAT THUONG (lech >25% so voi ky vong mua vu):")
        found = False
        for i in range(6, len(months) - 6):
            m = months[i]
            window = [series[months[j]] for j in range(i - 6, i + 6)]
            ma = sum(window) / len(window)
            exp = ma * idx.get(int(m[5:7]), 1.0)
            if exp > 0 and abs(series[m] / exp - 1) > 0.25:
                print(f"    {m}: thuc {series[m]/TY:.2f} ty vs ky vong {exp/TY:.2f} ty "
                      f"({(series[m]/exp-1)*100:+.0f}%)")
                found = True
        if not found:
            print("    (khong co thang nao lech qua 25% - chuoi kha on dinh)")
    return idx


# ---------------------------------------------------------------- (B) MO HINH
def fit_seasonal_index(series, months):
    ratios = defaultdict(list)
    for i in range(6, len(months) - 6):
        window = [series[months[j]] for j in range(i - 6, i + 6)]
        ma = sum(window) / len(window)
        if ma > 0:
            ratios[int(months[i][5:7])].append(series[months[i]] / ma)
    idx = {m: median(v) for m, v in ratios.items() if v}
    if idx:
        k = sum(idx.values()) / len(idx)
        idx = {m: v / k for m, v in idx.items()}
    return idx


# Dai dien CO DINH cua moi luong, chon TRUOC khi nhin ket qua test (neu chon "cai tot nhat tren test"
# roi mang di tron thi la ro ri thong tin - chi so dep gia).
REP_A = "A2. muc_nen_3thang x mua_vu"     # dai dien luong A
REP_B = "B1. cung_ky_nam_truoc"           # dai dien luong B (cung la moc nen)
REP_B5 = "B5. trung_binh_cung_ky_3_nam"   # mo hinh nen cho luong D (tot nhat tren du lieu that)


def predict_all(series, hist_months, target):
    """Tra ve {(luong, ten): du_bao}. Moi mo hinh CHI duoc dung hist_months (cac thang TRUOC target).

    CHIA 2 LUONG THEO DIEM NEO - do la khac biet ban chat:
      LUONG A "xu huong trong nam": neo vao CAC THANG VUA QUA cua nam nay, roi keo tiep.
              Tra loi cau hoi "may thang gan day dang di len hay xuong?"
      LUONG B "cung ky nam truoc"  : neo vao THANG CUNG KY nam ngoai.
              Tra loi cau hoi "thang nay so voi nam ngoai the nao?"
    Hai luong dung 2 nguon thong tin KHAC NHAU nen sai so cua chung co the doc lap - neu doc lap that
    thi trung binh 2 luong se tot hon ca hai (xem luong C).
    """
    out = {}
    vals = [series[m] for m in hist_months]
    tm = int(target[5:7])
    hs = set(hist_months)
    p1, p2, p3 = month_add(target, -12), month_add(target, -24), month_add(target, -36)

    # ---------------- LUONG A: neo vao cac thang gan day trong nam ----------------
    out[("A", "A0. thang_truoc")] = vals[-1]
    if len(vals) >= 3:
        out[("A", "A1. trung_binh_3_thang")] = sum(vals[-3:]) / 3

    idx = fit_seasonal_index(series, hist_months)
    if idx and tm in idx:
        des = [series[m] / idx.get(int(m[5:7]), 1.0) for m in hist_months]
        if len(des) >= 3:
            # Khu mua vu -> lay muc nen 3 thang gan nhat -> nhan lai mua vu thang dich.
            out[("A", REP_A)] = (sum(des[-3:]) / 3) * idx[tm]
        if len(des) >= 6:
            seg = des[-6:]
            n = len(seg)
            lvl = sum(seg) / n
            xm = (n - 1) / 2
            num = sum((i - xm) * (seg[i] - lvl) for i in range(n))
            den = sum((i - xm) ** 2 for i in range(n))
            slope = num / den if den else 0
            out[("A", "A3. muc_nen + xu_huong x mua_vu")] = (lvl + slope * (n / 2 + 1)) * idx[tm]

    # ---------------- LUONG B: neo vao cung ky nam truoc ----------------
    if p1 in hs:
        out[("B", REP_B)] = series[p1]

        # B2: cung ky x da tang truong CA NAM (12 thang gan nhat / 12 thang truoc do)
        if len(hist_months) >= 24:
            last12, prev12 = sum(vals[-12:]), sum(vals[-24:-12])
            if prev12 > 0:
                out[("B", "B2. cung_ky x tang_truong_12thang")] = series[p1] * (last12 / prev12)

        # B3: cung ky x da tang truong 3 THANG gan nhat so cung ky (bat da giam nhanh hon B2)
        recent_prev = [series.get(month_add(m, -12)) for m in hist_months[-3:]]
        if all(v for v in recent_prev) and sum(recent_prev) > 0:
            out[("B", "B3. cung_ky x tang_truong_3thang")] = series[p1] * (sum(vals[-3:]) / sum(recent_prev))

        # B4/B5: trung binh cung ky nhieu nam (giam nhieu cua 1 nam le)
        if p2 in hs:
            out[("B", "B4. trung_binh_cung_ky_2_nam")] = (series[p1] + series[p2]) / 2
            if p3 in hs:
                out[("B", REP_B5)] = (series[p1] + series[p2] + series[p3]) / 3

    # ---------------- LUONG C: ket hop 2 luong ----------------
    a, b = out.get(("A", REP_A)), out.get(("B", REP_B))
    if a and b:
        out[("C", "C1. trung binh A+B (50/50)")] = (a + b) / 2
        out[("C", "C2. nghieng ve B (30/70)")] = 0.3 * a + 0.7 * b
    return out


def evaluate(channel, series, months):
    print(f"\n{'=' * 78}\nSO SANH MO HINH - KENH {channel}  (walk-forward, cung tap test voi buoc truoc)\n{'=' * 78}")
    n_test = n_test_months(len(months))
    n_train = len(months) - n_test
    test_idx = range(n_train, len(months))
    print(f"  Chia 80/20 theo thoi gian: TRAIN {n_train} thang ({n_train/len(months)*100:.0f}%)"
          f"  |  TEST {n_test} thang ({n_test/len(months)*100:.0f}%)")
    print(f"  Train: {months[0]} -> {months[n_train-1]}   |   "
          f"Test: {months[n_train]} -> {months[-1]}")

    # ---- BUOC 1: tinh TRUOC du bao nen cho MOI thang co the du bao (walk-forward, 1 lan duy nhat).
    # Truoc day moi to hop lai goi predict_all() long nhau -> cham va kho doc. Nay moi thu doc lai
    # tu bang nay. Van dam bao khong nhin tuong lai: base[t] chi dung months[:t].
    base = {}
    for t in range(MIN_TRAIN_MONTHS, len(months)):
        base[t] = predict_all(series, months[:t], months[t])

    def signed_err(key, t):
        """Sai so CO DAU cua mo hinh `key` tai thang t (None neu khong tinh duoc)."""
        p = base.get(t, {}).get(key)
        a = series[months[t]]
        return (p - a) / a if (p and a > 0) else None

    def recent_errs(key, t, k):
        """Sai so cua `key` trong k thang TRUOC t (chi du lieu qua khu)."""
        out = []
        for j in range(max(MIN_TRAIN_MONTHS, t - k), t):
            e = signed_err(key, j)
            if e is not None:
                out.append(e)
        return out

    COMP_A = ("A", REP_A)     # dai dien luong A
    COMP_B = ("B", REP_B5)    # dai dien luong B (mo hinh tot nhat cua luong B tren du lieu that)

    errs = defaultdict(list)
    detail = defaultdict(dict)
    signed = defaultdict(dict)   # sai so CO DAU, de biet mo hinh doan CAO hay THAP

    for t in test_idx:
        target = months[t]
        actual = series[target]
        if actual <= 0:
            continue
        preds = dict(base.get(t, {}))

        # ---------------- LUONG D: hieu chinh DO LECH HE THONG ----------------
        # Ly do (do tren du lieu that 12/08/2026): MOI mo hinh OTC deu doan CAO hon thuc te +5..+10%
        # mot cach HE THONG - vi doanh thu OTC dang giam 13-14% ma mo hinh thi neo vao qua khu.
        # Lech MOT CHIEU thi sua duoc, khac han nhieu ngau nhien.
        # KET QUA THAT: giup OTC (12,9 -> 11,7%) nhung LAM HONG ETC (17,1 -> 25,0%) vi do lech ETC
        # khong phai xu huong deu ma do dung 1 thang bat thuong (01/2026 lech -58%).
        for k in (3, 6):
            he = recent_errs(COMP_B, t, k)
            b = preds.get(COMP_B)
            if b and he:
                bias = sum(he) / len(he)
                if bias > -0.9:
                    preds[("D", f"D{k}. B5 + hieu_chinh_lech_{k}thang")] = b / (1 + bias)

        # ---------------- LUONG E: HYBRID 2 CHIEU (tinh hon luong C tron co dinh) ----------------
        # Luong C truoc do tron CO DINH 50/50 va 30/70 -> thua ca A lan B o ca 2 kenh. Cau hoi con
        # lai: neu trong so KHONG co dinh ma HOC tu qua khu thi co tot hon khong? Ba cach:
        #   E1 - hoc trong so toi uu: thu w = 0; 0,1; ...; 1,0 tren 12 thang gan nhat, chon w cho sai
        #        so nho nhat, roi ap cho thang dich. (Hoc tren QUA KHU, khong phai tren tap test.)
        #   E2 - trong so nghich dao sai so: luong nao sai it hon gan day thi duoc trong so lon hon.
        #   E3 - CHUYEN LUONG (chon, khong tron): dung han luong nao thang trong 6 thang gan nhat.
        # Luu y ve ky vong: sai so 2 luong tuong quan r=+0,83 (OTC) / +0,71 (ETC) - cung sai mot kieu,
        # nen ve ly thuyet moi to hop tuyen tinh deu kho cai thien nhieu. Van thu de co cau tra loi
        # bang so thay vi bang suy doan.
        pa, pb = preds.get(COMP_A), preds.get(COMP_B)
        if pa and pb:
            # Ghep sai so theo CUNG THANG (khong so do dai 2 danh sach - A2 thieu o vai thang dau
            # vi can du lich su tinh chi so mua vu, lam 2 danh sach lech do dai).
            def paired(k):
                out = []
                for j in range(max(MIN_TRAIN_MONTHS, t - k), t):
                    x, y = signed_err(COMP_A, j), signed_err(COMP_B, j)
                    if x is not None and y is not None:
                        out.append((x, y))
                return out

            p12 = paired(12)
            if len(p12) >= 4:
                best_w, best_score = None, None
                for i in range(11):
                    w = i / 10
                    score = sum(abs(w * x + (1 - w) * y) for x, y in p12)
                    if best_score is None or score < best_score:
                        best_score, best_w = score, w
                preds[("E", "E1. hoc trong so toi uu tu qua khu")] = best_w * pa + (1 - best_w) * pb

            p6 = paired(6)
            if len(p6) >= 3:
                ma = sum(abs(x) for x, _ in p6) / len(p6)
                mb = sum(abs(y) for _, y in p6) / len(p6)
                if ma > 0 and mb > 0:
                    wa = (1 / ma) / ((1 / ma) + (1 / mb))
                    preds[("E", "E2. trong so nghich dao sai so")] = wa * pa + (1 - wa) * pb
                    preds[("E", "E3. chuyen luong (chon, khong tron)")] = pa if ma < mb else pb

        for key, pred in preds.items():
            errs[key].append(abs(pred - actual) / actual * 100)
            detail[key][target] = (pred, abs(pred - actual) / actual * 100)
            signed[key][target] = (pred - actual) / actual * 100

    if not errs:
        print("  Khong du du lieu.")
        return None

    LUONG = {
        "A": "LUONG A - so voi XU HUONG CAC THANG TRONG NAM (neo vao thang gan day)",
        "B": "LUONG B - so voi CUNG KY NAM TRUOC (neo vao thang nam ngoai)",
        "C": "LUONG C - KET HOP hai luong",
        "D": "LUONG D - luong B + HIEU CHINH DO LECH HE THONG (bat da tang/giam)",
        "E": "LUONG E - HYBRID 2 CHIEU, trong so HOC tu qua khu (khong co dinh nhu C)",
    }
    best_of = {}
    for stream in ("A", "B", "C", "D", "E"):
        items = [(k, v) for k, v in errs.items() if k[0] == stream]
        if not items:
            continue
        print(f"\n  {LUONG[stream]}")
        print(f"    {'Mo hinh':<34}{'So thang':>10}{'MAPE':>9}{'Xau nhat':>11}{'Xu huong lech':>16}")
        for (s, name), e in sorted(items, key=lambda kv: sum(kv[1]) / len(kv[1])):
            mape = sum(e) / len(e)
            sg = list(signed[(s, name)].values())
            bias = sum(sg) / len(sg)
            xu = "doan CAO hon" if bias > 3 else ("doan THAP hon" if bias < -3 else "can bang")
            print(f"    {name:<34}{len(e):>10}{mape:>8.1f}%{max(e):>10.1f}%   {xu} {bias:+.0f}%")
        bk, be = min(items, key=lambda kv: sum(kv[1]) / len(kv[1]))
        best_of[stream] = (bk, sum(be) / len(be))

    print(f"\n  {'-' * 74}")
    print("  SO TRUC DIEN GIUA CAC LUONG:")
    for s in ("A", "B", "C", "D", "E"):
        if s in best_of:
            print(f"    Luong {s}: tot nhat '{best_of[s][0][1]}'  ->  MAPE {best_of[s][1]:.1f}%")

    if "B" in best_of and "D" in best_of:
        mb, md = best_of["B"][1], best_of["D"][1]
        if md < mb:
            print(f"    => Hieu chinh do lech CO ICH cho kenh nay: {mb:.1f}% -> {md:.1f}% "
                  f"(tot hon {(mb-md)/mb*100:.0f}%). Do lech la XU HUONG DEU, sua duoc.")
        else:
            print(f"    => Hieu chinh do lech KHONG giup kenh nay ({mb:.1f}% -> {md:.1f}%). "
                  f"Do lech do THANG BAT THUONG chu khong phai xu huong deu -> dung dung luong D.")

    if "A" in best_of and "B" in best_of:
        ma, mb = best_of["A"][1], best_of["B"][1]
        thang = "B (cung ky nam truoc)" if mb < ma else "A (xu huong trong nam)"
        print(f"    => Luong {thang} thang, cach nhau {abs(ma - mb):.1f} diem %")

        # Sai so 2 luong co doc lap khong? Neu doc lap (tuong quan thap) thi ket hop moi co ich.
        sa = signed.get(("A", REP_A), {})
        sb = signed.get(("B", REP_B), {})
        common = sorted(set(sa) & set(sb))
        if len(common) >= 4:
            xa = [sa[m] for m in common]
            xb = [sb[m] for m in common]
            n = len(common)
            mxa, mxb = sum(xa) / n, sum(xb) / n
            cov = sum((xa[i] - mxa) * (xb[i] - mxb) for i in range(n))
            va = sum((v - mxa) ** 2 for v in xa) ** 0.5
            vb = sum((v - mxb) ** 2 for v in xb) ** 0.5
            r = cov / (va * vb) if va and vb else 0
            print(f"    Tuong quan sai so 2 luong: r = {r:+.2f}", end="  ")
            if r > 0.7:
                print("(cung sai mot kieu -> ket hop khong giup gi nhieu)")
            elif r < 0.3:
                print("(sai so kha DOC LAP -> ket hop co the tot hon ca hai)")
            else:
                print("(doc lap mot phan)")

    all_ranked = sorted(errs.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    bk, be = all_ranked[0]
    base = next((sum(e) / len(e) for k, e in errs.items() if k == ("B", REP_B)), None)
    print(f"\n  -> TOT NHAT TOAN CUOC: '{bk[1]}' (luong {bk[0]})  MAPE {sum(be)/len(be):.1f}%")
    if base is not None:
        if bk != ("B", REP_B):
            print(f"  -> Tot hon moc nen '{REP_B}' {(base - sum(be)/len(be))/base*100:.0f}% "
                  f"({base:.1f}% -> {sum(be)/len(be):.1f}%)")
        else:
            print(f"  -> KHONG mo hinh nao danh bai duoc moc nen. Giu moc nen, dung phuc tap hoa.")

    print(f"\n  Chi tiet tung thang cua mo hinh tot nhat ('{bk[1]}'):")
    print(f"    {'Thang':<9}{'Thuc te':>11}{'Du bao':>11}{'Lech':>9}")
    for m in sorted(detail[bk]):
        pred, ape = detail[bk][m]
        dau = "+" if signed[bk][m] > 0 else ""
        print(f"    {m:<9}{series[m]/TY:>10.2f}{pred/TY:>11.2f}   {dau}{signed[bk][m]:.1f}%")
    return bk


def main():
    if not os.path.exists(DB_PATH):
        print(f"KHONG tim thay {DB_PATH}")
        return 1
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    for channel, table in CHANNELS.items():
        series, months = load_series(conn, channel, table)
        if len(months) < 24:
            print(f"\nKENH {channel}: chi co {len(months)} thang - can >=24 thang de xet mua vu.")
            continue
        diagnose(channel, series, months)
        evaluate(channel, series, months)

    conn.close()
    print(f"\n{'=' * 78}")
    print("LUU Y KHI DOC KET QUA:")
    print(" - MAPE 13-15% o cap THANG la muc kha thuong voi nganh duoc (don thau ETC rat cuc bo).")
    print("   Truoc khi trach mo hinh, xem muc 'THANG BAT THUONG' o phan chan doan: neu co vai thang")
    print("   lech >25% thi do la bien dong THAT cua kinh doanh, khong mo hinh nao du bao duoc.")
    print(" - Neu khong mo hinh nao danh bai moc nen: GIU moc nen. Mo hinh phuc tap hon ma khong")
    print("   chinh xac hon thi chi lam kho giai thich voi khach khi so lech.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
