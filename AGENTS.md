# FinancialAgent – Architecture & Code Quality (NL)

FinancialAgent helpt Nederlandstalige gebruikers met schuldenadvies, investeringsadvies en uitgavenanalyse door bankdocumenten (CSV/XLS/PDF) te verwerken en specialist‑agents aan te sturen.

## Kernfunctionaliteit
- Documentverwerking: CSV, Excel (XLS) en PDF‑afschriften inlezen.
- Transactie‑analyse: normaliseren, categoriseren, trends en budgetadvies.
- Schuldenadvies: betalingsregelingen, prioritering en aflossingsplan.
- Investeringsadvies: risicoprofiel, strategie en portefeuillebeheer.

Deze handleiding beschrijft hoe we de FinancialAgent opzetten, welke kwaliteitsrichtlijnen we hanteren (linting/typing/formattering), hoe we MCP + WebSearchTool gebruiken, hoe sessie- en domeingegevens worden opgeslagen, hoe we documenten inlezen (CSV/Excel/PDF), en hoe we logging & tracing standaard inschakelen.

## Doel
- Financiële assistent in het Nederlands: schuldhulp, investeringen, budget/spend-analyse.
- Orkestratie via een triage-agent die doorverwijst naar specialisten. De orchestrator zelf geeft geen inhoudelijke antwoorden: specialisten geven het eindantwoord.

## Overzicht Architectuur
- Model: standaard `gpt-5` (configureerbaar via env). 
- Orchestrator (router) met handoffs naar specialisten:
  - DebtExpert: schulden, betalingsregelingen, prioritering, aflossingsplan.
  - InvestmentExpert: beleggingsstrategie, risicoprofiel, portefeuille.
  - SpendingAnalysisExpert: inkomen/uitgaven, trends, categorieën, budget advies.
  - FSAgent: bestandsinteracties (MCP filesystem) binnen de repository-root.
- Tools:
  - `WebSearchTool` altijd ingeschakeld op orchestrator en specialisten.
  - MCP filesystem server met single root op de repository-root en alle tools die de server aanbiedt (geen filter).
- Geheugen en data:
  - Twee SQLite-databases: één voor sessiegeheugen (conversatie) en één voor domeindata (transacties, documenten, merchants, categorieën, etc.).
  - Tracing standaard aan; uitgebreide logging met rotatie.

## Omgevingsvariabelen (.env)
Laad een `.env` (bijv. met `python-dotenv`), met minimaal:
- `OPENAI_API_KEY`
- `FINAGENT_MODEL` (default `gpt-5`)
- `FINAGENT_DOCUMENTS_DIR` (default `./documents`)
- `FINAGENT_DATA_DIR` (default `./data`)
- `FINAGENT_SESSION_DB` (default `./data/agent_memory.sqlite3`)
- `FINAGENT_DOMAIN_DB` (default `./data/finance.sqlite3`)
- `FINAGENT_TRACING=1`
- `FINAGENT_LOG_LEVEL=INFO`

## Agents – Instructies en routing
- Orchestrator (NL instructies – voorbeeld):
  - "Je coördineert de juiste specialist voor de vraag van de gebruiker. Je geeft nooit zelf inhoudelijke antwoorden. Je kiest exact één handoff: DebtExpert, InvestmentExpert of SpendingAnalysisExpert. Gebruik WebSearch en MCP-tools wanneer nodig."
- Handoff-beschrijvingen (NL):
  - DebtExpert: "Schulden, betalingsregelingen, aflossingsplan, prioritering van schuldeisers."
  - InvestmentExpert: "Beleggingsstrategie, risicoprofiel, portefeuillebeheer en rebalancing."
  - SpendingAnalysisExpert: "Inkomen/uitgaven, categorieën, trends, budgetadvies op basis van transacties."
  - FSAgent: "Lees/schrijf bestanden in de repository-root via MCP filesystem."
