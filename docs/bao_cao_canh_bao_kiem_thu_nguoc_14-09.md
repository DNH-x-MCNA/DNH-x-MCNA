# Cảnh báo và báo cáo định kỳ: kiểm thử ngược trên lịch sử thật (14/09/2026)

**Mục đích:** cảnh báo nào thật sự báo đúng việc cần làm, cảnh báo nào chỉ gây nhiễu; đề xuất bộ cảnh báo
thay thế và các ngưỡng cần DNH chốt.

**Cách làm:** chạy lại từng quy tắc cảnh báo trên dữ liệu Bravo 01/2025–09/2026 (chỉ đọc, không gửi gì,
không gọi model). Với mỗi quy tắc đo hai điều: bắn bao nhiêu lần, và những lần bắn có rơi đúng vào
tháng / khách / đội thật sự xấu hay không. Số liệu dưới đây là kết quả đo, không phải ước lượng.

**Trạng thái:** code và test đã xong trên nhánh `claude/canh-bao-kiem-thu-nguoc`, **chưa deploy, chưa bật
gửi thật**. Chưa ngưỡng nào được DNH chốt.

---

## 1. Kết luận chính

Phần lớn cảnh báo cũ không mang thông tin: hoặc bắn gần như liên tục, hoặc không bao giờ bắn.

| Cảnh báo cũ | Kết quả đo | Vấn đề |
|---|---|---|
| Doanh thu sụt giảm >20% so cùng số ngày tháng trước | OTC bắn 28% số ngày, 38% ở tuần đầu tháng | Đầu tháng luôn "giảm" giả |
| Lũy kế ngày 10/20 giảm >5% so TB 5 tháng (theo kênh) | OTC 17/30 lần, ETC 13/30 lần | Ngưỡng 5% nhỏ hơn dao động bình thường |
| Nhịp KPI ngày từng TDV (<3% chỉ tiêu tháng/ngày = Đỏ) | TB **78%** TDV bị Đỏ mỗi ngày | Doanh số dược đến theo đơn lớn, không rải đều |
| Lũy kế ngày 10/20 từng TDV giảm >5% | ~90 TDV/tháng; 56% đúng so với tỷ lệ nền 46% | Gần như ngẫu nhiên |
| Khách lớn giảm >50% so tháng trước | ~120 khách OTC/tháng, chỉ 38% đúng | So tháng đang chạy dở với cả tháng trước |
| Khách quá hạn >10tr vẫn lên đơn | 134 khách/tháng | Không ai xử lý hết |
| Nợ quá hạn lớn (top 5) | Gửi 16 lần trong 11 ngày, cùng một danh sách | Là báo cáo, không phải sự kiện |
| Tỷ lệ nợ quá hạn (OTC >80%, ETC >65%) | Thực tế OTC 59,1%, ETC 38,8% | **Không bao giờ bắn** |
| Tập trung doanh thu (top 3 khách >50%) | Top 3 chỉ 8–23% | **Không bao giờ bắn** |

**Gốc của nhóm "bắn liên tục": doanh thu dồn cuối tháng.**

| | Lũy kế tới ngày 5 | ngày 10 | ngày 15 | ngày 20 | ngày 25 |
|---|---|---|---|---|---|
| OTC (TB, min–max 12 tháng) | 8% (5–11%) | 21% (14–37%) | 38% (22–60%) | 50% (37–71%) | 72% (61–85%) |
| ETC | 18% (9–32%) | 37% (24–63%) | 54% (41–74%) | 69% (63–79%) | 85% (76–94%) |

OTC có 28% doanh thu tháng rơi vào ngày 26 trở đi. Mọi phép so "chia đều theo ngày" vì vậy báo động giả
đầu tháng. Bộ cảnh báo mới so với **đường cong lũy kế thật của 3 tháng trước**.

---

## 2. Bộ cảnh báo mới

