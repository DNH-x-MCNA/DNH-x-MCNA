# BÁO CÁO TIẾN ĐỘ — Dự án Dược Nam Hà (DNH)
### Tuần 27/07 – 31/07/2026 · Tuần T5/14 · Đơn vị thực hiện: MCNA
*(Số liệu chốt đến 28/07; chạy lại trước buổi báo cáo 30/07 để lấy số mới nhất)*

---

# TRANG 1/4 — Việc đã làm (Người thực hiện: Lê Việt Đặng)

*Trọng tâm tuần: đưa công nợ trên chatbot về đúng nguồn, tìm và sửa các lỗi còn sót ảnh hưởng trực
tiếp tới đánh giá nhân viên, và bịt hai lỗ hổng phân quyền.*

### A. Công nợ trên chatbot — đã về cùng một nguồn với báo cáo ⭐ *(trọng tâm tuần)*

Đây là rủi ro lớn nhất còn lại từ tuần trước: **chatbot và báo cáo trả lời công nợ từ hai nguồn khác
nhau**. Chatbot đọc bảng dữ liệu nhập tay một lần từ đầu dự án, không tự làm mới — chính nguồn đó
từng báo nợ một khách **9,17 tỷ** trong khi thực tế là **0,61 tỷ**.

Đã chuyển chatbot sang đọc **trực tiếp báo cáo công nợ gốc của DNH**, cùng nguồn mà báo cáo định kỳ
đang dùng.

| Kiểm chứng | Kết quả |
|---|---|
| Đối chiếu chatbot ↔ báo cáo gốc | ✅ **Lệch 0 đồng** (180,48 tỷ dư nợ · 77,07 tỷ quá hạn) |
| Số dòng dữ liệu | 9.787 khách hàng × kênh |
| Trường hợp cụ thể (BV Đa khoa Đồng Tháp) | ✅ Ra số cụ thể, trước đây báo "chưa có dữ liệu" |

Đồng thời **chặn cứng đường quay lại nguồn cũ** ở ba lớp, để không thể vô tình đọc nhầm về sau.

**→ Câu hỏi công nợ nay đã đủ tin cậy để đưa vào Demo #1.** Đây là câu ban lãnh đạo chắc chắn hỏi —
tránh được ở demo nhưng không tránh được ở nghiệm thu tháng 9.

### B. Lỗi ảnh hưởng trực tiếp tới đánh giá nhân viên

**1. Chỉ tiêu tháng bị lấy nhầm của tháng khác.** Khi xem doanh số theo từng ngày của một nhân viên,
hệ thống lấy **chỉ tiêu cao nhất trong 3 tháng gần nhất** thay vì chỉ tiêu của đúng tháng đang xem.

Hậu quả trên một nhân viên thật (tháng 7): chỉ tiêu bị lấy **343,7 triệu** (của tháng 4) thay vì
**302,2 triệu** thực tế.

| | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Mức hoàn thành tháng | 65,2% | **74,1%** |
| Số ngày bị chấm Đỏ | 11 | **10** |
| Số ngày Xanh | 4 | **6** |

Nhân viên này bị báo thấp hơn thực tế **9 điểm phần trăm**, và 3 ngày bị chấm màu xấu oan. Lỗi áp
dụng cho **mọi nhân viên bán hàng**, không riêng trường hợp này.

**2. Truy ra nguyên nhân hai chênh lệch số liệu còn treo từ tuần trước** — cả hai nay đã đóng:
- **1,75 tỷ** (chỉ tiêu miền Bắc): không phải lỗi. Đó là phần chỉ tiêu cá nhân của các quản lý vùng
  vừa quản đội vừa tự phụ trách địa bàn — hoàn toàn hợp lệ. Kiểm chứng khớp báo cáo gốc **0 đồng** ở
  cả 3 miền, bền qua 7 tháng liên tiếp.
- **1,13 tỷ** (chỉ tiêu một quản lý vùng): chính là lỗi ở mục 1 trên.

