# Kịch bản Demo #1 Chatbot — 09/08/2026

*Soạn 23/07/2026. Đáp án đúng sinh bằng `python scripts/demo1_ground_truth.py` (đọc thẳng Bravo qua
đúng các hàm của báo cáo định kỳ). **Chạy lại script sáng 09/08 để lấy số của ngày demo** — số trong
file này là của 23/07, chỉ dùng để tập dượt và dò lỗi trước.*

---

## ✅ Trạng thái sau ngày 23/07/2026

Đã vá và **deploy lên máy 24 lúc 09:51**, kiểm chứng trực tiếp trên chatbot thật:

| Mã | Vấn đề | Kết quả kiểm chứng |
|---|---|---|
| **R-F** | QLV xem được hiệu suất TDV đội khác | ✅ **87 → 10 TDV**, 9 người chưa đạt, khớp từng số thập phân |
| **R-E** | Cờ trùng lặp ẩn 2 nhân viên thật | ✅ Xếp hạng QLV miền Bắc **9 → 10**, MBKV12 quay lại (2,04 tỷ) |
| **R-G** | KPI ngày trả "0đ" cho mã QLV | ✅ Báo đúng *"mã không có trên hóa đơn, thiếu dữ liệu, không phải bán được 0đ"* |
| **R-B** | Công nợ đọc bảng cũ, im lặng | ✅ Trả *"chưa tra cứu được… không thể kết luận khách không có nợ"* |
| **R-C** | Ngưỡng đạt 100% vs 80% | ✅ Thống nhất 80%, hiện ngưỡng trên email |
| **R-D** | Tầng gộp KPI vùng khác nhau | ✅ Tầng lá cả 3 nơi, **sửa gốc bằng `ManagerCode` thật** — xem chi tiết bên dưới |

Commit: `acfd828` + `2487806` (repo DNH-x-MCNA) · `7811f76` (repo DNH).

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

| Kỳ | Đạt ≥100% | Đạt ≥80% | TB toàn đội |
|---|---|---|---|
| Tháng 4/2026 (trọn tháng) | 64/150 | 109/150 | 88,1% |
| Tháng 5/2026 (trọn tháng) | 19/149 | 50/149 | 67,3% |
| Tháng 6/2026 (trọn tháng) | 25/150 | 52/150 | 65,5% |
| Tháng 7/2026 (mới 23/31 ngày) | **0/147** | **10/147** | 41,6% |

**Demo 09/08 rơi vào ngày thứ 9 của tháng 8** → tỷ lệ ngày đã trôi qua chỉ ~29% → hỏi "ai đạt chỉ
tiêu tháng này" gần như chắc chắn ra **0/147 ở CẢ HAI ngưỡng**. Khách sẽ hiểu là hệ thống hỏng, hoặc
là cả đội bán hàng đang thảm hoạ — cả hai đều sai.

> **✅ Xử lý (bắt buộc)**: mọi câu hỏi KPI trong demo **phải hỏi tháng 7/2026** — tại thời điểm
> 09/08 thì tháng 7 đã trọn vẹn, số liệu có ý nghĩa (~25/150 đạt 100%). Với chatbot, truyền
> `as_of_date = 2026-07-31`; câu hỏi tự nhiên: *"KPI nhân viên tháng 7 thế nào?"*
> **Tuyệt đối không hỏi "tháng này"/"hiện tại" cho bất kỳ câu KPI nào.**
>
> Nếu khách tự hỏi "tháng này thì sao?" — có sẵn lời dẫn ở mục 4.

### 🔴 R-B. Chatbot và báo cáo đọc công nợ từ 2 nguồn khác nhau

| | Nguồn | Số ngày 23/07 |
|---|---|---|
| Báo cáo định kỳ (`D:\DNH`) | `usp_DeptAccDueDate_GetData` — báo cáo gốc DNH | Dư nợ 181,96 tỷ · quá hạn 80,18 tỷ (**44,1%**) |
| Chatbot (`D:\DNH-x-MCNA`) | Supabase `receivable_detail`/`receivable_etc` — **Excel nhập 1 lần đầu dự án, không tự làm mới** | Chưa đo (Khối 3) |

