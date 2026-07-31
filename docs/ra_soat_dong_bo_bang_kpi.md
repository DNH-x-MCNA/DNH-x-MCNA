# Rà soát đồng bộ bảng KPI — 20/27 cột chưa được kéo về

Phát hiện ngày 31/07/2026 khi chạy thử bộ câu hỏi KPI. Toàn bộ số liệu dưới đây truy trực tiếp Bravo,
không suy đoán.

---

## Tóm tắt

| | |
|---|---|
| Bảng nguồn | `dbo.FACT_TongHopKhachHang` trên Bravo — **27 cột** |
| Đang đồng bộ | **7 cột** |
| Chưa đồng bộ | **20 cột**, tất cả đều **có dữ liệu 100%**, không cột nào rỗng |
| Nơi cấu hình | [`backend/sync_warehouse.py`](../../DNH-x-MCNA/backend/sync_warehouse.py) `::sync_fact_tonghopkhachhang` |
| Bảng đích | [`backend/local_warehouse.py`](../../DNH-x-MCNA/backend/local_warehouse.py) `::fact_tonghopkhachhang` |

```sql
-- Đang kéo về (dòng 286 sync_warehouse.py)
SELECT EmployeeCode, CustomerCode, Amount_CT, MonthSaleTarget, SaveDate, IsNC, ManagerCode
FROM dbo.FACT_TongHopKhachHang WHERE SaveDate >= :a
```

---

## Hậu quả đã quan sát được

Chạy thử 12 câu hỏi KPI trên chatbot, **2 câu trả lời sai hoặc không trả lời được** vì thiếu cột:

| Câu hỏi | Chatbot trả lời | Vấn đề |
|---|---|---|
| *"Bao nhiêu khách mua lại tháng 7?"* | **6.002** | Cột `IsRO` không có trong kho → chatbot **suy diễn** "không phải khách mới". Số thật: **5.373** |
| *"Bao nhiêu nhân viên đủ điều kiện thưởng ASO?"* | *"Hệ thống chưa có dữ liệu"* | Đúng với kho, nhưng **Bravo CÓ sẵn** `IsASO` và `IsCalASOBonus` phủ 100% |

Chatbot từ chối trả lời ASO là hành vi **đúng và trung thực** — vấn đề nằm ở chỗ dữ liệu có mà không kéo về.

---

## 20 cột chưa đồng bộ, xếp theo mức ưu tiên

### 🔴 Ưu tiên cao — mở khoá tính năng đang thiếu

| Cột | Kiểu | Ý nghĩa | Mở khoá được gì |
|---|---|---|---|
| `YearSaleTarget` | numeric(18,2) | Chỉ tiêu **năm**, đã cộng dồn sẵn | Câu hỏi lũy kế năm, tiến độ so kế hoạch năm. Hiện hoàn toàn không trả lời được |
| `IsRO` | tinyint | Cờ khách **mua lại** | Thay phép suy diễn hiện tại bằng số thật |
| `IsAC` | tinyint | Cờ khách **hoạt động** | Chưa có gì thay thế |
| `IsASO` + `IsCalASOBonus` | tinyint | Diện tính thưởng ASO | Trả lời được câu thưởng ASO thay vì từ chối |
| `AreaCode` | varchar(24) | Vùng miền **ngay trên dòng KPI** | **Đã chứng minh 31/07:** cột này phủ MB 102 / MN 49 / MT 35 = **186 mã, không một mã rỗng**. Trong khi chatbot join qua `dim_nhanvien.area_code` thì **rơi mất 13 mã ôm 9,37 tỷ** rồi báo động giả là "lỗi dữ liệu". Kéo về là xoá sạch cả lớp lỗi này |
| `NCMonth` · `ROMonth` | numeric(16,5) | Số khách mới / mua lại **thực tế** trong tháng | Hiện đang đếm `SUM(is_nc)` theo dòng — **rủi ro cộng chồng 2 tầng** |

### 🟠 Ưu tiên trung bình — bổ sung chiều phân tích

| Cột | Ý nghĩa | Ghi chú |
|---|---|---|
| `NewCusTarget` · `ReOrderCusTarget` · `ActiveCusTarget` | Chỉ tiêu **số lượng khách** | Có 17 / 4 / 4 giá trị khác nhau. Giá trị lẻ (0,7) → là **trọng số**, không phải đếm đầu khách. Cần DNH xác nhận cách dùng |
| `MaxCustomerOrdAmount` | Đơn hàng lớn nhất của khách | 3.035 giá trị khác nhau — dữ liệu phong phú |
| `EmpDMSCode` | Mã nhân viên **theo định dạng hoá đơn** | Nối KPI ↔ hoá đơn thô mà không cần qua `DIM_NhanVien` |

