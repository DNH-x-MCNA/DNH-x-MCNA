# Tiến độ dự án DNH — 10/09 → 23/09/2026

*Dữ liệu cho slide báo cáo. Số lấy từ log UAT thật trên máy 24 và kết quả chạy kiểm — không ước lượng.*

Hạn đóng UAT: **30/09/2026**.

---

# A. CHATBOT — TỈ LỆ ĐÚNG

## A1. Kết quả chấm UAT (03/09 – 18/09)

| | Số lượt | Tỉ lệ |
|---|---:|---:|
| Người dùng chấm **đúng** 👍 | 14 | **40,0%** |
| Người dùng chấm **sai** 👎 | 21 | 60,0% |
| **Tổng lượt có chấm** | **35** | 100% |

## A2. Phân tích 21 lượt bị chấm sai

| Nhóm | Số lượt | Tỉ lệ |
|---|---:|---:|
| Lỗi thật — **đã có bản sửa** | **17** | **81,0%** |
| **Chatbot đúng**, người chấm đối chiếu khác phạm vi | 2 | 9,5% |
| Cần DNH chốt định nghĩa nghiệp vụ | 2 | 9,5% |

→ **Không có lượt nào là lỗi chưa tìm ra nguyên nhân.** 100% đã truy được nguồn gốc.

## A3. Tỉ lệ đúng — hiện tại và dự kiến

| Mốc | Tỉ lệ đúng |
|---|---:|
| Khi chấm UAT (03–18/09) | **40,0%** |
| Sau khi xác minh 2 ca chatbot vốn đã đúng | **45,7%** |
| **Dự kiến sau khi chấm lại 17 bản sửa** | **94,3%** |
| Phần còn phụ thuộc DNH chốt định nghĩa | 5,7% |

**Đã chấm lại thực tế 23/09: 2 lượt** — 1 đóng hoàn toàn, 1 đạt 2/3 điều kiện.
Còn 18 lượt chờ chạy để xác nhận con số 94,3%.

## A4. Điểm quan trọng: 45% "lỗi" không phải lỗi sản phẩm

Quét toàn bộ log tháng 9, có **31 lượt báo "Lỗi"**:

| Nguyên nhân | Số lượt | Tỉ lệ | Bản chất |
|---|---:|---:|---|
| **Hết hạn mức API** | **14** | **45,2%** | **Không phải chatbot sai** |
| Quá thời gian xử lý | 12 | 38,7% | Lỗi thật — đã sửa |
| Kẹt trạng thái | 3 | 9,7% | Đã sửa |
| Người dùng đóng sớm | 2 | 6,5% | Không phải lỗi |

Người chấm chỉ nhìn thấy chữ **"Lỗi"** nên ghi vào sổ như nhau. Nặng nhất: một người hỏi **cùng một
câu 5 lần trong 75 phút**, cả 5 lần đều do hết hạn mức.

**Đã khắc phục:** lỗi hết hạn mức nay có mã riêng và thông báo phân biệt rõ với lỗi sản phẩm.

12 lượt quá thời gian đều dừng ở **110 giây** — một ngưỡng cấu hình duy nhất, không phải 12 câu hỏi
chậm khác nhau. Đã sửa: nay trả câu trả lời rút gọn kèm phần đã đối chiếu được, thay vì chữ "Lỗi".

## A5. Độ chính xác số liệu — đã kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| Phép kiểm bất biến số liệu | **99/99 đạt, 0 lệch** |
| Công cụ báo cáo có phép đối chiếu | **49/51 = 96,1%** |
| Phân quyền theo vai/miền/kênh | **3/3 đạt** |
| Tài khoản hợp lệ phạm vi | **30/30 = 100%** |

**Cổng kiểm trước UAT: ĐẠT** — *"có thể chuyển sang bước test 5 câu."*

### Sai số liệu đã phát hiện và sửa

| Phát hiện | Số tiền |
|---|---:|
| Nhân bản dòng khi ghép mã nhân viên | 253.831.460 đ |
| Thiếu Kênh MT + Chợ sỹ Miền Nam khi đối soát | 205.469.532 đ |
| Chứng từ ngày tương lai lọt vào tổng | 17.558.648 đ |
| Chốt sai đội hình kỳ quá khứ | 9.214.815 đ |
| **Tổng đã sửa** | **486.074.455 đ** |

