# -*- coding: utf-8 -*-
"""29/09/2026 - chong lam dung dang nhap / quen mat khau.

1) Gioi han theo IP phai la IP nguoi dung: sau Cloudflare tunnel, request.client.host la IP may chu
   Vercel ma ca cong ty dung chung, nen 30 lan sai tu bat ky ai khoa dang nhap cua moi nguoi.
2) "Quen mat khau" khong duoc la cong tac khoa nguoi khac: truoc day ai biet email (doan duoc) cung
   doi duoc mat khau that va da chu tai khoan ra khoi moi phien, 3 lan/gio.
Khong gui email that: send_password_email / send_smtp_message deu la ham gia."""
import datetime as dt
import importlib.util
import os
import sqlite3
import sys

import pytest
from starlette.requests import Request

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import auth
import conversation_memory as cm
import mailer

EMAIL = "nguyen.van.a@namhapharma.com"
MAT_KHAU_CU = "mat-khau-cu-that-dai"


def _nap_main(tmp_path, monkeypatch, ten, api_key="khoa-proxy-vercel"):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(cm, "DB_PATH", str(tmp_path / "memory.db"))
    cm.init()
    spec = importlib.util.spec_from_file_location(ten, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[ten] = chatbot_main
    spec.loader.exec_module(chatbot_main)
    monkeypatch.setattr(chatbot_main, "API_KEY", api_key)
    chatbot_main._EMAIL_AUTH_ATTEMPTS.clear()
    chatbot_main._IP_AUTH_ATTEMPTS.clear()
    return chatbot_main


def _request(ip_header=None, client="198.51.100.7"):
    headers = [(b"x-dnh-client-ip", ip_header.encode())] if ip_header else []
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers,
                    "client": (client, 443)})


def _tao_nguoi_dung():
    auth.create_user("nguyen.van.a", MAT_KHAU_CU, name="Nguyen Van A", role="qlv",
                     scope_value="MB", employee_code="NV001", email=EMAIL)
    user = auth.verify_login(EMAIL, MAT_KHAU_CU)
    return user, auth.create_session(user["id"])


def _mail_gia(monkeypatch, chatbot_main):
    sent = []

    def gui(email, password, is_reset=False, giu_mat_khau_cu=False):
        sent.append({"email": email, "password": password, "is_reset": is_reset,
                     "giu_mat_khau_cu": giu_mat_khau_cu})
        return True

    monkeypatch.setattr(chatbot_main, "send_password_email", gui)
    return sent


