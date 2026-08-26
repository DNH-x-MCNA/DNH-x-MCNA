# -*- coding: utf-8 -*-
"""Doi chieu DO DUNG CUA SO tren cac tool moi - KHONG goi API, KHONG dung Bravo, khong ton tien.

VI SAO CAN: 26/08/2026 do dinh tuyen tool dat 25/25 (100%). Nhung "model goi dung tool" va "con so
tra ve dung" la HAI viec khac nhau. Ba lan dau nhat cua du an deu thuoc loai thu hai, va ca ba deu
cho ra cau tra loi TRONG HOAN TOAN HOP LY:
  - doanh thu tu dung cong thuc lech ~4%/ngay -> phai chuyen sang goi thang view Bravo;
  - cong no theo cong thuc cu thoi 4-15 lan -> phai chuyen sang usp_DeptAccDueDate_GetData;
  - cong lan tang TDV va tang QLV -> gap doi, da dinh 3 cho.
Dinh tuyen dung tool khong do duoc gi cho ca ba.

Script kiem cac BAT BIEN - nhung dieu phai dung du du lieu thay doi the nao. Cho nao lech chinh la
cho co loi. Chay tren may co du lieu that:

    python scripts/doi_chieu_so_lieu_tool_moi.py

Ma thoat 0 = moi bat bien deu giu; 1 = co it nhat mot cho lech can dieu tra.
"""
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 26/08/2026: CO Y khong dung DNH_BACKEND_DIR de chon noi nap module. Script nay nam trong repo nao
# thi phai kiem chinh backend cua repo do - neu khong, mot bien moi truong sot lai trong phien
# PowerShell se am tham lai script sang mot ban clone khac. Da xay ra that tren may 24: bien tro vao
# C:\dnh_chatbot_test_28a7328_20260825-140023\backend (ban test, kho rong) nen ca 5 phep kiem deu
# rong tuech ma bao cao van in ra dong ket luan xanh.
BACKEND = ROOT / "backend"
for _p in (str(BACKEND), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import report_templates as rt  # noqa: E402
import local_warehouse as _lw  # noqa: E402

_wq = rt._q  # cung ham truy van ma chinh cac tool dung - doi chieu tren cung nen du lieu

# 26/08/2026: KHONG duoc tin bien moi truong DNH_BACKEND_DIR de bao "dang doi chieu kho nao". Da dinh
# dung cai bay nay hai lan trong hai ngay:
#   - 25/08: run_business_evaluation.py doc log theo DNH_BACKEND_DIR trong khi cost_logger.py GHI theo
#     vi tri file cua chinh no -> bao cao "0 tool, 0 dong" ba lan lien, tuong model chon sai tool.
#   - 26/08: chinh script nay in "Kho du lieu: C:\\dnh_chatbot_test_...\\backend" - mot ban TEST - roi
#     bo qua ca 5 phep kiem va ket luan "MOI BAT BIEN DEU GIU". Ket luan trang, tren kho rong.
# Nguyen tac rut ra: LUON hoi chinh module dang lam viec xem no doc file nao, dung tu suy tu bien moi
# truong. local_warehouse.DB_PATH la duong dan THAT ma moi tool dang truy van.
KHO_THUC_TE = Path(_lw.DB_PATH)

_loi = []
_bo_qua = []


def _kiem(ten, dat, chi_tiet=""):
    print("  [%s] %s" % ("DAT " if dat else "LECH", ten))
    if chi_tiet:
        for dong in str(chi_tiet).splitlines():
            print("         %s" % dong)
    if not dat:
        _loi.append(ten)


def _bo(ten, ly_do):
    print("  [BO  ] %s" % ten)
    print("         %s" % ly_do)
    _bo_qua.append(ten)


def _tien(x):
    return "%s" % format(round(x or 0), ",")


# ---------------------------------------------------------------------------------------
def kiem_1_hai_nguon_khong_chong_lan():
    """Doanh thu duoc ghep tu HAI nguon: vhoadon_otc/etc (chi tiet 12 thang gan) +
    monthly_customer_summary (phan cu da nen). revenue_by_channel() cong CA HAI ma KHONG loai tru
    nhau: no cong chi tiet cho TOAN BO khoang ngay, roi cong them bang nen cho phan truoc moc cat.

    An toan hien nay dua vao mot bat bien KHONG AI KIEM: sync_warehouse.py chia theo TRON THANG
    (`if a < cutoff` voi a la ngay dau thang) nen mot thang chi nam o mot nguon. Neu ai sua moc cat
    o mot noi ma quen noi kia, cac thang chong lan se bi DEM HAI LAN - doanh thu tu nhien gap doi ma
    khong co canh bao nao. Dung loai loi tung ton 4%/ngay."""
    print()
    print("1. HAI NGUON DOANH THU KHONG DUOC CHONG LAN THANG")
    for kenh, bang in (("OTC", "vhoadon_otc"), ("ETC", "vhoadon_etc")):
        rows = _wq("SELECT DISTINCT substr(doc_date,1,7) ym FROM %s "
                   "INTERSECT SELECT DISTINCT year_month FROM monthly_customer_summary "
                   "WHERE channel=? ORDER BY ym" % bang, (kenh,))
        chong = [r["ym"] for r in rows]
        if chong:
            tong = _wq("SELECT COALESCE(SUM(revenue),0) v FROM monthly_customer_summary "
                       "WHERE channel=? AND year_month IN (%s)"
                       % ",".join("?" * len(chong)), (kenh, *chong))[0]["v"]
            _kiem("%s: khong thang nao nam o ca hai nguon" % kenh, False,
                  "Chong lan %d thang: %s\nSo tien bi dem hai lan: %s dong"
                  % (len(chong), ", ".join(chong), _tien(tong)))
        else:
            _kiem("%s: khong thang nao nam o ca hai nguon" % kenh, True)


def kiem_2_chuoi_thang_khop_mot_lan_goi():
    """revenue_monthly_series goi revenue_by_channel 12 lan (moi thang mot lan). Tong 12 lan do PHAI
    bang dung mot lan goi cho ca khoang - neu lech thi bien thang bi ho hoac chong (vd ngay 31 bi
    bo, hoac thang nhuan tinh sai). Hai duong di khac han nhau nen day la phep doi chieu that."""
    print()
    print("2. TONG CHUOI 12 THANG == MOT LAN GOI CA KHOANG")
    chuoi = rt.revenue_monthly_series(months_back=12, include_yoy=False)
    if chuoi.get("error"):
        return _bo("chuoi 12 thang", chuoi["error"])
    co_du_lieu = [m for m in chuoi["months"] if not m.get("khong_co_du_lieu")]
    if not co_du_lieu:
        return _bo("chuoi 12 thang", "Khong thang nao co du lieu.")
    tong_chuoi = sum(m["revenue"] or 0 for m in co_du_lieu)
    d_from, _ = rt._month_bounds(co_du_lieu[0]["month"])
    _, d_to = rt._month_bounds(co_du_lieu[-1]["month"])
    mot_lan = rt.revenue_by_channel(d_from, d_to)["total"]["revenue"]
    lech = abs(tong_chuoi - mot_lan)
    _kiem("tong tung thang == mot lan goi (%s .. %s)" % (d_from, d_to), lech < 1,
          "chuoi: %s dong\nmot lan: %s dong\nlech: %s dong (%.4f%%)"
          % (_tien(tong_chuoi), _tien(mot_lan), _tien(lech),
             lech / mot_lan * 100 if mot_lan else 0))


def kiem_3_dia_ban_cong_lai_bang_toan_cong_ty():
    """geography_monthly_performance chi truy van vhoadon_otc/etc, KHONG cong bang nen. Nen voi
    thang nam ngoai cua so chi tiet 12 thang, no tra ve 0 trong khi tool doanh thu tra ve so that -
    cung mot cau hoi ra hai con so khac nhau. Tool co ghi canh bao nhung canh bao khong ngan duoc
    viec model doc so 0 thanh "dia ban do khong ban duoc gi".

    Ngoai ra tong cac dia ban (KE CA UNKNOWN) phai bang tong toan cong ty - lech nghia la co khach
    bi rot am tham khi join danh muc tinh."""
    print()
    print("3. TONG CAC DIA BAN == TONG TOAN CONG TY (tung thang)")
    dia_ban = rt.geography_monthly_performance(months_back=12, dimension="area", limit=500)
    if dia_ban.get("error"):
        return _bo("dia ban theo thang", dia_ban["error"])
    chuoi = rt.revenue_monthly_series(months_back=12, include_yoy=False)
    theo_thang = {}
    for r in dia_ban["rows"]:
        theo_thang[r["month"]] = theo_thang.get(r["month"], 0.0) + (r["revenue"] or 0)
    thieu_han = []
    for m in chuoi.get("months", []):
        if m.get("khong_co_du_lieu"):
            continue
        thang, tong_cty = m["month"], (m["revenue"] or 0)
        tong_db = theo_thang.get(thang, 0.0)
        lech = abs(tong_db - tong_cty)
        if tong_db == 0 and tong_cty > 0:
            thieu_han.append(thang)
        elif lech >= 1:
            _kiem("thang %s" % thang, False,
                  "dia ban: %s | toan cong ty: %s | lech %s dong (%.3f%%)"
                  % (_tien(tong_db), _tien(tong_cty), _tien(lech),
                     lech / tong_cty * 100 if tong_cty else 0))
        else:
            _kiem("thang %s" % thang, True)
    if thieu_han:
        _kiem("cac thang dia ban tra ve 0 nhung cong ty co doanh thu", False,
              "%d thang: %s\nNguyen nhan gan nhu chac chan: geography_monthly_performance khong cong\n"
              "monthly_customer_summary nen moi thang ngoai cua so chi tiet 12 thang deu ra 0.\n"
              "Rui ro: model doc 0 thanh 'dia ban khong ban duoc gi' thay vi 'khong co du lieu'."
              % (len(thieu_han), ", ".join(thieu_han)))


def kiem_4_nang_suat_khong_cong_lan_tang():
    """Cong lan tang TDV va tang QLV lam so gap doi - da dinh 3 cho trong du an. Tong theo mien,
    theo QLV va toan bo deu phai ra cung mot con so."""
    print()
    print("4. NANG SUAT: TONG THEO MIEN == THEO QLV == TOAN BO")
    ket = {}
    for nhom in ("area", "manager", "total"):
        r = rt.workforce_productivity(months_back=6, group_by=nhom, limit=1000)
        if r.get("error") or r.get("not_applicable"):
            return _bo("nang suat theo %s" % nhom, r.get("error", "khong ap dung"))
        theo_thang = {}
        for row in r["rows"]:
            theo_thang[row["month"]] = theo_thang.get(row["month"], 0.0) + (row["actual"] or 0)
        ket[nhom] = theo_thang
    for thang in sorted(ket["total"]):
        a, m, t = ket["area"].get(thang, 0), ket["manager"].get(thang, 0), ket["total"][thang]
        _kiem("thang %s" % thang, abs(a - t) < 1 and abs(m - t) < 1,
              None if abs(a - t) < 1 and abs(m - t) < 1 else
              "mien: %s | QLV: %s | toan bo: %s" % (_tien(a), _tien(m), _tien(t)))


def kiem_5_vong_doi_khach_co_bao_nhieu_khach_khong_mang_co():
    """customer_lifecycle_summary dem khach theo CO is_nc/is_ro/is_ac trong fact_tonghopkhachhang.
    Da biet truoc (24/08): 646 khach co doanh thu nhung KHONG mang co nao, is_ac chi 44/6.859. Da
    hoi DNH, CHUA co xac nhan ngu nghia.

    Kiem nay DINH LUONG muc do, khong ket luan ben nao dung. Neu ty le khach khong mang co lon thi
    moi cau tra loi dang "thang nay co X khach moi" deu dang bo sot mot mang lon ma khong noi ra -
    va con so X van trong hoan toan hop ly."""
    print()
    print("5. VONG DOI KHACH: BAO NHIEU KHACH KHONG MANG CO NAO")
    vd = rt.customer_lifecycle_summary(months_back=3)
    if vd.get("error") or vd.get("not_applicable"):
        return _bo("vong doi khach", vd.get("error", "khong ap dung"))
    co_du = [m for m in vd.get("months", []) if not m.get("khong_co_du_lieu")]
    if not co_du:
        return _bo("vong doi khach", "Khong thang nao co snapshot KPI.")
    for m in co_du:
        tong = m["tong_khach"]
        khong_co = m["khach_khong_mang_co"]
        ty_le = khong_co / tong * 100 if tong else 0
        # Nguong 20%: duoi muc nay thi "khach hien huu khong mang co" con giai thich duoc; tren muc
        # nay thi co gan nhu chac chan khong mang y nghia ta dang gia dinh.
        _kiem("thang %s: ty le khach khong mang co < 20%%" % m["month"], ty_le < 20,
              "tong %s khach | khong mang co %s (%.1f%%) | moi %s | is_ro %s | is_ac %s\n"
              "Ty le cao = ngu nghia co CHUA dung nhu gia dinh. CAN DNH XAC NHAN, khong tu suy."
              % (format(tong, ","), format(khong_co, ","), ty_le,
                 format(m["khach_moi"], ","), format(m["so_is_ro"], ","), format(m["so_is_ac"], ",")))
        # Bat bien so hoc: cac nhom con khong duoc vuot tong.
        _kiem("thang %s: cac nhom con khong vuot tong" % m["month"],
              m["khach_moi"] <= tong and m["so_is_ro"] <= tong and khong_co <= tong,
              None if m["khach_moi"] <= tong else "moi %s > tong %s" % (m["khach_moi"], tong))


def main():
    print("=" * 78)
    print("DOI CHIEU DO DUNG CUA SO - CAC TOOL MOI (khong goi API, khong dung Bravo)")
    print("=" * 78)
    # In duong dan THAT ma cac tool dang truy van, kem kich thuoc - de nhin mot cai la biet co dang
    # doi chieu tren kho rong/kho test hay khong.
    co = KHO_THUC_TE.stat().st_size if KHO_THUC_TE.is_file() else 0
    print("  Kho du lieu THAT dang truy van: %s" % KHO_THUC_TE)
    print("  Kich thuoc: %s MB" % (format(co / 1024 / 1024, ",.1f") if co else "0 (KHONG TON TAI)"))
    env = os.environ.get("DNH_BACKEND_DIR")
    if env and Path(env).resolve() != KHO_THUC_TE.parent.resolve():
        print("  CANH BAO: bien moi truong DNH_BACKEND_DIR=%s TRO KHAC noi kho that nam." % env)
        print("            Da bo qua bien nay - lay theo local_warehouse.DB_PATH.")
    if co < 1024 * 1024:
        print("  CANH BAO: kho nho bat thuong - gan nhu chac chan la ban test/rong, khong phai production.")
    for ham in (kiem_1_hai_nguon_khong_chong_lan, kiem_2_chuoi_thang_khop_mot_lan_goi,
                kiem_3_dia_ban_cong_lai_bang_toan_cong_ty, kiem_4_nang_suat_khong_cong_lan_tang,
                kiem_5_vong_doi_khach_co_bao_nhieu_khach_khong_mang_co):
        try:
            ham()
        except Exception as e:
            # Kho MAU tren may dev thieu bang/cot so voi kho that tren may 24 - do la gioi han cua
            # noi chay, KHONG phai bat bien bi vi pham. Gop chung vao "lech" se tao bao dong gia va
            # lam nguoi doc quen di canh giac voi bao dong that.
            thieu_schema = "no such column" in str(e) or "no such table" in str(e)
            print()
            if thieu_schema:
                _bo(ham.__name__, "Kho o day thieu bang/cot (%s) - chay lai tren may co du lieu that." % e)
            else:
                print("  [VO  ] %s: %s" % (ham.__name__, e))
                _loi.append(ham.__name__)

    print()
    print("=" * 78)
    if _loi:
        print("CO %d CHO LECH - can dieu tra truoc khi tin so:" % len(_loi))
        for t in _loi:
            print("   - %s" % t)
    elif not _bo_qua:
        print("MOI BAT BIEN DEU GIU.")
    if _bo_qua:
        print("Bo qua %d muc (khong du du lieu de kiem): %s" % (len(_bo_qua), ", ".join(_bo_qua)))
    # 26/08/2026: TUYET DOI khong duoc bao "MOI BAT BIEN DEU GIU" khi khong kiem duoc gi. Lan chay dau
    # tren may 24 trung kho TEST rong, ca 5 muc deu bi bo qua, va script van in dong xanh do - mot
    # ket luan trang tren kho rong, y het loai loi ma chinh script nay sinh ra de bat.
    if not _loi and _bo_qua:
        print()
        print("KHONG KIEM DUOC GI: ca %d/%d muc deu bi bo qua." % (len(_bo_qua), len(_bo_qua)))
        print("Day KHONG phai ket qua dat - chi la khong co du lieu de kiem. Xem lai dong")
        print("'Kho du lieu THAT dang truy van' o dau ra tren: rat co the dang tro vao ban test.")
    print("=" * 78)
    return 1 if (_loi or _bo_qua) else 0


if __name__ == "__main__":
    raise SystemExit(main())
