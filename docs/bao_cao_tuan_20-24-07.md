# BÁO CÁO TUẦN — Dự án Dược Nam Hà (DNH)
### Tuần 20/07 – 24/07/2026 · Tuần T4/14 · Đơn vị thực hiện: MCNA

---

# TRANG 1/4 — Việc đã làm (Người thực hiện: Lê Việt Đặng)

*Phụ trách chính pipeline báo cáo/cảnh báo và chatbot tuần này — toàn bộ sửa lỗi số liệu, bảo mật, và chuẩn hóa chính sách lương thưởng.*

### A. Kiểm định độ chính xác dữ liệu theo 4 lớp ⭐ *(trọng tâm tuần)*

Kiểm từ dưới lên — cá nhân → quản lý → vùng → toàn công ty:

| Lớp | Phạm vi kiểm | Kết quả |
|---|---|---|
| Cá nhân | Doanh số từng nhân viên bán hàng | ✅ Đúng |
| Quản lý | Tổng đội từng quản lý vùng | ✅ Khớp tuyệt đối |
| Vùng | Doanh thu & công nợ theo miền | ✅ Lệch 0 đồng |
| Toàn công ty | Doanh thu, công nợ, KPI, tồn kho | ✅ Khớp hóa đơn gốc |

**→ 15/15 hạng mục đạt.**

### B. Lỗi số liệu phát hiện & sửa

1. **Doanh số bị tính gấp đôi trong KPI** — chỉ tiêu/doanh số của nhân viên và quản lý là hai cách nhìn của *cùng* một khoản doanh thu, từng bị cộng gộp làm một. Phát hiện qua tổng KPI (4,45 tỷ) cao hơn cả doanh thu hóa đơn thật (3,32 tỷ) — bất khả thi. Sửa còn 2,27 tỷ.
2. **Chatbot trả lời doanh thu gấp đôi thực tế** — 5,09 tỷ thay vì 2,54 tỷ, do hai tiến trình đồng bộ chạy chồng nhau ghi trùng dữ liệu. Đã sửa cả triệu chứng lẫn gốc rễ.
3. **Cảnh báo gửi trùng hai lần** — tiến trình tự khởi động lại trùng đúng chu kỳ quét theo lịch. Đã thêm cơ chế khóa chống trùng.
4. **Công nợ báo sai lệch lớn** — công thức cũ đọc nhầm cột dữ liệu, có trường hợp báo nợ 9,17 tỷ trong khi thực tế 0,61 tỷ. Chuyển sang gọi trực tiếp báo cáo gốc của DNH.

### C. Chuẩn hóa lương thưởng theo văn bản chính sách của DNH

- **Xác định ngưỡng thật theo từng vai trò** (trước là số tự đặt không căn cứ): nhân viên bán hàng 65%, cấp quản lý 70% — đối chiếu trực tiếp bảng cấu hình mà hệ thống tính lương của DNH đang dùng. Tháng 7 đổi từ 10/147 lên **27/147** nhân viên tới mức thưởng.
- **Tách bạch "đạt chỉ tiêu" (≥100%) khỏi "tới mức thưởng" (65-70%)** — hai khái niệm khác nhau từng bị gộp làm một, khiến báo cáo tự mâu thuẫn. Nay cả báo cáo lẫn chatbot nêu rõ cả hai.
- **Phát hiện 2 nhân viên có thể bị tính thiếu lương** — dữ liệu gốc đánh dấu nhầm là "trùng lặp", khiến doanh số biến mất khỏi mọi báo cáo. Đã đề nghị DNH đối chiếu bộ phận lương/kế toán.

### D. Bảo mật & chất lượng chatbot

- **Bịt lỗ hổng phân quyền** — tài khoản quản lý vùng từng xem được hiệu suất cá nhân của đội khác. Đã chặn triệt để, đúng cam kết họp 16/07.
- Chatbot không còn kết luận sai kiểu "nhân viên không được thưởng" khi chỉ dưới một mốc trong nhiều loại thưởng.
- Không còn lộ tên hàm/công cụ kỹ thuật ra câu trả lời cho người dùng.
- Phân biệt đúng "Kênh MT" (kênh bán hàng hiện đại) với vùng Miền Trung — tránh nhầm lẫn khi báo cáo.

