---
name: dnh-realtime-etl-pipeline
description: Kiến trúc ETL realtime (SQL Server Bravo → Supabase) + Notification Engine + kênh Chatbot, theo kế hoạch kỹ thuật đã chốt trong MCNA_DNH_Timeline_v1.2.pdf (02/07/2026). Dùng skill này khi viết/sửa/review code ETL/sync trong scripts/, khi thiết kế schema Supabase, khi làm Notification Engine (email/chatbot), hoặc khi quyết định LLM provider/kênh gửi cho ai_agent/, src/notifier.py, src/teams_bot.py.
---

# DNH Realtime ETL & Notification Pipeline

## Nguồn chuẩn

Toàn văn kế hoạch: `MCNA_DNH_Timeline_v1.2.pdf` (gốc dự án, lập 02/07/2026). Bản tóm tắt đầy đủ, greppable tại `references/etl_notification_plan.md`. Đây là nguồn xác nhận chính thức cho kiến trúc Supabase — khớp với quyết định đã ghi trong `dnh-project-context`.

## Lấy dữ liệu realtime từ SQL Server (Bravo)

- **Giai đoạn 1 — bắt buộc bắt đầu bằng Phương án A (watermark polling)**: `SELECT ... WHERE UpdatedAt > @last_watermark`, chu kỳ 5–15 phút. Không nhảy thẳng lên B/C/D khi A chưa triển khai/đánh giá xong.
- Phương án B (SQL Server Change Tracking) chỉ xét ở giai đoạn 2, và PHẢI có xác nhận/quyền từ đội quản trị Bravo trước khi bật ở cấp database/table.
- Phương án C (CDC) và D (trigger/Service Broker) — KHÔNG tự ý triển khai. D rủi ro cao nhất vì sửa schema của ERP đóng gói (Bravo), có thể vi phạm điều khoản hỗ trợ hoặc bị ghi đè khi Bravo update version. Chỉ làm nếu có xác nhận rõ ràng từ nhà cung cấp Bravo.
- ETL mới PHẢI dùng connection/user SQL Server **read-only riêng**, chạy độc lập theo lịch riêng — không chia sẻ tài nguyên hay phụ thuộc job ETL đang nuôi Power BI hiện có.
- Nếu bảng nguồn không có cột `UpdatedAt`/tương đương → đây là câu hỏi cần xác nhận với khách hàng (xem `dnh-onsite-prep`), không tự ý chọn giải pháp thay thế (vd. ID tăng dần) mà không ghi chú lại lý do.

## ETL & Supabase schema

- Load phải **upsert theo khoá chính** để idempotent. `scripts/sync_to_supabase.py` hiện dùng `df.to_sql(table, engine, if_exists='replace', ...)` — ghi đè toàn bảng mỗi lần đồng bộ, KHÔNG khớp kế hoạch và không an toàn cho luồng near-real-time (mất dữ liệu tạm thời trong lúc replace, không watermark). Đây là việc cần sửa khi chuyển ETL lõi từ mock sang thật.
- Bắt buộc có bảng vận hành `sync_watermark` (thời điểm/ID đồng bộ gần nhất mỗi bảng nguồn) và `etl_run_log` (log lỗi/tình trạng chạy) — hiện CHƯA có trong codebase.
- Schema Supabase nên phân lớp: `raw_*` (bronze, gần nguyên bản Bravo) → `stg_*` (silver, đã chuẩn hoá) → `mart_*` (gold, phục vụ trực tiếp chatbot/notification). Các bảng hiện tại (`brv_hoadonhdr`, `dms_khachhang`, `fact_tonghopkhachhang`...) tương đương tầng `raw_*`/gần Bravo. Khi thiết kế thêm bảng tổng hợp phục vụ chatbot, ưu tiên đặt ở tầng `mart_*` thay vì để chatbot tự JOIN nhiều bảng raw phức tạp mỗi lần (giảm rủi ro sai logic nghiệp vụ lặp lại trong system prompt của `ai_agent/chatbot.py`).

