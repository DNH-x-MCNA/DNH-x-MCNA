# -*- coding: utf-8 -*-
"""
Module gui email mat khau tu dong qua Outlook / Office365 SMTP hoac Gmail.
Hỗ trợ fallback ghi log local khi đang thử nghiệm môi trường Local Test hoặc khi SMTP bị chặn.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


def _load_env_file():
    """Doc va nap cac bien trong file backend/.env neu os.environ chua co."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and not os.environ.get(k):
                        os.environ[k] = v


def get_smtp_config():
    _load_env_file()
    return {
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "sender": os.environ.get("SENDER_EMAIL", os.environ.get("SMTP_USER", "")).strip(),
        "server": os.environ.get("SMTP_SERVER", "smtp.office365.com").strip(),
        "port": int(os.environ.get("SMTP_PORT", "587")),
    }


def send_password_email(to_email: str, password: str, is_reset: bool = False) -> bool:
    """Gui email mat khau khoi tao / cap lai mat khau cho nhan vien qua SMTP Office365 hoac Gmail."""
    config = get_smtp_config()
    smtp_user = config["user"]
    smtp_password = config["password"]
    sender_email = config["sender"]
    smtp_server = config["server"]
    smtp_port = config["port"]

    # 29/07/2026 - TUYET DOI KHONG ghi mat khau ra log/stdout.
    # Ban truoc co ham _log_local_fallback() ghi mat khau DANG CHU THUONG vao
    # backend/logs/sent_passwords.log va print ra stdout, chay trong CA HAI truong hop: chua cau hinh
    # SMTP, va SMTP gui loi bat ky ly do gi. Nghia la bat ky ai doc duoc file log tren may chu (hoac
    # log uvicorn) deu thay mat khau that cua moi nhan vien tung dang ky/quen mat khau. Da bo han.
    #
    # Khi can cuu canh vi SMTP chua san sang: mat khau van duoc tra ve MOT LAN trong response cua
    # POST /admin/users/create (truong generated_password) de admin doc tren man hinh va chuyen tay
    # cho nhan vien - khong bao gio xuong dia.
    def _log_failure(reason: str):
        """Chi ghi SU CO, khong bao gio ghi mat khau."""
        logger.warning(f"Khong gui duoc email mat khau toi {to_email}: {reason}")
        print(f"[MAILER] Khong gui duoc email toi {to_email}: {reason}")

    if not smtp_user or not smtp_password or smtp_user == "hophu_email@namhapharma.com":
        _log_failure("Chua cau hinh SMTP_USER/SMTP_PASSWORD trong backend/.env")
        return False

    action_title = "Cấp lại mật khẩu tài khoản" if is_reset else "Tài khoản đăng ký mới & Mật khẩu khởi tạo"
    subject = f"[Dược Nam Hà] {action_title}"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background: #ffffff;">
      <div style="background: linear-gradient(135deg, #0056b3, #00875a); padding: 24px; text-align: center; color: white;">
        <h2 style="margin: 0; font-size: 22px; text-transform: uppercase; letter-spacing: 1px;">CÔNG TY CỔ PHẦN DƯỢC NAM HÀ</h2>
        <p style="margin: 6px 0 0 0; opacity: 0.9; font-size: 14px;">Hệ thống AI Chatbot Quản trị Báo cáo</p>
      </div>
      <div style="padding: 24px; color: #333333; line-height: 1.6;">
        <p>Xin chào <strong>{to_email}</strong>,</p>
        <p>Hệ thống đã nhận được yêu cầu {'cấp lại mật khẩu' if is_reset else 'khởi tạo tài khoản mới'} cho email công ty của bạn.</p>
        
        <div style="background: #eef9f5; border-left: 4px solid #00875a; padding: 16px; margin: 20px 0; border-radius: 4px;">
          <p style="margin: 0 0 8px 0; font-size: 14px; color: #333;">🔑 <strong>Mật khẩu đăng nhập ngẫu nhiên của bạn:</strong></p>
          <div style="font-size: 22px; font-family: monospace; font-weight: bold; color: #00875a; background: #ffffff; padding: 8px 14px; border-radius: 4px; display: inline-block; border: 1px dashed #00875a;">{password}</div>
        </div>

        <p><strong>Lưu ý quan trọng:</strong></p>
        <ul>
          <li>Bạn có thể đăng nhập ngay bằng email này và mật khẩu được cấp ở trên.</li>
          <li>Vui lòng thực hiện <strong>Đổi mật khẩu mới</strong> ngay tại menu tài khoản sau khi đăng nhập thành công.</li>
        </ul>

        <p style="font-size: 13px; color: #777; margin-top: 24px;">Nếu bạn không yêu cầu hành động này, vui lòng liên hệ ngay với Quản trị viên hệ thống DNH.</p>
      </div>
      <div style="background: #f8f9fa; text-align: center; padding: 12px; font-size: 12px; color: #888; border-top: 1px solid #eee;">
        © 2026 Dược Nam Hà (Nam Ha Pharma). All rights reserved.
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Dược Nam Hà AI Bot <{sender_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(sender_email, [to_email], msg.as_string())
        server.quit()
        logger.info(f"✅ Gửi email thành công tới: {to_email}")
        print(f"[SMTP SUCCESS] Da gui email thanh cong toi {to_email}")
        return True
    except Exception as e:
        _log_failure(f"SMTP error: {e}")
        return False
