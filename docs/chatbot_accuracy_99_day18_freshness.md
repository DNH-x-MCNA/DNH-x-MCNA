# Ngày 18 — Độ mới dữ liệu xác định bởi backend

Ngày thực hiện: 17/08/2026
Branch: `codex/chatbot-accuracy-99`

## Kết quả

Chatbot không còn giao cho model tự chép câu “Dữ liệu cập nhật đến...” từ prompt hoặc lịch sử. Sau mỗi tool chạy thành công, backend ghi nhận đúng nguồn đã đọc, tự xác định ngày dữ liệu/snapshot, giờ đồng bộ hoặc giờ truy vấn live, cảnh báo stale và gắn footer cuối câu trả lời.

Metadata có cấu trúc được trả qua `/chat`, `/chat/stream` và lưu trong `query_runs.freshness_json`. Nội dung hiển thị trên UI và nội dung lưu lịch sử là cùng một chuỗi đã chuẩn hóa; timestamp cũ do model sinh ở cuối câu bị loại trước khi lưu.

## Mapping nguồn chính

| Nhóm nghiệp vụ | Nguồn độ mới |
|---|---|
| Doanh thu/sản phẩm/khách hàng/vùng/so sánh | `vhoadon_otc`, `vhoadon_etc` theo đúng kênh đã truy vấn |
| KPI/cây doanh thu/xếp hạng/đối chiếu | `fact_tonghopkhachhang`, cộng nguồn hóa đơn nếu tool sử dụng |
| Công nợ | snapshot `fact_congno_khachhang` |
| Tồn kho | `brv_tonkhodk` và thời điểm cập nhật file warehouse |
| Thưởng/phụ cấp đã chốt | snapshot `fact_thongketinhluong` |
| Quy tắc V15/V22/V25/ASO | SQL Server live + snapshot thưởng dùng để đối chiếu |
| Chương trình khuyến mãi | SQL Server DMS live, kèm ngày bao phủ liên kết CTKM |
| SQL ad-hoc local | tự nhận diện bảng xuất hiện trong SQL; fallback về warehouse chung |
| SQL ad-hoc live | SQL Server `NH_Report_TM`, giờ thực thi thật của request |

Mỗi request có một collector riêng, không dùng state toàn cục, nên nhiều câu hỏi chạy đồng thời không thể trộn metadata nguồn.

## Quy tắc stale tạm thời

- Biến cấu hình: `CHAT_FRESHNESS_STALE_MINUTES`.
- Mặc định: 90 phút, đồng nhất với ngưỡng health watchdog hiện có.
- Đây là ngưỡng tạm thời vì DNH chưa cung cấp SLA theo từng nguồn.
- Không thay đổi scheduler hoặc quy trình đồng bộ trên máy 24.
- Nếu không xác định được thời điểm đồng bộ, chatbot cảnh báo rõ thay vì coi dữ liệu là mới.

## Thay đổi tương thích dữ liệu cũ

`conversation_memory.init()` tự thêm cột `freshness_json` bằng migration idempotent. Các dòng lịch sử cũ được giữ nguyên và đọc thành `freshness=[]`; không cần xóa hoặc tạo lại `memory.db`.

## Xác minh

```text
python -m pytest -q
110 passed, 1 deselected

python scripts/business_stress_suite.py --validate
VALID: 90 cases, 62 checkers (50 SQL Server SELECT, 12 SQL Server SP-result SELECT)
```

11 test mới bao phủ: nguồn local đơn, snapshot công nợ, nhiều nguồn và chống trùng, SQL Server live, loại footer cũ, stale cấu hình được, cô lập request đồng thời, lưu metadata lịch sử, migration database cũ, non-stream và SSE.

## Bổ sung ground truth công nợ

Q037–Q048 đã được tách thành 12 checker riêng. Ground truth công nợ gọi trực tiếp
`dbo.usp_DeptAccDueDate_GetData` trên SQL Server bằng lệnh hard-code, rollback connection, rồi
materialize result set trong RAM để chạy SELECT. Không checker nào còn dùng `local` làm ground truth.

Khi chạy nhóm công nợ, source-gate tự so SP live với `warehouse.db`; warehouse trống, khác ngày
snapshot, thiếu/thừa khóa hoặc lệch bất kỳ giá trị nào quá 1 đồng đều làm lượt test fail. Q041 lấy
cả doanh thu trực tiếp từ hai view Total trên SQL Server; Q042 bắt buộc có `--scope-area`.

Smoke live trên máy dev ngày 17/08/2026: cả 12/12 checker SP-result chạy thành công; source-gate trả
`warehouse_empty` đúng thực trạng warehouse dev, vì vậy tiến trình vẫn trả exit code lỗi thay vì PASS giả.

## Điểm đang chờ DNH

1. SLA chính thức cho từng nguồn/bảng để thay ngưỡng 90 phút tạm thời.
2. Xác nhận nghiệp vụ cuối cùng cho V25/ASO (không tự sửa công thức khi chưa có xác nhận).

Tài khoản test theo vai trò đã có. Chưa merge `master`, chưa deploy hoặc sửa dịch vụ máy 24 trong bước này.
