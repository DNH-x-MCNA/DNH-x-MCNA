# Chatbot Accuracy 99% — Day 19 Evaluator

Ngày chốt: 18/08/2026. Bổ sung sau khi kiểm lại toàn bộ việc ngày 17-19 và phát hiện gate quan
trọng nhất của Day 19 ("evaluator end-to-end đủ 90 câu") thực tế chưa đạt.

## Hiện trạng trước khi sửa (18/08 sáng)

- `scripts/evaluate_model_canary.py`: gọi `nl2sql.ask()` thật, chấm 2 chiều (có gọi đúng tool
  không, có bị từ chối không) — nhưng chỉ **18/90 câu** golden, không đối chiếu số với SQL
  Server, không sinh báo cáo Markdown, không phân loại mức độ lỗi.
- `scripts/danh_gia_model.py` (viết trước đó cùng ngày, một phiên khác): **chưa từng được đưa
  vào Git** — nằm ngoài `git log --all` hoàn toàn. Đã xoá, hợp nhất phần ý tưởng còn dùng được
  (so số theo dãy chữ số bỏ dấu phân cách, phân biệt số cần có/số cấm) vào runner mới bên dưới
  thay vì duy trì 2 evaluator trùng mục đích.
- `pytest -q` từ gốc repo **không thu thập được** — xem đính chính trong
  `docs/chatbot_accuracy_99_day17_baseline.md`.

## Đã thêm: `scripts/run_business_evaluation.py`

Chạy toàn bộ 90 câu trong `scripts/business_stress_suite.py` qua `nl2sql.ask()` thật, đối
chiếu với SQL Server qua đúng cơ chế `_execute_checker()` mà `business_stress_suite.py` đã có
sẵn (không viết lại đường kết nối DB).

### Triết lý chấm điểm — cố tình KHÔNG tự động hoá mọi thứ

`business_stress_suite.py` tự ghi trong docstring: *"Không tự động phán PASS bằng so khớp câu
chữ; người kiểm thử đối chiếu số, kỳ, phạm vi và cảnh báo."* Runner mới tôn trọng đúng ranh giới
đó thay vì cố xây một máy chấm "đẹp trên giấy" nhưng đoán bừa ở chỗ không có cơ sở:

**Tự động chấm được, áp dụng cho cả 90 câu, không ngoại lệ:**
- Có lỗi hệ thống khi hỏi không.
- Có bị từ chối "câu hỏi quá phức tạp" không (đã có dữ liệu mà từ chối là sai).
- Có từ ngữ dự báo/ước tính lọt vào **câu trả lời** không — kiểm tra trên output thật, khác
  `evaluate_model_canary.py` (bản cũ chỉ kiểm tra chữ trong CÂU HỎI lúc định nghĩa case, không
  kiểm tra hành vi thật của model lúc trả lời).
- Có tool nào được gọi không — hỏi số liệu nghiệp vụ mà 0 tool chạy là dấu hiệu trực tiếp của
  tự bịa, bất kể tool cụ thể nào "đáng lẽ" đúng.

**Đối chiếu số với SQL Server — chỉ khi checker "gọn"** (≤3 dòng, ≤12 ô số): mọi số gốc phải
xuất hiện nguyên vẹn (so theo dãy chữ số, bỏ hết dấu phân cách) trong câu trả lời. Checker dạng
"top N" (top khách hàng, top sản phẩm...) **không** được tự chấm đúng/sai theo cách này — đối
chiếu 1-trong-20 dòng nào đúng cần hiểu ý câu hỏi. Ground truth vẫn đính kèm nguyên trong JSON
để người kiểm đối chiếu nhanh bằng mắt, đúng tinh thần gốc.

**Cố tình không chấm:** đúng tool cụ thể theo từng câu (chưa ai xác nhận tool nào đúng cho cả
90 câu — tự đoán rủi ro hơn để trống), đúng phạm vi vai trò (`audience` trong `BusinessCase` chỉ
là nhãn tài liệu, không map ra `scope_role`/`scope_area` thật), SQL ghi (đã có `_FORBIDDEN`
regex + test riêng ở `backend/query_engine.py`, không cần lặp lại).

### 3 lỗi bắt được ngay khi viết test (chưa từng chạy trên production)

1. `_significant_digit_runs` dùng `\d+` trần trên văn bản câu trả lời — dấu chấm ngăn nghìn
   ("39.327.016.119") cắt số thật thành các cụm ngắn rời rạc, không cụm nào đủ dài để tính là
   "số cần đối chiếu". Hậu quả nếu không bắt: **mọi câu trả lời đúng đều bị báo sai số.** Sửa
   bằng regex nhận cả số đã định dạng theo nhóm 3 chữ số lẫn số thô.
