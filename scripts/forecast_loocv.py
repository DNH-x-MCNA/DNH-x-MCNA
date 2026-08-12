# -*- coding: utf-8 -*-
"""
LOOCV (Leave-One-Out Cross-Validation) cho chuoi doanh thu thang - va SO SANH voi walk-forward.

CHAY:
    cd C:\\dnh_chatbot
    git fetch origin
    git checkout origin/feat/forecast-scripts -- scripts/forecast_loocv.py
    cd backend
    python ..\\scripts\\forecast_loocv.py

CHI DOC warehouse.db. Chi dung thu vien chuan Python.

=== DIEU PHAI BIET TRUOC KHI DOC KET QUA ===

LOOCV nghia la: bo RA 1 thang, hoc tu TAT CA cac thang con lai, roi du bao thang da bo. Voi du lieu
thong thuong (anh, khach hang, giao dich doc lap) day la cach danh gia rat tot vi tan dung toi da du
lieu. Voi CHUOI THOI GIAN thi co mot cho ket:

  "Tat ca cac thang con lai" bao gom ca cac thang SAU thang can du bao.
  Vi du bo thang 06/2024 ra: mo hinh duoc nhin thang 06/2025 va 06/2026 roi di du bao 06/2024.
  Trong thuc te van hanh, thang 06/2024 phai du bao KHI CHUA CO hai thang kia.

=> Con so LOOCV se DEP HON THUC TE mot cach co he thong (goi la ro ri du lieu / data leakage).

TRUONG HOP DAC BIET - va dung la truong hop dang hoi: THANG CUOI CUNG cua chuoi (07/2026).
Bo thang cuoi ra thi "tat ca cac thang con lai" DEU nam o qua khu -> khong co gi de nhin trom.
Voi rieng thang cuoi, LOOCV va walk-forward LA MOT.

Script nay in ca hai de tu kiem chung dieu do, va do luon muc "dep hon" cua LOOCV tren toan chuoi.
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
MIN_TRAIN_MONTHS = 24
BIAS_LOOKBACK = 6
BIAS_CORRECTION = {"OTC": True, "ETC": False}   # ket luan tu forecast_model_v1.py


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


def seasonal_index_from(series, month_list):
    """Chi so mua vu tinh tu DUNG danh sach thang duoc phep dung."""
    ratios = defaultdict(list)
    ml = sorted(month_list)
    for i in range(6, len(ml) - 6):
        window = [series[ml[j]] for j in range(i - 6, i + 6)]
        ma = sum(window) / len(window)
        if ma > 0:
            ratios[int(ml[i][5:7])].append(series[ml[i]] / ma)
    idx = {m: median(v) for m, v in ratios.items() if v}
    if idx:
        k = sum(idx.values()) / len(idx)
        idx = {m: v / k for m, v in idx.items()}
    return idx


def predict(series, allowed, target, use_bias):
    """Du bao `target` chi bang cac thang trong `allowed` (mot tap hop).
    Tra ve {ten_mo_hinh: du_bao}. `allowed` la cho khac biet duy nhat giua LOOCV va walk-forward."""
    out = {}
    A = set(allowed)

    # M1: trung binh cung ky 3 nam - CHI dung 3 thang cu the, khong dung phan con lai cua tap train
    ps = [month_add(target, -12), month_add(target, -24), month_add(target, -36)]
    if all(p in A for p in ps):
        base = sum(series[p] for p in ps) / 3
        out["M1. trung binh cung ky 3 nam"] = base

        # M2: M1 + hieu chinh do lech (do tren cac thang TRUOC target va nam trong `allowed`)
        if use_bias:
            errs = []
            for k in range(1, BIAS_LOOKBACK + 1):
                m = month_add(target, -k)
                if m not in A:
                    continue
                qs = [month_add(m, -12), month_add(m, -24), month_add(m, -36)]
                if all(q in A for q in qs) and series[m] > 0:
                    b = sum(series[q] for q in qs) / 3
                    errs.append((b - series[m]) / series[m])
            if errs:
                bias = sum(errs) / len(errs)
                if bias > -0.9:
                    out["M2. M1 + hieu chinh do lech"] = base / (1 + bias)

    # M3: chi so mua vu x muc nen 3 thang truoc
    #     -> DAY la mo hinh nhay cam voi LOOCV, vi chi so mua vu tinh tu CA TAP allowed.
    idx = seasonal_index_from(series, A)
    tm = int(target[5:7])
    prev3 = [month_add(target, -k) for k in (1, 2, 3)]
    if idx and tm in idx and all(p in A for p in prev3):
        des = [series[p] / idx.get(int(p[5:7]), 1.0) for p in prev3]
        out["M3. mua vu x muc nen 3 thang"] = (sum(des) / 3) * idx[tm]
    return out


def main():
    if not os.path.exists(DB_PATH):
        print(f"KHONG tim thay {DB_PATH}")
        return 1
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    for channel, table in CHANNELS.items():
        series, months = load_series(conn, channel, table)
        if len(months) < MIN_TRAIN_MONTHS + 3:
            print(f"\nKENH {channel}: chi co {len(months)} thang - bo qua.")
            continue
        use_bias = BIAS_CORRECTION.get(channel, False)
        target = months[-1]          # thang cuoi cung = 2026-07
        actual = series[target]

        print(f"\n{'=' * 78}")
        print(f"KENH {channel} - LOOCV cho thang {target}"
              f"   (thuc te: {actual/TY:.2f} ty dong)")
        print(f"{'=' * 78}")

        loo = predict(series, [m for m in months if m != target], target, use_bias)
        wf = predict(series, [m for m in months if m < target], target, use_bias)

        print(f"\n  {'Mo hinh':<32}{'LOOCV':>12}{'Walk-fwd':>12}{'Lech LOOCV':>13}{'Giong nhau?':>13}")
        for name in sorted(set(loo) | set(wf)):
            a = loo.get(name)
            b = wf.get(name)
            atxt = f"{a/TY:.2f}" if a else "-"
            btxt = f"{b/TY:.2f}" if b else "-"
            errtxt = f"{(a/actual-1)*100:+.1f}%" if a and actual > 0 else "-"
            same = "GIONG" if (a and b and abs(a - b) < 1) else ("khac" if (a and b) else "-")
            print(f"  {name:<32}{atxt:>12}{btxt:>12}{errtxt:>13}{same:>13}")

        print(f"\n  => Voi thang CUOI CHUOI, LOOCV va walk-forward cho ket qua GIONG NHAU o cac mo hinh")
        print(f"     chi dung du lieu qua khu (M1/M2). Khac biet neu co la o M3 - mo hinh tinh chi so")
        print(f"     mua vu tu TOAN BO tap train, nen ban LOOCV duoc nhin ca thang sau {target}.")

        # ---- Do muc "dep hon" cua LOOCV tren TOAN chuoi ----
        print(f"\n  {'-' * 74}")
        print("  LOOCV tren TOAN CHUOI vs WALK-FORWARD (day moi la cho LOOCV gay hieu nham)")
        errs_loo, errs_wf = defaultdict(list), defaultdict(list)
        for i in range(MIN_TRAIN_MONTHS, len(months)):
            m = months[i]
            a = series[m]
            if a <= 0:
                continue
            for name, p in predict(series, [x for x in months if x != m], m, use_bias).items():
                errs_loo[name].append(abs(p - a) / a * 100)
            for name, p in predict(series, [x for x in months if x < m], m, use_bias).items():
                errs_wf[name].append(abs(p - a) / a * 100)

        print(f"\n  {'Mo hinh':<32}{'LOOCV':>10}{'Walk-fwd':>12}{'Chenh':>10}")
        for name in sorted(set(errs_loo) | set(errs_wf)):
            el, ew = errs_loo.get(name, []), errs_wf.get(name, [])
            if not el or not ew:
                continue
            ml, mw = sum(el) / len(el), sum(ew) / len(ew)
            print(f"  {name:<32}{ml:>9.1f}%{mw:>11.1f}%{ml-mw:>9.1f}%")
        print("\n  Cot 'Chenh' am nghia la LOOCV cho ket qua DEP HON thuc te - do la ro ri du lieu,")
        print("  khong phai mo hinh tot hon. Con so dung de bao cao va de quyet dinh la cot Walk-fwd.")

    conn.close()
    print(f"\n{'=' * 78}")
    print("KET LUAN VE VIEC DUNG LOOCV O DAY:")
    print(" - Rieng thang CUOI CHUOI (07/2026): LOOCV = walk-forward, dung duoc, khong ro ri.")
    print(" - Cac thang GIUA chuoi: LOOCV cho mo hinh nhin thang sau -> so lieu dep hon thuc te.")
    print(" - Bao cao ra ngoai nen dung con so walk-forward, vi do dung cach he thong se chay that:")
    print("   moi thang chi biet nhung gi da xay ra truoc no.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
