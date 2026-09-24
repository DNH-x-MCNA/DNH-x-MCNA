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

---

## 🔴 Đo được 23/09: cả 12 lượt chết ở CÙNG một ngưỡng, không phải 6 câu chậm riêng lẻ

`duration_ms` của toàn bộ 12 lượt:

```
111,8  111,9  111,9  112,1  112,3  112,4  112,7  112,9  113,0  114,4  114,9  116,4 giây
```

*(Bản đầu của mục này chỉ liệt **11** giá trị — sót lượt 04/09 10:05 của `thuy.nguyen`, 112,9 giây.
Codex bắt được khi đối chiếu. Dải và kết luận không đổi.)*

Trải **18 ngày**, **6 câu hỏi khác nhau**, **2 tài khoản** — mà biên độ chỉ **4,6 giây**. Nếu là truy
vấn chậm thật thì thời lượng phải tản mát. Bó sát thế này chỉ có một cách giải thích: **một ngưỡng
cấu hình cố định**.

Ngưỡng đó nằm ở [nl2sql.py:180](../backend/nl2sql.py):

```python
REQUEST_TIMEOUT_SECONDS = _timeout_env("CHAT_REQUEST_TIMEOUT_SECONDS", 110, 120)
TOOL_TIMEOUT_SECONDS    = _timeout_env("CHAT_TOOL_TIMEOUT_SECONDS", 40, REQUEST_TIMEOUT_SECONDS)
LLM_CALL_TIMEOUT_SECONDS = _timeout_env("CHAT_LLM_TIMEOUT_SECONDS", 45, REQUEST_TIMEOUT_SECONDS)
```

**110 giây ngân sách + 1,8–6,4 giây dọn dẹp = 111,8–116,4 giây quan sát được.** Khớp trọn vẹn.

### Vì sao người dùng thấy chữ "Lỗi" thay vì một câu trả lời rút gọn

Hệ thống **đã có** đường xuống thang êm — [nl2sql.py:3714](../backend/nl2sql.py):

```python
if query_plan.expired():
    fallback = query_plan.timeout_answer()
```

Nhưng chỗ này chỉ được kiểm **ở bước chốt câu trả lời cuối**. Nếu ngân sách cạn **giữa** một lượt gọi
model trong vòng lặp, tham số

```python
timeout=max(1.0, min(LLM_CALL_TIMEOUT_SECONDS, query_plan.remaining_seconds()))
```

làm SDK **ném exception** — và exception đó thoát ra ngoài thành `status=error`,
`error_message="The read operation timed out"`.

⚠️ **Đính chính 23/09.** Bản đầu viết: *"cả 12 lượt đều có `sql_used_json` rỗng → không lượt nào
chạm tới `timeout_answer()`"*. **Suy luận đó sai.** Code cũ chỉ ghi `sql_used_json` **khi request
hoàn tất**, nên **mọi** lượt hỏng đều rỗng — bất kể hỏng ở đâu. Một đặc điểm chung của tất cả các ca
thất bại thì không chứng minh được riêng ca nào.

Trường rỗng đó **tương thích** với giả thuyết nhưng **không phải bằng chứng**. Căn cứ thật sự cho
giả thuyết chỉ có một: **độ bó của `duration_ms`** (12 lượt, 18 ngày, 6 câu, biên độ 4,6 giây) khớp
với ngưỡng 110 giây.

### Hệ quả

Đây **không phải** 6 câu hỏi cần tối ưu riêng. Đây là **một lỗ hổng xử lý ngoại lệ**: hệ thống có
sẵn phương án xuống thang nhưng không bắt được đúng exception để dùng nó.

Nếu giả thuyết đúng thì sửa chỗ này sẽ làm các lượt vượt ngân sách về sau chuyển từ chữ **"Lỗi"**
thành câu trả lời rút gọn kèm phần đã đối chiếu được. Với người chấm UAT, đó là khác biệt giữa
"chatbot hỏng" và "chatbot trả lời được một phần, nói rõ phần còn thiếu".

⚠️ **Chưa khẳng định được 12 lượt lịch sử sẽ trả lời đầy đủ sau khi sửa.** Chưa có số đo UAT thật
sau deploy, và mỗi câu vẫn có thể vượt ngân sách vì lý do riêng. Phải chấm lại đo thật rồi mới kết
luận — đúng như bài học "đừng kết luận từ replication mà chưa gọi chính tool đó".

> Cùng họ với sự cố credit: người chấm chỉ thấy một chữ "Lỗi" cho những nguyên nhân hoàn toàn khác
> nhau, nên ghi vào sổ như nhau.

### Gợi ý cho phiên `backend/`

1. Bắt exception timeout quanh **mọi** lượt gọi model trong vòng lặp, không chỉ ở bước chốt; rơi về
   `query_plan.timeout_answer()` thay vì để thoát ra.
2. Ghi `sql_used_json` **ngay khi bắt đầu gọi tool**, không đợi request hoàn tất — hiện lượt hỏng
   nào cũng để trống trường này nên không truy được đã chạy tới đâu. Đây vừa là việc cần sửa, vừa là
   lý do phép suy luận ở trên không dùng trường này làm bằng chứng được.
3. Chỉ sau khi làm xong hai việc trên mới bàn tới việc nới `CHAT_REQUEST_TIMEOUT_SECONDS` — nới trần
   mà không có đường xuống thang thì chỉ dời chỗ hỏng.

---

## Việc còn thiếu để Codex sửa tiếp

✅ **Đã lấy được `duration_ms` (xem trên).** `sql_used_json` thì **rỗng ở cả 12 lượt** — bản thân điều
đó là bằng chứng, không phải thiếu dữ liệu.

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
