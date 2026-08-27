# Các điểm nghiệp vụ cần Dược Nam Hà xác nhận

*Danh sách chạy — cập nhật trước mỗi buổi họp định kỳ với DNH, để buổi họp tập trung vào **quyết định** thay vì giải thích lại bối cảnh. Khởi tạo 13/07/2026, soạn lại toàn bộ 21/07/2026 (bỏ các mục đã tự giải quyết, gộp mục trùng bản chất, bổ sung phát hiện mới).*

Hệ thống báo cáo / cảnh báo / chatbot **đã chạy trên dữ liệu thật, cập nhật gần thời gian thực từ Bravo**. Các điểm dưới đây đang dùng **giả định tạm thời của MCNA** — số liệu vẫn đúng về mặt kỹ thuật (tính đúng theo công thức đang chọn), nhưng công thức đó có thể chưa khớp quy ước nội bộ DNH. **Càng chốt sớm, càng ít phải làm lại về sau.**

## Bảng ưu tiên

| Mức | Mục | Vì sao gấp |
|---|---|---|
| 🔴 **Chốt trước Demo #1 (09/08)** | A1, A2, A3, A4, A5, A6(b) | Ảnh hưởng trực tiếp con số hiển thị; sửa sau Demo sẽ phải làm lại số liệu đã trình bày |
| 🟠 **Nên chốt trong tháng 8** | B1, B2, B3, D1 | Quyết định ngưỡng cảnh báo — sai ngưỡng gây nhiễu hoặc bỏ sót, nhưng không sai số liệu gốc |
| 🟡 **Cần DNH sửa dữ liệu gốc** | C1, C2 | MCNA đã vá tạm ở tầng code; cần sửa gốc để không tái diễn |
| 🟢 **Phối hợp vận hành** | D2, D3, E1, E2, E3 | Không chặn kỹ thuật, nhưng cần để nghiệm thu & vận hành lâu dài |

---

# NHÓM A — Ảnh hưởng trực tiếp độ chính xác số liệu

## A1. Cách tính "ngày quá hạn" & xác nhận nguồn công nợ chuẩn

**Đang dùng**: Ngày đến hạn = Ngày hóa đơn (`DocDate`) + số ngày công nợ **ghi trên từng hóa đơn**. Quá hạn = hôm nay vượt qua ngày này.

**Bằng chứng đã tự kiểm** (18.741 hóa đơn OTC còn dư nợ): hạn ghi trên từng hóa đơn so với hạn mặc định trong danh mục khách hàng — **82,7% khớp**; **15,2%** khách chưa được cấu hình hạn mặc định nhưng hóa đơn vẫn có hạn thật; **2,1%** có cấu hình nhưng khác hóa đơn thực tế. → Dùng hạn trên **từng hóa đơn** đáng tin hơn.

**Đã sửa một lỗi lớn liên quan**: tỷ lệ nợ quá hạn từng báo **OTC 92,9% / ETC 81,1%** (anh Long phản ánh "quá cao, không thực tế" — **đúng, đó là bug**). Nguyên nhân: công thức cũ đọc cột "đã thanh toán" bị **đứng yên** (không ghi nhận khoản trả sau, không đối trừ ứng trước). Ví dụ FPT Long Châu bị báo nợ **9,17 tỷ** trong khi thực tế chỉ **0,61 tỷ**. Đã chuyển sang **gọi trực tiếp stored procedure gốc của DNH** (`usp_DeptAccDueDate_GetData`, chỉ đọc).

**Số liệu ĐÚNG sau khi sửa:**

| Kênh | Dư nợ | Nợ quá hạn | Tỷ lệ (cũ → đúng) |
|---|---|---|---|
| OTC | 11,77 tỷ | 4,64 tỷ | 92,9% → **39,4%** |
| ETC | 192,3 tỷ | 100,6 tỷ | 81,1% → **52,3%** |

**❓ Cần xác nhận**: (1) Cách tính ngày quá hạn trên có đúng quy ước DNH không? (2) `usp_DeptAccDueDate_GetData` có đúng là báo cáo công nợ chuẩn DNH dùng nội bộ không — nếu đúng thì số công nợ của hệ thống giờ **khớp 100%** với báo cáo nội bộ của DNH.

## A2. Mốc phân nhóm tuổi nợ

**Đang dùng**: **1-15 / 15-30 / 30-45 / >45 ngày**.

**Bối cảnh**: từng thử đổi sang chuẩn kế toán phổ biến (1-30/31-60/61-90/>90) nhưng đã quay lại mốc gốc, vì lúc đó chatbot và cảnh báo Teams vô tình dùng 2 mốc khác nhau cho cùng 1 câu hỏi. Hiện **toàn hệ thống đã đồng nhất đúng 1 mốc**.

