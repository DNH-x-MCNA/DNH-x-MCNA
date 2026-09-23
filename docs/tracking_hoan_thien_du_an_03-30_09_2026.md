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

12 lượt timeout tập trung vào **vài câu lặp lại**. Đã đối chiếu từng lượt với mốc commit — xem
[doi_chieu_12_luot_timeout_23-09.md](doi_chieu_12_luot_timeout_23-09.md):

- **6/12 đã có bản sửa trỏ đúng** (mùa vụ ×4 → `074e98f`; khách phát sinh 3 tháng → `2954886`;
  độ phủ khách → `34f9dca`). Không lượt nào hỏng **sau** bản sửa → chỉ cần chấm lại, không sửa thêm.
- **6/12 chưa có bản sửa nào.** Nặng nhất: *"cá nhân/đội dưới 80% liên tiếp 3 tháng"* hỏng **4 lần
  trong một ngày 08/09** (2 hết credit lúc 11:27 và 13:31, 2 timeout lúc 13:46 và 13:48 — cách nhau
  2 phút, người dùng bấm lại ngay).

### ✅ Đã sửa — PR #65 (chưa merge, chưa deploy)

| Việc | Trạng thái |
|---|---|
| Lỗi HTTP 400 credit có `status = api_credit_exhausted` + thông báo rõ cho người dùng; lỗi gốc vẫn lưu trong `query_runs` | ✅ |
| Chặn lượt gọi model thiếu `username` hoặc `session_id` nhận diện được | ✅ |
| Watchdog cảnh báo **Teams** sau lượt web đầu tiên bị từ chối vì hết credit | ✅ |
| Watchdog cảnh báo **sớm, trước khi cạn** | ⚠️ **có code nhưng CHƯA BẬT** |

**22 test hồi quy mới.** Full suite **1.031 passed, 1 deselected**. Không gọi API trả phí.

Lưu ý phân biệt hai lớp cảnh báo: lớp **sau khi bị từ chối** đã hoạt động — lần tới hết credit sẽ có
tin Teams ngay thay vì im lặng. Lớp **trước khi cạn** mới là phần còn chặn.

### 🔴 Việc đang chặn: watchdog cần hai số từ anh Đăng

Watchdog không tự đọc được số dư từ Anthropic — cần mốc thủ công để suy ra tốc độ tiêu:

1. **Số dư API hiện tại** (USD)
2. **Thời điểm chụp số dư đó** (ngày giờ)

Lấy tại Anthropic Console → **Billing / Credits**. Chưa có hai số này thì cảnh báo **sớm** không bật
được — hệ thống vẫn chỉ biết kêu **sau khi** đã hết tiền, tức người chấm vẫn mất một lượt.

Đây là mục cấp bách nhất còn lại — credit đã cạn **ngay trong ngày 23/09**.

### Còn lại của mục này

**Cả 14 dòng** hết credit trong tháng 9 vẫn mang trạng thái lỗi chung, **chưa backfill** sang
`api_credit_exhausted`. Không chặn gì, nhưng ai đọc `query_runs` thô về sau vẫn thấy chúng giống lỗi
sản phẩm — nên đối chiếu kèm `error_message`.

> ⚠️ Con số **9** từng ghi ở đây là **sai phạm vi**: nó chỉ là phần rơi vào cửa sổ 11–21/09 mà
> checklist soi, không phải cả tháng. Quét cả tháng 9 ra **14**. Cùng một cái bẫy đã làm bảng phân
> loại lỗi ở trên bị ghi thiếu — đọc số nào cũng phải kèm cửa sổ thời gian sinh ra nó.

### 🔴 2. Lượt gọi model không có `username` — không truy được ai chạy

`AGENTS.md` bắt buộc mọi lượt gọi model trả phí phải có `username` riêng và `session_id` có tiền tố
nhận diện được; thiếu thì **không dùng để chấm UAT**. Hiện **không có chỗ nào ép** điều này.

Log còn lại: 8 lượt `unknown` tối 13/09 (≈ **81.900 đ** trong 30 phút) và một cụm `unknown` ngày
11/09 (≈ **51.400 đ**) — không truy được ai chạy. (Cụm `unknown`/`alice` ngày 21/09 23:56 thì vô
hại: 0 token, 0 đ, là smoke test.)