### E. Hạ tầng & vận hành

- Chuyển toàn bộ báo cáo/cảnh báo sang đọc trực tiếp hệ thống nguồn của DNH, bỏ lớp lưu trữ trung gian.
- Bỏ hẳn kênh chat Telegram (đã chuyển hoàn toàn qua web) ở cả hai hệ thống.
- Rà soát và đưa vào quản lý phiên bản chính thức toàn bộ phần việc do đồng nghiệp phát triển trực tiếp trên máy chủ (xem Trang 2) — đảm bảo không mất công sức nếu máy chủ gặp sự cố.

---

# TRANG 2/4 — Việc đã làm (Người thực hiện: Triệu Đặng)

*Đóng góp đầu tuần cho pipeline báo cáo, cộng với một phần việc phát triển trực tiếp trên máy chủ chatbot, được rà soát và đưa vào quản lý phiên bản chính thức trong tuần này.*

### A. Sửa lỗi dữ liệu (20/07)

- **Sửa cột xác định nhân viên trên hóa đơn** — hệ thống từng dùng nhầm cột, dẫn tới gán sai doanh số cho nhân viên bán hàng ở một số trường hợp. Đã xác định đúng cột chuẩn.
- **Bổ sung tra cứu tên nhân viên dự phòng** — một số nhân viên thiếu tên trong danh mục chính, hệ thống nay tự động tra cứu từ nguồn dự phòng thay vì hiển thị mã trống.

### B. Tính năng mới

- **Tách riêng doanh thu "Kênh MT"** (kênh bán hàng hiện đại — chuỗi nhà thuốc lớn) trong báo cáo Miền Nam — trước đây gộp chung, không thấy được đóng góp riêng của kênh này.

### C. Phần việc phát triển trực tiếp trên máy chủ chatbot *(đưa vào quản lý phiên bản chính thức 24/07)*

Trong quá trình vận hành, một phần logic đã được bổ sung trực tiếp trên máy chủ để xử lý nhanh các yêu cầu phát sinh, chưa kịp đưa vào hệ thống quản lý phiên bản dùng chung. Tuần này đã rà soát và gộp lại an toàn:

- **Công cụ đối chiếu doanh thu** — so sánh doanh thu tính từ trên xuống (tổng hóa đơn toàn vùng) với cộng dồn từ dưới lên (từng nhân viên → quản lý → vùng), giúp phát hiện sớm nếu hai cách tính lệch nhau.
- **Nén dữ liệu hóa đơn cũ hơn 12 tháng** — giảm dung lượng lưu trữ và giảm rủi ro lộ dữ liệu chi tiết hóa đơn, trong khi vẫn giữ đủ số liệu tổng hợp theo khách hàng/tháng để tra cứu khi cần.
- Mở rộng thêm khả năng nhận diện "Kênh MT" cho chatbot, nối tiếp tính năng đã làm ở mục B.

*⚠️ Lưu ý quy trình: phần việc mục C từng chỉ tồn tại trên máy chủ, không có bản sao lưu trữ nào khác — rủi ro mất trắng nếu máy chủ gặp sự cố. Đã xử lý xong trong tuần này, không còn tồn đọng.*

---

# TRANG 3/4 — Việc đang làm, sắp tới & trạng thái

| Việc | Trạng thái | Mốc/Ghi chú |
|---|---|---|
| Chuẩn bị Demo #1 Chatbot | 🟡 Đang làm | Đã có kịch bản 23 câu hỏi theo 3 vai trò + bộ đáp án đối chiếu; đang chạy thử toàn bộ và rà lỗi. **Hạn 09/08** |
| Rà soát các tiện ích/script viết trực tiếp trên máy chủ | 🟡 Đang làm | Kiểm tra an toàn thông tin trước khi quyết định giữ lại hay loại bỏ từng phần |
| Đối chiếu văn bản chính sách lương thưởng còn thiếu | 🟡 Đang làm | Đã có chính sách nhân viên bán hàng & quản lý vùng cả 3 miền; còn thiếu văn bản một số chức danh phát sinh ít nhân sự — đang chờ bổ sung |
| Đo chi phí vận hành AI | ⚪ Chưa bắt đầu | Phục vụ ước tính chi phí go-live. **Cam kết hoàn thành tuần 8–10** |
| Nghiệm thu theo lớp cùng khách | ⚪ Chờ khách | MCNA đã tự kiểm xong 4 lớp (Trang 1, mục A); chờ khách khảo sát + cấp tài khoản quản lý vùng để tự kiểm tra |
| Dọn dẹp hạ tầng máy chủ tồn đọng | ⚪ Việc nhỏ | Một vài thư mục sao lưu cũ không còn cần thiết — chưa ưu tiên |

