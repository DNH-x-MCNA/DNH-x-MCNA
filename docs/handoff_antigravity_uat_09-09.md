# Handoff Antigravity — vá UAT còn lại ngày 09/09/2026

## Mục tiêu

Sửa lỗi đã có bằng chứng từ UAT thật mà không làm sai số liệu, không nới quyền và
không sửa checker cho khớp chatbot. Mỗi cụm chỉ hoàn tất khi có test đơn vị, đối
chiếu dữ liệu thật miễn phí và retest UI đúng tài khoản.

## Ràng buộc không được vi phạm

- Baseline gần nhất: `29da152`; bộ test backend đã từng đạt **516 passed, 1 deselected**.
- Các thư mục `.pytest-*` và `outputs/*` chưa theo dõi là output cục bộ. Không xóa,
  không thêm vào commit.
- Không chạy `business_eval`, không tạo Scheduled Task, không chạy lại 138 câu hay
  gọi chatbot hàng loạt khi chưa được cấp ngân sách. Tác vụ `DNH_Eval90_0828d` đã bị
  vô hiệu hóa.
- Không sửa `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md` để làm chatbot khớp.
  Checker chỉ đổi khi Bravo chứng minh checker sai.
- Không dùng `git add -A`; mỗi commit chỉ stage file vừa sửa.
- Gom mọi thay đổi prompt/tool description trong `backend/nl2sql.py` vào **một deploy**.
- Máy 24 chỉ restart service `DNH_Chatbot_Backend`, không chạy supervisor thủ công.

## Tài khoản UAT đúng

| Nhóm | Tài khoản/phạm vi đúng | Quy tắc |
|---|---|---|
| C01–C54 | C-Level | Xem toàn công ty, nhưng vẫn phải từ chối đúng khi thiếu nguồn. |
| M01–M44 | `thuy.nguyen2`, `regional_director`, MB | Toàn bộ nhóm M phải test bằng tài khoản này. |
| V01–V32 | `tu.pham`, QLV, đội MBKV2 | Chỉ dữ liệu đội MBKV2. |
| V33–V40 | `thuy.nguyen`, QLV, đội TM25010183 | Chỉ dữ liệu đội TM25010183. |

**Sai quy trình hiện có:** M02, M05, M10–M19 (trừ M11/M15/M16/M20 đã có lần test
đúng), M21–M44 đa số chạy dưới QLV. Những ghi chú đó chỉ để retest; không dùng làm
bằng chứng sửa code cho nhóm M.

---

## Cụm A — M16 / S55: nhiều nhân viên giảm liên tiếp nhưng chatbot nêu một người

### Bằng chứng

M16 hỏi nhân viên giảm doanh số liên tiếp 3 tháng và nguyên nhân. S55 có nhiều nhân
viên phù hợp. Chatbot chọn Đỗ Văn Trịnh (`TM25010167`) rồi gọi đây là “1 trường hợp
rõ ràng nhất” và “nguyên nhân duy nhất”. Đây là lỗi đầy đủ danh sách và suy diễn.

### Sửa ở đâu

#### `backend/report_templates.py::workforce_productivity()`

1. Khi `group_by="employee"`, giữ tập `rows` đầy đủ **trước** `_giu_top_don_vi()`.
2. Từ dòng tháng cuối của mỗi nhân viên tạo các field riêng:
   - `declining_employee_count`
   - `declining_employees`
   - `declining_employees_truncated`
   - `declining_employees_not_shown`
3. Mỗi dòng tối thiểu gồm `employee_code`, tên, tháng, `decline_streak_months`,
   `actual`, `previous_actual`, `mom_delta`, `mom_pct`.
4. Lọc streak `>= 2`, sắp xếp ổn định: streak giảm dần, mức giảm tuyệt đối giảm dần,
   rồi mã nhân viên.
5. Tổng đếm/danh sách giảm phải tính từ tập đầy đủ, không bị giới hạn top theo doanh
   số làm rơi mất người đang giảm.

#### Nguyên nhân mất khách/tần suất/AOV

- Hàm hiện chỉ có KPI/doanh số. Không có payload khách, đơn hay AOV theo từng NV thì
  chatbot phải nói **chưa đủ dữ liệu kết luận nguyên nhân**.
