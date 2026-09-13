"""Cấp mật khẩu tạm cho MỘT tài khoản quên mật khẩu mà không có email công ty.

Trang quản trị chỉ cấp lại mật khẩu qua email và chưa có chỗ bổ sung email cho tài khoản đã tạo, nên
tài khoản không có email không lấy lại được mật khẩu trên giao diện (lỗi "Tài khoản chưa có email
công ty hợp lệ"). Script này là đường dự phòng, chạy trên MÁY CHỦ (máy 24) bởi người có quyền vào
máy - cùng mức tin cậy với quyền đọc auth.db.

    python scripts/cap_lai_mat_khau.py tu.pham

- Sinh mật khẩu tạm 12 ký tự, bắt đổi ở lần đăng nhập đầu, thu hồi mọi phiên đang đăng nhập.
- In mật khẩu MỘT LẦN ra terminal. Không ghi file, không ghi log, không đưa vào Git.
- Ghi một dòng vào audit_log.jsonl: ai chạy, lúc nào, cho tài khoản nào - không có mật khẩu.
- Hỏi gõ lại username để tránh đổi nhầm tài khoản (bỏ qua bằng --dong-y).
- Tài khoản C-Level/Admin phải thêm --tai-khoan-dac-quyen.
"""

import argparse
import datetime as dt
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))

import auth  # noqa: E402

DEFAULT_DB = BACKEND / "auth.db"
DEFAULT_AUDIT = BACKEND / "logs" / "audit_log.jsonl"
DAC_QUYEN = {"c_level", "admin_ops"}


def _ghi_audit(path, nguoi_chay, username):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": dt.datetime.now().isoformat(),
            "username": "script:%s" % nguoi_chay,
            "question": "🔐 Cấp lại mật khẩu tạm cho %s (script trên máy chủ, tài khoản không có email)"
                        % username,
            "sql": "<script:cap_lai_mat_khau>",
            "status": "ok",
        }, ensure_ascii=False) + "\n")


def main(argv=None, nhap=input):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Cấp mật khẩu tạm cho tài khoản không có email")
    ap.add_argument("username")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="Đường dẫn auth.db")
    ap.add_argument("--audit-log", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--tai-khoan-dac-quyen", action="store_true",
                    help="Cho phép cấp lại cho tài khoản C-Level/Admin")
    ap.add_argument("--dong-y", action="store_true", help="Không hỏi gõ lại username")
    args = ap.parse_args(argv)

    auth.DB_PATH = str(args.db)
    user = auth.get_user_by_email_or_username(args.username)
    if not user:
        print("KHÔNG TÌM THẤY tài khoản: %s" % args.username)
        return 2
    username = user["username"]
    print("Tài khoản: %s | %s | vai trò %s | vùng %s | kênh %s | mã NV %s | %s"
          % (username, user.get("name") or "-", user["role"], user.get("scope_value") or "-",
             user.get("scope_channel") or "-", user.get("employee_code") or "-",
             "đang hoạt động" if user.get("is_active") else "ĐANG BỊ KHÓA"))
    if user["role"] in DAC_QUYEN and not args.tai_khoan_dac_quyen:
        print("DỪNG: tài khoản đặc quyền (%s). Thêm --tai-khoan-dac-quyen nếu chắc chắn." % user["role"])
        return 2
    if not args.dong_y and nhap("Gõ lại username để xác nhận: ").strip().lower() != username:
        print("DỪNG: username xác nhận không khớp, không đổi gì.")
        return 2

    mat_khau = auth.generate_password(12)
    if not auth.reset_password_and_revoke_sessions(username, mat_khau, must_change_password=True):
        print("THẤT BẠI: không đặt được mật khẩu, không đổi gì.")
        return 1
    _ghi_audit(args.audit_log, getpass.getuser(), username)
    print()
    print("MẬT KHẨU TẠM (chỉ hiện một lần, chép ngay, gửi riêng cho chủ tài khoản):")
    print("  %s   %s" % (username, mat_khau))
    print("Người dùng phải đổi mật khẩu ở lần đăng nhập đầu. Mọi phiên cũ đã bị thu hồi.")
    if not user.get("is_active"):
        print("LƯU Ý: tài khoản đang bị khóa - mở khóa trên trang quản trị thì mới đăng nhập được.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
