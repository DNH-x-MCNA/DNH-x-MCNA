# Báo cáo tiến độ chốt phiên 09/09/2026

## Kết luận ngắn

Antigravity **chưa triển khai backend/test theo handoff**. Sau khi nhận tài liệu
`docs/handoff_antigravity_uat_09-09.md`, thay đổi duy nhất Antigravity để lại là một
diff chưa commit trong SQL checker S67/S40. Diff này chưa đủ cơ sở nhận vì có lỗi
định nghĩa retention, rủi ro sai phạm vi và một đề xuất ngưỡng chưa được DNH duyệt.

Trong phiên kiểm tra này, Codex đã làm thử phần M16/S55 ở local và test mục tiêu xanh,
nhưng phát hiện thêm bẫy tháng MTD. Theo yêu cầu dừng của người dùng, phần này **để
nguyên chưa commit, chưa push, chưa deploy** và chưa được tính là hoàn thành.

## Trạng thái Git tại lúc chốt

- `HEAD`: `dc90454` — tài liệu handoff UAT cho Antigravity.
- `origin/master`: `29da152`.
- Nhánh local đang ahead remote 1 commit tài liệu.
- Không có commit mới của Antigravity sau `dc90454`.
- Output/cache `.pytest-*`, `outputs/*` được giữ nguyên, không xóa và không stage.

### File tracked đang thay đổi nhưng chưa commit

| File | Người/phần việc | Trạng thái |
|---|---|---|
| `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md` | Antigravity | Sửa dở S67/S40; chưa được duyệt. |
| `backend/report_templates.py` | Codex | Bản sửa thử M16 summary; còn thiếu guard tháng MTD. |
| `backend/nl2sql.py` | Codex | Bổ sung hướng dẫn M16; chưa deploy. |
| `tests/test_cat_danh_sach_chuoi_thang.py` | Codex | Hai test M16 mới; test file đạt 12/12. |

Không được commit gộp bốn file trên trong một commit. Phần checker của Antigravity và
phần backend của Codex là hai phạm vi độc lập.

## Tiến độ UAT có thể khẳng định

- Số chốt gần nhất trên sheet theo hợp `Kết quả chạy` khớp dữ liệu hoặc cột `Chốt
  đánh giá`: **59/138 câu (42,8%)**. Đây là số đã ghi nhận, không phải ước lượng.
- M20/S33 đã được kiểm tra về quyền: Trưởng phòng/Giám đốc miền không có quyền xem
  lương/thưởng cá nhân chi tiết; lớp ẩn tool và lớp chặn thực thi vẫn còn. Có thể chốt
  đạt về phân quyền sau khi cập nhật sheet.
- M16/S55 chưa đạt: câu trả lời cũ chỉ nêu một người trong khi SQL có nhiều người.
- Phần lớn M02, M05, M10–M19 và M21–M44 đã test bằng QLV thay vì
  `thuy.nguyen2`/`regional_director`; không dùng các kết quả cũ đó để tính lỗi hay sửa code.
- Chưa có vòng retest đúng vai trò sau handoff, do đó chưa có căn cứ báo mốc >95%.

## Antigravity đã làm gì

Antigravity sửa 35 dòng/thêm và 11 dòng/xóa trong
`docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`:

1. S67: thêm `TK` vào tầng nhân viên và bổ sung khách do QLV bán trực tiếp nếu không
   tìm thấy ở tầng TDV.
2. S40: thêm ghi chú so sánh biến thể S40c và đề xuất dùng chu kỳ động hoặc hạ ngưỡng
   im lặng từ 45 xuống 30 ngày.

Không có thay đổi trong `backend/` hoặc `tests/` của Antigravity. Vì vậy các cụm
M16, C54, V06, V07, V21, C30, C34 và C44 trong handoff vẫn chưa được Antigravity xử lý.

## Vì sao chưa thể nhận diff checker của Antigravity

### S67 chưa đủ điều kiện READY

- Query không trả hai phần mà tiêu đề yêu cầu: khách tái kích hoạt và khách ngừng mua.
- `RepeatCustomers / PrevTotal` không phải retention. Retention đúng phải đo giao tập:
  khách hoạt động tháng trước vẫn hoạt động tháng này / khách hoạt động tháng trước.
- Nhánh QLV trực tiếp dùng `NOT EXISTS` theo customer + month trên toàn tập, không khóa
  cùng `AreaCode`/đội. Cùng mã khách xuất hiện ở TDV vùng khác có thể làm mất khách QLV
  của vùng đang xét.
