"""Startup-safe schema validation for SQLite execution persistence foundation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from volcanoes.application.execution.enums import PaperExecutionMode
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.contracts import (
    ExecutionReconciliationRecord,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionReconciliationResultClassification,
)
from volcanoes.infrastructure.execution_persistence.sqlite.connection import (
    FULL_SYNCHRONOUS_VALUE,
)
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    check_dispatch_claim_bindings,
    check_dispatch_outcome_bindings,
    check_foreign_keys,
    run_quick_check,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    KNOWN_MIGRATIONS,
    inspect_schema_state,
)
from volcanoes.infrastructure.execution_persistence.sqlite.schema import (
    EXPECTED_COLUMNS,
    EXPECTED_INDEXES,
    EXPECTED_TABLES,
    EXPECTED_TRIGGERS,
)


@dataclass(frozen=True, slots=True)
class SchemaValidationResult:
    """Immutable schema validation result."""

    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def blocks_execution(self) -> bool:
        return not self.passed


def validate_sqlite_execution_schema(
    connection: sqlite3.Connection,
    *,
    expected_busy_timeout_ms: int,
    require_wal: bool = True,
) -> SchemaValidationResult:
    """Validate schema and required connection state without mutation."""

    failures: list[str] = []

    _validate_connection_pragmas(
        connection,
        expected_busy_timeout_ms=expected_busy_timeout_ms,
        require_wal=require_wal,
        failures=failures,
    )
    _validate_schema_objects(connection, failures=failures)
    _validate_migrations(connection, failures=failures)

    quick_check = run_quick_check(connection)
    if not quick_check.passed:
        failures.append("quick_check failed")

    foreign_key_check = check_foreign_keys(connection)
    if not foreign_key_check.passed:
        failures.append("foreign_key_check failed")

    control = connection.execute(
        "SELECT enabled, paper_mode, emergency_stop_active, legacy_authority_active, generation FROM execution_dispatch_controls WHERE control_id='PAPER_DISPATCH'"
    ).fetchone()
    if control is None or int(control[1]) != 1 or int(control[4]) < 1:
        failures.append("dispatch control singleton is invalid")
    claim_bindings = check_dispatch_claim_bindings(connection)
    if not claim_bindings.passed:
        failures.append("dispatch claim bindings are invalid")
    outcome_bindings = check_dispatch_outcome_bindings(connection)
    if not outcome_bindings.passed:
        failures.append("dispatch outcome bindings are invalid")
    _validate_reconciliation_record_fingerprints(connection, failures=failures)

    return SchemaValidationResult(passed=not failures, failures=tuple(failures))


def _validate_connection_pragmas(
    connection: sqlite3.Connection,
    *,
    expected_busy_timeout_ms: int,
    require_wal: bool,
    failures: list[str],
) -> None:
    foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    if foreign_keys != 1:
        failures.append("foreign_keys pragma is not ON")

    synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
    if synchronous != FULL_SYNCHRONOUS_VALUE:
        failures.append("synchronous pragma is not FULL")

    busy_timeout = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
    if busy_timeout != expected_busy_timeout_ms:
        failures.append("busy_timeout pragma does not match expected value")

    if require_wal:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        if journal_mode.lower() != "wal":
            failures.append("journal_mode is not WAL")


def _validate_schema_objects(
    connection: sqlite3.Connection,
    *,
    failures: list[str],
) -> None:
    tables = _sqlite_objects(connection, "table")
    indexes = _sqlite_objects(connection, "index")
    triggers = _sqlite_objects(connection, "trigger")

    for table in EXPECTED_TABLES:
        if table not in tables:
            failures.append(f"missing table: {table}")
            continue
        table_columns = _table_columns(connection, table)
        for column in EXPECTED_COLUMNS[table]:
            if column not in table_columns:
                failures.append(f"missing column: {table}.{column}")

    for index in EXPECTED_INDEXES:
        if index not in indexes:
            failures.append(f"missing index: {index}")

    for trigger in EXPECTED_TRIGGERS:
        if trigger not in triggers:
            failures.append(f"missing trigger: {trigger}")


def _validate_migrations(
    connection: sqlite3.Connection,
    *,
    failures: list[str],
) -> None:
    state = inspect_schema_state(connection, known_migrations=KNOWN_MIGRATIONS)
    if state.incompatible_reason:
        failures.append(state.incompatible_reason)
    current_database_version = max(
        migration.resulting_version for migration in KNOWN_MIGRATIONS
    )
    if state.current_version != current_database_version:
        failures.append("schema version is not current")
    expected_checksums = {
        migration.migration_id: migration.checksum for migration in KNOWN_MIGRATIONS
    }
    for applied in state.applied_migrations:
        if expected_checksums.get(applied.migration_id) != applied.checksum:
            failures.append("known migration checksum changed")


def _validate_reconciliation_record_fingerprints(
    connection: sqlite3.Connection,
    *,
    failures: list[str],
) -> None:
    """Fail closed if immutable reconciliation content no longer matches its fingerprint."""

    rows = connection.execute("SELECT * FROM execution_reconciliations").fetchall()
    for row in rows:
        try:
            record = ExecutionReconciliationRecord(
                reconciliation_id=str(row["reconciliation_id"]),
                aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
                starting_local_revision=PaperExecutionRevision(
                    int(row["starting_local_revision"])
                ),
                starting_lifecycle_state=PaperExecutionLifecycleState(
                    str(row["starting_lifecycle_state"])
                ),
                broker_observation_references=tuple(
                    json.loads(str(row["broker_observation_references_json"]))
                ),
                result_classification=ExecutionReconciliationResultClassification(
                    str(row["result_classification"])
                ),
                operator_action_required=bool(row["operator_action_required"]),
                unresolved=bool(row["unresolved"]),
                safe_reason_code=str(row["safe_reason_code"]),
                recorded_at=datetime.fromisoformat(
                    str(row["recorded_at"]).replace("Z", "+00:00")
                ),
                schema_version=int(str(row["schema_version"])),
                resulting_transition_id=row["resulting_transition_id"],
                resulting_revision=(
                    None
                    if row["resulting_revision"] is None
                    else PaperExecutionRevision(int(row["resulting_revision"]))
                ),
                mode=PaperExecutionMode(str(row["mode"])),
            )
        except (TypeError, ValueError):
            failures.append("reconciliation record content is invalid")
            continue
        if str(row["record_fingerprint"]) != record.record_fingerprint:
            failures.append("reconciliation record fingerprint mismatch")


def _sqlite_objects(connection: sqlite3.Connection, object_type: str) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = ?
            """,
            (object_type,),
        )
    )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> frozenset[str]:
    return frozenset(
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    )


__all__ = [
    "SchemaValidationResult",
    "validate_sqlite_execution_schema",
]
