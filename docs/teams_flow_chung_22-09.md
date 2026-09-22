# Chuyển Daily và alert DNH sang một Flow Teams chung

Phạm vi đã chốt: **chat cá nhân của từng quản lý**. Chưa có UPN Teams của người
nhận, chưa tạo/kiểm Flow trong tenant và chưa bật trên máy 24. Địa chỉ mailserver
riêng không mặc định là tài khoản đăng nhập Teams. Không gửi thử thật trước khi
xác định tài khoản nhận và được Đăng đồng ý.

## 1. Hành vi và cấu hình

- `TEAMS_DELIVERY_MODE=legacy` (mặc định): dùng các Flow đang có, không đọc bảng mới.
- `TEAMS_DELIVERY_MODE=shared`: Daily và alert nghiệp vụ dùng
  `TEAMS_SHARED_WEBHOOK_URL`; danh sách đích lấy từ
  `config/teams_recipients.local.json`. Có thể đổi đường dẫn bằng
  `TEAMS_RECIPIENTS_FILE` (đường dẫn tương đối tính từ gốc repo).
- File JSON chỉ chứa `tên audience: UPN Teams`, không chứa quyền, webhook hoặc
  nội dung báo cáo. Tên phải khớp đầy đủ `report_recipients` trong config hiện hành.
  Thiếu/thừa tên, trùng khóa, UPN trống hoặc webhook sai: dừng trước khi gửi; không
  quay về webhook cũ và không lấy `emails` làm người nhận Teams.
- Daily vẫn dựng một bản riêng cho mỗi audience. Một người nhận nhiều audience vẫn
  nhận đủ các bản Daily. Alert khớp theo vùng/kênh, khử trùng cùng người nhận cho
  cùng cảnh báo; card CRITICAL chỉ gộp những cảnh báo người đó được nhận.
- QLV vẫn đi qua nhánh khóa theo đội hiện có; không nhận alert toàn miền. Không
  mở thêm audience QLV trong đợt này.
- Watchdog hạ tầng dùng người nhận `C-Level (Toàn quốc)` trong chế độ shared.
  `WATCHDOG_TEAMS_WEBHOOK` chỉ còn áp dụng trong chế độ legacy.
- Weekly/Monthly qua email giữ nguyên; không đổi `emails`, SMTP, phạm vi hoặc lịch.

## 2. Tạo Flow mới trong Power Automate

Giữ các Flow cũ để khôi phục. Chưa tắt Flow cũ chỉ vì đã tạo xong Flow mới.

1. Tạo Flow tên `DNH - Teams - Shared`, dùng connection Microsoft Teams đã được
   DNH cho phép gửi đến các quản lý. Chọn trigger **When a Teams webhook request
   is received**.
