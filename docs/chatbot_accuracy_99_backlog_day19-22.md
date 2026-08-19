# Backlog chi tiết — Ngày 19-22 (đối chiếu với kế hoạch gốc, 19/08/2026)

Băm nhỏ từng bullet trong kế hoạch "Hoàn thiện chatbot trước 25/08/2026" thành việc cụ thể, đánh
dấu trạng thái thật (không tô hồng). ✅ = đã xác nhận bằng test/code thật. ⚠️ = một phần/chưa kiểm
chứng đủ. ❌ = chưa động tới. 🔒 = cần API AI thật mới làm/kiểm được (đang bị chặn bởi sự cố ngân
sách API tới 1/9).

## Ngày 19 — evaluator end-to-end

### 19.1 Sửa evaluator hiện có
- ✅ Đưa evaluator vào Git (`scripts/run_business_evaluation.py`, thay `danh_gia_model.py`)
- ✅ Thêm unit test cho evaluator (`tests/test_run_business_evaluation.py`, 30 test)
- ❌ Case xác nhận forecasting BỊ CHẶN (chưa có case nào chủ động test "hỏi dự báo → bị từ chối
  đúng cách", chỉ có kiểm tra "từ dự báo không lọt vào câu trả lời")
- ❌ Xác nhận không hardcode đường dẫn máy 24 (chưa rà)

### 19.2 Metadata từng case (BusinessCase hiện chỉ có: id, group, audience, question, checker_id, pass_rule)
- ❌ `expected_tool` — cố tình để trống (đã ghi rõ lý do: đoán rủi ro hơn để trống)
- ❌ `expected_period`
- ❌ `expected_scope`
- ❌ `required_numbers` (khác `sai_so_lieu` hiện tại — đó là đối chiếu TOÀN BỘ số trong ground truth,
  không phải danh sách số bắt buộc riêng cho từng case)
- ❌ `forbidden_numbers`
- ❌ `required_warning`
- ❌ `max_rounds` / `timeout` riêng từng case

### 19.3 Gọi API thật (HTTP, không gọi thẳng hàm) 🔒
- ❌ Đăng nhập bằng API
- ❌ Tạo session qua endpoint thật
- ❌ Gọi `/chat` hoặc `/chat/stream` production-like
- ❌ Thu streaming response
- ❌ Lưu HTTP status code
- Lý do treo: đổi cách gọi + chạy thử tốn API thật — nên làm SAU khi ngân sách phục hồi, làm trước
  sẽ không kiểm chứng được ngay.

### 19.4 Thu trace đầy đủ mỗi case
- ✅ Tool đã gọi, chi phí, thời gian phản hồi, câu trả lời cuối, error
- ❌ Tham số tool đã gọi (chỉ có tên tool, không có args)
- ❌ SQL thật (có trong `audit_log.jsonl` riêng, nhưng KHÔNG được gộp vào file kết quả JSON của
  từng case — phải tra chéo bằng session_id như đã làm thủ công hôm nay)
- ❌ Số dòng kết quả, số vòng tool đã dùng, số token
- ❌ Footer freshness có được gắn đúng không

### 19.5 Máy chấm deterministic — 4/10 chiều
- ✅ Lỗi hệ thống, từ chối "quá phức tạp", từ dự báo lọt câu trả lời, có gọi tool
- ✅ Số đúng (checker gọn) — MỚI nới thêm dung sai làm tròn hôm nay
- ❌ Có số CẤM xuất hiện không (forbidden_numbers - phụ thuộc 19.2)
- ❌ Có đúng KỲ báo cáo không
- ❌ Có đúng VÙNG/scope người dùng không
- ❌ Có đúng TIMESTAMP dữ liệu không
- ❌ Có lộ bảng trung gian ra ngoài không
- ❌ Có SQL write keyword không (chặn ở tầng thực thi `query_engine.py::_FORBIDDEN`, nhưng evaluator
  không tự kiểm tra lại độc lập)

### 19.6 Báo cáo
- ✅ JSON + Markdown, tỷ lệ PASS theo domain, latency/chi phí từng câu
- ⚠️ P0/P1/P2 — mới có P0 + P2 (hôm nay thêm `hoi_lai_hoac_giai_thich`), CHƯA phải 3 mức đúng nghĩa
  mức độ nghiệp vụ (vd sai số tiền vs thiếu tool nhưng tình cờ đúng)
- ❌ Top lỗi phổ biến (chưa tổng hợp thống kê theo loại lỗi xuyên suốt các lần chạy)

---

## Ngày 20 — doanh thu, khách hàng, sản phẩm, KPI

### Doanh thu
- ✅ Khóa nguồn vHoaDonTotal/vHoaDonETCTotal, bao gồm hoàn/điều chỉnh, không cộng trùng 2 kênh
  (vá hôm nay), không cộng chồng tầng nhân sự, đếm hóa đơn cấp hóa đơn
- ✅ Ngày không doanh thu = 0 (xác nhận `employee_daily_kpi` điền lịch đúng)
- ❌ Tổng vùng bằng tổng công ty — CHƯA có test đối chiếu
- ❌ Tổng kênh bằng tổng công ty — CHƯA có test đối chiếu
- ⚠️ Branch/distributor/channel — phát hiện `DistributorCode` trong `vHoaDonTotal` là cột suy biến
  (chỉ 2 giá trị toàn hệ thống), CHƯA quyết định hướng xử lý (báo cho DNH hay bỏ hẳn khái niệm
  "nhà phân phối" khỏi phạm vi trả lời được)

### Khách hàng và sản phẩm — ✅ phần có tool cố định đã xong (19/08, 4 test)
- ✅ Top khách đúng kỳ — `top_customers()`, đã test xếp hạng đúng theo doanh thu
- ✅ Khách thiếu danh mục vẫn giữ trong tổng — LEFT JOIN đã tài liệu hoá kỹ (chưa viết test riêng
  cho case này cụ thể, nhưng cơ chế đã xác nhận qua đọc code)
- ✅ Tách đúng theo kênh OTC/ETC/ALL — `top_products()`, đã test
- ✅ Loại hàng tặng khi tính SL bán thật (`unit_price>0`) nhưng vẫn tính đủ doanh thu — đã test,
  không tìm lỗi mới
- ⚠️ **Cặp sản phẩm cấp đơn (cross-sell, Q034), nhóm sản phẩm (Q033), revenue concentration (Q029)
  — KHÔNG có tool cố định**, chỉ trả lời được qua SQL tự do (`query_database`). Không kiểm được
  bằng phương pháp Python-function-test đã dùng cả ngày hôm nay — cần rà `schema_context.py`
  (hướng dẫn cho model viết SQL) giống cách đã làm buổi sáng cho Q016/Q012/Q044, không phải viết
  test cho hàm Python vì không có hàm nào để test.

### KPI và đội ngũ
- ✅ MAX(SaveDate)<=ngày hỏi, Đội xác định bằng ManagerCode, không dùng zone suy luận cũ,
  mapping EmpDMSCode↔DMSId, phân biệt 65/70/80/100%, KPI ngày và KPI tháng khác ngưỡng
- ✅ Xử lý duplicate (rất kỹ) — resigned xác nhận không cần lọc thêm ở KPI (fact table theo hoạt động)
- ❌ Gộp một dòng/nhân viên trước khi cộng — CHƯA có test riêng xác nhận không double-count khi 1
  nhân viên có nhiều dòng khách hàng trong cùng snapshot
- ❌ Target không nhân theo khách — CHƯA có test riêng (dùng MAX(month_sale_target) đúng theo code,
  nhưng chưa test case cụ thể chứng minh không bị SUM nhân bản theo số dòng khách)

---

## Ngày 21 — công nợ, lương thưởng, CTKM

### Công nợ
- ✅ Snapshot từ SP chuẩn, 4 bucket = tổng quá hạn, tách OTC/ETC, tách vùng, khách 2 kênh không
  cộng sai, top nợ đúng mẫu số (5 test mới hôm nay), không dùng nguồn Excel/Supabase cũ
- ⚠️ Cảnh báo snapshot cũ (>6h) — có code (`receivable_warning`) nhưng CHƯA có test
- ❌ Khách thiếu mã/vùng phải cảnh báo — `receivables_overview()` KHÔNG có `_warn()` cho trường hợp
  này (case Q047 DEBT_MISSING_DIMENSIONS có checker riêng nhưng là cho SQL tự do, không phải tool
  cố định)

### Lương thưởng — ✅ XONG (19/08, 14 test, 2 lỗi thật tìm được và vá)
- ✅ Chỉ dùng kỳ lương đã chốt (`_closed_salary_date_filter`, đã có từ trước + test)
- ✅ V15/V22/V25 từ fact + policy (`salary_detail`, `salary_bonus_policy`) — đọc kỹ, không thấy lỗi,
  code đã qua nhiều lần vá thật (03/08 phân quyền QLV, 28/07 dòng khởi tạo đầu tháng)
- ✅ ASO đọc đủ điều kiện pass/fail — có trong `salary_bonus_policy`, đã test
- ✅ Ca "V25 đạt bậc nhưng V25Bonus lưu = 0" — có sẵn trong `salary_bonus_policy`, đã test khớp
  đúng case Q072 SALARY_V25_MISMATCH
- ✅ Phân biệt thưởng và phụ cấp — `total_bonus` không gộp `allowance`, đã test
- ✅ Không kết luận tổng thu nhập khi thiếu lương cơ bản — cảnh báo LCB có sẵn, đã test
- ✅ Bắt buộc gọi policy tool khi hỏi cách tính — nằm ở tầng prompt (mô tả tool), không kiểm ở đây
- 🔴 **2 lỗi thật tìm được và vá**:
  1. **Rò rỉ bảo mật**: `get_salary_ranking` thiếu đăng ký trong `_PERSON_LEVEL_TEMPLATES`, khiến
     QLV thấy thưởng cá nhân TOÀN CÔNG TY, không giới hạn theo đội. Xác nhận bằng git-stash (commit
     `795e7b8`).
  2. **Lỗi định dạng mã**: `salary_achievement_summary` lọc nhầm DMSId lên cột EmployeeCode của
     bảng lương → QLV luôn nhận "không có dữ liệu" dù đội có dữ liệu thật (commit `7d2427b`).

### Khuyến mãi (CTKM) — ✅ XONG (19/08, 6 test, không tìm lỗi mới)
- ✅ Chuỗi DMS_CTKM → DMS_DonHangCTKM → DMS_DonHangHdr → hóa đơn qua DMSId — đúng theo code
- ✅ Distinct đơn, distinct khách — đúng theo code
- ✅ Phân biệt sản phẩm điều kiện và quà tặng — 2 CTE riêng biệt, đã test
- ✅ Đơn dùng nhiều CTKM không được cộng ngang revenue — cảnh báo có sẵn trong `interpretation_note`
- ✅ Nêu đơn chưa tìm thấy hóa đơn tương ứng — trường `orders_without_invoice`, đã test
- ✅ Nêu ngày coverage cuối cùng của chuỗi liên kết — `promotion_link_coverage_to`, đã test kỹ 2
  tình huống (hỏi vượt tương lai so với coverage → `source_gap`; không chỉ định kỳ → tự chọn tháng
  đầy đủ gần nhất)
- ✅ Không gọi doanh thu gắn với chương trình là "ROI" — xác nhận bằng test, chỉ có đúng 1 câu cảnh
  báo "chưa đủ cơ sở kết luận ROI"

---

## Ngày 22 — planner cho câu hỏi 8-10 bước 🔒

Đây là **tính năng kiến trúc mới**, không phải rà lỗi có sẵn — khác hẳn bản chất công việc Ngày
19-21. Phần lõi (planner tạo/theo dõi kế hoạch nhiều bước, trả lời từng phần khi thiếu dữ liệu)
**bắt buộc cần gọi chatbot thật** để kiểm chứng đúng/sai — không mô phỏng bằng test giả được vì
bản chất câu hỏi phức tạp nằm ở việc MODEL tự lập kế hoạch, không phải logic tool cố định.

- ❌ `QueryPlan` có cấu trúc (plan_id, metrics, period, scope, steps, dependencies, status, sources,
  reconciliation_rules) — CHƯA tồn tại dưới bất kỳ hình thức nào trong code hiện tại
- ❌ Trạng thái từng bước (pending/running/completed/partial/failed/skipped)
- ✅ Giới hạn vòng theo CẤP VAI TRÒ (19/08, thay vì hằng số phẳng): `qlv=5` (kèm "Trưởng kênh" MT),
  `regional_director=8` (TP = Giám đốc Miền = Giám đốc Kênh), `c_level`/`admin_ops=10`. Vai trò
  không xác định fallback về `DEFAULT_MAX_TOOL_ROUNDS=6` (mức hằng số cũ chốt 17/08). Đính chính:
  code TRƯỚC khi sửa là `MAX_TOOL_ROUNDS=6` (không phải 4 như bản backlog gốc ghi nhầm — giá trị 4
  chỉ là 1 mốc lịch sử 04/08, đã bị nâng lại nhiều lần). 4 test mới (`test_business_composite_tools.py`),
  xác nhận đúng số lần gọi model cho cả 4 vai trò bằng client giả luôn trả về tool_use.
- ✅ Tối đa 5 tool/vòng (`MAX_TOOLS_PER_ROUND=5`, đã có từ 10/08)
- ❌ Không gọi lại cùng tool/cùng tham số trong 1 phiên (chưa có cơ chế phát hiện)
- ❌ Timeout riêng từng tool / tổng timeout request (chưa rà — SQL Server có `STATEMENT_TIMEOUT_SEC`,
  nhưng tool cố định/toàn request thì chưa)
- ❌ Reconcile tự động (tổng vùng=tổng công ty, tổng kênh=tổng công ty, tổng đội=tổng nhân viên,
  tổng tuổi nợ=tổng quá hạn, CTKM không cộng chồng, total bonus không nhập phụ cấp) — không có
  bước reconcile CHUNG nào chạy trước khi trả lời, mỗi tool tự đúng trong phạm vi riêng của nó
- ❌ Partial answer có cấu trúc (nêu phần đã kiểm chứng / bảng thiếu / bước thất bại, không suy đoán
  số, không nói chung chung "quá phức tạp") — hiện chỉ có 2 lựa chọn nhị phân: trả lời đầy đủ hoặc
  từ chối, chưa có dạng "trả lời một phần + nêu rõ phần còn thiếu"
- ❌ 10 câu complex mẫu (doanh thu+KPI+công nợ, CTKM+khách+sản phẩm, đối chiếu warehouse/live...)
  — chưa soạn, cần soạn xong TRƯỚC khi có thể tự động kiểm bất cứ gì ở Ngày 22

---

## Tổng hợp mức độ sẵn sàng (ước lượng thô theo số bullet, không phải % chính xác)

| Ngày | Tổng bullet (ước) | ✅ Xong | ⚠️ Một phần | ❌ Chưa làm | 🔒 Cần API thật |
|---|---:|---:|---:|---:|---:|
| 19 | ~30 | 9 | 1 | 15 | 5 |
| 20 | ~25 | 13 | 2 | 10 | 0 |
| 21 | ~25 | 8 | 2 | 15 | 0 |
| 22 | ~14 | 1 | 1 | 12 | phần lõi cần API |

**Đọc đúng cách**: cột 🔒 KHÔNG nghĩa là "chặn hoàn toàn tới 1/9" — chỉ phần XÁC MINH cuối cùng
qua chatbot thật mới cần API. Phần thiết kế/viết code/test giả lập (như đã làm suốt hôm nay) vẫn
làm được ngay cho phần lớn Ngày 20-21 còn lại, và một phần kha khá của Ngày 22 (khung `QueryPlan`,
giới hạn vòng/timeout, cấu trúc partial-answer) — chỉ RIÊNG việc "10 câu complex có được trả lời
đúng không" mới thật sự cần model thật.

## Đề xuất thứ tự làm tiếp (không cần API)

1. **Lương thưởng** (Ngày 21) — rủi ro cao nhất theo đánh giá gốc, hoàn toàn chưa động tới, ảnh hưởng
   trực tiếp tới tiền lương người thật nếu sai.
2. **CTKM** (Ngày 21) — cùng mức rủi ro, cùng chưa động tới.
3. **Khách hàng/Sản phẩm** (Ngày 20) — khối lượng bullet còn lại nhiều nhất.
4. **Khung `QueryPlan` cơ bản** (Ngày 22) — chỉ phần cấu trúc/giới hạn, để sẵn sàng cắm API vào
   ngay khi ngân sách phục hồi, không phải đợi rồi mới bắt đầu thiết kế.
