---
name: dnh-onsite-prep
description: Tổng hợp danh sách câu hỏi cần hỏi khách hàng DNH khi onsite và checklist chuẩn bị. Chỉ gọi thủ công qua /dnh-onsite, không tự động trigger.
disable-model-invocation: true
argument-hint: "[cập nhật | xem]"
---

# DNH Onsite Prep

Gọi `/dnh-onsite xem` để in lại danh sách câu hỏi + checklist hiện tại.
Gọi `/dnh-onsite cập nhật` để cập nhật trạng thái câu hỏi sau khi có câu trả lời từ client (Claude sẽ hỏi lại câu trả lời và ghi vào `references/onsite_qa_log.md`, đồng thời cập nhật `dnh-project-context` nếu câu trả lời ảnh hưởng đến kiến trúc đã chốt).

## 3 câu hỏi mở chính (chưa chốt, ưu tiên hỏi đầu tiên)

1. **Baseline tính sụt giảm doanh thu** — so với kỳ nào, ngưỡng % bao nhiêu được coi là "sụt giảm"?
2. **Ngày cơ sở tính tuổi nợ (debt aging date basis)** — dùng `invoice_date` hay `due_date` hay ngày khác?
3. **Cấu hình cloud DB (Supabase)** — kế hoạch đã đổi từ SQL Server on-prem sang cloud Postgre (03/07/2026, xem `dnh-project-context`). Câu hỏi mở giờ là: region/project Supabase nào, ai quản lý access (service role key, RLS), chính sách backup/retention, và DNH có cần ký lại phụ lục data residency cho việc dữ liệu dược phẩm ra khỏi on-prem không.

Chi tiết đầy đủ danh sách câu hỏi (tiếng Việt) và checklist chuẩn bị xem tại `references/onsite_questions.md`.

## Checklist trước khi lên đường

- [ ] In/mang theo `MCNA_DNH_ProjectPlan_v3.docx`
- [ ] Xác nhận lại 3 câu hỏi mở ở trên với người có thẩm quyền quyết định (không phải chỉ đội DA)
- [ ] Chuẩn bị câu hỏi về quyền truy cập cloud DB Supabase (ai giữ service role key, IP allowlist, credential rotation)
- [ ] Xác nhận phạm vi Phase 1 KHÔNG bao gồm dashboard (để tránh hiểu nhầm lúc kick-off)
- [ ] Ghi chú lại toàn bộ câu trả lời ngay tại chỗ — dùng `/dnh-onsite cập nhật` ngay sau buổi họp trong khi thông tin còn mới

## Sau khi có câu trả lời

Cập nhật ngay vào `dnh-project-context` skill (mục "Câu hỏi mở cần xác nhận") để các skill khác (debt-aging-schema, email-alert-builder) không còn dùng giả định/config placeholder nữa mà dùng giá trị đã chốt.
