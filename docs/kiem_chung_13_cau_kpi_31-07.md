# Kiểm chứng 13 câu hỏi KPI — 31/07/2026

Toàn bộ số dưới đây truy **trực tiếp Bravo** sáng 31/07, không lấy từ kho cục bộ, không suy đoán.

> ⚠️ **Snapshot tháng 7 đã đổi kỳ ngay hôm nay.** Sáng 31/07 Bravo chốt lại: kỳ `2026-07-30`
> **không còn**, thay bằng `2026-07-31` (13.148 dòng, 186 mã NV). Chatbot lúc trả lời còn đang đọc kỳ
> 30/07. Đây là lý do các con số của tôi lệch 1–2 đơn vị so với chatbot, **không phải lỗi logic**.

---

## Bảng chấm điểm

| # | Câu hỏi | Chatbot | Kết luận |
|---|---|---|---|
| 1 | Bao nhiêu người đạt KPI | 49/174 | 🟡 **Gần đúng** — số thật 50/172 (lệch do đổi kỳ) |
| 2 | Bao nhiêu người tới mức thưởng | 87/174 | 🟡 **Gần đúng** — số thật 85 |
| 3 | Ai chưa đạt chỉ tiêu | 161/174 | 🟡 **Gần đúng** — số thật 158/172 |
| 4 | Đạt 67% có được thưởng không | TDV có, QLV không | ✅ **Đúng**, phân biệt đúng 2 ngưỡng |
| 5 | QLV và NV cùng ngưỡng không | Khác: 65% / 70% | ✅ **Đúng** |
| 6 | **Tổng doanh số cộng lại** | **56,88 tỷ** | 🔴 **SAI — cộng chồng 2 tầng.** Số thật **33,31 tỷ** |
| 7 | Tổng chỉ tiêu 17 QLV | 37,96 tỷ | 🟡 Chưa kiểm được đúng nhóm 17 mã |
| 8 | MN1 là cá nhân hay cả đội | Mã ảo kênh Modern Trade | ✅ **ĐÚNG** — đã xác minh tận nơi |
| 9 | **Cộng 3 miền có bằng tổng không** | "Bất thường, gấp 6 lần" | 🔴 **BÁO ĐỘNG GIẢ** — so 1 tháng với 1 ngày |
| 10 | **Đối chiếu KPI vs hoá đơn** | "Lệch 601%, không đáng tin" | 🔴 **BÁO ĐỘNG GIẢ** — cùng lỗi câu 9 |
| 11 | Xu hướng 3 tháng | 21 → 26 → 13 | 🟡 Đúng số, nhưng kỳ tháng 7 chưa trọn |
| 12 | Lũy kế năm | "OTC chưa có chỉ tiêu T8–T12" | ✅ **Đúng và có giá trị** |
| 13 | Có ai có chỉ tiêu mà 0 doanh số | "Không có" | ✅ **Đúng** — kiểm lại đúng bằng 0 |
| 14 | Có ai có doanh số mà không chỉ tiêu | 3 mã | ✅ Đúng 3 mã, ❌ nhưng **tra được tên cả 3** |
| 15 | Đủ 3 miền không | 98/34/41 + **13 không rõ vùng** | 🔴 **13 mã "không rõ" là bản ghi ảo**, không phải lỗi |

---

## 🔴 Phát hiện lớn nhất: cộng chồng đúng **gấp đôi**, không xê dịch một đồng

Tách bảng KPI làm 2 tầng — mã nào từng đứng làm `ManagerCode` của người khác thì thuộc tầng quản lý:

| | Số mã | Cộng `Amount_CT` |
|---|---:|---:|
| Tầng quản lý | 21 | **33.307.889.644** |
| Tầng nhân viên | 165 | **33.307.889.644** |
| Cộng tuốt cả bảng | 186 | **66.615.779.288** |
| **Doanh thu OTC tháng 7 THẬT** (`vHoaDonTotal`) | — | **33.307.889.644** — 9.011 HĐ |

