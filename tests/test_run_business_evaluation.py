# -*- coding: utf-8 -*-
"""Kiểm chứng logic chấm điểm của scripts/run_business_evaluation.py bằng dữ liệu giả -
không gọi model thật, không cần SQL Server. Chạy được trên bất kỳ máy nào.

Trọng tâm: chứng minh máy chỉ tự tin PHÁN khi thật sự chắc (checker gọn, đủ số), và biết
NHẬN RA khi nó không chắc (checker dạng danh sách -> cần_đối_chiếu_tay, không âm thầm PASS).
"""
import datetime as _dt
import decimal
import importlib.util
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))

_SPEC = importlib.util.spec_from_file_location(
    "run_business_evaluation", ROOT / "scripts" / "run_business_evaluation.py"
)
runner = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)


@dataclass(frozen=True)
class _Case:
    id: str
    group: str
    audience: str
    question: str
    checker_id: str
    pass_rule: str = ""


# ---------------------------------------------------------------- so hoc thuan (khong can mock)

def test_digits_of_lam_tron_so_thuc_va_bo_ky_phap_khoa_hoc():
    assert runner._digits_of(39_327_016_119) == "39327016119"
    assert runner._digits_of(39_327_016_119.0) == "39327016119"
    assert runner._digits_of(1_330_072_584.4) == "1330072584"  # lam tron, khong cat cut
    assert runner._digits_of(None) == ""
    assert runner._digits_of(True) == ""  # bool la subclass cua int - phai loai rieng


def test_significant_digit_runs_bo_qua_so_qua_ngan():
    text = "Top 20 khach hang, doanh thu 39.327.016.119 d, ty le 85%"
    runs = runner._significant_digit_runs(text)
    assert "39327016119" in runs
    assert "20" not in runs  # ngan hon MIN_DIGIT_RUN, tranh khop nham thu tu/phan tram
    assert "85" not in runs


def test_digits_of_KHONG_rut_so_tu_ma_khach_hang():
    """Cot ma khach/nhan vien tra ve tu SQL la str ("HCM04298") - KHONG duoc coi day la so can
    doi chieu, neu khong mot cot MA se bien thanh mot con so 'sai' moi khi khong khop van ban."""
    assert runner._digits_of("HCM04298") == ""
    assert runner._digits_of("TM23110128") == ""
    assert runner._digits_of("OTC") == ""
    assert runner._digits_of(39_327_016_119) == "39327016119"  # so THAT (int) van hoat dong


def test_ground_truth_numbers_gom_tu_nhieu_dong():
    gt = {"status": "ok", "rows": [[39_327_016_119, "OTC"], [35_508_451_204, "ETC"]]}
    assert runner._ground_truth_numbers(gt) == {"39327016119", "35508451204"}


def test_ground_truth_numbers_bo_qua_cot_ma_du_dung_1_dong():
    """Checker gon van co the co 1 cot ma (vd DEBT_SUMMARY co the kem area_code) - cot do
    khong duoc gop vao tap so can doi chieu."""
    gt = {"status": "ok", "rows": [["MBKV12", 4_482_140_193, "84.8%"]]}
    assert runner._ground_truth_numbers(gt) == {"4482140193"}


def test_is_compact_theo_so_dong_va_so_o_so():
    gon = {"rows": [[39_327_016_119, 35_508_451_204]]}
    assert runner._is_compact(gon) is True

    top_n = {"rows": [[f"KH{i}", 1_000_000 * i] for i in range(1, 21)]}
    assert runner._is_compact(top_n) is False


# ---------------------------------------------------------------- cham diem 1 cau

BASE_CASE = _Case("Q001", "Doanh thu", "c_level", "Doanh thu tháng 7 tách OTC/ETC?", "REV_CHANNEL")


def test_loi_he_thong_la_P0():
    r = runner.grade_case(BASE_CASE, "", "TimeoutError: het gio", ["get_revenue_by_channel"],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "loi_he_thong" for p in r["problems"])


