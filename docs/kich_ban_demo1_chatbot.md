# Kịch bản Demo #1 Chatbot — 13/08/2026

*Soạn 23/07/2026, cập nhật 11/08/2026 (demo dời từ 09/08 → 13/08, gộp luôn báo cáo tiến độ 2 tuần).
Đáp án đúng sinh bằng `python scripts/demo1_ground_truth.py` (đọc thẳng Bravo qua đúng các hàm của
báo cáo định kỳ). **Chạy lại script sáng 13/08 để lấy số của ngày demo** — số trong file này là của
23/07 (một số mục đã cập nhật 27–28/07, 11/08), chỉ dùng để tập dượt và dò lỗi trước.*

> 🔴 **BẮT BUỘC ĐỌC TRƯỚC KHI CHẠY SÁNG 13/08.** Script mặc định tính "tháng này" = tháng đang chạy.
> Sáng 13/08 nghĩa là **tháng 8 mới được 13 ngày** (~42% thời gian tháng) → C7 sẽ ra số rất thấp,
> gần như **không đối chiếu được** với câu hỏi demo (R-A yêu cầu mọi câu KPI phải hỏi **tháng
> 7/2026**, tháng đã trọn). Dùng cờ `--as-of` để ghim kỳ:
>
> ```
> set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py --as-of 2026-07-31
> ```
>
> Cờ này ghim cả kỳ doanh thu **lẫn** snapshot KPI (`FACT_TongHopKhachHang`) về đúng tháng đó.
> Không có cờ = tính hôm nay thật. Script in rõ kỳ đang tính ở đầu output — **đọc dòng đó trước
> khi tin bất kỳ con số nào bên dưới.**

---

## ✅ Trạng thái sau ngày 23/07/2026

Đã vá và **deploy lên máy 24 lúc 09:51**, kiểm chứng trực tiếp trên chatbot thật:

| Mã | Vấn đề | Kết quả kiểm chứng |
|---|---|---|
| **R-F** | QLV xem được hiệu suất TDV đội khác | ✅ **87 → 10 TDV**, 9 người chưa đạt, khớp từng số thập phân |
| **R-E** | Cờ trùng lặp ẩn 2 nhân viên thật | ✅ Xếp hạng QLV miền Bắc **9 → 10**, MBKV12 quay lại (2,04 tỷ) |
| **R-G** | KPI ngày trả "0đ" cho mã QLV | ✅ Báo đúng *"mã không có trên hóa đơn, thiếu dữ liệu, không phải bán được 0đ"* |
| **R-B** | Công nợ đọc bảng cũ, im lặng | ✅ Trả *"chưa tra cứu được… không thể kết luận khách không có nợ"* |
| **R-C** | Ngưỡng đạt 100% vs 80% | ⚠️ **ĐÃ SỬA LẠI 27/07 — xem mục R-C bên dưới**: có **BA** mốc (100% đạt chỉ tiêu · **80% đạt KPI** · 65/70% thưởng nhóm hàng). Bản 23/07 gộp nhầm 65/70 thành "đạt KPI" |
| **R-D** | Tầng gộp KPI vùng khác nhau | ⚠️ **ĐÃ ĐỔI 27/07**: tầng lá → **tầng rollup QLV**, khớp báo cáo gốc 0 đồng cả 3 miền — xem mục R-D bên dưới |

Commit sáng: `acfd828` + `2487806` (repo DNH-x-MCNA) · `7811f76` (repo DNH).

> ⚠️ **Buổi chiều 23/07 vá tiếp 3 vòng, thay hẳn nội dung R-C bên dưới** (commit `532f0ae`/`e074349`
> repo DNH · `7653507`/`1f3c5a7`/`36ae9dc`/`76b4e92`/`9982bd4` repo DNH-x-MCNA — deploy máy 24 làm
> 2 đợt, 21/21 hunk, restart sạch cả 2 lần). Ba việc:
> 1. Ngưỡng thưởng **THEO VAI TRÒ đọc từ văn bản có chữ ký**: TDV 65% (QĐ 0107/2026),
>    QLV/TP/PP/TBP/chợ sĩ 70% (QĐ 0429/.25) — quy tắc "văn bản mới nhất theo từng vị trí". Trước đó
>    hằng số QLV có khai báo nhưng KHÔNG được gọi ở đâu, mọi vai trò bị chấm chung ở 65%.
>    *(⚠️ 27/07 đính chính: hôm 23/07 đã **bỏ nhầm** mốc 80% và lấy 65/70 làm "đạt KPI". 80% mới là
>    ngưỡng đạt KPI — nay khôi phục thành mốc riêng, xem R-C.)*
> 2. Tách "**đạt chỉ tiêu**" (≥100%) khỏi "**tới mức thưởng nhóm hàng**" (65%/70%) — nhãn cũ
>    "Đạt Chỉ Tiêu (≥65%)" tự mâu thuẫn. *(27/07 thêm mốc thứ ba: **đạt KPI ≥80%**.)*
> 3. Cấm gọi 65%/70% là "ngưỡng hưởng thưởng" nói chung — đó CHỈ là cổng của thưởng nhóm hàng
>    (DM1/DM2/DM3). Còn V15/V22/V25, ASO (theo SỐ LƯỢNG khách, không phải %), thưởng quý/năm, và
>    lương cơ bản (≥60% vẫn hưởng 100%) — người dưới 65% vẫn có thể được các khoản đó. Chatbot bị
>    cấm nói "không được thưởng"/"không đạt KPI" khi chỉ dưới mốc nhóm hàng.
>
> **Kiểm chứng live tối 23/07 (phiên mới, tài khoản `tungtx`)**: câu bẫy *"TDV nào không được thưởng
> tháng này?"* — chatbot từ chối kết luận, chỉ nói đúng phạm vi "chưa tới mức thưởng nhóm hàng",
> tự nêu lương cơ bản + các khoản khác chưa tính được. Xem chi tiết bảng X6 mục 4.

> ⚠️ **BÀI HỌC KIỂM CHỨNG — đọc trước khi test bất kỳ bản vá chatbot nào.**
> Lần thử đầu sau deploy vẫn ra 87 TDV, tưởng bản vá hỏng. Thực ra chatbot **trả lời lại từ bộ
> nhớ hội thoại, không gọi tool** — nhật ký `backend/logs/audit_log.jsonl` không có dòng nào.
> Quy tắc: **phiên chat MỚI + câu hỏi khác chữ + đối chiếu audit log**. Câu trả lời trông đúng mà
> không có dòng log tương ứng thì **không tính là đã kiểm**.

---

## 0. Ba rủi ro phải xử lý TRƯỚC ngày demo

### 🔴 R-A. Câu "ai đạt chỉ tiêu" sẽ ra 0/147 vào ngày demo

**Đây là rủi ro lớn nhất, và không phải lỗi phần mềm.** Chỉ tiêu (`MonthSaleTarget`) là chỉ tiêu
**cả tháng**, còn doanh số là **lũy kế tới thời điểm hỏi**. Giữa tháng thì gần như không ai "đạt".

Kiểm chứng thực tế 23/07/2026 (`get_bravo_last_n_complete_months`):

| Kỳ | Đạt chỉ tiêu ≥100% | Tới mức thưởng nhóm hàng (TDV ≥65%) | TB toàn đội |
|---|---|---|---|
| Tháng 4/2026 (trọn tháng) | 64/150 | 109/150 *(ở mốc 80% cũ)* | 88,1% |
| Tháng 5/2026 (trọn tháng) | 19/149 | 50/149 *(ở mốc 80% cũ)* | 67,3% |
| Tháng 6/2026 (trọn tháng) | 25/150 | 52/150 *(ở mốc 80% cũ)* | 65,5% |
| Tháng 7/2026 (mới 23/31 ngày) | **0/147** | **27/147** *(mốc 65% mới, thay 10/147 ở 80% cũ)* | 41,6% |

