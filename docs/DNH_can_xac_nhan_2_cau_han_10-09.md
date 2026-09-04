# Hai câu cần DNH xác nhận — hạn **10/09/2026**

> Bản rút gọn từ `Cau_hoi_can_DNH_xac_nhan.md`. Bốn câu còn lại của Nhóm A (A1, A2, A3, A5)
> MCNA **đã tự giải quyết được** bằng đối chiếu dữ liệu — nêu ở phần cuối để DNH nắm, **không cần
> trả lời**.
>
> Hai câu dưới đây **không tự giải được**: chúng phụ thuộc vào ý định quản trị và cơ cấu tổ chức
> thật, không phải phụ thuộc dữ liệu.

---

## Câu 1 — Giữa tháng thì "đạt chỉ tiêu" so với cái gì?

### Vấn đề

`MonthSaleTarget` là chỉ tiêu **cả tháng**, còn doanh số là **lũy kế đến thời điểm xem**. Xem càng
sớm trong tháng thì tỷ lệ đạt càng gần 0.

Đo thật ngày **04/09/2026** (ngày thứ 4 của tháng), toàn công ty:

| | Số người |
|---|---:|
| Có chỉ tiêu tháng 9 trong hệ thống | **0 / 209** |
| Đạt ≥65% (mức thưởng nhóm hàng) | 0 |
| Đạt ≥100% | 0 |

Trong đợt kiểm thử ngày 04/09, **nhiều câu trả lời liên tiếp** đều dừng ở *"chỉ tiêu tháng 9 chưa
được nhập, không tính được % hoàn thành"*. Người dùng không có cách nào biết đây là **tình trạng
bình thường đầu tháng** hay là **lỗi dữ liệu** — và đã có câu trả lời nêu đích danh một nhân viên
là "thiếu target, có thể ảnh hưởng đánh giá thưởng", trong khi thực ra **cả 209 người đều chưa có**.

### Cần DNH chọn một

- [ ] **(1) Theo nhịp độ** — so lũy kế với phần chỉ tiêu tương ứng số ngày đã trôi qua
      *(đến ngày 15/30 thì mốc là 50% chỉ tiêu)*. **MCNA khuyến nghị phương án này.**
- [ ] **(2) Chỉ đánh giá tháng đã kết thúc** — trong tháng chỉ hiện doanh số lũy kế, không hiện "% đạt"
- [ ] **(3) Giữ nguyên** — so với chỉ tiêu cả tháng, chấp nhận con số thấp đầu tháng

Nếu chọn **(1)**, xin cho biết thêm: tính theo **ngày lịch** hay **ngày làm việc**?

### Vì sao cần DNH chốt

Đây là thay đổi **cách tính**, không phải cách hiển thị — MCNA không tự quyết được ngưỡng đánh giá
con người. Chọn (1) là sửa code; chọn (2) hoặc (3) thì giữ nguyên và chỉ ghi rõ hơn.

---

## Câu 2 — Mã `MBKV12` (bà Nguyễn Thị Thanh Thủy) là gì?

### Vấn đề

Bà Thủy có **ba bản ghi riêng biệt** trong cùng dữ liệu Bravo *(kiểm lại 04/09/2026)*:

| Mã | Chức danh | Số TDV dưới quyền | Chỉ tiêu tháng 8 |
|---|---|---:|---:|
| `MB` | **TP** — Trưởng phòng, quản lý toàn bộ 10 QLV miền Bắc | (cả vùng) | — |
| `MBKV12` | **QLV** — tổ trưởng | **0** | **6,72 tỷ** |
| `SA_MB` | **CS** — Chợ sỉ, khu vực `V11` | 0 | — |

Tức trong cây tổ chức hệ thống dựng từ Bravo, bà vừa là **sếp vùng** vừa là **cấp dưới của chính
mình**. Chỉ tiêu `MBKV12` là **6,72 tỷ** — **hơn gấp đôi** mức trung bình của QLV tổ miền Bắc
(**3,05 tỷ**, đo ngày 31/08/2026) — trong khi **không có ai báo cáo lên mã đó**.

### Ảnh hưởng đang diễn ra

Kỳ chốt tháng 8/2026, bản ghi `MBKV12` mang doanh số **7.841.342.825đ** trên chỉ tiêu
**6.720.000.000đ** (đạt 116,7%) nhưng **0 TDV dưới quyền**. Vì không có cấp dưới nào để đối chiếu,
hệ thống **loại bản ghi này khỏi mọi phép kiểm tự động** — nghĩa là gần **7,8 tỷ đồng chưa từng được
kiểm chứng lần nào**. Không phải vì số sai, mà vì không có gì để so.

