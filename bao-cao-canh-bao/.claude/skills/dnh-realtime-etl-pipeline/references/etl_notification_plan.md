# Tóm tắt MCNA_DNH_Timeline_v1.2.pdf

> Nguồn gốc: `MCNA_DNH_Timeline_v1.2.pdf` (root repo), lập 02/07/2026, phiên bản 1.2.
> File này là bản tóm tắt kỹ thuật để tra cứu nhanh — nếu cần trích dẫn chính xác từng câu chữ (vd. khi làm việc với khách hàng), đọc lại bản PDF gốc.

## 1. Tổng quan yêu cầu

Luồng dữ liệu mục tiêu:

```
ERP (Bravo), CRM, ... (nguồn Raw, SQL Server)
 ├── [Luồng hiện tại]  ETL → Máy chủ khách → Power BI (giữ nguyên, KHÔNG đụng vào)
 └── [Luồng mới - phạm vi dự án]
     ETL (Python) → Supabase (Data Warehouse)
        │
        ▼
     Notification Engine (event-driven)
        ├── Email: Microsoft Outlook (Graph API)
        └── Chatbot: Microsoft Teams (dùng Claude API)

Giai đoạn TEST:
  Email   → Gmail / Outlook test mailbox
  Chatbot → Telegram Bot
```

Mục tiêu: dữ liệu Bravo/SQL Server → Supabase gần như real-time → tự động sinh notification + cho phép hỏi-đáp qua chatbot.

## 2. Hiện trạng dữ liệu (3 lớp hiện có)

| Layer | Vai trò | Công nghệ | Tần suất |
|---|---|---|---|
| Layer 1 – Raw | Dữ liệu gốc ERP/CRM | Bravo (SQL Server) | Theo giờ cố định, nhiều lần/ngày |
| Layer 2 – Staging | ETL đẩy sang máy chủ khách | ETL job hiện có của khách | Theo lịch, đồng bộ Layer 1 |
| Layer 3 – Báo cáo | Trực quan hoá | Power BI | Refresh theo lịch (Import mode), giới hạn số lần/ngày |

**Điểm mấu chốt**: cả Layer 1 lẫn Layer 3 đều batch, không realtime tuyệt đối → hệ thống mới cần hiểu là **near-real-time (NRT)**, không phải realtime tức thời, và không được tạo tải nặng lên SQL Server nguồn.

## 3. Phương án kéo dữ liệu Realtime/NRT từ SQL Server

### Phương án A — Polling theo watermark (khuyến nghị triển khai trước)
- ETL Python chạy định kỳ 5–15 phút (cron/Airflow/Windows Task Scheduler).
- Query: `SELECT * FROM table WHERE UpdatedAt > @last_watermark`.
- Cần cột thời gian cập nhật (`UpdatedAt`, `ModifiedDate`...); nếu Bravo chưa có, cần đề xuất bổ sung hoặc dùng cột khoá tăng dần (`ID`, `RowVersion`).
- Ưu điểm: đơn giản, không cần quyền cao, triển khai nhanh, rủi ro thấp.
- Nhược điểm: có độ trễ = chu kỳ polling; không phát hiện DELETE nếu không có cờ soft-delete.

### Phương án B — SQL Server Change Tracking (CT)
- Có sẵn từ SQL Server 2008+, nhẹ hơn CDC, chỉ lưu "hàng nào đã đổi".
- ETL dùng `CHANGETABLE(CHANGES ...)` lấy thay đổi từ lần đồng bộ trước, JOIN lấy dữ liệu mới nhất.
- Ưu điểm: phát hiện chính xác INSERT/UPDATE/DELETE, tải nhẹ.
- Nhược điểm: cần bật ở cấp database/table trên Bravo → cần xin quyền/đánh giá tác động với đội quản trị Bravo.

### Phương án C — SQL Server Change Data Capture (CDC)
- Ghi đầy đủ lịch sử thay đổi (before/after) vào bảng `cdc.*`.
- ETL đọc log LSN tăng dần.
- Ưu điểm: đầy đủ nhất, phù hợp audit trail.
- Nhược điểm: cần SQL Server Standard/Enterprise hỗ trợ CDC, tốn I/O, cần quyền sysadmin — khả năng cao phải phối hợp IT/vendor Bravo.

