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
from statistics import median
from sqlalchemy import text
from local_warehouse import get_conn, get_sync_meta
from query_engine import _write_log, _get_engine
from region_map import region_from_customer_code, REGION_SQL_MARKERS, REGION_NAMES_VI
import org_hierarchy as oh
from pricing import USD_TO_VND_RATE
from feature_policy import (
    DISABLED_FUTURE_TOOL_NAMES,
    FUTURE_FORECAST_DISABLED_MESSAGE,
    disabled_future_result,
)

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
    if bucket is not None and msg not in bucket:
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


def _q_bravo(sql: str, params: dict = None) -> list[dict]:
    """Chay TRUY VAN CO DINH, chi-doc tren SQL Server cho bao cao chuan.

    Khac tool SQL tu do: cau SQL o day nam san trong code, nguoi dung/AI chi truyen tham so bind.
    Nho vay QLV/Manager van dung duoc bao cao da ep scope ma khong duoc quyen viet SQL tuy y.
    """
    normalized_params = {}
    for key, value in (params or {}).items():
        # Driver "SQL Server" cu tren may dev khong bind truc tiep datetime.date (HYC00).
        normalized_params[key] = value.isoformat() if isinstance(value, (dt.date, dt.datetime)) else value
    eng = _get_engine("bravo")
    with eng.connect() as conn:
        proxied = conn.connection
        driver_connection = getattr(proxied, "driver_connection", proxied)
        if hasattr(driver_connection, "timeout"):
            driver_connection.timeout = 30
        conn.exec_driver_sql("SET LOCK_TIMEOUT 5000")
        result = conn.execute(text(sql), normalized_params)
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]


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
    # Khong bao gio de chung tu mang ngay TUONG LAI dinh nghia "hom nay". Du lieu future-dated
    # co the xuat hien khi dong bo nham ky/chung tu du kien; neu lay MAX() khong rang buoc, model se
    # doi ngay he thong thanh ngay do va tra doanh thu tuong lai nhu da phat hien 17/08/2026.
    today = str(dt.date.today())
    r = _q("SELECT MAX(doc_date) d FROM vhoadon_otc WHERE substr(doc_date,1,10)<=?", (today,))
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


def data_freshness_note() -> str:
    """12/08/2026: cau NGAN GON de AI dan vao CUOI moi cau tra loi co so lieu (theo yeu cau C-Level
    can biet "du lieu ghi nhan/cap nhat luc nao" khi hoi doanh thu/KPI/cong no...) - khac
    sync_freshness_note() (chi len tieng khi sync TREO, dung lam canh bao loi) va latest_data_date()
    (chi tra NGAY chung tu moi nhat, khong co gio - dung lam moc suy luan "hom nay" noi bo cho AI,
    khong danh de hien thi truc tiep cho nguoi dung).

    Uu tien hien thi last_synced_at THAT (co gio:phut, tu sync_meta - moc HE THONG THAT SU dong bo
    xong lan gan nhat) neu doc duoc; fallback ve latest_data_date() (chi ngay) neu sync_meta chua co
    (vd DB moi khoi tao, bang sync_meta chua duoc tao)."""
    try:
        last_synced_at, _, _ = get_sync_meta("vhoadon_otc")
    except Exception:
        last_synced_at = None

    if last_synced_at:
        try:
            last_dt = dt.datetime.fromisoformat(last_synced_at)
            return f"Du lieu cap nhat den {last_dt.strftime('%H:%M %d/%m/%Y')}."
        except ValueError:
            pass

    return f"Du lieu cap nhat den ngay {latest_data_date()}."

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


class KhongXacDinhDuocDoi(Exception):
    """Khong xac dinh duoc doi cua 1 QLV. PHAI bao ro ra ngoai, TUYET DOI khong duoc am tham
    tra 0 dong - xem ghi chu trong _get_team_dms_ids()."""


# QLV tu phu trach khach hang truc tiep, khong co TDV bao cao ben duoi. Cac ma trong danh sach nay
# da duoc doi chieu rieng voi du lieu giao dich: DMSId tren dim_nhanvien la pham vi ca nhan cua chinh
# ho, KHONG phai ma tong hop toan mien. Chi fallback cho danh sach xac minh nay; moi ma khac van
# fail-closed de khong bien loi ManagerCode thanh bao cao thieu ma nguoi dung khong biet.
_VERIFIED_SELF_MANAGED_QLV_CODES = {"MBKV12"}


def _fact_date_le(as_of_date: str = None) -> str:
    """Ngay snapshot KPI gan nhat KHONG VUOT QUA as_of_date (rong = moi nhat co trong kho).

    13/08/2026: tach ra thanh ham rieng de revenue_tree va bo loc pham vi doanh thu dung CHUNG
    mot cach tinh. Truoc do moi ben tu tinh mot kieu: cay to chuc chot doi theo ky duoc hoi, con
    bo loc doanh thu luon lay ky moi nhat -> hoi doanh thu thang 7 thi cay tra ve doi thang 7
    nhung bo loc tra ve doi thang 8, lech 8/18 QLV khi nhan su co thay doi giua 2 thang."""
    if not as_of_date:
        return _fact_latest_date()
    r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?", (str(as_of_date),))
    return r[0]["d"] if r and r[0]["d"] else None


def _get_team_dms_ids(scope_employee_code: str, fdate: str = None) -> list:
    """DMSId cua tat ca TDV thuoc quyen quan ly cua 1 QLV tai thoi diem `fdate`.

    13/08/2026 DOI NGUON XAC DINH DOI - suy luan zone -> manager_code that tu Bravo.

    Truoc do ham nay dung org_hierarchy.qlv_zones() (suy luan qua quy uoc dat ten: tim ban ghi
    "bong" ten co hau to "(QLV)" mang manager_area_code cua to, roi khop ten voi ban ghi QLV that).
    Cach do sai ~30% - chinh docstring cua _team_of_qlv() da ghi ro va da THAY THE no "cho MOI cho
    can biet doi cua 1 QLV", sau su co 23/07/2026: 5 QLV bi hieu la "khong co doi" trong khi 4/5 co
    that 6-8 TDV, lam KPI Mien Trung cong trung 11,82 ty thay vi 6,79 ty that.
    Nhung cuoc doi nguon do BO SOT ham nay - noi loc doanh thu cho 5 tool da mo cho vai QLV. Do do
    trong kho code ton tai HAI dinh nghia "doi" song song, va kiem chung 13/08/2026 tren du lieu that
    cho thay hau qua:
      - 4/18 QLV bi tra 0 dong CAM LANG (zone khong suy ra duoc) - trong do 3 nguoi Mien Trung co
        tai khoan that: Hoang Cong Thuong, Hoang Van Dung, Pham Van Thuan;
      - 8/18 QLV lech doi hinh (cay to chuc dem 10 nguoi, bo loc doanh thu dem 9) theo CA HAI chieu.
    Gio dung CHUNG _team_of_qlv() voi revenue_tree/KPI nen 2 con so luon khop theo dinh nghia.

    KHONG them bat ky bo loc nao khac ngoai nhung gi _team_of_qlv() da loc - moi bo loc them vao day
    se lam 2 duong lech tro lai, dung la thu vua di sua.

    Nem KhongXacDinhDuocDoi thay vi tra [] khi khong ra doi: [] se thanh " AND 1=0" -> moi tool tra
    0 dong ma khong bao gi, nguoi dung tin la "doi minh khong ban duoc gi". Tha noi khong biet.

    `fdate`: ngay snapshot de chot doi. Rong = doi HIEN TAI. Cac tool doanh thu truyen ngay cuoi
    ky duoc hoi vao day, de "doanh thu doi toi thang 7" tinh theo doi CUA THANG 7 - dung dinh nghia
    ma cay to chuc, KPI va luong dang dung. Thieu tham so nay chinh la 8/18 ca lech con lai sau ban
    va sang 13/08."""
    team = _team_of_qlv(scope_employee_code, fdate)
    codes = [t["employee_code"] for t in team if t.get("employee_code")]
    if not codes:
        if scope_employee_code in _VERIFIED_SELF_MANAGED_QLV_CODES:
            rows = _q(
                "SELECT DISTINCT dmsid FROM dim_nhanvien "
                "WHERE employee_code=? AND position_code='QLV' "
                "AND dmsid IS NOT NULL AND TRIM(dmsid)<>''",
                (scope_employee_code,),
            )
            own_dms_ids = list(dict.fromkeys(str(r["dmsid"]).strip() for r in rows if r.get("dmsid")))
            if own_dms_ids:
                _warn(
                    f"Ma QLV '{scope_employee_code}' khong co TDV bao cao truc tiep. "
                    "Bao cao nay CHI gom giao dich ghi theo DMSId cua chinh QLV, "
                    "khong phai doanh so toan mien."
                )
                return own_dms_ids
        raise KhongXacDinhDuocDoi(
            f"Khong xac dinh duoc doi cua quan ly vung '{scope_employee_code}': khong tim thay TDV "
            f"nao bao cao len ma nay trong FACT_TongHopKhachHang. KHONG the tra so doanh thu theo "
            f"doi. Bao voi nguoi dung rang du lieu phan cong doi cua ho chua co trong he thong, "
            f"can DNH kiem tra lai ManagerCode tren Bravo.")
    placeholders = ",".join(["?"] * len(codes))
    rows = _q(f"SELECT employee_code,dmsid FROM dim_nhanvien "
              f"WHERE employee_code IN ({placeholders})", tuple(codes))
    dms_by_employee = {r["employee_code"]: r.get("dmsid") for r in rows if r.get("dmsid")}
    missing_codes = [code for code in codes if not dms_by_employee.get(code)]
    if missing_codes:
        # Fallback cho kho sync cu: EmpDMSCode trong FACT la khoa noi chuan sang hoa don va da duoc
        # dong bo tu 31/07/2026. UAT that tung gap dim_nhanvien.dmsid NULL 320/320 dong, lam moi bao
        # cao doi tra loi 0/"khong co du lieu" du FACT van co du mapping.
        try:
            missing_ph = ",".join(["?"] * len(missing_codes))
            fact_rows = _q(
                f"SELECT f.employee_code,f.emp_dms_code dmsid FROM fact_tonghopkhachhang f "
                f"JOIN (SELECT employee_code,MAX(save_date) d FROM fact_tonghopkhachhang "
                f"WHERE employee_code IN ({missing_ph}) GROUP BY employee_code) l "
                f"ON l.employee_code=f.employee_code AND l.d=f.save_date "
                f"WHERE f.emp_dms_code IS NOT NULL AND TRIM(f.emp_dms_code)<>'' "
                f"GROUP BY f.employee_code,f.emp_dms_code",
                tuple(missing_codes),
            )
            for r in fact_rows:
                dms_by_employee.setdefault(r["employee_code"], r["dmsid"])
        except sqlite3.OperationalError:
            pass
    dms_ids = [dms_by_employee[code] for code in codes if dms_by_employee.get(code)]
    if not dms_ids:
        raise KhongXacDinhDuocDoi(
            f"Doi cua quan ly vung '{scope_employee_code}' co {len(codes)} TDV nhung KHONG ai co "
            f"DMSId trong dim_nhanvien - hoa don ghi theo DMSId nen khong loc duoc doanh thu. "
            f"Bao voi nguoi dung day la thieu du lieu he thong, khong phai doi khong co doanh thu.")
    # 04/09/2026 - CHOT CHAN "HUT AM THAM". Phan giai DU (0 nguoi) da nem loi o tren, nhung phan giai
    # MOT PHAN thi truoc day tra ve im lang: moi bao cao doanh thu doi hut dung ty le so nguoi khong
    # phan giai duoc, ma nguoi doc KHONG co cach nao biet. Do that tren UAT 04/09/2026 (QLV
    # TM25010183): chi 2/10 TDV phan giai duoc DMSId, nen doanh thu T1-T5/2026 chi ra ~22% so that
    # (T1 bao 487,4tr / that 2.026,0tr - dung bang DNH00618 + HNO_04, khop ca 5 thang). Cac thang
    # T6-T8 dung vi di duong khac (snapshot KPI, khoa theo employee_code nen khong can DMSId) - the
    # nen bang so nhin RAT hop ly: 3 thang cuoi khop tuyet doi, 5 thang dau sai gap 4 lan.
    if len(dms_ids) < len(codes):
        thieu = [c for c in codes if not dms_by_employee.get(c)]
        _warn(f"CANH BAO SO LIEU HUT: doi cua '{scope_employee_code}' co {len(codes)} TDV nhung chi "
              f"{len(dms_ids)} nguoi phan giai duoc DMSId. Doanh thu/so don/so khach trong bao cao "
              f"nay CHI gom {len(dms_ids)} nguoi do, tuc THIEU phan cua {len(thieu)} nguoi con lai "
              f"({', '.join(thieu[:8])}{'...' if len(thieu) > 8 else ''}). PHAI noi ro voi nguoi dung "
              f"day la so THIEU, khong duoc trinh bay nhu doanh thu ca doi. Nguyen nhan thuong gap: "
              f"kho chua dong bo lai sau khi them cot dmsid - chay 'py sync_warehouse.py' de khac phuc.")
    return dms_ids


def _employee_scope_clause(scope_employee_code: str, alias: str, as_of: str = None) -> tuple:
    """13/08/2026: bo nhanh `return " AND 1=0"`. Nhanh do bien "khong biet doi gom ai" thanh
    "doi khong ban duoc dong nao" - cung mot cau tra loi cho hai su that hoan toan khac nhau.
    _get_team_dms_ids() gio nem KhongXacDinhDuocDoi, call_template bat va tra loi ro ly do.

    `as_of`: NGAY CUOI KY dang duoc hoi (thuong la date_to). Doi duoc chot theo snapshot gan nhat
    khong vuot qua ngay do - giong het cach revenue_tree lam. Bo trong = doi hien tai, dung cho
    cac cho khong gan voi mot ky cu the (vd chuoi lich su nhieu nam cua tool du bao)."""
    if not scope_employee_code:
        return "", ()
    team_snapshot = _fact_date_le(as_of) if as_of else None
    if as_of and not team_snapshot:
        _warn(
            "CANH BAO DOI LICH SU: FACT_TongHopKhachHang chi giu lich su phan cong doi khoang "
            "90 ngay, nen ky cu hon dang duoc tinh theo THANH PHAN DOI HIEN TAI. Thanh phan doi "
            "tai ky do co the khac; bat buoc noi ro khi trinh bay YoY/lich su cap doi."
        )
    dms_ids = _get_team_dms_ids(scope_employee_code, team_snapshot)
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
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    scope_sql += emp_sql
    scope_params += emp_params
    if scope_channel == "ETC":
        otc_rev, otc_hd = 0.0, 0
    else:
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
        if scope_channel != "ETC":
            msc_o, msc_o_params = _monthly_summary_scope_clause(scope_area_code, "OTC")
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
            msc_o += msc_emp_sql
            msc_o_params += msc_emp_params
            so = _q(f"SELECT COALESCE(SUM(m.revenue),0) rev, COALESCE(SUM(m.invoice_count),0) hd "
                    f"FROM monthly_customer_summary m WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ?{msc_o}",
                    (ym_from, ym_to) + msc_o_params)[0]
            otc_rev += _f(so["rev"]); otc_hd += int(so["hd"] or 0)
        if scope_channel != "OTC":
            msc_e, msc_e_params = _monthly_summary_scope_clause(scope_area_code, "ETC")
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
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
                  scope_area_code: str = None, scope_channel: str = None,
                  scope_employee_code: str = None) -> list:
    """Top N san pham theo doanh thu. Loai hang khuyen mai (unit_price=0) khoi so luong ban that.
    scope_area_code: ep loc theo vung khi tai khoan bi gioi han (xem revenue_by_channel).
    scope_channel: EP GHI DE tham so channel (bo qua gia tri AI truyen vao) khi tai khoan bi gioi
    han kenh - dam bao khong chi xem duoc tung kenh rieng le theo scope_channel.
    scope_employee_code: GIOI HAN san pham top theo tung doi QLV."""
    if scope_channel:
        channel = scope_channel
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    scope_sql += emp_sql
    scope_params += emp_params
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
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
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
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
            msc_sql += msc_emp_sql
            msc_params += msc_emp_params
            parts.append(f"SELECT m.customer_code, m.revenue AS amount9 FROM monthly_customer_summary m "
                         f"WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ?{msc_sql}")
            part_params.append((ym_from, ym_to) + msc_params)
        if channel in ("ETC", "ALL"):
            msc_sql, msc_params = _monthly_summary_scope_clause(scope_area_code, "ETC")
            msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
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
                       scope_channel: str = None, scope_employee_code: str = None) -> list:
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
    
    emp_sql_o, emp_params_o = _employee_scope_clause(scope_employee_code, "o", as_of=date_to)
    emp_sql_e, emp_params_e = _employee_scope_clause(scope_employee_code, "e", as_of=date_to)
    
    parts = []
    part_params = []
    if channel != "ETC":
        parts.append(f"""
        SELECT o.customer_code cc, tp.area_code area, SUM(o.amount9) rev
        FROM vhoadon_otc o LEFT JOIN dms_khachhang kh ON kh.code=o.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE o.doc_date BETWEEN ? AND ?{emp_sql_o} GROUP BY o.customer_code, tp.area_code""")
        part_params.append((date_from, date_to) + emp_params_o)
    if channel != "OTC":
        parts.append(f"""
        SELECT e.customer_code cc, tp.area_code area, SUM(e.amount9) rev
        FROM vhoadon_etc e LEFT JOIN dmssx_khachhang kh ON kh.code=e.customer_code
        LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
        WHERE e.doc_date BETWEEN ? AND ?{emp_sql_e} GROUP BY e.customer_code, tp.area_code""")
        part_params.append((date_from, date_to) + emp_params_e)
    params = tuple(p for pp in part_params for p in pp)
    rows = _q(" UNION ALL ".join(parts), params)

    # date_from truoc cua so 12 thang chi tiet -> cong them phan da NEN (monthly_customer_summary co
    # customer_code nen van suy luan vung qua dms_khachhang/dmssx_khachhang giong nhu tren).
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        summary_to = min(date_to, cutoff)
        ym_from, ym_to = date_from[:7], summary_to[:7]
        emp_sql_m, emp_params_m = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
        summary_parts = []
        summary_params = []
        if channel != "ETC":
            summary_parts.append(f"""
            SELECT m.customer_code cc, tp.area_code area, SUM(m.revenue) rev
            FROM monthly_customer_summary m LEFT JOIN dms_khachhang kh ON kh.code=m.customer_code
            LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
            WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ?{emp_sql_m} GROUP BY m.customer_code, tp.area_code""")
            summary_params.append((ym_from, ym_to) + emp_params_m)
        if channel != "OTC":
            summary_parts.append(f"""
            SELECT m.customer_code cc, tp.area_code area, SUM(m.revenue) rev
            FROM monthly_customer_summary m LEFT JOIN dmssx_khachhang kh ON kh.code=m.customer_code
            LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id
            WHERE m.channel='ETC' AND m.year_month BETWEEN ? AND ?{emp_sql_m} GROUP BY m.customer_code, tp.area_code""")
            summary_params.append((ym_from, ym_to) + emp_params_m)
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
        #
        # 12/08/2026 SUA LOI: truoc day goi revenue_by_channel(date_from, date_to) KHONG kem scope.
        # Voi tai khoan QLV (co scope_employee_code), `total` la doanh thu CUA DOI con `raw_total` la
        # doanh thu TOAN CONG TY -> luon lech -> LUON bom canh bao "SO LIEU THEO VUNG CO THE THIEU"
        # va dan AI "KHONG duoc trinh bay breakdown nay nhu so lieu chac chan", du so hoan toan dung.
        # Phep doi chieu chi co nghia khi 2 ve CUNG mot pham vi, nen phai truyen y het bo scope.
        rbc = revenue_by_channel(date_from, date_to, scope_area_code, scope_channel, scope_employee_code)
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
#   ASO  - theo SO LUONG khach hang hoat dong (MB 40, MT 35, MN 25) - KHONG phai %;
#          KHONG ap dung cho CS (Cho si) va TK (kenh MT), hai vai tro nay dung is_ac.
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

# 27/08/2026: DNH chot lai pham vi chi tieu khach hang hoat dong.
#   CS = Cho si (chao si/wholesale), TK = Truong kenh MT (Modern Trade)
# Hai vai tro nay dung co is_ac/Active Customer; KHONG dung ASO. ASO la khoan rieng cua
# cac vai tro con lai khi nguon tinh luong co ghi nhan. Giu quy tac o mot noi de cac bao cao
# luong/detail/ranking va phep doi chieu khong tu hieu moi ham mot kieu.
_IS_AC_POSITIONS = frozenset(("CS", "TK"))


def _uses_is_ac(position_code: str = None) -> bool:
    """True neu vai tro dung co is_ac (CS/Cho si hoac TK/Kenh MT), khong dung ASO."""
    return str(position_code or "").strip().upper() in _IS_AC_POSITIONS

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
    threshold_summary = [
        {"threshold_pct": threshold,
         "count": sum(1 for r in rows if r["pct"] >= threshold),
         "total": len(rows)}
        for threshold in (65, 70, 80, 100, 120)
    ]
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
            # Model tung dem tay sai 3/7 thay vi 2/7 o moc 80%. Tra san ca 5 moc ma UAT hay hoi
            # de cau tra loi chi DOC ket qua, khong tu dem lai danh sach va khong nham 65/70 voi KPI.
            "threshold_summary": threshold_summary,
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
                        scope_employee_code: str = None, scope_channel: str = None) -> dict:
    if employee_code and "," in employee_code:
        codes = [c.strip() for c in employee_code.split(",") if c.strip()]
        results, errors = [], []
        for code in codes[:30]:
            r_single = employee_daily_kpi(
                employee_code=code, year_month=year_month, scope_area_code=scope_area_code,
                scope_employee_code=scope_employee_code, scope_channel=scope_channel,
            )
            if r_single and "error" not in r_single:
                results.append(r_single)
            else:
                errors.append({"employee_code": code,
                               "error": (r_single or {}).get("error", "Khong co ket qua.")})

        # Khong gui 21-23 dong chi tiet x 7-30 nguoi vao model: payload 20-50K ky tu bi cat o
        # MAX_PAYLOAD_CHARS, tung lam model chi nhin thay nguoi DAU TIEN va bao sai 6/7 nguoi
        # "khong co du lieu". Bulk tra TOM TAT DU theo nguoi + nhip TONG DOI theo ngay; goi don
        # mot nguoi van giu nguyen danh sach days day du o nhanh ben duoi.
        compact = []
        team_by_date = {}
        team_target = sum(_f(r.get("month_sale_target")) for r in results)
        for r in results:
            days = r.get("days") or []
            compact.append({
                "employee_code": r.get("resolved_employee_code") or r.get("employee_code"),
                "employee_name": r.get("employee_name"),
                "month_sale_target": r.get("month_sale_target"),
                "month_total_sales": r.get("month_total_sales"),
                "month_pct_of_target": r.get("month_pct_of_target"),
                "count_red": r.get("count_red"),
                "count_yellow": r.get("count_yellow"),
                "count_green": r.get("count_green"),
                "zero_revenue_dates": [d["date"] for d in days if not _f(d.get("revenue"))],
                "yellow_dates": [d["date"] for d in days if str(d.get("status", "")).startswith("🟡")],
                "green_dates": [d["date"] for d in days if str(d.get("status", "")).startswith("🟢")],
            })
            for day in days:
                team_by_date[day["date"]] = team_by_date.get(day["date"], 0.0) + _f(day.get("revenue"))
        team_days = []
        for date, revenue in sorted(team_by_date.items()):
            pct = revenue / team_target * 100 if team_target else 0.0
            team_days.append({"date": date, "revenue": revenue,
                              "pct_of_team_target": pct, "status": _daily_kpi_status(pct)})
        team_daily_summary = {
            "count_red": sum(1 for d in team_days if str(d["status"]).startswith("🔴")),
            "count_yellow": sum(1 for d in team_days if str(d["status"]).startswith("🟡")),
            "count_green": sum(1 for d in team_days if str(d["status"]).startswith("🟢")),
            "zero_revenue_dates": [d["date"] for d in team_days if not d["revenue"]],
            "yellow_dates": [d["date"] for d in team_days if str(d["status"]).startswith("🟡")],
            "green_dates": [d["date"] for d in team_days if str(d["status"]).startswith("🟢")],
            "top_revenue_dates": sorted(team_days, key=lambda d: -d["revenue"])[:5],
        }
        return {
            "is_bulk": True, "requested_count": min(len(codes), 30), "count": len(results),
            "employees": compact, "errors": errors,
            "team_month_target": team_target,
            "team_month_total_sales": sum(_f(r.get("month_total_sales")) for r in results),
            "team_daily_summary": team_daily_summary,
            "definition": ("employees la tom tat DU tung nguoi; team_daily_summary la nhip cong cua "
                           "ca doi theo ngay lam viec, top_revenue_dates chi giu 5 ngay cao nhat de "
                           "payload khong bi cat. Khong duoc dien giai count < requested_count la "
                           "nhan vien khong co du lieu neu errors da neu ly do cu the."),
        }
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
    channel = str(scope_channel or "").strip().upper() or None
    if channel not in {None, "OTC", "ETC"}:
        raise ValueError("scope_channel chi nhan OTC hoac ETC.")

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
        sources = [channel.lower()] if channel else ["otc", "etc"]
        selects = [
            f"SELECT doc_date, amount9 FROM vhoadon_{source} "
            "WHERE employee_code=? AND doc_date BETWEEN ? AND ?"
            for source in sources
        ]
        query_params = []
        for _source in sources:
            query_params.extend([dms_code, str(month_start), str(range_end)])
        rows = _q(
            "SELECT doc_date, SUM(amount9) rev FROM (" + " UNION ALL ".join(selects) +
            ") GROUP BY doc_date",
            tuple(query_params),
        )
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
        "employee_code": employee_code, "resolved_employee_code": resolved_code,
        "employee_name": ident.get("name"), "year_month": year_month,
        "month_sale_target": target, "target_as_of": target_as_of,
        "daily_target_pct": DAILY_KPI_TARGET_PCT,
        "days": days,
        "count_red": count_red, "count_yellow": count_yellow, "count_green": count_green,
        "month_total_sales": total_sales_month, "month_pct_of_target": month_pct,
        "channel_scope": channel,
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
        dmsid = nv[0]["dmsid"]
        if not dmsid:
            # Kho tao boi ban sync cu co the co cot dmsid nhung 100% NULL, trong khi FACT da co
            # emp_dms_code dung. Khong duoc dung nham EmployeeCode de query hoa don roi tra ca thang 0.
            try:
                mapped = _q("SELECT emp_dms_code dmsid FROM fact_tonghopkhachhang "
                            "WHERE employee_code=? AND emp_dms_code IS NOT NULL "
                            "AND TRIM(emp_dms_code)<>'' ORDER BY save_date DESC LIMIT 1",
                            (nv[0]["employee_code"],))
                dmsid = mapped[0]["dmsid"] if mapped else None
            except sqlite3.OperationalError:
                dmsid = None
        return {"code": nv[0]["employee_code"], "name": nv[0]["name"],
                "position_code": nv[0]["position_code"], "area_code": nv[0]["area_code"],
                "dmsid": dmsid or code}
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
    limit = max(1, min(int(limit or 30), 100))
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
                     scope_area_code: str = None, scope_channel: str = None,
                     scope_employee_code: str = None) -> dict:
    """So sanh nhanh doanh thu giua 2 khoang thoi gian (vd thang nay vs thang truoc, cung ky nam truoc).
    Vi kho local co day du lich su (nhieu nam) nen so sanh xa duoc, khong chi vai ngay gan day."""
    a = revenue_by_channel(date_from_a, date_to_a, scope_area_code, scope_channel, scope_employee_code)
    b = revenue_by_channel(date_from_b, date_to_b, scope_area_code, scope_channel, scope_employee_code)
    delta = a["total"]["revenue"] - b["total"]["revenue"]
    pct_change = (delta / b["total"]["revenue"] * 100) if b["total"]["revenue"] else None
    return {"period_a": a, "period_b": b, "delta": delta, "pct_change": pct_change}


def revenue_ytd_cumulative(year_month_to: str, from_month: str = None, years_back: int = 3,
                            scope_area_code: str = None, scope_channel: str = None,
                            scope_employee_code: str = None) -> dict:
    """LUY KE doanh thu tu dau ky den 1 thang chi dinh, SO SANH cung khoang do giua nhieu nam gan nhat
    - dung khi cau hoi dang "luy ke tu thang 1 den thang 7", "so voi cung ky 3 nam gan nhat", "tu dau
    nam den nay tang/giam bao nhieu so nam ngoai". KHAC voi compare_periods (chi so 2 khoang RIENG LE
    do AI tu chi dinh ngay) - ham nay TU ĐỘNG dong bo cung 1 khoang thang (vd 01-07) qua N nam LIEN
    TIEP, khong can AI tu tinh ngay cho tung nam (de sai/lech ngay khi doi nam).

    year_month_to: thang KET THUC luy ke, dang YYYY-MM (vd '2026-07') - nam cua thang nay la nam GAN
    NHAT trong so sanh, cac nam truoc do tu dong lui ve.
    from_month: thang BAT DAU luy ke trong nam, dang MM (vd '01') - mac dinh '01' (tu dau nam duong
    lich). Ap dung CHUNG cho moi nam trong so sanh (vd from_month='01' -> nam nao cung tinh tu thang 1).
    years_back: so nam GAN NHAT can so sanh KE CA nam cua year_month_to (mac dinh 3, vd year_month_to=
    '2026-07' va years_back=3 se so 2024/2025/2026, tu thang from_month den thang cua year_month_to).
    Nam nao KHONG co du lieu (chua phat sinh, vd cong ty moi mo rong sau) se bi bo qua kem ghi chu,
    KHONG hien 0 nhu the la that.

    Day la du lieu THUC TE DA PHAT SINH (khong phai du bao) - KHONG bi chinh sach khoa tinh nang tuong
    lai chan (xem feature_policy.py), dung tu do."""
    if not year_month_to or len(str(year_month_to)) != 7 or str(year_month_to)[4] != "-":
        return {"error": f"year_month_to phai o dang YYYY-MM (nhan duoc: {year_month_to})."}
    year_to = int(str(year_month_to)[:4])
    month_to = str(year_month_to)[5:7]
    from_month = (from_month or "01").zfill(2)
    if not (1 <= int(from_month) <= 12):
        return {"error": f"from_month phai tu 01 den 12 (nhan duoc: {from_month})."}
    if int(from_month) > int(month_to):
        return {"error": f"from_month ({from_month}) phai <= thang cua year_month_to ({month_to})."}

    years_back = max(1, min(int(years_back or 3), 10))
    years, skipped = [], []
    for i in range(years_back):
        y = year_to - i
        date_from = f"{y:04d}-{from_month}-01"
        date_to = f"{y:04d}-{month_to}-{_last_day_of_month(y, int(month_to)):02d}"
        r = revenue_by_channel(date_from, date_to, scope_area_code, scope_channel, scope_employee_code)
        if r["total"]["revenue"] <= 0 and r["total"]["invoices"] == 0:
            skipped.append(y)
            continue
        years.append({"year": y, "date_from": date_from, "date_to": date_to,
                      "revenue": r["total"]["revenue"], "invoices": r["total"]["invoices"],
                      "otc_revenue": r["otc"]["revenue"], "etc_revenue": r["etc"]["revenue"]})

    # Moi nam sap xep TANG DAN theo thoi gian de tinh % tang truong giua nam lien ke (nam sau so nam
    # truoc ngay ben canh), roi moi dao lai THANH GIAM DAN (nam gan nhat len dau) cho de doc khi tra loi.
    years.sort(key=lambda r: r["year"])
    for idx in range(1, len(years)):
        prev = years[idx - 1]["revenue"]
        years[idx]["pct_change_vs_prev_year"] = (
            (years[idx]["revenue"] - prev) / prev * 100 if prev else None)
    years.sort(key=lambda r: -r["year"])

    result = {
        "tu_thang": from_month, "den_thang": month_to, "cac_nam": years,
        "data_as_of": latest_data_date(),
    }
    if skipped:
        result["nam_bi_bo_qua"] = skipped
        result["ghi_chu"] = (f"Cac nam {', '.join(str(y) for y in skipped)} KHONG co du lieu phat sinh "
                              f"trong khoang thang {from_month}-{month_to} (co the chua kinh doanh giai "
                              f"doan do) - da bo qua, KHONG hien nhu doanh thu 0.")
    return result


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day


