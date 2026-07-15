# -*- coding: utf-8 -*-
"""
Cong cu (Claude tool) tinh ngay thang THUC (khong de LLM tu suy luan - model de sai lech quy/thang VN,
vd nham quy duong lich voi quy tai chinh, hoac tinh sai "tuan nay" theo chuan ISO vs chuan VN).

CHI xu ly ngay thang bang Python thuan (datetime/rule-based) - Claude CHI quyet dinh KHI NAO can goi
tool nay (vd cau hoi co tu "quy truoc", "thang nay"...), KHONG tu tinh toan ket qua ngay thang.
"""
import datetime as dt
import re

GET_CURRENT_DATETIME_TOOL = {
    "name": "get_current_datetime",
    "description": "Tra ve ngay gio HIEN TAI cua he thong (khong phai ngay du lieu moi nhat trong kho - "
                    "xem note rieng cho cai do), kem quy/nam tai chinh. Goi khi can biet 'hom nay' la ngay nao "
                    "de tinh cac moc thoi gian khac.",
    "input_schema": {"type": "object", "properties": {}},
}

RESOLVE_RELATIVE_DATE_TOOL = {
    "name": "resolve_relative_date",
    "description": "Chuyen 1 cum tu thoi gian tuong doi tieng Viet (vd 'hom nay', 'tuan nay', 'thang truoc', "
                    "'quy nay', 'quy truoc', 'cung ky nam ngoai', '6 thang gan nhat', 'nam nay', 'nam ngoai') "
                    "thanh khoang ngay cu the {start_date, end_date} dang YYYY-MM-DD. BAT BUOC dung tool nay "
                    "cho MOI cum tu thoi gian tuong doi trong cau hoi - KHONG tu tinh ngay thang bang suy luan "
                    "rieng, de tranh sai lech quy/thang.",
    "input_schema": {
        "type": "object",
        "properties": {"phrase": {"type": "string", "description": "Cum tu thoi gian tuong doi, vd 'quy truoc'"}},
        "required": ["phrase"],
    },
}

REALTIME_TOOLS = [GET_CURRENT_DATETIME_TOOL, RESOLVE_RELATIVE_DATE_TOOL]
REALTIME_TOOL_NAMES = {"get_current_datetime", "resolve_relative_date"}


def _quarter(d: dt.date) -> int:
    return (d.month - 1) // 3 + 1


def _quarter_range(year: int, q: int):
    start_month = (q - 1) * 3 + 1
    start = dt.date(year, start_month, 1)
    end_month = start_month + 2
    end = (dt.date(year, end_month, 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return start, end


def get_current_datetime() -> dict:
    now = dt.datetime.now()
    d = now.date()
    return {
        "today": d.isoformat(),
        "weekday": ["Thu Hai", "Thu Ba", "Thu Tu", "Thu Nam", "Thu Sau", "Thu Bay", "Chu Nhat"][d.weekday()],
        "quarter": _quarter(d),
        "fiscal_year": d.year,  # DNH dung nam tai chinh trung nam duong lich
    }


def _month_range(year: int, month: int):
    start = dt.date(year, month, 1)
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return start, end


def resolve_relative_date(phrase: str) -> dict:
    """Rule-based, KHONG goi LLM. Tra ve {start_date, end_date, matched} hoac {error} neu khong nhan dien duoc."""
    if not phrase:
        return {"error": "Cum tu rong"}
    p = phrase.strip().lower()
    today = dt.date.today()

    def r(start, end, matched):
        return {"start_date": start.isoformat(), "end_date": end.isoformat(), "matched": matched}

    if p in ("hom nay", "hôm nay", "ngay hom nay", "ngày hôm nay"):
        return r(today, today, "hom nay")

    if p in ("hom qua", "hôm qua"):
        y = today - dt.timedelta(days=1)
        return r(y, y, "hom qua")

    if p in ("tuan nay", "tuần này"):
        start = today - dt.timedelta(days=today.weekday())
        return r(start, today, "tuan nay (Thu Hai den hom nay)")

    if p in ("tuan truoc", "tuần trước"):
        this_monday = today - dt.timedelta(days=today.weekday())
        start = this_monday - dt.timedelta(days=7)
        end = this_monday - dt.timedelta(days=1)
        return r(start, end, "tuan truoc")

    if p in ("thang nay", "tháng này"):
        start, _ = _month_range(today.year, today.month)
        return r(start, today, "thang nay (dau thang den hom nay)")

    if p in ("thang truoc", "tháng trước"):
        y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        start, end = _month_range(y, m)
        return r(start, end, "thang truoc")

    if p in ("quy nay", "quý này"):
        q = _quarter(today)
        start, _ = _quarter_range(today.year, q)
        return r(start, today, f"quy {q}/{today.year} (dau quy den hom nay)")

    if p in ("quy truoc", "quý trước"):
        q = _quarter(today)
        y, qp = (today.year - 1, 4) if q == 1 else (today.year, q - 1)
        start, end = _quarter_range(y, qp)
        return r(start, end, f"quy {qp}/{y}")

    if p in ("nam nay", "năm nay"):
        return r(dt.date(today.year, 1, 1), today, f"nam {today.year} (01/01 den hom nay)")

    if p in ("nam ngoai", "năm ngoái", "nam truoc", "năm trước"):
        y = today.year - 1
        return r(dt.date(y, 1, 1), dt.date(y, 12, 31), f"nam {y}")

    if p in ("cung ky nam ngoai", "cùng kỳ năm ngoái", "cung ky nam truoc", "cùng kỳ năm trước"):
        try:
            same_day_last_year = today.replace(year=today.year - 1)
        except ValueError:  # 29/2
            same_day_last_year = today.replace(year=today.year - 1, day=28)
        return r(dt.date(today.year - 1, 1, 1), same_day_last_year,
                  f"01/01/{today.year - 1} den {same_day_last_year.isoformat()} (cung ky voi tu dau nam den hom nay)")

    m = re.match(r"^(\d+)\s*(thang|tháng)\s*(gan nhat|gần nhất)$", p)
    if m:
        n = int(m.group(1))
        start = (today.replace(day=1) - dt.timedelta(days=1))
        for _ in range(n - 1):
            start = (start.replace(day=1) - dt.timedelta(days=1))
        start = start.replace(day=1)
        return r(start, today, f"{n} thang gan nhat (tu {start.isoformat()} den hom nay)")

    m = re.match(r"^(\d+)\s*(ngay|ngày)\s*(gan nhat|gần nhất)$", p)
    if m:
        n = int(m.group(1))
        start = today - dt.timedelta(days=n - 1)
        return r(start, today, f"{n} ngay gan nhat")

    return {"error": f"Khong nhan dien duoc cum tu '{phrase}' - hay hoi lai nguoi dung ngay/khoang ngay cu the."}
