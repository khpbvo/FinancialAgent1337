from __future__ import annotations

import csv
import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .normalization import (
    compute_txn_hash,
    normalize_description,
    normalize_text,
    parse_eu_amount_to_cents,
    try_extract_value_date,
    TxnHashInput,
)


HEADERS_EXPECTED: Final = [
    "Datum",
    "Naam / Omschrijving",
    "Rekening",
    "Tegenrekening",
    "Code",
    "Af Bij",
    "Bedrag (EUR)",
    "Mutatiesoort",
    "Mededelingen",
]


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


def _ensure_account(conn: sqlite3.Connection, iban: str | None, account_no: str | None) -> int:
    cur = conn.execute(
        "SELECT id FROM accounts WHERE institution=? AND iban IS ? AND account_no IS ?",
        ("ING", iban, account_no),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO accounts(institution, iban, account_no) VALUES (?,?,?)",
        ("ING", iban, account_no),
    )
    return int(cur.lastrowid)


def ingest_csv_ing(conn: sqlite3.Connection, csv_path: Path) -> IngestStats:
    stats = IngestStats()
    sha = _sha256_file(csv_path)
    cur = conn.execute("SELECT id FROM documents WHERE sha256=?", (sha,))
    row = cur.fetchone()
    if row:
        doc_id = int(row[0])
        conn.execute(
            "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
            (doc_id, "ingest", 1, "Already imported; reprocessing parse only"),
        )
    else:
        cur = conn.execute(
            "INSERT INTO documents(path, sha256, source_type, bank_hint) VALUES (?,?,?,?)",
            (str(csv_path), sha, "csv", "ING"),
        )
        stats.docs_new += 1
        doc_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
            (doc_id, "ingest", 1, "New document imported"),
        )

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        # Proceed best-effort if headers differ
        for row in reader:
            stats.tx_seen += 1
            try:
                booking_date = row.get("Datum", "").strip()
                # ING uses YYYYMMDD
                if len(booking_date) == 8 and booking_date.isdigit():
                    booking_iso = f"{booking_date[0:4]}-{booking_date[4:6]}-{booking_date[6:8]}"
                else:
                    booking_iso = booking_date
                description = row.get("Mededelingen", "").strip() or row.get("Naam / Omschrijving", "").strip()
                value_date = try_extract_value_date(description) or None
                debit_credit = row.get("Af Bij", "").strip()
                amount_cents = parse_eu_amount_to_cents(row.get("Bedrag (EUR)", "0"), debit_credit)
                currency = "EUR"
                counterparty_iban = (row.get("Tegenrekening", "") or "").strip() or None
                counterparty_name = row.get("Naam / Omschrijving", "").strip() or None
                account_str = row.get("Rekening", "").strip()
                account_id = _ensure_account(conn, iban=account_str, account_no=None)
                norm_desc = normalize_description(description)
                cp_ref = counterparty_iban or (counterparty_name or "")
                txn_hash = compute_txn_hash(
                    TxnHashInput(
                        account_id=account_id,
                        booking_date=booking_iso,
                        value_date=value_date,
                        amount_cents=amount_cents,
                        currency=currency,
                        debit_credit=("DEBIT" if debit_credit.lower() == "af" else "CREDIT"),
                        counterparty_iban_or_name=cp_ref,
                        normalized_description=norm_desc,
                    )
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO transactions(
                        account_id, document_id, txn_hash, booking_date, value_date,
                        amount_cents, currency, debit_credit, counterparty_name,
                        counterparty_iban, description
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        account_id,
                        doc_id,
                        txn_hash,
                        booking_iso,
                        value_date,
                        amount_cents,
                        currency,
                        ("DEBIT" if debit_credit.lower() == "af" else "CREDIT"),
                        counterparty_name,
                        counterparty_iban,
                        description,
                    ),
                )
                cur2 = conn.execute("SELECT changes()")
                if int(cur2.fetchone()[0]) > 0:
                    stats.tx_new += 1
            except Exception as e:  # noqa: BLE001
                conn.execute(
                    "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
                    (doc_id, "parse", 0, f"row error: {type(e).__name__}: {e}"),
                )

    conn.execute(
        "INSERT INTO parse_events(document_id, stage, ok, message) VALUES (?,?,?,?)",
        (doc_id, "parse", 1, f"parsed rows: seen={stats.tx_seen}, new={stats.tx_new}"),
    )
    conn.commit()
    return stats

