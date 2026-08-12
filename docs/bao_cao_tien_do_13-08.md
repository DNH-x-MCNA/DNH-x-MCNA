# Nội dung Báo cáo tiến độ — 13/08/2026

*Soạn 11/08/2026, dựa trên bản 30/07 (giữ nguyên cấu trúc 6 slide). Buổi này **gộp Demo #1 Chatbot
+ báo cáo tiến độ 2 tuần** (dời từ 09/08). Số liệu lấy từ git log thật (`git log --since=2026-07-30`)
và nhật ký sự cố ngày 10-11/08 — **các ô đánh dấu 🔄 cần chạy lại ngay trước buổi họp**.*

> ⚠️ **Lưu ý khi dùng file này**: Slide 3-4 (nhật ký công việc) trộn 2 nguồn — phần "Sự cố production
> 10-11/08" và các bản vá chatbot đi kèm là việc tôi trực tiếp làm và có đầy đủ bằng chứng (log, test,
> kiểm chứng bên ngoài). Phần còn lại (đăng nhập/phân quyền UI, dashboard chi phí, panel admin — phần
> lớn công của `nssiwi19`) tôi chỉ tổng hợp từ **tiêu đề commit** trên GitHub, KHÔNG có ngữ cảnh đầy
> đủ như người trực tiếp làm — nên xác nhận lại với đồng nghiệp trước khi đưa lên slide chiếu.

---

## SLIDE 1 — Title

> **BÁO CÁO TIẾN ĐỘ DỰ ÁN**
> Xây dựng hệ thống cảnh báo kinh doanh, báo cáo định kỳ và AI chatbot cho nội bộ doanh nghiệp
> **Dược Nam Hà (DNH)**
>
> Progress Update + Demo #1 Chatbot
> **Ngày báo cáo: 13/08/2026**

---

## SLIDE 2 — TIMELINE (High-level)

**Đổi mốc "HÔM NAY" → T5 (10/08 – 16/08), đúng ngày demo**

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| **GĐ1 — Khảo sát & Chuẩn bị** | Bravo, VPN, khảo sát & ETL dữ liệu mẫu | ✅ **Hoàn tất** |
| **GĐ2 — Phát triển AI Chatbot** | AI Engine, System Prompt, UI, Security | 🔵 **Đang triển khai** (vá lỗi + tối ưu liên tục) |
| **GĐ3 — UAT & Nghiệm thu Phase 1** | Demo #1, UAT, đào tạo & nghiệm thu | 🟢 **Demo #1: HÔM NAY (13/08)** |
| **GĐ4 — Báo cáo & Go-Live Phase 2** | Cảnh báo Outlook, Demo #2, UAT, Go-Live | ⚡ **Đã hoàn thành phần lớn TRƯỚC HẠN** (Daily Digest + Chất lượng vận hành xong 07/08) |
| **GĐ5 — Hypercare & Đóng dự án** | Theo dõi vận hành, đóng dự án | ⚪ Chưa tới |

**Thông điệp chính của slide:**
> 2 tuần vừa qua tập trung vào **độ tin cậy**: đóng Giai đoạn 4 (báo cáo/cảnh báo) sớm, xử lý dứt
> điểm 1 sự cố production thật (chatbot không đăng nhập được ~14 ngày do tunnel chết), và siết lại
> hàng loạt lỗi âm thầm trong chatbot (gọi tool lặp, bỏ sót nhân viên, bịa số khi thiếu dữ liệu).
> Điểm cần DNH phối hợp: **xác nhận các quy ước nghiệp vụ còn treo** (không đổi từ bản 30/07) và
> **quyết định vai QLV được xem gì** (mục R-H, xem kịch bản demo).

---

## SLIDE 2b — BẢN ĐỒ KIỂM SOÁT DỮ LIỆU 4 LỚP *(cập nhật 12/08 — đã sửa số liệu lạc hậu)*

> ⚠️ **Bản slide đang lưu hành có 3 chỗ sai/lạc hậu, sửa trước khi trình:**
>
> | Chỗ sai trên slide cũ | Số đúng (đếm từ code 12/08) |
> |---|---|
> | *"Đang tạm khóa **9** báo cáo"* | **5** — đã mở 5 tool nhóm (a) từ 03/08, khoá 9 là trạng thái 28/07 |
> | *"**148** nhân viên"* (lớp 4) | Kịch bản demo đang dùng mẫu số **147** ở mọi câu KPI — phải thống nhất 1 số |
> | *"Không có mã nào bị loại oan"* | Đúng **ở tầng báo cáo** (nhờ danh sách ngoại lệ), nhưng dữ liệu gốc vẫn sai — chính là mục **C1** đang chờ DNH, cộng **C3** (6 mã OTC ~484 triệu chưa giải thích được) |

