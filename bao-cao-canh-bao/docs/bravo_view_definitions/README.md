# Định nghĩa view gốc Bravo (nguồn doanh thu chính thức)

Thư mục này lưu **DDL gốc** của các view Bravo mà công thức doanh thu của hệ thống phụ thuộc vào —
do DNH cung cấp, dùng làm tài liệu tham chiếu để hiểu vì sao `src/etl.py::_period_revenue()` query
thẳng vào các view này thay vì tự ráp lại từ bảng thô.

## Các file

| File | View | Nội dung |
| --- | --- | --- |
| `vHoaDon.sql` | `dbo.vHoaDon` | Chi tiết hóa đơn thường (nhóm chứng từ "H2"). Là cơ sở của `vHoaDonTotal`/`vHoaDonETCTotal`. |
| `vHoaDonHC.sql` | `dbo.vHoaDonHC` | Chứng từ điều chỉnh/HC (nhóm "HC") — đảo dấu `IIF(DocGroup=1,-1,1)` cho hàng trả lại/giảm trừ. Đọc từ `BRV_HoaDonHCCt`/`BRVSX_HoaDonHCCt`, **2 bảng CHƯA đồng bộ sang Supabase** (lý do `_period_revenue` bỏ hẳn failover Postgres). |

## 2 điểm nghiệp vụ quan trọng rút ra từ các view này

1. **Gộp mã khách hàng đôi (cố ý)** — DNH cố tình gộp một số cặp mã khách hàng thành 1 trong công
   thức doanh thu:
   ```sql
   WHEN CustomerCode IN ('HCM04272','HCM14237') THEN 'HCM04272'
   WHEN CustomerCode IN ('HCM04298','HCM14236') THEN 'HCM04298'
   WHEN CustomerCode IN ('HNO03986','HNO11477') THEN 'HNO03986'
   WHEN CustomerCode IN ('HCM14365','HCM14366') THEN 'HCM14365'
   -- CustomerCode = 'NDI10105' -> lấy theo TRIM(Description)
   ```
   Đây là quy ước THẬT của DNH, KHÔNG phải hóa đơn trùng lỗi — cần nhớ khi rà soát công nợ/doanh thu
   theo khách hàng (các mã "biến mất" sau khi gộp là bình thường).

2. **Chứng từ HC trừ vào doanh thu** — hàng trả lại/điều chỉnh (nhóm HC) làm GIẢM doanh thu qua đảo
   dấu số lượng/tiền. Vì 2 bảng nguồn HC chưa có trên Supabase nên chỉ tính đúng được khi query
   thẳng Bravo — đây là 1 trong các lý do hệ thống chuyển sang Bravo-first cho doanh thu.

*Nguồn: DNH cung cấp. Lưu vào repo 16/07/2026 (trước đó nằm dạng file scratch ở root, chuyển vào
docs/ làm tài liệu tham chiếu chính thức).*
