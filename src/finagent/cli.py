from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from .agents.orchestrator import build_agents
from .config.env import load_settings
from .config.logging import attach_context, configure_logging
from .config.tracing import trace_context
from .db.init_db import init_domain_db
from .tools.csv_ingest import ingest_csv_ing
from .tools.excel_ingest import ingest_xls
from .tools.pdf_ingest import ingest_pdf_generic


def run_once(session_id: str, user_id: str | None, input_text: str) -> None:
    try:
        from agents import Runner
        from agents.memory import SQLiteSession
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "OpenAI Agents SDK not available. Install 'openai-agents' to run agents."
        ) from e

    settings = load_settings()
    agents = build_agents()
    orchestrator = agents["orchestrator"]

    sess = SQLiteSession(session_id=session_id, db_path=settings.session_db)
    with trace_context(workflow_name="FinancialAgent Orchestrator", group_id=session_id):
        res = Runner.run_sync(orchestrator, input=input_text, session=sess)
        print(res.final_output)


async def repl(session_id: str, user_id: str | None) -> None:
    try:
        from openai.types.responses import ResponseTextDeltaEvent
        from agents import Runner
        from agents.memory import SQLiteSession
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "OpenAI Agents SDK not available. Install 'openai-agents' to run agents."
        ) from e

    settings = load_settings()
    agents = build_agents()
    orchestrator = agents["orchestrator"]

    sess = SQLiteSession(session_id=session_id, db_path=settings.session_db)
    print("Type 'exit' om te stoppen.")
    while True:
        user = input("U: ").strip()
        if not user or user.lower() in {"exit", "quit"}:
            break
        streamed = Runner.run_streamed(orchestrator, input=user, session=sess)
        print("A: ", end="", flush=True)
        async for event in streamed.stream_events():
            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                print(event.data.delta, end="", flush=True)
        print()


def ingest_documents(domain_db: str, documents_dir: str) -> None:
    init_domain_db(domain_db)
    conn = sqlite3.connect(domain_db)
    try:
        for path in sorted(Path(documents_dir).glob("*")):
            if path.suffix.lower() == ".csv":
                ingest_csv_ing(conn, path)
            elif path.suffix.lower() in {".xls", ".xlsx"}:
                ingest_xls(conn, path)
            elif path.suffix.lower() == ".pdf":
                ingest_pdf_generic(conn, path)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    parser = argparse.ArgumentParser(prog="finagent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run a single turn")
    p_run.add_argument("--session", required=True)
    p_run.add_argument("--user", required=False)
    p_run.add_argument("--input", required=True)

    p_repl = sub.add_parser("repl", help="Interactive streaming REPL")
    p_repl.add_argument("--session", required=True)
    p_repl.add_argument("--user", required=False)

    p_ingest = sub.add_parser("ingest", help="Ingest documents from folder")
    p_ingest.add_argument("--dir", default=settings.documents_dir)

    p_cat = sub.add_parser("categorize", help="Auto-categorize uncategorized transactions")

    p_spend = sub.add_parser("spend-by-category", help="Report spend by category over a period")
    p_spend.add_argument("--start", required=True)
    p_spend.add_argument("--end", required=True)

    args = parser.parse_args()
    attach_context(session_id=getattr(args, "session", None), user_id=getattr(args, "user", None), trace_id=None)

    if args.cmd == "run":
        run_once(args.session, args.user, args.input)
    elif args.cmd == "repl":
        asyncio.run(repl(args.session, args.user))
    elif args.cmd == "ingest":
        ingest_documents(settings.domain_db, args.dir)
    elif args.cmd == "categorize":
        import sqlite3
        from .tools.categorizer import categorize_transactions

        stats = categorize_transactions(sqlite3.connect(settings.domain_db))
        print(f"Updated transactions: {stats.tx_updated}")
    elif args.cmd == "spend-by-category":
        # run the function tool directly for convenience
        from .agents.spending_tools import spend_by_category

        print(spend_by_category(args.start, args.end))
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
