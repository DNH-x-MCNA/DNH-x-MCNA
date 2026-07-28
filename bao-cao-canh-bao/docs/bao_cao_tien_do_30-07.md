# Nội dung Báo cáo tiến độ — 30/07/2026

*Soạn 22/07/2026. Bám đúng cấu trúc 6 slide của bản báo cáo 16/07 (Google Slides) để tái sử dụng
template. Số liệu lấy tại 22/07 — **các ô đánh dấu 🔄 cần chạy lại ngay trước buổi họp** (dữ liệu
thay đổi hằng ngày; xem mục "Lệnh lấy số liệu" ở cuối file).*

---

## SLIDE 1 — Title

> **BÁO CÁO TIẾN ĐỘ DỰ ÁN**
> Xây dựng hệ thống cảnh báo kinh doanh, báo cáo định kỳ và AI chatbot cho nội bộ doanh nghiệp
> **Dược Nam Hà (DNH)**
>
> Progress Update
> **Ngày báo cáo: 30/07/2026**

---

## SLIDE 2 — TIMELINE (High-level)

**Đổi mốc "HÔM NAY" → T5 (27/07 – 02/08)**

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| **GĐ1 — Khảo sát & Chuẩn bị** | Bravo, VPN, khảo sát & ETL dữ liệu mẫu | ✅ **Hoàn tất** |
| **GĐ2 — Phát triển AI Chatbot** | AI Engine, System Prompt, UI, Security | 🔵 **Đang triển khai** (giai đoạn cuối) |
| **GĐ3 — UAT & Nghiệm thu Phase 1** | Demo #1, UAT, đào tạo & nghiệm thu | 🟡 Sắp bắt đầu — **Demo #1: 09/08 (T6)** |
| **GĐ4 — Báo cáo & Go-Live Phase 2** | Cảnh báo Outlook, Demo #2, UAT, Go-Live | ⚡ **Đã hoàn thành phần lớn TRƯỚC HẠN** (kế hoạch T8–T11) |
| **GĐ5 — Hypercare & Đóng dự án** | Theo dõi vận hành, đóng dự án | ⚪ Chưa tới |

**Thông điệp chính của slide:**
> Khối lượng kỹ thuật **đang đi trước kế hoạch** — hệ thống báo cáo & cảnh báo (vốn thuộc Giai đoạn 4,
> dự kiến tháng 8–9) đã chạy thật trên dữ liệu Bravo từ giữa tháng 7.
> Điểm cần DNH phối hợp: **nghiệm thu theo lớp** và **xác nhận các quy ước nghiệp vụ**.

---

## SLIDE 3 — Nhật ký công việc (1/2): Nền tảng dữ liệu

**Kỳ 15/07 – 30/07/2026**

### Chuyển toàn bộ sang đọc trực tiếp Bravo
Bỏ hẳn lớp lưu trữ trung gian cho luồng báo cáo/cảnh báo — số liệu nay lấy thẳng từ Bravo theo thời
gian thực, hết độ trễ và sai lệch do đồng bộ.

### Kiểm tra chất lượng dữ liệu theo 4 lớp *(đúng mô hình anh Long yêu cầu)*
Kiểm **từ dưới lên**: cá nhân → quản lý → vùng → toàn công ty, vì lỗi ở lớp dưới sẽ lan lên trên.

| Lớp | Phạm vi kiểm | Kết quả |
|---|---|---|
| Lớp 4 — Cá nhân | Doanh số từng TDV | ✅ Đúng |
| Lớp 3 — Quản lý | Tổng đội từng QLV | ✅ Khớp tuyệt đối tổng TDV dưới quyền |
| Lớp 2 — Vùng | Doanh thu & công nợ theo miền | ✅ Khớp tổng, **lệch 0 đồng** |
| Lớp 1 — Toàn công ty | Doanh thu, công nợ, KPI, tồn kho | ✅ Khớp hóa đơn gốc Bravo |

**→ 15/15 hạng mục đạt, sai lệch 0 đồng ở mọi ranh giới giữa các lớp.**

### 3 lỗi thật phát hiện & sửa nhờ quy trình này

**① Tỷ lệ nợ quá hạn 92,9% / 81,1% mà DNH phản ánh — xác nhận là LỖI THẬT, đã sửa.**
Công thức cũ đọc cột "đã thanh toán" bị đứng yên (không ghi nhận khoản trả sau, không đối trừ ứng
trước). Ví dụ: FPT Long Châu bị báo nợ **9,17 tỷ** trong khi thực tế chỉ **0,61 tỷ**. Nay gọi trực
tiếp báo cáo công nợ gốc của DNH.

