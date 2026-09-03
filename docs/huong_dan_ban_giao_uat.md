# Hướng dẫn bàn giao UAT Chatbot Dược Nam Hà

## 1. Bộ tài liệu bàn giao

Gửi tester các file sau qua kênh nội bộ được DNH phê duyệt:

1. `uat_tracking_chatbot_dnh.xlsx` — checklist 138 câu, dropdown chấm điểm và trang tổng hợp.
2. `dap_an_bo_cau_hoi_dieu_hanh.md` — kết quả đối chiếu theo từng câu hỏi.
3. `bao_cao_sql_doi_chung_138.md` — bằng chứng chạy toàn bộ checker.
4. `doi_chieu_snapshot_vs_hoadon.md` — kiểm tra độc lập snapshot KPI/lương với hóa đơn.
5. Tài khoản test theo cây phân quyền; mật khẩu phải gửi riêng, không ghi trong các file trên.

Không gửi `.env`, API key, chuỗi kết nối, database hoặc log có thông tin xác thực.

## 2. Baseline kiểm thử

- Ngày chốt dữ liệu: **31/08/2026**.
- Lớp bán hàng đối chiếu: **368.226 dòng**.
- 87 checker: **81 chạy được**, **1 chạy một phần**, **1 cần kho local**, **4 bị khóa đúng chủ đích**.
- Trong 138 câu: **58 câu đủ nguồn**, **2 câu chỉ có số hiện tại**, **68 câu cần chốt công thức
  hoặc thiếu một phần**, **10 câu thiếu nguồn/lịch sử**.

> S01 mở rộng đủ 24 tháng đã chạy thành công trên Bravo: 72 dòng theo tháng và 3 dòng tăng trưởng.
> C01/M01 đã chuyển sang “Đủ nguồn”; file đáp án tổng 138 câu đã được sinh lại ngày 03/09/2026.

> **C31 — LỖI SỐ LIỆU, chấm KHÔNG ĐẠT (mức High).** Chatbot báo tỷ lệ bù đắp 32–40% và kết luận
> "mất khách nhanh hơn bù". Checker tính ở ba ngưỡng khách ngừng mua khác nhau (im lặng 1/2/3 tháng)
> đều cho T6–T8/2026 nằm trong dải 69–137% — chatbot thấp hơn **toàn bộ** dải ở cả ba tháng, nên đây
> không phải bất đồng định nghĩa. Nguyên nhân: chatbot chỉ lấy "khách mới xuất hiện lần đầu", loại
> nhóm tái kích hoạt khỏi vế tăng thêm nhưng vẫn tính đủ vế mất — lệch bất đối xứng. C31 hỏi rõ
> "khách mới **/tái kích hoạt**". Một C-level đọc bảng này sẽ kết luận ngược hẳn tình hình thật.

> **Cảnh báo cho người chấm — C54, M28, V17 (chất lượng dữ liệu):** hai bẫy khi đối chiếu.
> (1) **"Thiếu quản lý" gần như toàn dương tính giả**: T8/2026 tầng nhân viên có **0/183** người
> thiếu quản lý, còn 26 ca "thiếu" đều là chính các quản lý (TP/QLV/PP) — không có cấp trên là đúng
> cấu trúc. (2) **Snapshot tháng đang chạy dở**: ngày 03/09 mới có 16 nhân viên so với 186 của tháng
> 8 trọn vẹn, nên chatbot báo "6 người thiếu quản lý" là 6/16 chứ không phải 6/200. Đọc cột tổng số
> người trước khi diễn giải bất kỳ cột lỗi nào. Ca đáng xử lý thật sự chỉ có vài trường hợp — nổi bật
> là `TM25031901` (Nguyễn Quốc Chiến) có doanh số 4.180.953 nhưng không có chỉ tiêu, và không bị đánh
> dấu trùng.

> 🔴 **Cảnh báo cho người chấm — C18, M35, V34, C53 (khuyến mãi):** đồng bộ CTKM đã **dừng từ
> 09/01/2026**, tức đứng yên 8 tháng tính tới 03/09/2026. Đơn gắn CTKM từ 12.400–13.500/tháng
> (09–12/2025) tụt còn 2.042 trong 01/2026 rồi **bằng 0** từ 02/2026. Vì vậy mọi câu hỏi hiệu quả
> khuyến mãi cho kỳ 2026 **không có dữ liệu** — chatbot trả lời cho kỳ 2025 là đúng, đừng chấm trượt
> vì "số cũ". Ở C53, chatbot báo không lấy được mốc khuyến mãi do timeout: kết luận đúng hướng nhưng
> sai nguyên nhân — checker lấy mốc bình thường, vấn đề nằm ở sync đã chết. **Cần khôi phục sync
> trước khi UAT nhóm khuyến mãi.**

