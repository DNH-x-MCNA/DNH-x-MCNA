# -*- coding: utf-8 -*-
"""
Cac truy van BAO CAO CHUAN - doc tu KHO LOCAL (SQLite, warehouse.db), duoc dong bo dinh ky tu Bravo
qua sync_warehouse.py (xem file do). Doc local giup tra loi nhanh (<=10s) va co du lich su nhieu nam
de so sanh, thay vi phai goi Bravo qua VPN cho moi cau hoi (cham + phu thuoc VPN on dinh).

Du lieu co the tre toi da ~15-30 phut (chu ky dong bo) so voi Bravo that - chap nhan duoc cho hầu het
cau hoi phan tich/bao cao. Neu can so lieu "ngay tuc thi", noi ro voi nguoi dung day la so lieu tai
lan dong bo gan nhat.
"""
import datetime as dt
from sqlalchemy import text
from local_warehouse import get_conn
from query_engine import _write_log, _get_engine


def _q(sql, params=()):
    conn = get_conn()
    try:
        conn.row_factory = None
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _f(v):
    return float(v) if v is not None else 0.0


def latest_data_date() -> str:
    """Ngay gan nhat CO DU LIEU trong kho local (Bravo co the tre vai ngay, va kho local co the
    tre them toi da 1 chu ky dong bo nua so voi Bravo)."""
    r = _q("SELECT MAX(doc_date) d FROM vhoadon_otc")
    d = r[0]["d"] if r else None
    return d if d else str(dt.date.today())


def revenue_by_channel(date_from: str, date_to: str) -> dict:
    """Doanh thu + so hoa don theo kenh OTC/ETC trong khoang [date_from, date_to]."""
    o = _q("SELECT COALESCE(SUM(amount9),0) rev, COUNT(DISTINCT stt) hd FROM vhoadon_otc "
           "WHERE doc_date BETWEEN ? AND ?", (date_from, date_to))[0]
    e = _q("SELECT COALESCE(SUM(amount9),0) rev, COUNT(DISTINCT stt) hd FROM vhoadon_etc "
           "WHERE doc_date BETWEEN ? AND ?", (date_from, date_to))[0]
    otc_rev, otc_hd = _f(o["rev"]), int(o["hd"])
    etc_rev, etc_hd = _f(e["rev"]), int(e["hd"])
    return {
        "date_from": date_from, "date_to": date_to,
        "otc": {"revenue": otc_rev, "invoices": otc_hd},
        "etc": {"revenue": etc_rev, "invoices": etc_hd},
        "total": {"revenue": otc_rev + etc_rev, "invoices": otc_hd + etc_hd},
        "data_as_of": latest_data_date(),
    }


def top_products(date_from: str, date_to: str, limit: int = 10, channel: str = "ALL") -> list:
    """Top N san pham theo doanh thu. Loai hang khuyen mai (unit_price=0) khoi so luong ban that."""
    parts = []
    if channel in ("OTC", "ALL"):
        parts.append("SELECT item_code, amount9, quantity, unit_price FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ?")
    if channel in ("ETC", "ALL"):
        parts.append("SELECT item_code, amount9, quantity, unit_price FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ?")
    n_ranges = len(parts)
    sql = f"""WITH combined AS ({" UNION ALL ".join(parts)})
              SELECT c.item_code, sp.name,
                     SUM(c.amount9) rev,
                     SUM(CASE WHEN COALESCE(c.unit_price,0) > 0 THEN c.quantity ELSE 0 END) qty
              FROM combined c LEFT JOIN brv_sanpham sp ON sp.code = c.item_code
              GROUP BY c.item_code, sp.name ORDER BY rev DESC LIMIT ?"""
    params = (date_from, date_to) * n_ranges + (limit,)
    rows = _q(sql, params)
    return [{"item_code": r["item_code"], "name": r["name"] or f'(chua co ten - ma {r["item_code"]})',
             "revenue": _f(r["rev"]), "qty": _f(r["qty"])} for r in rows]


