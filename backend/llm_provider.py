# -*- coding: utf-8 -*-
"""
Nguồn sự thật DUY NHẤT cho câu hỏi "lượt gọi này dùng nhà cung cấp nào, key nào".

17/08/2026: thêm khi bắt đầu thử DeepSeek song song với Claude. Trong cùng một ngày có thể có
nhiều nhà cung cấp (và nhiều key của cùng một nhà cung cấp) cùng chạy, nên báo cáo chi phí gộp
chung một cục là vô dụng — không biết tiền của bên nào, cũng không so được bên nào rẻ hơn.

Đặt riêng một module vì nl2sql.py (tạo client) và cost_logger.py (ghi sổ) đều cần biết, mà
cost_logger KHÔNG import được nl2sql (nl2sql đã import cost_logger, sẽ thành vòng tròn). Viết
ở hai nơi thì sớm muộn cũng lệch nhau — và lệch ở đây nghĩa là ghi sai tiền cho sai nhà cung cấp.
"""
import hashlib
import os


def resolve_api_key() -> str:
    """Key thực sự dùng để gọi. LLM_API_KEY thắng để đổi nhà cung cấp mà không phải xoá key cũ."""
    return (os.environ.get("LLM_API_KEY", "").strip()
            or os.environ.get("ANTHROPIC_API_KEY", "").strip())


def base_url() -> str:
    return os.environ.get("LLM_BASE_URL", "").strip()


def provider_name(model: str = "") -> str:
    """Tên nhà cung cấp để hiển thị. Suy từ endpoint trước, vì đó mới là nơi tiền thực sự chảy tới;
    tên model chỉ là phương án dự phòng khi chạy mặc định (không đặt LLM_BASE_URL)."""
    url = base_url().lower()
    if url:
        if "deepseek" in url:
            return "DeepSeek"
        if "anthropic.com" in url:
            return "Anthropic"
        # Endpoint lạ: lấy tên miền làm nhãn, còn hơn gán bừa cho một nhà cung cấp có sẵn
        mien = url.split("//")[-1].split("/")[0]
        return mien or "Khac"
    m = (model or "").lower()
    if m.startswith("claude"):
        return "Anthropic"
    if m.startswith("deepseek"):
        return "DeepSeek"
    return "Khong ro"


def key_fingerprint(key: str = None) -> str:
    """Nhãn ngắn để PHÂN BIỆT các key, không phải để khôi phục key.

    Ghi 4 ký tự cuối (quy ước quen thuộc như 4 số cuối thẻ) kèm 4 ký tự băm — chỉ 4 ký tự cuối
    thôi thì hai key khác nhau vẫn có thể trùng đuôi, mà đó đúng là tình huống cần phân biệt.
    TUYỆT ĐỐI không ghi key đầy đủ vào log: cost_log.jsonl không được xem là nơi chứa bí mật,
    nó được đọc bởi dashboard và tải về được.
    """
    k = key if key is not None else resolve_api_key()
    if not k:
        return "chua-cau-hinh"
    bam = hashlib.sha256(k.encode("utf-8")).hexdigest()[:4]
    return f"...{k[-4:]}#{bam}"


def current_info(model: str = "") -> dict:
    """Gói sẵn cho cost_logger ghi kèm mỗi lượt gọi."""
    return {"provider": provider_name(model), "api_key_id": key_fingerprint()}