def test_tu_choi_la_P0():
    r = runner.grade_case(BASE_CASE, "Xin loi, cau hoi qua phuc tap can nhieu buoc.", None,
                          [], {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "tu_choi" for p in r["problems"])


def test_lo_du_bao_trong_cau_tra_loi_la_P0():
    r = runner.grade_case(BASE_CASE, "Ước tính tháng 8 sẽ đạt 50 tỷ.", None,
                          ["get_revenue_forecast"], {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "lo_du_bao" for p in r["problems"])


def test_canh_bao_khong_uoc_tinh_khong_bi_cham_lo_du_bao():
    answer = "Đây là số đã chốt từ bảng quy tắc, không dùng ước tính hay dự báo tương lai."
    r = runner.grade_case(BASE_CASE, answer, None, ["get_salary_bonus_policy"],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is True
    assert not any(p["code"] == "lo_du_bao" for p in r["problems"])


def test_phu_dinh_o_cau_truoc_khong_che_du_bao_that_o_cau_sau():
    answer = "Không dùng ước tính cũ. Dự báo tháng 8 sẽ đạt 50 tỷ."
    r = runner.grade_case(BASE_CASE, answer, None, ["get_salary_bonus_policy"],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "lo_du_bao" for p in r["problems"])


def test_khong_goi_tool_nao_la_P0():
    r = runner.grade_case(BASE_CASE, "Doanh thu tháng 7 khoảng 39 tỷ.", None, [],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "khong_goi_tool" for p in r["problems"])


def test_khong_goi_tool_voi_day_chu_so_dai_van_la_P0():
    """Con so day du (khong kem don vi ty/trieu) cung phai bi bat, khong chi rieng dang "X ty"."""
    r = runner.grade_case(BASE_CASE, "Doanh thu tháng 7 là 39327016119 đồng.", None, [],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "khong_goi_tool" for p in r["problems"])


def test_hoi_lai_khong_goi_tool_khong_bi_tinh_la_that_bai():
    """19/08/2026 (thuc te): Q018/Q023/Q055/Q032/Q033 - chatbot hoi lai "doi nao"/"ky nao" thay
    vi doan bua vi evaluator khong gan QLV/ky cu the. Cau tra loi KHONG neu con so nghiep vu nao
    - khong co gi de "bia" - nen KHONG duoc tinh la that bai tu dong nhu tu bia du lieu that."""
    r = runner.grade_case(BASE_CASE, "Anh muốn hỏi về đội của quản lý vùng nào ạ?", None, [],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is True
    assert any(p["code"] == "hoi_lai_hoac_giai_thich" for p in r["problems"])
    assert not any(p["code"] == "khong_goi_tool" for p in r["problems"])


def test_giai_thich_quy_tac_khong_goi_tool_cung_khong_bi_tinh_la_that_bai():
    """19/08/2026 (thuc te): Q021/Q060/Q061 - giai thich quy tac/nguong da biet (65%/80%/100%),
    khong tra so lieu moi nen khong can tool. Nguong % qua ngan de vuot MIN_DIGIT_RUN va khong
    phai don vi tien (ty/trieu) nen khong bi coi la con so nghiep vu can tool xac nhan."""
    answer = ("Ngưỡng đạt KPI là 80%, ngưỡng đạt chỉ tiêu là 100%, ngưỡng thưởng nhóm hàng TDV là "
             "65%. Ba mốc này độc lập, không được gộp làm một.")
    r = runner.grade_case(BASE_CASE, answer, None, [], {"status": "bo_qua"})
    assert r["passed_auto"] is True
    assert any(p["code"] == "hoi_lai_hoac_giai_thich" for p in r["problems"])


def test_checker_gon_du_so_thi_dat():
    gt = {"status": "ok", "rows": [[39_327_016_119, 35_508_451_204]]}
    answer = "OTC: 39.327.016.119 đ, ETC: 35.508.451.204 đ"
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass"
    assert r["needs_human_review"] is False


def test_khop_so_lam_tron_kieu_viet_nam_nhu_Q003_that():
    """Dung nguyen van cau tra loi that cua Q003 tren may 24 18/08/2026: '6,54 ty dong' - khong
    kem so nguyen day du. Truoc ban va bi cham 'sai_so_lieu' oan vi khong co digit-run nao khop."""
    gt = {"status": "ok", "rows": [[6_540_000_000]]}
    answer = ("Trong tháng 7/2026 (27 ngày có phát sinh):\n\n- **Cao nhất:** 27/07 với "
             "6,54 tỷ đồng\n- **Thấp nhất:** 04/07 với 0,39 tỷ đồng (387,6 triệu)")
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass_khop_so_lam_tron"


def test_so_lam_tron_qua_xa_van_bi_bao_sai():
    """Khoan dung KHONG duoc thanh lo hong: '7 ty' lech 7% so voi 6,54 ty phai VAN bi bao sai,
    khong duoc lam tron cuu no."""
    gt = {"status": "ok", "rows": [[6_540_000_000]]}
    answer = "Cao nhất khoảng 7 tỷ đồng."
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is False
    assert r["ground_truth_check"] == "fail"


def test_lam_tron_1_chu_so_thap_phan_gan_bien_1_phan_tram_van_dat():
    """19/08/2026 (thuc te): Q040 tra loi "3,1 ty" cho so that 3.052.479.909 - lam tron 1 chu so
    thap phan hop le, nhung lech ~1,55% vuot nguong tuong doi 1% trong gang tac, bi bao sai oan.
    Dung sai tuyet doi (nua buoc lam tron cua 1 chu so thap phan o thang ty = 50 trieu) phai cuu
    duoc ca nay ma KHONG lam long nguong cho so tron khong thap phan (xem test ben duoi)."""
    gt = {"status": "ok", "rows": [[3_052_479_909]]}
    answer = "Nợ quá hạn 16-30 ngày kênh OTC là 3,1 tỷ đồng."
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass_khop_so_lam_tron"


def test_checker_gon_thieu_so_thi_sai_so_lieu():
    gt = {"status": "ok", "rows": [[39_327_016_119, 35_508_451_204]]}
    answer = "OTC: 39.327.016.119 đ, ETC: khoảng 35 tỷ"  # thieu so ETC chinh xac
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is False
    assert r["ground_truth_check"] == "fail"
    assert any(p["code"] == "sai_so_lieu" for p in r["problems"])


def test_answer_columns_khong_bat_so_phu_khong_duoc_hoi_Q083():
    case = _Case(
        "Q083", "Khuyến mãi", "manager",
        "Chuỗi liên kết đơn hàng–khuyến mãi hiện có dữ liệu đến ngày nào?",
        "PROMO_COVERAGE",
    )
    object.__setattr__(case, "answer_columns", ("LastLinkedOrderDate",))
    gt = {
        "status": "ok",
        "columns": ["FirstLinkedOrderDate", "LastLinkedOrderDate", "LinkRows", "LinkedOrders"],
        "rows": [["2025-01-01", "2026-01-09", 2_257_428, 495_199]],
    }
    r = runner.grade_case(case, "Dữ liệu liên kết hiện đến ngày 09/01/2026.", None,
                          ["get_promotion_data_quality"], gt)
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass"


def test_answer_columns_Q084_chi_bat_hai_loai_lien_ket_loi():
    case = _Case(
        "Q084", "Khuyến mãi", "c_level",
        "Có bao nhiêu liên kết khuyến mãi mất đơn hàng hoặc mất mã chương trình?",
        "PROMO_QUALITY",
    )
    object.__setattr__(case, "answer_columns", ("MissingOrder", "MissingProgram"))
    gt = {
        "status": "ok",
        "columns": ["LinkRows", "MissingOrder", "MissingProgram", "ValidLinks"],
        "rows": [[2_257_428, 12, 22, 2_257_394]],
    }
    r = runner.grade_case(case, "Thiếu đơn hàng: 12; thiếu mã chương trình: 22.", None,
                          ["get_promotion_data_quality"], gt)
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass"


def test_answer_columns_sai_ten_cot_fail_closed():
    case = _Case("QX", "G", "c_level", "q", "X")
    object.__setattr__(case, "answer_columns", ("CotKhongTonTai",))
    gt = {"status": "ok", "columns": ["Dung"], "rows": [[123]]}
    r = runner.grade_case(case, "123", None, ["t"], gt)
    assert "chua_doi_chieu_duoc" in r["ground_truth_check"]


def test_answer_column_count_0_chap_nhan_cau_phu_dinh_tu_nhien():
    case = _Case("Q016", "Đội ngũ", "manager", "Có TDV thiếu quản lý không?", "KPI_MISSING_MANAGER")
    object.__setattr__(case, "answer_columns", ("MissingManagerCount",))
    gt = {
        "status": "ok",
        "columns": ["MissingManagerCount", "EmployeeCode"],
        "rows": [[0, None]],
    }
    r = runner.grade_case(
        case,
        "Không phát hiện TDV nào thiếu quản lý trực tiếp trong snapshot tháng 7.",
        None,
        ["sql_tu_do:bravo"],
        gt,
    )
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass"


def test_answer_column_count_khac_0_van_bat_buoc_co_so():
    case = _Case("Q016", "Đội ngũ", "manager", "Có TDV thiếu quản lý không?", "KPI_MISSING_MANAGER")
    object.__setattr__(case, "answer_columns", ("MissingManagerCount",))
    gt = {"status": "ok", "columns": ["MissingManagerCount"], "rows": [[3]]}
    r = runner.grade_case(
        case,
        "Có một số TDV thiếu quản lý trực tiếp.",
        None,
        ["sql_tu_do:bravo"],
        gt,
    )
    assert r["passed_auto"] is False
    assert r["ground_truth_check"] == "fail"


def test_checker_dang_top_n_KHONG_duoc_tu_phan_dung_sai():
    """Diem quan trong nhat: 'top N' phai di thang vao can nguoi kiem, KHONG duoc coi la
    dat chi vi khong bat duoc loi nao khac. day la ranh gioi giua tu tin that va bia do tin cay."""
    gt = {"status": "ok", "rows": [[f"KH{i}", 1_000_000 * i] for i in range(1, 21)]}
    answer = "Top khách hàng lớn nhất là KH20 với 20.000.000 đ, ..."
    r = runner.grade_case(BASE_CASE, answer, None, ["get_top_customers"], gt)
    assert r["ground_truth_check"] == "can_doi_chieu_tay"
    assert r["needs_human_review"] is True
    # KHONG co P0 nao khac -> passed_auto van True (khong bi phat vi thu no khong tu cham duoc)
    assert r["passed_auto"] is True


def test_ground_truth_loi_thi_khong_duoc_am_tham_thanh_pass():
    gt = {"status": "loi", "reason": "khong noi duoc SQL Server"}
    answer = "OTC: 39.327.016.119 đ"
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert "chua_doi_chieu_duoc" in r["ground_truth_check"]
    assert r["passed_auto"] is True  # khong co P0 nao khac, nhung KHONG duoc bao "pass" so lieu
    assert r["ground_truth_check"] != "pass"


def test_bo_qua_ground_truth_khi_skip_flag():
    gt = {"status": "bo_qua", "reason": "chay voi --skip-ground-truth"}
    r = runner.grade_case(BASE_CASE, "OTC: 39.327.016.119 đ", None,
                          ["get_revenue_by_channel"], gt)
    assert "chua_doi_chieu_duoc" in r["ground_truth_check"]


# ---------------------------------------------------------------- evaluate() dau-cuoi voi gia lap

class _FakeSuite:
    CASES = [
        _Case("Q001", "Doanh thu", "c_level", "Doanh thu tháng 7 tách OTC/ETC?", "REV_CHANNEL"),
        _Case("Q002", "Khách hàng", "c_level", "Top 5 khách hàng tháng 7?", "CUS_TOP"),
    ]
    CHECKERS = {"REV_CHANNEL": SimpleNamespace(id="REV_CHANNEL", database="bravo"),
               "CUS_TOP": SimpleNamespace(id="CUS_TOP", database="bravo")}

    @staticmethod
    def validate_catalog():
        return []

    @staticmethod
    def _execute_checker(checker, scope_area=None):
        if checker.id == "REV_CHANNEL":
            return {"status": "ok", "rows": [[39_327_016_119, 35_508_451_204]]}
        return {"status": "ok", "rows": [[f"KH{i}", 1_000_000 * i] for i in range(1, 6)]}


@pytest.fixture
def fake_answers(monkeypatch):
    """Gia lap nl2sql.ask(): Q001 tra loi dung du so, Q002 la 'top N' nen khong the tu cham."""
    import nl2sql

    def fake_ask(question, session_id, username=None, scope_role=None, **kw):
        if "OTC/ETC" in question:
            text = "OTC: 39.327.016.119 đ, ETC: 35.508.451.204 đ"
            tool = "get_revenue_by_channel"
        else:
            text = "Top khách: KH5 5.000.000 đ, KH4 4.000.000 đ, ..."
            tool = "get_top_customers"
        # ghi audit log GIONG HET production: 1 dong <template:...> theo session_id
        with io.open(runner.AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"session_id": session_id,
                                "sql": f"<template:{tool}>({{}})"}) + "\n")
        with io.open(runner.COST_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"session_id": session_id, "cost_usd": 0.001}) + "\n")
        return {"answer": text}

    monkeypatch.setattr(nl2sql, "ask", fake_ask)
    return fake_ask