def top_customers(date_from: str, date_to: str, limit: int = 10, channel: str = "ALL") -> list:
    """Top N khach hang theo doanh thu."""
    parts = []
    if channel in ("OTC", "ALL"):
        parts.append("SELECT customer_code, amount9 FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ?")
    if channel in ("ETC", "ALL"):
        parts.append("SELECT customer_code, amount9 FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ?")
    n_ranges = len(parts)
    sql = f"""WITH combined AS ({" UNION ALL ".join(parts)})
              SELECT customer_code, SUM(amount9) rev
              FROM combined GROUP BY customer_code ORDER BY rev DESC LIMIT ?"""
    params = (date_from, date_to) * n_ranges + (limit,)
    rows = _q(sql, params)
    return [{"customer_code": r["customer_code"], "revenue": _f(r["rev"])} for r in rows]


def revenue_by_region(date_from: str, date_to: str) -> list:
    """Doanh thu theo vung mien (MB/MT/MN), gop ca OTC + ETC. CA HAI deu LEFT JOIN qua bang khach hang
    de lay city_id (da doi chieu voi DA ben Bravo va xac nhan day la cach dung - KHONG dung city_id ghi
    truc tiep tren vhoadon_otc vi truong nay khong dang tin, tung gay lech doanh thu theo vung).
    BAT BUOC LEFT JOIN (khong duoc INNER JOIN) - khach "mo coi" khong co trong bang khach hang (vd
    HCM13508 - co that, ~2.3 ty doanh thu 2022-2025, KHONG co trong dms_khachhang) se bi INNER JOIN
    am tham loai bo ca khoi tong lan breakdown. Voi LEFT JOIN, khach mo coi roi vao bucket
    "Khac/chua xac dinh" thay vi bien mat - xem TODO doi len suy luan qua tien to ma KH (src/region_map.py,
    chua tich hop) truoc khi chap nhan la "Khac/chua xac dinh"."""
    rows = _q("""
        SELECT tp.area_code area, SUM(o.amount9) rev
        FROM vhoadon_otc o LEFT JOIN dms_khachhang kh ON kh.code=o.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE o.doc_date BETWEEN ? AND ? GROUP BY tp.area_code
        UNION ALL
        SELECT tp.area_code area, SUM(e.amount9) rev
        FROM vhoadon_etc e LEFT JOIN dmssx_khachhang kh ON kh.code=e.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE e.doc_date BETWEEN ? AND ? GROUP BY tp.area_code
        """, (date_from, date_to, date_from, date_to))
    agg = {}
    for r in rows:
        area = r["area"] or "Khac/chua xac dinh"
        agg[area] = agg.get(area, 0.0) + _f(r["rev"])
    total = sum(agg.values())

    # Tu doi chieu (re # 4): tong cong theo vung PHAI bang dung tong khong loc vung cung ky - neu
    # lech tuc la co JOIN nao do dang am tham lam roi du lieu (vd bi doi lai thanh INNER JOIN).
    raw_total = _f(_q("SELECT COALESCE(SUM(amount9),0) t FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ?",
                       (date_from, date_to))[0]["t"]) + \
                _f(_q("SELECT COALESCE(SUM(amount9),0) t FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ?",
                       (date_from, date_to))[0]["t"])
    if abs(total - raw_total) > 1:
        _write_log({"ts": dt.datetime.now().isoformat(), "status": "warn",
                    "sql": "<revenue_by_region reconciliation check>",
                    "error": f"Tong theo vung ({total}) LECH voi tong khong loc vung ({raw_total}) - "
                             f"co JOIN dang lam roi du lieu, kiem tra lai ngay."})
    return [{"area": k, "revenue": v, "share_pct": (v / total * 100 if total else 0.0)}
            for k, v in sorted(agg.items(), key=lambda x: -x[1])]