⚠️ Quét `query_runs` ngày 23/09 **không thấy dòng `unknown` nào**. Các lượt đó chỉ có trong
`backend/logs/cost_log.jsonl`. Nghĩa là chúng **không đi qua hàm ghi `query_runs`** — tự nó đã là
một phát hiện, không được đọc thành "đã sạch".

→ Chặn ở tầng gọi: **✅ xong trong PR #65**. Truy nguồn các lượt cũ: còn lại, và xem ghi chú trên —
các lượt `unknown` không có trong `query_runs` nên phải truy từ `cost_log.jsonl`.

### ✅ 3. Cổng kiểm trước UAT — ĐÃ ĐẠT (23/09, sau PR #75)

Chạy lại trên máy 24 sau khi deploy PR #75:

```
Da chay: 99 phep kiem DAT, 0 LECH, 2 muc khong chay duoc.
[DAT] Tai khoan va pham vi du lieu
[DAT] Phan quyen kenh ETC
[DAT] Bat bien so lieu cua 40 cong cu
KET LUAN: Cac cong kiem tra tu dong da dat; co the chuyen sang buoc test 5 cau.
```

Cả hai chỗ lệch **17.558.648đ** biến mất:

| Phép kiểm | Trước PR #75 | Sau |
|---|---:|---:|
| Tổng từng tháng vs một lần gọi | lệch 17.558.648 | **0** |
| Cộng địa bàn vs toàn công ty (09/2026) | lệch 17.558.648 | **`[DAT]`** |

Hai mục `get_promotion_effectiveness` và `get_receivables_period_compare` vẫn "không chạy được" —
thiếu nguồn đã biết, không phải lỗi.

#### Một số dư cần theo dõi, chưa chặn

Mục 11 (cây KPI) vẫn lệch **55.866.929đ (0,303%)** giữa rollup QLV của Bravo và tổng TDV dưới quyền —
dưới ngưỡng 1% nên `[DAT]`. Con số **không đổi** trước và sau PR #75, tập trung ở một QLV:
`Hoàng Công Thưởng` (rollup 941.259.147 vs cộng TDV 997.126.076). Đây là chênh ổn định, không phải
nhiễu; nên truy nguồn trước khi đóng UAT nhưng không chặn giao tài khoản.

### (đã đóng) Nguyên nhân lệch 17.558.648đ — giữ lại để tra cứu

Chạy `kiem_truoc_uat.ps1` trên **máy 24** ngày 23/09 (lần đầu chạy có `auth.db` thật, 30 tài khoản):

| Phép kiểm | Kết quả |
|---|---|
| Tài khoản và phạm vi dữ liệu | `[DAT]` |
| Phân quyền kênh ETC | `[DAT]` |
| Bất biến số liệu 40 công cụ | **`[CHUA DAT]`** — 97 đạt, **2 lệch**, 2 mục thiếu nguồn |

Cổng kết luận: *"CHƯA NÊN giao tài khoản cho tester."*

**Hai chỗ lệch đều đúng một số: 17.558.648đ.**

| Phép kiểm | Đường A | Đường B | Chênh |
|---|---:|---:|---:|
| Tổng từng tháng vs một lần gọi cả khoảng | chuỗi 973.135.481.906 | một lần gọi 973.153.040.554 | **+17.558.648** |
| Cộng địa bàn vs toàn công ty (09/2026) | toàn công ty 47.533.694.577 | địa bàn 47.551.253.225 | **+17.558.648** |

**Đã xác nhận bằng số trên máy 24** — đúng bộ chứng từ ETC đề ngày tương lai:

```
so dong: 4 | so chung tu: 2 | so khach: 1 | tong: 17.558.648d | ngay: 28/09/2026
  13126017 | NBI00003 | 80440000011 |  8.841.600
  13126017 | NBI00003 | 81180000008 |     82.857
  13126019 | NBI00003 | 80440000007 |  2.149.429
  13126019 | NBI00003 | 80440000018 |  6.484.762
```

Khớp **đến từng đồng**. Kênh OTC không có dòng nào.

#### Nguyên nhân: các đường tính không nhất quán

