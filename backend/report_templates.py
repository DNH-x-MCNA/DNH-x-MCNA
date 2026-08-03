# -*- coding: utf-8 -*-
"""
Cac truy van BAO CAO CHUAN - doc tu KHO LOCAL (SQLite, warehouse.db), duoc dong bo dinh ky tu Bravo
qua sync_warehouse.py (xem file do). Doc local giup tra loi nhanh (<=10s) va co du lich su nhieu nam
de so sanh, thay vi phai goi Bravo qua VPN cho moi cau hoi (cham + phu thuoc VPN on dinh).

Du lieu co the tre toi da ~15-30 phut (chu ky dong bo) so voi Bravo that - chap nhan duoc cho hầu het
cau hoi phan tich/bao cao. Neu can so lieu "ngay tuc thi", noi ro voi nguoi dung day la so lieu tai
lan dong bo gan nhat.
"""
import contextvars
import datetime as dt
import os
import sqlite3
from sqlalchemy import text
from local_warehouse import get_conn, get_sync_meta
from query_engine import _write_log, _get_engine
from region_map import region_from_customer_code, REGION_SQL_MARKERS, REGION_NAMES_VI
import org_hierarchy as oh
from pricing import USD_TO_VND_RATE

_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
AUDIT_LOG_PATH = os.path.join(_LOGS_DIR, "audit_log.jsonl")
COST_LOG_PATH = os.path.join(_LOGS_DIR, "cost_log.jsonl")


# 22/07/2026 (diem #5 gop y): kenh CANH BAO tu tool len cau tra loi. Truoc day cac phep tu-doi-chieu
# ben trong tool (vd revenue_by_region so tong theo vung vs tong tho) khi phat hien lech CHI ghi log -
# nguoi dung van nhan breakdown SAI ma khong biet. Dung contextvars (KHONG dung bien module thuong)
# vi backend phuc vu nhieu request dong thoi: bien module se ro ri canh bao cua request nay sang
# request khac. call_template() reset dau moi lan goi va gom lai o cuoi (xem cuoi file).
_tool_warnings = contextvars.ContextVar("tool_warnings", default=None)


def _warn(msg: str):
    """Ghi 1 canh bao de dinh kem vao ket qua tra ve cho AI (AI co trach nhiem noi lai voi nguoi dung).
    An toan khi goi ngoai pham vi call_template (bo qua, khong loi)."""
    bucket = _tool_warnings.get()
    if bucket is not None:
        bucket.append(msg)


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


def _scope_clause(scope_area_code: str):
    """Tra ve (sql_suffix, params) de them dieu kien loc vung khi user bi gioi han (QLV/GD mien).
    Gia dinh query da JOIN toi dim_tinhthanhpho voi alias 'tp' khi scope_area_code duoc truyen."""
    if scope_area_code:
        return " AND tp.area_code=?", (scope_area_code,)
    return "", ()


def _otc_area_join(alias: str = "v", scope_area_code: str = None) -> str:
    if not scope_area_code:
        return ""
    return f"LEFT JOIN dms_khachhang kh ON kh.code={alias}.customer_code LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id"


def _etc_area_join(alias: str = "v", scope_area_code: str = None) -> str:
    if not scope_area_code:
        return ""
    return f"LEFT JOIN dmssx_khachhang kh ON kh.code={alias}.customer_code LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id"


def latest_data_date() -> str:
    """Ngay gan nhat CO DU LIEU trong kho local (Bravo co the tre vai ngay, va kho local co the
    tre them toi da 1 chu ky dong bo nua so voi Bravo)."""
    r = _q("SELECT MAX(doc_date) d FROM vhoadon_otc")
    d = r[0]["d"] if r else None
    return d if d else str(dt.date.today())


def sync_freshness_note(stale_minutes: int = 60) -> str:
    """20/07/2026: kiem tra sync CO DANG SONG khong - khac latest_data_date() (chi biet NGAY du lieu
    moi nhat, khong biet tien trinh sync co dung/treo hay khong: cuoi tuan/le khong co hoa don moi
    van trong "binh thuong" du sync da treo vai ngay - nguoi dung se duoc tra loi tu tin bang du lieu
    cu/thieu ma khong ai biet). Doc sync_meta.last_synced_at (moc THOI GIAN THAT sync chay xong lan
    cuoi, ghi boi set_sync_meta() trong sync_warehouse.py - KHAC voi ngay cua ban than du lieu) cho
    2 bang giao dich quan trong nhat. Tra ve chuoi CANH BAO neu qua han (mac dinh >60 phut - gap doi
    chu ky binh thuong 15-30 phut da ghi trong docstring dau file), rong neu van tuoi/khong xac dinh
    duoc (KHONG chan cau tra loi, chi bo sung canh bao)."""
    warnings = []
    for table in ("vhoadon_otc", "vhoadon_etc"):
        try:
            last_synced_at, _, _ = get_sync_meta(table)
        except Exception:
            # Bang sync_meta moi them 20/07/2026 - se tu tao o lan sync ke tiep (init_schema() trong
            # sync_warehouse.py). Truoc do "no such table" la binh thuong, khong duoc lam vo cau tra loi.
            continue
        if not last_synced_at:
            continue
        try:
            last_dt = dt.datetime.fromisoformat(last_synced_at)
        except ValueError:
            continue
        age_min = (dt.datetime.now() - last_dt).total_seconds() / 60
        if age_min > stale_minutes:
            warnings.append(f"{table}: lần đồng bộ gần nhất cách đây {age_min:.0f} phút ({last_synced_at})")
    if not warnings:
        return ""
    return ("CẢNH BÁO ĐỒNG BỘ: có thể tiến trình sync đã TREO/LỖI — " + "; ".join(warnings) +
            " (chu kỳ bình thường 15-30 phút). PHẢI cảnh báo rõ người dùng trong câu trả lời rằng "
            "dữ liệu có thể CŨ HƠN BÌNH THƯỜNG, không chỉ nói ngày dữ liệu như bình thường.")


# Hoa don CU HON 12 THANG duoc nen thanh KH x thang trong monthly_customer_summary (khong con
# item_code/quantity/unit_price/created_at/stt tung dong) - xem sync_warehouse.py::DETAIL_WINDOW_MONTHS/
# _detail_cutoff_date(). Cac ham chi can TONG doanh thu/so hoa don (revenue_by_channel, top_customers,
# revenue_by_region, compare_periods qua revenue_by_channel) UNION them nguon nen nay khi khoang ngay
# duoc hoi vuot qua 12 thang gan nhat, de van ra dung so cho ca giai doan xa (vd "so voi cung ky nam
# ngoai"). Cac ham can CHI TIET tung dong (top_products: item_code; check_order_timing: created_at)
# KHONG the bu duoc bang nguon nen - xem canh bao rieng trong 2 ham do.
def _detail_cutoff() -> str:
    today = dt.date.today()
    y, m = today.year, today.month - 12
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}-01"


def _monthly_summary_scope_clause(scope_area_code: str, channel: str):
    """Tuong duong _scope_clause() nhung cho monthly_customer_summary - bang nay KHONG co san city_id
    nen phai join qua dms_khachhang (OTC) / dmssx_khachhang (ETC) qua customer_code de suy ra vung,
    giong het cach lam voi vhoadon_otc/etc chi tiet (xem _otc_area_join/_etc_area_join)."""
    if not scope_area_code:
        return "", ()
    kh_table = "dms_khachhang" if channel == "OTC" else "dmssx_khachhang"
    return (f" AND EXISTS (SELECT 1 FROM {kh_table} kh JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
            f"WHERE kh.code=m.customer_code AND tp.area_code=?)", (scope_area_code,))


def _get_team_dms_ids(scope_employee_code: str) -> list:
    """Tra ve danh sach DMSId cua tat ca TDV thuoc quyen quan ly cua 1 QLV."""
    from org_hierarchy import qlv_zones
    zones = qlv_zones(scope_employee_code)
    if not zones:
        return []
    placeholders = ",".join(["?"] * len(zones))
    # name NOT LIKE '%(QLV)%' de loai ban ghi bong, lay dung TDV ban hang
    rows = _q(f"SELECT dmsid FROM dim_nhanvien WHERE manager_area_code IN ({placeholders}) "
              f"AND end_date IS NULL AND COALESCE(is_resigned,0)<>1 AND name NOT LIKE '%(QLV)%'", tuple(zones))
    return [r["dmsid"] for r in rows if r.get("dmsid")]

def _employee_scope_clause(scope_employee_code: str, alias: str) -> tuple:
    if not scope_employee_code:
        return "", ()
    dms_ids = _get_team_dms_ids(scope_employee_code)
    if not dms_ids:
        return " AND 1=0", ()
    placeholders = ",".join(["?"] * len(dms_ids))
    return f" AND {alias}.employee_code IN ({placeholders})", tuple(dms_ids)


def revenue_by_channel(date_from: str, date_to: str, scope_area_code: str = None,
                        scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """Doanh thu + so hoa don theo kenh OTC/ETC trong khoang [date_from, date_to].
    scope_area_code: NEU duoc truyen (tai khoan QLV/GD mien bi gioi han vung), CHI tinh doanh thu
    cua dung vung do (join qua bang khach hang) - do la co che ep buoc o tang code, khong phu thuoc
    AI co tu loc dung hay khong.
    scope_channel: NEU duoc truyen (vd 'OTC'), KHONG truy van kenh con lai - tra ve 0 cho kenh do,
    kem co "channel_scope" bao hieu day la du lieu bi gioi han kenh (khac scope_area_code, co che
    nay doc lap va ap dung duoc cho moi role)."""
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v")
    scope_sql += emp_sql
    scope_params += emp_params
    join_o = _otc_area_join("v", scope_area_code)
    o = _q(f"SELECT COALESCE(SUM(v.amount9),0) rev, COUNT(DISTINCT v.stt) hd FROM vhoadon_otc v {join_o} "
           f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}", (date_from, date_to) + scope_params)[0]
    otc_rev, otc_hd = _f(o["rev"]), int(o["hd"])
    if scope_channel == "OTC":
        etc_rev, etc_hd = 0.0, 0
    else:
        join_e = _etc_area_join("v", scope_area_code)
        e = _q(f"SELECT COALESCE(SUM(v.amount9),0) rev, COUNT(DISTINCT v.stt) hd FROM vhoadon_etc v {join_e} "
               f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}", (date_from, date_to) + scope_params)[0]
        etc_rev, etc_hd = _f(e["rev"]), int(e["hd"])

    # date_from truoc cua so 12 thang chi tiet -> phan xa hon da bi nen, cong them tu
    # monthly_customer_summary (vhoadon_otc/etc chi con giu 12 thang gan nhat, xem sync_warehouse.py).
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        summary_to = min(date_to, cutoff)
        ym_from, ym_to = date_from[:7], summary_to[:7]
        msc_o, msc_o_params = _monthly_summary_scope_clause(scope_area_code, "OTC")
        msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m")
        msc_o += msc_emp_sql
        msc_o_params += msc_emp_params
        so = _q(f"SELECT COALESCE(SUM(m.revenue),0) rev, COALESCE(SUM(m.invoice_count),0) hd "
                f"FROM monthly_customer_summary m WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ?{msc_o}",
                (ym_from, ym_to) + msc_o_params)[0]
        otc_rev += _f(so["rev"]); otc_hd += int(so["hd"] or 0)
        if scope_channel != "OTC":
            msc_e, msc_e_params = _monthly_summary_scope_clause(scope_area_code, "ETC")
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m")
            msc_e += msc_emp_sql
            msc_e_params += msc_emp_params
            se = _q(f"SELECT COALESCE(SUM(m.revenue),0) rev, COALESCE(SUM(m.invoice_count),0) hd "
                    f"FROM monthly_customer_summary m WHERE m.channel='ETC' AND m.year_month BETWEEN ? AND ?{msc_e}",
                    (ym_from, ym_to) + msc_e_params)[0]
            etc_rev += _f(se["rev"]); etc_hd += int(se["hd"] or 0)

    result = {
        "date_from": date_from, "date_to": date_to,
        "otc": {"revenue": otc_rev, "invoices": otc_hd},
        "etc": {"revenue": etc_rev, "invoices": etc_hd},
        "total": {"revenue": otc_rev + etc_rev, "invoices": otc_hd + etc_hd},
        "data_as_of": latest_data_date(),
    }
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac KHONG duoc hien thi."
    return result


def top_products(date_from: str, date_to: str, limit: int = 10, channel: str = "ALL",
                  scope_area_code: str = None, scope_channel: str = None) -> list:
    """Top N san pham theo doanh thu. Loai hang khuyen mai (unit_price=0) khoi so luong ban that.
    scope_area_code: ep loc theo vung khi tai khoan bi gioi han (xem revenue_by_channel).
    scope_channel: EP GHI DE tham so channel (bo qua gia tri AI truyen vao) khi tai khoan bi gioi
    han kenh - dam bao khong the "mo khoa" kenh khac bang cach truyen channel='ETC'/'ALL'."""
    if scope_channel:
        channel = scope_channel
    scope_sql, scope_params = _scope_clause(scope_area_code)
    parts, part_params = [], []
    if channel in ("OTC", "ALL"):
        join = _otc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.item_code, v.amount9, v.quantity, v.unit_price FROM vhoadon_otc v {join} "
                      f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, date_to) + scope_params)
    if channel in ("ETC", "ALL"):
        join = _etc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.item_code, v.amount9, v.quantity, v.unit_price FROM vhoadon_etc v {join} "
                      f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, date_to) + scope_params)
    sql = f"""WITH combined AS ({" UNION ALL ".join(parts)})
              SELECT c.item_code, sp.name,
                     SUM(c.amount9) rev,
                     SUM(CASE WHEN COALESCE(c.unit_price,0) > 0 THEN c.quantity ELSE 0 END) qty
              FROM combined c LEFT JOIN brv_sanpham sp ON sp.code = c.item_code
              GROUP BY c.item_code, sp.name ORDER BY rev DESC LIMIT ?"""
    params = tuple(p for pp in part_params for p in pp) + (limit,)
    rows = _q(sql, params)
    result = [{"item_code": r["item_code"], "name": r["name"] or f'(chua co ten - ma {r["item_code"]})',
               "revenue": _f(r["rev"]), "qty": _f(r["qty"])} for r in rows]
    # Du lieu cu hon 12 thang da bi NEN thanh KH x thang (khong con item_code) - top san pham KHONG
    # the tinh dung cho phan xa hon cua so nay, phai bao ro thay vi am tham tra ve so thieu.
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        return {"warning": f"Cau hoi vuot qua cua so 12 thang gan nhat (truoc {cutoff}) - du lieu chi tiet "
                            f"tung san pham cho giai doan cu hon KHONG con duoc luu (chi con tong doanh thu "
                            f"theo khach hang/thang). Ket qua duoi day CHI tinh tu {max(date_from, cutoff)} "
                            f"tro di, KHONG dai dien cho toan bo khoang thoi gian da hoi.",
                "date_from_actually_used": max(date_from, cutoff), "products": result}
    return result


def top_customers(date_from: str, date_to: str, limit: int = 10, channel: str = "ALL",
                   scope_area_code: str = None, scope_channel: str = None, scope_employee_code: str = None) -> list:
    """Top N khach hang theo doanh thu. scope_area_code: ep loc theo vung khi tai khoan bi gioi han.
    scope_channel: EP GHI DE tham so channel khi tai khoan bi gioi han kenh (xem top_products)."""
    if scope_channel:
        channel = scope_channel
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v")
    scope_sql += emp_sql
    scope_params += emp_params
    parts, part_params = [], []
    if channel in ("OTC", "ALL"):
        join = _otc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.customer_code, v.amount9 FROM vhoadon_otc v {join} "
                      f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, date_to) + scope_params)
    if channel in ("ETC", "ALL"):
        join = _etc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.customer_code, v.amount9 FROM vhoadon_etc v {join} "
                      f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, date_to) + scope_params)

    # date_from truoc cua so 12 thang chi tiet -> cong them phan da NEN tu monthly_customer_summary
    # (khong con item/created_at nhung van co customer_code + revenue nen top_customers tinh dung duoc).
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        summary_to = min(date_to, cutoff)
        ym_from, ym_to = date_from[:7], summary_to[:7]
        if channel in ("OTC", "ALL"):
            msc_sql, msc_params = _monthly_summary_scope_clause(scope_area_code, "OTC")
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m")
            msc_sql += msc_emp_sql
            msc_params += msc_emp_params
            parts.append(f"SELECT m.customer_code, m.revenue AS amount9 FROM monthly_customer_summary m "
                         f"WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ?{msc_sql}")
            part_params.append((ym_from, ym_to) + msc_params)
        if channel in ("ETC", "ALL"):
            msc_sql, msc_params = _monthly_summary_scope_clause(scope_area_code, "ETC")
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m")
            msc_sql += msc_emp_sql
            msc_params += msc_emp_params
            parts.append(f"SELECT m.customer_code, m.revenue AS amount9 FROM monthly_customer_summary m "
                         f"WHERE m.channel='ETC' AND m.year_month BETWEEN ? AND ?{msc_sql}")
            part_params.append((ym_from, ym_to) + msc_params)

    sql = f"""WITH combined AS ({" UNION ALL ".join(parts)})
              SELECT customer_code, SUM(amount9) rev
              FROM combined GROUP BY customer_code ORDER BY rev DESC LIMIT ?"""
    params = tuple(p for pp in part_params for p in pp) + (limit,)
    rows = _q(sql, params)
    return [{"customer_code": r["customer_code"], "revenue": _f(r["rev"])} for r in rows]


def _channel_sub_buckets():
    """Cac ban ghi 'kenh ao' trong dim_nhanvien (QLV gia dung de gan doanh thu kenh dac biet, vd
    Modern Trade/Long Chau - Name bat dau bang 'Kênh', IsDuplicate=1) - KHONG phai QLV that, chi la
    cho gan doanh thu theo kenh ban hang. dmsid cua ban ghi nay khop voi vhoadon_otc.channel_code
    (tu EmpDMSCode2 tren Bravo, xem sync_warehouse.py) - CHI co o OTC, ETC khong co co che nay."""
    return _q("SELECT dmsid, name, area_code FROM dim_nhanvien "
              "WHERE position_code='QLV' AND is_duplicate=1 AND name LIKE 'Kênh%' AND dmsid IS NOT NULL")


