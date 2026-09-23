# Điều tra v34 — khuyến mãi đội đang dùng, khách tham gia, DT trước/trong/sau

*23/09/2026. Người chấm UAT ghi: "Chương trình khuyến mãi hiện chỉ đồng bộ đến 09/01/2026".
Câu V34, tool `promotion_effectiveness`, checker dùng `DMS_DonHangCTKM → DMS_CTKM → DMS_DonHangHdr`.*

Điều tra chạy cục bộ trên `backend/warehouse.db` + đọc code, **không gọi model trả phí**. Kho local
**không có bảng CTKM nào** nên không tái lập được số hóa đơn; phần số học dưới đây dựa trên chính
giá trị chatbot đã hiển thị, đối chiếu với code.

## 1. Kỳ báo cáo là THÁNG 12/2025 — chứng minh bằng số học, không phải suy đoán

Khi không nhận tham số kỳ, tool lấy **tháng đầy đủ gần nhất** trước mốc phủ dữ liệu
([report_templates.py:11894](../backend/report_templates.py)):

```python
report_to   = dt.date(coverage_date.year, coverage_date.month, 1) - timedelta(days=1)
report_from = dt.date(report_to.year, report_to.month, 1)
```

Mốc phủ = `09/01/2026` → kỳ báo cáo = **01/12–31/12/2025**.

Bốn dòng trong ảnh UAT xác nhận, không lệch một ngày:

| Chương trình | Chạy | Chatbot ghi | Kiểm lại |
|---|---|---|---|
| `MT_SP_TICHLUYCHAOTHU_ANC` | 06/12/25–20/02/26 | phủ **26**/77 | 06/12→31/12 = **26** ✓ · 26+31+20 = **77** ✓ |
| `T11.2025_ANCUNG_3_TQ.MS` | 01/11–31/12/25 | phủ **31**/61 | tháng 12 = **31** ✓ · 30+31 = **61** ✓ |
| `T12.2025_ANCUNG_3_TQ` | 01/12–31/12/25 | **trọn chương trình** | nằm gọn trong tháng 12 ✓ |
| `Q4.2025_CK_NHOM.NH02_TQ` | 01/10–31/12/25 | phủ **31**/92 | tháng 12 = **31** ✓ · 31+30+31 = **92** ✓ |

Cả bốn đều là "phần rơi vào tháng 12/2025". Tool có nói rõ qua `period_coverage_note`
(`_promotion_period_fields`, [dòng 11808](../backend/report_templates.py)): *"Các số ở đây là PHẦN
TRONG KỲ, không phải kết quả cả chương trình."*

> Dòng "chỉ mới phủ 26/77 ngày" trong ảnh **không phải** báo lỗi đồng bộ. Nó nói kỳ báo cáo chỉ
> cắt qua 26/77 ngày vòng đời chương trình. Hai chuyện khác nhau, dễ đọc nhầm thành một.

## 2. Tên cột khác nhau nhưng CÙNG một đại lượng — không phải sai lệch

| | Công thức |
|---|---|
| Checker — "DT gắn với đơn trong kỳ báo cáo" | `SUM(Amount9)` của hóa đơn, nối theo `TRY_CONVERT(int, DMSId) = OrderId` |
| Tool — "DT gắn với đơn có CTKM" | `SUM(Amount9)` từ `vHoaDonTotal`, nối y hệt ([dòng 11955](../backend/report_templates.py)) |

Cùng bảng, cùng cột, cùng khóa nối, cùng bộ lọc `DocDate` trong kỳ. **Khác nhãn, không khác số.**
Không cần sửa gì ở đây — nhưng nên thống nhất chữ để người chấm khỏi mất công đối chiếu.

---

## 3. 🔴 Phát hiện chính — đội hình dùng cho kỳ 12/2025 là đội hình của **30/06/2026**

Đây là lời giải cho chênh lệch 11 vs 14 khách · 12 vs 13 đơn · 775,68 vs 784,90 tr.

### Hai bên chốt đội bằng hai nguồn khác hẳn nhau

