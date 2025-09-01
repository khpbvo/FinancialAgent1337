from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final


LOG_DIR: Final = Path(os.getenv("FINAGENT_LOG_DIR", "./logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _build_handler(path: Path) -> RotatingFileHandler:
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3)
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] "
        "session=%(session_id)s user=%(user_id)s trace=%(trace_id)s "
        "%(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(fmt)
    return handler


def configure_logging(level: str = "INFO") -> None:
    level_val = getattr(logging, level.upper(), logging.INFO)
    logging.captureWarnings(True)

    main_log = _build_handler(LOG_DIR / "main.log")
    openai_log = _build_handler(LOG_DIR / "openai.log")
    tools_log = _build_handler(LOG_DIR / "tools.log")
    user_log = _build_handler(LOG_DIR / "user.log")

    # Root logger
    root = logging.getLogger()
    root.setLevel(level_val)
    root.addHandler(main_log)

    # Component loggers
    logging.getLogger("finagent.openai").setLevel(level_val)
    logging.getLogger("finagent.openai").addHandler(openai_log)

    logging.getLogger("finagent.tools").setLevel(level_val)
    logging.getLogger("finagent.tools").addHandler(tools_log)

    logging.getLogger("finagent.user").setLevel(level_val)
    logging.getLogger("finagent.user").addHandler(user_log)


class ContextFilter(logging.Filter):
    def __init__(self, session_id: str | None = None, user_id: str | None = None, trace_id: str | None = None) -> None:
        super().__init__()
        self.session_id = session_id or "-"
        self.user_id = user_id or "-"
        self.trace_id = trace_id or "-"

    def filter(self, record: logging.LogRecord) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        if not hasattr(record, "session_id"):
            record.session_id = self.session_id
        if not hasattr(record, "user_id"):
            record.user_id = self.user_id
        if not hasattr(record, "trace_id"):
            record.trace_id = self.trace_id
        return True


def attach_context(session_id: str | None, user_id: str | None, trace_id: str | None) -> None:
    f = ContextFilter(session_id=session_id, user_id=user_id, trace_id=trace_id)
    logging.getLogger().addFilter(f)
    logging.getLogger("finagent.openai").addFilter(f)
    logging.getLogger("finagent.tools").addFilter(f)
    logging.getLogger("finagent.user").addFilter(f)

