"""Doc query_runs tren MAY 24 - mien phi, KHONG goi model tra phi.

Chay THANG tren may 24:
    python C:\\dnh_chatbot\\scripts\\doc_query_runs_may_24.py

Vi sao can script nay: log chi phi chi co trang thai va nhan xet da tom tat, con `query_runs` trong
`memory.db` giu them TOOL DA GOI (`sql_used_json`), CAU TRA LOI DAY DU va `feedback_comment` nguyen
van. Doi chieu 23/09/2026 bang nguon nay dong duoc 6/24 muc trong danh sach cham lai ma khong ton
mot luot goi model nao.

LUU Y GIO: `audit_log.jsonl` ghi gio DIA PHUONG, `query_runs.created_at` ghi UTC - lech dung 7 tieng.
Loc theo `session_id` thay vi theo gio de khoi tim truot.

Khong co `sqlite3` CLI tren may 24 nen moi truy van phai di qua Python.
"""
import json
import os
import sqlite3
import sys

DB = os.environ.get("DNH_MEMORY_DB", r"C:\dnh_chatbot\backend\memory.db")

# Doi hai moc nay neu muon soi ky khac. Gio UTC.
TU_NGAY = "2026-09-01"
DEN_NGAY = "2026-09-30"

# Tool co the phat _warn() ma model CO THE khong noi lai. Xem muc 5 docs/dieu_tra_v34_23-09.md:
# _warn() chi dinh canh bao vao ket qua tra cho model, model bo qua duoc.
TOOL_CO_CANH_BAO = (
    "promotion", "customer_product_coverage", "kpi", "revenue", "salary", "coverage",
)

# Dau hieu cho thay cau tra loi CO noi lai canh bao pham vi/doi hinh.
DAU_HIEU_DA_NOI = (
    "doi hinh", "đội hình", "chot doi", "chốt đội", "snapshot", "phan cong doi",
    "phân công đội", "thieu du lieu", "thiếu dữ liệu", "canh bao", "cảnh báo",
    "chi gom", "chỉ gồm", "khong phai toan quoc", "không phải toàn quốc",
)


def _mo():
    if not os.path.exists(DB):
        sys.exit("KHONG THAY %s - sua bien DB o dau file hoac dat DNH_MEMORY_DB." % DB)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _tools(row):
    try:
        return json.loads(row["sql_used_json"] or "[]")
    except (TypeError, ValueError):
        return []


def _co_dau_hieu(text):
    low = (text or "").lower()
    return [d for d in DAU_HIEU_DA_NOI if d in low]


def phan_1_khuyen_mai(con):
    """V34: lay THAM SO thuc su cua luot khuyen mai de chot viec 4 vs 12+ chuong trinh."""
    print("=" * 78)
    print("PHAN 1 - CAC LUOT KHUYEN MAI (V34/C18/M35)")
    print("=" * 78)
    rows = [r for r in con.execute(
        "SELECT * FROM query_runs WHERE created_at>=? AND created_at<? ORDER BY created_at",
        (TU_NGAY, DEN_NGAY)) if any("promotion" in json.dumps(t).lower() for t in _tools(r))]
    if not rows:
        print("Khong thay luot nao goi tool khuyen mai trong ky nay.")
        return
    for r in rows:
        print("-" * 78)
        print("%s | %s | %s | session=%s" % (
            str(r["created_at"])[:19], r["username"], r["status"], r["session_id"]))
        print("HOI : %s" % (r["question"] or "")[:300])
        print("TOOL: %s" % json.dumps(_tools(r), ensure_ascii=False)[:1500])
        if r["feedback_rating"] is not None:
            print("CHAM: %s | %s | %s" % (
                r["feedback_rating"], r["feedback_category"], r["feedback_comment"]))
        ans = r["answer"] or ""
        print("So chuong trinh xuat hien trong cau tra loi (uoc luong theo dau '|'): %d dong bang"
              % ans.count("\n|"))
        print("TRA LOI (2000 ky tu dau):")
        print(ans[:2000])
    print()
    print(">> Can doi chieu: THAM SO scope_* trong TOOL o tren so voi @ManagerCode cua checker.")
    print(">> Neu checker chay voi @ManagerCode IS NULL thi no la TOAN QUOC, khong cung pham vi.")