| | Nguồn chốt đội | Thời điểm |
|---|---|---|
| **Checker** | `FACT_ThongKeTinhLuong` trên **Bravo** | `SaveDate` **nằm trong kỳ** (`>= @FromDate AND < @ToDate`) → đội THẬT của 12/2025 |
| **Tool** | `fact_tonghopkhachhang` trong **kho local** | `_get_team_dms_ids(scope_employee_code, str(report_to))` → chốt tại 31/12/2025 |

Nghe thì giống nhau. Vấn đề là kho local **không giữ nổi tới đó**:

```
fact_tonghopkhachhang save_date: min=2026-06-30  max=2026-09-15  so_moc=4
khoang giu lai: 78 ngay
co snapshot <= 2025-12-31 ?  0
co snapshot <= 2026-01-09 ?  0
```

```
_roster_snapshot_dates('2025-12-31') -> []
_roster_snapshot_dates('2026-01-09') -> []
_roster_snapshot_dates('2026-09-23') -> ['2026-08-31', '2026-09-15']
```

Không có mốc nào ≤ 31/12/2025. Tool rơi vào nhánh dự phòng trong `_get_team_dms_ids`
([dòng ~340](../backend/report_templates.py)) — nhánh này **được viết ra chính vì V34**, ghi chú đề
ngày 13/09/2026:

> *"13/09/2026 (V34): kỳ được hỏi có thể nằm TRƯỚC phạm vi phân công đội còn giữ trong kho
> (`fact_tonghopkhachhang` chỉ giữ ~90 ngày). Ví dụ thật: tool khuyến mãi lấy mốc phủ CTKM 09/01/2026
> làm ngày chốt đội → không có snapshot nào <= mốc đó → MỌI câu hỏi khuyến mãi của QLV đều hỏng cứng."*

Nhánh dự phòng lấy `MIN(save_date) > fdate` = **30/06/2026**, rồi `_warn(...)`.

### Hệ quả

**Báo cáo khuyến mãi tháng 12/2025 đang được lọc theo thành phần đội của 30/06/2026 — sau kỳ báo
cáo đúng sáu tháng.** Ai rời đội trong khoảng đó thì đơn của họ biến mất khỏi kết quả; ai mới vào
thì đơn cũ của họ bị kéo vào.

Khớp đúng hình dạng quan sát được: khách **ít hơn** (11 vs 14), đơn **ít hơn** (12 vs 13), nhưng
doanh thu chỉ hụt **1,2%** (775,68 vs 784,90 tr ≈ 9,2 tr) — vài khách nhỏ rơi ra, không phải sai
công thức.

Đây **không phải** lỗi logic của tool. Tool tính đúng cái nó được cho. Thiếu là ở **dữ liệu lịch sử
phân công đội trong kho local**, trong khi checker đọc thẳng Bravo nên vẫn có.

### Ba hướng xử lý

| # | Hướng | Đánh giá |
|---|---|---|
| A | Đồng bộ thêm lịch sử `FACT_ThongKeTinhLuong`/`fact_tonghopkhachhang` vào kho, đủ phủ 2025 | Giải quyết tận gốc, và **có lợi cho mọi tool khác** đang chốt đội theo kỳ quá khứ (v24 phát hiện 3 cùng họ vấn đề này) |
| B | Cho `promotion_effectiveness` đọc roster thẳng từ Bravo như checker | Sửa được đúng một tool, các tool khác vẫn lệch |
| C | Giữ nguyên, bắt buộc nêu cảnh báo `DOI LICH SU KHONG CO SNAPSHOT` ra câu trả lời | Rẻ nhất, nhưng người chấm vẫn thấy số lệch |

Khuyến nghị **A**. Nhưng dù chọn gì thì **C phải làm ngay** — xem mục 5.

## 4. Khác biệt nhỏ hơn, đã đo nên không phải nghi ngờ

**a) Tool nhận cả nhân viên thứ hai trên đơn, checker chỉ nhận người thứ nhất.**

```python
scope_where += f" AND (h.DMSEmpId1 IN ({joined}) OR h.DMSEmpId2 IN ({joined}))"   # tool
```
```sql
LEFT JOIN emp em ON em.DMSId = po.DMSEmpId1                                       -- checker
```

Chiều tác động **ngược** với chênh lệch quan sát được (nó làm tool ra *nhiều* hơn), nên nó không
phải nguyên nhân chính — nhưng vẫn là một bất đồng định nghĩa cần chốt: đơn có hai người thì tính
cho đội nào.

