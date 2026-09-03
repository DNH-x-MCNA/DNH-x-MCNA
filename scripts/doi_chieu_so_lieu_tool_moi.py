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
_dat = [0]  # dem so phep kiem THUC SU chay va dat - de dong tong ket khong noi qua muc bang chung


def _kiem(ten, dat, chi_tiet=""):
    print("  [%s] %s" % ("DAT " if dat else "LECH", ten))
    if chi_tiet:
        for dong in str(chi_tiet).splitlines():
            print("         %s" % dong)
    if dat:
        _dat[0] += 1
    else:
        _loi.append(ten)


def _bo(ten, ly_do):
    print("  [BO  ] %s" % ten)
    print("         %s" % ly_do)
    _bo_qua.append(ten)


def _f0(x):
    """Doc so an toan tu ket qua tool: None / chuoi rong / kieu la deu ve 0 thay vi lam vo phep kiem.
    Mot phep kiem vo vi TypeError se bi ghi thanh "LECH" - tuc bao dong gia, dung thu lam nguoi doc
    quen mat canh giac voi bao dong that."""
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


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



# =======================================================================================
# 26/08/2026 - MO RONG SANG CAC TOOL CU
#
# Nam phep kiem tren chi phu 11 tool MOI. Nhung cac tool CU (doanh thu theo vung, top khach,
# top san pham, so sanh ky, cong no, cay KPI, xep hang) moi la thu nguoi dung cham vao nhieu
# nhat - va chua tung bi soi kieu nay. Ca ba lan dau nhat cua du an deu roi vao nhom nay.
# =======================================================================================

def _thang_tron_gan_nhat():
    """Thang TRON VEN gan nhat co du lieu. KHONG lay thang hien tai: no chua ket thuc nen moi con so
    deu la so do dang, rat de bi doc nham thanh 'sut giam'."""
    earliest, latest = rt._revenue_data_month_range()
    if not latest:
        return None, None, None
    hom_nay = rt.dt.date.today().strftime("%Y-%m")
    ym = rt._month_add(latest, -1) if latest >= hom_nay else latest
    if earliest and ym < earliest:
        ym = latest
    d_from, d_to = rt._month_bounds(ym)
    return ym, d_from, d_to


def kiem_6_doanh_thu_theo_vung_bang_tong_cong_ty():
    """revenue_by_region va revenue_by_channel di hai duong SQL khac nhau (mot ben GROUP BY vung qua
    join danh muc tinh, mot ben SUM thang) nhung PHAI ra cung mot tong. Lech = co khach roi am tham
    khi join - dung loai loi tung lam bay hoi 4 QLV that va 7,93 ty chi tieu Mien Nam."""
    print()
    print("6. DOANH THU THEO VUNG == TONG TOAN CONG TY")
    ym, d_from, d_to = _thang_tron_gan_nhat()
    if not ym:
        return _bo("doanh thu theo vung", "Kho chua co hoa don.")
    vung = rt.revenue_by_region(d_from, d_to)
    if not isinstance(vung, list) or not vung:
        return _bo("doanh thu theo vung", "revenue_by_region tra ve rong/khong phai danh sach.")
    tong_vung = sum(_f0(r.get("revenue")) for r in vung)
    tong_cty = rt.revenue_by_channel(d_from, d_to)["total"]["revenue"]
    lech = abs(tong_vung - tong_cty)
    _kiem("thang %s: cong cac vung == tong cong ty" % ym, lech < 1,
          "theo vung: %s | toan cong ty: %s | lech %s dong (%.4f%%)"
          % (_tien(tong_vung), _tien(tong_cty), _tien(lech),
             lech / tong_cty * 100 if tong_cty else 0))


