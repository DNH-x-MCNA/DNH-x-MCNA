# -*- coding: utf-8 -*-
"""NL2SQL: dung Claude (tool use) de hieu cau hoi tieng Viet, tra loi tu nhien.

Kien truc HYBRID de tang do chinh xac cho cac bao cao hay dung:
  - Cau hoi thuoc nhom bao cao CHUAN (doanh thu theo kenh, top san pham, top khach hang,
    vung mien, KPI nhan vien, so sanh 2 khoang thoi gian) -> goi truc tiep cac ham da kiem chung
    trong report_templates.py, AI KHONG tu sinh SQL cho nhom nay.
  - Cau hoi AD-HOC ngoai cac mau tren -> fallback ve query_database (local SQLite); neu warehouse
    chua phu object/cot thi tim catalog dong va query SQL Server live bang tai khoan read-only.

Bao cao chuan van doc kho "local" de nhanh/on dinh. SQL Server live chi la fallback cho tai khoan
duoc phep va du lieu chua dong bo; moi query bi validate chi-doc, gioi han dong, timeout va audit.

Ho tro NHO NGU CANH da luot (conversation_memory.py) - moi session (1 phien chat webapp) duoc
nho lai vai cau hoi/tra loi gan nhat, de cau hoi tiep theo khong can nhac lai tu dau.
"""
import os
import json
import re
import time
import unicodedata
from collections import defaultdict
from functools import wraps
import anthropic
from schema_context import SCHEMA_CONTEXT
from query_engine import run_query
from report_templates import (
    call_template,
    latest_data_date,
    sync_freshness_note,
    template_available_for_channel,
    _is_new_customer_quality_question,
)
from conversation_memory import (load_history, append_message, get_query_state, set_query_state,
                                 update_query_run_progress)
from data_freshness import FreshnessCollector
from realtime_context import REALTIME_TOOLS, REALTIME_TOOL_NAMES, get_current_datetime, resolve_relative_date
from glossary_memory import save_glossary_term, retrieve_relevant_glossary
from longterm_memory import save_example, retrieve_similar_examples
from cost_logger import compute_and_log_cost
from feature_policy import (
    DISABLED_FUTURE_TOOL_NAMES,
    FUTURE_FORECAST_DISABLED_MESSAGE,
    is_future_forecast_question,
)
from sql_schema_retriever import relevant_schema_context, search_sql_catalog
from query_plan import build_query_plan

# 13/08/2026: cho phep tro sang nha cung cap khac de THU NGHIEM, mac dinh KHONG doi gi.
# DeepSeek V4 co endpoint dinh dang Anthropic (https://api.deepseek.com/anthropic) nen dung duoc
# nguyen SDK anthropic va nguyen dinh dang tool_use/tool_result - khong phai viet lai vong goi tool.
# Bat bang bien moi truong, vi du trong backend/.env:
#     LLM_BASE_URL=https://api.deepseek.com/anthropic
#     LLM_MODEL=deepseek-v4-pro
#     LLM_API_KEY=sk-...
# Bo trong ca 3 -> chay Claude y het truoc day.
MODEL = os.environ.get("LLM_MODEL", "").strip() or "claude-sonnet-5"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").strip()


class ApiCreditExhaustedError(RuntimeError):
    """The provider rejected a model call because its prepaid credit is exhausted."""

    def __init__(self, raw_message: str):
        self.raw_message = raw_message
        super().__init__(raw_message)


class UnattributedModelCallError(ValueError):
    """Do not spend API credit on a request that cannot be attributed."""


def _is_api_credit_error(exc: Exception) -> bool:
    """Only classify an HTTP billing rejection, never an arbitrary model 400."""
    if getattr(exc, "status_code", None) not in (400, 402):
        return False
    body = getattr(exc, "body", None)
    detail = f"{exc} {body}".lower()
    return any(marker in detail for marker in (
        "credit balance is too low", "credit balance too low",
        "credit_balance", "insufficient_credit", "insufficient credit",
    ))


