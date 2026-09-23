# Điều tra v34 — khuyến mãi đội đang dùng, khách tham gia, DT trước/trong/sau

*23/09/2026. Người chấm UAT ghi: "Chương trình khuyến mãi hiện chỉ đồng bộ đến 09/01/2026".
Câu V34, tool `promotion_effectiveness`, checker dùng `DMS_DonHangCTKM → DMS_CTKM → DMS_DonHangHdr`.*

Điều tra chạy trên `backend/warehouse.db` và **đọc thẳng Bravo từ máy dev** (Bravo kết nối được,
chỉ đọc), **không gọi model trả phí**. Kho local không có bảng CTKM nào, nhưng Bravo thì có — nên
toàn bộ kết luận dưới đây đã **tái lập được bằng số**, không dừng ở suy luận từ code.

> **Kết luận ngắn:** chênh lệch v34 do **đúng một** nguyên nhân — tool chốt đội hình ở **30/06/2026**
> cho kỳ báo cáo **12/2025**. Đã sửa, có test khóa, đã deploy lên máy 24 ngày 23/09.
> Việc "chatbot 4 vs checker 12+ chương trình" **không phải lỗi**: model hiển thị 8/20 chương trình
> tool trả về, còn checker sắp theo mã nên ảnh chụp toàn `MT_*`.
> Sự cố đồng bộ CTKM 09/01/2026 là chuyện khác, vẫn còn và vẫn thuộc phía DNH.

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

### Hệ quả — tái lập khớp đến từng đồng

**Bravo đọc được từ máy dev**, nên không phải dừng ở suy luận. Chạy đúng truy vấn của tool trên
Bravo cho `MT_SP_TICHLUYCHAOTHU_ANC`, kỳ 01–31/12/2025, chỉ đổi **một** biến là ngày chốt đội:

| Đội dùng để lọc | Khách | Đơn | Có HĐ | Doanh thu |
|---|---:|---:|---:|---:|
| **31/12/2025** — đúng kỳ | **14** | 15 | **13** | **784.895.766** |
| **30/06/2026** — tool đang dùng | **11** | **12** | **11** | **775.680.951** |

Dòng trên khớp checker, dòng dưới khớp số chatbot đã trả trong ảnh UAT — cả ba chỉ số, đến từng
đồng. **Toàn bộ chênh lệch v34 do đúng một nguyên nhân này.**

Lý do: trong khoảng giữa hai mốc, đội có **3 người rời và 3 người vào**:

```
chỉ có ở 12/2025 : TM23110133, TM24050203, TM25110302
chỉ có ở 06/2026 : TM23110127, TM26060101, TM26060102
```

Ba người rời ↔ ba khách chênh lệch. Cả hai bảng nguồn trên Bravo (`FACT_TongHopKhachHang` và
`FACT_ThongKeTinhLuong`) cho **cùng một tập chênh** này, nên không phải lỗi của riêng bảng nào.

Đây **không phải** lỗi logic của tool — tool tính đúng cái nó được cho. Thiếu là **lịch sử phân
công đội trong kho local**.

### ✅ Đã sửa (23/09)

Hóa ra kho **đã sẵn có** nguồn đúng, chỉ là không ai dùng tới:

| Bảng trong kho | Sync giữ | Phủ 12/2025? |
|---|---|---|
| `fact_tonghopkhachhang` | `days=90` | ❌ (sớm nhất 30/06/2026) |
| `fact_thongketinhluong` | `days=400` | ✅ (sớm nhất 17/08/2025) |

`fact_thongketinhluong` chính là `FACT_ThongKeTinhLuong` — **đúng bảng checker dùng** — và có
`manager_code`. Tại 31/12/2025 nó trả đúng 8 người của đội `TM23110128`.

Bản sửa: `_get_team_dms_ids()` nay thử `fact_thongketinhluong` **trước khi** nhảy tới một mốc sau kỳ.
Chỉ khi cả hai bảng đều không phủ mới nhảy tới, và khi đó đánh dấu `moc_sau_ky=True`.

Kèm theo, `promotion_effectiveness` bày mốc chốt đội ra **payload** (`team_roster_as_of`,
`team_roster_source`, `team_roster_note`) chứ không chỉ `_warn()` — xem mục 5 để biết vì sao.

Không cần đụng tới `sync_fact_tonghopkhachhang(days=90)`: nới cửa sổ đồng bộ tốn thêm dữ liệu mà
vẫn không dùng chung nguồn với checker.

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