def kiem_7_top_khach_cong_lai_bang_tong():
    """top_customers voi limit rat lon phai cong lai bang dung tong cong ty. Day la phep bat khach
    "mo coi" (co hoa don nhung khong co trong danh muc khach) bi INNER JOIN loai bo - loi tung lam
    mat ~2,3 ty doanh thu THAT ma khong co dau hieu bao truoc nao."""
    print()
    print("7. TONG TAT CA KHACH == TONG TOAN CONG TY")
    ym, d_from, d_to = _thang_tron_gan_nhat()
    if not ym:
        return _bo("top khach", "Kho chua co hoa don.")
    khach = rt.top_customers(d_from, d_to, limit=1000000)
    if not isinstance(khach, list) or not khach:
        return _bo("top khach", "top_customers tra ve rong.")
    tong_khach = sum(_f0(r.get("revenue")) for r in khach)
    tong_cty = rt.revenue_by_channel(d_from, d_to)["total"]["revenue"]
    lech = abs(tong_khach - tong_cty)
    _kiem("thang %s: cong %s khach == tong cong ty" % (ym, format(len(khach), ",")), lech < 1,
          "cong khach: %s | toan cong ty: %s | lech %s dong (%.4f%%)"
          % (_tien(tong_khach), _tien(tong_cty), _tien(lech),
             lech / tong_cty * 100 if tong_cty else 0))


def kiem_8_top_san_pham_cong_lai_bang_tong():
    """top_products KHONG bu duoc tu bang nen (bang nen khong giu item_code) nen chi kiem duoc trong
    cua so hoa don chi tiet. Trong cua so do thi tong san pham phai bang tong cong ty."""
    print()
    print("8. TONG TAT CA SAN PHAM == TONG TOAN CONG TY (trong cua so chi tiet)")
    ym, d_from, d_to = _thang_tron_gan_nhat()
    if not ym:
        return _bo("top san pham", "Kho chua co hoa don.")
    if d_from < rt._detail_cutoff():
        return _bo("top san pham", "Thang %s nam ngoai cua so hoa don chi tiet - khong kiem duoc." % ym)
    sp = rt.top_products(d_from, d_to, limit=1000000)
    ds = sp.get("products") if isinstance(sp, dict) else sp
    if not isinstance(ds, list) or not ds:
        return _bo("top san pham", "top_products tra ve rong.")
    tong_sp = sum(_f0(r.get("revenue")) for r in ds)
    tong_cty = rt.revenue_by_channel(d_from, d_to)["total"]["revenue"]
    lech = abs(tong_sp - tong_cty)
    _kiem("thang %s: cong %s san pham == tong cong ty" % (ym, format(len(ds), ",")), lech < 1,
          "cong san pham: %s | toan cong ty: %s | lech %s dong (%.4f%%)"
          % (_tien(tong_sp), _tien(tong_cty), _tien(lech),
             lech / tong_cty * 100 if tong_cty else 0))


def kiem_9_so_sanh_ky_khop_voi_tra_cuu_truc_tiep():
    """compare_periods phai cho ky A dung bang revenue_by_channel(ky A) tra cuu thang. Lech = duong
    ong truyen tham so bi hoan doi/xe dich - loai loi KHONG the phat hien tu cau tra loi, vi ca hai
    con so deu "trong hop ly"."""
    print()
    print("9. SO SANH KY: KY A == TRA CUU TRUC TIEP KY A")
    ym, d_from, d_to = _thang_tron_gan_nhat()
    if not ym:
        return _bo("so sanh ky", "Kho chua co hoa don.")
    truoc = rt._month_add(ym, -1)
    p_from, p_to = rt._month_bounds(truoc)
    ss = rt.compare_periods(d_from, d_to, p_from, p_to)
    a, b = ss.get("period_a"), ss.get("period_b")
    if not isinstance(a, dict) or not isinstance(b, dict):
        return _bo("so sanh ky", "compare_periods tra ve hinh dang la: %s" % sorted(ss.keys()))

    def _lay(x):
        if isinstance(x.get("total"), dict):
            return _f0(x["total"].get("revenue"))
        return _f0(x.get("revenue"))

    thang_a = rt.revenue_by_channel(d_from, d_to)["total"]["revenue"]
    thang_b = rt.revenue_by_channel(p_from, p_to)["total"]["revenue"]
    _kiem("ky A (%s) khop tra cuu truc tiep" % ym, abs(_lay(a) - thang_a) < 1,
          "so sanh: %s | truc tiep: %s" % (_tien(_lay(a)), _tien(thang_a)))
    _kiem("ky B (%s) khop tra cuu truc tiep" % truoc, abs(_lay(b) - thang_b) < 1,
          "so sanh: %s | truc tiep: %s" % (_tien(_lay(b)), _tien(thang_b)))


