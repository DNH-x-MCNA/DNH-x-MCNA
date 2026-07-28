# Các vấn đề nghiệp vụ cần Dược Nam Hà (DNH) xác nhận

*Chuẩn bị cho buổi họp báo cáo tiến độ ngày 16/07/2026. Gửi trước để buổi họp tập trung vào quyết định thay vì giải thích.*

Hệ thống báo cáo/cảnh báo/chatbot hiện đã chạy trên dữ liệu thật, cập nhật gần thời gian thực từ Bravo. Tuy nhiên các điểm dưới đây hiện đang dùng **giả định tạm thời** hoặc cần DNH xác nhận thêm vì chưa có xác nhận chính thức — số liệu vẫn đúng về mặt kỹ thuật (tính đúng theo công thức đang chọn) nhưng công thức đó có thể chưa khớp quy ước nội bộ của DNH. Càng chốt sớm, số liệu báo cáo/cảnh báo/chatbot càng đáng tin cậy.

**Phân nhóm nhanh** (theo mức độ ưu tiên):
- **Cách tính dữ liệu (ảnh hưởng độ chính xác số liệu)**: mục 1 (ngày quá hạn), 2 (mốc tuổi nợ), 4 (tồn kho).
- **Ngưỡng kích hoạt cảnh báo (giá trị số)**: mục 3b (sụt giảm doanh thu), 12 (các ngưỡng còn lại).
- **Chất lượng dữ liệu nguồn (Bravo/HR đánh dấu sai)**: mục 5 (khách hàng), 8 (nhân viên).
- **Nguồn/chu kỳ dữ liệu**: mục 6 (KPI quản lý), 7 (Excel công nợ/tồn kho).
- **Chính sách & chatbot**: mục 3 (QĐ 0429-2 — đang tắt), 9 (tài khoản chatbot), 10 (hạ tầng Supabase/on-prem), 11 (bảng vùng miền).

---

## 1. Cách tính "ngày quá hạn" của công nợ

**Đang dùng tạm**: Ngày đến hạn = Ngày hóa đơn (DocDate) + Số ngày công nợ (payment term, lấy TRÊN TỪNG HÓA ĐƠN). Quá hạn = ngày hiện tại vượt qua ngày đến hạn này.

**Cần DNH xác nhận**: Đây có đúng là cách tính chính thức DNH đang áp dụng không? (Có phương án khác thường gặp: tính từ ngày xuất hóa đơn điện tử, hoặc từ ngày ghi nhận công nợ trên hệ thống kế toán, có thể lệch vài ngày so với DocDate).

*Lý do hỏi kỹ: đã từng có bất đồng về cách tính này trong hợp đồng trước đây — cần chốt bằng văn bản để tránh lặp lại.*

*Cập nhật 16/07/2026: đã đối chiếu thêm — số ngày công nợ trên danh mục khách hàng (`BRV_KhachHang.DueDate`, hạn mặc định gán cho khách) so với số ngày công nợ ghi trên từng hóa đơn (`BRV_HTTDuDK.DueDate`) cho toàn bộ 18.741 hóa đơn OTC còn dư nợ: 82,7% khớp nhau; 15,2% khách hàng CHƯA được cấu hình hạn mặc định trong danh mục (DueDate=0) nhưng hóa đơn vẫn có hạn thật; 2,1% có cấu hình nhưng khác với hóa đơn thực tế (vd khách có hạn mặc định 3 ngày nhưng hóa đơn lại cho 12 ngày). Kết luận: dùng hạn trên TỪNG HÓA ĐƠN (như đang làm) đáng tin hơn hạn mặc định của danh mục khách hàng — không đổi cách tính, chỉ xác nhận thêm.*

## 1b. ĐÃ SỬA: dư nợ/tỷ lệ quá hạn trước đây bị thổi phồng 4-15 lần (nguyên nhân con số 92,9%/81,1%)

**Bối cảnh**: DNH phản hồi trong họp rằng tỷ lệ nợ quá hạn báo cáo (OTC 92,9% / ETC 81,1%) "quá cao, không thực tế". Đã truy nguyên (17/07/2026) và **xác nhận đây là bug thật, đã sửa dứt điểm**.