def revenue_by_region(date_from: str, date_to: str, scope_area_code: str = None, channel: str = "ALL",
                       scope_channel: str = None) -> list:
    """Doanh thu theo vung mien (MB/MT/MN). channel: 'ALL' (mac dinh, gop OTC+ETC), 'OTC', hoac 'ETC' -
    scope_channel: EP GHI DE tham so channel (bo qua gia tri AI truyen vao) khi tai khoan bi gioi han
    kenh (xem top_products/top_customers) - dam bao tai khoan chi duoc xem OTC khong the tu hoi ETC
    de "mo khoa" so lieu vung minh khong duoc thay.
    28/07/2026 THEM tham so nay sau khi phat hien BAT THUONG: cau hoi "doanh thu OTC theo vung" ma goi
    tool nay KHONG loc kenh se ra so BI THOI PHONG gap ~4 lan (vd Mien Nam OTC that ~6,6 ty nhung ETC
    rieng vung nay len toi ~18,8 ty do 1-2 benh vien/thau lon, cong chung ra 25,4 ty neu khong tach) -
    day la nguyen nhan khien AI phai duoc hoi lai nhieu lan moi ra dung so OTC rieng, gio da co san
    tham so de goi dung ngay tu dau. CA HAI kenh deu LEFT JOIN qua bang khach hang de lay city_id (da
    doi chieu voi DA ben Bravo va xac nhan day la cach dung - KHONG dung city_id ghi truc tiep tren
    vhoadon_otc vi truong nay khong dang tin, tung gay lech doanh thu theo vung).
    BAT BUOC LEFT JOIN (khong duoc INNER JOIN) - khach "mo coi" khong co trong bang khach hang (vd
    HCM13508 - co that, ~2.3 ty doanh thu 2022-2025, KHONG co trong dms_khachhang) se bi INNER JOIN
    am tham loai bo ca khoi tong lan breakdown. Voi LEFT JOIN, khach mo coi duoc suy luan vung qua
    TIEN TO ma khach hang (region_map.py, bang 63 tien to da kiem chung >=95% thuan, vd HCM -> MN) -
    CHI con roi vao "Khac/chua xac dinh" neu tien to khong nam trong bang do (an toan hon doan bua).
    Moi dong CO THE co them "channel_breakdown" (danh sach {name, revenue}) neu vung do co kenh dac
    biet duoc theo doi rieng (vd Modern Trade/Long Chau, Pharmacity... trong Mien Nam, CHI thuoc OTC) -
    day la SO DA NAM SAN TRONG "revenue" cua vung (KHONG duoc cong them vao tong), chi de bao cao minh
    bach tach rieng theo yeu cau nghiep vu (xac nhan voi DA DNH 20/07/2026): kenh nay VAN tinh vao tong
    vung nhung can hien thi tach biet vi ban chat kinh doanh khac (chuoi lon vs kenh thuong)."""
    if scope_channel:
        channel = scope_channel
    parts = []
    part_params = []
    if channel != "ETC":
        parts.append("""
        SELECT o.customer_code cc, tp.area_code area, SUM(o.amount9) rev
        FROM vhoadon_otc o LEFT JOIN dms_khachhang kh ON kh.code=o.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE o.doc_date BETWEEN ? AND ? GROUP BY o.customer_code, tp.area_code""")
        part_params.append((date_from, date_to))
    if channel != "OTC":
        parts.append("""
        SELECT e.customer_code cc, tp.area_code area, SUM(e.amount9) rev
        FROM vhoadon_etc e LEFT JOIN dmssx_khachhang kh ON kh.code=e.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE e.doc_date BETWEEN ? AND ? GROUP BY e.customer_code, tp.area_code""")
        part_params.append((date_from, date_to))
    params = tuple(p for pp in part_params for p in pp)
    rows = _q(" UNION ALL ".join(parts), params)

    # date_from truoc cua so 12 thang chi tiet -> cong them phan da NEN (monthly_customer_summary co
    # customer_code nen van suy luan vung qua dms_khachhang/dmssx_khachhang giong nhu tren).
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        summary_to = min(date_to, cutoff)
        ym_from, ym_to = date_from[:7], summary_to[:7]
        summary_parts = []
        summary_params = []
        if channel != "ETC":
            summary_parts.append("""
            SELECT m.customer_code cc, tp.area_code area, SUM(m.revenue) rev
            FROM monthly_customer_summary m LEFT JOIN dms_khachhang kh ON kh.code=m.customer_code
            LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
            WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ? GROUP BY m.customer_code, tp.area_code""")
            summary_params.append((ym_from, ym_to))
        if channel != "OTC":
            summary_parts.append("""
            SELECT m.customer_code cc, tp.area_code area, SUM(m.revenue) rev
            FROM monthly_customer_summary m LEFT JOIN dmssx_khachhang kh ON kh.code=m.customer_code
            LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
            WHERE m.channel='ETC' AND m.year_month BETWEEN ? AND ? GROUP BY m.customer_code, tp.area_code""")
            summary_params.append((ym_from, ym_to))
        rows = list(rows) + _q(" UNION ALL ".join(summary_parts),
                                tuple(p for pp in summary_params for p in pp))

    agg = {}
    for r in rows:
        area = r["area"] or region_from_customer_code(r["cc"]) or "Khac/chua xac dinh"
        agg[area] = agg.get(area, 0.0) + _f(r["rev"])
    total = sum(agg.values())

    if scope_area_code:
        # Tai khoan bi gioi han vung: CHI tra ve dung 1 vung duoc phep, KHONG lo cac vung khac ra
        # ngoai (agg da tinh full o tren de con dung cho phep tinh noi bo, nhung KHONG duoc tra het ra).
        v = agg.get(scope_area_code, 0.0)
        result = [{"area": scope_area_code, "revenue": v, "share_pct": 100.0 if v else 0.0}]
    else:
        # Tu doi chieu (re # 4): tong cong theo vung PHAI bang dung tong khong loc vung cung ky - neu
        # lech tuc la co JOIN nao do dang am tham lam roi du lieu (vd bi doi lai thanh INNER JOIN).
        # Dung LAI revenue_by_channel() (da co san UNION nen du lieu >12 thang) thay vi tu SUM rieng,
        # tranh 2 noi tinh "tong khong loc vung" khac cong thuc nhau (nhat la sau khi them nen du lieu).
        # Voi channel='OTC'/'ETC', so sanh dung voi phan kenh tuong ung (khong phai total gop ca 2).
        rbc = revenue_by_channel(date_from, date_to)
        raw_total = (rbc["otc"]["revenue"] if channel == "OTC"
                     else rbc["etc"]["revenue"] if channel == "ETC"
                     else rbc["total"]["revenue"])
        if abs(total - raw_total) > 1:
            _write_log({"ts": dt.datetime.now().isoformat(), "status": "warn",
                        "sql": "<revenue_by_region reconciliation check>",
                        "error": f"Tong theo vung ({total}) LECH voi tong khong loc vung ({raw_total}) - "
                                 f"co JOIN dang lam roi du lieu, kiem tra lai ngay."})
            # 22/07/2026 (diem #5): truoc day CHI ghi log - nguoi dung van nhan breakdown sai ma
            # khong he biet. Gio bao len tan cau tra loi.
            _warn(f"SO LIEU THEO VUNG CO THE THIEU: tong cong theo vung ({total:,.0f} d) khong khop "
                  f"tong doanh thu khong loc vung ({raw_total:,.0f} d), chenh {abs(total - raw_total):,.0f} d. "
                  f"PHAI canh bao nguoi dung rang phan chia theo vung dang thieu/sai, KHONG duoc trinh bay "
                  f"breakdown nay nhu so lieu chac chan.")
        result = [{"area": k, "revenue": v, "share_pct": (v / total * 100 if total else 0.0)}
                  for k, v in sorted(agg.items(), key=lambda x: -x[1])]

    # Tach rieng cac kenh dac biet (vd Modern Trade) da NAM SAN trong "revenue" cua vung - chi de
    # bao cao minh bach, KHONG cong them vao tong (xem _channel_sub_buckets()). CHI tinh duoc tu du
    # lieu CHI TIET (channel_code khong duoc luu trong monthly_customer_summary da nen) - neu date_from
    # vuot cua so 12 thang, breakdown nay se THIEU phan da nen, ghi ro trong "note" de khong hieu nham.
    # Kenh dac biet (Modern Trade...) CHI ton tai trong OTC - bo qua hoan toan khi channel='ETC'.
    buckets = _channel_sub_buckets() if channel != "ETC" else []
    if buckets:
        for row in result:
            row_buckets = [b for b in buckets if b["area_code"] == row["area"]]
            if row_buckets:
                breakdown = []
                for b in row_buckets:
                    r = _q("SELECT COALESCE(SUM(amount9),0) rev FROM vhoadon_otc WHERE channel_code=? "
                           "AND doc_date BETWEEN ? AND ?", (b["dmsid"], max(date_from, cutoff), date_to))
                    breakdown.append({"name": b["name"], "revenue": _f(r[0]["rev"])})
                row["channel_breakdown"] = breakdown
                if date_from < cutoff:
                    row["channel_breakdown_note"] = (
                        f"Chi tinh tu {cutoff} tro di - du lieu truoc {cutoff} da bi nen va khong con "
                        f"tach duoc theo kenh dac biet (vd Modern Trade).")
    return result


# 23/07/2026: doi tu 80 sang 65 - lay theo CAU HINH THAT cua DNH trong bang `dbo.DIM_BacThuong`
# (Bravo), bang ma chinh thu tuc tinh luong `usp_SaleSalary_Calculation_Ver2` doc de quyet dinh ty le
# thuong. Bac dau tien co Earn1>0 = moc bat dau duoc thuong:
#     TDV -> 65% (bac 65/75/85/95)   |   QLV,CS,TP,PP,TBP,TK -> 70% (bac 70/80/90/100/120)
# Giong nhau ca 3 mien MB/MT/MN. Con so 80 truoc day la MCNA tu dat, khong co can cu nghiep vu.
# Repo bao cao D:\DNH (src/etl.py) doi cung ngay, cung gia tri - 2 he thong PHAI giong nhau.
#
# ⚠️ 23/07/2026 (chieu) - PHAN BIET 2 KHAI NIEM BI GOP NHAM SUOT TU DAU:
#   "DAT CHI TIEU"              = lam duoc >= 100% chi tieu thang. Giua thang gan nhu luon ~0 nguoi,
#                                 vi doanh so moi luy ke toi hom nay con chi tieu la CA THANG.
#   "DAT MUC THUONG NHOM HANG"  = >= nguong bat dau duoc tinh THUONG NHOM HANG (TDV 65%, quan ly 70%).
# Hai cau hoi KHAC NHAU, ra 2 con so khac nhau. Nhan cu "Dat Chi Tieu (>=65%)" tu no da mau thuan:
# dat chi tieu ma moi lam duoc 65% chi tieu. Tra ve CA HAI, va noi ro dang tra loi cai nao.
#
# ⚠️⚠️ VA DUNG GOI 65%/70% LA "NGUONG HUONG THUONG" CHUNG CHUNG. Do CHI la cong cua THUONG NHOM HANG
# (DS.DM1/DM2/DM3). Trong dbo.DIM_BacThuong con it nhat 5 ho thuong khac, moc khac nhau va TRA THEO
# CHI SO KHAC NHAU:
#   V15  - dat 25% doanh so thang vao ngay 15        (moc giua ky, KHONG phai % ca thang)
#   V22  - 55% doanh so thang + ty le target >=75/80%
#   V25  - >=70% tinh den ngay 25 (the he QD 0429)
#   ASO  - theo SO LUONG khach hang hoat dong (MB 40, MT 35, MN 25) - KHONG phai %
#   QB/YB- thuong quy >=80% quy, thuong nam >=75% nam
# Chua ke LUONG CO BAN: tu 60% tro len van huong 100% LCB, duoi 60% moi bi cat theo ty le.
# => Nguoi duoi 65% VAN CO THE duoc V15/ASO va VAN huong du luong co ban. TUYET DOI khong dien dat
# thanh "khong duoc thuong" / "khong dat KPI" - do la noi sai ve tien luong cua nguoi that.
#
# ⚠️⚠️⚠️ 27/07/2026 - XAC NHAN VOI DNH: co BA MOC KHAC NHAU, TUYET DOI KHONG GOP:
#   >= 100%  DAT CHI TIEU        - lam du chi tieu thang duoc giao (nghia den).
#   >=  80%  DAT KPI             - moc danh gia HIEU QUA CONG VIEC. AP DUNG CHO MOI VAI TRO
#                                  (khong chia theo TDV/quan ly). Day la moc de cham 🟢/🟡/🔴.
#   >=65/70% TOI MUC THUONG      - CONG bat dau duoc tinh THUONG NHOM HANG (DM1/DM2/DM3), theo
#                                  DIM_BacThuong: TDV 65%, quan ly 70%. KHONG PHAI "dat KPI".
#
# LOI TUNG MAC (23/07 -> 27/07): 65/70 bi dat ten KPI_ACHIEVED_THRESHOLD va duoc goi la "dat KPI",
# lam nguoi dat 67% bi bao la "DA DAT KPI" trong khi thuc te moi qua cong thuong, chua dat KPI (80%).
# Nay tach han: BONUS_THRESHOLD* = cong thuong (65/70), KPI_ACHIEVED_THRESHOLD = dat KPI (80).
BONUS_THRESHOLD = 65             # TDV - cong THUONG NHOM HANG (QD 0107/2026)
BONUS_THRESHOLD_MGR = 70         # QLV va cac vai tro quan ly/kenh - cong thuong (QD 0429/.25)
KPI_ACHIEVED_THRESHOLD = 80      # DAT KPI - moc danh gia hieu qua, CHUNG cho moi vai tro
KPI_FULL_TARGET = 100            # "dat chi tieu" dung nghia den - khong lien quan 2 moc tren
KPI_WARN_THRESHOLD = 50          # duoi nguong nay coi la "nguy hiem" (do), giua 2 nguong la "trung binh" (vang)

# 23/07/2026 - PORT tu repo bao cao D:\DNH (src/alerts.py::_KNOWN_MISFLAGGED_DUPLICATE_CODES +
# _is_duplicate_filter_sql). 2 nhan vien THAT, dang lam viec binh thuong, bi Bravo gan nham co
# "trung lap" (IsDuplicate=1) nen bi LOAI KHOI moi bao cao KPI/doanh so:
#   MBKV12      Nguyen Thi Thanh Thuy  ~2,01 ty doanh so, target 5,28 ty
#   TM25030101  Lac Ngoc Sam           ~389 trieu/thang
# Da kiem chung day la loi gan co, KHONG phai nghi viec (khong co ngay ket thuc + van phat sinh doanh
# so deu 15-17 thang lien tuc). Repo bao cao da va tu 20/07; chatbot thi CHUA -> chay thu 23/07 voi
# tai khoan thuy.nguyen2 hoi "KPI cac QLV vung toi" chi ra 9/10 QLV, thieu dung MBKV12, va KHONG co
# dong nao bao la da bo qua ai. Da de nghi DNH sua du lieu goc (muc C1 trong
# docs/Cau_hoi_can_DNH_xac_nhan.md); den luc do giu ngoai le o day.
# DUNG _not_duplicate_sql() thay vi viet tay "COALESCE(is_duplicate,0)<>1" - truoc do viet tay lap lai
# 6 cho, sua 1 cho quen 5 cho la chuyen som muon.
_KNOWN_MISFLAGGED_DUPLICATE_CODES = ("MBKV12", "TM25030101")


def _not_duplicate_sql(alias: str = "nv") -> str:
    """Manh SQL loc "khong bi danh dau trung lap", CO ngoai le cho _KNOWN_MISFLAGGED_DUPLICATE_CODES."""
    codes = ",".join(f"'{c}'" for c in _KNOWN_MISFLAGGED_DUPLICATE_CODES)
    p = f"{alias}." if alias else ""
    return f"(COALESCE({p}is_duplicate,0)<>1 OR {p}employee_code IN ({codes}))"


# 23/07/2026 - VA LOI "nguong quan ly khai bao nhung khong dung": KPI_ACHIEVED_THRESHOLD_MGR ton tai
# tu ban va 65% buoi sang nhung KHONG duoc goi o BAT KY dau - moi vai tro deu bi cham o 65%. Hau qua
# that: 1 QLV dat 67% duoc gan nhan "🟢 Tot"/"da dat", trong khi QD 0429/QD-HDQT.25 (van hieu luc voi
# cap QLV) quy dinh duoi 70% huong 0% thuong danh muc - tuc la BAO SAI theo huong co loi.
# Nguon: QD 0429-1 (MB) phu luc 02 bang 01, QD 0429-2 (MN), QD 0429-3 (MT) - deu co chu ky, deu chan
# duoi o 70%. Rieng TDV da chuyen sang QD 0107/2026 (hieu luc 01/07/2026) nen chan duoi 65%.
def _bonus_threshold(position_code: str = None) -> int:
    """Nguong % de bat dau duoc tinh THUONG NHOM HANG, THEO VAI TRO. KHONG PHAI nguong "dat KPI"
    (dat KPI = 80% cho moi vai tro, xem _kpi_status).
    TDV -> 65 (QD 0107/2026). QLV/TP/PP/TBP/TK/CS -> 70 (QD 0429/.25, van hieu luc).
    position_code=None -> 65: giu nguyen hanh vi cu cho cac dong khong biet vai tro, va vi tuyet dai
    da so dong trong fact_tonghopkhachhang la TDV. KHONG doan bua sang 70 vi lam vay se bao "chua toi
    muc thuong" cho nguoi that ma minh chi khong tra duoc vai tro."""
    if position_code and position_code.strip().upper() != "TDV":
        return BONUS_THRESHOLD_MGR
    return BONUS_THRESHOLD


def _kpi_status(pct: float, position_code: str = None) -> str:
    """Phan loai mau theo moc DAT KPI = 80% (KPI_ACHIEVED_THRESHOLD), CHUNG cho moi vai tro - xac
    nhan voi DNH 27/07/2026. CO Y khong cham theo 65/70: do la cong THUONG, khong phai thuoc do hieu
    qua cong viec; cham theo 65/70 tung lam nguoi dat 67% duoc gan nhan "🟢 Tot"/"dat KPI" sai.
    >=80 Tot (xanh), 50..79 Trung binh (vang), <50 Nguy hiem (do).
    position_code giu lai cho tuong thich chu ky ham (khong con dung) - moc nay khong theo vai tro."""
    if pct >= KPI_ACHIEVED_THRESHOLD:
        return "🟢 Tốt"
    if pct >= KPI_WARN_THRESHOLD:
        return "🟡 Trung bình"
    return "🔴 Nguy hiểm"


