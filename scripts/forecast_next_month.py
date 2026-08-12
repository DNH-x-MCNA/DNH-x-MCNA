# -*- coding: utf-8 -*-
"""
DU BAO DOANH THU THANG TOI - ban dung duoc, kem KHOANG TIN CAY.

CHAY:
    cd C:\\dnh_chatbot
    git fetch origin
    git checkout origin/feat/forecast-scripts -- scripts/forecast_next_month.py
    cd backend
    python ..\\scripts\\forecast_next_month.py

CHI DOC warehouse.db. Chi dung thu vien chuan Python.

=== MO HINH DUNG O DAY VA VI SAO ===
Chon bang thuc nghiem tren du lieu that (49 thang, 2022-07 -> 2026-07), chia 80/20 theo thoi gian,
danh gia walk-forward. Da thu 13 mo hinh thuoc 5 nhom - xem forecast_model_v1.py de xem bang day du.

  OTC -> "trung binh cung ky 3 nam" + HIEU CHINH DO LECH 6 thang     MAPE 11,7%
  ETC -> "trung binh cung ky 3 nam" (KHONG hieu chinh)               MAPE 17,1%

Hai kenh dung hai mo hinh KHAC NHAU, co can cu: hieu chinh do lech giup OTC (12,9% -> 11,7%) vi do
lech la xu huong giam DEU (doanh thu OTC dang giam 13-14% so cung ky, mo hinh neo qua khu nen luon
hut theo); nhung LAM HONG ETC (17,1% -> 25,0%) vi do lech ETC khong phai xu huong ma do dung MOT
thang bat thuong (01/2026 cao gap 2,3 lan moi thang 1 truoc do).

Nhung thu DA THU VA THUA, ghi lai de khong ai mat cong lam lai:
  - Ngoai suy xu huong tuyen tinh            : 29-39% (te nhat)
  - Nhan them da tang truong 3 thang         : lam TE DI ca 2 kenh (da ngan han la nhieu)
  - Ket hop 2 luong (5 kieu, ke ca hoc trong so tu qua khu): thua mo hinh don o ca 2 kenh.
    Ly do: sai so 2 luong tuong quan r = +0,83 (OTC) / +0,71 (ETC) - cung sai mot kieu nen tron vao
    van ra cai sai do, lai them nhieu tu viec uoc luong trong so.

=== VI SAO PHAI CO KHOANG TIN CAY, KHONG DUA MOT CON SO TRAN ===
Sai so that la +-12% (OTC) va +-17% (ETC). Dua mot con so duy nhat cho lanh dao la ngam khang dinh
do chinh xac khong co that. Khoang tin cay o day tinh TU SAI SO THUC TE cua chinh mo hinh tren tap
test (phan vi cua |sai so|), khong phai cong thuc ly thuyet.
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
BIAS_LOOKBACK = 6      # so thang do do lech (chi ap dung cho kenh nao co loi - xem duoi)
N_EVAL = 10            # so thang gan nhat dung de do sai so thuc te -> dung lam khoang tin cay

# Kenh nao duoc BAT hieu chinh do lech. Ket luan tu thuc nghiem 12/08/2026, KHONG phai chon bua:
#   OTC: 12,9% -> 11,7% (co ich)   |   ETC: 17,1% -> 25,0% (lam hong)
# Neu sau nay dac diem du lieu doi, chay lai forecast_model_v1.py de kiem tra lai truoc khi sua day.
BIAS_CORRECTION = {"OTC": True, "ETC": False}


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
    s.update(det)   # thang co ca 2 nguon -> uu tien ban chi tiet
    today = dt.date.today()
    cur = f"{today.year:04d}-{today.month:02d}"
    months = sorted(k for k in s if s[k] > 0)
    if months:
        # Loai thang hien tai (chua xong) va thang dau cua so du lieu (co the bi cat)
        months = [m for m in months if m != cur and m != months[0]]
    return {m: s[m] for m in months}, months


def base_forecast(series, target, hist_set):
    """Trung binh cung ky 3 nam. None neu thieu du 3 nam lich su."""
    ps = [month_add(target, -12), month_add(target, -24), month_add(target, -36)]
    if all(p in hist_set for p in ps):
        return sum(series[p] for p in ps) / 3
    return None


def forecast_at(series, months, t_idx, use_bias):
    """Du bao thang months[t_idx] (hoac thang KE TIEP neu t_idx == len(months)),
    CHI dung du lieu cac thang truoc do."""
    hist = months[:t_idx]
    hs = set(hist)
    target = months[t_idx] if t_idx < len(months) else month_add(months[-1], 1)
    base = base_forecast(series, target, hs)
    if base is None:
        return None, None, target

    if not use_bias:
        return base, 0.0, target

    errs = []
    for k in range(max(MIN_TRAIN_MONTHS, t_idx - BIAS_LOOKBACK), t_idx):
        b = base_forecast(series, months[k], set(months[:k]))
        a = series[months[k]]
        if b and a > 0:
            errs.append((b - a) / a)
    if not errs:
        return base, 0.0, target
    bias = sum(errs) / len(errs)
    if bias <= -0.9:
        return base, 0.0, target
    return base / (1 + bias), bias, target


def recent_accuracy(series, months, use_bias, n=N_EVAL):
    """Sai so THUC TE cua dung mo hinh nay tren n thang gan nhat (walk-forward)."""
    out = []
    for t in range(max(MIN_TRAIN_MONTHS, len(months) - n), len(months)):
        p, _, _ = forecast_at(series, months, t, use_bias)
        a = series[months[t]]
        if p and a > 0:
            out.append(abs(p - a) / a)
    return out


def main():
    if not os.path.exists(DB_PATH):
        print(f"KHONG tim thay {DB_PATH}. Dat DNH_BACKEND_DIR neu nam cho khac.")
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    print("=" * 78)
    print("DU BAO DOANH THU THANG TOI")
    print("=" * 78)

    total_mid = 0.0
    total_lo = 0.0
    total_hi = 0.0
    ok_channels = []

    for channel, table in CHANNELS.items():
        series, months = load_series(conn, channel, table)
        use_bias = BIAS_CORRECTION.get(channel, False)

        print(f"\n{'-' * 78}")
        print(f"KENH {channel}")
        print(f"{'-' * 78}")

        if len(months) < MIN_TRAIN_MONTHS + 3:
            print(f"  Chi co {len(months)} thang lich su - can it nhat {MIN_TRAIN_MONTHS + 3}. Bo qua.")
            continue

        pred, bias, target = forecast_at(series, months, len(months), use_bias)
        if pred is None:
            print(f"  Thieu du lieu cung ky 3 nam cho thang {target}. Bo qua.")
            continue

        errs = recent_accuracy(series, months, use_bias)
        if not errs:
            print("  Khong do duoc sai so gan day. Bo qua.")
            continue
        mape = sum(errs) / len(errs) * 100
        srt = sorted(errs)
        p80 = srt[int(len(srt) * 0.8)] if len(srt) >= 5 else max(srt)

        lo, hi = pred * (1 - p80), pred * (1 + p80)
        total_mid += pred
        total_lo += lo
        total_hi += hi
        ok_channels.append(channel)

        ps = [month_add(target, -12), month_add(target, -24), month_add(target, -36)]
        print(f"  Mo hinh    : trung binh cung ky 3 nam"
              f"{' + hieu chinh do lech ' + str(BIAS_LOOKBACK) + ' thang' if use_bias else ' (khong hieu chinh)'}")
        print(f"  Can cu     : {', '.join(f'{p}={series[p]/TY:.1f}' for p in ps)}  (ty dong)")
        if use_bias:
            print(f"  Do lech do duoc {BIAS_LOOKBACK} thang gan nhat: {bias*100:+.1f}%"
                  f"  -> chia lai de bu")
        print(f"  Sai so thuc te {len(errs)} thang gan nhat: trung binh {mape:.1f}%, "
              f"8/10 lan trong vong {p80*100:.1f}%")
        print()
        print(f"  >>> DU BAO THANG {target}:  {pred/TY:.1f} ty dong")
        print(f"      Khoang tin cay (8/10 lan roi vao): {lo/TY:.1f} - {hi/TY:.1f} ty")

        last = series[months[-1]]
        same_last_year = month_add(target, -12)
        print(f"      So thang truoc ({months[-1]}: {last/TY:.1f} ty): {(pred/last-1)*100:+.1f}%")
        if same_last_year in series:
            sl = series[same_last_year]
            print(f"      So cung ky nam truoc ({same_last_year}: {sl/TY:.1f} ty): {(pred/sl-1)*100:+.1f}%")

    conn.close()

    if len(ok_channels) == 2:
        print(f"\n{'=' * 78}")
        print(f"TONG 2 KENH - THANG TOI:  {total_mid/TY:.1f} ty dong")
        print(f"  Khoang: {total_lo/TY:.1f} - {total_hi/TY:.1f} ty")
        print("  (Khoang tong la cong don 2 kenh - trong thuc te sai so 2 kenh co the bu tru nhau")
        print("   nen khoang that thuong HEP hon con so nay. Dung nhu can tren than trong.)")

    print(f"\n{'=' * 78}")
    print("CACH DUNG CON SO NAY:")
    print(" - Dung de dinh HUONG va canh bao som, KHONG dung lam cam ket hay chi tieu.")
    print(" - LUON dua kem khoang, dung dua moi con so giua - sai so +-12..17% la co that.")
    print(" - Neu thang dang chay co don thau/hop dong lon bat thuong, mo hinh KHONG biet dieu do:")
    print("   no chi hoc tu lich su. Vi du thang 01/2026 kenh ETC cao gap 2,3 lan moi thang 1 truoc")
    print("   do - khong mo hinh nao du bao duoc, phai lay thong tin tu kinh doanh.")
    print(" - Chay lai forecast_model_v1.py dinh ky (vd moi quy) de kiem mo hinh con phu hop khong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
