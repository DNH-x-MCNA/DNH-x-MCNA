# Danh sách câu cần chấm lại — 22/09/2026

Nguồn: log chi phí/phản hồi của chatbot từ 11/09 đến 22/09 (các lượt 👎, các lượt `Lỗi`/`Đang chạy`),
đối chiếu với commit log cùng khoảng. Toàn bộ việc lập danh sách này chạy cục bộ trên code và kho
local, **không gọi một lượt model trả phí nào**.

Mỗi lượt chấm lại là một lượt gọi model có tính phí. Trung bình ngày 22/09 là **~4.000 đ/lượt**, nên
trọn danh sách này (24 lượt) tốn khoảng **100.000 đ**. *(Cập nhật 23/09: #22 và #23 đã đóng không
tốn lượt nào, #13 đang chờ kiểm nhãn — còn tối đa 21 lượt, ~84.000 đ. Xem mục cập nhật bên dưới.)* Khi chạy phải truyền `username` riêng và
`session_id` có tiền tố nhận diện được, nếu không thì kết quả không lọc được theo vai/vùng và **không
dùng để chấm UAT** (xem `AGENTS.md`).

Thứ tự ưu tiên: nhóm 3 trước (còn nghi sai số thật), rồi nhóm 1 (nhiều khả năng đóng được), nhóm 2
xen kẽ, nhóm 4 đừng chấm cho tới khi sync xong.

---

## Cập nhật 23/09 — đối chiếu `query_runs` trước khi chấm lại

Danh sách này dựng từ **log chi phí**, trong đó mỗi lượt chỉ có trạng thái và nhận xét đã tóm tắt.
Bảng `query_runs` trong `backend/memory.db` trên máy 24 giữ thêm **tool đã gọi, câu trả lời đầy đủ
và `feedback_comment` nguyên văn**. Đọc SQLite, không gọi model, **không tốn đồng nào**.

Đối chiếu ngày 23/09 cho session `41b1aeae-5b02-4103-a8df-42e050fa48b9` (`dnh_etc`, 15/09) đóng
được **#22 và #23**, và cho thấy **#13 nhiều khả năng gán nhầm nhãn**. Ba mục trên tổng 24 — tức
riêng bước đối chiếu miễn phí này đã cắt khoảng **12.000 đ** và, quan trọng hơn, gỡ đúng mục đang
bị xếp "ưu tiên cao nhất" ra khỏi hàng đợi.

**Vì vậy: chạy đối chiếu `query_runs` cho toàn bộ 24 lượt TRƯỚC khi chấm lại bất cứ mục nào.**
Lọc theo `session_id` (lấy từ `audit_log.jsonl`) thay vì theo giờ — `audit_log` ghi giờ địa phương
còn `query_runs.created_at` ghi UTC, lệch đúng 7 tiếng, rất dễ tìm trượt.

```powershell
$py = @'
import sqlite3, json
SESS = "<session_id lay tu audit_log>"
c = sqlite3.connect(r"C:\dnh_chatbot\backend\memory.db")
c.row_factory = sqlite3.Row
for r in c.execute("SELECT * FROM query_runs WHERE session_id=? ORDER BY created_at", (SESS,)):
    print("=" * 78)
    print("%s | %s | %s" % (str(r["created_at"])[:19], r["username"], r["status"]))
    print("HOI : %s" % (r["question"] or ""))
    print("TOOL: %s" % json.loads(r["sql_used_json"] or "[]"))
    if r["feedback_rating"] is not None:
        print("CHAM: %s | %s | %s" % (r["feedback_rating"], r["feedback_category"],
                                      r["feedback_comment"]))
    print((r["answer"] or "")[:3000])
'@
$py | Out-File -Encoding utf8 $env:TEMP\doc_runs_sess.py
python $env:TEMP\doc_runs_sess.py
```

### ⚠️ Đính chính commit `6a4a692` (đã nằm trong master, không sửa message được)

Commit `6a4a692` (PR #49, merge `596ad1a`) có tiêu đề ghi **"(UAT dnh_etc 15/09 14:53)"** và phần
mở đầu trình bày như thể nó sửa cho mục #23. **Sai.** Lỗi mà commit đó vá là thật và độc lập
(`_detail_cutoff()` trả hằng số lệch dữ liệu, làm 20 tháng 2024-01 → 2025-08 ra 0 đồng cho cả hai
kênh), nhưng **không liên quan mục #23**: lượt 14:53 gọi `get_revenue_monthly_series(month_to=
'2026-09', months_back=9)`, tức 2026-01 → 2026-09, nằm trọn trong cửa sổ chi tiết.

Bản sửa message đã push lên nhánh nhưng PR được merge trước đó 1 phút nên không vào master. Phần
mô tả đúng nằm ở **body của PR #49** (đã sửa) và ở mục #23 bên dưới. Ai tra commit log về sau đọc
đến `6a4a692` thì đọc tiếp chỗ này.

---

## Nhóm 1 — Đã có bản sửa trỏ đúng lượt phản hồi đó, chấm lại để đóng

| # | Lượt phản hồi | Tài khoản | Câu hỏi | Phản hồi cũ | Bản sửa | Chấm lại cần thấy |
|---|---|---|---|---|---|---|
| 1 | 22/09 14:39 | Thanh Thủy | Khuyến mãi nhiều khách tham gia nhưng không tạo tăng trưởng | (điều tra 22/09) | `fix(m35)` ×2, 22/09 | Câu mở đầu nói rõ **chỉ Miền Bắc**; bảng có cột đơn **đã xuất hóa đơn** (SIRO_10 = 685/857); hai dòng `Q4.2025_NHOM_BOPHE_SIRO_` tách riêng kèm `program_id` |
| 2 | 22/09 13:52 | Thanh Thủy | Mở nhiều khách mới nhưng DT/khách và tỷ lệ mua lại thấp | (điều tra 22/09) | `feat(m24)`, 22/09 | 627 khách mới kỳ 8/2026 (MB 328 / MN 162 / MT 137); nói rõ khách mới lấy từ cờ `IsNC` của Bravo |
| 3 | 15/09 13:59 | Nguyễn Văn Danh | Danh sách khách hàng mới, ngày ghi nhận, doanh số tháng này | Thiếu khách mới; ngày ghi nhận sai | `fix(khach-kpi)` 15/09 (ghi rõ UAT 13:59–14:11), `fix(khach-hang)` 18/09 | Ngày ghi nhận = `NCSaveDate` (không phải ngày snapshot); không sót khách do QLV tự bán |
| 4 | 15/09 14:08 | Nguyễn Văn Danh | Khách phát sinh 3 tháng nhưng chưa đạt KPI tái đơn | Thiếu dữ liệu | `fix(khach-kpi)` 15/09 | Trả **danh sách khách** kèm lần mua gần nhất, không mô tả chung chung |
| 5 | 15/09 14:10 + 14:11 (Lỗi) | Nguyễn Văn Danh | Doanh số sản phẩm trọng tâm theo quản lý vùng | Thiếu KPI SP trọng tâm | `fix(khach-kpi)` 15/09 | Có %đạt target SKU trọng tâm theo từng QLV, không còn lỗi |
| 6 | 15/09 14:20 | OTC-Only C-Level | Bổ sung kế hoạch và % thực hiện | Thiếu target kênh MT | `fix(kenh-mt)` 15/09 (ghi rõ UAT 14:20) | Có kế hoạch và % thực hiện kênh MT theo từng tháng |
| 7 | 15/09 14:23 | OTC-Only C-Level | Top 10 khách hàng nợ quá hạn | Thiếu 2 nhà đầu, đang lấy tới nhà số 12 | `fix(otc)` 15/09 (UAT 14:23–14:40), `fix(receivables)` 16/09 | Đủ **10 dòng**, có `HCM04162` Dược Sài Gòn và `HCM04298` FPT Long Châu |
| 8 | 15/09 14:25 | OTC-Only C-Level | Bổ sung nhân viên, quản lý vùng tương ứng | Thiếu dữ liệu | `feat(dinh-dang)` 15/09, `fix(otc)` 15/09 | Mỗi khách kèm TDV/QLV phụ trách, mã luôn đi kèm tên |
| 9 | 15/09 14:40 | OTC-Only C-Level | Số lượng tồn kho bổ phế tính đến hôm nay | Thiếu dữ liệu | `fix(otc)` 15/09, `feat(tra-cuu)` 16/09 | Tra được theo **tên sản phẩm**, không bắt nhớ mã |
| 10 | 15/09 14:43 | dnh_etc | Doanh số tháng này theo các nhóm hàng | Thiếu nhóm đầu tư/khai thác/dược liệu/lao/khác | `fix(etc)` 15/09 (ghi rõ UAT dnh_etc 14:43) | Đủ nhóm hàng ETC theo `DIM_KeyClass` + `ItemTypeETC` |
| 11 | 15/09 15:16 (Lỗi 114 giây) | C-Level | Khách phát sinh 3 tháng chưa đạt KPI tái đơn, đội QLV TM23100148 | Lỗi timeout | `fix(loc-doi)` 16/09 (ghi rõ UAT 15/09 15:16) | Có `manager_code`, trả trong vài chục giây, không lọc tay trên danh sách toàn công ty |
| 12 | 16/09 09:48 và 09:52 | OTC-Only C-Level + dnh_etc | Top 10 khách hàng có công nợ quá hạn | Hỏi top 10 trả top 3 / top 5 | `fix(receivables): preserve requested top customer count` 16/09 | Hỏi 10 trả đủ 10 |
| 13 ⚠️ | 16/09 10:08 (Lỗi) | dnh_etc | Bệnh viện Bắc Ninh còn nợ bao nhiêu | Lỗi | `feat(tra-cuu)` 16/09 | **Kiểm lại nhãn trước khi chấm.** `query_runs` 23/09 cho lượt này `status=completed`, `rating=1` (👍): chatbot xin mã khách, người dùng đưa `BGI00699`, lượt sau trả đúng và cũng 👍. Nhãn "Lỗi" lấy từ log chi phí, không khớp `query_runs`. Nếu đúng là người dùng đã hài lòng thì bỏ khỏi hàng đợi |
| 14 | 16/09 15:21 | C-Level | Khách hoạt động, mới, mua lại, tái kích hoạt, ngừng mua từng tháng | Lệch số khách tái kích hoạt | `fix(vong-doi)` 18/09, `fix(c31)` 21/09 | Số tái kích hoạt khớp cửa sổ quan sát đã chốt; khách tách theo vùng |
| 15 | 17/09 13:46 (Lỗi 112 giây) | C-Level | Tháng mùa vụ cao/thấp theo kênh và nhóm sản phẩm | Lỗi timeout | `fix(c08): avoid seasonality report timeout` 21/09 | Trả được, không timeout |
| 16 | 18/09 09:44 | C-Level | Giá trị tồn kho, số tháng tồn, chậm luân chuyển, stock-out, cận date | Số liệu không đúng — "hàng tồn chưa thể xác nhận" | `fix(ton-kho)` ×2 17/09, `fix(ton-kho, do-moi)` 18/09, `fix(m40)` ×2 21/09 | Số lượng tồn là **hiện tại** (đã cộng nhập–xuất). **Giá trị** tồn vẫn là giá đầu năm và câu trả lời phải nói rõ điều đó — đây là câu A3 chờ DNH chốt nguồn giá, **đừng chấm trượt vì điểm này** |
| 17 | 14/09 13:50 | chosi.mn | Doanh số sản phẩm DM1, DM2, DM3, trọng tâm | KPI doanh số sản phẩm thiếu | `fix(khach-kpi)` 15/09 | Có KPI sản phẩm trọng tâm kèm %đạt |
| 18 | 14/09 11:07 | chosi.mn | Tình hình thực hiện KPI của các trình dược viên | Thiếu thưởng SP danh mục, V15/V22/V25, ASO, tổng trọng số | `fix(kpi)` 22/09 — **`fix(c45)` 21/09 KHÔNG phủ câu này**, nó chỉ đóng gói bảng ngưỡng theo tháng | Ngoài doanh số/chỉ tiêu phải nêu các cấu phần còn lại hoặc nói rõ cấu phần nào chưa lấy được. **V25 đã dừng từ 01/07/2026** — `V25Bonus = 0` là đúng cơ chế, không được đòi bù |

## Nhóm 2 — Lượt chết kỹ thuật, chấm lại để biết còn không

| # | Lượt | Tài khoản | Câu hỏi | Dấu hiệu |
|---|---|---|---|---|
| 19 | 14/09 16:59 | Phạm Văn Thuần | Tình hình thực hiện KPI của các trình dược viên | `Lỗi` sau 907 ms, **0 token** — chết trước khi gọi model |
| 20 | 14/09 14:44 | Nguyễn Văn Danh | Thực hiện doanh số ngày của các trình dược viên | `Lỗi` sau 843 ms, **0 token** |
| 21 | 17/09 16:02 | Nguyễn Thị Hồng Thúy | Khách vừa nợ quá hạn vừa giảm mua | Kẹt trạng thái `Đang chạy`, không có latency (lượt 16:05 chạy lại thì xong) |

0 token nghĩa là hỏng ở tầng phiên/định tuyến chứ không phải model trả sai. Nếu chấm lại vẫn hỏng thì
lấy `backend/logs` quanh đúng mốc giờ đó chứ đừng tốn thêm lượt.

## Nhóm 3 — Chưa có bản sửa nào nhắm vào, phải điều tra trước khi chấm

| # | Lượt | Tài khoản | Câu hỏi | Phản hồi | Vì sao còn treo |
|---|---|---|---|---|---|
| ~~22~~ | 15/09 14:48 | dnh_etc | Doanh số ETC tháng này | "tháng này mới có gần 6,5 tỷ thôi" | ✅ **ĐÓNG 23/09 — chatbot đúng, không chấm lại.** Xem bên dưới |
| ~~23~~ | 15/09 14:53 | dnh_etc | Thực hiện, kế hoạch doanh số các tháng trong năm | "Kế hoạch đúng, thực hiện sai" | ✅ **ĐÓNG 23/09 — chatbot đúng, không chấm lại.** Xem bên dưới |
| 24 | 14/09 13:45 | chosi.mn | Thực hiện và kế hoạch doanh số các quý | Thiếu kế hoạch quý | Kho có target theo tháng/vùng/QLV/SKU nhưng **không có bảng target quý**. Cần DNH chốt: cộng từ target tháng, hay có nguồn riêng |
| 25 | 16/09 15:00 | C-Level | Loại ảnh hưởng đổi địa bàn/chuyển NV/chuyển khách | "Số liệu không đúng", không ghi sai ở đâu | Hỏi lại người chấm sai chỗ nào trước, đừng đoán rồi tốn lượt |

### #22 và #23 — chatbot đúng, người chấm nhìn phạm vi khác

Ghi nhận ngày 15/09 (commit `309b5b7`) đã kết luận #22 "chatbot đã đúng, nhận xét chấm sai — anh
Đăng xác nhận". Danh sách 22/09 xếp lại nó thành "ưu tiên cao nhất, không commit nào nhắm vào" vì
tra theo **commit sửa** — mà một quyết định **không sửa** thì không để lại commit sửa nào. Ngày
23/09 `query_runs` cho bằng chứng trực tiếp:

| Lượt | Tool đã gọi | Chatbot trả |
|---|---|---|
| 14:48 | `resolve_relative_date` → `get_revenue_by_channel(2026-09-01 → 2026-09-15)` | **16,19 tỷ · 420 hóa đơn** |
| 14:53 | `get_revenue_monthly_series(month_to='2026-09', months_back=9)` | bảng 9 tháng, kèm ghi chú tháng 9 mới 15 ngày |

Chạy lại đúng hai bộ tham số đó trên kho ngày 23/09: 16,56 tỷ · 429 hóa đơn (chênh 2,2% vì lúc hỏi
kho mới sync 14:43, kho đọc lại đã sync tiếp 16:55 — đúng chiều, đúng lượng), và cả 9 tháng khớp
`SUM(amount9)` trên `vhoadon_etc` **đến từng chữ số**. Không có lỗi tính.

**Con số 6,5 tỷ đến từ đâu.** Đã thử tách theo nhóm hàng, theo nhân viên, theo tổ hợp nhóm — không
lát nào rơi vào 6,5. Lát duy nhất khớp là **theo vùng**:

| Vùng | Hóa đơn | 01–15/09 |
|---|---:|---:|
| MN | 200 | 8,44 tỷ |
| **MB** | **188** | **6,72 tỷ** |
| MT | 41 | 1,39 tỷ |

Quy về mốc sync lúc hỏi (×0,978) thì MB ≈ **6,58 tỷ** — đúng "gần 6,5 tỷ". Nhiều khả năng người
chấm đang đối chiếu báo cáo lọc **Miền Bắc**, còn tài khoản `dnh_etc` trả **toàn kênh, cả 3 miền**.

Không suy giả thuyết này sang #23: lấy MB so kế hoạch toàn quốc ra 27–41% mọi tháng, không ai gọi
thế là "kế hoạch đúng". #23 mới chỉ chắc được là **chatbot không sai**; căn cứ của người chấm thì
chưa rõ.

**Việc cần làm (miễn phí, thay cho 2 lượt chấm lại):** hỏi chủ kênh ETC đúng một câu — *con số
6,5 tỷ là toàn kênh hay riêng Miền Bắc, và bảng "thực hiện các tháng" so ở phạm vi nào?* Nếu trả
lời "Miền Bắc" thì đây **không phải lỗi số mà là lỗi trình bày**: câu trả lời tổng phải nói rõ
"toàn kênh ETC, gồm cả 3 miền". Sửa ở mô tả tool, **gộp vào đợt sửa prompt chung** — cache chiếm
71% chi phí, không vá lẻ.

## Nhóm 4 — Lỗ trống ETL, đừng chấm cho tới khi sync xong

| # | Lượt | Tài khoản | Câu hỏi | Thực trạng |
|---|---|---|---|---|
| 26 | 14/09 11:29 | chosi.mn | Số lượng đơn hàng đúng tuyến từng ngày | **Đã chấm lại 22/09: trả được**, nguồn ghi `SQL Server NH_Report_TM` — chatbot query thẳng Bravo chứ không qua kho. Kho local vẫn không có `DMS_DiTuyen` nên báo cáo cố định chưa dùng được, nhưng câu hỏi không bị chặn. Còn phải xác nhận với HR: ngày 01 và 03/09 trống trong khi là Thứ Ba và Thứ Năm (02/09 là Quốc khánh) |
| 27 | 14/09 11:06 | chosi.mn | Công làm việc, ăn ca, phụ cấp, chấm call | Chấm công chưa có nguồn nào trong kho lẫn trong tool. Đây mới thật sự là lỗ trống nguồn |

Với câu chấm công, ghi "chưa đủ nguồn" thay vì chấm trượt phần suy luận. Câu đi tuyến thì chấm bình
thường.

---

## Ghi chú về các lượt không tên

Log còn 8 lượt `unknown` tối 13/09 (≈ 81.900 đ trong 30 phút, latency 15–456 ms) và một cụm
`unknown` ngày 11/09 (≈ 51.400 đ). Không có `username` thì không lọc được theo vai/vùng, nên theo
`AGENTS.md` các lượt đó **không dùng để chấm UAT** — và cũng cần truy ra ai đã chạy. Các lượt
`unknown`/`alice` ngày 21/09 23:56 thì vô hại: 0 token, 0 đ, là smoke test.