**❓ Cần xác nhận**: DNH có quy ước riêng về mốc tuổi nợ không (có khác nhau giữa OTC bán lẻ và ETC bệnh viện không)? Nếu muốn đổi, xin nêu rõ để đổi **đúng một lần ở tất cả các nơi**, tránh lặp lại tình trạng lệch giữa các hệ thống.

## A3. Nguồn giá để tính **giá trị** tồn kho

**Đã giải quyết phần công thức**: DNH đã cung cấp SP gốc `usp_StockLotFinance_Report` (17/07) — đối chiếu đã phát hiện và sửa 2 lỗi thật (thiếu quy đổi đơn vị cho ~2,2% mặt hàng ETC; công thức vận tốc bán dùng nhầm mọi lượt xuất kho thay vì doanh số bán thật). **Số lượng tồn giờ đã đúng.**

**Còn thiếu**: chưa có nguồn giá để quy đổi *số lượng tồn → tiền*. Hệ quả cụ thể: mục **"Tồn kho chết"** trong mọi báo cáo/cảnh báo từng **luôn hiển thị 0** (vì lọc theo giá trị tồn > ngưỡng, mà giá trị đang = 0).
*(Cập nhật 07/08/2026: Đã tạm thời ẩn hoàn toàn mục/bảng "Mặt hàng tồn chết" khỏi các báo cáo Teams/Email và tắt trigger cảnh báo tương ứng qua cờ cấu hình `report_feature_flags.show_dead_stock: false` & `alert_feature_flags.dead_stock_check: false`, đồng thời bổ sung dòng ghi chú lý do ẩn rõ ràng trong template email).*

**❓ Cần xác nhận**: Nguồn giá đúng để tính giá trị tồn kho là gì — giá vốn bình quân, giá nhập gần nhất, hay một bảng giá riêng?

## A4. Chỉ tiêu cấp vùng vs chỉ tiêu cá nhân — trường hợp mã `MBKV12`

**Phát hiện 21/07/2026**: Bà **Nguyễn Thị Thanh Thủy** (mã `MBKV12`, DMSId `ASM11`) được gắn chức danh **QLV** trong danh mục nhân sự, nhưng:
- **Không có TDV nào báo cáo lên bà** (0 người);
- Chỉ tiêu tháng **5,28 tỷ** — gần **gấp đôi** QLV tổ thông thường (2,7–3 tỷ);
- Tự có doanh số **1,54 tỷ** từ **24 khách hàng phụ trách trực tiếp**.

Nhìn cấu trúc, bà giống **quản lý cấp vùng (ASM) tự ôm khách lớn**, không phải tổ trưởng QLV.

**Ảnh hưởng cụ thể**: chỉ tiêu 5,28 tỷ đang được cộng vào "Tổng chỉ tiêu" của báo cáo. **Nếu đây là chỉ tiêu cấp vùng bao trùm nhiều tổ** thì đang bị **cộng chồng** với chỉ tiêu các QLV tổ khác → "% hoàn thành toàn đội" bị kéo xuống thấp giả tạo. *(Doanh số thực tế 1,54 tỷ là khách riêng của bà, không cộng trùng — chỉ phần chỉ tiêu là nghi vấn.)*

**❓ Cần xác nhận**: (1) Bà Thủy là quản lý cấp vùng hay tổ trưởng QLV? (2) Chỉ tiêu 5,28 tỷ là của riêng bà hay là chỉ tiêu gộp cả vùng? (3) Còn bao nhiêu trường hợp tương tự (quản lý ôm khách trực tiếp, không có tổ)?

**Bổ sung 11/08/2026 — bằng chứng củng cố nghi vấn (1)/(2)**: kiểm tra trực tiếp `dim_nhanvien` phát
hiện bà Thủy có **2 bản ghi riêng biệt trong cùng dữ liệu Bravo**: một ở mã `MB` với `position_code='TP'`
(Trưởng phòng — đứng đầu cả vùng, quản lý toàn bộ 10 QLV miền Bắc), và một ở mã `MBKV12` với
`position_code='QLV'` (0 TDV, chỉ tiêu 5,28 tỷ như đã nêu). Tức bà vừa là **sếp vùng vừa là "cấp
dưới" của chính mình** trong cây tổ chức mà hệ thống dựng từ Bravo — càng củng cố giả thuyết bản ghi
`MBKV12` là **trùng lặp của chính vị trí TP**, không phải một QLV tổ riêng biệt. Đã thêm cảnh báo tự
động trong chatbot (khi hỏi về QLV này, hệ thống tự nói rõ nghi vấn trùng bản ghi thay vì trình bày
như QLV bình thường) — nhưng đây chỉ là xử lý tạm ở tầng hiển thị, không thay được việc DNH xác nhận
đúng bản chất của bản ghi.