def employee_kpi(as_of_date: str, limit: int = 10, order_by: str = "sales", filter: str = "all",
                  position_code: str = None, scope_area_code: str = None,
                  scope_employee_code: str = None) -> dict:
    """KPI nhan vien: snapshot fact_tonghopkhachhang gan nhat <= as_of_date.
    order_by: 'sales' hoac 'pct' (dung khi filter='all', luon xep TOT NHAT truoc).
    filter: 'all' (top N tot nhat), 'below_target' (CHUA toi muc thuong nhom hang, xep TE NHAT truoc),
            'above_target' (DA toi muc thuong nhom hang, xep TOT NHAT truoc).
    position_code: loc theo vai tro (vd 'TDV','QLV') - LUON dung tham so nay khi cau hoi chi dinh ro
    vai tro (vd "top TDV"), KHONG tu loc thu cong tu ket qua day du vi de sot/thieu chinh xac.

    ⚠️ PHAN BIET BA MOC, TUYET DOI KHONG GOP:
      - "DAT CHI TIEU" = >=100% chi tieu thang -> dung "count_full_target" (va co "meets_full_target"
        tren tung dong). Giua thang con so nay gan nhu luon ~0 va DO LA DUNG: doanh so moi luy ke toi
        hom nay, con chi tieu la ca thang.
      - "DAT KPI" = >=80% ("kpi_threshold_pct", CHUNG cho moi vai tro) -> dung "count_kpi_achieved";
        day cung la moc quyet dinh mau 🟢/🟡/🔴 o truong "status".
      - "TOI MUC THUONG NHOM HANG" = >= "threshold" cua tung dong (TDV 65% theo QD 0107/2026,
        QLV va cac cap quan ly 70% theo QD 0429/.25) -> dung "count_above_target"/"count_below_target".
    Hoi "ai chua dat chi tieu" -> moc 100%; hoi "ai dat KPI" -> moc 80%; hoi "ai toi muc thuong nhom
    hang" -> "threshold". Neu cau hoi mo ho thi dua CA BA con so va noi ro tung cai la gi.
    ⚠️ TUYET DOI khong goi 65%/70% la "dat KPI" - do chi la cong THUONG. Nguoi dat 67% la "da toi muc
    thuong nhom hang nhung CHUA dat KPI (80%)".

    ⚠️ 65%/70% CHI la cong cua THUONG NHOM HANG (DM1/DM2/DM3), KHONG phai "nguong huong thuong" noi
    chung. Con V15 (25% doanh so vao ngay 15), V22, V25, ASO (theo SO LUONG khach hang: MB 40/MT 35/
    MN 25, khong phai %), thuong quy, thuong nam - moc khac va tra theo chi so khac. Luong co ban tu
    60% tro len van huong 100%. Nguoi duoi 65% VAN CO THE duoc cac khoan kia va VAN co luong co ban,
    nen TUYET DOI khong dien dat "khong duoc thuong" / "khong dat KPI" - do la noi sai ve tien luong
    cua nguoi that. He thong hien CHUA co du lieu de tinh V15/V22/ASO (xem schema_context).

    scope_employee_code: CHI danh cho tai khoan qlv - ep chi tra ve CHINH HO + cac TDV THUOC DOI HO,
    khong thay nhan su cua QLV khac (du lieu hieu suat CA NHAN dong nghiep).
    23/07/2026 - VA LO HONG PHAN QUYEN: truoc do ham nay KHONG nhan scope_employee_code nen chi bi
    loc theo VUNG. Chay thu that voi tai khoan tung.trinh (QLV, doi 10 TDV) hoi "cac TDV duoi quyen
    toi" -> tra ve DU 87 TDV toan vung MB, gom ca nguoi cua doi MBKV1/MBKV2/MBKV3/MBKV9 kem doanh so
    + % dat. Cung tai khoan do hoi thang "doi anh Pham Kim Tan the nao" thi BI CHAN (vi AI chon
    get_kpi_ranking - tool DA co scope) -> tuc la phan quyen truoc day phu thuoc vao viec AI tinh co
    chon tool nao, khong phai hang rao that. Xem docs/kich_ban_demo1_chatbot.md muc R-F (repo D:\\DNH).
    """
    fdate_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?", (as_of_date,))
    fdate = fdate_r[0]["d"] if fdate_r else None
    if fdate is None:
        return {"as_of": None, "total_employees": 0, "count_below_target": 0, "count_above_target": 0, "rows": []}
    sql = f"""SELECT nv.name name, e.employee_code employee_code,
                    nv.position_code position_code, cv.description position_label,
                    SUM(e.amount_ct) sales, MAX(e.month_sale_target) target,
                    SUM(e.is_nc) new_customers
             FROM fact_tonghopkhachhang e
             JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=e.employee_code AND l.d=e.save_date
             LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code
             LEFT JOIN dim_chucvu cv ON cv.position_code=nv.position_code
             WHERE {_not_duplicate_sql('nv')}"""
    params = [fdate, fdate]
    if position_code:
        sql += " AND nv.position_code=?"
        params.append(position_code)
    if scope_area_code:
        sql += " AND nv.area_code=?"
        params.append(scope_area_code)
    if scope_employee_code:
        # Doi cua QLV nay + chinh ho, tai DUNG snapshot dang xet (fdate) - dung manager_code THAT tu
        # Bravo (_team_of_qlv), KHONG con suy luan qua zone nua (xem docstring _team_of_qlv - suy luan
        # zone tung lam 5 QLV bi hieu nham "khong co doi", gay cong trung KPI vung).
        team = _team_of_qlv(scope_employee_code, fdate)
        if not team:
            # Khac voi truoc (khi con dung zone, ~30% khong map duoc): gio manager_code la du lieu
            # THAT tren tung dong hoa don/snapshot, nen "khong co doi" o day PHAN LON la dung that
            # (vd QLV tu om khach, khong co TDV duoi quyen - vd MBKV12). Van tra loi mem thay vi loi
            # cung, vi khong loai tru truong hop hiem thieu du lieu dong bo.
            return {"as_of": fdate, "total_employees": 0, "count_below_target": 0, "count_above_target": 0,
                    "rows": [], "note": (
                        f"Khong tim thay TDV nao bao cao truc tiep len ma quan ly '{scope_employee_code}' "
                        f"tai snapshot {fdate}. Neu ban biet minh CO quan ly TDV, day co the la han che "
                        "dong bo du lieu - lien he MCNA. Neu ban tu phu trach khach hang truc tiep (khong "
                        "co doi), day la dung.")}
        allowed = [scope_employee_code] + [t["employee_code"] for t in team]
        sql += f" AND e.employee_code IN ({','.join(['?'] * len(allowed))})"
        params.extend(allowed)
    sql += """ GROUP BY nv.name, e.employee_code, nv.position_code, cv.description
               HAVING MAX(e.month_sale_target)>0"""
    rows = _q(sql, tuple(params))
    for r in rows:
        r["sales"] = _f(r["sales"]); r["target"] = _f(r["target"])
        r["pct"] = (r["sales"] / r["target"] * 100) if r["target"] else 0.0
        r["new_customers"] = int(r["new_customers"] or 0)
        # BA MOC TACH BACH (xac nhan voi DNH 27/07/2026) - dung gop khi tra loi:
        #  threshold      = cong THUONG NHOM HANG, theo VAI TRO tung dong (TDV 65% / quan ly 70%).
        #                   1 truy van co the tra ve lan lon 2 vai tro nen khong dung 1 nguong phang.
        #  kpi_threshold  = moc DAT KPI = 80%, CHUNG cho moi vai tro. status cham theo moc nay.
        #  meets_full_target = DAT CHI TIEU dung nghia den (>=100%).
        r["threshold"] = _bonus_threshold(r["position_code"])
        r["kpi_threshold"] = KPI_ACHIEVED_THRESHOLD
        r["meets_kpi"] = r["pct"] >= KPI_ACHIEVED_THRESHOLD
        r["status"] = _kpi_status(r["pct"], r["position_code"])
        r["meets_full_target"] = r["pct"] >= KPI_FULL_TARGET
    below = [r for r in rows if r["pct"] < r["threshold"]]
    above = [r for r in rows if r["pct"] >= r["threshold"]]
    if filter == "below_target":
        selected = sorted(below, key=lambda r: r["pct"])[:limit]
    elif filter == "above_target":
        selected = sorted(above, key=lambda r: -r["pct"])[:limit]
    else:
        key = "sales" if order_by == "sales" else "pct"
        selected = sorted(rows, key=lambda r: -r[key])[:limit]
    return {"as_of": fdate, "total_employees": len(rows),
            # count_below/above_target = so nguoi DUOI/DAT MUC HUONG THUONG doanh so (65% hoac 70%
            # tuy vai tro). Ten cu giu nguyen de khong pha cac cho dang goi, nhung Y NGHIA la "muc
            # huong thuong", KHONG phai "dat chi tieu".
            "count_below_target": len(below), "count_above_target": len(above),
            # DAT KPI = >=80%, moc danh gia hieu qua cong viec (chung moi vai tro).
            "count_kpi_achieved": sum(1 for r in rows if r["meets_kpi"]),
            "kpi_threshold_pct": KPI_ACHIEVED_THRESHOLD,
            # Con day moi la "DAT CHI TIEU" dung nghia den: lam duoc >=100% chi tieu thang.
            "count_full_target": sum(1 for r in rows if r["meets_full_target"]),
            "full_target_pct": KPI_FULL_TARGET,
            "rows": selected}


DAILY_KPI_TARGET_PCT = 4.0  # 4% MonthSaleTarget = "100%" cua 1 ngay lam viec (yeu cau nghiep vu)
DAILY_KPI_RED = 2.5          # duoi nguong nay: do
DAILY_KPI_YELLOW_MAX = 3.5   # 2.5% - 3.5%: vang; tren 3.5%: xanh


def _daily_kpi_status(pct: float) -> str:
    if pct < DAILY_KPI_RED:
        return "🔴 Đỏ"
    if pct <= DAILY_KPI_YELLOW_MAX:
        return "🟡 Vàng"
    return "🟢 Xanh"


def employee_daily_kpi(employee_code: str, year_month: str, scope_area_code: str = None,
                        scope_employee_code: str = None) -> dict:
    """KPI THEO NGAY cho 1 nhan vien CA NHAN (co ma truc tiep tren hoa don, vd EmpDMSCode nhu
    'tungtx') trong 1 thang (YYYY-MM). Target 1 ngay = 4% MonthSaleTarget cua nhan vien (tuong duong
    100% cua ngay). Phan loai tung ngay: 🔴 Do (<2.5%), 🟡 Vang (2.5%-3.5%), 🟢 Xanh (>3.5%). CHI tinh
    T2-T6 (bo qua T7/CN). Rieng "month_pct_of_target" la % TONG thang (thuc te/target*100, cach tinh
    CU khong lien quan 4%/ngay, KHONG co mau/nguong - chi la con so tham khao cuoi thang.
    KHONG dung cho ma khu vuc/quan ly vung (MBKV*, ASM*...) - cac ma nay khong xuat hien tren hoa don,
    dung get_employee_kpi (snapshot thang, nguong theo vai tro: TDV 65% / quan ly 70%, canh bao 50%)
    thay the cho nhom do.
    scope_area_code: NEU co, chi cho xem KPI cua nhan vien CUNG vung - tra ve loi neu khac vung
    (an toan hon la mac dinh cho phep khi khong xac dinh duoc vung cua nhan vien).
    LUU Y KY THUAT: hoa don (vhoadon_otc/etc.employee_code) ghi theo DMSId cua nhan vien, KHONG PHAI
    EmployeeCode (2 gia tri thuong khac nhau, vd EmployeeCode='DNH00832' nhung DMSId='HYE_02') - da
    xac minh 17/07/2026 doi chieu ~150 TDV khop 100% khi dung dung DMSId. Tham so employee_code dau
    vao co the la EmployeeCode HOAC DMSId (tra ca 2, giong employee_directory), ham tu quy doi sang
    DMSId that truoc khi truy van hoa don. NEU nhan vien khong co trong dim_nhanvien, tu dong thu
    tiep dmssx_nhanvien (bang rieng phia SX/ETC, xac nhan 20/07/2026 - xem _resolve_employee_identity())
    - truong hop nay scope_area_code se LUON tu choi (vung khong xac dinh duoc, an toan hon cho qua).
    scope_employee_code: CHI danh cho tai khoan qlv - chi cho xem nhan vien THUOC DOI ho (hoac chinh
    ho); nguoi ngoai doi bi tu choi (them 23/07/2026 cung dot va R-F, xem docstring employee_kpi)."""
    ident = _resolve_employee_identity(employee_code)
    resolved_code = ident["code"]
    dms_code = ident["dmsid"]
    if scope_area_code:
        if ident["area_code"] != scope_area_code:
            return {"error": f"Ban khong co quyen xem du lieu nhan vien nay - ngoai vung {scope_area_code} ban phu trach."}
    if scope_employee_code:
        # Snapshot gan nhat (khong co "as_of_date" rieng o day, chi co year_month cua doanh so can
        # xem) - cau truc quan ly it doi trong pham vi vai thang nen dung gan nhat la du.
        allowed = {scope_employee_code} | {t["employee_code"] for t in _team_of_qlv(scope_employee_code)}
        if resolved_code not in allowed:
            return {"error": "Ban chi duoc xem du lieu cua cac nhan vien trong doi minh phu trach."}
    # 23/07/2026 (R-G): CHAN ma cap quan ly thay vi tra "0 dong moi ngay". Ma QLV/TP/PP khong xuat
    # hien tren hoa don (hoa don ghi ma nhan vien ban hang ca nhan), nen ham nay se cong ra 0 va AI
    # dien giai thanh "17/17 ngay do, van de nghiem trong" - da xay ra that voi tungtx (QLV thuc te
    # dat 1,74 ty). So 0 do la THIEU DU LIEU, khong phai ket qua kinh doanh; tra ve loi ro rang de AI
    # khong the hieu nham, thay vi tra so 0 kem chu thich (chu thich rat de bi bo qua).
    if (ident["position_code"] or "").upper() in ("QLV", "TP", "PP", "TBP"):
        return {"error": (
            f"Ma '{employee_code}' la {ident['position_code']} (cap quan ly) - ma nay KHONG xuat hien "
            "tren hoa don nen KHONG co doanh so theo ngay. Day la gioi han du lieu, TUYET DOI KHONG "
            "duoc hieu la nhan vien nay ban duoc 0 dong. Dung get_employee_kpi (KPI thang) hoac "
            "get_revenue_tree (doanh so ca doi) cho cap quan ly.")}
    year, month = int(year_month[:4]), int(year_month[5:7])
    month_start = dt.date(year, month, 1)
    month_end = (dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)) - dt.timedelta(days=1)
    today = dt.date.today()
    range_end = min(month_end, today)
    target_asof = min(month_end, today)

    # 28/07/2026: TRUOC DAY MAX(month_sale_target)+MAX(save_date) doc lap tren MOI snapshot
    # save_date<=target_asof - vi kho giu nhieu thang lich su (khong chi 90 ngay gan nhat, Bravo
    # con snapshot tu 2025), MAX() lay nham CHI TIEU CAO NHAT tung co, khong phai chi tieu THANG
    # DANG HOI. Day chinh la nguyen nhan chenh lech 1,13 ty da ghi trong kich_ban_demo1_chatbot.md
    # (tungtx: chatbot tung bao 4.149.931.306d = snapshot thang 4/2026, trong khi thang 7/2026 that
    # la 3.016.493.346d) - da xac nhan bang truy van truc tiep Bravo 28/07/2026. Sua: ghim vao dung
    # 1 snapshot MOI NHAT nam TRONG khoang [month_start, target_asof]. Cung nguyen tac "gop theo
    # THANG, lay ban ghi moi nhat cua CHINH nhan vien do" ma _MONTH_LATEST_SUBQ ap dung cho cac ham
    # KPI khac (29/07/2026) - o day da dung san tu 28/07 nen khong phai sua lai.
    r = _q("SELECT month_sale_target t, save_date d FROM fact_tonghopkhachhang "
           "WHERE employee_code=? AND save_date BETWEEN ? AND ? "
           "ORDER BY save_date DESC LIMIT 1", (resolved_code, str(month_start), str(target_asof)))
    target = _f(r[0]["t"]) if r else 0.0
    target_as_of = r[0]["d"] if r else None
    if not r:
        # Fail-closed: KHONG de target=0 lam moi ngay tu dong thanh do (pct=0) roi AI dien giai
        # thanh "khong ban duoc gi" - phai noi ro la THIEU DU LIEU chi tieu cho thang nay.
        _warn(f"Khong co snapshot chi tieu cho '{employee_code}' trong thang {year_month} trong kho "
              "local - so % theo ngay duoi day KHONG dang tin cay (target=0), can dong bo lai hoac "
              "hoi thang khac.")

    days = []
    total_sales_month = 0.0
    count_red = count_yellow = count_green = 0
    if range_end >= month_start:
        rows = _q("""SELECT doc_date, SUM(amount9) rev FROM (
                        SELECT doc_date, amount9 FROM vhoadon_otc WHERE employee_code=? AND doc_date BETWEEN ? AND ?
                        UNION ALL
                        SELECT doc_date, amount9 FROM vhoadon_etc WHERE employee_code=? AND doc_date BETWEEN ? AND ?
                     ) GROUP BY doc_date""",
                  (dms_code, str(month_start), str(range_end), dms_code, str(month_start), str(range_end)))
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


def _resolve_employee_identity(code: str) -> dict:
    """Tra danh tinh 1 nhan vien tu 1 ma (EmployeeCode HOAC DMSId): thu dim_nhanvien (OTC) truoc -
    neu co nhieu dong trung ma, uu tien dong is_duplicate=1 (thuong la nguoi that, xem
    employee_directory()). Neu KHONG co trong dim_nhanvien, thu tiep dmssx_nhanvien (bang nhan vien
    RIENG cho phia SX/ETC, xac nhan 20/07/2026: mot nhom nhan vien - vd ma DNH00087, DNH00268,
    Sale01-Sale15... - hoan toan khong ton tai trong DIM_NhanVien, chi co o day).
    Luon tra ve dict co "code" (ma da resolve, hoac ma dau vao neu khong tim thay gi), "name",
    "position_code", "area_code" (None neu tu dmssx_nhanvien - bang do khong co truong nay), "dmsid"
    (ma dung de truy van hoa don - danh cho vhoadon_otc/etc.employee_code)."""
    if not code:
        return {"code": code, "name": None, "position_code": None, "area_code": None, "dmsid": code}
    nv = _q("SELECT employee_code, dmsid, name, position_code, area_code FROM dim_nhanvien "
            "WHERE employee_code=? OR dmsid=? ORDER BY is_duplicate DESC LIMIT 1", (code, code))
    if nv:
        return {"code": nv[0]["employee_code"], "name": nv[0]["name"],
                "position_code": nv[0]["position_code"], "area_code": nv[0]["area_code"],
                "dmsid": nv[0]["dmsid"] or code}
    sx = _q("SELECT dmscode, code, name FROM dmssx_nhanvien WHERE dmscode=? OR code=? LIMIT 1", (code, code))
    if sx:
        return {"code": sx[0]["dmscode"] or code, "name": sx[0]["name"], "position_code": None,
                "area_code": None, "dmsid": sx[0]["code"] or code}
    return {"code": code, "name": None, "position_code": None, "area_code": None, "dmsid": code}


