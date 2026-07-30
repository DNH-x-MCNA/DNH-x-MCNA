# Trọn bộ công việc 16/07 → 29/07/2026

**Kỳ báo cáo:** 2 tuần kể từ buổi họp 16/07 · **121 đầu việc** đã hoàn thành và đưa lên hệ thống thật.

Tài liệu này là bản đầy đủ để dựng slide. Bản rút gọn 7 slide: [`bao_cao_tien_do_30-07.md`](bao_cao_tien_do_30-07.md).

---

## Tổng quan theo ngày

| Ngày | Số đầu việc | Trọng tâm |
|---|---|---|
| 16/07 | 13 | Ngay sau họp: tách ngưỡng nợ theo kênh, đối chiếu KPI với hóa đơn thật, phân quyền QLV |
| 17/07 | 10 | **Sửa dư nợ bị thổi phồng 4–15 lần**; bịt 4 chỗ rò dữ liệu ngoài phạm vi |
| 20/07 | 6 | Kênh MT (Modern Trade), sửa mã nhân viên trên hóa đơn, đổi màu thương hiệu |
| 21/07 | 8 | **Bỏ hẳn Supabase** khỏi pipeline; sửa KPI cộng trùng 2 lần |
| 22/07 | 6 | Công cụ đối chiếu doanh thu 2 chiều, rate-limit, xử lý 3 góp ý treo |
| 23/07 | 19 | **Chuẩn hóa ngưỡng KPI theo cấu hình thật của DNH**; bỏ hẳn Telegram |
| 24/07 | 6 | Chính sách thu nhập TDV OTC 3 miền; theo dõi ngân sách chi phí AI |
| 27/07 | 12 | **Công nợ chatbot về cùng nguồn với báo cáo**; tầng gộp KPI |
| 28/07 | 21 | Hai lỗ hổng phân quyền; bảng điều khiển chi phí AI |
| 29/07 | 13 | Lỗi KPI thiếu 2 miền; 4 lớp lỗi tính tiền; giao diện mới |

---

## A. Số liệu sai — 13 lỗi đã tìm ra và sửa

Đây là nhóm quan trọng nhất: mỗi lỗi đều từng cho ra **con số trông hợp lý nhưng sai**.

### Nhóm nghiêm trọng — sai lệch lớn

| Lỗi | Sai như thế nào | Đã sửa |
|---|---|---|
| **Dư nợ và tỷ lệ quá hạn** *(17/07)* | Thổi phồng **4–15 lần** do tự dựng lại công thức tính nợ | Gọi thẳng thủ tục tính công nợ gốc của DNH |
| **KPI toàn công ty chỉ gồm 1 miền** *(29/07)* | Báo "toàn đội đạt 48,7%" trong khi chỉ là miền Trung — **thiếu 43,97 tỷ** chỉ tiêu 2 miền còn lại, **không hề báo lỗi** | Gộp theo tháng thay vì ghim một ngày; thêm cảnh báo bắt buộc khi thiếu miền |
| **Công nợ chatbot đọc nguồn cũ** *(27/07)* | Chatbot và báo cáo trả lời từ **2 nguồn khác nhau** — chatbot đọc bảng nhập tay không tự làm mới | Về chung một nguồn, chặn cứng đường quay lại ở 3 lớp |
| **Chỉ tiêu miền Nam hụt ~40%** *(23/07)* | Bỏ sót kênh Modern Trade khi tính chỉ tiêu vùng | Nhận diện đúng mã kênh MT |
| **KPI cộng trùng 2 lần** *(21/07)* | Cộng chồng tầng TDV và tầng QLV — mà QLV vốn đã là tổng của TDV | Chọn đúng một tầng, không cộng lẫn |

### Nhóm sai ngưỡng và phân loại