- Nếu bổ sung phân rã nguyên nhân: map DMSId sang mã nhân viên qua `dim_nhanvien`,
  dùng một nguồn hóa đơn duy nhất và tính cho từng NV ở hai kỳ cùng độ dài: khách
  unique, đơn unique, AOV và delta. Nếu mapping không chắc, trả
  `cause_data_available=false`, không đoán.
- Không gắn nhãn “nguyên nhân duy nhất” nếu nhiều chỉ số cùng giảm.

#### `backend/nl2sql.py`

Mô tả `get_workforce_productivity` phải bắt buộc M16/V13 gọi:

```text
group_by="employee", months_back >= 4, limit=200
```

Và bắt buộc câu trả lời: nói tổng số từ `declining_employee_count`, liệt kê toàn bộ
hoặc Top N kèm số còn lại/Excel, chỉ dùng chữ “duy nhất” khi count = 1.

### Test bắt buộc

- Thêm fixture có ít nhất 3 NV giảm liên tiếp trong
  `tests/test_cat_danh_sach_chuoi_thang.py` hoặc test chuyên biệt.
- Assert count = 3, đủ ba mã trong `declining_employees`, kể cả khi `limit` hiển thị
  rows thấp hơn 3.
- Assert thứ tự deterministic, không trùng mã.
- Assert mô tả tool có quy tắc employee/4 tháng và cấm kết luận nguyên nhân khi thiếu
  payload.

### Retest UI

Đăng nhập `thuy.nguyen2`, hỏi nguyên văn M16. Đạt khi nêu tổng số người; không bỏ
người có trong S55; Đỗ Văn Trịnh chỉ là một dòng; “mất khách hoàn toàn” chỉ dùng nếu
khách và đơn của chính anh ấy về 0; không lộ dữ liệu ngoài MB/tool/JSON.

---

## Cụm B — C54 / S38: mã thiếu target bị lặp

### Bằng chứng

C54 nói 17 người thiếu target nhưng liệt kê `TM25031901` hai lần vì mã vừa thuộc
`missing_target` vừa thuộc tập con `missing_target_with_sales`. Số unique có thể đúng
nhưng bảng người dùng nhìn thấy bị tự mâu thuẫn.

### Sửa ở đâu

Trong `backend/report_templates.py::operational_data_quality()`:

1. Giữ `missing_target_with_sales` là tập con cho thống kê, nhưng tạo một list hiển
   thị `missing_target_details` duy nhất: mỗi mã một dòng, có cờ
   `has_sales_without_target`.
2. Dedupe từ tập `missing_target`, thứ tự mã ổn định. Tổng là số unique, số ưu tiên là
   count riêng tập con, không cộng thêm vào tổng.
3. Giữ `employee_tier_employees` tách `management_rows_without_parent_in_source`.
   Không gọi QLV không có cha là nhân viên thiếu manager.
4. `snapshot_is_closed=false` chỉ là chưa chốt, không được tự nói “bình thường đầu
   tháng” hay “DNH chưa nhập kịp”.

Trong mô tả/prompt, dùng list cấu trúc trên thay cho hai list độc lập. Không dựa vào
việc model tự nhớ không được lặp mã.

### Test và retest

- Bổ sung test trong `tests/test_management_rounds_remaining.py`: một mã vừa thiếu
  target vừa có doanh số chỉ xuất hiện một lần, có cờ ưu tiên.
- Assert tổng unique, số ưu tiên và mẫu số employee tier.
- C-Level hỏi C54, snapshot 31/08: tổng phải khớp số mã unique, list không lặp; mã có
  doanh số không target chỉ được gắn cờ; 31/08 là snapshot chốt, không bị thay bằng
  freshness 09/09.

---

## Cụm C — V06 / S07: doanh thu, đơn, AOV và tần suất đội

### Bằng chứng

V06 lệch doanh thu/số đơn tháng 7 và 8. Rủi ro chính là chatbot ghép doanh thu từ
snapshot KPI với số đơn/AOV từ hóa đơn, hoặc đếm line hóa đơn thay vì đơn.

### Đường code

- Route đội có khách/đơn/AOV vào `get_customer_product_coverage(mode="employee")`.
- Hàm: `backend/report_templates.py::customer_product_coverage()`.

### Yêu cầu sửa

1. Mọi chỉ số tổng trong cùng bảng phải lấy từ `scope_totals` của **một tập hóa đơn**:
   doanh thu, đơn, khách, AOV, đơn/khách.
