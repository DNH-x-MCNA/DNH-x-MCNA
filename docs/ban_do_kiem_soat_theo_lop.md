# Bản đồ kiểm soát dữ liệu theo lớp

**Trả lời yêu cầu của DNH:** làm dữ liệu theo từng lớp, kiểm soát đúng từng số ở mỗi lớp, và chỉ rõ
luồng dữ liệu đang được xử lý ở lớp nào.

> ## 📍 Vị trí hiện tại: **LỚP 3 — QUẢN LÝ VÙNG (QLV)**
>
> Lớp 4 (cá nhân) đã đóng. Lớp 1–2 đã tự kiểm xong và đang chờ DNH soát.
> **Toàn bộ công việc đang mở đều nằm ở Lớp 3.**

---

## 1. Bốn lớp và luồng dữ liệu

Xây và kiểm **từ dưới lên**: cá nhân → quản lý → vùng → toàn công ty. Lý do: lỗi ở lớp dưới sẽ lan
lên trên, nên kiểm lớp trên trước là vô nghĩa.

> **Lưu ý cách đánh số:** lớp càng chi tiết thì số càng lớn. **Lớp 4 nằm dưới cùng** (từng cá nhân),
> **Lớp 1 trên cùng** (toàn công ty). Dữ liệu chảy **từ dưới lên**.

```
              ┌────────────────────────────────────────┐
              │  Lớp 1 — TOÀN CÔNG TY                  │   ✅ tự kiểm xong, lệch 0đ
              │  Doanh thu · Công nợ · KPI · Tồn kho   │   ⏳ chờ anh Long soát
              └───────────────────▲────────────────────┘
                                  │  cộng 3 miền
              ┌───────────────────┴────────────────────┐
              │  Lớp 2 — VÙNG                          │   ✅ tự kiểm xong, lệch 0đ
              │  Miền Bắc · Miền Trung · Miền Nam      │   ⏳ chờ anh Long soát
              └───────────────────▲────────────────────┘
                                  │  cộng theo AreaCode
              ┌───────────────────┴────────────────────┐
              │  Lớp 3 — QUẢN LÝ VÙNG (QLV)            │   📍 ĐANG XỬ LÝ
              │  21 quản lý có cấp dưới                │   Tự kiểm xong; chờ DNH
              └───────────────────▲────────────────────┘   chốt phạm vi + cấp t/khoản
                                  │  cộng theo ManagerCode thật
              ┌───────────────────┴────────────────────┐
              │  Lớp 4 — CÁ NHÂN (TDV)                 │   ✅ ĐÓNG 20/07
              │  148 nhân viên · 147 có chỉ tiêu       │   Cộng tay khớp 100%
              └───────────────────▲────────────────────┘
                                  │
                    ┌─────────────┴──────────────┐
                    │  BRAVO — nguồn gốc          │
                    │  FACT_TongHopKhachHang      │
                    │  DIM_NhanVien · vHoaDon*    │
                    │  usp_DeptAccDueDate_GetData │
                    └─────────────────────────────┘
```

**Đọc sơ đồ:** mỗi mũi tên đi lên là một phép cộng gộp, và mỗi phép cộng đó đều có bài kiểm riêng —
xem mục 3 (Ranh giới giữa các lớp).

---

## 2. Kiểm soát từng số ở mỗi lớp

### Lớp 4 — Cá nhân (TDV) · ✅ ĐÓNG

| Hạng mục | Nguồn số gốc | Cách kiểm | Kết quả |
|---|---|---|---|
| Số lượng TDV | `FACT_TongHopKhachHang` ⋈ `DIM_NhanVien` | Đếm trực tiếp trên Bravo *(29/07)* | **148 người** |
| Doanh số tháng từng TDV | `FACT_TongHopKhachHang.Amount_Cus` | Cộng tay 16 dòng của 1 TDV mẫu (`DNH00634`) | Khớp **100%** |
| Chỉ tiêu tháng | `FACT_TongHopKhachHang.MonthSaleTarget` | Đối chiếu bảng chỉ tiêu vùng chính thức | Khớp |
| Mã nhân viên | `DIM_NhanVien.EmployeeCode` | 148 TDV không mã nào trùng; 182/182 mã JOIN được | **0 mã bị loại oan** |

**Đối chiếu 148 và 147 — hai con số đều đúng, khác phạm vi:**

| | |
|---|---|
| Tổng TDV có mặt trong kỳ | **148** |
| TDV **có chỉ tiêu > 0** → được tính KPI | **147** ← con số dùng trong báo cáo |
| Chênh lệch | **1 người** |

