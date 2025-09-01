from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final


SCHEMA_SQL_PATH: Final[Path] = Path(__file__).with_name("schema.sql")


def init_domain_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        with SCHEMA_SQL_PATH.open("r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()

