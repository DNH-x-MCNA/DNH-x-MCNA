# Điều tra v24 — khách giảm tần suất / AOV / SKL so 3 tháng trước

*23/09/2026. Người chấm UAT ghi: "Không khớp dữ liệu về doanh thu, chatbot trả về các khách hàng
không có trong query". Câu V24, checker **S62**, tool `get_customer_product_coverage`
(`mode='customer'`, `lookback_months=3`).*

Toàn bộ điều tra chạy cục bộ trên `backend/warehouse.db`, **không gọi model trả phí**.

## Cửa sổ thời gian KHỚP — đừng sửa nhầm chỗ này

Chạy lại phép tính của tool với `as_of_date='2026-09-23'`, `lookback_months=3`:

```
current_period : {'from': '2026-07-01', 'to': '2026-09-23'}   (85 ngày)
previous_period: {'from': '2026-04-07', 'to': '2026-06-30'}   (85 ngày)
```

Trùng khít checker S62 (`CurStart` = đầu quý chứa `@MonthStart`; `PreStart = PreEnd - (SoNgay-1)`),
và trùng nhãn "Kỳ trước (07/04–30/06)" chatbot hiển thị. **Cửa sổ không phải nguyên nhân.**

## Dấu hiệu định hướng: kỳ NÀY khớp, kỳ TRƯỚC lệch toàn bộ

| Chỉ số | Kỳ trước — chatbot | Kỳ trước — S62 | Kỳ này — chatbot | Kỳ này — S62 |
|---|---:|---:|---:|---:|
| Doanh thu | 3,71 tỷ | **4,07 tỷ** | 3,28 tỷ | 3,28 tỷ ✓ |
| Số đơn | 608 | 607 | 719 | 719 ✓ |
| Khách mua | 349 | **292** | 391 | 391 ✓ |
| AOV | 6,09 tr | **6,705 tr** | 4,56 tr | 4,564 tr ✓ |
| Tần suất/khách | 1,74 | **2,08** | 1,84 | 1,84 ✓ |

Kỳ hiện tại khớp tuyệt đối cả 5 chỉ số. Mọi sai lệch nằm ở kỳ trước → nguyên nhân phải là thứ chỉ
tác động lên kỳ quá khứ.

---

## Phát hiện 1 — nhân bản dòng do join `dim_nhanvien` không khử trùng 🔴

`customer_product_coverage` join `LEFT JOIN dim_nhanvien nv ON nv.dmsid=v.employee_code` mà **không
khử trùng**. Trong `dim_nhanvien` có **6 giá trị `dmsid` bị trùng**:

| dmsid | Số dòng | employee_code |
|---|---:|---|
| `DNH00601` | 2 | `DNH00601`, `TM25010129` |
| `DNH01250` | 2 | `DNH01250`, `TM25010121` |
| `TM23110109` | 2 | `TM23110109`, `TM23110109.` ← thừa dấu chấm |
| `TM24050201` | 2 | `TM24050201`, `TM24050201.` |
| `TM24060301` | 2 | `TM24060301`, `TM24060301.` |

Mỗi dòng hóa đơn của các nhân viên này bị **đếm hai lần**. Đo trên kỳ hiện tại, kênh OTC:

| | Doanh thu |
|---|---:|
| Không join | 99.294.041.118 |
| Có join `dim_nhanvien` | 99.547.872.578 |
| **Phồng lên** | **+253.831.460 (+0,256%)** |

Con số này **khớp đến từng đồng** với chênh lệch giữa `scope_totals` của tool và SQL trực tiếp trên
cùng cửa sổ (183.242.330.033 − 182.988.498.573 = 253.831.460). Nguyên nhân được giải thích trọn vẹn.

Checker S62 khử trùng đúng cách:

```sql
n AS (SELECT DMSId, EmployeeCode FROM (
    SELECT DMSId, EmployeeCode,
           ROW_NUMBER() OVER(PARTITION BY DMSId ORDER BY ISNULL(IsDuplicate,0)) rn
    FROM dbo.DIM_NhanVien WHERE DMSId IS NOT NULL) x WHERE rn = 1)
```

