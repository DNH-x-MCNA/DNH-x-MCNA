# -*- coding: utf-8 -*-
"""
Long-term few-shot memory cho cau hoi AD-HOC (query_database) - thay the ban ChromaDB/embedding trong
spec goc bang SQLite + khop tu khoa don gian (khong can dependency nang, du dung cho quy mo hien tai).

LUU Y VE DO TIN CAY: chua co UI de nguoi dung xac nhan "cau tra loi nay dung" - tieu chi luu hien tai
la SQL chay THANH CONG (khong loi cu phap/logic SQL), KHONG dam bao ket qua dung ve nghiep vu. Day la
gioi han that, chi dung few-shot nay de goi y CACH VIET SQL (cau truc/join), khong coi la nguon "da
kiem chung" nhu 9 tool bao cao chuan.
"""
import os, sqlite3, time, re

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

_STOPWORDS = {"la", "gi", "cua", "cho", "va", "hay", "co", "khong", "toi", "ban", "nao", "the",
              "voi", "trong", "tren", "duoc", "nay", "do", "nhung", "mot", "theo", "de", "tu", "den"}


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    conn = _conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS qa_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        sql TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()


def _keywords(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9À-ỹ]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def save_example(question: str, sql: str):
    if not question or not sql:
        return
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO qa_examples (question, sql, created_at) VALUES (?,?,?)",
            (question.strip(), sql.strip(), time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        # Gioi han kich thuoc bang - chi giu 500 vi du gan nhat, tranh phinh vo han theo thoi gian.
        conn.execute("""DELETE FROM qa_examples WHERE id NOT IN (
            SELECT id FROM qa_examples ORDER BY id DESC LIMIT 500)""")
        conn.commit()
    finally:
        conn.close()


def retrieve_similar_examples(question: str, limit: int = 2) -> list:
    """So khop bang so tu khoa trung nhau (khong embedding) - tra ve top N cau hoi gan giong nhat kem SQL.
    Chi tra ve neu co it nhat 2 tu khoa trung, tranh goi y nham voi cau hoi khong lien quan."""
    q_kw = _keywords(question)
    if len(q_kw) < 2:
        return []
    conn = _conn()
    try:
        rows = conn.execute("SELECT question, sql FROM qa_examples ORDER BY id DESC LIMIT 500").fetchall()
    finally:
        conn.close()
    scored = []
    for q2, sql in rows:
        overlap = len(q_kw & _keywords(q2))
        if overlap >= 2:
            scored.append((overlap, q2, sql))
    scored.sort(key=lambda x: -x[0])
    return [{"question": q2, "sql": sql} for _, q2, sql in scored[:limit]]


init()
