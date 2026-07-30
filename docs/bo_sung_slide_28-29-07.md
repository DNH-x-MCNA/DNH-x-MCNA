# Bổ sung slide — công việc 28/07 → 29/07/2026

> Phần này bổ sung cho `bao_cao_tien_do_30-07.md`. Hai ngày cuối kỳ có **35 đầu việc**, tập trung vào
> 4 nhóm: bịt lỗ hổng phân quyền, sửa lỗi số liệu, đo được chi phí AI, và làm lại giao diện.

---

## A. Ba lỗ hổng phân quyền — MCNA tự phát hiện, tự vá trong 2 ngày

Không do khách báo. Đây là kết quả của quy trình tự rà soát đã cam kết tại họp 16/07.

| Lỗ hổng | Hậu quả nếu không vá | Trạng thái |
|---|---|---|
| **Quản lý vùng xem được doanh thu cả miền** | Hỏi "doanh thu tháng này" nhận về số của **cả 10 đội** thay vì riêng đội mình | Đã chặn 9 báo cáo theo nguyên tắc *thà từ chối còn hơn lộ nhầm* |
| **Tự nâng quyền qua báo cáo chi phí AI** | Một quản lý vùng có thể đọc lịch sử truy vấn của **toàn công ty** | Đã sửa: máy chủ luôn là bên quyết định quyền hạn |
| **Quyền suy từ TÊN tài khoản** | Tài khoản đặt tên `dnh.marketing` tự nhiên có quyền Ban điều hành | Đã sửa: chỉ căn cứ vai trò được cấp |

**Điểm cần chốt với DNH:** quản lý vùng được xem phạm vi **đội mình** hay **cả miền**? Chưa chốt thì
tại Demo #1 không trình bày được phần đăng nhập vai quản lý vùng.

---

## B. Chi phí AI — từ "không đo được" thành "đo được đến từng người"

Trước 28/07 mọi báo cáo chi phí đều hiện **0 đồng**. Hai ngày qua đã dựng xong toàn bộ đường đo và
sửa **4 lớp lỗi tính tiền** chồng lên nhau:

| # | Lỗi | Biểu hiện |
|---|---|---|
| 1 | Cộng trùng | Một phiên 6 lượt hỏi bị tính tiền **6 lần** — số bị thổi hơn 6 lần |
| 2 | Giấu mất phần lớn tiền | Tổng chỉ cộng phần quy được cho người dùng, phần còn lại **biến mất** |
| 3 | Không quy được cho ai | 89% chi phí không biết của ai, do sổ chi phí chưa ghi tên tài khoản |
| 4 | Bảng số không tự khớp | Cột tổng token và tổng tiền cộng tay **không ra** số hiển thị |

**Kết quả:** bảng số liệu nay tự kiểm chứng được — khách cộng tay từng cột đều ra khớp.

### Bảng điều khiển Chi phí AI cho Ban điều hành *(mới)*

Xem trực tiếp trên web, **không cần hỏi qua chatbot**: chi phí toàn công ty quy sẵn ra tiền Việt, phân
rã token, lịch sử truy vấn của mọi nhân viên, lọc theo người và theo khoảng thời gian.

### Con số thật lần đầu có được

| | |
|---|---|
| Chi phí 08/07 → 29/07 | **26,01 USD ≈ 685 nghìn đồng** |
| Nhịp hiện tại | ~1,18 USD ≈ **31 nghìn đồng/ngày** |
| Ước tính tháng | ~37 USD ≈ **965 nghìn đồng** |
| Sau 31/08 (hết khuyến mãi) | ~55 USD ≈ **1,45 triệu đồng/tháng** |

> ⚠️ Đây là mức **phát triển và kiểm thử của MCNA**, chưa phải vận hành thật với 147 TDV. Con số cho
> go-live vẫn theo cam kết **tuần 8–10**.
>
> ⚠️ Mức sau 31/08 (~55 USD) **đã vượt ngân sách 50 USD/tháng** đang đặt trong hệ thống — cần bàn.

---

## C. Giao diện chatbot — làm lại toàn bộ *(29/07)*

Chuyển từ giao diện mặc định sang bộ nhận diện riêng cho Dược Nam Hà, hướng "Executive Light Theme"
(nền sáng, trang nhã, hiện đại):

- **Bảng màu và chữ riêng** — xanh Navy đậm cho thanh điều hướng, Indigo cho nút hành động, màu cảnh
  báo riêng cho nợ quá hạn. Font hỗ trợ đầy đủ dấu tiếng Việt.
- **Số liệu tài chính gióng cột thẳng hàng** — mọi con số doanh thu, công nợ, token đều căn phải và
  dùng chữ số đều bề rộng, đọc nhanh hơn hẳn.
- **Bảng dữ liệu** bo góc, tiêu đề nền xám, tự gắn nhãn màu cho kênh (ETC/OTC) và ba miền.
- **Lịch sử trò chuyện** nhóm theo *Hôm nay / 7 ngày qua / Cũ hơn*, thêm bộ lọc theo người dùng cho
  Ban điều hành.
- **Ô nhập** dạng nổi kèm gợi ý câu hỏi nhanh.

---

## D. Kiểm chứng và vận hành

| Việc | Kết quả |
|---|---|
| **Kiểm chứng trọn bộ Demo #1** | **17/17 câu đạt** trên hệ thống thật, đủ 3 vai trò (Ban điều hành, Giám đốc miền, Quản lý vùng) |
| **Sự cố giao diện không cập nhật được 18 tiếng** | Đã tìm ra nguyên nhân và xử lý dứt điểm |
| **Đưa toàn bộ bản vá lên máy chủ thật** | Hoàn tất 29/07, hệ thống chạy ổn định |

---

## Gợi ý câu chốt cho slide

> Hai ngày cuối kỳ tập trung vào **độ tin cậy**: ba lỗ hổng phân quyền do MCNA tự tìm và tự vá, bốn
> lớp lỗi tính chi phí được bóc tách đến khi mọi con số tự khớp, và toàn bộ 17 câu hỏi Demo #1 được
> kiểm chứng trên hệ thống thật. Đây là bằng chứng của quy trình tự rà soát trước khi đưa cho khách,
> đúng như đã cam kết tại buổi họp 16/07.