## A5. Kênh ETC có chỉ tiêu theo từng nhân viên không?

**Phát hiện 21/07/2026**: Cấu trúc KPI của 2 kênh **khác hẳn nhau**:

| | Kênh OTC | Kênh ETC |
|---|---|---|
| Đội ngũ | ~150 TDV + ~20 QLV | **277 nhân sự đang hoạt động** (bảng riêng) |
| Chỉ tiêu | **Theo từng người, theo tháng** | Kế hoạch theo **nhóm sản phẩm**, không thấy chỉ tiêu cá nhân |
| Đo được "% hoàn thành"? | ✅ Có | ❌ Không (không có mốc để so) |

Doanh thu ETC tháng 7/2026 là **25,2 tỷ** — lớn hơn OTC (16,2 tỷ), nhưng hiện **không có báo cáo KPI cá nhân nào cho ETC** vì thiếu chỉ tiêu.

MCNA đã bổ sung tạm bảng **"Doanh số ETC theo nhân viên"** (chỉ có doanh số + số hóa đơn, **không có % hoàn thành**) — đã kiểm chứng tổng khớp tuyệt đối doanh thu ETC thật (lệch 0 đồng).

**❓ Cần xác nhận**: (1) ETC có giao chỉ tiêu doanh số cho từng nhân viên không? Nếu có thì lưu ở đâu (bảng nào / file nào)? (2) Nếu không có, DNH có muốn theo dõi ETC theo tiêu chí nào khác (theo nhóm hàng, theo bệnh viện/thầu, theo vùng)?

## A6. Thế nào là "đạt chỉ tiêu"? — ngưỡng % và cách tính giữa tháng

**Phát hiện 23/07/2026**, gồm **2 câu hỏi tách bạch** nhưng cùng ảnh hưởng đến một con số mà lãnh đạo hỏi nhiều nhất: *"có bao nhiêu nhân viên đạt chỉ tiêu?"*

### (a) Đã tách bạch hai khái niệm, ngưỡng theo vai trò đã chốt

**Phần đã tự giải quyết:** ban đầu báo cáo email và chatbot dùng **hai con số khác nhau** (≥100% và ≥80%) — cả hai đều do MCNA tự đặt, không có căn cứ. Sau khi đọc `DIM_BacThuong` (bảng cấu hình bậc thưởng mà thủ tục tính lương `usp_SaleSalary_Calculation_Ver2` đọc thật) và đối chiếu với các quyết định HĐQT có chữ ký, MCNA đã **tách rõ hai khái niệm bị gộp nhầm từ đầu** — cả email lẫn chatbot giờ hiển thị cả hai:

| Khái niệm | Mốc | Ý nghĩa |
|---|---|---|
| **Đạt chỉ tiêu** | ≥100% chỉ tiêu tháng | Hoàn thành kế hoạch doanh số |
| **Tới mức thưởng nhóm hàng** | TDV 65% · QLV và cấp quản lý 70% | Mốc *bắt đầu* được tính thưởng nhóm hàng (DM1/DM2/DM3) |

**Quan trọng — 65%/70% KHÔNG phải "ngưỡng được thưởng" nói chung:** đó chỉ là cổng của **thưởng nhóm hàng**. Chính sách DNH còn nhiều khoản thưởng khác với mốc riêng, tra theo chỉ số khác: thưởng tiến độ V15/V22/V25, thưởng khách hàng hoạt động ASO (tính theo **số lượng khách**, không phải %), thưởng quý, thưởng năm; chưa kể **lương cơ bản từ 60% trở lên vẫn hưởng 100%**. Vì vậy một người dưới 65% **vẫn có thể** được các khoản kia và vẫn đủ lương cơ bản — hệ thống đã được sửa để **không bao giờ** nói ai đó "không được thưởng" chỉ vì dưới mốc nhóm hàng.

**Cập nhật nghiệp vụ 27/08/2026:** cờ `IsAC`/Active Customer dành cho **CS (Chợ sỉ)** và **TK (kênh MT/Modern Trade)**. Dòng đã có `IsAC` thì **không có ASO**; báo cáo CS/TK phải dùng chỉ số Active Customer và không cộng ASO.

**Có hai thế hệ chính sách cùng tồn tại**, và ban đầu MCNA phát hiện chúng cho ra ngưỡng TDV khác nhau:

| Nguồn | Ngưỡng thưởng nhóm hàng cho TDV | Ghi chú |
|---|---|---|
| **QĐ 0429/QĐ-HĐQT.25** (ký 29/04/2025) | 70% | Thế hệ cũ, mốc chốt tiến độ ngày 25 (V25) |
| **QĐ 0107/2026** (ký 01/07/2026, hiệu lực 01/07/2026) | **65%** | Thế hệ mới, mốc chốt ngày 15+22 (V15/V22) |

**Quy tắc áp dụng đã chốt (23/07/2026)**: dùng văn bản **mới nhất theo từng loại vị trí**. TDV có văn bản mới hiệu lực từ 01/07/2026 (QĐ 0107) nên áp dụng luôn — **TDV = 65%**. Các vị trí khác (QLV, TP, PP, TBP, TDV chợ sĩ) chưa có văn bản nào mới hơn thay thế QĐ 0429/.25, nên vẫn giữ **70%** theo văn bản đó. Đây cũng là kết quả mà `DIM_BacThuong` (lọc theo ngày hiệu lực) đưa ra — cấu hình hệ thống và quy tắc áp dụng khớp nhau. Hệ thống đã dùng đúng theo bảng trên.

*(Có một ghi chú nội bộ khác trong mã nguồn chatbot nói bộ KPI kiểu mới "chưa áp dụng thực tế cho tháng 7" theo xác nhận với BA phía DNH — nhiều khả năng ghi chú đó nói về việc **các thành phần KPI chi tiết** (SKU, ASO, tái đơn theo công thức mới) chưa được theo dõi đủ trong kho dữ liệu, không phải về ngưỡng % dùng để tính thưởng. Nêu ở đây để DNH tiện đối chiếu nếu có sai khác.)*

**❓ Cần DNH xác nhận thêm**: Dùng "mốc bắt đầu được thưởng nhóm hàng" (theo quy tắc văn bản mới nhất/vị trí ở trên) làm chỉ số tóm tắt trong báo cáo quản trị có phù hợp không, hay DNH muốn mốc khác (vd vẫn lấy 100% là "hoàn thành kế hoạch")?

### (b) Đánh giá "đạt chỉ tiêu" **giữa tháng** thì so với cái gì?

Chỉ tiêu (`MonthSaleTarget`) là chỉ tiêu **cả tháng**, còn doanh số là **lũy kế tới thời điểm xem**. Vì vậy càng xem sớm trong tháng thì tỷ lệ "đạt" càng gần **0** — không phản ánh năng lực thật:

| Kỳ | Đạt ≥100% | Đạt ≥80% | TB toàn đội |
|---|---|---|---|
| Tháng 4/2026 *(trọn tháng)* | 64/150 | 109/150 | 88,1% |
| Tháng 5/2026 *(trọn tháng)* | 19/149 | 50/149 | 67,3% |
| Tháng 6/2026 *(trọn tháng)* | 25/150 | 52/150 | 65,5% |
| **Tháng 7/2026 *(mới 23/31 ngày)*** | **0/147** | **10/147** | **41,6%** |

*(Bảng trên lập khi hệ thống còn dùng ngưỡng 80% cũ. Sau khi tách 2 khái niệm ở mục (a): cột ≥100% là "đạt chỉ tiêu", còn "tới mức thưởng nhóm hàng" nay tính ở 65% cho TDV — tháng 7/2026 cho **27/147** thay vì 10/147 ở cột ≥80%.)*

Nghĩa là: nếu ai đó mở báo cáo vào ngày 5 hàng tháng, hệ thống sẽ báo *"0 nhân viên đạt chỉ tiêu"* — **đúng về mặt số học nhưng vô nghĩa về mặt quản trị.**

**❓ Cần xác nhận**: Khi xem **giữa tháng**, DNH muốn đánh giá theo cách nào?

1. **Theo nhịp độ** — so doanh số lũy kế với phần chỉ tiêu tương ứng số ngày đã trôi qua *(vd đến ngày 15/30 thì mốc là 50% chỉ tiêu)*. **MCNA khuyến nghị phương án này** — hiện đã có sẵn cơ chế tương tự trong cảnh báo nhịp KPI theo ngày (mục B2).
2. **Chỉ đánh giá tháng đã kết thúc**, trong tháng chỉ hiển thị doanh số lũy kế, không hiển thị "% đạt".
3. Giữ nguyên cách hiện tại *(so với chỉ tiêu cả tháng)* và chấp nhận con số thấp đầu tháng.

*Trong lúc chờ DNH chốt, MCNA sẽ ghi rõ ngưỡng và cách tính ngay trong mỗi báo cáo/câu trả lời — để hai con số khác nhau vẫn **giải thích được**, thay vì im lặng gây nghi ngờ số liệu.*