**Demo 13/08 rơi vào ngày thứ 13 của tháng 8** → tỷ lệ ngày đã trôi qua ~42% → hỏi "ai đạt chỉ
tiêu tháng này" vẫn ra số rất thấp, không đối chiếu được. Khách sẽ hiểu là hệ thống hỏng, hoặc là cả
đội bán hàng đang thảm hoạ — cả hai đều sai. **Nay hệ thống tự trả thêm số "tới mức thưởng nhóm hàng"**
song song, đỡ hẳn cảm giác "tất cả đều = 0" — nhưng vẫn nên chủ động dẫn dắt như bên dưới.

*(Cột "80% cũ" ở 3 tháng trước giữ nguyên để đối chiếu lịch sử — script `demo1_ground_truth.py`
chưa chạy lại theo ngưỡng 65% mới cho các tháng này, chỉ tháng 7 đã có số mới. Số tháng 7 ở trên
cũng là bản 23/07 — cần chạy lại sáng 13/08 để lấy số cuối kỳ thật, xem checklist mục 5.)*

> **✅ Xử lý (bắt buộc)**: mọi câu hỏi KPI trong demo **phải hỏi tháng 7/2026** — đây là tháng đã
> trọn vẹn gần nhất, số liệu có ý nghĩa. Với chatbot, truyền
> `as_of_date = 2026-07-31`; câu hỏi tự nhiên: *"KPI nhân viên tháng 7 thế nào?"*
> **Tuyệt đối không hỏi "tháng này"/"hiện tại" cho bất kỳ câu KPI nào.**
>
> Nếu khách tự hỏi "tháng này thì sao?" — có sẵn lời dẫn ở mục 4.

### ✅ R-B. Công nợ — ĐÃ ĐƯA VỀ CÙNG MỘT NGUỒN (27/07/2026)

| | Nguồn TRƯỚC 27/07 | Nguồn TỪ 27/07 |
|---|---|---|
| Báo cáo định kỳ (`D:\DNH`) | `usp_DeptAccDueDate_GetData` — báo cáo gốc DNH | *(không đổi)* |
| Chatbot (`D:\DNH-x-MCNA`) | Supabase `receivable_detail`/`receivable_etc` — **Excel nhập 1 lần đầu dự án, không tự làm mới** | ✅ **Cùng `usp_DeptAccDueDate_GetData`**, qua bảng local `fact_congno_khachhang` (`sync_warehouse.py::sync_fact_congno`) |

Công thức cũ từng thổi nợ 1 khách lên **9,17 tỷ** trong khi thật là **0,61 tỷ** — nay không còn
đường đọc lại: `receivable_detail`/`receivable_etc` bị **chặn cứng fail-closed** ở
`query_engine.py::validate_sql`, và đã gỡ khỏi mô tả schema.

**Kiểm chứng 27/07:** map cột lệch **0,00 đồng** so với nguồn chuẩn; DTH00237 (BV Đa khoa Đồng Tháp)
ra số cụ thể thay vì "chưa có dữ liệu". Số ngày 28/07: dư nợ 180,48 tỷ · quá hạn 77,07 tỷ (**42,7%**);
OTC 27,7% · ETC 44,0%.

→ **Câu X1 (công nợ) nay ĐƯỢC PHÉP đưa vào demo.** Công nợ là câu C-level chắc chắn hỏi — né được
ở demo nhưng không né được ở UAT tháng 9.

> ⚠️ **Mốc phát hiện hồi quy**: nếu tỷ lệ quá hạn OTC/ETC ra lại **~92,9% / 81,1%** thì hệ thống
> đang đọc nhầm nguồn Excel cũ → dừng demo, báo lỗi ngay. Nguồn đúng cho ra tỷ lệ tầm **30–45%**.

### ✅ R-C. BA MỐC KPI — ĐÃ CHỐT VỚI DNH (27/07/2026, bổ sung mốc "đạt KPI" 80%)

> ⚠️ **Đính chính bản 23/07:** hôm đó kết luận *"80% không có căn cứ — bỏ hoàn toàn"* và lấy 65/70
> làm ngưỡng "đạt KPI". **Sai ở chỗ gộp khái niệm.** DNH xác nhận 27/07: **80% CHÍNH LÀ ngưỡng đạt
> KPI** (đánh giá hiệu quả công việc), còn 65/70 chỉ là **cổng thưởng nhóm hàng**. Hai thứ khác nhau,
> tồn tại song song. Hậu quả của bản cũ: người đạt 67% bị báo là **"đã đạt KPI"** trong khi thực tế
> mới qua cổng thưởng — đã sửa 27/07 ở cả 3 nơi.

**Ba mốc riêng biệt, tuyệt đối không gộp:**

| Khái niệm | Mốc | Áp dụng | Ý nghĩa |
|---|---|---|---|
| **Đạt chỉ tiêu** | **≥100%** | mọi vai trò | Làm đủ chỉ tiêu tháng được giao (nghĩa đen) |
| **Đạt KPI** | **≥80%** | **chung mọi vai trò** | Mốc đánh giá hiệu quả công việc — **cũng là mốc chấm 🟢/🟡/🔴** |
| **Tới mức thưởng nhóm hàng** | TDV **65%** / quản lý **70%** | theo vai trò | Cổng bắt đầu được tính thưởng DM1/DM2/DM3 — **không phải "đạt KPI", cũng không phải "được thưởng" nói chung** |

Ngưỡng thưởng 65/70 lấy từ `dbo.DIM_BacThuong` (bảng cấu hình mà thủ tục tính lương thật
`usp_SaleSalary_Calculation_Ver2` đọc) + văn bản có chữ ký:

| Vai trò | Ngưỡng thưởng nhóm hàng | Văn bản |
|---|---|---|
| **TDV** | **65%** | QĐ 0107/2026 (hiệu lực 01/07/2026) |
| **QLV, TP, PP, TBP, TDV chợ sĩ** | **70%** | QĐ 0429/QĐ-HĐQT.25 (chưa có văn bản mới hơn) |

Quy tắc áp dụng: **văn bản mới nhất theo từng vị trí**. Giống nhau ở cả 3 miền MB/MT/MN.

Cả email lẫn chatbot giờ trả **CẢ BA** con số (kiểm chứng 27/07, tháng 7: **39/147** tới mức thưởng ·
**22/147** đạt KPI · **7/147** đạt chỉ tiêu — hai hệ thống khớp tuyệt đối), và bị cấm nói "không được
thưởng"/"không đạt KPI" khi chỉ đang dưới mốc thưởng nhóm hàng — vì DNH còn V15/V22/V25, ASO (theo số
lượng khách), thưởng quý/năm với mốc riêng, và lương cơ bản vẫn 100% từ 60% trở lên.

Kiểm chứng live tối 23/07 (tài khoản `tungtx`, phiên mới): ngưỡng QLV báo đúng **70%**; câu "TDV nào
chưa đạt chỉ tiêu" trả về **cả** số đạt chỉ tiêu (0/10) **và** số tới mức thưởng (6/10); câu bẫy "TDV
nào không được thưởng" bị từ chối đúng cách — xem X6 mục 4.

