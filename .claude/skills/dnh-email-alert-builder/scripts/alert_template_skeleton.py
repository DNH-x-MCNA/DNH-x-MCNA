"""
Khung khởi điểm cho một alert job mới của DNH.
Không chứa business logic của 4 trigger cụ thể (xem references/alert_triggers.md).
Đảm bảo mọi alert job mới đi theo cấu trúc: fetch (read-only) -> evaluate -> log -> send.
"""

import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dnh_alert")


def fetch_source_data(config: dict) -> list[dict]:
    """
    Đọc dữ liệu READ-ONLY từ DB trung gian (không truy vấn trực tiếp
    Bravo/DMS, không ghi ngược nguồn nào cả).
    TODO: implement query cụ thể cho từng trigger.
    """
    raise NotImplementedError("Điền query read-only cho trigger cụ thể")


def evaluate_trigger(rows: list[dict], config: dict) -> list[dict]:
    """
    Áp dụng điều kiện trigger (ngưỡng, baseline...) đọc từ config,
    KHÔNG hardcode giá trị chưa được client xác nhận (vd: revenue drop
    baseline, debt aging date basis) — xem dnh-onsite-prep skill.
    """
    raise NotImplementedError("Điền logic đánh giá điều kiện trigger")


def render_email(triggered_rows: list[dict], template_path: str) -> str:
    """Tách riêng template khỏi logic tính toán để dễ chỉnh sửa nội dung."""
    raise NotImplementedError("Điền render template email")


def send_email(subject: str, body: str, recipients: list[str]) -> None:
    """Gửi email và LUÔN log lại kết quả để phục vụ audit."""
    logger.info(
        "Sending alert email | recipients=%s | time=%s",
        recipients,
        datetime.utcnow().isoformat(),
    )
    # TODO: tích hợp SMTP / dịch vụ gửi email thật của DNH/MCNA
    raise NotImplementedError("Điền tích hợp gửi email thật")


def run_alert_job(config: dict) -> None:
    rows = fetch_source_data(config)
    triggered = evaluate_trigger(rows, config)
    if not triggered:
        logger.info("Không có bản ghi nào trigger alert lần này.")
        return
    body = render_email(triggered, config["template_path"])
    send_email(config["subject"], body, config["recipients"])
    logger.info("Alert job hoàn tất | số bản ghi trigger=%d", len(triggered))


if __name__ == "__main__":
    # TODO: load config thật (không hardcode threshold ở đây)
    raise NotImplementedError("Điền config loader cho job cụ thể")
