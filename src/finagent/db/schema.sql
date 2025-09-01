-- Users & sessions
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

-- Documents & parsing
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  sha256 TEXT UNIQUE NOT NULL,
  source_type TEXT,
  bank_hint TEXT,
  imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);

CREATE TABLE IF NOT EXISTS parse_events (
  id INTEGER PRIMARY KEY,
  document_id INTEGER REFERENCES documents(id) ON UPDATE CASCADE ON DELETE CASCADE,
  stage TEXT,
  ok INTEGER NOT NULL,
  message TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Accounts, merchants, categories, transactions
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
  code TEXT UNIQUE,
  label TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  account_id INTEGER REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE SET NULL,
  document_id INTEGER REFERENCES documents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  txn_hash TEXT UNIQUE,
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

-- Migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