def kiem_10_cong_no_cac_cach_chia_deu_bang_tong():
    """Cong no la cho tung sai NANG NHAT trong du an (cong thuc cu thoi 4-15 lan). Chia theo kenh va
    chia theo vung deu phai cong lai bang tong; tong qua han khong duoc vuot tong du no."""
    print()
    print("10. CONG NO: CHIA THEO KENH == CHIA THEO VUNG == TONG")
    cn = rt.receivables_overview(top_n=5)
    if cn.get("receivable_status") == "unavailable":
        return _bo("cong no", cn.get("receivable_warning", "khong tra cuu duoc"))
    tong = _f0(cn.get("total_balance_end"))
    if not tong:
        return _bo("cong no", "Tong du no bang 0 - khong co gi de doi chieu.")
    theo_kenh = sum(_f0(r.get("balance_end")) for r in (cn.get("by_channel") or []))
    theo_vung = sum(_f0(r.get("balance_end")) for r in (cn.get("by_region") or []))
    _kiem("cong theo kenh == tong du no", abs(theo_kenh - tong) < 1,
          "theo kenh: %s | tong: %s | lech %s"
          % (_tien(theo_kenh), _tien(tong), _tien(abs(theo_kenh - tong))))
    _kiem("cong theo vung == tong du no", abs(theo_vung - tong) < 1,
          "theo vung: %s | tong: %s | lech %s"
          % (_tien(theo_vung), _tien(tong), _tien(abs(theo_vung - tong))))
    _kiem("tong qua han khong vuot tong du no", _f0(cn.get("total_overdue")) <= tong + 1,
          "qua han: %s | du no: %s" % (_tien(_f0(cn.get("total_overdue"))), _tien(tong)))


