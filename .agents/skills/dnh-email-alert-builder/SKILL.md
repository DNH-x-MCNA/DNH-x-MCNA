---
name: dnh-email-alert-builder
description: Sinh code cho hệ thống email alert tự động của DNH Phase 1, theo đúng 4 trigger đã định nghĩa trong project plan. Dùng skill này khi viết, sửa, hoặc review code trong scripts/ hoặc backend/ liên quan đến gửi email cảnh báo, notification, hoặc alert tự động.
---

# DNH Email Alert Builder

## Nguyên tắc

Hệ thống chỉ có **4 trigger alert đã được định nghĩa** trong project plan (`MCNA_DNH_ProjectPlan_v3.docx`). Không tự thêm trigger mới ngoài phạm vi này khi code — nếu user/client muốn thêm, đó là thay đổi scope cần xác nhận lại, không phải việc tự quyết trong lúc code.

> File `references/alert_triggers.md` hiện là khung để điền — cần paste
> lại nội dung chi tiết 4 trigger từ `MCNA_DNH_ProjectPlan_v3.docx` (đã
> được định nghĩa ở phiên làm việc trước) vào đó để làm nguồn chuẩn.
> Cho đến khi điền đầy đủ, khi cần biết chi tiết trigger, hỏi lại user
> thay vì tự suy đoán ngưỡng/điều kiện.

## Khi sinh code alert mới

1. Xác định trigger nằm trong 1 của 4 loại đã chốt — nếu không khớp, hỏi lại trước khi code.
2. ETL/query phục vụ alert phải **read-only** trên hệ thống nguồn (theo `dnh-project-context`).
3. Nếu alert liên quan đến công nợ/aging → dùng đúng schema trong skill `dnh-debt-aging-schema`, không tự định nghĩa lại bucket.
4. Nếu alert liên quan đến sụt giảm doanh thu → baseline/ngưỡng % hiện **chưa chốt** (xem `dnh-onsite-prep`), phải đọc từ config, không hardcode.
5. Template email nên tách riêng khỏi logic tính toán (dễ chỉnh sửa nội dung mà không đụng vào business logic).
6. Log lại mỗi lần alert được trigger + gửi (ai nhận, nội dung, thời điểm) để phục vụ audit sau này.

## Script hỗ trợ

`scripts/alert_template_skeleton.py` — khung Python cơ bản để bắt đầu một alert job mới (chưa điền business logic cụ thể của 4 trigger, chỉ có structure + logging + email-sending stub).
