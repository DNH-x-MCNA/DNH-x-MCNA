---
name: dnh-debt-aging-schema
description: Schema và logic tính tuổi nợ (debt aging bucket) đã sửa đúng theo hợp đồng đã ký cho dự án DNH. Dùng skill này bất cứ khi nào viết, sửa, hoặc review code/SQL liên quan đến công nợ, debt aging, aging bucket, báo cáo công nợ, hoặc bảng liên quan trong backend/scripts/ETL của DNH.
---

# DNH Debt Aging Schema

## Mục đích

Đảm bảo mọi implementation của debt aging bucket khớp chính xác với đặc tả trong hợp đồng đã ký với DNH — đây là điểm đã từng bị sai trong prototype ban đầu và đã được sửa lại (T-SQL schema chuẩn nằm trong `assets/debt_aging_schema.sql`).

## Cách dùng

1. Trước khi sửa bất kỳ logic aging bucket nào, đọc `assets/debt_aging_schema.sql` để lấy đúng bucket boundaries.
2. **Ngày cơ sở tính tuổi nợ (date basis) hiện chưa được client xác nhận** (open item onsite 07/07/2026). Code phải đọc date basis từ config/parameter, KHÔNG hardcode một ngày cụ thể (không dùng invoice_date hay due_date mặc định nếu chưa có xác nhận từ DNH).
3. Nếu phát hiện code hiện tại dùng bucket khác với schema trong `assets/`, đây là bug — sửa lại theo file chuẩn, không tự sáng tạo bucket mới.
4. Mọi thay đổi với schema aging phải note lại lý do trong commit message / docs, vì đây là logic đã từng gây tranh cãi với hợp đồng.

## Khi viết báo cáo/email alert liên quan đến công nợ

- Tham chiếu đúng tên bucket trong schema chuẩn (không tự đặt tên khác)
- Alert quá hạn nợ nằm trong 4 trigger đã định nghĩa ở skill `dnh-email-alert-builder` — không tạo trigger mới ngoài phạm vi đã chốt mà không hỏi lại.