**Nguyên nhân**: công thức cũ đọc thẳng bảng `BRV_HTTDuDK`/`BRVSX_HTTDuDK` (Dư Đầu Kỳ) với cột `PaidAmount` **stale** (chỉ ghi khoản đã trả tại thời điểm tạo bản ghi, không cập nhật khoản trả sau này — khoản trả sau nằm ở sổ phát sinh `vHTTPhatSinh`, và ứng trước `vUTDuDauKy` cũng không được đối trừ). Hệ quả định lượng bằng dữ liệu thật, đối chiếu với SP gốc của DNH `NH_Report_TM.dbo.usp_DeptAccDueDate_GetData`:
- FPT Long Châu: repo báo nợ **9,17 tỷ**, thực tế chỉ **0,61 tỷ** (khách đã trả 34,5 tỷ nhưng cột `PaidAmount` chỉ ghi 261 triệu).
- Top 5 khách OTC lệch **4-15 lần**; có khách (Đa Phúc) đang **dư có** (trả thừa) vẫn bị báo nợ 2,45 tỷ.
- Tổng dư nợ OTC: repo 108,7 tỷ vs thực tế **11,77 tỷ**.

**Đã sửa**: `get_bravo_receivables_snapshot()` giờ gọi trực tiếp SP gốc DNH (read-only, chỉ tạo temp table). Đã kiểm chứng: viết replica trung thành logic SP thì **dư nợ khớp 100% từng khách đến từng đồng** (xác nhận SP là nguồn đúng); phần phân bổ waterfall của ứng trước vào các mốc quá hạn quá phức tạp để tái tạo bằng SQL thuần nên gọi thẳng SP cho chính xác tuyệt đối. Trigger A1 (nợ >45 ngày, theo hợp đồng) cũng đã chuyển sang dùng chung nguồn này.

**Số liệu ĐÚNG sau khi sửa (tức thời 17/07/2026)**:
| | Dư nợ | Nợ quá hạn | Tỷ lệ quá hạn (cũ → đúng) |
|---|---|---|---|
| OTC | 11,77 tỷ | 4,64 tỷ | 92,9% → **39,4%** |
| ETC | 192,3 tỷ | 100,6 tỷ | 81,1% → **52,3%** |

**Cần DNH xác nhận**: SP `usp_DeptAccDueDate_GetData` (với `@_Period2=15` cho mốc 1-15/16-30/31-45/>45 ngày) có đúng là báo cáo công nợ chuẩn DNH đang dùng nội bộ không? Nếu đúng thì số liệu công nợ của hệ thống giờ khớp 100% với báo cáo nội bộ DNH.

## 2. Mốc phân nhóm tuổi nợ (aging bucket) trong báo cáo "Công Nợ"

**Đang dùng tạm**: 1-15 / 15-30 / 30-45 / >45 ngày (mốc gốc từ đầu dự án — có thử đổi sang 1-30/31-60/61-90/>90 theo chuẩn kế toán phổ biến hôm 14/07, nhưng đã revert lại mốc gốc hôm 16/07 vì gây lệch giữa chatbot và card cảnh báo Teams — 2 nơi vô tình dùng 2 mốc khác nhau cho cùng 1 câu hỏi. Giờ toàn hệ thống — chatbot, alert, báo cáo — đã đồng nhất lại đúng 1 mốc 1-15/15-30/30-45/>45).

**Cần DNH xác nhận**: DNH có quy ước riêng về mốc phân nhóm tuổi nợ (vd theo chính sách tín dụng nội bộ, khác nhau giữa kênh OTC bán lẻ và ETC bệnh viện) không, hay dùng mốc 1-15/15-30/30-45/>45 hiện tại là được? (Nếu DNH muốn đổi sang mốc khác — kể cả mốc 1-30/31-60/61-90/>90 đã thử — xin nêu rõ để đổi ĐÚNG 1 LẦN ở tất cả các nơi cùng lúc, tránh lặp lại tình trạng lệch giữa các hệ thống.)

