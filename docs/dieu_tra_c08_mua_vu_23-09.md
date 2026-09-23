# Điều tra C08 — "tháng thấp nhất kênh ETC là tháng 9"

*23/09/2026. Người chấm ghi: "Tháng thấp nhất của kênh ETC là tháng 9, còn lại khớp".
Tool `revenue_seasonality` ([report_templates.py:2525](../backend/report_templates.py)), checker S80.*

> **Kết luận: chatbot đúng, checker sai phương pháp.** Checker tính cả **tháng 9/2026 chưa hết
> tháng** vào nền mùa vụ, kéo chỉ số tháng 9 xuống và làm nó thành tháng thấp nhất giả.
> **Không sửa code chatbot.** Cần sửa checker.

## Khác biệt nằm ở đúng một dòng

Tool loại tháng đang chạy khỏi nền mùa vụ:

```python
complete_rows = [
    row for row in series["months"]
    if not row.get("khong_co_du_lieu")
    and (row["month"] != latest_month or current_month_complete)
]
```

Checker `WHERE` không có điều kiện tương ứng — `#sales` gom mọi tháng, kể cả tháng đang chạy:

```sql
), idx AS (
  SELECT Mth,Channel,AVG(Revenue) AvgMonthRevenue FROM m GROUP BY Mth,Channel
)
```

## Tái lập trên kho dev — lật đúng kết luận

Chạy cùng chuỗi 24 tháng, chỉ đổi **một** biến là có tính tháng đang chạy hay không:

| | Tháng thấp nhất | Chỉ số |
|---|---|---:|
| **Cách checker** — tính cả tháng 9 chưa tròn | **tháng 9** | 70,27% |
| **Cách chatbot** — loại tháng đang chạy | **tháng 2** | 82,26% |

Cách chatbot cho **tháng 2 = 26,6 tỷ, 82,26%** — khớp đúng con số chatbot hiển thị trong ảnh UAT
(*"tháng 2 – TB ~26,6 tỷ/tháng, chỉ số 82,3%"*).

### Số của checker cũng tự tố cáo điều này

Checker cho tháng 9 ETC = **26.268.817.486**. Nhưng tháng 9 **tròn** duy nhất trong cửa sổ (9/2025)
là **28,2 tỷ**. Nếu checker lấy trung bình hai quan sát:

```
(28,2 tỷ + x) / 2 = 26,27 tỷ   →   x ≈ 24,3 tỷ
```

24,3 tỷ chính là mức hợp lý cho **23/30 ngày** của tháng 9/2026 tính đến ngày chấm. Con số khớp với
giả thuyết "một tháng cụt bị đếm như một tháng tròn".

## Vì sao đây là lỗi phương pháp, không phải khác biệt định nghĩa

Chỉ số mùa vụ trả lời câu *"tháng nào trong năm thường yếu"*. Đếm nửa tháng 9 như một tháng 9 đầy đủ
thì kết quả **phụ thuộc vào ngày chạy truy vấn**:

- Chạy ngày **23/09**: tháng 9 thành thấp nhất.
- Chạy ngày **01/10**: tháng 9 trở lại bình thường, tháng 2 lại thấp nhất.

Một chỉ số mùa vụ đổi kết luận theo ngày bấm nút thì không phải chỉ số mùa vụ. Đây cùng họ với lỗi
đã sửa ở `revenue_monthly_series` (PR #51: tháng đang chạy phải cắt tại hôm nay và gắn cờ
`thang_chua_tron`).

## Phần chatbot nên nói rõ hơn

Sau khi loại tháng đang chạy, tháng 9 chỉ còn **1 quan sát** trong khi các tháng khác có 2. Tool có
sẵn trường `observations` cho từng tháng và trạng thái
`INSUFFICIENT_HISTORY_FOR_SEASONAL_CONCLUSION`, nhưng câu trả lời trong ảnh **không nhắc** rằng
tháng 9 dựa trên một năm duy nhất.

Đây là điểm đáng cải thiện — **không phải lỗi số**: khi một tháng có ít quan sát hơn hẳn các tháng
còn lại thì phải nói ra, vì xếp hạng giữa các tháng sát nhau (tháng 2 là 82,26% và tháng 9 là
87,26%) không vững.

## Việc cần làm

| # | Việc | Vùng | Mức |
|---|---|---|---|
| 1 | Sửa checker S80: loại tháng chưa tròn khỏi `idx`, hoặc chỉ lấy các tháng đã kết thúc | checker/DNH | 🔴 checker đang cho kết luận sai |
| 2 | Câu trả lời nêu rõ tháng nào có ít quan sát hơn (`observations`) | `backend/` | 🟡 trình bày |
| 3 | Không sửa `revenue_seasonality` phần loại tháng đang chạy | — | ✅ đang đúng |

Gợi ý sửa checker — thêm điều kiện loại tháng của `@AsOfDate` khỏi nền:

```sql
), idx AS (
  SELECT Mth, Channel, AVG(Revenue) AvgMonthRevenue
  FROM m
  WHERE NOT (Yr = YEAR(@AsOfDate) AND Mth = MONTH(@AsOfDate))   -- bo thang chua tron
  GROUP BY Mth, Channel
)
```

Lưu ý phần `cur` của checker vẫn giữ nguyên — tháng đang chạy vẫn cần cho cột
`CurrentMonthRevenue`/`DeviationPct`, chỉ **không được** đưa vào nền so sánh.
