# Nội dung Báo cáo tiến độ — 27/08/2026

*Soạn 26/08/2026, giữ cấu trúc 6 slide của bản 13/08. Kỳ báo cáo: **13/08 → 26/08** (2 tuần).
Buổi này là báo cáo cuối trước kỳ nghỉ lễ.*

> ⚠️ **Lưu ý về nguồn số liệu.** Bản này phân biệt rõ hai loại:
> - **ĐÃ ĐO** — có kết quả chạy thật trên dữ liệu production, dán được log ra xem. Đây là phần
>   chịu trách nhiệm được.
> - **TRÊN GIẤY** — đối chiếu tài liệu/mô tả, chưa chạy thật. Đánh dấu rõ, **không được trình bày
>   như số đo**.
>
> Nhật ký công việc tổng hợp từ `git log --since=2026-08-13` (117 commit). Phần của đồng nghiệp
> (`Trieu Viet Dang` 12 commit, `danglvmcna` 4, `thanhf-mcna` 3) chỉ đọc từ tiêu đề commit —
> **xác nhận lại với họ trước khi đưa lên slide chiếu**.

---

## SLIDE 1 — Title

> **BÁO CÁO TIẾN ĐỘ DỰ ÁN**
> Hệ thống cảnh báo kinh doanh, báo cáo định kỳ và AI Chatbot nội bộ
> **Dược Nam Hà (DNH)**
>
> Kỳ báo cáo: **13/08 – 26/08/2026**
> Báo cáo trước kỳ nghỉ lễ

---

## SLIDE 2 — TIMELINE

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| **GĐ1 — Khảo sát & Chuẩn bị** | Bravo, VPN, khảo sát & ETL | ✅ Hoàn tất |
| **GĐ2 — Phát triển AI Chatbot** | AI Engine, System Prompt, UI, Security | 🔵 Đang triển khai — kỳ này tập trung **mở rộng năng lực + kiểm chứng số liệu** |
| **GĐ3 — UAT & Nghiệm thu Phase 1** | Demo #1 (13/08), UAT, đào tạo | 🟢 Demo #1 xong; chuẩn bị test diện rộng toàn công ty |
| **GĐ4 — Báo cáo & Go-Live Phase 2** | Cảnh báo Outlook, Demo #2, Go-Live | ⚡ Phần lớn hoàn thành trước hạn |
| **GĐ5 — Hypercare & Đóng dự án** | Theo dõi vận hành, đóng dự án | ⚪ Chưa tới |

**Thông điệp chính:**
> Hai tuần qua chuyển trọng tâm từ *"chatbot trả lời được không"* sang **_"con số nó trả lời có
> đúng không"_**. Đã bổ sung **21 công cụ nghiệp vụ mới** và — quan trọng hơn — dựng **bộ kiểm
> chứng tự động 35 phép** chạy trên dữ liệu production, không tốn chi phí AI.

---

## SLIDE 3 — VIỆC ĐÃ LÀM (13/08 – 26/08)

### 3.1 Mở rộng năng lực: 21 công cụ nghiệp vụ mới

Tổng số công cụ: **19 → 40**. Nhóm theo câu hỏi điều hành mà chúng mở khoá:

| Nhóm | Công cụ mới | Trả lời được câu gì |
|---|---|---|
| **Chuỗi thời gian** | `revenue_monthly_series`, `revenue_ytd_cumulative` | "Doanh thu 12/24 tháng gần nhất từng tháng, MoM/YoY" — trước đây **bất khả thi** vì phải gọi 12 lần, đụng trần công cụ |
| **Vòng đời khách hàng** | `customer_lifecycle_summary`, `customers_silent`, `customer_cohort_retention`, `customer_movement` | Khách mở mới / đặt lại / ngừng mua; tỷ lệ giữ chân sau 3–6 tháng |
| **Bán chéo & độ phủ** | `cross_sell_opportunities`, `customer_product_coverage` | "Khách mua A mà chưa mua B"; khách chỉ mua một nhóm hàng |
| **Địa bàn & đội ngũ** | `geography_monthly_performance`, `workforce_productivity` | Xếp hạng tỉnh theo tháng; năng suất/đầu người, span of control |
| **Công nợ** | `receivables_overview`, `receivables_period_compare`, `receivables_history_dates`, `customer_revenue_debt_risk` | So sánh công nợ giữa 2 kỳ; khách vừa nợ vừa giảm mua |
| **Vận hành & chất lượng** | `operational_data_quality`, `kpi_gap_run_rate`, `inventory_expiry_report` | Checklist cuối tháng; còn thiếu bao nhiêu để đạt chỉ tiêu; tồn kho theo lô/hạn dùng |
| **Lương thưởng & khuyến mãi** | `salary_bonus_policy`, `salary_data_quality`, `promotion_effectiveness`, `promotion_data_quality` | Chính sách thưởng; hiệu quả chương trình khuyến mãi |

