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
from sqlalchemy import text
from local_warehouse import get_conn, get_sync_meta
from query_engine import _write_log, _get_engine
from region_map import region_from_customer_code
import org_hierarchy as oh


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


def revenue_by_channel(date_from: str, date_to: str, scope_area_code: str = None,
                        scope_channel: str = None) -> dict:
    """Doanh thu + so hoa don theo kenh OTC/ETC trong khoang [date_from, date_to].
    scope_area_code: NEU duoc truyen (tai khoan QLV/GD mien bi gioi han vung), CHI tinh doanh thu
    cua dung vung do (join qua bang khach hang) - do la co che ep buoc o tang code, khong phu thuoc
    AI co tu loc dung hay khong.
    scope_channel: NEU duoc truyen (vd 'OTC'), KHONG truy van kenh con lai - tra ve 0 cho kenh do,
    kem co "channel_scope" bao hieu day la du lieu bi gioi han kenh (khac scope_area_code, co che
    nay doc lap va ap dung duoc cho moi role)."""
    scope_sql, scope_params = _scope_clause(scope_area_code)
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
    return [{"item_code": r["item_code"], "name": r["name"] or f'(chua co ten - ma {r["item_code"]})',
             "revenue": _f(r["rev"]), "qty": _f(r["qty"])} for r in rows]


def top_customers(date_from: str, date_to: str, limit: int = 10, channel: str = "ALL",
                   scope_area_code: str = None, scope_channel: str = None) -> list:
    """Top N khach hang theo doanh thu. scope_area_code: ep loc theo vung khi tai khoan bi gioi han.
    scope_channel: EP GHI DE tham so channel khi tai khoan bi gioi han kenh (xem top_products)."""
    if scope_channel:
        channel = scope_channel
    scope_sql, scope_params = _scope_clause(scope_area_code)
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


def revenue_by_region(date_from: str, date_to: str, scope_area_code: str = None) -> list:
    """Doanh thu theo vung mien (MB/MT/MN), gop ca OTC + ETC. CA HAI deu LEFT JOIN qua bang khach hang
    de lay city_id (da doi chieu voi DA ben Bravo va xac nhan day la cach dung - KHONG dung city_id ghi
    truc tiep tren vhoadon_otc vi truong nay khong dang tin, tung gay lech doanh thu theo vung).
    BAT BUOC LEFT JOIN (khong duoc INNER JOIN) - khach "mo coi" khong co trong bang khach hang (vd
    HCM13508 - co that, ~2.3 ty doanh thu 2022-2025, KHONG co trong dms_khachhang) se bi INNER JOIN
    am tham loai bo ca khoi tong lan breakdown. Voi LEFT JOIN, khach mo coi duoc suy luan vung qua
    TIEN TO ma khach hang (region_map.py, bang 63 tien to da kiem chung >=95% thuan, vd HCM -> MN) -
    CHI con roi vao "Khac/chua xac dinh" neu tien to khong nam trong bang do (an toan hon doan bua).
    Moi dong CO THE co them "channel_breakdown" (danh sach {name, revenue}) neu vung do co kenh dac
    biet duoc theo doi rieng (vd Modern Trade/Long Chau, Pharmacity... trong Mien Nam) - day la SO DA
    NAM SAN TRONG "revenue" cua vung (KHONG duoc cong them vao tong), chi de bao cao minh bach tach
    rieng theo yeu cau nghiep vu (xac nhan voi DA DNH 20/07/2026): kenh nay VAN tinh vao tong vung
    nhung can hien thi tach biet vi ban chat kinh doanh khac (chuoi lon vs kenh thuong)."""
    rows = _q("""
        SELECT o.customer_code cc, tp.area_code area, SUM(o.amount9) rev
        FROM vhoadon_otc o LEFT JOIN dms_khachhang kh ON kh.code=o.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE o.doc_date BETWEEN ? AND ? GROUP BY o.customer_code, tp.area_code
        UNION ALL
        SELECT e.customer_code cc, tp.area_code area, SUM(e.amount9) rev
        FROM vhoadon_etc e LEFT JOIN dmssx_khachhang kh ON kh.code=e.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE e.doc_date BETWEEN ? AND ? GROUP BY e.customer_code, tp.area_code
        """, (date_from, date_to, date_from, date_to))
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
        raw_total = _f(_q("SELECT COALESCE(SUM(amount9),0) t FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ?",
                           (date_from, date_to))[0]["t"]) + \
                    _f(_q("SELECT COALESCE(SUM(amount9),0) t FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ?",
                           (date_from, date_to))[0]["t"])
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
    # bao cao minh bach, KHONG cong them vao tong (xem _channel_sub_buckets()).
    buckets = _channel_sub_buckets()
    if buckets:
        for row in result:
            row_buckets = [b for b in buckets if b["area_code"] == row["area"]]
            if row_buckets:
                breakdown = []
                for b in row_buckets:
                    r = _q("SELECT COALESCE(SUM(amount9),0) rev FROM vhoadon_otc WHERE channel_code=? "
                           "AND doc_date BETWEEN ? AND ?", (b["dmsid"], date_from, date_to))
                    breakdown.append({"name": b["name"], "revenue": _f(r[0]["rev"])})
                row["channel_breakdown"] = breakdown
    return result