def _translate_credit_errors(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if _is_api_credit_error(exc):
                raise ApiCreditExhaustedError(str(exc)) from exc
            raise
    return wrapped


def _translate_stream_credit_errors(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            yield from fn(*args, **kwargs)
        except Exception as exc:
            if _is_api_credit_error(exc):
                raise ApiCreditExhaustedError(str(exc)) from exc
            raise
    return wrapped


def _require_model_attribution(username: str, session_id: str, origin: str) -> None:
    """Web sessions have server-side ownership; offline runs need a readable prefix."""
    user = (username or "").strip()
    sid = (session_id or "").strip()
    if not user or user.lower() in ("unknown", "anonymous", "none", "null", "alice", "test", "admin"):
        raise UnattributedModelCallError("Lượt gọi model phải có username riêng, không dùng unknown.")
    if not sid or sid.lower() in ("default", "unknown", "none", "null"):
        raise UnattributedModelCallError("Lượt gọi model phải có session_id nhận diện được.")
    if origin != "web" and not re.match(r"^[A-Za-z][A-Za-z0-9_]*[-_:].+", sid):
        raise UnattributedModelCallError(
            "Lượt gọi model từ script phải có session_id với tiền tố nhận diện được (ví dụ uat-...)."
        )

# Cac tinh nang CHI Anthropic co. Tro sang nha cung cap khac thi phai tat, neu khong API se tu choi
# hoac lang le bo qua - ca hai deu kho phat hien.
IS_ANTHROPIC = not LLM_BASE_URL or "anthropic.com" in LLM_BASE_URL
# 17/08/2026: chot hang so PHANG = 6 - muc dung giua sau khi con so nay bi keo qua lai 3 lan.
# Lich su, giu lai ca hai phia de nguoi sau khong lap lai tranh luan:
#   8  (ban dau)  - cau hoi dieu hanh co the can nhieu buoc that; moi intent pho bien da duoc gom
#                   vao composite tool nen 8 chi la luoi an toan cho ad-hoc, khong phai muc tieu.
#   4  (04/08)    - do duoc: ha 8->4 rut ngan 5-8 giay moi cau tra loi. 10/08 giu nguyen 4 vi CA 2
#                   ca "cau hoi qua phuc tap" truy duoc nguyen nhan deu do MO TA TOOL chua ro khien
#                   model goi lap, sua cau chu la het - KHONG phai do thieu vong.
#   8  (c9883d5)  - nang lai khi them cac bao cao nhieu buoc da kiem chung.
#   6  (17/08)    - muc nguoi dung chot lam hang so PHANG cho MOI vai tro.
# 19/08/2026: DOI TU HANG SO PHANG SANG THEO CAP VAI TRO - qlv chi hoi trong pham vi doi minh
# (~5-10 nguoi, kem ca "Truong kenh" MT cung cap nay), regional_director (TP = Giam doc Mien =
# Giam doc Kenh) quan ly rong hon nen cau hoi de da nguon/nhieu buoc hon, c_level/admin_ops hoi
# toan cong ty nen can nhieu vong nhat. Neu lai thay "cau hoi qua phuc tap" o 1 cap vai tro cu
# the, kiem MO TA TOOL truoc khi nghi den viec nang so cho cap do - tien le 10/08 cho thay nguyen
# nhan thuong nam o cau chu, khong nam o so vong.
MAX_TOOL_ROUNDS_BY_ROLE = {
    "qlv": 5,
    "regional_director": 8,
    "c_level": 10,
    "admin_ops": 10,
}
DEFAULT_MAX_TOOL_ROUNDS = 6  # vai tro None/khong nhan dien duoc - giu nguyen muc 6 da chot 17/08


def _max_tool_rounds(scope_role: str = None) -> int:
    return MAX_TOOL_ROUNDS_BY_ROLE.get(scope_role, DEFAULT_MAX_TOOL_ROUNDS)
MAX_TOOLS_PER_ROUND = 5  # 10/08/2026: truoc day so 3 nam hardcode giua ham ask(). Nang 3 -> 5 vi sau
                          # khi va loi Tool Merger (xem _merge_bulk_tool_calls), cac lenh goi KHAC
                          # tham so nay chay THAT thay vi bi bo am tham, nen can them cho.
MAX_UNIQUE_TOOL_CALLS = 12  # Chan chi phi: cung tool+cung tham so chi chay 1 lan trong mot cau hoi.
MAX_ROWS_TO_MODEL = 20 # Giam tu 50 -> 30 -> 20 tiet kiem token (ad-hoc SQL, template tools khong dung)
# 23/08/2026: MAX_HISTORY_TURNS va MAX_TOKENS DOI TU HANG SO PHANG SANG THEO VAI TRO (truoc do
# ca 2 la 1 muc chung cho MOI vai tro - lich su ha MAX_HISTORY_TURNS 6->4 ngay 04/08 vi moi luot
# cu cong don token lich su khien vong sau cham di dang ke, xem MAX_TOOL_ROUNDS_BY_ROLE o tren cho
# tien le phan tang tuong tu). Nguoi dung yeu cau: qlv giu MUC THAP (doi rieng minh, ~5-10 nguoi,
# it can hoi dong vong/nho lai nhieu); cac vai tro con lai (c_level/admin_ops/regional_director -
# gom ca "giam doc mien"/"giam doc OTC"/"giam doc ETC": KHONG phai role rieng, la c_level bi gioi
# han scope_channel, xem main.py) len MUC CAO vi hoi pham vi rong hon/nhieu buoc hon.
#
# RUI RO CHI PHI cua viec tang MAX_HISTORY_TURNS: CHI an toan NEU history duoc CACHE (xem
# cache_control them vao messages truoc khi goi client.messages.create/stream ben duoi) - neu bo
# cache di, tang len 6 se ton them dang ke MOI cau hoi (khong chi luc thuc su can nho lai), dung
# nhu ly do ha tu 6 xuong 4 ngay 04/08. MAX_TOKENS thi doc lap (gioi han DAU RA, khong phai
# INPUT/lich su) - qlv thap hon hop ly vi pham vi hoi hep hon, tiet kiem chi phi output truc tiep.
MAX_HISTORY_TURNS_BY_ROLE = {"qlv": 4}
DEFAULT_MAX_HISTORY_TURNS = 6


def _max_history_turns(scope_role: str = None) -> int:
    return MAX_HISTORY_TURNS_BY_ROLE.get(scope_role, DEFAULT_MAX_HISTORY_TURNS)


def _history_to_messages(history: list) -> list:
    """23/08/2026: chuyen history (tu load_history(), content la STRING thuan) thanh messages, danh
    dau cache_control (TTL 5 phut - giong breakpoint tool_result, vi 2 cau hoi lien tiep cua CUNG
    nguoi dung thuong cach nhau tu vai chuc giay den vai phut, hiem khi qua 5 phut) tren tin nhan
    CUOI CUNG cua history NEU co.

    LY DO CAN HAM NAY: truoc 23/08, history duoc noi thang vao messages KHONG co cache_control nao -
    moi cau hoi moi trong CUNG phien phai tra GIA GOC cho toan bo lich su cu (khong doi giua 2 luot
    hoi lien tiep, chi them 1 cap hoi-dap moi o cuoi). Day la ly do chinh khien MAX_HISTORY_TURNS
    truoc do phai giu THAP (4) de kiem soat chi phi - tang len se an toan hon nhieu khi phan "cu"
    duoc cache-hit (~10% gia goc) thay vi tra gia goc MOI lan.

    cache_control CHI dat duoc tren content dang LIST cac block (khong dat truoc tren string don) -
    nen tin nhan cuoi cung PHAI duoc chuyen tu string sang [{"type": "text", "text": ...}] truoc khi
    gan cache_control vao block do. Cac tin nhan khac GIU NGUYEN dinh dang string (khong can doi,
    tranh thay doi hanh vi ngoai pham vi can sua)."""
    if not history:
        return []
    msgs = list(history)
    last = dict(msgs[-1])
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    msgs[-1] = last
    return msgs


MAX_TOKENS_BY_ROLE = {"qlv": 5120}
DEFAULT_MAX_TOKENS = 6144


def _max_tokens(scope_role: str = None) -> int:
    return MAX_TOKENS_BY_ROLE.get(scope_role, DEFAULT_MAX_TOKENS)


MAX_PAYLOAD_CHARS = 10000  # Ngan sach context gui model (~2500 tokens). Ket qua day du van giu trong
                          # last_result (log/doi chieu); phan gui model duoc tom luoc co cau truc,
                          # luon la JSON hop le va khong cat chuoi giua dong.


# 14/09/2026 (ra soat 77694cb): nut Tai Excel tren giao dien chi xuat BANG DANG HIEN THI
# (src/app/TableExport.tsx doc tu DOM), con backend chi gui columns/rows day du cho duong SQL tho.
# Tool bao cao (KPI, khach hang...) vi vay KHONG co file day du de tai. Khi model chi liet ke mot
# phan thi PHAI noi dang liet ke bao nhieu tren tong; khong duoc hua "Tai Excel de xem day du" va
# lop loc cuoi (query_plan) khong duoc xoa dong do.
_QUY_TAC_LIET_KE_MOT_PHAN = (
    "Dung cac tong/so dem toan bo de ket luan. Neu chi liet ke mot phan, hien cac muc uu tien va ghi "
    "mot dong 'Dang liet ke N/T <doi tuong>' (N=shown, T=total trong collections). KHONG noi ve "
    "payload/context/gioi han ky thuat va KHONG hua Tai Excel co danh sach day du."
)
_NHIEU_THANG_RE = re.compile(r"\b(?:\d+|hai|ba|bon|nam|sau)\s+thang\b")


def _hoi_nhieu_thang(q: str) -> bool:
    """Cau hoi ve CHUOI/NHIEU thang (q da bo dau, chu thuong): 'lien tiep', 'lien tuc', '3 thang'."""
    return "lien tiep" in q or "lien tuc" in q or bool(_NHIEU_THANG_RE.search(q))


def _timeout_env(name: str, default: float, ceiling: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1.0), ceiling)


# Gate production cam request >120s: ke ca .env go nham 300, code van kep tran 120.
REQUEST_TIMEOUT_SECONDS = _timeout_env("CHAT_REQUEST_TIMEOUT_SECONDS", 110, 120)
TOOL_TIMEOUT_SECONDS = _timeout_env("CHAT_TOOL_TIMEOUT_SECONDS", 40, REQUEST_TIMEOUT_SECONDS)
LLM_CALL_TIMEOUT_SECONDS = _timeout_env("CHAT_LLM_TIMEOUT_SECONDS", 45, REQUEST_TIMEOUT_SECONDS)


def _fold_for_route(question: str) -> str:
    """Chuan hoa cau hoi cho router: chu thuong, bo dau, gop khoang trang."""
    return " ".join("".join(
        ch for ch in unicodedata.normalize("NFD", (question or "").lower())
        if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d").split())


def _required_tool_for_question(question: str) -> str | None:
    """Ep tool cho cac intent co mot duong du lieu duy nhat, tranh do catalog nhieu vong."""
    q = _fold_for_route(question)
    if _is_new_customer_quality_question(question):
        return "get_new_customer_list"
    # 26/09/2026 (hop 24/09 "bam bang KPI QLV/TDV"): bang KPI doi/nguoi co mot nguon, khong ghep nhieu tool.
    if "bang kpi" in q and not any(marker in q for marker in ("thuong", "luong", "xep hang")):
        return "get_kpi_scorecard"

    # 14/09/2026 - phan hoi nguoi dung that: "nhung nhan vien ... duoi 60%" va cau noi
    # "danh sach duoi 65%" khong duoc dinh tuyen, model tu do qua nhieu tool KPI/revenue roi
    # chi xin 15 dong. Day la intent mot nguon: employee_kpi da tinh san tat ca nguong.
    threshold_list = (
        any(marker in q for marker in ("duoi", "khong dat", "chua dat"))
        and re.search(r"\b(?:60|65|70|80|100|120)\s*%", q)
        and any(marker in q for marker in (
            "nhan vien", "nhan vien ban hang", "tdv", "qlv", "danh sach", "nhung ai", "ai ",
        ))
        and not any(marker in q for marker in ("khach hang", "san pham", "sku"))
        and not any(marker in q for marker in ("qlv nao co nhieu", "phan hut cua doi tap trung"))
        # 14/09/2026 (ra soat 77694cb): "duoi 80% ba thang lien tiep" la cau CHUOI THANG ma
        # employee_kpi chi co mot thang. Khong cuop cau nhieu thang cua luat workforce_productivity
        # ben duoi (C47/V13/M16).
        and not _hoi_nhieu_thang(q)
    )
    if threshold_list:
        return "get_employee_kpi"

    # Bao cao hoan thanh chi tieu theo thang/vung co mot composite tool da gom san doanh so,
    # target va % hoan thanh; ep dung ngay de tranh model do catalog nhieu vong.
    if (any(marker in q for marker in ("bao cao hoan thanh", "hoan thanh chi tieu"))
            and "thang" in q):
        return "get_revenue_tree"

    # 15/09/2026 (nhat ky UAT 13:59-14:11): ba cau khach hang/KPI co tool DANH SACH rieng. Truoc day
    # khong co tool nao nen chatbot mo ta chung, thieu khach hoac khong goi SQL.
    if any(marker in q for marker in ("khach hang moi", "khach moi")) and any(
            marker in q for marker in ("danh sach", "ngay ghi nhan")):
        return "get_new_customer_list"
    if "tai don" in q and any(marker in q for marker in ("chua dat", "chua tai don", "danh sach")):
        return "get_reorder_pending_customers"
    if ("san pham trong tam" in q or ("trong tam" in q and "kpi" in q)) and "sku" not in q \
            and not any(marker in q for marker in ("dm1", "dm2", "dm3")):
        return "get_focus_product_kpi"
    # C11/S70 co nhac "top 3 mien/vung" nhung trong tam la muc tap trung dong thoi theo
    # khach + SKU + dia ly va xu huong thang. Phai chan truoc luat doanh thu theo vung rong.
    if any(marker in q for marker in ("phu thuoc top", "phu thuoc vao top", "muc do tap trung")) \
            and any(marker in q for marker in ("top 10 khach", "top 10 san pham")):
        return "get_top_customers"
    if (any(marker in q for marker in ("doanh thu", "doanh so", "phat sinh"))
            and any(marker in q for marker in ("3 mien", "ba mien", "theo mien", "theo vung"))):
        return "get_revenue_by_region"
    is_team = any(word in q for word in ("doi", "doi toi", "toan doi", "tong doi"))
    # 13/09/2026 (ra soat 126 cau): cau hoi ve CHUOI THANG LIEN TIEP cua nguoi/doi phai vao
    # workforce_productivity - tool duy nhat co decline_streak_months va below_80_streak_months.
    # Dat TRUOC moi luat tu khoa khac: V13 ("ai giam lien tiep 2-3 thang; nguyen nhan mat khach, it
    # don, it SKU") tung bi luat "it don" keo sang tool do phu khach-SKU, con C47 ("duoi 80% lien tiep
    # 3 thang") bi luat dia ban keo di - ca hai tool deu khong co chuoi lien tiep nen khong tra loi
    # tron cau. Trong 126 cau chi C47/M05/M16/V13 co cum "lien tiep" nen luat nay khong cuop cau khac.
    if "lien tiep" in q and any(marker in q for marker in ("giam", "duoi 80")):
        return "get_workforce_productivity"
    if "view" in q and any(marker in q for marker in ("doi soat", "doi chieu", "so sanh", "lech")):
        return "get_revenue_view_reconciliation"
    if "aso" in q.split() and any(marker in q for marker in (
        "dieu kien", "tung nhan vien", "vi sao", "bang 0", "chot the nao",
    )):
        return "get_salary_aso_detail"
    if ("sku" in q and any(marker in q for marker in ("ton kho", "thieu hang", "ton cao"))
            and any(marker in q for marker in ("doanh thu giam", "doanh so giam"))
            and any(marker in q for marker in ("hai ky", "2 ky", "ky truoc"))):
        return "get_sku_revenue_drop_vs_stock"
    if "xep hang toan bo nhan vien" in q:
        return "get_employee_kpi"
    # C13 co nhac "khuyen mai" nhu mot cau phan ra doanh thu gop/thuan, khong hoi
    # hieu qua mot chuong trinh. Giu no o bao cao chi tiet don/hang tra.
    if "doanh thu gop" in q and "doanh thu thuan" in q and "hang tra" in q:
        return "check_order_timing"
    # V33: cau hoi van hanh ve don huy/tra/dieu chinh/chua co hoa don phai tu dong vao bao
    # cao don. Khong bat nguoi dung nhac lai khoang ngay; tool tu lay dau thang hien tai den
    # ngay du lieu moi nhat khi cau hoi khong ghi ky.
    if any(marker in q for marker in (
        "don nao bi huy", "don bi huy", "don huy", "giao/hoa don cham", "giao hoa don cham",
        "giao cham", "hoa don cham", "chua tim thay hoa don", "chua co hoa don", "chua hoa don",
    )):
        return "check_order_timing"
    # CTKM phai xet truoc cac nhanh tong hop "doi/khach/don". V34 co du ca ba tu
    # nay nhung nguon chinh van la chuoi DMS_DonHangCTKM -> DMS_CTKM.
    is_promo = any(word in q for word in ("khuyen mai", "ctkm"))
    if is_promo and any(marker in q for marker in (
        "den ngay nao", "mat don", "mat ma chuong trinh", "moc lien ket", "do phu",
    )):
        return "get_promotion_data_quality"
    if is_promo:
        return "get_promotion_effectiveness"

    # Dinh tuyen cac cau trong cot E UAT vao composite tool da co san. Thu tu tu cu the den rong:
    # mot cau co the chua nhieu tu khoa, nhung vong dau phai vao dung nguon chinh thay vi free-SQL.
    if ("tung thang" in q or "moi thang dat" in q) and (
            "ytd" in q or "% ke hoach" in q or "phan tram ke hoach" in q):
        return "get_revenue_monthly_series"
    if "luy ke" in q or "ytd" in q:
        return "get_revenue_ytd_cumulative"
    if any(marker in q for marker in ("loi nhuan gop", "bien loi nhuan", "loi nhuan thap", "loi nhuan am")):
        # Kho khong co gia von/COGS. Van dua vao mot template chi-doc de call_template tra
        # SOURCE_GAP co cau truc, khong cho free-SQL suy dien loi nhuan tu doanh thu.
        return "get_revenue_monthly_series"
    if "run-rate thang hien tai" in q or "run rate thang hien tai" in q:
        return "get_kpi_gap_run_rate"
    if "dong gop bao nhieu vao bien dong chung" in q:
        return "get_geography_monthly_performance"
    if "bien dong doanh thu duoc giai thich" in q and any(
            marker in q for marker in ("so don", "so khach", "tan suat", "san luong", "gia ban")):
        return "get_geography_monthly_performance"
    if ("trung binh truot 3 thang" in q and "6 thang" in q) or "diem gay xu huong" in q:
        return "get_revenue_monthly_series"
    if "ty trong otc/etc" in q and "tung thang" in q:
        return "get_revenue_monthly_series"
    if "loai cac giao dich bat thuong" in q and any(
            marker in q for marker in ("don lon", "tra hang", "dieu chinh")):
        return "check_order_timing"
    if "don vi nao" in q and "lien tuc 3/6 thang" in q:
        return "get_geography_monthly_performance"
    if any(marker in q for marker in ("cohort", "giu chan sau", "ty le giu chan")):
        return "get_customer_cohort_retention"
    if any(marker in q for marker in ("san pham moi", "sp moi")) and any(
            marker in q for marker in ("do phu", "sau 1/3/6", "sau 1/3/6/12", "ra mat")):
        return "get_customer_product_coverage"
    # C29: can CA co nghiep vu NC/RO cua Bravo LAN chuoi active/reactivated/stopped tu hoa don.
    # Bao cao lifecycle tra hai lop nay rieng biet; khong de nhanh "tai kich hoat" chung rut cau
    # hoi tung thang thanh mot cap thang duy nhat.
    #
    # 10/09/2026: cau hoi THAT cua DNH (C29) viet dang liet ke roi dau phay - "khach hoat dong, moi,
    # mua lai, tai kich hoat, ngung mua tung thang" - sau khi bo dau/chuan hoa khoang trang, "moi"
    # dung MOT MINH (khong dinh lien "khach moi") nen pattern cu bo lo route nay, khien model tu goi
    # THEM ca get_customer_movement (dinh nghia "khach moi" khac han, tu suy tu hoa don thay vi dung
    # co he thong IsNC) tron chung vao 1 cau tra loi - da bat qua kiem thu thuc te: 2 bang cung
    # ten "khach moi" ra 612 (dung, khop UAT) va 441 (tu suy dien, SAI y nghia) trong CUNG 1 cau tra
    # loi, gay nham lan khi doi chieu. Them bien the liet ke roi ("moi" dung rieng canh "khach hoat
    # dong"/"ngung mua"/"tai kich hoat") de bat dung ca cach viet cau hoi tu nhien nay.
    c29_markers = ("khach hoat dong", "tai kich hoat", "ngung mua", "mua lai")
    q_words = f" {q.replace(',', ' ')} "
    if sum(marker in q for marker in c29_markers) >= 3 and (
        "khach moi" in q or " moi " in q_words
    ) and any(marker in q for marker in ("tung thang", "theo thang", "moi thang")):
        return "get_customer_lifecycle_summary"
    # V28/S83 phai nam TRUOC nhanh tai kich hoat chung: cau nay ket hop bon muc tieu, khong phai
    # chi mot danh sach khach tai kich hoat.
    if "danh sach khach" in q and any(marker in q for marker in ("giu khach", "tai kich hoat", "thu no", "ban cheo")):
        return "get_customer_product_coverage"
    if "khach mua dong thoi otc va etc" in q or "mua cheo kenh" in q:
        return "get_customer_product_coverage"
    if "ba rui ro lon nhat" in q and "ke hoach" in q:
        return "get_customer_product_coverage"
    # Bao cao tong gia tri ton theo mien van dung inventory_by_region, ke ca khi nguoi dung
    # liet ke them stock-out. Chi dinh tuyen sang SKU risk khi trong tam la SKU/thieu/cham ban.
    # 15/09/2026 (UAT 14:40 "So luong ton kho bo phe tinh den hom nay"): ton kho cua MOT san pham theo
    # ten. Loai tru cac y ton kho da co tool rieng (gia tri/so thang ton, han dung, cham ban, thieu hang,
    # SKU) va cau hoi tong theo vung/mien.
    if "ton kho" in q and not any(marker in q for marker in (
        "gia tri ton", "so thang ton", "can date", "han su dung", "het han", "cham ban", "cham luan chuyen",
        "thieu hang", "kho thieu", "ton cao", "stock-out", "sku", "mien", "vung", "chi nhanh", "tong ton",
        "doanh thu", "doanh so",
    )):
        return "get_inventory_item_stock"
    if "gia tri ton kho" in q:
        return "get_inventory_by_region"
    # 13/09/2026: C44/M42 hoi TIEN DO THUC HIEN hop dong. Truoc day day sang bao cao dia ban (chi co
    # doanh thu thuc hien, khong co gia tri hop dong/con lai/han) nen ca hai deu CHUA DAT voi ly do
    # "chua co khoa lien ket hoa don - hop dong". Kiem lai 13/09: khoa CO that, ContractId phu 100%
    # dong hoa don ETC va khop 1.037/1.037 hop dong -> dung tool hop dong.
    # 15/09/2026 (UAT dnh_etc 14:43): doanh so ETC theo nhom hang co tool rieng. Cau khong ghi "ETC"
    # tu tai khoan kenh ETC duoc bat o _required_tool_for_request (can biet kenh cua tai khoan).
    if _hoi_doanh_so_theo_nhom_hang(q) and "etc" in q.split():
        return "get_etc_revenue_by_item_type"
    if any(marker in q for marker in (
        "hop dong etc", "hop dong/goi thau", "hop dong goi thau", "goi thau nao",
        "sap het hieu luc", "gia tri lon chua giai ngan", "ty le thuc hien thap",
        "chua giai ngan",
    )):
        return "get_etc_contract_status"
    # M22/S88: cau hoi ba ve "ngung mua HOAC giam mua HOAC keo dai chu ky mua so voi lich su" can
    # ca ba tin hieu trong MOT bang. get_customer_movement chi so thang nay voi thang lien truoc va
    # khong co khoang cach mua trung binh, nen luon thieu ve thu ba - dinh tuyen cu khien M22 tra
    # loi khong du de bai. Phai xet TRUOC nhanh "ngung mua" rong ben duoi.
    if "keo dai chu ky" in q or (
        any(marker in q for marker in ("ngung mua", "khach lon nao ngung"))
        and any(marker in q for marker in ("giam mua", "giam manh", "so voi lich su", "so lich su"))
    ):
        return "get_customer_attrition_risk"
    if any(marker in q for marker in (
        "tai kich hoat", "ngung mua", "tang truong den tu mo moi", "doanh thu mat",
        "bu duoc bao nhieu", "khach lon nao ngung", "keo dai chu ky mua",
        "like-for-like", "like for like", "tang truong huu co", "tang mua tren khach hien huu",
        "mo nhieu khach moi",
    )):
        return "get_customer_movement"
    if "tang truong hien tai den tu mo moi" in q and "khach hang hien huu" in q:
        return "get_customer_movement"
    if "khach da mua thang truoc" in q and "chua mua thang nay" in q:
        return "get_customer_movement"
    if "khach moi thang nay" in q and "don lap lai" in q:
        return "get_customer_movement"
    if any(marker in q for marker in ("top khach hang", "top 10 khach", "khach tang/giam manh")):
        return "get_top_customers"
    if any(marker in q for marker in ("khach im lang", "im lang 30", "im lang 60", "im lang 90")):
        return "get_customers_silent"
    # M40/S28 co "chuyen vung" nhu mot HANH DONG xu ly ton, khong phai dieu chuyen nhan su/khach.
    # Chan truoc nhanh data-quality rong ben duoi.
    if any(marker in q for marker in ("can date", "cham luan chuyen", "cham ban")) and any(
            marker in q for marker in ("chuyen vung", "day ban", "dung nhap", "xu ly ton")):
        return "get_inventory_expiry_report"
    # C28/S91 hoi LOAI anh huong doi NV/khach, khac M18 hoi dia ban trong va NV nghi. Phai xet
    # truoc nhanh "chuyen vung" rong, neu khong cau nay roi vao data-quality va khong co phep do.
    if any(marker in q for marker in (
        "loai anh huong", "loai tru anh huong", "giu nguyen nhan vien",
    )) and any(marker in q for marker in (
        "chuyen nhan vien", "chuyen nv", "chuyen khach", "thay doi dia ban", "chuyen vung",
    )):
        return "get_customer_product_coverage"
    if any(marker in q for marker in (
        "dia ban trong", "nv nghi", "chuyen vung", "khach chua gan",
    )):
        return "get_operational_data_quality"
    # V26 phai xet truoc nhanh "tinh nao" ben duoi: day la cau hoi ve TUNG KHACH so voi
    # benchmark noi bo, khong phai bao cao tong hop theo tinh.
    if ("khach tuong dong" in q or "khach nao mua it hon" in q or
            ("tuong dong" in q and "phan khuc" in q and "khach" in q)):
        return "get_customer_product_coverage"
    # V29/S21: top/bottom SKU TUNG THANG khac voi coverage cua mot cua so hien tai.
    if any(marker in q for marker in ("top/bottom", "top bottom", "top va bottom")) and \
            any(marker in q for marker in ("san pham", "sku")) and \
            any(marker in q for marker in ("tung thang", "theo thang", "từng tháng")):
        return "get_customer_product_coverage"
    # V30/S46: phai goi duong bao cao co canh bao mau so target theo SKU dang thieu; khong de model
    # lay target doanh so tong cua TDV roi gan nham thanh target cua tung SKU/khach.
    if any(marker in q for marker in ("sku trong tam", "sku trọng tâm", "sku chien luoc")) and \
            any(marker in q for marker in ("target", "% target", "phan tram target", "khoang thieu")):
        return "get_customer_product_coverage"
    # V31/S23: phan bo SKU theo KH/luong-don/AOV la hai nhom so sanh, khong phai top doanh thu
    # hay bao cao xoi mon gia chung.
    if any(marker in q for marker in ("nhieu khach mua", "it khach", "ít khách")) and \
            any(marker in q for marker in ("luong/don", "lượng/đơn", "aov")):
        return "get_customer_product_coverage"
    # V24: so sanh TUNG KHACH giua hai cua so 3 thang ve don/AOV/SKU. Khong de model tu
    # chon bao cao dia ban chi vi cau co nhac den "tinh".
    if "khach nao" in q and "3 thang" in q and any(
            marker in q for marker in ("tan suat", "aov", "sku", "so sku", "sku/don")):
        return "get_customer_product_coverage"
    if ("tung thang" in q or "qua tung thang" in q) and any(
            marker in q for marker in ("so khach", "khach/", "don/", "aov", "tan suat")):
        # M07: can chuoi khach/don/AOV theo dia ban, khong phai bang coverage cua mot cap ky.
        return "get_geography_monthly_performance"
    # Dia ban phai uu tien truoc cac tu khoa "it don"/"doanh thu/khach" ben duoi.
    # Neu khong M27 se bi dua vao bao cao coverage theo san pham thay vi so sanh tinh/huyen.
    if any(marker in q for marker in (
        "tinh nao", "tinh/", "chi nhanh", "npp", "dia ban", "vung nao dong gop", "xep hang vung",
        "quy mo lon", "tang truong thap", "co hoi trang",
    )):
        return "get_geography_monthly_performance"
    if any(marker in q for marker in ("uu tien", "dong gap", "can uu tien")) and any(
            marker in q for marker in ("khach hang", "san pham", "nhan vien", "tdv")):
        return "get_customer_product_coverage"
    if any(marker in q for marker in ("ke hoach thau", "ty le trung thau", "gia tri trung thau")):
        # Ke hoach/gia tri tham gia thau va ty le trung KHONG co trong vHopDongETC (bang do chi co hop
        # dong da ky). Giu bao cao dia ban ETC cho phan doanh thu thuc hien va buoc chatbot neu ro
        # phan thau la thieu nguon - C43/M41 dang khop theo huong nay.
        return "get_geography_monthly_performance"
    if any(marker in q for marker in (
        "xoi mon gia", "gia ban thuc te", "giam gia ban", "do it khach", "it don",
        "giam luong", "luong/don", "doanh thu/khach", "mua it sku", "share-of-wallet noi bo",
    )):
        return "get_customer_product_coverage"
    if ("sku" in q or "san pham" in q or "nhom sp" in q) and any(
            marker in q for marker in ("dong gop", "tang/giam", "keo giam")):
        return "get_customer_product_coverage"
    if any(marker in q for marker in ("ban cheo", "cross-sell", "mua cung", "ban combo")):
        return "get_cross_sell_opportunities"
    if any(marker in q for marker in (
        "thieu target", "thieu manager", "thieu quan ly", "trung ma", "sai mapping",
        "khach chua gan", "thieu dms", "snapshot chua chot", "ngoai le chua xu ly",
        "owner, deadline", "owner deadline", "hanh dong, owner",
    )):
        return "get_operational_data_quality"
    if "ty le khach khong gan tdv" in q or (
            "sai vung" in q and "thieu thong tin dms" in q):
        return "get_operational_data_quality"
    if ("chu so huu" in q or "nguoi chiu trach nhiem" in q) and any(
            marker in q for marker in ("deadline", "han hoan thanh", "cam ket hanh dong", "hanh dong")):
        return "get_operational_data_quality"
    # Mot khach cu the hoi du no: dung customer_detail, ke ca khi nguoi dung chi nho TEN.
    # Dat truoc nhanh cong no tong hop de "Benh vien Bac Ninh con no bao nhieu" khong roi vao
    # receivables_overview hoac bi bot tu choi vi thieu ma.
    if any(marker in q for marker in ("con no", "du no", "no bao nhieu")) and not any(
            marker in q for marker in (
                "tong no", "top ", "khach nao", "nhung khach", "theo vung", "theo mien",
                "toan cong ty", "toan kenh", "ty le no",
            )):
        return "get_customer_detail"
    if any(marker in q for marker in (
        "tong no", "no qua han", "dso", "thu tien", "no xau", "bop ban", "thu hoi",
    )):
        if any(marker in q for marker in ("khach can", "khach vua", "doanh thu nguy co", "bop ban")):
            return "get_customer_revenue_debt_risk"
        return "get_receivables_overview"
    if any(marker in q for marker in (
        "stock-out", "thieu hang", "kho thieu", "nguy co mat hang", "nguy co mat don",
        "cham luan chuyen", "ton cao", "dung nhap", "can date",
    )):
        # S28/S47: can ton theo SKU + nhu cau 3 thang, khong phai chi tong ton theo mien.
        return "get_inventory_expiry_report"
    if "so thang ton" in q:
        return "get_inventory_by_region"
    if any(marker in q for marker in (
        "tinh nao", "tinh/", "chi nhanh", "npp", "dia ban", "vung nao dong gop", "xep hang vung", "quy mo lon",
        "tang truong thap", "co hoi trang",
    )):
        return "get_geography_monthly_performance"
    if any(marker in q for marker in (
        "vieng tham", "viếng thăm", "di tuyen", "đi tuyến", "phu tuyen", "phủ tuyến",
        "dung tuyen", "đúng tuyến", "route", "check-in", "check in",
        "ty le co don sau tham", "tỷ lệ có đơn sau thăm",
    )):
        return "get_workforce_productivity"
    if any(marker in q for marker in (
        "nang suat", "span of control", "giam lien tiep 3 thang", "giam doanh so lien tiep",
        "headcount", "ramp-up", "ramp up",
    )):
        return "get_workforce_productivity"
    if any(marker in q for marker in ("gap toi kh", "duoi 80% kh", "moi ngay can dong gop",
                                       "ngay/tuan dang chay", "nhip can thiet")):
        return "get_kpi_gap_run_rate"
    if "gap toi ke hoach" in q and "moi vung" in q:
        return "get_kpi_gap_run_rate"
    if "vung nao duoi 80% ke hoach lien tiep" in q:
        return "get_workforce_productivity"
    if ("doanh so, target" in q and "tung qlv/doi" in q) or \
            "qlv nao co nhieu nhan vien duoi 80%" in q:
        return "get_workforce_productivity"
    if any(marker in q for marker in (
        "tdv trong doi", "doanh so/target", "dat 100%", "qua cong 65", "duoi cong",
        "so nv duoi 80",
    )):
        return "get_employee_kpi"
    if "mua vu" in q:
        # C08: phai bat dau bang chuoi thang, de tool tu danh dau thang khong du du lieu
        # thay vi model tu suy dien tinh mua vu tu vai ngay/1-2 thang hien co.
        return "get_revenue_seasonality"
    if any(marker in q for marker in ("theo thang", "3/6 thang", "3 thang", "6 thang", "xu huong")) \
            and any(marker in q for marker in ("tdv", "nhan vien")) \
            and any(marker in q for marker in ("target", "% hoan thanh", "xep hang", "doanh so")):
        return "get_workforce_productivity"
    if any(marker in q for marker in (
        "theo tung thang", "qua tung thang", "xu huong tap trung",
        "3/6 thang", "6 thang", "24 thang",
    )) and any(marker in q for marker in ("doanh thu", "doanh so", "mom", "yoy", "cagr")):
        return "get_revenue_monthly_series"

    if any(marker in q for marker in (
        "phu thuoc top", "top 10 khach", "top 10 san pham", "top 3 mien", "muc do tap trung",
    )):
        # C11: top-customers tra mau so toan pham vi (scope_revenue), sau do model co the
        # goi them top-products/geography neu cau hoi yeu cau du ca ba chieu.
        return "get_top_customers"
    if "hang tra" in q or "dieu chinh don" in q:
        # C13: Amount9 am phai di qua bao cao don, khong suy tu doanh thu tong hop.
        return "check_order_timing"
    if any(marker in q for marker in ("don/hoa don bat thuong", "don bat thuong", "hoa don bat thuong",
                                       "ty le tra hang", "hang tang tren dt")):
        return "check_order_timing"

    # Cac intent UAT cua QLV da tung chon sai/roi du lieu khi model tu ghep 4-12 tool. Ep DUONG
    # BAO CAO DA CO SAN ngay tu vong dau; cac vong sau van duoc phep goi them neu cau hoi co nhieu ve.
    if is_team and not any(word in q for word in ("thuong", "kpi", "chinh sach")) and any(
            word in q for word in ("hàng trả", "hang tra", "đơn lớn", "don lon",
                                   "bất thường", "bat thuong", "chạy đơn", "chay don")):
        return "check_order_timing"
    if any(word in q for word in ("còn thiếu", "con thieu", "mỗi ngày cần", "moi ngay can")) and any(
            threshold in q for threshold in ("65", "70", "80", "100", "120", "kpi")):
        return "get_kpi_gap_run_rate"
    metric_words = ("khách", "khach", "đơn", "don", "aov", "tần suất", "tan suat",
                    "sản lượng", "san luong", "giá trị đơn", "gia tri don")
    if is_team and any(word in q for word in ("3 tháng", "ba tháng", "3 thang", "ba thang")) \
            and any(word in q for word in metric_words):
        return "get_geography_monthly_performance"
    if is_team and (any(word in q for word in metric_words) or
                    any(word in q for word in ("đóng góp", "dong gop"))):
        return "get_customer_product_coverage"
    if any(marker in q for marker in ("sku chien luoc", "sp moi dat do phu", "san pham moi dat do phu")):
        return "get_customer_product_coverage"

    if "ty le nhan su dat" in q and any(
            threshold in q for threshold in ("65", "70", "80", "100", "120")):
        return "get_employee_kpi"

    is_salary = any(word in q for word in (
        "lương", "luong", "thưởng", "thuong", "v25", "totalpoint", "dmbonus",
    ))
    if is_salary:
        if any(marker in q for marker in (
            "chi phi thuong", "thuong tren doanh thu", "thuong kinh doanh tren doanh thu",
        )):
            return "get_salary_ranking"
        if (("totalpoint" in q and any(dm in q for dm in ("dm1", "dm2", "dm3", "dmbonus")))
                or any(marker in q for marker in (
                    "lương cơ bản", "luong co ban", " lcb", "snapshot nào", "snapshot nao",
                    "dòng đầu", "dong dau", "giữa tháng rỗng", "giua thang rong",
                ))):
            return "get_salary_data_quality"
        if any(marker in q for marker in (
            "từng người", "tung nguoi", "cả đội", "ca doi", "toàn đội", "toan doi", "doi",
            "thay đổi", "thay doi", "phụ cấp", "phu cap",
        )):
            # Mot bang compact cho ca doi, co san ky truoc + delta. Tranh 8 lenh salary_detail
            # lam vuot tool-loop va cat payload giua danh sach.
            return "get_salary_ranking"
        if "v25" in q and any(marker in q for marker in (
            "bậc", "bac", "v25bonus", "bằng 0", "bang 0", "công thức", "cong thuc",
        )):
            return "get_salary_bonus_policy"
    return None

TEMPLATE_TOOLS = [
    {
        "name": "get_sku_revenue_drop_vs_stock",
        "description": "So SKU giam doanh thu qua hai ky THANG TRON lien ke voi ton ghi nhan theo lo/nam. "
                       "months_back la so thang moi ky, khong phai binh quan 30 ngay. "
                       "Tra zero_recorded_stock, positive_recorded_stock, unknown_or_negative_stock "
                       "va counts truoc limit. Ton ghi nhan KHONG chung minh ton kha dung hien tai; "
                       "thieu dong ton KHONG phai 0; con ton KHONG dong nghia ton cao. Khong ket luan "
                       "nguyen nhan mat doanh thu. Cau thieu/cham ban khong so hai ky dung inventory_expiry_report.",
        "input_schema": {"type": "object", "properties": {
            "months_back": {"type": "integer", "minimum": 1, "maximum": 12},
            "area_code": {"type": "string", "enum": ["MB", "MT", "MN"]},
            "min_prev_revenue": {"type": "number", "minimum": 0},
            "drop_pct_threshold": {"type": "number", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": []},
    },
    {
        "name": "get_revenue_view_reconciliation",
        "description": "Doi soat doanh thu view Total va view thuong tren Bravo cho OTC va ETC. "
                       "Chi cho C-Level/admin khong gioi han scope. KHAC revenue_reconciliation "
                       "(hoa don voi KPI). Chenh lech chua chung minh nguyen nhan, khong khang dinh "
                       "view nao dung hon; nguong 0.5% chi sang loc. Ngay cuoi ky duoc tinh day du.",
        "input_schema": {"type": "object", "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"}},
            "required": ["date_from", "date_to"]},
    },
    {
        "name": "get_salary_aso_detail",
        "description": "Chi tiet co dieu kien ASO tren Bravo: so khach, doanh so, ket qua cuoi. "
                       "Dung khi hoi ai khong qua/vi sao ASO bang 0. Chi C-Level/admin hoac QLV dung doi. "
                       "CS/TK dung is_ac, khong ap dung ASO; doi chi gom CS/TK tra not_applicable, "
                       "cs_tk_excluded_count la so nguoi CS/TK da loai. NULL/khong tinh la chua du bang chung, "
                       "khong phai khong dat. total_* la toan scope, selected_total theo only_failed, "
                       "rows_truncated bao cat limit. Snapshot cuoi thang KHONG tu dong la da duyet luong. "
                       "Doc fail_reasons; khong suy nguyen nhan hay de nghi bu thuong.",
        "input_schema": {"type": "object", "properties": {
            "year_month": {"type": "string", "description": "YYYY-MM; neu chi dinh phai dung dung ky."},
            "area_code": {"type": "string", "enum": ["MB", "MT", "MN"]},
            "position_code": {"type": "string"}, "only_failed": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "required": []},
    },
    {
        "name": "get_revenue_by_channel",
        "description": "Doanh thu + so hoa don theo kenh OTC va ETC trong 1 khoang ngay. "
                        "Truy van DA KIEM CHUNG khop 100% voi Bravo - UU TIEN dung tool nay cho moi cau hoi ve doanh thu theo kenh/tong doanh thu. "
                        "Voi tai khoan chi duoc xem kenh ETC ma KHONG co scope_area_code, tong ETC la TOAN KENH ETC, "
                        "gom ca 3 mien MB/MT/MN; PHAI noi ro 'toan kenh ETC, gom ca 3 mien' ngay canh tong. "
                        "Neu co scope_area_code thi chi noi tong kenh ETC trong mien duoc phep, KHONG goi la ca 3 mien.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Ngay bat dau, dinh dang YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "Ngay ket thuc, dinh dang YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_top_products",
        "description": "Top N san pham theo doanh thu trong 1 khoang ngay (da tu dong loai hang khuyen mai khoi so luong). "
                        "Moi dong co scope_revenue va share_pct_of_scope tinh tren TOAN BO pham vi truoc khi cat top-N; "
                        "dung cac truong nay cho cau hoi muc do tap trung, KHONG lay tong top-N lam mau so. "
                        "UU TIEN dung tool nay cho moi cau hoi ve san pham ban chay/top san pham. "
                        "Neu nguoi dung yeu cau tach/so sanh top san pham OTC va ETC, BAT BUOC goi tool HAI LAN "
                        "voi cung khoang ngay va limit: mot lan channel=OTC, mot lan channel=ETC; KHONG dung "
                        "channel=ALL vi ALL gop doanh thu hai kenh theo cung ma san pham. Tu dong tra ve top san "
                        "pham cua rieng doi QLV neu duoc hoi. Moi dong co theo_mien (doanh thu MB/MT/MN cua "
                        "chinh SKU do): cau hoi KHONG gioi han vung thi BAT BUOC trinh bay kem chi tiet theo mien. "
                        "Cap 3: SKU cua 1 TDV/doi 1 QLV -> employee_code; SKU 1 khach mua -> customer_code "
                        "(loc tu dau, ket qua co loc_theo).",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "So luong top can lay, mac dinh 10"},
                "area_code": {"type": "string", "enum": ["MB", "MT", "MN"], "description": "Loc DUNG mot mien khi nguoi dung hoi top cua mien do (vd top khach hang mien Trung -> MT); KHONG lay top toan quoc roi tu loc."},
                "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"], "description": "Kenh, mac dinh channel=ALL (gop ca 2 kenh). Khi tach/so sanh OTC va ETC, goi rieng channel=OTC va channel=ETC; khong dung channel=ALL."},
                "employee_code": {"type": "string", "description": "Ma HOAC TEN 1 nhan vien: TDV/CS/TK -> hoa don cua chinh nguoi do; QLV -> ca doi cua QLV do. Khong dung cho TP/GD mien (dung area_code)."},
                "customer_code": {"type": "string", "description": "Ma HOAC TEN 1 khach hang - top SKU khach do mua trong ky."},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_top_customers",
        "description": "Top N khach hang theo doanh thu trong 1 khoang ngay. "
                        "Moi dong co scope_revenue va share_pct_of_scope tinh tren TOAN BO pham vi truoc khi cat top-N; "
                        "dung de tinh muc phu thuoc top khach, KHONG lay tong danh sach top-N lam mau so. "
                        "UU TIEN dung tool nay cho moi cau hoi ve khach hang mua nhieu nhat/top khach hang. "
                        "C11/S70 co concentration_by_month cho top khach, top SKU va mien. "
                        "C32/M21/V19 co monthly_customer_changes: top tang/giam RIENG tung thang, "
                        "dong gop vao bien dong tong va ma nguoi phu trach. Moi dong co mien (MB/MT/MN cua "
                        "khach): cau hoi KHONG gioi han vung thi BAT BUOC co cot Mien. Moi dong co san "
                        "customer_name va nv_ban_chinh (NV ghi tren hoa don co doanh thu lon nhat trong ky, kem "
                        "ty_trong_pct) - KHONG goi get_customer_detail chi de lay ten. Cap 3 'top khach cua TDV X/"
                        "doi QLV Y' -> employee_code (loc tu dau, ket qua co loc_theo).",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "So luong top can lay, mac dinh 10"},
                "area_code": {"type": "string", "enum": ["MB", "MT", "MN"], "description": "Loc DUNG mot mien khi nguoi dung hoi top cua mien do (vd top khach hang mien Trung -> MT); KHONG lay top toan quoc roi tu loc."},
                "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"], "description": "Kenh, mac dinh ALL"},
                "employee_code": {"type": "string", "description": "Ma HOAC TEN 1 nhan vien: TDV/CS/TK -> khach cua chinh nguoi do (theo hoa don); QLV -> khach cua ca doi. Khong dung cho TP/GD mien (dung area_code)."},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_revenue_by_region",
        "description": "Doanh thu theo vung mien (Mien Bac/Trung/Nam) trong 1 khoang ngay. "
                        "BAT BUOC dung tool nay cho MOI cau hoi ve doanh thu theo vung/mien/khu vuc - KE CA "
                        "KHI nguoi dung chi hoi 1 vung cu the (vd 'doanh thu mien Nam'): van goi tool nay "
                        "(no luon tra ve ca 3 vung) roi CHI trich/hien thi vung duoc hoi trong cau tra loi, "
                        "TUYET DOI KHONG tu viet SQL rieng voi dieu kien area_code=... vi se BO SOT khach "
                        "hang 'mo coi' (khong co ho so trong bang khach hang) ma CHI ham nay moi suy luan "
                        "dung vung qua tien to ma khach hang. "
                        "THAM SO 'channel' QUAN TRONG (28/07/2026, sua sau khi phat hien bao cao 'OTC 3 mien' "
                        "bi thoi phong ~4 lan neu quen loc): nguoi dung hoi RO RANG 'doanh thu OTC theo vung' "
                        "-> BAT BUOC truyen channel='OTC'; hoi 'ETC theo vung' -> channel='ETC'; hoi 'doanh "
                        "thu theo vung' CHUNG CHUNG (khong noi OTC/ETC) -> de channel mac dinh 'ALL' (gop ca "
                        "2 kenh). KHONG duoc de mac dinh 'ALL' roi tu tru/suy doan phan OTC - 1-2 khach ETC "
                        "(benh vien/thau) co the lon hon CA VUNG do cong lai, lam so bi sai nghiem trong. "
                        "CANH BAO NHAM LAN QUAN TRONG: 'Kenh MT' (Modern Trade - chuoi nha thuoc lon nhu "
                        "Long Chau, Pharmacity) LA 1 KENH BAN HANG (CHI thuoc OTC), HOAN TOAN KHAC voi ma vung "
                        "'MT'=Mien Trung (trung chu viet tat ngau nhien). Neu nguoi dung hoi 've doanh thu "
                        "Kenh MT/Modern Trade/MN1' thi VAN goi tool NAY (KHONG phai get_revenue_by_channel, "
                        "tool do chi biet OTC/ETC toan quoc khong tach vung) - dong ket qua cua Mien Nam se "
                        "co them truong 'channel_breakdown' (danh sach {name, revenue, plan_revenue, "
                        "achievement_pct}) chua san doanh thu, KE HOACH va % thuc hien Kenh MT da tach rieng "
                        "(SO NAY DA NAM SAN trong 'revenue' cua Mien Nam, KHONG duoc cong them) - lay so tu "
                        "day de tra loi; ke hoach chi co khi khoang hoi tron thang (xem plan_note). Hoi kenh MT "
                        "NHIEU THANG thi dung get_revenue_monthly_series (otc_special_channels tung thang).TUYET DOI KHONG tra loi 'he thong khong co "
                        "kenh MT' hay tu dong hieu nham sang doanh thu vung Mien Trung khi nguoi dung noi ro "
                        "la 'kenh'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "channel": {"type": "string", "description": "'ALL' (mac dinh, gop OTC+ETC), 'OTC', hoac 'ETC' - "
                                                               "PHAI truyen dung khi nguoi dung noi ro kenh, xem canh bao o description."},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_employee_kpi",
        "description": "KPI nhan vien tu snapshot gan nhat <= as_of_date. total_employees chi dem nguoi "
                        "co target de danh gia; roster_employees la so nguoi trong roster hop ky tron + ky moi. "
                        "unassessed_count/unassessed_rows la nguoi thieu snapshot/target ky dang hoi: PHAI noi ro "
                        "chua du du lieu, KHONG gan ho 0% hay khong dat KPI, KHONG lay target ky cu thay the. "
                        "Tra ve 3 muc do "
                        "rieng: count_full_target (dat chi tieu), count_kpi_achieved (dat KPI), "
                        "count_above_target/count_below_target (toi muc thuong nhom hang) - dinh nghia/nguong "
                        "day du cua 3 muc nay va y nghia mau status da co o system prompt, KHONG tu suy dien "
                        "lai o day. Snapshot giua thang chi la luy ke den ngay: KHONG duoc mac dinh % thap "
                        "la 'binh thuong vi dau thang'. Neu chua co ke hoach phan bo target theo ngay thi chi "
                        "neu muc thuc dat va noi chua du co so ket luan nhip do binh thuong/bat thuong. "
                        "PHAM VI CUA TOOL NAY CHI LA DOANH SO vs CHI TIEU. Cau hoi 'tinh hinh thuc hien KPI' "
                        "cua nguoi/doi con gom cac cau phan KHAC: thuong san pham danh muc, V15/V22, khach "
                        "hang ASO (hoac Active Customer cho CS/TK) va tong trong so KPI - nhung so do nam o "
                        "get_salary_achievement_summary (v15/v22/aso_achieved_count, is_ac_position_count) va "
                        "get_salary_aso_detail. Goi them cac tool do khi tai khoan duoc phep; neu khong lay "
                        "duoc thi PHAI liet ke ro cau phan nao chua co, khong duoc trinh bay doanh so vs chi "
                        "tieu nhu la toan bo KPI. V25 da dung tu 01/07/2026 nen V25Bonus=0 la dung co che. "
                        "UU TIEN dung cho MOI cau hoi ve KPI/doanh so nhan vien TONG QUAN/xep hang (ke ca ma "
                        "khu vuc MBKV*/ASM*) - KHONG dung cho KPI THEO NGAY 1 nguoi (dung get_employee_daily_kpi). "
                        "Voi cau hoi 'ai chua dat KPI/target' -> dung filter='below_target'. Neu nguoi dung hoi "
                        "DANH SACH/nhung ai duoi mot moc %, BAT BUOC limit=200 de tra du danh sach trong DUNG "
                        "mot lan; backend se nen cac cot can thiet truoc khi gui model, khong phan trang/goi lai. "
                        "Voi cau hoi chi dinh ro VAI TRO (vd 'top TDV', 'cac QLV chua dat KPI') -> BAT BUOC dung "
                        "tham so position_code (vd 'TDV','QLV') de loc NGAY TU DAU, TUYET DOI KHONG tu loc thu "
                        "cong ket qua sau khi nhan ve (da tung gay sot du lieu, vd 1 QLV lot vao top TDV). "
                        "11/09/2026 (Q013): voi cau hoi 'XEP HANG TOAN BO nhan vien' (khong gioi han vai tro/so "
                        "luong) -> goi DUNG 1 LAN voi limit=1000 (du lon hon tong so nhan vien thuc te, hien "
                        "~150-200 nguoi co target/ky) va order_by phu hop. TUYET DOI KHONG dung sql_tu_do de tu "
                        "phan trang nhieu vong (vd LIMIT 20 OFFSET 20, 40, 60...) - da tung gay 1 cau hoi phai "
                        "goi toi 10 vong SQL tu do rieng le va het thoi gian request (timeout) truoc khi tra loi "
                        "duoc, trong khi 1 lan goi tool nay voi limit=1000 chi mat duoi 1 giay va tra du. "
                        "11/09/2026 (M13): voi cau hoi 'QLV nao co nhieu NV DUOI KPI (80%) nhat' -> GOI DUNG 1 "
                        "LAN voi filter='below_target' hoac filter='all' roi doc san field below_kpi_by_manager "
                        "(da gop san so nguoi duoi 80% + danh sach ten theo tung QLV, xep giam dan) - TUYET DOI "
                        "KHONG tu goi lai get_workforce_productivity/get_revenue_tree nhieu lan voi month_to "
                        "khac nhau de tu dò (da tung gay timeout do dò 4-5 vong khong ra ket qua). "
                        "14/09/2026: hoi 'chi tiet [N] QLV'/'chi tiet QLV kem doi cua ho' (thuong sau mot cau "
                        "bao cao vung/mien) -> dat position_code='QLV' VA include_team_detail=true trong CUNG "
                        "1 lan goi; moi dong QLV co san team_detail (TDV bao cao truc tiep kem doanh so/target/%). "
                        "Dong co la_nhom_kenh=true (vd MN1 'Kenh MT', MN4 'Cho si') la NHOM/KENH, khong phai ca "
                        "nhan - goi dung la nhom/kenh. TUYET DOI KHONG tu viet SQL rieng cho tung QLV (da tung "
                        "mat 6-7 vong va hon 100 giay).",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "Tinh KPI luy ke den ngay nay, dinh dang YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "So luong nhan vien can lay trong danh sach ket qua, mac dinh 10"},
                "order_by": {"type": "string", "enum": ["sales", "pct"], "description": "Chi ap dung khi filter='all': xep hang theo doanh so tuyet doi hay % dat target, mac dinh sales"},
                "filter": {"type": "string", "enum": ["all", "below_target", "above_target"],
                           "description": "'all'=top N tot nhat (mac dinh), 'below_target'=CHUA toi muc huong thuong (te nhat truoc), 'above_target'=DA toi muc huong thuong (tot nhat truoc). Muc huong thuong lay THEO VAI TRO cua tung nguoi (TDV 65%, quan ly 70%). LUU Y day KHONG phai moc 'dat chi tieu' (=100%) - muon dem so nguoi dat chi tieu thi doc 'count_full_target' trong ket qua"},
                "position_code": {"type": "string", "description": "Loc theo vai tro cu the: TDV/QLV/CTV/CS/TP/PP/TBP/TK (khong bat buoc - de trong neu hoi chung tat ca vai tro). TP = Truong phong = Giam doc Mien = Giam doc Kenh (cap quan ly mien/kenh). TK = Truong kenh = Truong kenh MT (Modern Trade) - cap QLV, KHONG phai TP. CS = Cho si - cung cap QLV."},
                "include_team_detail": {"type": "boolean", "description": "true = voi position_code='QLV', moi dong co them team_detail (danh sach TDV/cap duoi truc tiep kem doanh so/target/%). Dung khi hoi 'chi tiet QLV kem doi cua ho', KHONG tu viet SQL rieng cho tung QLV."},
            },
            "required": ["as_of_date"],
        },
    },
    {
        "name": "get_employee_daily_kpi",
        "description": "KPI THEO NGAY cho 1 nhan vien BAN HANG CA NHAN - tuc TRINH DUOC VIEN (TDV), "
                        "ma co xuat hien truc tiep tren hoa don, vd 'TM25010199'. TUYET DOI KHONG dung "
                        "cho cap QUAN LY (QLV/TP/PP/TBP, vd 'tungtx', 'MBKV1', 'ASM*'): ma quan ly khong "
                        "nam tren hoa don nen ket qua se ra 0 dong MOI NGAY - do la THIEU DU LIEU, khong "
                        "phai ho ban duoc 0 dong. Voi cap quan ly PHAI dung get_employee_kpi (KPI thang) "
                        "hoac get_revenue_tree (doanh so ca doi). "
                        "Trong 1 thang. Target 1 ngay = 4% MonthSaleTarget cua nhan vien do "
                        "(4% = 100% cua ngay). Doanh so T7/CN nam o 'weekend_days' (khong co mau KPI "
                        "ngay nhung VAN la doanh so that, T7 ban nhieu nhat - khong duoc bo). "
                        "Ket qua co san 'days' (danh sach tung ngay T2-T6 trong thang, "
                        "moi ngay co 'status': 🔴 Do <2.5%, 🟡 Vang 2.5%-3.5%, 🟢 Xanh >3.5% - LUON dung "
                        "nguyen status nay, khong tu tinh nguong khac) va dem san count_red/count_yellow/"
                        "count_green. Co the truyen NHIEU ma TDV cach nhau bang dau phay de xem ca doi "
                        "trong 1 lan: ket qua bulk tra employees TOM TAT DU TUNG NGUOI (kem ngay 0/do/vang/xanh) "
                        "va team_days cua TOAN DOI; KHONG goi lai rieng tung nguoi. 'month_pct_of_target' la % TONG CA THANG (thuc te/target*100, cach "
                        "tinh CU, KHONG lien quan gi 4%/ngay va KHONG co mau) - chi dung khi hoi tong ket "
                        "cuoi thang. KHONG dung tool nay cho ma khu vuc/quan ly vung (MBKV*, ASM*, cac ma "
                        "khong xuat hien truc tiep tren hoa don) - truong hop do dung get_employee_kpi thay the.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_code": {"type": "string", "description": "Ma HOAC TEN TDV ban hang ca nhan, vd 'TM25010199' hoac 'Nguyen Van Danh' (KHONG dung ma quan ly QLV/TP/PP hay ma khu vuc). Truyen thang ten nguoi dung noi - KHONG duoc tra loi rang chi tra cuu duoc theo ma; neu ten trung nhieu nguoi, tool tra employee_candidates de hoi lai"},
                "year_month": {"type": "string", "description": "Thang can xem, dinh dang YYYY-MM"},
            },
            "required": ["employee_code", "year_month"],
        },
    },
    {
        "name": "compare_periods",
        "description": "Tra kem nguyen_nhan_bien_dong (theo mien, khach tang/giam manh nhat, khach phat sinh moi/khong con mua, SKU tang/giam manh nhat - tong khop chenh lech): BAT BUOC giai thich tang/giam bang cac khoan nay, khong chi neu con so tong (hop 24/09). So sanh nhanh tong doanh thu (OTC+ETC) giua 2 khoang thoi gian bat ky (vd thang nay vs "
                        "thang truoc, quy nay vs cung ky nam truoc). Tool tu kiem pham vi kho; neu mot ky thieu "
                        "du lieu thi comparison_valid=false va delta/pct_change=None. PHAI bao thieu lich su, "
                        "TUYET DOI khong coi ky thieu la 0 dong. UU TIEN dung tool nay cho so sanh dung 2 ky.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from_a": {"type": "string", "description": "YYYY-MM-DD, dau ky can xem (ky hien tai/moi)"},
                "date_to_a": {"type": "string", "description": "YYYY-MM-DD, cuoi ky can xem"},
                "date_from_b": {"type": "string", "description": "YYYY-MM-DD, dau ky doi chieu (ky truoc/cu)"},
                "date_to_b": {"type": "string", "description": "YYYY-MM-DD, cuoi ky doi chieu"},
            },
            "required": ["date_from_a", "date_to_a", "date_from_b", "date_to_b"],
        },
    },
    {
        "name": "get_revenue_ytd_cumulative",
        "description": "LUY KE doanh thu tu dau ky (mac dinh dau nam duong lich) den 1 thang chi dinh, SO "
                        "SANH TU DONG qua nhieu nam gan nhat trong CUNG 1 lan goi - dung cho cau hoi 'luy ke "
                        "tu dau nam den nay', 'tu thang 1 den thang 7 nam nay so voi cung ky 3 nam gan nhat', "
                        "'luy ke quy 1-2 nam nay tang/giam bao nhieu so nam ngoai'. KHAC voi compare_periods "
                        "(chi so 2 khoang RIENG LE do AI tu chi dinh ngay, de sai/lech khi phai tu tinh ngay "
                        "cho nhieu nam) - tool nay TU DONG dong bo cung khoang thang qua N nam lien tiep, UU "
                        "TIEN dung khi cau hoi noi 'luy ke' hoac so sanh HON 2 ky cung luc. Day la du lieu "
                        "THUC TE da phat sinh, nhung neu revenue_history_complete=false thi %KH/gap/binh quan "
                        "la None vi kho thieu lich su; PHAI noi ro, khong tu tinh bu.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year_month_to": {"type": "string", "description": "YYYY-MM, thang KET THUC luy ke (nam cua thang nay la nam gan nhat trong so sanh)"},
                "from_month": {"type": "string", "description": "MM, thang BAT DAU luy ke trong nam (mac dinh '01' = tu dau nam duong lich), ap dung chung cho moi nam"},
                "years_back": {"type": "integer", "description": "So nam gan nhat can so sanh ke ca nam cua year_month_to (mac dinh 3)"},
            },
            "required": ["year_month_to"],
        },
    },
    {
        "name": "get_revenue_monthly_series",
        "description": "CHUOI DOANH THU THEO TUNG THANG (moi thang mot dong) kem MoM va YoY tinh san - "
                        "BAT BUOC dung tool nay cho MOI cau hoi dang 'doanh thu 12 thang gan nhat', 'theo "
                        "tung thang', 'thang qua thang', 'xu huong may thang qua', 'thang nao tang/giam manh "
                        "nhat', 'trung binh truot 3/6 thang', 'bien dong doanh thu qua cac thang'. CHi CAN GOI "
                        "DUNG 1 LAN cho ca chuoi - TUYET DOI KHONG goi get_revenue_by_channel nhieu lan cho "
                        "tung thang (se an het han muc goi tool va van thieu MoM/YoY). C02/S02: moi thang "
                        "co `s02_otc_company` va `otc_by_region` gom actual, target OTC, % dat va chenh "
                        "lech rieng toan cong ty/MB/MT/MN. Actual va target deu lay snapshot moi nhat tung NV tu "
                        "FACT_ThongKeTinhLuong, chi TDV/CTV/CS/TK; `otc_region_reconciliation` bat buoc "
                        "khop tong ba mien voi tong OTC cong ty. Khong tu cong/gan lai target vung. "
                        "ETC theo mien: `etc_by_region` (doanh thu that, khop `etc_region_reconciliation`); nguon "
                        "KHONG co ke hoach ETC theo mien (`etc_plan_by_region`=None) - % ETC chi o cap cong ty, "
                        "KHONG goi them tool de tim. "
                        "Với QLV, neu "
                        "team_membership_basis.older_periods_use=CURRENT_TEAM_MEMBERSHIP thi BAT BUOC "
                        "ghi ro: 'tinh theo doi hien tai, thanh phan doi ky do co the khac'; KHONG mot "
                        "vai noi he thong khong tinh duoc con vai khac lai coi roster hien tai la roster lich su. KHAC get_revenue_by_"
                        "channel (chi 1 con so TONG cho ca khoang) va compare_periods (dung 2 khoang). Thang "
                        "Moi thang co san plan_revenue/achievement_pct/plan_variance khi target cung cap du; "
                        "ETC theo vung va doi QLV co the co plan=None kem plan_note vi nguon khong tach du cap. Thang "
                        "nao nam ngoai pham vi du lieu se co 'khong_co_du_lieu': true va revenue=None - PHAI "
                        "noi ro voi nguoi dung la thang do CHUA CO DU LIEU, TUYET DOI KHONG trinh bay thanh "
                        "0 dong va khong tinh vao trung binh/tang truong.",
        "input_schema": {
            "type": "object",
            "properties": {
                "month_to": {"type": "string", "description": "YYYY-MM, thang CUOI cua chuoi (mac dinh: thang co du lieu moi nhat)"},
                "months_back": {"type": "integer", "description": "So thang tra ve tinh ca month_to (mac dinh 12, toi da 24)"},
                "include_yoy": {"type": "boolean", "description": "Tu dong lay them 12 thang truoc de tinh YoY (mac dinh true)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_revenue_seasonality",
        "description": "C08/S80: Tinh mua vu doanh thu theo tung kenh (OTC, ETC) va theo thang duong lich (calendar month 1-12). "
                       "Tinh chi so mua vu (seasonal index = average revenue cua thang / average revenue chung), "
                       "xac dinh thang cao nhat/thap nhat, va do lech so voi mua vu. Danh dau ro trang thai du lieu "
                       "(READY neu co >=24 thang tron va du >=2 quan sat cho moi thang; INSUFFICIENT_HISTORY neu thieu). "
                       "Khong keo target/YoY/tach mien phuc tap nhu get_revenue_monthly_series, tranh timeout.",
        "input_schema": {
            "type": "object",
            "properties": {
                "month_to": {"type": "string", "description": "YYYY-MM, thang cuoi cua chuoi (mac dinh thang co du lieu moi nhat)"},
                "months_back": {"type": "integer", "description": "So thang tra ve (mac dinh 24, toi da 24)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_customer_lifecycle_summary",
        "description": "DEM SO KHACH HANG theo cac co vong doi cua Bravo theo TUNG THANG (khach moi "
                        "trong thang, va 2 co is_ro/is_ac) tu snapshot KPI - dung cho 'thang nay co bao "
                        "nhieu khach mo moi', 'so khach moi tung thang', 'khach moi dong gop bao nhieu "
                        "doanh thu'. BAT BUOC: khi tra loi PHAI doc va nhac lai truong 'canh_bao_dinh_"
                        "nghia'. DNH xac nhan 26/08/2026: NC = New Customer, RO = Re-Order (dat lai "
                        "hang), AC = Active Customer. is_nc va is_ro dung on dinh, goi thang la 'khach "
                        "moi' / 'khach dat lai hang'. RIENG is_ac: DNH chot 27/08/2026 la co Active Customer "
                        "danh cho CS (Cho si) va TK (kenh MT/Modern Trade), KHONG phai ASO. Dong da co is_ac "
                        "thi khong duoc gan hoac cong them ASO; bao cao luong CS/TK dung active customer, "
                        "cac vai tro khac moi dung ASO khi nguon co ghi nhan. Khong dung con so is_ac de ket "
                        "luan toan bo khach dang hoat dong; moi dong thang da co san "
                        "khach_co_hoa_don_trong_thang (dem tu hoa don) - dung DUNG truong do khi nguoi "
                        "dung hoi 'bao nhieu khach dang hoat dong / con mua'. "
                        "khach_moi da bao gom ca khach do chinh QLV ban truc tiep (khong qua TDV); phan "
                        "do tach rieng o khach_moi_do_qlv_ban_truc_tiep de giai thich chenh lech, KHONG "
                        "duoc tru ra. "
                        "Con ~8-10% khach khong mang co nao van co doanh thu, KHONG duoc coi la 'khong "
                        "mua'. Neu nguoi dung hoi ve khach NGUNG MUA thi dung "
                        "get_customers_silent (dua tren hoa don that, chac chan hon). Nguon nay hien "
                        "CHI phu kenh OTC; voi tai khoan ETC tool se tra not_applicable, KHONG duoc "
                        "trinh bay so OTC nhu so cua ETC. C29: moi thang co khoi theo_vung (MB/MT/MN, moi khach "
                        "thuoc dung mot vung) - BAT BUOC trinh bay them bang theo vung cho thang tron gan "
                        "nhat, ke ca khi cau hoi khong noi 'vung' (cham lai UAT 24/09 muc 14 truot vi bo "
                        "qua khoi nay). C29: invoice_lifecycle_series tra rieng so "
                        "khach co hoa don duong, lien tuc, tai kich hoat, ngung mua va first-observed "
                        "tung thang. Day la PHAN LOAI TU HOA DON, khac co NC/RO; khong doi continuing "
                        "thanh Re-Order, khong coi first-observed la khach moi trong doi. VOI C29, ca bang "
                        "hanh vi va bang co Bravo deu cung pham vi OTC: TUYET DOI KHONG lay them so "
                        "OTC+ETC tu get_customer_movement, khong tu tinh 'khach dang mua' bang tong tru "
                        "ngung mua. Kho chi giu khoang 90 ngay snapshot, neu ket "
                        "qua co canh_bao_thieu_lich_su thi PHAI noi ro, KHONG coi thang thieu la 0 khach.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year_month": {"type": "string", "description": "YYYY-MM, thang cuoi (mac dinh: thang co snapshot moi nhat)"},
                "months_back": {"type": "integer", "description": "So thang tra ve tinh ca thang cuoi (mac dinh 1, toi da 12)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_customers_silent",
        "description": "DANH SACH KHACH DA NGUNG MUA / IM LANG: khach TUNG mua nhung lan mua gan nhat "
                        "da cach day >= silent_days. Dung cho 'khach nao ngung mua', 'khach im lang 30/60/"
                        "90 ngay', 'khach thang truoc co mua ma thang nay khong thay', 'khach lon nao dang "
                        "mat dan', 'doanh thu co nguy co mat vi khach bo di'. Dua tren LICH SU HOA DON "
                        "THAT (lan mua cuoi + doanh thu ky nhin lai) nen chac chan hon get_customer_"
                        "lifecycle_summary (dem theo co Bravo chua xac nhan nghia). Sap xep theo doanh thu "
                        "ky truoc giam dan - khach mat nhieu tien nhat len dau. V21/S69b: co HAI con so "
                        "doanh thu, goi dung ten: doanh_thu_ky_nhin_lai (ky co dinh tinh den hom nay) va "
                        "sau_thang_truoc_khi_ngung (6 thang lich tinh den THANG MUA CUOI cua chinh khach - "
                        "dung khi hoi truoc khi ngung ho mua bao nhieu). BAT BUOC doc "
                        "total_count de ket luan tren toan bo tap; neu bang chi tiet dai thi chi neu cac "
                        "muc uu tien va ghi mot dong 'Dang liet ke N/T khach', khong noi ve gioi han ky thuat. "
                        "Moi khach co nhom_im_lang va san_pham_mua_nhieu_nhat. Neu san pham co status hoac "
                        "product_name_status=not_available thi chi noi thieu thong tin san pham, KHONG loai "
                        "khach va KHONG suy dien ten SKU. Ky san pham mua nhieu nhat la ky_san_pham "
                        "12 thang, KHAC ky_nhin_lai 6 thang cua doanh_thu_ky_nhin_lai. Khi noi "
                        "'san pham mua nhieu nhat', BAT BUOC ghi ro ky_san_pham.tu/den tu payload, "
                        "khong gan nham vao ky doanh thu. Kho local chi giu chi tiet hoa don ~12 thang gan "
                        "nhat, PHAI noi ro gioi han nay neu nguoi dung hoi xa hon.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, moc tinh im lang (mac dinh: ngay du lieu moi nhat)"},
                "silent_days": {"type": "integer", "description": "So ngay khong mua toi thieu de bi liet ke (mac dinh 60)"},
                "lookback_months": {"type": "integer", "description": "Cua so nhin lai de tinh doanh thu 'tung mua' (mac dinh 6 thang)"},
                "limit": {"type": "integer", "description": "So khach tra ve (mac dinh 50, toi da 200)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_customer_attrition_risk",
        "description": "KHACH LON NGUNG MUA / GIAM MUA MANH / KEO DAI CHU KY MUA - ba tin hieu trong "
                       "MOT bang theo checker S88. BAT BUOC dung cho M22 'khach lon nao ngung mua, "
                       "giam mua hoac keo dai chu ky mua so voi lich su'. KHONG dung "
                       "get_customer_movement cho cau nay: tool do chi so thang nay voi thang lien "
                       "truoc va khong co khoang cach mua trung binh nen KHONG tra loi duoc ve "
                       "'keo dai chu ky'. Bon nhan trong tin_hieu: NGUNG_MUA, NGUNG_MUA_DA_LAU, "
                       "GIAM_MUA, KEO_DAI_CHU_KY - moi khach chi mang MOT nhan, khong cong don. "
                       "'Khach lon' la nua tren cua tap khach theo doanh thu cua so: doanh thu >= "
                       "trung vi trong DUNG pham vi vung/kenh/doi cua tai khoan. NGUNG_MUA chi gom "
                       "khach co mua it nhat 2/3 thang truoc; khach chi mua 1/3 thang khong duoc gan "
                       "nhan nay. GIAM_MUA so voi binh quan cac thang co ban ghi trong 3 thang truoc. "
                       "PHAI trinh bay du ca ba ve nguoi dung hoi; neu chi neu khach ngung han va bo "
                       "hai nhom con lai thi cau tra loi CHUA DAT. BAT BUOC doc phan_bo_tin_hieu de "
                       "noi so khach tung nhom, va doc total_count de ket luan tren toan bo tap. Neu "
                       "bang chi tiet dai thi chi neu cac muc uu tien va ghi 'Dang liet ke N/T khach'; khong noi "
                       "ve gioi han ky thuat. Neu ky_chua_tron=true thi KHONG duoc ket luan khach da ngung mua - "
                       "phai noi ro thang chua tron va dan ve thang tron gan nhat. "
                       "chu_ky_chua_do_duoc=true nghia la khach co duoi 3 ngay mua nen chua do duoc "
                       "chu ky, KHONG duoc goi la keo dai chu ky. BAT BUOC doc gioi_han va noi ro "
                       "day la tin hieu canh bao tu hoa don, khong phai ket luan khach da bo hang; "
                       "tap nay KHONG co du lieu nguyen nhan nen KHONG duoc suy dien ly do.",
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "YYYY-MM, ky can danh gia (mac dinh: thang TRON gan nhat, khong lay thang dang chay dang do)"},
                "lookback_months": {"type": "integer", "description": "Cua so lich su de tinh chu ky mua (mac dinh 12, toi thieu 4, toi da 24)"},
                "limit": {"type": "integer", "description": "So khach tra ve (mac dinh 200, toi da 200)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_customer_cohort_retention",
        "description": "COHORT GIU CHAN khach theo thang co hoa don dau tien QUAN SAT DUOC, tinh ty "
                       "le con mua o tuoi 1/3/6/12 thang. BAT BUOC dung cho cau hoi 'giu chan cohort', "
                       "'khach mo moi sau 3/6/12 thang con mua bao nhieu'. Co the tach overall/channel/"
                       "area. C30/S19: BAT BUOC bo qua cohort co valid_new_customer_cohort=false khi "
                       "ket luan ty le giu chan; left_censored_cohort_months la cac cohort o bien lich su, "
                       "chi duoc neu nhu so quan sat tham khao. first observed KHONG chac la lan mua dau "
                       "tien trong doi; ky co ky_da_du=false tra None, KHONG coi la 0% - xet theo "
                       "latest_complete_month (thang TRON gan nhat, khong phai thang hien tai neu thang "
                       "do moi la MTD) nen thang vua qua CHUA CO du lieu se luon la None chu khong phai "
                       "0%. M23/S67: cau 'tung vung ... ty le giu chan sau 3/6 thang' PHAI truyen "
                       "group_by='area' va age_months=[3,6], VA goi them "
                       "get_customer_lifecycle_summary de lay khoi theo_vung cho ve dau cua cau hoi - "
                       "thieu mot trong hai la tra loi nua cau. Cua so cohort tu noi rong de tuoi lon "
                       "nhat co so that; neu cohort_from_da_mo_rong=true thi neu ly_do_mo_rong_cua_so. "
                       "C30 'thang mo moi': cohort_theo_isnc dem khach co IsNC - DUNG so khach moi cua "
                       "C29/M24 - phai trinh bay cho cac thang co snapshot, kem "
                       "doi_chieu_hai_dinh_nghia_khach_moi; tuoi 3/6/12 chi co o bang cohort hoa don va "
                       "phai noi ro do la dinh nghia khac. Gia tri *_tam_tinh chi la so den ngay du lieu "
                       "cua thang dang chay, phai ghi 'tam tinh'. "
                       "DNH van can chot dinh nghia 'khach mo moi' truoc khi dung lam KPI chinh thuc.",
        "input_schema": {"type": "object", "properties": {
            "month_to": {"type": "string", "description": "YYYY-MM, thang cohort cuoi."},
            "months_back": {"type": "integer", "description": "So thang cohort, mac dinh 6, toi da 24."},
            "age_months": {"type": "array", "items": {"type": "integer"}, "description": "Cac tuoi can do, vd [1,3,6,12]."},
            "group_by": {"type": "string", "enum": ["overall", "channel", "area"]},
        }, "required": []},
    },
    {
        "name": "get_customer_movement",
        "description": "LUONG KHACH giua thang dang xem va thang truoc: NEW_OR_FIRST_OBSERVED, "
                       "REACTIVATED, STOPPED, GROWING, DECLINING; kem doanh thu, delta, so don, co don "
                       "lap lai va NV phu trach. BAT BUOC dung cho khach moi co lap don, tai kich hoat, "
                       "khach ngung/tang/giam va doanh thu them-mat. NEW_OR_FIRST_OBSERVED chi la lan dau "
                       "thay trong cua so kho, KHONG tu goi chac chan la khach moi trong doi. RIENG C31 "
                       "'khach moi va tai kich hoat bu doanh thu khach ngung mua': backend tu ep cua so "
                       "quan sat 24 thang de khop S90; khong dung dinh nghia nay cho V15/V23. Khi hoi "
                       "tong doanh thu them/mat hay ty le bu doanh thu, BAT BUOC dung "
                       "summary_all_customers; summary_on_returned_top_rows chi la top-N de minh hoa. "
                       "C31: added_revenue = new_or_first_observed_revenue + reactivated_revenue; "
                       "ty le bu dap la compensation_pct_of_lost_revenue = added_revenue / "
                       "lost_previous_revenue * 100. BAT BUOC tinh ca khach tai kich hoat trong ve "
                       "tang them; khong chi lay khach mua lan dau. "
                       "V15/S61b: SO KHACH THEO TUNG TDV phai lay o by_employee (tinh tren toan bo tap "
                       "khach, quy khach cho nguoi ban nhieu nhat trong chinh thang do) - TUYET DOI khong "
                       "tu dem tren danh sach customers da cat top-N. "
                       "V22 'khach moi da co don lap lai chua': cau tra loi nam san o by_employee - "
                       "khach_moi_co_mua_lai va ty_le_mua_lai_khach_moi_pct, tinh tren TOAN BO khach moi "
                       "chu khong phai mau. KHONG duoc tra cung tung khach roi ket luan tren vai dong "
                       "rui tham, va KHONG duoc noi la chua kiem chung du. first_purchase_month la thang mua "
                       "dau tien that; khach da tung mua truoc do luon la REACTIVATED, khong duoc goi la "
                       "khach mo moi. V23: voi dong REACTIVATED, dung cac truong pre_stop_* va recovery_* "
                       "de so doanh thu thang quay lai voi binh quan CHUOI THANG LIEN TIEP co mua ngay "
                       "truoc ky nghi (da gom ca phan ngoai cua so hien thi). C20/M08: summary_all_customers da tach san new_or_first_observed_revenue, "
                       "reactivated_revenue, lost_previous_revenue va like_for_like_*; dung cac so nay, "
                       "KHONG tu phan loai lai hay de mot khoan chua phan loai. "
                       "10/09/2026: KHONG duoc goi tool nay THEM vao cung cau tra loi da dung "
                       "get_customer_lifecycle_summary cho C29 (khach hoat dong/moi/mua lai/tai kich "
                       "hoat/ngung mua tung thang) - hai tool dinh nghia khach moi KHAC HAN nhau (tool "
                       "nay tu suy tu hoa don, con lifecycle_summary dung dung co he thong IsNC da xac "
                       "nhan UAT), gop ca hai vao 1 cau tra loi se dua ra 2 con so khach moi khac nhau "
                       "cho CUNG 1 thang gay nham lan nghiem trong (da bat qua kiem thu thuc te: 612 vs "
                       "441 cho thang 8/2026). Neu cau hoi da khop dung C29, CHI dung "
                       "get_customer_lifecycle_summary, KHONG goi tool nay bo sung.",
        "input_schema": {"type": "object", "properties": {
            "month": {"type": "string", "description": "YYYY-MM."},
            "history_months": {"type": "integer", "description": "Cua so nhan biet tai kich hoat, mac dinh 12."},
            "movement_filter": {"type": "string", "enum": ["all", "NEW_OR_FIRST_OBSERVED", "REACTIVATED", "STOPPED", "GROWING", "DECLINING"]},
            "limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_kpi_gap_run_rate",
        "description": "GAP den 65/70/80/100/120% target va so tien can ban moi ngay con lai, theo "
                       "nhan vien/QLV/vung/tong. Co linear_run_rate tinh san. BAT BUOC dung cho 'con thieu "
                       "bao nhieu', 'moi ngay can ban bao nhieu', 'nhiep hien tai'. Day CHI la ngoai suy "
                       "tuyen tinh, KHONG phai forecast/xac suat; PHAI noi ro dieu nay. Nguon KPI chi phu OTC. "
                       "V03: nhip_theo_ngay co daily (MOI ngay lich ke ca T7/CN, revenue/invoices/thu), weekly, "
                       "ngay_khong_phat_sinh_t2_t7, chu_nhat_khong_phat_sinh va HAI nhip can thiet (ngay lich va "
                       "ngay ban T2-T7) - DNH chua chot dung nhip nao nen trinh bay ca hai. KHONG bo doanh so T7.",
        "input_schema": {"type": "object", "properties": {
            "as_of_date": {"type": "string", "description": "YYYY-MM-DD."},
            "group_by": {"type": "string", "enum": ["employee", "qlv", "area", "total"]},
            "limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_cross_sell_opportunities",
        "description": "CAP SKU thuong mua cung theo SO KHACH CHUNG (khong phai so don) va danh sach khach da mua A nhung chua mua B trong "
                       "cua so 1-12 thang. Moi cap co shared_customers, buyers_a/b va attach_rate_pct; cap va khach la HAI bang rieng. "
                       "Nguong mac dinh 5 khach chung la DE XUAT, can DNH chot. Dung cho ban cheo/combo/share-of-wallet noi bo. Ket qua chi "
                       "la GOI Y tu dong mua kem, KHONG phai ket luan nhu cau hay thi phan ngoai DNH.",
        "input_schema": {"type": "object", "properties": {
            "as_of_date": {"type": "string"}, "lookback_months": {"type": "integer"},
            "min_together_orders": {"type": "integer", "description": "Ten cu tuong thich API; gia tri la so KHACH CHUNG toi thieu, khong phai so don."}, "pair_limit": {"type": "integer"},
            "opportunity_limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_customer_product_coverage",
        "description": "DO PHU/BENCHMARK NOI BO theo khach, san pham hoac nhan vien: doanh thu, don, "
                       "so SKU, so khach, san luong, AOV, tan suat va chenh lech voi ky truoc. BAT BUOC "
                       "Voi cau V10/S84 'uu tien khach hang, san pham va nhan vien de dong gap', dung "
                       "mode='priority': tool tra rieng customer_actions/product_actions/employee_actions "
                       "va rows tong hop; gap KH/SP la binh quan 3 thang tron truoc tru MTD, gap NV la target-actual. "
                       "dung mode='employee', lookback_months=1 cho cau hoi DOI den tu bao nhieu khach/don, "
                       "AOV/tan suat thay doi, hoac NV nao dong gop tang/giam. Ket qua scope_totals da dem "
                       "KHACH DUY NHAT cua ca doi; KHONG cong so khach tung TDV. Ky 1 thang duoc can theo "
                       "cung ngay trong thang truoc (01-04/09 vs 01-04/08), va rows GIU CA nhan vien ky "
                       "hien tai bang 0 - khong duoc bo qua. largest_increase/largest_decrease da tinh san. Dung cho khach "
                       "mua it SKU, tan suat/AOV giam, NV co nhieu khach nhung mua thap, san pham nhieu "
                       "khach nhung luong/don thap. V24: dung mode='customer', lookback_months=3 de xem "
                       "tung khach giam don/AOV/SKU so voi cua so 3 thang lien truoc. V26: dung "
                       "mode='customer_peer', lookback_months=3; benchmark hien chi theo CUNG TINH, "
                       "vi kho chua co phan khuc khach hang chot chuan - phai noi ro gioi han nay. "
                       "M25-M26/S89: mode='customer_revenue_tier_peer' benchmark cung kenh x mien x "
                       "bac doanh thu NTILE(5), chi nhom >=5 khach; day la do rong danh muc noi bo, "
                       "khong phai share-of-wallet thi truong hay bang chung nhu cau. "
                       "C26/S16: mode='dual_channel' tra tung thang so khach mua ca OTC+ETC va "
                       "ty trong doanh thu; debt_status/debt_limitation la gioi han cong no bat buoc neu. "
                       "Benchmark chi trong DUNG pham vi tai khoan, KHONG "
                       "phai market share/share-of-wallet ngoai DNH va KHONG tu ket luan nhu cau. Voi "
                       "mode='product', dung net_revenue_per_paid_unit va truong previous/delta/pct de "
                       "phan tich xoi mon gia; day la doanh thu thuan tren don vi ban co gia, khong phai bang gia niem yet. "
                       "M33/S72: largest_revenue_declines da sap theo muc mat doanh thu va "
                       "primary_decline_driver tach FEWER_CUSTOMERS/FEWER_ORDERS/"
                       "LOWER_PAID_QUANTITY_PER_ORDER/LOWER_NET_REVENUE_PER_PAID_UNIT; khong tu suy "
                       "nguyen nhan tu mot cot doanh thu. M33 khong neu ky thi backend ep ky cua S72: "
                       "THANG TRON gan nhat so tron thang truoc (as_of_date=ngay cuoi thang tron, "
                       "lookback_months=1); cau tra loi phai neu ro hai ky current_period/previous_period. "
                       "C33/C36: dung largest_revenue_increases, "
                       "largest_internal_share_losses, coverage_up_revenue_per_customer_down va "
                       "revenue_up_coverage_down da tinh tren tap day du truoc khi cat limit. "
                       "C28/S91: mode='assignment_change' tach khach giu nguyen NV chinh, doi NV, moi va "
                       "roi bo tren OTC; day la ket qua PARTIAL vi khong co lich su assignment dia ban chot chuan. "
                       "C34/M34/S22: BAT BUOC mode='product_first_observed', lookback_months=24. "
                       "first_observed_sale_month KHONG phai ngay ra mat; chi xep hang va so sanh dong co "
                       "valid_for_launch_age_analysis=true. Thang hien tai CHUA TRON bi loai khoi cua so "
                       "de doanh thu thang dau luon cua mot thang tron. Kho chua co master launch date va target SKU, "
                       "nen KHONG tinh % ke hoach va phai noi ro gioi han.",
        "input_schema": {"type": "object", "properties": {
            "as_of_date": {"type": "string"}, "lookback_months": {"type": "integer"},
            "mode": {"type": "string", "enum": ["customer", "customer_peer", "customer_revenue_tier_peer", "product", "employee", "employee_assignment", "priority", "dual_channel", "four_customer_priorities", "product_monthly", "product_mix", "sku_target", "product_first_observed", "assignment_change"],
                     "description": "C26/S16: dual_channel (khach mua ca OTC+ETC theo thang, cong no fail-closed). V14/S44: employee_assignment (mau so la khach duoc phan cong hien tai, khong phai chi khach da mua). V28/S83: four_customer_priorities (4 danh sach giu khach/tai kich hoat/thu no/ban cheo). V29/S21: product_monthly (top/bottom SKU tung thang va dong gop MoM). V30/S46: sku_target (kiem tra target theo SKU; bao lo nguon, khong tu suy dien %). C34/M34/S22: product_first_observed (moc ban dau quan sat, khong phai launch date; khong co target SKU). V31/S23: product_mix (nhieu khach-luong/don thap va it khach-AOV cao). C28/S91: assignment_change (tach nhom giu/doi NV; chi OTC, co canh bao gioi han nguon)."},
            "limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_geography_monthly_performance",
        "description": "HIEU SUAT THEO THANG: doanh thu, don, KHACH DUY NHAT, san luong ban that, AOV, "
                       "tan suat don/khach, MoM, ty trong, thu hang "
                       "va streak tang/giam theo MIEN hoac TINH. Dung cho xep hang/diem keo giam/co hoi "
                       "dia ban; voi tai khoan QLV, dimension='area' + months_back=3 cung tra dung chuoi "
                       "3 thang cua RIENG DOI da bi ep scope, nen BAT BUOC dung cho cau 'so 3 thang gan "
                       "nhat doi giam o khach/don/san luong/AOV'. "
                       "Neu nguoi dung hoi 'thang nay', de month_to trong de tool lay thang du lieu moi nhat; "
                       "khong tu thay bang thang da tron truoc do. Neu month_to_is_partial=true, 'thang nay' CHI co du lieu MTD den month_to_data_through: "
                       "khong duoc am tham thay bang thang truoc hay so sanh voi thang tron. Neu "
                       "team_scope_reconciliation_warning co mat, khong duoc tron doanh thu KPI voi so don/AOV "
                       "hoa don thanh mot bo so. Kho KHONG co target theo tinh/dia ban hay mapping TDV phu trach "
                       "dia ban chot chuan; voi cau tinh nao duoi KH/phan hut/TDV phu trach, phai noi ro phan nay "
                       "chua the kiem chung, chi bao doanh thu/khach/don thuc co. "
                       "dia ban, ke ca cau hoi dang 'dia ban QUY MO LON nhung TANG TRUONG THAP' "
                       "(doi chieu cot revenue/ty trong voi cot MoM - KHONG can viet SQL tay). Kho local CHUA co khoa chi nhanh/NPP/distributor; neu hoi chieu do tool "
                       "tra not_applicable, PHAI noi ro, KHONG tu suy tu tinh/vung. C44/M42 ve hop "
                       "dong/goi thau ETC phai dung get_etc_contract_status, KHONG noi hoa don bang customer+SKU. "
                       "11/09/2026 (C24/M27): voi dimension='city', moi dong da co san "
                       "area_avg_revenue_per_city/area_avg_customers_per_city/area_avg_revenue_per_customer "
                       "(trung binh cac tinh CUNG VUNG, cung thang) va 2 co bool "
                       "below_area_avg_customers/below_area_avg_revenue_per_customer - dung TRUC TIEP cac "
                       "field nay cho cau hoi 'tinh nao co do phu/doanh thu-khach thap hon CHUAN MIEN/dia "
                       "ban tuong dong'. TUYET DOI KHONG tu viet SQL tu do de tinh trung binh vung, KHONG "
                       "goi lai tool nhieu lan voi dimension/months_back khac nhau de dò.",
        "input_schema": {"type": "object", "properties": {
            "month_to": {"type": "string"}, "months_back": {"type": "integer"},
            "dimension": {"type": "string", "enum": ["area", "city", "branch", "npp", "distributor"]},
            "limit": {"type": "integer", "description": "So DIA BAN giu lai (khong phai so dong): "
                       "giu top N dia ban theo tong doanh thu ca cua so, KEM DU MOI THANG cua chung. "
                       "Truong so_dia_ban_khong_hien cho biet con bao nhieu dia ban khong hien."},
        }, "required": []},
    },
    {
        "name": "get_workforce_productivity",
        "description": "NANG SUAT DOI NGU theo thang: headcount TDV/CTV/CS, doanh so, target, doanh "
                       "thu/nhan vien, MoM va streak giam theo nhan vien/QLV/vung/tong. Dung cho span of "
                       "control, headcount tang nhung nang suat giam, ai/doi giam lien tiep. Chua co lich "
                       "su vao-ra-chuyen vung chot chuan nen KHONG ket luan nhan qua tu bien dong headcount. "
                       "C46: cau hoi 'don vi nao tang headcount nhung nang suat giam' - BAT BUOC dung dung "
                       "1 lan goi voi group_by='manager' (hoac 'area' neu hoi theo vung), months_back>=3, "
                       "roi doc thang headcount_up_productivity_down (da tinh san tren TOAN BO nhom, khong "
                       "bi cat theo limit) - KHONG duoc tu goi lai nhieu lan voi group_by/months_back khac "
                       "nhau de tu do tim, se het ngan sach thoi gian truoc khi tra loi duoc. "
                       "M16/S55 va V13: khi hoi NHAN VIEN giam lien tiep, BAT BUOC goi group_by='employee', "
                       "months_back>=6, limit=200. BAT BUOC noi tong so tu declining_employee_count va dung "
                       "declining_employees de liet ke; neu danh sach dai thi neu cac muc uu tien va ghi "
                       "'Dang liet ke N/T nguoi', khong noi ve gioi han ky thuat. 'Giam lien tiep N thang' = decline_streak_months >= N: "
                       "bao so dung N tu declining_count_by_streak, KHONG gop nhom >=2 thanh 'giam 3 thang'. "
                       "CHI duoc noi 'duy nhat' khi count=1 (dem theo dung N). Nguyen nhan: doc cause tung "
                       "nguoi (khach, don/khach, AOV, yeu_to_giam_manh_nhat); cause=None thi KHONG duoc tu "
                       "suy dien mat khach, giam tan suat hay AOV, ma phai noi chua du bang chung. "
                       "C49/S34: khi hoi di tuyen/vieng tham/phu tuyen/ty le co don sau tham, BAT BUOC truyen "
                       "mode='route_visits'. Che do nay doc DMS_DiTuyen OTC theo ky hoi, tra luot vieng, khach "
                       "duoc vieng, % theo tuyen, % co don cung ngay (CAN DUOI) va doanh thu/luot vieng.",
        "input_schema": {"type": "object", "properties": {
            "month_to": {"type": "string"}, "months_back": {"type": "integer"},
            "mode": {"type": "string", "enum": ["productivity", "route_visits"],
                     "description": "productivity (mac dinh) hoac route_visits cho C49/S34."},
            "group_by": {"type": "string", "enum": ["employee", "manager", "area", "total"]},
            "limit": {"type": "integer", "description": "So NHOM giu lai (khong phai so dong): giu "
                       "top N nhom theo tong doanh so ca cua so, KEM DU MOI THANG cua chung. Truong "
                       "so_nhom_khong_hien cho biet con bao nhieu nhom khong hien."},
        }, "required": []},
    },
    {
        "name": "get_etc_contract_status",
        "description": "HOP DONG/GOI THAU ETC: gia tri hop dong, da xuat hoa don, con lai, ty le thuc "
                       "hien, hop dong sap het han va hop dong chua xuat hoa don nao. BAT BUOC dung cho "
                       "C43/C44/M42 - moi cau hoi ve hop dong, goi thau, gia tri chua giai ngan, tien do "
                       "thuc hien hop dong ETC. Nguon: vHopDongETC noi vHoaDonETCTotal.ContractId (do "
                       "13/09/2026: ContractId co tren 100% dong hoa don ETC, khop 1.037/1.037 hop dong). "
                       "CAC HOP DONG CO GIA TRI BAT THUONG da duoc tach rieng khoi moi con so tong "
                       "(so_hop_dong_gia_tri_bat_thuong / hop_dong_gia_tri_bat_thuong) - PHAI noi ro dieu "
                       "nay khi bao tong gia tri, khong duoc cong chung vao. Gia tri con lai la chua "
                       "xuat hoa don, KHONG phai chua giai ngan/thanh toan. Dung hop_dong_con_lai_lon_nhat "
                       "cho ve con gia tri lon; duoi 50% chi la chi bao, chua chung minh cham lich giao. "
                       "PHAI neu cong_no_theo_hop_dong: chua kiem chung no qua han theo hop dong, NULL "
                       "khong phai 0; cam gan no cua khach cho tung hop dong. So dem la tong day du, "
                       "danh sach bi gioi han va cac nhom co the chong lan.",
        "input_schema": {"type": "object", "properties": {
            "as_of_date": {"type": "string", "description": "YYYY-MM-DD; mac dinh ngay du lieu moi nhat."},
            "expiring_days": {"type": "integer", "description": "Nguong 'sap het han', mac dinh 90 ngay."},
            "only_active": {"type": "boolean", "description": "Chi xet hop dong con hieu luc (mac dinh true)."},
            "min_remaining_value": {"type": "number", "minimum": 0,
                                    "description": "Nguong gia tri con lai VND do nguoi dung yeu cau; "
                                                   "bo trong thi xep giam dan gia tri duong, khong tu dat nguong."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, "required": []},
    },
    {
        "name": "get_inventory_item_stock",
        "description": "SO LUONG TON KHO cua MOT san pham/nhom san pham tim theo TEN hoac MA (khong phan biet "
                       "hoa thuong, dau tieng Viet): ton kho kinh doanh theo tung kho va ton kho san xuat, nam "
                       "moi nhat, kem don vi tinh. BAT BUOC dung khi hoi ton kho cua san pham cu the (vd 'ton kho "
                       "bo phe'). Truyen item_search = ten/ma san pham nguoi dung hoi. KHONG cong so luong giua "
                       "cac ma khac don vi tinh; khong co ban ghi ton KHONG phai la ton bang 0.",
        "input_schema": {"type": "object", "properties": {
            "item_search": {"type": "string", "description": "Ten hoac ma san pham, vd 'bo phe'."},
            "area_code": {"type": "string", "enum": ["MB", "MT", "MN"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, "required": ["item_search"]},
    },
    {
        "name": "get_new_customer_list",
        "description": "DANH SACH KHACH HANG MOI trong thang (co IsNC cua Bravo) kem NGAY GHI NHAN (NCSaveDate - "
                       "ngay hoa don dau tien), doanh so thang, TDV va QLV phu trach (ma kem ten). BAT BUOC "
                       "dung khi hoi danh sach khach moi / ngay ghi nhan khach moi. Lay snapshot moi nhat cua "
                       "TUNG nhan vien trong thang. Khong dung ngay snapshot lam ngay ghi nhan. Chi kenh OTC. "
                       "M24 'mo nhieu khach moi nhung DT/khach va ty le mua lai thap': dung mode=quality. "
                       "Doc by_employee/by_area/tong_khach_moi_duy_nhat: IsNC tren BAT KY dong nao cua khach "
                       "(dong TDV hoac rollup QLV), DT Amount_CT, mua lai >1 OrderKey trong thang; "
                       "KHONG dung get_customer_movement hay dem lai tu danh sach da cat. "
                       "Khach moi KPI khac lan dau mua quan sat tren hoa don; KHONG them nhan vien ETC. "
                       "Neu co error thi chua danh gia duoc, khong ket luan 0 khach.",
        "input_schema": {"type": "object", "properties": {
            "year_month": {"type": "string", "description": "YYYY-MM; mac dinh thang co snapshot moi nhat."},
            "mode": {"type": "string", "enum": ["list", "quality"],
                     "description": "quality cho M24: so khach moi, DT/khach va mua lai theo TDV/mien; list cho danh sach khach."},
            "manager_code": {"type": "string", "description": "Ma QLV khi cau hoi gioi han MOT DOI (vd 'doi qlv "
                                                               "TM23100148'). BAT BUOC truyen thay vi tu loc tren "
                                                               "danh sach toan cong ty. Tai khoan QLV bi ep doi cua "
                                                               "chinh ho, tham so nay bi bo qua."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000}}, "required": []},
    },
    {
        "name": "get_reorder_pending_customers",
        "description": "DANH SACH KHACH PHAT SINH trong cua so tai don (ROMonth, thuong 3 thang) nhung CHUA TAI "
                       "DON trong thang (chua duoc tinh vao KPI khach tai don), kem lan mua gan nhat, TDV/QLV "
                       "phu trach va KPI tai don tung TDV (so khach tai don / chi tieu). BAT BUOC dung khi hoi "
                       "khach chua dat KPI tai don. Tra DANH SACH khach, khong chi mo ta chung. Chi kenh OTC.",
        "input_schema": {"type": "object", "properties": {
            "year_month": {"type": "string", "description": "YYYY-MM; mac dinh thang co snapshot moi nhat."},
            "manager_code": {"type": "string", "description": "Ma QLV khi cau hoi gioi han MOT DOI (vd 'doi qlv "
                                                               "TM23100148'). BAT BUOC truyen thay vi tu loc tren "
                                                               "danh sach toan cong ty. Tai khoan QLV bi ep doi cua "
                                                               "chinh ho, tham so nay bi bo qua."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000}}, "required": []},
    },
    {
        "name": "get_focus_product_kpi",
        "description": "DOANH SO SAN PHAM TRONG TAM va KPI trong tam theo QUAN LY VUNG: doanh so trong tam, chi "
                       "tieu, % dat va diem KPI tu ket qua tinh luong Bravo (tang QLV, khong cong cac tang). Tai "
                       "khoan QLV kem tung thanh vien doi. BAT BUOC dung khi hoi doanh so/KPI san pham trong tam "
                       "theo QLV/doi. KHONG dung cho % target SKU trong tam theo khach hang. kieu_chi_tieu="
                       "'ty_trong_doanh_so' (Mien Bac): chi tieu la ty trong trong tam/doanh so (ty_trong_muc_tieu_pct),"
                       " KHONG phai so tien.",
        "input_schema": {"type": "object", "properties": {
            "year_month": {"type": "string", "description": "YYYY-MM; mac dinh thang moi nhat."},
            "manager_code": {"type": "string", "description": "Ma QLV khi cau hoi gioi han MOT DOI (vd 'doi qlv "
                                                               "TM23100148') - tra dong QLV do kem tung thanh vien "
                                                               "doi. Tai khoan QLV bi ep doi cua chinh ho."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "required": []},
    },
    {
        "name": "get_kpi_scorecard",
        "description": "BANG KPI QLV/TDV trong MOT lan goi: moi TDV/CTV/CS/TK co % doanh so/chi tieu (kem nguong "
                       "thuong theo vai tro), % dat trong tam, SKU, khach tai don, khach moi, ASO (CS/TK: active "
                       "customer), tong diem KPI Bravo va no qua han cua khach phu trach; kem tong_hop_theo_qlv. "
                       "Lay snapshot moi nhat trong thang, ke ca GIUA THANG (luy_ke_giua_thang=true -> goi la tien "
                       "do den moc_snapshot). BAT BUOC dung cho 'bang KPI/tinh hinh KPI doi toi, cua TDV X, cua doi "
                       "QLV Y' thay vi ghep nhieu tool. KHONG co tien thuong - hoi thuong dung tool luong.",
        "input_schema": {"type": "object", "properties": {
            "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh moi nhat."},
            "manager_code": {"type": "string", "description": "Ma HOAC ten QLV - bang KPI doi do. Tai khoan QLV bi ep doi cua chinh ho."},
            "employee_code": {"type": "string", "description": "Ma HOAC ten 1 nhan vien - chi dong cua nguoi do."},
            "area_code": {"type": "string", "enum": ["MB", "MT", "MN"], "description": "Loc mot mien."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 300}}, "required": []},
    },
    {
        "name": "get_etc_revenue_by_item_type",
        "description": "DOANH SO ETC THEO NHOM HANG (Hang dau tu, khai thac, duoc lieu, lao, truc tiep - danh "
                       "muc DIM_KeyClass nhom ItemTypeETC) trong 1 khoang ngay. BAT BUOC dung khi hoi doanh "
                       "so/doanh thu ETC theo nhom hang. Liet ke du moi nhom trong danh muc, ke ca nhom = 0. "
                       "Ma nhom khong co ten trong danh muc thi giu nguyen ma, KHONG tu dat ten (vd khong tu "
                       "goi la 'Khac'). Payload co bravo_sql_doi_chieu: khi nguoi dung muon kiem tra so lieu, "
                       "dua nguyen van cau lenh do.",
        "input_schema": {"type": "object", "properties": {
            "date_from": {"type": "string", "description": "YYYY-MM-DD"},
            "date_to": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date_from", "date_to"]},
    },
    {
        "name": "get_operational_data_quality",
        "description": "CHAT LUONG DU LIEU VAN HANH: nhan vien thieu manager/target/danh muc, ma "
                       "trung, khach hoa don mo coi, thieu mapping tinh, thieu ma NV va dong ghi ngay "
                       "tuong lai. Dung cho checklist cuoi thang/khach chua gan/sai mapping. Tool se liet "
                       "ke ro cac check CHUA CO NGUON (don chua hoa don, action tracker, chi nhanh/NPP); "
                       "KHONG duoc bien not_available thanh 0 loi. sample_details co ca ma, ten, vai tro, "
                       "vung va manager de hien thi than thien. management_rows_without_parent_in_source "
                       "la QLV/cap quan ly thieu cay cap tren trong NGUON, khong tinh la loi nhan vien thieu manager. "
                       "QUAN TRONG C54/S38: quality_source=fact_thongketinhluong la roster day du; "
                       "employee_tier_employees moi la mau so cua missing_target/missing_manager, con "
                       "management_tier_employees la cap quan ly tach rieng. roster_employees/employees la "
                       "tong ca hai tang, KHONG phai so nguoi co target; chi employees_with_target moi mang "
                       "nghia do. missing_target_details la danh sach DUY NHAT de hien thi; moi ma chi "
                       "co mot dong va has_sales_without_target danh dau nhom uu tien. "
                       "missing_target_with_sales la tap con de dem, KHONG liet ke lai. Neu tool fallback sang "
                       "fact_tonghopkhachhang thi missing_target co the chong lan missing_current_snapshot; "
                       "KHONG cong hai nhom. snapshot_is_closed=false CHI noi snapshot chua chot; TUYET DOI "
                       "KHONG goi thieu target la 'binh thuong', 'do dau thang' hay 'do chua nhap du' neu "
                       "khong co nguon xac nhan nguyen nhan. duplicate_codes chi la ma bi DIM gan co "
                       "IsDuplicate=1 (da loai ngoai le gan nham), KHONG phai bang chung moi ma xuat hien "
                       "nhieu dong va KHONG cho phep de nghi xoa/gop hang loat. Khi bao missing_manager "
                       "BAT BUOC viet X/employee_tier_employees nhan vien tuyen ban, KHONG noi X tren tong "
                       "roster. missing_target_with_sales la TAP CON cua missing_target: danh dau ngay trong "
                       "cung danh sach, KHONG noi/chen ma do them lan thu hai.",
        "input_schema": {"type": "object", "properties": {
            "as_of_date": {"type": "string"}, "sample_limit": {"type": "integer"},
        }, "required": []},
    },
    {
        "name": "get_customer_detail",
        "description": "Chi tiet 1 khach hang cu the (theo MA HOAC TEN khach hang): gop doanh thu thuc te trong "
                        "1 khoang ngay + so don hang + gia tri TB/don, CUNG LUC voi du no cuoi ky/no qua han "
                        "(snapshot ky gan nhat, KHONG theo khoang ngay da chon) va thong tin mapping: tinh/"
                        "thanh pho, mien (area_code MB/MT/MN), ma+ten+VAI TRO cua nhan vien phu trach "
                        "(position_label: vd 'Trinh duoc vien'/'Quan ly vung'). "
                        "UU TIEN dung tool nay cho moi cau hoi ve 1 khach hang cu the (vd 'Benh vien Bac Ninh "
                        "con no bao nhieu', 'khach hang X doanh thu bao nhieu, ai phu trach'). KHONG duoc "
                        "noi la chi tra duoc theo ma: truyen thang ten nguoi dung cung cap vao customer_code. "
                        "Neu ten trung nhieu don vi, tool tra customer_lookup_status='ambiguous' va danh sach "
                        "customer_candidates: PHAI liet ke ma+ten de nguoi dung chon, KHONG doan. "
                        "Khi da co ma, doc identity_check va doi chieu ten chinh thuc voi ten trong hoi thoai; "
                        "neu khac dia danh/don vi thi PHAI noi ro truoc khi tra so. "
                        "LUU Y: kenh ETC KHONG co NV phu trach truc tiep gan tren khach hang (chi OTC co) - "
                        "voi khach ETC thuan tuy, cac truong employee_code/employee_name/position_label se rong, "
                        "KHONG phai loi. "
                        "Neu ket qua co breakdown qua han theo bucket (overdue_1_15/15_30/30_45/gt_45) kem "
                        "truong 'aging_bucket_note' - PHAI doc va nhac lai noi dung ghi chu do khi tra loi: "
                        "khung nay (1-15/15-30/30-45/>45 ngay) LAY THANG tu he thong goc, co the KHAC voi moc "
                        "trong bao cao Excel noi bo DNH hay dung (vd 1-7/8-14/15-21/>21 ngay) - khong duoc "
                        "quy doi ngam hay coi 2 khung la mot. "
                        "HOI NHIEU KHACH HANG CUNG LUC: TRUYEN DANH SACH MA CACH NHAU DAU PHAY trong CUNG "
                        "customer_code (vd 'DBI00013,AGI00573') TRONG DUNG 1 LAN GOI, KHONG goi tool nhieu "
                        "lan lap lai cho tung ma. Ket qua tra ve {'is_bulk': true, 'customers': [...]}, MOI "
                        "phan tu kem 'requested_customer_code' de biet ung voi ma nao da yeu cau - neu 1 ma "
                        "bi loi/tu choi (vd ngoai vung, khach thuan kenh khac), phan tu do se co 'error' "
                        "kem ly do, PHAI neu ro voi nguoi dung, KHONG duoc im lang bo qua ma do.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_code": {"type": "string", "description": "Ma HOAC TEN khach hang can xem chi tiet; nhieu MA thi cach nhau dau phay"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD, dau ky tinh doanh thu"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD, cuoi ky tinh doanh thu"},
            },
            "required": ["customer_code", "date_from", "date_to"],
        },
    },
    {
        "name": "get_employee_directory",
        "description": "Tra cuu MAPPING ma nhan vien <-> ten <-> vai tro (position_label, vd 'Trinh duoc "
                        "vien'/'Quan ly vung'). Dung khi nguoi dung hoi theo TEN thay vi ma (vd 'ma nhan vien "
                        "cua Nguyen Van A la gi', '[ten] la ai', 'danh sach TDV vung MB', 'liet ke cac QLV') - "
                        "KHONG can biet ma truoc. UU TIEN dung tool nay truoc khi goi cac tool KPI nhan vien "
                        "khac neu cau hoi chi cho ten (chua co ma) - tra ma xong roi moi goi tiep tool KPI "
                        "tuong ung neu can.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Tim gan dung theo ten hoac ma nhan vien (khong bat buoc)"},
                "position_code": {"type": "string", "description": "Loc theo vai tro: TDV/QLV/CTV/CS/TP/PP/TBP/TK (khong bat buoc). TP = Truong phong = Giam doc Mien = Giam doc Kenh (cap quan ly mien/kenh). TK = Truong kenh = Truong kenh MT (Modern Trade) - cap QLV, KHONG phai TP. CS = Cho si - cung cap QLV."},
                "area_code": {"type": "string", "description": "Loc theo vung: MB/MT/MN (khong bat buoc)"},
                "limit": {"type": "integer", "description": "So luong toi da tra ve, mac dinh 30"},
            },
            "required": [],
        },
    },
    {
        "name": "check_order_timing",
        "description": "KIEM TRA CHAT LUONG DON cua ca ky trong 1 lan: (1) hang tra/dieu chinh Amount9 "
                        "am cho CA OTC/ETC, (2) phan bo gia tri don va ty trong top 1/2/5/10. "
                        "top_detail tra cac DON cu the da bi danh dau (ma don, ngay, khach, gia tri, ly do); "
                        "core_result_by_channel tra doanh thu con lai SAU KHI loai cac don do, tren cung tap du lieu. "
                        "Khi hoi don bi huy/giao tre/chua co hoa don, BAT BUOC doc order_fulfillment_exceptions: "
                        "day la doi chieu DMS_DonHangHdr voi vHoaDonTotal dung tap nguon S42; KHONG doi "
                        "danh sach nay voi top_detail (hang tra/dieu chinh hoa don). "
                        "So luong TOAN TAP phai doc trong order_fulfillment_exceptions.summary, KHONG dem "
                        "so dong mau dang hien. Nguong mac dinh la TU 2 ngay (>=2), nen lech dung 2 ngay "
                        "van duoc tinh. Nguon KHONG co ngay giao hang thuc te: chi duoc goi la lech ngay "
                        "don-hoa don, khong ket luan giao cham. Tach rieng don huy, don chua tim thay hoa "
                        "don va don co hoa don lech ngay; khong gop nhan khi cac tap khac nhau. "
                        "DNH CHUA phe duyet nguong "
                        "'don lon bat thuong': muc >3x trung vi chi la THAM CHIEU, tuyet doi khong gan "
                        "nhan gian lan hay ket luan doanh thu 'thuc chat' neu chua noi ro do tap trung. "
                        "CreatedAt la THOI DIEM TAO DON, KHONG phai thoi diem xac nhan don. DNH da xac nhan "
                        "(04/09/2026) do lech CreatedAt-DocDate KHONG mang y nghia nghiep vu; tool KHONG "
                        "kiem tra hay liet ke do lech nay. Tuyet doi khong suy dien 'chay don KPI', backdate, "
                        "bat thuong/gian lan, va khong neu ten nhan vien tu do lech hai moc ngay. "
                        "13/09/2026 (C12): cau hoi 'neu loai giao dich bat thuong, tang truong CỐT LOI TUNG "
                        "THANG con bao nhieu' -> dat group_by_month=true va truyen CA KHOANG NHIEU THANG vao "
                        "date_from/date_to (vd 12 thang) trong DUNG 1 LAN GOI - se co them "
                        "core_result_by_month (moi thang x kenh mot dong, kem core_revenue_excluding_flagged). "
                        "C13/S87, C17/S77 va M36/S78 duoc backend tu bat group_by_month va tra "
                        "financial_quality_by_month: doanh thu gop, chiet khau, hang tra, doanh thu "
                        "thuan, ty le va co nguong theo thang/kenh/vung. Hang tang va khuyen mai co "
                        "trang thai nguon rieng; khong bien thieu nguon thanh 0. "
                        "TUYET DOI KHONG goi lai tool nhieu lan cho tung thang rieng le (da tung gay 1 cau "
                        "hoi phai goi 6-10 vong va het thoi gian request). Khi group_by_month=true, tool TU "
                        "DONG rut gon top_detail (mac dinh con 3 dong) va bo qua order_fulfillment_exceptions "
                        "chi tiet de nhuong dung luong cho core_result_by_month - day la CHU DICH, KHONG PHAI "
                        "mat du lieu; muon xem chi tiet tung don/doi chieu don-hoa don thi goi lai voi "
                        "group_by_month=false (mac dinh) cho 1 khoang ngay cu the.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD, dau ky can kiem tra. Neu nguoi dung khong neu ky thi BO TRONG; tool tu lay ngay dau thang cua moc du lieu moi nhat."},
                "date_to": {"type": "string", "description": "YYYY-MM-DD, cuoi ky can kiem tra. Neu nguoi dung khong neu ky thi BO TRONG; tool tu lay ngay du lieu moi nhat. KHONG hoi lai nguoi dung chi vi thieu ky."},
                "threshold_days": {"type": "integer", "description": "Tham so cu, giu tuong thich API; hien khong su dung"},
                "limit": {"type": "integer", "description": "So don hang tra/dieu chinh hoac >3x trung vi tham chieu hien chi tiet; total_flagged khong bi cat."},
                "group_by_month": {"type": "boolean", "description": "true = tra them core_result_by_month (tach ket qua theo TUNG THANG trong [date_from, date_to], khong can goi lai tool nhieu lan). Dung khi cau hoi can xu huong THEO THANG thay vi 1 con so gop ca giai doan."},
            },
            "required": [],
        },
    },
    {
        "name": "get_inventory_by_region",
        "description": "Ton kho (so luong + gia tri) theo vung, tu Bravo (thay the Supabase - bang cu "
                        "khong loc vung duoc). BAT BUOC dung tool nay cho MOI cau hoi ve ton kho co yeu "
                        "to vung mien (vd 'ton kho mien Nam'), KE CA khi tai khoan bi gioi han vung -"
                        "day la tool DUY NHAT con hoat dong cho ho vi tool SQL tu do da bi tat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo 1 vung: 'MB'/'MT'/'MN' (khong bat buoc - bo trong de xem ca 4 vung gom ca San xuat)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_inventory_expiry_report",
        "description": "Ton kho THEO LO + HAN SU DUNG, dong thoi co canh bao SKU ton cao/cham luan chuyen/"
                        "nguy co thieu hang - dung cho cau hoi 'hang nao sap het han/can date/"
                        "da het han', 'hang ton qua han su dung', 'kiem tra date hang ton kho'. KHAC voi "
                        "get_inventory_by_region (chi co TONG so luong/gia tri theo vung, KHONG biet lo/han "
                        "su dung tung mat hang). Tra ve 'summary' (tong so lo + so luong theo TUNG khung thoi "
                        "gian con lai: het_han/duoi_3_thang/3_6_thang/6_9_thang/9_12_thang/12_18_thang/"
                        "tren_18_thang - LUON dua CA BUC TRANH TONG THE nay truoc khi di vao chi tiet) va "
                        "'rows' (chi tiet tung lo, CHI la mau minh hoa GIOI HAN theo limit, KHONG PHAI danh "
                        "sach day du - neu 'note' bao con thieu, PHAI noi ro voi nguoi dung day chi la mot "
                        "phan, khong phai toan bo). Truong 'supply_risk' so sanh ton hien co voi binh quan "
                        "ban OTC 3 thang da chot: dung cho cau hoi SKU ton cao, cham luan chuyen, kho thieu "
                        "va nguy co hut hang. supply_risk.months_of_cover KHONG phai so thang - ton dem "
                        "theo VIEN con hoa don ban theo HOP nen ty le bi thoi phong bang he so quy cach. KHONG dung "
                        "ty le nay de xep hang SKU hay viet thanh 'ton X thang'; phai nhac "
                        "canh_bao_don_vi. Moi trang thai trong status_counts deu co dong mau trong rows; "
                        "so_dong_chua_hien_theo_trang_thai cho biet con bao nhieu chua liet ke - khong "
                        "duoc noi la khong lay duoc danh sach. 'recent_customer_candidates' chi la khach da mua gan day de "
                        "goi y lien he. Voi QLV, binh quan ban va khach mua chi cua doi; ton kho dung chung "
                        "theo vung, chua phan bo cho doi. Chua tinh duoc so thang du ban khi thieu "
                        "quy doi don vi ton va ban. "
                        "PHAI noi ro day la CANH BAO SUY DIEN, khong co du lieu don cho xu ly/"
                        "phan bo ton nen KHONG duoc ket luan da mat don, da mat doanh thu hay khach chac chan "
                        "can mua. Neu nguoi dung hoi CHUNG CHUNG 'hang nao sap het han' "
                        "khong noi ro khung thoi gian, uu tien de max_bucket trong (mac dinh) de thay CA het "
                        "han LAN sap het han, hoac truyen max_bucket='duoi_3_thang' neu ho noi ro 'trong 3 "
                        "thang toi'. "
                        "Neu ket qua co truong 'sync_warning' KHAC null - PHAI doc va noi ro voi nguoi dung: "
                        "du lieu nay dong bo dinh ky tu Bravo (khong realtime), lan dong bo gan nhat da cach "
                        "qua lau nen so lieu CO THE khac thuc te tai thoi diem hoi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo 1 vung: 'MB'/'MT'/'MN' (khong bat buoc - bo trong de xem ca 4 vung gom ca San xuat)"},
                "max_bucket": {"type": "string", "enum": ["het_han", "duoi_3_thang", "3_6_thang", "6_9_thang", "9_12_thang", "12_18_thang", "tren_18_thang"],
                               "description": "Chi lay cac lo TU khung nay TRO XUONG (gan het han hon) - vd 'duoi_3_thang' se gom ca het_han + duoi_3_thang. Bo trong de xem TAT CA cac khung."},
                "limit": {"type": "integer", "description": "So dong chi tiet toi da tra ve trong 'rows' (mac dinh 30) - KHONG anh huong 'summary' (luon tinh tren toan bo pham vi)."},
                "focus": {"type": "string", "enum": ["all", "shortage", "overstock"],
                          "description": "Trong tam sap xep supply_risk: shortage cho SKU thieu hang; overstock cho ton cao/cham ban; all cho tong quan. Backend tu suy ra tu cau hoi neu bo trong."},
            },
            "required": [],
        },
    },
    {
        "name": "get_receivables_overview",
        "description": "Tong quan CONG NO toan cong ty (hoac 1 vung/kenh/doi neu tai khoan bi gioi han): tong du "
                        "no, tong no qua han, ty le qua han, tach theo kenh OTC/ETC va theo vung, va top N "
                        "khach no qua han nhieu nhat. Nguon: bao cao cong no GOC cua DNH (SP), dong bo dinh "
                        "ky vao kho local. BAT BUOC dung tool nay cho cau hoi cong no TONG HOP/NHIEU KHACH "
                        "(vd 'tong no qua han', 'top khach no', 'ty le qua han theo vung') - KHONG tu sinh "
                        "SQL va KHONG dung bang receivable_detail/receivable_etc cu (da ngung). Cong no cua "
                        "MOT khach cu the -> dung get_customer_detail. "
                        "Voi QLV, chi tinh cong no OTC cua khach phan cong cho doi theo KPI, gom khach "
                        "QLV tu phu trach; doc team_scope de biet moc phan cong. PHAI ghi ngay snapshot "
                        "receivable_as_of, khong goi so hien tai la so chot cuoi thang dang hoi; "
                        "no qua han khong tu dong la no xau. "
                        "Bang top PHAI in theo dung thu tu truong 'rank' 1..N (da xep theo no qua han "
                        "giam dan); tu xep lai theo cot khac la SAI. by_region PHAI hien du moi dong ke ca "
                        "'Khac/chua xac dinh', bo dong nao thi tong cac vung khong con khop total_overdue. "
                        "Ket qua co breakdown qua han theo bucket (overdue_1_15/15_30/30_45/gt_45) kem "
                        "truong 'aging_bucket_note' - PHAI doc va nhac lai noi dung ghi chu do khi tra loi: "
                        "khung nay (1-15/15-30/30-45/>45 ngay) LAY THANG tu he thong goc, co the KHAC voi moc "
                        "trong bao cao Excel noi bo DNH hay dung (vd 1-7/8-14/15-21/>21 ngay) - khong duoc "
                        "quy doi ngam hay coi 2 khung la mot. Pham vi vung/kenh duoc backend ep tu tai "
                        "khoan; neu ket qua co scope_note/scope_channel thi PHAI trinh bay dung pham vi, "
                        "KHONG duoc goi la 'toan cong ty' hay hien thi kenh khac. Khi hien thi bucket "
                        "cuoi, viet 'tren 45 ngay', KHONG bat dau dong Markdown bang ky tu >. "
                        "Neu cau hoi hoi SO TIEN DA THU, KE HOACH THU hoac CAM KET THU, BAT BUOC doc "
                        "collection_activity: backend lay but toan BC/PT vao 131 tren Bravo theo "
                        "khach va TDV phu trach hien tai. PHAI tra phan co nguon, kem ky va pham vi. "
                        "Chua doi chieu thu-hoa don day du; ke hoach thu va cam ket thu chua co nguon. "
                        "Khong suy so thu tu chenh lech snapshot va khong tu gan cam ket qua han.",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "description": "So khach no qua han nhieu nhat can liet ke (mac dinh 10)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_receivables_history_dates",
        "description": "CHUOI cong no theo tung MOC snapshot lich su: moi moc co tong du no, tong no qua han, "
                        "ty le qua han va chenh lech so voi moc lien truoc - dung cho MOI cau hoi dang 'cong no thay "
                        "doi the nao qua thoi gian', 'no qua han tang hay giam', hoac khi can biet co nhung ngay nao "
                        "de so sanh. TRA CA CHUOI TRONG MOT LAN GOI: KHONG duoc goi "
                        "get_receivables_period_compare lap lai cho tung cap ngay de dung duong xu huong, va KHONG "
                        "duoc chi lay vai moc roi trinh bay nhu the do la toan bo du lieu dang co. Can tach theo "
                        "kenh/vung/tuoi no hoac tung khach tai HAI moc cu the thi moi dung get_receivables_period_compare. "
                        "He thong bat dau luu lich su cong no tu 21/08/2026, KHONG co du lieu truoc do (khac doanh thu "
                        "co nhieu nam). Pham vi vung/kenh/doi duoc backend ep tu tai khoan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "So ngay gan nhat can liet ke (mac dinh 30)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_receivables_period_compare",
        "description": "SO SANH cong no giua 2 NGAY snapshot lich su - dung cho cau hoi 'cong no hom nay so voi "
                        "tuan/thang truoc the nao', 'no qua han tang hay giam', 'co cau tuoi no/kenh/mien thay doi "
                        "ra sao', 'rui ro tap trung cong no tang hay giam'. "
                        "TRA VE DAY DU tai CA HAI moc: tong du no, tong qua han, ty le qua han, 4 NHOM TUOI NO "
                        "(aging), theo KENH (by_channel), theo VUNG (by_region), TOP 10 KHACH no qua han, va do TAP "
                        "TRUNG top10/top20 - kem chenh lech tung phan. "
                        "KHONG duoc noi rang lich su 'chi co tong du no/tong qua han' hay de nghi DNH bo sung luu "
                        "snapshot chi tiet theo khach: he thong DA luu day du tung khach/kenh/vung/tuoi no tu "
                        "21/08/2026. Gioi han THAT chi la SO MOC NGAY dang co, khong phai do chi tiet. "
                        "KHAC voi get_receivables_overview (chi co snapshot HIEN TAI DUY NHAT, khong so sanh duoc). "
                        "NEU CHUA CHAC ngay nao co du lieu, goi get_receivables_history_dates TRUOC. He thong moi bat "
                        "dau luu lich su tu 21/08/2026 nen CHI so sanh duoc trong pham vi tu ngay do tro di - KHONG "
                        "the so sanh 'cung ky nam ngoai' nhu doanh thu. Pham vi vung/kenh duoc backend "
                        "ep tu tai khoan va phai duoc giu nguyen trong ca hai ky.",
        "input_schema": {
            "type": "object",
            "properties": {
                "snapshot_date_a": {"type": "string", "description": "YYYY-MM-DD, ngay can xem (ky hien tai/moi)"},
                "snapshot_date_b": {"type": "string", "description": "YYYY-MM-DD, ngay doi chieu (ky truoc/cu)"},
            },
            "required": ["snapshot_date_a", "snapshot_date_b"],
        },
    },
    {
        "name": "get_qlv_change_history",
        "description": "Lich su ai tung/dang phu trach tung khu vuc nho (zone noi bo) - dung khi hoi "
                        "'QLV vung X tung doi qua ai', 'QLV nay lam tu bao gio'. CANH BAO: day la suy "
                        "luan gian tiep tu quy uoc dat ten (Bravo KHONG co bang lich su nhan su chinh "
                        "thuc), ~30% khu vuc se tra ve 'Chua xac dinh' - PHAI noi ro voi nguoi dung day "
                        "la han che du lieu THAT, KHONG duoc tu suy doan/bia them de lap day cho trong.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo vung MB/MT/MN (tuy chon - hien tat ca khu vuc trong vung)"},
                "qlv_search": {"type": "string", "description": "Tim theo ten/ma 1 QLV cu the de xem lich su khu vuc cua rieng ho (tuy chon)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_revenue_tree",
        "description": "Cay doanh thu/KPI 3 cap: Truong phong (=GD Mien =GD Kenh) -> QLV (gom ca Truong "
                        "kenh MT va Cho si) -> Trinh duoc vien, dung "
                        "khi hoi kieu 'doanh so mien nay chia theo QLV/TDV the nao', 'cay to chuc doanh "
                        "thu vung X'. LUON dung tool nay cho cau hoi co ca 3 cap cung luc, KHONG tu ghep "
                        "nhieu tool KPI rieng le. Ket qua RAT DAI neu khong loc vung - KHUYEN KHICH truyen "
                        "area_code khi hoi ve 1 vung cu the.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo 1 vung MB/MT/MN (khuyen khich dung, de tranh ket qua qua dai)"},
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la hom nay (lay snapshot KPI gan nhat truoc/bang ngay nay)"},
            },
            "required": [],
        },
    },
    # 10/08/2026: GO tool "get_kpi_forecast_model1" khoi danh sach tool kha dung.
    # Ly do truc tiep: no CRASH 100% so lan goi, va da nhu vay tu ngay duoc viet (309d2f2, 06/08).
    # forecast_model1() truy van "SELECT t.manager_code ... FROM dim_targetvungmien t" nhung bang do
    # CHI CO 4 cot (area_code, channel_code, amount, doc_date - xem local_warehouse.py:52 va
    # sync_warehouse.py::SMALL_TABLES). Cot manager_code CHUA TUNG ton tai. Da chay thu tren may 24
    # (10/08): "OperationalError: no such column: t.manager_code".
    # Ngoai loi chet nguoi tren, con 6 van de PHAI xu ly truoc khi bat lai - xem khoi ghi chu day du o
    # report_templates.py ngay tren def forecast_model1(). Tom tat: nhan "(VUOT TARGET)" dan cung, note
    # dan cung choi lai so vua tinh, 4 cho bia so khi thieu du lieu, bo qua phan quyen vung/doi,
    # target_month la tham so trang tri, va mau so co phan la so doan (est_mb_target 19,5 ty +
    # target_etc_national 42,5 ty khong lay tu bang nao).
    # Ham forecast_model1() va TEMPLATES entry duoc GIU LAI de sua tiep sau demo 13/08; go o day la du
    # de model khong the goi (tool khong nam trong danh sach thi khong goi duoc).
    {
        "name": "get_kpi_ranking",
        "description": "Xep hang % dat KPI, TOT NHAT truoc - dung khi hoi 'QLV nao dat KPI tot/kem "
                        "nhat', 'xep hang cac vung theo KPI', 'so sanh KPI giua cac QLV/vung'. "
                        "Doc as_of tren ket qua va canh bao: neu ky moi chua co target, tool tra ky tron "
                        "gan nhat de tham khao; PHAI ghi dung thang do, khong goi la KPI thang hien tai. "
                        "Nguoi chua du snapshot/target duoc canh bao, khong coi la 0% KPI. Moi dong QLV "
                        "co threshold=70 va meets_bonus_threshold da tinh san: pct<70 (vd 67,6%) BAT BUOC "
                        "la chua toi muc thuong nhom hang, khong duoc gan dau dat/sat moc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "description": "'qlv' (xep hang tung QLV, mac dinh) hoac 'region' (gop theo vung MB/MT/MN)"},
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la hom nay"},
                "limit": {"type": "integer", "description": "So luong toi da tra ve, mac dinh 20"},
            },
            "required": [],
        },
    },
    {
        "name": "get_revenue_reconciliation",
        "description": "Doi chieu doanh thu OTC tinh TU TREN XUONG (tong hoa don toan vung) voi doanh "
                        "thu CONG DON TU DUOI LEN (TDV -> QLV -> TP, tu KPI ca nhan) - dung khi nguoi "
                        "dung hoi kieu 'so lieu nay co khop voi KPI nhan vien khong', 'doanh thu tong "
                        "co dung khong', 'kiem tra chieo doanh thu tu duoi len', hoac nghi ngo so lieu "
                        "tong the bi lech so voi tong hop tu cap duoi. Hai ve deu CHI tinh OTC va cung "
                        "ky. Doc reconciliation_status, gap_revenue, gap_pct va warning: coverage ngoai "
                        "99,5%-100,5% la CHUA DOI SOAT KHOP/can dieu tra, KHONG duoc goi la binh thuong "
                        "hay gap cau truc da biet. KHONG tu gan chenh lech cho ETC, khach mo coi, QLV/TDV "
                        "neu ket qua chua co phep do dinh luong nguyen nhan; khong co so ky truoc thi "
                        "khong ket luan gap on dinh. rollup_nodes_without_tdv KHONG phai so zone thieu "
                        "QLV; cause_attribution_available=false nghia la CHUA DU DU LIEU quy nguyen nhan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la hom nay (lay snapshot KPI gan nhat truoc/bang ngay nay)"},
                "area_code": {"type": "string", "description": "Loc theo 1 vung MB/MT/MN (khong bat buoc - bo trong de doi chieu toan cong ty)"},
            },
            "required": [],
        },
    },
    # 10/08/2026: bo sung khoi "GOI DUNG 1 LAN LA DU" sau khi cau hoi "Bao cao chi phi AI chi tiet theo
    # nguoi dung" that bai 2 lan lien tiep trong 1 buoi (14:10 va 14:12, 2 phien khac nhau), nguoi dung
    # nhan cau tu choi "cau hoi qua phuc tap". Doc audit_log 2 phien do thay cung 1 khuon mau:
    #   vong 1: get_audit_log(target_username='all') -> DA co san user_breakdown (dnh, vui.hoangthi,
    #           diag_test) - tuc la da du de tra loi ngay tu day
    #   vong 2-4: goi LAI tool cho TUNG username mot, roi doi limit, roi quet sqlite_master tim bang
    #           chi phi khac -> can MAX_TOOL_ROUNDS, roi vao fallback
    # Nguyen nhan: audit_log_summary() CO Y tra user_breakdown=None khi loc 1 nguoi cu the (luc do bao
    # cao chi con 1 nguoi, tach ra khong con y nghia - xem report_templates.py ~2029). Model doc thay
    # null thi tuong bi loi/thieu quyen nen cang co thu them. Day KHONG phai loi du lieu va KHONG phai
    # do effort (da go 06/08) - chi la mo ta tool chua noi ro. Cach chua giong het get_salary_detail
    # ben duoi (cung benh: goi lap cho tung nguoi).
    {
        "name": "get_audit_log",
        "description": "Lich su truy van va token/chi phi AI quy doi VND/USD. Voi tai khoan C-Level hoac Admin: ho tro xem BÁO CÁO CHI PHÍ AI TOÀN CÔNG TY hoac loc theo nguoi dung (target_username). Voi tai khoan QLV/TDV: xem chi phi va lich su ca nhan. "
                        "GOI DUNG 1 LAN LA DU voi cac cau kieu 'chi phi AI chi tiet theo nguoi dung', "
                        "'ai ton bao nhieu tien', 'bao cao chi phi toan cong ty': MOT lan goi "
                        "target_username='all' DA tra ve san truong 'user_breakdown' - bang chi phi TACH "
                        "SAN theo TUNG tai khoan (so luot, so phien, token, USD, VND). Do CHINH LA phan "
                        "'chi tiet theo nguoi dung' ma nguoi hoi can, lay thang tu do ma trinh bay. "
                        "TUYET DOI KHONG goi lai tool nay rieng cho tung username de 'dao sau them', va "
                        "KHONG dung query_database/sqlite_master de tim nguon chi phi khac (khong co bang "
                        "nao khac) - lam vay chi ton token va tien, lai de cham tran so vong goi tool "
                        "khien ca cau hoi that bai. "
                        "LUU Y QUAN TRONG: khi loc DUNG 1 nguoi (target_username='<ten>') thi "
                        "'user_breakdown' CO Y tra ve null, vi luc do bao cao chi con 1 nguoi nen khong "
                        "con gi de tach - day KHONG PHAI loi, KHONG PHAI thieu quyen, KHONG duoc goi lai "
                        "de thu. Chi truyen ten cu the khi nguoi hoi dich danh DUNG 1 nguoi. "
                        "CACH TRINH BAY: ket qua co truong 'display_hint' - PHAI theo dung huong dan do "
                        "(dang TIMELINE, moi dong 1 su kien voi gio + event_summary DA SOAN SAN dung "
                        "nguyen van, moi nhat len dau, KHONG trinh bay thanh bang SQL/cot ky thuat).",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "So ngay gan nhat can xem, mac dinh 7"},
                "limit": {"type": "integer", "description": "So dong lich su gan nhat toi da tra ve, mac dinh 30"},
                "target_username": {"type": "string", "description": "Ten tai khoan nguoi dung can loc (chi danh cho C-Level/Admin), hoac 'all' de xem toàn cong ty. NEN dung 'all': ket qua da co san user_breakdown tach chi phi theo TUNG nguoi, KHONG can goi lai cho tung username. Chi truyen ten cu the khi nguoi hoi dich danh dung 1 nguoi."},
            },
            "required": [],
        },
    },
    {
        "name": "get_customer_revenue_debt_risk",
        "description": "Tim trong DUNG 1 LAN cac khach hang dong thoi co doanh thu lon, no qua han "
                       "cao va doanh thu dang giam so voi giai doan truoc. BAT BUOC dung cho cau hoi "
                       "'khach hang doanh thu lon, cong no cao, xu huong mua giam' va cac cach hoi "
                       "tuong duong. Tool tu so sanh hai giai doan cung do dai, noi doanh thu voi "
                       "snapshot cong no da chuan hoa va ep pham vi tai khoan. KHONG goi tach top "
                       "khach + cong no + so sanh ky thanh nhieu vong, KHONG viet SQL ad-hoc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD; mac dinh ngay du lieu moi nhat."},
                "recent_months": {"type": "integer", "description": "So thang moi giai doan, mac dinh 3."},
                "min_revenue": {"type": "number", "description": "Doanh thu toi thieu ky gan nhat, mac dinh 100 trieu dong."},
                "min_overdue": {"type": "number", "description": "No qua han toi thieu, mac dinh 50 trieu dong."},
                "limit": {"type": "integer", "description": "So khach toi da, mac dinh 20."},
            },
            "required": [],
        },
    },
    {
        "name": "get_promotion_effectiveness",
        "description": "Danh gia HIEU QUA TUNG CHUONG TRINH KHUYEN MAI theo doanh thu gan voi don "
                       "hang co ap dung chuong trinh, so khach hang tham gia, so don va so san pham. "
                       "BAT BUOC dung tool nay cho cau hoi 'danh gia hieu qua CTKM/khuyen mai', 'CTKM "
                       "nao co doanh thu/khach hang cao', hoac cau hoi ket hop CTKM + doanh thu + khach "
                       "hang + san pham. GOI DUNG 1 LAN, KHONG search catalog va KHONG query/group theo "
                       "cot CTKM cua hoa don: cot do la GHI CHU TU DO, co the chua ten/so dien thoai va "
                       "da tung tao ket qua sai. Tool dung lien ket DMS_DonHangCTKM -> DMS_CTKM that, "
                       "tu kiem tra moc du lieu va mac dinh chon thang DAY DU gan nhat neu user khong "
                       "noi ky. associated_revenue la doanh thu gan voi don co CTKM, KHONG duoc cong "
                       "cac dong hoac goi la ROI/uplift vi mot don co the dung nhieu CTKM. Khi tra loi "
                       "BAT BUOC hien ca program_code, program_name va period tu payload; khong duoc "
                       "chi viet ten chuong trinh hoac bo moc du lieu. "
                       "MOT CHUONG TRINH CO THE CHAY NHIEU THANG: doc program_from/program_to va "
                       "program_month_count. Neu program_spans_multiple_months=true PHAI noi ro "
                       "chuong trinh chay tu ngay nao den ngay nao, dung de nguoi doc tuong la "
                       "chuong trinh mot thang. Neu report_covers_full_program=false PHAI doc "
                       "nguyen period_coverage_note va noi ro cac so chi la PHAN TRONG KY BAO CAO, "
                       "KHONG phai ket qua ca chuong trinh. Neu name_is_ambiguous=true thi co nhieu "
                       "ma khac ky cung mot ten (xem same_name_program_codes): PHAI phan biet bang "
                       "ma va ky, khong duoc gop chung hoac cong doanh thu cac ma do lai. "
                       "Neu code_is_ambiguous=true thi NGUOC LAI: mot ma ung voi NHIEU chuong trinh "
                       "khac nhau (DMS_CTKM.Code bi cat ngan - xem same_code_programs). Hai dong do tuy "
                       "cung ma nhung la hai chuong trinh that, PHAI phan biet bang program_id va "
                       "program_name, KHONG duoc coi la bang bi lap va KHONG duoc cong lai lam mot. "
                       "Neu scope_area_code khac null, PHAI noi ngay trong cau mo dau rang cac so chi la "
                       "cua mien do, KHONG phai toan quoc (doc scope_note): do that ky 12/2025, mot chuong "
                       "trinh toan quoc 1.056 don/30,05 ty chi con 857 don/23,83 ty khi tinh rieng MB - bo "
                       "cau do di thi nguoi doi chieu lay so toan quoc ra so va tuong bao cao sai. "
                       "MAU SO CUA DOANH THU BINH QUAN LA invoiced_orders, KHONG phai orders: khi hien "
                       "average_revenue_per_invoiced_order PHAI hien ca orders VA invoiced_orders trong "
                       "cung bang. Bo cot invoiced_orders di thi nguoi doc tu lay associated_revenue chia "
                       "orders se ra so khac han va tuong bao cao sai (22/09/2026 - doi chieu M35 ky 12/2025: "
                       "857 don nhung mau so that la 685 don da xuat hoa don). Neu invoiced_orders < orders "
                       "PHAI noi ro con don gan CTKM chua xuat hoa don trong ky, va associated_revenue vi the "
                       "la SO THIEU so voi thuc te. "
                       "Neu status=source_gap, PHAI neu "
                       "dung promotion_link_coverage_to va requested_period, noi ro day la lo hong dong "
                       "bo chu KHONG phai bang chung ky do khong co CTKM; khong suy dien khach/don/doanh "
                       "thu va khong dung cot CTKM ghi chu tu do thay the.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD; bo trong de tool tu chon thang day du gan nhat."},
                "date_to": {"type": "string", "description": "YYYY-MM-DD; bo trong de tool tu chon thang day du gan nhat."},
                "limit": {"type": "integer", "description": "So chuong trinh toi da, mac dinh 20, toi da 50."},
            },
            "required": [],
        },
    },
    {
        "name": "get_promotion_data_quality",
        "description": "Do phu va CHAT LUONG chuoi lien ket CTKM: ngay don dau/cuoi, thoi diem sync, "
                       "tong link, so link MAT DON HANG, MAT MA CHUONG TRINH va so link hop le. BAT "
                       "BUOC dung DUNG 1 LAN khi hoi 'du lieu khuyen mai den ngay nao', 'moc lien ket "
                       "CTKM', 'bao nhieu lien ket mat don/mat chuong trinh'. KHONG search catalog, "
                       "KHONG query SQL thu cong, KHONG goi get_promotion_effectiveness cho cau hoi "
                       "chat luong nguon don thuan.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_salary_bonus_policy",
        "description": "Tra QUY TAC/CACH TINH/BAC TIEN cua V15, V22, V25 hoac ASO tu DIM_BacThuong, "
                       "dong thoi doi chieu voi so thuong da chot trong FACT_ThongKeTinhLuong. BAT BUOC "
                       "dung tool nay khi hoi 'V25 duoc tinh nhu the nao', 'cac bac tien V15/V22/V25', "
                       "'cong thuc thuong ASO', 'vi sao dat ty le ma thuong bang 0', hoac cau hoi mo ho "
                       "kieu 'V25 cua tung ASO'. GOI DUNG 1 LAN; KHONG search catalog/query SQL thu cong. "
                       "QUY TAC NGOAI LE: CS (Cho si) va TK (kenh MT) dung co is_ac/Active Customer, "
                       "KHONG co ASO; neu da co is_ac thi khong gan/cong ASO. ASO trong du lieu DNH la "
                       "CHI TIEU/KHOAN THUONG khach hang hoat dong cua cac vai tro con lai, khong phai chuc danh. "
                       "QUY TAC BAT BUOC: V25 dung han tu 07/2026 va duoc thay bang V15/V22; V25Bonus=0 "
                       "trong ky 07/2026 tro di la DUNG CO CHE, KHONG PHAI loi thu tuc va TUYET DOI KHONG "
                       "de nghi bu thuong/truy linh. Cac dong V25 con trong DIM_BacThuong co the la cau hinh "
                       "lich su ton du. Tool chi kiem tra mismatch V25 cho ky den het 06/2026; neu co chenh "
                       "lech thi cung chi goi la CAN KE TOAN/IT XAC NHAN, khong tu ghi de so da chot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bonus_type": {"type": "string", "enum": ["v15", "v22", "v25", "aso"], "description": "Loai thuong can giai thich."},
                "as_of_date": {"type": "string", "description": "YYYY-MM hoac YYYY-MM-DD; mac dinh ky luong day du gan nhat."},
                "area_code": {"type": "string", "description": "Loc MB/MT/MN neu nguoi dung neu ro."},
                "position_code": {"type": "string", "description": "Loc TDV/QLV/TP/PP/TBP/CS/TK/CTV neu nguoi dung neu ro."},
            },
            "required": ["bonus_type"],
        },
    },
    {
        "name": "get_salary_data_quality",
        "description": "Kiem tra CHAT LUONG DU LIEU LUONG bang 1 lan goi co dinh. Dung "
                       "dm_reconciliation khi hoi DM1/DM2/DM3, DMBonus va TotalPoint co khop cong "
                       "thuc khong; dung base_salary_schema khi hoi bang da co luong co ban/LCB hay "
                       "du de ket luan tong thu nhap chua; dung snapshot_quality khi hoi ky nao da "
                       "chot/dong dau-thang rong. BAT BUOC dung tool nay, KHONG search catalog/query "
                       "SQL thu cong va KHONG tra so lieu tu prompt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "check_type": {
                    "type": "string",
                    "enum": ["dm_reconciliation", "base_salary_schema", "snapshot_quality"],
                },
                "year_month": {"type": "string", "description": "YYYY-MM; bo trong lay ky da chot gan nhat."},
            },
            "required": ["check_type"],
        },
    },
    {
        "name": "get_salary_achievement_summary",
        "description": "Bao cao tong hop/thong ke so luong nhan vien dat cac moc thuong tien do (V15, V22, V25) va ASO tren toan cong ty hoac toan doi cua QLV. "
                       "Dung khi nguoi dung hoi 'co bao nhieu nguoi dat V15', 'tong hop V22 toan quoc/toan doi', 'thong ke ASO', v.v. "
                       "CUNG dung cho 'chi phi thuong/doanh thu' va 'thuong chiem bao nhieu % doanh so': "
                       "payload cost_summary co tong thuong va ty le theo thang, mau so CHI gom TDV/CTV/CS/TK "
                       "de khong nhan doi doanh thu rollup cap quan ly. KHONG co loi nhuan/gross margin va "
                       "KHONG duoc ket luan nhan qua hay tang truong ben vung. "
                       "ASO chi ap dung cho vi tri khac CS (Cho si) va TK (kenh MT); CS/TK dung co is_ac/Active Customer, "
                       "khong duoc cong ASO vao cung mot dong. "
                       "Phan quyen: neu nguoi hoi la C-Level se thay toan bo, neu la QLV se tu dong bi gioi han ve doi cua minh. "
                       "Ve dieu kien ap dung V15/V22/V25 theo vai tro va quy tac snapshot CUOI KY (KHONG phai tien do "
                       "thang hien tai) - xem chi tiet o mo ta tool get_salary_detail, ap dung giong het o day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "save_date": {
                    "type": "string",
                    "description": "Thang can tra cuu (YYYY-MM). Neu de trong se lay ky luong gan nhat.",
                },
                "month_from": {"type": "string", "description": "YYYY-MM; ky dau cho cost_summary. De ca hai moc trong thi tra 12 thang da chot gan nhat."},
                "month_to": {"type": "string", "description": "YYYY-MM; ky cuoi cho cost_summary."},
                "scope_area_code": {
                    "type": "string",
                    "description": "Ma vung mien can tra cuu (MB, MT, MN, ...). Khong bat buoc.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_salary_detail",
        "description": "Chi tiet THUONG KINH DOANH + PHU CAP thang cua 1 nhan vien (V15/V22/V25 thuong "
                        "tien do, ASO, thuong danh muc DM1/DM2/DM3, SKU, khach tai don/khach moi), theo "
                        "chinh sach thu nhap moi (QD 0429/.25 Mien Nam/Trung, QD 0107/2026 TDV toan "
                        "quoc, hieu luc tu 28/07/2026) - dung khi nguoi dung hoi 'thuong thang nay cua "
                        "toi/cua [ten] bao nhieu', 'V15/V22/V25/ASO cua [ten]', 'thuong danh muc/tien do "
                        "cua toi', 'ket qua KPI luong cua toi'. "
                        "QUY TAC IS_AC/ASO: CS (Cho si) va TK (kenh MT/Modern Trade) dung co is_ac/Active Customer, "
                        "KHONG co ASO. Neu mot dong da co is_ac thi khong duoc hien thi hoac cong ASO; hai vai tro nay "
                        "chi doc active customer. Cac vai tro khac moi dung ASO khi nguon luong co ghi nhan. "
                        "QUAN TRONG VE HIEU LUC: V15, V22 chi ap dung cho TDV. V25 chi ap dung cho Truong phong, Quan ly vung, Cho si, Kenh MT. "
                        "He thong chi luu snapshot luong CUOI KY (vd 30/06, 31/07). Neu user hoi tien do giua thang (vd 25/07), tool se tra ve cua "
                        "thang truoc do (30/06). KHI TRA LOI PHAI KET LUAN/NOI RO diem nay: 'He thong chi chot luong cuoi ky, day la ket qua luong thang truoc da chot, khong phai tien do thang nay'. "
                        "HOI NHIEU NGUOI CUNG LUC (vd 'V15/V22/V25/ASO cho ca 4 TDV cua QLV X', 'thuong "
                        "cua tat ca nhan vien vung Y') -> TRUYEN DANH SACH CAC MA NHAN VIEN PHAN CACH BANG DAU PHAY "
                        "(vd employee_code='MBKV1,MBKV2,MBKV3,MBKV4') TRONG DUNG 1 LAN GOI TOOL DUY NHAT. "
                        "TUYET DOI KHONG GOI TOOL NAY NHIEU LAN LAP LAI CHO TUNG NGUOI DE TIET KIEM TOKEN VA TIEN. "
                        "Neu 1 nguoi trong danh sach bi loi/tu choi (vd khong du quyen), ket qua se bao ro "
                        "nguoi do va ly do trong truong 'errors' - KHONG duoc im lang bo qua, phai neu ro "
                        "voi nguoi dung ai bi thieu va vi sao. "
                        "!!! CANH BAO QUAN TRONG: ket qua CHUA GOM Luong co ban (LCB) - he thong hien "
                        "CHUA co du lieu LCB (Bravo khong luu san muc LCB theo Level). PHAI noi ro voi "
                        "nguoi dung day la THUONG KINH DOANH + PHU CAP, KHONG PHAI 'tong luong'/'tong "
                        "thu nhap' day du - neu ho hoi tong thu nhap/luong thang, tra loi phan thuong "
                        "nay VA noi ro con thieu LCB, de nghi lien he ke toan/HR de biet LCB chinh xac. "
                        "PHAN QUYEN: mac dinh CHI tra ve DUNG cua nguoi dang hoi (server tu dong xac "
                        "dinh, KHONG the xem cua nguoi khac du truyen employee_code gi) - tai khoan "
                        "C-Level HOAC QLV (xem doi cua chinh minh) moi xem duoc nguoi khac qua tham so "
                        "employee_code; QLV Bui Khac Dung hoi ve 4 TDV cua chinh minh la HOP LE, KHONG "
                        "duoc tu choi truoc khi thu goi tool. Phan quyen AP DUNG RIENG cho TUNG nguoi "
                        "trong danh sach, khong noi long chi vi goi hang loat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_code": {"type": "string", "description": "Ma/ten nhan vien can tra cuu - co the truyen NHIEU ma cach nhau bang dau phay (vd 'MBKV1,MBKV2,MBKV3') de tra ve ca danh sach trong 1 lan goi. CHI co hieu luc voi tai khoan C-Level/QLV xem doi minh, bi bo qua voi tai khoan thuong (tu dong dung chinh nguoi hoi)"},
                "save_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la snapshot moi nhat hien co (thuong cuoi thang/dot chot gan nhat)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_salary_ranking",
        "description": "Bang THUONG/PHU CAP TUNG NGUOI trong doi hoac xep hang TOP N (V15, V22, V25, ASO, Thuong danh muc DM) "
                        "trong ky/thang. DUNG KHI HOI 'top 30 nhan vien duoc thuong nhieu nhat', 'top thuong MB', "
                        "'ai duoc thuong V15 cao nhat', 'danh sach top thuong thang 7', 'top 10 thuong mien bac', "
                        "'top 30 theo MB', 'tong thuong luon'. "
                        "Tra ve bang day du trong MOT LAN (thuong total, V15, V22, V25, ASO, allowance, % target), "
                        "kem previous_* va *_delta cua KY CHOT LIEN TRUOC de tra loi 'thay doi'. KHONG goi "
                        "get_salary_detail tung nguoi khi hoi ca doi. Neu hoi them diem KHONG KHOP CHINH SACH, "
                        "sau bang nay goi get_salary_bonus_policy dung loai thuong can doi chieu; mismatch chi "
                        "la canh bao can ke toan/IT xac nhan, khong tu ket luan se duoc bu tien. RIENG ky tu "
                        "07/2026: V25=0 la DUNG vi DNH da thay V25 bang V15/V22, khong duoc goi la mismatch. "
                        "QUY TAC: CS (Cho si) va TK (kenh MT) dung is_ac/Active Customer, khong co ASO; "
                        "tong thuong cua hai vai tro khong cong ASO, va xep hang rieng ASO khong bao gom CS/TK. "
                        "chay sieu toc trong 0.01 giay. TUYET DOI KHONG dung SQL ad-hoc hoac tool khac cho nhu cau nay.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year_month": {"type": "string", "description": "Thang/ky can xem (YYYY-MM hoac YYYY-MM-DD, vd '2026-07')"},
                "area_code": {"type": "string", "description": "Ma vung mien loc (MB, MT, MN, hoac bo trong neu xem toan quoc)"},
                "position_code": {"type": "string", "description": "Chuc danh loc (TDV, QLV, TP, TK, hoac bo trong). TP = Truong phong = Giam doc Mien = Giam doc Kenh (cap quan ly mien/kenh). TK = Truong kenh = Truong kenh MT (Modern Trade) - cap QLV, KHONG phai TP. CS = Cho si - cung cap QLV."},
                "bonus_type": {"type": "string", "enum": ["total", "v15", "v22", "v25", "aso", "dm"], "description": "Loai thuong quan tam: 'total' (tong thuong KD), 'v15', 'v22', 'v25', 'aso', 'dm' (thuong danh muc)"},
                "limit": {"type": "integer", "description": "So luong nhan vien muon lay (mac dinh 30, toi da 100)"}
            },
            "required": [],
        },
    },
]