def _month_add(year_month: str, delta: int) -> str:
    """Cong/tru so thang vao chuoi 'YYYY-MM' (delta am la lui ve truoc)."""
    y, m = int(year_month[:4]), int(year_month[5:7])
    total = y * 12 + (m - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _month_bounds(year_month: str) -> tuple:
    """('YYYY-MM') -> ('YYYY-MM-01', 'YYYY-MM-<ngay cuoi thang>')."""
    y, m = int(year_month[:4]), int(year_month[5:7])
    return f"{year_month}-01", f"{year_month}-{_last_day_of_month(y, m):02d}"


def _revenue_data_month_range() -> tuple:
    """Khoang thang THUC SU co du lieu doanh thu trong kho local -> ('YYYY-MM' som nhat, muon nhat).

    24/08/2026: BAT BUOC co ham nay truoc khi lam chuoi theo thang. revenue_by_channel() tra ve 0
    cho MOI khoang ngay khong co du lieu - khong phan biet duoc "thang do doanh thu that su bang 0"
    voi "thang do CHUA duoc dong bo vao kho". Neu cu the ma ve chuoi 12-24 thang, cac thang chua co
    du lieu se hien thanh 0 dong trong nhu so THAT (xac nhan thuc te tren may dev: kho chi co thang
    7/2026, hoi thang 3/2024 tra ve dung 0 chu khong bao loi). Day dung la kieu bia so ma ca du an
    dang chong - nen chuoi thang PHAI danh dau ro thang nao nam ngoai pham vi du lieu."""
    latest = latest_data_date()[:7]
    candidates = []
    r = _q("SELECT MIN(year_month) d FROM monthly_customer_summary")
    if r and r[0]["d"]:
        candidates.append(str(r[0]["d"])[:7])
    for table in ("vhoadon_otc", "vhoadon_etc"):
        try:
            r = _q(f"SELECT MIN(doc_date) d FROM {table}")
        except Exception:
            continue
        if r and r[0]["d"]:
            candidates.append(str(r[0]["d"])[:7])
    return (min(candidates) if candidates else None), latest


def revenue_monthly_series(month_to: str = None, months_back: int = 12, include_yoy: bool = True,
                            scope_area_code: str = None, scope_channel: str = None,
                            scope_employee_code: str = None) -> dict:
    """CHUOI DOANH THU THEO TUNG THANG (moi thang 1 dong) kem MoM va YoY - dung cho MOI cau hoi dang
    "doanh thu 12 thang gan nhat", "theo tung thang", "xu huong thang qua thang", "thang nao tang/
    giam", "trung binh truot 3/6 thang". CHi CAN GOI 1 LAN cho ca chuoi.

    24/08/2026 - VI SAO CO TOOL NAY: truoc do MOI tool doanh thu (revenue_by_channel,
    revenue_by_region, top_customers...) chi nhan date_from/date_to va tra ve MOT con so TONG cho ca
    khoang, khong phai chuoi tung thang. Muon 12 thang thi model phai goi 12 lan voi 12 khoang ngay
    khac nhau - dung bang tran MAX_UNIQUE_TOOL_CALLS=12 trong nl2sql.py, tuc an TRON han muc, khong
    con luot nao de doi chieu/tinh toan; con hoi 24 thang thi BAT KHA THI. Do la nut that lam ca
    nhom cau hoi dieu hanh "month-by-month" khong tra loi duoc.

    month_to: thang CUOI cua chuoi, dang 'YYYY-MM' (mac dinh: thang co du lieu moi nhat).
    months_back: so thang tra ve, tinh CA month_to (mac dinh 12, toi da 24).
    include_yoy: TU DONG lay them 12 thang truoc do (khong hien ra) de tinh YoY cho tung thang.

    So lieu lay bang cach goi lai CHINH revenue_by_channel() cho tung thang - CO CHU DICH, khong tu
    viet SQL GROUP BY thang moi: revenue_by_channel co logic ghep 2 nguon (chi tiet 12 thang gan
    trong vhoadon_otc/etc + phan cu da nen trong monthly_customer_summary, xem _detail_cutoff) va
    toan bo co che loc pham vi vung/kenh/doi. Viet lai SQL rieng se lech so voi chinh tool doanh thu
    kia - nguoi dung hoi "doanh thu thang 7" va "chuoi 12 thang" PHAI ra cung mot con so cho thang 7.
    Do thuc te: 6-9ms/thang nen 24 thang chi ~0,2 giay.

    Thang nam NGOAI pham vi du lieu duoc danh dau "khong_co_du_lieu": true va revenue=None (KHONG
    phai 0) - xem ghi chu o _revenue_data_month_range()."""
    earliest, latest = _revenue_data_month_range()
    if not latest:
        return {"error": "Kho du lieu chua co doanh thu nao de dung chuoi theo thang."}

    month_to = (month_to or latest)[:7]
    if len(month_to) != 7 or month_to[4] != "-":
        return {"error": f"month_to phai o dang YYYY-MM (nhan duoc: {month_to})."}
    # KHONG dung "months_back or 12": so 0 la falsy nen se am tham thanh 12, trong khi so am lai bi
    # kep ve 1 - hai dau vao vo nghia cho ra hai ket qua khac han. None = khong truyen -> mac dinh
    # 12; con da truyen so thi kep thang ve [1, 24].
    months_back = 12 if months_back is None else max(1, min(int(months_back), 24))

    # Lay them 12 thang phia truoc (khong hien ra) chi de tinh YoY cho cac thang duoc hoi.
    lead = 12 if include_yoy else 0
    all_months = [_month_add(month_to, -i) for i in range(months_back + lead - 1, -1, -1)]

    rows = {}
    for ym in all_months:
        if (earliest and ym < earliest) or ym > latest:
            rows[ym] = None  # ngoai pham vi du lieu - KHONG duoc coi la 0
            continue
        d_from, d_to = _month_bounds(ym)
        r = revenue_by_channel(d_from, d_to, scope_area_code, scope_channel, scope_employee_code)
        rows[ym] = r

    shown = all_months[lead:]
    months = []
    for ym in shown:
        r = rows.get(ym)
        if r is None:
            months.append({"month": ym, "khong_co_du_lieu": True, "revenue": None})
            continue
        prev, prev_year = rows.get(_month_add(ym, -1)), rows.get(_month_add(ym, -12))
        item = {
            "month": ym,
            "otc_revenue": r["otc"]["revenue"], "etc_revenue": r["etc"]["revenue"],
            "revenue": r["total"]["revenue"], "invoices": r["total"]["invoices"],
        }
        # Thang NAM TRONG pham vi du lieu nhung khong co hoa don nao: pham vi tong the khong bat
        # duoc truong hop nay. Voi toan cong ty gan nhu chac chan la LO HONG DONG BO (DNH khong the
        # ban 0 dong ca thang); voi 1 doi QLV nho thi co the that. Khong tu ket luan - danh dau de
        # model neu ro can kiem chung, thay vi trinh bay 0 dong nhu so binh thuong.
        if r["total"]["invoices"] == 0 and not r["total"]["revenue"]:
            item["can_kiem_chung"] = ("Thang nay nam trong pham vi du lieu nhung KHONG co hoa don nao - "
                                       "co the la lo hong dong bo, khong chac la doanh thu that bang 0.")
        if prev:
            base = prev["total"]["revenue"]
            item["mom_delta"] = r["total"]["revenue"] - base
            item["mom_pct"] = ((r["total"]["revenue"] - base) / base * 100) if base else None
        if prev_year:
            base = prev_year["total"]["revenue"]
            item["yoy_delta"] = r["total"]["revenue"] - base
            item["yoy_pct"] = ((r["total"]["revenue"] - base) / base * 100) if base else None
        months.append(item)

    missing = [m["month"] for m in months if m.get("khong_co_du_lieu")]
    team_membership_basis = None
    if scope_employee_code:
        oldest_team_row = _q("SELECT MIN(save_date) d FROM fact_tonghopkhachhang")
        oldest_team_date = oldest_team_row[0]["d"] if oldest_team_row else None
        requested_before_team_history = bool(
            oldest_team_date and any(ym < str(oldest_team_date)[:7] for ym in all_months)
        )
        team_membership_basis = {
            "exact_history_from": oldest_team_date,
            "older_periods_use": "CURRENT_TEAM_MEMBERSHIP" if requested_before_team_history else None,
            "warning": (
                "Cac ky truoc moc tren duoc tinh theo DOI HIEN TAI; thanh phan doi tai ky lich su "
                "co the khac. YoY cap doi la so theo roster hien tai, khong phai tai lap co cau doi cu."
                if requested_before_team_history else None
            ),
        }
    result = {
        "month_from": shown[0], "month_to": shown[-1], "so_thang": len(shown),
        "pham_vi_du_lieu_co_that": {"tu_thang": earliest, "den_thang": latest},
        # Dat TRUOC danh sach months dai de canh bao khong bi cat khoi payload gui model.
        "team_membership_basis": team_membership_basis,
        "months": months,
        "data_as_of": latest_data_date(),
    }
    if missing:
        result["canh_bao"] = (
            f"{len(missing)}/{len(shown)} thang KHONG CO du lieu trong kho ({', '.join(missing)}) - "
            f"kho chi co tu {earliest} den {latest}. Cac thang nay tra ve revenue=None, TUYET DOI "
            "KHONG duoc trinh bay thanh 0 dong hay tinh vao trung binh/tang truong.")
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac KHONG duoc hien thi."
    return result


# ===================== VONG DOI KHACH HANG =====================
# 24/08/2026. Nhom cau hoi dieu hanh ve khach mo moi / mua lai / ngung mua truoc day KHONG co tool
# nao phu - ma vai tro TP va QLV thi KHONG duoc dung SQL tu do (xem _tools_for_request trong
# nl2sql.py), nen khong co duong lui nao ca. Xem docs/doi_chieu_138_cau_voi_tool_thuc_te.md.

# Cac cot vong doi CHi co y nghia o TANG NHAN VIEN (xem schema_context.py: "is_ro/ac CHI co o TANG
# NHAN VIEN. Luon loc tang nhan vien va COUNT(DISTINCT customer_code)"). Do thuc te 24/08/2026 tren
# snapshot that: dung SUM(is_nc) cho ra 174 trong khi so khach THAT chi 92 - sai gap 1,89 lan, vi
# bang nay co CA dong TDV lan dong rollup QLV chong len nhau (2.258 dong / 1.131 khach that).
#
# 03/09/2026 - them "TK" vao danh sach nay. TK/CS mang cap hanh chinh "QLV" (xem
# docs/chuc_vu_ma_position_code.md), nhung day KHONG dong nghia voi rollup trong bang nay:
# _rollup_tier_codes() da tung canh bao position_code sai nhan cho cap duoi cua Kenh MT/Cho si,
# nen phai kiem THAT bang manager_code chu khong suy tu ten chuc danh. Da kiem tren warehouse
# local: nguoi duy nhat mang position_code='TK' (TM23100133) tu bao cao len 'MN1' va KHONG co
# dong FACT nao khac mang manager_code=TM23100133 - tuc co ay la LA/individual contributor,
# giong het CS, khong phai diem rollup. Truoc khi sua, so_is_ac do thieu TK: 21 thay vi 22 (dung).
# Loai TK khoi danh sach nay tung lam customer_lifecycle_summary() bo qua CA BON cot dem
# (tong_khach, khach_moi, so_is_ro, so_is_ac) cho dong TK, khong chi rieng so_is_ac.
_EMPLOYEE_TIER_POSITIONS = ("TDV", "CTV", "CS", "TK")


def _tier_ph() -> str:
    """Placeholder cho _EMPLOYEE_TIER_POSITIONS. 04/09/2026: kpi_gap_run_rate va
    workforce_productivity truoc day CHEP CUNG ('TDV','CTV','CS') - khi 03/09 them 'TK' vao hang so
    thi hai ham nay khong duoc cap nhat, tiep tuc bo sot nguoi mang chuc danh TK. Dung chung ham nay
    de lan sau doi hang so la moi noi doi theo."""
    return ",".join(["?"] * len(_EMPLOYEE_TIER_POSITIONS))


def _customer_flag_caveat() -> str:
    """Canh bao BAT BUOC kem theo moi so lieu dem theo co vong doi.

    Do thuc te thang 7/2026 (thang tron ven, tang nhan vien): is_ro=5.607 khach / 30,69 ty;
    KHONG mang co nao=646 khach / 1,66 ty; is_nc=606 khach / 1,16 ty; is_ac=44 khach.
    Hai diem KHONG khop voi cach hieu thong thuong:
      - is_ac chi 44/6.859 khach trong snapshot OTC. DNH da xac nhan pham vi ngay 27/08/2026:
        day la co danh cho CS (Cho si) va TK (kenh MT), khong phai mot phep dem ASO cho TDV/QLV.
      - 646 khach khong mang co nao NHUNG VAN CO doanh thu 1,66 ty (646/646 dong deu co amount_ct>0)
        - tuc "khong co co" KHONG phai la "khong mua". Suy ra is_ro cung khong han la "mua lai" theo
        nghia thong thuong.
    Quy tac pham vi moi 27/08/2026: is_ac la co danh cho CS (Cho si) va TK (kenh MT),
    khong phai co ASO. Vi vay so_is_ac chi duoc doc tren dong thuoc mot trong hai vai tro nay;
    khong duoc suy dien TDV/QLV co is_ac thanh ASO hoac nguoc lai. Ten "Active Customer" da duoc
    xac nhan, nhung cach dem van phai noi ro la co goc Bravo, khong tu dong dong nghia voi toan bo
    khach dang mua."""
    return ("So dem theo CO GOC cua Bravo. DNH da xac nhan ten viet tat ngay 26/08/2026: "
            "NC = New Customer (khach moi), RO = Re-Order (khach dat lai hang), AC = Active Customer. "
            "Muc do TIN CAY khi tra loi thi VAN khac nhau, phai noi dung muc: "
            "(1) is_nc va is_ro dung on dinh - do 3 thang lien tiep cho thay is_nc + is_ro + (khong "
            "mang co nao) BANG DUNG tong so khach moi thang, tuc hai co loai tru nhau va cung phu "
            "~90% khach, khop voi nghia moi/dat lai. "
            "(2) is_ac: DNH xac nhan ngay 27/08/2026 day la co danh cho CS (Cho si) va TK (kenh MT), "
            "khong phai ASO. Khi dong da co is_ac thi khong duoc gan them ASO; voi CS/TK chi bao cao "
            "Active Customer. Con so is_ac lich su chi 37-44 khach/thang tren ~6.000 (0,6%) trong "
            "snapshot OTC co the hep hon so khach dang mua, nen "
            "van phai noi ro day la so co goc Bravo, khong dung no de suy ra toan bo khach dang hoat dong; "
            "muon dem khach con mua thi dung is_ro hoac dem tu hoa don. "
            "(3) Con ~8-10% khach KHONG mang co nao NHUNG VAN CO doanh thu - chua giai thich duoc, "
            "khong duoc coi la 'khong mua'.")


def customer_lifecycle_summary(year_month: str = None, months_back: int = 1,
                                scope_area_code: str = None,
                                scope_employee_code: str = None,
                                scope_channel: str = None) -> dict:
    """DEM SO KHACH theo cac co vong doi cua Bravo (khach moi / is_ro / is_ac) theo TUNG THANG, tu
    snapshot KPI FACT_TongHopKhachHang - dung cho cau hoi 'thang nay co bao nhieu khach moi', 'so
    khach mo moi tung thang', 'khach moi dong gop bao nhieu doanh thu'.

    year_month: 'YYYY-MM' thang cuoi (mac dinh: thang co snapshot moi nhat).
    months_back: so thang tra ve tinh ca thang cuoi (mac dinh 1, toi da 12).

    QUAN TRONG - doc _customer_flag_caveat(): chi rieng "khach moi" (is_nc) la nhan da on dinh;
    so_is_ro/so_is_ac van tra ve duoi ten co goc. is_ac chi ap dung cho CS (Cho si) va TK (kenh MT),
    khong phai ASO; khong dat nhan ASO cho mot dong da co is_ac.

    Moi con so deu la COUNT(DISTINCT customer_code) tren TANG NHAN VIEN (TDV/CTV/CS) cua nguon OTC - bat buoc, vi
    bang co ca dong rollup QLV chong len dong TDV (xem ghi chu o _EMPLOYEE_TIER_POSITIONS)."""
    # FACT_TongHopKhachHang noi qua DIM_NhanVien, ma danh muc nay chi phu nhan vien OTC (xem
    # docs/data_dictionary.md muc 8.2). Khong duoc tra so OTC cho tai khoan ETC roi gan nhan nhu
    # do la vong doi khach cua kenh ETC.
    if scope_channel and scope_channel.upper() != "OTC":
        return {
            "not_applicable": True,
            "error": "Nguon KPI vong doi khach hien chi phu kenh OTC; chua co nguon tuong duong cho ETC.",
            "channel_scope": scope_channel.upper(),
        }

    months_back = 1 if months_back is None else max(1, min(int(months_back), 12))
    latest = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang")
    latest = latest[0]["d"] if latest else None
    if not latest:
        return {"error": "Kho chua co snapshot KPI khach hang nao."}
    year_month = (year_month or latest)[:7]

    allowed = None
    if scope_employee_code:
        team = _team_of_qlv(scope_employee_code, latest)
        allowed = [scope_employee_code] + [t["employee_code"] for t in team]

    pos_ph = ",".join(["?"] * len(_EMPLOYEE_TIER_POSITIONS))
    months = []
    for i in range(months_back - 1, -1, -1):
        ym = _month_add(year_month, -i)
        snap = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE substr(save_date,1,7)=?", (ym,))
        snap = snap[0]["d"] if snap else None
        if not snap:
            months.append({"month": ym, "khong_co_du_lieu": True})
            continue
        sql = (f"SELECT COUNT(DISTINCT f.customer_code) tong_khach, "
               f"COUNT(DISTINCT CASE WHEN f.is_nc=1 THEN f.customer_code END) khach_moi, "
               f"COUNT(DISTINCT CASE WHEN f.is_ro=1 THEN f.customer_code END) so_is_ro, "
               f"COUNT(DISTINCT CASE WHEN f.is_ac=1 "
               f"AND UPPER(COALESCE(nv.position_code,'')) IN ('CS','TK') "
               f"THEN f.customer_code END) so_is_ac, "
               # BAY SQLite (do thuc te 24/08/2026): is_nc/is_ro luu kieu TEXT ('0'/'1') du schema
               # khai INTEGER. So sanh THANG "f.is_nc=1" van dung vi SQLite ap affinity cua COT len
               # gia tri. Nhung COALESCE(f.is_nc,0) la BIEU THUC - bieu thuc KHONG co affinity, nen
               # COALESCE(...)=0 thanh so sanh TEXT voi INTEGER va LUON SAI: dem ra 0 thay vi 646.
               # Vi vay phai so sanh TRUC TIEP tren cot, xu ly NULL bang IS NULL rieng.
               f"COUNT(DISTINCT CASE WHEN (f.is_nc IS NULL OR f.is_nc<>1) "
               f"     AND (f.is_ro IS NULL OR f.is_ro<>1) THEN f.customer_code END) khach_khong_mang_co, "
               f"SUM(CASE WHEN f.is_nc=1 THEN COALESCE(f.amount_ct,0) ELSE 0 END) doanh_so_khach_moi, "
               f"SUM(COALESCE(f.amount_ct,0)) doanh_so_tang_nhan_vien "
               f"FROM fact_tonghopkhachhang f "
               f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
               # Loc ban ghi nhan vien trung: so DEM khach thi khong bi anh huong (da COUNT DISTINCT
               # customer_code) nhung 2 truong doanh so dung SUM(amount_ct) thi SE bi thoi phong.
               f"WHERE f.save_date=? AND nv.position_code IN ({pos_ph}) "
               f"  AND {_not_duplicate_sql('nv')}")
        params = [snap, *_EMPLOYEE_TIER_POSITIONS]
        if scope_area_code:
            sql += " AND nv.area_code=?"
            params.append(scope_area_code)
        if allowed is not None:
            sql += f" AND f.employee_code IN ({','.join(['?'] * len(allowed))})"
            params.extend(allowed)
        r = _q(sql, tuple(params))[0]
        months.append({
            "month": ym, "snapshot_date": snap,
            "tong_khach": int(r["tong_khach"] or 0),
            "khach_moi": int(r["khach_moi"] or 0),
            "so_is_ro": int(r["so_is_ro"] or 0),
            "so_is_ac": int(r["so_is_ac"] or 0),
            "khach_khong_mang_co": int(r["khach_khong_mang_co"] or 0),
            "doanh_so_khach_moi": _f(r["doanh_so_khach_moi"]),
            "doanh_so_tang_nhan_vien": _f(r["doanh_so_tang_nhan_vien"]),
        })

    missing = [m["month"] for m in months if m.get("khong_co_du_lieu")]
    result = {
        "months": months,
        "tang_du_lieu": "Chi dem TANG NHAN VIEN (TDV/CTV/CS), COUNT(DISTINCT khach) - da loai dong "
                         "rollup QLV chong len de khong dem doi.",
        "canh_bao_dinh_nghia": _customer_flag_caveat(),
        "pham_vi_kenh": "OTC (nguon FACT_TongHopKhachHang noi qua DIM_NhanVien chi phu nhan vien OTC)",
        "data_as_of": latest_data_date(),
    }
    if missing:
        result["canh_bao_thieu_lich_su"] = (
            f"Khong co snapshot cho {len(missing)}/{len(months)} thang: {', '.join(missing)}. "
            "Kho fact_tonghopkhachhang chi dong bo khoang 90 ngay gan nhat; khong duoc coi cac "
            "thang thieu la 0 khach."
        )
    if scope_channel:
        result["channel_scope"] = "OTC"
    return result


def _customer_names(codes: list) -> dict:
    """Ten khach cho nhieu ma cung luc (1 truy van/bang, khong goi tung dong).

    Tra ca 2 bang danh muc: dms_khachhang (OTC) truoc, dmssx_khachhang (ETC) bu vao cho con thieu -
    giong cach customer_detail() da lam. Ma KHONG tim thay ten van duoc GIU LAI voi nhan "khong co
    trong danh muc" chu KHONG bi loai: khach "mo coi" la co that (vd HCM13508 co ~2,3 ty doanh thu
    2022-2025 ma khong co trong dms_khachhang), loai di la lam bay hoi doanh thu that."""
    codes = [c for c in dict.fromkeys(codes) if c]
    if not codes:
        return {}
    ph = ",".join(["?"] * len(codes))
    names = {}
    for table in ("dms_khachhang", "dmssx_khachhang"):
        for r in _q(f"SELECT code, name FROM {table} WHERE code IN ({ph})", tuple(codes)):
            if r["code"] not in names and r["name"]:
                names[r["code"]] = r["name"]
    return names


def customers_silent(as_of_date: str = None, silent_days: int = 60, lookback_months: int = 6,
                      limit: int = 50, scope_area_code: str = None, scope_channel: str = None,
                      scope_employee_code: str = None) -> dict:
    """DANH SACH KHACH DA NGUNG MUA / IM LANG - khach TUNG mua trong ky nhin lai nhung lan mua gan
    nhat da cach day >= silent_days. Dung cho 'khach nao ngung mua', 'khach im lang 30/60/90 ngay',
    'khach thang truoc co mua thang nay khong thay', 'khach lon nao dang mat dan'.

    KHAC customer_lifecycle_summary (dem theo co Bravo, nghia chua xac nhan): tool nay dung THANG
    LICH SU HOA DON THAT (vhoadon_otc/etc) - lan mua cuoi cung va doanh thu ky truoc deu la su kien
    co that tren chung tu, khong phu thuoc co nghiep vu nao chua duoc xac nhan.

    silent_days: so ngay khong mua toi thieu de bi liet ke (mac dinh 60).
    lookback_months: cua so nhin lai de tinh doanh thu "tung mua" (mac dinh 6 thang).
    Sap xep theo doanh thu ky truoc GIAM DAN - khach mat nhieu tien nhat len dau."""
    as_of_date = (as_of_date or latest_data_date())[:10]
    silent_days = max(1, min(int(silent_days or 60), 720))
    lookback_months = max(1, min(int(lookback_months or 6), 24))
    limit = max(1, min(int(limit or 50), 200))

    as_of = dt.date.fromisoformat(as_of_date)
    cutoff = (as_of - dt.timedelta(days=silent_days)).isoformat()
    ym_from = _month_add(as_of_date[:7], -(lookback_months - 1))
    date_from = f"{ym_from}-01"

    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    scope_sql += emp_sql
    scope_params += emp_params

    parts, part_params = [], []
    if scope_channel != "ETC":
        join_o = _otc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.customer_code, v.doc_date, v.amount9 FROM vhoadon_otc v {join_o} "
                      f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, as_of_date) + scope_params)
    if scope_channel != "OTC":
        join_e = _etc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.customer_code, v.doc_date, v.amount9 FROM vhoadon_etc v {join_e} "
                      f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, as_of_date) + scope_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung voi pham vi tai khoan."}

    sql = f"""SELECT customer_code, MAX(doc_date) lan_mua_cuoi, SUM(amount9) doanh_thu_ky_nhin_lai,
                     COUNT(DISTINCT substr(doc_date,1,7)) so_thang_co_mua
              FROM ({" UNION ALL ".join(parts)})
              GROUP BY customer_code
              HAVING MAX(doc_date) <= ? AND SUM(amount9) > 0
              ORDER BY SUM(amount9) DESC LIMIT ?"""
    params = tuple(p for pp in part_params for p in pp) + (cutoff, limit)
    rows = _q(sql, params)

    names = _customer_names([r["customer_code"] for r in rows])
    out = []
    for r in rows:
        last = str(r["lan_mua_cuoi"])[:10]
        out.append({
            "customer_code": r["customer_code"],
            "customer_name": names.get(r["customer_code"], "(khong co trong danh muc khach hang)"),
            "lan_mua_cuoi": last,
            "so_ngay_im_lang": (as_of - dt.date.fromisoformat(last)).days,
            "doanh_thu_ky_nhin_lai": _f(r["doanh_thu_ky_nhin_lai"]),
            "so_thang_co_mua": int(r["so_thang_co_mua"] or 0),
        })

    result = {
        "as_of": as_of_date, "nguong_im_lang_ngay": silent_days,
        "ky_nhin_lai": {"tu": date_from, "den": as_of_date},
        "so_khach": len(out), "khach_im_lang": out,
        "ghi_chu": ("Doanh thu o day la TONG trong ky nhin lai (khong phai doanh thu thang cuoi). "
                     "Kho local chi giu chi tiet hoa don ~12 thang gan nhat nen khach im lang lau hon "
                     "the co the khong xuat hien trong danh sach."),
        "data_as_of": latest_data_date(),
    }
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac KHONG duoc hien thi."
    return result


def _customer_monthly_activity(month_from: str, month_to: str,
                               scope_area_code: str = None,
                               scope_channel: str = None,
                               scope_employee_code: str = None) -> list:
    """Tra cac dong (thang, khach, kenh, vung, NV, doanh thu, so don) tu hai lop kho.

    Chi tiet hoa don giu khoang 12 thang; phan cu hon duoc bu tu monthly_customer_summary. Ham nay
    la nguon chung cho cohort va luong khach de hai tool khong tu lap logic ghep kho.
    """
    date_from, _ = _month_bounds(month_from)
    _, date_to = _month_bounds(month_to)
    detail_date_from = max(date_from, _detail_cutoff())
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    detail_scope_sql = scope_sql + emp_sql
    detail_scope_params = scope_params + emp_params
    parts, part_params = [], []

    if scope_channel != "ETC" and detail_date_from <= date_to:
        join = ("LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
                "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id")
        parts.append(
            "SELECT substr(v.doc_date,1,7) month, v.customer_code, 'OTC' channel, "
            "COALESCE(tp.area_code,'UNKNOWN') area_code, v.employee_code, "
            "SUM(v.amount9) revenue, COUNT(DISTINCT v.stt) orders "
            f"FROM vhoadon_otc v {join} WHERE v.doc_date BETWEEN ? AND ?{detail_scope_sql} "
            "GROUP BY month,v.customer_code,tp.area_code,v.employee_code"
        )
        part_params.append((detail_date_from, date_to) + detail_scope_params)
    if scope_channel != "OTC" and detail_date_from <= date_to:
        join = ("LEFT JOIN dmssx_khachhang kh ON kh.code=v.customer_code "
                "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id")
        parts.append(
            "SELECT substr(v.doc_date,1,7) month, v.customer_code, 'ETC' channel, "
            "COALESCE(tp.area_code,'UNKNOWN') area_code, v.employee_code, "
            "SUM(v.amount9) revenue, COUNT(DISTINCT v.stt) orders "
            f"FROM vhoadon_etc v {join} WHERE v.doc_date BETWEEN ? AND ?{detail_scope_sql} "
            "GROUP BY month,v.customer_code,tp.area_code,v.employee_code"
        )
        part_params.append((detail_date_from, date_to) + detail_scope_params)

    # Phan da nen chi chua cac thang cu hon cutoff. Ep dieu kien nay de khong dem trung neu qua
    # trinh nen/chay test de lai cung mot thang o ca bang chi tiet lan summary.
    summary_to = min(month_to, _month_add(_detail_cutoff()[:7], -1))
    if month_from <= summary_to:
        if scope_channel != "ETC":
            m_scope, m_params = _monthly_summary_scope_clause(scope_area_code, "OTC")
            m_emp, m_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
            parts.append(
                "SELECT m.year_month month,m.customer_code,'OTC' channel,"
                "COALESCE(tp.area_code,'UNKNOWN') area_code,m.employee_code,"
                "SUM(m.revenue) revenue,SUM(m.invoice_count) orders "
                "FROM monthly_customer_summary m "
                "LEFT JOIN dms_khachhang kh ON kh.code=m.customer_code "
                "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
                f"WHERE m.channel='OTC' AND m.year_month BETWEEN ? AND ?{m_scope}{m_emp} "
                "GROUP BY m.year_month,m.customer_code,tp.area_code,m.employee_code"
            )
            part_params.append((month_from, summary_to) + m_params + m_emp_params)
        if scope_channel != "OTC":
            m_scope, m_params = _monthly_summary_scope_clause(scope_area_code, "ETC")
            m_emp, m_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
            parts.append(
                "SELECT m.year_month month,m.customer_code,'ETC' channel,"
                "COALESCE(tp.area_code,'UNKNOWN') area_code,m.employee_code,"
                "SUM(m.revenue) revenue,SUM(m.invoice_count) orders "
                "FROM monthly_customer_summary m "
                "LEFT JOIN dmssx_khachhang kh ON kh.code=m.customer_code "
                "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
                f"WHERE m.channel='ETC' AND m.year_month BETWEEN ? AND ?{m_scope}{m_emp} "
                "GROUP BY m.year_month,m.customer_code,tp.area_code,m.employee_code"
            )
            part_params.append((month_from, summary_to) + m_params + m_emp_params)

    if not parts:
        return []
    sql = ("WITH a AS (" + " UNION ALL ".join(parts) + ") "
           "SELECT month,customer_code,channel,area_code,employee_code,"
           "SUM(revenue) revenue,SUM(orders) orders FROM a "
           "GROUP BY month,customer_code,channel,area_code,employee_code")
    params = tuple(p for group in part_params for p in group)
    return _q(sql, params)


def customer_cohort_retention(month_to: str = None, months_back: int = 6,
                              age_months: list = None, group_by: str = "overall",
                              scope_area_code: str = None, scope_channel: str = None,
                              scope_employee_code: str = None) -> dict:
    """Cohort theo THANG MUA DAU TIEN QUAN SAT DUOC, tinh giu chan o tuoi 1/3/6/12 thang.

    Khong gan nhan cohort nay bang IsNC cua Bravo: y nghia cohort o day duoc dinh nghia minh bach
    tu hoa don. Neu kho khong co lich su truoc thang mua dau tien thi day chi la "first observed",
    khong duoc khang dinh la lan mua dau tien trong doi khach.
    """
    earliest, latest = _revenue_data_month_range()
    if not earliest or not latest:
        return {"error": "Kho chua co lich su hoa don de tinh cohort."}
    month_to = (month_to or latest)[:7]
    months_back = max(1, min(int(months_back or 6), 24))
    ages = sorted({max(0, min(int(x), 24)) for x in (age_months or [1, 3, 6, 12])})
    if group_by not in {"overall", "channel", "area"}:
        return {"error": "group_by chi nhan overall/channel/area."}
    cohort_from = _month_add(month_to, -(months_back - 1))
    activity_to = min(latest, _month_add(month_to, max(ages or [0])))
    rows = _customer_monthly_activity(
        earliest, activity_to, scope_area_code, scope_channel, scope_employee_code)

    by_customer = {}
    for r in rows:
        c = by_customer.setdefault(r["customer_code"], {"months": set(), "first_rows": []})
        c["months"].add(r["month"])
        c["first_rows"].append(r)

    grouped = {}
    for customer_code, c in by_customer.items():
        first = min(c["months"])
        if first < cohort_from or first > month_to:
            continue
        first_row = next(r for r in c["first_rows"] if r["month"] == first)
        group = ("ALL" if group_by == "overall" else
                 first_row["channel"] if group_by == "channel" else first_row["area_code"])
        bucket = grouped.setdefault((first, group), {"customers": set(), "retained": {a: set() for a in ages}})
        bucket["customers"].add(customer_code)
        for age in ages:
            if _month_add(first, age) in c["months"]:
                bucket["retained"][age].add(customer_code)

    cohorts = []
    for (cohort_month, group), b in sorted(grouped.items()):
        size = len(b["customers"])
        retention = []
        for age in ages:
            target_month = _month_add(cohort_month, age)
            complete = target_month <= latest
            retained = len(b["retained"][age]) if complete else None
            retention.append({
                "age_month": age, "target_month": target_month,
                "retained_customers": retained,
                "retention_pct": (retained / size * 100) if complete and size else None,
                "ky_da_du": complete,
            })
        cohorts.append({"cohort_month": cohort_month, "group": group,
                        "cohort_customers": size, "retention": retention})

    return {
        "definition": "Cohort = thang co hoa don dau tien QUAN SAT DUOC trong kho; retained = co hoa don o dung thang tuoi.",
        "cohort_from": cohort_from, "cohort_to": month_to, "group_by": group_by,
        "ages": ages, "cohorts": cohorts,
        "pham_vi_du_lieu_co_that": {"tu_thang": earliest, "den_thang": latest},
        "canh_bao": ("Neu khach da mua truoc moc tu_thang cua kho, 'thang mua dau tien quan sat duoc' "
                      "KHONG phai lan mua dau tien trong doi khach. Cac tuoi co target_month sau "
                      "den_thang duoc tra None, khong coi la 0% giu chan."),
        "data_as_of": latest_data_date(),
    }


def customer_movement(month: str = None, history_months: int = 6,
                      movement_filter: str = "all", limit: int = 50,
                      scope_area_code: str = None, scope_channel: str = None,
                      scope_employee_code: str = None) -> dict:
    """Luon khach giua thang hien tai va thang truoc: moi quan sat/tai kich hoat/ngung/tang/giam."""
    earliest, latest = _revenue_data_month_range()
    if not earliest or not latest:
        return {"error": "Kho chua co hoa don de phan tich luong khach."}
    month = (month or latest)[:7]
    history_months = max(2, min(int(history_months or 6), 24))
    limit = max(1, min(int(limit or 50), 200))
    start = max(earliest, _month_add(month, -(history_months - 1)))
    prev_month = _month_add(month, -1)
    rows = _customer_monthly_activity(start, month, scope_area_code, scope_channel, scope_employee_code)

    customers = {}
    for r in rows:
        c = customers.setdefault(r["customer_code"], {"months": {}, "channels": set(), "areas": set(), "employees": {}})
        m = c["months"].setdefault(r["month"], {"revenue": 0.0, "orders": 0})
        m["revenue"] += _f(r["revenue"]); m["orders"] += int(r["orders"] or 0)
        c["channels"].add(r["channel"]); c["areas"].add(r["area_code"])
        c["employees"][r["employee_code"]] = c["employees"].get(r["employee_code"], 0.0) + _f(r["revenue"])

    names = _customer_names(list(customers))
    detail = []
    for code, c in customers.items():
        cur = c["months"].get(month, {"revenue": 0.0, "orders": 0})
        prev = c["months"].get(prev_month, {"revenue": 0.0, "orders": 0})
        earlier = sum(v["revenue"] for k, v in c["months"].items() if k < prev_month)
        if cur["revenue"] > 0 and prev["revenue"] <= 0:
            movement = "REACTIVATED" if earlier > 0 else "NEW_OR_FIRST_OBSERVED"
        elif cur["revenue"] <= 0 and prev["revenue"] > 0:
            movement = "STOPPED"
        elif cur["revenue"] > prev["revenue"]:
            movement = "GROWING"
        elif cur["revenue"] < prev["revenue"]:
            movement = "DECLINING"
        else:
            movement = "UNCHANGED"
        if movement_filter != "all" and movement != movement_filter.upper():
            continue
        emp = max(c["employees"], key=c["employees"].get) if c["employees"] else None
        detail.append({
            "customer_code": code,
            "customer_name": names.get(code, "(khong co trong danh muc khach hang)"),
            "movement": movement,
            "current_revenue": cur["revenue"], "previous_revenue": prev["revenue"],
            "delta": cur["revenue"] - prev["revenue"],
            "current_orders": cur["orders"], "previous_orders": prev["orders"],
            "has_repeat_order_current": cur["orders"] >= 2,
            "earlier_revenue_in_window": earlier,
            "employee_code": emp, "channels": sorted(c["channels"]), "areas": sorted(c["areas"]),
        })
    detail.sort(key=lambda x: abs(x["delta"]), reverse=True)
    detail = detail[:limit]

    counts = {}
    for r in detail:
        counts[r["movement"]] = counts.get(r["movement"], 0) + 1
    added = sum(r["current_revenue"] for r in detail
                if r["movement"] in {"NEW_OR_FIRST_OBSERVED", "REACTIVATED"})
    lost = sum(r["previous_revenue"] for r in detail if r["movement"] == "STOPPED")
    return {
        "month": month, "previous_month": prev_month, "history_from": start,
        "summary_on_returned_top_rows": {"counts": counts, "added_revenue": added,
                                          "lost_previous_revenue": lost, "net_offset": added - lost},
        "customers": detail,
        "canh_bao": ("NEW_OR_FIRST_OBSERVED chi co nghia la lan dau THAY trong cua so du lieu dang co; "
                      "khong duoc khang dinh la khach moi trong doi neu kho thieu lich su truoc do. "
                      "Summary chi tong tren cac dong tra ve sau limit, khong phai tong toan bo neu bi cat."),
        "data_as_of": latest_data_date(),
    }