# 23/07/2026: doi tu 80 sang 65 - lay theo CAU HINH THAT cua DNH trong bang `dbo.DIM_BacThuong`
# (Bravo), bang ma chinh thu tuc tinh luong `usp_SaleSalary_Calculation_Ver2` doc de quyet dinh ty le
# thuong. Bac dau tien co Earn1>0 = moc bat dau duoc thuong:
#     TDV -> 65% (bac 65/75/85/95)   |   QLV,CS,TP,PP,TBP,TK -> 70% (bac 70/80/90/100/120)
# Giong nhau ca 3 mien MB/MT/MN. Con so 80 truoc day la MCNA tu dat, khong co can cu nghiep vu.
# Repo bao cao D:\DNH (src/etl.py) doi cung ngay, cung gia tri - 2 he thong PHAI giong nhau.
#
# ⚠️ 23/07/2026 (chieu) - PHAN BIET 2 KHAI NIEM BI GOP NHAM SUOT TU DAU:
#   "DAT CHI TIEU"          = lam duoc >= 100% chi tieu thang. Giua thang gan nhu luon ~0 nguoi, vi
#                             doanh so moi luy ke toi hom nay con chi tieu la CA THANG.
#   "DAT MUC HUONG THUONG"  = >= nguong bat dau duoc tinh thuong doanh so (TDV 65%, quan ly 70%).
# Hai cau hoi KHAC NHAU, ra 2 con so khac nhau. Nhan cu "Dat Chi Tieu (>=65%)" tu no da mau thuan:
# dat chi tieu ma moi lam duoc 65% chi tieu. Tra ve CA HAI, va noi ro dang tra loi cai nao.
KPI_ACHIEVED_THRESHOLD = 65      # TDV (tang ca nhan - phan lon cau hoi KPI roi vao day)
KPI_ACHIEVED_THRESHOLD_MGR = 70  # QLV va cac vai tro quan ly/kenh
KPI_FULL_TARGET = 100            # "dat chi tieu" dung nghia den - khong lien quan nguong thuong
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
def _kpi_threshold(position_code: str = None) -> int:
    """Nguong % dat chi tieu de bat dau huong thuong doanh so, THEO VAI TRO.
    TDV -> 65 (QD 0107/2026). QLV/TP/PP/TBP/TK/CS -> 70 (QD 0429/.25, van hieu luc).
    position_code=None -> 65: giu nguyen hanh vi cu cho cac dong khong biet vai tro, va vi tuyet dai
    da so dong trong fact_tonghopkhachhang la TDV. KHONG doan bua sang 70 vi lam vay se bao "chua dat"
    cho nguoi that ma minh chi khong tra duoc vai tro."""
    if position_code and position_code.strip().upper() != "TDV":
        return KPI_ACHIEVED_THRESHOLD_MGR
    return KPI_ACHIEVED_THRESHOLD