*Lưu ý: cảnh báo "khách hàng lần đầu chuyển nhóm nợ xấu" (mục A1 trong 4 trigger đã chốt) vẫn giữ nguyên mốc >45 ngày cố định, KHÔNG phụ thuộc vào mốc hiển thị này — 2 việc tách biệt, không đổi theo dù mục 2 này đổi thế nào.*

## 3. Chính sách thu nhập QĐ 0429-2 (khối OTC Miền Nam) — nhiều giả định

**Trạng thái**: Cảnh báo này (nguy cơ chấm dứt HĐLĐ / mất thưởng quý-năm theo QĐ 0429-2) hiện **đang TẠM TẮT** — lý do tắt cũ ("KPI hiện 100% Miền Bắc") đã lỗi thời (nhánh Bravo chính đã xác nhận có đủ dữ liệu Miền Nam/Trung), nhưng vẫn giữ tắt vì đây là cảnh báo nêu đích danh nhân sự có nguy cơ chấm dứt HĐLĐ — **cần DNH + người phụ trách xác nhận rõ ràng riêng trước khi bật**, không tự ý bật cùng lúc với sửa lỗi logic.

- **Điều kiện "2 tháng liên tiếp"** — ĐÃ GIẢI QUYẾT được phần kỹ thuật 16/07/2026: xác nhận Bravo (`FACT_TongHopKhachHang`) có lưu lịch sử KPI theo tháng từ 01/2025, đủ để kiểm tra thật điều kiện này (không còn chỉ dựa vào tháng hiện tại). Chạy thử: trong số nhân sự Miền Nam vi phạm ngưỡng, có nhóm đủ điều kiện CHÍNH THỨC 2 tháng liên tiếp (khác nhóm chỉ mới cảnh báo sớm 1 tháng). Vẫn cần DNH xác nhận cách tính này có đúng tinh thần chính sách không, trước khi dùng làm căn cứ chính thức cho quyết định nhân sự.
- **Định nghĩa "Quý"** — đang dùng quý dương lịch (Q1=T1-T3...). QĐ 0429-2 có dùng đúng quy ước này để tính "% đạt chỉ tiêu quý" không, hay theo mốc khác (quý tài chính lệch tháng)?
- **Ánh xạ vai trò** — quy ước CS = TDV chợ sỉ, TK = Trưởng kênh MT hiện là **tự suy luận** từ dữ liệu, chưa có bảng chú giải chính thức từ HR. Xin xác nhận.
- **Mốc ngày 10/20** trong cảnh báo nhịp KPI giữa tháng — có phải mốc chốt theo QĐ/quy định nội bộ không, hay chỉ là mốc tham chiếu?

## 3b. Ngưỡng "sụt giảm doanh thu" (revenue drop) và kỳ so sánh

**Đang dùng tạm**: Cảnh báo khi doanh thu tháng mới nhất giảm **> 20%** so với **tháng liền trước** (month-over-month).

**Cần DNH xác nhận** (2 việc):
1. **Ngưỡng %**: 20% là con số MCNA tạm đặt, chưa có căn cứ nghiệp vụ từ DNH — DNH muốn ngưỡng nào là "sụt giảm bất thường đáng cảnh báo"?
2. **Kỳ so sánh**: đang so tháng liền kề (MoM). DNH có muốn so **cùng kỳ năm trước** (year-over-year, tránh nhiễu mùa vụ — vd tháng Tết thấp là bình thường) không? *(Lưu ý: hiện dữ liệu chưa đủ dài để tính YoY, nhưng cần chốt hướng để chuẩn bị.)*

## 4. Công thức tính tồn kho hiện tại từ Bravo

**Hiện trạng CŨ**: Đã thử tính tồn kho hiện tại trực tiếp từ bảng thẻ kho thô (`BRV_TheKho`, quy ước kế toán kép `DebitAccount/CreditAccount`), đối chiếu với 1 mã hàng cụ thể thì lệch khoảng 19 lần so với số liệu đã biết là đúng — nên **chưa dùng** công thức này.

