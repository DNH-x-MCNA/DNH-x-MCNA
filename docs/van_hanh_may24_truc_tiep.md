# Web chatbot chạy thẳng trên máy 24 — dựng, deploy, quay lại

Trạng thái 02/10/2026: **mới là cấu hình soạn sẵn**. Chưa có NAT, chưa có bản ghi DNS, chưa cài gì trên máy 24.
Người dùng vẫn vào `https://dnh-bot.vercel.app`.

Anh Đăng chốt 02/10: bỏ cả Vercel lẫn Cloud Server trung gian; tên miền trỏ thẳng vào máy 24. Bộ
`deploy/cloud_server/` (#164) giữ lại làm phương án dự phòng.

## Sơ đồ

```
Trình duyệt
  │ (1) hỏi DNS Mắt Bão: chatbot.namhatrading.com → IP public của DNH (bản ghi A)
  │ (2) HTTPS, cổng 443
  ▼
Firewall/NAT của DNH: IP public:443 → máy 24:443 (chỉ cổng này)
  ▼
Máy 24 (DC-DATA-REPORT, 172.16.0.24)
  Caddy :443 (chứng chỉ Let's Encrypt) → web Next.js 127.0.0.1:3000 → backend 127.0.0.1:8010
```

- Chỉ Caddy nhận kết nối từ ngoài. Web và backend chỉ được gọi từ chính máy 24.
- Mọi file cấu hình nằm trong `deploy/may24_truc_tiep/`. Không sửa tay trên máy 24: sửa trong repo, `git pull`.
- Ba script đều **mặc định chỉ kiểm**; chỉ đổi hệ thống khi có `-ApDung`.

## Rủi ro đã biết của hướng này

- Máy 24 đang chứa kho dữ liệu, SQL Server riêng của DNH và tài khoản đọc Bravo. Mở cổng 443 vào máy này nghĩa là
  lỗ hổng ở Caddy/Next.js có thể dẫn vào đó. Giảm thiểu: hai dịch vụ web chạy bằng `LOCAL SERVICE` (không phải
  SYSTEM), firewall đóng 3000/8010, chỉ NAT đúng một cổng.
- RAM máy 24 chỉ còn trống khoảng 2,8/12 GB (đo 30/09). Build web bị giới hạn 1,5 GB và không chạy trong khung
  17:15–18:15.

## DNH cần làm

| # | Việc | Xong khi |
|---|---|---|
| 1 | NAT **TCP 443** từ một IP public tĩnh vào `172.16.0.24:443`. Không NAT 80, 3000, 8010, SQL, RDP | Từ ngoài mạng DNH, `Test-NetConnection <IP public> -Port 443` ra `True` (sau khi Caddy chạy) |
| 2 | NAT phải **giữ IP nguồn của người dùng** (DNAT, không đổi nguồn thành IP firewall) | Xem mục kiểm IP bên dưới |
| 3 | Bản ghi **A** `uat-chatbot` → IP public đó, TTL 300 (DNS Mắt Bão của `namhatrading.com`) | `nslookup uat-chatbot.namhatrading.com` ra đúng IP |
| 4 | Sau khi chạy thử đạt: bản ghi **A** `chatbot` → cùng IP | `nslookup chatbot.namhatrading.com` ra đúng IP |

Không đụng `@`, MX, SPF, DKIM hay bản ghi khác của tên miền.

Vì sao mục 2 quan trọng: web giới hạn đăng nhập sai theo IP người dùng. Nếu firewall đổi IP nguồn, mọi người
mang chung một IP và 30 lần sai của bất kỳ ai sẽ khoá đăng nhập của tất cả.

## Dựng lần đầu trên máy 24

Mọi lệnh chạy trong PowerShell **Run as Administrator**, tại `C:\dnh_chatbot\deploy\may24_truc_tiep`.

| # | Việc | Xong khi |
|---|---|---|
| 1 | Đặt `caddy.exe` (bản Windows amd64 từ caddyserver.com, đối chiếu checksum) vào `C:\dnh_chatbot\tools\caddy\` | `.\cai_dat_lan_dau.ps1` in `CO` cho caddy.exe |
| 2 | Tạo `C:\dnh_web\web.env` từ `web.env.mau`, dán `BACKEND_API_KEY` lấy trong `C:\dnh_chatbot\backend\.env` | Không còn chữ `DAN_KHOA_TU_BACKEND_ENV` |
| 3 | `.\deploy_web.ps1` | In `DAT (chua co dich vu …)`: đã build và trỏ `current` |
| 4 | `.\cai_dat_lan_dau.ps1` (chỉ kiểm), đọc kết quả | Cổng 443 trống, Caddyfile hợp lệ |
| 5 | `.\cai_dat_lan_dau.ps1 -ApDung -ChayThu` | Hai dịch vụ `Running`, chạy bằng `NT AUTHORITY\LocalService` |
| 6 | `.\tuong_lua_truc_tiep.ps1` (chỉ kiểm), đọc mục "Kết nối đang mở vào 3000/8010", rồi `-ApDung` | Máy khác trong LAN không gọi được 8010 |
| 7 | Kiểm trên `https://uat-chatbot.namhatrading.com` theo mục dưới | Đạt đủ các mục |
| 8 | Chuyển sang tên thật: `.\cai_dat_lan_dau.ps1 -ApDung` (không có `-ChayThu`) | Trình duyệt mở `https://chatbot.namhatrading.com` không cảnh báo chứng chỉ |

`-ChayThu` dùng tên `uat-chatbot` và chứng chỉ **thử** của Let's Encrypt, nên trình duyệt sẽ báo chứng chỉ không
tin cậy; đó là đúng ở bước thử. Chứng chỉ thật chỉ xin ở bước 8, để lỗi cấu hình không làm cạn hạn mức cấp chứng
chỉ.

Không dán khoá API hay nội dung `web.env` vào chat, email hoặc repo.

## Kiểm trước khi báo người dùng

1. `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/` trên máy 24 ra 200.
2. Từ máy ngoài mạng DNH: mở trang, đăng nhập, hỏi một câu không tốn phí (ví dụ câu dự phóng) và thấy chữ hiện dần
   (stream).
3. **IP người dùng:** đăng nhập sai một lần từ máy ngoài, rồi mở `C:\dnh_web\logs\caddy_access.log`. Trường
   `remote_ip` của dòng đó phải là IP Internet của máy ngoài, không phải IP firewall DNH. Nếu là IP firewall thì
   dừng, báo DNH sửa NAT (mục 2 của bảng DNH).
4. Từ một máy khác trong LAN: `Test-NetConnection 172.16.0.24 -Port 8010` và `-Port 3000` phải ra `False`.
5. Phân quyền: đăng nhập bằng một tài khoản QLV, một GĐ miền, một C-Level; mỗi tài khoản chỉ thấy phạm vi của mình.
6. Chỉ hỏi câu tốn phí model khi anh Đăng duyệt.

## Chuyển người dùng sang tên miền mới

1. Sửa `CHATBOT_WEB_URL=https://chatbot.namhatrading.com` trong `C:\dnh_chatbot\.env`, rồi
   `Restart-Service DNH_Realtime_Alerts` (link trong thẻ Teams và email). Tránh 17:15–18:15.
2. Báo người dùng địa chỉ mới.
3. Giữ `DNH_Chatbot_Tunnel` và Vercel chạy song song cho tới khi DNH xác nhận ổn định. Sau đó
   `Stop-Service DNH_Chatbot_Tunnel` và đặt `Startup type = Disabled`: service này tự gọi `vercel redeploy` mỗi khi
   URL tunnel đổi.

## Deploy web về sau

Web không còn do Vercel build. Sau mỗi lần `git pull` có thay đổi trong `src/`, `public/`, `package*.json` hoặc
`next.config.ts`:

```powershell
C:\dnh_chatbot\deploy\may24_truc_tiep\deploy_web.ps1
```

Build xong mới đổi sang bản mới; bản mới không lên thì tự quay về bản cũ. Giữ 3 bản gần nhất. Thay đổi chỉ ở
`backend/` hay `src/*.py` thì không cần chạy lệnh này.

## Quay lại

| Tình huống | Lệnh |
|---|---|
| Bản web mới lỗi | `.\deploy_web.ps1 -QuayLai` |
| Bỏ firewall vừa thêm | `.\tuong_lua_truc_tiep.ps1 -GoBo` |
| Bỏ hai dịch vụ | `.\cai_dat_lan_dau.ps1 -GoBo` |
| Về hẳn Vercel | `Start-Service DNH_Chatbot_Tunnel`, trả `CHATBOT_WEB_URL` về `https://dnh-bot.vercel.app`, nhờ DNH gỡ NAT 443 |

## Chưa có

- Watchdog chưa canh web cổng 3000 và Caddy. Hiện chỉ có NSSM tự chạy lại khi tiến trình thoát.
- Caddyfile, bước đăng ký dịch vụ và firewall **chưa chạy thử trên máy thật** (máy dev không có Caddy/NSSM). Riêng
  `deploy_web.ps1` đã chạy thử trên máy dev ở chế độ chưa có dịch vụ.
