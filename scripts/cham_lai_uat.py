"""Chay lai cac luot UAT can cham lai - MAC DINH KHONG GOI MODEL, phai co --xac-nhan.

    python scripts/cham_lai_uat.py                      # xem truoc, KHONG ton tien
    python scripts/cham_lai_uat.py --ma 01 03 --xac-nhan  # chay that 2 muc

AGENTS.md: moi luot goi model tra phi phai duoc anh Dang duyet TRUOC. Script nay vi vay fail-closed:
khong co `--xac-nhan` thi chi in ra se chay gi va uoc tinh het bao nhieu, roi thoat.

AGENTS.md cung bat buoc truyen `username` rieng va `session_id` co tien to nhan dien duoc, neu khong
thi ket qua KHONG dung de cham UAT. Script lay pham vi (mien/kenh/ma nhan vien/vai) tu CHINH auth.db
qua `main._business_scopes` - dung ham web app dang dung, khong viet lai. Viet lai se sinh ra hai
dinh nghia pham vi song song, dung cai bay da ghi trong report_templates._get_team_dms_ids.

Neu khong xac dinh duoc tai khoan cho mot muc thi BO QUA muc do va bao ro, khong chay bang quyen
trong - chay sai vai con te hon khong chay, vi so lieu nhin van hop ly.
"""
import argparse
import datetime as dt
import io
import json
import os
import statistics
import sys
import time
import unicodedata

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GOC, "backend"))

for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DANH_SACH = os.path.join(GOC, "scripts", "cham_lai_20_luot.json")
# 23/09/2026: BO uoc tinh mot don gia chung. Chi phi moi luot phu thuoc DO NANG cua cau hoi - hai
# luot dau chay that mat 33,9 giay va 23,8 giay, khong the cung gia. Gio uoc tinh theo LICH SU CUA
# CHINH CAU HOI DO trong cost_log: tra ve trung vi cac lan da hoi, kem so quan sat de biet do tin.
# Cau nao chua tung hoi thi dung trung vi chung va danh dau ro.
#
# Lich su cac con so da dung, de khong ai quay lai dung nham:
#   4.000d  - trung binh log ngay 22/09, tren cac phien NHIEU luot dung san cache -> khong ap duoc
#   8.550d  - trung binh 2 luot chay that 23/09 -> dung kieu chay nhung phang, bo qua do nang
VND_MOI_USD = 25000


def _gon(s: str) -> str:
    """Bo dau, chu thuong, gop khoang trang - de khop cau hoi trong JSON (khong dau) voi
    question_preview trong cost_log (co dau)."""
    s = "".join(ch for ch in unicodedata.normalize("NFD", (s or "").lower())
                if unicodedata.category(ch) != "Mn")
    return " ".join(s.replace("d", "d").replace("đ", "d").split())


def _lich_su_chi_phi():
    """question (da gon) -> danh sach cost_usd cac lan da hoi. Doc cost_log, khong goi model."""
    try:
        from cost_logger import LOG_PATH
    except ImportError:
        return {}, []
    if not os.path.exists(LOG_PATH):
        return {}, []
    theo_cau, tat_ca = {}, []
    with io.open(LOG_PATH, encoding="utf-8", errors="replace") as f:
        for dong in f:
            dong = dong.strip()
            if not dong:
                continue
            try:
                e = json.loads(dong)
            except ValueError:
                continue
            gia = float(e.get("cost_usd") or 0)
            if gia <= 0:
                continue
            tat_ca.append(gia)
            khoa = _gon(e.get("question_preview") or "")
            if khoa:
                theo_cau.setdefault(khoa, []).append(gia)
    return theo_cau, tat_ca


def _uoc_tinh(cau_hoi: str, theo_cau: dict, tat_ca: list):
    """Tra (usd, so_quan_sat, nguon). Khop theo tien to vi question_preview bi cat con 120 ky tu."""
    can = _gon(cau_hoi)
    khop = []
    for khoa, gia in theo_cau.items():
        if khoa.startswith(can[:60]) or can.startswith(khoa[:60]):
            khop.extend(gia)
    if khop:
        return statistics.median(khop), len(khop), "lich su chinh cau nay"
    if tat_ca:
        return statistics.median(tat_ca), len(tat_ca), "TRUNG VI CHUNG (cau nay chua tung hoi)"
    return None, 0, "khong co lich su"


