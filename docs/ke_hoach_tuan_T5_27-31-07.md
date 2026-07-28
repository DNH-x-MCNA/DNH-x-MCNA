# Kế hoạch tuần T5 — 27/07 → 31/07/2026 (dự án DNH)

## Context

Demo #1 Chatbot hạn **09/08** (còn ~2 tuần: T5 rồi T6). Tuần T4 vừa xong đã chốt ngưỡng lương thưởng
theo văn bản gốc, bịt lỗ hổng phân quyền, và đưa toàn bộ code live-only vào git.

Còn đúng **một rủi ro ở mức chặn demo**: chatbot và báo cáo trả lời công nợ từ **hai nguồn khác
nhau** (R-B). Chatbot đọc bảng Supabase — vốn là Excel nhập tay một lần đầu dự án, không tự làm mới;
chính công thức dòng dõi đó từng thổi nợ một khách lên 9,17 tỷ trong khi thật là 0,61 tỷ. Hiện mới
vá cảnh báo (chatbot chịu nói "chưa tra cứu được"), chưa thay nguồn. Kịch bản demo đang ghi *"không
đưa câu hỏi công nợ vào demo cho tới khi xử lý xong"* — nhưng công nợ là câu C-level chắc chắn hỏi,
né được ở demo chứ không né được ở UAT tháng 9.

Ngoài ra: 5 câu demo chưa từng thử lần nào, 4 câu cần chạy lại vì trước đo ở ngưỡng 80% đã bỏ, dữ
liệu chi phí AI đang nằm ngoài tầm với và có thể mất khi deploy, và 2 chênh lệch số liệu còn treo.

**Kết quả mong muốn cuối tuần**: công nợ trên chatbot khớp báo cáo (lệch ≤0,05%), kịch bản demo
không còn ô trống, dữ liệu chi phí AI đã an toàn và đọc được.

---

## Phân bổ theo ngày

| Ngày | Trọng tâm | Thực tế |
|---|---|---|
| **T2 27/07** | 🔴 Spike quyền chạy SP (chặn) · sao lưu dữ liệu chi phí · soi secret | ✅ Spike xong (SP 15,1s). **Làm luôn TOÀN BỘ R-B 1.1→1.6** (vượt kế hoạch 2 ngày) + sửa tầng rollup KPI + tách 3 mốc + gộp 2 repo |
| **T3 28/07** | ~~R-B P0: bảng local + hàm đồng bộ + đối chiếu số~~ | ✅ Đã xong từ T2 → **xếp lại việc**: sửa 2 bug đang sai số thật (chỉ tiêu daily KPI sai tháng = chênh 1,13 tỷ; `get_audit_log` crash với tài khoản giới hạn vùng) + vá 3 lỗ hổng script ground truth + bổ sung đáp án R2/R4 |
| **T4 29/07** | ~~R-B P0: đổi nguồn + chặn đường cũ · deploy~~ → **Kiểm chứng demo** | Đã xong T2. Chuyển sang: hỏi lại 5 câu KPI (C6, C7, R3, Q1, **Q2**) ở phiên mới |
| **T5 30/07** | ~~R-B P1: tool công nợ tổng hợp~~ → **Kiểm chứng demo (tiếp)** | Đã xong T2. Chuyển sang: 7 câu chưa từng hỏi (C8, R2, R4, X1, X2, X4, X5) |
| **T6 31/07** | ~~Truy 2 chênh lệch~~ · công cụ đọc chi phí AI · dọn máy 24 · báo cáo tuần | ✅ 2 chênh lệch **đã đóng cả hai** (27/07 và 28/07) |

---

## Hạng mục 1 — R-B: đưa công nợ đúng vào chatbot ⭐ *(lớn nhất)*

### 1.0 SPIKE CHẶN — làm đầu tiên sáng thứ Hai, ~30 phút

Chạy **trên máy chủ live** `C:\dnh_chatbot`, trước khi viết bất kỳ dòng code nào:

- Tài khoản Bravo của chatbot có quyền `EXECUTE` trên `usp_DeptAccDueDate_GetData` không?
- Hai repo dùng **tên biến môi trường khác nhau** (`BRAVO_SQL_*` ở `D:\DNH` vs `BRAVO_*` ở chatbot)
  và có thể khác cả user/database — xác nhận chatbot trỏ đúng database chứa SP.
- In ra: danh sách cột result set, số dòng, **thời gian chạy (giây)**, tổng `CloseBal`.

