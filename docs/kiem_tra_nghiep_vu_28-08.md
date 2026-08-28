# Kiểm tra nghiệp vụ và phân quyền — 28/08/2026

## Kết quả

- Production `516525b` đã qua ba smoke test: Top 10 OTC/ETC tách riêng, nhãn Trưởng phòng đúng,
  và QLV chỉ thấy đội của mình.
- Rà soát tiếp 40 công cụ nghiệp vụ phát hiện ba đường rò cùng nguyên nhân: nhánh phân quyền
  `scope_channel="ETC"` chưa loại dữ liệu OTC một cách đối xứng.
- Đã sửa tại:
  - `get_revenue_by_channel` — cả hóa đơn chi tiết và lịch sử tháng đã nén;
  - `get_customer_detail` — khách hai kênh chỉ trả phần ETC, khách thuần OTC bị từ chối;
  - `check_order_timing` — không còn đưa đơn OTC vào phân tích của tài khoản ETC.
- Các báo cáo gọi lại `get_revenue_by_channel`, gồm `compare_periods` và
  `revenue_ytd_cumulative`, được khóa test để bảo đảm giữ nguyên vùng, kênh và mã đội.
- Bổ sung kiểm thử tồn kho theo lô/hạn dùng: ghép đúng khóa kép `(item_lot_code, item_id)`, phân
  loại hết hạn/cận hạn, ghi nhận lô thiếu hạn và ép phạm vi vùng.

## Bằng chứng kiểm thử

- Trọng điểm: **23 passed**.
- Toàn hệ thống sau vòng đóng coverage: **424 passed, 1 deselected**.
- Kiểm tra cú pháp và `git diff --check`: đạt. Cảnh báo `PermissionError` khi pytest dọn thư mục
  tạm trên Windows xuất hiện sau khi test đã hoàn tất, không phải lỗi kiểm thử.
- Đối chiếu tĩnh tên hàm trong test: **40/40 công cụ** đã có test trực tiếp. Vòng cuối bổ sung test
  cho `get_audit_log`, `get_employee_directory`, `get_receivables_history_dates`: tài khoản thường
  không thể tự nâng quyền xem chi phí người khác; scope vùng ghi đè bộ lọc nhân viên do AI truyền;
  ngày snapshot công nợ được khử trùng, sắp mới nhất trước. Tham số `limit` của cả ba công cụ được
  chặn trong khoảng 1–100 để giá trị âm không làm trả toàn bộ lịch sử ngoài ý muốn.

## Email QLV

Danh sách địa chỉ email thật chưa đủ để kích hoạt gửi hàng loạt. Ngay cả khi có địa chỉ, DNH dùng
mail server riêng nên còn phải chốt một trong các đường tích hợp: SMTP relay của DNH, tài khoản gửi
được phép relay, hoặc Microsoft Graph/Power Automate trong tenant của DNH. Trước khi có cấu hình đó:

- không bật lịch gửi email cho 19 QLV;
- chỉ gửi thử thủ công về địa chỉ kiểm thử đã thống nhất;
- UAT chatbot và phân quyền tiếp tục bình thường, không phụ thuộc email.

## Bước triển khai an toàn trên máy 24

1. Fetch đúng commit của nhánh sửa và chạy toàn bộ pytest khi đã gỡ các biến API.
2. Chạy `python scripts/verify_etc_channel_scope.py`. Script đọc dữ liệu thật nhưng không gọi API,
   không gửi tin và không ghi database; nó kiểm tra doanh thu tổng hợp, chi tiết khách hai kênh và
   thời điểm đơn với scope ETC.
3. Chỉ fast-forward production sau khi cả ba kết quả không chứa số OTC.
4. Backup database/cấu hình, khởi động lại đúng một bộ supervisor, kiểm tra `/health`.
5. Smoke test một tài khoản ETC trên giao diện trước khi kết thúc triển khai.