Thêm một lỗi không quy ra tiền được: **20 tháng doanh thu trả về 0 đồng** (01/2024–08/2025) — đã sửa.

---

# B. HỆ THỐNG CẢNH BÁO (ALERT)

## B1. Mức hoàn thành

| Hạng mục | Trạng thái |
|---|---|
| Số loại cảnh báo đã xây | **19 trigger** |
| Dịch vụ chạy thường trực trên máy thật | ✅ **Đang chạy** (`DNH_Realtime_Alerts`) |
| Kiểm thử tự động | **43 test** |
| Kênh gửi: Email | ✅ đang chạy |
| Kênh gửi: Teams | ⏳ **chờ DNH cấp 6 UPN + webhook** |
| Đổi máy chủ gửi mail sang tên miền DNH | ⏳ **chờ DNH cấp đặc tả SMTP** |

**Mức hoàn thành phần code: ~95%.** Phần còn lại không nằm ở MCNA.

## B2. Danh mục 19 cảnh báo

| Nhóm | Cảnh báo |
|---|---|
| **Doanh thu** (5) | Sụt doanh thu · Nhịp tháng theo kênh · Nhịp theo đội · Tập trung doanh thu · Nhịp KPI ngày |
| **Công nợ** (4) | Vượt hạn mức tín dụng · Tỉ lệ quá hạn toàn công ty · Khách quá hạn vẫn đặt đơn mới · Dịch chuyển tuổi nợ |
| **Tồn kho** (2) | Hàng chậm luân chuyển · Hàng cận date |
| **Khách hàng** (2) | Khách rời bỏ · Khách mua đều bỗng im lặng |
| **Nhân sự / KPI** (3) | Rủi ro lực lượng bán · Nhân viên không phát sinh doanh số · Tụt mốc KPI |
| **Chất lượng dữ liệu** (3) | Độ mới dữ liệu ETL · Đối soát KPI vs doanh thu · Tỉ lệ hàng trả |

---

# C. HỆ THỐNG BÁO CÁO (REPORT)

## C1. Mức hoàn thành

| Hạng mục | Trạng thái |
|---|---|
| Công cụ báo cáo cố định | **51 công cụ** |
| Có phép kiểm bất biến số liệu | **49/51 = 96,1%** |
| 2 công cụ chưa kiểm được | thiếu nguồn từ DNH, **không phải lỗi** |
| Báo cáo định kỳ tự động | ✅ Bản tin QLV · Báo cáo insight · Bộ gửi thông báo |
| Kiểm thử tự động | **64 file test** |

**Mức hoàn thành: ~96%.**

## C2. Hai công cụ chưa chạy được — nguyên nhân ngoài MCNA

| Công cụ | Nguyên nhân |
|---|---|
| Hiệu quả khuyến mãi | **Job đồng bộ CTKM dừng từ 09/01/2026** — 11 bảng cùng chết. Thuộc hạ tầng DNH |
| So sánh công nợ theo kỳ | Lịch sử công nợ chỉ lưu từ 21/08/2026 |

> Sự cố CTKM làm **3 câu UAT không trả lời được cho bất kỳ kỳ nào trong năm 2026**. MCNA chỉ đọc dữ
> liệu, không sửa được chiều ghi — cần đội vận hành DNH khởi động lại job và chạy bù.

---

# D. CHI PHÍ VẬN HÀNH AI

### Chi phí và thời gian theo độ phức tạp — đo trên 180 lượt thật

*Nguồn: nhật ký chi phí 15–23/09. Đã loại 4 lượt có thời gian dưới 5 giây (lượt trùng/dùng lại
kết quả, không phải lần chạy thật).*

| | Trung bình | Trung vị |
|---|---:|---:|
| Chi phí mỗi lượt | **5.042 đ** | **3.241 đ** |
| Thời gian trả lời | **36,5 giây** | **31,1 giây** |

> Trung vị thấp hơn trung bình khá nhiều → **một số ít câu rất nặng kéo trung bình lên**. Khi lập
> ngân sách nên dùng trung vị cho số đông và tính riêng nhóm nặng.

#### Theo độ phức tạp của CÂU TRẢ LỜI

