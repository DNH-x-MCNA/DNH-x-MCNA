# Chuẩn bị chuyển máy chủ gửi mail DNH — 22/09/2026

Trạng thái: chuẩn bị code trên dev, chưa đổi cấu hình máy 24, chưa gửi thử qua DNH.
Domain dự kiến là `chatbot.namhatrading.com`; endpoint API cố định và DNS chờ IT.

## Phần đã chuẩn bị

- `EMAIL_PROVIDER=auto|smtp|sendgrid` chọn đường gửi **báo cáo/cảnh báo email**.
  Không đặt biến hoặc đặt `auto`: giữ cách cũ, có SendGrid key thì chọn SendGrid,
  nếu không thì SMTP. `smtp` buộc dùng SMTP dù vẫn còn SendGrid key.
  Giá trị sai hoặc chọn SendGrid nhưng thiếu key: dừng gửi, trả kết quả thất bại.
- Email cấp/reset tài khoản luôn dùng SMTP như trước; không đưa mật khẩu tài khoản
  qua SendGrid chỉ vì báo cáo đang dùng SendGrid.
- Hai đường SMTP dùng chung kiểm tra cấu hình, timeout và xử lý lỗi tại
  `backend/mail_transport.py`. Không ghi phản hồi SMTP thô chứa nội dung/bí mật.
- Hỗ trợ STARTTLS và TLS trực tiếp; kiểm chứng chỉ bằng trust store mặc định.
  Cấu hình TLS sai không tự hạ xuống kết nối thường.
- Nếu một phần người nhận bị từ chối thì báo thất bại, không báo cả lượt thành công.
  Không tự chuyển nhà cung cấp hay gửi lại cả danh sách; các địa chỉ khác có thể đã nhận.
- Lỗi QUIT sau khi server chấp nhận DATA không làm lượt đã gửi thành thất bại.

Đây chưa phải xác nhận mailserver DNH tương thích. Hiện hỗ trợ xác thực SMTP bằng
username/password. Nếu IT yêu cầu OAuth hoặc relay theo IP không dùng mật khẩu,
phải bổ sung và kiểm thử sau khi nhận đặc tả; không tự suy đoán.

## Thông tin chờ IT

Hostname, port, STARTTLS/TLS trực tiếp, kiểu xác thực, địa chỉ From được phép,
whitelist kết nối từ máy 24, chứng chỉ/trust chain và người nhận 6 audience.
IT xác nhận cấu hình xác thực domain mail; bí mật truyền qua kênh riêng.

## Cấu hình sau khi IT xác nhận

Các giá trị dưới đây là mẫu, không chạy nguyên mẫu trên production:

```dotenv
EMAIL_PROVIDER=smtp
SMTP_SERVER=<hostname IT cung cấp>
SMTP_PORT=<port IT cung cấp>
SMTP_SECURITY=starttls
SMTP_TIMEOUT_SECONDS=15
SMTP_USER=<tài khoản dịch vụ>
SMTP_PASSWORD=<bí mật bàn giao riêng>
SENDER_EMAIL=<địa chỉ From được phép>
```

- `SMTP_SECURITY=starttls`: nâng kết nối lên TLS trước khi đăng nhập.
- `SMTP_SECURITY=ssl`: TLS ngay khi kết nối; đặt port đúng thông tin IT, không tự suy ra port.
- `SMTP_SECURITY=none`: chỉ để tương thích cấu hình không TLS cũ; không dùng để né lỗi TLS.
- Không đặt `SMTP_SECURITY`: báo cáo giữ `email.use_tls` trong YAML (mặc định true);
  email tài khoản mặc định STARTTLS.
- Timeout áp dụng từng thao tác socket, không phải tổng thời gian gửi cả báo cáo.

Không thay đổi cách nạp `.env` trong bản chuẩn bị này:

- `main.py` báo cáo nạp `.env` → `backend/.env` → `config/.env`, file sau ghi đè file trước.
- Backend nạp môi trường tiến trình trước, sau đó `backend/.env` rồi `.env` ở gốc
  cho những biến chưa có. Mailer còn đọc `backend/.env` khi biến trống.
- `src.notifier` khi dùng trực tiếp cũng nạp dotenv; báo cáo còn có fallback YAML.

Vì vậy phải rà cả các file và biến của tài khoản dịch vụ/Task Scheduler; không chỉ
sửa `.env` ở gốc rồi coi đã chuyển. Đặt bộ SMTP đã duyệt nhất quán ở những nơi thực
sự được dùng, bỏ giá trị SMTP cũ ghi đè và không in password/key ra log.

## Thứ tự kiểm và triển khai

1. Review/merge bản chuẩn bị sau test. Máy 24 chỉ pull commit được duyệt.
2. Lưu cấu hình cũ trong nơi bảo mật, chốt cửa sổ chuyển đổi tránh trùng lịch gửi.
3. IT cấu hình tài khoản/quyền gửi; kiểm kết nối và TLS từ máy 24.
4. Đặt cấu hình SMTP DNH; restart tiến trình dài hạn đang giữ môi trường cũ.
5. Gửi thử tới Linh bằng recipient override: Weekly/Monthly cho 6 audience;
   kiểm email cấp/reset trên tài khoản thử. Lưu xác nhận thực nhận và log gửi.
6. Chỉ sau khi xác nhận mới gỡ override, mở người nhận đã được DNH duyệt và kiểm
   lần chạy từ Task Scheduler. Không mở năm audience còn dùng hộp thư UAT.
7. Nếu lỗi, khôi phục cấu hình trước chuyển và restart đúng tiến trình. Chỉ gửi lại
   người chưa nhận, đặc biệt khi server từ chối một phần danh sách hoặc timeout sau DATA.

Không đổi DNS, không deploy và không gửi mail thật chỉ để kiểm code ở dev.
Test tự động của bản chuẩn bị dùng SMTP/SendGrid giả.

Kết quả dev 22/09: bộ test mục tiêu 37 passed; full suite 921 passed, 1 deselected
(integration dựng báo cáo thật bị loại mặc định), 24 cảnh báo datetime adapter cũ.
Chưa chạy integration với SMTP DNH vì chưa có cấu hình/đặc tả của IT.

```powershell
python -m pytest tests/test_mail_transport.py tests/test_tai_khoan_email.py tests/test_report_task_runtime.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Tham chiếu transport: https://docs.python.org/3.12/library/smtplib.html
