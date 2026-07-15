# _deprecated — Mã nguồn không còn dùng cho bản Go-Live

Theo **DNH Go-Live Plan (Phase 5)**, quyết định đã chốt với DNH:

> Chatbot chỉ chạy trên **web UI**, KHÔNG làm Teams Bot hỏi-đáp nữa.
> Teams chỉ nhận **alert real-time** qua Incoming Webhook (xem `src/notifier.py::send_teams_alert`).

Các file dưới đây được đưa vào đây (thay vì xóa hẳn) để giữ lịch sử, có thể khôi phục nếu cần:

| File | Lý do deprecate |
|---|---|
| `teams_bot.py` | Bot hỏi-đáp Microsoft Teams (Bot Framework). Không còn dùng — Teams chỉ nhận alert webhook, không hội thoại. |
| `manifest.json` | Manifest đăng ký Teams App cho bot hỏi-đáp trên. |
| `nextjs_chat_skeleton/` | Bản frontend Next.js thử nghiệm song song. Đã chốt dùng `frontend/` (vanilla JS) làm bản go-live chính thức (Phase 5.4). |

Đồng thời đã gỡ khỏi `backend/main.py`: import `botbuilder`, `src.teams_bot`, và route `POST /api/messages`;
và gỡ `botbuilder-core` / `botbuilder-schema` khỏi `backend/requirements.txt`.
