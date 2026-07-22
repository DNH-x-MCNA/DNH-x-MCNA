---
name: dnh-debt-aging-schema
description: Schema và logic tính tuổi nợ (debt aging bucket) đã sửa đúng theo hợp đồng đã ký cho dự án DNH. Dùng skill này bất cứ khi nào viết, sửa, hoặc review code/SQL liên quan đến công nợ, debt aging, aging bucket, báo cáo công nợ, hoặc bảng liên quan trong backend/scripts/ETL của DNH.
---

# DNH Debt Aging Schema

## Mục đích

Đảm bảo mọi implementation của debt aging bucket khớp chính xác với cách DNH tự tính công nợ trong Bravo — đây là điểm đã từng bị sai trong prototype ban đầu và đã được sửa lại (T-SQL schema chuẩn nằm trong `assets/debt_aging_schema.sql`).

## Trạng thái: ĐÃ XÁC NHẬN (22/07/2026)

Ngày cơ sở tính tuổi nợ (date basis) **không còn provisional** — người dùng đã cung cấp toàn văn stored procedure gốc `[dbo].[usp_DeptAccDueDate_GetData]` từ Bravo (`NH_Report_TM`), xác nhận công thức `date_basis="doc_date_plus_term"` mà `config.yaml`/code đã dùng tạm trước đó là ĐÚNG với cách DNH tự tính nội bộ, không phải giả định của MCNA. Xem toàn bộ phân tích + bucket + ngưỡng màu trong `assets/debt_aging_schema.sql`.

## Cách dùng

1. Trước khi sửa bất kỳ logic aging bucket nào, đọc `assets/debt_aging_schema.sql` để lấy đúng bucket boundaries và các quy tắc nghiệp vụ đặc thù (loại trừ CustomerId, xử lý prepayment, 2 ClassCode TM/SX).
2. Bucket ĐANG DÙNG (chatbot + Teams alert) là bộ 15 ngày/kỳ: 1-15 / 16-30 / 31-45 / >45 ngày. SP gốc còn có bộ 7 ngày/kỳ (0/1-7/8-14/15-21/>21) — chỉ dùng nếu người dùng yêu cầu rõ ràng đổi độ chi tiết, KHÔNG tự ý đổi vì sẽ làm lệch số liệu đang hiển thị cho DNH.
3. Ngưỡng màu xanh/vàng/đỏ đề xuất: xem mục 3 trong `assets/debt_aging_schema.sql` — khớp với trigger alert A1 (`check_debt_aging_migration_alert`, cảnh báo khách mới rơi vào nhóm >45 ngày = đỏ).
4. Nếu phát hiện code hiện tại dùng bucket khác với schema trong `assets/`, đây là bug — sửa lại theo file chuẩn, không tự sáng tạo bucket mới.
5. Mọi thay đổi với schema aging phải note lại lý do trong commit message / docs, vì đây là logic đã từng gây tranh cãi với hợp đồng.

## Khi viết báo cáo/email alert liên quan đến công nợ

- Tham chiếu đúng tên bucket trong schema chuẩn (không tự đặt tên khác)
- Alert quá hạn nợ nằm trong 4 trigger đã định nghĩa ở skill `dnh-email-alert-builder` — không tạo trigger mới ngoài phạm vi đã chốt mà không hỏi lại.