def kpi_gap_run_rate(as_of_date: str = None, group_by: str = "employee", limit: int = 50,
                     scope_area_code: str = None, scope_channel: str = None,
                     scope_employee_code: str = None) -> dict:
    """Khoang thieu toi 65/70/80/100/120% va run-rate TUYEN TINH, khong phai du bao."""
    if scope_channel and scope_channel.upper() != "OTC":
        return {"not_applicable": True,
                "error": "Nguon KPI/target hien chi phu doi ngu OTC; khong co target ETC tuong duong.",
                "channel_scope": scope_channel.upper()}
    if group_by not in {"employee", "qlv", "area", "total"}:
        return {"error": "group_by chi nhan employee/qlv/area/total."}
    fdate = _fact_date_le(as_of_date)
    if not fdate:
        return {"error": "Khong co snapshot KPI phu hop."}
    limit = max(1, min(int(limit or 50), 200))

    rows = []
    if group_by == "employee":
        # 04/09/2026 - LOI MAU SO DA SUA: truoc day lay nen tu fact_tonghopkhachhang (1 dong/(NV x
        # khach hang)). Nhan vien KHONG duoc giao khach nao thi KHONG co dong nao -> vo hinh voi moi
        # cach gop tu duoi len (chinh loi da duoc ghi nhan trong kpi_ranking cho tang vung). Hau qua:
        # 29 TDV bien mat khoi mau so ngay 31/08/2026 va HO DEU DUOI NGUONG, nen moi ty le deu bi
        # thoi phong (TDV dat >=80%: bao 45% trong khi that la 38%; rieng MN bao 81% vs that 57%).
        # fact_thongketinhluong la snapshot 1 DONG/NHAN VIEN nen mau so day du. GIU NGUYEN loc chuc
        # danh TDV/CTV/CS: dong QLV la ROLLUP cua TDV, tron vao se dem gap doi (lat cat song song).
        sql = ("SELECT f.employee_code,COALESCE(f.employee_name,nv.name) name,f.position_code,"
               "f.area_code,MAX(f.manager_code) manager_code,"
               "MAX(COALESCE(f.month_sale_amount,0)) actual,MAX(COALESCE(f.month_sale_target,0)) target "
               "FROM fact_thongketinhluong f LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
               f"WHERE f.save_date=? AND UPPER(COALESCE(f.position_code,'')) IN ({_tier_ph()}) "
               f"AND (nv.employee_code IS NULL OR {_not_duplicate_sql('nv')})")
        params = [fdate, *_EMPLOYEE_TIER_POSITIONS]
        if scope_area_code:
            sql += " AND f.area_code=?"; params.append(scope_area_code)
        if scope_employee_code:
            team = _team_of_qlv(scope_employee_code, fdate)
            codes = [r["employee_code"] for r in team]
            if not codes:
                raise KhongXacDinhDuocDoi(f"Khong xac dinh duoc doi cua {scope_employee_code}.")
            sql += f" AND f.employee_code IN ({','.join(['?'] * len(codes))})"
            params.extend(codes)
        sql += " GROUP BY f.employee_code,COALESCE(f.employee_name,nv.name),f.position_code,f.area_code"
        rows = _q(sql, tuple(params))
        for r in rows:
            r["group_code"] = r["employee_code"]
            r["group_name"] = r["name"] or r["employee_code"]
    elif group_by == "qlv":
        base = kpi_ranking("qlv", fdate, 999, scope_area_code, scope_employee_code)
        for r in base:
            rows.append({"group_code": r["employee_code"], "group_name": r["name"],
                         "position_code": "QLV", "area_code": r.get("area_code"),
                         "actual": r["sales"], "target": r["target"],
                         "la_nhom_kenh": r.get("la_nhom_kenh", False)})
    else:
        # QLV hoi "tong"/"vung" trong tool gap phai ra tong DOI CUA HO, khong phai tong ca mien.
        # Du lieu gap la hieu suat ca nhan/doi, nhay cam hon bao cao doanh thu tong hop theo mien.
        if scope_employee_code:
            own = kpi_ranking("qlv", fdate, 1, scope_area_code, scope_employee_code)
            actual = sum(_f(r["sales"]) for r in own)
            target = sum(_f(r["target"]) for r in own)
            area = own[0].get("area_code") if own else scope_area_code
            rows = [{"group_code": scope_employee_code, "group_name": "Tong doi cua ban",
                     "position_code": "QLV", "area_code": area,
                     "actual": actual, "target": target}]
            base = None
        else:
            base = kpi_ranking("region", fdate, 99, scope_area_code, None)
        if base is None:
            pass
        elif group_by == "area":
            rows = [{"group_code": r["area_code"], "group_name": r["area_code"],
                     "position_code": "AREA", "area_code": r["area_code"],
                     "actual": r["sales"], "target": r["target"]} for r in base]
        else:
            rows = [{"group_code": "ALL", "group_name": "Toan bo pham vi",
                     "position_code": "TOTAL", "area_code": scope_area_code,
                     "actual": sum(_f(r["sales"]) for r in base),
                     "target": sum(_f(r["target"]) for r in base)}]

    y, m = int(fdate[:4]), int(fdate[5:7])
    month_days = _last_day_of_month(y, m)
    elapsed = min(int(fdate[8:10]), month_days)
    remaining = max(0, month_days - elapsed)
    complete_month = elapsed >= month_days
    result_rows = []
    for r in rows:
        actual, target = _f(r.get("actual")), _f(r.get("target"))
        pct = actual / target * 100 if target else None
        projected = actual if complete_month else (actual / elapsed * month_days if elapsed else None)
        position = (r.get("position_code") or "").upper()
        bonus_gate = 65 if position == "TDV" else 70
        out = {**r, "actual": actual, "target": target, "achievement_pct": pct,
               "bonus_gate_pct": bonus_gate, "elapsed_calendar_days": elapsed,
               "remaining_calendar_days": remaining,
               "linear_run_rate": projected,
               "linear_run_rate_pct": (projected / target * 100) if projected is not None and target else None}
        for threshold in (65, 70, 80, 100, 120):
            gap = max(0.0, target * threshold / 100 - actual)
            out[f"gap_{threshold}"] = gap
            out[f"needed_per_remaining_day_{threshold}"] = (gap / remaining if remaining else (0.0 if gap == 0 else None))
        result_rows.append(out)
    result_rows.sort(key=lambda r: (r["achievement_pct"] is None, r["achievement_pct"] or 0))
    threshold_summary = [
        {
            "threshold_pct": threshold,
            "count": sum(1 for r in result_rows
                         if r["achievement_pct"] is not None and r["achievement_pct"] >= threshold),
            "total_with_target": sum(1 for r in result_rows if r["achievement_pct"] is not None),
        }
        for threshold in (65, 70, 80, 100, 120)
    ]
    return {
        "as_of": fdate, "group_by": group_by, "rows": result_rows[:limit],
        # Tra san phep dem tren TOAN BO tap du lieu truoc limit. Model khong duoc dem bang tay tren
        # danh sach bi cat (UAT tung bao 3/7 nguoi >=80% trong khi ket qua dung la 2/7).
        "threshold_summary": threshold_summary,
        "definition": ("linear_run_rate = doanh so luy ke / so ngay lich da qua * so ngay trong thang. "
                       "Day CHI la ngoai suy tuyen tinh, KHONG phai forecast/xac suat dat."),
        "thresholds": {"65_70": "cong thuong theo vai tro", "80": "dat KPI",
                       "100": "dat chi tieu", "120": "vuot 120%"},
        "pham_vi_kenh": "OTC",
    }