def kiem_11_cay_kpi_khong_cong_lan_tang():
    """revenue_tree co 3 tang TP -> QLV -> TDV. Bravo TU rollup san cho tang QLV, nen sales cua mot
    QLV va tong sales cac TDV duoi no la HAI NGUON DOC LAP - doi chieu duoc. Cong lan hai tang lam so
    gap doi da dinh 3 lan trong du an, lan nao cau tra loi cung trong hoan toan hop ly.

    26/08/2026 - PHIEN BAN DAU BAO DONG GIA: no so THANG tong rollup QLV voi tong TDV va bao lech
    30,6% (10,96 ty). Doc ky thi ca 10,92 ty trong so do nam o DUNG BA nut ma TOOL DA TU DANH DAU:
      - "Kenh MT" va "Cho si": la_nhom_kenh=True, code CO Y gan team=[] vi day la nhom kenh ban hang
        chu khong phai mot ca nhan co doi TDV;
      - "Nguyen Thi Thanh Thuy" (MBKV12): ca ghi nhan tu 21/07/2026 (muc A4,
        Cau_hoi_can_DNH_xac_nhan.md) - nghi Bravo luu 2 ban ghi cho cung mot nguoi (1 cap TP, 1 cap
        QLV voi 0 TDV), tool da gan san ghi_chu canh bao.
    Tuc tool VON DA DUNG; phep kiem moi la thu sai. Mot phep kiem luon do vi nhung ca da duoc xu ly
    dung thi chi day nguoi doc toi cho bo qua no - nguy hiem hon la khong co phep kiem nao.

    Nay: loai cac nut da mang la_nhom_kenh hoac ghi_chu ra khoi phep so (van bao ra de con thay), chi
    do phan CHUA duoc giai thich. Do lai tren du lieu that 26/08: 0,13% - dat."""
    print()
    print("11. CAY KPI: ROLLUP QLV CUA BRAVO == TONG TDV DUOI QUYEN")
    cay = rt.revenue_tree()
    if cay.get("error") or not cay.get("tree"):
        return _bo("cay KPI", cay.get("error", "cay rong"))
    tong_qlv = tong_tdv = 0.0
    da_danh_dau = []
    lech_nhieu = []
    so_qlv = 0
    for tp in cay["tree"]:
        for qlv in (tp.get("qlv") or []):
            ten = qlv.get("name") or qlv.get("employee_code")
            s_qlv = _f0(qlv.get("sales"))
            s_tdv = sum(_f0(t.get("sales")) for t in (qlv.get("tdv") or []))
            # Nut da co canh bao san = ca DA BIET va DA duoc tool noi ro cho nguoi dung. Dua vao phep
            # so chi tao bao dong lap lai cho thu khong con phai phat hien nua.
            if qlv.get("la_nhom_kenh") or qlv.get("ghi_chu"):
                da_danh_dau.append((ten, s_qlv, s_tdv,
                                    "nhom kenh" if qlv.get("la_nhom_kenh") else "co ghi_chu canh bao"))
                continue
            so_qlv += 1
            tong_qlv += s_qlv
            tong_tdv += s_tdv
            if s_qlv and abs(s_qlv - s_tdv) / s_qlv > 0.01:
                lech_nhieu.append((abs(s_qlv - s_tdv), ten, s_qlv, s_tdv))
    if da_danh_dau:
        print("         %d nut BI LOAI khoi phep so vi tool da danh dau san:" % len(da_danh_dau))
        for ten, a, b, ly_do in da_danh_dau:
            print("           %-28s rollup %-18s TDV %-14s (%s)"
                  % (str(ten)[:28], _tien(a), _tien(b), ly_do))
    if not so_qlv:
        return _bo("cay KPI", "Khong con QLV nao sau khi loai cac nut da danh dau.")
    lech_tong = abs(tong_qlv - tong_tdv)
    ty_le = lech_tong / tong_qlv * 100 if tong_qlv else 0
    # Nguong 1%: rollup cua Bravo va tong chi tiet co the lech chut it do lam tron/do tre snapshot.
    # Con neu cong lan hai tang thi se ra khoang 100%, khong the lot qua nguong nay.
    _kiem("tong %d QLV (da loai nut danh dau) == tong TDV duoi quyen (nguong 1%%)" % so_qlv, ty_le < 1,
          "rollup QLV: %s | cong TDV: %s | lech %s dong (%.3f%%)"
          % (_tien(tong_qlv), _tien(tong_tdv), _tien(lech_tong), ty_le))
    if lech_nhieu:
        lech_nhieu.sort(reverse=True)
        print("         %d QLV con lech >1%% giua rollup va chi tiet, nang nhat:" % len(lech_nhieu))
        for d, ten, a, b in lech_nhieu[:5]:
            print("           %-28s rollup %s vs cong TDV %s" % (str(ten)[:28], _tien(a), _tien(b)))


