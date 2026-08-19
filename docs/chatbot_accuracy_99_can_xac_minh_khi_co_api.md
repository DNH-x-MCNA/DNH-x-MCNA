# Danh sách cần xác minh qua chatbot thật khi ngân sách API phục hồi

Tổng hợp TOÀN BỘ thay đổi từ 18-19/08/2026 (16 commit code + 9 commit test/docs) — mọi thứ dưới
đây đã qua test giả lập (SQLite fixture, `_q_bravo` giả lập, git-stash xác nhận fail→pass), nhưng
**chưa có gì được xác minh bằng chatbot thật**. Không được coi các mục này là "đã xong" cho tới khi
chạy qua đây.

**Cách kiểm bắt buộc**: phiên chat MỚI (không hỏi lại trong phiên cũ — sẽ chỉ nhận lại câu trả lời
cũ từ bộ nhớ hội thoại). Đối chiếu `backend/logs/audit_log.jsonl` theo `session_id` để biết chắc
tool/SQL nào đã thực sự chạy, không chỉ nhìn câu trả lời.

---

## 🔴 Ưu tiên 1 — Bảo mật (đã xác nhận rò rỉ dữ liệu thật trên code cũ)

### 1. `get_salary_ranking` — lỗ hổng rò rỉ thưởng cá nhân (commit `795e7b8`)
Đăng nhập vai **QLV**, hỏi: *"Top 30 nhân viên có thưởng kinh doanh cao nhất tháng 7"*
- ✅ Kỳ vọng: chỉ thấy chính mình + TDV báo cáo trực tiếp lên mình
- ❌ Nếu thấy tên/mã nhân viên KHÔNG thuộc đội mình → fix chưa ăn, báo ngay