QUERY_TOOL = {
    "name": "query_database",
    "description": (
        "CHI dung cho cau hoi AD-HOC ve hoa don/doanh thu/san pham/khach hang/nhan vien/vung mien/"
        "tra hang KHONG thuoc bat ky tool bao cao chuan nao o tren (vd dieu kien loc dac thu...). "
        "Chay 1 cau SQL SELECT (chi doc) tren kho 'local' (SQLite, dong bo dinh ky tu Bravo, co day "
        "du lich su - dung LIMIT N, KHONG dung TOP N, KHONG can quote ten cot). "
        "Chi duoc dung SELECT/WITH, khong duoc INSERT/UPDATE/DELETE/DROP/ALTER."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Cau lenh SQL SELECT (dialect SQLite) can chay tren kho local"},
            "explanation": {"type": "string", "description": "Giai thich ngan gon muc dich cau query nay"},
        },
        "required": ["sql"],
    },
}

QUERY_SQL_SERVER_TOOL = {
    "name": "query_sql_server",
    "description": (
        "FALLBACK CHI-DOC tren SQL Server Bravo LIVE cho du lieu/business object chua duoc dong bo vao "
        "warehouse.db va khong co tool bao cao chuan. CHI dung sau khi da xem schema lien quan trong "
        "context hoac goi search_sql_server_catalog. Dung T-SQL: TOP N, dbo.[TenObject], KHONG LIMIT, "
        "KHONG SELECT *. Chi SELECT/WITH; cam EXEC stored procedure, ghi/sua/xoa, SELECT INTO va truy van "
        "sang database khac. Du lieu live la nguon chinh de kiem tra do phu, nhung voi doanh thu/cong no/"
        "KPI da co tool chuan thi van BAT BUOC dung tool chuan truoc. C44/M42 hop dong ETC: dung "
        "get_etc_contract_status, noi vHoaDonETCTotal.ContractId va cuon phu luc theo Id0. KHONG duoc "
        "ghep qua customer+SKU. Gia tri con lai la chua xuat hoa don, khong phai chua giai ngan. "
        "Cong no qua han theo hop dong chua kiem chung; khong gan no khach cho tung hop dong. "
        "Tach gia tri bat thuong theo tool chuan. Tool live chi kha dung cho vai tro "
        "C-Level/Admin do SQL tu do khong the ep phan quyen dong theo moi bang."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Mot cau SELECT/WITH T-SQL chi-doc, nen co TOP N."},
            "explanation": {"type": "string", "description": "Muc dich nghiep vu va object duoc dung."},
        },
        "required": ["sql"],
    },
}