2. Số đơn = `COUNT(DISTINCT order_key)` sau khi gom line đơn. AOV = doanh thu tập đơn
   / số đơn. Tần suất = số đơn / khách distinct trên toàn đội.
3. Nếu `team_scope_invoice_reconciliation_warning` có mặt, chatbot tách nguồn và nói
   không thể ghép thành một bảng khớp. Không được âm thầm chọn số đẹp.
4. Kỳ giữa tháng phải cùng độ dài: 01–N tháng này so 01–N tháng trước, đồng thời ghi
   MTD.

### Test và retest

- Fixture có 2 line cùng `order_key`, 2 TDV cùng 1 khách và 1 NV không bán. Assert
  order không bị đếm đôi, khách đội là distinct toàn đội, tổng rows trước cắt khớp
  `scope_totals`, AOV/tần suất đúng.
- Retest V06 bằng `tu.pham`. Đối chiếu cả doanh thu và số đơn T7/T8 với S07/Bravo,
  không chỉ kiểm phần trăm.

---

## Cụm D — V07 / S05: “tháng này” không được tự đổi thành tháng 8

### Bằng chứng

Câu hỏi dùng “tháng này” trong tháng 9 nhưng chatbot gọi tháng 8 là tháng này, đồng
thời số đơn/doanh thu lệch.

### Đường code và yêu cầu

- Route: `get_geography_monthly_performance`.
- Khi hỏi “tháng này”, giữ tháng dữ liệu mới nhất. Nếu kỳ dở, phải ghi MTD đến ngày
  nào và không so MTD với cả tháng trước.
- Nếu dùng tháng 8, gọi đúng là “tháng hoàn chỉnh gần nhất”, không gọi là tháng này.
- Có thể so 01–N với 01–N tháng trước hoặc nói chưa đủ căn cứ kết luận xu hướng đầy
  tháng. Không âm thầm đổi kỳ.
- S05 là DERIVED. Không gán một nguyên nhân khi DNH chưa chốt công thức phân rã; báo
  các chỉ số quan sát được trước.

### Test và retest

- Fixture có tháng partial; assert payload đánh dấu partial và không tự lùi tháng.
- Retest V07 bằng `tu.pham`; tháng hiển thị rõ ràng, totals đúng phạm vi đội MBKV2.

---

## Cụm E — V21 / S69: danh sách khách im lặng bị mất dòng

### Bằng chứng

Hai khách mã MBI có trong SQL nhưng chatbot không hiển thị. Cần tìm chính xác họ mất
ở tool payload, join sản phẩm, scope, hay giới hạn hiển thị.

### Các bước điều tra/sửa

1. Xác định route `get_customers_silent`; so ba tập: SQL S69, payload tool, bảng
   chatbot. Không sửa trước khi biết mất ở tầng nào.
2. Tool phải trả `total_count`, `returned_count`, `truncated`, `not_shown_count`.
   Không tăng limit vô điều kiện.
3. Mỗi khách có mã, tên nếu có, bucket im lặng, ngày mua cuối, giá trị gần nhất và SP
   thường mua. Thiếu sản phẩm phải trả `not_available`, không xóa khách.
4. Filter đội MBKV2 phải chạy trước khi đếm/cắt list.

### Test và retest

- Fixture có hai khách MBI và một khách không có sản phẩm. Assert đủ ba khách trong
  tập kết quả; chỉ field sản phẩm được unavailable.
- Retest V21 bằng `tu.pham`; nếu cắt màn hình, chatbot nêu tổng và Excel đầy đủ.

---

## Cụm F — chỉ thêm guard/trả đúng giới hạn: C30, C34, C44

Không “vá số” để câu có vẻ đầy đủ. Ba câu đạt UAT nếu trả phần có nguồn và ghi rõ
phần không chứng minh được.

### C30 / S19 — cohort retention

- `MIN(DocDate)` trong cửa sổ lịch sử không phải bằng chứng khách mua lần đầu đời;
  cohort đầu cửa sổ bị left-censoring.
- Chỉ tính 1/3/6/12 tháng cho cohort đủ tuổi; loại hoặc gắn nhãn cohort bị censored.
- Tách OTC/ETC/miền đúng phạm vi. Nêu rõ giới hạn lịch sử chi tiết 12 tháng.
- Cần DNH chốt “khách mới” là lần đầu trong đời hay lần đầu trong cửa sổ.

### C34 / S22 — sản phẩm mới

