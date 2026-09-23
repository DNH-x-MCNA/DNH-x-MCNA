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
import datetime as dt
import json
import os
import re
import sqlite3
import sys

# 23/09/2026: khi dan dau ra qua pipe (vd `| Select-String`), Windows khong dung ma hoa cua console
# nua ma roi ve cp1252 -> cau hoi tieng Viet lam vo script bang UnicodeEncodeError. Chay thang ra
# console thi KHONG lo loi nay, nen phai ep UTF-8 ngay trong script thay vi dua vao moi truong.
for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DB = os.environ.get("DNH_MEMORY_DB", r"C:\dnh_chatbot\backend\memory.db")

# Doi hai moc nay neu muon soi ky khac. Gio UTC.
TU_NGAY = "2026-09-01"
DEN_NGAY = "2026-09-30"

# Cua so bang phan cong doi trong kho: sync_warehouse.sync_fact_tonghopkhachhang(days=90).
# Ky bao cao lui xa hon nguong nay thi _get_team_dms_ids() KHONG con snapshot dung ky - phai di
# duong du phong va phat _warn. Xem docs/dieu_tra_v34_23-09.md muc 3.
CUA_SO_ROSTER_NGAY = 90

# Tool CHOT DOI theo ky duoc hoi. Chi nhung tool nay moi dinh vao bay tren.
TOOL_CHOT_DOI = (
    "promotion_effectiveness", "customer_product_coverage", "employee_kpi", "kpi_ranking",
    "focus_product_kpi", "customer_lifecycle",
)

# promotion_effectiveness khong truyen ngay thi TU LUI ve thang day du gan nhat truoc moc phu CTKM
# (dung o 09/01/2026) - tuc luon la ky qua khu xa, du args rong.
TOOL_MAC_DINH_LUI_QUA_KHU = ("promotion_effectiveness",)

# Dau hieu cho thay cau tra loi CO noi lai canh bao pham vi/doi hinh.
DAU_HIEU_DA_NOI = (
    "doi hinh", "đội hình", "chot doi", "chốt đội", "snapshot", "phan cong doi",
    "phân công đội", "thanh phan doi", "thành phần đội", "roster",
)

_NGAY = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


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


def _ngay_cu_nhat(blob):
    """Ngay xua nhat xuat hien trong tham so tool. None neu khong co ngay nao."""
    ngay = []
    for y, m, d in _NGAY.findall(blob):
        try:
            ngay.append(dt.date(int(y), int(m), int(d or 1)))
        except ValueError:
            pass
    return min(ngay) if ngay else None


