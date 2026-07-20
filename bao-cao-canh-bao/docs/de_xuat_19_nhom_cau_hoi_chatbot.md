# Đề xuất mở rộng bộ câu hỏi chuẩn cho chatbot (DNH-x-MCNA)

Bổ sung cho 10 tool sẵn có trong `backend/nl2sql.py` (DNH-x-MCNA) — cùng format
`TEMPLATE_TOOLS`/`report_templates.py`, dialect SQLite kho local (trừ các tool ghi rõ
"Nguồn: Supabase"). Đây là tài liệu tham khảo, **chưa đưa vào code** — repo DNH-x-MCNA hiện
đang có việc dở dang (nhánh `cleanup-post-merge`), chưa nên động vào cho tới khi việc đó
commit xong.

**3 nhóm KHÔNG viết được với dữ liệu hiện có** (không bịa SQL sai):
- Khách hàng vượt hạn mức tín dụng — thiếu cột hạn mức tín dụng nguồn (đang tắt trong chính
  repo D:\DNH vì lý do này, xem `alert_feature_flags.credit_limit_check`).
- KPI sụt giảm so với trung bình 5 tháng trước — `fact_tonghopkhachhang` ở kho local chỉ giữ
  ~90 ngày, không đủ 5 tháng lịch sử (cần đọc Bravo trực tiếp thay vì kho local).
- Nợ chuyển nhóm tuổi so với kỳ trước — `receivable_detail` (Supabase) chỉ có 1 kỳ duy nhất
  (Excel nhập 1 lần đầu dự án, chưa tích lũy nhiều kỳ để so sánh).

**Lưu ý nguồn dữ liệu**: các tool đọc `receivable_detail`/`receivable_etc`/`inventory` trên
Supabase hiện là dữ liệu **Excel nhập 1 lần đầu dự án, không tự làm mới** — số liệu có thể cũ.
Nếu muốn công nợ chính xác thời gian thực, cần port cơ chế gọi thẳng SP gốc DNH
(`usp_DeptAccDueDate_GetData`) mà repo D:\DNH vừa chuyển sang dùng (xem
`src/alerts.py::get_bravo_receivables_snapshot`) — vượt phạm vi tài liệu này.

---

## 11. Top khách nợ quá hạn nhiều nhất

```python
{
    "name": "get_top_overdue_customers",
    "description": "Top N khách hàng có nợ quá hạn lớn nhất. Nguồn: Supabase receivable_detail "
                    "(dữ liệu Excel, có thể cũ — xem lưu ý nguồn dữ liệu ở đầu tài liệu).",
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Số lượng top, mặc định 10"},
            "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"], "description": "Kênh, mặc định ALL"},
        },
        "required": [],
    },
}
```
SQL (Supabase, PostgreSQL — quote cột):
```sql
SELECT "customer_code", "customer_name", "total_overdue", "balance_end", "sales_channel"
FROM receivable_detail
WHERE "period" = :latest_period AND "total_overdue" > 0
  {AND "sales_channel" = :channel nếu channel != ALL}
ORDER BY "total_overdue" DESC LIMIT :limit
```
`latest_period` lấy qua `MAX(period)` đã parse đúng (period dạng "M_YYYY", không sort trực
tiếp — xem `_latest_period_key` đã có sẵn trong `backend/main.py`).

## 12. Tỷ lệ nợ quá hạn theo kênh/công ty

```python
{
    "name": "get_overdue_ratio_by_channel",
    "description": "Tỷ lệ nợ quá hạn/tổng dư nợ theo kênh OTC/ETC hoặc toàn công ty. "
                    "Nguồn: Supabase receivable_detail (có thể cũ).",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
```
```sql
SELECT "sales_channel", SUM("total_overdue") AS overdue, SUM("balance_end") AS balance
FROM receivable_detail WHERE "period" = :latest_period GROUP BY "sales_channel"
```
Tính `overdue/balance*100` ở tầng Python sau khi lấy kết quả.

## 13. Tồn kho sắp hết hàng / tồn kho chết

```python
{
    "name": "get_inventory_risk",
    "description": "Mặt hàng sắp hết hàng (tồn kho thấp, bán nhanh) hoặc tồn kho chết (bán rất "
                    "chậm/không bán). Nguồn: Supabase inventory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "risk_type": {"type": "string", "enum": ["near_stockout", "dead_stock"], "description": "Loại rủi ro cần xem"},
            "limit": {"type": "integer", "description": "Số lượng tối đa, mặc định 10"},
        },
        "required": ["risk_type"],
    },
}
```
```sql
-- near_stockout
SELECT "item_code", "item_name", "closing_qty", "months_to_sell", "channel"
FROM inventory WHERE "months_to_sell" > 0 AND "months_to_sell" <= 1.0
ORDER BY "months_to_sell" ASC LIMIT :limit

-- dead_stock (bán rất chậm hoặc không bán, 9999 = sentinel "không bán được")
SELECT "item_code", "item_name", "closing_qty", "months_to_sell", "channel"
FROM inventory WHERE "closing_qty" > 0 AND ("months_to_sell" >= 6 OR "months_to_sell" = 9999)
ORDER BY "closing_qty" DESC LIMIT :limit
```