- Không gọi `MIN(DocDate)` của cửa sổ ngắn là ngày ra mắt. Đây là nguyên nhân lệch
  tháng phát hành.
- Không có master launch date/lịch sử đủ dài: dùng `first_observed_sale`, loại SKU ở
  đầu cửa sổ khỏi mốc 1/3/6/12 tháng.
- Không có target theo SKU: không suy diễn `%KH SKU`.

### C44 / S86 — hợp đồng ETC

- Ghép hóa đơn với hợp đồng qua khách + SKU không chứng minh doanh thu thuộc hợp đồng,
  có nguy cơ nhận nhầm/double count.
- Chưa có khóa hợp đồng trên invoice: chỉ báo thông tin hợp đồng, hiệu lực, giá trị
  nguồn đáng tin; không khẳng định tỷ lệ thực hiện/còn lại/nợ theo từng hợp đồng.
- Guard các giá trị hợp đồng bất thường lịch sử để không bóp méo tổng.

---

## Cụm G — retest trước, không sửa code trước

Các câu dưới đã có commit ở cột I hoặc bị thiếu nguồn. Retest trước; chỉ mở code nếu
retest tiếp tục sai.

| Nhóm | Câu | Cần kiểm |
|---|---|---|
| C-Level | C02, C03, C08, C11, C13, C20, C28, C42, C49, C54 | Kỳ, phạm vi, số chính và cách từ chối khi nguồn thiếu. |
| Manager | M02, M05, M10–M15, M17–M19, M21–M44 | Phải chạy `thuy.nguyen2`; kết quả QLV cũ vô hiệu để chấm M. |
| Manager đã xác minh một phần | M11, M15, M20 | M11/M15 kiểm số; M20 kiểm phân quyền không lộ lương. |
| QLV | V05, V10, V11, V15, V17, V18, V22–V26, V28–V32, V34, V37 | Kiểm đủ danh sách, phạm vi đội, không suy đoán. |

### M20 / S33 — không sửa quyền

`regional_director` không có quyền xem lương/thưởng cá nhân chi tiết. Đây là chủ ý
hai lớp: tool lương bị ẩn ở `nl2sql.py`, và `call_template()` chặn fail-closed trong
`report_templates.py`. M20 đạt nếu nêu giới hạn đó, vẫn trả KPI/doanh thu đội có bằng
chứng và không lộ V15/V22/V25/ASO/lương cá nhân. Không mở quyền chỉ để làm UAT đầy đủ.

---

## Trình tự triển khai

1. Chạy `git status --short`; chỉ xác nhận, không xóa output/cache.
2. Làm Cụm A, thêm test, chạy test mục tiêu.
3. Làm Cụm B, thêm test, chạy test mục tiêu.
4. Làm Cụm C rồi D, sau đó Cụm E. Mỗi cụm xanh mới chuyển cụm khác.
5. Với C30/C34/C44 chỉ thêm guard/giới hạn có bằng chứng.
6. Chạy đầy đủ trước khi commit cuối:

```powershell
python -m pytest tests/test_cat_danh_sach_chuoi_thang.py tests/test_management_rounds_remaining.py tests/test_business_composite_tools.py -q -p no:cacheprovider
python -m pytest tests -q -p no:cacheprovider
python scripts/doi_chieu_so_lieu_tool_moi.py
```

7. Commit theo cụm nguyên nhân, ví dụ `fix(uat): report all consecutive-decline employees`.
8. Khi tất cả commit/test xong mới deploy một lần: máy 24 fast-forward, restart service,
   kiểm health/commit/sync time. Không deploy lúc đồng nghiệp đang test.
9. Retest UI theo đúng tài khoản ở đầu tài liệu. Cột I ghi commit + ngày. Cột J chỉ ghi
   `Đạt` sau retest đúng vai trò và đối chiếu số.

## Definition of done cho một câu

Chỉ chuyển `Đạt` khi đủ năm điều kiện:

1. Số liệu/kỳ/phạm vi khớp Bravo hoặc đối chứng đáng tin.
2. Trả đúng trọng tâm, đủ danh sách hoặc nêu rõ số dòng đã cắt.
3. Không rò dữ liệu ngoài quyền.
4. Thiếu nguồn thì nêu phần thiếu cụ thể, không bịa số hay nguyên nhân.
5. Tiếng Việt dễ đọc, không tên tool, không JSON thô, không tự mâu thuẫn.