def employee_directory(search: str = None, position_code: str = None, area_code: str = None, limit: int = 30,
                        scope_area_code: str = None) -> list:
    """Tra cuu MAPPING ma nhan vien <-> ten <-> vai tro (TDV/QLV/CTV/CS/TP/PP/TBP/TK). Dung khi nguoi
    dung hoi "ma cua [ten]" / "[ten] la ai" / "danh sach TDV vung MB" - KHONG can biet ma truoc.
    search: tim gan dung theo TEN, employee_code, HOAC dmsid (khong phan biet hoa/thuong) - mot nguoi
    co the duoc hoi toi qua employee_code (vd 'TM25010101') hoac qua dmsid (ma noi bo DMS khac, vd
    'DNH00591') tuy nguon du lieu, nen PHAI thu ca 2. position_code: loc theo vai tro. area_code: loc
    theo vung (MB/MT/MN).
    KHONG loc is_duplicate (khac ban truoc) - day la tool TRA CUU/DINH DANH, khong phai tong hop KPI/
    doanh so (chi tool do moi can loc is_duplicate de tranh dem trung). PHAI tra ve ca is_duplicate va
    dmsid de nguoi goi tu phan biet khi trung: DA XAC NHAN THAT tren du lieu dmsid co the trung giua
    nhieu employee_code/vai tro khac nhau (vd DMSId 'DNH00601' vua la employee_code cua 1 dong TDV
    (is_duplicate=1) vua la dmsid cua 1 dong QLV khac (is_duplicate=0)) - VA is_duplicate=0 KHONG PHAI
    luon la dong "dung hon": vi du TM24060301, dong is_duplicate=0 la vi tri TRONG ("Trong QLV MK3"),
    dong is_duplicate=1 moi la ten nguoi that. Khi ket qua co NHIEU dong cho cung 1 ma tra cuu, PHAI
    liet ke HET, KHONG tu chon 1 dong.
    NEU co "search" VA KHONG loc position_code/area_code: ket qua CO THE gom them nhan vien tu
    dmssx_nhanvien (bang rieng phia SX/ETC, xac nhan 20/07/2026 - vd ma DNH00087, Sale01-Sale15...
    hoan toan khong co trong dim_nhanvien) - cac dong nay se co position_code/position_label/area_code
    = None vi bang do khong luu thong tin nay."""
    if scope_area_code:
        area_code = scope_area_code
    sql = """SELECT n.employee_code employee_code, n.dmsid dmsid, n.name name,
                    n.position_code position_code, c.description position_label, n.area_code area_code,
                    n.is_duplicate is_duplicate
             FROM dim_nhanvien n LEFT JOIN dim_chucvu c ON c.position_code=n.position_code
             WHERE 1=1"""
    params = []
    if search:
        sql += " AND (n.name LIKE ? OR n.employee_code LIKE ? OR n.dmsid LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if position_code:
        sql += " AND n.position_code=?"
        params.append(position_code)
    if area_code:
        sql += " AND n.area_code=?"
        params.append(area_code)
    rows = _q(sql, tuple(params))
    if search and not position_code and not area_code:
        sx_rows = _q("""SELECT dmscode employee_code, code dmsid, name name
                         FROM dmssx_nhanvien WHERE name LIKE ? OR dmscode LIKE ? OR code LIKE ?""",
                     (f"%{search}%", f"%{search}%", f"%{search}%"))
        for r in sx_rows:
            r["position_code"] = None; r["position_label"] = None
            r["area_code"] = None; r["is_duplicate"] = 0
        rows += sx_rows
    rows.sort(key=lambda r: r["name"] or "")
    return rows[:limit]


def compare_periods(date_from_a: str, date_to_a: str, date_from_b: str, date_to_b: str,
                     scope_area_code: str = None, scope_channel: str = None) -> dict:
    """So sanh nhanh doanh thu giua 2 khoang thoi gian (vd thang nay vs thang truoc, cung ky nam truoc).
    Vi kho local co day du lich su (nhieu nam) nen so sanh xa duoc, khong chi vai ngay gan day."""
    a = revenue_by_channel(date_from_a, date_to_a, scope_area_code, scope_channel)
    b = revenue_by_channel(date_from_b, date_to_b, scope_area_code, scope_channel)
    delta = a["total"]["revenue"] - b["total"]["revenue"]
    pct_change = (delta / b["total"]["revenue"] * 100) if b["total"]["revenue"] else None
    return {"period_a": a, "period_b": b, "delta": delta, "pct_change": pct_change}


def _customer_receivable(customer_code: str, channel: str) -> dict:
    """Tra du no/qua han cua 1 khach tu KHO LOCAL fact_congno_khachhang - snapshot tuc thoi tu SP goc
    DNH usp_DeptAccDueDate_GetData (xem sync_warehouse.py::sync_fact_congno). Truoc 29/07/2026 doc tu
    2 bang Supabase receivable_detail/receivable_etc (Excel nhap tay 1 lan dau du an, mang dong doi
    cong thuc cu tung thoi no 1 khach len 9,17 ty trong khi that la 0,61 ty) - da BO nguon do.

    THAY DOI HANH VI CO CHU Y (so voi ban Supabase cu): khach co CA 2 kenh -> ban cu chi tra OTC;
    ban moi CONG CA HAI (mot dong = khach x kenh trong kho, nen SUM). channel loc pham vi: 'OTC' ->
    chi OTC, 'ETC' -> chi ETC, 'OTC+ETC'/None -> ca hai (giu dung channel-scoping cua customer_detail).

    Giu 5 khoa cu (balance_end, total_overdue, overdue_pct, receivable_status, receivable_warning) de
    KHONG phai sua nl2sql.py; them khoa moi khong pha tuong thich: receivable_as_of, receivable_source,
    va 4 bucket overdue_1_15/15_30/30_45/gt_45 (de tra loi "qua han bao lau").

    4 trang thai (receivable_status):
      - "unavailable": bang CHUA co du lieu (chua dong bo/SP loi) -> canh bao BAT BUOC "chua tra cuu
                       duoc", TUYET DOI khong noi "khach khong co no".
      - "ok" + canh bao moc thoi gian: snapshot cu > 6 gio.
      - "no_data": khach KHONG co dong nao -> "khong co du no tai thoi diem X theo bao cao cong no goc"
                   (dang tin cay vi nguon la SP goc, khac ban Supabase cu).
      - "ok": binh thuong, tra so + moc snapshot.
    """
    # 29/07/2026 (R-B da xu ly goc): GO canh bao "bang nhap tay CO THE SAI" cu - sau khi doi nguon
    # sang SP goc thi canh bao do thanh SAI SU THAT va lam mat uy tin tai demo.
    channels = []
    if "OTC" in channel:
        channels.append("OTC")
    if "ETC" in channel:
        channels.append("ETC")
    if not channels:
        channels = ["OTC", "ETC"]

    meta = _q("SELECT COUNT(*) n, MAX(snapshot_at) at FROM fact_congno_khachhang")
    total_rows = int(meta[0]["n"]) if meta else 0
    if total_rows == 0:
        _warn("Bang cong no (fact_congno_khachhang) CHUA co du lieu (chua dong bo hoac SP loi). PHAI "
              "tra loi 'chua tra cuu duoc cong no', TUYET DOI KHONG ket luan 'khach khong co no'.")
        return {"balance_end": None, "total_overdue": None, "overdue_pct": None,
                "receivable_status": "unavailable", "receivable_source": "bao cao cong no goc DNH (SP)",
                "receivable_as_of": None,
                "receivable_warning": (
                    "Chua tra cuu duoc cong no (kho cong no chua co du lieu tai thoi diem nay). PHAI "
                    "noi ro la 'chua tra cuu duoc', TUYET DOI KHONG ket luan khach khong co no.")}

    snapshot_at = meta[0]["at"]
    stale = False
    try:
        age_h = (dt.datetime.now() - dt.datetime.fromisoformat(snapshot_at)).total_seconds() / 3600.0
        stale = age_h > 6
    except Exception:
        pass

    ph = ",".join(["?"] * len(channels))
    r = _q(f"SELECT COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od, "
           f"COALESCE(SUM(overdue_1_15),0) b1, COALESCE(SUM(overdue_15_30),0) b2, "
           f"COALESCE(SUM(overdue_30_45),0) b3, COALESCE(SUM(overdue_gt_45),0) b4, COUNT(*) n "
           f"FROM fact_congno_khachhang WHERE customer_code=? AND sales_channel IN ({ph})",
           (customer_code, *channels))[0]

    if int(r["n"]) == 0:
        return {"balance_end": None, "total_overdue": None, "overdue_pct": None,
                "receivable_status": "no_data",
                "receivable_source": "bao cao cong no goc DNH (SP)", "receivable_as_of": snapshot_at,
                "receivable_warning": (
                    f"Khach {customer_code} KHONG co du no tai thoi diem {snapshot_at} theo bao cao "
                    "cong no goc cua DNH.")}

    balance, overdue = _f(r["bal"]), _f(r["od"])
    result = {"balance_end": balance, "total_overdue": overdue,
              "overdue_pct": (overdue / balance * 100) if balance else 0.0,
              "receivable_status": "ok",
              "receivable_source": "bao cao cong no goc DNH (SP)", "receivable_as_of": snapshot_at,
              "overdue_1_15": _f(r["b1"]), "overdue_15_30": _f(r["b2"]),
              "overdue_30_45": _f(r["b3"]), "overdue_gt_45": _f(r["b4"])}
    if stale:
        result["receivable_warning"] = (
            f"So cong no lay tu snapshot luc {snapshot_at} (da cu hon 6 gio) - nen luu y moc thoi gian "
            "khi tra loi.")
    return result


def customer_detail(customer_code: str, date_from: str, date_to: str, scope_area_code: str = None,
                     scope_channel: str = None) -> dict:
    """Chi tiet 1 khach hang: gop doanh thu thuc te (kho local, tu Bravo) + du no/qua han (Supabase) +
    mapping vung mien/NV phu trach (DMS_KhachHang + DIM_NhanVien). Doanh thu tinh trong [date_from,date_to],
    du no/qua han la SNAPSHOT KY GAN NHAT hien co (khong theo date_from/date_to).
    LUU Y: kenh ETC KHONG co NV phu trach truc tiep gan tren khach hang (chi OTC co qua EmpDMSCode1) -
    cot employee_code/employee_name/position_label se rong voi khach hang thuan ETC.
    scope_area_code: NEU co, xac dinh vung cua khach TRUOC KHI tra du lieu - tu choi neu khac vung
    (dung ca tien to ma KH lam fallback cho khach "mo coi" giong revenue_by_region).
    scope_channel: NEU co (vd 'OTC'), tu choi thang neu khach hang la khach THUAN kenh khac (khong co
    giao dich nao trong kenh duoc phep) - neu khach co CA 2 kenh, chi hien phan doanh thu cua kenh
    duoc phep (redact kenh kia ve 0, KHONG lo so lieu that)."""
    if scope_area_code:
        c = _q("""SELECT tp.area_code a FROM dms_khachhang kh
                  LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id WHERE kh.code=?
                  UNION ALL
                  SELECT tp.area_code a FROM dmssx_khachhang kh
                  LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id WHERE kh.code=?""",
                 (customer_code, customer_code))
        cust_area = next((r["a"] for r in c if r["a"]), None) or region_from_customer_code(customer_code)
        if cust_area != scope_area_code:
            return {"error": f"Ban khong co quyen xem khach hang nay - ngoai vung {scope_area_code} ban phu trach."}
    o = _q("SELECT COALESCE(SUM(amount9),0) rev, COUNT(DISTINCT stt) hd FROM vhoadon_otc "
           "WHERE customer_code=? AND doc_date BETWEEN ? AND ?", (customer_code, date_from, date_to))[0]
    e = _q("SELECT COALESCE(SUM(amount9),0) rev, COUNT(DISTINCT stt) hd FROM vhoadon_etc "
           "WHERE customer_code=? AND doc_date BETWEEN ? AND ?", (customer_code, date_from, date_to))[0]
    real_otc_hd, real_etc_hd = int(o["hd"]), int(e["hd"])
    if scope_channel == "OTC" and real_otc_hd == 0 and real_etc_hd > 0:
        return {"error": f"Ban khong co quyen xem khach hang nay - day la khach hang kenh ETC, tai khoan cua ban chi duoc xem kenh {scope_channel}."}
    otc_rev, otc_hd = _f(o["rev"]), real_otc_hd
    etc_rev, etc_hd = (0.0, 0) if scope_channel == "OTC" else (_f(e["rev"]), real_etc_hd)

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
            nv = _q(f"SELECT name, position_code FROM dim_nhanvien WHERE employee_code=? AND {_not_duplicate_sql('')}",
                    (emp_code,))
            if nv:
                emp_name = nv[0]["name"]; position_code = nv[0]["position_code"]
                cv = _q("SELECT description FROM dim_chucvu WHERE position_code=? LIMIT 1", (position_code,))
                position_label = cv[0]["description"] if cv else position_code

    receivable = _customer_receivable(customer_code, channel or lookup_src)

    result = {
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
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac (neu co) KHONG duoc hien thi."
    return result


def order_timing_check(date_from: str, date_to: str, threshold_days: int = 2, limit: int = 20,
                        scope_area_code: str = None, scope_channel: str = None) -> dict:
    """Phat hien dau hieu 'chay don don KPI': hoa don co created_at (thoi diem BAN GHI THUC SU duoc
    tao trong Bravo) lech qua xa so voi doc_date (ngay chung tu tren hoa don, co the bi chon tay).
    Vd: doc_date la cuoi thang truoc nhung created_at lai la dau thang sau -> dau hieu tao/sua don
    backdate de kip chi tieu KPI thang truoc. threshold_days: so ngay lech toi thieu de bi liet ke
    (mac dinh 2). Tra ve ca TOM TAT theo tung nhan vien (ai co nhieu don bat thuong nhat) LAN danh
    sach chi tiet top nhung don lech nhieu nhat. scope_area_code: ep loc theo vung khi bi gioi han.
    scope_channel: NEU co (vd 'OTC'), BO HAN kenh con lai khoi truy van (khong chi redact ket qua)."""
    scope_sql, scope_params = _scope_clause(scope_area_code)
    join_o = _otc_area_join("v", scope_area_code)
    parts = [f"""SELECT v.doc_date, v.created_at, v.customer_code, v.employee_code, v.amount9, v.stt
            FROM vhoadon_otc v {join_o} WHERE v.doc_date BETWEEN ? AND ? AND v.created_at IS NOT NULL{scope_sql}"""]
    part_params = [(date_from, date_to) + scope_params]
    if scope_channel != "OTC":
        join_e = _etc_area_join("v", scope_area_code)
        parts.append(f"""SELECT v.doc_date, v.created_at, v.customer_code, v.employee_code, v.amount9, v.stt
            FROM vhoadon_etc v {join_e} WHERE v.doc_date BETWEEN ? AND ? AND v.created_at IS NOT NULL{scope_sql}""")
        part_params.append((date_from, date_to) + scope_params)
    sql = f"""
        SELECT doc_date, created_at, customer_code, employee_code, amount9, stt,
               CAST(julianday(created_at) - julianday(doc_date) AS INTEGER) AS lech_ngay
        FROM ({" UNION ALL ".join(parts)})
        WHERE ABS(CAST(julianday(created_at) - julianday(doc_date) AS INTEGER)) >= ?
        ORDER BY ABS(lech_ngay) DESC
    """
    params = tuple(p for pp in part_params for p in pp) + (threshold_days,)
    rows = _q(sql, params)

    for r in rows:
        r["amount9"] = _f(r["amount9"])
        # Bao cao chong gian lan: LAY TEN DU is_duplicate=1 (khac cac tool khac) - muc dich la minh
        # bach danh tinh, khong nen an ten chi vi 1 co du lieu khong lien quan.
        # r["employee_code"] o day la gia tri THO tren hoa don = DMSId (KHONG PHAI EmployeeCode -
        # da xac minh 17/07/2026, xem ghi chu trong employee_daily_kpi()) - tra qua
        # _resolve_employee_identity() (thu dim_nhanvien truoc, roi dmssx_nhanvien - xac nhan
        # 20/07/2026 mot nhom nhan vien chi co o bang do), sau do gan lai employee_code THAT.
        ident = _resolve_employee_identity(r["employee_code"])
        r["employee_name"] = ident["name"]
        r["position_code"] = ident["position_code"]
        if ident["name"]:
            r["employee_code"] = ident["code"]

    by_employee = {}
    for r in rows:
        key = r["employee_code"] or "(khong xac dinh)"
        if key not in by_employee:
            by_employee[key] = {"employee_code": key, "employee_name": r["employee_name"],
                                 "position_code": r["position_code"], "count": 0, "total_amount": 0.0}
        by_employee[key]["count"] += 1
        by_employee[key]["total_amount"] += r["amount9"]
    summary = sorted(by_employee.values(), key=lambda x: -x["count"])

    result = {
        "date_from": date_from, "date_to": date_to, "threshold_days": threshold_days,
        "total_flagged": len(rows),
        "summary_by_employee": summary,
        "top_detail": rows[:limit],
        "data_as_of": latest_data_date(),
    }
    # Du lieu cu hon 12 thang da bi NEN thanh KH x thang (khong con created_at tung dong) - tool nay
    # KHONG the phat hien "chay don don KPI" cho giai doan cu hon, phai bao ro thay vi am tham thieu.
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        result["warning"] = (f"Cau hoi vuot qua cua so 12 thang gan nhat (truoc {cutoff}) - du lieu "
                              f"created_at tung hoa don cho giai doan cu hon KHONG con duoc luu (da nen "
                              f"thanh tong theo khach hang/thang). Ket qua tren CHI kiem tra duoc tu "
                              f"{max(date_from, cutoff)} tro di, KHONG dai dien cho toan bo khoang thoi "
                              f"gian da hoi.")
        result["date_from_actually_used"] = max(date_from, cutoff)
    return result


_AREA_TO_BRANCH = {"MB": "B02", "MT": "B03", "MN": "B04"}
_BRANCH_LABEL = {"B01": "Sản xuất", "B02": "Kinh doanh Miền Bắc",
                 "B03": "Kinh doanh Miền Trung", "B04": "Kinh doanh Miền Nam"}


def inventory_by_region(area_code: str = None, scope_area_code: str = None) -> list:
    """Ton kho (so luong + gia tri) theo vung, tu Bravo qua brv_tonkhodk/brv_kho/brv_sanpham - THAY
    THE nguon Supabase cu (bang inventory co cot warehouse nhung 100% NULL, khong loc vung duoc).
    area_code: 'MB'/'MT'/'MN' - tuy chon, khong truyen se tra ve CA 4 vung (gom ca B01 San xuat).
    scope_area_code: EP GHI DE area_code khi tai khoan bi gioi han vung (giong cac ham khac) - vi
    B01 (San xuat) khong thuoc vung MB/MT/MN nao nen KHONG BAO GIO hien voi tai khoan bi gioi han."""
    if scope_area_code:
        area_code = scope_area_code
    branch_filter = _AREA_TO_BRANCH.get(area_code) if area_code else None
    sql = """SELECT k.branch_code area_code, COUNT(DISTINCT t.item_id) so_mat_hang,
                    SUM(t.quantity) tong_so_luong, SUM(t.amount) tong_gia_tri
             FROM brv_tonkhodk t LEFT JOIN brv_kho k ON k.id_code = t.warehouse_id
             WHERE t.is_active = 1"""
    params = []
    if branch_filter:
        sql += " AND k.branch_code = ?"
        params.append(branch_filter)
    elif scope_area_code:
        # scope_area_code duoc set nhung khong map duoc sang branch (khong nen xay ra voi MB/MT/MN
        # hop le) - an toan hon la khong tra ve gi thay vi lo het ca 4 vung.
        return []
    sql += " GROUP BY k.branch_code ORDER BY k.branch_code"
    rows = _q(sql, tuple(params))
    for r in rows:
        r["area_label"] = _BRANCH_LABEL.get(r["area_code"], r["area_code"])
        r["tong_so_luong"] = _f(r["tong_so_luong"])
        r["tong_gia_tri"] = _f(r["tong_gia_tri"])
    return rows


# area_code (MB/MB2/MN/MT) -> ten mien tieng Viet, gom MB+MB2 thanh Mien Bac (theo REGION_SQL_MARKERS).
_AREA_TO_REGION_VI = {m: REGION_NAMES_VI[key] for key, ms in REGION_SQL_MARKERS.items() for m in ms}


def receivables_overview(top_n: int = 10, scope_area_code: str = None) -> dict:
    """Tong quan CONG NO tu kho local fact_congno_khachhang (snapshot tuc thoi tu SP goc DNH
    usp_DeptAccDueDate_GetData): tong du no, tong qua han, ty le qua han, tach theo KENH (OTC/ETC)
    va theo VUNG, top N khach no qua han nhieu nhat.

    MOT DONG = (khach x kenh) nen luon SUM. scope_area_code: EP LOC theo vung khi tai khoan bi gioi
    han (regional_director/qlv) - dung REGION_SQL_MARKERS de gom ca MB va MB2 cho mien Bac.

    4 trang thai giong _customer_receivable:
      - unavailable: bang chua co du lieu -> canh bao BAT BUOC, khong ket luan "khong co no".
      - ok + canh bao moc thoi gian: snapshot cu > 6 gio.
      - ok: binh thuong.
    (khong co trang thai no_data rieng: neu co du lieu ma vung nay = 0 thi cac tong = 0, van la 'ok'.)
    """
    meta = _q("SELECT COUNT(*) n, MAX(snapshot_at) at FROM fact_congno_khachhang")
    total_rows = int(meta[0]["n"]) if meta else 0
    if total_rows == 0:
        _warn("Bang cong no (fact_congno_khachhang) CHUA co du lieu (chua dong bo hoac SP loi). PHAI "
              "tra loi 'chua tra cuu duoc cong no', TUYET DOI KHONG ket luan 'khong co no'.")
        return {"receivable_status": "unavailable", "receivable_as_of": None,
                "receivable_source": "bao cao cong no goc DNH (SP)",
                "receivable_warning": (
                    "Chua tra cuu duoc cong no (kho cong no chua co du lieu tai thoi diem nay).")}

    snapshot_at = meta[0]["at"]
    # Loc vung: gom cac ma area cua mien (MB -> MB,MB2). Khong scope -> tra toan cong ty.
    where, params = "", []
    if scope_area_code:
        region_key = next((k for k, ms in REGION_SQL_MARKERS.items() if scope_area_code in ms), None)
        markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code])
        where = f"WHERE area_code IN ({','.join(['?'] * len(markers))})"
        params = list(markers)

    tot = _q(f"SELECT COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od, "
             f"COALESCE(SUM(overdue_1_15),0) b1, COALESCE(SUM(overdue_15_30),0) b2, "
             f"COALESCE(SUM(overdue_30_45),0) b3, COALESCE(SUM(overdue_gt_45),0) b4 "
             f"FROM fact_congno_khachhang {where}", tuple(params))[0]
    total_balance, total_overdue = _f(tot["bal"]), _f(tot["od"])

    by_channel = _q(f"SELECT sales_channel, COALESCE(SUM(balance_end),0) bal, "
                    f"COALESCE(SUM(total_overdue),0) od FROM fact_congno_khachhang {where} "
                    f"GROUP BY sales_channel", tuple(params))
    channels = [{"channel": r["sales_channel"], "balance_end": _f(r["bal"]),
                 "total_overdue": _f(r["od"]),
                 "overdue_pct": (_f(r["od"]) / _f(r["bal"]) * 100) if _f(r["bal"]) else 0.0}
                for r in by_channel]

    regions = []
    if not scope_area_code:  # scope roi thi chi con 1 vung, khong can tach
        by_area = _q("SELECT area_code, COALESCE(SUM(balance_end),0) bal, "
                     "COALESCE(SUM(total_overdue),0) od FROM fact_congno_khachhang "
                     "GROUP BY area_code")
        agg = {}
        for r in by_area:
            label = _AREA_TO_REGION_VI.get(r["area_code"], "Khac/chua xac dinh")
            b, o = agg.get(label, (0.0, 0.0))
            agg[label] = (b + _f(r["bal"]), o + _f(r["od"]))
        regions = [{"region": lbl, "balance_end": b, "total_overdue": o,
                    "overdue_pct": (o / b * 100) if b else 0.0}
                   for lbl, (b, o) in sorted(agg.items(), key=lambda x: -x[1][1])]

    top = _q(f"SELECT customer_code, MAX(customer_name) name, "
             f"COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od "
             f"FROM fact_congno_khachhang {where} GROUP BY customer_code "
             f"HAVING SUM(total_overdue) > 0 ORDER BY SUM(total_overdue) DESC LIMIT ?",
             tuple(params) + (int(top_n),))
    top_customers = [{"customer_code": r["customer_code"], "customer_name": r["name"],
                      "balance_end": _f(r["bal"]), "total_overdue": _f(r["od"])} for r in top]

    result = {
        "receivable_status": "ok",
        "receivable_source": "bao cao cong no goc DNH (SP)",
        "receivable_as_of": snapshot_at,
        "scope_area_code": scope_area_code,
        "total_balance_end": total_balance,
        "total_overdue": total_overdue,
        "overdue_pct": (total_overdue / total_balance * 100) if total_balance else 0.0,
        "overdue_1_15": _f(tot["b1"]), "overdue_15_30": _f(tot["b2"]),
        "overdue_30_45": _f(tot["b3"]), "overdue_gt_45": _f(tot["b4"]),
        "by_channel": channels,
        "by_region": regions,
        "top_overdue_customers": top_customers,
    }
    try:
        age_h = (dt.datetime.now() - dt.datetime.fromisoformat(snapshot_at)).total_seconds() / 3600.0
        if age_h > 6:
            result["receivable_warning"] = (
                f"So cong no lay tu snapshot luc {snapshot_at} (da cu hon 6 gio) - luu y moc thoi gian.")
    except Exception:
        pass
    if scope_area_code:
        result["scope_note"] = f"(chi vung {scope_area_code})"
    return result