**Thời gian chạy quyết định thiết kế lịch đồng bộ** (xem 1.3). **Nếu không có quyền → báo ngay và
xin DNH cấp**, đây là việc phải chờ phía khách, không tự giải quyết bằng code. Phương án lùi trong
trường hợp đó: job bên `D:\DNH` đẩy kết quả SP lên Supabase (xấu hơn, chỉ dùng khi kẹt).

### 1.1 Bảng local mới — `D:\DNH-x-MCNA\backend\local_warehouse.py`

Thêm `fact_congno_khachhang` vào hằng `SCHEMA`: `snapshot_date`, `snapshot_at`, `customer_code`,
`customer_name`, `sales_channel`, `area_code`, `balance_end`, 4 cột bucket
(`overdue_1_15/15_30/30_45/gt_45`), `total_overdue` (tính sẵn khi ghi). Index theo customer/channel/area.

Một dòng = **(khách hàng × kênh)** — khách bán cả 2 kênh có 2 dòng, nên mọi truy vấn phải `SUM`.

### 1.2 Hàm đồng bộ — `D:\DNH-x-MCNA\backend\sync_warehouse.py`

**Port nguyên văn** từ `D:\DNH\src\alerts.py::get_bravo_receivables_snapshot` (~dòng 446-550) — đã
verify khớp 100% với báo cáo nội bộ DNH. Ba đặc điểm **không được đơn giản hoá**:

1. SP trả **nhiều result set** → phải dùng `raw_connection()` + vòng `cur.nextset()`, chọn result
   set có đồng thời `CustomerCode` và `OverDueAmount`. Dùng helper `bravo_query()` sẵn có sẽ lấy nhầm.
2. `raw.rollback()` trong `finally` — SP tạo bảng tạm; rollback đảm bảo read-only tuyệt đối với Bravo.
3. Map cột giữ y nguyên: `ClassCode='TM'`→OTC, `AreaCode='MB1'`→`MB`, NULL→suy từ tiền tố mã khách
   (dùng lại `backend/region_map.py::region_from_customer_code`).

**Hai chốt an toàn bắt buộc** (đây là dữ liệu người dùng hỏi trực tiếp, khác các bảng khác):
- **Không bao giờ ghi đè bằng bảng rỗng** — SP lỗi quyền/VPN chập có thể trả 0 dòng; ghi đè sẽ làm
  chatbot mất khả năng trả lời công nợ mà không ai biết. Gặp 0 dòng → giữ snapshot cũ, báo lỗi.
- `BEGIN IMMEDIATE` + `PRAGMA busy_timeout` — backend đọc song song, tránh `database is locked`.

Khuôn mẫu tái sử dụng: `sync_fact_tonghopkhachhang()` và `sync_hoadon_recent()` trong cùng file.

### 1.3 Lịch đồng bộ — cạm bẫy timeout

`backend/server_deploy/sync_scheduler.ps1` đặt timeout **90 giây**. Nếu nhét SP vào vòng sync chung
mà SP chạy lâu hơn, PowerShell kill cả tiến trình → mất luôn sync hóa đơn. Xử lý theo kết quả spike:

- SP **< 20s** → gọi trong `main()` với throttle 60 phút, không cần lịch riêng *(đơn giản nhất)*.
- SP **> 60s** → thêm cờ `--congno-only`, chạy lịch riêng timeout 300s.

Dù chọn hướng nào, bọc `try/except` để SP lỗi không làm hỏng phần còn lại của lần sync.

### 1.4 Đổi nguồn `_customer_receivable` — `backend/report_templates.py`

Giữ **nguyên chữ ký và 5 khóa trả về** hiện có → **không phải sửa `nl2sql.py`** cho phần P0. Thay
thân hàm bằng truy vấn kho local. Thêm khóa mới (không phá tương thích): `receivable_as_of`,
`receivable_source`, và 4 bucket để chatbot trả lời được "quá hạn bao lâu".

Bốn trạng thái cần phân biệt rõ:

| Tình huống | Hành vi |
|---|---|
| Bảng chưa có dữ liệu | `"unavailable"` + cảnh báo bắt buộc *"chưa tra cứu được"* — **tuyệt đối không** nói "khách không có nợ" |
| Snapshot cũ > 6 giờ | Trả số nhưng kèm cảnh báo mốc thời gian |
| Khách không có dòng | *"không có dư nợ tại thời điểm X theo báo cáo công nợ gốc"* |
| Bình thường | Trả số + mốc snapshot |

