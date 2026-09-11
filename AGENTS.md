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

## Không sửa code trực tiếp trên máy 24 (từ 11/09/2026)

- Máy 24 là máy chạy chatbot thật. **Không sửa code trên máy 24.** Sửa ở máy phát triển, commit, chạy test,
  rồi máy 24 chỉ `git pull` bản đã test và khởi động lại dịch vụ.
- Lý do: ngày 10–11/09/2026 có 361 dòng backend bị sửa tay trên máy 24, không qua git, không review. File trên
  đĩa lệch với code đang chạy, và một bản sửa đảo ngược chính sách V25 suýt lên chạy thật chỉ vì một lần
  khởi động lại. Toàn bộ đã được cất vào nhánh `may24-sua-tay-1109` để review.
- Nếu buộc phải thử trên máy 24: tạo nhánh riêng, commit và push ngay. Không để thay đổi chưa commit trên
  máy 24 qua giờ nghỉ, và không khởi động lại dịch vụ khi đĩa đang lệch với bản đã deploy.

## Quy tắc nghiệp vụ đã chốt — không tự đảo ngược

- **Thưởng V25 dừng từ 01/07/2026** theo quyết định đã chốt, thay bằng V15/V22. V25Bonus = 0 từ kỳ 07/2026 là
  đúng cơ chế, **không phải lỗi thủ tục tính lương**. Các dòng V25 còn `EndDate` NULL trong `DIM_BacThuong` là
  cấu hình chưa đóng, không phải bằng chứng V25 còn hiệu lực. Không đề nghị bù hay truy lĩnh thưởng V25.
- Test `test_v25_tu_07_2026_la_doi_co_che_khong_phai_mismatch` và
  `test_salary_bonus_policy_v25_tu_07_khong_bao_sai_loi_he_thong` khoá quy tắc này. Bản sửa nào làm hai test
  này hỏng là sai, không được sửa test cho khớp.
