# -*- coding: utf-8 -*-
"""
Dung chuoi doanh thu THEO THANG + danh gia cac mo hinh nen (baseline) cho bai toan:
DU BAO DOANH THU THANG TOI.

CHAY TREN MAY 24 (noi co warehouse.db that):
    cd C:\\dnh_chatbot\\backend
    python D:\\DNH\\scripts\\forecast_monthly_dataset.py
    (hoac copy file nay vao backend/ roi chay: python forecast_monthly_dataset.py)

CHI DOC (SELECT), khong ghi gi vao warehouse.db.
Ket qua ghi ra scratch/forecast/ canh warehouse.db.

=== VI SAO DU BAO THEO THANG DE HON DU BAO TRONG THANG ===
Kho chi giu CHI TIET TUNG NGAY 12 thang gan nhat; cu hon bi nen vao monthly_customer_summary
(mat chi tiet ngay, CON tong theo thang). Nghia la:
  - Du bao TRONG THANG (can du lieu ngay): toi da 12 thang lich su -> khong hoc duoc mua vu nam.
  - Du bao THEO THANG (chi can tong thang): dung duoc CA bang nen -> lui duoc nhieu nam.
Script nay ghep 2 nguon lai thanh 1 chuoi thang lien tuc.

=== BA DIEU SCRIPT NAY TU KIEM TRUOC KHI TIN DU LIEU ===
1. HAI NGUON CO DEM TRUNG KHONG. Theo thiet ke thi khong (nen xong la xoa khoi bang chi tiet), nhung
   van kiem that: neu 1 thang xuat hien o CA hai nguon -> bao dong, uu tien lay ban CHI TIET.
2. BANG NEN CO DONG TRUNG KHONG. _compress_rows_to_summary() dung INSERT thuan va bang
   monthly_customer_summary KHONG co rang buoc duy nhat - neu 1 lan sync tung crash giua chung
   (da insert nhung chua kip xoa khoi bang chi tiet) thi lan sau se insert lai, THOI PHONG doanh thu
   thang cu ma khong ai biet. Kiem bang cach dem (thang, kenh, khach, nhan vien) trung.
3. THANG DAU/CUOI CO TRON VEN KHONG. Thang hien tai chua xong, thang dau cua so du lieu co the bi
   cat -> loai ca hai, neu khong mo hinh se hoc nham "thang nao cung hut".

=== CHIA TRAIN/TEST ===
Dung WALK-FORWARD (rolling origin), KHONG phai chia doi mot lan. Voi chuoi thang ngan thi walk-forward
tan dung du lieu tot hon: voi moi thang trong tap test, hoc tren TAT CA thang truoc no roi du bao 1
buoc. Tuyet doi khong chia ngau nhien - do la cho model nhin trom tuong lai.
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
TEST_MONTHS = 6           # so thang cuoi dung de danh gia (walk-forward tren tung thang)
MIN_MONTHS_REQUIRED = 12  # duoi muc nay thi moi ket luan deu khong dang tin


def _q(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        print(f"    (bo qua: {e})")
        return []


def month_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7])
    total = y * 12 + (m - 1) + k
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def load_monthly(conn, channel, table):
    """Ghep chuoi thang tu 2 nguon. Tra ve (series, chan_doan)."""
    detail = {r[0]: float(r[1] or 0.0) for r in _q(
        conn, f"SELECT substr(doc_date,1,7) ym, SUM(amount9) FROM {table} "
              f"WHERE doc_date IS NOT NULL GROUP BY ym")}
    compressed = {r[0]: float(r[1] or 0.0) for r in _q(
        conn, "SELECT year_month, SUM(revenue) FROM monthly_customer_summary "
              "WHERE channel=? GROUP BY year_month", (channel,))}

    diag = {"n_detail": len(detail), "n_compressed": len(compressed)}

    # (1) Kiem dem trung giua 2 nguon
    overlap = sorted(set(detail) & set(compressed))
    diag["overlap"] = overlap

    # (2) Kiem dong trung trong bang nen
    dup = _q(conn, "SELECT year_month, COUNT(*) - COUNT(DISTINCT customer_code || '|' || "
                    "COALESCE(employee_code,'')) AS thua FROM monthly_customer_summary "
                    "WHERE channel=? GROUP BY year_month HAVING thua > 0 ORDER BY year_month",
             (channel,))
    diag["dup_months"] = [(r[0], r[1]) for r in dup]

    series = dict(compressed)
    series.update(detail)   # thang nao co ca 2 -> uu tien ban CHI TIET (moi va chinh xac hon)
    return series, diag


def usable_months(series):
    """Loai thang hien tai + thang dau (co the bi cat) + thang co doanh thu = 0."""
    if not series:
        return [], {}
    months = sorted(series)
    today = dt.date.today()
    cur = f"{today.year:04d}-{today.month:02d}"
    reasons, out = {}, []
    for ym in months:
        if ym == cur:
            reasons[ym] = "LOAI - thang hien tai, chua ket thuc"
        elif ym == months[0]:
            reasons[ym] = "LOAI - thang dau cua so du lieu, co the bi cat"
        elif series[ym] <= 0:
            reasons[ym] = "LOAI - doanh thu = 0"
        else:
            out.append(ym)
            reasons[ym] = "dung duoc"
    # phai lien tuc: neu thieu thang o giua thi cac mo hinh tre (lag) se sai
    gaps = [month_add(out[i], 1) for i in range(len(out) - 1) if month_add(out[i], 1) != out[i + 1]]
    return out, (reasons, gaps)


def forecasts_for(series, months, t_idx):
    """Du bao thang months[t_idx] CHI dung du lieu cac thang TRUOC do (khong nhin tuong lai)."""
    hist = months[:t_idx]
    if not hist:
        return {}
    vals = [series[m] for m in hist]
    out = {"naive_thang_truoc": vals[-1]}
    if len(vals) >= 3:
        out["trung_binh_3_thang"] = sum(vals[-3:]) / 3
    if len(vals) >= 2:
        out["xu_huong_tuyen_tinh"] = vals[-1] + (vals[-1] - vals[-2])
    same_last_year = month_add(months[t_idx], -12)
    if same_last_year in series and same_last_year in set(hist):
        out["cung_ky_nam_truoc"] = series[same_last_year]
        # cung ky nam truoc, dieu chinh theo da tang truong 3 thang gan nhat
        prev_year_recent = [series.get(month_add(m, -12)) for m in hist[-3:]]
        if all(v for v in prev_year_recent):
            growth = sum(vals[-3:]) / sum(prev_year_recent)
            out["cung_ky_x_tang_truong"] = series[same_last_year] * growth
    return out


def main():
    print("DA TAT: khong chay nghien cuu/du bao tuong lai. He thong chi phuc vu du lieu thuc te va lich su.")
    return 2

    # Ma nghien cuu cu giu lai de audit; khong the chay qua entrypoint.
    print("=" * 78)
    print("CHUOI DOANH THU THEO THANG + DANH GIA CAC MO HINH NEN")
    print("=" * 78)

    if not os.path.exists(DB_PATH):
        print(f"KHONG tim thay {DB_PATH}. Dat DNH_BACKEND_DIR neu nam cho khac.")
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    all_series, rows_csv = {}, []

    for channel, table in CHANNELS.items():
        print(f"\n{'-' * 78}\nKENH {channel}\n{'-' * 78}")
        series, diag = load_monthly(conn, channel, table)

        print(f"  Thang lay tu bang CHI TIET ({table}) : {diag['n_detail']}")
        print(f"  Thang lay tu bang NEN (monthly_customer_summary): {diag['n_compressed']}")

        if diag["overlap"]:
            print(f"  ** CANH BAO: {len(diag['overlap'])} thang co o CA HAI nguon -> {diag['overlap'][:6]}")
            print("  ** Da uu tien lay ban CHI TIET. Neu nhieu thang bi trung, nghi buoc nen chua xoa")
            print("  ** het khoi bang chi tiet - kiem lai compress_aged_out_months().")
        else:
            print("  Khong co thang nao bi dem trung giua 2 nguon. (dung nhu thiet ke)")

        if diag["dup_months"]:
            print(f"  ** CANH BAO NANG: bang nen co dong TRUNG o {len(diag['dup_months'])} thang:")
            for ym, thua in diag["dup_months"][:8]:
                print(f"       {ym}: thua {thua} dong")
            print("  ** monthly_customer_summary KHONG co rang buoc duy nhat va _compress_rows_to_summary()")
            print("  ** dung INSERT thuan -> 1 lan sync crash giua chung se nen lai, THOI PHONG doanh thu.")
            print("  ** PHAI xu ly truoc khi dung so nay du bao.")
        else:
            print("  Bang nen khong co dong trung.")

        months, (reasons, gaps) = usable_months(series)
        if gaps:
            print(f"  ** CANH BAO: chuoi bi DUT o cac thang {gaps} - mo hinh dung do tre (lag) se sai.")

        if months:
            print(f"  Thang dung duoc: {len(months)}  ({months[0]} -> {months[-1]})")
        loai = [ym for ym, r in reasons.items() if r.startswith("LOAI")]
        for ym in loai:
            print(f"     {ym}: {reasons[ym]}")

        all_series[channel] = (series, months)
        for ym in months:
            rows_csv.append({"year_month": ym, "channel": channel,
                              "revenue": round(series[ym], 2)})

    conn.close()

    print(f"\n{'=' * 78}")
    os.makedirs(OUT_DIR, exist_ok=True)
    if rows_csv:
        path = os.path.join(OUT_DIR, "monthly_series.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["year_month", "channel", "revenue"])
            w.writeheader()
            w.writerows(rows_csv)
        print(f"Da ghi chuoi thang -> {path}")

    for channel, (series, months) in all_series.items():
        print(f"\n{'=' * 78}")
        print(f"DANH GIA MO HINH NEN - KENH {channel}  (walk-forward, du bao 1 thang toi)")
        print("=" * 78)

        if len(months) < MIN_MONTHS_REQUIRED:
            print(f"  ** CHI CO {len(months)} thang - duoi muc toi thieu {MIN_MONTHS_REQUIRED}.")
            print("  ** Moi ket luan tu day deu KHONG dang tin. Muon them lich su: chay")
            print("  ** 'python sync_warehouse.py --full' de keo toan bo lich su tu Bravo (thang cu")
            print("  ** se vao bang nen, van dung duoc cho du bao THEO THANG).")
            if len(months) < 4:
                continue

        n_test = min(TEST_MONTHS, max(1, len(months) - 3))
        test_idx = range(len(months) - n_test, len(months))
        print(f"  Train: {months[0]} -> {months[len(months) - n_test - 1]}"
              f"   |   Test: {months[len(months) - n_test]} -> {months[-1]}  ({n_test} thang)")
        if len(months) < 25:
            print("  Luu y: duoi 25 thang thi mo hinh 'cung ky nam truoc' hau nhu khong chay duoc")
            print("  (thieu du lieu nam truoc) - can >=24 thang moi hoc duoc mua vu.")

        errs = defaultdict(list)
        for t in test_idx:
            actual = series[months[t]]
            for name, pred in forecasts_for(series, months, t).items():
                if actual > 0:
                    errs[name].append(abs(pred - actual) / actual * 100)

        if not errs:
            print("  Khong du du lieu de danh gia.")
            continue
        print(f"\n  {'Mo hinh nen':<26}{'So thang do':>13}{'Sai so TB (MAPE)':>20}")
        for name, e in sorted(errs.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
            print(f"  {name:<26}{len(e):>13}{sum(e) / len(e):>19.1f}%")
        best = min(errs.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        print(f"\n  -> Tot nhat: '{best[0]}' voi MAPE {sum(best[1]) / len(best[1]):.1f}%")

    print(f"\n{'=' * 78}")
    print("MOC SO SANH: mo hinh moi (hoi quy, cay, chuoi thoi gian...) PHAI danh bai duoc con so")
    print("MAPE tot nhat o tren, tren DUNG tap test nay. Neu khong vuot duoc thi khong dang dung -")
    print("cang phuc tap cang kho giai thich cho khach khi so lech.")
    print("\nCHUA lam mo hinh nao o buoc nay. Day moi la du lieu + moc so sanh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