def kiem_12_xep_hang_kpi_hai_cach_gom_bang_nhau():
    """kpi_ranking gom theo QLV va gom theo vung phai cho cung mot tong doanh so - lech nghia la mot
    trong hai duong dang bo sot hoac dem trung mot nhom."""
    print()
    print("12. XEP HANG KPI: GOM THEO QLV == GOM THEO VUNG")
    theo_qlv = rt.kpi_ranking(group_by="qlv", limit=1000)
    theo_vung = rt.kpi_ranking(group_by="region", limit=1000)
    if not isinstance(theo_qlv, list) or not isinstance(theo_vung, list) or not theo_qlv:
        return _bo("xep hang KPI", "kpi_ranking tra ve rong.")
    khoa = None
    for ung_vien in ("sales", "actual", "revenue"):
        if ung_vien in theo_qlv[0]:
            khoa = ung_vien
            break
    if not khoa:
        return _bo("xep hang KPI",
                   "Khong tim thay cot doanh so trong ket qua: %s" % sorted(theo_qlv[0].keys()))
    a = sum(_f0(r.get(khoa)) for r in theo_qlv)
    b = sum(_f0(r.get(khoa)) for r in theo_vung)
    lech = abs(a - b)
    _kiem("gom %d QLV == gom %d vung" % (len(theo_qlv), len(theo_vung)), lech < 1,
          "theo QLV: %s | theo vung: %s | lech %s dong (%.3f%%)"
          % (_tien(a), _tien(b), _tien(lech), lech / a * 100 if a else 0))


def _mau_dau_tien(sql, params=()):
    """Lấy một giá trị mẫu; thiếu bảng/cột thì trả None để checker ghi BỎ, không giả vờ đạt."""
    try:
        rows = _wq(sql, params)
        return next(iter(dict(rows[0]).values())) if rows else None
    except Exception:
        return None


def _ly_do_khong_co_payload(result):
    """Trả lý do nếu tool chưa tạo được kết quả có thể kiểm trên kho hiện tại.

    Một dict chỉ có warning/note không được tính là đã kiểm. Kết quả số 0 vẫn hợp lệ nếu tool có
    mốc dữ liệu/snapshot rõ ràng; còn list rỗng thì phải BỎ vì không có dòng nào để đối chiếu.
    """
    if result is None:
        return "tool tra ve None"
    if isinstance(result, list):
        return None if result else "danh sach rong"
    if not isinstance(result, dict):
        return "sai kieu ket qua: %s" % type(result).__name__
    if result.get("error"):
        return str(result["error"])
    if result.get("not_applicable"):
        return str(result.get("reason") or result.get("warning") or "khong ap dung")
    for key in ("receivable_status", "status", "data_status"):
        if str(result.get(key, "")).lower() in {"unavailable", "not_available", "missing"}:
            return str(result.get("warning") or result.get("receivable_warning") or result[key])
    # Dữ liệu có thể nằm trong list/dict lồng nhau hoặc là các tổng số. Không dùng chuỗi ghi chú
    # làm bằng chứng vì một tool chỉ trả lời "không có dữ liệu" vẫn có rất nhiều text.
    def co_du_lieu(value):
        if isinstance(value, list):
            return bool(value)
        if isinstance(value, dict):
            return any(co_du_lieu(v) for v in value.values())
        if isinstance(value, (int, float)):
            return value != 0
        return False
    if co_du_lieu(result):
        return None
    # Một số báo cáo chất lượng hợp lệ có toàn bộ bộ đếm = 0. Chỉ chấp nhận nếu có mốc snapshot
    # thật; như vậy không biến một dict rỗng/ghi chú thành kết luận xanh.
    if any(result.get(k) for k in ("snapshot_date", "as_of_date", "date_from", "month", "year_month")):
        return None
    return "khong co dong/tong so hay moc snapshot de doi chieu"


