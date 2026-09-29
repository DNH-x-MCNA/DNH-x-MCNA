# Dự phóng kỳ hiện tại và biểu đồ trong chatbot

Hai cờ backend độc lập, mặc định tắt trong `backend/.env.example`:

```dotenv
DNH_BAT_DU_PHONG=0
DNH_BAT_BIEU_DO=0
```

Bật bằng `1` rồi khởi động lại backend khi triển khai bản đã review. Không có API key hay cờ bí mật
ở trình duyệt. Tắt cờ biểu đồ sẽ ngừng gửi cả biểu đồ mới lẫn biểu đồ lưu trong lịch sử;
dữ liệu đã lưu vẫn được giữ để bật lại. Migration thêm cột nullable `messages.charts_json`,
tự chạy idempotent trên database hội thoại hiện có, không cần sửa kho Bravo.

## Dự phóng

- Các câu C50/M43/V09 về tháng/quý **đang chạy** được xử lý xác định bằng tool mới
  `get_current_period_projection`, không cần gọi model để tính hay chép lại số.
- Công ty/kênh/miền: thực tế dùng `revenue_by_channel`, kế hoạch dùng `_ytd_plan`.
  Đội/QLV/TDV: dùng `kpi_gap_run_rate`, giữ nguyên nguồn KPI và linear run-rate S35.
  Không coi KPI snapshot và doanh thu hóa đơn là một đại lượng để cộng chéo.
- Mốc đầu vào tối đa là ngày hôm qua và ngày dữ liệu khả dụng, để không coi ngày đang chạy dở
  là ngày hoàn chỉnh. KPI có thể dùng snapshot cũ hơn trong cùng tháng và phải nêu đúng ngày đó.
  Không có dữ liệu tháng hiện tại thì trả thiếu nguồn, không suy từ tháng cũ.
- Tháng: lũy kế / số ngày lịch đã qua × số ngày tháng. Quý: cộng thực tế các tháng đã đóng,
  cộng dự phóng tháng hiện tại, rồi dùng nhịp ngày tháng hiện tại cho các tháng còn lại của quý.
  **Chưa hỗ trợ quý ở cấp đội/TDV** vì chưa có bộ snapshot/chỉ tiêu đủ quý; trả thông báo rõ.
- Xấu/cơ sở/tốt: min/trung vị/max tỷ lệ doanh thu cuối tháng trên lũy kế cùng ngày của tối đa
  sáu tháng trước. Cần ít nhất ba tháng hợp lệ; tổng tháng đã nén không được dùng thay MTD.
  Snapshot KPI phải đúng ngày so sánh và đúng cuối tháng. Thiếu lịch sử, mẫu số không dương,
  hoặc số liệu âm thì không dựng kịch bản giả. Có số tháng hợp lệ trong câu trả lời.
- Đây là kịch bản mô tả, **không phải khoảng tin cậy hoặc xác suất đạt**. Chưa mô hình hóa ngày nghỉ,
  mùa vụ hoặc tác động CTKM mới. Không gắn nhãn "xác suất không đạt cao nhất" khi chưa có mô hình đó.
- Các công cụ dự báo cũ vẫn tắt. Câu hỏi tháng/quý/năm sau vẫn bị chặn kể cả khi bật cờ.
  Scope miền/kênh/đội do server ép; tham số model không thể mở rộng quyền.

## Biểu đồ

Biểu đồ SVG dựng từ payload tool đã thực thi và kiểm soát scope, không parse số từ văn bản model.
Các nguồn được hỗ trợ: dự phóng mới, doanh thu theo kênh, chuỗi doanh thu tháng. Câu trả lời thông thường
dùng kết quả tool cuối cùng nếu thuộc danh sách hỗ trợ; không tự vẽ mọi loại bảng hay dữ liệu lương.
Payload chỉ chứa loại chart, nhãn và số hữu hạn; không nhận HTML/SVG/URL/script từ backend/model.
Có bảng số liệu để đọc chính xác và tooltip, giá trị thiếu khác với số 0, đường có dữ liệu thiếu được ngắt.
Giới hạn 3 biểu đồ/lượt; dự phóng hiển thị tối đa 12 nhóm, chuỗi tháng tối đa 24 điểm.

Chat thường và SSE cùng trả `charts`; biểu đồ lưu cùng tin nhắn và trả qua `/history`.
Khi lịch sử lương bị ẩn theo #150, biểu đồ cũng bị xóa khỏi phản hồi. Các bước kiểm tra quyền phiên
và giới hạn gửi tin thay người khác giữ nguyên.

## Kiểm tra và triển khai

```powershell
python -m pytest tests/test_current_projection_charts.py tests/test_future_forecast_disabled.py tests/test_lich_su_an_luong.py -q
python -m pytest -q -p no:cacheprovider
npm run build
```

Các test mới dùng dữ liệu giả lập và SQLite tạm; không gọi model hay Bravo. Tool mới không được thêm
vào runner đối chiếu trực tiếp toàn bộ tool. Preview desktop/mobile dùng component thật với số liệu
giả lập; chưa đối soát dự phóng với snapshot production và chưa bật cờ trên máy 24.

Sau khi PR được review/merge, máy 24 chỉ pull bản đã kiểm thử. Bật từng cờ riêng khi được Đăng duyệt;
không sửa code trực tiếp trên máy 24. Kiểm tra một lượt hỏi có scope miền/đội, mở lại lịch sử và
tắt lại cờ biểu đồ để kiểm tra khả năng quay về hành vi cũ. Không dùng bộ business-eval đã bị cấm.