| Đường | Xử lý chứng từ tương lai |
|---|---|
| Chuỗi từng tháng | **cắt tại hôm nay** (PR #51) |
| Một lần gọi cả khoảng | dùng ngày cuối kỳ → **có cộng** |
| Báo cáo theo địa bàn | dùng ngày cuối kỳ → **có cộng** |

PR #51 mới cắt ở một số đường. Chính sách đã chốt (xem `cau_hoi_DNH_23-09.md` câu 2) là **không cộng
vào doanh thu tháng đang chạy nhưng có nêu ra** — nên hai đường còn lại phải sửa theo, không phải
ngược lại.

→ Giao phiên `backend/`: áp **cùng một** quy tắc cắt ngày tương lai cho mọi đường doanh thu, thay vì
để từng đường tự quyết. Khi DNH trả lời câu 2 thì chỉ phải đổi một chỗ.

> Kho dev đồng bộ đến 15/09 nên **không** tái lập được — chứng từ 28/09 chỉ có trên máy 24. Đây là
> ca phải đo trên máy thật, không suy từ kho dev.

### 🟡 4. Chấm lại 20 lượt — đơn giá gấp đôi ước tính ban đầu

Xem [checklist_cham_lai_22-09.md](checklist_cham_lai_22-09.md). Danh sách gốc 24 lượt; đối chiếu
`query_runs` miễn phí ngày 23/09 đóng được 6 mục mà không tốn lượt nào, nhưng phát hiện thêm 1 lượt
bị sót → **còn 20 lượt**.

**Phải chạy đối chiếu `query_runs` trước khi chấm lại bất cứ mục nào** — bước này miễn phí và đã
chứng minh cắt được ¼ hàng đợi. Anh Đăng tự xem danh sách này.

Khi chạy: bắt buộc truyền `username` riêng và `session_id` có tiền tố nhận diện được.

### 🟡 5. Cổng kiểm trên kho dev (tham chiếu)

Bản 03/09 ghi *"35 phép đạt, 25 mục bị bỏ"*. Chạy lại toàn bộ trên kho dev ngày 23/09:

| Phép kiểm | Kết quả |
|---|---|
| Tài khoản và phạm vi dữ liệu | `[CHUA DAT]` — không có `backend/auth.db` trên máy dev (đúng dự kiến), exit 2 |
| Phân quyền kênh ETC | **`[DAT]`** — 3/3 phép giữ đúng phạm vi ETC |
| Bất biến số liệu 40 công cụ | **`[DAT]`** — **99 phép đạt, 0 lệch, 2 mục không chạy được** |

**Từ 25 mục bị bỏ xuống còn 2**, và số phép kiểm chạy được tăng 35 → 99. Hai mục còn lại:
`get_promotion_effectiveness` (chuỗi liên kết CTKM chết 09/01/2026 — phía DNH) và
`get_receivables_period_compare` (lịch sử công nợ chỉ lưu từ 21/08/2026).

Đã rà `scripts/kiem_truoc_uat.ps1` trước khi khuyến nghị chạy trên máy thật: ba script nó gọi đều
tồn tại, cờ `--db` hợp lệ, và **không script nào gọi model trả phí**. Cổng cũng trả mã thoát đúng —
kiểm tài khoản không mở được kho thì exit 2, cổng báo `[CHUA DAT]` chứ không âm thầm cho qua.

**Còn lại: chạy trên máy 24.** Ở đó có `auth.db` thật nên phép kiểm thứ nhất mới có nghĩa, và hai
mục thiếu nguồn có thể giảm tiếp.

```powershell
powershell -ExecutionPolicy Bypass -File C:\dnh_chatbot\scripts\kiem_truoc_uat.ps1
```

### ✅ 6. Kiểm tài khoản thiếu phạm vi — đã chạy trên máy 24

`[DAT]`. 30 tài khoản, 30 đang hoạt động, **0 tài khoản đã duyệt nào thiếu phạm vi**. Một tài khoản
**chưa duyệt** thiếu vùng và mã nhân viên: `linh.nguyen4` (vai `qlv`) — không chặn gì, nhưng phải bổ
sung trước khi duyệt.

Con số "12 tài khoản QLV cũ không hợp lệ" trong bản 03/09 là của **kho dev**, không phải production.

### (cũ) Kiểm tài khoản thiếu phạm vi trên `auth.db` máy 24

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
| #65 | Bắt lỗi hết credit, chặn lượt gọi thiếu `username`, watchdog cảnh báo dự phòng (Codex) — **chưa merge** |
| #66 | "Dưới 80% liên tiếp 3 tháng": payload cũ gửi model 0 kết quả, bản sửa gửi đủ 8/8 đội và 54/54 cá nhân (Codex) — **chưa merge** |

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

## C08 — checker sai phương pháp, chatbot đúng

Người chấm ghi *"tháng thấp nhất của kênh ETC là tháng 9"*. Điều tra
([dieu_tra_c08_mua_vu_23-09.md](dieu_tra_c08_mua_vu_23-09.md)): checker tính cả **tháng 9/2026 chưa
hết tháng** vào nền mùa vụ, kéo chỉ số tháng đó xuống thành thấp nhất giả. Tool thì loại tháng đang
chạy — đúng phương pháp.

Tái lập trên kho dev, chỉ đổi một biến: tính cả tháng cụt → thấp nhất là **tháng 9 (70,27%)**; loại
tháng cụt → **tháng 2 (82,26%)**, khớp đúng số chatbot đã trả.

**Cần sửa checker S80, không sửa chatbot.** Một chỉ số mùa vụ đổi kết luận theo ngày bấm nút thì
không phải chỉ số mùa vụ.

## C20 — khoản dư "chưa phân loại" đã được sửa từ 07/09, tài liệu chưa kịp ghi

Bản 03/09 ghi C20 là điểm treo: *"LFL chatbot −37,40 tỷ + phần dư chưa phân loại +2,87 tỷ, còn S13
cho LFL −34,49 tỷ và phần dư = 0"*, và đề xuất đọc `audit_log` để tìm chatbot xếp 2,87 tỷ vào đâu.

Commit **`b957283` (07/09)** — *"fix(uat): route and reconcile executive checks"* — đã xử lý, nhưng
tiêu đề không nhắc C20 nên tra commit log không ra. Liên kết nằm ở **ghi chú trong code**
([report_templates.py](../backend/report_templates.py), `_movement_summary`):

```python
# Neu co doanh thu am do hang tra, "doanh thu them - doanh thu mat" khong bang delta.
# Tach ro phan dieu chinh nay thay vi de mot khoan du "chua phan loai" nhu C20 UAT.
non_positive_adjustment = classified_delta - (added + lfl_delta - lost)
```

Đo lại trên kho dev, kỳ 08/2026 (miễn phí, không gọi model):

| | Giá trị |
|---|---:|
| Tổng kỳ này | 80,55 tỷ |
| Tổng kỳ trước | 74,84 tỷ |
| Biến động | **+5,72 tỷ** |
| LFL | +3,83 tỷ |
| Khách mới | +1,99 tỷ |
| Tái kích hoạt | +14,86 tỷ |
| Ngừng mua | −14,96 tỷ |
| **Điều chỉnh âm (hàng trả)** | **−0,01 tỷ** |
| **Cộng lại** | **+5,72 tỷ** ✓ khớp biến động |

**Không còn khoản dư chưa phân loại.** Payload cân bằng tuyệt đối, và phần từng gây tranh cãi nay có
tên riêng `non_positive_revenue_adjustment` — ở kỳ này chỉ **10 triệu**, tức 0,2% biến động, chứ
không phải 2,87 tỷ.

### Còn lại

Việc *cân bằng* đã xong. Chưa xác nhận được là **mức LFL** của chatbot có còn lệch S13 hay không —
cần một trong hai:

1. **SQL của checker S13** để đối chiếu định nghĩa LFL (nghi ngờ: S13 gộp phần điều chỉnh âm vào
   LFL, chatbot tách riêng — cộng lại thì −37,40 + 2,87 = −34,53 so với −34,49 của S13, lệch
   40 triệu); hoặc
2. **Chấm lại C20 một lượt** sau bản sửa 07/09 — lượt gốc chạy trước đó nên số cũ không còn đại diện.

Đây là **lần thứ ba trong ngày** gặp cùng một kiểu: tài liệu ghi "chưa sửa" trong khi commit có sửa
nhưng tiêu đề không nhắc tên câu. Cách tra đúng: `git log -S` theo tên trường/mã câu, hoặc grep ghi
chú trong code.

## Nợ kỹ thuật đã thấy nhưng không chặn UAT

- Cây `frontend/` cũ vẫn giữ vì máy 24 còn dùng `.vercel/project.json`; ESLint đã bỏ qua cây này để
  khỏi trộn kết quả bản sao với ứng dụng production. Chỉ xóa sau khi chuyển cấu hình triển khai và
  được duyệt rõ ràng.
- 10 nhánh cục bộ đã merge chưa dọn.