def test_ip_gioi_han_lay_tu_proxy_khi_co_khoa_api(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lam_dung_ip")

    assert chatbot_main._login_client_ip(_request("203.0.113.25")) == "203.0.113.25"
    assert chatbot_main._login_client_ip(_request("2001:db8::7")) == "2001:db8::7"
    # Header rac / thieu -> quay ve IP ket noi, khong de chuoi tuy y lam khoa dem.
    assert chatbot_main._login_client_ip(_request("khong-phai-ip")) == "198.51.100.7"
    assert chatbot_main._login_client_ip(_request()) == "198.51.100.7"


def test_khong_co_khoa_api_thi_khong_tin_header_ip(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lam_dung_ip_khong_khoa", api_key="")

    assert chatbot_main._login_client_ip(_request("203.0.113.25")) == "198.51.100.7"


def test_dang_nhap_sai_tu_mot_may_khong_khoa_may_khac(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lam_dung_login_ip")
    chatbot_main._LOGIN_IDENTIFIER_ATTEMPTS.clear()
    chatbot_main._LOGIN_IP_ATTEMPTS.clear()
    _tao_nguoi_dung()

    ke_tan_cong = _request("203.0.113.66", client="18.0.0.1")   # cung IP Vercel voi nguoi that
    for i in range(chatbot_main.LOGIN_IP_LIMIT):
        with pytest.raises(chatbot_main.HTTPException):
            chatbot_main.login(chatbot_main.LoginRequest(username=f"doan{i}", password="sai"), ke_tan_cong)
    with pytest.raises(chatbot_main.HTTPException) as bi_chan:
        chatbot_main.login(chatbot_main.LoginRequest(username="doan-them", password="sai"), ke_tan_cong)
    assert bi_chan.value.status_code == 429

    nguoi_that = _request("203.0.113.10", client="18.0.0.1")
    result = chatbot_main.login(chatbot_main.LoginRequest(username=EMAIL, password=MAT_KHAU_CU), nguoi_that)
    assert result.username == "nguyen.van.a"


def test_quen_mat_khau_khong_doi_mat_khau_cu_va_khong_da_phien(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lam_dung_quen_giu_cu")
    sent = _mail_gia(monkeypatch, chatbot_main)
    _user, token_cu = _tao_nguoi_dung()

    result = chatbot_main.forgot_password(chatbot_main.ForgotPasswordRequest(email=EMAIL),
                                          _request("203.0.113.9"))

    assert result["ok"] is True
    assert sent == [{"email": EMAIL, "password": sent[0]["password"], "is_reset": True, "giu_mat_khau_cu": True}]
    # Nguoi khong yeu cau van dang nhap binh thuong, phien cu van song.
    assert auth.get_user_by_session(token_cu) is not None
    assert auth.verify_login(EMAIL, MAT_KHAU_CU).get("must_change_password") == 0
    # Dang nhap bang mat khau cu -> huy mat khau tam dang cho.
    assert auth.verify_login(EMAIL, sent[0]["password"]) == {"error": "wrong_password"}


def test_dang_nhap_bang_mat_khau_tam_moi_doi_han_va_thu_hoi_phien(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lam_dung_quen_dung_tam")
    sent = _mail_gia(monkeypatch, chatbot_main)
    _user, token_cu = _tao_nguoi_dung()
    chatbot_main.forgot_password(chatbot_main.ForgotPasswordRequest(email=EMAIL), _request("203.0.113.9"))
    mat_khau_tam = sent[0]["password"]

    result = chatbot_main.login(chatbot_main.LoginRequest(username=EMAIL, password=mat_khau_tam),
                                _request("203.0.113.9"))

    assert result.must_change_password is True
    assert auth.get_user_by_session(token_cu) is None                       # phien cu bi thu hoi
    assert auth.get_user_by_session(result.token) is not None               # phien moi con song
    assert auth.verify_login(EMAIL, MAT_KHAU_CU) == {"error": "wrong_password"}
    assert auth.verify_login(EMAIL, mat_khau_tam)["must_change_password"] == 1


def test_mat_khau_tam_het_han_thi_khong_dung_duoc(tmp_path, monkeypatch):
    _nap_main(tmp_path, monkeypatch, "lam_dung_het_han")
    _tao_nguoi_dung()
    auth.set_pending_reset_password(EMAIL, "mat-khau-tam-da-cu")
    conn = sqlite3.connect(auth.DB_PATH)
    conn.execute("UPDATE users SET reset_expires_at=?",
                 ((dt.datetime.now() - dt.timedelta(minutes=1)).isoformat(),))
    conn.commit()
    conn.close()

    assert auth.verify_login(EMAIL, "mat-khau-tam-da-cu") == {"error": "wrong_password"}
    assert auth.verify_login(EMAIL, MAT_KHAU_CU)["must_change_password"] == 0


def test_doi_mat_khau_hoac_admin_cap_lai_thi_huy_mat_khau_tam(tmp_path, monkeypatch):
    _nap_main(tmp_path, monkeypatch, "lam_dung_huy_tam")
    _tao_nguoi_dung()

    auth.set_pending_reset_password(EMAIL, "mat-khau-tam-mot")
    auth.set_password(EMAIL, "mat-khau-moi-tu-doi")
    assert auth.verify_login(EMAIL, "mat-khau-tam-mot") == {"error": "wrong_password"}

    auth.set_pending_reset_password(EMAIL, "mat-khau-tam-hai")
    auth.reset_password_and_revoke_sessions(EMAIL, "mat-khau-admin-cap")
    assert auth.verify_login(EMAIL, "mat-khau-tam-hai") == {"error": "wrong_password"}
    assert auth.verify_login(EMAIL, "mat-khau-admin-cap")["must_change_password"] == 1


def test_gioi_han_quen_mat_khau_tinh_theo_ip_that(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "lam_dung_quen_ip")
    _mail_gia(monkeypatch, chatbot_main)

    ke_tan_cong = _request("203.0.113.66", client="18.0.0.1")
    for i in range(10):
        chatbot_main.forgot_password(
            chatbot_main.ForgotPasswordRequest(email=f"doan{i}@namhapharma.com"), ke_tan_cong)
    with pytest.raises(chatbot_main.HTTPException) as bi_chan:
        chatbot_main.forgot_password(
            chatbot_main.ForgotPasswordRequest(email="doan-them@namhapharma.com"), ke_tan_cong)
    assert bi_chan.value.status_code == 429

    result = chatbot_main.forgot_password(chatbot_main.ForgotPasswordRequest(email=EMAIL),
                                          _request("203.0.113.10", client="18.0.0.1"))
    assert result["ok"] is True


def test_email_mat_khau_tam_noi_ro_mat_khau_cu_van_dung_va_escape_html(monkeypatch):
    gui = []
    monkeypatch.setattr(mailer, "get_smtp_config", lambda: {"sender": "bot@namhapharma.com"})
    monkeypatch.setattr(mailer, "send_smtp_message", lambda msg, to, config: gui.append(msg))

    assert mailer.send_password_email(EMAIL, "ab<cd>&ef", is_reset=True, giu_mat_khau_cu=True)
    noi_dung = gui[0].get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "vẫn dùng được" in noi_dung
    assert "ab&lt;cd&gt;&amp;ef" in noi_dung and "ab<cd>" not in noi_dung

    assert mailer.send_password_email(EMAIL, "khoi-tao-123", is_reset=False)
    khoi_tao = gui[1].get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "vẫn dùng được" not in khoi_tao
