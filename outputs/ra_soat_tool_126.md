# Rà soát tầng tool cho bộ câu hỏi UAT

Chạy `scripts/ra_soat_tool_126_cau.py` — gọi đúng tool mà từng câu định tuyến vào, theo đúng vai trò/phạm vi của người hỏi. Không gọi model, không tốn API.

| Trạng thái | Số câu |
|---|---:|
| TOOL_BAO_LOI | 1 |
| KHONG_CO_DU_LIEU | 1 |
| CHAY_DUOC | 124 |

## TOOL_BAO_LOI

| Mã | Tool | Chi tiết |
|---|---|---|
| M20 | `get_salary_ranking` | Bao cao luong ca nhan khong mo cho vai tro giam doc mien/kenh. |

## KHONG_CO_DU_LIEU

| Mã | Tool | Chi tiết |
|---|---|---|
| C28 | `get_customer_product_coverage` | ['status', 'mode', 'channel', 'required_period', 'available_detail_period', 'note'] |

## Chạy được nhưng có thể thiếu chiều câu hỏi yêu cầu

| Mã | Tool | Câu hỏi đòi | Câu hỏi |
|---|---|---|---|
| C11 | `get_top_customers` | theo tháng | Doanh thu đang phụ thuộc vào top 10 khách hàng, top 10 sản phẩm và top |
| C12 | `check_order_timing` | theo tháng | Nếu loại các giao dịch bất thường, đơn lớn đột biến, trả hàng và điều  |
| C13 | `check_order_timing` | theo tháng | Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từn |
| C17 | `check_order_timing` | theo tháng | Tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh là bao nhi |
| C32 | `get_top_customers` | theo tháng | Top khách hàng tăng/giảm mạnh nhất từng tháng là ai; thay đổi đó ảnh h |
| C41 | `get_inventory_by_region` | theo tháng | Giá trị tồn kho, số tháng tồn, hàng chậm luân chuyển, stock-out và hàn |
| C45 | `get_employee_kpi` | theo tháng, theo kênh | Tỷ lệ nhân sự đạt 65/70%, 80%, 100% và 120% KPI từng tháng theo kênh/m |
| M12 | `get_employee_kpi` | theo tháng | Đội nào đạt 100%, 80%, qua cổng 65/70% hoặc dưới cổng; xu hướng 3 thán |
| M21 | `get_top_customers` | theo tháng | Top khách hàng theo doanh thu từng tháng; khách nào tăng/giảm mạnh và  |
| M32 | `get_customer_product_coverage` | tỷ lệ | SKU chiến lược đạt bao nhiêu % target tại từng vùng; vùng nào có khoản |
| M44 | `get_operational_data_quality` | nguyên nhân | Với từng vùng dưới kế hoạch: ba nguyên nhân định lượng, ba hành động,  |
| V14 | `get_customer_product_coverage` | tỷ lệ | Ai có nhiều khách phụ trách nhưng tỷ lệ khách mua thấp; ai có ít khách |
| V19 | `get_top_customers` | theo tháng | Top khách hàng đội tôi từng tháng là ai; khách nào tăng/giảm mạnh nhất |
| V30 | `get_customer_product_coverage` | tỷ lệ | SKU trọng tâm đạt bao nhiêu % target theo từng TDV và khách hàng; khoả |

