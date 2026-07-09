# Go-Live Phase 0 — Bảng ánh xạ cột tracking cho incremental sync (HOÀN THIỆN)

> **Trạng thái: đã khảo sát đầy đủ 42 bảng + index thực tế. Còn 1 việc: Đăng review & duyệt.**

## Kiến trúc dữ liệu (đã chốt tạm)

```
Bravo (OTC) / Bravo SX (ETC) / DMS   →   [ETL bên thứ ba, ~1 giờ/lần]   →   Lớp hậu-ETL   →   Supabase (view)
```

Supabase là **VIEW của lớp hậu-ETL đã xử lý** (không phải mirror thô Bravo/DMS). Cột
`CreatedAt/ModifiedAt/SyncAt/Id` trên bảng raw là cột tracking thật của lớp này. **Quyết định
go-live: giữ tạm lớp hậu-ETL làm nguồn**, không dựng SQL Server on-prem song song.

## Bảng ánh xạ cột tracking + trạng thái index

| Bảng (số dòng) | Cột tracking | Đã index? | Chiến lược incremental |
|---|---|---|---|
| `brv_hoadonhdr` (25.557) | `Id`, `SyncAt`, `ModifiedAt`, `DocDate` | ❌ (chỉ CustomerCode, Stt) | Theo `Id` — **cần thêm index `Id`/`SyncAt`** |
| `brv_hoadonct` (187.065) | `Id`, `SyncAt`, `ModifiedAt` | ❌ (chỉ ItemCode, Stt) | Theo `Id` — cần index; đây cũng là bảng dùng cho **watermark** `MAX(SyncAt)` |
| `brv_donhang` (26.671) | `Id` (PK), `SyncAt`, `ModifiedAt` | ✅ `Id` (PK) | Theo `Id` — hiệu quả sẵn |
| `brv_donhangct` (193.217) | `Id`, `SyncAt`, `ModifiedAt` | ❌ (chỉ BizDocId, ItemCode) | Theo `Id` — cần index |
| `brv_khachhang` (40.094) | `Id`, `ModifiedAt`, `DueDate` | ❌ (không có index nào) | Biến động chậm → full-scan giới hạn OK |
| `brv_sanpham` (382) | `Id` (PK), `SyncAt`, `ModifiedAt` | ✅ `Id` (PK) | Nhỏ → full-scan OK |
| `brvsx_hoadonhdr` (2.448) | `Id`, `SyncAt`, `ModifiedAt`, `DocDate` | ❌ (chỉ CustomerCode) | Theo `Id` — nhỏ, chấp nhận |
| `brvsx_hoadonct` (9.919) | `Id`, `SyncAt`, `ModifiedAt` | ❌ (chỉ ItemCode, Stt) | Theo `Id` — nhỏ, chấp nhận |
| `brvsx_thekholot` (35.709) | `Id`, `SyncAt`, `ModifiedAt`, `ItemLotCode` | ❌ (không có index nào) | Theo `Id` — cân nhắc index nếu dùng nhiều |
| `brvsx_tralai` (18) | `Id`, `SyncAt`, `ModifiedAt`, `ExpiryDate` | ❌ (không có index nào) | Tí hon → full-scan OK |
| `dms_khachhang` (47.412) | `Id`, `SyncAt`, `ModifiedAt`, `Code` | ✅ `Code`, `CityId` (❌ Id/SyncAt) | Biến động chậm → full-scan giới hạn OK |
| `dmssx_khachhang` (39.967) | `Id` (PK), `SyncAt`, `ModifiedAt` | ✅ `Id` (PK), Code | Theo `Id` — hiệu quả sẵn |
| `dmssx_donhanghdr` (37.406) | `Id`, `SyncAt`, `ModifiedAt`, `DocDate` | ❌ (không có index nào) | Theo `Id` — cần index nếu incremental |
| `fact_tonghopkhachhang` (38.249) | `Id` (PK), `SaveDate`, `CreatedAt` | ✅ `Id` (PK), `SaveDate`, EmployeeCode | Theo `SaveDate` (mốc kỳ) — index sẵn ✅ |
| `receivable_detail` (165.102) — mart | `period` (không có tracking dòng) | ❌ **không index nào** | Rebuild theo kỳ; **cần index `period`** (xem dưới) |
| `inventory` (211) — mart | *(không có)* | ❌ | Snapshot nhỏ → rebuild toàn bộ OK |
| `kpi_summary` (58) — mart | *(không có)* | ❌ | Snapshot nhỏ → rebuild OK |

## Phát hiện & khuyến nghị

1. **Cột tracking hầu như chưa có index.** `Id`/`SyncAt`/`ModifiedAt` chỉ được index (qua PK) ở
   4 bảng (`brv_donhang`, `brv_sanpham`, `dmssx_khachhang`, `fact_tonghopkhachhang`). Các bảng
   hóa đơn lớn (`brv_hoadonhdr/ct`) chỉ index cột join (CustomerCode/ItemCode/Stt).
   → **Nếu về sau làm incremental sync thật**, phải thêm index trên cột tracking trước, nếu không
   query delta mỗi 5-10 phút sẽ seq-scan chậm. Với kiến trúc đã chốt (watermark `MAX(SyncAt)` mỗi
   ~1 giờ) thì seq-scan chấp nhận được — **chưa bắt buộc thêm index cho tracking**.

2. **⭐ Mart thiếu index `period` (`receivable_detail` 165k):** dashboard + alert query
   `WHERE period = ...` liên tục nhưng bảng không có index nào → seq-scan 165k dòng mỗi lần.
   **LƯU Ý QUAN TRỌNG:** `receivable_detail` là bảng bị **rebuild/replace khi đồng bộ** (theo
   header `scripts/add_supabase_indexes.sql`), nên **KHÔNG được thêm index vào script thủ công đó**
   — sẽ bị xóa ở lần replace kế tiếp. Cách đúng: hoặc (a) thêm `CREATE INDEX ... (period)` vào
   **cuối routine rebuild** mart, hoặc (b) đổi rebuild từ DROP+recreate sang **TRUNCATE + append**
   (giữ nguyên schema/index). Cần xác nhận routine nào đang tạo `receivable_detail` (ETL bên thứ ba
   hay `sync_daemon.py`) trước khi sửa.

3. `inventory`/`kpi_summary` nhỏ (≤211 dòng) → không cần index.

## Còn lại để đóng Phase 0
- [ ] **Đăng review & duyệt** bảng mapping này (cổng con người, không tự làm được).
- [ ] (Tùy chọn) Thêm index `receivable_detail(period)` — cải thiện tốc độ dashboard/alert ngay.