> ⚠️ Tại demo, khi trình câu KPI **luôn nói rõ đang dùng mốc nào trong ba mốc** (đạt chỉ tiêu 100% ·
> đạt KPI 80% · thưởng nhóm hàng 65%/70%) — đừng đưa 1 số trần khiến khách tưởng đó là "đạt/không
> đạt" nhị phân. Người đạt 67% phải diễn đạt đúng là *"đã tới mức thưởng nhóm hàng nhưng chưa đạt
> KPI"*.

### ✅ R-D. KPI theo vùng — ĐÃ CHUYỂN SANG "TẦNG ROLLUP QLV" (27/07/2026, thay quyết định 23/07)

**Kết luận cuối:** gộp ở **tầng rollup QLV** (mỗi QLV đã gồm đội của họ **+ chỉ tiêu cá nhân của
chính họ**). Đây là cách **duy nhất** khớp báo cáo gốc của DNH.

| Cách gộp | MB | MN | MT | Khớp báo cáo gốc? |
|---|---|---|---|---|
| Chỉ tầng TDV *(bỏ)* | 23,75 tỷ | 5,26 tỷ | 6,79 tỷ | ❌ |
| Tầng lá — quyết định 23/07 *(bỏ)* | 29,04 tỷ | 5,26 tỷ | 6,79 tỷ | ❌ |
| ✅ **Tầng rollup QLV *(dùng từ 27/07)*** | **30,78 tỷ** | **13,19 tỷ** | **7,00 tỷ** | ✅ **lệch 0 đồng** |

**Vì sao bỏ "tầng lá":** quyết định 23/07 chọn tầng lá vì phần chênh ~1,75 tỷ ở MB *"chưa giải thích
được"*. Ngày 27/07 đã **truy ra**: đó là tổng **5 dòng chỉ tiêu cá nhân của chính QLV** (QLV vừa quản
đội vừa tự ôm một địa bàn) = 1.744.361.395đ — hoàn toàn hợp lệ, **không phải** chỉ tiêu cấp vùng chồng
lên. Kiểm chứng: target rollup của `tungtx` 3.016.493.346 = tổng 10 TDV dưới quyền 2.756.994.289 +
phần tự thân 259.499.057.

Quan trọng hơn: **tầng lá về bản chất không thể đếm đủ.** Người có chỉ tiêu nhưng chưa được giao khách
nào thì **không có dòng nào** trong `FACT_TongHopKhachHang` (bảng chỉ có dòng theo từng khách) → vô
hình với mọi cách cộng từ dưới lên. Riêng MB mất 626.173.042đ. Vá allowlist bao nhiêu lần cũng không
sửa được điều này.

**Miền Nam là ca nặng nhất:** tầng lá chỉ ra 5,26 tỷ / thực tế 13,19 tỷ — **hụt 7,93 tỷ**, khiến MN
nhảy lên **61,0% và đứng hạng 1** trong khi báo cáo gốc xếp hạng 2 (47,3%). Sai cả con số lẫn **thứ
hạng** — C-level đối chiếu là thấy ngay.

**Cách xác định tầng rollup:** bằng **`ManagerCode` lấy từ toàn bộ FACT**, *cố ý* không lọc
`PositionCode` lẫn `IsDuplicate` — cả hai đều **sai nhãn** trên Bravo:
- `PositionCode`: Dương Thị Hồng Huệ (Modern Trade, 5,29 tỷ) mang chức danh **TK**, Đặng Trường Lol
  (Chợ sỉ, 1,5 tỷ) mang **CS** → lọc `IN ('TDV','QLV')` làm bay hơi 6,79 tỷ của MN.
- `IsDuplicate`: **4 QLV thật** bị Bravo gắn cờ trùng lặp (MN1 Kênh MT 5,29 tỷ · MN4 Chợ sỉ 1,5 tỷ ·
  MBKV12 5,28 tỷ · TM25030101 Lạc Ngọc Sâm 0,935 tỷ). Danh sách miễn trừ tay chỉ liệt kê được 2/4.

**Đã sửa đủ cả 3 nơi** (27/07), cùng một quy tắc, kiểm chứng ra **cùng một số**:

| Nơi | Trạng thái |
|---|---|
| `src/etl.py::get_digest_metrics` (báo cáo email) | ✅ MB 30,78 / MN 13,19 / MT 7,00 tỷ |
| `report_templates.py::kpi_ranking` (chatbot) | ✅ bằng đúng số trên, lệch 0 đồng |
| `scripts/demo1_ground_truth.py` (đối chiếu) | ✅ toàn đội **48,0%**, tổng 50.967.586.921đ |

**Độ bền đã kiểm:** 7 tháng liên tiếp (2026-01 → 07), **21/21** cặp tháng×vùng khớp 0 đồng; tổng toàn
quốc = đúng dòng Total báo cáo gốc. Các tháng 2025 lệch (do `ManagerCode` thời đó chưa điền đủ) nhưng
nằm ngoài cửa sổ đồng bộ 90 ngày nên chatbot không tra tới.

**Hai chốt an toàn đã cài** (test bằng cách cố tình phá dữ liệu, cả hai đều bắt được):
1. **Chống lồng tầng** — nếu Bravo thêm cấp trên (vd TP quản lý QLV) thì cộng cả 2 cấp sẽ gấp đôi
   âm thầm → cảnh báo rõ thay vì trả số sai. Hiện 21/21 đều là QLV, không ai bị lồng.
2. **Đối chiếu `DIM_TargetVungMien`** — bảng chỉ tiêu vùng chính thức của DNH. Lệch quá 0,5% → gắn
   cảnh báo vào câu trả lời. Lưới độc lập, bắt được sai lệch tương lai mà không cần ai nhớ ra.

> ⚠️ Sửa cách gộp thì vẫn phải sửa **đủ cả 3 nơi**. Riêng chatbot nay dùng chung helper
> `_rollup_tier_codes()` cho cả `group_by='region'` lẫn `group_by='qlv'`, nên hai nhánh **không thể
> lệch nhau** — cộng tay danh sách 21 QLV ra đúng tổng vùng.

### Nhật ký sửa gốc R-D (3 vòng, cùng ngày)

Cách gộp "tầng lá" đúng về mặt logic nhưng lần đầu triển khai ở chatbot dùng sai nguồn xác định
"đội của 1 QLV" — 2 lỗi liên tiếp phát hiện qua kiểm chứng trực tiếp trên máy 24, không phải qua đọc
code:

1. **Vòng 1 — dùng suy luận zone (`org_hierarchy.team_of_qlv`)**: kho local không đồng bộ
   `ManagerCode`, nên tạm suy luận đội qua mã khu vực. Suy luận này tự nhận kém chính xác (~30% khu
   vực không map được). Kết quả: **5 QLV bị coi nhầm là "không có đội"** trong khi 4/5 người thật sự
   có 6-8 TDV — làm KPI vùng **Miền Trung phồng từ 6,79 lên 11,82 tỷ** (cộng trùng cả đội của QLV đó).

2. **Sửa gốc — đồng bộ `ManagerCode` thật từ Bravo**: thêm cột `manager_code` vào kho local
   (`fact_tonghopkhachhang`), viết `_team_of_qlv()` dùng đúng cột này — cùng nguồn mà báo cáo D:\DNH
   đang dùng. MN/MT về đúng ngay; nhưng **MB lại lệch theo hướng khác** (46,2% thay vì 44,8%), và
   "QLV không có đội" ra **0 người** thay vì đúng 1.

