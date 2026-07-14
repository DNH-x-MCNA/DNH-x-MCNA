# -*- coding: utf-8 -*-
"""Nguồn chuẩn duy nhất cho mapping vùng miền (mã AreaCode Bravo <-> tên tiếng Việt).

Tách riêng khỏi ai_agent/chatbot.py (14/07/2026) — trước đó src/etl.py, src/alerts.py,
src/notifier.py đều import DNHChatbot._REGION_SQL_MARKERS/_REGION_NAMES_VI thẳng từ file chatbot,
khiến service báo cáo/cảnh báo (chạy nền trên máy 24, không liên quan gì tới chatbot) phụ thuộc
runtime vào 1 file vốn thuộc phần chatbot — nếu file đó bị xoá/thay thế (vd giao hẳn phần chatbot
cho người khác) thì service vỡ ngay vì mất nguồn mapping vùng miền này. ai_agent/chatbot.py giờ
import ngược lại từ đây để giữ nguyên hành vi nội bộ của nó.
"""

REGION_SQL_MARKERS = {"bac": ["MB", "MB2"], "nam": ["MN"], "trung": ["MT"]}  # mã miền, không quote — quote khi dùng
REGION_NAMES_VI = {"bac": "Miền Bắc", "nam": "Miền Nam", "trung": "Miền Trung"}
