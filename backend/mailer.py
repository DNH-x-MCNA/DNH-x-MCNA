# -*- coding: utf-8 -*-
"""
Gui email tai khoan qua SMTP da cau hinh. Khong ghi mat khau vao log.
"""
import os
import html
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

if __package__:
    from .mail_transport import smtp_settings, send_smtp_message, mail_failure_reason
else:
    # uvicorn main:app runs with backend/ as its working directory on machine 24.
    from mail_transport import smtp_settings, send_smtp_message, mail_failure_reason

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
    return smtp_settings()


def send_password_email(to_email: str, password: str, is_reset: bool = False,
                        giu_mat_khau_cu: bool = False) -> bool:
    """Gui email mat khau khoi tao / cap lai mat khau cho nhan vien qua SMTP Office365 hoac Gmail.

    giu_mat_khau_cu=True: mat khau tam cua "Quen mat khau" (29/09/2026) - mat khau cu van dung duoc
    cho toi khi nguoi dung dang nhap bang mat khau tam, noi ro de ai khong yeu cau thi khong hoang."""
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

    try:
        config = get_smtp_config()
    except Exception as e:
        _log_failure(mail_failure_reason(e))
        return False
    sender_email = config["sender"]

    action_title = "Cấp lại mật khẩu tài khoản" if is_reset else "Tài khoản đăng ký mới & Mật khẩu khởi tạo"
    subject = f"[Dược Nam Hà] {action_title}"
    email_html = html.escape(to_email)
    password_html = html.escape(password)
    if giu_mat_khau_cu:
        luu_y = (
            "<li>Mật khẩu hiện tại của bạn <strong>vẫn dùng được</strong>. Mật khẩu tạm ở trên có hiệu lực "
            "24 giờ; khi bạn đăng nhập bằng nó, mật khẩu cũ mới bị thay và mọi phiên đăng nhập cũ bị đăng xuất.</li>"
            "<li>Sau khi đăng nhập bằng mật khẩu tạm, bạn phải <strong>Đổi mật khẩu mới</strong> trước khi dùng tiếp.</li>"
            "<li>Nếu bạn không yêu cầu, cứ bỏ qua email này: tiếp tục đăng nhập bằng mật khẩu cũ là mật khẩu tạm bị huỷ.</li>"
        )
    else:
        luu_y = (
            "<li>Bạn có thể đăng nhập ngay bằng email này và mật khẩu được cấp ở trên.</li>"
            "<li>Vui lòng thực hiện <strong>Đổi mật khẩu mới</strong> ngay tại menu tài khoản sau khi đăng nhập thành công.</li>"
        )

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background: #ffffff;">
      <div style="background: linear-gradient(135deg, #0056b3, #00875a); padding: 24px; text-align: center; color: white;">
        <h2 style="margin: 0; font-size: 22px; text-transform: uppercase; letter-spacing: 1px;">CÔNG TY CỔ PHẦN DƯỢC NAM HÀ</h2>
        <p style="margin: 6px 0 0 0; opacity: 0.9; font-size: 14px;">Hệ thống AI Chatbot Quản trị Báo cáo</p>
      </div>
      <div style="padding: 24px; color: #333333; line-height: 1.6;">
        <p>Xin chào <strong>{email_html}</strong>,</p>
        <p>Hệ thống đã nhận được yêu cầu {'cấp lại mật khẩu' if is_reset else 'khởi tạo tài khoản mới'} cho email công ty của bạn.</p>
        
        <div style="background: #eef9f5; border-left: 4px solid #00875a; padding: 16px; margin: 20px 0; border-radius: 4px;">
          <p style="margin: 0 0 8px 0; font-size: 14px; color: #333;">🔑 <strong>Mật khẩu đăng nhập ngẫu nhiên của bạn:</strong></p>
          <div style="font-size: 22px; font-family: monospace; font-weight: bold; color: #00875a; background: #ffffff; padding: 8px 14px; border-radius: 4px; display: inline-block; border: 1px dashed #00875a;">{password_html}</div>
        </div>

        <p><strong>Lưu ý quan trọng:</strong></p>
        <ul>
          {luu_y}
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
    # 30/09/2026: ten co dau ma ghep chuoi "Ten <dia chi>" thi thu vien email ma hoa CA cum, ke ca dia chi
    # (=?utf-8?b?...?=) - may chu nhan khong doc duoc From. formataddr chi ma hoa phan ten.
    msg["From"] = formataddr(("Dược Nam Hà AI Bot", sender_email))
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        send_smtp_message(msg, [to_email], config)
        logger.info(f"✅ Gửi email thành công tới: {to_email}")
        print(f"[SMTP SUCCESS] Da gui email thanh cong toi {to_email}")
        return True
    except Exception as e:
        _log_failure(mail_failure_reason(e))
        return False
