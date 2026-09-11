"""Cam business-eval (11/09/2026) va khoa phan doc nhat ky da tach ra truoc khi go.

Ngay 10/09/2026 luc 15-16h, business-eval chay 235 luot goi model (7,08 USD) trong luc khong ai
dieu phoi. Chu du an quyet dinh cam han va go bo. Test nay chan viec dua no tro lai.
"""

import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _nap(ten, duong):
    spec = importlib.util.spec_from_file_location(ten, duong)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runner_business_eval_da_bi_go():
    assert not (ROOT / "scripts" / "run_business_evaluation.py").exists()


def test_khong_con_code_goi_chatbot_voi_ten_business_eval():
    tracked = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    loi = []
    for p in tracked:
        if p.startswith("tests/"):
            continue
        noi_dung = (ROOT / p).read_text(encoding="utf-8", errors="replace")
        if re.search(r"""username\s*=\s*["']business-eval["']""", noi_dung):
            loi.append(p)
    assert loi == [], "Van con code goi chatbot duoi ten business-eval: %s" % loi


def test_hai_runner_con_lai_nap_nhat_ky_tu_module_moi():
    for ten in ("run_bo_138_cau.py", "run_tool_routing_sample.py"):
        nguon = (ROOT / "scripts" / ten).read_text(encoding="utf-8")
        assert "nhat_ky_eval.py" in nguon, ten
        assert "run_business_evaluation.py\")" not in nguon, ten


def test_runner_138_nap_duoc_helper_ma_khong_goi_model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-used")
    monkeypatch.setitem(sys.modules, "nl2sql", types.SimpleNamespace())
    runner = _nap("run_bo_138_cau_cam_beval", ROOT / "scripts" / "run_bo_138_cau.py")
    helpers = runner._load_eval_helpers()
    assert hasattr(helpers, "_audit_by_session") and hasattr(helpers, "_cost_by_session")


def test_doc_nhat_ky_theo_session(tmp_path):
    mod = _nap("nhat_ky_eval_test", ROOT / "scripts" / "nhat_ky_eval.py")
    audit = tmp_path / "audit_log.jsonl"
    cost = tmp_path / "cost_log.jsonl"
    audit.write_text("\n".join([
        json.dumps({"session_id": "a", "sql": "<template:get_top_products>(...)"}),
        json.dumps({"session_id": "a", "sql": "SELECT 1", "db": "local", "status": "ok"}),
        json.dumps({"session_id": "a", "sql": "SELECT 2", "db": "local", "status": "error"}),
        json.dumps({"session_id": "khac", "sql": "<template:get_kpi_ranking>(...)"}),
        "dong hong khong phai json",
    ]), encoding="utf-8")
    cost.write_text("\n".join([
        json.dumps({"session_id": "a", "cost_usd": 0.25}),
        json.dumps({"session_id": "a", "cost_usd": 0.5}),
        json.dumps({"session_id": "khac", "cost_usd": 9}),
    ]), encoding="utf-8")
    mod.AUDIT_LOG, mod.COST_LOG = audit, cost

    # SQL tu do chi tinh khi chay thanh cong; session ngoai danh sach khong lan vao.
    assert mod._audit_by_session({"a"}) == {"a": {"get_top_products", "sql_tu_do:local"}}
    assert mod._cost_by_session({"a", "khong_co"}) == {"a": 0.75, "khong_co": 0.0}


def test_khong_co_file_log_thi_tra_rong_khong_loi(tmp_path):
    mod = _nap("nhat_ky_eval_rong", ROOT / "scripts" / "nhat_ky_eval.py")
    mod.AUDIT_LOG, mod.COST_LOG = tmp_path / "khong.jsonl", tmp_path / "khong2.jsonl"
    assert mod._audit_by_session({"x"}) == {"x": set()}
    assert mod._cost_by_session({"x"}) == {"x": 0.0}
