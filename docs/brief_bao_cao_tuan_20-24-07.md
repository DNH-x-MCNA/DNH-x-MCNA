# BRIEF — Dựng báo cáo tuần dự án DNH (tuần 20/07 – 24/07/2026)

> **Cách dùng**: copy TOÀN BỘ file này đưa cho Claude. File tự chứa đủ bối cảnh + số liệu, người
> nhận không cần truy cập mã nguồn hay cơ sở dữ liệu.
>
> ⚠️ **Soạn ngày 22/07 (thứ Tư)** — phần việc 20–22/07 là ĐÃ LÀM XONG; phần 23–24/07 là KẾ HOẠCH.
> Nếu dựng báo cáo vào cuối tuần, cần cập nhật lại mục "Kế hoạch còn lại" thành việc đã làm thật.

---

## PHẦN 1 — Bối cảnh

**Dự án**: MCNA xây dựng cho Dược Nam Hà (DNH) hệ thống cảnh báo kinh doanh + báo cáo định kỳ +
AI chatbot nội bộ. Thời gian: 01/07 – 30/09/2026 (14 tuần).

**Tuần báo cáo**: 20/07 – 24/07/2026 — tuần **T4** trong khung 14 tuần.

**Bối cảnh quan trọng của tuần này**: mốc **M1 (Dữ liệu + AI Engine sẵn sàng) hạn 19/07** vừa kết
thúc ngay trước tuần này. Vì vậy trọng tâm cả tuần là **kiểm định lại toàn bộ độ chính xác số liệu**
trước khi bàn giao nghiệm thu, thay vì làm thêm tính năng mới — đúng chỉ đạo của khách tại họp 16/07
("dừng thêm tính năng, tập trung tính chính xác và tính mở rộng của dữ liệu").