| # | Cảnh báo | Quy tắc (mặc định) | Kết quả kiểm thử | Mức, gửi tới |
|---|---|---|---|---|
| 1 | Doanh thu kênh chậm nhịp tháng | So lũy kế với nhịp thường lệ 3 tháng trước. ETC chậm >20% từ ngày 8; OTC chậm >30% từ ngày 10 | ETC: bắn 14% số ngày, 93% lần bắn nằm trong tháng xấu, bắt 4/4 tháng xấu. OTC: 17%, 77%, bắt 5/5 | Nghiêm trọng; C-Level, quản lý kênh |
| 2 | Đội QLV có nguy cơ hụt chỉ tiêu | Đội ≥3 TDV, từ ngày 15, dự phóng cuối tháng <60% chỉ tiêu | Ngày 15: ~7/18 đội/tháng, 72% thật sự cuối tháng <80%. Ngày 20: ~5 đội, **90%** | Cảnh báo; theo miền |
| 3 | Khách mua đều chưa có đơn tháng này | Mua đủ 6/6 tháng; tới ngày 20 chưa có đơn; nền OTC ≥50tr/tháng, ETC ≥100tr | OTC ~11 khách/tháng, 47% cả tháng mua <30% thường lệ; ETC ~5 khách/tháng, **81%** | Cảnh báo; theo miền và kênh |
| 4 | Khách mới rơi vào nợ >45 ngày | Nợ >45 ngày >50tr, bản chụp 7 ngày trước chưa có | 04/08→14/09: 27 khách, 3,76 tỷ (ETC 25, OTC 2) | Nghiêm trọng; theo miền |
| 5 | Nợ >45 ngày vẫn lên đơn | Nợ >45 ngày ≥50tr và có đơn trong tháng | 14/09: 14 khách, đơn 1,42 tỷ (quy tắc cũ: 134 khách) | Nghiêm trọng; theo miền |
| 6 | Hàng trả ETC tăng bất thường | 30 ngày trượt, tỷ lệ >3% và giá trị ≥200tr | Tháng thường 0,04–1,15%; riêng 04/2026 là 7,82% (2,2 tỷ) | Cảnh báo; C-Level, kênh ETC |

Mỗi đối tượng chỉ báo một lần trong kỳ; trong 7 ngày chỉ nhắc lại khi tình hình xấu thêm một bậc
(ví dụ chậm nhịp từ 30% lên 40%).

**Ngừng gọi** (code còn giữ để tham chiếu): nợ quá hạn top 5, tiến độ KPI TDV dưới 60%, báo cáo phân tích KPI
theo chức danh, doanh thu sụt giảm kiểu cũ, tỷ lệ nợ quá hạn, khách lớn sụt giảm, tập trung doanh thu,
nhịp KPI ngày, mốc 10/20, khách quá hạn >10tr lên đơn, nợ chuyển nhóm so bản chụp tháng trước.

**Giữ nguyên:** nhân sự có chỉ tiêu mà doanh số bằng 0; đối chiếu doanh thu KPI với hóa đơn; ETL đứng và
dữ liệu rỗng; hạn mức tín dụng và cận date (chưa có dữ liệu nguồn); rủi ro KPI theo QĐ 0429-2 (đang tắt,
chờ DNH duyệt).

---

## 3. Thay đổi báo cáo định kỳ

- Email tuần/tháng và Teams ngày thêm **Tiến độ tháng**: lũy kế từng kênh so với nhịp thường lệ, dự phóng
  cả tháng.
- Hai mục **"Cảnh báo trong kỳ"** và **"Điểm nổi bật"** (đọc lại log cảnh báo đã gửi, phần lớn là cảnh báo
  lặp) được thay bằng **"Việc cần xử lý"**: tính ngay lúc dựng báo cáo theo đúng các quy tắc 2–5, đã lọc
  theo miền/kênh của người nhận.
- Số tiền viết kiểu Việt Nam ("12,35 tỷ đ") thay cho "12,345,678,900 đ".
- Teams ngày bỏ "% so hôm qua": báo cáo gửi 17:45 khi hóa đơn hôm nay còn đang nhập, nên phép so luôn ra
  "giảm" giả.