> 🟠 **Phát hiện mới cần DNH xác nhận** *(29/07)*: nhân viên `TM26060104` — **Nguyễn Văn Dũng (NTH01)**
> có doanh số thật **4.952.381đ** nhưng **chỉ tiêu tháng = 0**. Người này đang bán hàng mà không được
> đặt chỉ tiêu, nên không xuất hiện trong mọi thống kê KPI. Nếu là nhân viên mới chưa kịp giao chỉ tiêu
> thì cần bổ sung; nếu thuộc diện không giao chỉ tiêu thì cần xác nhận để hệ thống ghi nhận đúng.

**Bẫy đã xử lý ở lớp này:**
- Mã trên hóa đơn (`EmpDMSCode`) **khác** mã chuẩn (`EmployeeCode`) — từng nối nhầm cột
- Cờ `IsDuplicate` sai trong dữ liệu gốc làm **2 quản lý thật bị ẩn** khỏi báo cáo
- Nhân viên thiếu trong `DIM_NhanVien` — bổ sung đường tra dự phòng `DMSSX_NhanVien`

---

### Lớp 3 — Quản lý vùng (QLV) · 📍 ĐANG XỬ LÝ

**Đây là lớp khó nhất và là nơi mọi việc đang mở.** Lý do: quan hệ "ai quản ai" không nằm sẵn thành
một cột sạch, và mọi lỗi phân quyền đều biểu hiện ở đây.

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Số lượng QLV | ✅ **21 người** có cấp dưới | Đếm trực tiếp trên Bravo 29/07 theo `ManagerCode` |
| Xác định đội của QLV | ✅ Đã sửa | Dùng `ManagerCode` thật từ Bravo, **không** suy đoán theo mã vùng như trước |
| Tổng đội = tổng TDV dưới quyền | ✅ Khớp tuyệt đối | |
| Không cộng chồng TDV + QLV | ✅ Đã sửa | QLV **đã là** tổng của TDV — cộng chung là gấp đôi. Đã dính 3 chỗ |
| Ngưỡng KPI riêng cho cấp quản lý | ✅ Đã sửa | Quản lý **70%**, nhân viên **65%** — trước dùng chung 80% |
| Phạm vi xem của QLV | 🔴 **Chờ DNH chốt** | Đội mình hay cả miền? Tồn kho/công nợ có thuộc quyền? |
| QLV tự nghiệm thu đội mình | 🔴 **Chờ DNH cấp tài khoản** | Đã đề nghị từ 16/07 |

**Ba lỗ hổng phân quyền phát hiện ở lớp này** *(đều do MCNA tự tìm, không phải khách báo)*:

| Lỗ hổng | Biểu hiện |
|---|---|
| Xem được doanh thu cả miền | Hỏi "doanh thu tháng này" nhận số của **cả 10 đội** thay vì riêng đội mình |
| Tự nâng quyền qua báo cáo chi phí AI | Đọc được lịch sử truy vấn **toàn công ty** |
| Quyền suy từ tên tài khoản | Tài khoản tên `dnh.marketing` tự nhiên có quyền Ban điều hành |

Hiện **tạm chặn 9 báo cáo** với tài khoản QLV theo nguyên tắc *thà từ chối còn hơn lộ nhầm* — sẽ mở
lại đúng phạm vi ngay khi DNH chốt.

---

### Lớp 2 — Vùng (3 miền) · ✅ Tự kiểm xong, ⏳ chờ DNH soát

| Hạng mục | Nguồn số gốc | Kết quả kiểm |
|---|---|---|
| Doanh thu theo miền | `vHoaDonTotal` / `vHoaDonETCTotal` | Khớp tổng, **lệch 0 đồng** |
| Công nợ theo miền | `usp_DeptAccDueDate_GetData` (thủ tục gốc DNH) | **Lệch 0 đồng**, 9.787 dòng |
| Chỉ tiêu theo miền | `dim_targetvungmien` | Tổng **50.967.586.921đ** — khớp từng đồng |

**Bẫy đã xử lý ở lớp này:**
- Kênh **Modern Trade** thuộc miền Nam nhưng tổ chức khác các đội thường → từng làm **hụt 6,79 tỷ** chỉ tiêu MN
- Mã kênh `GT`/`MT` bị hiểu nhầm thành `OTC`/`ETC`
- Cảnh báo hằng ngày từng lộ mã khách hàng thuộc vùng khác

---

### Lớp 1 — Toàn công ty · ✅ Tự kiểm xong, ⏳ chờ DNH soát

