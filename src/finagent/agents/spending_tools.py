from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any


def _connect_domain_db() -> sqlite3.Connection:
    db = os.getenv("FINAGENT_DOMAIN_DB", "./data/finance.sqlite3")
    return sqlite3.connect(db)


try:
    from agents import function_tool, RunContextWrapper
except Exception:  # pragma: no cover - Agents SDK may be missing in some envs
    def function_tool(fn=None, **kwargs):  # type: ignore
        def wrap(f):
            return f

        return wrap if fn is None else wrap(fn)

    class RunContextWrapper:  # type: ignore
        def __init__(self, context: Any) -> None:
            self.context = context


@dataclass
class SpendByCategoryArgs:
    start_date: str
    end_date: str


@function_tool
def spend_by_category(start_date: str, end_date: str) -> str:
    """Sommeer uitgaven per categorie in een datumbereik (ISO: YYYY-MM-DD).

    Args:
        start_date: Inclusieve startdatum (ISO).
        end_date: Inclusieve einddatum (ISO).
    """
    con = _connect_domain_db()
    try:
        cur = con.execute(
            """
            SELECT COALESCE(c.code, 'UNCATEGORIZED') as cat,
                   SUM(CASE WHEN t.debit_credit='DEBIT' THEN t.amount_cents ELSE 0 END) as debit,
                   SUM(CASE WHEN t.debit_credit='CREDIT' THEN t.amount_cents ELSE 0 END) as credit
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.booking_date BETWEEN ? AND ?
            GROUP BY COALESCE(c.code, 'UNCATEGORIZED')
            ORDER BY debit DESC
            """,
            (start_date, end_date),
        )
        rows = cur.fetchall()
        lines = ["Categorie; Debet (EUR); Credit (EUR)"]
        for cat, debit_cents, credit_cents in rows:
            lines.append(
                f"{cat}; {debit_cents/100:.2f}; {credit_cents/100:.2f}"
            )
        return "\n".join(lines)
    finally:
        con.close()