| Lỗi | Sai như thế nào | Đã sửa |
|---|---|---|
| **Ngưỡng đạt KPI** *(23/07)* | Hệ thống dùng 80% trong khi cấu hình thật của DNH là **65% (nhân viên) / 70% (quản lý)** | Sửa 5 chỗ; tách bạch 3 mốc: đạt chỉ tiêu ≥100%, đạt KPI ≥80%, tới mức thưởng nhóm hàng 65%/70% |
| **"Đạt chỉ tiêu N/M"** *(21/07)* | Đếm gộp cả nhân viên lẫn quản lý vào cùng mẫu số | Đếm riêng tầng nhân viên |
| **Chỉ tiêu vùng miền nhầm kênh** *(24/07)* | Mã kênh GT/MT bị hiểu nhầm thành OTC/ETC | Sửa ánh xạ mã kênh |
| **Chỉ tiêu KPI theo ngày lấy nhầm tháng** *(28/07)* | Lấy chỉ tiêu tháng khác làm chỉ tiêu tháng hiện tại | Giới hạn đúng trong tháng đang xét |
| **Đội của quản lý vùng xác định sai** *(23/07)* | Suy đoán theo mã vùng thay vì quan hệ quản lý thật; **mất hẳn doanh số 1 quản lý** | Dùng mã người quản lý thật từ Bravo |

### Nhóm tồn kho và cây doanh thu

| Lỗi | Sai như thế nào |
|---|---|
| **Tồn kho ETC sai đơn vị** *(17/07)* | Sai đơn vị tính và sai bản chất chỉ số vận tốc bán |
| **Ngưỡng hàng chậm luân chuyển** *(22/07)* | Đối chiếu lại với thủ tục tồn kho gốc, sửa cả kết luận về dữ liệu cận hạn |
| **Cây doanh thu thiếu kênh** *(28/07)* | Thiếu Kênh MT và Chợ sỉ; doanh thu theo vùng gộp nhầm OTC/ETC |

---

## B. Phân quyền — 11 lỗ hổng, tất cả do MCNA tự phát hiện

Không có lỗ hổng nào do khách báo. Đây là kết quả quy trình tự rà soát đã cam kết tại họp 16/07.

| Lỗ hổng | Hậu quả nếu không vá |
|---|---|
| **Quản lý vùng xem được doanh thu cả miền** *(28/07)* | Hỏi "doanh thu tháng này" nhận về số của **cả 10 đội** thay vì riêng đội mình |
| **Tự nâng quyền qua báo cáo chi phí AI** *(28/07)* | Quản lý vùng đọc được **lịch sử truy vấn toàn công ty** và tự nhận quyền Ban điều hành |
| **Quyền suy từ TÊN tài khoản** *(28/07)* | Tài khoản đặt tên `dnh.marketing` tự nhiên có quyền Ban điều hành |
| **Cảnh báo hằng ngày lộ mã khách vùng khác** *(17/07)* | Người vùng này thấy khách hàng vùng khác |
| **Email/Teams hiện doanh thu kênh ngoài phạm vi** *(17/07)* | Tài khoản chỉ phụ trách OTC vẫn thấy số ETC |
| **"Điểm nổi bật trong kỳ" rò cảnh báo kênh khác** *(17/07)* | Rò dữ liệu qua đường phụ ít ai để ý |
| **Phiên chat lẫn giữa các tài khoản** *(16/07)* | Hai người dùng chung trình duyệt có thể thấy hội thoại của nhau |
| **Bảng xếp hạng KPI lộ bản ghi không phải người** *(17/07)* | Bản ghi trùng lọt vào bảng vùng |
| Cùng nhóm *(23/07)* | Vá lỗ hổng phân quyền QLV phát hiện khi kiểm định trước Demo #1 |

**Nguyên tắc áp dụng:** *thà từ chối trả lời còn hơn lộ nhầm*. Hiện đã tạm chặn **9 báo cáo** với tài
khoản quản lý vùng — chờ DNH chốt phạm vi.

---

## C. Hạ tầng và độ ổn định — 11 việc

