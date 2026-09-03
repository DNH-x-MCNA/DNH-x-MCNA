# Tracking hoàn thiện dự án DNH — cập nhật 03/09/2026

## Kết quả đã hoàn tất trong đợt làm sạch miễn phí

| Việc | Trạng thái | Bằng chứng / ghi chú |
|---|---|---|
| Trang quyết định Nhóm A | Xong | `Nhom_A_can_DNH_chot_truoc_UAT_10-09-2026.md`, gồm A1–A9 và số câu bị ảnh hưởng trực tiếp. |
| Top sản phẩm tách OTC/ETC | Đã có trong code | Mô tả tool và system prompt đều buộc gọi hai lần khi so sánh hai kênh; không sửa lặp lại. |
| Bộ kiểm bất biến 40 công cụ | Xong phần code | Catalog phủ đúng 40/40 tool. Kho dev chạy được 35 phép đạt, 0 lệch; 25 mục bị bỏ vì kho dev thiếu bảng/cột hoặc không có dữ liệu. Phải chạy lại trên máy 24 trước UAT. |
| Panel vai trò Trưởng phòng | Đã có trong code | `regional_director` hiển thị “Giám đốc Miền / Kênh (Trưởng phòng)” ở danh sách, form tạo và form sửa. |
| S27/S30 mồ côi | Xong | C41 chuyển sang S27 (`READY_CURRENT`); C45 chuyển sang S30 (`READY`). Không còn checker mồ côi. |
| C01/M01 đủ 24 tháng | Xong và đã chạy thật | S01 đọc thẳng 24 tháng hóa đơn và tính MoM/YoY/tăng trưởng. Lần chạy cuối ra 72 dòng theo tháng và 3 dòng tăng trưởng; C01/M01 chuyển sang `READY`. |
| Quy tắc Active Customer | Xong | Thêm TK vào tầng nhân viên cùng TDV/CTV/CS; CS và TK dùng `is_ac`, không cộng/hiển thị ASO. Test hiện kiểm riêng cả CS lẫn TK. |
| Cây `frontend/` trùng | Đã cảnh báo rõ hơn | File `_KHONG_DUNG_LAM_ROOT_DIRECTORY.md` ghi rõ chênh lệch và cách xóa phần git-tracked sau khi được duyệt. Chưa xóa vì máy 24 còn dùng `.vercel/project.json`. |
| Đáp án 138 câu | Xong | Đã sinh lại lúc 09:28 ngày 03/09 trên 368.226 dòng bán hàng: 80 checker chạy đủ, 1 chạy một phần, 1 dùng kho local, 4 khóa đúng chủ đích, không có checker lỗi. Baseline: 63 `READY`, 2 `READY_CURRENT`, 62 `PARTIAL/DERIVED`, 11 `BLOCKED`. |
| Snapshot KPI/lương vs hóa đơn | Đã chạy lại | Khớp 1.960/1.973 dòng chung; khi loại `IsDuplicate=1` khớp 1.875/1.876 dòng chung trong ngưỡng 1%. |
| File Excel giao tester | Đã cập nhật | Ngày chốt 31/08/2026; C01/M01→`READY`, C41→S27, C45→S30; tổng hợp tự tính 62 câu cần chốt/thiếu một phần. |
| Kiểm thử tự động | Đạt | 435 test đạt, 1 test chủ động bỏ qua. Đã sửa ca test dùng cứng ngày 28 khiến sai khi tháng có 31 ngày. |
| Build và lint giao diện production | Đạt | Next.js build thành công, TypeScript và 16 trang tĩnh hoàn tất. ESLint đạt sạch sau khi loại đúng các cây lưu trữ, bản sao và đầu ra sinh tự động khỏi phạm vi kiểm tra. |
| Kiểm tra phân quyền ETC | Đạt | 3/3 phép kiểm giữ đúng kênh ETC. Script mặc định đã đổi từ JSON sang báo cáo tiếng Việt; vẫn có `--json` cho hệ thống tự động. |
| Lệnh kiểm tra một lần trước UAT | Xong | `scripts/kiem_truoc_uat.ps1` chạy tuần tự kiểm tài khoản, phân quyền ETC và bất biến 40 công cụ; cuối cùng kết luận rõ Đạt/Chưa đạt. |
| Gói UAT chiều 03/09 | Đã chuẩn bị | `handoff_private/UAT_Chatbot_DNH_2026-09-03_v2.zip`, gồm trang đọc trước và 8 tài liệu/file kiểm thử; không chứa mật khẩu, API key hay chuỗi kết nối. Chỉ phát hành sau khi tài khoản máy 24 qua kiểm tra scope. |

