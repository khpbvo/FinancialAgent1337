from __future__ import annotations

import os
from dataclasses import dataclass


def _maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        # dotenv is optional; proceed silently if unavailable
        pass


_maybe_load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    model: str
    documents_dir: str
    data_dir: str
    session_db: str
    domain_db: str
    tracing_enabled: bool
    log_level: str
    repo_root: str


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("FINAGENT_MODEL", "gpt-5"),
        documents_dir=os.getenv("FINAGENT_DOCUMENTS_DIR", "./documents"),
        data_dir=os.getenv("FINAGENT_DATA_DIR", "./data"),
        session_db=os.getenv("FINAGENT_SESSION_DB", "./data/agent_memory.sqlite3"),
        domain_db=os.getenv("FINAGENT_DOMAIN_DB", "./data/finance.sqlite3"),
        tracing_enabled=os.getenv("FINAGENT_TRACING", "1") not in {"0", "false", "False"},
        log_level=os.getenv("FINAGENT_LOG_LEVEL", "INFO"),
        repo_root=os.getenv("FINAGENT_REPO_ROOT", "."),
    )

