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


def test_khong_goi_tool_nao_la_P0():
    r = runner.grade_case(BASE_CASE, "Doanh thu tháng 7 khoảng 39 tỷ.", None, [],
                          {"status": "bo_qua"})
    assert r["passed_auto"] is False
    assert any(p["code"] == "khong_goi_tool" for p in r["problems"])


def test_checker_gon_du_so_thi_dat():
    gt = {"status": "ok", "rows": [[39_327_016_119, 35_508_451_204]]}
    answer = "OTC: 39.327.016.119 đ, ETC: 35.508.451.204 đ"
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is True
    assert r["ground_truth_check"] == "pass"
    assert r["needs_human_review"] is False


def test_checker_gon_thieu_so_thi_sai_so_lieu():
    gt = {"status": "ok", "rows": [[39_327_016_119, 35_508_451_204]]}
    answer = "OTC: 39.327.016.119 đ, ETC: khoảng 35 tỷ"  # thieu so ETC chinh xac
    r = runner.grade_case(BASE_CASE, answer, None, ["get_revenue_by_channel"], gt)
    assert r["passed_auto"] is False
    assert r["ground_truth_check"] == "fail"
    assert any(p["code"] == "sai_so_lieu" for p in r["problems"])


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
