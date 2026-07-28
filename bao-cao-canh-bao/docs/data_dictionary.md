# Từ Điển Dữ Liệu Data Warehouse (DWH Data Dictionary) - Dược Nam Hà

Tài liệu này mô tả chi tiết tên cột, kiểu dữ liệu, các ràng buộc và ý nghĩa nghiệp vụ của toàn bộ các bảng dữ liệu trong schema `dnh_core` trên SQL Server DWH.

> **20/07/2026:** Mục 8 bên dưới ("Lớp 4 — Dữ liệu cấp cá nhân") mô tả **đúng nguồn Bravo thật**
> (không phải schema `dnh_core` kế hoạch ở các mục 1-7 — mục đó là thiết kế DWH ban đầu, hiện hệ
> thống đang đọc THẲNG Bravo (`dbo.*`)/Supabase bảng phẳng (không có schema `dnh_core`), chưa khớp
> hoàn toàn với tài liệu cũ). Xây dựng theo thứ tự **từ dưới lên** (cá nhân → quản lý → tổng quát,
> xem [[feedback_data_correctness_bottom_up]]) — Lớp 4 (cấp cá nhân) làm trước, đã kiểm chứng với
> dữ liệu Bravo thật ngày 20/07/2026.

---

## 1. Bảng: `dnh_core.regions` (Danh mục Vùng miền)
Lưu trữ danh sách các vùng miền kinh doanh của Dược Nam Hà.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `region_id` | `VARCHAR(10)` | PRIMARY KEY | Mã vùng miền (ví dụ: 'MN', 'MB', 'MB2', 'MT') |
| `region_name` | `NVARCHAR(100)` | NOT NULL | Tên vùng miền tiếng Việt (ví dụ: 'Miền Nam', 'Miền Bắc') |

---

## 2. Bảng: `dnh_core.employees` (Nhân sự kinh doanh & Quản lý)
Lưu trữ thông tin chi tiết của Trình dược viên và Quản lý vùng.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `employee_id` | `VARCHAR(20)` | PRIMARY KEY | Mã số nhân viên (ví dụ: 'HCM04', 'TM23100123') |
| `full_name` | `NVARCHAR(150)` | NOT NULL | Họ và tên đầy đủ |
| `position_name`| `NVARCHAR(100)` | NULL | Chức vụ (Trình dược viên, Quản lý vùng, v.v.) |
| `region_id` | `VARCHAR(10)` | FOREIGN KEY | Mã vùng miền nhân viên trực thuộc (link `regions`) |
| `email` | `VARCHAR(100)` | NULL | Email liên hệ công việc |
| `phone` | `VARCHAR(20)` | NULL | Số điện thoại di động |

---

## 3. Bảng: `dnh_core.customers` (Danh mục Khách hàng)
Lưu trữ thông tin khách hàng từ hệ thống ERP/DMS.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `customer_id` | `VARCHAR(20)` | PRIMARY KEY | Mã số khách hàng |
| `customer_name`| `NVARCHAR(250)` | NOT NULL | Tên nhà thuốc, hộ kinh doanh, hoặc bệnh viện |
| `segment` | `VARCHAR(20)` | NOT NULL | Phân khúc khách hàng: 'OTC' (Bán lẻ) hoặc 'ETC' (Bệnh viện) |
| `region_id` | `VARCHAR(10)` | FOREIGN KEY | Mã vùng địa lý của khách hàng |
| `daily_debt_limit`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Hạn mức dư nợ cho phép tối đa trong ngày (VND) |
| `allowed_debt_days`| `INT` | DEFAULT 30 | Số ngày nợ tối đa cho phép kể từ khi xuất hóa đơn |

---

## 4. Bảng: `dnh_core.receivable_detail` (Công nợ chi tiết OTC & Sản xuất)
Bảng giao dịch và theo dõi số dư công nợ kèm tuổi nợ quá hạn.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | PRIMARY KEY (IDENTITY) | ID tự tăng |
| `period` | `VARCHAR(20)` | NOT NULL | Kỳ báo cáo công nợ (ví dụ: '1_2026') |
| `customer_code`| `VARCHAR(20)` | FOREIGN KEY | Liên kết mã khách hàng (`customers`) |
| `balance_end` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Tổng số dư nợ phải thu cuối kỳ |
| `in_term` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Số nợ trong hạn thanh toán |
| `overdue_1_15` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Số nợ quá hạn từ 1 đến 15 ngày |
| `overdue_15_30`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Số nợ quá hạn từ 15 đến 30 ngày |
| `overdue_30_45`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Số nợ quá hạn từ 30 đến 45 ngày |
| `overdue_gt_45`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Số nợ quá hạn trên 45 ngày |
| `total_overdue`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Tổng số nợ quá hạn (`overdue_1_15` + ... + `overdue_gt_45`) |
| `sales_channel`| `VARCHAR(50)` | NULL | Kênh bán hàng (ví dụ: 'OTC', 'SX') |
| `sync_date` | `DATETIME` | DEFAULT GETDATE() | Thời gian đồng bộ dữ liệu vào DWH |

