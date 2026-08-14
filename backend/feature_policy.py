# -*- coding: utf-8 -*-
"""Chinh sach tinh nang co tinh quyet dinh, khong phu thuoc vao AI.

Tu 14/08/2026, moi tinh nang du bao tuong lai bi khoa de uu tien doi chieu va
do dung cua du lieu da phat sinh. Khong cung cap bien moi truong de bat lai vo
tinh; viec mo lai can mot thay doi code duoc review va bo kiem thu rieng.
"""
from __future__ import annotations

import re
import unicodedata


DISABLED_FUTURE_TOOL_NAMES = frozenset({
    "get_revenue_forecast",
    "get_kpi_forecast",
    "get_kpi_forecast_model1",
})

FUTURE_FORECAST_DISABLED_MESSAGE = (
    "Tính năng dự báo tương lai đã được tắt để ưu tiên tuyệt đối độ đúng của dữ liệu. "
    "Tôi chỉ trả lời số thực tế đã phát sinh hoặc dữ liệu kế hoạch/chỉ tiêu đã được nhập. "
    "Bạn có thể hỏi doanh thu lũy kế đến một ngày, so sánh các kỳ lịch sử, KPI thực đạt so với "
    "chỉ tiêu, hoặc thời điểm dữ liệu được cập nhật gần nhất."
)


def disabled_future_result() -> dict:
    """Ket qua chuan cho moi duong goi truc tiep vao tinh nang da khoa."""
    return {
        "error": FUTURE_FORECAST_DISABLED_MESSAGE,
        "feature_disabled": True,
        "policy": "actual_and_historical_data_only",
    }


def _plain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", (value or "").lower())
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", without_accents.replace("đ", "d")).strip()


_EXPLICIT_FORECAST_RE = re.compile(
    r"\b(?:du bao|forecast|du phong|tien doan|ngoai suy|predict(?:ion|ive)?)\b"
)
_FUTURE_PERIOD_RE = re.compile(
    r"\b(?:cuoi thang|thang (?:sau|toi|ke tiep)|quy (?:sau|toi|ke tiep)|"
    r"nam (?:sau|toi|ke tiep)|tuong lai)\b"
)
_SPECULATIVE_RE = re.compile(
    r"\b(?:uoc tinh|du kien|se dat|se la|se bao nhieu|kha nang dat|con bao nhieu ngay|"
    r"bao gio (?:het|can))\b"
)
_BUSINESS_METRIC_RE = re.compile(
    r"\b(?:doanh thu|doanh so|kpi|chi tieu|cong no|ton kho|kho|mat hang|hang hoa|san pham|khach hang)\b"
)
_FACTUAL_PLAN_RE = re.compile(r"\b(?:target|chi tieu|ke hoach|ngan sach)\b")


def is_future_forecast_question(question: str) -> bool:
    """Chan cau hoi yeu cau suy dien tuong lai, nhung khong chan tra cuu ke hoach da nhap.

    Day la lop chan xac dinh truoc khi goi LLM. Prompt van co quy tac tuong tu de
    phong truong hop mot cau hoi vong vo khong duoc bo loc nhan dien.
    """
    text = _plain_text(question)
    if not text:
        return False

    explicit_forecast = bool(_EXPLICIT_FORECAST_RE.search(text))
    if explicit_forecast:
        return True

    # "Chi tieu/ke hoach thang sau la bao nhieu?" la tra cuu mot gia tri da nhap,
    # khong phai yeu cau chatbot tu suy dien ra mot gia tri moi.
    if _FACTUAL_PLAN_RE.search(text) and not _SPECULATIVE_RE.search(text):
        return False

    return bool(
        _FUTURE_PERIOD_RE.search(text)
        and _SPECULATIVE_RE.search(text)
        and _BUSINESS_METRIC_RE.search(text)
    )