- Join `DIM_NhanVien` chưa khử duplicate và dùng mapping hiện tại cho kỳ lịch sử; có
  nguy cơ nhân dòng hoặc gán lịch sử sang vùng hiện tại.

Kết luận: giữ diff để người sửa tiếp tục điều tra; không chốt số “khớp 100%” hoặc
`READY` dựa trên query hiện tại.

### S40 không được tự hạ ngưỡng

Hạ `SilentDays` từ 45 xuống 30 chưa có phê duyệt DNH và có thể tạo nhiều cảnh báo giả.
Chỉ nên giữ công thức chu kỳ động dựa trên lịch sử mua, hoặc chờ DNH chốt ngưỡng.

## Phần M16 Codex vừa làm thử

Đã bổ sung local:

- `declining_employee_count` và `declining_employees` tính trên toàn tập trước khi cắt
  Top N.
- Số người bị cắt, cờ dữ liệu nguyên nhân chưa sẵn sàng, và quy tắc không được gọi một
  người là “duy nhất” khi count > 1.
- Mô tả tool yêu cầu `group_by='employee'`, tối thiểu bốn tháng.
- Hai test mới chứng minh ba người giảm liên tiếp vẫn được giữ đủ dù `limit=1`.

Kết quả test mục tiêu:

```text
tests/test_cat_danh_sach_chuoi_thang.py: 12 passed
```

### Lý do chưa được coi là hoàn tất

`workforce_productivity()` mặc định dùng tháng dữ liệu mới nhất. Nếu tháng đó mới là
MTD, doanh số thấp có thể làm nhiều nhân viên bị gắn “giảm liên tiếp” giả. Trước khi
commit phải chọn một trong hai hành vi an toàn:

1. Chỉ tính streak đến tháng tròn gần nhất; hoặc
2. Giữ MTD nhưng đánh dấu kỳ partial và loại tháng partial khỏi phép xác nhận streak.

Ngoài ra payload hiện mới chứng minh doanh số giảm, chưa có khách/đơn/AOV theo từng
nhân viên. Chatbot chỉ được nói chưa đủ dữ liệu nguyên nhân; không được suy diễn mất
khách hay giảm tần suất.

## Trạng thái các cụm còn lại

| Cụm | Trạng thái lúc dừng | Việc còn lại |
|---|---|---|
| M16/S55 | Đang sửa local, test mục tiêu xanh nhưng thiếu guard MTD | Hoàn thiện kỳ partial, chạy full test, đối chiếu và retest UI. |
| C54/S38 | Chưa làm | Gộp danh sách thiếu target thành list unique, cờ riêng mã có doanh số. |
| V06/S07 | Chưa làm mới | Kiểm khóa đơn và thống nhất toàn bộ chỉ số từ một tập hóa đơn. |
| V07/S05 | Code cũ đã có cảnh báo partial | Retest UI/số thật; chỉ sửa nếu vẫn tự đổi “tháng này”. |
| V21/S69 | Chưa làm | Thêm tổng/returned/truncated; không làm rơi khách khi thiếu tên SP. |
| C30/S19 | Một phần từ code cũ | Chặn cohort bị left-censoring. |
| C34/S22 | Chưa làm | Không gọi first observed là ngày ra mắt; không suy target SKU. |
| C44/S86 | Chưa làm | Fail-closed khi thiếu khóa hợp đồng trên hóa đơn. |
| M20/S33 | Đạt về quyền | Chỉ cập nhật kết quả retest vào sheet; không nới quyền. |

## Thứ tự tiếp tục ở phiên sau

1. Đọc `docs/handoff_antigravity_uat_09-09.md` và báo cáo này.
2. Không đụng diff checker Antigravity cho đến khi chủ sở hữu chốt giữ/sửa/bỏ.
3. Hoàn thiện guard MTD của M16; chạy test mục tiêu và full backend.
4. Sửa C54 và V21 vì đây là lỗi danh sách có bằng chứng rõ.
5. Đối chiếu V06/V07 trên cùng tập hóa đơn trước khi thay đổi công thức.
6. Retest nhóm M bằng đúng `thuy.nguyen2`; không dùng kết quả QLV cũ.
7. Gom prompt/tool description và deploy một lần sau khi tất cả test xanh.

## Điều tuyệt đối chưa làm trong phiên này

- Không deploy máy 24.
- Không push remote.
- Không gọi API chatbot trả phí hoặc chạy business evaluation.
- Không cập nhật cột J cho câu chưa retest.
- Không xóa/revert thay đổi của Antigravity.
