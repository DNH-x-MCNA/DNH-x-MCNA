# Web chatbot chạy thẳng trên máy 24 — dựng, deploy, quay lại

Trạng thái 02/10/2026:

- **Đã xong trên máy 24:** code `5fa4ad8`, `C:\dnh_web\web.env`, bản build web (`current` → `releases\…`),
  `caddy.exe` 2.11.6 (đã đối chiếu SHA512), Caddyfile hợp lệ, web tạm ↔ backend gọi được nhau.
- **Chưa làm:** rule Windows Firewall, đăng ký hai dịch vụ, khoá quyền, chứng chỉ.
- **Chờ DNH:** NAT 443 và bản ghi DNS (kiểm 02/10 14:30: `chatbot.namhatrading.com` chưa có bản ghi A).
- Người dùng vẫn vào `https://dnh-bot.vercel.app`.

Anh Đăng chốt 02/10: bỏ cả Vercel lẫn Cloud Server trung gian, tên miền trỏ thẳng vào máy 24, và đi thẳng tên thật
`chatbot.namhatrading.com` (không dựng `uat-chatbot`). Bộ `deploy/cloud_server/` (#164) giữ lại làm phương án dự phòng.

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
- Bốn script đều **mặc định chỉ kiểm**; chỉ đổi hệ thống khi có `-ApDung`.

## Rủi ro đã biết của hướng này

- Máy 24 đang chứa kho dữ liệu, SQL Server riêng của DNH và tài khoản đọc Bravo. Mở cổng 443 vào máy này nghĩa là
  lỗ hổng ở Caddy/Next.js có thể dẫn vào đó. Giảm thiểu:
  - chỉ NAT đúng một cổng; firewall trên máy đóng 3000/8010;
  - hai dịch vụ web chạy bằng `LOCAL SERVICE`, không phải SYSTEM;
  - `khoa_quyen_truc_tiep.ps1` từ chối `LOCAL SERVICE` đọc/ghi `C:\dnh_chatbot` (trừ `tools` và
    `deploy\may24_truc_tiep`, chỉ đọc). Thiếu bước này thì `LOCAL SERVICE` vẫn đọc được `.env` của backend và tạo
    được file cạnh code chạy bằng SYSTEM, vì nó thuộc nhóm `Users`.
- Phần không che được: tiến trình web buộc phải giữ `BACKEND_API_KEY`. Kẻ chiếm được web gọi được backend qua
  loopback, nhưng mọi API dữ liệu vẫn đòi thêm phiên đăng nhập của người dùng.
- `khoa_quyen_truc_tiep.ps1` chỉ lo `C:\dnh_chatbot` và `C:\nssm`. Thư mục khác của DNH trên máy 24 mà nhóm `Users`
  đọc được thì vẫn đọc được.
- RAM máy 24 chỉ còn trống khoảng 2,2–2,8/12 GB. Build web bị giới hạn 1,5 GB và không chạy trong khung 17:15–18:15.

## DNH cần làm

| # | Việc | Xong khi |
|---|---|---|
| 1 | NAT **TCP 443** từ một IP public tĩnh vào `172.16.0.24:443`, nguồn `Any`. Không NAT 80, 3000, 8010, SQL, RDP | Từ ngoài mạng DNH, `Test-NetConnection <IP public> -Port 443` ra `True` (sau khi Caddy chạy) |
| 2 | NAT phải **giữ IP nguồn của người dùng** (DNAT, không đổi nguồn thành IP firewall) | Xem mục kiểm IP bên dưới |
| 3 | Bản ghi **A** `chatbot` → IP public đó, TTL 300 (DNS Mắt Bão của `namhatrading.com`) | `cai_dat_lan_dau.ps1` in `DNS cong khai : <đúng IP>` |
| 4 | Người ngồi **trong văn phòng** mở được tên miền: firewall cho vòng lại (hairpin NAT), hoặc thêm bản ghi DNS nội bộ `chatbot.namhatrading.com` → `172.16.0.24` | Từ một máy trong văn phòng mở được `https://chatbot.namhatrading.com` |

Không đụng `@`, MX, SPF, DKIM hay bản ghi khác của tên miền.

Vì sao mục 1 cần nguồn `Any`: máy chủ kiểm tra của Let's Encrypt ở nước ngoài và gọi vào cổng 443 mỗi lần cấp hoặc
gia hạn chứng chỉ (khoảng 60 ngày một lần). Firewall chỉ cho IP Việt Nam thì không xin được chứng chỉ.

Vì sao mục 2 quan trọng: web giới hạn đăng nhập sai theo IP người dùng. Nếu firewall đổi IP nguồn, mọi người
mang chung một IP và 30 lần sai của bất kỳ ai sẽ khoá đăng nhập của tất cả.

Vì sao có mục 4: máy trong văn phòng hỏi DNS ra IP public của chính công ty. Nhiều firewall không tự chuyển lưu
lượng đó quay lại máy 24, nên ngoài Internet vào được mà trong văn phòng lại không.

## Dựng lần đầu trên máy 24

Mọi lệnh chạy trong PowerShell **Run as Administrator**, tại `C:\dnh_chatbot\deploy\may24_truc_tiep`.

| # | Việc | Cần DNH xong trước? | Xong khi |
|---|---|---|---|
| 1 | Đặt `caddy.exe` vào `C:\dnh_chatbot\tools\caddy\` | Không — **đã xong 02/10** | `.\cai_dat_lan_dau.ps1` in `CO` cho caddy.exe |
| 2 | Tạo `C:\dnh_web\web.env` từ `web.env.mau`, dán `BACKEND_API_KEY` lấy trong `C:\dnh_chatbot\backend\.env` | Không — **đã xong 02/10** | Không còn chữ `DAN_KHOA_TU_BACKEND_ENV` |
| 3 | `.\deploy_web.ps1` | Không — **đã xong 02/10** | In `DAT (chua co dich vu …)` |
| 4 | `.\tuong_lua_truc_tiep.ps1` (chỉ kiểm), đọc mục "Ket noi DANG MO vao 3000/8010", rồi `-ApDung` | Không | Có 2 rule nhóm `DNH chatbot truc tiep`; máy khác trong LAN không gọi được 8010 |
| 5 | `.\cai_dat_lan_dau.ps1` (chỉ kiểm) | Có | `DNS cong khai` ra đúng IP; `Rule tuong lua` ra `CO`; cổng 443 trống |
| 6 | `.\cai_dat_lan_dau.ps1 -ApDung` | Có | In `DAT: … Caddy dang phuc vu chung chi`; mục `Chung chi` ghi `chung chi THAT` |
| 7 | Kiểm từ ngoài mạng DNH theo mục dưới | Có | Đạt đủ các mục |
| 8 | `.\khoa_quyen_truc_tiep.ps1` (chỉ kiểm), rồi `-ApDung` | Có (cần hai dịch vụ đang chạy) | In `DAT: LOCAL SERVICE khong con doc/ghi duoc …` |
| 9 | Chuyển người dùng (mục dưới) | Có | — |

Thứ tự 4 → 6 là bắt buộc. Let's Encrypt kiểm tên miền bằng cách gọi vào cổng 443 của máy 24; chưa có rule firewall
hoặc chưa có bản ghi DNS thì lần xin chứng chỉ đầu tiên chắc chắn hỏng và tính vào hạn mức (5 lần hỏng mỗi giờ cho một
tên). Vì vậy `-ApDung` ở bước 6 tự dừng khi thiếu một trong hai; bỏ qua bằng `-BoQuaKiemTruoc`.

Bước 6 chờ tối đa 90 giây cho Caddy xin chứng chỉ. Nếu chưa có, script in 12 dòng cuối của nhật ký Caddy. Khi cần dò
lỗi nhiều lần mà không tốn hạn mức, chạy `.\cai_dat_lan_dau.ps1 -ApDung -ChayThu`: cùng tên miền nhưng xin chứng chỉ
**thử** (trình duyệt sẽ cảnh báo, đó là đúng). Dò xong chạy lại `-ApDung` không kèm `-ChayThu`.

Bước 8 làm web ngừng vài giây (khởi động lại hai dịch vụ để kiểm với quyền mới). Web không lên thì script tự gỡ
khoá và báo lỗi.

Không dán khoá API hay nội dung `web.env` vào chat, email hoặc repo.

## Kiểm trước khi báo người dùng

1. `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/` trên máy 24 ra 200.
2. Từ máy ngoài mạng DNH (4G): mở trang không có cảnh báo chứng chỉ, đăng nhập, hỏi một câu và thấy chữ hiện dần
   (stream).
3. **IP người dùng:** đăng nhập sai một lần từ máy ngoài, rồi mở `C:\dnh_web\logs\caddy_access.log`. Trường
   `remote_ip` của dòng đó phải là IP Internet của máy ngoài, không phải IP firewall DNH. Nếu là IP firewall thì
   dừng, báo DNH sửa NAT (mục 2 của bảng DNH).
4. Từ một máy khác trong LAN: `Test-NetConnection 172.16.0.24 -Port 8010` và `-Port 3000` phải ra `False`.
5. Từ một máy trong văn phòng: mở được `https://chatbot.namhatrading.com` (mục 4 của bảng DNH).
6. Phân quyền: đăng nhập bằng một tài khoản QLV, một GĐ miền, một C-Level; mỗi tài khoản chỉ thấy phạm vi của mình.
7. Chỉ hỏi câu tốn phí model khi anh Đăng duyệt.

## Chuyển người dùng sang tên miền mới

1. Sửa `CHATBOT_WEB_URL=https://chatbot.namhatrading.com` trong `C:\dnh_chatbot\.env`, rồi
   `Restart-Service DNH_Realtime_Alerts` (link trong thẻ Teams và email). Tránh 17:15–18:15.
2. Báo người dùng địa chỉ mới.
3. Giữ `DNH_Chatbot_Tunnel` và Vercel chạy song song cho tới khi DNH xác nhận ổn định. Sau đó
   `Stop-Service DNH_Chatbot_Tunnel` và đặt `Startup type = Disabled`: service này tự gọi `vercel redeploy` mỗi khi
   URL tunnel đổi.

Bước 1 cũng là lúc watchdog bắt đầu canh web (mục dưới).

## Watchdog

`backend/health_watchdog.py` (task `DNH_Chatbot_Health_Watchdog`, 15 phút một lần) canh thêm ba thứ, **chỉ khi**
`CHATBOT_WEB_URL` đã trỏ về tên miền riêng và máy có `C:\dnh_web\current`:

| Kiểm | Báo khi | Mức |
|---|---|---|
| Web `http://127.0.0.1:3000/` | Không trả 200 sau 3 lần thử cách nhau 10 giây | Nghiêm trọng |
| Caddy cổng 443 (bắt tay TLS với đúng tên miền) | Không bắt tay được sau 3 lần thử | Nghiêm trọng |
| Hạn chứng chỉ | Còn dưới 1/6 thời hạn (chứng chỉ 90 ngày: dưới 15 ngày) | Cảnh báo |

Mỗi sự cố báo một lần, hết thì báo một lần, gửi về cùng nơi với cảnh báo "đồng bộ dữ liệu ngừng" hiện có. Trước khi
đổi `CHATBOT_WEB_URL`, hoặc khi quay về Vercel, watchdog bỏ qua phần này.

Watchdog chạy trên máy 24 nên **không thấy** lỗi ở NAT hay DNS: khi firewall DNH đổi cấu hình, bên trong vẫn bình
thường mà bên ngoài không vào được. Dấu hiệu gián tiếp duy nhất là cảnh báo hạn chứng chỉ (gia hạn cũng cần cổng 443
từ ngoài vào). Muốn biết ngay thì cần một dịch vụ theo dõi từ ngoài Internet; chưa có.

## Deploy web về sau

Web không còn do Vercel build. Sau mỗi lần `git pull` có thay đổi trong `src/`, `public/`, `package*.json` hoặc
`next.config.ts`:

```powershell
C:\dnh_chatbot\deploy\may24_truc_tiep\deploy_web.ps1
```

Build xong mới đổi sang bản mới; bản mới không lên thì tự quay về bản cũ. Giữ 3 bản gần nhất. Thay đổi chỉ ở
`backend/` hay `src/*.py` thì không cần chạy lệnh này. `Caddyfile` đổi thì `Restart-Service DNH_Chatbot_Proxy`.

## Quay lại

| Tình huống | Lệnh |
|---|---|
| Bản web mới lỗi | `.\deploy_web.ps1 -QuayLai` |
| Bỏ khoá quyền | `.\khoa_quyen_truc_tiep.ps1 -GoBo` |
| Bỏ firewall vừa thêm | `.\tuong_lua_truc_tiep.ps1 -GoBo` |
| Bỏ hai dịch vụ | `.\cai_dat_lan_dau.ps1 -GoBo` |
| Về hẳn Vercel | `Start-Service DNH_Chatbot_Tunnel`, trả `CHATBOT_WEB_URL` về `https://dnh-bot.vercel.app`, nhờ DNH gỡ NAT 443 |

## Đã thử đến đâu

| Phần | Đã thử |
|---|---|
| `deploy_web.ps1` | Chạy thật trên máy dev và trên máy 24 (chế độ chưa có dịch vụ) |
| Caddyfile | `caddy validate` trên máy 24: hợp lệ |
| Web chạy khi thư mục build chỉ đọc (như lúc chạy bằng `LOCAL SERVICE`) | Máy dev: trang chủ 200, không ghi gì ngoài `.next\cache` |
| Lệnh đổi tài khoản dịch vụ (`sc.exe`) | Máy dev với một dịch vụ không tồn tại: `sc.exe` hiểu đúng tham số. Dạng viết cũ thì hỏng |
| `khoa_quyen_truc_tiep.ps1` | Máy dev, trên cây thư mục thử: bị khoá thì không đọc được `.env`, không tạo được file; vẫn đọc được `node`/Caddyfile; gỡ ra về như cũ |
| Đọc chứng chỉ, hỏi DNS công khai | Máy dev với các trang HTTPS công khai |
| **Chưa thử được ở đâu** | Đăng ký dịch vụ bằng NSSM, chạy thật bằng `LOCAL SERVICE`, rule firewall, xin chứng chỉ: cần quyền admin và NAT/DNS thật. Lần chạy đầu trên máy 24 là lần thử đầu |