| Lớp | Phạm vi | Trạng thái thật |
|---|---|---|
| **Lớp 4 — Cá nhân (TDV)** | Doanh số & mã từng nhân viên | ✅ Đóng 24/07 — khớp 100% với hệ thống gốc. *Kèm chú thích: 2 nhân viên thật đang bị Bravo gắn nhầm cờ trùng lặp, MCNA vá tạm bằng danh sách ngoại lệ (mục C1)* |
| **Lớp 3 — Quản lý vùng (21 QLV)** | Tổng đội từng QLV | 📍 Đang xử lý — đã sửa lỗi cộng chồng (QLV bị gấp đôi do cộng cả TDV lẫn QLV) và tách ngưỡng KPI theo vai trò (quản lý 70%, nhân viên 65%). **Còn khoá 5 tool** (kho, công nợ, lịch sử đổi QLV, đối chiếu doanh thu, kiểm đơn bất thường) — chờ DNH chốt QLV được xem tới đâu |
| **Lớp 2 — Vùng (3 miền)** | Doanh thu & công nợ theo miền | ⏳ Chờ DNH soát — lệch 0đ **tại lần kiểm chứng 30/07** |
| **Lớp 1 — Toàn công ty** | Doanh thu, công nợ, KPI, tồn kho | ⏳ Chờ DNH soát — lệch 0đ **tại lần kiểm chứng 30/07** |

> 🔴 **Điểm phải nói thẳng nếu bị hỏi**: con số "lệch 0 đồng" ở Lớp 1 & 2 được kiểm chứng lần cuối
> **30/07**. Từ đó tới nay có **91 commit**, nhiều commit đụng thẳng logic doanh thu/KPI/phân quyền.
> **Chưa chạy lại kiểm chứng** (công cụ đã viết sẵn: `scripts/verify_rh_a_tools.py`, cần chạy trên
> máy có dữ liệu thật). Trình "lệch 0đ" như trạng thái hôm nay là đang dựa vào số của 2 tuần trước.

---

## SLIDE 3 — Nhật ký công việc (1/2): Sự cố production & độ tin cậy chatbot

**Kỳ 30/07 – 13/08/2026**

### 🔴 Sự cố thật: chatbot không đăng nhập được, âm thầm suốt ~14 ngày

Phát hiện 10/08 khi người dùng báo lỗi *"Failed to execute 'json' on 'Response'"* lúc đăng nhập.
Truy nguyên ra **4 lớp lỗi chồng nhau**, mỗi lớp che khuất lớp dưới:

| # | Lớp lỗi | Xử lý |
|---|---|---|
| 1 | Tầng trung gian (proxy) giữa web và máy chủ không đọc được lỗi, trả về trang trống | Đọc + dịch lỗi thành thông báo tiếng Việt rõ ràng |
| 2 | Đường hầm kết nối tới máy chủ tự chết sau mỗi lần khởi động lại máy, không ai biết | Cài dịch vụ tự giám sát, tự phục hồi + tự cập nhật, **đã kiểm chứng qua mô phỏng khởi động lại máy — PASS** |
| 3 | 2 tiến trình quản lý cùng tranh nhau 1 đường hầm, phá lẫn nhau mỗi lần cập nhật code | Gộp về đúng 1 nơi quản lý duy nhất |
| 4 | Sai cấu hình ở nơi lưu trữ web (trỏ nhầm thư mục cũ) | Đã sửa qua Dashboard, xác nhận web nhận đúng code mới |

**→ Đã kiểm chứng từ bên ngoài (không chỉ tin log nội bộ): trang chủ + đăng nhập hoạt động đúng,
kể cả sau khi mô phỏng khởi động lại máy chủ.**

### Vá 6 lỗi âm thầm khác trong chatbot (phát hiện khi kiểm tra sâu, không phải khách báo)

Chủ động rà lại chatbot trước demo, phát hiện và vá:

1. **Chatbot tự gọi lặp không cần thiết** rồi từ chối trả lời ("câu hỏi quá phức tạp") — nguyên nhân
   là hướng dẫn nội bộ cho AI chưa đủ rõ, không phải do dữ liệu hay giới hạn kỹ thuật.
2. **Cơ chế gộp câu hỏi hàng loạt (tiết kiệm chi phí) có lỗi**: khi hỏi 2 điều khác nhau về cùng 1
   người (vd "so sánh tháng 7 với tháng 8"), hệ thống **âm thầm bỏ mất 1 nửa câu hỏi** mà không báo
   — chatbot trả lời tự tin bằng dữ liệu thiếu. Lỗi này có ở **cả 2 đường xử lý câu hỏi** (thường +
   trả lời dần từng chữ) vì được viết tay 2 lần — nay gộp về 1 chỗ để không lệch nhau nữa.
