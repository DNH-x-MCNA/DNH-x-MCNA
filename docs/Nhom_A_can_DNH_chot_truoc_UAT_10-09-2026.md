# Nhóm A — Các quyết định DNH cần chốt trước UAT

**Hạn phản hồi đề nghị: 10/09/2026.** Nếu chưa có phản hồi, MCNA chỉ được dùng giả định đã ghi rõ;
không biến giả định thành kết luận nghiệp vụ.

Số câu ảnh hưởng dưới đây là số câu **trực tiếp** trong bộ 138, đếm theo nội dung câu hỏi. Một câu
có thể bị nhiều quyết định cùng lúc nên không cộng các dòng thành tổng.

| Mã | DNH cần xác nhận | Số câu ảnh hưởng trực tiếp | Mã câu |
|---|---|---:|---|
| A1 | `usp_DeptAccDueDate_GetData` có phải nguồn công nợ chuẩn; ngày quá hạn lấy theo hạn của từng hóa đơn? | 18 | C25, C26, C37–C40, C44, C53, M04, M29, M37, M38, M41, V28, V35–V37, V40 |
| A2 | Mốc tuổi nợ dùng chung là 1–15 / 16–30 / 31–45 / >45 ngày hay quy ước khác theo OTC/ETC? | 10 | C25, C37, C39, C44, M37, M38, V35–V37, V40 |
| A3 | Giá trị tồn kho dùng giá vốn bình quân, giá nhập gần nhất hay bảng giá riêng? | 9 | C25, C41, C42, C53, M29, M39, M40, V38, V39 |
| A4 | `MBKV12` là chỉ tiêu riêng hay chỉ tiêu cấp vùng bị cộng chồng; còn trường hợp tương tự không? | 16 | C45, C47, M11–M13, M15, M17, M19, M20, M43, V01, V08, V11, V17, V30, V37 |
| A5 | ETC có chỉ tiêu cá nhân không; nếu không thì KPI ETC theo nhóm hàng, bệnh viện/thầu hay vùng? | 2 câu ETC trực tiếp; tối đa 16 câu KPI khi lọc ETC | C43, M41; và nhóm câu KPI ở A4 khi người dùng yêu cầu riêng ETC |
| A6 | Báo cáo tóm tắt dùng mốc nào: hoàn thành kế hoạch 100%, đạt KPI 80%, hay cổng thưởng nhóm hàng 65%/70%; giữa tháng có so theo tiến độ ngày không? | 16 | C45, C47, M11–M13, M15, M17, M19, M20, M43, V01, V08, V11, V17, V30, V37 |
| A7 | SP lương **chỉ đếm OTC và có trừ hàng trả** có đúng chủ đích tính lương không? | 4 câu lương trực tiếp; 16 câu KPI phụ thuộc snapshot | C48, C53, M20, V18; cộng nhóm câu KPI ở A4 |
| A8 | Giữ nguyên 24 nhân viên `IsDuplicate=1` đang chiếm khoảng **373 triệu (1,05%)** doanh số tầng TDV tháng 8, dù không truy ngược được hóa đơn qua DMSId của chính họ? | 18 | Nhóm 16 câu KPI ở A4, cộng C54 và V17 |
| A9 | “Tuần trong tháng” là tuần lịch Thứ Hai–Chủ Nhật hay các đoạn ngày 01–07, 08–14…? | 4 | M06, V03, V10, V28 |

## Bằng chứng cần lưu cùng phản hồi

- A7: kết quả đối chiếu snapshot KPI/lương với hóa đơn gốc, tách rõ OTC/ETC và hàng trả.
- A8: danh sách 24 mã, doanh số liên quan và lý do không map được qua DMSId.
- Mỗi câu trả lời cần có người xác nhận, ngày xác nhận và tài liệu/quy định nguồn nếu có.

## Quy tắc tạm thời tới hạn 10/09

- Không tự tính công nợ ngoài SP chuẩn.
- Không hiển thị giá trị tồn kho khi chưa chốt nguồn giá.
- Không gọi 65%/70% là “đạt KPI” hoặc “đạt chỉ tiêu”.
- Không kết luận KPI cá nhân ETC khi chưa có nguồn target cá nhân.
- Với “tuần trong tháng”, hỏi lại người dùng muốn tuần lịch hay đoạn 7 ngày cho tới khi DNH chốt.
