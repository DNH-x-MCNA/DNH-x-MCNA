# -*- coding: utf-8 -*-
"""
Dung bo du lieu TRAIN/TEST cho bai toan: DU BAO DOANH THU CUOI THANG tu so lieu GIUA THANG.

Bai toan cu the: dung ngay thu d cua thang, da biet doanh thu luy ke tu ngay 1 den ngay d
-> du bao tong doanh thu CA THANG. Day dung la cau hoi lanh dao hay hoi ("thang nay uoc dat bao
nhieu"), va cung la bai toan ma tool get_kpi_forecast_model1 (da go 10/08/2026) dinh giai nhung
lam sai: hardcode ty trong 13,41%/14,07% thay vi hoc tu du lieu, hardcode luon ca ngay 01-06/08.

CHAY TREN MAY 24 (noi co warehouse.db that):
    cd C:\\dnh_chatbot\\backend
    python D:\\DNH\\scripts\\forecast_intramonth_dataset.py
    (hoac copy file nay vao backend/ roi chay: python forecast_intramonth_dataset.py)

CHI DOC (SELECT), khong ghi gi vao warehouse.db. Chay lai bao nhieu lan cung duoc.
Ket qua ghi ra thu muc scratch/forecast/ canh warehouse.db.

=== BA NGUYEN TAC BAT BUOC CUA BAI TOAN CHUOI THOI GIAN (khong duoc pha) ===

1. CHIA TRAIN/TEST THEO THOI GIAN, KHONG NGAU NHIEN.
   Train = cac thang TRUOC, test = cac thang SAU. Chia ngau nhien = cho model nhin trom tuong lai,
   chi so dep gia, ra that sai bet. Script nay ep chia theo thoi gian, khong co tuy chon random.

2. CHI DUNG THANG DA TRON VEN lam mau.
   Thang hien tai (dang chay do) va thang dau/cuoi cua so du lieu co the bi cat -> loai bo, neu
   khong model se hoc rang "thang nao cung hut o cuoi" (sai he thong).

3. KHONG GIA DINH NGAY LAM VIEC - PHAI DO TU DU LIEU.
   Trong repo dang co HAI dinh nghia mau thuan: report_templates.py:790 loai ca T7 lan CN
   (weekday()<5), con alerts.py:2326 chi loai CN (da do thuc te: 10/10 Chu nhat deu 0 doanh thu,
   nhung KHONG noi gi ve T7). Script nay DEM doanh thu theo tung thu trong tuan roi tu ket luan,
   khong chon bua mot ben.
"""
import os
import sys
import csv
import sqlite3
import datetime as dt
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BACKEND_DIR = os.environ.get("DNH_BACKEND_DIR", r"C:\dnh_chatbot\backend")
DB_PATH = os.path.join(BACKEND_DIR, "warehouse.db")
OUT_DIR = os.path.join(BACKEND_DIR, "scratch", "forecast")

CHANNELS = {"OTC": "vhoadon_otc", "ETC": "vhoadon_etc"}

# Cac moc ngay trong thang de du bao (ngay ra quyet dinh thuc te cua lanh dao).
CUTOFF_DAYS = list(range(3, 29))

# So thang CUOI dung lam tap TEST (con lai la TRAIN). 3 thang la muc toi thieu de nhin duoc xu huong
# sai so; neu tong so thang tron ven qua it, script se canh bao ro thay vi im lang chia bua.
TEST_MONTHS = 3
MIN_MONTHS_REQUIRED = 6


