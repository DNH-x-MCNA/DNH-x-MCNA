# Tracking hoàn thiện dự án DNH — cập nhật **23/09/2026**

> **Bản 03/09 đã cũ 20 ngày và gây hiểu nhầm.** Nó liệt 6 việc trong "đợt sửa prompt gộp — CHƯA
> deploy", nhưng kiểm lại trong code ngày 23/09 thì **5/6 đã làm xong**, chỉ còn 1 mục đang chờ DNH.
> Ai đọc bản cũ rồi bắt tay làm lại là mất công. Mục này ghi lại để lần sau không lặp: **tài liệu
> tracking phải đối chiếu code trước khi dùng làm danh sách việc.**

Còn **7 ngày** tới hạn đóng UAT 30/09/2026.

---

## Đợt sửa prompt gộp — đã xong 5/6, không phải 0/6

Kiểm bằng cách đọc code ngày 23/09, kèm vị trí cụ thể:

| # | Việc | Trạng thái | Bằng chứng |
|---:|---|---|---|
| 1 | So sánh hai kênh phải gọi `get_top_products` hai lần | ✅ xong | `nl2sql.py:2984` — *"goi get_top_products HAI LAN voi cung khoang ngay/limit: mot lan channel=OTC va mot lan channel=ETC"* |
| 3 | Free-SQL viết thẳng `c.area_code` lên `dms_khachhang` (cột không tồn tại) | ✅ xong | `schema_context.py:96` ghi rõ `dms_khachhang` có `city_id`, **không** có `area_code`; đường join đúng `customer_code → dms_khachhang.code → city_id → dim_tinhthanhpho.area_code` được mô tả ở dòng 47–49, 62–63 |
| 5 | CTKM luôn hiện `program_code` + kỳ kèm tên | ✅ xong | `nl2sql.py:1755` — *"BAT BUOC hien ca program_code, program_name va period tu payload"*; dòng 1763 xử lý `same_name_program_codes` |
| 6 | C31: vế tăng thêm phải gồm **cả** khách tái kích hoạt | ✅ xong | `nl2sql.py:1061` — `added_revenue = new_or_first_observed_revenue + reactivated_revenue` |
| 7 | Thiếu tool **tổng hợp** thưởng toàn công ty (C48) | ✅ đã quyết **không** mở tool mới | `report_templates.py:12858` — *"C48 UAT 07/09: dung chung tool luong da co thay vi mo them tool moi (bo 40 phep doi chieu…)"*. Dùng `salary_achievement_summary` |
| 2 | Định nghĩa "tuần trong tháng" | ⏳ **chờ DNH** | `schema_context.py:382–386` đang áp quy tắc tạm: gặp "tuần trong tháng"/"tuần này"/"từng tuần" mà người hỏi không nói rõ cách chia thì **hỏi lại**, không tự chọn |

**Kết luận: mục này không còn là một "đợt deploy gộp" nữa.** Chỉ còn #2, và nó chặn ở phía DNH chứ
không phải ở code. Quy tắc gộp thay đổi mô tả tool/system prompt vào **một** lần deploy (cache chiếm
71% chi phí) vẫn giữ nguyên cho các thay đổi sau này.

---

## Việc còn lại thật sự — xếp theo mức chặn

### 🔴 1. Lỗi hết credit đang bị ghi vào sổ chấm như lỗi sản phẩm

Quét `query_runs` cả tháng 9 trên máy 24 (23/09) — **nặng hơn con số 13 ghi trong checklist**, vì
checklist chỉ soi 11–21/09:

| Loại | Số lượt | Thực chất |
|---|---:|---|
| `credit balance is too low` | **14** | Hết tiền API — **không phải lỗi sản phẩm** |
| `The read operation timed out` | **12** | Lỗi thật |
| Kẹt `running`, không có `error_message` | 3 | Không chạy tới cuối hàm |
| `Client closed stream` | 2 | Người dùng đóng trước khi xong |

Người chấm UAT chỉ nhìn thấy chữ **"Lỗi"**, không phân biệt được hai loại, nên ghi vào sổ như chatbot
hỏng. Nặng nhất: `thuan.pham` ngày 11/09 hỏi **cùng một câu 5 lần trong 75 phút** (02:58 → 04:12
UTC), cả 5 lần đều hết credit.

