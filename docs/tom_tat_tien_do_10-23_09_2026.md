# Tóm tắt tiến độ DNH — 10/09 → 23/09/2026

*Dữ liệu cho slide báo cáo. Mọi con số lấy từ git log, kết quả chạy test, và các lần đo trên kho
thật — không ước lượng.*

Mốc so sánh: commit `f692e45` (10/09/2026). Hạn đóng UAT: **30/09/2026** (còn 7 ngày).

---

## 1. Khối lượng

| Chỉ số | Giá trị |
|---|---:|
| Commit | **199** |
| PR đã merge | **60** |
| File thay đổi | **178** |
| Dòng thêm | **26.849** |
| Dòng xoá | **2.850** |

Phân bổ dòng thay đổi:

| Vùng | Dòng | % |
|---|---:|---:|
| `tests/` | 11.007 | **37,1%** |
| `backend/` | 7.823 | 26,4% |
| `scripts/` | 4.002 | 13,5% |
| `docs/` | 3.547 | 12,0% |
| `src/` | 2.451 | 8,3% |
| khác | 828 | 2,7% |

> Kiểm thử chiếm tỷ trọng lớn nhất — mỗi bản sửa số liệu đều kèm test khoá.

Nhịp PR theo ngày: 15/09 (5) · 16/09 (5) · 17/09 (10) · 18/09 (3) · 21/09 (6) · 22/09 (8) · 23/09 (**27**)

---

## 2. Kiểm thử tự động

| | 10/09 | 23/09 | Tăng |
|---|---:|---:|---:|
| Hàm test | 523 | **949** | **+81,5%** |
| File test | 55 | **121** | **+120,0%** |

Kết quả chạy toàn bộ ngày 23/09: **1.052 passed, 1 deselected, 0 failed** → **100%** test đạt.

---

## 3. Cổng kiểm trước UAT

Trạng thái **23/09, chạy trên máy 24 (production)**:

| Cổng | Kết quả |
|---|---|
| Tài khoản và phạm vi dữ liệu | **ĐẠT** |
| Phân quyền kênh ETC | **ĐẠT** — 3/3 phép |
| Bất biến số liệu 51 công cụ | **ĐẠT** — 99 phép đạt, **0 lệch** |

**Kết luận cổng: "Các cổng kiểm tra tự động đã đạt; có thể chuyển sang bước test 5 câu."**

| Chỉ số | Giá trị |
|---|---:|
| Phép kiểm chạy được và đạt | **99/99 = 100%** |
| Tool có phép đối chiếu | **49/51 = 96,1%** |
| Tool thiếu nguồn (đã biết, phía DNH) | 2 |
| Tài khoản đã duyệt hợp lệ phạm vi | **30/30 = 100%** |

Tiến triển trong ngày: kho dev 03/09 chạy được 35 phép → 23/09 đạt **99 phép** (+183%); số mục bị bỏ
giảm **25 → 2** (−92%).

---

## 4. Xử lý phản hồi UAT

| Chỉ số | Giá trị |
|---|---:|
| Câu UAT điều tra dứt điểm | **7** (v21, v24, v34, C08, C20, C24, C29) |
| Trong đó: lỗi thật của chatbot, đã sửa | **4** |
| Trong đó: **chatbot đúng, checker sai** | **2** (C08, C29 bảng A) |
| Trong đó: bất đồng định nghĩa, cần DNH chốt | **1** |
| Đợt sửa prompt gộp | **5/6 = 83%** xong, 1 mục chờ DNH |

### Danh sách chấm lại

| | Số lượt | Ghi chú |
|---|---:|---|
| Ban đầu | 24 | |
| Đóng **miễn phí** bằng đối chiếu log | **−6 (25%)** | không tốn lượt gọi model nào |
| Phát hiện bổ sung | +2 | log chi phí bỏ sót |
| **Còn phải chấm lại** | **20** | |
| Đã chạy 23/09 | 2 | 1 đóng được, 1 đạt 2/3 điều kiện |
| Còn lại | **18** | |

### Phân loại lỗi UAT tháng 9 (quét toàn bộ `query_runs`)

| Loại | Số lượt | Bản chất |
|---|---:|---|
| Hết hạn mức API | **14** | **KHÔNG phải lỗi sản phẩm** |
| Timeout | 12 | lỗi thật — đã truy ra **một** nguyên nhân chung |
| Kẹt trạng thái | 3 | |
| Người dùng đóng sớm | 2 | |
| **Tổng** | **31** | |

> **45% số "lỗi" trong sổ chấm UAT là hết tiền API, không phải chatbot hỏng.** Người chấm chỉ thấy
> chữ "Lỗi" nên ghi như nhau. Đã sửa: lỗi hết credit nay có mã riêng + thông báo phân biệt.

12 lượt timeout đều chết trong dải **111,8–116,4 giây** (biên độ 4,6 giây, trải 18 ngày, 6 câu hỏi
khác nhau) → **một ngưỡng cấu hình 110 giây**, không phải 6 câu chậm riêng lẻ. Đã sửa: hết ngân sách
nay trả câu trả lời rút gọn thay vì chữ "Lỗi".