Ba con số **trùng khít đến từng đồng**. Đây không còn là suy đoán: bảng KPI chứa **cùng một khoản
doanh thu ghi hai lần** — một lần gắn TDV, một lần gắn quản lý của họ. Cộng cả bảng luôn ra **đúng
gấp 2 lần** doanh thu thật.

> **Quy tắc bất di bất dịch:** muốn ra tổng, phải **chọn một tầng**. Cộng cả bảng = sai gấp đôi,
> lần nào cũng thế.

Chatbot trả **56,88 tỷ** vì đã loại bản ghi ảo nhưng **vẫn gộp hai tầng** → vẫn sai, chỉ bớt sai hơn.

---

## 🔴 Hai câu báo động giả — nguy hiểm nhất trong cả bộ

Câu 9 và 10 chatbot kết luận:

> *"Cộng dồn cao gấp ~6 lần hóa đơn thực tế… Số liệu KPI hiện tại **không đáng tin cậy** để dùng
> so sánh/báo cáo cho đến khi bộ phận kỹ thuật kiểm tra lại."*

**Không có gì bất thường cả.** Chatbot đã so:

| Vế trái | Vế phải |
|---|---|
| KPI **lũy kế cả tháng 7** — 24,86 tỷ | Hoá đơn **riêng ngày 30/07** — 4,14 tỷ |

Đã kiểm: `SUM(Amount9) WHERE DocDate='2026-07-30'` = **4.138.270.544đ / 522 HĐ** — đúng bằng con số
chatbot gọi là "tổng hóa đơn toàn công ty". Đó là **một ngày**, không phải cả tháng.

So đúng kỳ thì: tầng TDV **24,59 tỷ** / doanh thu OTC cả tháng **33,31 tỷ** = **74%** — thấp hơn tổng,
đúng như kỳ vọng, vì tầng TDV không gồm kênh ảo, CS, TK, CTV.

**Vì sao đây là lỗi nặng nhất:** ba câu hỏi khác đều trả lời tử tế, rồi hai câu này quay ra bảo khách
rằng dữ liệu của chính họ hỏng và cần gọi kỹ thuật. Một lời cảnh báo sai kiểu này phá sạch niềm tin
vào cả 13 câu còn lại.

---

## 🔴 "13 mã không xác định vùng" — không phải lỗi dữ liệu

Chatbot báo 13 mã ôm **9,37 tỷ** không rõ vùng, đề nghị kiểm tra. Đối chiếu:

| Nhóm `IsDuplicate=1` trong `DIM_NhanVien` | Số mã | Doanh số |
|---|---:|---:|
| QLV ảo | 4 | 8.926.733.428 |
| TDV ảo | 9 | 444.734.022 |
| **Cộng** | **13** | **9.371.467.450** |

Khớp **đến từng đồng** với "13 mã không rõ vùng" của chatbot. Chúng không thiếu vùng vì lỗi — chúng
thiếu vùng vì `dim_nhanvien` không gán vùng cho bản ghi loại này.

### ⚠️ Nhưng tuyệt đối **không được lọc bỏ** chúng

Đây là chỗ tôi suýt sửa sai. Chú thích trong [`report_templates.py:1501-1508`](../../DNH-x-MCNA/backend/report_templates.py)
cảnh báo rằng `IsDuplicate` **gán nhầm 4 QLV THẬT**. Kiểm lại trên Bravo, kỳ 31/07, tầng quản lý:

| Cách tính | Kết quả |
|---|---:|
| **Không** lọc `IsDuplicate` | **33.307.889.644** — đúng bằng doanh thu OTC thật |
| **Có** lọc `IsDuplicate` | 24.381.156.216 — **mất 8.926.733.428đ (26,8%) tiền thật** |

Bốn mã đó — `MN1` (Kênh MT), `MN4` (Chợ sỉ), `MBKV12`, `TM25030101` — là **quản lý vùng thật ôm doanh
thu thật**, chỉ bị Bravo gán nhầm cờ trùng lặp. Lọc chúng đi là xoá gần 9 tỷ khỏi báo cáo.