| Kênh | Tỷ lệ quá hạn (sai → đúng) |
|---|---|
| OTC | 92,9% → **39,4%** |
| ETC | 81,1% → **52,3%** |

**② Hai quản lý bị hệ thống gắn nhầm cờ "trùng lặp"** — khiến doanh số và **cả đội dưới quyền họ**
(≈1,55 tỷ + ≈389 triệu/tháng) biến mất khỏi mọi báo cáo KPI. Đã vá tạm để báo cáo chạy đúng; **cần
DNH sửa dữ liệu gốc**.

**③ Nhóm khách hàng thiếu hồ sơ vùng** khiến **2,1 tỷ** doanh thu không được tính vào đúng miền.

---

## SLIDE 4 — Nhật ký công việc (2/2): Chatbot & Báo cáo

**Kỳ 15/07 – 30/07/2026**

### AI Chatbot (Giai đoạn 2)
- **Phân quyền theo vùng đã áp dụng thật ở tầng code** — mỗi tài khoản chỉ truy vấn được đúng
  vùng/kênh của mình, không phụ thuộc vào việc AI có "tự giác" lọc hay không.
  *(Đáp ứng trực tiếp yêu cầu tại họp 16/07: mỗi QLV chỉ tự kiểm tra vùng mình.)*
- **Cảnh báo khi dữ liệu có thể cũ** — phát hiện tiến trình đồng bộ treo, thay vì trả lời tự tin
  bằng số liệu cũ.
- **Cảnh báo khi số liệu không khớp** — nếu tổng theo vùng lệch tổng chung, chatbot **nói rõ với
  người dùng** thay vì im lặng đưa số sai.
- **Giới hạn 10 câu hỏi/phút/người** — kiểm soát chi phí API *(đúng mối lo anh Long nêu ở họp 16/07
  về chi phí khi 10–20 người dùng đồng thời)*.
- **Sửa lỗi dữ liệu nhân đôi**: doanh thu chatbot từng báo gấp 2 lần thật; đã truy ra nguyên nhân và
  xử lý — nay **khớp Bravo lệch 0 đồng**.

### Báo cáo định kỳ (Giai đoạn 4 — làm sớm)
- **Thêm "Chi tiết KPI theo Vùng – QLV – TDV"** — thể hiện đúng mô hình 4 lớp; quản lý vùng thấy
  từng QLV và từng TDV dưới quyền.
- **Thêm "Doanh số ETC theo nhân viên"** — trước đây kênh ETC hoàn toàn không có báo cáo nhân sự.
- **Sửa lỗi cộng trùng KPI**: chỉ tiêu/doanh số từng bị cộng gấp đôi do gộp nhầm 2 tầng TDV và QLV
  (vốn là 2 cách cắt lát của cùng một khoản doanh thu).
- **Nhãn kỳ báo cáo trung thực hơn**: hiển thị đúng khoảng đã có dữ liệu thay vì cả khung lịch.

---

## SLIDE 5 — OVERALL STATUS UPDATE

### VIỆC ĐANG LÀM / SẮP TỚI

- **Chuẩn bị Demo #1 Chatbot (09/08)**
- **Chờ DNH xác nhận 14 điểm nghiệp vụ** *(đã gửi danh sách kèm bằng chứng số liệu)* — trong đó
  **5 điểm cần chốt trước Demo #1** vì ảnh hưởng trực tiếp con số hiển thị:
  1. Cách tính ngày quá hạn & xác nhận báo cáo công nợ chuẩn
  2. Mốc phân nhóm tuổi nợ
  3. Nguồn giá để tính giá trị tồn kho *(thiếu nên mục "tồn kho chết" luôn hiển thị 0)*
  4. Chỉ tiêu cấp vùng vs cá nhân *(nghi có cộng chồng chỉ tiêu)*
  5. Kênh ETC có giao chỉ tiêu theo từng nhân viên không
- **Đề nghị DNH nghiệm thu theo từng lớp dữ liệu** — MCNA đã tự kiểm xong (bước 1–2); chờ anh Long
  khảo sát (bước 3) và quản lý vùng chéo kiểm (bước 4).
- **Cần danh sách tài khoản Chatbot thật** để cấp quyền cho quản lý vùng tự kiểm tra.
- Chuẩn bị **ước tính chi phí go-live** (cam kết tuần 8–10).

### MILESTONES