def test_evaluate_dau_cuoi_voi_gia_lap(tmp_path, monkeypatch, fake_answers):
    monkeypatch.setattr(runner, "AUDIT_LOG", tmp_path / "audit_log.jsonl")
    monkeypatch.setattr(runner, "COST_LOG", tmp_path / "cost_log.jsonl")
    (tmp_path / "audit_log.jsonl").touch()
    (tmp_path / "cost_log.jsonl").touch()

    results = runner.evaluate(_FakeSuite(), _FakeSuite.CASES, label="test", delay_seconds=0,
                              skip_ground_truth=False, scope_area=None)

    assert len(results) == 2
    by_id = {r["case"]["id"]: r for r in results}
    assert by_id["Q001"]["grade"]["passed_auto"] is True
    assert by_id["Q001"]["grade"]["ground_truth_check"] == "pass"
    assert by_id["Q002"]["grade"]["needs_human_review"] is True
    assert by_id["Q001"]["tools_called"] == ["get_revenue_by_channel"]
    assert by_id["Q001"]["cost_usd"] == pytest.approx(0.001)

    md = runner.render_markdown(results, "test")
    assert "Q002" not in md.split("## Câu chưa đạt tự động")[-1] if "## Câu chưa đạt" in md else True
    assert "Tổng số câu: 2" in md


