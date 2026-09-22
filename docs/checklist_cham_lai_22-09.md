# Danh sách câu cần chấm lại — 22/09/2026

Nguồn: log chi phí/phản hồi của chatbot từ 11/09 đến 22/09 (các lượt 👎, các lượt `Lỗi`/`Đang chạy`),
đối chiếu với commit log cùng khoảng. Toàn bộ việc lập danh sách này chạy cục bộ trên code và kho
local, **không gọi một lượt model trả phí nào**.

Mỗi lượt chấm lại là một lượt gọi model có tính phí. Trung bình ngày 22/09 là **~4.000 đ/lượt**, nên
trọn danh sách này (24 lượt) tốn khoảng **100.000 đ**. Khi chạy phải truyền `username` riêng và
`session_id` có tiền tố nhận diện được, nếu không thì kết quả không lọc được theo vai/vùng và **không
dùng để chấm UAT** (xem `AGENTS.md`).

Thứ tự ưu tiên: nhóm 3 trước (còn nghi sai số thật), rồi nhóm 1 (nhiều khả năng đóng được), nhóm 2
xen kẽ, nhóm 4 đừng chấm cho tới khi sync xong.

---

## Nhóm 1 — Đã có bản sửa trỏ đúng lượt phản hồi đó, chấm lại để đóng

