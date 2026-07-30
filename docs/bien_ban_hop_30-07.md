# Biên bản cuộc họp — Dự án Tích hợp Dữ liệu & AI Chatbot

| | |
|---|---|
| **Thời gian** | …giờ… ngày 30/07/2026 |
| **Địa điểm / Hình thức** | ……………………………………… |
| **Kỳ báo cáo** | 16/07 → 30/07/2026 *(2 tuần, kể từ buổi họp 16/07)* |
| **Chủ trì** | ……………………………………… |
| **Người ghi biên bản** | Lê Viết Đăng (MCNA) |

**Thành phần tham dự**

| Bên | Họ tên | Vai trò |
|---|---|---|
| Dược Nam Hà | | |
| Dược Nam Hà | | |
| MCNA | Đặng Việt Triều | |
| MCNA | Lê Viết Đăng | |
| MCNA | Nguyễn Thế Thành | |

---

## 1. Nội dung MCNA báo cáo

*(Phần này đã chuẩn bị sẵn, chỉ cần đối chiếu khi trình bày. Chi tiết:
[`tong_hop_cong_viec_16-29-07.md`](tong_hop_cong_viec_16-29-07.md))*

### 1.1. Khối lượng công việc

**121 đầu việc** hoàn thành trong 14 ngày, chia 6 nhóm:

| Nhóm | Số lượng | Kết quả nổi bật |
|---|---|---|
| Sửa lỗi số liệu | 13 lỗi | Dư nợ từng bị thổi phồng **4–15 lần**; KPI toàn công ty từng **thiếu hẳn 2 miền** mà không báo lỗi |
| Bịt lỗ hổng phân quyền | 11 lỗ hổng | **Toàn bộ do MCNA tự phát hiện**, không phải khách báo |
| Hạ tầng & độ ổn định | 11 việc | Bỏ hẳn Supabase và Telegram khỏi hệ thống |
| Chi phí AI | 5 mốc | Từ chỗ không đo được → nay quy được đến từng người dùng |
| Báo cáo & giao diện | 10 việc | Làm lại toàn bộ giao diện chatbot theo bộ nhận diện DNH |
| Kiểm chứng | 6 việc | **17/17 câu Demo #1 đạt** trên hệ thống thật |

### 1.2. Kiểm soát dữ liệu theo lớp *(đáp ứng yêu cầu của DNH)*

Chi tiết: [`ban_do_kiem_soat_theo_lop.md`](ban_do_kiem_soat_theo_lop.md)

Xây và kiểm **từ dưới lên**: cá nhân → quản lý → vùng → toàn công ty.

| Lớp | Phạm vi | Số lượng | Trạng thái |
|---|---|---|---|
| Lớp 4 — Cá nhân | Doanh số từng TDV | **148 người** | ✅ Đóng từ 20/07 |
| Lớp 3 — Quản lý | Tổng đội từng QLV | **21 quản lý** | 📍 **Đang xử lý** |
| Lớp 2 — Vùng | Doanh thu & công nợ 3 miền | MB · MT · MN | ✅ Tự kiểm xong, chờ DNH soát |
| Lớp 1 — Toàn công ty | Doanh thu · công nợ · KPI · tồn kho | | ✅ Tự kiểm xong, chờ DNH soát |

**Sai lệch 0 đồng ở cả 4 ranh giới giữa các lớp** (TDV→QLV, QLV→Vùng, Vùng→Công ty, Công ty↔Bravo).

> **Trả lời câu hỏi "đang xử lý ở lớp nào":** luồng dữ liệu hiện ở **Lớp 3 — Quản lý vùng**. Lớp 4 đã
> đóng; Lớp 1–2 đã tự kiểm xong và chờ DNH soát. Toàn bộ việc đang mở đều nằm ở Lớp 3.

### 1.3. Chi phí vận hành AI — đo được lần đầu

| | |
|---|---|
| Chi phí thực tế 08/07 → 29/07 | **26,01 USD ≈ 685 nghìn đồng** *(tỷ giá 26.334,50 đ/USD)* |
| Nhịp hiện tại | ~1,18 USD ≈ **31 nghìn đồng/ngày** |
| Ước tính tháng | ~37 USD ≈ **965 nghìn đồng** |
| Sau 31/08 (hết khuyến mãi) | ~55 USD ≈ **1,45 triệu đồng/tháng** |

