# -*- coding: utf-8 -*-
"""Nghiên cứu insight cảnh báo MỚI bằng kiểm thử ngược trên Bravo — 15/09/2026. CHỈ ĐỌC, không gửi gì.

Cùng phương pháp docs/bao_cao_canh_bao_kiem_thu_nguoc_14-09.md: chạy lại quy tắc trên lịch sử thật, đo
(1) bắn bao nhiêu lần, (2) lần bắn có rơi đúng vào kết cục xấu không so với tỷ lệ nền, (3) báo trước bao lâu.
Chỉ đề xuất quy tắc: chính xác hơn hẳn tỷ lệ nền, khối lượng xử lý nổi, có hành động cụ thể.

Chạy trên máy vào được Bravo (đọc .env ở gốc repo):
    set PYTHONIOENCODING=utf-8
    python scripts/nghien_cuu_insight.py keo-cong-no     # 53 lần gọi SP công nợ theo tuần, ~12 phút, có cache
    python scripts/nghien_cuu_insight.py keo-du-lieu     # hóa đơn, snapshot KPI, chỉ tiêu, hợp đồng ETC
    python scripts/nghien_cuu_insight.py phan-tich       # đọc cache -> results/nghien_cuu_insight/ket_qua.json

Dữ liệu kéo về nằm ở results/nghien_cuu_insight/ (git bỏ qua). Các hàm phân tích là hàm thuần, có test
tests/test_nghien_cuu_insight.py.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "results", "nghien_cuu_insight")

# --------------------------------------------------------------------------------------------------
# Tiện ích chung
# --------------------------------------------------------------------------------------------------


def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def month_add(y, m, n):
    idx = y * 12 + (m - 1) + n
    return idx // 12, idx % 12 + 1


def mondays(start, end):
    """Các thứ Hai trong [start, end]."""
    d = _as_date(start)
    d += dt.timedelta(days=(7 - d.weekday()) % 7)
    out = []
    while d <= _as_date(end):
        out.append(d)
        d += dt.timedelta(days=7)
    return out


def ratio(a, b):
    return a / b if b else None


def pct(a, b):
    r = ratio(a, b)
    return None if r is None else round(r * 100, 1)


def _engine():
    sys.path.insert(0, ROOT)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    from src.database import _get_bravo_engine
    eng = _get_bravo_engine()
    if eng is None:
        raise SystemExit("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env ở gốc repo).")
    return eng


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)


def _read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------------------------------
# 1. Công nợ sắp chạm 45 ngày — dữ liệu: SP usp_DeptAccDueDate_GetData gọi với ngày chốt quá khứ
# --------------------------------------------------------------------------------------------------

CONG_NO_DIR = os.path.join(CACHE, "cong_no")
CONG_NO_COLS = ["customer_code", "channel", "area", "balance", "b1_15", "b16_30", "b31_45", "gt45"]


def _norm_area(raw, customer_code):
    from src.region_map import region_from_customer_code
    if raw == "MB1":
        return "MB"
    return raw or region_from_customer_code(customer_code) or ""


def keo_cong_no(ngay_list, force=False):
    """Gọi SP công nợ cho từng ngày chốt, lưu mỗi ngày một file. Cùng tham số với
    src/alerts.py::get_bravo_receivables_snapshot (mốc 7/15 ngày, gồm chứng từ ứng trước)."""
    eng = _engine()
    for d in ngay_list:
        path = os.path.join(CONG_NO_DIR, f"{d.isoformat()}.csv")
        if os.path.exists(path) and not force:
            continue
        raw = eng.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute("EXEC dbo.usp_DeptAccDueDate_GetData @_DocDate1=?, @_DocDate2=?, @_Period1=?, "
                        "@_Period2=?, @_RepType=?, @_IsPrepaymentInclude=?",
                        f"{d.year}-01-01", d.isoformat(), 7, 15, 1, 1)
            data, ix = [], {}
            while True:
                if cur.description is not None:
                    cols = [c[0] for c in cur.description]
                    if "CustomerCode" in cols and "OverDueAmount" in cols:
                        ix = {c: i for i, c in enumerate(cols)}
                        data = cur.fetchall()
                        break
                if not cur.nextset():
                    break
        finally:
            raw.rollback()
        gop = {}
        for r in data:
            cc = r[ix["CustomerCode"]]
            if not cc:
                continue
            ch = "OTC" if r[ix["ClassCode"]] == "TM" else "ETC"
            row = gop.setdefault((cc, ch), [cc, ch, _norm_area(r[ix["AreaCode"]], cc), 0.0, 0.0, 0.0, 0.0, 0.0])
            for j, col in enumerate(("CloseBal", "CloseBal5", "CloseBal6", "CloseBal7", "CloseBal8"), start=3):
                row[j] += float(r[ix[col]] or 0)
        _write_csv(path, CONG_NO_COLS, gop.values())
        print(f"[cong-no] {d}: {len(gop)} khach x kenh")


def doc_cong_no():
    """{date: {(cc, channel): {'area', 'b31_45', 'gt45', 'balance'}}} từ cache."""
    out = {}
    if not os.path.isdir(CONG_NO_DIR):
        return out
    for name in sorted(os.listdir(CONG_NO_DIR)):
        if not name.endswith(".csv"):
            continue
        d = _as_date(name[:10])
        out[d] = {(r["customer_code"], r["channel"]): {
            "area": r["area"], "balance": float(r["balance"]), "b31_45": float(r["b31_45"]),
            "gt45": float(r["gt45"])} for r in _read_csv(os.path.join(CONG_NO_DIR, name))}
    return out


_ZERO_DEBT = {"area": "", "balance": 0.0, "b31_45": 0.0, "gt45": 0.0}


def phan_tich_no_sap_45(snaps, nguong_list=(20e6, 50e6, 100e6), buoc_ngay=14, ty_le_chuyen=0.5,
                        nguong_su_kien=50e6):
    """Quy tắc ứng viên: tại ngày d khách có nợ 31–45 ngày >= T và CHƯA có nợ >45 ngày.

    Kết cục "trượt thành nợ xấu": sau ``buoc_ngay`` ngày, nợ >45 ngày tăng ít nhất ``ty_le_chuyen`` x phần
    31–45 đã thấy (tức phần đó không được thu mà rơi vào >45). Tỷ lệ nền: mọi khách có nợ 31–45 > 0.

    Độ phủ (recall) so với cảnh báo đang chạy "khách mới rơi vào nợ >45 ngày > nguong_su_kien": sự kiện tại
    ngày e (nợ >45 ngày vượt ngưỡng, tuần trước 0) có bị quy tắc này bắn trước đó ``buoc_ngay`` ngày không.
    """
    ngay = sorted(snaps)
    co = set(ngay)
    nen = defaultdict(lambda: [0, 0])                      # kênh -> [số, trượt]
    ban = defaultdict(lambda: {"so": 0, "truot": 0, "gia_tri": 0.0, "gia_tri_truot": 0.0,
                               "theo_tuan": defaultdict(int)})
    for d in ngay:
        d2 = d + dt.timedelta(days=buoc_ngay)
        if d2 not in co:
            continue
        sau = snaps[d2]
        for key, row in snaps[d].items():
            x = row["b31_45"]
            if x <= 0:
                continue
            ch = key[1]
            truot = (sau.get(key, _ZERO_DEBT)["gt45"] - row["gt45"]) >= ty_le_chuyen * x
            nen[ch][0] += 1
            nen[ch][1] += int(truot)
            if row["gt45"] > 0:
                continue
            for t in nguong_list:
                if x >= t:
                    b = ban[(t, ch)]
                    b["so"] += 1
                    b["truot"] += int(truot)
                    b["gia_tri"] += x
                    b["gia_tri_truot"] += x if truot else 0.0
                    b["theo_tuan"][d] += 1

    su_kien = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # t -> kênh -> [sự kiện, đã báo trước]
    for e in ngay:
        truoc_1_tuan = e - dt.timedelta(days=7)
        truoc = e - dt.timedelta(days=buoc_ngay)
        if truoc_1_tuan not in co or truoc not in co:
            continue
        for key, row in snaps[e].items():
            if row["gt45"] <= nguong_su_kien or snaps[truoc_1_tuan].get(key, _ZERO_DEBT)["gt45"] > 0:
                continue
            cu = snaps[truoc].get(key, _ZERO_DEBT)
            for t in nguong_list:
                s = su_kien[t][key[1]]
                s[0] += 1
                s[1] += int(cu["gt45"] <= 0 and cu["b31_45"] >= t)

    ket_qua = {"nen": {ch: {"so": v[0], "ty_le_truot_pct": pct(v[1], v[0])} for ch, v in nen.items()},
               "quy_tac": []}
    so_tuan = len([d for d in ngay if d + dt.timedelta(days=buoc_ngay) in co])
    for (t, ch), b in sorted(ban.items()):
        ket_qua["quy_tac"].append({
            "nguong": t, "kenh": ch, "so_lan_ban": b["so"],
            "trung_binh_moi_tuan": round(b["so"] / so_tuan, 1) if so_tuan else None,
            "do_chinh_xac_pct": pct(b["truot"], b["so"]),
            "ty_le_nen_pct": pct(nen[ch][1], nen[ch][0]),
            "gia_tri_31_45": round(b["gia_tri"]), "gia_tri_da_truot": round(b["gia_tri_truot"]),
            "su_kien_no_45_moi": su_kien[t][ch][0],
            "do_phu_pct": pct(su_kien[t][ch][1], su_kien[t][ch][0]),
        })
    ket_qua["so_tuan_danh_gia"] = so_tuan
    return ket_qua


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------


def quantile(values, q):
    """Phân vị q (0..1) nội suy tuyến tính; None nếu rỗng."""
    vals = sorted(values)
    if not vals:
        return None
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


# --------------------------------------------------------------------------------------------------
# 2. Khách mới không mua lại
# --------------------------------------------------------------------------------------------------


def don_theo_khach(khach_ngay):
    """rows (cc, date, doanh thu) -> {cc: [(ngày, doanh thu)] chỉ ngày có doanh thu > 0, tăng dần}."""
    gop = defaultdict(lambda: defaultdict(float))
    for cc, day, rev in khach_ngay:
        gop[cc][_as_date(day)] += float(rev or 0)
    return {cc: sorted((d, r) for d, r in days.items() if r > 0) for cc, days in gop.items()}


def phan_tich_khach_moi(don, vung, data_end, bat_dau_lich_su, k_list=(30, 45, 60), horizon=90,
                        min_don_dau_list=(0.0, 5e6, 20e6)):
    """Quy tắc ứng viên: khách có đơn đầu tiên (không có đơn nào trong >= 365 ngày lịch sử trước đó), sau
    k ngày chưa có đơn thứ hai -> bắn. Kết cục "mất": vẫn không có đơn nào trong ``horizon`` ngày tiếp theo.
    Tỷ lệ nền: trong MỌI khách mới, bao nhiêu mất (không mua lại trong k + horizon ngày)."""
    data_end, moc_moi = _as_date(data_end), _as_date(bat_dau_lich_su) + dt.timedelta(days=365)
    out = []
    for k in k_list:
        for mn in min_don_dau_list:
            tong = ban = mat = 0
            gia_tri_mat = 0.0
            theo_thang, theo_vung_thang = defaultdict(int), defaultdict(int)
            for cc, orders in don.items():
                if not orders:
                    continue
                first_day, first_rev = orders[0]
                if first_day < moc_moi or first_rev < mn:
                    continue
                if first_day + dt.timedelta(days=k + horizon) > data_end:
                    continue
                tong += 1
                han_k = first_day + dt.timedelta(days=k)
                sau = [d for d, _ in orders[1:]]
                if any(d <= han_k for d in sau):
                    continue
                ban += 1
                thang = (han_k.year, han_k.month)
                theo_thang[thang] += 1
                theo_vung_thang[(vung.get(cc, ""), thang)] += 1
                if not any(d <= han_k + dt.timedelta(days=horizon) for d in sau):
                    mat += 1
                    gia_tri_mat += first_rev
            so_thang = len(theo_thang)
            out.append({
                "k_ngay": k, "don_dau_toi_thieu": mn, "tong_khach_moi": tong, "so_lan_ban": ban,
                "ty_le_ban_pct": pct(ban, tong), "do_chinh_xac_pct": pct(mat, ban),
                "ty_le_nen_mat_pct": pct(mat, tong), "tu_quay_lai_pct": pct(ban - mat, ban),
                "tb_moi_thang": round(ban / so_thang, 1) if so_thang else None,
                "max_mot_vung_mot_thang": max(theo_vung_thang.values()) if theo_vung_thang else 0,
                "gia_tri_don_dau_khach_mat": round(gia_tri_mat),
            })
    return out


# --------------------------------------------------------------------------------------------------
# 3. Khách lớn bỏ SKU chủ lực
# --------------------------------------------------------------------------------------------------


def khach_upto_ngay(don, ngay=20):
    """{(cc, (y, m)): doanh thu các ngày <= ``ngay`` của tháng}."""
    out = defaultdict(float)
    for cc, orders in don.items():
        for d, r in orders:
            if d.day <= ngay:
                out[(cc, (d.year, d.month))] += r
    return out


def phan_tich_sku_chu_luc(sku_rows, khach_upto20, thang_list, lookback=6, min_thang=5, min_tb=10e6):
    """Quy tắc ứng viên: cặp (khách, SKU) mua đều (>= min_thang/lookback tháng, TB >= min_tb/tháng), khách
    VẪN có đơn tới ngày 20 tháng M nhưng chưa lấy SKU đó -> bắn. Khác "khách im lặng" (khách không mua gì).
    Kết cục "bỏ thật": SKU đó không có doanh thu cả tháng M lẫn tháng M+1.
    Tỷ lệ nền: mọi cặp mua đều có khách hoạt động tới ngày 20."""
    hist = defaultdict(dict)
    for cc, item, ym, full, upto in sku_rows:
        hist[(cc, item)][tuple(ym)] = (float(full or 0), float(upto or 0))
    ung_vien = {key: h for key, h in hist.items() if sum(1 for v in h.values() if v[0] > 0) >= min_thang}
    nen = nen_bo = ban = bo = 0
    gia_tri_bo = 0.0
    theo_thang = defaultdict(int)
    for M in thang_list:
        M = tuple(M)
        truoc = [month_add(M[0], M[1], -i) for i in range(1, lookback + 1)]
        sau = month_add(M[0], M[1], 1)
        for (cc, item), h in ung_vien.items():
            vals = [h.get(p, (0.0, 0.0))[0] for p in truoc]
            if sum(1 for v in vals if v > 0) < min_thang:
                continue
            tb = sum(vals) / lookback
            if tb < min_tb or khach_upto20.get((cc, M), 0) <= 0:
                continue
            cur, nxt = h.get(M, (0.0, 0.0)), h.get(sau, (0.0, 0.0))
            bo_that = cur[0] <= 0 and nxt[0] <= 0
            nen += 1
            nen_bo += int(bo_that)
            if cur[1] <= 0:
                ban += 1
                bo += int(bo_that)
                gia_tri_bo += tb if bo_that else 0.0
                theo_thang[M] += 1
    so_thang = len([m for m in thang_list])
    return {"min_tb": min_tb, "so_cap_danh_gia": nen, "ty_le_nen_bo_pct": pct(nen_bo, nen),
            "so_lan_ban": ban, "do_chinh_xac_pct": pct(bo, ban),
            "tb_moi_thang": round(ban / so_thang, 1) if so_thang else None,
            "doanh_thu_thang_mat_tb": round(gia_tri_bo / so_thang) if so_thang else None,
            "thang_ban_nhieu_nhat": max(theo_thang.values()) if theo_thang else 0}


# --------------------------------------------------------------------------------------------------
# 4. Đội QLV mất độ phủ khách
# --------------------------------------------------------------------------------------------------


def phan_tich_do_phu_doi(nhan_su_thang, khach_nv_thang, thang_list, nguong_giam=(0.10, 0.15, 0.20),
                         min_nv=3, nguong_kpi=0.8):
    """Quy tắc ứng viên: số khách có mua của đội tháng M giảm >= X so TB 3 tháng trước -> bắn.
    Kết cục: tháng M+1 đội đạt < 80% chỉ tiêu (snapshot KPI tầng quản lý). Tách riêng đội tháng M đã
    < 80% để thấy quy tắc có thêm thông tin hay chỉ lặp lại "đội yếu thì yếu tiếp".

    nhan_su_thang: (ym, employee, dms, manager, target, actual) - dòng quản lý có target/actual rollup.
    khach_nv_thang: (ym, dms, customer) khách có doanh thu > 0 trong tháng."""
    quan_ly = defaultdict(set)
    for ym, emp, dms, mgr, tgt, act in nhan_su_thang:
        if mgr:
            quan_ly[tuple(ym)].add(mgr)
    doi_cua_dms = defaultdict(dict)
    so_nv = defaultdict(int)
    dat = {}
    for ym, emp, dms, mgr, tgt, act in nhan_su_thang:
        ym = tuple(ym)
        doi = mgr or (emp if emp in quan_ly[ym] else None)
        if doi and dms:
            doi_cua_dms[ym][dms] = doi
            if mgr:
                so_nv[(ym, doi)] += 1
        if emp in quan_ly[ym] and float(tgt or 0) > 0:
            dat[(ym, emp)] = float(act or 0) / float(tgt)
    khach = defaultdict(set)
    for ym, dms, cc in khach_nv_thang:
        doi = doi_cua_dms[tuple(ym)].get(dms)
        if doi:
            khach[(tuple(ym), doi)].add(cc)
    dem = {key: len(v) for key, v in khach.items()}

    def giam(M, doi):
        truoc = [dem.get((month_add(M[0], M[1], -i), doi)) for i in (1, 2, 3)]
        if any(not x for x in truoc):
            return None
        return 1 - dem.get((M, doi), 0) / (sum(truoc) / 3)

    out = []
    for x in nguong_giam:
        nen = nen_xau = ban = ban_xau = 0
        nhom = {"da_duoi_80": [0, 0], "dang_tren_80": [0, 0]}
        nen_nhom = {"da_duoi_80": [0, 0], "dang_tren_80": [0, 0]}
        for M in thang_list:
            M = tuple(M)
            sau = month_add(M[0], M[1], 1)
            for doi in quan_ly[M]:
                if so_nv[(M, doi)] < min_nv or (sau, doi) not in dat or (M, doi) not in dat:
                    continue
                g = giam(M, doi)
                if g is None:
                    continue
                xau = dat[(sau, doi)] < nguong_kpi
                ten_nhom = "da_duoi_80" if dat[(M, doi)] < nguong_kpi else "dang_tren_80"
                nen += 1
                nen_xau += int(xau)
                nen_nhom[ten_nhom][0] += 1
                nen_nhom[ten_nhom][1] += int(xau)
                if g >= x:
                    ban += 1
                    ban_xau += int(xau)
                    nhom[ten_nhom][0] += 1
                    nhom[ten_nhom][1] += int(xau)
        out.append({
            "nguong_giam_pct": round(x * 100), "so_doi_thang": nen, "ty_le_nen_duoi_80_pct": pct(nen_xau, nen),
            "so_lan_ban": ban, "do_chinh_xac_pct": pct(ban_xau, ban),
            "tb_moi_thang": round(ban / len(thang_list), 1) if thang_list else None,
            "khi_thang_nay_da_duoi_80": {"ban": nhom["da_duoi_80"][0], "chinh_xac_pct": pct(*nhom["da_duoi_80"][::-1]),
                                         "nen_pct": pct(*nen_nhom["da_duoi_80"][::-1])},
            "khi_thang_nay_tren_80": {"ban": nhom["dang_tren_80"][0], "chinh_xac_pct": pct(*nhom["dang_tren_80"][::-1]),
                                      "nen_pct": pct(*nen_nhom["dang_tren_80"][::-1])},
        })
    return out


# --------------------------------------------------------------------------------------------------
# 5. Chỉ tiêu còn lại vượt năng lực bán lịch sử
# --------------------------------------------------------------------------------------------------


def phan_tich_chi_tieu(doanh_thu_ngay, chi_tieu, last_day, ngay_list=(10, 15, 20, 25), lookback=3, q=0.9,
                       min_hist=6):
    """Quy tắc ứng viên: tới ngày d, lũy kế + phần doanh thu còn lại ở mức CAO (phân vị q) của lịch sử cùng
    giai đoạn vẫn < chỉ tiêu -> bắn "không thể đạt". Phần còn lại tính theo tỷ lệ so với TB 3 tháng trước.
    Kết cục: cả tháng thật sự < chỉ tiêu (và < 80%). Chỉ dùng tháng trước M để tính phân vị, không nhìn trước.

    doanh_thu_ngay: {date: doanh thu}; chi_tieu: {(y, m): chỉ tiêu}; last_day: ngày dữ liệu cuối cùng."""
    last_day = _as_date(last_day)
    theo_thang = defaultdict(dict)
    for d, r in doanh_thu_ngay.items():
        d = _as_date(d)
        theo_thang[(d.year, d.month)][d.day] = theo_thang[(d.year, d.month)].get(d.day, 0.0) + float(r)
    thang = sorted(m for m in theo_thang
                   if dt.date(*month_add(m[0], m[1], 1), 1) - dt.timedelta(days=1) <= last_day)
    tong = {m: sum(theo_thang[m].values()) for m in thang}

    def tb3(m):
        truoc = [month_add(m[0], m[1], -i) for i in (1, 2, 3)]
        if any(p not in tong for p in truoc):
            return None
        return sum(tong[p] for p in truoc) / 3

    ket_qua, ban_ghi = [], []
    for d in ngay_list:
        c = {"ngay": d, "so_thang": 0, "duoi_100": 0, "ban_100": 0, "dung_100": 0,
             "duoi_80": 0, "ban_80": 0, "dung_80": 0}
        for i, M in enumerate(thang):
            T, base = chi_tieu.get(M), tb3(M)
            if not T or not base:
                continue
            lich_su = [P for P in thang[:i] if tb3(P)]
            if len(lich_su) < min_hist:
                continue
            con_lai = quantile([sum(v for day, v in theo_thang[P].items() if day > d) / tb3(P)
                                for P in lich_su], q)
            mtd = sum(v for day, v in theo_thang[M].items() if day <= d)
            toi_da = mtd + con_lai * base
            c["so_thang"] += 1
            thuc = tong[M]
            for muc, he_so in (("100", 1.0), ("80", 0.8)):
                duoi = thuc < he_so * T
                ban = toi_da < he_so * T
                c["duoi_" + muc] += int(duoi)
                c["ban_" + muc] += int(ban)
                c["dung_" + muc] += int(ban and duoi)
            if toi_da < T:
                ban_ghi.append({"thang": "%04d-%02d" % M, "ngay": d, "luy_ke_pct_chi_tieu": pct(mtd, T),
                                "toi_da_pct": pct(toi_da, T), "thuc_te_pct": pct(thuc, T)})
        for muc in ("100", "80"):
            c["do_chinh_xac_%s_pct" % muc] = pct(c["dung_" + muc], c["ban_" + muc])
            c["do_phu_%s_pct" % muc] = pct(c["dung_" + muc], c["duoi_" + muc])
        ket_qua.append(c)
    return {"theo_ngay": ket_qua, "cac_lan_ban_100": ban_ghi}


# --------------------------------------------------------------------------------------------------
# 6. Hợp đồng ETC sắp hết hạn, thực hiện thấp
# --------------------------------------------------------------------------------------------------


def phan_tich_hop_dong(hop_dong, hoa_don, data_end, moc_ngay=(90, 60), nguong_thuc_hien=0.5,
                       nguong_con_lai=(1.0, 500e6), ket_cuc=0.7, an_han=60, tu_ngay="2024-01-01"):
    """Quy tắc ứng viên: còn ``moc`` ngày tới hạn hợp đồng mà mới xuất hóa đơn < 50% giá trị, phần còn lại
    >= R -> bắn. Kết cục: tới hạn + ``an_han`` ngày vẫn thực hiện < 70%. Đo thêm tỷ lệ bù kịp và tỷ lệ khách có
    hợp đồng MỚI ký quanh ngày hết hạn (thấp vì được thay bằng hợp đồng khác, không phải mất doanh thu).

    hop_dong: {id: {cc, tu, den, gia_tri, lech}}; hoa_don: {id: [(ngày, giá trị)]}."""
    data_end, tu_ngay = _as_date(data_end), _as_date(tu_ngay)
    hd_theo_khach = defaultdict(list)
    for hid, h in hop_dong.items():
        hd_theo_khach[h["cc"]].append((_as_date(h["tu"]), hid))

    def luy_ke(hid, den):
        return sum(v for d, v in hoa_don.get(hid, []) if d <= den)

    out = []
    for moc in moc_ngay:
        for R in nguong_con_lai:
            nen = nen_thap = ban = ban_thap = gia_han = 0
            con_lai_mat = 0.0
            bu = []
            theo_thang = defaultdict(int)
            for hid, h in hop_dong.items():
                den, tu = _as_date(h["den"]), _as_date(h["tu"])
                gia_tri = float(h["gia_tri"] or 0)
                if gia_tri <= 0 or h.get("lech") or den < tu_ngay or den + dt.timedelta(days=an_han) > data_end:
                    continue
                c = den - dt.timedelta(days=moc)
                if tu > c:
                    continue
                da_c = luy_ke(hid, c)
                con = gia_tri - da_c
                if con < R:
                    continue
                cuoi = luy_ke(hid, den + dt.timedelta(days=an_han))
                thap = cuoi / gia_tri < ket_cuc
                nen += 1
                nen_thap += int(thap)
                if da_c / gia_tri >= nguong_thuc_hien:
                    continue
                ban += 1
                ban_thap += int(thap)
                theo_thang[(c.year, c.month)] += 1
                bu.append((cuoi - da_c) / con if con > 0 else 0.0)
                if thap:
                    con_lai_mat += gia_tri - cuoi
                    moi = [t for t, other in hd_theo_khach[h["cc"]] if other != hid
                           and den - dt.timedelta(days=30) <= t <= den + dt.timedelta(days=an_han)]
                    gia_han += int(bool(moi))
            out.append({
                "moc_ngay": moc, "con_lai_toi_thieu": R, "so_hop_dong": nen, "ty_le_nen_thap_pct": pct(nen_thap, nen),
                "so_lan_ban": ban, "do_chinh_xac_pct": pct(ban_thap, ban),
                "tb_moi_thang": round(ban / len(theo_thang), 1) if theo_thang else None,
                "bu_kip_trung_vi_pct": round(quantile(bu, 0.5) * 100, 1) if bu else None,
                "thap_nhung_co_hop_dong_moi_pct": pct(gia_han, ban_thap),
                "gia_tri_con_lai_khong_thuc_hien": round(con_lai_mat),
            })
    return out


# --------------------------------------------------------------------------------------------------
# Kéo dữ liệu (chỉ đọc Bravo) và chạy phân tích
# --------------------------------------------------------------------------------------------------

VIEWS = {"OTC": "dbo.vHoaDonTotal", "ETC": "dbo.vHoaDonETCTotal"}


def _sql_khach(channel):
    """(join, area_expr, keep_where) - loại mã rác như bộ cảnh báo, vùng theo đường chính + tiền tố mã."""
    from src.region_map import customer_code_prefix_sql_or, customer_region_resolve_sql
    join, area = customer_region_resolve_sql("v", channel)
    if channel == "ETC":
        join += " LEFT JOIN dbo.DMSSX_KhachHang k ON v.CustomerCode = k.Code"
    keep = f"(k.Code IS NOT NULL OR {customer_code_prefix_sql_or('v.CustomerCode')})"
    return join, area, keep


def keo_du_lieu(force=False):
    from sqlalchemy import text
    eng = _engine()
    hom_nay = dt.date.today()
    end = hom_nay.isoformat()   # loại trừ hôm nay (đang nhập dở)

    def keo(ten, header, sql, **params):
        path = os.path.join(CACHE, ten + ".csv")
        if os.path.exists(path) and not force:
            print(f"[du-lieu] {ten}: dùng cache")
            return
        with eng.connect() as conn:
            rows = [tuple(r) for r in conn.execute(text(sql), {"end": end, **params}).fetchall()]
        _write_csv(path, header, rows)
        print(f"[du-lieu] {ten}: {len(rows):,} dòng")

    for ch, view in VIEWS.items():
        join, area, keep = _sql_khach(ch)
        keo(f"khach_ngay_{ch}", ["cc", "d", "rev"],
            f"SELECT v.CustomerCode, CAST(v.DocDate AS date), SUM(v.Amount9) FROM {view} v {join} "
            f"WHERE {keep} AND v.DocDate >= '2022-07-01' AND v.DocDate < :end "
            f"GROUP BY v.CustomerCode, CAST(v.DocDate AS date)")
        keo(f"khach_vung_{ch}", ["cc", "area"],
            f"SELECT v.CustomerCode, MAX({area}) FROM {view} v {join} WHERE {keep} AND v.DocDate >= '2022-07-01' "
            f"AND v.DocDate < :end GROUP BY v.CustomerCode")
        keo(f"khach_sku_thang_{ch}", ["cc", "item", "y", "m", "full", "upto20"],
            f"SELECT v.CustomerCode, v.ItemCode, YEAR(v.DocDate), MONTH(v.DocDate), SUM(v.Amount9), "
            f"SUM(CASE WHEN DAY(v.DocDate) <= 20 THEN v.Amount9 ELSE 0 END) FROM {view} v {join} "
            f"WHERE {keep} AND v.DocDate >= '2024-07-01' AND v.DocDate < :end "
            f"GROUP BY v.CustomerCode, v.ItemCode, YEAR(v.DocDate), MONTH(v.DocDate)")

    keo("nhan_su_thang", ["ym", "employee", "dms", "manager", "target", "actual"],
        "WITH l AS (SELECT EmployeeCode, CONVERT(varchar(7), SaveDate, 120) ym, MAX(SaveDate) d "
        "FROM dbo.FACT_TongHopKhachHang GROUP BY EmployeeCode, CONVERT(varchar(7), SaveDate, 120)) "
        "SELECT l.ym, f.EmployeeCode, MAX(f.EmpDMSCode), MAX(f.ManagerCode), MAX(f.MonthSaleTarget), "
        "SUM(f.Amount_Cus) FROM dbo.FACT_TongHopKhachHang f JOIN l ON l.EmployeeCode = f.EmployeeCode "
        "AND l.d = f.SaveDate GROUP BY l.ym, f.EmployeeCode")
    keo("khach_nv_thang", ["ym", "dms", "cc"],
        "SELECT CONVERT(varchar(7), DocDate, 120), EmpDMSCode, CustomerCode FROM dbo.vHoaDonTotal "
        "WHERE DocDate >= '2025-01-01' AND DocDate < :end AND EmpDMSCode IS NOT NULL "
        "GROUP BY CONVERT(varchar(7), DocDate, 120), EmpDMSCode, CustomerCode HAVING SUM(Amount9) > 0")
    keo("chi_tieu_vung", ["ym", "area", "target"],
        "SELECT CONVERT(varchar(7), DocDate, 120), AreaCode, SUM(Amount) FROM dbo.DIM_TargetVungMien "
        "GROUP BY CONVERT(varchar(7), DocDate, 120), AreaCode")
    join, area, _ = _sql_khach("OTC")
    keo("doanh_thu_ngay_vung_OTC", ["d", "area", "rev"],
        f"SELECT CAST(v.DocDate AS date), {area}, SUM(v.Amount9) FROM dbo.vHoaDonTotal v {join} "
        f"WHERE v.DocDate >= '2024-09-01' AND v.DocDate < :end GROUP BY CAST(v.DocDate AS date), {area}")
    keo("hop_dong", ["id", "cc", "tu", "den", "gia_tri", "so_dong", "so_dong_lech"],
        # Giá trị hợp đồng lấy TRƯỚC VAT để so cùng gốc với Amount9 trên hóa đơn (xem kiem_vat_hoa_don).
        "WITH dong AS (SELECT Id, RowId, MAX(CustomerCode) CustomerCode, MAX(FromDate) FromDate, MAX(ToDate) ToDate, "
        "MAX(AmountBefVat) AmountBefVat, MAX(Quantity) Quantity, MAX(UnitPrice) UnitPrice "
        "FROM dbo.vHopDongETC GROUP BY Id, RowId) "
        "SELECT Id, MAX(CustomerCode), CONVERT(varchar(10), MAX(FromDate), 120), CONVERT(varchar(10), MAX(ToDate), 120), "
        "SUM(AmountBefVat), COUNT(*), SUM(CASE WHEN ABS(AmountBefVat - Quantity*UnitPrice) > 0.05*CASE WHEN "
        "ABS(AmountBefVat) > ABS(Quantity*UnitPrice) THEN ABS(AmountBefVat) ELSE ABS(Quantity*UnitPrice) END "
        "THEN 1 ELSE 0 END) FROM dong GROUP BY Id")
    keo("kiem_vat_hoa_don", ["amount9", "qty_x_price", "amount3", "amount4"],
        "SELECT SUM(Amount9), SUM(Quantity*UnitPrice), SUM(Amount3), SUM(Amount4) FROM dbo.vHoaDonETCTotal "
        "WHERE DocDate >= '2026-08-01' AND DocDate < '2026-09-01'")
    keo("hop_dong_hoa_don", ["id", "d", "rev"],
        "SELECT ContractId, CAST(DocDate AS date), SUM(Amount9) FROM dbo.vHoaDonETCTotal "
        "WHERE ContractId IS NOT NULL AND DocDate < :end GROUP BY ContractId, CAST(DocDate AS date)")
    with open(os.path.join(CACHE, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"keo_luc": dt.datetime.now().isoformat(timespec="seconds"),
                   "du_lieu_den": (hom_nay - dt.timedelta(days=1)).isoformat()}, f)


def _area_key(area):
    a = (area or "").upper()
    return "bac" if a in ("MB", "MB1", "MB2") else "nam" if a == "MN" else "trung" if a == "MT" else ""


def _thang_giua(tu, den):
    out, (y, m) = [], tu
    while (y, m) <= den:
        out.append((y, m))
        y, m = month_add(y, m, 1)
    return out


def phan_tich():
    with open(os.path.join(CACHE, "meta.json"), encoding="utf-8") as f:
        data_end = _as_date(json.load(f)["du_lieu_den"])
    y, m = data_end.year, data_end.month
    thang_tron_cuoi = (y, m) if (data_end + dt.timedelta(days=1)).month != m else month_add(y, m, -1)
    ket_qua = {"du_lieu_den": data_end.isoformat()}

    def csv_rows(ten):
        return _read_csv(os.path.join(CACHE, ten + ".csv"))

    for ch in ("OTC", "ETC"):
        don = don_theo_khach((r["cc"], r["d"], r["rev"]) for r in csv_rows(f"khach_ngay_{ch}"))
        vung = {r["cc"]: _area_key(r["area"]) for r in csv_rows(f"khach_vung_{ch}")}
        ket_qua[f"khach_moi_{ch}"] = phan_tich_khach_moi(
            don, vung, data_end, "2022-07-01",
            min_don_dau_list=(0.0, 5e6, 20e6) if ch == "OTC" else (0.0, 20e6, 100e6))
        upto20 = khach_upto_ngay(don)
        sku = [(r["cc"], r["item"], (int(r["y"]), int(r["m"])), r["full"], r["upto20"])
               for r in csv_rows(f"khach_sku_thang_{ch}")]
        thang_sku = _thang_giua((2025, 1), month_add(*thang_tron_cuoi, -1))
        ket_qua[f"sku_chu_luc_{ch}"] = [phan_tich_sku_chu_luc(sku, upto20, thang_sku, min_tb=t)
                                        for t in ((5e6, 10e6, 30e6) if ch == "OTC" else (30e6, 100e6))]
        del don, sku, upto20

    ns = [((int(r["ym"][:4]), int(r["ym"][5:7])), r["employee"], r["dms"], r["manager"], r["target"], r["actual"])
          for r in csv_rows("nhan_su_thang")]
    kn = [((int(r["ym"][:4]), int(r["ym"][5:7])), r["dms"], r["cc"]) for r in csv_rows("khach_nv_thang")]
    ket_qua["do_phu_doi"] = phan_tich_do_phu_doi(ns, kn, _thang_giua((2025, 4), month_add(*thang_tron_cuoi, -1)))

    dt_ngay = defaultdict(lambda: defaultdict(float))
    for r in csv_rows("doanh_thu_ngay_vung_OTC"):
        d = _as_date(r["d"])
        dt_ngay[_area_key(r["area"])][d] += float(r["rev"] or 0)
        dt_ngay["toan_quoc"][d] += float(r["rev"] or 0)
    ct = defaultdict(lambda: defaultdict(float))
    for r in csv_rows("chi_tieu_vung"):
        ym = (int(r["ym"][:4]), int(r["ym"][5:7]))
        ct[_area_key(r["area"])][ym] += float(r["target"] or 0)
        ct["toan_quoc"][ym] += float(r["target"] or 0)
    ket_qua["chi_tieu_OTC"] = {vung: phan_tich_chi_tieu(dt_ngay[vung], ct[vung], data_end)
                               for vung in ("toan_quoc", "bac", "nam", "trung")}

    hd = {r["id"]: {"cc": r["cc"], "tu": r["tu"], "den": r["den"], "gia_tri": float(r["gia_tri"] or 0),
                    "lech": int(float(r["so_dong_lech"] or 0)) > 0} for r in csv_rows("hop_dong") if r["tu"] and r["den"]}
    hdd = defaultdict(list)
    for r in csv_rows("hop_dong_hoa_don"):
        hdd[r["id"]].append((_as_date(r["d"]), float(r["rev"] or 0)))
    ket_qua["hop_dong_ETC"] = phan_tich_hop_dong(hd, hdd, data_end)

    snaps = doc_cong_no()
    if snaps:
        ket_qua["no_sap_45"] = phan_tich_no_sap_45(snaps)

    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "ket_qua.json"), "w", encoding="utf-8") as f:
        json.dump(ket_qua, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(ket_qua, ensure_ascii=False, indent=1, default=str))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lenh", choices=["keo-cong-no", "keo-du-lieu", "phan-tich"])
    ap.add_argument("--tu", default="2025-09-01")
    ap.add_argument("--den", default="2026-09-14")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if args.lenh == "keo-cong-no":
        keo_cong_no(mondays(args.tu, args.den), force=args.force)
    elif args.lenh == "keo-du-lieu":
        keo_du_lieu(force=args.force)
    else:
        phan_tich()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
