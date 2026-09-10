# Mẫu số chấm điểm UAT — loại câu không thể chấm được (10/09/2026)

Nguồn dữ liệu: sheet kết quả UAT (tab `Trang tính1`, 138 dòng, cột `Kết quả chạy` và
`Chốt đánh giá`) đối chiếu với cột trạng thái nguồn trong
`docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md` tại `c697799`.

## Kết luận số

| Chỉ số | Giá trị |
|---|---:|
| Tổng câu trong bộ | 138 |
| Loại khỏi mẫu số (không thể chấm) | 19 |
| **Mẫu số chấm điểm đúng** | **119** |
| Số câu đã đạt | 62 |
| Tỷ lệ đang báo (sai mẫu số) | 62/138 = **44,9%** |
| **Tỷ lệ đúng** | 62/119 = **52,1%** |

Đã kiểm chứng: **không câu nào trong 19 câu bị loại đang được tính là "đạt"**. Việc sửa mẫu
số chỉ bỏ đi phần tử số 0 — không có câu đạt nào bị rút khỏi tử số, nên đây không phải là
làm đẹp số liệu bằng cách loại câu khó.

## Nhóm 1 — Không có nguồn dữ liệu (10 câu)

Checker của các câu này **không phải truy vấn nghiệp vụ** mà là truy vấn dò schema
(`sys.objects`/`sys.columns`) hoặc dò snapshot kho local. Nó luôn "không đúng trọng tâm" vì
mục đích của nó là chứng minh nguồn không tồn tại. Chấm các câu này là lỗi chatbot là sai
bản chất.

| Câu | Checker | Vì sao không có nguồn |
|---|---|---|
| C14, C15, C19 | S10 | Không có cột giá vốn hàng bán trên `vHoaDonTotal`/`vHoaDonETCTotal`. Chỉ có giá vốn **tồn kho** trên thẻ kho — dùng thay giá vốn hàng bán sẽ lệch biên lợi nhuận theo biến động giá nhập. |
| C52, M44 | S36 | Không tồn tại bảng action/owner/deadline nào trong Bravo. |
| C37, M37, V35 | S25 | Lịch sử công nợ theo tháng: thiết kế hiện tại **ghi đè** snapshot cũ, chỉ còn snapshot hiện tại. |
| C38, V37 | S45 | Không có bảng thu tiền/DSO/cam kết thu. |

## Nhóm 2 — Câu dự báo, chủ đích không test (6 câu)

C04, C50, C51, M39, M43, V09 — cột `Kết quả chạy` ghi rõ "Câu dự báo, không test". Đây là
quyết định phạm vi đã có từ trước, không phải câu bị lỗi.

## Nhóm 3 — Chưa có target/kế hoạch để đối chiếu (3 câu)

M02, V02, V03 — "Chưa nhập target tháng 9, chưa thể kiểm chứng". Đây là **việc nhập liệu
phía DNH**, không phải lỗi chatbot. Khi target tháng 9 được nhập thì trả 3 câu này về mẫu số.

## Cách chấm hai lớp — đề nghị giữ, không xóa dòng khỏi sheet

Không xóa 19 dòng này khỏi file. Lý do: với 10 câu Nhóm 1, hành vi **từ chối đúng cách** là
một yêu cầu có thật và phải được kiểm. Nếu xóa dòng thì mất luôn hàng rào chặn chatbot bịa
số lợi nhuận gộp — đúng thứ mà 3 câu C14/C15/C19 sinh ra để canh.

Đề nghị dùng hai chỉ số song song:

1. **Tỷ lệ trả lời đúng nghiệp vụ = 62/119 (52,1%)** — chỉ số chính đưa vào báo cáo tiến độ.
2. **Tỷ lệ hành vi đúng trên nhóm bị chặn = ?/19** — chấm riêng, tiêu chí đạt là chatbot nói
   rõ thiếu nguồn và **không** đưa ra con số. Ghi nhận sẵn: C52 và V37 đã có ghi chú chatbot
   phản hồi không có dữ liệu — hai câu này nhiều khả năng đạt tiêu chí từ chối, cần chốt lại.

Thêm một cột `Loại khỏi mẫu số` với ba giá trị `KHONG_CO_NGUON` / `CAU_DU_BAO` /
`CHO_TARGET` để công thức tính tỷ lệ tự loại, thay vì xóa dòng.

## Đòn bẩy lớn nhất còn lại: 27 câu đã sửa nhưng chưa retest

C02, C03, C08, C13, C20, C28, C41, C49, C54, M39, M40, V05, V10, V11, V15, V17, V18, V23,
V24, V25, V26, V28, V29, V30, V31, V32, V34.

Các câu này đã có commit sửa kèm mã commit trong cột `Đã sửa` nhưng cột `Chốt đánh giá` còn
trống. Đây là 27 câu có khả năng chuyển sang đạt mà **không cần viết thêm code** — chỉ cần
chạy lại đúng vai trò. Nếu retest đạt toàn bộ thì tỷ lệ lên 89/119 = 74,8%.

## 39 câu còn treo

C25, C30, C34, C39, C40, C43, C44, C50, C51, M05, M16, M20, M22, M23, M24, M25, M28, M29,
M30, M32, M33, M35, M36, M38, M41, M42, V06, V07, V08, V16, V21, V36, V40 (và C04, M02, V02,
V03, V09, M43 đã nằm trong nhóm loại ở trên).

Trong đó **M22 đã được xử lý trong phiên này** bằng tool `get_customer_attrition_risk` theo
đúng checker S88 — cần retest để chốt.

## Cảnh báo về file sheet

Dòng tiêu đề của sheet vẫn ghi `Thời điểm chạy 2026-08-28T14:59:00 — Phiên bản 77022a7`, và
khối tổng quan vẫn là `63 / 37 / 26 / 1 / 5 / 6`. Con số này **đã cũ**: checker doc tại
`c697799` hiện là 61 READY / 2 READY_CURRENT / 42 PARTIAL / 23 DERIVED / 5 BLOCKED /
5 BLOCKED_HISTORY. Phải cập nhật khối tổng quan trước khi gửi tester, nếu không hai nguồn
đá nhau.
