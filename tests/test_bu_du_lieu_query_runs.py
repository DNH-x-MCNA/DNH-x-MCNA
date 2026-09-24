"""scripts/bu_du_lieu_query_runs.py: chi sua dung hai loai dong ghi sai, khong dong vao dong khac."""
import importlib.util
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.insert(0, str(GOC / "backend"))

import conversation_memory as memory  # noqa: E402

_spec = importlib.util.spec_from_file_location("bu_du_lieu_qr", GOC / "scripts" / "bu_du_lieu_query_runs.py")
bu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bu)


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    conn = sqlite3.connect(memory.DB_PATH)

    def them(qid, status, duration_ms, error_message, created_at, completed_at):
        conn.execute(
            "INSERT INTO query_runs (query_id, session_id, username, question, status, duration_ms, "
            "error_message, created_at, completed_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (qid, "s-" + qid, "u", "cau hoi", status, duration_ms, error_message, created_at, completed_at))
    # Het credit that (Anthropic 400) bi ghi 'error' - phai doi.
    them("credit", "error", 4200, "Error code: 400 - {'error': {'message': 'Your credit balance is too low'}}",
         "2026-09-20T02:00:00+00:00", "2026-09-20T02:00:04+00:00")
    # Loi thuong - KHONG duoc doi.
    them("loi", "error", 900, "SQL timeout", "2026-09-20T03:00:00+00:00", "2026-09-20T03:00:01+00:00")
    # #81: abandoned, duration = luc don - luc tao (3 ngay) - phai ve NULL.
    them("doan", "abandoned", 259_200_000, "Luot truy van dung ma khong co ket qua cuoi",
         "2026-09-17T08:00:00+00:00", "2026-09-20T08:00:00+00:00")
    # abandoned nhung duration la so do that truoc do (#83 giu nguyen) - KHONG duoc xoa.
    them("do_that", "abandoned", 31_000, "Luot truy van dung ma khong co ket qua cuoi",
         "2026-09-17T08:00:00+00:00", "2026-09-20T08:00:00+00:00")
    # Hoan thanh binh thuong - khong dong vao.
    them("ok", "completed", 33_900, None, "2026-09-20T04:00:00.123456+00:00", "2026-09-20T04:00:34.023456+00:00")
    conn.commit()
    return conn


def _dong(conn, qid):
    return conn.execute("SELECT status, duration_ms, error_message FROM query_runs WHERE query_id=?",
                        (qid,)).fetchone()


def test_xem_truoc_nhan_dung_hai_loai_va_khong_sua(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    credit, bo_do = bu.tim_dong(conn)
    assert [r["query_id"] for r in credit] == ["credit"]
    assert [r["query_id"] for r in bo_do] == ["doan"]
    conn.row_factory = None
    assert _dong(conn, "credit")[0] == "error", "Xem truoc khong duoc sua."


def test_ghi_chi_sua_dung_dong_va_giu_nguyen_phan_con_lai(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    assert bu.ghi(conn) == (1, 1)
    conn.row_factory = None
    st, dur, msg = _dong(conn, "credit")
    assert st == "api_credit_exhausted" and dur == 4200 and "credit balance" in msg
    assert _dong(conn, "loi")[0] == "error"
    assert _dong(conn, "doan")[:2] == ("abandoned", None)
    assert _dong(conn, "do_that")[1] == 31_000, "So do that cua luot abandoned phai giu nguyen."
    assert _dong(conn, "ok")[:2] == ("completed", 33_900)


def test_chay_lai_khong_sua_them(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    bu.ghi(conn)
    assert bu.ghi(conn) == (0, 0)
    assert bu.tim_dong(conn) == ([], [])
