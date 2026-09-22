# Danh sách câu hỏi Onsite DNH (07/07/2026)

> Ghi chú: đây là bản khung dựa trên 3 open item đã biết. Bổ sung câu hỏi
> chi tiết hơn (nếu đã có sẵn từ tài liệu chuẩn bị onsite trước đó) vào
> file này để Claude dùng làm nguồn tham chiếu đầy đủ.

## 1. Revenue drop baseline
- So sánh với kỳ nào: tháng trước, cùng kỳ năm trước, hay trung bình 3 tháng?
- Ngưỡng % nào được coi là "sụt giảm đáng báo động" để trigger alert?
- Áp dụng theo SKU, theo khu vực, hay theo tổng doanh thu công ty?

## 2. Debt aging date basis
- Dùng `invoice_date` (ngày xuất hoá đơn) hay `due_date` (ngày đến hạn)?
- Có case đặc biệt nào (công nợ trả góp, công nợ có điều chỉnh) cần xử lý riêng?
- Bucket boundaries hiện tại (0-30/31-60/61-90/>90) có đúng với cách DNH đang quản lý không?

## 3. Cấu hình cloud DB (Supabase) cho warehouse trung gian
> Đã đổi từ on-prem SQL Server sang cloud Postgres (Supabase) — cập nhật 03/07/2026, xem `dnh-project-context`. Câu hỏi cũ về vị trí/instance SQL Server không còn áp dụng; thay bằng các câu dưới.
- Region/project Supabase cụ thể nào? Có ràng buộc data residency (dữ liệu dược phẩm/khách hàng ra khỏi VN) cần DNH duyệt riêng không?
- Ai giữ service role key / connection string (`CLOUD_DB_URL`)? Quy trình rotate credential ra sao?
- Có cần IP allowlist / VPN/tunnel riêng cho đội MCNA kết nối, hay dùng thẳng public endpoint của Supabase?
- Backup/retention policy trên cloud do ai chịu trách nhiệm — MCNA hay Supabase managed backup mặc định có đủ theo yêu cầu DNH không?
- DNH có cần ký lại phụ lục hợp đồng vì đổi từ cam kết on-prem sang cloud không (đây là thay đổi so với điều khoản data residency gốc)?

## Câu hỏi bổ sung nên hỏi
- Xác nhận phạm vi Phase 1 không bao gồm dashboard — có gây hiểu nhầm với stakeholder không trực tiếp tham gia ký hợp đồng không?
- Timeline 9 tuần có xung đột với lịch nội bộ nào của DNH (đóng sổ kỳ kế toán, kiểm toán...) không?
- Ai là người sign-off cuối cùng cho từng deliverable của Phase 1 và Phase 2?