---

## 5. Sai số liệu đã tìm ra và sửa — quy ra tiền

| Phát hiện | Số tiền | Trạng thái |
|---|---:|---|
| Join `dmsid` trùng làm phồng doanh thu (0,256%) | **253.831.460 đ** | ✅ đã sửa, khớp SQL đến từng đồng |
| Thiếu Kênh MT + Chợ sỹ Miền Nam trong đối soát | **205.469.532 đ** | ✅ đã sửa |
| Chứng từ ETC ngày tương lai lọt vào 2 đường tính | **17.558.648 đ** | ✅ đã sửa |
| Chốt sai đội hình kỳ quá khứ (v34) | **9.214.815 đ** | ✅ đã sửa |
| 20 tháng doanh thu trả về **0 đồng** (01/2024–08/2025) | *toàn bộ kỳ* | ✅ đã sửa |
| 11 khách Miền Trung thiếu dòng FACT cấp nhân viên | **13.173.440 đ** | ⏳ chờ DNH xác nhận |
| Cây KPI: rollup QLV vs tổng TDV (0,303%) | **55.866.929 đ** | ⚠️ dưới ngưỡng 1%, cần truy |

**Tổng sai số đã sửa: 486.074.455 đ** (chưa kể 20 tháng ra 0 đồng).
**Còn treo: 69.040.369 đ.**

---

## 6. Chi phí AI

| Khoản | Số tiền |
|---|---:|
| Sự cố `business-eval` 10/09 (235 lượt không điều phối) | **7,08 USD ≈ 177.000 đ** |
| Lượt gọi không truy được người chạy (11/09 + 13/09) | **≈ 133.300 đ** |
| Đợt chấm lại 23/09 — đã chạy 2 lượt | **0,6841 USD = 17.103 đ** |
| Đơn giá thật đo được | **8.550 đ/lượt** |
| 18 lượt còn lại (dự kiến) | **≈ 154.000 đ** |

### Biện pháp đã áp dụng

| Biện pháp | Kết quả |
|---|---|
| Cấm `business-eval`, mọi lượt trả phí phải được duyệt trước | ✅ vào `AGENTS.md` |
| Chặn lượt gọi model thiếu `username`/`session_id` | ✅ đã deploy |
| Lỗi hết credit có mã riêng + cảnh báo Teams | ✅ đã deploy |
| Cảnh báo **trước khi** cạn số dư | ⏳ chờ số dư từ Anthropic Console |
| Đóng 6 mục chấm lại bằng đối chiếu log miễn phí | ✅ tiết kiệm **≈ 51.300 đ** |
| Gộp 4 lượt "mùa vụ" thành 1 | ✅ tiết kiệm **≈ 25.650 đ** |

**Tiết kiệm đã thực hiện: ≈ 76.950 đ** (bằng phân tích log, 0 đồng chi phí model).

> Ước tính ban đầu 4.000 đ/lượt là **sai một nửa** — đo thật ra 8.550 đ/lượt vì mỗi mục chạy trong
> phiên riêng nên phải ghi lại cache (cache chiếm 71% chi phí). Ngân sách 20 lượt: 80.000 đ →
> **171.000 đ**.

---

## 7. Công cụ vận hành mới

| Công cụ | Mục đích |
|---|---|
| `doc_query_runs_may_24.py` | Đọc log UAT máy 24, 5 phần — miễn phí |
| `truy_luot_khong_ten.py` | Truy nguồn lượt gọi model không có danh tính |
| `cham_lai_uat.py` | Chạy lại lượt UAT đúng vai, **mặc định không gọi model** |
| `kiem_truoc_uat.ps1` | Cổng kiểm 3 lớp trước khi giao tài khoản |
| `runbook_trien_khai_may_24.md` | Quy trình pull–restart, 5 bẫy đã gặp |

---

## 8. Còn lại trước 30/09

| Việc | Chặn ở | Tiền |
|---|---|---:|
| 18 lượt chấm lại | quyết định ngân sách | **≈ 154.000 đ** |
| 4 câu hỏi định nghĩa nghiệp vụ | **DNH** | — |
| Số dư API để bật cảnh báo sớm | nội bộ | — |
| Sự cố đồng bộ CTKM dừng 09/01/2026 | **DNH** — MCNA không sửa được | — |
| Truy chênh cây KPI 1 QLV | nội bộ | 55.866.929 đ |

**Chặn kỹ thuật duy nhất ngoài tầm MCNA:** job đồng bộ nhóm CTKM (11 bảng) chết từ 09/01/2026, làm
3 câu UAT không trả lời được cho mọi kỳ năm 2026.

---

## 9. Ba con số tóm gọn

| | |
|---|---:|
| Cổng kiểm trước UAT | **ĐẠT — 99/99 phép, 0 lệch** |
| Kiểm thử tự động | **1.052 đạt / 0 hỏng**, +81,5% số test |
| Sai số liệu đã sửa | **486.074.455 đ** |