def cross_sell_opportunities(as_of_date: str = None, lookback_months: int = 3,
                             min_together_orders: int = 2, pair_limit: int = 20,
                             opportunity_limit: int = 100,
                             scope_area_code: str = None, scope_channel: str = None,
                             scope_employee_code: str = None) -> dict:
    """Cap SKU mua cung va khach da mua A nhung chua mua B trong cua so nhin lai."""
    as_of_date = (as_of_date or latest_data_date())[:10]
    lookback_months = max(1, min(int(lookback_months or 3), 12))
    pair_limit = max(1, min(int(pair_limit or 20), 100))
    opportunity_limit = max(1, min(int(opportunity_limit or 100), 500))
    month_from = _month_add(as_of_date[:7], -(lookback_months - 1))
    date_from = f"{month_from}-01"

    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    parts, param_groups = [], []
    if scope_channel != "ETC":
        join = _otc_area_join("v", scope_area_code)
        parts.append("SELECT 'OTC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,v.customer_code,v.item_code,"
                     f"v.amount9 FROM vhoadon_otc v {join} WHERE v.doc_date BETWEEN ? AND ? "
                     f"AND COALESCE(v.unit_price,0)>0 AND v.item_code IS NOT NULL{suffix}")
        param_groups.append((date_from, as_of_date) + suffix_params)
    if scope_channel != "OTC":
        join = _etc_area_join("v", scope_area_code)
        parts.append("SELECT 'ETC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,v.customer_code,v.item_code,"
                     f"v.amount9 FROM vhoadon_etc v {join} WHERE v.doc_date BETWEEN ? AND ? "
                     f"AND COALESCE(v.unit_price,0)>0 AND v.item_code IS NOT NULL{suffix}")
        param_groups.append((date_from, as_of_date) + suffix_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung."}
    lines_cte = "WITH lines AS (" + " UNION ALL ".join(parts) + ") "
    params = tuple(p for group in param_groups for p in group)
    pair_rows = _q(
        lines_cte +
        "SELECT a.item_code item_a,b.item_code item_b,COUNT(DISTINCT a.order_key) together_orders "
        "FROM lines a JOIN lines b ON b.order_key=a.order_key AND b.item_code>a.item_code "
        "GROUP BY a.item_code,b.item_code HAVING COUNT(DISTINCT a.order_key)>=? "
        "ORDER BY together_orders DESC LIMIT ?",
        params + (max(1, int(min_together_orders or 2)), pair_limit))

    item_codes = sorted({r[k] for r in pair_rows for k in ("item_a", "item_b")})
    names = {}
    if item_codes:
        ph = ",".join(["?"] * len(item_codes))
        names = {r["code"]: (r["name"] or r["code"]) for r in
                 _q(f"SELECT code,name FROM brv_sanpham WHERE code IN ({ph})", tuple(item_codes))}
    item_customers = {}
    customer_revenue = {}
    if item_codes:
        ph = ",".join(["?"] * len(item_codes))
        for r in _q(lines_cte +
                    f"SELECT customer_code,item_code,SUM(amount9) revenue FROM lines WHERE item_code IN ({ph}) "
                    "GROUP BY customer_code,item_code", params + tuple(item_codes)):
            item_customers.setdefault(r["item_code"], set()).add(r["customer_code"])
            customer_revenue[r["customer_code"]] = customer_revenue.get(r["customer_code"], 0.0) + _f(r["revenue"])

    opportunities = []
    for p in pair_rows:
        for owned, missing in ((p["item_a"], p["item_b"]), (p["item_b"], p["item_a"])):
            for customer in item_customers.get(owned, set()) - item_customers.get(missing, set()):
                opportunities.append({"customer_code": customer, "has_item": owned,
                                      "has_item_name": names.get(owned, owned),
                                      "missing_item": missing, "missing_item_name": names.get(missing, missing),
                                      "pair_together_orders": int(p["together_orders"]),
                                      "revenue_on_pair_items": customer_revenue.get(customer, 0.0)})
    opportunities.sort(key=lambda r: (-r["pair_together_orders"], -r["revenue_on_pair_items"]))
    customer_names = _customer_names([r["customer_code"] for r in opportunities[:opportunity_limit]])
    for r in opportunities[:opportunity_limit]:
        r["customer_name"] = customer_names.get(r["customer_code"], "(khong co trong danh muc khach hang)")
    return {
        "date_from": date_from, "date_to": as_of_date,
        "pairs": [{**p, "item_a_name": names.get(p["item_a"], p["item_a"]),
                    "item_b_name": names.get(p["item_b"], p["item_b"])} for p in pair_rows],
        "opportunities": opportunities[:opportunity_limit],
        "definition": ("Co hoi = khach da mua mot SKU cua cap thuong mua cung trong cua so nhin lai "
                       "nhung chua mua SKU con lai. Day la goi y tu dong mua kem, KHONG phai ket luan nhu cau."),
        "canh_bao": "Chi tiet SKU/hoa don chi duoc giu khoang 12 thang; lookback da bi gioi han toi da 12.",
        "data_as_of": latest_data_date(),
    }


def customer_product_coverage(as_of_date: str = None, lookback_months: int = 3,
                              mode: str = "customer", limit: int = 100,
                              scope_area_code: str = None, scope_channel: str = None,
                              scope_employee_code: str = None) -> dict:
    """Do phu va benchmark noi bo theo khach/san pham/nhan vien, co so sanh ky truoc cung do dai."""
    if mode not in {"customer", "product", "employee"}:
        return {"error": "mode chi nhan customer/product/employee."}
    as_of_date = (as_of_date or latest_data_date())[:10]
    lookback_months = max(1, min(int(lookback_months or 3), 12))
    limit = max(1, min(int(limit or 100), 500))
    current_month_from = _month_add(as_of_date[:7], -(lookback_months - 1))
    current_from = f"{current_month_from}-01"
    current_start_date = dt.date.fromisoformat(current_from)
    current_end_date = dt.date.fromisoformat(as_of_date)
    window_days = (current_end_date - current_start_date).days + 1
    previous_end_date = current_start_date - dt.timedelta(days=1)
    if lookback_months == 1:
        # So sanh MTD/thang tron voi CUNG CAC NGAY DA TROI QUA cua thang truoc. Ban cu dung cua so
        # lien ke (vd 01-04/09 lai so voi 28-31/08), khien cau "thang nay ai dong gop tang/giam"
        # khong cung diem trong chu ky ban hang va cho ket luan sai.
        previous_ym = _month_add(as_of_date[:7], -1)
        py, pm = int(previous_ym[:4]), int(previous_ym[5:7])
        aligned_day = min(current_end_date.day, _last_day_of_month(py, pm))
        previous_from = f"{previous_ym}-01"
        previous_to = f"{previous_ym}-{aligned_day:02d}"
        comparison_basis = "CUNG NGAY TRONG THANG TRUOC (MTD-aligned)"
    else:
        previous_to = previous_end_date.isoformat()
        previous_from = (previous_end_date - dt.timedelta(days=window_days - 1)).isoformat()
        comparison_basis = "CUA SO LIEN KE CUNG SO NGAY"
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params

    parts, params = [], []
    for period, date_from, date_to in (("CURRENT", current_from, as_of_date),
                                       ("PREVIOUS", previous_from, previous_to)):
        if scope_channel != "ETC":
            join = (_otc_area_join("v", scope_area_code) +
                    " LEFT JOIN dim_nhanvien nv ON nv.dmsid=v.employee_code")
            parts.append(f"SELECT '{period}' period,v.customer_code,v.item_code,v.amount9,v.quantity,"
                         "'OTC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                         f"COALESCE(nv.employee_code,v.employee_code) employee_code FROM vhoadon_otc v {join} "
                         f"WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}")
            params.extend((date_from, date_to) + suffix_params)
        if scope_channel != "OTC":
            join = (_etc_area_join("v", scope_area_code) +
                    " LEFT JOIN dim_nhanvien nv ON nv.dmsid=v.employee_code")
            parts.append(f"SELECT '{period}' period,v.customer_code,v.item_code,v.amount9,v.quantity,"
                         "'ETC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                         f"COALESCE(nv.employee_code,v.employee_code) employee_code FROM vhoadon_etc v {join} "
                         f"WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}")
            params.extend((date_from, date_to) + suffix_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung."}
    cte = "WITH lines AS (" + " UNION ALL ".join(parts) + ") "
    dim = {"customer": "customer_code", "product": "item_code", "employee": "employee_code"}[mode]
    raw = _q(
        cte + f"SELECT period,{dim} code,SUM(amount9) revenue,SUM(quantity) quantity,"
        "COUNT(DISTINCT order_key) orders,COUNT(DISTINCT customer_code) customers,"
        "COUNT(DISTINCT item_code) products FROM lines "
        f"WHERE {dim} IS NOT NULL AND TRIM({dim})<>'' GROUP BY period,{dim}", tuple(params))
    totals_raw = _q(
        cte + "SELECT period,SUM(amount9) revenue,SUM(quantity) quantity,"
        "COUNT(DISTINCT order_key) orders,COUNT(DISTINCT customer_code) customers,"
        "COUNT(DISTINCT item_code) products FROM lines GROUP BY period", tuple(params))
    totals_by_period = {r["period"]: r for r in totals_raw}
    by_code = {}
    for r in raw:
        by_code.setdefault(r["code"], {})[r["period"]] = r

    customer_names = _customer_names(list(by_code)) if mode == "customer" else {}
    product_names = {}
    if mode == "product" and by_code:
        ph = ",".join(["?"] * len(by_code))
        product_names = {r["code"]: r["name"] for r in
                         _q(f"SELECT code,name FROM brv_sanpham WHERE code IN ({ph})", tuple(by_code))}
    employee_names = {}
    if mode == "employee" and by_code:
        ph = ",".join(["?"] * len(by_code))
        employee_names = {r["employee_code"]: r["name"] for r in
                          _q(f"SELECT employee_code,name FROM dim_nhanvien WHERE employee_code IN ({ph})", tuple(by_code))}

    rows = []
    for code, periods in by_code.items():
        cur = periods.get("CURRENT", {})
        prev = periods.get("PREVIOUS", {})
        if not cur and mode != "employee":
            continue
        row = {
            "code": code,
            "name": (customer_names.get(code) if mode == "customer" else
                     product_names.get(code) if mode == "product" else employee_names.get(code)) or code,
            "revenue": _f(cur.get("revenue")), "orders": int(cur.get("orders") or 0),
            "customers": int(cur.get("customers") or 0), "products": int(cur.get("products") or 0),
            "quantity": _f(cur.get("quantity")),
            "aov": _f(cur.get("revenue")) / int(cur.get("orders") or 1),
            "previous_revenue": _f(prev.get("revenue")),
            "previous_orders": int(prev.get("orders") or 0),
            "previous_customers": int(prev.get("customers") or 0),
            "previous_quantity": _f(prev.get("quantity")),
            "previous_products": int(prev.get("products") or 0),
        }
        row["frequency"] = row["orders"] / row["customers"] if row["customers"] else None
        row["previous_aov"] = (row["previous_revenue"] / row["previous_orders"]
                               if row["previous_orders"] else None)
        row["previous_frequency"] = (row["previous_orders"] / row["previous_customers"]
                                     if row["previous_customers"] else None)
        row["revenue_delta"] = row["revenue"] - row["previous_revenue"]
        row["orders_delta"] = row["orders"] - row["previous_orders"]
        row["customers_delta"] = row["customers"] - row["previous_customers"]
        row["quantity_delta"] = row["quantity"] - row["previous_quantity"]
        row["aov_delta"] = row["aov"] - row["previous_aov"] if row["previous_aov"] is not None else None
        row["frequency_delta"] = (row["frequency"] - row["previous_frequency"]
                                  if row["frequency"] is not None and row["previous_frequency"] is not None
                                  else None)
        row["products_delta"] = row["products"] - row["previous_products"]
        rows.append(row)
    avg_products = sum(r["products"] for r in rows) / len(rows) if rows else 0.0
    avg_revenue = sum(r["revenue"] for r in rows) / len(rows) if rows else 0.0
    for r in rows:
        r["product_gap_vs_scope_avg"] = avg_products - r["products"]
        r["revenue_gap_vs_scope_avg"] = avg_revenue - r["revenue"]
        if mode == "product":
            r["revenue_per_customer"] = r["revenue"] / r["customers"] if r["customers"] else None
            r["quantity_per_order"] = r["quantity"] / r["orders"] if r["orders"] else None
    if mode == "employee":
        rows.sort(key=lambda r: (-abs(r["revenue_delta"]), -r["revenue"]))
    else:
        rows.sort(key=lambda r: (-r["product_gap_vs_scope_avg"], -r["revenue"]))

    def _period_total(period):
        raw_total = totals_by_period.get(period, {})
        orders = int(raw_total.get("orders") or 0)
        customers = int(raw_total.get("customers") or 0)
        revenue = _f(raw_total.get("revenue"))
        return {
            "revenue": revenue, "orders": orders, "customers": customers,
            "quantity": _f(raw_total.get("quantity")),
            "aov": revenue / orders if orders else None,
            "frequency": orders / customers if customers else None,
        }

    current_total, previous_total = _period_total("CURRENT"), _period_total("PREVIOUS")
    total_change = {
        key + "_delta": (current_total[key] - previous_total[key]
                          if current_total[key] is not None and previous_total[key] is not None else None)
        for key in ("revenue", "orders", "customers", "quantity", "aov", "frequency")
    }
    active_rows = [r for r in rows if r["revenue"] or r["previous_revenue"]]
    increase_rows = [r for r in active_rows if r["revenue_delta"] > 0]
    decrease_rows = [r for r in active_rows if r["revenue_delta"] < 0]
    return {
        "mode": mode, "window_days": window_days,
        "current_period": {"from": current_from, "to": as_of_date},
        "previous_period": {"from": previous_from, "to": previous_to},
        "comparison_basis": comparison_basis,
        "scope_totals": {"current": current_total, "previous": previous_total, **total_change},
        "customer_count_definition": (
            "scope_totals.*.customers = COUNT(DISTINCT customer_code) tren hoa don cua TOAN BO "
            "pham vi doi sau khi phan giai DMSId; day la so khach mua that, KHONG phai tong cong "
            "so khach tung TDV va KHONG phai co khach moi/is_ro/is_ac."
        ),
        "scope_benchmarks": {"avg_products": avg_products, "avg_revenue": avg_revenue},
        "rows": rows[:limit],
        "largest_increase": (max(increase_rows, key=lambda r: r["revenue_delta"])
                             if mode == "employee" and increase_rows else None),
        "largest_decrease": (min(decrease_rows, key=lambda r: r["revenue_delta"])
                             if mode == "employee" and decrease_rows else None),
        "definition": (f"Ky so sanh: {comparison_basis}. Benchmark la "
                       "trung binh NOI BO cua dung pham vi tai khoan va cua so duoc hoi. "
                       "Khong phai market share/share-of-wallet ben ngoai DNH. product_gap > 0 nghia "
                       "la mua it SKU hon trung binh pham vi, khong tu dong dong nghia co nhu cau."),
        "canh_bao": "Chi tiet san pham/hoa don chi giu khoang 12 thang; moi cua so bi gioi han toi da 12.",
        "data_as_of": latest_data_date(),
    }


def _giu_top_don_vi(rows, khoa_don_vi, khoa_gia_tri, limit):
    """Cat danh sach chuoi-theo-thang bang cach GIU LAI top `limit` DON VI (tinh/mien/nhan vien/QLV)
    va giu DU MOI THANG cua cac don vi do - thay vi cat `rows[-limit:]`.

    26/08/2026 - VI SAO PHAI SUA: hai tool chuoi thang truoc day tra ve `rows[-limit:]`, tuc cat tu
    DUOI mang da sap xep theo (thang tang dan, thu hang tot dan). Cat kieu do gay ra HAI hong cung luc,
    deu am tham:
      1. Mat cac thang DAU - dung thu can nhat de nhin xu huong. Cau hoi "tinh nao giam lien tiep
         nhieu thang" nhan ve du lieu chi con vai thang cuoi.
      2. Giu lai don vi TE NHAT, vut don vi TOT NHAT. Trong thang bi cat do dang, phan con lai la
         duoi bang xep hang. Model goi limit=10 y muon "top 10 tinh" thi nhan dung 10 tinh BET NHAT.
    Do quy mo that: 63 tinh x 6 thang = 378 dong > limit mac dinh 100 -> cat mat 3/4 chuoi. Voi
    workforce_productivity group_by='employee': 281 nhan vien x 6 thang = 1.686 dong > 200 -> chi con
    dung thang cuoi va 200 nguoi thap nhat.

    11 tool khac trong file nay deu dung `[:limit]` SAU khi sap theo do quan trong - hai cho nay la
    ngoai le lac loai, khong phai chu y thiet ke.

    `limit` gio co nghia la SO DON VI giu lai (khong phai so dong). Chon top theo TONG gia tri ca cua
    so, khong theo thang cuoi - de mot thang bat thuong khong hat mot tinh lon ra khoi bang.
    Tra ve (rows_da_loc, so_don_vi_bi_cat) - so bi cat PHAI duoc bao ra ngoai de model noi ro cho
    nguoi dung, dung nguyen tac "tha noi khong biet con hon giau"."""
    tong = {}
    for r in rows:
        k = r.get(khoa_don_vi)
        tong[k] = tong.get(k, 0.0) + (r.get(khoa_gia_tri) or 0.0)
    if len(tong) <= limit:
        return rows, 0
    giu = {k for k, _ in sorted(tong.items(), key=lambda kv: -kv[1])[:limit]}
    return [r for r in rows if r.get(khoa_don_vi) in giu], len(tong) - len(giu)


def geography_monthly_performance(month_to: str = None, months_back: int = 6,
                                  dimension: str = "area", limit: int = 100,
                                  scope_area_code: str = None, scope_channel: str = None,
                                  scope_employee_code: str = None) -> dict:
    """Doanh thu/khach/don theo thang va dia ban: mien (area) hoac tinh (city)."""
    if dimension in {"branch", "npp", "distributor"}:
        return {"not_applicable": True, "error": (
            "Kho local chua co khoa chi nhanh/NPP/distributor tren hoa don va danh muc khach; "
            "khong the drill-down chinh xac den chieu nay.")}
    if dimension not in {"area", "city"}:
        return {"error": "dimension chi nhan area/city; branch/NPP hien chua co nguon."}
    earliest, latest = _revenue_data_month_range()
    if not earliest or not latest:
        return {"error": "Kho chua co hoa don."}
    month_to = (month_to or latest)[:7]
    months_back = max(1, min(int(months_back or 6), 12))
    month_from = _month_add(month_to, -(months_back - 1))
    date_from, _ = _month_bounds(month_from); _, date_to = _month_bounds(month_to)
    limit = max(1, min(int(limit or 100), 500))
    # 26/08/2026: ham nay CHi truy van vhoadon_otc/etc, KHONG cong monthly_customer_summary nhu
    # revenue_by_channel lam - vi bang nen khong co khoa tinh (chi co khach + nhan vien), suy tinh
    # phai di qua danh muc khach HIEN TAI, tuc gan tinh hom nay cho doanh thu nam ngoai.
    # DA QUYET 26/08/2026: GIU NGUYEN, khong bu tu bang nen. Doi lay so "co ve day du" bang cach quy
    # sai vung cho khach da chuyen dia ban la danh doi khong dang - bao cao dia ban chi phu 12 thang
    # gan nhat, va noi ro dieu do. DUNG mo lai cach bu nay neu khong co khoa tinh trong bang nen.
    # Nhung viec CHUA sua duoc khong cho phep IM LANG: neu khong bao gi, thang nam ngoai cua so chi
    # tiet se ra 0 dong trong khi tool doanh thu tra ve so that - cung mot thang, hai con so, va
    # model rat de doc 0 thanh "dia ban do khong ban duoc gi". Bao ra thanh mot truong rieng de model
    # buoc phai noi lai.
    cutoff = _detail_cutoff()
    ngoai_cua_so = date_from < cutoff
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    unit_expr = "COALESCE(tp.area_code,'UNKNOWN')" if dimension == "area" else "COALESCE(tp.city_name,'UNKNOWN')"
    parts, groups = [], []
    if scope_channel != "ETC":
        parts.append(f"SELECT substr(v.doc_date,1,7) month,{unit_expr} unit,tp.area_code,"
                     "v.amount9 revenue,'OTC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                     "v.customer_code,v.quantity,v.unit_price FROM vhoadon_otc v "
                     "LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
                     f"LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id WHERE v.doc_date BETWEEN ? AND ?{suffix} "
                     "")
        groups.append((date_from, date_to) + suffix_params)
    if scope_channel != "OTC":
        parts.append(f"SELECT substr(v.doc_date,1,7) month,{unit_expr} unit,tp.area_code,"
                     "v.amount9 revenue,'ETC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                     "v.customer_code,v.quantity,v.unit_price FROM vhoadon_etc v "
                     "LEFT JOIN dmssx_khachhang kh ON kh.code=v.customer_code "
                     f"LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id WHERE v.doc_date BETWEEN ? AND ?{suffix} "
                     "")
        groups.append((date_from, date_to) + suffix_params)
    sql = ("WITH x AS (" + " UNION ALL ".join(parts) + ") SELECT month,unit,area_code,"
           "SUM(revenue) revenue,COUNT(DISTINCT order_key) invoices,COUNT(DISTINCT customer_code) customers,"
           "SUM(CASE WHEN COALESCE(unit_price,0)>0 THEN quantity ELSE 0 END) paid_quantity "
           "FROM x GROUP BY month,unit,area_code")
    raw = _q(sql, tuple(p for g in groups for p in g)) if parts else []
    for r in raw:
        r["revenue"] = _f(r.get("revenue"))
        r["paid_quantity"] = _f(r.get("paid_quantity"))
        r["invoices"] = int(r.get("invoices") or 0)
        r["customers"] = int(r.get("customers") or 0)
        r["aov"] = r["revenue"] / r["invoices"] if r["invoices"] else None
        r["orders_per_customer"] = r["invoices"] / r["customers"] if r["customers"] else None

    by_unit = {}
    totals = {}
    for r in raw:
        r["revenue"] = _f(r["revenue"]); r["invoices"] = int(r["invoices"] or 0)
        r["customers"] = int(r["customers"] or 0)
        by_unit.setdefault(r["unit"], {})[r["month"]] = r
        totals[r["month"]] = totals.get(r["month"], 0.0) + r["revenue"]
    rows = []
    for unit, monthly in by_unit.items():
        streak_dir, streak_len = None, 0
        for ym in sorted(monthly):
            r = monthly[ym]
            prev = monthly.get(_month_add(ym, -1))
            delta = r["revenue"] - prev["revenue"] if prev else None
            direction = "UP" if delta is not None and delta > 0 else "DOWN" if delta is not None and delta < 0 else "FLAT"
            if delta is not None:
                if direction == streak_dir: streak_len += 1
                else: streak_dir, streak_len = direction, 1
            rows.append({**r, "mom_delta": delta,
                         "mom_pct": (delta / prev["revenue"] * 100) if prev and prev["revenue"] else None,
                         "share_pct": r["revenue"] / totals[ym] * 100 if totals.get(ym) else None,
                         "streak_direction": streak_dir, "streak_months": streak_len})
    for ym in sorted({r["month"] for r in rows}):
        month_rows = sorted([r for r in rows if r["month"] == ym], key=lambda r: -r["revenue"])
        for rank, r in enumerate(month_rows, 1): r["rank"] = rank
    rows.sort(key=lambda r: (r["month"], r.get("rank", 999)))
    # Thu hang (rank) va ty trong (share_pct) da tinh trên TOAN BO dia ban o tren, truoc khi cat -
    # nen so lieu cua cac don vi duoc giu van dung tuong quan voi ca nuoc, khong bi tinh lai theo
    # nhom con.
    rows, so_bi_cat = _giu_top_don_vi(rows, "unit", "revenue", limit)
    ket_qua = {"month_from": month_from, "month_to": month_to, "dimension": dimension,
            "customer_count_definition": (
                "customers = COUNT(DISTINCT customer_code) tren hoa don da loc day du pham vi doi. "
                "Khong thay bang co khach moi/is_ro/is_ac va khong goi la uoc tinh."
            ),
            "rows": rows, "so_dia_ban_khong_hien": so_bi_cat,
            "unavailable_dimensions": ["branch", "NPP", "distributor"],
            "canh_bao": ("UNKNOWN la khach/hoa don khong noi duoc danh muc tinh. Khong duoc tu gan "
                          "vung/tinh cho nhom nay. Chi tiet dia ban chi nam trong cua so hoa don gan."),
            "data_as_of": latest_data_date()}
    if ngoai_cua_so:
        ket_qua["thieu_du_lieu_truoc_ngay"] = cutoff
        ket_qua["canh_bao_ngoai_cua_so"] = (
            f"Khoang duoc hoi bat dau tu {date_from}, TRUOC moc {cutoff} - phan truoc moc do da bi "
            "nen thanh bang thang KHONG CO khoa tinh/mien, nen bao cao dia ban KHONG bao gom phan "
            "do. Cac thang truoc moc se hien 0 hoac khong xuat hien: day la KHONG CO DU LIEU DIA "
            "BAN, TUYET DOI khong duoc doc thanh 'dia ban do khong ban duoc gi'. Tong doanh thu cac "
            "thang do van tra cuu duoc bang get_revenue_monthly_series (co gop nguon nen) - neu can "
            "so tong thi dung tool do va noi ro la khong tach duoc theo dia ban.")
    return ket_qua


def workforce_productivity(month_to: str = None, months_back: int = 6,
                           group_by: str = "manager", limit: int = 200,
                           scope_area_code: str = None, scope_channel: str = None,
                           scope_employee_code: str = None) -> dict:
    """Nang suat thang theo nhan vien/QLV/vung, headcount, span va streak tang-giam."""
    if scope_channel and scope_channel.upper() != "OTC":
        return {"not_applicable": True,
                "error": "Nguon KPI nhan su hien khong co chieu kenh ETC de ep phan quyen.",
                "channel_scope": scope_channel.upper()}
    if group_by not in {"employee", "manager", "area", "total"}:
        return {"error": "group_by chi nhan employee/manager/area/total."}
    latest_r = _q("SELECT MAX(save_date) d FROM fact_thongketinhluong")
    latest = latest_r[0]["d"] if latest_r and latest_r[0]["d"] else None
    if not latest:
        return {"error": "Kho chua co snapshot KPI/luong de tinh nang suat."}
    month_to = (month_to or latest)[:7]
    months_back = max(1, min(int(months_back or 6), 12))
    month_from = _month_add(month_to, -(months_back - 1))
    limit = max(1, min(int(limit or 200), 1000))
    sql = ("WITH snaps AS (SELECT substr(save_date,1,7) month,MAX(save_date) d "
           "FROM fact_thongketinhluong WHERE substr(save_date,1,7) BETWEEN ? AND ? GROUP BY month) "
           "SELECT substr(f.save_date,1,7) month,f.save_date,f.employee_code,f.employee_name,"
           "f.position_code,f.area_code,f.manager_code,COALESCE(f.month_sale_amount,0) actual,"
           "COALESCE(f.month_sale_target,0) target,f.month_sale_percent,nv.start_date "
           "FROM fact_thongketinhluong f JOIN snaps s ON s.d=f.save_date "
           "LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
           f"WHERE f.position_code IN ({_tier_ph()})")
    params = [month_from, month_to, *_EMPLOYEE_TIER_POSITIONS]
    if scope_area_code:
        sql += " AND f.area_code=?"; params.append(scope_area_code)
    if scope_employee_code:
        sql += " AND f.manager_code=?"; params.append(scope_employee_code)
    raw = _q(sql, tuple(params))

    def tenure_months(start_date, month):
        if not start_date or len(str(start_date)) < 7:
            return None
        try:
            sy, sm = int(str(start_date)[:4]), int(str(start_date)[5:7])
            y, m = int(month[:4]), int(month[5:7])
            return max(0, (y - sy) * 12 + m - sm)
        except Exception:
            return None

    monthly = {}
    for r in raw:
        if group_by == "employee":
            key, name = r["employee_code"], r["employee_name"] or r["employee_code"]
        elif group_by == "manager":
            key, name = r["manager_code"] or "MISSING_MANAGER", r["manager_code"] or "Thieu manager"
        elif group_by == "area":
            key, name = r["area_code"] or "UNKNOWN", r["area_code"] or "UNKNOWN"
        else:
            key, name = "ALL", "Toan bo pham vi"
        b = monthly.setdefault((key, r["month"]), {
            "group_code": key, "group_name": name, "month": r["month"],
            "actual": 0.0, "target": 0.0, "employees": set(), "tenures": [],
        })
        b["actual"] += _f(r["actual"]); b["target"] += _f(r["target"])
        b["employees"].add(r["employee_code"])
        tm = tenure_months(r.get("start_date"), r["month"])
        if tm is not None: b["tenures"].append(tm)

    by_group = {}
    for (key, month), b in monthly.items():
        row = {k: v for k, v in b.items() if k not in {"employees", "tenures"}}
        row["headcount"] = len(b["employees"])
        row["revenue_per_employee"] = b["actual"] / row["headcount"] if row["headcount"] else None
        row["achievement_pct"] = b["actual"] / b["target"] * 100 if b["target"] else None
        row["avg_tenure_months"] = (sum(b["tenures"]) / len(b["tenures"])) if b["tenures"] else None
        by_group.setdefault(key, {})[month] = row

    rows = []
    for key, ms in by_group.items():
        decline_streak = 0
        for month in sorted(ms):
            r = ms[month]; prev = ms.get(_month_add(month, -1))
            r["mom_delta"] = r["actual"] - prev["actual"] if prev else None
            r["mom_pct"] = (r["mom_delta"] / prev["actual"] * 100) if prev and prev["actual"] else None
            if r["mom_delta"] is not None and r["mom_delta"] < 0: decline_streak += 1
            else: decline_streak = 0
            r["decline_streak_months"] = decline_streak
            rows.append(r)
    rows.sort(key=lambda r: (r["month"], -(r["actual"] or 0)))
    rows, so_bi_cat = _giu_top_don_vi(rows, "group_code", "actual", limit)
    return {
        "month_from": month_from, "month_to": month_to, "group_by": group_by,
        "rows": rows, "so_nhom_khong_hien": so_bi_cat,
        "definition": ("Headcount = nhan vien TDV/CTV/CS co dong trong snapshot luong thang; "
                       "revenue_per_employee = tong doanh so / headcount. Decline streak chi tang "
                       "khi cac thang lien tiep deu giam."),
        "limitations": [
            "Chua co FACT_PhatSinhNhanVien/lich su chuyen vung chot chuan, nen khong tach duoc anh huong vao-ra-chuyen dia ban.",
            "Ngay vao lam lay tu dim_nhanvien; dong thieu start_date co avg_tenure_months=None va khong duoc suy dien.",
        ],
        "pham_vi_kenh": "OTC", "data_as_of": latest_data_date(),
    }


def operational_data_quality(as_of_date: str = None, sample_limit: int = 30,
                             scope_area_code: str = None, scope_channel: str = None,
                             scope_employee_code: str = None) -> dict:
    """Kiem tra mapping/target/manager/danh muc hoa don bang cac phep dem fail-closed."""
    sample_limit = max(1, min(int(sample_limit or 30), 100))
    as_of_date = (as_of_date or latest_data_date())[:10]
    result = {"as_of": as_of_date, "checks": {}, "samples": {}, "data_as_of": latest_data_date()}

    # KPI customer hien la nguon OTC. Tai khoan ETC khong duoc nhan cac dem nay nhu the la cua ETC.
    if not scope_channel or scope_channel.upper() == "OTC":
        fdate = _fact_date_le(as_of_date)
        if fdate:
            sql = ("SELECT f.employee_code,MAX(f.manager_code) manager_code,"
                   "MAX(COALESCE(f.month_sale_target,0)) target,nv.employee_code dim_code,"
                   "nv.is_duplicate,nv.area_code FROM fact_tonghopkhachhang f "
                   "LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code WHERE f.save_date=?")
            params = [fdate]
            if scope_area_code:
                sql += " AND nv.area_code=?"; params.append(scope_area_code)
            if scope_employee_code:
                team = _team_of_qlv(scope_employee_code, fdate)
                codes = [r["employee_code"] for r in team]
                sql += f" AND f.employee_code IN ({','.join(['?'] * len(codes))})"
                params.extend(codes)
            sql += " GROUP BY f.employee_code,nv.employee_code,nv.is_duplicate,nv.area_code"
            employees = _q(sql, tuple(params))
            missing_manager = [r["employee_code"] for r in employees if not (r["manager_code"] or "").strip()]
            missing_target = [r["employee_code"] for r in employees if _f(r["target"]) <= 0]
            missing_dim = [r["employee_code"] for r in employees if not r["dim_code"]]
            duplicates = [r["employee_code"] for r in employees if int(r["is_duplicate"] or 0) == 1
                          and r["employee_code"] not in _KNOWN_MISFLAGGED_DUPLICATE_CODES]
            result["checks"]["kpi_employee_mapping"] = {
                "snapshot": fdate, "employees": len(employees),
                "missing_manager": len(missing_manager), "missing_target": len(missing_target),
                "missing_employee_dim": len(missing_dim), "duplicate_codes": len(duplicates),
            }
            result["samples"].update({
                "missing_manager": missing_manager[:sample_limit],
                "missing_target": missing_target[:sample_limit],
                "missing_employee_dim": missing_dim[:sample_limit],
                "duplicate_codes": duplicates[:sample_limit],
            })
    else:
        result["checks"]["kpi_employee_mapping"] = {
            "not_applicable": True,
            "reason": "FACT_TongHopKhachHang/DIM_NhanVien chi phu KPI doi ngu OTC."
        }

    invoice_checks = {}
    for channel, table, kh_table in (("OTC", "vhoadon_otc", "dms_khachhang"),
                                     ("ETC", "vhoadon_etc", "dmssx_khachhang")):
        if scope_channel and scope_channel.upper() != channel:
            continue
        join = (f"LEFT JOIN {kh_table} kh ON kh.code=v.customer_code "
                "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id")
        where, params = " WHERE substr(v.doc_date,1,10)<=?", [as_of_date]
        if scope_area_code:
            where += " AND tp.area_code=?"; params.append(scope_area_code)
        if scope_employee_code:
            emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
            where += emp_sql; params.extend(emp_params)
        row = _q(
            f"SELECT COUNT(*) lines,COUNT(DISTINCT v.customer_code) customers,"
            "COUNT(DISTINCT CASE WHEN kh.code IS NULL THEN v.customer_code END) orphan_customers,"
            "COUNT(DISTINCT CASE WHEN kh.code IS NOT NULL AND tp.city_id IS NULL THEN v.customer_code END) missing_city_mapping,"
            "COUNT(DISTINCT CASE WHEN v.employee_code IS NULL OR TRIM(v.employee_code)='' THEN v.stt END) missing_employee_invoices "
            f"FROM {table} v {join}{where}", tuple(params))[0]
        future_where, future_params = " WHERE substr(v.doc_date,1,10)>?", [as_of_date]
        if scope_area_code:
            future_where += " AND tp.area_code=?"; future_params.append(scope_area_code)
        if scope_employee_code:
            emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
            future_where += emp_sql; future_params.extend(emp_params)
        future = _q(f"SELECT COUNT(*) n FROM {table} v {join}{future_where}", tuple(future_params))[0]["n"]
        invoice_checks[channel] = {**row, "future_dated_lines": int(future or 0)}
    result["checks"]["invoice_mapping"] = invoice_checks
    result["unavailable_checks"] = [
        "Don hang huy/cham/chua hoa don: bang DMS_DonHangHdr chua duoc dong bo vao kho local.",
        "Action/owner/deadline: chua co nguon action tracker.",
        "Sai chi nhanh/NPP: hoa don/danh muc local chua co khoa branch/distributor chuan.",
    ]
    result["canh_bao"] = ("So UNKNOWN/orphan trong tai khoan bi gioi han vung co the khong dem duoc vi "
                           "chinh dong thieu mapping khong suy ra duoc no thuoc vung nao. Khong duoc "
                           "hieu 0 la toan cong ty khong co loi.")
    return result


# ===================== DU BAO DOANH THU THEO THANG =====================
# 12/08/2026. Thay cho get_kpi_forecast_model1 da GO ngay 10/08 (ham do crash 100% vi tham chieu
# cot t.manager_code khong ton tai, va bia so o 4 cho). Mo hinh o day KHAC HAN: da duoc kiem chung
# bang walk-forward tren 49 thang du lieu that (2022-07 -> 2026-07), doi dau voi 20 mo hinh khac
# (xu huong trong nam, cung ky nam truoc, nhan he so da tang-giam 3/6/12 thang, hieu chinh do lech,
# trung vi, trong so theo nam, giam chan, cac dang hybrid). Ket qua: mo hinh DON GIAN NHAT thang.
#
#   MO HINH: du bao thang X = TRUNG BINH doanh thu dung thang X cua toi da 3 nam gan nhat.
#
# KHONG dung he so tang truong: da do, moi moc (3/6/12 thang) deu lam SAI SO TANG, va cang cat bot
# he so thi cang chinh xac - tuc tin hieu "da tang/giam" gan nhu toan nhieu.
# KHONG dung du lieu trong thang dang chay: mo hinh khong can, nen tra loi duoc ngay tu ngay 1 va
# khong dinh van de "doanh thu don ve cuoi thang".
#
# Sai so THAT do duoc tren du lieu toan cong ty: OTC ~14%, ETC ~17% (MAPE walk-forward 25 thang).
# KHONG hardcode 2 so nay - moi lan goi deu TU DO LAI tren dung pham vi dang hoi (toan cong ty hay
# 1 doi QLV), vi sai so cua 1 doi nho chac chan khac sai so toan cong ty.
_FORECAST_YEARS = 3            # so nam lay cung thang de trung binh
_FORECAST_MIN_YEARS = 2        # duoi muc nay thi TU CHOI, khong doan tu 1 nam duy nhat
_FORECAST_BACKTEST_MONTHS = 24  # so thang gan nhat dung de do sai so that cua mo hinh
# Tren nguong sai so nay thi con so du bao vo dung (khoang uoc tinh rong hon ca gia tri du bao)
# -> danh dau "khong_dang_tin" de AI noi thang, thay vi trinh bay 1 con so nhu that.
# Muc 50%: sai so THAT do duoc tren du lieu toan cong ty la 14% (OTC) / 17% (ETC), nen 50% da la
# gap 3 lan muc binh thuong - chi xay ra o pham vi nho, bien dong manh (vd 1 doi QLV it khach).
_FORECAST_MAX_ERROR_PCT = 50.0


def _ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def _monthly_series(channel: str, scope_area_code=None, scope_employee_code=None) -> dict:
    """{year_month: doanh_thu} cua 1 kenh, gop CA 2 nguon giong revenue_by_channel:
    vhoadon_otc/etc (chi tiet, chi con 12 thang gan nhat) + monthly_customer_summary (phan da nen).
    Thang nao co ca 2 nguon thi lay ban CHI TIET (day du hon)."""
    table = "vhoadon_otc" if channel == "OTC" else "vhoadon_etc"
    join = (_otc_area_join("v", scope_area_code) if channel == "OTC"
            else _etc_area_join("v", scope_area_code))
    sql_scope, params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v")
    sql_scope += emp_sql
    params += emp_params
    det = {r["ym"]: _f(r["rev"]) for r in _q(
        f"SELECT substr(v.doc_date,1,7) ym, SUM(v.amount9) rev FROM {table} v {join} "
        f"WHERE v.doc_date IS NOT NULL{sql_scope} GROUP BY 1", params)}

    msc, msc_params = _monthly_summary_scope_clause(scope_area_code, channel)
    msc_emp_sql, msc_emp_params = _employee_scope_clause(scope_employee_code, "m")
    msc += msc_emp_sql
    msc_params += msc_emp_params
    try:
        comp = {r["ym"]: _f(r["rev"]) for r in _q(
            f"SELECT m.year_month ym, SUM(m.revenue) rev FROM monthly_customer_summary m "
            f"WHERE m.channel=?{msc} GROUP BY 1", (channel,) + msc_params)}
    except sqlite3.OperationalError:
        comp = {}

    s = dict(comp)
    s.update(det)  # ban chi tiet ghi de ban nen
    # Bo thang dang chay (chua tron) va thang dau chuoi (co the la thang cut, chi co vai ngay cuoi).
    cur = dt.date.today().strftime("%Y-%m")
    months = sorted(k for k in s if s[k] > 0 and k != cur)
    if len(months) > 1:
        months = months[1:]
    return {m: s[m] for m in months}


def _forecast_one(series: dict, target: str):
    """Du bao 1 thang tu chuoi thang. Tra ve (du_bao, cac_nam_can_cu) hoac (None, []) neu thieu."""
    base = []
    for i in range(1, _FORECAST_YEARS + 1):
        m = _ym_add(target, -12 * i)
        if series.get(m, 0) > 0:
            base.append({"thang": m, "doanh_thu": series[m]})
    if len(base) < _FORECAST_MIN_YEARS:
        return None, base
    return sum(b["doanh_thu"] for b in base) / len(base), base


def _forecast_accuracy(series: dict) -> dict:
    """Do sai so THAT cua chinh mo hinh nay, tren chinh pham vi dang hoi, bang walk-forward:
    voi moi thang da qua, du bao no CHI bang cac thang truoc no roi so voi so thuc te."""
    months = sorted(series)
    errs = []
    for m in months[-_FORECAST_BACKTEST_MONTHS:]:
        past = {k: v for k, v in series.items() if k < m}
        pred, _ = _forecast_one(past, m)
        if pred and series[m] > 0:
            errs.append(abs(pred - series[m]) / series[m] * 100)
    if len(errs) < 6:
        return {"do_duoc": False, "so_thang_kiem": len(errs)}
    return {"do_duoc": True, "so_thang_kiem": len(errs),
            "sai_so_trung_binh_pct": round(sum(errs) / len(errs), 1)}


def revenue_forecast_month(year_month: str = None, scope_area_code: str = None,
                            scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """UOC TINH doanh thu CA THANG (khong phai so thuc te) cho 1 thang, theo kenh OTC/ETC va tong.

    Mo hinh: trung binh doanh thu DUNG THANG DO cua toi da 3 nam gan nhat. Da doi dau voi 20 mo hinh
    phuc tap hon tren 49 thang du lieu that va thang tat ca (xem khoi ghi chu phia tren ham nay).
    KHONG dung du lieu trong thang dang chay, nen tra loi duoc ngay ca khi thang moi bat dau.

    Moi lan goi deu TU DO LAI sai so tren dung pham vi dang hoi (walk-forward) - khong dung so cung.
    Neu chua du 2 nam lich su cho thang do thi TU CHOI du bao, khong doan tu 1 nam duy nhat."""
    return disabled_future_result()

    # Ma tinh cu duoc giu lai ben duoi de phuc vu audit, nhung khong the toi duoc
    # tu runtime va cung khong con duoc dang ky trong TEMPLATES.
    if not year_month:
        year_month = dt.date.today().strftime("%Y-%m")
    year_month = str(year_month)[:7]
    if len(year_month) != 7 or year_month[4] != "-":
        return {"error": f"Thang phai o dang YYYY-MM (nhan duoc: {year_month})."}

    channels = ["OTC", "ETC"]
    if scope_channel in ("OTC", "ETC"):
        channels = [scope_channel]

    out, tong_du_bao, thieu = {}, 0.0, []
    for ch in channels:
        series = _monthly_series(ch, scope_area_code, scope_employee_code)
        pred, base = _forecast_one(series, year_month)
        if pred is None:
            thieu.append(ch)
            out[ch] = {"du_bao": None, "can_cu": base, "so_thang_lich_su": len(series),
                       "ly_do_khong_du_bao": (
                           f"Chi co {len(base)} nam co du lieu thang {year_month[5:7]} trong pham vi "
                           f"nay (can it nhat {_FORECAST_MIN_YEARS}). KHONG du bao tu 1 nam duy nhat.")}
            continue
        acc = _forecast_accuracy(series)
        item = {"du_bao": pred, "can_cu": base, "so_nam_can_cu": len(base),
                "so_thang_lich_su": len(series), "do_chinh_xac": acc}
        if acc.get("do_duoc"):
            e = acc["sai_so_trung_binh_pct"] / 100
            # Chan duoi o 0: doanh thu khong the am. Khi sai so do duoc > 100% thi pred*(1-e) am,
            # in ra "khoang -0,8 den 18 ty" vua vo nghia vua lam nguoi doc tuong he thong hong.
            item["khoang_uoc_tinh"] = {"thap": max(0.0, pred * (1 - e)), "cao": pred * (1 + e)}
            if acc["sai_so_trung_binh_pct"] > _FORECAST_MAX_ERROR_PCT:
                # Mo hinh KHONG dung duoc cho pham vi nay - noi thang thay vi dua ra con so ma
                # khoang uoc tinh rong toi muc vo dung.
                item["khong_dang_tin"] = (
                    f"Sai so do duoc tren chinh pham vi nay la {acc['sai_so_trung_binh_pct']:.0f}% "
                    f"(nguong chap nhan {_FORECAST_MAX_ERROR_PCT:.0f}%) - doanh thu o pham vi nay bien "
                    f"dong qua manh de du bao theo mua vu. PHAI noi ro con so nay KHONG dang tin cay, "
                    f"hoac tu choi dua ra con so.")
        out[ch] = item
        tong_du_bao += pred

    result = {
        "thang_du_bao": year_month,
        "cac_kenh": out,
        "mo_hinh": "Trung binh doanh thu cung thang cua toi da 3 nam gan nhat (khong nhan he so tang truong).",
        "day_la_uoc_tinh": True,
        "data_as_of": latest_data_date(),
    }

    if len(channels) > 1 and not thieu:
        result["tong"] = {"du_bao": tong_du_bao}

    # Thang dang chay: kem luy ke THUC TE den nay de nguoi doc phan biet duoc so THAT va so UOC.
    if year_month == dt.date.today().strftime("%Y-%m"):
        d_from = f"{year_month}-01"
        # latest_data_date() tra MAX(doc_date) - la DAU THOI GIAN (vd '2026-08-12 09:00:00'), khong
        # phai ngay tran. Dung thang lam d_to thi "BETWEEN ? AND ?" LOAI BO cac hoa don phat sinh
        # muon hon trong dung ngay do (cung loi tung lam lech 6 ty, xem xu ly o call_template).
        ngay_cuoi = str(latest_data_date())[:10]
        if ngay_cuoi >= d_from:
            act = revenue_by_channel(d_from, ngay_cuoi + " 23:59:59",
                                     scope_area_code, scope_channel, scope_employee_code)
            result["luy_ke_thuc_te_den_nay"] = {
                "den_ngay": ngay_cuoi, "otc": act["otc"]["revenue"],
                "etc": act["etc"]["revenue"], "tong": act["total"]["revenue"]}

    canh_bao = [
        "DAY LA SO UOC TINH, KHONG phai doanh thu thuc te. PHAI noi ro dieu nay voi nguoi dung.",
        "Phai neu kem khoang uoc tinh va sai so trung binh, TUYET DOI khong trinh bay 1 con so don le "
        "nhu the la con so chac chan.",
        "Mo hinh chi dua tren mua vu lich su - KHONG biet cac su kien moi (mat/them khach lon, thay "
        "doi chinh sach, dut hang, thau ETC). Neu nguoi dung biet co su kien nhu vay thi so nay sai.",
    ]
    if thieu:
        canh_bao.append(f"Khong du bao duoc cho kenh: {', '.join(thieu)} (thieu lich su cung thang).")
    result["canh_bao"] = canh_bao
    return result


# ===================== DU BAO KPI THEO VAI TRO =====================
# 12/08/2026. Forecast KPI khong duoc phep lay % hien tai chia cho so ngay da qua.
# Dung cac snapshot KPI theo ngay de hoc ty le doanh so da chay duoc tai cung moc ngay cua
# cac thang truoc, sau do forecast doanh so cuoi thang = doanh so hien tai / ty le trung vi.
# Model nay dung duoc cho moi position_code co target, khong chi QLV.
_KPI_FORECAST_CUTOFFS = (3, 5, 6, 8, 10, 12, 15, 18, 20, 22, 25)
_KPI_FORECAST_MIN_SAMPLES = 8


def _kpi_percentile(values: list, p: float):
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * p
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _kpi_forecast_snapshot_rows(as_of_date: str) -> list:
    """Gom 1 dong/nhan vien/snapshot, khong dem lap target theo tung khach hang."""
    return _q(f"""
        SELECT f.employee_code, f.save_date,
               SUM(f.amount_ct) sales, MAX(f.month_sale_target) target,
               MAX(f.manager_code) manager_code, MAX(f.emp_dms_code) emp_dms_code,
               COALESCE(nv.name, f.employee_code) name,
               COALESCE(nv.position_code, 'UNKNOWN') position_code,
               cv.description position_label, nv.area_code area_code
        FROM fact_tonghopkhachhang f
        LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code
        LEFT JOIN dim_chucvu cv ON cv.position_code=nv.position_code
        WHERE f.save_date<=?
        GROUP BY f.employee_code, f.save_date, nv.name, nv.position_code,
                 cv.description, nv.area_code
        HAVING MAX(f.month_sale_target)>0
    """, (as_of_date,))


def _kpi_forecast_ratio_samples(rows: list, before_year_month: str = None) -> list:
    """Tao mau ty le luy ke/cuoi thang tu cac thang da tron ven truoc moc forecast."""
    by_employee_month = {}
    for r in rows:
        ym = str(r["save_date"])[:7]
        if before_year_month and ym >= before_year_month:
            continue
        key = (r["employee_code"], ym)
        by_employee_month.setdefault(key, []).append(r)

    samples = []
    for (employee_code, ym), snapshots in by_employee_month.items():
        ordered = sorted(snapshots, key=lambda x: x["save_date"])
        final = ordered[-1]
        if int(str(final["save_date"])[8:10]) < 25 or _f(final["sales"]) <= 0:
            continue
        for cutoff in _KPI_FORECAST_CUTOFFS:
            cutoff_date = f"{ym}-{cutoff:02d}"
            available = [x for x in ordered if x["save_date"] <= cutoff_date]
            if not available:
                continue
            partial = available[-1]
            partial_sales = _f(partial["sales"])
            final_sales = _f(final["sales"])
            ratio = partial_sales / final_sales if final_sales else 0
            # Du lieu snapshot co the co dong dieu chinh; bo mau vo ly de khong keo trung vi.
            if 0 < ratio <= 1.25:
                samples.append({
                    "employee_code": employee_code,
                    "year_month": ym,
                    "position_code": final["position_code"],
                    "cutoff": cutoff,
                    "ratio": ratio,
                })
    return samples


def _kpi_invoice_forecast_data(rows: list, as_of_date: str):
    """Dung doanh thu hoa don theo ngay lam fallback khi Bravo khong luu KPI snapshot theo ngay.

    FACT_TongHopKhachHang van duoc dung de lay target, vai tro va mapping manager_code tai snapshot
    cuoi thang. Doanh thu partial/final lay cung nguon hoa don (vHoaDonTotal/vHoaDonETCTotal) de
    tranh lay tu hai he quy chieu khac nhau. Với TDV, hoa don duoc tinh cho ca TDV va cong len QLV
    truc tiep; cac vai tro khac giu mapping truc tiep theo EmpDMSCode.
    """
    invoice_rows = _q("""
        SELECT substr(doc_date, 1, 10) doc_date, employee_code, SUM(amount9) sales
        FROM (
            SELECT doc_date, employee_code, amount9 FROM vhoadon_otc
            WHERE substr(doc_date, 1, 10)<=? AND employee_code IS NOT NULL
            UNION ALL
            SELECT doc_date, employee_code, amount9 FROM vhoadon_etc
            WHERE substr(doc_date, 1, 10)<=? AND employee_code IS NOT NULL
        ) v
        GROUP BY substr(doc_date, 1, 10), employee_code
    """, (as_of_date, as_of_date))
    if not invoice_rows:
        return [], {}

    # Chot 1 dong mapping/nhan vien/thang theo snapshot cuoi cung ma kho dang co.
    final_by_month_emp = {}
    for r in rows:
        ym = str(r["save_date"])[:7]
        key = (ym, r["employee_code"])
        if key not in final_by_month_emp or r["save_date"] > final_by_month_emp[key]["save_date"]:
            final_by_month_emp[key] = r

    try:
        dim_rows = _q("SELECT employee_code, dmsid, position_code FROM dim_nhanvien WHERE dmsid IS NOT NULL")
    except sqlite3.OperationalError:
        # Mot so warehouse dev cu chua co cot DMSId; fact snapshot van co the co emp_dms_code.
        dim_rows = _q("SELECT employee_code, NULL AS dmsid, position_code FROM dim_nhanvien")
    dim_by_employee = {r["employee_code"]: r for r in dim_rows}
    month_dms_map = {}
    for (ym, employee_code), r in final_by_month_emp.items():
        dim = dim_by_employee.get(employee_code) or {}
        keys = {r.get("emp_dms_code"), dim.get("dmsid"), employee_code}
        keys.discard(None)
        keys.discard("")
        item = {
            "employee_code": employee_code,
            "position_code": r["position_code"],
            "manager_code": r.get("manager_code"),
        }
        for key in keys:
            month_dms_map.setdefault(ym, {}).setdefault(str(key), []).append(item)

    # daily_sales[(year_month, target_employee)][day] = doanh thu hoa don cua target.
    daily_sales = {}
    for inv in invoice_rows:
        ym = str(inv["doc_date"])[:7]
        day = int(str(inv["doc_date"])[8:10])
        candidates = month_dms_map.get(ym, {}).get(str(inv["employee_code"]), [])
        target_codes = set()
        for candidate in candidates:
            target_codes.add(candidate["employee_code"])
            if candidate["position_code"] == "TDV" and candidate.get("manager_code"):
                target_codes.add(candidate["manager_code"])
        for target_code in target_codes:
            day_map = daily_sales.setdefault((ym, target_code), {})
            day_map[day] = day_map.get(day, 0.0) + _f(inv["sales"])

    cumulative_sales = {}
    for key, day_map in daily_sales.items():
        running = 0.0
        cumulative = {}
        for day in sorted(day_map):
            running += day_map[day]
            cumulative[day] = running
        cumulative_sales[key] = cumulative

    def total_until(ym, employee_code, cutoff):
        cumulative = cumulative_sales.get((ym, employee_code), {})
        eligible = [day for day in cumulative if day <= cutoff]
        return cumulative[max(eligible)] if eligible else 0.0

    samples = []
    for (ym, employee_code), final_row in final_by_month_emp.items():
        final_day = max(cumulative_sales.get((ym, employee_code), {}), default=0)
        if final_day < 25:
            continue
        final_sales = total_until(ym, employee_code, final_day)
        if final_sales <= 0:
            continue
        for cutoff in _KPI_FORECAST_CUTOFFS:
            partial_sales = total_until(ym, employee_code, cutoff)
            ratio = partial_sales / final_sales if final_sales else 0
            if 0 < ratio <= 1.25:
                samples.append({
                    "employee_code": employee_code,
                    "year_month": ym,
                    "position_code": final_row["position_code"],
                    "cutoff": cutoff,
                    "ratio": ratio,
                    "partial_sales": partial_sales,
                    "final_sales": final_sales,
                })

    current_ym = str(as_of_date)[:7]
    current_sales = {}
    for r in rows:
        if str(r["save_date"])[:7] != current_ym:
            continue
        employee_code = r["employee_code"]
        current_sales[employee_code] = total_until(current_ym, employee_code,
                                                   int(str(as_of_date)[8:10]))
    return samples, current_sales


def _kpi_forecast_backtest_samples(samples: list, position_code: str, cutoff: int) -> dict:
    """Walk-forward MAPE cho samples tao tu hoa don ngay (fallback)."""
    months = sorted({s["year_month"] for s in samples})
    errors = []
    role_samples = [s for s in samples if s["position_code"] == position_code and s["cutoff"] == cutoff]
    for target_month in months:
        past = [s for s in role_samples if s["year_month"] < target_month]
        ratio, used, _ = _kpi_pick_ratio(past, position_code, cutoff)
        if not ratio or not used:
            continue
        for sample in role_samples:
            if sample["year_month"] != target_month or sample["final_sales"] <= 0:
                continue
            predicted = sample["partial_sales"] / ratio
            errors.append(abs(predicted - sample["final_sales"]) / sample["final_sales"] * 100)
    if len(errors) < 6:
        return {"do_duoc": False, "so_mau": len(errors)}
    return {"do_duoc": True, "so_mau": len(errors), "mape_pct": round(sum(errors) / len(errors), 1)}


def _kpi_pick_ratio(samples: list, position_code: str, cutoff: int):
    """Uu tien cung vai tro/cung moc; fallback cung vai tro moc gan; cuoi cung toan he thong."""
    def vals(items):
        return [s["ratio"] for s in items]

    exact = [s for s in samples if s["position_code"] == position_code and s["cutoff"] == cutoff]
    if len(exact) >= _KPI_FORECAST_MIN_SAMPLES:
        return median(vals(exact)), exact, "same_position_same_cutoff"

    role_near = [s for s in samples if s["position_code"] == position_code and abs(s["cutoff"] - cutoff) <= 3]
    if len(role_near) >= _KPI_FORECAST_MIN_SAMPLES:
        return median(vals(role_near)), role_near, "same_position_near_cutoff"

    global_near = [s for s in samples if abs(s["cutoff"] - cutoff) <= 3]
    if len(global_near) >= _KPI_FORECAST_MIN_SAMPLES:
        return median(vals(global_near)), global_near, "all_positions_near_cutoff"
    return None, global_near, "insufficient_history"


def _kpi_forecast_backtest(rows: list, position_code: str, cutoff: int) -> dict:
    """Walk-forward MAPE cho 1 vai tro/moc, chi hoc tu cac thang truoc thang test."""
    months = sorted({str(r["save_date"])[:7] for r in rows})
    # Tao mau lich su 1 lan. Ban cu tinh lai toan bo samples trong moi thang test,
    # vua ton CPU vua lam thoi gian tra loi tang theo so thang snapshot.
    all_samples = sorted(_kpi_forecast_ratio_samples(rows), key=lambda x: x["year_month"])
    samples_before = []
    sample_idx = 0
    role_months = {}
    for r in rows:
        if r["position_code"] != position_code:
            continue
        ym = str(r["save_date"])[:7]
        role_months.setdefault(ym, {}).setdefault(r["employee_code"], []).append(r)

    errors = []
    for target_month in months:
        while sample_idx < len(all_samples) and all_samples[sample_idx]["year_month"] < target_month:
            samples_before.append(all_samples[sample_idx])
            sample_idx += 1
        past = samples_before
        if not past:
            continue
        ratio, used, _ = _kpi_pick_ratio(past, position_code, cutoff)
        if not ratio or not used:
            continue
        for snapshots in role_months.get(target_month, {}).values():
            ordered = sorted(snapshots, key=lambda x: x["save_date"])
            final = ordered[-1]
            if int(str(final["save_date"])[8:10]) < 25 or _f(final["sales"]) <= 0:
                continue
            avail = [x for x in ordered if x["save_date"] <= f"{target_month}-{cutoff:02d}"]
            if not avail:
                continue
            partial = avail[-1]
            predicted = _f(partial["sales"]) / ratio
            actual = _f(final["sales"])
            if actual > 0:
                errors.append(abs(predicted - actual) / actual * 100)
    if len(errors) < 6:
        return {"do_duoc": False, "so_mau": len(errors)}
    return {"do_duoc": True, "so_mau": len(errors), "mape_pct": round(sum(errors) / len(errors), 1)}


def kpi_forecast_month(year_month: str = None, as_of_date: str = None,
                       position_code: str = None, limit: int = 100,
                       scope_area_code: str = None, scope_employee_code: str = None) -> dict:
    """Du bao % hoan thanh KPI cuoi thang cho moi chuc vu co target.

    Khong ngoai suy theo so ngay. Model hoc ty le doanh so luy ke/cuoi thang tu snapshot lich su,
    uu tien cung position_code va cung moc ngay. Neu warehouse khong co du snapshot lich su thi tra
    ve ly_do_khong_du_bao thay vi bia so. Dung cho QLV, TDV, CTV, CS, TK va cac chuc vu khac co target.
    """
    return disabled_future_result()

    # Ma tinh cu chi con de audit; runtime dung tai chinh sach fail-closed o tren.
    if not as_of_date:
        r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang")
        as_of_date = r[0]["d"] if r and r[0]["d"] else dt.date.today().isoformat()
    as_of_date = str(as_of_date)[:10]
    if not year_month:
        year_month = as_of_date[:7]
    year_month = str(year_month)[:7]
    if len(year_month) != 7 or year_month[4] != "-":
        return {"error": f"Thang phai o dang YYYY-MM (nhan duoc: {year_month})."}
    if year_month != as_of_date[:7]:
        return {"error": "Tool nay chi du bao thang dang chay tu snapshot luy ke hien tai."}

    rows = _kpi_forecast_snapshot_rows(as_of_date)
    current = [r for r in rows if str(r["save_date"])[:7] == year_month]
    if not current:
        return {"thang_du_bao": year_month, "as_of": as_of_date,
                "ly_do_khong_du_bao": "Khong co snapshot KPI cua thang dang chay trong warehouse."}

    # Dung snapshot moi nhat cua tung nhan vien, nhung ghi ro ngay thuc te cua tung dong.
    allowed = None
    if scope_employee_code:
        team = _team_of_qlv(scope_employee_code, max(str(r["save_date"]) for r in current))
        allowed = {scope_employee_code, *(t["employee_code"] for t in team)}

    current_map = {}
    for r in current:
        if scope_area_code and r["area_code"] != scope_area_code:
            continue
        if allowed is not None and r["employee_code"] not in allowed:
            continue
        if position_code and r["position_code"] != position_code:
            continue
        key = r["employee_code"]
        if key not in current_map or r["save_date"] > current_map[key]["save_date"]:
            current_map[key] = r

    samples = _kpi_forecast_ratio_samples(rows, before_year_month=year_month)
    forecast_source = "kpi_snapshots"
    invoice_current_sales = {}
    if not samples:
        # Bravo thuc te co hoa don theo ngay nhung khong co FACT KPI snapshot theo ngay. Dung cung
        # nguon hoa don cho ca partial va final, chi dung FACT de lay target/role/manager mapping.
        samples, invoice_current_sales = _kpi_invoice_forecast_data(rows, as_of_date)
        samples = [s for s in samples if s["year_month"] < year_month]
        forecast_source = "daily_invoices_fallback"
    if not samples:
        return {"thang_du_bao": year_month, "as_of": as_of_date,
                "ly_do_khong_du_bao": (
                    "Warehouse khong co du snapshot KPI theo ngay va cung khong co du doanh thu hoa don "
                    "theo ngay de dung mo hinh fallback.")}

    results = []
    backtest_cache = {}
    for r in current_map.values():
        current_sales = _f(r["sales"])
        if forecast_source == "daily_invoices_fallback" and r["employee_code"] in invoice_current_sales:
            # Dung cung nguon hoa don voi cac mau lich su. Neu khong map duoc thi giu snapshot hien tai,
            # tranh lam mat dong du lieu chi vi EmpDMSCode khong day du.
            invoice_sales = _f(invoice_current_sales[r["employee_code"]])
            if invoice_sales > 0:
                current_sales = invoice_sales
        target = _f(r["target"])
        if target <= 0:
            continue
        cutoff = int(str(r["save_date"])[8:10])
        ratio, used, method = _kpi_pick_ratio(samples, r["position_code"], cutoff)
        current_pct = current_sales / target * 100
        if not ratio:
            results.append({
                "employee_code": r["employee_code"], "name": r["name"],
                "position_code": r["position_code"], "position_label": r["position_label"],
                "current_pct": round(current_pct, 1), "forecast_pct": None,
                "ly_do_khong_du_bao": "Thieu mau lich su phu hop cho vai tro va moc ngay nay.",
            })
            continue
        forecast_pct = current_pct / ratio
        q25 = _kpi_percentile([s["ratio"] for s in used], 0.25)
        q75 = _kpi_percentile([s["ratio"] for s in used], 0.75)
        item = {
            "employee_code": r["employee_code"], "name": r["name"],
            "position_code": r["position_code"], "position_label": r["position_label"],
            "sales_current": current_sales, "target": target,
            "current_pct": round(current_pct, 1), "forecast_pct": round(forecast_pct, 1),
            "cutoff_day": cutoff, "ratio_luy_ke_trung_vi": round(ratio, 4),
            "so_mau_lich_su": len(used), "phuong_phap": method,
            "forecast_status": _kpi_status(forecast_pct, r["position_code"]),
        }
        if len(used) >= _KPI_FORECAST_MIN_SAMPLES and q25 and q75:
            item["forecast_interval_pct"] = {
                "thap": round(current_pct / q75, 1),
                "cao": round(current_pct / q25, 1),
            }
        backtest_key = (r["position_code"], cutoff)
        if backtest_key not in backtest_cache:
            if forecast_source == "daily_invoices_fallback":
                backtest_cache[backtest_key] = _kpi_forecast_backtest_samples(
                    samples, r["position_code"], cutoff)
            else:
                backtest_cache[backtest_key] = _kpi_forecast_backtest(rows, r["position_code"], cutoff)
        item["backtest"] = backtest_cache[backtest_key]
        results.append(item)

    by_position = {}
    for r in results:
        p = r["position_code"]
        bucket = by_position.setdefault(p, {"position_code": p, "position_label": r["position_label"], "rows": []})
        bucket["rows"].append(r)
    summary = []
    for bucket in by_position.values():
        forecasts = [r["forecast_pct"] for r in bucket["rows"] if r["forecast_pct"] is not None]
        summary.append({
            "position_code": bucket["position_code"], "position_label": bucket["position_label"],
            "count": len(bucket["rows"]), "count_forecasted": len(forecasts),
            "median_forecast_pct": round(median(forecasts), 1) if forecasts else None,
            "count_meeting_kpi": sum(v >= KPI_ACHIEVED_THRESHOLD for v in forecasts),
        })

    results.sort(key=lambda x: (x["forecast_pct"] is None, -(x["forecast_pct"] or 0)))
    warnings = [
        "Day la uoc tinh, khong phai ket qua KPI thuc te.",
        "Khoang uoc tinh chi hien khi co du mau lich su; moi chuc vu co the co do tin cay khac nhau.",
    ]
    if forecast_source == "kpi_snapshots":
        warnings.append("Mo hinh uu tien snapshot KPI; khong nen dung neu snapshot thang bi ghi do dang.")
    else:
        warnings.extend([
            "Khong co snapshot KPI theo ngay nen ket qua nay dung doanh thu hoa don theo ngay lam fallback.",
            "Doanh thu hoa don co the khac Amount_CT do quy tac ghi nhan/tra hang; can xem day la uoc tinh tham khao.",
        ])
    return {
        "thang_du_bao": year_month, "as_of": as_of_date,
        "day_cutoff_max": max(int(str(r["save_date"])[8:10]) for r in current),
        "model": ("Trung vi ty le luy ke/cuoi thang theo position_code va moc ngay; khong chia theo so ngay."
                  if forecast_source == "kpi_snapshots" else
                  "Fallback: trung vi ty le doanh thu hoa don luy ke/cuoi thang theo position_code va moc ngay."),
        "data_source": forecast_source,
        "kpi_threshold_pct": KPI_ACHIEVED_THRESHOLD,
        "summary_by_position": sorted(summary, key=lambda x: x["position_code"]),
        "total_rows": len(results), "rows": results[:max(1, min(int(limit or 100), 200))],
        "canh_bao": warnings,
    }


# 21/08/2026: khung tuoi no CHATBOT dang dung (1-15/15-30/30-45/>45 ngay) lay THANG tu SP goc Bravo
# usp_DeptAccDueDate_GetData - xac nhan qua doi chieu voi file Excel "Bao cao cong no phai thu" DNH
# tu cung cap: file do chia theo mac khac han (1-7/8-14/15-21/>21 ngay). HAI khung nay CUNG TON TAI
# that trong nghiep vu DNH (SP he thong dung 1 kieu, bao cao thu cong Excel dung kieu khac) - KHONG
# phai loi du lieu/code, nhung neu tra loi ma khong noi ro se de bi hieu nham la chatbot tinh sai so
# voi bao cao Excel quen thuoc. Chua co xac nhan tu DNH kieu nao la "chuan chinh thuc" nen KHONG tu
# doi bucket - chi gan canh bao ro rang de AI PHAI nhac lai voi nguoi dung khi tra ve breakdown nay.
_AGING_BUCKET_NOTE = (
    "Khung qua han duoi day (1-15 / 15-30 / 30-45 / >45 ngay) lay THANG tu he thong cong no goc cua "
    "DNH (SP usp_DeptAccDueDate_GetData). Neu ban dang doi chieu voi bao cao Excel noi bo (mot so ban "
    "dung moc 1-7 / 8-14 / 15-21 / >21 ngay), 2 khung nay KHAC NHAU va KHONG the quy doi truc tiep tuong "
    "ung tung khoang - can hoi lai bo phan ke toan/DNH de xac nhan khung nao dang duoc dung lam chuan."
)


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
    va 4 bucket overdue_1_15/15_30/30_45/gt_45 (de tra loi "qua han bao lau") kem "aging_bucket_note"
    (xem _AGING_BUCKET_NOTE) - PHAI co mat cung breakdown de AI biet ma khung nay khac Excel noi bo.

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
              "overdue_30_45": _f(r["b3"]), "overdue_gt_45": _f(r["b4"]),
              "aging_bucket_note": _AGING_BUCKET_NOTE}
    if stale:
        result["receivable_warning"] = (
            f"So cong no lay tu snapshot luc {snapshot_at} (da cu hon 6 gio) - nen luu y moc thoi gian "
            "khi tra loi.")
    return result


def receivables_history_dates(limit: int = 30) -> dict:
    """Liet ke cac NGAY da co snapshot cong no LICH SU (fact_congno_khachhang_history) - dung TRUOC
    khi goi get_receivables_period_compare de biet co ngay nao de so sanh chua, hoac khi nguoi dung
    hoi 'cong no co du lieu tu bao gio', 'co the so sanh cong no voi ngay nao'.

    21/08/2026: bang lich su MOI duoc them (xem sync_fact_congno trong sync_warehouse.py) - CHI co
    du lieu TU NGAY BAT DAU GHI TRO DI, KHONG co lich su cong no truoc do (khac han doanh thu co du
    lieu nhieu nam). PHAI noi ro dieu nay neu danh sach ngay con it/moi bat dau."""
    limit = max(1, min(int(limit or 30), 100))
    rows = _q("SELECT DISTINCT snapshot_date FROM fact_congno_khachhang_history "
              "ORDER BY snapshot_date DESC LIMIT ?", (limit,))
    dates = [r["snapshot_date"] for r in rows]
    return {"so_ngay_co_du_lieu": len(dates), "cac_ngay": dates,
            "ghi_chu": ("He thong bat dau luu lich su cong no tu 21/08/2026 - CHUA co du lieu cong "
                        "no cua cac ky truoc ngay do, khac voi doanh thu (co du lieu nhieu nam).")}


def receivables_period_compare(snapshot_date_a: str, snapshot_date_b: str,
                                scope_area_code: str = None,
                                scope_channel: str = None) -> dict:
    """SO SANH cong no giua 2 NGAY snapshot lich su (fact_congno_khachhang_history) - dung khi cau
    hoi dang "cong no hom nay so voi tuan truoc/thang truoc the nao", "no qua han tang hay giam so
    voi ngay X". KHAC voi get_receivables_overview (chi tra ve snapshot HIEN TAI DUY NHAT, khong so
    sanh duoc) - dung get_receivables_history_dates TRUOC de biet cac ngay co san neu chua chac.

    snapshot_date_a/date_b: 'YYYY-MM-DD', PHAI la ngay CO trong fact_congno_khachhang_history (dung
    get_receivables_history_dates de tra cuu) - neu 1 trong 2 ngay khong co du lieu, tra ve loi ro
    rang thay vi so sanh voi 0.

    21/08/2026: bang lich su moi duoc them nen CHI so sanh duoc trong pham vi tu ngay bat dau ghi -
    KHONG the so sanh voi cac ky xa hon (vd "cung ky nam ngoai") nhu doanh thu da lam duoc."""
    conditions, params = [], []
    if scope_area_code:
        region_key = next((k for k, ms in REGION_SQL_MARKERS.items() if scope_area_code in ms), None)
        markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code])
        conditions.append(f"area_code IN ({','.join(['?'] * len(markers))})")
        params.extend(markers)
    if scope_channel:
        channel = str(scope_channel).strip().upper()
        if channel not in {"OTC", "ETC"}:
            raise ValueError(f"scope_channel khong hop le: {scope_channel}")
        conditions.append("UPPER(TRIM(sales_channel))=?")
        params.append(channel)
    where = "".join(f" AND {condition}" for condition in conditions)

    def _snapshot(d):
        r = _q(f"SELECT COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od, COUNT(*) n "
               f"FROM fact_congno_khachhang_history WHERE snapshot_date=?{where}", (d, *params))[0]
        return {"snapshot_date": d, "balance_end": _f(r["bal"]), "total_overdue": _f(r["od"]),
                "so_dong": int(r["n"])}

    a, b = _snapshot(snapshot_date_a), _snapshot(snapshot_date_b)
    missing = [d for d, s in ((snapshot_date_a, a), (snapshot_date_b, b)) if s["so_dong"] == 0]
    if missing:
        return {"error": (f"Khong co du lieu cong no lich su cho ngay {', '.join(missing)}. "
                           "Dung get_receivables_history_dates de xem cac ngay dang co san.")}

    delta_balance = a["balance_end"] - b["balance_end"]
    delta_overdue = a["total_overdue"] - b["total_overdue"]
    return {
        "ky_a": a, "ky_b": b,
        "delta_balance_end": delta_balance,
        "delta_total_overdue": delta_overdue,
        "pct_change_balance_end": (delta_balance / b["balance_end"] * 100) if b["balance_end"] else None,
        "pct_change_total_overdue": (delta_overdue / b["total_overdue"] * 100) if b["total_overdue"] else None,
        "aging_bucket_note": _AGING_BUCKET_NOTE,
        "scope_area_code": scope_area_code,
        "scope_channel": str(scope_channel).strip().upper() if scope_channel else None,
    }


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
    duoc phep (redact kenh kia ve 0, KHONG lo so lieu that).

    24/08/2026: SUA 2 loi - (1) docstring nay TRUOC DAY nam SAU nhanh xu ly hang loat ben duoi nen
    KHONG PHAI __doc__ that cua ham (Python chi coi statement DAU TIEN la docstring) - da chuyen len
    dung vi tri; (2) duong hang loat (customer_code co dau phay) AM THAM loai bo cac ma bi tu choi/loi
    (vd ngoai vung, khach thuan kenh khac) khoi ket qua ma KHONG bao ly do - nguoi dung hoi 3 ma nhung
    chi thay 1 ket qua ma khong biet 2 ma kia bi gi. Sua theo dung pattern salary_detail(): giu lai loi
    kem 'requested_customer_code' thay vi im lang bo qua."""
    if customer_code and "," in customer_code:
        codes = [c.strip() for c in customer_code.split(",") if c.strip()]
        results = []
        for code in codes[:30]:
            r_single = customer_detail(customer_code=code, date_from=date_from, date_to=date_to, scope_area_code=scope_area_code, scope_channel=scope_channel)
            r_single = dict(r_single) if r_single else {"error": f"Khong tra ve duoc du lieu cho khach hang '{code}'."}
            r_single["requested_customer_code"] = code
            results.append(r_single)
        return {"is_bulk": True, "count": len(results), "customers": results}
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
    if scope_channel == "ETC" and real_etc_hd == 0 and real_otc_hd > 0:
        return {"error": f"Ban khong co quyen xem khach hang nay - day la khach hang kenh OTC, tai khoan cua ban chi duoc xem kenh {scope_channel}."}
    otc_rev, otc_hd = (0.0, 0) if scope_channel == "ETC" else (_f(o["rev"]), real_otc_hd)
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
                        scope_area_code: str = None, scope_channel: str = None,
                        scope_employee_code: str = None) -> dict:
    """Phat hien dau hieu 'chay don don KPI': hoa don co created_at (thoi diem BAN GHI THUC SU duoc
    tao trong Bravo) lech qua xa so voi doc_date (ngay chung tu tren hoa don, co the bi chon tay).
    Vd: doc_date la cuoi thang truoc nhung created_at lai la dau thang sau -> dau hieu tao/sua don
    backdate de kip chi tieu KPI thang truoc. threshold_days: so ngay lech toi thieu de bi liet ke
    (mac dinh 2). Tra ve ca TOM TAT theo tung nhan vien (ai co nhieu don bat thuong nhat) LAN danh
    sach chi tiet top nhung don lech nhieu nhat. scope_area_code: ep loc theo vung khi bi gioi han.
    scope_channel: NEU co (vd 'OTC'), BO HAN kenh con lai khoi truy van (khong chi redact ket qua).

    19/08/2026: THEM scope_employee_code - ham nay tra ve TOM TAT THEO TUNG NHAN VIEN (nghi van
    "chay don don KPI"), du lieu nhay cam/gan nhu to cao ca nhan nen truoc day bi fail-closed chan
    HOAN TOAN voi tai khoan QLV (dung, vi chua ho tro gioi han theo doi). Dung
    _employee_scope_clause() (alias "v" - dung DMSId, KHOP dinh dang employee_code THAT tren
    vhoadon_otc/etc, KHAC voi loi dinh dang tung xay ra o salary_achievement_summary vi do la bang
    HOA DON, khong phai bang luong)."""
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    scope_sql += emp_sql
    scope_params += emp_params
    parts = []
    part_params = []
    if scope_channel != "ETC":
        join_o = _otc_area_join("v", scope_area_code)
        parts.append(f"""SELECT 'OTC' channel,v.doc_date,v.created_at,v.customer_code,v.employee_code,v.amount9,v.stt
                FROM vhoadon_otc v {join_o} WHERE v.doc_date BETWEEN ? AND ? AND v.created_at IS NOT NULL{scope_sql}""")
        part_params.append((date_from, date_to) + scope_params)
    if scope_channel != "OTC":
        join_e = _etc_area_join("v", scope_area_code)
        parts.append(f"""SELECT 'ETC' channel,v.doc_date,v.created_at,v.customer_code,v.employee_code,v.amount9,v.stt
            FROM vhoadon_etc v {join_e} WHERE v.doc_date BETWEEN ? AND ? AND v.created_at IS NOT NULL{scope_sql}""")
        part_params.append((date_from, date_to) + scope_params)
    sql = f"""
        SELECT channel,doc_date,MAX(created_at) created_at,customer_code,employee_code,
               SUM(amount9) amount9,stt,
               CAST(julianday(MAX(created_at)) - julianday(doc_date) AS INTEGER) AS lech_ngay
        FROM ({" UNION ALL ".join(parts)}) raw
        GROUP BY channel,doc_date,customer_code,employee_code,stt
        HAVING ABS(CAST(julianday(MAX(created_at)) - julianday(doc_date) AS INTEGER)) >= ?
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
    # Cung mot lan goi phai tra du phan "don lon + hang tra + backdate". Truoc day tool chi co
    # backdate, khien model noi sai rang OTC khong co nguon hang tra va tu ket luan toan bo doanh thu
    # la "thuc chat" ma chua he soi do tap trung don hang. vhoadon_otc GIU cac dong Amount9 am.
    quality_parts, quality_params = [], []
    if scope_channel != "ETC":
        join_o = _otc_area_join("v", scope_area_code)
        quality_parts.append(
            f"SELECT 'OTC' channel,v.doc_date,v.customer_code,v.stt,v.amount9 FROM vhoadon_otc v {join_o} "
            f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        quality_params.extend((date_from, date_to) + scope_params)
    if scope_channel != "OTC":
        join_e = _etc_area_join("v", scope_area_code)
        quality_parts.append(
            f"SELECT 'ETC' channel,v.doc_date,v.customer_code,v.stt,v.amount9 FROM vhoadon_etc v {join_e} "
            f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        quality_params.extend((date_from, date_to) + scope_params)
    order_rows = _q(
        "WITH lines AS (" + " UNION ALL ".join(quality_parts) + ") "
        "SELECT channel||':'||COALESCE(NULLIF(stt,''),doc_date||':'||COALESCE(customer_code,'')) order_key,"
        "SUM(amount9) revenue,"
        "SUM(CASE WHEN amount9<0 THEN amount9 ELSE 0 END) return_amount,"
        "MAX(CASE WHEN amount9<0 THEN 1 ELSE 0 END) has_return "
        "FROM lines GROUP BY channel,COALESCE(NULLIF(stt,''),doc_date||':'||COALESCE(customer_code,''))",
        tuple(quality_params)) if quality_parts else []
    order_values = sorted((_f(r["revenue"]) for r in order_rows), reverse=True)
    total_order_revenue = sum(order_values)
    median_order = float(median(order_values)) if order_values else 0.0
    proposed_threshold = median_order * 3
    reference_large = [v for v in order_values if v > proposed_threshold]
    concentration = {}
    for n in (1, 2, 5, 10):
        value = sum(order_values[:n])
        concentration[f"top_{n}_revenue"] = value
        concentration[f"top_{n}_share_pct"] = (value / total_order_revenue * 100
                                                 if total_order_revenue else None)
    result["returns"] = {
        "orders_with_negative_lines": sum(1 for r in order_rows if int(r["has_return"] or 0)),
        "negative_amount": sum(_f(r["return_amount"]) for r in order_rows),
        "definition": "Hang tra/dieu chinh = dong hoa don co Amount9 am; ap dung cho ca OTC va ETC.",
    }
    result["order_value_distribution"] = {
        "orders": len(order_rows), "revenue": total_order_revenue,
        "median_order_value": median_order, **concentration,
        "reference_over_3x_median": {
            "status": "CHI_LA_THAM_CHIEU_CHUA_DUOC_DNH_PHE_DUYET",
            "threshold": proposed_threshold,
            "orders": len(reference_large), "revenue": sum(reference_large),
        },
        "warning": ("DNH chua phe duyet nguong nao duoc goi la 'don lon bat thuong'. Chi trinh bay "
                    "phan bo/top share va tham chieu >3x trung vi; KHONG ket luan gian lan/chay don "
                    "chi tu gia tri don."),
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


def _nam_moi_nhat(table: str, col: str):
    """MAX(col) tren bang ton kho, tra None neu kho CU chua co cot do (chua chay migration).
    Bao cao ton kho khong duoc SAP vi thieu cot - thay vao do tra None de ham goi tu canh bao
    rang so lieu co the dang cong don nhieu nam tai chinh."""
    try:
        r = _q(f"SELECT MAX({col}) y FROM {table} WHERE {col} IS NOT NULL")
    except Exception:
        return None
    return r[0]["y"] if r and r[0]["y"] is not None else None


def inventory_by_region(area_code: str = None, scope_area_code: str = None) -> list:
    """Ton kho (so luong + gia tri) theo vung, tu Bravo qua brv_tonkhodk/brv_kho/brv_sanpham - THAY
    THE nguon Supabase cu (bang inventory co cot warehouse nhung 100% NULL, khong loc vung duoc).
    area_code: 'MB'/'MT'/'MN' - tuy chon, khong truyen se tra ve CA 4 vung (gom ca B01 San xuat).
    scope_area_code: EP GHI DE area_code khi tai khoan bi gioi han vung (giong cac ham khac) - vi
    B01 (San xuat) khong thuoc vung MB/MT/MN nao nen KHONG BAO GIO hien voi tai khoan bi gioi han."""
    if scope_area_code:
        area_code = scope_area_code
    branch_filter = _AREA_TO_BRANCH.get(area_code) if area_code else None
    # 04/09/2026 - LOI NANG DA SUA: brv_tonkhodk la TON DAU KY THEO NAM TAI CHINH (Bravo giu ca
    # 2024/2025/2026), KHONG phai ton hien tai. Truoc day khong loc nam -> cong don ca 3 nam, dem
    # trung cung mot lo hang toi 3 lan (vd B04 bao 28,78 trieu don vi trong khi nam 2026 chi co
    # 10,61 trieu). LUON loc nam moi nhat.
    nam_moi_nhat = _nam_moi_nhat("brv_tonkhodk", "fiscal_year")
    sql = """SELECT k.branch_code area_code, COUNT(DISTINCT t.item_id) so_mat_hang,
                    SUM(t.quantity) tong_so_luong, SUM(t.amount) tong_gia_tri
             FROM brv_tonkhodk t LEFT JOIN brv_kho k ON k.id_code = t.warehouse_id
             WHERE t.is_active = 1"""
    params = []
    if nam_moi_nhat is not None:
        sql += " AND t.fiscal_year = ?"
        params.append(nam_moi_nhat)
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
        r["nam_tai_chinh"] = nam_moi_nhat
        if nam_moi_nhat is None:
            r["canh_bao"] = ("Kho chua dong bo cot fiscal_year - so lieu nay co the dang CONG DON "
                             "nhieu nam tai chinh (dem trung). Can chay lai sync_warehouse.py "
                             "truoc khi dung con so nay.")
    return rows


# 13/08/2026 (them 21/08 sau khi nguoi dung xac nhan): khung phan loai theo SO THANG CON LAI den han
# su dung - KHOP voi cach DNH dang bao cao thu cong qua Excel "Bao cao ton kho thanh pham" (sheet
# "Ton kho theo lo date", cot Q-V: Duoi 3T/3T-6T/6T-9T/9T-12T/12T-18T/Lon hon 18T). Dung "thang" =
# 30 ngay (xap xi, DNH khong ghi ro quy uoc lich trong file mau - neu can chinh xac tuyet doi theo
# thang duong lich thi phai hoi lai DNH, hien tai xap xi la du cho muc dich canh bao).
_EXPIRY_BUCKET_DAYS = [
    ("het_han", None, 0),           # da qua ExpiryDate
    ("duoi_3_thang", 0, 90),
    ("3_6_thang", 90, 180),
    ("6_9_thang", 180, 270),
    ("9_12_thang", 270, 360),
    ("12_18_thang", 360, 540),
    ("tren_18_thang", 540, None),
]


def _expiry_bucket(days_left: float) -> str:
    if days_left < 0:
        return "het_han"
    if days_left < 90:
        return "duoi_3_thang"
    if days_left < 180:
        return "3_6_thang"
    if days_left < 270:
        return "6_9_thang"
    if days_left < 360:
        return "9_12_thang"
    if days_left < 540:
        return "12_18_thang"
    return "tren_18_thang"


def inventory_expiry_report(area_code: str = None, max_bucket: str = None, limit: int = 30,
                             scope_area_code: str = None) -> dict:
    """Bao cao TON KHO THEO LO + HAN SU DUNG - tra loi cau hoi "hang nao sap het han/can date/da het
    han", KHAC voi inventory_by_region() (chi co TONG so luong/gia tri theo vung, KHONG biet lo/han
    su dung). Nguon: brv_tonkhodklot (ton kho tung lo) JOIN brv_lot (ngay san xuat/het han theo lo) -
    xem local_warehouse.py::SCHEMA ve ly do BAT BUOC join CA HAI cot (item_lot_code, item_id), vi ma
    lo CO THE trung giua cac san pham khac nhau tren Bravo (xac nhan 13/08/2026, vd ma lo '020521'
    xuat hien o nhieu san pham voi han su dung khac nhau).

    Phan loai theo SO THANG CON LAI (khop voi file Excel "Bao cao ton kho thanh pham" DNH dang dung
    thu cong - sheet "Ton kho theo lo date"): het_han (da qua han), duoi_3_thang, 3_6_thang,
    6_9_thang, 9_12_thang, 12_18_thang, tren_18_thang. LUON tra ve "summary" (tong gia tri + so luong
    theo TUNG khung, toan bo pham vi) DE nguoi dung thay duoc BUC TRANH TONG THE truoc, "rows" (chi
    tiet tung lo, XEP THEO SO NGAY CON LAI IT NHAT truoc - het han/sap het han len dau) chi la mau
    minh hoa GIOI HAN theo limit, KHONG PHAI danh sach day du - PHAI noi ro dieu nay khi tra loi neu
    tong so lo trong khung do lon hon limit.

    area_code: 'MB'/'MT'/'MN' - loc theo vung (branch_code), bo trong = toan cong ty (gom ca San xuat).
    max_bucket: neu truyen (vd '3_6_thang'), CHI tra ve cac lo tu khung do TRO XUONG (gan het han
    hon) - dung khi nguoi dung hoi "hang nao con duoi 6 thang" v.v. Cac gia tri hop le: het_han,
    duoi_3_thang, 3_6_thang, 6_9_thang, 9_12_thang, 12_18_thang, tren_18_thang (dung dung ten nay,
    KHONG tu doi dinh dang).
    scope_area_code: EP GHI DE area_code khi tai khoan bi gioi han vung (giong inventory_by_region).

    LUU Y QUAN TRONG: du lieu chi co O CAC LO CON HOAT DONG (is_active=1) va CON SO LUONG TON >0 -
    lo da xuat het/ngung theo doi se KHONG xuat hien, day la BINH THUONG (khong phai thieu du lieu).
    Neu 1 lo TON KHO nhung KHONG tim thay han su dung trong brv_lot (hiem, xem "khong_xac_dinh_han"
    trong summary), PHAI noi ro la "chua xac dinh duoc han su dung" cho phan do, TUYET DOI KHONG bo
    qua trong im lang hay coi nhu khong co han.

    21/08/2026: THEM canh bao do moi dong bo ("sync_warning" trong ket qua, chi xuat hien khi lan
    dong bo brv_tonkhodklot/brv_lot gan nhat CU HON 6 GIO - cung nguong voi cong no) - day la du
    lieu tu Bravo qua sync dinh ky, KHONG realtime; neu dong bo bi tre/loi ma khong canh bao, so
    lieu het han/con date co the SAI LECH THUC TE (vd lo da xuat het nhung he thong local chua kip
    cap nhat) ma khong ai biet. day la RUI RO VAN HANH khong sua duoc tu code (phu thuoc chat luong
    dong bo Bravo /VPN/lich chay), nen chi co the CANH BAO ro cho nguoi dung biet gioi han nay."""
    if scope_area_code:
        area_code = scope_area_code
    branch_filter = _AREA_TO_BRANCH.get(area_code) if area_code else None
    if scope_area_code and not branch_filter:
        return {"error": f"Khong xac dinh duoc vung '{scope_area_code}' de loc ton kho theo han su dung."}

    valid_buckets = [b[0] for b in _EXPIRY_BUCKET_DAYS]
    if max_bucket and max_bucket not in valid_buckets:
        return {"error": f"max_bucket '{max_bucket}' khong hop le. Cac gia tri hop le: {', '.join(valid_buckets)}."}

    sql = """SELECT t.item_lot_code, t.item_id, sp.name item_name, t.quantity, t.branch_code,
                    k.branch_code kho_branch, l.mfg_date, l.expiry_date
             FROM brv_tonkhodklot t
             LEFT JOIN brv_lot l ON l.item_lot_code = t.item_lot_code AND l.item_id = t.item_id
             LEFT JOIN brv_sanpham sp ON sp.id_code = t.item_id
             LEFT JOIN brv_kho k ON k.id_code = t.warehouse_id
             WHERE t.is_active = 1 AND t.quantity > 0"""
    # 04/09/2026 - LOI NANG DA SUA: cung ly do inventory_by_region. Khong loc nam thi ton dau ky
    # nam 2024/2025 (hang da ban het tu lau) van bi tinh, sinh ra 668 "lo da het han" voi 7,67 trieu
    # don vi - hoan toan la lo ma. Loc nam 2026: 0 lo het han.
    nam_lot_moi = _nam_moi_nhat("brv_tonkhodklot", "year")
    params = []
    if nam_lot_moi is not None:
        sql += " AND t.year = ?"
        params.append(nam_lot_moi)
    if branch_filter:
        sql += " AND t.branch_code = ?"
        params.append(branch_filter)
    rows = _q(sql, tuple(params))

    today = dt.date.today()
    summary = {b[0]: {"so_lo": 0, "tong_so_luong": 0.0} for b in _EXPIRY_BUCKET_DAYS}
    unknown_expiry_count = 0
    detail = []
    for r in rows:
        qty = _f(r["quantity"])
        if not r["expiry_date"]:
            unknown_expiry_count += 1
            continue
        try:
            expiry = dt.date.fromisoformat(r["expiry_date"])
        except (ValueError, TypeError):
            unknown_expiry_count += 1
            continue
        days_left = (expiry - today).days
        bucket = _expiry_bucket(days_left)
        summary[bucket]["so_lo"] += 1
        summary[bucket]["tong_so_luong"] += qty
        detail.append({
            "item_lot_code": r["item_lot_code"],
            "item_name": r["item_name"] or f'(chua co ten - ma {r["item_id"]})',
            "quantity": qty,
            "branch_code": r["kho_branch"] or r["branch_code"],
            "area_label": _BRANCH_LABEL.get(r["kho_branch"] or r["branch_code"], r["kho_branch"] or r["branch_code"]),
            "mfg_date": r["mfg_date"],
            "expiry_date": r["expiry_date"],
            "days_left": days_left,
            "bucket": bucket,
        })

    if max_bucket:
        allowed = set(valid_buckets[:valid_buckets.index(max_bucket) + 1])
        detail = [d for d in detail if d["bucket"] in allowed]

    detail.sort(key=lambda d: d["days_left"])

    # Canh bao do moi dong bo - cung nguong 6 gio voi cong no (_customer_receivable/receivables_overview).
    # brv_tonkhodklot va brv_lot dong bo CUNG 1 lan (2 bang duoc them chung trong SMALL_TABLES, xem
    # sync_warehouse.py) nen chi can kiem tra 1 trong 2, lay bang co Y NGHIA nghiep vu ro hon (ton kho).
    sync_warning = None
    try:
        last_synced_at, _, _ = get_sync_meta("brv_tonkhodklot")
        if last_synced_at:
            age_h = (dt.datetime.now() - dt.datetime.fromisoformat(last_synced_at)).total_seconds() / 3600.0
            if age_h > 6:
                sync_warning = (
                    f"Du lieu ton kho theo lo nay dong bo tu Bravo lan gan nhat luc {last_synced_at} "
                    f"(da cu hon {age_h:.0f} gio) - so lo/han su dung CO THE da thay doi tren he thong "
                    "that (xuat kho, nhap lo moi...) ma chua duoc cap nhat vao day. PHAI noi ro voi "
                    "nguoi dung day la so lieu tai lan dong bo gan nhat, khong phai realtime.")
    except Exception:
        pass

    return {
        "as_of": str(today),
        "area_code": area_code,
        "summary": summary,
        "khong_xac_dinh_han": unknown_expiry_count,
        "tong_so_lo_hien_thi": len(detail),
        "rows": detail[:limit],
        "note": (f"Chi hien thi {min(limit, len(detail))}/{len(detail)} lo (sap xep gan het han nhat "
                 f"truoc) - dung 'summary' de biet TONG THE ca khung, 'rows' chi la mau minh hoa."
                 if len(detail) > limit else None),
        "sync_warning": sync_warning,
    }


# area_code (MB/MB2/MN/MT) -> ten mien tieng Viet, gom MB+MB2 thanh Mien Bac (theo REGION_SQL_MARKERS).
_AREA_TO_REGION_VI = {m: REGION_NAMES_VI[key] for key, ms in REGION_SQL_MARKERS.items() for m in ms}


def receivables_overview(top_n: int = 10, scope_area_code: str = None,
                         scope_channel: str = None) -> dict:
    """Tong quan CONG NO tu kho local fact_congno_khachhang (snapshot tuc thoi tu SP goc DNH
    usp_DeptAccDueDate_GetData): tong du no, tong qua han, ty le qua han, tach theo KENH (OTC/ETC)
    va theo VUNG, top N khach no qua han nhieu nhat.

    MOT DONG = (khach x kenh) nen luon SUM. scope_area_code: EP LOC theo vung khi tai khoan bi gioi
    han (regional_director/qlv) - dung REGION_SQL_MARKERS de gom ca MB va MB2 cho mien Bac.
    scope_channel: EP LOC OTC/ETC ngay trong SQL cho tai khoan Giam doc Kenh/OTC-only; khong chi
    an breakdown sau khi da tinh tong, de tong/top khach/bucket deu khong the lot kenh khac.

    Ket qua LUON kem "aging_bucket_note" (xem _AGING_BUCKET_NOTE) canh bao 4 bucket overdue_1_15/
    15_30/30_45/gt_45 lay THANG tu SP goc, co the khac moc Excel noi bo DNH hay dung.

    4 trang thai giong _customer_receivable:
      - unavailable: bang chua co du lieu -> canh bao BAT BUOC, khong ket luan "khong co no".
      - ok + canh bao moc thoi gian: snapshot cu > 6 gio.
      - ok: binh thuong.
    (khong co trang thai no_data rieng: neu co du lieu ma vung nay = 0 thi cac tong = 0, van la 'ok'.)
    """
    conditions, params = [], []
    if scope_area_code:
        region_key = next((k for k, ms in REGION_SQL_MARKERS.items() if scope_area_code in ms), None)
        markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code])
        conditions.append(f"area_code IN ({','.join(['?'] * len(markers))})")
        params.extend(markers)
    channel = None
    if scope_channel:
        channel = str(scope_channel).strip().upper()
        if channel not in {"OTC", "ETC"}:
            raise ValueError(f"scope_channel khong hop le: {scope_channel}")
        conditions.append("UPPER(TRIM(sales_channel))=?")
        params.append(channel)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    meta = _q(f"SELECT COUNT(*) n, MAX(snapshot_at) at FROM fact_congno_khachhang {where}",
              tuple(params))
    total_rows = int(meta[0]["n"]) if meta else 0
    if total_rows == 0:
        _warn("Bang cong no (fact_congno_khachhang) CHUA co du lieu (chua dong bo hoac SP loi). PHAI "
              "tra loi 'chua tra cuu duoc cong no', TUYET DOI KHONG ket luan 'khong co no'.")
        return {"receivable_status": "unavailable", "receivable_as_of": None,
                "receivable_source": "bao cao cong no goc DNH (SP)",
                "receivable_warning": (
                    "Chua tra cuu duoc cong no trong pham vi tai khoan tai thoi diem nay."),
                "scope_area_code": scope_area_code, "scope_channel": channel}

    snapshot_at = meta[0]["at"]

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
        by_area = _q(f"SELECT area_code, COALESCE(SUM(balance_end),0) bal, "
                     f"COALESCE(SUM(total_overdue),0) od FROM fact_congno_khachhang {where} "
                     f"GROUP BY area_code", tuple(params))
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
        "scope_channel": channel,
        "total_balance_end": total_balance,
        "total_overdue": total_overdue,
        "overdue_pct": (total_overdue / total_balance * 100) if total_balance else 0.0,
        "overdue_1_15": _f(tot["b1"]), "overdue_15_30": _f(tot["b2"]),
        "overdue_30_45": _f(tot["b3"]), "overdue_gt_45": _f(tot["b4"]),
        "aging_bucket_note": _AGING_BUCKET_NOTE,
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
    scope_parts = []
    if scope_area_code:
        scope_parts.append(f"vung {scope_area_code}")
    if channel:
        scope_parts.append(f"kenh {channel}")
    if scope_parts:
        result["scope_note"] = "(chi " + ", ".join(scope_parts) + ")"
    return result


# 29/07/2026 - GOP THEO THANG, khong ghim MOT save_date.
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


def _fdate_roster(fdate: str = None) -> str:
    """Ngay snapshot dung de xac dinh DANH SACH DOI (ai bao cao len ai) - KHAC voi ngay dung de doc
    SO LIEU cua mot ky.

    04/09/2026 - LOI NANG: fact_tonghopkhachhang la 1 dong/(nhan vien x khach hang), nen nhan vien
    CHUA BAN GI trong ky thi KHONG CO DONG NAO. Snapshot giua thang vi the KHONG phai danh sach doi
    - no la "danh sach nguoi da ban". Do that snapshot 04/09 (ngay thu 4 cua thang): toan cong ty chi
    con 47/186 nhan vien va 15/21 QLV; rieng doi TM25010183 co 10 TDV trong ca ba snapshot cuoi thang
    6/7/8 nhung chi con 2 TDV o snapshot 04/09.
    Hau qua da do duoc: cac ky KHONG co snapshot rieng (T1-T5/2026) roi ve snapshot moi nhat = ban
    co lai nay -> doanh thu doi chi ra ~22% so that, dung bang tong cua 2 nguoi con sot. T6-T8 dung
    vi co snapshot cuoi thang cua chinh ky do.

    Vi vay danh sach doi LUON lay tu snapshot CUOI THANG gan nhat (thang da tron), khong bao gio lay
    snapshot giua thang. Neu chua co thang nao tron thi danh moi lay ngay moi nhat va chap nhan."""
    ngay = _fact_date_le(fdate) if fdate else _fact_latest_date()
    if not ngay:
        return ngay
    ngay = str(ngay)
    # "Thang da tron" = thang cua snapshot do da co snapshot ngay CUOI CUNG cua no. Kiem bang cach
    # so voi ngay cuoi thang that su, khong dua vao quy uoc "ngay >= 28" (thang 2 chi co 28-29 ngay,
    # va DNH co the chot vao ngay khac).
    y, m = int(ngay[:4]), int(ngay[5:7])
    cuoi = "%04d-%02d-%02d" % (y, m, _last_day_of_month(y, m))
    if ngay >= cuoi:
        return ngay
    r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang "
           "WHERE substr(save_date,1,7)<?", (ngay[:7],))
    truoc = r[0]["d"] if r and r[0]["d"] else None
    return truoc or ngay


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
    # 04/09/2026: lay HOP cua hai moc thay vi mot moc.
    #   - moc THANG DA TRON  : giu du nguoi chua ban gi trong ky nay (chong co lai danh sach doi)
    #   - moc MOI NHAT       : giu NGUOI MOI VAO chua co trong anh chup thang truoc
    # Chi lay moc tron thi bo sot nguoi moi (do duoc: kiem_11 lech tu 0,831% len 1,713%); chi lay
    # moc moi nhat thi dinh dung bay co lai da gay loi M01. Hop hai moc giu duoc ca hai.
    moc_tron = _fdate_roster(fdate)
    moc_moi = _fact_date_le(fdate) if fdate else _fact_latest_date()
    cac_moc = [d for d in dict.fromkeys([moc_tron, moc_moi]) if d]
    if len(cac_moc) > 1:
        phan = " UNION ".join(
            f"SELECT DISTINCT e.employee_code, nv.name FROM fact_tonghopkhachhang e "
            f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=e.employee_code AND l.d=e.save_date "
            f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code "
            f"WHERE e.manager_code=? AND nv.position_code='TDV'" for _ in cac_moc)
        tham = tuple(x for d in cac_moc for x in (d, d, qlv_employee_code))
        return _q(phan, tham)
    fdate = moc_tron
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
    nhay cam hon so lieu tong hop thong thuong. 24/08/2026: cung TU DONG gioi han ca tang TP xuong dung
    vung cua QLV do (truoc day chi loc QLV, van tra ve TP cac vung khac voi node rong - xem ghi chu
    "BUG DA SUA" trong than ham); neu khong xac dinh duoc vung cua QLV se tra ve loi ro rang thay vi
    am tham bo qua loc. Cac 'to' KHONG xac dinh duoc QLV (xem org_hierarchy.py)
    se KHONG xuat hien duoi bat ky TP nao - can luu y khi doc ket qua co the thieu 1 vai to.
    LUU Y QUAN TRONG: cap TP hien LUON co sales/target/pct = 0 (Bravo khong tracking target ca nhan
    cho TP trong fact_tonghopkhachhang) - khi tra loi PHAI noi ro so 0 nay la "chua co du lieu target
    rieng cho TP", TUYET DOI KHONG bao la TP "khong dat KPI"/0% - do la thong tin sai lech nghiem trong.
    Muon biet tong doanh thu THAT cua ca vung TP phu trach, cong don sales cua tat ca QLV ben duoi
    (hoac dung get_revenue_by_region cho doanh thu hoa don thuc te, khac voi so KPI o day).

    27/07/2026 - DONG BO voi kpi_ranking()/_rollup_tier_codes(): truoc day danh sach "QLV" duoi moi TP
    loc truc tiep position_code='QLV' AND is_duplicate<>1, BO SOT cac NHOM/KENH nhu 'Kênh MT'/'Chợ sỹ'
    (Mien Nam - IsDuplicate=1 vi Bravo gan trung ma, khong phai QLV that bi trung). Hau qua THUC TE: cay
    QLV/TDV cua Mien Nam ra 3,50 ty trong khi tong vung (get_revenue_by_region) la 6,25 ty - nguoi dung
    phai HOI LAI "con thieu gi" moi duoc bao thieu Kenh MT (2,73 ty) + Cho si (0,15 ty). Gio dung CHUNG
    _rollup_tier_codes(fdate) (theo manager_code THAT) lam nguon danh sach QLV, giong het kpi_ranking -
    2 tool nay LUON phai ra cung tong 1 vung, khong con truong hop tong khop nhung bóc tach le."""
    if scope_area_code:
        area_code = scope_area_code
    if as_of_date is None:
        as_of_date = str(dt.date.today())
    # 24/08/2026: BUG DA SUA - scope_employee_code truoc day CHI loc qlv_rows BEN TRONG vong lap (xem
    # duoi), nhung vong lap "for tp in tp_rows" van chay qua TAT CA TP toan cong ty truoc do. Voi cac
    # TP khong lien quan, code tao 1 node RONG (qlv=[]) thay vi loai han - lo TEN + MA nhan vien cua
    # Truong phong CAC VUNG KHAC cho tai khoan QLV (xac nhan that: QLV MBKV1 vung MB nhan ve ca TP
    # Mien Nam/Mien Trung du qlv_count=0). Sua: tra area_code CUA CHINH QLV do truoc, gan vao bien
    # area_code local de tp_sql o duoi TU LOC theo dung 1 vung ngay tu dau - dung chung co che loc
    # area_code da co san, khong them nhanh loc song song moi. Bo loc qlv_rows ben duoi GIU NGUYEN
    # lam lop bao ve thu 2 (phong truong hop 1 vung co nhieu TP).
    if scope_employee_code and not area_code:
        qlv_area_r = _q("SELECT area_code FROM dim_nhanvien WHERE employee_code=?", (scope_employee_code,))
        if qlv_area_r and qlv_area_r[0]["area_code"]:
            area_code = qlv_area_r[0]["area_code"]
        else:
            # Fail-closed: KHONG xac dinh duoc vung cua QLV nay -> KHONG duoc de tp_sql roi ve khong
            # loc gi (se quay lai dung bug cu, loop toan bo TP toan cong ty). Tha tu choi con hon lo
            # ten/ma cac Truong phong vung khac.
            return {"as_of": None, "tree": [], "error": (
                f"Khong xac dinh duoc vung phu trach cua tai khoan '{scope_employee_code}' de gioi han "
                "cay to chuc - tam thoi khong the tra ket qua de tranh lo du lieu ngoai pham vi.")}
    # 13/08/2026: dung CHUNG _fact_date_le() voi bo loc pham vi doanh thu (_employee_scope_clause).
    # Truoc do 2 ben tu tinh moc chot doi mot kieu nen lech nhau 8/18 QLV - viet 1 lan o 1 cho thi
    # khong the lech tro lai.
    fdate = _fact_date_le(as_of_date)
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
            # 10/08/2026: phat hien khi test cau "doanh so mien bac theo qlv" - MB co 1 QLV
            # (MBKV12, ba Nguyen Thi Thanh Thuy, 0 TDV) TRUNG TEN voi chinh TP dang quan ly ca vung
            # MB (cung la Nguyen Thi Thanh Thuy). Day la ca da duoc ghi nhan tu 21/07/2026 (muc A4,
            # Cau_hoi_can_DNH_xac_nhan.md) - nghi Bravo co 2 ban ghi cho cung 1 nguoi (1 o cap TP quan
            # ly ca vung, 1 o cap QLV rieng le), CHUA duoc DNH xac nhan la QLV that hay chi la ban ghi
            # trung. Neu khong danh dau, model de bi cau hoi "doanh so theo QLV" cua vung nay lam roi
            # (thay 1 nguoi vua la sep vung vua la "nhan vien" duoi quyen chinh minh) roi goi lai tool
            # nhieu lan/di do SQL tho thay vi tra loi thang - xem ghi chu doi chieu voi hanh vi that
            # trong nl2sql.py (session 20b6c3d5, 10/08, cau "doanh so mien bac theo qlv").
            elif qlv["name"] and tp["name"] and qlv["name"].strip() == tp["name"].strip():
                qlv_entry["ghi_chu"] = (
                    f"CANH BAO DU LIEU: '{qlv['name']}' (ma QLV {qlv['employee_code']}) TRUNG TEN voi "
                    f"chinh Truong phong dang phu trach ca vung {tp['area_code']} (ma {tp['employee_code']}) "
                    "- rat co the la CUNG MOT NGUOI, Bravo dang luu 2 ban ghi rieng (1 cap TP, 1 cap QLV "
                    "voi 0 TDV). Day la ca DANG CHO DNH XAC NHAN (xem muc A4 trong "
                    "Cau_hoi_can_DNH_xac_nhan.md), CHUA RO day la QLV that hay ban ghi trung. KHI TRA "
                    "LOI ve nguoi/ma nay: PHAI neu ro nghi van trung ban ghi voi Truong phong vung, "
                    "KHONG duoc trinh bay nhu mot QLV thong thuong khac trong doi hinh.")
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

    limit = max(1, min(int(limit or 30), 100))

    # 28/07/2026: CHI dua vao scope_role - gia tri nay duoc call_template EP tu server (tu user["role"]
    # da xac thuc), AI khong the dua vao.
    # DA BO ve suy luan quyen theo CHUOI username (truoc day: username in ('admin','ceo'...) hoac
    # startswith('c_level'/'admin')). Hai ly do:
    #   - username cung chi la 1 chuoi, khi _SELF_SCOPED_TEMPLATES rong thi do AI dua -> tu nang quyen.
    #   - ngay ca khi ep dung tu server, suy quyen tu TEN tai khoan la sai nguyen tac: mot nguoi ten
    #     'admin.nguyen' hay 'ceo.tro.ly' se duoc quyen xem chi phi toan cong ty ma khong ai co y do.
    # Quyen phai doc tu vai tro trong CSDL tai khoan, khong doc tu cach dat ten.
    is_clevel_admin = bool(
        scope_role and str(scope_role).lower() in ('c_level', 'super_admin', 'ceo', 'cfo', 'admin_ops', 'admin')
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
    # 03/08/2026: Dem SO CAU HOI THAT (nhom theo session_id + question) thay vi dem audit_log entries
    # (tuc la dem SQL). Mot cau hoi KPI sinh ra 10+ lenh SQL nhung van chi la 1 cau hoi - phai dem la 1.
    _seen_q_keys = set()
    questions_by_user = {}
    cost_per_question = {}
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

                # --- 03/08/2026: Dem cau hoi + chi phi per-question ---
                q_preview = c.get("question_preview", "")
                q_key = (sid or "", q_preview)
                cpq = cost_per_question.setdefault(q_key, {
                    "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
                    "cache_read_tokens": 0, "cache_write_tokens": 0, "ts": c.get("ts")})
                cpq["cost_usd"] += cost
                cpq["input_tokens"] += p_tok
                cpq["output_tokens"] += c_tok
                cpq["cache_read_tokens"] += (c.get("cache_read_tokens", 0) or 0)
                cpq["cache_write_tokens"] += (c.get("cache_write_tokens", 0) or 0)
                if q_key not in _seen_q_keys:
                    _seen_q_keys.add(q_key)
                    _q_owner = owner or UNATTRIBUTED
                    questions_by_user[_q_owner] = questions_by_user.get(_q_owner, 0) + 1

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

    # 03/08/2026: Fallback - neu cost_log rong, dem dedup tu audit_log
    if not questions_by_user:
        _seen_audit_q = set()
        for e in my_entries:
            _k = e.get("username") or owner_of.get(e.get("session_id")) or UNATTRIBUTED
            _aq_key = (e.get("session_id") or "", (e.get("question") or "")[:120])
            if _aq_key not in _seen_audit_q:
                _seen_audit_q.add(_aq_key)
                questions_by_user[_k] = questions_by_user.get(_k, 0) + 1

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

    # 03/08/2026: Dedup history - moi (session, question) chi hien 1 dong, hien chi phi per-question.
    _seen_history_q = set()
    recent = []
    for e in sorted(my_entries, key=lambda e: e.get("ts", ""), reverse=True):
        _hq_key = (e.get("session_id") or "", (e.get("question") or "")[:120])
        if _hq_key in _seen_history_q:
            continue
        _seen_history_q.add(_hq_key)
        recent.append(e)
        if len(recent) >= limit:
            break
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
        "question_cost_usd": cost_per_question.get(
            (e.get("session_id") or "", (e.get("question") or "")[:120]), {}).get("cost_usd"),
        "question_input_tokens": cost_per_question.get(
            (e.get("session_id") or "", (e.get("question") or "")[:120]), {}).get("input_tokens"),
        "question_output_tokens": cost_per_question.get(
            (e.get("session_id") or "", (e.get("question") or "")[:120]), {}).get("output_tokens"),
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
        _keys = set(cost_by_user) | set(sessions_by_user) | set(questions_by_user)
        user_breakdown = []
        for u in sorted(_keys, key=lambda k: -cost_by_user.get(k, _zero)["cost_usd"]):
            d = cost_by_user.get(u, _zero)
            user_breakdown.append({
                "username": u,
                "queries": questions_by_user.get(u, 0),
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
        "total_queries": sum(questions_by_user.values()) or len(my_entries),
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


def _shift_month_start(value: dt.date, months: int) -> dt.date:
    month_index = value.year * 12 + (value.month - 1) + months
    return dt.date(month_index // 12, month_index % 12 + 1, 1)


def customer_revenue_debt_risk(as_of_date: str = None, recent_months: int = 3,
                               min_revenue: float = 100_000_000,
                               min_overdue: float = 50_000_000, limit: int = 20,
                               scope_area_code: str = None, scope_employee_code: str = None,
                               scope_channel: str = None) -> dict:
    """Khach doanh thu lon + no cao + doanh thu giam, trong MOT truy van warehouse da kiem soat."""
    recent_months = min(max(int(recent_months or 3), 1), 12)
    limit = min(max(int(limit or 20), 1), 100)
    data_day = _parse_report_date(as_of_date or latest_data_date(), "as_of_date")
    this_month = dt.date(data_day.year, data_day.month, 1)
    recent_end = data_day if data_day == _month_end(data_day) else this_month - dt.timedelta(days=1)
    recent_start = _shift_month_start(dt.date(recent_end.year, recent_end.month, 1), -(recent_months - 1))
    prior_end = recent_start - dt.timedelta(days=1)
    prior_start = _shift_month_start(dt.date(prior_end.year, prior_end.month, 1), -(recent_months - 1))

    channel = str(scope_channel or "ALL").upper()
    if channel not in {"ALL", "OTC", "ETC"}:
        channel = "ALL"
    dms_ids = _get_team_dms_ids(scope_employee_code, str(recent_end)) if scope_employee_code else []

    sales_parts = []
    sales_params = []
    for table, label in (("vhoadon_otc", "OTC"), ("vhoadon_etc", "ETC")):
        if channel != "ALL" and channel != label:
            continue
        employee_filter = ""
        if dms_ids:
            employee_filter = f" AND v.employee_code IN ({','.join(['?'] * len(dms_ids))})"
        sales_parts.append(
            f"SELECT v.customer_code, v.doc_date, v.amount9 FROM {table} v "
            f"WHERE v.doc_date BETWEEN ? AND ?{employee_filter}"
        )
        sales_params.extend([str(prior_start), str(recent_end)])
        sales_params.extend(dms_ids)
    if not sales_parts:
        return {"customers": [], "status": "no_data"}

    debt_where = ["c.snapshot_date=(SELECT MAX(snapshot_date) FROM fact_congno_khachhang)"]
    debt_params = []
    if channel != "ALL":
        debt_where.append("c.sales_channel=?")
        debt_params.append(channel)
    if scope_area_code:
        region_key = next((key for key, markers in REGION_SQL_MARKERS.items()
                           if scope_area_code in markers), None)
        markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code])
        debt_where.append(f"c.area_code IN ({','.join(['?'] * len(markers))})")
        debt_params.extend(markers)
    if dms_ids:
        debt_where.append(
            "EXISTS (SELECT 1 FROM dms_khachhang kh WHERE kh.code=c.customer_code "
            f"AND kh.emp_code IN ({','.join(['?'] * len(dms_ids))}))"
        )
        debt_params.extend(dms_ids)

    sql = f"""
        WITH all_sales AS (
            {' UNION ALL '.join(sales_parts)}
        ), revenue AS (
            SELECT customer_code,
                   SUM(CASE WHEN doc_date BETWEEN ? AND ? THEN amount9 ELSE 0 END) rev_recent,
                   SUM(CASE WHEN doc_date BETWEEN ? AND ? THEN amount9 ELSE 0 END) rev_prior
            FROM all_sales GROUP BY customer_code
        ), debt AS (
            SELECT c.customer_code, MAX(c.customer_name) customer_name,
                   SUM(c.balance_end) balance_end, SUM(c.total_overdue) overdue,
                   MAX(c.snapshot_at) snapshot_at
            FROM fact_congno_khachhang c
            WHERE {' AND '.join(debt_where)}
            GROUP BY c.customer_code
        )
        SELECT r.customer_code, d.customer_name, r.rev_recent, r.rev_prior,
               CASE WHEN r.rev_prior<>0 THEN (r.rev_recent-r.rev_prior)*100.0/r.rev_prior END pct_change,
               d.balance_end, d.overdue, d.snapshot_at
        FROM revenue r INNER JOIN debt d ON d.customer_code=r.customer_code
        WHERE r.rev_recent>=? AND d.overdue>=? AND r.rev_recent<r.rev_prior
        ORDER BY d.overdue DESC, r.rev_recent DESC
        LIMIT ?
    """
    params = (sales_params
              + [str(recent_start), str(recent_end), str(prior_start), str(prior_end)]
              + debt_params + [float(min_revenue), float(min_overdue), limit])
    rows = _q(sql, tuple(params))
    customers = [{
        "customer_code": row.get("customer_code"),
        "customer_name": row.get("customer_name"),
        "recent_revenue": _f(row.get("rev_recent")),
        "prior_revenue": _f(row.get("rev_prior")),
        "change_pct": round(_f(row.get("pct_change")), 1),
        "balance_end": _f(row.get("balance_end")),
        "overdue": _f(row.get("overdue")),
    } for row in rows]
    return {
        "status": "ok",
        "recent_period": {"from": str(recent_start), "to": str(recent_end)},
        "prior_period": {"from": str(prior_start), "to": str(prior_end)},
        "revenue_threshold": float(min_revenue),
        "overdue_threshold": float(min_overdue),
        "customer_count": len(customers),
        "customers": customers,
        "receivable_snapshot_at": rows[0].get("snapshot_at") if rows else None,
        "note": "Danh sach chi gom khach dong thoi dat nguong doanh thu, no qua han va doanh thu giam.",
    }


def _parse_report_date(value, field_name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} phai co dinh dang YYYY-MM-DD.")


def _month_end(value: dt.date) -> dt.date:
    next_month = (dt.date(value.year + 1, 1, 1) if value.month == 12
                  else dt.date(value.year, value.month + 1, 1))
    return next_month - dt.timedelta(days=1)


def promotion_effectiveness(date_from: str = None, date_to: str = None, limit: int = 20,
                            scope_area_code: str = None, scope_employee_code: str = None,
                            scope_channel: str = None) -> dict:
    """Hieu qua CTKM theo DON HANG THUC SU gan chuong trinh tren DMS.

    Nguon dung la DMS_DonHangCTKM -> DMS_CTKM -> DMS_DonHangHdr, KHONG phai cot CTKM tu do tren
    vHoaDonTotal (cot do co ca ghi chu/nguoi lien he va da gay ra bang sai tren production).

    Doanh thu o day la doanh thu GAN VOI don hang co su dung CTKM. Mot don co the dung nhieu CTKM,
    vi vay doanh thu cua cac chuong trinh KHONG cong ngang voi nhau de ra doanh thu cong ty va KHONG
    duoc goi la ROI/uplift neu chua co chi phi va nhom doi chung.
    """
    limit = min(max(int(limit or 20), 1), 50)
    if scope_channel and str(scope_channel).upper() not in ("OTC", "ALL"):
        return {
            "status": "not_applicable",
            "programs": [],
            "note": "Du lieu chuong trinh DMS nay thuoc kenh OTC; pham vi tai khoan khong co kenh OTC.",
        }

    coverage_rows = _q_bravo("""
        SELECT TOP (1) h.DocDate AS CoverageDate, x.SyncAt AS LinkSyncedAt, x.Id AS LinkRowId
        FROM dbo.DMS_DonHangCTKM x
        LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
        ORDER BY x.Id DESC
    """)
    coverage_date = coverage_rows[0].get("CoverageDate") if coverage_rows else None
    if not coverage_date:
        return {
            "status": "source_gap",
            "programs": [],
            "note": "Khong xac dinh duoc moc du lieu don hang gan chuong trinh khuyen mai.",
        }
    if not isinstance(coverage_date, dt.date):
        coverage_date = _parse_report_date(coverage_date, "coverage_date")

    used_default_period = not date_from and not date_to
    if used_default_period:
        # Chi dung THANG DAY DU gan nhat. Neu link moi nhat dang o giua thang thi lui ve thang truoc.
        report_to = dt.date(coverage_date.year, coverage_date.month, 1) - dt.timedelta(days=1)
        report_from = dt.date(report_to.year, report_to.month, 1)
    else:
        report_to = _parse_report_date(date_to or date_from, "date_to")
        report_from = (_parse_report_date(date_from, "date_from") if date_from
                       else dt.date(report_to.year, report_to.month, 1))
    if report_from > report_to:
        raise ValueError("date_from khong duoc lon hon date_to.")

    requested_to = report_to
    if report_from > coverage_date:
        return {
            "status": "source_gap",
            "requested_period": {"from": str(report_from), "to": str(report_to)},
            "promotion_link_coverage_to": str(coverage_date),
            "programs": [],
            "warning": (
                "Bang lien ket don hang-chuong trinh khong co du lieu den ky duoc hoi. "
                "Khong dung cot CTKM tren hoa don de thay the vi cot do la ghi chu tu do."
            ),
        }
    report_to = min(report_to, coverage_date)
    date_to_exclusive = report_to + dt.timedelta(days=1)

    params = {
        "date_from": report_from,
        "date_to_exclusive": date_to_exclusive,
    }
    scope_joins = ""
    scope_where = ""
    if scope_area_code:
        scope_joins += (" LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=h.CustomerCode "
                        " LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId ")
        scope_where += " AND tp.AreaCode=:scope_area_code"
        params["scope_area_code"] = scope_area_code
    if scope_employee_code:
        dms_ids = _get_team_dms_ids(scope_employee_code, str(report_to))
        emp_placeholders = []
        for idx, dms_id in enumerate(dms_ids):
            key = f"emp_{idx}"
            params[key] = dms_id
            emp_placeholders.append(f":{key}")
        joined = ",".join(emp_placeholders)
        scope_where += f" AND (h.DMSEmpId1 IN ({joined}) OR h.DMSEmpId2 IN ({joined}))"

    rows = _q_bravo(f"""
        WITH ProgramOrders AS (
            SELECT x.ProgId, x.OrderId, MAX(h.CustomerCode) AS CustomerCode
            FROM dbo.DMS_DonHangHdr h
            INNER HASH JOIN dbo.DMS_DonHangCTKM x ON x.OrderId=h.Id
            {scope_joins}
            WHERE h.DocDate>=:date_from AND h.DocDate<:date_to_exclusive {scope_where}
            GROUP BY x.ProgId, x.OrderId
        ),
        InvoiceByOrder AS (
            SELECT TRY_CONVERT(int, DMSId) AS OrderId,
                   SUM(Amount9) AS Revenue,
                   COUNT(DISTINCT CASE WHEN UnitPrice>0 THEN ItemCode END) AS PaidProductCount
            FROM dbo.vHoaDonTotal
            WHERE DocDate>=:date_from AND DocDate<:date_to_exclusive
              AND TRY_CONVERT(int, DMSId) IS NOT NULL
            GROUP BY TRY_CONVERT(int, DMSId)
        ),
        GiftProducts AS (
            SELECT po.ProgId, COUNT(DISTINCT NULLIF(x.ItemCode, '')) AS GiftProductCount
            FROM ProgramOrders po
            INNER JOIN dbo.DMS_DonHangCTKM x
              ON x.ProgId=po.ProgId AND x.OrderId=po.OrderId
            GROUP BY po.ProgId
        ),
        ConfiguredProducts AS (
            SELECT t.ProgId, COUNT(DISTINCT NULLIF(d.ItemId, '')) AS ConfiguredProductCount
            FROM dbo.DMS_CTKMOnTop1 t
            INNER JOIN dbo.DMS_DKKMCt d ON d.CondId=t.CondId
            GROUP BY t.ProgId
        )
        SELECT TOP ({limit})
               p.Id AS ProgramId, p.Code AS ProgramCode, p.Name AS ProgramName,
               COUNT_BIG(*) AS Orders,
               COUNT(DISTINCT po.CustomerCode) AS Customers,
               SUM(ISNULL(i.Revenue, 0)) AS AssociatedRevenue,
               SUM(CASE WHEN i.OrderId IS NULL THEN 1 ELSE 0 END) AS OrdersWithoutInvoice,
               SUM(ISNULL(i.PaidProductCount, 0)) AS PaidProductOccurrences,
               MAX(ISNULL(g.GiftProductCount, 0)) AS GiftProductCount,
               MAX(ISNULL(c.ConfiguredProductCount, 0)) AS ConfiguredProductCount
        FROM ProgramOrders po
        INNER JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId
        LEFT HASH JOIN InvoiceByOrder i ON i.OrderId=po.OrderId
        LEFT JOIN GiftProducts g ON g.ProgId=po.ProgId
        LEFT JOIN ConfiguredProducts c ON c.ProgId=po.ProgId
        GROUP BY p.Id, p.Code, p.Name
        ORDER BY AssociatedRevenue DESC
        OPTION (HASH JOIN)
    """, params)

    programs = []
    for row in rows:
        orders = int(row.get("Orders") or 0)
        invoiced_orders = max(orders - int(row.get("OrdersWithoutInvoice") or 0), 0)
        revenue = _f(row.get("AssociatedRevenue"))
        programs.append({
            "program_id": row.get("ProgramId"),
            "program_code": row.get("ProgramCode"),
            "program_name": row.get("ProgramName"),
            "associated_revenue": revenue,
            "participating_customers": int(row.get("Customers") or 0),
            "orders": orders,
            "invoiced_orders": invoiced_orders,
            "average_revenue_per_invoiced_order": revenue / invoiced_orders if invoiced_orders else 0.0,
            "configured_product_count": int(row.get("ConfiguredProductCount") or 0),
            "gift_product_count": int(row.get("GiftProductCount") or 0),
            "paid_product_occurrences": int(row.get("PaidProductOccurrences") or 0),
        })

    warning = None
    if requested_to > coverage_date:
        warning = (f"Du lieu lien ket don hang-chuong trinh moi den {coverage_date}; "
                   f"bao cao da cat tai moc nay thay vi suy dien den {requested_to}.")
    elif used_default_period:
        warning = (f"Khong co ky duoc chi dinh; dung thang day du gan nhat {report_from:%m/%Y}. "
                   f"Lien ket don hang-chuong trinh moi nhat ghi nhan den {coverage_date}.")

    return {
        "status": "ok" if programs else "no_data",
        "period": {"from": str(report_from), "to": str(report_to)},
        "promotion_link_coverage_to": str(coverage_date),
        "promotion_link_synced_at": str(coverage_rows[0].get("LinkSyncedAt") or ""),
        "warning": warning,
        "interpretation_note": (
            "associated_revenue la doanh thu cua don hang co gan chuong trinh. Mot don co the dung "
            "nhieu chuong trinh nen KHONG cong doanh thu cac dong voi nhau, va chua du co so ket luan "
            "ROI/uplift neu thieu chi phi chuong trinh va nhom doi chung."
        ),
        "program_count_returned": len(programs),
        "programs": programs,
    }


def promotion_data_quality(scope_area_code: str = None, scope_employee_code: str = None,
                           scope_channel: str = None) -> dict:
    """Do phu va chat luong chuoi DMS_DonHangCTKM -> don hang -> chuong trinh trong 1 query.

    Day la duong nhanh, co dinh cho cac cau hoi ve moc du lieu/missing link. Truoc day model phai
    search catalog + query SQL live qua nhieu vong, gay P95 hon 100 giay cho Q083/Q084.
    """
    if scope_channel and str(scope_channel).upper() not in ("OTC", "ALL"):
        return {
            "status": "not_applicable",
            "note": "Du lieu lien ket chuong trinh DMS thuoc kenh OTC; tai khoan khong co kenh OTC.",
        }

    joins = ""
    where = ""
    params = {}
    if scope_area_code:
        joins += (
            " LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=h.CustomerCode "
            " LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId "
        )
        where += " AND tp.AreaCode=:scope_area_code"
        params["scope_area_code"] = scope_area_code
    if scope_employee_code:
        dms_ids = _get_team_dms_ids(scope_employee_code)
        placeholders = []
        for index, dms_id in enumerate(dms_ids):
            key = f"employee_{index}"
            params[key] = dms_id
            placeholders.append(f":{key}")
        joined = ",".join(placeholders)
        where += f" AND (h.DMSEmpId1 IN ({joined}) OR h.DMSEmpId2 IN ({joined}))"

    rows = _q_bravo(f"""
        SELECT MIN(h.DocDate) AS FirstLinkedOrderDate,
               MAX(h.DocDate) AS LastLinkedOrderDate,
               COUNT_BIG(*) AS LinkRows,
               COUNT(DISTINCT x.OrderId) AS LinkedOrders,
               COUNT(DISTINCT x.ProgId) AS Programs,
               SUM(CASE WHEN h.Id IS NULL THEN 1 ELSE 0 END) AS MissingOrder,
               SUM(CASE WHEN p.Id IS NULL THEN 1 ELSE 0 END) AS MissingProgram,
               SUM(CASE WHEN h.Id IS NOT NULL AND p.Id IS NOT NULL THEN 1 ELSE 0 END) AS ValidLinks,
               MAX(x.SyncAt) AS LastLinkSyncAt
        FROM dbo.DMS_DonHangCTKM x
        LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
        LEFT JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
        {joins}
        WHERE 1=1 {where}
    """, params)
    if not rows:
        return {"status": "source_gap", "note": "Khong doc duoc chuoi lien ket CTKM."}
    row = rows[0]
    return {
        "status": "ok",
        "first_linked_order_date": str(row.get("FirstLinkedOrderDate") or ""),
        "last_linked_order_date": str(row.get("LastLinkedOrderDate") or ""),
        "last_link_sync_at": str(row.get("LastLinkSyncAt") or ""),
        "link_rows": int(row.get("LinkRows") or 0),
        "linked_orders": int(row.get("LinkedOrders") or 0),
        "programs": int(row.get("Programs") or 0),
        "missing_order": int(row.get("MissingOrder") or 0),
        "missing_program": int(row.get("MissingProgram") or 0),
        "valid_links": int(row.get("ValidLinks") or 0),
        "scope_note": (
            "Ket qua da gioi han theo pham vi tai khoan; lien ket mat don hang khong the quy vung/doi."
            if scope_area_code or scope_employee_code else None
        ),
    }


def salary_bonus_policy(bonus_type: str = "v25", as_of_date: str = None,
                        area_code: str = None, position_code: str = None,
                        scope_area_code: str = None, scope_employee_code: str = None,
                        scope_role: str = None) -> dict:
    """Quy tac + bac tien cua V15/V22/V25/ASO, doc tu DIM_BacThuong va doi chieu so da chot.

    Quy tac nghiep vu 27/08/2026: CS (Cho si) va TK (kenh MT) dung is_ac/Active Customer,
    khong co ASO. Vi vay truy van chinh sach ASO cho hai vai tro nay phai tra ve
    ``not_applicable`` thay vi doc nham bac ASO chung.
    """
    bonus = str(bonus_type or "v25").strip().upper()
    if bonus not in {"V15", "V22", "V25", "ASO"}:
        raise ValueError("bonus_type chi nhan V15, V22, V25 hoac ASO.")
    if scope_area_code:
        area_code = scope_area_code

    normalized_position = str(position_code or "").strip().upper()
    if bonus == "ASO" and _uses_is_ac(normalized_position):
        return {
            "bonus_type": bonus,
            "position_code": normalized_position,
            "not_applicable": True,
            "policy_as_of": None,
            "actual_snapshot_date": None,
            "formula": (
                "ASO khong ap dung cho CS (Cho si) va TK (kenh MT). Hai vai tro nay dung co "
                "is_ac/Active Customer; mot ban ghi da co is_ac thi khong duoc gan hoac cong ASO."
            ),
            "procedure_loads_v25_rules": None,
            "implementation_warning": None,
            "rule_actual_mismatch_count": 0,
            "rule_actual_mismatches": [],
            "terminology_note": (
                "CS/TK dung chi tieu Active Customer (is_ac), khong phai chi tieu/khoan thuong ASO."
            ),
            "rule_count": 0,
            "rules": [],
        }

    if as_of_date:
        raw = str(as_of_date).strip()
        if len(raw) == 7:
            requested = _month_end(dt.date.fromisoformat(raw + "-01"))
        else:
            requested = _parse_report_date(raw, "as_of_date")
    else:
        requested = dt.date.today()

    closed = _q(
        "SELECT MAX(save_date) d FROM fact_thongketinhluong "
        "WHERE save_date<=? AND save_date=date(save_date,'start of month','+1 month','-1 day')",
        (str(requested),),
    )
    snapshot_date = closed[0]["d"] if closed and closed[0]["d"] else None
    policy_date = _parse_report_date(snapshot_date, "snapshot_date") if snapshot_date else requested
    month_start = dt.date(policy_date.year, policy_date.month, 1)
    month_end = _month_end(policy_date)
    # DNH doi co che tu ky 07/2026: V25 dung han, V15/V22 bat dau duoc chi. Du lieu toan cong ty
    # 07-08/2026 deu co V25Bonus=0, ke ca QLV vuot nguong; day KHONG phai mismatch ca nhan hay loi
    # thu tuc. DIM_BacThuong co the van con dong V25 lich su/chua dong EndDate, khong duoc dung cac
    # dong cau hinh ton du do de de nghi bu thuong.
    v25_inactive_by_mechanism = bonus == "V25" and policy_date >= dt.date(2026, 7, 1)

    params = {
        "bonus_type": bonus,
        "month_start": month_start,
        "month_end": month_end,
    }
    where = ""
    if area_code:
        where += " AND AreaCode=:area_code"
        params["area_code"] = area_code
    if normalized_position:
        where += " AND PositionCode=:position_code"
        params["position_code"] = normalized_position

    rule_rows = _q_bravo(f"""
        SELECT CriterialCode, TypeCode, AreaCode, PositionCode, Description,
               StartDate, EndDate, IsTargetPercent, IsEarnPercent,
               FromValue, ToValue, Earn1, Earn2, EarnMax,
               CheckASO, CheckTargetEmp, ASOCusCondType
        FROM dbo.DIM_BacThuong
        WHERE TypeCode=:bonus_type
          AND StartDate<=:month_start
          AND (EndDate IS NULL OR EndDate>=:month_end)
          {where}
        ORDER BY AreaCode, PositionCode, BuildInOrder
    """, params)

    grouped = {}
    for row in rule_rows:
        key = (row.get("AreaCode"), row.get("PositionCode"), row.get("Description"))
        item = grouped.setdefault(key, {
            "area_code": row.get("AreaCode"),
            "position_code": row.get("PositionCode"),
            "description": row.get("Description"),
            "effective_from": str(row.get("StartDate") or ""),
            "effective_to": str(row.get("EndDate") or ""),
            "bands": [],
        })
        item["bands"].append({
            "from_pct_or_quantity": _f(row.get("FromValue")) if row.get("FromValue") is not None else None,
            "to_pct_or_quantity": _f(row.get("ToValue")) if row.get("ToValue") is not None else None,
            "bonus_amount": _f(row.get("Earn1")),
        })

    mismatch_rows = []
    procedure_loads_v25 = None
    if bonus == "V25" and snapshot_date and not v25_inactive_by_mechanism:
        actual_params = {
            "snapshot_date": _parse_report_date(snapshot_date, "snapshot_date"),
            "month_start": month_start,
            "month_end": month_end,
        }
        actual_where = ""
        if area_code:
            actual_where += " AND f.AreaCode=:actual_area_code"
            actual_params["actual_area_code"] = area_code
        if normalized_position:
            actual_where += " AND f.PositionCode=:actual_position_code"
            actual_params["actual_position_code"] = normalized_position
        if scope_employee_code:
            allowed_codes = [scope_employee_code]
            allowed_codes += [x.get("employee_code") for x in _team_of_qlv(scope_employee_code, snapshot_date)
                              if x.get("employee_code")]
            placeholders = []
            for idx, employee_code in enumerate(dict.fromkeys(allowed_codes)):
                key = f"allowed_{idx}"
                actual_params[key] = employee_code
                placeholders.append(f":{key}")
            actual_where += f" AND f.EmployeeCode IN ({','.join(placeholders)})"

        mismatch_rows = _q_bravo(f"""
            SELECT TOP (50) f.EmployeeCode, f.EmployeeName, f.AreaCode, f.PositionCode,
                   f.SaveDate, f.V25Date, f.V25Amount, f.MonthSaleTarget,
                   f.V25Percent_R, f.V25Bonus
            FROM dbo.FACT_ThongKeTinhLuong f
            WHERE f.SaveDate=:snapshot_date
              AND f.V25Percent_R>0.7
              AND ISNULL(f.V25Bonus, 0)=0
              {actual_where}
              AND EXISTS (
                  SELECT 1 FROM dbo.DIM_BacThuong b
                  WHERE b.TypeCode='V25'
                    AND b.AreaCode=f.AreaCode AND b.PositionCode=f.PositionCode
                    AND b.StartDate<=:month_start
                    AND (b.EndDate IS NULL OR b.EndDate>=:month_end)
                    AND ISNULL(b.Earn1, 0)>0
                    AND f.V25Percent_R>=ISNULL(b.FromValue, 0)/100.0
                    AND f.V25Percent_R<ISNULL(b.ToValue, 3000)/100.0
              )
            ORDER BY f.V25Percent_R DESC
        """, actual_params)
        mismatch_rows = [{
            "employee_code": row.get("EmployeeCode"),
            "employee_name": row.get("EmployeeName"),
            "area_code": row.get("AreaCode"),
            "position_code": row.get("PositionCode"),
            "snapshot_date": str(row.get("SaveDate") or ""),
            "v25_date": str(row.get("V25Date") or ""),
            "v25_amount": _f(row.get("V25Amount")),
            "month_target": _f(row.get("MonthSaleTarget")),
            "v25_percent": round(_f(row.get("V25Percent_R")) * 100, 2),
            "stored_v25_bonus": _f(row.get("V25Bonus")),
        } for row in mismatch_rows]

        try:
            definition_rows = _q_bravo(
                "SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.usp_SaleSalary_Calculation_Ver2')) AS Definition"
            )
            definition = str(definition_rows[0].get("Definition") or "") if definition_rows else ""
            upper = definition.upper()
            start = upper.find("INTO #KPICT")
            end = upper.find("#LONGKPICT", start + 1) if start >= 0 else -1
            section = upper[start:end] if start >= 0 and end > start else ""
            procedure_loads_v25 = "'V25'" in section
        except Exception:
            procedure_loads_v25 = None

    formula = {
        "V25": (
            "V25 chi ap dung den het ky 06/2026. Tu ky 07/2026 DNH da doi co che sang V15/V22; "
            "V25Bonus=0 trong cac ky tu 07/2026 la dung co che, KHONG PHAI loi tinh luong."
            if v25_inactive_by_mechanism else
            "Ty le V25 = doanh so luy ke den ngay chot V25 / chi tieu thang; doi chieu bac V25 "
            "dang hieu luc cho cac ky den het 06/2026."
        ),
        "V15": "Tinh doanh so luy ke den moc V15, doi chieu dieu kien va bac tien V15 dang hieu luc.",
        "V22": "Tinh doanh so luy ke den moc V22, doi chieu dieu kien va bac tien V22 dang hieu luc.",
        "ASO": (
            "ASO la thuong theo so luong/ty le khach hang hoat dong va cac cong dieu kien doanh so, "
            "khong phai ten mot chuc danh nhan vien."
        ),
    }[bonus]

    implementation_warning = None
    if bonus == "V25" and procedure_loads_v25 is False and not v25_inactive_by_mechanism:
        implementation_warning = (
            "Can DNH kiem tra usp_SaleSalary_Calculation_Ver2: khoi #KPICt hien khong nap TypeCode "
            "V25 nhung buoc sau lai JOIN #KPICt de gan V25Bonus. Chatbot chi bao so da luu va "
            "chenh lech, KHONG tu sua/tinh de len so chot cua SQL Server."
        )
    elif mismatch_rows and not v25_inactive_by_mechanism:
        implementation_warning = (
            "Co truong hop ty le V25 nam trong bac co tien thuong nhung V25Bonus da luu bang 0; "
            "can DNH/ke toan xac nhan truoc khi dung de chi tra."
        )

    return {
        "bonus_type": bonus,
        "policy_as_of": str(policy_date),
        "actual_snapshot_date": snapshot_date,
        "formula": formula,
        "mechanism_status": ("INACTIVE_FROM_2026_07_REPLACED_BY_V15_V22"
                             if v25_inactive_by_mechanism else "ACTIVE_FOR_REQUESTED_PERIOD"),
        "procedure_loads_v25_rules": procedure_loads_v25,
        "implementation_warning": implementation_warning,
        "rule_actual_mismatch_count": len(mismatch_rows),
        "rule_actual_mismatches": mismatch_rows,
        "inactive_rule_rows_count": len(rule_rows) if v25_inactive_by_mechanism else 0,
        "terminology_note": (
            "Trong du lieu tinh luong DNH, ASO la mot chi tieu/khoan thuong rieng; neu y nguoi hoi "
            "la 'tung nhan vien' thi phai liet ke theo nhan vien, khong goi nhan vien la ASO."
        ),
        "rule_count": 0 if v25_inactive_by_mechanism else len(rule_rows),
        "rules": [] if v25_inactive_by_mechanism else list(grouped.values()),
    }


def salary_data_quality(check_type: str, year_month: str = None, scope_area_code: str = None,
                        scope_employee_code: str = None, scope_role: str = None) -> dict:
    """Doi chieu DM bonus, schema luong co ban, hoac chat luong snapshot bang luong.

    Gom cac cau hoi audit luong thanh mot tool co dinh de model khong phai do catalog/SQL qua nhieu
    vong. Nhanh dm_reconciliation chi doc snapshot da dong bo va fail-closed theo doi QLV.
    """
    check = str(check_type or "").strip().lower()
    if check not in {"dm_reconciliation", "base_salary_schema", "snapshot_quality"}:
        raise ValueError(
            "check_type chi nhan dm_reconciliation, base_salary_schema hoac snapshot_quality."
        )

    if check == "base_salary_schema":
        columns = _q_bravo("""
            SELECT c.name AS ColumnName, t.name AS DataType
            FROM sys.columns c
            JOIN sys.types t ON t.user_type_id=c.user_type_id
            WHERE c.object_id=OBJECT_ID('dbo.FACT_ThongKeTinhLuong')
              AND (c.name LIKE '%Luong%' OR c.name LIKE '%Salary%'
                   OR c.name LIKE '%Level%' OR c.name LIKE '%LCB%')
            ORDER BY c.column_id
        """)
        normalized = {
            "".join(ch for ch in str(row.get("ColumnName") or "").lower() if ch.isalnum())
            for row in columns
        }
        base_salary_names = {"lcb", "luongcoban", "basesalary", "basicsalary"}
        has_base_salary = bool(normalized & base_salary_names)
        return {
            "status": "ok",
            "table": "dbo.FACT_ThongKeTinhLuong",
            "has_base_salary_amount": has_base_salary,
            "has_level_to_base_salary_mapping": False,
            "candidate_columns": columns,
            "conclusion": (
                "Du du lieu luong co ban de tinh tong thu nhap."
                if has_base_salary else
                "Chua co cot so tien luong co ban va chua co mapping Level -> LCB; khong du co so "
                "goi thuong + phu cap la tong luong/tong thu nhap."
            ),
        }

    scope_clauses = []
    scope_params: list = []
    if scope_area_code:
        scope_clauses.append("area_code=?")
        scope_params.append(scope_area_code)
    if scope_employee_code:
        scope_clauses.append("(employee_code=? OR manager_code=?)")
        scope_params.extend([scope_employee_code, scope_employee_code])
    scope_sql = "" if not scope_clauses else " AND " + " AND ".join(scope_clauses)

    date_cond, date_params = _closed_salary_date_filter("", year_month)
    date_rows = _q(
        f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE 1=1 {date_cond} "
        f"AND v25_percent IS NOT NULL{scope_sql}",
        tuple(date_params) + tuple(scope_params),
    )
    snapshot_date = date_rows[0]["d"] if date_rows and date_rows[0].get("d") else None
    if not snapshot_date:
        return {"status": "no_data", "note": "Chua co snapshot luong cuoi ky da chot."}

    if check == "snapshot_quality":
        rows = _q(
            "SELECT save_date,COUNT(*) employees,"
            "SUM(CASE WHEN v25_percent IS NULL THEN 1 ELSE 0 END) missing_v25_percent,"
            "SUM(CASE WHEN month_sale_target IS NULL OR month_sale_target<=0 THEN 1 ELSE 0 END) "
            "missing_target FROM fact_thongketinhluong WHERE save_date>=date(?,'-2 months')"
            f"{scope_sql} GROUP BY save_date ORDER BY save_date",
            tuple([snapshot_date] + scope_params),
        )
        return {
            "status": "ok", "latest_closed_snapshot": snapshot_date, "snapshots": rows,
            "note": "Chi snapshot cuoi thang moi duoc coi la ky luong da chot.",
        }

    formula = (
        "expected_dm_bonus = (DM1Amount*DM1Percent + DM2Amount*DM2Percent + "
        "DM3Amount*DM3Percent) * TotalPoint"
    )
    expression = (
        "(COALESCE(dm1_amount,0)*COALESCE(dm1_percent,0)+"
        "COALESCE(dm2_amount,0)*COALESCE(dm2_percent,0)+"
        "COALESCE(dm3_amount,0)*COALESCE(dm3_percent,0))*COALESCE(total_point,0)"
    )
    summary = _q(
        "SELECT COUNT(*) employees,"
        "SUM(CASE WHEN dm_bonus>0 THEN 1 ELSE 0 END) employees_with_dm_bonus,"
        f"SUM(CASE WHEN ABS(COALESCE(dm_bonus,0)-{expression})>1 THEN 1 ELSE 0 END) mismatches,"
        f"MAX(ABS(COALESCE(dm_bonus,0)-{expression})) max_abs_delta "
        "FROM fact_thongketinhluong WHERE save_date=?" + scope_sql,
        tuple([snapshot_date] + scope_params),
    )[0]
    mismatches = _q(
        "SELECT employee_code,employee_name,area_code,position_code,dm_bonus,total_point,"
        f"{expression} expected_dm_bonus FROM fact_thongketinhluong "
        f"WHERE save_date=?{scope_sql} AND ABS(COALESCE(dm_bonus,0)-{expression})>1 "
        "ORDER BY ABS(COALESCE(dm_bonus,0)-" + expression + ") DESC LIMIT 50",
        tuple([snapshot_date] + scope_params),
    )
    return {
        "status": "ok",
        "snapshot_date": snapshot_date,
        "formula": formula,
        "tolerance_vnd": 1,
        "employees": int(summary.get("employees") or 0),
        "employees_with_dm_bonus": int(summary.get("employees_with_dm_bonus") or 0),
        "mismatch_count": int(summary.get("mismatches") or 0),
        "max_abs_delta": _f(summary.get("max_abs_delta")),
        "mismatches": mismatches,
    }


def _closed_salary_date_filter(alias: str, value: str = None) -> tuple[str, tuple]:
    """Chi chon snapshot CUOI THANG; dong giua thang la tien do, khong phai luong da chot."""
    prefix = f"{alias}." if alias else ""
    clause = (f" AND {prefix}save_date="
              f"date({prefix}save_date,'start of month','+1 month','-1 day')")
    if not value:
        return clause, ()
    raw = str(value).strip()
    if len(raw) == 7:
        return clause + f" AND substr({prefix}save_date,1,7)=?", (raw,)
    cutoff = str(_parse_report_date(raw, "save_date"))
    return clause + f" AND {prefix}save_date<=?", (cutoff,)


def salary_achievement_summary(save_date: str = None, scope_area_code: str = None,
                               scope_employee_code: str = None, scope_role: str = None) -> dict:
    """Tong hop so luong nhan vien dat cac moc thuong tien do (V15, V22, V25) va ASO.
    Tra ve so luong dat dieu kien va ty le % tren tong so nhan vien thuoc pham vi.
    Phan quyen: scope_employee_code gioi han ve doi cua QLV.

    Quy tac 27/08/2026: CS (Cho si) va TK (kenh MT) dung is_ac/Active Customer, khong co ASO.
    Vi vay ASO chi dem tren cac vi tri khac CS/TK; khong de mot dong ASO bi gan nham cho
    nguoi da co co is_ac.

    19/08/2026: SUA loi dinh dang ma - truoc day dung _employee_scope_clause() (qua
    _get_team_dms_ids(), tra ve DMSId dung de loc BANG HOA DON vhoadon_otc/etc), nhung
    fact_thongketinhluong.employee_code duoc dong bo tu CHINH EmployeeCode tho cua Bravo (xem
    sync_warehouse.py::sync_fact_thongketinhluong - SELECT EmployeeCode, khong phai EmpDMSCode),
    KHAC dinh dang voi DMSId (vd EmployeeCode='DNH00832' nhung DMSId='HYE_02' - da tai lieu hoa o
    employee_daily_kpi()). Loc DMSId len cot EmployeeCode khien QLV LUON nhan 'khong co du lieu'
    du doi minh co du lieu that. Loc TRUC TIEP tren manager_code cua CHINH bang nay - cung dinh
    dang voi employee_code trong CUNG 1 bang, khong con nguy co lech nguon/dinh dang."""
    if scope_employee_code:
        emp_sql = " AND (f.employee_code=? OR f.manager_code=?)"
        emp_params = (scope_employee_code, scope_employee_code)
    else:
        emp_sql, emp_params = "", ()
    area_sql = " AND f.area_code=?" if scope_area_code else ""
    area_params = (scope_area_code,) if scope_area_code else ()
    
    cond_sql = emp_sql + area_sql
    cond_params = emp_params + area_params
    
    date_cond, date_param = _closed_salary_date_filter("f", save_date)

    fdate_r = _q(f"SELECT MAX(f.save_date) d FROM fact_thongketinhluong f WHERE 1=1 {cond_sql}{date_cond} AND f.v25_percent IS NOT NULL", cond_params + date_param)
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        fdate_r = _q(f"SELECT MAX(f.save_date) d FROM fact_thongketinhluong f WHERE 1=1 {cond_sql}{date_cond}", cond_params + date_param)
        fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return {"error": "Chua co snapshot thuong/luong CUOI KY da chot trong ky nay hoac trong pham vi cua ban."}
        
    sql = f"""SELECT 
        COUNT(f.employee_code) as total_emp,
        SUM(CASE WHEN f.v15_bonus > 0 THEN 1 ELSE 0 END) as v15_achieved,
        SUM(CASE WHEN f.v22_bonus > 0 THEN 1 ELSE 0 END) as v22_achieved,
        SUM(CASE WHEN f.v25_bonus > 0 THEN 1 ELSE 0 END) as v25_achieved,
        SUM(CASE WHEN f.aso_bonus > 0
                      AND UPPER(COALESCE(f.position_code,'')) NOT IN ('CS','TK')
                 THEN 1 ELSE 0 END) as aso_achieved,
        SUM(CASE WHEN UPPER(COALESCE(f.position_code,'')) IN ('CS','TK')
                 THEN 1 ELSE 0 END) as is_ac_position_count
        FROM fact_thongketinhluong f
        WHERE f.save_date=? {cond_sql}
        """
    row = _q(sql, (fdate,) + cond_params)
    if not row or row[0]["total_emp"] == 0:
        return {"error": "Khong co nhan vien nao trong pham vi quan ly co du lieu tinh luong."}
        
    r = row[0]
    total = r["total_emp"]
    return {
        "save_date": fdate,
        "snapshot_status": "closed_period",
        "total_employees": total,
        "v15_achieved_count": r["v15_achieved"],
        "v15_achieved_pct": round(r["v15_achieved"] / total * 100, 1) if total else 0,
        "v22_achieved_count": r["v22_achieved"],
        "v22_achieved_pct": round(r["v22_achieved"] / total * 100, 1) if total else 0,
        "v25_achieved_count": r["v25_achieved"],
        "v25_achieved_pct": round(r["v25_achieved"] / total * 100, 1) if total else 0,
        "aso_achieved_count": r["aso_achieved"],
        "aso_achieved_pct": round(r["aso_achieved"] / total * 100, 1) if total else 0,
        "is_ac_position_count": int(r["is_ac_position_count"] or 0),
        "note": (
            "So luong nhan vien dat cac moc thuong V15, V22, V25 va ASO tren tong so nhan vien "
            "(dua tren du lieu co phat sinh tien thuong > 0). ASO chi ap dung cho vi tri khac CS/TK; "
            "CS (Cho si) va TK (kenh MT) dung co is_ac/Active Customer, khong cong ASO."
        )
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

    QUY TAC CHI TIEU KHACH HANG 27/08/2026: CS (Cho si) va TK (kenh MT) dung co
    is_ac/Active Customer, KHONG co ASO. Neu nguon luong co ghi aso_* o mot dong CS/TK,
    van phai coi ASO la khong ap dung va khong cong vao total_bonus; chi tra ve chi so Active
    Customer cho hai vai tro nay. Cac vai tro con lai moi hien ASO khi nguon co du lieu.

    PHAN QUYEN: employee_code mac dinh la CHINH NGUOI DANG HOI (server ep qua scope_employee_code,
    xem _SELF_SCOPED_TEMPLATES) - AI KHONG duoc tu chon xem nguoi khac tru khi la C-Level/QLV xem
    doi minh (xem call_template). scope_role='c_level' moi duoc bo qua gioi han nay.

    save_date: ngay snapshot can xem (mac dinh: gan nhat hien co, thuong la cuoi thang/dot chot gan
    nhat - fact_thongketinhluong CHI co 1 snapshot/thang, khac fact_tonghopkhachhang nhieu dong/thang).

    employee_code (nhieu ma, 04-07/08/2026): toi uu chi phi AI - phat hien qua cost_log.jsonl: cau
    hoi "top 30 theo MB"/"V15/V22/V25/ASO top 30 nguoi" ton 7-8 VONG goi API/cau hoi, ~$0.6-1.2/cau
    vi AI phai goi lai tool nay LAP LAI tung nguoi 1 (moi vong gui lai TOAN BO lich su hoi thoai tich
    luy, khong cache duoc vi noi dung tool_result doi lien tuc) - xem ghi chu nl2sql.py. HO TRO nhieu
    ma cach nhau BANG DAU PHAY trong CUNG 1 chuoi (vd 'MBKV1,MBKV2,MBKV3') de tra ve ca danh sach
    trong 1 LAN GOI: tach chuoi, AP DUNG Y HET logic phan quyen/snapshot nhu duong 1-nguoi cho TUNG
    ma (khong noi long fail-closed vi goi hang loat) - tra ve {"employees": [{...KET QUA hoac
    "error", "requested_employee_code"}, ...]}. 1 nguoi loi (vd ngoai doi QLV) KHONG lam hong ca lo,
    chi ghi error rieng dong do kem ma da yeu cau - giu dung tinh than "1 loi khong duoc dung ca cau
    tra loi" da ghi trong mo ta tool, KHONG duoc im lang bo qua nguoi loi."""
    if employee_code and "," in employee_code:
        codes = [c.strip() for c in employee_code.split(",") if c.strip()]
        results = []
        for code in codes:
            one = _salary_detail_one(employee_code=code, save_date=save_date,
                                      scope_employee_code=scope_employee_code, scope_role=scope_role)
            # Ghi de/them "requested_employee_code" (KHONG dung "employee_code" de tranh de len ten
            # cot that tra ve khi thanh cong) de AI/nguoi doc luon biet dong nay ung voi ma nao da
            # yeu cau - ham con (_salary_detail_one) khong biet no dang bi goi hang loat nen khong tu
            # gan duoc. KHONG loc bo nguoi loi (khac ban truoc): AI/nguoi dung can biet AI bi thieu
            # va vi sao, im lang bo qua se gay hieu nham la nguoi do khong co du lieu.
            one["requested_employee_code"] = code
            results.append(one)
        # Ban chi tiet day du moi nguoi dai ~1.5-2K ky tu; 8 nguoi vuot tran payload 6K va bi cat
        # dung giua danh sach. Bulk chi giu cac truong can de lap bang thuong/phu cap; can xem KPI
        # thanh phan cua mot nguoi thi model goi rieng dung nguoi do o vong sau.
        compact, errors = [], []
        for one in results:
            if one.get("error"):
                error_row = {"requested_employee_code": one["requested_employee_code"],
                             "error": one["error"]}
                errors.append(error_row)
                compact.append(error_row)
                continue
            compact.append({
                "requested_employee_code": one["requested_employee_code"],
                "employee_code": one.get("employee_code"),
                "employee_name": one.get("employee_name"),
                "position_code": one.get("position_code"),
                "save_date": one.get("save_date"),
                "month_sale_percent": one.get("month_sale_percent"),
                "bonus_threshold_pct": one.get("bonus_threshold_pct"),
                "meets_bonus_threshold": one.get("meets_bonus_threshold"),
                "dm_bonus": one.get("dm_bonus"),
                "progress_bonus": one.get("progress_bonus"),
                "aso_bonus": one.get("aso_bonus"),
                "total_bonus": one.get("total_bonus"),
                "allowance": one.get("allowance"),
            })
        return {
            "requested_count": len(codes), "count": len(compact),
            "success_count": len(compact) - len(errors),
            "employees": compact, "errors": errors,
            "warning": ("CHUA GOM LUONG CO BAN (LCB): so lieu chi la Thuong kinh doanh + Phu cap. "
                        "Khong duoc noi nguoi bi thieu du lieu neu count=requested_count va errors rong."),
        }
    return _salary_detail_one(employee_code=employee_code, save_date=save_date,
                               scope_employee_code=scope_employee_code, scope_role=scope_role)