---

# NHÓM B — Ngưỡng kích hoạt cảnh báo

> Các ngưỡng dưới đây là **giá trị MCNA tạm đặt theo thông lệ chung**, chưa có căn cứ nghiệp vụ từ DNH. Hệ thống đã tách sẵn ra file cấu hình nên **đổi rất nhanh, không cần sửa code**.

## B1. Sụt giảm doanh thu — ngưỡng % và kỳ so sánh

**Đang dùng**: cảnh báo khi doanh thu tháng mới nhất giảm **> 20%** so với **tháng liền trước**.

**❓ Cần xác nhận**: (1) Mức giảm bao nhiêu thì DNH coi là "bất thường đáng cảnh báo"? (2) So với **tháng liền trước** hay **cùng kỳ năm trước**? *(So cùng kỳ năm trước tránh được nhiễu mùa vụ — vd tháng Tết thấp là bình thường. Hiện dữ liệu chưa đủ dài để tính, nhưng cần chốt hướng để chuẩn bị.)*

## B2. Các ngưỡng cảnh báo còn lại

| Cảnh báo | Ngưỡng đang dùng |
|---|---|
| Khách lớn sụt giảm / rời bỏ | Giảm > 50% so tháng trước, VÀ tháng trước mua > 50 triệu |
| Rủi ro tập trung doanh thu | Top 3 khách chiếm > 50% doanh thu kỳ |
| Tỷ lệ hàng trả về cao (ETC) | > 5% doanh số ETC |
| Tồn kho chết / bán chậm | Đủ bán ≥ 12 tháng VÀ giá trị tồn > 50 triệu *(phụ thuộc mục A3)* |
| Nhịp KPI ngày của TDV (OTC) | < 3%/ngày = Đỏ · 3–4% = Vàng · ≥ 4% = Xanh; gửi báo cáo khi ≥ 5 TDV Đỏ |
| Sụt giảm mốc giữa tháng (ngày 10/20) | Giảm > 5% so trung bình 5 tháng trước |
| Tỷ lệ nợ quá hạn cao | OTC > 80% · ETC > 65% *(đặt theo mức nền cũ — **cần đặt lại** vì mức thật giờ là 39,4% / 52,3%, xem A1)* |

**❓ Cần xác nhận**: DNH xem và điều chỉnh cho phù hợp khẩu vị rủi ro — ngưỡng nào **quá nhạy gây nhiễu**, ngưỡng nào **chưa đủ nhạy** để bắt vấn đề thật?

## B3. Ngưỡng "khách im lặng" / nguy cơ rời bỏ

**Đã thử tính**: tỷ lệ khách trong sổ mỗi TDV không mua hàng **> 60 ngày** → trung bình toàn công ty **47,9%**, cá biệt có TDV lên **90–100%**.

Con số này **rất nhạy với cách chọn mẫu số** (thử một cách khác ra tới 78,6%) → **chưa đủ tin cậy để dùng làm cảnh báo**, nên MCNA chưa bật.

**❓ Cần xác nhận**: (1) Chu kỳ mua hàng bình thường của khách dược là bao lâu — có khác nhau giữa OTC và ETC không? (2) Bao lâu không mua thì DNH coi là "có dấu hiệu rời bỏ" đáng cảnh báo?

---

# NHÓM C — Chất lượng dữ liệu gốc trên Bravo

> MCNA đã vá tạm ở tầng code để báo cáo chạy đúng, **nhưng dữ liệu gốc vẫn sai** — cần DNH sửa tận gốc, nếu không sẽ tái diễn với các bản ghi mới.

## C1. Nhân viên thật bị gắn nhầm cờ "trùng lặp" (`IsDuplicate`)

**Phát hiện**: 2 nhân viên bán hàng **thật, đang làm việc bình thường** bị gắn cờ trùng lặp, khiến **toàn bộ doanh số và cả đội dưới quyền họ biến mất khỏi mọi báo cáo KPI**:

| Nhân viên | Mã | Doanh số/tháng | Vào làm |
|---|---|---|---|
| Nguyễn Thị Thanh Thủy | `MBKV12` | ~1,545 tỷ đ | 11/04/2024 |
| Lạc Ngọc Sâm | `TM25030101` | ~388,6 triệu đ | 01/03/2025 |

**Đã kiểm chứng đây là lỗi gắn cờ, không phải nghỉ việc** — đối chiếu với 2 Phó phòng đã nghỉ thật: người nghỉ thật có ngày kết thúc rõ ràng và **doanh số dừng hẳn**; còn 2 người trên **không có ngày kết thúc** và **vẫn phát sinh doanh số đều đặn 15–17 tháng liên tục tới hôm nay**.

