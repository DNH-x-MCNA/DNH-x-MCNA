import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# APPEND, khong insert(0): backend/ co main.py rieng, day len dau se che mat main.py o goc repo
# va lam tests/test_phase1_phase2.py vo ngay luc thu thap ("cannot import name send_daily_digest
# from main"). Da dinh dung loi nay 1 lan (test_forecast_va_scope.py, 12/08/2026) - tai dien vi
# file moi lai insert(0) rieng thay vi dung path da co san.
_BACKEND = str(ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.append(_BACKEND)

from cost_repricing import reprice_entry, reprice_jsonl


def test_deepseek_v4_pro_uses_official_price_and_keeps_original_cost():
    original = {
        "model": "deepseek-v4-pro", "input_tokens": 1_000_000,
        "output_tokens": 1_000_000, "cache_read_tokens": 1_000_000,
        "cache_write_tokens": 999, "cost_usd": 5.324,
    }
    updated, changed = reprice_entry(original)

    assert changed is True
    assert updated["cost_usd"] == 1.308625
    assert updated["cost_usd_before_reprice"] == 5.324
    assert updated["pricing_version"] == "deepseek-official-2026-08-18"


def test_repricing_is_dry_run_until_apply_and_preserves_other_models(tmp_path):
    path = tmp_path / "cost_log.jsonl"
    rows = [
        {"model": "deepseek-v4-flash", "input_tokens": 1_000_000,
         "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.44},
        {"model": "claude-sonnet-5", "input_tokens": 10, "output_tokens": 20, "cost_usd": 0.01},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    preview = reprice_jsonl(path)
    assert preview["changed"] == 1
    assert preview["applied"] is False
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["cost_usd"] == 0.44

    applied = reprice_jsonl(path, apply=True)
    rewritten = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert applied["applied"] is True
    assert Path(applied["backup_path"]).is_file()
    assert rewritten[0]["cost_usd"] == 0.14
    assert rewritten[1] == rows[1]
