"""Rà tài khoản chatbot thiếu phạm vi dữ liệu, chỉ đọc và không in thông tin bí mật."""

import argparse
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parents[1] / "backend" / "auth.db"


def _text(value):
    return str(value or "").strip()


def _ly_do_bat_hop_le(row):
    role = _text(row["role"]).lower()
    area = _text(row["scope_value"])
    employee = _text(row["employee_code"])
    channel = _text(row["scope_channel"])
    if role == "qlv":
        missing = []
        if not area:
            missing.append("vùng")
        if not employee:
            missing.append("mã nhân viên")
        return "thiếu " + " và ".join(missing) if missing else None
    if role == "regional_director" and not (area or channel):
        return "thiếu vùng hoặc kênh"
    return None


def _doc_users(db_path):
    uri = "file:%s?mode=ro" % Path(db_path).resolve().as_posix()
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT username, name, role, scope_value, employee_code, scope_channel, "
            "COALESCE(status, 'approved') status, COALESCE(is_active, 1) is_active "
            "FROM users ORDER BY role, username"
        ).fetchall()


def _phan_loai(rows):
    approved_invalid = []
    pending_invalid = []
    scope_warnings = []
    for row in rows:
        reason = _ly_do_bat_hop_le(row)
        status = _text(row["status"]).lower() or "approved"
        active = bool(row["is_active"])
        if reason and active:
            target = approved_invalid if status == "approved" else pending_invalid
            target.append((row, reason))
        if _text(row["role"]).lower() in {"c_level", "admin_ops"} and any(
            _text(row[key]) for key in ("scope_value", "employee_code", "scope_channel")
        ):
            scope_warnings.append(row)
    return approved_invalid, pending_invalid, scope_warnings


def _in_danh_sach(title, items):
    if not items:
        return
    print()
    print(title)
    for row, reason in items:
        display = _text(row["name"]) or _text(row["username"])
        print("  - %s (%s, %s): %s" % (display, row["username"], row["role"], reason))


def main(argv=None):
    # PowerShell tren may van hanh co the mac dinh CP1252; ep UTF-8 de ten/chuc danh tieng Viet
    # hien dung va khong lam script dung giua chung.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Kiểm tài khoản thiếu vùng/kênh/mã nhân viên")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Đường dẫn auth.db cần kiểm")
    args = parser.parse_args(argv)
    try:
        rows = _doc_users(args.db)
    except (OSError, sqlite3.Error) as exc:
        print("KHÔNG KIỂM ĐƯỢC: %s" % exc)
        return 2

    approved, pending, warnings = _phan_loai(rows)
    active = sum(bool(row["is_active"]) for row in rows)
    print("KIỂM TRA TÀI KHOẢN VÀ PHẠM VI DỮ LIỆU")
    print("Nguồn: %s" % args.db.resolve())
    print("Tổng tài khoản: %d | đang hoạt động: %d" % (len(rows), active))
    print("Đã duyệt nhưng thiếu phạm vi: %d" % len(approved))
    print("Chưa duyệt nhưng thiếu phạm vi: %d" % len(pending))
    print("C-Level/Admin đang mang phạm vi giới hạn: %d" % len(warnings))
    _in_danh_sach("CẦN SỬA TRƯỚC KHI GIAO TESTER", approved)
    _in_danh_sach("CẦN BỔ SUNG TRƯỚC KHI DUYỆT", pending)
    if warnings:
        print()
        print("CẦN XÁC NHẬN (có thể là chủ đích)")
        for row in warnings:
            display = _text(row["name"]) or _text(row["username"])
            print("  - %s (%s, %s)" % (display, row["username"], row["role"]))
    print()
    if approved:
        print("KẾT LUẬN: CHƯA SẴN SÀNG giao tester; hãy sửa các tài khoản đã duyệt ở trên.")
        return 1
    print("KẾT LUẬN: Phạm vi của các tài khoản đã duyệt đang hợp lệ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