- Routingregels:
  - Orchestrator beslist uitsluitend over handoff en antwoordt niet zelf.
  - Data-gedreven vragen (over transacties/uitgaven): eerst naar SpendingAnalysisExpert.
  - Schulden en betalingsregelingen: DebtExpert. Beleggingsvragen: InvestmentExpert.
  - Tools zijn altijd beschikbaar (WebSearch, MCP) voor de specialisten.

## Voorbeeld: MCP filesystem + WebTool + Orchestrator
```python
import os
from agents import Agent, Runner, WebSearchTool
from agents.mcp import MCPServerStdio

REPO_ROOT = os.getenv("FINAGENT_REPO_ROOT", ".")

# MCP server met single root naar repository-root en alle tools zichtbaar
fs_server = MCPServerStdio(
    params={
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", REPO_ROOT],
    },
    cache_tools_list=True,
)

debt_expert = Agent(
    name="DebtExpert",
    instructions=(
        "Je helpt met schulden, betalingsregelingen, prioritering en aflossing."
    ),
    tools=[WebSearchTool()],
    mcp_servers=[fs_server],
)

investment_expert = Agent(
    name="InvestmentExpert",
    instructions=(
        "Je adviseert over beleggingsstrategie, risicoprofiel en portefeuille."
    ),
    tools=[WebSearchTool()],
    mcp_servers=[fs_server],
)

spending_expert = Agent(
    name="SpendingAnalysisExpert",
    instructions=(
        "Je analyseert transacties, herkent categorieën en geeft budgetadvies."
    ),
    tools=[WebSearchTool()],
    mcp_servers=[fs_server],
)

orchestrator = Agent(
    name="FinancialOrchestrator",
    instructions=(
        "Je routeert naar de juiste specialist en geeft zelf nooit inhoudelijke antwoorden."
    ),
    handoffs=[debt_expert, investment_expert, spending_expert],
    tools=[WebSearchTool()],
    mcp_servers=[fs_server],
    model=os.getenv("FINAGENT_MODEL", "gpt-5"),
)
```

## Sessies & geheugen (conversatie)
Gebruik de Agents SDK `SQLiteSession` in een eigen database.
```python
from agents.memory import SQLiteSession
import os

session = SQLiteSession(
    session_id="default",
    db_path=os.getenv("FINAGENT_SESSION_DB", "./data/agent_memory.sqlite3"),
)

result = Runner.run_sync(orchestrator, input="…", session=session)
print(result.final_output)
```