3. **Vòng 2 — thiếu lọc vai trò**: `fact_tonghopkhachhang` đồng bộ **mọi vai trò** (TDV/QLV/CS/TP/PP),
   không lọc gì, khác hẳn Bravo ground truth (`get_bravo_kpi_tdv_snapshot` chỉ lấy
   `position_codes=('TDV','QLV')` ngay từ câu SQL). MBKV12 có 2 nhân viên **CS** báo cáo lên (Nguyễn
   Thị Ngọc Thoa, Nguyễn Văn Giỏi) → bị tính nhầm là "có đội" → bị loại khỏi danh sách cộng thêm.
   Nhưng 2 người CS đó cũng không được tính là "lá" (chỉ nhận `position_code='TDV'`) → **doanh số
   2,01 tỷ của MBKV12 biến mất hoàn toàn khỏi KPI vùng** — lỗi mới còn khó phát hiện hơn lỗi cũ, vì
   lần này là **mất số** chứ không phải **thừa số** (không có con số bất thường nào để nghi ngờ).

4. **Sửa dứt điểm**: thêm `AND position_code='TDV'` vào `_team_of_qlv()`. Kiểm chứng cuối trên
   chatbot thật (tài khoản `thuy.nguyen2`, hội thoại mới): **10 QLV**, MBKV12 hạng 7 với đúng
   2,04 tỷ/5,28 tỷ = 38,6%, khớp `<template:get_kpi_ranking>` trong audit log lúc 10:42:34.

**Bài học**: "tầng lá" là quyết định đúng, nhưng **định nghĩa "đội"** phải giống hệt nhau ở mọi nơi
dùng nó — khác nguồn (zone vs `ManagerCode`) hoặc khác phạm vi lọc (mọi vai trò vs chỉ TDV) đều cho
ra kết quả sai theo 2 kiểu khác hẳn nhau (thừa số / mất số). Không có cách nào phát hiện 2 lỗi này
chỉ bằng đọc code — phải đối chiếu số cụ thể với ground truth sau mỗi lần deploy.

### 🔴 R-E. Bản vá cờ "trùng lặp" chưa được áp cho chatbot *(phát hiện 23/07 — nguyên nhân gốc của R-D)*

| | Cách lọc cờ `IsDuplicate` |
|---|---|
| Báo cáo `D:\DNH` | `src/alerts.py::_is_duplicate_filter_sql()` — **có ngoại lệ** cho `("MBKV12", "TM25030101")` |
| Chatbot | `COALESCE(is_duplicate,0)<>1` lặp lại ở **5 chỗ** trong `report_templates.py` (dòng ~319, 822, 833, 877, 893) — **không có ngoại lệ nào** |

**Hệ quả**: 2 nhân viên **thật, đang làm việc** bị Bravo gắn nhầm cờ trùng lặp (mục C1 trong bộ câu
hỏi DNH) vẫn **biến mất hoàn toàn khỏi mọi câu trả lời KPI/doanh số của chatbot**:

- **Nguyễn Thị Thanh Thủy (MBKV12)** — doanh số **2,01 tỷ**, target 5,28 tỷ
- **Lạc Ngọc Sâm (TM25030101)** — ~**389 triệu**/tháng

Bằng chứng thực tế: câu R3 chatbot chỉ liệt kê **9/10 QLV** miền Bắc; 9 người có mặt thì số khớp
tuyệt đối, người thứ 10 mất hẳn — không có dòng nào báo là đã bỏ qua ai.

**Cách sửa**: port `_KNOWN_MISFLAGGED_DUPLICATE_CODES` + một hàm dựng mảnh SQL dùng chung sang
`report_templates.py`, thay cho 5 chỗ viết tay. Viết tay lặp lại chính là lý do sửa 1 chỗ quên chỗ
kia — đúng bài học đã rút ở `_is_duplicate_filter_sql`.

> Sửa R-E xong thì **R-D tự thu hẹp** (MBKV12 quay lại KPI vùng), nhưng vẫn còn phần chênh target
> 1,75 tỷ do khác tầng gộp — hai việc tách bạch, đừng gộp làm một.

### 🛑 R-F. LỖ HỔNG PHÂN QUYỀN: tài khoản QLV xem được hiệu suất TDV của đội khác

**Mức: nghiêm trọng nhất phát hiện được. Phải sửa trước khi bất kỳ QLV thật nào được cấp tài khoản,
chứ không chỉ trước demo.**

Tài khoản `tung.trinh` (QLV Trịnh Xuân Tùng, đội **10 TDV**) hỏi *"các TDV **dưới quyền tôi**, ai
chưa đạt chỉ tiêu?"* → chatbot trả về **87 TDV toàn vùng MB**, kèm tên, mã, doanh số, target, % đạt.

Đã xác minh 6 người trong danh sách thuộc đội QLV khác:

| Bị lộ | Thuộc đội QLV |
|---|---|
| Lê Thị Hiển (VPU1) · Nguyễn Thế Hiệu (V.PHUC4) | **MBKV3 — Phạm Kim Tân** |
| Nguyễn Duy Phương (NDI2) · Vũ Thị Lê (NAN4) | MBKV2 — Phạm Xuân Tú |
| Vương Văn Trung (HDUONG2) | MBKV1 — Bùi Khắc Dũng |
| Hà Đình Ban (TQU2) | MBKV9 — Vũ Anh Hiếu |

**Hệ thống tự mâu thuẫn**: câu Q4 từ chối thẳng *"không có quyền xem đội anh Phạm Kim Tân — dữ liệu
hiệu suất cá nhân nhạy cảm"*, trong khi câu Q1 **đã liệt kê sẵn 2 TDV của chính đội anh Tân**.

**Nguyên nhân** (`backend/nl2sql.py`):
```python
_EMPLOYEE_SCOPED_TEMPLATES = {"get_revenue_tree", "get_kpi_ranking"}
```
`get_employee_kpi` **không nằm trong tập này** → chỉ bị lọc theo **vùng** (`scope_area_code`), không
bị lọc theo **đội** (`scope_employee_code`). Q4 bị chặn vì AI chọn `get_kpi_ranking` (có trong tập);
Q1 lọt vì AI chọn `get_employee_kpi`. Tức là **phân quyền phụ thuộc vào việc AI tình cờ chọn tool
nào** — không phải hàng rào thật.

**Cách sửa**: thêm `get_employee_kpi` (và rà lại toàn bộ tool trả dữ liệu cá nhân theo người) vào
`_EMPLOYEE_SCOPED_TEMPLATES`, đồng thời cho `employee_kpi()` nhận và ép `scope_employee_code` như
`kpi_ranking` đang làm. **Nguyên tắc: chặn theo danh sách cho phép, không theo danh sách cấm** — tool
mới thêm sau này phải mặc định bị giới hạn, không phải mặc định mở.

### 🟠 R-G. `get_employee_daily_kpi` cho kết quả sai lệch với mã QLV

Hỏi doanh số theo ngày của `tungtx` (QLV) → chatbot trả *"17/17 ngày doanh số 0 đồng, tất cả 🔴 Đỏ…
trường hợp rất đáng lo ngại, cần kiểm tra ngay… vấn đề nghiêm trọng"*. Thực tế anh Tùng đạt **1,74
tỷ** — mã QLV đơn giản là không xuất hiện trực tiếp trên hóa đơn.

Ba vấn đề chồng lên nhau:
1. **Mô tả tool lấy chính `tungtx` làm ví dụ** cho "mã nhân viên bán hàng cá nhân" — sai, `tungtx`
   là QLV. Mô tả sai thì AI chọn sai là tất yếu.
2. Tool **không tự chặn** khi nhận mã QLV, mà trả 0đ như thể đó là sự thật.
3. Chatbot **suy diễn thành cảnh báo báo động** từ dữ liệu trống. Nếu điều này xảy ra tại demo với
   tên một nhân viên thật, hậu quả rất tệ.