# 29/07/2026 — GOP THEO THANG, khong ghim MOT save_date.
#
# Vi sao: DNH KHONG ghi snapshot thang thanh mot lan. Xac nhan tren Bravo 29/07/2026 - thang 7 co 2
# snapshot, moi cai chua mot phan vung:
#     save_date 2026-07-27 -> MB (102 NV) + MN (48 NV), KHONG co MT
#     save_date 2026-07-28 -> CHI co MT (34 NV)
# Ghim vao MAX(save_date) nhu truoc => ngay 29/07 chi thay MT, bao "toan doi 48,7%" trong khi thuc
# chat la rieng Mien Trung - hut MB 30,78 ty va MN 13,19 ty. So tron tru, tu tin, va sai ca mot bac
# do lon. Cac thang da dong (31/05, 30/06...) chi co 1 snapshot tron ven nen loi chi lo GIUA THANG.
#
# Cach gop: trong THANG cua fdate, moi nhan vien lay save_date moi nhat cua CHINH ho. Kiem chung
# 29/07/2026 tren Bravo: tong chi tieu ra dung 50.967.586.921d (MB 30.781.764.408 · MN 13.185.822.513
# · MT 7.000.000.000) - khop tung dong voi gia tri da verify, va khoi phuc du ca 3 mien.
# LUON truyen tham so theo thu tu (fdate, fdate).
_MONTH_LATEST_SUBQ = """(SELECT employee_code, MAX(save_date) d FROM fact_tonghopkhachhang
                          WHERE save_date<=? AND substr(save_date,1,7)=substr(?,1,7)
                          GROUP BY employee_code)"""


def _kpi_snapshot(employee_code: str, fdate: str, position_code: str = None):
    """Sales/target/pct cua 1 nhan vien (QLV/TDV deu dung duoc) trong THANG cua fdate -
    fact_tonghopkhachhang da tinh san rollup cho ca cap QLV (Bravo tu tong hop), khong can tu cong
    tay tu doanh thu TDV.
    position_code: BAT BUOC truyen khi da biet vai tro - nguong THUONG khac nhau (TDV 65% / quan ly
    70%), de trong se cham nham cap quan ly o nguong TDV. (Moc DAT KPI 80% thi chung moi vai tro.)"""
    r = _q(f"SELECT SUM(f.amount_ct) sales, MAX(f.month_sale_target) target "
           f"FROM fact_tonghopkhachhang f "
           f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=f.employee_code AND l.d=f.save_date "
           f"WHERE f.employee_code=?", (fdate, fdate, employee_code))
    sales = _f(r[0]["sales"]) if r else 0.0
    target = _f(r[0]["target"]) if r else 0.0
    pct = (sales / target * 100) if target else 0.0
    return {"sales": sales, "target": target, "pct": pct,
            "threshold": _bonus_threshold(position_code),      # cong thuong nhom hang (65/70)
            "kpi_threshold": KPI_ACHIEVED_THRESHOLD,           # dat KPI (80, chung moi vai tro)
            "meets_kpi": pct >= KPI_ACHIEVED_THRESHOLD,
            "status": _kpi_status(pct, position_code)}



def _fact_latest_date() -> str:
    r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang")
    return r[0]["d"] if r and r[0]["d"] else None


def _team_of_qlv(qlv_employee_code: str, fdate: str = None) -> list:
    """TDV bao cao TRUC TIEP len 1 QLV, xac dinh qua manager_code THAT tu Bravo
    (FACT_TongHopKhachHang.ManagerCode, dong bo 23/07/2026 - xem local_warehouse.py::SCHEMA).
    THAY THE org_hierarchy.team_of_qlv() (suy luan qua ma khu vuc) cho MOI cho can biet "doi cua 1
    QLV de gioi han quyen xem/tong hop KPI" - suy luan zone KEM CHINH XAC hon nhieu (~30% khu vuc
    khong map duoc QLV, xem qlv_change_history()), phat hien qua kiem chung thuc te 23/07/2026: 5 QLV
    bi hieu nham la "khong co doi" trong khi 4/5 nguoi co that 6-8 TDV, lam KPI vung Mien Trung bi
    CONG TRUNG doanh so ca doi ho (11,82 ty thay vi 6,79 ty that). manager_code la CUNG mot nguon ma
    repo bao cao D:\\DNH dang dung (src/alerts.py::get_bravo_kpi_tdv_snapshot) - 2 he thong gio xac
    dinh "doi" giong het nhau.
    org_hierarchy.py (zone-based) VAN con dung rieng cho qlv_change_history() - do la lich su AI TUNG
    phu trach 1 khu vuc theo thoi gian, ban chat khac voi "doi hien tai bao cao len ai"."""
    if fdate is None:
        fdate = _fact_latest_date()
    if not fdate:
        return []
    return _q(
        f"SELECT DISTINCT e.employee_code, nv.name FROM fact_tonghopkhachhang e "
        f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=e.employee_code AND l.d=e.save_date "
        f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code "
        f"WHERE e.manager_code=? AND nv.position_code='TDV'", (fdate, fdate, qlv_employee_code))


def qlv_change_history(area_code: str = None, qlv_search: str = None, scope_area_code: str = None) -> list:
    """Lich su ai tung/dang phu trach tung 'to' (zone noi bo V01-V22) - CHI suy luan duoc tu quy uoc
    dat ten (xem org_hierarchy.py), KHONG phai du lieu audit chinh thuc (Bravo khong co bang lich su
    thay doi nhan su). area_code: loc theo vung MB/MT/MN (hien tat ca to trong vung). qlv_search: tim
    theo ten/ma 1 QLV de xem lich su dung to cua ho. scope_area_code: ep gioi han vung khi tai khoan
    bi han che. LUU Y: ~30% so to KHONG suy luan duoc QLV hien tai qua cach nay (se ghi "Chua xac
    dinh") - day la han che that cua du lieu, KHONG duoc tu suy doan de lap day."""
    if scope_area_code:
        area_code = scope_area_code
    status = oh.all_zones_with_qlv_status()

    target_zones = None
    if qlv_search:
        matches = _q("SELECT employee_code FROM dim_nhanvien WHERE (name LIKE ? OR employee_code LIKE ?) "
                      "AND position_code='QLV'", (f"%{qlv_search}%", f"%{qlv_search}%"))
        target_zones = set()
        for m in matches:
            target_zones.update(oh.qlv_zones(m["employee_code"]))
        if not target_zones:
            return []

    result = []
    for z in status:
        zone = z["zone"]
        if target_zones is not None and zone not in target_zones:
            continue
        if area_code:
            zone_area = _q("SELECT area_code FROM dim_nhanvien WHERE manager_area_code=? AND area_code IS NOT NULL LIMIT 1", (zone,))
            if not zone_area or zone_area[0]["area_code"] != area_code:
                continue
        history = oh.qlv_history_for_zone(zone)
        result.append({"zone": zone, "current_qlv": z["qlv_name"], "history": history})
    return result


def revenue_tree(as_of_date: str = None, area_code: str = None, scope_area_code: str = None,
                  scope_employee_code: str = None) -> dict:
    """Cay doanh thu/KPI 3 cap: Truong phong (TP) -> QLV -> TDV, dung snapshot KPI da co san trong
    fact_tonghopkhachhang (Bravo tu tong hop rollup cho ca cap QLV, khong can tu cong tay). area_code:
    loc theo 1 vung MB/MT/MN (khuyen khich dung khi hoi ca cong ty vi cay day du RAT dai). scope_area_code:
    ep gioi han vung khi tai khoan bi han che. scope_employee_code: CHI danh cho qlv - ep chi tra ve
    DUNG 1 QLV nay (khong thay cac QLV khac cung vung) vi day la du lieu hieu suat CA NHAN dong nghiep,
    nhay cam hon so lieu tong hop thong thuong. Cac 'to' KHONG xac dinh duoc QLV (xem org_hierarchy.py)
    se KHONG xuat hien duoi bat ky TP nao - can luu y khi doc ket qua co the thieu 1 vai to.
    LUU Y QUAN TRONG: cap TP hien LUON co sales/target/pct = 0 (Bravo khong tracking target ca nhan
    cho TP trong fact_tonghopkhachhang) - khi tra loi PHAI noi ro so 0 nay la "chua co du lieu target
    rieng cho TP", TUYET DOI KHONG bao la TP "khong dat KPI"/0% - do la thong tin sai lech nghiem trong.
    Muon biet tong doanh thu THAT cua ca vung TP phu trach, cong don sales cua tat ca QLV ben duoi
    (hoac dung get_revenue_by_region cho doanh thu hoa don thuc te, khac voi so KPI o day).

    27/07/2026 - DONG BO voi kpi_ranking()/_rollup_tier_codes(): truoc day danh sach "QLV" duoi moi TP
    loc truc tiep position_code='QLV' AND is_duplicate<>1, BO SOT cac NHOM/KENH nhu 'Kênh MT'/'Chợ sỉ'
    (Mien Nam - IsDuplicate=1 vi Bravo gan trung ma, khong phai QLV that bi trung). Hau qua THUC TE: cay
    QLV/TDV cua Mien Nam ra 3,50 ty trong khi tong vung (get_revenue_by_region) la 6,25 ty - nguoi dung
    phai HOI LAI "con thieu gi" moi duoc bao thieu Kenh MT (2,73 ty) + Cho si (0,15 ty). Gio dung CHUNG
    _rollup_tier_codes(fdate) (theo manager_code THAT) lam nguon danh sach QLV, giong het kpi_ranking -
    2 tool nay LUON phai ra cung tong 1 vung, khong con truong hop tong khop nhung bóc tach le."""
    if scope_area_code:
        area_code = scope_area_code
    if as_of_date is None:
        as_of_date = str(dt.date.today())
    fdate_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?", (as_of_date,))
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return {"as_of": None, "tree": []}

    tp_sql = ("SELECT employee_code, name, area_code FROM dim_nhanvien WHERE position_code='TP' "
              f"AND end_date IS NULL AND COALESCE(is_resigned,0)<>1 AND {_not_duplicate_sql('')}")
    tp_params = ()
    if area_code:
        tp_sql += " AND area_code=?"
        tp_params = (area_code,)
    tp_rows = _q(tp_sql, tp_params)

    # Danh sach "QLV" (bao gom ca nhom/kenh nhu Kenh MT/Cho si) - CUNG nguon voi kpi_ranking() de 2
    # tool khong bao gio lech nhau. Cac ban ghi nhom/kenh KHONG co manager_code tro len TP (chung la
    # tang rollup doc lap, khong bao cao ai) nen gan theo area_code cua chinh ban ghi do thay vi cho
    # doi chieu qua manager_code nhu QLV that.
    managers = _rollup_tier_codes(fdate)
    qlv_all = []
    if managers:
        ph = ",".join(["?"] * len(managers))
        qlv_all = _q(f"SELECT employee_code, name, area_code, COALESCE(is_duplicate,0) dup "
                     f"FROM dim_nhanvien WHERE employee_code IN ({ph})", tuple(managers))

    tree = []
    for tp in tp_rows:
        tp_kpi = _kpi_snapshot(tp["employee_code"], fdate, "TP")
        qlv_rows = [q for q in qlv_all if q["area_code"] == tp["area_code"]]
        if scope_employee_code:
            qlv_rows = [q for q in qlv_rows if q["employee_code"] == scope_employee_code]
        qlv_rows = sorted(qlv_rows, key=lambda q: q["name"] or "")
        qlv_list = []
        for qlv in qlv_rows:
            q_kpi = _kpi_snapshot(qlv["employee_code"], fdate, "QLV")
            is_unit = (int(qlv["dup"] or 0) == 1
                       and qlv["employee_code"] not in _KNOWN_MISFLAGGED_DUPLICATE_CODES)
            team = [] if is_unit else _team_of_qlv(qlv["employee_code"], fdate)
            tdv_list = []
            for t in team:
                # _team_of_qlv da loc san position_code='TDV' nen o day chac chan la TDV (nguong 65%).
                t_kpi = _kpi_snapshot(t["employee_code"], fdate, "TDV")
                tdv_list.append({"employee_code": t["employee_code"], "name": t["name"], **t_kpi})
            qlv_entry = {"employee_code": qlv["employee_code"], "name": qlv["name"], **q_kpi,
                         "tdv_count": len(tdv_list), "tdv": tdv_list, "la_nhom_kenh": is_unit}
            if is_unit:
                qlv_entry["ghi_chu"] = (f"'{qlv['name']}' la NHOM/KENH ban hang (khong phai mot ca "
                                        "nhan/khong co doi TDV rieng) - khi tra loi phai goi dung la "
                                        "kenh/nhom, KHONG duoc noi nhu mot QLV thong thuong.")
            qlv_list.append(qlv_entry)
        tree.append({"employee_code": tp["employee_code"], "name": tp["name"], "area_code": tp["area_code"],
                      **tp_kpi, "qlv_count": len(qlv_list), "qlv": qlv_list})
    return {"as_of": fdate, "tree": tree}


