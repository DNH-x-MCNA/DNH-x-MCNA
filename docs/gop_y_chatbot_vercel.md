# Góp ý chatbot Vercel (DNH-x-MCNA) — 6 điểm ưu tiên

> **TRẠNG THÁI (cập nhật 22/07/2026): ĐÃ XỬ LÝ XONG CẢ 6 ĐIỂM.** Giữ file này làm hồ sơ rà soát
> — nội dung mô tả bên dưới là **hiện trạng TẠI THỜI ĐIỂM RÀ SOÁT**, không còn đúng với code hiện
> tại. Đối chiếu nhanh:
>
> | Điểm | Đã xử lý | Ghi chú |
> |---|---|---|
> | 1. Phân quyền chưa enforce | ✅ | `scope_area_code`/`scope_employee_code`/`scope_channel` ép ở tầng code trong `report_templates.py`, không phụ thuộc AI |
> | 2. Snapshot cũ nhưng vô hình | ✅ | `sync_freshness_note()` cảnh báo khi tiến trình đồng bộ treo (khác với chỉ xem ngày dữ liệu) |
> | 3. Nguồn sync `vHoaDonTotal`/`vHoaDonETCTotal` | ✅ | Đã xác nhận đúng nguồn (không phải `vHoaDon` thô) |
> | 4. `_customer_receivable` nuốt mọi lỗi | ✅ 22/07 | Thêm `receivable_status` (`ok`/`no_data`/`error`) — phân biệt "không nợ" với "không tra được" |
> | 5. `revenue_by_region` chỉ ghi log khi lệch | ✅ 22/07 | Thêm kênh cảnh báo qua `contextvars` → cảnh báo lên tận câu trả lời (vá cả chỗ `nl2sql.py` làm rơi mất cảnh báo) |
> | 6. Không rate-limit/quota | ✅ 22/07 | `CHAT_RATE_LIMIT_PER_MIN` (mặc định 10 câu/phút/user) + trần vòng tool `MAX_TOOL_ROUNDS=8` đã có sẵn |

Kiến trúc tổng thể tốt: tool báo cáo đã kiểm chứng thay vì để LLM tự chế SQL, prompt cache 1h
tiết kiệm token, đọc snapshot SQLite nên nhanh + không đè tải Bravo, `auth.py` hash mật khẩu
PBKDF2 + session chuẩn. 6 điểm nên ưu tiên xử lý:

**🔴 1. Phân quyền chưa enforce** (`backend/main.py:141-142`). `role`/`scope_value` đã lưu trong
auth.db nhưng không truyền vào `ask()` → mọi user đăng nhập đều xem được dữ liệu toàn quốc. Cần
truyền `user["scope_value"]` vào `ask()` rồi ép filter `area_code` trong template tool + raw-SQL.
(Map thẳng yêu cầu họp: mỗi QLV chỉ tự kiểm tra vùng mình.)

**🔴 2. Snapshot cũ nhưng vô hình.** Sync 15-30'/lần; nếu sync treo/đổ một phần, chatbot vẫn trả
lời tự tin bằng dữ liệu cũ/thiếu, không báo. Cần 1 bảng watermark ghi mốc sync + hiển thị "dữ liệu
tính đến HH:MM" trong mỗi câu trả lời, cảnh báo nếu quá cũ.

**🔴 3. Bảo đảm nguồn sync = `vHoaDonTotal`/`vHoaDonETCTotal`** (không phải `vHoaDon` thô — lệch
~4%). Tool đang quảng cáo "khớp 100% Bravo" nên phải chắc chắn nguồn đúng + fail-loud nếu đổi nhầm.

**🟠 4. `report_templates.py:327` `_customer_receivable` nuốt mọi lỗi** (`except: pass`). Supabase
sập → trả "không nợ", lẫn với khách thật sự không nợ. Cần tách "không có dữ liệu" khỏi "lỗi tra cứu".

**🟠 5. `report_templates.py:126` `revenue_by_region` tự-đối-chiếu nhưng chỉ ghi log.** Tổng theo
vùng lệch tổng thô vẫn trả breakdown sai cho user. Nên thêm cờ để câu trả lời cảnh báo.

**🟠 6. Không có rate-limit/quota token.** 1 user spam câu nhiều-tool (tối đa 8 vòng LLM) không bị
chặn → rủi ro chi phí. Nên giới hạn số câu/phút/user + trần vòng tool.

Các điểm nhỏ hơn (KPI không target thành đỏ giả, lọc is_duplicate ẩn NV thật, khe SELECT...INTO,
câu nhiều-tool chỉ hiện bảng cuối) để xử lý sau.