> **Cảnh báo cho người chấm — C49, V16 (phủ tuyến/viếng thăm):** chatbot từ chối vì kho nó truy cập
> không có dữ liệu viếng thăm — **đúng với quyền truy cập của nó**, chấm ĐẠT. Nhưng lý do nó nêu là
> SAI: dữ liệu CÓ trên Bravo (`dbo.DMS_DiTuyen`, **1.785.213 dòng**, 451 nhân viên, từ 06/2022 đến
> nay), kèm cả `IsPlaned` (theo tuyến/ngoài tuyến) và `ArriveTime`/`LeaveTime` (check-in/check-out).
> Đây là **khoảng trống đồng bộ ETL**, không phải thiếu nguồn — đồng bộ bảng này là mở khoá cả nhóm
> câu hỏi phủ tuyến. Đã ghi vào backlog.

> **Cảnh báo cho người chấm — C48, M20, V18 (chi phí thưởng):** chatbot từ chối vì hai lý do, **cả
> hai đều chính đáng nhưng khác bản chất**. (1) Không có lợi nhuận — đúng, cùng gốc thiếu giá vốn với
> `S10`, chấm ĐẠT. (2) Không có công cụ tổng hợp thưởng toàn công ty, chỉ có tool xếp hạng TOP 100 nên
> sẽ bỏ sót ~106/209 người — chatbot thà từ chối còn hơn cộng TOP 100 rồi gọi là tổng, **quyết định
> đúng**, chấm ĐẠT; nhưng đây là **thiếu công cụ chứ không thiếu dữ liệu**, đã ghi vào backlog để bổ
> sung tool. Khi đối chiếu, nhớ tỷ lệ thưởng/doanh thu phải lấy mẫu số là doanh thu **tầng nhân viên**
> (T8/2026: 2,168%); lấy tổng mọi chức danh sẽ ra 0,680% vì doanh thu quản lý là rollup bị đếm trùng.

> **Cảnh báo cho người chấm — C45 (tỷ lệ nhân sự đạt KPI):** đừng chấm trượt vì lệch tỷ lệ. Tử số
> của chatbot khớp tuyệt đối với Bravo ở cả bốn mốc TDV (122 / 66 / 30 / 11) — chỉ **mẫu số** khác:
> chatbot đếm 171 người, checker đếm 192 (mọi bản ghi có target > 0), chênh 21 người, làm tỷ lệ TDV
> qua cổng thành 83,6% thay vì 77,2%. Cần biết chatbot lọc "nhân sự OTC" theo tiêu chí gì rồi mới
> kết luận. Lưu ý cổng 65/70% là **mốc thưởng nhóm hàng**, không phải "đạt chỉ tiêu" (≥100%).

> **Cảnh báo cho người chấm — C43, M41 (đấu thầu ETC):** chatbot TỪ CHỐI là **đúng**, chấm ĐẠT. Đã
> quét toàn bộ catalog Bravo ngày 03/09: chỉ có 4 đối tượng liên quan và tất cả đều là **hợp đồng đã
> ký** (`vHopDongETC`, `DMSSX_HopDongHdr/Ct`, `FACT_DuDKHopDongETC`); không có bảng nào ghi kế hoạch
> thầu, giá trị tham gia hay kết quả trúng/trượt. `StatusId` chỉ có 2 giá trị trên 8.607 hợp đồng nên
> không suy ra tỷ lệ trúng được. Muốn trả lời phải được DNH cấp nguồn dữ liệu đấu thầu.

> **Cảnh báo cho người chấm — C41, M40, V39 (tồn kho):** hai điều chatbot nói là **đúng**, chấm ĐẠT.
> (1) Không có lịch sử tồn kho theo tháng — `BRV_TonKhoDK` chỉ là snapshot hiện tại. (2) Miền Trung
> hiện 0 đồng giá trị tồn là **số thật**: 132 mặt hàng, 9.014.691 đơn vị, `Amount` = 0. Kiểm thêm cho
> thấy vấn đề rộng hơn chatbot nêu — B02 còn 614 dòng và B04 còn 585 dòng cũng có số lượng mà giá
> bằng 0, lại còn vài mã có **giá trị âm** dù số lượng dương. Tổng "~6,26 tỷ" vì thế là số thiếu, đừng
> dùng làm giá trị tồn kho. Đây là câu A3 chờ DNH chốt nguồn giá.

> **Cảnh báo cho người chấm — C30, M24 (cohort giữ chân):** checker dùng cohort = tháng có hóa đơn
> đầu tiên (proxy), còn chatbot dùng cờ `IsNC` của DNH. Quy mô cohort khác nhau rất xa — T10/2025
> kênh OTC ra 2.433 khách theo checker so với 341 chatbot báo — nên **tỷ lệ giữ chân hai bên không so
> trực tiếp được** cho tới khi DNH chốt câu A10 (định nghĩa "khách mở mới"). Không chấm trượt bên nào
> vì chênh lệch này.