**Cập nhật 16/07/2026 — tìm hướng mới khả quan hơn**: Phát hiện 2 VIEW (không phải bảng thô) chưa từng thử: `vTheKhoLot` (có sẵn cột `ReceiptQuantity`/`IssueQuantity` rõ ràng theo từng lô/kho) và `vTonKhoDKLot` (tồn đầu kỳ theo lô/năm). Công thức thử nghiệm:
```
Tồn hiện tại = Tồn đầu kỳ (năm hiện tại, vTonKhoDKLot) + Σ Nhập − Σ Xuất trong năm (vTheKhoLot)
```
Test trên 3 mã hàng mẫu cho kết quả **dương, ổn định, hợp lý** — khác hẳn lần thử trước. Nhiều khả năng lỗi "lệch 19 lần" trước đây đến từ việc dùng bảng thô có quy ước kế toán kép dễ sai dấu, chứ không phải do thiếu dữ liệu.

**Cần DNH xác nhận**: Xin 1 (hoặc vài) mã hàng cụ thể kèm số tồn ĐÃ BIẾT LÀ ĐÚNG tại 1 thời điểm, để đối chiếu công thức trên — đây là bước còn thiếu duy nhất trước khi có thể tin dùng (khác doanh thu, đã có số DNH báo để so khớp ngay; tồn kho thì chưa có gì để đối chiếu). Nếu công thức khớp, có thể thay thế hẳn nguồn Excel tồn kho tĩnh hiện tại (xem thêm mục 7).

## 5. Cờ nhận diện "không phải khách hàng thật" trong `BRV_KhachHang`

**Đã tự đối chiếu, không còn cần DNH xác nhận phần chính**: Trước đó nghi ngờ `CustomerType = 2` (9.483 bản ghi) là cờ chung cho "không phải khách hàng thật" — kiểm tra lại bằng dữ liệu thật thì **KHÔNG đúng**: 97,9% nhóm này (`IsCustomer=1`) là khách "QUẦY THUỐC..." có thật, đối chiếu với `KenhBH` cũng cho thấy không liên quan gì đến phân kênh OTC/ETC. `CustomerType` nhiều khả năng chỉ là phân loại định dạng khách hàng (vd Nhà thuốc lớn vs Quầy thuốc nhỏ lẻ), không phải cờ thật/giả — **không loại nhóm này khỏi công nợ**, nếu loại sẽ mất oan 9.287 khách hàng thật.

Cờ đúng để loại khách "không phải khách hàng thật" là **`IsCustomer`** — code hiện tại (`src/alerts.py`) đã dùng đúng cờ này. Mã `NCC100122` (nhà cung cấp) phải loại riêng bằng tay vì bị Bravo đánh dấu NHẦM `IsCustomer=1`. Rà thêm phát hiện 2 mã lỗi tương tự: `TEST00`, `TESt001` (1 mã tên rác "uuuuuu") — cũng bị đánh dấu nhầm `IsCustomer=1`, may là chưa phát sinh hóa đơn nào nên chưa ảnh hưởng số liệu.

**Vẫn cần DNH hỗ trợ**: không có cách tự động 100% để bắt hết các bản ghi bị đánh dấu `IsCustomer` sai như trên (chỉ tìm được 3 mã trên nhờ dò theo tiền tố mã `NCC*`/`TEST*`, không đảm bảo hết) — DNH có quy trình/danh sách nào để rà soát định kỳ các bản ghi `BRV_KhachHang` bị gán sai `IsCustomer` không?

## 6. Nguồn dữ liệu KPI cho chức danh TP/PP/TBP

**Hiện trạng CŨ**: KPI của Trưởng phòng (TP), Phó phòng (PP), Trưởng bộ phận (TBP) hiện chỉ có trong 1 file Excel DNH gửi đầu dự án (import 1 lần, không tự cập nhật). Từng giả định các chức danh này "không tồn tại trên Bravo".

**Cập nhật 16/07/2026 — tìm được nguồn thật**: Giả định trên **SAI** — cả 7 người (4 TP, 2 PP, 1 TBP) đều có hồ sơ thật trên Bravo (`DIM_NhanVien`). Và tìm ra 1 bảng chưa từng dùng, `FACT_ThongKeTinhLuong` ("Thống kê tính lương"), có đủ chỉ tiêu/doanh số đạt/% hoàn thành theo tháng cho cả 7 người này (cùng cơ chế snapshot hàng tháng như bảng KPI TDV/QLV đang dùng).

