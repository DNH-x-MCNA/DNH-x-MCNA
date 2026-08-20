# -*- coding: utf-8 -*-
"""Chạy TOÀN BỘ 90 câu nghiệp vụ (scripts/business_stress_suite.py) qua chatbot thật và
chấm điểm tự động những gì có thể chấm CHẮC CHẮN, còn lại giao cho người kiểm.

Bối cảnh: scripts/evaluate_model_canary.py (18/08/2026) là canary NHANH - 18 câu, đủ để
biết model có "đi đúng đường" hay không sau mỗi lần đổi cấu hình/nhà cung cấp. Script này
là bài kiểm ĐẦY ĐỦ - toàn bộ 90 câu golden, có đối chiếu số với SQL Server thật khi làm được
một cách AN TOÀN, chạy trước khi mở production cho vai trò mới hoặc đổi model mặc định.

=== TRIẾT LÝ CHẤM ĐIỂM: KHÔNG BỊA ĐỘ TIN CẬY ===
business_stress_suite.py tự ghi rõ trong docstring: "Không tự động phán PASS bằng so khớp
câu chữ; người kiểm thử đối chiếu số, kỳ, phạm vi và cảnh báo." Script này tôn trọng đúng
nguyên tắc đó, KHÔNG cố tự động hoá phần không thể tự động hoá đáng tin:

  TỰ ĐỘNG CHẤM ĐƯỢC (áp dụng cho cả 90 câu, không có ngoại lệ - nếu sai là sai thật):
    - Có lỗi hệ thống khi hỏi không.
    - Có bị từ chối "câu hỏi quá phức tạp" không (chatbot có dữ liệu, không được từ chối).
    - Có KHẲNG ĐỊNH DỰ BÁO/ƯỚC TÍNH lọt vào câu trả lời không - vẫn bắt trên toàn bộ 90 câu,
      nhưng không phạt câu phủ định đúng chính sách như "không dùng ước tính".
    - Có gọi tool nào không - hỏi số liệu nghiệp vụ mà 0 tool nào chạy là dấu hiệu trực tiếp
      của việc tự bịa, bất kể tool cụ thể nào "đáng lẽ" phải gọi (không đoán tool đúng, chỉ
      bắt trường hợp KHÔNG tool nào).

  ĐỐI CHIẾU SỐ VỚI SQL SERVER - CHỈ khi kết quả checker "gọn" (<=3 dòng, <=12 ô số): các case
  có answer_columns chỉ bắt đúng trường câu hỏi yêu cầu; case cũ chưa khai báo metadata giữ cách
  chấm toàn checker. Số phải xuất hiện nguyên vẹn (theo dãy chữ số, bỏ hết dấu phân cách) hoặc
  khớp quy tắc làm tròn đã kiểm thử.
  Loại checker dạng "top N" (vd top 20 khách hàng) KHÔNG được tự chấm theo cách này - đối
  chiếu 1-trong-20 dòng nào đúng cần hiểu ý câu hỏi, không phải việc máy nên tự quyết. Ground
  truth vẫn được đính kèm nguyên trong báo cáo để người kiểm đối chiếu nhanh, đúng tinh thần
  gốc của business_stress_suite.py.

  KHÔNG cố chấm: đúng tool cụ thể (chưa có ai hạ bút xác nhận tool nào đúng cho từng câu/90),
  đúng phạm vi vai trò (audience trong BusinessCase chỉ là NHÃN tài liệu, không map ra
  scope_role/scope_area thật - tự bịa mapping đó rủi ro hơn là để trống), SQL ghi (đã có
  _FORBIDDEN regex + test riêng ở backend/query_engine.py, không lặp lại ở đây).

Chạy (cần backend có ANTHROPIC_API_KEY/LLM_* và kết nối SQL Server thật - máy 24):
    cd C:\\dnh_chatbot
    python scripts\\run_business_evaluation.py --label sonnet-5
    python scripts\\run_business_evaluation.py --group "Công nợ" --label smoke-debt
    python scripts\\run_business_evaluation.py --skip-ground-truth   # may khong noi duoc SQL Server
    python scripts\\run_business_evaluation.py --dry-run             # chi in danh sach, khong goi gi
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import importlib.util
import io
import json
import os
import re
import statistics
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
# APPEND, khong insert(0): xem ghi chu day du trong scripts/evaluate_model_canary.py va
# tests/test_tool_merger.py - insert(0) tung lam vo tests/test_phase1_phase2.py 4 lan.
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load_env_before_first_call() -> None:
    """Nap backend/.env vao os.environ TRUOC KHI goi nl2sql.ask() lan dau.

    18/08/2026 (thuc te, khong phai gia dinh): chay that 90 cau, CAU DAU TIEN (Q001) tra ve
    '⚠️ Chua cau hinh API Key' - KHONG PHAI vi thieu key that, ma vi kich ban nay chay nhu SCRIPT
    DOC LAP (khong qua backend/main.py, noi duy nhat tu goi load_env() khi khoi dong service that).
    ANTHROPIC_API_KEY chi vo tinh xuat hien trong os.environ SAU KHI mot tool nao do cham toi SQL
    Server song lan dau (query_engine._get_engine("bravo") tu goi _load_project_connection_env(),
    nap CA FILE .env nhu mot tac dung phu) - nen CAC CAU DAU, truoc khi co tool nao cham Bravo,
    deu dinh loi nay va bi cham diem oan la "khong goi tool" (tu bia du lieu), trong khi that ra
    la ha tang chua san sang, khong lien quan gi toi chat luong tra loi.
    Sua bang cach tu nap .env O DAY, giong het main.py::load_env() - dam bao moi cau, ke ca cau
    dau tien, chay trong cung mot dieu kien nhu production that."""
    for env_path in (BACKEND / ".env", ROOT / ".env"):
        if not env_path.exists():
            continue
        with io.open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env_before_first_call()

AUDIT_LOG = BACKEND / "logs" / "audit_log.jsonl"
COST_LOG = BACKEND / "logs" / "cost_log.jsonl"
RESULTS_DIR = ROOT / "results"

REFUSAL_MARKERS = ("qua phuc tap", "quá phức tạp", "vui long hoi cu the", "vui lòng hỏi cụ thể")
# Chi kiem trong CAU TRA LOI (khong phai cau hoi) - khac evaluate_model_canary.py von chi kiem
# tu ngu cua CASE luc dinh nghia. O day bat dung luc model TU SINH ra tu du bao trong luc tra
# loi, du cau hoi hoan toan khong nhac toi.
FORECAST_LEAK_MARKERS = ("dự báo", "du bao", "ước tính", "uoc tinh", "forecast")
FORECAST_NEGATIONS = (
    "không", "khong", "chưa", "chua", "không phải", "khong phai", "không dùng",
    "khong dung", "không có", "khong co", "không tự", "khong tu",
)

# "gon" = du nho de doi chieu CHAC CHAN bang may, khong doan y nguoi hoi.
COMPACT_MAX_ROWS = 3
COMPACT_MAX_NUMERIC_CELLS = 12
MIN_DIGIT_RUN = 5  # duoi muc nay de tranh khop nham so trang/phan tram/thu tu dong


def _json_safe(value: Any) -> Any:
    """default= cho json.dumps: ket qua checker SQL Server tra ve nguyen kieu driver
    (decimal.Decimal cho cot tien, datetime.date/datetime cho cot ngay) - json chuan KHONG
    biet serialize 2 kieu nay va se nem TypeError.

    18/08/2026 (thuc te, khong phai gia dinh): chay that 90 cau tren may 24, TON TIEN VA THOI
    GIAN GOI CHATBOT THAT XONG CA 90 CAU, roi vo ngay o dong ghi file CUOI CUNG vi dung ground
    truth co cot decimal - mat trang toan bo ket qua da tra tien, phai chay lai tu dau. Chuyen
    Decimal thanh str() (giu nguyen chinh xac, khong quy tron qua float) thay vi so nguyen/thuc,
    vi day la file bang chung de nguoi kiem doi chieu, khong phai so dung de tinh toan tiep."""
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _dump_results_or_die_trying(payload: dict, json_path: Path) -> None:
    """Ghi JSON voi bo chuyen doi kieu biet truoc (_json_safe). Neu VAN con kieu la chua tung
    thay (tuong lai checker moi tra ve kieu khac), rong bien ca xuong default=str (chuyen MOI
    thu thanh chuoi, khong the that bai voi bat ky doi tuong Python nao) - tha co file xau con
    hon lai mat trang mot lan chay da ton tien nhu 18/08/2026."""
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_safe)
    except TypeError:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    json_path.write_text(text, encoding="utf-8")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _digits_of(value: Any) -> str:
    """Chuoi chu so cua 1 O DU LIEU SQL (khong phai van ban tu do), bo het dau phan cach/don vi.
    So thuc/Decimal duoc lam tron ve so nguyen truoc (doanh thu/KPI trong mien nay luon la don
    vi nguyen), tranh '39327016119.0' hay ky phap khoa hoc lam sai lech so sanh.

    CO Y bo qua chuoi ky tu (str) - KHONG rut chu so tu do: cot ma khach hang/nhan vien tra ve
    tu SQL la string (vd "HCM04298", "TM23110128"). Neu rut '04298' tu "HCM04298" roi doi hoi
    no phai xuat hien trong cau tra loi thi mot cot MA lai bien thanh mot 'con so can doi chieu'
    khong co that - da bat duoc bang test truoc khi len production."""
    if value is None or isinstance(value, (bool, str)):
        return ""
    if isinstance(value, int):
        return re.sub(r"\D", "", str(value))
    if isinstance(value, float):
        try:
            return re.sub(r"\D", "", str(int(round(value))))
        except (ValueError, OverflowError):
            return ""
    try:  # decimal.Decimal va cac kieu tuong tu tu driver SQL
        return re.sub(r"\D", "", str(int(round(float(value)))))
    except (TypeError, ValueError):
        return ""


# Khop CA HAI dang: so da dinh dang theo nhom 3 chu so ("39.327.016.119" hoac kieu Anh-My
# "39,327,016,119"), VA day so tho khong dau phan cach. Khong dung \d+ don gian: dau cham/phay
# ngan nghin CAT chuoi so THAT thanh nhieu cum ngan ("39", "327", "016", "119"), khong cum nao
# du dai de vuot MIN_DIGIT_RUN - lam MOI so dung dinh dang deu bi bao "thieu", du cau tra loi
# hoan toan chinh xac. Da bat duoc bang test truoc khi len production (xem
# test_significant_digit_runs_bo_qua_so_qua_ngan).
_FORMATTED_NUMBER = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")


# 18/08/2026 (thuc te): Q003 tren du lieu that tra loi "Cao nhat: 27/07 voi 6,54 ty dong" - KHONG
# kem so nguyen day du nhu quy uoc thay o cac tool bao cao chuan (report_templates.py::money()).
# Day la cach tra loi HOP LY cho cau hoi dang "ngay nao cao nhat" (khong ai muon doc so le 11 chu
# so cho moi ngay) - quy uoc so nguyen day du chi dang tin cho tool CO DINH, khong phai cho SQL
# TU DO/prose tu do cua model. Neu khong xu ly rieng, MOI cau kieu nay bi bao "sai_so_lieu" oan.
# Vi VN dung dau PHAY lam dau THAP PHAN o day (khac dau CHAM ngan nghin trong so nguyen day du).
_ROUNDED_UNIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tỷ|ty|triệu|trieu|nghìn|nghin|ngàn|ngan)\b",
                          re.IGNORECASE)
_UNIT_SCALE = {"tỷ": 1e9, "ty": 1e9, "triệu": 1e6, "trieu": 1e6,
              "nghìn": 1e3, "nghin": 1e3, "ngàn": 1e3, "ngan": 1e3}
_ROUNDING_TOLERANCE = 0.01  # 1% - du rong cho lam tron 2 chu so thap phan o thang ty, du chat


def _rounded_numbers_in_text(text: str) -> list[tuple[float, Optional[float]]]:
    """Tra ve (gia_tri, dung_sai_tuyet_doi_hoac_None) cho moi so da lam tron kieu "X ty/trieu...".

    19/08/2026 (thuc te, khong phai gia dinh): chay that 90 cau, Q040 tra loi dung "3,1 ty" cho
    so that 3.052.479.909 (lam tron 1 chu so thap phan - hop le) nhung lech ~1,55%, VUOT nguong
    tuong doi 1% trong gang tac -> bi bao sai oan. Them dung sai TUYET DOI = nua buoc lam tron cua
    CHU SO THAP PHAN CUOI CUNG hien thi (vd "3,1 ty" hien 1 chu so thap phan -> buoc lam tron 0,1
    ty -> dung sai toi da +-0,05 ty = 50 trieu dong) - danh CHO cach lam tron co chu y nay.
    CHI tinh dung sai tuyet doi khi co IT NHAT 1 chu so thap phan hien thi - so tron KHONG thap
    phan (vd "7 ty") tra ve None cho phan tu do, BAT BUOC noi goi van chi dung dung sai tuong doi
    (_ROUNDING_TOLERANCE) - day co the la doan so mo ho chu khong phai lam tron co chu y (da co
    test khoa san dieu nay: test_so_lam_tron_qua_xa_van_bi_bao_sai, "7 ty" cho so that 6,54 ty
    PHAI van bi bao sai, khong duoc dung sai tuyet doi cuu no)."""
    out: list[tuple[float, Optional[float]]] = []
    for num_str, unit in _ROUNDED_UNIT.findall(text or ""):
        try:
            scale = _UNIT_SCALE[unit.lower()]
            value = float(num_str.replace(",", ".")) * scale
        except (ValueError, KeyError):
            continue
        parts = re.split(r"[.,]", num_str)
        abs_tolerance = 0.5 * (10 ** -len(parts[1])) * scale if len(parts) > 1 else None
        out.append((value, abs_tolerance))
    return out


def _significant_digit_runs(text: str, min_len: int = MIN_DIGIT_RUN) -> set[str]:
    runs = set()
    for match in _FORMATTED_NUMBER.findall(text or ""):
        digits = re.sub(r"\D", "", match)
        if len(digits) >= min_len:
            runs.add(digits)
    return runs


def _ground_truth_numbers(ground_truth: dict) -> set[str]:
    runs: set[str] = set()
    for row in ground_truth.get("rows", []):
        for cell in row:
            digits = _digits_of(cell)
            if len(digits) >= MIN_DIGIT_RUN:
                runs.add(digits)
    return runs


def _project_ground_truth(case, ground_truth: dict) -> dict:
    """Thu gon checker ve dung cac cot ma cau hoi yeu cau truoc khi cham.

    Checker SQL duoc phep tra them cot de audit/chan doan, nhung cac cot phu khong duoc bien thanh
    nghia vu bat model lap lai. Neu metadata sai ten cot thi fail-closed thanh loi evaluator thay vi
    am tham PASS.
    """
    wanted = tuple(getattr(case, "answer_columns", ()) or ())
    if not wanted or ground_truth.get("status") != "ok":
        return ground_truth
    columns = list(ground_truth.get("columns") or [])
    by_name = {str(name).casefold(): index for index, name in enumerate(columns)}
    missing = [name for name in wanted if name.casefold() not in by_name]
    if missing:
        return {
            "status": "loi",
            "reason": f"answer_columns khong ton tai trong checker: {missing}",
        }
    indexes = [by_name[name.casefold()] for name in wanted]
    projected = dict(ground_truth)
    projected["columns"] = list(wanted)
    projected["rows"] = [
        [row[index] for index in indexes]
        for row in ground_truth.get("rows", [])
    ]
    return projected


def _forecast_leaks(answer: str) -> list[str]:
    """Bat khang dinh du bao, bo qua cau phu dinh/canh bao ve chinh sach.

    `khong dung uoc tinh` la cau tu choi du bao dung quy tac, khong phai lo du bao. Regex cu chi
    tim tu khoa nen phat P0 oan cho nhung cau nhu vay.
    """
    lower = (answer or "").lower()
    leaked: list[str] = []
    for marker in FORECAST_LEAK_MARKERS:
        start = 0
        while True:
            index = lower.find(marker, start)
            if index < 0:
                break
            prefix = lower[max(0, index - 40):index]
            # Chi xet menh de hien tai (sau dau cau/xuong dong gan nhat), tranh mot "khong" o
            # cau truoc vo tinh mien tru cho mot du bao that o cau sau.
            prefix = re.split(r"[.!?;\n]", prefix)[-1]
            if not any(negation in prefix for negation in FORECAST_NEGATIONS):
                leaked.append(marker)
                break
            start = index + len(marker)
    return leaked


def _date_or_datetime_in_answer(value: Any, answer: str) -> bool:
    if isinstance(value, (dt.date, dt.datetime)):
        raw = value.isoformat()
    elif isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
        raw = value.strip()
    else:
        return False
    date_part = raw[:10]
    try:
        parsed = dt.date.fromisoformat(date_part)
    except ValueError:
        return False
    variants = {
        date_part,
        f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}",
        f"{parsed.day}/{parsed.month}/{parsed.year}",
    }
    if not any(variant in (answer or "") for variant in variants):
        return False
    time_match = re.search(r"[T ](\d{2}:\d{2})", raw)
    return not time_match or time_match.group(1) in (answer or "")


def _explicit_value_missing(value: Any, answer: str) -> bool:
    """So khop gia tri o cot duoc khai bao ro, ke ca count ngan va ngay gio."""
    if value is None:
        return False
    if _date_or_datetime_in_answer(value, answer):
        return False
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return False
        return raw.casefold() not in (answer or "").casefold()
    if isinstance(value, bool):
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if numeric == 0 and re.search(
        r"\b(không\s+(?:có|phát hiện|ghi nhận)|chưa\s+phát hiện)\b",
        (answer or "").casefold(),
    ):
        # Với checker count được khai báo tường minh, "không có trường hợp nào" mang đúng
        # nghĩa số lượng bằng 0; không ép câu trả lời tự nhiên phải in thêm chữ số 0.
        return False
    integer = str(int(round(numeric)))
    answer_numbers = _significant_digit_runs(answer, min_len=1)
    if integer in answer_numbers:
        return False
    if numeric > 0:
        for rounded_value, tolerance in _rounded_numbers_in_text(answer):
            if (abs(rounded_value - numeric) / numeric < _ROUNDING_TOLERANCE
                    or (tolerance is not None and abs(rounded_value - numeric) <= tolerance)):
                return False
    return True


def _is_compact(ground_truth: dict) -> bool:
    rows = ground_truth.get("rows", [])
    if len(rows) > COMPACT_MAX_ROWS:
        return False
    numeric_cells = sum(
        1 for row in rows for cell in row
        if isinstance(cell, (int, float)) or (isinstance(cell, str) and re.fullmatch(r"[\d.,\s]+", cell or ""))
    )
    return numeric_cells <= COMPACT_MAX_NUMERIC_CELLS


def _audit_by_session(session_ids: set[str]) -> dict[str, set[str]]:
    """Tool nao da chay cho tung session, doc tu audit_log.jsonl.

    18/08/2026 (thuc te, khong phai gia dinh): chay that 90 cau, 48 cau bi cham "khong_goi_tool"
    OAN - doc lai answer thi toan la cau tra loi CO SO LIEU THAT, chi tiet, bang bieu (vd "10.384
    dong cong no", "642 khach hang", "2.257.428 ban ghi lien ket CTKM"). Nguyen nhan: regex cu chi
    nhan dien <template:TEN>(...) - dung dinh dang cua call_template() (report_templates.py). Cau
    hoi phuc tap khong co template co dinh (tim nhan vien trung ma, khach vua doanh thu lon vua no
    qua han, cap san pham hay mua cung...) duoc tra loi qua run_query() (query_engine.py) - SQL TU
    DO, ghi log voi "sql": <chuoi SQL tho>, KHONG co tag <template:>. Day van la mot TOOL THAT,
    chay tren du lieu that (co validate read-only, co audit, co gioi han dong) - chi la khong
    mang ten co dinh. Bo sot no la nguyen nhan chinh cua 48/49 ca "khong_goi_tool" sai.

    Phan biet 2 dang bang su co mat cua khoa "db": call_template() KHONG bao gio ghi khoa nay
    (xem report_templates.py::call_template, entry chi co ts/username/question/sql/session_id),
    con run_query() LUON ghi (entry["db"] = db) - dang tin cay hon la doan qua hinh dang chuoi sql."""
    found: dict[str, set[str]] = {sid: set() for sid in session_ids}
    if not AUDIT_LOG.is_file():
        return found
    with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid not in found:
                continue
            match = re.search(r"<template:([a-zA-Z_]+)>", str(item.get("sql") or ""))
            if match:
                found[sid].add(match.group(1))
            elif "db" in item and item.get("status") == "ok":
                found[sid].add(f"sql_tu_do:{item['db']}")
    return found


def _cost_by_session(session_ids: set[str]) -> dict[str, float]:
    cost: dict[str, float] = {sid: 0.0 for sid in session_ids}
    if not COST_LOG.is_file():
        return cost
    with io.open(COST_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid in cost:
                cost[sid] += float(item.get("cost_usd") or 0.0)
    return cost


def _fetch_ground_truth(suite, checker_id: str, *, scope_area: Optional[str],
                        skip: bool) -> dict:
    if skip:
        return {"status": "bo_qua", "reason": "chay voi --skip-ground-truth"}
    checker = suite.CHECKERS.get(checker_id)
    if checker is None:
        return {"status": "loi", "reason": f"khong tim thay checker '{checker_id}'"}
    try:
        return suite._execute_checker(checker, scope_area=scope_area)
    except Exception as exc:  # May dev khong ket noi duoc SQL Server - ghi ro, KHONG coi la PASS.
        return {"status": "loi", "reason": f"{type(exc).__name__}: {exc}"}


def grade_case(case, answer: str, error: Optional[str], tools_called: list[str],
              ground_truth: dict) -> dict:
    problems: list[dict] = []

    if error:
        problems.append({"severity": "P0", "code": "loi_he_thong", "detail": error})

    lower = (answer or "").lower()
    if any(marker in lower for marker in REFUSAL_MARKERS):
        problems.append({"severity": "P0", "code": "tu_choi",
                         "detail": "Chatbot tu choi voi ly do 'qua phuc tap' - vi pham gate "
                                   "'0 tu choi voi cau co du dieu ho tro'."})

    leaked = _forecast_leaks(answer)
    if leaked:
        problems.append({"severity": "P0", "code": "lo_du_bao",
                         "detail": f"Cau tra loi chua tu ngu du bao bi cam: {leaked}"})

    if not error and not tools_called:
        # 19/08/2026 (thuc te, khong phai gia dinh): chay that 90 cau, ca 8/8 case dinh
        # "khong_goi_tool" deu KHONG phai loi that - 5 cau hoi lai hop le (vd "doi toi" nhung
        # evaluator luon chay duoi vai c_level, khong gan QLV cu the nao nen chatbot dung khi hoi
        # nguoc lai thay vi doan bua) va 3 cau giai thich quy tac co san (vd "vi sao khong cong
        # don...") tra loi dung tu kien thuc nghiep vu, khong can tra so moi. Diem chung: CA 8 cau
        # deu KHONG chua bat ky con so nghiep vu nao (khong day chu so dai, khong so dang "X ty/
        # trieu") trong cau tra loi - tuc khong co gi bi "bia" ca. Dung dung tin hieu nay de tach:
        # neu cau tra loi KHONG neu con so nghiep vu nao, ha xuong P2 va doi ma - van ghi nhan de
        # nguoi kiem doc duoc, nhung KHONG tinh la that bai tu dong. Neu VAN co con so (vd "khoang
        # 39 ty" - xem test_khong_goi_tool_nao_la_P0) ma khong tool nao chay, GIU NGUYEN P0 - do
        # moi dung la dau hieu tu bia so lieu that, khong duoc lam long boi quy tac nay.
        neu_con_so = bool(_significant_digit_runs(answer)) or bool(_rounded_numbers_in_text(answer))
        if neu_con_so:
            problems.append({"severity": "P0", "code": "khong_goi_tool",
                             "detail": "Tra loi so lieu nghiep vu ma khong tool nao duoc goi - "
                                       "dau hieu truc tiep cua tu bia du lieu."})
        else:
            problems.append({"severity": "P2", "code": "hoi_lai_hoac_giai_thich",
                             "detail": "Khong goi tool, nhung cau tra loi khong neu con so nghiep "
                                       "vu nao (hoi lai nguoi dung hoac giai thich quy tac co san) "
                                       "- khong phai dau hieu tu bia, KHONG tinh la that bai tu "
                                       "dong."})

    ground_truth = _project_ground_truth(case, ground_truth)
    gt_status = ground_truth.get("status")
    ground_truth_check = "khong_ap_dung"
    if gt_status == "ok" and not error:
        if _is_compact(ground_truth):
            explicit_columns = tuple(getattr(case, "answer_columns", ()) or ())
            if explicit_columns:
                missing_values = []
                for row in ground_truth.get("rows", []):
                    for value in row:
                        if _explicit_value_missing(value, answer):
                            missing_values.append(str(value))
                if missing_values:
                    problems.append({
                        "severity": "P0", "code": "sai_so_lieu",
                        "detail": "Thieu gia tri bat buoc theo answer_columns: "
                                  f"{missing_values[:5]}",
                    })
                    ground_truth_check = "fail"
                else:
                    ground_truth_check = "pass"
                # Khong chay lai nhanh so-khop-toan-checker o duoi.
                gt_numbers = set()
            else:
                gt_numbers = _ground_truth_numbers(ground_truth)
            ans_numbers = _significant_digit_runs(answer)
            missing_exact = gt_numbers - ans_numbers
            # Truoc khi ket luan la sai, thu khop voi so DA LAM TRON trong cau tra loi ("6,54 ty")
            # - hop le cho cau hoi dang tuong thuat (vd "ngay nao cao nhat"), khac han voi bao cao
            # co dinh luon in so nguyen day du. Chi thu khi CO thieu, tranh tinh toan thua.
            still_missing = missing_exact
            if missing_exact:
                rounded = _rounded_numbers_in_text(answer)
                still_missing = {m for m in missing_exact
                                 if not (int(m) > 0 and any(
                                     abs(rv - int(m)) / int(m) < _ROUNDING_TOLERANCE
                                     or (tol is not None and abs(rv - int(m)) <= tol)
                                     for rv, tol in rounded))}
            if gt_numbers and still_missing:
                problems.append({"severity": "P0", "code": "sai_so_lieu",
                                 "detail": f"Thieu {len(still_missing)} so tu SQL Server (da thu "
                                           f"ca dang lam tron nhu '6,54 ty'): "
                                           f"{sorted(still_missing)[:5]}"})
                ground_truth_check = "fail"
            elif gt_numbers and missing_exact:
                # Khop nho khop LAM TRON, khong phai so nguyen day du - ghi ro de khong ai tuong
                # day la khop tuyet doi giong cac checker khac.
                ground_truth_check = "pass_khop_so_lam_tron"
            elif gt_numbers:
                ground_truth_check = "pass"
            elif not explicit_columns:
                ground_truth_check = "khong_co_so_de_doi_chieu"
        else:
            ground_truth_check = "can_doi_chieu_tay"  # checker "top N" - danh cho nguoi kiem
    elif gt_status in ("loi", "bo_qua", "empty", None):
        ground_truth_check = f"chua_doi_chieu_duoc ({ground_truth.get('reason', gt_status)})"

    severities = {p["severity"] for p in problems}
    passed_auto = "P0" not in severities and not error
    return {
        "problems": problems,
        "passed_auto": passed_auto,
        "ground_truth_check": ground_truth_check,
        "needs_human_review": ground_truth_check == "can_doi_chieu_tay",
    }


def evaluate(suite, cases, *, label: str, delay_seconds: float, skip_ground_truth: bool,
            scope_area: Optional[str]) -> list[dict]:
    import nl2sql

    results: list[dict] = []
    for index, case in enumerate(cases, 1):
        session_id = f"beval-{label}-{case.id}-{uuid.uuid4().hex[:8]}"
        print(f"[{index}/{len(cases)}] {case.id} [{case.audience}] {case.question[:60]}", flush=True)
        started = time.monotonic()
        try:
            response = nl2sql.ask(case.question, session_id=session_id,
                                 username="business-eval", scope_role="c_level")
            answer, error = str(response.get("answer") or ""), None
        except Exception as exc:
            answer, error = "", f"{type(exc).__name__}: {exc}"
        duration = round(time.monotonic() - started, 2)
        ground_truth = _fetch_ground_truth(suite, case.checker_id, scope_area=scope_area,
                                           skip=skip_ground_truth)
        results.append({
            "case": asdict(case), "session_id": session_id, "answer": answer, "error": error,
            "duration_seconds": duration, "ground_truth": ground_truth,
        })
        if delay_seconds:
            time.sleep(delay_seconds)

    audit = _audit_by_session({r["session_id"] for r in results})
    cost = _cost_by_session({r["session_id"] for r in results})
    for r in results:
        tools = sorted(audit[r["session_id"]])
        r["tools_called"] = tools
        r["cost_usd"] = round(cost[r["session_id"]], 6)
        r["grade"] = grade_case(_CaseView(**r["case"]), r["answer"], r["error"], tools,
                                r["ground_truth"])
    return results


class _CaseView:
    """Bien du lieu case tu dict (sau khi da qua asdict) tro lai co thuoc tinh, tranh phai
    truyen ca doi tuong BusinessCase xuyen qua vong lap sau khi da serialize."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def render_markdown(results: list[dict], label: str) -> str:
    total = len(results)
    auto_pass = sum(1 for r in results if r["grade"]["passed_auto"])
    needs_review = sum(1 for r in results if r["grade"]["needs_human_review"])
    # "dat tu dong" va "can doi chieu tay" la 2 CO DOC LAP (1 cau "top N" khong dinh P0 nao khac
    # se dong thoi True o ca hai) - cong truc tiep 2 dong tren se RA QUA TONG SO CAU, tung gay
    # hieu nham that tren may 24 (31 + 65 = 96 != 90). Them 3 nhom LOAI TRU LAN NHAU de doc dung.
    sach_hoan_toan = sum(1 for r in results
                         if r["grade"]["passed_auto"] and not r["grade"]["needs_human_review"])
    can_doi_chieu = sum(1 for r in results
                        if r["grade"]["passed_auto"] and r["grade"]["needs_human_review"])
    that_bai = total - auto_pass
    by_group: dict[str, list[dict]] = {}
    for r in results:
        by_group.setdefault(r["case"]["group"], []).append(r)

    lines = [
        f"# Kết quả đánh giá nghiệp vụ — {label}",
        "",
        f"Chạy lúc: {dt.datetime.now().strftime('%H:%M %d/%m/%Y')}",
        "",
        "**Đọc bảng này đúng cách**: `Đạt (tự động)` chỉ xác nhận KHÔNG có lỗi hệ thống, từ "
        "chối, lộ dự báo, thiếu tool, hay sai số ở các checker gọn. Dòng `cần đối chiếu tay` "
        "là 'top N' - máy KHÔNG tự phán đúng/sai, phải mở `ground_truth` trong file JSON kèm "
        "theo và so bằng mắt, đúng tinh thần gốc của `business_stress_suite.py`. Hai cờ này ĐỘC "
        "LẬP — một câu 'top N' không dính lỗi nào khác vẫn đạt tự động VÀ vẫn cần đối chiếu tay "
        "cùng lúc, nên đừng cộng thẳng 2 dòng dưới đây (sẽ ra quá tổng số câu); dùng bảng 3 nhóm "
        "loại trừ lẫn nhau ngay sau đây để biết chính xác việc còn phải làm.",
        "",
        f"- Tổng số câu: {total}",
        f"- Đạt tự động (0 vấn đề P0): {auto_pass}/{total}",
        f"- Cần đối chiếu tay (checker dạng danh sách): {needs_review}",
        "",
        "| | Số câu | Việc cần làm |",
        "|---|---:|---|",
        f"| Sạch hoàn toàn | {sach_hoan_toan} | Không cần làm gì thêm |",
        f"| Cần đối chiếu tay | {can_doi_chieu} | Mở `ground_truth` trong JSON, so bằng mắt — KHÔNG phải lỗi |",
        f"| Thất bại thật sự | {that_bai} | Xem mục 'Câu chưa đạt tự động' bên dưới — cần sửa |",
        f"| **Tổng** | **{sach_hoan_toan + can_doi_chieu + that_bai}** | (phải khớp {total}) |",
        "",
        "## Theo nhóm nghiệp vụ",
        "",
        "| Nhóm | Đạt tự động | Cần đối chiếu tay | Tổng |",
        "|---|---:|---:|---:|",
    ]
    for group, items in sorted(by_group.items()):
        g_pass = sum(1 for r in items if r["grade"]["passed_auto"])
        g_review = sum(1 for r in items if r["grade"]["needs_human_review"])
        lines.append(f"| {group} | {g_pass}/{len(items)} | {g_review} | {len(items)} |")

    failing = [r for r in results if not r["grade"]["passed_auto"]]
    if failing:
        lines += ["", "## Câu chưa đạt tự động", ""]
        for r in failing:
            probs = "; ".join(f"[{p['severity']}] {p['code']}: {p['detail']}" for p in r["grade"]["problems"])
            lines.append(f"- **{r['case']['id']}** ({r['case']['audience']}) — {r['case']['question'][:70]}")
            lines.append(f"  {probs}")

    durations = [r["duration_seconds"] for r in results if not r["error"]]
    if durations:
        durations_sorted = sorted(durations)
        p50 = statistics.median(durations_sorted)
        p95 = durations_sorted[min(len(durations_sorted) - 1, int(len(durations_sorted) * 0.95))]
        total_cost = sum(r["cost_usd"] for r in results)
        lines += [
            "",
            "## Hiệu năng & chi phí",
            "",
            f"- Thời gian trả lời: P50 {p50:.1f}s · P95 {p95:.1f}s",
            f"- Tổng chi phí lần chạy này: ${total_cost:.4f}",
        ]

    return "\n".join(lines) + "\n"


def _selected_cases(suite, args):
    cases = list(suite.CASES)
    if args.case:
        wanted = {c.upper() for c in args.case}
        cases = [c for c in cases if c.id in wanted]
    if args.group:
        needle = args.group.casefold()
        cases = [c for c in cases if needle in c.group.casefold()]
    if args.audience:
        cases = [c for c in cases if c.audience == args.audience]
    if args.limit:
        cases = cases[:args.limit]
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="current-model")
    parser.add_argument("--case", nargs="*", default=None, help="Chi chay dung cac ma nay (Q001...)")
    parser.add_argument("--group", default=None, help="Loc theo nhom (khop mot phan, khong phan biet hoa thuong)")
    parser.add_argument("--audience", default=None, choices=["qlv", "tp", "manager", "c_level"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=7.0, help="Giay nghi giua 2 cau (gioi han 10 cau/phut)")
    parser.add_argument("--skip-ground-truth", action="store_true",
                        help="May khong noi duoc SQL Server - chi cham 4 muc tu-log, bo doi chieu so")
    parser.add_argument("--scope-area", default=None, help="Bat buoc cho checker DEBT_SCOPE_AGING")
    parser.add_argument("--dry-run", action="store_true", help="Chi in danh sach cau se chay")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    suite = _load_module("business_stress_suite", ROOT / "scripts" / "business_stress_suite.py")
    errors = suite.validate_catalog()
    if errors:
        print("Bo cau hoi khong hop le, dung lai:")
        for e in errors:
            print(" ", e)
        return 2

    cases = _selected_cases(suite, args)
    if not cases:
        print("Khong co cau nao khop bo loc.")
        return 1

    if args.dry_run:
        for c in cases:
            print(f"{c.id} [{c.audience}/{c.group}] {c.question} -> {c.checker_id}")
        print(f"\nTong: {len(cases)} cau (dry-run, chua goi gi)")
        return 0

    results = evaluate(suite, cases, label=args.label, delay_seconds=args.delay,
                       skip_ground_truth=args.skip_ground_truth, scope_area=args.scope_area)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = Path(args.output) if args.output else RESULTS_DIR / f"business-eval-{args.label}-{stamp}.json"
    md_path = json_path.with_suffix(".md")

    auto_pass = sum(1 for r in results if r["grade"]["passed_auto"])
    payload = {"label": args.label, "run_at": dt.datetime.now().isoformat(),
              "total": len(results), "passed_auto": auto_pass, "results": results}

    # Ghi JSON TRUOC, tach rieng khoi Markdown: da hoi that 90 cau (ton tien + thoi gian that)
    # truoc khi toi diem nay, nen tu day tro di TUYET DOI khong duoc de 1 loi ren tiep (vd
    # render_markdown lam vo mot cach khac) lam mat ket qua da co trong tay.
    _dump_results_or_die_trying(payload, json_path)
    print(f"  JSON: {json_path}")
    try:
        md_path.write_text(render_markdown(results, args.label), encoding="utf-8")
        print(f"  Markdown: {md_path}")
    except Exception as exc:
        print(f"  CANH BAO: sinh Markdown loi ({type(exc).__name__}: {exc}) - "
              f"nhung JSON o tren van du du lieu, khong mat gi.")

    # 18/08/2026: "dat tu dong" va "can doi chieu tay" la 2 CO DOC LAP - 1 cau "top N" khong
    # dinh loi P0 nao khac se dong thoi True o CA HAI, nen in rieng roi cong lai se ra > tong so
    # cau (dung xay ra tren may 24: 31 + 65 = 96 != 90, gay hieu nham). Chia lai thanh 3 nhom
    # LOAI TRU LAN NHAU, cong dung bang tong.
    sach_hoan_toan = sum(1 for r in results
                         if r["grade"]["passed_auto"] and not r["grade"]["needs_human_review"])
    can_doi_chieu = sum(1 for r in results
                        if r["grade"]["passed_auto"] and r["grade"]["needs_human_review"])
    that_bai = sum(1 for r in results if not r["grade"]["passed_auto"])
    assert sach_hoan_toan + can_doi_chieu + that_bai == len(results)  # 3 nhom PHAI khop tong

    print(f"\nKET QUA ({len(results)} cau):")
    print(f"  Sach hoan toan (khong can lam gi them) : {sach_hoan_toan}")
    print(f"  Can nguoi doi chieu tay ('top N')       : {can_doi_chieu}  (KHONG phai loi - "
          f"xem ground_truth trong JSON)")
    print(f"  That bai that su (co P0)                : {that_bai}  <-- xem muc 'Cau chua dat "
          f"tu dong' trong file .md")
    return 0 if that_bai == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
