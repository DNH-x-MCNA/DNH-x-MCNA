"""Shared SMTP settings/transport. Importing this module never loads files or sends mail."""
import math
import os
import smtplib
import ssl


class MailConfigurationError(ValueError):
    """An actionable configuration error that contains no credentials."""


def report_email_provider():
    """Keep legacy SendGrid preference unless the operator explicitly selects SMTP."""
    provider = os.getenv("EMAIL_PROVIDER", "auto").strip().lower() or "auto"
    if provider not in {"auto", "smtp", "sendgrid"}:
        raise MailConfigurationError("EMAIL_PROVIDER chi nhan auto, smtp hoac sendgrid.")
    has_key = bool(os.getenv("SENDGRID_API_KEY", "").strip())
    if provider == "sendgrid" and not has_key:
        raise MailConfigurationError("EMAIL_PROVIDER=sendgrid nhung thieu SENDGRID_API_KEY.")
    return ("sendgrid" if has_key else "smtp") if provider == "auto" else provider


def smtp_settings(defaults=None):
    """Resolve already-loaded environment over legacy YAML defaults; validate offline.

    Username/password SMTP is the currently supported authentication method. Do not
    silently guess an unauthenticated relay or OAuth setup before DNH supplies it.
    """
    defaults = defaults or {}

    def value(env_key, config_key, default=""):
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
        config_value = defaults.get(config_key)
        return default if config_value is None or config_value == "" else config_value

    user = str(value("SMTP_USER", "smtp_user")).strip()
    password = str(value("SMTP_PASSWORD", "smtp_password"))
    sender = str(value("SENDER_EMAIL", "sender_email", user)).strip()
    host = str(value("SMTP_SERVER", "smtp_server", "smtp.office365.com")).strip()
    # Absent SMTP_SECURITY preserves the existing report use_tls setting; account
    # emails have no YAML defaults and therefore continue to require STARTTLS.
    security = (os.getenv("SMTP_SECURITY", "").strip().lower()
                or ("starttls" if defaults.get("use_tls", True) else "none"))
    if security not in {"starttls", "ssl", "none"}:
        raise MailConfigurationError("SMTP_SECURITY chi nhan starttls, ssl hoac none.")
    try:
        port = int(value("SMTP_PORT", "smtp_port", 587))
        timeout = float(value("SMTP_TIMEOUT_SECONDS", "smtp_timeout_seconds", 15))
    except (TypeError, ValueError):
        raise MailConfigurationError("SMTP_PORT va SMTP_TIMEOUT_SECONDS phai la so.") from None
    if not 1 <= port <= 65535:
        raise MailConfigurationError("SMTP_PORT phai tu 1 den 65535.")
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise MailConfigurationError("SMTP_TIMEOUT_SECONDS phai > 0 va <= 120.")
    if not user or not password or user == "hophu_email@namhapharma.com":
        raise MailConfigurationError("Thieu SMTP_USER/SMTP_PASSWORD.")
    if not host or not sender or any(c in sender + user + host for c in "\r\n"):
        raise MailConfigurationError("SMTP_SERVER, SMTP_USER hoac SENDER_EMAIL khong hop le.")
    return {"user": user, "password": password, "sender": sender, "server": host,
            "port": port, "security": security, "timeout": timeout}


def send_smtp_message(message, recipients, settings):
    """Raise on any rejected recipient. Never fall back to another provider."""
    if not recipients:
        raise MailConfigurationError("Chua co nguoi nhan email.")
    server = None
    try:
        if settings["security"] == "ssl":
            server = smtplib.SMTP_SSL(settings["server"], settings["port"],
                                      timeout=settings["timeout"], context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(settings["server"], settings["port"], timeout=settings["timeout"])
        server.ehlo()
        if settings["security"] == "starttls":
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(settings["user"], settings["password"])
        refused = server.sendmail(settings["sender"], recipients, message.as_string())
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    finally:
        if server is not None:
            try:
                server.quit()
            except OSError:
                # A disconnect after DATA acceptance must not turn a successful send
                # into a retry/duplicate. Still close the socket after a failed QUIT.
                server.close()


def mail_failure_reason(error):
    """Log only controlled messages: SMTP replies may echo credentials or content."""
    if isinstance(error, MailConfigurationError):
        return str(error)
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "SMTP tu choi xac thuc; kiem tai khoan va quyen gui."
    if isinstance(error, ssl.SSLError):
        return "Khong thiet lap duoc TLS; kiem chung chi va SMTP_SECURITY."
    if isinstance(error, TimeoutError):
        return "SMTP qua thoi gian cho; kiem ket noi tu may chay dich vu."
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "SMTP tu choi mot hoac nhieu nguoi nhan; khong tu gui lai cac dia chi da nhan."
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return "SMTP khong ho tro TLS/xac thuc da chon; can xac nhan cau hinh voi IT."
    return "Gui mail that bai (%s); kiem log phia mailserver." % type(error).__name__