**Đây là lỗi thật, không phải bất đồng định nghĩa.** Ảnh hưởng mọi kỳ, mọi vai — chỉ là 0,256% nên
không ai thấy bằng mắt.

### ✅ Đã sửa (23/09)

Thêm `_NV_THEO_DMSID` — khử trùng bằng `ROW_NUMBER() OVER (PARTITION BY dmsid ORDER BY
COALESCE(is_duplicate,0), employee_code)`, ưu tiên dòng **không** bị đánh cờ trùng, đúng cách S62
làm. Áp vào cả hai chỗ join trong `customer_product_coverage`.

Đo lại trên kho thật sau khi sửa, kỳ hiện tại:

| | Doanh thu |
|---|---:|
| Tool trước khi sửa | 183.242.330.033 |
| **Tool sau khi sửa** | **182.988.498.573** |
| SQL trực tiếp | 182.988.498.573 |

Khớp đến từng đồng. Test khóa: `tests/test_chot_doi_ky_qua_khu.py::test_khu_trung_dmsid_khong_nhan_ban_dong_hoa_don`
(dựng đúng hình `TM23110109` / `TM23110109.`, xác nhận join thô làm phồng gấp đôi rồi mới kiểm bản sửa).

## Phát hiện 2 — tập khách kỳ trước định nghĩa khác nhau

Checker dựng `owner` **chỉ từ cửa sổ HIỆN TẠI**, rồi ép cả `cur` lẫn `pre` phải nằm trong `scope`:

```sql
owner AS (SELECT s.CustomerCode, MAX(s.EmpDMSCode) ...
          WHERE s.DocDate >= w.CurStart AND s.DocDate <= w.CurEnd)   -- chỉ kỳ NÀY
pre   AS (... AND s.CustomerCode IN (SELECT CustomerCode FROM scope))
```

Tool thì không ràng buộc như vậy — đã kiểm: `scope_totals.previous.customers` = **11.536** đúng bằng
số khách mua trong cửa sổ đó, còn `current.customers` = 11.123. Tool đếm mọi khách mua từng kỳ.

Đo lại trên nhóm khách `BDI*` (xấp xỉ đội trong ảnh UAT):

| Cách đếm khách kỳ trước | Số khách |
|---|---:|
| Mọi khách mua kỳ trước (cách tool) | **189** |
| Chỉ khách mua kỳ trước **và** kỳ này (cách checker) | **118** |

Đúng hình dạng 349 vs 292 trong UAT.

### Đây cũng là lời giải cho "chatbot trả về khách không có trong query"

Hai danh sách **rời nhau hoàn toàn** — và đó là hệ quả cấu trúc, không phải lỗi:

- Chatbot liệt `BDI00357`, `BDI00202`, `BDI00348`… tất cả đều **kỳ này = 0** (đã dừng mua hẳn).
- Checker liệt `BDI00271`, `BDI00278`, `BDI00281`… tất cả đều **kỳ này > 0**.

Vì `owner` chỉ lấy từ cửa sổ hiện tại, khách **dừng mua hoàn toàn không thể xuất hiện trong kết quả
checker** — họ không có `EmpDMSCode` ở kỳ này nên không quy được về quản lý nào.

⚠️ **Cần DNH/PMO chốt:** câu hỏi V24 là *"khách nào giảm tần suất mua, AOV hoặc SKU/đơn"*. Khách
dừng mua hẳn là ca giảm nặng nhất, nhưng checker loại họ **theo thiết kế**. Đừng vội nắn tool theo
checker ở điểm này — rất có thể checker mới là bên có điểm mù.

## Phát hiện 3 — quy đội theo DÒNG vs theo KHÁCH

| | Cách quy |
|---|---|
| **Tool** | Lọc **từng dòng hóa đơn** theo `employee_code IN (đội tại as_of)` — xem `_employee_scope_clause` |
| **Checker** | Quy **khách** về quản lý theo `EmpDMSCode` kỳ hiện tại, rồi tính **toàn bộ** doanh thu kỳ trước của khách đó, bất kể ai bán |