KPI_ACHIEVED_THRESHOLD = 80  # % dat KPI nhan vien tinh la "dat" (theo yeu cau nghiep vu, KHONG phai 100%)
KPI_WARN_THRESHOLD = 50      # duoi nguong nay coi la "nguy hiem" (do), giua 2 nguong la "trung binh" (vang)


def _kpi_status(pct: float) -> str:
    """Phan loai mau theo % dat KPI: >=80 Tot (xanh), 50-79 Trung binh (vang), <50 Nguy hiem (do)."""
    if pct >= KPI_ACHIEVED_THRESHOLD:
        return "🟢 Tốt"
    if pct >= KPI_WARN_THRESHOLD:
        return "🟡 Trung bình"
    return "🔴 Nguy hiểm"


def employee_kpi(as_of_date: str, limit: int = 10, order_by: str = "sales", filter: str = "all",
                  position_code: str = None) -> dict:
    """KPI nhan vien: snapshot fact_tonghopkhachhang gan nhat <= as_of_date.
    order_by: 'sales' hoac 'pct' (dung khi filter='all', luon xep TOT NHAT truoc).
    filter: 'all' (top N tot nhat), 'below_target' (CHUA dat KPI, pct<80, xep TE NHAT truoc),
            'above_target' (DA dat KPI, pct>=80, xep TOT NHAT truoc).
    position_code: loc theo vai tro (vd 'TDV','QLV') - LUON dung tham so nay khi cau hoi chi dinh ro
    vai tro (vd "top TDV"), KHONG tu loc thu cong tu ket qua day du vi de sot/thieu chinh xac.
    NGUONG DAT KPI la 80% (khong phai 100%). Moi dong co san "status" (🟢 Tot/🟡 Trung binh/🔴 Nguy hiem)
    - LUON dung nguyen gia tri nay khi tra loi, khong tu tinh nguong khac."""
    fdate_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?", (as_of_date,))
    fdate = fdate_r[0]["d"] if fdate_r else None
    if fdate is None:
        return {"as_of": None, "total_employees": 0, "count_below_target": 0, "count_above_target": 0, "rows": []}
    sql = """SELECT nv.name name, e.employee_code employee_code,
                    nv.position_code position_code, cv.description position_label,
                    SUM(e.amount_ct) sales, MAX(e.month_sale_target) target,
                    SUM(e.is_nc) new_customers
             FROM fact_tonghopkhachhang e
             LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code
             LEFT JOIN dim_chucvu cv ON cv.position_code=nv.position_code
             WHERE e.save_date=? AND COALESCE(nv.is_duplicate,0)<>1"""
    params = [fdate]
    if position_code:
        sql += " AND nv.position_code=?"
        params.append(position_code)
    sql += """ GROUP BY nv.name, e.employee_code, nv.position_code, cv.description
               HAVING MAX(e.month_sale_target)>0"""
    rows = _q(sql, tuple(params))
    for r in rows:
        r["sales"] = _f(r["sales"]); r["target"] = _f(r["target"])
        r["pct"] = (r["sales"] / r["target"] * 100) if r["target"] else 0.0
        r["new_customers"] = int(r["new_customers"] or 0)
        r["status"] = _kpi_status(r["pct"])
    below = [r for r in rows if r["pct"] < KPI_ACHIEVED_THRESHOLD]
    above = [r for r in rows if r["pct"] >= KPI_ACHIEVED_THRESHOLD]
    if filter == "below_target":
        selected = sorted(below, key=lambda r: r["pct"])[:limit]
    elif filter == "above_target":
        selected = sorted(above, key=lambda r: -r["pct"])[:limit]
    else:
        key = "sales" if order_by == "sales" else "pct"
        selected = sorted(rows, key=lambda r: -r[key])[:limit]
    return {"as_of": fdate, "total_employees": len(rows), "count_below_target": len(below),
            "count_above_target": len(above), "rows": selected}


