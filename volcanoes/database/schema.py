"""
=========================================================
Volcanes — The Real Volcanoes
EduTrader AI

Module: Database Schema
Purpose: Create and maintain the initial SQLite database
         structure used by the Volcanes trading engine.

Author: Eduardo Yuseff
=========================================================
"""

from pathlib import Path

from volcanoes.database.connection import database_session


SCHEMA = """
CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    component TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL UNIQUE,
    entry_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    description TEXT NOT NULL,
    symbol TEXT,
    quantity INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_regimes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    regime TEXT NOT NULL,
    confidence REAL,
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scanner_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    universe_size INTEGER NOT NULL DEFAULT 0,
    qualified_count INTEGER NOT NULL DEFAULT 0,
    execution_mode TEXT NOT NULL DEFAULT 'PREVIEW',
    status TEXT NOT NULL DEFAULT 'STARTED'
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanner_run_id INTEGER,
    symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    score REAL NOT NULL,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    explanation TEXT,
    status TEXT NOT NULL DEFAULT 'DISCOVERED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (scanner_run_id)
        REFERENCES scanner_runs(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL,
    exit_price REAL,
    stop_price REAL,
    target_price REAL,
    status TEXT NOT NULL DEFAULT 'DISCOVERED',
    opened_at TEXT,
    closed_at TEXT,
    realized_pnl REAL,
    explanation TEXT,

    FOREIGN KEY (candidate_id)
        REFERENCES candidates(id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    broker TEXT NOT NULL,
    broker_order_id TEXT,
    order_type TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    limit_price REAL,
    stop_price REAL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    filled_at TEXT,

    FOREIGN KEY (trade_id)
        REFERENCES trades(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    quantity INTEGER NOT NULL,
    average_price TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    starting_cash TEXT NOT NULL,
    cash TEXT NOT NULL,
    equity TEXT NOT NULL,
    buying_power TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trading_date TEXT NOT NULL UNIQUE,
    starting_equity REAL,
    ending_equity REAL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    trades_opened INTEGER NOT NULL DEFAULT 0,
    trades_closed INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    maximum_drawdown REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    market_regime TEXT,
    total_trades INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    win_rate REAL,
    net_pnl REAL NOT NULL DEFAULT 0,
    average_return REAL,
    score REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (strategy_name, market_regime)
);

CREATE INDEX IF NOT EXISTS idx_candidates_symbol
    ON candidates(symbol);

CREATE INDEX IF NOT EXISTS idx_candidates_status
    ON candidates(status);

CREATE INDEX IF NOT EXISTS idx_trades_symbol
    ON trades(symbol);

CREATE INDEX IF NOT EXISTS idx_trades_status
    ON trades(status);

CREATE INDEX IF NOT EXISTS idx_orders_trade_id
    ON orders(trade_id);

CREATE INDEX IF NOT EXISTS idx_system_events_component
    ON system_events(component);

CREATE INDEX IF NOT EXISTS idx_system_events_created_at
    ON system_events(created_at);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_created_at
    ON ledger_entries(created_at);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_symbol
    ON ledger_entries(symbol);
"""


def initialize_database(
    database_path: Path | None = None,
) -> None:
    """Create all Volcanes database tables and indexes."""

    with database_session(database_path) as connection:
        connection.executescript(SCHEMA)


if __name__ == "__main__":
    initialize_database()
    print("Volcanes database initialized successfully.")