---

## 5. Bảng: `dnh_core.receivable_etc` (Công nợ thầu bệnh viện ETC)
Lưu trữ tình hình giải ngân thầu và công nợ của kênh bệnh viện/phòng khám.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | PRIMARY KEY (IDENTITY) | ID tự tăng |
| `customer_code`| `VARCHAR(20)` | FOREIGN KEY | Mã bệnh viện/nhà thầu |
| `contract_value`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Tổng giá trị gói thầu/hợp đồng gốc |
| `total_paid` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Lũy kế số tiền bệnh viện đã thanh toán |
| `in_term` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Nợ thầu trong hạn |
| `overdue_1_7` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Nợ thầu quá hạn 1-7 ngày |
| `overdue_8_14` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Nợ thầu quá hạn 8-14 ngày |
| `overdue_15_21`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Nợ thầu quá hạn 15-21 ngày |
| `overdue_gt_21`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Nợ thầu quá hạn trên 21 ngày |
| `total_overdue`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Tổng nợ thầu quá hạn |
| `total_receivable`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Tổng số nợ thầu còn lại phải thu |
| `province_code`| `VARCHAR(10)` | NULL | Mã tỉnh thành nơi diễn ra thầu |
| `sales_manager`| `NVARCHAR(100)`| NULL | Giám đốc kinh doanh vùng chịu trách nhiệm thầu |
| `sync_date` | `DATETIME` | DEFAULT GETDATE() | Thời gian đồng bộ dữ liệu |

---

## 6. Bảng: `dnh_core.inventory` (Tồn kho thành phẩm)
Lưu trữ số liệu tồn kho thành phẩm của Nam Hà và dự phóng bán hàng.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `item_code` | `VARCHAR(30)` | PRIMARY KEY | Mã số hàng hóa/sản phẩm (ví dụ: '31190000680') |
| `item_name` | `NVARCHAR(250)`| NOT NULL | Tên sản phẩm đầy đủ (ví dụ: 'Siro thuốc ho bổ phế Nam Hà') |
| `unit` | `NVARCHAR(50)` | NULL | Đơn vị tính gốc |
| `closing_qty` | `DECIMAL(18, 2)`| DEFAULT 0.0 | Số lượng tồn kho thực tế cuối kỳ |
| `closing_value`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Tổng giá trị tồn kho quy đổi thành tiền (VND) |
| `months_to_sell`| `DECIMAL(5, 2)` | DEFAULT 0.0 | Số tháng dự kiến bán hết hàng tồn kho hiện tại |
| `sync_date` | `DATETIME` | DEFAULT GETDATE() | Thời gian đồng bộ dữ liệu |

---

## 7. Bảng: `dnh_core.kpi_summary` (Tổng hợp KPI doanh số)
Bảng tổng hợp kết quả hoàn thành chỉ tiêu doanh số theo nhân viên.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | PRIMARY KEY (IDENTITY) | ID tự tăng |
| `area_code` | `VARCHAR(10)` | FOREIGN KEY | Mã vùng miền hoạt động |
| `employee_code`| `VARCHAR(20)` | FOREIGN KEY | Mã nhân viên kinh doanh phụ trách |
| `month_sale_target`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Chỉ tiêu doanh số tháng (VND) |
| `month_sale_amount`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Doanh số thực đạt trong tháng (VND) |
| `month_sale_percent`| `DECIMAL(7, 4)` | DEFAULT 0.0 | Tỷ lệ hoàn thành chỉ tiêu tháng (1.0 = 100%) |
| `total_point` | `DECIMAL(5, 2)` | DEFAULT 0.0 | Điểm KPI tổng kết đánh giá năng lực |
| `quarter_sale_target`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Chỉ tiêu doanh số quý (VND) |
| `quarter_sale_amount`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Doanh số thực đạt trong quý (VND) |
| `quarter_sale_percent`| `DECIMAL(7, 4)` | DEFAULT 0.0 | Tỷ lệ hoàn thành chỉ tiêu quý |
| `year_sale_target`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Chỉ tiêu doanh số năm (VND) |
| `year_sale_amount`| `DECIMAL(18, 2)`| DEFAULT 0.0 | Doanh số thực đạt trong năm (VND) |
| `year_sale_percent`| `DECIMAL(7, 4)` | DEFAULT 0.0 | Tỷ lệ hoàn thành chỉ tiêu năm |
| `sync_date` | `DATETIME` | DEFAULT GETDATE() | Thời gian đồng bộ dữ liệu |

