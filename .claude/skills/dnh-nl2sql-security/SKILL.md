---
name: dnh-nl2sql-security
description: Checklist bảo mật bắt buộc cho AI Chatbot NL2SQL của dự án DNH (Phase 2, thư mục ai_agent/). Dùng skill này mỗi khi viết, sửa, hoặc review bất kỳ code nào cho phép LLM sinh ra SQL và thực thi trên database, kể cả code trong ai_agent/, backend/, hoặc bất kỳ chỗ nào chuyển câu hỏi tiếng Việt thành SQL. Bắt buộc kiểm tra trước khi merge PR liên quan đến text-to-SQL, semantic layer, hoặc chatbot query engine.
---

# DNH NL2SQL Security Checklist

## Bối cảnh

Prototype ban đầu của DNH chatbot có lỗ hổng SQL injection nghiêm trọng: SQL do LLM generate được thực thi trực tiếp không qua validation. Skill này enforce các lớp bảo vệ đã được thiết kế lại — **không được bỏ qua bất kỳ layer nào** dù chỉ để demo nhanh.

Checklist này áp dụng bất kể LLM provider nào đang chạy phía sau (`ai_agent/chatbot.py` hiện dùng Gemini/OpenAI làm tạm; kế hoạch chính thức là Claude API — xem `dnh-realtime-etl-pipeline`). Khi thêm nhánh Claude, mọi layer bảo vệ dưới đây vẫn phải giữ nguyên, không viết lại pipeline riêng cho provider mới.

## Các lớp bảo vệ bắt buộc (multi-layer SQL validation)

1. **Không bao giờ execute SQL raw từ LLM output trực tiếp.**
   - LLM chỉ được sinh SQL, không có quyền tự thực thi.
   - Phải đi qua parser/validator trước khi chạy.

2. **Whitelist thao tác:** Chỉ cho phép `SELECT`. Chặn tuyệt đối `INSERT/UPDATE/DELETE/DROP/ALTER/EXEC/TRUNCATE` và multi-statement (`;`).

3. **RBAC filter injection:** Mọi câu SQL trước khi chạy phải được inject thêm điều kiện WHERE dựa trên role/scope của user hỏi (C-level chỉ xem được data theo quyền được cấp — không dựa vào LLM tự tuân thủ prompt, phải enforce ở tầng code sau khi SQL được sinh ra).

4. **Confidence scoring:** Nếu model không tự tin về SQL sinh ra (ambiguous question, thiếu context), phải trả lời "cần làm rõ" thay vì đoán và chạy SQL sai.

5. **Audit logging:** Log đầy đủ mọi câu hỏi tiếng Việt gốc + SQL được sinh ra + user + timestamp + kết quả (hoặc lỗi). Không được thiếu log cho bất kỳ query nào, kể cả query bị chặn.

6. **Semantic layer là lớp trung gian bắt buộc** — LLM không truy cập trực tiếp schema DB thật, mà qua semantic layer đã được định nghĩa trước (giới hạn bảng/cột được phép truy vấn).

7. **Timeout & resource limit:** Query phải có timeout, giới hạn số dòng trả về, tránh LLM sinh query full-scan bảng lớn.

## Khi review PR

Từ chối merge nếu thiếu bất kỳ điều nào:
- [ ] SQL đi qua validator trước khi execute
- [ ] Chỉ SELECT, không multi-statement
- [ ] RBAC filter được inject ở tầng code, không dựa vào prompt
- [ ] Có confidence threshold + fallback "cần làm rõ"
- [ ] Audit log đầy đủ
- [ ] Semantic layer giới hạn schema truy cập được
- [ ] Có timeout/row limit

## Khi viết code mới

Ưu tiên cấu trúc: `User question (VN) → LLM sinh SQL qua semantic layer → Validator (whitelist + RBAC inject) → Execute (timeout/limit) → Audit log → Trả kết quả`. Không rút gọn pipeline này dù để demo nhanh cho onsite.