def _tool_cases_40():
    """Một ca smoke/contract cho đúng 40 tool nghiệp vụ, toàn bộ chỉ đọc kho local."""
    ym, d_from, d_to = _thang_tron_gan_nhat()
    if not ym:
        ym, d_from, d_to = "2026-07", "2026-07-01", "2026-07-31"
    p_ym = rt._month_add(ym, -1)
    p_from, p_to = rt._month_bounds(p_ym)
    customer = (_mau_dau_tien(
        "SELECT customer_code FROM vhoadon_otc WHERE doc_date BETWEEN ? AND ? "
        "AND customer_code IS NOT NULL LIMIT 1", (d_from, d_to)) or "KHONG_CO_MAU")
    employee = (_mau_dau_tien(
        "SELECT employee_code FROM dim_nhanvien WHERE employee_code IS NOT NULL "
        "AND position_code IN ('TDV','CTV','CS') LIMIT 1") or "KHONG_CO_MAU")
    debt_dates = []
    try:
        debt_dates = [r["d"] for r in _wq(
            "SELECT DISTINCT snapshot_date d FROM fact_congno_khachhang "
            "WHERE snapshot_date IS NOT NULL ORDER BY d DESC LIMIT 2")]
    except Exception:
        pass
    debt_a = debt_dates[0] if debt_dates else d_to
    debt_b = debt_dates[1] if len(debt_dates) > 1 else p_to

    return {
        "get_revenue_by_channel": ({"date_from": d_from, "date_to": d_to}, dict),
        "get_top_products": ({"date_from": d_from, "date_to": d_to, "limit": 10}, list),
        "get_top_customers": ({"date_from": d_from, "date_to": d_to, "limit": 10}, list),
        "get_revenue_by_region": ({"date_from": d_from, "date_to": d_to}, list),
        "get_revenue_ytd_cumulative": ({"year_month_to": ym}, dict),
        "get_revenue_monthly_series": ({"month_to": ym, "months_back": 3, "include_yoy": False}, dict),
        "get_customer_lifecycle_summary": ({"year_month": ym, "months_back": 1}, dict),
        "get_customers_silent": ({"as_of_date": d_to, "limit": 10}, dict),
        "get_customer_cohort_retention": ({"month_to": ym, "months_back": 3}, dict),
        "get_customer_movement": ({"month": ym, "limit": 10}, dict),
        "get_kpi_gap_run_rate": ({"as_of_date": d_to, "limit": 10}, dict),
        "get_cross_sell_opportunities": ({"as_of_date": d_to, "pair_limit": 5, "opportunity_limit": 10}, dict),
        "get_customer_product_coverage": ({"as_of_date": d_to, "limit": 10}, dict),
        "get_geography_monthly_performance": ({"month_to": ym, "months_back": 3, "limit": 20}, dict),
        "get_workforce_productivity": ({"month_to": ym, "months_back": 3, "limit": 20}, dict),
        "get_operational_data_quality": ({"as_of_date": d_to, "sample_limit": 10}, dict),
        "get_employee_kpi": ({"as_of_date": d_to, "limit": 10}, dict),
        "get_employee_daily_kpi": ({"employee_code": employee, "year_month": ym}, dict),
        "compare_periods": ({"date_from_a": d_from, "date_to_a": d_to,
                             "date_from_b": p_from, "date_to_b": p_to}, dict),
        "get_customer_detail": ({"customer_code": customer, "date_from": d_from, "date_to": d_to}, dict),
        "get_employee_directory": ({"limit": 10}, list),
        "check_order_timing": ({"date_from": d_from, "date_to": d_to, "limit": 10}, dict),
        "get_inventory_by_region": ({}, list),
        "get_inventory_expiry_report": ({"limit": 10}, dict),
        "get_qlv_change_history": ({}, list),
        "get_revenue_tree": ({"as_of_date": d_to}, dict),
        "get_kpi_ranking": ({"as_of_date": d_to, "limit": 20}, list),
        "get_revenue_reconciliation": ({"as_of_date": d_to}, dict),
        "get_receivables_overview": ({"top_n": 10}, dict),
        "get_receivables_period_compare": ({"snapshot_date_a": debt_a, "snapshot_date_b": debt_b}, dict),
        "get_receivables_history_dates": ({"limit": 10}, dict),
        "get_customer_revenue_debt_risk": ({"as_of_date": d_to, "limit": 10}, dict),
        "get_audit_log": ({"days": 30, "limit": 10, "scope_role": "c_level"}, dict),
        "get_promotion_effectiveness": ({"date_from": d_from, "date_to": d_to, "limit": 10}, dict),
        "get_promotion_data_quality": ({}, dict),
        "get_salary_bonus_policy": ({"bonus_type": "v25", "as_of_date": d_to, "scope_role": "c_level"}, dict),
        "get_salary_data_quality": ({"check_type": "dm_reconciliation", "year_month": ym,
                                     "scope_role": "c_level"}, dict),
        "get_salary_detail": ({"employee_code": employee, "scope_role": "c_level"}, dict),
        "get_salary_achievement_summary": ({"save_date": d_to, "scope_role": "c_level"}, dict),
        "get_salary_ranking": ({"year_month": ym, "limit": 10, "scope_role": "c_level"}, dict),
    }