## Việc còn lại trước khi giao tester

| Ưu tiên | Việc | Người cần xử lý | Hạn / điều kiện |
|---:|---|---|---|
| 1 | Chọn ngân sách A (nạp thêm khoảng 60–80 USD) hoặc B (giảm hạn mức UAT) | MCNA + DNH | Trong tuần 1; chưa chốt thì không nên mở UAT rộng. |
| 2 | Chạy `scripts/kiem_tai_khoan_thieu_pham_vi.py` trên `auth.db` của máy 24 và sửa mọi tài khoản đã duyệt còn thiếu scope | Người vận hành máy 24 | Trước khi gửi tài khoản. Kho local hiện có 12 tài khoản QLV cũ không hợp lệ; đây chưa phải kết luận về production. |
| 3 | Gửi trang Nhóm A và lấy xác nhận bằng văn bản | DNH | Trước 10/09/2026. Riêng “tuần trong tháng” chưa sửa code cho tới khi có phản hồi hoặc tới hạn áp dụng giả định. |

## Đợt sửa prompt gộp cuối tuần 1 — CHƯA deploy

Gom vào MỘT lần duy nhất vì mỗi lần sửa mô tả tool/system prompt là một lần trả tiền ghi lại cache
cho mọi vai (cache chiếm 71% chi phí). Không vá lẻ từng cái.

| # | Việc | File | Gốc |
|---:|---|---|---|
| 1 | Mô tả `get_top_products`: câu hỏi so sánh hai kênh phải gọi tool hai lần, mỗi lần một `channel` | `backend/report_templates.py` | Ca `dnh` 14/08 |
| 2 | Định nghĩa "tuần trong tháng" — chốt tạm tuần lịch thứ Hai nếu 10/09 chưa có phản hồi DNH | `backend/schema_context.py` | Câu A9 nhóm A |
| 3 | Free-SQL bỏ qua join `city_id → area_code`, viết thẳng `c.area_code` lên `dms_khachhang`/`dmssx_khachhang` (cột không tồn tại); retry lặp lại đúng lỗi 8 lần không tự sửa | `backend/schema_context.py` + vòng retry free-SQL | UAT trực tiếp 03/09 — câu C02 hỏng hoàn toàn, ghi nhận không hài lòng |
| 4 | CTKM: phải dùng NGUYÊN `invoiced_orders` và `average_revenue_per_invoiced_order` do tool trả, không tự tính lại. Tool trả đúng 313 đơn / 9,47tr nhưng chatbot hiển thị 309 đơn / 9,6tr — 309 chính là **số khách** đã xuất HĐ bị gọi thành **số đơn** | Mô tả `get_promotion_effectiveness` trong `backend/nl2sql.py` | UAT trực tiếp 03/09 — câu C18 |
| 7 | Thiếu công cụ **tổng hợp** thưởng toàn công ty: chỉ có tool xếp hạng TOP 100 nên chatbot phải từ chối C48 (bỏ sót ~106/209 người). Dữ liệu có sẵn trên Bravo, chỉ thiếu tool cộng tổng. Chatbot từ chối là đúng, nhưng nên vá khoảng trống | `backend/report_templates.py` — thêm tool tổng hợp thưởng theo tháng/vùng/chức danh | UAT trực tiếp 03/09 — câu C48 |
| 6 | C31: khi hỏi "khách mới/tái kích hoạt bù được bao nhiêu", vế tăng thêm phải gồm **cả khách tái kích hoạt**, không chỉ khách xuất hiện lần đầu. Hiện loại bất đối xứng nên tỷ lệ bù đắp ra 32–40% trong khi thực tế 69–137% ở mọi ngưỡng churn — kết luận ngược hẳn | Mô tả tool luồng khách trong `backend/nl2sql.py` | UAT trực tiếp 03/09 — câu C31, mức High |
| 5 | CTKM: luôn hiển thị `program_code` và kỳ kèm tên chương trình. Nhiều chương trình trùng tên khác kỳ (`T9.2025_BPNGAM_10_TQ`, `Q4.2025_BPNGAM_10_TQ`, `Q1.2026_BPNGAM_10_TQ` đều là "Bổ phế Ngậm mua 10 tặng 01") — thiếu mã/kỳ thì câu trả lời không kiểm chứng được | Mô tả `get_promotion_effectiveness` trong `backend/nl2sql.py` | UAT trực tiếp 03/09 — câu C18 |