### ⚪ Ưu tiên thấp — chưa thấy nhu cầu

`Id` · `CreatedAt` · `AreaCode2` · `ROLastDate` · `ReOrderStartDate` · `NewCusStartDate`

### ⚠️ Trường hợp riêng: `Amount_Cus`

Kỳ 30/07 **trùng khít** `Amount_CT` (13.088/13.088 dòng bằng nhau). Nhưng các kỳ cũ **có lệch**:

| Kỳ | Số dòng lệch |
|---|---|
| 2025-08-31 | **46** |
| 2025-06-01 · 2025-05-01 | **41** mỗi kỳ |
| 2025-07-31 | 10 |
| 2025-10-31 | 8 |
| 2025-04-01 | 6 |
| 2025-09-30 | 4 |

Kho chỉ có `Amount_CT`. **Chưa rõ hai cột khác nhau ở điểm nào về nghiệp vụ** — cần hỏi DNH trước khi
quyết định dùng cột nào làm chuẩn, hoặc kéo cả hai về để đối chiếu.

---

## Vấn đề thứ hai: kho đang giữ snapshot mà Bravo đã xoá

Chạy **đúng logic của chatbot** (gộp theo tháng, mỗi nhân viên lấy `SaveDate` mới nhất của chính họ,
loại `IsDuplicate`, `MonthSaleTarget > 0`) trên hai nguồn:

| Nguồn | Số nhân viên |
|---|---|
| Bravo (sống, truy 31/07) | **172** |
| Chatbot (đọc kho cục bộ) | **174** |

Nguyên nhân: tháng 7 trên Bravo **chỉ còn duy nhất một kỳ**. Các snapshot lẻ 27/07 (MB+MN) và
28/07 (MT) — từng gây lỗi "KPI chỉ có 1 miền" — **đã bị DNH xoá và chốt lại**. Kho cục bộ nhiều khả năng
vẫn còn 2 kỳ cũ đó, nên gộp theo tháng nhặt thêm 2 nhân viên chỉ tồn tại ở snapshot cũ.

> 🔄 **Cập nhật trưa 31/07:** Bravo vừa chốt lại lần nữa — kỳ `2026-07-30` **đã biến mất**, thay bằng
> `2026-07-31` (13.148 dòng, 186 mã NV). Nghĩa là DNH **chốt lại snapshot nhiều lần trong tháng**,
> không phải chuyện xảy ra một lần. Kho cục bộ vì thế sẽ **liên tục giữ kỳ đã bị xoá** cho tới lần
> đồng bộ kế tiếp — đây là vấn đề định kỳ, không phải sự cố đơn lẻ.

> Đây **không phải lỗi của bản vá gộp-theo-tháng** — bản vá vẫn đúng và vẫn cần. Vấn đề là kho chưa
> phản ánh việc Bravo xoá dữ liệu.

**Kiểm chứng trên máy 24:**

```powershell
cd C:\dnh_chatbot\backend
python -c "import sqlite3; c=sqlite3.connect('warehouse.db'); [print(r) for r in c.execute(\"SELECT save_date, COUNT(*), COUNT(DISTINCT employee_code) FROM fact_tonghopkhachhang WHERE save_date LIKE '2026-07%' GROUP BY save_date ORDER BY save_date\")]"
```

- Ra **1 dòng** `2026-07-30` → kho đã sạch, chênh lệch 174/172 do nguyên nhân khác, cần truy tiếp.
- Ra **nhiều dòng** (có 27/07, 28/07) → đúng như phán đoán, cần đồng bộ lại.

`sync_fact_tonghopkhachhang` đã `DELETE FROM fact_tonghopkhachhang` toàn bộ trước khi nạp lại, nên
**chỉ cần chạy lại đồng bộ là tự sạch** — không cần can thiệp tay.

---

## 🔄 Cập nhật 31/07 — Triều đã làm trước một phần, và lộ ra bẫy nặng hơn

Commit `ce6aeea` (30/07) của Triều thêm bảng **`fact_thongketinhluong`** đồng bộ từ
`FACT_ThongKeTinhLuong` với **52 cột**. Bảng này đã có sẵn phần lớn thứ tôi định kéo về:

| Tôi định thêm | Triều đã có | Kết luận |
|---|---|---|
| `AreaCode` | `AreaCode` + `AreaCode2` | ✅ Xong |
| `IsASO`, `IsCalASOBonus` | `ASOQuantity`, `ASOPercent_R`, `ASOBonus` | ✅ Tốt hơn — số thật thay vì cờ |
| `NCMonth`, `ROMonth` | `NewCustomerQuantity`, `ROCustomerQuantity` | ✅ Xong |
| 3 cột chỉ tiêu khách | `NewCusTarget`, `ReOrderCusTarget`, `ActiveCusTarget` | ✅ Xong |
| **`YearSaleTarget`** | *(không có)* | ❌ **Vẫn thiếu** |
| `IsRO`, `IsAC` theo từng khách | *(chỉ có số lượng gộp)* | ❌ Vẫn thiếu |
| `Amount_Cus`, `MaxCustomerOrdAmount`, `EmpDMSCode` | *(không có)* | ❌ Vẫn thiếu |

Nên phần việc còn lại **thu hẹp đáng kể**: chỉ còn `YearSaleTarget`, `Amount_Cus`, `IsRO`/`IsAC`,
`MaxCustomerOrdAmount`, `EmpDMSCode`.

### 🔴 Nhưng bảng mới có BA tầng, không phải hai

Kỳ 31/07/2026, 206 mã. Cộng theo từng cấp:

| Tầng | Số mã | `MonthSaleAmount` |
|---|---:|---:|
| TP (trưởng phòng / GĐ miền) | 3 | **33.307.889.644** |
| QLV | 21 | **33.307.889.644** |
| TDV + CS + TK + CTV (lá) | ~180 | **33.307.889.644** |
| PP (lớp phủ thêm, chỉ MN) | 2 | 5.198.362.685 |
| **Cộng cả bảng** | 206 | **105.122.031.617** |

Ba tầng đều **đúng bằng doanh thu OTC thật**. Cộng cả bảng ra `3 × 33.307.889.644 + 5.198.362.685`
= **105.122.031.617** — khớp tuyệt đối, tức **sai gấp hơn 3 lần**.

> Điều này ứng nghiệm đúng lời cảnh báo Triều tự viết trong `kpi_ranking`:
> *"Nếu sau này Bravo thêm cấp trên (vd TP quản lý QLV), cộng cả 2 cấp sẽ GẤP ĐÔI âm thầm."*
> Bảng lương mới **chính là chỗ có TP**.

Thêm một điểm: mẹo "mã nào không xuất hiện làm `ManagerCode`" — dùng đúng cho
`fact_tonghopkhachhang` (2 tầng) — **sai trên bảng này**, vì QLV vừa quản lý người khác vừa bị TP
quản lý. Áp mẹo đó ra **71.814.141.973**, sai gấp 2,16 lần.

### Hiện tại chưa nguy hiểm, nhưng là mìn cài sẵn

Tool `salary_detail` của Triều **an toàn**: trả đúng một dòng cho một người (`LIMIT 1`), phân quyền
chặt, không cộng gộp gì. Và bảng này **chưa được khai trong `schema_context.py`** nên AI không thể
tự viết SQL chạm vào.

Rủi ro nằm ở tương lai: **ngay khi ai đó khai bảng này vào `schema_context.py`** để mở thêm câu hỏi,
cái bẫy 3 tầng mở ra — và nó nặng hơn bẫy 2 tầng đã gây 4 câu trả lời sai hôm nay. Phải viết cảnh
báo cùng lúc, không được khai bảng trước rồi cảnh báo sau.

---

## ✅ Đã làm 31/07 — kéo về 6 cột, và một phát hiện bất ngờ

Đã mở rộng `sync_fact_tonghopkhachhang` từ 7 lên **13 cột**, thêm: `YearSaleTarget`, `Amount_Cus`,
`IsRO`, `IsAC`, `MaxCustomerOrdAmount`, `EmpDMSCode`. Kho cũ tự nâng cấp qua `_COLUMN_MIGRATIONS`
(`ALTER TABLE`), đã kiểm: giữ nguyên dữ liệu, không phải dựng lại.

**`AreaCode` cố ý KHÔNG kéo** dù nó phủ đủ 186/186 mã — vì bảng `fact_thongketinhluong` của Triều đã
có sẵn cột đó. Kéo về hai nơi là tạo ra hai nguồn vùng miền có thể lệch nhau mà không biết tin bên nào.

### 🔴 Ba cờ khách hàng hành xử KHÁC NHAU giữa hai tầng

Đo trên Bravo kỳ 31/07/2026:

| Tầng | `IsNC` | `IsRO` | `IsAC` |
|---|---:|---:|---:|
| Quản lý | 577 | **0** | **0** |
| Nhân viên | 601 | 5.594 | 45 |

Hai kiểu sai ngược chiều nhau:

- **`IsNC` có ở cả hai tầng** → cộng cả bảng ra 1.178, gấp đôi số thật.
- **`IsRO` và `IsAC` chỉ có ở tầng nhân viên** → lọc nhầm sang tầng quản lý ra **0**, và số 0 này
  trông rất giống một câu trả lời hợp lệ nên khó phát hiện.

Đã ghi cảnh báo vào `schema_context.py` kèm số đo thật.

---

## Đề xuất thay đổi *(phần còn lại sau khi trừ việc Triều đã làm)*

### Bước 1 — Mở rộng câu truy vấn đồng bộ

`sync_warehouse.py::sync_fact_tonghopkhachhang`, thêm 12 cột ưu tiên cao + trung bình:

```sql
SELECT EmployeeCode, EmpDMSCode, CustomerCode, ManagerCode, AreaCode,
       Amount_CT, Amount_Cus, MonthSaleTarget, YearSaleTarget, MaxCustomerOrdAmount,
       NewCusTarget, ReOrderCusTarget, ActiveCusTarget, NCMonth, ROMonth,
       IsNC, IsRO, IsAC, IsASO, IsCalASOBonus, SaveDate
FROM dbo.FACT_TongHopKhachHang WHERE SaveDate >= :a
```

### Bước 2 — Mở rộng schema kho

`local_warehouse.py`, bảng `fact_tonghopkhachhang`. Dùng đúng pattern `ALTER TABLE ... / except
OperationalError: pass` đã có sẵn trong `auth.py::init_schema` để không phá kho đang chạy.

### Bước 3 — Dạy chatbot biết các cột mới **và 2 quy tắc chống sai số**

`schema_context.py` — nếu không mô tả cột mới ở đây thì AI không biết là có, kéo về cũng vô ích.

Nhân dịp này phải ghi thêm 2 cảnh báo, cả hai đều đã gây ra câu trả lời sai thật
(xem [kiểm chứng 13 câu KPI](kiem_chung_13_cau_kpi_31-07.md)):

1. **Cộng cả bảng = sai đúng gấp 2.** Bảng chứa 2 tầng, tầng quản lý lặp lại y nguyên doanh số của
   tầng nhân viên. Đã kiểm kỳ 31/07: mỗi tầng đều bằng **33.307.889.644đ**, đúng bằng doanh thu OTC
   tháng 7 thật từ `vHoaDonTotal`. Muốn ra tổng thì **phải chọn một tầng**.
2. **`MonthSaleTarget` lặp trên mọi dòng khách** → `SUM` luôn sai. Cộng cả bảng ra **18.189 tỷ** trong
   khi chỉ tiêu OTC tháng 7 của công ty là **50,97 tỷ** — sai gấp 357 lần. Bắt buộc dùng
   `MAX(MonthSaleTarget)` sau `GROUP BY EmployeeCode`.

### Bước 4 — Chạy lại đồng bộ đầy đủ

Việc này đồng thời xử lý luôn vấn đề snapshot cũ ở mục trên.

### Chi phí

Kho chỉ giữ **90 ngày** ≈ 3 kỳ × 13.000 dòng ≈ **40.000 dòng**. Thêm 14 cột vào 40.000 dòng là không
đáng kể về dung lượng lẫn thời gian đồng bộ.

---

## Cần DNH xác nhận

| # | Câu hỏi | Vì sao cần |
|---|---|---|
| 1 | `Amount_CT` và `Amount_Cus` khác nhau thế nào về nghiệp vụ? | Kho đang dùng `Amount_CT`; các kỳ 2025 lệch tới 46 dòng, chưa rõ cột nào là chuẩn |
| 2 | `NewCusTarget`/`ReOrderCusTarget`/`ActiveCusTarget` là **trọng số** hay **số lượng khách**? | Giá trị lẻ (0,7) nên không thể là đếm đầu khách |
| 3 | Ngưỡng ASO (MB 40 / MT 35 / MN 25 khách) đối chiếu với cột nào? | Có `IsASO` và `IsCalASOBonus` nhưng chưa rõ cột nào quyết định |
| 4 | Vì sao snapshot 27–28/07 bị xoá và chốt lại ngày 30/07? | Để biết đây là quy trình bình thường hàng tháng hay xử lý một lần |