**Gỡ cảnh báo bắt buộc cũ** ("bảng nhập tay, CÓ THỂ SAI") — sau khi đổi nguồn thì nó thành sai sự
thật và làm mất uy tín tại demo.

*Thay đổi hành vi có chủ ý:* khách có cả 2 kênh, bản cũ chỉ trả OTC; bản mới **cộng cả hai**. Ghi rõ
vào docstring.

### 1.5 Chặn đường quay lại nguồn cũ *(bỏ bước này thì sửa như không sửa)*

`_customer_receivable` chỉ phục vụ câu hỏi từng khách. Câu tổng hợp ("top khách nợ quá hạn") đi qua
tool `query_inventory_receivables` → vẫn ra **số Excel cũ**, im lặng. Ba sửa nhỏ:

- `backend/schema_context.py` — thêm mô tả bảng mới vào khối kho local; **xoá** `receivable_detail`/
  `receivable_etc` khỏi khối Supabase.
- `backend/nl2sql.py` — định tuyến câu hỏi công nợ sang `query_database` (kho local) thay vì Supabase.
- `backend/query_engine.py::validate_sql` — **chốt fail-closed**: chặn cứng mọi SQL đụng
  `receivable_detail|receivable_etc`. Đây là lớp bảo vệ không phụ thuộc AI có đọc prompt đúng hay
  không — đúng bài học từ bản vá phân quyền tuần trước.

**Không xoá bảng Supabase**: còn một chỗ dùng thật ở `D:\DNH\src\alerts.py` (dự phòng khi Bravo lỗi),
và là dữ liệu gốc khách gửi. Sau khi chặn ở 3 chỗ trên thì rủi ro đọc nhầm bằng 0.

### 1.6 P1 — tool báo cáo công nợ tổng hợp

Sau bước 1.5, tài khoản `regional_director`/`qlv` **không còn đường nào** hỏi công nợ tổng hợp (mọi
tool SQL tự do đã bị chặn với tài khoản có giới hạn phạm vi). Thêm template `receivables_overview`
trong `report_templates.py`: tổng dư nợ, tổng quá hạn, tỷ lệ, tách theo kênh + vùng, top N khách quá
hạn. Đăng ký vào `TEMPLATES` + danh sách template có ép phạm vi, thêm định nghĩa tool vào `nl2sql.py`.

Khuôn mẫu gần nhất để copy: **`inventory_by_region()`** trong cùng file — cũng là ca "thay bảng
Supabase bằng bảng local từ Bravo", đã có sẵn cách ép `scope_area_code`.

---

## Hạng mục 2 — Hoàn tất kiểm chứng kịch bản demo

Mở **phiên chat mới** mỗi lượt (hỏi lại trong phiên cũ sẽ nhận câu trả lời cũ từ bộ nhớ hội thoại),
đối chiếu `backend/logs/audit_log.jsonl` — không có dòng log tương ứng thì **không tính là đã kiểm**.

**5 câu chưa từng thử**: C8 (cây doanh thu MB theo QLV/TDV — đang nằm trong luồng demo đề xuất mà
chưa hỏi lần nào), R2 (top khách vùng), R4 (tồn kho vùng), X2 (tồn kho chết), X4 (đơn dồn cuối tháng).
R2/R4 **chưa có đáp án đúng** — cần chạy `scripts/demo1_ground_truth.py` bổ sung trước.

**4 câu phải chạy lại** vì trước đo ở ngưỡng 80% đã bỏ: C6, C7, R3, Q1.

**Sửa lỗi đánh số trong tài liệu**: mã câu ở bảng kết quả Lô A lệch so với bảng kịch bản (Lô A ghi
"C5" nhưng nội dung là C6, "C6" là nội dung C7...). Đọc theo nội dung, và sửa lại cho khớp.

---

## Hạng mục 3 — Chi phí AI

**Việc gấp (thứ Hai, ~15 phút)**: kéo `backend/logs/cost_log.jsonl` từ máy 24 về nơi an toàn. File
này bị `.gitignore` loại trừ, chỉ tồn tại trên máy chủ — **deploy xoá thư mục `logs/` là mất sạch
lịch sử**. Đây là nguyên liệu duy nhất cho cam kết ước tính chi phí (hạn tuần 8–10).

**Việc chính (thứ Sáu)**: viết script đọc/tổng hợp — hiện **1 nơi ghi, 0 nơi đọc**. Ba lưu ý:
- Một câu hỏi sinh **tới 8–9 dòng log** (mỗi vòng gọi tool một dòng) → phải gộp theo phiên, không
  đếm dòng = số câu hỏi.
