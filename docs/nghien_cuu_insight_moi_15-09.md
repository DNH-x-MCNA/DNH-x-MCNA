# Nghiên cứu insight cảnh báo mới: kiểm thử ngược trên lịch sử thật (15/09/2026)

**Mục đích:** tìm thêm cảnh báo có ý nghĩa thật, ngoài 6 cảnh báo đã chốt ở
`docs/bao_cao_canh_bao_kiem_thu_nguoc_14-09.md`. Chỉ đề xuất quy tắc đạt đủ ba điều kiện:
1. độ chính xác cao hơn hẳn tỷ lệ nền;
2. khoảng 15 dòng/tháng trở xuống cho mỗi người nhận;
3. có hành động và người chịu trách nhiệm rõ.

**Cách làm:** cùng phương pháp 14/09.
- Dữ liệu: Bravo, chỉ đọc, dữ liệu đến 14/09/2026. Không gửi gì, không gọi model.
- Mỗi ứng viên đo bốn điều: bắn bao nhiêu lần, lần bắn có rơi vào kết cục xấu thật không, tỷ lệ nền (kết cục xấu
  xảy ra bao nhiêu khi không lọc gì), khối lượng mỗi tháng.
- Chỉ dùng dữ liệu trước thời điểm bắn, không nhìn trước.

**Trạng thái:**
- Hai quy tắc A/B đã được code vào bundle báo cáo ngày 15/09, sau cờ
  `insight_etc_sku_stop` / `insight_new_customer_no_repeat`; cả hai cờ mặc định **false**, chưa bật, chưa deploy.
- Script tái lập: `scripts/nghien_cuu_insight.py`, test tại `tests/test_nghien_cuu_insight.py`.
- Dữ liệu kéo về ở `results/nghien_cuu_insight/`, không commit.

---

## 1. Kết luận

| # | Ứng viên | Kết luận | Lý do chính |
|---|---|---|---|
| A | Khách ETC lớn ngừng một SKU chủ lực | **Đề xuất** | 60% lần bắn là bỏ thật (nền 13%), ~3 dòng/tháng |
| B | Khách mới không mua lại | **Đề xuất có điều kiện** | OTC đơn đầu ≥20tr: 43% mất (nền 8%), ~1,5 dòng/tháng. ETC: 71% (nền 42%) |
| C | Hợp đồng ETC sắp hết hạn, thực hiện thấp | **Không làm cảnh báo; đưa vào báo cáo tháng ETC** | Gần như không bao giờ bù kịp, nên không có việc để "cứu". Cần DNH xác nhận giá trị hợp đồng là trần |
| D | Nợ sắp chạm 45 ngày | Loại | ETC: 75% khoản 31–45 ngày trượt sang >45 dù lọc hay không; OTC chính xác thấp hơn nền |
| E | Đội QLV mất độ phủ khách | Loại | Chỉ lặp lại "đội đang yếu thì tháng sau yếu" |
| F | Chỉ tiêu còn lại vượt năng lực lịch sử | Loại | OTC toàn quốc **chưa tháng nào đạt 100%** trong 20 tháng: báo "sẽ hụt" không thêm thông tin |
| G | Hàng trả OTC bất thường theo khách | Loại | Đo ở bước khảo sát: dòng trả trên hóa đơn OTC quá nhỏ để có tín hiệu |
| H | Dự phóng đội bằng rollup QLV | Giữ cách cộng TDV | Rollup không tăng độ chính xác ở ngày 15 hoặc 20 |

---

## 2. Chi tiết từng ứng viên

### A. Khách lớn ngừng một SKU chủ lực (đề xuất cho ETC)

**Quy tắc:**
- Cặp (khách, SKU) được coi là **mua đều** khi có mua ít nhất 5/6 tháng trước, trung bình ≥ ngưỡng/tháng.
- Tới ngày 20, khách **vẫn có đơn** nhưng chưa lấy SKU đó → bắn.
- Khác cảnh báo 3 ("khách mua đều chưa có đơn"): khách vẫn mua, chỉ bỏ mặt hàng chủ lực.

**Kết cục xấu:** SKU đó không có doanh thu cả tháng này lẫn tháng sau.

**Kỳ đánh giá:** 01/2025–07/2026.

