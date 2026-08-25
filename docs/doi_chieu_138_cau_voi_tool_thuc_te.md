# Đối chiếu 138 câu hỏi điều hành với tool thật của chatbot

> Cập nhật ngày 24/08/2026, **không gọi API**. Kết quả được đối chiếu từ
> `backend/nl2sql.py`, `backend/report_templates.py` và kiểm thử tự động.
>
> Hệ thống hiện đăng ký **40 tool cố định**, tăng 11 tool so với mốc rà soát ban đầu 29 tool.
> Toàn bộ test mã nguồn hiện qua: **297 passed, 1 deselected**.

## 1. Kết quả các vòng triển khai

### P0 — Chuỗi tháng và vòng đời khách hàng: đã hoàn thành ở mức dữ liệu hiện có

| Tool | Khả năng |
|---|---|
| `get_revenue_monthly_series` | Chuỗi doanh thu theo tháng, MoM/YoY trong một lần gọi; không còn phải gọi 12–24 lần cho một báo cáo |
| `get_customer_lifecycle_summary` | Khách mới theo từng tháng dựa trên tháng mua đầu tiên quan sát được |
| `get_customers_silent` | Khách im lặng/ngừng mua theo ngưỡng ngày và kỳ so sánh |
| `get_customer_cohort_retention` | Cohort giữ chân sau 1/3/6/12 tháng, nhóm theo toàn công ty/kênh/miền |
| `get_customer_movement` | Khách mới, tái kích hoạt, ngừng mua, tăng, giảm, không đổi; có doanh thu, số đơn, TDV và đơn lặp lại |

Phủ trực tiếp hoặc phần lớn nhóm câu `C29` `C30` `C31` `M08` `M22` `M23` `M24`
`V15` `V20` `V21` `V22` `V23`.

Giới hạn cần hiểu đúng:

- “Khách mới” là lần mua đầu tiên **trong lịch sử dữ liệu đang có**, không khẳng định là lần mua đầu tiên suốt đời.
- Cohort 6/12 tháng chỉ hoàn chỉnh khi kho có đủ lịch sử và cohort đã đủ tuổi.
- Không dùng dữ liệu tổng hợp chồng lên chi tiết ở vùng thời gian giao nhau.

### P1 — Gap/run-rate, độ phủ và bán chéo: đã hoàn thành

| Tool | Khả năng |
|---|---|
| `get_kpi_gap_run_rate` | Khoảng thiếu để đạt 65/70/80/100/120% target và doanh số/ngày cần đạt trong số ngày lịch còn lại |
| `get_cross_sell_opportunities` | Cặp sản phẩm thường mua cùng nhau và khách đã mua A nhưng chưa mua B |
| `get_customer_product_coverage` | Độ phủ theo khách/sản phẩm/nhân viên; kỳ hiện tại so với kỳ trước; doanh thu, đơn, khách, SKU, sản lượng, AOV và khoảng cách với benchmark nội bộ |

Phủ phần lớn nhóm `C04` `C24` `C26` `C36` `M02` `M06` `M25` `M26` `V02`
`V03` `V07` `V14` `V24` `V25` `V26` `V31` `V32`.

Giới hạn cần hiểu đúng:

- Run-rate là phép chia tuyến tính theo số ngày lịch còn lại, **không phải dự báo**.
- Benchmark độ phủ là benchmark nội bộ trên dữ liệu bán hàng, không phải thị phần hay share-of-wallet bên ngoài.
- ETC chưa có target cùng cấu trúc với KPI OTC nên tool gap trả trạng thái không áp dụng thay vì suy đoán.

### P1 — Địa bàn: hoàn thành đến cấp dữ liệu có khóa

`get_geography_monthly_performance` hỗ trợ:

- miền và tỉnh/thành;
- doanh thu, số hóa đơn, số khách, MoM, tỷ trọng, thứ hạng và streak tăng/giảm;
- gộp OTC/ETC nhưng khử trùng khách hàng và hóa đơn bằng khóa nghiệp vụ;
- áp đúng phạm vi miền/kênh/đội của người dùng.

Các yêu cầu theo **chi nhánh/NPP/nhà phân phối** trả `not_applicable`: kho hiện chưa có khóa ánh xạ tin cậy
từ hóa đơn sang các cấp này. Nhóm `C21` `C23` `C25` `C27` `C28` `M10` `M27` `M29`
`V08` vì vậy chỉ được phủ ở cấp miền/tỉnh, chưa phủ cấp chi nhánh/NPP.

### P2 — Năng suất đội ngũ: đã hoàn thành, có cảnh báo lịch sử nhân sự

`get_workforce_productivity` trả theo nhân viên/QLV/miền/toàn công ty:

- headcount, doanh thu/người, MoM và streak tăng/giảm;
- thâm niên bình quân khi có ngày vào làm;
- phạm vi QLV chỉ nhìn thấy chính đội được gán.

Phủ phần lớn `C22` `C46` `C47` `M05` `M15` `M16` `M17` `M19` `V13`.

Kho chưa có lịch sử điều chuyển/gán quản lý theo từng ngày. Báo cáo lịch sử vì vậy dùng cấu trúc nhân sự
hiện tại và trả cảnh báo rõ, không ngầm coi đó là cơ cấu lịch sử chính xác.

### P2 — Chất lượng dữ liệu vận hành: hoàn thành các kiểm tra có nguồn

`get_operational_data_quality` kiểm tra:

- nhân viên KPI thiếu quản lý, thiếu target hoặc thiếu bản ghi dimension;
- mã nhân viên trùng/đánh dấu trùng;
- hóa đơn thiếu khách hàng, tỉnh/thành, nhân viên hoặc có ngày tương lai;
- phạm vi miền/đội được giữ nguyên cho cả phép đếm ngày tương lai.

Các kiểm tra sau được trả trong danh sách `unavailable_checks`, không tạo số giả:

- đơn DMS chưa xuất hóa đơn/hủy đơn — chưa có bảng nguồn đơn hàng DMS được ánh xạ;
- action tracker — chưa có nguồn;
- lỗi ánh xạ chi nhánh/NPP — chưa có khóa nguồn.

## 2. Bảo mật phạm vi

TP/QLV không có SQL tự do nên 11 tool mới đều được đăng ký vào lớp tool cố định, lớp lọc nhân sự và
lớp lọc kênh. Các trường hợp quan trọng đã có test:

- QLV hỏi tổng/miền trong tool gap chỉ nhận kết quả của đội mình;
- doanh thu ETC/OTC không làm đếm trùng khách trong báo cáo địa lý;
- kiểm tra hóa đơn tương lai không làm lộ số toàn công ty cho người dùng có phạm vi;
- các khóa đơn cho bán chéo gồm kênh, ngày, khách và số thứ tự chứng từ.

## 3. Những nhóm vẫn phụ thuộc dữ liệu DNH

| Nhóm | Câu tiêu biểu | Thiếu gì |
|---|---|---|
| Giá vốn/lợi nhuận | `C13` `C14` `C15` `C19` | Chưa map tin cậy giá vốn và chiết khấu |
| Thu tiền/DSO | `C38` `V37` | Chưa có chứng từ thu tiền theo hóa đơn |
| Lịch sử công nợ | `C37` `M37` `V35` | Bảng lịch sử mới bắt đầu ghi từ 21/08/2026, cần thời gian tích lũy |
| Thầu/hợp đồng ETC | `C43` `C44` `M41` `M42` | Chưa map trạng thái tham gia, trúng, thua và hợp đồng |
| Viếng thăm/đi tuyến | `C49` `V16` | `DMS_DiTuyen` chưa được đưa vào kho/tool |
| Đơn chưa hóa đơn/hủy | một phần nhóm chất lượng vận hành | Chưa có nguồn đơn DMS được ánh xạ |
| Chi nhánh/NPP | một phần nhóm địa bàn | Chưa có khóa ánh xạ từ hóa đơn |
| Action tracker | `C52` `M44` | Không có nguồn dữ liệu |

## 4. Các câu bị chặn có chủ đích

`C50` `M43` `V09` là câu dự báo tương lai. Chatbot từ chối theo thiết kế và không trừ hạn mức tuần.
Run-rate mới chỉ cho biết tốc độ tuyến tính cần đạt, không mở đường vòng để gọi đó là dự báo.

## 5. Kết luận cam kết

Các vòng P0/P1/P2 đã được triển khai hết trong phạm vi dữ liệu hiện có. Không nên diễn giải kết quả này
thành “138/138 câu đều trả lời đầy đủ”: các nhóm tại mục 3 vẫn cần DNH cung cấp hoặc xác nhận nguồn dữ
liệu. Bước tiếp theo nên là kiểm thử live theo bộ câu hỏi và thu lại câu trả lời/SQL để đánh giá khả năng
model chọn đúng tool; việc này chưa được thực hiện vì vòng này chủ động **không gọi API**.

---

# Bổ sung 25/08/2026 — đã thử kiểm chứng live, bị chặn

Mục 5 ở trên nêu bước tiếp theo là **kiểm thử live để đánh giá model có chọn đúng tool không**.
Ngày 25/08/2026 đã thử chạy nhưng **không thực hiện được**: tài khoản Anthropic hết số dư
(`Your credit balance is too low to access the Anthropic API`) — không phải hết hạn mức tạm thời.

Vì vậy cần đọc toàn bộ tài liệu này với một lưu ý quan trọng:

**Toàn bộ đánh giá phủ câu hỏi ở trên là đối chiếu TRÊN GIẤY** (mô tả tool ↔ nội dung câu hỏi).
322 test đơn vị chứng minh SQL của từng tool chạy đúng, nhưng **không** chứng minh model biết chọn
đúng tool khi người dùng hỏi bằng tiếng Việt tự nhiên. **11 tool mới chưa từng được model gọi thật
lần nào.** Đây đúng là khoảng cách đã nhiều lần gây lỗi trong dự án này (câu trả lời trông hợp lý
nhưng gọi nhầm tool/nhầm tầng dữ liệu).

Ước lượng thô mức phủ hiện tại: khoảng **84/138 câu (61%)** trả lời được, ~22 câu còn thiếu tool
(tập trung ở target theo SKU, chi nhánh/NPP, thiếu hàng, hàng trả — đều do **hạ tầng dữ liệu chưa
có**, không phải thiếu công sức viết tool), ~20 câu chờ DNH cung cấp nguồn, 3 câu chặn có chủ đích.
Con số 61% phải coi là **giới hạn trên chưa kiểm chứng**, không phải kết quả đã đo.

**Việc cần làm ngay khi có ngân sách API**: chạy mẫu phân tầng ~25 câu (mỗi nhóm vài câu, ưu tiên
các câu dùng 11 tool mới), thu lại câu trả lời + tool đã gọi, để biến con số trên giấy thành số đo
thật. Chi phí ước tính 1–2 USD.