def _kpi_status(pct: float, position_code: str = None) -> str:
    """Phan loai mau theo % dat KPI, nguong dat LAY THEO VAI TRO (_kpi_threshold):
    >=nguong Tot (xanh), tu KPI_WARN_THRESHOLD den duoi nguong Trung binh (vang), <50 Nguy hiem (do)."""
    if pct >= _kpi_threshold(position_code):
        return "🟢 Tốt"
    if pct >= KPI_WARN_THRESHOLD:
        return "🟡 Trung bình"
    return "🔴 Nguy hiểm"


def employee_kpi(as_of_date: str, limit: int = 10, order_by: str = "sales", filter: str = "all",
                  position_code: str = None, scope_area_code: str = None,
                  scope_employee_code: str = None) -> dict:
    """KPI nhan vien: snapshot fact_tonghopkhachhang gan nhat <= as_of_date.
    order_by: 'sales' hoac 'pct' (dung khi filter='all', luon xep TOT NHAT truoc).
    filter: 'all' (top N tot nhat), 'below_target' (CHUA toi muc huong thuong, xep TE NHAT truoc),
            'above_target' (DA toi muc huong thuong, xep TOT NHAT truoc).
    position_code: loc theo vai tro (vd 'TDV','QLV') - LUON dung tham so nay khi cau hoi chi dinh ro
    vai tro (vd "top TDV"), KHONG tu loc thu cong tu ket qua day du vi de sot/thieu chinh xac.

    ⚠️ PHAN BIET 2 MOC, DUNG GOP LAM MOT:
      - "DAT CHI TIEU" = >=100% chi tieu thang -> dung "count_full_target" (va co "meets_full_target"
        tren tung dong). Giua thang con so nay gan nhu luon ~0 va DO LA DUNG: doanh so moi luy ke toi
        hom nay, con chi tieu la ca thang.
      - "DAT MUC HUONG THUONG doanh so" = >= "threshold" cua tung dong (TDV 65% theo QD 0107/2026,
        QLV va cac cap quan ly 70% theo QD 0429/.25) -> dung "count_above_target"/"count_below_target".
    Hoi "ai chua dat chi tieu" thi tra loi theo moc 100%; hoi "ai duoc thuong / ai toi muc thuong"
    thi tra loi theo "threshold". Neu cau hoi mo ho thi dua CA HAI con so va noi ro tung cai la gi.
    Moi dong con co "status" (🟢 Tot/🟡 Trung binh/🔴 Nguy hiem) - mau nay chia theo muc HUONG THUONG,
    khong phai theo moc 100%. LUON dung nguyen cac gia tri nay, khong tu tinh nguong khac.

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
             LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code
             LEFT JOIN dim_chucvu cv ON cv.position_code=nv.position_code
             WHERE e.save_date=? AND {_not_duplicate_sql('nv')}"""
    params = [fdate]
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
        # Nguong theo VAI TRO cua chinh dong do, khong dung 1 nguong phang cho ca bang: 1 truy van
        # co the tra ve lan lon TDV (65%) va QLV (70%) khi khong loc position_code.
        r["threshold"] = _kpi_threshold(r["position_code"])
        r["status"] = _kpi_status(r["pct"], r["position_code"])
        # "Dat chi tieu" dung nghia den (>=100%) - KHAC voi "dat muc huong thuong" (>=threshold).
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

    r = _q("SELECT MAX(month_sale_target) t, MAX(save_date) d FROM fact_tonghopkhachhang "
           "WHERE employee_code=? AND save_date<=?", (resolved_code, str(target_asof)))
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
    """Tra du no/qua han tu Supabase (khong co tren Bravo). channel co the la 'OTC','ETC','OTC+ETC'
    - neu ca 2 kenh, uu tien receivable_detail (OTC) truoc vi pho bien hon.

    22/07/2026 (diem #4 gop y): TRUOC DAY `except: pass` nuot MOI loi roi tra ve dict rong -
    khong phan biet duoc "khach KHONG co no" voi "KHONG TRA CUU DUOC" (Supabase sap/mat mang).
    Hau qua: chatbot tra loi tu tin "khach nay khong co cong no" trong khi that ra la loi tra cuu -
    nguy hiem cho quyet dinh cong no. Gio them `receivable_status`:
      - "ok"      : tra duoc, CO du lieu
      - "no_data" : tra duoc, khach KHONG co ban ghi cong no (that su khong no)
      - "error"   : KHONG tra cuu duoc (kem `receivable_warning` de AI canh bao nguoi dung)
    """
    # 23/07/2026 (R-B): moi cau tra loi ve cong no PHAI kem canh bao nguon. Nguon o day la 2 bang
    # Supabase receivable_detail/receivable_etc - du lieu Excel nhap 1 lan dau du an, KHONG tu lam
    # moi, va mang dong doi cong thuc cu (cong thuc do tung thoi no 1 khach len 9,17 ty trong khi
    # that la 0,61 ty). Repo bao cao D:\DNH da chuyen sang goi thang usp_DeptAccDueDate_GetData - SP
    # goc cua DNH - nen 2 he thong dang tra 2 so khac nhau.
    # Bang chung thuc te 23/07/2026: hoi chatbot ve DTH00237 (Benh vien Da khoa Dong Thap, mua 1,53 ty
    # trong 3 tuan) -> tra "Cong no: chua co du lieu". Mot benh vien tinh mua ngan do gan nhu chac
    # chan CO cong no; do la bang RONG chu khong phai khach khong no.
    # Xu ly tam: gan canh bao BAT BUOC vao moi ket qua (ca khi tra duoc so), de AI khong bao gio
    # khang dinh mot minh. Xu ly goc (port SP): can lam truoc Demo #1 09/08.
    _warn("CONG NO trong chatbot lay tu bang nhap tay tu dau du an, KHONG tu dong cap nhat va CO THE "
          "SAI/THIEU. PHAI noi ro dieu nay khi tra loi. Neu khong tim thay du lieu, PHAI noi la "
          "'chua tra cuu duoc/chua co trong bang du lieu', TUYET DOI KHONG ket luan 'khach khong co "
          "no'. So cong no chuan hien nam o bao cao dinh ky gui qua email.")
    empty = {"balance_end": None, "total_overdue": None, "overdue_pct": None,
             "receivable_status": "no_data",
             "receivable_warning": (
                 f"Khong tim thay ban ghi cong no cua khach {customer_code} trong bang du lieu "
                 "(bang nay nhap tay tu dau du an, khong day du). Day KHONG co nghia la khach khong "
                 "co no - PHAI tra loi la 'chua tra cuu duoc', va huong nguoi dung sang bao cao cong "
                 "no dinh ky de co so chuan.")}
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
                                "overdue_pct": (overdue / balance * 100) if balance else 0.0,
                                "receivable_status": "ok"}
            if "ETC" in channel:
                r = conn.execute(text('SELECT "total_receivable", "total_overdue" FROM receivable_etc '
                                       'WHERE "customer_code"=:c'), {"c": customer_code}).fetchone()
                if r:
                    balance, overdue = float(r[0] or 0), float(r[1] or 0)
                    return {"balance_end": balance, "total_overdue": overdue,
                            "overdue_pct": (overdue / balance * 100) if balance else 0.0,
                            "receivable_status": "ok"}
    except Exception as e:
        # KHONG tra ve `empty` (se bi hieu nham la "khong no") - danh dau ro la LOI tra cuu.
        return {"balance_end": None, "total_overdue": None, "overdue_pct": None,
                "receivable_status": "error",
                "receivable_warning": (
                    f"KHONG tra cuu duoc cong no cua khach {customer_code} (loi he thong: "
                    f"{type(e).__name__}). PHAI noi ro voi nguoi dung la CHUA XAC DINH duoc cong no, "
                    f"TUYET DOI KHONG ket luan khach nay khong co no.")}
    return empty


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

    return {
        "date_from": date_from, "date_to": date_to, "threshold_days": threshold_days,
        "total_flagged": len(rows),
        "summary_by_employee": summary,
        "top_detail": rows[:limit],
        "data_as_of": latest_data_date(),
    }


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


