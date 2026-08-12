# ⛔ KHÔNG đặt thư mục này làm Root Directory trên Vercel

**Bản chuẩn của ứng dụng web là `src/app/` ở THƯ MỤC GỐC của repo, không phải `frontend/`.**
Cấu hình đúng trên Vercel: **Root Directory để TRỐNG**.

## Vì sao có ghi chú này

Ngày 10/08/2026 production sập (đăng nhập báo *"Failed to execute 'json' on 'Response': Unexpected
end of JSON input"*, `/api/*` trả 404) đúng vì Vercel đang đặt Root Directory = `frontend`. Lúc đó
`frontend/` chỉ là một trang HTML tĩnh cũ, không có route API nào. Đã sửa bằng cách **xoá trống Root
Directory** trên Vercel Dashboard.

Ngày 12/08/2026 commit `47306dc` đồng bộ bản Next.js thật từ máy 24 vào `frontend/`. Từ đó repo có
**HAI bản** của cùng ứng dụng. Nguy cơ mới: ai đó thấy `frontend/` giờ là app thật, tưởng cấu hình
Root Directory đang sai, đặt lại thành `frontend` — và lỗi 10/08 quay lại nguyên vẹn.

## Khác biệt cụ thể giữa 2 bản (đo ngày 12/08/2026)

| | `src/app/api/` (gốc — ĐANG DÙNG) | `frontend/src/app/api/` (thư mục này) |
|---|---|---|
| Số route | 17 | 17 |
| Dùng `_proxy.ts` (bản vá 10/08) | **17/17** | **0/17** |
| File `_proxy.ts` | ✅ có | ❌ **không có** |

`_proxy.ts` là bản vá cho đúng lỗi đăng nhập nói trên: bọc `fetch` trong try/catch, phát hiện body
rỗng / body không phải JSON, và trả về thông báo tiếng Việt đọc được thay vì để route sập trắng.
Bản trong thư mục này vẫn là code cũ (`await fetch(...)` không try/catch, dán nhãn
`Content-Type: application/json` vô điều kiện) — backend không trả lời là trình duyệt lại báo
"Unexpected end of JSON input".

*(Ngoại lệ duy nhất: `chat/stream/route.ts` CỐ Ý không dùng `_proxy.ts` ở cả hai bản, vì proxy đọc
hết body trước khi trả về sẽ phá mất tính chất streaming — đúng thiết kế, không phải thiếu sót.)*

## Thư mục này còn dùng làm gì

**Đừng xoá khỏi máy 24.** `backend/cloudflared_supervisor.ps1` `Push-Location` vào
`C:\dnh_chatbot\frontend` để chạy `npx vercel redeploy` — cần `.vercel/project.json` nằm ở đó để
biết đang deploy project nào. File `.vercel/` là file cục bộ của máy 24, không nằm trong git.

## Việc nên làm sau demo 13/08

Chốt lại một bản duy nhất: hoặc xoá `frontend/` khỏi git (giữ `.vercel/` cục bộ trên máy 24 để
supervisor vẫn chạy được), hoặc gộp hẳn hai bản. Để hai bản song song lâu dài sẽ tiếp tục phân kỳ
âm thầm — đúng loại lỗi đã tốn 2 ngày xử lý tuần này.