## Domeindata: database schema (sqlite)
We gebruiken een tweede SQLite-database voor domeintabellen. Startpunt (aanpasbaar, met indices):
```sql
-- Gebruikers & sessies
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  external_id TEXT UNIQUE,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON UPDATE CASCADE ON DELETE SET NULL,
  started_at TEXT DEFAULT CURRENT_TIMESTAMP,
  ended_at TEXT
);

-- Documenten & parsing
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  sha256 TEXT UNIQUE NOT NULL,
  source_type TEXT,        -- pdf/csv/xls
  bank_hint TEXT,          -- ING/Rabobank/ABN/AMEX/etc.
  imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);

CREATE TABLE IF NOT EXISTS parse_events (
  id INTEGER PRIMARY KEY,
  document_id INTEGER REFERENCES documents(id) ON UPDATE CASCADE ON DELETE CASCADE,
  stage TEXT,              -- ingest/parse/normalize
  ok INTEGER NOT NULL,
  message TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Domein: rekeningen, transacties, merchants, categorieën
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  institution TEXT,
  iban TEXT,
  account_no TEXT,
  currency TEXT DEFAULT 'EUR',
  UNIQUE(institution, iban, account_no)
);

CREATE TABLE IF NOT EXISTS merchants (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE,
  normalized TEXT,
  category_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_merchants_normalized ON merchants(normalized);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE,        -- GROCERIES, RENT, UTILITIES
  label TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  account_id INTEGER REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE SET NULL,
  document_id INTEGER REFERENCES documents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  txn_hash TEXT UNIQUE,    -- idempotency hash
  booking_date TEXT,
  value_date TEXT,
  amount_cents INTEGER NOT NULL,
  currency TEXT DEFAULT 'EUR',
  debit_credit TEXT CHECK(debit_credit IN ('DEBIT','CREDIT')),
  counterparty_name TEXT,
  counterparty_iban TEXT,
  description TEXT,
  merchant_id INTEGER,
  category_id INTEGER,
  balance_after_cents INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tx_account_booking ON transactions(account_id, booking_date);

-- Observability
CREATE TABLE IF NOT EXISTS run_summaries (
  id INTEGER PRIMARY KEY,
  started_at TEXT,
  finished_at TEXT,
  documents_seen INTEGER,
  documents_new INTEGER,
  tx_seen INTEGER,
  tx_new INTEGER,
  warnings INTEGER,
  notes TEXT
);

-- Eenvoudige migratietabel
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Ingestie (CSV, Excel, PDF)
We ondersteunen CSV (ING), Excel (`.xls`), en PDF bankafschriften.

### CSV (ING) mapping (afgeleid uit voorbeeldbestand)
- `booking_date`: kolom "Datum" (formaat `YYYYMMDD`).
- `value_date`: uit "Mededelingen" via patroon `Valutadatum: DD-MM-YYYY` (indien aanwezig), anders `NULL`.
- `amount_cents`: parseer EU-getal uit "Bedrag (EUR)"; teken via "Af/Bij" (`Af` → negatief/`DEBIT`, `Bij` → positief/`CREDIT`).
- `currency`: "EUR".
- `description`: teksten uit "Mededelingen"; fallback "Naam / Omschrijving".
- `counterparty_name`: uit `Naam: ...` in mededelingen; anders "Naam / Omschrijving".
- `counterparty_iban`: uit kolom "Tegenrekening" of uit `IBAN: ...` in mededelingen.
- `account`: kolom "Rekening" (koppeling naar `accounts`).
- Extra hints: `Code`, `Mutatiesoort` voor merchant/categorie-herkenning.

### Excel (`.xls`)
- Zelfde mapping als CSV. Detecteer headers (case-insensitief), EU-locale parsing.

### PDF
- Gebruik `pdfplumber` voor tekstextractie. Herken datum, valutadatum, bedrag, omschrijving, rekening/IBAN via regex-heuristiek. Lukt structurele extractie niet, sla op als ongestructureerd en log `parse_events.ok=0` met een duidelijke `message`.

## Normalisatie & idempotency
- `txn_hash`: SHA-256 over de canonieke tuple:
  - `account_id`, `booking_date` (ISO), `value_date` (indien beschikbaar), `amount_cents`, `currency`, `debit_credit`, `counterparty_iban|counterparty_name`, `normalized_description`.
- Canonicalisatie:
  - Trim, uppercase- of casefold-normalisatie waar zinvol, Unicode NFKD, whitespace collapsen.
  - EU-bedrag → integer cents.
  - Verwijder vluchtige tokens: timestamps ("Datum/Tijd:"), pasvolgnr, terminal-ID’s, “Apple Pay”, transactie-ID’s die per betaling uniek zijn maar niet inhoudelijk.
  - Behoud stabiele referenties: `Kenmerk: ...`, incassant- en machtiging-ID’s, IBAN, polisnummers.
- Merchant-normalisatie:
  - Strip locatie-suffixen ("NLD", plaatsnamen), verwijder terminal/pas/periodeteksten en volgnummerrommel.
  - Bewaar originele `name`, sla `normalized` op; koppel `category_id` indien bekend.

## Tracing & logging
- Tracing: standaard aan. Gebruik per run een `workflow_name` zoals "FinancialAgent Orchestrator" en groepeer op `session_id`.
- Logging-bestanden (rotatie 5 MB, max 3 backups):
  - `logs/main.log`: algemene app-flow.
  - `logs/openai.log`: model/tool-interacties met OpenAI.
  - `logs/tools.log`: lokale tools/MCP-calls (bestanden/parsers).
  - `logs/user.log`: inkomende prompts/gebruikersacties.
- Log velden: `timestamp`, `level`, `session_id`, `user_id`, `trace_id`, `agent`, `event`.

## Codekwaliteit – Linters, types, formatting
- Linters: `ruff` (lint + import sort), `pylint`.
- Types: `pyright --strict` (strikt overal).
- Formatter: `black` (bijv. line-length 88) + `ruff` isort-regels.
- Aanbevolen `pyproject.toml` (kern):
```toml
[tool.black]
line-length = 88
target-version = ["py311"]