def _salary_detail_one(employee_code: str = None, save_date: str = None,
                        scope_employee_code: str = None, scope_role: str = None) -> dict:
    """Logic that cho DUNG 1 nhan vien - tach rieng tu salary_detail() de dung chung cho ca duong
    don-nguoi va duong hang loat (employee_code voi nhieu ma cach nhau dau phay, xem salary_detail)."""
    # 03/08/2026 (phat hien qua kiem thu QLV Bui Khac Dung hoi V15/V22/V25/ASO cho 4 TDV cua minh):
    # TRUOC DAY chi C-Level moi duoc xem nguoi khac - QLV hoi ve CHINH DOI CUA MINH bi tu choi chung
    # chung, khien AI (dung docstring cu "C-Level/QLV xem doi minh" nhung code khong lam dieu do) bao
    # sai "chua co du lieu". Sua: QLV duoc xem TDV NEU va CHI NEU nguoi do co manager_code=chinh QLV
    # (doi chieu qua fact_thongketinhluong.manager_code, KHONG tin employee_code AI truyen ma khong
    # kiem tra quan he quan ly - tranh QLV do doi nguoi ngoai doi).
    is_clevel = bool(scope_role and str(scope_role).lower() in ("c_level", "super_admin", "ceo", "cfo", "admin_ops", "admin"))
    is_manager_role = bool(scope_role and str(scope_role).lower() in ("qlv", "regional_director"))
    target_code = employee_code
    if not is_clevel:
        if not scope_employee_code:
            return {"error": "Khong xac dinh duoc ma nhan vien cua tai khoan nay de tra cuu thuong/luong."}
        if employee_code and employee_code != scope_employee_code:
            if not is_manager_role:
                # TDV/vai tro khac: KHONG duoc xem nguoi khac trong bat ky truong hop nao.
                target_code = scope_employee_code
            else:
                # QLV: kiem tra nguoi duoc hoi co THAT SU bao cao len minh khong (qua manager_code
                # trong CHINH fact_thongketinhluong - nguon du lieu nay dang dung, khong phai suy
                # luan tu bang khac de tranh lech dinh nghia "doi" giua 2 nguon).
                target_ident = _resolve_employee_identity(employee_code)
                target_lookup = target_ident["dmsid"] or employee_code
                mgr_check = _q(
                    "SELECT manager_code FROM fact_thongketinhluong "
                    "WHERE (employee_code=? OR employee_code=?) AND manager_code IS NOT NULL "
                    "ORDER BY save_date DESC LIMIT 1", (employee_code, target_lookup))
                qlv_ident = _resolve_employee_identity(scope_employee_code)
                qlv_lookup = qlv_ident["dmsid"] or scope_employee_code
                is_direct_report = bool(mgr_check and mgr_check[0]["manager_code"] in
                                         (scope_employee_code, qlv_lookup))
                if not is_direct_report:
                    return {"error": (
                        f"Ban khong co quyen xem thuong/luong cua '{employee_code}' - nguoi nay khong "
                        "thuoc doi cua ban (hoac he thong chua xac dinh duoc quan he quan ly). QLV chi "
                        "duoc xem TDV BAO CAO TRUC TIEP len chinh minh.")}
                target_code = employee_code
        else:
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
    date_cond, date_param = _closed_salary_date_filter("", save_date)

    fdate_r = _q(f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE {base_cond}{date_cond} "
                 f"AND v25_percent IS NOT NULL", base_params + date_param)
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        fdate_r = _q(f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE {base_cond}{date_cond}",
                     base_params + date_param)
        fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return {"error": f"Chua co snapshot thuong/luong CUOI KY da chot cho nhan vien '{target_code}' "
                          "trong ky duoc hoi (hoac ma nhan vien khong dung)."}

    row = _q("SELECT * FROM fact_thongketinhluong WHERE (employee_code=? OR employee_code=?) "
             "AND save_date=? LIMIT 1", (target_code, lookup_code, fdate))
    if not row:
        return {"error": f"Chua co du lieu thuong/luong cho nhan vien '{target_code}' tai ky {fdate}."}
    r = row[0]

    dm_bonus = _f(r["dm_bonus"])
    position_code = str(r["position_code"] or "").strip().upper()
    uses_is_ac = _uses_is_ac(position_code)
    raw_aso_bonus = _f(r["aso_bonus"])
    # CS/TK khong co ASO theo nghiep vu. Tra None thay vi 0 de UI/model khong nham
    # day la mot khoan ASO that; total_bonus loai khoan nay ra hoan toan.
    aso_bonus = None if uses_is_ac else raw_aso_bonus
    v15_bonus = _f(r["v15_bonus"])
    v22_bonus = _f(r["v22_bonus"])
    v25_bonus = _f(r["v25_bonus"])
    allowance = _f(r["lunch_amount"]) + _f(r["transport_amount"]) + _f(r["phone_amount"])
    total_bonus = dm_bonus + (0.0 if uses_is_ac else raw_aso_bonus) + v15_bonus + v22_bonus + v25_bonus

    active_customer = {
        "quantity": _f(r["active_cus_quantity"]),
        "target": _f(r["active_cus_target"]),
        "percent": _f(r["active_cus_percent"]),
    }
    aso_indicator = {
        "quantity": _f(r["aso_quantity"]),
        "target": _f(r["active_cus_target"]),
        "percent": _f(r["aso_percent"]),
        "bonus": raw_aso_bonus,
    }

    threshold = _bonus_threshold(r["position_code"])
    pct = _f(r["month_sale_percent"]) * 100
    return {
        "employee_code": r["employee_code"], "employee_name": r["employee_name"],
        "position_code": r["position_code"], "area_code": r["area_code"], "save_date": fdate,
        "snapshot_status": "closed_period",
        "customer_activity_metric": "is_ac" if uses_is_ac else "aso",
        "is_ac_applicable": uses_is_ac,
        "aso_applicable": not uses_is_ac,
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
            # Chi mot trong hai chi so duoc ap dung theo vai tro: CS/TK -> Active Customer;
            # cac vai tro khac -> ASO. De None o nhanh khong ap dung de tranh hien thi nham ca hai.
            "active_customer": active_customer if uses_is_ac else None,
            "aso": aso_indicator if not uses_is_ac else None,
        },
        "business_rule_note": (
            "CS (Cho si) va TK (kenh MT) dung co is_ac/Active Customer; ASO khong ap dung."
            if uses_is_ac else
            "ASO la chi tieu/khoan thuong cua vai tro nay; neu co is_ac trong du lieu khach hang "
            "thi khong duoc cong dong do vao ASO."
        ),
        "warning": ("CHUA GOM LUONG CO BAN (LCB): so lieu nay CHI la Thuong kinh doanh + Phu cap, KHONG "
                    "PHAI tong thu nhap day du. LCB tinh theo Level (dua tren Target thang) hien CHUA co "
                    "trong du lieu dong bo - can bao nguoi dung lien he ke toan/HR de biet LCB chinh xac."),
    }