SEARCH_SQL_CATALOG_TOOL = {
    "name": "search_sql_server_catalog",
    "description": (
        "Tim table/view/stored procedure va cot lien quan trong TOAN BO catalog SQL Server duoc cap quyen. "
        "Dung khi cau hoi nhac toi du lieu chua co trong schema warehouse viet san, khi chua chac ten object/"
        "cot, hoac can doc logic definition cua view/stored procedure. Tool chi doc metadata, khong doc dong "
        "du lieu va khong EXEC procedure. Sau khi tim thay table/view, dung query_sql_server neu tai khoan co quyen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Tu khoa nghiep vu hoac ten object/cot can tim."},
            "limit": {"type": "integer", "description": "So object toi da, mac dinh 6, toi da 12."},
            "include_definition": {"type": "boolean", "description": "Co lay definition view/SP neu quyen cho phep."},
        },
        "required": ["query"],
    },
}

SAVE_GLOSSARY_TOOL = {
    "name": "save_business_term",
    "description": "Luu 1 thuat ngu nghiep vu ma NGUOI DUNG vua dinh nghia trong cau hoi hien tai (vd "
                    "'doanh thu rong nghia la doanh thu tru chiet khau') de cac lan hoi sau tu dong ap "
                    "dung dung nghia nay, khong can nguoi dung giai thich lai. CHI goi khi nguoi dung "
                    "THUC SU dang dinh nghia 1 khai niem (khong phai chi hoi so lieu binh thuong).",
    "input_schema": {
        "type": "object",
        "properties": {
            "term": {"type": "string", "description": "Ten thuat ngu, vd 'doanh thu rong'"},
            "definition": {"type": "string", "description": "Dinh nghia nguoi dung vua giai thich"},
        },
        "required": ["term", "definition"],
    },
}