def test_bang_3_nhom_khong_bao_gio_vuot_tong_so_cau():
    """Tai hien dung tinh huong tren may 24 18/08/2026: 31 'dat tu dong' + 65 'can doi chieu
    tay' in rieng cong lai ra 96 tren 90 cau - gay hieu nham vi 2 co nay DOC LAP, mot cau 'top N'
    khong dinh loi gi khac se dong thoi dung o CA HAI. Bang 3 nhom loai tru lan nhau phai LUON
    cong dung tong, du du lieu that nhieu bao nhieu cau."""
    gt_top_n = {"status": "ok", "rows": [[f"KH{i}", 1_000_000 * i] for i in range(1, 6)]}
    gt_gon_dung = {"status": "ok", "rows": [[39_327_016_119]]}
    gt_gon_sai = {"status": "ok", "rows": [[39_327_016_119]]}

    def _row(case_id, answer, gt):
        return {"case": {"id": case_id, "group": "G", "audience": "c_level", "question": "q"},
               "tools_called": ["t"], "error": None, "duration_seconds": 1.0, "cost_usd": 0.001,
               "grade": runner.grade_case(BASE_CASE, answer, None, ["t"], gt)}

    results = [
        _row("A", "39.327.016.119", gt_gon_dung),
        _row("B", "khong co so nao dung", gt_gon_sai),
        _row("C", "Top khach KH5...", gt_top_n),
    ]
    md = runner.render_markdown(results, "test")
    assert "| **Tổng** | **3** |" in md  # phai khop dung so cau, khong duoc la 4 hay hon


