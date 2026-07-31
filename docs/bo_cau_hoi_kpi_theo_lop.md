# Bộ câu hỏi KPI cho chatbot — cắt theo 3 trục

Dựng từ cấu trúc thật của bảng `FACT_TongHopKhachHang` (đã truy vấn và kiểm chứng 31/07/2026).
Mục đích: kiểm chatbot **theo hệ thống** thay vì hỏi ngẫu nhiên — mỗi câu chạm một ô cụ thể trong
lưới, và phần lớn câu được thiết kế để **chạm đúng vào các bẫy đã biết**.

---

## Khung tư duy: dữ liệu KPI có 3 trục

### Trục DỌC — phân cấp tổ chức (dữ liệu gộp từ dưới lên)

```
Lớp 1  TOÀN CÔNG TY          50,1 tỷ chỉ tiêu · 3 miền
Lớp 2  VÙNG                  MB 92 NV · MN 42 NV · MT 31 NV
Lớp 3  QUẢN LÝ VÙNG          21 người (ManagerCode IS NULL)
Lớp 4  NHÂN VIÊN (TDV)       165 người (ManagerCode IS NOT NULL)
       └─ KHÁCH HÀNG         19.420 khách — độ mịn nhỏ nhất của bảng
```

> ⚠️ Lớp 3 **đã là bản gộp** của Lớp 4. Đã xác minh kỳ 31/07: hai tầng có số dòng bằng nhau tuyệt đối
> (6.574 = 6.574) và tổng tiền bằng nhau tuyệt đối (**33.307.889.644 = 33.307.889.644**), lại đúng
> bằng doanh thu OTC tháng 7 thật từ `vHoaDonTotal`. Cộng cả hai = **đúng gấp đôi**.

### Trục NGANG — các chỉ số tại cùng một lớp

| Nhóm | Cột nguồn | Câu hỏi điển hình |
|---|---|---|
| Doanh số thực đạt | `Amount_Cus` | "bán được bao nhiêu" |
| Chỉ tiêu | `MonthSaleTarget`, `YearSaleTarget` | "được giao bao nhiêu" |
| Mức hoàn thành | đạt ÷ chỉ tiêu | "đạt bao nhiêu %" |
| Khách hàng | `IsNC`, `IsRO`, `IsAC`, `NCMonth`, `ROMonth` | "bao nhiêu khách mới / mua lại" |
| Thưởng | `IsASO`, `IsCalASOBonus` | "ai đủ điều kiện thưởng" |
| Đơn hàng | `MaxCustomerOrdAmount` | "đơn lớn nhất" |

### Trục SÂU — cắt lớp xuyên qua hai trục trên

- **Thời gian**: kỳ hiện tại · so kỳ trước · xu hướng nhiều kỳ · lũy kế năm (20 kỳ chốt, 01/2025→07/2026)
- **Ba ngưỡng**: ≥100% *đạt chỉ tiêu* · ≥80% *đạt KPI* · 65% TDV / 70% quản lý *tới mức thưởng nhóm hàng*
- **Phân quyền**: `c_level` thấy tất cả · `regional_director` giới hạn miền · `qlv` chỉ đội mình

---

## 32 câu hỏi

Ký hiệu cột **Soi gì**: 🎯 chức năng thường · ⚠️ chạm bẫy đã biết · 🔒 phải bị chặn

### Nhóm A — Trục dọc: đi từ Lớp 1 xuống Lớp 4 *(tài khoản `dnh`)*

| # | Câu hỏi | Lớp | Soi gì |
|---|---|---|---|
| 1 | Chỉ tiêu tháng 7/2026 toàn công ty là bao nhiêu, đã đạt bao nhiêu phần trăm? | 1 | ⚠️ Phải ra **~50,1 tỷ**. Ra 101 tỷ = cộng chồng 2 tầng; ra 18.106 tỷ = cộng mọi dòng |
| 2 | Ba miền xếp hạng thế nào theo mức đạt KPI tháng 7/2026? | 2 | 🎯 Đủ **3 miền**, không thiếu miền nào |
| 3 | Miền Bắc có bao nhiêu quản lý vùng, ai đạt cao nhất tháng 7/2026? | 3 | ⚠️ Phải đủ **10 QLV** miền Bắc (từng thiếu MBKV12) |
| 4 | Đội của quản lý vùng MBKV1 gồm những ai, doanh số từng người tháng 7/2026? | 4 | ⚠️ Xác định đội bằng `ManagerCode` thật, không suy từ mã vùng |
| 5 | Cây doanh thu miền Bắc theo quản lý vùng và nhân viên tháng 7/2026? | 3→4 | ⚠️ Tổng cây phải khớp tổng miền, **không nhân đôi** |
| 6 | Nhân viên TM23100133 tháng 7/2026 đạt bao nhiêu phần trăm chỉ tiêu? | 4 | 🎯 Chỉ tiêu đúng của **tháng 7**, không lấy nhầm tháng khác |

### Nhóm B — Trục ngang: đổi chỉ số, giữ nguyên lớp