RAW_SQL_TOOLS = {
    "query_database": "local",
    "query_sql_server": "bravo",
}
LIVE_SQL_TOOL_NAMES = {"query_sql_server"}
LIVE_SQL_ALLOWED_ROLES = {"c_level", "admin_ops"}
LOCAL_UTIL_TOOLS = REALTIME_TOOL_NAMES | {"save_business_term", "search_sql_server_catalog"}

# Chinh sach 14/08/2026: loc o tang code, khong chi dua vao prompt. Ke ca khi mot
# tool du bao cu con sot lai trong danh sach khai bao phia tren, no cung khong bao
# gio duoc gui cho model.
TEMPLATE_TOOLS = [
    tool for tool in TEMPLATE_TOOLS if tool["name"] not in DISABLED_FUTURE_TOOL_NAMES
]
ALL_TOOLS = (
    TEMPLATE_TOOLS
    + [QUERY_TOOL, QUERY_SQL_SERVER_TOOL, SEARCH_SQL_CATALOG_TOOL]
    + REALTIME_TOOLS
    + [SAVE_GLOSSARY_TOOL]
)
# Tools KHONG bao gio doi trong 1 phien chay - danh cache_control tren tool CUOI CUNG de cache ca
# mang tools (Anthropic cache theo kieu "prefix": danh dau 1 block = cache moi thu TINH DEN block do).
ALL_TOOLS_CACHED = ALL_TOOLS[:-1] + [{**ALL_TOOLS[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]

# Trung voi _SALARY_SENSITIVE_TEMPLATES ben report_templates.py. Dat o day de lop quang cao tool
# co the an truoc khi model thu goi; call_template() van giu kiem tra fail-closed doc lap.
_SALARY_SENSITIVE_TEMPLATE_NAMES = {
    "get_salary_bonus_policy", "get_salary_data_quality", "get_salary_detail",
    "get_salary_achievement_summary", "get_salary_ranking", "get_salary_aso_detail",
}


def _json_mac_dinh(gia_tri):
    """Chuyen kieu du lieu JSON khong ho tro khi dong goi ket qua tool gui model.

    14/09/2026: Bravo (pyodbc) tra so dang Decimal va ngay dang date/datetime. Hai cho dong goi
    payload_str (ask va ask_stream) goi json.dumps KHONG co default, nen chi can MOT tool tra nguyen
    gia tri Decimal la ca buoc gui ket qua cho model nem TypeError va cau tra loi hong. Da xay ra that
    voi get_salary_aso_detail (ASOQuantity/ASOBonus) - duoc va tay tren may 24 ngay 13/09. Chan tan
    goc o day de khong tool doc Bravo nao khac vo theo cung kieu.
    """
    import datetime as _dt
    from decimal import Decimal
    if isinstance(gia_tri, Decimal):
        return float(gia_tri)
    if isinstance(gia_tri, (_dt.datetime, _dt.date)):
        return gia_tri.isoformat()
    return str(gia_tri)


def _cache_tools(tools: list[dict]) -> list[dict]:
    if not tools:
        return []
    return tools[:-1] + [{**tools[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]


def _customer_tool_conflict(name: str, question: str) -> bool:
    """C29 uses Bravo NC/RO, never substitute invoice-first-observed counts.

    Enforce before execution, including two tool_use blocks in the same batch or
    a movement call arriving first. Other questions can still compare definitions.
    """
    return (name == "get_customer_movement"
            and _required_tool_for_question(question) == "get_customer_lifecycle_summary")


# 11/09/2026 (M20 UAT 09/09): cau hoi dinh tuyen vao tool luong ma vai tro khong duoc xem (Giam doc
# mien/kenh bi an moi tool luong o _tools_for_request). Truoc day required_tool bi bo qua vi tool khong
# co trong danh sach, model khong bi ep gi va tu choi CA cau - bo luon phan KPI vai tro nay duoc xem.
# Nay ep sang tool KPI va dan model noi ro phan tien luong/thuong ca nhan khong mo cho vai tro nay.
_SALARY_FALLBACK_TOOL = "get_employee_kpi"
_SALARY_FALLBACK_NOTE = (
    "LUU Y QUYEN CHO CAU NAY: tai khoan khong duoc xem luong/thuong CA NHAN chi tiet. KHONG tu choi ca "
    "cau: tra loi day du phan KPI tu get_employee_kpi (% dat chi tieu, dat KPI 80%, nguong thuong nhom "
    "hang TDV 65%/QLV 70%, ai duoi nguong, QLV nao co nhieu nguoi duoi KPI), roi noi ro so tien "
    "luong/thuong tung nguoi chi C-Level hoac QLV cua chinh doi do xem duoc. "
    "Rieng M20: dung comparison_threshold_summary de lap bang KPI TDV; mau so "
    "denominator_all_tdv gom ca nguoi thieu target, employees_with_target chi la so nguoi "
    "du target duoc phan loai moc. "
    "Neu co nguoi thieu target thi neu ro, KHONG tinh ho vao nhom duoi moc 65%."
)


def _hoi_doanh_so_theo_nhom_hang(q_folded: str) -> bool:
    """Cau hoi doanh so/doanh thu theo nhom hang (da bo dau)."""
    return "nhom hang" in q_folded and any(marker in q_folded for marker in ("doanh so", "doanh thu"))


def _required_tool_for_request(question: str, tools_for_request: list[dict],
                               scope_channel: str = None) -> tuple:
    """(tool bat buoc, ghi chu them vao system dong) theo cau hoi VA danh sach tool cua vai tro."""
    tool = _required_tool_for_question(question)
    names = {t["name"] for t in tools_for_request}
    # 15/09/2026: tai khoan kenh ETC hoi "doanh so thang nay theo cac nhom hang" (khong ghi ETC) - nhom
    # hang cua kenh ETC la ItemTypeETC. Chi ap cho tai khoan ETC de khong cuop cau nhom hang cua OTC.
    if (tool is None and str(scope_channel or "").strip().upper() == "ETC"
            and "get_etc_revenue_by_item_type" in names
            and _hoi_doanh_so_theo_nhom_hang(_fold_for_route(question))):
        return "get_etc_revenue_by_item_type", ""
    if (tool in _SALARY_SENSITIVE_TEMPLATE_NAMES and tool not in names
            and _SALARY_FALLBACK_TOOL in names):
        return _SALARY_FALLBACK_TOOL, "\n\n" + _SALARY_FALLBACK_NOTE
    return tool, ""


def _tools_for_question(tools: list[dict], question: str) -> list[dict]:
    allowed = [tool for tool in tools if not _customer_tool_conflict(tool["name"], question)]
    return _cache_tools([{k: v for k, v in tool.items() if k != "cache_control"}
                         for tool in allowed]) if len(allowed) != len(tools) else tools


def _tools_for_request(scope_area_code: str = None, scope_channel: str = None,
                       scope_role: str = None, scope_employee_code: str = None) -> list[dict]:
    """Phan quyen tool o tang code, dung chung cho ask va ask_stream."""
    if scope_role is not None and scope_role not in {
        "c_level", "admin_ops", "regional_director", "qlv"
    }:
        return []
    tools = ALL_TOOLS
    if scope_area_code or scope_channel:
        tools = [tool for tool in tools if tool["name"] not in RAW_SQL_TOOLS]
    elif scope_role not in LIVE_SQL_ALLOWED_ROLES:
        tools = [tool for tool in tools if tool["name"] not in LIVE_SQL_TOOL_NAMES]
    if scope_channel:
        tools = [
            tool for tool in tools
            if template_available_for_channel(
                tool["name"], scope_channel, scope_employee_code
            )
        ]
    # Bao cao luong la du lieu ca nhan nhay cam. regional_director da bi chan fail-closed o
    # call_template(), nen khong duoc quang cao cac tool nay cho model de no thu lap 5 lan, cham
    # gioi han tool va bo sot phan doanh thu/KPI cua cung cau hoi (M20 UAT 07/09).
    if scope_role == "regional_director":
        tools = [tool for tool in tools if tool["name"] not in _SALARY_SENSITIVE_TEMPLATE_NAMES]
    if (scope_role not in {"c_level", "admin_ops"} or scope_area_code
            or scope_channel or scope_employee_code):
        tools = [tool for tool in tools if tool["name"] != "get_revenue_view_reconciliation"]
    return ALL_TOOLS_CACHED if tools is ALL_TOOLS else _cache_tools(tools)


_SCHEMA_COVERAGE_ERROR_MARKERS = (
    "no such table",
    "no such column",
    "has no column named",
    "invalid object name",
    "invalid column name",
)


def _raw_query_payload(result: dict, db: str, question: str) -> dict:
    if result.get("ok"):
        return {
            "columns": result["columns"],
            "rows": result["rows"][:MAX_ROWS_TO_MODEL],
            "row_count": result["row_count"],
            "truncated": result.get("truncated", False),
            "database": result.get("database", db),
        }

    payload = {"error": result.get("error", "Loi truy van khong xac dinh")}
    error_lower = payload["error"].lower()
    # C02 UAT: c.area_code da bi model lap lai nhieu lan du schema khong co cot nay. Day khong phai
    # loi thieu bang/can fallback SQL Server; phai sua JOIN ngay trong warehouse: invoice -> customer
    # -> city_id -> dim_tinhthanhpho.area_code. Gui huong dan cu the de vong tiep theo khong thu lai
    # cung mot SQL sai roi cat ket qua tra loi.
    if db == "local" and "no such column: c.area_code" in error_lower:
        payload["query_correction"] = (
            "Khong lap lai truy van nay. dms_khachhang/dmssx_khachhang khong co area_code: "
            "LEFT JOIN khach theo customer_code, sau do LEFT JOIN dim_tinhthanhpho theo city_id va "
            "dung tp.area_code. Giu LEFT JOIN de khong lam mat khach mo coi."
        )
        payload["next_action"] = (
            "Sua JOIN theo query_correction roi goi query_database MOT LAN voi SQL da sua. "
            "Day la cot sai trong bang local da co, khong phai thieu nguon SQL Server."
        )
        return payload
    if db == "local" and any(marker in error_lower for marker in _SCHEMA_COVERAGE_ERROR_MARKERS):
        try:
            payload["sql_server_catalog_fallback"] = search_sql_catalog(
                question, limit=8, include_definition=False
            )
            payload["next_action"] = (
                "Warehouse khong phu schema nay. Dung object/cot trong catalog fallback de tao T-SQL "
                "va goi query_sql_server neu tool kha dung; khong ket luan la khong truy cap duoc du lieu."
            )
        except Exception as exc:
            payload["catalog_error"] = str(exc)[:180]
    return payload


# 26/09/2026 (Cost of Value, C02): chuoi 12 thang ~20 KB (27 KB sau khi them ETC theo mien) vuot MAX_PAYLOAD_CHARS nen
# ban rut gon chung chi con 5/12 (roi 3/12) thang; model goi lai get_revenue_monthly_series voi 12 -> 6 -> 3 thang de
# thay du (query_runs may 24 16-17/09: 3-4 lan goi, 5 vong, 12-13 nghin dong/luot). Dang bang: ten cot ghi mot lan.
_COT_THANG = ("month", "revenue", "plan_revenue", "achievement_pct", "plan_variance", "otc_revenue",
              "plan_otc_revenue", "etc_revenue", "plan_etc_revenue", "invoices", "mom_delta", "mom_pct",
              "yoy_delta", "yoy_pct", "s02_otc_actual", "s02_otc_achievement_pct", "s02_otc_plan_variance",
              "otc_mien_khop_tong", "etc_mien_khop_tong")
_COT_OTC_MIEN = ("month", "area_code", "otc_revenue", "plan_otc_revenue", "achievement_pct", "plan_variance")
_COT_ETC_MIEN = ("month", "area_code", "etc_revenue")
_COT_KENH_DAC_BIET = ("month", "name", "area_code", "revenue", "plan_revenue", "achievement_pct")
_KHOA_THANG_DA_GOM = set(_COT_THANG) | {
    "otc_by_region", "s02_otc_company", "otc_region_reconciliation", "etc_by_region", "etc_region_reconciliation",
    "etc_plan_by_region", "etc_region_note", "otc_special_channels", "target_source"}


def _so_gon(v, pct=False):
    if isinstance(v, float):
        return round(v, 2) if pct else (int(round(v)) if abs(v) >= 1 else round(v, 2))
    return v


def _chuoi_thang_dang_bang(data: dict) -> dict:
    thang, otc_mien, etc_mien, kenh, ghi_chu = [], [], [], [], {}
    nguon_otc_mien, nguon_ke_hoach, ghi_chu_etc = set(), set(), None
    for m in data["months"]:
        if not isinstance(m, dict):
            continue
        s02 = m.get("s02_otc_company") or {}
        otc_rec = m.get("otc_region_reconciliation") or {}
        etc_rec = m.get("etc_region_reconciliation") or {}
        dong = dict(m, s02_otc_actual=s02.get("actual"), s02_otc_achievement_pct=s02.get("achievement_pct"),
                    s02_otc_plan_variance=s02.get("plan_variance"),
                    otc_mien_khop_tong=(bool(otc_rec.get("revenue_matches") and otc_rec.get("plan_matches"))
                                        if otc_rec else None),
                    etc_mien_khop_tong=bool(etc_rec.get("revenue_matches")) if etc_rec else None)
        thang.append([_so_gon(dong.get(c), pct=c.endswith("_pct")) for c in _COT_THANG])
        for r in m.get("otc_by_region") or []:
            otc_mien.append([m["month"]] + [_so_gon(r.get(c), pct=c.endswith("_pct")) for c in _COT_OTC_MIEN[1:]])
            if r.get("actual_source"):
                nguon_otc_mien.add(r["actual_source"])
        for r in m.get("etc_by_region") or []:
            etc_mien.append([m["month"], r.get("area_code"), _so_gon(r.get("etc_revenue"))])
        for r in m.get("otc_special_channels") or []:
            kenh.append([m["month"]] + [_so_gon(r.get(c), pct=c.endswith("_pct")) for c in _COT_KENH_DAC_BIET[1:]])
        if m.get("target_source"):
            nguon_ke_hoach.add(m["target_source"])
        ghi_chu_etc = ghi_chu_etc or m.get("etc_region_note")
        con_lai = {k: v for k, v in m.items() if k not in _KHOA_THANG_DA_GOM and v is not None}
        if con_lai:
            ghi_chu[m["month"]] = con_lai
    gon = {k: v for k, v in data.items() if k != "months"}
    gon.update({
        "cot_thang": list(_COT_THANG), "thang": thang,
        "cot_otc_theo_mien": list(_COT_OTC_MIEN), "otc_theo_mien": otc_mien,
    })
    if etc_mien:
        gon.update({"cot_etc_theo_mien": list(_COT_ETC_MIEN), "etc_theo_mien": etc_mien,
                    "etc_ke_hoach_theo_mien": None, "etc_ghi_chu": ghi_chu_etc})
    if kenh:
        gon.update({"cot_kenh_dac_biet": list(_COT_KENH_DAC_BIET), "kenh_dac_biet": kenh})
    if ghi_chu:
        gon["ghi_chu_theo_thang"] = ghi_chu
    gon["_model_view"] = {
        "mode": "bang_gon_du_thang",
        "so_thang": len(thang),
        "giai_thich": ("DU TAT CA cac thang da hoi - KHONG goi lai tool voi khung ngan hon. Moi dong 'thang' theo "
                       "'cot_thang' (s02_otc_* = s02_otc_company; *_khop_tong = doi chieu tong mien khop tong cong "
                       "ty). otc_theo_mien/etc_theo_mien/kenh_dac_biet theo cot tuong ung. Tien lam tron dong."),
        "nguon_ke_hoach": sorted(nguon_ke_hoach), "nguon_otc_theo_mien": sorted(nguon_otc_mien),
    }
    return gon


# 26/09/2026: do kich thuoc payload 52 tool tren kho dev - hai tool nay vuot MAX_PAYLOAD_CHARS nen bi cat dong:
# get_kpi_scorecard ca cong ty 23,7 KB -> model chi thay 5/20 nguoi, 5/21 QLV; get_revenue_seasonality (C08) 10,8 KB ->
# 5/12 thang moi kenh. Dang bang (ten cot ghi mot lan, gop truong con 'a.b') vua ngan sach ma giu du dong. Tool khac
# van dung ban cat chung - doi sang day can du lieu goi lai tren may 24 truoc (nhieu test UAT khoa ban cat do).
_TOOL_BANG_HOA_KHI_VUOT = {"get_kpi_scorecard", "get_revenue_seasonality"}


def _lam_tron_gon(v):
    if isinstance(v, float):
        return int(round(v)) if abs(v) >= 1000 else round(v, 3)
    return v


def _phang_mot_cap(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, dict) and v and all(not isinstance(x, (dict, list)) for x in v.values()):
            for k2, x in v.items():
                out[f"{k}.{k2}"] = x
        else:
            out[k] = v
    return out


def _bang_hoa(value):
    """list >= 3 dict phang (sau khi gop truong con) -> {"cot": [...], "dong": [[...]]}; so thuc lam tron."""
    if isinstance(value, list):
        if len(value) >= 3 and all(isinstance(x, dict) for x in value):
            dong = [_phang_mot_cap(x) for x in value]
            if all(not isinstance(v, (dict, list)) for d in dong for v in d.values()):
                cot = list(dict.fromkeys(k for d in dong for k in d))
                return {"cot": cot, "dong": [[_lam_tron_gon(d.get(c)) for c in cot] for d in dong]}
        return [_bang_hoa(x) for x in value]
    if isinstance(value, dict):
        return {k: _bang_hoa(v) for k, v in value.items()}
    return _lam_tron_gon(value)


def _payload_for_model(tool_name: str, payload, question: str):
    """Rut gon co cau truc cho tool dai, giu payload day du o last_result/UI.

    Cat chuoi JSON giua dong lam model thay 15/22 don va tu dem sai. V33 chi can chi tiet don
    fulfillment + hang tra/dieu chinh; phan tham chieu don lon thuoc cau hoi khac, nen bo khoi ban
    gui model de JSON con nguyen ven trong gioi han 6.000 ky tu.
    """
    if not isinstance(payload, dict):
        return payload
    if tool_name == "get_promotion_effectiveness":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload["du_lieu"] if wrapper else payload
        programs = data.get("programs")
        if isinstance(programs, list) and programs:
            # UAT 01 (24/09): the generic size cap sent only 8/21 December programs
            # to the model, hiding both versions of Q4.2025_NHOM_BOPHE_SIRO_.
            # Keep the complete ranked list with the measures needed to distinguish
            # orders from invoiced orders; the original payload remains in last_result.
            fields = (
                "program_id", "program_code", "program_name",
                "participating_customers", "orders", "invoiced_orders",
                "associated_revenue", "program_from", "program_to",
            )
            concise = [{key: row[key] for key in fields if key in row}
                       if isinstance(row, dict) else row for row in programs]
            data = {**data, "programs": concise}
            return {**wrapper, "du_lieu": data} if wrapper else data
    if tool_name == "get_revenue_monthly_series":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload["du_lieu"] if wrapper else payload
        if (isinstance(data.get("months"), list) and data["months"]
                and len(json.dumps(data, ensure_ascii=False, default=str)) > MAX_PAYLOAD_CHARS):
            gon = _chuoi_thang_dang_bang(data)
            gon = {**wrapper, "du_lieu": gon} if wrapper else gon
            # Dang bang van vuot (vd 24 thang) thi tra ban goc cho luoi cat chung: cat chung tren bang se cat ca
            # danh sach TEN COT va tung dong, lam hong bang.
            if len(json.dumps(gon, ensure_ascii=False, default=str)) <= MAX_PAYLOAD_CHARS:
                return gon
            return payload
    if (tool_name in _TOOL_BANG_HOA_KHI_VUOT
            and len(json.dumps(payload, ensure_ascii=False, default=str)) > MAX_PAYLOAD_CHARS):
        gon = _bang_hoa(payload)
        gon["_model_view"] = {
            "mode": "bang_gon_du_dong",
            "giai_thich": ("Danh sach dang {cot, dong}: moi dong theo thu tu 'cot'; cot 'a.b' la truong b cua a. "
                           "DU TAT CA cac dong - KHONG goi lai tool de lay them. So tien lam tron dong."),
        }
        if len(json.dumps(gon, ensure_ascii=False, default=str)) <= MAX_PAYLOAD_CHARS:
            return gon
        return payload
    normalized = " ".join("".join(
        ch for ch in unicodedata.normalize("NFD", (question or "").lower())
        if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d").split())

    if (tool_name == "get_workforce_productivity"
            and "lien tiep" in normalized and "duoi 80" in normalized):
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload["du_lieu"] if wrapper else payload
        source_rows = data.get("rows")
        if isinstance(source_rows, list):
            requested = re.search(r"\b(\d+)\s*thang\b", normalized)
            min_months = max(1, int(requested.group(1))) if requested else 3
            evaluated_month = data.get("decline_evaluated_through") or data.get("month_to")
            matches = []
            for row in source_rows:
                if (not isinstance(row, dict) or row.get("month") != evaluated_month
                        or (row.get("below_80_streak_months") or 0) < min_months):
                    continue
                actual, target = float(row.get("actual") or 0), float(row.get("target") or 0)
                matches.append({
                    "code": row.get("group_code"), "name": row.get("group_name"),
                    "achievement_pct": round(row.get("achievement_pct") or 0, 2),
                    "streak_months": row["below_80_streak_months"],
                    "gap_to_80": round(max(0, 0.8 * target - actual)),
                    "gap_to_target": round(max(0, target - actual)),
                })
            matches.sort(key=lambda row: (-row["gap_to_80"], str(row["code"])))
            group_by = data.get("group_by")
            both_levels = "ca nhan" in normalized and "doi" in normalized
            other_level = ({"manager": "employee", "employee": "manager"}.get(group_by)
                           if both_levels else None)
            compact = {
                "group_by": group_by, "month_to": data.get("month_to"),
                "month_to_is_partial": data.get("month_to_is_partial"),
                "pham_vi_kenh": data.get("pham_vi_kenh"), "data_as_of": data.get("data_as_of"),
                "streak_below_80": {
                    "evaluated_month": evaluated_month,
                    "minimum_consecutive_months": min_months,
                    "qualifying_count": len(matches),
                    "source_groups_not_shown": data.get("so_nhom_khong_hien") or 0,
                    "count_is_complete": not bool(data.get("so_nhom_khong_hien")),
                    "gap_to_80_total": sum(row["gap_to_80"] for row in matches),
                    "gap_to_target_total": sum(row["gap_to_target"] for row in matches),
                    "rows": matches,
                    "other_group_by_needed_for_both_levels": other_level,
                    "gap_definition": (
                        "gap_to_80 = so tien con thieu de dat 80% target; "
                        "gap_to_target = so tien con thieu de dat 100% target, tai thang danh gia."
                    ),
                },
            }
            return {**wrapper, "du_lieu": compact} if wrapper else compact

    if tool_name == "get_receivables_overview":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload.get("du_lieu") if wrapper else payload
        if data.get("receivable_status") != "ok":
            return payload
        top_rows = data.get("top_overdue_customers") or []
        compact_top = []
        missing_assignment = False
        for row in top_rows:
            if not isinstance(row, dict):
                continue
            compact_top.append({
                # 22/09/2026: 'rank' phai nam trong danh sach trang nay, neu khong thi truong rank
                # cua tool bi cat o day va model lai tu xep lai thu tu khi viet bang.
                key: row.get(key) for key in (
                    "rank", "customer_code", "customer_name", "balance_end", "total_overdue",
                    "employee_code", "employee_name", "manager_code", "manager_name",
                )
            })
            missing_assignment = missing_assignment or not row.get("employee_code")

        requested = int(data.get("top_overdue_requested_count") or len(compact_top))
        returned = int(data.get("top_overdue_returned_count") or len(compact_top))
        eligible = int(data.get("top_overdue_eligible_count") or returned)
        if returned < requested:
            display_rule = (
                f"Chi co {returned} khach co no qua han trong pham vi (nguoi dung yeu cau top "
                f"{requested}); noi ro day la toan bo {returned} khach tim thay, khong dien dat "
                "nhu the danh sach bi cat."
            )
        else:
            display_rule = (
                f"Nguoi dung yeu cau top {requested}; PHAI liet ke du {returned} dong trong "
                "top_overdue_customers, khong tu rut gon con top 5/top 3."
            )

        compact_data = {
            key: data.get(key) for key in (
                "receivable_status", "receivable_source", "receivable_as_of",
                "receivable_warning", "scope_area_code", "scope_channel",
                "scope_employee_code", "scope_note", "total_balance_end", "total_overdue",
                "overdue_pct", "overdue_1_15", "overdue_15_30", "overdue_30_45",
                "overdue_gt_45", "aging_bucket_note", "by_channel", "by_region",
                "ranking_basis", "by_region_note",
            )
        }
        # 22/09/2026 (cham lai UAT dnh_etc): bang theo vung chi hien MB/MN/MT, bo dong khach chua gan
        # vung nen ba mien cong lai 62,13 ty trong khi tong qua han 62,94 ty. Canh bao co so tien cu
        # the thi kho bo qua hon mot ghi chu chung chung.
        chua_gan = next((r for r in (data.get("by_region") or [])
                         if isinstance(r, dict) and str(r.get("region", "")).startswith("Khac")
                         and (r.get("total_overdue") or 0) > 0), None)
        if chua_gan:
            compact_data["by_region_warning"] = (
                f"Co {chua_gan['total_overdue']:.0f} dong no qua han thuoc nhom "
                f"'{chua_gan['region']}'. PHAI hien thanh MOT DONG rieng trong bang theo vung; bo di "
                "thi tong cac vung khong con khop total_overdue.")
        compact_data.update({
            "top_overdue_requested_count": requested,
            "top_overdue_eligible_count": eligible,
            "top_overdue_returned_count": returned,
            "top_overdue_customers": compact_top,
            "top_overdue_display_rule": display_rule,
        })
        if missing_assignment:
            compact_data["assignment_note"] = (
                "Khach khong co employee_code/manager_code thi ghi ro chua co phan cong KPI OTC; "
                "khach ETC khong co TDV/QLV truc tiep tren nguon."
            )
        # 16/09/2026: LUON kem danh sach du no lon chua qua han, bo dieu kien tu khoa. Nhat ky UAT
        # 15/09: nguoi cham hoi "vi sao thieu HCM04162" - cau do khong chua tu khoa nao trong bo loc
        # cu nen model KHONG he nhin thay danh sach va tra loi rang khach do khong co no. Tool da
        # gioi han san top 5 nen khong lam phinh payload.
        compact_data["du_no_lon_chua_qua_han"] = (data.get("du_no_lon_chua_qua_han") or [])[:5]
        if any(marker in normalized for marker in (
            "da thu", "ke hoach thu", "cam ket thu",
        )):
            compact_data["collection_activity"] = data.get("collection_activity")
        if wrapper:
            return {**payload, "du_lieu": compact_data}
        return compact_data

    if tool_name == "get_geography_monthly_performance":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload.get("du_lieu") if wrapper else payload
        rows = data.get("rows")
        if not isinstance(rows, list) or not rows:
            return payload

        # 16/09/2026 (nhat ky UAT 14:02 - "Tinh/vung do phu khach thap; co hoi trang o dau" chay 110
        # giay, 15.126 dong): tool tra 166 dong (thang x dia ban) = 103k ky tu, va tool nay CHUA co
        # nhanh thu gon nen luoi an toan cat mu con 12 dong DAU - khong phai 12 dia ban yeu nhat.
        # Model ket luan "tinh nao do phu kem" tren 7% du lieu MA VAN NOI CHAC CHAN. Thu gon co chu
        # dich: giu DU danh sach dia ban (tong ca ky) de khong dia ban nao bien mat am tham, cong
        # bang xep hang thang cuoi theo DUNG tieu chi cau hoi dang hoi.
        def _so(value):
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        chi_tieu = "customers" if any(marker in normalized for marker in (
            "do phu", "phu khach", "co hoi trang", "it khach", "khach thap",
        )) else "revenue"
        thang_cuoi = str(data.get("month_to") or "")[:7]
        dong_thang_cuoi = [r for r in rows if isinstance(r, dict)
                           and str(r.get("month") or "")[:7] == thang_cuoi]
        if not dong_thang_cuoi:
            dong_thang_cuoi = [r for r in rows if isinstance(r, dict)]

        def _tron(value):
            """Lam tron de tiet kiem cho: '17867631804.0' ton gan gap ruoi '17867631804'."""
            so = _so(value)
            return int(so) if abs(so) >= 1 else round(so, 2)

        def _gon(row):
            gon = {key: row.get(key) for key in ("unit", "area_code", "month") if row.get(key)}
            for key in ("revenue", "customers", "invoices", "revenue_per_customer"):
                if row.get(key) is not None:
                    gon[key] = _tron(row.get(key))
            return gon

        xep = sorted(dong_thang_cuoi, key=lambda r: _so(r.get(chi_tieu)))
        khach_thang_cuoi = {r.get("unit"): _tron(r.get("customers")) for r in dong_thang_cuoi}
        tong_ky = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            muc = tong_ky.setdefault(row.get("unit"), {
                "unit": row.get("unit"), "so_thang": 0, "revenue_ca_ky": 0.0,
            })
            muc["so_thang"] += 1
            muc["revenue_ca_ky"] += _so(row.get("revenue"))

        compact_data = {key: data.get(key) for key in (
            "month_from", "month_to", "dimension", "customer_count_definition",
            "so_dia_ban_khong_hien", "unavailable_dimensions", "unavailable_metrics",
            "target_gap_note", "canh_bao", "data_as_of", "month_to_is_partial",
        ) if data.get(key) is not None}
        compact_data.update({
            "tieu_chi_xep_hang": chi_tieu,
            "tong_so_dia_ban": len(tong_ky),
            "tong_so_dong_goc": len(rows),
            "thap_nhat_thang_cuoi": [_gon(r) for r in xep[:10]],
            "cao_nhat_thang_cuoi": [_gon(r) for r in reversed(xep[-5:])],
            # Danh sach nay PHAI DU (64 tinh that tren may 24). Giu dang gon nhat co the - so nguyen,
            # bo cot thua - de tong payload nam duoi MAX_PAYLOAD_CHARS: neu vuot, luoi an toan se cat
            # xuong 12 dia ban va tai dien dung loi dang di sua.
            "tong_ca_ky_theo_dia_ban": [
                {"unit": m["unit"], "revenue_ca_ky": _tron(m["revenue_ca_ky"]),
                 "khach_thang_cuoi": khach_thang_cuoi.get(m["unit"])}
                for m in sorted(tong_ky.values(), key=lambda m: -m["revenue_ca_ky"])
            ],
            "display_rule": (
                f"thap_nhat_thang_cuoi/cao_nhat_thang_cuoi la xep hang thang {thang_cuoi} theo "
                f"'{chi_tieu}'. tong_ca_ky_theo_dia_ban liet ke DU {len(tong_ky)} dia ban nen KHONG "
                "duoc ket luan thieu dia ban nao. Chuoi tung thang cua tung dia ban khong gui kem; "
                "can thi goi lai tool voi pham vi hep hon (it dia ban hoac it thang), KHONG doan."
            ),
        })
        if wrapper:
            return {**payload, "du_lieu": compact_data}
        return compact_data

    if tool_name == "get_customer_cohort_retention":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload.get("du_lieu") if wrapper else payload
        cohorts = data.get("cohorts")
        if not isinstance(cohorts, list) or not cohorts:
            return payload

        # 24/09/2026 (UAT C30): 16 cohort x 4 tuoi dang dict day du vuot MAX_PAYLOAD_CHARS, luoi
        # an toan cat con 12 cohort DAU. Ngay 23/09 model mat cohort 06-08/2026 roi viet "quá mới nên
        # tuổi 1-3 tháng cũng chưa tròn kỳ" - sai, 06 va 07/2026 da co so tuoi 1. Ngay 21/09 model
        # viet "chưa có cohort nào đủ 12 tháng" trong khi 06-08/2025 co so. Gui bang gon DU moi cohort.
        def _pct(value):
            return None if value is None else round(float(value), 1)

        def _ty_le(retention, tien_to=""):
            cot = {}
            for r in retention or []:
                tuoi = r.get("age_month")
                cot[f"{tien_to}t{tuoi}"] = _pct(r.get("retention_pct"))
                if r.get("retention_pct_tam_tinh") is not None:
                    cot[f"{tien_to}t{tuoi}_tam_tinh"] = _pct(r.get("retention_pct_tam_tinh"))
            return cot

        # 24/09/2026 (chay lai C30 sau deploy ad2a047): khoi IsNC gui RIENG thi model bo qua, chi
        # nhac 1 dong ghi chu va van goi cot 324 khach (lan dau co hoa don) la "cohort mo moi" - dung
        # loi nguoi cham da ghi. Ghep IsNC vao CUNG dong cua bang chinh, va doi ten cot hoa don.
        isnc = data.get("cohort_theo_isnc")
        isnc_ok = isinstance(isnc, dict) and isnc.get("status") == "ok"
        isnc_theo_thang = ({c.get("cohort_month"): c for c in isnc.get("cohorts") or []
                            if isinstance(c, dict)} if isnc_ok else {})
        bang = []
        for c in cohorts:
            if not isinstance(c, dict):
                continue
            dong = {"cohort": c.get("cohort_month"),
                    "khach_lan_dau_co_hoa_don": c.get("cohort_customers")}
            if c.get("group") not in (None, "ALL"):
                dong["nhom"] = c.get("group")
            if c.get("cohort_is_left_censored"):
                dong["kiem_duyet_trai"] = True
            dong.update(_ty_le(c.get("retention")))
            ghep = isnc_theo_thang.get(c.get("cohort_month"))
            if ghep:
                dong["khach_mo_moi_isnc"] = ghep.get("cohort_customers")
                dong.update(_ty_le(ghep.get("retention"), "isnc_"))
            bang.append(dong)
        co_so = {}
        for tuoi in data.get("ages") or []:
            thang = [d["cohort"] for d in bang
                     if d.get(f"t{tuoi}") is not None and not d.get("kiem_duyet_trai")]
            co_so[f"t{tuoi}"] = {"so_cohort": len(thang), "tu": min(thang) if thang else None,
                                 "den": max(thang) if thang else None}
        compact_data = {key: data.get(key) for key in (
            "definition", "cohort_from", "cohort_to", "group_by", "ages", "cohort_from_da_mo_rong",
            "ly_do_mo_rong_cua_so", "left_censored_cohort_months", "valid_cohort_count",
            "pham_vi_du_lieu_co_that", "latest_complete_month", "pham_vi_kenh", "canh_bao",
            "luu_y_doi_chieu", "ghi_chu_hai_dinh_nghia", "tam_tinh_thang_chua_tron", "data_as_of",
        ) if data.get(key) is not None}
        compact_data.update({
            "tong_so_cohort": len(bang),
            "bang_cohort": bang,
            "cohort_co_so_theo_tuoi": co_so,
            "cach_doc": (
                "tN = % khach cua cohort con mua dung thang tuoi N; null = thang dich chua tron, KHONG "
                "phai 0%. tN_tam_tinh = so tam tinh den ngay du lieu cua thang dang chay. bang_cohort "
                f"liet ke DU {len(bang)} cohort; KHONG duoc noi 'chua co cohort nao du tuoi N' khi "
                "cohort_co_so_theo_tuoi.tN.so_cohort > 0, va phai neu ca cohort moi nhat co so."),
        })
        if isinstance(isnc, dict):
            compact_data["cohort_theo_isnc"] = (
                {key: isnc.get(key) for key in ("status", "definition", "gioi_han")
                 if isnc.get(key) is not None} if isnc_ok else isnc)
        if isnc_theo_thang:
            thang_isnc = sorted(isnc_theo_thang)
            compact_data["cach_trinh_bay_bat_buoc"] = (
                "Bang tra loi PHAI co HAI cot so khach: 'Khach lan dau co hoa don' (khach_lan_dau_co_"
                "hoa_don) va 'Khach mo moi (IsNC)' (khach_mo_moi_isnc, cung so khach moi cua C29/M24), "
                f"cot IsNC dien cho {', '.join(thang_isnc)} va de trong o thang khac vi kho chua co "
                "snapshot. Ty le giu chan theo IsNC (isnc_tN) dat canh ty le hoa don cua cung dong. "
                "KHONG duoc goi khach_lan_dau_co_hoa_don la 'khach mo moi'. Neu ro vi sao IsNC lon hon "
                "(khach Bravo gan co mo moi co the da tung mua truoc do).")
        if wrapper:
            return {**payload, "du_lieu": compact_data}
        return compact_data

    if tool_name == "get_customer_product_coverage" and payload.get("mode") == "product":
        # 18/09/2026 (cau M33): payload tho cua nhanh nay do duoc 500.156 ky tu - gap 50 lan ngan
        # sach 10.000. Bo rut gon chung ha dan 12 -> 8 -> 5 -> 3 -> 1 -> 0 dong, va o buoc 0 thi MOI
        # danh sach SKU thanh mang rong trong khi cac so dem vo huong van con. Chatbot vi the bao
        # dung "cong cu tra ve tong so dem (68 giam, 94 tang, 68 mat ty trong) nhung khong kem danh
        # sach chi tiet tung ma SKU" - lan thu NAM cua lop loi danh sach bi cat am tham.
        # Phinh vi sau danh sach cung chua LAI ca dong day du ~40 truong cua cung mot SKU.
        # Cau hoi that la "SKU nao giam VI SAO", nen gom thang theo nguyen nhan chinh thay vi tra
        # sau danh sach chong cheo.
        def _so(value):
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        def _tron(value):
            so = _so(value)
            return int(so) if abs(so) >= 1 else round(so, 2)

        def _gon(row):
            ten = str(row.get("name") or "")
            return {
                "ma": row.get("code"),
                "ten": (ten[:44] + "...") if len(ten) > 47 else ten,
                "doanh_thu": _tron(row.get("revenue")),
                "thay_doi": _tron(row.get("revenue_delta")),
                "khach_thay_doi": _tron(row.get("customers_delta")),
                "don_thay_doi": _tron(row.get("orders_delta")),
            }

        giam = [r for r in (payload.get("largest_revenue_declines") or []) if isinstance(r, dict)]
        tang = [r for r in (payload.get("largest_revenue_increases") or []) if isinstance(r, dict)]
        mat_ty_trong = [r for r in (payload.get("largest_internal_share_losses") or [])
                        if isinstance(r, dict)]
        theo_nguyen_nhan = {}
        for row in giam:
            khoa = row.get("primary_decline_driver") or "OTHER_OR_MIXED"
            muc = theo_nguyen_nhan.setdefault(khoa, {"so_sku": 0, "tong_muc_giam": 0.0, "dan_dau": []})
            muc["so_sku"] += 1
            muc["tong_muc_giam"] += _so(row.get("revenue_delta"))
        for khoa, muc in theo_nguyen_nhan.items():
            cung_nhom = [r for r in giam if (r.get("primary_decline_driver") or "OTHER_OR_MIXED") == khoa]
            cung_nhom.sort(key=lambda r: _so(r.get("revenue_delta")))
            muc["dan_dau"] = [_gon(r) for r in cung_nhom[:8]]
            muc["so_sku_chua_liet_ke"] = max(0, muc["so_sku"] - len(muc["dan_dau"]))
            muc["tong_muc_giam"] = _tron(muc["tong_muc_giam"])

        compact = {key: payload.get(key) for key in (
            "mode", "window_days", "current_period", "previous_period", "comparison_basis",
            "scope_totals", "reconciliation", "customer_count_definition",
            "decline_driver_definition", "canh_bao", "data_as_of",
        ) if payload.get(key) is not None}
        compact.update({
            "so_sku_giam": len(giam),
            "so_sku_tang": len(tang),
            "so_sku_mat_ty_trong_noi_bo": len(mat_ty_trong),
            "sku_giam_theo_nguyen_nhan": dict(sorted(
                theo_nguyen_nhan.items(), key=lambda kv: kv[1]["tong_muc_giam"])),
            "sku_tang_dan_dau": [_gon(r) for r in tang[:8]],
            "sku_mat_ty_trong_dan_dau": [
                {**_gon(r), "ty_trong_giam_diem": round(_so(r.get("internal_share_delta_pct_points")), 2)}
                for r in mat_ty_trong[:8]],
            "display_rule": (
                f"Da co DU danh sach {len(giam)} SKU giam, gom theo nguyen nhan chinh; moi nhom cho "
                "toi da 8 ma giam manh nhat kem so_sku_chua_liet_ke. PHAI tra loi bang cac ma cu the "
                "nay - TUYET DOI khong noi la khong co danh sach chi tiet. Muon xem het mot nhom thi "
                "goi lai tool voi pham vi hep hon (it thang hon hoac mot vung), KHONG doan."),
        })
        return compact

    if tool_name == "get_employee_kpi":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload.get("du_lieu") if wrapper else payload
        monthly_key = next((key for key in (
            "monthly_threshold_summary", "monthly_team_threshold_summary"
        ) if isinstance(data.get(key), dict)), None)
        if monthly_key:
            # C45/M12: call_template da tinh bang tung thang nhung ban nen cu bo mat ca
            # khoi nay, chi gui danh sach nhan vien cua MOT snapshot. Dong goi theo cot
            # de giu du moi thang/vung/chuc danh trong ngan sach 10.000 ky tu.
            monthly = data[monthly_key]
            columns = ["month", "manager_code"] if monthly_key == "monthly_team_threshold_summary" else [
                "month", "area_code", "position_code"]
            columns += ["employees_with_target", "count_gate", "count_80", "count_100", "count_120",
                        "pct_gate", "pct_80", "pct_100", "pct_120"]
            if monthly_key == "monthly_team_threshold_summary":
                columns += ["pct_gate_change_vs_previous_month", "pct_gate_rolling_3_month_avg"]

            def _cell(row, key):
                value = row.get(key)
                return round(value, 2) if key.startswith("pct_") and isinstance(value, (int, float)) else value

            compact_monthly = {
                "month_from": monthly.get("month_from"),
                "month_to": monthly.get("month_to"),
                "group_by": monthly.get("group_by"),
                "channel_scope": monthly.get("channel_scope"),
                "columns": columns,
                "rows": [[_cell(row, key) for key in columns]
                         for row in monthly.get("rows", []) if isinstance(row, dict)],
                "definition": monthly.get("definition"),
            }
            compact_data = {
                "as_of": data.get("as_of"),
                monthly_key: compact_monthly,
                "pham_vi_du_lieu": data.get("pham_vi_du_lieu"),
                "answer_rule": (
                    "Dung bang theo tung thang o tren lam nguon cho cau hoi nay; columns la ten cot "
                    "cua tung mang trong rows. Mau so la employees_with_target cua CHINH thang/vung/"
                    "chuc danh (hoac doi). KHONG lay total_employees/threshold_summary cua snapshot "
                    "mot ngay de thay cho chuoi thang. Kenh du lieu chi la OTC neu channel_scope=OTC."
                ),
            }
            if wrapper:
                return {**payload, "du_lieu": compact_data}
            return compact_data
        rows = data.get("rows") or []
        compact_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            compact_rows.append({
                "employee_code": row.get("employee_code"),
                "name": row.get("name"),
                "position_code": row.get("position_code"),
                "sales": row.get("sales"),
                "target": row.get("target"),
                "pct": round(float(row.get("pct") or 0), 2),
                "threshold": row.get("threshold"),
                "status": row.get("status"),
                **({"la_nhom_kenh": True} if row.get("la_nhom_kenh") else {}),
                # 14/09/2026: giu team_detail - bo nen nay tung chi giu 8 cot, se xoa mat doi cua QLV
                # va dua model quay lai do tung QLV bang nhieu vong goi.
                **({"team_detail_count": row.get("team_detail_count"),
                    "team_detail": [
                        {k: t.get(k) for k in ("employee_code", "name", "sales", "target", "pct")}
                        for t in (row.get("team_detail") or []) if isinstance(t, dict)
                    ]} if "team_detail" in row else {}),
            })

        compact_data = {
            key: data.get(key) for key in (
                "as_of", "total_employees", "roster_employees", "unassessed_count",
                "missing_current_snapshot_count", "unassessed_rows_truncated",
                "count_below_target", "count_above_target", "count_kpi_achieved",
                "kpi_threshold_pct", "count_full_target", "full_target_pct",
                "threshold_summary", "kpi_source", "position_code", "comparison_basis",
                "comparison_threshold_summary",
            )
        }
        compact_data["rows_returned"] = len(compact_rows)
        compact_data["rows"] = compact_rows

        manager_intent = any(marker in normalized for marker in (
            "qlv nao co nhieu", "theo tung qlv", "theo qlv", "phan hut cua doi tap trung",
        ))
        if manager_intent:
            # M13 chi can xep QLV theo SO NGUOI duoi KPI. Bo ban sao day du cua moi TDV trong
            # tung manager (danh sach phang da co o rows), chi giu so dem de payload khong lap.
            compact_data["below_kpi_by_manager"] = [
                {
                    "manager_code": item.get("manager_code"),
                    "manager_name": item.get("manager_name"),
                    "count_below_kpi": item.get("count_below_kpi"),
                }
                for item in (data.get("below_kpi_by_manager") or [])
                if isinstance(item, dict)
            ]
        if data.get("unassessed_rows"):
            compact_data["unassessed_rows"] = [
                {key: item.get(key) for key in ("employee_code", "name", "reason")}
                for item in data["unassessed_rows"]
                if isinstance(item, dict)
            ]
        # 22/09/2026 (cham lai UAT chosi.mn): cau "tinh hinh thuc hien KPI" van chi ra doanh so vs
        # chi tieu. Mot dong dan trong mo ta tool khong du - liet ke CAC CAU PHAN CON THIEU ngay
        # trong payload thi model moi neu ra, giong cach by_region_warning va __dang_liet_ke da chay.
        if "kpi" in normalized:
            compact_data["cau_phan_kpi_ngoai_tool_nay"] = {
                "chua_co_trong_ket_qua_nay": ["thuong san pham danh muc", "V15", "V22",
                                              "khach hang ASO (hoac Active Customer cho CS/TK)",
                                              "tong trong so KPI"],
                "lay_o_dau": ["get_salary_achievement_summary", "get_salary_aso_detail"],
                "answer_rule": ("Tool nay CHI co doanh so vs chi tieu. Neu khong goi them cac tool tren "
                                "thi PHAI noi ro nhung cau phan liet ke o day chua duoc tinh, khong duoc "
                                "trinh bay doanh so vs chi tieu nhu la toan bo KPI. V25 da dung tu "
                                "01/07/2026 nen khong dua vao."),
            }
        if wrapper:
            return {**payload, "du_lieu": compact_data}
        return compact_data

    if tool_name == "get_inventory_expiry_report":
        wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
        data = payload.get("du_lieu") if wrapper else payload
        supply = data.get("supply_risk") or {}
        risk_rows = supply.get("rows") if isinstance(supply, dict) else []
        risk_rows = risk_rows if isinstance(risk_rows, list) else []
        # Ty le ton/ban chua quy doi don vi va co the lech khac nhau theo tung SKU.
        # Giu trong ket qua goc de doi chieu, nhung khong dua con so nay cho model.
        shown_risks = [
            {key: value for key, value in row.items() if key != "months_of_cover"}
            for row in risk_rows[:6] if isinstance(row, dict)
        ]
        shown_codes = {row.get("item_code") for row in shown_risks if isinstance(row, dict)}
        candidates = supply.get("recent_customer_candidates") or []
        shown_candidates = [item for item in candidates if (
            isinstance(item, dict) and item.get("item_code") in shown_codes
        )][:3]
        compact_supply = {
            key: value for key, value in supply.items()
            if key not in {"rows", "recent_customer_candidates"}
        }
        compact_supply.update({
            "rows_shown_to_model": len(shown_risks),
            "rows_not_shown_to_model": max(0, len(risk_rows) - len(shown_risks)),
            "rows_are_sample": len(risk_rows) > len(shown_risks),
            "rows": shown_risks,
            "recent_customer_candidates": shown_candidates,
            "customer_candidate_groups_shown": len(shown_candidates),
        })
        asks_expiry = any(marker in normalized for marker in (
            "can date", "han su dung", "het han", "gan han",
        ))
        expiry_rows = data.get("rows") or []
        compact_data = {
            "as_of": data.get("as_of"),
            "area_code": data.get("area_code"),
            "summary": data.get("summary"),
            "khong_xac_dinh_han": data.get("khong_xac_dinh_han"),
            "expiry_rows": expiry_rows[:3] if asks_expiry else [],
            "expiry_rows_are_sample": bool(asks_expiry and len(expiry_rows) > 3),
            "supply_risk": compact_supply,
            "sync_warning": data.get("sync_warning"),
            "pham_vi_du_lieu": data.get("pham_vi_du_lieu"),
        }
        if wrapper:
            return {**payload, "du_lieu": compact_data}
        return compact_data

    if tool_name != "check_order_timing":
        return payload
    fulfillment_intent = any(marker in normalized for marker in (
        "don nao bi huy", "don bi huy", "don huy", "giao/hoa don cham", "giao hoa don cham",
        "giao cham", "hoa don cham", "chua tim thay hoa don", "chua co hoa don", "chua hoa don",
    ))
    if not fulfillment_intent:
        return payload

    wrapper = payload if isinstance(payload.get("du_lieu"), dict) else None
    data = payload.get("du_lieu") if wrapper else payload
    fulfillment = data.get("order_fulfillment_exceptions") or {}
    rows = fulfillment.get("rows") if isinstance(fulfillment, dict) else []
    rows = rows if isinstance(rows, list) else []
    shown = rows[:12]
    compact_fulfillment = {
        key: value for key, value in fulfillment.items() if key != "rows"
    }
    compact_fulfillment.update({
        "rows_shown_to_model": len(shown),
        "rows_not_shown_to_model": max(0, len(rows) - len(shown)),
        "rows_are_sample": len(rows) > len(shown),
        "rows": shown,
    })
    top_detail = data.get("top_detail") or []
    return_detail = [row for row in top_detail if (
        isinstance(row, dict) and "HANG_TRA_DIEU_CHINH" in (row.get("reasons") or [])
    )][:10]
    compact_data = {
        "date_from": data.get("date_from"),
        "date_to": data.get("date_to"),
        "period_defaulted": data.get("period_defaulted"),
        "order_fulfillment_exceptions": compact_fulfillment,
        "returns": data.get("returns"),
        "return_adjustment_detail": return_detail,
        "return_adjustment_detail_truncated": sum(
            1 for row in top_detail if isinstance(row, dict)
            and "HANG_TRA_DIEU_CHINH" in (row.get("reasons") or [])
        ) > len(return_detail),
        "created_at_doc_date_check": data.get("created_at_doc_date_check"),
        "unavailable_checks": data.get("unavailable_checks"),
        "pham_vi_du_lieu": data.get("pham_vi_du_lieu"),
        "data_as_of": data.get("data_as_of"),
        "warning": data.get("warning"),
    }
    if wrapper:
        return {**payload, "du_lieu": compact_data}
    return compact_data


def _normalize_tool_input_for_question(tool_name: str, tool_input: dict, question: str) -> dict:
    """Sua tham so an toan cho cac intent co mot cach goi chuan, truoc khi tao van tay/chay tool.

    Khong thay scope phan quyen. Ham chi ngan model xin limit qua nho o cau hoi can danh sach day du.
    """
    args = dict(tool_input or {})
    q = " ".join("".join(
        ch for ch in unicodedata.normalize("NFD", (question or "").lower())
        if unicodedata.category(ch) != "Mn"
    ).replace("đ", "d").split())

    # Neu nguoi dung noi ro can DANH SACH ma khong dat top N, lay du mot lan o tang tool. Context
    # gui model van duoc dong goi gon va model phai noi dang liet ke bao nhieu tren tong.
    asks_complete_list = (
        any(marker in q for marker in ("danh sach", "toan bo", "tat ca", "nhung ai"))
        and not re.search(r"\btop\s*\d+\b", q)
    )
    tool_definition = next((item for item in ALL_TOOLS if item.get("name") == tool_name), None)
    supports_limit = bool(
        tool_definition
        and "limit" in ((tool_definition.get("input_schema") or {}).get("properties") or {})
    )
    if asks_complete_list and supports_limit:
        args["limit"] = max(200, int(args.get("limit") or 0))

    if tool_name == "get_receivables_overview":
        # So luong nguoi dung noi ro la hop dong cua cau hoi. Neu model gui top_n nho hon cho cau
        # "top 10", ep lai o backend de khong phu thuoc cach model goi.
        requested_top = re.search(r"\btop\s*(\d{1,3})\b", q)
        if requested_top:
            args["top_n"] = min(100, max(1, int(requested_top.group(1))))
        return args

    if tool_name == "get_customer_product_coverage" and args.get("mode") == "product":
        # 24/09/2026 (UAT M33, cham 22/09): cau "SKU DT giam do it khach/it don/giam luong/giam gia
        # ban" khong neu ky, model tu chon lookback_months=3 -> so 01/07-22/09 voi 08/04-30/06 (co
        # thang dang chay, cua so lech thang). Checker S72 so THANG TRON voi thang truoc. Do tren may
        # 24: cung ky thi tool khop S72 tung SKU; khac ky thi ket luan nguoc chieu (Siro ho bo phe
        # -8,98 ty theo 3 thang nhung +5,74 ty T8 so T7). Khong neu ky -> ep ve ky cua S72.
        nguyen_nhan = sum(marker in q for marker in ("it khach", "it don", "giam luong", "giam gia"))
        neu_ky = re.search(
            r"thang\s*\d|\bt\d{1,2}\b|\bquy\b|nam\s*(nay|truoc|\d{4})|\d{1,2}/\d{2,4}|\d+\s*thang|"
            r"\btuan\b|\bngay\b|\bmtd\b|\bytd\b|thang nay|thang truoc|ky nay|\btu\s+\d", q)
        if nguyen_nhan >= 2 and not neu_ky:
            from report_templates import _latest_complete_revenue_month, _month_bounds
            args["as_of_date"] = _month_bounds(_latest_complete_revenue_month())[1]
            args["lookback_months"] = 1
        return args

    if tool_name == "get_workforce_productivity":
        if "lien tiep" in q and "duoi 80" in q:
            # Include three complete months even when month_to is an in-progress month, and keep
            # every employee/team in the source before making a short model-facing view.
            requested = re.search(r"\b(\d+)\s*thang\b", q)
            min_months = max(1, int(requested.group(1))) if requested else 3
            args["months_back"] = max(min_months + 1, int(args.get("months_back") or 0))
            args["limit"] = max(1000, int(args.get("limit") or 0))
        return args

    if tool_name != "get_employee_kpi":
        return args
    asks_threshold_list = (
        any(marker in q for marker in ("danh sach", "nhung ai", "nhan vien", "tdv", "qlv"))
        and any(marker in q for marker in ("duoi", "khong dat", "chua dat"))
        and re.search(r"\b(?:60|65|70|80|100|120)\s*%", q)
    )
    if not asks_threshold_list:
        return args
    args["limit"] = max(200, int(args.get("limit") or 0))
    args["filter"] = "below_target"
    if not args.get("position_code") and any(marker in q for marker in (
        "nhan vien ban hang", "trinh duoc vien", "tdv",
    )):
        args["position_code"] = "TDV"
    return args


def _compact_collections_for_model(value, max_items: int, path: str, overview: list):
    """Giu tong/metadata, rut gon cac collection dai ma khong pha JSON."""
    if isinstance(value, list):
        shown = min(len(value), max_items)
        if shown < len(value):
            overview.append({"path": path or "$", "total": len(value), "shown": shown})
        return [
            _compact_collections_for_model(item, max_items, f"{path}[{index}]", overview)
            for index, item in enumerate(value[:shown])
        ]
    if isinstance(value, dict):
        # 22/09/2026 (UAT doi QLV TM23100148): danh sach bi cat con 12 dong, model doc 12 dong roi
        # viet "Tong cong 12 khach" trong khi total_pending_customers=27 va _model_view.collections
        # deu ghi 27. Moc bao "dang liet ke" o CUNG CAP voi danh sach, khong de rieng cuoi payload -
        # cho dong ke ben thi model khong bo qua duoc nhu mot muc long o cuoi.
        compacted = {}
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else key
            compacted[key] = _compact_collections_for_model(item, max_items, child_path, overview)
            if isinstance(item, list) and len(item) > max_items:
                compacted[f"{key}__dang_liet_ke"] = (
                    f"Dang liet ke {max_items}/{len(item)} dong cua '{key}'. Tong THAT la {len(item)}; "
                    f"KHONG duoc noi tong bang so dong dang hien, va phai ghi ro dang liet ke mot phan.")
        return compacted
    if isinstance(value, str) and len(value) > 800:
        overview.append({"path": path or "$", "total_chars": len(value), "shown_chars": 800})
        return value[:800]
    return value


def _serialize_payload_for_model(tool_name: str, payload, question: str) -> str:
    """Dong goi context dung-du-ngan trong MAX_PAYLOAD_CHARS, luon la JSON hop le.

    Payload day du van nam trong ``last_result`` (log/doi chieu). Model nhan tong va metadata
    chinh xac cung mot bang uu tien vua ngan sach; khong bao gio nhan nua chuoi JSON bi chat giua dong.
    """
    model_payload = _payload_for_model(tool_name, payload, question)
    if not isinstance(model_payload, (dict, list)):
        return str(model_payload)

    encoded = json.dumps(model_payload, ensure_ascii=False, default=_json_mac_dinh)
    if len(encoded) <= MAX_PAYLOAD_CHARS:
        return encoded

    for max_items in (12, 8, 5, 3, 1, 0):
        overview = []
        concise = _compact_collections_for_model(model_payload, max_items, "", overview)
        if isinstance(concise, dict):
            concise = dict(concise)
            concise["_model_view"] = {
                "mode": "concise_priority_view",
                "collections": overview,
                "answer_rule": _QUY_TAC_LIET_KE_MOT_PHAN,
            }
        else:
            concise = {
                "rows": concise,
                "_model_view": {
                    "mode": "concise_priority_view",
                    "collections": overview,
                    "answer_rule": _QUY_TAC_LIET_KE_MOT_PHAN,
                },
            }
        encoded = json.dumps(concise, ensure_ascii=False, default=_json_mac_dinh)
        if len(encoded) <= MAX_PAYLOAD_CHARS:
            return encoded

    # Luoi an toan cuoi: lay cac truong vo huong/metadata o cap dau thay vi cat giua chuoi.
    # Cac tong/so dem cap dau thuong la can cu chinh de cau tra loi van dung va du y.
    view = {
        "mode": "summary_only",
        "answer_rule": ("Chi co cac tong/so dem, KHONG co danh sach chi tiet: tra loi bang cac tong va "
                        "de nghi nguoi dung thu hep pham vi (theo vung/doi/thang) de xem tung dong."),
    }
    summary = {"_model_view": view}
    scalar_items = [
        (key, value) for key, value in model_payload.items()
        if not isinstance(value, (dict, list)) and not (isinstance(value, str) and len(value) > 800)
    ] if isinstance(model_payload, dict) else []
    priority_markers = (
        "total", "count", "sum", "revenue", "sales", "target", "status",
        "period", "date", "month", "as_of", "from", "to", "threshold", "scope",
    )
    scalar_items.sort(
        key=lambda item: (
            not any(marker in str(item[0]).lower() for marker in priority_markers),
            str(item[0]),
        )
    )
    for key, value in scalar_items:
        candidate = dict(summary)
        candidate[key] = value
        encoded = json.dumps(candidate, ensure_ascii=False, default=_json_mac_dinh)
        if len(encoded) <= MAX_PAYLOAD_CHARS:
            summary = candidate
    return json.dumps(summary, ensure_ascii=False, default=_json_mac_dinh)

# Beta header can thiet de dung TTL 1h (mac dinh cache_control chi song 5 phut neu khong co header nay).
# Ap dung cho toan bo request (system + tools) - giup cache song qua nhieu cau hoi lien tiep trong gio
# hanh chinh thay vi het han sau vai phut, tang ty le cache-hit (chi ~10% gia input goc khi hit).
_CACHE_BETA_HEADERS = ({"anthropic-beta": "extended-cache-ttl-2025-04-11"} if IS_ANTHROPIC else {})


def _llm_client():
    """Client goi model. Doc key theo thu tu LLM_API_KEY -> ANTHROPIC_API_KEY de doi nha cung cap
    ma khong phai xoa key cu (doi lai chi can bo LLM_* la ve Claude ngay)."""
    from llm_provider import resolve_api_key
    key = resolve_api_key()   # thu tu uu tien dinh nghia MOT cho, xem llm_provider.py
    # CHI truyen base_url khi thuc su doi nha cung cap. Truyen base_url=None cung la them mot doi so,
    # va cac test dang gia lap anthropic.Anthropic bang lambda chi nhan api_key se vo ngay
    # (da dinh: test_repeated_tool_call_is_not_reexecuted_and_forces_final_answer). Giu duong mac dinh
    # goi y het truoc day thi khong the lam hong thu gi dang chay.
    if LLM_BASE_URL:
        return anthropic.Anthropic(api_key=key, base_url=LLM_BASE_URL)
    return anthropic.Anthropic(api_key=key)


def _static_system_prompt() -> str:
    """Phan TINH cua system prompt (quy tac + schema) - KHONG bao gio doi giua cac lan goi, nen danh
    cache_control (TTL 1h) o day. Moc ngay du lieu ("hom nay") la phan DONG, tach rieng o
    _dynamic_context_note() de khong lam vo cache moi 15-30 phut khi kho dong bo lai."""
    return f"""Ban la AI Analyst chuyen phan tich du lieu kinh doanh cho Duoc Nam Ha (DNH),
mot doanh nghiep duoc pham. Nguoi dung se hoi bang tieng Viet ve doanh thu, cong no, KPI nhan vien,
ton kho, vung mien... Ban dung cac tool duoc cung cap de truy van du lieu THAT. Bao cao chuan uu tien
warehouse.db da doi chieu; du lieu chua duoc warehouse phu thi tim trong catalog va doc SQL Server
live neu tai khoan duoc phep. Tra loi dua tren ket qua da truy van - KHONG duoc bia so lieu.

Neu cuoc hoi thoai co cac luot truoc do, HAY DUNG NGU CANH DO de hieu cau hoi hien tai (vd neu vua
hoi "doanh thu thang 6" roi hoi tiep "con thang 5?", hieu la van hoi doanh thu theo kenh/tieu chi
tuong tu nhung doi sang thang 5) - KHONG hoi lai nguoi dung nhung gi da ro tu ngu canh truoc.

14/09/2026: cau hoi TIEP NOI kieu "chi tiet ca N [doi tuong]", "xem chi tiet di", "con [X] thi sao"
sau mot bao cao - neu tham so con mo ho (vd "chi tiet" khong noi xep theo doanh so, % dat hay danh
sach thieu chi tieu) thi CHON MOT cach hieu hop ly nhat theo ngu canh (thuong: xep theo doanh so/gia
tri chinh cua bao cao truoc), GOI TOOL DUNG 1 LAN, noi ro dang xem theo tieu chi nao va moi nguoi
dung yeu cau lai neu can. TUYET DOI KHONG goi lai CUNG tool nhieu lan voi tham so khac nhau (vd
order_by='sales' roi order_by='pct' roi filter='below_target') de do y nguoi dung - vua cham vua
khong chac dung y.

QUAN TRONG VE CHON TOOL:
- CTKM: moi lan hoi C13/M35/V34 PHAI doc moc promotion_link_coverage_to vua tra ve tu
  get_promotion_effectiveness; KHONG lap lai moc 09/01/2026 cua lan kiem cu neu chua kiem lai nguon.
  Doanh thu/DiscountRate tren hoa don KHONG chung minh chuong trinh hien tai. M36 hoi chiet khau,
  hang tra va hang tang theo vung, khong tu dong doi thanh cau hoi CTKM.
- ⚠️  KHONG BAO GIO nhac ten tool/ham/truong ky thuat trong cau tra loi cho nguoi dung. Nguoi doc la
  lanh dao kinh doanh, khong phai lap trinh vien. VD SAI: "tra cuu chi tiet (get_customer_detail)",
  "count_full_target = 0", "[tien ich] resolve_relative_date(...)". VD DUNG: "toi co the tra cuu chi
  tiet tung khach hang de xem ai phu trach". Mo ta viec lam bang ngon ngu nghiep vu, giau het ten ky
  thuat ben trong.
- KET LUAN PHAI GIOI HAN THEO BANG CHUNG: neu bat ky phan cot loi ma nguoi dung hoi (vd doanh thu,
  KPI, thuong) chua kiem chung duoc vi thieu quyen, loi nguon, bi bo qua hay cham gioi han truy van,
  PHAI noi ro "chua the ket luan toan dien". TUYET DOI khong viet "khong phat hien bat thuong",
  "da khop" hay "binh thuong" cho TOAN BO cau hoi khi con phan chua kiem chung. Chi ket luan trong
  pham vi tung phan da co bang chung.
- Neu cau hoi thuoc cac nhom bao cao chuan: doanh thu theo kenh, top san pham, top khach hang, doanh thu
  theo vung mien, KPI/doanh so nhan vien (tong quan/thang), KPI THEO NGAY 1 nhan vien ca nhan, SO SANH
  2 khoang thoi gian, CHI TIET 1 khach hang cu the, TRA CUU ma/ten/vai tro nhan vien, KIEM TRA hang
  tra/phan bo gia tri don, TON KHO THEO VUNG, TON KHO SAP/DA HET HAN SU DUNG THEO LO, LICH SU DOI QLV,
  CAY DOANH THU/KPI TP-QLV-TDV, XEP HANG KPI, DOI CHIEU doanh thu tu tren xuong vs cong don tu duoi len,
  LICH SU TRUY VAN/CHI PHI AI cua chinh nguoi dang hoi, HIEU QUA CHUONG TRINH KHUYEN MAI, QUY TAC/BAC
  TIEN V15-V22-V25-ASO, THUONG KINH DOANH/PHU CAP thang cua 1 nhan vien -> BAT BUOC dung tool tuong ung
  (get_revenue_by_channel, get_top_products, get_top_customers, get_revenue_by_region, get_employee_kpi,
  get_employee_daily_kpi, compare_periods, get_revenue_ytd_cumulative, get_customer_detail, get_employee_directory, check_order_timing,
  get_inventory_by_region, get_inventory_expiry_report, get_qlv_change_history, get_revenue_tree,
  get_kpi_ranking, get_revenue_reconciliation, get_receivables_overview, get_customer_revenue_debt_risk,
  get_audit_log, get_promotion_effectiveness, get_promotion_data_quality,
  get_salary_bonus_policy, get_salary_data_quality, get_salary_detail,
  get_salary_achievement_summary).
- PHAM VI LA DU LIEU BAT BUOC, KHONG PHAI LOI VAN: neu payload co pham_vi_du_lieu.loai=DOI_CUA_QLV
  thi MOI con so trong payload la cua RIENG DOI do. TUYET DOI KHONG goi no la "toan vung", "toan
  mien" hay "toan cong ty", ke ca khi ma vung cung xuat hien. Neu tool YTD tra 9,82 ty cho tai khoan
  QLV thi do van la YTD CUA DOI, khong duoc doi nhan thanh YTD cua mien.
- Khi so sanh thang dang chay voi thang truoc, PHAI cung do dai theo diem trong chu ky: 01-N thang
  nay so 01-N thang truoc. KHONG so MTD voi ca thang truoc; KHONG so 01-04 voi 28-31 thang truoc.
- KHONG tu ket luan "khong phu thuoc vai don lon" chi vi so don/AOV cung tang. Muon ket luan do tap
  trung PHAI doc order_value_distribution (top share). Nguong >3x trung vi chi la THAM CHIEU chua
  duoc DNH phe duyet, khong duoc gan nhan gian lan.
- SO KHACH MUA THAT CUA DOI trong mot ky: BAT BUOC doc get_customer_product_coverage.scope_totals
  .current.customers (COUNT DISTINCT ma khach tren hoa don sau khi da loc DU doi). KHONG cong cot
  customers cua tung TDV, KHONG dung employee_kpi.new_customers, va KHONG dung cac co is_nc/is_ro/
  is_ac thay cho tong khach mua. Day la so dem that, khong duoc goi la "uoc tinh". Neu ket qua khac
  mot bao cao cu, uu tien scope_totals va kiem tra canh_bao phan giai DMSId.
- HIEU QUA CTKM: BAT BUOC goi get_promotion_effectiveness DUNG 1 LAN. KHONG duoc GROUP BY cot CTKM
  tren vHoaDon/vHoaDonTotal: cot do la ghi chu tu do, co the chua ten nguoi va so dien thoai. Doanh
  thu chuong trinh phai noi qua DMS_DonHangCTKM -> DMS_CTKM. Neu tool bao nguon lien ket chi den mot
  moc cu, noi ro moc do; KHONG lay ghi chu hoa don thay the va KHONG suy dien phan thieu. Khi trinh bay
  tung CTKM, BAT BUOC ghi ro program_code, program_name va period do tool tra ve. Neu status=source_gap,
  PHAI neu dung promotion_link_coverage_to + requested_period va noi ro day la lo hong dong bo, KHONG
  phai bang chung ky do khong co CTKM; khong noi chung chung "khong co du lieu".
- CHAT LUONG/DO PHU CTKM (moc du lieu, link mat don/mat ma chuong trinh): BAT BUOC goi
  get_promotion_data_quality DUNG 1 LAN; KHONG search catalog/query SQL thu cong.
- CACH TINH/BAC TIEN V15/V22/V25/ASO: BAT BUOC goi get_salary_bonus_policy DUNG 1 LAN. Neu tool phat
  hien bang quy tac, stored procedure va so da chot khong khop, PHAI neu ro chenh lech va van phan
  biet 'so SQL Server da chot' voi 'so theo bang quy tac'; KHONG tu sua so thay ke toan/DNH.
- QUY TAC IS_AC/ASO DNH XAC NHAN 27/08/2026: CS (Cho si) va TK (kenh MT/Modern Trade) dung co
  is_ac/Active Customer, KHONG co ASO. Neu dong du lieu da co is_ac thi tuyet doi khong gan, hien thi
  hoac cong them ASO cho dong do. Khi tra bao cao CS/TK, dung chi so Active Customer; chi dung ASO
  cho cac vai tro khac khi nguon tinh luong co ghi nhan.
- CHI PHI THUONG/DOANH THU: BAT BUOC goi get_salary_achievement_summary va dung cost_summary.
  Dung total_bonus va employee_tier_sales trong CUNG dong thang; mau so chi gom TDV/CTV/CS/TK de
  tranh nhan doi doanh thu rollup cap quan ly. Kho khong co loi nhuan/gross margin: KHONG duoc tu
  ket luan ve loi nhuan, tuong quan hay tang truong ben vung.
- LUONG KHACH: Khi hoi tong doanh thu khach moi/tai kich hoat bu duoc bao nhieu doanh thu khach
  dung mua, BAT BUOC dung summary_all_customers cua get_customer_movement. Top-N chi dung de liet ke
  vi du, khong duoc suy ra tong cua ca doi.
- DOI CHIEU DM1/DM2/DM3-TOTALPOINT, KIEM TRA LCB, CHAT LUONG SNAPSHOT LUONG: BAT BUOC goi
  get_salary_data_quality DUNG 1 LAN voi check_type tuong ung; KHONG tu doc prompt roi ket luan va
  KHONG search catalog/query SQL thu cong.
- CHAT LUONG ROSTER/TARGET/MANAGER (C54/M28/V17): BAT BUOC tach tang nhan vien va tang quan ly.
  missing_manager/missing_target co mau so employee_tier_employees, KHONG phai tong roster. Tuyet doi
  khong viet "toan bo roster deu co manager" khi management_rows_without_parent_in_source > 0.
  missing_target_with_sales la TAP CON cua missing_target: moi ma chi liet ke MOT LAN va danh dau uu tien
  ngay tai dong do, KHONG noi hai danh sach roi ghep trung. future_dated_lines chi la chung tu co ngay lon
  hon future_date_cutoff (ngay he thong); giao dich sau mot snapshot LICH SU khong phai chung tu tuong lai.
- Cau hoi ket hop KHACH DOANH THU LON + CONG NO CAO + XU HUONG MUA GIAM: goi
  get_customer_revenue_debt_risk DUNG 1 LAN. Tool da noi hai ky doanh thu voi snapshot cong no;
  KHONG tach thanh nhieu tool/query lap lai.
- DU BAO TUONG LAI DA TAT: TUYET DOI KHONG du bao, du phong, uoc tinh, ngoai suy hoac tu tinh mot
  gia tri tuong lai cho doanh thu, doanh so, KPI, cong no, ton kho, khach hang hay "kha nang dat".
  Khong duoc dung SQL tu do de lach quy tac nay. Neu nguoi dung yeu cau du bao, noi ro tinh nang da
  tat de uu tien do dung va goi y cac lua chon DU LIEU THAT: luy ke den ngay, so sanh ky lich su,
  KPI thuc dat so voi chi tieu da nhap, va thoi diem cap nhat du lieu. Chi tieu/ke hoach cua ky tuong
  lai da duoc con nguoi nhap san van la du lieu thuc te co the tra cuu; khong duoc bien no thanh du bao.
- Neu cau hoi co NHIEU khia canh cung luc (vd hoi ca doanh thu, top san pham, vung mien, nhan vien
  trong 1 cau) -> goi TUAN TU nhieu tool tuong ung, moi tool 1 khia canh, roi tong hop lai.
- TOP SAN PHAM THEO KENH: neu nguoi dung yeu cau tach hoac so sanh top san pham OTC va ETC, BAT BUOC
  goi get_top_products HAI LAN voi cung khoang ngay/limit: mot lan channel=OTC va mot lan channel=ETC.
  KHONG dung channel=ALL trong truong hop nay, vi ALL gop doanh thu hai kenh cua cung ma san pham va
  khong con hai bang xep hang doc lap. Cau tra loi phai ghi ro bang OTC va bang ETC rieng.
- CHI TIET THEO KHU VUC (hop tien do 24/09/2026): cau hoi top khach hang, cong no, san pham/SKU, doanh
  thu ma KHONG gioi han vung -> trinh bay kem chi tiet theo mien (MB/MT/MN) tu truong mien/theo_mien/
  by_area/theo_vung ma tool da tra. Tai khoan da bi gioi han mot vung thi khong can tach.
  Cap 2/3 = mien -> QLV/TDV -> khach -> SKU: top khach/SKU cua 1 TDV hoac doi 1 QLV dung employee_code,
  SKU cua 1 khach dung customer_code tren get_top_customers/get_top_products; KHONG tu viet SQL.
- CONG NO: cau hoi TONG HOP/nhieu khach (tong no qua han, top khach no, ty le qua han theo vung/kenh)
  -> dung get_receivables_overview. Cong no cua 1 khach cu the -> get_customer_detail. CONG NO da
  KHONG con tren Supabase - TUYET DOI khong truy van receivable_detail/receivable_etc (bang cu, da chan).
  Neu hoi SO DA THU TRONG THANG/KE HOACH THU/CAM KET THU QUA HAN, doc collection_activity trong
  get_receivables_overview: collection_activity tra but toan BC/PT vao tai khoan 131 theo khach/TDV
  phu trach hien tai trong thang, nhung CHUA co ke hoach thu hay bang cam ket. Tra phan thu duoc,
  noi ro pham vi va phan thieu nguon; KHONG lay chenh lech snapshot lam tien da thu.
- HOP DONG/GOI THAU ETC (C44/M42): BAT BUOC get_etc_contract_status, khoa vHoaDonETCTotal.ContractId
  da duoc kiem chung; phu luc cuon ve Id0. KHONG ghep bang khach hang + SKU. Gia tri con lai la chua
  xuat hoa don TRUOC VAT, KHONG phai chua giai ngan/thanh toan. Duoi 50% la chi bao sang loc, chua
  chung minh cham lich giao hang. Dung danh sach con lai lon nhat va sap het han cung nguong tool tra.
  PHAI noi ro cong no qua han theo hop dong (cong_no_theo_hop_dong) chua kiem chung: NULL khong phai 0; khong gan no khach cho tung
  hop dong, khong suy no qua han tu phan chua xuat. Tong khong gom gia tri bat thuong; so dem day du
  khac so dong mau va cac nhom co the chong lan. Doc canh_bao ve gioi han metadata lich su.
- Voi phan cau hoi KHONG thuoc cac nhom tren: thu query_database tren warehouse truoc neu schema da
  mo ta. Neu warehouse KHONG CO object/cot can thiet, BAT BUOC dung search_sql_server_catalog de tim
  trong TOAN BO SQL Server da duoc cap quyen, sau do dung query_sql_server (neu tool kha dung) de doc
  live. TUYET DOI KHONG noi "khong truy cap/khong den duoc du lieu" chi vi schema viet tay khong liet
  ke bang do; chi ket luan thieu sau khi da tim catalog va thu truy van, va phai noi ro loi that neu co.
  query_sql_server dung T-SQL (TOP, dbo.[Object]), query_database dung SQLite (LIMIT).
  Neu can boc tach cong no ad-hoc ngoai 2 tool cong no chuan, van uu tien fact_congno_khachhang trong
  warehouse vi day la snapshot da chuan hoa tu SP goc; khong tu EXEC stored procedure bat ky.
- TON KHO snapshot Supabase cu chi dung khi cau hoi dung pham vi bang inventory da xac nhan. Neu hoi
  table/view ton kho khac tren Bravo, tim catalog SQL Server; khong tu suy dien months_to_sell.
- Cau hoi CO cum tu thoi gian TUONG DOI (hom nay, tuan nay, thang truoc, quy nay, quy truoc, cung ky
  nam ngoai, N thang/ngay gan nhat...) -> BAT BUOC goi resolve_relative_date TRUOC de lay khoang ngay
  cu the, roi moi dung ket qua do lam date_from/date_to cho tool khac - TUYET DOI KHONG tu suy luan
  ngay thang, de tranh nham quy/thang. Neu resolve_relative_date bao loi (khong nhan dien duoc cum
  tu), hoi lai nguoi dung ngay/khoang ngay cu the thay vi doan bua.
- Neu nguoi dung dinh nghia 1 thuat ngu nghiep vu moi trong cau hoi (vd "doanh thu rong la doanh thu
  tru chiet khau") -> goi save_business_term de luu lai, roi tiep tuc tra loi cau hoi nhu binh thuong.
- Voi KPI nhan vien TONG QUAN/xep hang/nhieu nhan vien cung luc (ke ca ma khu vuc nhu MBKV*, ASM*):
  dung get_employee_kpi. CO BA MOC KHAC NHAU, TUYET DOI KHONG GOP - va dung goi moc 65%/70% la
  "dat chi tieu" HAY "dat KPI": do chi la cong BAT DAU DUOC HUONG THUONG NHOM HANG.
    - Hoi "ai chua dat chi tieu / bao nhieu nguoi dat chi tieu" -> dung "count_full_target" (moc 100%).
      Giua thang con so nay gan nhu luon ~0 va DO LA DUNG, khong phai loi: doanh so moi luy ke toi hom
      nay con chi tieu la ca thang. Noi ro dieu do thay vi de nguoi doc tuong he thong hong.
    - Hoi "ai dat KPI / bao nhieu nguoi dat KPI" -> dung "count_kpi_achieved" (moc 80%, truong
      "kpi_threshold_pct"), AP DUNG CHUNG cho moi vai tro. Day cung la moc quyet dinh mau 🟢/🟡/🔴.
    - Hoi "ai toi muc thuong nhom hang" -> dung "count_above_target"/"count_below_target", nguong lay
      tu truong "threshold" cua tung dong (TDV 65% theo QD 0107/2026, QLV va cac cap quan ly 70% theo
      QD 0429/.25 - van hieu luc voi cap quan ly).
    - Nguoi dat 67%: dien dat dung la "da toi muc thuong nhom hang (65%) nhung CHUA dat KPI (80%)".
    - Cau hoi mo ho -> dua CA BA con so kem nhan ro rang, dung tu chon 1 cai roi im lang.
    - Snapshot GIUA THANG chi la doanh so luy ke den ngay, trong khi target la ca thang. Dau thang giai thich
      vi sao % chua cao nhung KHONG phai bang chung rang muc do do "binh thuong". Neu khong co ke hoach phan
      bo target theo ngay/nhan su thi PHAI noi "chua du co so ket luan nhip do binh thuong hay bat thuong";
      chi ghi nhan % thuc dat. KHONG duoc viet "khong co ai lech bat thuong" chi vi moi dau chu ky.
    - KHONG bao gio in ten truong ky thuat ra cho nguoi dung (vd dung viet "count_full_target = 0").
      Nguoi doc la lanh dao kinh doanh, khong phai lap trinh vien - noi "0/87 nguoi dat chi tieu".
  ⚠️ 65%/70% CHI la cong cua THUONG NHOM HANG (DM1/DM2/DM3). DNH con it nhat 5 ho thuong khac, moc
  khac va tra theo CHI SO KHAC: V15/V22/V25 (tien do theo cac moc ngay), ASO (khach hang hoat dong;
  chi ap dung cho vai tro khong phai CS/TK),
  thuong quy va thuong nam. Bac, nguong va hieu luc cu the PHAI doc bang get_salary_bonus_policy,
  KHONG dung mot con so viet san trong prompt cho moi ky/vai tro. Luong co ban: tu 60% tro len
  van huong 100%, duoi 60% moi bi cat ty le. => Nguoi duoi 65% VAN CO THE duoc V15/ASO va VAN huong
  du luong co ban. TUYET DOI KHONG duoc dien dat thanh "khong duoc thuong", "khong dat KPI", "bi cat
  thuong" - do la noi SAI ve tien luong cua nguoi that. Chi duoc noi dung pham vi: "chua toi muc
  thuong nhom hang". He thong co so V15/V22/V25/ASO DA CHOT trong FACT_ThongKeTinhLuong; dung
  get_salary_detail/get_salary_ranking de doc so thuc te, dung get_salary_bonus_policy de giai thich.
  Truong "status" (🟢 Tot / 🟡 Trung binh / 🔴 Nguy hiem) chia theo moc DAT KPI 80% (KHONG phai muc
  huong thuong 65/70%) - LUON dat emoji nay canh ten/ma NV, khong tu nghi nguong khac. Vi du dung:
  "TDV Nguyen Van A dat 67% chi tieu - da toi muc thuong nhom hang cua TDV (65%) nhung CHUA dat KPI
  (80%), va chua dat chi tieu 100%". Voi QLV dat 67% thi VAN duoi cong thuong nhom hang 70%.
- Voi KPI THEO NGAY cua 1 nhan vien CA NHAN cu the trong 1 thang (vd "hieu suat hang ngay cua tungtx
  thang 7", "ngay nao tungtx do KPI") -> dung get_employee_daily_kpi. Nguong theo NGAY khac hoan toan
  nguong thang: 🔴 Do <2.5%, 🟡 Vang 2.5%-3.5%, 🟢 Xanh >3.5% (target ngay = 4% MonthSaleTarget). Tool
  nay KHONG dung duoc cho ma khu vuc/quan ly vung.
- Voi 1 khach hang CU THE (biet ma khach hang, hoi doanh thu/cong no/ai phu trach...) -> dung
  get_customer_detail. Ket qua co san "position_label" (vd "Trinh duoc vien"/"Quan ly vung") cho biet
  VAI TRO cua nhan vien phu trach - LUON neu ro vai tro nay khi tra loi. Khach hang kenh ETC thuan tuy
  se KHONG co nhan vien phu trach (employee_code/employee_name/position_label rong) - day la HAN CHE DU
  LIEU THUC TE (ETC khong co truong nay tren Bravo), KHONG phai loi, giai thich ro cho nguoi dung neu gap.

{SCHEMA_CONTEXT}

- TIET KIEM TOKEN VA TOC DO: VOI BAT KY TOOL NAO (get_salary_detail, get_customer_detail, get_employee_daily_kpi...), KHI CAN XEM NHIEU DOI TUONG (NHIEU NV, NHIEU KHACH HANG) -> TRUYEN DANH SACH CAC MA PHAN CACH BANG DAU PHAY (vd employee_code='NV1,NV2,NV3', customer_code='KH1,KH2,KH3') TRONG DUNG 1 LAN GOI TOOL DUY NHAT. TUYET DOI KHONG GOI TOOL MULTI-ROUNDS TAP LAP LAI DANG LE RA DUNG BANG BULK.

QUAN TRONG VE DO DAI CAU TRA LOI (tiet kiem chi phi - moi token output deu tinh tien):
- MOI CAU TRA LOI PHAI DAT BA TIEU CHI: DUNG - DU - NGAN GON HET SUC CO THE. DUNG = chi dung so lieu
  va pham vi da kiem chung. DU = tra loi du cac y nguoi dung hoi va dung tong/so dem cua TOAN BO tap,
  khong danh dong bang mau uu tien voi toan bo du lieu. NGAN = chon it cau/it cot nhat van truyen du y.
- Tra loi NGAN GON, DI THANG vao so lieu - KHONG mo dau dai dong, KHONG nhac lai cau hoi, KHONG giai
  thich lai nhung gi tool da tra ve neu nguoi dung khong hoi "tai sao"/"giai thich".
  neu chi 1 con so thi neu ro con so + don vi + ngu canh (vd "ngay nao", "khach hang nao") trong 1-2 cau,
  KHONG viet thanh doan van dai. Neu ket qua co nhieu dong, dung BANG (markdown table) thay vi mo ta
  bang loi van. Chi mo rong nhan xet/phan tich khi nguoi dung hoi ro "vi sao"/"nhan xet"/"danh gia".
- Neu tool tra ve loi hoac khong co du lieu phu hop, noi ngan gon cho nguoi dung, khong doan bua.

TIET KIEM TOKEN - QUAN TRONG:
- Sau khi nhan du lieu tu tool, TRA LOI NGAY cho nguoi dung. Chi goi THEM tool khi: (a) tool truoc bao
  LOI/khong co du lieu can thu lai, hoac (b) cau hoi co NHIEU khia canh rieng biet can tool KHAC LOAI.
- TUYET DOI KHONG goi lai CUNG tool voi tham so tuong tu chi de "kiem tra lai" hay "xac nhan".
- Neu payload co `_model_view`, dung tong/so dem toan bo de ket luan; bang chi tiet chi neu cac muc uu
  tien can hanh dong. Neu chi liet ke mot phan, ghi mot dong "Đang liệt kê N/T ..." (N = so dong da
  neu, T = tong). KHONG hua "Tải Excel để xem đầy đủ": nut Tai Excel chi xuat dung bang dang hien thi.
- TUYET DOI KHONG noi voi nguoi dung ve payload/context, gioi han ky thuat, so dong bi an, `truncated`,
  `returned_count`, `not_shown_count`, "bi cat bot", "gioi han hien thi" hoac ten tool noi bo.

MA KEM TEN (15/09/2026):
- MOI ma san pham (item_code) va ma nhan vien/QLV (employee_code, manager_code) hien thi cho nguoi dung
  PHAI kem ten, dang "ma - ten" (vd "TM25010183 - Nguyen Thi Hong Thuy", "31190000680 - Siro thuoc ho bo
  phe Nam Ha"). Lay ten tu ket qua tool (item_name, employee_name, manager_name, name). Neu ket qua khong
  co ten thi ghi "chua co ten trong danh muc", KHONG tu dat ten.

THOI DIEM DU LIEU:
- Backend se tu gan nguon, moc du lieu, moc dong bo va canh bao do moi sau khi cau tra loi hoan tat.
- KHONG tu viet dong "Du lieu cap nhat den...", KHONG chep timestamp tu lich su hoi thoai va KHONG
  doan thoi diem dong bo. Chi tong hop noi dung nghiep vu tu ket qua tool.
"""


# Cac tool nhan DANH SACH ma ngan cach bang dau phay -> nhieu lenh goi trong CUNG mot luot co the gop
# lam mot, tiet kiem token. Gia tri = ten tham so chua ma. CHI duoc them tool vao day khi tool do THAT
# SU co tham so nay VA ham xu ly biet tach chuoi "A,B,C" - xem get_salary_detail lam mau.
# CANH BAO (10/08/2026): da tung co nguoi dinh them "get_employee_kpi": "employee_code" - SAI, tool do
# khong he co tham so employee_code (chi co as_of_date/limit/order_by/filter/position_code). Them nham
# se lam moi lenh goi thu 2 tro di cua tool do bi bo trong im lang.
BULK_TOOLS_MAP = {
    "get_salary_detail": "employee_code",
    "get_customer_detail": "customer_code",
    "get_employee_daily_kpi": "employee_code",
}


def _merge_bulk_tool_calls(tool_uses, bulk_tools_map=None):
    """Gop nhieu lenh goi CUNG mot tool trong CUNG mot luot thanh mot lenh goi duy nhat mang danh sach
    ma ngan cach bang dau phay. Tra ve tap id cua cac lenh goi DA BI GOP vao lenh khac (caller phai
    tra ve tool_result gia cho chung de giu dung hop dong cua Anthropic API).

    SUA 10/08/2026 - VA HAI LOI GAY MAT DU LIEU AM THAM. Ban cu (nam lan trong ask()) lam the nay:

        if codes:
            ... gop ...
        for sub in tu_list[1:]:        # <-- NAM NGOAI khoi `if codes:`
            merged_sub_ids.add(sub.id)

    1. DANH DAU "da gop" KE CA KHI KHONG GOP DUOC GI. Khi tool khong co tham so khoa (vd bi them nham
       vao bang), `codes` rong nen khong gop gi ca, NHUNG cac lenh goi thu 2 tro di van bi danh dau va
       bi bo. Model nhan lai dung cau "Da gop ket qua tra cuu hang loat vao luot goi truoc" - mot loi
       noi doi - roi tra loi tu tin bang du lieu thieu.
    2. CHI GOP MOT THAM SO KHOA, AM THAM VUT MOI THAM SO KHAC. Hoi "so sanh doanh so khach X thang 7
       voi thang 8" -> model goi get_customer_detail 2 lan CUNG customer_code nhung KHAC date_from/
       date_to. Sau khu trung, codes chi con ['X'], lenh goi thu 2 bi bo -> model chi co thang 7 nhung
       tuong da co ca hai.

    Cach sua: gom cac lenh goi theo "van tay" = toan bo tham so NGOAI khoa gop. Chi gop trong cung mot
    nhom (tuc la moi thu khac deu giong het, chi khac moi ma). Va chi danh dau da-gop khi THUC SU gop.
    Khac tham so -> de chay rieng, tha ton them mot luot con hon tra so thieu ma khong ai biet.
    """
    if bulk_tools_map is None:
        bulk_tools_map = BULK_TOOLS_MAP

    merged_sub_ids = set()
    tool_by_name = defaultdict(list)
    for tu in tool_uses:
        tool_by_name[tu.name].append(tu)

    for name, tu_list in tool_by_name.items():
        if name not in bulk_tools_map or len(tu_list) <= 1:
            continue
        param_name = bulk_tools_map[name]

        # Van tay: moi tham so TRU khoa gop. json.dumps de gia tri dict/list cung so sanh duoc
        # (tham so cua tool khong phai luc nao cung la chuoi/so).
        groups = defaultdict(list)
        for tu in tu_list:
            fingerprint = tuple(sorted(
                (k, json.dumps(v, sort_keys=True, ensure_ascii=False, default=str))
                for k, v in (tu.input or {}).items() if k != param_name
            ))
            groups[fingerprint].append(tu)

        for grp in groups.values():
            if len(grp) <= 1:
                continue
            codes = []
            for sc in grp:
                val = ((sc.input or {}).get(param_name) or "")
                val = val.strip() if isinstance(val, str) else str(val).strip()
                if val and val not in codes:
                    codes.append(val)
            if not codes:
                # Khong lay duoc ma nao -> tool nay khong co tham so khoa (bi them nham vao bang).
                # TUYET DOI khong danh dau da-gop o day - de tat ca chay binh thuong. Day chinh la
                # loi (1) neu tren: ban cu van danh dau, khien lenh goi thu 2 bi bo trong im lang.
                continue
            # Den day: cung tool, cung moi tham so phu, chi khac ma (hoac trung hoan toan) -> gop
            # an toan. codes co 1 phan tu nghia la cac lenh goi trung het nhau, gop lai la dung.
            primary = grp[0]
            merged_input = dict(primary.input or {})
            merged_input[param_name] = ",".join(codes)
            primary.input = merged_input
            for sub in grp[1:]:
                merged_sub_ids.add(sub.id)

    return merged_sub_ids


def _tool_call_key(name: str, tool_input: dict) -> str:
    """Van tay on dinh de khong chay lai cung tool+cung tham so trong mot cau hoi."""
    return f"{name}:{json.dumps(tool_input or {}, sort_keys=True, ensure_ascii=False, default=str)}"


_FORCE_FINAL_ANSWER = (
    "Dung goi them cong cu. Hay tra loi CUOI CUNG ngay tu du lieu da lay. "
    "Khong duoc noi 'cau hoi qua phuc tap'. Neu du lieu chua du de ket luan, neu CHINH XAC phan nao "
    "da doi chieu duoc, phan nao con thieu hoac nguon nao bi dut; khong hien bang trung gian nhu ket "
    "qua cuoi va khong bia so."
)


def _response_text(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _dynamic_context_note(question: str = "", session_id: str = "", scope_area_code: str = None,
                           scope_employee_code: str = None, scope_channel: str = None,
                           username: str = None, scope_role: str = None) -> str:
    """Phan DONG cua system prompt (ngay du lieu + ngu canh doi theo tung cau hoi) - tach rieng khoi
    phan tinh de KHONG lam vo cache (kho local dong bo lai moi 15-30 phut, glossary/query-state doi
    theo tung cau hoi nen KHONG the cache chung voi schema/rules tinh)."""
    latest = latest_data_date()
    parts = [f'Ngay co du lieu moi nhat trong kho hien tai: {latest} (dung lam moc cho "hom nay"/'
             f'"gan day" neu nguoi dung khong noi ro ngay; kho local co the tre toi da ~15-30 phut so voi Bravo that).']

    # 19/08/2026: sync_freshness_note() da ton tai tu 20/07/2026 (kiem tra tien trinh sync co TREO
    # khong, khac latest_data_date() chi biet NGAY du lieu moi nhat chu khong biet sync con song hay
    # khong) nhung CHUA TUNG duoc noi vao day - phat hien lai qua ke hoach 11-08/2026, van con nguyen
    # sau hon 1 tuan. Ham tu tra chuoi RONG khi binh thuong (khong lam vo cau tra loi/cache khi sync
    # on dinh), chi len tieng khi qua han - an toan de goi vo dieu kien o day.
    freshness_warning = sync_freshness_note()
    if freshness_warning:
        parts.append(freshness_warning)

    parts.append(
        "Backend tu gan footer do moi theo dung nguon da truy van. Model KHONG duoc lap lai timestamp "
        "trong lich su hoac tu viet dong 'Du lieu cap nhat den'."
    )

    if scope_area_code:
        parts.append(
            f'QUAN TRONG - TAI KHOAN NAY BI GIOI HAN VUNG {scope_area_code}: moi tool bao cao da duoc '
            f'EP LOC theo dung vung nay o tang he thong (khong the vo tinh lo du lieu vung khac du AI '
            f'co lam gi). Neu nguoi dung hoi ve 1 vung KHAC (vd hoi "mien Nam" trong khi tai khoan chi '
            f'duoc xem {scope_area_code}), hoac hoi CHUNG CHUNG kieu "ca cong ty"/"toan quoc" - PHAI TU '
            f'CHOI RO RANG, giai thich tai khoan chi co quyen xem vung {scope_area_code}, KHONG duoc tra '
            f'loi bang so lieu vung {scope_area_code} nhu the la dung cau hoi (gay hieu nham). Tool tra '
            f'cuu SQL tu do (query_database) KHONG kha dung cho tai khoan nay. '
            f'MOI cau tra loi co so lieu (ke ca khi nguoi dung KHONG hoi ro vung) PHAI ghi ro dang "(vung '
            f'{scope_area_code})" ngay canh con so - de nguoi dung luon biet day la so lieu da bi gioi han '
            f'vung, khong phai so lieu toan quoc/vung khac.'
        )
    if scope_role == "regional_director":
        parts.append(
            "TAI KHOAN GIAM DOC MIEN/KENH KHONG CO QUYEN xem luong/thuong ca nhan chi tiet. "
            "Cac bao cao luong da duoc an khoi danh sach tra cuu; khong thu goi lai bang cach khac. "
            "Neu cau hoi gom ca thuong va KPI/doanh thu, chi tra phan KPI/doanh thu co bang chung va "
            "ket luan ro rang rang chua the doi chieu thuong thuc chi/toan dien."
        )
    if scope_employee_code:
        parts.append(
            # 23/07/2026: PHAI noi ro AI dang phuc vu AI - truoc day note nay khong he cho biet ma nhan
            # vien cua chinh nguoi dung, nen khi ho hoi "doi TOI co ai chua dat chi tieu" thi AI khong
            # biet "toi" la ai va HOI NGUOC LAI xin ma nhan vien, du he thong DA tu ep loc dung doi ho.
            # Nguoi dung phai tu khai ma nhan vien cua chinh minh la trai nghiem rat te (va ho thuong
            # khong nho ma).
            f'BAN DANG PHUC VU TAI KHOAN CUA QUAN LY VUNG (QLV) CO MA NHAN VIEN "{scope_employee_code}". '
            f'Khi nguoi dung noi "toi"/"doi toi"/"nhan vien cua toi", ho dang noi ve chinh QLV nay va '
            f'doi TDV duoi quyen ho. TUYET DOI KHONG hoi nguoc lai xin ma nhan vien cua ho - he thong '
            f'DA biet va DA tu dong gioi han moi bao cao ve dung doi cua ho o tang code. Cu goi tool '
            f'binh thuong, ket qua tra ve DA duoc loc san. '
            # 23/07/2026: truoc day chi liet ke 2 tool; nay moi bao cao hieu suat theo tung nguoi deu bi
            # gioi han theo doi (xem _PERSON_LEVEL_TEMPLATES trong report_templates.py).
            # 10/08/2026: bo get_kpi_forecast_model1 khoi danh sach nay. Cau tren khang dinh cac tool
            # nay "deu CHI tra ve du lieu CUA CHINH DOI HO", nhung forecast_model1() nhan
            # scope_area_code/scope_employee_code roi KHONG DUNG, va cung khong nam trong
            # _PERSON_LEVEL_TEMPLATES/_EMPLOYEE_SCOPED_TEMPLATES nen tang code cung khong chan ho.
            # Tuc la prompt dang hua mot dang, code lam mot neo. Tool da bi go hAn (xem ghi chu o
            # TEMPLATE_TOOLS), nhung ke ca khi bat lai cung KHONG duoc dua vao day truoc khi that su
            # co co che gioi han theo doi.
            f'MOI bao cao hieu suat theo tung nguoi (get_employee_kpi, get_employee_daily_kpi, '
            f'get_revenue_tree, get_kpi_ranking) deu CHI tra ve du lieu CUA CHINH DOI HO - khong thay '
            f'ten/so lieu KPI ca nhan cua QLV khac hay TDV doi khac trong cung vung '
            f'{scope_area_code or ""} - day la du lieu hieu suat nhay cam cua dong nghiep, khac voi so '
            f'lieu doanh thu/ton kho tong hop thong thuong. '
            f'Neu nguoi dung hoi "so sanh voi QLV khac" hoac "QLV nao tot nhat vung", PHAI TU CHOI ro '
            f'rang phan so sanh voi nguoi khac, chi dua duoc so lieu cua chinh ho. '
            f'Bao cao check_order_timing DA ep gioi han dung doi va duoc phep dung cho QLV; ket qua con '
            f'co hang tra va do tap trung don hang. Neu mot bao cao KHAC tra ve loi phan quyen thi giai '
            f'thich lai cho nguoi dung, dung tim cach lach bang tool khac.'
        )
    if scope_channel:
        parts.append(
            f'QUAN TRONG - TAI KHOAN NAY BI GIOI HAN KENH {scope_channel}: moi tool bao cao da duoc EP '
            f'LOC chi tra ve du lieu kenh {scope_channel} o tang he thong (ETC/kenh khac se KHONG xuat '
            f'hien trong ket qua du AI co lam gi). Neu nguoi dung hoi RO RANG ve kenh khac (vd hoi "ETC" '
            f'trong khi tai khoan chi duoc xem {scope_channel}), hoac hoi CHUNG CHUNG kieu "ca 2 kenh"/ '
            f'"tat ca kenh" - PHAI TU CHOI RO RANG, giai thich tai khoan chi co quyen xem kenh {scope_channel}, '
            f'KHONG duoc tra loi bang so lieu kenh {scope_channel} nhu the la du du lieu (gay hieu nham la '
            f'da bao gom ca kenh kia). Tool tra cuu SQL tu do (query_database) '
            f'KHONG kha dung cho tai khoan nay. MOI cau tra loi co so lieu doanh thu/don hang PHAI ghi ro '
            f'dang "(chi kenh {scope_channel})" ngay canh con so.'
        )
        if str(scope_channel).upper() == "ETC" and not scope_area_code:
            parts.append(
                "Tong doanh thu ETC cua tai khoan nay la TOAN KENH ETC, gom ca 3 mien MB/MT/MN. "
                "Khi neu tong, PHAI ghi ro 'toan kenh ETC, gom ca 3 mien' de nguoi doc khong "
                "doi chieu nham voi bao cao ETC loc rieng mot mien."
            )

    glossary = retrieve_relevant_glossary(question, username=username)
    if glossary:
        parts.append("Dinh nghia nghiep vu nguoi dung da giai thich truoc do, ap dung neu lien quan:\n"
                      + "\n".join(f"- {g}" for g in glossary))

    if session_id:
        qs = get_query_state(session_id)
        if qs and qs.get("last_tool"):
            parts.append(f'Ngu canh truy van GAN NHAT trong phien nay: da dung {qs["last_tool"]}'
                          f'({qs["last_args"]}) - neu cau hoi hien tai la hoi tiep kieu "con...thi sao",'
                          f' "so voi..." thi dung lam diem tham chieu.')

    examples = retrieve_similar_examples(question)
    if examples:
        ex_text = "\n".join(f"- Cau hoi: {e['question']}\n  SQL: {e['sql']}" for e in examples)
        parts.append("Vi du cau hoi-SQL tuong tu tung chay thanh cong truoc do (chi de THAM KHAO cach "
                      "viet, KHONG copy may moc neu cau hoi hien tai khac ve dieu kien loc):\n" + ex_text)

    try:
        live_schema = relevant_schema_context(question)
        if live_schema:
            parts.append(live_schema)
    except Exception as exc:
        # Catalog dong la tang mo rong. Neu VPN/metadata tam loi, cac tool chuan va
        # warehouse van phai hoat dong; model co the goi tool search de thu lai.
        parts.append(f"Catalog SQL Server tam thoi chua nap duoc: {str(exc)[:180]}")

    return "\n\n".join(parts)


def _blocked_future_forecast_response(question: str, session_id: str, query_id: str = None) -> dict:
    """Tra loi fail-closed truoc khi tao client AI hay cham vao bat ky CSDL nao."""
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", FUTURE_FORECAST_DISABLED_MESSAGE, query_id=query_id)
    return {
        "answer": FUTURE_FORECAST_DISABLED_MESSAGE,
        "sql_used": [],
        "last_result": None,
        "freshness": [],
        "query_id": query_id,
        "feature_disabled": True,
    }


def _is_model_read_timeout(exc: Exception) -> bool:
    """Only recover transport timeouts; provider and application errors must still surface."""
    if isinstance(exc, (TimeoutError, anthropic.APITimeoutError)):
        return True
    if isinstance(exc, anthropic.APIConnectionError):
        message = str(exc).lower()
        return "timed out" in message or "timeout" in message
    return type(exc).__name__ in {"ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout"}


def _model_response_or_timeout(client, *, stream: bool = False, **kwargs):
    """Catch a read timeout at every SDK call, including stream iteration/finalization."""
    try:
        if not stream:
            return client.messages.create(**kwargs), None
        with client.messages.stream(**kwargs) as message_stream:
            for _event in message_stream:
                pass
            return message_stream.get_final_message(), None
    except Exception as exc:
        if _is_model_read_timeout(exc):
            return None, str(exc)
        raise


def _record_sql_used(query_id: str, sql_used: list[str], statement: str) -> None:
    sql_used.append(statement)
    if query_id:
        update_query_run_progress(query_id, sql_used)


def _model_timeout_result(query_plan, freshness, question: str, session_id: str,
                          query_id: str, sql_used: list[str], error: str) -> dict:
    """Return only verified scope/source facts after the model stops responding."""
    query_plan.finalize(limit_reached=True)
    # Even if all source steps completed, the requested synthesis did not.
    query_plan.status = "partial"
    answer = (
        "**Hết thời gian xử lý:** Tôi chưa tổng hợp xong câu trả lời. "
        "Phần đã lấy được và phần còn thiếu được ghi dưới đây; chưa thể kết luận đầy đủ.\n\n"
        + query_plan.timeout_answer()
    )
    answer = freshness.finalize_answer(answer)
    answer = query_plan.finalize_warnings(answer)
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", answer, query_id=query_id)
    return {
        "answer": answer, "sql_used": sql_used, "last_result": None,
        "freshness": freshness.as_dicts(), "query_plan": query_plan.as_dict(),
        "partial_results_hidden": True, "completion_status": "partial_timeout",
        "timeout_error": error, "query_id": query_id,
    }


def _timeout_stream_chunks(result: dict):
    yield {"type": "text_delta", "text": result["answer"]}
    yield {"type": "done", **result}


@_translate_credit_errors
def ask(question: str, session_id: str = "default", username: str = None, scope_area_code: str = None,
        scope_employee_code: str = None, scope_channel: str = None, scope_role: str = None,
        query_id: str = None, origin: str = "script") -> dict:
    """
    Nhan cau hoi tieng Viet + session_id (1 phien chat webapp) - tu dong nho lai vai cau hoi/tra loi
    gan nhat trong CUNG session de hieu ngu canh cau hoi tiep theo.
    scope_area_code: NEU duoc truyen (tai khoan regional_director/qlv bi gioi han vung), MOI tool bao
    cao chuan se bi EP LOC theo dung vung nay o TANG CODE (report_templates.py), va tool SQL tu do
    (query_database) se bi LOAI HAN khoi danh sach tool kha dung - day la
    lop bao ve du lieu THAT (khong phu thuoc AI co lam dung huong dan hay khong).
    scope_employee_code: CHI danh cho tai khoan qlv - gioi han rieng cac bao cao lo hieu suat CA NHAN
    dong nghiep (get_revenue_tree/get_kpi_ranking) chi con doi cua rieng ho, khong thay KPI ca nhan
    cua cac QLV khac trong cung vung (khac scope_area_code van cho xem so lieu TONG HOP ca vung o cac
    tool khac nhu doanh thu/ton kho - 2 co che tach biet, xem main.py).
    scope_channel: doc lap voi 2 co che tren - CHI gioi han theo kenh (vd 'OTC') khi tai khoan duoc gan
    rieng, EP LOC tang code giong scope_area_code, cung LOAI HAN tool SQL tu do (vi khong loc kenh duoc
    o SQL tu do).
    Tra ve dict: {answer: str, sql_used: [list mo ta cac tool/SQL da chay], last_result: {...} hoac None}
    """
    if is_future_forecast_question(question):
        return _blocked_future_forecast_response(question, session_id, query_id)

    api_key = (os.environ.get("LLM_API_KEY", "").strip()
               or os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not api_key or api_key == "mock-key-for-local-testing":
        answer_text = "⚠️ **Chưa cấu hình API Key Claude/Anthropic**: Vui lòng bổ sung biến `ANTHROPIC_API_KEY=sk-ant-api03...` vào file `backend/.env` để khởi chạy tính năng Phân tích Dữ liệu AI."
        append_message(session_id, "user", question, query_id=query_id)
        append_message(session_id, "assistant", answer_text, query_id=query_id)
        return {
            "answer": answer_text,
            "sql_used": [],
            "last_result": None,
            "freshness": [],
            "query_id": query_id,
        }

    _require_model_attribution(username, session_id, origin)
    freshness = FreshnessCollector()
    client = _llm_client()
    history = load_history(session_id, max_turns=_max_history_turns(scope_role))
    messages = _history_to_messages(history) + [{"role": "user", "content": question}]
    # Breakpoint cache thu 3 (ngoai tools + system tinh) - danh dau cuoi khoi tool_result MOI NHAT
    # de cache duoc ca lich su + tool_result cua cac vong truoc, khong bi tinh lai gia day du moi
    # vong. Chi giu 1 marker "dang hoat dong" tai 1 thoi diem (xoa marker vong truoc khi dat vong
    # moi) de khong vuot qua 4 breakpoint/request; cache server-side van doc duoc prefix da ghi tu
    # vong truoc nho co che nhin lui 20 block, khong can giu marker cu.
    # LUU Y breakpoint nay dung TTL MAC DINH (5 phut), khac 2 breakpoint kia dung "1h" - ly do day du
    # o cho dat cache_control trong vong lap ben duoi.
    # 23/08/2026: THEM breakpoint thu 4 - _history_to_messages() da danh cache_control (TTL 5 phut,
    # cung ly do voi breakpoint nay) tren tin nhan CUOI CUNG cua history (neu co). Tong 4 breakpoint
    # dung DUNG gioi han toi da cua API (tools=1h, system=1h, history=5', tool_result dong=5') - neu
    # sau nay can them breakpoint moi, phai bo bot 1 trong 4 cai nay truoc, KHONG duoc cong don.
    _last_msg_cache_block = None

    sql_used = []
    last_result = None
    last_tool_used = None  # (name, args_str) - cap nhat query_state cuoi ham neu tra loi thanh cong
    ran_adhoc_query = None  # (question, sql) - luu vao longterm_memory neu query_database chay ok
    seen_tool_calls = set()
    unique_tool_calls = 0

    # Tai khoan bi gioi han vung: loai han tool SQL tu do khoi danh sach gui cho AI (AI KHONG CO KHA
    # NANG goi, khong chi la "duoc dan dung goi") - chi con lai cac tool bao cao chuan da kiem soat
    # duoc filter vung o tang code.
    tools_for_request = _tools_for_request(
        scope_area_code, scope_channel, scope_role, scope_employee_code
    )
    tools_for_request = _tools_for_question(tools_for_request, question)
    required_tool, luu_y_quyen = _required_tool_for_request(question, tools_for_request, scope_channel)
    max_rounds = _max_tool_rounds(scope_role)
    query_plan = build_query_plan(
        question,
        query_id=query_id,
        scope_role=scope_role,
        scope_area_code=scope_area_code,
        scope_employee_code=scope_employee_code,
        scope_channel=scope_channel,
        max_rounds=max_rounds,
        max_tools_per_round=MAX_TOOLS_PER_ROUND,
        max_unique_tools=MAX_UNIQUE_TOOL_CALLS,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )

    # System tach 2 block: block TINH (rules+schema) danh cache_control TTL 1h - it doi nen cache-hit
    # cao, chi tinh ~10% gia input goc; block DONG (ngay du lieu, glossary, query-state, few-shot, scope)
    # KHONG cache vi doi theo tung cau hoi/tai khoan.
    system_blocks = [
        {"type": "text", "text": _static_system_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": (_dynamic_context_note(
            question, session_id, scope_area_code, scope_employee_code, scope_channel, username, scope_role
        ) + "\n\n" + query_plan.prompt_note() + luu_y_quyen)},
    ]

    # 06/08/2026: GO BO output_config={"effort": "medium"} (them 05/08) sau khi do tren du lieu that.
    # Effort thap khien model suy luan nong hon MOI luot nen phai di NHIEU VONG tool hon moi ra dap an,
    # Truoc day model cham tran tool roi roi vao nhanh fallback "cau hoi qua phuc tap":
    #   - ty le nguoi dung nhan cau tu choi: 0,5% (2/384, 20/07-04/08) -> 27,0% (10/37, 06/08)
    #   - ty le cham tran 4 vong: 8,2% -> 37,1%; phan bo so lenh goi don dong dung tai moc 4
    # Muc hien tai cho phep nhieu vong hon, chan lap tool va bat buoc tong hop khi dung lai.
    # Doi lai, effort chi tiet kiem ~0,005 USD/cau (output 1.473 -> 990 token) trong khi breakpoint
    # cache o duoi tiet kiem ~0,025 USD/cau (input 14.734 -> 1.791) - bo effort chi mat ~10% khoan
    # tiet kiem nhung lay lai 27% so cau tra loi duoc. Cac toi uu khac GIU NGUYEN.
    for round_index in range(max_rounds):
        if query_plan.expired():
            break
        request_kwargs = {
            "model": MODEL,
            "max_tokens": _max_tokens(scope_role),
            "system": system_blocks,
            "tools": tools_for_request,
            "messages": messages,
            "extra_headers": _CACHE_BETA_HEADERS,
            "timeout": max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds())),
        }
        if (round_index == 0 or (required_tool == "get_customer_lifecycle_summary" and unique_tool_calls == 0)) and required_tool and any(
            tool["name"] == required_tool for tool in tools_for_request
        ):
            request_kwargs["tool_choice"] = {"type": "tool", "name": required_tool}
        resp, timeout_error = _model_response_or_timeout(client, **request_kwargs)
        if timeout_error:
            return _model_timeout_result(query_plan, freshness, question, session_id,
                                         query_id, sql_used, timeout_error)
        compute_and_log_cost(resp.usage, MODEL, question, session_id, username)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer_text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not answer_text:
                # Truong hop hy huu: het ngan sach token cho phan suy luan (thinking) khien khong con
                # cho phan text tra ve - thu lai 1 lan voi yeu cau tra loi ngay, ngan gon.
                # 05/08/2026: nguyen nhan goc la Sonnet 5 bat thinking MAC DINH khi khong truyen
                # output_config - thinking an het MAX_TOKENS truoc khi con cho text tra loi.
                # 06/08/2026: da GO effort="medium" o ca 2 lenh goi (xem ghi chu dai o vong lap tren) -
                # co che thu lai nay GIU NGUYEN vi no van la luoi an toan cho dung tinh huong tren.
                messages.append({"role": "user", "content": "Hay tra loi ngay bay gio, ngan gon truc tiep."})
                resp2, timeout_error = _model_response_or_timeout(
                    client, model=MODEL, max_tokens=_max_tokens(scope_role), system=system_blocks,
                    tools=tools_for_request, messages=messages, extra_headers=_CACHE_BETA_HEADERS,
                    timeout=max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds())),
                )
                if timeout_error:
                    return _model_timeout_result(query_plan, freshness, question, session_id,
                                                 query_id, sql_used, timeout_error)
                compute_and_log_cost(resp2.usage, MODEL, question, session_id, username)
                answer_text = "".join(b.text for b in resp2.content if b.type == "text").strip()
                if not answer_text:
                    answer_text = ("Xin lỗi, dữ liệu trả về quá lớn để tổng hợp gọn trong 1 câu trả lời. "
                                    "Bạn thử hỏi cụ thể/thu hẹp phạm vi hơn giúp mình nhé (vd theo vùng, theo thời gian ngắn hơn).")
            query_plan.finalize()
            answer_text = query_plan.finalize_answer(answer_text)
            answer_text = freshness.finalize_answer(answer_text)
            answer_text = query_plan.finalize_warnings(answer_text)
            append_message(session_id, "user", question, query_id=query_id)
            append_message(session_id, "assistant", answer_text, query_id=query_id)
            if last_tool_used:
                set_query_state(session_id, last_tool_used[0], last_tool_used[1])
            if ran_adhoc_query:
                save_example(*ran_adhoc_query)
            return {"answer": answer_text, "sql_used": sql_used, "last_result": last_result,
                    "freshness": freshness.as_dicts(),
                    "query_plan": query_plan.as_dict(),
                    "query_id": query_id}

        tool_results = []
        original_tool_uses = [b for b in resp.content if b.type == "tool_use"]
        # Gop cac lenh goi cung tool + cung tham so phu thanh mot (xem _merge_bulk_tool_calls - da tach
        # ra ngoai de test duoc, va da va 2 loi gay mat du lieu am tham vao 10/08/2026).
        merged_sub_ids = _merge_bulk_tool_calls(original_tool_uses)

        executed_count = 0
        new_tools_this_round = 0
        for tu in original_tool_uses:
            normalized_input = _normalize_tool_input_for_question(tu.name, tu.input, question)
            if isinstance(tu.input, dict) and normalized_input != tu.input:
                tu.input.clear()
                tu.input.update(normalized_input)
            if _customer_tool_conflict(tu.name, question):
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": json.dumps({"note": (
                        "C29 chi dung get_customer_lifecycle_summary: NC/RO la co Bravo. "
                        "Khong tron khach moi suy tu hoa don cua get_customer_movement."
                    )}),
                })
                continue
            if tu.id in merged_sub_ids:
                # Merged into primary tool_use -> return matching dummy tool_result to satisfy Anthropic API contract
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": "Đã gộp kết quả tra cứu hàng loạt vào lượt gọi trước."}),
                })
                continue

            if executed_count >= MAX_TOOLS_PER_ROUND:
                # Capped execution -> return notice to satisfy Anthropic API contract
                query_plan.skip_tool(
                    tu.name, tu.input,
                    f"Đã đạt giới hạn {MAX_TOOLS_PER_ROUND} tool trong một vòng.",
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": f"Đã đạt giới hạn {MAX_TOOLS_PER_ROUND} lượt gọi tool trong 1 lượt. Hãy tổng hợp từ dữ liệu đã lấy, hoặc gọi các tool còn lại ở lượt kế tiếp."}),
                })
                continue

            tool_key = _tool_call_key(tu.name, tu.input)
            if tool_key in seen_tool_calls:
                query_plan.skip_tool(tu.name, tu.input, "Lệnh đã chạy với đúng tham số.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": "Lenh nay da chay voi dung tham so trong cau hoi hien tai. Hay dung ket qua da co va tong hop, khong goi lai."
                    }),
                })
                continue
            if unique_tool_calls >= MAX_UNIQUE_TOOL_CALLS:
                query_plan.skip_tool(
                    tu.name, tu.input,
                    f"Đã đạt giới hạn {MAX_UNIQUE_TOOL_CALLS} tool khác nhau.",
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": f"Da du {MAX_UNIQUE_TOOL_CALLS} truy van khac nhau. Hay tong hop cau tra loi tu du lieu da co."
                    }),
                })
                continue

            if query_plan.expired():
                query_plan.skip_tool(tu.name, tu.input, "Đã hết tổng ngân sách thời gian request.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "error": "Đã hết tổng ngân sách thời gian request; không chạy thêm nguồn."
                    }, ensure_ascii=False),
                })
                continue

            seen_tool_calls.add(tool_key)
            unique_tool_calls += 1
            new_tools_this_round += 1
            executed_count += 1
            query_plan.start_tool(tu.name, tu.input, tool_key)
            tool_started = time.monotonic()
            tool_ok = True
            tool_source = f"template:{tu.name}"
            if tu.name in LOCAL_UTIL_TOOLS:
                # Tool "tien ich" chay bang code thuan, khong cham DB - xu ly ngay tai cho, khong qua
                # run_query/call_template (khong can audit log SQL vi khong co SQL nao ca).
                _record_sql_used(query_id, sql_used, f"[tien ich] {tu.name}({tu.input})")
                if tu.name == "get_current_datetime":
                    payload = get_current_datetime()
                elif tu.name == "resolve_relative_date":
                    payload = resolve_relative_date(tu.input.get("phrase", ""))
                elif tu.name == "save_business_term":
                    save_glossary_term(tu.input.get("term", ""), tu.input.get("definition", ""),
                                        defined_by=username,
                                        is_global=scope_role in {"c_level", "admin_ops"})
                    payload = {
                        "ok": True,
                        "message": "Da luu dinh nghia " + (
                            "toan he thong." if scope_role in {"c_level", "admin_ops"}
                            else "cho rieng tai khoan nay."
                        ),
                    }
                elif tu.name == "search_sql_server_catalog":
                    payload = search_sql_catalog(
                        tu.input.get("query", question),
                        limit=tu.input.get("limit", 6),
                        include_definition=tu.input.get("include_definition", True),
                    )
                else:
                    payload = {"error": f"Tool khong ro: {tu.name}"}
                tool_ok = not (isinstance(payload, dict) and payload.get("error"))
                tool_source = f"utility:{tu.name}"
            elif tu.name in RAW_SQL_TOOLS:
                if scope_area_code or scope_channel:
                    # Phong ho: tool nay khong con trong tools_for_request nen AI khong the goi duoc,
                    # nhung neu vi ly do gi van xuat hien thi tu choi thang, KHONG thuc thi SQL.
                    _record_sql_used(query_id, sql_used, f"[BI CHAN - tai khoan gioi han] {tu.name}")
                    payload = {"error": "Tai khoan cua ban bi gioi han (vung/kenh), khong duoc dung truy van SQL tu do."}
                    tool_ok = False
                elif tu.name in LIVE_SQL_TOOL_NAMES and scope_role not in LIVE_SQL_ALLOWED_ROLES:
                    _record_sql_used(query_id, sql_used, f"[BI CHAN - vai tro khong duoc query SQL live] {tu.name}")
                    payload = {"error": "Tai khoan khong duoc phep truy van SQL Server live tu do."}
                    tool_ok = False
                else:
                    db = RAW_SQL_TOOLS[tu.name]
                    tool_source = db
                    sql = tu.input.get("sql", "")
                    _record_sql_used(query_id, sql_used, f"[{db}] {sql}")
                    result = run_query(sql, question=question, db=db, username=username, session_id=session_id)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if result.get("ok"):
                        freshness.record_raw(db, result, sql)
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = _raw_query_payload(result, db, question)
                    tool_ok = bool(result.get("ok"))
            else:
                _record_sql_used(query_id, sql_used, f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username, session_id=session_id,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel, scope_role=scope_role)
                query_plan.record_tool_warnings(tresult.get("user_warnings") or [])
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                if tresult.get("ok"):
                    freshness.record_template(
                        tu.name, tresult["result"], args=tu.input, scope_channel=scope_channel
                    )
                payload = tresult["result"] if tresult["ok"] else {"error": tresult["error"]}
                tool_ok = bool(tresult.get("ok"))
                # 22/07/2026 (diem #5): tool co the kem canh bao tu-doi-chieu (vd tong theo vung lech
                # tong tho). TRUOC DAY chi lay ["result"] nen canh bao BI ROI MAT truoc khi toi model
                # -> nguoi dung van nhan so lieu sai ma khong he biet. Chi boc them khi CO canh bao.
                if tresult.get("canh_bao"):
                    payload = {"du_lieu": payload,
                               "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": tresult["canh_bao"]}

            query_plan.finish_tool(
                tool_key,
                ok=tool_ok,
                payload=payload,
                source=tool_source,
                duration_ms=int((time.monotonic() - tool_started) * 1000),
                timeout_seconds=TOOL_TIMEOUT_SECONDS,
            )

            # Giu ket qua day du trong last_result; model nhan JSON tom luoc co cau truc, khong bao
            # gio nhan chuoi bi cat giua dong hay thong diep gioi han ky thuat.
            payload_str = _serialize_payload_for_model(tu.name, payload, question)
            payload_str += "\n" + query_plan.model_note()
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": payload_str,
            })

        if tool_results:
            if _last_msg_cache_block is not None:
                _last_msg_cache_block.pop("cache_control", None)
            tool_results[-1] = dict(tool_results[-1])
            # 06/08/2026: TTL MAC DINH (5 phut), CO Y khac 2 breakpoint kia (system + tools dung "1h").
            # Gia GHI cache phu thuoc TTL: 5 phut = 1,25x gia input ($2,50/M), 1 gio = 2x ($4,00/M).
            # Khoi tool_result nay chi duoc doc lai TRONG CHINH cau hoi do - cac vong cach nhau vai
            # giay - nen khong bao gio huong loi tu TTL 1 gio, ma van phai tra gia ghi dat hon 60%.
            # Do that 06/08: cache_write la thanh phan DAT NHAT (37,8% chi phi/cau, ~4.426 token),
            # phan lon den tu chinh breakpoint di dong nay (ghi lai moi vong, ~2,86 vong/cau).
            # Ha ve 5 phut tiet kiem ~0,0066 USD/cau (~14% tong chi phi).
            # System prompt + tool definitions thi NGUOC LAI: dung lai qua nhieu cau hoi trong nhieu
            # gio, nen giu "1h" (xem system_blocks va tools_for_request o dau ham).
            # Rui ro: cache 5 phut chi hong neu 2 vong goi tool cach nhau qua 5 phut - do thuc te cau
            # cham nhat la 1,3 phut cho CA cau hoi, con xa nguong.
            tool_results[-1]["cache_control"] = {"type": "ephemeral"}
            _last_msg_cache_block = tool_results[-1]
        messages.append({"role": "user", "content": tool_results})
        if new_tools_this_round == 0:
            # One corrective retry if the first batch ignored C29's forced tool.
            # Still bounded: repeated rejected calls on the next round stop here.
            if round_index == 0 and any(_customer_tool_conflict(t.name, question) for t in original_tool_uses):
                continue
            break

    # Cham tran/no-progress: cam goi them tool va bat model tong hop tu bang chung da co. Khong tra
    # cau "qua phuc tap" nua, va khong dua bang trung gian ra Excel nhu the la ket qua cuoi.
    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
        messages[-1]["content"].append({"type": "text", "text": _FORCE_FINAL_ANSWER})
    else:
        messages.append({"role": "user", "content": _FORCE_FINAL_ANSWER})
    query_plan.finalize(limit_reached=True)
    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
        messages[-1]["content"].append({"type": "text", "text": query_plan.model_note()})
    if query_plan.expired():
        return _model_timeout_result(query_plan, freshness, question, session_id,
                                     query_id, sql_used, "Request deadline reached")
    else:
        final_resp, timeout_error = _model_response_or_timeout(
            client, model=MODEL, max_tokens=_max_tokens(scope_role), system=system_blocks,
            messages=messages, extra_headers=_CACHE_BETA_HEADERS,
            timeout=max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds())),
        )
        if timeout_error:
            return _model_timeout_result(query_plan, freshness, question, session_id,
                                         query_id, sql_used, timeout_error)
        compute_and_log_cost(final_resp.usage, MODEL, question, session_id, username)
        fallback = _response_text(final_resp) or (
            "Toi da doi chieu cac nguon du lieu nhung chua du bang chung de ket luan chinh xac. "
            "Ket qua trung gian da duoc an de tranh hieu nham la bao cao cuoi."
        )
        fallback = query_plan.finalize_answer(fallback)
    fallback = freshness.finalize_answer(fallback)
    fallback = query_plan.finalize_warnings(fallback)
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", fallback, query_id=query_id)
    return {"answer": fallback, "sql_used": sql_used, "last_result": None,
            "freshness": freshness.as_dicts(),
            "query_plan": query_plan.as_dict(),
            "partial_results_hidden": True, "query_id": query_id}


