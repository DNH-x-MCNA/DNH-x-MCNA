# Backlog từ phản hồi người dùng thật

*Lập 26/08/2026, từ bảng `query_feedback_events` trong `backend/memory.db` trên máy 24.
Kỳ dữ liệu: 14/08 – 25/08/2026 (ngay sau Demo #1 ngày 13/08).*

## Bối cảnh số liệu

23 lượt đánh giá: **12 hài lòng, 11 không hài lòng**.

**Không dùng tỷ lệ 52% làm chỉ số chất lượng.** Mẫu 23 lượt có sai số quá lớn, và phần lớn phản hồi
đến từ một đợt test có tổ chức ngay sau Demo #1 chứ không phải sử dụng thường ngày. Giá trị thật của
bộ dữ liệu này nằm ở **nội dung từng ca**, không ở con số tổng.

Lấy lại số bất cứ lúc nào (đọc SQLite, không gọi API, không tốn tiền):

```powershell
$py = @'
import sqlite3, textwrap
c = sqlite3.connect(r"C:\dnh_chatbot\backend\memory.db")
c.row_factory = sqlite3.Row
for i, r in enumerate(c.execute("""
    SELECT r.created_at, r.username, r.question, r.answer, f.category, f.comment
    FROM query_feedback_events f JOIN query_runs r ON r.query_id = f.query_id
    WHERE f.rating = -1 ORDER BY r.created_at DESC"""), 1):
    print("=" * 78)
    print("%d. %s | %s | %s" % (i, r["created_at"][:16], r["username"], r["category"]))
    print("   HOI : %s" % textwrap.shorten(r["question"] or "", 150))
    print("   TRA : %s" % textwrap.shorten((r["answer"] or "").replace("\n", " "), 300))
    if r["comment"]:
        print("   NOI : %s" % r["comment"])
'@
$py | Out-File -Encoding utf8 $env:TEMP\xem_loi.py
python $env:TEMP\xem_loi.py
```

---

## ✅ ĐÃ XỬ LÝ — không cần làm gì thêm

### 3 ca báo SỐ SAI, cả ba đều truy được đúng bản vá

| Ca | Người dùng thấy gì | Bản vá |
|---|---|---|
| **14/08 · `dnh`**<br>*"Cuối tháng 7 có bao nhiêu khách mới, mua lại và hoạt động"* | Bảng trả về **"Khách hoạt động (is_active): 46"**. Người dùng ghi *"Lệch số liệu về số khách hàng"* — 46 trên tổng ~6.000 khách không thể là "khách hoạt động" | `02c3e0c` (26/08). Chatbot nay **không được phép** gọi `IsAC` là "khách hoạt động"; nếu người dùng hỏi về khách đang hoạt động thì phải nói rõ chưa có định nghĩa được DNH xác nhận |
| **14/08 · `dnh`**<br>*"Dữ liệu hoá đơn OTC và ETC mới nhất đến ngày nào"* | Trả về **ETC có chứng từ ngày 28/08/2026** — ngày tương lai. Người dùng ghi *"Thời gian bản ghi đồng bộ bị lệch"* | Đã lọc `DocDate <= CAST(GETDATE() AS DATE)` ở **3 chỗ** trong `src/alerts.py`. Một hoá đơn ghi ngày tương lai từng làm hỏng toàn bộ mốc "hôm nay" |
| **14/08 · `thuy.nguyen2`**<br>*"Khách từng mua quý II nhưng không mua tháng 7 là ai"* | Chatbot **so Top 50 quý II với Top 50 tháng 7** để đoán khách rớt — vì không có công cụ nào làm đúng việc này. Người dùng ghi *"Không tìm thấy một số mã KH tương ứng trong fact check sql"* | `get_customer_movement` + `get_customers_silent` (24/08) trả lời trực tiếp, không còn chắp vá bằng top-50 |

### Không nhận phạm vi đội khi QLV đã đăng nhập

**17/08 · `thuy.nguyen2`** — hỏi *"Trong đội tôi ai có nhiều khách phụ trách nhưng tỷ lệ hoàn thành
thấp nhất?"*, chatbot hỏi ngược lại mã QLV. Nguyên văn:

> *"Mặc dù đã đăng nhập, chatbot vẫn yêu cầu nêu rõ tên nv và mã nv để tra cứu, mặc dù còn đưa ra
> đúng ví dụ về tên và mã nv của tk đang sử dụng"*

**Nguyên nhân**: tài khoản là vai `qlv` nhưng **chưa được gán `employee_code`**. Ghi chú phạm vi
trong system prompt (`nl2sql.py`, thêm 23/07) chỉ chạy khi trường đó có giá trị — rỗng thì model
không có gì để dựa vào, đành hỏi lại. Hành vi đúng về an toàn, nhưng vô lý với người dùng.

**Đã bịt ba tầng:**

| Tầng | Cơ chế |
|---|---|
| Tạo/duyệt tài khoản | `admin_create_user` và đường duyệt đều truyền `require_complete=True` — không tạo nổi tài khoản QLV `approved` mà thiếu vùng hoặc mã nhân viên |
| Lúc chạy | `_business_scopes` (`backend/main.py`) chặn 403 kèm thông báo rõ. Thêm `5db7078` ngày **24/08** — một tuần **sau** phản hồi này |
| Prompt | Model được báo rõ đang phục vụ QLV nào và phạm vi đã siết ở tầng code |

**Đã kiểm 26/08**: 0 tài khoản đã duyệt thiếu phạm vi.

**Vẫn nên kiểm lại trước UAT** — tài khoản `pending` vẫn tạo được với scope rỗng (đúng thiết kế:
người dùng tự đăng ký trước, admin gán sau). Nếu duyệt hàng loạt 28 tài khoản QLV mà chưa có bảng
ánh xạ tài khoản ↔ mã nhân viên thì sẽ tắc từng cái một giữa lúc chuẩn bị họp.

```powershell
$py = @'
import sqlite3
c = sqlite3.connect(r"C:\dnh_chatbot\backend\auth.db")
c.row_factory = sqlite3.Row
xau = c.execute("""SELECT username, role, scope_value, employee_code FROM users
                   WHERE status='approved' AND (
                     (role='qlv' AND (employee_code IS NULL OR employee_code='' OR scope_value IS NULL OR scope_value=''))
                     OR (role='regional_director' AND (scope_value IS NULL OR scope_value='')
                         AND (scope_channel IS NULL OR scope_channel='')))""").fetchall()
print("Tai khoan da duyet nhung THIEU pham vi: %d" % len(xau))
for r in xau:
    print("  %-18s %-20s vung=%-4s ma_nv=%s" % (r["username"], r["role"], r["scope_value"] or "-", r["employee_code"] or "-"))
'@
$py | Out-File -Encoding utf8 $env:TEMP\kiem_tk.py
python $env:TEMP\kiem_tk.py
```

---

## 🔧 CẦN LÀM — sửa được bằng code

### 1. Hỏi "top 10 mỗi kênh khác nhau thế nào" thì gộp cả hai kênh

**14/08 · `dnh`** — *"Top 10 sản phẩm OTC và top 10 ETC có khác nhau thế nào?"*
Người dùng ghi: *"Chatbot gộp cả 2 kênh thay vì xếp hạng 2 kênh riêng"*.

`top_products` **đã có** tham số `channel`, nên đây là chuyện **định tuyến/mô tả tool**, không phải
thiếu năng lực: model cần hiểu câu hỏi so sánh hai kênh thì phải gọi tool **hai lần**, mỗi lần một
kênh, rồi mới đặt cạnh nhau.

Hướng: bổ sung vào mô tả `get_top_products` rằng câu hỏi dạng "so sánh giữa các kênh" cần gọi riêng
từng kênh. **Nhớ gộp chung đợt với các sửa đổi prompt khác** — mỗi lần sửa mô tả tool là một lần trả
tiền ghi lại cache cho mọi vai (xem `docs/` và memory về cache).

### 2. "Tuần trong tháng" — hai định nghĩa khác nhau ⚠️ CẦN DNH CHỐT

**14/08 · `thuy.nguyen2`** — *"Tuần nào trong tháng 7 đóng góp doanh thu lớn nhất và chiếm bao nhiêu
phần trăm tháng?"*. Nguyên văn phản hồi:

> *"Tuần tính lệch so với kết quả, chatbot tự động lấy 7 ngày đầu thành 1 tuần mà trong sql lấy theo
> đúng thứ tự thứ trong tháng => kết quả tổng doanh thu bị lệch."*

**Đây KHÔNG phải lỗi code — là hai định nghĩa nghiệp vụ khác nhau:**

| Cách hiểu | "Tuần 1 của tháng 7/2026" |
|---|---|
| Chatbot đang dùng | 01–07/07 (7 ngày đầu tháng) |
| SQL đối chứng của người dùng | Tuần lịch chứa ngày 01/07, tính theo thứ Hai đầu tuần |

Hai cách cho ra tổng khác nhau. **Phải hỏi DNH dùng cách nào**, rồi thống nhất một nguồn duy nhất —
ảnh hưởng mọi báo cáo theo tuần về sau, gồm cả Weekly Report gửi thứ Bảy.

Chốt xong thì ghi vào `schema_context.py` để đường SQL tự do và đường công cụ không dạy model hai
điều trái ngược — đúng bài học từ vụ `IsAC` ngày 26/08.

### 3. ✅ Role trưởng phòng không hiện trong bảng quản lý tài khoản — ĐÃ SỬA

Cùng phản hồi 14/08 ở trên: *"Role trưởng phòng không hiện trong bảng qltk"*.

**Điều tra 03/09/2026**: không phải dòng bị ẩn, cũng không phải lỗi dữ liệu — `list_users()`
(`backend/auth.py`) trả về mọi tài khoản không lọc theo role, và `GET /admin/users` không lọc thêm.
Bản panel đang chạy tại thời điểm phản hồi (commit `c40f792`, `src/app/AdminUsersPanel.tsx`) hiển
thị **nguyên mã tiếng Anh**: `<span>Role:</span> {u.role}` — tài khoản `regional_director` hiện ra
là chữ `regional_director`, không có chỗ nào ghi chữ "Trưởng phòng" để người dùng tìm thấy.

**Đã sửa tại `516525b` (28/08/2026)**: thêm `src/app/roleLabels.ts` làm nguồn nhãn duy nhất, đổi
bảng sang `<span>Vai trò:</span> {getRoleLabel(u.role)}` — `regional_director` nay hiện đúng
"Giám đốc Miền / Kênh (Trưởng phòng)". Dropdown tạo/sửa tài khoản đã có `regional_director` từ
04/08 (`0884a4c`, `5189ca0`), chỉ riêng bảng hiển thị là còn thiếu nhãn — nay đã đồng bộ.

Đã xác nhận production build từ `src/app/` (không phải hai cây trùng lặp `frontend/` hay
`bao-cao-canh-bao/`), nên bản vá này đã có hiệu lực trên live site.

---

## ⛔ CHẶN BỞI NGUỒN DỮ LIỆU — cần DNH mở nguồn

Bốn ca dưới đây **không phải thiếu công sức phát triển**. Chúng là **bằng chứng thực địa** cho mục
"nguồn dữ liệu còn thiếu" trong báo cáo tiến độ: người dùng thật của DNH đã hỏi và đã vấp phải.

| Ca | Câu hỏi | Thiếu gì |
|---|---|---|
| **14/08 · `truongphongmb`** | *"Top 20 nhà phân phối theo doanh thu tháng 7, tách theo kênh?"*<br>→ chatbot trả về **khách hàng** thay vì nhà phân phối. Người dùng ghi: *"trả về danh sách khách hàng thay vì nhà phân phối (DistributorCode)"* | Hoá đơn **không có khoá NPP/chi nhánh** |
| **17/08 · `dnh`** | *"Nhóm sản phẩm nào đóng góp doanh thu lớn nhất và có bao nhiêu mã hàng bán ra?"* | `brv_sanpham.group_code` **không phủ hết** mã hàng đã bán; chưa có danh mục ngành hàng có tên rõ ràng |
| **25/08 · `vui.hoangthi`** | *"Đánh giá tình hình thị trường TP.HCM tuần 17–22/8, chỉ ra khuyến nghị"* | Báo cáo địa bàn **chỉ có theo THÁNG**, không tách doanh thu theo tỉnh theo TUẦN |
| **25/08 · `vui.hoangthi`** | *"Khả năng phát triển khách hàng lẻ của TDV Thương?"* | Chưa có công cụ đếm khách mới/khách lẻ theo **từng nhân viên cá nhân** (hiện chỉ có theo đội QLV) |

Ca thứ tư có thể một phần giải được bằng công cụ đã có (`customer_lifecycle_summary` nhận
`scope_employee_code`) — cần kiểm lại trước khi xếp hẳn vào nhóm thiếu nguồn.

---

## Nguyên tắc rút ra

Ba ca `wrong_number` đều là loại **"số sai nhưng câu trả lời trông hoàn toàn hợp lý"** — không báo
lỗi, không sập, chỉ đưa ra con số sai một cách thuyết phục. Người dùng phát hiện được vì họ **biết
nghiệp vụ**, không phải vì hệ thống tự báo.

Đó chính là lý do tồn tại của bộ 35 phép kiểm bất biến
(`scripts/doi_chieu_so_lieu_tool_moi.py`, chạy miễn phí): bắt loại lỗi này **trước khi** người dùng
gặp. Nên chạy lại sau mỗi đợt thay đổi logic số liệu.
