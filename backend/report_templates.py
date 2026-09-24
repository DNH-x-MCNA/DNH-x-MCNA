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
import re
import sqlite3
import unicodedata
from statistics import median
from sqlalchemy import text
from local_warehouse import get_conn, get_sync_meta
from customer_scope import TEAM_CUSTOMER_WINDOW_DAYS, team_customer_codes
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
_tool_user_warnings = contextvars.ContextVar("tool_user_warnings", default=None)


def _fold_question(value: str) -> str:
    """Chuan hoa cau hoi de cac guard UAT khong phu thuoc dau tieng Viet."""
    normalized = unicodedata.normalize("NFD", (value or "").lower())
    return " ".join("".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d").split())


def _warn(msg: str, *, code: str, severity: str, message: str):
    """Keep model guidance and a separately authored, user-facing message together.

    Only warning severity requires disclosure; info records valid source choices.
    Context-local buckets keep independent requests from sharing messages.
    """
    if severity not in {"warning", "info"}:
        raise ValueError(f"Unsupported tool warning severity: {severity}")
    bucket = _tool_warnings.get()
    if bucket is not None and msg not in bucket:
        bucket.append(msg)
    user_bucket = _tool_user_warnings.get()
    warning = {"code": code, "severity": severity, "message": message}
    if user_bucket is not None and warning not in user_bucket:
        user_bucket.append(warning)


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

# Hoa don TRUOC 01/01/2024 duoc nen thanh KH x thang trong monthly_customer_summary (khong con
# item_code/quantity/unit_price/stt tung dong) - xem sync_warehouse.py::DETAIL_HISTORY_START/
# _detail_cutoff_date(). Cac ham chi can TONG doanh thu/so hoa don (revenue_by_channel, top_customers,
# revenue_by_region, compare_periods qua revenue_by_channel) UNION them nguon nen nay khi khoang ngay
# duoc hoi vuot qua 12 thang gan nhat, de van ra dung so cho ca giai doan xa (vd "so voi cung ky nam
# ngoai"). Cac ham can CHI TIET tung dong (top_products: item_code; check_order_timing: stt/Amount9)
# KHONG the bu duoc bang nguon nen - xem canh bao rieng trong 2 ham do.

_DETAIL_CUTOFF_FALLBACK = "2024-01-01"
# Khoa cache theo DUONG DAN kho dang mo, khong phai mot o nho duy nhat: test doi DB_PATH sang kho
# tam cho tung ca, con may 24 co the tro sang ban sao khi doi chieu. Cache khong khoa se tra moc
# cua kho TRUOC do cho kho HIEN TAI - sai am tham va phu thuoc thu tu goi.
_DETAIL_CUTOFF_CACHE = {}
_DETAIL_CUTOFF_TTL = dt.timedelta(minutes=10)


def _detail_cutoff() -> str:
    """Ngay som nhat CON GIU hoa don chi tiet trong kho - doc TU CHINH KHO, khong tin hang so.

    23/09/2026 (UAT dnh_etc 15/09 14:53 "thuc hien, ke hoach doanh so cac thang"): truoc day ham
    nay tra ve cung hang so voi sync_warehouse.DETAIL_HISTORY_START (2024-01-01). Nhung kho tren
    dia duoc dung theo chinh sach CU (chi giu 12 thang chi tiet) nen chi tiet that su chi bat dau
    2025-09. Hai nguon vi the ho mat 20 thang lien tiep 2024-01 -> 2025-08: revenue_by_channel chi
    UNION monthly_customer_summary khi date_from < cutoff, ma cutoff lai la 2024-01-01, nen khoang
    do doc bang chi tiet - von rong - va tra ve DUNG 0 dong cho CA HAI kenh du monthly_customer_
    summary co du so. Do la kieu "0 dong" bia ra ma ca du an dang chong.

    Hang so chi khop du lieu sau khi da --full lai toan bo hoa don; truoc do khong ai bao loi.
    Lay ranh gioi THAT tu kho khien moi do lech giua chinh sach sync va du lieu tren dia tu lanh,
    khong phu thuoc vao viec co ai nho chay lai sync hay khong. Cache 10 phut vi ranh gioi chi doi
    sau mot dot sync lon.
    """
    import local_warehouse

    now = dt.datetime.now()
    khoa = str(local_warehouse.DB_PATH)
    cached = _DETAIL_CUTOFF_CACHE.get(khoa)
    if cached and now - cached[0] < _DETAIL_CUTOFF_TTL:
        return cached[1]
    moc = []
    for table in ("vhoadon_otc", "vhoadon_etc"):
        try:
            r = _q(f"SELECT MIN(doc_date) d FROM {table}")
        except Exception:
            continue
        # .get(): mot so ca test thay _q bang stub tra ve dong co khoa khac; moc cat khong duoc lam
        # vo ca tool chi vi khong doc duoc mot bang.
        if r and isinstance(r[0], dict) and r[0].get("d"):
            moc.append(str(r[0]["d"])[:10])
    # Khong co bang/khong co dong nao: giu hang so cu thay vi doan - kho rong thi moi cau tra loi
    # deu da bi chan o tang khac.
    # Lam tron ve NGAY DAU THANG: nguon nen la bang KH x THANG nen ranh gioi hai nguon chi co nghia
    # o muc thang. Neu giu nguyen ngay hoa don dau tien (vd 2025-09-03) thi cau hoi ca thang 09/2025
    # (tu 2025-09-01) bi coi la "ky da nen" du chi tiet phu tron thang.
    value = (min(moc)[:7] + "-01") if moc else _DETAIL_CUTOFF_FALLBACK
    _DETAIL_CUTOFF_CACHE[khoa] = (now, value)
    return value


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


# 23/09/2026 (v24 phat hien 1): dim_nhanvien co 6 gia tri dmsid ung voi HAI dong - DNH00601,
# DNH01250, va bon ma kieu TM23110109 / 'TM23110109.' (thua dau cham). LEFT JOIN thang bang nay vao
# bang hoa don theo dmsid lam NHAN BAN dong: moi dong hoa don cua nhung nguoi do bi dem hai lan.
# Do tren ky hien tai, kenh OTC: 99.294.041.118 -> 99.547.872.578, phong +253.831.460 (+0,256%) -
# khop den tung dong voi chenh lech giua scope_totals cua tool va SQL truc tiep.
# Checker S62 khu trung bang ROW_NUMBER uu tien dong KHONG bi danh co IsDuplicate; day lam giong het
# de hai ben cung mot dinh nghia thay vi moi ben mot kieu.
_NV_THEO_DMSID = (
    "(SELECT dmsid, employee_code FROM ("
    "SELECT dmsid, employee_code, ROW_NUMBER() OVER ("
    "PARTITION BY dmsid ORDER BY COALESCE(is_duplicate,0), employee_code) rn "
    "FROM dim_nhanvien WHERE dmsid IS NOT NULL AND TRIM(dmsid)<>''"
    ") WHERE rn=1)"
)


def _dms_theo_ma_nv(codes: list) -> dict:
    """employee_code -> DMSId (khoa noi sang hoa don). Dung chung cho doi QLV va phan ra M16."""
    if not codes:
        return {}
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
    return dms_by_employee


def _get_team_dms_ids(scope_employee_code: str, fdate: str = None, thong_tin: dict = None) -> list:
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
    va sang 13/08.

    `thong_tin`: dict tuy chon de ham GHI RA moc da thuc su dung ("moc_chot_doi", "nguon_chot_doi",
    "moc_sau_ky"). Tool nao muon dua thong tin nay vao payload thi truyen vao - xem
    promotion_effectiveness. _warn() mot minh la KHONG DU: no chi dinh canh bao vao ket qua tra cho
    model, ma model co the khong noi lai."""
    def _ghi(moc, nguon, sau_ky=False):
        if thong_tin is not None:
            thong_tin["moc_chot_doi"] = str(moc)[:10] if moc else None
            thong_tin["nguon_chot_doi"] = nguon
            thong_tin["moc_sau_ky"] = sau_ky

    team = _team_of_qlv(scope_employee_code, fdate)
    codes = [t["employee_code"] for t in team if t.get("employee_code")]
    if codes:
        _ghi((_roster_snapshot_dates(fdate) or [None])[-1] if fdate else None,
             "fact_tonghopkhachhang")
    if not codes and fdate:
        # 23/09/2026 (V34): TRUOC KHI nhay toi moc sau ky, thu bang snapshot luong - bang do giu 400
        # ngay thay vi 90, thuong van phu dung ky duoc hoi. Do tren du lieu that: chot doi dung ky
        # 12/2025 tra ve 14 khach/784.895.766d (khop checker), con nhay toi 30/06/2026 tra 11
        # khach/775.680.951d - lech vi 3 nguoi roi doi va 3 nguoi moi vao.
        team_luong, moc_luong = _team_of_qlv_tu_luong(scope_employee_code, fdate)
        codes = [t["employee_code"] for t in team_luong if t.get("employee_code")]
        if codes:
            team = team_luong
            _ghi(moc_luong, "fact_thongketinhluong")
            _warn(f"DOI CHOT TU SNAPSHOT LUONG: bang phan cong doi theo khach "
                  f"(fact_tonghopkhachhang) chi giu ~90 ngay nen khong phu ky den {fdate}; da chot "
                  f"doi bang fact_thongketinhluong tai moc {str(moc_luong)[:10]} - dung nguon va "
                  f"dung ky. So lieu hop le, khong can canh bao them voi nguoi dung.",
                  code="team_roster_salary_snapshot", severity="info",
                  message=(f"Đội của QLV {scope_employee_code} được xác định theo dữ liệu lương "
                           f"ngày {str(moc_luong)[:10]}, phù hợp với kỳ đến {fdate}."))
    if not codes and fdate:
        # 13/09/2026 (V34): ky duoc hoi co the nam TRUOC pham vi phan cong doi con giu trong kho
        # (fact_tonghopkhachhang chi giu ~90 ngay). Vi du that: tool khuyen mai lay moc phu CTKM
        # 09/01/2026 lam ngay chot doi -> khong co snapshot nao <= moc do -> MOI cau hoi khuyen mai
        # cua QLV deu hong cung. _employee_scope_clause() gap dung tinh huong nay thi canh bao roi
        # dung doi hien tai; o day phai xu ly giong nhau, khong duoc hong cung.
        som = _q("SELECT MIN(save_date) d FROM fact_tonghopkhachhang WHERE save_date>?", (fdate,))
        som_nhat = som[0]["d"] if som and som[0]["d"] else None
        if som_nhat:
            team = _team_of_qlv(scope_employee_code, som_nhat)
            codes = [t["employee_code"] for t in team if t.get("employee_code")]
            if codes:
                _ghi(som_nhat, "fact_tonghopkhachhang", sau_ky=True)
                _warn(f"DOI LICH SU KHONG CO SNAPSHOT: ky duoc hoi den {fdate} nam TRUOC pham vi phan "
                      f"cong doi con giu trong kho (som nhat {str(som_nhat)[:10]}). Dang dung thanh phan "
                      f"doi tai {str(som_nhat)[:10]}; thanh phan doi tai ky do co the khac - PHAI noi ro "
                      f"khi trinh bay, khong duoc khang dinh day la doi hinh cua chinh ky do.",
                      code="historical_team_roster_after_period", severity="warning",
                      message=(f"Chưa có dữ liệu đội của QLV {scope_employee_code} cho kỳ đến {fdate}. "
                               f"Báo cáo đang dùng đội ngày {str(som_nhat)[:10]}, sau kỳ được hỏi; "
                               "thành viên có thể khác nên số liệu chưa phản ánh đúng đội của kỳ đó."))
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
                    "khong phai doanh so toan mien.",
                    code="manager_own_transactions_only", severity="warning",
                    message=(f"QLV {scope_employee_code} chưa có TDV báo cáo trực tiếp trong dữ liệu. "
                             "Báo cáo chỉ gồm giao dịch của chính QLV, chưa đại diện cho doanh số toàn miền.")
                )
                return own_dms_ids
        raise KhongXacDinhDuocDoi(
            f"Khong xac dinh duoc doi cua quan ly vung '{scope_employee_code}': khong tim thay TDV "
            f"nao bao cao len ma nay trong FACT_TongHopKhachHang. KHONG the tra so doanh thu theo "
            f"doi. Bao voi nguoi dung rang du lieu phan cong doi cua ho chua co trong he thong, "
            f"can DNH kiem tra lai ManagerCode tren Bravo.")
    dms_by_employee = _dms_theo_ma_nv(codes)
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
              f"kho chua dong bo lai sau khi them cot dmsid - chay 'py sync_warehouse.py' de khac phuc.",
              code="team_revenue_partial_members", severity="warning",
              message=(f"Báo cáo của QLV {scope_employee_code} chỉ tính được {len(dms_ids)}/{len(codes)} TDV. "
                       f"Còn thiếu phần của {len(thieu)} người "
                       f"({', '.join(thieu[:8])}{'…' if len(thieu) > 8 else ''}) vì chưa nối được mã nhân viên "
                       "với hóa đơn; doanh thu, số đơn và số khách chưa đầy đủ cho cả đội."))
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
    # Khi snapshot khach hang da het han luu (~90 ngay), van phai truyen NGAY KY HOI
    # de _get_team_dms_ids thu snapshot luong (~400 ngay) truoc khi buoc dung doi sau ky.
    # Truyen None o day se am tham chot DOI HIEN TAI, lam sai moi tool dung scope nay.
    dms_ids = _get_team_dms_ids(scope_employee_code, team_snapshot or as_of)
    placeholders = ",".join(["?"] * len(dms_ids))
    return f" AND {alias}.employee_code IN ({placeholders})", tuple(dms_ids)


def _revenue_by_channel_raw(date_from: str, date_to: str, scope_area_code: str = None,
                            scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """Phep cong doanh thu theo khoang ngay, ke ca chung tu de ngay tuong lai.

    Chi dung noi bo de thong ke rieng phan chung tu de ngay sau hom nay. Doanh thu
    da phat sinh cho nguoi dung phai di qua revenue_by_channel().
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

    # date_from truoc moc con giu chi tiet -> phan xa hon da bi nen, cong them tu
    # monthly_customer_summary (xem _detail_cutoff: moc lay tu chinh kho, khong phai hang so).
    cutoff = _detail_cutoff()
    # Chi cong bang nen cho cac thang TRUOC HAN thang cua cutoff. Truoc day cat theo NGAY
    # (min(date_to, cutoff) roi lay [:7]) nen thang chua cutoff bi tinh o CA hai nguon khi thang do
    # vua co dong da nen vua co dong chi tiet - cong doi doanh thu dung mot thang giao nhau. Cach
    # cat theo thang nay da duoc dung san o customer_movement/_customer_monthly_activity.
    ym_from = date_from[:7]
    ym_to = min(date_to[:7], _month_add(cutoff[:7], -1)) if date_from < cutoff else None
    if ym_to and ym_from <= ym_to:
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

    coverage = _revenue_period_coverage(date_from, date_to)
    result = {
        "date_from": date_from, "date_to": date_to,
        "otc": {"revenue": otc_rev, "invoices": otc_hd},
        "etc": {"revenue": etc_rev, "invoices": etc_hd},
        "total": {"revenue": otc_rev + etc_rev, "invoices": otc_hd + etc_hd},
        "data_as_of": latest_data_date(),
        "data_coverage": coverage,
    }
    if not coverage["complete"]:
        result["coverage_warning"] = coverage["warning"]
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac KHONG duoc hien thi."
    return result


def revenue_by_channel(date_from: str, date_to: str, scope_area_code: str = None,
                       scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """Doanh thu da phat sinh den hom nay; chung tu de ngay sau do duoc neu rieng."""
    today = dt.date.today().isoformat()
    actual_to = min(date_to, today)
    result = _revenue_by_channel_raw(
        date_from, actual_to, scope_area_code, scope_channel, scope_employee_code,
    )
    result["date_to"] = date_to
    if actual_to < date_to:
        result["tinh_den_ngay"] = today
        future_from = max(date_from, (dt.date.today() + dt.timedelta(days=1)).isoformat())
        future = _revenue_by_channel_raw(
            future_from, date_to, scope_area_code, scope_channel, scope_employee_code,
        )
        if future["total"]["revenue"] or future["total"]["invoices"]:
            result["chung_tu_ngay_tuong_lai"] = {
                "tu_ngay": future_from, "den_ngay": date_to,
                "revenue": future["total"]["revenue"],
                "invoices": future["total"]["invoices"],
                "ghi_chu": ("Chung tu de ngay SAU hom nay, KHONG duoc cong vao doanh thu "
                            "da phat sinh."),
            }
        coverage = _revenue_period_coverage(date_from, date_to)
        result["data_coverage"] = coverage
        if not coverage["complete"]:
            result["coverage_warning"] = coverage["warning"]
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
                     SUM(CASE WHEN COALESCE(c.unit_price,0) > 0 THEN c.quantity ELSE 0 END) qty,
                     SUM(SUM(c.amount9)) OVER () scope_rev
              FROM combined c LEFT JOIN brv_sanpham sp ON sp.code = c.item_code
              GROUP BY c.item_code, sp.name ORDER BY rev DESC LIMIT ?"""
    params = tuple(p for pp in part_params for p in pp) + (limit,)
    rows = _q(sql, params)
    result = [{"item_code": r["item_code"], "name": r["name"] or f'(chua co ten - ma {r["item_code"]})',
               "revenue": _f(r["rev"]), "qty": _f(r["qty"]),
               "scope_revenue": _f(r["scope_rev"]),
               "share_pct_of_scope": (_f(r["rev"]) / _f(r["scope_rev"]) * 100
                                      if _f(r["scope_rev"]) else None)} for r in rows]
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
              SELECT customer_code, SUM(amount9) rev, SUM(SUM(amount9)) OVER () scope_rev
              FROM combined GROUP BY customer_code ORDER BY rev DESC LIMIT ?"""
    params = tuple(p for pp in part_params for p in pp) + (limit,)
    rows = _q(sql, params)
    return [{"customer_code": r["customer_code"], "revenue": _f(r["rev"]),
             "scope_revenue": _f(r["scope_rev"]),
             "share_pct_of_scope": (_f(r["rev"]) / _f(r["scope_rev"]) * 100
                                    if _f(r["scope_rev"]) else None)} for r in rows]


def _month_starts_between(date_from: str, date_to: str) -> list[str]:
    """Danh sach YYYY-MM nam trong mot khoang ngay, ke ca hai dau."""
    current = str(date_from)[:7]
    end = str(date_to)[:7]
    months = []
    while current <= end and len(months) < 24:
        months.append(current)
        current = _month_add(current, 1)
    return months


def _revenue_concentration_by_month(date_from: str, date_to: str, channel: str = "ALL",
                                    scope_area_code: str = None,
                                    scope_channel: str = None,
                                    scope_employee_code: str = None) -> dict:
    """S70/C11: cung mot tap thang, tinh top khach, top SKU va top mien de doc xu huong."""
    rows = []
    for month in _month_starts_between(date_from, date_to):
        month_from, month_to = _month_bounds(month)
        month_from = max(month_from, str(date_from)[:10])
        month_to = min(month_to, str(date_to)[:10])
        customers = top_customers(month_from, month_to, 10, channel,
                                  scope_area_code, scope_channel, scope_employee_code)
        products = top_products(month_from, month_to, 10, channel,
                                scope_area_code, scope_channel, scope_employee_code)
        if isinstance(products, dict):
            products = products.get("products", [])
        regions = revenue_by_region(month_from, month_to, scope_area_code, channel,
                                    scope_channel, scope_employee_code)
        scope_revenue = (_f(customers[0].get("scope_revenue")) if customers else
                         sum(_f(row.get("revenue")) for row in regions))
        top_customer_revenue = sum(_f(row.get("revenue")) for row in customers)
        top_product_revenue = sum(_f(row.get("revenue")) for row in products)
        top_regions = sorted(regions, key=lambda row: -_f(row.get("revenue")))[:3]
        top3_region_revenue = sum(_f(row.get("revenue")) for row in top_regions)
        top1_region_revenue = _f(top_regions[0].get("revenue")) if top_regions else 0.0
        rows.append({
            "month": month, "scope_revenue": scope_revenue,
            "top_10_customer_revenue": top_customer_revenue,
            "top_10_customer_share_pct": (top_customer_revenue / scope_revenue * 100
                                            if scope_revenue else None),
            "top_10_product_revenue": top_product_revenue,
            "top_10_product_share_pct": (top_product_revenue / scope_revenue * 100
                                           if scope_revenue else None),
            "top_3_region_revenue": top3_region_revenue,
            "top_3_region_share_pct": (top3_region_revenue / scope_revenue * 100
                                        if scope_revenue else None),
            "top_1_region": top_regions[0].get("area") if top_regions else None,
            "top_1_region_share_pct": (top1_region_revenue / scope_revenue * 100
                                        if scope_revenue else None),
        })
    return {
        "rows": rows,
        "trend_available": len(rows) >= 2,
        "top_3_region_interpretation": (
            "DNH chi co ba mien MB/MT/MN, nen top-3 mien thuong la toan bo va ty le xap xi 100%; "
            "dung top_1_region_share_pct de danh gia tap trung dia ly co y nghia hon."
        ),
        "detail_window_note": (
            "Top SKU chi tinh duoc trong cua so hoa don chi tiet gan nhat; thang cu hon khong con item_code."
        ),
    }


def _top_customer_changes_by_month(date_from: str, date_to: str, limit: int = 10,
                                   scope_area_code: str = None,
                                   scope_channel: str = None,
                                   scope_employee_code: str = None) -> dict:
    """S71/C32 va S20/M21/V19: top tang/giam cua TUNG thang, khong cat truoc khi tinh."""
    parts, params = [], []
    for table, channel, area_join in (
        ("vhoadon_otc", "OTC", _otc_area_join("v", scope_area_code)),
        ("vhoadon_etc", "ETC", _etc_area_join("v", scope_area_code)),
    ):
        if scope_channel and scope_channel.upper() != channel:
            continue
        scope_sql, scope_params = _scope_clause(scope_area_code)
        employee_sql, employee_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
        parts.append(
            f"SELECT substr(v.doc_date,1,7) month,v.customer_code,v.employee_code,"
            f"SUM(v.amount9) revenue FROM {table} v {area_join} "
            f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}{employee_sql} "
            "GROUP BY substr(v.doc_date,1,7),v.customer_code,v.employee_code"
        )
        params.extend((date_from, date_to) + scope_params + employee_params)
    if not parts:
        return {"rows": [], "months": [], "total_customer_month_rows": 0}
    raw = _q(" UNION ALL ".join(parts), tuple(params))
    by_customer_month = {}
    owner_revenue = {}
    totals = {}
    for row in raw:
        key = (str(row["month"]), row["customer_code"])
        revenue = _f(row["revenue"])
        by_customer_month[key] = by_customer_month.get(key, 0.0) + revenue
        totals[key[0]] = totals.get(key[0], 0.0) + revenue
        employee = row.get("employee_code")
        if employee:
            owner_key = (key[0], key[1], employee)
            owner_revenue[owner_key] = owner_revenue.get(owner_key, 0.0) + revenue
    owner_best = {}
    for (month, customer, employee), revenue in owner_revenue.items():
        key = (month, customer)
        best = owner_best.get(key)
        if best is None or revenue > best[0]:
            owner_best[key] = (revenue, employee)
    months = sorted(totals)
    customers = sorted({customer for _, customer in by_customer_month})
    result_rows = []
    for index, month in enumerate(months):
        if index == 0:
            continue
        previous_month = months[index - 1]
        total_delta = totals[month] - totals[previous_month]
        changes = []
        for customer in customers:
            current = by_customer_month.get((month, customer), 0.0)
            previous = by_customer_month.get((previous_month, customer), 0.0)
            delta = current - previous
            if not delta:
                continue
            owner = ((owner_best.get((month, customer)) or (None, None))[1]
                     or (owner_best.get((previous_month, customer)) or (None, None))[1])
            changes.append({
                "month": month, "previous_month": previous_month,
                "customer_code": customer, "customer_name": customer,
                "current_revenue": current, "previous_revenue": previous, "delta": delta,
                "direction": "TANG" if delta > 0 else "GIAM",
                "contribution_pct_of_total_change": (delta / abs(total_delta) * 100
                                                     if total_delta else None),
                "employee_dms_code": owner,
            })
        increases = sorted((row for row in changes if row["delta"] > 0),
                           key=lambda row: (-row["delta"], row["customer_code"]))[:limit]
        decreases = sorted((row for row in changes if row["delta"] < 0),
                           key=lambda row: (row["delta"], row["customer_code"]))[:limit]
        result_rows.append({
            "month": month, "previous_month": previous_month,
            "scope_revenue": totals[month], "scope_revenue_delta": total_delta,
            "top_increases": increases, "top_decreases": decreases,
        })
    returned_codes = sorted({
        row["customer_code"] for month_row in result_rows
        for direction in ("top_increases", "top_decreases") for row in month_row[direction]
    })
    names = _customer_names(returned_codes)
    for month_row in result_rows:
        for direction in ("top_increases", "top_decreases"):
            for row in month_row[direction]:
                row["customer_name"] = names.get(row["customer_code"]) or row["customer_code"]
    return {
        "months": months, "rows": result_rows,
        "total_customer_month_rows": len(by_customer_month),
        "definition": (
            "Moi thang giu toi da top tang va top giam rieng; contribution_pct_of_total_change "
            "dung delta cua toan bo pham vi lam mau so. Ma phu trach la nguoi co doanh thu lon nhat "
            "cua khach trong thang, hoac thang truoc neu khach da ve 0."
        ),
    }


def _channel_sub_buckets():
    """Cac ban ghi 'kenh ao' trong dim_nhanvien (QLV gia dung de gan doanh thu kenh dac biet, vd
    Modern Trade/Long Chau - Name bat dau bang 'Kênh', IsDuplicate=1) - KHONG phai QLV that, chi la
    cho gan doanh thu theo kenh ban hang. dmsid cua ban ghi nay khop voi vhoadon_otc.channel_code
    (tu EmpDMSCode2 tren Bravo, xem sync_warehouse.py) - CHI co o OTC, ETC khong co co che nay."""
    return _q("SELECT dmsid, name, area_code FROM dim_nhanvien "
              "WHERE position_code='QLV' AND is_duplicate=1 AND name LIKE 'Kênh%' AND dmsid IS NOT NULL")


def _special_channel_plan(bucket_name: str, area_code: str, date_from: str, date_to: str) -> tuple:
    """(ke hoach, ghi chu) cua kenh dac biet (vd 'Kênh MT') trong khoang ngay.

    15/09/2026 (UAT OTC-Only C-Level 14:20 "bo sung ke hoach va % thuc hien" thieu target kenh MT):
    DIM_TargetVungMien co dong ChannelCode='MT' (Modern Trade, mien Nam) - do tren kho 15/09 khop tuyet
    doi chi tieu dong MN1 'Kênh MT' cua FACT_ThongKeTinhLuong moi thang 2026 (T9: 6.653.790.357d). Chi
    tieu la theo THANG nen chi tinh khi khoang hoi tron thang."""
    if "kenh mt" not in _fold_question(bucket_name):
        return None, "Kenh nay chua co chi tieu rieng trong bang chi tieu vung."
    day_from, day_to = str(date_from)[:10], str(date_to)[:10]
    try:
        end = dt.date.fromisoformat(day_to)
        dt.date.fromisoformat(day_from)
    except ValueError:
        return None, "Khoang ngay khong hop le."
    if day_from[8:10] != "01" or end.day != _last_day_of_month(end.year, end.month):
        return None, "Khoang hoi khong tron thang; chi tieu kenh tinh theo thang nen khong tinh % thuc hien."
    try:
        rows = _q("SELECT SUM(COALESCE(amount,0)) amount, COUNT(*) n FROM dim_targetvungmien "
                  "WHERE channel_code='MT' AND area_code=? AND substr(doc_date,1,7) BETWEEN ? AND ?",
                  (area_code, day_from[:7], day_to[:7]))
    except sqlite3.OperationalError:
        return None, "Kho chua dong bo bang chi tieu vung."
    if not rows or not rows[0]["n"]:
        return None, "Khong co chi tieu kenh MT cho khoang nay."
    return _f(rows[0]["amount"]), None


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
                  f"breakdown nay nhu so lieu chac chan.",
                  code="regional_revenue_reconciliation_mismatch", severity="warning",
                  message=(f"Kỳ {date_from} đến {date_to}: tổng doanh thu theo vùng {total:,.0f} đồng "
                           f"lệch {abs(total - raw_total):,.0f} đồng so với tổng {raw_total:,.0f} đồng "
                           "trong cùng phạm vi. Phần chia theo vùng cần được đối chiếu lại."))
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
                    bucket_revenue = _f(r[0]["rev"])
                    # 15/09/2026: kem ke hoach kenh (DIM_TargetVungMien ChannelCode='MT') va % thuc hien.
                    plan, plan_note = _special_channel_plan(b["name"], b["area_code"], date_from, date_to)
                    entry = {"name": b["name"], "revenue": bucket_revenue, "plan_revenue": plan,
                             "achievement_pct": (bucket_revenue / plan * 100) if plan else None}
                    if plan_note:
                        entry["plan_note"] = plan_note
                    breakdown.append(entry)
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
# 14/09/2026 (dua ban sua tay may 24 vao repo): nhom/kenh gop MN1 'Kenh MT', MN4 'Cho si' cung mang
# is_duplicate=1 nhung KHONG duoc them vao danh sach tren - kpi_ranking/revenue_tree dung no de nhan
# dien la_nhom_kenh. employee_kpi chi mien loc 2 ma nay khi hoi RIENG QLV (bao cao that 14/09: "Mien
# Nam co 7 nhom/QLV nhung chi lay duoc chi tiet 5/7"); cau hoi moi vai tro/TDV giu nguyen de so dem
# nhan vien khong bi cong them 2 nhom kenh.
_KPI_CHANNEL_UNIT_CODES = ("MN1", "MN4")


def _not_duplicate_sql(alias: str = "nv", exempt_codes: tuple = None) -> str:
    """Manh SQL loc "khong bi danh dau trung lap", CO ngoai le cho _KNOWN_MISFLAGGED_DUPLICATE_CODES
    (hoac exempt_codes truyen rieng)."""
    codes = ",".join(f"'{c}'" for c in (exempt_codes or _KNOWN_MISFLAGGED_DUPLICATE_CODES))
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


def _kpi_thresholds_by_month(as_of_date: str, months_back: int = 3,
                             group_by: str = "area_position",
                             scope_area_code: str = None,
                             scope_employee_code: str = None) -> dict:
    """S30/S31: dem NGUOI co target theo cac moc, tren snapshot cuoi cua tung nguoi/thang."""
    month_to = str(as_of_date)[:7]
    months_back = max(1, min(int(months_back or 3), 12))
    month_from = _month_add(month_to, -(months_back - 1))
    sql = (
        "WITH snaps AS (SELECT employee_code,substr(save_date,1,7) month,MAX(save_date) d "
        "FROM fact_thongketinhluong WHERE substr(save_date,1,7) BETWEEN ? AND ? "
        "GROUP BY employee_code,substr(save_date,1,7)) "
        "SELECT substr(f.save_date,1,7) month,f.employee_code,f.position_code,f.area_code,"
        "f.manager_code,COALESCE(f.month_sale_amount,0) actual,f.month_sale_target target "
        "FROM fact_thongketinhluong f JOIN snaps s ON s.employee_code=f.employee_code "
        "AND s.month=substr(f.save_date,1,7) AND s.d=f.save_date "
        "WHERE f.month_sale_target>0"
    )
    params = [month_from, month_to]
    if scope_area_code:
        sql += " AND f.area_code=?"
        params.append(scope_area_code)
    if scope_employee_code:
        sql += " AND f.manager_code=?"
        params.append(scope_employee_code)
    if group_by == "manager":
        positions = sorted(_EMPLOYEE_TIER_POSITIONS)
        sql += f" AND UPPER(COALESCE(f.position_code,'')) IN ({','.join('?' for _ in positions)})"
        params.extend(positions)
    raw = _q(sql, tuple(params))
    buckets = {}
    for row in raw:
        position = str(row.get("position_code") or "UNKNOWN").upper()
        if group_by == "manager":
            group_code = row.get("manager_code") or "MISSING_MANAGER"
            key = (row["month"], group_code, None)
        else:
            group_code = row.get("area_code") or "UNKNOWN"
            key = (row["month"], group_code, position)
        bucket = buckets.setdefault(key, {
            "month": row["month"],
            "manager_code": group_code if group_by == "manager" else None,
            "area_code": group_code if group_by != "manager" else None,
            "position_code": position if group_by != "manager" else None,
            "employees_with_target": 0,
            "count_gate": 0, "count_80": 0, "count_100": 0, "count_120": 0,
        })
        actual, target = _f(row.get("actual")), _f(row.get("target"))
        pct = actual / target * 100 if target else None
        if pct is None:
            continue
        bucket["employees_with_target"] += 1
        gate = 65 if position == "TDV" else 70
        bucket["count_gate"] += int(pct >= gate)
        bucket["count_80"] += int(pct >= 80)
        bucket["count_100"] += int(pct >= 100)
        bucket["count_120"] += int(pct >= 120)
    rows = sorted(buckets.values(), key=lambda row: (
        row["month"], row.get("manager_code") or row.get("area_code") or "",
        row.get("position_code") or "",
    ))
    previous_gate_pct = {}
    rolling_gate_pct = {}
    for row in rows:
        total = row["employees_with_target"]
        for suffix in ("gate", "80", "100", "120"):
            row[f"pct_{suffix}"] = row[f"count_{suffix}"] / total * 100 if total else None
        series_key = row.get("manager_code") or f'{row.get("area_code")}:{row.get("position_code")}'
        history = rolling_gate_pct.setdefault(series_key, [])
        row["pct_gate_change_vs_previous_month"] = (
            row["pct_gate"] - previous_gate_pct[series_key]
            if series_key in previous_gate_pct and row["pct_gate"] is not None else None
        )
        if row["pct_gate"] is not None:
            history.append(row["pct_gate"])
            history[:] = history[-3:]
            previous_gate_pct[series_key] = row["pct_gate"]
        row["pct_gate_rolling_3_month_avg"] = (sum(history) / len(history) if history else None)
    return {
        "month_from": month_from, "month_to": month_to, "group_by": group_by,
        "channel_scope": "OTC",
        "rows": rows,
        "definition": (
            "Mau so chi gom nhan vien co target>0 tai snapshot cuoi cua CHINH nguoi do trong tung "
            "thang. Cong nhom hang la 65% voi TDV va 70% voi vai tro khac; 80%=dat KPI, "
            "100%=dat chi tieu, 120%=vuot 120%. Nguon KPI ca nhan hien chi phu OTC."
        ),
    }


def employee_kpi(as_of_date: str, limit: int = 10, order_by: str = "sales", filter: str = "all",
                  position_code: str = None, scope_area_code: str = None,
                  scope_employee_code: str = None, include_team_detail: bool = False,
                  kpi_source: str = "customer") -> dict:
    """KPI nhan vien: mac dinh tu fact_tonghopkhachhang; M20 dung KPI snapshot nhan su.
    include_team_detail: chi co tac dung khi position_code='QLV' - moi dong QLV co them team_detail
    (TDV/cap duoi truc tiep kem doanh so/target/%) trong cung mot lan goi.
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
    if kpi_source not in {"customer", "salary_kpi"}:
        raise ValueError("Nguon KPI khong hop le.")
    hoi_rieng_qlv = str(position_code or "").strip().upper() == "QLV"
    if kpi_source == "salary_kpi":
        # M20/S33: FACT_TongHopKhachHang chi co nguoi duoc gan khach. Snapshot nhan su Bravo
        # gom ca TDV chua co khach va ma bi gan IsDuplicate, nhung moi EmployeeCode chi tinh 1 lan.
        # Chi doc cac cot KPI; khong truy van hay tra ve cot tien luong/thuong ca nhan.
        if scope_employee_code or str(position_code or "").upper() != "TDV" or not scope_area_code:
            return {"error": "Nguon KPI M20 chi ho tro TDV trong pham vi mien cua giam doc."}
        fdate_r = _q(
            "SELECT MAX(save_date) d FROM fact_thongketinhluong "
            "WHERE save_date<=? AND substr(save_date,1,7)=substr(?,1,7)",
            (as_of_date, as_of_date),
        )
        fdate = fdate_r[0]["d"] if fdate_r else None
        if fdate is None:
            return {"error": "Chua co snapshot KPI nhan su trong ky duoc hoi.",
                    "kpi_source": "fact_thongketinhluong", "as_of": None}
        sql = """WITH latest AS (
                     SELECT employee_code, MAX(save_date) d FROM fact_thongketinhluong
                     WHERE save_date<=? AND substr(save_date,1,7)=substr(?,1,7)
                     GROUP BY employee_code
                 ) SELECT COALESCE(f.employee_name,nv.name) name, f.employee_code,
                          0 is_duplicate, f.position_code, cv.description position_label,
                          f.month_sale_amount sales, f.month_sale_target target,
                          0 new_customers, f.save_date metric_snapshot, f.manager_code,
                          COALESCE(mgr.name,f.manager_code) manager_name
                   FROM fact_thongketinhluong f
                   JOIN latest l ON l.employee_code=f.employee_code AND l.d=f.save_date
                   LEFT JOIN (SELECT employee_code, MAX(name) name FROM dim_nhanvien
                              GROUP BY employee_code) nv ON nv.employee_code=f.employee_code
                   LEFT JOIN (SELECT position_code, MAX(description) description FROM dim_chucvu
                              GROUP BY position_code) cv ON cv.position_code=f.position_code
                   LEFT JOIN (SELECT employee_code, MAX(name) name FROM dim_nhanvien
                              GROUP BY employee_code) mgr ON mgr.employee_code=f.manager_code
                   WHERE 1=1"""
        params = [fdate, fdate]
        if position_code:
            sql += " AND f.position_code=?"; params.append(position_code)
        if scope_area_code:
            sql += " AND f.area_code=?"; params.append(scope_area_code)
        roster = _q(sql, tuple(params))
        roster_snapshots = [fdate]
    else:
        fdate_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE save_date<=?", (as_of_date,))
        fdate = fdate_r[0]["d"] if fdate_r else None
        if fdate is None:
            return {"as_of": None, "total_employees": 0, "count_below_target": 0, "count_above_target": 0, "rows": []}
        exempt = (_KNOWN_MISFLAGGED_DUPLICATE_CODES + _KPI_CHANNEL_UNIT_CODES) if hoi_rieng_qlv else None
        roster_sql, roster_params = _roster_employee_sql(fdate)
        sql = f"""WITH roster AS ({roster_sql}), metrics AS (
                 SELECT e.employee_code, SUM(e.amount_ct) sales,
                        MAX(e.month_sale_target) target, SUM(e.is_nc) new_customers,
                        MAX(e.save_date) metric_snapshot, MAX(e.manager_code) manager_code
                 FROM fact_tonghopkhachhang e
                 JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=e.employee_code AND l.d=e.save_date
                 GROUP BY e.employee_code
             ) SELECT nv.name name, e.employee_code employee_code, nv.is_duplicate is_duplicate,
                    nv.position_code position_code, cv.description position_label,
                    m.sales, m.target, m.new_customers, m.metric_snapshot, m.manager_code,
                    COALESCE(mgr.name, m.manager_code) manager_name
             FROM roster e
             LEFT JOIN metrics m ON m.employee_code=e.employee_code
             LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code
             LEFT JOIN dim_chucvu cv ON cv.position_code=nv.position_code
             LEFT JOIN (SELECT employee_code, MAX(name) name FROM dim_nhanvien
                        GROUP BY employee_code) mgr ON mgr.employee_code=m.manager_code
             WHERE {_not_duplicate_sql('nv', exempt)}"""
        params = [*roster_params, fdate, fdate]
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
        roster = _q(sql, tuple(params))
        roster_snapshots = _roster_snapshot_dates(fdate)
    rows = [r for r in roster if _f(r["target"]) > 0]
    unassessed = [
        {"employee_code": r["employee_code"], "name": r["name"],
         "reason": "missing_current_snapshot" if r["metric_snapshot"] is None else "missing_target",
         "sales": None if r["metric_snapshot"] is None else _f(r["sales"]),
         "pct": None}
        for r in roster if _f(r["target"]) <= 0
    ]
    if unassessed:
        _warn(f"Danh sach doi ghi nhan {len(roster)} nguoi; chi {len(rows)} nguoi co chi tieu du "
              f"de danh gia KPI ky {fdate[:7]}. {len(unassessed)} nguoi chua du du lieu, "
              "KHONG duoc ket luan ho dat 0%/khong dat KPI hay lay target thang truoc thay the.",
              code="employee_kpi_incomplete_coverage", severity="warning",
              message=(f"Kỳ {fdate[:7]}: chỉ {len(rows)}/{len(roster)} người đủ dữ liệu để đánh giá KPI. "
                       f"{len(unassessed)} người còn lại chưa đủ dữ liệu; chưa thể kết luận họ đạt 0% "
                       "hoặc không đạt KPI."))
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
        r["la_nhom_kenh"] = (int(r.pop("is_duplicate", 0) or 0) == 1
                             and r["employee_code"] not in _KNOWN_MISFLAGGED_DUPLICATE_CODES)
    below = [r for r in rows if r["pct"] < r["threshold"]]
    above = [r for r in rows if r["pct"] >= r["threshold"]]
    if filter == "below_target":
        selected = sorted(below, key=lambda r: r["pct"])[:limit]
    elif filter == "above_target":
        selected = sorted(above, key=lambda r: -r["pct"])[:limit]
    else:
        key = "sales" if order_by == "sales" else "pct"
        selected = sorted(rows, key=lambda r: -r[key])[:limit]
    if include_team_detail and hoi_rieng_qlv:
        # 14/09/2026 (ban sua tay may 24): "chi tiet ca 4 quan ly" tung mat 6-7 vong/SQL rieng va hon
        # 100 giay. Tra san doi cua tung QLV trong CUNG lan goi. Dung _kpi_snapshot (snapshot moi nhat
        # CUA TUNG NGUOI trong thang) giong revenue_tree; ban sua tay doc save_date=fdate nen giua thang
        # TDV thuoc mien ghi snapshot vao ngay khac se bi ra doanh so 0.
        for r in selected:
            team = []
            for t in _team_of_qlv(r["employee_code"], fdate):
                t_kpi = _kpi_snapshot(t["employee_code"], fdate, t.get("position_code") or "TDV")
                team.append({"employee_code": t["employee_code"], "name": t.get("name"),
                             "position_code": t.get("position_code"), "sales": t_kpi["sales"],
                             "target": t_kpi["target"], "pct": round(t_kpi["pct"], 1),
                             "status": t_kpi["status"]})
            r["team_detail"] = sorted(team, key=lambda d: -(d["sales"] or 0))
            r["team_detail_count"] = len(team)
    threshold_summary = [
        {"threshold_pct": threshold,
         "count": sum(1 for r in rows if r["pct"] >= threshold),
         "total": len(rows)}
        for threshold in (65, 70, 80, 100, 120)
    ]
    # 11/09/2026 (M13): cau hoi "QLV nao co nhieu NV duoi 80% nhat" truoc day khong co san field
    # gop theo QLV (chi co danh sach phang tung nhan vien) nen model phai tu dò nhieu vong
    # get_workforce_productivity/get_revenue_tree voi cac month_to khac nhau va het thoi gian
    # request. Tinh san so nguoi DUOI KPI (80%, khong phai muc huong thuong 65/70%) theo tung QLV.
    below_kpi = [r for r in rows if not r["meets_kpi"]]
    by_manager = {}
    for r in below_kpi:
        mgr_code = r.get("manager_code") or "MISSING_MANAGER"
        entry = by_manager.setdefault(mgr_code, {
            "manager_code": mgr_code,
            "manager_name": r.get("manager_name") or mgr_code,
            "count_below_kpi": 0,
            "employees": [],
        })
        entry["count_below_kpi"] += 1
        entry["employees"].append({
            "employee_code": r["employee_code"], "name": r["name"], "pct": round(r["pct"], 1),
        })
    below_kpi_by_manager = sorted(by_manager.values(), key=lambda x: -x["count_below_kpi"])
    for entry in below_kpi_by_manager:
        entry["employees"] = sorted(entry["employees"], key=lambda e: e["pct"])
    result = {"as_of": fdate, "total_employees": len(rows),
            "roster_employees": len(roster), "unassessed_count": len(unassessed),
            "missing_current_snapshot_count": sum(r["metric_snapshot"] is None for r in roster),
            "roster_snapshots": roster_snapshots,
            "kpi_source": ("fact_thongketinhluong" if kpi_source == "salary_kpi"
                           else "fact_tonghopkhachhang"),
            "position_code": position_code,
            "comparison_basis": (
                "M20/S33 dem moi EmployeeCode mot lan tu snapshot KPI nhan su; mau so doi chieu la "
                "roster_employees, gom ca nguoi thieu target. Chi total_employees nguoi co target "
                "duoc phan loai vao cac moc; khong coi nguoi thieu target la duoi 65%."
                if kpi_source == "salary_kpi" else None),
            "unassessed_rows": unassessed[:max(1, limit)],
            "unassessed_rows_truncated": len(unassessed) > max(1, limit),
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
            # QLV nao co nhieu NV DUOI KPI (80%) nhat - da xep giam dan san, moi QLV kem danh sach
            # NV cua minh (te nhat truoc). "MISSING_MANAGER" nghia la khong xac dinh duoc QLV that
            # tren fact_tonghopkhachhang, KHONG duoc bao la mot QLV that.
            "below_kpi_by_manager": below_kpi_by_manager,
            "rows": selected}
    if kpi_source == "salary_kpi":
        result["comparison_threshold_summary"] = {
            "denominator_all_tdv": len(roster),
            "employees_with_target": len(rows),
            "unassessed_missing_target": len(unassessed),
            "at_least_100_pct": result["count_full_target"],
            "at_least_80_pct": result["count_kpi_achieved"],
            "at_least_65_pct": result["count_above_target"],
            "below_65_pct": result["count_below_target"],
        }
    return result


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
        team_weekend = {}
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
                "weekend_revenue": r.get("weekend_revenue"),
            })
            for day in days:
                team_by_date[day["date"]] = team_by_date.get(day["date"], 0.0) + _f(day.get("revenue"))
            for day in r.get("weekend_days") or []:
                cu = team_weekend.setdefault(day["date"], {"date": day["date"], "thu": day["thu"],
                                                           "revenue": 0.0})
                cu["revenue"] += _f(day.get("revenue"))
        team_days = []
        for date, revenue in sorted(team_by_date.items()):
            pct = revenue / team_target * 100 if team_target else 0.0
            team_days.append({"date": date, "revenue": revenue,
                              "pct_of_team_target": pct, "status": _daily_kpi_status(pct)})
        weekend = sorted(team_weekend.values(), key=lambda d: d["date"])
        team_daily_summary = {
            "count_red": sum(1 for d in team_days if str(d["status"]).startswith("🔴")),
            "count_yellow": sum(1 for d in team_days if str(d["status"]).startswith("🟡")),
            "count_green": sum(1 for d in team_days if str(d["status"]).startswith("🟢")),
            "zero_revenue_dates": [d["date"] for d in team_days if not d["revenue"]],
            "yellow_dates": [d["date"] for d in team_days if str(d["status"]).startswith("🟡")],
            "green_dates": [d["date"] for d in team_days if str(d["status"]).startswith("🟢")],
            # T7/CN khong co mau KPI ngay nhung VAN la doanh so that - xep hang ngay cao nhat gom ca T7.
            "top_revenue_dates": sorted(team_days + weekend, key=lambda d: -d["revenue"])[:5],
            "weekend_days": weekend,
            "weekend_revenue": sum(d["revenue"] for d in weekend),
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
    100% cua ngay). Phan loai tung ngay: 🔴 Do (<2.5%), 🟡 Vang (2.5%-3.5%), 🟢 Xanh (>3.5%). Mau KPI
    ngay CHI ap T2-T6; doanh so T7/CN tra rieng o weekend_days (11/09/2026 - truoc do bi bo han, ma T7
    la ngay ban nhieu nhat). Rieng "month_pct_of_target" la % TONG thang (thuc te/target*100, cach tinh
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
    if ident.get("name_candidates"):
        return _ung_vien_ten_nhan_vien_loi(ident, employee_code)
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
              "hoi thang khac.",
              code="daily_kpi_target_unavailable", severity="warning",
              message=(f"Chưa có dữ liệu chỉ tiêu tháng {year_month} của nhân viên {employee_code}. "
                       "Tỷ lệ hoàn thành theo ngày chưa đủ căn cứ để đánh giá KPI."))

    days = []
    # 11/09/2026 (V03): T7/CN tach RIENG, khong bo. T7 la ngay ban nhieu nhat (22,3% doanh thu OTC
    # T8/2026 tren Bravo); vong lap cu chi giu T2-T6 nen danh sach theo ngay giau ca phan do. Mau KPI
    # ngay (4%/ngay) van chi ap cho T2-T6 cho toi khi DNH chot lai quy tac - khong tu doi quy tac.
    weekend_days = []
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
            else:
                weekend_days.append({"date": str(d), "thu": "T7" if d.weekday() == 5 else "CN",
                                     "revenue": by_date.get(str(d), 0.0)})
            d += dt.timedelta(days=1)

    month_pct = (total_sales_month / target * 100) if target else 0.0
    return {
        "employee_code": employee_code, "resolved_employee_code": resolved_code,
        "employee_name": ident.get("name"), "year_month": year_month,
        "month_sale_target": target, "target_as_of": target_as_of,
        "daily_target_pct": DAILY_KPI_TARGET_PCT,
        "days": days,
        "count_red": count_red, "count_yellow": count_yellow, "count_green": count_green,
        "weekend_days": weekend_days,
        "weekend_revenue": sum(x["revenue"] for x in weekend_days),
        "weekend_note": ("days chi gom T2-T6 (mau KPI ngay 4%). Doanh so T7/CN nam o weekend_days, "
                         "VAN tinh trong month_total_sales - khong duoc bo khi noi ve doanh so tung ngay."),
        "month_total_sales": total_sales_month, "month_pct_of_target": month_pct,
        "channel_scope": channel,
        "data_as_of": latest_data_date(),
    }


def _employee_name_candidates(query: str, limit: int = 10) -> list:
    """Tim nhan vien theo TEN (bo dau, khong phan biet hoa/thuong) trong dim_nhanvien + dmssx_nhanvien.

    16/09/2026 (yeu cau anh Dang): nguoi dung nho TEN chu khong nho ma, nhung cac tool KPI/luong
    truoc day CHI nhan ma nen bot tra loi "can ma nhan vien" du kho co du danh muc. Loc bang Python
    chu khong bang LIKE cua SQLite vi SQLite khong bo dau tieng Viet ("Danh" khong khop "Dánh") -
    cung ly do da dung o inventory_item_stock().
    CHI tra ve ung vien: khi ten ung voi nhieu nguoi thi nguoi goi phai hoi lai, KHONG duoc tu chon.
    """
    q = str(query or "").strip()
    if len(q) < 3 or not any(ch.isalpha() for ch in q):
        return []
    if " " not in q and any(ch.isdigit() for ch in q):
        return []          # 'TM25010199' la ma, khong phai ten - khong doan mo
    tokens = [t for t in _fold_question(q).split() if t]
    if not tokens:
        return []

    rows = []
    try:
        rows += _q("SELECT employee_code, name, position_code, area_code, dmsid, is_duplicate "
                   "FROM dim_nhanvien WHERE name IS NOT NULL AND TRIM(name)<>''")
    except sqlite3.OperationalError:
        pass
    try:
        rows += [dict(r, position_code=None, area_code=None, is_duplicate=0)
                 for r in _q("SELECT dmscode employee_code, name, code dmsid FROM dmssx_nhanvien "
                             "WHERE name IS NOT NULL AND TRIM(name)<>''")]
    except sqlite3.OperationalError:
        pass

    folded_query = " ".join(tokens)
    found = {}
    for r in rows:
        code = str(r.get("employee_code") or r.get("dmsid") or "").strip()
        name = str(r.get("name") or "").strip()
        if not code or not name:
            continue
        folded_name = _fold_question(name)
        if folded_name == folded_query:
            score = 1000
        elif all(token in folded_name.split() for token in tokens):
            score = 900
        else:
            continue
        # Trung ma trong dim_nhanvien: dong is_duplicate=1 thuong la nguoi that, dong kia co the la
        # vi tri trong ("Trong QLV MK3") - xem employee_directory().
        score += 1 if r.get("is_duplicate") else 0
        cu = found.get(code.upper())
        if cu and cu["_score"] >= score:
            continue
        found[code.upper()] = {"employee_code": code, "employee_name": name,
                               "position_code": r.get("position_code"),
                               "area_code": r.get("area_code"),
                               "dmsid": r.get("dmsid") or code, "_score": score}

    best = sorted(found.values(), key=lambda x: (-x["_score"], x["employee_name"]))
    return [{k: v for k, v in item.items() if k != "_score"}
            for item in best[:max(1, int(limit or 10))]]


def _ung_vien_ten_nhan_vien_loi(ident: dict, query: str) -> dict:
    """Loi chuan khi mot TEN nhan vien ung voi nhieu nguoi - bat AI hoi lai thay vi doan."""
    return {
        "error": f"Ten '{query}' ung voi {len(ident['name_candidates'])} nhan vien - chua xac dinh "
                 "duoc nguoi can xem.",
        "employee_candidates": ident["name_candidates"],
        "answer_rule": ("Liet ke ma + ten + vai tro cua cac ung vien de nguoi dung chon. TUYET DOI "
                        "khong tu chon mot nguoi va khong noi he thong chi tra cuu duoc theo ma."),
    }


def _resolve_employee_identity(code: str, _tim_theo_ten: bool = True) -> dict:
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
    # Khong khop ma nao: thu hieu chuoi vao nhu TEN nhan vien (16/09/2026). Chi nhan khi ten ung
    # voi DUNG MOT nguoi; trung ten thi tra "name_candidates" de ham goi hoi lai, khong duoc doan.
    if _tim_theo_ten:
        ung_vien = _employee_name_candidates(code)
        if len(ung_vien) == 1:
            ident = _resolve_employee_identity(ung_vien[0]["employee_code"], _tim_theo_ten=False)
            ident["resolved_from_name"] = code
            if not ident.get("name"):
                ident["name"] = ung_vien[0]["employee_name"]
            if not ident.get("dmsid") or ident["dmsid"] == ung_vien[0]["employee_code"]:
                ident["dmsid"] = ung_vien[0]["dmsid"] or ident.get("dmsid") or code
            return ident
        if len(ung_vien) > 1:
            return {"code": code, "name": None, "position_code": None, "area_code": None,
                    "dmsid": code, "name_candidates": ung_vien}
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
    luon la dong "dung hon". Do lai 18/09/2026 tren kho that, co is_duplicate KHONG he phan biet duoc
    o trong voi nguoi that: TM24060301 co CA HAI dong deu is_duplicate=1 (mot la "Trong QLV MK3",
    mot la Truong Ho Minh Luan), con TM24100101 thi chinh dong O TRONG moi mang is_duplicate=1
    (nguoi that Nguyen Ngoc Quoc Hung mang 0). Dau hieu dung la TEN - xem _la_vi_tri_trong().
    Khi ket qua co NHIEU dong cho cung 1 ma tra cuu, PHAI liet ke HET, KHONG tu chon 1 dong.
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
    """So sanh doanh thu hai ky; khong tao chenh lech khi mot ky nam ngoai pham vi kho."""
    a = revenue_by_channel(date_from_a, date_to_a, scope_area_code, scope_channel, scope_employee_code)
    b = revenue_by_channel(date_from_b, date_to_b, scope_area_code, scope_channel, scope_employee_code)
    a_complete = (a.get("data_coverage") or {}).get("complete", True)
    b_complete = (b.get("data_coverage") or {}).get("complete", True)
    if not a_complete or not b_complete:
        return {
            "period_a": a, "period_b": b, "delta": None, "pct_change": None,
            "comparison_valid": False,
            "warning": ("Mot hoac ca hai ky nam ngoai pham vi doanh thu day du cua kho. "
                        "Khong coi phan thieu la 0 dong va khong tinh chenh lech/% thay doi."),
        }
    delta = a["total"]["revenue"] - b["total"]["revenue"]
    pct_change = (delta / b["total"]["revenue"] * 100) if b["total"]["revenue"] else None
    return {"period_a": a, "period_b": b, "delta": delta, "pct_change": pct_change,
            "comparison_valid": True}


def _ytd_plan(year: int, from_month: str, to_month: str, scope_area_code: str = None,
              scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """Ke hoach luy ke; target OTC bam dung snapshot/cach khử trùng cua checker S02."""
    period_from = f"{year:04d}-{from_month}-01"
    period_to = f"{year:04d}-{to_month}-{_last_day_of_month(year, int(to_month)):02d}"
    period_exclusive = (dt.date(year, int(to_month), _last_day_of_month(year, int(to_month)))
                        + dt.timedelta(days=1)).isoformat()
    channel = str(scope_channel or "ALL").upper()
    if channel not in {"ALL", "OTC", "ETC"}:
        channel = "ALL"
    if scope_employee_code:
        return {
            "total": None, "otc": None, "etc": None,
            "note": ("Khong co target lich su da chot theo DOI QLV. Khong lay danh sach doi hien tai "
                     "de cong nguoc ke hoach cac thang cu."),
        }

    def _sum(sql, params):
        try:
            rows = _q(sql, params)
        except sqlite3.OperationalError:
            return None
        return _f(rows[0]["amount"]) if rows and rows[0]["amount"] is not None else None

    otc = None
    otc_by_region = None
    otc_actual_s02 = None
    otc_actual_by_region_s02 = None
    target_source = None
    plan_note_parts = []
    if channel != "ETC":
        # S02 chấm theo snapshot mới nhất CUA TUNG NHAN VIEN trong từng tháng, chỉ tầng
        # TDV/CTV/CS/TK. Trước đây dùng DIM_TargetVungMien; hai nguồn từng khớp nhưng có thể lệch
        # khi một miền (thực tế MN) cập nhật snapshot sau bảng target vùng.
        # DENSE_RANK được giữ đúng checker, kể cả trường hợp có nhiều dòng cùng SaveDate mới nhất.
        salary_sql = (
            "WITH b AS (SELECT employee_code,area_code,position_code,month_sale_amount,"
            "month_sale_target,save_date,"
            "DENSE_RANK() OVER (PARTITION BY substr(save_date,1,7),employee_code "
            "ORDER BY save_date DESC) snapshot_rank FROM fact_thongketinhluong "
            "WHERE save_date>=? AND save_date<?) "
            "SELECT area_code,SUM(COALESCE(month_sale_target,0)) amount,"
            "SUM(COALESCE(month_sale_amount,0)) actual,"
            "COUNT(DISTINCT substr(save_date,1,7)) covered_months FROM b "
            f"WHERE snapshot_rank=1 AND UPPER(position_code) IN ({_tier_ph()})"
        )
        salary_params = [period_from, period_exclusive, *_EMPLOYEE_TIER_POSITIONS]
        if scope_area_code:
            salary_sql += " AND area_code=?"
            salary_params.append(scope_area_code)
        salary_sql += " GROUP BY area_code"
        expected_months = int(to_month) - int(from_month) + 1
        try:
            salary_rows = _q(salary_sql, tuple(salary_params))
        except sqlite3.OperationalError:
            salary_rows = []
        required_areas = {scope_area_code} if scope_area_code else {"MB", "MT", "MN"}
        returned_areas = {row.get("area_code") for row in salary_rows}
        coverage_by_area = {
            row.get("area_code"): int(row.get("covered_months") or 0) for row in salary_rows
        }
        salary_complete = required_areas.issubset(returned_areas) and all(
            coverage_by_area.get(area) == expected_months for area in required_areas
        )
        if salary_complete:
            otc_by_region = {row["area_code"]: _f(row["amount"]) for row in salary_rows}
            otc_actual_by_region_s02 = {
                row["area_code"]: _f(row["actual"]) for row in salary_rows
            }
            otc = sum(otc_by_region.values())
            otc_actual_s02 = sum(otc_actual_by_region_s02.values())
            target_source = "FACT_ThongKeTinhLuong_S02"
        else:
            sql = ("SELECT area_code,SUM(COALESCE(amount,0)) amount FROM dim_targetvungmien "
                   "WHERE doc_date BETWEEN ? AND ?")
            params = [period_from, period_to]
            if scope_area_code:
                sql += " AND area_code=?"
                params.append(scope_area_code)
            sql += " GROUP BY area_code"
            try:
                fallback_rows = _q(sql, tuple(params))
            except sqlite3.OperationalError:
                fallback_rows = []
            if fallback_rows:
                otc_by_region = {row["area_code"]: _f(row["amount"]) for row in fallback_rows}
                otc = sum(otc_by_region.values())
                target_source = "DIM_TargetVungMien_FALLBACK"
                plan_note_parts.append(
                    "FACT_ThongKeTinhLuong khong phu du cac thang trong ky; target OTC dang tam lay "
                    "tu DIM_TargetVungMien va chua duoc doi chieu theo S02."
                )

    # FACT_KeHoachTongETC chi co target toan quoc, khong co vung/QLV. Tra None thay vi chia deu.
    etc = None
    if channel != "OTC":
        if scope_area_code:
            plan_note_parts.append("Ke hoach ETC chua tach theo vung trong nguon hien co.")
        else:
            etc = _sum(
                "SELECT SUM(COALESCE(amount,0)) amount FROM fact_kehoachtongetc WHERE doc_date BETWEEN ? AND ?",
                (period_from, period_to),
            )

    if channel == "OTC":
        total = otc
    elif channel == "ETC":
        total = etc
    else:
        total = otc + etc if otc is not None and etc is not None else None
    return {
        "total": total, "otc": otc, "etc": etc,
        "otc_by_region": otc_by_region,
        "otc_actual_s02": otc_actual_s02,
        "otc_actual_by_region_s02": otc_actual_by_region_s02,
        "target_source": target_source,
        "note": " ".join(plan_note_parts) or None,
    }


def revenue_ytd_cumulative(year_month_to: str = None, from_month: str = None, years_back: int = 3,
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
    # 16/09/2026: thieu year_month_to KHONG duoc nem TypeError nua. Truoc day day la tham so BAT
    # BUOC nen moi duong goi quen truyen (script, tool test, model bo sot) deu vo thanh "Loi khi chay
    # bao cao chuan". Mac dinh ve thang du lieu gan nhat giong cac tool chuoi thang khac; chi bao loi
    # khi nguoi goi truyen gia tri SAI DINH DANG.
    if not year_month_to:
        _, thang_du_lieu_moi_nhat = _revenue_data_month_range()
        if not thang_du_lieu_moi_nhat:
            return {"error": "Kho chua co hoa don de tinh luy ke."}
        year_month_to = str(thang_du_lieu_moi_nhat)[:7]
    if len(str(year_month_to)) != 7 or str(year_month_to)[4] != "-":
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
    earliest_revenue_month, _ = _revenue_data_month_range()
    for i in range(years_back):
        y = year_to - i
        date_from = f"{y:04d}-{from_month}-01"
        date_to = f"{y:04d}-{month_to}-{_last_day_of_month(y, int(month_to)):02d}"
        r = revenue_by_channel(date_from, date_to, scope_area_code, scope_channel, scope_employee_code)
        if r["total"]["revenue"] <= 0 and r["total"]["invoices"] == 0:
            skipped.append(y)
            continue
        plan = _ytd_plan(y, from_month, month_to, scope_area_code, scope_channel, scope_employee_code)
        actual = r["total"]["revenue"]
        plan_total = plan["total"]
        # C03 UAT 07/09: target T1-T8 van du nhung kho doanh thu hien chi con T7-T8. Neu lay
        # 2 thang thuc dat chia 8 thang target, chatbot se bao 15% YTD rat tron tru nhung sai. Khong
        # duoc cong cac thang khong co kho nhu 0, va cung khong duoc tinh %KH/gap/binh quan can dat.
        history_complete = not earliest_revenue_month or date_from[:7] >= earliest_revenue_month
        year_row = {
            "year": y, "date_from": date_from, "date_to": date_to,
            "revenue": actual, "invoices": r["total"]["invoices"],
            "otc_revenue": r["otc"]["revenue"], "etc_revenue": r["etc"]["revenue"],
            "plan_revenue": plan_total, "plan_otc_revenue": plan["otc"],
            "plan_etc_revenue": plan["etc"],
            "revenue_history_complete": history_complete,
            "pct_of_plan": round(actual / plan_total * 100, 2) if plan_total and history_complete else None,
        }
        if not history_complete:
            year_row["revenue_history_available_from"] = earliest_revenue_month
            year_row["history_warning"] = (
                f"Kho doanh thu chi co tu {earliest_revenue_month}; doanh thu {date_from} den {date_to} "
                f"dang thieu phan truoc {earliest_revenue_month}. Khong tinh % ke hoach/YTD gap "
                "hay binh quan can dat tu so lieu khong day du."
            )
        if plan.get("note"):
            year_row["plan_note"] = plan["note"]
        # Day la phep chia KE HOACH DA NHAP - khong phai du bao/run-rate. Chi co y nghia cho nam
        # dang xem va khi target duoc nguon xac nhan.
        if y == year_to and plan_total is not None and history_complete:
            remaining = max(0.0, plan_total - actual)
            months_remaining = 12 - int(month_to)
            year_row["plan_gap_remaining"] = remaining
            year_row["months_remaining"] = months_remaining
            year_row["average_monthly_plan_needed"] = (
                remaining / months_remaining if months_remaining else None
            )
        years.append(year_row)

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

    # 17/09/2026 - SUA PHEP SO "CUNG KY" KHONG CUNG KY (UAT that, cau C03): date_to o tren LUON la
    # ngay CUOI THANG cua tung nam, nen khi thang dang chay chua tron, nam nay chi co du lieu den
    # ngay 17 nhung nam truoc duoc tinh TRON ca thang. Ket qua: chatbot bao "YTD 2026 thap hon cung
    # ky 2025 -8,7%" trong khi mot phan muc giam chi la do thieu 13 ngay cuoi thang 9/2026. Tool CHI
    # canh bao ve ke hoach (ke hoach tron thang), KHONG canh bao ve phep so cung ky nen model khong
    # co cach nao biet. Cac tool anh em da co co che nay (month_to_is_partial o geography/kpi,
    # comparison_valid o compare_periods) - rieng ham nay con thieu.
    # Giu nguyen cac_nam de khong pha gi dang dung; THEM khoi so cung ky CAT DUNG NGAY.
    moc_du_lieu = latest_data_date()
    nam_moi_nhat = years[0]["year"] if years else None
    if moc_du_lieu and nam_moi_nhat and moc_du_lieu[:7] == f"{nam_moi_nhat:04d}-{month_to}":
        ngay_cat = int(moc_du_lieu[8:10])
        if ngay_cat < _last_day_of_month(nam_moi_nhat, int(month_to)):
            cung_ky = []
            for row in years:
                y = row["year"]
                ngay = min(ngay_cat, _last_day_of_month(y, int(month_to)))
                d_from, d_to = f"{y:04d}-{from_month}-01", f"{y:04d}-{month_to}-{ngay:02d}"
                r = revenue_by_channel(d_from, d_to, scope_area_code, scope_channel,
                                       scope_employee_code)
                cung_ky.append({"year": y, "date_from": d_from, "date_to": d_to,
                                "revenue": r["total"]["revenue"],
                                "otc_revenue": r["otc"]["revenue"],
                                "etc_revenue": r["etc"]["revenue"]})
            for idx in range(len(cung_ky) - 1):
                truoc = cung_ky[idx + 1]["revenue"]      # cac_nam da sap xep giam dan theo nam
                cung_ky[idx]["pct_change_vs_prev_year"] = (
                    (cung_ky[idx]["revenue"] - truoc) / truoc * 100 if truoc else None)
            result["ky_chua_tron"] = True
            result["du_lieu_den_ngay"] = moc_du_lieu
            result["so_cung_ky_dung_ngay"] = {
                "cat_den_ngay": ngay_cat,
                "cac_nam": cung_ky,
                "giai_thich": (f"Cac nam deu cat den ngay {ngay_cat} cua thang {month_to} de so "
                               "CUNG SO NGAY. Day moi la phep so cung ky dung."),
            }
            result["answer_rule_cung_ky"] = (
                "Thang cuoi cua ky nay CHUA TRON (du lieu den " + moc_du_lieu + "). Khi noi ve tang/"
                "giam SO VOI CUNG KY NAM TRUOC, BAT BUOC dung so trong so_cung_ky_dung_ngay - so "
                "trong cac_nam lay het thang cho MOI nam nen nam truoc duoc tinh du thang con nam "
                "nay chi co mot phan, khong phai cung ky. Rieng % ke hoach van doc o cac_nam (ke "
                "hoach von theo tron thang) va phai noi ro ky chua tron."
            )

    if any(not row["revenue_history_complete"] for row in years):
        result["canh_bao_thieu_lich_su_doanh_thu"] = (
            "Co ky YTD thieu du lieu doanh thu truoc moc kho hien co. Cac cot % ke hoach, gap va "
            "binh quan can dat cua ky do la None, khong duoc tu tinh them."
        )
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


def _lui_thang_giu_ngay(ngay: str, so_thang: int) -> str:
    """Lui N thang nhung GIU NGUYEN ngay trong thang - tuong duong DATEADD(month,-N,<ngay>) cua
    SQL Server, ke ca cach ket ngay khi thang dich ngan hon (31/03 lui 1 thang -> 28/02).

    KHAC _month_add(...)+'-01' (moc dau thang lich). Hai cach cho ra ky khac nhau va da tung lam
    lech so that: xem customers_silent.
    """
    y, m, d = int(ngay[:4]), int(ngay[5:7]), int(ngay[8:10])
    ym = _month_add(f"{y:04d}-{m:02d}", -so_thang)
    y2, m2 = int(ym[:4]), int(ym[5:7])
    return f"{y2:04d}-{m2:02d}-{min(d, _last_day_of_month(y2, m2)):02d}"


def _month_diff(year_month_from: str, year_month_to: str) -> int:
    """So thang tu 'YYYY-MM' den 'YYYY-MM' (am neu moc den nam truoc moc tu)."""
    yf, mf = int(year_month_from[:4]), int(year_month_from[5:7])
    yt, mt = int(year_month_to[:4]), int(year_month_to[5:7])
    return (yt * 12 + mt) - (yf * 12 + mf)


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


def _revenue_period_coverage(date_from: str, date_to: str) -> dict:
    """Danh dau khoang doanh thu bi thieu thay vi de SUM rong bien thanh 0 dong hop le."""
    earliest, latest_month = _revenue_data_month_range()
    latest_day = latest_data_date()[:10]
    requested_from_month = str(date_from)[:7]
    requested_to_month = str(date_to)[:7]
    reasons = []
    if not earliest or not latest_month:
        reasons.append("Kho chua co du lieu doanh thu.")
    else:
        if requested_from_month < earliest:
            reasons.append(f"Ky bat dau truoc thang som nhat trong kho ({earliest}).")
        if requested_to_month > latest_month:
            reasons.append(f"Ky ket thuc sau thang moi nhat trong kho ({latest_month}).")
        elif str(date_to)[:10] > latest_day:
            reasons.append(f"Ky ket thuc sau ngay du lieu moi nhat ({latest_day}).")
    return {
        "complete": not reasons,
        "available_from_month": earliest,
        "available_to_date": latest_day,
        "warning": " ".join(reasons) if reasons else None,
    }


def revenue_monthly_series(month_to: str = None, months_back: int = 12, include_yoy: bool = True,
                            scope_area_code: str = None, scope_channel: str = None,
                            scope_employee_code: str = None, include_plans: bool = True,
                            include_region_breakdown: bool = True,
                            include_special_channels: bool = True) -> dict:
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

    # 23/09/2026: hoa don ETC tren may 24 co chung tu de NGAY TUONG LAI (4 dong ngay 28/09 trong khi
    # hom do la 23/09; truoc do 14/08 cung gap dung kieu nay voi ngay 28/08). _month_bounds tra ve
    # ca thang nen thang DANG CHAY cong luon phan tuong lai do, trong khi cau hoi "doanh so thang
    # nay" di qua resolve_relative_date lai cat tai hom nay -> CUNG MOT THANG ra HAI con so tuy cach
    # hoi. Cat tran tai HOM NAY (khong phai latest_data_date(): moc do doc tu vhoadon_otc, neu sync
    # OTC tre hon ETC mot ngay thi se cat mat doanh thu ETC co that).
    hom_nay = str(dt.date.today())
    rows = {}
    tran_thang = {}
    for ym in all_months:
        if (earliest and ym < earliest) or ym > latest:
            rows[ym] = None  # ngoai pham vi du lieu - KHONG duoc coi la 0
            continue
        d_from, d_to = _month_bounds(ym)
        d_to_that = min(d_to, hom_nay)
        if d_to_that < d_from:
            rows[ym] = None
            continue
        tran_thang[ym] = (d_to_that, d_to)
        r = revenue_by_channel(d_from, d_to_that, scope_area_code, scope_channel,
                               scope_employee_code)
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
        d_to_that, d_to_lich = tran_thang.get(ym, (None, None))
        if d_to_that and d_to_that < d_to_lich:
            # Thang chua tron: noi ro so nay tinh den ngay nao, de "38,4% ke hoach" khong bi doc
            # thanh ca thang. Model da tu dien giai dung o UAT 15/09 nhung do la may, khong co gi
            # trong payload bat buoc no phai noi.
            item["tinh_den_ngay"] = d_to_that
            item["thang_chua_tron"] = (
                f"Doanh thu tinh den {d_to_that}, ke hoach la CA THANG - ty le dat KHONG phai ket "
                "qua ca thang.")
            # Chung tu de ngay sau hom nay: KHONG cong vao, nhung cung KHONG duoc giau. Chua co ket
            # luan cua DNH ve viec hoa don ETC de ngay 28 hang thang la ghi truoc theo ke hoach hay
            # nhap sai ngay, nen chi neu ra.
            ngay_sau = (dt.date.fromisoformat(d_to_that) + dt.timedelta(days=1)).isoformat()
            tl = _revenue_by_channel_raw(ngay_sau, d_to_lich, scope_area_code, scope_channel,
                                         scope_employee_code)
            if tl["total"]["revenue"] or tl["total"]["invoices"]:
                item["chung_tu_ngay_tuong_lai"] = {
                    "tu_ngay": ngay_sau, "den_ngay": d_to_lich,
                    "revenue": tl["total"]["revenue"], "invoices": tl["total"]["invoices"],
                    "ghi_chu": ("Chung tu de ngay SAU hom nay, KHONG duoc cong vao doanh thu thang "
                                "va khong duoc trinh bay nhu doanh thu da phat sinh."),
                }
        # C02: tra san target/%/chenh lech cua DUNG thang de model khong tu ghep doanh thu va
        # target tu hai query roi cong nham kenh. C08 chi can doanh thu lich su; bo qua toan bo
        # phan nay de khong lap 24 lan truy van target/phan ra mien roi timeout.
        if include_plans:
            plan = _ytd_plan(int(ym[:4]), ym[5:7], ym[5:7],
                             scope_area_code, scope_channel, scope_employee_code)
            item["plan_revenue"] = plan["total"]
            item["plan_otc_revenue"] = plan["otc"]
            item["plan_etc_revenue"] = plan["etc"]
            item["target_source"] = plan.get("target_source")
            item["achievement_pct"] = (
                item["revenue"] / plan["total"] * 100 if plan["total"] else None
            )
            item["plan_variance"] = (
                item["revenue"] - plan["total"] if plan["total"] is not None else None
            )
            if plan.get("note"):
                item["plan_note"] = plan["note"]
        # C02/S02 yeu cau ca mien. Tra san actual + target OTC tung mien trong cung payload de
        # model khong tu ghep target toan cong ty vao MN, hoac cong nham target MN vao tong.
        if include_plans and include_region_breakdown and scope_channel != "ETC" and not scope_employee_code:
            target_by_region = plan.get("otc_by_region") or {}
            region_codes = ([scope_area_code] if scope_area_code else ["MB", "MT", "MN"])
            s02_actual_by_region = plan.get("otc_actual_by_region_s02") or {}
            # 15/09/2026 (review PR #14): (1) ban dau goi revenue_by_region(d_from, d_to) voi bien SOT
            # tu vong lap truoc -> MOI thang lay doanh thu vung cua month_to; (2) goi ca khi da co S02
            # (ket qua khong dung); (3) thieu bang vung lam hong ca chuoi thang. Chi goi khi can du phong
            # hoa don, dung khoang ngay CUA THANG DO, va loi du lieu vung khong lam hong chuoi.
            region_note = None
            if s02_actual_by_region:
                actual_by_region, actual_source = s02_actual_by_region, "FACT_ThongKeTinhLuong_S02"
            else:
                month_from, month_to_day = _month_bounds(ym)
                try:
                    region_actuals = revenue_by_region(
                        month_from, month_to_day, scope_area_code=scope_area_code, channel="OTC",
                    )
                    actual_by_region = {row["area"]: _f(row["revenue"]) for row in region_actuals}
                    actual_source = "HOA_DON_OTC_FALLBACK"
                except sqlite3.OperationalError as exc:
                    actual_by_region, actual_source = None, None
                    region_note = (f"Chua tach duoc doanh thu OTC theo mien cho thang nay (thieu du lieu "
                                   f"vung: {str(exc)[:120]}). KHONG coi cac mien bang 0.")
        if include_plans and include_region_breakdown and scope_channel != "ETC" and not scope_employee_code and actual_by_region is None:
            item["otc_by_region"] = None
            item["otc_region_note"] = region_note
        elif include_plans and include_region_breakdown and scope_channel != "ETC" and not scope_employee_code:
            item["otc_by_region"] = [{
                "area_code": area,
                "otc_revenue": actual_by_region.get(area, 0.0),
                "plan_otc_revenue": target_by_region.get(area),
                "achievement_pct": (
                    actual_by_region.get(area, 0.0) / target_by_region[area] * 100
                    if target_by_region.get(area) else None
                ),
                "plan_variance": (
                    actual_by_region.get(area, 0.0) - target_by_region[area]
                    if area in target_by_region else None
                ),
                "actual_source": actual_source,
            } for area in region_codes]
            region_actual_total = sum(actual_by_region.get(area, 0.0) for area in region_codes)
            region_plan_total = sum(target_by_region.get(area, 0.0) for area in region_codes)
            s02_company_actual = plan.get("otc_actual_s02")
            scope_company_actual = (
                s02_company_actual if s02_company_actual is not None else item["otc_revenue"]
            )
            item["s02_otc_company"] = {
                "actual": scope_company_actual,
                "target": plan["otc"],
                "achievement_pct": (
                    scope_company_actual / plan["otc"] * 100
                    if scope_company_actual is not None and plan["otc"] else None
                ),
                "plan_variance": (
                    scope_company_actual - plan["otc"]
                    if scope_company_actual is not None and plan["otc"] is not None else None
                ),
                "source": actual_source,
            }
            item["otc_region_reconciliation"] = {
                "revenue_sum_regions": region_actual_total,
                "revenue_company_otc": scope_company_actual,
                "revenue_matches": (scope_company_actual is not None
                                    and abs(region_actual_total - scope_company_actual) <= 1),
                "invoice_otc_revenue_reference": item["otc_revenue"],
                "plan_sum_regions": region_plan_total,
                "plan_company_otc": plan["otc"],
                "plan_matches": (plan["otc"] is not None
                                 and abs(region_plan_total - plan["otc"]) <= 1),
            }
        # 15/09/2026 (UAT OTC-Only C-Level 14:17-14:20 "doanh so kenh MT cac thang" roi "bo sung ke
        # hoach va % thuc hien"): tra san doanh thu + ke hoach + % dat kenh dac biet (Kenh MT) tung thang
        # trong CUNG payload. So nay DA NAM SAN trong doanh thu OTC mien Nam, khong cong them.
        if include_special_channels and scope_channel != "ETC" and not scope_employee_code:
            month_from, month_last_day = _month_bounds(ym)
            try:
                buckets = _channel_sub_buckets()
            except sqlite3.OperationalError:
                buckets = []
            special = []
            for b in buckets:
                if scope_area_code and b["area_code"] not in _area_markers(scope_area_code):
                    continue
                if month_from < _detail_cutoff():
                    bucket_revenue = None   # phan da nen khong con ma kenh, khong tach duoc
                else:
                    bucket_revenue = _f(_q(
                        "SELECT COALESCE(SUM(amount9),0) rev FROM vhoadon_otc WHERE channel_code=? "
                        "AND doc_date BETWEEN ? AND ?",
                        (b["dmsid"], month_from, f"{month_last_day} 23:59:59"))[0]["rev"])
                plan, plan_note = _special_channel_plan(b["name"], b["area_code"], month_from, month_last_day)
                entry = {"name": b["name"], "area_code": b["area_code"], "revenue": bucket_revenue,
                         "plan_revenue": plan,
                         "achievement_pct": (bucket_revenue / plan * 100)
                         if plan and bucket_revenue is not None else None}
                if bucket_revenue is None:
                    entry["revenue_note"] = "Thang nay da nen theo khach x thang, khong con tach duoc kenh."
                if plan_note:
                    entry["plan_note"] = plan_note
                if ym == latest:
                    entry["thang_dang_chay"] = "Doanh thu tinh den ngay du lieu moi nhat; ke hoach la ca thang."
                special.append(entry)
            if special:
                item["otc_special_channels"] = special
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


def revenue_seasonality(month_to: str = None, months_back: int = 24,
                        scope_area_code: str = None, scope_channel: str = None,
                        scope_employee_code: str = None) -> dict:
    """C08/S80: mua vu doanh thu theo kenh, khong keo target/YoY/tach mien cua C02.

    C08 tung dung get_revenue_monthly_series mac dinh: 24 thang x target x mien x kenh dac biet
    lam tool timeout truoc khi model co du lieu de tra loi. O day chi lay chuoi doanh thu can thiet
    va danh dau ro khi kho chua du it nhat hai quan sat cho moi thang duong lich.
    """
    months_back = max(12, min(int(months_back or 24), 24))
    series = revenue_monthly_series(
        month_to=month_to, months_back=months_back, include_yoy=False,
        scope_area_code=scope_area_code, scope_channel=scope_channel,
        scope_employee_code=scope_employee_code, include_plans=False,
        include_region_breakdown=False, include_special_channels=False,
    )
    if series.get("error"):
        return series

    latest_day = str(series.get("data_as_of") or latest_data_date())[:10]
    latest_month = latest_day[:7]
    today_month_end = _last_day_of_month(int(latest_month[:4]), int(latest_month[5:7]))
    current_month_complete = latest_day >= f"{latest_month}-{today_month_end:02d}"
    complete_rows = [
        row for row in series["months"]
        if not row.get("khong_co_du_lieu")
        and (row["month"] != latest_month or current_month_complete)
    ]

    def _channel_result(channel: str, field: str):
        values = [row for row in complete_rows if row.get(field) is not None]
        by_calendar_month = {}
        for row in values:
            by_calendar_month.setdefault(int(row["month"][5:7]), []).append(_f(row[field]))
        if not values:
            return {"channel": channel, "status": "NO_DATA_IN_SCOPE", "months": []}
        monthly_average = {month: sum(amounts) / len(amounts) for month, amounts in by_calendar_month.items()}
        overall_average = sum(monthly_average.values()) / len(monthly_average) if monthly_average else None
        current = next((row for row in series["months"] if row["month"] == latest_month), None)
        current_value = _f(current[field]) if current and current.get(field) is not None else None
        expected = monthly_average.get(int(latest_month[5:7]))
        observations = len(by_calendar_month.get(int(latest_month[5:7]), []))
        enough_history = len(values) >= 24 and all(len(by_calendar_month.get(month, [])) >= 2 for month in range(1, 13))
        rows = []
        for month in sorted(monthly_average):
            average = monthly_average[month]
            rows.append({
                "calendar_month": month,
                "observations": len(by_calendar_month[month]),
                "average_revenue": average,
                "seasonal_index_pct": average / overall_average * 100 if overall_average else None,
            })

        # 24/09/2026 (C08 UAT): status INSUFFICIENT_HISTORY da co san cho ca hai kenh nhung cau tra loi
        # van chot "thang 2 thap nhat" nhu chac chan. Mot co chung chung khong du - phai chi ro CHO NAO
        # chua vung. Thuoc do: nua chenh lech giua hai nam cua CUNG mot thang duong lich, quy ra diem
        # chi so - tuc la neu chi co mot nam thi chi so thang do lech khoi binh quan hai nam bao nhieu.
        # Do tren kho that 24/09: trung vi 6,8 diem (OTC), 10,2 diem (ETC). Truong hop C08: thang 2
        # (82,26%, 2 nam) chi thap hon thang 9 (87,26%, 1 nam) 5,0 diem - nho hon dao dong binh thuong,
        # ma thang 9 lai chi co mot nam du lieu. Khong co can cu noi "thang 2 thap nhat".
        so_qs = {row["calendar_month"]: row["observations"] for row in rows}
        qs_max = max(so_qs.values()) if so_qs else 0
        thang_it_qs = sorted(month for month, n in so_qs.items() if n < qs_max)
        nua_chenh = [
            (max(amounts) - min(amounts)) / 2 / overall_average * 100
            for amounts in by_calendar_month.values()
            if len(amounts) >= 2 and overall_average
        ]
        dao_dong = median(nua_chenh) if nua_chenh else None

        def _xep_hang(cao_nhat: bool):
            thu_tu = sorted(rows, key=lambda row: row["seasonal_index_pct"] or 0, reverse=cao_nhat)
            if len(thu_tu) < 2:
                return None
            dau, nhi = thu_tu[0], thu_tu[1]
            chenh = abs((dau["seasonal_index_pct"] or 0) - (nhi["seasonal_index_pct"] or 0))
            ly_do = []
            if dau["calendar_month"] in thang_it_qs:
                ly_do.append("thang %d chi co %d nam du lieu (cac thang khac %d nam)"
                             % (dau["calendar_month"], dau["observations"], qs_max))
            if dao_dong is None:
                ly_do.append("chua do duoc do dao dong giua cac nam")
            elif chenh < dao_dong:
                ly_do.append("chi %s hon thang %d %.1f diem, nho hon muc dao dong binh thuong giua hai nam "
                             "cua cung mot thang (%.1f diem)%s"
                             % ("cao" if cao_nhat else "thap", nhi["calendar_month"], chenh, dao_dong,
                                "; thang %d lai chi co %d nam du lieu" % (nhi["calendar_month"], nhi["observations"])
                                if nhi["calendar_month"] in thang_it_qs else ""))
            return {
                "calendar_month": dau["calendar_month"],
                "runner_up_month": nhi["calendar_month"],
                "gap_pts": round(chenh, 2),
                "robust": not ly_do,
                "reason": "; ".join(ly_do) or None,
            }

        xep_thap, xep_cao = _xep_hang(False), _xep_hang(True)
        chua_vung = [(nhan, x) for nhan, x in (("thap nhat", xep_thap), ("cao nhat", xep_cao))
                     if x and not x["robust"]]
        ranking_note = None
        if chua_vung:
            ranking_note = (
                "BAT BUOC NOI RO VOI NGUOI DUNG: " + " | ".join(
                    "Xep hang thang %s (thang %d) CHUA VUNG: %s" % (nhan, x["calendar_month"], x["reason"])
                    for nhan, x in chua_vung)
                + ". KHONG khang dinh 'thang X la thang %s'; trinh bay la hai thang sat nhau va chua du "
                  "du lieu de phan dinh." % "/".join(nhan for nhan, _ in chua_vung))
        return {
            "channel": channel,
            "status": "READY" if enough_history else "INSUFFICIENT_HISTORY_FOR_SEASONAL_CONCLUSION",
            "complete_months_observed": len(values),
            "required_complete_months": 24,
            "months": rows,
            "highest_calendar_month": max(rows, key=lambda row: row["seasonal_index_pct"]) if rows else None,
            "lowest_calendar_month": min(rows, key=lambda row: row["seasonal_index_pct"]) if rows else None,
            "calendar_months_with_fewer_observations": thang_it_qs,
            "year_to_year_noise_pts": round(dao_dong, 1) if dao_dong is not None else None,
            "lowest_ranking": xep_thap,
            "highest_ranking": xep_cao,
            "ranking_note": ranking_note,
            "current_month": latest_month,
            "current_month_revenue": current_value,
            "expected_full_month_revenue": expected,
            "current_month_observations_in_baseline": observations,
            "deviation_from_seasonal": (
                current_value - expected if current_month_complete and current_value is not None and expected is not None else None
            ),
            "deviation_pct": (
                (current_value - expected) / expected * 100
                if current_month_complete and current_value is not None and expected else None
            ),
            "current_month_note": (
                "Thang dang chay chua tron; khong so sanh doanh thu luy ke voi muc binh quan cua thang tron."
                if not current_month_complete else None
            ),
        }

    channels = []
    if scope_channel != "ETC":
        channels.append(_channel_result("OTC", "otc_revenue"))
    if scope_channel != "OTC":
        channels.append(_channel_result("ETC", "etc_revenue"))

    # Nhom hang ETC co tren hoa don chi tiet. OTC khong co GroupCode du tin cay; khong lay ten SKU
    # hay chuoi quy cach de tu gan nhom. Lich su chi tiet co cua so rieng nen ket qua nay la tham khao,
    # khong duoc noi la mua vu nhieu nam.
    etc_groups = []
    etc_group_status = "NOT_APPLICABLE_CHANNEL_SCOPE" if scope_channel == "OTC" else None
    if scope_channel != "OTC":
        join = _etc_area_join("v", scope_area_code)
        scope_sql, scope_params = _scope_clause(scope_area_code)
        emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=latest_day)
        try:
            rows = _q(
                "SELECT substr(v.doc_date,1,7) month,COALESCE(NULLIF(TRIM(v.group_code),''),'UNKNOWN') group_code,"
                "SUM(v.amount9) revenue FROM vhoadon_etc v " + join +
                " WHERE v.doc_date>=? AND v.doc_date<=?" + scope_sql + emp_sql +
                " GROUP BY substr(v.doc_date,1,7),COALESCE(NULLIF(TRIM(v.group_code),''),'UNKNOWN')",
                (_detail_cutoff(), latest_day, *scope_params, *emp_params),
            )
            names = {str(row["code"]): row["name"] for row in _q(
                "SELECT code,name FROM dim_keyclass WHERE group_code=?", (_ETC_ITEM_TYPE_GROUP,)
            )}
            per_group = {}
            for row in rows:
                per_group.setdefault(str(row["group_code"]), []).append(row)
            for code, values in sorted(per_group.items()):
                etc_groups.append({
                    "group_code": code, "group_name": names.get(code) or code,
                    "months_observed": len({row["month"] for row in values}),
                    "revenue_by_month": values,
                })
            etc_group_status = (
                "INSUFFICIENT_DETAIL_HISTORY_FOR_SEASONAL_CONCLUSION"
                if len({row["month"] for row in rows}) < 24 else "READY"
            )
        except sqlite3.Error as exc:
            etc_group_status = f"SOURCE_UNAVAILABLE: {str(exc)[:120]}"

    return {
        "status": "READY" if all(row.get("status") == "READY" for row in channels) else "PARTIAL_HISTORY",
        "as_of": latest_day,
        "month_from": series["month_from"], "month_to": series["month_to"],
        "seasonality_by_channel": channels,
        "product_groups": {
            "otc_status": "SOURCE_GAP_OTC_PRODUCT_GROUP_NOT_CLASSIFIED",
            "etc_status": etc_group_status,
            "etc_groups": etc_groups,
            "definition": (
                "Nhom hang ETC chi co trong cua so hoa don chi tiet. OTC khong co ma nhom san pham "
                "du tin cay trong kho, nen khong tu suy dien tu ten SKU."
            ),
        },
        "definition": (
            "Chi so mua vu = doanh thu binh quan cua mot thang duong lich / binh quan cac thang duong lich. "
            "Ket luan cao/thap chi dung khi moi thang duong lich co it nhat 2 quan sat nam va co >=24 thang tron."
        ),
        "data_as_of": series.get("data_as_of"),
    }


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


def _invoice_customer_lifecycle_series(month_to: str, months_back: int,
                                       scope_area_code: str = None,
                                       scope_employee_code: str = None) -> dict:
    """Chuoi C29 suy tu hoa don OTC, tach khoi co nghiep vu NC/RO/AC cua Bravo.

    Khong goi `first_observed` la khach moi that. Cua so quan sat C29 bat dau 10/2025
    theo #sales cua checker UAT, doc lap voi so thang hien thi. C29 hien chi co co NC/RO
    cho OTC, nen chuoi kem theo cung khoa OTC.
    """
    earliest, latest = _revenue_data_month_range()
    if not earliest or not latest:
        return {"status": "no_data", "months": []}
    # #sales cua checker C29 loc DocDate >= 2025-10-01. Thang 09/2025 van co trong kho,
    # nhung neu nap no thi khach chi mua T9 roi quay lai T4-T9/2026 bi chuyen nham
    # tu first-observed sang reactivated. Giữ mốc này cố định khi đổi months_back.
    required_history_from = "2025-10"
    history_from = max(earliest, required_history_from)
    history_complete = earliest <= required_history_from
    rows = _customer_monthly_activity(
        history_from, month_to, scope_area_code, "OTC", scope_employee_code,
    )
    activity = {}
    for row in rows:
        # Du _customer_monthly_activity co the tra nhieu dong/NV, C29 dem moi khach dung mot lan.
        key = (row["channel"], row["customer_code"])
        months = activity.setdefault(key, {})
        months[row["month"]] = months.get(row["month"], 0.0) + _f(row["revenue"])

    series = []
    for offset in range(months_back - 1, -1, -1):
        month = _month_add(month_to, -offset)
        previous = _month_add(month, -1)
        if month < history_from:
            series.append({
                "month": month, "khong_co_du_lieu_hoa_don": True,
                "invoice_active_customers": None, "invoice_continuing_customers": None,
                "invoice_reactivated_customers": None, "invoice_stopped_customers": None,
                "invoice_first_observed_customers": None,
            })
            continue
        active = continuing = reactivated = first_observed = stopped = 0
        for periods in activity.values():
            current_revenue = periods.get(month, 0.0)
            previous_revenue = periods.get(previous, 0.0)
            had_before_previous = any(
                revenue > 0 and observed_month < previous
                for observed_month, revenue in periods.items()
            )
            if current_revenue > 0:
                active += 1
                if previous_revenue > 0:
                    continuing += 1
                elif had_before_previous:
                    reactivated += 1
                else:
                    first_observed += 1
            elif previous_revenue > 0:
                stopped += 1
        series.append({
            "month": month,
            "invoice_active_customers": active,
            # Thieu thang lien truoc thi khong duoc bien "khong thay" thanh 0.
            "invoice_continuing_customers": continuing if previous >= history_from else None,
            "invoice_reactivated_customers": reactivated if history_complete else None,
            "invoice_stopped_customers": stopped if previous >= history_from else None,
            "invoice_first_observed_customers": first_observed if history_complete else None,
            "classification_history_complete": history_complete,
        })
    return {
        "status": "ok" if history_complete else "PARTIAL_HISTORY", "channel": "OTC",
        "required_history_from": required_history_from, "history_from": history_from,
        "available_month_range": {"from": earliest, "to": latest},
        "months": series,
        "definitions": {
            "invoice_active_customers": "Khach co doanh thu hoa don rong duong trong thang.",
            "invoice_continuing_customers": "Khach co doanh thu duong o ca thang nay va thang lien truoc.",
            "invoice_reactivated_customers": (
                "Khach co doanh thu duong thang nay, khong mua thang lien truoc, va da mua som hon "
                "trong cua so lich su."
            ),
            "invoice_stopped_customers": (
                "Khach co doanh thu duong thang truoc nhung thang nay khong co doanh thu duong; "
                "chi dem tai thang dau tien ngung."
            ),
            "invoice_first_observed_customers": (
                "Lan dau thay doanh thu duong trong cua so lich su dang co; KHONG dong nghia chac "
                "chan la khach moi trong doi."
            ),
        },
        "warning": (
            "Chuoi hoa don la phep suy dien hanh vi, KHAC co Bravo: khach_moi=is_nc va "
            "so_is_ro=Re-Order. Khong doi ten continuing thanh Re-Order va khong cong cac nhom "
            "voi nhau nhu mot phep phan hoach neu chua khoa cung dinh nghia. Neu status=PARTIAL_HISTORY, "
            "reactivated/first_observed tra None vi thieu lich su de phan biet; KHONG duoc noi la 0."
        ),
    }


def _vong_doi_khach_theo_vung(snap: str, scope_area_code: str = None,
                              allowed: list = None) -> list:
    """Tach so khach theo VUNG cho mot snapshot KPI - dung quy tac cua checker S67.

    18/09/2026 (cau M23): cau hoi la "so khach moi/tai kich hoat/mua lai/ngung mua cua TUNG VUNG",
    nhung tool chi co scope_area_code de LOC, khong co truc vung - nen chatbot tra ve mot dong toan
    quoc va bo han ve dau cua cau hoi.

    Khong duoc group thang theo nv.area_code: mot khach co nhieu dong (TDV cua ho va dong rollup
    QLV) va hai dong do co the mang area khac nhau, cong lai se vuot tong. Quy tac cua S67: khach
    thuoc vung cua dong TANG NHAN VIEN; chi khach KHONG co dong tang nao moi lay vung cua dong QLV
    (QLV tu ban khi dia ban trong, vd LCH00074 do QLV Vu Xuan Phong TM25010129 ban truc tiep).
    Do lai 18/09 tren kho: MB 4.859 / MN 1.080 / MT 987, tong 6.926 - khop 100% so da chot cua S67,
    va ca bon cot cong lai bang dung so toan quoc."""
    pos_ph = ",".join(["?"] * len(_EMPLOYEE_TIER_POSITIONS))
    sql = (f"SELECT nv.area_code area_code, f.customer_code customer_code, "
           f"MAX(CASE WHEN nv.position_code IN ({pos_ph}) THEN 1 ELSE 0 END) la_tang, "
           f"MAX(CASE WHEN f.is_nc=1 THEN 1 ELSE 0 END) nc, "
           f"MAX(CASE WHEN f.is_ro=1 THEN 1 ELSE 0 END) ro "
           f"FROM fact_tonghopkhachhang f "
           f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
           f"WHERE f.save_date=? AND {_not_duplicate_sql('nv')}")
    params = [*_EMPLOYEE_TIER_POSITIONS, snap]
    if scope_area_code:
        sql += " AND nv.area_code=?"
        params.append(scope_area_code)
    if allowed is not None:
        sql += f" AND f.employee_code IN ({','.join(['?'] * len(allowed))})"
        params.extend(allowed)
    sql += " GROUP BY nv.area_code, f.customer_code"

    chon = {}
    for row in _q(sql, tuple(params)):
        vung = row["area_code"] or "KHONG_XAC_DINH"
        cu = chon.get(row["customer_code"])
        # Uu tien dong tang nhan vien; hoa thi chot theo ten vung de ket qua on dinh giua cac lan chay.
        if cu is None or (row["la_tang"] and not cu["la_tang"]) or (
                row["la_tang"] == cu["la_tang"] and vung < cu["area_code"]):
            chon[row["customer_code"]] = {"area_code": vung, "la_tang": row["la_tang"],
                                          "nc": row["nc"], "ro": row["ro"]}
    gop = {}
    for row in chon.values():
        muc = gop.setdefault(row["area_code"], {
            "area_code": row["area_code"], "tong_khach": 0, "khach_moi": 0,
            "so_is_ro": 0, "khach_khong_mang_co": 0})
        muc["tong_khach"] += 1
        muc["khach_moi"] += int(row["nc"] or 0)
        muc["so_is_ro"] += int(row["ro"] or 0)
        if not row["nc"] and not row["ro"]:
            muc["khach_khong_mang_co"] += 1
    return sorted(gop.values(), key=lambda r: -r["tong_khach"])


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

    pos_ph = ",".join(["?"] * len(_EMPLOYEE_TIER_POSITIONS))
    months = []
    for i in range(months_back - 1, -1, -1):
        ym = _month_add(year_month, -i)
        snap = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang WHERE substr(save_date,1,7)=?", (ym,))
        snap = snap[0]["d"] if snap else None
        if not snap:
            months.append({"month": ym, "khong_co_du_lieu": True})
            continue

        # 07/09/2026: khong duoc lay DOI HIEN TAI roi ap nguoc cho chuoi lich su. Cung mot bay
        # da tung lam M01 sai: TDV chuyen doi se bi tinh nham vao (hoac bi bo sot khoi) thang cu.
        # ManagerCode cua dung snapshot la nguon duy nhat biet thanh phan doi o ky dang bao cao.
        allowed = None
        roster_snapshot = None
        if scope_employee_code:
            team = _team_of_qlv(scope_employee_code, snap)
            allowed = [scope_employee_code] + [t["employee_code"] for t in team]
            roster_snapshot = snap
        # 18/09/2026 - cau M24: bo loc TANG NHAN VIEN ra khoi cac cot DEM.
        # COUNT(DISTINCT customer_code) von da mien nhiem voi chuyen dong QLV chong len dong TDV, nen
        # loc tang o WHERE khong chong duoc gi ma chi lam MAT khach chi xuat hien tren dong QLV -
        # tuc khach do chinh QLV ban truc tiep, khong co TDV nao duoi quyen ghi nhan. Do that snapshot
        # 31/08/2026: 627 khach moi that, ban cu bao 612; 15 khach bi mat deu nam tron tren mot dong
        # QLV duy nhat (Do Thi Thuy 7 khach, Tran Thien Khiem 2, Nguyen Thi Hong Thuy 2...).
        # Thang 7 la 613 vs 605, thang 6 la 765 vs 752 - lech co he thong chu khong phai ngau nhien.
        # Loc tang VAN CAN cho hai cot SUM(amount_ct) vi tien thi that su bi cong hai lan.
        sql = (f"SELECT COUNT(DISTINCT f.customer_code) tong_khach, "
               f"COUNT(DISTINCT CASE WHEN f.is_nc=1 THEN f.customer_code END) khach_moi, "
               f"COUNT(DISTINCT CASE WHEN f.is_nc=1 AND nv.position_code IN ({pos_ph}) "
               f"THEN f.customer_code END) khach_moi_co_tang_nhan_vien, "
               f"COUNT(DISTINCT CASE WHEN f.is_ro=1 THEN f.customer_code END) so_is_ro, "
               f"COUNT(DISTINCT CASE WHEN f.is_ac=1 "
               f"AND UPPER(COALESCE(nv.position_code,'')) IN ('CS','TK') "
               f"THEN f.customer_code END) so_is_ac, "
               # BAY SQLite (do thuc te 24/08/2026): is_nc/is_ro luu kieu TEXT ('0'/'1') du schema
               # khai INTEGER. So sanh THANG "f.is_nc=1" van dung vi SQLite ap affinity cua COT len
               # gia tri. Nhung COALESCE(f.is_nc,0) la BIEU THUC - bieu thuc KHONG co affinity, nen
               # COALESCE(...)=0 thanh so sanh TEXT voi INTEGER va LUON SAI: dem ra 0 thay vi 646.
               # Vi vay phai so sanh TRUC TIEP tren cot, xu ly NULL bang IS NULL rieng.
               #
               # 18/09/2026: phai dem KHACH CO MANG CO roi tru ra, KHONG duoc dem dong "khong mang co
               # nao". Ke tu khi bo loc tang nhan vien, moi khach deu co them mot dong rollup QLV va
               # dong do thuong de trong ca hai co - dem theo dong thi gan nhu ca kho roi vao nhom
               # "khong mang co" (do that: 6.344 thay vi 734).
               f"COUNT(DISTINCT CASE WHEN f.is_nc=1 OR f.is_ro=1 THEN f.customer_code END) khach_co_mang_co, "
               f"SUM(CASE WHEN f.is_nc=1 AND nv.position_code IN ({pos_ph}) "
               f"THEN COALESCE(f.amount_ct,0) ELSE 0 END) doanh_so_khach_moi, "
               f"SUM(CASE WHEN nv.position_code IN ({pos_ph}) "
               f"THEN COALESCE(f.amount_ct,0) ELSE 0 END) doanh_so_tang_nhan_vien "
               f"FROM fact_tonghopkhachhang f "
               f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
               # Loc ban ghi nhan vien trung: so DEM khach thi khong bi anh huong (da COUNT DISTINCT
               # customer_code) nhung 2 truong doanh so dung SUM(amount_ct) thi SE bi thoi phong.
               f"WHERE f.save_date=? AND {_not_duplicate_sql('nv')}")
        params = [*_EMPLOYEE_TIER_POSITIONS, *_EMPLOYEE_TIER_POSITIONS,
                  *_EMPLOYEE_TIER_POSITIONS, snap]
        if scope_area_code:
            sql += " AND nv.area_code=?"
            params.append(scope_area_code)
        if allowed is not None:
            sql += f" AND f.employee_code IN ({','.join(['?'] * len(allowed))})"
            params.extend(allowed)
        r = _q(sql, tuple(params))[0]
        month_result = {
            "month": ym, "snapshot_date": snap,
            "tong_khach": int(r["tong_khach"] or 0),
            "khach_moi": int(r["khach_moi"] or 0),
            "khach_moi_do_qlv_ban_truc_tiep": (int(r["khach_moi"] or 0)
                                               - int(r["khach_moi_co_tang_nhan_vien"] or 0)),
            "so_is_ro": int(r["so_is_ro"] or 0),
            "so_is_ac": int(r["so_is_ac"] or 0),
            "khach_khong_mang_co": (int(r["tong_khach"] or 0) - int(r["khach_co_mang_co"] or 0)),
            "doanh_so_khach_moi": _f(r["doanh_so_khach_moi"]),
            "doanh_so_tang_nhan_vien": _f(r["doanh_so_tang_nhan_vien"]),
        }
        if roster_snapshot:
            month_result["team_roster_snapshot"] = roster_snapshot
        month_result["theo_vung"] = _vong_doi_khach_theo_vung(snap, scope_area_code, allowed)
        months.append(month_result)

    missing = [m["month"] for m in months if m.get("khong_co_du_lieu")]
    result = {
        "months": months,
        "tang_du_lieu": (
            "Cac cot DEM khach lay tren TOAN BO dong cua snapshot (COUNT DISTINCT customer_code nen "
            "dong rollup QLV chong len dong TDV khong lam sai). khach_moi_do_qlv_ban_truc_tiep la so "
            "khach chi xuat hien tren dong QLV - QLV tu ban, khong co TDV duoi quyen ghi nhan; day la "
            "khach THAT, da nam trong khach_moi. Rieng hai cot doanh so chi cong TANG NHAN VIEN "
            "(TDV/CTV/CS/TK) vi tien thi bi cong hai lan that. "
            "theo_vung tach dung bon cot dem do theo tung vung, moi khach thuoc DUNG MOT vung "
            "(vung cua dong tang nhan vien; khach khong co dong tang nao moi lay vung cua dong QLV) "
            "nen cac vung cong lai bang dung so toan quoc - dung khoi nay cho cau hoi 'tung vung', "
            "KHONG goi lai tool ba lan theo tung vung."),
        "canh_bao_dinh_nghia": _customer_flag_caveat(),
        "pham_vi_kenh": "OTC (nguon FACT_TongHopKhachHang noi qua DIM_NhanVien chi phu nhan vien OTC)",
        "data_as_of": latest_data_date(),
    }
    result["invoice_lifecycle_series"] = _invoice_customer_lifecycle_series(
        year_month, months_back, scope_area_code, scope_employee_code,
    )
    # 18/09/2026 - cau "thang nay co bao nhieu khach dang hoat dong": so_is_ac chi 28-46 khach/thang
    # vi day la co Bravo danh RIENG cho CS/Cho si va TK/kenh MT, khong phai phep dem khach con mua.
    # Con so dung nam o invoice_lifecycle_series, cach do mot cap nested - du xa de bi doc nham.
    # Dat thang canh so_is_ac trong cung mot dong thang de khong the nham nua.
    _theo_thang = {m.get("month"): m for m in result["invoice_lifecycle_series"].get("months", [])}
    for m in months:
        nguon = _theo_thang.get(m.get("month")) or {}
        if nguon.get("invoice_active_customers") is not None:
            m["khach_co_hoa_don_trong_thang"] = nguon["invoice_active_customers"]
            m["y_nghia_so_is_ac"] = (
                f"so_is_ac={m.get('so_is_ac')} la CO CS/TK cua Bravo, KHONG phai so khach dang hoat "
                f"dong. Muon tra loi 'bao nhieu khach con mua' thi dung "
                f"khach_co_hoa_don_trong_thang={nguon['invoice_active_customers']}.")
    if missing:
        result["canh_bao_thieu_lich_su"] = (
            f"Khong co snapshot cho {len(missing)}/{len(months)} thang: {', '.join(missing)}. "
            "Kho fact_tonghopkhachhang chi dong bo khoang 90 ngay gan nhat; khong duoc coi cac "
            "thang thieu la 0 khach."
        )
    if scope_channel:
        result["channel_scope"] = "OTC"
    return result


def _table_columns(table: str) -> set:
    try:
        return {r["name"] for r in _q(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return set()


def _employee_name_map(codes) -> dict:
    """Ten nhan vien cho nhieu ma cung luc; uu tien ban ghi con lam viec."""
    codes = [c for c in dict.fromkeys(codes) if c]
    if not codes:
        return {}
    ph = ",".join(["?"] * len(codes))
    names = {}
    for r in _q(f"SELECT employee_code, name FROM dim_nhanvien WHERE employee_code IN ({ph}) "
                "ORDER BY CASE WHEN is_resigned=0 THEN 0 ELSE 1 END", tuple(codes)):
        if r["employee_code"] not in names and r["name"]:
            names[r["employee_code"]] = r["name"]
    return names


def _area_markers(scope_area_code: str) -> list:
    region_key = next((k for k, ms in REGION_SQL_MARKERS.items() if scope_area_code in ms), None)
    return list(REGION_SQL_MARKERS.get(region_key, [scope_area_code]))


def _ma_doi_hieu_luc(scope_employee_code, manager_code):
    """Ma doi duoc dung: pham vi server (tai khoan QLV) LUON thang tham so model truyen vao.

    16/09/2026 (nhat ky UAT 15:16 - C-Level hoi "... doi qlv TM23100148" bi LOI sau 114 giay): ba tool
    danh sach chi loc doi khi TAI KHOAN la QLV, khong co tham so cho C-Level hoi ve MOT doi cu the, nen
    model phai loc tay tren danh sach toan cong ty (523 khach, payload ~105k ky tu) roi cham tran thoi
    gian. Them manager_code, nhung tai khoan QLV khong the dung no de xem doi khac."""
    if scope_employee_code:
        return scope_employee_code
    return str(manager_code or "").strip() or None


def _kpi_customer_month_rows(year_month, where_sql, extra_cols, scope_area_code, scope_employee_code,
                             manager_code=None):
    """Dong khach x nhan vien cua snapshot MOI NHAT CUA TUNG NHAN VIEN trong thang.

    15/09/2026 (UAT 13:59 thieu khach moi): ghim MOT MAX(save_date) chung cho ca thang (cach cua
    customer_lifecycle_summary) se mat khach khi cac mien chot snapshot khac ngay (vd 27/07 MB-MN,
    28/07 MT). Checker S93 lay snapshot moi nhat theo tung nhan vien - dung chung cach do."""
    latest_r = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang")
    latest = latest_r[0]["d"] if latest_r and latest_r[0]["d"] else None
    if not latest:
        return None, []
    ym = (year_month or str(latest))[:7]
    fdate = f"{ym}-{_last_day_of_month(int(ym[:4]), int(ym[5:7])):02d}"
    sql = (f"SELECT f.customer_code, f.employee_code, f.manager_code, f.save_date, f.amount_ct{extra_cols}, "
           "nv.position_code, nv.area_code FROM fact_tonghopkhachhang f "
           f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=f.employee_code AND l.d=f.save_date "
           "LEFT JOIN (SELECT employee_code, MAX(position_code) position_code, MAX(area_code) area_code "
           "FROM dim_nhanvien GROUP BY employee_code) nv ON nv.employee_code=f.employee_code "
           f"WHERE {where_sql}")
    params = [fdate, fdate]
    team_code = _ma_doi_hieu_luc(scope_employee_code, manager_code)
    if team_code:
        sql += " AND (f.manager_code=? OR f.employee_code=?)"
        params += [team_code, team_code]
    if scope_area_code:
        markers = _area_markers(scope_area_code)
        sql += f" AND nv.area_code IN ({','.join('?' for _ in markers)})"
        params += markers
    return ym, _q(sql, tuple(params))


def _prefer_employee_tier(rows: list) -> list:
    """Bang KPI co ca dong rollup QLV chong len dong TDV cho CUNG khach. Moi khach giu dong tang nhan
    vien (moi nhan vien mot dong); khach chi co dong quan ly thi giu mot dong do."""
    by_customer = {}
    for row in rows:
        by_customer.setdefault(row["customer_code"], []).append(row)
    chosen = []
    for items in by_customer.values():
        tier = [r for r in items if str(r.get("position_code") or "").upper() in _EMPLOYEE_TIER_POSITIONS]
        if tier:
            seen = set()
            for row in tier:
                if row["employee_code"] not in seen:
                    seen.add(row["employee_code"])
                    chosen.append(row)
        else:
            chosen.append(max(items, key=lambda r: _f(r.get("amount_ct"))))
    return chosen


def _co_bat(value) -> bool:
    """Co Bravo luu '1'/'0' (TEXT) hoac 1/0 - so sanh an toan."""
    return str(value).strip() in {"1", "1.0", "True", "true"}


def _nguoi_phu_trach(row: dict, emp_names: dict) -> dict:
    return {"employee_code": row["employee_code"], "employee_name": emp_names.get(row["employee_code"]),
            "manager_code": row.get("manager_code"), "manager_name": emp_names.get(row.get("manager_code"))}


def _is_new_customer_quality_question(question: str) -> bool:
    q = _fold_question(question)
    return (any(marker in q for marker in ("khach moi", "khach hang moi"))
            and any(marker in q for marker in ("mo nhieu", "chat luong", "dt/khach",
                                               "doanh thu/khach", "doanh thu tren moi khach"))
            and "mua lai" in q)


def _dem_don_khach_trong_ky(customer_codes, start, end, channels) -> dict:
    """So don cua TUNG khach trong ky. OrderKey = kenh + Stt: hai kenh co the trung Stt (gop lai se
    dem thieu don), con mot Stt nhieu dong SKU van chi la MOT don."""
    counts = {}
    codes = sorted(customer_codes)
    for i in range(0, len(codes), 400):
        chunk = codes[i:i + 400]
        ph = ",".join("?" for _ in chunk)
        parts, params = [], []
        for table, channel in channels:
            parts.append(f"SELECT customer_code, '{channel}|' || COALESCE(stt,'') order_key "
                         f"FROM {table} WHERE doc_date>=? AND doc_date<? AND customer_code IN ({ph})")
            params.extend([start, end, *chunk])
        for r in _q("SELECT customer_code, COUNT(DISTINCT order_key) n FROM "
                    f"({' UNION ALL '.join(parts)}) GROUP BY customer_code", tuple(params)):
            counts[r["customer_code"]] = r["n"]
    return counts


def _new_customer_quality(year_month=None, limit=200, manager_code=None,
                          scope_area_code=None, scope_employee_code=None, scope_channel=None):
    """M24: khach moi = co IsNC cua Bravo trong snapshot moi nhat cua TUNG nhan vien; khong suy tu hoa don.

    22/09/2026 - do tren kho ngay 21/09, ky 8/2026:
      - Co IsNC phai OR tren MOI dong cua khach roi moi gan nguoi phu trach (dung quy tac 15/09 cua
        new_customer_list va checker S93: co khach chi mang co o dong rollup QLV con dong TDV IsNC=0).
        Chi dem dong TDV ra 611 khach, OR moi dong ra 627 - khop "627/627 khach T8" ghi o
        local_warehouse.py::SCHEMA. 625/627 khach co dong tang nhan vien de gan, 2 khach chi co dong
        quan ly thi giu dong quan ly (giong _prefer_employee_tier cua cac tool danh sach).
      - Tang nhan vien lay theo _EMPLOYEE_TIER_POSITIONS (TDV/CTV/CS/TK), KHONG chep cung 'TDV':
        thang 8 co 1 khach cua CTV, chep cung la mat khach do (dung bay da mac ngay 03/09 voi chuc
        danh TK, xem _tier_ph).
      - Pham vi doi loc theo (manager_code OR employee_code) nhu cac tool danh sach khac. Loc moi
        manager_code thi tai khoan TDV khong khop dong nao va bi tra ve "0 khach moi" - dung dieu ma
        tool nay cam ket khong bao gio lam."""
    if scope_channel and str(scope_channel).strip().upper() != "OTC":
        return {"not_applicable": True, "channel_scope": str(scope_channel).strip().upper(),
                "error": "Nguon khach moi (FACT_TongHopKhachHang) hien chi phu kenh OTC."}
    latest = _q("SELECT MAX(save_date) d FROM fact_tonghopkhachhang")
    if not latest or not latest[0]["d"]:
        return {"error": "CHUA danh gia duoc: kho chua co snapshot KPI khach hang."}
    month = (year_month or str(latest[0]["d"]))[:7]
    start = _month_bounds(month)[0]
    end = _month_bounds(_month_add(month, 1))[0]
    if "area_code" not in _table_columns("fact_tonghopkhachhang"):
        return {"error": "CHUA danh gia duoc M24: can dong bo lai KPI khach hang de co AreaCode cua snapshot."}
    if not _q("SELECT 1 FROM fact_tonghopkhachhang WHERE save_date>=? AND save_date<? LIMIT 1", (start, end)):
        return {"error": f"CHUA danh gia duoc M24: khong co snapshot ky {month}."}
    missing = _q("SELECT COUNT(*) n FROM fact_tonghopkhachhang "
                 "WHERE save_date>=? AND save_date<? AND (area_code IS NULL OR TRIM(area_code)='')",
                 (start, end))
    if missing[0]["n"]:
        return {"error": "CHUA danh gia duoc M24: snapshot con thieu AreaCode; can dong bo lai KPI khach hang."}
    team = _ma_doi_hieu_luc(scope_employee_code, manager_code)
    params = [start, end]
    filters = ""
    if scope_area_code:
        markers = _area_markers(scope_area_code)
        filters += f" AND f.area_code IN ({','.join('?' for _ in markers)})"
        params.extend(markers)
    if team:
        filters += " AND (f.manager_code=? OR f.employee_code=?)"
        params.extend([team, team])
    rows = _q(f"""WITH latest_snap AS (
        SELECT employee_code,MAX(save_date) d FROM fact_tonghopkhachhang
        WHERE save_date>=? AND save_date<? GROUP BY employee_code
    ), nv AS (
        SELECT employee_code,MAX(position_code) position_code FROM dim_nhanvien GROUP BY employee_code
    )
    SELECT f.employee_code,f.customer_code,f.amount_ct,f.is_nc,f.save_date,f.area_code,nv.position_code
    FROM fact_tonghopkhachhang f JOIN latest_snap s
      ON s.employee_code=f.employee_code AND s.d=f.save_date
    LEFT JOIN nv ON nv.employee_code=f.employee_code
    WHERE 1=1{filters}""", tuple(params))
    nc_customers = {r["customer_code"] for r in rows if _co_bat(r.get("is_nc"))}
    pairs = [(r["employee_code"], r["customer_code"]) for r in rows if r["customer_code"] in nc_customers]
    if len(pairs) != len(set(pairs)):
        return {"error": "CHUA danh gia duoc M24: snapshot trung cap TDV/khach; can doi chieu nguon truoc khi cong doanh thu."}
    chosen = [r for r in _prefer_employee_tier(rows) if r["customer_code"] in nc_customers]
    # Scope ap tren snapshot TRUOC khi noi don. Chi truy hoa don cua cac khach duoc phep; tai khoan
    # chi OTC khong duoc dem don ETC cua khach chung hai kenh.
    channels = [("vhoadon_otc", "OTC")] + ([] if scope_channel else [("vhoadon_etc", "ETC")])
    orders = _dem_don_khach_trong_ky(nc_customers, start, end, channels)
    emp_names = _employee_name_map([r["employee_code"] for r in chosen])
    by_emp, by_area = {}, {}
    for r in chosen:
        mua_lai = 1 if orders.get(r["customer_code"], 0) > 1 else 0
        doanh_thu = _f(r["amount_ct"])
        e = by_emp.setdefault((r["employee_code"], r["area_code"]), {
            "employee_code": r["employee_code"], "employee_name": emp_names.get(r["employee_code"]),
            "position_code": r["position_code"], "area_code": r["area_code"],
            "snapshot_date": str(r["save_date"])[:10], "khach_moi": 0, "doanh_thu_khach_moi": 0.0,
            "khach_moi_co_mua_lai": 0})
        e["snapshot_date"] = min(e["snapshot_date"], str(r["save_date"])[:10])
        e["khach_moi"] += 1
        e["doanh_thu_khach_moi"] += doanh_thu
        e["khach_moi_co_mua_lai"] += mua_lai
        a = by_area.setdefault(r["area_code"], {
            "area_code": r["area_code"], "so_nhan_vien": 0, "so_luot_khach_moi_theo_nhan_vien": 0,
            "so_khach_moi_duy_nhat": 0, "doanh_thu_khach_moi": 0.0, "so_luot_mua_lai": 0,
            "_khach": set(), "_nv": set()})
        a["so_luot_khach_moi_theo_nhan_vien"] += 1
        a["doanh_thu_khach_moi"] += doanh_thu
        a["so_luot_mua_lai"] += mua_lai
        a["_khach"].add(r["customer_code"])
        a["_nv"].add(r["employee_code"])
    items = sorted(by_emp.values(), key=lambda r: (-r["khach_moi"], r["employee_code"]))
    for r in items:
        r["doanh_thu_binh_quan_khach_moi"] = r["doanh_thu_khach_moi"] / r["khach_moi"]
        r["ty_le_mua_lai_khach_moi_pct"] = 100 * r["khach_moi_co_mua_lai"] / r["khach_moi"]
    for a in by_area.values():
        a["so_khach_moi_duy_nhat"] = len(a.pop("_khach"))
        a["so_nhan_vien"] = len(a.pop("_nv"))
        a["doanh_thu_binh_quan_khach_moi"] = (a["doanh_thu_khach_moi"]
                                              / a["so_luot_khach_moi_theo_nhan_vien"])
        a["ty_le_mua_lai_khach_moi_pct"] = (100 * a["so_luot_mua_lai"]
                                            / a["so_luot_khach_moi_theo_nhan_vien"])
    limit = max(1, min(int(limit or 200), 1000))
    return {"month": month, "mode": "quality", "classification_basis": "BRAVO_ISNC_SNAPSHOT",
            "scope_area_code": scope_area_code, "manager_code": team,
            "invoice_channels": [channel for _, channel in channels],
            "by_employee": items[:limit],
            "by_area": sorted(by_area.values(), key=lambda a: -a["so_luot_khach_moi_theo_nhan_vien"]),
            "tong_khach_moi_duy_nhat": len(nc_customers),
            "total_count": len(items), "returned_count": len(items[:limit]), "truncated": len(items) > limit,
            "snapshot_dates": sorted({r["snapshot_date"] for r in items}),
            "definition": "Khach moi = co IsNC=1 cua Bravo tren BAT KY dong nao cua khach trong snapshot "
                          "moi nhat tung nhan vien trong thang (dong TDV hoac dong rollup QLV), sau do gan "
                          "cho dong tang nhan vien (TDV/CTV/CS/TK); khach chi co dong quan ly thi giu dong "
                          "quan ly. Doanh thu = Amount_CT cua snapshot trong CHINH thang do; mua lai = tren 1 OrderKey "
                          "(kenh + Stt) cung trong thang do. KHAC checker S92: S92 dem tren hoa don "
                          "(Amount9) trong cua so 3 thang va tinh mua lai la co tu 2 NGAY mua tro len, "
                          "nen ty le mua lai va DT/khach cua S92 cao hon han - phai neu ro moc nao khi tra loi. "
                          "Mapping theo EmployeeCode KPI, KHONG theo nguoi ban tren hoa don. Khong tron voi "
                          "khach lan dau mua quan sat tu hoa don/nhan vien ETC. Tong theo mien la luot "
                          "khach-nhan vien; so khach duy nhat o so_khach_moi_duy_nhat. Khong tu ket luan mo "
                          "nhieu nhung kem neu cac chi so khong chung minh dieu do."}


def new_customer_list(year_month: str = None, limit: int = 200, manager_code: str = None,
                      scope_area_code: str = None, scope_employee_code: str = None,
                      scope_channel: str = None, mode: str = "list") -> dict:
    """DANH SACH khach hang moi (IsNC Bravo) trong thang kem ngay ghi nhan, doanh so thang va nguoi
    phu trach.

    15/09/2026 (UAT 13:59 "danh sach khach hang moi, ngay ghi nhan va doanh so phat sinh thang nay" -
    thieu khach, ngay ghi nhan sai): chua co tool DANH SACH, va snapshot bi ghim mot MAX(save_date).
    Ngay ghi nhan = NCSaveDate, KHONG dung ngay snapshot (ngay snapshot giong nhau cho moi khach)."""
    if mode == "quality":
        return _new_customer_quality(year_month, limit, manager_code, scope_area_code,
                                     scope_employee_code, scope_channel)
    if mode != "list":
        return {"error": "mode chi nhan list/quality."}
    if scope_channel and str(scope_channel).strip().upper() != "OTC":
        return {"not_applicable": True, "channel_scope": str(scope_channel).strip().upper(),
                "error": "Nguon khach moi (FACT_TongHopKhachHang) hien chi phu kenh OTC."}
    limit = max(1, min(int(limit or 200), 1000))
    has_nc_date = "nc_save_date" in _table_columns("fact_tonghopkhachhang")
    extra = (", f.nc_save_date" if has_nc_date else ", NULL nc_save_date") + ", f.is_nc"
    # Co khach moi tinh theo KHACH (OR tren moi dong): do tren kho 15/09, 4 khach cua TDV moi TM26081401
    # co dong TDV IsNC=0 nhung dong rollup QLV IsNC=1 kem NCSaveDate - la khach moi that (checker S93 dem).
    # Nguoi phu trach van lay dong tang nhan vien; ngay ghi nhan lay tu dong mang co.
    team_code = _ma_doi_hieu_luc(scope_employee_code, manager_code)
    ym, rows = _kpi_customer_month_rows(year_month, "1=1", extra, scope_area_code, scope_employee_code,
                                        manager_code)
    if ym is None:
        return {"error": "Kho chua co snapshot KPI khach hang nao."}
    nc_dates = {}
    for r in rows:
        if _co_bat(r.get("is_nc")):
            current = nc_dates.get(r["customer_code"])
            value = str(r["nc_save_date"])[:10] if r.get("nc_save_date") else None
            nc_dates[r["customer_code"]] = min(filter(None, (current, value)), default=None)
    rows = [dict(r, nc_save_date=nc_dates[r["customer_code"]])
            for r in _prefer_employee_tier(rows) if r["customer_code"] in nc_dates]
    customer_names = _customer_names([r["customer_code"] for r in rows])
    emp_names = _employee_name_map([r["employee_code"] for r in rows] + [r["manager_code"] for r in rows])
    items = [{
        "customer_code": r["customer_code"],
        "customer_name": customer_names.get(r["customer_code"]) or "(chua co ten trong danh muc)",
        "ngay_ghi_nhan": str(r["nc_save_date"])[:10] if r.get("nc_save_date") else None,
        "doanh_so_thang": _f(r["amount_ct"]),
        "snapshot_date": str(r["save_date"])[:10],
        **_nguoi_phu_trach(r, emp_names),
    } for r in rows]
    items.sort(key=lambda i: (i["ngay_ghi_nhan"] or "", i["doanh_so_thang"]), reverse=True)
    result = {
        "month": ym,
        "ma_doi": team_code,
        "total_new_customers": len({i["customer_code"] for i in items}),
        "total_rows": len(items),
        "tong_doanh_so_thang": sum(i["doanh_so_thang"] for i in items),
        "snapshot_dates": sorted({i["snapshot_date"] for i in items}),
        "rows": items[:limit],
        "rows_truncated": len(items) > limit,
        "definition": (
            "Khach moi = co IsNC=1 cua Bravo trong snapshot moi nhat cua tung nhan vien trong thang. "
            "Ngay ghi nhan = NCSaveDate (ngay hoa don dau tien ghi nhan khach moi). Doanh so thang = "
            "Amount_CT cua snapshot, tinh den ngay snapshot."),
        "pham_vi_kenh": "OTC",
        "data_as_of": latest_data_date(),
    }
    if not has_nc_date:
        result["canh_bao_ngay_ghi_nhan"] = (
            "Kho chua dong bo NCSaveDate nen chua co ngay ghi nhan. KHONG dung ngay snapshot thay the.")
    return result


def reorder_pending_customers(year_month: str = None, limit: int = 200, manager_code: str = None,
                              scope_area_code: str = None, scope_employee_code: str = None,
                              scope_channel: str = None) -> dict:
    """DANH SACH khach phat sinh trong cua so tai don (ROMonth, thuong 3 thang) nhung CHUA tai don
    trong thang (IsRO<>1), kem lan mua gan nhat va KPI tai don cua tung TDV.

    15/09/2026 (UAT 14:08 "khach hang phat sinh 3 thang nhung chua dat KPI tai don cua TDV"): chua co
    tool tra DANH SACH, chatbot chi mo ta chung. Kho chua dong bo ROMonth/ROLastDate truoc ngay nay."""
    if scope_channel and str(scope_channel).strip().upper() != "OTC":
        return {"not_applicable": True, "channel_scope": str(scope_channel).strip().upper(),
                "error": "Nguon tai don (FACT_TongHopKhachHang) hien chi phu kenh OTC."}
    if "ro_month" not in _table_columns("fact_tonghopkhachhang"):
        return {"status": "SOURCE_NOT_SYNCED", "error": (
            "Kho chua dong bo cua so tai don (ROMonth/ROLastDate). Chua lap duoc danh sach; "
            "KHONG ket luan khach nao da hay chua tai don.")}
    limit = max(1, min(int(limit or 200), 1000))
    # 15/09/2026 (do tren Bravo): dong rollup QLV mang IsRO=0 cho CHINH cac khach ma dong TDV da IsRO=1
    # (doi TM23100148: 144/144 dong QLV trung khach dong TDV). Loc co truoc khi khu trung se bo dong TDV
    # va gan nham khach "chua tai don" cho QLV -> khu trung TRUOC, loc co SAU.
    team_code = _ma_doi_hieu_luc(scope_employee_code, manager_code)
    ym, rows = _kpi_customer_month_rows(
        year_month, "f.ro_month IS NOT NULL",
        ", f.ro_month, f.ro_last_date, f.reorder_start_date, f.is_ro", scope_area_code, scope_employee_code,
        manager_code)
    if ym is None:
        return {"error": "Kho chua co snapshot KPI khach hang nao."}
    reordered = {r["customer_code"] for r in rows if _co_bat(r.get("is_ro"))}
    rows = [r for r in _prefer_employee_tier(rows) if r["customer_code"] not in reordered]
    customer_names = _customer_names([r["customer_code"] for r in rows])
    emp_names = _employee_name_map([r["employee_code"] for r in rows] + [r["manager_code"] for r in rows])
    items = [{
        "customer_code": r["customer_code"],
        "customer_name": customer_names.get(r["customer_code"]) or "(chua co ten trong danh muc)",
        "ro_last_date_bravo": str(r["ro_last_date"])[:10] if r.get("ro_last_date") else None,
        "cua_so_tai_don_tu": str(r["reorder_start_date"])[:10] if r.get("reorder_start_date") else None,
        "so_thang_cua_so": int(_f(r["ro_month"])) if r.get("ro_month") is not None else None,
        "doanh_so_thang": _f(r["amount_ct"]),
        "snapshot_date": str(r["save_date"])[:10],
        **_nguoi_phu_trach(r, emp_names),
    } for r in rows]
    items.sort(key=lambda i: (i["employee_code"] or "", i["customer_code"] or ""))

    kpi_by_employee = []
    employee_codes = sorted({i["employee_code"] for i in items if i["employee_code"]})
    if employee_codes:
        fdate = f"{ym}-{_last_day_of_month(int(ym[:4]), int(ym[5:7])):02d}"
        ph = ",".join("?" for _ in employee_codes)
        try:
            kpi_rows = _q(
                "WITH s AS (SELECT employee_code, MAX(save_date) d FROM fact_thongketinhluong "
                "WHERE save_date<=? AND substr(save_date,1,7)=? GROUP BY employee_code) "
                "SELECT f.employee_code, f.position_code, f.reorder_cus_quantity q, f.reorder_percent p "
                "FROM fact_thongketinhluong f JOIN s ON s.employee_code=f.employee_code AND s.d=f.save_date "
                f"WHERE f.employee_code IN ({ph})", (fdate, ym, *employee_codes))
        except sqlite3.OperationalError:
            kpi_rows = []
        pending = {}
        for item in items:
            pending[item["employee_code"]] = pending.get(item["employee_code"], 0) + 1
        for r in kpi_rows:
            quantity, ratio = _f(r["q"]), _f(r["p"])
            is_manager = str(r["position_code"] or "").upper() not in _EMPLOYEE_TIER_POSITIONS
            row = {
                "employee_code": r["employee_code"], "employee_name": emp_names.get(r["employee_code"]),
                "position_code": r["position_code"],
                "khach_da_tai_don": quantity,
                # 15/09/2026 (do tren Bravo): ReOrderCusTarget = 1.0 la HE SO, KHONG phai so khach. Chi tieu so
                # khach la FACT_PhatSinhNhanVien.ReOrderTarget va ROPercent_R = ROCustomerQuantity/ReOrderTarget
                # (TM23100128: 18/27 = 0,66667; TM25030305: 26/29 = 0,89655) - suy nguoc tu hai cot da dong bo.
                "chi_tieu_khach_tai_don": round(quantity / ratio) if ratio > 0 and not is_manager else None,
                "ty_le_dat_kpi_tai_don_pct": ratio * 100 if not is_manager else None,
                "so_khach_chua_tai_don": pending.get(r["employee_code"], 0),
            }
            if is_manager:
                row["ghi_chu"] = "Dong quan ly la so tong hop, khong cham KPI tai don rieng."
            kpi_by_employee.append(row)
    return {
        "month": ym,
        "ma_doi": team_code,
        "total_pending_customers": len({i["customer_code"] for i in items}),
        "total_rows": len(items),
        "rows": items[:limit],
        "rows_truncated": len(items) > limit,
        "kpi_tai_don_theo_nhan_vien": kpi_by_employee,
        "definition": (
            "Khach phat sinh trong cua so tai don (ROMonth thang, tu cua_so_tai_don_tu) cua snapshot moi "
            "nhat tung nhan vien, CHUA co co IsRO trong thang = chua tinh vao KPI khach tai don. Do tren "
            "Bravo 15/09: moi dong IsRO=0 deu co hoa don trong thang - la khach DA mua nhung chua dat dieu "
            "kien tai don cua Bravo (ReOrderCond), KHONG phai khach ngung mua. ro_last_date_bravo la cot "
            "ROLastDate cua Bravo (co the rong), khong phai ngay mua gan nhat. "
            "KPI tai don tung TDV lay tu ket qua tinh luong: so khach da tai don va ty le dat; chi tieu so "
            "khach = so khach da tai don / ty le dat (khop ReOrderTarget cua Bravo)."),
        "pham_vi_kenh": "OTC",
        "data_as_of": latest_data_date(),
    }


def focus_product_kpi(year_month: str = None, limit: int = 100, manager_code: str = None,
                      scope_area_code: str = None, scope_employee_code: str = None) -> dict:
    """DOANH SO SAN PHAM TRONG TAM va KPI trong tam theo QUAN LY VUNG (tang QLV) tu FACT_ThongKeTinhLuong.

    15/09/2026 (UAT 14:10-14:11 "Doanh so san pham trong tam theo quan ly vung" - thieu KPI san pham
    trong tam, luot hoi lai loi): chua co tool nao doc TargetProductAmount/TPRTargetAmount. Bang co nhieu
    tang chong nhau (TP/QLV/TDV cung doanh so) - chi lay DUNG tang QLV, khong cong cac tang."""
    cols = _table_columns("fact_thongketinhluong")
    if not cols:
        return {"error": "Kho chua co ket qua KPI tinh luong."}
    latest_r = _q("SELECT MAX(save_date) d FROM fact_thongketinhluong")
    latest = latest_r[0]["d"] if latest_r and latest_r[0]["d"] else None
    if not latest:
        return {"error": "Kho chua co ket qua KPI tinh luong."}
    ym = (year_month or str(latest))[:7]
    fdate = f"{ym}-{_last_day_of_month(int(ym[:4]), int(ym[5:7])):02d}"
    target_col = "f.tpr_target_amount" if "tpr_target_amount" in cols else "NULL"
    sql = ("WITH s AS (SELECT employee_code, MAX(save_date) d FROM fact_thongketinhluong "
           "WHERE save_date<=? AND substr(save_date,1,7)=? GROUP BY employee_code) "
           "SELECT f.employee_code, f.employee_name, f.position_code, f.area_code, f.manager_code, f.save_date, "
           f"f.target_product_amount actual, {target_col} target, f.target_product_percent pct_goc, "
           "f.tpr_point diem FROM fact_thongketinhluong f "
           "JOIN s ON s.employee_code=f.employee_code AND s.d=f.save_date WHERE 1=1")
    params = [fdate, ym]
    if scope_area_code:
        markers = _area_markers(scope_area_code)
        sql += f" AND f.area_code IN ({','.join('?' for _ in markers)})"
        params += markers
    rows = _q(sql, tuple(params))
    emp_names = _employee_name_map([r["manager_code"] for r in rows])

    def _item(r):
        actual, target = _f(r["actual"]), (_f(r["target"]) if r["target"] is not None else None)
        return {"employee_code": r["employee_code"], "employee_name": r["employee_name"],
                "area_code": r["area_code"], "manager_code": r["manager_code"],
                "manager_name": emp_names.get(r["manager_code"]),
                "doanh_so_trong_tam": actual, "chi_tieu_trong_tam": target,
                "pct_dat": (actual / target * 100) if target else None,
                "ty_le_goc_bravo": r["pct_goc"], "diem_kpi_trong_tam": r["diem"],
                "snapshot_date": str(r["save_date"])[:10]}

    team_code = _ma_doi_hieu_luc(scope_employee_code, manager_code)
    managers = [r for r in rows if str(r["position_code"] or "").upper() == "QLV"]
    members = [r for r in rows if str(r["position_code"] or "").upper() in _EMPLOYEE_TIER_POSITIONS]
    if team_code:
        managers = [r for r in managers if r["employee_code"] == team_code]
        members = [r for r in members if r["manager_code"] == team_code]
    manager_items = sorted((_item(r) for r in managers),
                           key=lambda i: (i["pct_dat"] is None, i["pct_dat"] or 0))
    result = {
        "month": ym,
        "quan_ly_vung": manager_items[:limit],
        "so_quan_ly_vung": len(manager_items),
        "definition": (
            "Doanh so trong tam = TargetProductAmount, chi tieu = TPRTargetAmount, pct_dat = doanh so / chi "
            "tieu. ty_le_goc_bravo va diem_kpi_trong_tam la so Bravo da tinh san cho KPI luong. Snapshot moi "
            "nhat tung nguoi trong thang; chi tang QLV, KHONG cong TP/QLV/TDV vi cac tang chong nhau."),
        "pham_vi_kenh": "OTC",
        "data_as_of": latest_data_date(),
    }
    if team_code:
        result["ma_doi"] = team_code
        result["thanh_vien_doi"] = sorted((_item(r) for r in members),
                                          key=lambda i: (i["pct_dat"] is None, i["pct_dat"] or 0))[:limit]
    if target_col == "NULL":
        result["canh_bao_chi_tieu"] = ("Kho chua dong bo TPRTargetAmount nen chua co chi tieu trong tam; "
                                       "KHONG tu tinh % dat.")
    return result


# 15/09/2026 (anh Dang): moi ma san pham va ma nhan vien trong cau tra loi phai kem ten. (khoa ma,
# cac khoa ten da co san thi khong gan lai, khoa ten se gan, loai danh muc)
_MA_CAN_TEN = (
    ("item_code", ("item_name", "name", "product_name", "ten_san_pham"), "item_name", "product"),
    ("employee_code", ("employee_name", "name", "ten_nhan_vien"), "employee_name", "employee"),
    ("manager_code", ("manager_name", "ten_quan_ly"), "manager_name", "employee"),
)
_MAX_DICT_GAN_TEN = 5000
_CHUNK_GAN_TEN = 500


def _can_gan_ten(row: dict, code_key: str, name_keys: tuple):
    code = row.get(code_key)
    if not isinstance(code, str) or not code.strip() or any(row.get(k) for k in name_keys):
        return None
    return code.strip()


def _tra_ten_theo_lo(sql_template: str, codes: list, key_cols: tuple) -> dict:
    names = {}
    for i in range(0, len(codes), _CHUNK_GAN_TEN):
        chunk = codes[i:i + _CHUNK_GAN_TEN]
        ph = ",".join("?" for _ in chunk)
        params = tuple(chunk) * len(key_cols)
        for r in _q(sql_template.format(ph=ph), params):
            for col in key_cols:
                if r.get(col) and r.get("name") and r[col] not in names:
                    names[r[col]] = r["name"]
    return names


def _gan_ten_cho_ma(result):
    """Gan ten cho moi item_code/employee_code/manager_code chua co ten trong ket qua tool.

    Lam MOT LAN o call_template thay vi sua tung tool: 50 tool, nhieu tool tra ma tran. Khong ghi de ten
    da co, khong tu dat ten khi danh muc khong co. Buoc bo sung - loi o day KHONG duoc lam hong ket qua."""
    try:
        stack, rows = [result], []
        while stack and len(rows) < _MAX_DICT_GAN_TEN:
            current = stack.pop()
            if isinstance(current, dict):
                rows.append(current)
                stack.extend(v for v in current.values() if isinstance(v, (dict, list)))
            elif isinstance(current, list):
                stack.extend(v for v in current if isinstance(v, (dict, list)))
        need_products, need_employees = set(), set()
        for row in rows:
            for code_key, name_keys, _, kind in _MA_CAN_TEN:
                code = _can_gan_ten(row, code_key, name_keys)
                if code:
                    (need_products if kind == "product" else need_employees).add(code)
        if not need_products and not need_employees:
            return result
        product_names, employee_names = {}, {}
        if need_products:
            try:
                product_names = _tra_ten_theo_lo(
                    "SELECT code, name FROM brv_sanpham WHERE code IN ({ph})", sorted(need_products), ("code",))
            except sqlite3.OperationalError:
                pass
        if need_employees:
            try:
                employee_names = _tra_ten_theo_lo(
                    "SELECT employee_code, dmsid, name FROM dim_nhanvien "
                    "WHERE employee_code IN ({ph}) OR dmsid IN ({ph}) "
                    "ORDER BY CASE WHEN COALESCE(is_duplicate,0)=0 THEN 0 ELSE 1 END",
                    sorted(need_employees), ("employee_code", "dmsid"))
            except sqlite3.OperationalError:
                pass
            con_thieu = sorted(need_employees - set(employee_names))
            if con_thieu:
                # Nhan vien rieng phia ETC khong co trong dim_nhanvien (vd DNH00087, Sale01...).
                try:
                    for code, name in _tra_ten_theo_lo(
                            "SELECT code, dmscode, name FROM dmssx_nhanvien WHERE code IN ({ph}) OR dmscode IN ({ph})",
                            con_thieu, ("code", "dmscode")).items():
                        employee_names.setdefault(code, name)
                except sqlite3.OperationalError:
                    pass
        for row in rows:
            for code_key, name_keys, target_key, kind in _MA_CAN_TEN:
                code = _can_gan_ten(row, code_key, name_keys)
                name = (product_names if kind == "product" else employee_names).get(code) if code else None
                if name:
                    row[target_key] = name
    except Exception as exc:  # buoc bo sung ten khong duoc lam hong cau tra loi
        _write_log({"ts": dt.datetime.now().isoformat(), "status": "warn",
                    "sql": "<gan ten cho ma>", "error": str(exc)[:300]})
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
    lookback_months: cua so nhin lai de tinh doanh thu "tung mua" (mac dinh 6 thang), tinh LUI DUNG
    N THANG TU as_of (23/09 lui 6 thang = 23/03), khong phai moc dau thang lich - giong
    DATEADD(month,-N,...) cua checker S69c.
    San pham mua nhieu nhat dung ky RIENG 12 thang (ky_san_pham), khong phai ky nhin lai.
    Sap xep theo doanh thu ky truoc GIAM DAN - khach mat nhieu tien nhat len dau."""
    as_of_date = (as_of_date or latest_data_date())[:10]
    silent_days = max(1, min(int(silent_days or 60), 720))
    lookback_months = max(1, min(int(lookback_months or 6), 24))
    limit = max(1, min(int(limit or 50), 200))

    as_of = dt.date.fromisoformat(as_of_date)
    cutoff = (as_of - dt.timedelta(days=silent_days)).isoformat()
    # 23/09/2026 (UAT v21): ky nhin lai truoc day la _month_add(...)+'-01', tuc moc DAU THANG LICH
    # (01/04 khi hoi ngay 23/09), trong khi checker S69c dung DATEADD(month,-6,GETDATE()) = 23/03.
    # Chenh dung phan doanh thu 23-31/03 nen hang loat khach ra so thap hon checker. Do lai tren kho:
    # 10/10 khach khop tuyet doi checker voi moc 23/03, 7/10 khop so chatbot cu voi moc 01/04.
    date_from = _lui_thang_giu_ngay(as_of_date, lookback_months)
    # San pham mua nhieu nhat dung ky RIENG, RONG HON - checker lay 12 thang tinh tu dau thang
    # as_of (DATEADD(month,-12,@MonthStart)). Dung chung ky 6 thang voi doanh thu thi top SKU doi
    # han: ca BDI00361 doanh thu giong het checker (5,5 trieu) ma san pham van khac.
    item_from = f"{_month_add(as_of_date[:7], -12)}-01"

    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    scope_sql += emp_sql
    scope_params += emp_params

    def _base_ban_hang(tu: str, den: str):
        """Nguon ban hang da ep scope cho mot khoang ngay. Tach ra vi doanh thu va san pham dung
        HAI ky khac nhau - truoc day dung chung mot base nen khong tach duoc."""
        cac_phan, tham_so = [], []
        if scope_channel != "ETC":
            join_o = _otc_area_join("v", scope_area_code)
            cac_phan.append(
                f"SELECT v.customer_code, v.doc_date, v.item_code, v.amount9 FROM vhoadon_otc v {join_o} "
                f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
            tham_so.append((tu, den) + scope_params)
        if scope_channel != "OTC":
            join_e = _etc_area_join("v", scope_area_code)
            cac_phan.append(
                f"SELECT v.customer_code, v.doc_date, v.item_code, v.amount9 FROM vhoadon_etc v {join_e} "
                f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
            tham_so.append((tu, den) + scope_params)
        return (" UNION ALL ".join(cac_phan),
                tuple(p for pp in tham_so for p in pp))

    base_sql, base_params_moi = _base_ban_hang(date_from, as_of_date)
    if not base_sql:
        return {"error": "Khong co kenh nao kha dung voi pham vi tai khoan."}
    item_base_sql, item_base_params = _base_ban_hang(item_from, as_of_date)
    sql = f"""WITH base AS ({base_sql}), silent AS (
                SELECT customer_code, MAX(doc_date) lan_mua_cuoi,
                       SUM(amount9) doanh_thu_ky_nhin_lai,
                       COUNT(DISTINCT substr(doc_date,1,7)) so_thang_co_mua
                FROM base
                GROUP BY customer_code
                HAVING MAX(doc_date) <= ? AND SUM(amount9) > 0
              )
              SELECT *, COUNT(*) OVER() total_count
              FROM silent
              ORDER BY doanh_thu_ky_nhin_lai DESC, customer_code
              LIMIT ?"""
    base_params = base_params_moi
    params = base_params + (cutoff, limit)
    rows = _q(sql, params)

    names = _customer_names([r["customer_code"] for r in rows])
    # San pham mua nhieu nhat chi la thong tin bo sung. Thieu danh muc/ma SKU KHONG duoc
    # lam roi khach khoi ket qua V21: chinh tap khach im lang moi la tap can doi soat.
    favourite_items = {}
    returned_codes = [r["customer_code"] for r in rows]
    if returned_codes:
        ph = ",".join(["?"] * len(returned_codes))
        item_rows = _q(
            f"""WITH base AS ({item_base_sql})
                SELECT customer_code,item_code,SUM(amount9) revenue
                FROM base
                WHERE customer_code IN ({ph})
                  AND item_code IS NOT NULL AND TRIM(item_code)<>''
                GROUP BY customer_code,item_code
                HAVING SUM(amount9)>0
                ORDER BY customer_code,revenue DESC,item_code""",
            item_base_params + tuple(returned_codes),
        )
        for item in item_rows:
            favourite_items.setdefault(item["customer_code"], {
                "item_code": item["item_code"],
                # Ky RIENG, khong phai ky nhin lai cua doanh thu - ten truong phai noi ro dieu do.
                "ky": {"tu": item_from, "den": as_of_date},
                "revenue_trong_ky_san_pham": _f(item["revenue"]),
            })
        item_codes = [v["item_code"] for v in favourite_items.values()]
        item_names = {}
        if item_codes:
            item_ph = ",".join(["?"] * len(item_codes))
            try:
                item_names = {r["code"]: r["name"] for r in _q(
                    f"SELECT code,name FROM brv_sanpham WHERE code IN ({item_ph})",
                    tuple(item_codes),
                )}
            except sqlite3.OperationalError:
                # Fixture/kho cu co the chua co danh muc SP. Day la truong bo sung,
                # khong phai ly do loai ca khach hang khoi danh sach.
                item_names = {}
        for value in favourite_items.values():
            value["item_name"] = item_names.get(value["item_code"])
            value["product_name_status"] = (
                "available" if value["item_name"] else "not_available"
            )

    # 13/09/2026 (V21/S69b): "ky nhin lai" cu la 6 thang tinh den HOM NAY, nen khach ngung tu lau chi
    # con vai thang co mua trong do - lech han voi checker (6 thang TRUOC LAN MUA CUOI cua chinh khach).
    # Tra ca hai, ghi ro dinh nghia. Lich su lay ca phan da nen nen khong bi cat nhu #sales 12 thang.
    lich_su_khach = _lich_su_thang_cua_khach(returned_codes, as_of_date[:7], scope_area_code,
                                             scope_channel, scope_employee_code)

    def _truoc_khi_ngung(ma, lan_cuoi):
        thang = lich_su_khach.get(ma) or {}
        if not thang:
            return None
        den = str(lan_cuoi)[:7]
        tu = _month_add(den, -5)
        trong_ky = {ym: rev for ym, rev in thang.items() if tu <= ym <= den and rev}
        return {
            "tu_thang": tu, "den_thang": den,
            "doanh_thu": sum(trong_ky.values()),
            "so_thang_co_mua": len(trong_ky),
            "trung_binh_thang": (sum(trong_ky.values()) / len(trong_ky)) if trong_ky else None,
        }

    out = []
    for r in rows:
        last = str(r["lan_mua_cuoi"])[:10]
        silent_for = (as_of - dt.date.fromisoformat(last)).days
        favourite = favourite_items.get(r["customer_code"])
        out.append({
            "customer_code": r["customer_code"],
            "customer_name": names.get(r["customer_code"], "(khong co trong danh muc khach hang)"),
            "lan_mua_cuoi": last,
            "so_ngay_im_lang": silent_for,
            "nhom_im_lang": (">=180_ngay" if silent_for >= 180 else
                              "90_179_ngay" if silent_for >= 90 else
                              "60_89_ngay" if silent_for >= 60 else
                              "duoi_60_ngay"),
            "doanh_thu_ky_nhin_lai": _f(r["doanh_thu_ky_nhin_lai"]),
            "so_thang_co_mua": int(r["so_thang_co_mua"] or 0),
            "sau_thang_truoc_khi_ngung": _truoc_khi_ngung(r["customer_code"], last),
            "san_pham_mua_nhieu_nhat": favourite or {
                "status": "not_available",
                "reason": "Khong co ma san pham co doanh thu duong trong ky nhin lai.",
            },
        })

    total_count = int(rows[0]["total_count"] or 0) if rows else 0
    returned_count = len(out)
    result = {
        "as_of": as_of_date, "nguong_im_lang_ngay": silent_days,
        "ky_nhin_lai": {"tu": date_from, "den": as_of_date},
        "ky_san_pham": {"tu": item_from, "den": as_of_date},
        "so_khach": total_count,
        "total_count": total_count,
        "returned_count": returned_count,
        "truncated": total_count > returned_count,
        "not_shown_count": max(0, total_count - returned_count),
        "khach_im_lang": out,
        "ghi_chu": ("HAI con so doanh thu KHAC NHAU, phai goi dung ten khi tra loi: "
                     "doanh_thu_ky_nhin_lai = tong trong ky nhin lai CO DINH (ky_nhin_lai.tu -> den, "
                     "tinh den hom nay); sau_thang_truoc_khi_ngung = 6 thang lich tinh den THANG MUA "
                     "CUOI cua chinh khach do (dung khi hoi 'truoc khi ngung mua ho mua bao nhieu'). "
                     "Danh sach khach im lang duoc loc theo ky nhin lai co dinh, nen khach im lang lau "
                     "hon ky do co the khong xuat hien. "
                     "san_pham_mua_nhieu_nhat tinh tren ky_san_pham (12 thang), KHAC ky_nhin_lai cua "
                     "doanh thu - khi neu san pham PHAI ghi ro ky do, dung mac dinh nguoi doc hieu la "
                     "cung ky voi cot doanh thu."),
        "data_as_of": latest_data_date(),
    }
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac KHONG duoc hien thi."
    return result


def customer_attrition_risk(month: str = None, lookback_months: int = 12,
                            limit: int = 200, scope_area_code: str = None,
                            scope_channel: str = None,
                            scope_employee_code: str = None) -> dict:
    """KHACH LON NGUNG MUA / GIAM MUA MANH / KEO DAI CHU KY MUA - ba tin hieu trong MOT bang,
    dung dung dinh nghia checker S88. Dung cho cau M22 'khach lon nao ngung mua, giam mua hoac keo
    dai chu ky mua so voi lich su'.

    KHAC customers_silent (chi bat mot ve: da im lang >= N ngay) va KHAC customer_movement (chi so
    thang nay voi thang lien truoc, khong co chu ky mua). Cau M22 hoi CA BA ve; tra loi chi mot ve
    la CHUA DAT.

    Chi danh gia nua tren cua tap khach co doanh thu cua so duong (Revenue12M >= median), dung nghia
    "khach lon" cua checker M22. Median duoc tinh SAU khi ep scope vung/kenh/nhan vien.

    Ba tin hieu:
      NGUNG_MUA        Cur=0 va co mua it nhat 2/3 thang truoc.
      NGUNG_MUA_DA_LAU Cur=0 va ca 3 thang truoc cung =0, chi con doanh thu xa hon trong cua so.
      GIAM_MUA         Cur>0 nhung < 60% binh quan cac thang co ban ghi trong baseline 3 thang.
      KEO_DAI_CHU_KY   So ngay im lang > 2 lan khoang cach mua trung binh cua CHINH khach do.

    Nguong chu ky la dong theo tung khach (AvgGapDays) chu khong phai mot moc cung - moc cung 45 ngay
    tung lam ve thu ba ra 0 dong. AvgGapDays chi tinh khi khach co tu 3 ngay mua tro len, duoi muc do
    chu ky chua co nghia."""
    earliest, latest = _revenue_data_month_range()
    if not earliest or not latest:
        return {"error": "Kho chua co hoa don de phan tich rui ro mat khach."}
    used_default_month = not month
    complete_month = _latest_complete_revenue_month()
    # Mac dinh lay thang TRON gan nhat. Neu lay thang dang chay dang do (MTD), moi khach chua kip
    # dat don dau thang deu bi gan nhan "ngung mua"/"giam mua" gia. Day la bay da duoc ghi nhan khi
    # ra soat M16, khong duoc lap lai o day.
    month = ((complete_month if used_default_month else month) or latest)[:7]
    lookback_months = max(4, min(int(lookback_months or 12), 24))
    limit = max(1, min(int(limit or 200), 200))

    window_from = max(earliest, _month_add(month, -(lookback_months - 1)))
    date_from, _ = _month_bounds(window_from)
    cur_start, cur_end = _month_bounds(month)
    prior_start, _ = _month_bounds(_month_add(month, -3))
    prior_end = (dt.date.fromisoformat(cur_start) - dt.timedelta(days=1)).isoformat()
    prior_month_bounds = [_month_bounds(_month_add(month, offset)) for offset in (-3, -2, -1)]
    data_day = str(latest_data_date())[:10]
    as_of_date = min(data_day, cur_end)
    as_of = dt.date.fromisoformat(as_of_date)
    ky_chua_tron = month > complete_month

    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    scope_sql += emp_sql
    scope_params += emp_params

    parts, part_params = [], []
    if scope_channel != "ETC":
        join_o = _otc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.customer_code, v.doc_date, v.amount9 FROM vhoadon_otc v {join_o} "
                     f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, cur_end) + scope_params)
    if scope_channel != "OTC":
        join_e = _etc_area_join("v", scope_area_code)
        parts.append(f"SELECT v.customer_code, v.doc_date, v.amount9 FROM vhoadon_etc v {join_e} "
                     f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        part_params.append((date_from, cur_end) + scope_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung voi pham vi tai khoan."}

    base_sql = " UNION ALL ".join(parts)
    rows = _q(
        f"""WITH base AS ({base_sql})
            SELECT customer_code,
                   SUM(amount9) rev_window,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN amount9 ELSE 0 END) cur_revenue,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN amount9 ELSE 0 END) prior_m1_revenue,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN amount9 ELSE 0 END) prior_m2_revenue,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN amount9 ELSE 0 END) prior_m3_revenue,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN 1 ELSE 0 END) prior_m1_rows,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN 1 ELSE 0 END) prior_m2_rows,
                   SUM(CASE WHEN doc_date>=? AND doc_date<=? THEN 1 ELSE 0 END) prior_m3_rows,
                   MAX(doc_date) last_buy, MIN(doc_date) first_buy,
                   COUNT(DISTINCT substr(doc_date,1,10)) buy_days
            FROM base
            GROUP BY customer_code
            HAVING SUM(amount9)>0""",
        tuple(p for pp in part_params for p in pp)
        + (cur_start, cur_end)
        + tuple(value for bounds in prior_month_bounds for value in bounds)
        + tuple(value for bounds in prior_month_bounds for value in bounds),
    )

    large_customer_threshold = median([_f(r["rev_window"]) for r in rows]) if rows else None
    detail = []
    for r in rows:
        rev_window = _f(r["rev_window"])
        if large_customer_threshold is None or rev_window < large_customer_threshold:
            continue
        cur = _f(r["cur_revenue"])
        observed_prior_months = [
            _f(r[f"prior_m{i}_revenue"])
            for i in range(1, 4)
            if int(r[f"prior_m{i}_rows"] or 0) > 0
        ]
        prior3m = sum(observed_prior_months)
        active_prior3_months = sum(value > 0 for value in observed_prior_months)
        baseline = (sum(observed_prior_months) / len(observed_prior_months)
                    if observed_prior_months else None)
        last_buy = str(r["last_buy"])[:10]
        first_buy = str(r["first_buy"])[:10]
        buy_days = int(r["buy_days"] or 0)
        silent_days = (as_of - dt.date.fromisoformat(last_buy)).days
        avg_gap = None
        if buy_days >= 3:
            span = (dt.date.fromisoformat(last_buy) - dt.date.fromisoformat(first_buy)).days
            avg_gap = span / (buy_days - 1) if span > 0 else None
        # Thu tu nhanh giu dung CASE cua S88: mot khach chi mang mot tin hieu, khong dem trung.
        if cur <= 0 and active_prior3_months >= 2:
            signal = "NGUNG_MUA"
        elif cur <= 0 and active_prior3_months == 0:
            signal = "NGUNG_MUA_DA_LAU"
        elif cur > 0 and baseline and cur < 0.6 * baseline:
            signal = "GIAM_MUA"
        elif cur > 0 and avg_gap is not None and silent_days > 2 * avg_gap:
            signal = "KEO_DAI_CHU_KY"
        else:
            continue
        detail.append({
            "customer_code": r["customer_code"],
            "tin_hieu": signal,
            "doanh_thu_cua_so": rev_window,
            "doanh_thu_ky": cur,
            "doanh_thu_3_thang_truoc": prior3m,
            "so_thang_co_mua_trong_3_thang_truoc": active_prior3_months,
            "muc_trung_binh_thang_baseline": baseline,
            "pct_so_baseline": (round((cur - baseline) / baseline * 100, 1)
                                if baseline else None),
            "lan_mua_cuoi": last_buy,
            "so_ngay_im_lang": silent_days,
            "so_ngay_co_mua": buy_days,
            "khoang_cach_mua_trung_binh_ngay": round(avg_gap, 1) if avg_gap is not None else None,
            "chu_ky_chua_do_duoc": avg_gap is None,
        })

    detail.sort(key=lambda x: (-x["doanh_thu_cua_so"], x["customer_code"]))
    # Tong hop tinh TRUOC khi cat top-N: neu dem sau khi cat thi so khach tung nhom se thay doi
    # theo limit, dung bai hoc da ghi o C31.
    counts, revenue_at_risk = {}, {}
    for row in detail:
        counts[row["tin_hieu"]] = counts.get(row["tin_hieu"], 0) + 1
        revenue_at_risk[row["tin_hieu"]] = (
            revenue_at_risk.get(row["tin_hieu"], 0.0) + row["doanh_thu_cua_so"])
    total_count = len(detail)
    shown = detail[:limit]

    names = _customer_names([row["customer_code"] for row in shown])
    for row in shown:
        row["customer_name"] = names.get(row["customer_code"],
                                         "(khong co trong danh muc khach hang)")

    gioi_han = [
        "Ba nhom tren la tin hieu canh bao tu hoa don, KHONG phai ket luan khach da bo hang. "
        "Phai lien he xac minh truoc khi bao cao mat khach.",
        "Khong co du lieu nguyen nhan (doi thu, gia, cong no, ton kho khach) trong tap nay; "
        "khong duoc suy dien ly do khach giam mua.",
    ]
    if ky_chua_tron:
        gioi_han.insert(0, (
            f"Thang {month} CHUA TRON (du lieu den {as_of_date}). Nhan NGUNG_MUA va GIAM_MUA o ky "
            "chua tron co the la bao dong gia do khach chua kip dat don trong thang. Chi ket luan "
            f"tren thang tron gan nhat ({complete_month})."))
    if window_from > _month_add(month, -(lookback_months - 1)):
        gioi_han.append(
            f"Kho chi co hoa don tu {window_from}; khach ngung mua truoc moc do khong xuat hien.")

    result = {
        "ky": month,
        "ky_chua_tron": ky_chua_tron,
        "thang_tron_gan_nhat": complete_month,
        "cua_so_nhin_lai": {"tu": window_from, "den": month},
        "baseline_3_thang": {"tu": prior_start[:7], "den": prior_end[:7]},
        "as_of": as_of_date,
        "dinh_nghia_tin_hieu": {
            "NGUNG_MUA": "Ky nay khong mua, co mua it nhat 2/3 thang truoc.",
            "NGUNG_MUA_DA_LAU": "Ky nay va ca 3 thang truoc deu khong mua, chi con doanh thu xa hon.",
            "GIAM_MUA": "Ky nay co mua nhung duoi 60% binh quan cac thang co ban ghi trong baseline 3 thang.",
            "KEO_DAI_CHU_KY": "So ngay im lang > 2 lan khoang cach mua trung binh cua chinh khach do "
                              "(va ky nay van co mua).",
        },
        "dinh_nghia_khach_lon": "Doanh thu cua so >= trung vi cua cac khach co doanh thu duong trong cung pham vi.",
        "nguong_doanh_thu_khach_lon": large_customer_threshold,
        "so_khach_co_doanh_thu_duong": len(rows),
        "so_khach_rui_ro": total_count,
        "phan_bo_tin_hieu": counts,
        "doanh_thu_cua_so_theo_tin_hieu": revenue_at_risk,
        "total_count": total_count,
        "returned_count": len(shown),
        "truncated": total_count > len(shown),
        "not_shown_count": max(0, total_count - len(shown)),
        "khach_rui_ro": shown,
        "gioi_han": gioi_han,
        "data_as_of": data_day,
    }
    if scope_channel:
        result["channel_scope"] = (
            f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac KHONG duoc hien thi.")
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


def _latest_complete_revenue_month() -> str:
    """Thang tron gan nhat theo ngay du lieu that, khong theo dong ho may chu."""
    data_day = dt.date.fromisoformat(str(latest_data_date())[:10])
    if data_day.day < _last_day_of_month(data_day.year, data_day.month):
        return _month_add(data_day.strftime("%Y-%m"), -1)
    return data_day.strftime("%Y-%m")


def _product_month_pair_summary(current_month: str, previous_month: str,
                                scope_area_code: str = None,
                                scope_channel: str = None,
                                scope_employee_code: str = None) -> dict:
    """Phan ra bien dong doanh thu theo TAP SAN PHAM giu nguyen/mo moi/ngung ban.

    C20 hoi dong thoi "cung tap khach hang" va "cung tap san pham". Ban cu chi tra truc khach
    hang, de model dung mot bang khach hang tra loi cho ca hai ve. Ham nay tinh doc lap tren SKU,
    va tra san phep doi soat de hai phan ra deu cong lai dung tong doanh thu.
    """
    previous_from, previous_to = _month_bounds(previous_month)
    current_from, current_to = _month_bounds(current_month)
    if previous_from < _detail_cutoff():
        return {
            "status": "source_gap",
            "current_month": current_month,
            "previous_month": previous_month,
            "note": ("Chi tiet SKU cua ky truoc nam ngoai cua so luu chi tiet 12 thang; "
                     "khong the tinh LFL theo san pham tu tong doanh thu da nen."),
        }

    scope_sql, scope_params = _scope_clause(scope_area_code)
    employee_sql, employee_params = _employee_scope_clause(
        scope_employee_code, "v", as_of=current_to
    )
    suffix = scope_sql + employee_sql
    suffix_params = scope_params + employee_params
    parts, groups = [], []
    if scope_channel != "ETC":
        join = _otc_area_join("v", scope_area_code)
        parts.append(
            "SELECT substr(v.doc_date,1,7) month,v.item_code,SUM(v.amount9) revenue "
            f"FROM vhoadon_otc v {join} WHERE v.doc_date BETWEEN ? AND ? "
            f"AND v.item_code IS NOT NULL AND TRIM(v.item_code)<>''{suffix} "
            "GROUP BY substr(v.doc_date,1,7),v.item_code"
        )
        groups.append((previous_from, current_to) + suffix_params)
    if scope_channel != "OTC":
        join = _etc_area_join("v", scope_area_code)
        parts.append(
            "SELECT substr(v.doc_date,1,7) month,v.item_code,SUM(v.amount9) revenue "
            f"FROM vhoadon_etc v {join} WHERE v.doc_date BETWEEN ? AND ? "
            f"AND v.item_code IS NOT NULL AND TRIM(v.item_code)<>''{suffix} "
            "GROUP BY substr(v.doc_date,1,7),v.item_code"
        )
        groups.append((previous_from, current_to) + suffix_params)
    if not parts:
        return {"status": "no_data", "current_month": current_month,
                "previous_month": previous_month}

    rows = _q(
        "WITH x AS (" + " UNION ALL ".join(parts) + ") "
        "SELECT month,item_code,SUM(revenue) revenue FROM x GROUP BY month,item_code",
        tuple(value for group in groups for value in group),
    )
    by_item = {}
    for row in rows:
        by_item.setdefault(row["item_code"], {})[row["month"]] = _f(row["revenue"])

    lfl, current_only, previous_only, non_positive = [], [], [], []
    for item_code, periods in by_item.items():
        current = periods.get(current_month, 0.0)
        previous = periods.get(previous_month, 0.0)
        item = {"item_code": item_code, "current_revenue": current,
                "previous_revenue": previous, "delta": current - previous}
        if current > 0 and previous > 0:
            lfl.append(item)
        elif current > 0 and previous <= 0:
            current_only.append(item)
        elif previous > 0 and current <= 0:
            previous_only.append(item)
        elif current or previous:
            non_positive.append(item)

    def _sum(rows_to_sum, key):
        return sum(row[key] for row in rows_to_sum)

    total_current = sum(_f(row["revenue"]) for row in rows if row["month"] == current_month)
    total_previous = sum(_f(row["revenue"]) for row in rows if row["month"] == previous_month)
    lfl_current = _sum(lfl, "current_revenue")
    lfl_previous = _sum(lfl, "previous_revenue")
    lfl_delta = lfl_current - lfl_previous
    current_only_delta = _sum(current_only, "delta")
    previous_only_delta = _sum(previous_only, "delta")
    non_positive_delta = _sum(non_positive, "delta")
    reconciled = lfl_delta + current_only_delta + previous_only_delta + non_positive_delta
    total_delta = total_current - total_previous
    return {
        "status": "ok",
        "current_month": current_month,
        "previous_month": previous_month,
        "like_for_like_product_count": len(lfl),
        "like_for_like_current_revenue": lfl_current,
        "like_for_like_previous_revenue": lfl_previous,
        "like_for_like_delta": lfl_delta,
        "like_for_like_pct": (lfl_delta / lfl_previous * 100) if lfl_previous else None,
        "current_only_product_count": len(current_only),
        "current_only_product_delta": current_only_delta,
        "previous_only_product_count": len(previous_only),
        "previous_only_product_delta": previous_only_delta,
        "non_positive_adjustment_delta": non_positive_delta,
        "total_current_revenue": total_current,
        "total_previous_revenue": total_previous,
        "total_revenue_delta": total_delta,
        "reconciled_delta": reconciled,
        "reconciliation_gap": reconciled - total_delta,
        "definition": ("LFL san pham = SKU co doanh thu duong o ca hai thang. SKU chi co o thang "
                       "hien tai/ky truoc duoc tach rieng; khong tu goi la san pham moi/ngung kinh "
                       "doanh neu chua co lich su va danh muc trang thai san pham."),
    }


def _isnc_cohort_retention(cohort_from: str, month_to: str, ages: list, latest: str,
                           latest_complete: str, months_by_customer: dict,
                           scope_area_code: str = None, scope_employee_code: str = None) -> dict:
    """Cohort theo co IsNC (khach mo moi cua Bravo) - CUNG nguon voi so 'khach moi' cua C29/M24.

    24/09/2026 (UAT C30, cham 21/09): cohort hoa don cua tool nay cho 08/2026 = 324 khach, trong khi
    C29/M24 bao 627 khach moi (is_nc=1, snapshot 31/08) - nguoi cham coi 627 la dung va ghi C30 "lech
    so khach moi". Ca hai deu dung theo dinh nghia rieng: 324 la khach LAN DAU co hoa don trong kho
    tu 06/2022, 627 la khach Bravo gan co mo moi trong ky. Tra ca hai, cung ten nguon, de model khong
    goi hai con so khac nhau cung la "khach mo moi". Loc giong het C29 (bo nhan vien trung, loc vung
    theo nv.area_code, doi QLV theo dung snapshot).
    """
    try:
        rows = _q("SELECT substr(save_date,1,7) ym, MAX(save_date) d FROM fact_tonghopkhachhang "
                  "WHERE substr(save_date,1,7) BETWEEN ? AND ? GROUP BY ym", (cohort_from, month_to))
    except Exception as exc:
        return {"status": "khong_co_nguon", "ly_do": f"Kho chua co fact_tonghopkhachhang: {exc}"}
    snaps = {r["ym"]: r["d"] for r in rows if r["d"]}
    if not snaps:
        return {"status": "khong_co_nguon",
                "ly_do": f"Kho khong co snapshot KPI khach nao tu {cohort_from} den {month_to}."}

    cohorts = []
    for ym in sorted(snaps):
        snap = snaps[ym]
        sql = ("SELECT DISTINCT f.customer_code FROM fact_tonghopkhachhang f "
               "LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
               f"WHERE f.save_date=? AND f.is_nc=1 AND {_not_duplicate_sql('nv')}")
        params = [snap]
        if scope_area_code:
            sql += " AND nv.area_code=?"
            params.append(scope_area_code)
        if scope_employee_code:
            allowed = [scope_employee_code] + [
                t["employee_code"] for t in _team_of_qlv(scope_employee_code, snap)]
            sql += f" AND f.employee_code IN ({','.join(['?'] * len(allowed))})"
            params.extend(allowed)
        khach = {r["customer_code"] for r in _q(sql, tuple(params)) if r["customer_code"]}
        retention = []
        for age in ages:
            target_month = _month_add(ym, age)
            complete = target_month <= latest_complete
            retained = sum(1 for c in khach if target_month in months_by_customer.get(c, ()))
            muc = {"age_month": age, "target_month": target_month,
                   "retained_customers": retained if complete else None,
                   "retention_pct": (retained / len(khach) * 100) if complete and khach else None,
                   "ky_da_du": complete}
            if not complete and target_month == latest and khach:
                muc["retained_customers_tam_tinh"] = retained
                muc["retention_pct_tam_tinh"] = retained / len(khach) * 100
            retention.append(muc)
        cohorts.append({"cohort_month": ym, "snapshot_date": snap,
                        "cohort_customers": len(khach), "retention": retention})

    thieu = [m for m in _months_between(cohort_from, month_to) if m not in snaps]
    return {
        "status": "ok",
        "definition": ("Cohort = khach co is_nc=1 trong snapshot KPI cuoi thang (FACT_TongHopKhachHang, "
                       "chi kenh OTC) - CUNG so 'khach moi' cua C29/M24. retained = co hoa don o dung "
                       "thang tuoi."),
        "cohorts": cohorts,
        "thang_khong_co_snapshot": thieu,
        "gioi_han": (f"Kho chi co snapshot KPI khach tu {min(snaps)}; cac thang truoc do KHONG co co "
                     "IsNC nen khong dung duoc dinh nghia nay cho tuoi 3/6/12 thang. Tuoi dai phai doc "
                     "o bang cohort hoa don (dinh nghia khac, noi ro khi dung)." if thieu else None),
    }


def _months_between(month_from: str, month_to: str) -> list:
    thang, ket_qua = month_from, []
    while thang <= month_to:
        ket_qua.append(thang)
        thang = _month_add(thang, 1)
    return ket_qua


def customer_cohort_retention(month_to: str = None, months_back: int = 6,
                              age_months: list = None, group_by: str = "overall",
                              scope_area_code: str = None, scope_channel: str = None,
                              scope_employee_code: str = None) -> dict:
    """Cohort theo THANG MUA DAU TIEN QUAN SAT DUOC, tinh giu chan o tuoi 1/3/6/12 thang.

    Khong gan nhan cohort nay bang IsNC cua Bravo: y nghia cohort o day duoc dinh nghia minh bach
    tu hoa don. Neu kho khong co lich su truoc thang mua dau tien thi day chi la "first observed",
    khong duoc khang dinh la lan mua dau tien trong doi khach.

    10/09/2026 - SUA LOI "da du ky" xet theo THANG TRON gan nhat (_latest_complete_revenue_month()),
    khong con dung thang cua ngay du lieu tho (latest_data_date()[:7]). Truoc day, neu thang hien tai
    moi la MTD (vd moi co 10/30 ngay), moi cohort co target_month roi dung vao thang do bi tinh "da du
    ky" va retention bi danh gia THAP GIA TAO (khach chua kip mua trong vai ngay dau thang bi coi la
    khong giu chan) - phat hien qua vi du thuc te: cohort 06/2026 tuoi 3 thang bao 10,7% trong khi
    cohort lien ke 04-05/2026 bao 42,9%/33,8%, chenh lech bat thuong cung 1 nguyen nhan.
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
    # 10/09/2026 - SUA LOI: truoc day dung `latest` (thang cua NGAY du lieu moi nhat, vd '2026-09' tu
    # ngay 2026-09-10) de xet "da du ky" cho tung tuoi cohort - nhung thang hien tai co the moi la MTD
    # (10/30 ngay), khien retention cua BAT KY cohort nao co target_month roi vao thang chua tron bi
    # danh gia THAP GIA TAO (khach chua kip mua trong vai ngay dau thang bi tinh la "khong giu chan").
    # Da bat qua vi du thuc te: cohort 06/2026 tuoi 3 thang (target=09/2026) bao 10,7% trong khi cohort
    # lien ke 04/2026, 05/2026 bao 42,9%/33,8% - chenh lech bat thuong do cung 1 nguyen nhan. Dung thang
    # TRON gan nhat (giong customer_movement da lam) de xet "da du ky", khong dung thang cua ngay du
    # lieu tho.
    latest_complete = _latest_complete_revenue_month()
    # 18/09/2026 (cau M23 "ty le giu chan sau 3/6 thang"): voi months_back mac dinh 6, cua so cohort
    # bat dau o thang_to - 5, trong khi mot cohort phai lui it nhat 6 thang truoc thang TRON gan nhat
    # moi cham duoc tuoi 6. Ket qua: cot tuoi 6 rong 100% - khong phai vi thieu du lieu (kho co lich
    # su tu 2022) ma vi cua so tu chon sai. Do that: months_back=6 -> 0/6 cohort co so o tuoi 6;
    # months_back=12 -> 5/12 cohort co so. Model doc duoc mot cot toan None roi ket luan "chua du ky"
    # cho tat ca, hoac bo luon ve nay cua cau hoi.
    # Noi rong cua so vua du de it nhat 3 cohort cham duoc tuoi lon nhat duoc hoi.
    cohort_from_da_hoi = cohort_from
    tuoi_lon_nhat = max(ages) if ages else 0
    if latest_complete and tuoi_lon_nhat:
        can_lui_den = _month_add(latest_complete, -(tuoi_lon_nhat + 2))
        if can_lui_den < cohort_from:
            cohort_from = max(earliest, can_lui_den)
            if _month_diff(cohort_from, month_to) + 1 > 18:      # chan payload phinh
                cohort_from = _month_add(month_to, -17)
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
        # Khach xuat hien o dung bien trai cua kho co the da mua truoc do. Van tra so lieu
        # quan sat de doi chieu, nhung gan nhan fail-closed de model khong goi day la cohort
        # khach MOI hay dung lam mau so retention nghiep vu chinh thuc.
        cohort_is_left_censored = cohort_month == earliest
        retention = []
        for age in ages:
            target_month = _month_add(cohort_month, age)
            complete = target_month <= latest_complete
            retained = len(b["retained"][age]) if complete else None
            muc = {
                "age_month": age, "target_month": target_month,
                "retained_customers": retained,
                "retention_pct": (retained / size * 100) if complete and size else None,
                "ky_da_du": complete,
            }
            # 24/09/2026 (UAT C30): cohort 08/2026 tuoi 1 roi vao thang 09 dang chay nen tra None -
            # dung, nhung nguoi chay ghi "thang 8 da ket thuc ma khong co % giu chan 1 thang".
            # Checker S19 lay LastMonth = MAX(thang co hoa don), tuc tinh luon thang chua tron.
            # Van giu retention_pct=None (khong tron ky thi khong ket luan), them so TAM TINH co nhan.
            if not complete and target_month == latest and size:
                muc["retained_customers_tam_tinh"] = len(b["retained"][age])
                muc["retention_pct_tam_tinh"] = len(b["retained"][age]) / size * 100
            retention.append(muc)
        cohorts.append({"cohort_month": cohort_month, "group": group,
                        "cohort_customers": size,
                        "cohort_is_left_censored": cohort_is_left_censored,
                        "valid_new_customer_cohort": not cohort_is_left_censored,
                        "retention": retention})

    left_censored_months = sorted({
        c["cohort_month"] for c in cohorts if c["cohort_is_left_censored"]
    })
    # IsNC chi co o kenh OTC va chi co mot so tong cho ca pham vi - khong tach duoc theo kenh/vung
    # cua cohort. group_by khac overall thi khong ghep, tranh dat hai con so khac truc canh nhau.
    cohort_isnc, doi_chieu = None, None
    if group_by == "overall" and (scope_channel or "").upper() != "ETC":
        months_by_customer = {code: c["months"] for code, c in by_customer.items()}
        cohort_isnc = _isnc_cohort_retention(
            cohort_from, month_to, ages, latest, latest_complete, months_by_customer,
            scope_area_code=scope_area_code, scope_employee_code=scope_employee_code)
        if cohort_isnc.get("status") == "ok":
            isnc_theo_thang = {c["cohort_month"]: c["cohort_customers"] for c in cohort_isnc["cohorts"]}
            hoa_don_theo_thang = {c["cohort_month"]: c["cohort_customers"] for c in cohorts}
            doi_chieu = [{"month": m, "khach_mo_moi_isnc": isnc_theo_thang[m],
                          "khach_lan_dau_co_hoa_don_trong_kho": hoa_don_theo_thang.get(m, 0)}
                         for m in sorted(isnc_theo_thang)]
    tam_tinh_den = latest_data_date() if latest != latest_complete else None
    return {
        "definition": "Cohort = thang co hoa don dau tien QUAN SAT DUOC trong kho; retained = co hoa don o dung thang tuoi.",
        "cohort_theo_isnc": cohort_isnc,
        "doi_chieu_hai_dinh_nghia_khach_moi": doi_chieu,
        "ghi_chu_hai_dinh_nghia": (
            "cohorts dem khach LAN DAU co hoa don trong kho (lich su tu pham_vi_du_lieu_co_that.tu_thang); "
            "cohort_theo_isnc dem khach Bravo gan co mo moi (is_nc=1) - chinh la so 'khach moi' cua "
            "C29/M24. Khach mo moi theo IsNC co the da tung mua truoc day nen so IsNC LON HON. Khi cau "
            "hoi noi 'thang mo moi' phai neu so IsNC cho cac thang co snapshot va noi ro tuoi dai "
            "(3/6/12) chi do duoc bang dinh nghia hoa don." if doi_chieu else None),
        "tam_tinh_thang_chua_tron": (
            f"Tuoi co target_month = {latest} (thang dang chay, du lieu den {tam_tinh_den}) co them "
            "retention_pct_tam_tinh: CHI la so tam tinh den ngay du lieu, khong phai ty le chot; "
            "retention_pct cua o do van None." if tam_tinh_den else None),
        "cohort_from": cohort_from, "cohort_to": month_to, "group_by": group_by,
        "cohort_from_da_mo_rong": cohort_from < cohort_from_da_hoi,
        "ly_do_mo_rong_cua_so": (
            f"months_back duoc hoi chi lui den {cohort_from_da_hoi}, nhung mot cohort phai lui it nhat "
            f"{tuoi_lon_nhat} thang truoc thang tron gan nhat ({latest_complete}) moi cham duoc tuoi "
            f"{tuoi_lon_nhat}. Da noi rong ve {cohort_from} de cot tuoi lon nhat co so that thay vi "
            "rong hoan toan." if cohort_from < cohort_from_da_hoi else None),
        "ages": ages, "cohorts": cohorts,
        "left_censored_cohort_months": left_censored_months,
        "valid_cohort_count": sum(1 for c in cohorts if c["valid_new_customer_cohort"]),
        "pham_vi_du_lieu_co_that": {"tu_thang": earliest, "den_thang": latest},
        "latest_complete_month": latest_complete,
        "canh_bao": ("Cohort o dung tu_thang cua kho bi left-censored: chi la lan dau QUAN SAT DUOC, "
                      "khong duoc goi la khach moi trong doi hay dung de ket luan retention chinh thuc. "
                      "Cac cohort khac van can DNH chot dinh nghia khach moi. Cac tuoi co target_month "
                      "sau latest_complete_month duoc tra None ('ky_da_du': false), khong coi la 0% giu "
                      "chan - day KHONG PHAI loi, ma la thang do CHUA TRON (vd thang hien tai moi co du "
                      "lieu vai ngay dau) nen chua the danh gia cong bang."),
        # 13/09/2026 (M23/S67): cohort dem tu HOA DON nen mac dinh gom CA OTC va ETC, con S67
        # dem tu FACT_TongHopKhachHang chi phu doi OTC. Cung MB thang 8/2026: 5.087 khach neu
        # gom ETC, 4.859 neu chi OTC (khop tuyet doi tung ma voi S67). Ghi ro de khong so nham.
        "pham_vi_kenh": (scope_channel.upper() if scope_channel else "OTC+ETC"),
        "luu_y_doi_chieu": ("Con so nay dem tu hoa don. Checker S67 dem tu FACT_TongHopKhachHang, "
                            "chi phu doi OTC - muon so voi S67 phai truyen scope_channel='OTC'."),
        "data_as_of": latest_data_date(),
    }


def _la_vi_tri_trong(name: str) -> bool:
    """Dong danh muc khong phai mot con nguoi ma la O TRONG dang cho tuyen ("Trong QLV MK3").

    Phai nhan ra bang TEN. Co is_duplicate KHONG phan biet duoc: TM24060301 co CA HAI dong deu
    is_duplicate=1 (mot la o trong, mot la nguoi that), con TM24100101 thi chinh dong o trong moi
    mang is_duplicate=1. Xem them _EMPLOYEE_TIER_POSITIONS va employee_directory()."""
    return _fold_question(name or "").strip().startswith("trong ")


def _nv_theo_dms(dms_ids: list) -> dict:
    """{DMSId: {'employee_code','employee_name'}} - hoa don ghi theo DMSId, bao cao can ma nhan vien.

    Hai bay da bat duoc ngay 18/09/2026 khi cham cau M24:
      1. Chi tra dim_nhanvien la BO SOT toan bo nhan vien ETC/SX - ho chi ton tai trong
         dmssx_nhanvien (vd DNH00087, DNH00268, Sale02...). Do that tren kho: 26/194 dong
         by_employee cua thang 8 ra ma tran khong co ten, om 35 khach moi + 186 khach tai kich hoat.
         _resolve_employee_identity() da tra bang nay tu 20/07/2026; o day thi chua.
      2. Khi mot DMSId ung voi nhieu dong danh muc, ban cu chi ORDER BY is_duplicate DESC roi lay
         dong dau - va cham vao dung O TRONG: TM24060301 ra "Trong QLV MK3" thay vi Truong Ho Minh
         Luan, TM24100101 ra "Trong QLV" thay vi Nguyen Ngoc Quoc Hung. Cong viec ban hang cua
         nguoi that bi gan cho mot cho ngoi chua co nguoi.
    """
    ids = [x for x in dict.fromkeys(dms_ids) if x]
    if not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 300):
        chunk = ids[i:i + 300]
        ph = ",".join(["?"] * len(chunk))
        ung_vien = {}
        for r in _q(f"SELECT dmsid, employee_code, name, is_duplicate FROM dim_nhanvien "
                    f"WHERE dmsid IN ({ph})", tuple(chunk)):
            ung_vien.setdefault(r["dmsid"], []).append(r)
        for dmsid, rows in ung_vien.items():
            # Nguoi that truoc o trong; trong so nguoi that thi giu uu tien is_duplicate=1 cu
            # (dong duoc danh dau trung thuong moi la nguoi dang lam viec - xem employee_directory).
            rows.sort(key=lambda r: (_la_vi_tri_trong(r["name"]),
                                     -(int(r["is_duplicate"] or 0)),
                                     str(r["employee_code"] or "")))
            out[dmsid] = {"employee_code": rows[0]["employee_code"], "employee_name": rows[0]["name"]}
        con_thieu = [x for x in chunk if x not in out]
        if con_thieu:
            ph2 = ",".join(["?"] * len(con_thieu))
            for r in _q(f"SELECT code, name FROM dmssx_nhanvien WHERE code IN ({ph2})",
                        tuple(con_thieu)):
                out.setdefault(r["code"], {"employee_code": r["code"], "employee_name": r["name"]})
    return out


def _lich_su_thang_cua_khach(codes: list, month_to: str, scope_area_code: str = None,
                             scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """{ma_khach: {'YYYY-MM': doanh_thu}} tren TOAN BO lich su kho (chi tiet 12 thang + bang nen cu
    hon), theo dung pham vi tai khoan.

    13/09/2026 (V15/S61b, V23/S68b): customer_movement chi nhin trong cua so history_months nen
    (1) khach tung mua truoc cua so bi goi la "khach mo moi" - do tren Bravo doi MBKV2 thang 8/2026:
    tool goi 32 khach la moi, that ra chi 22 khach lan dau mua, 10 khach da mua tu 2023-2025;
    (2) moc "truoc khi ngung" va so thang nghi cung bi cat theo cua so. Ham nay lay ca phan ngoai
    cua so de hai viec do dung.
    """
    if not codes:
        return {}
    _, date_to = _month_bounds(month_to)
    summary_to = min(month_to, _month_add(_detail_cutoff()[:7], -1))
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    lich_su = {}
    codes = list(dict.fromkeys(codes))
    for i in range(0, len(codes), 300):
        chunk = codes[i:i + 300]
        ph = ",".join(["?"] * len(chunk))
        parts, part_params = [], []
        for channel, table, join_fn in (("OTC", "vhoadon_otc", _otc_area_join),
                                        ("ETC", "vhoadon_etc", _etc_area_join)):
            if scope_channel and scope_channel != channel:
                continue
            join = join_fn("v", scope_area_code)
            parts.append(f"SELECT v.customer_code code, substr(v.doc_date,1,7) m, SUM(v.amount9) rev "
                         f"FROM {table} v {join} WHERE v.customer_code IN ({ph}) AND v.doc_date<=?"
                         f"{scope_sql}{emp_sql} GROUP BY v.customer_code, substr(v.doc_date,1,7)")
            part_params.append(tuple(chunk) + (date_to,) + scope_params + emp_params)
        for channel in ("OTC", "ETC"):
            if scope_channel and scope_channel != channel:
                continue
            m_scope, m_params = _monthly_summary_scope_clause(scope_area_code, channel)
            m_emp, m_emp_params = _employee_scope_clause(scope_employee_code, "m", as_of=date_to)
            parts.append("SELECT m.customer_code code, m.year_month m, SUM(m.revenue) rev "
                         "FROM monthly_customer_summary m "
                         f"WHERE m.channel=? AND m.customer_code IN ({ph}) AND m.year_month<=?"
                         f"{m_scope}{m_emp} GROUP BY m.customer_code, m.year_month")
            part_params.append((channel,) + tuple(chunk) + (summary_to,) + m_params + m_emp_params)
        if not parts:
            return {}
        sql = "SELECT code, m, SUM(rev) rev FROM (" + " UNION ALL ".join(parts) + ") GROUP BY code, m"
        params = tuple(p for group in part_params for p in group)
        for r in _q(sql, params):
            lich_su.setdefault(r["code"], {})[r["m"]] = _f(r["rev"])
    return lich_su


def _chuoi_truoc_khi_ngung(thang_doanh_thu: dict, month: str, prev_month: str) -> dict:
    """Moc mua cuoi truoc khi ngung + chuoi thang lien tiep co mua ngay truoc do (dung cho V23/S68b)."""
    co_mua = sorted(ym for ym, rev in thang_doanh_thu.items() if ym < prev_month and rev > 0)
    if not co_mua:
        return {"last_active_month": None, "streak_months": 0, "streak_revenue": 0.0,
                "streak_avg": None, "gap_months": None, "first_purchase_month": None}
    last_active = co_mua[-1]
    chuoi = [last_active]
    while True:
        truoc = _month_add(chuoi[0], -1)
        if thang_doanh_thu.get(truoc, 0.0) > 0:
            chuoi.insert(0, truoc)
        else:
            break
    tong = sum(thang_doanh_thu[ym] for ym in chuoi)
    gap = 0
    cursor = _month_add(last_active, 1)
    while cursor <= prev_month:
        gap += 1
        cursor = _month_add(cursor, 1)
    return {"last_active_month": last_active, "streak_months": len(chuoi), "streak_revenue": tong,
            "streak_avg": tong / len(chuoi), "gap_months": gap,
            "first_purchase_month": min(thang_doanh_thu)}


def customer_movement(month: str = None, history_months: int = 12,
                      movement_filter: str = "all", limit: int = 50,
                      scope_area_code: str = None, scope_channel: str = None,
                      scope_employee_code: str = None,
                      classification_basis: str = "full_history") -> dict:
    """Luon khach giua thang hien tai va thang truoc: moi quan sat/tai kich hoat/ngung/tang/giam."""
    earliest, latest = _revenue_data_month_range()
    if not earliest or not latest:
        return {"error": "Kho chua co hoa don de phan tich luong khach."}
    used_default_month = not month
    # Cau C20 khong ghi ky: dung thang TRON gan nhat de hai ve cung do dai. Ban cu mac dinh thang
    # du lieu moi nhat, nen ngay 08/09 co the am tham so 8 ngay T9 voi ca thang T8. Model co luc tu
    # lui ve T8, co luc khong, lam cung mot cau UAT thay doi ky giua cac lan chay.
    month = ((_latest_complete_revenue_month() if used_default_month else month) or latest)[:7]
    if classification_basis not in {"full_history", "observed_window_24m"}:
        return {"error": "classification_basis khong hop le."}
    observed_window = classification_basis == "observed_window_24m"
    # C31/S90 dinh nghia #sales la cua so 24 thang: "lan dau quan sat" chi co nghia la chua
    # xuat hien trong cua so nay. V15/V23 can lich su day du de khong goi nham khach cu la moi,
    # nen chi C31 duoc call_template ep sang basis nay; khong dung chung mot nhan cho hai bai toan.
    history_months = 24 if observed_window else max(2, min(int(history_months or 6), 24))
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
        if r["month"] == month:
            thang_nay = c.setdefault("employees_this_month", {})
            thang_nay[r["employee_code"]] = thang_nay.get(r["employee_code"], 0.0) + _f(r["revenue"])

    names = _customer_names(list(customers))
    # 13/09/2026 (V15/S61b): khach "thang nay co mua, thang truoc khong" phai tra lich su DAY DU de
    # biet ho lan dau mua hay quay lai - cua so history_months khong du de ket luan.
    ung_vien = [ma for ma, c in customers.items()
                if c["months"].get(month, {"revenue": 0.0})["revenue"] > 0
                and c["months"].get(prev_month, {"revenue": 0.0})["revenue"] <= 0]
    lich_su_day_du = (
        _lich_su_thang_cua_khach(ung_vien, prev_month, scope_area_code, scope_channel,
                                 scope_employee_code)
        if not observed_window else {}
    )
    detail = []
    for code, c in customers.items():
        cur = c["months"].get(month, {"revenue": 0.0, "orders": 0})
        prev = c["months"].get(prev_month, {"revenue": 0.0, "orders": 0})
        earlier = sum(v["revenue"] for k, v in c["months"].items() if k < prev_month)
        truoc_day = lich_su_day_du.get(code) or {}
        thang_mua_dau = min(truoc_day) if truoc_day else None
        # S90/C31 dung dung dau so cua checker: chi CURRENT = 0 moi la ngung mua. Dong am (tra
        # hang/dieu chinh) la DECLINING, khong duoc day vao doanh thu mat do khach ngung mua.
        cur_absent = cur["revenue"] == 0 if observed_window else cur["revenue"] <= 0
        prev_absent = prev["revenue"] == 0 if observed_window else prev["revenue"] <= 0
        if cur["revenue"] > 0 and prev_absent:
            # Lan dau mua that su (ke ca phan ngoai cua so) moi duoc goi la khach moi.
            movement = "REACTIVATED" if ((truoc_day or earlier > 0) if not observed_window
                                          else earlier > 0) else "NEW_OR_FIRST_OBSERVED"
        elif cur_absent and prev["revenue"] > 0:
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
        # V15/S61b: nguoi "mo" khach la nguoi ban cho khach do trong CHINH thang dang xet (ban nhieu
        # nhat), khong phai nguoi ban nhieu nhat ca cua so 12 thang.
        emp_thang = c.get("employees_this_month") or {}
        # Hoa nhau thi lay ma nho hon de ket qua on dinh va trung voi checker S61b.
        emp_thang_nay = min(emp_thang, key=lambda ma: (-emp_thang[ma], str(ma))) if emp_thang else None
        # 13/09/2026 (V23/S68b): "truoc khi ngung" tinh tren CHUOI THANG LIEN TIEP co mua ngay truoc
        # ky nghi, lay ca phan ngoai cua so hien thi - truoc day chia trung binh cho moi thang co mua
        # trong cua so nen lech voi checker.
        chuoi = _chuoi_truoc_khi_ngung(truoc_day, month, prev_month) if truoc_day else None
        reactivation_fields = {
            "last_active_month_before_reactivation": chuoi["last_active_month"] if chuoi else None,
            "inactive_months_before_reactivation": (chuoi["gap_months"] or None) if chuoi else None,
            "pre_stop_streak_month_count": chuoi["streak_months"] if chuoi else 0,
            "pre_stop_streak_revenue": chuoi["streak_revenue"] if chuoi else None,
            "pre_stop_average_monthly_revenue": chuoi["streak_avg"] if chuoi else None,
            "recovery_delta_vs_pre_stop_average": (
                cur["revenue"] - chuoi["streak_avg"] if chuoi and chuoi["streak_avg"] else None),
            "recovery_pct_vs_pre_stop_average": (
                cur["revenue"] / chuoi["streak_avg"] * 100 if chuoi and chuoi["streak_avg"] else None),
        } if movement == "REACTIVATED" else {}
        detail.append({
            "customer_code": code,
            "customer_name": names.get(code, "(khong co trong danh muc khach hang)"),
            "movement": movement,
            "current_revenue": cur["revenue"], "previous_revenue": prev["revenue"],
            "delta": cur["revenue"] - prev["revenue"],
            "current_orders": cur["orders"], "previous_orders": prev["orders"],
            "has_repeat_order_current": cur["orders"] >= 2,
            "earlier_revenue_in_window": earlier,
            "employee_code": emp, "employee_code_this_month": emp_thang_nay,
            "channels": sorted(c["channels"]), "areas": sorted(c["areas"]),
            "first_purchase_month": (
                min(c["months"]) if observed_window and cur["revenue"] > 0 and not prev["revenue"]
                else thang_mua_dau or (month if cur["revenue"] > 0 and not prev["revenue"] else None)
            ),
            **reactivation_fields,
        })
    detail.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # 07/09/2026 (C31 UAT): limit chi de gioi han danh sach khach de model khong bi cat payload.
    # Neu tinh "khach moi/tai kich hoat bu duoc bao nhieu" SAU khi cat top-N, mot khach lon co the
    # lam ket luan ve ca doi dao chieu. Tong ket phai tinh tren TOAN BO tap khach truoc, con top-N
    # chi dung de giai thich cac dong dang hien thi.
    def _movement_summary(rows):
        counts = {}
        for row in rows:
            counts[row["movement"]] = counts.get(row["movement"], 0) + 1
        new_revenue = sum(row["current_revenue"] for row in rows
                          if row["movement"] == "NEW_OR_FIRST_OBSERVED")
        reactivated_revenue = sum(row["current_revenue"] for row in rows
                                  if row["movement"] == "REACTIVATED")
        added = new_revenue + reactivated_revenue
        lost = sum(row["previous_revenue"] for row in rows if row["movement"] == "STOPPED")
        lfl_rows = [row for row in rows if row["movement"] in {"GROWING", "DECLINING", "UNCHANGED"}]
        lfl_current = sum(row["current_revenue"] for row in lfl_rows)
        lfl_previous = sum(row["previous_revenue"] for row in lfl_rows)
        lfl_delta = lfl_current - lfl_previous
        total_current = sum(row["current_revenue"] for row in rows)
        total_previous = sum(row["previous_revenue"] for row in rows)
        new_delta = sum(row["delta"] for row in rows
                        if row["movement"] == "NEW_OR_FIRST_OBSERVED")
        reactivated_delta = sum(row["delta"] for row in rows
                                if row["movement"] == "REACTIVATED")
        stopped_delta = sum(row["delta"] for row in rows if row["movement"] == "STOPPED")
        classified_delta = new_delta + reactivated_delta + stopped_delta + lfl_delta
        # Neu co doanh thu am do hang tra, "doanh thu them - doanh thu mat" khong bang delta.
        # Tach ro phan dieu chinh nay thay vi de mot khoan du "chua phan loai" nhu C20 UAT.
        non_positive_adjustment = classified_delta - (added + lfl_delta - lost)
        return {
            "customer_count_considered": len(rows),
            "counts": counts,
            "new_or_first_observed_revenue": new_revenue,
            "reactivated_revenue": reactivated_revenue,
            "added_revenue": added,
            "lost_previous_revenue": lost,
            "net_offset": added - lost,
            # Khong lam tron som: S90/C31 doi chieu ty le voi SQL tra day du phan thap phan.
            # Tang hien thi co the tu chon 1-2 chu so, nhung payload khong duoc mat chenh lech.
            "compensation_pct_of_lost_revenue": added / lost * 100 if lost else None,
            "like_for_like_customer_count": len(lfl_rows),
            "like_for_like_current_revenue": lfl_current,
            "like_for_like_previous_revenue": lfl_previous,
            "like_for_like_delta": lfl_delta,
            "like_for_like_pct": (lfl_delta / lfl_previous * 100) if lfl_previous else None,
            "total_current_revenue": total_current,
            "total_previous_revenue": total_previous,
            "total_revenue_delta": total_current - total_previous,
            "new_or_first_observed_delta": new_delta,
            "reactivated_delta": reactivated_delta,
            "stopped_delta": stopped_delta,
            "non_positive_revenue_adjustment": non_positive_adjustment,
            "reconciled_delta": classified_delta,
        }

    summary_all = _movement_summary(detail)
    # 13/09/2026 (V15/S61b): so khach theo tung TDV truoc day model phai tu dem tren danh sach da cat
    # top-N va chi co ma DMS - nen lech han voi checker. Tinh san o day tren TOAN BO tap khach.
    nv = _nv_theo_dms([row.get("employee_code_this_month") for row in detail])
    theo_nv = {}
    for row in detail:
        dms = row.get("employee_code_this_month")
        khoa = (nv.get(dms, {}).get("employee_code") or dms or "(khong xac dinh)")
        muc = theo_nv.setdefault(khoa, {
            "employee_code": khoa, "employee_name": nv.get(dms, {}).get("employee_name"),
            "dms_id": dms, "khach_moi": 0, "khach_moi_co_mua_lai": 0, "doanh_thu_khach_moi": 0.0,
            "khach_tai_kich_hoat": 0, "doanh_thu_tai_kich_hoat": 0.0, "khach_ngung_mua": 0,
            "doanh_thu_mat_do_ngung": 0.0,
        })
        if row["movement"] == "NEW_OR_FIRST_OBSERVED":
            muc["khach_moi"] += 1
            muc["doanh_thu_khach_moi"] += row["current_revenue"]
            muc["khach_moi_co_mua_lai"] += int(bool(row.get("has_repeat_order_current")))
        elif row["movement"] == "REACTIVATED":
            muc["khach_tai_kich_hoat"] += 1
            muc["doanh_thu_tai_kich_hoat"] += row["current_revenue"]
        elif row["movement"] == "STOPPED":
            muc["khach_ngung_mua"] += 1
            muc["doanh_thu_mat_do_ngung"] += row["previous_revenue"]
    for muc in theo_nv.values():
        muc["ty_le_mua_lai_khach_moi_pct"] = (
            muc["khach_moi_co_mua_lai"] / muc["khach_moi"] * 100 if muc["khach_moi"] else None)
    by_employee = sorted(theo_nv.values(),
                         key=lambda x: (-x["khach_moi"], -x["khach_tai_kich_hoat"], x["employee_code"]))
    returned_detail = detail[:limit]
    product_summary = _product_month_pair_summary(
        month, prev_month, scope_area_code, scope_channel, scope_employee_code
    )
    return {
        "month": month, "previous_month": prev_month, "history_from": start,
        "classification_basis": classification_basis,
        "period_selection": ("THANG_TRON_GAN_NHAT" if used_default_month else "THANG_DUOC_CHI_DINH"),
        "summary_all_customers": summary_all,
        "by_employee": by_employee,
        "summary_all_products": product_summary,
        "summary_on_returned_top_rows": _movement_summary(returned_detail),
        "customers": returned_detail,
        "canh_bao": (("NEW_OR_FIRST_OBSERVED = lan dau xuat hien trong cua so 24 thang tu "
                      f"{start} den {month}, dung dinh nghia C31/S90. Khong duoc goi la khach moi trong doi; "
                      "khach co mua trong cua so truoc thang nay la REACTIVATED. "
                      if observed_window else
                      "NEW_OR_FIRST_OBSERVED = lan dau mua tren TOAN BO lich su kho trong pham vi tai "
                      "khoan (13/09/2026), khong con phu thuoc history_months; first_purchase_month cua "
                      "tung dong la bang chung. Khach tung mua truoc do luon la REACTIVATED. ") +
                      "pre_stop_* lay ca phan ngoai cua so hien thi: pre_stop_average_monthly_revenue la "
                      "trung binh cua CHUOI THANG LIEN TIEP co mua ngay truoc ky nghi. "
                      "So khach theo tung TDV BAT BUOC lay o by_employee (tinh tren toan bo tap khach, "
                      "quy chu khach cho nguoi ban nhieu nhat trong chinh thang do) - KHONG duoc tu dem "
                      "tren danh sach customers da cat top-N. "
                      "Khi hoi tong doanh thu them/mat hoac ty le bu doanh thu, BAT BUOC dung "
                      "summary_all_customers; summary_on_returned_top_rows chi mo ta cac dong top-N "
                      "dang hien thi, khong dai dien cho toan bo tap khach."),
        "data_as_of": latest_data_date(),
    }


_THU = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")


def _otc_daily_series(date_from: str, date_to: str, scope_area_code: str = None,
                      scope_employee_code: str = None) -> dict:
    """Doanh thu hoa don OTC tung ngay LICH trong [date_from, date_to], cung bo loc vung/doi voi
    revenue_by_channel. Ngay khong co hoa don van co dong (revenue=0) de liet ke ngay khong phat sinh."""
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    join_o = _otc_area_join("v", scope_area_code)
    ngay_sau = str(dt.date.fromisoformat(date_to) + dt.timedelta(days=1))
    rows = _q(f"SELECT substr(v.doc_date,1,10) d, COALESCE(SUM(v.amount9),0) rev, "
              f"COUNT(DISTINCT v.stt) hd FROM vhoadon_otc v {join_o} "
              f"WHERE v.doc_date>=? AND v.doc_date<?{scope_sql}{emp_sql} GROUP BY substr(v.doc_date,1,10)",
              (date_from, ngay_sau) + tuple(scope_params) + tuple(emp_params))
    return {r["d"]: (_f(r["rev"]), int(r["hd"] or 0)) for r in rows}


def _nhip_theo_ngay(fdate: str, as_of_date: str, scope_target: float, scope_area_code: str = None,
                    scope_employee_code: str = None) -> dict:
    """V03: doanh so tung ngay/tuan so voi nhip can thiet, liet ke ngay khong phat sinh.

    11/09/2026: truoc day V03 di vao tool nay nhung chi co so TONG THANG, khong co ngay/tuan; con
    get_employee_daily_kpi thi bo han T7/CN - ma T7 la ngay ban nhieu nhat (22,3% doanh thu OTC
    T8/2026 tren Bravo). Tinh DU moi ngay lich. DNH chua chot nhip theo ngay lich hay ngay lam viec,
    nen tra CA HAI nhip, khong tu chon."""
    y, m = int(fdate[:4]), int(fdate[5:7])
    month_days = _last_day_of_month(y, m)
    thang_dau, thang_cuoi = dt.date(y, m, 1), dt.date(y, m, month_days)
    den = dt.date.fromisoformat(str(as_of_date or latest_data_date())[:10])
    den = max(thang_dau, min(den, thang_cuoi, dt.date.today()))
    theo_ngay = _otc_daily_series(str(thang_dau), str(den), scope_area_code, scope_employee_code)
    # Ngay ban hang = T2-T7: CN khong phat sinh hoa don OTC tren Bravo (T8/2026: 0 dong).
    ngay_ban_trong_thang = sum(1 for i in range(month_days)
                               if (thang_dau + dt.timedelta(days=i)).weekday() < 6)
    nhip_lich = scope_target / month_days if scope_target else None
    nhip_ban = scope_target / ngay_ban_trong_thang if scope_target else None
    daily, weekly, tuan = [], [], {}
    d = thang_dau
    while d <= den:
        rev, hd = theo_ngay.get(str(d), (0.0, 0))
        daily.append({
            "date": str(d), "thu": _THU[d.weekday()], "revenue": rev, "invoices": hd,
            "khong_phat_sinh": rev == 0 and hd == 0,
            "dang_chay_do": d == dt.date.today(),
            "pct_nhip_ngay_lich": rev / nhip_lich * 100 if nhip_lich else None,
            "pct_nhip_ngay_ban_t2_t7": (rev / nhip_ban * 100 if nhip_ban and d.weekday() < 6 else None),
        })
        dau_tuan = d - dt.timedelta(days=d.weekday())
        w = tuan.setdefault(dau_tuan, {"tu": str(max(dau_tuan, thang_dau)), "den": str(d),
                                       "revenue": 0.0, "invoices": 0, "so_ngay": 0,
                                       "so_ngay_khong_phat_sinh": 0})
        w["den"] = str(d)
        w["revenue"] += rev
        w["invoices"] += hd
        w["so_ngay"] += 1
        w["so_ngay_khong_phat_sinh"] += int(rev == 0 and hd == 0)
        d += dt.timedelta(days=1)
    for w in tuan.values():
        w["nhip_can_thiet_ngay_lich"] = nhip_lich * w["so_ngay"] if nhip_lich else None
        weekly.append(w)
    return {
        "tu_ngay": str(thang_dau), "den_ngay": str(den),
        "scope_target": scope_target or None,
        "nhip_can_thiet_moi_ngay_lich": nhip_lich,
        "nhip_can_thiet_moi_ngay_ban_t2_t7": nhip_ban,
        "so_ngay_ban_t2_t7_trong_thang": ngay_ban_trong_thang,
        "daily": daily, "weekly": weekly,
        "ngay_khong_phat_sinh_t2_t7": [x["date"] for x in daily
                                      if x["khong_phat_sinh"] and x["thu"] != "CN"
                                      and not x["dang_chay_do"]],
        "chu_nhat_khong_phat_sinh": [x["date"] for x in daily if x["khong_phat_sinh"] and x["thu"] == "CN"],
        "tong_doanh_thu_hoa_don": sum(x["revenue"] for x in daily),
        "definition": ("Doanh thu hoa don OTC theo NGAY LICH (gom T7, CN), cung pham vi vung/doi. KHAC "
                       "nguon voi actual (snapshot KPI) nen tong co the lech do moc chot. DNH CHUA CHOT "
                       "nhip theo ngay lich hay ngay ban hang: trinh bay ca hai, khong tu chon. Ngay "
                       "dang_chay_do moi luy ke mot phan ngay, khong ket luan la thap."),
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
    # Nhip theo ngay dung target CA pham vi (truoc limit), khong phai target cua cac dong dang hien.
    scope_target = sum(r["target"] for r in result_rows)
    try:
        nhip = _nhip_theo_ngay(fdate, as_of_date, scope_target, scope_area_code, scope_employee_code)
    except KhongXacDinhDuocDoi as exc:
        nhip = {"error": str(exc)}
    return {
        "as_of": fdate, "group_by": group_by, "rows": result_rows[:limit],
        # Tra san phep dem tren TOAN BO tap du lieu truoc limit. Model khong duoc dem bang tay tren
        # danh sach bi cat (UAT tung bao 3/7 nguoi >=80% trong khi ket qua dung la 2/7).
        "threshold_summary": threshold_summary,
        "nhip_theo_ngay": nhip,
        "definition": ("linear_run_rate = doanh so luy ke / so ngay lich da qua * so ngay trong thang. "
                       "Day CHI la ngoai suy tuyen tinh, KHONG phai forecast/xac suat dat."),
        "thresholds": {"65_70": "cong thuong theo vai tro", "80": "dat KPI",
                       "100": "dat chi tieu", "120": "vuot 120%"},
        "pham_vi_kenh": "OTC",
    }


def cross_sell_opportunities(as_of_date: str = None, lookback_months: int = 3,
                             min_together_orders: int = 5, pair_limit: int = 20,
                             opportunity_limit: int = 100,
                             scope_area_code: str = None, scope_channel: str = None,
                             scope_employee_code: str = None) -> dict:
    """S74: cap SKU co KHACH chung va khach da mua A nhung chua mua B trong cua so nhin lai.

    ``min_together_orders`` giu ten tham so cu de tuong thich API, nhung tu 07/09/2026 no co nghia
    la SO KHACH CHUNG toi thieu (khong phai so don). SQL checker S74 dem distinct CustomerCode; dem
    don da tung lam ket qua cap SKU lech va thoi phong cap mua lap lai nhieu lan.
    """
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
        ", buyers AS (SELECT DISTINCT customer_code,item_code FROM lines "
        "WHERE customer_code IS NOT NULL AND TRIM(customer_code)<>''), "
        "pair_stats AS (SELECT a.item_code item_a,b.item_code item_b,COUNT(DISTINCT a.customer_code) shared_customers "
        "FROM buyers a JOIN buyers b ON b.customer_code=a.customer_code AND b.item_code>a.item_code "
        "GROUP BY a.item_code,b.item_code HAVING COUNT(DISTINCT a.customer_code)>=?), "
        "counts AS (SELECT item_code,COUNT(DISTINCT customer_code) buyers FROM buyers GROUP BY item_code) "
        "SELECT p.item_a,p.item_b,p.shared_customers,ca.buyers buyers_a,cb.buyers buyers_b,"
        "100.0*p.shared_customers/NULLIF(ca.buyers,0) attach_rate_pct,"
        "ca.buyers-p.shared_customers candidates_buy_a_only "
        "FROM pair_stats p JOIN counts ca ON ca.item_code=p.item_a JOIN counts cb ON cb.item_code=p.item_b "
        "ORDER BY p.shared_customers DESC,p.item_a,p.item_b LIMIT ?",
        params + (max(1, int(min_together_orders or 5)), pair_limit))

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
                                      "shared_customers": int(p["shared_customers"]),
                                      "attach_rate_pct": _f(p["attach_rate_pct"]),
                                      "revenue_on_pair_items": customer_revenue.get(customer, 0.0)})
    opportunities.sort(key=lambda r: (-r["shared_customers"], -r["revenue_on_pair_items"]))
    customer_names = _customer_names([r["customer_code"] for r in opportunities[:opportunity_limit]])
    for r in opportunities[:opportunity_limit]:
        r["customer_name"] = customer_names.get(r["customer_code"], "(khong co trong danh muc khach hang)")
    return {
        "date_from": date_from, "date_to": as_of_date,
        "pairs": [{**p, "item_a_name": names.get(p["item_a"], p["item_a"]),
                    "item_b_name": names.get(p["item_b"], p["item_b"])} for p in pair_rows],
        "opportunities": opportunities[:opportunity_limit],
        "definition": ("Cap manh = it nhat min_shared_customers KHACH da tung mua ca hai SKU trong cua so. "
                       "Attach rate = khach chung / nguoi mua SKU A. Co hoi = khach da mua mot SKU cua cap "
                       "nhung chua mua SKU con lai; day la goi y tu dong mua kem, KHONG phai ket luan nhu cau."),
        "min_shared_customers": max(1, int(min_together_orders or 5)),
        "threshold_status": "DE_XUAT_CHO_DNH_CHOT",
        "canh_bao": "Chi tiet SKU/hoa don chi duoc giu khoang 12 thang; lookback da bi gioi han toi da 12.",
        "data_as_of": latest_data_date(),
    }


def product_first_observed_performance(as_of_date: str = None, lookback_months: int = 24,
                                       limit: int = 100, scope_area_code: str = None,
                                       scope_channel: str = None,
                                       scope_employee_code: str = None) -> dict:
    """C34/M34: hieu suat SKU theo moc dau tien quan sat duoc trong 24 thang tron.

    C34 can 12 thang truoc moc danh gia de phan biet SKU moi voi SKU da ban tu truoc cua so.
    Kho giu hoa don chi tiet tu 01/01/2024; neu chua dong bo lai du moc nay thi fail-closed.
    """
    as_of_date = (as_of_date or latest_data_date())[:10]
    # Cau C34 hoi toi tuoi 12 thang, nen bat buoc cua so 24 thang; khong cho AI rut xuong 12 thang.
    lookback_months = 24
    limit = max(1, min(int(limit or 100), 500))
    ay, am, ad = (int(x) for x in as_of_date.split("-"))
    latest_month = as_of_date[:7]
    complete_through_month = (
        latest_month if ad == _last_day_of_month(ay, am) else _month_add(latest_month, -1)
    )
    candidate_from = _month_add(complete_through_month, -(lookback_months - 1))
    ey, em = (int(x) for x in complete_through_month.split("-"))
    analysis_date_to = f"{complete_through_month}-{_last_day_of_month(ey, em):02d}"

    detail_starts = []
    for table in ("vhoadon_otc", "vhoadon_etc"):
        try:
            row = _q(f"SELECT MIN(doc_date) d FROM {table}")[0]
            if row.get("d"):
                detail_starts.append(str(row["d"])[:7])
        except sqlite3.OperationalError:
            continue
    detail_start = min(detail_starts) if detail_starts else None
    if not detail_start or detail_start > candidate_from:
        return {
            "mode": "product_first_observed", "as_of": as_of_date,
            "candidate_from": candidate_from, "complete_through_month": complete_through_month,
            "status": "HISTORY_INCOMPLETE", "products": [], "total_count": 0,
            "returned_count": 0, "history_source": "invoice_detail",
            "history_source_start": detail_start, "history_complete": False,
            "note": ("Lich su hoa don chi tiet chua du tu " + candidate_from +
                     "; chua the xac dinh SKU moi mot cach dung. "
                     "Can dong bo lai kho bang python backend/sync_warehouse.py --full."),
            "launch_date_source": "not_available", "sku_target_source": "not_available",
            "data_as_of": latest_data_date(),
        }

    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    parts, params = [], []
    if scope_channel != "ETC":
        join = _otc_area_join("v", scope_area_code)
        parts.append(
            "SELECT v.doc_date,v.item_code,v.customer_code,v.amount9 FROM vhoadon_otc v "
            f"{join} WHERE v.doc_date BETWEEN ? AND ? AND v.item_code IS NOT NULL "
            f"AND TRIM(v.item_code)<>''{suffix}"
        )
        params.extend((f"{candidate_from}-01", analysis_date_to) + suffix_params)
    if scope_channel != "OTC":
        join = _etc_area_join("v", scope_area_code)
        parts.append(
            "SELECT v.doc_date,v.item_code,v.customer_code,v.amount9 FROM vhoadon_etc v "
            f"{join} WHERE v.doc_date BETWEEN ? AND ? AND v.item_code IS NOT NULL "
            f"AND TRIM(v.item_code)<>''{suffix}"
        )
        params.extend((f"{candidate_from}-01", analysis_date_to) + suffix_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung."}

    monthly = _q(
        "WITH base AS (" + " UNION ALL ".join(parts) + ") "
        "SELECT substr(doc_date,1,7) month,item_code,"
        "COUNT(DISTINCT customer_code) customers,SUM(amount9) revenue "
        "FROM base GROUP BY substr(doc_date,1,7),item_code",
        tuple(params),
    )
    if not monthly:
        return {"mode": "product_first_observed", "products": [],
                "status": "NO_DATA_IN_SCOPE", "data_as_of": latest_data_date()}

    by_product = {}
    for row in monthly:
        by_product.setdefault(row["item_code"], {})[row["month"]] = row
    codes = list(by_product)
    product_names = {}
    if codes:
        ph = ",".join(["?"] * len(codes))
        try:
            product_names = {r["code"]: r["name"] for r in _q(
                f"SELECT code,name FROM brv_sanpham WHERE code IN ({ph})", tuple(codes)
            )}
        except sqlite3.OperationalError:
            product_names = {}

    products = []
    for code, months in by_product.items():
        first_observed = min(months)
        left_censored = first_observed == candidate_from
        age_results = []
        for age in (1, 3, 6, 12):
            target_month = _month_add(first_observed, age)
            complete = target_month <= complete_through_month
            row = months.get(target_month, {}) if complete else {}
            age_results.append({
                "age_month": age, "target_month": target_month,
                "period_complete": complete,
                "customers": int(row.get("customers") or 0) if complete else None,
                "revenue": _f(row.get("revenue")) if complete else None,
                "target_status": "not_available", "target_achievement_pct": None,
            })
        first_row = months[first_observed]
        ly_do_khong_dung = (["thang ghi nhan dau trung bien trai lich su"] if left_censored else [])
        products.append({
            "item_code": code, "item_name": product_names.get(code) or code,
            "first_observed_sale_month": first_observed,
            "first_observed_is_launch_date": False,
            "first_observed_is_left_censored": left_censored,
            "first_observed_month_complete": True,
            "months_of_history_before_first_sale": _month_diff(candidate_from, first_observed),
            "valid_for_launch_age_analysis": not left_censored,
            "ly_do_khong_dung_cho_phan_tich_tuoi": ly_do_khong_dung,
            "first_observed_customers": int(first_row.get("customers") or 0),
            "first_observed_revenue": _f(first_row.get("revenue")),
            "age_results": age_results,
        })
    products.sort(key=lambda r: (-r["first_observed_revenue"], r["item_code"]))
    total = len(products)
    returned = products[:limit]
    return {
        "mode": "product_first_observed", "as_of": as_of_date,
        "candidate_from": candidate_from, "history_boundary_month": candidate_from,
        "complete_through_month": complete_through_month,
        "history_source": "invoice_detail", "history_source_start": detail_start,
        "history_complete": True,
        "total_count": total, "returned_count": len(returned),
        "truncated": total > len(returned), "not_shown_count": max(0, total - len(returned)),
        "so_sku_thang_dau_chua_tron": 0,
        "so_sku_dung_cho_phan_tich_tuoi": sum(1 for r in products if r["valid_for_launch_age_analysis"]),
        "products": returned,
        "launch_date_source": "not_available", "sku_target_source": "not_available",
        "definition": ("first_observed_sale_month la thang ban dau tien QUAN SAT DUOC trong dung "
                       "pham vi tai khoan, KHONG phai ngay ra mat san pham."),
        "limitations": [
            "SKU o history_boundary_month bi left-censored va khong duoc dung de ket luan tuoi san pham.",
            "Kho chua co master launch date va target theo SKU; khong tinh % ke hoach.",
            "Thang hien tai chua tron duoc loai khoi cua so phan tich de doanh thu thang dau luon la thang tron.",
            "months_of_history_before_first_sale la so thang co du lieu TRUOC moc ghi nhan dau. So "
            "nay cang nho thi bang chung 'SKU moi' cang yeu - co the chi la SKU ban lai sau mot thoi gian nghi.",
        ],
        "answer_rule": (
            "Chi xep hang va so sanh cac dong co valid_for_launch_age_analysis=true. Cac dong con lai "
            "phai neu rieng kem ly_do_khong_dung_cho_phan_tich_tuoi, KHONG duoc dua vao bang so sanh "
            "doanh thu thang dau."),
        "data_as_of": latest_data_date(),
    }

def dual_channel_customer_summary(as_of_date: str = None, lookback_months: int = 6,
                                  limit: int = 100, scope_area_code: str = None,
                                  scope_channel: str = None,
                                  scope_employee_code: str = None) -> dict:
    """C26/S16: khach co hoa don o ca OTC va ETC trong cung thang.

    Chi cong doanh thu hoa don. Kho cong no khong co chieu kenh va lich su thang du de gan
    an toan cho tap khach mua cheo, nen phan cong no phai fail-closed thay vi tu noi bang ma KH.
    """
    if scope_channel:
        return {
            "status": "NOT_APPLICABLE_SINGLE_CHANNEL_SCOPE",
            "requested": "Khach mua dong thoi OTC va ETC",
            "channel_scope": str(scope_channel).upper(),
            "note": "Tai khoan chi duoc xem mot kenh nen khong the doi chieu tap mua cheo hai kenh.",
            "rows": [], "dual_customers": [], "data_as_of": latest_data_date(),
        }
    as_of_date = (as_of_date or latest_data_date())[:10]
    lookback_months = max(1, min(int(lookback_months or 6), 12))
    limit = max(1, min(int(limit or 100), 500))
    month_from = _month_add(as_of_date[:7], -(lookback_months - 1))
    date_from = f"{month_from}-01"
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    otc = (
        "SELECT substr(v.doc_date,1,7) month,v.customer_code,'OTC' channel,v.amount9 revenue "
        "FROM vhoadon_otc v " + _otc_area_join("v", scope_area_code) +
        f" WHERE v.doc_date BETWEEN ? AND ?{suffix}"
    )
    etc = (
        "SELECT substr(v.doc_date,1,7) month,v.customer_code,'ETC' channel,v.amount9 revenue "
        "FROM vhoadon_etc v " + _etc_area_join("v", scope_area_code) +
        f" WHERE v.doc_date BETWEEN ? AND ?{suffix}"
    )
    params = (date_from, as_of_date) + suffix_params + (date_from, as_of_date) + suffix_params
    per_customer = _q(
        "WITH lines AS (" + otc + " UNION ALL " + etc + "), c AS ("
        "SELECT month,customer_code,COUNT(DISTINCT channel) channels,"
        "SUM(CASE WHEN channel='OTC' THEN revenue ELSE 0 END) otc_revenue,"
        "SUM(CASE WHEN channel='ETC' THEN revenue ELSE 0 END) etc_revenue,SUM(revenue) revenue "
        "FROM lines WHERE customer_code IS NOT NULL AND TRIM(customer_code)<>'' "
        "GROUP BY month,customer_code) SELECT * FROM c ORDER BY month,customer_code",
        params,
    )
    monthly = {}
    dual_totals = {}
    for row in per_customer:
        ym = row["month"]
        bucket = monthly.setdefault(ym, {
            "month": ym, "total_customers": 0, "dual_channel_customers": 0,
            "total_revenue": 0.0, "dual_channel_revenue": 0.0,
        })
        revenue = _f(row.get("revenue"))
        bucket["total_customers"] += 1
        bucket["total_revenue"] += revenue
        if int(row.get("channels") or 0) == 2:
            bucket["dual_channel_customers"] += 1
            bucket["dual_channel_revenue"] += revenue
            customer = dual_totals.setdefault(row["customer_code"], {
                "customer_code": row["customer_code"], "months_bought_both": 0,
                "otc_revenue": 0.0, "etc_revenue": 0.0, "total_revenue": 0.0,
            })
            customer["months_bought_both"] += 1
            customer["otc_revenue"] += _f(row.get("otc_revenue"))
            customer["etc_revenue"] += _f(row.get("etc_revenue"))
            customer["total_revenue"] += revenue
    rows = []
    for ym in sorted(monthly):
        row = monthly[ym]
        row["dual_customer_share_pct"] = (
            row["dual_channel_customers"] / row["total_customers"] * 100
            if row["total_customers"] else None
        )
        row["dual_revenue_share_pct"] = (
            row["dual_channel_revenue"] / row["total_revenue"] * 100
            if row["total_revenue"] else None
        )
        rows.append(row)
    names = _customer_names(list(dual_totals)) if dual_totals else {}
    dual_customers = sorted(dual_totals.values(), key=lambda row: (
        -row["total_revenue"], row["customer_code"],
    ))
    for row in dual_customers:
        row["customer_name"] = names.get(row["customer_code"]) or row["customer_code"]
    return {
        "status": "PARTIAL_DEBT_SOURCE_GAP",
        "mode": "dual_channel", "period": {"from": date_from, "to": as_of_date},
        "rows": rows, "dual_customer_count_in_window": len(dual_customers),
        "dual_customers": dual_customers[:limit],
        "dual_customers_truncated": len(dual_customers) > limit,
        "definition": (
            "Khach mua cheo = cung customer_code co it nhat mot hoa don OTC va mot hoa don ETC "
            "trong CUNG thang. Doanh thu mua cheo la toan bo doanh thu OTC+ETC cua tap khach do."
        ),
        "debt_status": "not_available_for_dual_channel_customer_history",
        "debt_limitation": (
            "Nguon cong no hien khong co lich su thang va chieu kenh da xac nhan de gan an toan "
            "cho tap khach mua cheo; khong duoc tu noi/gop cong no bang ma khach."
        ),
        "data_as_of": latest_data_date(),
    }


def customer_revenue_tier_peer(as_of_date: str = None, lookback_months: int = 3,
                               limit: int = 200, scope_area_code: str = None,
                               scope_channel: str = None,
                               scope_employee_code: str = None) -> dict:
    """S89/M25-M26: benchmark noi bo theo kenh x mien x bac doanh thu NTILE(5)."""
    requested = dt.date.fromisoformat((as_of_date or latest_data_date())[:10])
    requested_month_end = _month_end(requested)
    end_date = requested if requested == requested_month_end else (
        dt.date(requested.year, requested.month, 1) - dt.timedelta(days=1)
    )
    end_month = end_date.strftime("%Y-%m")
    lookback_months = max(1, min(int(lookback_months or 3), 12))
    limit = max(1, min(int(limit or 200), 500))
    date_from = f"{_month_add(end_month, -(lookback_months - 1))}-01"
    date_to = end_date.isoformat()
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    parts, params = [], []
    if scope_channel != "ETC":
        parts.append(
            "SELECT 'OTC' channel,COALESCE(tp.area_code,'UNKNOWN') area_code,"
            "v.customer_code,v.item_code,COALESCE(p.group_code,'UNKNOWN') group_code,v.amount9 "
            "FROM vhoadon_otc v LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
            "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
            "LEFT JOIN brv_sanpham p ON p.code=v.item_code "
            f"WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}"
        )
        params.extend((date_from, date_to) + suffix_params)
    if scope_channel != "OTC":
        parts.append(
            "SELECT 'ETC' channel,COALESCE(tp.area_code,'UNKNOWN') area_code,"
            "v.customer_code,v.item_code,COALESCE(p.group_code,'UNKNOWN') group_code,v.amount9 "
            "FROM vhoadon_etc v LEFT JOIN dmssx_khachhang kh ON kh.code=v.customer_code "
            "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
            "LEFT JOIN brv_sanpham p ON p.code=v.item_code "
            f"WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}"
        )
        params.extend((date_from, date_to) + suffix_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung.", "rows": []}
    raw = _q(
        "WITH lines AS (" + " UNION ALL ".join(parts) + ") "
        "SELECT channel,area_code,customer_code,SUM(amount9) revenue,"
        "COUNT(DISTINCT item_code) skus,COUNT(DISTINCT group_code) product_groups "
        "FROM lines WHERE customer_code IS NOT NULL AND TRIM(customer_code)<>'' "
        "GROUP BY channel,area_code,customer_code HAVING SUM(amount9)>0",
        tuple(params),
    )
    grouped = {}
    for row in raw:
        grouped.setdefault((row["channel"], row["area_code"]), []).append({
            "customer_code": row["customer_code"], "channel": row["channel"],
            "area_code": row["area_code"], "revenue": _f(row["revenue"]),
            "skus": int(row["skus"] or 0), "product_groups": int(row["product_groups"] or 0),
        })

    candidates = []
    all_members = []
    for (_channel, _area), members in grouped.items():
        members.sort(key=lambda row: (row["revenue"], row["customer_code"]))
        count = len(members)
        quotient, remainder = divmod(count, 5)
        cursor = 0
        for tier in range(1, 6):
            size = quotient + (1 if tier <= remainder else 0)
            for row in members[cursor:cursor + size]:
                row["revenue_tier"] = tier
            cursor += size
        peers = {}
        for row in members:
            peers.setdefault(row["revenue_tier"], []).append(row)
        for row in members:
            group = peers[row["revenue_tier"]]
            peer_n = len(group)
            peer_skus = sum(item["skus"] for item in group) / peer_n if peer_n else None
            peer_groups = sum(item["product_groups"] for item in group) / peer_n if peer_n else None
            row["peer_count"] = peer_n
            row["peer_avg_skus"] = peer_skus
            row["peer_avg_product_groups"] = peer_groups
            row["missing_skus_vs_peer"] = peer_skus - row["skus"] if peer_skus is not None else None
            row["missing_groups_vs_peer"] = (
                peer_groups - row["product_groups"] if peer_groups is not None else None
            )
            row["priority_score"] = max(0.0, row["missing_skus_vs_peer"] or 0) * row["revenue"]
            row["peer_status"] = "AVAILABLE" if peer_n >= 5 else "INSUFFICIENT_PEERS"
            if peer_n >= 5 and row["missing_skus_vs_peer"] > 0:
                candidates.append(row)
            all_members.append(row)
    one_group_high_revenue = sorted(
        [row for row in all_members if row["product_groups"] == 1],
        key=lambda row: (-row["revenue"], row["customer_code"]),
    )
    name_codes = {row["customer_code"] for row in candidates + one_group_high_revenue[:limit]}
    names = _customer_names(list(name_codes)) if name_codes else {}
    for row in candidates + one_group_high_revenue[:limit]:
        row["customer_name"] = names.get(row["customer_code"]) or row["customer_code"]
    candidates.sort(key=lambda row: (-row["priority_score"], -row["revenue"], row["customer_code"]))
    return {
        "status": "OK", "mode": "customer_revenue_tier_peer",
        "period": {"from": date_from, "to": date_to},
        "period_selection": (
            "THANG_TRON_GAN_NHAT" if end_date != requested else "DEN_NGAY_DUOC_CHI_DINH"
        ),
        "rows": candidates[:limit], "total_candidates": len(candidates),
        "truncated": len(candidates) > limit,
        "one_group_high_revenue": one_group_high_revenue[:limit],
        "one_group_high_revenue_total": len(one_group_high_revenue),
        "definition": (
            "Nhom tuong dong NOI BO = cung kenh x cung mien x bac doanh thu NTILE(5), "
            "chi so sanh nhom co it nhat 5 khach. Xep uu tien theo so SKU thieu so voi "
            "trung binh nhom nhan doanh thu cua khach."
        ),
        "share_of_wallet_limitation": (
            "Day la do rong danh muc mua noi bo DNH, KHONG phai share-of-wallet thi truong va "
            "khong tu dong chung minh khach co nhu cau voi SKU con thieu."
        ),
        "data_as_of": latest_data_date(),
    }


def employee_assignment_coverage(as_of_date: str = None, limit: int = 100,
                                 scope_area_code: str = None,
                                 scope_channel: str = None,
                                 scope_employee_code: str = None) -> dict:
    """S44/V14: mau so la danh muc khach DANG duoc phan cong, khong phai tap da mua."""
    if scope_channel and str(scope_channel).upper() not in {"OTC", "ALL"}:
        return {"status": "not_applicable", "rows": [],
                "note": "Danh muc phan cong DMS hien chi co cho kenh OTC."}
    columns = {row["name"] for row in _q("PRAGMA table_info(dms_khachhang)")}
    if "is_active" not in columns:
        return {
            "status": "SOURCE_GAP_ASSIGNMENT_ACTIVE_FLAG_NOT_SYNCED", "rows": [],
            "required_source": "DMS_KhachHang.IsActive va EmpDMSCode1",
            "note": "Kho local cu chua dong bo co hoat dong cua danh muc phan cong; khong lay tap khach da mua lam mau so thay the.",
        }
    active_flag_coverage = _q(
        "SELECT COUNT(*) total_rows,"
        "SUM(CASE WHEN is_active IS NOT NULL THEN 1 ELSE 0 END) populated_rows "
        "FROM dms_khachhang"
    )[0]
    if int(active_flag_coverage.get("total_rows") or 0) > 0 \
            and int(active_flag_coverage.get("populated_rows") or 0) == 0:
        return {
            "status": "SOURCE_GAP_ASSIGNMENT_ACTIVE_FLAG_NOT_SYNCED", "rows": [],
            "required_source": "Dong bo lai DMS_KhachHang.IsActive sau khi nang cap schema",
            "note": "Cot IsActive da duoc tao nhung du lieu cu chua duoc nap lai; khong coi NULL la khach ngung hoat dong.",
        }
    as_of_date = str(as_of_date or latest_data_date())[:10]
    month_from = f"{as_of_date[:7]}-01"
    assigned = _q(
        "SELECT emp_code,COUNT(DISTINCT code) assigned_customers FROM dms_khachhang "
        "WHERE is_active=1 AND emp_code IS NOT NULL AND TRIM(emp_code)<>'' GROUP BY emp_code"
    )
    purchases = _q(
        "SELECT kh.emp_code,COUNT(DISTINCT v.customer_code) purchasing_customers,"
        "COALESCE(SUM(v.amount9),0) revenue FROM vhoadon_otc v "
        "JOIN (SELECT code,emp_code FROM dms_khachhang WHERE is_active=1 "
        "GROUP BY code,emp_code) kh ON kh.code=v.customer_code "
        "WHERE v.doc_date BETWEEN ? AND ? AND kh.emp_code IS NOT NULL "
        "GROUP BY kh.emp_code", (month_from, as_of_date)
    )
    purchase_by_dms = {row["emp_code"]: row for row in purchases}
    dms_codes = [row["emp_code"] for row in assigned]
    employee_by_dms = {}
    if dms_codes:
        placeholders = ",".join("?" for _ in dms_codes)
        employee_by_dms = {row["dmsid"]: row for row in _q(
            f"SELECT dmsid,employee_code,name,position_code,area_code FROM dim_nhanvien "
            f"WHERE dmsid IN ({placeholders})", tuple(dms_codes)
        )}
    allowed_dms = None
    if scope_employee_code:
        allowed_dms = set(_get_team_dms_ids(scope_employee_code, as_of_date))
    rows = []
    for book in assigned:
        dms = book["emp_code"]
        employee = employee_by_dms.get(dms, {})
        if allowed_dms is not None and dms not in allowed_dms:
            continue
        if scope_area_code and employee.get("area_code") != scope_area_code:
            continue
        bought = purchase_by_dms.get(dms, {})
        assigned_count = int(book.get("assigned_customers") or 0)
        purchasing_count = int(bought.get("purchasing_customers") or 0)
        revenue = _f(bought.get("revenue"))
        rows.append({
            "employee_dms_code": dms,
            "employee_code": employee.get("employee_code"),
            "employee_name": employee.get("name") or dms,
            "position_code": employee.get("position_code"),
            "area_code": employee.get("area_code"),
            "assigned_customers": assigned_count,
            "purchasing_customers": purchasing_count,
            "non_purchasing_customers": assigned_count - purchasing_count,
            "purchase_rate_pct": (purchasing_count / assigned_count * 100
                                  if assigned_count else None),
            "revenue": revenue,
            "revenue_per_purchasing_customer": (revenue / purchasing_count
                                                if purchasing_count else None),
        })
    assigned_median = median([row["assigned_customers"] for row in rows]) if rows else 0
    rate_values = [row["purchase_rate_pct"] for row in rows if row["purchase_rate_pct"] is not None]
    rate_median = median(rate_values) if rate_values else 0
    revenue_values = [row["revenue_per_purchasing_customer"] for row in rows
                      if row["revenue_per_purchasing_customer"] is not None]
    revenue_median = median(revenue_values) if revenue_values else 0
    many_low = sorted([
        row for row in rows if row["assigned_customers"] >= assigned_median
        and row["purchase_rate_pct"] is not None and row["purchase_rate_pct"] < rate_median
    ], key=lambda row: (-row["assigned_customers"], row["purchase_rate_pct"]))
    few_high = sorted([
        row for row in rows if row["assigned_customers"] < assigned_median
        and row["revenue_per_purchasing_customer"] is not None
        and row["revenue_per_purchasing_customer"] > revenue_median
    ], key=lambda row: -row["revenue_per_purchasing_customer"])
    limit = max(1, min(int(limit or 100), 500))
    return {
        "status": "ok", "as_of_date": as_of_date, "period": {"from": month_from, "to": as_of_date},
        "assigned_customer_snapshot": "CURRENT_DMS_ASSIGNMENT",
        "rows": sorted(rows, key=lambda row: (-row["assigned_customers"], row["purchase_rate_pct"] or 0))[:limit],
        "many_assigned_low_purchase_rate": many_low[:limit],
        "few_assigned_high_revenue_per_customer": few_high[:limit],
        "benchmarks": {"median_assigned_customers": assigned_median,
                       "median_purchase_rate_pct": rate_median,
                       "median_revenue_per_purchasing_customer": revenue_median},
        "definition": (
            "Khach phu trach = khach IsActive=1 trong DMS_KhachHang.EmpDMSCode1 hien tai; khach mua = "
            "khach co hoa don OTC trong ky. Danh muc phan cong la snapshot hien tai, khong dung de "
            "truy nguoc lich su phan cong."
        ),
    }


def customer_product_coverage(as_of_date: str = None, lookback_months: int = 3,
                              mode: str = "customer", limit: int = 100,
                              scope_area_code: str = None, scope_channel: str = None,
                              scope_employee_code: str = None) -> dict:
    """Do phu/benchmark noi bo; mode=priority tra ba danh sach dong gap theo S84.

    customer_peer la benchmark TUNG KHACH theo trung vi CUNG TINH. Kho khong co phan khuc khach
    hang chot chuan, nen tuyen doi khong goi day la benchmark "cung tinh/phan khuc".
    """
    if mode == "priority":
        return priority_gap_actions(as_of_date=as_of_date, limit=limit,
                                    scope_area_code=scope_area_code,
                                    scope_channel=scope_channel,
                                    scope_employee_code=scope_employee_code)
    if mode == "dual_channel":
        return dual_channel_customer_summary(
            as_of_date=as_of_date, lookback_months=lookback_months, limit=limit,
            scope_area_code=scope_area_code, scope_channel=scope_channel,
            scope_employee_code=scope_employee_code,
        )
    if mode == "customer_revenue_tier_peer":
        return customer_revenue_tier_peer(
            as_of_date=as_of_date, lookback_months=lookback_months, limit=limit,
            scope_area_code=scope_area_code, scope_channel=scope_channel,
            scope_employee_code=scope_employee_code,
        )
    if mode == "four_customer_priorities":
        return four_customer_priorities(as_of_date=as_of_date, limit=limit,
                                        scope_area_code=scope_area_code,
                                        scope_channel=scope_channel,
                                        scope_employee_code=scope_employee_code)
    if mode == "product_monthly":
        return product_monthly_performance(as_of_date=as_of_date, months_back=lookback_months,
                                           limit=limit, scope_area_code=scope_area_code,
                                           scope_channel=scope_channel,
                                           scope_employee_code=scope_employee_code)
    if mode == "product_mix":
        return product_mix_performance(as_of_date=as_of_date, limit=limit,
                                       scope_area_code=scope_area_code, scope_channel=scope_channel,
                                       scope_employee_code=scope_employee_code)
    if mode == "employee_assignment":
        return employee_assignment_coverage(
            as_of_date=as_of_date, limit=limit, scope_area_code=scope_area_code,
            scope_channel=scope_channel, scope_employee_code=scope_employee_code,
        )
    if mode == "sku_target":
        # S46/V30: warehouse co co SKU trong tam, nhung KHONG co chi tieu gia tri/so luong
        # theo (TDV, khach, SKU). Tra ve lo nguon co cau truc de model khong bien viec thieu
        # target thanh 0% hoac tu tinh % tu doanh thu.
        return {
            "status": "SOURCE_GAP_NO_SKU_TARGET_VALUE",
            "requested": "% target SKU trong tam theo tung TDV va khach hang",
            "can_not_calculate": ["target_value_by_employee_sku", "target_quantity_by_employee_sku",
                                  "target_by_customer_sku", "gap_by_customer_sku"],
            "available": "Chi co co SKU trong tam va doanh thu/so luong ban tren hoa don; khong co mau so target theo SKU.",
            "required_source": "Bang/field target gia tri hoac san luong theo ky x TDV x khach hang x SKU, da duoc DNH xac nhan.",
            "safe_next_report": "Co the bao cao do phu va doanh thu SKU tung thang; khong duoc goi do la % hoan thanh target.",
            "data_as_of": latest_data_date(),
        }
    if mode == "product_first_observed":
        return product_first_observed_performance(
            as_of_date=as_of_date, lookback_months=lookback_months, limit=limit,
            scope_area_code=scope_area_code, scope_channel=scope_channel,
            scope_employee_code=scope_employee_code,
        )
    if mode == "assignment_change":
        return customer_assignment_change(
            as_of_date=as_of_date, lookback_months=lookback_months, limit=limit,
            scope_area_code=scope_area_code, scope_channel=scope_channel,
            scope_employee_code=scope_employee_code,
        )
    if mode not in {"customer", "customer_peer", "product", "employee"}:
        return {"error": "mode chi nhan customer/customer_peer/customer_revenue_tier_peer/product/employee/employee_assignment/priority/dual_channel/four_customer_priorities/product_monthly/product_mix/sku_target/product_first_observed/assignment_change."}
    customer_mode = mode in {"customer", "customer_peer"}
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
        # 24/09/2026 (M33/S72): as_of la NGAY CUOI thang thi day la thang TRON, phai so voi TRON
        # thang truoc. Ban cu cat theo so ngay: 30/09 chi so voi 01-30/08 (mat ngay 31), 28/02 chi
        # so voi 01-28/01 - lech checker S72 (thang tron vs thang tron).
        thang_tron = current_end_date.day == _last_day_of_month(current_end_date.year,
                                                                current_end_date.month)
        if thang_tron:
            aligned_day = _last_day_of_month(py, pm)
        previous_from = f"{previous_ym}-01"
        previous_to = f"{previous_ym}-{aligned_day:02d}"
        comparison_basis = ("THANG TRON SO VOI TRON THANG TRUOC" if thang_tron
                            else "CUNG NGAY TRONG THANG TRUOC (MTD-aligned)")
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
            geo_join = _otc_area_join("v", scope_area_code)
            if not scope_area_code:
                geo_join = (" LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
                            "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id")
            join = geo_join + f" LEFT JOIN {_NV_THEO_DMSID} nv ON nv.dmsid=v.employee_code"
            parts.append(f"SELECT '{period}' period,v.customer_code,v.item_code,v.amount9,v.quantity,"
                         "'OTC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                         f"COALESCE(nv.employee_code,v.employee_code) employee_code,COALESCE(tp.city_name,'UNKNOWN') city_name FROM vhoadon_otc v {join} "
                         f"WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}")
            params.extend((date_from, date_to) + suffix_params)
        if scope_channel != "OTC":
            geo_join = _etc_area_join("v", scope_area_code)
            if not scope_area_code:
                geo_join = (" LEFT JOIN dmssx_khachhang kh ON kh.code=v.customer_code "
                            "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id")
            join = geo_join + f" LEFT JOIN {_NV_THEO_DMSID} nv ON nv.dmsid=v.employee_code"
            parts.append(f"SELECT '{period}' period,v.customer_code,v.item_code,v.amount9,v.quantity,"
                         "'ETC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                         f"COALESCE(nv.employee_code,v.employee_code) employee_code,COALESCE(tp.city_name,'UNKNOWN') city_name FROM vhoadon_etc v {join} "
                         f"WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}")
            params.extend((date_from, date_to) + suffix_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung."}
    cte = "WITH lines AS (" + " UNION ALL ".join(parts) + ") "
    dim = {"customer": "customer_code", "customer_peer": "customer_code", "product": "item_code", "employee": "employee_code"}[mode]
    raw = _q(
        cte + f"SELECT period,{dim} code,MAX(city_name) city_name,SUM(amount9) revenue,SUM(quantity) quantity,"
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

    customer_names = _customer_names(list(by_code)) if customer_mode else {}
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
        # M33 UAT: phai GIU ca SKU/khach chi co o ky truoc va da ve 0 ky nay. Neu bo chung,
        # bao cao mat dung nhom suy giam nang nhat va tong dimension lech tong pham vi.
        row = {
            "code": code,
            "name": (customer_names.get(code) if customer_mode else
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
        if mode == "customer_peer":
            row["province"] = cur.get("city_name") or prev.get("city_name") or "UNKNOWN"
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
        if mode == "product":
            row["net_revenue_per_paid_unit"] = (
                row["revenue"] / row["quantity"] if row["quantity"] else None
            )
            row["previous_net_revenue_per_paid_unit"] = (
                row["previous_revenue"] / row["previous_quantity"]
                if row["previous_quantity"] else None
            )
            previous_unit_value = row["previous_net_revenue_per_paid_unit"]
            row["net_revenue_per_paid_unit_delta"] = (
                row["net_revenue_per_paid_unit"] - previous_unit_value
                if row["net_revenue_per_paid_unit"] is not None and previous_unit_value is not None
                else None
            )
            row["net_revenue_per_paid_unit_pct"] = (
                row["net_revenue_per_paid_unit_delta"] / previous_unit_value * 100
                if previous_unit_value and row["net_revenue_per_paid_unit_delta"] is not None else None
            )
            row["quantity_per_order"] = (
                row["quantity"] / row["orders"] if row["orders"] else None
            )
            row["previous_quantity_per_order"] = (
                row["previous_quantity"] / row["previous_orders"]
                if row["previous_orders"] else None
            )
            row["quantity_per_order_delta"] = (
                row["quantity_per_order"] - row["previous_quantity_per_order"]
                if row["quantity_per_order"] is not None
                and row["previous_quantity_per_order"] is not None else None
            )
        rows.append(row)
    if mode == "customer_peer":
        from statistics import median
        peer_groups = {}
        for r in rows:
            if r.get("province") and r["province"] != "UNKNOWN" and r["revenue"] > 0:
                peer_groups.setdefault(r["province"], []).append(r)
        for r in rows:
            peers = peer_groups.get(r.get("province"), [])
            r["peer_group_size"] = len(peers)
            if r["revenue"] <= 0:
                # Doanh thu rong am thuong la hang tra/dieu chinh. Day khong phai bang chung khach
                # "mua it" va ty le am so voi trung vi se danh lua nguoi doc.
                r["peer_benchmark_status"] = "NON_POSITIVE_NET_REVENUE_REQUIRES_RETURN_CHECK"
            elif len(peers) >= 3:
                r["peer_benchmark_status"] = "AVAILABLE"
                for metric, key in (("revenue", "city_median_revenue"), ("orders", "city_median_orders"),
                                    ("aov", "city_median_aov"), ("products", "city_median_products")):
                    med = median([_f(p[metric]) for p in peers if p.get(metric) is not None])
                    r[key] = med
                    r[f"{metric}_pct_of_city_median"] = (_f(r[metric]) / med * 100) if med else None
                r["below_city_median_metrics"] = [metric for metric in ("revenue", "orders", "aov", "products")
                                                  if r.get(f"{metric}_pct_of_city_median") is not None
                                                  and r[f"{metric}_pct_of_city_median"] < 100]
            else:
                r["peer_benchmark_status"] = "INSUFFICIENT_PEERS_OR_UNKNOWN_PROVINCE"
    avg_products = sum(r["products"] for r in rows) / len(rows) if rows else 0.0
    avg_revenue = sum(r["revenue"] for r in rows) / len(rows) if rows else 0.0
    for r in rows:
        r["product_gap_vs_scope_avg"] = avg_products - r["products"]
        r["revenue_gap_vs_scope_avg"] = avg_revenue - r["revenue"]
        if mode == "product":
            r["revenue_per_customer"] = r["revenue"] / r["customers"] if r["customers"] else None
            r["previous_revenue_per_customer"] = (
                r["previous_revenue"] / r["previous_customers"]
                if r["previous_customers"] else None
            )
            r["revenue_per_customer_delta"] = (
                r["revenue_per_customer"] - r["previous_revenue_per_customer"]
                if r["revenue_per_customer"] is not None
                and r["previous_revenue_per_customer"] is not None else None
            )
    if mode == "customer_peer":
        rows.sort(key=lambda r: (r.get("peer_benchmark_status") != "AVAILABLE",
                                 r.get("revenue_pct_of_city_median") if r.get("revenue_pct_of_city_median") is not None else float("inf"),
                                 r["revenue"]))
    elif mode == "employee":
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
    if mode == "product":
        for r in rows:
            r["current_internal_revenue_share_pct"] = (
                r["revenue"] / current_total["revenue"] * 100
                if current_total["revenue"] else None
            )
            r["previous_internal_revenue_share_pct"] = (
                r["previous_revenue"] / previous_total["revenue"] * 100
                if previous_total["revenue"] else None
            )
            r["internal_share_delta_pct_points"] = (
                r["current_internal_revenue_share_pct"] - r["previous_internal_revenue_share_pct"]
                if r["current_internal_revenue_share_pct"] is not None
                and r["previous_internal_revenue_share_pct"] is not None else None
            )
            if r["revenue_delta"] >= 0:
                r["primary_decline_driver"] = None
            elif r["customers_delta"] < 0:
                r["primary_decline_driver"] = "FEWER_CUSTOMERS"
            elif r["orders_delta"] < 0:
                r["primary_decline_driver"] = "FEWER_ORDERS"
            elif r.get("quantity_per_order_delta") is not None and r["quantity_per_order_delta"] < 0:
                r["primary_decline_driver"] = "LOWER_PAID_QUANTITY_PER_ORDER"
            elif (r.get("net_revenue_per_paid_unit_delta") is not None
                  and r["net_revenue_per_paid_unit_delta"] < 0):
                r["primary_decline_driver"] = "LOWER_NET_REVENUE_PER_PAID_UNIT"
            else:
                r["primary_decline_driver"] = "OTHER_OR_MIXED"
    current_rows_total = sum(r["revenue"] for r in rows)
    previous_rows_total = sum(r["previous_revenue"] for r in rows)
    total_change = {
        key + "_delta": (current_total[key] - previous_total[key]
                          if current_total[key] is not None and previous_total[key] is not None else None)
        for key in ("revenue", "orders", "customers", "quantity", "aov", "frequency")
    }
    active_rows = [r for r in rows if r["revenue"] or r["previous_revenue"]]
    increase_rows = [r for r in active_rows if r["revenue_delta"] > 0]
    decrease_rows = [r for r in active_rows if r["revenue_delta"] < 0]
    product_extras = {}
    if mode == "product":
        product_extras = {
            "largest_revenue_increases": sorted(
                increase_rows, key=lambda r: (-r["revenue_delta"], r["code"])
            )[:limit],
            "largest_revenue_declines": sorted(
                decrease_rows, key=lambda r: (r["revenue_delta"], r["code"])
            )[:limit],
            "largest_internal_share_losses": sorted(
                [r for r in active_rows if (r.get("internal_share_delta_pct_points") or 0) < 0],
                key=lambda r: (r["internal_share_delta_pct_points"], r["code"]),
            )[:limit],
            "coverage_up_revenue_per_customer_down": [
                r for r in sorted(active_rows, key=lambda r: (-r["customers_delta"], r["code"]))
                if r["customers_delta"] > 0 and (r.get("revenue_per_customer_delta") or 0) < 0
            ][:limit],
            "revenue_up_coverage_down": [
                r for r in sorted(active_rows, key=lambda r: (-r["revenue_delta"], r["code"]))
                if r["revenue_delta"] > 0 and r["customers_delta"] < 0
            ][:limit],
            "decline_driver_definition": (
                "Chi gan nguyen nhan chinh cho SKU co revenue_delta<0, theo thu tu: giam so khach, "
                "giam so don, giam san luong tra tien/don, giam doanh thu rong/don vi tra tien, "
                "sau do moi la hon hop/khac. Hang tang unit_price<=0 khong vao san luong tra tien."
            ),
        }
    return {
        "mode": mode, "window_days": window_days,
        "current_period": {"from": current_from, "to": as_of_date},
        "previous_period": {"from": previous_from, "to": previous_to},
        "comparison_basis": comparison_basis,
        "scope_totals": {"current": current_total, "previous": previous_total, **total_change},
        "reconciliation": {
            "current_scope_minus_all_dimension_rows": current_total["revenue"] - current_rows_total,
            "previous_scope_minus_all_dimension_rows": previous_total["revenue"] - previous_rows_total,
            "passed": (abs(current_total["revenue"] - current_rows_total) <= 1
                       and abs(previous_total["revenue"] - previous_rows_total) <= 1),
            "note": "Doi chieu tong pham vi voi tong tat ca dong dimension TRUOC khi cat limit.",
        },
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
        **product_extras,
        "definition": (f"Ky so sanh: {comparison_basis}. Benchmark la "
                       "trung binh NOI BO cua dung pham vi tai khoan va cua so duoc hoi. "
                       "Khong phai market share/share-of-wallet ben ngoai DNH. product_gap > 0 nghia "
                       "la mua it SKU hon trung binh pham vi, khong tu dong dong nghia co nhu cau."),
        "peer_benchmark_definition": (
            "customer_peer: trung vi cua cac khach co mua trong CUNG TINH, can toi thieu 3 khach. "
            "Doanh thu rong am khong duoc goi la mua it, can kiem tra hang tra/dieu chinh truoc. "
            "Kho chua co phan khuc khach hang chot chuan, nen KHONG the khang dinh benchmark cung phan khuc."),
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
    today = dt.date.today().isoformat()
    actual_date_to = min(date_to, today)
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
    unit_expr = "COALESCE(tp.area_code,'UNKNOWN')" if dimension == "area" else "COALESCE(tp.city_name,'UNKNOWN')"
    parts, groups = [], []
    # Scope cua QLV phai chot THEO TUNG THANG. Neu lay mot danh sach DMSId cua thang cuoi
    # roi ap nguoc ve thang truoc, bao cao co the mat/chen doanh thu khi TDV chuyen doi.
    months = [_month_add(month_from, i) for i in range(months_back)]
    periods = [(ym, *_month_bounds(ym)) for ym in months] if scope_employee_code else [(month_to, date_from, date_to)]
    for _ym, period_from, period_to in periods:
        period_to = min(period_to, actual_date_to)
        emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=period_to)
        suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
        if scope_channel != "ETC":
            parts.append(f"SELECT substr(v.doc_date,1,7) month,{unit_expr} unit,tp.area_code,"
                         "v.amount9 revenue,'OTC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                         "v.customer_code,v.quantity,v.unit_price FROM vhoadon_otc v "
                         "LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code "
                         f"LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id WHERE v.doc_date BETWEEN ? AND ?{suffix} ")
            groups.append((period_from, period_to) + suffix_params)
        if scope_channel != "OTC":
            parts.append(f"SELECT substr(v.doc_date,1,7) month,{unit_expr} unit,tp.area_code,"
                         "v.amount9 revenue,'ETC:'||v.doc_date||':'||v.customer_code||':'||COALESCE(v.stt,'') order_key,"
                         "v.customer_code,v.quantity,v.unit_price FROM vhoadon_etc v "
                         "LEFT JOIN dmssx_khachhang kh ON kh.code=v.customer_code "
                         f"LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id WHERE v.doc_date BETWEEN ? AND ?{suffix} ")
            groups.append((period_from, period_to) + suffix_params)
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
        r["revenue_per_customer"] = r["revenue"] / r["customers"] if r["customers"] else None
        by_unit.setdefault(r["unit"], {})[r["month"]] = r
        totals[r["month"]] = totals.get(r["month"], 0.0) + r["revenue"]
    # 11/09/2026 (C24/M27): "dia ban nao co do phu/doanh thu-khach thap hon CHUAN MIEN/dia ban tuong
    # dong" truoc day khong co san field so sanh nay, khien model tu viet SQL tu do dò tung vung
    # (C24) hoac goi lai tool nhieu lan voi dimension/months_back khac nhau (M27) va timeout. Tinh
    # san TRUNG BINH VUNG (area_code) cung thang de moi dia ban (city) so duoc voi chuan mien cua no,
    # khong tu suy dien "chuan" la gi.
    area_month_avg = {}
    if dimension == "city":
        area_month_totals = {}
        for r in raw:
            key = (r.get("area_code") or "UNKNOWN", r["month"])
            bucket = area_month_totals.setdefault(key, {"revenue": 0.0, "customers": 0, "units": set()})
            bucket["revenue"] += r["revenue"]
            bucket["customers"] += r["customers"]
            bucket["units"].add(r["unit"])
        for (area_code, month), bucket in area_month_totals.items():
            n_units = len(bucket["units"]) or 1
            area_month_avg[(area_code, month)] = {
                "area_code": area_code, "month": month,
                "avg_revenue_per_city": bucket["revenue"] / n_units,
                "avg_customers_per_city": bucket["customers"] / n_units,
                "avg_revenue_per_customer": (bucket["revenue"] / bucket["customers"]) if bucket["customers"] else None,
            }
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
            area_avg = area_month_avg.get((r.get("area_code") or "UNKNOWN", ym))
            rows.append({**r, "mom_delta": delta,
                         "mom_pct": (delta / prev["revenue"] * 100) if prev and prev["revenue"] else None,
                         "share_pct": r["revenue"] / totals[ym] * 100 if totals.get(ym) else None,
                         "streak_direction": streak_dir, "streak_months": streak_len,
                         "area_avg_revenue_per_city": area_avg["avg_revenue_per_city"] if area_avg else None,
                         "area_avg_customers_per_city": area_avg["avg_customers_per_city"] if area_avg else None,
                         "area_avg_revenue_per_customer": area_avg["avg_revenue_per_customer"] if area_avg else None,
                         "below_area_avg_customers": (
                             area_avg is not None and r["customers"] < area_avg["avg_customers_per_city"]
                         ),
                         "below_area_avg_revenue_per_customer": (
                             area_avg is not None and area_avg["avg_revenue_per_customer"] is not None
                             and r["revenue_per_customer"] is not None
                             and r["revenue_per_customer"] < area_avg["avg_revenue_per_customer"]
                         )})
    for ym in sorted({r["month"] for r in rows}):
        month_rows = sorted([r for r in rows if r["month"] == ym], key=lambda r: -r["revenue"])
        for rank, r in enumerate(month_rows, 1): r["rank"] = rank
    rows.sort(key=lambda r: (r["month"], r.get("rank", 999)))
    # Thu hang (rank) va ty trong (share_pct) da tinh trên TOAN BO dia ban o tren, truoc khi cat -
    # nen so lieu cua cac don vi duoc giu van dung tuong quan voi ca nuoc, khong bi tinh lai theo
    # nhom con.
    rows, so_bi_cat = _giu_top_don_vi(rows, "unit", "revenue", limit)
    data_as_of = latest_data_date()
    _, month_to_end = _month_bounds(month_to)
    month_to_partial = month_to == data_as_of[:7] and data_as_of < month_to_end
    ket_qua = {"month_from": month_from, "month_to": month_to, "dimension": dimension,
            "customer_count_definition": (
                "customers = COUNT(DISTINCT customer_code) tren hoa don da loc day du pham vi doi. "
                "Khong thay bang co khach moi/is_ro/is_ac va khong goi la uoc tinh."
            ),
            "rows": rows, "so_dia_ban_khong_hien": so_bi_cat,
            "unavailable_dimensions": ["branch", "NPP", "distributor"],
            "unavailable_metrics": ["target_by_city", "gap_to_target_by_city", "employee_responsibility_by_city"],
            "target_gap_note": (
                "Kho chua co target phan bo theo tinh/dia ban va khong co mapping TDV-phu trach-dia ban "
                "co lich su chot chuan. Chi co the bao doanh thu/khach/don theo dia ban; KHONG the ket "
                "luan tinh nao duoi ke hoach, phan hut bao nhieu hay TDV nao chiu trach nhiem."),
            "canh_bao": ("UNKNOWN la khach/hoa don khong noi duoc danh muc tinh. Khong duoc tu gan "
                          "vung/tinh cho nhom nay. Chi tiet dia ban chi nam trong cua so hoa don gan."),
            "data_as_of": data_as_of,
            "month_to_is_partial": month_to_partial,
            "month_to_data_through": data_as_of if month_to_partial else None,
        }
    if actual_date_to < date_to:
        ket_qua["tinh_den_ngay"] = today
        future_from = max(date_from, (dt.date.today() + dt.timedelta(days=1)).isoformat())
        future = _revenue_by_channel_raw(
            future_from, date_to, scope_area_code, scope_channel, scope_employee_code,
        )
        if future["total"]["revenue"] or future["total"]["invoices"]:
            ket_qua["chung_tu_ngay_tuong_lai"] = {
                "tu_ngay": future_from, "den_ngay": date_to,
                "revenue": future["total"]["revenue"],
                "invoices": future["total"]["invoices"],
                "ghi_chu": ("Chung tu de ngay SAU hom nay, KHONG duoc cong vao doanh thu "
                            "theo dia ban da phat sinh."),
            }
    if month_to_partial:
        ket_qua["current_month_comparison_warning"] = (
            f"Thang {month_to} moi co du lieu den {data_as_of}. Khong duoc so sanh truc tiep voi "
            "thang tron hoac tu y doi 'thang nay' thanh thang truoc; neu can so sanh cong bang, chi "
            "so den cung ngay trong cac thang truoc hoac noi ro day la MTD.")
    if scope_employee_code:
        reconciliation = []
        for ym in months:
            _, period_end = _month_bounds(ym)
            fdate = _fact_date_le(period_end)
            if not fdate:
                reconciliation.append({"month": ym, "status": "NO_KPI_SNAPSHOT"})
                continue
            team = _team_of_qlv(scope_employee_code, fdate)
            codes = [r["employee_code"] for r in team if r.get("employee_code")]
            if not codes:
                reconciliation.append({"month": ym, "status": "NO_TEAM_ROSTER", "snapshot": fdate})
                continue
            ph = ",".join("?" for _ in codes)
            fact = _q(
                f"SELECT COALESCE(SUM(f.amount_ct),0) revenue FROM fact_tonghopkhachhang f "
                f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=f.employee_code AND l.d=f.save_date "
                f"WHERE f.employee_code IN ({ph})", (fdate, fdate, *codes))
            snapshot_revenue = _f(fact[0]["revenue"]) if fact else 0.0
            invoice_revenue = _f(totals.get(ym))
            delta = invoice_revenue - snapshot_revenue
            reconciliation.append({
                "month": ym, "snapshot": fdate, "invoice_revenue": invoice_revenue,
                "kpi_snapshot_revenue": snapshot_revenue, "delta": delta,
                "matched": abs(delta) < 1,
            })
        ket_qua["team_scope_invoice_reconciliation"] = reconciliation
        bad = [r for r in reconciliation if r.get("matched") is False]
        if bad:
            ket_qua["team_scope_reconciliation_warning"] = (
                "Doanh thu hoa don theo DMSId KHONG khop doanh thu snapshot KPI o it nhat mot thang. "
                "KHONG duoc ket hop doanh thu snapshot voi so don/AOV tu hoa don thanh mot bo so duy nhat; "
                "can doi soat mapping DMSId lich su truoc khi ket luan cap doi.")
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


def _route_visit_effectiveness(month_to: str = None, months_back: int = 1, limit: int = 50,
                               scope_area_code: str = None, scope_channel: str = None,
                               scope_employee_code: str = None) -> dict:
    """C49/S34: hieu qua di tuyen tu DMS_DiTuyen, truy van tong hop tren Bravo.

    Khong dua 1,8 trieu dong di tuyen vao SMALL_TABLES: co che do reload toan bo moi gio va se lam
    vong dong bo treo. Chi doc phan ky nguoi dung hoi, gom theo thang x TDV, nen vua du de phan tich
    lai tuyen/vieng tham vua khong lam kho local phinh bat thuong.
    """
    if scope_channel and scope_channel.upper() == "ETC":
        return {
            "not_applicable": True, "channel_scope": "ETC", "rows": [],
            "error": "DMS_DiTuyen la nguon viếng thăm kenh OTC; khong co nguon tuong duong cho ETC.",
        }
    latest = latest_data_date()
    if not month_to:
        # Mac dinh thang da tron gan nhat, tranh ket luan tu vai ngay MTD khi nguoi dung khong chi dinh ky.
        today = dt.date.today()
        month_to = _month_add(f"{today.year:04d}-{today.month:02d}", -1)
    month_to = str(month_to)[:7]
    try:
        end_month_date = dt.date.fromisoformat(month_to + "-01")
    except ValueError:
        return {"error": "month_to phai co dang YYYY-MM.", "rows": []}
    months_back = max(1, min(int(months_back or 1), 12))
    month_from = _month_add(month_to, -(months_back - 1))
    date_from = dt.date.fromisoformat(month_from + "-01")
    date_to_exclusive = dt.date(end_month_date.year + (end_month_date.month == 12),
                                1 if end_month_date.month == 12 else end_month_date.month + 1, 1)
    limit = max(1, min(int(limit or 50), 200))

    params = {"date_from": date_from, "date_to_exclusive": date_to_exclusive}
    visit_joins = ""
    visit_filter = ""
    invoice_joins = ""
    invoice_filter = ""
    if scope_area_code:
        visit_joins = (" LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=v.CustomerCode "
                       " LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId ")
        visit_filter += " AND tp.AreaCode=:scope_area_code"
        invoice_joins = (" LEFT JOIN dbo.DMS_KhachHang ikh ON ikh.Code=i.CustomerCode "
                         " LEFT JOIN dbo.DIM_TinhThanhPho itp ON itp.CityId=ikh.CityId ")
        invoice_filter += " AND itp.AreaCode=:scope_area_code"
        params["scope_area_code"] = scope_area_code
    if scope_employee_code:
        try:
            dms_ids = _get_team_dms_ids(scope_employee_code, str(date_to_exclusive - dt.timedelta(days=1)))
        except Exception as exc:
            return {"error": f"Khong xac dinh duoc doi de loc du lieu di tuyen: {exc}", "rows": []}
        placeholders = []
        for idx, dms_id in enumerate(dms_ids):
            key = f"employee_dms_{idx}"
            params[key] = dms_id
            placeholders.append(f":{key}")
        if not placeholders:
            return {"error": "Khong co DMSId duoc phan quyen de loc du lieu di tuyen.", "rows": []}
        joined = ",".join(placeholders)
        visit_filter += f" AND v.EmpDMSCode IN ({joined})"
        invoice_filter += f" AND i.EmpDMSCode IN ({joined})"

    try:
        raw = _q_bravo(f"""
            WITH visits AS (
                SELECT v.DocDate, v.EmpDMSCode, v.CustomerCode,
                       MAX(CASE WHEN v.IsPlaned=1 THEN 1 ELSE 0 END) IsPlanned
                FROM dbo.DMS_DiTuyen v
                {visit_joins}
                WHERE v.DocDate>=:date_from AND v.DocDate<:date_to_exclusive {visit_filter}
                GROUP BY v.DocDate, v.EmpDMSCode, v.CustomerCode
            ), orders AS (
                SELECT DISTINCT h.DocDate, h.DMSEmpId1 AS EmpDMSCode, h.CustomerCode
                FROM dbo.DMS_DonHangHdr h
                WHERE h.DocDate>=:date_from AND h.DocDate<:date_to_exclusive
            ), revenue AS (
                SELECT EOMONTH(i.DocDate) AS MonthEnd, i.EmpDMSCode, SUM(i.Amount9) Revenue
                FROM dbo.vHoaDonTotal i
                {invoice_joins}
                WHERE i.DocDate>=:date_from AND i.DocDate<:date_to_exclusive {invoice_filter}
                GROUP BY EOMONTH(i.DocDate), i.EmpDMSCode
            )
            SELECT EOMONTH(v.DocDate) AS MonthEnd, v.EmpDMSCode,
                   COUNT(*) AS Visits, COUNT(DISTINCT v.CustomerCode) AS VisitedCustomers,
                   SUM(v.IsPlanned) AS PlannedVisits,
                   SUM(CASE WHEN o.CustomerCode IS NOT NULL THEN 1 ELSE 0 END) AS VisitsWithOrder,
                   MAX(r.Revenue) AS Revenue
            FROM visits v
            LEFT JOIN orders o ON o.DocDate=v.DocDate AND o.EmpDMSCode=v.EmpDMSCode
                              AND o.CustomerCode=v.CustomerCode
            LEFT JOIN revenue r ON r.MonthEnd=EOMONTH(v.DocDate) AND r.EmpDMSCode=v.EmpDMSCode
            GROUP BY EOMONTH(v.DocDate), v.EmpDMSCode
            ORDER BY MonthEnd DESC, Visits DESC, v.EmpDMSCode
        """, params)
    except Exception as exc:
        return {
            "error": f"Khong doc duoc nguon DMS_DiTuyen tren Bravo: {exc}", "rows": [],
            "source": "DMS_DiTuyen + DMS_DonHangHdr + vHoaDonTotal (OTC)",
        }

    rows = []
    for row in raw:
        visits = int(row.get("Visits") or 0)
        with_order = int(row.get("VisitsWithOrder") or 0)
        planned = int(row.get("PlannedVisits") or 0)
        revenue = _f(row.get("Revenue"))
        month_end = row.get("MonthEnd")
        rows.append({
            "month": str(month_end)[:7] if month_end else None,
            "employee_dms_code": row.get("EmpDMSCode"),
            "visits": visits,
            "visited_customers": int(row.get("VisitedCustomers") or 0),
            "planned_visits": planned,
            "planned_visit_pct": round(planned / visits * 100, 1) if visits else None,
            "visits_with_order": with_order,
            "same_day_order_pct_lower_bound": round(with_order / visits * 100, 1) if visits else None,
            "revenue": revenue,
            "revenue_per_visit": round(revenue / visits, 2) if visits else None,
        })

    monthly_summary = []
    for month in sorted({r["month"] for r in rows if r["month"]}, reverse=True):
        group = [r for r in rows if r["month"] == month]
        visits = sum(r["visits"] for r in group)
        planned = sum(r["planned_visits"] for r in group)
        ordered = sum(r["visits_with_order"] for r in group)
        revenue = sum(r["revenue"] for r in group)
        monthly_summary.append({
            "month": month, "employees_with_visits": len(group), "visits": visits,
            "visited_customers": sum(r["visited_customers"] for r in group),
            "planned_visits": planned,
            "planned_visit_pct": round(planned / visits * 100, 1) if visits else None,
            "visits_with_order": ordered,
            "same_day_order_pct_lower_bound": round(ordered / visits * 100, 1) if visits else None,
            "revenue": revenue, "revenue_per_visit": round(revenue / visits, 2) if visits else None,
        })
    visible_rows, hidden = _giu_top_don_vi(rows, "employee_dms_code", "visits", limit)
    return {
        "mode": "route_visits", "month_from": month_from, "month_to": month_to,
        "rows": visible_rows, "monthly_summary": monthly_summary,
        "so_nhan_vien_khong_hien": hidden,
        "source": "DMS_DiTuyen + DMS_DonHangHdr + vHoaDonTotal (OTC)",
        "definition": (
            "Mot luot vieng = mot cap ngay + TDV DMS + khach hang (loai dong trung). "
            "Ty le co don chi tinh don cung ngay, cung TDV, cung khach nen la CAN DUOI; "
            "don dat sau luot tham khong duoc tinh."),
        "data_as_of": latest,
    }


def _nguyen_nhan_giam_doanh_so(employee_codes: list, month: str) -> dict:
    """M16: do mat khach, giam tan suat hay giam gia tri don? So thang cuoi chuoi giam voi thang
    lien truoc tren hoa don OTC cua chinh NV. Khach x (don/khach) x AOV = doanh thu hoa don, nen ba ty
    le thay doi cho biet phan nao keo giam. Doanh thu hoa don co the lech doanh so bang luong."""
    dms = _dms_theo_ma_nv(employee_codes)
    if not dms:
        return {}
    ma_theo_dms = {}
    for code, dms_id in dms.items():
        ma_theo_dms.setdefault(dms_id, code)
    thang_truoc = _month_add(month, -1)
    tu, _ = _month_bounds(thang_truoc)
    _, den = _month_bounds(month)
    den_sau = str(dt.date.fromisoformat(den) + dt.timedelta(days=1))
    ph = ",".join(["?"] * len(ma_theo_dms))
    so = {}
    for r in _q(f"SELECT employee_code dms, substr(doc_date,1,7) m, COUNT(DISTINCT customer_code) kh, "
                f"COUNT(DISTINCT stt) don, COALESCE(SUM(amount9),0) dt, COUNT(DISTINCT item_code) sku "
                f"FROM vhoadon_otc WHERE employee_code IN ({ph}) AND doc_date>=? AND doc_date<? "
                f"GROUP BY employee_code, substr(doc_date,1,7)", tuple(ma_theo_dms) + (tu, den_sau)):
        so[(ma_theo_dms.get(r["dms"]), r["m"])] = r

    def _pct(moi, cu):
        return (moi - cu) / cu * 100 if cu else None

    ket_qua = {}
    for code in employee_codes:
        cu, moi = so.get((code, thang_truoc)), so.get((code, month))
        if not cu and not moi:
            continue
        cu, moi = cu or {}, moi or {}
        kh = (int(cu.get("kh") or 0), int(moi.get("kh") or 0))
        don = (int(cu.get("don") or 0), int(moi.get("don") or 0))
        dt_ = (_f(cu.get("dt")), _f(moi.get("dt")))
        tan_suat = tuple(d / k if k else None for d, k in zip(don, kh))
        aov = tuple(v / d if d else None for v, d in zip(dt_, don))
        thay_doi = {
            "mat_khach": _pct(kh[1], kh[0]),
            "giam_tan_suat": _pct(tan_suat[1], tan_suat[0]) if None not in tan_suat else None,
            "giam_gia_tri_don": _pct(aov[1], aov[0]) if None not in aov else None,
        }
        am = {k: v for k, v in thay_doi.items() if v is not None and v < 0}
        ket_qua[code] = {
            "thang": month, "thang_truoc": thang_truoc,
            "khach": {"truoc": kh[0], "nay": kh[1]}, "don": {"truoc": don[0], "nay": don[1]},
            "don_moi_khach": {"truoc": tan_suat[0], "nay": tan_suat[1]},
            "aov": {"truoc": aov[0], "nay": aov[1]},
            "sku": {"truoc": int(cu.get("sku") or 0), "nay": int(moi.get("sku") or 0)},
            "doanh_thu_hoa_don": {"truoc": dt_[0], "nay": dt_[1]},
            "pct_thay_doi": thay_doi,
            "yeu_to_giam_manh_nhat": min(am, key=am.get) if am else None,
        }
    return ket_qua


def workforce_productivity(month_to: str = None, months_back: int = 6,
                           group_by: str = "manager", limit: int = 200, mode: str = "productivity",
                           scope_area_code: str = None, scope_channel: str = None,
                           scope_employee_code: str = None) -> dict:
    """Nang suat thang theo nhan vien/QLV/vung, headcount, span va streak tang-giam.

    10/09/2026: them headcount_up_productivity_down (chi voi group_by='manager'/'area') - danh sach
    san cac nhom co headcount tang nhung revenue_per_employee giam so thang truoc, tranh phai goi
    tool nhieu lan voi group_by/months_back khac nhau de tu do tim (da gay timeout thuc te o C46)."""
    if mode == "route_visits":
        return _route_visit_effectiveness(month_to, months_back, limit, scope_area_code,
                                          scope_channel, scope_employee_code)
    if mode != "productivity":
        return {"error": "mode chi nhan productivity hoac route_visits."}
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
    latest_month = str(latest)[:7]
    ly, lm = int(latest_month[:4]), int(latest_month[5:7])
    latest_snapshot_is_month_end = str(latest)[:10] == (
        f"{ly:04d}-{lm:02d}-{_last_day_of_month(ly, lm):02d}"
    )
    # M16/S55: snapshot cua thang dang chay chi la MTD. Neu dem no vao chuoi giam,
    # gan nhu moi NV se bi danh dau giam gia vi dang so vai ngay voi ca thang truoc.
    # Van tra rows MTD de nguoi dung xem nang suat hien tai, nhung summary "giam lien
    # tiep" chi chot den thang tron gan nhat.
    month_to_is_partial = month_to == latest_month and not latest_snapshot_is_month_end
    decline_evaluated_through = _month_add(month_to, -1) if month_to_is_partial else month_to
    months_back = max(1, min(int(months_back or 6), 12))
    month_from = _month_add(month_to, -(months_back - 1))
    limit = max(1, min(int(limit or 200), 1000))
    # Snapshot luong/KPI duoc ghi lech ngay giua cac mien va co the lech ngay giua tung NV.
    # Ghim MAX(save_date) theo rieng thang se lam mat nhan vien/target cua ngay chot som hon
    # (loi V11/S56: doanh so van thay o snapshot ca nhan nhung target thang 7 bi rong).
    sql = ("WITH snaps AS (SELECT employee_code,substr(save_date,1,7) month,MAX(save_date) d "
           "FROM fact_thongketinhluong WHERE substr(save_date,1,7) BETWEEN ? AND ? "
           "GROUP BY employee_code,substr(save_date,1,7)) "
           "SELECT substr(f.save_date,1,7) month,f.save_date,f.employee_code,f.employee_name,"
           "f.position_code,f.area_code,f.manager_code,COALESCE(f.month_sale_amount,0) actual,"
           "COALESCE(f.month_sale_target,0) target,f.month_sale_percent,nv.start_date "
           "FROM fact_thongketinhluong f JOIN snaps s ON s.employee_code=f.employee_code "
           "AND s.month=substr(f.save_date,1,7) AND s.d=f.save_date "
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
            "employee_metrics": [],
        })
        b["actual"] += _f(r["actual"]); b["target"] += _f(r["target"])
        b["employees"].add(r["employee_code"])
        b["employee_metrics"].append({
            "employee_code": r["employee_code"],
            "employee_name": r["employee_name"] or r["employee_code"],
            "actual": _f(r["actual"]), "target": _f(r["target"]),
        })
        tm = tenure_months(r.get("start_date"), r["month"])
        if tm is not None: b["tenures"].append(tm)

    by_group = {}
    for (key, month), b in monthly.items():
        row = {k: v for k, v in b.items()
               if k not in {"employees", "tenures", "employee_metrics"}}
        row["headcount"] = len(b["employees"])
        row["revenue_per_employee"] = b["actual"] / row["headcount"] if row["headcount"] else None
        row["achievement_pct"] = b["actual"] / b["target"] * 100 if b["target"] else None
        row["avg_tenure_months"] = (sum(b["tenures"]) / len(b["tenures"])) if b["tenures"] else None
        with_target = [item for item in b["employee_metrics"] if item["target"] > 0]
        below_80 = [item for item in with_target if item["actual"] < 0.8 * item["target"]]
        below_80.sort(key=lambda item: (-(item["target"] - item["actual"]), item["employee_code"]))
        row["employees_with_target"] = len(with_target)
        row["employees_without_target"] = row["headcount"] - len(with_target)
        row["assessment_status"] = (
            "NO_TARGET_DATA" if not with_target else
            "PARTIAL_TARGET_DATA" if len(with_target) < row["headcount"] else "OK"
        )
        row["below_80_count"] = len(below_80)
        row["below_80_pct"] = len(below_80) / len(with_target) * 100 if with_target else None
        row["below_80_gap"] = sum(item["target"] - item["actual"] for item in below_80)
        row["worst_employee"] = ({**below_80[0],
                                  "gap": below_80[0]["target"] - below_80[0]["actual"]}
                                 if below_80 else None)
        by_group.setdefault(key, {})[month] = row

    rows = []
    for key, ms in by_group.items():
        decline_streak = 0
        below_80_streak = 0
        for month in sorted(ms):
            r = ms[month]; prev = ms.get(_month_add(month, -1))
            r["previous_actual"] = prev["actual"] if prev else None
            r["mom_delta"] = r["actual"] - prev["actual"] if prev else None
            r["mom_pct"] = (r["mom_delta"] / prev["actual"] * 100) if prev and prev["actual"] else None
            if r["mom_delta"] is not None and r["mom_delta"] < 0: decline_streak += 1
            else: decline_streak = 0
            r["decline_streak_months"] = decline_streak
            if r["achievement_pct"] is not None and r["achievement_pct"] < 80:
                below_80_streak += 1
            else:
                below_80_streak = 0
            r["below_80_streak_months"] = below_80_streak
            rows.append(r)
    rows.sort(key=lambda r: (r["month"], -(r["actual"] or 0)))
    if group_by == "manager":
        manager_codes = sorted({
            row["group_code"] for row in rows
            if row.get("group_code") and row["group_code"] != "MISSING_MANAGER"
        })
        manager_names = {}
        if manager_codes:
            ph = ",".join("?" for _ in manager_codes)
            manager_names = {row["employee_code"]: row["name"] for row in _q(
                f"SELECT employee_code,name FROM dim_nhanvien WHERE employee_code IN ({ph})",
                tuple(manager_codes),
            )}
        for row in rows:
            row["group_name"] = manager_names.get(row["group_code"]) or row["group_name"]

    # M16/S55 + V13: `rows` se bi cat theo top doanh so de payload khong qua lon. Neu dung chinh
    # tap da cat de tim nguoi giam lien tiep thi cac nhan vien doanh so thap (thuong la nhom can
    # quan tam nhat) lai bien mat, va model co the nhin thay 1 nguoi roi goi do la "duy nhat".
    # Tao mot summary rieng TU TAP DAY DU, moi NV chi lay dong moi nhat trong cua so. `>= 2` nghia
    # la da co it nhat hai cap MoM giam lien tiep, tuong ung chuoi ba thang di xuong trong S55.
    declining_employees = []
    declining_employee_count = 0
    declining_summary_limit = 200
    if group_by == "employee":
        latest_by_employee = {}
        for row in rows:
            if row["month"] != decline_evaluated_through:
                continue
            current = latest_by_employee.get(row["group_code"])
            if current is None:
                latest_by_employee[row["group_code"]] = row
        all_declining = [
            {
                "employee_code": row["group_code"],
                "employee_name": row["group_name"],
                "latest_month": row["month"],
                "decline_streak_months": row["decline_streak_months"],
                "current_revenue": row["actual"],
                "previous_revenue": row["previous_actual"],
                "mom_delta": row["mom_delta"],
                "mom_pct": row["mom_pct"],
                # Tool nang suat chua co khach/don/AOV theo NV. Dat co cau truc fail-closed de
                # chatbot khong bien mot chuoi doanh so giam thanh ket luan nhan qua.
                "cause_data_available": False,
            }
            for row in latest_by_employee.values()
            if row["decline_streak_months"] >= 2
        ]
        all_declining.sort(key=lambda row: (
            -row["decline_streak_months"],
            -abs(row["mom_delta"] or 0),
            row["employee_code"],
        ))
        declining_employee_count = len(all_declining)
        declining_employees = all_declining[:declining_summary_limit]
        # 11/09/2026 (M16 "do mat khach/giam tan suat/giam gia tri don"): truoc day chi co co
        # cause_data_available=False nen cau tra loi thieu han ve nguyen nhan cua cau hoi.
        if declining_employees:
            nguyen_nhan = _nguyen_nhan_giam_doanh_so(
                [row["employee_code"] for row in declining_employees], decline_evaluated_through)
            for row in declining_employees:
                row["cause"] = nguyen_nhan.get(row["employee_code"])
                row["cause_data_available"] = row["cause"] is not None
    declining_count_by_streak = (
        {f">={n}": sum(1 for row in all_declining if row["decline_streak_months"] >= n) for n in (2, 3, 4)}
        if group_by == "employee" else None
    )

    manager_attention = []
    manager_attention_evaluated_month = None
    manager_attention_period_fallback = False
    if group_by == "manager":
        candidate_months = sorted({
            row["month"] for row in rows if row.get("employees_with_target", 0) > 0
        })
        latest_manager_month = month_to if month_to in candidate_months else (
            candidate_months[-1] if candidate_months else month_to
        )
        manager_attention_evaluated_month = latest_manager_month
        manager_attention_period_fallback = latest_manager_month != month_to
        manager_attention = [
            {
                "manager_code": row["group_code"], "manager_name": row["group_name"],
                "month": row["month"], "actual": row["actual"], "target": row["target"],
                "achievement_pct": row["achievement_pct"],
                "below_80_count": row["below_80_count"],
                "employees_with_target": row["employees_with_target"],
                "employees_without_target": row["employees_without_target"],
                "assessment_status": row["assessment_status"],
                "below_80_pct": row["below_80_pct"], "below_80_gap": row["below_80_gap"],
                "below_80_streak_months": row["below_80_streak_months"],
                "worst_employee": row["worst_employee"],
            }
            for row in rows if row["month"] == latest_manager_month
        ]
        manager_attention.sort(key=lambda row: (
            -row["below_80_count"], -row["below_80_gap"], row["manager_code"],
        ))

    # 10/09/2026 (C46): cau hoi "don vi nao tang headcount nhung nang suat giam" khong co tool tong
    # hop san - model phai tu goi workforce_productivity NHIEU LAN (group_by khac nhau, months_back
    # khac nhau) de tu do tim, het ngan sach thoi gian truoc khi tra loi duoc (bat qua thuc te: 5 lan
    # goi lien tiep roi timeout). Tinh san danh sach nay tu TAP DAY DU (truoc khi cat theo limit) de
    # model chi can 1 lan goi la co ngay cau tra loi, giong cach da lam voi declining_employees.
    headcount_up_productivity_down = []
    if group_by in {"manager", "area"}:
        for key, ms in by_group.items():
            for month in sorted(ms):
                r = ms[month]
                prev = ms.get(_month_add(month, -1))
                if month > decline_evaluated_through:
                    continue
                if (not prev or prev.get("revenue_per_employee") is None
                        or r.get("revenue_per_employee") is None):
                    continue
                if r["headcount"] > prev["headcount"] and r["revenue_per_employee"] < prev["revenue_per_employee"]:
                    headcount_up_productivity_down.append({
                        "group_code": r["group_code"], "group_name": r["group_name"], "month": month,
                        "headcount": r["headcount"], "previous_headcount": prev["headcount"],
                        "revenue_per_employee": r["revenue_per_employee"],
                        "previous_revenue_per_employee": prev["revenue_per_employee"],
                        "revenue_per_employee_pct_change": (
                            (r["revenue_per_employee"] - prev["revenue_per_employee"])
                            / abs(prev["revenue_per_employee"]) * 100
                            if prev["revenue_per_employee"] else None
                        ),
                    })
        headcount_up_productivity_down.sort(
            key=lambda row: (row["revenue_per_employee_pct_change"] is None,
                             row["revenue_per_employee_pct_change"] or 0))

    rows, so_bi_cat = _giu_top_don_vi(rows, "group_code", "actual", limit)
    return {
        "month_from": month_from, "month_to": month_to, "group_by": group_by,
        "headcount_up_productivity_down": headcount_up_productivity_down,
        "headcount_up_productivity_down_definition": (
            "Danh sach (nhom, thang) co headcount THANG NAY > THANG TRUOC lien ke VA "
            "revenue_per_employee THANG NAY < THANG TRUOC - tinh tren TOAN BO tap nhom truoc khi cat "
            "theo limit. Chi co gia tri khi group_by='manager' hoac 'area'; rong voi group_by khac. "
            "Sap xep theo % giam nang suat manh nhat truoc."
            if group_by in {"manager", "area"} else None
        ),
        "month_to_is_partial": month_to_is_partial,
        "decline_evaluated_through": decline_evaluated_through,
        "partial_month_excluded_from_decline_streak": month_to_is_partial,
        "rows": rows, "so_nhom_khong_hien": so_bi_cat,
        "declining_employee_count": declining_employee_count,
        "declining_employees": declining_employees,
        "declining_employees_truncated": declining_employee_count > len(declining_employees),
        "declining_employees_not_shown": max(0, declining_employee_count - len(declining_employees)),
        "declining_count_by_streak": declining_count_by_streak,
        "decline_cause_data_available": (any(r.get("cause_data_available") for r in declining_employees)
                                         if group_by == "employee" else None),
        "decline_cause_limitation": (
            "cause so thang cuoi chuoi voi thang lien truoc tren HOA DON OTC cua chinh NV: khach, "
            "don/khach (tan suat), AOV - ba he so nhan lai bang doanh thu hoa don. Doanh thu hoa don "
            "co the lech doanh so bang luong; cause=None la khong co hoa don de phan ra, khong suy dien."
            if group_by == "employee" else None
        ),
        "manager_attention": manager_attention,
        "manager_attention_evaluated_month": manager_attention_evaluated_month,
        "manager_attention_period_fallback": manager_attention_period_fallback,
        "manager_attention_definition": (
            "Tinh tren tung nhan vien co target trong moi doi: dem nguoi actual < 80% target, "
            "cong gap target-actual cua chinh nhom do, va giu nguoi co gap lon nhat. Danh sach "
            "duoc tinh truoc khi cat rows. Neu thang yeu cau khong co bat ky target nao, "
            "manager_attention tu lui ve thang gan nhat co target va danh dau period_fallback=true; "
            "khong bao 0 nguoi duoi 80%. below_80_streak_months la so thang lien tiep ca doi "
            "co achievement_pct < 80%."
            if group_by == "manager" else None
        ),
        "definition": ("Headcount = nhan vien TDV/CTV/CS co dong trong snapshot luong thang; "
                       "revenue_per_employee = tong doanh so / headcount. Decline streak chi tang "
                       "khi cac thang lien tiep deu giam. Voi group_by=employee, "
                       "declining_employee_count/declining_employees duoc tinh tren toan bo nhan vien "
                       "truoc khi cat rows. decline_streak_months = so LAN giam lien tiep so voi thang "
                       "lien truoc; thieu thang thi dut chuoi. 'Giam lien tiep N thang' = streak >= N "
                       "(can N+1 thang lien nhau), dem san o declining_count_by_streak; danh sach gom tu "
                       "streak >= 2 de thay nguoi sap vao chuoi - KHONG gop nhom >=2 thanh 'giam 3 thang'. "
                       "Neu month_to_is_partial=true, thang MTD van co trong rows nhung bi loai khoi "
                       "summary chuoi giam; decline_evaluated_through la thang tron da dung."),
        "limitations": [
            "Chua co FACT_PhatSinhNhanVien/lich su chuyen vung chot chuan, nen khong tach duoc anh huong vao-ra-chuyen dia ban.",
            "Ngay vao lam lay tu dim_nhanvien; dong thieu start_date co avg_tenure_months=None va khong duoc suy dien.",
        ],
        "pham_vi_kenh": "OTC", "data_as_of": latest_data_date(),
    }


def priority_gap_actions(as_of_date: str = None, limit: int = 20,
                         scope_area_code: str = None, scope_channel: str = None,
                         scope_employee_code: str = None) -> dict:
    """Ba danh sach uu tien dong gap: khach hang, san pham va nhan vien.

    Gap khach/san pham = binh quan doanh thu 3 thang tron truoc tru doanh thu MTD ky dang xem.
    Gap nhan vien = target thang - doanh so thang tu snapshot luong/KPI.
    """
    as_of_date = (as_of_date or latest_data_date())[:10]
    limit = max(1, min(int(limit or 20), 100))
    month_start = f"{as_of_date[:7]}-01"
    prior_start = f"{_month_add(as_of_date[:7], -3)}-01"
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    parts, params = [], []
    if scope_channel != "ETC":
        parts.append(
            "SELECT v.doc_date,v.customer_code,v.item_code,v.amount9 revenue "
            "FROM vhoadon_otc v " + _otc_area_join("v", scope_area_code) +
            f" WHERE v.doc_date BETWEEN ? AND ?{suffix}")
        params.extend((prior_start, as_of_date) + suffix_params)
    if scope_channel != "OTC":
        parts.append(
            "SELECT v.doc_date,v.customer_code,v.item_code,v.amount9 revenue "
            "FROM vhoadon_etc v " + _etc_area_join("v", scope_area_code) +
            f" WHERE v.doc_date BETWEEN ? AND ?{suffix}")
        params.extend((prior_start, as_of_date) + suffix_params)

    def dimension_gap(column: str) -> list:
        if not parts:
            return []
        raw = _q(
            "WITH x AS (" + " UNION ALL ".join(parts) + ") "
            f"SELECT {column} code,"
            "SUM(CASE WHEN doc_date < ? THEN revenue ELSE 0 END)/3.0 prior_avg,"
            "SUM(CASE WHEN doc_date >= ? THEN revenue ELSE 0 END) current_revenue "
            "FROM x GROUP BY " + column,
            tuple(params) + (month_start, month_start),
        )
        out = []
        for row in raw:
            code = row.get("code")
            if not code or not str(code).strip():
                continue
            prior_avg = _f(row.get("prior_avg")); current = _f(row.get("current_revenue"))
            gap = prior_avg - current
            if gap > 0:
                out.append({"code": code, "gap": gap, "baseline_3m_avg": prior_avg,
                            "current_revenue": current})
        out.sort(key=lambda row: (-row["gap"], row["code"]))
        return out[:limit]

    customer_actions = dimension_gap("customer_code")
    product_actions = dimension_gap("item_code")
    if customer_actions:
        names = _customer_names([r["code"] for r in customer_actions])
        for row in customer_actions:
            row["name"] = names.get(row["code"]) or row["code"]
    if product_actions:
        ph = ",".join("?" for _ in product_actions)
        names = {r["code"]: r["name"] for r in _q(
            f"SELECT code,name FROM brv_sanpham WHERE code IN ({ph})",
            tuple(r["code"] for r in product_actions))}
        for row in product_actions:
            row["name"] = names.get(row["code"]) or row["code"]

    employee_actions = []
    fdate = _fact_date_le(as_of_date)
    if fdate:
        employee_codes = None
        if scope_employee_code:
            employee_codes = [r["employee_code"] for r in _team_of_qlv(scope_employee_code, fdate)]
            if not employee_codes:
                raise KhongXacDinhDuocDoi(f"Khong xac dinh duoc doi cua {scope_employee_code}.")
        snaps = ("SELECT employee_code,MAX(save_date) d FROM fact_thongketinhluong "
                 "WHERE save_date<=? AND substr(save_date,1,7)=? GROUP BY employee_code")
        sql = ("WITH s AS (" + snaps + ") SELECT f.employee_code code,"
               "COALESCE(f.employee_name,nv.name) name,f.month_sale_amount actual,f.month_sale_target target "
               "FROM fact_thongketinhluong f JOIN s ON s.employee_code=f.employee_code AND s.d=f.save_date "
               "LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
               f"WHERE UPPER(COALESCE(f.position_code,'')) IN ({_tier_ph()})")
        p = [fdate, as_of_date[:7], *_EMPLOYEE_TIER_POSITIONS]
        if scope_area_code:
            sql += " AND f.area_code=?"; p.append(scope_area_code)
        if employee_codes:
            sql += f" AND f.employee_code IN ({','.join('?' for _ in employee_codes)})"; p.extend(employee_codes)
        for row in _q(sql, tuple(p)):
            target, actual = _f(row.get("target")), _f(row.get("actual"))
            if target > actual:
                employee_actions.append({"code": row["code"], "name": row["name"] or row["code"],
                                         "gap": target - actual, "target": target, "actual": actual})
        employee_actions.sort(key=lambda row: (-row["gap"], row["code"]))
        employee_actions = employee_actions[:limit]

    combined = ([{"dimension": "KHACH_HANG", **r} for r in customer_actions] +
                [{"dimension": "SAN_PHAM", **r} for r in product_actions] +
                [{"dimension": "NHAN_VIEN", **r} for r in employee_actions])
    return {
        "as_of": as_of_date, "month_start": month_start,
        "prior_window": {"from": prior_start, "to": _month_add(as_of_date[:7], -1)},
        "customer_actions": customer_actions, "product_actions": product_actions,
        "employee_actions": employee_actions, "rows": combined,
        "definition": "Gap KH/SP = binh quan 3 thang tron truoc - doanh thu MTD; gap NV = target - actual snapshot luong.",
        "warning": "Danh sach uu tien la xep hang theo gap quan sat duoc, khong phai cam ket nhu cau hay du bao.",
        "data_as_of": latest_data_date(),
    }
def customer_assignment_change(as_of_date: str = None, lookback_months: int = 3,
                               limit: int = 100, scope_area_code: str = None,
                               scope_channel: str = None,
                               scope_employee_code: str = None) -> dict:
    """C28/S91: tach tang truong nhom khach giu nguyen NV khoi nhom doi NV."""
    requested_date = str(as_of_date or "").strip()[:10]
    if requested_date:
        current_month = requested_date[:7]
        requested_day = dt.date.fromisoformat(requested_date)
        if requested_day.day < _last_day_of_month(requested_day.year, requested_day.month):
            current_month = _month_add(current_month, -1)
            period_selection = "THANG_TRON_TRUOC_NGAY_DUOC_CHI_DINH"
        else:
            period_selection = "THANG_DUOC_CHI_DINH_DA_TRON"
    else:
        current_month = _latest_complete_revenue_month()
        period_selection = "THANG_TRON_GAN_NHAT"

    lookback_months = max(1, min(int(lookback_months or 3), 6))
    limit = max(1, min(int(limit or 100), 500))
    current_from = f"{_month_add(current_month, -(lookback_months - 1))}-01"
    _, current_to = _month_bounds(current_month)
    previous_to_month = _month_add(current_month, -lookback_months)
    previous_from = f"{_month_add(previous_to_month, -(lookback_months - 1))}-01"
    _, previous_to = _month_bounds(previous_to_month)

    if scope_channel and str(scope_channel).upper() == "ETC":
        return {
            "status": "SOURCE_GAP_ETC_ASSIGNMENT_HISTORY", "available_channel": "OTC",
            "note": "Chua co lich su phan cong ETC da duoc chot de loai anh huong chuyen khach/NV.",
        }

    available = _q("SELECT MIN(doc_date) min_date,MAX(doc_date) max_date FROM vhoadon_otc")[0]
    available_from, available_to = available.get("min_date"), available.get("max_date")
    if not available_from or available_from > previous_from or not available_to or available_to < current_to:
        return {
            "status": "SOURCE_GAP_INCOMPLETE_ASSIGNMENT_HISTORY", "mode": "assignment_change",
            "channel": "OTC", "required_period": {"from": previous_from, "to": current_to},
            "available_detail_period": {"from": available_from, "to": available_to},
            "note": (
                "Du lieu hoa don chi tiet hien khong phu du hai cua so so sanh. Khong duoc coi "
                "khach khong xuat hien trong phan lich su bi thieu la khach moi/chuyen NV."
            ),
        }

    scope_sql, scope_params = _scope_clause(scope_area_code)
    employee_sql, employee_params = _employee_scope_clause(
        scope_employee_code, "v", as_of=current_to,
    )
    suffix = scope_sql + employee_sql
    rows = _q(
        "SELECT CASE WHEN v.doc_date BETWEEN ? AND ? THEN 'PREVIOUS' ELSE 'CURRENT' END period,"
        "v.customer_code,COALESCE(NULLIF(TRIM(v.employee_code),''),'UNKNOWN') employee_code,"
        "SUM(v.amount9) revenue "
        f"FROM vhoadon_otc v {_otc_area_join('v', scope_area_code)} "
        "WHERE v.doc_date BETWEEN ? AND ? AND v.customer_code IS NOT NULL "
        f"AND TRIM(v.customer_code)<>''{suffix} "
        "GROUP BY period,v.customer_code,COALESCE(NULLIF(TRIM(v.employee_code),''),'UNKNOWN')",
        (previous_from, previous_to, previous_from, current_to) + scope_params + employee_params,
    )

    grouped = {}
    for row in rows:
        key = (row["customer_code"], row["period"])
        grouped.setdefault(key, []).append({
            "employee_code": row["employee_code"], "revenue": _f(row["revenue"]),
        })
    primary = {}
    for key, candidates in grouped.items():
        total = sum(item["revenue"] for item in candidates)
        chosen = sorted(candidates, key=lambda item: (-item["revenue"], item["employee_code"]))[0]
        primary[key] = {"employee_code": chosen["employee_code"], "revenue": total}

    customers = sorted({customer for customer, _ in primary})
    buckets = {
        "STABLE_EMPLOYEE": [], "CHANGED_EMPLOYEE": [], "CURRENT_ONLY": [],
        "PREVIOUS_ONLY": [], "UNKNOWN_ASSIGNMENT": [],
    }
    stable_by_employee = {}
    detail = []
    for customer in customers:
        previous = primary.get((customer, "PREVIOUS"))
        current = primary.get((customer, "CURRENT"))
        prev_revenue = _f(previous and previous["revenue"])
        cur_revenue = _f(current and current["revenue"])
        prev_employee = previous and previous["employee_code"]
        cur_employee = current and current["employee_code"]
        if "UNKNOWN" in (prev_employee, cur_employee):
            group = "UNKNOWN_ASSIGNMENT"
        elif not previous:
            group = "CURRENT_ONLY"
        elif not current:
            group = "PREVIOUS_ONLY"
        elif prev_employee == cur_employee:
            group = "STABLE_EMPLOYEE"
        else:
            group = "CHANGED_EMPLOYEE"
        item = {
            "customer_code": customer, "previous_primary_employee": prev_employee,
            "current_primary_employee": cur_employee, "previous_revenue": prev_revenue,
            "current_revenue": cur_revenue, "delta": cur_revenue - prev_revenue, "group": group,
        }
        buckets[group].append(item)
        detail.append(item)
        if group == "STABLE_EMPLOYEE":
            unit = stable_by_employee.setdefault(cur_employee, {
                "employee_code": cur_employee, "customers": 0,
                "previous_revenue": 0.0, "current_revenue": 0.0,
            })
            unit["customers"] += 1
            unit["previous_revenue"] += prev_revenue
            unit["current_revenue"] += cur_revenue

    groups = []
    for name, items in buckets.items():
        previous_revenue = sum(item["previous_revenue"] for item in items)
        current_revenue = sum(item["current_revenue"] for item in items)
        groups.append({
            "group": name, "customers": len(items), "previous_revenue": previous_revenue,
            "current_revenue": current_revenue, "delta": current_revenue - previous_revenue,
            "growth_pct": ((current_revenue - previous_revenue) / previous_revenue * 100
                           if previous_revenue else None),
        })
    stable_units = []
    for unit in stable_by_employee.values():
        unit["delta"] = unit["current_revenue"] - unit["previous_revenue"]
        unit["growth_pct"] = (unit["delta"] / unit["previous_revenue"] * 100
                              if unit["previous_revenue"] else None)
        stable_units.append(unit)
    stable_units.sort(key=lambda item: (-abs(item["delta"]), item["employee_code"]))
    total_previous = sum(item["previous_revenue"] for item in detail)
    total_current = sum(item["current_revenue"] for item in detail)
    group_previous = sum(item["previous_revenue"] for item in groups)
    group_current = sum(item["current_revenue"] for item in groups)
    stable = next(item for item in groups if item["group"] == "STABLE_EMPLOYEE")
    return {
        "status": "PARTIAL_SOURCE_LIMIT", "mode": "assignment_change", "channel": "OTC",
        "period_selection": period_selection,
        "current_period": {"from": current_from, "to": current_to},
        "previous_period": {"from": previous_from, "to": previous_to},
        "groups": groups, "stable_customer_growth": stable,
        "stable_growth_by_employee": stable_units[:limit],
        "changed_customer_samples": sorted(
            buckets["CHANGED_EMPLOYEE"], key=lambda item: -abs(item["delta"]),
        )[:limit],
        "reconciliation": {
            "total_previous_revenue": total_previous, "total_current_revenue": total_current,
            "total_delta": total_current - total_previous,
            "group_previous_gap": group_previous - total_previous,
            "group_current_gap": group_current - total_current,
            "passed": abs(group_previous - total_previous) <= 1 and abs(group_current - total_current) <= 1,
        },
        "definition": (
            "Tang truong it bi xao tron nhat = doanh thu cua cac khach co cung mot NV chinh o ca hai "
            "cua so. NV chinh la NV co doanh thu cao nhat cua khach trong cua so; day la quy uoc "
            "phan tich, khong phai lich su phan cong chot chuan."
        ),
        "limitations": (
            "Kho chua co lich su assignment dia ban/QLV chot chuan, nen KHONG the noi da loai sach "
            "anh huong doi dia ban. Khach bi chuyen NV roi ngung mua se nam o PREVIOUS_ONLY, vi vay "
            "anh huong ban giao co the bi danh gia thap. Chi duoc trinh bay day la tang truong nhom "
            "khach giu nguyen NV chinh, khong goi la tang truong thuc tuyet doi cua tung don vi."
        ),
        "data_as_of": latest_data_date(),
    }


def four_customer_priorities(as_of_date: str = None, limit: int = 20,
                             scope_area_code: str = None, scope_channel: str = None,
                             scope_employee_code: str = None) -> dict:
    """S83/V28: tach ro bon muc tieu khach hang, khong tra mot danh sach gap chung chung.

    "Tuan nay" chua co quy uoc DNH chot (tuan lich hay 01-07/08-14...), vi vay cac phep
    xep hang ben duoi dung den ngay ``as_of`` va phai hien ro day la MTD, khong tu nhan la tuan.
    """
    as_of_date = (as_of_date or latest_data_date())[:10]
    limit = max(1, min(int(limit or 20), 100))

    # 1. Giu khach lon: phai dat ca hai dieu kien: MTD giam va baseline >= binh quan TOAN BO
    # khach co mua trong 3 thang truoc. Khong lay top gap chung cua S84 roi goi tat ca la "khach lon".
    month_start = f"{as_of_date[:7]}-01"
    prior_start = f"{_month_add(as_of_date[:7], -3)}-01"
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    retention_parts, retention_params = [], []
    if scope_channel != "ETC":
        retention_parts.append("SELECT v.doc_date,v.customer_code,v.amount9 revenue FROM vhoadon_otc v " +
                               _otc_area_join("v", scope_area_code) +
                               f" WHERE v.doc_date BETWEEN ? AND ?{suffix}")
        retention_params.extend((prior_start, as_of_date) + suffix_params)
    if scope_channel != "OTC":
        retention_parts.append("SELECT v.doc_date,v.customer_code,v.amount9 revenue FROM vhoadon_etc v " +
                               _etc_area_join("v", scope_area_code) +
                               f" WHERE v.doc_date BETWEEN ? AND ?{suffix}")
        retention_params.extend((prior_start, as_of_date) + suffix_params)
    retention = []
    if retention_parts:
        retention_rows = _q(
            "WITH lines AS (" + " UNION ALL ".join(retention_parts) + "), per_customer AS ("
            "SELECT customer_code,SUM(CASE WHEN doc_date<? THEN revenue ELSE 0 END)/3.0 baseline_3m_avg,"
            "SUM(CASE WHEN doc_date>=? THEN revenue ELSE 0 END) current_revenue "
            "FROM lines WHERE customer_code IS NOT NULL AND TRIM(customer_code)<>'' GROUP BY customer_code"
            "), benchmark AS (SELECT AVG(baseline_3m_avg) avg_baseline_3m FROM per_customer "
            "WHERE baseline_3m_avg>0) SELECT p.customer_code,p.baseline_3m_avg,p.current_revenue,"
            "p.baseline_3m_avg-p.current_revenue revenue_gap,b.avg_baseline_3m FROM per_customer p "
            "CROSS JOIN benchmark b WHERE p.baseline_3m_avg>=b.avg_baseline_3m "
            "AND p.current_revenue<p.baseline_3m_avg ORDER BY revenue_gap DESC,p.customer_code LIMIT ?",
            tuple(retention_params + [month_start, month_start, limit]))
        retention_names = _customer_names([r["customer_code"] for r in retention_rows])
        retention = [{
            "customer_code": r["customer_code"],
            "customer_name": retention_names.get(r["customer_code"]) or r["customer_code"],
            "baseline_3m_avg": _f(r["baseline_3m_avg"]), "current_revenue": _f(r["current_revenue"]),
            "revenue_gap": _f(r["revenue_gap"]), "scope_avg_baseline_3m": _f(r["avg_baseline_3m"]),
            "criterion": "MTD thap hon baseline va baseline >= binh quan 3 thang cua toan bo khach trong pham vi.",
        } for r in retention_rows]

    # 2. Tai kich hoat: phan loai tu luong khach, khong suy dien tu mot thang doanh thu am/0.
    movement = customer_movement(month=as_of_date[:7], history_months=12,
                                 movement_filter="REACTIVATED", limit=limit,
                                 scope_area_code=scope_area_code, scope_channel=scope_channel,
                                 scope_employee_code=scope_employee_code)
    reactivation = [{
        "customer_code": r["customer_code"], "customer_name": r["customer_name"],
        "current_revenue": r["current_revenue"],
        "inactive_months_before_reactivation": r.get("inactive_months_before_reactivation"),
        "last_active_month_before_reactivation": r.get("last_active_month_before_reactivation"),
        "criterion": "Da mua lai sau it nhat mot thang khong mua trong cua so du lieu.",
    } for r in movement.get("customers", [])]

    # 3. Thu no: dung snapshot cong no chuan. KHONG dung customer_revenue_debt_risk o day vi tool
    # do co them dieu kien doanh thu giam + nguong cao, se bo sot khach no qua han can xu ly trong S83.
    debt_unavailable = None
    try:
        debt_where = ["c.snapshot_date=(SELECT MAX(snapshot_date) FROM fact_congno_khachhang)",
                      "COALESCE(c.total_overdue,0)>0"]
        debt_params = []
        channel = str(scope_channel or "ALL").upper()
        if channel in {"OTC", "ETC"}:
            debt_where.append("c.sales_channel=?")
            debt_params.append(channel)
        if scope_area_code:
            region_key = next((key for key, markers in REGION_SQL_MARKERS.items()
                               if scope_area_code in markers), None)
            markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code])
            debt_where.append(f"c.area_code IN ({','.join('?' for _ in markers)})")
            debt_params.extend(markers)
        if scope_employee_code:
            dms_ids = _get_team_dms_ids(scope_employee_code, as_of_date)
            if dms_ids:
                debt_where.append("EXISTS (SELECT 1 FROM dms_khachhang kh WHERE kh.code=c.customer_code "
                                  f"AND kh.emp_code IN ({','.join('?' for _ in dms_ids)}))")
                debt_params.extend(dms_ids)
            else:
                raise KhongXacDinhDuocDoi(f"Khong xac dinh duoc doi cua {scope_employee_code}.")
        debt_rows = _q(
            "SELECT c.customer_code,MAX(c.customer_name) customer_name,SUM(c.balance_end) balance_end,"
            "SUM(c.total_overdue) overdue,MAX(c.snapshot_at) snapshot_at "
            "FROM fact_congno_khachhang c WHERE " + " AND ".join(debt_where) +
            " GROUP BY c.customer_code ORDER BY overdue DESC,balance_end DESC LIMIT ?",
            tuple(debt_params + [limit]))
        collection = [{
            "customer_code": r["customer_code"], "customer_name": r.get("customer_name") or r["customer_code"],
            "overdue": _f(r["overdue"]), "balance_end": _f(r["balance_end"]),
            "snapshot_at": r.get("snapshot_at"),
            "criterion": "No qua han cao nhat, theo snapshot cong no chuan.",
        } for r in debt_rows]
    except Exception as exc:  # Kho dev co the chua dong bo snapshot cong no.
        collection = []
        debt_unavailable = f"Khong doc duoc snapshot cong no: {exc}"

    # 4. Ban cheo: chi goi la co hoi khi co cap SKU da tung mua cung, khong gan nhu cau cho khach.
    cross = cross_sell_opportunities(as_of_date=as_of_date, lookback_months=3,
                                    opportunity_limit=limit, pair_limit=20,
                                    scope_area_code=scope_area_code,
                                    scope_channel=scope_channel,
                                    scope_employee_code=scope_employee_code)
    cross_sell = [{
        "customer_code": r["customer_code"], "customer_name": r.get("customer_name") or r["customer_code"],
        "has_item": r["has_item"], "has_item_name": r.get("has_item_name"),
        "missing_item": r["missing_item"], "missing_item_name": r.get("missing_item_name"),
        "shared_customers": r["shared_customers"],
        "attach_rate_pct": r["attach_rate_pct"],
        "criterion": "Khach da mua mot SKU cua cap co khach chung, nhung chua mua SKU con lai.",
    } for r in cross.get("opportunities", [])]

    # Mot khach co the trung nhieu muc tieu. Hang tong hop de uu tien nhung GIU cac bang rieng
    # de nguoi dung thay duoc ly do, dung nghia cua S83.
    combined = {}
    for label, rows in (("GIU_KHACH_LON", retention), ("TAI_KICH_HOAT", reactivation),
                        ("THU_NO", collection), ("BAN_CHEO", cross_sell)):
        for row in rows:
            item = combined.setdefault(row["customer_code"], {
                "customer_code": row["customer_code"], "customer_name": row.get("customer_name"),
                "priority_targets": [],
            })
            item["priority_targets"].append(label)
    rows = list(combined.values())
    rows.sort(key=lambda r: (-len(r["priority_targets"]), r["customer_code"]))
    for row in rows:
        row["matched_target_count"] = len(row["priority_targets"])

    return {
        "status": "PARTIAL" if debt_unavailable else "OK",
        "as_of": as_of_date,
        "period_definition": "MTD den ngay as_of; chua duoc goi la 'tuan nay' vi DNH chua chot quy uoc tuan.",
        "retention_actions": retention,
        "reactivation_actions": reactivation,
        "collection_actions": collection,
        "cross_sell_actions": cross_sell,
        "rows": rows[:limit],
        "collection_unavailable_reason": debt_unavailable,
        "definition": "Moi danh sach co tieu chi rieng; mot khach co the xuat hien o nhieu muc tieu.",
        "data_as_of": latest_data_date(),
    }


def product_monthly_performance(as_of_date: str = None, months_back: int = 3, limit: int = 10,
                                scope_area_code: str = None, scope_channel: str = None,
                                scope_employee_code: str = None) -> dict:
    """S21/V29: top/bottom SKU tung thang va dong gop tang/giam so voi thang truoc."""
    as_of_date = (as_of_date or latest_data_date())[:10]
    months_back = max(2, min(int(months_back or 3), 12))
    limit = max(1, min(int(limit or 10), 50))
    first_month = _month_add(as_of_date[:7], -(months_back - 1))
    # Can them mot thang nen de tinh delta cua thang dau tien dang hien thi.
    query_from = f"{_month_add(first_month, -1)}-01"
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
    suffix, suffix_params = scope_sql + emp_sql, scope_params + emp_params
    parts, params = [], []
    if scope_channel != "ETC":
        parts.append("SELECT substr(v.doc_date,1,7) ym,v.item_code,v.amount9 "
                     "FROM vhoadon_otc v " + _otc_area_join("v", scope_area_code) +
                     f" WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}")
        params.extend((query_from, as_of_date) + suffix_params)
    if scope_channel != "OTC":
        parts.append("SELECT substr(v.doc_date,1,7) ym,v.item_code,v.amount9 "
                     "FROM vhoadon_etc v " + _etc_area_join("v", scope_area_code) +
                     f" WHERE v.doc_date BETWEEN ? AND ? AND COALESCE(v.unit_price,0)>0{suffix}")
        params.extend((query_from, as_of_date) + suffix_params)
    if not parts:
        return {"error": "Khong co kenh nao kha dung."}
    raw = _q("WITH lines AS (" + " UNION ALL ".join(parts) + ") "
             "SELECT ym,item_code,SUM(amount9) revenue FROM lines "
             "WHERE item_code IS NOT NULL AND TRIM(item_code)<>'' GROUP BY ym,item_code",
             tuple(params))
    by_month = {}
    all_codes = set()
    for r in raw:
        by_month.setdefault(r["ym"], {})[r["item_code"]] = _f(r["revenue"])
        all_codes.add(r["item_code"])
    names = {}
    if all_codes:
        placeholders = ",".join("?" for _ in all_codes)
        names = {r["code"]: r["name"] for r in _q(
            f"SELECT code,name FROM brv_sanpham WHERE code IN ({placeholders})", tuple(all_codes))}
    current_month = as_of_date[:7]
    current_is_complete = dt.date.fromisoformat(as_of_date) == _month_end(dt.date.fromisoformat(as_of_date))
    months = []
    for offset in range(months_back):
        ym = _month_add(first_month, offset)
        values = by_month.get(ym, {})
        previous = by_month.get(_month_add(ym, -1), {})
        entries = [{
            "item_code": code, "item_name": names.get(code) or code, "revenue": revenue,
            "revenue_delta_vs_previous_month": revenue - _f(previous.get(code)),
        } for code, revenue in values.items()]
        top = sorted(entries, key=lambda r: (-r["revenue"], r["item_code"]))[:limit]
        bottom = sorted(entries, key=lambda r: (r["revenue"], r["item_code"]))[:limit]
        comparable = ym != current_month or current_is_complete
        months.append({
            "month": ym, "period_complete": comparable,
            "total_revenue": sum(values.values()),
            "top_products": top, "bottom_products": bottom,
            "largest_increase": sorted(entries, key=lambda r: (-r["revenue_delta_vs_previous_month"], r["item_code"]))[:limit] if comparable else [],
            "largest_decrease": sorted(entries, key=lambda r: (r["revenue_delta_vs_previous_month"], r["item_code"]))[:limit] if comparable else [],
        })
    return {
        "as_of": as_of_date, "months": months,
        "definition": "Top/bottom theo doanh thu thuan SKU cua tung thang. Tang/giam la chenh lech SKU voi thang truoc.",
        "warning": ("Thang dang chay chua du ngay nen chi hien top/bottom MTD; khong ket luan tang/giam voi thang tron."
                    if not current_is_complete else None),
        "data_as_of": latest_data_date(),
    }


def product_mix_performance(as_of_date: str = None, limit: int = 20,
                            scope_area_code: str = None, scope_channel: str = None,
                            scope_employee_code: str = None) -> dict:
    """S23/V31: tach hai danh sach 'phu rong, luong/don thap' va 'phu hep, AOV cao'."""
    as_of = dt.date.fromisoformat((as_of_date or latest_data_date())[:10])
    # Khong so sanh vai ngay MTD voi ca thang: cau V31 khong neu MTD, nen dung thang tron gan nhat.
    if as_of != _month_end(as_of):
        as_of = dt.date(as_of.year, as_of.month, 1) - dt.timedelta(days=1)
    base = customer_product_coverage(as_of_date=as_of.isoformat(), lookback_months=1,
                                     mode="product", limit=500,
                                     scope_area_code=scope_area_code, scope_channel=scope_channel,
                                     scope_employee_code=scope_employee_code)
    rows = [r for r in base.get("rows", []) if r.get("orders", 0) > 0 and r.get("revenue", 0) > 0]
    if not rows:
        return {"as_of": as_of.isoformat(), "month": as_of.strftime("%Y-%m"),
                "high_customer_low_quantity_per_order": [], "low_customer_high_aov": [],
                "product_metrics": [], "data_as_of": latest_data_date()}
    from statistics import median
    customer_median = float(median(r["customers"] for r in rows))
    quantity_per_order_median = float(median(r["quantity_per_order"] for r in rows
                                             if r["quantity_per_order"] is not None))
    aov_median = float(median(r["aov"] for r in rows if r["aov"] is not None))
    metrics = [{
        "item_code": r["code"], "item_name": r["name"], "revenue": r["revenue"],
        "customers": r["customers"], "orders": r["orders"], "quantity": r["quantity"],
        "quantity_per_order": r["quantity_per_order"], "aov": r["aov"],
    } for r in rows]
    high_customer_low_quantity = [r for r in metrics
                                  if r["customers"] >= customer_median
                                  and r["quantity_per_order"] is not None
                                  and r["quantity_per_order"] < quantity_per_order_median]
    low_customer_high_aov = [r for r in metrics
                             if r["customers"] < customer_median
                             and r["aov"] is not None and r["aov"] > aov_median]
    high_customer_low_quantity.sort(key=lambda r: (-r["customers"], r["quantity_per_order"], r["item_code"]))
    low_customer_high_aov.sort(key=lambda r: (-r["aov"], r["customers"], r["item_code"]))
    return {
        "as_of": as_of.isoformat(), "month": as_of.strftime("%Y-%m"),
        "high_customer_low_quantity_per_order": high_customer_low_quantity[:limit],
        "low_customer_high_aov": low_customer_high_aov[:limit],
        "product_metrics": sorted(metrics, key=lambda r: (-r["revenue"], r["item_code"]))[:limit],
        "benchmarks": {"customer_median": customer_median,
                       "quantity_per_order_median": quantity_per_order_median,
                       "aov_median": aov_median},
        "definition": ("Danh sach 1: so khach >= trung vi va luong/don < trung vi. Danh sach 2: "
                       "so khach < trung vi va AOV > trung vi. Su dung thang tron gan nhat."),
        "data_as_of": latest_data_date(),
    }


def _chat_luong_mapping_khach_theo_thang(month_to: str, months_back: int = 6,
                                         scope_area_code: str = None, scope_channel: str = None,
                                         scope_employee_code: str = None) -> list:
    """M28/S75: ty le khach khong gan TDV / ma NV la / khong map vung / khong co trong danh muc, theo
    TUNG THANG. Moi khach dem MOT LAN trong thang; mau so la so khach co hoa don thang do.

    13/09/2026: truoc day operational_data_quality chi dem tai MOT thoi diem, khong co chuoi theo
    thang nen M28 ("ty le ... theo thang") khong tra loi tron cau duoc."""
    month_from = _month_add(month_to, -(max(1, min(int(months_back or 6), 24)) - 1))
    date_from, _ = _month_bounds(month_from)
    _, date_to = _month_bounds(month_to)
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    parts, part_params = [], []
    for channel, table, kh_table in (("OTC", "vhoadon_otc", "dms_khachhang"),
                                     ("ETC", "vhoadon_etc", "dmssx_khachhang")):
        if scope_channel and scope_channel.upper() != channel:
            continue
        # LEFT JOIN de GIU lai dong thieu mapping - day chinh la thu dang dem.
        parts.append(
            "SELECT substr(v.doc_date,1,7) thang, v.customer_code, "
            "MAX(CASE WHEN v.employee_code IS NULL OR TRIM(v.employee_code)='' THEN 1 ELSE 0 END) khong_gan_tdv, "
            "MAX(CASE WHEN v.employee_code IS NOT NULL AND TRIM(v.employee_code)<>'' "
            "         AND nv.dmsid IS NULL AND sx.code IS NULL THEN 1 ELSE 0 END) ma_nv_la, "
            "MAX(CASE WHEN v.employee_code IS NOT NULL AND TRIM(v.employee_code)<>'' "
            "         AND nv.dmsid IS NULL AND sx.code IS NOT NULL THEN 1 ELSE 0 END) ma_nv_he_etc, "
            "MAX(CASE WHEN tp.area_code IS NULL THEN 1 ELSE 0 END) khong_map_vung, "
            "MAX(CASE WHEN kh.code IS NULL THEN 1 ELSE 0 END) khong_co_trong_danh_muc "
            f"FROM {table} v "
            f"LEFT JOIN {kh_table} kh ON kh.code=v.customer_code "
            "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
            "LEFT JOIN (SELECT DISTINCT dmsid FROM dim_nhanvien WHERE dmsid IS NOT NULL "
            "           AND TRIM(dmsid)<>'') nv ON nv.dmsid=v.employee_code "
            # 13/09/2026: nhan vien phia SX/ETC nam o BANG RIENG. Chi noi dim_nhanvien thi 28/29 ma
            # nguoi ban tren hoa don ETC thang 8 bi dem la "ma la" (228 khach MB), trong khi that su
            # chi 1 ma khong co o dau. Checker S75 cung dang thieu phep noi nay.
            "LEFT JOIN (SELECT DISTINCT code FROM dmssx_nhanvien) sx ON sx.code=v.employee_code "
            f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}{emp_sql} "
            "GROUP BY substr(v.doc_date,1,7), v.customer_code")
        part_params.append((date_from, date_to) + tuple(scope_params) + tuple(emp_params))
    if not parts:
        return []
    try:
        rows = _q(
            "WITH k AS (" + " UNION ALL ".join(parts) + ") "
            "SELECT thang, COUNT(DISTINCT customer_code) tong_khach, "
            "SUM(khong_gan_tdv) khong_gan_tdv, SUM(ma_nv_la) ma_nv_la, SUM(ma_nv_he_etc) ma_nv_he_etc, "
            "SUM(khong_map_vung) khong_map_vung, SUM(khong_co_trong_danh_muc) khong_co_trong_danh_muc, "
            "SUM(CASE WHEN khong_gan_tdv=1 OR khong_map_vung=1 OR khong_co_trong_danh_muc=1 THEN 1 ELSE 0 END) co_it_nhat_mot_loi "
            "FROM k GROUP BY thang ORDER BY thang",
            tuple(p for group in part_params for p in group))
    except sqlite3.OperationalError:
        # Kho cu chua co bang nhan vien SX/ETC: khong duoc lam hong ca tool chi vi phan bo sung nay.
        return []
    ket_qua = []
    for r in rows:
        tong = int(r["tong_khach"] or 0)
        muc = {k: (int(r[k] or 0) if k != "thang" else r[k]) for k in r.keys()}
        for ten in ("khong_gan_tdv", "ma_nv_la", "ma_nv_he_etc", "khong_map_vung",
                    "khong_co_trong_danh_muc", "co_it_nhat_mot_loi"):
            muc["ty_le_%s_pct" % ten] = (muc[ten] / tong * 100) if tong else None
        ket_qua.append(muc)
    return ket_qua


_NGUON_DON_HANG_CACHE = {"ts": None, "value": None}
_NGUON_DON_HANG_TTL = dt.timedelta(minutes=10)


def _trang_thai_nguon_don_hang() -> dict:
    """Doc thu nguon don DMS tren Bravo. Nang luc lay tu tinh trang THAT, cache 10 phut.

    11/09/2026 (ke hoach UAT, loi cheo M20/C54/V40): operational_data_quality tung ghi CUNG "bang
    DMS_DonHangHdr chua duoc dong bo" trong khi check_order_timing van doc bang do truc tiep Bravo."""
    now = dt.datetime.now()
    cache = _NGUON_DON_HANG_CACHE
    if cache["value"] is not None and cache["ts"] and now - cache["ts"] < _NGUON_DON_HANG_TTL:
        return cache["value"]
    try:
        _q_bravo("SELECT TOP (1) 1 AS ok FROM dbo.DMS_DonHangHdr", {})
        value = {"status": "OK"}
    except Exception as exc:
        value = {"status": "UNAVAILABLE", "reason": str(exc)[:200]}
    cache.update(ts=now, value=value)
    return value


_ETC_ITEM_TYPE_GROUP = "ItemTypeETC"
_BRAVO_SQL_ETC_ITEM_TYPE = (
    "SELECT v.GroupCode, k.Name AS NhomHang, SUM(v.Amount9) AS DoanhThu, COUNT(DISTINCT v.Stt) AS SoHoaDon\n"
    "FROM dbo.vHoaDonETCTotal v\n"
    "LEFT JOIN dbo.DIM_KeyClass k ON k.GroupCode = 'ItemTypeETC' AND k.Code = v.GroupCode\n"
    "WHERE v.DocDate >= '{tu}' AND v.DocDate < '{den}'\n"
    "GROUP BY v.GroupCode, k.Name\n"
    "ORDER BY DoanhThu DESC;"
)


def _etc_group_code(value) -> str:
    """Chuan hoa ma nhom: Bravo/SQLite co the tra 0, '0' hoac 0.0 cho cung mot ma."""
    if value is None or str(value).strip() == "":
        return None
    text_value = str(value).strip()
    try:
        number = float(text_value)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text_value


def etc_revenue_by_item_type(date_from: str, date_to: str, scope_area_code: str = None,
                             scope_channel: str = None) -> dict:
    """Doanh so ETC theo NHOM HANG (DIM_KeyClass, GroupCode='ItemTypeETC') trong [date_from, date_to].

    15/09/2026 (UAT dnh_etc 14:43 "Doanh so thang nay theo cac nhom hang"): kho truoc day KHONG co
    GroupCode tren hoa don ETC va khong co DIM_KeyClass, nen khong tool nao tra loi duoc - chatbot tra
    loi khong goi SQL va thieu Dau tu/Khai thac/Duoc lieu/Lao. Moi nhom trong danh muc deu duoc liet ke,
    ke ca doanh thu 0. Ma nhom tren hoa don KHONG co trong danh muc thi giu nguyen ma, KHONG tu dat ten:
    nhom "Khac" nguoi cham neu chua duoc DNH xac nhan tuong ung ma nao.
    Kem bravo_sql_doi_chieu: cau lenh chi doc tren Bravo de nguoi cham tu chay doi chieu."""
    if scope_channel and str(scope_channel).strip().upper() != "ETC":
        return {"not_applicable": True, "error": "Nhom hang ItemTypeETC chi co tren hoa don ETC."}
    day_from, day_to = str(date_from)[:10], str(date_to)[:10]
    den = (dt.date.fromisoformat(day_to) + dt.timedelta(days=1)).isoformat()
    result = {
        "date_from": day_from, "date_to": day_to,
        "nguon": "Hoa don ETC (vHoaDonETCTotal.GroupCode) noi danh muc DIM_KeyClass nhom ItemTypeETC",
        "bravo_sql_doi_chieu": _BRAVO_SQL_ETC_ITEM_TYPE.format(tu=day_from, den=den),
        "scope_area_code": scope_area_code,
        "data_as_of": latest_data_date(),
    }
    if "group_code" not in {r["name"] for r in _q("PRAGMA table_info(vhoadon_etc)")}:
        result.update(status="SOURCE_NOT_SYNCED", error=(
            "Kho chua dong bo ma nhom hang tren hoa don ETC. Chua the tach doanh so theo nhom; "
            "KHONG duoc ket luan nhom nao bang 0."))
        return result
    try:
        names = {_etc_group_code(r["code"]): r["name"] for r in _q(
            "SELECT code, name FROM dim_keyclass WHERE group_code=?", (_ETC_ITEM_TYPE_GROUP,))}
    except sqlite3.OperationalError:
        names = {}
    rows = _q("SELECT v.group_code gc, v.stt stt, v.customer_code cc, tp.area_code area, SUM(v.amount9) rev "
              "FROM vhoadon_etc v LEFT JOIN dmssx_khachhang kh ON kh.code=v.customer_code "
              "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
              "WHERE v.doc_date BETWEEN ? AND ? "
              "GROUP BY v.group_code, v.stt, v.customer_code, tp.area_code", (date_from, date_to))
    markers = None
    if scope_area_code:
        region_key = next((k for k, ms in REGION_SQL_MARKERS.items() if scope_area_code in ms), None)
        markers = set(REGION_SQL_MARKERS.get(region_key, [scope_area_code]))
    revenue, invoices, all_invoices = {}, {}, set()
    for r in rows:
        area = r["area"] or region_from_customer_code(r["cc"])
        if markers is not None and area not in markers:
            continue
        code = _etc_group_code(r["gc"])
        revenue[code] = revenue.get(code, 0.0) + _f(r["rev"])
        invoices.setdefault(code, set()).add(r["stt"])
        all_invoices.add(r["stt"])
    total = sum(revenue.values())

    def _row(code, name, note=None):
        value = revenue.get(code, 0.0)
        item = {"group_code": code, "group_name": name, "revenue": value,
                "invoices": len(invoices.get(code, ())),
                "share_pct": (value / total * 100) if total else 0.0}
        if note:
            item["ghi_chu"] = note
        return item

    def _sort_key(code):
        return (0, int(code)) if str(code).isdigit() else (1, str(code))

    groups = [_row(code, names[code]) for code in sorted(names, key=_sort_key)]
    groups += [_row(code, None, "Ma nhom khong co trong danh muc DIM_KeyClass ItemTypeETC - chua co ten, "
                                "can DNH xac nhan; khong tu dat ten.")
               for code in sorted((c for c in revenue if c is not None and c not in names), key=_sort_key)]
    if None in revenue:
        groups.append(_row(None, None, "Dong hoa don chua co ma nhom trong kho (dong bo truoc khi co cot "
                                       "hoac nguon de trong)."))
    groups.sort(key=lambda g: -g["revenue"])
    missing_share = (revenue.get(None, 0.0) / total * 100) if total else 0.0
    status = "OK"
    if not names:
        status = "PARTIAL_KEYCLASS_NOT_SYNCED"
        result["canh_bao_danh_muc"] = "Danh muc ten nhom (DIM_KeyClass) chua dong bo; chi co ma nhom."
    if revenue.get(None):
        status = "PARTIAL_GROUP_CODE_MISSING"
        result["canh_bao_ma_nhom"] = (
            f"{missing_share:.1f}% doanh thu ETC trong ky chua co ma nhom trong kho - can dong bo lai "
            "hoa don ETC; phan nay KHONG duoc chia vao nhom nao.")
    if day_from < _detail_cutoff():
        status = "PARTIAL_OLDER_THAN_DETAIL_WINDOW"
        result["canh_bao_ky"] = (
            f"Chi co ma nhom tren hoa don chi tiet tu {_detail_cutoff()}; phan truoc do da nen theo "
            "khach x thang, khong tach duoc nhom hang.")
    result.update(status=status, total_revenue=total, total_invoices=len(all_invoices), groups=groups)
    return result


def etc_contract_status(as_of_date: str = None, expiring_days: int = 90, limit: int = 50,
                        only_active: bool = True, scope_area_code: str = None,
                        scope_channel: str = None, scope_employee_code: str = None) -> dict:
    """C43/C44/M42: hop dong ETC - gia tri, da xuat hoa don, con lai, ty le thuc hien, sap het han.

    13/09/2026 - VI SAO CO TOOL NAY: ba cau cum H bi ghi la "chua co khoa lien ket hoa don voi hop
    dong/goi thau ETC" nen deu CHUA DAT, va router day chung sang bao cao dia ban (chi co doanh thu
    thuc hien). Kiem lai tren Bravo: vHoaDonETCTotal CO cot ContractId, do phu 100% so dong va 100%
    doanh thu T7-T8/2026, va 1.037/1.037 ma hop dong tren hoa don deu khop vHopDongETC. Khoa co that.

    NHUNG gia tri hop dong co ban ghi hong: 3/9.135 hop dong chiem 99,88% tong gia tri (HD 115627 ghi
    don gia 295.238.095.239d/don vi). Vi vay tool TACH RIENG cac hop dong co gia tri bat thuong
    (truoc VAT lech qua 5% so voi Quantity*UnitPrice, don gia > 1 ty, hoac sau VAT chenh truoc VAT qua
    2 lan - xem ghi chu 15/09/2026 trong SQL) ra khoi moi con so tong, khong am tham cong vao - nguoi
    doc thay ca hai phan.
    """
    as_of_date = (as_of_date or latest_data_date())[:10]
    expiring_days = max(1, min(int(expiring_days or 90), 720))
    limit = max(1, min(int(limit or 50), 200))
    params = {"as_of": as_of_date}
    dieu_kien_vung = ""
    if scope_area_code:
        dieu_kien_vung = (" AND EXISTS (SELECT 1 FROM dbo.DMSSX_KhachHang kh "
                          "JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId "
                          "WHERE kh.Code=hd.CustomerCode AND CASE WHEN tp.AreaCode IN (N'MB',N'MB1',N'MB2') "
                          "THEN N'MB' ELSE tp.AreaCode END=:area)")
        params["area"] = scope_area_code
    dieu_kien_nv = ""
    if scope_employee_code:
        dms_ids = _get_team_dms_ids(scope_employee_code, as_of_date)
        cho = []
        for i, ma in enumerate(dms_ids):
            params["nv%d" % i] = ma
            cho.append(":nv%d" % i)
        dieu_kien_nv = " AND (hd.EmpDMSCode1 IN (%s) OR hd.EmpDMSCode2 IN (%s))" % (
            ",".join(cho), ",".join(cho))
    sql = (
        "WITH dong AS ("
        " SELECT Id, RowId, MAX(Id0) Id0, MAX(ParentId) ParentId,"
        " MAX(CustomerCode) CustomerCode, MAX(DocNo0) DocNo0,"
        " MAX(FromDate0) FromDate0, MAX(ToDate0) ToDate0, MAX(StatusId) StatusId,"
        " MAX(EmpDMSCode1) EmpDMSCode1, MAX(EmpDMSCode2) EmpDMSCode2,"
        " MAX(AmountAfterVat) AmountAfterVat, MAX(AmountBefVat) AmountBefVat,"
        " MAX(Quantity) Quantity, MAX(UnitPrice) UnitPrice, MAX(ItemCode) ItemCode"
        " FROM dbo.vHopDongETC GROUP BY Id, RowId"
        "), hd AS ("
        # Id0 la hop dong goc; Id khac Id0 la phu luc/phien ban con (910 ho hop dong co phu luc,
        # kiem tra Bravo 21/09/2026). Phai cuon gia tri va hoa don cua moi Id con ve Id0. Neu group
        # theo Id, cung mot hop dong bi tach thanh nhieu dong va ty le thuc hien sai.
        " SELECT Id0 Id, MAX(CustomerCode) CustomerCode, MAX(DocNo0) DocNo,"
        " MIN(FromDate0) FromDate, MAX(ToDate0) ToDate, MAX(StatusId) StatusId,"
        " MAX(EmpDMSCode1) EmpDMSCode1,"
        # 15/09/2026: gia tri lay TRUOC VAT de cung goc voi Amount9 tren hoa don (T8/2026: Amount9 =
        # Quantity*UnitPrice, VAT nam rieng o Amount3 = 5,0%). Truoc do chia Amount9 cho AmountAfterVat nen
        # ty le thuc hien thap hon that ~5%.
        #
        # Kiem ban ghi hong cung doi (do tren Bravo 15/09, 9.138 hop dong). Cach cu "AmountAfterVat lech
        # Quantity*UnitPrice >5%" tach 70 hop dong nhung:
        #   - BO LOT HD 115627 (don gia 295 ty/don vi, so lieu tu khop nhau) -> tong phan "sach" ra
        #     2,96 trieu ty neu tinh ca hop dong het han;
        #   - tach oan 9 hop dong thue 8% (sau VAT lech truoc VAT ~7,4% la dung thue).
        # Luat moi: dong hong khi truoc VAT lech Quantity*UnitPrice >5%, HOAC don gia >1 ty/don vi, HOAC sau
        # VAT va truoc VAT chenh nhau qua 2 lan. Tach 60 hop dong, bat du 115627/112468/115175/122296; phan
        # sach tong 3.548 ty, hop dong lon nhat 107 ty.
        " MAX(EmpDMSCode2) EmpDMSCode2, SUM(AmountBefVat) GiaTri, COUNT(*) SoDong,"
        " COUNT(DISTINCT Id) SoPhienBan,"
        " COUNT(DISTINCT CASE WHEN Id<>Id0 OR ParentId IS NOT NULL THEN Id END) SoPhuLuc,"
        " SUM(CASE WHEN ABS(AmountBefVat - Quantity*UnitPrice) >"
        "          0.05*CASE WHEN ABS(AmountBefVat)>ABS(Quantity*UnitPrice)"
        "                    THEN ABS(AmountBefVat) ELSE ABS(Quantity*UnitPrice) END"
        "       OR UnitPrice > 1000000000"
        "       OR ABS(AmountAfterVat - AmountBefVat) >"
        "          0.5*CASE WHEN ABS(AmountAfterVat)>ABS(AmountBefVat)"
        "                   THEN ABS(AmountAfterVat) ELSE ABS(AmountBefVat) END"
        "     THEN 1 ELSE 0 END) SoDongLechGiaTri"
        " FROM dong GROUP BY Id0"
        "), map_hop_dong AS ("
        " SELECT DISTINCT Id ContractId, Id0 HopDongGocId FROM dong"
        "), sku_hop_dong AS ("
        " SELECT DISTINCT Id0, ItemCode FROM dong"
        "), dong_hoadon AS ("
        # 24/09/2026 (UAT C44): ContractId dung cho da so, nhung co chung tu GAN NHAM hop dong. HD
        # KT.06.G1.HD.TTYTTB-NH (khach DTH00244, 1 SKU) ban 2.000 roi tra lai du 2.000 -> rong 0, nhung
        # phieu tra TL 00006979 ngay 16/09 cua khach TBI00502, SKU 80440000007 lai mang ContractId cua
        # no -> tool bao da xuat -3,3 trieu (-4,8%). Do toan Bravo: 18 dong / 7 hop dong khac CA khach
        # LAN SKU = gan nham -> loai khoi da xuat, bao rieng. Khac ma khach nhung CUNG SKU (71 dong / 28
        # hop dong) phan lon la cung don vi hai ma (TTYT Nam Dinh NDI00011/NDI00018, BV 354, BV Pham
        # Ngoc Thach, TTYT Tam Binh doi ten sau sap nhap) -> van tinh, danh dau de nguoi doc biet.
        " SELECT m.HopDongGocId ContractId, s.Stt, s.DocDate, s.Amount9,"
        " CASE WHEN s.CustomerCode<>hd.CustomerCode THEN 1 ELSE 0 END KhacKhach,"
        " CASE WHEN k.ItemCode IS NULL THEN 1 ELSE 0 END KhacSku"
        " FROM dbo.vHoaDonETCTotal s"
        " JOIN map_hop_dong m ON m.ContractId=s.ContractId"
        " JOIN hd ON hd.Id=m.HopDongGocId"
        " LEFT JOIN sku_hop_dong k ON k.Id0=m.HopDongGocId AND k.ItemCode=s.ItemCode"
        " WHERE s.ContractId IS NOT NULL"
        "), hoadon AS ("
        " SELECT ContractId,"
        " SUM(CASE WHEN KhacKhach=1 AND KhacSku=1 THEN 0 ELSE Amount9 END) DaXuat,"
        " COUNT(DISTINCT CASE WHEN KhacKhach=1 AND KhacSku=1 THEN NULL ELSE Stt END) SoHoaDon,"
        " MAX(CASE WHEN KhacKhach=1 AND KhacSku=1 THEN NULL ELSE DocDate END) LanXuatCuoi,"
        " SUM(CASE WHEN KhacKhach=1 AND KhacSku=1 THEN 1 ELSE 0 END) SoDongGanNham,"
        " SUM(CASE WHEN KhacKhach=1 AND KhacSku=1 THEN Amount9 ELSE 0 END) TienGanNham,"
        " SUM(CASE WHEN KhacKhach=1 AND KhacSku=0 THEN Amount9 ELSE 0 END) TienKhacMaKhach"
        " FROM dong_hoadon GROUP BY ContractId"
        ") SELECT hd.Id, hd.DocNo, hd.CustomerCode, hd.StatusId, hd.SoDong, hd.SoDongLechGiaTri,"
        " hd.SoPhienBan, hd.SoPhuLuc,"
        " CONVERT(varchar(10), hd.FromDate, 120) FromDate,"
        " CONVERT(varchar(10), hd.ToDate, 120) ToDate,"
        " hd.GiaTri, ISNULL(h.DaXuat, 0) DaXuat, ISNULL(h.SoHoaDon, 0) SoHoaDon,"
        " ISNULL(h.SoDongGanNham, 0) SoDongGanNham, ISNULL(h.TienGanNham, 0) TienGanNham,"
        " ISNULL(h.TienKhacMaKhach, 0) TienKhacMaKhach,"
        " CONVERT(varchar(10), h.LanXuatCuoi, 120) LanXuatCuoi,"
        " DATEDIFF(day, CAST(:as_of AS date), hd.ToDate) ConLaiNgay"
        " FROM hd LEFT JOIN hoadon h ON h.ContractId = hd.Id"
        " WHERE 1=1" + dieu_kien_vung + dieu_kien_nv + " ORDER BY hd.Id")
    rows = _q_bravo(sql, params)

    hop_dong, bat_thuong = [], []
    for r in rows:
        gia_tri = _f(r["GiaTri"])
        da_xuat = _f(r["DaXuat"])
        con_lai_ngay = int(r["ConLaiNgay"]) if r["ConLaiNgay"] is not None else None
        muc = {
            "contract_id": r["Id"], "so_hop_dong": r["DocNo"], "customer_code": r["CustomerCode"],
            "tu_ngay": r["FromDate"], "den_ngay": r["ToDate"], "status_id": r["StatusId"],
            "so_phien_ban_hop_dong": int(r.get("SoPhienBan") or 1),
            "so_phu_luc": int(r.get("SoPhuLuc") or 0),
            "gia_tri_hop_dong": gia_tri, "da_xuat_hoa_don": da_xuat,
            "con_lai": gia_tri - da_xuat,
            "ty_le_thuc_hien_pct": (da_xuat / gia_tri * 100) if gia_tri else None,
            "so_hoa_don": int(r["SoHoaDon"] or 0), "lan_xuat_cuoi": r["LanXuatCuoi"],
            "con_lai_ngay": con_lai_ngay,
            "sap_het_han": con_lai_ngay is not None and 0 <= con_lai_ngay <= expiring_days,
            "da_het_han": con_lai_ngay is not None and con_lai_ngay < 0,
        }
        if int(r.get("SoDongGanNham") or 0) > 0:
            muc["chung_tu_gan_nham_da_loai"] = {
                "so_dong": int(r["SoDongGanNham"]), "so_tien": _f(r.get("TienGanNham")),
                "ly_do": "Chung tu mang ContractId cua hop dong nay nhung KHAC ca ma khach lan mat hang "
                         "- nghi gan nham, KHONG tinh vao da xuat."}
        if _f(r.get("TienKhacMaKhach")):
            muc["hoa_don_khac_ma_khach_van_tinh"] = _f(r.get("TienKhacMaKhach"))
        if int(r["SoDongLechGiaTri"] or 0) > 0:
            muc["ly_do_bat_thuong"] = (
                "Gia tri khong nhat quan o %d/%d dong (truoc VAT lech qua 5%% so voi Quantity*UnitPrice, "
                "don gia > 1 ty, hoac sau VAT chenh truoc VAT qua 2 lan) - gia tri hop dong KHONG dung "
                "de ket luan." % (int(r["SoDongLechGiaTri"]), int(r["SoDong"] or 0)))
            bat_thuong.append(muc)
        else:
            hop_dong.append(muc)

    dang_hieu_luc = [x for x in hop_dong if not x["da_het_han"]]
    xet = dang_hieu_luc if only_active else hop_dong
    sap_het = [x for x in xet if x["sap_het_han"]]
    chua_xuat = [x for x in xet if x["so_hoa_don"] == 0]
    thuc_hien_thap = sorted(
        [x for x in xet if x["ty_le_thuc_hien_pct"] is not None and x["ty_le_thuc_hien_pct"] < 50],
        key=lambda x: (x["ty_le_thuc_hien_pct"], -x["con_lai"]))
    gan_nham = [x for x in xet if x.get("chung_tu_gan_nham_da_loai")]
    return {
        "as_of": as_of_date, "nguong_sap_het_han_ngay": expiring_days,
        "chi_xet_hop_dong_con_hieu_luc": only_active,
        "nguon": ("vHopDongETC cuon hop dong/phu luc theo Id0 + "
                  "vHoaDonETCTotal.ContractId (Bravo)"),
        "do_phu_khoa": ("ContractId co tren 100% dong hoa don ETC T7-T8/2026 va khop 1.037/1.037 ma "
                        "hop dong - kiem chung 13/09/2026."),
        "tong_so_hop_dong": len(hop_dong) + len(bat_thuong),
        "so_hop_dong_con_hieu_luc": len(dang_hieu_luc),
        "tong_gia_tri": sum(x["gia_tri_hop_dong"] for x in xet),
        "tong_da_xuat_hoa_don": sum(x["da_xuat_hoa_don"] for x in xet),
        "tong_con_lai": sum(x["con_lai"] for x in xet),
        "so_hop_dong_sap_het_han": len(sap_het),
        "gia_tri_con_lai_cua_hop_dong_sap_het_han": sum(x["con_lai"] for x in sap_het),
        "so_hop_dong_chua_xuat_hoa_don_nao": len(chua_xuat),
        # 17/09/2026: THEM so dem. Moi danh sach khac trong ham nay deu co truong dem di kem
        # (so_hop_dong_sap_het_han, so_hop_dong_chua_xuat_hoa_don_nao...) rieng danh sach nay thi
        # khong - nen khi bi cat o limit, model doc duoc 50 dong va bao "co 50 hop dong duoi 50%"
        # nhu the do la tong that (UAT 17/09, cau C44). Cung lop loi voi "hoi top 10 tra top 3".
        "so_hop_dong_thuc_hien_duoi_50_pct": len(thuc_hien_thap),
        "hop_dong_thuc_hien_duoi_50_pct": thuc_hien_thap[:limit],
        "hop_dong_sap_het_han": sorted(sap_het, key=lambda x: x["con_lai_ngay"])[:limit],
        "so_hop_dong_gia_tri_bat_thuong": len(bat_thuong),
        "hop_dong_gia_tri_bat_thuong": sorted(bat_thuong, key=lambda x: -x["gia_tri_hop_dong"])[:20],
        "so_hop_dong_co_chung_tu_gan_nham": len(gan_nham),
        "tong_tien_chung_tu_gan_nham_da_loai": sum(x["chung_tu_gan_nham_da_loai"]["so_tien"] for x in gan_nham),
        "hop_dong_co_chung_tu_gan_nham": [
            {k: x[k] for k in ("contract_id", "so_hop_dong", "customer_code", "chung_tu_gan_nham_da_loai")}
            for x in sorted(gan_nham, key=lambda x: -abs(x["chung_tu_gan_nham_da_loai"]["so_tien"]))[:20]],
        "so_hop_dong_co_hoa_don_khac_ma_khach": sum(1 for x in xet if x.get("hoa_don_khac_ma_khach_van_tinh")),
        "canh_bao": ("Hop dong goc va phu luc da duoc cuon theo Id0; hoa don noi qua dung "
                     "ContractId cua tung phien ban, khong ghep gan dung theo khach/SKU/thoi gian. "
                     "Cac hop dong co gia tri bat thuong da duoc TACH RIENG khoi moi con so tong o "
                     "day (do 13/09/2026: 3/9.135 hop dong chiem 99,88% tong gia tri). Khi tra loi "
                     "phai neu ro con so tong khong gom nhung hop dong do va can DNH kiem lai du lieu "
                     "goc. Ty le thuc hien = tong Amount9 hoa don co ContractId / gia tri hop dong, "
                     "ca hai deu TRUOC VAT. Chung tu mang ContractId nhung khac CA ma khach LAN mat "
                     "hang cua hop dong bi coi la gan nham: KHONG tinh vao da xuat, liet ke o "
                     "hop_dong_co_chung_tu_gan_nham - neu co thi noi ro va de DNH kiem lai. Hoa don "
                     "khac ma khach nhung cung mat hang van tinh (thuong la cung don vi co hai ma)."),
        "data_as_of": latest_data_date(),
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
            roster_sql, roster_params = _roster_employee_sql(fdate)
            sql = (f"WITH roster AS ({roster_sql}), metrics AS ("
                   "SELECT e.employee_code,MAX(e.month_sale_target) target,SUM(e.amount_ct) actual,"
                   "MAX(e.save_date) metric_snapshot "
                   f"FROM fact_tonghopkhachhang e JOIN {_MONTH_LATEST_SUBQ} l "
                   "ON l.employee_code=e.employee_code AND l.d=e.save_date GROUP BY e.employee_code) "
                   "SELECT f.employee_code,f.manager_code,m.target,m.actual,m.metric_snapshot,"
                   "nv.employee_code dim_code,"
                   "nv.name employee_name,nv.position_code,nv.is_duplicate,nv.area_code FROM roster f "
                   "LEFT JOIN metrics m ON m.employee_code=f.employee_code "
                   "LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code WHERE 1=1")
            params = [*roster_params, fdate, fdate]
            if scope_area_code:
                sql += " AND nv.area_code=?"; params.append(scope_area_code)
            if scope_employee_code:
                team = _team_of_qlv(scope_employee_code, fdate)
                codes = [r["employee_code"] for r in team]
                sql += f" AND f.employee_code IN ({','.join(['?'] * len(codes))})"
                params.extend(codes)
            employees = _q(sql, tuple(params))

            # C54/S38: FACT_TongHopKhachHang la 1 dong/(NV x khach) nen roster cua no chi co
            # nguoi da phat sinh khach/doanh so. Nguon dung de kiem tra thieu target, trung tang
            # va manager la FACT_ThongKeTinhLuong: 1 dong/NV, gom ca nguoi chua ban va cac ban ghi
            # alias/vi tri trong. Do that T8/2026: TongHopKhachHang chi co 186 ma va bao 2 ca thieu
            # target; ThongKeTinhLuong co 209 dong, trong do tang nhan vien 183 nguoi va 17 ca thieu
            # target (2 ca da co doanh so). Chi dung nguon nay khi so dong khong kem hon roster cu,
            # de fail-safe neu job luong/KPI chua dong bo du tren mot moi truong.
            quality_source = "fact_tonghopkhachhang"
            quality_snapshot = fdate
            try:
                salary_date_r = _q(
                    "SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE save_date<=?",
                    (as_of_date,),
                )
                salary_date = salary_date_r[0]["d"] if salary_date_r and salary_date_r[0]["d"] else None
                if salary_date:
                    salary_sql = (
                        "WITH latest AS (SELECT employee_code,MAX(save_date) d "
                        "FROM fact_thongketinhluong WHERE save_date<=? "
                        "AND substr(save_date,1,7)=substr(?,1,7) GROUP BY employee_code) "
                        "SELECT f.employee_code,f.manager_code,f.month_sale_target target,"
                        "f.month_sale_amount actual,f.save_date metric_snapshot,"
                        "nv.employee_code dim_code,COALESCE(f.employee_name,nv.name) employee_name,"
                        "COALESCE(f.position_code,nv.position_code) position_code,"
                        "nv.is_duplicate,COALESCE(f.area_code,nv.area_code) area_code "
                        "FROM fact_thongketinhluong f JOIN latest l "
                        "ON l.employee_code=f.employee_code AND l.d=f.save_date "
                        "LEFT JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code WHERE 1=1"
                    )
                    salary_params = [salary_date, salary_date]
                    if scope_area_code:
                        salary_sql += " AND COALESCE(f.area_code,nv.area_code)=?"
                        salary_params.append(scope_area_code)
                    if scope_employee_code:
                        salary_sql += (
                            f" AND f.manager_code=? AND UPPER(COALESCE(f.position_code,"
                            f"nv.position_code,'')) IN ({_tier_ph()})"
                        )
                        salary_params.extend([scope_employee_code, *_EMPLOYEE_TIER_POSITIONS])
                    salary_rows = _q(salary_sql, tuple(salary_params))
                    if salary_rows and len(salary_rows) >= len(employees):
                        employees = salary_rows
                        quality_source = "fact_thongketinhluong"
                        quality_snapshot = salary_date
            except sqlite3.OperationalError:
                # Kho cu/test fixture co the chua co bang luong hoac chua du cot. Duong cu van
                # fail-closed va cac canh bao snapshot tiep tuc duoc tra ve.
                pass
            # C54 UAT: cap QLV khong co manager_code trong nguon phang la gioi han cay cap tren,
            # khong duoc tron vao loi "nhan vien tuyen ban hang thieu quan ly". Neu tron, kho that
            # 31/08 bao sai 21 loi trong khi ca 21 dong deu la QLV. Dong thieu DIM van giu trong
            # tap loi vi chua du vai tro de chung minh day la cap quan ly hop le.
            def _is_employee_tier(row):
                position = str(row["position_code"] or "").upper()
                return position in _EMPLOYEE_TIER_POSITIONS or not row["dim_code"]

            employee_tier = [r for r in employees if _is_employee_tier(r)]
            management_tier = [r for r in employees if not _is_employee_tier(r)]

            def _unique_codes(rows, predicate=lambda _row: True):
                return sorted({
                    r["employee_code"] for r in rows
                    if r["employee_code"] and predicate(r)
                }, key=str)

            missing_manager = _unique_codes(
                employees,
                lambda r: not (r["manager_code"] or "").strip() and _is_employee_tier(r),
            )
            management_without_parent = _unique_codes(
                employees,
                lambda r: not (r["manager_code"] or "").strip() and not _is_employee_tier(r),
            )
            target_population = employee_tier if quality_source == "fact_thongketinhluong" else employees
            missing_target = _unique_codes(target_population, lambda r: _f(r["target"]) <= 0)
            missing_snapshot = (_unique_codes(employees, lambda r: r["metric_snapshot"] is None)
                                if quality_source != "fact_thongketinhluong" else [])
            target_with_snapshot = _unique_codes(
                target_population,
                lambda r: r["metric_snapshot"] is not None and _f(r["target"]) > 0,
            )
            missing_target_with_snapshot = _unique_codes(
                target_population,
                lambda r: r["metric_snapshot"] is not None and _f(r["target"]) <= 0,
            )
            missing_target_with_sales = _unique_codes(
                target_population,
                lambda r: _f(r["target"]) <= 0 and _f(r.get("actual")) > 0,
            )
            missing_dim = _unique_codes(employees, lambda r: not r["dim_code"])
            duplicates = _unique_codes(
                employees,
                lambda r: int(r["is_duplicate"] or 0) == 1
                and r["employee_code"] not in _KNOWN_MISFLAGGED_DUPLICATE_CODES,
            )
            snapshot_is_closed = False
            if quality_snapshot:
                sy, sm = int(str(quality_snapshot)[:4]), int(str(quality_snapshot)[5:7])
                snapshot_is_closed = str(quality_snapshot)[:10] == (
                    f"{sy:04d}-{sm:02d}-{_last_day_of_month(sy, sm):02d}"
                )
            result["checks"]["kpi_employee_mapping"] = {
                "snapshot": quality_snapshot, "quality_source": quality_source,
                "snapshot_is_closed": snapshot_is_closed,
                "employees": len(_unique_codes(employees)),
                # Ten ro nghia de model khong doc nham `employees` thanh "so nguoi co target".
                # Giu `employees` ben tren de tuong thich nguoc voi pack UAT/script hien tai.
                "roster_employees": len(_unique_codes(employees)),
                "roster_rows": len(employees),
                "employee_tier_employees": len(_unique_codes(employee_tier)),
                "management_tier_employees": len(_unique_codes(management_tier)),
                "employees_with_current_snapshot": len(_unique_codes(employees)) - len(missing_snapshot),
                "employees_with_target": len(target_with_snapshot),
                "roster_snapshots": ([quality_snapshot] if quality_source == "fact_thongketinhluong"
                                     else _roster_snapshot_dates(fdate)),
                "missing_current_snapshot": len(missing_snapshot),
                "missing_manager": len(missing_manager), "missing_target": len(missing_target),
                "missing_target_with_current_snapshot": len(missing_target_with_snapshot),
                "missing_target_with_sales": len(missing_target_with_sales),
                "missing_employee_dim": len(missing_dim), "duplicate_codes": len(duplicates),
                "management_rows_without_parent_in_source": len(management_without_parent),
                "note": "quality_source cho biet nguon roster da dung. Neu la fact_thongketinhluong, "
                        "employee_tier_employees moi la mau so cua missing_target/missing_manager; "
                        "management_tier_employees duoc tach rieng. roster_employees/employees la tong "
                        "ca hai tang, KHONG phai so nguoi co target. employees_with_target moi la so "
                        "nhan vien tuyen ban hang co target duong. missing_target_with_sales la nhom "
                        "uu tien kiem tra. O duong fallback fact_tonghopkhachhang, missing_target va "
                        "missing_current_snapshot CO CHONG LAN, KHONG duoc cong hai nhom. Chua du du lieu "
                        "khong dong nghia voi 0% KPI hay da xac nhan chua giao chi tieu. "
                        "snapshot_is_closed=false CHI co nghia so lieu chua phai chot cuoi thang; "
                        "KHONG duoc tu ket luan thieu target la binh thuong, do dau thang, hay do DNH "
                        "chua nhap du. duplicate_codes la cac ma bi DIM_NhanVien gan co IsDuplicate=1 "
                        "(da loai 2 ma gan nham da biet), KHONG tu no chung minh mot ma xuat hien nhieu "
                        "dong hoac cho phep xoa/gop hang loat. "
                        "management_rows_without_parent_in_source la QLV/cap quan ly khong co cay "
                        "cap tren trong nguon phang; chi de canh bao gioi han nguon, khong tinh la loi NV.",
            }
            result["samples"].update({
                "missing_manager": missing_manager[:sample_limit],
                "missing_target": missing_target[:sample_limit],
                "missing_target_with_sales": missing_target_with_sales[:sample_limit],
                "missing_current_snapshot": missing_snapshot[:sample_limit],
                "missing_employee_dim": missing_dim[:sample_limit],
                "duplicate_codes": duplicates[:sample_limit],
                "management_rows_without_parent_in_source": management_without_parent[:sample_limit],
            })
            by_code = {r["employee_code"]: r for r in employees}
            missing_target_with_sales_set = set(missing_target_with_sales)
            missing_target_details = [{
                "employee_code": code,
                "employee_name": by_code[code].get("employee_name") or "(chua co ten trong danh muc)",
                "position_code": by_code[code].get("position_code"),
                "area_code": by_code[code].get("area_code"),
                "manager_code": by_code[code].get("manager_code"),
                "has_sales_without_target": code in missing_target_with_sales_set,
            } for code in missing_target[:sample_limit]]
            result["missing_target_details"] = missing_target_details
            result["missing_target_details_total"] = len(missing_target)
            result["missing_target_details_returned"] = len(missing_target_details)
            result["missing_target_details_truncated"] = len(missing_target) > len(missing_target_details)
            detail_groups = {
                "missing_manager": missing_manager,
                "missing_target": missing_target,
                "missing_target_with_sales": missing_target_with_sales,
                "missing_current_snapshot": missing_snapshot,
                "missing_employee_dim": missing_dim,
                "duplicate_codes": duplicates,
                "management_rows_without_parent_in_source": management_without_parent,
            }
            result["sample_details"] = {
                key: [{
                    "employee_code": code,
                    "employee_name": by_code[code].get("employee_name") or "(chua co ten trong danh muc)",
                    "position_code": by_code[code].get("position_code"),
                    "area_code": by_code[code].get("area_code"),
                    "manager_code": by_code[code].get("manager_code"),
                } for code in codes[:sample_limit]]
                for key, codes in detail_groups.items()
            }
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
        # "Ngay tuong lai" phai so voi ngay he thong hien tai, KHONG so voi moc lich su nguoi
        # dung dang hoi. Truoc day hoi snapshot 31/08 vao ngay 09/09 lam moi hoa don 01-09/09 bi
        # gan nham la future (4.943 dong OTC + 361 ETC), du chung chi la giao dich sau ky doi chieu.
        future_cutoff = dt.date.today().isoformat()
        future_where, future_params = " WHERE substr(v.doc_date,1,10)>?", [future_cutoff]
        if scope_area_code:
            future_where += " AND tp.area_code=?"; future_params.append(scope_area_code)
        if scope_employee_code:
            emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=as_of_date)
            future_where += emp_sql; future_params.extend(emp_params)
        future = _q(f"SELECT COUNT(*) n FROM {table} v {join}{future_where}", tuple(future_params))[0]["n"]
        invoice_checks[channel] = {
            **row, "future_dated_lines": int(future or 0),
            "future_date_cutoff": future_cutoff,
            "future_date_definition": "Ngay chung tu lon hon ngay he thong, khong phai lon hon moc snapshot dang hoi.",
        }
    result["checks"]["invoice_mapping"] = invoice_checks
    unavailable = [
        "Action/owner/deadline: chua co nguon action tracker.",
        "Sai chi nhanh/NPP: hoa don/danh muc local chua co khoa branch/distributor chuan.",
    ]
    nguon_don = {"source": "DMS_DonHangHdr + vHoaDonTotal (OTC)", "tool": "check_order_timing"}
    if scope_channel and scope_channel.upper() == "ETC":
        nguon_don["status"] = "NOT_APPLICABLE"
        unavailable.insert(0, "Don hang huy/cham/chua hoa don: nguon don DMS chi co kenh OTC.")
    else:
        nguon_don.update(_trang_thai_nguon_don_hang())
        if nguon_don["status"] == "OK":
            nguon_don["note"] = ("Don huy/cham/chua hoa don KHONG nam trong kho local nhung DOC DUOC truc "
                                 "tiep Bravo: tra bang check_order_timing. Khong duoc bao la chua dong bo.")
        else:
            unavailable.insert(0, "Don hang huy/cham/chua hoa don: khong doc duoc nguon DMS_DonHangHdr "
                                  "tren Bravo luc kiem (%s)." % nguon_don.get("reason"))
    result["checks"]["order_invoice_source"] = nguon_don
    # M28/S75: ty le theo TUNG THANG, mau so la so khach co hoa don thang do.
    theo_thang = _chat_luong_mapping_khach_theo_thang(
        as_of_date[:7], 6, scope_area_code, scope_channel, scope_employee_code)
    result["checks"]["customer_mapping_by_month"] = {
        "rows": theo_thang,
        "definition": ("Moi khach dem MOT LAN trong thang; mau so tong_khach la so khach co hoa don "
                       "thang do. ma_nv_la = ma nguoi ban tren hoa don khong co trong danh muc nhan "
                       "vien (khac voi khong_gan_tdv la hoa don khong ghi ma nao). ma_nv_he_etc la "
                       "ma NAM O bang nhan vien SX/ETC rieng - KHONG phai loi mapping, khong duoc gop "
                       "vao ma_nv_la. Dung dinh nghia "
                       "S75 - khi hoi 'ty le ... theo thang' phai lay o day, khong dung so dem cua "
                       "mot thoi diem ben tren."),
    }
    result["unavailable_checks"] = unavailable
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
              "tra loi 'chua tra cuu duoc cong no', TUYET DOI KHONG ket luan 'khach khong co no'.",
              code="customer_receivables_unavailable", severity="warning",
              message=(f"Chưa tra cứu được công nợ của khách {customer_code} vì nguồn công nợ chưa có dữ liệu. "
                       "Chưa thể xác nhận khách có nợ hay không."))
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


_THU_TU_NHOM_TUOI = (("overdue_1_15", "b1", 1), ("overdue_15_30", "b2", 2),
                     ("overdue_30_45", "b3", 3), ("overdue_gt_45", "b4", 4))


def _nhom_tuoi_xau_nhat(row) -> str:
    """Nhom tuoi no XAU NHAT con du tien cua mot khach tai mot moc. Dung de tra loi "khach nao
    chuyen sang nhom xau hon" bang DOI CHIEU thay vi suy luan."""
    xau = None
    for ten, khoa, _bac in _THU_TU_NHOM_TUOI:
        if _f(row[khoa]) > 0:
            xau = ten
    return xau


def _bac_nhom_tuoi(ten_nhom: str) -> int:
    for ten, _khoa, bac in _THU_TU_NHOM_TUOI:
        if ten == ten_nhom:
            return bac
    return 0


def _loc_pham_vi_cong_no_lich_su(conditions: list, params: list, scope_area_code: str,
                                 scope_channel: str, scope_employee_code: str) -> tuple:
    """Gom dieu kien loc pham vi (vung / kenh / DOI QLV) cho hai tool doc bang lich su cong no.

    17/09/2026 - VA LO PHAM VI DOI: truoc do receivables_period_compare KHONG nhan
    scope_employee_code va KHONG nam trong _PERSON_LEVEL_TEMPLATES, nen chot fail-closed trong
    call_template() khong he kich hoat voi tai khoan QLV - tool chay voi pham vi CA VUNG. Khi tool
    chi tra 2 con so tong thi hau qua con nho; nhung tu ban 17/09 no tra them TOP 10 KHACH kem ten
    va so no, tuc QLV se doc duoc khach cua doi khac. Dung dieu ma chinh chot fail-closed trong
    call_template() goi la khong chap nhan duoc ("Tha tu choi con hon lo ... cua doi khac").

    Dung DUNG ngu nghia cua receivables_overview de hai bao cao khong lech dinh nghia "doi":
    khach thuoc doi lay tu phan cong KPI (FACT_TongHopKhachHang), va khach ETC thi CHUA co phan
    cong theo doi nen tu choi thang thay vi lay cong no ca vung thay the."""
    if scope_area_code:
        region_key = next((k for k, ms in REGION_SQL_MARKERS.items() if scope_area_code in ms), None)
        markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code])
        conditions.append(f"area_code IN ({','.join(['?'] * len(markers))})")
        params.extend(markers)

    team_scope = None
    if scope_employee_code:
        if scope_channel and str(scope_channel).strip().upper() != "OTC":
            raise KhongXacDinhDuocDoi(
                "Chua co phan cong khach ETC theo doi QLV de loc cong no lich su; "
                "khong the dung phan cong OTC hay cong no ca vung thay the.")
        scope_channel = "OTC"
        ngay_phan_cong = dt.date.today()
        ma_khach = sorted(team_customer_codes(_q, scope_employee_code, ngay_phan_cong))
        if not ma_khach:
            raise KhongXacDinhDuocDoi(
                f"Khong xac dinh duoc khach thuoc doi {scope_employee_code} trong phan cong KPI; "
                "CHUA danh gia duoc cong no lich su cua doi, khong ket luan khong co no.")
        conditions.append(f"customer_code IN ({','.join('?' for _ in ma_khach)})")
        params.extend(ma_khach)
        team_scope = {
            "manager_code": scope_employee_code,
            "assignment_as_of": ngay_phan_cong.isoformat(),
            "assigned_customers": len(ma_khach),
            "source": "FACT_TongHopKhachHang.ManagerCode/EmployeeCode",
        }

    if scope_channel:
        channel = str(scope_channel).strip().upper()
        if channel not in {"OTC", "ETC"}:
            raise ValueError(f"scope_channel khong hop le: {scope_channel}")
        conditions.append("UPPER(TRIM(sales_channel))=?")
        params.append(channel)
    return scope_channel, team_scope


def receivables_history_dates(limit: int = 30, scope_area_code: str = None,
                              scope_channel: str = None,
                              scope_employee_code: str = None) -> dict:
    """Liet ke cac NGAY da co snapshot cong no LICH SU (fact_congno_khachhang_history) - dung TRUOC
    khi goi get_receivables_period_compare de biet co ngay nao de so sanh chua, hoac khi nguoi dung
    hoi 'cong no co du lieu tu bao gio', 'co the so sanh cong no voi ngay nao'.

    21/08/2026: bang lich su MOI duoc them (xem sync_fact_congno trong sync_warehouse.py) - CHI co
    du lieu TU NGAY BAT DAU GHI TRO DI, KHONG co lich su cong no truoc do (khac han doanh thu co du
    lieu nhieu nam). PHAI noi ro dieu nay neu danh sach ngay con it/moi bat dau.

    17/09/2026 - TRA LUON SO LIEU TUNG MOC, khong chi liet ke ngay. Ly do tu UAT that (cau C37):
    ban cu chi tra danh sach ngay, muon ve duoc duong xu huong thi model phai goi
    get_receivables_period_compare cho TUNG CAP ngay - voi ~27 moc la bat kha thi trong han muc
    MAX_TOOL_ROUNDS, nen model chi lay 4 moc roi trinh bay nhu the do la toan bo du lieu co. Mot
    lan goi duy nhat o day tra ca chuoi (moi moc 4 con so, payload rat nho) la du dung duong xu
    huong that."""
    limit = max(1, min(int(limit or 30), 100))
    conditions, params = [], []
    scope_channel, team_scope = _loc_pham_vi_cong_no_lich_su(
        conditions, params, scope_area_code, scope_channel, scope_employee_code)
    where = "".join(f" AND {condition}" for condition in conditions)

    rows = _q(
        "SELECT snapshot_date, COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od, "
        "COUNT(*) so_dong FROM fact_congno_khachhang_history "
        f"WHERE 1=1{where} GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT ?",
        (*params, limit))
    chuoi = []
    for r in rows:
        bal, od = _f(r["bal"]), _f(r["od"])
        chuoi.append({"snapshot_date": r["snapshot_date"], "balance_end": bal,
                      "total_overdue": od,
                      "overdue_pct": (od / bal * 100) if bal else 0.0,
                      "so_dong": int(r["so_dong"])})
    # cac_ngay GIU nguyen hop dong cu: moi nhat truoc (nhieu noi dang dua vao thu tu nay).
    # Rieng chuoi_theo_moc dao lai tang dan de doc duong xu huong cho tu nhien.
    ngay_moi_truoc = [r["snapshot_date"] for r in chuoi]
    chuoi.reverse()
    for idx in range(1, len(chuoi)):
        truoc = chuoi[idx - 1]
        chuoi[idx]["delta_total_overdue"] = chuoi[idx]["total_overdue"] - truoc["total_overdue"]
        chuoi[idx]["delta_overdue_pct_diem"] = chuoi[idx]["overdue_pct"] - truoc["overdue_pct"]

    ket_qua = {
        "so_ngay_co_du_lieu": len(chuoi),
        "cac_ngay": ngay_moi_truoc,
        "chuoi_theo_moc": chuoi,
        "ghi_chu": ("He thong bat dau luu lich su cong no tu 21/08/2026 - CHUA co du lieu cong "
                    "no cua cac ky truoc ngay do, khac voi doanh thu (co du lieu nhieu nam)."),
        "answer_rule": (
            "chuoi_theo_moc da co DU cac moc dang luu kem tong du no/qua han/ty le tung moc - dung "
            "TRUC TIEP de dung duong xu huong, KHONG can goi get_receivables_period_compare cho "
            "tung cap ngay va KHONG duoc chi lay vai moc roi trinh bay nhu the do la toan bo du "
            "lieu. Can tach theo kenh/vung/tuoi no hay tung khach tai hai moc cu the thi moi goi "
            "get_receivables_period_compare."),
    }
    if team_scope:
        ket_qua["pham_vi_doi"] = team_scope
    if scope_area_code or scope_channel:
        ket_qua["pham_vi"] = {"scope_area_code": scope_area_code, "scope_channel": scope_channel}
    return ket_qua


def receivables_period_compare(snapshot_date_a: str, snapshot_date_b: str,
                                scope_area_code: str = None,
                                scope_channel: str = None,
                                scope_employee_code: str = None) -> dict:
    """SO SANH cong no giua 2 NGAY snapshot lich su (fact_congno_khachhang_history) - dung khi cau
    hoi dang "cong no hom nay so voi tuan truoc/thang truoc the nao", "no qua han tang hay giam so
    voi ngay X". KHAC voi get_receivables_overview (chi tra ve snapshot HIEN TAI DUY NHAT, khong so
    sanh duoc) - dung get_receivables_history_dates TRUOC de biet cac ngay co san neu chua chac.

    snapshot_date_a/date_b: 'YYYY-MM-DD', PHAI la ngay CO trong fact_congno_khachhang_history (dung
    get_receivables_history_dates de tra cuu) - neu 1 trong 2 ngay khong co du lieu, tra ve loi ro
    rang thay vi so sanh voi 0.

    21/08/2026: bang lich su moi duoc them nen CHI so sanh duoc trong pham vi tu ngay bat dau ghi -
    KHONG the so sanh voi cac ky xa hon (vd "cung ky nam ngoai") nhu doanh thu da lam duoc.

    17/09/2026: tra ve DAY DU cac chieu co san trong bang lich su tai CA HAI moc - 4 nhom tuoi no
    (aging), theo kenh (by_channel), theo vung (by_region), top 10 khach no qua han va do tap trung
    top10/top20 - kem chenh lech tuong ung. Ban truoc chi tra 2 con so tong moi moc, khien chatbot
    hieu nham la du lieu KHONG CO cac chieu do va di bao voi nguoi dung nhu vay (xem ghi chu chi
    tiet trong _snapshot)."""
    conditions, params = [], []
    scope_channel, team_scope = _loc_pham_vi_cong_no_lich_su(
        conditions, params, scope_area_code, scope_channel, scope_employee_code)
    where = "".join(f" AND {condition}" for condition in conditions)

    def _snapshot(d):
        # 17/09/2026 - SUA THIEU SOT NANG: ban cu CHI tra SUM(balance_end)+SUM(total_overdue), vut
        # bo 4 nhom tuoi no, chieu kenh, chieu vung va chi tiet tung khach - DU CA BON deu nam san
        # trong chinh bang dang query (xem schema fact_congno_khachhang_history). Hau qua thuc te
        # (nhat ky UAT 17/09, cau C37 va C40): chatbot tuong day la GIOI HAN DU LIEU va tuyen bo
        # voi nguoi dung rang "cac moc snapshot lich su cu chi co tong du no & tong qua han, khong
        # tach duoc kenh/mien/co cau tuoi no", C40 con khuyen DNH "bo sung luu snapshot chi tiet
        # theo khach hang" - trong khi he thong DA luu day du tu 21/08/2026. Bao cao thieu nang luc
        # minh dang co la sai nghiem trong hon bao loi ky thuat.
        r = _q(f"SELECT COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od, "
               f"COALESCE(SUM(overdue_1_15),0) b1, COALESCE(SUM(overdue_15_30),0) b2, "
               f"COALESCE(SUM(overdue_30_45),0) b3, COALESCE(SUM(overdue_gt_45),0) b4, COUNT(*) n, "
               f"SUM(CASE WHEN total_overdue > 0 THEN 1 ELSE 0 END) n_qh "
               f"FROM fact_congno_khachhang_history WHERE snapshot_date=?{where}", (d, *params))[0]
        bal, od = _f(r["bal"]), _f(r["od"])
        snap = {"snapshot_date": d, "balance_end": bal, "total_overdue": od,
                "overdue_pct": (od / bal * 100) if bal else 0.0,
                "so_dong": int(r["n"]), "so_khach_qua_han": int(r["n_qh"] or 0),
                "aging": {"overdue_1_15": _f(r["b1"]), "overdue_15_30": _f(r["b2"]),
                          "overdue_30_45": _f(r["b3"]), "overdue_gt_45": _f(r["b4"])}}
        if not snap["so_dong"]:
            return snap

        by_channel = _q(f"SELECT sales_channel, COALESCE(SUM(balance_end),0) bal, "
                        f"COALESCE(SUM(total_overdue),0) od FROM fact_congno_khachhang_history "
                        f"WHERE snapshot_date=?{where} GROUP BY sales_channel", (d, *params))
        snap["by_channel"] = [
            {"channel": c["sales_channel"], "balance_end": _f(c["bal"]),
             "total_overdue": _f(c["od"]),
             "overdue_pct": (_f(c["od"]) / _f(c["bal"]) * 100) if _f(c["bal"]) else 0.0}
            for c in by_channel]

        if not scope_area_code:     # da scope roi thi chi con 1 vung, tach lai khong con y nghia
            by_area = _q(f"SELECT area_code, COALESCE(SUM(balance_end),0) bal, "
                         f"COALESCE(SUM(total_overdue),0) od FROM fact_congno_khachhang_history "
                         f"WHERE snapshot_date=?{where} GROUP BY area_code", (d, *params))
            agg = {}
            for c in by_area:
                label = _AREA_TO_REGION_VI.get(c["area_code"], "Khac/chua xac dinh")
                b, o = agg.get(label, (0.0, 0.0))
                agg[label] = (b + _f(c["bal"]), o + _f(c["od"]))
            snap["by_region"] = [
                {"region": lbl, "balance_end": b, "total_overdue": o,
                 "overdue_pct": (o / b * 100) if b else 0.0}
                for lbl, (b, o) in sorted(agg.items(), key=lambda x: -x[1][1])]

        # 17/09/2026 (UAT that, cau V35 "khach nao moi chuyen sang nhom tuoi no xau hon" va C39):
        # ban truoc chi tra ma/ten/du no/qua han cho tung khach, KHONG tra 4 nhom tuoi no - trong khi
        # bang lich su co du. Chatbot vi the bao "he thong chua luu lich su bucket rieng le theo
        # khach" (SAI ve du lieu, dung ve cong cu) roi TU SUY LUAN khach nao gia di bang meo "so tien
        # qua han khong doi", va neu ten 4 khach kem nhom tuoi nhu mot ket luan. Suy luan thay cho
        # doi chieu la dung dieu khong duoc phep. Tra thang 4 nhom tuoi tung khach de khong phai doan.
        top = _q(f"SELECT customer_code, MAX(customer_name) name, COALESCE(SUM(balance_end),0) bal, "
                 f"COALESCE(SUM(total_overdue),0) od, COALESCE(SUM(overdue_1_15),0) b1, "
                 f"COALESCE(SUM(overdue_15_30),0) b2, COALESCE(SUM(overdue_30_45),0) b3, "
                 f"COALESCE(SUM(overdue_gt_45),0) b4 FROM fact_congno_khachhang_history "
                 f"WHERE snapshot_date=?{where} GROUP BY customer_code "
                 f"HAVING SUM(total_overdue) > 0 ORDER BY SUM(total_overdue) DESC LIMIT 20",
                 (d, *params))
        snap["top_overdue_customers"] = [
            {"customer_code": c["customer_code"], "customer_name": c["name"],
             "balance_end": _f(c["bal"]), "total_overdue": _f(c["od"]),
             # Chi giu nhom CO tien va lam tron: 10 khach x 2 moc x 4 nhom day du day payload
             # len 9.550/10.000 ky tu, sat tran den muc luoi an toan se cat mat chinh phan nay.
             # Nhom vang mat = 0 dong (da noi ro trong aging_bucket_note o cap tren).
             "aging": {ten: int(_f(c[khoa])) for ten, khoa, _b in _THU_TU_NHOM_TUOI
                       if _f(c[khoa]) > 0},
             "nhom_tuoi_xau_nhat": _nhom_tuoi_xau_nhat(c)} for c in top[:10]]
        if od:
            # Do TAP TRUNG tai tung moc - de tra loi duoc "rui ro tap trung TANG hay GIAM" thay vi
            # bao "khong co lich su chi tiet theo khach" (C40 17/09/2026).
            snap["tap_trung_no_qua_han"] = {
                "top10_share_pct": sum(_f(c["od"]) for c in top[:10]) / od * 100,
                "top20_share_pct": sum(_f(c["od"]) for c in top) / od * 100,
            }
        return snap

    a, b = _snapshot(snapshot_date_a), _snapshot(snapshot_date_b)
    missing = [d for d, s in ((snapshot_date_a, a), (snapshot_date_b, b)) if s["so_dong"] == 0]
    if missing:
        return {"error": (f"Khong co du lieu cong no lich su cho ngay {', '.join(missing)}. "
                           "Dung get_receivables_history_dates de xem cac ngay dang co san.")}

    delta_balance = a["balance_end"] - b["balance_end"]
    delta_overdue = a["total_overdue"] - b["total_overdue"]
    ket_qua = {
        "ky_a": a, "ky_b": b,
        "delta_balance_end": delta_balance,
        "delta_total_overdue": delta_overdue,
        "pct_change_balance_end": (delta_balance / b["balance_end"] * 100) if b["balance_end"] else None,
        "pct_change_total_overdue": (delta_overdue / b["total_overdue"] * 100) if b["total_overdue"] else None,
        "delta_overdue_pct_diem": a["overdue_pct"] - b["overdue_pct"],
        "delta_aging": {k: a["aging"][k] - b["aging"][k] for k in a["aging"]},
        "aging_bucket_note": _AGING_BUCKET_NOTE,
        "scope_area_code": scope_area_code,
        "scope_channel": str(scope_channel).strip().upper() if scope_channel else None,
    }
    # 17/09/2026: tinh san danh sach khach GIA DI giua hai moc - dung cau hoi cua V35/C39. Tinh o
    # day (doi chieu nhom tuoi xau nhat cua tung khach tai hai moc) de model KHONG phai suy luan tu
    # "so tien qua han khong doi" nhu no da lam.
    truoc_theo_ma = {c["customer_code"]: c for c in (b.get("top_overdue_customers") or [])}
    gia_di = []
    for c in a.get("top_overdue_customers") or []:
        cu_ = truoc_theo_ma.get(c["customer_code"])
        if not cu_:
            continue
        bac_moi, bac_cu = _bac_nhom_tuoi(c["nhom_tuoi_xau_nhat"]), _bac_nhom_tuoi(cu_["nhom_tuoi_xau_nhat"])
        if bac_moi > bac_cu:
            gia_di.append({
                "customer_code": c["customer_code"], "customer_name": c["customer_name"],
                "nhom_tuoi_truoc": cu_["nhom_tuoi_xau_nhat"], "nhom_tuoi_sau": c["nhom_tuoi_xau_nhat"],
                "total_overdue_truoc": cu_["total_overdue"], "total_overdue_sau": c["total_overdue"],
            })
    ket_qua["khach_chuyen_nhom_tuoi_xau_hon"] = gia_di
    # Danh sach khach o moc CU chi con dung lam boi canh: phan so sanh gia di va do tap trung deu da
    # tinh san o tren tu top 20 day du. Giu 10 dong o CA HAI moc day payload len 9.430/10.000 ky tu -
    # sat tran den muc luoi an toan se cat mat chinh phan vua them. Rut moc cu con 5 dong.
    if len(b.get("top_overdue_customers") or []) > 5:
        b["top_overdue_customers"] = b["top_overdue_customers"][:5]
        b["ghi_chu_top"] = ("Chi giu 5 khach lam boi canh; so sanh gia di va do tap trung da tinh "
                            "san tu danh sach day du.")
    ket_qua["pham_vi_so_sanh_khach"] = (
        "khach_chuyen_nhom_tuoi_xau_hon va cac chi so theo khach chi xet trong TOP 20 khach no qua "
        "han cua MOI moc (da loc dung pham vi tai khoan) - KHONG phai toan bo khach. Noi ro dieu nay "
        "khi tra loi, va KHONG suy luan khach nao gia di tu viec 'so tien khong doi'.")

    tt_a, tt_b = a.get("tap_trung_no_qua_han"), b.get("tap_trung_no_qua_han")
    if tt_a and tt_b:
        ket_qua["delta_tap_trung_diem"] = {
            "top10_share_pct": tt_a["top10_share_pct"] - tt_b["top10_share_pct"],
            "top20_share_pct": tt_a["top20_share_pct"] - tt_b["top20_share_pct"],
        }
    ket_qua["answer_rule"] = (
        "Du lieu lich su nay CO DU chieu kenh, vung, 4 nhom tuoi no va tung khach hang tai MOI moc "
        "- KHONG duoc noi rang lich su chi co tong du no/tong qua han, va KHONG duoc de nghi DNH "
        "'bo sung luu snapshot chi tiet' vi he thong DA luu tu 21/08/2026. Gioi han THAT chi la SO "
        "MOC ngay dang co (xem get_receivables_history_dates), khong phai do chi tiet."
    )
    return ket_qua


def _customer_code_exists(value: str) -> bool:
    """Ma co that trong danh muc, hoa don hoac snapshot cong no."""
    rows = _q(
        "SELECT 1 found FROM dms_khachhang WHERE UPPER(code)=UPPER(?) "
        "UNION ALL SELECT 1 FROM dmssx_khachhang WHERE UPPER(code)=UPPER(?) "
        "UNION ALL SELECT 1 FROM vhoadon_otc WHERE UPPER(customer_code)=UPPER(?) "
        "UNION ALL SELECT 1 FROM vhoadon_etc WHERE UPPER(customer_code)=UPPER(?) "
        "UNION ALL SELECT 1 FROM fact_congno_khachhang WHERE UPPER(customer_code)=UPPER(?) LIMIT 1",
        (value, value, value, value, value),
    )
    return bool(rows)


def _customer_name_candidates(query: str, scope_area_code: str = None,
                              scope_channel: str = None, limit: int = 20) -> list[dict]:
    """Tim ma khach theo ten trong danh muc va snapshot cong no, co loc pham vi truoc khi tra ve."""
    raw_words = [word.strip(".,;:()[]{}\"'") for word in str(query or "").split()]
    raw_words = [word for word in raw_words if len(word) >= 2]
    search_word = raw_words[-1] if raw_words else str(query or "").strip()
    like = f"%{search_word}%"
    channel_scope = str(scope_channel or "").strip().upper()
    region_key = next((key for key, markers in REGION_SQL_MARKERS.items()
                       if scope_area_code in markers), None)
    area_markers = REGION_SQL_MARKERS.get(region_key, [scope_area_code]) if scope_area_code else []

    rows = []
    for table, channel in (("dms_khachhang", "OTC"), ("dmssx_khachhang", "ETC")):
        if channel_scope and channel_scope != channel:
            continue
        area_sql = ""
        params = [like]
        if area_markers:
            area_sql = f" AND tp.area_code IN ({','.join('?' for _ in area_markers)})"
            params.extend(area_markers)
        rows.extend(_q(
            f"SELECT kh.code,kh.name,'{channel}' channel,tp.area_code "
            f"FROM {table} kh LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
            f"WHERE kh.name LIKE ?{area_sql} LIMIT 500",
            tuple(params),
        ))

    debt_conditions = ["customer_name LIKE ?"]
    debt_params = [like]
    if channel_scope:
        debt_conditions.append("UPPER(sales_channel)=?")
        debt_params.append(channel_scope)
    if area_markers:
        debt_conditions.append(f"area_code IN ({','.join('?' for _ in area_markers)})")
        debt_params.extend(area_markers)
    rows.extend(_q(
        "SELECT customer_code code,MAX(customer_name) name,MAX(sales_channel) channel,"
        "MAX(area_code) area_code FROM fact_congno_khachhang WHERE "
        + " AND ".join(debt_conditions)
        + " GROUP BY customer_code,sales_channel LIMIT 500",
        tuple(debt_params),
    ))

    folded_query = _fold_question(query)
    query_tokens = [token for token in folded_query.split() if len(token) >= 2]
    merged = {}
    for row in rows:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code or not name:
            continue
        folded_name = _fold_question(name)
        matched = sum(token in folded_name for token in query_tokens)
        if folded_name == folded_query:
            score = 1000
        elif folded_query and folded_query in folded_name:
            score = 900
        elif query_tokens and matched == len(query_tokens):
            score = 800 + matched
        else:
            continue
        item = merged.setdefault(code.upper(), {
            "customer_code": code,
            "customer_name": name,
            "channels": set(),
            "area_code": row.get("area_code"),
            "_score": score,
        })
        item["channels"].add(str(row.get("channel") or "").upper())
        if score > item["_score"]:
            item["_score"] = score
            item["customer_name"] = name
            item["area_code"] = row.get("area_code") or item.get("area_code")

    result = sorted(merged.values(), key=lambda item: (
        -item["_score"], item["customer_name"].lower(), item["customer_code"]
    ))
    return [{
        "customer_code": item["customer_code"],
        "customer_name": item["customer_name"],
        "channel": "+".join(sorted(ch for ch in item["channels"] if ch)) or None,
        "area_code": item["area_code"],
    } for item in result[:max(1, min(int(limit or 20), 50))]]


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
    customer_code = str(customer_code or "").strip()
    original_customer_query = customer_code
    resolved_lookup_channel = None
    if customer_code and "," in customer_code:
        codes = [c.strip() for c in customer_code.split(",") if c.strip()]
        results = []
        for code in codes[:30]:
            r_single = customer_detail(customer_code=code, date_from=date_from, date_to=date_to, scope_area_code=scope_area_code, scope_channel=scope_channel)
            r_single = dict(r_single) if r_single else {"error": f"Khong tra ve duoc du lieu cho khach hang '{code}'."}
            r_single["requested_customer_code"] = code
            results.append(r_single)
        return {"is_bulk": True, "count": len(results), "customers": results}

    # Nguoi dung thuong nho TEN, khong nho ma. Truoc day schema bat ma nen bot tu choi du kho co
    # danh muc. Neu input khong phai ma da biet, tim ten trong dung pham vi; chi tu chon khi duy nhat.
    looks_like_code = bool(re.fullmatch(r"[A-Za-z0-9_-]+", customer_code)
                           and any(ch.isdigit() or ch == "_" for ch in customer_code))
    if not _customer_code_exists(customer_code) and not looks_like_code:
        candidates = _customer_name_candidates(
            customer_code, scope_area_code=scope_area_code, scope_channel=scope_channel,
        )
        if len(candidates) != 1:
            status = "ambiguous" if candidates else "not_found"
            return {
                "customer_lookup_status": status,
                "customer_query": customer_code,
                "candidate_count": len(candidates),
                "customer_candidates": candidates,
                "answer_rule": (
                    "Neu ambiguous: liet ke cac ung vien kem ma/ten/kenh va hoi nguoi dung chon; "
                    "khong doan mot khach. Neu not_found: noi khong tim thay trong danh muc thuoc "
                    "pham vi tai khoan; khong noi he thong chi tra duoc theo ma."
                ),
            }
        customer_code = candidates[0]["customer_code"]
        if candidates[0].get("channel") in {"OTC", "ETC"}:
            resolved_lookup_channel = candidates[0]["channel"]
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
    effective_channel = str(scope_channel or "").strip().upper() or resolved_lookup_channel
    otc_rev, otc_hd = (0.0, 0) if effective_channel == "ETC" else (_f(o["rev"]), real_otc_hd)
    etc_rev, etc_hd = (0.0, 0) if effective_channel == "OTC" else (_f(e["rev"]), real_etc_hd)

    if otc_hd and etc_hd:
        channel = "OTC+ETC"
    elif otc_hd:
        channel = "OTC"
    elif etc_hd:
        channel = "ETC"
    else:
        channel = effective_channel if effective_channel in {"OTC", "ETC"} else None

    revenue = otc_rev + etc_rev
    orders = otc_hd + etc_hd
    avg_order_value = (revenue / orders) if orders else 0.0

    dms_otc = _q(
        "SELECT name, city_id, id_code, emp_code, kenh_bh FROM dms_khachhang "
        "WHERE code=? LIMIT 1", (customer_code,))
    dms_etc_raw = _q(
        "SELECT name, city_id, id_code, kenh_bh FROM dmssx_khachhang WHERE code=? LIMIT 1",
        (customer_code,))
    dms_etc = [{**dms_etc_raw[0], "emp_code": None}] if dms_etc_raw else []
    debt_channels = {
        str(row["sales_channel"] or "").strip().upper()
        for row in _q(
            "SELECT DISTINCT sales_channel FROM fact_congno_khachhang WHERE customer_code=?",
            (customer_code,))
        if row.get("sales_channel")
    }
    preferred_channel = effective_channel or channel
    if preferred_channel not in {"OTC", "ETC"} and len(debt_channels) == 1:
        preferred_channel = next(iter(debt_channels))

    # Cung mot ma co the co ten khac nhau o hai danh muc. Chon danh muc theo kenh cua hoa don/cong
    # no dang tra de ten hien thi khop voi so lieu, khong uu tien OTC vo dieu kien (BGI00699: DMS
    # ghi "Bac Giang", danh muc SX/cong no ETC ghi "Bac Ninh").
    # 16/09/2026 - anh Dang xac nhan day KHONG phai gan nham: tinh Bac Giang da sap nhap vao Bac
    # Ninh, hai ten la cung MOT benh vien. Vi vay chi neu ten con lai de doi chieu, tuyet doi khong
    # dien giai thanh hai khach khac nhau.
    if preferred_channel == "ETC":
        dms, lookup_src = (dms_etc or dms_otc), ("ETC" if dms_etc else "OTC")
    else:
        dms, lookup_src = (dms_otc or dms_etc), ("OTC" if dms_otc else "ETC")
    catalog_identity_warning = None
    if dms_otc and dms_etc and _fold_question(dms_otc[0].get("name")) != _fold_question(
            dms_etc[0].get("name")):
        catalog_identity_warning = {
            "OTC": dms_otc[0].get("name"),
            "ETC": dms_etc[0].get("name"),
            "selected_channel": lookup_src,
            "answer_rule": (
                "Cung MOT ma khach nhung hai danh muc ghi ten khac nhau - thuong do doi ten hoac "
                "sap nhap don vi hanh chinh (Bac Giang nay thuoc Bac Ninh), KHONG PHAI hai khach "
                "khac nhau. Dung ten cua selected_channel cho so lieu dang tra, va neu ten con lai "
                "de nguoi dung doi chieu."
            ),
        }

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
        "identity_check": (
            f"Ma {customer_code} co ten trong kho la '{name}'. Neu ten nguoi dung goi khac ten nay "
            "thi PHAI noi ro ten dang luu trong kho truoc khi trinh bay so lieu. KHONG duoc ket luan "
            "day la khach khac chi vi khac dia danh: sau sap nhap don vi hanh chinh 2025 (vd Bac "
            "Giang nay thuoc Bac Ninh) danh muc con giu ten tinh cu, van la MOT khach."
        ),
    }
    if catalog_identity_warning:
        result["catalog_identity_warning"] = catalog_identity_warning
    if original_customer_query != customer_code:
        result["customer_lookup"] = {
            "query": original_customer_query,
            "resolved_customer_code": customer_code,
            "resolved_channel": resolved_lookup_channel,
        }
    if scope_channel:
        result["channel_scope"] = f"Tai khoan chi duoc xem kenh {scope_channel} - so lieu kenh khac (neu co) KHONG duoc hien thi."
    return result


def _order_fulfillment_exceptions(date_from: str, date_to: str, threshold_days: int,
                                  scope_area_code: str = None, scope_channel: str = None,
                                  scope_employee_code: str = None) -> dict:
    """Doi chieu don DMS OTC voi hoa don Bravo, dung dung tap nguon cua S42.

    Phan hang tra trong kho local va phan don DMS chua/tre hoa don la HAI phep kiem tra
    khac nhau. Khong duoc lay ``CreatedAt`` thay cho ngay xac nhan, vi DNH da xac nhan
    CreatedAt chi la thoi diem tao don (04/09/2026).
    """
    if scope_channel == "ETC":
        return {
            "status": "NOT_APPLICABLE",
            "source": "DMS_DonHangHdr + vHoaDonTotal (OTC)",
            "reason": "Nguon DMS_DonHangHdr dung de doi chieu don-hoa don nay thuoc kenh OTC; tai khoan chi duoc xem ETC.",
            "rows": [],
        }

    try:
        # call_template them 23:59:59 cho truy van SQLite bao gom tron ngay cuoi. DMS chi can
        # phan ngay, nen khong duoc dua chuoi co gio vao date.fromisoformat().
        report_to = dt.date.fromisoformat(str(date_to)[:10])
    except ValueError:
        return {
            "status": "INVALID_PERIOD", "rows": [],
            "reason": "date_to phai co dang YYYY-MM-DD de doi chieu don DMS voi hoa don.",
        }

    params = {
        "date_from": str(date_from),
        "date_to_exclusive": report_to + dt.timedelta(days=1),
        "lag_threshold": max(0, int(threshold_days or 0)),
    }
    scope_joins = ""
    scope_where = ""
    if scope_area_code:
        scope_joins += (" LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=h.CustomerCode "
                        " LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId ")
        scope_where += " AND tp.AreaCode=:scope_area_code"
        params["scope_area_code"] = scope_area_code
    if scope_employee_code:
        try:
            dms_ids = _get_team_dms_ids(scope_employee_code, str(date_to))
        except Exception as exc:
            return {
                "status": "SCOPE_UNAVAILABLE", "rows": [],
                "reason": f"Khong xac dinh duoc DMSId cua doi de doi chieu don: {exc}",
            }
        placeholders = []
        for idx, dms_id in enumerate(dms_ids):
            key = f"employee_dms_{idx}"
            params[key] = dms_id
            placeholders.append(f":{key}")
        if not placeholders:
            return {
                "status": "SCOPE_UNAVAILABLE", "rows": [],
                "reason": "Khong co DMSId duoc phan quyen de doi chieu don.",
            }
        joined = ",".join(placeholders)
        scope_where += f" AND (h.DMSEmpId1 IN ({joined}) OR h.DMSEmpId2 IN ({joined}))"

    try:
        rows = _q_bravo(f"""
            SELECT TOP (200)
                   h.Id AS OrderId, h.DocDate AS OrderDate, h.CustomerCode,
                   h.DMSEmpId1, h.StatusId, h.StatusDescription, h.IsSync,
                   MIN(v.DocDate) AS InvoiceDate,
                   DATEDIFF(day, h.DocDate, MIN(v.DocDate)) AS LagDays
            FROM dbo.DMS_DonHangHdr h
            {scope_joins}
            LEFT JOIN dbo.vHoaDonTotal v ON TRY_CONVERT(int, v.DMSId)=h.Id
            WHERE h.DocDate>=:date_from AND h.DocDate<:date_to_exclusive {scope_where}
            GROUP BY h.Id,h.DocDate,h.CustomerCode,h.DMSEmpId1,
                     h.StatusId,h.StatusDescription,h.IsSync
            HAVING MIN(v.DocDate) IS NULL
                OR ABS(DATEDIFF(day, h.DocDate, MIN(v.DocDate)))>=:lag_threshold
            ORDER BY h.DocDate, h.Id
        """, params)
    except Exception as exc:
        # Bao cao hang tra/phan bo gia tri don trong kho local van dung duoc neu VPN/Bravo dang loi.
        return {
            "status": "SOURCE_UNAVAILABLE", "source": "DMS_DonHangHdr + vHoaDonTotal (OTC)",
            "rows": [], "reason": f"Khong doc duoc nguon don DMS de doi chieu: {exc}",
        }

    def _iso(value):
        return value.isoformat() if isinstance(value, (dt.date, dt.datetime)) else (str(value) if value else None)

    details = []
    for row in rows:
        invoice_date = row.get("InvoiceDate")
        details.append({
            "order_id": row.get("OrderId"),
            "order_date": _iso(row.get("OrderDate")),
            "customer_code": row.get("CustomerCode"),
            "employee_dms_id": row.get("DMSEmpId1"),
            "status_id": row.get("StatusId"),
            "status_description": row.get("StatusDescription"),
            "is_sync": row.get("IsSync"),
            "invoice_date": _iso(invoice_date),
            "invoice_lag_days": int(row["LagDays"]) if row.get("LagDays") is not None else None,
            "exception_reason": ("CHUA_TIM_THAY_HOA_DON" if invoice_date is None
                                 else "CHENH_LECH_NGAY_DON_HOA_DON"),
        })
    lag_threshold = params["lag_threshold"]
    cancelled = [row for row in details if (
        "hủy" in str(row.get("status_description") or "").lower()
        or "huy" in str(row.get("status_description") or "").lower()
    )]
    missing_invoice = [row for row in details if row.get("invoice_date") is None]
    invoice_after = [row for row in details if (
        row.get("invoice_lag_days") is not None
        and row["invoice_lag_days"] >= lag_threshold
    )]
    invoice_before = [row for row in details if (
        row.get("invoice_lag_days") is not None
        and row["invoice_lag_days"] <= -lag_threshold
    )]
    return {
        "status": "OK", "source": "DMS_DonHangHdr + vHoaDonTotal (OTC)",
        "date_from": str(date_from), "date_to": str(date_to),
        "lag_threshold_days": lag_threshold, "total_returned": len(details),
        # Dat summary TRUOC rows de model van nhan du con so toan tap neu danh sach chi tiet dai
        # bi lop gioi han payload rut gon. V33 tung dem 9/10/15 tuy theo doan JSON bi cat, du nguon
        # Bravo co 22 dong; moi ket luan so luong phai doc summary nay, khong dem bang hien thi.
        "summary": {
            "total_exceptions": len(details),
            "cancelled_orders": len(cancelled),
            "missing_invoice_orders": len(missing_invoice),
            "cancelled_and_missing_invoice_orders": sum(
                1 for row in missing_invoice if row in cancelled
            ),
            "missing_invoice_not_cancelled_orders": sum(
                1 for row in missing_invoice if row not in cancelled
            ),
            "invoice_after_order_at_least_threshold": len(invoice_after),
            "invoice_before_order_at_least_threshold": len(invoice_before),
        },
        "counting_guidance": (
            f"Dung cac con so trong summary cho TOAN TAP. Nguong la TU {lag_threshold} ngay "
            f"(>= {lag_threshold}), nen don lech dung {lag_threshold} ngay VAN duoc tinh. "
            "Khong goi lech ngay don-hoa don la giao cham vi nguon khong co ngay giao hang thuc te."
        ),
        "rows": details,
        "definition": ("Chua hoa don = khong tim thay hoa don noi bang DMSId. Chenh lech hoa don = "
                       f"tri tuyet doi cua so ngay tu ngay don den hoa don dau tien >= {lag_threshold}. "
                       "Day KHONG phai phep do giao cham. CreatedAt khong duoc dung vi chi la thoi diem tao don."),
        "limit_note": "Toi da 200 dong theo truy van chuan S42; neu can can xu ly them, hay chia nho ky.",
    }


def _sales_financial_quality_by_month(date_from: str, date_to: str,
                                      scope_area_code: str = None,
                                      scope_channel: str = None,
                                      scope_employee_code: str = None) -> dict:
    """S77/S78/S87 tu hoa don local; fail closed neu kho cu chua co DiscountRate/DocCode."""
    missing = {}
    not_populated = {}
    table_channels = (("vhoadon_otc", "OTC"), ("vhoadon_etc", "ETC"))
    for table, channel in table_channels:
        if scope_channel and scope_channel.upper() != channel:
            continue
        columns = {row["name"] for row in _q(f"PRAGMA table_info({table})")}
        absent = sorted({"discount_rate", "doc_code"} - columns)
        if absent:
            missing[table] = absent
            continue
        coverage = _q(
            f"SELECT COUNT(*) total_rows,"
            "SUM(CASE WHEN discount_rate IS NOT NULL OR doc_code IS NOT NULL THEN 1 ELSE 0 END) "
            f"populated_rows FROM {table} WHERE doc_date BETWEEN ? AND ?",
            (date_from, date_to),
        )[0]
        if int(coverage.get("total_rows") or 0) > 0 \
                and int(coverage.get("populated_rows") or 0) == 0:
            not_populated[table] = int(coverage.get("total_rows") or 0)
    if missing or not_populated:
        return {
            "status": "SOURCE_GAP_INVOICE_QUALITY_COLUMNS_NOT_SYNCED",
            "missing_columns": missing,
            "tables_with_unpopulated_new_columns": not_populated,
            "rows_by_month_channel": [], "rows_by_month_area": [],
            "required_action": "Chay dong bo warehouse moi de nap DiscountRate va DocCode tu hai view hoa don Total.",
        }
    parts, params = [], []
    for table, channel, customer_table in (
        ("vhoadon_otc", "OTC", "dms_khachhang"),
        ("vhoadon_etc", "ETC", "dmssx_khachhang"),
    ):
        if scope_channel and scope_channel.upper() != channel:
            continue
        employee_sql, employee_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
        parts.append(
            f"SELECT '{channel}' channel,substr(v.doc_date,1,7) month,"
            "COALESCE(tp.area_code,'UNKNOWN') area_code,v.amount9,v.quantity,v.unit_price,"
            "COALESCE(v.discount_rate,0) discount_rate,COALESCE(v.doc_code,'') doc_code,"
            f"'{channel}:'||v.doc_date||':'||COALESCE(v.customer_code,'')||':'||COALESCE(v.stt,'') order_key "
            f"FROM {table} v LEFT JOIN {customer_table} kh ON kh.code=v.customer_code "
            "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id "
            f"WHERE v.doc_date BETWEEN ? AND ?{employee_sql}"
        )
        params.extend((date_from, date_to) + employee_params)
    if not parts:
        return {"status": "not_applicable", "rows_by_month_channel": [], "rows_by_month_area": []}
    raw = _q(" UNION ALL ".join(parts), tuple(params))
    if scope_area_code:
        raw = [row for row in raw if row.get("area_code") == scope_area_code]

    def aggregate(keys):
        buckets = {}
        for row in raw:
            key = tuple(row[name] for name in keys)
            bucket = buckets.setdefault(key, {
                **{name: row[name] for name in keys},
                "gross_revenue": 0.0, "discount_amount": 0.0,
                "return_adjustment": 0.0, "invoice_revenue_after_returns": 0.0,
                "gift_quantity": 0.0, "gift_orders": set(), "total_orders": set(),
            })
            amount = _f(row.get("amount9"))
            order_key = row.get("order_key")
            if order_key:
                bucket["total_orders"].add(order_key)
            if amount > 0:
                bucket["gross_revenue"] += amount
                bucket["discount_amount"] += amount * _f(row.get("discount_rate"))
            if amount < 0 or str(row.get("doc_code") or "").upper() == "HC":
                bucket["return_adjustment"] += abs(amount)
            if _f(row.get("unit_price")) == 0 and _f(row.get("quantity")) > 0:
                bucket["gift_quantity"] += _f(row.get("quantity"))
                if order_key:
                    bucket["gift_orders"].add(order_key)
            bucket["invoice_revenue_after_returns"] += amount
        result = []
        for bucket in buckets.values():
            gross = bucket["gross_revenue"]
            gift_order_count = len(bucket["gift_orders"])
            total_order_count = len(bucket["total_orders"])
            bucket["gift_orders"] = gift_order_count
            bucket["total_orders"] = total_order_count
            bucket["gift_order_share_pct"] = (
                gift_order_count / total_order_count * 100 if total_order_count else None
            )
            bucket["net_revenue_after_discount_and_returns"] = (
                bucket["invoice_revenue_after_returns"] - bucket["discount_amount"]
            )
            bucket["discount_rate_pct"] = (bucket["discount_amount"] / gross * 100
                                            if gross else None)
            bucket["return_adjustment_rate_pct"] = (bucket["return_adjustment"] / gross * 100
                                                     if gross else None)
            bucket["return_threshold_pct"] = 2.0
            bucket["return_threshold_flag"] = (
                "VUOT_NGUONG_DE_XUAT" if bucket["return_adjustment_rate_pct"] is not None
                and bucket["return_adjustment_rate_pct"] > 2 else "TRONG_NGUONG_DE_XUAT"
            )
            result.append(bucket)
        return sorted(result, key=lambda row: tuple(str(row[name]) for name in keys))

    return {
        "status": "ok",
        "rows_by_month_channel": aggregate(("month", "channel")),
        "rows_by_month_area": aggregate(("month", "area_code")),
        "discount_definition": "Chiet khau = Amount9 duong x DiscountRate; Amount9 la doanh thu gop truoc chiet khau.",
        "return_definition": "Hang tra/dieu chinh = Amount9 am hoac DocCode='HC'; ty le chia cho doanh thu gop duong.",
        "return_threshold_note": "Nguong 2% chi la de xuat cua MCNA, can DNH chot.",
        "gift_metric_status": "AVAILABLE_FROM_ZERO_PRICE_INVOICE_LINES",
        "gift_metric_note": (
            "Hang tang = UnitPrice=0 va Quantity>0; gift_order_share_pct chia so don co hang tang "
            "cho tong so don trong cung thang/kenh hoac thang/vung."
        ),
        "promotion_metric_status": "REQUIRES_FRESH_PROMOTION_LINK_CHECK",
        "promotion_metric_note": (
            "Chi phi/khuyen mai phai doc chuoi DMS_DonHangCTKM va moc coverage moi nhat trong lan hoi; "
            "khong suy tu DiscountRate va khong lap lai mot moc dong bo cu."
        ),
    }


def order_timing_check(date_from: str = None, date_to: str = None, threshold_days: int = 2, limit: int = None,
                        scope_area_code: str = None, scope_channel: str = None,
                        scope_employee_code: str = None, group_by_month: bool = False) -> dict:
    """Kiem tra hang tra/dieu chinh va phan bo gia tri don trong ky.

    ``created_at`` la THOI DIEM TAO DON, khong phai thoi diem xac nhan don. DNH xac nhan ngay
    04/09/2026 rang do lech giua ``created_at`` va ``doc_date`` khong mang y nghia nghiep vu, nen
    ham nay khong truy van, xep hang hay neu ten nhan vien theo do lech do. Ket qua tach ro hai phan:
    ``top_detail`` la hang tra/dieu chinh va phan bo gia tri tu hoa don local; con
    ``order_fulfillment_exceptions`` doi chieu dung DMS_DonHangHdr voi vHoaDonTotal cho cac don
    chua/tre hoa don. ``limit`` gioi han so dong chi tiet hang tra/gia tri don; tong so dong co trong
    ``total_flagged`` khong bi cat. ``scope_channel`` va ``scope_employee_code`` ep pham vi o ca hai phan.
    Neu khong truyen ky, mac dinh tu ngay dau thang chua moc du lieu moi nhat den chinh moc do; V33
    vi vay chay ngay thay vi hoi nguoi dung them mot luot.

    group_by_month: 13/09/2026 (C12) - khi True, tra THEM core_result_by_month (danh sach tung
    thang trong [date_from, date_to], moi thang co core_revenue_excluding_flagged/flagged_revenue
    theo kenh) trong CUNG 1 lan goi. Dung cho cau hoi 'tang truong COT LOI TUNG THANG neu loai giao
    dich bat thuong' - TUYET DOI KHONG tu goi lai tool nhieu lan cho tung thang rieng le (da tung
    gay 1 cau hoi phai goi toi 6-10 vong va het thoi gian request)."""
    period_defaulted = not date_from and not date_to
    latest_day = latest_data_date()[:10]
    raw_to = str(date_to or latest_day)
    date_to_day = raw_to[:10]
    raw_from = str(date_from or f"{date_to_day[:7]}-01")
    date_from_day = raw_from[:10]
    try:
        parsed_from = dt.date.fromisoformat(date_from_day)
        parsed_to = dt.date.fromisoformat(date_to_day)
    except ValueError as exc:
        raise ValueError("date_from/date_to phai co dang YYYY-MM-DD.") from exc
    if parsed_from > parsed_to:
        raise ValueError("date_from khong duoc sau date_to.")

    # Giu hau to gio do call_template them vao date_to de SQLite gom het ngay cuoi; cac phep
    # nghiep vu va SQL Server dung phan YYYY-MM-DD da chuan hoa.
    date_from = date_from_day
    date_to_query = raw_to if len(raw_to) > 10 else date_to_day
    date_to = date_to_day
    scope_sql, scope_params = _scope_clause(scope_area_code)
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=date_to)
    scope_sql += emp_sql
    scope_params += emp_params
    result = {
        "date_from": date_from, "date_to": date_to, "threshold_days": threshold_days,
        "period_defaulted": period_defaulted,
        "created_at_doc_date_check": {
            "status": "NOT_APPLICABLE",
            "definition": "CreatedAt la thoi diem tao don, khong phai thoi diem xac nhan don.",
            "reason": ("DNH xac nhan ngay 04/09/2026: do lech CreatedAt-DocDate khong mang y "
                       "nghia nghiep vu va khong duoc dung de suy dien bat thuong hay KPI."),
        },
        "total_flagged": 0,
        "summary_by_employee": [],
        "top_detail": [],
        "data_as_of": latest_data_date(),
    }
    if group_by_month:
        # 13/09/2026 (C12): doi chieu don-hoa don khong lien quan cau hoi "tang truong cot loi theo
        # thang" va la phan chiem nhieu dung luong nhat trong response, tung lam core_result_by_month
        # (thu nguoi dung thuc su can) bi cat mat khoi ket qua tra ve model. Bo qua khi group_by_month.
        result["order_fulfillment_exceptions"] = {
            "skipped_reason": "group_by_month=true: bo qua doi chieu don-hoa don de nhuong dung "
                               "luong cho core_result_by_month. Goi lai voi group_by_month=false "
                               "neu can xem chi tiet don huy/tre hoa don."
        }
    else:
        result["order_fulfillment_exceptions"] = _order_fulfillment_exceptions(
            date_from, date_to, threshold_days, scope_area_code, scope_channel, scope_employee_code)
    # Cung mot lan goi tra du phan hang tra va phan bo gia tri don. vhoadon_otc GIU cac dong Amount9 am.
    quality_parts, quality_params = [], []
    if scope_channel != "ETC":
        join_o = _otc_area_join("v", scope_area_code)
        quality_parts.append(
            f"SELECT 'OTC' channel,v.doc_date,v.customer_code,v.stt,v.amount9 FROM vhoadon_otc v {join_o} "
            f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        quality_params.extend((date_from, date_to_query) + scope_params)
    if scope_channel != "OTC":
        join_e = _etc_area_join("v", scope_area_code)
        quality_parts.append(
            f"SELECT 'ETC' channel,v.doc_date,v.customer_code,v.stt,v.amount9 FROM vhoadon_etc v {join_e} "
            f"WHERE v.doc_date BETWEEN ? AND ?{scope_sql}")
        quality_params.extend((date_from, date_to_query) + scope_params)
    order_rows = _q(
        "WITH lines AS (" + " UNION ALL ".join(quality_parts) + ") "
        "SELECT channel||':'||COALESCE(NULLIF(stt,''),doc_date||':'||COALESCE(customer_code,'')) order_key,"
        "MIN(doc_date) doc_date,MAX(customer_code) customer_code,"
        "SUM(amount9) revenue,"
        "SUM(CASE WHEN amount9<0 THEN amount9 ELSE 0 END) return_amount,"
        "MAX(CASE WHEN amount9<0 THEN 1 ELSE 0 END) has_return "
        "FROM lines GROUP BY channel,COALESCE(NULLIF(stt,''),doc_date||':'||COALESCE(customer_code,''))",
        tuple(quality_params)) if quality_parts else []
    order_values = sorted((_f(r["revenue"]) for r in order_rows), reverse=True)
    total_order_revenue = sum(order_values)
    # Trung vi phai tinh RIENG tung kenh. OTC va ETC co mat bang gia tri don rat khac nhau;
    # gop chung se danh dau sai don ETC hoac bo sot don OTC, trai voi quy tac S09 da cong bo.
    values_by_channel = {}
    for row in order_rows:
        channel = str(row["order_key"]).split(":", 1)[0]
        values_by_channel.setdefault(channel, []).append(_f(row["revenue"]))
    median_by_channel = {
        channel: float(median(values)) if values else 0.0
        for channel, values in values_by_channel.items()
    }
    flagged = []
    for row in order_rows:
        channel = str(row["order_key"]).split(":", 1)[0]
        median_order = median_by_channel.get(channel, 0.0)
        proposed_threshold = median_order * 3
        has_return = bool(row["has_return"])
        is_large_reference = _f(row["revenue"]) > proposed_threshold
        if not has_return and not is_large_reference:
            continue
        reasons = []
        if has_return:
            reasons.append("HANG_TRA_DIEU_CHINH")
        if is_large_reference:
            reasons.append("TREN_3X_TRUNG_VI_THAM_CHIEU")
        flagged.append({
            "order_key": row["order_key"],
            "channel": channel,
            "doc_date": row["doc_date"],
            "customer_code": row["customer_code"],
            "order_revenue": _f(row["revenue"]),
            "return_adjustment": _f(row["return_amount"]),
            "reasons": reasons,
            "median_order_value": median_order,
            "multiple_of_median": (_f(row["revenue"]) / median_order if median_order else None),
            "large_order_threshold_status": "CHI_LA_THAM_CHIEU_CHUA_DUOC_DNH_PHE_DUYET",
        })
    flagged.sort(key=lambda row: abs(row["order_revenue"]), reverse=True)
    result["total_flagged"] = len(flagged)
    # group_by_month=true: neu model KHONG tu truyen limit rieng, gioi han top_detail con 3 (thay vi
    # mac dinh 20) de nhuong dung luong cho core_result_by_month - nguoi hoi xu huong theo thang
    # khong can toan bo chi tiet tung don. Model van co the tu truyen limit khac de ghi de.
    if limit is None:
        default_limit = 3 if group_by_month else 20
    else:
        default_limit = int(limit)
    result["top_detail"] = flagged[:max(1, min(default_limit, 100))]
    result["top_detail_truncated"] = len(flagged) > len(result["top_detail"])
    # Tra ve du ca hai ve cua cau hoi V05/M09/C12: don nao bi danh dau va sau khi loai thi
    # con bao nhieu. Day la phep tinh tren CUNG tap don, khong ghep tong doanh thu tu tool khac.
    flagged_keys = {row["order_key"] for row in flagged}
    core_by_channel = []
    for channel in sorted(values_by_channel):
        channel_rows = [r for r in order_rows if str(r["order_key"]).split(":", 1)[0] == channel]
        abnormal_rows = [r for r in channel_rows if r["order_key"] in flagged_keys]
        gross_revenue = sum(_f(r["revenue"]) for r in channel_rows)
        abnormal_revenue = sum(_f(r["revenue"]) for r in abnormal_rows)
        core_by_channel.append({
            "channel": channel,
            "total_orders": len(channel_rows),
            "flagged_orders": len(abnormal_rows),
            "revenue_including_flagged": gross_revenue,
            "core_revenue_excluding_flagged": gross_revenue - abnormal_revenue,
            "flagged_revenue": abnormal_revenue,
            "flagged_revenue_share_pct": (
                abnormal_revenue / gross_revenue * 100 if gross_revenue else None),
            "median_order_value": median_by_channel[channel],
            "large_order_threshold": median_by_channel[channel] * 3,
        })
    result["core_result_by_channel"] = core_by_channel
    if group_by_month:
        # Gom lai theo (thang, kenh) tu CUNG tap order_rows/flagged_keys da tinh o tren - khong
        # query lai Bravo/SQLite, chi nhom lai trong Python.
        month_channel = {}
        for row in order_rows:
            channel = str(row["order_key"]).split(":", 1)[0]
            ym = str(row["doc_date"])[:7]
            bucket = month_channel.setdefault((ym, channel), {"gross": 0.0, "flagged": 0.0, "n_total": 0, "n_flagged": 0})
            rev = _f(row["revenue"])
            bucket["gross"] += rev
            bucket["n_total"] += 1
            if row["order_key"] in flagged_keys:
                bucket["flagged"] += rev
                bucket["n_flagged"] += 1
        core_by_month = []
        for (ym, channel), b in sorted(month_channel.items()):
            core_by_month.append({
                "month": ym, "channel": channel,
                "total_orders": b["n_total"], "flagged_orders": b["n_flagged"],
                "revenue_including_flagged": b["gross"],
                "core_revenue_excluding_flagged": b["gross"] - b["flagged"],
                "flagged_revenue": b["flagged"],
                "flagged_revenue_share_pct": (b["flagged"] / b["gross"] * 100 if b["gross"] else None),
            })
        result["core_result_by_month"] = core_by_month
        result["core_result_by_month_note"] = (
            "Tach theo tung thang trong [date_from, date_to] da yeu cau, cung dinh nghia 'bat "
            "thuong' voi core_result_by_channel (hang tra/dieu chinh + tren 3x trung vi THAM CHIEU "
            "cua ca giai doan, khong tinh lai trung vi rieng tung thang)."
        )
        financial_quality = _sales_financial_quality_by_month(
            date_from, date_to_query, scope_area_code, scope_channel, scope_employee_code)
        result["financial_quality_by_month"] = financial_quality
        result["return_adjustment_by_month"] = financial_quality.get("rows_by_month_channel", [])
        result["financial_quality_by_month_area"] = financial_quality.get("rows_by_month_area", [])
    reference_large_rows = [
        row for row in order_rows
        if _f(row["revenue"]) > median_by_channel.get(str(row["order_key"]).split(":", 1)[0], 0.0) * 3
    ]
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
        "median_order_value_all_channels": (float(median(order_values)) if order_values else 0.0), **concentration,
        "reference_over_3x_median": {
            "status": "CHI_LA_THAM_CHIEU_CHUA_DUOC_DNH_PHE_DUYET",
            "definition": "Nguong tinh rieng theo tung kenh; xem core_result_by_channel.",
            "orders": len(reference_large_rows),
            "revenue": sum(_f(r["revenue"]) for r in reference_large_rows),
        },
        "warning": ("DNH chua phe duyet nguong nao duoc goi la 'don lon bat thuong'. Chi trinh bay "
                    "phan bo/top share va tham chieu >3x trung vi; KHONG ket luan gian lan/chay don "
                    "chi tu gia tri don."),
    }
    # Du lieu cu hon 12 thang da bi NEN thanh KH x thang (khong con stt/Amount9 tung dong), nen phan
    # hang tra va phan bo gia tri don chi dai dien cho phan nam trong cua so chi tiet.
    cutoff = _detail_cutoff()
    if date_from < cutoff:
        result["warning"] = (f"Cau hoi vuot qua cua so 12 thang gan nhat (truoc {cutoff}) - chi tiet "
                              f"tung don cho giai doan cu hon KHONG con duoc luu (da nen thanh tong theo "
                              f"khach hang/thang). Hang tra va phan bo gia tri don CHI kiem tra duoc tu "
                              f"{max(date_from, cutoff)} tro di, KHONG dai dien cho toan bo khoang thoi "
                              f"gian da hoi.")
        result["date_from_actually_used"] = max(date_from, cutoff)
    return result


_AREA_TO_BRANCH = {"MB": "B02", "MT": "B03", "MN": "B04"}
# 04/09/2026: B01 truoc day ghi la "San xuat" - TRUNG TEN voi he kho BRVSX (he_thong='SAN_XUAT').
# Sau khi dong bo them he kho san xuat that, mot cau tra loi hien ra: muc "He kho Kinh doanh" co dong
# "San xuat/Tru so (B01)" nam ngay tren muc "He kho San xuat" - hai thu khac han nhau cung mot ten,
# nguoi doc rat de hieu B01 la mot phan cua he san xuat. B01 la kho tai TRU SO thuoc he KINH DOANH.
_BRANCH_LABEL = {"B01": "Trụ sở (hệ kinh doanh)", "B02": "Kinh doanh Miền Bắc",
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
    # 17/09/2026: SO LUONG da duoc cong bien dong nhap-xuat den hom nay (xem sync_tonkho_hien_tai
    # trong sync_warehouse.py), nhung GIA TRI thi KHONG: view nguon vTheKhoLot chi co cot so luong
    # nhap/xuat, khong co cot tien, nen cac dong bien dong de amount rong va SUM(amount) bo qua
    # chung. Hau qua neu khong noi ro: nguoi doc ghep "so luong thang 9" voi "gia tri thang 1" thanh
    # mot cau tra loi nghe rat tron (vd kho SX giam 18% so luong nhung gia tri van nguyen 175 ty).
    # Phai gan canh bao vao DUNG dong du lieu, khong de o cho khac.
    gia_tri_chi_dau_ky = bool(_q(
        "SELECT 1 FROM brv_tonkhodk WHERE amount IS NULL AND quantity <> 0 LIMIT 1"))
    for r in rows:
        r["area_label"] = _BRANCH_LABEL.get(r["area_code"], r["area_code"])
        r["tong_so_luong"] = _f(r["tong_so_luong"])
        r["tong_gia_tri"] = _f(r["tong_gia_tri"])
        r["nam_tai_chinh"] = nam_moi_nhat
        r["he_thong"] = "KINH_DOANH"
        if gia_tri_chi_dau_ky:
            r["gia_tri_moc_thoi_gian"] = "DAU_NAM"
            r["canh_bao_gia_tri"] = (
                "tong_so_luong la ton HIEN TAI (da cong nhap-xuat den moc du lieu), nhung "
                "tong_gia_tri CHI la gia tri DAU NAM TAI CHINH - nguon bien dong khong co cot tien. "
                "KHONG duoc trinh bay tong_gia_tri nhu gia tri ton kho hien tai, va KHONG duoc chia "
                "tong_gia_tri cho tong_so_luong de suy ra don gia.")
        if nam_moi_nhat is None:
            r["canh_bao"] = ("Kho chua dong bo cot fiscal_year - so lieu nay co the dang CONG DON "
                             "nhieu nam tai chinh (dem trung). Can chay lai sync_warehouse.py "
                             "truoc khi dung con so nay.")

    # 04/09/2026: THEM HE KHO SAN XUAT. Truoc do ham nay chi doc brv_tonkhodk (kho kinh doanh
    # B01-B04, nam 2026 chi 5,38 ty) va chatbot trinh bay con so do NHU LA ton kho toan cong ty -
    # trong khi kho san xuat co 229,80 ty, tuc dang bao 2% su that. Hai he TACH HAN (kiem chung tren
    # Bravo: khong trung mot Id kho nao, cap (kho, mat hang) nam 2026 trung 0) nen cong duoc, nhung
    # van tra ve RIENG DONG voi co he_thong - de nguoi doc thay ro dau la kho ban hang, dau la kho
    # san xuat, thay vi gop mu thanh mot con so.
    # Kho san xuat KHONG thuoc vung MB/MT/MN nao (BranchCode rong hoac 'A01') nen an voi tai khoan
    # bi gioi han vung - cung quy tac dang ap cho B01, xem docstring o tren.
    if not area_code and not scope_area_code:
        nam_sx = _nam_moi_nhat("brvsx_tonkhodk", "year")
        try:
            sql_sx = ("SELECT COALESCE(NULLIF(TRIM(k.branch_code),''),'SX') area_code,"
                      "COUNT(DISTINCT t.item_id) so_mat_hang, SUM(t.quantity) tong_so_luong,"
                      "SUM(t.amount) tong_gia_tri FROM brvsx_tonkhodk t "
                      "LEFT JOIN brvsx_kho k ON k.id_code = t.warehouse_id WHERE t.is_active = 1")
            ps = []
            if nam_sx is not None:
                sql_sx += " AND t.year = ?"; ps.append(nam_sx)
            sql_sx += " GROUP BY COALESCE(NULLIF(TRIM(k.branch_code),''),'SX') ORDER BY 1"
            gia_tri_sx_dau_ky = bool(_q(
                "SELECT 1 FROM brvsx_tonkhodk WHERE amount IS NULL AND quantity <> 0 LIMIT 1"))
            for r in _q(sql_sx, tuple(ps)):
                r["area_label"] = "San xuat" if r["area_code"] == "SX" else "San xuat - %s" % r["area_code"]
                r["tong_so_luong"] = _f(r["tong_so_luong"])
                r["tong_gia_tri"] = _f(r["tong_gia_tri"])
                r["nam_tai_chinh"] = nam_sx
                r["he_thong"] = "SAN_XUAT"
                if gia_tri_sx_dau_ky:
                    r["gia_tri_moc_thoi_gian"] = "DAU_NAM"
                    r["canh_bao_gia_tri"] = (
                        "tong_so_luong la ton HIEN TAI, nhung tong_gia_tri CHI la gia tri DAU NAM "
                        "TAI CHINH - nguon bien dong khong co cot tien. KHONG trinh bay tong_gia_tri "
                        "nhu gia tri ton kho hien tai, KHONG chia ra don gia.")
                rows.append(r)
        except Exception:
            # Kho cu chua co bang BRVSX - tra ve phan kinh doanh kem canh bao thay vi sap bao cao.
            for r in rows:
                r.setdefault("canh_bao", "Kho chua dong bo he kho SAN XUAT (brvsx_tonkhodk) - con so "
                                         "nay CHI la kho kinh doanh, khong phai ton kho toan cong ty.")
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


def inventory_item_stock(item_search: str, area_code: str = None, scope_area_code: str = None,
                         limit: int = 30) -> dict:
    """SO LUONG TON KHO THEO SAN PHAM, tim theo ten/ma (khong phan biet hoa thuong va dau tieng Viet).

    15/09/2026 (UAT OTC-only C-Level 14:40 "So luong ton kho bo phe tinh den hom nay"):
      1. Moi tool ton kho bi chan voi tai khoan gioi han kenh nen chatbot tra loi khong co SQL. Anh Dang
         chot 15/09: tai khoan gioi han kenh xem duoc ton kho (van giu gioi han vung).
      2. Khong co tool tim ton theo TEN san pham: inventory_by_region chi co tong theo vung,
         inventory_expiry_report theo lo/han dung. SQLite LIKE khong gap chu co dau ("Bổ Phế" khac
         "bổ phế"), nen so khop tai Python sau khi bo dau.
    Chi tra SO LUONG theo don vi tinh tung ma - khong cong giua cac ma (Lo/Vien/Chiec khac nhau) va
    khong tra gia tri ton (cot gia tri thieu/am dien rong, xem checker S27)."""
    search = _fold_question(item_search)
    if not search:
        return {"error": "Can ten hoac ma san pham de tra cuu ton kho."}
    if scope_area_code:
        area_code = scope_area_code
    branch_filter = _AREA_TO_BRANCH.get(area_code) if area_code else None
    if area_code and not branch_filter:
        return {"error": f"Vung {area_code} khong hop le (MB/MT/MN)."}
    tokens = search.split()
    raw_search = str(item_search).strip()
    matched = {}
    for p in _q("SELECT code, name, unit, id_code FROM brv_sanpham WHERE id_code IS NOT NULL"):
        if all(token in _fold_question(p["name"]) for token in tokens) or (
                raw_search and str(p["code"] or "").startswith(raw_search)):
            matched[p["id_code"]] = p
    if not matched:
        return {"status": "NO_MATCH", "item_search": item_search, "matched_items": 0,
                "note": "Khong tim thay san pham khop ten/ma trong danh muc; KHONG ket luan ton kho bang 0."}
    ids = list(matched)
    ph = ",".join("?" for _ in ids)
    nam_kd = _nam_moi_nhat("brv_tonkhodk", "fiscal_year")
    sql = ("SELECT t.item_id, k.branch_code, SUM(t.quantity) qty FROM brv_tonkhodk t "
           "LEFT JOIN brv_kho k ON k.id_code=t.warehouse_id "
           f"WHERE t.is_active=1 AND t.item_id IN ({ph})")
    params = list(ids)
    if nam_kd is not None:
        sql += " AND t.fiscal_year=?"
        params.append(nam_kd)
    if branch_filter:
        sql += " AND k.branch_code=?"
        params.append(branch_filter)
    by_item = {}
    for r in _q(sql + " GROUP BY t.item_id, k.branch_code", tuple(params)):
        by_item.setdefault(r["item_id"], {"kinh_doanh": [], "san_xuat": None})["kinh_doanh"].append({
            "branch_code": r["branch_code"], "kho": _BRANCH_LABEL.get(r["branch_code"], r["branch_code"]),
            "so_luong": _f(r["qty"])})
    nam_sx = None
    if not area_code:
        # Kho san xuat khong thuoc vung MB/MT/MN nao - an voi tai khoan bi gioi han vung (nhu inventory_by_region).
        nam_sx = _nam_moi_nhat("brvsx_tonkhodk", "year")
        sql_sx = f"SELECT t.item_id, SUM(t.quantity) qty FROM brvsx_tonkhodk t WHERE t.is_active=1 AND t.item_id IN ({ph})"
        params_sx = list(ids)
        if nam_sx is not None:
            sql_sx += " AND t.year=?"
            params_sx.append(nam_sx)
        try:
            for r in _q(sql_sx + " GROUP BY t.item_id", tuple(params_sx)):
                by_item.setdefault(r["item_id"], {"kinh_doanh": [], "san_xuat": None})["san_xuat"] = _f(r["qty"])
        except sqlite3.OperationalError:
            pass
    rows = []
    for item_id, p in matched.items():
        stock = by_item.get(item_id, {"kinh_doanh": [], "san_xuat": None})
        rows.append({
            "item_code": p["code"], "item_name": p["name"], "don_vi_tinh": p["unit"],
            "ton_kho_kinh_doanh": sum(b["so_luong"] for b in stock["kinh_doanh"]),
            "ton_kinh_doanh_theo_kho": sorted(stock["kinh_doanh"], key=lambda b: str(b["branch_code"] or "")),
            "ton_kho_san_xuat": None if area_code else stock["san_xuat"],
            "co_ban_ghi_ton": bool(stock["kinh_doanh"]) or stock["san_xuat"] is not None,
        })
    rows.sort(key=lambda r: -(r["ton_kho_kinh_doanh"] + (r["ton_kho_san_xuat"] or 0)))
    limit = max(1, min(int(limit or 30), 200))
    return {
        "item_search": item_search, "matched_items": len(rows), "rows": rows[:limit],
        "rows_truncated": len(rows) > limit, "scope_area_code": area_code,
        "nam_tai_chinh_kinh_doanh": nam_kd, "nam_san_xuat": nam_sx,
        "definition": (
            "So luong ton theo bang ton kho Bravo, nam moi nhat: he KINH DOANH (kho B01-B04) va he SAN XUAT - "
            "hai he tach han, khong trung. Moi ma dung don vi tinh rieng, KHONG cong giua cac ma. Khong co "
            "ban ghi ton (co_ban_ghi_ton=false) nghia la khong co dong ton, khong khang dinh ton bang 0. "
            "Tai khoan gioi han vung khong thay kho san xuat. Khong tra gia tri ton (cot gia tri thieu/am)."),
        "data_as_of": latest_data_date(),
    }


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


def _inventory_supply_risk(stock_by_item: dict, item_names: dict, area_code: str,
                           limit: int = 30, focus: str = "all",
                           scope_employee_code: str = None) -> dict:
    """So sanh TON HIEN CO voi nhu cau OTC 3 thang da chot gan nhat.

    Day la canh bao suy dien de tra loi S47/S28, khong phai bang chung khach da dat
    hang ma bi thieu hay doanh thu da mat: DNH chua co DMS_DonHangHdr/backlog va du
    lieu phan bo ton theo don.  Tach ham nay khoi phan han dung de mot cau hoi ve
    "SKU thieu hang/cham ban" khong bi tra lai bang danh sach date lo hang khong lien quan.
    """
    if not stock_by_item:
        return {"status": "NO_STOCK", "rows": [], "recent_customer_candidates": []}

    today = dt.date.today()
    last_complete = today.replace(day=1) - dt.timedelta(days=1)
    month_end = last_complete.isoformat()
    month_exclusive_end = today.replace(day=1).isoformat()
    month_start = f"{_month_add(last_complete.strftime('%Y-%m'), -2)}-01"
    # Cung phan cong ManagerCode -> DMSId voi cac tool doanh thu. Chot doi o cuoi ky
    # va dung lai cho CA nhu cau SKU LAN khach mua, khong roi ve toan vung khi thieu doi.
    emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=month_end)
    item_codes = sorted(stock_by_item)
    placeholders = ",".join("?" for _ in item_codes)
    conditions = ["v.doc_date>=? AND v.doc_date<?", f"v.item_code IN ({placeholders})"]
    params = [month_start, month_exclusive_end, *item_codes]
    joins = "LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code"
    if area_code:
        joins += " LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id"
        conditions.append("tp.area_code=?")
        params.append(area_code)

    try:
        demand_rows = _q(
            "SELECT v.item_code, "
            "SUM(CASE WHEN COALESCE(v.unit_price,0)>0 THEN COALESCE(v.quantity,0) ELSE 0 END) qty_3m, "
            "SUM(COALESCE(v.amount9,0)) revenue_3m "
            f"FROM vhoadon_otc v {joins} WHERE {' AND '.join(conditions)}{emp_sql} "
            "GROUP BY v.item_code",
            (*params, *emp_params),
        )
    except (sqlite3.Error, OSError):
        # Kho cu/test database chua co hoa don chi tiet: bao ro nguon khong san sang,
        # tuyet doi khong suy ra "khong co nhu cau" tu truy van loi.
        return {
            "status": "SOURCE_UNAVAILABLE",
            "period": {"from": month_start, "to": month_end},
            "rows": [],
            "recent_customer_candidates": [],
            "warning": "Chua doc duoc hoa don OTC chi tiet de tinh nhu cau 3 thang; khong ket luan SKU cham ban hay thieu hang.",
        }

    demand_by_item = {r["item_code"]: r for r in demand_rows}
    risk_rows = []
    for code, stock_qty in stock_by_item.items():
        demand = demand_by_item.get(code, {})
        avg_qty = _f(demand.get("qty_3m")) / 3.0
        avg_revenue = _f(demand.get("revenue_3m")) / 3.0
        cover = stock_qty / avg_qty if avg_qty > 0 else None
        if avg_qty > 0 and stock_qty < avg_qty:
            status = "CO_NGUY_CO_THIEU_HANG_DERIVED"
        elif avg_qty <= 0:
            status = "TON_KHONG_BAN_3_THANG"
        elif cover > 6:
            status = "CHAM_LUAN_CHUYEN_DERIVED"
        else:
            status = "BINH_THUONG"
        risk_rows.append({
            "item_code": code,
            "item_name": item_names.get(code) or f"(chua co ten - ma {code})",
            "stock_qty": stock_qty,
            "average_monthly_qty_3m": avg_qty,
            "average_monthly_revenue_3m": avg_revenue,
            "months_of_cover": round(cover, 2) if cover is not None else None,
            "status": status,
        })

    actionable = [r for r in risk_rows if r["status"] != "BINH_THUONG"]
    focus = focus if focus in {"all", "shortage", "overstock"} else "all"

    def _priority(row):
        status = row["status"]
        if focus == "overstock":
            # Uu tien nhom ma nguoi dung hoi. Khi chua co he so quy doi don vi,
            # khong xep hang SKU trong nhom bang so thang ton hay so luong ton.
            rank = {
                "TON_KHONG_BAN_3_THANG": 0,
                "CHAM_LUAN_CHUYEN_DERIVED": 1,
                "CO_NGUY_CO_THIEU_HANG_DERIVED": 2,
            }.get(status, 3)
            return rank, row["item_code"]
        # V38/all: nhom thieu hang duoc uu tien, trong nhom chi sap theo ma.
        rank = 0 if status == "CO_NGUY_CO_THIEU_HANG_DERIVED" else 1
        return rank, row["item_code"]

    actionable.sort(key=_priority)

    # "Khach phu hop" chi duoc dua ra nhu danh sach goi y lien he: khach da mua SKU
    # trong 3 thang. Khong co du lieu nhu cau/chao hang de khang dinh se mua.
    # Chi dua khach cho 10 SKU uu tien dau de payload khong phinh thanh hang tram dong,
    # nhung van tra tong so SKU va thong ke trang thai o ben duoi.
    # 18/09/2026 (cau C42): truoc day cat thang theo thu tu uu tien cua focus, nen mot NHOM
    # TRANG THAI co the bi day het ra ngoai limit du status_counts van bao no ton tai. Do that
    # focus='overstock', limit=30: 55 SKU cho xu ly (16 thieu hang / 28 cham luan chuyen / 11 ton
    # khong ban) - 30 dong tra ve KHONG co lay mot dong thieu hang nao. Chatbot doc duoc con so 16
    # roi phai tu noi "he thong danh dau 16 SKU nhung toi chua lay duoc danh sach chi tiet".
    # Nay danh han han ngach cho tung nhom truoc, phan con lai moi lap theo uu tien.
    limit_n = max(1, min(int(limit or 30), 50))
    _nhom_theo_trang_thai = {}
    for row in actionable:           # actionable da sap theo _priority nen tung nhom cung dung thu tu
        _nhom_theo_trang_thai.setdefault(row["status"], []).append(row)
    # Nhom nao dang duoc focus uu tien thi duoc chon truoc trong moi vong.
    _thu_tu_nhom = sorted(_nhom_theo_trang_thai, key=lambda tt: _priority(_nhom_theo_trang_thai[tt][0]))
    _han_ngach = max(3, limit_n // 6)
    shown_rows, _da_chon = [], set()
    for _vong in range(_han_ngach):
        _them_duoc = False
        for _tt in _thu_tu_nhom:
            _ds = _nhom_theo_trang_thai[_tt]
            if _vong < len(_ds) and len(shown_rows) < limit_n:
                shown_rows.append(_ds[_vong])
                _da_chon.add(id(_ds[_vong]))
                _them_duoc = True
        if not _them_duoc:
            break
    for row in actionable:
        if len(shown_rows) >= limit_n:
            break
        if id(row) not in _da_chon:
            shown_rows.append(row)
            _da_chon.add(id(row))
    shown_rows.sort(key=_priority)
    buyer_candidates = []
    candidate_codes = [
        r["item_code"] for r in shown_rows if r["average_monthly_qty_3m"] > 0
    ][:10]
    if candidate_codes:
        candidate_marks = ",".join("?" for _ in candidate_codes)
        buyer_conditions = ["v.doc_date>=? AND v.doc_date<?", f"v.item_code IN ({candidate_marks})"]
        buyer_params = [month_start, month_exclusive_end, *candidate_codes]
        buyer_joins = "LEFT JOIN dms_khachhang kh ON kh.code=v.customer_code"
        if area_code:
            buyer_joins += " LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=kh.city_id"
            buyer_conditions.append("tp.area_code=?")
            buyer_params.append(area_code)
        try:
            buyers = _q(
                "SELECT v.item_code, v.customer_code, COALESCE(kh.name,v.customer_code) customer_name, "
                "SUM(CASE WHEN COALESCE(v.unit_price,0)>0 THEN COALESCE(v.quantity,0) ELSE 0 END) qty_3m, "
                "SUM(COALESCE(v.amount9,0)) revenue_3m "
                f"FROM vhoadon_otc v {buyer_joins} WHERE {' AND '.join(buyer_conditions)}{emp_sql} "
                "GROUP BY v.item_code,v.customer_code,kh.name ORDER BY v.item_code, revenue_3m DESC",
                (*buyer_params, *emp_params),
            )
            per_item = {}
            for buyer in buyers:
                per_item.setdefault(buyer["item_code"], []).append(buyer)
            for code, customers in per_item.items():
                buyer_candidates.append({"item_code": code, "customers": customers[:3]})
        except (sqlite3.Error, OSError):
            pass

    return {
        "status": "OK_DERIVED",
        "focus": focus,
        "period": {"from": month_start, "to": month_end},
        "total_actionable_skus": len(actionable),
        "status_counts": {
            status: sum(1 for row in actionable if row["status"] == status)
            for status in (
                "CO_NGUY_CO_THIEU_HANG_DERIVED",
                "CHAM_LUAN_CHUYEN_DERIVED",
                "TON_KHONG_BAN_3_THANG",
            )
        },
        "rows": shown_rows,
        "so_dong_da_hien": len(shown_rows),
        "so_dong_chua_hien_theo_trang_thai": {
            tt: len(ds) - sum(1 for r in shown_rows if r["status"] == tt)
            for tt, ds in _nhom_theo_trang_thai.items()
            if len(ds) > sum(1 for r in shown_rows if r["status"] == tt)
        },
        "answer_rule": (
            "Moi trang thai co trong status_counts deu DA co it nhat vai dong mau trong rows. "
            "Neu so_dong_chua_hien_theo_trang_thai con so du cho mot trang thai, day la danh sach BI "
            "CAT theo limit - noi ro con bao nhieu SKU chua liet ke va co the goi lai voi limit lon "
            "hon hoac focus='shortage'/'overstock'. TUYET DOI khong noi la khong lay duoc danh sach."),
        "recent_customer_candidates": buyer_candidates,
        # 18/09/2026 (cau M40): hai ve cua phep chia KHONG cung don vi. brv_sanpham.unit cua cac ma
        # nay la "Vien" va ton kho theo lo dem bang vien, trong khi hoa don ban theo HOP - don gia
        # 17.143d cua Hysdin la gia mot hop (Hop x 2 vi x 10 vien), khong phai gia mot vien. Vi vay
        # months_of_cover bi thoi phong dung bang he so quy cach: Hysdin ra 155 thang trong khi quy
        # ve hop la 5.730/848 = khoang 6,8 thang - sai hon 20 lan.
        # KHONG tu suy he so tu ten quy cach: "Kien x 80 hop x 1 tui x 5 vi x 12 vien" khong cho biet
        # hoa don tinh theo Kien hay theo Hop (doi chieu don gia thi la Hop, tuc 60 chu khong phai
        # 4.800). Kho local khong co bang quy doi nao. Cho DNH chot nguon he so truoc khi sua cong thuc.
        "don_vi_hai_ve_khong_khop": True,
        "canh_bao_don_vi": (
            "months_of_cover KHONG phai so thang. Ton kho dem theo don vi le cua danh muc (thuong la "
            "VIEN) con hoa don ban theo HOP, nen ty le nay bi thoi phong theo he so quy cach cua tung "
            "SKU. KHONG duoc "
            "XEP HANG cac SKU theo ty le nay vi he so quy doi khac nhau; thu tu rows chi de hien thi. "
            "TUYET DOI khong doc thanh 'ton X thang' hay 'du ban X thang'. "
            "Nhom TON_KHONG_BAN_3_THANG khong bi anh huong (ban bang 0 thi don vi nao cung la "
            "0); nhom CO_NGUY_CO_THIEU_HANG_DERIVED van dang tin theo huong THAN TRONG (ton dang bi "
            "tinh cao hon thuc te ma van bao thieu, tuc thieu that); rieng CHAM_LUAN_CHUYEN_DERIVED "
            "bi bao nhieu hon thuc te."),
        "definition": (
            "Canh bao suy dien tu ton hien co so voi binh quan ban OTC 3 thang da chot. "
            "Khong co du lieu don cho xu ly/chia ton/khach cam ket nen KHONG ket luan da mat don hay doanh thu. "
            + ("Binh quan ban va khach mua gan day CHI thuoc doi QLV; ton kho van la ton dung chung "
               "trong pham vi vung da loc, chua phan bo cho doi. Chua tinh duoc so thang du ban khi "
               "thieu quy doi don vi ton va ban; "
               "TON_KHONG_BAN_3_THANG chi nghia la doi nay khong ban, khong ket luan ca vung khong ban."
               if scope_employee_code else "")),
    }


def sku_revenue_drop_vs_stock(months_back: int = 3, area_code: str = None,
                              min_prev_revenue: float = 50_000_000,
                              drop_pct_threshold: float = 30, limit: int = 30,
                              scope_area_code: str = None, scope_channel: str = None,
                              scope_employee_code: str = None) -> dict:
    """Two adjacent complete-calendar-month periods against recorded lot stock.

    Stock is fiscal-year lot data, NOT proven current available-to-promise stock.
    Missing lot rows are unknown, not zero; positive stock alone is not overstock.
    """
    area_code = scope_area_code or area_code
    if area_code and area_code not in _AREA_TO_BRANCH:
        return {"error": "Vung khong hop le; khong mo rong sang ton kho toan cong ty."}
    channel = str(scope_channel or "").upper()
    if channel not in {"", "OTC", "ETC"}:
        return {"error": "Kenh khong hop le."}
    months_back = max(1, min(int(months_back or 3), 12))
    limit = max(1, min(int(limit or 30), 100))
    min_prev_revenue = max(0, float(min_prev_revenue))
    drop_pct_threshold = max(0, float(drop_pct_threshold))
    end_month = _latest_complete_revenue_month()
    if not end_month:
        return {"error": "Chua co thang doanh thu day du."}
    cur_month = _month_add(end_month, 1 - months_back)
    prev_month = _month_add(cur_month, -months_back)
    cur_from, _ = _month_bounds(cur_month)
    _, cur_to = _month_bounds(end_month)
    prev_from, _ = _month_bounds(prev_month)
    _, prev_to = _month_bounds(_month_add(cur_month, -1))
    periods = {"period_current": {"from": cur_from, "to": cur_to},
               "period_previous": {"from": prev_from, "to": prev_to}}
    # This report needs item-level detail, not the longer customer-only rollup.
    if prev_from < _detail_cutoff():
        return {**periods, "status": "source_gap", "rows": [],
                "warning": "Thieu lich su hoa don chi tiet cho hai ky; khong suy thang thieu thanh 0."}
    parts, params = [], []
    for label, start, end in (("CUR", cur_from, cur_to), ("PREV", prev_from, prev_to)):
        emp_sql, emp_params = _employee_scope_clause(scope_employee_code, "v", as_of=end)
        for ch, table, customers in (("OTC", "vhoadon_otc", "dms_khachhang"),
                                      ("ETC", "vhoadon_etc", "dmssx_khachhang")):
            if channel and ch != channel:
                continue
            # EXISTS avoids multiplying invoice lines if a customer dimension has duplicates.
            area_sql = (f" AND EXISTS (SELECT 1 FROM {customers} kh JOIN dim_tinhthanhpho tp "
                        "ON tp.city_id=kh.city_id WHERE kh.code=v.customer_code AND tp.area_code=?)"
                        if area_code else "")
            parts.append(f"SELECT '{label}' period, v.item_code, v.amount9 revenue FROM {table} v "
                         f"WHERE v.doc_date>=? AND v.doc_date<?{area_sql}{emp_sql}")
            exclusive = (dt.date.fromisoformat(end[:10]) + dt.timedelta(days=1)).isoformat()
            params.extend([start, exclusive, *([area_code] if area_code else []), *emp_params])
    raw = _q("WITH x AS (" + " UNION ALL ".join(parts) + ") "
             "SELECT item_code,period,SUM(revenue) revenue FROM x GROUP BY item_code,period", tuple(params))
    year = _nam_moi_nhat("brv_tonkhodklot", "year")
    if year is None:
        return {**periods, "status": "source_gap", "rows": [],
                "warning": "Chua xac dinh duoc nam ton kho theo lo; khong cong nhieu nam."}
    stock_params = [year]
    stock_area = ""
    if area_code:
        stock_area = " AND k.branch_code=?"
        stock_params.append(_AREA_TO_BRANCH[area_code])
    stock_rows = _q(
        "SELECT sp.code item_code, MAX(sp.name) item_name, SUM(t.quantity) stock_qty "
        "FROM brv_tonkhodklot t JOIN brv_sanpham sp ON sp.id_code=t.item_id "
        "LEFT JOIN brv_kho k ON k.id_code=t.warehouse_id "
        f"WHERE t.is_active=1 AND t.year=?{stock_area} GROUP BY sp.code", tuple(stock_params))
    stock = {r["item_code"]: r for r in stock_rows}
    sales = {}
    for row in raw:
        if row["item_code"]:
            sales.setdefault(row["item_code"], {})[row["period"]] = _f(row["revenue"])
    groups = {"zero_recorded_stock": [], "positive_recorded_stock": [], "unknown_or_negative_stock": []}
    for code, values in sales.items():
        previous, current = values.get("PREV", 0), values.get("CUR", 0)
        if previous <= 0 or previous < min_prev_revenue:
            continue
        drop = (previous - current) / previous * 100
        if drop < drop_pct_threshold:
            continue
        item = stock.get(code, {})
        qty = _f(item["stock_qty"]) if item.get("stock_qty") is not None else None
        key = ("unknown_or_negative_stock" if qty is None or qty < 0 else
               "zero_recorded_stock" if qty == 0 else "positive_recorded_stock")
        groups[key].append({"item_code": code, "item_name": item.get("item_name"),
                            "prev_revenue": previous, "cur_revenue": current,
                            "revenue_delta": current - previous, "revenue_drop_pct": drop,
                            "stock_qty": qty})
    for rows in groups.values():
        rows.sort(key=lambda r: (r["revenue_delta"], r["item_code"]))
    return {**periods, "status": "ok", "area_code": area_code, "channel": channel or "ALL",
            "stock_fiscal_year": year, "stock_basis": "FISCAL_YEAR_LOT_RECORDS_NOT_LIVE_ATP",
            "thresholds": {"min_prev_revenue": min_prev_revenue, "drop_pct": drop_pct_threshold},
            "counts": {key: len(rows) for key, rows in groups.items()},
            **{key: rows[:limit] for key, rows in groups.items()},
            "truncated": any(len(rows) > limit for rows in groups.values()),
            "definition": "Hai ky thang duong lich da tron; ton kho la so ghi nhan theo lo/nam. "
                          "Khong co dong ton = chua biet, khong phai 0. Con ton khong dong nghia ton cao. "
                          "Khong ket luan mat don/doanh thu do thieu hang hay nhu cau da xac nhan."}


def inventory_expiry_report(area_code: str = None, max_bucket: str = None, limit: int = 30,
                             focus: str = "all",
                             scope_area_code: str = None, scope_employee_code: str = None) -> dict:
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
    scope_employee_code: loc nhu cau ban va khach mua theo doi QLV; ton kho dung chung theo vung.

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

    sql = """SELECT t.item_lot_code, t.item_id, sp.code item_code, sp.name item_name, t.quantity, t.branch_code,
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
    stock_by_item, item_names = {}, {}
    for r in rows:
        qty = _f(r["quantity"])
        item_code = r["item_code"] or str(r["item_id"])
        stock_by_item[item_code] = stock_by_item.get(item_code, 0.0) + qty
        item_names[item_code] = r["item_name"] or item_names.get(item_code)
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
            "item_code": item_code,
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
    supply_risk = _inventory_supply_risk(
        stock_by_item, item_names, area_code, limit=limit, focus=focus,
        scope_employee_code=scope_employee_code,
    )

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
        "supply_risk": supply_risk,
        "note": (f"Chi hien thi {min(limit, len(detail))}/{len(detail)} lo (sap xep gan het han nhat "
                 f"truoc) - dung 'summary' de biet TONG THE ca khung, 'rows' chi la mau minh hoa."
                 if len(detail) > limit else None),
        "sync_warning": sync_warning,
    }


# area_code (MB/MB2/MN/MT) -> ten mien tieng Viet, gom MB+MB2 thanh Mien Bac (theo REGION_SQL_MARKERS).
_AREA_TO_REGION_VI = {m: REGION_NAMES_VI[key] for key, ms in REGION_SQL_MARKERS.items() for m in ms}


def _collection_source_gap() -> dict:
    """Gioi han nguon cho S45/V37 - tach khoi so du cong no hien tai.

    Snapshot SP cong no cho biet con no bao nhieu, khong cho biet trong thang da thu
    bao nhieu, ke hoach thu hay cam ket cua TDV/khach. Tra cau truc co dinh de model
    khong suy ra nham "thu tien" tu chenh lech so du giua hai snapshot.
    """
    return {
        "status": "source_gap",
        "available_metrics": ["so_du_cong_no_hien_tai", "no_qua_han_hien_tai", "tuoi_no_hien_tai"],
        "unavailable_metrics": [
            "so_tien_da_thu_trong_thang_theo_tdv_khach",
            "ke_hoach_thu_tien",
            "cam_ket_thu_va_han_cam_ket",
            "doi_chieu_chung_tu_thu_voi_hoa_don",
        ],
        "reason": (
            "Kho chatbot chi co snapshot du no tu usp_DeptAccDueDate_GetData; chua co chung tu thu "
            "gan hoa don/khach, chi tieu thu tien va bang cam ket thu."),
        "answer_rule": (
            "Khong suy ra so da thu tu chenh lech hai snapshot va khong gan nhan cam ket qua han. "
            "Chi duoc trinh bay so du/no qua han hien tai neu nguoi dung chap nhan pham vi thay the."),
    }


def _collection_actual_mtd(as_of_date: str = None, scope_area_code: str = None,
                           scope_channel: str = None, scope_employee_code: str = None,
                           customer_limit: int = 100) -> dict:
    """V37/S45: but toan thu BC/PT vao 131 tren Bravo, tach ro phan khong co nguon.

    Khong suy so da thu tu chenh lech snapshot no. BC/PT la phieu bao co/phieu thu;
    BT, hoa don va hang tra khong phai tien thu. Gan TDV theo phan cong khach hien tai
    trong DMS, khong suy ra TDV truc tiep thu tien hay nguoi lap phieu.
    """
    today = dt.date.today()
    as_of = dt.date.fromisoformat(str(as_of_date or today.isoformat())[:10])
    if as_of > today:
        as_of = today
    date_from = as_of.replace(day=1)
    date_to_exclusive = as_of + dt.timedelta(days=1)
    if scope_employee_code and scope_channel and scope_channel.upper() != "OTC":
        raise KhongXacDinhDuocDoi("Chua co phan cong khach ETC theo doi QLV de loc thu tien.")
    channel = "OTC" if scope_employee_code else str(scope_channel or "ALL").upper()
    if channel not in {"ALL", "OTC", "ETC"}:
        raise ValueError(f"scope_channel khong hop le: {scope_channel}")
    team_codes = None
    if scope_employee_code:
        team_codes = sorted(team_customer_codes(_q, scope_employee_code, as_of))
        if not team_codes:
            raise KhongXacDinhDuocDoi(
                f"Khong xac dinh duoc khach cua doi {scope_employee_code} de loc thu tien.")
    params = {"date_from": date_from, "date_to": date_to_exclusive}
    team_clause = ""
    if team_codes is not None:
        holders = []
        for index, code in enumerate(team_codes):
            key = f"team_customer_{index}"
            params[key] = code
            holders.append(f":{key}")
        team_clause = f" AND k.Code IN ({','.join(holders)})"
    area_clause = ""
    if scope_area_code:
        holders = []
        for index, area in enumerate(_area_markers(scope_area_code)):
            key = f"scope_area_{index}"
            params[key] = area
            holders.append(f":{key}")
        area_clause = f" AND tp.AreaCode IN ({','.join(holders)})"
    rows = []
    for source_channel, class_code, customer_table, dms_table in (
        ("OTC", "TM", "BRV_KhachHang", "DMS_KhachHang"),
        ("ETC", "SX", "BRVSX_KhachHang", "DMSSX_KhachHang"),
    ):
        if channel not in {"ALL", source_channel}:
            continue
        dms_employee = "MAX(d.EmpDMSCode1)" if source_channel == "OTC" else "CAST(NULL AS varchar(50))"
        area_join = (" JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=d.CityId "
                     if scope_area_code else "")
        sql = f"""
            SELECT k.Code CustomerCode,MAX(k.Name) CustomerName,
                   {dms_employee} EmployeeDMSCode,
                   SUM(h.Amount) Amount,COUNT(*) PostingRows,
                   SUM(CASE WHEN h.DocCode='BC' THEN h.Amount ELSE 0 END) BankCreditAmount,
                   SUM(CASE WHEN h.DocCode='PT' THEN h.Amount ELSE 0 END) CashReceiptAmount
            FROM dbo.vHTTPhatSinh h
            JOIN dbo.{customer_table} k ON k.Id=h.CustomerId
            LEFT JOIN dbo.{dms_table} d ON d.Code=k.Code
            {area_join}
            WHERE h.ClassCode=:class_code AND h.IsActive=1
              AND h.DocCode IN ('BC','PT') AND h.Account LIKE '131%'
              AND h.DocDate>=:date_from AND h.DocDate<:date_to
              {team_clause}{area_clause}
            GROUP BY k.Code
        """
        source_rows = _q_bravo(sql, {**params, "class_code": class_code})
        for source_row in source_rows:
            rows.append({
                "channel": source_channel,
                "customer_code": source_row["CustomerCode"],
                "customer_name": source_row.get("CustomerName"),
                "employee_dms_code": source_row.get("EmployeeDMSCode"),
                "actual_collected": _f(source_row.get("Amount")),
                "bank_credit_amount": _f(source_row.get("BankCreditAmount")),
                "cash_receipt_amount": _f(source_row.get("CashReceiptAmount")),
                "posting_rows": int(source_row.get("PostingRows") or 0),
            })
    rows.sort(key=lambda row: (-row["actual_collected"], row["customer_code"]))
    employee_groups = {}
    for row in rows:
        key = (row["channel"], row["employee_dms_code"] or "CHUA_GAN_TDV")
        group = employee_groups.setdefault(key, {
            "channel": key[0], "employee_dms_code": key[1],
            "actual_collected": 0.0, "customers": 0,
        })
        group["actual_collected"] += row["actual_collected"]
        group["customers"] += 1
    employee_rows = sorted(employee_groups.values(),
                           key=lambda row: (-row["actual_collected"], row["employee_dms_code"]))
    limit = max(1, min(int(customer_limit or 100), 200))
    _warn("V37: PHAI noi ke hoach thu va cam ket/hang cam ket CHUA co nguon; "
          "so BC/PT chi la but toan thu vao 131, khong phai doi chieu hoa don day du.",
          code="v37_collection_partial", severity="warning",
          message=("Đã tra cứu được bút toán thu BC/PT vào tài khoản 131 theo khách và "
                   "TDV phụ trách hiện tại. Chưa có nguồn kế hoạch thu và cam kết hoặc "
                   "hạn cam kết để so sánh hay xác định quá hạn; số thu chưa đối chiếu "
                   "đầy đủ với từng hóa đơn."))
    return {
        "status": "partial", "period_from": date_from.isoformat(),
        "period_to": as_of.isoformat(), "source": "Bravo dbo.vHTTPhatSinh (BC/PT, Account 131)",
        "scope_channel": channel, "scope_area_code": scope_area_code,
        "scope_employee_code": scope_employee_code,
        "total_actual_collected": sum(row["actual_collected"] for row in rows),
        "total_customers": len(rows),
        "total_posting_rows": sum(row["posting_rows"] for row in rows),
        "by_employee": employee_rows,
        "by_customer": rows[:limit], "customers_not_shown": max(0, len(rows) - limit),
        "available_metrics": ["thu_thuc_te_BC_PT_vao_131_theo_khach_va_TDV_phu_trach_hien_tai"],
        "unavailable_metrics": ["ke_hoach_thu_tien", "cam_ket_thu_va_han_cam_ket",
                                "doi_chieu_day_du_chung_tu_thu_voi_hoa_don"],
        "definition": (
            "So thu la tong but toan BC/PT con hieu luc vao tai khoan 131 trong thang den "
            "period_to, gan theo MA KHACH. TDV la nguoi phu trach khach HIEN TAI tren DMS, "
            "khong phai nguoi truc tiep thu tien. Khong cong BT/hoa don/hang tra. "
            "Chua doi chieu phieu thu voi tung hoa don, ung truoc hay toan bo cach thanh toan; "
            "khong goi day la tong thu chinh thuc neu DNH chua chot."),
        "answer_rule": (
            "Tra so thu BC/PT theo TDV/khach va noi ro pham vi, so khach bi cat. "
            "KHONG noi 'khong co du lieu' cho ca cau. Ke hoach thu va cam ket qua han "
            "chua co nguon: neu ro tung phan, khong tu suy ra tu du no."),
    }


def _gan_nguoi_phu_trach_cong_no(rows: list) -> None:
    """Gan TDV/QLV phu trach (ma kem ten) cho danh sach khach cong no, theo snapshot KPI gan nhat cua
    TUNG khach. Nguon phan cong chi phu OTC; khach khong co phan cong thi ghi ro, khong bo trong im lang."""
    codes = [r["customer_code"] for r in rows if r.get("customer_code")]
    if not codes:
        return
    ph = ",".join("?" for _ in codes)
    try:
        assignments = _q(
            "WITH gan AS (SELECT customer_code, MAX(save_date) d FROM fact_tonghopkhachhang "
            f"WHERE customer_code IN ({ph}) GROUP BY customer_code) "
            "SELECT f.customer_code, f.employee_code, f.manager_code, nv.position_code, 0 amount_ct "
            "FROM fact_tonghopkhachhang f JOIN gan ON gan.customer_code=f.customer_code AND gan.d=f.save_date "
            "LEFT JOIN (SELECT employee_code, MAX(position_code) position_code FROM dim_nhanvien "
            "GROUP BY employee_code) nv ON nv.employee_code=f.employee_code", tuple(codes))
    except sqlite3.OperationalError:
        assignments = []
    by_customer = {}
    for row in _prefer_employee_tier(assignments):
        by_customer.setdefault(row["customer_code"], row)
    names = _employee_name_map([a["employee_code"] for a in by_customer.values()]
                               + [a["manager_code"] for a in by_customer.values()])
    for row in rows:
        assigned = by_customer.get(row.get("customer_code"))
        if assigned:
            row.update(_nguoi_phu_trach(assigned, names))
        else:
            row.update(employee_code=None, employee_name=None, manager_code=None, manager_name=None,
                       nguoi_phu_trach_ghi_chu=("Khong co phan cong KPI (OTC) cho khach nay trong kho; "
                                                "khach ETC khong co TDV/QLV phu trach tren nguon."))


def receivables_overview(top_n: int = 10, scope_area_code: str = None,
                         scope_channel: str = None, scope_employee_code: str = None,
                         include_collection: bool = False,
                         collection_as_of_date: str = None) -> dict:
    """Tong quan CONG NO tu kho local fact_congno_khachhang (snapshot tuc thoi tu SP goc DNH
    usp_DeptAccDueDate_GetData): tong du no, tong qua han, ty le qua han, tach theo KENH (OTC/ETC)
    va theo VUNG, top N khach no qua han nhieu nhat.

    MOT DONG = (khach x kenh) nen luon SUM. scope_area_code: EP LOC theo vung khi tai khoan bi gioi
    han (regional_director/qlv) - dung REGION_SQL_MARKERS de gom ca MB va MB2 cho mien Bac.
    scope_channel: EP LOC OTC/ETC ngay trong SQL cho tai khoan Giam doc Kenh/OTC-only; khong chi
    an breakdown sau khi da tinh tong, de tong/top khach/bucket deu khong the lot kenh khac.
    scope_employee_code: khach phan cong cho doi QLV theo KPI, cung nguon voi bao cao QLV.
    Nguon phan cong nay chi phu OTC; khong gan no ETC cua khach trung ma vao doi OTC.

    Ket qua LUON kem "aging_bucket_note" (xem _AGING_BUCKET_NOTE) canh bao 4 bucket overdue_1_15/
    15_30/30_45/gt_45 lay THANG tu SP goc, co the khac moc Excel noi bo DNH hay dung.

    4 trang thai giong _customer_receivable:
      - unavailable: bang chua co du lieu -> canh bao BAT BUOC, khong ket luan "khong co no".
      - ok + canh bao moc thoi gian: snapshot cu > 6 gio.
      - ok: binh thuong.
    (khong co trang thai no_data rieng: neu co du lieu ma vung nay = 0 thi cac tong = 0, van la 'ok'.)
    """
    try:
        requested_top_n = min(100, max(1, int(top_n)))
    except (TypeError, ValueError):
        requested_top_n = 10

    collection_activity = _collection_source_gap()
    if include_collection:
        try:
            collection_activity = _collection_actual_mtd(
                collection_as_of_date, scope_area_code, scope_channel, scope_employee_code)
        except KhongXacDinhDuocDoi:
            raise
        except Exception as exc:
            collection_activity = {
                **_collection_source_gap(),
                "source_error": f"Chua doc duoc chung tu BC/PT tren Bravo: {exc}",
            }

    conditions, params = [], []
    team_scope = None
    if scope_employee_code:
        if scope_channel and str(scope_channel).strip().upper() != "OTC":
            raise KhongXacDinhDuocDoi(
                "Chua co phan cong khach ETC theo doi QLV de loc cong no; "
                "khong the dung phan cong OTC hay cong no ca vung thay the."
            )
        scope_channel = "OTC"
        assignment_day = dt.date.today()
        customer_codes = sorted(team_customer_codes(_q, scope_employee_code, assignment_day))
        if not customer_codes:
            raise KhongXacDinhDuocDoi(
                f"Khong xac dinh duoc khach thuoc doi {scope_employee_code} trong phan cong KPI; "
                "CHUA danh gia duoc cong no cua doi, khong ket luan khong co no."
            )
        conditions.append(f"customer_code IN ({','.join('?' for _ in customer_codes)})")
        params.extend(customer_codes)
        team_scope = {
            "manager_code": scope_employee_code,
            "assignment_as_of": assignment_day.isoformat(),
            "assignment_window_days": TEAM_CUSTOMER_WINDOW_DAYS,
            "assigned_customers": len(customer_codes),
            "source": "FACT_TongHopKhachHang.ManagerCode/EmployeeCode",
            "definition": (
                "Khach thuoc doi theo snapshot gan nhat cua TUNG khach, gom khach QLV tu phu trach. "
                "Khach da chuyen doi khong con o doi cu; khong chi lay khach co hoa don trong thang. "
                "Chi phu OTC. Khach khong con phan cong trong cua so du lieu khong the gan ve doi."
            ),
        }
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
              "tra loi 'chua tra cuu duoc cong no', TUYET DOI KHONG ket luan 'khong co no'.",
              code="receivables_unavailable", severity="warning",
              message=("Chưa tra cứu được công nợ trong phạm vi tài khoản vì nguồn công nợ chưa có dữ liệu. "
                       "Chưa thể xác nhận có nợ hay không."))
        return {"receivable_status": "unavailable", "receivable_as_of": None,
                "receivable_source": "bao cao cong no goc DNH (SP)",
                "receivable_warning": (
                    "Chua tra cuu duoc cong no trong pham vi tai khoan tai thoi diem nay."),
                "scope_area_code": scope_area_code, "scope_channel": channel,
                "scope_employee_code": scope_employee_code, "team_scope": team_scope,
                "collection_activity": collection_activity}

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
             f"COALESCE(SUM(balance_end),0) bal, COALESCE(SUM(total_overdue),0) od, "
             f"COUNT(*) OVER() eligible_n "
             f"FROM fact_congno_khachhang {where} GROUP BY customer_code "
             f"HAVING SUM(total_overdue) > 0 ORDER BY SUM(total_overdue) DESC LIMIT ?",
             tuple(params) + (requested_top_n,))
    # 22/09/2026 (UAT dnh_etc 22/09): SQL da ORDER BY no qua han DESC, nhung bang tra loi ra thu tu
    # 1,90 - 1,68 - 1,51 - 1,94 - 1,89: model tu xep lai khi trinh bay. Danh so rank san de thu tu
    # nam trong CHINH du lieu, model chi viec in theo rank.
    top_customers = [{"rank": index, "customer_code": r["customer_code"], "customer_name": r["name"],
                      "balance_end": _f(r["bal"]), "total_overdue": _f(r["od"])}
                     for index, r in enumerate(top, start=1)]
    eligible_top_count = int(top[0]["eligible_n"]) if top else 0
    # 15/09/2026 (UAT OTC C-Level 14:25 "Bo sung nhan vien, quan ly vung tuong ung"): kem TDV/QLV phu
    # trach theo phan cong KPI cua tung khach - pham vi da loc o tren nen khong mo rong quyen.
    _gan_nguoi_phu_trach_cong_no(top_customers)
    # 15/09/2026 (UAT 14:23 "thieu HCM04162, HCM04298"): hai khach nay du no 2,91 ty / 1,06 ty nhung SP goc
    # ghi qua han = 0 (toan bo o CloseBal0). Top VAN xep theo no qua han (anh Dang chot); liet ke rieng
    # khach du no lon chua qua han de nguoi doc khong nham la bi bo sot.
    big_not_overdue = _q(
        f"SELECT customer_code, MAX(customer_name) name, COALESCE(SUM(balance_end),0) bal "
        f"FROM fact_congno_khachhang {where} GROUP BY customer_code "
        f"HAVING COALESCE(SUM(total_overdue),0)=0 AND COALESCE(SUM(balance_end),0)>0 "
        f"ORDER BY SUM(balance_end) DESC LIMIT 5", tuple(params))
    large_balance_not_overdue = [{"customer_code": r["customer_code"], "customer_name": r["name"],
                                  "balance_end": _f(r["bal"]), "total_overdue": 0.0}
                                 for r in big_not_overdue]
    _gan_nguoi_phu_trach_cong_no(large_balance_not_overdue)

    result = {
        "receivable_status": "ok",
        "receivable_source": "bao cao cong no goc DNH (SP)",
        "receivable_as_of": snapshot_at,
        "scope_area_code": scope_area_code,
        "scope_channel": channel,
        "scope_employee_code": scope_employee_code,
        "team_scope": team_scope,
        "receivable_definition": (
            "Du no/no qua han tai ngay receivable_as_of cua snapshot SP; khong phai so chot cuoi "
            "thang nguoi dung dang hoi. No qua han khong tu dong la no xau; khong suy so tien da thu."
        ),
        "total_balance_end": total_balance,
        "total_overdue": total_overdue,
        "overdue_pct": (total_overdue / total_balance * 100) if total_balance else 0.0,
        "overdue_1_15": _f(tot["b1"]), "overdue_15_30": _f(tot["b2"]),
        "overdue_30_45": _f(tot["b3"]), "overdue_gt_45": _f(tot["b4"]),
        "aging_bucket_note": _AGING_BUCKET_NOTE,
        "by_channel": channels,
        "by_region": regions,
        "top_overdue_customers": top_customers,
        "top_overdue_requested_count": requested_top_n,
        "top_overdue_eligible_count": eligible_top_count,
        "top_overdue_returned_count": len(top_customers),
        "ranking_basis": ("Top xep theo NO QUA HAN (tong bon nhom tuoi no cua SP goc), khong theo du no. "
                          "In theo dung thu tu 'rank' 1..N, KHONG duoc xep lai theo cot khac. "
                          "Khach du no lon nhung chua qua han nam o du_no_lon_chua_qua_han."),
        "by_region_note": ("by_region da gom DU moi vung ke ca 'Khac/chua xac dinh'. Phai hien du cac dong, "
                           "neu bo dong nao thi tong cac vung se khong khop total_overdue."),
        "du_no_lon_chua_qua_han": large_balance_not_overdue,
        "collection_activity": collection_activity,
    }
    try:
        age_h = (dt.datetime.now() - dt.datetime.fromisoformat(snapshot_at)).total_seconds() / 3600.0
        if age_h > 6:
            result["receivable_warning"] = (
                f"So cong no lay tu snapshot luc {snapshot_at} (da cu hon 6 gio) - luu y moc thoi gian.")
    except Exception:
        pass
    scope_parts = []
    if scope_employee_code:
        scope_parts.append(f"khach cua doi QLV {scope_employee_code}")
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
    bonus_threshold = _bonus_threshold(position_code)
    return {"sales": sales, "target": target, "pct": pct,
            "threshold": bonus_threshold,                       # cong thuong nhom hang (65/70)
            "meets_bonus_threshold": pct >= bonus_threshold,
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


def _roster_snapshot_dates(fdate: str = None) -> list:
    """Hai moc can HOP khi dung FACT de xac dinh DANH SACH NGUOI.

    Moc thang da tron giu nguoi chua ban trong thang moi; moc moi nhat giu nguoi moi vao. Ham nay
    chi dung cho roster, KHONG tu y tron so KPI cua hai ky.
    """
    moc_tron = _fdate_roster(fdate)
    moc_moi = _fact_date_le(fdate) if fdate else _fact_latest_date()
    return [d for d in dict.fromkeys([moc_tron, moc_moi]) if d]


def _roster_employee_sql(fdate: str) -> tuple:
    """Roster hop ky tron + ky moi, moi NV mot dong; quan ly lay theo moc moi nhat cua NV.

    Chi cung cap danh tinh/quan he. Tuyet doi khong mang target/doanh so ky cu sang ky moi.
    """
    queries, params = [], []
    for moc in _roster_snapshot_dates(fdate):
        queries.append(
            "SELECT e.employee_code, MAX(e.manager_code) manager_code, e.save_date roster_snapshot "
            f"FROM fact_tonghopkhachhang e JOIN {_MONTH_LATEST_SUBQ} l "
            "ON l.employee_code=e.employee_code AND l.d=e.save_date "
            "GROUP BY e.employee_code,e.save_date"
        )
        params.extend([moc, moc])
    if not queries:
        return "SELECT NULL employee_code,NULL manager_code,NULL roster_snapshot WHERE 0", ()
    return (
        "SELECT employee_code,manager_code,roster_snapshot FROM ("
        "SELECT r.*,ROW_NUMBER() OVER (PARTITION BY employee_code ORDER BY roster_snapshot DESC) rn "
        f"FROM ({' UNION ALL '.join(queries)}) r) WHERE rn=1", tuple(params)
    )


def _team_of_qlv(qlv_employee_code: str, fdate: str = None) -> list:
    """Nhan vien ban hang bao cao TRUC TIEP len 1 QLV, xac dinh qua manager_code THAT tu Bravo
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
    # Giữ người chưa bán ở kỳ mới, nhưng phân công mới phải thay thế quan hệ cũ.
    # UNION sau khi lọc manager giữ một người ở CẢ HAI đội khi họ chuyển QLV.
    # Dùng cùng roster như employee_kpi: chốt mốc mới nhất của từng người TRƯỚC
    # khi lọc theo QLV. Không mang số KPI/target của kỳ cũ sang kỳ đang hỏi.
    roster_sql, roster_params = _roster_employee_sql(fdate)
    return _q(
        f"SELECT DISTINCT e.employee_code, nv.name, nv.position_code FROM ({roster_sql}) e "
        f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code "
        f"WHERE e.manager_code=? AND UPPER(COALESCE(nv.position_code,'')) IN ({_tier_ph()})",
        (*roster_params, qlv_employee_code, *_EMPLOYEE_TIER_POSITIONS),
    )


def _team_of_qlv_tu_luong(qlv_employee_code: str, fdate: str) -> tuple:
    """Doi cua 1 QLV lay tu snapshot LUONG - nguon du phong cho ky QUA KHU. Tra (danh_sach, moc).

    23/09/2026 (V34). Kho giu hai bang snapshot voi hai do dai khac nhau:
      - fact_tonghopkhachhang : sync_warehouse.sync_fact_tonghopkhachhang(days=90)
      - fact_thongketinhluong : sync_warehouse.sync_fact_thongketinhluong() - TOAN BO lich su (24/09)
    Ca hai deu co cot manager_code that tu Bravo. Cac cau hoi khuyen mai roi vao 12/2025 (vi chuoi
    lien ket CTKM dung o 09/01/2026 nen ky mac dinh lui ve thang day du gan nhat) - NGOAI tam bang
    thu nhat nhung VAN trong tam bang thu hai.

    Truoc ban va nay, khong tim thay snapshot <= fdate thi _get_team_dms_ids nhay TOI mot moc SAU ky
    bao cao. Do tren du lieu that (QLV TM23110128, chuong trinh MT_SP_TICHLUYCHAOTHU_ANC, ky 12/2025):
      - chot doi tai 31/12/2025 -> 14 khach / 13 don co HD / 784.895.766d  (khop checker)
      - chot doi tai 30/06/2026 -> 11 khach / 12 don / 775.680.951d        (khop so chatbot da tra)
    Lech vi 3 nguoi roi doi va 3 nguoi moi vao trong khoang do. Con so chenh khong lon (1,2% doanh
    thu) nen nhin bang mat KHONG the phat hien.

    Day cung dung nguon voi checker S-* (FACT_ThongKeTinhLuong + ManagerCode), nen hai ben chot doi
    giong nhau thay vi moi ben mot kieu.
    """
    if not fdate:
        return [], None
    try:
        r = _q("SELECT MAX(save_date) d FROM fact_thongketinhluong WHERE save_date<=?", (str(fdate),))
    except sqlite3.OperationalError:
        return [], None
    moc = r[0]["d"] if r and r[0]["d"] else None
    if not moc:
        return [], None
    return _q(
        f"SELECT DISTINCT l.employee_code, nv.name, nv.position_code "
        f"FROM fact_thongketinhluong l "
        f"LEFT JOIN dim_nhanvien nv ON nv.employee_code=l.employee_code "
        f"WHERE l.save_date=? AND l.manager_code=? "
        f"AND UPPER(COALESCE(nv.position_code,'')) IN ({_tier_ph()})",
        (moc, qlv_employee_code, *_EMPLOYEE_TIER_POSITIONS),
    ), moc


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
                # Doi co the co TDV hoac CTV. CTV dung nguong thuong quan ly 70%, khong duoc
                # gan cung TDV (65%) chi vi bang cay chua hien rieng cot vai tro.
                t_kpi = _kpi_snapshot(t["employee_code"], fdate, t.get("position_code") or "TDV")
                tdv_list.append({"employee_code": t["employee_code"], "name": t["name"],
                                 "position_code": t.get("position_code"), **t_kpi})
            member_roles = {}
            for member in tdv_list:
                role = member.get("position_code") or "UNKNOWN"
                member_roles[role] = member_roles.get(role, 0) + 1
            qlv_entry = {"employee_code": qlv["employee_code"], "name": qlv["name"], **q_kpi,
                         "tdv_count": member_roles.get("TDV", 0), "tdv": tdv_list,
                         "team_member_count": len(tdv_list),
                         "team_member_count_by_position": member_roles, "la_nhom_kenh": is_unit}
            if is_unit:
                qlv_entry["ghi_chu"] = (f"'{qlv['name']}' la NHOM/KENH ban hang (khong phai mot ca "
                                        "nhan/khong co doi TDV rieng) - khi tra loi phai goi dung la "
                                        "kenh/nhom, KHONG duoc noi nhu mot QLV thong thuong.")
            # Trung ten chi la quan sat, khong chung minh trung ban ghi hoac target sai.
            # Canh bao cu con gan cung "0 TDV" va ep model nghi loi nguon du doi da co CS.
            elif qlv["name"] and tp["name"] and qlv["name"].strip() == tp["name"].strip():
                qlv_entry["same_name_as_region_head"] = True
                qlv_entry["ghi_chu"] = (
                    f"'{qlv['name']}' (ma QLV {qlv['employee_code']}) TRUNG TEN voi "
                    f"chinh Truong phong dang phu trach ca vung {tp['area_code']} (ma {tp['employee_code']}) "
                    "nhung rieng ten trung KHONG chung minh trung ban ghi, cong trung hay target sai. "
                    "Khong gan day la bat thuong neu chua doi chieu ho so phan cong va chi tieu. "
                    "Thanh phan doi lay theo team_member_count_by_position, khong goi CS/TK la TDV.")
            qlv_list.append(qlv_entry)
        tree.append({"employee_code": tp["employee_code"], "name": tp["name"], "area_code": tp["area_code"],
                      **tp_kpi, "qlv_count": len(qlv_list), "qlv": qlv_list})
    return {"as_of": fdate, "tree": tree,
            "population_note": "Cay gom TDV/CTV/CS/TK theo phan cong KPI khach hang, hop ky truoc "
                               "va ky hien tai. Danh sach tdv la ten cu; doc position_code tung dong. "
                               "Khong dung so nguoi trong cay thay cho roster TDV tinh luong.",
            "individual_invoice_reconciliation_performed": False}


def _rollup_tier_codes(fdate: str) -> list:
    """Ma cua TANG ROLLUP tai snapshot fdate = nhung nguoi CO quan ly nguoi khac (xuat hien o cot
    manager_code). CO Y khong loc position_code lan is_duplicate - ca hai deu sai nhan tren Bravo:
    cap duoi cua 'Kenh MT'/'Cho si' mang chuc danh TK/CS, va 4 QLV that bi gan co trung lap. Loc
    theo 2 truong do lam bay hoi ca QLV that khoi bao cao (da tung mat 7,93 ty chi tieu Mien Nam).

    Dung CHUNG cho ca group_by='region' va group_by='qlv' de 2 nhanh LUON khop nhau - nguoi dung
    cong tay danh sach QLV phai ra dung tong vung. Cung quy tac voi bao cao email ben D:/DNH
    (src/alerts.py::get_bravo_manager_codes) de 2 he thong khong bao gio lech.
    """
    cac_moc = _roster_snapshot_dates(fdate)
    if not cac_moc:
        return []
    # Moi moc chi lay ban ghi moi nhat cua TUNG nhan vien trong thang do. HOP cac moc de tranh ca
    # hai bay: snapshot moi nhat bo nguoi chua ban; chi snapshot tron bo nguoi moi vao.
    queries = []
    params = []
    for moc in cac_moc:
        queries.append(
            f"SELECT DISTINCT e.manager_code FROM fact_tonghopkhachhang e "
            f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=e.employee_code AND l.d=e.save_date "
            "WHERE e.manager_code IS NOT NULL AND e.manager_code<>''"
        )
        params.extend([moc, moc])
    rows = _q(" UNION ".join(queries), tuple(params))
    return [m["manager_code"] for m in rows]


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
                  f"can doi chieu lai, KHONG khang dinh chac chan voi nguoi dung.",
                  code="regional_kpi_target_mismatch", severity="warning",
                  message=(f"Vùng {r['area_code']}, kỳ {ym}: chỉ tiêu cộng từ nhân viên "
                           f"{r['target']:,.0f} đồng lệch {diff_pct:.1f}% so với chỉ tiêu vùng chính thức "
                           f"{ref:,.0f} đồng. Kết quả KPI cần được đối chiếu lại."))

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
              f"khac nhau. Hoi lai vao thang da tron (vd cuoi thang) de co so day du.",
              code="regional_kpi_missing_areas", severity="warning",
              message=(f"Dữ liệu KPI đến {fdate} thiếu các vùng {', '.join(sorted(missing))}, "
                       f"có tổng chỉ tiêu chính thức {hut:,.0f} đồng. Kết quả chỉ gồm các vùng còn lại, "
                       "chưa đủ để đại diện cho toàn công ty."))


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
    requested_as_of = as_of_date or str(dt.date.today())
    latest_available = _fact_date_le(requested_as_of)
    fdate = latest_available
    if not fdate:
        return []
    managers = _rollup_tier_codes(latest_available)
    if not managers:
        _warn("Khong xac dinh duoc tang quan ly (manager_code rong). KHONG du so lieu de xep hang KPI.",
              code="kpi_manager_hierarchy_unavailable", severity="warning",
              message=(f"Chưa có dữ liệu phân cấp quản lý đến {fdate} nên chưa thể xếp hạng KPI."))
        return []
    ph = ",".join("?" for _ in managers)
    coverage_sql = (
        "SELECT nv.employee_code,MAX(f.month_sale_target) target FROM dim_nhanvien nv "
        f"LEFT JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=nv.employee_code "
        "LEFT JOIN fact_tonghopkhachhang f ON f.employee_code=l.employee_code AND f.save_date=l.d "
        f"WHERE nv.employee_code IN ({ph})"
    )
    coverage_params = list(managers)
    if scope_area_code:
        coverage_sql += " AND nv.area_code=?"
        coverage_params.append(scope_area_code)
    if scope_employee_code and group_by != "region":
        coverage_sql += " AND nv.employee_code=?"
        coverage_params.append(scope_employee_code)
    coverage_sql += " GROUP BY nv.employee_code"
    coverage = _q(coverage_sql, (fdate, fdate, *coverage_params))
    rankable_now = sum(_f(r["target"]) > 0 for r in coverage)
    roster_fdate = _fdate_roster(requested_as_of)
    use_closed_period = not rankable_now
    # A sparse new-month snapshot can already contain a target for ONE manager.
    # The old all-or-nothing fallback then returned only that manager in the
    # default ranking, although the closed month still had the whole team.
    # Compare like-for-like periods for an unqualified/default ranking. An
    # explicit midmonth request still reports only that month's known KPI.
    if as_of_date is None and roster_fdate and roster_fdate != fdate and rankable_now:
        closed_coverage = _q(coverage_sql, (roster_fdate, roster_fdate, *coverage_params))
        rankable_closed = sum(_f(r["target"]) > 0 for r in closed_coverage)
        use_closed_period = rankable_now < rankable_closed
    if use_closed_period and roster_fdate and roster_fdate != fdate:
        fdate = roster_fdate
        coverage = _q(coverage_sql, (fdate, fdate, *coverage_params))
    if latest_available and str(latest_available) != str(fdate):
        _warn(
            f"Xep hang KPI dang dung ky day du gan nhat {fdate}, khong dung snapshot giua thang "
            f"{latest_available} vi snapshot giua thang chi co nguoi da phat sinh ban hang va co "
            "the chua du target.",
            code="kpi_closed_period_used", severity="warning",
            message=(f"Bảng xếp hạng KPI sử dụng kỳ đầy đủ gần nhất đến {fdate}. "
                     f"Dữ liệu mới hơn ngày {latest_available} chưa đủ người hoặc chỉ tiêu để so sánh.")
        )
    unavailable = sum(_f(r["target"]) <= 0 for r in coverage)
    if unavailable:
        _warn(f"{unavailable}/{len(coverage)} ma quan ly trong roster chua du snapshot/target ky "
              f"{fdate[:7]}; bang xep hang chi tinh cac ma co target. KHONG coi nguoi thieu du lieu "
              "la dat 0% hay khong dat KPI.",
              code="kpi_ranking_incomplete_coverage", severity="warning",
              message=(f"Kỳ {fdate[:7]}: {unavailable}/{len(coverage)} mã quản lý chưa đủ dữ liệu hoặc chỉ tiêu. "
                       "Bảng xếp hạng chỉ gồm các mã có chỉ tiêu; chưa thể kết luận những người còn lại "
                       "đạt 0% hoặc không đạt KPI."))

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
                  "vung. PHAI noi ro la chua tra cuu duoc, KHONG duoc tra ve 0 nhu the la khong dat.",
                  code="regional_kpi_hierarchy_unavailable", severity="warning",
                  message=(f"Chưa có dữ liệu phân cấp quản lý đến {fdate} nên chưa tính được KPI theo vùng. "
                           "Chưa thể kết luận vùng không đạt KPI."))
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
                  "dang can kiem tra lai, khong khang dinh chac chan.",
                  code="regional_kpi_nested_managers", severity="warning",
                  message=(f"Dữ liệu đến {fdate} có {len(nested)} mã quản lý đồng thời thuộc một cấp quản lý khác "
                           f"({', '.join(n['employee_code'] for n in nested[:5])}{'…' if len(nested) > 5 else ''}). "
                           "Tổng KPI theo vùng có thể bị tính trùng và cần được đối chiếu lại."))

        sql = f"""SELECT nv.area_code area_code, SUM(e.sales) sales, SUM(e.target) target
                  FROM (SELECT f.employee_code, SUM(f.amount_ct) sales, MAX(f.month_sale_target) target
                        FROM fact_tonghopkhachhang f
                        JOIN {_MONTH_LATEST_SUBQ} l
                          ON l.employee_code=f.employee_code AND l.d=f.save_date
                        GROUP BY f.employee_code HAVING MAX(f.month_sale_target)>0) e
                  JOIN dim_nhanvien nv ON nv.employee_code=e.employee_code
                  WHERE e.employee_code IN ({ph})"""
        params = [fdate, fdate] + managers
        if scope_area_code:
            sql += " AND nv.area_code=?"
            params.append(scope_area_code)
        sql += " GROUP BY nv.area_code"
        rows = _q(sql, tuple(params))
        for r in rows:
            r["as_of"] = fdate
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
              "PHAI noi ro la chua tra cuu duoc, KHONG tra ve danh sach rong nhu the la khong co ai.",
              code="qlv_kpi_hierarchy_unavailable", severity="warning",
              message=(f"Chưa có dữ liệu phân cấp quản lý đến {fdate} nên chưa xếp hạng được QLV. "
                       "Danh sách trống chưa có nghĩa là không có QLV trong phạm vi này."))
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
        row = {"as_of": fdate, "employee_code": qlv["employee_code"], "name": qlv["name"],
               "area_code": qlv["area_code"], **kpi, "la_nhom_kenh": is_unit}
        if is_unit:
            row["ghi_chu"] = (f"'{qlv['name']}' la NHOM/KENH ban hang (khong phai mot ca nhan) - khi "
                              "tra loi phai goi dung la kenh/nhom, KHONG duoc noi nhu mot nhan vien.")
        result.append(row)
    return sorted(result, key=lambda x: -x["pct"])[:limit]


def revenue_view_reconciliation(date_from: str, date_to: str, scope_role: str = None,
                                scope_area_code: str = None, scope_channel: str = None,
                                scope_employee_code: str = None) -> dict:
    """Compare actual Total/base views. No inferred cause or unapproved source preference."""
    if (scope_role not in {"c_level", "admin_ops"} or scope_area_code
            or scope_channel or scope_employee_code):
        return {"error": "Doi soat view toan cong ty chi mo cho C-Level/admin khong gioi han pham vi."}
    start = _parse_report_date(date_from, "date_from")
    end = _parse_report_date(date_to, "date_to")
    if start > end or end > dt.date.today():
        return {"error": "Ky doi soat khong hop le hoac nam trong tuong lai."}
    params = {"date_from": start, "date_to_exclusive": end + dt.timedelta(days=1)}
    results = {}
    for channel, total_view, base_view in (("otc", "vHoaDonTotal", "vHoaDon"),
                                           ("etc", "vHoaDonETCTotal", "vHoaDonETC")):
        rows = _q_bravo(f"""SELECT
            (SELECT COALESCE(SUM(Amount9),0) FROM dbo.{total_view}
             WHERE DocDate>=:date_from AND DocDate<:date_to_exclusive) total_view_revenue,
            (SELECT COUNT(DISTINCT Stt) FROM dbo.{total_view}
             WHERE DocDate>=:date_from AND DocDate<:date_to_exclusive) total_view_invoices,
            (SELECT COALESCE(SUM(Amount9),0) FROM dbo.{base_view}
             WHERE DocDate>=:date_from AND DocDate<:date_to_exclusive) base_view_revenue,
            (SELECT COUNT(DISTINCT Stt) FROM dbo.{base_view}
             WHERE DocDate>=:date_from AND DocDate<:date_to_exclusive) base_view_invoices""", params)
        if not rows:
            return {"error": f"Chua lay du bang doi soat kenh {channel}; khong coi la 0."}
        row = rows[0]
        total, base = _f(row["total_view_revenue"]), _f(row["base_view_revenue"])
        gap = base - total
        pct = gap / abs(total) * 100 if total else None
        results[channel] = {"total_view_revenue": total, "base_view_revenue": base,
                            "total_view_invoices": int(row["total_view_invoices"] or 0),
                            "base_view_invoices": int(row["base_view_invoices"] or 0),
                            "gap_base_minus_total": gap, "gap_pct": pct,
                            "needs_investigation": abs(pct) > .5 if pct is not None else gap != 0}
    return {"date_from": str(start), "date_to": str(end), **results,
            "total": {key: sum(row[key] for row in results.values()) for key in
                      ("total_view_revenue", "base_view_revenue", "gap_base_minus_total")},
            "definition": "Nguon: Bravo truc tiep. Chenh lech can doi chieu dong chung tu de xac dinh "
                          "nguyen nhan; khong tu ket luan view nao dung hon. Nguong 0.5% chi de sang loc, "
                          "khong chung minh chenh lech nho la binh thuong."}


def revenue_reconciliation_check(as_of_date: str = None, area_code: str = None,
                                  scope_area_code: str = None) -> dict:
    """Doi chieu doanh thu TU TREN XUONG (SUM(amount9) tren hoa don OTC, toan vung) voi doanh thu
    CONG DON TU DUOI LEN (TDV -> QLV -> TP, dua tren snapshot fact_tonghopkhachhang qua revenue_tree)
    - phat hien lech giua 2 nguon thay vi chi tin 1 chieu tu tren xuong.

    Hai ve deu CHI tinh OTC va cung ky. Coverage khac 100% la mot KET QUA CHUA DOI SOAT KHOP, khong
    tu dong la "gap binh thuong". Ham khong du bang chung dinh luong de gan phan chenh cho khach mo
    coi/cay to chuc; moi nguyen nhan phai duoc do rieng truoc khi ket luan.
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
        invoice_rows = [r for r in rows
                        if (r["area"] or region_from_customer_code(r["cc"])) == area_code]
    else:
        invoice_rows = _q("SELECT customer_code cc, SUM(amount9) rev FROM vhoadon_otc "
                          "WHERE doc_date BETWEEN ? AND ? GROUP BY customer_code",
                          (month_start, fdate))
    top_down_rev = sum(_f(r["rev"]) for r in invoice_rows)

    # Doanh thu OTC CONG DON TU DUOI LEN: dung LAI cay to chuc cua revenue_tree() (TDV -> QLV -> TP)
    # thay vi tu viet lai truy van rieng - tranh 2 noi dinh nghia khac nhau ve "ai thuoc doi ai".
    tree = revenue_tree(as_of_date=fdate, area_code=area_code)
    leaf_revenue = 0.0
    standalone_rollup_revenue = 0.0
    leaf_counts_by_position = {}
    unique_leaf_codes = set()
    seen_rollup_codes = set()
    rollup_nodes_without_tdv = 0
    for tp in tree["tree"]:
        for qlv in tp["qlv"]:
            if qlv["employee_code"] in seen_rollup_codes:
                continue
            seen_rollup_codes.add(qlv["employee_code"])
            if not qlv["tdv"]:
                # Day la MOT NUT QLV/nhom kenh khong co TDV trong cay, KHONG phai bang chung
                # "mot dia ban/zone chua co QLV". Ten bien cu lam chatbot quy sai nguyen nhan M20.
                rollup_nodes_without_tdv += 1
                # Nhom/kenh trong Bravo co doanh thu o nut roll-up nhung khong co
                # doi TDV trong cay. Cong nut nay MOT LAN; khong xem la TDV ao.
                if qlv.get("la_nhom_kenh"):
                    standalone_rollup_revenue += qlv["sales"]
            for t in qlv["tdv"]:
                leaf_revenue += t["sales"]
                role = t.get("position_code") or "UNKNOWN"
                leaf_counts_by_position[role] = leaf_counts_by_position.get(role, 0) + 1
                unique_leaf_codes.add(t["employee_code"])

    bottom_up_rev = leaf_revenue + standalone_rollup_revenue
    # Do tong trong dung sai 0,5% van co the che mat khach co hoa don nhung
    # khong co dong FACT o bat ky ma TDV/CTV/CS/TK nao. Doi chieu danh sach
    # khach tren dung snapshot/ky, giu nguyen gioi han vung cua tai khoan.
    leaf_area_sql = " AND nv.area_code=?" if area_code else ""
    leaf_customers = {row["customer_code"] for row in _q(
        f"SELECT DISTINCT f.customer_code FROM fact_tonghopkhachhang f "
        f"JOIN {_MONTH_LATEST_SUBQ} l ON l.employee_code=f.employee_code AND l.d=f.save_date "
        f"JOIN dim_nhanvien nv ON nv.employee_code=f.employee_code "
        f"WHERE UPPER(COALESCE(nv.position_code,'')) IN ({_tier_ph()}){leaf_area_sql}",
        (fdate, fdate, *_EMPLOYEE_TIER_POSITIONS, *((area_code,) if area_code else ())),
    )}
    unattributed_rows = [r for r in invoice_rows if r["cc"] not in leaf_customers]
    unattributed_revenue = sum(_f(r["rev"]) for r in unattributed_rows)
    unattributed_customers = {r["cc"] for r in unattributed_rows}

    coverage_pct = (bottom_up_rev / top_down_rev * 100) if top_down_rev else 0.0
    gap_revenue = top_down_rev - bottom_up_rev
    gap_pct = (gap_revenue / top_down_rev * 100) if top_down_rev else None
    if top_down_rev <= 0:
        reconciliation_status = "not_comparable_no_top_down_revenue"
    elif coverage_pct > 100.5:
        reconciliation_status = "overcount_needs_investigation"
    elif coverage_pct < 99.5:
        reconciliation_status = "incomplete_needs_investigation"
    elif unattributed_customers and abs(gap_revenue) > 1:
        reconciliation_status = "incomplete_customer_attribution"
    else:
        reconciliation_status = "matched_within_tolerance"
    result = {
        "as_of": fdate, "area_code": area_code,
        "period_from": month_start, "period_to": fdate,
        "top_down_revenue_otc": top_down_rev,
        "bottom_up_revenue_otc": bottom_up_rev,
        "leaf_revenue_otc": leaf_revenue,
        "standalone_rollup_revenue_otc": standalone_rollup_revenue,
        "unattributed_invoice_customer_count": len(unattributed_customers),
        "unattributed_invoice_revenue_otc": unattributed_revenue,
        "coverage_pct": coverage_pct,
        "gap_revenue": gap_revenue,
        "gap_pct": gap_pct,
        "reconciliation_status": reconciliation_status,
        "matched_within_tolerance": reconciliation_status == "matched_within_tolerance",
        "tolerance_pct_points": 0.5,
        "tdv_count_in_tree": leaf_counts_by_position.get("TDV", 0),
        "leaf_count_in_tree": sum(leaf_counts_by_position.values()),
        "unique_leaf_count_in_tree": len(unique_leaf_codes),
        "leaf_count_by_position": leaf_counts_by_position,
        "reconciliation_level": "region_total",
        "individual_invoice_reconciliation_performed": False,
        "rollup_nodes_without_tdv": rollup_nodes_without_tdv,
        "zones_without_qlv": None,
        "cause_attribution_available": False,
        "note": (f"CA HAI VE deu tinh cho cung ky {month_start} -> {fdate} (luy ke tu dau thang den "
                 "ngay chot snapshot KPI) va CA HAI VE deu CHI kenh OTC - ETC da bi loai khoi ca tu so "
                 "lan mau so nen KHONG phai ly do gay chenh lech, TUYET DOI KHONG giai thich khoang "
                 "chenh bang 'do co kenh ETC'. Coverage ngoai 99,5%-100,5% la CHUA DOI SOAT KHOP va "
                 "can dieu tra; KHONG duoc goi la 'binh thuong', 'gap cau truc da biet', hay tu gan "
                 "nguyen nhan cho khach mo coi/QLV/TDV neu chua co phep do rieng. Neu chua co ty le ky "
                 "truoc thi cung KHONG duoc ket luan gap nay on dinh hay khong bat thuong. "
                 "Doanh thu nhom/kenh khong co TDV duoc cong tu nut roll-up va giu RIENG khoi "
                 "leaf_revenue_otc; khong dem nhom/kenh thanh TDV ao. "
                 "unattributed_invoice_customer_count dem khach co hoa don nhung khong co dong "
                 "FACT tang TDV/CTV/CS/TK trong snapshot; chua biet vi sao chua phan bo. "
                 "rollup_nodes_without_tdv chi dem nut QLV/nhom kenh khong co TDV trong cay, KHONG "
                 "dong nghia voi so zone thieu QLV. cause_attribution_available=false nghia la tool "
                 "CHUA cung cap du phep do de ket luan nguyen nhan cua khoang chenh. "
                 "Phep doi chieu chi o TONG doanh thu; tong khop KHONG chung minh doanh so/target "
                 "tung nguoi khop hoa don hay chinh sach. So nguoi trong cay gom nhieu chuc danh "
                 "(leaf_count_by_position), khong phai roster TDV tinh luong. "
                 "Khi trinh bay PHAI neu ro khoang thoi gian nay de nguoi doc khong tuong dang so 1 "
                 "ngay voi 1 thang."),
    }
    if coverage_pct > 100.5:  # dung sai nho cho lam tron, > han han moi la dau hieu bug that (dem trung)
        result["warning"] = ("BAT THUONG: cong don tu duoi len VUOT QUA tong tren xuong - dau hieu co "
                              "the dang dem trung TDV (vd 1 nguoi xuat hien o nhieu 'to') hoac loi join, "
                              "can kiem tra lai truoc khi tin so lieu nay.")
    elif reconciliation_status == "incomplete_needs_investigation":
        result["warning"] = ("CHUA DOI SOAT KHOP: cong don tu duoi len con thieu so voi tong tren "
                             "xuong. Chua co bang chung dinh luong de quy chenh lech cho nguyen nhan "
                             "cu the; can kiem tra mapping khach hang - NV va cay doi ngu truoc khi "
                             "ket luan day la gap binh thuong.")
        if unattributed_customers:
            result["warning"] += (
                f" Da do duoc {len(unattributed_customers)} khach co hoa don "
                f"{unattributed_revenue:,.0f} d nhung khong co dong FACT tang "
                "TDV/CTV/CS/TK trong snapshot; chua biet vi sao."
            )
    elif reconciliation_status == "incomplete_customer_attribution":
        result["warning"] = (
            "CHUA DOI SOAT KHOP: "
            f"Da cong {standalone_rollup_revenue:,.0f} d tu nhom/kenh khong co TDV. "
            f"{len(unattributed_customers)} khach co hoa don OTC {unattributed_revenue:,.0f} d "
            "nhung khong co dong FACT tang TDV/CTV/CS/TK trong snapshot. "
            f"Tong hoa don va cay con lech {gap_revenue:,.0f} d du nam trong dung sai 0,5%. "
            "Can doi chieu phan cong/nguon; chua ket luan nguyen nhan."
        )
    elif reconciliation_status == "not_comparable_no_top_down_revenue":
        result["warning"] = ("KHONG DU DIEU KIEN DOI SOAT: doanh thu OTC tren xuong bang 0 trong ky, "
                             "khong the dien giai coverage_pct.")
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
               d.balance_end, d.overdue, d.snapshot_at,
               -- 17/09/2026: tong so khach THOA DIEU KIEN truoc khi cat theo LIMIT. Truoc day
               -- customer_count = len(danh sach DA CAT), nen tool bao "co 20 khach" du thuc te co
               -- the hang tram - cung lop loi voi "hoi top 10 tra top 3" (cong no) va "50 hop dong
               -- duoi 50%" (ETC) da sua cung ngay.
               COUNT(*) OVER() total_matching
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
        # Lui ve len(customers) neu vi ly do gi cot total_matching khong co - tha bao thieu con
        # hon vo ca bao cao.
        "customer_count": int(rows[0].get("total_matching") or len(customers)) if rows else 0,
        "returned_count": len(customers),
        "customers": customers,
        "display_rule": (
            "customer_count la TONG so khach thoa dieu kien; customers chi la {0} dong dau (cat theo "
            "limit). Neu customer_count > returned_count PHAI noi ro danh sach la mot phan va nen "
            "con bao nhieu khach chua liet ke - KHONG duoc trinh bay nhu the day la toan bo, va "
            "KHONG duoc cong tien cua phan da liet ke roi goi do la tong so tien can thu."
        ).format(len(customers)),
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


def _promotion_period_fields(program_from, program_to, report_from, report_to) -> dict:
    """Ky chay THAT cua chuong trinh so voi ky bao cao dang xem.

    Mot chuong trinh quy (vd Q1.2026_BPNGAM_10_TQ chay 01/01-31/03) trai ba thang. Neu ky bao cao
    chi la mot thang thi associated_revenue chi phu mot phan vong doi chuong trinh. Truoc day payload
    khong he noi dieu do, nen cau tra loi trinh bay so mot thang nhu la hieu qua ca chuong trinh.
    """
    def _d(v):
        if not v:
            return None
        if isinstance(v, dt.date):
            return v
        try:
            return dt.date.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    pf, pt = _d(program_from), _d(program_to)
    rf, rt = _d(report_from), _d(report_to)
    out = {
        "program_from": pf.isoformat() if pf else None,
        "program_to": pt.isoformat() if pt else None,
    }
    if not pf or not pt:
        out["program_period_status"] = "not_available"
        return out
    months = (pt.year - pf.year) * 12 + (pt.month - pf.month) + 1
    out["program_month_count"] = max(1, months)
    out["program_spans_multiple_months"] = months > 1
    if rf and rt:
        phu_tu, phu_den = max(pf, rf), min(pt, rt)
        so_ngay_phu = (phu_den - phu_tu).days + 1 if phu_den >= phu_tu else 0
        so_ngay_ct = (pt - pf).days + 1
        out["report_covers_program_days"] = so_ngay_phu
        out["program_total_days"] = so_ngay_ct
        out["report_covers_full_program"] = so_ngay_phu >= so_ngay_ct
        if 0 < so_ngay_phu < so_ngay_ct:
            out["period_coverage_note"] = (
                "Ky bao cao chi phu %d/%d ngay cua chuong trinh (%s den %s). Cac so o day la PHAN "
                "TRONG KY, khong phai ket qua ca chuong trinh." % (
                    so_ngay_phu, so_ngay_ct, out["program_from"], out["program_to"]))
    return out


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
            "missing_source": "DMS_DonHangCTKM -> DMS_CTKM -> DMS_DonHangHdr",
            "note": "Khong xac dinh duoc moc du lieu don hang gan chuong trinh khuyen mai.",
            "answer_rule": (
                "Khong ket luan khong co chuong trinh; khong dung cot CTKM ghi chu tu do thay the. "
                "Can khoi phuc/nap bu chuoi lien ket CTKM tu DMS."),
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
            "missing_source": "Du lieu lien ket DMS_DonHangCTKM sau moc coverage",
            "warning": (
                f"Bang lien ket don hang-chuong trinh chi co du lieu den {coverage_date}, "
                f"khong phu ky {report_from} den {report_to}. Day la lo hong dong bo, KHONG phai "
                "bang chung ky do khong co chuong trinh. Khong dung cot CTKM tren hoa don de thay "
                "the vi cot do la ghi chu tu do."
            ),
            "answer_rule": (
                "Neu tra loi nguoi dung, phai neu dung moc coverage va ky bi thieu; khong noi chung "
                "chung 'khong co du lieu' va khong suy dien khach/don/doanh thu CTKM."),
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
    thong_tin_doi = {}
    if scope_employee_code:
        dms_ids = _get_team_dms_ids(scope_employee_code, str(report_to), thong_tin_doi)
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
        SELECT
               p.Id AS ProgramId, p.Code AS ProgramCode, p.Name AS ProgramName,
               COUNT_BIG(*) AS Orders,
               COUNT(DISTINCT po.CustomerCode) AS Customers,
               SUM(ISNULL(i.Revenue, 0)) AS AssociatedRevenue,
               SUM(CASE WHEN i.OrderId IS NULL THEN 1 ELSE 0 END) AS OrdersWithoutInvoice,
               SUM(ISNULL(i.PaidProductCount, 0)) AS PaidProductOccurrences,
               MAX(ISNULL(g.GiftProductCount, 0)) AS GiftProductCount,
               MAX(ISNULL(c.ConfiguredProductCount, 0)) AS ConfiguredProductCount,
               p.FromDate AS ProgramFrom, p.ToDate AS ProgramTo
        FROM ProgramOrders po
        INNER JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId
        LEFT HASH JOIN InvoiceByOrder i ON i.OrderId=po.OrderId
        LEFT JOIN GiftProducts g ON g.ProgId=po.ProgId
        LEFT JOIN ConfiguredProducts c ON c.ProgId=po.ProgId
        GROUP BY p.Id, p.Code, p.Name, p.FromDate, p.ToDate
        ORDER BY AssociatedRevenue DESC, p.Id
        OPTION (HASH JOIN)
    """, params)

    # DMS_CTKM.Code is truncated and is not a program key. Limiting SQL rows before
    # checking codes can leave one program in the top N while hiding a lower-revenue
    # program with the same code (Dec 2025: 4,251 versus 644 orders). Aggregate all
    # programs first; return the top N plus their same-code siblings from this period.
    top_codes = {row.get("ProgramCode") for row in rows[:limit] if row.get("ProgramCode")}
    rows = [row for rank, row in enumerate(rows) if rank < limit
            or row.get("ProgramCode") in top_codes]

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
            **_promotion_period_fields(row.get("ProgramFrom"), row.get("ProgramTo"),
                                       report_from, report_to),
        })

    # Cung MOT ten chuong trinh co the ung voi nhieu ma o cac ky khac nhau
    # (T9.2025_BPNGAM_10_TQ, Q4.2025_..., Q1.2026_... deu ten "Bo phe Ngam mua 10 tang 01").
    # Neu chi doc ten thi ba dong nay nhin nhu mot chuong trinh duy nhat.
    _ten = {}
    for prog in programs:
        _ten.setdefault(prog["program_name"], []).append(prog["program_code"])
    for prog in programs:
        trung = _ten.get(prog["program_name"], [])
        prog["same_name_program_codes"] = sorted(trung) if len(trung) > 1 else []
        prog["name_is_ambiguous"] = len(trung) > 1

    # 22/09/2026 (doi chieu M35 ky 12/2025): chieu NGUOC LAI cung xay ra - MOT ma ung voi NHIEU
    # chuong trinh. DMS_CTKM.Code bi cat ngan nen hai chuong trinh khac nhau ve chung mot ma:
    # 'Q4.2025_NHOM_BOPHE_SIRO_' co hai dong 4.251 don va 644 don, khac ten, khac ProgId. Tool gom
    # theo ProgId nen van ra hai dong dung, nhung hai dong do hien ra CUNG MOT MA - nhin nhu bang bi
    # lap, va cong lai thi thanh mot chuong trinh khong co that.
    _ma = {}
    for prog in programs:
        _ma.setdefault(prog["program_code"], []).append(prog)
    for prog in programs:
        trung_ma = _ma.get(prog["program_code"], [])
        prog["code_is_ambiguous"] = len(trung_ma) > 1
        prog["same_code_programs"] = sorted(
            ({"program_id": other["program_id"], "program_name": other["program_name"]}
             for other in trung_ma if other["program_id"] != prog["program_id"]),
            key=lambda item: str(item["program_id"])) if len(trung_ma) > 1 else []

    # These rows remain visible when the general model payload compacts the ranked
    # programs list. A warning about a shared code is not enough unless both actual
    # ProgramIds and their separate numbers reach the model.
    same_code_programs_to_distinguish = [
        {key: prog[key] for key in (
            "program_id", "program_code", "program_name", "orders",
            "invoiced_orders", "associated_revenue")}
        for prog in programs if prog["code_is_ambiguous"]
    ]

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
        # 22/09/2026 (doi chieu M35 ky 12/2025): bang tra loi chi co so cua MIEN BAC ma khong cau nao
        # noi ra, nen nguoi doi chieu lay so toan quoc ra so va tuong chatbot sai doanh thu. Do that
        # tren Bravo: Q4.2025_SIRO_10_RV.KENH. toan quoc 1.056 don / 30,05 ty, rieng MB 857 don /
        # 23,83 ty - dung y con so chatbot da tra.
        "scope_area_code": scope_area_code,
        "scope_note": (
            f"Tat ca so trong bao cao nay CHI tinh don cua khach thuoc mien {scope_area_code}, "
            "khong phai toan quoc." if scope_area_code else None),
        # 23/09/2026 (V34): ky mac dinh cua tool nay luon lui ve qua khu (thang day du gan nhat truoc
        # moc phu CTKM), nen doi duoc chot o mot ngay CACH XA hom nay. Do tren du lieu that, chot
        # nham moc lam lech 14->11 khach va 784,90->775,68 tr ma nhin bang mat khong thay. Bay ra
        # payload thay vi chi _warn(), vi _warn() phu thuoc vao viec model co chiu noi lai hay khong.
        "team_roster_as_of": thong_tin_doi.get("moc_chot_doi"),
        "team_roster_source": thong_tin_doi.get("nguon_chot_doi"),
        "team_roster_note": (
            "Thanh phan doi dung de loc bao cao nay duoc chot tai %s - SAU ky bao cao (%s den %s). "
            "Ai roi doi hoac moi vao giua hai moc se lam lech so khach/so don/doanh thu. PHAI noi ro "
            "dieu nay khi trinh bay." % (thong_tin_doi.get("moc_chot_doi"), report_from, report_to)
            if thong_tin_doi.get("moc_sau_ky") else None),
        "warning": warning,
        "interpretation_note": (
            "associated_revenue la doanh thu cua don hang co gan chuong trinh. Mot don co the dung "
            "nhieu chuong trinh nen KHONG cong doanh thu cac dong voi nhau, va chua du co so ket luan "
            "ROI/uplift neu thieu chi phi chuong trinh va nhom doi chung."
        ),
        # 23/09/2026 (V34): checker dat ten cot la "DT gan voi don trong ky bao cao", chatbot tung
        # trinh bay thanh "DT gan voi don co CTKM". Cung mot dai luong (SUM(Amount9) cua vHoaDonTotal
        # noi theo TRY_CONVERT(int,DMSId)), khac moi cai ten - nhung nguoi cham UAT phai mat cong doi
        # chieu moi biet la khong lech. Chot mot ten de hai ben goi giong nhau.
        "associated_revenue_label": "DT gan voi don trong ky bao cao",
        "program_count_returned": len(programs),
        "same_code_programs_to_distinguish": same_code_programs_to_distinguish,
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


def salary_aso_detail(year_month: str = None, area_code: str = None, position_code: str = None,
                      only_failed: bool = False, limit: int = 300,
                      scope_area_code: str = None, scope_employee_code: str = None,
                      scope_role: str = None) -> dict:
    """Read ASO flags as stored in Bravo; NULL means unknown, not failed.

    Exact requested month, full-scope counts before truncation, team membership
    from that salary snapshot. A month-end row is not proof of payroll approval.
    """
    if scope_role not in {"c_level", "admin_ops", "qlv"}:
        return {"error": "Vai tro khong duoc xem luong/thuong ca nhan."}
    if scope_role == "qlv" and not scope_employee_code:
        return {"error": "QLV thieu scope nhan vien; khong mo rong pham vi."}
    area_code = scope_area_code or area_code
    position = str(position_code or "").strip().upper()
    if position in _IS_AC_POSITIONS:
        return {"not_applicable": True, "rows": [],
                "warning": "CS/TK dung is_ac/Active Customer, khong ap dung ASO."}
    params = {"today": dt.date.today().isoformat()}
    month_sql = ""
    if year_month:
        month = str(year_month).strip()
        if len(month) != 7:
            raise ValueError("year_month phai la YYYY-MM.")
        start = _parse_report_date(month + "-01", "year_month")
        params.update(month_from=str(start), month_to=str(_month_end(start) + dt.timedelta(days=1)))
        month_sql = " AND SaveDate>=:month_from AND SaveDate<:month_to"
    snapshots = _q_bravo(
        "SELECT MAX(SaveDate) snapshot_date FROM dbo.FACT_ThongKeTinhLuong "
        "WHERE SaveDate<DATEADD(day,1,CAST(:today AS date)) "
        "AND CAST(SaveDate AS date)=EOMONTH(SaveDate)" + month_sql, params)
    snapshot = snapshots[0].get("snapshot_date") if snapshots else None
    if not snapshot:
        return {"status": "source_gap", "requested_month": year_month, "rows": [],
                "warning": "Chua co snapshot cuoi thang duoc yeu cau; khong lay thang truoc thay the."}
    params = {"snapshot_date": snapshot}
    # 11/09/2026: CS/TK duoc lay ve roi tach o duoi, KHONG loc trong SQL. Loc trong SQL thi doi chi
    # gom CS/TK (Kenh MT = MN1, Cho si = MN4/MBKV12) chi con dong cua chinh ma quan ly khung va tool bao
    # "1 nguoi chua danh gia ASO" - dung ra la ca doi khong ap dung ASO.
    where = ["f.SaveDate=:snapshot_date"]
    if area_code:
        where.append("f.AreaCode=:area_code"); params["area_code"] = area_code
    if position:
        where.append("f.PositionCode=:position_code"); params["position_code"] = position
    if scope_employee_code:
        where.append("(f.EmployeeCode=:employee OR f.ManagerCode=:employee)")
        params["employee"] = scope_employee_code
    # One employee/snapshot row is the source grain. Counts remain full-scope even
    # when only_failed or limit removes displayed rows.
    raw = _q_bravo(f"""SELECT f.EmployeeCode, f.EmployeeName, f.PositionCode, f.AreaCode,
             f.IsCalASOBonus, f.PassCheckASOForASO, f.PassCheckSaleForASO, f.PassCheckASOBonus,
             f.ASOQuantity, f.ASOQuantityTarget, f.ASOPercent_R, f.ASOBonus, f.IsSuspend
        FROM dbo.FACT_ThongKeTinhLuong f WHERE {' AND '.join(where)}
        ORDER BY f.EmployeeCode""", params)
    cs_tk, khac = [], []
    for r in raw:
        la_cs_tk = str(r.get("PositionCode") or "").strip().upper() in _IS_AC_POSITIONS
        (cs_tk if la_cs_tk else khac).append(r)
    raw = khac
    codes = [r.get("EmployeeCode") for r in raw]
    if len(set(codes)) != len(codes):
        return {"error": "Trung nhan vien tai snapshot ASO; can doi chieu truoc khi cong thuong."}

    def flag(value):
        return None if value is None else bool(int(value))

    rows = []
    for r in raw:
        calculated = flag(r.get("IsCalASOBonus"))
        quantity = flag(r.get("PassCheckASOForASO"))
        sale = flag(r.get("PassCheckSaleForASO"))
        final = flag(r.get("PassCheckASOBonus"))
        reasons = []
        if calculated is False:
            reasons.append("not_calculated_in_source")
        elif calculated is None or final is None:
            reasons.append("missing_condition_flags")
        elif final is False:
            if quantity is False:
                reasons.append("customer_quantity_condition_failed")
            if sale is False:
                reasons.append("sale_condition_failed")
            if not reasons:
                reasons.append("final_failed_reason_requires_DNH_confirmation")
        ratio = r.get("ASOPercent_R")
        rows.append({"employee_code": r.get("EmployeeCode"), "employee_name": r.get("EmployeeName"),
                     "position_code": r.get("PositionCode"), "area_code": r.get("AreaCode"),
                     "is_calculated": calculated, "pass_customer_quantity_condition": quantity,
                     "pass_sale_condition": sale, "passed_final": final,
                     "fail_reasons": reasons,
                     "aso_quantity": _f(r.get("ASOQuantity")) if r.get("ASOQuantity") is not None else None,
                     "aso_quantity_target": _f(r.get("ASOQuantityTarget")) if r.get("ASOQuantityTarget") is not None else None,
                     "aso_ratio_raw": _f(ratio) if ratio is not None else None,
                     "aso_percent": _f(ratio) * 100 if ratio is not None else None,
                     "aso_bonus": _f(r.get("ASOBonus")) if r.get("ASOBonus") is not None else None,
                     "is_suspend": flag(r.get("IsSuspend"))})
    cs_tk_rows = [{"employee_code": r.get("EmployeeCode"), "employee_name": r.get("EmployeeName"),
                   "position_code": r.get("PositionCode")} for r in cs_tk]
    # Doi chi gom CS/TK: phan con lai chi la chinh ma quan ly (ma khung nhu MN1/MN4) va ma do khong
    # duoc tinh ASO -> ca doi khong ap dung, khong bao la "chua danh gia". Quan ly co ASO that thi giu.
    if scope_employee_code and cs_tk and all(
            r["employee_code"] == scope_employee_code and r["is_calculated"] is not True for r in rows):
        return {"snapshot_date": str(snapshot), "requested_month": year_month,
                "not_applicable": True, "rows": [],
                "cs_tk_count": len(cs_tk_rows), "cs_tk_employees": cs_tk_rows,
                "warning": "Doi nay chi gom CS/TK: thuong tinh theo khach hoat dong (is_ac), KHONG ap "
                           "dung ASO. Khong noi la chua danh gia hay khong dat ASO."}
    assessed = [r for r in rows if r["is_calculated"] is True and r["passed_final"] is not None]
    failed = [r for r in assessed if r["passed_final"] is False]
    selected = failed if only_failed else rows
    limit = max(1, min(int(limit or 300), 500))
    return {"snapshot_date": str(snapshot), "requested_month": year_month,
            "snapshot_basis": "MONTH_END_ROW_NOT_APPROVAL_STATUS", "area_code": area_code,
            "total_employees": len(rows), "total_calculated": sum(r["is_calculated"] is True for r in rows),
            "total_passed": len(assessed) - len(failed), "total_failed": len(failed),
            "unassessed_count": len(rows) - len(assessed), "selected_total": len(selected),
            "rows": selected[:limit], "rows_truncated": len(selected) > limit,
            "cs_tk_excluded_count": len(cs_tk_rows),
            "definition": "Co ASO doc truc tiep tu Bravo; NULL/khong tinh khong dong nghia khong dat. "
                          "Khong suy nguyen nhan ngoai cac co, khong de nghi bu thuong. "
                          "Snapshot cuoi thang khong chung minh da duyet chi tra."}


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


def salary_achievement_summary(save_date: str = None, month_from: str = None, month_to: str = None,
                               scope_area_code: str = None, scope_employee_code: str = None,
                               scope_role: str = None) -> dict:
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
    result = {
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
    # C48 UAT 07/09: dung chung tool luong da co thay vi mo them tool moi (bo 40 phep doi chieu
    # phai bao phu toan bo tool dang ky). Neu user chi dinh snapshot thi giu dung mot ky; neu khong
    # chi dinh ky, helper tra 12 thang da chot de cau hoi "theo thang" khong bi rut thanh 1 diem.
    cost_from = month_from or (str(fdate)[:7] if save_date else None)
    cost_to = month_to or (str(fdate)[:7] if save_date else None)
    result["cost_summary"] = _salary_cost_summary(
        month_from=cost_from, month_to=cost_to,
        scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
        scope_role=scope_role,
    )
    return result


def _salary_cost_summary(month_from: str = None, month_to: str = None,
                         scope_area_code: str = None, scope_employee_code: str = None,
                         scope_role: str = None) -> dict:
    """Chi phi thuong kinh doanh/doanh thu theo thang, khong nhan doi doanh thu cap quan ly.

    Mau so doanh thu CHI gom TDV/CTV/CS/TK. Doanh thu cua QLV/TP la rollup cua doi; cong no vao
    mau so se nhan doi va lam ty le thuong/doanh thu sai. Tu so van gom thuong cua ca doi ngu
    (DM + V15 + V22 + V25 + ASO hop le); ASO cua CS/TK bi loai theo quy tac 27/08/2026.
    Loi nhuan va quan he nhan qua voi tang truong khong co trong kho, nen tool chi tra ve None thay
    vi suy dien "hieu qua" tu ty le chi phi.
    """
    def _month(value: str, field: str) -> str:
        raw = str(value or "").strip()[:7]
        try:
            dt.date.fromisoformat(raw + "-01")
        except ValueError as exc:
            raise ValueError(f"{field} phai theo dinh dang YYYY-MM.") from exc
        return raw

    if scope_employee_code:
        emp_sql = " AND (f.employee_code=? OR f.manager_code=?)"
        emp_params = (scope_employee_code, scope_employee_code)
    else:
        emp_sql, emp_params = "", ()
    area_sql = " AND f.area_code=?" if scope_area_code else ""
    area_params = (scope_area_code,) if scope_area_code else ()
    scope_sql, scope_params = emp_sql + area_sql, emp_params + area_params

    if month_to:
        to_month = _month(month_to, "month_to")
    else:
        latest = _q(
            "SELECT MAX(substr(f.save_date,1,7)) month FROM fact_thongketinhluong f "
            "WHERE f.save_date=date(f.save_date,'start of month','+1 month','-1 day') "
            f"{scope_sql} AND f.v25_percent IS NOT NULL",
            scope_params,
        )
        if not latest or not latest[0]["month"]:
            latest = _q(
                "SELECT MAX(substr(f.save_date,1,7)) month FROM fact_thongketinhluong f "
                "WHERE f.save_date=date(f.save_date,'start of month','+1 month','-1 day') "
                f"{scope_sql}", scope_params,
            )
        to_month = latest[0]["month"] if latest and latest[0]["month"] else None
    if not to_month:
        return {"error": "Chua co snapshot thuong/luong CUOI KY da chot trong pham vi cua ban."}

    # Chi ro mot thang thi tra dung mot thang; khong chi ro ky thi tra 12 ky da chot gan nhat de
    # nguoi dung co the xem xu huong, nhung khong goi day la tuong quan/nhan qua.
    from_month = _month(month_from, "month_from") if month_from else (
        to_month if month_to else _month_add(to_month, -11)
    )
    if from_month > to_month:
        return {"error": "month_from khong duoc sau month_to."}

    bonus_expr = (
        "COALESCE(f.dm_bonus,0)+COALESCE(f.v15_bonus,0)+COALESCE(f.v22_bonus,0)+"
        "COALESCE(f.v25_bonus,0)+CASE WHEN UPPER(COALESCE(f.position_code,'')) IN ('CS','TK') "
        "THEN 0 ELSE COALESCE(f.aso_bonus,0) END"
    )
    tier_predicate = "UPPER(COALESCE(f.position_code,'')) IN ('TDV','CTV','CS','TK')"
    sql = f"""
        WITH latest_employee_snapshot AS (
            SELECT f.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY f.employee_code, substr(f.save_date,1,7)
                       ORDER BY CASE WHEN f.v25_percent IS NOT NULL THEN 1 ELSE 0 END DESC,
                                f.save_date DESC
                   ) AS snapshot_rank
            FROM fact_thongketinhluong f
            WHERE f.save_date=date(f.save_date,'start of month','+1 month','-1 day')
              AND substr(f.save_date,1,7) BETWEEN ? AND ? {scope_sql}
        )
        SELECT substr(f.save_date,1,7) month,
               COUNT(*) total_employees,
               SUM({bonus_expr}) total_bonus,
               SUM(CASE WHEN {tier_predicate} THEN {bonus_expr} ELSE 0 END) employee_tier_bonus,
               SUM(CASE WHEN NOT ({tier_predicate}) THEN {bonus_expr} ELSE 0 END) management_bonus,
               SUM(CASE WHEN {tier_predicate} THEN COALESCE(f.month_sale_amount,0) ELSE 0 END) employee_tier_sales
        FROM latest_employee_snapshot f
        WHERE snapshot_rank=1
        GROUP BY substr(f.save_date,1,7)
        ORDER BY month
    """
    rows = _q(sql, (from_month, to_month) + scope_params)
    if not rows:
        return {"error": "Khong co snapshot luong da chot trong khoang thang da chon."}

    months = []
    for row in rows:
        sales = _f(row["employee_tier_sales"])
        total_bonus = _f(row["total_bonus"])
        months.append({
            "month": row["month"],
            "total_employees": int(row["total_employees"] or 0),
            "total_bonus": total_bonus,
            "employee_tier_bonus": _f(row["employee_tier_bonus"]),
            "management_bonus": _f(row["management_bonus"]),
            "employee_tier_sales": sales,
            "bonus_to_sales_pct": round(total_bonus / sales * 100, 3) if sales else None,
            "profit_data_available": False,
        })
    return {
        "period": {"from_month": from_month, "to_month": to_month},
        "months": months,
        "formula": {
            "numerator": "DM + V15 + V22 + V25 + ASO (ASO loai CS/TK)",
            "denominator": "Doanh thu TDV/CTV/CS/TK; khong cong doanh thu rollup cua cap quan ly",
        },
        "limitations": (
            "Kho khong co loi nhuan/gross margin va khong du co so de ket luan co che thuong gay ra "
            "tang truong ben vung. Chi duoc bao cao ty le chi phi thuong/doanh thu va xu huong quan sat."
        ),
        "snapshot_status": "closed_period",
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
    # Quy TEN ve MA ngay tu dau (16/09/2026): phai lam TRUOC phan kiem tra quan he quan ly ben duoi,
    # vi doi chieu manager_code bang mot chuoi ten se khong khop va bi tu choi nham thanh "khong co
    # quyen" thay vi "chua xac dinh duoc nguoi".
    if employee_code:
        ident_ten = _resolve_employee_identity(employee_code)
        if ident_ten.get("name_candidates"):
            return _ung_vien_ten_nhan_vien_loi(ident_ten, employee_code)
        if ident_ten.get("resolved_from_name"):
            employee_code = ident_ten["code"]
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
    "get_revenue_seasonality": revenue_seasonality,
    "get_customer_lifecycle_summary": customer_lifecycle_summary,
    "get_customers_silent": customers_silent,
    "get_new_customer_list": new_customer_list,
    "get_reorder_pending_customers": reorder_pending_customers,
    "get_focus_product_kpi": focus_product_kpi,
    "get_customer_attrition_risk": customer_attrition_risk,
    "get_customer_cohort_retention": customer_cohort_retention,
    "get_customer_movement": customer_movement,
    "get_kpi_gap_run_rate": kpi_gap_run_rate,
    "get_cross_sell_opportunities": cross_sell_opportunities,
    "get_customer_product_coverage": customer_product_coverage,
    "get_geography_monthly_performance": geography_monthly_performance,
    "get_workforce_productivity": workforce_productivity,
    "get_operational_data_quality": operational_data_quality,
    "get_etc_contract_status": etc_contract_status,
    "get_etc_revenue_by_item_type": etc_revenue_by_item_type,
    "get_employee_kpi": employee_kpi,
    "get_employee_daily_kpi": employee_daily_kpi,
    "compare_periods": compare_periods,
    "get_customer_detail": customer_detail,
    "get_employee_directory": employee_directory,
    "check_order_timing": order_timing_check,
    "get_inventory_by_region": inventory_by_region,
    "get_inventory_expiry_report": inventory_expiry_report,
    "get_inventory_item_stock": inventory_item_stock,
    "get_sku_revenue_drop_vs_stock": sku_revenue_drop_vs_stock,
    "get_qlv_change_history": qlv_change_history,
    "get_revenue_tree": revenue_tree,
    "get_kpi_ranking": kpi_ranking,
    "get_revenue_reconciliation": revenue_reconciliation_check,
    "get_revenue_view_reconciliation": revenue_view_reconciliation,
    "get_receivables_overview": receivables_overview,
    "get_receivables_period_compare": receivables_period_compare,
    "get_receivables_history_dates": receivables_history_dates,
    "get_customer_revenue_debt_risk": customer_revenue_debt_risk,
    "get_audit_log": audit_log_summary,
    "get_promotion_effectiveness": promotion_effectiveness,
    "get_promotion_data_quality": promotion_data_quality,
    "get_salary_bonus_policy": salary_bonus_policy,
    "get_salary_aso_detail": salary_aso_detail,
    "get_salary_data_quality": salary_data_quality,
    "get_salary_detail": salary_detail,
    "get_salary_achievement_summary": salary_achievement_summary,
    "get_salary_ranking": salary_ranking,
}

_SELF_SCOPED_TEMPLATES = {"get_audit_log"}

_ROLE_SCOPED_TEMPLATES = {
    "get_salary_aso_detail", "get_revenue_view_reconciliation",
    "get_salary_detail", "get_salary_achievement_summary", "get_salary_ranking",
    "get_salary_bonus_policy", "get_salary_data_quality",
}

_AREA_EXEMPT_TEMPLATES = {
    "get_audit_log", "get_salary_detail", "get_salary_achievement_summary", "get_salary_ranking",
    "get_salary_bonus_policy", "get_salary_data_quality",
    # 17/09/2026: get_receivables_history_dates DA BO khoi day. Tu ban nay no tra SO LIEU cong no
    # tung moc (khong con chi la danh sach ngay) nen BAT BUOC chiu gioi han vung nhu moi bao cao
    # cong no khac - ham da nhan scope_area_code/scope_channel/scope_employee_code.
}

_PERSON_LEVEL_TEMPLATES = {
    "get_receivables_overview",
    # 17/09/2026: hai tool lich su cong no tra danh sach khach (top no qua han) nen phai chiu
    # gioi han theo doi y het receivables_overview - truoc do KHONG co o day nen chot fail-closed
    # cua call_template khong kich hoat voi tai khoan QLV.
    "get_receivables_period_compare", "get_receivables_history_dates",
    # Ton kho theo vung, nhung nhu cau va danh sach khach mua phai gioi han theo doi.
    "get_inventory_expiry_report",
    "get_sku_revenue_drop_vs_stock", "get_revenue_view_reconciliation",
    "get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
    "get_employee_daily_kpi", "check_order_timing",
    "get_revenue_by_channel", "get_revenue_by_region", "get_top_customers",
    "get_top_products", "compare_periods", "get_revenue_ytd_cumulative", "get_revenue_monthly_series",
    "get_revenue_seasonality",
    "get_customer_lifecycle_summary", "get_customers_silent", "get_customer_attrition_risk",
    "get_customer_cohort_retention", "get_customer_movement", "get_kpi_gap_run_rate",
    "get_cross_sell_opportunities", "get_customer_product_coverage", "get_geography_monthly_performance",
    "get_workforce_productivity", "get_operational_data_quality",
    "get_promotion_effectiveness",
    "get_promotion_data_quality",
    "get_customer_revenue_debt_risk",
    # 15/09/2026: doanh so ETC theo nhom hang chua co loc theo doi QLV -> QLV bi chan fail-closed.
    "get_etc_revenue_by_item_type",
    # 15/09/2026: danh sach khach moi/chua tai don va KPI trong tam - loc theo doi QLV.
    "get_new_customer_list", "get_reorder_pending_customers", "get_focus_product_kpi",
    # 19/08: inventory_by_region/qlv_change_history/revenue_reconciliation chi loc vung.
    # 15/09 V40: receivables_overview da ho tro loc khach theo doi, dang ky o CA HAI tap
    # de backend ep pham vi QLV ma khong chan nham tool nhu truoc day.
    # 19/08/2026: THEM get_salary_ranking - truoc do CHI 3 tool luong kia o day, ham nay dung
    # chung _ROLE_SCOPED_TEMPLATES/_AREA_EXEMPT_TEMPLATES voi 3 tool do (deu bo qua scope_area_code
    # de nhuong cho co che theo doi tinh hon), nhung thieu mat o day khien nhanh ep
    # scope_employee_code (hoac fail-closed neu chua ho tro) KHONG BAO GIO duoc kich hoat - QLV goi
    # duoc ham nay VA thay xep hang thuong ca nhan CUA CA CONG TY, khong bi chan o dau ca. Xem sua
    # cung dot: salary_ranking() them tham so scope_employee_code + loc that tren manager_code.
    "get_salary_detail", "get_salary_achievement_summary", "get_salary_bonus_policy",
    "get_salary_data_quality", "get_salary_aso_detail",
    "get_salary_ranking",
}

_EMPLOYEE_SCOPED_TEMPLATES = {
    "get_receivables_overview",
    # 17/09/2026: ca hai tool lich su cong no da ho tro loc khach theo doi (cung nguon phan cong
    # KPI voi receivables_overview) nen dang ky o CA HAI tap - QLV van dung duoc, chi bi ep dung
    # pham vi doi minh thay vi bi tu choi thang.
    "get_receivables_period_compare", "get_receivables_history_dates",
    "get_inventory_expiry_report",
    "get_sku_revenue_drop_vs_stock",
    "get_revenue_tree", "get_kpi_ranking", "get_employee_kpi",
    "get_employee_daily_kpi", "get_revenue_by_channel", "get_top_customers",
    "get_top_products", "get_revenue_by_region", "compare_periods", "get_revenue_ytd_cumulative",
    "get_revenue_monthly_series", "get_revenue_seasonality", "get_customer_lifecycle_summary", "get_customers_silent",
    "get_customer_attrition_risk",
    "get_customer_cohort_retention", "get_customer_movement", "get_kpi_gap_run_rate",
    "get_cross_sell_opportunities", "get_customer_product_coverage", "get_geography_monthly_performance",
    "get_workforce_productivity", "get_operational_data_quality",
    "get_promotion_effectiveness",
    "get_promotion_data_quality",
    "get_customer_revenue_debt_risk",
    "get_new_customer_list", "get_reorder_pending_customers", "get_focus_product_kpi",
    "get_salary_detail", "get_salary_achievement_summary", "get_salary_bonus_policy",
    "get_salary_data_quality", "get_salary_aso_detail",
    "get_salary_ranking",
    # check_order_timing can scope_employee_code de hang tra/phan bo gia tri don cua QLV chi gom doi minh.
    "check_order_timing",
}

_CHANNEL_SCOPE_POLICIES = {
    # Tool co tham so scope_channel va bat buoc duoc backend ghi de.
    **{name: "filter" for name in {
        "get_revenue_by_channel", "get_top_products", "get_top_customers",
        "compare_periods", "get_revenue_ytd_cumulative", "get_revenue_monthly_series",
        "get_revenue_seasonality",
        "get_customer_lifecycle_summary", "get_customers_silent", "get_customer_attrition_risk",
        "get_customer_cohort_retention",
        "get_customer_movement", "get_kpi_gap_run_rate", "get_cross_sell_opportunities",
        "get_customer_product_coverage", "get_geography_monthly_performance",
        "get_workforce_productivity", "get_operational_data_quality", "get_customer_detail",
        "check_order_timing", "get_revenue_by_region", "get_promotion_effectiveness",
        "get_promotion_data_quality", "get_customer_revenue_debt_risk",
        "get_receivables_overview", "get_receivables_period_compare", "get_employee_daily_kpi",
        "get_receivables_history_dates",
        "get_sku_revenue_drop_vs_stock",
        # 15/09/2026: tu tra not_applicable voi kenh ETC (nguon KPI khach chi phu OTC).
        "get_new_customer_list", "get_reorder_pending_customers",
    }},
    # Cac tool nay hien chi co nguon OTC. Tai khoan OTC duoc dung; ETC bi chan de tranh tra sai kenh.
    **{name: "otc_only" for name in {
        "get_employee_kpi", "get_revenue_tree", "get_kpi_ranking", "get_revenue_reconciliation",
        # 15/09/2026: KPI san pham trong tam tu ket qua tinh luong OTC.
        "get_focus_product_kpi",
        # 15/09/2026: bao cao lo/han dung kem nhu cau ban va khach mua OTC gan day - mo cho tai khoan
        # OTC; tai khoan ETC dung get_inventory_by_region/get_inventory_item_stock (khong lo khach OTC).
        "get_inventory_expiry_report",
    }},
    # Nguoc lai: hop dong/goi thau chi co o kenh ETC (vHopDongETC). Tai khoan gioi han kenh OTC bi chan.
    **{name: "etc_only" for name in {
        "get_etc_contract_status",
        # 15/09/2026: nhom hang ItemTypeETC chi co tren hoa don ETC.
        "get_etc_revenue_by_item_type",
    }},
    # Du lieu luong chi duoc mo cho tai khoan QLV da co scope nhan vien; regional channel-only bi chan.
    **{name: "employee" for name in {
        "get_salary_bonus_policy", "get_salary_data_quality", "get_salary_detail",
        "get_salary_achievement_summary", "get_salary_ranking", "get_salary_aso_detail",
    }},
    # Chua co cot/quan he kenh du tin cay: fail-closed thay vi mac dinh xem toan cong ty.
    **{name: "blocked" for name in {
        "get_employee_directory",
        "get_qlv_change_history",
        # Luon tra ca OTC+ETC gop trong 1 payload, khong co scope_channel de loc rieng kenh -
        # tai khoan bi gioi han 1 kenh se thay ca so kenh khac neu khong chan.
        "get_revenue_view_reconciliation",
    }},
    # Metadata khong chua so lieu kinh doanh theo kenh, hoac da tu gioi han theo chinh nguoi dung.

    "get_audit_log": "exempt",
    # 15/09/2026 (UAT 14:40, anh Dang chot): ton kho khong phai so lieu theo kenh - tai khoan gioi han
    # kenh xem duoc ton kho; gioi han vung van ep qua scope_area_code.
    "get_inventory_by_region": "exempt",
    "get_inventory_item_stock": "exempt",
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
    if policy == "etc_only":
        return channel == "ETC"
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
    user_warning_token = _tool_user_warnings.set([])
    try:
        fn = TEMPLATES[name]
        call_args = dict(args)
        if name == "get_employee_kpi":
            # Nguon nhan su la lua chon noi bo, khong nhan tu tham so model. M20 cua giam doc mien
            # doi chieu TDV theo S33; khong mo bat ky truong luong/thuong ca nhan nao.
            call_args.pop("kpi_source", None)
            m20_question = _fold_question(question)
            if (scope_role == "regional_director"
                    and "thuong" in m20_question and "kpi" in m20_question
                    and "doi" in m20_question and "chinh sach" in m20_question):
                if not scope_area_code:
                    return {"ok": False, "error": "Tai khoan giam doc mien thieu pham vi mien de doi chieu KPI."}
                call_args["position_code"] = "TDV"
                call_args["kpi_source"] = "salary_kpi"
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
        q_folded = _fold_question(question)
        if name == "get_receivables_overview":
            # V37: model khong duoc tu bat/tat phan thu tien qua args.
            call_args["include_collection"] = "thu tien" in q_folded or "cam ket thu" in q_folded
            call_args.pop("collection_as_of_date", None)
        if name == "get_new_customer_list" and _is_new_customer_quality_question(question):
            call_args["mode"] = "quality"
        if name == "get_customer_movement" and (
                "bu" in q_folded and "ngung mua" in q_folded
                and any(marker in q_folded for marker in ("khach moi", "tai kich hoat"))):
            # C31/S90: query doi chieu dung #sales cua so 24 thang, nen "moi" la lan dau QUAN SAT
            # trong cua so. Khong ap dung cho V15/V23, vi hai cau do can truy ca lich su de phan biet
            # lan mua dau that voi khach quay lai sau nhieu nam.
            call_args["classification_basis"] = "observed_window_24m"
        concentration_question = (
            name == "get_top_customers"
            and any(marker in q_folded for marker in ("phu thuoc top", "muc do tap trung"))
            and "top 10" in q_folded
        )
        monthly_customer_change_question = (
            name == "get_top_customers"
            and any(marker in q_folded for marker in ("tung thang", "theo thang"))
            and any(marker in q_folded for marker in ("tang/giam manh", "tang giam manh"))
        )
        if concentration_question or monthly_customer_change_question:
            end_day = str(call_args.get("date_to") or latest_data_date())[:10]
            end_month = end_day[:7]
            requested_from = str(call_args.get("date_from") or "")[:10]
            if not requested_from or requested_from[:7] == end_month:
                call_args["date_from"] = f"{_month_add(end_month, -5)}-01"
            call_args["date_to"] = end_day
            call_args["limit"] = 10
        monthly_financial_question = (
            name == "check_order_timing"
            and (
                ("doanh thu gop" in q_folded and "doanh thu thuan" in q_folded)
                or ("ty le hang tra" in q_folded and "theo thang" in q_folded)
                or ("ty le tra hang" in q_folded and "chiet khau" in q_folded)
            )
        )
        if monthly_financial_question:
            end_day = str(call_args.get("date_to") or latest_data_date())[:10]
            end_month = end_day[:7]
            requested_from = str(call_args.get("date_from") or "")[:10]
            if not requested_from or requested_from[:7] == end_month:
                call_args["date_from"] = f"{_month_add(end_month, -5)}-01"
            call_args["date_to"] = end_day
            call_args["group_by_month"] = True
        if name == "get_inventory_expiry_report":
            if any(marker in q_folded for marker in (
                "ton cao", "cham ban", "cham luan chuyen", "xu ly ton",
            )):
                call_args["focus"] = "overstock"
            elif any(marker in q_folded for marker in (
                "thieu hang", "kho thieu", "nguy co mat",
            )):
                call_args["focus"] = "shortage"
        if name == "get_workforce_productivity":
            if any(marker in q_folded for marker in (
                "vieng tham", "di tuyen", "phu tuyen",
                "ty le co don sau tham", "check-in", "check in",
            )):
                call_args["mode"] = "route_visits"
            elif "vung nao duoi 80" in q_folded and "lien tiep" in q_folded:
                call_args["mode"] = "productivity"
                call_args["group_by"] = "manager"
                call_args["month_to"] = _latest_complete_revenue_month()
                call_args["months_back"] = 6
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif ("tung qlv" in q_folded and any(marker in q_folded for marker in (
                        "target", "% hoan thanh", "suy giam",
                    ))) or "qlv nao co nhieu nhan vien duoi 80" in q_folded:
                call_args["mode"] = "productivity"
                call_args["group_by"] = "manager"
                call_args["months_back"] = 6
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif "tung tdv" in q_folded and any(marker in q_folded for marker in (
                "theo thang", "xu huong", "xep hang",
            )):
                call_args["mode"] = "productivity"
                call_args["group_by"] = "employee"
                call_args["months_back"] = 6
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            if any(marker in q_folded for marker in (
                "nhan vien giam doanh so lien tiep", "nv giam doanh so lien tiep",
                "ai giam doanh so lien tiep",
            )):
                call_args["group_by"] = "employee"
                # 11/09/2026: 6 thang. "Giam lien tiep 3 thang" = 3 lan giam, can 4 thang tron lien
                # nhau; thang dang chay bi loai va thang dau cua so khong co thang truoc de so, nen
                # 4 thang chi do toi da duoc 2 lan giam.
                call_args["months_back"] = max(6, int(call_args.get("months_back") or 6))
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
        if name == "get_customer_product_coverage":
            # Cac cau nay dung chung mot tool nhung can mode khac nhau. Ep theo intent ke ca khi
            # model da truyen mot mode khac: dung tool ma sai mode van cho mot cau tra loi rat
            # thuyet phuc nhung sai trong tam (loi lap lai tai M/V UAT ngay 07-09/09).
            if "mua dong thoi otc va etc" in q_folded or "mua cheo kenh" in q_folded:
                call_args["mode"] = "dual_channel"
                call_args["lookback_months"] = 6
                call_args["limit"] = max(100, int(call_args.get("limit") or 100))
            elif "ba rui ro lon nhat" in q_folded and "ke hoach" in q_folded:
                call_args["mode"] = "priority"
                call_args["limit"] = max(20, int(call_args.get("limit") or 20))
            elif "danh sach khach" in q_folded and any(marker in q_folded for marker in (
                "giu khach", "tai kich hoat", "thu no", "ban cheo",
            )):
                call_args["mode"] = "four_customer_priorities"
                call_args["limit"] = max(20, int(call_args.get("limit") or 20))
            elif any(marker in q_folded for marker in (
                "top/bottom san pham", "top bottom san pham", "top va bottom san pham",
            )) and any(marker in q_folded for marker in ("tung thang", "theo thang")):
                call_args["mode"] = "product_monthly"
                call_args["lookback_months"] = 3
            elif ("sku" in q_folded or "san pham" in q_folded) \
                    and "dong gop" in q_folded \
                    and any(marker in q_folded for marker in ("tung thang", "theo thang")):
                call_args["mode"] = "product_monthly"
                call_args["lookback_months"] = 3
            elif "sku" in q_folded and any(marker in q_folded for marker in (
                "% target", "phan tram target", "khoang thieu",
            )):
                call_args["mode"] = "sku_target"
            elif "nhieu khach mua" in q_folded and "it khach" in q_folded \
                    and any(marker in q_folded for marker in ("luong/don", "aov")):
                call_args["mode"] = "product_mix"
            elif "nhieu khach phu trach" in q_folded and "ty le khach mua" in q_folded:
                call_args["mode"] = "employee_assignment"
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif any(marker in q_folded for marker in (
                "san pham moi", "sp moi",
            )) and any(marker in q_folded for marker in (
                "do phu", "sau 1", "sau 3", "sau 6", "sau 12", "ra mat",
            )):
                call_args["mode"] = "product_first_observed"
                call_args["lookback_months"] = 24
            elif any(marker in q_folded for marker in (
                "loai anh huong", "loai tru anh huong",
            )) and any(marker in q_folded for marker in (
                "chuyen nhan vien", "chuyen khach", "thay doi dia ban", "chuyen vung",
            )):
                call_args["mode"] = "assignment_change"
            elif "cung tinh" in q_folded and any(marker in q_folded for marker in (
                "khach tuong dong", "mua it hon",
            )):
                call_args["mode"] = "customer_peer"
                call_args["lookback_months"] = 3
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif any(marker in q_folded for marker in (
                "khach tuong dong", "nhom khach tuong dong", "share-of-wallet noi bo",
                "share of wallet noi bo", "mua it sku hon",
            )):
                call_args["mode"] = "customer_revenue_tier_peer"
                call_args["lookback_months"] = 3
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif "khach nao" in q_folded and "3 thang" in q_folded and any(
                marker in q_folded for marker in ("tan suat", "aov", "sku", "so sku")
            ):
                call_args["mode"] = "customer"
                call_args["lookback_months"] = 3
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif any(marker in q_folded for marker in (
                "sku nao doanh thu giam", "sku nao giam do", "giam luong/don",
                "xoi mon gia", "gia ban thuc te binh quan cua tung sku",
            )):
                call_args["mode"] = "product"
                call_args["lookback_months"] = 1
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif ("sku" in q_folded or "san pham" in q_folded) and any(
                marker in q_folded for marker in (
                    "dong luc tang truong", "keo giam tang truong", "mat thi phan noi bo",
                    "do phu khach hang tang", "do phu co lai",
                )
            ):
                call_args["mode"] = "product"
                call_args["lookback_months"] = 3
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
            elif any(marker in q_folded for marker in (
                "hom nay", "tuan nay", "dong gap lon nhat",
            )) and any(marker in q_folded for marker in (
                "khach hang", "san pham", "nhan vien", "tdv",
            )):
                call_args["mode"] = "priority"
            elif "doi" in q_folded and all(marker in q_folded for marker in ("khach", "don")) \
                    and any(marker in q_folded for marker in ("aov", "tan suat")):
                call_args["mode"] = "employee"
                call_args["lookback_months"] = 1
                call_args["limit"] = max(200, int(call_args.get("limit") or 200))
        if name == "get_geography_monthly_performance":
            if "thang nay" in q_folded:
                # Khong cho model tu doi "thang nay" thanh thang tron truoc. Tool se danh dau MTD
                # va cam ket luan so sanh truc tiep voi thang tron.
                call_args["month_to"] = latest_data_date()[:7]
            if "3 thang gan nhat" in q_folded or "so voi 3 thang" in q_folded:
                call_args["months_back"] = 3
            if any(marker in q_folded for marker in ("tinh", "huyen", "dia ban con")):
                call_args["dimension"] = "city"
            elif "vung" in q_folded:
                call_args["dimension"] = "area"
        contract_etc_question = any(marker in q_folded for marker in (
            "hop dong etc", "hop dong/goi thau", "goi thau nao", "sap het hieu luc",
            "gia tri lon chua giai ngan", "ty le thuc hien thap",
        ))
        margin_question = any(marker in q_folded for marker in (
            "loi nhuan gop", "bien loi nhuan", "loi nhuan thap", "loi nhuan am",
        ))
        if name == "get_revenue_monthly_series" and margin_question:
            result = {
                "status": "SOURCE_GAP_NO_COGS_OR_GROSS_MARGIN",
                "requested": "Loi nhuan gop/bien loi nhuan va phan ra nguyen nhan",
                "verified_available": [
                    "Doanh thu thuan, san luong ban co gia va doanh thu rong tren don vi ban co gia.",
                ],
                "not_verifiable": [
                    "Gia von/COGS", "Loi nhuan gop", "Bien loi nhuan gop",
                    "San pham/khach hang loi nhuan thap hoac am",
                    "Nguyen nhan bien dong loi nhuan do gia von",
                ],
                "reason": (
                    "Kho chatbot chua co gia von/COGS theo hoa don-SKU. Doanh thu va gia ban "
                    "khong du de suy ra loi nhuan."
                ),
                "forbidden_inference": (
                    "Khong duoc goi doanh thu cao/thap, chiet khau, Amount9 hoac gia ban la loi nhuan."
                ),
                "required_source": (
                    "Gia von/COGS da chot theo hoa don x SKU, hoac bang loi nhuan gop chinh thuc cua DNH."
                ),
                "data_as_of": latest_data_date(),
            }
        elif name == "get_geography_monthly_performance" and contract_etc_question:
            # C44/M42: hoa don khong co contract_id da DNH xac nhan. Tra source-gap co
            # cau truc ngay tai tool de model khong the tu ghep customer+SKU roi tinh sai.
            result = {
                "status": "SOURCE_GAP_CONTRACT_INVOICE_LINK",
                "requested_scope": "ETC",
                "verified_available": [
                    "Metadata hop dong truc tiep trong nguon: so hop dong, khach hang, hieu luc, gia tri goc.",
                ],
                "not_verifiable": [
                    "Doanh thu thuc hien theo tung hop dong",
                    "Gia tri con lai/chua giai ngan va ty le thuc hien",
                    "Cong no qua han theo tung hop dong",
                ],
                "reason": ("Hoa don hien khong co khoa hop dong da DNH xac nhan. Ghep bang khach "
                           "hang + SKU co the gan nham hoac dem trung doanh thu."),
                "forbidden_inference": "Khong noi hoa don vao hop dong qua customer+SKU.",
                "data_quality_guard": ("Khong cong tong/xep hang gia tri hop dong bat thuong khi "
                                       "chua co quy tac chat luong duoc DNH chot."),
                "required_source": "contract_id hoac khoa lien ket don/hoa don-hop dong da DNH xac nhan.",
                "data_as_of": latest_data_date(),
            }
        else:
            result = fn(**call_args)
        if name == "get_top_customers" and isinstance(result, list):
            if concentration_question:
                result = {
                    "customers": result,
                    "concentration_by_month": _revenue_concentration_by_month(
                        call_args["date_from"], call_args["date_to"], call_args.get("channel", "ALL"),
                        scope_area_code, scope_channel, scope_employee_code,
                    ),
                }
            elif monthly_customer_change_question:
                result = {
                    "customers": result,
                    "monthly_customer_changes": _top_customer_changes_by_month(
                        call_args["date_from"], call_args["date_to"], 10,
                        scope_area_code, scope_channel, scope_employee_code,
                    ),
                }
        if name == "get_employee_kpi" and isinstance(result, dict):
            if "ty le nhan su dat" in q_folded and any(
                threshold in q_folded for threshold in ("65", "70", "80", "100", "120")
            ):
                result["monthly_threshold_summary"] = _kpi_thresholds_by_month(
                    call_args["as_of_date"], 6, "area_position",
                    scope_area_code, scope_employee_code,
                )
            elif "doi nao dat" in q_folded and any(
                marker in q_folded for marker in ("qua cong", "duoi cong", "xu huong 3 thang")
            ):
                result["monthly_team_threshold_summary"] = _kpi_thresholds_by_month(
                    call_args["as_of_date"], 3, "manager",
                    scope_area_code, scope_employee_code,
                )
        # Gan nhan pham vi NGAY TRONG payload cho model. Truoc day code da loc dung doi QLV nhung
        # payload chi con cac con so; model da goi 9,82 ty cua DOI thanh "toan vung MT" trong UAT.
        if isinstance(result, dict):
            result = dict(result)
            if name == "check_order_timing":
                q_lower = (question or "").lower()
                if "giao" in q_lower and ("chậm" in q_lower or "cham" in q_lower):
                    # DMS_DonHangHdr + vHoaDonTotal chi cho ngay don va ngay hoa don dau tien.
                    # Khong co ngay giao thuc te thi khong duoc doi ten phep do thanh "giao cham".
                    result["unavailable_checks"] = [
                        "Giao chậm: nguồn hiện chưa có mốc giao hàng thực tế; chỉ đối chiếu được "
                        "ngày đơn với ngày hóa đơn đầu tiên."
                    ]
            if scope_employee_code and name == "get_inventory_expiry_report":
                result["pham_vi_du_lieu"] = {
                    "loai": "TON_KHO_CHUNG_NHU_CAU_DOI",
                    "ma_qlv": scope_employee_code,
                    "ma_vung": result.get("area_code"),
                    "canh_bao": (
                        "Binh quan ban va khach mua gan day CHI cua doi QLV tren. "
                        "Ton kho la ton dung chung trong pham vi da loc, chua phan bo cho doi. "
                        "So thang du ban so sanh ton chung voi suc ban cua doi, khong phai suc ban ca vung."
                    ),
                }
            elif scope_employee_code and name in _EMPLOYEE_SCOPED_TEMPLATES:
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
        # 15/09/2026: ma san pham/nhan vien trong ket qua luon kem ten (yeu cau anh Dang).
        result = _gan_ten_cho_ma(result)
        entry["status"] = "ok"
        entry["duration_ms"] = int((dt.datetime.now() - t0).total_seconds() * 1000)
        _write_log(entry)
        payload = {"ok": True, "result": result}
        warnings = _tool_warnings.get() or []
        if warnings:
            payload["canh_bao"] = warnings
        user_warnings = _tool_user_warnings.get() or []
        if user_warnings:
            payload["user_warnings"] = user_warnings
        return payload
    except KhongXacDinhDuocDoi as e:
        # KHONG boc them "Loi khi chay bao cao chuan" - day khong phai su co ky thuat ma la
        # THIEU DU LIEU PHAN CONG DOI. Thong diep da viet san cho nguoi dung, giu nguyen van.
        entry["status"] = "no_team"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": str(e)}
    except TypeError as e:
        # 17/09/2026 (UAT that: cau C37 "Du no... month-by-month", model tu goi them
        # get_customer_detail() de "doi chieu cong no" nhung KHONG truyen tham so nao - truoc day
        # roi thang xuong nhanh Exception ben duoi, tra nguyen van loi Python cho nguoi dung:
        # "get_customer_detail() missing 3 required positional arguments: 'customer_code',
        # 'date_from', and 'date_to'" - lo ten tham so noi bo, doc nhu loi he thong hong thay vi
        # loi model goi thieu tham so. Cac tool nhu customer_detail/salary_detail KHONG the co gia
        # tri mac dinh hop ly cho ma khach/nhan vien (khac revenue_ytd_cumulative da sua rieng
        # 16/09/2026, noi thang thieu co the suy ve thang gan nhat) - o day dung cach xu ly chung:
        # nhan dien DUNG loai TypeError "thieu tham so bat buoc" (khong bat nham TypeError khac,
        # vd loi cong None+so ben trong ham), tra thong diep ro cho model biet PHAI hoi lai nguoi
        # dung de co doi tuong cu the, khong duoc tu doan hay bao loi he thong.
        msg = str(e)
        thieu_tham_so = re.search(r"missing \d+ required (positional |keyword-only )?argument", msg)
        if not thieu_tham_so:
            entry["status"] = "error"; entry["error"] = msg[:300]
            _write_log(entry)
            return {"ok": False, "error": f"Loi khi chay bao cao chuan '{name}': {msg[:300]}"}
        entry["status"] = "missing_args"; entry["error"] = msg[:300]
        _write_log(entry)
        return {"ok": False, "error": (
            f"Cong cu '{name}' can them thong tin de chay ({msg.split('missing', 1)[-1].strip()}). "
            "KHONG duoc tu suy dien hay bo qua phan nay - hoi lai nguoi dung de biet ro doi tuong cu "
            "the (vd ten/ma khach hang, ten/ma nhan vien) truoc khi goi lai cong cu nay."
        )}
    except Exception as e:
        entry["status"] = "error"; entry["error"] = str(e)[:300]
        _write_log(entry)
        return {"ok": False, "error": f"Loi khi chay bao cao chuan '{name}': {str(e)[:300]}"}
    finally:
        _tool_warnings.reset(token)
        _tool_user_warnings.reset(user_warning_token)
