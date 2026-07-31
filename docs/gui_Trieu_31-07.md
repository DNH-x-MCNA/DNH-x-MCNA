# Gửi Triều — 31/07/2026

Hai việc phát hiện khi rà soát `FACT_ThongKeTinhLuong` (commit `ce6aeea` của bạn). Không có gì hỏng,
không cần sửa gấp — nhưng một cái là **đúng thứ bạn đã cảnh báo trước**, nên gửi để bạn biết.

---

## 1. Cái bẫy bạn lường trước đã thành thật

Trong `kpi_ranking()` bạn viết hôm 27/07:

> *"CHOT AN TOAN 1 - chong LONG TANG: gop tang rollup chi dung khi cac rollup KHONG chua nhau.
> Nếu sau này Bravo thêm cấp trên (vd TP quản lý QLV), cộng cả 2 cấp sẽ GẤP ĐÔI âm thầm.
> Hiện tại (27/07/2026): 21/21 đều là QLV, không ai bị lồng."*

**`FACT_ThongKeTinhLuong` chính là chỗ có TP.** Đo trên Bravo kỳ 31/07/2026, 206 mã:

| Tầng | Số mã | `MonthSaleAmount` |
|---|---:|---:|
| TP (trưởng phòng / GĐ miền) | 3 | **33.307.889.644** |
| QLV | 21 | **33.307.889.644** |
| TDV + CS + TK + CTV | ~180 | **33.307.889.644** |
| PP (lớp phủ, chỉ MN) | 2 | 5.198.362.685 |
| **Cộng cả bảng** | 206 | **105.122.031.617** |

Ba tầng đều đúng bằng doanh thu OTC thật tháng 7 (`SUM(Amount9)` trên `vHoaDonTotal`). Cộng cả bảng ra
đúng `3 × 33.307.889.644 + 5.198.362.685` — **sai gấp hơn 3 lần**.

Thêm một điểm dễ vấp: mẹo *"mã nào không xuất hiện làm `ManagerCode`"* — dùng tốt cho
`fact_tonghopkhachhang` (2 tầng) — **sai ở bảng này**, vì QLV vừa quản lý người khác vừa bị TP quản lý.
Áp mẹo đó ra **71.814.141.973**, sai 2,16 lần.

### Chưa nguy hiểm, và không đụng gì vào code của bạn

`salary_detail()` **an toàn**: trả đúng một dòng cho một người (`LIMIT 1`), phân quyền chặt, không cộng
gộp. Và bảng chưa khai trong `schema_context.py` nên AI không tự viết SQL chạm vào được.

Chỉ thêm cảnh báo ở hai chỗ (commit `bf1c6f0`):
- `local_warehouse.py` — ngay trên `CREATE TABLE`, kèm số đo đầy đủ.
- `schema_context.py` — comment Python **ngoài** chuỗi prompt, để ai định khai bảng này vào sẽ đọc
  được trước. Đã kiểm: độ dài prompt gửi AI không đổi.

**Điều cần nhớ:** nếu sau này khai bảng vào `schema_context.py` để mở thêm câu hỏi, phải viết kèm cảnh
báo 3 tầng **ngay trong cùng lần sửa** — đừng khai trước rồi cảnh báo sau.

---

## 2. Câu hỏi cần DNH xác nhận: CTV đang bị chấm ngưỡng 70%

Chú thích trong `local_warehouse.py` ghi `position_code` chỉ có `'QLV'` hoặc `'TDV'`. Thực tế Bravo có
**7 giá trị**: `TP`, `PP`, `QLV`, `TDV`, `CS`, `TK`, `CTV`.

`_bonus_threshold()` xử lý đúng theo thiết kế (`TDV → 65`, mọi vai trò khác `→ 70`). Nhưng hệ quả là
**3 CTV ở miền Nam đang bị chấm ngưỡng 70% như cấp quản lý**.

Cộng tác viên chịu ngưỡng của quản lý nghe hơi lạ, nhưng mình không có văn bản chính sách để khẳng
định — nên để thành **câu hỏi cho DNH** chứ không tự sửa. Nếu DNH trả lời CTV phải là 65%, sửa chỉ là
đổi điều kiện trong `_bonus_threshold()`.

Đã cập nhật chú thích cho đúng 7 giá trị, không đổi logic.

---

## Tham chiếu

- Rà soát đầy đủ: [`docs/ra_soat_dong_bo_bang_kpi.md`](ra_soat_dong_bo_bang_kpi.md)
- Kiểm chứng 15 câu hỏi KPI: [`docs/kiem_chung_13_cau_kpi_31-07.md`](kiem_chung_13_cau_kpi_31-07.md)
- Commit cảnh báo: `bf1c6f0` trên nhánh `master`