### C. Bảo mật — phát hiện và bịt hai lỗ hổng phân quyền

**1. Quản lý vùng xem được doanh thu toàn miền.** Tài khoản quản lý vùng hỏi *"doanh thu tháng này"*
nhận về doanh thu **cả miền Bắc** (tổng 10 đội), thay vì riêng đội mình. Nguyên nhân: lớp bảo vệ dựng
tuần trước chỉ phủ nhóm báo cáo KPI, bỏ sót nhóm doanh thu, khách hàng, tồn kho, công nợ.

Đã chặn 9 báo cáo với tài khoản quản lý vùng theo nguyên tắc **thà từ chối còn hơn lộ nhầm**.

**2. Có thể tự nâng quyền qua báo cáo chi phí AI.** Tính năng mới cho ban điều hành xem chi phí toàn
công ty có sơ hở: danh tính và vai trò người dùng do phần AI tự khai, không phải máy chủ quyết định.
Kiểm chứng bằng thử nghiệm thật cho thấy một tài khoản quản lý vùng có thể đọc lịch sử của người khác
và xem được số liệu toàn công ty.

Đã sửa để **máy chủ luôn là bên quyết định danh tính và quyền hạn**. Cũng bỏ cách nhận diện quyền
theo *tên* tài khoản — cách cũ khiến chỉ cần đặt tên tài khoản gần giống lãnh đạo là có quyền xem chi
phí toàn công ty.

### D. Chi phí vận hành AI — lần đầu đo được

Trước đây hệ thống có ghi nhận chi phí nhưng **không nối được với người dùng**, nên mọi báo cáo đều
hiện 0 đồng. Đã sửa và bắt đầu có số thật.

- **Tỷ lệ dữ liệu vào/ra ≈ 8,7 lần** — chi phí bị chi phối bởi phần dữ liệu nạp vào (mô tả cấu trúc
  dữ liệu + lịch sử hội thoại), không phải độ dài câu trả lời. Đây là chỗ cần tối ưu nếu muốn giảm giá.
- ⚠️ **Giá dịch vụ AI tăng ~50% sau 31/08/2026** — bản ước tính chi phí go-live phải dùng giá sau
  khuyến mãi, nếu không sẽ báo thiếu.

Cần thêm vài ngày dữ liệu đầy đủ mới đưa ra được đơn giá tin cậy cho mỗi lượt hỏi.

### E. Chuẩn bị Demo #1 (09/08)

- **Sửa lỗi có thể làm hỏng buổi demo**: công cụ sinh đáp án đối chiếu mặc định tính "tháng này" =
  tháng đang chạy. Chạy sáng 09/08 sẽ ra số của tháng 8 mới 9 ngày, không đối chiếu được với câu hỏi
  demo (vốn hỏi về tháng 7). Đã bổ sung tùy chọn ghim kỳ.
- **Bổ sung 2 đáp án còn trống**: top khách hàng theo vùng, và tồn kho theo vùng. Riêng tồn kho là
  **lần đầu tiên** số liệu của chatbot được đối chiếu độc lập với hệ thống nguồn.
- Bổ sung mốc đánh giá 70% cho cấp quản lý (trước chỉ có mốc 65% của nhân viên).

### F. Quản lý mã nguồn

Hợp nhất hai kho mã nguồn từng tồn tại song song thành một, sau khi phát hiện mỗi bên đều có phần
việc riêng chưa được đồng bộ — tránh nguy cơ mất công sức hoặc chạy nhầm phiên bản.

---

# TRANG 2/4 — Việc đã làm (Người thực hiện: Triệu Đặng)

### A. Bảng điều khiển Chi phí AI & Nhật ký truy vấn cho Ban điều hành ⭐

Xây dựng màn hình riêng cho cấp lãnh đạo, xem được **không cần hỏi qua chatbot**:
- Toàn bộ lịch sử câu hỏi của mọi nhân viên, dạng dòng thời gian
- Chi phí AI toàn công ty, quy đổi sẵn ra tiền Việt
- Lọc theo từng người dùng

