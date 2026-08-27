# Chính sách thu nhập TDV OTC (Miền Nam/Trung/Bắc) — tài liệu tham chiếu, CHƯA bật cho chatbot

Nguồn: 3 Quyết định chính thức của Chủ tịch HĐQT Công ty CP Thương mại Dược Nam Hà (số 0107-01,
0107-02, 0107-03/2026/QĐ-CTHĐQT.DNH, ký 01/07/2026, hiệu lực từ 01/07/2026), người dùng cung cấp
23/07/2026: "Chính sách thu nhập Trình dược viên OTC Miền Nam/Miền Trung/Miền Bắc".

**QUAN TRỌNG — TRẠNG THÁI ÁP DỤNG THỰC TẾ (xác nhận với DA bên DNH, 23/07/2026): dù văn bản ghi hiệu
lực từ 01/07/2026, chính sách này CHƯA được áp dụng thực tế để tính lương tháng 7/2026** — có độ trễ
giữa ngày ban hành và ngày vận hành thật (hệ thống Bravo/DMS chưa cập nhật kịp theo công thức mới).
Từ đầu năm 2026 đến hết tháng 6/2026, DNH vẫn dùng cách tính KPI CŨ (ngưỡng đạt 80%/50% trên
`fact_tonghopkhachhang`, đã có sẵn qua `get_employee_kpi`/`get_kpi_ranking`) — **2 hệ thống KPI hoàn
toàn tách biệt, KHÔNG được trộn lẫn**. Chưa rõ mốc chính sách này sẽ chính thức vận hành — hỏi lại
DNH khi cần.

**CHƯA có bảng dữ liệu tương ứng trong `warehouse.db`/Supabase** (không có SKU, khách tái đơn, khách
active/ASO, SP trọng tâm...). Tài liệu này **chỉ ghi lại công thức đã đọc từ văn bản gốc để dùng khi
triển khai sau** — KHÔNG được dùng để AI tự tính/bịa số lương thật cho tới khi (1) DNH xác nhận đang
áp dụng và (2) có ETL đưa nguồn dữ liệu vào hệ thống.

## A. Cơ cấu thu nhập chung (giống hệt cả 3 vùng)

```
TỔNG THU NHẬP = LƯƠNG CƠ BẢN + PHỤ CẤP + THƯỞNG
```

## B.1. Lương cơ bản (LCB) — theo Level doanh số

Level xác định theo **Target doanh số tháng** (doanh số trước VAT) đạt được. Bảng Level/LCB/Thưởng
Level Target **khác nhau theo vùng**:

| Vùng | Số Level | LCB (Level thấp nhất) | LCB (Level cao hơn) | Thưởng Level Target (thấp→cao) |
|---|---|---|---|---|
| Miền Nam | 8 (135tr → ≥450tr) | 6.000.000 | 6.000.000 (đồng nhất) | 0 → 500k → 1.5tr → 2tr → 2.5tr → 3tr → 3.5tr → 4tr |
| Miền Trung | 9 (135tr → ≥450tr) | 5.500.000 | 5.500.000 (đồng nhất) | 0 → 0 → 0 → 500k → 1tr → 1.5tr → 2tr → 2.5tr → 3tr |
| Miền Bắc | 8 (135tr → ≥500tr) | 5.500.000 (Level 1-2) | 6.000.000 (Level 3-8) | 0 → 0 → 500k → 1tr → 1.5tr → 2tr → 2.5tr → 3tr |

Chi tiết mốc doanh số từng Level **khác nhau theo vùng** — xem văn bản gốc PDF của từng vùng khi cần
số chính xác (không chép lại đầy đủ ở đây vì dễ sai sót, nhiều mốc gần giống nhau dễ nhầm vùng).

**Công thức % đạt LCB — GIỐNG HỆT cả 3 vùng:**
```
Đạt Level Target < 30%  → chỉ hưởng 3% × Doanh số thực đạt
Đạt Level Target 30-50% → hưởng 50% mức LCB (của Level đạt được)
Đạt Level Target ≥ 50%  → hưởng 100% mức LCB + Thưởng Level Target
```

**Công thức LCB+Thưởng thực nhận (làm việc không trọn tháng) — giống hệt cả 3 vùng:**
```
LCB thực nhận + Thưởng Level Target = (Mức LCB + Mức thưởng Level Target) × (Số ngày chấm calls hợp lệ / Số ngày công tiêu chuẩn)
```

Level 1 khi làm không trọn tháng (điều kiện Target DS tối thiểu: MN/MT =70 triệu, MB =100 triệu):
```
Mức LCB cơ sở = Mức LCB cơ sở Level 1 × (Mức target DS thực nhận / Mức target DS thấp nhất của Level 1)
```

## B.2. Phụ cấp