def _rollup_tier_codes(fdate: str) -> list:
    """Ma cua TANG ROLLUP tai snapshot fdate = nhung nguoi CO quan ly nguoi khac (xuat hien o cot
    manager_code). CO Y khong loc position_code lan is_duplicate - ca hai deu sai nhan tren Bravo:
    cap duoi cua 'Kenh MT'/'Cho si' mang chuc danh TK/CS, va 4 QLV that bi gan co trung lap. Loc
    theo 2 truong do lam bay hoi ca QLV that khoi bao cao (da tung mat 7,93 ty chi tieu Mien Nam).

    Dung CHUNG cho ca group_by='region' va group_by='qlv' de 2 nhanh LUON khop nhau - nguoi dung
    cong tay danh sach QLV phai ra dung tong vung. Cung quy tac voi bao cao email ben D:/DNH
    (src/alerts.py::get_bravo_manager_codes) de 2 he thong khong bao gio lech.
    """
    return [m["manager_code"] for m in _q(
        "SELECT DISTINCT manager_code FROM fact_tonghopkhachhang "
        "WHERE save_date<=? AND substr(save_date,1,7)=substr(?,1,7) "
        "AND manager_code IS NOT NULL AND manager_code<>''", (fdate, fdate))]


def _warn_region_target_mismatch(rows: list, fdate: str, tolerance_pct: float = 0.5) -> None:
    """CHOT AN TOAN 2 cho KPI theo vung: doi chieu tong target vua gop (tu fact_tonghopkhachhang,
    tang rollup QLV) voi bang dim_targetvungmien - chi tieu vung CHINH THUC do DNH dat top-down.

    Day la LUOI AN TOAN DOC LAP: 2 nguon hoan toan khac nhau (mot ben cong tu tung nhan vien, mot ben
    la con so cong ty cong bo). Binh thuong chung khop tuyet doi (kiem chung 27/07/2026: MB
    30.781.764.408 | MN 13.185.822.513 | MT 7.000.000.000 - khop ca 3 mien voi bao cao goc). Neu lech
    qua nguong -> cau truc du lieu Bravo da doi (them tang, doi cach gan manager_code, them kenh moi...)
    va cach gop dang dung KHONG con dung nua. Canh bao de nguoi doc biet, thay vi am tham tra so sai -
    dung bai hoc tu chinh lo nay: so sai suot nhieu ngay ma khong ai phat hien vi khong co doi chieu.

    Chi CANH BAO, khong sua so: nguoi dung van thay du lieu, kem loi nhac kiem tra lai.
    """
    if not rows or not fdate:
        return
    ym = str(fdate)[:7]
    official = {r["area_code"]: _f(r["amount"]) for r in _q(
        "SELECT area_code, SUM(amount) amount FROM dim_targetvungmien "
        "WHERE substr(doc_date,1,7)=? GROUP BY area_code", (ym,))}
    if not official:
        return  # chua dong bo bang target vung - khong the doi chieu, khong canh bao bua
    for r in rows:
        ref = official.get(r["area_code"])
        if not ref or not r["target"]:
            continue
        diff_pct = abs(r["target"] - ref) / ref * 100
        if diff_pct > tolerance_pct:
            _warn(f"DOI CHIEU LECH ({r['area_code']}): tong chi tieu gop tu nhan vien "
                  f"{r['target']:,.0f}d vs chi tieu vung chinh thuc (dim_targetvungmien) {ref:,.0f}d "
                  f"- lech {diff_pct:.1f}%. Cau truc du lieu co the da doi; PHAI noi ro con so dang "
                  f"can doi chieu lai, KHONG khang dinh chac chan voi nguoi dung.")

    # 29/07/2026 - VA DIEM MU: vong lap tren chi duyet cac vung CO MAT trong rows, nen vung BIEN MAT
    # HOAN TOAN khoi snapshot thi khong co dong nao de kiem -> khong canh bao gi ca.
    # Da xay ra that: DNH ghi snapshot thang 7 TACH LAM 2 NGAY theo vung (SaveDate 27/07 co MB+MN,
    # SaveDate 28/07 CHI co MT). Vi ca bao cao lan chatbot deu ghim vao MOT save_date, cau hoi KPI
    # ngay 29/07 chi thay MT va bao "TOAN DOI 48,7%" - thuc chat la rieng Mien Trung, hut MB 30,78 ty
    # va MN 13,19 ty. Khong he co canh bao vi MT doi chieu voi dim_targetvungmien van khop.
    # Day la loai sai NGUY HIEM NHAT: so tron tru, tu tin, va sai ca mot bac do lon.
    missing = [a for a in official if a not in {r["area_code"] for r in rows}]
    if missing:
        hut = sum(official[a] for a in missing)
        _warn(f"THIEU VUNG trong snapshot {fdate}: {', '.join(sorted(missing))} khong co dong nao "
              f"(chi tieu vung chinh thuc: {hut:,.0f}d). Con so 'toan doi' duoi day CHI gom cac vung "
              f"con lai, KHONG phai toan cong ty - TUYET DOI khong trinh bay nhu so toan quoc. "
              f"Nguyen nhan thuong gap: snapshot thang dang duoc ghi do dang, moi vung ghi mot ngay "
              f"khac nhau. Hoi lai vao thang da tron (vd cuoi thang) de co so day du.")


def kpi_ranking(group_by: str = "qlv", as_of_date: str = None, limit: int = 20,
                 scope_area_code: str = None, scope_employee_code: str = None) -> list:
    """Xep hang KPI (% dat target) giua cac QLV hoac giua cac vung, TOT NHAT truoc. group_by: 'qlv'
    (xep hang tung QLV, dung khi hoi 'QLV nao dat KPI tot nhat') hoac 'region' (gop theo vung
    MB/MT/MN, dung khi hoi 'vung nao dat KPI tot nhat'). scope_area_code: ep gioi han vung
    khi tai khoan bi han che - voi group_by='region' se chi con 1 dong (vung cua chinh ho). scope_employee_code:
    CHI danh cho qlv - voi group_by='qlv' se chi tra ve DUNG 1 dong (chinh ho), khong xep hang so sanh
    voi cac QLV khac (du lieu hieu suat CA NHAN dong nghiep, khong duoc xem).

    group_by='region' gop o TANG ROLLUP QLV (moi QLV da bao gom doi cua ho + chi tieu ca nhan cua
    chinh ho) - KHOP TUYET DOI voi bao cao goc "Tien do doanh so thang theo NVKD" cua DNH va bang
    chi tieu vung DIM_TargetVungMien. KHONG cong them tang TDV vao (se gap doi). Xem ghi chu chi tiet
    trong than ham va _warn_region_target_mismatch()."""
    fdate_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?",
                 (as_of_date or str(dt.date.today()),))
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return []

    if group_by == "region":
        # QUAN TRONG: phai gom ve 1 dong/nhan vien TRUOC (SUM(amount_ct), MAX(target) - target lap
        # lai moi dong theo khach hang) roi moi SUM tiep theo vung - neu SUM(target) truc tiep tren
        # fact_tonghopkhachhang se dem target trung nhieu lan (1 lan/khach hang cua nhan vien do),
        # thoi phong target sai hang chuc lan, lam % KPI vung bi tinh sai (qua thap).
        #
        # 27/07/2026 - DOI TU "TANG LA" SANG "TANG ROLLUP QLV". Ly do (da kiem chung tren Bravo that,
        # doi chieu bao cao goc "Tien do doanh so thang theo NVKD" thang 7 va bang DIM_TargetVungMien):
        #
        #   Tang la KHONG THE dem du target, du co va bao nhieu lan. Co nhung nguoi CO chi tieu nhung
        #   KHONG co dong nao trong fact_tonghopkhachhang (khong duoc giao khach nao) - vd 2 dong tu
        #   than QLV o MB tong 626.173.042d. Bang fact chi co dong theo TUNG KHACH HANG, nen nguoi
        #   khong co khach thi vo hinh voi moi cach gop tu duoi len. Rollup cua QLV da bao gom san
        #   phan chi tieu ca nhan nay (kiem chung: target rollup tungtx 3.016.493.346 = tong 10 TDV
        #   duoi quyen 2.756.994.289 + chi tieu tu than 259.499.057).
        #
        #   Doi chieu thuc te 27/07/2026 (target ca thang):
        #     tang la (ban cu)  : MB 23,75 ty | MN  5,26 ty | MT 6,79 ty  -> lech bao cao goc rat lon
        #     tang rollup (nay) : MB 30,78 ty | MN 13,19 ty | MT 7,00 ty  -> KHOP TUYET DOI ca 3 mien
        #   Hau qua cua ban cu: Mien Nam bi thieu 7,93 ty mau so -> nhay len 61% va DUNG HANG 1 trong
        #   khi bao cao goc xep hang 2 (47,3%, sau MB 48,9%) - sai ca con so lan THU HANG.
        #
        # Tang rollup duoc xac dinh bang MANAGER_CODE (quan he du lieu THAT), CO Y khong dung
        # position_code lan is_duplicate - CA HAI DEU SAI NHAN tren Bravo va da tung gay dung lo nay:
        #   - position_code: Duong Thi Hong Hue (Modern Trade, target 5,29 ty) mang chuc danh 'TK',
        #     Dang Truong Lol (Cho si, 1,5 ty) mang 'CS' -> loc 'TDV' lam bay hoi 6,79 ty cua MN.
        #   - is_duplicate: 4 QLV THAT bi Bravo gan co trung lap (MN1 Kenh MT 5,29 ty, MN4 Cho si
        #     1,5 ty, MBKV12 5,28 ty, TM25030101 Lac Ngoc Sam 0,935 ty). Danh sach mien tru tay
        #     _KNOWN_MISFLAGGED_DUPLICATE_CODES chi liet ke duoc 2/4 - va se lai thieu khi DNH them
        #     kenh moi. Gop theo manager_code khong phu thuoc nhan nen khong con phai va tiep.
        managers = _rollup_tier_codes(fdate)
        if not managers:
            _warn("Khong xac dinh duoc tang quan ly (manager_code rong) nen KHONG tinh duoc KPI theo "
                  "vung. PHAI noi ro la chua tra cuu duoc, KHONG duoc tra ve 0 nhu the la khong dat.")
            return []
        ph = ",".join(["?"] * len(managers))

        # CHOT AN TOAN 1 - chong LONG TANG: gop tang rollup chi dung khi cac rollup KHONG chua nhau.
        # Neu sau nay Bravo them cap tren (vd TP quan ly QLV), cong ca 2 cap se GAP DOI am tham.
        # Thay vi tra ve so sai, bao ro rang. Hien tai (27/07/2026): 21/21 deu la QLV, khong ai bi long.
        nested = _q(f"SELECT DISTINCT employee_code FROM fact_tonghopkhachhang "
                    f"WHERE save_date<=? AND substr(save_date,1,7)=substr(?,1,7) "
                    f"AND employee_code IN ({ph}) AND manager_code IS NOT NULL AND manager_code<>''",
                    (fdate, fdate, *managers))
        if nested:
            _warn(f"CANH BAO CAU TRUC: {len(nested)} nguoi o tang quan ly lai co cap tren "
                  f"({', '.join(n['employee_code'] for n in nested[:5])}...) - cay to chuc da co them "
                  "tang moi, cach gop KPI theo vung hien tai CO THE DEM TRUNG. PHAI noi ro so lieu "
                  "dang can kiem tra lai, khong khang dinh chac chan.")

        sql = f"""SELECT nv.area_code area_code, SUM(e.sales) sales, SUM(e.target) target
                  FROM (SELECT f.employee_code, SUM(f.amount_ct) sales, MAX(f.month_sale_target) target
                        FROM fact_tonghopkhachhang f
                        JOIN {_MONTH_LATEST_SUBQ} l
                          ON l.employee_code=f.employee_code AND l.d=f.save_date
                        GROUP BY f.employee_code) e
                  JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code
                  WHERE e.employee_code IN ({ph})"""
        params = [fdate, fdate] + managers
        if scope_area_code:
            sql += " AND nv.area_code=?"
            params.append(scope_area_code)
        sql += " GROUP BY nv.area_code"
        rows = _q(sql, tuple(params))
        for r in rows:
            r["sales"] = _f(r["sales"]); r["target"] = _f(r["target"])
            r["pct"] = (r["sales"] / r["target"] * 100) if r["target"] else 0.0
            # Dong TONG HOP theo VUNG cham theo moc DAT KPI 80% - 1 vung khong phai 1 con nguoi nen
            # khong co cong thuong nao ap cho no; 80% la moc danh gia hieu qua, dung ban chat o day.
            r["threshold"] = KPI_ACHIEVED_THRESHOLD
            r["kpi_threshold"] = KPI_ACHIEVED_THRESHOLD
            r["status"] = _kpi_status(r["pct"])
        _warn_region_target_mismatch(rows, fdate)
        return sorted(rows, key=lambda x: -x["pct"])[:limit]

    # group_by == "qlv"
    # 27/07/2026: dung CUNG tang rollup voi nhanh 'region' (_rollup_tier_codes) thay vi loc
    # position_code='QLV' + bo is_duplicate. Truoc day tra ve 19 dong trong khi bao cao goc cua DNH
    # co 21 - thieu dung 'Kenh MT' (5,29 ty) va 'Cho si' (1,5 ty) do bi co IsDuplicate loc mat, nen
    # nguoi dung cong tay danh sach QLV se KHONG ra tong vung (venh 6,79 ty o Mien Nam). Bao cao goc
    # CO liet ke 2 don vi nay nhu mot dong QLV, nen dua vao la dung - kem co danh dau ro day la
    # NHOM/KENH chu khong phai ca nhan, de khong ai hieu nham dang xep hang mot con nguoi.
    # CO Y khong loc end_date/is_resigned nua: pham vi phai TRUNG KHIT nhanh 'region', them bat ky
    # dieu kien nao chi co o day se lam 2 con so lech nhau tro lai.
    managers = _rollup_tier_codes(fdate)
    if not managers:
        _warn("Khong xac dinh duoc tang quan ly (manager_code rong) nen KHONG xep hang duoc QLV. "
              "PHAI noi ro la chua tra cuu duoc, KHONG tra ve danh sach rong nhu the la khong co ai.")
        return []
    ph = ",".join(["?"] * len(managers))
    qlv_sql = (f"SELECT employee_code, name, area_code, COALESCE(is_duplicate,0) dup "
               f"FROM dim_nhanvien WHERE employee_code IN ({ph})")
    params = list(managers)
    if scope_area_code:
        qlv_sql += " AND area_code=?"
        params.append(scope_area_code)
    if scope_employee_code:
        qlv_sql += " AND employee_code=?"
        params.append(scope_employee_code)
    qlv_rows = _q(qlv_sql, tuple(params))
    result = []
    for qlv in qlv_rows:
        kpi = _kpi_snapshot(qlv["employee_code"], fdate, "QLV")
        if kpi["target"] <= 0:
            continue
        # Ban ghi bi Bravo gan co trung lap MA KHONG nam trong danh sach "nguoi that bi gan nham"
        # (_KNOWN_MISFLAGGED_DUPLICATE_CODES) thi la don vi ao/nhom kenh, khong phai ca nhan:
        # vd MN1 'Kenh MT' (Modern Trade - Long Chau/Pharmacity...), MN4 'Cho si'.
        is_unit = (int(qlv["dup"] or 0) == 1
                   and qlv["employee_code"] not in _KNOWN_MISFLAGGED_DUPLICATE_CODES)
        row = {"employee_code": qlv["employee_code"], "name": qlv["name"],
               "area_code": qlv["area_code"], **kpi, "la_nhom_kenh": is_unit}
        if is_unit:
            row["ghi_chu"] = (f"'{qlv['name']}' la NHOM/KENH ban hang (khong phai mot ca nhan) - khi "
                              "tra loi phai goi dung la kenh/nhom, KHONG duoc noi nhu mot nhan vien.")
        result.append(row)
    return sorted(result, key=lambda x: -x["pct"])[:limit]