## 14. Khách hàng lớn sụt giảm doanh số (churn risk)

```python
{
    "name": "get_customer_churn_risk",
    "description": "Khách hàng lớn có doanh số tháng mới nhất sụt giảm mạnh so với tháng trước. "
                    "Nguồn: kho local.",
    "input_schema": {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "enum": ["OTC", "ETC"], "description": "Kênh"},
            "min_prev_revenue": {"type": "number", "description": "Ngưỡng doanh thu tháng trước tối thiểu để tính, mặc định 50 triệu"},
            "drop_threshold_pct": {"type": "number", "description": "Ngưỡng % sụt giảm tối thiểu, mặc định 30"},
        },
        "required": ["channel"],
    },
}
```
```sql
WITH monthly AS (
    SELECT customer_code, strftime('%Y-%m', doc_date) AS ym, SUM(amount9) AS rev
    FROM vhoadon_{otc|etc}
    WHERE doc_date >= date((SELECT MAX(doc_date) FROM vhoadon_{otc|etc}), '-2 months', 'start of month')
    GROUP BY customer_code, ym
),
latest2 AS (
    SELECT customer_code, ym, rev,
        ROW_NUMBER() OVER (PARTITION BY customer_code ORDER BY ym DESC) AS rn
    FROM monthly
)
SELECT cur.customer_code, prev.rev AS prev_rev, cur.rev AS cur_rev,
    (prev.rev - cur.rev) * 100.0 / prev.rev AS drop_pct
FROM latest2 cur JOIN latest2 prev ON cur.customer_code = prev.customer_code AND prev.rn = 2
WHERE cur.rn = 1 AND prev.rev >= :min_prev_revenue
  AND (prev.rev - cur.rev) * 100.0 / prev.rev >= :drop_threshold_pct
ORDER BY drop_pct DESC
```

## 15. Rủi ro tập trung doanh thu (concentration)

```python
{
    "name": "get_revenue_concentration",
    "description": "Top N khách hàng chiếm bao nhiêu % tổng doanh thu kênh — cảnh báo rủi ro "
                    "phụ thuộc quá nhiều vào ít khách hàng.",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "channel": {"type": "string", "enum": ["OTC", "ETC"]},
            "top_n": {"type": "integer", "description": "Mặc định 3"},
        },
        "required": ["date_from", "date_to", "channel"],
    },
}
```
```sql
WITH cust AS (
    SELECT customer_code, SUM(amount9) AS rev
    FROM vhoadon_{otc|etc} WHERE doc_date BETWEEN ? AND ? GROUP BY customer_code
)
SELECT customer_code, rev, rev * 100.0 / (SELECT SUM(rev) FROM cust) AS pct_of_total
FROM cust ORDER BY rev DESC LIMIT :top_n
```

## 16. Tỷ lệ trả hàng ETC

```python
{
    "name": "get_etc_return_rate",
    "description": "Tỷ lệ giá trị hàng trả về / doanh thu kênh ETC trong 1 khoảng ngày.",
    "input_schema": {
        "type": "object",
        "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
        "required": ["date_from", "date_to"],
    },
}
```
```sql
SELECT
  (SELECT COALESCE(SUM(amount9),0) FROM brvsx_tralai WHERE is_active=1 AND doc_date BETWEEN ? AND ?) AS returns,
  (SELECT COALESCE(SUM(amount9),0) FROM vhoadon_etc WHERE doc_date BETWEEN ? AND ?) AS revenue
```
Tính `returns/revenue*100` ở tầng Python.

## 17. Khách hàng mới mở trong kỳ

```python
{
    "name": "get_new_customers",
    "description": "Danh sách khách hàng mới trong kỳ (is_nc=1 trong snapshot KPI). "
                    "LƯU Ý: fact_tonghopkhachhang chỉ giữ ~90 ngày gần nhất.",
    "input_schema": {
        "type": "object",
        "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
        "required": ["date_from", "date_to"],
    },
}
```
```sql
SELECT DISTINCT e.customer_code, e.employee_code, n.name AS employee_name
FROM fact_tonghopkhachhang e LEFT JOIN dim_nhanvien n ON n.employee_code = e.employee_code
WHERE e.is_nc = 1 AND e.save_date BETWEEN ? AND ?
```