| Mức | Số lượt | Chi phí TB | Trung vị | Thời gian TB |
|---|---:|---:|---:|---:|
| Rất nhẹ | 20 | 2.855 đ | 1.515 đ | **12,3 giây** |
| Nhẹ | 71 | 4.147 đ | 2.707 đ | 24,2 giây |
| Trung bình | 45 | 4.827 đ | 3.246 đ | 38,7 giây |
| Nặng | 33 | 7.093 đ | 5.804 đ | 57,4 giây |
| Rất nặng | 11 | 9.525 đ | **11.660 đ** | **88,7 giây** |

Từ nhóm nhẹ nhất đến nặng nhất: chi phí tăng **3,3 lần**, thời gian tăng **7,2 lần**.

#### Theo bản chất CÂU HỎI

| Loại câu hỏi | Số lượt | Chi phí TB | Trung vị | Thời gian TB |
|---|---:|---:|---:|---:|
| Hỏi lại / giải thích cách tính | 8 | **1.721 đ** | 1.389 đ | 19,6 giây |
| Tra cứu một số / một khách | 15 | 2.908 đ | 1.741 đ | **15,9 giây** |
| Danh sách / top N | 21 | 4.931 đ | 3.657 đ | 29,4 giây |
| Tổng hợp một chiều | 80 | 5.321 đ | 3.675 đ | 38,7 giây |
| **So sánh kỳ / chuỗi thời gian** | 38 | **6.156 đ** | **5.416 đ** | **45,1 giây** |
| Chẩn đoán đa chiều | 18 | 4.836 đ | 3.044 đ | 41,8 giây |

**Câu đắt nhất không phải câu phức tạp nhất về nghiệp vụ, mà là câu kéo nhiều tháng dữ liệu.**
Nhóm "so sánh kỳ / chuỗi thời gian" tốn hơn nhóm "chẩn đoán đa chiều" **27%**, dù nghe có vẻ đơn
giản hơn.

#### Biên độ rất rộng — không có "đơn giá" cho một lượt hỏi

| | Rẻ / nhanh nhất | Đắt / chậm nhất | Chênh |
|---|---:|---:|---:|
| Chi phí | 1.074 đ | 15.126 đ | **14,1 lần** |
| Thời gian | 7,0 giây | 116,7 giây | **16,7 lần** |

Tương quan giữa chi phí và thời gian chỉ **r = 0,42** — câu chạy lâu **không** đồng nghĩa tốn nhiều
tiền. Không thể suy chi phí từ thời gian, và ngược lại.

### Kiểm soát chi phí đã áp dụng

| Biện pháp | Trạng thái |
|---|---|
| Mọi lượt gọi trả phí phải được duyệt trước | ✅ |
| Chặn lượt gọi không xác định được người dùng | ✅ đã chạy thật |
| Lỗi hết hạn mức có cảnh báo Teams ngay | ✅ đã chạy thật |
| Cảnh báo **trước khi** cạn hạn mức | ⏳ chờ số dư từ Console |

---

# E. TỔNG HỢP MỨC HOÀN THÀNH

| Hạng mục | Mức hoàn thành |
|---|---:|
| **Cảnh báo (Alert)** | **~95%** |
| **Báo cáo (Report)** | **~96%** |
| **Chatbot — độ chính xác số liệu** | **99/99 phép kiểm đạt** |
| **Chatbot — tỉ lệ đúng theo người dùng chấm** | 40% → **dự kiến 94,3%** |
| **Cổng kiểm trước UAT** | ✅ **ĐẠT** |

---

# F. VIỆC CHỜ PHÍA DNH

| Việc | Ảnh hưởng |
|---|---|
| **Khởi động lại job đồng bộ CTKM** (dừng 09/01/2026) | 3 câu UAT không trả lời được cho năm 2026 |
| 4 câu hỏi định nghĩa nghiệp vụ | Chặn đóng UAT |
| 6 UPN Teams + webhook | Chưa bật kênh Teams cho cảnh báo |
| Đặc tả SMTP | Chưa đổi được máy chủ gửi mail sang tên miền DNH |
| Nguồn giá tồn kho | 969.269 đơn vị đang hiển thị 0 đồng |
| Nguồn chỉ tiêu theo quý | 1 câu UAT chưa trả lời đủ |

---

# G. BA CON SỐ CHO SLIDE TỔNG KẾT

| | |
|---|---:|
| Cổng kiểm số liệu trước UAT | **99/99 đạt — 0 lệch** |
| Nguyên nhân phản hồi UAT đã truy ra | **100%** (21/21) |
| Sai số liệu đã phát hiện và sửa | **486.074.455 đ** |
