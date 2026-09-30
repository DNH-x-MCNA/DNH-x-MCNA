# -*- coding: utf-8 -*-
"""30/09/2026 - gui mail bang system@namhapharma.com KHONG dang nhap (direct send vao Microsoft 365).

Tenant M365 cua DNH tat SMTP AUTH cho ca to chuc; system@ la hop thu chi gui, khong dang nhap. Kiem that tu
may 24: namhapharma-com.mail.protection.outlook.com:25 nhan nguoi nhan noi bo (250), tu choi nguoi nhan
ngoai (451). SMTP_AUTH=none: khong login(), bat buoc TLS, bat buoc SENDER_EMAIL. Moi ket noi SMTP la gia."""
import os
from email import message_from_string
from email.header import decode_header, make_header
from email.utils import parseaddr

import pytest

from backend import mailer, mail_transport as transport
from src import notifier

MX = "namhapharma-com.mail.protection.outlook.com"
SYSTEM = "system@namhapharma.com"


@pytest.fixture
def smtp(monkeypatch):
    for key in list(os.environ):
        if key.startswith("SMTP_") or key in {"EMAIL_PROVIDER", "SENDGRID_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAILS"}:
            monkeypatch.delenv(key)
    monkeypatch.setenv("SMTP_AUTH", "none")
    monkeypatch.setenv("SMTP_SERVER", MX)
    monkeypatch.setenv("SMTP_PORT", "25")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SENDER_EMAIL", SYSTEM)
    monkeypatch.setattr(mailer, "_load_env_file", lambda: None)
    monkeypatch.setattr(notifier, "load_config", lambda: {"email": {
        "smtp_server": "smtp.office365.com", "smtp_port": 587, "use_tls": True,
        "sender_name": "DNH", "recipient_emails": [],
    }})
    state = {"calls": [], "messages": [], "refused": {}}

    class FakeSMTP:
        def __init__(self, host, port, *, timeout, context=None):
            state["calls"].append(("connect", host, port))

        def ehlo(self):
            state["calls"].append(("ehlo",))

        def starttls(self, *, context):
            state["calls"].append(("starttls",))

        def login(self, user, password):
            state["calls"].append(("login", user))

        def sendmail(self, sender, recipients, body):
            state["messages"].append((sender, recipients, message_from_string(body)))
            return state["refused"]

        def quit(self):
            state["calls"].append(("quit",))

        def close(self):
            state["calls"].append(("close",))

    monkeypatch.setattr(transport.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(transport.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(notifier, "send_email_via_sendgrid", lambda *a, **k: pytest.fail("khong duoc qua SendGrid"))
    return state


def _goi(state):
    return [c[0] for c in state["calls"]]


def test_bao_cao_gui_khong_dang_nhap_qua_tls_tu_system(smtp):
    assert notifier.send_email("Báo cáo tuần", "<p>Doanh thu</p>", recipient_override=["long.tran@namhapharma.com"])
    assert smtp["calls"][0] == ("connect", MX, 25)
    assert "starttls" in _goi(smtp) and "login" not in _goi(smtp)
    sender, recipients, msg = smtp["messages"][0]
    assert sender == SYSTEM and recipients == ["long.tran@namhapharma.com"]
    assert parseaddr(msg["From"])[1] == SYSTEM


def test_email_mat_khau_gui_khong_dang_nhap(smtp):
    assert mailer.send_password_email("qlv.mb@namhapharma.com", "mat-khau-tam-123", is_reset=True)
    assert "login" not in _goi(smtp) and "starttls" in _goi(smtp)
    sender, recipients, msg = smtp["messages"][0]
    assert sender == SYSTEM and recipients == ["qlv.mb@namhapharma.com"]
    # Dia chi trong From phai doc duoc (khong nam trong cum ma hoa), ten co dau van giu nguyen.
    ten, dia_chi = parseaddr(msg["From"])
    assert dia_chi == SYSTEM and str(make_header(decode_header(ten))) == "Dược Nam Hà AI Bot"
    assert "mat-khau-tam-123" in msg.get_payload()[0].get_payload(decode=True).decode("utf-8")


def test_tai_khoan_gmail_con_sot_trong_env_khong_duoc_dung(smtp, monkeypatch):
    # .env goc may 24 van con SMTP_USER/SMTP_PASSWORD Gmail ca nhan; backend\.env ghi de phan con lai.
    monkeypatch.setenv("SMTP_USER", "ca-nhan@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-gmail")
    assert notifier.send_email("Báo cáo", "<p>x</p>", recipient_override=["long.tran@namhapharma.com"])
    assert "login" not in _goi(smtp)
    assert smtp["messages"][0][0] == SYSTEM


@pytest.mark.parametrize("key, value", [("SMTP_SECURITY", "none"), ("SENDER_EMAIL", ""), ("SMTP_AUTH", "oauth")])
def test_cau_hinh_sai_dung_truoc_khi_ket_noi(smtp, monkeypatch, capsys, key, value):
    if value:
        monkeypatch.setenv(key, value)
    else:
        monkeypatch.delenv(key)
    monkeypatch.setenv("SMTP_USER", "ca-nhan@gmail.com")      # khong duoc lay lam nguoi gui thay SENDER_EMAIL
    assert not notifier.send_email("Báo cáo", "<p>x</p>", recipient_override=["long.tran@namhapharma.com"])
    assert not mailer.send_password_email("qlv.mb@namhapharma.com", "mat-khau-tam-123")
    assert smtp["calls"] == [] and smtp["messages"] == []
    assert "mat-khau-tam-123" not in capsys.readouterr().out


def test_nguoi_nhan_ngoai_bi_m365_tu_choi_thi_bao_that_bai(smtp, capsys):
    smtp["refused"] = {"hop-thu-uat@outlook.com.vn": (451, b"4.4.4 Mail received as unauthenticated")}
    assert not notifier.send_email("Báo cáo", "<p>x</p>",
                                   recipient_override=["long.tran@namhapharma.com", "hop-thu-uat@outlook.com.vn"])
    assert "tu choi" in capsys.readouterr().out


def test_mac_dinh_van_dang_nhap_nhu_cu(smtp, monkeypatch):
    monkeypatch.delenv("SMTP_AUTH")
    monkeypatch.setenv("SMTP_USER", "service@example.invalid")
    monkeypatch.setenv("SMTP_PASSWORD", "mat-khau-smtp")
    assert notifier.send_email("Báo cáo", "<p>x</p>", recipient_override=["long.tran@namhapharma.com"])
    assert ("login", "service@example.invalid") in smtp["calls"]