[tool.ruff]
line-length = 88
select = ["E","F","I","PL","UP","B","C4"]
ignore = []

[tool.pylint.MASTER]
disable = ["C0114","C0115","C0116"]

[tool.pyright]
typeCheckingMode = "strict"
reportMissingTypeStubs = true
reportUnknownMemberType = true
pythonVersion = "3.11"
```
- Pre-commit (fragment):
```yaml
repos:
- repo: https://github.com/psf/black
  rev: 24.8.0
  hooks:
  - id: black
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.6.8
  hooks:
  - id: ruff
  - id: ruff-format
- repo: https://github.com/pre-commit/mirrors-pylint
  rev: v3.2.6
  hooks:
  - id: pylint
- repo: https://github.com/RobertCraigie/pyright-python
  rev: v1.1.377
  hooks:
  - id: pyright
```
- CI: voer `ruff`, `black --check`, `pylint`, `pyright`, en unit-tests uit. Build faalt bij fouten.

## CLI en gebruik
- Aanbevolen entrypoint: `python -m finagent run --session default --user u1 --input "…"` dat `Runner.run_sync(orchestrator, ..., session=SQLiteSession(...))` aanroept.
- Orchestrator antwoordt nooit inhoudelijk; specialisten leveren het eindresultaat. WebSearchTool is altijd beschikbaar; MCP filesystem-tools zijn beschikbaar onder de repo-root.

## Interactieve REPL + streaming
Werkt direct vanuit een Python REPL met token‑voor‑token streaming. Uitgaand van de hierboven gedefinieerde `orchestrator`:
```python
import os
import asyncio
from agents import Runner
from agents.memory import SQLiteSession
from openai.types.responses import ResponseTextDeltaEvent

async def repl():
    session = SQLiteSession(
        "repl",
        os.getenv("FINAGENT_SESSION_DB", "./data/agent_memory.sqlite3"),
    )
    print("Type 'exit' om te stoppen.")
    while True:
        user = input("U: ").strip()
        if not user or user.lower() in {"exit", "quit"}:
            break
        streamed = Runner.run_streamed(orchestrator, input=user, session=session)
        print("A: ", end="", flush=True)
        async for event in streamed.stream_events():
            # Stream LLM tekst-token updates
            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                print(event.data.delta, end="", flush=True)
        print()  # newline na het antwoord

if __name__ == "__main__":
    asyncio.run(repl())
```

## Veiligheid & grenzen
- Geen bestandsgrenzen binnen de projectstructuur: de MCP filesystem-server wijst naar de repository-root. Gebruik dit bewust; schrijf path-validaties in tools als later nodig.

## Volgende stappen
- Implementatie parsers: CSV/Excel direct, PDF via `pdfplumber` (eerste versie mag heuristisch zijn). Verbeter OCR/structuur later indien nodig.
- Merchant- en categorie-heuristiek uitbreiden met patterns + handmatige overrides.
- Metrieken toevoegen aan `run_summaries` (bijv. `parse_errors`, `tool_calls_total`, `web_search_calls`, `mcp_calls`).
