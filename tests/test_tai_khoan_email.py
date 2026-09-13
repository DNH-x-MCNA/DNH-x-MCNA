"""Tao tai khoan kem email, va gan email cho tai khoan da co de cap lai mat khau duoc (11/09/2026)."""
import importlib.util
import os
import sys

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import auth  # noqa: E402

C_LEVEL = {"role": "c_level", "username": "dnh"}
ADMIN_OPS = {"role": "admin_ops", "username": "admin.dnh"}


def _main(tmp_path, monkeypatch, ten):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    spec = importlib.util.spec_from_file_location(ten, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[ten] = chatbot_main
    spec.loader.exec_module(chatbot_main)
    auth.init_schema()
    monkeypatch.setattr(chatbot_main, "_write_log", lambda entry: None)
    return chatbot_main


def _mail_that(sent, ket_qua=True):
    # Dung CHU KY THAT cua mailer.send_password_email: truyen tham so la (vd user_name=) se vo o day,
    # dung nhu loi 500 cu.
    def fake(to_email, password, is_reset=False):
        sent.append({"email": to_email, "password": password, "is_reset": is_reset})
        return ket_qua
    return fake


def test_tao_tai_khoan_kem_email_khong_con_loi_500(tmp_path, monkeypatch):
    m = _main(tmp_path, monkeypatch, "email_create_main")
    sent = []
    monkeypatch.setattr(m, "send_password_email", _mail_that(sent))

    kq = m.create_user_by_admin(m.AdminCreateUserRequest(
        username="moi.user", name="Người Mới", email="Moi.User@namhapharma.com",
        role="regional_director", scope_value="MB"), C_LEVEL)

    assert kq["ok"] is True and kq["email_sent"] is True
    assert sent == [{"email": "moi.user@namhapharma.com", "password": kq["generated_password"],
                     "is_reset": False}]
    assert "error" not in auth.verify_login("moi.user", kq["generated_password"])


def test_gui_mail_loi_van_tra_mat_khau_cho_admin_chuyen_tay(tmp_path, monkeypatch):
    m = _main(tmp_path, monkeypatch, "email_create_fail_main")
    monkeypatch.setattr(m, "send_password_email", _mail_that([], ket_qua=False))

    kq = m.create_user_by_admin(m.AdminCreateUserRequest(
        username="moi.user", email="moi.user@namhapharma.com",
        role="qlv", scope_value="MN", employee_code="TM23100148"), C_LEVEL)

    assert kq["email_sent"] is False
    assert "error" not in auth.verify_login("moi.user", kq["generated_password"])


def test_gan_email_cho_tai_khoan_da_co_roi_cap_lai_mat_khau_duoc(tmp_path, monkeypatch):
    m = _main(tmp_path, monkeypatch, "email_assign_main")
    auth.create_user("hung.le", "mk-cu-123", "Lê Văn Hưng", "regional_director", "MT")
    sent = []
    monkeypatch.setattr(m, "send_password_email", _mail_that(sent))

    # Chua co email: dung loi nguoi dung gap tren trang quan tri.
    with pytest.raises(m.HTTPException) as chua_co:
        m.reset_user_password_endpoint("hung.le", ADMIN_OPS)
    assert chua_co.value.status_code == 400

    m.approve_user_endpoint("hung.le", m.ApproveUserRequest(
        role="regional_director", scope_value="MT", email=" Hung.Le@namhapharma.com "), C_LEVEL)
    assert auth.get_user_by_email_or_username("hung.le")["email"] == "hung.le@namhapharma.com"

    m.reset_user_password_endpoint("hung.le", ADMIN_OPS)
    assert sent[-1]["email"] == "hung.le@namhapharma.com" and sent[-1]["is_reset"] is True
    assert "error" not in auth.verify_login("hung.le", sent[-1]["password"])


def test_email_sai_ten_mien_hoac_cua_nguoi_khac_bi_tu_choi_va_khong_doi_quyen(tmp_path, monkeypatch):
    m = _main(tmp_path, monkeypatch, "email_reject_main")
    auth.create_user("tu.pham", "mk", "Phạm Xuân Tú", "qlv", "MB", "MBKV2")
    auth.create_user("khac", "mk", "Người khác", "qlv", "MB", "MBKV3", email="khac@namhapharma.com")

    for email in ("tu.pham@gmail.com", "khac@namhapharma.com"):
        with pytest.raises(m.HTTPException) as loi:
            m.approve_user_endpoint("tu.pham", m.ApproveUserRequest(
                role="regional_director", scope_value="MB", email=email), C_LEVEL)
        assert loi.value.status_code == 400

    sau = auth.get_user_by_email_or_username("tu.pham")
    assert (sau["role"], sau["employee_code"], sau["email"]) == ("qlv", "MBKV2", None)


def test_admin_van_hanh_khong_doi_duoc_email(tmp_path, monkeypatch):
    m = _main(tmp_path, monkeypatch, "email_ops_main")
    auth.create_user("tu.pham", "mk", "Phạm Xuân Tú", "qlv", "MB", "MBKV2")

    with pytest.raises(m.HTTPException) as loi:
        m.approve_user_endpoint("tu.pham", m.ApproveUserRequest(
            role="qlv", scope_value="MB", employee_code="MBKV2",
            email="admin.cua.toi@namhapharma.com"), ADMIN_OPS)

    assert loi.value.status_code == 403
    assert auth.get_user_by_email_or_username("tu.pham")["email"] is None