def _kpi_snapshot(employee_code: str, fdate: str, position_code: str = None):
    """Sales/target/pct cua 1 nhan vien (QLV/TDV deu dung duoc) tai 1 snapshot da biet - fact_tonghopkhachhang
    da tinh san rollup cho ca cap QLV (Bravo tu tong hop), khong can tu cong tay tu doanh thu TDV.
    position_code: BAT BUOC truyen khi da biet vai tro - nguong dat khac nhau (TDV 65% / quan ly 70%),
    de trong se cham nham cap quan ly o nguong TDV."""
    r = _q("SELECT SUM(amount_ct) sales, MAX(month_sale_target) target FROM fact_tonghopkhachhang "
           "WHERE employee_code=? AND save_date=?", (employee_code, fdate))
    sales = _f(r[0]["sales"]) if r else 0.0
    target = _f(r[0]["target"]) if r else 0.0
    pct = (sales / target * 100) if target else 0.0
    return {"sales": sales, "target": target, "pct": pct,
            "threshold": _kpi_threshold(position_code), "status": _kpi_status(pct, position_code)}


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

    BAT BUOC loc position_code='TDV' - phat hien 23/07/2026 (cung ngay, vong 2): fact_tonghopkhachhang
    dong bo TAT CA vai tro (TDV/QLV/CS/TP/PP/...) khong loc gi, khac han Bravo ground truth ben repo
    bao cao (get_bravo_kpi_tdv_snapshot chi lay position_codes=('TDV','QLV') NGAY TU CAU SQL, CS/TP/PP
    chua bao gio duoc dua vao snapshot). Neu khong loc o day, 1 QLV co NHAN VIEN CS bao cao len (vd
    MBKV12 co 2 CS: Nguyen Thi Ngoc Thoa, Nguyen Van Gioi) se bi tinh nham la "co doi" -> bi loai khoi
    childless_qlv trong kpi_ranking(region), NHUNG ban than 2 nguoi CS do cung KHONG duoc dem la la
    (leaf_clause chi nhan position_code='TDV') -> ca nhanh doanh so cua QLV do BIEN MAT HOAN TOAN khoi
    tong vung (con te hon loi cong trung ban dau - lan nay la MAT so, khong phai THUA so).
    org_hierarchy.py (zone-based) VAN con dung rieng cho qlv_change_history() - do la lich su AI TUNG
    phu trach 1 khu vuc theo thoi gian, ban chat khac voi "doi hien tai bao cao len ai"."""
    if fdate is None:
        fdate = _fact_latest_date()
    if not fdate:
        return []
    return _q(
        "SELECT DISTINCT e.employee_code, nv.name FROM fact_tonghopkhachhang e "
        "LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code "
        "WHERE e.manager_code=? AND e.save_date=? AND nv.position_code='TDV'", (qlv_employee_code, fdate))


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
    (hoac dung get_revenue_by_region cho doanh thu hoa don thuc te, khac voi so KPI o day)."""
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

    tree = []
    for tp in tp_rows:
        tp_kpi = _kpi_snapshot(tp["employee_code"], fdate, "TP")
        qlv_sql = ("SELECT employee_code, name FROM dim_nhanvien WHERE position_code='QLV' AND area_code=? "
                   f"AND end_date IS NULL AND COALESCE(is_resigned,0)<>1 AND {_not_duplicate_sql('')}")
        qlv_params = [tp["area_code"]]
        if scope_employee_code:
            qlv_sql += " AND employee_code=?"
            qlv_params.append(scope_employee_code)
        qlv_sql += " ORDER BY name"
        qlv_rows = _q(qlv_sql, tuple(qlv_params))
        qlv_list = []
        for qlv in qlv_rows:
            q_kpi = _kpi_snapshot(qlv["employee_code"], fdate, "QLV")
            team = _team_of_qlv(qlv["employee_code"], fdate)
            tdv_list = []
            for t in team:
                # _team_of_qlv da loc san position_code='TDV' nen o day chac chan la TDV (nguong 65%).
                t_kpi = _kpi_snapshot(t["employee_code"], fdate, "TDV")
                tdv_list.append({"employee_code": t["employee_code"], "name": t["name"], **t_kpi})
            qlv_list.append({"employee_code": qlv["employee_code"], "name": qlv["name"], **q_kpi,
                              "tdv_count": len(tdv_list), "tdv": tdv_list})
        tree.append({"employee_code": tp["employee_code"], "name": tp["name"], "area_code": tp["area_code"],
                      **tp_kpi, "qlv_count": len(qlv_list), "qlv": qlv_list})
    return {"as_of": fdate, "tree": tree}