def phan_2_canh_bao_bi_nuot(con):
    """Cac luot goi tool co the phat _warn nhung cau tra loi khong nhac gi den pham vi/doi hinh."""
    print()
    print("=" * 78)
    print("PHAN 2 - UNG VIEN 'CANH BAO BI NUOT'")
    print("=" * 78)
    print("Day la DANH SACH UNG VIEN, khong phai ket luan. Nguoi doc tu quyet.")
    print()
    nghi, tong = [], 0
    for r in con.execute(
            "SELECT * FROM query_runs WHERE created_at>=? AND created_at<? AND status='completed' "
            "ORDER BY created_at", (TU_NGAY, DEN_NGAY)):
        blob = json.dumps(_tools(r), ensure_ascii=False).lower()
        if not any(k in blob for k in TOOL_CO_CANH_BAO):
            continue
        tong += 1
        if not _co_dau_hieu(r["answer"]):
            nghi.append(r)
    print("Luot goi tool co the phat canh bao : %d" % tong)
    print("Trong do cau tra loi KHONG nhac gi den pham vi/doi hinh/thieu du lieu : %d" % len(nghi))
    print()
    for r in nghi[:40]:
        print("  %s | %-14s | %s" % (
            str(r["created_at"])[:19], r["username"], (r["question"] or "")[:90]))
    if len(nghi) > 40:
        print("  ... con %d luot nua" % (len(nghi) - 40))
    print()
    print(">> Khong phai luot nao trong so nay cung co canh bao that - tool chi phat _warn trong mot")
    print(">> so dieu kien. Day la de KHOANH VUNG, buoc sau moi doc tung luot.")


def phan_3_luot_khong_ten(con):
    """AGENTS.md: luot khong co username rieng thi KHONG dung de cham UAT - va can truy ra ai chay."""
    print()
    print("=" * 78)
    print("PHAN 3 - LUOT KHONG TRUY DUOC NGUOI CHAY")
    print("=" * 78)
    rows = list(con.execute(
        "SELECT username, session_id, COUNT(*) n, MIN(created_at) tu, MAX(created_at) den "
        "FROM query_runs WHERE username IS NULL OR TRIM(username)='' OR LOWER(username) IN "
        "('unknown','alice','test','admin') GROUP BY username, session_id ORDER BY MIN(created_at)"))
    if not rows:
        print("Khong con luot nao khong truy duoc nguoi chay. Tot.")
        return
    print("%-12s %-38s %5s  %-19s %-19s" % ("USER", "SESSION", "SO", "TU (UTC)", "DEN (UTC)"))
    for r in rows:
        print("%-12s %-38s %5d  %-19s %-19s" % (
            r["username"] or "(rong)", r["session_id"], r["n"],
            str(r["tu"])[:19], str(r["den"])[:19]))
    print()
    print(">> Cong 7 tieng de ra gio may 24. Doi chieu session_id nay voi audit_log.jsonl")
    print(">> (ghi gio DIA PHUONG) de truy ra may/nguoi da chay.")


def phan_4_loi_va_phan_hoi(con):
    """Phan loai luot error theo error_message - 9/13 luot thang 9 la HET CREDIT, khong phai loi SP."""
    print()
    print("=" * 78)
    print("PHAN 4 - LUOT LOI VA LUOT CO PHAN HOI")
    print("=" * 78)
    loai = {}
    for r in con.execute(
            "SELECT * FROM query_runs WHERE created_at>=? AND created_at<? AND status<>'completed' "
            "ORDER BY created_at", (TU_NGAY, DEN_NGAY)):
        msg = (r["error_message"] or "").strip()
        if "credit balance" in msg.lower():
            key = "HET CREDIT (khong phai loi san pham)"
        elif "timed out" in msg.lower() or "timeout" in msg.lower():
            key = "TIMEOUT (loi that)"
        elif not msg:
            key = "KHONG CO error_message (status=%s)" % r["status"]
        else:
            key = msg[:60]
        loai.setdefault(key, []).append(r)
    if not loai:
        print("Khong co luot nao khac 'completed' trong ky.")
    for key, rows in sorted(loai.items(), key=lambda kv: -len(kv[1])):
        print()
        print("[%d luot] %s" % (len(rows), key))
        for r in rows:
            print("   %s | %-14s | %s" % (
                str(r["created_at"])[:19], r["username"], (r["question"] or "")[:80]))

    print()
    print("-" * 78)
    print("LUOT CO PHAN HOI CHAM")
    print("-" * 78)
    for r in con.execute(
            "SELECT * FROM query_runs WHERE created_at>=? AND created_at<? "
            "AND feedback_rating IS NOT NULL ORDER BY created_at", (TU_NGAY, DEN_NGAY)):
        dau = "THICH" if r["feedback_rating"] == 1 else "KHONG THICH"
        print("%s | %-14s | %-11s | %s" % (
            str(r["created_at"])[:19], r["username"], dau, (r["question"] or "")[:70]))
        if r["feedback_comment"]:
            print("      nhan xet: %s" % r["feedback_comment"])


def main():
    con = _mo()
    print("Doc: %s" % DB)
    print("Ky : %s -> %s (gio UTC; cong 7 tieng ra gio may 24)" % (TU_NGAY, DEN_NGAY))
    print()
    phan_1_khuyen_mai(con)
    phan_2_canh_bao_bi_nuot(con)
    phan_3_luot_khong_ten(con)
    phan_4_loi_va_phan_hoi(con)
    con.close()


if __name__ == "__main__":
    main()
