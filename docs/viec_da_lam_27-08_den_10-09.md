# Công việc đã làm 27/08 – 10/09/2026

**Tổng: 95 commit · 91 file · +19.748 / −904 dòng · 546 test tự động đạt**

Nhịp theo ngày: 27/08 (18) · 28/08 (6) · 03/09 (2) · 04/09 (16) · 05/09 (2) · 07/09 (19) · 08/09 (9) · 09/09 (15) · 10/09 (8)

---

## 1. Báo cáo tự động cho Quản lý vùng

- Xây báo cáo QLV hằng ngày, hằng tuần, hằng tháng, giới hạn đúng phạm vi đội
- Gửi báo cáo tuần/tháng qua email; chuẩn hoá định dạng danh sách email
- Tự động nhận diện đội QLV để đối chiếu (không cần khai báo tay)
- Công cụ chẩn đoán chênh lệch QLV ở chế độ chỉ đọc
- Loại TDV đã nghỉ khỏi đối chiếu QLV
- Tách rollup theo kênh khỏi đội QLV (trước đây bị trộn làm sai số)
- Hạ Adaptive Card Teams 1.5 → 1.4 và gỡ bảng để qua giới hạn Power Automate

## 2. Phân quyền và phạm vi dữ liệu

- Siết phạm vi kênh ETC đối xứng hai chiều
- Trình kiểm tra ETC production ở chế độ chỉ đọc
- Chuẩn hoá nhãn vai trò Trưởng phòng / Giám đốc miền
- Tách xếp hạng sản phẩm theo kênh
- Ẩn tên tool nội bộ khỏi câu trả lời người dùng
- Script rà tài khoản thiếu phạm vi

## 3. Tồn kho

- Đồng bộ hệ kho SẢN XUẤT — trước đó chatbot chỉ nhìn thấy 2% giá trị tồn
- Sửa lỗi cộng dồn tồn đầu kỳ qua 3 năm tài chính
- Sửa nhãn kho B01 bị trùng tên với hệ kho sản xuất
- Báo cáo nguy cơ thiếu hàng theo phạm vi
- Script kiểm tồn kho sau deploy, tự kết luận Đạt / Chưa đạt

## 4. KPI, doanh thu và đội ngũ

- Gộp snapshot Bravo theo THÁNG thay vì ghim MAX(SaveDate)
- Dùng roster kỳ tròn cho xếp hạng đầu tháng (trước đó trả rỗng)
- Hiện rõ nhân sự thiếu dữ liệu thay vì bỏ qua im lặng
- Đưa CTV vào `_team_of_qlv`, giữ ngưỡng thưởng CTV trong cây doanh thu
- Sửa mẫu số KPI thiếu người
- Khôi phục target đội, chặn kết luận KPI giữa tháng khi chưa đủ dữ liệu
- Danh sách đội lấy theo snapshot giữa tháng — gốc thật của lỗi M01
- Chốt phân giải DMSId của đội + script chẩn đoán

## 5. Khách hàng và vòng đời

- Chuỗi vòng đời khách theo hoá đơn (C29), khoá đúng phạm vi OTC
- Ổn định cửa sổ lịch sử khi tính tái kích hoạt
- Tách IsAC khỏi ASO
- Đối chiếu C20, giới hạn phạm vi thay đổi phân công C28
- Định tuyến và benchmark câu hỏi hành vi khách
- Cơ cấu SKU và cặp bán chéo
- Ngưỡng khách lớn cho hành động giữ chân
- **Tool khách rủi ro 3 tín hiệu theo checker S88** — ngừng mua / giảm mua mạnh / kéo dài chu kỳ (M22)

## 6. Đơn hàng và đi tuyến

- Gỡ suy luận gian lận từ chênh CreatedAt/DocDate sau khi DNH xác nhận hai mốc thuộc hai giai đoạn
- Đối chiếu đơn DMS với hoá đơn, thống kê ngoại lệ
- Báo cáo hiệu quả đi tuyến từ DMS_DiTuyen
- Kiểm phạm vi đơn ETC không dùng heuristic CreatedAt
- Fail-closed khi hợp đồng ETC thiếu khoá liên kết

## 7. Định tuyến và độ tin cậy câu trả lời

- Định tuyến câu hỏi cấp C-Level, Trưởng phòng/Giám đốc miền và QLV
- Khoá chế độ báo cáo cho toàn bộ 138 câu
- Chặn tính YTD khi kỳ chưa đủ dữ liệu
- Nêu rõ giới hạn nguồn thay vì trả lời như đã đủ dữ liệu
- Từ chối kết luận chênh lệch doanh thu chưa có bằng chứng
- Giữ ranh giới kỳ khi dữ liệu chỉ có một phần

## 8. Bộ kiểm và công cụ đối chứng

- Sửa 7 câu bị gán nhầm checker; bổ sung checker S88–S92
- Bộ kiểm bất biến phủ đủ 41 công cụ nghiệp vụ
- Đối chiếu toàn bộ 138 câu với Bravo qua UAT trực tiếp
- **Chạy trọn 92 checker SQL trên Bravo**: 85 chạy được, 1 chạy một phần, 4 bỏ qua chủ đích
- **Phát hiện và sửa lỗi S69** — checker của V21 chưa từng chạy được (thiếu chiếu cột `ManagerAreaCode`)
- **Kiểm định tuyến 138 câu, chi phí 0, chạy 3 giây** — 135/138 có tool bắt buộc
- Sửa 2 lỗi nặng ngày 04/09 bằng phép kiểm chạy được
- Cảnh lỗi đếm trùng số khách hàng
- Trình chạy 138 câu: dừng đúng khi tài khoản nhà cung cấp lỗi, che API key khỏi log

## 9. Tài liệu và bàn giao

- Gói bàn giao UAT cho tester (SQL + Excel + hướng dẫn)
- Trang quyết định Nhóm A (A1–A9) DNH cần chốt trước UAT
- Bản rút gọn 2 câu DNH cần xác nhận, hạn 10/09
- Kế hoạch 04–30/09
- Báo cáo toàn bộ công việc 27/08–09/09 theo commit
- Handoff sửa UAT cho Antigravity + báo cáo audit
- **Sửa mẫu số chấm điểm: 138 → 119 câu chấm được**, tỷ lệ 44,9% → 52,1%

## 10. Giao diện

- Xử lý sạch lỗi lint Next 16
- Cảnh báo rõ cây `frontend/` trùng, không dùng làm root