| # | Lượt phản hồi | Tài khoản | Câu hỏi | Phản hồi cũ | Bản sửa | Chấm lại cần thấy |
|---|---|---|---|---|---|---|
| 1 | 22/09 14:39 | Thanh Thủy | Khuyến mãi nhiều khách tham gia nhưng không tạo tăng trưởng | (điều tra 22/09) | `fix(m35)` ×2, 22/09 | Câu mở đầu nói rõ **chỉ Miền Bắc**; bảng có cột đơn **đã xuất hóa đơn** (SIRO_10 = 685/857); hai dòng `Q4.2025_NHOM_BOPHE_SIRO_` tách riêng kèm `program_id` |
| 2 | 22/09 13:52 | Thanh Thủy | Mở nhiều khách mới nhưng DT/khách và tỷ lệ mua lại thấp | (điều tra 22/09) | `feat(m24)`, 22/09 | 627 khách mới kỳ 8/2026 (MB 328 / MN 162 / MT 137); nói rõ khách mới lấy từ cờ `IsNC` của Bravo |
| 3 | 15/09 13:59 | Nguyễn Văn Danh | Danh sách khách hàng mới, ngày ghi nhận, doanh số tháng này | Thiếu khách mới; ngày ghi nhận sai | `fix(khach-kpi)` 15/09 (ghi rõ UAT 13:59–14:11), `fix(khach-hang)` 18/09 | Ngày ghi nhận = `NCSaveDate` (không phải ngày snapshot); không sót khách do QLV tự bán |
| 4 | 15/09 14:08 | Nguyễn Văn Danh | Khách phát sinh 3 tháng nhưng chưa đạt KPI tái đơn | Thiếu dữ liệu | `fix(khach-kpi)` 15/09 | Trả **danh sách khách** kèm lần mua gần nhất, không mô tả chung chung |
| 5 | 15/09 14:10 + 14:11 (Lỗi) | Nguyễn Văn Danh | Doanh số sản phẩm trọng tâm theo quản lý vùng | Thiếu KPI SP trọng tâm | `fix(khach-kpi)` 15/09 | Có %đạt target SKU trọng tâm theo từng QLV, không còn lỗi |
| 6 | 15/09 14:20 | OTC-Only C-Level | Bổ sung kế hoạch và % thực hiện | Thiếu target kênh MT | `fix(kenh-mt)` 15/09 (ghi rõ UAT 14:20) | Có kế hoạch và % thực hiện kênh MT theo từng tháng |
| 7 | 15/09 14:23 | OTC-Only C-Level | Top 10 khách hàng nợ quá hạn | Thiếu 2 nhà đầu, đang lấy tới nhà số 12 | `fix(otc)` 15/09 (UAT 14:23–14:40), `fix(receivables)` 16/09 | Đủ **10 dòng**, có `HCM04162` Dược Sài Gòn và `HCM04298` FPT Long Châu |
| 8 | 15/09 14:25 | OTC-Only C-Level | Bổ sung nhân viên, quản lý vùng tương ứng | Thiếu dữ liệu | `feat(dinh-dang)` 15/09, `fix(otc)` 15/09 | Mỗi khách kèm TDV/QLV phụ trách, mã luôn đi kèm tên |
| 9 | 15/09 14:40 | OTC-Only C-Level | Số lượng tồn kho bổ phế tính đến hôm nay | Thiếu dữ liệu | `fix(otc)` 15/09, `feat(tra-cuu)` 16/09 | Tra được theo **tên sản phẩm**, không bắt nhớ mã |
| 10 | 15/09 14:43 | dnh_etc | Doanh số tháng này theo các nhóm hàng | Thiếu nhóm đầu tư/khai thác/dược liệu/lao/khác | `fix(etc)` 15/09 (ghi rõ UAT dnh_etc 14:43) | Đủ nhóm hàng ETC theo `DIM_KeyClass` + `ItemTypeETC` |
| 11 | 15/09 15:16 (Lỗi 114 giây) | C-Level | Khách phát sinh 3 tháng chưa đạt KPI tái đơn, đội QLV TM23100148 | Lỗi timeout | `fix(loc-doi)` 16/09 (ghi rõ UAT 15/09 15:16) | Có `manager_code`, trả trong vài chục giây, không lọc tay trên danh sách toàn công ty |
| 12 | 16/09 09:48 và 09:52 | OTC-Only C-Level + dnh_etc | Top 10 khách hàng có công nợ quá hạn | Hỏi top 10 trả top 3 / top 5 | `fix(receivables): preserve requested top customer count` 16/09 | Hỏi 10 trả đủ 10 |
| 13 | 16/09 10:08 (Lỗi) | dnh_etc | Bệnh viện Bắc Ninh còn nợ bao nhiêu | Lỗi | `feat(tra-cuu)` 16/09 | Tìm được khách theo tên, không cần mã |
| 14 | 16/09 15:21 | C-Level | Khách hoạt động, mới, mua lại, tái kích hoạt, ngừng mua từng tháng | Lệch số khách tái kích hoạt | `fix(vong-doi)` 18/09, `fix(c31)` 21/09 | Số tái kích hoạt khớp cửa sổ quan sát đã chốt; khách tách theo vùng |
| 15 | 17/09 13:46 (Lỗi 112 giây) | C-Level | Tháng mùa vụ cao/thấp theo kênh và nhóm sản phẩm | Lỗi timeout | `fix(c08): avoid seasonality report timeout` 21/09 | Trả được, không timeout |
| 16 | 18/09 09:44 | C-Level | Giá trị tồn kho, số tháng tồn, chậm luân chuyển, stock-out, cận date | Số liệu không đúng — "hàng tồn chưa thể xác nhận" | `fix(ton-kho)` ×2 17/09, `fix(ton-kho, do-moi)` 18/09, `fix(m40)` ×2 21/09 | Số lượng tồn là **hiện tại** (đã cộng nhập–xuất). **Giá trị** tồn vẫn là giá đầu năm và câu trả lời phải nói rõ điều đó — đây là câu A3 chờ DNH chốt nguồn giá, **đừng chấm trượt vì điểm này** |
| 17 | 14/09 13:50 | chosi.mn | Doanh số sản phẩm DM1, DM2, DM3, trọng tâm | KPI doanh số sản phẩm thiếu | `fix(khach-kpi)` 15/09 | Có KPI sản phẩm trọng tâm kèm %đạt |
| 18 | 14/09 11:07 | chosi.mn | Tình hình thực hiện KPI của các trình dược viên | Thiếu thưởng SP danh mục, V15/V22/V25, ASO, tổng trọng số | `fix(kpi)` 22/09 — **`fix(c45)` 21/09 KHÔNG phủ câu này**, nó chỉ đóng gói bảng ngưỡng theo tháng | Ngoài doanh số/chỉ tiêu phải nêu các cấu phần còn lại hoặc nói rõ cấu phần nào chưa lấy được. **V25 đã dừng từ 01/07/2026** — `V25Bonus = 0` là đúng cơ chế, không được đòi bù |

## Nhóm 2 — Lượt chết kỹ thuật, chấm lại để biết còn không

