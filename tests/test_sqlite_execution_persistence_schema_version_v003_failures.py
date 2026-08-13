"""Negative-path and rollback specifications for the unregistered v003 migration.

Every database is created below pytest's ``tmp_path``.  The tests use explicit
v001/v002 setup and only exercise the SQLite migration boundary.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from volcanoes.infrastructure.execution_persistence.sqlite import (
    CONTRACT_ALIGNMENT_MIGRATION,
    INITIAL_MIGRATION,
    KNOWN_MIGRATIONS,
    SCHEMA_VERSION_TEXT_MIGRATION,
    SqliteExecutionMigration,
    apply_pending_migrations,
    inspect_schema_state,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionMigrationError,
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
TIMESTAMP = "2026-08-14T12:00:00.000000Z"
EXECUTION_TABLES = (
    "execution_aggregates",
    "execution_commands",
    "execution_idempotency",
    "execution_transitions",
    "execution_broker_references",
    "execution_receipts",
    "execution_failures",
    "execution_approvals",
    "execution_reconciliations",
)
SNAPSHOT_TABLES = (*EXECUTION_TABLES, "schema_migrations")
PRIMARY_KEYS = {
    "execution_aggregates": "aggregate_id",
    "execution_commands": "command_id",
    "execution_idempotency": "idempotency_key",
    "execution_transitions": "transition_record_id",
    "execution_broker_references": "broker_reference",
    "execution_receipts": "receipt_fingerprint",
    "execution_failures": "failure_fingerprint",
    "execution_approvals": "approval_fingerprint",
    "execution_reconciliations": "reconciliation_id",
}
INDEX_ATTACHMENTS = {
    "idx_execution_aggregates_lifecycle_state": "execution_aggregates",
    "idx_execution_aggregates_consequential_state": "execution_aggregates",
    "idx_execution_aggregates_updated_at": "execution_aggregates",
    "idx_execution_commands_aggregate_received": "execution_commands",
    "idx_execution_commands_idempotency_key": "execution_commands",
    "idx_execution_idempotency_aggregate": "execution_idempotency",
    "idx_execution_transitions_command": "execution_transitions",
    "ux_execution_broker_references_active_aggregate": "execution_broker_references",
    "idx_execution_broker_references_aggregate_active": "execution_broker_references",
    "idx_execution_receipts_command_aggregate": "execution_receipts",
    "idx_execution_failures_command_aggregate": "execution_failures",
    "idx_execution_reconciliations_aggregate_unresolved": "execution_reconciliations",
}
TRIGGER_ATTACHMENTS = {
    "trg_execution_commands_no_update": "execution_commands",
    "trg_execution_commands_no_delete": "execution_commands",
    "trg_execution_transitions_no_update": "execution_transitions",
    "trg_execution_transitions_no_delete": "execution_transitions",
    "trg_execution_receipts_no_update": "execution_receipts",
    "trg_execution_receipts_no_delete": "execution_receipts",
    "trg_execution_failures_no_update": "execution_failures",
    "trg_execution_failures_no_delete": "execution_failures",
    "trg_execution_approvals_no_update": "execution_approvals",
    "trg_execution_approvals_no_delete": "execution_approvals",
    "trg_execution_reconciliations_no_update": "execution_reconciliations",
    "trg_execution_reconciliations_no_delete": "execution_reconciliations",
}
CORRUPT_VALUES = (
    ("zero", 0, "integer"),
    ("negative", -1, "integer"),
    ("real", 1.5, "real"),
    ("text", "invalid", "text"),
    ("blob", b"1", "blob"),
)


def _connection(tmp_path: Path, name: str) -> sqlite3.Connection:
    return open_sqlite_execution_connection(tmp_path / name)


def _apply_through_v002(connection: sqlite3.Connection) -> None:
    result = apply_pending_migrations(
        connection,
        (INITIAL_MIGRATION, CONTRACT_ALIGNMENT_MIGRATION),
        applied_at=NOW,
        application_version="f5e2c-v003-c2-test",
    )
    assert result.applied_migration_ids == ("v001", "v002")
    assert result.schema_state.current_version == 2
    assert _migration_ids(connection) == ("v001", "v002")
    assert _v003_count(connection) == 0
    assert not connection.in_transaction


def _v003_count(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v003'"
        ).fetchone()[0]
    )


def _migration_ids(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT migration_id FROM schema_migrations "
            "ORDER BY resulting_schema_version, migration_id"
        ).fetchall()
    )


def _insert_all_rows(
    connection: sqlite3.Connection,
    suffix: str,
    versions: dict[str, object] | None = None,
) -> None:
    """Insert one valid, related v002 row in each durable execution table."""

    schema_versions = versions or {table: 1 for table in EXECUTION_TABLES}
    aggregate = f"agg-{suffix}"
    command = f"cmd-{suffix}"
    idempotency = f"idem-{suffix}"
    broker = f"broker-{suffix}"
    connection.execute(
        "INSERT INTO execution_aggregates VALUES (?, ?, 'CREATED', 0, '0', '1', "
        "NULL, 0, 0, 0, 0, 'PX-TRN-000', NULL, NULL, NULL, NULL, 'PAPER', ?, ?, ?, ?)",
        (aggregate, f"corr-{suffix}", TIMESTAMP, TIMESTAMP,
         schema_versions["execution_aggregates"], f"aggregate-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_commands VALUES (?, ?, ?, ?, 'SUBMIT', 0, ?, '{}', ?, ?, "
        "?, 'PENDING', 'PAPER', ?, ?)",
        (command, aggregate, f"corr-{suffix}", idempotency, f"payload-{suffix}",
         f"approval-{suffix}", f"policy-{suffix}", TIMESTAMP,
         schema_versions["execution_commands"], f"command-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_idempotency VALUES (?, ?, ?, ?, 'RESERVED', NULL, ?, NULL, "
        "0, 'PAPER', ?, ?)",
        (idempotency, f"logical-{suffix}", command, aggregate, TIMESTAMP,
         schema_versions["execution_idempotency"], f"idempotency-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_transitions VALUES (?, ?, ?, 'CREATED', 'READY_FOR_DISPATCH', "
        "0, 1, 'COMMAND', ?, ?, ?, ?, NULL, NULL, NULL, 'NONE', '[]', '[]', 'OK', "
        "'PAPER', ?, ?, ?)",
        (f"transition-{suffix}", aggregate, f"PX-TRN-{suffix}", f"input-{suffix}",
         command, f"corr-{suffix}", idempotency, TIMESTAMP,
         schema_versions["execution_transitions"], f"transition-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_broker_references VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, 1, "
        "NULL, 'PAPER', ?, ?)",
        (broker, aggregate, command, f"adapter-{suffix}", TIMESTAMP, TIMESTAMP,
         schema_versions["execution_broker_references"], f"broker-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_receipts VALUES (?, ?, ?, ?, 'SUBMIT', "
        "'COMMAND_ACCEPTED_LOCALLY', 'CREATED', 1, ?, 'OK', ?, 1, 0, ?, 'PAPER', ?, ?)",
        (f"receipt-{suffix}", aggregate, command, f"corr-{suffix}", TIMESTAMP, broker,
         TIMESTAMP, schema_versions["execution_receipts"], f"receipt-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_failures VALUES (?, ?, ?, ?, 'CONTRACT_VALIDATION', 'INFO', "
        "'SAFE', 'safe message', 0, 0, 0, 0, 0, ?, 'PAPER', ?, ?)",
        (f"failure-{suffix}", aggregate, command, f"corr-{suffix}", TIMESTAMP,
         schema_versions["execution_failures"], f"failure-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_approvals VALUES (?, ?, 'OPERATOR', ?, ?, ?, NULL, ?, "
        "'PAPER', ?, ?)",
        (f"approval-{suffix}", f"bound-{suffix}", f"operator-{suffix}", TIMESTAMP,
         TIMESTAMP, TIMESTAMP, schema_versions["execution_approvals"],
         f"approval-fp-{suffix}"),
    )
    connection.execute(
        "INSERT INTO execution_reconciliations VALUES (?, ?, 1, 'READY_FOR_DISPATCH', '[]', "
        "'UNRESOLVED', ?, 1, 1, 1, 'SAFE', ?, 'PAPER', ?, ?)",
        (f"reconciliation-{suffix}", aggregate, f"PX-TRN-{suffix}", TIMESTAMP,
         schema_versions["execution_reconciliations"], f"reconciliation-fp-{suffix}"),
    )


def _prepare_populated_v002(connection: sqlite3.Connection, suffix: str) -> None:
    _apply_through_v002(connection)
    _insert_all_rows(connection, suffix)
    connection.commit()
    assert not connection.in_transaction
    assert _migration_ids(connection) == ("v001", "v002")
    assert _v003_count(connection) == 0


def _snapshot(connection: sqlite3.Connection) -> dict[str, object]:
    rows = {
        table: tuple(
            tuple(row) + tuple(
                connection.execute(
                    f"SELECT typeof(schema_version) FROM {table} "
                    f"WHERE {PRIMARY_KEYS[table]} = ?",
                    (row[PRIMARY_KEYS[table]],),
                ).fetchone()
            )
            for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY {PRIMARY_KEYS[table]}"
            ).fetchall()
        )
        for table in EXECUTION_TABLES
    }
    schema_inventory = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    )
    index_rows = connection.execute(
        "SELECT name, tbl_name, sql FROM sqlite_schema WHERE type = 'index' "
        f"AND tbl_name IN ({', '.join('?' for _ in SNAPSHOT_TABLES)}) "
        "ORDER BY tbl_name, name",
        SNAPSHOT_TABLES,
    ).fetchall()
    index_lists = {
        table: {
            str(row["name"]): tuple(row)
            for row in connection.execute(f"PRAGMA index_list({table})").fetchall()
        }
        for table in SNAPSHOT_TABLES
    }
    return {
        "rows": rows,
        "migrations": tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT migration_id, migration_name, checksum, applied_at, "
                "application_version, previous_schema_version, resulting_schema_version, "
                "safe_notes FROM schema_migrations "
                "ORDER BY resulting_schema_version, migration_id"
            ).fetchall()
        ),
        "current_version": inspect_schema_state(
            connection, known_migrations=KNOWN_MIGRATIONS
        ).current_version,
        "schema_inventory": schema_inventory,
        "columns": {
            table: tuple(
                tuple(row)
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            for table in SNAPSHOT_TABLES
        },
        "primary_keys": {
            table: tuple(
                (row["name"], row["pk"])
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                if int(row["pk"])
            )
            for table in SNAPSHOT_TABLES
        },
        "foreign_keys": {
            table: tuple(
                tuple(row)
                for row in connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
            )
            for table in SNAPSHOT_TABLES
        },
        "indexes": tuple(
            (
                row["name"],
                row["tbl_name"],
                row["sql"],
                index_lists[str(row["tbl_name"])][str(row["name"])],
                tuple(
                    sorted(
                        (
                            tuple(index_row)
                            for index_row in connection.execute(
                                f"PRAGMA index_xinfo({row['name']})"
                            ).fetchall()
                        ),
                        key=lambda index_row: int(index_row[0]),
                    )
                ),
            )
            for row in index_rows
        ),
        "triggers": tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT name, tbl_name, sql FROM sqlite_schema "
                "WHERE type = 'trigger' ORDER BY name"
            ).fetchall()
        ),
        "foreign_key_check": tuple(
            sorted(
                (
                    tuple(row)
                    for row in connection.execute("PRAGMA foreign_key_check").fetchall()
                ),
                key=lambda row: (
                    str(row[0]),
                    row[1] is not None,
                    0 if row[1] is None else int(row[1]),
                    str(row[2]),
                    int(row[3]),
                ),
            )
        ),
        "legacy_tables": tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' "
                "AND name LIKE '_v002_%' ORDER BY name"
            ).fetchall()
        ),
        "guard_present": connection.execute(
            "SELECT name FROM sqlite_temp_master "
            "WHERE type = 'table' AND name = '_v003_guard'"
        ).fetchone()
        is not None,
    }


def _assert_exact_v002_rollback(
    connection: sqlite3.Connection, before: dict[str, object]
) -> None:
    assert _snapshot(connection) == before
    assert before["current_version"] == 2
    assert _migration_ids(connection) == ("v001", "v002")
    assert _v003_count(connection) == 0
    assert not connection.in_transaction
    assert connection.execute("SELECT 1").fetchone()[0] == 1


def _v003_descriptor(sql_text: str) -> SqliteExecutionMigration:
    return SqliteExecutionMigration.create(
        migration_id="v003",
        name=SCHEMA_VERSION_TEXT_MIGRATION.name,
        previous_version=2,
        resulting_version=3,
        sql_text=sql_text,
        irreversible=True,
        safe_description=SCHEMA_VERSION_TEXT_MIGRATION.safe_description,
    )


def _attempt(connection: sqlite3.Connection, v003: SqliteExecutionMigration) -> None:
    apply_pending_migrations(
        connection,
        (INITIAL_MIGRATION, CONTRACT_ALIGNMENT_MIGRATION, v003),
        applied_at=NOW,
        application_version="f5e2c-v003-c2-test",
    )


def _assert_migration_failure(
    connection: sqlite3.Connection, v003: SqliteExecutionMigration
) -> sqlite3.Error:
    with pytest.raises(SqliteExecutionMigrationError, match="SQLite migration failed") as exc:
        _attempt(connection, v003)
    assert isinstance(exc.value.__cause__, sqlite3.Error)
    return exc.value.__cause__


def _remove_recreated_object(source: str, name: str, table: str, kind: str) -> str:
    if kind == "index":
        pattern = re.compile(
            rf"CREATE (?:UNIQUE )?INDEX {re.escape(name)}\n"
            rf"ON {re.escape(table)}.*?;\n",
            re.DOTALL,
        )
    else:
        pattern = re.compile(
            rf"CREATE TRIGGER {re.escape(name)}\n"
            rf"BEFORE (?:UPDATE|DELETE) ON {re.escape(table)}\n"
            rf"BEGIN\n    SELECT RAISE\(ABORT, '.*?'\);\nEND;\n",
            re.DOTALL,
        )
    altered, changed = pattern.subn("", source, count=1)
    assert changed == 1
    assert pattern.search(altered) is None
    return altered


def _duplicate_copy_statement(source: str, table: str) -> str:
    pattern = re.compile(
        rf"(INSERT INTO {re.escape(table)} \(.+?\)\n"
        rf"SELECT .+? FROM _v002_{re.escape(table)};)"
    )
    match = pattern.search(source)
    assert match is not None
    assert len(pattern.findall(source)) == 1
    statement = match.group(1)
    return source[: match.end()] + "\n" + statement + source[match.end() :]


def test_v003_rejects_when_foreign_keys_are_disabled(tmp_path: Path) -> None:
    connection = _connection(tmp_path, "foreign-keys-off.sqlite")
    try:
        _prepare_populated_v002(connection, "foreign-keys-off")
        before = _snapshot(connection)
        connection.execute("PRAGMA foreign_keys = OFF")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        cause = _assert_migration_failure(connection, SCHEMA_VERSION_TEXT_MIGRATION)
        assert "CHECK constraint failed" in str(cause)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        _assert_exact_v002_rollback(connection, before)
    finally:
        connection.close()


def test_v003_rejects_when_legacy_alter_table_is_enabled(tmp_path: Path) -> None:
    connection = _connection(tmp_path, "legacy-alter-table.sqlite")
    try:
        _prepare_populated_v002(connection, "legacy-alter")
        before = _snapshot(connection)
        connection.execute("PRAGMA legacy_alter_table = ON")
        assert connection.execute("PRAGMA legacy_alter_table").fetchone()[0] == 1
        cause = _assert_migration_failure(connection, SCHEMA_VERSION_TEXT_MIGRATION)
        assert "CHECK constraint failed" in str(cause)
        assert connection.execute("PRAGMA legacy_alter_table").fetchone()[0] == 1
        _assert_exact_v002_rollback(connection, before)
    finally:
        connection.close()


@pytest.mark.parametrize("table_name", EXECUTION_TABLES)
@pytest.mark.parametrize("label, value, expected_type", CORRUPT_VALUES)
def test_v003_rejects_each_durable_noninteger_v002_schema_version(
    tmp_path: Path, table_name: str, label: str, value: object, expected_type: str
) -> None:
    connection = _connection(tmp_path, f"corrupt-{table_name}-{label}.sqlite")
    try:
        _apply_through_v002(connection)
        connection.execute("PRAGMA ignore_check_constraints = ON")
        assert connection.execute("PRAGMA ignore_check_constraints").fetchone()[0] == 1
        versions: dict[str, object] = {table: 1 for table in EXECUTION_TABLES}
        versions[table_name] = value
        _insert_all_rows(connection, f"corrupt-{table_name}-{label}", versions)
        connection.commit()
        connection.execute("PRAGMA ignore_check_constraints = OFF")
        assert connection.execute("PRAGMA ignore_check_constraints").fetchone()[0] == 0
        stored = connection.execute(
            f"SELECT schema_version, typeof(schema_version) FROM {table_name} "
            f"ORDER BY {PRIMARY_KEYS[table_name]}"
        ).fetchone()
        assert stored is not None
        assert tuple(stored) == (value, expected_type)
        before = _snapshot(connection)
        cause = _assert_migration_failure(connection, SCHEMA_VERSION_TEXT_MIGRATION)
        assert "CHECK constraint failed" in str(cause)
        _assert_exact_v002_rollback(connection, before)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("name", "table", "kind"),
    tuple((name, table, "index") for name, table in INDEX_ATTACHMENTS.items())
    + tuple((name, table, "trigger") for name, table in TRIGGER_ATTACHMENTS.items()),
)
def test_v003_rolls_back_when_a_required_recreated_object_is_omitted(
    tmp_path: Path, name: str, table: str, kind: str
) -> None:
    connection = _connection(tmp_path, f"missing-{kind}-{name}.sqlite")
    try:
        expected_attachment = (
            INDEX_ATTACHMENTS[name] if kind == "index" else TRIGGER_ATTACHMENTS[name]
        )
        assert expected_attachment == table
        _prepare_populated_v002(connection, f"missing-{name}")
        before = _snapshot(connection)
        altered = _remove_recreated_object(
            SCHEMA_VERSION_TEXT_MIGRATION.sql_text, name, table, kind
        )
        cause = _assert_migration_failure(connection, _v003_descriptor(altered))
        assert "CHECK constraint failed" in str(cause)
        _assert_exact_v002_rollback(connection, before)
    finally:
        connection.close()


def test_v003_preserves_preexisting_foreign_key_corruption_on_rejection(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "foreign-key-corruption.sqlite")
    try:
        _prepare_populated_v002(connection, "orphan-base")
        connection.execute("PRAGMA foreign_keys = OFF")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        connection.execute(
            "INSERT INTO execution_commands VALUES (?, ?, ?, ?, 'SUBMIT', 0, ?, '{}', ?, ?, "
            "?, 'PENDING', 'PAPER', 1, ?)",
            (
                "cmd-orphan",
                "agg-missing",
                "corr-orphan",
                "idem-orphan",
                "payload-orphan",
                "approval-orphan",
                "policy-orphan",
                TIMESTAMP,
                "command-fp-orphan",
            ),
        )
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        violations = tuple(
            tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        assert violations == (("execution_commands", 2, "execution_aggregates", 0),)
        before = _snapshot(connection)
        cause = _assert_migration_failure(connection, SCHEMA_VERSION_TEXT_MIGRATION)
        assert "CHECK constraint failed" in str(cause)
        _assert_exact_v002_rollback(connection, before)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "table_name",
    (
        "execution_aggregates",
        "execution_broker_references",
        "execution_reconciliations",
    ),
)
def test_v003_rolls_back_when_a_copy_statement_replays_existing_rows(
    tmp_path: Path, table_name: str
) -> None:
    connection = _connection(tmp_path, f"duplicate-copy-{table_name}.sqlite")
    try:
        _prepare_populated_v002(connection, f"copy-{table_name}")
        before = _snapshot(connection)
        altered = _duplicate_copy_statement(
            SCHEMA_VERSION_TEXT_MIGRATION.sql_text, table_name
        )
        cause = _assert_migration_failure(connection, _v003_descriptor(altered))
        assert "UNIQUE constraint failed" in str(cause)
        _assert_exact_v002_rollback(connection, before)
    finally:
        connection.close()
