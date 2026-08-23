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

# 21/08/2026: bo sung sau khi ra soat thay nhanh chinh (_FUTURE_PERIOD_RE AND _SPECULATIVE_RE AND
# _BUSINESS_METRIC_RE, ca 3 CUNG LUC) co the bi lot neu cau hoi dien dat kheo, thieu dung 1 trong 3
# nhom tu khoa - vd "tinh hinh thang sau se the nao" (thieu chi so nghiep vu cu the), "kha nang dat
# duoc khong" (thieu moc thoi gian tuong lai ro rang vi ngu canh da ham y "sap toi" qua hoi thoai
# truoc do). Day la PHONG TUYEN CUNG BO SUNG (khong thay the nhanh cu, chi mo rong pham vi bat) -
# nhan dien dong tu/cum tu "suy dien tuong lai" DOC LAP, khong doi hoi phai co ca moc thoi gian
# TUONG MINH lan tu khoa nghiep vu cu the trong CUNG cau hoi.
_IMPLICIT_FUTURE_SPECULATION_RE = re.compile(
    r"\b(?:se (?:the nao|ra sao|nhu the nao|dat khong|tang|giam|len|xuong)|"
    r"sap toi (?:the nao|ra sao|se)|"
    r"kha nang (?:dat|hoan thanh|thanh cong)(?:\s+\w+){0,4}\s+khong\b|"
    r"xu huong (?:sap toi|thoi gian toi|tiep theo)|"
    r"neu tiep tuc (?:da tang|da giam|xu huong nay|nhu vay)|"
    r"co dat duoc khong|lieu co (?:dat|hoan thanh))\b"
)


def is_future_forecast_question(question: str) -> bool:
    """Chan cau hoi yeu cau suy dien tuong lai, nhung khong chan tra cuu ke hoach da nhap.

    Day la lop chan xac dinh truoc khi goi LLM. Prompt van co quy tac tuong tu de
    phong truong hop mot cau hoi vong vo khong duoc bo loc nhan dien.

    21/08/2026: THEM nhanh _IMPLICIT_FUTURE_SPECULATION_RE doc lap voi nhanh chinh (xem ghi chu
    tren dinh nghia bien) - giam rui ro cau hoi dien dat kheo lot qua ca 2 lop (regex + prompt).
    Van la phong tuyen tu khoa (khong the bat 100% cach dien dat), nhung mo rong dang ke pham vi
    so voi truoc, ma khong sua doi hanh vi cu (moi test cu van phai qua y nguyen).
    """
    text = _plain_text(question)
    if not text:
        return False

    explicit_forecast = bool(_EXPLICIT_FORECAST_RE.search(text))
    if explicit_forecast:
        return True

    # "Chi tieu/ke hoach thang sau la bao nhieu?" la tra cuu mot gia tri da nhap,
    # khong phai yeu cau chatbot tu suy dien ra mot gia tri moi. CHI thoat som neu KHONG co dau hieu
    # suy dien nao (ca nhanh _SPECULATIVE_RE cu LAN nhanh _IMPLICIT_FUTURE_SPECULATION_RE moi) -
    # "Lieu co dat chi tieu khong?" phai DI TIEP xuong nhanh implicit ben duoi, khong duoc thoat som
    # chi vi co tu "chi tieu" (21/08/2026, phat hien qua test_nhan_dien_cau_hoi_du_bao).
    if (_FACTUAL_PLAN_RE.search(text) and not _SPECULATIVE_RE.search(text)
            and not _IMPLICIT_FUTURE_SPECULATION_RE.search(text)):
        return False

    if (
        _FUTURE_PERIOD_RE.search(text)
        and _SPECULATIVE_RE.search(text)
        and _BUSINESS_METRIC_RE.search(text)
    ):
        return True

    # Nhanh bo sung: chi can dong tu/cum tu suy dien tuong lai DOC LAP + co nhac den 1 chi so
    # nghiep vu (khong bat buoc phai co moc thoi gian tuong minh trong CUNG cau - vd cau hoi tiep
    # theo trong hoi thoai da ham y dang noi ve tuong lai).
    if _IMPLICIT_FUTURE_SPECULATION_RE.search(text) and _BUSINESS_METRIC_RE.search(text):
        return True

    return False
