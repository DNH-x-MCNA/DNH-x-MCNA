# Kiểm cấu hình email QLV trước khi gửi thử

Chạy trên máy có cấu hình định gửi (máy 24), từ repo đã pull bản được duyệt:

```powershell
python C:\dnh_chatbot\scripts\kiem_tra_email_qlv.py
$LASTEXITCODE
```

Lệnh chỉ đọc file và biến môi trường trong tiến trình hiện tại, không dựng báo cáo,
không truy Bravo/kho dữ liệu, không kết nối SMTP/Teams hoặc gọi model. Không sửa
file, Task Scheduler hay service. Kết quả JSON chỉ chứa mã lỗi, tên trường, số thứ
tự dòng cấu hình và số QLV; không in email, mã nhân viên, mật khẩu hoặc webhook.

- Mã thoát **0**, `CONFIG_VALID_OFFLINE`: cấu trúc SMTP và cấu hình người nhận QLV
  đạt kiểm tra offline. **Chưa xác minh** mật khẩu/quyền SMTP, hộp thư thực nhận,
  mã nhân viên có tồn tại hay thuộc đúng miền/đội trong Bravo.
- Mã thoát **1**, `NEEDS_CONFIGURATION`: xem `errors`, sửa đúng trường trong cấu
  hình vận hành theo thông tin DNH cấp. `report_recipients[1]` là phần tử đầu tiên
  của danh sách YAML (tính cả lãnh đạo trước các QLV).
- `INPUT_ERROR`: kiểm file tại chỗ; không in thông báo parser vì có thể chứa bí mật.

Lệnh dùng thứ tự `.env` → `backend/.env` → `config/.env` (file sau ghi đè), giống
`main.load_env`; cấu hình ưu tiên `config.yaml` ở gốc, sau đó `config/config.yaml`.
Có thể chỉ định `--repo <thư mục repo>`. Biến của phiên PowerShell hiện tại có thể
khác tài khoản SYSTEM chạy Scheduler; đạt ở phiên này chưa xác nhận môi trường
của task. `${TEN_BIEN}` trong YAML được thay bằng môi trường như báo cáo thật.

Các điểm kiểm cho bàn giao SMTP DNH:

- Provider thực tế phải là SMTP; `auto` còn SendGrid key sẽ bị báo. Đặt
  `EMAIL_PROVIDER=smtp` theo [hướng dẫn SMTP](chuan_bi_mail_dnh_22-09.md).
- Thông số SMTP hợp lệ và TLS là `starttls` hoặc `ssl`; địa chỉ From có cấu trúc
  email. Không tự đoán server, mật khẩu, port hay quyền gửi của DNH.
- Có ít nhất một QLV/ASM/RM; từng người có audience, employee_code, miền, danh sách
  email hợp lệ và kênh xác nhận rõ. Runtime cũ mặc định OTC khi thiếu channel;
  phép kiểm bàn giao yêu cầu khai báo rõ để tránh tự suy phạm vi.
- Audience QLV không trùng tên với bất kỳ dòng nào khác, kể cả lãnh đạo; nếu trùng,
  gửi thử theo audience có thể chọn nhiều người nhận.
- Không kiểm UPN hay flow Teams: email QLV độc lập với việc Claude đang đổi flow.

Sau khi đạt và DNH xác nhận danh sách, anh Đăng gửi thử tới hộp thư đã duyệt, chọn
đúng một audience QLV. Runner Daily cần bản sửa #126 để truyền `--email-override`.
Email override không chặn Teams nếu bỏ lọc audience. Lưu thời điểm chạy, mã thoát
và xác nhận thư trong hộp thư trước khi mở lịch gửi thật; không dùng kết quả
offline này làm bằng chứng nghiệm thu thực nhận.