| Kênh | Ngưỡng TB/tháng | Cặp đánh giá | Bắn TB/tháng | Tháng nhiều nhất | Bỏ thật | Tỷ lệ nền | Doanh thu/tháng của các cặp bỏ thật |
|---|---|---|---|---|---|---|---|
| ETC | 100tr | 235 | **2,7** | 6 | **59,6%** | 13,2% | ~384tr |
| ETC | 30tr | 592 | 7,7 | 15 | 58,2% | 14,4% | ~531tr |
| OTC | 30tr | 1.665 | 24,1 | 58 | 25,5% | 7,1% | ~532tr |
| OTC | 10tr | 4.913 | 71,1 | 109 | 30,1% | 8,3% | ~781tr |

**Đọc số:**
- ETC ngưỡng 100tr: cứ 5 dòng thì 3 dòng là khách bỏ hẳn mặt hàng hai tháng liền.
- Mỗi tháng chỉ vài dòng: TDV ETC gọi hỏi được ngay (hết thầu? đổi nhà cung cấp? hết hàng?).
- OTC: độ chính xác chỉ ~30%, 24–71 dòng/tháng. Không đạt.

**Rủi ro cần kiểm khi code:** SKU ETC có thể dừng vì gói thầu hết hạn. Nên ghi kèm hợp đồng còn hiệu lực của khách
(nguồn `vHopDongETC`) để người nhận biết ngay.

**Đã code 15/09:** mỗi dòng kèm danh sách hợp đồng đã bắt đầu và chưa hết hạn của khách; cờ mặc định tắt.

### B. Khách mới không mua lại

**Quy tắc:**
- Khách mới = đơn đầu tiên, trước đó ít nhất 12 tháng không có đơn nào.
- Sau k ngày chưa có đơn thứ hai → bắn.

**Kết cục xấu:** vẫn không có đơn nào trong 90 ngày tiếp theo.

**Tỷ lệ nền:** tỷ lệ mất trong **mọi** khách mới.

| Kênh | Chờ k ngày | Đơn đầu tối thiểu | Khách mới | Bắn TB/tháng | Mất thật | Tỷ lệ nền | Tự quay lại dù không báo |
|---|---|---|---|---|---|---|---|
| OTC | 45 | 20tr | 116 | **1,5** | **42,9%** | 7,8% | 57,1% |
| OTC | 45 | 5tr | 684 | 6,1 | 34,0% | 10,7% | 66,0% |
| OTC | 30 | 5tr | 691 | 9,0 | 25,7% | 11,7% | 74,3% |
| OTC | 45 | không | 9.626 | 158,5 | 52,3% | 30,2% | 47,7% |
| ETC | 60 | 20tr | 160 | **3,0** | **71,3%** | 41,9% | 28,7% |
| ETC | 45 | 20tr | 163 | 3,2 | 65,1% | 42,3% | 34,9% |

**Đọc số:**
- OTC không lọc giá trị đơn đầu: ~160 khách/tháng, phần lớn là đơn lẻ nhỏ. Không ai xử lý hết.
- OTC lọc đơn đầu ≥20tr: chỉ ~1,5 khách/tháng. Gần một nửa sẽ mất nếu không ai gọi lại. Việc rõ cho TDV/QLV.
- ETC: ngay cả khách mới lớn cũng mất 42%. Lọc 60 ngày nâng lên 71%, ~3 khách/tháng.

**Điều kiện:** cần DNH chốt ngưỡng đơn đầu và số ngày chờ. Số liệu này chưa trừ khách mở mã mới cho đơn thầu một lần.

**Đã code 15/09:** báo đúng một lần vào ngày vừa chạm mốc 45/60 để khách không nằm mãi trong danh sách; cờ mặc
định tắt. Đơn được gom theo `Stt`, nên hai đơn dương cùng ngày vẫn được nhận đúng là đã có đơn thứ hai.

### C. Hợp đồng ETC sắp hết hạn, thực hiện thấp

**Quy tắc:** còn 60 hoặc 90 ngày tới hạn, đã xuất hóa đơn < 50% giá trị hợp đồng.

**Kết cục xấu:** tới hạn + 60 ngày vẫn thực hiện < 70%.

**Cách tính:**
- Giá trị hợp đồng lấy **trước VAT** (`AmountBefVat`).
- So với `Amount9` trên hóa đơn. `Amount9` là doanh thu trước VAT: T8/2026 `Amount9` = `Quantity×UnitPrice`,
  VAT (`Amount3`) = 5,0%.
