# Câu hỏi cần DNH xác nhận — 23/09/2026

Bốn câu dưới đây **chặn việc đóng UAT**, không phải câu hỏi tìm hiểu thêm. Mỗi câu đều đã điều tra
hết mức làm được từ phía MCNA; phần còn lại là định nghĩa nghiệp vụ chỉ DNH trả lời được.

---

## Câu 1 — "Doanh số ETC" là toàn kênh hay một miền?

**Gửi:** phụ trách kênh ETC (tài khoản `dnh_etc`).

Ngày 15/09 khi chấm UAT, anh/chị hỏi *"Doanh số ETC tháng này"*. Chatbot trả **16,19 tỷ** (lũy kế
01–15/09, 420 hóa đơn) và bị chấm sai với nhận xét *"tháng này mới có gần 6,5 tỷ thôi"*. Cùng phiên,
câu *"thực hiện, kế hoạch doanh số các tháng trong năm"* cũng bị chấm *"kế hoạch đúng, thực hiện sai"*.

Chúng tôi đã đối chiếu lại toàn bộ:

- Chatbot gọi đúng công cụ, đúng kỳ; con số **khớp tuyệt đối** với `vHoaDonETCTotal` trên Bravo.
- Bảng 9 tháng cũng khớp từng chữ số với nguồn.
- Đã thử tách theo nhóm hàng, theo nhân viên, theo tổ hợp nhóm — **không lát cắt nào ra 6,5 tỷ**.
- Lát duy nhất khớp là **theo miền**: Miền Bắc 01–15/09 là **6,72 tỷ** (quy về đúng mốc đồng bộ lúc
  anh/chị hỏi thì ≈ 6,58 tỷ).

| Miền | Hóa đơn | 01–15/09 |
|---|---:|---:|
| Miền Nam | 200 | 8,44 tỷ |
| **Miền Bắc** | **188** | **6,72 tỷ** |
| Miền Trung | 41 | 1,39 tỷ |
| **Toàn kênh** | **429** | **16,56 tỷ** |

**Xin xác nhận hai ý:**

1. Con số 6,5 tỷ anh/chị đối chiếu là **toàn kênh ETC** hay **riêng Miền Bắc**?
2. Bảng "thực hiện các tháng" anh/chị so sánh ở **phạm vi nào** — toàn quốc như kế hoạch, hay một miền?

Nếu là Miền Bắc thì đây **không phải sai số**, mà là chatbot chưa nói rõ phạm vi. Chúng tôi sẽ sửa
để mọi câu trả lời tổng đều ghi rõ *"toàn kênh ETC, gồm cả 3 miền"*.

---

## Câu 2 — Hóa đơn ETC đề ngày 28 hàng tháng

**Gửi:** kế toán / phụ trách dữ liệu Bravo.

Trên Bravo có hóa đơn ETC mang **ngày chứng từ trong tương lai**, lặp lại theo tháng và luôn rơi vào
**ngày 28**:

| Thời điểm phát hiện | Chứng từ |
|---|---|
| 14/08/2026 | ETC đề ngày **28/08/2026** |
| 23/09/2026 | ETC đề ngày **28/09/2026** — 4 dòng, 2 số chứng từ, 1 khách, 17,56 triệu |

Vì lặp đúng ngày 28 qua hai tháng khác nhau nên nhiều khả năng đây là **chứng từ ghi trước theo
lịch**, không phải lỗi nhập ngẫu nhiên.

**Xin xác nhận:**

1. Hóa đơn ETC đề ngày 28 hàng tháng là **chứng từ ghi trước theo kế hoạch**, hay **nhập sai ngày**?
2. Nếu là ghi trước: doanh số tháng nên tính theo **ngày chứng từ** hay **ngày thực xuất**?

**Xử lý tạm hiện tại:** chatbot **không cộng** phần đề ngày tương lai vào doanh thu tháng đang chạy,
nhưng **có nêu ra** kèm số tiền, để không giấu cũng không tự cộng. Mức ảnh hưởng hiện rất nhỏ
(17,56 triệu trên 45,9 tỷ = 0,04%). Có câu trả lời thì đổi cách xử lý được ngay mà không phải sửa
lại cấu trúc.

---

## Câu 3 — 11 khách có doanh thu ở Miền Trung nhưng không có dòng FACT cấp nhân viên

**Gửi:** phụ trách dữ liệu Bravo / phân công địa bàn.

Phép đối soát doanh thu (PR #62) trên kho dev kỳ **01–15/09/2026** còn lệch **13.173.440đ** của
**11 khách hàng**. Các khách này **có hóa đơn và có doanh thu** ghi ở mã quản lý Miền Trung, nhưng
**không có dòng nào trong FACT ở cấp nhân viên** — nên cộng theo nhân viên thì thiếu, cộng theo mã
quản lý thì đủ.

Chưa quy nguyên nhân. Bản sửa **giữ nguyên cảnh báo** thay vì tự bù số.

**Xin xác nhận:** 11 khách này thuộc **phân công của ai**, và vì sao không phát sinh dòng FACT cấp
nhân viên — khách chưa gán TDV, TDV đã nghỉ, hay lỗi đồng bộ?

---

## Câu 4 — Đơn hàng có hai nhân viên thì tính cho đội nào?

**Gửi:** phụ trách kênh OTC / DMS.

`DMS_DonHangHdr` có hai cột nhân viên: `DMSEmpId1` và `DMSEmpId2`. Hai bên đang hiểu khác nhau:

| | Cách lọc |
|---|---|
| Chatbot | `DMSEmpId1 IN (đội) **OR** DMSEmpId2 IN (đội)` |
| Checker UAT | chỉ `DMSEmpId1` |

Nghĩa là đơn do người ngoài đội đứng tên chính nhưng có người trong đội ở vai thứ hai thì chatbot
tính vào đội, checker thì không.

**Xin xác nhận:** doanh số/khách của đội nên tính theo **người đứng tên chính** (`DMSEmpId1`), hay
**bất kỳ ai tham gia đơn**? Đây là định nghĩa nghiệp vụ, chúng tôi không tự chọn để nắn số cho khớp
checker.

---

## Đang chờ, không phải câu hỏi mới

| Việc | Chờ ai | Chặn gì |
|---|---|---|
| UPN Teams của 6 người nhận + webhook Flow mới | DNH | PR #41 — chuyển Daily/alert sang một Flow chung |
| Đặc tả SMTP: hostname, port, STARTTLS/TLS, kiểu xác thực, địa chỉ From được phép, whitelist từ máy 24, chứng chỉ | IT DNH | Chuyển máy chủ gửi mail sang `chatbot.namhatrading.com` |
| Nguồn giá tồn kho (969.269 đơn vị đang = 0đ) | DNH | Câu B03 — không chặn go-live |
| Nguồn target quý (kho chỉ có target tháng/vùng/QLV/SKU) | DNH | Mục #24 checklist chấm lại |

Nếu IT yêu cầu OAuth hoặc relay theo IP không dùng mật khẩu thì phải bổ sung và kiểm thử sau khi
nhận đặc tả — hiện mới hỗ trợ xác thực SMTP bằng username/password.
