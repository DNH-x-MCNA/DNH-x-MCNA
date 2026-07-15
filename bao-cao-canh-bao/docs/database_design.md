# Thiết Kế Cơ Sở Dữ Liệu Data Warehouse (SQL Server DWH Design)

Tài liệu này định nghĩa cấu trúc cơ sở dữ liệu Data Warehouse (DWH) trung tâm của Dược Nam Hà. DWH được thiết kế chạy trên hệ quản trị cơ sở dữ liệu **Microsoft SQL Server**, lưu trữ dữ liệu lịch sử trên 2 năm từ hệ thống Bravo (ERP) và DMS (CRM).

---

## 1. Cấu Trúc Schemas & Phân Quyền
DWH được phân chia làm hai vùng dữ liệu (Schema) riêng biệt:
1. **`dnh_staging`**: Vùng đệm tạm thời chứa dữ liệu thô (raw data) trích xuất hàng ngày từ Bravo/DMS.
2. **`dnh_core`**: Vùng dữ liệu trung tâm đã làm sạch, chuẩn hóa, có lập chỉ mục (index) tối ưu để phục vụ Power BI, Metabase và AI Chatbot.

---

## 2. Danh Sách Các Bảng Core (dnh_core)

### 2.1 Bảng Vùng Miền (`dnh_core.regions`)
Lưu trữ thông tin 3 miền Bắc, Trung, Nam để gộp từ 3 khay của Bravo.
```sql
CREATE TABLE dnh_core.regions (
    region_id VARCHAR(10) PRIMARY KEY, -- 'BAC', 'TRUNG', 'NAM', 'MB2'
    region_name NVARCHAR(100) NOT NULL
);
```

### 2.2 Bảng Nhân Viên (`dnh_core.employees`)
Bảng nhân viên kinh doanh và quản lý.
```sql
CREATE TABLE dnh_core.employees (
    employee_id VARCHAR(20) PRIMARY KEY,
    full_name NVARCHAR(150) NOT NULL,
    position_name NVARCHAR(100),
    region_id VARCHAR(10) FOREIGN KEY REFERENCES dnh_core.regions(region_id),
    email VARCHAR(100),
    phone VARCHAR(20)
);
```

### 2.3 Bảng Đối Tượng Khách Hàng (`dnh_core.customers`)
Lưu trữ thông tin khách hàng, phân loại kênh OTC/ETC và hạn mức công nợ ngày cụ thể.
```sql
CREATE TABLE dnh_core.customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    customer_name NVARCHAR(250) NOT NULL,
    segment VARCHAR(20) NOT NULL, -- OTC hoặc ETC
    region_id VARCHAR(10) FOREIGN KEY REFERENCES dnh_core.regions(region_id),
    daily_debt_limit DECIMAL(18, 2) DEFAULT 0.0,
    allowed_debt_days INT DEFAULT 30
);
```

### 2.4 Bảng Công Nợ Chi Tiết OTC & SX (`dnh_core.receivable_detail`)
Lưu trữ công nợ phải thu chi tiết theo từng khách hàng và phân loại tuổi nợ quá hạn.
```sql
CREATE TABLE dnh_core.receivable_detail (
    id INT IDENTITY(1,1) PRIMARY KEY,
    period VARCHAR(20) NOT NULL,
    customer_code VARCHAR(20) FOREIGN KEY REFERENCES dnh_core.customers(customer_id),
    balance_end DECIMAL(18, 2) DEFAULT 0.0, -- Số dư phải thu cuối kỳ
    in_term DECIMAL(18, 2) DEFAULT 0.0,    -- Phải thu trong hạn
    overdue_1_15 DECIMAL(18, 2) DEFAULT 0.0, -- Quá hạn 1-15 ngày
    overdue_15_30 DECIMAL(18, 2) DEFAULT 0.0,
    overdue_30_45 DECIMAL(18, 2) DEFAULT 0.0,
    overdue_gt_45 DECIMAL(18, 2) DEFAULT 0.0,
    total_overdue DECIMAL(18, 2) DEFAULT 0.0, -- Tổng nợ quá hạn
    sales_channel VARCHAR(50),                -- Kênh bán hàng (OTC,...)
    sync_date DATETIME DEFAULT GETDATE()
);
```