def test_selected_cases_loc_theo_nhom_va_gioi_han():
    args = SimpleNamespace(case=None, group="khách", audience=None, limit=None)
    selected = runner._selected_cases(_FakeSuite(), args)
    assert [c.id for c in selected] == ["Q002"]

    args2 = SimpleNamespace(case=None, group=None, audience=None, limit=1)
    selected2 = runner._selected_cases(_FakeSuite(), args2)
    assert len(selected2) == 1


# ---------------------------------------------------------------- ghi JSON (tai hien loi that 18/08)

def test_ghi_json_khong_vo_voi_decimal_va_date_tu_sql_server():
    """Tai hien DUNG loi that xay ra tren may 24 18/08/2026: chay that 90 cau, TON TIEN GOI
    CHATBOT THAT, roi vo o buoc ghi file cuoi cung vi ground_truth co decimal.Decimal (cot tien
    SQL Server) va datetime.date (cot ngay) - 2 kieu json chuan khong biet serialize. Phai KHONG
    duoc nem loi, va phai giu nguyen gia tri (khong quy tron sai) trong file ghi ra."""
    payload = {
        "label": "test", "total": 1,
        "results": [{
            "case": {"id": "Q037"}, "answer": "...",
            "ground_truth": {
                "status": "ok",
                "rows": [[decimal.Decimal("39327016119.00"), _dt.date(2026, 7, 31),
                         _dt.datetime(2026, 7, 31, 14, 9, 0)]],
            },
        }],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=runner._json_safe)
    restored = json.loads(text)
    row = restored["results"][0]["ground_truth"]["rows"][0]
    assert row[0] == "39327016119.00"  # giu nguyen chinh xac, KHONG quy tron thanh float
    assert row[1] == "2026-07-31"
    assert row[2] == "2026-07-31T14:09:00"