| # | Câu hỏi | Chỉ số | Soi gì |
|---|---|---|---|
| 7 | Tháng 7/2026 toàn công ty có bao nhiêu khách hàng mới? | `IsNC` | ⚠️ **601 khách riêng biệt** (kỳ 31/07). Cộng cả bảng = **1.178** vì `IsNC` có ở **cả hai tầng** |
| 8 | Bao nhiêu khách mua lại trong tháng 7/2026? | `IsRO` | ⚠️ **5.594 khách** (kỳ 31/07). Cột đã kéo về kho từ 31/07. Lọc nhầm sang tầng quản lý sẽ ra **0** vì `IsRO` chỉ có ở tầng nhân viên |
| 9 | Đơn hàng lớn nhất tháng 7/2026 là của khách nào, bao nhiêu tiền? | `MaxCustomerOrdAmount` | 🎯 |
| 10 | Có bao nhiêu nhân viên đủ điều kiện tính thưởng ASO tháng 7/2026? | `IsCalASOBonus` | ⚠️ ASO tính theo **số lượng khách** (MB 40/MT 35/MN 25), **không phải %** |
| 11 | Chỉ tiêu năm 2026 của miền Nam là bao nhiêu? | `YearSaleTarget` | ⚠️ Cột này **đã cộng dồn sẵn**, không cộng dồn lần nữa |
| 12 | Top 10 nhân viên bán tốt nhất tháng 7/2026? | `Amount_Cus` | 🎯 Phải lọc đúng một tầng |

### Nhóm C — Ba ngưỡng *(bẫy hay nhầm nhất)*

| # | Câu hỏi | Ngưỡng đúng | Soi gì |
|---|---|---|---|
| 13 | Tháng 7/2026 có bao nhiêu nhân viên **đạt chỉ tiêu**? | ≥100% | ⚠️ Không được trả về con số của mốc 80% hay 65% |
| 14 | Bao nhiêu người **đạt KPI** tháng 7/2026? | ≥80% | ⚠️ Mốc 80% dùng chung mọi vai trò |
| 15 | Bao nhiêu nhân viên **tới mức thưởng nhóm hàng** tháng 7/2026? | 65% TDV | ⚠️ Quản lý là **70%**, không phải 65% |
| 16 | Ai chưa đạt chỉ tiêu tháng 7/2026? | *mơ hồ* | ⚠️ Câu mơ hồ → phải nêu **cả ba mốc** và giải thích từng cái |
| 17 | Nhân viên đạt 67% chỉ tiêu thì có được thưởng không? | — | ⚠️ **Tuyệt đối không** nói "không được thưởng". 67% đã qua mốc 65% nhưng chưa đạt KPI 80%; vẫn có V15/V22/ASO và lương cơ bản đủ |
| 18 | Quản lý vùng và nhân viên có cùng ngưỡng thưởng không? | — | ⚠️ Phải nói rõ **70% vs 65%** |

### Nhóm D — Bẫy cộng chồng *(quan trọng nhất)*

| # | Câu hỏi | Soi gì |
|---|---|---|
| 19 | Tổng doanh số của tất cả nhân viên tháng 7/2026 cộng lại là bao nhiêu? | ⚠️ **33.307.889.644** (một tầng), không phải 66,62 tỷ |
| 20 | Cộng doanh số 3 miền có bằng tổng toàn công ty không? | ⚠️ Phải **khớp**, lệch = sai tầng gộp |
| 21 | Tổng chỉ tiêu của tất cả quản lý vùng cộng lại là bao nhiêu? | ⚠️ Không được cộng thêm chỉ tiêu TDV dưới quyền họ |
| 22 | Doanh số của quản lý vùng MN1 là của riêng anh ấy hay cả đội? | ⚠️ Phải trả lời rõ: **cả đội** — dòng quản lý là bản gộp |
| 23 | Đối chiếu doanh thu KPI với hóa đơn thực tế tháng 7/2026 lệch bao nhiêu? | 🎯 Công cụ đối chiếu 2 chiều |

### Nhóm E — Trục thời gian

| # | Câu hỏi | Soi gì |
|---|---|---|
| 24 | So sánh mức đạt KPI tháng 7/2026 với tháng 6/2026? | 🎯 Hai kỳ chốt liền nhau |
| 25 | Xu hướng đạt chỉ tiêu 3 tháng gần nhất? | 🎯 Ba kỳ 05/06/07 |
| 26 | Kỳ chốt số liệu KPI gần nhất là ngày nào? | ⚠️ Phải ra **31/07/2026**. Kỳ này **thay đổi liên tục** — Bravo chốt lại nhiều lần trong tháng, kỳ 30/07 đã bị xoá |
| 27 | Lũy kế năm 2026 đến giờ đạt bao nhiêu phần trăm chỉ tiêu năm? | ⚠️ Dùng `YearSaleTarget` đã cộng dồn |

### Nhóm F — Dữ liệu thiếu và bất thường *(kiểm tính trung thực)*

