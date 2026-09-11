<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Cấm chạy business-eval và gọi API trả phí không điều phối (từ 11/09/2026)

- `business-eval` (`scripts/run_business_evaluation.py`) đã bị **gỡ bỏ và cấm dùng**. Không chạy lại, không
  khôi phục từ git history, không viết script thay thế chạy cả bộ câu hỏi. Lý do: ngày 10/09/2026 lúc 15–16h
  nó chạy 235 lượt gọi model (7,08 USD) trong lúc không ai điều phối.
- Mọi lượt gọi model trả phí (`nl2sql.ask`, runner 138 câu, verify/retest) phải được **anh Đăng** duyệt trước,
  kể cả khi chỉ vài câu. Không tự chạy trong nền hoặc tiếp tục chạy khi người giao việc vắng mặt.
- Khi được phép gọi `nl2sql.ask` từ script: **bắt buộc** truyền `username` riêng cho lượt chạy và `session_id`
  có tiền tố nhận diện được, để log chi phí truy ra được nguồn. Lượt gọi không tên không lọc được theo vai/vùng
  nên kết quả **không dùng để chấm UAT**.