| Hạng mục | Kết quả kiểm |
|---|---|
| Doanh thu | Khớp hóa đơn gốc Bravo |
| Công nợ | 180,48 tỷ dư nợ · 77,07 tỷ quá hạn — **lệch 0 đồng** so với báo cáo gốc |
| KPI | 147 người, đủ 3 miền, tổng chỉ tiêu 50,97 tỷ |
| Tồn kho | Khớp thủ tục tồn kho gốc |

**Lỗi nghiêm trọng nhất của kỳ nằm ở ranh giới Lớp 2 → Lớp 1** *(sửa 29/07)*:

DNH ghi số liệu tháng thành **nhiều đợt theo từng miền** — tháng 7 có 2 đợt: 27/07 ghi MB+MN, 28/07 chỉ
ghi MT. Hệ thống lấy đợt mới nhất nên **chỉ thấy miền Trung**, báo *"toàn đội đạt 48,7%"* mà thực chất
chỉ là 29/147 người. **Thiếu 43,97 tỷ chỉ tiêu và không hề có cảnh báo.**

| | Trước | Sau |
|---|---|---|
| Nhân viên tính KPI | 29 | **147** |
| Miền có mặt | Chỉ MT | **Đủ 3** |
| Tổng chỉ tiêu | 7,00 tỷ | **50,97 tỷ** |

Đã sửa ở **cả 3 hệ thống** (chatbot · báo cáo email · công cụ đối chiếu) và bổ sung cảnh báo bắt buộc
khi thiếu miền.

---

## 3. Ranh giới giữa các lớp — nơi số dễ sai nhất

Kiểm theo lớp có giá trị nhất ở **chỗ nối** giữa hai lớp, vì đó là nơi số bị cộng thiếu hoặc cộng thừa.

| Ranh giới | Phép kiểm | Kết quả |
|---|---|---|
| Lớp 4 → Lớp 3 | Tổng doanh số TDV của một đội **=** số báo cáo của QLV đó | ✅ Lệch 0 |
| Lớp 3 → Lớp 2 | Tổng các đội trong miền **=** doanh thu miền | ✅ Lệch 0 |
| Lớp 2 → Lớp 1 | Tổng 3 miền **=** số toàn công ty | ✅ Lệch 0 |
| Lớp 1 ↔ nguồn gốc | Số toàn công ty **=** hóa đơn gốc Bravo | ✅ Lệch 0 |

**→ 15/15 hạng mục đạt, sai lệch 0 đồng ở mọi ranh giới.**

> ⚠️ **Cạm bẫy đã dính 3 lần:** Lớp 3 (QLV) **đã là** tổng của Lớp 4 (TDV). Cộng hai lớp lại với nhau
> cho ra con số **gấp đôi** mà vẫn trông hợp lý. Khi đọc bất kỳ báo cáo nào, phải biết nó đang ở lớp
> nào — đây chính là lý do DNH yêu cầu chỉ rõ lớp, và yêu cầu đó là đúng.

---

## 4. Ai nghiệm thu lớp nào

| Lớp | MCNA tự kiểm | DNH nghiệm thu | Trạng thái |
|---|---|---|---|
| Lớp 4 — Cá nhân | ✅ Xong 20/07 | Qua QLV *(cần tài khoản)* | 🔴 Chờ |
| Lớp 3 — Quản lý | ✅ Xong | **QLV tự kiểm đội mình** *(cần tài khoản)* | 🔴 Chờ |
| Lớp 2 — Vùng | ✅ Xong | Anh Long | ⏳ Chờ soát |
| Lớp 1 — Công ty | ✅ Xong | Anh Long | ⏳ Chờ soát |

**Đề nghị cụ thể:** DNH chỉ định **1–2 quản lý vùng** nhận tài khoản để tự kiểm số liệu đội mình. Không
có bước này thì sai lệch (nếu còn) chỉ lộ ra ở nghiệm thu tháng 9 — lúc đó sửa tốn gấp nhiều lần.

---

## 5. Câu trả lời ngắn gọn cho DNH

> **Luồng dữ liệu đang được xử lý ở Lớp 3 — Quản lý vùng.**
>
> Lớp 4 (cá nhân) đã đóng từ 20/07. Lớp 1 và 2 đã tự kiểm xong với sai lệch 0 đồng, đang chờ anh Long
> soát. **Toàn bộ việc đang mở đều nằm ở Lớp 3**: ba lỗ hổng phân quyền vừa vá xong, phạm vi xem của
> quản lý vùng đang chờ DNH chốt, và cần tài khoản để chính quản lý vùng tự nghiệm thu đội mình.
>
> Mỗi ranh giới giữa hai lớp đều có phép kiểm riêng và hiện **lệch 0 đồng** ở cả 4 ranh giới.