def kpi_ranking(group_by: str = "qlv", as_of_date: str = None, limit: int = 20,
                 scope_area_code: str = None, scope_employee_code: str = None) -> list:
    """Xep hang KPI (% dat target) giua cac QLV hoac giua cac vung, TOT NHAT truoc. group_by: 'qlv'
    (xep hang tung QLV, dung khi hoi 'QLV nao dat KPI tot nhat') hoac 'region' (gop tat ca nhan vien
    theo vung MB/MT/MN, dung khi hoi 'vung nao dat KPI tot nhat'). scope_area_code: ep gioi han vung
    khi tai khoan bi han che - voi group_by='region' se chi con 1 dong (vung cua chinh ho). scope_employee_code:
    CHI danh cho qlv - voi group_by='qlv' se chi tra ve DUNG 1 dong (chinh ho), khong xep hang so sanh
    voi cac QLV khac (du lieu hieu suat CA NHAN dong nghiep, khong duoc xem)."""
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
        # 23/07/2026 (R-D): gop o "TANG LA" = moi TDV + nhung QLV KHONG co TDV nao duoi quyen.
        # TRUOC DAY chi lay position_code='TDV' -> BO SOT hoan toan QLV tu om khach khong co doi
        # (vd MBKV12: doanh so 2,01 ty, target 5,28 ty bien mat khoi KPI mien Bac). Nhung cung KHONG
        # duoc lay ca tang QLV: fact_tonghopkhachhang da rollup san doanh so doi len dong QLV, cong ca
        # 2 tang la gap doi. Tang la vua khong sot vua khong trung.
        # Repo bao cao D:\DNH (src/etl.py, cung ngay) da doi sang DUNG cach nay - 2 he thong phai gop
        # giong nhau, neu khong khach mo song song chatbot va email se thay 2 bo so khac nhau.
        #
        # 23/07/2026 SUA LOI: ban dau dung oh.team_of_qlv() (suy luan qua zone) de xac dinh "khong co
        # doi" - kiem chung thuc te phat hien 5 QLV bi tinh nham la khong co doi (dung ra chi 1),
        # trong khi 4/5 nguoi co that 6-8 TDV. Hau qua: doanh so+target CA DOI ho bi cong THEM vao
        # tang la (vi ho lot vao leaf_clause nhu the la QLV don le), CONG TRUNG voi chinh cac TDV cua
        # ho da nam trong nhanh position_code='TDV' -> KPI Mien Trung phong tu 6,79 len 11,82 ty.
        # Doi sang _team_of_qlv() (manager_code THAT tu Bravo, DUNG fdate dang xet - khac voi truoc
        # day khong truyen fdate, mac dinh lay "gan nhat" co the khac snapshot dang gop) sua dut diem.
        childless_qlv = [q["employee_code"] for q in _q(
            "SELECT employee_code FROM dim_nhanvien WHERE position_code='QLV' "
            f"AND end_date IS NULL AND COALESCE(is_resigned,0)<>1 AND {_not_duplicate_sql('')}")
            if not _team_of_qlv(q["employee_code"], fdate)]
        leaf_clause = "nv.position_code='TDV'"
        if childless_qlv:
            leaf_clause = (f"(nv.position_code='TDV' OR nv.employee_code IN "
                           f"({','.join(['?'] * len(childless_qlv))}))")
        sql = f"""SELECT nv.area_code area_code, SUM(e.sales) sales, SUM(e.target) target
                  FROM (SELECT employee_code, SUM(amount_ct) sales, MAX(month_sale_target) target
                        FROM fact_tonghopkhachhang WHERE save_date=? GROUP BY employee_code) e
                  JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code AND {_not_duplicate_sql('nv')}
                  WHERE {leaf_clause}"""
        params = [fdate] + childless_qlv
        if scope_area_code:
            sql += " AND nv.area_code=?"
            params.append(scope_area_code)
        sql += " GROUP BY nv.area_code"
        rows = _q(sql, tuple(params))
        for r in rows:
            r["sales"] = _f(r["sales"]); r["target"] = _f(r["target"])
            r["pct"] = (r["sales"] / r["target"] * 100) if r["target"] else 0.0
            # CO Y dung nguong TDV (65%) cho dong TONG HOP theo VUNG: 1 vung khong phai 1 con nguoi
            # nen khong co nguong chinh sach nao ap cho no. Tang la dang gop o day gan nhu toan bo la
            # TDV, nen 65% la moc de hieu nhat. Day la quy uoc trinh bay, KHONG phai nguong tra thuong.
            r["threshold"] = KPI_ACHIEVED_THRESHOLD
            r["status"] = _kpi_status(r["pct"])
        return sorted(rows, key=lambda x: -x["pct"])[:limit]

    # group_by == "qlv"
    qlv_sql = ("SELECT employee_code, name, area_code FROM dim_nhanvien WHERE position_code='QLV' "
               f"AND end_date IS NULL AND COALESCE(is_resigned,0)<>1 AND {_not_duplicate_sql('')}")
    params = []
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
        result.append({"employee_code": qlv["employee_code"], "name": qlv["name"], "area_code": qlv["area_code"], **kpi})
    return sorted(result, key=lambda x: -x["pct"])[:limit]


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
}


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
_PERSON_LEVEL_TEMPLATES = {"get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
                            "get_employee_daily_kpi", "check_order_timing"}
