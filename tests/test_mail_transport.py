"""Offline preparation for DNH SMTP migration; every outgoing transport is mocked."""
import smtplib
import ssl
import os
from email import message_from_string

import pytest

from backend import mailer, mail_transport as transport
from src import notifier


@pytest.fixture
def mail_setup(monkeypatch):
    for key in list(os.environ):
        if key.startswith("SMTP_") or key in {
            "EMAIL_PROVIDER", "SENDGRID_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAILS",
        }:
            monkeypatch.delenv(key)
    monkeypatch.setenv("SMTP_USER", "service@example.invalid")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password-not-for-logs")
    monkeypatch.setenv("SMTP_SERVER", "smtp.example.invalid")
    monkeypatch.setenv("SENDER_EMAIL", "bot@example.invalid")
    monkeypatch.setattr(mailer, "_load_env_file", lambda: None)
    monkeypatch.setattr(notifier, "load_config", lambda: {"email": {
        "smtp_server": "legacy.example.invalid", "smtp_port": 587, "use_tls": True,
        "sender_name": "DNH", "recipient_emails": ["old@example.invalid"],
    }})
    state = {"calls": [], "messages": [], "refused": {}}

    class FakeSMTP:
        def __init__(self, host, port, *, timeout, context=None):
            state["calls"].append(("connect", host, port, timeout, context))

        def ehlo(self):
            state["calls"].append(("ehlo",))

        def starttls(self, *, context):
            state["calls"].append(("starttls", context))
            if state.get("tls_error"):
                raise state["tls_error"]

        def login(self, user, password):
            state["calls"].append(("login", user, password))
            if state.get("login_error"):
                raise state["login_error"]

        def sendmail(self, sender, recipients, body):
            state["messages"].append((sender, recipients, message_from_string(body)))
            if state.get("send_error"):
                raise state["send_error"]
            return state["refused"]

        def quit(self):
            state["calls"].append(("quit",))
            if state.get("quit_error"):
                raise state["quit_error"]

        def close(self):
            state["calls"].append(("close",))

    monkeypatch.setattr(transport.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(transport.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(notifier, "send_email_via_sendgrid", lambda *a, **k:
                        pytest.fail("Unexpected SendGrid request"))
    return state


def _send_report(**kwargs):
    return notifier.send_email("Báo cáo tuần", "<p>Công nợ tháng này</p>", **kwargs)


def test_explicit_smtp_ignores_stale_sendgrid_key_and_preserves_audience(mail_setup, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SENDGRID_API_KEY", "unused-stale-key")
    monkeypatch.setenv("RECIPIENT_EMAILS", "unrelated@example.invalid")
    assert _send_report(recipient_override=["tester@example.invalid"], importance="high")
    sender, recipients, msg = mail_setup["messages"][0]
    assert sender == "bot@example.invalid"
    assert recipients == ["tester@example.invalid"]
    assert msg["To"] == "tester@example.invalid"
    assert msg["Importance"].lower() == "high" and msg["X-Priority"] == "1"
    assert msg.get_payload()[0].get_payload(decode=True).decode("utf-8") == "<p>Công nợ tháng này</p>"


@pytest.mark.parametrize("provider", [None, "auto", "sendgrid"])
def test_legacy_sendgrid_choice_is_preserved(mail_setup, monkeypatch, provider):
    if provider:
        monkeypatch.setenv("EMAIL_PROVIDER", provider)
    monkeypatch.setenv("SENDGRID_API_KEY", "fake-key")
    seen = []
    monkeypatch.setattr(notifier, "send_email_via_sendgrid",
                        lambda *args, **kw: seen.append((args, kw)) or True)
    assert _send_report(recipient_override=["tester@example.invalid"], importance="high")
    assert len(seen) == 1 and seen[0][1]["recipient_override"] == ["tester@example.invalid"]
    assert mail_setup["calls"] == []


def test_sendgrid_failure_does_not_fall_back_to_smtp(mail_setup, monkeypatch):
    monkeypatch.setenv("SENDGRID_API_KEY", "fake-key")
    monkeypatch.setattr(notifier, "send_email_via_sendgrid", lambda *a, **k: False)
    assert not _send_report()
    assert mail_setup["calls"] == []


@pytest.mark.parametrize("provider", ["sendgrid", "typo"])
def test_invalid_provider_or_missing_sendgrid_key_sends_nothing(mail_setup, monkeypatch, provider):
    monkeypatch.setenv("EMAIL_PROVIDER", provider)
    assert not _send_report()
    assert mail_setup["calls"] == []


def test_default_smtp_uses_timeout_and_verified_starttls_before_login(mail_setup):
    assert _send_report()
    calls = mail_setup["calls"]
    assert [c[0] for c in calls] == ["connect", "ehlo", "starttls", "ehlo", "login", "quit"]
    assert calls[0][1:4] == ("smtp.example.invalid", 587, 15)
    context = calls[2][1]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize("account_mail", [False, True])
def test_both_mail_paths_support_explicit_ssl(mail_setup, monkeypatch, account_mail):
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "20")
    ok = (mailer.send_password_email("tester@example.invalid", "new-account-password")
          if account_mail else _send_report())
    assert ok
    calls = mail_setup["calls"]
    assert [c[0] for c in calls] == ["connect", "ehlo", "login", "quit"]
    assert calls[0][1:4] == ("smtp.example.invalid", 465, 20)
    assert calls[0][4].check_hostname and calls[0][4].verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize("key,value", [
    ("SMTP_PORT", "bad-secret-value"), ("SMTP_PORT", "70000"),
    ("SMTP_TIMEOUT_SECONDS", "0"), ("SMTP_TIMEOUT_SECONDS", "nan"),
    ("SMTP_TIMEOUT_SECONDS", "inf"), ("SMTP_TIMEOUT_SECONDS", "121"),
    ("SMTP_SECURITY", "bad-secret-value"), ("SMTP_PASSWORD", ""),
])
def test_bad_settings_fail_cleanly_before_network_on_both_paths(mail_setup, monkeypatch, capsys, key, value):
    monkeypatch.setenv(key, value)
    assert not _send_report()
    assert not mailer.send_password_email("tester@example.invalid", "new-account-password")
    assert mail_setup["calls"] == []
    output = capsys.readouterr().out
    assert "bad-secret-value" not in output
    assert "new-account-password" not in output


@pytest.mark.parametrize("error", [
    smtplib.SMTPNotSupportedError("server-echo-secret"),
    ssl.SSLCertVerificationError("server-echo-secret"),
])
def test_tls_failure_never_logs_in_or_sends(mail_setup, capsys, error):
    mail_setup["tls_error"] = error
    assert not _send_report()
    assert not mailer.send_password_email("tester@example.invalid", "new-account-password")
    assert not any(c[0] == "login" for c in mail_setup["calls"])
    assert mail_setup["messages"] == []
    assert "server-echo-secret" not in capsys.readouterr().out


def test_authentication_failure_is_not_logged_with_server_reply(mail_setup, capsys, caplog):
    mail_setup["login_error"] = smtplib.SMTPAuthenticationError(535, b"smtp-password-not-for-logs")
    assert not _send_report()
    assert not mailer.send_password_email("tester@example.invalid", "new-account-password")
    assert mail_setup["messages"] == []
    output = capsys.readouterr().out + caplog.text
    assert "xac thuc" in output
    assert "smtp-password-not-for-logs" not in output
    assert "new-account-password" not in output


def test_timeout_fails_without_retrying_or_leaking_content(mail_setup, capsys):
    mail_setup["send_error"] = TimeoutError("echo-of-message-or-password")
    assert not _send_report()
    assert len(mail_setup["messages"]) == 1
    assert mail_setup["calls"][-1][0] == "quit"
    assert "echo-of-message-or-password" not in capsys.readouterr().out


def test_partial_recipient_refusal_is_not_reported_as_success(mail_setup):
    mail_setup["refused"] = {"bad@example.invalid": (550, b"refused")}
    assert not _send_report(recipient_override=["ok@example.invalid", "bad@example.invalid"])
    assert len(mail_setup["messages"]) == 1


def test_disconnect_after_acceptance_does_not_turn_into_retry(mail_setup):
    mail_setup["quit_error"] = smtplib.SMTPServerDisconnected("closed after DATA")
    assert _send_report()
    assert len(mail_setup["messages"]) == 1
    assert mail_setup["calls"][-1][0] == "close"


def test_no_recipients_sends_nothing(mail_setup, monkeypatch):
    monkeypatch.setattr(notifier, "load_config", lambda: {"email": {}})
    assert not _send_report()
    assert mail_setup["calls"] == []


def test_legacy_report_yaml_tls_setting_is_preserved(mail_setup, monkeypatch):
    monkeypatch.setattr(notifier, "load_config", lambda: {"email": {
        "use_tls": False, "recipient_emails": ["tester@example.invalid"],
    }})
    assert _send_report()
    assert not any(c[0] == "starttls" for c in mail_setup["calls"])


def test_account_email_remains_smtp_even_when_reports_use_sendgrid(mail_setup, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "sendgrid")
    monkeypatch.setenv("SENDGRID_API_KEY", "fake-key")
    assert mailer.send_password_email("tester@example.invalid", "new-account-password", is_reset=True)
    sender, recipients, msg = mail_setup["messages"][0]
    assert sender == "bot@example.invalid" and recipients == ["tester@example.invalid"]
    assert "new-account-password" in msg.get_payload()[0].get_payload(decode=True).decode("utf-8")


def test_yaml_smtp_defaults_work_when_environment_is_absent(mail_setup, monkeypatch):
    for key in ["SMTP_USER", "SMTP_PASSWORD", "SENDER_EMAIL", "SMTP_SERVER"]:
        monkeypatch.delenv(key)
    monkeypatch.setattr(notifier, "load_config", lambda: {"email": {
        "smtp_user": "legacy@example.invalid", "smtp_password": "legacy-password",
        "smtp_server": "legacy.example.invalid", "smtp_port": 2525,
        "recipient_emails": ["tester@example.invalid"],
    }})
    assert _send_report()
    assert mail_setup["calls"][0][1:4] == ("legacy.example.invalid", 2525, 15)
    assert mail_setup["messages"][0][0] == "legacy@example.invalid"