**Đã xác nhận nội bộ (16/07/2026)**: chỉ 3/7 người có dữ liệu cập nhật đến hôm nay — đúng là do nhân sự đã nghỉ, không phải lỗi đồng bộ: **cả 2 Phó phòng (PP) đã nghỉ việc**, và thực tế hiện chỉ còn **3 Trưởng phòng (TP)** đang làm việc (khớp chính xác với 3 người có dữ liệu Bravo mới nhất — Nguyễn Thị Thanh Thủy/Miền Bắc, Trần Thanh Tùng/Miền Nam, Lê Văn Hưng/Miền Trung). Còn 1 Trưởng bộ phận (TBP — Hoàng Công Thưởng, dữ liệu dừng ở 30/09/2025) **chưa xác nhận** tình trạng.

**Vẫn cần DNH xác nhận**: (1) `FACT_ThongKeTinhLuong` có đúng là nguồn KPI chính thức cho cấp quản lý này không (để chuyển hẳn sang đọc tự động, bỏ file Excel tĩnh, và bỏ luôn 2 mã PP đã nghỉ + xác nhận 3 mã TP hiện tại)? (2) Trưởng bộ phận (TBP) Hoàng Công Thưởng còn đang làm việc không?

## 7. Chu kỳ cập nhật dữ liệu công nợ/tồn kho dạng tổng hợp sẵn

**Hiện trạng**: 2 bảng công nợ theo kỳ (`receivable_detail`) và tồn kho tổng hợp (`inventory`) hiện là dữ liệu Excel DNH gửi 1 lần đầu dự án — không tự làm mới. (Lưu ý: công nợ đã có nguồn thay thế cập nhật real-time từ Bravo — xem mục 1; tồn kho thì chưa, xem mục 4.)

**Cập nhật 16/07/2026 — định lượng được mức độ cũ**: Bảng `inventory` (Supabase) **không có bất kỳ cột ngày/timestamp nào** — bản thân hệ thống không tự biết được dữ liệu cũ bao nhiêu. Tra lại lịch sử: script import chỉ chạy **đúng 1 lần**, từ commit ĐẦU TIÊN của cả repo (02/07/2026), với dữ liệu được ghi rõ là **"aligned June 2026"** (phản ánh tình trạng tháng 6). Tính đến hôm nay: tối thiểu ~2 tuần không refresh kể từ lúc import, và bản thân số liệu gốc đã là của tháng trước — với ngành dược vòng quay nhanh, đây là độ trễ đáng kể cho các cảnh báo "sắp hết hàng"/"tồn kho chết" đang dùng đúng bảng này.

**Cần DNH xác nhận**: Nếu mục 4 (công thức tồn kho tự tính từ Bravo) chưa xác nhận được ngay, DNH có thể cung cấp file Excel tồn kho cập nhật theo chu kỳ nào (hàng tuần/hàng tháng) để thay thế bản dữ liệu tháng 6 hiện tại không?

## 8. Cờ `IsDuplicate` trên `DIM_NhanVien` (danh mục nhân sự bán hàng) — mới phát hiện 16/07/2026

**Hiện trạng**: Khi xây dựng thêm 1 lớp kiểm tra tự động đối chiếu doanh thu hóa đơn thực tế với bảng KPI (đã triển khai, chạy hàng ngày), phát hiện ít nhất 2 nhân viên bán hàng THẬT đang bị hệ thống gắn cờ "trùng lặp" (`IsDuplicate = 1`) trên `DIM_NhanVien`, khiến doanh số thật của họ (tổng ~1,55 tỷ đồng/tháng) bị loại khỏi mọi báo cáo/thống kê tính theo nhân viên hợp lệ, dù họ vẫn đang bán hàng bình thường:
- Nguyễn Thị Thanh Thủy (mã `MBKV12`, Miền Bắc, vào làm chính thức từ 11/04/2024) — ~1,25 tỷ đ/tháng.
- Lạc Ngọc Sâm (mã `TM25030101`, Miền Nam, vào làm chính thức từ 01/03/2025) — ~296 triệu đ/tháng.

