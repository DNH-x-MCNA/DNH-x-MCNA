# Hướng dẫn bàn giao UAT Chatbot Dược Nam Hà

## 1. Bộ tài liệu bàn giao

Gửi tester các file sau qua kênh nội bộ được DNH phê duyệt:

1. `uat_tracking_chatbot_dnh.xlsx` — checklist 138 câu, dropdown chấm điểm và trang tổng hợp.
2. `dap_an_bo_cau_hoi_dieu_hanh.md` — kết quả đối chiếu theo từng câu hỏi.
3. `bao_cao_sql_doi_chung_138.md` — bằng chứng chạy toàn bộ checker.
4. `doi_chieu_snapshot_vs_hoadon.md` — kiểm tra độc lập snapshot KPI/lương với hóa đơn.
5. Tài khoản test theo cây phân quyền; mật khẩu phải gửi riêng, không ghi trong các file trên.

Không gửi `.env`, API key, chuỗi kết nối, database hoặc log có thông tin xác thực.

## 2. Baseline kiểm thử

- Ngày chốt dữ liệu: **28/08/2026**.
- Lớp bán hàng đối chiếu: **366.725 dòng**.
- 86 checker: **80 chạy được**, **1 chạy một phần**, **1 cần kho local**, **4 bị khóa đúng chủ đích**.
- Trong 138 câu: **61 câu đủ nguồn và chạy được**, **1 câu chỉ có số hiện tại**, **65 câu cần chốt công thức hoặc thiếu một phần**, **11 câu thiếu nguồn/lịch sử**.

“SQL chạy được” chỉ là bằng chứng kỹ thuật, không thay cho kết luận UAT.

## 3. Cách tester thực hiện

1. Chọn đúng tài khoản/cấp phân quyền trong sheet `Checklist UAT`.
2. Nhập câu hỏi đúng nội dung cần kiểm tra; ghi ngày giờ và thời gian phản hồi.
3. Dán kết quả chatbot và đối chiếu file kết quả theo mã câu/checker.
4. Chấm riêng ba tiêu chí: đúng số liệu, đúng phân quyền và dễ hiểu.
5. Với lỗi, chọn mức độ, ghi nguyên nhân dự kiến, người xử lý và gắn ảnh/log.
6. MCNA sửa xong chuyển `Chờ retest`; tester DNH kiểm tra lại rồi mới chuyển `Đóng`.

## 4. Quy tắc đạt

Một test chỉ đạt khi đúng số liệu/kỳ dữ liệu, đúng phân quyền, trình bày dễ hiểu và không lộ dữ liệu nhạy cảm.

Câu thiếu nguồn/lịch sử được tính đạt khi chatbot nói rõ giới hạn và không suy đoán số liệu. Độ chính xác tính trên các test đã chấm xong:

`Độ chính xác = Số test Đạt / (Số test Đạt + Số test Không đạt)`

Điều kiện đề xuất trước UAT chính thức: không còn lỗi Critical/High chưa xử lý và độ chính xác trên bộ test hợp lệ lớn hơn 95%.

## 5. Phân công

- MCNA: tự test, cung cấp log, sửa lỗi kỹ thuật và phản hồi nguyên nhân.
- DNH: xác nhận công thức nghiệp vụ cho nhóm `DERIVED/PARTIAL`.
- Tester DNH: retest độc lập bằng tài khoản đúng phân quyền và ký xác nhận kết quả.