def phan_2_canh_bao_bi_nuot(con):
    """Luot CHOT DOI cho ky lui xa hon cua so roster - dung dieu kien _warn thuc su phat.

    Ban dau muc nay loc theo ten tool chung chung ("revenue", "kpi", "salary") va ra 153/263 luot -
    rong den muc khong ai doc noi. Gio bam dung dieu kien gay loi V34: ky bao cao lui qua
    CUA_SO_ROSTER_NGAY ngay so voi luc chay.
    """
    print()
    print("=" * 78)
    print("PHAN 2 - LUOT CHOT DOI CHO KY QUA KHU XA (ung vien 'canh bao bi nuot')")
    print("=" * 78)
    print("Dieu kien: tool chot doi theo ky + ky bao cao lui hon %d ngay so voi luc chay."
          % CUA_SO_ROSTER_NGAY)
    print("Do la luc kho het snapshot phan cong doi va tool phai di duong du phong.")
    print()
    nghi, tong = [], 0
    for r in con.execute(
            "SELECT * FROM query_runs WHERE created_at>=? AND created_at<? AND status='completed' "
            "ORDER BY created_at", (TU_NGAY, DEN_NGAY)):
        blob = (r["sql_used_json"] or "")
        low = blob.lower()
        if not any(k in low for k in TOOL_CHOT_DOI):
            continue
        try:
            chay = dt.date.fromisoformat(str(r["created_at"])[:10])
        except ValueError:
            continue
        moc = chay - dt.timedelta(days=CUA_SO_ROSTER_NGAY)
        cu = _ngay_cu_nhat(blob)
        mac_dinh_lui = any(k in low for k in TOOL_MAC_DINH_LUI_QUA_KHU)
        if not ((cu and cu < moc) or mac_dinh_lui):
            continue
        tong += 1
        if not _co_dau_hieu(r["answer"]):
            nghi.append((r, cu, mac_dinh_lui))
    print("Luot chot doi cho ky qua khu xa            : %d" % tong)
    print("Trong do cau tra loi KHONG nhac gi den doi hinh : %d" % len(nghi))
    print()
    for r, cu, mac_dinh in nghi[:40]:
        print("  %s | %-14s | ky=%s%s" % (
            str(r["created_at"])[:19], r["username"],
            cu.isoformat() if cu else "(mac dinh)",
            " [tu lui]" if mac_dinh and not cu else ""))
        print("      %s" % (r["question"] or "")[:100])
    if len(nghi) > 40:
        print("  ... con %d luot nua" % (len(nghi) - 40))
    print()
    print(">> Tu ban sua 23/09 (PR #63), cac luot nay chot doi bang fact_thongketinhluong (giu 400")
    print(">> ngay) nen KHONG con lech. Danh sach tren chu yeu de ra soat luot CU truoc ban sua.")


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
        print("Khong co dong nao trong query_runs. NHUNG DAY KHONG PHAI KET LUAN 'da sach':")
        print("danh sach luot `unknown` trong checklist 22/09 lay tu LOG CHI PHI")
        print("(backend/logs/cost_log.jsonl), khong phai tu query_runs. Neu cost_log co ma")
        print("query_runs khong co thi nhung luot do DA DI DUONG KHAC, khong qua ham ghi")
        print("query_runs - tu no da la mot phat hien, phai truy tiep chu khong duoc bo qua.")
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


def phan_5_timeout(con):
    """Chi tiet 12 luot timeout - du de tach loi TRUOC/SAU tung ban sua.

    Phien backend/ can dung ba thu cho moi dong: created_at (UTC), duration_ms, va tool da goi.
    Gio may 24 = UTC + 7.
    """
    print()
    print("=" * 78)
    print("PHAN 5 - CHI TIET LUOT TIMEOUT (cho phien backend/)")
    print("=" * 78)
    rows = [r for r in con.execute(
        "SELECT * FROM query_runs WHERE created_at>=? AND created_at<? AND status<>'completed' "
        "ORDER BY created_at", (TU_NGAY, DEN_NGAY))
        if "timed out" in (r["error_message"] or "").lower()
        or "timeout" in (r["error_message"] or "").lower()]
    if not rows:
        print("Khong co luot timeout nao trong ky.")
        return
    print("%-19s %-19s %9s  %-13s %s" % ("UTC", "GIO MAY 24", "GIAY", "USER", "CAU HOI"))
    for r in rows:
        utc = str(r["created_at"])[:19]
        try:
            lo = (dt.datetime.fromisoformat(utc) + dt.timedelta(hours=7)).isoformat(sep=" ")
        except ValueError:
            lo = "?"
        giay = (r["duration_ms"] or 0) / 1000.0
        print("%-19s %-19s %9.1f  %-13s %s" % (utc, lo, giay, r["username"],
                                               (r["question"] or "")[:70]))
        print("    TOOL: %s" % (r["sql_used_json"] or "(khong ghi)")[:400])
    print()
    print(">> Doi chieu gio MAY 24 (khong phai UTC) voi gio commit ban sua de biet truoc/sau.")


def main():
    con = _mo()
    print("Doc: %s" % DB)
    print("Ky : %s -> %s (gio UTC; cong 7 tieng ra gio may 24)" % (TU_NGAY, DEN_NGAY))
    print()
    phan_1_khuyen_mai(con)
    phan_2_canh_bao_bi_nuot(con)
    phan_3_luot_khong_ten(con)
    phan_4_loi_va_phan_hoi(con)
    phan_5_timeout(con)
    con.close()


if __name__ == "__main__":
    main()