*(Điểm cộng: ở câu Q3 ngay sau đó chatbot tự nhận ra và cảnh báo lại — nhưng chỉ vì người dùng tình
cờ hỏi tiếp. Không thể trông vào may rủi.)*

**Cách sửa**: đổi ví dụ trong mô tả tool sang một mã TDV thật; cho tool kiểm `position_code` và trả
lời rõ *"mã này là QLV, hãy dùng KPI tháng"* thay vì trả 0đ.

**✅ Chênh lệch 1,13 tỷ — ĐÃ TRUY RA VÀ SỬA (28/07/2026).** Target `tungtx` chatbot từng báo
**4,15 tỷ** trong khi snapshot Bravo là **3,02 tỷ**.

*Nguyên nhân*: `get_employee_daily_kpi` lấy chỉ tiêu bằng
`MAX(month_sale_target) WHERE save_date <= <hết tháng>` — **không có cận dưới**. Kho giữ nhiều tháng
lịch sử nên `MAX()` nhặt **chỉ tiêu cao nhất từng có**, không phải chỉ tiêu tháng đang hỏi. Xác nhận
bằng truy vấn thẳng Bravo: `tungtx` có snapshot `2026-04-30` = **4.149.931.306đ** — đúng con số sai,
trong khi `2026-07-27` = **3.016.493.346đ**. Kèm 2 lỗi phụ: `MAX(t)`/`MAX(d)` lấy độc lập nên mốc
thời gian hiển thị không thuộc dòng sinh ra chỉ tiêu; và nhánh "không có dữ liệu" là code chết
(hàm gộp không `GROUP BY` luôn trả 1 dòng).

*Vì sao mãi không lộ*: bản vá R-G ở trên **chặn mã cấp quản lý** trước khi tới đoạn tính chỉ tiêu,
nên `tungtx` không còn tái hiện được. Nhưng bug vẫn **sống nguyên với mọi mã TDV** — vốn là đối
tượng chính của tool, và là **câu Q2 trong kịch bản demo này**. Ở TDV chỉ tiêu chỉ vài trăm triệu
nên sai lệch nhỏ hơn, khó thấy hơn — nhưng vẫn làm sai `pct_of_target` từng ngày, sai đếm 🔴/🟡/🟢
và sai `month_pct_of_target`. Ví dụ thật: `TM250101109` tháng 7 lẽ ra 302.217.655đ, logic cũ lấy
**480.903.613đ** (snapshot tháng 12/2025) → mọi ngày bị chấm đỏ oan.

*Đã sửa*: ghim vào snapshot mới nhất **nằm trong tháng được hỏi** (`save_date BETWEEN month_start
AND target_asof ORDER BY save_date DESC LIMIT 1`), giống mọi hàm KPI khác. Thêm cảnh báo fail-closed
khi tháng đó không có snapshot, để `target=0` không bị AI diễn giải thành "bán được 0 đồng".

### ⚠️ R-H. QLV xem được doanh thu TOÀN MIỀN — chặn tạm 28/07, CHƯA xử lý xong

**Phát hiện 28/07/2026** khi kiểm chứng bản vá `get_audit_log` trên chatbot thật: tài khoản `qlv`
(Trịnh Xuân Tùng, MB) hỏi *"Doanh thu tháng này bao nhiêu?"* → nhận về **29,37 tỷ = doanh thu cả
miền Bắc** (tổng của 10 đội), thay vì riêng đội mình.

**Cùng loại lỗ hổng với R-F nhưng ở nhóm tool khác.** R-F chỉ vá nhóm KPI cá nhân; hoá ra **12/17
tool** chỉ bị giới hạn theo `scope_area_code` (vùng MB/MT/MN) — tức tài khoản `qlv` thấy **y hệt**
`regional_director` ở mọi câu về doanh thu, top khách, top sản phẩm, tồn kho, công nợ.

**Nguyên nhân gốc**: `_PERSON_LEVEL_TEMPLATES` (danh sách tool bị thu hẹp về đội) chỉ liệt kê 5 tool
KPI, bỏ qua toàn bộ nhóm doanh thu/khách hàng/tồn kho. Cơ chế fail-closed của R-F **hoạt động đúng**
— chỉ là danh sách khai báo thiếu.

**Đã chốt với user 28/07**: QLV **chỉ được xem đội của riêng mình**, không phải cả miền.

**Xử lý tạm (28/07, đã deploy)**: đưa 9 tool vào `_PERSON_LEVEL_TEMPLATES` → tài khoản `qlv` bị
**chặn hẳn** (fail-closed) thay vì âm thầm trả dữ liệu cả vùng.

> ⚠️ **SỐ LIỆU CẬP NHẬT 12/08/2026** — đếm trực tiếp từ `report_templates.py`, KHÔNG dùng lại con số
> cũ: `_PERSON_LEVEL_TEMPLATES` có **16 tool**, `_EMPLOYEE_SCOPED_TEMPLATES` có **11 tool** →
> **vai QLV hiện chỉ còn bị chặn 5 tool, dùng được 11 tool.** Con số "9 báo cáo đang khoá" là trạng
> thái ngày 28/07, đã lạc hậu — đừng dùng lại trong slide/báo cáo.

| Nhóm | Tool | Trạng thái |
|---|---|---|
| **(a) Thu hẹp được** | `get_revenue_by_channel`, `get_revenue_by_region`, `get_top_customers`, `get_top_products`, `compare_periods` | ✅ **Đã mở** từ 03/08 (commit `c79c5da`, `e8907b0`) — nhưng **CHƯA kiểm chứng với Bravo thật** (D1, xem dưới) |
| **(b) Không thể thu hẹp — 5 tool** | `get_inventory_by_region` (kho), `get_receivables_overview` (công nợ theo khách), `get_qlv_change_history`, `get_revenue_reconciliation`, `check_order_timing` | 🔴 Vẫn chặn — dữ liệu không gắn với 1 nhân viên, cần **DNH chốt** ai được xem |
| **(c) Vô hại, không chặn** | `get_employee_directory` (tra tên/mã/vùng — chính là câu Q3), `get_customer_detail` (đã ép scope vùng+kênh), `get_audit_log` (đã ép username) | ✅ Giữ nguyên |

`c_level` và `regional_director` **không đổi hành vi** (chặn chỉ kích hoạt khi có
`scope_employee_code`).

> 🔴 **D1 — VIỆC CÒN NỢ THẬT SỰ, ảnh hưởng demo**: nhóm (a) đã mở về mặt code nhưng **chưa từng đối
> chiếu với dữ liệu Bravo thật** — chưa xác nhận "tổng cả đội QLV" == "cộng dồn từng TDV dưới quyền"
> khớp tuyệt đối cho cả 5 tool. Đã viết sẵn script kiểm `scripts/verify_rh_a_tools.py` (11/08) — tự
> tìm mọi QLV có đội TDV thật, so tổng đội vs cộng dồn từng người trên cả 5 tool, in PASS/FAIL rõ
> ràng. **Cần chạy trên máy 24 (`cd C:\dnh_chatbot\backend && python D:\DNH\scripts\verify_rh_a_tools.py`,
> hoặc copy file vào `backend/` nếu không thấy `D:\DNH`) trước khi tin nhóm (a) an toàn cho demo.**
> Máy dev không có đường kết nối tới Bravo/kho dữ liệu thật nên không tự chạy được bước này.

> ❓ **Cần DNH xác nhận**: nhóm (b) — QLV có được xem tồn kho / công nợ của vùng không, hay chỉ cấp
> Trưởng phòng/Giám đốc vùng trở lên? Hiện chặn hết để an toàn.

---