def _nap_muc():
    with io.open(DANH_SACH, encoding="utf-8") as f:
        return json.load(f)["muc"]


def _nap_tai_khoan():
    """Doc danh sach tai khoan MOT lan. Bao ro thay vi nem traceback khi kho chua san sang."""
    import auth
    import sqlite3
    try:
        return auth.list_users() or []
    except sqlite3.OperationalError as loi:
        sys.exit(
            "KHONG DOC DUOC TAI KHOAN tu %s: %s\n"
            "Script nay phai chay TREN MAY 24, noi co auth.db that. Tren may dev khong co du\n"
            "tai khoan nen khong the suy ra pham vi dung vai - va chay sai vai thi theo AGENTS.md\n"
            "ket qua khong dung de cham UAT duoc." % (getattr(auth, "DB_PATH", "auth.db"), loi))


def _tra_tai_khoan(ds: list, nguoi: str):
    """Ten hien thi trong checklist -> ban ghi user that. Tra (user, ly_do_khong_ra).

    TU CHOI khi khong ra hoac ra nhieu hon mot - khong doan. Mot luot chay sai vai van tra ve so
    lieu trong hop ly, nen doan o day la cach chac chan nhat de hong ca dot cham lai ma khong ai biet.
    """
    khop_username = [u for u in ds if str(u.get("username", "")).lower() == nguoi.lower()]
    if len(khop_username) == 1:
        return khop_username[0], None
    can = nguoi.lower().strip()
    khop_ten = [u for u in ds
                if can in str(u.get("name") or "").lower()
                or can in str(u.get("username") or "").lower()]
    if len(khop_ten) == 1:
        return khop_ten[0], None
    if not khop_ten:
        return None, "khong tim thay tai khoan nao khop"
    ten = ", ".join(sorted(str(u.get("username")) for u in khop_ten))
    return None, f"khop {len(khop_ten)} tai khoan ({ten}) - phai ghi ro username trong file danh sach"


def _pham_vi(user: dict):
    """Dung dung ham cua web app de khong sinh dinh nghia pham vi thu hai."""
    import main
    try:
        return main._business_scopes(user), None
    except Exception as exc:  # HTTPException cua FastAPI, hoac loi cau hinh scope
        return None, str(getattr(exc, "detail", exc))[:200]


def _chi_phi_theo_session(sid: str):
    """Chi phi THAT cua rieng mot muc - cong cac dong cost_log mang dung session_id nay.

    Chinh xac hon phep tru tong truoc/sau: neu co luot khac chay xen vao thi phep tru sai, con
    loc theo session_id thi khong.
    """
    try:
        from cost_logger import LOG_PATH
    except ImportError:
        return None
    if not os.path.exists(LOG_PATH):
        return None
    tong = 0.0
    with io.open(LOG_PATH, encoding="utf-8", errors="replace") as f:
        for dong in f:
            dong = dong.strip()
            if not dong:
                continue
            try:
                e = json.loads(dong)
            except ValueError:
                continue
            if e.get("session_id") == sid:
                tong += float(e.get("cost_usd") or 0)
    return tong


def _chi_phi_hien_tai():
    """Tong USD trong cost_log, de do chenh lech truoc/sau ma khong phai doan."""
    try:
        from cost_logger import LOG_PATH
    except ImportError:
        return None
    if not os.path.exists(LOG_PATH):
        return 0.0
    tong = 0.0
    with io.open(LOG_PATH, encoding="utf-8", errors="replace") as f:
        for dong in f:
            dong = dong.strip()
            if not dong:
                continue
            try:
                tong += float(json.loads(dong).get("cost_usd") or 0)
            except ValueError:
                pass
    return tong