Tool gọi `_employee_scope_clause(..., as_of=as_of_date)` **một lần**, rồi áp chung cho **cả hai kỳ**.
Nghĩa là doanh thu kỳ trước chỉ tính phần do **nhân viên đang thuộc đội hôm nay** bán ra; phần do
người đã rời đội bán thì mất.

Đây là hướng giải thích doanh thu kỳ trước của chatbot **thấp hơn** checker (3,71 vs 4,07 tỷ), trong
khi số khách lại **cao hơn** (349 vs 292) — hai hiệu ứng ngược chiều nhau, khớp đúng những gì quan sát.

Bản thân code đã cảnh báo về vùng này: `FACT_TongHopKhachHang` chỉ giữ lịch sử phân công đội khoảng
**90 ngày**, mà kỳ trước kết thúc 30/06 — cách `as_of` 85 ngày, sát mép.

### ✅ Đã xác minh bằng số (23/09, sau khi có `manager_code`)

Lượt UAT là của `thuan.pham` — vai `qlv`, phạm vi **MT**, `employee_code` = **`TM23110128`**. Khớp
với việc khách trong ảnh toàn mã `BDI*` (Bình Định). Đội có **7 nhân viên** tại mốc 23/09.

Chạy lại kỳ trước (07/04–30/06) cho đúng đội đó trên kho dev:

| Cách tính | Doanh thu | Khách | Đơn |
|---|---:|---:|---:|
| **Cách TOOL** — lọc từng dòng theo đội hôm nay | **3.705,7 tr** | **349** | **608** |
| **Cách CHECKER** — quy khách, không lọc người bán | 4.029,4 tr | 273 | 584 |
| Chênh | +323,8 tr | −76 khách | |

**Dòng "cách TOOL" khớp chính xác con số chatbot hiển thị trong ảnh UAT: 3,71 tỷ · 349 khách ·
608 đơn.** Không còn là suy luận từ code.

Dòng "cách CHECKER" ra 4.029,4 tr / 273 khách so với checker thật 4.069,8 tr / 292 khách — lệch nhẹ
vì kho dev chỉ có dữ liệu đến 15/09 nên tập `scope` (khách mua ở kỳ này) nhỏ hơn máy 24. Hướng và
độ lớn thì khớp: **cách checker cho doanh thu CAO hơn nhưng số khách THẤP hơn** — đúng nghịch lý
quan sát được, và là hệ quả cộng gộp của phát hiện 2 và 3.

---

## Việc cần làm

| # | Việc | Vùng | Trạng thái |
|---|---|---|---|
| 1 | Khử trùng `dmsid` khi join `dim_nhanvien` trong `customer_product_coverage` | `backend/` | ✅ **đã sửa 23/09**, khớp SQL trực tiếp đến từng đồng |
| 2 | Chốt định nghĩa tập khách kỳ trước: có loại khách đã dừng mua hẳn không | DNH/PMO | ⏳ chặn UAT |
| 3 | Chốt cách quy đội cho kỳ quá khứ: theo dòng-tại-thời-điểm, hay theo khách như checker | DNH/PMO | ⏳ chặn UAT |

Mục 2 và 3 là **quyết định nghiệp vụ**, không nên tự chọn rồi nắn code cho khớp checker — phải hỏi.

Đã rà các chỗ join `dim_nhanvien` theo `dmsid` còn lại: chỉ hai chỗ trong tool này là join thẳng vào
bảng hóa đơn nên mới nhân bản dòng; chỗ ở `revenue_tree` đã dùng `SELECT DISTINCT dmsid` (một cột,
không nhân bản), các chỗ khác tra theo chiều `employee_code → dmsid` nên không ảnh hưởng.

> **Liên quan:** phát hiện 3 ở đây (quy đội cho kỳ quá khứ) cùng họ với lỗi V34 — xem
> [dieu_tra_v34_23-09.md](dieu_tra_v34_23-09.md). Ở V34 nguyên nhân đã truy ra trọn vẹn và sửa được:
> kho chỉ giữ 90 ngày `fact_tonghopkhachhang` nên tool chốt đội ở một mốc **sau** kỳ báo cáo.
