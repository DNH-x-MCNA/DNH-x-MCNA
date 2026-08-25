# -*- coding: utf-8 -*-
"""
Business glossary - luu dinh nghia thuat ngu nghiep vu do nguoi dung giai thich trong hoi thoai
(vd "doanh thu rong nghia la doanh thu tru chiet khau"), de lan sau hoi lai co the ap dung dung
nghia ma khong can giai thich lai tu dau.

Luu trong memory.db (cung file voi lich su hoi thoai) - bang rieng, khong lien quan du lieu kinh doanh.
"""
import os, sqlite3, time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    conn = _conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS business_glossary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term TEXT NOT NULL,
        definition TEXT NOT NULL,
        defined_by TEXT,
        defined_at TEXT NOT NULL,
        is_global INTEGER NOT NULL DEFAULT 0
    )""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(business_glossary)")}
    if "is_global" not in columns:
        conn.execute(
            "ALTER TABLE business_glossary ADD COLUMN is_global INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()
    conn.close()


def save_glossary_term(term: str, definition: str, defined_by: str = None,
                       is_global: bool = False):
    term = (term or "").strip()
    if not term or not definition:
        return
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO business_glossary "
            "(term, definition, defined_by, defined_at, is_global) VALUES (?,?,?,?,?)",
            (term, definition.strip(), defined_by, time.strftime("%Y-%m-%d %H:%M:%S"),
             1 if is_global else 0),
        )
        conn.commit()
    finally:
        conn.close()


def retrieve_relevant_glossary(question: str, limit: int = 3,
                               username: str = None) -> list:
    """Khop tu khoa don gian: tra ve dinh nghia ma 'term' xuat hien (khong phan biet hoa/thuong) trong
    cau hoi hien tai. Neu 1 term duoc dinh nghia nhieu lan, lay ban ghi MOI NHAT."""
    if not question:
        return []
    q = question.lower()
    conn = _conn()
    try:
        if username:
            rows = conn.execute(
                "SELECT term, definition FROM business_glossary "
                "WHERE defined_by=? OR is_global=1 "
                "ORDER BY CASE WHEN defined_by=? THEN 0 ELSE 1 END, defined_at DESC, id DESC",
                (username, username),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT term, definition FROM business_glossary WHERE is_global=1 "
                "ORDER BY defined_at DESC, id DESC"
            ).fetchall()
    finally:
        conn.close()
    seen_terms = set()
    matched = []
    for term, definition in rows:
        tl = term.lower()
        if tl in seen_terms:
            continue  # da co ban ghi moi hon cho term nay roi
        if tl in q:
            seen_terms.add(tl)
            matched.append(f'"{term}" = {definition}')
        if len(matched) >= limit:
            break
    return matched


init()