| # | Lượt | Tài khoản | Câu hỏi | Dấu hiệu |
|---|---|---|---|---|
| 19 | 14/09 16:59 | Phạm Văn Thuần | Tình hình thực hiện KPI của các trình dược viên | `Lỗi` sau 907 ms, **0 token** — chết trước khi gọi model |
| 20 | 14/09 14:44 | Nguyễn Văn Danh | Thực hiện doanh số ngày của các trình dược viên | `Lỗi` sau 843 ms, **0 token** |
| 21 | 17/09 16:02 | Nguyễn Thị Hồng Thúy | Khách vừa nợ quá hạn vừa giảm mua | Kẹt trạng thái `Đang chạy`, không có latency (lượt 16:05 chạy lại thì xong) |

0 token nghĩa là hỏng ở tầng phiên/định tuyến chứ không phải model trả sai. Nếu chấm lại vẫn hỏng thì
lấy `backend/logs` quanh đúng mốc giờ đó chứ đừng tốn thêm lượt.

## Nhóm 3 — Chưa có bản sửa nào nhắm vào, phải điều tra trước khi chấm

| # | Lượt | Tài khoản | Câu hỏi | Phản hồi | Vì sao còn treo |
|---|---|---|---|---|---|
| 22 | 15/09 14:48 | dnh_etc | Doanh số ETC tháng này | "tháng này mới có gần 6,5 tỷ thôi" | **Ưu tiên cao nhất** — chính chủ kênh báo sai số tuyệt đối, không commit nào từ 15/09 đến nay nhắm vào con số doanh số ETC theo tháng |
| 23 | 15/09 14:53 | dnh_etc | Thực hiện, kế hoạch doanh số các tháng trong năm | "Kế hoạch đúng, thực hiện sai" | Cùng gốc với #22. Chấm chung một lượt điều tra |
| 24 | 14/09 13:45 | chosi.mn | Thực hiện và kế hoạch doanh số các quý | Thiếu kế hoạch quý | Kho có target theo tháng/vùng/QLV/SKU nhưng **không có bảng target quý**. Cần DNH chốt: cộng từ target tháng, hay có nguồn riêng |
| 25 | 16/09 15:00 | C-Level | Loại ảnh hưởng đổi địa bàn/chuyển NV/chuyển khách | "Số liệu không đúng", không ghi sai ở đâu | Hỏi lại người chấm sai chỗ nào trước, đừng đoán rồi tốn lượt |

## Nhóm 4 — Lỗ trống ETL, đừng chấm cho tới khi sync xong

| # | Lượt | Tài khoản | Câu hỏi | Thực trạng |
|---|---|---|---|---|
| 26 | 14/09 11:29 | chosi.mn | Số lượng đơn hàng đúng tuyến từng ngày | **Đã chấm lại 22/09: trả được**, nguồn ghi `SQL Server NH_Report_TM` — chatbot query thẳng Bravo chứ không qua kho. Kho local vẫn không có `DMS_DiTuyen` nên báo cáo cố định chưa dùng được, nhưng câu hỏi không bị chặn. Còn phải xác nhận với HR: ngày 01 và 03/09 trống trong khi là Thứ Ba và Thứ Năm (02/09 là Quốc khánh) |
| 27 | 14/09 11:06 | chosi.mn | Công làm việc, ăn ca, phụ cấp, chấm call | Chấm công chưa có nguồn nào trong kho lẫn trong tool. Đây mới thật sự là lỗ trống nguồn |

Với câu chấm công, ghi "chưa đủ nguồn" thay vì chấm trượt phần suy luận. Câu đi tuyến thì chấm bình
thường.

---

## Ghi chú về các lượt không tên

Log còn 8 lượt `unknown` tối 13/09 (≈ 81.900 đ trong 30 phút, latency 15–456 ms) và một cụm
`unknown` ngày 11/09 (≈ 51.400 đ). Không có `username` thì không lọc được theo vai/vùng, nên theo
`AGENTS.md` các lượt đó **không dùng để chấm UAT** — và cũng cần truy ra ai đã chạy. Các lượt
`unknown`/`alice` ngày 21/09 23:56 thì vô hại: 0 token, 0 đ, là smoke test.
