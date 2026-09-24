"""Bu hai loai dong query_runs ghi sai tren may 24 - MAC DINH CHI XEM TRUOC, phai co --ghi.

    python scripts/bu_du_lieu_query_runs.py          # xem truoc, khong sua gi
    python scripts/bu_du_lieu_query_runs.py --ghi    # sao luu memory.db ra TEMP roi sua

Khong goi model. Chi sua memory.db (bang query_runs), trong mot giao dich.

1. Het han muc API bi ghi la "error". Truoc khi co ApiCreditExhaustedError (nl2sql.py), luot bi Anthropic
   tu choi vi het credit rot vao `except Exception` -> status 'error'. Dashboard hien "Loi" nhu the cau
   hoi sai. Do tren may 24: 14 dong. Nhan dien bang CUNG bo dau hieu voi nl2sql._is_api_credit_error va
   health_watchdog; chi doi status, giu nguyen error_message va duration_ms.

2. Luot abandoned mang thoi luong doan. PR #81 dong luot 'running' khi khoi dong va ghi duration_ms =
   luc don - luc tao (co the nhieu ngay). PR #83 da sua cho cac luot ve sau (de NULL) nhung khong viet
   lai 5 dong da bi #81 ghi. Nhan dien: status 'abandoned' va duration_ms xap xi (completed_at -
   created_at) - dung dau vet cua #81. Dua ve NULL, khong doan so khac.
"""
import argparse
import os
import sqlite3
import sys
import tempfile
from datetime import datetime

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import conversation_memory  # noqa: E402

# Cung bo dau hieu voi nl2sql._is_api_credit_error.
DAU_HIEU_HET_CREDIT = ("credit balance is too low", "credit balance too low", "credit_balance",
                       "insufficient_credit", "insufficient credit")
# Sai so cho phep giua duration_ms va (completed_at - created_at): #81 tinh ca hai tu cung mot "now".
SAI_SO_MS = 5000

_DIEU_KIEN_CREDIT = ("status='error' AND (" + " OR ".join(
    "LOWER(COALESCE(error_message,'')) LIKE ?" for _ in DAU_HIEU_HET_CREDIT) + ")")
_THAM_SO_CREDIT = tuple("%" + d + "%" for d in DAU_HIEU_HET_CREDIT)
_DIEU_KIEN_BO_DO = ("status='abandoned' AND duration_ms IS NOT NULL AND completed_at IS NOT NULL "
                    "AND ABS(duration_ms - (julianday(completed_at) - julianday(created_at)) * 86400000.0) <= ?")


def tim_dong(conn):
    """Tra ve (dong_het_credit, dong_abandoned_doan) - moi dong la dict."""
    conn.row_factory = sqlite3.Row
    cot = "query_id, username, session_id, created_at, completed_at, status, duration_ms, error_message"
    credit = [dict(r) for r in conn.execute(
        f"SELECT {cot} FROM query_runs WHERE {_DIEU_KIEN_CREDIT} ORDER BY created_at", _THAM_SO_CREDIT)]
    bo_do = [dict(r) for r in conn.execute(
        f"SELECT {cot} FROM query_runs WHERE {_DIEU_KIEN_BO_DO} ORDER BY created_at", (SAI_SO_MS,))]
    return credit, bo_do


def ghi(conn):
    """Sua trong mot giao dich. Tra ve (so_dong_credit, so_dong_abandoned)."""
    with conn:
        n1 = conn.execute(f"UPDATE query_runs SET status='api_credit_exhausted' WHERE {_DIEU_KIEN_CREDIT}",
                          _THAM_SO_CREDIT).rowcount
        n2 = conn.execute(f"UPDATE query_runs SET duration_ms=NULL WHERE {_DIEU_KIEN_BO_DO}",
                          (SAI_SO_MS,)).rowcount
    return n1, n2


def _sao_luu(db_path):
    dich = os.path.join(tempfile.gettempdir(),
                        "memory_truoc_bu_%s.db" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    nguon = sqlite3.connect(db_path, timeout=30)
    dst = sqlite3.connect(dich)
    try:
        nguon.backup(dst)
    finally:
        dst.close()
        nguon.close()
    return dich


def _in(tieu_de, dong):
    print("%s: %d dong" % (tieu_de, len(dong)))
    for r in dong:
        print("  %s  %-16s %-8s dur=%-10s %s" % (
            (r["created_at"] or "")[:19], r["username"], r["status"], r["duration_ms"],
            (r["error_message"] or "")[:70].replace("\n", " ")))


def main():
    ap = argparse.ArgumentParser(description="Bu dong query_runs ghi sai (het credit, abandoned doan gio)")
    ap.add_argument("--ghi", action="store_true", help="Thuc su sua. Khong co co nay thi chi xem truoc.")
    ap.add_argument("--db", default=conversation_memory.DB_PATH, help="Duong dan memory.db")
    tham = ap.parse_args()

    if not os.path.isfile(tham.db):
        sys.exit("Khong thay %s" % tham.db)
    conn = sqlite3.connect(tham.db, timeout=30)
    try:
        credit, bo_do = tim_dong(conn)
        _in("1. Het han muc API dang ghi 'error' -> se doi thanh 'api_credit_exhausted'", credit)
        print()
        _in("2. Abandoned mang thoi luong doan cua #81 -> se dua duration_ms ve NULL", bo_do)
        print()
        if not tham.ghi:
            print("CHUA SUA GI - day la ban xem truoc. Them --ghi de sua (se sao luu memory.db ra TEMP truoc).")
            return 0
        if not credit and not bo_do:
            print("Khong co dong nao can sua.")
            return 0
        print("Sao luu: %s" % _sao_luu(tham.db))
        n1, n2 = ghi(conn)
        con1, con2 = tim_dong(conn)
        print("Da sua: %d dong het credit, %d dong abandoned. Con lai sau khi sua: %d / %d" % (
            n1, n2, len(con1), len(con2)))
        return 0 if not con1 and not con2 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