- Log **không có tên người dùng**, chỉ có mã phiên → phải nối qua bảng phiên để quy về người dùng.
- Giá Sonnet đang là **giá giới thiệu, tăng ~50% sau 31/08** → bản ước tính go-live phải dùng giá sau
  khuyến mãi, nếu không sẽ báo thiếu.

---

## Hạng mục 4 — Soi secret + dọn máy 24

~30 file trên máy chủ chưa vào git, gồm script tạo/kiểm tài khoản (`bulk_create_accounts.py`,
`check_accounts.py`, `create_dnh_otc.py`) — **rủi ro mật khẩu hardcode**. Quét mẫu secret trước, rồi
phân loại: có secret → xoá hoặc chuyển sang đọc từ `.env`; sạch + hữu ích → đưa vào git; scratch → bỏ.

Kèm theo: xoá 2 thư mục backup cũ (`_093544`, `_095101`) và `telegram_bot.py` còn sót dù đã gỡ Telegram.

---

## ✅ Hạng mục 5 — Truy 2 chênh lệch còn treo — **ĐÃ ĐÓNG CẢ HAI**

- ✅ **1,75 tỷ** *(đóng 27/07)*: **không phải lỗi**. Đó là tổng **5 dòng chỉ tiêu cá nhân của chính
  QLV** (QLV vừa quản đội vừa tự ôm một địa bàn) = **1.744.361.395đ**, hoàn toàn hợp lệ — hệ quả tất
  yếu của việc so tầng lá với tầng rollup, **không phải** chỉ tiêu cấp vùng chồng lên chỉ tiêu cá
  nhân. Kiểm chứng số học: `tungtx` 3.016.493.346 = 2.756.994.289 (10 TDV) + 259.499.057 (tự thân).
  Việc chuyển sang tầng rollup cũng **bác luôn nghi vấn A4** ở mức số học: tổng rollup khớp **tuyệt
  đối** `DIM_TargetVungMien` — nếu có cộng chồng thì tổng phải vượt.

- ✅ **1,13 tỷ** *(đóng 28/07)*: **là bug thật, đã sửa**. `get_employee_daily_kpi` lấy chỉ tiêu bằng
  `MAX(month_sale_target) WHERE save_date <= <hết tháng>` — **không có cận dưới** → nhặt chỉ tiêu
  cao nhất từng có thay vì chỉ tiêu tháng đang hỏi. Xác nhận trên Bravo: `tungtx` snapshot
  `2026-04-30` = 4.149.931.306đ (đúng con số sai), `2026-07-27` = 3.016.493.346đ (đúng số thật).
  Bản vá R-G trước đây chỉ **che triệu chứng** (chặn mã cấp quản lý) — bug vẫn sống với **mọi mã
  TDV**, đúng đối tượng của câu demo Q2. Đã ghim vào snapshot trong đúng tháng được hỏi.

---

## Rủi ro đang theo dõi (phát hiện 28/07, chưa xử lý — có chủ ý)

- 🔴 **Cloudflare Quick Tunnel có thể làm chatbot chết giữa demo.**
  `backend/server_deploy/cloudflared_supervisor.ps1` dùng quick tunnel → URL `*.trycloudflare.com`
  **đổi mỗi lần khởi động lại**, và dòng 2 ghi rõ phần tự động cập nhật Vercel *"tạm thời BỎ QUA
  theo yêu cầu"*. Mỗi lần backend/tunnel restart phải **sửa tay** `BACKEND_API_URL` trên Vercel rồi
  redeploy — đã xảy ra **4 lần** chiều 27/07. Nếu trúng sáng 09/08, chatbot chết tới khi có người
  vào Vercel sửa. → **Cần báo anh Triệu** (người quản Vercel/máy chủ). Cách khắc phục triệt để: nối
  lại phần tự cập nhật qua Vercel API, hoặc chuyển sang named tunnel có hostname cố định.

- 🟠 **Bug tiềm ẩn chưa phát tác** — `src/alerts.py` (`get_bravo_kpi_tdv_snapshot`, CTE `tdv_target`)
  dùng `SELECT DISTINCT` trên **bộ 4 cột** thay vì gộp theo `EmployeeCode`. Nếu một nhân viên có 2
  giá trị `AreaCode`/`ManagerCode` khác nhau trong cùng snapshot → CTE trả 2 dòng cho cùng người →
  `sum(month_sale_target)` bên `etl.py` **cộng đôi chỉ tiêu** người đó, âm thầm. Hiện tổng 3 miền
  vẫn khớp 0 đồng nên **chưa xảy ra**; chỉ cần Bravo đổi `AreaCode`/`ManagerCode` giữa tháng là
  phồng. Sửa: `GROUP BY [EmployeeCode]` + `MAX(...)` cho 3 cột còn lại.