Điều kiện áp dụng — **GIỐNG cả 3 vùng, riêng Miền Bắc có thêm 1 điều kiện**:
- Chấm calls hàng ngày đúng quy định đi tuyến.
- Có phát sinh ≥1 đơn hàng đúng tuyến/ngày.
- Ngày hợp lệ = ngày đạt đủ 2 điều kiện trên.
- **CHỈ RIÊNG MIỀN BẮC**: thêm điều kiện trong tháng số ngày hợp lệ phải đạt ≥80% ngày công tiêu
  chuẩn tháng (làm tròn theo phần nguyên) — Miền Nam/Miền Trung KHÔNG có ngưỡng % này.

Mức phụ cấp — **giống hệt cả 3 vùng**:
- Ăn ca: 30.000đ/ngày, không tính thứ 7.
- Xăng xe: 800.000đ/tháng.
- Điện thoại: 200.000đ/tháng (không áp dụng nếu công ty đã cấp sim; phần cước vượt định mức bị trừ
  vào thu nhập).
```
Phụ cấp tháng = Mức phụ cấp tháng × (Số ngày hợp lệ / Số ngày công tiêu chuẩn tháng)
```

Quy định đi tuyến (số calls tối thiểu/ngày, khác nhau theo khu vực) — mỗi vùng có bảng khu vực riêng,
xem văn bản gốc; nguyên tắc chung: khu vực trung tâm (HCM/Hà Nội) đòi hỏi nhiều calls nhất (15/ngày
thường, 8/ngày thứ 7), TDV chợ sỉ chỉ cần 1 call/ngày. Điều kiện calls hợp lệ: đúng tuyến cài sẵn
trên DMS, thời gian tại điểm bán 3-60 phút.

## B.3. Thưởng tháng

### 3.1. Thưởng doanh số theo nhóm hàng (danh mục DM1/DM2/DM3)

```
Mức hưởng = Σ(n=1→3) (DMn × kt) × KPIs
```
- `DMn`: doanh số thực đạt từng danh mục (DM1/DM2/DM3 — nhóm mặt hàng theo tiêu chí công ty quy định,
  có thể thay đổi theo thời điểm/phê duyệt của Chủ tịch HĐQT).
- `kt`: hệ số thưởng danh mục theo % hoàn thành target doanh số tháng (Bảng 01) — **khác nhau theo
  vùng, đặc biệt Miền Bắc có hệ số DM1 thấp hơn hẳn Nam/Trung**:

| Vùng | DM1 (dưới65%→từ đủ105%) | DM2 | DM3 |
|---|---|---|---|
| Miền Nam | 0/1.3/1.5/1.65/1.85/2.0% | 0/1.8/2.0/2.2/2.5/3.0% | 0/5.5/5.5/6.0/6.5/7.5% |
| Miền Trung | 0/1.3/1.5/1.65/1.85/2.0% | 0/1.8/2.0/2.2/2.5/3.0% | 0/5.5/5.5/6.0/6.5/7.5% |
| Miền Bắc | 0/0.5/0.8/0.9/1.0/1.1% | 0/1.5/1.7/2.2/2.5/3.0% | 0/5.5/5.5/6.0/6.5/7.5% |

- `KPIs`: kết quả bộ chỉ tiêu KPI (Bảng 02) — **công thức và trọng số GIỐNG HỆT cả 3 vùng**, chỉ khác
  1 tham số (ngưỡng tối thiểu KH tái đơn):

| Chỉ tiêu | Trọng số | Kết quả tối đa | Cách tính điểm |
|---|---|---|---|
| Số lượng SKU bán được (kế hoạch giao tối thiểu 25 sản phẩm) | 20% | 20% | `= Thực đạt/Kế hoạch × Trọng số` |
| Tỷ trọng doanh số nhóm hàng trọng tâm (SPTT) | 30% | 35% | `= Thực đạt/Kế hoạch × Trọng số` |
| Khách hàng tái đơn (mua lại trong 3 tháng, doanh thu ≥500k/đơn) | 30% | 35% | `= Thực đạt/Kế hoạch × Trọng số` |
| Khách hàng mở mới (chưa từng/không phát sinh 6 tháng, đơn đầu ≥500k) | 20% | 20% | `= Thực đạt/Kế hoạch × Trọng số` |
| **Tổng** | **100%** | **110%** | |

  Ngưỡng tối thiểu "% KH tái đơn" để không bị tính KPI=0: **Miền Nam 25%, Miền Trung 30%, Miền Bắc
  50%** (Miền Bắc siết chặt nhất). SKU tính đảm bảo đạt 100.000đ/đơn; hết hàng được trừ mục tiêu SKU
  sau phê duyệt TGĐ; sản phẩm mới cộng thêm khi bán ra thị trường. Tỷ trọng SPTT = Doanh số thực đạt
  nhóm hàng trọng tâm tháng / Tổng doanh số thực đạt tháng — **đây chính là công thức đúng của "%
  Thực đạt" trong file CSV KPI thử nghiệm trước đó mà chưa xác định được** (không phải chia cho Target
  như đã thử sai trước đây).