### 3.2 Kiểm soát chi phí: đã triển khai hạn mức tuần

- **QLV 30 câu/tuần · TP 60 · C-level 120**, đặt lại vào thứ Hai. Có hiển thị số lượt còn lại trên giao diện.
- Câu bị hệ thống từ chối (hỏi dự báo tương lai) **không trừ hạn mức** — không phạt người dùng vì
  giới hạn của hệ thống.
- **Chi phí thực đo:** ngày 25/08 tốn **$13,40**; người dùng thật ~**$2,9/ngày ≈ $87/tháng**, so
  ngân sách **$300/tháng**. Đã đối chiếu ba nguồn (log nội bộ · dashboard · Anthropic Console) —
  **khớp trong 0,7%**.

### 3.3 Sửa lỗi số liệu và vận hành

| Lỗi | Ảnh hưởng thật | Trạng thái |
|---|---|---|
| Hai công cụ chuỗi tháng cắt danh sách **từ đuôi mảng** | Hỏi "xếp hạng 63 tỉnh theo tháng" nhận về **1/4 dữ liệu**, và giữ đúng các tỉnh **yếu nhất** thay vì mạnh nhất | ✅ Sửa, khoá bằng 10 test |
| Hai nguồn định nghĩa đối nghịch về cờ `IsAC` | Đường SQL tự do dạy AI một đằng, đường công cụ dạy một nẻo | ✅ Hợp nhất |
| Báo cáo địa bàn trả **0** cho tháng ngoài cửa sổ 12 tháng | AI dễ đọc "0" thành *"địa bàn không bán được gì"* | ✅ Nay báo rõ *"không có dữ liệu địa bàn"* |
| Hoá đơn ghi ngày tương lai làm hỏng mốc "hôm nay" | Sai toàn bộ mốc so sánh trong luồng cảnh báo | ✅ Sửa 3 chỗ |
| **Dịch vụ nuốt bản cập nhật suốt 19 tiếng** | Deploy báo "Failed to start" trong khi bản cũ vẫn phục vụ người dùng — **không có cảnh báo nào** | ✅ Nay tự phát hiện và báo rõ |

**Số kiểm thử tự động: 322 → 340.**

---

## SLIDE 4 — KIỂM CHỨNG: SỐ ĐO THẬT

> Đây là phần quan trọng nhất kỳ này. Trước đây độ tin cậy dựa trên *"code trông đúng"* và test đơn vị.
> Kỳ này có **hai phép đo độc lập chạy trên dữ liệu production**.

### 4.1 AI có chọn đúng công cụ không? — **25/25 (100%)**

Mẫu phân tầng 25 câu hỏi điều hành, chạy thật trên máy chủ DNH.

| Nhóm vai | Kết quả | Vì sao đáng chú ý |
|---|---|---|
| **Giám đốc Miền + QLV** | **13/13 = 100%** | Hai vai này **không được dùng SQL tự do** (chặn theo phân quyền), nên chọn sai công cụ là **không có đường lùi** |
| C-level | 12/12 sau khi sửa | Vòng đầu 10/12; một câu trượt thật đã sửa, một câu là kỳ vọng đo sai |

### 4.2 Con số trả về có đúng không? — **35/35 phép kiểm bất biến**

Chạy trên kho dữ liệu thật **153 MB**, **không gọi AI, không tốn chi phí**. Nguyên tắc: cùng một
con số phải ra giống nhau khi đi qua các đường tính khác nhau.

| Phép kiểm | Kết quả |
|---|---|
| Doanh thu 12 tháng, hai đường tính độc lập | **994.503.772.255 đ — lệch 0 đồng** |
| Tháng 7 qua **4 lối khác nhau** (theo vùng · theo 7.304 khách · theo 200 sản phẩm · so sánh kỳ) | **cả bốn ra đúng 74.835.467.323 đ** |
| Công nợ 180,59 tỷ: chia theo kênh và theo vùng | khớp tuyệt đối |
| Cây KPI: rollup của Bravo so tổng chi tiết TDV | lệch 0,13% (đã giải thích được toàn bộ phần chênh) |
| Địa bàn từng tháng, 12/12 tháng | khớp tổng công ty |

> **Vì sao phép kiểm này đáng giá:** ba sự cố tốn nhiều thời gian nhất của dự án đều thuộc loại
> *"số sai nhưng câu trả lời trông hoàn toàn hợp lý"* — doanh thu lệch 4%/ngày, công nợ thổi 4–15
> lần, cộng lẫn tầng TDV/QLV thành gấp đôi. Không phép kiểm nào phát hiện được chúng bằng mắt.
> Bộ 35 phép này chạy được bất cứ lúc nào, miễn phí, và sẽ bắt ngay nếu tái diễn.

