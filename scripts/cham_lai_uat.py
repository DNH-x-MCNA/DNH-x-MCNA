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
import sys
import time

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GOC, "backend"))

for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DANH_SACH = os.path.join(GOC, "scripts", "cham_lai_20_luot.json")
# DO THAT 23/09/2026: 2 luot dau tien het 0,6841 USD = ~17.100d, tuc ~8.550d/luot - GAP DOI con so
# 4.000d lay tu log chi phi ngay 22/09. Ly do: moi muc chay trong mot session RIENG nen luot nao cung
# phai ghi cache tu dau, ma cache chiem 71% chi phi. Con so 4.000d/luot cua ngay 22/09 la trung binh
# tren cac phien nhieu luot, dung san cache - khong ap duoc cho kieu chay nay.
VND_MOI_LUOT = 8550


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

    for m, user, pv in ke_hoach:
        area, emp, kenh = pv
        print("  [%s] %-16s vai=%-18s mien=%-4s kenh=%-4s nv=%s" % (
            m["ma"], user["username"], user.get("role"), area or "-", kenh or "-", emp or "-"))
        print("       %s" % m["cau_hoi"][:90])
    if bo_qua:
        print()
        print("BO QUA %d muc (khong chay bang quyen trong):" % len(bo_qua))
        for m, ly_do in bo_qua:
            print("  [%s] %-16s -> %s" % (m["ma"], m["nguoi"], ly_do))

    print()
    print("Se chay : %d luot" % len(ke_hoach))
    print("Uoc tinh: ~%s VND (%d x %s)" % (
        format(len(ke_hoach) * VND_MOI_LUOT, ",d").replace(",", "."),
        len(ke_hoach), format(VND_MOI_LUOT, ",d").replace(",", ".")))

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
                        "cong_cu": cong_cu, "giay": round(giay, 1), "session_id": sid})

    sau = _chi_phi_hien_tai()
    print()
    print("=" * 78)
    if truoc is not None and sau is not None:
        usd = sau - truoc
        print("Chi phi THAT cua dot nay: %.4f USD (~%s VND)" % (
            usd, format(round(usd * 25000), ",d").replace(",", ".")))
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
            if k["cong_cu"]:
                f.write("**Công cụ đã gọi:**\n\n```\n%s\n```\n\n" % "\n".join(str(c) for c in k["cong_cu"]))
            if k["loi"]:
                f.write("> ⚠️ **LỖI:** %s\n\n" % k["loi"])
            f.write("**Trả lời:**\n\n%s\n\n---\n\n" % (k["tra_loi"] or "*(rỗng)*"))
    print("Da ghi: %s" % duong_dan)


if __name__ == "__main__":
    main()