Đi kèm phân quyền: nhân viên và quản lý vùng chỉ xem được lịch sử và chi phí **của chính mình**.

### B. Sửa lỗi số liệu

1. **Cây doanh thu miền Nam thiếu hai đơn vị** — "Kênh MT" và "Chợ sỉ" không hiện trong danh sách
   quản lý vùng do cách tổ chức dữ liệu khác các đội thường. Đã dùng chung cách xác định với báo cáo
   xếp hạng để hai nơi luôn ra cùng một tổng.
2. **Doanh thu theo vùng không tách được kênh** — trước đây luôn gộp OTC + ETC. Phát hiện khi đối
   chiếu: riêng ETC miền Nam lên tới 18,76 tỷ (do một vài bệnh viện/gói thầu lớn), khiến câu hỏi
   "doanh thu OTC theo vùng" có thể bị thổi phồng ~4 lần nếu không tách.
3. **Sửa 5 lỗi trong luồng xử lý dữ liệu** phát hiện qua rà soát.
4. **Khôi phục bước nạp cấu hình bị mất** khi viết lại phần máy chủ cho bảng điều khiển mới — thiếu
   bước này khiến chatbot lỗi ngay ở câu hỏi đầu tiên.

### C. Vận hành

- Đồng bộ bảng giá dịch vụ AI theo đúng biểu giá hiện hành và biểu giá sau 31/08.
- Kết nối lại cơ chế tự động cập nhật giao diện web sau khi liên kết cũ bị đứt.

---

# TRANG 3/4 — Việc đang làm, sắp tới & trạng thái

| Việc | Trạng thái | Mốc/Ghi chú |
|---|---|---|
| Công nợ trên chatbot | ✅ **Xong** | Khớp báo cáo gốc 0 đồng, đã chạy trên hệ thống thật |
| Hai chênh lệch số liệu tồn từ tuần trước | ✅ **Đóng cả hai** | 1,75 tỷ: không phải lỗi · 1,13 tỷ: đã sửa |
| Bịt lỗ hổng phân quyền (2 lỗ hổng mới) | ✅ **Xong** | Đã kiểm chứng trên hệ thống thật |
| Bảng điều khiển Chi phí AI cho Ban điều hành | 🟡 Đang làm | Phần máy chủ đã xong; phần giao diện chờ cập nhật lần cuối |
| Chuẩn bị Demo #1 Chatbot | 🟡 Đang làm | Kịch bản 17 câu theo 3 vai trò + đáp án đối chiếu đã sẵn sàng; đang chạy kiểm chứng từng câu. **Hạn 09/08** |
| Đo chi phí vận hành AI | 🟡 Đang làm | Đã đo được số đầu tiên; cần thêm vài ngày dữ liệu để ra đơn giá. **Cam kết hoàn thành tuần 8–10** |
| Nghiệm thu theo lớp cùng khách | ⚪ **Chờ khách** | MCNA đã tự kiểm xong; chờ cấp tài khoản cho quản lý vùng để tự kiểm tra |
| Chốt các điểm nghiệp vụ còn treo | ⚪ **Chờ khách** | Xem Trang 4 |

**Trọng tâm tuần tới (T6 · 03/08 – 07/08):** chạy kiểm chứng trọn bộ kịch bản Demo #1 trên cả 3 vai
trò, hoàn tất ước tính chi phí AI, và tổng duyệt trước ngày 09/08.

---

# TRANG 4/4 — Điểm nghẽn & giải pháp