**Hai điều cần nói rõ:**
- Đây là mức **giai đoạn phát triển và kiểm thử của MCNA**, chưa phải vận hành thật với 147 TDV. Con số
  cho go-live vẫn theo cam kết **tuần 8–10**.
- Mức sau 31/08 (~55 USD) **đã vượt ngân sách 50 USD/tháng** đang đặt trong hệ thống.

### 1.4. Việc mới ngoài kế hoạch ban đầu

Hoàn thành đêm 29/07, đã kiểm chứng trên máy chủ thật:

- **Đăng nhập bằng email công ty** `@namhapharma.com` (tài khoản cũ dùng username vẫn nguyên).
- **Trang Quản lý Tài khoản** cho Ban điều hành: tạo tài khoản, phân quyền, khoá/mở.
- **Đổi mật khẩu** và **quên mật khẩu**.
- Giao diện chatbot làm lại toàn bộ theo bảng màu Dược Nam Hà.

> **Lưu ý:** tính năng tự đăng ký công khai **cố ý không mở**. Lý do: Bravo không lưu email nhân viên
> (đã kiểm toàn bộ database, 0 cột email), nên hệ thống không có cách nào biết người đăng ký ứng với mã
> nhân viên nào để giới hạn phạm vi xem. Sở hữu hộp thư `@namhapharma.com` chỉ chứng minh **là người của
> DNH**, không chứng minh **là ai**. Vì vậy tài khoản phải do Ban điều hành tạo và gán quyền.

---

## 2. Đề nghị MCNA trình DNH quyết

| # | Nội dung | Mức | Ý kiến DNH | Người phụ trách | Hạn |
|---|---|---|---|---|---|
| 1 | **Phạm vi xem của quản lý vùng** — đội mình hay cả miền? Tồn kho và công nợ có thuộc quyền họ không? | 🔴 Cao | | | |
| 2 | **Cấp tài khoản cho 1–2 quản lý vùng tự nghiệm thu** *(đã nêu từ 16/07)* | 🔴 Cao | | | |
| 3 | **Hai nhân viên có thể đang bị tính thiếu lương** — đề nghị bộ phận lương/kế toán đối chiếu | 🟠 TB | | | |
| 4 | **Xác nhận văn bản chính sách lương áp dụng cho tháng 7** — có 2 phiên bản cùng tồn tại | 🟠 TB | | | |
| 5 | **`TM26060104` Nguyễn Văn Dũng (NTH01)** có doanh số 4,95 triệu nhưng chỉ tiêu = 0 | 🟠 TB | | | |
| 6 | **Xin hộp thư `@namhapharma.com` + app password** để hệ thống gửi mật khẩu tự động | 🔵 Thấp | | | |

**Ghi chú cho mục 1:** MCNA đã tạm chặn **9 báo cáo** với tài khoản quản lý vùng theo nguyên tắc *thà từ
chối còn hơn lộ nhầm*. Chưa chốt thì tại Demo #1 (09/08) không trình bày được phần đăng nhập vai quản lý
vùng — vốn là phần thể hiện năng lực phân quyền.

---

## 3. Ý kiến, yêu cầu từ phía Dược Nam Hà

*(ghi tại cuộc họp)*

| # | Nội dung | Người nêu | MCNA phản hồi |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |

---

## 4. Kết luận và phân công

| # | Việc | Bên thực hiện | Người phụ trách | Hạn hoàn thành |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

---

## 5. Mốc tiếp theo

| Mốc | Thời gian | Ghi chú |
|---|---|---|
| **Demo #1 Chatbot** | **09/08/2026** | Còn 10 ngày. Đã kiểm chứng 17/17 câu; chờ DNH chốt mục 1–2 để trình bày được vai quản lý vùng |
| Buổi họp tiến độ tiếp theo | …/08/2026 | Nhịp 2 tuần/lần |
| Ước tính chi phí go-live | Tuần 8–10 | Cam kết từ buổi họp 16/07 |

---

## 6. Vấn đề còn treo, chưa có hướng xử lý

*(ghi tại cuộc họp — những điểm hai bên chưa thống nhất được hoặc cần thêm thông tin)*

| # | Vấn đề | Vì sao chưa chốt được | Cần gì để chốt |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

---

**Biên bản được lập thành … bản, mỗi bên giữ … bản.**

| Đại diện Dược Nam Hà | Đại diện MCNA |
|---|---|
| | |
| | |
| *(ký, ghi rõ họ tên)* | *(ký, ghi rõ họ tên)* |