3. **1 công cụ tính dự báo doanh thu bị lỗi 100% số lần gọi** (không phải thỉnh thoảng) — đã gỡ hẳn
   khỏi danh sách chatbot được dùng thay vì để nó âm thầm bịa số khi hỏi "dự báo tháng 8".
4. **1 nhân viên thật (QLV, chỉ tiêu 5,28 tỷ) bị chatbot bỏ sót** khi tự viết truy vấn dữ liệu — do
   Bravo gắn nhầm cờ "trùng lặp" cho người này (xem mục C1 tài liệu câu hỏi DNH). Đã dặn chatbot rõ
   ràng: gặp trường hợp này phải tính, không được bỏ qua.
5. Phát hiện **cùng 1 người vừa đứng đầu cả vùng vừa xuất hiện như "nhân viên" dưới quyền chính
   mình** trong dữ liệu Bravo (bằng chứng củng cố thêm cho câu hỏi A4 gửi DNH) — chatbot nay tự cảnh
   báo nghi vấn này thay vì trình bày như bình thường.
6. Cảnh báo "dữ liệu có thể đang cũ" (viết xong từ trước) **chưa từng được bật** — nay đã nối vào
   đúng chỗ, chatbot sẽ tự nói nếu tiến trình đồng bộ dữ liệu bị treo.

**→ Toàn bộ đã kiểm chứng bằng dữ liệu thật trên hệ thống đang chạy (không phải chỉ đọc code), có
ghi lại bằng chứng cho từng lỗi.**

---

## SLIDE 4 — Nhật ký công việc (2/2): Báo cáo định kỳ & các cải tiến khác

**Kỳ 30/07 – 13/08/2026**

### Báo cáo định kỳ — Giai đoạn 4, đóng sớm (07/08)
- Đưa mục **"Cảnh báo lặp lại trong kỳ"** vào Daily Digest — gộp các cảnh báo lặp, tránh làm phiền.
- Thêm mục **"Chất lượng vận hành"** (nhịp KPI theo ngày, đối chiếu doanh thu vs KPI, tỷ lệ hàng trả
  về ETC) — **đặt sau cờ tắt mặc định** theo đúng tiền lệ dự án (bật thử nghiệm trước khi cho chạy
  thật với 6 nhóm người nhận), và bổ sung luôn vào email Tuần/Tháng (trước đây chỉ có ở Teams).
- Dọn 1 tham số kỹ thuật không dùng tới (đã có từ trước nhưng chưa từng hoạt động, không ảnh hưởng
  số liệu hiển thị).

### Chatbot — các cải tiến khác *(phần lớn việc của đồng nghiệp, tổng hợp từ tiêu đề commit)*
- Bổ sung **giao diện quản trị tài khoản** (tạo người dùng, phân vai trò, phân vùng/kênh phụ trách).
- Bổ sung **nhật ký bảo mật** (đăng nhập, đổi mật khẩu, thao tác quản trị) tách riêng khỏi nhật ký
  truy vấn dữ liệu.
- Bổ sung **bảng theo dõi chi phí AI theo tuần**, lọc theo người dùng/chức vụ/ngày cụ thể.
- Chatbot trả lời theo kiểu **hiện chữ dần** thay vì chờ xong mới hiện — giảm cảm giác chờ đợi.
- Nhiều lượt tối ưu chi phí gọi AI (đã đo thật, xem mục "Kiểm tra chất lượng" — 1 lần tối ưu quá tay
  từng làm tăng tỷ lệ chatbot từ chối trả lời từ 0,5% lên 27%, đã phát hiện và gỡ bỏ kịp thời).

---

## SLIDE 5 — OVERALL STATUS UPDATE

### VIỆC ĐANG LÀM / SẮP TỚI

- **Demo #1 Chatbot — diễn ra hôm nay (13/08)**, gộp luôn báo cáo tiến độ này.
- **Cần chạy kiểm chứng cuối trước khi cho vai QLV hỏi doanh thu** (đã có sẵn công cụ kiểm tự động,
  so tổng cả đội với cộng dồn từng nhân viên — cần chạy trên máy chủ thật trước giờ demo).