- Khóa nối là `vHoaDonETCTotal.ContractId` = `vHopDongETC.Id`.
- Hợp đồng hết hạn 01/2024–07/2026.

| Mốc | Còn lại tối thiểu | Hợp đồng | Bắn TB/tháng | Kết thúc < 70% | Tỷ lệ nền | Bù kịp (trung vị) | Có hợp đồng mới cùng khách |
|---|---|---|---|---|---|---|---|
| 90 ngày | bất kỳ | 2.510 | 52,7 | 79,6% | 58,2% | 0% | 33,5% |
| 90 ngày | 500tr | 314 | 8,7 | 85,5% | 76,1% | 0,9% | 38,8% |
| 60 ngày | 500tr | 303 | 8,8 | 89,8% | 80,5% | 0% | 39,0% |

**Phân bố mức thực hiện cuối cùng** (3.685 hợp đồng):

| Mức thực hiện cuối | Số hợp đồng | Tỷ lệ |
|---|---|---|
| Không xuất hóa đơn nào | 843 | 23% |
| < 30% | 451 | 12% |
| 30–70% | 575 | 16% |
| 70–100% | 833 | 23% |
| > 100% | 983 | 27% |

**Đọc số:**
- Hợp đồng dưới 50% khi còn 60–90 ngày **gần như không bao giờ bù kịp**: trung vị phần bù ~0%.
- Báo trước không cứu được doanh thu. Hợp đồng thầu bệnh viện nhiều khả năng là **mức trần**, bệnh viện gọi hàng
  theo nhu cầu.
- ~35–39% trường hợp thực hiện thấp có hợp đồng mới cùng khách quanh ngày hết hạn: bị thay thế, không phải mất.

**Đề xuất:**
- Không làm cảnh báo.
- Đưa vào báo cáo tháng kênh ETC một bảng "hợp đồng sắp hết hạn, còn ≥500tr chưa thực hiện" (~9 dòng/tháng).
  Mục đích là rà lý do và chuẩn bị gói thầu kỳ sau.

**Lưu ý dữ liệu:**
- Tổng giá trị không đáng tin vì còn hợp đồng ghi giá trị hỏng. Ví dụ khách TBI00509 có 25,8 tỷ không xuất đồng
  nào. Nên đọc theo **số hợp đồng**, không theo tổng tiền.
- Công cụ hợp đồng ETC trong `backend/report_templates.py` từng chia hóa đơn trước VAT cho giá trị hợp đồng
  **sau VAT**, nên tỷ lệ thực hiện thấp hơn thật khoảng 5%.
  **Đã sửa 15/09** (sau khi nhánh Codex được gộp): giá trị hợp đồng lấy `AmountBefVat`.
- Bộ kiểm tra bản ghi hỏng của công cụ đó cũng đã sửa, đo trên 9.138 hợp đồng:

  | | Cách cũ | Luật mới |
  |---|---|---|
  | Quy tắc | sau VAT lệch `Quantity×UnitPrice` > 5% | trước VAT lệch `Quantity×UnitPrice` > 5%, hoặc đơn giá > 1 tỷ, hoặc sau/trước VAT chênh quá 2 lần |
  | Số hợp đồng bị tách | 70 | 60 |
  | Bắt HD 115627 (đơn giá 295 tỷ) | Không | Có |
  | Tách oan hợp đồng thuế 8% | 9 | 0 |
  | Tổng phần "sạch", kể cả hết hạn | 2,96 triệu tỷ | 3.548 tỷ (lớn nhất 107 tỷ) |
- Script nghiên cứu này kiểm tra bản ghi hỏng theo `AmountBefVat`, không bắt được hợp đồng hỏng nào. Vì vậy các
  bảng mục C ở trên chỉ đọc theo số hợp đồng.

### D. Nợ sắp chạm 45 ngày (loại)

**Quy tắc:** khoản 31–45 ngày ≥ ngưỡng, khách chưa có nợ >45 ngày → bắn.

**Kết cục xấu:** sau 14 ngày nợ >45 ngày tăng ít nhất một nửa khoản đó.

**Dữ liệu:** 53 bản chụp công nợ thứ Hai hằng tuần, 01/09/2025–14/09/2026.

| Kênh | Ngưỡng | Bắn TB/tuần | Trượt thật | Tỷ lệ nền |
|---|---|---|---|---|
| ETC | 50tr | 17,5 | 75,8% | 75,4% |
| ETC | 100tr | 9,6 | 74,8% | 75,4% |
| OTC | 50tr | 0,5 | 44,8% | 73,5% |