*(Lưu ý: 2 mã khác cũng bị gắn cờ này — `MN1` "Kênh MT", `MN4` "Chợ sỉ" — là mã kênh phân phối, **gắn cờ đúng**, MCNA không đụng tới.)*

**❓ Cần xác nhận**: (1) Xác nhận 2 người trên là nhân viên hợp lệ để **sửa thẳng dữ liệu gốc** (khi đó MCNA gỡ bản vá tạm trong code). (2) DNH có quy trình rà soát định kỳ để phát hiện trường hợp tương tự không?

### ⚠️ Nghi vấn nghiêm trọng hơn: đây có thể không chỉ là lỗi báo cáo — mà là lỗi TÍNH LƯƠNG THẬT

Cờ `IsDuplicate` không chỉ ảnh hưởng báo cáo KPI. Đọc trực tiếp thủ tục tính lương gốc `usp_SaleSalary_Calculation_Ver2` (DNH dùng để trả lương kinh doanh thật), cờ này tác động vào **chính quy trình tính thưởng**:

1. `IsDuplicate=1` khiến 2 điểm thành phần (`NCPoint` — khách mở mới, `TPRPoint` — sản phẩm trọng tâm) bị nhân với 0.
2. Cùng lúc, người bị gắn cờ **bị loại khỏi** danh sách xét bậc thưởng nhóm hàng (`DMBonus`).
3. Vì `DMBonus` được tính bằng cách **nhân** với tổng điểm KPI, mất điểm và mất bậc cộng dồn thành **mất toàn bộ khoản thưởng nhóm hàng của tháng đó** — bất kể doanh số thực đạt cao đến đâu.

**Đối chứng sơ bộ đã chạy** (dữ liệu 4 tháng gần nhất tính đến 20/07/2026, cần DNH/MCNA chạy lại để xác nhận số chính xác trước khi dùng chính thức):
- Cả 4/4 tháng có dữ liệu của 2 người bị gắn cờ sai đều cho `TotalPoint = 0,000` — trong khi 17/17 QLV không bị gắn cờ trong cùng kỳ đều có `TotalPoint > 0`.
- Ví dụ cụ thể: tháng 3/2026, bà Thủy (`MBKV12`) đạt **101,2%** chỉ tiêu với doanh số **7,28 tỷ** (gấp ~2,5 lần các QLV khác cùng kỳ) nhưng nhận **0đ** thưởng nhóm hàng; các QLV khác đạt 92–104% với doanh số 2,6–2,9 tỷ nhận **10–11 triệu đồng**.
- Ước tính sơ bộ theo mức thưởng trung bình của QLV tương đương (~9,3 triệu/tháng, tính trên 28 lượt quan sát): **thiệt hại có thể ≥37 triệu đồng qua 4 tháng** cho riêng 2 người này — **con số cần DNH đối chiếu lại với hệ thống lương/kế toán nội bộ, MCNA không có quyền và không tự xác nhận số tiền cuối cùng.**

*(Không phải mọi trường hợp gắn cờ đều sai — `MN1`/`MN4` là mã kênh phân phối, gắn cờ đúng; `TM24100101x` là vị trí đang khuyết người. Nghi vấn thiệt hại lương chỉ áp dụng cho 2 mã nêu trên.)*

**❓ Cần xác nhận thêm**: (3) DNH có thể đối chiếu 2 mã nhân viên trên với hệ thống chấm công/kế toán lương thực tế của các tháng gần đây không — để xác nhận có bị thiếu thưởng hay không, và nếu có thì xử lý truy trả theo đúng quy trình nội bộ DNH?

## C2. Bản ghi không phải khách hàng nhưng bị đánh dấu là khách hàng

**Đã tự xử lý phần lớn**: xác định đúng cờ cần dùng là `IsCustomer`. Nhưng phát hiện 3 bản ghi **bị đánh dấu sai**: `NCC100122` (là nhà cung cấp), `TEST00`, `TESt001` (bản ghi rác, tên "uuuuuu"). May là 2 mã test chưa phát sinh hóa đơn nên chưa ảnh hưởng số liệu.

**Hạn chế**: chỉ tìm được 3 mã này nhờ dò theo tiền tố `NCC*`/`TEST*` — **không có cách tự động bắt hết**.

**❓ Cần xác nhận**: DNH có quy trình/danh sách rà soát định kỳ các bản ghi bị gán sai cờ khách hàng không?

## C3. 6 mã nhân viên OTC không xác định được (~484 triệu đồng)