## Notification Engine

- Kiến trúc mục tiêu: Supabase Database Webhook (event khi insert/update) → Notification Engine (Python/FastAPI) → xác định loại sự kiện/đối tượng nhận → (tuỳ chọn) gọi Claude API để format nội dung động → gửi qua kênh tương ứng.
- `main.py` hiện dùng vòng lặp polling cố định (`etl_check_interval_seconds`), không phải webhook — hành vi tạm chấp nhận được cho giai đoạn đầu, nhưng khi refactor Notification Engine cần hướng tới webhook event-driven, không nhân rộng thêm polling loop mới.
- Email: **production PHẢI dùng Microsoft Graph API** (`Mail.Send`, Azure AD App Registration) — không phải SMTP trực tiếp. `src/notifier.py` hiện dùng `smtplib`/Outlook SMTP — đây là hành vi TEST hợp lệ (tương đương "Outlook test mailbox" trong kế hoạch), không phải bản production cuối cùng.
- Chatbot: **production là Microsoft Teams**, **test là Telegram** — khớp với code hiện tại (`src/teams_bot.py` + nhánh Telegram trong `ai_agent/chatbot.py`/`src/notifier.py`). Giữ nguyên pattern một backend dùng chung, chỉ khác kênh gửi — không viết logic riêng cho từng kênh.

## LLM Provider cho Chatbot

- Kế hoạch đã chốt: **chatbot dùng Claude API** (Anthropic), không phải Gemini/OpenAI.
- **Đã lấp (03/07/2026):** `ai_agent/chatbot.py` giờ có nhánh `ANTHROPIC_API_KEY` (`model_type = "claude"`, model `claude-opus-4-8`) qua `_call_claude()`, ưu tiên cao nhất trong chuỗi `if/elif` ở `__init__` — tự động dùng Claude ngay khi `.env` có `ANTHROPIC_API_KEY`, không cần sửa code thêm. Nhánh Gemini/OpenAI vẫn giữ nguyên làm fallback test/demo.
- **Còn thiếu:** `ANTHROPIC_API_KEY` thật — dự án hiện vẫn chạy Gemini vì chưa có key. Khi có key, chỉ cần thêm vào `.env` (đã có placeholder trong `.env.example`).
- Lưu ý kỹ thuật: `claude-opus-4-8` không nhận `temperature`/`top_p`/`top_k` (400 nếu gửi) — `_call_claude()` cố tình không forward tham số sampling, khác với nhánh Gemini/OpenAI.
- Việc này thuộc phạm vi bắt buộc tuân theo checklist `dnh-nl2sql-security` khi code (multi-layer validation áp dụng bất kể provider nào — không đổi gì ở `_execute_sql`/validator khi thêm Claude).

## Bảo mật & vận hành (mục 7 kế hoạch)

- Secrets (SQL Server conn string, Supabase service key, Claude API key) chỉ qua biến môi trường/secrets manager — không hardcode. Khớp với rủi ro bảo mật đã ghi trong `dnh-project-context`.
- Trước khi đưa trường dữ liệu ERP/CRM nào vào Supabase hoặc hiển thị qua chatbot/notification, phải rà PII/dữ liệu tài chính nhạy cảm — không mặc định đưa hết mọi cột.
- Nâng cấp lên Change Tracking/CDC sau này luôn cần phối hợp với đội quản trị/nhà cung cấp Bravo — không tự quyết trong lúc code.

## Timeline tham chiếu

Xem `references/etl_notification_plan.md` mục "6. Lộ trình" — 3 tháng/12 tuần, 6 giai đoạn (khảo sát hạ tầng → ETL lõi → Notification bản test → tích hợp Claude API + chuyển kênh production → UAT/go-live → giám sát & tối ưu). Timeline này **thay thế/làm chi tiết hơn** mốc "9 tuần" cũ trong `dnh-project-context`; nếu thấy mâu thuẫn giữa hai nguồn, ưu tiên bản 12 tuần này vì mới hơn (lập 02/07/2026).
