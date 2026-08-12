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


def predict_all(series, hist_months, target):
    """Moi mo hinh CHI duoc dung hist_months (cac thang TRUOC target)."""
    out = {}
    vals = [series[m] for m in hist_months]
    tm = int(target[5:7])
    prev_year = month_add(target, -12)

    # 0. Moc nen dang thang: cung ky nam truoc
    if prev_year in series and prev_year in set(hist_months):
        out["[nen] cung_ky_nam_truoc"] = series[prev_year]

    # 1. Cung ky nam truoc x da tang truong 12 THANG (thay vi 3 thang - 3 thang da chung minh la nhieu)
    if prev_year in set(hist_months) and len(hist_months) >= 24:
        last12 = sum(vals[-12:])
        prev12 = sum(vals[-24:-12])
        if prev12 > 0:
            out["cung_ky x tang_truong_nam"] = series[prev_year] * (last12 / prev12)

    # 2. Chi so mua vu x muc nen gan day (Holt-Winters rut gon, nhan tinh)
    idx = fit_seasonal_index(series, hist_months)
    if idx and tm in idx:
        des = [series[m] / idx.get(int(m[5:7]), 1.0) for m in hist_months]
        if len(des) >= 3:
            level = sum(des[-3:]) / 3
            out["mua_vu x muc_nen_3thang"] = level * idx[tm]
        if len(des) >= 6:
            lvl = sum(des[-6:]) / 6
            n = len(des[-6:])
            xm = (n - 1) / 2
            ym = lvl
            num = sum((i - xm) * (des[-6:][i] - ym) for i in range(n))
            den = sum((i - xm) ** 2 for i in range(n))
            slope = num / den if den else 0
            out["mua_vu x muc_nen + xu_huong"] = (lvl + slope * (n / 2 + 1)) * idx[tm]

    # 3. Trung binh cung ky 2 nam gan nhat (giam nhieu cua 1 nam le)
    p1, p2 = month_add(target, -12), month_add(target, -24)
    hs = set(hist_months)
    if p1 in hs and p2 in hs:
        out["trung_binh_cung_ky_2_nam"] = (series[p1] + series[p2]) / 2
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

    errs = defaultdict(list)
    detail = defaultdict(dict)
    for t in test_idx:
        target = months[t]
        actual = series[target]
        for name, pred in predict_all(series, months[:t], target).items():
            if actual > 0:
                ape = abs(pred - actual) / actual * 100
                errs[name].append(ape)
                detail[name][target] = (pred, ape)

    if not errs:
        print("  Khong du du lieu.")
        return None

    print(f"\n  {'Mo hinh':<32}{'So thang':>10}{'MAPE':>9}{'Sai so xau nhat':>18}")
    ranked = sorted(errs.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    for name, e in ranked:
        print(f"  {name:<32}{len(e):>10}{sum(e)/len(e):>8.1f}%{max(e):>17.1f}%")

    best, be = ranked[0]
    base = next((sum(e)/len(e) for n, e in errs.items() if n.startswith("[nen]")), None)
    print(f"\n  -> Tot nhat: '{best}'  MAPE {sum(be)/len(be):.1f}%")
    if base is not None and not best.startswith("[nen]"):
        imp = (base - sum(be)/len(be)) / base * 100
        print(f"  -> Tot hon moc nen {imp:.0f}% (nen {base:.1f}% -> {sum(be)/len(be):.1f}%)")
    elif base is not None:
        print(f"  -> KHONG mo hinh nao danh bai duoc moc nen ({base:.1f}%). Giu moc nen, dung phuc tap hoa.")

    print(f"\n  Chi tiet tung thang cua mo hinh tot nhat ('{best}'):")
    print(f"    {'Thang':<9}{'Thuc te':>11}{'Du bao':>11}{'Lech':>9}")
    for m in sorted(detail[best]):
        pred, ape = detail[best][m]
        print(f"    {m:<9}{series[m]/TY:>10.2f}{pred/TY:>11.2f}{ape:>8.1f}%")
    return best


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