**Giọng văn**: tiếng Việt, chuyên nghiệp, ngắn gọn, hướng kết quả. Nêu số liệu cụ thể thay vì nói
chung chung. **Không dùng thuật ngữ kỹ thuật** (không nói "commit", "refactor", "JOIN", "stored
procedure") — diễn đạt theo ngôn ngữ nghiệp vụ.

---

## PHẦN 2 — Việc ĐÃ LÀM trong tuần (20/07 – 22/07)

### A. Kiểm định độ chính xác dữ liệu theo 4 lớp ⭐ *(trọng tâm của tuần)*

Kiểm **từ dưới lên** — cá nhân → quản lý → vùng → toàn công ty — vì lỗi ở lớp dưới sẽ lan lên trên.
Đây là đúng mô hình kiểm tra khách hàng yêu cầu tại họp 16/07.

| Lớp | Phạm vi kiểm | Kết quả |
|---|---|---|
| Lớp 4 — Cá nhân | Doanh số từng nhân viên bán hàng | ✅ Đúng |
| Lớp 3 — Quản lý | Tổng đội từng quản lý vùng | ✅ Khớp tuyệt đối tổng nhân viên dưới quyền |
| Lớp 2 — Vùng | Doanh thu & công nợ theo miền | ✅ Khớp tổng, **lệch 0 đồng** |
| Lớp 1 — Toàn công ty | Doanh thu, công nợ, KPI, tồn kho | ✅ Khớp hóa đơn gốc |

**→ 15/15 hạng mục đạt, sai lệch 0 đồng ở mọi ranh giới giữa các lớp.**

### B. Bốn lỗi số liệu thật phát hiện & sửa nhờ đợt kiểm định này

**B1. Doanh số bị cộng trùng gấp đôi trong báo cáo KPI.**
Chỉ tiêu và doanh số của nhân viên (TDV) và của quản lý (QLV) bị cộng gộp làm một — trong khi đây là
**hai cách nhìn của cùng một khoản doanh thu**, không phải hai phần cộng dồn.
*Cách phát hiện*: tổng doanh số KPI (4,45 tỷ) cao hơn cả doanh thu hóa đơn thật của kênh (3,32 tỷ) —
điều không thể xảy ra. Sau sửa còn **2,27 tỷ**, hợp lý.
*Lỗi tương tự ở phép đếm*: mục "Đạt chỉ tiêu N/M" đếm gộp cả hai cấp (vd "0/36" = 31 nhân viên +
5 quản lý) — nay đếm đúng tầng nhân viên ("0/31").

**B2. Chatbot trả lời doanh thu gấp đôi thực tế.**
Khách hỏi doanh số ngày 20/07, chatbot trả **5,09 tỷ** trong khi thực tế là **2,54 tỷ**. Truy ra
nguyên nhân: **hai tiến trình đồng bộ dữ liệu chạy chồng lên nhau**, ghi trùng mọi dòng.
Đã xử lý cả triệu chứng lẫn gốc rễ — nay chatbot **khớp Bravo lệch 0 đồng**.

**B3. Cảnh báo gửi trùng hai lần.**
Cùng một cảnh báo được gửi hai lần liên tiếp. Nguyên nhân: tiến trình bị lỗi và tự khởi động lại,
trùng đúng lúc chu kỳ quét theo lịch — cả hai cùng gửi. Đã bổ sung cơ chế khóa chống trùng.

**B4. Mục "Điểm nổi bật trong kỳ" trống oan ở báo cáo theo vùng**, trong khi vẫn hiện dòng chữ
"kỳ này có cảnh báo nghiêm trọng" — tức hệ thống *hứa* có nội dung nhưng không hiện gì. Đã bổ sung
gắn vùng cho từng cảnh báo để hiện đúng.

### C. Hai mục báo cáo mới *(phục vụ nghiệm thu theo lớp)*

- **"Chi tiết KPI theo Vùng – Quản lý – Nhân viên"** trong báo cáo tuần/tháng — thể hiện đúng mô
  hình 4 lớp; trưởng kênh thấy được từng vùng, quản lý vùng thấy từng quản lý và từng nhân viên
  dưới quyền. *Đây chính là công cụ để khách nghiệm thu theo lớp.*
- **"Doanh số ETC theo nhân viên"** — trước đây kênh ETC **hoàn toàn không có báo cáo nhân sự nào**,
  dù doanh thu ETC (25,7 tỷ/tháng) lớn hơn OTC (17,0 tỷ). Đã kiểm chứng tổng khớp doanh thu ETC
  thật, lệch 0 đồng.

### D. Kiến trúc & vận hành

- **Chuyển toàn bộ luồng báo cáo/cảnh báo sang đọc trực tiếp Bravo**, bỏ hẳn lớp lưu trữ trung gian
  — số liệu tươi hơn, ít mắt xích có thể hỏng hơn.
- **Máy chủ đã tự phục hồi**: cấu hình tự khởi động lại sau khi máy khởi động hoặc tiến trình gặp
  lỗi — trước đó nếu máy chủ khởi động lại thì chatbot chết cho tới khi có người bật tay.
- Dọn dứt điểm tình trạng **nhiều tiến trình đồng bộ chạy song song** trên máy chủ (nguyên nhân gốc
  của lỗi B2).

### E. Chất lượng & bảo mật chatbot

- **Giới hạn 10 câu hỏi/phút/người dùng** — *đúng mối lo khách nêu tại họp 16/07 về chi phí khi
  10–20 người dùng đồng thời.*
- **Cảnh báo khi dữ liệu có thể đã cũ** — phát hiện tiến trình đồng bộ bị treo, thay vì trả lời tự
  tin bằng số liệu cũ mà không ai biết.
- **Cảnh báo khi số liệu không khớp** — nếu tổng theo vùng lệch tổng chung, chatbot nói rõ với người
  dùng thay vì im lặng đưa số sai.
- **Phân biệt "khách không có nợ" với "không tra cứu được"** — trước đây lỗi tra cứu bị hiểu nhầm
  thành "khách không có công nợ", rất rủi ro cho quyết định công nợ.
- Tách riêng doanh thu **Kênh MT (Modern Trade)** trong báo cáo Miền Nam.

### F. Tài liệu

- Soạn lại toàn bộ **bộ câu hỏi nghiệp vụ cần DNH xác nhận**: 14 mục, chia 5 nhóm theo mức độ chặn
  tiến độ, kèm bảng ưu tiên và bằng chứng số liệu. Trong đó **5 mục cần chốt trước Demo #1 (09/08)**.
- Giao diện email/Teams chuyển sang **màu thương hiệu DNH** (xanh lá + cam) kèm logo.

---

## PHẦN 3 — Kế hoạch còn lại trong tuần (23/07 – 24/07)

*(Cập nhật lại nếu dựng báo cáo sau khi tuần kết thúc)*

- Gửi **báo cáo hoàn thành mốc M1** và **bộ câu hỏi nghiệp vụ** cho khách; đề nghị nghiệm thu theo
  từng lớp dữ liệu
- Chuẩn bị nội dung **Demo #1 Chatbot (09/08)** — dựng bộ câu hỏi demo, chạy thử, rà lỗi trước
- Bắt đầu **đo chi phí vận hành AI** phục vụ ước tính go-live (cam kết tuần 8–10)

---

## PHẦN 4 — Số liệu hệ thống *(tại 22/07/2026)*

| Chỉ số | Giá trị (tháng 7, đến 22/07) |
|---|---|
| Doanh thu OTC | 16,97 tỷ đ (5.535 hóa đơn) |
| Doanh thu ETC | 25,71 tỷ đ (629 hóa đơn) |
| **Tổng doanh thu** | **42,68 tỷ đ** (+5,4% so kỳ trước) |
| Tổng dư nợ | 180,06 tỷ đ |
| Nợ quá hạn | 81,48 tỷ đ (**45,3%**) |
| KPI toàn đội OTC | 36,0% hoàn thành chỉ tiêu tháng |
| Doanh thu ETC theo vùng | Bắc 9,40 tỷ · Trung 1,24 tỷ · Nam 15,08 tỷ |
| Quy mô đội ngũ | OTC ~150 nhân viên + ~20 quản lý · ETC 277 nhân sự |

---

## PHẦN 5 — Rủi ro cần nêu

| # | Rủi ro | Mức | Biện pháp |
|---|---|---|---|
| 1 | **14 điểm nghiệp vụ chưa được DNH chốt** → số liệu còn dùng giả định, rủi ro phải làm lại | 🔴 Cao | Đã soạn danh sách kèm bằng chứng; đề nghị chốt 5 điểm ưu tiên trước Demo #1 (09/08) |
| 2 | **Chưa có nghiệm thu từng lớp từ khách** → sai lệch phát hiện muộn | 🔴 Cao | Đã tự kiểm xong 4 lớp; chờ khách khảo sát + cấp tài khoản cho quản lý vùng tự kiểm |
| 3 | **Dữ liệu gốc Bravo có cờ/mã sai** — 2 quản lý thật bị ẩn khỏi báo cáo; 6 mã nhân viên không xác định (≈484 triệu) | 🟠 TB | Đã vá tạm ở tầng hệ thống; đề nghị DNH sửa gốc |
| 4 | **Chi phí AI khi nhiều người dùng đồng thời** | 🟠 TB | Đã áp giới hạn số câu/phút; đang chuẩn bị số liệu ước tính chi phí |

---

## PHẦN 6 — Yêu cầu đầu ra

Tạo **báo cáo tuần** (tuần 20–24/07/2026) cho dự án DNH, gồm các mục:

1. **Tóm tắt điều hành** — 3–4 dòng: tuần này làm gì, kết quả nổi bật nhất
2. **Kết quả chính** — chọn lọc, tối đa 6–7 ý (ưu tiên mục A và B ở Phần 2)
3. **Kế hoạch tuần tới**
4. **Rủi ro & việc cần khách phối hợp**

**Quy tắc bắt buộc:**
1. **Chọn lọc, không liệt kê hết** — báo cáo tuần nên đọc hết trong 2 phút.
2. **Luôn kèm số liệu cụ thể** khi nêu kết quả (vd "5,09 tỷ → 2,54 tỷ" thay vì "đã sửa lỗi sai số").
3. **Không nêu tên nhân viên cụ thể** ở phần lỗi dữ liệu — chỉ nói "2 quản lý".
4. **Không dùng thuật ngữ kỹ thuật** — viết cho người quản lý đọc.
5. Thông điệp xuyên suốt: **tuần này tập trung vào tính chính xác của số liệu (đúng chỉ đạo của
   khách), đã tìm và sửa được 4 lỗi thật mà nếu để lâu sẽ rất khó truy** — nhấn mạnh giá trị của
   việc kiểm theo lớp, vì đó chính là phương pháp khách yêu cầu.