def main():
    ap = argparse.ArgumentParser(description="Chay lai cac luot UAT can cham lai")
    ap.add_argument("--ma", nargs="*", help="Chi chay cac ma nay (vd: 01 03 15). Rong = tat ca.")
    ap.add_argument("--xac-nhan", action="store_true",
                    help="BAT BUOC de thuc su goi model. Khong co co nay thi chi xem truoc.")
    ap.add_argument("--ket-qua", default=None, help="File markdown ghi ket qua")
    tham = ap.parse_args()

    muc = _nap_muc()
    if tham.ma:
        chon = {m.strip() for m in tham.ma}
        muc = [m for m in muc if m["ma"] in chon]
        thieu = chon - {m["ma"] for m in muc}
        if thieu:
            sys.exit("Khong co ma: %s" % ", ".join(sorted(thieu)))
    if not muc:
        sys.exit("Danh sach rong.")

    print("=" * 78)
    print("CHAM LAI UAT - %d muc" % len(muc))
    print("=" * 78)

    tai_khoan = _nap_tai_khoan()
    print("Doc duoc %d tai khoan tu auth.db." % len(tai_khoan))
    print()

    ke_hoach, bo_qua = [], []
    for m in muc:
        user, ly_do = _tra_tai_khoan(tai_khoan, m["nguoi"])
        if not user:
            bo_qua.append((m, ly_do))
            continue
        pv, loi = _pham_vi(user)
        if not pv:
            bo_qua.append((m, "pham vi khong hop le: %s" % loi))
            continue
        ke_hoach.append((m, user, pv))

    theo_cau, tat_ca = _lich_su_chi_phi()
    print("Lich su chi phi: %d luot da ghi, %d cau hoi khac nhau." % (len(tat_ca), len(theo_cau)))
    print()

    tong_usd, so_doan = 0.0, 0
    print("%-5s %-16s %10s %5s  %s" % ("MA", "TAI KHOAN", "UOC TINH", "QS", "CAU HOI"))
    for m, user, pv in ke_hoach:
        usd, n, nguon = _uoc_tinh(m["cau_hoi"], theo_cau, tat_ca)
        if usd is None:
            gia = "?"
        else:
            tong_usd += usd
            if "CHUNG" in nguon:
                so_doan += 1
            gia = format(round(usd * VND_MOI_USD), ",d").replace(",", ".") + "d"
        print("%-5s %-16s %10s %5s  %s" % (m["ma"], user["username"], gia, n or "-",
                                           m["cau_hoi"][:60]))
        if usd is not None and "CHUNG" in nguon:
            print("      ^ cau nay CHUA TUNG HOI - dung trung vi chung, do tin thap")
    if bo_qua:
        print()
        print("BO QUA %d muc (khong chay bang quyen trong):" % len(bo_qua))
        for m, ly_do in bo_qua:
            print("  [%s] %-16s -> %s" % (m["ma"], m["nguoi"], ly_do))

    print()
    print("Se chay : %d luot" % len(ke_hoach))
    if tat_ca:
        print("Uoc tinh: ~%s VND  (%.4f USD) - tinh theo DO NANG tung cau, khong phai don gia chung"
              % (format(round(tong_usd * VND_MOI_USD), ",d").replace(",", "."), tong_usd))
        re_nhat = min(tat_ca) * VND_MOI_USD
        dat_nhat = max(tat_ca) * VND_MOI_USD
        print("         Bien do mot luot trong lich su: %s - %sd -> uoc tinh co the lech nhieu"
              % (format(round(re_nhat), ",d").replace(",", "."),
                 format(round(dat_nhat), ",d").replace(",", ".")))
        if so_doan:
            print("         %d/%d muc phai dung trung vi chung (chua tung hoi) - phan nay do tin thap"
                  % (so_doan, len(ke_hoach)))
    else:
        print("Uoc tinh: KHONG CO LICH SU CHI PHI - khong uoc tinh duoc, phai chay tren may 24.")

    if not tham.xac_nhan:
        print()
        print("=" * 78)
        print("CHUA CHAY GI CA - day la ban xem truoc, khong ton mot dong nao.")
        print("Them --xac-nhan de thuc su goi model. AGENTS.md: phai duoc anh Dang duyet truoc.")
        print("=" * 78)
        return

    import nl2sql
    ngay = dt.date.today().strftime("%d%m")
    truoc = _chi_phi_hien_tai()
    ket_qua = []
    for m, user, pv in ke_hoach:
        area, emp, kenh = pv
        sid = "chamlai%s-%s" % (ngay, m["ma"])
        print()
        print("-" * 78)
        print("[%s] %s | session=%s" % (m["ma"], user["username"], sid))
        print("HOI: %s" % m["cau_hoi"])
        bat_dau = time.time()
        try:
            r = nl2sql.ask(m["cau_hoi"], session_id=sid, username=user["username"],
                           scope_area_code=area, scope_employee_code=emp, scope_channel=kenh,
                           scope_role=user.get("role"), origin="cham_lai_uat")
            tra_loi, loi = r.get("answer") or "", None
            cong_cu = r.get("sql_used") or []
        except Exception as exc:
            tra_loi, loi, cong_cu = "", "%s: %s" % (type(exc).__name__, str(exc)[:300]), []
        giay = time.time() - bat_dau
        print("=> %.1f giay | %s" % (giay, ("LOI: " + loi) if loi else "xong"))
        if tra_loi:
            print(tra_loi[:1200])
        ket_qua.append({"ma": m["ma"], "nguoi": user["username"], "cau_hoi": m["cau_hoi"],
                        "can_thay": m["can_thay"], "tra_loi": tra_loi, "loi": loi,
                        "cong_cu": cong_cu, "giay": round(giay, 1), "session_id": sid,
                        "usd": _chi_phi_theo_session(sid)})

    sau = _chi_phi_hien_tai()
    print()
    print("=" * 78)
    print("CHI PHI THAT THEO TUNG MUC")
    print("=" * 78)
    print("%-5s %10s %8s  %s" % ("MA", "THAT", "GIAY", "CAU HOI"))
    for k in ket_qua:
        tien = ("%sd" % format(round((k["usd"] or 0) * VND_MOI_USD), ",d").replace(",", ".")
                if k["usd"] is not None else "?")
        print("%-5s %10s %8.1f  %s" % (k["ma"], tien, k["giay"], k["cau_hoi"][:52]))
    do_duoc = [k["usd"] for k in ket_qua if k["usd"]]
    if do_duoc:
        print()
        print("  re nhat : %sd" % format(round(min(do_duoc) * VND_MOI_USD), ",d").replace(",", "."))
        print("  dat nhat: %sd" % format(round(max(do_duoc) * VND_MOI_USD), ",d").replace(",", "."))
        print("  chenh   : %.1f lan giua cau re nhat va dat nhat" % (max(do_duoc) / min(do_duoc)))
    print()
    if truoc is not None and sau is not None:
        usd = sau - truoc
        print("Tong chi phi dot nay: %.4f USD (~%s VND)" % (
            usd, format(round(usd * VND_MOI_USD), ",d").replace(",", ".")))
    print("Xong %d/%d luot, %d luot loi." % (
        len(ket_qua), len(ke_hoach), sum(1 for k in ket_qua if k["loi"])))

    duong_dan = tham.ket_qua or os.path.join(
        GOC, "docs", "ket_qua_cham_lai_%s.md" % dt.date.today().strftime("%d-%m"))
    with io.open(duong_dan, "w", encoding="utf-8", newline="") as f:
        f.write("# Kết quả chấm lại UAT — %s\n\n" % dt.date.today().strftime("%d/%m/%Y"))
        f.write("*Sinh tự động bởi `scripts/cham_lai_uat.py`. Mỗi mục kèm điều kiện cần thấy "
                "để đóng, lấy từ `docs/checklist_cham_lai_22-09.md`.*\n\n")
        for k in ket_qua:
            f.write("## Mục %s — `%s`\n\n" % (k["ma"], k["nguoi"]))
            f.write("**Hỏi:** %s\n\n" % k["cau_hoi"])
            f.write("**Cần thấy để đóng:** %s\n\n" % k["can_thay"])
            f.write("**Phiên:** `%s` · **Thời gian:** %.1f giây\n\n" % (k["session_id"], k["giay"]))
            if k.get("usd") is not None:
                f.write("**Chi phí thật:** %s đ\n\n"
                        % format(round(k["usd"] * VND_MOI_USD), ",d").replace(",", "."))
            if k["cong_cu"]:
                f.write("**Công cụ đã gọi:**\n\n```\n%s\n```\n\n" % "\n".join(str(c) for c in k["cong_cu"]))
            if k["loi"]:
                f.write("> ⚠️ **LỖI:** %s\n\n" % k["loi"])
            f.write("**Trả lời:**\n\n%s\n\n---\n\n" % (k["tra_loi"] or "*(rỗng)*"))
    print("Da ghi: %s" % duong_dan)


if __name__ == "__main__":
    main()