**Trọng tâm tuần tới (T5 · 27/07 – 31/07):** hoàn tất chuẩn bị Demo #1, bắt đầu đo chi phí AI, và đề nghị khách chốt các điểm nghiệp vụ ưu tiên (xem Trang 4).

---

# TRANG 4/4 — Điểm nghẽn & giải pháp

| # | Điểm nghẽn | Mức | Giải pháp / Đề nghị |
|---|---|---|---|
| 1 | **Nhiều điểm nghiệp vụ chưa được DNH chốt** (ngưỡng thưởng, mốc tuổi nợ, nguồn giá tồn kho...) → số liệu còn dùng giả định, có thể phải làm lại nếu sai | 🔴 Cao | Đã soạn danh sách đầy đủ kèm bằng chứng số liệu cho từng điểm; **đề nghị họp chốt các điểm ưu tiên trước Demo #1 (09/08)** |
| 2 | **Chưa có nghiệm thu từng lớp từ khách** → nếu có sai lệch sẽ phát hiện muộn | 🔴 Cao | MCNA đã tự kiểm xong 4 lớp; **đề nghị khách cấp tài khoản cho quản lý vùng** để tự kiểm tra dữ liệu của mình |
| 3 | **2 nhân viên có thể đang bị tính thiếu lương** do dữ liệu gốc đánh dấu sai | 🟠 TB | Đã vá tạm ở tầng hệ thống (không ảnh hưởng báo cáo); **đề nghị DNH đối chiếu với bộ phận lương/kế toán và sửa dữ liệu gốc** |
| 4 | **Có 2 phiên bản văn bản chính sách lương cùng tồn tại** — cần xác nhận tháng 7 áp dụng bản nào | 🟠 TB | Đã đối chiếu với cấu hình hệ thống tính lương thật của DNH (cho thấy nghiêng về bản mới, hiệu lực 01/07); **đề nghị DNH xác nhận chính thức** để loại trừ rủi ro sai lệch |
| 5 | **Chi phí AI chưa rõ khi nhiều người dùng đồng thời** | 🟠 TB | Đã áp giới hạn số câu hỏi/phút mỗi người dùng để kiểm soát rủi ro trước mắt; đang đo số liệu thực tế để ước tính chi phí |
| 6 | **Một số phần việc từng chỉ tồn tại trên máy chủ**, chưa qua kiểm tra an toàn thông tin | 🟡 Thấp | Đã đưa vào quản lý phiên bản chính thức trong tuần này; đang rà soát an toàn thông tin trước khi hoàn tất |

---

## Số liệu hệ thống *(tháng 7/2026, đến 22/07 — đã kiểm định)*

| Chỉ số | Giá trị |
|---|---|
| Doanh thu OTC | 16,97 tỷ đ (5.535 hóa đơn) |
| Doanh thu ETC | 25,71 tỷ đ (629 hóa đơn) |
| **Tổng doanh thu** | **42,68 tỷ đ** (+5,4% so kỳ trước) |
| Tổng dư nợ | 180,06 tỷ đ |
| Nợ quá hạn | 81,48 tỷ đ (45,3%) |
| Nhân viên tới mức thưởng doanh số (OTC) | 27/147 |
| Quy mô đội ngũ | OTC ~150 nhân viên + ~20 quản lý · ETC 277 nhân sự |

---

*Thông điệp xuyên suốt tuần: trọng tâm là **tính chính xác của số liệu** — phương pháp kiểm theo lớp đã giúp tìm và sửa nhiều lỗi thật mà nếu để lâu sẽ rất khó phát hiện, đặc biệt các lỗi chạm tới lương thưởng của nhân viên.*