> Mục 4 cần đối chiếu `audit_log` của phiên hỏi C18 để biết 309 đến từ lệnh nào (tool trả 313, nên
> con số này phải phát sinh ở một lượt gọi khác). Chưa xác định được cơ chế thì chỉ siết mô tả tool,
> không kết luận nguyên nhân.

## 🔴 Sự cố vận hành phát hiện 03/09/2026 — job đồng bộ CTKM đã chết

**Không sửa được từ phía MCNA.** Repo chỉ ĐỌC các bảng `DMS_*` (không có lệnh `INSERT`/`UPDATE`/
`MERGE` nào), và `sync_warehouse.py` chạy theo hướng Bravo → `warehouse.db`. Job hỏng nằm ở chiều
ngược lại — **app DMS → Bravo**, thuộc hạ tầng DNH. Đây là phần cần chuyển cho đội vận hành DNH.

### Phạm vi chính xác

11 bảng nhóm khuyến mãi cùng dừng trong một khoảng 40 giây ngày **09/01/2026**, trong khi phần còn
lại của pipeline vẫn chạy bình thường tới hôm nay:

| Trạng thái | Bảng | `MAX(SyncAt)` |
|---|---|---|
| ✅ Bình thường | `DMS_KhachHang`, `DMS_DiTuyen`, `DMSSX_DonHangHdr`, `DMSSX_HopDongHdr`, `DMSSX_KhachHang` | 03/09/2026 15:01 |
| 🔴 **Đã chết** | `DMS_NhomCTKM` | 09/01/2026 11:11:31 |
| 🔴 | `DMS_CTKM` | 09/01/2026 11:11:32 |
| 🔴 | `DMS_CTKMOnTop1`, `DMS_CTKMOnTop2`, `DMS_CTKMUpTien`, `DMS_CTKMUpSanPham` | 09/01/2026 11:11:33 |
| 🔴 | `DMS_DonHangCTKM`, `DMS_TraKM`, `DMS_TraKMCt`, `DMS_DKKM`, `DMS_DKKMCt` | 09/01/2026 11:12:10 |
| ⚠️ Cũng dừng | `DMS_DonHangSS` | 04/01/2026 |
| ⚠️ | `DMS_NhomKHNPP` | 30/12/2025 |
| ⚠️ | `DMS_CTKMOnTop3` | `NULL` — chưa từng ghi |

Các mốc liền nhau theo thứ tự chạy cho thấy đây là **một job duy nhất phụ trách nhóm CTKM**, dừng sau
lần chạy thành công cuối. Hai bảng còn lại dừng quanh dịp đầu năm, nhiều khả năng cùng đợt.

### Hệ quả và việc cần làm

Đơn gắn CTKM: 12.447–13.545/tháng (09–12/2025) → 2.042 (01/2026, dừng giữa tháng) → **0** từ 02/2026.
C18, M35, V34 không trả lời được cho bất kỳ kỳ nào trong 2026.