Chính công thức cũ này từng thổi nợ 1 khách lên **9,17 tỷ** trong khi thật là **0,61 tỷ**.
→ Xem mục 4, câu X1. **Không đưa câu hỏi công nợ vào kịch bản demo cho tới khi xử lý xong.**

### ✅ R-C. Ngưỡng "đạt KPI" — ĐÃ THỐNG NHẤT VỀ 80% (23/07/2026)

Trước đó 2 hệ thống dùng 2 ngưỡng khác nhau (báo cáo ≥100%, chatbot ≥80%) → cùng dữ liệu tháng 6
ra **25/150** vs **52/150**, chênh **27 người**. Đã đưa báo cáo định kỳ về **≥ 80%** cho khớp
chatbot (`src/etl.py::KPI_ACHIEVED_THRESHOLD`), và **hiện ngưỡng ngay trên email** — ô "Đạt Chỉ
Tiêu" giờ ghi rõ *"(≥80%)"*.

Kiểm chứng sau khi sửa (tháng 7, tại 23/07): báo cáo trả **10/147**, đúng bằng con số ngưỡng 80%
trong `scripts/demo1_ground_truth.py`.

> ⚠️ **Vẫn cần DNH xác nhận** 80% có đúng là quy ước nghiệp vụ không — đang hỏi ở
> `docs/Cau_hoi_can_DNH_xac_nhan.md` mục A6. Ngưỡng đã tách thành hằng số, đổi 1 chỗ khi có trả lời.
> Tại demo, khi trình câu KPI **vẫn phải nói rõ đang dùng ngưỡng 80%** — số nào cũng phải giải thích
> được, đừng đưa số trần.

### ✅ R-D. KPI theo vùng — ĐÃ THỐNG NHẤT VỀ "TẦNG LÁ" (23/07/2026)

Phát hiện khi chạy thử: hai hệ thống gộp ở hai tầng khác nhau nên ra hai bộ số.

| Cách gộp | MB | MN | MT |
|---|---|---|---|
| Chỉ tầng TDV — chatbot *(cũ)* | 10,89 / 23,75 tỷ = 45,9% | 2,79 / 5,26 = 53,0% | 2,54 / 6,79 = 37,4% |
| QLV + TDV mồ côi — báo cáo *(cũ)* | 12,97 / 30,78 tỷ = 42,1% | 2,88 / 6,39 = 45,0% | 2,55 / 7,00 = 36,4% |
| ✅ **Tầng lá — cả hai *(mới)*** | **13,01 / 29,04 tỷ = 44,8%** | **2,79 / 5,26 = 53,1%** | **2,54 / 6,79 = 37,5%** |

**Không bên nào sai công thức** — hai lát cắt song song hợp lệ của cùng một khoản doanh thu. Nhưng
mỗi cách đều có khuyết điểm thật:

- Tầng TDV thuần **bỏ sót** QLV tự ôm khách, không có đội — **Nguyễn Thị Thanh Thủy (MBKV12)**,
  doanh số **2,01 tỷ** biến mất khỏi KPI miền Bắc.
- Tầng QLV **cộng chồng target cấp quản lý**: MB 30,78 tỷ so với 23,75 tỷ ở tầng TDV — chênh 7,03
  tỷ, trong đó MBKV12 chiếm 5,28 tỷ, **còn 1,75 tỷ chưa giải thích được** (nghi vấn mục A4).

**Đã chọn "tầng lá"** = mọi TDV + những QLV **không có** TDV nào dưới quyền. Không bỏ sót ai, không
cộng chồng. Áp cho **cả ba nơi**, đã kiểm chứng ra cùng con số trên chatbot LIVE:

| Nơi | Trạng thái |
|---|---|
| `src/etl.py::get_digest_metrics` (báo cáo) | ✅ toàn đội **44,7%** |
| `report_templates.py::kpi_ranking` (chatbot) | ✅ Deploy + kiểm chứng trên chatbot thật |
| `scripts/demo1_ground_truth.py` (đối chiếu) | ✅ |

> ⚠️ Sửa cách gộp thì phải sửa **đủ cả 3 nơi** — sót một chỗ là lệch lại như cũ.

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

**Ghi chú thêm**: target `tungtx` chatbot báo **4,15 tỷ**, snapshot Bravo là **3,02 tỷ** — chênh
1,13 tỷ, chưa rõ nguyên nhân, cần kiểm riêng.

---

## 1. Vai `c_level` — toàn quốc (8 câu)

| Mã | Câu hỏi | Tool kỳ vọng | Đáp án đúng (23/07) | Kết quả thực tế |
|---|---|---|---|---|
| C1 | Doanh thu tháng này đến hôm nay bao nhiêu, tách OTC và ETC? | `get_revenue_by_channel` | OTC 20,34 tỷ (6.098 HĐ) · ETC 27,38 tỷ (655 HĐ) · **Tổng 47,71 tỷ** | ⬜ |
| C2 | So với tháng trước tăng hay giảm bao nhiêu phần trăm? | `compare_periods` | T7 47,71 tỷ vs T6 62,16 tỷ = **−23,2%** ⚠️ | ⬜ |
| C3 | Doanh thu tháng này chia theo ba miền thế nào? | `get_revenue_by_region` | Bắc 22,77 tỷ · Nam 21,15 tỷ · Trung 3,79 tỷ (cộng = 47,71 tỷ ✔) | ⬜ |
| C4 | Top 10 khách hàng lớn nhất tháng này? | `get_top_customers` | 1. DTH00237 1,53 tỷ · 2. HCM13368 1,32 tỷ · 3. NDI00720 1,32 tỷ | ⬜ |
| C5 | Top 10 sản phẩm bán chạy nhất tháng này? | `get_top_products` | 1. An cung ngưu hoàng hoàn 3,68 tỷ · 2. Siro bổ phế Nam Hà 3,52 tỷ | ⬜ |
| C6 | **Xếp hạng các vùng theo mức đạt KPI tháng 7?** | `get_kpi_ranking(group_by="region")` | MN 45,0% · MB 42,1% · MT 36,4% — toàn đội 41,6% | ⬜ |
| C7 | **Tháng 7 có bao nhiêu TDV chưa đạt chỉ tiêu?** | `get_employee_kpi(filter="below_target", position_code="TDV", as_of_date="2026-07-31")` | Ngưỡng ≥80%: **đạt 10/147 · chưa đạt 137/147** *(số tại 23/07 — chạy lại sát ngày demo)* | ⬜ |
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
| R2 | Top khách hàng vùng tôi tháng này? | `get_top_customers` đã ép scope | *(chạy script để lấy)* | ⬜ |
| R3 | KPI các QLV trong vùng tôi tháng 7 xếp hạng thế nào? | `get_kpi_ranking(group_by="qlv")` | Xem cây C8 — dẫn đầu Trịnh Xuân Tùng 57,1% | ⬜ |
| R4 | Tồn kho vùng tôi hiện bao nhiêu? | `get_inventory_by_region(area_code="MB")` | *(đối chiếu báo cáo tồn kho)* | ⬜ |
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
| X1 | Khách hàng [mã] còn nợ bao nhiêu, quá hạn bao nhiêu? | Chatbot đọc Supabase Excel cũ → **mâu thuẫn báo cáo** (xem R-B) | Vá cảnh báo bắt buộc hôm nay; port SP gốc trước 09/08 | ⬜ |
| X2 | Hiện có bao nhiêu hàng tồn kho chết? | Thiếu nguồn giá vốn → giá trị tồn luôn = 0 | **Né.** Nếu khách hỏi: nói thẳng đang chờ DNH xác nhận nguồn giá | ⬜ |
| X3 | Doanh thu kênh MT tháng này? | MT = Modern Trade hay Miền Trung | Thử xem chatbot **có hỏi lại không**. Tự đoán = phải sửa | ⬜ |
| X4 | Có ai chạy đơn dồn cuối tháng không? | `check_order_timing` **nêu đích danh nhân viên** | Nhạy cảm — **không demo trước đông người** | ⬜ |
| X5 | Doanh số ETC theo từng nhân viên? | Chatbot **không có tool** cho mục này → sẽ tự ghép SQL hoặc trả thiếu | Né; mục này chỉ trình qua báo cáo email | ⬜ |

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