| # | Câu hỏi | Soi gì |
|---|---|---|
| 28 | Có nhân viên nào có doanh số nhưng không được giao chỉ tiêu không? | ⚠️ Phải tìm ra **TM26060104 — Nguyễn Văn Dũng (NTH01)**, doanh số 4.952.381đ, chỉ tiêu = 0 |
| 29 | Số liệu KPI tháng 7/2026 có đủ cả 3 miền không? | ⚠️ Đủ 3 miền. Nếu thiếu, **phải cảnh báo** thay vì trả số im lặng |
| 30 | Có nhân viên nào có chỉ tiêu nhưng chưa bán được đồng nào tháng 7/2026 không? | 🎯 Phát hiện người doanh số = 0 |

### Nhóm G — Phân quyền *(đăng nhập vai khác)*

| # | Tài khoản | Câu hỏi | Kỳ vọng |
|---|---|---|---|
| 31 | `tung.trinh` (qlv) | Đội tôi tháng 7/2026 ai chưa đạt chỉ tiêu? | ⚠️ Đúng **10 TDV** đội mình, không phải 147 |
| 32 | `tung.trinh` (qlv) | Xếp hạng tôi so với các quản lý vùng khác? | 🔒 Chỉ trả về **chính họ**, không lộ hiệu suất đồng nghiệp |
| 33 | `thuy.nguyen2` (regional_director MB) | KPI các quản lý vùng trong miền tôi tháng 7/2026? | 🎯 Đủ 10 QLV miền Bắc |
| 34 | `thuy.nguyen2` (regional_director MB) | Doanh thu miền Nam tháng 7/2026 bao nhiêu? | 🔒 **PHẢI BỊ CHẶN** — ra số MN là rò rỉ |

---

## Cách chạy

- **Mỗi câu một phiên chat mới.** Hỏi nối tiếp sẽ nhận lại câu trả lời cũ từ bộ nhớ hội thoại,
  không tính là đã kiểm.
- **Giới hạn 10 câu/phút/người** — hỏi thong thả, dồn quá sẽ dính lỗi 429.
- **Luôn nêu rõ "tháng 7/2026"**, đừng để chatbot tự hiểu "tháng này".
- Đối chiếu với đáp án gốc: `scripts/demo1_ground_truth.py`.

## Số mốc để đối chiếu nhanh *(kỳ chốt 31/07/2026 — đã kiểm chứng trên Bravo)*

> ⚠️ Bravo **chốt lại snapshot nhiều lần trong tháng**. Kỳ 30/07 đã bị xoá, thay bằng 31/07 (13.148
> dòng, 186 mã). Số dưới đây lấy theo kỳ 31/07 — xem [kiểm chứng đầy đủ](kiem_chung_13_cau_kpi_31-07.md).

| Chỉ số | Giá trị đúng | Giá trị SAI hay gặp |
|---|---|---|
| Chỉ tiêu tháng toàn công ty (OTC) | **50,97 tỷ** | 101 tỷ · 18.189 tỷ |
| **Doanh số một tầng (OTC)** | **33.307.889.644** | **66.615.779.288** = đúng gấp 2 |
| Số mã tầng quản lý | **21** | |
| Số mã tầng nhân viên | **165** | 186 (gộp cả 2 tầng) |
| Số dòng một tầng | **6.574** | 13.148 |
| Khách mới `IsNC=1` | **601 khách** | 1.178 (cộng cả 2 tầng) |
| Khách mua lại `IsRO=1` | **5.594 khách** | **0** nếu lọc nhầm tầng quản lý |
| Khách hoạt động `IsAC=1` | **45 khách** | **0** nếu lọc nhầm tầng quản lý |
| Doanh số theo vùng (`AreaCode`) | MB **42,90 tỷ** · MN **16,18 tỷ** · MT **7,53 tỷ** | có nhóm "không rõ vùng" 9,37 tỷ |
| Đạt chỉ tiêu ≥100% | **14** | |
| Đạt KPI ≥80% | **50** | |
| Tới mức thưởng (65% TDV + 70% QL) | **85** | |

**Ba con số cùng bằng 33.307.889.644**: tầng quản lý, tầng nhân viên, và doanh thu OTC tháng 7 thật từ
`vHoaDonTotal` (9.011 hoá đơn). Trùng khít đến từng đồng — đây là bằng chứng chốt cho việc bảng có 2 tầng.

> Nếu chatbot trả **66,6 tỷ** thay vì 33,31 tỷ → đang cộng chồng 2 tầng.
> Nếu trả **101 tỷ** chỉ tiêu thay vì 50,97 tỷ → cùng lỗi đó ở phía chỉ tiêu.
> Nếu trả **18.189 tỷ** → đang cộng `MonthSaleTarget` trên mọi dòng (lặp theo từng khách hàng).
> Nếu trả **24,38 tỷ** → đã lọc `IsDuplicate` khi cộng tiền, **mất 8,93 tỷ tiền thật** của 4 QLV bị
> Bravo gán nhầm cờ (MN1, MN4, MBKV12, TM25030101). Cộng tiền thì KHÔNG lọc; chỉ lọc khi đếm người.
