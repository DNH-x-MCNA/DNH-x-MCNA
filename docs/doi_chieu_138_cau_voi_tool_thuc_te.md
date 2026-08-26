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

# Bổ sung 25/08/2026 — đã kiểm chứng live: **25/25 câu chọn đúng tool**

Mục 5 ở trên nêu bước tiếp theo là kiểm thử live để đánh giá model có chọn đúng tool không. Việc này
**đã làm xong ngày 25/08/2026** trên máy 24 với dữ liệu và tài khoản production.

## Kết quả đo được

Mẫu phân tầng 25 câu (`scripts/run_tool_routing_sample.py`), ưu tiên các câu dùng 11 tool mới:

| Vòng | Kết quả | Chi phí |
|---|---|---|
| Vòng 1 (`tool-routing-20260825-165120.json`) | 23/25 = 92% | 1,4360 USD |
| Vòng 2, sau khi sửa mô tả tool (`tool-routing-20260825-170905.json`) | **25/25 = 100%** | 1,8539 USD |

Tách theo vai ở vòng 1 — đây mới là con số quan trọng:

| Nhóm vai | Kết quả vòng 1 | Vì sao đáng chú ý |
|---|---|---|
| **TP + QLV** (13 câu) | **13/13 = 100%** | Nhóm này bị `_tools_for_request()` gỡ sạch tool SQL tự do (luôn có `scope_area_code`/`scope_channel`). Chọn sai tool là **không có đường lùi**. |
| C-level (12 câu) | 10/12 | Vẫn còn SQL tự do làm phương án dự phòng. |

## Hai câu trượt ở vòng 1 và cách xử lý

**S13 — trượt thật, đã sửa.** *"Địa bàn nào quy mô lớn nhưng tăng trưởng thấp?"* → model tự viết SQL
thay vì gọi `get_geography_monthly_performance`, dù tool thừa dữ liệu để trả lời (doanh thu, tỷ trọng,
MoM, streak theo miền/tỉnh). Nguyên nhân: mô tả tool chỉ ghi *"xep hang / diem keo giam / co hoi dia
ban"*, không có cụm nào khớp "quy mô lớn + tăng trưởng thấp". Đã bổ sung đúng cụm đó vào mô tả
(`faeccdf`), vòng 2 gọi đúng.

Đây là câu **đáng lo nhất cả bộ**: C-level còn SQL tự do nên vẫn ra số, nhưng cùng câu đó do một TP
hỏi thì không có gì đỡ — sẽ từ chối hoặc ra số sai. Bài học rút ra: **mô tả tool phải phủ được cách
người dùng thật diễn đạt, không chỉ phủ được chức năng kỹ thuật của tool.**

**C05 — kỳ vọng trong kịch bản đo sai, model đúng.** *"Dữ liệu doanh thu và công nợ đang cập nhật đến
ngày nào?"* — kịch bản kỳ vọng `get_receivables_overview` + `get_revenue_by_channel`, nhưng hai tool
đó trả về **số tiền**, không trả về ngày. Model gọi `get_receivables_history_dates`, đúng y hướng dẫn
trong docstring của chính tool đó. Ngày dữ liệu doanh thu thì đã có sẵn trong `_dynamic_context_note()`
nên không cần tool. Đã sửa kỳ vọng cho khớp nghiệp vụ.

## Ba lần đo đầu tiên báo 4% — là lỗi thước đo, không phải lỗi model

Ghi lại để không ai lặp lại: ba lần chạy đầu đều báo *"1/25 (4%) — chi phí 0,0000 USD"*, trông y hệt
model chọn sai tool hàng loạt. Thực tế chatbot **chạy đúng ngay từ lần đầu**. Nguyên nhân:
`run_business_evaluation.py` tính đường dẫn **đọc** log qua biến môi trường `DNH_BACKEND_DIR`, còn code
**ghi** log (`cost_logger.py`, `query_engine.py`) dùng vị trí file của chính nó — hai bên trỏ về hai
thư mục khác nhau nên đọc ra 0 dòng. Đã sửa ở `96c4d85` (ép lấy đường dẫn thẳng từ module đang ghi).

Bài học: **khi số đo bất thường, đọc nội dung câu trả lời trước khi suy đoán nguyên nhân.** Chỉ cần
nhìn trường `answer` là thấy ngay bảng doanh thu 12 tháng và danh sách khách im lặng đúng định dạng
tool — đủ để loại bỏ giả thuyết "model không gọi tool" ngay lập tức.

## Giới hạn của con số 25/25 — phải đọc kỹ trước khi báo cáo DNH

1. **Chỉ đo ĐỊNH TUYẾN TOOL, chưa đo ĐỘ ĐÚNG CỦA SỐ.** 25/25 nghĩa là model gọi đúng tool cần gọi.
   Việc các con số trong câu trả lời có khớp Bravo hay không là **phép kiểm riêng, chưa làm**.
2. **25 câu, không phải 138.** Mẫu chọn theo tầng, ưu tiên 11 tool mới. Phần còn lại vẫn là đối chiếu
   trên giấy.
3. **Không suy ra "138/138 trả lời được".** Các nhóm ở mục 3 vẫn thiếu nguồn dữ liệu từ DNH.

## Chi phí thực đo

1,8539 USD / 25 câu = **0,0742 USD/câu** — là **cận trên**: 25 câu này là loại nặng nhất bộ điều hành
(chuỗi 12 tháng, vòng đời khách, bán chéo, năng suất đội ngũ), nặng hơn hẳn câu hỏi thường ngày. Con số
này nên dùng để soát lại trần tuần (QLV 30 / TP 60 / C-level 120) so với ngân sách, chứ không nên lấy
làm chi phí bình quân.

## Việc tiếp theo

Kiểm chứng **độ đúng của số** trên các tool mới: chọn vài câu đã chạy, đối chiếu kết quả với truy vấn
Bravo trực tiếp. Đây là loại lỗi đã nhiều lần xảy ra trong dự án (số trông hợp lý nhưng sai tầng dữ
liệu hoặc đếm trùng TDV/QLV), và định tuyến đúng tool **không** bảo vệ được khỏi loại lỗi đó.