def _q(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def load_daily_revenue(conn, table):
    """{ 'YYYY-MM-DD': doanh_thu } - SUM(amount9) theo dung cach toan he thong dang tinh doanh thu
    (nguon vHoaDonTotal/vHoaDonETCTotal, DA gom ca dong dieu chinh/hoan DocCode='HC')."""
    rows = _q(conn, f"SELECT doc_date, SUM(amount9) FROM {table} "
                    f"WHERE doc_date IS NOT NULL GROUP BY doc_date")
    return {r[0]: float(r[1] or 0.0) for r in rows}


def measure_business_days(daily):
    """DO tu du lieu xem thu nao thuc su co kinh doanh, thay vi gia dinh.
    Tra ve (set cac weekday co kinh doanh, bang thong ke de in ra)."""
    by_wd_total = defaultdict(float)
    by_wd_days = defaultdict(int)
    by_wd_zero = defaultdict(int)
    for ds, rev in daily.items():
        try:
            d = dt.date.fromisoformat(ds)
        except ValueError:
            continue
        wd = d.weekday()
        by_wd_total[wd] += rev
        by_wd_days[wd] += 1
        if rev <= 0:
            by_wd_zero[wd] += 1

    stats = []
    business = set()
    for wd in range(7):
        n = by_wd_days.get(wd, 0)
        if n == 0:
            stats.append((wd, 0, 0.0, 0.0, None))
            continue
        avg = by_wd_total[wd] / n
        zero_pct = by_wd_zero[wd] / n * 100
        # Coi la NGAY KINH DOANH neu KHONG phai da so ngay deu bang 0.
        is_biz = zero_pct < 80
        if is_biz:
            business.add(wd)
        stats.append((wd, n, avg, zero_pct, is_biz))
    return business, stats


def complete_months(daily, business_days):
    """Cac thang TRON VEN co the dung lam mau. Loai:
      - thang hien tai (chua xong)
      - thang dau tien cua du lieu (rat co the bi cat boi cua so giu chi tiet 12 thang)
      - thang thieu qua nhieu ngay kinh doanh (nghi du lieu khong day du)
    """
    if not daily:
        return [], {}
    dates = sorted(dt.date.fromisoformat(d) for d in daily if d)
    first, last = dates[0], dates[-1]
    today = dt.date.today()

    months = sorted({(d.year, d.month) for d in dates})
    usable, reasons = [], {}
    for (y, m) in months:
        label = f"{y}-{m:02d}"
        # so ngay kinh doanh theo lich cua thang do
        d = dt.date(y, m, 1)
        cal_biz = 0
        while d.month == m:
            if d.weekday() in business_days:
                cal_biz += 1
            d += dt.timedelta(days=1)
        # so ngay kinh doanh THUC SU co mat trong du lieu
        have_biz = sum(1 for ds in daily
                       if ds.startswith(label)
                       and dt.date.fromisoformat(ds).weekday() in business_days)

        if (y, m) == (today.year, today.month):
            reasons[label] = "LOAI - thang hien tai, chua ket thuc"
        elif (y, m) == (first.year, first.month):
            reasons[label] = "LOAI - thang dau cua so du lieu, co the bi cat"
        elif (y, m) == (last.year, last.month) and last.day < 28:
            reasons[label] = "LOAI - thang cuoi khong tron ven"
        elif cal_biz and have_biz / cal_biz < 0.8:
            reasons[label] = f"LOAI - chi co {have_biz}/{cal_biz} ngay kinh doanh (nghi thieu du lieu)"
        else:
            usable.append(label)
            reasons[label] = f"DUNG DUOC ({have_biz}/{cal_biz} ngay kinh doanh)"
    return usable, reasons


def build_rows(daily, months, channel, business_days):
    """Moi dong = 1 (thang, kenh, moc ngay d): dac trung tu ngay 1..d, nhan = tong CA thang."""
    out = []
    for label in months:
        y, m = int(label[:4]), int(label[5:7])
        month_days = {ds: rev for ds, rev in daily.items() if ds.startswith(label)}
        full_total = sum(month_days.values())
        if full_total <= 0:
            continue

        # tong so ngay kinh doanh theo lich trong thang
        d = dt.date(y, m, 1)
        biz_total = 0
        while d.month == m:
            if d.weekday() in business_days:
                biz_total += 1
            d += dt.timedelta(days=1)

        for cutoff in CUTOFF_DAYS:
            try:
                cutoff_date = dt.date(y, m, cutoff)
            except ValueError:
                continue  # vd ngay 29-31 cua thang ngan
            cum = sum(rev for ds, rev in month_days.items()
                      if dt.date.fromisoformat(ds) <= cutoff_date)
            biz_elapsed = sum(1 for dd in range(1, cutoff + 1)
                              if dt.date(y, m, dd).weekday() in business_days)
            out.append({
                "year_month": label,
                "channel": channel,
                "cutoff_day": cutoff,
                "cum_revenue": round(cum, 2),
                "days_elapsed": cutoff,
                "bizdays_elapsed": biz_elapsed,
                "bizdays_total": biz_total,
                "bizdays_remaining": biz_total - biz_elapsed,
                "biz_frac_elapsed": round(biz_elapsed / biz_total, 4) if biz_total else 0.0,
                "full_month_revenue": round(full_total, 2),
                "ratio_cum_over_full": round(cum / full_total, 6),
            })
    return out


def baseline_and_eval(rows, train_months, test_months):
    """Baseline THAY THE cach lam cu (hardcode 13,41%/14,07%): HOC ty trong tu chinh du lieu train,
    rieng cho tung (kenh, moc ngay), roi do sai so tren test.
    Du bao: tong_ca_thang_uoc_tinh = luy_ke_den_ngay_d / ty_trong_trung_vi(kenh, d).
    Dung TRUNG VI (median) chu khong phai trung binh - 1 thang bat thuong khong keo lech ca bang."""
    ratios = defaultdict(list)
    for r in rows:
        if r["year_month"] in train_months and r["ratio_cum_over_full"] > 0:
            ratios[(r["channel"], r["cutoff_day"])].append(r["ratio_cum_over_full"])

    table = {}
    for k, vals in ratios.items():
        vals.sort()
        n = len(vals)
        table[k] = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    errs = defaultdict(list)
    for r in rows:
        if r["year_month"] not in test_months:
            continue
        ratio = table.get((r["channel"], r["cutoff_day"]))
        if not ratio or r["full_month_revenue"] <= 0:
            continue
        pred = r["cum_revenue"] / ratio
        ape = abs(pred - r["full_month_revenue"]) / r["full_month_revenue"] * 100
        errs[(r["channel"], r["cutoff_day"])].append(ape)
    return table, errs


def main():
    print("=" * 78)
    print("DUNG BO DU LIEU TRAIN/TEST - DU BAO DOANH THU CUOI THANG TU GIUA THANG")
    print("=" * 78)

    if not os.path.exists(DB_PATH):
        print(f"KHONG tim thay {DB_PATH}")
        print("Dat bien moi truong DNH_BACKEND_DIR neu warehouse.db nam cho khac.")
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    all_rows, all_months_per_channel = [], {}

    for channel, table in CHANNELS.items():
        print(f"\n{'-' * 78}\nKENH {channel}  (bang {table})\n{'-' * 78}")
        daily = load_daily_revenue(conn, table)
        if not daily:
            print("  KHONG co du lieu - bo qua kenh nay.")
            continue

        ds = sorted(daily)
        print(f"  Khoang ngay co du lieu : {ds[0]} -> {ds[-1]}  ({len(daily)} ngay co ban ghi)")

        business, stats = measure_business_days(daily)
        names = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
        print("\n  DO NGAY KINH DOANH TU DU LIEU (khong gia dinh):")
        print(f"    {'Thu':<5}{'So ngay':>9}{'DT trung binh':>18}{'% ngay = 0':>13}   Ket luan")
        for wd, n, avg, zero_pct, is_biz in stats:
            if n == 0:
                continue
            kl = "kinh doanh" if is_biz else "KHONG kinh doanh"
            print(f"    {names[wd]:<5}{n:>9}{avg:>18,.0f}{zero_pct:>12.1f}%   {kl}")

        usable, reasons = complete_months(daily, business)
        print("\n  THANG NAO DUNG DUOC LAM MAU:")
        for label in sorted(reasons):
            print(f"    {label}  {reasons[label]}")

        all_months_per_channel[channel] = usable
        if usable:
            all_rows += build_rows(daily, usable, channel, business)

    conn.close()

    months = sorted({r["year_month"] for r in all_rows})
    print(f"\n{'=' * 78}")
    print(f"TONG SO THANG TRON VEN DUNG DUOC: {len(months)}  -> {months}")

    if len(months) < MIN_MONTHS_REQUIRED:
        print(f"\n  ** CANH BAO: chi co {len(months)} thang, duoi muc toi thieu {MIN_MONTHS_REQUIRED}.")
        print("  ** Khong du de chia train/test co y nghia. Can chay 'python sync_warehouse.py --full'")
        print("  ** de keo lai lich su tu Bravo (kho chi giu CHI TIET 12 thang gan nhat; cu hon da bi")
        print("  ** nen vao bang monthly_customer_summary - dung duoc cho du bao THEO THANG nhung")
        print("  ** KHONG dung duoc cho du bao TRONG THANG vi mat chi tiet tung ngay).")
        if not months:
            return 1

    if len(months) > TEST_MONTHS:
        train_months = months[:-TEST_MONTHS]
        test_months = months[-TEST_MONTHS:]
    else:
        train_months, test_months = months, []

    print(f"\nCHIA THEO THOI GIAN (KHONG ngau nhien):")
    print(f"  TRAIN ({len(train_months)} thang): {train_months}")
    print(f"  TEST  ({len(test_months)} thang): {test_months}")

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, subset in (("train", train_months), ("test", test_months)):
        if not subset:
            continue
        path = os.path.join(OUT_DIR, f"intramonth_{name}.csv")
        sel = [r for r in all_rows if r["year_month"] in subset]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(sel)
        print(f"  Da ghi {len(sel):>5} dong -> {path}")

    if not test_months:
        print("\nChua du thang de danh gia baseline - dung o buoc dung du lieu.")
        return 0

    table, errs = baseline_and_eval(all_rows, set(train_months), set(test_months))

    print(f"\n{'=' * 78}")
    print("BASELINE (hoc ty trong tu TRAIN, do sai so tren TEST)")
    print("Cach du bao: tong_ca_thang = luy_ke_den_ngay_d / ty_trong_trung_vi(kenh, ngay d)")
    print("Day la ban THAY THE dung dan cho cach hardcode 13,41%/14,07% cua tool cu.")
    print("=" * 78)
    print(f"  {'Kenh':<6}{'Ngay':>6}{'Ty trong hoc duoc':>20}{'Sai so TB (MAPE)':>20}")
    for channel in CHANNELS:
        for cutoff in CUTOFF_DAYS:
            if cutoff not in (5, 10, 15, 20, 25):
                continue
            ratio = table.get((channel, cutoff))
            e = errs.get((channel, cutoff), [])
            if ratio is None or not e:
                continue
            mape = sum(e) / len(e)
            print(f"  {channel:<6}{cutoff:>6}{ratio * 100:>19.2f}%{mape:>19.1f}%")

    print("\nDoc bang tren the nao: sai so giam dan ve cuoi thang la BINH THUONG (cang gan cuoi cang")
    print("biet nhieu). Neu sai so o ngay 20-25 van cao (>10%) thi baseline ty trong KHONG du dung,")
    print("phai them dac trung (ngay trong tuan, so ngay kinh doanh con lai, mua vu) hoac doi mo hinh.")
    print("\nCHUA lam gi voi mo hinh phuc tap hon - buoc nay chi dung du lieu + moc so sanh. Moi mo")
    print("hinh moi PHAI danh bai duoc baseline nay tren dung tap TEST, neu khong thi khong dang dung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