def salary_ranking(year_month: str = None, area_code: str = None, position_code: str = None,
                   bonus_type: str = "total", limit: int = 30,
                   scope_area_code: str = None, scope_role: str = None,
                   scope_employee_code: str = None) -> dict:
    """Xep hang TOP N nhan vien co THUONG CAO NHAT (hoac thuong V15, V22, V25, ASO, Thuong danh muc DM)
    trong ky/thang.

    Quy tac 27/08/2026: CS (Cho si) va TK (kenh MT) dung is_ac/Active Customer, khong co ASO.
    Khi xep tong thuong, ASO bi loai khoi hai vi tri nay; khi xep rieng ASO, hai vi tri nay
    bi loai khoi tap xep hang va truy van rieng CS/TK tra ve ``not_applicable``.

    year_month: Thang can xem (YYYY-MM hoac YYYY-MM-DD, mac dinh: snapshot gan nhat da chot luong).
    area_code: Loc theo vung MB/MT/MN (mac dinh: toan cong ty).
    position_code: Loc theo chuc danh TDV/QLV/TP/CS/TK (mac dinh: tat ca).
    bonus_type: 'total' (Tong thuong KD), 'v15', 'v22', 'v25', 'aso', 'dm' (Thuong danh muc DM1+DM2+DM3).
    limit: So luong nhan vien tra ve trong bang xep hang (mac dinh 30, toi da 100).
    scope_area_code: Ep gioi han vung theo phan quyen tai khoan.

    19/08/2026: THEM scope_employee_code - truoc do ham nay khong nhan tham so nay nen KHONG nam
    trong _EMPLOYEE_SCOPED_TEMPLATES, khien call_template() FAIL-CLOSED tu choi MOI lan tai khoan
    QLV goi ham nay (xem ghi chu "Fail-closed" trong call_template), ke ca khi hoi ve chinh doi
    minh - trong khi salary_detail()/employee_kpi() (cung domain, cung nguy co lo hieu suat ca nhan
    dong nghiep) da ho tro dung. Loc TRUC TIEP tren manager_code cua CHINH fact_thongketinhluong
    (KHONG dung _team_of_qlv() - ham do truy van fact_tonghopkhachhang, KHAC bang/snapshot voi bang
    luong nay, co the lech doi neu 2 nguon dong bo lech nhau) - giu QLV + cac TDV bao cao truc tiep
    len ho TAI DUNG snapshot dang xep hang.
    """
    if scope_area_code:
        area_code = scope_area_code
    if position_code:
        position_code = str(position_code).strip().upper()

    limit = min(max(int(limit or 30), 1), 100)

    date_cond, date_params = _closed_salary_date_filter("", year_month)

    fdate_r = _q(f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE 1=1 {date_cond} "
                 f"AND v25_percent IS NOT NULL", date_params)
    fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        fdate_r = _q(f"SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE 1=1 {date_cond}",
                     date_params)
        fdate = fdate_r[0]["d"] if fdate_r else None
    if not fdate:
        return {"error": "Chua co snapshot thong ke tinh luong CUOI KY da chot cho ky nay."}

    aso_component = (
        "CASE WHEN UPPER(COALESCE(position_code,'')) IN ('CS','TK') THEN 0 "
        "ELSE COALESCE(aso_bonus,0) END"
    )
    order_col = f"(COALESCE(dm_bonus,0) + COALESCE(v15_bonus,0) + COALESCE(v22_bonus,0) + COALESCE(v25_bonus,0) + {aso_component})"
    btype = str(bonus_type or "total").lower()
    if btype == "v15":
        order_col = "COALESCE(v15_bonus,0)"
    elif btype == "v22":
        order_col = "COALESCE(v22_bonus,0)"
    elif btype == "v25":
        order_col = "COALESCE(v25_bonus,0)"
    elif btype == "aso":
        normalized_position = str(position_code or "").strip().upper()
        if normalized_position in _IS_AC_POSITIONS:
            return {
                "bonus_type": btype,
                "position_code": normalized_position,
                "not_applicable": True,
                "count": 0,
                "ranking": [],
                "warning": (
                    "ASO khong ap dung cho CS (Cho si) va TK (kenh MT); hai vai tro nay dung "
                    "co is_ac/Active Customer."
                ),
            }
        order_col = aso_component
    elif btype in ("dm", "danh_muc"):
        order_col = "COALESCE(dm_bonus,0)"

    # TRONGTDV* la ma vi tri trong/vacant slot, khong phai mot con nguoi de dua vao bang
    # "thuong/phu cap tung nguoi" (vd TRONGTDV6 mang ten QLV Pham Van Thuan lam doi bi dem 9 thay
    # vi 8). Bao cao nhan su loai cac slot nay, khong anh huong bao cao doanh thu dia ban.
    where_clauses = ["save_date = ?", "employee_code NOT LIKE 'TRONGTDV%'"]
    params = [fdate]

    if area_code:
        where_clauses.append("area_code = ?")
        params.append(area_code)

    if position_code:
        where_clauses.append("position_code = ?")
        params.append(position_code)
    elif btype == "aso":
        # Khong de cac dong CS/TK (khong co ASO) chen vao bang xep hang ASO voi gia tri 0.
        where_clauses.append("UPPER(COALESCE(position_code,'')) NOT IN ('CS','TK')")

    if scope_employee_code:
        where_clauses.append("(employee_code = ? OR manager_code = ?)")
        params.extend([scope_employee_code, scope_employee_code])

    where_sql = " WHERE " + " AND ".join(where_clauses)
    query_sql = f"""
        SELECT employee_code, employee_name, area_code, position_code, save_date,
               month_sale_amount, month_sale_target, month_sale_percent,
               dm_bonus, v15_bonus, v22_bonus, v25_bonus, aso_bonus,
               active_cus_quantity, active_cus_target, active_cus_percent,
               aso_quantity, aso_percent,
               (COALESCE(lunch_amount,0) + COALESCE(transport_amount,0) + COALESCE(phone_amount,0)) allowance,
               (COALESCE(dm_bonus,0) + COALESCE(v15_bonus,0) + COALESCE(v22_bonus,0) + COALESCE(v25_bonus,0) + {aso_component}) total_bonus
        FROM fact_thongketinhluong
        {where_sql}
        ORDER BY {order_col} DESC
        LIMIT ?
    """
    params.append(limit)
    rows = _q(query_sql, params)

    # Lay ky chot lien truoc cho dung y "thay doi". Chi truy van cac ma DA qua loc phan quyen o
    # ky hien tai; khong mo rong lai tap nhan vien tu ky cu.
    previous_date_row = _q(
        "SELECT MAX(save_date) d FROM fact_thongketinhluong "
        "WHERE save_date<? AND save_date=date(save_date,'start of month','+1 month','-1 day')",
        (fdate,),
    )
    previous_date = previous_date_row[0]["d"] if previous_date_row else None
    previous_by_employee = {}
    current_codes = [r["employee_code"] for r in rows if r.get("employee_code")]
    if previous_date and current_codes:
        placeholders = ",".join(["?"] * len(current_codes))
        previous_rows = _q(
            "SELECT employee_code,month_sale_percent,dm_bonus,v15_bonus,v22_bonus,v25_bonus,"
            "aso_bonus,position_code,"
            "(COALESCE(lunch_amount,0)+COALESCE(transport_amount,0)+COALESCE(phone_amount,0)) allowance "
            f"FROM fact_thongketinhluong WHERE save_date=? AND employee_code IN ({placeholders})",
            (previous_date, *current_codes),
        )
        for old in previous_rows:
            old_uses_is_ac = _uses_is_ac(old.get("position_code"))
            old["total_bonus"] = (
                _f(old.get("dm_bonus")) + _f(old.get("v15_bonus")) + _f(old.get("v22_bonus"))
                + _f(old.get("v25_bonus"))
                + (0.0 if old_uses_is_ac else _f(old.get("aso_bonus")))
            )
            previous_by_employee[old["employee_code"]] = old

    ranking = []
    for idx, r in enumerate(rows, 1):
        pct = _f(r["month_sale_percent"]) * 100
        threshold = _bonus_threshold(r["position_code"])
        uses_is_ac = _uses_is_ac(r["position_code"])
        raw_aso_bonus = _f(r["aso_bonus"])
        previous = previous_by_employee.get(r["employee_code"])
        total_bonus = _f(r["total_bonus"])
        allowance = _f(r["allowance"])
        previous_total_bonus = _f(previous.get("total_bonus")) if previous else None
        previous_allowance = _f(previous.get("allowance")) if previous else None
        previous_pct = (_f(previous.get("month_sale_percent")) * 100 if previous else None)
        ranking.append({
            "rank": idx,
            "employee_code": r["employee_code"],
            "employee_name": r["employee_name"],
            "area_code": r["area_code"],
            "position_code": r["position_code"],
            "month_sale_amount": _f(r["month_sale_amount"]),
            "month_sale_target": _f(r["month_sale_target"]),
            "month_sale_percent": round(pct, 1),
            "meets_bonus_threshold": pct >= threshold,
            "dm_bonus": _f(r["dm_bonus"]),
            "v15_bonus": _f(r["v15_bonus"]),
            "v22_bonus": _f(r["v22_bonus"]),
            "v25_bonus": _f(r["v25_bonus"]),
            "aso_bonus": None if uses_is_ac else raw_aso_bonus,
            "allowance": allowance,
            "total_bonus": total_bonus,
            "previous_save_date": previous_date if previous else None,
            "previous_month_sale_percent": round(previous_pct, 1) if previous_pct is not None else None,
            "previous_total_bonus": previous_total_bonus,
            "previous_allowance": previous_allowance,
            "total_bonus_delta": (total_bonus - previous_total_bonus
                                  if previous_total_bonus is not None else None),
            "allowance_delta": (allowance - previous_allowance
                                if previous_allowance is not None else None),
        })

    return {
        "save_date": fdate,
        "previous_save_date": previous_date,
        "snapshot_status": "closed_period",
        "bonus_type": btype,
        "area_code": area_code or "Toàn công ty",
        "position_code": position_code or "Tất cả",
        "excluded_placeholder_employee_codes": "TRONGTDV%",
        "count": len(ranking),
        "ranking": ranking,
        "warning": "CHƯA GỒM LƯƠNG CƠ BẢN (LCB): Số liệu là Thưởng kinh doanh + Phụ cấp."
    }