Ngoài ra còn 2 mã khác cũng bị gắn `IsDuplicate=1` nhưng KHÔNG phải người thật — là mã kênh phân phối chung (`MN1` "Kênh MT", `MN4` "Chợ sỉ") — 2 mã này việc gắn cờ có vẻ hợp lý (không phải nhân viên cá nhân).

**Cập nhật 16/07/2026 — kiểm định lại bằng chính case đã biết (2 PP đã nghỉ, xem mục 6)**: Đối chiếu `EndDate`/hoạt động gần nhất giữa 2 PP ĐÃ XÁC NHẬN NGHỈ và 2 người nghi gắn nhầm cờ này:
- 2 PP đã nghỉ: có `EndDate=2026-04-30` (trùng khớp), dữ liệu doanh số **dừng đúng ngày đó, không có gì sau** — mẫu hình rõ ràng của người đã thôi việc.
- Nguyễn Thị Thanh Thủy & Lạc Ngọc Sâm: **`EndDate = None`** (không có), và **vẫn phát sinh doanh số thật đều đặn tới tận HÔM NAY (16/07/2026)** — Thủy: 1,26 tỷ đ/22 khách hôm nay, 17 tháng liên tục có dữ liệu; Sâm: 305,6 triệu đ/84 khách hôm nay, 15 tháng liên tục.

→ Mẫu hình hoàn toàn khác người đã nghỉ — đây gần như chắc chắn là lỗi gắn cờ, không phải trạng thái nghỉ việc/ngừng hoạt động. Cũng xác nhận thêm: `IsResigned` (bit) **không đáng tin** (cả người đã nghỉ thật cũng để `None`) — nên dùng `EndDate` làm tín hiệu chính khi rà soát tương tự.

**Cần DNH/phía nhân sự xác nhận**: 2 trường hợp Nguyễn Thị Thanh Thủy và Lạc Ngọc Sâm có đúng là bị gắn nhầm cờ không? DNH có quy trình rà soát định kỳ nào để phát hiện các trường hợp tương tự trong tương lai không (giống câu hỏi tương tự đã nêu ở mục 5 cho `BRV_KhachHang`)?

*Đã bổ sung sẵn: 1 alert tự động (chạy mỗi chu kỳ quét) đối chiếu tổng doanh thu OTC từ hóa đơn với tổng doanh số trong bảng KPI — báo ngay nếu lệch dù chỉ 1 đồng, giúp phát hiện sớm các trường hợp tương tự mà không cần chờ rà soát tay.*

## 9. Danh sách tài khoản đăng nhập Chatbot DNH

**Hiện trạng**: Chatbot web (nút "Hỏi Chatbot DNH" trên card Teams/báo cáo) đang xác thực qua danh sách tài khoản cấu hình sẵn (`CHATBOT_USERS_JSON`), mỗi tài khoản gắn cố định 1 phạm vi vùng/kênh được phép hỏi (RBAC — vd tài khoản Quản lý Miền Bắc chỉ hỏi được dữ liệu Miền Bắc). Danh sách này hiện vẫn là tài khoản do MCNA tự tạo để test, chưa xác nhận là danh sách thật của từng người dùng DNH.

**Cần DNH xác nhận**: Danh sách người dùng thật sẽ dùng Chatbot là ai (tên, vai trò, phạm vi vùng/kênh tương ứng)? Ai bên DNH sẽ là đầu mối cập nhật danh sách này khi có nhân sự mới/nghỉ việc/đổi vai trò? *(Câu hỏi cùng tính chất với danh sách nhận Teams DM cá nhân hoá — cả 2 đều đang chờ danh sách thật từ DNH.)*

## 10. Hạ tầng dữ liệu cho Chatbot: Supabase (cloud) hay SQL Server on-premises

