# Go-Live Phase 0 — Bảng ánh xạ cột tracking cho incremental sync (BẢN SƠ BỘ)

> **Trạng thái: SƠ BỘ — cần Đăng review trước khi sang Phase 2.**

## Kiến trúc dữ liệu thực tế (đã xác nhận)

```
Bravo (OTC) / DMS (ETC)   →   [ETL trên máy chủ vật lý riêng]   →   Dữ liệu HẬU-ETL đã xử lý
   (nguồn ERP/CRM thô)          (xử lý, chuẩn hóa)                    (nằm trên máy chủ đó)
                                                                              │
                                                                     Supabase = VIEW của lớp
                                                                     dữ liệu hậu-ETL này
```

**Hệ quả quan trọng:** Supabase KHÔNG phải "mirror thô có thể lệch nguồn" — nó là **VIEW của
lớp dữ liệu hậu-ETL đã qua xử lý**. Do đó các cột `CreatedAt / ModifiedAt / SyncAt / Id`
quan sát được **chính là cột tracking thật của lớp dữ liệu mà incremental sync sẽ đọc**, dùng
được trực tiếp cho Phase 2. Lớp Bravo/DMS thô nằm BÊN DƯỚI lớp này và đã có ETL riêng lo —
incremental sync ở Phase 2 làm việc với **lớp hậu-ETL** (qua view Supabase / máy chủ hậu-ETL),
KHÔNG cần động tới Bravo/DMS thô.

Toàn bộ business logic (chatbot, các cảnh báo Phase 1) đọc đúng lớp hậu-ETL này — dữ liệu đã
xử lý, đúng để tính doanh thu/công nợ/tồn kho.

## Bảng ánh xạ (lớp dữ liệu hậu-ETL, quan sát qua Supabase view)

| Bảng (lớp hậu-ETL) | Cột tracking khả dụng | Kiểu | Ghi chú |
|---|---|---|---|
| `brv_hoadonhdr` (HĐ OTC - header) | `DocDate`, `SaveDate` (TEXT `YYYY-MM-DDTHH:MM:SS`), `Id` | text / bigint | `DocDate`/`SaveDate` lưu dạng TEXT — incremental cần so sánh `::date`/`::timestamp`. Nên incremental theo `Id` tăng dần cho chắc. |
| `brv_hoadonct` (HĐ OTC - chi tiết) | `Id` (bigint), `CreatedAt`, `ModifiedAt`, `SyncAt` (timestamp) | bigint / timestamp | ✅ Có đủ cột tracking. `Id` tăng dần → incremental theo `Id`; `ModifiedAt` để bắt dòng cũ bị cập nhật. |
| `brvsx_hoadonhdr` (HĐ ETC - header) | `DocDate`, `SaveDate`, `Id` | text / bigint | Tương tự `brv_hoadonhdr`. |
| `brvsx_hoadonct` (HĐ ETC - chi tiết) | `Id`, `CreatedAt`, `ModifiedAt`, `SyncAt` | bigint / timestamp | ✅ Có đủ cột tracking. Tương tự `brv_hoadonct`. |
| `dms_khachhang` / `dmssx_khachhang` (khách hàng) | `Code`, (kiểm tra thêm `ModifiedAt` khi mạng ổn) | text | Bảng biến động chậm — full-scan giới hạn chấp nhận được. **KHÔNG có cột hạn mức tín dụng** (đã kiểm tra, xem mục dưới). |
| `fact_tonghopkhachhang` (tổng hợp KH/KPI) | `SaveDate` (mốc kỳ), `EmployeeCode` | text | `SaveDate` là mốc chốt kỳ, rebuild theo kỳ. |
| `brv_sanpham` (sản phẩm) | `Id`, `Code`, `CreatedAt`, `ModifiedAt`, `SyncAt` | bigint / timestamp | ✅ Có đủ cột tracking. Biến động chậm. |
| `receivable_detail` (mart) | `period` (TEXT `M_YYYY`) | text | Không có timestamp dòng. Dùng logic kỳ (`_latest_period_key`), rebuild theo kỳ. |
| `inventory` (mart) | *(không có cột tracking)* | — | Bảng snapshot, rebuild toàn bộ mỗi kỳ. Full-scan chấp nhận được vì nhỏ (~211 dòng). |
| `kpi_summary` (mart) | *(kiểm tra thêm khi mạng ổn)* | — | Bảng snapshot theo kỳ, rebuild. |

## Phát hiện quan trọng cho Phase 1.2b (credit limit)

Đã kiểm tra `information_schema` trên Supabase: **KHÔNG tìm thấy cột hạn mức tín dụng**
(pattern `%credit%limit%`, `%hanmuc%`) trong `dms_khachhang`, `dmssx_khachhang`,
`receivable_detail`. → **Đây là GAP DỮ LIỆU, không phải gap code.** Hàm
`check_credit_limit_exceeded_alert()` đã viết phòng thủ: tự dò cột lúc chạy, no-op + log
rõ nếu chưa có; tự kích hoạt khi DNH đưa cột hạn mức vào mart.

**Cần hỏi DNH:** hạn mức tín dụng từng khách hàng lưu ở đâu trong Bravo/DMS, có thể đưa
vào staging/mart không?

## Việc còn phải làm để hoàn tất Phase 0

1. Kiểm tra nốt cột tracking của `dms_khachhang`/`dmssx_khachhang`/`kpi_summary` khi kết nối
   Supabase ổn định (hiện mạng máy local tới Supabase đang chập chờn, một số query timeout).
2. Xác nhận cột tracking (`Id`, `ModifiedAt`, `SyncAt`) trên lớp hậu-ETL đã có **index** chưa
   — nếu chưa, incremental query mỗi 5-10 phút sẽ chậm; tạo index (đọc-only, an toàn).
3. Chốt với DNH: đích go-live là giữ lớp hậu-ETL hiện tại (view Supabase / máy chủ hậu-ETL)
   hay đẩy tiếp sang SQL Server on-prem 3-layer như plan mô tả — quyết định này ảnh hưởng
   Phase 2/3.
4. Đăng review & duyệt bảng mapping trước khi bắt đầu Phase 2 (incremental sync).
