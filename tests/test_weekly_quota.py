"""21/08/2026: han muc cau hoi/tuan theo vai tro (QLV 30, TP 60, C-level 120), reset thu Hai -
chinh sach chot voi DNH de khong vuot ngan sach API 300 USD/thang (xem docs trao doi chi phi)."""
import datetime as dt
import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import auth  # noqa: E402

# 21/08/2026: KHONG dung "import main" thang - trung ten voi main.py o goc repo (pipeline alert/
# report), va test_phase1_phase2.py da "from main import send_daily_digest" truoc do trong cung
# phien pytest -> sys.modules['main'] bi chiem truoc, "import main" o day se lay NHAM module goc,
# AttributeError o WEEKLY_QUESTION_LIMITS (xac nhan thuc te khi chay full suite). Nap qua
# importlib voi ten rieng, giong _load() da dung trong test_complex_evaluation.py.
_import_tmp_db = tempfile.mktemp(suffix=".db")
auth.DB_PATH = _import_tmp_db
_spec = importlib.util.spec_from_file_location("dnh_backend_main", BACKEND / "main.py")
chatbot_main = importlib.util.module_from_spec(_spec)
sys.modules["dnh_backend_main"] = chatbot_main
_spec.loader.exec_module(chatbot_main)


def _fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    auth.init_schema()


def _create(username, role="qlv"):
    auth.create_user(username=username, password="temp-pass-1234", name=username, role=role)


# ---------- auth.check_and_consume_weekly_quota: logic loi ----------

def test_khong_gioi_han_khi_limit_none_hoac_0(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    _create("khong_gioi_han")
    for limit in (None, 0):
        result = auth.check_and_consume_weekly_quota("khong_gioi_han", limit)
        assert result["allowed"] is True
        assert result["limit"] is None


def test_cho_phep_dung_bang_limit_roi_chan_cau_tiep_theo(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    _create("qlv_test", role="qlv")
    limit = 3
    for i in range(1, limit + 1):
        result = auth.check_and_consume_weekly_quota("qlv_test", limit)
        assert result["allowed"] is True, f"cau thu {i} phai duoc phep"
        assert result["used"] == i

    blocked = auth.check_and_consume_weekly_quota("qlv_test", limit)
    assert blocked["allowed"] is False
    assert blocked["used"] == limit
    assert blocked["limit"] == limit


def test_bi_chan_khong_lam_dem_tang_qua_limit(monkeypatch, tmp_path):
    """Goi lai nhieu lan sau khi da bi chan khong duoc lam 'used' vuot qua limit that."""
    _fresh_db(monkeypatch, tmp_path)
    _create("qlv_lap", role="qlv")
    limit = 2
    for _ in range(limit):
        auth.check_and_consume_weekly_quota("qlv_lap", limit)
    for _ in range(5):
        result = auth.check_and_consume_weekly_quota("qlv_lap", limit)
        assert result["allowed"] is False
        assert result["used"] == limit


def test_reset_khi_sang_tuan_moi(monkeypatch, tmp_path):
    """Da dung het quota tuan truoc -> sang tuan nay phai duoc cap lai tu dau."""
    _fresh_db(monkeypatch, tmp_path)
    _create("qlv_tuan", role="qlv")
    limit = 2

    # Gia lap da dung het quota va reset_at ghi nhan tu 2 tuan truoc.
    two_weeks_ago = dt.datetime.now() - dt.timedelta(days=14)
    conn = auth.get_conn()
    try:
        conn.execute(
            "UPDATE users SET weekly_question_count=?, weekly_reset_at=? WHERE username=?",
            (limit, two_weeks_ago.isoformat(), "qlv_tuan"),
        )
        conn.commit()
    finally:
        conn.close()

    result = auth.check_and_consume_weekly_quota("qlv_tuan", limit)
    assert result["allowed"] is True
    assert result["used"] == 1, "phai reset ve 0 roi tinh cau nay la cau dau tien"


def test_resets_at_luon_la_00h_thu_hai_ke_tiep(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    _create("qlv_resetat", role="qlv")
    result = auth.check_and_consume_weekly_quota("qlv_resetat", 10)
    resets_at = dt.datetime.fromisoformat(result["resets_at"])
    assert resets_at.weekday() == 0  # Thu Hai
    assert (resets_at.hour, resets_at.minute, resets_at.second) == (0, 0, 0)
    assert resets_at > dt.datetime.now()


def test_username_khong_ton_tai_fail_open(monkeypatch, tmp_path):
    """Tai khoan khong co trong bang users (truong hop du phong) - khong chan chat vi ly do khac."""
    _fresh_db(monkeypatch, tmp_path)
    result = auth.check_and_consume_weekly_quota("khong_ton_tai_bao_gio", 5)
    assert result["allowed"] is True


# ---------- backend/main.py: noi day WEEKLY_QUESTION_LIMITS + _check_weekly_quota ----------

def test_han_muc_dung_3_vai_tro_da_chot():
    assert chatbot_main.WEEKLY_QUESTION_LIMITS == {
        "qlv": 30,
        "regional_director": 60,
        "c_level": 120,
    }


def test_check_weekly_quota_khong_chan_khi_con_han_muc(monkeypatch):
    monkeypatch.setattr(
        chatbot_main, "check_and_consume_weekly_quota",
        lambda username, limit: {"allowed": True, "used": 5, "limit": 30, "resets_at": "2026-08-24T00:00:00"},
    )
    chatbot_main._check_weekly_quota({"username": "qlv_bac", "role": "qlv"})  # khong duoc nem loi


def test_check_weekly_quota_chan_va_bao_dung_gio_reset(monkeypatch):
    monkeypatch.setattr(
        chatbot_main, "check_and_consume_weekly_quota",
        lambda username, limit: {"allowed": False, "used": 30, "limit": 30, "resets_at": "2026-08-24T00:00:00"},
    )
    with pytest.raises(chatbot_main.HTTPException) as exc_info:
        chatbot_main._check_weekly_quota({"username": "qlv_bac", "role": "qlv"})
    assert exc_info.value.status_code == 429
    assert "30" in exc_info.value.detail
    assert "24/08" in exc_info.value.detail