| Việc | Ý nghĩa |
|---|---|
| **Bỏ hẳn Supabase khỏi pipeline** *(21/07)* | Toàn bộ báo cáo/cảnh báo nay lấy thẳng từ Bravo — bớt một tầng có thể sai lệch |
| **Bỏ hẳn Telegram Bot** *(23/07)* | Kênh chat đã chuyển hoàn toàn sang web; Telegram là nguồn sinh tiến trình mồ côi gây gửi trùng |
| **Đồng bộ ghi trùng khi 2 tiến trình chạy chồng** *(21/07)* | Gộp thành thao tác nguyên tử |
| **Đồng bộ mất dữ liệu vĩnh viễn nếu Bravo lỗi giữa chừng** *(24/07)* | Lỗi âm thầm, nguy hiểm nhất trong nhóm này |
| **Lịch đồng bộ chạy mỗi 5 phút thay vì 60** *(23/07)* | Tải máy chủ cao vô ích |
| **Cảnh báo gửi trùng** *(21/07)* | |
| **Cảnh báo khi tiến trình đồng bộ treo** *(21/07)* | Thay vì im lặng trả số liệu cũ |
| **Nền tảng kiểm soát vận hành ETL** *(17/07)* | Nhật ký chạy và mốc đồng bộ, để truy được khi có sự cố |
| **Nén lịch sử hóa đơn cũ hơn 12 tháng** *(21/07)* | Giảm dung lượng, tăng tốc truy vấn |
| **Giới hạn 10 câu hỏi/phút/người** *(22/07)* | Kiểm soát chi phí API — đúng lo ngại nêu tại họp 16/07 |
| **Sự cố giao diện không cập nhật được 18 tiếng** *(29/07)* | Đã tìm ra nguyên nhân và xử lý dứt điểm |

---

## D. Chi phí AI — từ "không đo được" thành "đo được đến từng người"

Trước 24/07 hệ thống hoàn toàn không theo dõi chi phí. Nay có đủ chuỗi: đo → quy cho người → cảnh báo ngân sách.

| Mốc | Việc |
|---|---|
| 24/07 | Theo dõi và cảnh báo ngân sách theo tháng (đặt mức 50 USD) |
| 27/07 | Mỗi người xem được lịch sử truy vấn và chi phí **của chính mình** |
| 28/07 | **Bảng điều khiển Chi phí AI & Nhật ký truy vấn** cho Ban điều hành — xem trực tiếp trên web, không cần hỏi qua chatbot |
| 28–29/07 | Bóc tách **4 lớp lỗi tính tiền** chồng lên nhau |
| 29/07 | Cập nhật tỷ giá, gom về một nguồn duy nhất trong hệ thống |

### Bốn lớp lỗi tính tiền

| # | Lỗi | Biểu hiện |
|---|---|---|
| 1 | Cộng trùng | Một phiên 6 lượt hỏi bị tính tiền **6 lần** |
| 2 | Giấu mất phần lớn tiền | Tổng chỉ cộng phần quy được cho người dùng, phần còn lại biến mất |
| 3 | Không quy được cho ai | 89% chi phí không biết của ai |
| 4 | Bảng số không tự khớp | Cột tổng token và tổng tiền cộng tay không ra số hiển thị |

### Con số thật

| | |
|---|---|
| Chi phí 08/07 → 29/07 | **26,01 USD ≈ 685 nghìn đồng** |
| Nhịp hiện tại | ~1,18 USD ≈ **31 nghìn đồng/ngày** |
| Ước tính tháng | ~37 USD ≈ **965 nghìn đồng** |
| Sau 31/08 (hết khuyến mãi) | ~55 USD ≈ **1,45 triệu đồng/tháng** |
| Tỷ lệ dữ liệu vào/ra | **≈ 8,7 lần** — chi phí do phần nạp vào chi phối, không phải độ dài câu trả lời |

> ⚠️ Đây là mức **phát triển và kiểm thử của MCNA**, chưa phải vận hành thật 147 TDV. Con số go-live
> vẫn theo cam kết **tuần 8–10**.
>
> ⚠️ Mức sau 31/08 (~55 USD) **đã vượt ngân sách 50 USD/tháng** đang đặt — cần bàn.

---

## E. Báo cáo và giao diện

