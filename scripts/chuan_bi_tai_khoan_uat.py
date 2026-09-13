"""Chuẩn bị bộ tài khoản UAT từ TÀI KHOẢN ĐÃ CÓ, phủ đủ các case theo vai trò/vùng/kênh.

Chạy trên máy có auth.db THẬT (máy 24). Bốn bước, mỗi bước gọi riêng:

  1. python scripts/chuan_bi_tai_khoan_uat.py
       Chỉ đọc. In trạng thái hiện tại của từng tài khoản trong bộ test, so với cấu hình đúng,
       và báo trước tài khoản nào sẽ bị chặn 403 khi tester đăng nhập hỏi.
  2. python scripts/chuan_bi_tai_khoan_uat.py --sua-pham-vi
       Gán lại role/vùng/kênh/mã NV cho tài khoản đang sai. Dùng đúng approve_user() của trang
       quản trị (có kiểm hợp lệ). Nguyên nhân sai thường gặp: trước 13/08/2026 mỗi lần khởi động
       backend tự ép mọi tài khoản không phải manager_* thành qlv (xem auth.migrate_and_seed_users).
  3. python scripts/chuan_bi_tai_khoan_uat.py --tao-moi
       Tạo các tài khoản test chưa có trong danh sách 13/08 (dnh_etc, head.mt, chosi.mb, chosi.mn),
       in mật khẩu một lần. Chỉ tạo mục đánh dấu tao_moi, không tạo lại tài khoản thật bị thiếu.
  4. python scripts/chuan_bi_tai_khoan_uat.py --cap-mk danh.nguyen,dung.bui
       Đặt mật khẩu tạm cho đúng các tài khoản chỉ định, thu hồi mọi phiên cũ, in mật khẩu MỘT LẦN
       ra terminal. Từ chối tài khoản đã từng đăng nhập (có thể là người thật đang dùng) trừ khi
       thêm --ke-ca-da-dang-nhap.

Mật khẩu: không ghi file, không ghi log, không đưa vào Git, không dán vào chat. Chép từ terminal
và gửi riêng cho người test.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))

import auth  # noqa: E402

DEFAULT_DB = BACKEND / "auth.db"

# Bộ test chọn từ danh sách tài khoản xuất ngày 13/08/2026 (25 tài khoản). Mã NV/vùng đối chiếu
# dim_nhanvien và _team_of_qlv() ngày 11/09/2026: mọi QLV dưới đây phân giải đủ đội, không hụt.
BO_TEST = [
    dict(username="admin.dnh", role="admin_ops",
         case="Admin vận hành (quản trị tài khoản, không chat)", nguon="Danh sách 13/08"),
    dict(username="dnh", role="c_level",
         case="C-Level, toàn công ty", nguon="Đã dùng UAT C01-C54"),
    dict(username="dnh_etc", role="regional_director", scope_channel="ETC", tao_moi=True,
         ten="DNH ETC - Giám đốc kênh ETC",
         case="Giám đốc kênh ETC (theo kênh, toàn quốc)", nguon="Bảng tài khoản test 11/09"),
    dict(username="dnh_otc", role="regional_director", scope_channel="OTC",
         case="Giám đốc kênh OTC (theo kênh, toàn quốc)",
         nguon="13/08 đang là qlv kênh OTC, thiếu vùng/mã NV -> bị chặn; sửa bằng --sua-pham-vi"),
    dict(username="thuy.nguyen2", role="regional_director", scope_value="MB",
         case="Giám đốc Miền Bắc (theo vùng)", nguon="Đã dùng UAT M01-M44"),
    dict(username="hung.le", role="regional_director", scope_value="MT",
         case="Giám đốc Miền Trung (theo vùng)", nguon="Bravo: Lê Văn Hưng, TP, mã NV 'MT'"),
    dict(username="tung.tran", role="regional_director", scope_value="MN",
         case="Giám đốc Miền Nam (theo vùng)", nguon="Bravo: Trần Thanh Tùng, TP, mã NV 'MN'"),
    dict(username="tu.pham", role="qlv", scope_value="MB", employee_code="MBKV2",
         case="QLV Miền Bắc, đội 11 TDV (chuẩn)", nguon="Đã dùng UAT V01-V32"),
    dict(username="thuy.nguyen", role="qlv", scope_value="MB", employee_code="TM25010183",
         case="QLV Miền Bắc, đội 10 TDV",
         nguon="Đã dùng UAT V33-V40; kế hoạch 11-20/09 chốt MB + TM25010183"),
    dict(username="thuan.pham", role="qlv", scope_value="MT", employee_code="TM23110128",
         case="QLV Miền Trung, đội 7 TDV", nguon="Nhóm QLV MT từng bị lỗi trả 0 đồng 23/07"),
    dict(username="danh.nguyen", role="qlv", scope_value="MN", employee_code="TM23100148",
         case="QLV Miền Nam, đội 10 TDV", nguon="Đội lớn nhất Miền Nam"),
    dict(username="dung.bui", role="qlv", scope_value="MB", employee_code="MBKV1",
         case="QLV có đội bán cả ETC", nguon="MBKV1 có doanh thu ETC trên hóa đơn"),
    # Chưa có trong danh sách 13/08 - tạo mới bằng --tao-moi. Gắn theo MÃ QUẢN LÝ, không theo mã cá
    # nhân: _team_of_qlv(mã cá nhân TK/CS) ra đội rỗng và mọi tool doanh thu báo không xác định được
    # đội. Kênh MT (Modern Trade) chỉ có ở Miền Nam - vùng MN, không phải "MT" Miền Trung.
    dict(username="head.mt", role="qlv", scope_value="MN", employee_code="MN1", tao_moi=True,
         ten="Trưởng kênh MT (MN1)",
         case="Trưởng kênh MT (Modern Trade), 1 người TK",
         nguon="MN1 'Kênh MT' -> Dương Thị Hồng Huệ TM23100133; T8 5,11 tỷ = dòng target MT"),
    dict(username="chosi.mb", role="qlv", scope_value="MB", employee_code="MBKV12", tao_moi=True,
         ten="Chợ sỉ Miền Bắc (MBKV12)",
         case="Chợ sỉ Miền Bắc, 2 người CS",
         nguon="MBKV12 -> Thoa HN5, Giỏi HAPU; mã có is_duplicate=1 nhưng là người thật (ngoại lệ)"),
    dict(username="chosi.mn", role="qlv", scope_value="MN", employee_code="MN4", tao_moi=True,
         ten="Chợ sỉ Miền Nam (MN4)",
         case="Chợ sỉ Miền Nam, 1 người CS",
         nguon="MN4 'Chợ sỉ' -> Đặng Trường Lol TM23100153; T8 3,46 tỷ"),
]

# Chưa đủ căn cứ để tự gán quyền: script chỉ in cảnh báo, không sửa.
CAN_DNH_XAC_NHAN = {
    "linh.nguyen4": "13/08: qlv, MN, kênh ETC, không mã NV -> bị chặn. Nếu là phụ trách kênh ETC "
                    "thì chuyển regional_director (MN + ETC, hoặc chỉ ETC). Cần DNH chốt vai trò.",
}


def _text(value):
    return str(value or "").strip()


def _chuan_hoa(role, scope_value=None, employee_code=None, scope_channel=None):
    return (_text(role).lower(), _text(scope_value).upper() or None,
            _text(employee_code) or None, _text(scope_channel).upper() or None)


def _ly_do_bi_chan(role, area, employee, channel):
    """Giống _require_valid_scope() trong main.py: None nghĩa là đăng nhập hỏi được."""
    if role not in auth.VALID_ROLES:
        return "vai trò không hợp lệ"
    if role == "admin_ops":
        return "admin_ops bị chặn khỏi /chat"
    if role == "c_level" and (area or employee or channel):
        return "c_level mang phạm vi"
    if role == "regional_director":
        if not (area or channel):
            return "Giám đốc miền/kênh thiếu vùng hoặc kênh"
        if employee:
            return "Giám đốc miền/kênh mang mã NV"
    if role == "qlv" and (not area or not employee):
        return "QLV thiếu " + " và ".join(
            x for x, ok in (("vùng", area), ("mã NV", employee)) if not ok)
    return None


def _doc(db_path, usernames):
    uri = "file:%s?mode=ro" % Path(db_path).resolve().as_posix()
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        extra = [c for c in ("last_login_at", "must_change_password") if c in cols]
        rows = conn.execute(
            "SELECT username, name, role, scope_value, employee_code, scope_channel, "
            "COALESCE(status,'approved') status, COALESCE(is_active,1) is_active%s FROM users "
            "WHERE username IN (%s)" % ("".join(", " + c for c in extra),
                                        ",".join("?" * len(usernames))),
            tuple(usernames)).fetchall()
    return {r["username"]: dict(r) for r in rows}


def danh_gia(bo_test, hien_tai):
    """Trả danh sách (muc, row, trang_thai, chi_tiet). Không đụng DB."""
    ket_qua = []
    for muc in bo_test:
        row = hien_tai.get(muc["username"])
        if row is None:
            ket_qua.append((muc, None, "KHONG_TON_TAI",
                            "chưa tạo - chạy --tao-moi" if muc.get("tao_moi")
                            else "không có trong auth.db"))
            continue
        if not row["is_active"]:
            ket_qua.append((muc, row, "BI_KHOA", "tài khoản đang bị khóa"))
            continue
        if _text(row["status"]).lower() != "approved":
            ket_qua.append((muc, row, "CHUA_DUYET", "trạng thái %s" % row["status"]))
            continue
        dung = _chuan_hoa(muc["role"], muc.get("scope_value"), muc.get("employee_code"),
                          muc.get("scope_channel"))
        dang = _chuan_hoa(row["role"], row["scope_value"], row["employee_code"],
                          row["scope_channel"])
        if dang == dung:
            ket_qua.append((muc, row, "DUNG", ""))
            continue
        chan = _ly_do_bi_chan(*dang)
        ket_qua.append((muc, row, "SAI_CAU_HINH",
                        ("đang bị chặn 403: %s" % chan) if chan else "hỏi được nhưng sai phạm vi"))
    return ket_qua


def _mo_ta(role, area, employee, channel):
    phan = [role or "?"]
    if area:
        phan.append("vùng " + area)
    if channel:
        phan.append("kênh " + channel)
    if employee:
        phan.append("mã NV " + employee)
    return ", ".join(phan)


def _in_bao_cao(ket_qua):
    print("BỘ TÀI KHOẢN UAT - trạng thái trong auth.db")
    print("=" * 96)
    for muc, row, trang_thai, chi_tiet in ket_qua:
        dung = _mo_ta(*_chuan_hoa(muc["role"], muc.get("scope_value"), muc.get("employee_code"),
                                  muc.get("scope_channel")))
        print("%-13s %-12s %s" % (muc["username"], trang_thai, muc["case"]))
        print("    cần: %s" % dung)
        if row is not None and trang_thai != "DUNG":
            print("    đang: %s" % _mo_ta(*_chuan_hoa(row["role"], row["scope_value"],
                                                     row["employee_code"], row["scope_channel"])))
        if chi_tiet:
            print("    -> %s" % chi_tiet)
        if row is not None:
            login = row.get("last_login_at")
            print("    đăng nhập gần nhất: %s | phải đổi MK: %s"
                  % (login or "chưa từng", "có" if row.get("must_change_password") else "không"))
        print("    nguồn: %s" % muc["nguon"])
    print()
    print("CẦN DNH XÁC NHẬN (script không tự sửa)")
    for username, ghi_chu in CAN_DNH_XAC_NHAN.items():
        print("  - %s: %s" % (username, ghi_chu))


def sua_pham_vi(ket_qua):
    da_sua = []
    for muc, row, trang_thai, _ in ket_qua:
        if trang_thai != "SAI_CAU_HINH":
            continue
        ok = auth.approve_user(muc["username"], muc["role"], muc.get("scope_value"),
                               muc.get("employee_code"), muc.get("scope_channel"))
        if ok:
            da_sua.append(muc["username"])
    return da_sua


def tao_moi(ket_qua):
    """Tạo các tài khoản đánh dấu tao_moi còn thiếu. Trả list[(username, mat_khau)].

    Chỉ tạo mục có tao_moi=True: tài khoản thật bị thiếu (vd hung.le) là dấu hiệu sai dữ liệu, phải
    điều tra, không được tự tạo lại một login mới đè lên."""
    da_tao = []
    for muc, _, trang_thai, _ in ket_qua:
        if trang_thai != "KHONG_TON_TAI" or not muc.get("tao_moi"):
            continue
        _, mat_khau = auth.admin_create_user(
            username=muc["username"], name=muc.get("ten") or muc["username"], role=muc["role"],
            scope_value=muc.get("scope_value"), employee_code=muc.get("employee_code"),
            scope_channel=muc.get("scope_channel"))
        da_tao.append((muc["username"], mat_khau))
    return da_tao


def cap_mat_khau(usernames, hien_tai, ke_ca_da_dang_nhap=False, bat_doi_mk=True):
    """Trả (da_cap: list[(username, mat_khau)], tu_choi: list[(username, ly_do)])."""
    trong_bo = {m["username"] for m in BO_TEST}
    da_cap, tu_choi = [], []
    for username in usernames:
        row = hien_tai.get(username)
        if username not in trong_bo:
            tu_choi.append((username, "không nằm trong bộ test - không cấp MK tùy tiện"))
        elif row is None:
            tu_choi.append((username, "không có trong auth.db"))
        elif row.get("last_login_at") and not ke_ca_da_dang_nhap:
            tu_choi.append((username, "đã từng đăng nhập %s - có thể người thật đang dùng; "
                                      "thêm --ke-ca-da-dang-nhap nếu chắc chắn" % row["last_login_at"]))
        else:
            mat_khau = auth.generate_password(12)
            if auth.reset_password_and_revoke_sessions(username, mat_khau,
                                                       must_change_password=bat_doi_mk):
                da_cap.append((username, mat_khau))
            else:
                tu_choi.append((username, "đặt MK thất bại"))
    return da_cap, tu_choi


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Chuẩn bị bộ tài khoản UAT từ tài khoản đã có")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="Đường dẫn auth.db")
    ap.add_argument("--sua-pham-vi", action="store_true",
                    help="Gán lại role/vùng/kênh/mã NV cho tài khoản đang sai cấu hình")
    ap.add_argument("--tao-moi", action="store_true",
                    help="Tạo tài khoản test còn thiếu (dnh_etc, head.mt, chosi.mb, chosi.mn)")
    ap.add_argument("--cap-mk", help="Đặt MK tạm cho các username này, cách nhau dấu phẩy")
    ap.add_argument("--ke-ca-da-dang-nhap", action="store_true",
                    help="Cho phép đặt lại MK cả tài khoản đã từng đăng nhập")
    ap.add_argument("--khong-bat-doi-mk", action="store_true",
                    help="Không bắt đổi MK ở lần đăng nhập đầu (chỉ khi nhiều người dùng chung)")
    args = ap.parse_args(argv)

    auth.DB_PATH = str(args.db)
    usernames = [m["username"] for m in BO_TEST] + list(CAN_DNH_XAC_NHAN)
    try:
        hien_tai = _doc(args.db, usernames)
    except (OSError, sqlite3.Error) as exc:
        print("KHÔNG ĐỌC ĐƯỢC auth.db: %s" % exc)
        return 2

    print("Nguồn: %s" % Path(args.db).resolve())
    ket_qua = danh_gia(BO_TEST, hien_tai)
    _in_bao_cao(ket_qua)

    if args.sua_pham_vi:
        da_sua = sua_pham_vi(ket_qua)
        print()
        print("ĐÃ SỬA PHẠM VI: %s" % (", ".join(da_sua) or "không có tài khoản nào cần sửa"))
        hien_tai = _doc(args.db, usernames)
        ket_qua = danh_gia(BO_TEST, hien_tai)

    mat_khau_moi, tu_choi = [], []
    if args.tao_moi:
        mat_khau_moi += tao_moi(ket_qua)
        hien_tai = _doc(args.db, usernames)
        ket_qua = danh_gia(BO_TEST, hien_tai)

    if args.cap_mk:
        chon = [x.strip().lower() for x in args.cap_mk.split(",") if x.strip()]
        da_cap, tu_choi = cap_mat_khau(chon, hien_tai, args.ke_ca_da_dang_nhap,
                                       not args.khong_bat_doi_mk)
        mat_khau_moi += da_cap

    if mat_khau_moi or tu_choi:
        print()
        print("MẬT KHẨU TẠM - chỉ hiện một lần, chép ngay, gửi riêng từng người, không lưu file:")
        for username, mat_khau in mat_khau_moi:
            print("  %-13s %s" % (username, mat_khau))
        for username, ly_do in tu_choi:
            print("  %-13s KHÔNG CẤP: %s" % (username, ly_do))

    con_sai = [m["username"] for m, _, tt, _ in ket_qua if tt != "DUNG"]
    print()
    if con_sai:
        print("CHƯA SẴN SÀNG: %s" % ", ".join(con_sai))
        return 1
    print("SẴN SÀNG: cả %d tài khoản trong bộ test đúng cấu hình." % len(BO_TEST))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
