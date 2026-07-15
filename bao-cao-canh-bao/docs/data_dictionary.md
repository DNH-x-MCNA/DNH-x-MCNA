# Từ Điển Dữ Liệu Data Warehouse (DWH Data Dictionary) - Dược Nam Hà

Tài liệu này mô tả chi tiết tên cột, kiểu dữ liệu, các ràng buộc và ý nghĩa nghiệp vụ của toàn bộ các bảng dữ liệu trong schema `dnh_core` trên SQL Server DWH.

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