### 2.5 Bảng Công Nợ & Thầu ETC Bệnh Viện (`dnh_core.receivable_etc`)
Theo dõi chi tiết giá trị hợp đồng thầu, số tiền đã thanh toán, dư nợ và nợ quá hạn của kênh ETC.
```sql
CREATE TABLE dnh_core.receivable_etc (
    id INT IDENTITY(1,1) PRIMARY KEY,
    customer_code VARCHAR(20) FOREIGN KEY REFERENCES dnh_core.customers(customer_id),
    contract_value DECIMAL(18, 2) DEFAULT 0.0, -- Giá trị hợp đồng thầu
    total_paid DECIMAL(18, 2) DEFAULT 0.0,     -- Tổng đã thanh toán
    in_term DECIMAL(18, 2) DEFAULT 0.0,        -- Phải thu trong hạn
    overdue_1_7 DECIMAL(18, 2) DEFAULT 0.0,
    overdue_8_14 DECIMAL(18, 2) DEFAULT 0.0,
    overdue_15_21 DECIMAL(18, 2) DEFAULT 0.0,
    overdue_gt_21 DECIMAL(18, 2) DEFAULT 0.0,
    total_overdue DECIMAL(18, 2) DEFAULT 0.0,  -- Tổng quá hạn
    total_receivable DECIMAL(18, 2) DEFAULT 0.0, -- Tổng phải thu còn lại
    province_code VARCHAR(10),
    sales_manager NVARCHAR(100),
    sync_date DATETIME DEFAULT GETDATE()
);
```

### 2.6 Bảng Tồn Kho Thành Phẩm (`dnh_core.inventory`)
Theo dõi tồn kho cuối kỳ của sản phẩm và cảnh báo rủi ro qua số tháng bán dự phòng.
```sql
CREATE TABLE dnh_core.inventory (
    item_code VARCHAR(30) PRIMARY KEY,
    item_name NVARCHAR(250) NOT NULL,
    unit NVARCHAR(50),
    closing_qty DECIMAL(18, 2) DEFAULT 0.0,   -- Tồn cuối kỳ (Số lượng)
    closing_value DECIMAL(18, 2) DEFAULT 0.0, -- Giá trị tồn kho (VND)
    months_to_sell DECIMAL(5, 2) DEFAULT 0.0,  -- Dự phòng số tháng bán hết
    sync_date DATETIME DEFAULT GETDATE()
);
```

### 2.7 Bảng Tổng Hợp KPI (`dnh_core.kpi_summary`)
Lưu trữ thông tin chỉ tiêu doanh số và tỉ lệ hoàn thành theo tháng/quý/năm của từng nhân sự kinh doanh.
```sql
CREATE TABLE dnh_core.kpi_summary (
    id INT IDENTITY(1,1) PRIMARY KEY,
    area_code VARCHAR(10) FOREIGN KEY REFERENCES dnh_core.regions(region_id),
    employee_code VARCHAR(20) FOREIGN KEY REFERENCES dnh_core.employees(employee_id),
    month_sale_target DECIMAL(18, 2) DEFAULT 0.0,
    month_sale_amount DECIMAL(18, 2) DEFAULT 0.0,
    month_sale_percent DECIMAL(7, 4) DEFAULT 0.0, -- % Hoàn thành tháng
    total_point DECIMAL(5, 2) DEFAULT 0.0,
    quarter_sale_target DECIMAL(18, 2) DEFAULT 0.0,
    quarter_sale_amount DECIMAL(18, 2) DEFAULT 0.0,
    quarter_sale_percent DECIMAL(7, 4) DEFAULT 0.0,
    year_sale_target DECIMAL(18, 2) DEFAULT 0.0,
    year_sale_amount DECIMAL(18, 2) DEFAULT 0.0,
    year_sale_percent DECIMAL(7, 4) DEFAULT 0.0,
    sync_date DATETIME DEFAULT GETDATE()
);
```

---

## 3. Quy Tắc Nghiệp Vụ Cốt Lõi (Core Business Logic)

### 3.1 Cảnh Báo Công Nợ Vượt Hạn Mức Ngày (Daily Debt Alert)
Job quét chạy hàng ngày vào lúc 7:00 sáng sẽ đối chiếu:
* **Nợ quá hạn (`total_overdue`)**: Nếu `total_overdue > 0` trong bảng `receivable_detail` (đối với OTC) hoặc `receivable_etc` (đối với ETC/Bệnh viện), hệ thống sẽ lập tức gắn cờ cảnh báo và gửi email thông báo chi tiết đến C-Level/Sales Manager.

### 3.2 Cảnh Báo Kho Dược Phẩm (Inventory Risk Alerts)
Bảng `inventory` theo dõi dự phóng số tháng bán hết (`months_to_sell`) của từng sản phẩm để phân loại rủi ro:
1. **Cận date / Hàng bán chậm**: `months_to_sell >= 6` (Lượng tồn quá lớn so với tốc độ bán, có rủi ro hết hạn sử dụng).
2. **Bình thường**: `1 < months_to_sell < 6`.
3. **Thiếu hàng / Đứt gãy chuỗi cung ứng**: `months_to_sell <= 1` (Lượng hàng còn lại chỉ đủ bán trong vòng 1 tháng trở xuống).
