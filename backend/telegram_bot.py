# -*- coding: utf-8 -*-
"""
Telegram Bot cho AI Chatbot DNH - noi tin nhan Telegram voi cung logic NL2SQL (nl2sql.ask()).
Chay doc lap: py telegram_bot.py  (long-polling, khong can webhook/domain cong khai)
Bien moi truong can: TELEGRAM_BOT_TOKEN (xem .env.example)

LUU Y VE FORMAT: Telegram KHONG render bang markdown (| a | b |) thanh bang that - no chi hien
nguyen ky tu | va - nhin roi. Nen o day tu chuyen bang markdown cua AI thanh khoi monospace (<pre>)
can le cot, va **bold**/### header thanh <b> - gui bang parse_mode="HTML".
"""
import os, re, logging, traceback

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
load_env()

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from nl2sql import ask

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_bot")

MAX_MSG_LEN = 3500  # Telegram gioi han 4096 ky tu/tin nhan, chua bien do an toan cho tag HTML


# ==================== FORMAT MARKDOWN -> TELEGRAM HTML ====================
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_separator_row(line: str) -> bool:
    s = line.strip()
    return bool(s) and "-" in s and set(s) <= set("|-: ")


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return "|" in s and not _is_separator_row(s)


def _split_row(line: str):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace("**", "") for c in s.split("|")]


def _render_table(table_lines):
    rows = [_split_row(l) for l in table_lines]
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    widths = [max(len(r[c]) for r in rows) for c in range(ncols)]
    out_lines = [" | ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows]
    return "<pre>" + "\n".join(out_lines) + "</pre>"


def _format_line(line: str) -> str:
    m = re.match(r"^(#{1,6})\s*(.+)$", line)
    if m:
        return f"<b>{m.group(2).strip()}</b>"
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)


def format_for_telegram(text: str) -> str:
    """Chuyen bang markdown thanh khoi <pre> can le cot, **bold**/#header thanh <b>."""
    text = _esc(text)
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if _is_table_row(lines[i]) and i + 1 < len(lines) and _is_separator_row(lines[i + 1]):
            j = i + 2
            table_lines = [lines[i]]
            while j < len(lines) and _is_table_row(lines[j]):
                table_lines.append(lines[j]); j += 1
            out.append(_render_table(table_lines))
            i = j
            continue
        out.append(_format_line(lines[i]))
        i += 1
    return "\n".join(out)


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def _chunk_html(html: str, max_len: int = MAX_MSG_LEN):
    """Cat thanh nhieu tin nhan, giu nguyen ven tung khoi <pre>...</pre> (khong cat giua the)."""
    blocks = []
    for part in re.split(r"(<pre>.*?</pre>)", html, flags=re.DOTALL):
        if part.startswith("<pre>"):
            blocks.append(part)
        else:
            blocks.extend(part.split("\n"))
    chunks, cur = [], ""
    for b in blocks:
        add = b if not cur else "\n" + b
        if cur and len(cur) + len(add) > max_len:
            chunks.append(cur); cur = b
        else:
            cur += add
    if cur:
        chunks.append(cur)
    return chunks


# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Xin chào! Tôi là AI Analyst của Dược Nam Hà.\n"
        "Hỏi tôi về doanh thu, công nợ, KPI nhân viên, tồn kho, vùng miền...\n\n"
        "Ví dụ: \"Doanh thu hôm nay bao nhiêu?\", \"Top 10 sản phẩm bán chạy?\""
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    chat_id = update.effective_chat.id
    log.info(f"[chat {chat_id}] Cau hoi: {question}")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        result = ask(question, session_id=f"telegram_{chat_id}")
        raw_answer = result["answer"] or "Xin lỗi, tôi không tìm được câu trả lời phù hợp."
        answer_html = format_for_telegram(raw_answer)
    except Exception as e:
        log.error(f"Loi xu ly cau hoi: {traceback.format_exc()}")
        answer_html = _esc(f"Xin lỗi, có lỗi hệ thống: {str(e)[:200]}")

    for chunk in _chunk_html(answer_html):
        try:
            await update.message.reply_text(chunk, parse_mode="HTML")
        except Exception:
            log.warning("Gui HTML that bai, fallback ve plain text")
            await update.message.reply_text(_strip_html(chunk))


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("Telegram bot dang chay (long-polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
