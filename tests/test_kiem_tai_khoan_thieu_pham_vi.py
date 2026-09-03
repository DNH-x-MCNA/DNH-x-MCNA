import sqlite3

from scripts import kiem_tai_khoan_thieu_pham_vi as scope_check


def _db(tmp_path, users):
    path = tmp_path / "auth.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users (username TEXT, name TEXT, role TEXT, scope_value TEXT, "
            "employee_code TEXT, scope_channel TEXT, status TEXT, is_active INTEGER)"
        )
        conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", users)
    return path


def test_qlv_can_ca_vung_va_ma_nhan_vien(tmp_path):
    path = _db(tmp_path, [
        ("du", "Đủ", "qlv", "MB", "MBKV1", None, "approved", 1),
        ("thieu", "Thiếu", "qlv", "MB", None, None, "approved", 1),
    ])
    approved, pending, warnings = scope_check._phan_loai(scope_check._doc_users(path))

    assert len(approved) == 1
    assert approved[0][0]["username"] == "thieu"
    assert approved[0][1] == "thiếu mã nhân viên"
    assert pending == []
    assert warnings == []


def test_giam_doc_mien_chi_can_vung_hoac_kenh(tmp_path):
    path = _db(tmp_path, [
        ("mien", "Miền", "regional_director", "MN", None, None, "approved", 1),
        ("kenh", "Kênh", "regional_director", None, None, "ETC", "approved", 1),
        ("rong", "Rỗng", "regional_director", None, None, None, "pending", 1),
    ])
    approved, pending, _ = scope_check._phan_loai(scope_check._doc_users(path))

    assert approved == []
    assert len(pending) == 1
    assert pending[0][0]["username"] == "rong"


def test_c_level_mang_scope_chi_canh_bao(tmp_path):
    path = _db(tmp_path, [
        ("boss", "Boss", "c_level", None, None, "OTC", "approved", 1),
    ])
    approved, pending, warnings = scope_check._phan_loai(scope_check._doc_users(path))

    assert approved == []
    assert pending == []
    assert len(warnings) == 1