# =============================================================================================
# 10/08/2026 - HAM NAY DANG BI TAT. Tool "get_kpi_forecast_model1" da duoc GO khoi TEMPLATE_TOOLS
# trong nl2sql.py nen model KHONG the goi. Giu lai ham de sua tiep sau demo 13/08.
#
# LOI CHET NGUOI (phai sua truoc tien):
#   0. CRASH 100% so lan goi, tu ngay duoc viet (309d2f2, 06/08). Doan qlv_forecasts truy van
#      "SELECT t.manager_code ... FROM dim_targetvungmien t" nhung bang do CHI CO 4 cot:
#      area_code, channel_code, amount, doc_date (local_warehouse.py:52; dong bo tu Bravo cung chi
#      keo 4 cot do - sync_warehouse.py::SMALL_TABLES). Cot manager_code CHUA TUNG ton tai.
#      Chay thu tren may 24 ngay 10/08: "OperationalError: no such column: t.manager_code".
#      => Chua tung co ai nhan duoc ket qua tu tool nay.
#
# SAU KHI HET CRASH, VAN CON 6 VAN DE - dung bat lai truoc khi xu ly het:
#   1. Nhan "(VUOT TARGET)" dan cung vao chuoi etc_vs_national_target -> ETC dat 60% van in ra
#      "60.0% (VUOT TARGET)". Phai tinh theo dieu kien.
#   2. Truong "note" la chuoi CO DINH ("ETC du kien vuot chi tieu 104.1%. OTC dat ~85.0%") nen no
#      MAU THUAN voi chinh cac so vua tinh trong cung mot phan hoi. Phai sinh tu gia tri that.
#   3. BIA SO khi thieu du lieu - 4 cho: thieu OTC -> 4,66 ty; thieu ETC -> 6,22 ty; thieu target ->
#      21.363.814.418; doi QLV khong co doanh so -> m_tgt*0.134/7.4 (bia doanh so TU CHI TIEU, khien
#      QLV ban 0 dong van hien du bao dep). Du lieu thieu PHAI bao loi, khong duoc doan.
#   4. BO QUA PHAN QUYEN: nhan scope_area_code/scope_employee_code nhung khong dung; qlv_forecasts
#      liet ke toi 10 QLV moi mien. Lai khong nam trong _PERSON_LEVEL_TEMPLATES lan
#      _EMPLOYEE_SCOPED_TEMPLATES nen tang code cung khong chan ho => tai khoan QLV se thay ten va
#      % cua QLV khac. Khi bat lai PHAI them vao ca 2 tap do VA thuc su loc trong than ham.
#   5. target_month la tham so TRANG TRI - moi cau SQL deu cung ngay '2026-08'. Hoi thang 9 tra so
#      thang 8 dan nhan thang 9.
#   6. (10/08 - DA XAC MINH, KHONG PHAI cau hoi cho DNH, la BUG THUAN) est_mb_target=19,5 ty va
#      target_etc_national=42,5 ty tuong la "so uoc tinh" nhung thuc ra du lieu THAT da co san trong
#      kho, code chi khong chiu doc:
#        - fact_kehoachtongetc thang 8/2026 SUM = 42,5 ty - KHOP CHINH XAC hang so hardcode. Dev cu
#          chup 1 lan roi dong cung, dung ra phai SELECT SUM(amount) FROM fact_kehoachtongetc WHERE
#          doc_date LIKE '<thang>%'.
#        - dim_targetvungmien da co dong area_code='MB' THAT (34,16 ty). Nghiem trong hon: cau SQL
#          o r_tgt_otc KHONG loc area_code, nen no DA CONG CA MB THAT vao target_otc_current roi -
#          the ma code van cong THEM est_mb_target=19,5 ty len tren => MB BI TINH TRUNG 2 LAN (1 lan
#          that + 1 lan doan). Hang so fallback 21.363.814.418 khop khit tong MN+MT that (8,19+5,67+
#          7,5=21,36 ty) - luc viet code MB chua co du lieu target nen dev doan tam, nay Bravo da co
#          du roi ma khong ai go phan doan di. Sua dung: loc area_code ro rang cho tung vung, BO HAN
#          est_mb_target.
#   7. Docstring goc noi "Tu dong tinh ty trong phan bo 6 ngay dau thang theo lich su" - khong dung,
#      thuc te la 2 hang so go tay (0.1341 / 0.1407).
# =============================================================================================
def forecast_model1(target_month: str = "2026-08", scope_area_code: str = None, scope_employee_code: str = None):
    """DANG BI TAT - xem khoi ghi chu ngay tren. Du bao ty le hoan thanh KPI/doanh thu theo Mo Hinh 1
    (Intra-Month Pattern). CANH BAO: ty trong 6 ngay dau thang la HANG SO GO TAY (0.1341/0.1407),
    KHONG phai tu tinh tu lich su nhu ten goi gay hieu nham."""
    return disabled_future_result()

    # Ma tinh cu chi con de audit; runtime dung tai chinh sach fail-closed o tren.
    import datetime as dt
    
    # 1. Tỷ trọng lịch sử 6 ngày đầu
    avg_otc_ratio = 0.1341  # 13.41%
    avg_etc_ratio = 0.1407  # 14.07%
    
    # 2. Thực tế 6 ngày đầu Tháng 8/2026
    r_otc = _q("SELECT SUM(amount9) a FROM vhoadon_otc WHERE doc_date >= '2026-08-01' AND doc_date <= '2026-08-06'")
    act_otc_6d = _f(r_otc[0]["a"]) if r_otc and r_otc[0]["a"] else 4660000000.0
    
    r_etc = _q("SELECT SUM(amount9) a FROM vhoadon_etc WHERE doc_date >= '2026-08-01' AND doc_date <= '2026-08-06'")
    act_etc_6d = _f(r_etc[0]["a"]) if r_etc and r_etc[0]["a"] else 6220000000.0
    
    # 3. Targets Tháng 8
    r_tgt_otc = _q("SELECT SUM(CAST(amount AS REAL)) a FROM dim_targetvungmien WHERE doc_date LIKE '2026-08%'")
    target_otc_current = _f(r_tgt_otc[0]["a"]) if r_tgt_otc and r_tgt_otc[0]["a"] else 21363814418.0
    
    target_etc_national = 42500000000.0  # 42.5 tỷ
    est_mb_target = 19500000000.0        # Ước tính MB target 19.5 tỷ
    est_national_otc_target = target_otc_current + est_mb_target  # ~40.86 tỷ
    
    # 4. Tính toán dự phóng Model 1
    proj_otc = act_otc_6d / avg_otc_ratio
    proj_etc = act_etc_6d / avg_etc_ratio
    
    pct_otc_current = (proj_otc / target_otc_current * 100) if target_otc_current else 0
    pct_otc_normalized = (proj_otc / est_national_otc_target * 100) if est_national_otc_target else 0
    pct_etc = (proj_etc / target_etc_national * 100) if target_etc_national else 0
    
    # QLV level forecasts if requested
    qlv_forecasts = []
    r_qlv = _q("SELECT t.manager_code, COALESCE(n.name, t.manager_code) name, t.area_code, SUM(CAST(t.amount AS REAL)) tgt FROM dim_targetvungmien t LEFT JOIN dim_nhanvien n ON t.manager_code=n.employee_code WHERE t.doc_date LIKE '2026-08%' GROUP BY t.manager_code")
    for q in r_qlv:
        m_code = q["manager_code"]
        m_name = q["name"]
        m_area = q["area_code"]
        m_tgt = _f(q["tgt"])
        # Query 6-day sales for this QLV team
        r_team = _q("SELECT SUM(o.amount9) a FROM vhoadon_otc o JOIN fact_tonghopkhachhang f ON o.customer_code=f.customer_code WHERE f.manager_code=? AND o.doc_date >= '2026-08-01' AND o.doc_date <= '2026-08-06'", (m_code,))
        t_6d = _f(r_team[0]["a"]) if r_team and r_team[0]["a"] else (m_tgt * 0.134 / 7.4)
        t_proj = t_6d / avg_otc_ratio
        t_pct = (t_proj / m_tgt * 100) if m_tgt else 0
        qlv_forecasts.append({
            "manager_code": m_code,
            "manager_name": m_name,
            "area_code": m_area,
            "actual_6days": round(t_6d, 0),
            "projected_month": round(t_proj, 0),
            "target": round(m_tgt, 0),
            "projected_pct": round(t_pct, 1)
        })

    return {
        "model_name": "Mô hình 1 - Trọng số Điểm rơi Phân bổ trong Tháng (Intra-Month Pattern)",
        "target_month": target_month,
        "historical_weight_days_1_to_6": {
            "otc": "13.4%",
            "etc": "14.1%"
        },
        "actuals_days_1_to_6": {
            "otc": round(act_otc_6d, 0),
            "etc": round(act_etc_6d, 0)
        },
        "projected_month_totals": {
            "otc_projected": round(proj_otc, 0),
            "etc_projected": round(proj_etc, 0)
        },
        "targets": {
            "otc_current_target_mn_mt": round(target_otc_current, 0),
            "otc_estimated_national_target": round(est_national_otc_target, 0),
            "etc_national_target": round(target_etc_national, 0)
        },
        "projected_completion_pct": {
            "otc_vs_current_mn_mt_target": f"{pct_otc_current:.1f}%",
            "otc_vs_normalized_national_target": f"{pct_otc_normalized:.1f}% (Chuẩn hóa đủ 3 miền)",
            "etc_vs_national_target": f"{pct_etc:.1f}% (VƯỢT TARGET)"
        },
        "qlv_forecasts": qlv_forecasts[:10],
        "note": "Mô hình 1 áp dụng điểm rơi 7-10 ngày cuối tháng (chiếm ~40-50% tổng tháng). ETC dự kiến vượt chỉ tiêu 104.1%. OTC đạt ~85.0% sau khi chuẩn hóa mẫu số Miền Bắc."
    }