---

## 4. Insight điều hành rút ra từ dữ liệu

**KPI TDV (13 tháng chốt, 08/2025–08/2026)**

- Tháng thường: trung vị hoàn thành 85–101%. Tháng yếu: 01/2026, 05/2026, 06/2026 (trung vị 70–71%, khoảng
  100/150 TDV dưới 80%).
- Tính bền: TDV dưới 65% tháng này thì **53%** tháng sau vẫn dưới 65%, gấp đôi tỷ lệ nền 25%.
- 13 TDV dưới 65% cả tháng 07 và 08/2026.

**Theo miền (hoàn thành chỉ tiêu tháng, tầng TDV)**

- Miền Bắc tụt mạnh 05–07/2026 (66%, 63%, 74%), là nguồn chính của các tháng yếu.
- Miền Trung yếu kéo dài: 60–83% suốt 12 tháng.
- Miền Nam dao động mạnh: 60–121%.

**Công nợ (14/09/2026)**

| Kênh | Dư nợ | Tỷ lệ quá hạn | Trong quá hạn, phần >45 ngày |
|---|---|---|---|
| ETC | 157,7 tỷ | 38,8% | 59,7% |
| OTC | 18,8 tỷ | 59,1% | 10,9% |

Theo miền, tỷ lệ quá hạn cao nhất là OTC Miền Trung 84,6% và OTC MB2 77,1%. Top 10 khách chiếm 37% nợ quá
hạn OTC và 24% nợ quá hạn ETC.

**Khác**

- Không có rủi ro tập trung khách: tháng 08/2026 top 10 khách chỉ chiếm 30% doanh thu OTC và 27% ETC.
- OTC bán đều T2–T7 (14–18%/ngày), Chủ nhật bằng 0. ETC chỉ T2–T6.
- Hàng trả ETC: bảng `BRVSX_TraLai` và dòng âm trong view hóa đơn ETC lệch nhau ở một số tháng (01/2026: 598
  so với 343 triệu), cần xác định nguồn chuẩn.

---

## 5. Cần DNH chốt

| # | Nội dung | Đề xuất hiện tại |
|---|---|---|
| 1 | Ngưỡng chậm nhịp doanh thu từng kênh và ngày bắt đầu đánh giá | ETC 20% từ ngày 8; OTC 30% từ ngày 10 |
| 2 | Ngưỡng dự phóng đội QLV và ngày đánh giá | <60% từ ngày 15 (hoặc chờ ngày 20 để chính xác 90%) |
| 3 | Thế nào là "khách mua đều" và ngưỡng khách lớn từng kênh | 6/6 tháng; OTC ≥50tr, ETC ≥100tr/tháng |
| 4 | Ngưỡng nợ >45 ngày cho cảnh báo khách mới và khách vẫn lên đơn | 50tr |
| 5 | Nguồn chuẩn cho hàng trả ETC và ngưỡng tỷ lệ | `BRVSX_TraLai`; >3% và ≥200tr / 30 ngày |
| 6 | Ai nhận từng loại cảnh báo trên Teams | Như bảng mục 2 |

Mọi ngưỡng nằm trong `config/config.yaml` mục `thresholds.business.insight_rules`, đổi không cần sửa code.

---

## 6. Giới hạn cần biết

- Kiểm thử trên 8–14 tháng, trong đó 2026 có nhiều tháng yếu; độ chính xác có thể khác khi kinh doanh ổn định.
- Dự phóng đội QLV lấy doanh số từ snapshot KPI, còn đường cong lấy từ hóa đơn toàn công ty OTC.
- Cảnh báo "khách mới vào nợ >45 ngày" cần bản chụp công nợ tích lũy; máy mới cần đủ 7 ngày mới bắt đầu báo.
- Báo cáo riêng từng QLV chưa dùng các mục mới.
