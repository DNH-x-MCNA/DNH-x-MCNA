# Thư mục này không chứa ứng dụng web

**Ứng dụng web thật nằm ở `src/app/` ở gốc repo.** Vercel (project `dnh-bot`) build từ gốc repo với
**Root Directory để trống**.

Từ 12/08/2026 thư mục này từng chứa một bản sao Next.js song song (trước nữa là trang HTML tĩnh). Bản sao
không được deploy nhưng vẫn gây nhầm. Hai sự cố:
- 10/08/2026: Vercel đặt Root Directory = `frontend` làm production sập toàn bộ `/api/*`.
- 28/09/2026: PR #132 sửa giao diện nhầm vào bản sao này nên trang chính không đổi. Việc thiết kế lại phải
  làm lại ở #133.

Ngày 29/09/2026 toàn bộ mã trong đây đã được xoá.

## Vì sao vẫn giữ thư mục

`backend/cloudflared_supervisor.ps1` trên máy 24 chạy `npx vercel env …` và `npx vercel redeploy …` **từ
`C:\dnh_chatbot\frontend`** mỗi khi URL tunnel đổi. Vercel CLI đọc `.vercel/project.json` trong thư mục
này để biết project cần cập nhật. File đó **không nằm trong git** (bị `.gitignore` bỏ qua), nên
`git pull` không xoá nó.

- Không xoá thư mục `frontend/` trên máy 24.
- Không đặt thư mục này làm Root Directory trên Vercel.
- Không thêm mã app vào đây. Sửa giao diện ở `src/app/`.
