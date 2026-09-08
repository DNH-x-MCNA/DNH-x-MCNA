"""Khoa cac chot chan cua runner 138 cau de khong tao hang loat loi gia."""

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "run_bo_138_cau.py"


def _load_runner(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-used")
    monkeypatch.setitem(sys.modules, "nl2sql", types.SimpleNamespace())
    spec = importlib.util.spec_from_file_location("run_bo_138_cau_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_het_credit_phai_dung_ngay(monkeypatch):
    runner = _load_runner(monkeypatch)

    marker = runner.loi_provider_can_dung(
        "BadRequestError: Your credit balance is too low to access the Anthropic API."
    )

    assert marker == "credit balance is too low"


def test_loi_nghiep_vu_mot_cau_khong_lam_dung_ca_vong(monkeypatch):
    runner = _load_runner(monkeypatch)

    assert runner.loi_provider_can_dung("OperationalError: no such column: x") is None