**Bối cảnh**: đa số mã "lạ" trên hóa đơn thực ra chỉ là bí danh, MCNA đã tự đối chiếu xong. Sau khi xử lý hết, còn đúng **6 mã không khớp bất kỳ nhân viên nào** trong cả 2 danh mục nhân sự:

| Mã nhân viên | Doanh thu tháng 7/2026 |
|---|---|
| `DNH01229` | 208.967.517 đ |
| `DNH01206` | 106.798.255 đ |
| `DNH01257` | 60.556.481 đ |
| `DNH01171` | 56.075.189 đ |
| `DNH01208` | 41.856.721 đ |
| `DNH00107` | 10.258.333 đ |

**❓ Cần xác nhận**: 6 mã này là nhân viên đã nghỉ (hóa đơn chưa cập nhật) hay lỗi nhập liệu? Có ảnh hưởng tới báo cáo KPI/lương của ai đang làm việc không?

---

# NHÓM D — Chính sách & định nghĩa nghiệp vụ

## D1. Chính sách thu nhập QĐ 0429-2 (khối OTC Miền Nam) — cảnh báo đang TẮT

**Trạng thái**: cảnh báo "nguy cơ chấm dứt HĐLĐ / mất thưởng theo QĐ 0429-2" **đang tạm tắt**. Lý do: đây là cảnh báo **nêu đích danh nhân sự có nguy cơ mất việc**, gửi lên Teams — MCNA **không tự ý bật** khi chưa có xác nhận rõ ràng từ DNH.

**Phần kỹ thuật đã sẵn sàng**: đã xác nhận Bravo lưu lịch sử KPI theo tháng từ 01/2025, đủ để kiểm tra thật điều kiện **"2 tháng liên tiếp"** (không còn chỉ dựa vào tháng hiện tại). Chạy thử cho thấy có nhóm đủ điều kiện chính thức 2 tháng liên tiếp, tách biệt với nhóm mới vi phạm 1 tháng (cảnh báo sớm).

**❓ Cần xác nhận trước khi bật**:
1. Cách kiểm tra "2 tháng liên tiếp" như trên có đúng tinh thần chính sách không?
2. **"Quý"** trong chính sách là quý dương lịch (Q1 = T1–T3) hay quý tài chính lệch tháng?
3. Quy ước vai trò **CS = TDV chợ sỉ**, **TK = Trưởng kênh MT** hiện là MCNA **tự suy luận** từ dữ liệu — xin xác nhận từ phòng nhân sự.
4. **Mốc ngày 10/20** trong cảnh báo nhịp KPI giữa tháng là mốc chốt theo quy định nội bộ, hay chỉ là mốc tham chiếu?
5. **Ai bên DNH chịu trách nhiệm phê duyệt bật cảnh báo này?**

## D2. Định nghĩa "khách hàng mở mới"

**Đã thử một định nghĩa** (chưa triển khai chính thức): khách mở mới = **hóa đơn đầu tiên trong toàn bộ lịch sử** của khách rơi vào tháng hiện tại. Kết quả hợp lý: **144 khách mới OTC / 79 TDV** trong tháng 7/2026.

**❓ Cần xác nhận**: Định nghĩa chính thức của DNH (dùng cho KPI/thưởng) có khớp không, hay có tiêu chí khác — vd phải có N hóa đơn liên tiếp mới tính, hoặc loại trừ khách quay lại sau thời gian dài ngừng mua?

## D3. Nguồn KPI chính thức cho cấp quản lý TP/PP/TBP

**Đã tìm được nguồn thật trên Bravo**: bảng `FACT_ThongKeTinhLuong` có đủ chỉ tiêu / doanh số đạt / % hoàn thành theo tháng cho cấp quản lý — thay thế được file Excel tĩnh DNH gửi đầu dự án (import 1 lần, không tự cập nhật).

**Đã đối chiếu nhân sự**: chỉ 3/7 người có dữ liệu cập nhật — và **đúng là do nhân sự đã nghỉ**, không phải lỗi đồng bộ. Cả 2 Phó phòng đã nghỉ; hiện còn 3 Trưởng phòng đang làm (Nguyễn Thị Thanh Thủy — Miền Bắc, Trần Thanh Tùng — Miền Nam, Lê Văn Hưng — Miền Trung), khớp chính xác với dữ liệu.

**❓ Cần xác nhận**: (1) `FACT_ThongKeTinhLuong` có đúng là nguồn KPI chính thức cho cấp quản lý không (để bỏ hẳn file Excel tĩnh)? (2) Trưởng bộ phận **Hoàng Công Thưởng** (dữ liệu dừng ở 30/09/2025) còn đang làm việc không?

---