TEMPLATES = {
    "get_revenue_by_channel": revenue_by_channel,
    "get_top_products": top_products,
    "get_top_customers": top_customers,
    "get_revenue_by_region": revenue_by_region,
    "get_revenue_ytd_cumulative": revenue_ytd_cumulative,
    "get_revenue_monthly_series": revenue_monthly_series,
    "get_customer_lifecycle_summary": customer_lifecycle_summary,
    "get_customers_silent": customers_silent,
    "get_customer_cohort_retention": customer_cohort_retention,
    "get_customer_movement": customer_movement,
    "get_kpi_gap_run_rate": kpi_gap_run_rate,
    "get_cross_sell_opportunities": cross_sell_opportunities,
    "get_customer_product_coverage": customer_product_coverage,
    "get_geography_monthly_performance": geography_monthly_performance,
    "get_workforce_productivity": workforce_productivity,
    "get_operational_data_quality": operational_data_quality,
    "get_employee_kpi": employee_kpi,
    "get_employee_daily_kpi": employee_daily_kpi,
    "compare_periods": compare_periods,
    "get_customer_detail": customer_detail,
    "get_employee_directory": employee_directory,
    "check_order_timing": order_timing_check,
    "get_inventory_by_region": inventory_by_region,
    "get_inventory_expiry_report": inventory_expiry_report,
    "get_qlv_change_history": qlv_change_history,
    "get_revenue_tree": revenue_tree,
    "get_kpi_ranking": kpi_ranking,
    "get_revenue_reconciliation": revenue_reconciliation_check,
    "get_receivables_overview": receivables_overview,
    "get_receivables_period_compare": receivables_period_compare,
    "get_receivables_history_dates": receivables_history_dates,
    "get_customer_revenue_debt_risk": customer_revenue_debt_risk,
    "get_audit_log": audit_log_summary,
    "get_promotion_effectiveness": promotion_effectiveness,
    "get_promotion_data_quality": promotion_data_quality,
    "get_salary_bonus_policy": salary_bonus_policy,
    "get_salary_data_quality": salary_data_quality,
    "get_salary_detail": salary_detail,
    "get_salary_achievement_summary": salary_achievement_summary,
    "get_salary_ranking": salary_ranking,
}

_SELF_SCOPED_TEMPLATES = {"get_audit_log"}

_ROLE_SCOPED_TEMPLATES = {
    "get_salary_detail", "get_salary_achievement_summary", "get_salary_ranking",
    "get_salary_bonus_policy", "get_salary_data_quality",
}

_AREA_EXEMPT_TEMPLATES = {
    "get_audit_log", "get_salary_detail", "get_salary_achievement_summary", "get_salary_ranking",
    "get_salary_bonus_policy", "get_salary_data_quality",
    # 21/08/2026: get_receivables_history_dates chi liet ke NGAY co du lieu (khong co so lieu cong
    # no nao), khong nhan tham so scope_area_code trong chu ky ham - PHAI o day neu khong call_template
    # se ep them tham so ma ham khong khai bao, gay TypeError.
    "get_receivables_history_dates",
}

_PERSON_LEVEL_TEMPLATES = {
    "get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
    "get_employee_daily_kpi", "check_order_timing",
    "get_revenue_by_channel", "get_revenue_by_region", "get_top_customers",
    "get_top_products", "compare_periods", "get_revenue_ytd_cumulative", "get_revenue_monthly_series",
    "get_customer_lifecycle_summary", "get_customers_silent",
    "get_customer_cohort_retention", "get_customer_movement", "get_kpi_gap_run_rate",
    "get_cross_sell_opportunities", "get_customer_product_coverage", "get_geography_monthly_performance",
    "get_workforce_productivity", "get_operational_data_quality",
    "get_promotion_effectiveness",
    "get_promotion_data_quality",
    "get_customer_revenue_debt_risk",
    # 19/08/2026: BO get_inventory_by_region/get_receivables_overview/get_qlv_change_history/
    # get_revenue_reconciliation KHOI day - phan loai SAI tu truoc: ca 4 tool nay KHONG co cot nao
    # gan voi TUNG NHAN VIEN ca nhan (ton kho theo vung/san pham, cong no theo khach hang/vung, lich
    # su QLV theo to/vung, doi soat doanh thu toan vung) - khong co du lieu hieu suat ca nhan nao can
    # bao ve giua cac dong nghiep. scope_area_code (da co san, dung dan) la CO CHE GIOI HAN DU cho ca
    # 4 tool. Nam trong day khien nhanh "scope_employee_code and name in _PERSON_LEVEL_TEMPLATES" tai
    # call_template() FAIL-CLOSED chan HOAN TOAN moi tai khoan QLV goi 4 tool nay (QLV luon co ca
    # scope_area_code LAN scope_employee_code cung luc, xem main.py) - vi ca 4 ham KHONG nhan tham so
    # scope_employee_code nen KHONG THE nam trong _EMPLOYEE_SCOPED_TEMPLATES, chi con duong fail-closed.
    # Xac nhan bang test: goi qua call_template() truoc sua bi chan, sau sua thanh cong VA
    # scope_area_code van duoc ap dung dung (khong mo khoa vung).
    # 19/08/2026: THEM get_salary_ranking - truoc do CHI 3 tool luong kia o day, ham nay dung
    # chung _ROLE_SCOPED_TEMPLATES/_AREA_EXEMPT_TEMPLATES voi 3 tool do (deu bo qua scope_area_code
    # de nhuong cho co che theo doi tinh hon), nhung thieu mat o day khien nhanh ep
    # scope_employee_code (hoac fail-closed neu chua ho tro) KHONG BAO GIO duoc kich hoat - QLV goi
    # duoc ham nay VA thay xep hang thuong ca nhan CUA CA CONG TY, khong bi chan o dau ca. Xem sua
    # cung dot: salary_ranking() them tham so scope_employee_code + loc that tren manager_code.
    "get_salary_detail", "get_salary_achievement_summary", "get_salary_bonus_policy",
    "get_salary_data_quality",
    "get_salary_ranking",
}

_EMPLOYEE_SCOPED_TEMPLATES = {
    "get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
    "get_employee_daily_kpi", "get_revenue_by_channel", "get_top_customers",
    "get_top_products", "get_revenue_by_region", "compare_periods", "get_revenue_ytd_cumulative",
    "get_revenue_monthly_series", "get_customer_lifecycle_summary", "get_customers_silent",
    "get_customer_cohort_retention", "get_customer_movement", "get_kpi_gap_run_rate",
    "get_cross_sell_opportunities", "get_customer_product_coverage", "get_geography_monthly_performance",
    "get_workforce_productivity", "get_operational_data_quality",
    "get_promotion_effectiveness",
    "get_promotion_data_quality",
    "get_customer_revenue_debt_risk",
    "get_salary_detail", "get_salary_achievement_summary", "get_salary_bonus_policy",
    "get_salary_data_quality",
    "get_salary_ranking",
    # 19/08/2026: THEM check_order_timing - tra ve tom tat theo tung nhan vien (nghi van "chay don
    # don KPI"), truoc day KHONG nam trong tap nay nen QLV bi fail-closed chan hoan toan (dung y
    # dinh, vi tool nay THAT SU nhay cam theo ca nhan) - gio da them scope_employee_code + loc dung
    # qua _employee_scope_clause() nen mo duoc, QLV chi thay tom tat cua doi minh.
    "check_order_timing",
}

_CHANNEL_SCOPE_POLICIES = {
    # Tool co tham so scope_channel va bat buoc duoc backend ghi de.
    **{name: "filter" for name in {
        "get_revenue_by_channel", "get_top_products", "get_top_customers",
        "compare_periods", "get_revenue_ytd_cumulative", "get_revenue_monthly_series",
        "get_customer_lifecycle_summary", "get_customers_silent", "get_customer_cohort_retention",
        "get_customer_movement", "get_kpi_gap_run_rate", "get_cross_sell_opportunities",
        "get_customer_product_coverage", "get_geography_monthly_performance",
        "get_workforce_productivity", "get_operational_data_quality", "get_customer_detail",
        "check_order_timing", "get_revenue_by_region", "get_promotion_effectiveness",
        "get_promotion_data_quality", "get_customer_revenue_debt_risk",
        "get_receivables_overview", "get_receivables_period_compare", "get_employee_daily_kpi",
    }},
    # Cac tool nay hien chi co nguon OTC. Tai khoan OTC duoc dung; ETC bi chan de tranh tra sai kenh.
    **{name: "otc_only" for name in {
        "get_employee_kpi", "get_revenue_tree", "get_kpi_ranking", "get_revenue_reconciliation",
    }},
    # Du lieu luong chi duoc mo cho tai khoan QLV da co scope nhan vien; regional channel-only bi chan.
    **{name: "employee" for name in {
        "get_salary_bonus_policy", "get_salary_data_quality", "get_salary_detail",
        "get_salary_achievement_summary", "get_salary_ranking",
    }},
    # Chua co cot/quan he kenh du tin cay: fail-closed thay vi mac dinh xem toan cong ty.
    **{name: "blocked" for name in {
        "get_employee_directory", "get_inventory_by_region", "get_inventory_expiry_report",
        "get_qlv_change_history",
    }},
    # Metadata khong chua so lieu kinh doanh theo kenh, hoac da tu gioi han theo chinh nguoi dung.
    "get_receivables_history_dates": "exempt",
    "get_audit_log": "exempt",
}

if set(_CHANNEL_SCOPE_POLICIES) != set(TEMPLATES):
    missing = sorted(set(TEMPLATES) - set(_CHANNEL_SCOPE_POLICIES))
    extra = sorted(set(_CHANNEL_SCOPE_POLICIES) - set(TEMPLATES))
    raise RuntimeError(f"Channel scope policy incomplete; missing={missing}, extra={extra}")

_CHANNEL_SCOPED_TEMPLATES = {
    name for name, policy in _CHANNEL_SCOPE_POLICIES.items() if policy == "filter"
}
_SALARY_SENSITIVE_TEMPLATES = {
    name for name, policy in _CHANNEL_SCOPE_POLICIES.items() if policy == "employee"
}


def template_available_for_channel(name: str, scope_channel: str = None,
                                   scope_employee_code: str = None) -> bool:
    """Fail-closed availability used by both tool advertisement and execution."""
    if name not in TEMPLATES or not scope_channel:
        return True
    channel = str(scope_channel).strip().upper()
    if channel not in {"OTC", "ETC"}:
        return False
    policy = _CHANNEL_SCOPE_POLICIES[name]
    if policy in {"filter", "exempt"}:
        return True
    if policy == "otc_only":
        return channel == "OTC"
    if policy == "employee":
        return bool(scope_employee_code)
    return False


_SINGLE_PERIOD_TEMPLATES = {
    "get_revenue_by_channel", "get_revenue_by_region", "get_top_products",
    "get_top_customers", "check_order_timing", "get_customer_detail",
}


def _is_today_only_question(question: str) -> bool:
    """Nhan dien ca hoi chi hoi rieng "hom nay", khong ghi de cac ca so sanh/luy ke."""
    q = " ".join((question or "").lower().split())
    if "hôm nay" not in q and "hom nay" not in q:
        return False
    return not any(marker in q for marker in (
        "đến hôm nay", "den hom nay", "so sánh", "so sanh", "hôm qua", "hom qua",
        "tuần", "tuan", "tháng", "thang", "quý", "quy", "năm", "nam ", "từ ", "tu ",
    ))


def _enforce_non_future_dates(name: str, call_args: dict, question: str) -> None:
    """Backend, khong phai model, la nguon su that cho moc ngay truy van du lieu."""
    today = dt.date.today()
    today_text = today.isoformat()

    # Cac cau kieu "Doanh thu hom nay bao nhieu?" phai dung ngay he thong ngay ca khi model bo qua
    # resolve_relative_date hoac tu suy luan nham ngay ke tiep.
    if name in _SINGLE_PERIOD_TEMPLATES and _is_today_only_question(question):
        call_args["date_from"] = today_text
        call_args["date_to"] = today_text

    for key in ("date_from", "date_to", "date_from_a", "date_to_a", "date_from_b", "date_to_b", "as_of_date"):
        value = call_args.get(key)
        if not isinstance(value, str) or len(value) < 10:
            continue
        try:
            requested = dt.date.fromisoformat(value[:10])
        except ValueError:
            continue
        if requested > today:
            raise ValueError(
                f"{key}={requested.isoformat()} nam sau ngay he thong {today_text}; "
                "chatbot khong duoc truy van du lieu tuong lai."
            )



def call_template(name: str, args: dict, question: str = "", username: str = None,
                   scope_area_code: str = None, scope_employee_code: str = None,
                   scope_channel: str = None, session_id: str = None,
                   scope_role: str = None) -> dict:
    """Goi 1 template theo ten, ghi audit log (giong format run_query de nhat quan truy vet).
    scope_area_code: EP TRUYEN tu server (khong phai tu tham so AI dua ra) khi tai khoan bi gioi han
    vung - ghi de bat ky gia tri nao AI cung cap trong args, dam bao AI KHONG the tu "mo khoa" vung
    khac bang cach truyen tham so la. KHONG truyen cho tool trong _AREA_EXEMPT_TEMPLATES (da gioi han
    bang co che khac, xem docstring set do). scope_employee_code duoc ep cho moi ham da dang ky trong
    _EMPLOYEE_SCOPED_TEMPLATES; ham chua ho tro se fail-closed, khong duoc truyen bua. scope_channel:
    CHI ap dung cho cac template lien quan doanh
    thu/khach hang (xem _CHANNEL_SCOPED_TEMPLATES) - EP GIOI HAN kenh (vd 'OTC'), doc lap voi 2 co
    che scope kia, ap dung duoc cho MOI role. session_id: 28/07/2026 - THEM de audit_log.jsonl noi
    duoc voi cost_log.jsonl trong get_audit_log (xem audit_log_summary) - thieu truong nay thi phep
    noi qua session_id luon rong, chi phi bao 0d cho MOI tai khoan (phat hien khi kiem thu lan dau)."""
    t0 = dt.datetime.now()
    entry = {"ts": t0.isoformat(), "username": username, "question": question,
             "sql": f"<template:{name}>({args})", "session_id": session_id}
    if name in DISABLED_FUTURE_TOOL_NAMES:
        entry["status"] = "disabled"
        entry["error"] = FUTURE_FORECAST_DISABLED_MESSAGE
        entry["duration_ms"] = 0
        _write_log(entry)
        return {
            "ok": False,
            "error": FUTURE_FORECAST_DISABLED_MESSAGE,
            "feature_disabled": True,
        }
    # 22/07/2026 (diem #5): mo "hop" canh bao rieng cho lan goi nay - tool goi _warn() trong luc chay
    # se duoc gom lai va dinh kem vao ket qua tra ve cho AI.
    token = _tool_warnings.set([])
    try:
        fn = TEMPLATES[name]
        call_args = dict(args)
        if scope_role is not None and scope_role not in {"c_level", "admin_ops", "regional_director", "qlv"}:
            entry["status"] = "blocked"
            entry["error"] = "Vai tro tai khoan khong hop le."
            _write_log(entry)
            return {"ok": False, "error": entry["error"]}
        if name in _SALARY_SENSITIVE_TEMPLATES:
            if scope_role == "regional_director":
                entry["status"] = "blocked"
                entry["error"] = "Bao cao luong ca nhan khong mo cho vai tro giam doc mien/kenh."
                _write_log(entry)
                return {"ok": False, "error": entry["error"]}
            if scope_role == "qlv" and not scope_employee_code:
                entry["status"] = "blocked"
                entry["error"] = "Tai khoan QLV thieu scope nhan vien nen khong the xem bao cao luong."
                _write_log(entry)
                return {"ok": False, "error": entry["error"]}
        if scope_channel and not template_available_for_channel(
            name, scope_channel, scope_employee_code
        ):
            entry["status"] = "blocked"
            entry["error"] = (
                f"Bao cao '{name}' chua co co che gioi han du lieu an toan cho kenh "
                f"{str(scope_channel).upper()}."
            )
            _write_log(entry)
            return {"ok": False, "error": entry["error"]}
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

        _enforce_non_future_dates(name, call_args, question)
        
        # 28/07/2026: Tu dong append " 23:59:59" vao bat ky tham so nao la date_to/date_to_a/date_to_b
        # (YYYY-MM-DD) truoc khi truyen cho SQL. Neu khong co phan nay, "BETWEEN date_from AND date_to"
        # trong SQLite se am tham LOAI BO hoan toan cac hoa don phat sinh TRONG ngay cuoi cung (date_to),
        # vi string '2026-07-31' duoc hieu ngam la '2026-07-31 00:00:00', tuc la nho hon moi hoa don
        # phat sinh luc '2026-07-31 08:00:00'. Day la nguyen nhan lech 6 ty tien doanh thu tung thay!
        for key in ["date_to", "date_to_a", "date_to_b"]:
            if key in call_args and isinstance(call_args[key], str) and len(call_args[key]) == 10:
                call_args[key] += " 23:59:59"

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
        if scope_channel and _CHANNEL_SCOPE_POLICIES[name] == "filter":
            call_args["scope_channel"] = scope_channel
        result = fn(**call_args)
        # Gan nhan pham vi NGAY TRONG payload cho model. Truoc day code da loc dung doi QLV nhung
        # payload chi con cac con so; model da goi 9,82 ty cua DOI thanh "toan vung MT" trong UAT.
        if isinstance(result, dict):
            result = dict(result)
            if scope_employee_code and name in _EMPLOYEE_SCOPED_TEMPLATES:
                result["pham_vi_du_lieu"] = {
                    "loai": "DOI_CUA_QLV",
                    "ma_qlv": scope_employee_code,
                    "canh_bao": ("Tat ca so lieu trong payload nay CHI cua doi QLV tren, KHONG PHAI "
                                 "toan vung/toan mien/toan cong ty. Bat buoc ghi ro 'doi' khi tra loi."),
                }
            elif scope_area_code:
                result["pham_vi_du_lieu"] = {
                    "loai": "VUNG_MIEN", "ma_vung": scope_area_code,
                    "canh_bao": "So lieu da gioi han theo vung, khong phai toan cong ty.",
                }
        entry["status"] = "ok"
        entry["duration_ms"] = int((dt.datetime.now() - t0).total_seconds() * 1000)
        _write_log(entry)
        payload = {"ok": True, "result": result}
        warnings = _tool_warnings.get() or []
        if warnings:
            payload["canh_bao"] = warnings
        return payload
    except KhongXacDinhDuocDoi as e:
        # KHONG boc them "Loi khi chay bao cao chuan" - day khong phai su co ky thuat ma la
        # THIEU DU LIEU PHAN CONG DOI. Thong diep da viet san cho nguoi dung, giu nguyen van.
        entry["status"] = "no_team"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": str(e)}
    except Exception as e:
        entry["status"] = "error"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": f"Loi khi chay bao cao chuan '{name}': {str(e)[:300]}"}
    finally:
        _tool_warnings.reset(token)