DAILY_KPI_TARGET_PCT = 4.0  # 4% MonthSaleTarget = "100%" cua 1 ngay lam viec (yeu cau nghiep vu)
DAILY_KPI_RED = 2.5          # duoi nguong nay: do
DAILY_KPI_YELLOW_MAX = 3.5   # 2.5% - 3.5%: vang; tren 3.5%: xanh


def _daily_kpi_status(pct: float) -> str:
    if pct < DAILY_KPI_RED:
        return "🔴 Đỏ"
    if pct <= DAILY_KPI_YELLOW_MAX:
        return "🟡 Vàng"
    return "🟢 Xanh"


def employee_daily_kpi(employee_code: str, year_month: str) -> dict:
    """KPI THEO NGAY cho 1 nhan vien CA NHAN (co ma truc tiep tren hoa don, vd EmpDMSCode2 nhu
    'tungtx') trong 1 thang (YYYY-MM). Target 1 ngay = 4% MonthSaleTarget cua nhan vien (tuong duong
    100% cua ngay). Phan loai tung ngay: 🔴 Do (<2.5%), 🟡 Vang (2.5%-3.5%), 🟢 Xanh (>3.5%). CHI tinh
    T2-T6 (bo qua T7/CN). Rieng "month_pct_of_target" la % TONG thang (thuc te/target*100, cach tinh
    CU khong lien quan 4%/ngay, KHONG co mau/nguong - chi la con so tham khao cuoi thang.
    KHONG dung cho ma khu vuc/quan ly vung (MBKV*, ASM*...) - cac ma nay khong xuat hien tren hoa don,
    dung get_employee_kpi (snapshot thang, nguong 80%/50%) thay the cho nhom do."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    month_start = dt.date(year, month, 1)
    month_end = (dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)) - dt.timedelta(days=1)
    today = dt.date.today()
    range_end = min(month_end, today)
    target_asof = min(month_end, today)

    r = _q("SELECT MAX(month_sale_target) t, MAX(save_date) d FROM fact_tonghopkhachhang "
           "WHERE employee_code=? AND save_date<=?", (employee_code, str(target_asof)))
    target = _f(r[0]["t"]) if r else 0.0
    target_as_of = r[0]["d"] if r else None

    days = []
    total_sales_month = 0.0
    count_red = count_yellow = count_green = 0
    if range_end >= month_start:
        rows = _q("""SELECT doc_date, SUM(amount9) rev FROM (
                        SELECT doc_date, amount9 FROM vhoadon_otc WHERE employee_code=? AND doc_date BETWEEN ? AND ?
                        UNION ALL
                        SELECT doc_date, amount9 FROM vhoadon_etc WHERE employee_code=? AND doc_date BETWEEN ? AND ?
                     ) GROUP BY doc_date""",
                  (employee_code, str(month_start), str(range_end), employee_code, str(month_start), str(range_end)))
        by_date = {r["doc_date"]: _f(r["rev"]) for r in rows}
        total_sales_month = sum(by_date.values())
        d = month_start
        while d <= range_end:
            if d.weekday() < 5:  # 0=T2..4=T6, bo qua 5=T7,6=CN
                rev = by_date.get(str(d), 0.0)
                pct = (rev / target * 100) if target else 0.0
                status = _daily_kpi_status(pct)
                days.append({"date": str(d), "revenue": rev, "pct_of_target": pct, "status": status})
                if status.startswith("🔴"): count_red += 1
                elif status.startswith("🟡"): count_yellow += 1
                else: count_green += 1
            d += dt.timedelta(days=1)

    month_pct = (total_sales_month / target * 100) if target else 0.0
    return {
        "employee_code": employee_code, "year_month": year_month,
        "month_sale_target": target, "target_as_of": target_as_of,
        "daily_target_pct": DAILY_KPI_TARGET_PCT,
        "days": days,
        "count_red": count_red, "count_yellow": count_yellow, "count_green": count_green,
        "month_total_sales": total_sales_month, "month_pct_of_target": month_pct,
        "data_as_of": latest_data_date(),
    }


def employee_directory(search: str = None, position_code: str = None, area_code: str = None, limit: int = 30) -> list:
    """Tra cuu MAPPING ma nhan vien <-> ten <-> vai tro (TDV/QLV/CTV/CS/TP/PP/TBP/TK). Dung khi nguoi
    dung hoi "ma cua [ten]" / "[ten] la ai" / "danh sach TDV vung MB" - KHONG can biet ma truoc.
    search: tim gan dung theo TEN hoac MA (khong phan biet hoa/thuong). position_code: loc theo vai tro
    (vd 'TDV','QLV'). area_code: loc theo vung (MB/MT/MN). LUON loc is_duplicate<>1."""
    sql = """SELECT n.employee_code employee_code, n.name name,
                    n.position_code position_code, c.description position_label, n.area_code area_code
             FROM dim_nhanvien n LEFT JOIN dim_chucvu c ON c.position_code=n.position_code
             WHERE COALESCE(n.is_duplicate,0)<>1"""
    params = []
    if search:
        sql += " AND (n.name LIKE ? OR n.employee_code LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if position_code:
        sql += " AND n.position_code=?"
        params.append(position_code)
    if area_code:
        sql += " AND n.area_code=?"
        params.append(area_code)
    sql += " ORDER BY n.name LIMIT ?"
    params.append(limit)
    return _q(sql, tuple(params))


def compare_periods(date_from_a: str, date_to_a: str, date_from_b: str, date_to_b: str) -> dict:
    """So sanh nhanh doanh thu giua 2 khoang thoi gian (vd thang nay vs thang truoc, cung ky nam truoc).
    Vi kho local co day du lich su (nhieu nam) nen so sanh xa duoc, khong chi vai ngay gan day."""
    a = revenue_by_channel(date_from_a, date_to_a)
    b = revenue_by_channel(date_from_b, date_to_b)
    delta = a["total"]["revenue"] - b["total"]["revenue"]
    pct_change = (delta / b["total"]["revenue"] * 100) if b["total"]["revenue"] else None
    return {"period_a": a, "period_b": b, "delta": delta, "pct_change": pct_change}


def _customer_receivable(customer_code: str, channel: str) -> dict:
    """Tra du no/qua han tu Supabase (khong co tren Bravo). channel co the la 'OTC','ETC','OTC+ETC'
    - neu ca 2 kenh, uu tien receivable_detail (OTC) truoc vi pho bien hon."""
    empty = {"balance_end": None, "total_overdue": None, "overdue_pct": None}
    try:
        eng = _get_engine("supabase")
        with eng.connect() as conn:
            if "OTC" in channel:
                periods = conn.execute(text('SELECT DISTINCT "period" FROM receivable_detail WHERE "customer_code"=:c'),
                                        {"c": customer_code}).fetchall()
                if periods:
                    def _period_key(p):
                        m, y = p.split("_")
                        return (int(y), int(m))
                    latest = max((p[0] for p in periods), key=_period_key)
                    r = conn.execute(text('SELECT "balance_end", "total_overdue" FROM receivable_detail '
                                           'WHERE "customer_code"=:c AND "period"=:p'),
                                      {"c": customer_code, "p": latest}).fetchone()
                    if r:
                        balance, overdue = float(r[0] or 0), float(r[1] or 0)
                        return {"balance_end": balance, "total_overdue": overdue,
                                "overdue_pct": (overdue / balance * 100) if balance else 0.0}
            if "ETC" in channel:
                r = conn.execute(text('SELECT "total_receivable", "total_overdue" FROM receivable_etc '
                                       'WHERE "customer_code"=:c'), {"c": customer_code}).fetchone()
                if r:
                    balance, overdue = float(r[0] or 0), float(r[1] or 0)
                    return {"balance_end": balance, "total_overdue": overdue,
                            "overdue_pct": (overdue / balance * 100) if balance else 0.0}
    except Exception:
        pass
    return empty


def customer_detail(customer_code: str, date_from: str, date_to: str) -> dict:
    """Chi tiet 1 khach hang: gop doanh thu thuc te (kho local, tu Bravo) + du no/qua han (Supabase) +
    mapping vung mien/NV phu trach (DMS_KhachHang + DIM_NhanVien). Doanh thu tinh trong [date_from,date_to],
    du no/qua han la SNAPSHOT KY GAN NHAT hien co (khong theo date_from/date_to).
    LUU Y: kenh ETC KHONG co NV phu trach truc tiep gan tren khach hang (chi OTC co qua EmpDMSCode1) -
    cot employee_code/employee_name/position_label se rong voi khach hang thuan ETC."""
    o = _q("SELECT COALESCE(SUM(amount9),0) rev, COUNT(DISTINCT stt) hd FROM vhoadon_otc "
           "WHERE customer_code=? AND doc_date BETWEEN ? AND ?", (customer_code, date_from, date_to))[0]
    e = _q("SELECT COALESCE(SUM(amount9),0) rev, COUNT(DISTINCT stt) hd FROM vhoadon_etc "
           "WHERE customer_code=? AND doc_date BETWEEN ? AND ?", (customer_code, date_from, date_to))[0]
    otc_rev, otc_hd = _f(o["rev"]), int(o["hd"])
    etc_rev, etc_hd = _f(e["rev"]), int(e["hd"])

    if otc_hd and etc_hd:
        channel = "OTC+ETC"
    elif otc_hd:
        channel = "OTC"
    elif etc_hd:
        channel = "ETC"
    else:
        channel = None

    revenue = otc_rev + etc_rev
    orders = otc_hd + etc_hd
    avg_order_value = (revenue / orders) if orders else 0.0

    dms = _q("SELECT name, city_id, id_code, emp_code, kenh_bh FROM dms_khachhang WHERE code=? LIMIT 1", (customer_code,))
    lookup_src = "OTC"
    if not dms:
        d2 = _q("SELECT name, city_id, id_code, kenh_bh FROM dmssx_khachhang WHERE code=? LIMIT 1", (customer_code,))
        if d2:
            dms = [{**d2[0], "emp_code": None}]
            lookup_src = "ETC"

    name = city_name = area_code = emp_code = emp_name = position_code = position_label = id_code = kenh_bh = None
    if dms:
        d = dms[0]
        name = d["name"]; id_code = d["id_code"]; emp_code = d.get("emp_code"); kenh_bh = d["kenh_bh"]
        city = _q("SELECT city_name, area_code FROM dim_tinhthanhpho WHERE city_id=?", (d["city_id"],))
        if city:
            city_name = city[0]["city_name"]; area_code = city[0]["area_code"]
        if emp_code:
            nv = _q("SELECT name, position_code FROM dim_nhanvien WHERE employee_code=? AND COALESCE(is_duplicate,0)<>1",
                    (emp_code,))
            if nv:
                emp_name = nv[0]["name"]; position_code = nv[0]["position_code"]
                cv = _q("SELECT description FROM dim_chucvu WHERE position_code=? LIMIT 1", (position_code,))
                position_label = cv[0]["description"] if cv else position_code

    receivable = _customer_receivable(customer_code, channel or lookup_src)

    return {
        "customer_code": customer_code, "customer_name": name, "channel": channel,
        "kenh_bh": kenh_bh, "province": city_name, "area_code": area_code,
        "employee_code": emp_code, "employee_name": emp_name,
        "position_code": position_code, "position_label": position_label,
        "id_code": id_code,
        "date_from": date_from, "date_to": date_to,
        "revenue": revenue, "orders": orders, "avg_order_value": avg_order_value,
        **receivable,
        "data_as_of": latest_data_date(),
    }


def order_timing_check(date_from: str, date_to: str, threshold_days: int = 2, limit: int = 20) -> dict:
    """Phat hien dau hieu 'chay don don KPI': hoa don co created_at (thoi diem BAN GHI THUC SU duoc
    tao trong Bravo) lech qua xa so voi doc_date (ngay chung tu tren hoa don, co the bi chon tay).
    Vd: doc_date la cuoi thang truoc nhung created_at lai la dau thang sau -> dau hieu tao/sua don
    backdate de kip chi tieu KPI thang truoc. threshold_days: so ngay lech toi thieu de bi liet ke
    (mac dinh 2). Tra ve ca TOM TAT theo tung nhan vien (ai co nhieu don bat thuong nhat) LAN danh
    sach chi tiet top nhung don lech nhieu nhat."""
    sql = """
        SELECT doc_date, created_at, customer_code, employee_code, amount9, stt,
               CAST(julianday(created_at) - julianday(doc_date) AS INTEGER) AS lech_ngay
        FROM (
            SELECT doc_date, created_at, customer_code, employee_code, amount9, stt
            FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ? AND created_at IS NOT NULL
            UNION ALL
            SELECT doc_date, created_at, customer_code, employee_code, amount9, stt
            FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ? AND created_at IS NOT NULL
        )
        WHERE ABS(CAST(julianday(created_at) - julianday(doc_date) AS INTEGER)) >= ?
        ORDER BY ABS(lech_ngay) DESC
    """
    rows = _q(sql, (date_from, date_to, date_from, date_to, threshold_days))

    for r in rows:
        r["amount9"] = _f(r["amount9"])
        # Bao cao chong gian lan: LAY TEN DU is_duplicate=1 (khac cac tool khac) - muc dich la minh
        # bach danh tinh, khong nen an ten chi vi 1 co du lieu khong lien quan.
        nv = _q("SELECT name, position_code FROM dim_nhanvien WHERE employee_code=? LIMIT 1",
                (r["employee_code"],)) if r["employee_code"] else []
        r["employee_name"] = nv[0]["name"] if nv else None
        r["position_code"] = nv[0]["position_code"] if nv else None

    by_employee = {}
    for r in rows:
        key = r["employee_code"] or "(khong xac dinh)"
        if key not in by_employee:
            by_employee[key] = {"employee_code": key, "employee_name": r["employee_name"],
                                 "position_code": r["position_code"], "count": 0, "total_amount": 0.0}
        by_employee[key]["count"] += 1
        by_employee[key]["total_amount"] += r["amount9"]
    summary = sorted(by_employee.values(), key=lambda x: -x["count"])

    return {
        "date_from": date_from, "date_to": date_to, "threshold_days": threshold_days,
        "total_flagged": len(rows),
        "summary_by_employee": summary,
        "top_detail": rows[:limit],
        "data_as_of": latest_data_date(),
    }


TEMPLATES = {
    "get_revenue_by_channel": revenue_by_channel,
    "get_top_products": top_products,
    "get_top_customers": top_customers,
    "get_revenue_by_region": revenue_by_region,
    "get_employee_kpi": employee_kpi,
    "get_employee_daily_kpi": employee_daily_kpi,
    "compare_periods": compare_periods,
    "get_customer_detail": customer_detail,
    "get_employee_directory": employee_directory,
    "check_order_timing": order_timing_check,
}


def call_template(name: str, args: dict, question: str = "", username: str = None) -> dict:
    """Goi 1 template theo ten, ghi audit log (giong format run_query de nhat quan truy vet)."""
    t0 = dt.datetime.now()
    entry = {"ts": t0.isoformat(), "username": username, "question": question, "sql": f"<template:{name}>({args})"}
    try:
        fn = TEMPLATES[name]
        result = fn(**args)
        entry["status"] = "ok"
        entry["duration_ms"] = int((dt.datetime.now() - t0).total_seconds() * 1000)
        _write_log(entry)
        return {"ok": True, "result": result}
    except Exception as e:
        entry["status"] = "error"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": f"Loi khi chay bao cao chuan '{name}': {str(e)[:300]}"}