**c) Số chương trình 4 vs 12+ — ✅ đã chốt 23/09 bằng payload lượt thật.**

Đọc `query_runs` trên máy 24, lượt UAT là `2026-09-23 06:56:39 | thuan.pham`:

```
get_promotion_effectiveness({})
get_promotion_effectiveness({'date_from':'2026-09-01','date_to':'2026-09-23','limit':20})
get_promotion_effectiveness({'date_from':'2025-12-01','date_to':'2025-12-31','limit':20})
```

Và chính câu trả lời ghi: *"Đang liệt kê **8/20** chương trình (theo doanh thu gắn CTKM giảm dần)."*

**Tool trả 20 chương trình, model chỉ hiển thị 8** rồi tự nói ra điều đó. Không có chương trình nào
bị lọc mất. Checker thì `ORDER BY p.Code` và không có `TOP`, mà `MT_` xếp trước `Q…`/`T…` nên ảnh
chụp checker đương nhiên toàn `MT_*`.

Hai bên **cùng phạm vi MT**, chỉ khác cách sắp xếp và mức cắt hiển thị. Không phải lỗi.

> Danh sách chatbot trả gồm cả `MT_*` lẫn `T11.2025_*`, `T12.2025_*`, `Q4.2025_*` — tức không lọc
> theo tiền tố mã. Giả thuyết "checker lọc theo tiền tố `MT_`" nêu ở bản trước là **sai**; nguyên
> nhân thật chỉ là thứ tự sắp xếp.

## 5. Vì sao `_warn()` một mình là không đủ

`_warn()` chỉ **đính cảnh báo vào kết quả trả cho model**; model có trách nhiệm nói lại:

```python
def _warn(msg: str):
    """Ghi 1 canh bao de dinh kem vao ket qua tra ve cho AI (AI co trach nhiem noi lai voi nguoi dung)."""
```

Lượt V34 chắc chắn đã sinh cảnh báo `DOI LICH SU KHONG CO SNAPSHOT ...` (chứng minh ở mục 3), nhưng
**trong ảnh UAT câu trả lời không nhắc gì đến việc đội hình lấy từ 30/06/2026**. Người đọc không có
cách nào biết số mình đang nhìn bị lệch.

Đó là lý do bản sửa không chỉ dừng ở chốt đúng đội, mà còn bày mốc chốt đội ra **payload**
(`team_roster_as_of`, `team_roster_source`, `team_roster_note`). Payload thì model phải đọc để trả
lời; cảnh báo thì có thể bỏ qua.

Vẫn nên kiểm `query_runs` trên máy 24 (miễn phí, không gọi model) để biết model đã nuốt bao nhiêu
cảnh báo khác — đây khó mà là trường hợp duy nhất.

---

## Việc cần làm

| # | Việc | Vùng | Trạng thái |
|---|---|---|---|
| 1 | Chốt đội theo `fact_thongketinhluong` cho kỳ quá khứ | `backend/` | ✅ **đã sửa**, 5 test khóa |
| 2 | Bày mốc chốt đội ra payload thay vì chỉ `_warn()` | `backend/` | ✅ **đã sửa** |
| 3 | Thống nhất nhãn cột "DT gắn với đơn…" (`associated_revenue_label`) | `backend/` | ✅ **đã sửa** |
| 4 | Chốt: đơn có `DMSEmpId2` thì tính cho đội nào | DNH/PMO | ⏳ chặn UAT, cần hỏi |
| 5 | Lấy payload lượt V34 để chốt việc 4 vs 12+ chương trình | vận hành | ✅ **đã chốt** — model hiển thị 8/20, checker sắp theo mã |
| 6 | Kiểm `query_runs` xem model còn nuốt cảnh báo nào nữa không | vận hành | ⏳ nên làm |

**Sự cố đồng bộ CTKM dừng 09/01/2026 vẫn là chuyện riêng, không phải nguyên nhân của chênh lệch số
ở trên.** Nó thuộc chiều DMS → Bravo, hạ tầng DNH, đã ghi trong
[tracking_hoan_thien_du_an_03-30_09_2026.md](tracking_hoan_thien_du_an_03-30_09_2026.md) (11 bảng
nhóm CTKM cùng dừng trong một khoảng 40 giây). Chừng nào chưa nạp bù thì V34 vẫn chỉ trả lời được
cho kỳ ≤ 12/2025, và mọi câu hỏi khuyến mãi năm 2026 vẫn rơi vào `source_gap`.