def kiem_13_phu_du_40_tool_nghiep_vu():
    print()
    print("13. SMOKE/CONTRACT CHO TOAN BO 40 TOOL NGHIEP VU")
    cases = _tool_cases_40()
    registered = set(rt.TEMPLATES)
    configured = set(cases)
    _kiem("catalog ca kiem phu dung 40/40 tool", len(cases) == 40 and configured == registered,
          "configured=%d | registered=%d | thieu=%s | thua=%s"
          % (len(cases), len(registered), sorted(registered - configured), sorted(configured - registered)))
    for name in sorted(registered):
        kwargs, expected_type = cases[name]
        try:
            result = rt.TEMPLATES[name](**kwargs)
        except Exception as exc:
            # Kho dev duoc phep nho hon kho production. Thieu schema la gioi han cua noi chay,
            # khong phai tool tra sai; ghi BO de van bat buoc chay lai tren may 24.
            if "no such column" in str(exc) or "no such table" in str(exc):
                _bo(name, "Kho o day thieu bang/cot (%s) - chay lai tren may co du lieu that." % exc)
                continue
            _kiem("%s: goi duoc khong vo" % name, False, str(exc))
            continue
        if not isinstance(result, expected_type):
            _kiem("%s: dung kieu ket qua" % name, False,
                  "mong %s, nhan %s" % (expected_type.__name__, type(result).__name__))
            continue
        ly_do = _ly_do_khong_co_payload(result)
        if ly_do:
            _bo(name, ly_do)
            continue
        _kiem("%s: co payload de doi chieu" % name, True)


CAC_PHEP_KIEM = (
    kiem_1_hai_nguon_khong_chong_lan,
    kiem_2_chuoi_thang_khop_mot_lan_goi,
    kiem_3_dia_ban_cong_lai_bang_toan_cong_ty,
    kiem_4_nang_suat_khong_cong_lan_tang,
    kiem_5_vong_doi_khach_co_bao_nhieu_khach_khong_mang_co,
    kiem_6_doanh_thu_theo_vung_bang_tong_cong_ty,
    kiem_7_top_khach_cong_lai_bang_tong,
    kiem_8_top_san_pham_cong_lai_bang_tong,
    kiem_9_so_sanh_ky_khop_voi_tra_cuu_truc_tiep,
    kiem_10_cong_no_cac_cach_chia_deu_bang_tong,
    kiem_11_cay_kpi_khong_cong_lan_tang,
    kiem_12_xep_hang_kpi_hai_cach_gom_bang_nhau,
    kiem_13_phu_du_40_tool_nghiep_vu,
)