---

## 8. Lớp 4 — Dữ liệu cấp cá nhân (TDV) — nguồn Bravo thật, đã kiểm chứng 20/07/2026

Không đọc qua bảng `dnh_core.*` ở trên — hệ thống thật đọc **trực tiếp** các bảng/view sau trên
Bravo (SQL Server, schema `dbo`), qua các hàm `get_bravo_*_snapshot()` trong `src/alerts.py`.

### 8.1. Bảng `dbo.FACT_TongHopKhachHang` (KPI cá nhân TDV/QLV)

| Tên Cột | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- |
| `SaveDate` | Ngày snapshot — luôn dùng `MAX(SaveDate)` làm kỳ mới nhất, KHÔNG hardcode tháng |
| `EmployeeCode` | Mã nhân viên — **mã CHUẨN**, khớp `DIM_NhanVien.EmployeeCode` (không phải bí danh DMSCode, xem 8.3) |
| `CustomerCode` | Mã khách hàng gắn với dòng doanh số này |
| `AreaCode` | Vùng miền hoạt động của nhân viên |
| `MonthSaleTarget` | Chỉ tiêu doanh số THÁNG (số THÁNG, không cộng dồn — dao động lên xuống qua các tháng) |
| `Amount_Cus` | Doanh số thực đạt của nhân viên với khách hàng này, trong tháng của `SaveDate` |
| `YearSaleTarget` | Chỉ tiêu năm — **ĐÃ cộng dồn theo năm** (khác `MonthSaleTarget`), không cộng dồn thêm lần nữa |

**Công thức KPI cá nhân** (`get_bravo_kpi_tdv_snapshot`, `src/alerts.py:564`):
`month_sale_amount = SUM(Amount_Cus)` theo `EmployeeCode` tại `SaveDate` mới nhất;
`month_sale_percent = month_sale_amount / month_sale_target` (`None` nếu target ≤ 0, không chia
cho 0). JOIN với `DIM_NhanVien` để lấy tên/chức danh, loại `IsDuplicate=1`.

**Verify 20/07/2026**: cộng tay 16 dòng của 1 TDV mẫu (`DNH00634`) khớp 100% với hàm; không có
`EmployeeCode` nào bị trùng trong 148 TDV; toàn bộ 182 mã trong snapshot đều JOIN được với
`DIM_NhanVien` (0 mã bị loại oan bởi INNER JOIN).

### 8.2. Bảng `dbo.DIM_NhanVien` (Danh mục nhân viên — mã chuẩn)

| Tên Cột | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- |
| `EmployeeCode` | Mã nhân viên chuẩn (dùng làm khóa nối với `FACT_TongHopKhachHang`) |
| `DMSId` | Mã nhân viên **theo định dạng ghi trên hóa đơn** (`BRV_HoaDonHdr.EmpDMSCode`) — KHÁC `EmployeeCode`, dùng để nối hóa đơn thô OTC với nhân viên |
| `PositionCode` | Chức danh: `TDV`, `QLV`, `TP`, `PP`, `TBP`, `CS`, `CTV`, `TK`... |
| `IsDuplicate` | Cờ đánh dấu bản ghi trùng — LUÔN lọc `IsDuplicate IS NULL OR IsDuplicate = 0` |

**LƯU Ý QUAN TRỌNG (phát hiện 20/07/2026)**: `DIM_NhanVien` **không phải danh mục nhân viên đầy
đủ** — chỉ phủ nhân viên phía OTC. Nhân viên ETC (và một phần OTC) chỉ có trong `DMSSX_NhanVien`
(mục 8.3). JOIN chỉ với `DIM_NhanVien` mà không kèm `DMSSX_NhanVien` sẽ hiểu lầm hàng loạt nhân
viên thật thành "không tồn tại" — xác nhận thực tế: JOIN trực tiếp `vHoaDonTotal`/`vHoaDonETCTotal`
với `DIM_NhanVien.EmployeeCode` cho tháng 7/2026 cho ra **107 mã OTC + 27 mã ETC "không tồn tại"**
(~36,3 tỷ đồng doanh thu), nhưng sau khi UNION thêm `DMSSX_NhanVien` thì ETC còn lại **0 mã**, OTC
còn lại **6 mã/484 triệu đồng** (nhóm này mới thật sự đáng nghi — nhân viên nghỉ việc/mã chưa đồng
bộ, cần DNH xác nhận).

### 8.3. Bảng `dbo.DMSSX_NhanVien` (Danh mục nhân viên — mã DMS/hóa đơn, có bí danh)