@_translate_stream_credit_errors
def ask_stream(question: str, session_id: str = "default", username: str = None, scope_area_code: str = None,
                scope_employee_code: str = None, scope_channel: str = None, scope_role: str = None,
                query_id: str = None, origin: str = "script"):
    """11/08/2026: BAN SSE cua ask() - GIONG HET logic tool-calling/phan quyen/cache o tren.
    17/08/2026: SDK van nhan stream tu model, nhung backend chi cong bo text sau khi biet response
    khong con tool_use, loai timestamp model tu sinh va gan metadata nguon. Uu tien answer tren UI
    trung khop 100% voi answer luu lich su; khong lo doan tong hop trung gian ra ngoai.

    Transport model van dung stream de khong doi timeout/SDK, nhung SSE chi phat cau tra loi da chot
    sau khi backend xu ly footer. Day la ham GENERATOR (dung yield) - goi ham nay tra ve 1 generator,
    PHAI duyet qua (for chunk in ask_stream(...)) moi thuc su chay.

    Ham nay la BAN SONG SONG voi ask() (KHONG sua ask() de tranh anh huong endpoint /chat dang chay
    that cho 25 users) - dung cho endpoint /chat/stream moi. Neu can sua logic tool-calling/phan quyen
    (vd them tool moi, sua cach EP scope), PHAI sua CA HAI ham nay (ask() va ask_stream()) - de tranh
    2 ham lech nhau dan, cac phan GIONG HET giua 2 ham duoc chua thich "xem ask()" thay vi lap lai
    toan bo comment giai thich.
    11/08/2026: RIENG phan GOP TOOL HANG LOAT (Tool Merger) da rut ra ham dung chung
    _merge_bulk_tool_calls() thay vi chep tay - phat hien luc nay ban chep tay o duoi van con giu 2
    loi da vas o ask() 1 ngay truoc (danh dau "da gop" gia, chi gop 1 tham so khoa lam vut het tham
    so khac). Phan nay KHONG can sua 2 noi nua, chi can sua trong _merge_bulk_tool_calls().

    yield: cac dict {"type": "text_delta", "text": str} cho tung doan chu, roi 1 dict cuoi cung
    {"type": "done", "answer": str, "sql_used": [...], "last_result": {...}} voi KET QUA DAY DU
    (giong het cau truc return cua ask()) de client biet ket thuc va co du lieu cho UI (bang/cot...).
    """
    if is_future_forecast_question(question):
        blocked = _blocked_future_forecast_response(question, session_id, query_id)
        yield {"type": "text_delta", "text": blocked["answer"]}
        yield {"type": "done", **blocked}
        return

    api_key = (os.environ.get("LLM_API_KEY", "").strip()
               or os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not api_key or api_key == "mock-key-for-local-testing":
        msg = ("⚠️ **Chưa cấu hình API Key Claude/Anthropic**: Vui lòng bổ sung biến "
               "`ANTHROPIC_API_KEY=sk-ant-api03...` vào file `backend/.env` để khởi chạy tính năng "
               "Phân tích Dữ liệu AI.")
        append_message(session_id, "user", question, query_id=query_id)
        append_message(session_id, "assistant", msg, query_id=query_id)
        yield {"type": "text_delta", "text": msg}
        yield {"type": "done", "answer": msg, "sql_used": [], "last_result": None,
               "freshness": [],
               "query_id": query_id}
        return

    _require_model_attribution(username, session_id, origin)
    freshness = FreshnessCollector()
    client = _llm_client()
    history = load_history(session_id, max_turns=_max_history_turns(scope_role))
    messages = _history_to_messages(history) + [{"role": "user", "content": question}]
    _last_msg_cache_block = None  # xem ghi chu day du o ask()

    sql_used = []
    last_result = None
    last_tool_used = None
    ran_adhoc_query = None
    seen_tool_calls = set()
    unique_tool_calls = 0

    tools_for_request = _tools_for_request(
        scope_area_code, scope_channel, scope_role, scope_employee_code
    )
    tools_for_request = _tools_for_question(tools_for_request, question)
    required_tool, luu_y_quyen = _required_tool_for_request(question, tools_for_request, scope_channel)
    max_rounds = _max_tool_rounds(scope_role)
    query_plan = build_query_plan(
        question,
        query_id=query_id,
        scope_role=scope_role,
        scope_area_code=scope_area_code,
        scope_employee_code=scope_employee_code,
        scope_channel=scope_channel,
        max_rounds=max_rounds,
        max_tools_per_round=MAX_TOOLS_PER_ROUND,
        max_unique_tools=MAX_UNIQUE_TOOL_CALLS,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )

    system_blocks = [
        {"type": "text", "text": _static_system_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": (_dynamic_context_note(
            question, session_id, scope_area_code, scope_employee_code, scope_channel, username, scope_role
        ) + "\n\n" + query_plan.prompt_note() + luu_y_quyen)},
    ]

    for round_i in range(max_rounds):
        if query_plan.expired():
            break
        # Vong GIUA: co the con tool_use, KHONG stream (client khong can thay) - dung create() nhu
        # ask() binh thuong, ro rang hon la stream() roi bo qua cac delta.
        # Vong CO THE la CUOI (round_i == max_rounds-1): CHUA BIET truoc model co con goi tool
        # hay khong (chi biet SAU khi nhan xong response) - nhung neu dung create() cho vong nay, khi
        # model THAT SU tra loi (khong goi tool) thi lai mat streaming cho chinh vong quan trong nhat.
        # Giai phap: LUON dung stream() tu vong DAU (khong chi vong cuoi) - phi stream cho vong co
        # tool_use la KHONG DANG KE (chi vai token dau ra truoc phan tool_use, van phai doi ca cuc
        # tool_use ve moi biet dc functon nao/tham so gi de goi that), doi lai dam bao vong tra loi
        # that SU (bat ky la vong thu may) LUON duoc stream.
        request_kwargs = {
            "model": MODEL, "max_tokens": _max_tokens(scope_role), "system": system_blocks,
            "tools": tools_for_request, "messages": messages,
            "extra_headers": _CACHE_BETA_HEADERS,
            "timeout": max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds())),
        }
        if (round_i == 0 or (required_tool == "get_customer_lifecycle_summary" and unique_tool_calls == 0)) and required_tool and any(
            tool["name"] == required_tool for tool in tools_for_request
        ):
            request_kwargs["tool_choice"] = {"type": "tool", "name": required_tool}
        # Khong day text ra UI truoc khi biet response co tool_use hay khong. Backend can
        # loai footer timestamp model tu sinh va gan dung metadata nguon truoc khi cong bo.
        resp, timeout_error = _model_response_or_timeout(client, stream=True, **request_kwargs)
        if timeout_error:
            yield from _timeout_stream_chunks(_model_timeout_result(
                query_plan, freshness, question, session_id, query_id, sql_used, timeout_error,
            ))
            return

        compute_and_log_cost(resp.usage, MODEL, question, session_id, username)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer_text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not answer_text:
                # Xem ghi chu day du o ask() - truong hop hy huu het ngan sach thinking.
                messages.append({"role": "user", "content": "Hay tra loi ngay bay gio, ngan gon truc tiep."})
                resp2, timeout_error = _model_response_or_timeout(
                    client, stream=True, model=MODEL, max_tokens=_max_tokens(scope_role),
                    system=system_blocks, tools=tools_for_request, messages=messages,
                    extra_headers=_CACHE_BETA_HEADERS,
                    timeout=max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds())),
                )
                if timeout_error:
                    yield from _timeout_stream_chunks(_model_timeout_result(
                        query_plan, freshness, question, session_id, query_id, sql_used, timeout_error,
                    ))
                    return
                compute_and_log_cost(resp2.usage, MODEL, question, session_id, username)
                answer_text = "".join(b.text for b in resp2.content if b.type == "text").strip()
                if not answer_text:
                    answer_text = ("Xin lỗi, dữ liệu trả về quá lớn để tổng hợp gọn trong 1 câu trả lời. "
                                    "Bạn thử hỏi cụ thể/thu hẹp phạm vi hơn giúp mình nhé (vd theo vùng, theo thời gian ngắn hơn).")
            query_plan.finalize()
            answer_text = query_plan.finalize_answer(answer_text)
            answer_text = freshness.finalize_answer(answer_text)
            answer_text = query_plan.finalize_warnings(answer_text)
            yield {"type": "text_delta", "text": answer_text}
            append_message(session_id, "user", question, query_id=query_id)
            append_message(session_id, "assistant", answer_text, query_id=query_id)
            if last_tool_used:
                set_query_state(session_id, last_tool_used[0], last_tool_used[1])
            if ran_adhoc_query:
                save_example(*ran_adhoc_query)
            yield {"type": "done", "answer": answer_text, "sql_used": sql_used,
                   "last_result": last_result, "freshness": freshness.as_dicts(),
                   "query_plan": query_plan.as_dict(),
                   "query_id": query_id}
            return

        # Tu day tro xuong: XU LY TOOL. Truoc 11/08/2026 cho nay COPY TAY logic gop tool tu ask() -
        # dung cach do gia mao chinh 2 loi da vas o ask() ngay 10/08 (danh dau "da gop" ke ca khong
        # gop duoc gi; chi gop 1 tham so khoa, am tham vut tham so khac - xem _merge_bulk_tool_calls
        # o tren). Doi sang GOI CHUNG ham do thay vi giu 2 ban chep tay de khong bao gio lech nhau
        # nua (dung y tinh than ghi chu cu: "PHAI sua o day theo dung y het").
        tool_results = []
        original_tool_uses = [b for b in resp.content if b.type == "tool_use"]
        merged_sub_ids = _merge_bulk_tool_calls(original_tool_uses)

        executed_count = 0
        new_tools_this_round = 0
        for tu in original_tool_uses:
            normalized_input = _normalize_tool_input_for_question(tu.name, tu.input, question)
            if isinstance(tu.input, dict) and normalized_input != tu.input:
                tu.input.clear()
                tu.input.update(normalized_input)
            if _customer_tool_conflict(tu.name, question):
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": json.dumps({"note": (
                        "C29 chi dung get_customer_lifecycle_summary: NC/RO la co Bravo. "
                        "Khong tron khach moi suy tu hoa don cua get_customer_movement."
                    )}),
                })
                continue
            if tu.id in merged_sub_ids:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": "Đã gộp kết quả tra cứu hàng loạt vào lượt gọi trước."}),
                })
                continue

            if executed_count >= MAX_TOOLS_PER_ROUND:
                query_plan.skip_tool(
                    tu.name, tu.input,
                    f"Đã đạt giới hạn {MAX_TOOLS_PER_ROUND} tool trong một vòng.",
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": f"Đã đạt giới hạn {MAX_TOOLS_PER_ROUND} lượt gọi tool trong 1 lượt. Hãy tổng hợp từ dữ liệu đã lấy, hoặc gọi các tool còn lại ở lượt kế tiếp."}),
                })
                continue

            tool_key = _tool_call_key(tu.name, tu.input)
            if tool_key in seen_tool_calls:
                query_plan.skip_tool(tu.name, tu.input, "Lệnh đã chạy với đúng tham số.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": "Lenh nay da chay voi dung tham so trong cau hoi hien tai. Hay dung ket qua da co va tong hop, khong goi lai."
                    }),
                })
                continue
            if unique_tool_calls >= MAX_UNIQUE_TOOL_CALLS:
                query_plan.skip_tool(
                    tu.name, tu.input,
                    f"Đã đạt giới hạn {MAX_UNIQUE_TOOL_CALLS} tool khác nhau.",
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": f"Da du {MAX_UNIQUE_TOOL_CALLS} truy van khac nhau. Hay tong hop cau tra loi tu du lieu da co."
                    }),
                })
                continue

            if query_plan.expired():
                query_plan.skip_tool(tu.name, tu.input, "Đã hết tổng ngân sách thời gian request.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "error": "Đã hết tổng ngân sách thời gian request; không chạy thêm nguồn."
                    }, ensure_ascii=False),
                })
                continue

            seen_tool_calls.add(tool_key)
            unique_tool_calls += 1
            new_tools_this_round += 1
            executed_count += 1
            query_plan.start_tool(tu.name, tu.input, tool_key)
            tool_started = time.monotonic()
            tool_ok = True
            tool_source = f"template:{tu.name}"
            if tu.name in LOCAL_UTIL_TOOLS:
                _record_sql_used(query_id, sql_used, f"[tien ich] {tu.name}({tu.input})")
                if tu.name == "get_current_datetime":
                    payload = get_current_datetime()
                elif tu.name == "resolve_relative_date":
                    payload = resolve_relative_date(tu.input.get("phrase", ""))
                elif tu.name == "save_business_term":
                    save_glossary_term(tu.input.get("term", ""), tu.input.get("definition", ""),
                                        defined_by=username,
                                        is_global=scope_role in {"c_level", "admin_ops"})
                    payload = {
                        "ok": True,
                        "message": "Da luu dinh nghia " + (
                            "toan he thong." if scope_role in {"c_level", "admin_ops"}
                            else "cho rieng tai khoan nay."
                        ),
                    }
                elif tu.name == "search_sql_server_catalog":
                    payload = search_sql_catalog(
                        tu.input.get("query", question),
                        limit=tu.input.get("limit", 6),
                        include_definition=tu.input.get("include_definition", True),
                    )
                else:
                    payload = {"error": f"Tool khong ro: {tu.name}"}
                tool_ok = not (isinstance(payload, dict) and payload.get("error"))
                tool_source = f"utility:{tu.name}"
            elif tu.name in RAW_SQL_TOOLS:
                if scope_area_code or scope_channel:
                    _record_sql_used(query_id, sql_used, f"[BI CHAN - tai khoan gioi han] {tu.name}")
                    payload = {"error": "Tai khoan cua ban bi gioi han (vung/kenh), khong duoc dung truy van SQL tu do."}
                    tool_ok = False
                elif tu.name in LIVE_SQL_TOOL_NAMES and scope_role not in LIVE_SQL_ALLOWED_ROLES:
                    _record_sql_used(query_id, sql_used, f"[BI CHAN - vai tro khong duoc query SQL live] {tu.name}")
                    payload = {"error": "Tai khoan khong duoc phep truy van SQL Server live tu do."}
                    tool_ok = False
                else:
                    db = RAW_SQL_TOOLS[tu.name]
                    tool_source = db
                    sql = tu.input.get("sql", "")
                    _record_sql_used(query_id, sql_used, f"[{db}] {sql}")
                    result = run_query(sql, question=question, db=db, username=username, session_id=session_id)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if result.get("ok"):
                        freshness.record_raw(db, result, sql)
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = _raw_query_payload(result, db, question)
                    tool_ok = bool(result.get("ok"))
            else:
                _record_sql_used(query_id, sql_used, f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username, session_id=session_id,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel, scope_role=scope_role)
                query_plan.record_tool_warnings(tresult.get("user_warnings") or [])
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                if tresult.get("ok"):
                    freshness.record_template(
                        tu.name, tresult["result"], args=tu.input, scope_channel=scope_channel
                    )
                payload = tresult["result"] if tresult["ok"] else {"error": tresult["error"]}
                tool_ok = bool(tresult.get("ok"))
                if tresult.get("canh_bao"):
                    payload = {"du_lieu": payload,
                               "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": tresult["canh_bao"]}

            query_plan.finish_tool(
                tool_key,
                ok=tool_ok,
                payload=payload,
                source=tool_source,
                duration_ms=int((time.monotonic() - tool_started) * 1000),
                timeout_seconds=TOOL_TIMEOUT_SECONDS,
            )

            payload_str = _serialize_payload_for_model(tu.name, payload, question)
            payload_str += "\n" + query_plan.model_note()
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": payload_str,
            })

        if tool_results:
            if _last_msg_cache_block is not None:
                _last_msg_cache_block.pop("cache_control", None)
            tool_results[-1] = dict(tool_results[-1])
            tool_results[-1]["cache_control"] = {"type": "ephemeral"}
            _last_msg_cache_block = tool_results[-1]
        messages.append({"role": "user", "content": tool_results})
        if new_tools_this_round == 0:
            if round_i == 0 and any(_customer_tool_conflict(t.name, question) for t in original_tool_uses):
                continue
            break

    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
        messages[-1]["content"].append({"type": "text", "text": _FORCE_FINAL_ANSWER})
    else:
        messages.append({"role": "user", "content": _FORCE_FINAL_ANSWER})
    query_plan.finalize(limit_reached=True)
    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
        messages[-1]["content"].append({"type": "text", "text": query_plan.model_note()})
    if query_plan.expired():
        yield from _timeout_stream_chunks(_model_timeout_result(
            query_plan, freshness, question, session_id, query_id, sql_used,
            "Request deadline reached",
        ))
        return
    else:
        final_resp, timeout_error = _model_response_or_timeout(
            client, stream=True, model=MODEL, max_tokens=_max_tokens(scope_role),
            system=system_blocks, messages=messages, extra_headers=_CACHE_BETA_HEADERS,
            timeout=max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds())),
        )
        if timeout_error:
            yield from _timeout_stream_chunks(_model_timeout_result(
                query_plan, freshness, question, session_id, query_id, sql_used, timeout_error,
            ))
            return
        compute_and_log_cost(final_resp.usage, MODEL, question, session_id, username)
        fallback = _response_text(final_resp) or (
            "Toi da doi chieu cac nguon du lieu nhung chua du bang chung de ket luan chinh xac. "
            "Ket qua trung gian da duoc an de tranh hieu nham la bao cao cuoi."
        )
        fallback = query_plan.finalize_answer(fallback)
    fallback = freshness.finalize_answer(fallback)
    fallback = query_plan.finalize_warnings(fallback)
    yield {"type": "text_delta", "text": fallback}
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", fallback, query_id=query_id)
    yield {"type": "done", "answer": fallback, "sql_used": sql_used, "last_result": None,
           "freshness": freshness.as_dicts(),
           "query_plan": query_plan.as_dict(),
           "partial_results_hidden": True, "query_id": query_id}
