from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable

from .normalization import normalize_text


DEFAULT_CATEGORY_MAP: dict[str, str] = {
    # keyword (lowercase) -> category code
    "albert heijn": "GROCERIES",
    "jumbo": "GROCERIES",
    "lidle": "GROCERIES",
    "action": "HOUSEHOLD",
    "brabantwonen": "RENT",
    "huur": "RENT",
    "vgz": "HEALTH",
    "nn schadeverzekering": "INSURANCE",
    "verzekering": "INSURANCE",
    "ing creditcard": "CREDIT_CARD",
    "betaalpakket": "BANK_FEES",
    "rente": "INTEREST",
    "amazon": "SHOPPING",
    "washin7": "TRANSPORT",
}


@dataclass
class CategorizeStats:
    merchants_new: int = 0
    categories_new: int = 0
    tx_updated: int = 0


def _ensure_category(conn: sqlite3.Connection, code: str, label: str | None = None) -> int:
    cur = conn.execute("SELECT id FROM categories WHERE code=?", (code,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO categories(code, label) VALUES (?,?)",
        (code, label or code.title()),
    )
    return int(cur.lastrowid)


def _ensure_merchant(conn: sqlite3.Connection, name: str, normalized: str) -> int:
    cur = conn.execute("SELECT id FROM merchants WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO merchants(name, normalized) VALUES (?,?)",
        (name, normalized),
    )
    return int(cur.lastrowid)


def categorize_transactions(conn: sqlite3.Connection) -> CategorizeStats:
    stats = CategorizeStats()
    # Build category ids
    category_ids: dict[str, int] = {}
    for kw, code in DEFAULT_CATEGORY_MAP.items():
        if code not in category_ids:
            category_ids[code] = _ensure_category(conn, code)

    cur = conn.execute(
        "SELECT id, description, counterparty_name FROM transactions WHERE category_id IS NULL"
    )
    rows = cur.fetchall()
    for tx_id, desc, cp in rows:
        base = normalize_text((desc or "") + " " + (cp or "")).lower()
        chosen: str | None = None
        for kw, code in DEFAULT_CATEGORY_MAP.items():
            if kw in base:
                chosen = code
                break
        if not chosen:
            continue
        cat_id = category_ids[chosen]
        conn.execute("UPDATE transactions SET category_id=? WHERE id=?", (cat_id, tx_id))
        stats.tx_updated += 1
    conn.commit()
    return stats

