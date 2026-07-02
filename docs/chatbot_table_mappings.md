# Hướng Dẫn Ánh Xạ Bảng Dữ Liệu Thực Tế Cho Chatbot AI DNH

Tài liệu này chi tiết hóa cách chatbot ánh xạ các câu hỏi ngôn ngữ tự nhiên về doanh số, vùng miền, KPI và công nợ sang các bảng thực tế ( Bravo/DMS ) trên Supabase PostgreSQL DWH.

---

## 1. Doanh thu thực tế (Actual Sales/Revenue)
Chatbot **không sử dụng** bảng giả lập `orders` hay `invoices` nữa. Thay vào đó, doanh thu thực tế được tính từ các hóa đơn gốc:

*   **Doanh thu OTC (Nhà thuốc/Đại lý):**
    *   **Bảng:** `brv_hoadonhdr` (Header) và `brv_hoadonct` (Detail) liên kết qua trường `Stt`.
    *   **Trường số tiền:** `TotalAmount` trong `brv_hoadonhdr`.
*   **Doanh thu ETC (Bệnh viện/Thầu):**
    *   **Bảng:** `brvsx_hoadonhdr` (Header) và `brvsx_hoadonct` (Detail) liên kết qua trường `Stt`.
    *   **Trường số tiền:** `TotalAmount` trong `brvsx_hoadonhdr`.
*   **Hàng trả lại ETC (Returns):**
    *   **Bảng:** `brvsx_tralai`
    *   **Trường số tiền:** `TotalAmount0`.
*   **Doanh thu thuần ETC (Net ETC):** Bằng tổng doanh thu ETC trừ tổng tiền hàng trả lại.
*   **Điều kiện lọc hóa đơn hợp lệ (Valid Invoices Filter):** Loại bỏ hoàn toàn hóa đơn bị hủy ở cả trạng thái duyệt chứng từ và hóa đơn điện tử:
    ```sql
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE 
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
    ```

---

## 2. Vùng miền / Địa bàn (Regions/Territories)
Chatbot xác định vùng miền của hóa đơn bằng cách map khách hàng với tỉnh thành:
*   **Kênh OTC:** `brv_hoadonhdr` join `dms_khachhang` (qua `CustomerCode = Code`) join `dim_tinhthanhpho` (qua `CityId = CityId`).
*   **Kênh ETC:** `brvsx_hoadonhdr` join `dmssx_khachhang` (qua `CustomerCode = Code`) join `dim_tinhthanhpho` (qua `CityId = CityId`).
*   **Phân vùng:** Sử dụng cột `dim_tinhthanhpho.AreaCode` để quy đổi:
    *   `'MB'` $\rightarrow$ Miền Bắc.
    *   `'MT'` $\rightarrow$ Miền Trung.
    *   `'MN'` $\rightarrow$ Miền Nam.

---

## 3. Chỉ tiêu Doanh thu (Revenue Targets)
*   **Chỉ tiêu OTC vùng miền:** Truy vấn bảng `dim_targetvungmien` (cột `Amount`), nhóm theo `AreaCode`.
*   **Chỉ tiêu ETC toàn công ty:** Truy vấn bảng `fact_kehoachtongetc` (cột `Amount`).
*   **Chỉ tiêu của nhân viên:** Truy vấn bảng `fact_tonghopkhachhang` (cột `MonthSaleTarget`).
    *   *Lưu ý:* Do bảng này lưu chi tiết đến cấp khách hàng nên `MonthSaleTarget` bị lặp lại cho mỗi nhân viên/tháng. Chatbot dùng cú pháp `DISTINCT` trước khi cộng tổng:
        ```sql
        SELECT SUM(target) FROM (SELECT DISTINCT "EmployeeCode", "SaveDate", "MonthSaleTarget" as target FROM fact_tonghopkhachhang) t;
        ```

---

## 4. KPI & Hiệu suất Nhân viên (Employee KPI)
*   **Bảng chính:** `fact_tonghopkhachhang`
    *   **Doanh số thực tế:** `Amount_Cus`.
    *   **Chỉ tiêu tháng:** `MonthSaleTarget`.
*   **Bảng thông tin nhân viên:** `dim_nhanvien` (chứa `Name` và `PositionCode`).
    *   Liên kết qua `EmployeeCode = EmployeeCode` (hoặc `EmpDMSCode = DMSId`).
*   **Chức danh:** Lọc theo `dim_nhanvien.PositionCode` (ví dụ: `'TDV'` cho Trình dược viên, `'QLV'` cho Quản lý vùng).

---

## 5. Sản phẩm (Products)
*   **Bảng danh mục sản phẩm:** `brv_sanpham` (Code, Name).
*   **Liên kết chi tiết hóa đơn:** Join `brv_hoadonct` hoặc `brvsx_hoadonct` với `brv_sanpham` trên `ItemCode = Code`.
*   **Trường số lượng & số tiền:** `Quantity` và `Amount9` (ở cấp chi tiết).

---

## 6. Công nợ & Tồn kho (Receivables & Inventory)
*   **Công nợ phải thu:** Truy vấn bảng `receivable_detail` (không sử dụng `receivable_etc`).
    *   *Lưu ý:* Kỳ dữ liệu mới nhất được quy chuẩn là `'9_2025'` (dùng gạch dưới).
*   **Tồn kho thành phẩm:** Truy vấn bảng `inventory` (closing_qty, closing_value, months_to_sell).