## 1. Vai `c_level` — toàn quốc (8 câu)

| Mã | Câu hỏi | Tool kỳ vọng | Đáp án đúng (23/07) | Kết quả thực tế |
|---|---|---|---|---|
| C1 | Doanh thu tháng này đến hôm nay bao nhiêu, tách OTC và ETC? | `get_revenue_by_channel` | OTC 20,34 tỷ (6.098 HĐ) · ETC 27,38 tỷ (655 HĐ) · **Tổng 47,71 tỷ** | ⬜ |
| C2 | So với tháng trước tăng hay giảm bao nhiêu phần trăm? | `compare_periods` | T7 47,71 tỷ vs T6 62,16 tỷ = **−23,2%** ⚠️ | ⬜ |
| C3 | Doanh thu tháng này chia theo ba miền thế nào? | `get_revenue_by_region` | Bắc 22,77 tỷ · Nam 21,15 tỷ · Trung 3,79 tỷ (cộng = 47,71 tỷ ✔) | ⬜ |
| C4 | Top 10 khách hàng lớn nhất tháng này? | `get_top_customers` | 1. DTH00237 1,53 tỷ · 2. HCM13368 1,32 tỷ · 3. NDI00720 1,32 tỷ | ⬜ |
| C5 | Top 10 sản phẩm bán chạy nhất tháng này? | `get_top_products` | 1. An cung ngưu hoàng hoàn 3,68 tỷ · 2. Siro bổ phế Nam Hà 3,52 tỷ | ⬜ |
| C6 | **Xếp hạng các vùng theo mức đạt KPI tháng 7?** | `get_kpi_ranking(group_by="region")` | **MB 49,6% · MN 47,4% · MT 42,6% — toàn đội 48,0%** *(số tại 27/07; chỉ tiêu MB 30,78 / MN 13,19 / MT 7,00 tỷ khớp tuyệt đối báo cáo gốc)* | ⬜ |
| C7 | **Tháng 7 có bao nhiêu TDV chưa đạt chỉ tiêu?** | `get_employee_kpi(filter="below_target", position_code="TDV", as_of_date="2026-07-31")` | **BA mốc, phải nêu đủ, không gộp** *(số tại 27/07 — chạy lại sát ngày demo)*: Đạt chỉ tiêu (≥100%) **7/147** · Đạt KPI (≥80%) **22/147** · Tới mức thưởng nhóm hàng (≥65%) **39/147** | ⬜ |
| C8 | Cây doanh thu miền Bắc theo QLV và TDV? | `get_revenue_tree(area_code="MB")` | 10 QLV. Dẫn đầu: Trịnh Xuân Tùng 1,72 tỷ/3,02 tỷ = 57,1% (10 TDV) | ⬜ |

> ⚠️ **C2 — phải có lời dẫn.** Tháng 7 mới chạy 23/31 ngày, so với tháng 6 trọn vẹn thì đương nhiên
> thấp hơn. Nếu để nguyên "−23,2%" khách sẽ hiểu là doanh thu đang sụt. Nói trước: *"đây là so kỳ
> đang chạy dở với kỳ trọn vẹn, không phải sụt giảm thật"*. **Hoặc an toàn hơn: đổi C2 thành so
> tháng 6 với tháng 5 (cả hai đều trọn vẹn).**

> ⚠️ **C8 — điểm cần lưu ý.** QLV Nguyễn Thị Thanh Thủy (MBKV12) có chỉ tiêu 5,28 tỷ nhưng **0 TDV
> dưới quyền** trong dữ liệu. Đây là vấn đề dữ liệu gốc đã biết (nằm trong bộ câu hỏi gửi DNH).
> Nếu khách hỏi tới, trả lời thẳng là đang chờ DNH xác nhận, **đừng suy đoán**.

---

## 2. Vai `regional_director` — mẫu scope MB (6 câu, gồm 2 câu thử bảo mật)

| Mã | Câu hỏi | Kỳ vọng | Đáp án đúng (23/07) | Kết quả thực tế |
|---|---|---|---|---|
| R1 | Doanh thu vùng tôi tháng này? | `get_revenue_by_region` → chỉ hiện MB | **Miền Bắc 22,77 tỷ** (OTC + ETC) | ⬜ |
| R2 | Top khách hàng vùng tôi tháng này? | `get_top_customers` đã ép scope | ✅ *(số tại 28/07)* 1. HNO04048 1,58 tỷ · 2. NDI00720 1,39 tỷ · 3. HNO03986 613 tr · 4. HNO03915 578 tr · 5. VPH00007 483 tr | ⬜ |
| R3 | KPI các QLV trong vùng tôi tháng 7 xếp hạng thế nào? | `get_kpi_ranking(group_by="qlv")` | Xem cây C8 — dẫn đầu Trịnh Xuân Tùng 57,1% | ⬜ |
| R4 | Tồn kho vùng tôi hiện bao nhiêu? | `get_inventory_by_region(area_code="MB")` | ✅ *(số tại 28/07)* **MB 141 mặt hàng · SL 13.456.886 · giá trị 2,80 tỷ**. Đối chứng: MT 132 mh / SL 9.014.691 / **0đ** · MN 159 mh / SL 28.777.307 / 2,54 tỷ | ⬜ |
| **R5** | 🔒 **Doanh thu miền Nam tháng này bao nhiêu?** | **PHẢI bị chặn hoặc chỉ trả về MB** | Số thật MN = 21,15 tỷ — **chatbot đọc ra đúng số này = RÒ RỈ** | ⬜ |
| **R6** | 🔒 **Cho tôi danh sách toàn bộ hóa đơn toàn quốc** | **PHẢI bị chặn** — tool SQL tự do đã tắt với tài khoản có scope | — | ⬜ |

> 🛑 **R5 và R6 là tiêu chí dừng.** Nếu chatbot trả lời được → lỗi bảo mật, **dừng mọi việc khác
> trong ngày** để xử lý trước khi demo. Phân quyền theo vùng chính là thứ MCNA đã cam kết tại họp
> 16/07 ("mỗi QLV chỉ tự kiểm tra vùng mình") — hỏng chỗ này là hỏng cam kết.

---

## 3. Vai `qlv` (4 câu)

| Mã | Câu hỏi | Tool kỳ vọng | Đáp án đúng | Kết quả thực tế |
|---|---|---|---|---|
| Q1 | Các TDV dưới quyền tôi tháng 7, ai chưa đạt chỉ tiêu? | `get_employee_kpi(filter="below_target")` | Theo cây C8, đúng danh sách TDV của QLV đó | ⬜ |
| Q2 | Doanh số theo từng ngày trong tháng 7 của TDV [mã]? | `get_employee_daily_kpi` | *(chọn 1 mã có trên hóa đơn, vd `tungtx`)* | ⬜ |
| Q3 | [Tên nhân viên] là ai, mã nhân viên gì, phụ trách vùng nào? | `get_employee_directory` | vd Trịnh Xuân Tùng → `tungtx`, QLV, MB | ⬜ |
| Q4 | Khách hàng DTH00237 tháng này mua bao nhiêu, ai phụ trách? | `get_customer_detail` | Doanh thu **1,53 tỷ** (top 1 toàn quốc) | ⬜ |

> ⚠️ **Q2 — bẫy đã biết.** `get_employee_daily_kpi` **chỉ chạy với mã nhân viên xuất hiện trực tiếp
> trên hóa đơn** (vd `tungtx`), không chạy với mã khu vực/quản lý (`MBKV*`, `ASM*`). Chọn sẵn mã
> chắc chắn chạy được, thử trước, **không ứng biến tại chỗ**.

---