2. `_digits_of` (đọc ô dữ liệu SQL) rút chữ số từ CHUỖI KÝ TỰ bất kỳ — mã khách hàng
   `"HCM04298"` bị hiểu thành số `"04298"` cần đối chiếu. Sửa: chỉ nhận kiểu số thật
   (int/float/Decimal) từ SQL, bỏ qua mọi cột chuỗi.
3. `sys.path.insert(0, backend)` tái phát trong chính file canary trước đó — xem
   `docs/chatbot_accuracy_99_day17_baseline.md`.

Cả 3 lỗi đều được bắt bằng test viết TRƯỚC khi chạy thật (`tests/test_run_business_evaluation.py`,
18 test), không phải phát hiện trên production.

### Vẫn còn giới hạn thật, không che giấu

- **Chưa từng chạy trên dữ liệu thật.** Máy dev không nối được SQL Server; toàn bộ 90 câu mới
  được kiểm bằng dữ liệu giả (`_FakeSuite` trong test). Ai chạy thật trên máy 24 lần đầu có thể
  vẫn gặp lỗi runtime chưa lường trước — đây là rủi ro thật, không phải đã "xong 90/90".
- **Không gọi qua HTTP API thật** (đăng nhập, streaming, mã trạng thái HTTP) như kế hoạch gốc
  mô tả — gọi thẳng `nl2sql.ask()` trong tiến trình, giống hệt cách `evaluate_model_canary.py`
  đã làm. Bỏ qua tầng FastAPI/auth/streaming. Muốn kiểm đúng "production-like" thật sự cần một
  runner khác gọi qua `requests`/`httpx` tới server đang chạy — chưa làm, cần quyết định có đáng
  làm không trước khi đầu tư thêm.
- **Không có `expected_period`/`expected_scope`/`forbidden_numbers`/`required_warning` theo
  từng câu** như đặc tả gốc — `BusinessCase` không mang các trường đó, và tự suy ra cho 90 câu
  trong một lần ngồi có rủi ro sai cao hơn giá trị mang lại.
- **Không phân loại P0/P1/P2 theo đúng nghĩa mức độ nghiệp vụ** — hiện chỉ có 1 mức (P0) cho mọi
  lỗi tự động bắt được; chưa phân biệt "sai số tiền" (nghiêm trọng nhất) với "thiếu tool nhưng
  câu trả lời tình cờ đúng" (cũng nghiêm trọng nhưng khác bản chất).

### Cách chạy (cần máy có `ANTHROPIC_API_KEY`/`LLM_*` và nối được SQL Server — máy 24)

```powershell
cd C:\dnh_chatbot
python scripts\run_business_evaluation.py --label sonnet-5
python scripts\run_business_evaluation.py --group "Công nợ" --label smoke-debt
python scripts\run_business_evaluation.py --skip-ground-truth   # neu may khong noi duoc SQL Server
python scripts\run_business_evaluation.py --dry-run             # chi in danh sach, an toan tuyet doi
```

Kết quả ghi vào `results/business-eval-<label>-<timestamp>.json` (chi tiết từng câu, kèm
ground truth thô) và `.md` cùng tên (tổng hợp theo nhóm, danh sách câu chưa đạt, P50/P95 thời
gian trả lời, tổng chi phí).

## Gate Day 19 — đối chiếu thật, không tô hồng

| Yêu cầu kế hoạch | Trạng thái |
|---|---|
| Đưa evaluator vào Git | ✅ `scripts/run_business_evaluation.py` + 18 test |
| Đủ 90 câu | ✅ tái dùng nguyên `business_stress_suite.CASES` |
| Gọi API thật (HTTP, đăng nhập, streaming) | ❌ gọi thẳng hàm trong tiến trình |
| Máy chấm deterministic | ⚠️ 4/9 chiều kế hoạch gốc yêu cầu (tool, từ chối, lộ dự báo, số ở checker gọn); 5 chiều còn lại cố tình để trống thay vì đoán bừa |
| Sinh báo cáo JSON + Markdown | ✅ |
| P0/P1/P2 | ❌ mới có 1 mức |
| Đã chạy thật trên 90 câu | ❌ chưa — cần máy 24 |

**Kết luận thẳng:** hạ tầng đã đủ để CHẠY, nhưng "Day 19 đạt 99%" vẫn là một tuyên bố chưa có
bằng chứng — không ai trên trái đất, kể cả công cụ vừa viết, đã thấy 90 câu chạy thật một lần
nào. Việc tiếp theo bắt buộc là chạy trên máy 24 rồi đọc đúng file Markdown sinh ra, không phải
tin vào tài liệu này.
