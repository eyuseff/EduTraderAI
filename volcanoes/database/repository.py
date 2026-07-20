"""SQLite repository for Volcanes — The Real Volcanoes."""

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from volcanoes.config import config
from volcanoes.database.connection import database_session
from volcanoes.database.models import (
    Candidate,
    SystemEvent,
    Trade,
    TradeStatus,
)
from volcanoes.domain import LedgerEntry, LedgerEntryType


class SQLiteRepository:
    """Persist and retrieve Volcanes domain objects using SQLite."""

    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or config.database_path

    def save_candidate(self, candidate: Candidate) -> int:
        """Insert a candidate and return its database ID."""

        query = """
        INSERT INTO candidates (
            scanner_run_id,
            symbol,
            strategy_name,
            score,
            entry_price,
            stop_price,
            target_price,
            explanation,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            candidate.scanner_run_id,
            candidate.symbol,
            candidate.strategy_name,
            candidate.score,
            candidate.entry_price,
            candidate.stop_price,
            candidate.target_price,
            candidate.explanation,
            candidate.status.value,
            candidate.created_at.isoformat(),
        )

        with database_session(self.database_path) as connection:
            cursor = connection.execute(query, values)
            candidate.id = cursor.lastrowid

        if candidate.id is None:
            raise RuntimeError("Candidate could not be saved.")

        return candidate.id

    def get_candidate(self, candidate_id: int) -> Candidate | None:
        """Return a candidate by ID, or None when it does not exist."""

        query = """
        SELECT *
        FROM candidates
        WHERE id = ?
        """

        with database_session(self.database_path) as connection:
            row = connection.execute(query, (candidate_id,)).fetchone()

        if row is None:
            return None

        return Candidate(
            id=row["id"],
            scanner_run_id=row["scanner_run_id"],
            symbol=row["symbol"],
            strategy_name=row["strategy_name"],
            score=row["score"],
            entry_price=row["entry_price"],
            stop_price=row["stop_price"],
            target_price=row["target_price"],
            explanation=row["explanation"],
            status=TradeStatus(row["status"]),
        )

    def save_trade(self, trade: Trade) -> int:
        """Insert a trade and return its database ID."""

        query = """
        INSERT INTO trades (
            candidate_id,
            symbol,
            strategy_name,
            side,
            quantity,
            entry_price,
            exit_price,
            stop_price,
            target_price,
            status,
            opened_at,
            closed_at,
            realized_pnl,
            explanation
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            trade.candidate_id,
            trade.symbol,
            trade.strategy_name,
            trade.side.value,
            trade.quantity,
            trade.entry_price,
            trade.exit_price,
            trade.stop_price,
            trade.target_price,
            trade.status.value,
            trade.opened_at.isoformat() if trade.opened_at else None,
            trade.closed_at.isoformat() if trade.closed_at else None,
            trade.realized_pnl,
            trade.explanation,
        )

        with database_session(self.database_path) as connection:
            cursor = connection.execute(query, values)
            trade.id = cursor.lastrowid

        if trade.id is None:
            raise RuntimeError("Trade could not be saved.")

        return trade.id

    def update_trade_status(
        self,
        trade_id: int,
        status: TradeStatus,
    ) -> None:
        """Update the lifecycle status of a trade."""

        query = """
        UPDATE trades
        SET status = ?
        WHERE id = ?
        """

        with database_session(self.database_path) as connection:
            cursor = connection.execute(
                query,
                (status.value, trade_id),
            )

            if cursor.rowcount == 0:
                raise LookupError(f"Trade {trade_id} was not found.")

    def record_system_event(self, event: SystemEvent) -> int:
        """Persist an auditable system event."""

        query = """
        INSERT INTO system_events (
            event_type,
            component,
            severity,
            message,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """

        values = (
            event.event_type,
            event.component,
            event.severity,
            event.message,
            json.dumps(event.metadata),
            event.created_at.isoformat(),
        )

        with database_session(self.database_path) as connection:
            cursor = connection.execute(query, values)
            event.id = cursor.lastrowid

        if event.id is None:
            raise RuntimeError("System event could not be saved.")

        return event.id

    def save_ledger_entry(self, entry: LedgerEntry) -> int:
        """Persist an immutable ledger entry."""

        if not isinstance(entry, LedgerEntry):
            raise TypeError("entry must be a LedgerEntry instance.")

        query = """
        INSERT INTO ledger_entries (
            entry_id,
            entry_type,
            amount,
            description,
            symbol,
            quantity,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            entry.id,
            entry.entry_type.value,
            str(entry.amount),
            entry.description,
            entry.symbol,
            entry.quantity,
            entry.created_at.isoformat(),
        )

        with database_session(self.database_path) as connection:
            cursor = connection.execute(query, values)
            database_id = cursor.lastrowid

        if database_id is None:
            raise RuntimeError("Ledger entry could not be saved.")

        return int(database_id)

    def get_ledger_entries(self) -> list[LedgerEntry]:
        """Return all ledger entries in chronological order."""

        query = """
        SELECT
            entry_id,
            entry_type,
            amount,
            description,
            symbol,
            quantity,
            created_at
        FROM ledger_entries
        ORDER BY created_at ASC, id ASC
        """

        with database_session(self.database_path) as connection:
            rows = connection.execute(query).fetchall()

        return [
            LedgerEntry(
                id=row["entry_id"],
                entry_type=LedgerEntryType(row["entry_type"]),
                amount=Decimal(row["amount"]),
                description=row["description"],
                symbol=row["symbol"],
                quantity=row["quantity"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def count_rows(self, table_name: str) -> int:
        """Return the number of rows in an approved table."""

        allowed_tables = {
            "candidates",
            "trades",
            "orders",
            "positions",
            "system_events",
            "ledger_entries",
        }

        if table_name not in allowed_tables:
            raise ValueError(f"Unsupported table: {table_name}")

        query = f"SELECT COUNT(*) AS total FROM {table_name}"

        with database_session(self.database_path) as connection:
            row: sqlite3.Row = connection.execute(query).fetchone()

        return int(row["total"])