**b) Khử trùng `DIM_NhanVien` — ở đây KHÔNG thành vấn đề.** Checker lọc `ISNULL(n.IsDuplicate,0)=0`,
tool không lọc. Đo trên kho: 48/330 dòng bị gắn `is_duplicate=1` và **cả 48 dòng đều có `dmsid`**,
nhưng **không `employee_code` nào ứng với hơn một `dmsid`** (đo: 0 trường hợp). Tool tra theo chiều
`employee_code → dmsid` nên cờ trùng không đổi kết quả.

> Khác với v24 phát hiện 1: ở đó join theo chiều ngược (`nv.dmsid = v.employee_code`) nên `dmsid`
> trùng làm **nhân bản dòng hóa đơn**. Cùng một bảng, hai chiều join, chỉ một chiều hỏng.

**c) Số chương trình 4 vs 12+ — chưa kết luận được.** Hai khả năng, không phân biệt được bằng dữ
liệu đang có:

- Checker `ORDER BY p.Code` và **không có `TOP`**; `MT_` xếp trước `Q…` và `T…` nên ảnh chụp phần
  đầu danh sách đương nhiên toàn `MT_*`. Tool thì `TOP (limit) ORDER BY AssociatedRevenue DESC`.
- Hoặc phạm vi đội của tool hẹp hơn phạm vi checker chạy thật (`@ManagerCode` có thể là `NULL`).

Cần **payload lượt UAT thật** (`sql_used_json` / tham số `scope_*` trong `query_runs`) mới chốt được.
Tôi không đoán tiếp.

## 5. ⚠️ Việc cần kiểm ngay: cảnh báo có được nói ra không

`_warn()` chỉ **đính cảnh báo vào kết quả trả cho AI**; AI có trách nhiệm nói lại:

```python
def _warn(msg: str):
    """Ghi 1 canh bao de dinh kem vao ket qua tra ve cho AI (AI co trach nhiem noi lai voi nguoi dung)."""
```

Lượt V34 chắc chắn đã sinh cảnh báo `DOI LICH SU KHONG CO SNAPSHOT ...` (đã chứng minh ở mục 3).
**Trong ảnh UAT không thấy câu trả lời nhắc gì đến việc đội hình lấy từ 30/06/2026.** Nếu đúng là
model nuốt mất cảnh báo thì đó là lỗi nặng hơn cả chênh lệch số: người đọc không có cách nào biết.

Kiểm bằng `query_runs` trên máy 24 (miễn phí, không gọi model) — lọc lượt V34, đọc `answer` xem có
chuỗi "30/06/2026" hoặc "đội hình" không.

---

## Việc cần làm

| # | Việc | Vùng | Mức |
|---|---|---|---|
| 1 | Kiểm `query_runs` xem câu trả lời V34 có nêu cảnh báo đội hình không | vận hành | 🔴 kiểm ngay |
| 2 | Đồng bộ lịch sử phân công đội đủ phủ kỳ quá khứ (hướng A) | kho/sync | 🔴 gốc rễ, dùng chung với v24 |
| 3 | Chốt: đơn có `DMSEmpId2` thì tính cho đội nào | DNH/PMO | chặn UAT |
| 4 | Thống nhất nhãn cột "DT gắn với đơn…" giữa chatbot và checker | `backend/` | thấp, chỉ là chữ |
| 5 | Lấy payload lượt V34 để chốt việc 4 vs 12+ chương trình | vận hành | chưa kết luận |

**Sự cố đồng bộ CTKM dừng 09/01/2026 vẫn là chuyện riêng, không phải nguyên nhân của chênh lệch số
ở trên.** Nó thuộc chiều DMS → Bravo, hạ tầng DNH, đã ghi trong
[tracking_hoan_thien_du_an_03-30_09_2026.md](tracking_hoan_thien_du_an_03-30_09_2026.md) (11 bảng
nhóm CTKM cùng dừng trong một khoảng 40 giây). Chừng nào chưa nạp bù thì V34 vẫn chỉ trả lời được
cho kỳ ≤ 12/2025, và mọi câu hỏi khuyến mãi năm 2026 vẫn rơi vào `source_gap`.