def test_dump_results_khong_bao_gio_mat_du_lieu_du_json_safe_bo_sot_kieu(tmp_path):
    """Neu trong tuong lai co checker tra ve mot kieu MOI ma _json_safe chua tung nghi toi,
    van khong duoc phep mat trang ca lan chay - phai co phuong an du phong."""
    class KieuLa:
        def __str__(self):
            return "kieu-la-nhung-van-doc-duoc"

    payload = {"label": "test", "results": [{"gia_tri": KieuLa()}]}
    out = tmp_path / "ket-qua.json"
    runner._dump_results_or_die_trying(payload, out)
    assert out.exists()
    restored = json.loads(out.read_text(encoding="utf-8"))
    assert "kieu-la" in restored["results"][0]["gia_tri"]


# ------------------------------------------- SQL tu do cung phai duoc tinh la tool (tai hien 18/08)

def test_audit_by_session_nhan_dien_ca_sql_tu_do_khong_chi_template(tmp_path, monkeypatch):
    """Tai hien DUNG hinh dang dong log that cua Q003 (run_query, khong co <template:>) va Q037
    (call_template, co <template:>) - ca hai deu phai duoc tinh la 'co goi tool'. Truoc ban va,
    48/49 cau dung SQL tu do bi cham oan 'khong_goi_tool' vi regex cu chi nhan <template:>."""
    log = tmp_path / "audit_log.jsonl"
    dong = [
        # Dung dinh dang that cua run_query() (query_engine.py) - SQL tho, co khoa "db"
        {"session_id": "s-adhoc", "sql": "WITH otc AS (SELECT doc_date, SUM(amount9) AS rev "
                                         "FROM vhoadon_otc WHERE doc_date...", "db": "local",
         "status": "ok"},
        # Dung dinh dang that cua call_template() (report_templates.py) - co tag <template:>
        {"session_id": "s-template", "sql": "<template:get_receivables_overview>({})",
         "status": "ok"},
        # SQL tu do nhung THAT BAI (bi tu choi/loi) - KHONG duoc tinh la da co tool chay
        {"session_id": "s-adhoc-loi", "sql": "SELECT * FROM x", "db": "local", "status": "rejected"},
    ]
    with io.open(log, "w", encoding="utf-8") as f:
        for d in dong:
            f.write(json.dumps(d) + "\n")
    monkeypatch.setattr(runner, "AUDIT_LOG", log)

    found = runner._audit_by_session({"s-adhoc", "s-template", "s-adhoc-loi"})

    assert found["s-adhoc"] == {"sql_tu_do:local"}
    assert found["s-template"] == {"get_receivables_overview"}
    assert found["s-adhoc-loi"] == set()  # that bai thi khong tinh