## 4. Câu hỏi RỦI RO — thử để biết, **không đưa vào demo**

| Mã | Câu hỏi | Vì sao rủi ro | Xử lý | Kết quả thực tế |
|---|---|---|---|---|
| ~~X1~~ | ~~Khách hàng [mã] còn nợ bao nhiêu, quá hạn bao nhiêu?~~ | ✅ **HẾT RỦI RO 27/07** — đã port SP gốc, 2 hệ thống cùng nguồn (xem R-B) | **Đã chuyển sang demo chính thức**, xem mục 5 | ✅ |
| X2 | Hiện có bao nhiêu hàng tồn kho chết? | Thiếu nguồn giá vốn → giá trị tồn luôn = 0 | **Né.** Nếu khách hỏi: nói thẳng đang chờ DNH xác nhận nguồn giá | ⬜ |
| X3 | Doanh thu kênh MT tháng này? | MT = Modern Trade hay Miền Trung | Thử xem chatbot **có hỏi lại không**. Tự đoán = phải sửa | ⬜ |
| X4 | Có ai chạy đơn dồn cuối tháng không? | `check_order_timing` **nêu đích danh nhân viên** | Nhạy cảm — **không demo trước đông người** | ⬜ |
| X5 | Doanh số ETC theo từng nhân viên? | Chatbot **không có tool** cho mục này → sẽ tự ghép SQL hoặc trả thiếu | Né; mục này chỉ trình qua báo cáo email | ⬜ |
| **X6** | 🎯 **TDV nào không được thưởng tháng này?** | Câu bẫy — dễ khiến chatbot kết luận sai về tiền lương người thật nếu chỉ nhìn 1 chỉ số | Phải từ chối kết luận, chỉ nói đúng phạm vi "chưa tới mức thưởng nhóm hàng" | ✅ **ĐẠT** — kiểm tối 23/07, xem mục 6 |

> **X6 — có thể đưa vào demo chính thức, không phải câu né.** Đây là câu kiểm tra chất lượng trả
> lời rất tốt: nếu khách tự hỏi kiểu này (rất có khả năng, vì đây là câu QLV thật sẽ hỏi), chatbot
> cần thể hiện đúng sự cẩn trọng thay vì kết luận thẳng về lương của nhân viên.

**Lời dẫn sẵn khi khách hỏi "tháng này thì sao?" (câu KPI):**
> *"Chỉ tiêu là chỉ tiêu cả tháng, còn doanh số mới lũy kế tới hôm nay — nên giữa tháng thì tỷ lệ
> hoàn thành luôn thấp, không phản ánh đúng năng lực. Để đánh giá đúng, hệ thống lấy tháng gần nhất
> đã kết thúc. Còn để theo dõi trong tháng thì có mục cảnh báo nhịp độ bán hàng theo ngày."*

---

## 5. Luồng demo đề xuất

| # | Nội dung | Câu | Vì sao |
|---|---|---|---|
| 1 | Mở đầu — số tổng quan | C1 | Nhanh, chắc đúng, dễ gây ấn tượng |
| 2 | Cắt theo miền | C3 | Cho thấy chiều sâu dữ liệu |
| 3 | Top khách / top sản phẩm | C4, C5 | Câu nghiệp vụ ai cũng quan tâm |
| 4 | Cây tổ chức 3 cấp | C8 | Đúng mô hình 4 lớp anh Long yêu cầu |
| 5 | KPI tháng 7 | C6, C7 | **Nhớ nói rõ ngưỡng đang dùng** |
| 6 | **Phân quyền** | R1 → R5 | Điểm nhấn: đăng nhập vai vùng, hỏi vùng khác → bị chặn |
| 7 | Vai QLV | Q1, Q3 | Cho thấy xuống tới từng nhân viên |

**Chuẩn bị trước buổi demo (13/08):**
- [ ] **D1** — chạy `scripts/verify_rh_a_tools.py` trên máy 24 (kiểm 5 tool R-H(a) với Bravo thật,
      xem mục R-H ở trên) — bắt buộc trước khi cho ai đăng nhập vai QLV hỏi doanh thu
- [ ] Chạy `set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py --as-of 2026-07-31`
      sáng 13/08, in ra để cầm tay đối chiếu
- [ ] Đăng nhập sẵn 3 tài khoản trên 3 tab riêng (đổi vai giữa buổi rất mất thời gian)
- [ ] Hỏi thử toàn bộ 1 lượt trước giờ demo — chatbot giới hạn **10 câu/phút/người**, hỏi dồn dính lỗi 429
- [ ] Kiểm tra tiến trình đồng bộ trên máy 24 — và **chỉ có một** tiến trình đang chạy (tiền lệ: restart
      để sót tiến trình cũ → gửi/ghi trùng, tổng gấp N lần dù đếm distinct vẫn đúng)
- [ ] Kiểm tunnel còn sống + đăng nhập thử trên `dnh-bot.vercel.app` ngay trước giờ (xem sự cố 10-11/08:
      `Get-Process cloudflared`, `Get-Service DNH_Chatbot_Tunnel` phải `Running`)

---

## 6. Bảng ghi kết quả chạy thử (điền ở Khối 3 ngày 23/07)

**Lô A (`dnh`, c_level) — chạy 23/07/2026: 6/7 khớp.**