- 🟡 **Tồn kho Miền Trung có 132 mặt hàng nhưng giá trị = 0đ** (phát hiện khi dựng đáp án R4 ngày
  28/07 — lần đầu tồn kho được đối chiếu theo vùng). MB 2,80 tỷ và MN 2,54 tỷ đều có giá trị bình
  thường, riêng MT bằng 0 dù có 9.014.691 đơn vị số lượng. Cần xác định là thiếu giá vốn cho kho MT
  hay lỗi dữ liệu gốc — **nếu khách hỏi tồn kho MT tại demo thì đây là câu trả lời khó**.

---

## Verification

**R-B — ba tầng, làm đủ cả ba:**

1. **Cùng tiến trình** (mạnh nhất): gọi SP tươi rồi truy vấn ngay bảng local vừa đồng bộ — số dòng
   **bằng nhau tuyệt đối**, tổng dư nợ/quá hạn **lệch ≤ 1 đồng**, top 50 khách quá hạn **lệch 0 đồng**.
   Lệch hơn = lỗi map cột, phải sửa trước khi đi tiếp.
2. **Chéo với báo cáo** (bằng chứng cho khách): chạy `scripts/demo1_ground_truth.py` bên `D:\DNH`
   trong vòng 15 phút sau khi đồng bộ. Ngưỡng: dư nợ/quá hạn lệch ≤ **0,05%**, tỷ lệ quá hạn lệch
   ≤ **0,1 điểm %**. Tỷ lệ OTC/ETC phải ra **≈39,4% / 52,3%** — nếu ra 92,9%/81,1% là vẫn đang đọc
   nguồn cũ.
3. **Ca cụ thể**: FPT Long Châu phải ra ≈0,61 tỷ (trước là 9,17 tỷ); DTH00237 (BV Đa khoa Đồng Tháp)
   phải ra **số cụ thể** thay vì "chưa có dữ liệu"; khách đang dư có không được xuất hiện như con nợ.

**Đầu-cuối qua chatbot thật** (không chỉ qua python), 3 loại tài khoản, phiên mới:
- Hỏi công nợ 1 khách → có số + mốc thời gian, **không** còn cảnh báo "bảng nhập tay có thể sai".
- Hỏi tổng công nợ → khớp tầng 2; kiểm `audit_log.jsonl` xác nhận đọc kho local, không phải Supabase.
- Ép AI đọc nguồn cũ ("tra bảng receivable_detail") → **phải bị chặn**.

**Độ bền**: tắt VPN rồi chạy đồng bộ → phải **giữ nguyên** snapshot cũ, không ghi đè bằng rỗng.
Xoá sạch bảng thủ công → chatbot phải nói "chưa tra cứu được", tuyệt đối không nói "khách không có nợ".

**Không hồi quy**: `pytest tests/ -q` bên `D:\DNH` (17 test) + smoke test ngưỡng theo vai trò vẫn pass.

---

## Rủi ro tuần

| Rủi ro | Xử lý |
|---|---|
| **Chatbot không có quyền chạy SP** → chặn toàn bộ hạng mục 1 | Spike thứ Hai phát hiện sớm; xin DNH cấp quyền ngay đầu tuần; phương án lùi là đẩy dữ liệu qua job bên `D:\DNH` |
| SP chạy lâu hơn timeout 90s → kill cả tiến trình sync, hỏng luôn sync hóa đơn | Đo thời gian ở spike; tách lịch riêng nếu cần |
| Deploy lên máy chủ: thêm bảng mới **không tự có** khi pull code | Bắt buộc chạy khởi tạo schema + hàm đồng bộ + restart backend; kiểm `git status` trước khi pull vì máy chủ từng có code chưa commit |
| Đổi mô tả schema/tool làm **mất bộ nhớ đệm prompt 1 giờ** → vài câu đầu đắt hơn | Bình thường, không phải lỗi — chỉ cần biết trước khi nhìn số chi phí |
| Khối lượng tuần lớn (5 hạng mục) | Thứ tự đã xếp theo mức chặn: R-B trước, việc dọn dẹp để cuối tuần, cắt được nếu thiếu thời gian |
