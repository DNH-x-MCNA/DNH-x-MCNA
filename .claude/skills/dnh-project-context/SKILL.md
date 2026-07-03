---
name: dnh-project-context
description: Bối cảnh và các quyết định kiến trúc đã chốt cho dự án Dược Nam Hà (DNH) - tích hợp dữ liệu và AI Chatbot. Luôn dùng skill này khi làm việc trong repo DNH, khi review code backend/frontend/ai_agent/scripts, khi viết tài liệu kỹ thuật, hoặc khi user hỏi về DNH, Dược Nam Hà, Phase 1, Phase 2, Bravo, DMS. Đảm bảo mọi output tuân thủ kiến trúc đã ký hợp đồng, không đề xuất lại các quyết định đã chốt.
user-invocable: false
---

# DNH Project Context

Nền tảng bối cảnh cho mọi tác vụ trong repo `lvd192/DNH`. Đây là dự án tư vấn 2 giai đoạn của MCNA cho khách hàng Dược Nam Hà (DNH) - công ty dược phẩm.

## Cấu trúc repo

```
DNH/
├── docs/         # đặc tả yêu cầu, thiết kế database, API
├── backend/      # API Middleware (Python/NodeJS) kết nối DB trung gian
├── frontend/     # Webapp Portal & Dashboard (Next.js/React)
├── ai_agent/     # AI Chatbot: Text-to-SQL + Semantic Layer (Phase 2)
├── scripts/      # ETL đồng bộ dữ liệu từ Bravo/DMS
├── config/
├── mock_source/  # dữ liệu mẫu để test ETL/chatbot khi chưa có access thật
├── src/
└── main.py, manifest.json, query
```

## Phạm vi dự án (đã chốt, KHÔNG đề xuất lại)

**Phase 1 - Data Engineering & Reporting:**
- Tự động hoá báo cáo + email alert
- 4 trigger alert cụ thể đã định nghĩa (xem `dnh-email-alert-builder` skill)
- ETL từ Bravo/DMS về DB trung gian, **read-only** — không được ghi ngược vào hệ thống nguồn
- **KHÔNG có dashboard scope** — DNH đã có đội DA riêng tự làm dashboard trên dữ liệu trung gian

**Phase 2 - AI Chatbot (NL2SQL):**
- Chatbot cho C-level query dữ liệu bằng tiếng Việt
- Kiến trúc: Text-to-SQL + Semantic Layer trong `ai_agent/`
- Bắt buộc theo `dnh-nl2sql-security` skill khi code hoặc review phần này

## Kiến trúc dữ liệu (đã chốt — cập nhật 03/07/2026)

- **Tầng dữ liệu trung gian chạy trên cloud Postgres (Supabase)**, không còn on-premises SQL Server. Đây là thay đổi kế hoạch so với bản gốc — xem "Lịch sử thay đổi" bên dưới. Code kết nối qua biến `CLOUD_DB_URL` (`.env`), có fallback về SQLite cục bộ (`scripts/dnh_intermediate.db`) khi cloud không khả dụng.
- ETL vẫn là **read-only** từ hệ thống nguồn (Bravo, DMS) — mọi write chỉ nằm trong DB trung gian (giờ là Supabase), không ghi ngược nguồn.
- Kết nối tới cloud DB phải dùng **một engine/connection pool dùng chung** (đã từng phát hiện lỗi tạo `create_engine` mới cho mỗi lần gọi trong `ai_agent/chatbot.py`, gây chậm và tốn kết nối — đã sửa bằng `_get_cloud_engine()` cache theo process). Không revert về pattern tạo engine rời rạc mỗi call.
- Vì đổi sang cloud, cần rà lại data residency/compliance cho dữ liệu dược phẩm (khách hàng, công nợ) trước khi go-live thật — xem mục câu hỏi mở bên dưới, chưa nên coi đây là đã xác nhận đầy đủ với client chỉ vì đã đổi trong code.
- **Kiến trúc kỹ thuật chi tiết** (4 phương án lấy dữ liệu realtime, schema `raw_*/stg_*/mart_*`, watermark/upsert, Notification Engine event-driven, Claude API cho chatbot) → xem skill `dnh-realtime-etl-pipeline`, nguồn là `MCNA_DNH_Timeline_v1.2.pdf`. Không lặp lại chi tiết đó ở đây, chỉ giữ bối cảnh tổng quan.

### Lịch sử thay đổi
- **Bản gốc hợp đồng:** 3 tầng dữ liệu on-premises trên SQL Server, do chính sách data residency của DNH — không dùng cloud DB.
- **03/07/2026:** đổi sang cloud DB (Supabase Postgres) theo chỉ đạo cập nhật kế hoạch. Lý do nghiệp vụ cụ thể (đổi yêu cầu từ client hay quyết định kỹ thuật nội bộ) **chưa được ghi lại** — nếu có thêm chi tiết, bổ sung vào đây để không mất ngữ cảnh khi hợp đồng/PM cần đối chiếu.

## Timeline

- Kick-off: **07/07/2026**
- **Bản kỹ thuật chi tiết nhất (ưu tiên dùng)**: `MCNA_DNH_Timeline_v1.2.pdf` (lập 02/07/2026) — lộ trình 3 tháng/12 tuần: T1 W1-2 khảo sát hạ tầng & tạo project Supabase → T1 W3-4 xây ETL lõi (watermark) → T2 W5-6 Notification Engine bản test (Gmail/Telegram) → T2 W7-8 tích hợp Claude API cho chatbot + chuyển kênh production (Graph API/Teams) → T3 W9-10 UAT & go-live → T3 W11-12 giám sát & tối ưu. Chi tiết đầy đủ xem `dnh-realtime-etl-pipeline`.
- Mốc "9 tuần, 2 phase" trong `MCNA_DNH_ProjectPlan_v3.docx` (bản đề xuất/hợp đồng gốc) vẫn là tài liệu phạm vi/scope tổng quát — nếu hai bản mâu thuẫn về mốc thời gian kỹ thuật, ưu tiên Timeline v1.2 vì mới hơn và chi tiết hơn.

## Câu hỏi mở cần xác nhận khi onsite (chưa chốt)

- Baseline để tính "sụt giảm doanh thu" (revenue drop)
- Ngày cơ sở (date basis) để tính tuổi nợ (debt aging)
- ~~Vị trí đặt data warehouse trên SQL Server~~ — đã thay bằng cloud (Supabase); câu hỏi mở mới: region/project Supabase cụ thể, ai quản lý access (service role key, RLS), chính sách backup/retention trên cloud, và có cần DNH ký lại phụ lục data residency không.

Khi những câu hỏi này chưa có câu trả lời từ client, code liên quan phải để dạng config/parameter, KHÔNG hardcode giả định.

## Rủi ro bảo mật đã phát hiện trong prototype (phải tránh lặp lại)

- Thiếu authentication ở API middleware
- SQL injection qua việc chạy trực tiếp SQL do LLM generate
- Kết nối DB không nhất quán giữa các module

Khi review hoặc viết code mới trong `backend/` hoặc `ai_agent/`, luôn kiểm tra 3 điểm này trước.