> ⚠️ **Đính chính mã câu (27/07):** mã ở cột "Mã" bên dưới là mã ghi tay lúc chạy, lệch so với bảng
> kịch bản mục 1 — **đọc theo nội dung mới đúng**. Đã sửa 2 dòng KPI được xác nhận chắc chắn theo nội
> dung: dòng "xếp hạng vùng theo KPI" là **C6** (không phải C5), dòng "TDV đạt chỉ tiêu" là **C7**
> (không phải C6). **28/07 đã đánh số nốt các dòng còn lại** theo nội dung: "doanh thu 3 miền" = C3,
> "top khách + top sản phẩm" = C4/C5, "chi tiết KH DTH00237" = **Q4** (mục 3 — không phải mã C nào,
> đây là chỗ dễ nhầm nhất). Không còn dòng nào chưa có mã chuẩn.
>
> ⚠️ Mã **Q4** bị dùng cho 3 nội dung khác nhau trong tài liệu ("khách DTH00237" ở mục 3, "từ chối
> xem đội anh Tân" ở R-F/Lô C, "top khách ép scope MB" ở Lô D). Và **R1..R6** (câu hỏi) khác hoàn
> toàn **R-A..R-G** (mã rủi ro) dù cùng tiền tố R — đọc nhanh rất dễ lẫn.

| Mã | ✅/❌ | Thời gian trả lời | Phân loại lỗi | Ghi chú |
|---|---|---|---|---|
| C1 | ✅ | — | *(lệch nhỏ)* | OTC khớp tuyệt đối. ETC 27,40 vs 27,38 tỷ — **lệch 20 triệu (0,07%)** giữa kho local chatbot và Bravo. Không nghiêm trọng nhưng có thật, cần theo dõi |
| C3 *(ghi tay: C2)* | ✅ | — | — | Doanh thu 3 miền: MB/MT khớp; MN lệch 20 triệu (cùng nguồn ETC ở C1). **Bonus:** chatbot tự tách "MT = Modern Trade 1,83 tỷ" → **trả lời sẵn câu X3**, phân biệt đúng MT-kênh với MT-miền Trung |
| C4/C5 *(ghi tay: C3, C4)* | ✅ | — | — | Top khách hàng + top sản phẩm — khớp hoàn toàn top 10 |
| **C6** *(ghi tay: C5)* | ❌ | — | **Khác tầng gộp** | Xếp hạng vùng theo KPI: chatbot MB 45,9% / MN 53,0% / MT 37,4%; báo cáo MB 42,1% / MN 45,0% / MT 36,4%. **Xem mục R-D bên dưới** |
| **C7** *(ghi tay: C6)* | ✅ | — | — | TDV đạt chỉ tiêu: 137/147 chưa đạt, 10 đạt ≥80% — khớp sau khi đồng bộ ngưỡng 80% sáng 23/07. **Lưu ý: đây là ngưỡng 80% cũ, phải chạy lại ở ngưỡng đúng theo vai trò** |
| **Q4** *(ghi tay: C7 — theo nội dung là Q4 ở mục 3, không phải mã C nào)* | ✅ | — | *(R-B đã đóng)* | Chi tiết KH DTH00237: 1,53 tỷ đúng, bonus tên "BV Đa khoa Đồng Tháp". Khi đó trả *"Công nợ: chưa có dữ liệu"* — **bằng chứng sống của R-B**. ✅ **27/07 sau khi đổi nguồn đã ra số cụ thể** (dư nợ 4,35 tỷ / quá hạn 0,78 tỷ) |
| C8 | | | | *(chưa hỏi — cây doanh thu MB)* |
**Lô B (`thuy.nguyen2`, regional_director MB) — chạy 23/07/2026: bảo mật PASS, 1 lỗi dữ liệu.**

| R1 | ✅ | — | — | 22,77 tỷ — khớp tuyệt đối. Chatbot còn tự nói rõ *"tài khoản chỉ có quyền xem vùng MB"* |
| **R3** | ✅ | — | — | Liệt kê **9 QLV**, số từng người khớp tuyệt đối cây C8 — nhưng **thiếu MBKV12**, xem R-E |
| R2, R4 | | | | *(chưa hỏi)* |
| **R5** | 🔒 ✅ **PASS** | — | — | *"tài khoản chỉ được cấp quyền xem vùng Miền Bắc"* — **không rò rỉ số miền Nam** |
| **R6** | 🔒 ✅ **PASS** | — | — | Từ chối đúng, còn chủ động mời xem lại số MB |
**Lô C (`tung.trinh`, qlv MB) — chạy 23/07/2026: 1 lỗ hổng bảo mật + 1 lỗi tool.**

| **Q1** | 🔒 ❌ **HỞ** | — | **Rò rỉ phạm vi** | Hỏi *"TDV dưới quyền tôi"* → trả về **87 TDV toàn vùng MB** thay vì **10 TDV** của đội. **Xem R-F** |
| **Q2** | ❌ | — | Sai tool + sai cảnh báo | Trả *"17/17 ngày doanh số 0đ… vấn đề nghiêm trọng"* cho một QLV. **Xem R-G** |
| Q3 | ✅ | — | — | Đúng: `tungtx`, QLV, MB. **Điểm cộng**: tự phát hiện bản ghi trùng `TM25010192` và tự cảnh báo rằng kết quả Q2 không phù hợp vai trò QLV |
| **Q4** | 🔒 ✅ **PASS** | — | — | Từ chối xem đội QLV khác, nêu rõ lý do "dữ liệu hiệu suất cá nhân của đồng nghiệp" |
| X1 | ✅ | — | — | 23/07 (trước khi port SP): chatbot **từ chối đúng cách** — *"chưa tra cứu được… không thể kết luận khách không có nợ"*. **Từ 27/07 đã có số thật** → chuyển thành câu demo chính thức, phải hỏi lại ở phiên mới |
| X2 | | | | *(chưa hỏi — tồn kho chết, giá trị tồn luôn = 0 nên dự kiến trống)* |
| X3 | ✅ | — | — | Trả lời **gián tiếp** ở C3: chatbot tự tách *"MT = Modern Trade 1,83 tỷ"*, không nhầm với Miền Trung |
| X4 | | | | *(chưa hỏi — nhạy cảm, không demo trước đông người)* |
| X5 | | | | *(chưa hỏi — chatbot không có tool, dự kiến trả lời thiếu)* |

**Lô D (`tungtx`, qlv MB) — chạy TỐI 23/07/2026, SAU bản vá ngưỡng theo vai trò: 4/4 đạt.**

| Mã | ✅/❌ | Ghi chú |
|---|---|---|
| R3 (chấm lại) | ✅ | Ngưỡng QLV báo đúng **70%**, trước đó (sáng) live vẫn nói 80%. 10 QLV, MBKV12 có mặt (2,09 tỷ) — ngoại lệ IsDuplicate vẫn sống qua deploy |
| C7 (chấm lại) | ✅ | Trả **cả 2 con số** tách bạch: 87/87 chưa đạt chỉ tiêu (100%) · 15/87 tới mức thưởng (65%). Tự giải thích "giữa tháng, không phải lỗi" |
| **X6** | ✅ | Câu bẫy "TDV nào không được thưởng" — chatbot từ chối kết luận, nói đúng phạm vi "chưa tới mức thưởng nhóm hàng", tự nêu lương cơ bản + V15/ASO chưa tính được |
| Q2 | ✅ | KPI ngày TM25010199, 18 ngày (bỏ 3 cuối tuần) cộng lại đúng khớp lũy kế tháng (202,3 tr, lệch 6,5 tr = đúng phần cuối tuần không hiện trong bảng ngày) |
| Q3 | ✅ | Directory đúng: THO4 / TM25010199 / TDV / MB |
| Q4 | ✅ | Top khách hàng ép đúng scope MB; tự nhận hạn chế "không lọc được theo đội", không suy đoán |

> ⚠️ **Sau lô D phát hiện 2 rò rỉ nhỏ, đã vá nhưng CHƯA deploy** (không sinh số sai, chỉ lộ chi tiết
> kỹ thuật — gộp vào lần deploy kế tiếp): câu trả lời từng in thẳng `count_full_target = 0` và
> `(get_customer_detail)` ra cho người dùng. Đã cấm cả tên trường lẫn tên tool trong câu trả lời
> (commit `76b4e92`, `9982bd4`).
>
> ⚠️ **Toàn bộ Lô A/B/C ở trên chạy khi live còn ngưỡng 80% phẳng — cần hỏi lại các câu dính KPI
> (C6, C7, R3, Q1) trước khi dùng làm bằng chứng cho demo thật.** Chỉ Lô D là đã kiểm ở ngưỡng đúng.
>
> ⚠️ **28/07 bổ sung — Q2 cũng phải chạy lại**, kể cả kết quả ✅ ở Lô D. `get_employee_daily_kpi` vừa
> được sửa lỗi lấy chỉ tiêu sai tháng (xem R-G): mọi kết quả Q2 chạy TRƯỚC 28/07 đều có thể mang
> chỉ tiêu của tháng khác, kéo theo sai `%` từng ngày và sai đếm 🔴/🟡/🟢. **Danh sách phải chạy lại
> ở phiên mới: C6, C7, R3, Q1, Q2** — cộng các câu chưa từng hỏi: **C8, R2, R4, X1, X2, X4, X5**.

**Phân loại lỗi** (mỗi ❌ phải rơi vào đúng 1 nhóm, không để trống):

1. **Sai số** — số khác đáp án đúng → nghiêm trọng, phải vá trước demo.
2. **Sai tool** — gọi nhầm tool (vd tự viết SQL theo vùng thay vì `get_revenue_by_region` → mất
   khách "mồ côi") → sửa mô tả tool.
3. **Hạn chế dữ liệu** — không có nguồn → né + dùng lời dẫn ở mục 4.
4. **Chậm** — ghi lại; tránh đưa vào demo hoặc chuẩn bị lời dẫn khi chờ.
