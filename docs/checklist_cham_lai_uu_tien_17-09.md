# Checklist chấm lại ưu tiên — 17/09/2026

Nguồn: đối chiếu router `_required_tool_for_question` phiên bản `f692e45` (mốc sổ 11/09) với phiên
bản hiện tại `bd0991f` (đã gộp PR #14–#20), cộng đối chiếu commit log cùng khoảng. Toàn bộ việc này
chạy cục bộ, không gọi API model trả phí.

**Phạm vi tài liệu này:** 18/138 câu — những câu (a) trước đây CHƯA ĐẠT hoặc CHỜ KIỂM theo sổ
11/09, VÀ (b) nay được định tuyến vào một tool đã sửa lỗi cụ thể từ 15–16/09. Đây là tập có khả
năng chuyển ĐẠT cao nhất, nên ưu tiên chấm trước trong ngân sách hôm nay.

**Không nằm trong tài liệu này** (nhưng vẫn cần retest theo quy tắc kế hoạch 11–20/09): 22 câu
trước ĐẠT nhưng route qua tool đã đổi (C01, C05, C06, C07, C10, C21–C24, C27, C35, M01, M03, M04,
M07, M10, M29, V01, V07, V08, V13, V27) — kiểm hồi quy, không cấp bách bằng.

**Quan trọng — số liệu trong tài liệu này đo trên kho local của tôi lúc sửa (16/09), KHÔNG PHẢI
kho production máy 24.** Lịch sử/thời điểm đồng bộ khác nhau nên số tuyệt đối sẽ khác. Số ở đây
chỉ để chứng minh CƠ CHẾ đã đúng (không còn cắt dữ liệu, không còn crash, gán đúng người phụ
trách...); người chấm phải lấy số thật trên máy 24 làm căn cứ ĐẠT/CHƯA ĐẠT.

---

## Cụm A — Công nợ (6 câu): top N bị cắt, thiếu người phụ trách

| Mã | Tài khoản | Checker | Trạng thái 11/09 | Lý do cũ |
|---|---|---|---|---|
| C37 | C-Level | S25 | CHƯA ĐẠT | "sai checker do check local" |
| C38 | C-Level | S45 | CHƯA ĐẠT | "SQL trả về không đúng trọng tâm" |
| C40 | C-Level | S24 | CHƯA ĐẠT | "sai checker do check local" |
| M37 | GĐ miền/kênh | S25 | CHƯA ĐẠT | "bảng fact_congno_khachhang là bảng local, không test" |
| V35 | QLV | S25 | CHƯA ĐẠT | "bảng fact_congno_khachhang là bảng local, không test" |
| V36 | QLV | S26 | CHƯA ĐẠT | "cùng S26 — dùng bản tháng tròn 11/09, lọc đúng đội" |

**Đã sửa (PR #18, #20, commit `4847cb2`, `743a90a`, `34f9dca`):**
- Top N không còn bị cắt: hỏi top 10 nay trả đủ 10, kèm `top_overdue_requested_count` /
  `top_overdue_eligible_count` / `top_overdue_returned_count` để model không tự rút gọn.
- Mỗi khách nợ quá hạn kèm `employee_code`/`employee_name`/`manager_code`/`manager_name` (TDV/QLV
  phụ trách), lấy từ snapshot KPI gần nhất.
- Danh sách "dư nợ lớn chưa quá hạn" (`du_no_lon_chua_qua_han`) nay LUÔN được gửi cho model, không
  còn phụ thuộc từ khóa trong câu hỏi.
- QLV/GĐ miền: công nợ được lọc đúng phạm vi đội/vùng (PR #13, `4847cb2`).

**Đối chiếu trên kho local của tôi (16/09):** OTC top 10/2.127 khách đủ điều kiện, ETC top
10/4.944 khách; ví dụ khách `HCM04162` (dư nợ 2.914.915.581, chưa quá hạn) xuất hiện đúng trong
`du_no_lon_chua_qua_han` thay vì bị coi là "không có nợ".

**Cách chấm lại:** hỏi lại đúng câu C37/C38/C40 (C-Level), M37 (GĐ miền), V35/V36 (QLV) trên tài
khoản tương ứng; đối chiếu checker S24/S25/S26/S45 đã map. C39 xem riêng ở Cụm D vì có ghi chú số
cụ thể từ trước.

---

## Cụm B — ETC hợp đồng (3 câu): giá trị trước VAT, lọc bản ghi hỏng

| Mã | Tài khoản | Checker | Trạng thái 11/09 | Lý do cũ |
|---|---|---|---|---|
| C43 | C-Level | S29 | CHƯA ĐẠT | "không đưa ra câu trả lời do không có dữ liệu" |
| C44 | C-Level | S86 | CHƯA ĐẠT | "SQL trả về không đúng trọng tâm" |
| M42 | GĐ miền/kênh | S86 | CHƯA ĐẠT | "chưa có khóa liên kết chính thức hóa đơn — hợp đồng/gói thầu" |

**Đã sửa (commit `720c726`):** giá trị hợp đồng chuyển sang `SUM(AmountBefVat)` (trước VAT, đồng
nhất hai vế phép chia tỷ lệ thực hiện); quy tắc phát hiện bản ghi hỏng đổi thành
`ABS(AmountBefVat - Quantity*UnitPrice) > 5% HOẶC UnitPrice > 1 tỷ HOẶC ABS(AmountAfterVat -
AmountBefVat) > 50%` — bắt được HĐ 115627 mà quy tắc cũ bỏ sót; số hợp đồng hỏng bị tách ra khỏi
tổng giảm từ 70 xuống 60.

**Định tuyến đổi (16/09):** C44 và M42 trước đây rơi vào `get_geography_monthly_performance` (chỉ
có doanh thu thực hiện, không có giá trị hợp đồng/còn lại/hạn) — đúng nguyên nhân "SQL trả về
không đúng trọng tâm" trong sổ 11/09. Nay route thẳng vào `get_etc_contract_status`.

**Lưu ý cho người chấm — C43 KHÔNG cùng loại với C44/M42:** C43 hỏi "kế hoạch thầu, giá trị tham
gia, giá trị TRÚNG, tỷ lệ TRÚNG thầu" — đây là dữ liệu đấu thầu (tham gia thầu nhưng có thể trượt),
khác với "thực hiện hợp đồng đã ký" mà `get_etc_contract_status` đang mô hình hóa. Router hiện
KHÔNG đưa C43 vào tool này (đúng, không phải bug định tuyến) vì tool chưa có khái niệm "trượt
thầu". Nếu dữ liệu bidding không tồn tại trong Bravo, C43 nên xếp diện "ĐẠT — giới hạn nguồn đã
xác nhận" chứ không phải "chờ sửa thêm" — cần DNH xác nhận Bravo có lưu lịch sử đấu thầu (thắng/
trượt) hay chỉ có hợp đồng đã ký.

**Cách chấm lại:** C43/C44 trên C-Level (kênh ETC), M42 trên GĐ kênh ETC.

---

## Cụm C — Doanh thu theo tháng (3 câu): C02/S02 loop-leak, không còn crash khi thiếu tham số

| Mã | Tài khoản | Checker | Trạng thái 11/09 | Lý do cũ |
|---|---|---|---|---|
| C02 | C-Level | S02 | CHỜ KIỂM | "% đạt target của miền Nam bị lệch, MB và MT đều đúng" |
| C08 | C-Level | S80 | CHỜ KIỂM | "SQL trả về không đúng trọng tâm" |
| C03 | C-Level | S79 | CHỜ KIỂM | "không khớp dữ liệu, cần xem lại cả chatbot và query SQL" |

**Đã sửa:**
- `revenue_by_region`/`revenue_monthly_series` (PR #14, commit `bb5dc4d`, `9ebab9b`): biến vòng lặp
  bị rò (mọi tháng dùng nhầm khoảng ngày của `month_to`) khiến % kế hoạch miền Nam sai lệch có hệ
  thống — đã tách đúng khoảng ngày từng tháng; không còn crash khi thiếu bảng vùng.
- `revenue_ytd_cumulative` (commit `34f9dca`, 16/09): thiếu `year_month_to` trước đây ném
  `TypeError` → người dùng thấy "Lỗi khi chạy báo cáo chuẩn"; nay mặc định về tháng dữ liệu gần
  nhất, chỉ báo lỗi khi tham số sai định dạng.

**Đối chiếu đã làm trong đợt sửa PR #14:** xác nhận số C02/S02 giữ nguyên đúng ở các tháng trước
đó vốn đã đúng, chỉ sửa đúng phần sai (không làm hỏng phần đang chạy tốt).

**Cách chấm lại:** C02, C03, C08 trên C-Level — kiểm riêng % kế hoạch miền Nam của C02 vì đó là
lỗi cụ thể đã sửa.

---

## Cụm D — Tồn kho, khách hàng vòng đời, mapping nhân sự (5 câu)

| Mã | Tài khoản | Checker | Trạng thái 11/09 | Lý do cũ |
|---|---|---|---|---|
| M40 | GĐ miền/kênh | S28 | CHỜ KIỂM | (chờ kiểm, chưa ghi lý do cụ thể) |
| C39 | — | S26 | CHỜ KIỂM | "S26 bản 10/09 so 4 ngày T9 với cả T8 (2.575 khách/36,5 tỷ); đúng là T8 so T7 đủ tháng: 1.647 khách/20,3 tỷ (nợ snapshot 04/09)" |
| M27 | GĐ miền/kênh | S53 | CHỜ KIỂM | ghi "Khớp dữ liệu" nhưng chưa chốt |
| V17 | QLV | S38 | CHỜ KIỂM | "chốt đạt trước khi S38 có lọc đội (10/09) — chấm lại với @ManagerCode đúng đội" |
| V37 | QLV | S45 | CHỜ KIỂM | "chat trả lời không có dữ liệu để trả lời, cần confirm" |

**Đã sửa:**
- **M40**: định tuyến đổi từ `get_operational_data_quality` sang `get_inventory_expiry_report` —
  đúng nhóm câu hỏi "hàng cận date/chậm luân chuyển" thay vì báo cáo chất lượng dữ liệu chung.
- **C39**: chưa sửa thêm trong đợt này, nhưng route qua `get_receivables_overview` đã có sẵn ghi
  chú số đúng từ 10/09 (T8 so T7: 1.647 khách/20,3 tỷ, snapshot nợ 04/09) — chỉ cần chấm lại trên
  máy 24 với snapshot mới nhất, không cần sửa code thêm.
- **V17**: `manager_code`/`scope_employee_code` đã được truyền xuyên suốt các tool danh sách/KPI từ
  PR #17 (`2954886`) — QLV hỏi về đội mình không còn bị lẫn với toàn công ty.

**Cách chấm lại:** M40 trên GĐ miền/kênh; C39 không cần tài khoản cụ thể (đã ghi "—" trong sổ,
kiểm lại theo checker S26); M27 trên GĐ miền/kênh; V17, V37 trên QLV `thuy.nguyen`
(Nguyễn Thị Hồng Thúy, TM25010183, MB) — đúng tài khoản đối chứng đã chốt trong kế hoạch, không
nhầm với Nguyễn Thị Thanh Thủy.

---

## Việc cần anh Đăng làm (tôi không tự chạy được)

1. **Duyệt ngân sách gọi API cho đúng 18 câu này hôm nay.** Đây là việc duy nhất chặn đường — tôi
   đã xác định chính xác câu nào cần chấm và vì sao, nhưng không được tự gọi `nl2sql.ask`.
2. Khi chấm xong, báo tôi câu nào vẫn chưa đạt kèm câu trả lời thật của chatbot — tôi đối chiếu
   tiếp với code để biết còn sai chỗ nào hay chỉ là dữ liệu máy 24 khác kho tôi kiểm.
3. Riêng **C43**: cần anh hoặc DNH xác nhận Bravo có bảng lịch sử đấu thầu (tham gia/trúng/trượt)
   hay không — quyết định câu này là "ĐẠT — giới hạn nguồn" hay "cần thêm tool mới".