**Quy tắc đúng, tuỳ mục đích:**

| Mục đích | `IsDuplicate` |
|---|---|
| Tính **tổng tiền** (doanh số, doanh thu vùng/công ty) | **KHÔNG lọc** — lọc là mất tiền thật |
| **Đếm người / xếp hạng cá nhân** (ai đạt KPI, top NV) | **Có lọc** — mã bóng không phải người thật |

**Và vùng miền thì không hề thiếu.** Cột `AreaCode` nằm ngay trên dòng KPI:

| Vùng | Số mã | Doanh số |
|---|---:|---:|
| MB | 102 | 42.904.435.740 |
| MN | 49 | 16.181.950.686 |
| MT | 35 | 7.529.392.862 |
| *(rỗng)* | **0** | — |

**Không một mã nào thiếu vùng.** Chatbot phải vòng qua `dim_nhanvien.area_code` nên mới rơi 13 mã.

Điều này khiến đề xuất kéo cột `AreaCode` về kho (trong [rà soát đồng bộ](ra_soat_dong_bo_bang_kpi.md))
trở nên **bắt buộc chứ không còn là tiện nghi**: hiện chỉ có hai lựa chọn, hoặc chấp nhận một nhóm
"chưa rõ vùng" 9,37 tỷ, hoặc lọc bỏ và mất 8,93 tỷ tiền thật. Kéo `AreaCode` về là **lối thoát duy
nhất không phải đánh đổi**.

---

## ✅ Những chỗ chatbot làm đúng, đáng ghi nhận

**MN1** — chatbot bảo là "nhân viên ảo, kênh Modern Trade". Tra `DIM_NhanVien`:

```
EmployeeCode=MN1 | Name="Kênh MT" | IsDuplicate=1 | PositionCode=QLV | AreaCode=MN | DMSId=ASM01
```

Đúng cả bốn ý: mã ảo, kênh MT, miền Nam, đã đánh dấu trùng. Không hề bịa.

⚠️ Chỉ một chỗ chatbot nói chưa chuẩn: *"được đánh dấu là bản ghi trùng/không dùng để tính KPI"*.
Cờ trùng lặp đó là **Bravo gán nhầm** — MN1 ôm **5,29 tỷ doanh thu THẬT** và bắt buộc phải được tính
vào tổng công ty. Chỉ nên loại khi **đếm đầu người**, không được loại khi **cộng tiền**.

**"Không có ai có chỉ tiêu mà chưa bán được đồng nào"** — kiểm lại: đúng bằng **0**.

**"OTC chưa có chỉ tiêu tháng 8–12"** — đúng, và đây chính là hệ quả của việc `YearSaleTarget` chưa
được kéo về kho. Chatbot từ chối tính % năm là hành vi **trung thực**, không phải yếu kém.

---

## ❌ Ba mã "lạ" — tra được tên cả ba

Chatbot bảo 2/3 mã "không tra được tên". Bravo có đủ:

| Mã | Tên trong `DIM_NhanVien` | Chức vụ | Vùng | Doanh số |
|---|---|---|---|---:|
| `TRONGTDV2` | QLV Sâm (Hậu Giang + Long An) | TDV | MN | 33.453.229 |
| `TM26060104` | Nguyễn Văn Dũng (NTH01) | TDV | MT | 4.952.381 |
| `TM24050201.` | Nguyễn Phương Nam (QLV) | TDV | MN | 1.850.794 |

Kho cục bộ tra không ra → `dim_nhanvien` bên kho thiếu 2 mã này hoặc đã bị lọc mất. Cần kiểm riêng.

Nhân tiện, **dữ liệu gốc của DNH cũng có mâu thuẫn**: hai mã có tên ghi "QLV" nhưng `PositionCode`
lại là `TDV`. Nên hỏi lại DNH.

---

