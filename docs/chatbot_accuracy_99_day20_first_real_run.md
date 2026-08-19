# Chatbot Accuracy 99% — Day 20 First Real Run

Chạy thật: 18/08/2026 17:35 (máy 24, `results/business-eval-sonnet-5-v2-20260818-173525.json`).
Phân tích + vá lỗi: 19/08/2026.

Đây là việc mà `docs/chatbot_accuracy_99_day19_evaluator.md` chốt là **bắt buộc phải làm tiếp**:
*"Đã chạy thật trên 90 câu | ❌ chưa — cần máy 24"*. Hôm nay đã chạy, và kết quả không đơn giản
như con số thô ban đầu cho thấy.

## Con số thô gây hiểu lầm nếu đọc vội

`run_business_evaluation.py` báo **42/90 câu "chưa đạt tự động"**. Đọc thẳng con số này sẽ kết
luận sai là chatbot lỗi gần một nửa. Sau khi tách bằng chứng cho từng câu, thực tế là:

| Nhóm | Số câu | Bản chất |
|---|---:|---|
| `loi_he_thong` (Q067–Q090) | 24 | Hết ngân sách API giữa lúc chạy — không phải lỗi code |
| `khong_goi_tool` | 8 | 0/8 là lỗi thật — xem bên dưới |
| `sai_so_lieu` | 10 | **3/10 là lỗi thật**, 7/10 là hạn chế của máy chấm |
| **Lỗi chatbot thật xác nhận được** | **3** | Q016, Q012, Q044 — đã vá |

Tỷ lệ lỗi thật trên tổng 90 câu (bỏ qua 24 câu chưa test được vì hết ngân sách): **3/66 ≈ 4,5%**.

## Nhóm `loi_he_thong` (24 câu, Q067–Q090) — sự cố hạ tầng, không phải bug

Toàn bộ 24 câu cùng một lỗi: `BadRequestError: ... You have reached your specified API usage
limits. You will regain access on 2026-09-01`. Đây là hạn mức chi tiêu tự đặt trên Anthropic
Console cho API key dùng chung, không phải giới hạn cứng của nền tảng. **Xác nhận đây là sự cố
đang diễn ra thật (19/08), không chỉ ảnh hưởng lần chạy eval**: chatbot production dùng chung
key này, nên người dùng thật cũng đang nhận lỗi ngay lúc viết tài liệu này. Xử lý nằm ngoài phạm
vi code — cần nâng/gỡ hạn mức trên Console (vài phút, không phải đợi tới 1/9), do người quản lý
billing thực hiện.

## Nhóm `khong_goi_tool` (8 câu) — xác nhận 0/8 là lỗi thật

Đọc từng câu trả lời thật thay vì tin bảng lỗi thô:

- **5 câu hỏi lại hợp lệ** (Q018, Q023, Q055, Q032, Q033): evaluator chạy dưới vai `c_level`
  không gắn với QLV cụ thể nào (giới hạn đã ghi trong Day 19: *"`audience` chỉ là nhãn tài liệu,
  không map ra `scope_role`/`scope_area` thật"*). Câu hỏi dùng "đội tôi" mà không có scope thật —
  chatbot hỏi lại thay vì đoán bừa, đúng tinh thần "thà nói không biết còn hơn bịa".
- **3 câu giải thích quy tắc** (Q021, Q060, Q061): hỏi "vì sao"/ngưỡng chính sách, trả lời đúng từ
  quy tắc đã có trong `schema_context.py`/prompt hệ thống, không cần gọi tool vì không tra số liệu
  mới.

**Kết luận:** luật chấm điểm "0 tool = tự bịa" trong `grade_case()` (`run_business_evaluation.py`)
quá cứng cho 2 loại câu này. Đây là hạn chế của máy chấm, **chưa vá trong code** — mọi lần chạy
sau vẫn sẽ báo sai y hệt cho các câu dạng hỏi-lại/giải-thích-quy-tắc.

## Nhóm `sai_so_lieu` (10 câu) — soi bằng SQL thật, không đoán

Lấy `ground_truth` (SQL đối chiếu) và SQL tự do thật mà chatbot đã chạy (từ
`backend/logs/audit_log.jsonl`) cho từng câu.

### 3 lỗi chatbot thật — đã vá

| Case | Lỗi | SQL sai (thật, từ audit_log) | Sửa |
|---|---|---|---|
| **Q016** | Dùng nhầm cột. Hỏi "TDV nào chưa có quản lý trực tiếp" nhưng SQL dò `dim_nhanvien.manager_area_code` (mã VÙNG mà QLV phụ trách) thay vì `fact_tonghopkhachhang.manager_code` (quan hệ quản lý THẬT, thêm 23/07/2026 chính để thay thế cách suy luận qua vùng — `sync_warehouse.py:285-286`). Ra 15 TDV thay vì gần 0. Q024/Q062 hỏi cùng chủ đề trong **cùng lần chạy** lại tự dùng đúng `manager_code` — vì cột đó chưa từng được ghi trong tài liệu schema nên model chọn ngẫu nhiên giữa 2 cách. | `WHERE n.position_code='TDV' AND (n.manager_area_code IS NULL OR n.manager_area_code='')` | `backend/schema_context.py`: thêm cảnh báo tại `dim_nhanvien` + thêm mô tả `manager_code` là nguồn chuẩn duy nhất tại `fact_tonghopkhachhang` |
| **Q012** | Đối soát doanh thu "tháng 7" (không giới hạn kênh) nhưng SQL chỉ viết cho OTC (`vHoaDonTotal`/`vHoaDon`), bỏ sót hoàn toàn ETC. | `FROM dbo.vHoaDonTotal ... UNION ALL FROM dbo.vHoaDon` (không có view ETC nào) | `schema_context.py` rule 13: câu hỏi không giới hạn kênh phải tính cả OTC và ETC |
| **Q044** | Hỏi "dư nợ cả OTC và ETC... tổng nợ của họ thế nào" — case tự ghi rõ yêu cầu "trả riêng dư nợ/quá hạn OTC, ETC" nhưng SQL gộp `SUM(balance_end)` 2 kênh làm một ngay trong subquery, mất khả năng tách lại. | `SELECT customer_code, SUM(balance_end) AS balance_end, ...` (không có `CASE WHEN sales_channel=...`) | `schema_context.py` rule 13: câu cần tách kênh phải dùng `SUM(CASE WHEN sales_channel='OTC' THEN ... END)` |

Vá bằng 1 commit, chỉ sửa `backend/schema_context.py` (tài liệu mô tả schema đưa vào prompt —
không đổi `query_engine.py` hay cơ chế thực thi SQL). Đã push `origin/master` (`7f39182`).

### 7 câu còn lại — hạn chế của máy chấm, không phải lỗi chatbot

- **Q007, Q011**: checker ground-truth chứa thêm cột (`Revenue` tổng, `RowCount`) mà câu hỏi
  không hề hỏi tới; chatbot trả lời đúng 100% các số được hỏi. Máy chấm coi thiếu cột không được
  hỏi cũng là "sai số".
- **Q009**: cột `DistributorCode` trong `vHoaDonTotal`/`vHoaDonETCTotal` chỉ có 2 giá trị duy nhất
  toàn hệ thống (`'OTC1'`, `'ETC'`) — không mang thông tin nhà phân phối thật. Chatbot tự chuyển
  sang trả lời theo khách hàng (`get_top_customers`) — hợp lý hơn hẳn so với khớp đúng nghĩa đen 2
  dòng vô nghĩa của checker.
- **Q040**: chatbot làm tròn "3,1 tỷ" cho 3.052.479.909 (tròn 1 chữ số thập phân, hợp lệ), lệch
  ~1,55% vượt ngưỡng dung sai 1% của checker trong gang tấc.
- **Q046**: kết luận định tính đúng ("khớp 100%") nhưng không trích số liệu cụ thể để chứng minh —
  ranh giới, có thể cải thiện tính minh bạch nhưng không sai nội dung.

**Chưa vá trong code** — đây là ghi nhận cho lần sửa `run_business_evaluation.py` sau, không phải
việc của Day 20.

## Đã làm

- Chạy thật 90 câu qua `nl2sql.ask()` trên máy 24, đóng gate "Đã chạy thật trên 90 câu" của Day 19.
- Viết 3 script debug dùng lại được (`scripts/debug_sai_so_lieu.py`,
  `scripts/debug_sql_for_cases.py`, cập nhật `scripts/debug_classify_failures.py`) — đọc file JSON
  kết quả đã có sẵn, không tốn thêm 1 lệnh gọi model nào để chẩn đoán.
- Xác định chính xác 3 lỗi chatbot thật bằng SQL thật (không đoán), vá trong
  `backend/schema_context.py`, push `origin/master`.
- Phát hiện sự cố đang sống: production dùng chung API key với testing, đã chạm hạn mức chi tiêu,
  chatbot thật đang từ chối người dùng thật tại thời điểm viết tài liệu này.

## Chưa làm — không tô hồng

- **Fix Q016/Q012/Q044 CHƯA được xác minh trên dữ liệu thật.** Đã đưa 3 câu hỏi kiểm chứng cụ thể
  cho người vận hành chạy sau khi deploy, nhưng bị chặn bởi sự cố hết ngân sách API — chưa chạy
  được đến lúc viết tài liệu này.
- **24/90 câu (Q067–Q090) chưa từng được test** — bị cắt ngang giữa chừng bởi cùng sự cố ngân sách.
  Sau khi ngân sách được khôi phục, phải chạy lại riêng nhóm này (lương thưởng + khuyến mãi + tồn
  kho + độ mới dữ liệu) trước khi coi 90 câu là đã kiểm đủ.
- **Máy chấm (`run_business_evaluation.py::grade_case`) vẫn còn 2 nguồn báo sai oan**, chưa vá:
  luật "0 tool = tự bịa" quá cứng cho câu hỏi-lại/giải-thích-quy-tắc (8 câu); checker "sai_so_lieu"
  không phân biệt cột được hỏi với cột phụ trợ, và dung sai làm tròn 1% quá chặt cho số 1 chữ số
  thập phân ở thang tỷ (Q007, Q009, Q011, Q040, Q046).
- **P0/P1/P2 theo đúng mức độ nghiệp vụ** vẫn chưa có — gap này Day 19 đã ghi, chưa đụng tới hôm
  nay.
- **Gọi qua HTTP API thật** (đăng nhập, streaming) vẫn chưa làm — cùng gap Day 19.
- **Sự cố hết ngân sách API chưa được xử lý** — nằm ngoài phạm vi code, cần người quản lý billing
  nâng/gỡ hạn mức trên Anthropic Console.

## Gate Day 20 — đối chiếu thật, không tô hồng

| Yêu cầu | Trạng thái |
|---|---|
| Chạy thật 90 câu trên máy 24 | ✅ (18/08, có cắt ngang ở Q067 vì hết ngân sách) |
| Phân loại đúng bản chất 42 câu "chưa đạt" | ✅ 24 hạ tầng / 8 máy chấm quá cứng / 10 → 3 lỗi thật + 7 máy chấm |
| Vá lỗi chatbot thật, có bằng chứng SQL | ✅ 3/3 (Q016, Q012, Q044), commit `7f39182` |
| Xác minh fix trên dữ liệu thật | ❌ chặn bởi sự cố ngân sách API |
| Test đủ 24 câu còn thiếu (Q067–Q090) | ❌ chặn bởi cùng sự cố |
| Vá máy chấm (2 nguồn báo sai oan) | ❌ chưa làm, ghi nhận để làm sau |
| Sự cố ngân sách API | ⚠️ đã chẩn đoán + đưa hướng xử lý, chờ người quản lý billing thao tác |

**Kết luận thẳng:** Day 20 chứng minh được điều quan trọng nhất — sau khi tách đúng bản chất, tỷ
lệ lỗi chatbot thật trên dữ liệu thật thấp hơn nhiều so với con số thô 42/90 (~47%) ban đầu gợi ý,
và 3 lỗi tìm được đều có bằng chứng SQL cụ thể, đã vá. Nhưng "đã vá" không đồng nghĩa "đã xong":
chưa xác minh được trên dữ liệu thật vì sự cố ngân sách API đang chặn ngay cả việc kiểm tra, và
24 câu chưa test coi như một lỗ hổng coverage còn treo, không được coi là đã qua.