## 18. Khách hàng mua lần đầu (theo lịch sử toàn bộ, không giới hạn 90 ngày)

```python
{
    "name": "get_first_time_customers",
    "description": "Khách hàng có giao dịch ĐẦU TIÊN trong khoảng ngày được hỏi (dựa vào lịch "
                    "sử hóa đơn đầy đủ nhiều năm ở kho local, KHÔNG giới hạn 90 ngày như "
                    "get_new_customers).",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "channel": {"type": "string", "enum": ["OTC", "ETC"]},
        },
        "required": ["date_from", "date_to", "channel"],
    },
}
```
```sql
WITH first_purchase AS (
    SELECT customer_code, MIN(doc_date) AS first_date FROM vhoadon_{otc|etc} GROUP BY customer_code
)
SELECT customer_code, first_date FROM first_purchase WHERE first_date BETWEEN ? AND ?
```

## 19. Doanh thu theo tỉnh/thành phố

```python
{
    "name": "get_revenue_by_province",
    "description": "Doanh thu theo từng tỉnh/thành (chi tiết hơn get_revenue_by_region — vốn "
                    "chỉ có 3 miền Bắc/Trung/Nam).",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"]},
        },
        "required": ["date_from", "date_to"],
    },
}
```
```sql
SELECT tp.city_name, tp.area_code, SUM(o.amount9) AS rev
FROM vhoadon_otc o
    LEFT JOIN dms_khachhang k ON k.code = o.customer_code
    LEFT JOIN dim_tinhthanhpho tp ON tp.city_id = k.city_id
WHERE o.doc_date BETWEEN ? AND ?
GROUP BY tp.city_name, tp.area_code ORDER BY rev DESC
-- UNION ALL nhánh ETC tương tự qua dmssx_khachhang nếu channel=ETC/ALL
```
BẮT BUỘC LEFT JOIN (không INNER) — cùng lý do đã ghi trong `schema_context.py` hiện tại: khách
"mồ côi" sẽ bị mất khỏi tổng nếu dùng INNER JOIN.

## 20. Xu hướng doanh thu 1 tỉnh qua nhiều năm

```python
{
    "name": "get_province_revenue_trend",
    "description": "Doanh thu 1 tỉnh/thành cụ thể qua từng năm — dùng lịch sử nhiều năm có sẵn ở kho local.",
    "input_schema": {
        "type": "object",
        "properties": {
            "province_name": {"type": "string", "description": "Tên tỉnh/thành, khớp gần đúng city_name"},
            "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"]},
        },
        "required": ["province_name"],
    },
}
```
```sql
SELECT strftime('%Y', o.doc_date) AS yr, SUM(o.amount9) AS rev
FROM vhoadon_otc o
    LEFT JOIN dms_khachhang k ON k.code = o.customer_code
    LEFT JOIN dim_tinhthanhpho tp ON tp.city_id = k.city_id
WHERE tp.city_name LIKE '%' || :province_name || '%'
GROUP BY yr ORDER BY yr
```

## 22. Nhân sự nghi nghỉ ngầm (có chỉ tiêu, doanh số = 0)

```python
{
    "name": "get_zero_sales_employees",
    "description": "Nhân sự có chỉ tiêu doanh số tháng nhưng đạt 0 trong kỳ — nghi ngờ nghỉ "
                    "ngầm/vấn đề địa bàn.",
    "input_schema": {
        "type": "object",
        "properties": {"as_of_date": {"type": "string"}},
        "required": ["as_of_date"],
    },
}
```
```sql
SELECT e.employee_code, n.name, n.area_code, n.position_code, MAX(e.month_sale_target) AS target
FROM fact_tonghopkhachhang e LEFT JOIN dim_nhanvien n ON n.employee_code = e.employee_code
WHERE e.save_date = (SELECT MAX(save_date) FROM fact_tonghopkhachhang WHERE save_date <= :as_of_date)
  AND COALESCE(n.is_duplicate, 0) <> 1
GROUP BY e.employee_code, n.name, n.area_code, n.position_code
HAVING MAX(e.month_sale_target) > 0 AND SUM(e.amount_ct) = 0
```

## 25. Xếp hạng nhân viên theo doanh số tuyệt đối