| # | Điểm nghẽn | Mức | Giải pháp / Đề nghị |
|---|---|---|---|
| 1 | **Quyền xem của quản lý vùng chưa được chốt** — hiện đã chặn 9 báo cáo với tài khoản quản lý vùng để an toàn, nhưng như vậy họ chưa hỏi được về doanh thu, tồn kho, công nợ | 🔴 Cao | **Đề nghị DNH chốt trước 09/08**: quản lý vùng được xem số liệu ở phạm vi *đội của mình* hay *cả miền*? Riêng tồn kho và công nợ có thuộc quyền xem của họ không? |
| 2 | **Nhiều điểm nghiệp vụ chưa được DNH chốt** (mốc tuổi nợ, nguồn giá tồn kho, ngưỡng cảnh báo...) → số liệu còn dùng giả định | 🔴 Cao | Danh sách đầy đủ kèm bằng chứng đã gửi; **đề nghị họp chốt các điểm ưu tiên trước Demo #1** |
| 3 | **Chưa có nghiệm thu từng lớp từ khách** → sai lệch (nếu có) sẽ phát hiện muộn | 🔴 Cao | **Đề nghị khách cấp tài khoản cho quản lý vùng** để tự kiểm tra số liệu của mình |
| 4 | **Hạ tầng vận hành còn mong manh** — đường kết nối giữa giao diện web và máy chủ đổi địa chỉ mỗi lần khởi động lại, phải sửa tay; nhật ký lỗi bị ghi đè nên khó truy nguyên nhân sự cố | 🟠 TB | Đã ghi nhận đầy đủ; **đề nghị xử lý dứt điểm trước 09/08** để tránh rủi ro chatbot gián đoạn giữa buổi demo |
| 5 | **2 nhân viên có thể đang bị tính thiếu lương** do dữ liệu gốc đánh dấu sai | 🟠 TB | Đã vá tạm ở tầng hệ thống; **đề nghị DNH đối chiếu với bộ phận lương/kế toán và sửa dữ liệu gốc** |
| 6 | **Chi phí AI sẽ tăng ~50% sau 31/08/2026** do hết giai đoạn khuyến mãi của nhà cung cấp | 🟠 TB | Bản ước tính go-live sẽ dùng **giá sau khuyến mãi**; đang tối ưu phần dữ liệu nạp vào để giảm chi phí |
| 7 | **Có 2 phiên bản văn bản chính sách lương cùng tồn tại** | 🟡 Thấp | Đã đối chiếu với cấu hình hệ thống tính lương thật của DNH; **đề nghị DNH xác nhận chính thức** |

---

## Số liệu hệ thống *(tháng 7/2026, đến 28/07 — đã kiểm định, lệch 0 đồng với nguồn gốc)*

| Chỉ số | Giá trị |
|---|---|
| Doanh thu OTC | 26,51 tỷ đ (7.580 hóa đơn) |
| Doanh thu ETC | 33,09 tỷ đ (774 hóa đơn) |
| **Tổng doanh thu** | **59,59 tỷ đ** |
| Tổng dư nợ | 180,48 tỷ đ |
| Nợ quá hạn | 77,07 tỷ đ (42,7%) |
| Đạt chỉ tiêu tháng (≥100%) | 8/147 |
| Đạt KPI (≥80%) | 24/147 |
| Tới mức thưởng nhóm hàng (≥65%) | 50/147 |
| Mức hoàn thành theo miền | Bắc 53,5% · Nam 50,2% · Trung 47,1% — toàn đội **51,8%** |

> ⚠️ Tháng 7 còn 3 ngày chưa kết thúc — các con số "đạt chỉ tiêu" so lũy kế đến nay với chỉ tiêu
> **cả tháng**, nên tự nhiên thấp. Số cuối tháng sẽ cao hơn đáng kể.

---

*Thông điệp xuyên suốt tuần: chuyển từ **kiểm định số liệu** sang **bịt các lỗ hổng còn sót**. Ba
nhóm lỗi tìm được tuần này đều thuộc loại không tự lộ ra khi nhìn báo cáo — một lỗi chấm sai kết quả
làm việc của nhân viên, hai lỗ hổng cho phép xem dữ liệu ngoài phạm vi. Đây chính là loại rủi ro mà
nếu để tới lúc nghiệm thu mới phát hiện thì rất khó xử lý.*
