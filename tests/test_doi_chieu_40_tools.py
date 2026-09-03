"""Khoa danh sach smoke/contract de tool moi khong bi bo quen khoi doi chieu."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "doi_chieu_so_lieu_tool_moi.py"
SPEC = importlib.util.spec_from_file_location("doi_chieu_so_lieu_tool_moi", MODULE_PATH)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_catalog_smoke_phu_dung_toan_bo_tool_da_dang_ky():
    cases = checker._tool_cases_40()

    assert len(cases) == 40
    assert set(cases) == set(checker.rt.TEMPLATES)


def test_payload_rong_khong_duoc_tinh_la_da_kiem():
    assert checker._ly_do_khong_co_payload([]) == "danh sach rong"
    assert checker._ly_do_khong_co_payload({"warning": "khong co du lieu"}) is not None
    assert checker._ly_do_khong_co_payload({"error": "loi truy van"}) == "loi truy van"


def test_payload_co_du_lieu_hoac_moc_snapshot_duoc_chap_nhan():
    assert checker._ly_do_khong_co_payload([{"value": 1}]) is None
    assert checker._ly_do_khong_co_payload({"total": 12}) is None
    assert checker._ly_do_khong_co_payload({"total": 0, "snapshot_date": "2026-08-31"}) is None
