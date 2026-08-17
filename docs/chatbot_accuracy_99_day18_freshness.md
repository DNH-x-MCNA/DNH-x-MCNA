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
105 passed, 1 deselected

python scripts/business_stress_suite.py --validate
VALID: 90 cases, 57 read-only SQL checkers
```

11 test mới bao phủ: nguồn local đơn, snapshot công nợ, nhiều nguồn và chống trùng, SQL Server live, loại footer cũ, stale cấu hình được, cô lập request đồng thời, lưu metadata lịch sử, migration database cũ, non-stream và SSE.

## Điểm đang chờ DNH

1. SLA chính thức cho từng nguồn/bảng để thay ngưỡng 90 phút tạm thời.
2. Xác nhận nghiệp vụ cuối cùng cho V25/ASO (không tự sửa công thức khi chưa có xác nhận).

Tài khoản test theo vai trò đã có. Chưa merge `master`, chưa deploy hoặc sửa dịch vụ máy 24 trong bước này.