| Mốc | Hạn | Trạng thái |
|---|---|---|
| **M1 — Dữ liệu + AI Engine sẵn sàng** | 19/07 | ✅ Kỹ thuật hoàn thành — **chờ DNH nghiệm thu** |
| **M2 — Demo #1 Chatbot** | 09/08 | 🔵 Đang chuẩn bị |
| **M4 — Demo #2 Cảnh báo Outlook** | 06/09 | ⚡ Nội dung đã sẵn sàng sớm |
| **Đóng dự án** | 30/09 | ⚪ |

### 🔄 Số liệu hệ thống đang vận hành *(cập nhật 22/07 — chạy lại trước buổi họp)*

| Chỉ số | Giá trị (tháng 7, đến 22/07) |
|---|---|
| Doanh thu OTC | 16,97 tỷ đ (5.535 hóa đơn) |
| Doanh thu ETC | 25,71 tỷ đ (629 hóa đơn) |
| **Tổng doanh thu** | **42,68 tỷ đ** (+5,4% so kỳ trước) |
| Tổng dư nợ / quá hạn | 180,06 tỷ / 81,48 tỷ (**45,3%**) |
| KPI toàn đội OTC | 36,0% hoàn thành chỉ tiêu tháng |
| Doanh thu ETC theo vùng | Bắc 9,40 tỷ · Trung 1,24 tỷ · Nam 15,08 tỷ |

---

## SLIDE 6 — RISK & MITIGATION

| # | Rủi ro | Mức | Biện pháp xử lý |
|---|---|---|---|
| 1 | **14 điểm nghiệp vụ chưa được DNH chốt** → số liệu còn dùng giả định, rủi ro phải làm lại sau Demo | 🔴 Cao | Đã lập danh sách kèm bằng chứng số liệu; đề nghị chốt **5 điểm ưu tiên trước 09/08** |
| 2 | **Chưa có nghiệm thu từng lớp từ DNH** → sai lệch phát hiện muộn, tốn công sửa lại cuối dự án | 🔴 Cao | Mời anh Long soát Lớp 1–2 trước; cấp tài khoản để QLV vùng tự kiểm Lớp 3–4 |
| 3 | **Chi phí token AI** khi 10–20 người dùng đồng thời | 🟠 TB | Đã áp giới hạn 10 câu/phút/người + phân vùng dữ liệu theo quyền; cam kết ước tính chi phí tuần 8–10 |
| 4 | **Dữ liệu gốc Bravo có cờ/mã sai** (2 quản lý thật bị ẩn khỏi báo cáo, 6 mã nhân viên không xác định ≈484 triệu) | 🟠 TB | Đã vá tạm ở tầng code; đề nghị DNH sửa gốc + lập quy trình rà soát định kỳ |
| 5 | **Gián đoạn vận hành máy chủ** trước các mốc demo | 🟢 Thấp | Đã cấu hình tự khởi động lại sau khi máy khởi động / tiến trình lỗi *(xử lý xong 22/07)* |

---

## SLIDE 7 — Kết

> Cảm ơn đã lắng nghe
> **MCNA Technology**

---

## Ghi chú khi dựng slide

- **Giữ nguyên template & bố cục** bản 16/07 để nhất quán, chỉ thay nội dung.
- **Slide 2**: nhớ dời dải "HÔM NAY" sang **T5 (27/07–02/08)** và đổi màu trạng thái 5 giai đoạn.
- **Không đưa tên nhân viên cụ thể** lên slide chiếu chung ở phần lỗi dữ liệu (mục ②) — chỉ nói
  "2 quản lý"; danh tính đã có trong tài liệu gửi riêng.
- Phần nhật ký (slide 3–4) nên để dạng **bảng/gạch đầu dòng ngắn**, số liệu in đậm — bản 16/07
  dùng bảng, giữ vậy cho quen mắt.

## Lệnh lấy lại số liệu trước buổi họp

Chạy trong `D:\DNH`:

```bash
python -c "
from src.etl import get_monthly_digest_metrics
m = get_monthly_digest_metrics(region=None, channel=None)
r = m['revenue']; rec = m.get('receivables') or {}; k = m.get('kpi_summary') or {}
print(f\"Ky: {m['period_range']}\")
print(f\"OTC {r['otc']:,.0f} ({r['otc_invoice_count']} HD) | ETC {r['etc']:,.0f} ({r['etc_invoice_count']} HD)\")
print(f\"TONG {r['total']:,.0f} | so ky truoc {r['change_pct']}%\")
print(f\"Cong no: qua han {rec.get('total_overdue',0):,.0f} / du no {rec.get('balance_end',0):,.0f}\")
print(f\"KPI doi: {k.get('achieved_count')}/{k.get('total_count')} | toan doi {k.get('team_pct')}%\")
"
```