# ---------------------------------------------------------------- nap .env (tai hien loi that 18/08)

def test_load_env_nap_duoc_key_truoc_cau_dau_tien(tmp_path, monkeypatch):
    """Tai hien DUNG loi that: chay nhu script doc lap (khong qua backend/main.py) thi
    ANTHROPIC_API_KEY khong tu co trong os.environ - cau DAU TIEN se dinh '⚠️ Chua cau hinh API
    Key' oan uong, du key that su co san trong file .env, chi la chua duoc nap vao tien trinh."""
    for k in ("ANTHROPIC_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    (fake_backend / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-test-tu-file-env\n", encoding="utf-8")
    monkeypatch.setattr(runner, "BACKEND", fake_backend)
    monkeypatch.setattr(runner, "ROOT", tmp_path)

    assert os.environ.get("ANTHROPIC_API_KEY") is None  # dung nhu tien trinh moi khoi dong

    runner._load_env_before_first_call()

    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-tu-file-env"


def test_load_env_khong_ghi_de_key_da_co_san(tmp_path, monkeypatch):
    """setdefault, khong phai gan thang: neu tien trinh DA co key that (vd dat qua $env: truoc
    khi chay script), file .env khong duoc phep ghi de len."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-da-dat-tu-truoc")
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    (fake_backend / ".env").write_text("ANTHROPIC_API_KEY=key-trong-file\n", encoding="utf-8")
    monkeypatch.setattr(runner, "BACKEND", fake_backend)
    monkeypatch.setattr(runner, "ROOT", tmp_path)

    runner._load_env_before_first_call()

    assert os.environ.get("ANTHROPIC_API_KEY") == "key-da-dat-tu-truoc"


def test_dry_run_khong_goi_ask_khong_ghi_log(tmp_path, monkeypatch, capsys):
    """CLI --dry-run phai an toan chay tren may khong co API key/SQL Server."""
    import nl2sql

    def boom(*a, **kw):
        raise AssertionError("dry-run KHONG duoc goi nl2sql.ask()")

    monkeypatch.setattr(nl2sql, "ask", boom)
    monkeypatch.setattr(sys, "argv", ["run_business_evaluation.py", "--dry-run", "--group", "Doanh thu"])
    monkeypatch.setattr(runner, "_load_module", lambda name, path: _FakeSuite())

    rc = runner.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out.lower()