## ⚠️ Bẫy chết người: `MonthSaleTarget` lặp trên **mọi dòng**

| Số giá trị chỉ tiêu khác nhau / mỗi NV | Số NV |
|---|---|
| 1 (lặp y hệt trên mọi dòng khách) | 183 |
| 0 (không có chỉ tiêu) | 3 |

Nghĩa là **`SUM(MonthSaleTarget)` luôn sai**. Cộng cả bảng ra **18.189 tỷ** — trong khi chỉ tiêu OTC
tháng 7 của cả công ty là **50,97 tỷ**. Sai gấp **357 lần**.

Phải dùng `MAX(MonthSaleTarget)` sau khi `GROUP BY EmployeeCode`. Tôi đã tự dính bẫy này ở lần chạy
đầu và ra kết quả "không ai đạt 65%" — hoàn toàn vô lý, nhờ đó mới phát hiện.

✅ **Chỗ này chatbot KHÔNG sai** — `schema_context.py:129` đã ghi sẵn *"month_sale_target (target
thang, MAX vi lap lai moi dong)"*. Đó là lý do các con số ngưỡng của nó chỉ lệch 1–2 đơn vị so với
tôi. Ghi lại đây làm cảnh báo cho người viết SQL tay, **không phải việc cần sửa**.

---

## Số đúng để dùng — tháng 7/2026, kỳ 31/07

Đã loại `IsDuplicate`, dùng `MAX(MonthSaleTarget)`, tách tầng:

| Tầng | Số NV | ≥100% | ≥80% | ≥65% | ≥70% | Doanh số | Chỉ tiêu | Đạt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **TDV** | 148 | **14** | **48** | **78** | 67 | 24,59 tỷ | 35,94 tỷ | 68,4% |
| **Quản lý & khác** | 24 | **0** | **2** | 10 | **7** | 32,65 tỷ | 50,31 tỷ | 64,9% |
| Gộp | 172 | 14 | 50 | — | — | — | — | — |

- **Tới mức thưởng nhóm hàng** = 78 (TDV ≥65%) + 7 (quản lý ≥70%) = **85 người**
- **Chỉ tiêu tầng quản lý 50,31 tỷ** ≈ **98,7%** chỉ tiêu OTC công ty tháng 7 (50,97 tỷ) → xác nhận
  tầng quản lý chính là tầng cộng dồn cấp công ty
- **Không một cấp quản lý nào đạt chỉ tiêu**, chỉ 2/24 đạt mốc KPI 80% — chênh lệch rõ rệt so với
  TDV (14 đạt chỉ tiêu, 48 đạt KPI). Đáng đưa ra bàn với DNH

---

## Việc cần làm

| # | Việc | Vì sao gấp |
|---|---|---|
| 1 | Ghi quy tắc **"chọn một tầng, không cộng cả bảng"** vào `schema_context.py` | Sai gấp 2 lần, đã tái diễn ở 3 câu. Hiện `schema_context.py` **chưa hề có** cảnh báo này |
| 2 | Dạy chatbot **luôn nói rõ kỳ so sánh** (tháng vs ngày) trước khi kết luận "bất thường" | Nguồn gốc của 2 câu báo động giả |
| 3 | Ghi rõ **`IsDuplicate` lọc hay không là tuỳ mục đích** | Lọc nhầm chỗ = mất 8,93 tỷ tiền thật |
| 4 | Kéo cột `AreaCode` về kho | Lối thoát duy nhất không phải đánh đổi (xem trên) |
| 5 | Đồng bộ lại kho — kỳ đã đổi 30/07 → 31/07 | Kho đang giữ kỳ Bravo đã xoá |
| 6 | Hỏi DNH: vì sao tên ghi "QLV" mà `PositionCode` là `TDV` | Dữ liệu gốc mâu thuẫn |

> Việc 1–3 chỉ sửa **một file `schema_context.py`**, không đụng code đang chạy, không cần deploy lại
> backend logic — nhưng chặn được cả 3 câu trả lời sai.