2. Backend hiện gọi signed webhook không có Entra bearer token. Trigger cần kiểu
   **Anyone** tương thích cách gọi này; URL có chữ ký là bí mật, chỉ lưu trên máy
   chạy. Nếu IT chỉ cho phép caller được Entra xác thực, dừng bước kích hoạt để
   bổ sung token; không tự nới chính sách tenant. Các lựa chọn xác thực được mô tả
   trong [Teams connector](https://learn.microsoft.com/en-us/connectors/teams/#when-a-teams-webhook-request-is-received).
3. Thêm **Condition**: trường `recipient` và `audience` không trống, và
   `length(triggerBody()?['attachments'])` bằng `1`. Nhánh sai dùng **Terminate → Failed**,
   không gán người nhận mặc định. Payload hiện tại luôn chứa một Adaptive Card.
4. Trong nhánh đúng, thêm **Post card in a chat or channel** (không chọn action
   chờ phản hồi). Thiết lập:

   | Trường | Giá trị |
   |---|---|
   | Post as | Flow bot |
   | Post in | Chat with Flow bot |
   | Recipient | Expression: `triggerBody()?['recipient']` |
   | Adaptive Card | Expression: `string(first(triggerBody()?['attachments'])?['content'])` |

   Chọn Expression cho hai trường cuối, không dán như chuỗi văn bản cố định.
   Không thêm vòng lặp qua danh sách sáu quản lý trong Flow: mỗi HTTP request đã
   chỉ định một người nhận và một card. Xem
   [cách gửi card đến người dùng](https://learn.microsoft.com/en-us/power-automate/overview-adaptive-cards).
5. Save. Lưu URL trigger riêng trên máy triển khai, không gửi URL vào chat/Git.
   Connection phải dùng tài khoản đúng tenant và Workflows được IT cho phép.
6. Mẫu body để đối chiếu khi kiểm Run history:
   `docs/teams_shared_flow_payload.example.json`. Thay placeholder bằng UPN thử đã
   được duyệt; đây chỉ là mẫu, không phải gói import Flow hay bằng chứng đã gửi.

## 3. Chuẩn bị người nhận và kiểm miễn phí

Sau khi PR đã review/gộp và máy 24 đã kéo bản chốt, sao chép mẫu **nếu file local
chưa tồn tại**. Không ghi đè danh sách đã cấu hình:

```powershell
Set-Location C:\dnh_chatbot
if (-not (Test-Path -LiteralPath .\config\teams_recipients.local.json)) {
    Copy-Item -LiteralPath .\config\teams_recipients.example.json -Destination .\config\teams_recipients.local.json
}
notepad .\config\teams_recipients.local.json
```

Điền đúng UPN cho cả sáu audience. Khi kiểm riêng với một tester, có thể tạm điền
cùng UPN đã được duyệt vào cả sáu dòng; người đó phải được phép xem toàn bộ phạm vi.
Ghi lại đây là danh sách thử và thay bằng danh sách chính thức trước khi bật lịch.
File local đã được gitignore. Không lấy một email giả để vượt kiểm cấu hình.

Trong `config/.env` trên máy 24, lưu các biến dưới đây bằng trình soạn thảo;
giữ `legacy` trong lúc chuẩn bị:

```dotenv
TEAMS_DELIVERY_MODE=legacy
TEAMS_SHARED_WEBHOOK_URL=THAY_BANG_SIGNED_WEBHOOK_MOI
TEAMS_RECIPIENTS_FILE=config/teams_recipients.local.json
```

Root `.env` → `backend/.env` → `config/.env`: file sau ghi đè file trước cho report
runner, preflight và watchdog. Kiểm các khai báo trùng trước khi chuyển; không in
toàn bộ env hoặc URL ra log. Không commit file env hay file local.

```powershell
python .\scripts\check_teams_routing.py --shared
if ($LASTEXITCODE -ne 0) { throw "Cấu hình Flow chung chưa đạt; chưa bật lịch." }
```

Lệnh này chỉ đọc cấu hình và in audience/phạm vi/UPN; không gọi Bravo, model hoặc
webhook, không thay đổi môi trường của dịch vụ. `PASS cấu hình` chưa chứng minh
tài khoản tồn tại trong Teams hoặc Flow gửi được.

## 4. Kiểm thực nhận sau khi có UPN

Chỉ chạy khi Đăng đã duyệt tài khoản nhận thử. Lệnh sau **gửi thật một card giả**
theo UPN đang gán cho C-Level; kiểm lại file local trước khi chạy:

```powershell
python .\scripts\check_teams_routing.py --shared --send-probe --audience "C-Level (Toàn quốc)"
if ($LASTEXITCODE -ne 0) { throw "Gửi card thử thất bại." }
```

Kiểm Run history của Flow và chat Teams thực tế. HTTP 202 chỉ cho biết trigger đã
nhận request, không bảo đảm action Teams đã chạy thành công. Sau đó lặp có kiểm
soát cho các audience còn lại với `--audience` đúng tên.

Sau khi card giả đạt, đối chiếu một lượt Daily thực và cảnh báo đúng scope trong
khung thử đã duyệt: C-Level toàn công ty; Bắc/Trung/Nam riêng miền; OTC/ETC riêng
kênh. Người nhận nhiều audience vẫn có nhiều bản Daily khác nhau. Không tạo cảnh
báo kinh doanh giả trên dữ liệu/state production để kích thử.

## 5. Chuyển chính thức và khôi phục

1. Ghi nhận commit đã test, sao lưu cấu hình env/local trước khi đổi. Chốt danh
   sách người nhận chính thức và giờ chuyển tránh lượt gửi theo lịch.
2. Đặt `TEAMS_DELIVERY_MODE=shared` trong `config/.env` rồi chạy preflight không
   có `--shared` để kiểm đúng cấu hình sẽ được nạp khi chạy thật.
3. Khởi động lại `DNH_Realtime_Alerts` trong khung triển khai được Đăng duyệt.
   Scheduled Tasks Daily và watchdog đọc cấu hình ở lần chạy tiếp theo; không cần
   sửa action/lịch. Không restart chatbot chỉ để đổi đích gửi Teams.
4. Theo dõi Daily đầu tiên, alert CRITICAL và watchdog: đúng người, đúng phạm vi,
   không gửi lại người đã nhận thành công khi người khác bị lỗi HTTP.
5. Chỉ ngừng dùng Flow cũ sau khi kiểm các nguồn gửi khác trong tenant. Phần
   backend/watchdog thuộc repo này đã đi qua routing shared; các Flow/lịch ngoài
   repo cần người vận hành xác nhận riêng.
6. Nếu cần khôi phục: đặt lại `TEAMS_DELIVERY_MODE=legacy`, khởi động lại dịch vụ
   alert và kiểm các Flow cũ còn hoạt động. Không gửi lại cả kỳ báo cáo khi chưa
   biết người nào đã nhận để tránh trùng.

## 6. Kiểm tra trước merge

Chạy test routing/payload/Daily/QLV/watchdog với dữ liệu và HTTP giả, rồi full suite:

```powershell
python -m pytest tests/test_teams_shared_flow.py tests/test_teams_dinh_tuyen_nguoi_nhan.py tests/test_teams_adaptive_card_1_4.py tests/test_qlv_digest.py tests/test_report_task_runtime.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Chưa có UPN và webhook Flow mới nên chưa thể nghiệm thu thực nhận. Chuyển cấu
hình trên máy 24 là bước vận hành sau review/deploy, không phải sửa code tại máy 24.

Kiểm thử trên dev 22/09: **86 test định tuyến liên quan passed**; full suite
**952 passed, 1 deselected, 24 warnings** (cảnh báo `sqlite3` cũ trên Python 3.12).
