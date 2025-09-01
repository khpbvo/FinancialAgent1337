from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .normalization import parse_eu_amount_to_cents, normalize_description, TxnHashInput, compute_txn_hash


@dataclass
class IngestStats:
    docs_new: int = 0
    tx_seen: int = 0
    tx_new: int = 0


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


_DATE_RE = re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")
_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}[A-Z]{4}\d{10})\b")
_AMOUNT_RE = re.compile(r"([-+]?\d{1,3}(?:\.\d{3})*,\d{2})")


def _extract_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _guess_account_iban(text: str) -> str | None:
    m = _IBAN_RE.search(text)
    return m.group(1) if m else None


def _iter_tx_candidates(lines: list[str]) -> Iterable[tuple[str, str, str]]:
    """Yield (date, description, amount_str) triples heuristically from lines."""
    for i, ln in enumerate(lines):
        d = _DATE_RE.search(ln)
        a = _AMOUNT_RE.search(ln)
        if d and a:
            date = d.group(1)
            amt = a.group(1)
            # description: remove date/amount from line; if empty, look at neighbor lines
            desc = ln
            desc = _DATE_RE.sub("", desc)
            desc = _AMOUNT_RE.sub("", desc)
            desc = desc.strip() or (lines[i + 1] if i + 1 < len(lines) else "")
            yield date, desc, amt


def ingest_pdf_generic(conn: sqlite3.Connection, pdf_path: Path) -> IngestStats:
    stats = IngestStats()
    sha = _sha256_file(pdf_path)
    cur = conn.execute("SELECT id FROM documents WHERE sha256=?", (sha,))
    row = cur.fetchone()
    if row:
        doc_id = int(row[0])
    else:
        cur = conn.execute(
            "INSERT INTO documents(path, sha256, source_type, bank_hint) VALUES (?,?,?,?)",
            (str(pdf_path), sha, "pdf", None),
        )
        stats.docs_new += 1
        doc_id = int(cur.lastrowid)
    try:
        try:
            import pdfplumber  # type: ignore

            texts: list[str] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    # Prefer tables when available
                    try:
                        tables = page.extract_tables() or []
                    except Exception:
                        tables = []
                    if tables:
                        for tbl in tables:
                            for row in tbl:
                                texts.append(" ".join(c or "" for c in row))
                    else:
                        texts.append(page.extract_text() or "")
            full_text = "\n".join(texts)
            lines = _extract_lines(full_text)

            account_iban = _guess_account_iban(full_text)
            if account_iban:
                acc = conn.execute(
                    "INSERT OR IGNORE INTO accounts(institution, iban, account_no) VALUES (?,?,?)",
                    ("ING", account_iban, None),
                )
                # fetch id
                cur2 = conn.execute(
                    "SELECT id FROM accounts WHERE institution=? AND iban IS ? AND account_no IS ?",
                    ("ING", account_iban, None),
                )
                account_id = int(cur2.fetchone()[0])
            else:
                # Unknown account bucket
                cur2 = conn.execute(
                    "INSERT OR IGNORE INTO accounts(institution, iban, account_no) VALUES (?,?,?)",
                    ("ING", None, "UNKNOWN_PDF"),
                )
                cur3 = conn.execute(
                    "SELECT id FROM accounts WHERE institution=? AND iban IS ? AND account_no IS ?",
                    ("ING", None, "UNKNOWN_PDF"),
                )
                account_id = int(cur3.fetchone()[0])

            for date_str, desc_raw, amt_str in _iter_tx_candidates(lines):
                stats.tx_seen += 1
                try:
                    # dd-mm-YYYY to ISO
                    d = datetime.strptime(date_str, "%d-%m-%Y").date()
                    booking_iso = d.isoformat()
                    debit_credit_hint = "Af" if "-" in amt_str.strip() else "Bij"
                    amount_cents = parse_eu_amount_to_cents(amt_str.replace("-", ""), debit_credit_hint)
                    description = desc_raw
                    norm_desc = normalize_description(description)
                    txn_hash = compute_txn_hash(
                        TxnHashInput(
                            account_id=account_id,
                            booking_date=booking_iso,
                            value_date=None,
                            amount_cents=amount_cents,
                            currency="EUR",
                            debit_credit=("DEBIT" if debit_credit_hint.lower() == "af" else "CREDIT"),
                            counterparty_iban_or_name="",
                            normalized_description=norm_desc,
                        )
                    )
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO transactions(
                            account_id, document_id, txn_hash, booking_date, value_date,
                            amount_cents, currency, debit_credit, description
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            account_id,
                            doc_id,
                            txn_hash,
                            booking_iso,
                            None,
                            amount_cents,
                            "EUR",
                            ("DEBIT" if debit_credit_hint.lower() == "af" else "CREDIT"),
                            description,
                        ),
                    )
                    if int(conn.execute("SELECT changes()").fetchone()[0]) > 0:
                        stats.tx_new += 1
                except Exception as e:  # noqa: BLE001
                    conn.execute(
                        "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
                        (doc_id, "parse", 0, f"pdf row error: {type(e).__name__}: {e}"),
                    )

            conn.execute(
                "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
                (doc_id, "parse", 1, f"pdf parsed: seen={stats.tx_seen}, new={stats.tx_new}"),
            )
        except ModuleNotFoundError:
            conn.execute(
                "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
                (
                    doc_id,
                    "parse",
                    0,
                    "pdfplumber not installed; cannot parse PDF.",
                ),
            )
    except Exception as e:  # noqa: BLE001
        conn.execute(
            "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
            (doc_id, "parse", 0, f"pdf error: {type(e).__name__}: {e}"),
        )
    conn.commit()
    return stats