### Phương án D — Trigger + Queue table / Service Broker (event-driven, đẩy thay vì kéo)
- Trigger trên bảng nguồn ghi ID bản ghi thay đổi vào bảng hàng đợi, hoặc Service Broker bắn message ngay khi có thay đổi.
- Ưu điểm: độ trễ thấp nhất trong các phương án dùng SQL Server thuần.
- Nhược điểm: phải sửa schema/database Bravo — rủi ro cao (ERP thương mại đóng gói), có thể vi phạm điều khoản hỗ trợ hoặc bị ghi đè khi Bravo update version.

### Khuyến nghị lộ trình
- **Giai đoạn 1 (MVP)**: Phương án A, chu kỳ 5–15 phút — không động vào hệ thống Bravo.
- **Giai đoạn 2 (tối ưu)**: đánh giá bật Change Tracking (B) trên các bảng cụ thể, sau khi đội quản trị Bravo/SQL Server chấp thuận.
- **Không khuyến nghị** đụng trigger/CDC trực tiếp trên database lõi Bravo trừ khi có xác nhận rõ ràng từ nhà cung cấp Bravo.
- ETL mới chạy song song, dùng kết nối/user SQL Server riêng, **read-only**, độc lập lịch chạy — không chia sẻ tài nguyên với job ETL nuôi Power BI.

## 4. Kiến trúc ETL & Data Warehouse (Python + Supabase)

### 4.1 Thành phần
- **Extract**: Python (pyodbc/pymssql) kết nối SQL Server Bravo, đọc theo watermark.
- **Transform**: chuẩn hoá kiểu dữ liệu, mapping trường, gộp bảng (pandas hoặc SQL thuần trong Postgres sau khi load).
- **Load**: ghi vào Supabase (Postgres) qua Supabase Python client hoặc psycopg2/SQLAlchemy trực tiếp, **dùng upsert theo khoá chính** để tránh trùng lặp.
- **Lưu trạng thái đồng bộ**: bảng `sync_watermark` trong Supabase — thời điểm/ID đồng bộ gần nhất mỗi bảng nguồn, đảm bảo idempotent.
- **Scheduler**: cron / Airflow / GitHub Actions scheduled workflow (tuỳ hạ tầng khách cho phép).

### 4.2 Tận dụng Supabase Realtime cho tầng thông báo
- Supabase hỗ trợ Realtime (logical replication/WAL) và Database Webhooks.
- ETL insert/update mới → Database Webhook gọi thẳng Notification Engine (HTTP endpoint) ngay khi có thay đổi, thay vì Notification Engine phải polling lại Supabase.
- → toàn chuỗi "SQL Server → Supabase → Notification" trở thành event-driven, giảm độ trễ tổng thể.

### 4.3 Schema đề xuất (mô hình lớp dữ liệu Supabase)
- `raw_*`: dữ liệu thô, gần nguyên bản Bravo (bronze).
- `stg_*`: dữ liệu đã chuẩn hoá, làm sạch (silver).
- `mart_*`: dữ liệu tổng hợp phục vụ trực tiếp notification/chatbot (gold).
- `sync_watermark`, `etl_run_log`: bảng vận hành, theo dõi tình trạng đồng bộ và log lỗi.

## 5. Hệ thống Notification & Chatbot

### 5.1 Notification qua Email (Outlook)
- **Production**: Microsoft Graph API (`sendMail`), đăng ký app trên Azure AD (App Registration), quyền `Mail.Send`.
- **Test**: Gmail SMTP/API hoặc mailbox Outlook test riêng (sandbox) — không phát tán thông báo thật trong giai đoạn kiểm thử.
- Logic: Notification Engine nhận sự kiện từ Supabase Webhook → format nội dung (template) → gọi API gửi mail.

### 5.2 Chatbot trên Microsoft Teams (dùng Claude API)
- **Production**: đăng ký bot qua Azure Bot Framework, tạo Teams App Manifest, cấu hình endpoint bot trỏ về backend.
- Backend nhận câu hỏi từ Teams → gọi **Claude API** (kèm ngữ cảnh dữ liệu từ Supabase) → trả lời tự nhiên.
- **Test**: Telegram Bot API (BotFather) — setup nhanh, không cần phê duyệt phức tạp như Teams/Azure Bot. Sau khi luồng logic ổn định mới port sang Teams SDK.