**Đọc số:**
- ETC: ba phần tư các khoản 31–45 ngày trượt sang >45 ngày, **bất kể lớn nhỏ**. Ngưỡng không lọc ra gì. Đây là
  nhịp thanh toán thường lệ của bệnh viện, không phải dấu hiệu bất thường.
- Khối lượng 10–30 dòng/tuần.
- Cảnh báo 4 hiện có (khách mới rơi vào nợ >45 ngày) đã bắt đúng sự kiện này khi nó xảy ra.
- OTC hiếm khi bắn, và khi bắn chính xác thấp hơn nền.

### E. Đội QLV mất độ phủ khách hoạt động (loại)

**Quy tắc:** số khách có mua của đội tháng M giảm ≥ X% so với trung bình 3 tháng trước.

**Kết cục xấu:** tháng M+1 đội đạt < 80% chỉ tiêu.

**Kỳ đánh giá:**
- Đội đạt từ 3 người, 211 lượt đội-tháng.
- Tính từ 07/2025, vì bản chụp KPI thiếu 02–03/2025 và 05/2025 bị lặp dòng.

| Giảm ≥ | Bắn TB/tháng | Tháng sau < 80% | Nền | Khi tháng này đã < 80% (chính xác / nền) | Khi tháng này ≥ 80% (chính xác / nền) |
|---|---|---|---|---|---|
| 10% | 3,7 | 47,5% | 50,7% | 59,1% / 61,0% | 13,3% / 41,4% |
| 20% | 1,6 | 64,0% | 50,7% | 69,6% / 61,0% | 0% / 41,4% |

**Đọc số:**
- Trông có vẻ tốt ở ngưỡng 20% (64% so với 51%), nhưng gần như mọi lần bắn rơi vào đội **đã dưới 80%**.
- Tách riêng hai nhóm thì lợi thế gần như biến mất.
- Với đội đang tốt, quy tắc còn chính xác kém hơn nền.
- Cảnh báo 2 (đội có nguy cơ hụt chỉ tiêu) đã phủ việc này.

### F. Chỉ tiêu còn lại vượt năng lực bán lịch sử (loại)

**Quy tắc:**
- Tới ngày d: lũy kế + phần doanh thu còn lại ở mức cao (phân vị 90 của lịch sử cùng giai đoạn, tính theo TB 3
  tháng trước) vẫn < chỉ tiêu → bắn "không thể đạt".
- Chỉ tiêu lấy từ `DIM_TargetVungMien`. Doanh thu OTC hóa đơn.

**Đối chiếu nguồn:** doanh thu hóa đơn khớp tuyệt đối với thực hiện tầng QLV trên `FACT_TongHopKhachHang` từ
08/2025. Nguồn đúng.

**Doanh thu OTC toàn quốc so chỉ tiêu:**

| Tháng | 06/25 | 07/25 | 08/25 | 09/25 | 10/25 | 11/25 | 12/25 | 01/26 | 02/26 | 03/26 | 04/26 | 05/26 | 06/26 | 07/26 | 08/26 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| % đạt | 69 | 87 | 86 | 95 | 87 | 80 | 97 | 75 | 96 | 93 | 88 | 68 | 62 | 77 | 88 |

**Đọc số:**
- Kiểm thử 15 tháng: 15/15 tháng dưới 100%. Báo "sẽ không đạt 100%" đúng 100% nhưng không thêm thông tin gì.
- Mức "dưới 80%" mới có ý nghĩa:
  - ngày 10–20: bắt được 1/6 tháng xấu (toàn quốc);
  - ngày 25: bắt 6/6 nhưng còn 5–6 ngày, không kịp làm gì.
- Mục "Tiến độ tháng" hiện có trong báo cáo đã cho dự phóng cả tháng. Không cần cảnh báo riêng.

**Câu hỏi quản trị (không phải lỗi dữ liệu):** chỉ tiêu OTC có đang được đặt cao hơn năng lực có chủ đích không?
Chưa tháng nào đạt trong 20 tháng.

### G. Hàng trả OTC (loại)

- Đo 12 tháng ở bước khảo sát: dòng âm trên `vHoaDonTotal` rất nhỏ so với doanh thu.
- OTC không có nguồn trả hàng riêng như ETC. Không đủ tín hiệu để dựng cảnh báo theo khách.