_EMPLOYEE_SCOPED_TEMPLATES = {"get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
                               "get_employee_daily_kpi"}
# check_order_timing CO Y de ngoai _EMPLOYEE_SCOPED_TEMPLATES: day la bao cao CHONG GIAN LAN neu dich
# danh nhan su nghi "chay don don KPI" - chua co xac nhan nghiep vu ai duoc phep xem, nen voi tai khoan
# qlv thi CHAN han (fail-closed) cho toi khi DNH chot. Xem D1 trong docs/Cau_hoi_can_DNH_xac_nhan.md.

_CHANNEL_SCOPED_TEMPLATES = {"get_revenue_by_channel", "get_top_products", "get_top_customers",
                              "compare_periods", "get_customer_detail", "check_order_timing"}


def call_template(name: str, args: dict, question: str = "", username: str = None,
                   scope_area_code: str = None, scope_employee_code: str = None,
                   scope_channel: str = None) -> dict:
    """Goi 1 template theo ten, ghi audit log (giong format run_query de nhat quan truy vet).
    scope_area_code: EP TRUYEN tu server (khong phai tu tham so AI dua ra) khi tai khoan bi gioi han
    vung - ghi de bat ky gia tri nao AI cung cap trong args, dam bao AI KHONG the tu "mo khoa" vung
    khac bang cach truyen tham so la. scope_employee_code: CHI ap dung cho get_revenue_tree/
    get_kpi_ranking (xem _EMPLOYEE_SCOPED_TEMPLATES) - cac ham khac khong nhan tham so nay nen KHONG
    duoc truyen bua, se loi TypeError. scope_channel: CHI ap dung cho cac template lien quan doanh
    thu/khach hang (xem _CHANNEL_SCOPED_TEMPLATES) - EP GIOI HAN kenh (vd 'OTC'), doc lap voi 2 co
    che scope kia, ap dung duoc cho MOI role."""
    t0 = dt.datetime.now()
    entry = {"ts": t0.isoformat(), "username": username, "question": question, "sql": f"<template:{name}>({args})"}
    # 22/07/2026 (diem #5): mo "hop" canh bao rieng cho lan goi nay - tool goi _warn() trong luc chay
    # se duoc gom lai va dinh kem vao ket qua tra ve cho AI.
    token = _tool_warnings.set([])
    try:
        fn = TEMPLATES[name]
        call_args = dict(args)
        if scope_area_code:
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