🔴 **Credit đang cạn lại ngay lúc này.** Lượt `2026-09-23 06:43:25 | thuan.pham` hỏng vì hết credit —
**13 phút trước** chính lượt V34 đang điều tra. Việc giao phiên `backend/` không còn là dự phòng.

12 lượt timeout tập trung vào **vài câu lặp lại**: "mùa vụ cao/thấp" 4 lần, "dưới 80% liên tiếp
3 tháng" 3 lần. Đây là câu hỏi hỏng có hệ thống, không phải sự cố lẻ.

Đã grep toàn bộ `backend/` và `src/`: **không có chỗ nào bắt lỗi credit**. Chưa ai làm.

→ Giao phiên `backend/` (Codex) 23/09: bắt riêng lỗi 400 credit với thông báo phân biệt được, và cho
`backend/health_watchdog.py` cảnh báo **trước khi** số dư cạn hẳn.

### 🔴 2. Lượt gọi model không có `username` — không truy được ai chạy

`AGENTS.md` bắt buộc mọi lượt gọi model trả phí phải có `username` riêng và `session_id` có tiền tố
nhận diện được; thiếu thì **không dùng để chấm UAT**. Hiện **không có chỗ nào ép** điều này.

Log còn lại: 8 lượt `unknown` tối 13/09 (≈ **81.900 đ** trong 30 phút) và một cụm `unknown` ngày
11/09 (≈ **51.400 đ**) — không truy được ai chạy. (Cụm `unknown`/`alice` ngày 21/09 23:56 thì vô
hại: 0 token, 0 đ, là smoke test.)

⚠️ Quét `query_runs` ngày 23/09 **không thấy dòng `unknown` nào**. Các lượt đó chỉ có trong
`backend/logs/cost_log.jsonl`. Nghĩa là chúng **không đi qua hàm ghi `query_runs`** — tự nó đã là
một phát hiện, không được đọc thành "đã sạch".

→ Chặn/cảnh báo ở tầng gọi: phiên `backend/`. Truy nguồn các lượt cũ: phiên `docs/`.

### 🟡 3. Chấm lại 20 lượt ≈ 80.000 đ

Xem [checklist_cham_lai_22-09.md](checklist_cham_lai_22-09.md). Danh sách gốc 24 lượt; đối chiếu
`query_runs` miễn phí ngày 23/09 đóng được 6 mục mà không tốn lượt nào, nhưng phát hiện thêm 1 lượt
bị sót → **còn 20 lượt**.

**Phải chạy đối chiếu `query_runs` trước khi chấm lại bất cứ mục nào** — bước này miễn phí và đã
chứng minh cắt được ¼ hàng đợi. Anh Đăng tự xem danh sách này.

Khi chạy: bắt buộc truyền `username` riêng và `session_id` có tiền tố nhận diện được.

### 🟡 4. Bộ kiểm bất biến 40 công cụ phải chạy lại trên máy 24

Kho dev chạy được 35 phép đạt, 0 lệch; **25 mục bị bỏ** vì kho dev thiếu bảng/cột hoặc không có dữ
liệu. Chưa chạy trên máy 24. Dùng `scripts/kiem_truoc_uat.ps1` (chạy tuần tự kiểm tài khoản, phân
quyền ETC, bất biến 40 công cụ, kết luận Đạt/Chưa đạt).

### 🟡 5. Kiểm tài khoản thiếu phạm vi trên `auth.db` máy 24

`scripts/kiem_tai_khoan_thieu_pham_vi.py`. Kho local có 12 tài khoản QLV cũ không hợp lệ — **đây chưa
phải kết luận về production**, phải chạy trên máy 24 mới biết.

### ⏳ 6. Câu hỏi đang chờ DNH

Xem [cau_hoi_DNH_23-09.md](cau_hoi_DNH_23-09.md) — 4 câu chặn đóng UAT:

| # | Câu | Chặn |
|---:|---|---|
| 1 | "Doanh số ETC" là toàn kênh hay một miền? | Mục #22/#23 checklist |
| 2 | Hóa đơn ETC đề ngày 28 hàng tháng: ghi trước hay nhập sai? | Cách tính doanh số tháng đang chạy |
| 3 | 11 khách Miền Trung có doanh thu nhưng không có dòng FACT cấp nhân viên (13.173.440 đ) | Phép đối soát doanh thu (PR #62) |
| 4 | Đơn có `DMSEmpId2` thì tính cho đội nào? | v24, v34 |

Cộng thêm, từ bản cũ và vẫn còn treo: định nghĩa "tuần trong tháng" (A9), nguồn giá tồn kho (B03,
969.269 đơn vị đang = 0 đ), nguồn target quý (mục #24 checklist), UPN Teams + webhook Flow (PR #41),
đặc tả SMTP.

### ✅ 7. v34 — đã chốt hết, không còn điểm treo

Payload lượt thật (`2026-09-23 06:56:39`) cho thấy tool trả **20** chương trình, model hiển thị
**8** và tự ghi ra *"Đang liệt kê 8/20"*. Checker `ORDER BY p.Code` không có `TOP` nên ảnh chụp
toàn `MT_*`. Cùng phạm vi, khác cách sắp xếp — **không phải lỗi**.

---

## Đã làm xong ngày 23/09

| PR | Nội dung |
|---|---|
| #49 | `_detail_cutoff()` đọc mốc từ dữ liệu thay vì hằng số — vá lỗ 20 tháng ra 0 đồng |
| #50, #55 | Checklist chấm lại: đóng 6 mục miễn phí, hạ 24 → 20 lượt |
| #51 | Chứng từ ngày tương lai không cộng vào tháng đang chạy |
| #52 | v21 — hai định nghĩa cửa sổ nhìn lại |
| #53, #61 | Runbook triển khai máy 24 (restart theo **thư mục** thay đổi, cổng 8010) |
| #59, #60 | Điều tra v24 — 1 lỗi thật, 2 bất đồng định nghĩa |
| #62 | Đối soát doanh thu: cộng thêm Kênh MT và Chợ sỹ Miền Nam (Codex) |
| **#63** | **v34 + v24** — chốt đội đúng kỳ quá khứ, khử trùng `dmsid` |
| #64 | Cập nhật tracking này + `scripts/doc_query_runs_may_24.py` |

**PR #63 đã merge và ĐÃ DEPLOY** lên máy 24 lúc 14:56 ngày 23/09 (`9a3a5c4`). Xác nhận:
`_team_of_qlv_tu_luong` và `_NV_THEO_DMSID` có mặt trên đĩa, `Application startup complete`,
uvicorn chạy trên `0.0.0.0:8010`.

### Hai bài học ghi lại từ hôm nay

1. **Bravo đọc được thẳng từ máy dev** qua `_q_bravo()`. Tôi đã viết vào tài liệu rằng "không tái lập
   được vì kho local thiếu bảng CTKM" rồi dừng ở suy luận — thử một câu `SELECT TOP (1) 1` thì ra
   ngay, và nhờ đó tái lập v34 khớp đến từng đồng. Các bảng chỉ có trên Bravo: nhóm `DMS_*`, và lịch
   sử `FACT_*` dài hơn cửa sổ sync.
2. **`Invoke-WebRequest` ném exception ở mọi mã 4xx/5xx**, nên lệnh kiểm sức khỏe viết tắt in ra
   chữ "LOI" đúng lúc backend đang khỏe (404 ở `/` là bình thường). Thêm vào đó, kiểm ngay sau
   `Restart-Service` thì uvicorn chưa nạp xong và ra `Unable to connect`. Hai cái cộng lại làm báo
   động nhầm hai lần trong một buổi. Runbook đã sửa: đọc `$_.Exception.Response.StatusCode` —
   **có mã HTTP nào cũng là ĐẠT**, và chờ vài giây trước khi kiểm.
3. **Đừng kết luận "chưa ai sửa" từ tiêu đề commit.** Hai lần trong một ngày mắc đúng lỗi này. Phải
   `git log -S` theo mã câu **hoặc** grep ghi chú trong code — liên kết thường chỉ nằm ở comment.

---

## 🔴 Sự cố vận hành — job đồng bộ CTKM đã chết (phát hiện 03/09, **vẫn chưa khôi phục**)

**Không sửa được từ phía MCNA.** Repo chỉ ĐỌC các bảng `DMS_*` (không có `INSERT`/`UPDATE`/`MERGE`
nào), và `sync_warehouse.py` chạy theo hướng Bravo → `warehouse.db`. Job hỏng nằm ở chiều ngược lại —
**app DMS → Bravo**, thuộc hạ tầng DNH.

11 bảng nhóm khuyến mãi cùng dừng trong một khoảng 40 giây ngày **09/01/2026**, trong khi phần còn
lại của pipeline vẫn chạy bình thường:

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

Đơn gắn CTKM: 12.447–13.545/tháng (09–12/2025) → 2.042 (01/2026, dừng giữa tháng) → **0** từ 02/2026.
**C18, M35, V34 không trả lời được cho bất kỳ kỳ nào trong 2026.**

1. **DNH**: tìm và khởi động lại job đồng bộ nhóm CTKM, chạy bù từ 09/01/2026.
2. **MCNA**: không cần sửa gì — khôi phục xong là `S12` và tool khuyến mãi tự chạy lại.
3. **Trước khi giao UAT nhóm khuyến mãi**: nếu chưa khôi phục, tester sẽ báo lỗi hàng loạt cho cùng
   một nguyên nhân. Nên hoặc khôi phục trước, hoặc ghi rõ trong pack là nhóm này chỉ kiểm kỳ 2025.

> Ngày 23/09 điều tra v34 xác nhận lại: mốc phủ liên kết CTKM vẫn dừng ở **09/01/2026**. Vì vậy kỳ
> báo cáo mặc định của tool khuyến mãi lùi về **12/2025** — đúng thiết kế, không phải lỗi.

---

## Khoảng trống đồng bộ ETL — dữ liệu có trên Bravo nhưng chatbot không thấy

| Nguồn | Quy mô trên Bravo | Mở khoá được gì | Trạng thái kho local |
|---|---|---|---|
| `dbo.DMS_DiTuyen` | 1.785.213 dòng, 451 NV, 37.853 khách, 06/2022–nay. Có `IsPlaned`, `ArriveTime`, `LeaveTime` | C49, V16 và toàn bộ nhóm phủ tuyến/viếng thăm | **Không có bảng nào** |
| `DiscountRate` trên `vHoaDonTotal`/`vHoaDonETCTotal` | Mọi dòng hóa đơn | Chiết khấu trong C13 | Không có cột |
| `BranchCode`/`DistributorCode` trên hai view hóa đơn | Mọi dòng hóa đơn | Phần chi nhánh nội bộ của C25/M29 | Không có cột |
| Lịch sử `FACT_TongHopKhachHang` | 22 mốc, 01/2025–nay | Chốt đội cho kỳ quá khứ | Chỉ giữ **90 ngày** (`sync_fact_tonghopkhachhang(days=90)`) |

Ba nguồn đầu **có sẵn trên Bravo**, chỉ chưa đưa xuống `warehouse.db` — sửa được bằng ETL, không
phải giới hạn dữ liệu, nên tách khỏi nhóm "cần DNH mở nguồn".

Dòng thứ tư là nguyên nhân lỗi v34. **Đã xử lý bằng đường khác** (PR #63): dùng
`fact_thongketinhluong` — kho đã giữ sẵn 400 ngày và đúng là bảng checker dùng — thay vì nới cửa sổ
đồng bộ.

---

## Điểm cần làm rõ định nghĩa (chưa phải lỗi)

| Câu | Hiện trạng | Cần làm |
|---|---|---|
| C20 | Ba số tổng khớp tuyệt đối với `S13` (217,56 / 226,84 / −9,28 tỷ), số khách lệch không đáng kể. Nhưng LFL chatbot −37,40 tỷ + "phần dư chưa phân loại" +2,87 tỷ, còn `S13` cho LFL −34,49 tỷ và phần dư = 0. Đã loại hai giả thuyết: 0 giao dịch thiếu mã khách; hàng trả cả kỳ chỉ −502 triệu | Xem `audit_log` phiên hỏi C20 để biết chatbot xếp khoản 2,87 tỷ vào đâu và theo tiêu chí gì. Chốt một định nghĩa LFL duy nhất rồi mới so |

---

## Nợ kỹ thuật đã thấy nhưng không chặn UAT

- Cây `frontend/` cũ vẫn giữ vì máy 24 còn dùng `.vercel/project.json`; ESLint đã bỏ qua cây này để
  khỏi trộn kết quả bản sao với ứng dụng production. Chỉ xóa sau khi chuyển cấu hình triển khai và
  được duyệt rõ ràng.
- 10 nhánh cục bộ đã merge chưa dọn.
