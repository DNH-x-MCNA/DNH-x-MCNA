# Tracking hoàn thiện dự án DNH — cập nhật 03/09/2026

## Kết quả đã hoàn tất trong đợt làm sạch miễn phí

| Việc | Trạng thái | Bằng chứng / ghi chú |
|---|---|---|
| Trang quyết định Nhóm A | Xong | `Nhom_A_can_DNH_chot_truoc_UAT_10-09-2026.md`, gồm A1–A9 và số câu bị ảnh hưởng trực tiếp. |
| Top sản phẩm tách OTC/ETC | Đã có trong code | Mô tả tool và system prompt đều buộc gọi hai lần khi so sánh hai kênh; không sửa lặp lại. |
| Bộ kiểm bất biến 40 công cụ | Xong phần code | Catalog phủ đúng 40/40 tool. Kho dev chạy được 35 phép đạt, 0 lệch; 25 mục bị bỏ vì kho dev thiếu bảng/cột hoặc không có dữ liệu. Phải chạy lại trên máy 24 trước UAT. |
| Panel vai trò Trưởng phòng | Đã có trong code | `regional_director` hiển thị “Giám đốc Miền / Kênh (Trưởng phòng)” ở danh sách, form tạo và form sửa. |
| S27/S30 mồ côi | Xong | C41 chuyển sang S27 (`READY_CURRENT`); C45 chuyển sang S30 (`READY`). Không còn checker mồ côi. |
| C01/M01 đủ 24 tháng | Xong và đã chạy thật | S01 đọc thẳng 24 tháng hóa đơn và tính MoM/YoY/tăng trưởng. Lần chạy cuối ra 72 dòng theo tháng và 3 dòng tăng trưởng; C01/M01 chuyển sang `READY`. |
| Quy tắc Active Customer | Xong | Thêm TK vào tầng nhân viên cùng TDV/CTV/CS; CS và TK dùng `is_ac`, không cộng/hiển thị ASO. Test hiện kiểm riêng cả CS lẫn TK. |
| Cây `frontend/` trùng | Đã cảnh báo rõ hơn | File `_KHONG_DUNG_LAM_ROOT_DIRECTORY.md` ghi rõ chênh lệch và cách xóa phần git-tracked sau khi được duyệt. Chưa xóa vì máy 24 còn dùng `.vercel/project.json`. |
| Đáp án 138 câu | Xong | Đã sinh lại lúc 09:28 ngày 03/09 trên 368.226 dòng bán hàng: 80 checker chạy đủ, 1 chạy một phần, 1 dùng kho local, 4 khóa đúng chủ đích, không có checker lỗi. Baseline: 63 `READY`, 2 `READY_CURRENT`, 62 `PARTIAL/DERIVED`, 11 `BLOCKED`. |
| Snapshot KPI/lương vs hóa đơn | Đã chạy lại | Khớp 1.960/1.973 dòng chung; khi loại `IsDuplicate=1` khớp 1.875/1.876 dòng chung trong ngưỡng 1%. |
| File Excel giao tester | Đã cập nhật | Ngày chốt 31/08/2026; C01/M01→`READY`, C41→S27, C45→S30; tổng hợp tự tính 62 câu cần chốt/thiếu một phần. |
| Kiểm thử tự động | Đạt | 434 test đạt, 1 test chủ động bỏ qua. Đã sửa ca test dùng cứng ngày 28 khiến sai khi tháng có 31 ngày. |
| Build giao diện production | Đạt | Next.js build thành công, TypeScript và 16 trang tĩnh hoàn tất. |

## Việc còn lại trước khi giao tester

| Ưu tiên | Việc | Người cần xử lý | Hạn / điều kiện |
|---:|---|---|---|
| 1 | Chọn ngân sách A (nạp thêm khoảng 60–80 USD) hoặc B (giảm hạn mức UAT) | MCNA + DNH | Trong tuần 1; chưa chốt thì không nên mở UAT rộng. |
| 2 | Chạy `scripts/kiem_tai_khoan_thieu_pham_vi.py` trên `auth.db` của máy 24 và sửa mọi tài khoản đã duyệt còn thiếu scope | Người vận hành máy 24 | Trước khi gửi tài khoản. Kho local hiện có 12 tài khoản QLV cũ không hợp lệ; đây chưa phải kết luận về production. |
| 3 | Gửi trang Nhóm A và lấy xác nhận bằng văn bản | DNH | Trước 10/09/2026. Riêng “tuần trong tháng” chưa sửa code cho tới khi có phản hồi hoặc tới hạn áp dụng giả định. |

## Gói gửi tester sau khi ba việc trên đạt

1. `outputs/uat_chatbot_dnh/uat_tracking_chatbot_dnh.xlsx`.
2. `docs/dap_an_bo_cau_hoi_dieu_hanh.md` và `docs/bao_cao_sql_doi_chung_138.md` qua kênh nội bộ.
3. `docs/doi_chieu_snapshot_vs_hoadon.md`.
4. Tài khoản đúng cây phân quyền; gửi mật khẩu bằng kênh riêng.
5. `docs/huong_dan_ban_giao_uat.md` và trang quyết định Nhóm A.

## Chưa làm trong hôm nay để tránh tốn tiền hoặc vượt quyền

- Chưa chạy thử chatbot 5 câu và chưa chạy vòng 138 câu qua API.
- Chưa thay đổi hạn mức câu hỏi vì cần quyết định ngân sách A/B.
- Chưa sửa định nghĩa tuần trong tháng vì hạn phản hồi là 10/09.
- Chưa sửa tài khoản production, deploy, gửi email hay gửi tài liệu ra ngoài.
- Chưa commit/push.

## Nợ kỹ thuật đã thấy nhưng không chặn build

- Lệnh lint toàn repo đang quét cả `.next/`, `_deprecated/`, cây `frontend/` cũ và các thư mục báo
  cáo, nên trả hàng nghìn lỗi/cảnh báo cũ. Build production vẫn đạt. Nên tách một việc riêng để thu
  hẹp phạm vi lint và xử lý lỗi thật trong `src/app`; không gộp vào đợt sửa prompt/UAT này.