**Hiện trạng**: Hợp đồng gốc quy định kiến trúc 3 tầng dữ liệu **on-premises trên SQL Server** (theo chính sách data residency của DNH, không dùng cloud). Theo chỉ đạo 03/07/2026, team đang build & test Chatbot trên **Supabase (Postgres, cloud)** để đẩy nhanh tiến độ — đây được xác định là bước TEST TRƯỚC, chưa phải quyết định thay thế vĩnh viễn kiến trúc on-prem đã ký.

**Cần DNH xác nhận**: Supabase có được chấp nhận làm hạ tầng CHÍNH THỨC lâu dài cho Chatbot (và dữ liệu trung gian nói chung) không, hay sau giai đoạn test phải chuyển về SQL Server on-prem như hợp đồng gốc? Nếu chấp nhận Supabase chính thức: cần xác nhận thêm region/project Supabase cụ thể, ai bên DNH quản lý quyền truy cập (service role key), chính sách backup/retention, và có cần ký phụ lục data residency mới không (vì khác với điều khoản gốc).

## 11. Bảng suy luận vùng miền theo tiền tố mã khách hàng (dùng cho khách hàng "mồ côi")

**Hiện trạng**: Với các khách hàng thiếu hồ sơ trong `DMS_KhachHang`/`DMSSX_KhachHang` (không join được sang bảng vùng miền chuẩn), cả Chatbot lẫn hệ thống cảnh báo đang dùng 1 bảng suy luận vùng miền TỰ XÂY DỰNG dựa theo 2-3 ký tự đầu của mã khách hàng (vd `HNO*` → Hà Nội, `HCM*` → TP.HCM...) — suy ra bằng thống kê từ ~47.500 khách hàng đã biết vùng, độ chính xác ước tính ≥95% nhưng KHÔNG phải dữ liệu chính thức từ DNH.

**Cần DNH xác nhận**: DNH có bảng ánh xạ chính thức (mã khách hàng/CityId → tỉnh thành/vùng miền) để thay thế bảng suy luận này không? Nếu có, xin cung cấp để tăng độ chính xác cho các báo cáo/cảnh báo phân theo vùng miền — đặc biệt với nhóm khách hàng mồ côi vẫn đang dùng suy luận tạm.

## 12. Các ngưỡng cảnh báo còn lại (giá trị số kích hoạt cảnh báo)

**Hiện trạng**: Ngoài các mục đã nêu riêng ở trên, các ngưỡng dưới đây hiện là **giá trị mặc định MCNA tự đặt** dựa trên thông lệ chung, CHƯA có căn cứ nghiệp vụ chính thức từ DNH. Hệ thống đã tách sẵn ra file cấu hình nên đổi rất nhanh, không cần sửa code:

| Cảnh báo | Ngưỡng đang dùng |
| --- | --- |
| Khách lớn sụt giảm/rời bỏ | Giảm > 50% so tháng trước, VÀ tháng trước mua > 50 triệu (mới coi là "khách lớn") |
| Rủi ro tập trung doanh thu | Top 3 khách chiếm > 50% doanh thu kỳ |
| Tỷ lệ hàng trả về cao (ETC) | > 5% doanh số ETC |
| Tồn kho chết / bán chậm | Đủ bán ≥ 12 tháng VÀ giá trị tồn > 50 triệu |
| Nhịp KPI ngày TDV (OTC) | < 3%/ngày = Đỏ, 3-4% = Vàng, ≥ 4% = Xanh; gửi báo cáo khi ≥ 5 TDV Đỏ |
| Sụt giảm mốc giữa tháng (ngày 10/20) | Giảm > 5% so trung bình 5 tháng trước |
| Tỷ lệ nợ quá hạn cao | OTC > 80%, ETC > 65% (tách riêng 16/07 dựa trên mức nền thực tế; vẫn tạm, phụ thuộc mục 1) |

**Cần DNH xác nhận**: DNH xem qua và điều chỉnh các ngưỡng trên cho phù hợp với thực tế kinh doanh / khẩu vị rủi ro của công ty (ngưỡng nào đang quá nhạy gây nhiễu, ngưỡng nào chưa đủ nhạy để bắt vấn đề thật)?

---

*Chuẩn bị bởi: MCNA — 13/07/2026, cập nhật 16/07/2026*
