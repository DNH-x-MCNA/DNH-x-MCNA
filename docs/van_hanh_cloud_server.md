# Web chatbot trên Cloud Server Mắt Bão — dựng, deploy, quay lại

Trạng thái 30/09/2026: **mới là cấu hình soạn sẵn**, chưa có Cloud Server, chưa có bản ghi DNS. Người dùng vẫn
vào `https://dnh-bot.vercel.app`. Chốt 30/09: bỏ Vercel, không gắn domain lên Vercel.

## Sơ đồ

```
Trình duyệt
  │ (1) hỏi DNS Mắt Bão: chatbot.namhatrading.com → IP Cloud Server (bản ghi A)
  │ (2) HTTPS
  ▼
Cloud Server Mắt Bão (Ubuntu 24.04)
  Nginx :443 (chứng chỉ Let's Encrypt) → web Next.js 127.0.0.1:3000 (dnh-web.service)
  │ (3) đường hầm WireGuard, do MÁY 24 chủ động mở ra (UDP 51820). DNH không mở cổng vào.
  ▼
Máy 24 (172.16.0.24): backend :8010 → kho SQLite (+ Bravo 172.16.0.26)
```

- Trình duyệt chỉ thấy `chatbot.namhatrading.com`. Web gọi backend tại `http://10.88.24.2:8010`, địa chỉ của
  máy 24 trong đường hầm, và gửi kèm `BACKEND_API_KEY` như hiện nay.
- Đường hầm chỉ nối hai địa chỉ `10.88.24.1` (Cloud Server) ↔ `10.88.24.2` (máy 24). Cloud Server không vào được
  mạng nội bộ DNH. Máy 24 không đổi tuyến mạng hay DNS nào khác.
- Mọi file cấu hình nằm trong `deploy/cloud_server/`. Không sửa tay trên server: sửa trong repo rồi cài lại.

## Dựng lần đầu

| # | Việc | Ai | Xong khi |
|---|---|---|---|
| 1 | Thuê Cloud Server riêng: Ubuntu **24.04**, x86_64, khoảng 2 vCPU/2 GB RAM, IP public tĩnh; cấp SSH | DNH | Có IP và tài khoản sudo |
| 2 | Thêm bản ghi **A** `chatbot` → IP Cloud Server, TTL 300 | IT DNH (DNS Mắt Bão) | `nslookup chatbot.namhatrading.com` ra đúng IP |
| 3 | Xác nhận máy 24 được đi ra IP Cloud Server qua UDP 51820 | IT DNH | Câu trả lời bằng văn bản |
| 4 | Chạy `cai_dat_lan_dau.sh` (lệnh ở đầu file) | Anh Đăng | Script in "XONG phần cài đặt" |
| 5 | `sudo nano /etc/dnh-web/web.env`, dán `BACKEND_API_KEY` lấy từ `C:\dnh_chatbot\backend\.env` trên máy 24 | Anh Đăng | Không còn chữ `DAN_KHOA_TU_MAY_24` |
| 6 | Đường hầm, xem mục dưới | Anh Đăng | `curl http://10.88.24.2:8010/health` trên Cloud Server ra `"status":"ok"` |
| 7 | Trên máy 24: `.\tuong_lua_8010.ps1` (chỉ kiểm), đọc kết quả, rồi `-ApDung` | Anh Đăng | Cloud Server vẫn gọi được `/health`; máy khác trong LAN thì không |
| 8 | `sudo /opt/dnh-web/repo/deploy/cloud_server/deploy_web.sh` | Anh Đăng | Script in "DAT: web chay ban …" và "Backend may 24 tra loi qua duong ham: OK" |
| 9 | Chạy thử trên `https://chatbot.namhatrading.com`, xem mục **Kiểm trước khi báo người dùng** | Anh Đăng + Claude | Đạt đủ các mục |

Không dán khoá API, khoá WireGuard hay nội dung `web.env` vào chat, email hoặc repo.

### Đường hầm WireGuard (bước 6)

1. Trên Cloud Server: `sudo bash /opt/dnh-web/repo/deploy/cloud_server/cai_wireguard.sh`. Script in **khoá công
   khai** của Cloud Server. Khoá này công khai, gửi qua chat được.
2. Trên máy 24: cài WireGuard for Windows từ trang chính thức `wireguard.com`. Chọn **Add Tunnel → Add empty
   tunnel**, đặt tên `dnh-cloud`, rồi điền theo `deploy/cloud_server/wireguard/may24.conf.mau`. App tự tạo khoá
   riêng; khoá này không rời máy 24. Lưu lại, **chưa Activate**, và chép dòng "Public key".
3. Trên Cloud Server: `sudo MAY24_PUBKEY='<Public key của máy 24>' bash .../cai_wireguard.sh`.
4. Trên máy 24: **Activate** tunnel `dnh-cloud`.
5. Trên Cloud Server: `sudo wg show wg0 latest-handshakes` phải có mốc thời gian, và
   `curl -s http://10.88.24.2:8010/health` phải ra `"status":"ok"`.

Nếu tường lửa DNH chỉ cho đi ra qua TCP 443 thì không dùng được WireGuard. Khi đó cần đổi sang loại đường hầm
chạy trên TCP; phần này chưa soạn.

## Kiểm trước khi báo người dùng

Trong lúc này người dùng vẫn ở link cũ. Anh kiểm trên link mới:

- Trang mở bằng https, khoá xanh; gõ `http://chatbot.namhatrading.com` thì tự chuyển sang https.
- Đăng nhập được, đăng xuất được.
- Hỏi một câu dài: chữ phải **hiện dần**. Nếu cả câu hiện ra một lần ở cuối thì stream đang bị buffer; báo Claude.
- Mở lại lịch sử phiên cũ, gửi 👍/👎, vào trang quản trị (tài khoản admin).
- Chống dò mật khẩu: backend không ghi IP đăng nhập ra log (chỉ giữ trong bộ nhớ để đếm số lần sai), nên kiểm
  ở Nginx. `sudo tail -n 5 /var/log/nginx/access.log` trên Cloud Server phải hiện IP mạng của người thử, không phải
  `127.0.0.1`. Việc ghi đè header IP từ giá trị đó đã được test khoá trong cấu hình.
- `curl -I http://<IP Cloud Server>` phải bị đóng kết nối ngay: truy cập bằng IP trần không ra trang nào.

## Chuyển người dùng sang link mới

1. Gửi thông báo: link mới là `https://chatbot.namhatrading.com`; mỗi người **đăng nhập lại một lần** (trình duyệt
   lưu phiên theo từng tên miền); lịch sử chat vẫn còn nguyên.
2. Trên máy 24: đổi `CHATBOT_WEB_URL` trong `C:\dnh_chatbot\.env` (ghi UTF-8 **không BOM**), rồi restart
   `DNH_Realtime_Alerts`, để link trong cảnh báo Teams và email trỏ về tên miền mới. Tránh khung 17:15–18:15.
3. Claude mở PR đổi link mặc định trong `src/notifier.py`, `.env.example` và tài liệu bàn giao UAT.
4. Giữ Vercel và tunnel tạm (`DNH_Chatbot_Tunnel`) chạy song song 1–2 tuần để dự phòng.
5. Khi đã ổn định: dừng và disable `DNH_Chatbot_Tunnel` (link Vercel ngừng chạy), xoá biến `BACKEND_API_URL`
   trên Vercel, chuyển repo sang private. Trước khi chuyển, tạo deploy key chỉ đọc cho Cloud Server và máy 24,
   để `git pull` vẫn chạy được.

Từ khi đóng băng 08/10 20:00 đến hết nghiệm thu 10/10: không dựng hay chuyển gì cả.

## Deploy hằng ngày

- **Web** (thay đổi trong `src/app`): trên Cloud Server chạy
  `sudo /opt/dnh-web/repo/deploy/cloud_server/deploy_web.sh`.
  - Mỗi bản build vào `/opt/dnh-web/releases/<giờ>-<commit>`. Web cũ vẫn phục vụ trong lúc build.
  - Build lỗi, hoặc web mới không lên trong khoảng 90 giây, thì script tự giữ hoặc quay về bản cũ.
  - Build chạy luôn bước kiểm CSS (`kiem_css_sau_build.mjs`).
  - Script giữ 3 bản gần nhất.
- **Backend**: vẫn theo khối deploy máy 24 như cũ. Cloud Server không cần làm gì.
- Khi Vercel còn chạy song song thì merge vào master vẫn tự deploy lên Vercel. Link mới chỉ đổi khi chạy
  `deploy_web.sh`.

## Quay lại khi có sự cố

| Tình huống | Làm gì |
|---|---|
| Bản web mới lỗi | `sudo .../deploy_web.sh --rollback` về bản build trước |
| Cloud Server hoặc đường hầm hỏng, Vercel còn chạy | Báo người dùng tạm dùng `https://dnh-bot.vercel.app` |
| Tường lửa 8010 làm hỏng thứ gì trên máy 24 | `.\tuong_lua_8010.ps1 -GoBo` |
| Cần chuyển tên miền đi nơi khác | Sửa bản ghi A. TTL 300 nên có hiệu lực sau khoảng 5 phút |

## Theo dõi

- `systemctl status dnh-web nginx wg-quick@wg0`; log web: `journalctl -u dnh-web -n 200`.
- `sudo wg show`: `latest handshake` quá 3 phút tức là đường hầm đã đứt. Kiểm tunnel `dnh-cloud` trên máy 24.
- Chứng chỉ tự gia hạn qua `certbot.timer`. Xem hạn: `sudo certbot certificates`. Email trong `EMAIL_LE` sẽ nhận
  cảnh báo nếu gia hạn lỗi.
- Hệ điều hành tự vá bảo mật (`unattended-upgrades`). Nên để SSH chỉ đăng nhập bằng khoá; chỉ tắt đăng nhập
  mật khẩu sau khi đã thử đăng nhập bằng khoá thành công, để không tự khoá mình ngoài.

## Các điểm đã khoá bằng test

`tests/test_cau_hinh_cloud_server.py` kiểm:

- Nginx **ghi đè** `X-Real-IP`/`X-Forwarded-For` bằng `$remote_addr`, khớp với header mà `_proxy.ts` đọc.
- Stream chat không bị buffer hay nén; timeout ≥ 300 giây.
- Web chỉ nghe `127.0.0.1`, không chạy bằng root.
- Địa chỉ đường hầm khớp nhau ở mọi file.
- File mẫu không chứa khoá thật.
- Script tường lửa mặc định chỉ kiểm.
- File chạy trên Linux dùng LF.