### 3.2. Thưởng tiến độ (V15/V22) — GIỐNG HỆT cả 3 vùng

Chốt và ghi nhận doanh số trên Bravo tới hết ngày 15 và 22 hàng tháng (nếu rơi thứ 7/CN thì dời sang
ngày làm việc tiếp theo gần nhất):

| Mốc | Điều kiện | Thưởng |
|---|---|---|
| Ngày 15 | Đạt ≥25% DS tháng | 500.000đ |
| Ngày 22 | Đạt ≥55% DS tháng + tỷ lệ đạt Target DS tháng tối thiểu 75% | 1.000.000đ |
| Ngày 22 | Đạt ≥55% DS tháng + tỷ lệ đạt Target DS tháng tối thiểu 80% | 2.000.000đ |

Lưu ý: file CSV KPI thử nghiệm trước có nhắc "Ngày chốt V25" (25/tháng) — văn bản chính thức 3 vùng
này **chỉ có mốc V15/V22**, KHÔNG có mốc V25 riêng biệt trong công thức thưởng tiến độ (V25 trong CSV
có thể là ngày báo cáo/tổng hợp cuối cùng, không phải 1 mốc thưởng độc lập — chưa xác nhận, không suy
diễn thêm).

### 3.3. Thưởng khách hàng hoạt động (ASO) — công thức giống, NGƯỠNG SỐ khác hẳn theo vùng

**Cập nhật nghiệp vụ 27/08/2026:** ASO không áp dụng cho CS (Chợ sỉ) và TK (kênh MT/Modern
Trade). Hai vai trò này dùng cờ/chỉ số **IsAC — Active Customer**; bản ghi đã có IsAC thì không
được gán hoặc cộng thêm ASO.

Điều kiện chung: Doanh số thực đạt/Target ≥60%, và "khách hàng hoạt động" = khách có phát sinh doanh
số ≥500.000đ/đơn (Miền Bắc ghi "/tháng", Nam/Trung ghi "/đơn" — nguyên văn theo từng bản, có thể là
khác biệt soạn thảo, chưa xác nhận có chủ đích khác nhau hay không).

| Vùng | Ngưỡng thấp (0đ) | Ngưỡng giữa | Ngưỡng cao | Mức hưởng tối đa |
|---|---|---|---|---|
| Miền Nam | ASO < 25 | 25≤ASO<60: 1.5tr × ASO/50 | ASO≥60: 2tr × ASO/60 | 2.500.000đ |
| Miền Trung | ASO < 35 | 35≤ASO<70: 1tr × ASO/60 | ASO≥70: 1.5tr × ASO/70 | 1.800.000đ |
| Miền Bắc | ASO < 40 | 40≤ASO<100: 1.5tr × ASO/80 | ASO≥100: 2tr × ASO/100 | 2.500.000đ |

`ASO` = số lượng khách hàng hoạt động (KHÔNG phải "Active Sales Outlet" hay suy đoán khác — đây chính
là số đếm khách hàng thỏa điều kiện "khách hàng hoạt động" nêu trên, xác nhận qua công thức chia cho
ASO trong bảng). Đây là câu trả lời cho phần "ASO là gì" từng ghi CHƯA XÁC ĐỊNH trong tài liệu CSV.

## C. Thưởng Quý và Thưởng Năm — GIỐNG HỆT cả 3 vùng

**Điều kiện tháng làm việc làm căn cứ tính thưởng**: vào làm muộn nhất ngày 15 → tính tròn 1 tháng
làm căn cứ; vào làm từ ngày 16 trở đi → tháng đó KHÔNG tính vào căn cứ thưởng.

**Thưởng Quý:**
```
Mức hưởng = R × kq
```
- `R`: doanh số thực đạt của quý.
- `kq`: hệ số thưởng quý theo % Doanh số thực đạt Quý/Target Quý — điều kiện: không bị kỷ luật văn
  bản, làm đủ ≥2 tháng/quý, còn làm việc đến thời điểm chi trả:

| Doanh số thực đạt Quý/Target Quý | Hệ số kq |
|---|---|
| Dưới 70% | 0% |
| 70% - dưới 80% | 0.5% |
| 80% - dưới 90% | 0.65% |
| 90% - dưới 100% | 0.7% |
| 100% - dưới 110% | 0.8% |
| Từ đủ 110% | 0.9% |

Thưởng Quý trả cùng kỳ lương tháng đầu tiên của quý tiếp theo.

**Thưởng Năm — 2 phần:**