### H. Dự phóng tiến độ đội: cộng TDV so với rollup QLV

**Mục đích:** kiểm tra có nên đổi `_team_pace_part` từ tổng các dòng TDV sang dòng rollup của QLV. Hai cách
được chấm trên cùng 262 lượt đội-tháng, cùng kết cục xấu là rollup QLV cuối tháng đạt dưới 80% chỉ tiêu.

**Kỳ đánh giá:** 07/2025–08/2026, đội có ít nhất 3 TDV. `FACT_TongHopKhachHang` không lưu bản chụp lịch sử
đúng ngày 15/20, nên doanh thu tại hai mốc được tái tạo bằng tập khách của snapshot cuối tháng nối với hóa đơn
OTC theo ngày. Tỷ lệ doanh thu kỳ vọng tới mốc lấy trung bình ba tháng trước, đúng cách `_team_pace_part` đang
dùng. Việc đối soát cuối tháng cho thấy hóa đơn khớp FACT trong 1% ở 247/262 lượt theo cách cộng TDV (94,3%)
và 262/262 lượt theo rollup (100%); sai lệch tuyệt đối trung vị đều là 0%.

| Mốc | Lượt đội-tháng | Kết cục <80% / tỷ lệ nền | Cách | Bắn | Đúng | Độ chính xác | TB bắn/tháng | Cao nhất/tháng |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Ngày 15 | 262 | 130 / 49,6% | Cộng TDV | 78 | 56 | **71,8%** | 5,6 | 14 |
| Ngày 15 | 262 | 130 / 49,6% | Rollup QLV | 83 | 59 | 71,1% | 5,9 | 14 |
| Ngày 20 | 262 | 130 / 49,6% | Cộng TDV | 52 | 45 | **86,5%** | 3,7 | 11 |
| Ngày 20 | 262 | 130 / 49,6% | Rollup QLV | 58 | 50 | 86,2% | 4,1 | 12 |

**Kết luận:** rollup bắn thêm 5 lượt ở ngày 15 và 6 lượt ở ngày 20 nhưng độ chính xác thấp hơn lần lượt 0,7
và 0,3 điểm phần trăm. Chênh lệch 66%/59% của MBKV1 tháng 9 không chuyển thành lợi thế rõ trên lịch sử.
Giữ cách cộng TDV hiện tại; không đổi code sản phẩm.

---

## 3. Việc cần DNH chốt

1. **A. SKU chủ lực ETC:** bật với ngưỡng TB 100tr/tháng (~3 dòng/tháng)? Gửi cho ai: TDV ETC phụ trách khách
   hay quản lý kênh ETC?
2. **B. Khách mới không mua lại:**
   - OTC: đơn đầu ≥20tr, chờ 45 ngày.
   - ETC: đơn đầu ≥20tr, chờ 60 ngày.
   - Có loại khách mở mã cho đơn thầu một lần không?
3. **C. Hợp đồng ETC:** giá trị hợp đồng thầu là mức trần hay cam kết? Có đưa bảng "sắp hết hạn, còn nhiều giá trị"
   vào báo cáo tháng ETC không?
4. **F. Chỉ tiêu OTC:** mức đạt 62–97% hằng tháng có phải chủ đích không? Nếu đúng, ngưỡng đỏ của cảnh báo 2 nên
   bám mức đạt thường lệ thay vì 100%.

## 4. Chưa làm, để lần sau

- **Báo cáo QLV:** đã thêm Việc cần xử lý và dự phóng đội (15/09), chỉ gồm khách gắn với đội theo phân công KPI.
  Khách ETC không gắn được đội nên không hiện trong báo cáo QLV (QLV hiện chỉ phụ trách OTC).

## 5. Tái lập

```
set PYTHONIOENCODING=utf-8
python scripts/nghien_cuu_insight.py keo-cong-no   # 53 lần gọi SP công nợ, ~12 phút
python scripts/nghien_cuu_insight.py keo-du-lieu   # hóa đơn, KPI, chỉ tiêu, hợp đồng ETC, ~vài phút
python scripts/nghien_cuu_insight.py phan-tich     # -> results/nghien_cuu_insight/ket_qua.json
```

Chạy trên máy vào được Bravo, `.env` ở gốc repo. Mọi truy vấn chỉ đọc, chạy tuần tự.