### 2. 5 tool bị chặn nhầm cho QLV, nay đã mở (commit `afc8c65`, `e3ba10c`)
Đăng nhập vai **QLV**, hỏi lần lượt (trước đây cả 5 câu đều bị từ chối cứng "chưa hỗ trợ giới hạn
theo đội"):
- *"Tồn kho vùng tôi hiện có bao nhiêu?"* (`get_inventory_by_region`)
- *"Công nợ vùng tôi tổng bao nhiêu, quá hạn bao nhiêu?"* (`get_receivables_overview`)
- *"Lịch sử QLV phụ trách các tổ trong vùng tôi"* (`get_qlv_change_history`)
- *"Đối soát doanh thu tháng 7 vùng tôi giữa 2 cách tính"* (`get_revenue_reconciliation`)
- *"Trong đội tôi có đơn nào nghi chạy dồn KPI không?"* (`check_order_timing`)
- ✅ Kỳ vọng: cả 5 câu trả lời được (không còn báo "chưa hỗ trợ giới hạn theo đội")
- ✅ Riêng câu cuối: QLV chỉ thấy tên trong đội mình, không thấy đội khác

---

## 🟠 Ưu tiên 2 — Sửa lỗi dữ liệu/logic thật (commit `7f39182`, `7d2427b`)

### 3. Q016 — "quản lý trực tiếp" dùng đúng cột
Hỏi: *"Bao nhiêu TDV chưa có quản lý trực tiếp trong dữ liệu tháng 7?"*
- ✅ Kỳ vọng: số gần 0 (trước đây ra 15 do dùng nhầm cột vùng thay vì cột quản lý)
- Đối chiếu `audit_log.jsonl`: SQL phải dùng `fact_tonghopkhachhang.manager_code`, KHÔNG dùng
  `dim_nhanvien.manager_area_code`

### 4. Q012 — đối soát doanh thu đủ 2 kênh
Hỏi: *"Đối soát doanh thu tháng 7 giữa view tổng và view thường: lệch bao nhiêu và nên tin nguồn nào?"*
- ✅ Kỳ vọng: SQL có cả `vHoaDonTotal`/`vHoaDon` (OTC) **và** `vHoaDonETCTotal`/`vHoaDonETC` (ETC)
- ❌ Trước đây chỉ có OTC, thiếu hẳn ETC

### 5. Q044 — công nợ 2 kênh tách riêng
Hỏi: *"Có bao nhiêu khách đang có dư nợ ở cả OTC và ETC; tổng nợ của họ thế nào?"*
- ✅ Kỳ vọng: câu trả lời tách riêng dư nợ/quá hạn OTC và ETC
- ❌ Trước đây chỉ trả tổng gộp, không tách được

### 6. `salary_achievement_summary` — QLV không còn báo sai "chưa có dữ liệu"
Vai **QLV**, hỏi: *"Trong đội tôi có bao nhiêu người đạt V15/V22/V25/ASO tháng 7?"*
- ✅ Kỳ vọng: trả lời có số liệu thật
- ❌ Trước đây LUÔN báo "chưa có snapshot đã chốt" dù dữ liệu tồn tại thật (lỗi định dạng mã)

---

## 🟡 Ưu tiên 3 — Hiển thị/UX (mojibake đã sửa, ảnh hưởng câu chữ không phải số liệu)

### 7. Cảnh báo đồng bộ treo (commit `ea013f8`, `b359cb6`, `e262128`)
Không có câu hỏi cụ thể — đây là footer TỰ ĐỘNG gắn vào MỌI câu trả lời có số liệu khi sync bị treo
quá 60 phút. Cách kiểm: hỏi bất kỳ câu doanh thu nào, xem cuối câu trả lời có dòng "CẢNH BÁO ĐỒNG
BỘ..." không khi sync thực sự đang chậm (theo dõi tại thời điểm dịch vụ sync có vấn đề thật), và
**đọc đúng tiếng Việt** (không vỡ chữ kiểu "CẢNH BÃO ÄỘNG Bá»˜").

### 8. Nhãn đỏ/vàng/xanh trong KPI theo ngày
Hỏi: *"Doanh số từng ngày của tôi tháng 7, ngày nào đỏ ngày nào vàng?"* (`get_employee_daily_kpi`)
- ✅ Kỳ vọng: nhãn hiện đúng "🔴 Đỏ"/"🟡 Vàng"/"🟢 Xanh" (chữ Việt sạch)
- ✅ Kỳ vọng: nếu hỏi thêm "có mấy ngày đỏ, mấy ngày vàng" → số đếm đúng thực tế (trước đây
  `count_red`/`count_yellow` LUÔN bằng 0 vì lỗi so khớp emoji hỏng)

### 9. Nhãn Tốt/Trung bình/Nguy hiểm trong xếp hạng KPI
Hỏi: *"Xếp hạng KPI tháng 7 của đội tôi"* (`get_employee_kpi`/status field)
- ✅ Kỳ vọng: nhãn "🟢 Tốt"/"🟡 Trung bình"/"🔴 Nguy hiểm" hiện đúng chữ Việt

### 10. Tách kênh đặc biệt trong doanh thu theo vùng
Hỏi: *"Doanh thu tháng 7 theo vùng, có tách riêng Modern Trade không?"* (`get_revenue_by_region`)
- ✅ Kỳ vọng: nếu vùng có Modern Trade/kênh đặc biệt, câu trả lời có mục tách riêng
  ("channel_breakdown") — trước đây tính năng này ÂM THẦM không bao giờ hoạt động

### 11. Nhãn chi nhánh tồn kho
Hỏi: *"Tồn kho theo chi nhánh"* (`get_inventory_by_region`, không giới hạn vùng)
- ✅ Kỳ vọng: tên chi nhánh hiện đúng "Sản xuất"/"Kinh doanh Miền Bắc/Trung/Nam" (chữ Việt sạch)

---

## 🔵 Ưu tiên 4 — Giới hạn vòng gọi tool theo vai trò (commit `6dd2196`)

Không có câu hỏi cụ thể để test trực tiếp số vòng (khó quan sát từ ngoài), nhưng cần theo dõi:
- Vai **QLV** hỏi câu phức tạp nhiều bước → nếu chạm trần 5 vòng, chatbot phải tự tổng hợp từ dữ
  liệu đã có, KHÔNG được nói "câu hỏi quá phức tạp"
- Vai **C-level** hỏi câu tương đương độ phức tạp → không được chạm trần sớm như QLV (có tới 10 vòng)
- Nếu QLV liên tục gặp "đã đạt giới hạn 5 lượt gọi tool, hãy tổng hợp..." ở câu hỏi đơn giản mà
  trước đây trả lời được trong 6 vòng (mức cũ) → có thể cần xem lại số 5 có quá chặt không

---

## 🟢 Ưu tiên 5 — Hướng dẫn SQL tự do mới thêm (commit `6dd3afb`) — CHƯA CÓ BẰNG CHỨNG THẬT

Khác các mục trên (đều dựa trên bug đã quan sát/tái hiện được), 3 mục này là hướng dẫn **phòng
ngừa dựa trên phân tích trước**, chưa từng thấy chatbot trả lời sai thật (vì bộ 90 câu gốc chỉ mới
chạy 1 lần và 3 câu này không có tool cố định nên không tự động đối chiếu được số).

- Q034: *"Những cặp sản phẩm nào thường được mua cùng một đơn nhất trong tháng 7?"*
  → kiểm SQL không tạo cặp A-A, không đếm đôi A-B/B-A
- Q033: *"Nhóm sản phẩm nào đóng góp doanh thu lớn nhất và có bao nhiêu mã hàng bán ra?"*
  → kiểm số mã hàng dùng COUNT(DISTINCT), không đếm trùng dòng
- Q029: *"Top 10 khách hàng chiếm bao nhiêu phần trăm doanh thu toàn công ty tháng 7?"*
  → kiểm tử số và mẫu số cùng phạm vi kênh (không lệch OTC-only vs OTC+ETC)

---

## Việc còn treo khác (không thuộc phần "double check", nhưng liên quan)

- **24 câu Q067-Q090 chưa từng test** — bị cắt ngang bởi sự cố ngân sách hôm 18/08, cần chạy lại
  toàn bộ nhóm (lương thưởng + CTKM + tồn kho + độ mới dữ liệu) sau khi ngân sách phục hồi.
- **`kpi_ranking()`/`revenue_tree()`** — 2 tool doanh thu/KPI còn lại chưa viết test giả lập, chưa
  rà bằng phương pháp code-only đã dùng cho các tool khác — có thể làm tiếp trước khi cần API.