### 5.3 Kiến trúc Notification Engine
```
Supabase Webhook (event) ──► Notification Engine (Python/FastAPI)
  ├── Xác định loại sự kiện & đối tượng nhận
  ├── Gọi Claude API (nếu cần format/nội dung động)
  ├── Gửi Email (Outlook Graph API / Gmail test)
  └── Gửi/khởi tạo hội thoại Chatbot (Teams / Telegram test)
```

## 6. Lộ trình triển khai theo giai đoạn (3 tháng / 12 tuần)

| Tháng/Tuần | Giai đoạn | Nội dung | Đầu ra |
|---|---|---|---|
| T1 W1-2 | Khảo sát & chuẩn bị hạ tầng | Xin quyền đọc SQL Server (read-only), xác định bảng/trường cần lấy, tạo project Supabase, đăng ký Azure AD app | Danh sách bảng nguồn, tài khoản kết nối, môi trường Supabase |
| T1 W3-4 | Xây ETL lõi | Pipeline Python (E-T-L) theo watermark, bảng `sync_watermark`, lịch chạy | ETL chạy ổn định, dữ liệu vào Supabase đúng, đồng bộ định kỳ |
| T2 W5-6 | Notification Engine (bản test) | Webhook từ Supabase, gửi thử qua Gmail/Outlook test và Telegram | Luồng thông báo end-to-end trên kênh test |
| T2 W7-8 | Tích hợp Claude API cho Chatbot | Thiết kế prompt, dùng dữ liệu Supabase làm ngữ cảnh, test hội thoại qua Telegram | Chatbot trả lời đúng dữ liệu, phản hồi hợp lý |
| T2 W7-8 | Chuyển sang kênh Production | Cấu hình Outlook Graph API chính thức, đăng ký & publish Teams Bot | Notification/chatbot chạy trên kênh thật |
| T3 W9-10 | UAT & Go-live | Khách hàng kiểm thử thực tế, tinh chỉnh nội dung/logic, giám sát log lỗi | Nghiệm thu, chuyển giao vận hành |
| T3 W11-12 | Giám sát & tối ưu sau go-live | Theo dõi độ trễ đồng bộ, tối ưu chu kỳ polling, đào tạo user, bàn giao tài liệu | Báo cáo vận hành, đề xuất cải tiến |

## 7. Rủi ro & lưu ý cần thống nhất với khách hàng

- **Quyền truy cập SQL Server (Bravo)**: cần tài khoản read-only riêng, tránh ảnh hưởng luồng ETL/Power BI hiện có.
- **Cột thời gian cập nhật**: cần xác nhận các bảng nguồn có `UpdatedAt`/tương đương; nếu không, thống nhất phương án thay thế (vd. ID tăng dần) hoặc đề xuất bổ sung.
- **Độ trễ thực tế**: cần SLA cụ thể (vd. "trong vòng 10 phút") để chọn chu kỳ polling phù hợp — tránh kỳ vọng "realtime tức thời" không khả thi ở giai đoạn 1.
- **Bảo mật**: connection string SQL Server, Supabase service key, Claude API key → secrets manager/biến môi trường, không hardcode.
- **Dữ liệu nhạy cảm**: nếu ERP/CRM có PII/tài chính, cần rà soát trường nào được phép vào Supabase và hiển thị qua notification/chatbot.
- **Chi phí vận hành**: Supabase (theo gói), Claude API (theo token), Azure Bot Framework/Teams (theo cấu hình app) — cần dự trù chi phí hàng tháng.
- **Phụ thuộc Bravo**: nâng cấp lên Change Tracking/CDC sau này phải làm việc với đội quản trị/nhà cung cấp Bravo để xin phép và đánh giá tác động.

## 8. Tóm tắt khuyến nghị kỹ thuật

- Watermark polling (5–15 phút) cho giai đoạn đầu, không động vào schema Bravo.
- Supabase làm Data Warehouse trung tâm, tận dụng Database Webhooks/Realtime để "Supabase → Notification" thành event-driven.
- Notification Engine dùng chung một backend cho cả email và chatbot, chỉ khác kênh gửi — dễ chuyển đổi test/production mà không viết lại logic.
- Test toàn bộ luồng qua Gmail + Telegram trước, khi ổn định mới chuyển Outlook Graph API + Teams Bot Framework.
- Đánh giá nâng cấp Change Tracking ở giai đoạn 2 nếu SLA độ trễ khắt khe hơn mức polling đáp ứng được.