| Việc | Ngày |
|---|---|
| Tách ngưỡng nợ quá hạn riêng cho OTC và ETC | 16/07 |
| Phân biệt giao diện báo cáo Tuần / Tháng, chia theo tuần lịch thật | 16/07 |
| Bảng xu hướng doanh thu tự đối chiếu với tổng, ẩn nếu lệch | 16/07 |
| Đồng bộ mốc tuổi nợ 1-15 / 15-30 / 30-45 / >45 giữa chatbot và cảnh báo | 16/07 |
| Đổi màu thương hiệu DNH (xanh lá + cam) + logo cho email và Teams | 20/07 |
| Thêm **Chi tiết KPI theo Vùng – QLV – TDV** | 21/07 |
| Thêm doanh số ETC theo nhân viên | 21/07 |
| Cấm chatbot in tên trường kỹ thuật và tên hàm ra câu trả lời | 23–24/07 |
| **Làm lại toàn bộ giao diện chatbot** theo bộ nhận diện Dược Nam Hà | 29/07 |
| Lịch sử trò chuyện nhóm theo thời gian + lọc theo người dùng | 29/07 |

---

## F. Kiểm chứng và tài liệu nghiệp vụ

| Việc | Kết quả |
|---|---|
| **Kiểm chứng trọn bộ Demo #1** *(29/07)* | **17/17 câu đạt** trên hệ thống thật, đủ 3 vai trò |
| Công cụ sinh đáp án đối chiếu độc lập *(22, 28/07)* | Cho phép so từng câu trả lời của chatbot với số gốc |
| Kịch bản Demo #1 + bộ đáp án *(23, 27, 28/07)* | Tài liệu sống, cập nhật theo từng bản vá |
| Chính sách thu nhập TDV OTC 3 miền *(24/07)* | Đưa công thức chính thức vào hệ thống; xác nhận chưa áp dụng cho tháng 7 |
| Lưu định nghĩa view gốc Bravo *(16/07)* | Tài liệu tham chiếu, tránh tự suy diễn công thức |
| Đối chiếu doanh thu KPI với hóa đơn thực tế *(16/07)* | |

---

## Hai chênh lệch treo từ họp 16/07 — đã đóng cả hai

| Chênh lệch | Kết luận |
|---|---|
| **1,75 tỷ** (chỉ tiêu miền Bắc) | **Không phải lỗi** — là chỉ tiêu cá nhân của các quản lý vừa quản đội vừa phụ trách địa bàn. Kiểm chứng khớp **0 đồng** cả 3 miền, bền qua **7 tháng liên tiếp** |
| **1,13 tỷ** (chỉ tiêu một quản lý) | Chính là lỗi chỉ tiêu KPI theo ngày lấy nhầm tháng, đã sửa |

---

## Năm việc cần DNH chốt

| # | Việc | Vì sao gấp |
|---|---|---|
| 1 | **Phạm vi xem của quản lý vùng** — đội mình hay cả miền? Tồn kho và công nợ có thuộc quyền họ không? | Đang tạm chặn 9 báo cáo. Chưa chốt thì Demo #1 không trình bày được vai quản lý vùng |
| 2 | **Cấp tài khoản cho 1–2 quản lý vùng tự nghiệm thu** | Đã nêu từ 16/07, vẫn chờ. Không có bước này thì sai lệch chỉ lộ ở nghiệm thu tháng 9 |
| 3 | **Hai nhân viên có thể đang bị tính thiếu lương** | Cờ dữ liệu sai tác động vào chính thủ tục tính lương của DNH |
| 4 | **Xác nhận văn bản chính sách lương áp dụng cho tháng 7** | Có 2 phiên bản cùng tồn tại; cấu hình hệ thống thật nghiêng về bản mới |
| 5 | 🆕 **`TM26060104` — Nguyễn Văn Dũng (NTH01)**: có doanh số **4.952.381đ** nhưng chỉ tiêu tháng = **0** | Đang bán hàng thật mà không được đo KPI, không xuất hiện trong mọi thống kê. Phát hiện 29/07 khi kiểm số ở Lớp 4 |

---

## Câu chốt gợi ý cho slide

> Hai tuần qua tập trung vào **độ tin cậy của con số**: 13 lỗi số liệu được tìm ra và sửa, 11 lỗ hổng
> phân quyền do MCNA tự phát hiện và tự vá, chi phí AI từ chỗ không đo được nay quy được đến từng
> người dùng, và toàn bộ 17 câu hỏi Demo #1 đã kiểm chứng trên hệ thống thật.
>
> Điều đáng chú ý: **không lỗi nào trong số này do khách báo** — tất cả đều phát hiện qua quy trình tự
> rà soát trước khi đưa cho khách, đúng như cam kết tại buổi họp 16/07.
