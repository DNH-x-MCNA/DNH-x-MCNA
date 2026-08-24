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


# ---------- auth.get_weekly_quota_status: CHI DOC, khong tang dem (dung cho UI/badge) ----------

def test_doc_trang_thai_khong_lam_tang_dem(monkeypatch, tmp_path):
    """Goi get_weekly_quota_status() nhieu lan lien tiep KHONG duoc lam used tang len - khac han
    check_and_consume_weekly_quota() (moi vai tro ho tro chatbot mo trang la mat 1 luot oan)."""
    _fresh_db(monkeypatch, tmp_path)
    _create("qlv_doc", role="qlv")
    auth.check_and_consume_weekly_quota("qlv_doc", 10)  # dung that 1 cau -> used=1

    for _ in range(5):
        status = auth.get_weekly_quota_status("qlv_doc", 10)
        assert status["used"] == 1
        assert status["remaining"] == 9
        assert status["limit"] == 10


def test_doc_trang_thai_tinh_dung_reset_tuan_moi_ma_khong_ghi_db(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    _create("qlv_doc2", role="qlv")
    two_weeks_ago = dt.datetime.now() - dt.timedelta(days=14)
    conn = auth.get_conn()
    try:
        conn.execute(
            "UPDATE users SET weekly_question_count=?, weekly_reset_at=? WHERE username=?",
            (10, two_weeks_ago.isoformat(), "qlv_doc2"),
        )
        conn.commit()
    finally:
        conn.close()

    status = auth.get_weekly_quota_status("qlv_doc2", 10)
    assert status["used"] == 0
    assert status["remaining"] == 10

    # Xac nhan KHONG ghi gi xuong DB (chi doc) - dong ho tuan truoc van con nguyen trong bang.
    conn = auth.get_conn()
    try:
        row = conn.execute("SELECT weekly_question_count FROM users WHERE username=?", ("qlv_doc2",)).fetchone()
    finally:
        conn.close()
    assert row[0] == 10


def test_doc_trang_thai_khong_gioi_han(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    _create("clevel_doc", role="c_level")
    status = auth.get_weekly_quota_status("clevel_doc", None)
    assert status == {"used": 0, "limit": None, "remaining": None, "resets_at": None}


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
    quota = chatbot_main._check_weekly_quota({"username": "qlv_bac", "role": "qlv"})  # khong duoc nem loi
    assert quota == {
        "quota_used": 5, "quota_limit": 30, "quota_remaining": 25,
        "quota_resets_at": "2026-08-24T00:00:00",
    }


def test_quota_status_for_chi_doc_dung_ham_khong_tang_dem(monkeypatch):
    """_quota_status_for (dung cho /auth/login, /auth/me) phai goi get_weekly_quota_status - KHONG
    duoc goi nham check_and_consume_weekly_quota (se lam hut mat 1 luot moi lan mo trang)."""
    monkeypatch.setattr(
        chatbot_main, "get_weekly_quota_status",
        lambda username, limit: {"used": 12, "limit": 30, "remaining": 18, "resets_at": "2026-08-24T00:00:00"},
    )
    monkeypatch.setattr(
        chatbot_main, "check_and_consume_weekly_quota",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("khong duoc goi ham tang dem o day")),
    )
    quota = chatbot_main._quota_status_for({"username": "qlv_bac", "role": "qlv"})
    assert quota == {
        "quota_used": 12, "quota_limit": 30, "quota_remaining": 18,
        "quota_resets_at": "2026-08-24T00:00:00",
    }


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


# ---------- _quota_for_question: cau hoi bi chan mien phi (du bao) KHONG duoc tru quota ----------

def test_cau_hoi_du_bao_khong_tru_quota(monkeypatch):
    """24/08/2026: is_future_forecast_question() chan cau hoi NGAY DAU ask() truoc khi goi model -
    khong ton dong nao. Tru quota cho cau nay la khong cong bang (phat hien tu phan hoi thuc te cua
    user: hoi "du bao doanh thu thang 8" bi tu choi nhung van bi tinh vao han muc tuan)."""
    monkeypatch.setattr(
        chatbot_main, "check_and_consume_weekly_quota",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cau hoi mien phi khong duoc goi ham tang dem")),
    )
    monkeypatch.setattr(
        chatbot_main, "get_weekly_quota_status",
        lambda username, limit: {"used": 5, "limit": 30, "remaining": 25, "resets_at": "2026-08-31T00:00:00"},
    )
    quota = chatbot_main._quota_for_question(
        {"username": "qlv_bac", "role": "qlv"}, "Dự báo doanh thu tháng 8 là bao nhiêu?"
    )
    assert quota == {
        "quota_used": 5, "quota_limit": 30, "quota_remaining": 25,
        "quota_resets_at": "2026-08-31T00:00:00",
    }


def test_cau_hoi_binh_thuong_van_tru_quota_nhu_cu(monkeypatch):
    monkeypatch.setattr(
        chatbot_main, "check_and_consume_weekly_quota",
        lambda username, limit: {"allowed": True, "used": 6, "limit": 30, "resets_at": "2026-08-31T00:00:00"},
    )
    quota = chatbot_main._quota_for_question(
        {"username": "qlv_bac", "role": "qlv"}, "Doanh thu tháng 7 theo vùng là bao nhiêu?"
    )
    assert quota["quota_used"] == 6


def test_cau_hoi_du_bao_van_duoc_tra_loi_du_da_het_quota(monkeypatch):
    """Cau hoi mien phi PHAI luot qua ca gate 429 - het quota van tra loi tu choi du bao binh
    thuong, khong bi chan vi ly do khac (het luot)."""
    monkeypatch.setattr(
        chatbot_main, "check_and_consume_weekly_quota",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("khong duoc goi - se bi chan 429 oan")),
    )
    monkeypatch.setattr(
        chatbot_main, "get_weekly_quota_status",
        lambda username, limit: {"used": 30, "limit": 30, "remaining": 0, "resets_at": "2026-08-31T00:00:00"},
    )
    quota = chatbot_main._quota_for_question(
        {"username": "qlv_bac", "role": "qlv"}, "Xu hướng doanh số sắp tới ra sao?"
    )
    assert quota["quota_remaining"] == 0
