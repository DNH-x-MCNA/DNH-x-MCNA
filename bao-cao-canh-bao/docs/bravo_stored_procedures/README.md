# Stored procedure gốc Bravo (công nợ, tồn kho)

Thư mục này lưu **toàn văn stored procedure gốc** trên Bravo mà DNH cung cấp — khác với
`docs/bravo_view_definitions/` (chỉ chứa VIEW dùng cho doanh thu), các file ở đây là STORED
PROCEDURE tính toán nghiệp vụ phức tạp (công nợ, tồn kho theo lô) mà hệ thống MCNA dùng làm nguồn
xác nhận chính thức để thay thế các công thức "tạm thời/provisional" tự suy đoán trước đó.

## Các file

| File | SP gốc | Mục đích |
| --- | --- | --- |
| (xem `.claude/skills/dnh-debt-aging-schema/assets/debt_aging_schema.sql`) | `usp_DeptAccDueDate_GetData` | Công nợ/tuổi nợ khách hàng — cung cấp 22/07/2026, đã áp dụng (xem skill `dnh-debt-aging-schema`). |
| `usp_StockLotFinance_Report.sql` | `usp_StockLotFinance_Report` | Tồn kho theo lô (hạn dùng) + tốc độ bán/tồn "chết" — cung cấp 22/07/2026. |

## Điểm nghiệp vụ rút ra từ `usp_StockLotFinance_Report`

SP có 2 báo cáo chọn qua tham số `@_RepType`:

### `@_RepType = 0` — Tồn kho theo lô, phân loại hạn dùng còn lại

- **Nguồn hạn dùng**: `BRVSX_Lot.ExpiryDate` (kênh SX/ETC) và `BRV_Lot.ExpiryDate` (kênh TM/OTC) —
  join qua `ItemId + ItemLotCode`, KHÔNG nằm trực tiếp trên bảng tồn kho (`vTonKhoDKLot`/
  `vTheKhoLot`). **Đây là lý do khảo sát trước đó (10/07/2026, ghi trong
  `check_near_expiry_alert()` ở `src/alerts.py`) kết luận sai là Bravo "không có cột hạn dùng" —
  khảo sát chỉ tìm cột `Expir*`/`HanDung*` trên các bảng `%thekho%`/`%tonkho%`, bỏ sót bảng
  `BRV_Lot`/`BRVSX_Lot` riêng.** Khi triển khai near-expiry alert thật, phải đồng bộ 2 bảng này
  (chưa có ở đâu trong hệ thống — chưa vào `warehouse.db` lẫn Supabase).
- Bucket theo **tháng còn lại tới hạn** (tham số `@_ExpiryPeriod`, mặc định 3 tháng/kỳ):
  `CloseQuantity0` (đã hết hạn) / `1` (1 đến kỳ-1 tháng) / `2` (kỳ đến 2×kỳ-1) / `3` (2×kỳ đến
  3×kỳ-1) / `4` (3×kỳ đến 4×kỳ-1) / `5` (4×kỳ đến 6×kỳ-1) / `6` (≥6×kỳ tháng).
- Cột `Description` dùng **ngày** (khác đơn vị với bucket trên) qua 2 tham số riêng:
  `@_ExpiryDays=180` → "Hết date" nếu còn ≤180 ngày; `@_NearExpiryDays=540` → "Cận date" nếu
  181–539 ngày; còn lại để trống.
- 2 kênh xử lý riêng: `ClassCode='SX'` (ETC) dùng `BRVSX_Lot`, `ClassCode='TM'` (OTC) dùng
  `BRV_Lot` — luôn xử lý cả 2 nhánh khi tái tạo logic tương đương.

### `@_RepType = 1` — Tốc độ bán / tồn kho "chết"

```
RemainMonths = FLOOR(tồn kho hiện tại / TB số lượng bán mỗi ngày-có-bán trong 6 tháng gần nhất)
"Thiếu hàng"  nếu RemainMonths <= @_OutOfStockMonth   (mặc định 1 tháng)
"Bán chậm"    nếu RemainMonths >= @_ShortOfStockMonth (mặc định 6 tháng)
"Bình thường" ở giữa
"Không phát sinh DS" nếu không có doanh số 6 tháng gần nhất để so sánh
```

- Tốc độ bán trung bình dùng dữ liệu **6 tháng gần nhất** (`@_SaleVelocityNum`), tính theo
  `SUM(Quantity)/COUNT(DISTINCT ngày có bán)`, quy đổi đơn vị DMS qua `BRVSX_SanPhamDvt.ConvertRate`
  nếu đơn vị bán khác đơn vị DMS chuẩn.
- **Ngưỡng `dead_stock_months` trong `config/config.yaml` đã đổi từ 12.0 xuống 6.0 (22/07/2026)**
  để khớp đúng `@_ShortOfStockMonth` mặc định của SP này — xem `src/alerts.py::check_dead_stock_alert()`.
- Chỉ áp dụng cho sản phẩm `ItemGroupCode IN ('155','156') AND IsItemWithLot = 1` (nhóm hàng quản
  lý theo lô) — không phải toàn bộ danh mục sản phẩm.

## Việc chưa làm (khi triển khai near-expiry alert thật)

`check_near_expiry_alert()` (`src/alerts.py`) hiện vẫn là no-op có chủ đích (đợi dữ liệu). Để bật
thật cần: đồng bộ `BRV_Lot`/`BRVSX_Lot` (ItemLotCode, ItemId, MfgDate, ExpiryDate, IsActive) vào
`local_warehouse.py`/`sync_warehouse.py` (tương tự các bảng khác), viết lại logic tồn theo lô +
join hạn dùng theo đúng công thức SP này, và bật `alert_feature_flags.near_expiry_check: true`
trong `config.yaml`. Đây là thay đổi kiến trúc (thêm ETL mới), cần xác nhận riêng trước khi làm —
KHÔNG tự ý triển khai chỉ vì đã có tài liệu tham chiếu.

*Nguồn: người dùng cung cấp toàn văn SP qua chat 22/07/2026.*
