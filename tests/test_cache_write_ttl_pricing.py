# -*- coding: utf-8 -*-
"""25/08/2026: tach don gia GHI CACHE theo TTL (5 phut = 1.25x input, 1 gio = 2x input).

Boi canh: nguoi dung doi chieu dashboard noi bo voi Anthropic Console va thay noi bo cao hon.
Truy nguyen:
  - Cong thuc KHONG sai: tinh lai tu token tho tren 89 dong log that cua may 24 khop tuyet doi
    cost_usd da ghi (0/89 dong lech).
  - Nguyen nhan CHINH la so sanh lech mui gio: dashboard chia ngay theo gio Viet Nam
    (cost_logger.py dung datetime.now()), Console chia theo UTC - lech 7 tieng, khong so truc tiep
    tung ngay duoc.
  - Nguyen nhan PHU, co that: nl2sql.py dung 4 breakpoint cache voi HAI TTL khac nhau (system
    prompt + tool definitions = 1 gio; tool_results + lich su hoi thoai = 5 phut) nhung bang gia
    chi co MOT don gia cache_write nen phan 5 phut bi tinh theo gia 1 gio. Do tren 89 dong that:
    thoi phong toi da 1,13 lan.
"""
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# APPEND, khong insert(0) - xem ghi chu trong test_cost_repricing.py.
_BACKEND = str(ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.append(_BACKEND)

from pricing import MODEL_PRICING, compute_cost_usd


def test_khong_truyen_phan_tach_thi_giu_nguyen_hanh_vi_cu():
    """Dong log CU (chi co mot con so cache_write) phai tinh y het truoc khi sua - neu khong, moi
    bao cao lich su se doi so mot cach am tham. Con so ky vong lay tu dong log THAT cua may 24."""
    cost = compute_cost_usd("claude-sonnet-5", 2, 171, 36817, 3957)
    assert round(cost, 6) == 0.024905


def test_ghi_cache_5_phut_re_hon_ghi_1_gio():
    chung = ("claude-sonnet-5", 2, 171, 36817, 3957)
    tat_ca_1h = compute_cost_usd(*chung)
    tat_ca_5m = compute_cost_usd(*chung, cache_write_5m_tokens=3957)
    assert tat_ca_5m < tat_ca_1h
    # Chenh lech dung bang phan ghi cache doi tu 4.00 xuong 2.50 (khong dung == tuyet doi: hieu cua
    # hai so lon tich luy sai so dau phay dong toi ~1e-6).
    assert tat_ca_1h - tat_ca_5m == pytest.approx(3957 / 1_000_000 * (4.00 - 2.50), abs=1e-9)


def test_tach_mot_nua_thi_tinh_dung_ca_hai_don_gia():
    cost = compute_cost_usd("claude-sonnet-5", 0, 0, 0, 1000, cache_write_5m_tokens=400)
    assert round(cost, 6) == round((400 * 2.50 + 600 * 4.00) / 1_000_000, 6)


def test_ap_dung_cho_moi_model_claude_khong_chi_sonnet():
    """Truoc 25/08 haiku va opus dat NHAM he so 1.25x (gia TTL 5 phut) vao o gia TTL 1 gio - tuc 2
    model do dang tinh theo quy uoc nguoc voi sonnet-5. Khoa lai ca ba cho khong lech nhau nua."""
    for model in ("claude-sonnet-5", "claude-haiku-4-5", "claude-opus-4-8"):
        p = MODEL_PRICING[model]
        assert p["cache_write"] == p["input"] * 2, f"{model}: gia TTL 1 gio phai la 2x input"
        assert p["cache_write_5m"] == p["input"] * 1.25, f"{model}: gia TTL 5 phut phai la 1.25x input"


def test_du_lieu_bat_thuong_khong_lam_am_tien():
    """API tra ve khong nhat quan (phan 5 phut > tong, hoac am) khong duoc lam phan 1 gio thanh am."""
    chung = ("claude-sonnet-5", 2, 171, 36817, 3957)
    tat_ca_5m = compute_cost_usd(*chung, cache_write_5m_tokens=3957)
    assert compute_cost_usd(*chung, cache_write_5m_tokens=999_999) == tat_ca_5m
    assert compute_cost_usd(*chung, cache_write_5m_tokens=-5) == compute_cost_usd(*chung)


def test_model_khong_co_gia_5_phut_van_chay_duoc():
    """DeepSeek khong tinh rieng cache write (cache_write=0.0, khong co cache_write_5m) - truyen
    phan tach vao khong duoc lam vo ham."""
    cost = compute_cost_usd("deepseek-v4-pro", 1000, 1000, 1000, 1000, cache_write_5m_tokens=500)
    assert cost >= 0


def test_cost_logger_doc_duoc_hai_truong_ttl_cua_sdk(monkeypatch, tmp_path):
    """anthropic SDK 0.116.0 tra ve usage.cache_creation.ephemeral_5m_input_tokens /
    .ephemeral_1h_input_tokens - da kiem chung 25/08/2026 (pricing.py truoc do ghi "chua kiem chung
    duoc"). Test dung object gia dung hinh dang do."""
    import cost_logger

    class _CacheCreation:
        ephemeral_5m_input_tokens = 3000
        ephemeral_1h_input_tokens = 957

    class _Usage:
        input_tokens = 2
        output_tokens = 171
        cache_read_input_tokens = 36817
        cache_creation_input_tokens = 3957
        cache_creation = _CacheCreation()

    monkeypatch.setattr(cost_logger, "LOG_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setattr(cost_logger, "_check_monthly_budget", lambda: None)
    cost = cost_logger.compute_and_log_cost(_Usage(), "claude-sonnet-5")

    mong_doi = compute_cost_usd("claude-sonnet-5", 2, 171, 36817, 3957, cache_write_5m_tokens=3000)
    assert round(cost, 6) == round(mong_doi, 6)

    import json
    entry = json.loads((tmp_path / "cost.jsonl").read_text(encoding="utf-8").strip())
    assert entry["cache_write_5m_tokens"] == 3000
    assert entry["cache_write_1h_tokens"] == 957


def test_cost_logger_van_chay_khi_sdk_khong_co_cache_creation(monkeypatch, tmp_path):
    """Nha cung cap khac / SDK cu khong co truong nay - phai giu nguyen cach tinh cu, khong vo."""
    import cost_logger

    class _Usage:
        input_tokens = 2
        output_tokens = 171
        cache_read_input_tokens = 36817
        cache_creation_input_tokens = 3957

    monkeypatch.setattr(cost_logger, "LOG_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setattr(cost_logger, "_check_monthly_budget", lambda: None)
    cost = cost_logger.compute_and_log_cost(_Usage(), "claude-sonnet-5")
    assert round(cost, 6) == 0.024905