---

## SLIDE 5 — ĐANG LÀM & CHUẨN BỊ LÀM

| Việc | Trạng thái | Ghi chú |
|---|---|---|
| **Test diện rộng toàn công ty** — bộ 138 câu hỏi điều hành | Đã dựng xong bộ chạy tự động | **Chưa chạy** — cần ngân sách API ~$9 |
| Kiểm chứng độ đúng số liệu ở các công cụ còn lại | 35/35 phép hiện phủ 18 công cụ | Mở rộng dần sang 22 công cụ còn lại |
| Ghi chú múi giờ trên giao diện | Code xong, chờ deploy Vercel | |
| Đào tạo & UAT Phase 1 | Chờ lịch DNH | |

### Về bộ 138 câu — nói rõ để tránh hiểu nhầm

Bộ câu hỏi này do phía DNH đặt ra làm tiêu chí nghiệm thu diện rộng. Đánh giá hiện tại:

- **~84/138 câu (61%) trả lời được** — nhưng đây là **ĐỐI CHIẾU TRÊN GIẤY**, chưa chạy thật.
- **25 câu đã đo thật** đều đạt (mục 4.1).
- **113 câu còn lại chưa từng được hỏi lần nào.**

**Không được trình bày 61% như một số đo.** Nó là giới hạn trên chưa kiểm chứng.

---

## SLIDE 6 — CẦN DNH PHỐI HỢP

### 6.1 Hai câu hỏi nghiệp vụ — chặn nhóm câu về khách hàng

1. **Cột `IsAC` trong `FACT_TongHopKhachHang` nghĩa là gì?**
   Đã xác nhận viết tắt là *Active Customer*, nhưng số liệu 3 tháng liên tiếp cho thấy chỉ
   **37–44 khách/tháng trên tổng ~6.000 (0,6%)** mang cờ này, trong khi **~80% khách vẫn đang mua**
   (có cờ `IsRO`). Hai điều đó không thể cùng đúng nếu hiểu `IsAC` là "khách đang hoạt động".
   → **Cần biết tiêu chí gán cờ.** Hiện chatbot buộc phải từ chối câu *"công ty có bao nhiêu khách
   đang hoạt động"* thay vì trả con số 44 gây hiểu nhầm.

2. **Nhóm 8–10% khách (460–640 khách/tháng) không mang cả `IsNC` lẫn `IsRO` nhưng vẫn phát sinh
   doanh thu** — họ là ai?

*(Tin tốt: `IsNC` + `IsRO` + nhóm không cờ = **đúng bằng** tổng số khách, ba tháng liên tiếp,
không dư không thiếu một khách nào. Cấu trúc dữ liệu nhất quán — chỉ thiếu định nghĩa.)*

### 6.2 Các nhóm câu hỏi thiếu nguồn dữ liệu

Không phải thiếu công sức phát triển — **thiếu nguồn**. Muốn phủ thì cần DNH mở thêm:

| Nhóm câu hỏi | Thiếu gì |
|---|---|
| Giá vốn / lợi nhuận | Chưa map được giá vốn và chiết khấu |
| Thu tiền / DSO | Chưa có chứng từ thu tiền theo hoá đơn |
| Thầu / hợp đồng ETC | Chưa map trạng thái tham gia, trúng, thua |
| Viếng thăm / đi tuyến | `DMS_DiTuyen` chưa đưa vào kho |
| Chi nhánh / NPP | Hoá đơn không có khoá chi nhánh |
| Action tracker | Không có nguồn dữ liệu |
| Lịch sử công nợ | Bảng mới bắt đầu ghi 21/08 — cần thời gian tích luỹ |

### 6.3 Quyết định đã chốt kỳ này

- **Báo cáo địa bàn giới hạn 12 tháng gần nhất.** Bảng dữ liệu nén không có khoá tỉnh; suy tỉnh từ
  danh mục khách hiện tại sẽ quy sai vùng cho khách đã chuyển địa bàn. Chọn **nói rõ giới hạn** thay
  vì đưa số có vẻ đầy đủ nhưng sai.
- **Giữ chặt bộ lọc chặn câu hỏi dự báo.** Chấp nhận chặn nhầm vài câu để đổi lấy việc chatbot
  không bao giờ bịa số dự báo.

---

## Phụ lục — Nguồn kiểm chứng

Người đọc muốn tự kiểm, chạy trên máy chủ:

```
python scripts\doi_chieu_so_lieu_tool_moi.py      # 35 phép kiểm bất biến, KHÔNG tốn chi phí AI
python -m pytest tests -q                          # 340 kiểm thử tự động
```

Tài liệu chi tiết: `docs/doi_chieu_138_cau_voi_tool_thuc_te.md`