# NHÓM E — Vận hành & nghiệm thu

## E1. Danh sách tài khoản Chatbot thật *(cần cho bước nghiệm thu)*

**Hiện trạng**: Chatbot đã có **phân quyền theo vùng hoạt động thật ở tầng code** — mỗi tài khoản chỉ truy vấn được đúng phạm vi vùng/kênh của mình (đúng yêu cầu anh Long nêu ở họp 16/07: *"mỗi QLV chỉ tự kiểm tra vùng mình"*). Nhưng danh sách tài khoản hiện vẫn là **tài khoản MCNA tự tạo để test**.

**Vì sao cần gấp**: đây là điều kiện để chạy **bước 4 của quy trình nghiệm thu** đã thống nhất — *quản lý vùng tự đăng nhập kiểm tra số liệu vùng mình*. Không có tài khoản thật thì không nghiệm thu được lớp 3–4.

**❓ Cần cung cấp**: (1) Danh sách người dùng thật (họ tên, vai trò, vùng/kênh được xem). (2) Ai bên DNH là đầu mối cập nhật danh sách khi có nhân sự mới/nghỉ/đổi vai trò?

## E2. Hạ tầng dữ liệu — xác nhận lại kiến trúc hiện tại

**Thay đổi lớn so với đầu dự án**: hợp đồng gốc quy định kiến trúc dữ liệu **on-premises trên SQL Server**; giai đoạn đầu team dùng tạm nền tảng cloud (Supabase) để đẩy nhanh tiến độ. **Hiện đã chuyển gần như hoàn toàn về on-premises**:

| Thành phần | Hiện tại chạy ở đâu |
|---|---|
| Báo cáo & cảnh báo | **Đọc trực tiếp Bravo (on-prem)** — đã bỏ hẳn cloud |
| Dữ liệu chatbot | **File dữ liệu cục bộ trên máy chủ DNH** (đồng bộ định kỳ từ Bravo) |
| Giao diện web chatbot | Nền tảng cloud (chỉ là lớp giao diện — **không chứa dữ liệu kinh doanh**) |

**❓ Cần xác nhận**: (1) Kiến trúc trên có được DNH chấp nhận chính thức không? (2) Riêng phần giao diện web đặt trên cloud — có cần chuyển về máy chủ nội bộ DNH luôn không, hay giữ như hiện tại là được? *(Về mặt kỹ thuật chuyển được, chỉ cần biết định hướng của DNH.)*

## E3. Bảng ánh xạ vùng miền chính thức

**Hiện trạng**: với khách hàng thiếu hồ sơ trong danh mục (không tra được vùng), hệ thống đang dùng **bảng suy luận tự xây** theo tiền tố mã khách hàng (`HNO*` → Hà Nội, `HCM*` → TP.HCM…), dựng từ thống kê ~47.500 khách đã biết vùng, độ chính xác ước tính **≥ 95%** — nhưng **không phải dữ liệu chính thức từ DNH**.

**❓ Cần cung cấp**: DNH có bảng ánh xạ chính thức (mã khách hàng hoặc mã tỉnh → vùng miền) không? Nếu có, xin gửi để thay thế bảng suy luận tạm này.

---

## Phụ lục — Các điểm MCNA đã tự giải quyết *(không cần DNH trả lời, nêu để DNH nắm)*

| Vấn đề | Kết quả |
|---|---|
| Dư nợ / tỷ lệ quá hạn bị thổi phồng 4–15 lần | ✅ Đã sửa — chuyển sang gọi SP gốc DNH (chi tiết ở A1) |
| Công thức tồn kho sai đơn vị & sai vận tốc bán | ✅ Đã sửa nhờ SP gốc DNH cung cấp 17/07 (còn giá trị tồn — xem A3) |
| Nghi ngờ cờ `CustomerType = 2` là "khách không thật" | ✅ Đã bác bỏ — nếu loại nhóm này sẽ mất oan 9.287 khách hàng thật |
| Đa số mã nhân viên "lạ" trên hóa đơn | ✅ Đã tự đối chiếu xong (chỉ còn 6 mã — xem C3) |
| Dữ liệu tồn kho/công nợ dạng Excel tĩnh (tháng 6) | ✅ Không còn dùng — cả 2 đã đọc trực tiếp Bravo theo thời gian thực |
| Chatbot chưa áp phân quyền theo vùng | ✅ Đã áp dụng thật ở tầng code (còn chờ danh sách tài khoản — xem E1) |

---

*Chuẩn bị bởi: MCNA — khởi tạo 13/07/2026, soạn lại toàn bộ 21/07/2026, bổ sung mục A6 ngày 23/07/2026*
