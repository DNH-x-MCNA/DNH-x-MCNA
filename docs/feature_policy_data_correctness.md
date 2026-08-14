# Chính sách sản phẩm: chỉ dữ liệu thực tế và lịch sử

Hiệu lực từ ngày 14/08/2026, theo kết luận cuộc họp tiến độ Dược Nam Hà ngày 13/08/2026.

## Mục tiêu

Ưu tiên tuyệt đối độ đúng, khả năng đối chiếu và truy vết nguồn dữ liệu. Ngưỡng chất lượng trước khi trình diễn/go-live là tối thiểu 95%; mục tiêu chiến lược đối với dữ liệu lịch sử là khớp 100% với nguồn SQL Server chính trong phạm vi đã được Dược Nam Hà xác nhận.

Không tuyên bố “đúng 100%” nếu chưa có biên bản đối chiếu trên SQL Server chính. Khi nguồn dev, `warehouse.db` và SQL Server chính khác nhau, SQL Server chính là nguồn chuẩn để nghiệm thu.

## Đã tắt hoàn toàn

- Dự báo/dự phóng doanh thu tương lai.
- Dự báo tỷ lệ hoàn thành KPI cuối tháng, bao gồm mô hình cũ Model 1.
- Ngoại suy từ doanh thu/KPI lũy kế sang kết quả cuối kỳ.
- Dự báo ngày hoặc số tháng bán hết tồn kho; cảnh báo “sắp cạn/sắp hết hàng” dựa trên tốc độ bán.
- Cảnh báo tồn chết/bán chậm nếu công thức còn dựa trên `months_to_sell`.
- Các entrypoint nghiên cứu tạo tập dữ liệu dự báo trong `scripts/forecast_*_dataset.py`.

Các tính năng trên bị khóa ở tầng code, không có cờ môi trường để bật lại. Muốn mở lại cần quyết định sản phẩm mới, công thức được Dược Nam Hà ký xác nhận, bộ dữ liệu nghiệm thu trên máy chính và regression test độc lập.

## Vẫn được phép

- Doanh thu, công nợ, KPI và tồn kho thực tế đến thời điểm đồng bộ gần nhất.
- So sánh giữa các kỳ đã phát sinh: ngày/tuần/tháng/quý/năm và cùng kỳ.
- KPI thực đạt so với target/chỉ tiêu đã được nhập.
- Tra cứu target, kế hoạch hoặc ngân sách của kỳ tương lai nếu đó là dữ liệu do con người đã nhập; chatbot không tự suy diễn giá trị mới.
- Cảnh báo công nợ đến hạn/quá hạn dựa trên ngày và số dư thực tế.
- Cảnh báo doanh thu giảm dựa trên hai kỳ đã phát sinh.
- Cảnh báo khách hàng không mua trong 3–4 tháng dựa trên giao dịch lịch sử.
- Tồn kho snapshot hiện tại. Cảnh báo tồn chết chỉ được mở lại khi có công thức dựa trên dữ liệu thực tế đã được Dược Nam Hà chốt, ví dụ không phát sinh giao dịch hoặc tỷ lệ bán thực tế so với tồn snapshot.

Giá vốn/COGS tiếp tục không được đưa vào kết quả cho tới khi Dược Nam Hà xác nhận nguồn và công thức.

## Quy tắc trả lời bắt buộc

Mọi câu trả lời có số liệu phải cho biết thời điểm dữ liệu. Với các báo cáo trọng yếu, kết quả phải truy vết được nguồn bảng/view/stored procedure, tham số lọc, công thức tổng hợp và phạm vi phân quyền. Nếu thiếu dữ liệu hoặc chưa đối chiếu được, hệ thống phải nêu rõ trạng thái thiếu/chưa xác minh, không điền số 0 và không tự ước tính thay thế.

Khi người dùng yêu cầu dự báo, chatbot trả lời rằng tính năng đã tắt và đề xuất các lựa chọn dựa trên dữ liệu thật: số lũy kế, so sánh lịch sử, KPI thực đạt so với target và thời điểm cập nhật gần nhất.
