# Đối chiếu 12 lượt timeout với mốc bản sửa — 23/09/2026

*Nguồn: `query_runs` trên máy 24, quét 01–30/09. Miễn phí, không gọi model.*

**Giờ trong `query_runs` là UTC; giờ máy 24 = UTC + 7.** Bảng dưới đã quy về giờ máy 24 để so trực
tiếp với giờ commit. Lẫn hai hệ giờ này là cách dễ nhất để kết luận sai "bản sửa vào trước lượt lỗi".

## Kết quả: 6/12 đã có bản sửa trỏ đúng, 6/12 chưa

### ✅ Nhóm đã có bản sửa — chỉ cần chấm lại, không sửa thêm

| Câu | Lượt lỗi (giờ máy 24) | Bản sửa | Khoảng cách |
|---|---|---|---|
| Mùa vụ cao/thấp theo kênh & nhóm SP | 04/09 16:12 · 04/09 16:16 · 17/09 13:46 · **21/09 09:39** | `074e98f` **21/09 13:54** *fix(c08): avoid seasonality report timeout* | lượt cuối cách bản sửa **4 giờ 15 phút** |
| Khách phát sinh 3 tháng chưa đạt KPI tái đơn | 15/09 15:16 | `2954886` **16/09 08:39** *fix(loc-doi): thêm manager_code…* | commit ghi thẳng *"UAT 15/09 15:16 loi 114 giay"* |
| Tỉnh/vùng độ phủ khách thấp | 16/09 14:00 | `34f9dca` **16/09 15:50** *fix(payload): địa bàn không bị cắt mù…* | 1 giờ 50 phút sau |

Cả 4 lượt "mùa vụ" đều **trước** `074e98f`. Không có lượt nào hỏng sau bản sửa → **chưa có bằng
chứng bản sửa chưa đủ.** Tính **một** lượt chấm lại cho cả 4, không phải bốn.

### ⏳ Nhóm chưa tìm thấy bản sửa nào trỏ đúng — ứng viên cho phiên `backend/`

| Câu | Lượt lỗi (giờ máy 24) | Ghi chú |
|---|---|---|
| **Cá nhân/đội dưới 80% liên tiếp 3 tháng; khoảng hụt** | 08/09 **13:46** · 08/09 **13:48** | 🔴 xem dưới |
| Mỗi tháng đạt bao nhiêu % kế hoạch theo công ty/kênh/miền | 03/09 09:25 | |
| Biến động DT giải thích bởi đơn/khách/tần suất/sản lượng/giá/cơ cấu | 03/09 10:10 | |
| DT gộp, chiết khấu, khuyến mãi, hàng trả, DT thuần từng tháng | 04/09 09:28 | |
| Tăng trưởng đến từ mở mới hay tăng mua trên khách hiện hữu | 04/09 10:05 | |

## 🔴 Câu hỏi hỏng nặng nhất: "dưới 80% liên tiếp 3 tháng"

Trong **một ngày 08/09**, câu này hỏng **4 lần** — và người dùng cứ hỏi lại:

| Giờ máy 24 | Kiểu hỏng |
|---|---|
| 11:27 | hết credit |
| 13:31 | hết credit |
| **13:46** | **timeout** |
| **13:48** | **timeout** |

Hai lượt timeout cách nhau **2 phút** — dấu hiệu người dùng bấm lại ngay. Hai lượt hết credit trước
đó làm nhiễu: nhìn vào sổ chấm thì cả bốn đều là "Lỗi", không phân biệt được.

**Đây là ứng viên số một** sau khi xong việc credit: cùng một câu, cùng một ngày, bốn lần hỏng, và
chưa có commit nào nhắm vào.

## Việc còn thiếu để Codex sửa tiếp

Bảng trên đã có `created_at` và câu hỏi. **Còn thiếu `duration_ms` và tool đã gọi** — hai thứ cần để
biết timeout ở bước nào (truy vấn kho, đọc Bravo, hay model xử payload).

Đã bổ sung **Phần 5** vào [`scripts/doc_query_runs_may_24.py`](../scripts/doc_query_runs_may_24.py):
in ra từng lượt timeout kèm giờ UTC, **giờ máy 24 đã quy đổi sẵn**, `duration_ms` theo giây, và
`sql_used_json`. Chạy trên máy 24:

```
python C:\dnh_chatbot\scripts\doc_query_runs_may_24.py
```

## Lưu ý khi đọc kết quả

Bài học từ câu "độ phủ khách" (16/09): 110 giây **không phải do truy vấn chậm**. Đo lại trên kho dev
thì `geography_monthly_performance` chỉ mất **2,2–2,6 giây**; chỗ chậm là **model phải xử payload
236.714 ký tự**. Bản sửa thu gọn payload xuống 8.850 ký tự (−96,3%).

Vì vậy `duration_ms` lớn mà tool nhanh thì hướng sửa là **thu gọn payload**, không phải tối ưu SQL.
Kiểm bằng cách gọi thẳng tool trên kho dev và bấm giờ trước khi đụng vào truy vấn.