> **Cảnh báo cho người chấm — C29, M08, V22 (vòng đời khách):** các dòng của truy vấn thứ nhất trong
> `S18` là `COUNT(DISTINCT)` theo (tháng × vùng × QLV) — **cộng lại là đếm trùng**, phải dùng truy vấn
> tổng thứ hai. Đo trên Bravo T8/2026: khách mới thật **627**, chatbot báo **612** (đúng bằng nhóm có
> QLV) — thiếu 15 khách chưa gắn QLV, khoảng 2,4%. Chênh nhỏ nhưng là chỉ số đếm nên phải ghi nhận.
> Riêng việc chatbot báo "T4, T5/2026 không có dữ liệu": **chưa kết luận được** — kho dev có đủ hai
> tháng này, nhưng bản dev đã cũ (snapshot cuối 06/08 so với Bravo 28/08), phải kiểm trên kho
> production của máy 24 mới kết luận.

> **Cảnh báo cho người chấm — C33, M31, V29 (nhóm sản phẩm):** cột `GroupCode` trên hóa đơn OTC là
> **bậc thưởng** (`DM1/DM2/DM3`), không phải nhóm sản phẩm; bên ETC lại là mã số khác hệ (`0..4`).
> Chatbot chỉ trả lời theo SKU, hoặc từ chối phần "nhóm sản phẩm", đều là **đúng** — chấm ĐẠT.
> `S21` đã hạ từ READY xuống PARTIAL ngày 03/09.

> **Cảnh báo cho người chấm — C25 và M29 (NPP/chi nhánh):** chatbot TỪ CHỐI hai câu này là **đúng**,
> phải chấm ĐẠT. Kiểm thật trên Bravo: `DistributorCode` chỉ có 3 giá trị (`OTC1`/`OTC`/`ETC` — nhãn
> kênh, không phải NPP) và `BranchCode` chỉ có 4 giá trị (chi nhánh kho nội bộ DNH). Không tồn tại
> chiều nhà phân phối. `S15` trước 03/09 gắn nhãn READY và sinh ra bảng trông như đáp án — ai đối
> chiếu máy móc sẽ chấm sai cho một câu trả lời đúng. Nay đã hạ xuống PARTIAL.

> UAT trực tiếp 03/09/2026 phát hiện `S10` từng khóa cả C13 dù chiết khấu có nguồn thật
> (`DiscountRate` trên `vHoaDonTotal`/`vHoaDonETCTotal`) — tách sang `S87` (PARTIAL), đối chiếu với
> câu trả lời thật của chatbot lệch dưới 1%. Cũng phát hiện `S11` (C16) chỉ trả bảng thô, chưa nêu
> thẳng SKU nào xói mòn giá — thêm truy vấn nhận diện streak giảm giá, khớp tuyệt đối 4/4 SKU chatbot
> đã nêu (cả trị số lẫn phân loại liên tục/không liên tục). `C14/C15/C19` (lợi nhuận) vẫn khóa đúng —
> giá vốn duy nhất tìm thấy là giá vốn tồn kho, không phải giá vốn tại thời điểm bán.

“SQL chạy được” chỉ là bằng chứng kỹ thuật, không thay cho kết luận UAT.

## 3. Cách tester thực hiện

1. Chọn đúng tài khoản/cấp phân quyền trong sheet `Checklist UAT`.
2. Nhập câu hỏi đúng nội dung cần kiểm tra; ghi ngày giờ và thời gian phản hồi.
3. Dán kết quả chatbot và đối chiếu file kết quả theo mã câu/checker.
4. Chấm riêng ba tiêu chí: đúng số liệu, đúng phân quyền và dễ hiểu.
5. Với lỗi, chọn mức độ, ghi nguyên nhân dự kiến, người xử lý và gắn ảnh/log.
6. MCNA sửa xong chuyển `Chờ retest`; tester DNH kiểm tra lại rồi mới chuyển `Đóng`.

## 4. Quy tắc đạt

Một test chỉ đạt khi đúng số liệu/kỳ dữ liệu, đúng phân quyền, trình bày dễ hiểu và không lộ dữ liệu nhạy cảm.

Câu thiếu nguồn/lịch sử được tính đạt khi chatbot nói rõ giới hạn và không suy đoán số liệu. Độ chính xác tính trên các test đã chấm xong:

`Độ chính xác = Số test Đạt / (Số test Đạt + Số test Không đạt)`

Điều kiện đề xuất trước UAT chính thức: không còn lỗi Critical/High chưa xử lý và độ chính xác trên bộ test hợp lệ lớn hơn 95%.

## 5. Phân công

- MCNA: tự test, cung cấp log, sửa lỗi kỹ thuật và phản hồi nguyên nhân.
- DNH: xác nhận công thức nghiệp vụ cho nhóm `DERIVED/PARTIAL`.
- Tester DNH: retest độc lập bằng tài khoản đúng phân quyền và ký xác nhận kết quả.