Nếu 6,72 tỷ là **chỉ tiêu cấp vùng bao trùm nhiều tổ**, nó đang bị **cộng chồng** với chỉ tiêu các
QLV tổ khác → "% hoàn thành toàn miền Bắc" bị kéo xuống thấp giả tạo.
*(Doanh số 7,84 tỷ là khách riêng của bà, không cộng trùng — chỉ phần chỉ tiêu là nghi vấn.)*

### Cần DNH xác nhận

1. Bản ghi `MBKV12` là **một tổ QLV thật**, hay là **bản trùng lặp của chính vị trí TP**?
2. Chỉ tiêu **6,72 tỷ** là của riêng bà, hay là chỉ tiêu gộp cả vùng?
3. Còn **bao nhiêu trường hợp tương tự** — quản lý ôm khách trực tiếp, không có tổ dưới quyền?

MCNA đã thêm cảnh báo tạm trong chatbot (khi hỏi về QLV này, hệ thống tự nói rõ nghi vấn trùng bản
ghi thay vì trình bày như QLV bình thường). Đây chỉ là xử lý ở tầng hiển thị — không thay được việc
xác nhận đúng bản chất bản ghi.

---

## Bốn câu MCNA đã tự giải quyết *(không cần trả lời, nêu để DNH nắm)*

**A1 — Nguồn công nợ chuẩn.** Đã chuyển sang dùng đúng SP gốc của DNH
(`usp_DeptAccDueDate_GetData`). Kiểm tự động ngày 04/09: chia theo kênh, chia theo vùng và tổng dư nợ
khớp **lệch 0 đồng**.

**A3 — Nguồn giá tính giá trị tồn kho.** Đã tìm ra: hệ kho sản xuất (`BRVSX_TonKhoDK`) có đầy đủ đơn
giá và thành tiền — **229,8 tỷ** cho năm 2026. Trước đó hệ thống chỉ đọc kho kinh doanh (5,38 tỷ) và
trình bày như tổng toàn công ty, tức chỉ **2,3% sự thật**. Đã đồng bộ cả hai hệ và tách rõ.
Mục "tồn kho chết" từng phải tắt vì giá trị luôn = 0 nay bật lại được.
*Còn lại:* kho kinh doanh miền Trung (`B03`) vẫn thiếu giá trên 969.269 đơn vị — nếu DNH tiện xác
nhận nguồn giá cho riêng phần này thì tốt, nhưng không chặn gì.

**A5 — Chỉ tiêu cá nhân kênh ETC.** Đã tìm ra bảng `FACT_TargetETCCT`: **493 dòng, 9 nhân viên, 43
sản phẩm, 35 hợp đồng**, khoá theo *(hợp đồng × sản phẩm)*. Đây là **chỉ tiêu sản phẩm theo hợp đồng
thầu**, không phải chỉ tiêu doanh số cá nhân theo tháng như bên OTC — và chỉ 9 người có, trong khi
hóa đơn ETC ghi nhận 34 nhân viên. MCNA **không dùng bảng này để chấm KPI cá nhân**, vì làm vậy là
tạo ra một thước đo DNH không dùng.
*Nếu DNH có ý định khác cho bảng này, xin cho biết — nhưng không chặn tiến độ.*

**A2 — Mốc phân nhóm tuổi nợ.** Đang dùng đúng bốn mốc của báo cáo gốc DNH (1–15, 15–30, 30–45,
>45 ngày). Không phát hiện sai lệch.

---

## Ngoài Nhóm A — một điểm DNH đã xác nhận ngày 04/09

Thời điểm tạo đơn (`CreatedAt`, không phải thời điểm xác nhận đơn) so với ngày chứng từ (`DocDate`)
**không mang ý nghĩa nghiệp vụ** — đơn có thể được tạo vào bất kỳ thời điểm nào. MCNA đã **gỡ toàn
bộ** phần diễn giải độ lệch này thành "dấu hiệu
chạy đơn KPI" khỏi hệ thống, vì nó từng dẫn tới một câu trả lời nêu đích danh 4 nhân viên như nghi
vấn gian lận — cáo buộc dựa trên nhiễu. Cảm ơn DNH đã làm rõ sớm.