| Tên Cột | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- |
| `Code` | Mã nhân viên — thường trùng `DIM_NhanVien.EmployeeCode` của cùng người |
| `DMSCode` | **Bí danh khác** của CÙNG nhân viên, dùng trên hóa đơn/DMS — vd nhân viên `Code='DNH00634'` có `DMSCode='DNH01010'`, 2 mã trỏ về CÙNG 1 người |
| `Name` | Tên nhân viên |

**Cách dùng đúng**: khi tra cứu 1 mã nhân viên xuất hiện trên hóa đơn (`EmpDMSCode`) mà không thấy
trong `DIM_NhanVien.EmployeeCode`, PHẢI thử tiếp `DMSSX_NhanVien.Code`/`DMSSX_NhanVien.DMSCode`
trước khi kết luận "nhân viên không tồn tại". `scripts/build_ods_sales_transactions.py` đã làm
đúng pattern này (gộp cả 2 bảng vào 1 map trước khi dùng); `get_bravo_kpi_tdv_snapshot`/
`get_bravo_inventory_snapshot` không cần vì nguồn của chúng (`FACT_TongHopKhachHang`, hóa đơn qua
`DIM_NhanVien.DMSId`) đã dùng đúng mã chuẩn/mã hóa đơn tương ứng ngay từ đầu.

### 8.4. Bảng `dbo.DMS_KhachHang` (Khách hàng OTC — người phụ trách)

| Tên Cột | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- |
| `Code` | Mã khách hàng |
| `EmpDMSCode1` | Mã nhân viên phụ trách khách hàng này (có thể là `EmployeeCode` HOẶC bí danh `DMSCode`, xem 8.3) |
| `CityId` | Liên kết tỉnh/thành (`DIM_TinhThanhPho`) — dùng suy luận vùng miền |

**LƯU Ý**: `DMSSX_KhachHang` (khách hàng ETC) **không có cột tương đương** — phía ETC không có
danh sách "khách hàng phụ trách" cố định ở cấp customer-master, chỉ suy ra được từ hóa đơn gần đây.

**Verify 20/07/2026** (47.588 khách hàng OTC): 6.677 khách (14%) chưa có `EmpDMSCode1`, nhưng lọc
theo khách THẬT SỰ hoạt động (có hóa đơn 90 ngày gần nhất) thì chỉ còn **70 khách** chưa gán người
phụ trách (~540 triệu đồng doanh thu 90 ngày) — không phải vấn đề lớn. Trong số khách CÓ gán:
100% khớp với 1 nhân viên thật (qua `DIM_NhanVien` hoặc `DMSSX_NhanVien`), 0 mã rác.

### 8.5. Công nợ quá hạn theo TDV (rollup, không phải bảng riêng)

Không có bảng "công nợ theo nhân viên" trực tiếp — tính bằng cách JOIN kết quả
`get_bravo_receivables_snapshot()` (đã verify khớp 100% với SP gốc DNH `usp_DeptAccDueDate_GetData`,
xem [[receivables_uses_dnh_sp]]) với `DMS_KhachHang.EmpDMSCode1` theo `customer_code`. Verify
20/07/2026: chỉ 3/2.245 khách OTC có nợ quá hạn mà chưa gán người phụ trách (1,77 triệu đồng —
không đáng kể).

### 8.6. Domain CHƯA triển khai thành tính năng — cần DNH xác nhận định nghĩa trước

Đã thử nghiệm (ad-hoc, KHÔNG phải alert/tính năng chính thức — tránh vi phạm chỉ đạo "dừng thêm
tính năng mới" từ họp 16/07):
- **Khách hàng mở mới theo TDV**: định nghĩa thử = hóa đơn đầu tiên trong lịch sử rơi vào tháng
  hiện tại (`MIN(DocDate)` theo `CustomerCode`). Ra số hợp lý (144 khách mới/79 TDV, tháng 7 OTC)
  nhưng ĐÂY LÀ ĐỊNH NGHĨA TỰ CHỌN — DNH có thể định nghĩa khác cho mục đích thưởng/KPI.
- **Ngưỡng churn/im lặng theo TDV**: định nghĩa thử = khách có mua trong 12 tháng gần đây nhưng
  im lặng >60 ngày. Ra 47,9% trung bình toàn công ty — CON SỐ NÀY RẤT NHẠY VỚI NGƯỠNG (mẫu số
  sai 1 lần đã cho ra 78,6%), giống hệt tranh cãi ngưỡng quá hạn 30/45/60 ngày DNH từng nêu —
  KHÔNG dùng số này làm căn cứ cho tới khi DNH xác nhận ngưỡng/chu kỳ mua hàng bình thường của
  ngành dược.