1. **DNH**: tìm và khởi động lại job đồng bộ nhóm CTKM, chạy bù từ 09/01/2026.
2. **MCNA**: không cần sửa gì — khôi phục xong là `S12` và tool khuyến mãi tự chạy lại.
3. **Trước khi giao UAT nhóm khuyến mãi**: nếu chưa khôi phục, tester sẽ báo lỗi hàng loạt cho cùng
   một nguyên nhân. Nên hoặc khôi phục trước, hoặc ghi rõ trong pack là nhóm này chỉ kiểm kỳ 2025.

## Khoảng trống đồng bộ ETL — dữ liệu có trên Bravo nhưng chatbot không thấy

| Nguồn | Quy mô trên Bravo | Mở khoá được gì | Trạng thái kho local |
|---|---|---|---|
| `dbo.DMS_DiTuyen` | 1.785.213 dòng, 451 NV, 37.853 khách, 06/2022–nay. Có `IsPlaned`, `ArriveTime`, `LeaveTime` | C49, V16 và toàn bộ nhóm phủ tuyến/viếng thăm | **Không có bảng nào** |
| `DiscountRate` trên `vHoaDonTotal`/`vHoaDonETCTotal` | Mọi dòng hóa đơn | Chiết khấu trong C13 | Không có cột |
| `BranchCode`/`DistributorCode` trên hai view hóa đơn | Mọi dòng hóa đơn | Phần chi nhánh nội bộ của C25/M29 | Không có cột |

Ba nguồn này đều **có sẵn trên Bravo**, chỉ chưa đưa xuống `warehouse.db`. Chatbot từ chối các câu
liên quan là hợp lý với quyền truy cập của nó, nhưng đây là việc sửa được bằng ETL chứ không phải
giới hạn dữ liệu — nên tách khỏi nhóm "cần DNH mở nguồn".

## Điểm cần làm rõ định nghĩa (chưa phải lỗi)

| Câu | Hiện trạng | Cần làm |
|---|---|---|
| C20 | Ba số tổng khớp tuyệt đối với `S13` (217,56 / 226,84 / -9,28 tỷ), số khách lệch không đáng kể. Nhưng LFL chatbot -37,40 tỷ + "phần dư chưa phân loại" +2,87 tỷ, còn `S13` cho LFL -34,49 tỷ và phần dư = 0. Đã loại hai giả thuyết: 0 giao dịch thiếu mã khách; hàng trả cả kỳ chỉ -502 triệu | Xem `audit_log` phiên hỏi C20 để biết chatbot xếp khoản 2,87 tỷ vào đâu và theo tiêu chí gì. Chốt một định nghĩa LFL duy nhất rồi mới so |

## Gói gửi tester sau khi ba việc trên đạt

1. `outputs/uat_chatbot_dnh/uat_tracking_chatbot_dnh.xlsx`.
2. `docs/dap_an_bo_cau_hoi_dieu_hanh.md` và `docs/bao_cao_sql_doi_chung_138.md` qua kênh nội bộ.
3. `docs/doi_chieu_snapshot_vs_hoadon.md`.
4. Tài khoản đúng cây phân quyền; gửi mật khẩu bằng kênh riêng.
5. `docs/huong_dan_ban_giao_uat.md` và trang quyết định Nhóm A.

## Chưa làm trong hôm nay để tránh tốn tiền hoặc vượt quyền

- Chưa chạy thử chatbot 5 câu và chưa chạy vòng 138 câu qua API.
- Chưa thay đổi hạn mức câu hỏi vì cần quyết định ngân sách A/B.
- Chưa sửa định nghĩa tuần trong tháng vì hạn phản hồi là 10/09.
- Chưa sửa tài khoản production, deploy, gửi email hay gửi tài liệu ra ngoài.
- Đợt bổ sung sau commit `79ee98e` (báo cáo ETC thân thiện, lệnh kiểm trước UAT và cấu hình lint) chưa commit/push.

## Nợ kỹ thuật đã thấy nhưng không chặn UAT

- Cây `frontend/` cũ vẫn được giữ lại vì máy 24 còn dùng `.vercel/project.json`; ESLint đã bỏ qua cây
  này để tránh trộn kết quả của bản sao với ứng dụng production. Chỉ xóa sau khi đã chuyển cấu hình
  triển khai và được duyệt rõ ràng.