def main():
    print("=" * 78)
    print("DOI CHIEU DO DUNG CUA SO - CAC TOOL MOI (khong goi API, khong dung Bravo)")
    print("=" * 78)
    # In duong dan THAT ma cac tool dang truy van, kem kich thuoc - de nhin mot cai la biet co dang
    # doi chieu tren kho rong/kho test hay khong.
    co = KHO_THUC_TE.stat().st_size if KHO_THUC_TE.is_file() else 0
    # 26/08/2026: script phai TU KHAI BAO phien ban cua chinh no. Da bi nham 3 lan trong mot ngay
    # theo 3 kieu khac nhau ("code nao dang chay?"), lan gan nhat: ban tren may 24 con la ban cu chi
    # co 5 phep kiem, dau ra dung o muc 5 va in ket luan xanh - nhin thoang y het mot lan chay day du.
    # So phep kiem la dau hieu re nhat va kho nham nhat: 5 hay 12 la thay ngay.
    print("  Ban script: %d nhom kiem, phu %d tool | sua lan cuoi %s"
          % (len(CAC_PHEP_KIEM), len(_tool_cases_40()),
             __import__("datetime").datetime.fromtimestamp(
                 Path(__file__).stat().st_mtime).strftime("%d/%m/%Y %H:%M")))
    print("  Kho du lieu THAT dang truy van: %s" % KHO_THUC_TE)
    print("  Kich thuoc: %s MB" % (format(co / 1024 / 1024, ",.1f") if co else "0 (KHONG TON TAI)"))
    env = os.environ.get("DNH_BACKEND_DIR")
    if env and Path(env).resolve() != KHO_THUC_TE.parent.resolve():
        print("  CANH BAO: bien moi truong DNH_BACKEND_DIR=%s TRO KHAC noi kho that nam." % env)
        print("            Da bo qua bien nay - lay theo local_warehouse.DB_PATH.")
    if co < 1024 * 1024:
        print("  CANH BAO: kho nho bat thuong - gan nhu chac chan la ban test/rong, khong phai production.")
    for ham in CAC_PHEP_KIEM:
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
    # 26/08/2026 - hai lan phai sua dong tong ket nay, ca hai deu vi no NOI QUA MUC bang chung:
    #   lan 1: bao "MOI BAT BIEN DEU GIU" trong khi ca 5 muc deu bi bo qua tren mot kho rong;
    #   lan 2: bao "KHONG KIEM DUOC GI: ca 5/5 muc bi bo qua" trong khi 3 phep kiem da chay va DAT -
    #          cong thuc cu lay len(_bo_qua) lam ca tu va mau nen luon ra 100%.
    # Nay bam vao DEM THAT: bao nhieu phep kiem chay va dat, bao nhieu lech, bao nhieu khong chay duoc.
    if _loi:
        print("CO %d CHO LECH - can dieu tra truoc khi tin so:" % len(_loi))
        for t in _loi:
            print("   - %s" % t)
    if _bo_qua:
        print("Khong chay duoc %d muc: %s" % (len(_bo_qua), ", ".join(_bo_qua)))

    print()
    print("Da chay: %d phep kiem DAT, %d LECH, %d muc khong chay duoc."
          % (_dat[0], len(_loi), len(_bo_qua)))
    if not _dat[0]:
        print("KHONG PHEP KIEM NAO CHAY DUOC - day KHONG phai ket qua dat. Xem lai dong")
        print("'Kho du lieu THAT dang truy van' o tren: rat co the dang tro vao ban test/kho rong.")
    elif not _loi and not _bo_qua:
        print("MOI BAT BIEN DEU GIU.")
    elif not _loi:
        print("Cac phep kiem CHAY DUOC deu giu. Nhung con %d muc chua kiem - chua the ket luan"
              " toan bo." % len(_bo_qua))
    print("=" * 78)
    # Ma thoat khac 0 khi co cho lech HOAC con muc chua kiem duoc: "chua kiem het" khong duoc phep
    # trong giong "da kiem xong va sach" trong CI hay trong mat nguoi doc luot.
    return 1 if (_loi or _bo_qua) else 0


if __name__ == "__main__":
    raise SystemExit(main())