def revenue_reconciliation_check(as_of_date: str = None, area_code: str = None,
                                  scope_area_code: str = None) -> dict:
    """Doi chieu doanh thu TU TREN XUONG (SUM(amount9) tren hoa don OTC, toan vung) voi doanh thu
    CONG DON TU DUOI LEN (TDV -> QLV -> TP, dua tren snapshot fact_tonghopkhachhang qua revenue_tree)
    - phat hien lech giua 2 nguon thay vi chi tin 1 chieu tu tren xuong.

    QUAN TRONG - LY DO CO SAN 1 KHOANG LECH "BINH THUONG" (khong phai loi du lieu):
    1. Doanh thu tren xuong tinh CA kenh ETC (khong co NV phu trach truc tiep tren hoa don, xem
       vhoadon_etc/dmssx_khachhang) + khach hang 'mo coi' (khong co ho so trong dms_khachhang) - 2
       nhom nay KHONG THE gan cho bat ky TDV nao nen KHONG BAO GIO xuat hien trong tong cong don tu
       duoi len. Ham nay CHI so sanh rieng kenh OTC (co gan NV) de tranh lech "gia" do nhom nay.
    2. Cay to chuc suy luan qua quy uoc dat ten (org_hierarchy.py) co ~30% 'to' KHONG xac dinh duoc
       QLV phu trach (ghi "Chua xac dinh", BI LOAI khoi cong don) - day la GAP TO CHUC da biet, khong
       phai bug. Vi vay tong cong don tu duoi len LUON <= tong tren xuong ve mat cau truc, KHONG bao
       gio > - neu code sau nay thay > thi moi la dau hieu bug that (vd dem trung TDV).
    Ket qua tra ve ca "coverage_pct" (cong don duoc bao nhieu % so voi tong tren xuong) de nguoi dung
    tu danh gia gap co hop ly khong, THAY VI chi 1 con so "lech" kho dien giai.
    scope_area_code: ep gioi han vung khi tai khoan bi han che (vd QLV/GD mien)."""
    if scope_area_code:
        area_code = scope_area_code
    if as_of_date is None:
        as_of_date = str(dt.date.today())

    fdate_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?", (as_of_date,))
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return {"as_of": None, "error": "Khong co snapshot KPI nao truoc/bang ngay nay de doi chieu."}

    # Doanh thu OTC TREN XUONG - CHI kenh OTC (ETC khong co NV phu trach truc tiep tren hoa don nen
    # khong doi chieu cong don duoc, xem docstring). Neu loc theo area_code, PHAI xu ly khach hang
    # "mo coi" (khong co ho so trong dms_khachhang) GIONG HET revenue_by_region(): LEFT JOIN that (KHONG
    # duoc WHERE tp.area_code=? sau JOIN, se vo tinh bien thanh INNER JOIN va am tham loai khach mo coi
    # khoi tong - day la bug thuc te da phat hien qua fixture test khi viet ham nay lan dau) + suy luan
    # vung qua tien to ma KH (region_map.py) cho dong nao co area=NULL, roi moi loc theo area_code sau
    # khi da xac dinh vung. Neu KHONG loc vung, don gian SUM toan bo (khong can quan tam khach mo coi
    # thuoc vung nao vi dang tinh tong ca cong ty).
    # !!! PHAI SO CUNG KY. fact_tonghopkhachhang (nguon cua bottom_up) la so LUY KE TU DAU THANG den
    # ngay snapshot, con vhoadon_otc la so THEO TUNG NGAY. Truoc 31/07/2026 khoi nay lay
    # "doc_date BETWEEN fdate AND fdate" tuc CHI 1 NGAY, roi dem so sanh voi ca thang -> bottom_up luon
    # vuot xa top_down -> canh bao "BAT THUONG, co the dem trung TDV" ban ra SAI. Da xay ra that:
    # 31/07/2026 tool bao "1,30 ty tren xuong vs 26,01 ty duoi len, ty le 2.006%, can bo phan van hanh
    # kiem tra" trong khi doanh thu OTC ca thang 7 la ~34 ty va khong he co loi gi.
    month_start = fdate[:8] + "01"
    if area_code:
        rows = _q("""
            SELECT v.customer_code cc, tp.area_code area, SUM(v.amount9) rev
            FROM vhoadon_otc v LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code
            LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
            WHERE v.doc_date BETWEEN ? AND ? GROUP BY v.customer_code, tp.area_code
            """, (month_start, fdate))
        top_down_rev = sum(_f(r["rev"]) for r in rows
                            if (r["area"] or region_from_customer_code(r["cc"])) == area_code)
    else:
        top_down_rev = _f(_q("SELECT COALESCE(SUM(amount9),0) rev FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ?",
                              (month_start, fdate))[0]["rev"])

    # Doanh thu OTC CONG DON TU DUOI LEN: dung LAI cay to chuc cua revenue_tree() (TDV -> QLV -> TP)
    # thay vi tu viet lai truy van rieng - tranh 2 noi dinh nghia khac nhau ve "ai thuoc doi ai".
    tree = revenue_tree(as_of_date=fdate, area_code=area_code)
    bottom_up_rev = 0.0
    tdv_count = 0
    undetermined_zones = 0
    for tp in tree["tree"]:
        for qlv in tp["qlv"]:
            if not qlv["tdv"]:
                undetermined_zones += 1
            for t in qlv["tdv"]:
                bottom_up_rev += t["sales"]
                tdv_count += 1

    coverage_pct = (bottom_up_rev / top_down_rev * 100) if top_down_rev else 0.0
    result = {
        "as_of": fdate, "area_code": area_code,
        "period_from": month_start, "period_to": fdate,
        "top_down_revenue_otc": top_down_rev,
        "bottom_up_revenue_otc": bottom_up_rev,
        "coverage_pct": coverage_pct,
        "tdv_count_in_tree": tdv_count,
        "zones_without_qlv": undetermined_zones,
        "note": (f"CA HAI VE deu tinh cho cung ky {month_start} -> {fdate} (luy ke tu dau thang den "
                 "ngay chot snapshot KPI) va CA HAI VE deu CHI kenh OTC - ETC da bi loai khoi ca tu so "
                 "lan mau so nen KHONG phai ly do gay chenh lech, TUYET DOI KHONG giai thich khoang "
                 "chenh bang 'do co kenh ETC'. Cong don tu duoi len LUON nho hon tong tren xuong (khong "
                 "bao gio bang 100%) vi 3 ly do THAT: khach 'mo coi' trong hoa don OTC khong co NV phu "
                 "trach, cac 'to' chua xac dinh QLV (xem zones_without_qlv), va TDV khong nam trong cay "
                 "to chuc - day la GAP cau truc da biet, KHONG phai loi. coverage_pct qua thap bat "
                 "thuong (vd giam dot ngot so ky truoc) moi dang nghi ngo co van de gan NV/vung sai. "
                 "Khi trinh bay PHAI neu ro khoang thoi gian nay de nguoi doc khong tuong dang so 1 "
                 "ngay voi 1 thang."),
    }
    if coverage_pct > 100.5:  # dung sai nho cho lam tron, > han han moi la dau hieu bug that (dem trung)
        result["warning"] = ("BAT THUONG: cong don tu duoi len VUOT QUA tong tren xuong - dau hieu co "
                              "the dang dem trung TDV (vd 1 nguoi xuat hien o nhieu 'to') hoac loi join, "
                              "can kiem tra lai truoc khi tin so lieu nay.")
    return result