**Chuẩn bị trước buổi demo:**
- [ ] Chạy `python scripts/demo1_ground_truth.py` sáng 09/08, in ra để cầm tay đối chiếu
- [ ] Đăng nhập sẵn 3 tài khoản trên 3 tab riêng (đổi vai giữa buổi rất mất thời gian)
- [ ] Hỏi thử toàn bộ 1 lượt trước giờ demo — chatbot giới hạn **10 câu/phút/người**, hỏi dồn dính lỗi 429
- [ ] Kiểm tra tiến trình đồng bộ trên máy 24 còn chạy (dữ liệu cũ → số lệch báo cáo)

---

## 6. Bảng ghi kết quả chạy thử (điền ở Khối 3 ngày 23/07)

**Lô A (`dnh`, c_level) — chạy 23/07/2026: 6/7 khớp.**

| Mã | ✅/❌ | Thời gian trả lời | Phân loại lỗi | Ghi chú |
|---|---|---|---|---|
| C1 | ✅ | — | *(lệch nhỏ)* | OTC khớp tuyệt đối. ETC 27,40 vs 27,38 tỷ — **lệch 20 triệu (0,07%)** giữa kho local chatbot và Bravo. Không nghiêm trọng nhưng có thật, cần theo dõi |
| C2 | ✅ | — | — | MB/MT khớp; MN lệch 20 triệu (cùng nguồn ETC ở C1). **Bonus:** chatbot tự tách "MT = Modern Trade 1,83 tỷ" → **trả lời sẵn câu X3**, phân biệt đúng MT-kênh với MT-miền Trung |
| C3 | ✅ | — | — | Khớp hoàn toàn top 10 |
| C4 | ✅ | — | — | Khớp hoàn toàn top 10 |
| **C5** | ❌ | — | **Khác tầng gộp** | Chatbot MB 45,9% / MN 53,0% / MT 37,4%; báo cáo MB 42,1% / MN 45,0% / MT 36,4%. **Xem mục R-D bên dưới** |
| C6 | ✅ | — | — | 137/147 chưa đạt, 10 đạt ≥80% — **khớp hoàn hảo** sau khi đồng bộ ngưỡng 80% sáng 23/07 |
| C7 | ✅ | — | *(xác nhận R-B)* | 1,53 tỷ đúng, bonus tên "BV Đa khoa Đồng Tháp". Nhưng trả *"Công nợ: chưa có dữ liệu"* cho một bệnh viện tỉnh — **bằng chứng sống của R-B** |
| C8 | | | | *(chưa hỏi)* |
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
| X1 | | | | |
| X2 | | | | |
| X3 | | | | |
| X4 | | | | |
| X5 | | | | |

**Phân loại lỗi** (mỗi ❌ phải rơi vào đúng 1 nhóm, không để trống):

1. **Sai số** — số khác đáp án đúng → nghiêm trọng, phải vá trước demo.
2. **Sai tool** — gọi nhầm tool (vd tự viết SQL theo vùng thay vì `get_revenue_by_region` → mất
   khách "mồ côi") → sửa mô tả tool.
3. **Hạn chế dữ liệu** — không có nguồn → né + dùng lời dẫn ở mục 4.
4. **Chậm** — ghi lại; tránh đưa vào demo hoặc chuẩn bị lời dẫn khi chờ.