```python
{
    "name": "get_employee_revenue_ranking",
    "description": "Xếp hạng TDV/QLV theo DOANH SỐ TUYỆT ĐỐI (khác get_employee_kpi vốn xếp "
                    "theo % đạt chỉ tiêu) — dùng khi hỏi 'ai bán nhiều nhất', không phải "
                    "'ai đạt/chưa đạt chỉ tiêu'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "as_of_date": {"type": "string"},
            "limit": {"type": "integer", "description": "Mặc định 10"},
            "position_code": {"type": "string", "description": "Lọc vai trò, vd TDV/QLV"},
            "area_code": {"type": "string", "description": "Lọc vùng MB/MT/MN"},
        },
        "required": ["as_of_date"],
    },
}
```
```sql
SELECT e.employee_code, n.name, n.position_code, n.area_code, SUM(e.amount_ct) AS sales
FROM fact_tonghopkhachhang e LEFT JOIN dim_nhanvien n ON n.employee_code = e.employee_code
WHERE e.save_date = (SELECT MAX(save_date) FROM fact_tonghopkhachhang WHERE save_date <= :as_of_date)
  AND COALESCE(n.is_duplicate, 0) <> 1
  {AND n.position_code = :position_code nếu có}
  {AND n.area_code = :area_code nếu có}
GROUP BY e.employee_code, n.name, n.position_code, n.area_code
ORDER BY sales DESC LIMIT :limit
```

## 26. Giá trị đơn hàng trung bình (AOV)

```python
{
    "name": "get_average_order_value",
    "description": "Giá trị trung bình mỗi đơn hàng theo kênh/khoảng ngày.",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "channel": {"type": "string", "enum": ["OTC", "ETC"]},
        },
        "required": ["date_from", "date_to", "channel"],
    },
}
```
```sql
SELECT AVG(order_amount) AS aov, COUNT(*) AS n_orders
FROM (
    SELECT stt, SUM(amount9) AS order_amount
    FROM vhoadon_{otc|etc} WHERE doc_date BETWEEN ? AND ? GROUP BY stt
)
```

## 27. Xu hướng số lượng đơn hàng theo thời gian

```python
{
    "name": "get_order_count_trend",
    "description": "Xu hướng SỐ LƯỢNG đơn hàng theo tháng (khác get_revenue_by_channel — đo tần "
                    "suất mua, không phải giá trị).",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "channel": {"type": "string", "enum": ["OTC", "ETC"]},
        },
        "required": ["date_from", "date_to", "channel"],
    },
}
```
```sql
SELECT strftime('%Y-%m', doc_date) AS ym, COUNT(DISTINCT stt) AS n_orders
FROM vhoadon_{otc|etc} WHERE doc_date BETWEEN ? AND ? GROUP BY ym ORDER BY ym
```

## 28. So sánh tỷ trọng & tăng trưởng OTC vs ETC cùng lúc

```python
{
    "name": "get_channel_mix_comparison",
    "description": "So sánh song song 2 kênh OTC/ETC trong CÙNG 1 kỳ: tỷ trọng doanh thu + tăng "
                    "trưởng so kỳ trước mỗi kênh — khác compare_periods (so 2 kỳ, không tách kênh "
                    "trong cùng 1 lần trả lời).",
    "input_schema": {
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "prev_date_from": {"type": "string"}, "prev_date_to": {"type": "string"},
        },
        "required": ["date_from", "date_to", "prev_date_from", "prev_date_to"],
    },
}
```
Gọi lại `revenue_by_channel()` đã có sẵn 2 lần (kỳ hiện tại + kỳ trước), tính tỷ trọng +
% tăng trưởng riêng từng kênh ở tầng Python — không cần SQL mới, chỉ cần tool wrapper mới.

## 29. Tình trạng thực hiện hợp đồng/thầu ETC

```python
{
    "name": "get_etc_contract_status",
    "description": "Tình trạng thực hiện hợp đồng/thầu ETC (giá trị hợp đồng, đã thanh toán, "
                    "còn lại). Nguồn: Supabase receivable_etc (có thể cũ).",
    "input_schema": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Mặc định 10, xếp theo còn lại nhiều nhất"}},
        "required": [],
    },
}
```
```sql
SELECT "customer_code", "customer_name", "contract_value", "total_paid",
    ("contract_value" - "total_paid") AS remaining, "province_code", "sales_manager"
FROM receivable_etc WHERE "contract_value" > 0
ORDER BY remaining DESC LIMIT :limit
```

---

**Tổng cộng 16 nhóm khả thi** (11-20, 22, 25-29) + 3 nhóm cần chờ dữ liệu (21, 23, 24, ghi chú
ở đầu) + 1 nhóm nhạy cảm không nên thêm (30, xem hội thoại — rủi ro KPI QĐ 0429-2 nêu tên nhân
sự, đang bị chặn cố ý trong repo D:\DNH).