```
Lương tháng 13 = [Tổng(LCB + Thưởng Level Target) cả năm / 12] × kn
Thưởng kinh doanh = [Tổng thưởng hàng tháng cả năm / 12] × kn
```
- "Tổng thưởng hàng tháng cả năm" (cho phần Thưởng kinh doanh) = tổng cộng dồn: Thưởng danh mục +
  Thưởng tiến độ V15/V22 + Thưởng khách hàng hoạt động (ASO) — **Miền Nam văn bản gốc ghi thiếu "+
  Thưởng ASO" trong định nghĩa nhưng có khả năng là lỗi đánh máy** (Miền Trung/Bắc đều liệt kê đủ 3
  khoản) — nên hiểu là đủ cả 3 khoản cho cả 3 vùng, cần xác nhận lại với DNH nếu quan trọng.
- `kn`: hệ số thưởng năm theo % Doanh số thực đạt năm/Target năm — **GIỐNG HỆT cả 3 vùng**:

| Doanh số thực đạt năm/Target năm | Hệ số kn |
|---|---|
| Dưới 70% | 0% |
| 70% - dưới 75% | 60% |
| 75% - dưới 80% | 100% |
| 80% - dưới 85% | 120% |
| 85% - dưới 90% | 140% |
| 90% - dưới 100% | 160% |
| 100% - dưới 105% | 180% |
| 105% - dưới 110% | 190% |
| Từ đủ 110% | 200% |

Thưởng Năm trả chậm nhất vào cùng kỳ lương tháng thứ 2 của quý tiếp theo (sau năm tính thưởng).

## D. Quy định chung khác (giống cả 3 vùng, trừ khi ghi chú)

- TDV thử việc áp dụng chính sách này như TDV đã ký HĐLĐ chính thức.
- Thưởng tháng có thể bị dừng/giảm nếu TDV bị kỷ luật văn bản hoặc có hành vi gây thiệt hại tài chính
  đã xác định được cho công ty (dù chưa kết luận hình thức kỷ luật).
- **Cảnh báo hiệu suất kém** — TDV có 2 tháng liên tiếp (hoặc 2/3 tháng liên tiếp gần nhất) doanh số
  thực đạt/Target ở mức thấp bị coi là "liên tiếp không hoàn thành công việc", công ty có quyền chấm
  dứt HĐLĐ và chuyển sang hình thức cộng tác viên:
  - **Miền Nam**: ngưỡng ≤50% áp dụng 01/07/2026-30/09/2026, sau đó ngưỡng ≤60% áp dụng từ 01/10/2026
    (chính sách siết dần theo thời gian).
  - **Miền Trung, Miền Bắc**: ngưỡng cố định ≤60%, không có giai đoạn chuyển tiếp như Miền Nam.
- Quy định giao Target do Tổng Giám đốc ban hành/phê duyệt theo từng giai đoạn (không cố định trong
  văn bản chính sách này).

## Đối chiếu với file CSV "Báo cáo KPI lương kinh doanh_MN" (thử nghiệm, xem file cũ đã lưu)

Văn bản chính thức này **xác nhận đúng** hầu hết các mục từng đánh dấu "CHƯA XÁC ĐỊNH" trong tài liệu
CSV trước — công thức Bảng 02 (SKU/SPTT/KH tái đơn/KH mới đều `=Thực đạt/Kế hoạch×Trọng số`), ASO là
số khách hàng hoạt động, "% Thực đạt" SPTT = tỷ trọng doanh số nhóm trọng tâm/tổng doanh số. Vẫn còn
1 điểm **chưa khớp hoàn toàn**: hệ số trọng số SKU trong CSV mẫu (TDV ra ~0.2, QLV/TP ra ~0.5, không
nhất quán) — có thể do QLV/TP không áp dụng công thức TDV cá nhân mà cộng dồn/tính khác theo cấp bậc
(văn bản này chỉ nói rõ cho TDV, không đề cập QLV/TP) — cần hỏi lại DNH nếu cần áp dụng cho cấp QLV.

## Việc cần làm trước khi bật rule cho chatbot

1. Xác nhận lại với DNH mốc thời gian chính sách này bắt đầu áp dụng thực tế (khác ngày hiệu lực văn
   bản 01/07/2026).
2. Thiết kế nguồn dữ liệu (Bravo hay Excel nội bộ?) cho SKU/khách tái đơn/ASO/SP trọng tâm/Call, và
   ETL tương ứng đưa vào `warehouse.db`.
3. Xác nhận công thức áp dụng cho cấp QLV/TP (văn bản chỉ viết rõ cho TDV).
4. Chỉ sau đó mới viết tool chuẩn/cập nhật `schema_context.py` để AI trả lời câu hỏi lương/KPI theo
   chính sách mới — KHÔNG bật trước khi có nguồn dữ liệu thật và xác nhận đang áp dụng, tránh AI tính
   sai ảnh hưởng lương thật của nhân viên.
