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

## ⚠️ Cập nhật 03/09/2026 — rủi ro đã xảy ra thật, không còn là dự đoán

Khuyến nghị trên đã **quá hạn 3 tuần**. Trong lúc đó, commit `516525b` (28/08/2026) — sửa
`AdminUsersPanel.tsx` để hiện đúng nhãn "Trưởng phòng" thay vì mã `regional_director` — đã
**ghi cùng một bản vá vào cả `src/app/` lẫn `frontend/src/app/`**. Đúng kiểu "phân kỳ âm thầm"
văn bản này cảnh báo từ 12/08, ngoại trừ nó không âm thầm: ai/công cụ nào sửa bug đều đang phải
tốn công sửa **hai lần**, và một lần quên đồng bộ là `frontend/` lại chứa lỗi đã vá ở `src/app/`.

Diff hiện tại (03/09) cho thấy `frontend/src/app/` đã **thiếu hẳn** so với `src/app/`:
`roleLabels.ts`, `TableExport.tsx`, `icons.tsx`, `useModal.ts`, `api/_proxy.ts`, `api/queries/` —
không tồn tại trong bản `frontend/`. Nghĩa là ngay cả nỗ lực đồng bộ song song cũng không theo kịp.

**Việc này chỉ dừng khi xoá khỏi git**, không phải khi nhắc thêm một dòng cảnh báo. Đây là quyết
định cần xác nhận trước khi thực hiện (không tự xoá khi chưa hỏi — xem
`docs/backlog_tu_phan_hoi_nguoi_dung.md` và lịch sử trùng lặp trong dự án). Lệnh an toàn đề xuất
khi được duyệt — chỉ xoá phần **git-tracked**, không đụng `.vercel/project.json` (file cục bộ,
không nằm trong git, `cloudflared_supervisor.ps1` trên máy 24 vẫn cần nguyên vị trí đó):

```
git rm -r frontend/src frontend/README.md frontend/package.json frontend/next.config.* \
  frontend/tsconfig.json frontend/tailwind.config.* frontend/postcss.config.*
git commit -m "chore: xoa ban Next.js trung lap trong frontend/, giu file .vercel cuc bo tren may 24"
```

Kiểm bằng `git status` trước khi commit để chắc không xoá nhầm gì ngoài dự kiến — cấu trúc thư mục
`frontend/` có thể đã đổi từ lúc viết lệnh này.
