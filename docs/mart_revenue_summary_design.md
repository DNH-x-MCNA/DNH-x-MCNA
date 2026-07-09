# Mart Layer — `mart_revenue_summary`

Thiết kế theo đề xuất 08/07/2026: chatbot đọc bảng tổng hợp sẵn thay vì quét bảng raw hàng
triệu dòng mỗi câu hỏi doanh thu — giảm Disk IO gần về 0, tránh statement timeout kể cả khi
Supabase đang cạn IO budget.

## Schema

```sql
CREATE SCHEMA IF NOT EXISTS mart_layer;

CREATE TABLE IF NOT EXISTS mart_layer.mart_revenue_summary (
    report_date     date NOT NULL,
    channel         text NOT NULL,           -- 'OTC' hoặc 'ETC'
    revenue         numeric(18,2) NOT NULL DEFAULT 0,
    invoice_count   integer NOT NULL DEFAULT 0,
    updated_at      timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (report_date, channel)
);

CREATE INDEX IF NOT EXISTS idx_mart_revenue_date ON mart_layer.mart_revenue_summary (report_date);
```

**Grain**: 1 dòng / ngày / kênh (OTC hoặc ETC) — ví dụ 1 năm dữ liệu ≈ 365 ngày × 2 kênh ≈ 730
dòng, đúng tinh thần "vài trăm dòng" đã đề xuất. Mọi câu hỏi tổng hợp theo ngày/tuần/tháng/quý/
năm chỉ cần `SUM(revenue) WHERE report_date BETWEEN x AND y GROUP BY channel` — quét tối đa vài
trăm dòng thay vì hàng triệu dòng hóa đơn gốc.

**Business rule tính `revenue`**: giữ NGUYÊN đúng quy tắc đã kiểm chứng nhiều lần trong session
này (loại dòng CTKM khuyến mãi, loại chứng từ hủy, loại mã chuyển kho nội bộ qua JOIN dim khách
hàng) — xem `_period_revenue()` trong `src/etl.py`, mart layer dùng lại chính xác logic đó theo
ngày thay vì theo khoảng ngày tùy ý.

## Phạm vi KHÔNG làm trong mart layer này

- Không có breakdown theo khách hàng/sản phẩm/nhân viên — những câu hỏi cần chi tiết đó (vd "top
  khách hàng", "sản phẩm bán chạy") vẫn phải đọc bảng raw như hiện tại, mart layer chỉ tăng tốc
  nhóm câu hỏi TỔNG HỢP DOANH THU thuần túy (chiếm phần lớn câu hỏi thường gặp qua thực tế test
  hôm nay: "doanh thu hôm nay/tháng này/quý này bao nhiêu").
- Không tự động mở rộng sang công nợ/tồn kho/KPI trong lượt này — nếu cần, làm mart riêng theo
  domain, không gộp chung 1 bảng đa mục đích.

## Vận hành

- **Backfill lần đầu** (`scripts/build_mart_revenue_summary.py --full`): quét toàn bộ lịch sử,
  chỉ chạy 1 LẦN khi IO đã hồi phục — đây là truy vấn NẶNG (GROUP BY toàn bảng), không chạy khi
  IO đang cạn.
- **Cập nhật hằng đêm** (`scripts/build_mart_revenue_summary.py`, mặc định incremental): chỉ tính
  lại N ngày gần nhất (mặc định 7 — đủ để bắt các chứng từ nhập trễ/điều chỉnh), rẻ hơn NHIỀU so
  với full rebuild. Đăng ký lịch 2h sáng qua `scripts/register_mart_refresh_schedule.bat`.
- Chatbot: xem `ai_agent/chatbot.py` — hướng dẫn sinh SQL ưu tiên `mart_layer.mart_revenue_summary`
  cho câu hỏi doanh thu tổng hợp theo kỳ, chỉ rơi về bảng raw khi cần chi tiết hơn mức ngày/kênh.
