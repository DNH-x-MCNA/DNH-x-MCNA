# Gửi người chấm UAT — cập nhật 10/09/2026

> ⛔ **ĐÃ BỊ THAY THẾ ngày 11/09/2026.** Mẫu số 119 trong tài liệu này KHÔNG còn dùng. Phạm vi chính thức là **126 câu** theo cột `TÍnh cần thiết của câu hỏi` trên sheet UAT (loại 9 câu dự báo/lợi nhuận: C04, C14, C15, C19, C50, C51, M39, M43, V09; tạm loại 3 câu: C25, C49, V16). Các câu thiếu nguồn vẫn nằm trong phạm vi và được chấm theo nhãn "ĐẠT — giới hạn nguồn/quyền đã xác nhận". Giữ tài liệu để truy vết, không trích số từ đây.

## 1. Dừng chấm 7 câu này, checker đã đổi từ 04/09

Commit `700ad9f` ngày 04/09 đã đổi checker cho 7 câu vì checker cũ trả lời **câu khác**. Nếu đang
chấm bằng bảng cũ thì kết quả 7 câu này không dùng được, phải chấm lại bằng checker mới:

| Câu | Checker CŨ (bỏ) | Checker ĐÚNG |
|---|---|---|
| C28 | S17 | **S91** |
| C31 | S20 | **S90** |
| M08 | S18 | **S90** |
| M22 | S40 | **S88** |
| M24 | S19 | **S92** |
| M25 | S41 | **S89** |
| M26 | S23 | **S89** |

Hai câu vừa báo "không khớp" đều nằm trong nhóm này:

- **M24** hỏi *"vùng nào"*. S19 là cohort giữ chân theo **tháng mở mới** — không trả lời theo vùng.
  Số đúng, chạy trên Bravo 10/09 (checker S92):

  | Vùng | Khách mới | DT/khách | Tỷ lệ mua lại |
  |---|---:|---:|---:|
  | MB | 596 | 7,6 tr | 42,1% |
  | MN | 316 | 6,3 tr | 33,9% |
  | MT | 203 | 4,4 tr | 29,1% |

  Kết luận đúng: **không vùng nào "mở nhiều nhưng chất lượng thấp"** — MB dẫn đầu cả ba trục, MT yếu
  cả ba. Câu trả lời khẳng định có vùng như vậy là sai với dữ liệu.

- **M25** hỏi *"nhóm khách tương đồng"*. S41c benchmark theo **cùng tỉnh** và tự ghi rõ *"chưa có
  phân khúc khách hàng chuẩn"*. S89 mới đúng: nhóm tương đồng = kênh × miền × bậc doanh thu NTILE 5.

`S38c`, `S41b`, `S41c` không có trong bộ chuẩn của repo.

## 2. Nhóm V phải set `@ManagerCode`, nếu không số sẽ sai

Trước 10/09, S38 **không có bộ lọc phạm vi nào** và S33 chỉ lọc theo miền. Câu cấp đội nhận số toàn
công ty. Đã sửa, nhưng khi chạy phải khai báo:

    DECLARE @ManagerCode varchar(24) = 'MBKV2';   -- đội Phạm Xuân Tú (tu.pham), 11 người

- V01–V32 → `@ManagerCode = 'MBKV2'` (Phạm Xuân Tú)
- V33–V40 → `@ManagerCode = 'TM25010183'` (Nguyễn Thị Hồng Thúy)

Để NULL thì ra 209 người toàn công ty thay vì 11 người của đội.

## 3. Ba câu bị chấm oan — chatbot đúng, checker sai

- **M33 / S72** — checker cũ dùng inner join nên **bỏ sót SKU ngừng bán hẳn**. Đo T7→T8: bản cũ 71
  SKU, thiếu thêm **36 SKU tương ứng 3.151.845.812đ**. Chatbot nêu SKU ngừng bán là **đúng**; người
  chấm không thấy trong query nên ghi "SKU chatbot trả về không có trong query". Đã sửa → 107 dòng.

- **M36 / S78** — kết luận *"không có nguồn số liệu chiết khấu, đây là hạn chế thật của hệ thống"*
  là **không đúng**. Cột `DiscountRate` có thật trên cả hai view hóa đơn, đã xác nhận từ 03/09 ở
  S87, và `#sales` mang sẵn cột này. Đã bổ sung → **MB tháng 01/2026 chiết khấu 1,51 tỷ = 3,16%
  doanh thu gộp**. Câu này chấm lại được.

- **V21 / S69** — checker báo `Invalid column name 'ManagerAreaCode'`, tức **chưa từng chạy được lần
  nào**, nên V21 không hề có số đối chứng. Đã sửa → 204 dòng. Câu này giờ mới chấm được.

## 4. Một câu là lỗi chatbot thật

**M35 / S12** — *"1 chương trình có nhiều tháng triển khai, chatbot chưa đề cập rõ ràng"*. Đây là lỗi
chatbot, không phải checker. Đã nằm trong danh sách sửa prompt gộp (luôn hiện `program_code` và kỳ
kèm tên chương trình). Chưa deploy nên tạm thời vẫn ghi nhận là chưa đạt.

## 5. Cách tính tỷ lệ

Mẫu số **119**, không phải 138. Có 19 câu không thể chấm được, không câu nào trong đó đang đạt:

- **10 câu không có nguồn dữ liệu**: C14, C15, C19 (giá vốn hàng bán); C52, M44 (action tracker);
  C37, M37, V35 (lịch sử công nợ theo tháng); C38, V37 (thu tiền/DSO). Checker của nhóm này là
  truy vấn **dò schema**, không phải truy vấn nghiệp vụ — nó luôn "không đúng trọng tâm" vì mục
  đích của nó là chứng minh nguồn không tồn tại.
- **6 câu dự báo** chủ đích không test: C04, C50, C51, M39, M43, V09.
- **3 câu chưa nhập target tháng 9**: M02, V02, V03.

Đề nghị **giữ nguyên 19 dòng trong file**, thêm cột `Loại khỏi mẫu số` thay vì xóa dòng — với nhóm
không có nguồn, hành vi **từ chối đúng cách** vẫn phải được kiểm; xóa dòng là mất hàng rào chặn
chatbot bịa số lợi nhuận gộp.