- **Chờ DNH xác nhận các điểm nghiệp vụ đã gửi** — không đổi so với bản 30/07, **5 điểm ưu tiên**
  vẫn treo:
  1. Cách tính ngày quá hạn & xác nhận báo cáo công nợ chuẩn
  2. Mốc phân nhóm tuổi nợ
  3. Nguồn giá để tính giá trị tồn kho *(thiếu nên mục "tồn kho chết" luôn hiển thị 0)*
  4. Chỉ tiêu cấp vùng vs cá nhân *(có thêm bằng chứng mới — 1 người vừa là trưởng vùng vừa "là nhân
     viên của chính mình" trong dữ liệu, càng củng cố nghi vấn trùng bản ghi)*
  5. Kênh ETC có giao chỉ tiêu theo từng nhân viên không
  6. **[Mới]** QLV có được xem tồn kho/công nợ của vùng không, hay chỉ từ Trưởng phòng trở lên?
- Chuẩn bị **ước tính chi phí go-live** (cam kết tuần 8–10, vẫn trong hạn).

### MILESTONES

| Mốc | Hạn | Trạng thái |
|---|---|---|
| **M1 — Dữ liệu + AI Engine sẵn sàng** | 19/07 | ✅ Kỹ thuật hoàn thành — **chờ DNH nghiệm thu** |
| **M2 — Demo #1 Chatbot** | 13/08 (dời từ 09/08) | 🟢 **Diễn ra hôm nay** |
| **M4 — Demo #2 Cảnh báo Outlook** | 06/09 | ⚡ Nội dung đã sẵn sàng sớm |
| **Đóng dự án** | 30/09 | ⚪ |

### 🔄 Số liệu hệ thống đang vận hành *(cần chạy lại trước buổi họp)*

```
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

---

## SLIDE 6 — RISK & MITIGATION

| # | Rủi ro | Mức | Biện pháp xử lý |
|---|---|---|---|
| 1 | **Sự cố tunnel/đăng nhập tái diễn** trước/trong lúc demo — đã xảy ra 3 lần trong tuần này | 🟢 Thấp *(đã xử lý gốc rễ 11/08)* | Gộp về 1 dịch vụ quản lý duy nhất, đã kiểm chứng qua mô phỏng khởi động lại; khuyến nghị sau demo chuyển sang hạ tầng ổn định hơn (tên miền cố định thay vì đường hầm tạm) |
| 2 | **5+1 điểm nghiệp vụ chưa được DNH chốt** → số liệu còn dùng giả định | 🔴 Cao | Không đổi so với 30/07 — đề nghị chốt tại buổi demo hôm nay |
| 3 | **Chatbot có thể trình bày sai dữ liệu vai QLV** (5 công cụ vừa mở lại cho vai này) nếu chưa kiểm chứng kỹ trước demo | 🟠 TB | Có sẵn công cụ kiểm tự động, đối chiếu tổng đội vs cộng dồn từng người — cần chạy trên máy thật trước giờ demo |
| 4 | **2 người cùng sửa 1 phần code song song không kiểm tra chéo** — đã gây ra đúng 1 lỗi thật tuần này (lỗi gộp câu hỏi bị chép tay lần 2 mang theo cả lỗi cũ) | 🟠 TB | Đã gộp về 1 nơi xử lý chung, không còn 2 bản chép tay; khuyến nghị thống nhất quy trình kiểm tra trước khi đẩy code lên chung |
| 5 | **Dữ liệu gốc Bravo có cờ/mã sai** (2 quản lý thật bị ẩn khỏi báo cáo, 6 mã nhân viên không xác định ≈484 triệu) | 🟠 TB | Đã vá tạm ở tầng code (kể cả nhánh chatbot tự viết truy vấn); đề nghị DNH sửa gốc |

---

## SLIDE 7 — Kết

> Cảm ơn đã lắng nghe
> **MCNA Technology**

---

## Ghi chú khi dựng slide

- **Giữ nguyên template & bố cục** bản 16/07 để nhất quán, chỉ thay nội dung.
- **Slide 2**: dời dải "HÔM NAY" sang **T5 (10/08–16/08)**, đổi màu GĐ3 sang đang diễn ra.
- **Không đưa tên nhân viên cụ thể** lên slide chiếu chung ở phần lỗi dữ liệu — chỉ nói "1 nhân
  viên"/"2 quản lý"; danh tính đã có trong tài liệu gửi riêng (`Cau_hoi_can_DNH_xac_nhan.md`).
- **Phần "sự cố production" (slide 3)** nên trình bày điềm tĩnh, tập trung vào cách xử lý và kiểm
  chứng — không cần đi sâu chi tiết kỹ thuật trên slide chiếu, giữ ở mức tóm tắt như bảng trên.
- **Trước khi trình bày slide 4 phần "việc của đồng nghiệp"**: xác nhận lại với `nssiwi19` — phần đó
  chỉ tổng hợp từ tiêu đề commit GitHub, chưa được người trực tiếp làm xác nhận nội dung.

## Lệnh lấy lại số liệu trước buổi họp

Chạy trong `D:\DNH` (cần dữ liệu Bravo thật đồng bộ tới máy đang chạy lệnh — dev machine hiện KHÔNG
kết nối được, phải chạy trên máy chủ hoặc máy có kết nối Bravo):

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