def audit_log_summary(days: int = 7, limit: int = 30, username: str = None, target_username: str = None, scope_role: str = None) -> dict:
    """Lich su truy van + token/chi phi AI. 
    Neu tai khoan la C-Level hoac Admin: cho phep xem CHI PHI TOAN CONG TY hoac loc theo target_username.
    Neu tai khoan la QLV/TDV: chi duoc xem lich su va chi phi CUA CHINH NGUOI DANG HOI."""
    import json

    # 28/07/2026: CHI dua vao scope_role - gia tri nay duoc call_template EP tu server (tu user["role"]
    # da xac thuc), AI khong the dua vao.
    # DA BO ve suy luan quyen theo CHUOI username (truoc day: username in ('admin','ceo'...) hoac
    # startswith('c_level'/'admin')). Hai ly do:
    #   - username cung chi la 1 chuoi, khi _SELF_SCOPED_TEMPLATES rong thi do AI dua -> tu nang quyen.
    #   - ngay ca khi ep dung tu server, suy quyen tu TEN tai khoan la sai nguyen tac: mot nguoi ten
    #     'admin.nguyen' hay 'ceo.tro.ly' se duoc quyen xem chi phi toan cong ty ma khong ai co y do.
    # Quyen phai doc tu vai tro trong CSDL tai khoan, khong doc tu cach dat ten.
    is_clevel_admin = bool(
        scope_role and str(scope_role).lower() in ('c_level', 'super_admin', 'ceo', 'cfo')
    )

    entries = []
    if os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    UNATTRIBUTED = "(chua quy duoc)"

    cutoff = dt.datetime.now() - dt.timedelta(days=days) if days else None
    my_entries = []
    my_sessions = set()

    effective_target = target_username if (is_clevel_admin and target_username and str(target_username).lower() != 'all') else None

    # Ban do phien -> chu phien, dung de quy chi phi cho tung nguoi voi cac dong cost_log CU (ghi
    # truoc 20bec9d 29/07/2026, khi do cost_log chua co truong username).
    #
    # HAI NGUON, doc theo thu tu do ben dan:
    #   1. bang sessions trong memory.db - nguon CHINH. Ben vung vi day la CSDL that, khong bi xoay
    #      vong nhu file log. Cung cach cost_report.py::_session_owner_map() da dung tu truoc.
    #   2. audit_log.jsonl - bo sung cho cac phien chua kip dang ky trong memory.db.
    # Truoc 31/07/2026 chi dung nguon (2), ma audit_log bi cat bot theo thoi gian nen cac phien cu
    # khong tra duoc chu -> 68% chi phi roi vao nhom "chua quy duoc" du van con tra duoc qua memory.db.
    session_owner = {}
    try:
        try:
            from conversation_memory import DB_PATH as _MEM_DB
        except Exception:
            _MEM_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")
        if os.path.exists(_MEM_DB):
            _mc = sqlite3.connect(_MEM_DB)
            try:
                for _sid, _owner in _mc.execute("SELECT session_id, owner_username FROM sessions"):
                    if _sid and _owner:
                        session_owner[_sid] = _owner
            finally:
                _mc.close()
    except Exception as _e:
        # Thieu bang/CSDL thi bo qua, van con nguon audit_log ben duoi - KHONG lam chet ca bao cao.
        print(f"[audit_log_summary] Khong doc duoc sessions tu memory.db: {_e}")

    for e in entries:
        sid_e, u_e = e.get("session_id"), e.get("username")
        if sid_e and u_e and sid_e not in session_owner:
            session_owner[sid_e] = u_e

    for e in entries:
        user_in_log = e.get("username")
        if not is_clevel_admin and user_in_log != username:
            continue
        if effective_target and user_in_log != effective_target:
            continue
        if cutoff:
            try:
                if dt.datetime.fromisoformat(e["ts"]) < cutoff:
                    continue
            except (KeyError, ValueError):
                continue
        my_entries.append(e)
        sid = e.get("session_id")
        if sid:
            my_sessions.add(sid)

    cost_by_session = {}
    cost_by_user = {}
    cost_username_by_session = {}
    cost_sessions = set()
    total_cost = 0.0
    total_tokens_in = total_tokens_out = 0
    if os.path.exists(COST_LOG_PATH):
        with open(COST_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    c = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = c.get("session_id")
                if not is_clevel_admin and sid not in my_sessions:
                    continue
                if cutoff:
                    try:
                        if dt.datetime.fromisoformat(c["ts"]) < cutoff:
                            continue
                    except (KeyError, ValueError):
                        continue
                cost = c.get("cost_usd", 0.0) or 0.0
                p_tok = c.get("input_tokens", 0) or 0
                c_tok = c.get("output_tokens", 0) or 0

                # username duoc ghi thang vao cost_log tu 20bec9d (29/07/2026); dong cu hon thi suy
                # qua session_owner. Khong tra ra duoc ca hai -> xep vao nhom "chua quy duoc".
                owner = (c.get("username") or "").strip() or session_owner.get(sid) or ""

                # C-Level loc rieng 1 tai khoan thi CHI PHI cung phai loc theo tai khoan do. Truoc day
                # vong nay khong loc theo effective_target, nen so luot hoi la cua 1 nguoi con so tien
                # lai la cua CA CONG TY - hai con so canh nhau nhung khac pham vi.
                if effective_target and owner != effective_target:
                    continue

                total_cost += cost
                total_tokens_in += p_tok
                total_tokens_out += c_tok

                if sid:
                    cost_sessions.add(sid)
                    # cost_log co truong username rieng (tu 20bec9d) - dung lam nguon BO SUNG cho ban
                    # do chu phien, phong khi phien khong co trong memory.db lan audit_log.
                    if owner and sid not in session_owner:
                        cost_username_by_session.setdefault(sid, owner)

                # Chi gom theo nguoi khi la C-Level: tai khoan thuong khong duoc thay chi phi nguoi khac.
                if is_clevel_admin:
                    agg_u = cost_by_user.setdefault(owner or UNATTRIBUTED,
                                                    {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
                    agg_u["cost_usd"] += cost
                    agg_u["input_tokens"] += p_tok
                    agg_u["output_tokens"] += c_tok

                if sid:
                    agg = cost_by_session.setdefault(sid, {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0})
                    agg["cost_usd"] += cost
                    agg["input_tokens"] += p_tok
                    agg["output_tokens"] += c_tok
                    agg["calls"] += 1

    # ---- PHAN HOACH luot hoi va phien theo tung nguoi ----
    # Lam SAU vong cost de co day du 3 nguon xac dinh chu phien. Dung phep CHIA (moi phien/luot thuoc
    # DUNG MOT nguoi) chu khong phai hop cac tap dung rieng le - nho vay cong cac dong BUOC PHAI bang
    # tong, thay vi hy vong no bang. Ban truoc (01748f1) lay hop 2 tap nen 1 phien co the roi vao 2
    # nguoi -> cong cac dong ra 112 trong khi tong la 111. Va so luot chi dem ban ghi CO username nen
    # 228/764 luot khong hien o dong nao, tao ra nghich ly "0 luot / 25 phien".
    owner_of = dict(session_owner)
    for _sid, _u in cost_username_by_session.items():
        owner_of.setdefault(_sid, _u)

    sessions_by_user = {}
    for _sid in (my_sessions | cost_sessions):
        sessions_by_user.setdefault(owner_of.get(_sid) or UNATTRIBUTED, set()).add(_sid)

    queries_by_user = {}
    for e in my_entries:
        _k = e.get("username") or owner_of.get(e.get("session_id")) or UNATTRIBUTED
        queries_by_user[_k] = queries_by_user.get(_k, 0) + 1

    def _event_summary(e: dict) -> str:
        """1 dong mo ta ngan gon kieu 'nhat ky hoat dong' (giong timeline audit log admin: 'Ai - lam
        gi - luc nao') - de AI trinh bay nhat quan thay vi tu dien giai tu question/sql/status moi lan
        1 kieu khac nhau (28/07/2026, theo yeu cau dinh dang giong timeline hanh chinh admin). sql co
        dang '<template:ten_tool>(...)' cho bao cao chuan, hoac SQL tho cho query_database - rut gon
        lai thanh 1 cau hanh dong ro rang. C-Level xem toan cong ty se thay ten nguoi dung dat truoc
        (vd "tungtx: Chay bao cao...") de phan biet dong nao cua ai."""
        sql = e.get("sql") or ""
        status = e.get("status")
        if sql.startswith("<template:"):
            tool_name = sql.split(":", 1)[1].split(">", 1)[0]
            action = f"Chạy báo cáo '{tool_name}'"
        elif sql:
            action = "Chạy truy vấn dữ liệu tự do (query_database)"
        else:
            action = "Thực hiện thao tác"
        if status == "ok":
            rc = e.get("row_count")
            detail = f" — {rc} dòng kết quả" if rc is not None else ""
            dur = e.get("duration_ms")
            detail += f", {dur} ms" if dur is not None else ""
            line = f"{action}{detail}"
        elif status == "rejected":
            line = f"{action} — BỊ TỪ CHỐI ({str(e.get('error', ''))[:80]})"
        elif status == "blocked":
            line = f"{action} — BỊ CHẶN (không đủ quyền)"
        elif status == "error":
            line = f"{action} — LỖI ({str(e.get('error', ''))[:80]})"
        else:
            line = action
        if is_clevel_admin and not effective_target and e.get("username"):
            line = f"{e['username']}: {line}"
        return line

    recent = sorted(my_entries, key=lambda e: e.get("ts", ""), reverse=True)[:limit]
    history = [{
        "ts": e.get("ts"),
        "event_summary": _event_summary(e),
        "username": e.get("username"),
        "question": e.get("question"),
        "sql": e.get("sql"),
        "status": e.get("status"),
        "row_count": e.get("row_count"),
        "duration_ms": e.get("duration_ms"),
        "error": e.get("error"),
        "session_cost_usd": cost_by_session.get(e.get("session_id"), {}).get("cost_usd"),
    } for e in recent]

    _rate_vn = f"{USD_TO_VND_RATE:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # CHI C-Level xem toan cong ty moi duoc tach chi phi theo tung nguoi (chot voi nguoi dung
    # 31/07/2026). Tai khoan thuong -> None, KHONG duoc lo chi phi cua dong nghiep. C-Level dang loc
    # rieng 1 nguoi cung -> None vi luc do ca bao cao da chi con 1 nguoi, tach ra khong con y nghia.
    user_breakdown = None
    if is_clevel_admin and not effective_target:
        # Lay HOP cac khoa cua 3 bang: nguoi co chi phi, nguoi co phien, nguoi co luot hoi. Neu chi
        # duyet cost_by_user thi nguoi co hoat dong ma khong tra duoc chi phi se bien mat khoi bang,
        # va cong cac dong se khong con bang tong.
        _zero = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
        _keys = set(cost_by_user) | set(sessions_by_user) | set(queries_by_user)
        user_breakdown = []
        for u in sorted(_keys, key=lambda k: -cost_by_user.get(k, _zero)["cost_usd"]):
            d = cost_by_user.get(u, _zero)
            user_breakdown.append({
                "username": u,
                "queries": queries_by_user.get(u, 0),
                "sessions": len(sessions_by_user.get(u, ())),
                "input_tokens": d["input_tokens"],
                "output_tokens": d["output_tokens"],
                "total_tokens": d["input_tokens"] + d["output_tokens"],
                "cost_usd": round(d["cost_usd"], 6),
                "cost_vnd": round(d["cost_usd"] * USD_TO_VND_RATE, 2),
                "is_unattributed": u == UNATTRIBUTED,
            })

    return {
        "username": username,
        "scope": "toan cong ty" if (is_clevel_admin and not effective_target) else (f"nguoi dung {effective_target}" if effective_target else f"ca nhan {username}"),
        "days": days,
        "total_queries": len(my_entries),
        "total_sessions": len(my_sessions | cost_sessions),
        "total_cost_usd": round(total_cost, 6),
        "total_cost_vnd": round(total_cost * USD_TO_VND_RATE, 2),
        "total_input_tokens": total_tokens_in,
        "total_output_tokens": total_tokens_out,
        "total_tokens": total_tokens_in + total_tokens_out,
        "history": history,
        "user_breakdown": user_breakdown,
        "display_hint": ("Trinh bay ket qua o dang TIMELINE - moi dong 1 su kien, theo thu tu MOI NHAT "
                          "TRUOC: gio:phut (ts) + event_summary (da soan san, dung nguyen van, KHONG tu "
                          "dien giai lai tu sql/question) + cau hoi goc (question) rut gon neu can. KHONG "
                          "trinh bay duoi dang bang SQL/cot ky thuat - day la nhat ky hoat dong cho nguoi "
                          "dung thuong, khong phai bao cao du lieu. "
                          "NEU co user_breakdown (khac null): he thong DA tach duoc chi phi theo tung tai "
                          "khoan - trinh bay them 1 BANG chi phi theo nguoi dung (cot: tai khoan, so luot, "
                          "so phien, token, tien VND) TRUOC phan timeline. TUYET DOI KHONG noi 'he thong "
                          "chua tach duoc chi phi theo tung nguoi' khi truong nay co du lieu. Dong nao co "
                          "is_unattributed=true thi ghi ro la phan CHUA QUY DUOC cho tai khoan nao, khong "
                          "gan bua cho mot nguoi."),
        "note": (f"Bao cao chi phi AI quy doi ty gia 1 USD = {_rate_vn} VND. Tai khoan C-Level / "
                 "Admin co quyen xem tong quan toan cong ty va loc theo tung nguoi dung. "
                 "user_breakdown=null nghia la tai khoan nay KHONG duoc phep xem chi phi cua nguoi "
                 "khac (chi C-Level xem toan cong ty moi co), KHONG phai he thong thieu du lieu."),
    }



def salary_detail(employee_code: str = None, save_date: str = None,
                   scope_employee_code: str = None, scope_role: str = None) -> dict:
    """Chi tiet THUONG KINH DOANH + PHU CAP theo chinh sach thu nhap moi (QD 0429/.25 Mien Nam/Trung,
    QD 0107/2026 TDV) - doc TRUC TIEP tu fact_thongketinhluong, nguon Bravo FACT_ThongKeTinhLuong DA
    TU TINH SAN dung cong thuc (verify 28/07/2026: DMBonus/Sigma(DM*k)=TotalPoint khop tuyet doi voi
    Bang 01 trong 3 Phu luc chinh sach - xem local_warehouse.py::SCHEMA).

    !!! GIOI HAN QUAN TRONG - PHAI NOI RO KHI TRA LOI: ham nay CHUA co LUONG CO BAN (LCB) - Bravo
    KHONG luu san muc LCB theo Level (chi co Target/Thuc dat/% theo thang trong DIM_BangLuong2025,
    KHONG PHAI bang tra Level->LCB). Ket qua tra ve la THUONG KINH DOANH (thuong danh muc DM1/2/3,
    thuong tien do V15/V22/V25, thuong ASO) + PHU CAP (an ca/xang xe/dien thoai) - CHUA PHAI Tong thu
    nhap day du (con thieu LCB). TUYET DOI KHONG duoc noi day la "tong luong" hay "thu nhap day du".

    PHAN QUYEN: employee_code mac dinh la CHINH NGUOI DANG HOI (server ep qua scope_employee_code,
    xem _SELF_SCOPED_TEMPLATES) - AI KHONG duoc tu chon xem nguoi khac tru khi la C-Level/QLV xem
    doi minh (xem call_template). scope_role='c_level' moi duoc bo qua gioi han nay.

    save_date: ngay snapshot can xem (mac dinh: gan nhat hien co, thuong la cuoi thang/dot chot gan
    nhat - fact_thongketinhluong CHI co 1 snapshot/thang, khac fact_tonghopkhachhang nhieu dong/thang)."""
    is_clevel = bool(scope_role and str(scope_role).lower() in ("c_level", "super_admin", "ceo", "cfo"))
    target_code = employee_code
    if not is_clevel:
        # QLV/TDV thuong: CHI duoc xem CHINH MINH - scope_employee_code (ep tu server) la nguon DUY
        # NHAT dang tin, bo qua employee_code AI/nguoi dung tu truyen de tranh do doi nguoi khac.
        if not scope_employee_code:
            return {"error": "Khong xac dinh duoc ma nhan vien cua tai khoan nay de tra cuu thuong/luong."}
        target_code = scope_employee_code

    if not target_code:
        return {"error": "Can cho biet ma nhan vien (hoac ten) can tra cuu thuong/luong."}

    ident = _resolve_employee_identity(target_code)
    lookup_code = ident["dmsid"] or target_code

    # 28/07/2026 (phat hien khi kiem thu Mien Bac): Bravo tao SAN 1 dong "khoi tao" cho ngay dau
    # thang moi (vd SaveDate=2026-08-01) truoc ca khi co phat sinh - dong nay CO total_point=0.0
    # (KHONG phai NULL - da kiem chung thuc te, loc "IS NOT NULL" KHONG loai duoc no) nhung
    # v25_percent/v15_percent/... deu NULL that su va month_sale_amount=0. Neu chi lay MAX(save_date)
    # don thuan se am tham lay nham dong RONG dau thang nay thay vi snapshot THAT cua ky truoc do da
    # chot du lieu (vd 2026-07-31 co day du V15/V22/V25/ASO cho toan bo Mien Bac, dm_bonus>0) - day
    # chinh la nguyen nhan chatbot tung bao sai "chua co du lieu V15/V22/V25/ASO" trong khi du lieu
    # THAT SU da duoc dong bo day du. Dung v25_percent IS NOT NULL lam dau hieu "ky da chot" (dang
    # tin hon total_point vi khong bi lam tron ve 0 nham).
    base_cond = "(employee_code=? OR employee_code=?)"
    base_params = (target_code, lookup_code)
    date_cond = " AND save_date<=?" if save_date else ""
    date_param = (save_date,) if save_date else ()

    fdate_r = _q(f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE {base_cond}{date_cond} "
                 f"AND v25_percent IS NOT NULL", base_params + date_param)
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        fdate_r = _q(f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE {base_cond}{date_cond}",
                     base_params + date_param)
        fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return {"error": f"Chua co du lieu thuong/luong cho nhan vien '{target_code}' (co the ma sai, "
                          "hoac du lieu chua duoc dong bo/chua phat sinh trong ky nay)."}

    row = _q("SELECT * FROM fact_thongketinhluong WHERE (employee_code=? OR employee_code=?) "
             "AND save_date=? LIMIT 1", (target_code, lookup_code, fdate))
    if not row:
        return {"error": f"Chua co du lieu thuong/luong cho nhan vien '{target_code}' tai ky {fdate}."}
    r = row[0]

    dm_bonus = _f(r["dm_bonus"])
    aso_bonus = _f(r["aso_bonus"])
    v15_bonus = _f(r["v15_bonus"])
    v22_bonus = _f(r["v22_bonus"])
    v25_bonus = _f(r["v25_bonus"])
    allowance = _f(r["lunch_amount"]) + _f(r["transport_amount"]) + _f(r["phone_amount"])
    total_bonus = dm_bonus + aso_bonus + v15_bonus + v22_bonus + v25_bonus

    threshold = _bonus_threshold(r["position_code"])
    pct = _f(r["month_sale_percent"]) * 100
    return {
        "employee_code": r["employee_code"], "employee_name": r["employee_name"],
        "position_code": r["position_code"], "area_code": r["area_code"], "save_date": fdate,
        "month_sale_amount": _f(r["month_sale_amount"]), "month_sale_target": _f(r["month_sale_target"]),
        "month_sale_percent": pct, "bonus_threshold_pct": threshold,
        "meets_bonus_threshold": pct >= threshold,
        "dm_breakdown": {
            "dm1": {"amount": _f(r["dm1_amount"]), "percent": _f(r["dm1_percent"])},
            "dm2": {"amount": _f(r["dm2_amount"]), "percent": _f(r["dm2_percent"])},
            "dm3": {"amount": _f(r["dm3_amount"]), "percent": _f(r["dm3_percent"])},
            "kpis_total_point": _f(r["total_point"]),
        },
        "dm_bonus": dm_bonus,
        "progress_bonus": {"v15": v15_bonus, "v22": v22_bonus, "v25": v25_bonus},
        "aso_bonus": aso_bonus,
        "total_bonus": total_bonus,
        "allowance": {"lunch": _f(r["lunch_amount"]), "transport": _f(r["transport_amount"]),
                      "phone": _f(r["phone_amount"]), "total": allowance},
        "kpi_indicators": {
            "sku": {"quantity": _f(r["sku_quantity"]), "target": _f(r["sku_target"]), "percent": _f(r["sku_percent"])},
            "reorder_customer": {"quantity": _f(r["reorder_cus_quantity"]), "target": _f(r["reorder_cus_target"]), "percent": _f(r["reorder_percent"])},
            "new_customer": {"quantity": _f(r["new_cus_quantity"]), "target": _f(r["new_cus_target"]), "percent": _f(r["new_cus_percent"])},
            "call": {"quantity": _f(r["call_quantity"]), "target": _f(r["call_target"]), "percent": _f(r["call_percent"])},
        },
        "warning": ("CHUA GOM LUONG CO BAN (LCB): so lieu nay CHI la Thuong kinh doanh + Phu cap, KHONG "
                    "PHAI tong thu nhap day du. LCB tinh theo Level (dua tren Target thang) hien CHUA co "
                    "trong du lieu dong bo - can bao nguoi dung lien he ke toan/HR de biet LCB chinh xac."),
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
    "get_inventory_by_region": inventory_by_region,
    "get_qlv_change_history": qlv_change_history,
    "get_revenue_tree": revenue_tree,
    "get_kpi_ranking": kpi_ranking,
    "get_revenue_reconciliation": revenue_reconciliation_check,
    "get_receivables_overview": receivables_overview,
    "get_audit_log": audit_log_summary,
    "get_salary_detail": salary_detail,
}

# Tool tra du lieu RIENG CUA NGUOI DANG HOI (lich su truy van/chi phi cua chinh ho) - username PHAI
# duoc EP tu server (call_template), KHONG BAO GIO tin username AI tu dua trong args, neu khong 1 tai
# khoan co the doc lich su nguoi khac chi bang cach yeu cau AI truyen username la.
#
# 28/07/2026: KHOI PHUC lai {"get_audit_log"} sau khi phat hien set nay bi lam RONG (trong commit them
# tinh nang C-Level xem chi phi toan cong ty). Hau qua khi de rong - da kiem chung bang test thuc te:
#   1) LO DU LIEU: username khong con duoc ep tu server -> chi con lay tu args do AI dua ra. Tai khoan
#      qlv chi can khien AI truyen username='dnh' la doc duoc lich su nguoi khac (test tra ve dung
#      username=dnh). Nang hon: truyen scope_role='c_level' la xem duoc TOAN CONG TY (test: 68 dong).
#   2) HONG TINH NANG: khi AI chi truyen tham so DUOC KHAI BAO (days/limit/target_username) thi
#      username=None -> is_clevel_admin=False -> bo loc di so sanh voi None, moi tai khoan (ke ca
#      C-Level) nhan ve cung mot tap sai. Tren live noi log co username that -> tat ca nhan ve RONG.
# Ca 2 cung mot goc: DANH TINH va VAI TRO phai do SERVER quyet dinh, khong bao gio do AI truyen.
_SELF_SCOPED_TEMPLATES = {"get_audit_log"}

# 28/07/2026 (KPI+luong moi): salary_detail() cung can scope_role tu server (C-Level moi duoc xem
# nguoi khac) NHUNG khong nhan tham so 'username' (dung employee_code, khac get_audit_log) - tach
# rieng khoi _SELF_SCOPED_TEMPLATES de khong ep nham 'username' vao ham khong co tham so do (TypeError).
_ROLE_SCOPED_TEMPLATES = {"get_salary_detail"}

# 28/07/2026: tool da bi gioi han bang co che MANH HON scope vung (ep username, xem
# _SELF_SCOPED_TEMPLATES) nen KHONG nhan tham so scope_area_code - ham audit_log_summary() khong co
# tham so nay trong chu ky. Neu call_template van truyen vo dieu kien (nhu MOI template khac) se
# TypeError -> tai khoan regional_director/qlv goi get_audit_log LUON LOI (phat hien 28/07/2026, tu
# khi tool nay them vao 27/07). Day la MIEN TRU CO CHU DICH, khong phai noi long fail-closed: moi
# tool KHAC quen khai bao tham so nay van se no TypeError nhu cu, dung xoa dong nay de "sua" loi khac.
# get_salary_detail: cung khong nhan scope_area_code (dung scope_employee_code + scope_role) - them
# vao day vi ly do tuong tu.
_AREA_EXEMPT_TEMPLATES = {"get_audit_log", "get_salary_detail"}


# 23/07/2026 - DOI SANG CO CHE "DANH SACH CHO PHEP, FAIL-CLOSED" sau khi phat hien lo hong R-F
# (xem docstring employee_kpi). TRUOC DAY chi co _EMPLOYEE_SCOPED_TEMPLATES: tool NAO co ten trong do
# thi duoc ep scope, tool nao KHONG co ten thi... chay tu do. Nghia la MOI tool moi them vao he thong
# deu MAC DINH HO cho toi khi co ai do nho bo sung ten vao set - va da quen that voi get_employee_kpi.
#
# Gio tach lam 2 khai niem:
#   _PERSON_LEVEL_TEMPLATES = tool tra du lieu HIEU SUAT THEO TUNG NGUOI (nhay cam voi tai khoan qlv)
#   _EMPLOYEE_SCOPED_TEMPLATES = tool DA nhan duoc tham so scope_employee_code
# Tool nam trong nhom 1 nhung KHONG nam trong nhom 2 -> CHAN HAN lan goi (khong tra du lieu), thay vi
# am tham tra du lieu toan vung. Them tool moi ma quen khai bao -> bi chan, khong bi ho.
#
# 28/07/2026 (R-H) - MO RONG sau khi phat hien lo hong CUNG LOAI voi R-F nhung o nhom tool KHAC:
# tai khoan qlv hoi "doanh thu thang nay" van nhan ve doanh thu TOAN MIEN MB (29,37 ty = ca 10 doi),
# thay vi rieng doi minh. Nguyen nhan: 12/17 tool chi bi gioi han theo scope_area_code (VUNG) - y HET
# regional_director - vi _PERSON_LEVEL_TEMPLATES truoc day chi liet ke tool KPI ca nhan, bo qua ca
# nhom doanh thu/khach hang/ton kho/cong no. User xac nhan 28/07: QLV CHI duoc xem doi cua rieng minh.
#
# Cach xu ly theo dung tien le R-F: khai bao vao _PERSON_LEVEL_TEMPLATES de bi CHAN HAN voi qlv, thay
# vi am tham tra du lieu ca vung. Chia 3 nhom theo kha nang thu hep:
#   (a) THU HEP DUOC ve doi (hoa don co employee_code) nhung CHUA lam - can sua SQL tung ham + test
#       lai voi Bravo: get_revenue_by_channel, get_revenue_by_region, get_top_customers,
#       get_top_products, compare_periods. CHAN TAM cho toi khi thu hep xong.
#   (b) KHONG THE thu hep ve doi (du lieu khong gan voi 1 nhan vien): get_inventory_by_region (kho),
#       get_receivables_overview (cong no theo khach), get_qlv_change_history (lich su doi QLV),
#       get_revenue_reconciliation (cong cu doi chieu he thong). Chan han cho toi khi DNH chot ai duoc xem.
#   (c) VO HAI, KHONG chan: get_employee_directory (chi tra ten/ma/vung, khong phai so lieu kinh
#       doanh - chinh la cau Q3 trong kich ban demo), get_customer_detail (tra cuu 1 khach cu the ma
#       nguoi dung da biet ma - da bi ep scope vung + kenh), get_audit_log (da ep username).
_PERSON_LEVEL_TEMPLATES = {"get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
                            "get_employee_daily_kpi", "check_order_timing",
                            # (a) cho thu hep ve doi - xem ghi chu tren
                            "get_revenue_by_channel", "get_revenue_by_region", "get_top_customers",
                            "get_top_products", "compare_periods",
                            # (b) khong the thu hep ve doi
                            "get_inventory_by_region", "get_receivables_overview",
                            "get_qlv_change_history", "get_revenue_reconciliation",
                            # 28/07/2026: get_salary_detail - du lieu THUONG/LUONG CA NHAN, nhay cam
                            # nhat trong moi tool (tien that cua tung nguoi) - BAT BUOC ep scope, xem
                            # ham salary_detail() va _EMPLOYEE_SCOPED_TEMPLATES.
                            "get_salary_detail"}
_EMPLOYEE_SCOPED_TEMPLATES = {"get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
                              "get_employee_daily_kpi", "get_revenue_by_channel", "get_top_customers", "get_salary_detail"}
# check_order_timing CO Y de ngoai _EMPLOYEE_SCOPED_TEMPLATES: day la bao cao CHONG GIAN LAN neu dich
# danh nhan su nghi "chay don don KPI" - chua co xac nhan nghiep vu ai duoc phep xem, nen voi tai khoan
# qlv thi CHAN han (fail-closed) cho toi khi DNH chot. Xem D1 trong docs/Cau_hoi_can_DNH_xac_nhan.md.

_CHANNEL_SCOPED_TEMPLATES = {"get_revenue_by_channel", "get_top_products", "get_top_customers",
                              "compare_periods", "get_customer_detail", "check_order_timing",
                              "get_revenue_by_region"}


def call_template(name: str, args: dict, question: str = "", username: str = None,
                   scope_area_code: str = None, scope_employee_code: str = None,
                   scope_channel: str = None, session_id: str = None,
                   scope_role: str = None) -> dict:
    """Goi 1 template theo ten, ghi audit log (giong format run_query de nhat quan truy vet).
    scope_area_code: EP TRUYEN tu server (khong phai tu tham so AI dua ra) khi tai khoan bi gioi han
    vung - ghi de bat ky gia tri nao AI cung cap trong args, dam bao AI KHONG the tu "mo khoa" vung
    khac bang cach truyen tham so la. KHONG truyen cho tool trong _AREA_EXEMPT_TEMPLATES (da gioi han
    bang co che khac, xem docstring set do). scope_employee_code: CHI ap dung cho get_revenue_tree/
    get_kpi_ranking (xem _EMPLOYEE_SCOPED_TEMPLATES) - cac ham khac khong nhan tham so nay nen KHONG
    duoc truyen bua, se loi TypeError. scope_channel: CHI ap dung cho cac template lien quan doanh
    thu/khach hang (xem _CHANNEL_SCOPED_TEMPLATES) - EP GIOI HAN kenh (vd 'OTC'), doc lap voi 2 co
    che scope kia, ap dung duoc cho MOI role. session_id: 28/07/2026 - THEM de audit_log.jsonl noi
    duoc voi cost_log.jsonl trong get_audit_log (xem audit_log_summary) - thieu truong nay thi phep
    noi qua session_id luon rong, chi phi bao 0d cho MOI tai khoan (phat hien khi kiem thu lan dau)."""
    t0 = dt.datetime.now()
    entry = {"ts": t0.isoformat(), "username": username, "question": question,
             "sql": f"<template:{name}>({args})", "session_id": session_id}
    # 22/07/2026 (diem #5): mo "hop" canh bao rieng cho lan goi nay - tool goi _warn() trong luc chay
    # se duoc gom lai va dinh kem vao ket qua tra ve cho AI.
    token = _tool_warnings.set([])
    try:
        fn = TEMPLATES[name]
        call_args = dict(args)
        if name in _SELF_SCOPED_TEMPLATES:
            # EP CA HAI tu server, ghi de bat ky gia tri nao AI dua vao args: username (danh tinh)
            # va scope_role (vai tro, quyet dinh co duoc xem toan cong ty hay khong). Thieu 1 trong 2
            # la AI co the tu nang quyen - xem ghi chu o _SELF_SCOPED_TEMPLATES.
            call_args["username"] = username
            call_args["scope_role"] = scope_role
        if name in _ROLE_SCOPED_TEMPLATES:
            # Giong _SELF_SCOPED_TEMPLATES nhung KHONG ep 'username' (tool dung employee_code, xem
            # ghi chu o _ROLE_SCOPED_TEMPLATES) - chi ep scope_role de xac dinh co phai C-Level khong.
            call_args["scope_role"] = scope_role
        if scope_area_code and name not in _AREA_EXEMPT_TEMPLATES:
            call_args["scope_area_code"] = scope_area_code
        if scope_employee_code and name in _PERSON_LEVEL_TEMPLATES:
            if name in _EMPLOYEE_SCOPED_TEMPLATES:
                call_args["scope_employee_code"] = scope_employee_code
            else:
                # Fail-closed: tool tra du lieu theo tung nguoi nhung chua ho tro gioi han theo doi
                # -> KHONG chay. Tha tu choi con hon lo hieu suat ca nhan cua doi khac.
                entry["status"] = "blocked"
                _write_log(entry)
                return {"ok": False, "error": (
                    f"Bao cao '{name}' chua ho tro gioi han theo doi cua rieng ban nen khong the chay "
                    "voi tai khoan quan ly vung. Hay hoi ve doi cua chinh ban, hoac lien he cap quan ly "
                    "cao hon (Truong phong/Giam doc vung) neu can pham vi rong hon.")}
        if scope_channel and name in _CHANNEL_SCOPED_TEMPLATES:
            call_args["scope_channel"] = scope_channel
        result = fn(**call_args)
        entry["status"] = "ok"
        entry["duration_ms"] = int((dt.datetime.now() - t0).total_seconds() * 1000)
        _write_log(entry)
        payload = {"ok": True, "result": result}
        warnings = _tool_warnings.get() or []
        if warnings:
            payload["canh_bao"] = warnings
        return payload
    except Exception as e:
        entry["status"] = "error"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": f"Loi khi chay bao cao chuan '{name}': {str(e)[:300]}"}
    finally:
        _tool_warnings.reset(token)
