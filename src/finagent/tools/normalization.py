from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any


_VALUTADATUM_RE = re.compile(r"Valutadatum:\s*(\d{2}-\d{2}-\d{4})")


def parse_eu_amount_to_cents(amount_str: str, debit_credit: str) -> int:
    s = amount_str.strip().replace(".", "").replace("\u00a0", " ")
    s = s.replace(" ", "")
    # decimal comma
    if "," in s:
        s = s.replace(",", ".")
    val = float(s)
    cents = int(round(val * 100))
    if debit_credit.strip().lower() == "af":
        return -abs(cents)
    return abs(cents)


def try_extract_value_date(text: str) -> str | None:
    m = _VALUTADATUM_RE.search(text)
    if not m:
        return None
    d = datetime.strptime(m.group(1), "%d-%m-%Y").date()
    return d.isoformat()


def normalize_text(value: str) -> str:
    v = value.strip()
    v = unicodedata.normalize("NFKD", v)
    v = re.sub(r"\s+", " ", v)
    return v


def normalize_description(desc: str) -> str:
    v = normalize_text(desc)
    # Remove volatile tokens: timestamps, pasvolgnr, terminal ids, Apple Pay markers
    patterns = [
        r"Datum/Tijd:\s*\d{2}-\d{2}-\d{4}\s*\d{2}:\d{2}:\d{2}",
        r"Pasvolgnr:\s*\d+",
        r"Term:\s*\S+",
        r"Apple Pay",
        r"Transactie:\s*\S+",
    ]
    for p in patterns:
        v = re.sub(p, "", v, flags=re.IGNORECASE)
    v = re.sub(r"\s+", " ", v).strip()
    return v


@dataclass(frozen=True)
class TxnHashInput:
    account_id: int
    booking_date: str
    value_date: str | None
    amount_cents: int
    currency: str
    debit_credit: str
    counterparty_iban_or_name: str
    normalized_description: str


def compute_txn_hash(inp: TxnHashInput) -> str:
    parts: list[str] = [
        str(inp.account_id),
        inp.booking_date,
        inp.value_date or "",
        str(inp.amount_cents),
        inp.currency.upper(),
        inp.debit_credit.upper(),
        normalize_text(inp.counterparty_iban_or_name).upper(),
        inp.normalized_description.upper(),
    ]
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

